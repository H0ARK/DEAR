# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import time
from typing import List, Optional, cast, Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage, BaseMessage
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph_with_memory
from src.server.chat_request import ChatRequest, ChatMessage, RepositoryInfo

logger = logging.getLogger(__name__)

# Global MemorySaver instance
shared_memory_checkpointer = MemorySaver()

def register_chat_routes(app: FastAPI):
    """Register chat-related routes with the FastAPI app."""
    
    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest):
        thread_id = request.thread_id
        if thread_id == "__default__":
            thread_id = str(uuid4())
        
        # Ensure messages is not None, pass the list of ChatMessage objects
        input_messages = request.messages if request.messages is not None else []

        return StreamingResponse(
            _astream_workflow_generator(
                input_messages, # Pass the list of ChatMessage objects
                thread_id,
                request.max_plan_iterations,
                request.max_step_num,
                request.user_feedback_payload,
                request.force_interactive,
                request.enable_background_investigation,
                request.repository,
                request.locale,
            ),
            media_type="text/event-stream",
        )

    async def _astream_workflow_generator(
        messages: List[ChatMessage],
        thread_id: str,
        max_plan_iterations: int = 3,
        max_step_num: int = 10,
        user_feedback_payload: Optional[dict] = None,
        force_interactive: bool = True,
        enable_background_investigation: bool = True,
        repository_info: Optional[RepositoryInfo] = None,
        locale: str = "en-US",
    ):
        """Generate a stream of events from the workflow."""
        # Convert only the latest message to the format expected by the graph
        # Assumes the client sends messages in order, and the last one is the newest.
        latest_message_converted = []
        if messages: # If there are any messages
            message = messages[-1] # Get the last message
            if message.role == "user":
                latest_message_converted.append({"type": "human", "content": message.content})
            elif message.role == "assistant": # Should generally not be the latest input, but handle defensively
                latest_message_converted.append({"type": "ai", "content": message.content})
            elif message.role == "system": # System messages usually aren't part of iterative chat input this way
                latest_message_converted.append({"type": "system", "content": message.content})
            elif message.role == "tool":
                latest_message_converted.append(
                    {
                        "type": "tool",
                        "content": message.content,
                        "tool_call_id": message.tool_call_id,
                    }
                )
        
        if not latest_message_converted and not user_feedback_payload: # If no new message and no feedback, it's problematic
            logger.warning("No new message to process in _astream_workflow_generator and no feedback payload.")
            # Depending on desired behavior, you might want to yield an error or handle differently.
            # For now, we'll proceed, but the graph might not have new input to act on unless feedback is present.

        # Build the graph with the shared memory checkpointer
        graph = build_graph_with_memory(checkpointer=shared_memory_checkpointer)

        # Prepare the config
        config = {
            "configurable": {
                "thread_id": thread_id,
                "max_plan_iterations": max_plan_iterations,
                "max_step_num": max_step_num,
                "force_interactive": force_interactive,
                "repository_info": repository_info.model_dump() if repository_info else None,
                "locale": locale,
            }
        }

        # Prepare the input
        input_data = {
            "messages": latest_message_converted, # Use only the latest converted message
            "enable_background_investigation": enable_background_investigation,
            "force_interactive": force_interactive,
        }

        # Add feedback if provided
        if user_feedback_payload:
            if "last_initial_context_feedback" in user_feedback_payload:
                input_data["last_initial_context_feedback"] = user_feedback_payload["last_initial_context_feedback"]
            if "last_prd_feedback" in user_feedback_payload:
                input_data["last_prd_feedback"] = user_feedback_payload["last_prd_feedback"]
            if "last_plan_feedback" in user_feedback_payload:
                input_data["last_plan_feedback"] = user_feedback_payload["last_plan_feedback"]

        # Stream the events
        try:
            # Use stream_mode='updates' to get state diffs, or 'values' for full state.
            # 'debug' provides the most comprehensive info including state.
            # stream = graph.astream_events(input_data, config=config, stream_mode="updates")
            stream = graph.astream_events(input_data, config=config, stream_mode="debug")
            
            async for event in stream:
                event_type = event["event"]
                event_data = event["data"]
                event_name = event.get("name", "") # Node name for some events

                # Log the raw event for debugging if needed
                logger.debug(f"Raw event type: {event_type}, name: {event_name}")
                # logger.debug(f"Raw event: {event}") # Uncomment for full event data if needed
                
                # --- Handle Interrupt Exception Events ---
                if event_type == "on_end" and isinstance(event_data.get("output"), dict) and "values" in event_data["output"] and (
                    event_data["output"]["values"].get("awaiting_initial_context_input") or
                    event_data["output"]["values"].get("awaiting_prd_review_input") or
                    event_data["output"]["values"].get("awaiting_plan_review_input")
                ):
                    # This is an end event where the state indicates a human interrupt is needed.
                    # This pattern might occur if the graph finishes an execution pass but the state
                    # signals a required interrupt that wasn't caught by a specific interrupt event.
                    # It's safer to rely on a specific LangGraph interrupt event if available,
                    # but this handles the case where the state flags are the primary indicator.
                    current_state_values = event_data["output"]["values"]
                    
                    # Determine which type of interrupt it is and get the pending query
                    interrupt_type = "unknown"
                    query_content = "An interrupt occurred."

                    if current_state_values.get("awaiting_initial_context_input") and current_state_values.get("pending_initial_context_query"):
                         interrupt_type = "initial_context_review"
                         query_content = current_state_values["pending_initial_context_query"]
                    elif current_state_values.get("awaiting_prd_review_input") and current_state_values.get("pending_prd_review_query"):
                         interrupt_type = "prd_review"
                         query_content = current_state_values["pending_prd_review_query"]
                    elif current_state_values.get("awaiting_plan_review_input") and current_state_values.get("pending_plan_review_query"):
                         interrupt_type = "plan_review"
                         query_content = current_state_values["pending_plan_review_query"]

                    logger.critical(f"SERVER: Detected human interrupt needed ({interrupt_type}). Sending SSE and stopping stream.")
                    yield _make_event_sse(
                        "interrupt_required", # Custom event type for the frontend
                        {
                            "thread_id": thread_id,
                            "interrupt_type": interrupt_type,
                            "query": query_content,
                            "agent": event_name or "deer_ai_handler",
                        }
                    )
                    # CRITICAL: Stop the generator to pause and wait for client feedback
                    return 

                # --- Existing Event Handling Logic ---
                elif event_type == "on_chat_model_stream":
                    chunk = event_data.get("chunk")
                    if isinstance(chunk, AIMessageChunk):
                        # Using a single consistent approach for all models (OpenAI, Gemini, etc.)
                        # Let LangChain handle the formatting differences between providers
                        logger.info(f"Sending message chunk from {event_name or 'unknown_agent'}, content: '{chunk.content[:30]}...'")
                        
                        # Check if this is a final chunk with finish_reason
                        if event_data.get("finish_reason"):
                            yield _make_event_sse("message_chunk", {
                                "content": chunk.content, 
                                "agent": event_name or "assistant", 
                                "thread_id": thread_id,
                                "role": "assistant",
                                "finish_reason": event_data.get("finish_reason")
                            })
                        else:
                            yield _make_event_sse("message_chunk", {
                                "content": chunk.content, 
                                "agent": event_name or "assistant",
                                "thread_id": thread_id,
                                "role": "assistant"
                            })
                            
                elif event_type == "on_tool_start":
                    yield _make_event_sse("tool_start", {"name": event_name, "input": event_data.get("input")})
                elif event_type == "on_tool_end":
                    output = event_data.get("output")
                    # LangGraph might wrap Command objects in ToolMessage for tool_end
                    if isinstance(output, ToolMessage) and isinstance(output.content, Command):
                         logger.warning(f"on_tool_end for node '{event_name}' resulted in a Command object within ToolMessage. Processed internally. Command: {output.content}")
                         yield _make_event_sse("info", {"name": event_name, "message": "Tool returned a Command, processed internally."})
                    elif isinstance(output, ToolMessage):
                        yield _make_event_sse("tool_end", {"name": event_name, "output": output.content})
                    else:
                        yield _make_event_sse("tool_end", {"name": event_name, "output": output})
                elif event_type == "on_chain_end": # This event often contains final state or node outputs
                    current_state_values = None
                    # Handle both stream_mode='updates' (output in event_data['output']['values'])
                    # and potentially stream_mode='values' (output directly in event_data['values'])
                    if isinstance(event_data.get("output"), dict) and "values" in event_data["output"]:
                        current_state_values = event_data["output"]["values"]
                    elif isinstance(event_data, dict) and "values" in event_data: # For stream_mode="values" on graph directly
                         current_state_values = event_data["values"]

                    # Handle non-interrupt related on_chain_end events
                    # This part remains to process final outputs or state changes that are NOT interrupts
                    if current_state_values:
                        # If it's not an interrupt state (already handled at the top),
                        # decide what other state changes or final outputs to send.
                        # For now, we might not send full state on every on_chain_end unless needed,
                        # focusing on tokens, tool outputs, and explicit interrupts.
                        pass # No action needed for non-interrupt state in this specific handler for now

                    else: # Fallback or other chain_end events
                        output_data = event_data.get("output", {})

                        # If the output is a Command object, don't try to serialize it directly.
                        # This usually means LangGraph is handling it internally.
                        # We can log it for debugging or decide if parts of it should be sent.
                        if isinstance(output_data, Command):
                            logger.warning(f"on_chain_end for node '{event_name}' resulted in a Command object. This is unusual for direct serialization. Command: {output_data}")
                            # Optionally, decide if you want to send a placeholder or parts of the command if safe
                            # For now, let's just skip sending this specific problematic event or send a marker
                            yield _make_event_sse("info", {"name": event_name, "message": "Node returned a Command, processed internally."})
                            
                elif event_type == "on_tool_error":
                    logger.warning(f"Tool error in node '{event_name}': {event_data.get('error')}")
                    yield _make_event_sse("error", {
                        "name": event_name,
                        "message": f"Error in tool: {event_data.get('error')}",
                        "thread_id": thread_id,
                    })

        except Exception as e:
            logger.exception(f"Error in workflow: {e}")
            yield _make_event_sse("error", {
                "message": f"Error in workflow: {str(e)}",
                "thread_id": thread_id,
            })

def _make_event_sse(event_type: str, data: dict) -> str:
    """Create SSE data for an event."""
    # Generate a random ID to help with deduplication on the client
    data["id"] = str(uuid4())
    
    # Add timestamp for debugging/tracking
    data["timestamp"] = time.time()
    
    # Sanitize any objects that can't be directly serialized
    data = _sanitize_message_objects(data)
    
    # Format as SSE
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

def _sanitize_message_objects(data: Any) -> Any:
    """Recursively sanitize objects that can't be directly JSON serialized."""
    if isinstance(data, dict):
        return {k: _sanitize_message_objects(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_message_objects(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    else:
        # For other types (like BaseMessage, Command, etc), convert to string
        return str(data)

async def _test_streaming():
    # Test code...
    pass

