# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import time
import random
from typing import List, Optional, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage

from src.graph import build_graph_with_memory
from src.server.chat_request import ChatMessage, ChatRequest, RepositoryInfo

logger = logging.getLogger(__name__)

def _make_event(event_type: str, data: dict):
    """Create an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

def register_chat_routes(app: FastAPI):
    """Register chat-related routes with the FastAPI app."""
    
    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest):
        """Stream chat responses."""
        logger.info(f"Received chat request: {request}")
        
        # Validate the request
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        # Convert the messages to the format expected by the graph
        messages = []
        for msg in request.messages:
            if msg.role == "user":
                messages.append({"type": "human", "content": msg.content})
            elif msg.role == "assistant":
                messages.append({"type": "ai", "content": msg.content})
            elif msg.role == "system":
                messages.append({"type": "system", "content": msg.content})
            elif msg.role == "tool":
                messages.append({"type": "tool", "content": msg.content, "tool_name": msg.name})
        
        # Build the graph
        graph = build_graph_with_memory()
        
        # Set up the config
        config = {
            "configurable": {
                "thread_id": request.thread_id or str(uuid4()),
                "locale": request.locale or "en-US",
                "enable_background_investigation": request.enable_background_investigation or False,
                "wait_for_input": True,
            }
        }
        
        # Add repository info if provided
        if request.repository_info:
            repo_info = request.repository_info
            config["configurable"]["repository_url"] = repo_info.url
            config["configurable"]["repository_branch"] = repo_info.branch
            config["configurable"]["repository_commit"] = repo_info.commit
        
        # Create the event generator
        async def event_generator():
            # Send the initial message
            yield _make_event("message", {"type": "start", "thread_id": config["configurable"]["thread_id"]})
            
            try:
                # Stream the response
                for chunk in graph.stream({"messages": messages}, config):
                    # Check if this is a final state update
                    if "__end__" in chunk:
                        yield _make_event("message", {"type": "end"})
                        break
                    
                    # Check if this is a message chunk
                    if "messages" in chunk:
                        messages_chunk = chunk["messages"]
                        if messages_chunk and isinstance(messages_chunk[-1], AIMessageChunk):
                            ai_message = messages_chunk[-1]
                            content = ai_message.content
                            
                            # Send the content chunk
                            yield _make_event("message", {
                                "type": "chunk",
                                "content": content,
                                "tool_calls": ai_message.tool_calls if hasattr(ai_message, "tool_calls") else None
                            })
                        
                        # Check if this is a tool message
                        elif messages_chunk and isinstance(messages_chunk[-1], ToolMessage):
                            tool_message = messages_chunk[-1]
                            
                            # Send the tool message
                            yield _make_event("message", {
                                "type": "tool",
                                "name": tool_message.name,
                                "content": tool_message.content
                            })
                    
                    # Add a small delay to avoid overwhelming the client
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Error streaming chat response: {e}")
                yield _make_event("error", {"message": str(e)})
                
        # Return the streaming response
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )

