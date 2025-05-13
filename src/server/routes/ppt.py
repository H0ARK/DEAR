# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
from fastapi import FastAPI, HTTPException

from src.ppt.graph.builder import build_graph as build_ppt_graph
from src.server.chat_request import GeneratePPTRequest

logger = logging.getLogger(__name__)

def register_ppt_routes(app: FastAPI):
    """Register PowerPoint generation routes with the FastAPI app."""
    
    @app.post("/api/ppt/generate")
    async def generate_ppt(request: GeneratePPTRequest):
        """Generate a PowerPoint presentation."""
        logger.info(f"Received PPT generation request: {request}")
        
        # Validate the request
        if not request.topic:
            raise HTTPException(status_code=400, detail="No topic provided")
        
        try:
            # Build the PPT graph
            graph = build_ppt_graph()
            
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
                    "ppt_style": request.style or "professional",
                    "ppt_slides": request.slides or 10,
                    "ppt_theme": request.theme or "modern"
                },
                config
            )
            
            # Return the PPT content
            return {
                "content": result.get("ppt_content", "No content generated"),
                "title": result.get("ppt_title", "Untitled Presentation"),
                "outline": result.get("ppt_outline", "No outline available")
            }
            
        except Exception as e:
            logger.error(f"Error generating PPT: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating PPT: {str(e)}")

