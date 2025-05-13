# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import base64
import json
import logging
import os
import random
import time
from typing import List, Optional, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.types import Command

from src.graph import build_graph_with_memory
from src.podcast.graph.builder import build_graph as build_podcast_graph
from src.ppt.graph.builder import build_graph as build_ppt_graph
from src.prose.graph.builder import build_graph as build_prose_graph
from src.server.chat_request import (
    ChatMessage,
    ChatRequest,
    GeneratePodcastRequest,
    GeneratePPTRequest,
    GenerateProseRequest,
    RepositoryInfo,
    TTSRequest,
)
from src.server.mcp_request import MCPServerMetadataRequest, MCPServerMetadataResponse
from src.server.mcp_utils import load_mcp_tools
from src.tools import VolcengineTTS

logger = logging.getLogger(__name__)

app = FastAPI(
    title="DeerFlow API",
    description="API for Deer",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

graph = build_graph_with_memory()


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    thread_id = request.thread_id
    if thread_id == "__default__":
        thread_id = str(uuid4())
    return StreamingResponse(
        _astream_workflow_generator(
            request.model_dump()["messages"],
            thread_id,
            request.max_plan_iterations,
            request.max_step_num,
            request.auto_accepted_plan,
            request.interrupt_feedback,
            request.mcp_settings,
            request.enable_background_investigation,
            request.repository,
            request.create_workspace,
            request.force_interactive,
        ),
        media_type="text/event-stream",
    )


async def _astream_workflow_generator(
    messages: List[ChatMessage],
    thread_id: str,
    max_plan_iterations: int,
    max_step_num: int,
    auto_accepted_plan: bool,
    initial_context_user_feedback: Optional[str],
    mcp_settings: dict,
    enable_background_investigation: bool,
    repository: Optional[RepositoryInfo] = None,
    create_workspace: bool = False,
    force_interactive: bool = True,
):
    input_ = {
        "messages": messages,
        "plan_iterations": 0,
        "final_report": "",
        "current_plan": None,
        "observations": [],
        "auto_accepted_plan": auto_accepted_plan,
        "enable_background_investigation": enable_background_investigation,
        "force_interactive": force_interactive,
        "prd_iterations": 0,
        "create_workspace": create_workspace,
        "awaiting_initial_context_input": False,
        "initial_context_approved": False,
        "last_initial_context_feedback": None,
    }

    if repository:
        input_["repository"] = repository.model_dump()
        logger.info(f"Using repository from UI: {repository.fullName}")

    if initial_context_user_feedback:
        logger.info(f"Received user feedback for initial context: {initial_context_user_feedback}")
        input_["last_initial_context_feedback"] = initial_context_user_feedback
        input_["awaiting_initial_context_input"] = False

    current_graph_config = {
        "thread_id": thread_id,
        "max_plan_iterations": max_plan_iterations,
        "max_step_num": max_step_num,
        "mcp_settings": mcp_settings,
        "configurable": {
            "max_plan_iterations": max_plan_iterations,
            "max_step_num": max_step_num,
            "force_interactive": force_interactive,
            "mcp_settings": mcp_settings,
            "workspace_path": repository.fullName if repository else None,
            "github_token": os.environ.get("GITHUB_TOKEN", ""),
        }
    }
    
    async for path, op, data_for_op in graph.astream(
        input_,
        config=current_graph_config,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        agent_name_for_event = path[0].split(":")[0] if path and path[0] else "deer_ai_handler"

        if op == "update":
            state_values = data_for_op.get("values", {})
            if state_values.get("awaiting_initial_context_input") and state_values.get("pending_initial_context_query"):
                query_content = state_values["pending_initial_context_query"]
                logger.info(f"Detected pending initial context query: {query_content[:100]}...")
                yield _make_event(
                    "human_context_query",
                    {
                        "thread_id": thread_id,
                        "id": f"initial_context_query-{random.randint(1000, 9999)}",
                        "agent": "deer_ai_handler",
                        "role": "assistant",
                        "content": query_content,
                        "query_type": "initial_context_review",
                        "finish_reason": "human_query",
                    },
                )
                continue
            continue

        elif op == "stream":
            message_chunk = cast(AIMessageChunk, data_for_op)
            event_stream_message: dict[str, any] = {
                "thread_id": thread_id,
                "agent": agent_name_for_event,
                "id": message_chunk.id,
                "role": "assistant",
                "content": message_chunk.content,
            }
            if message_chunk.response_metadata.get("finish_reason"):
                event_stream_message["finish_reason"] = message_chunk.response_metadata.get("finish_reason")
            
            if isinstance(message_chunk, ToolMessage):
                event_stream_message["tool_call_id"] = message_chunk.tool_call_id
                yield _make_event("tool_call_result", event_stream_message)
            else:
                if message_chunk.tool_calls:
                    event_stream_message["tool_calls"] = message_chunk.tool_calls
                    event_stream_message["tool_call_chunks"] = message_chunk.tool_call_chunks
                    yield _make_event("tool_calls", event_stream_message)
                elif message_chunk.tool_call_chunks:
                    event_stream_message["tool_call_chunks"] = message_chunk.tool_call_chunks
                    yield _make_event("tool_call_chunks", event_stream_message)
                else:
                    yield _make_event("message_chunk", event_stream_message)
            continue

        if isinstance(data_for_op, dict) and "__interrupt__" in data_for_op:
            interrupt_info_dict = data_for_op["__interrupt__"]
            logger.warning(f"Old __interrupt__ event triggered with data: {data_for_op}. Op was '{op}'. This might be unexpected.")
            
            interrupt_node_id = "unknown_interrupt_node"
            interrupt_content = "An interruption has occurred."
            options = []

            interrupt_items = []
            if isinstance(interrupt_info_dict, list) and len(interrupt_info_dict) > 0:
                interrupt_items = interrupt_info_dict
            elif hasattr(interrupt_info_dict, 'ns'):
                interrupt_items = [interrupt_info_dict]
            
            if interrupt_items:
                first_interrupt_item = interrupt_items[0]
                logger.info(f"Interrupt item: {first_interrupt_item}")
                if hasattr(first_interrupt_item, 'ns') and first_interrupt_item.ns and len(first_interrupt_item.ns) > 0:
                    interrupt_node_id = first_interrupt_item.ns[0]
                    logger.info(f"Found interrupt node ID: {interrupt_node_id}")
                if hasattr(first_interrupt_item, 'value'):
                    interrupt_content = first_interrupt_item.value
                    logger.info(f"Found interrupt content: {interrupt_content[:100]}...")
                
                if interrupt_node_id == "human_prd_review":
                    options = [
                        {"text": "Approve PRD", "value": "approve"},
                        {"text": "Revise PRD (add feedback)", "value": "revise_prd"},
                        {"text": "Needs more research", "value": "research_needed"},
                    ]
                elif interrupt_node_id == "human_feedback_plan":
                     options = [
                        {"text": "Accept Plan", "value": "accept"},
                        {"text": "Revise Plan (add feedback)", "value": "revise_plan"},
                    ]
                else:
                    options = [{"text": "Continue", "value": "continue"}, {"text": "Abort", "value": "abort"}]
            else:
                logger.warning("'__interrupt__' key found but its value is empty or not as expected.")

            message_id = f"msg-{interrupt_node_id}-{random.randint(1000, 9999)}"
            yield _make_event(
                "message_chunk",
                {
                    "thread_id": thread_id, "agent": agent_name_for_event, "id": message_id,
                    "role": "assistant", "content": interrupt_content, "finish_reason": "stop",
                },
            )
            time.sleep(0.5)
            interrupt_event_id = f"{interrupt_node_id}-{random.randint(1000, 9999)}"
            yield _make_event(
                "interrupt",
                {
                    "thread_id": thread_id, "id": interrupt_event_id, "role": "assistant",
                    "content": "Please provide your feedback:", "finish_reason": "interrupt", "options": options,
                },
            )
            continue

        logger.debug(f"Graph event not specifically handled for SSE: op='{op}', data_type='{type(data_for_op)}'")


def _make_event(event_type: str, data: dict[str, any]):
    if data.get("content") == "":
        data.pop("content")
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech using volcengine TTS API."""
    try:
        app_id = os.getenv("VOLCENGINE_TTS_APPID", "")
        if not app_id:
            raise HTTPException(
                status_code=400, detail="VOLCENGINE_TTS_APPID is not set"
            )
        access_token = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", "")
        if not access_token:
            raise HTTPException(
                status_code=400, detail="VOLCENGINE_TTS_ACCESS_TOKEN is not set"
            )
        cluster = os.getenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
        voice_type = os.getenv("VOLCENGINE_TTS_VOICE_TYPE", "BV700_V2_streaming")

        tts_client = VolcengineTTS(
            appid=app_id,
            access_token=access_token,
            cluster=cluster,
            voice_type=voice_type,
        )
        # Call the TTS API
        result = tts_client.text_to_speech(
            text=request.text[:1024],
            encoding=request.encoding,
            speed_ratio=request.speed_ratio,
            volume_ratio=request.volume_ratio,
            pitch_ratio=request.pitch_ratio,
            text_type=request.text_type,
            with_frontend=request.with_frontend,
            frontend_type=request.frontend_type,
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=str(result["error"]))

        # Decode the base64 audio data
        audio_data = base64.b64decode(result["audio_data"])

        # Return the audio file
        return Response(
            content=audio_data,
            media_type=f"audio/{request.encoding}",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=tts_output.{request.encoding}"
                )
            },
        )
    except Exception as e:
        logger.exception(f"Error in TTS endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/podcast/generate")
async def generate_podcast(request: GeneratePodcastRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_podcast_graph()
        final_state = workflow.invoke({"input": report_content})
        audio_bytes = final_state["output"]
        return Response(content=audio_bytes, media_type="audio/mp3")
    except Exception as e:
        logger.exception(f"Error occurred during podcast generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ppt/generate")
async def generate_ppt(request: GeneratePPTRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_ppt_graph()
        final_state = workflow.invoke({"input": report_content})
        generated_file_path = final_state["generated_file_path"]
        with open(generated_file_path, "rb") as f:
            ppt_bytes = f.read()
        return Response(
            content=ppt_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        logger.exception(f"Error occurred during ppt generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prose/generate")
async def generate_prose(request: GenerateProseRequest):
    try:
        logger.info(f"Generating prose for prompt: {request.prompt}")
        workflow = build_prose_graph()
        events = workflow.astream(
            {
                "content": request.prompt,
                "option": request.option,
                "command": request.command,
            },
            stream_mode="messages",
            subgraphs=True,
        )
        return StreamingResponse(
            (f"data: {event[0].content}\n\n" async for _, event in events),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.exception(f"Error occurred during prose generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
async def mcp_server_metadata(request: MCPServerMetadataRequest):
    """Get information about an MCP server."""
    try:
        # Set default timeout with a longer value for this endpoint
        timeout = 300  # Default to 300 seconds for this endpoint

        # Use custom timeout from request if provided
        if request.timeout_seconds is not None:
            timeout = request.timeout_seconds

        # Load tools from the MCP server using the utility function
        tools = await load_mcp_tools(
            server_type=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            timeout_seconds=timeout,
        )

        # Create the response with tools
        response = MCPServerMetadataResponse(
            transport=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            tools=tools,
        )

        return response
    except Exception as e:
        if not isinstance(e, HTTPException):
            logger.exception(f"Error in MCP server metadata endpoint: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        raise
