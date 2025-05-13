# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
from fastapi import FastAPI, HTTPException

from src.prose.graph.builder import build_graph as build_prose_graph
from src.server.chat_request import GenerateProseRequest

logger = logging.getLogger(__name__)

def register_prose_routes(app: FastAPI):
    """Register prose generation routes with the FastAPI app."""
    
    @app.post("/api/prose/generate")
    async def generate_prose(request: GenerateProseRequest):
        """Generate prose content."""
        logger.info(f"Received prose generation request: {request}")
        
        # Validate the request
        if not request.topic:
            raise HTTPException(status_code=400, detail="No topic provided")
        
        try:
            # Build the prose graph
            graph = build_prose_graph()
            
            # Set up the config
            config = {
                "configurable": {
                    "locale": request.locale or "en-US",
                    "wait_for_input": False,
                    "simulated_input": True
                }
            }
            
            # Run the graph
            result = graph.invoke(
                {
                    "messages": [{"type": "human", "content": request.topic}],
                    "prose_style": request.style or "article",
                    "prose_tone": request.tone or "informative",
                    "prose_length": request.length or "medium"
                },
                config
            )
            
            # Return the prose content
            return {
                "content": result.get("prose_content", "No content generated"),
                "title": result.get("prose_title", "Untitled"),
                "summary": result.get("prose_summary", "No summary available")
            }
            
        except Exception as e:
            logger.error(f"Error generating prose: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating prose: {str(e)}")

