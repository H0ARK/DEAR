# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import time
from typing import List, Optional, cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage

from src.graph import build_graph_with_memory
from src.server.chat_request import ChatRequest, ChatMessage, RepositoryInfo

logger = logging.getLogger(__name__)

def register_chat_routes(app: FastAPI):
    """Register chat-related routes with the FastAPI app."""
    
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
                request.wait_for_input,
                request.enable_background_investigation,
                request.repository_info,
                request.locale,
            ),
            media_type="text/event-stream",
        )

    async def _astream_workflow_generator(
        messages: List[ChatMessage],
        thread_id: str,
        max_plan_iterations: int = 3,
        max_step_num: int = 10,
        wait_for_input: bool = True,
        enable_background_investigation: bool = True,
        repository_info: Optional[RepositoryInfo] = None,
        locale: str = "en-US",
    ):
        """Generate a stream of events from the workflow."""
        # Convert messages to the format expected by the graph
        converted_messages = []
        for message in messages:
            if message.role == "user":
                converted_messages.append({"type": "human", "content": message.content})
            elif message.role == "assistant":
                converted_messages.append({"type": "ai", "content": message.content})
            elif message.role == "system":
                converted_messages.append({"type": "system", "content": message.content})
            elif message.role == "tool":
                converted_messages.append(
                    {
                        "type": "tool",
                        "content": message.content,
                        "tool_call_id": message.tool_call_id,
                    }
                )

        # Build the graph with memory
        graph = build_graph_with_memory(thread_id)

        # Prepare the config
        config = {
            "configurable": {
                "thread_id": thread_id,
                "max_plan_iterations": max_plan_iterations,
                "max_step_num": max_step_num,
                "wait_for_input": wait_for_input,
                "repository_info": repository_info.model_dump() if repository_info else None,
                "locale": locale,
            }
        }

        # Prepare the input
        input_data = {
            "messages": converted_messages,
            "enable_background_investigation": enable_background_investigation,
            "wait_for_input": wait_for_input,
        }

        # Stream the events
        try:
            stream = graph.astream_events(input_data, config=config)
            async for event in stream:
                if event["event"] == "on_chat_model_stream":
                    if isinstance(event["data"], AIMessageChunk):
                        yield f"data: {json.dumps({'type': 'token', 'content': event['data'].content})}\n\n"
                elif event["event"] == "on_tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': event['name'], 'input': event['data']})}\n\n"
                elif event["event"] == "on_tool_end":
                    if isinstance(event["data"], ToolMessage):
                        yield f"data: {json.dumps({'type': 'tool_end', 'name': event['name'], 'output': event['data'].content})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'tool_end', 'name': event['name'], 'output': event['data']})}\n\n"
                elif event["event"] == "on_chain_end":
                    yield f"data: {json.dumps({'type': 'chain_end', 'output': event['data']})}\n\n"
        except Exception as e:
            logger.error(f"Error in workflow: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'end'})}\n\n"

