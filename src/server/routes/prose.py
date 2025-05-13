# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from src.server.chat_request import GenerateProseRequest
from src.graph import build_prose_graph

logger = logging.getLogger(__name__)

def register_prose_routes(app: FastAPI):
    """Register prose generation routes with the FastAPI app."""
    
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
            )
            
            async def event_generator():
                try:
                    async for event in events:
                        if "output" in event:
                            yield f"data: {json.dumps({'content': event['output']})}\n\n"
                except Exception as e:
                    logger.exception(f"Error in prose generation stream: {str(e)}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                finally:
                    yield "data: [DONE]\n\n"
            
            return StreamingResponse(event_generator(), media_type="text/event-stream")
        except Exception as e:
            logger.exception(f"Error occurred during prose generation: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

