# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
from fastapi import FastAPI, HTTPException

from src.podcast.graph.builder import build_graph as build_podcast_graph
from src.server.chat_request import GeneratePodcastRequest

logger = logging.getLogger(__name__)

def register_podcast_routes(app: FastAPI):
    """Register podcast generation routes with the FastAPI app."""
    
    @app.post("/api/podcast/generate")
    async def generate_podcast(request: GeneratePodcastRequest):
        """Generate a podcast script."""
        logger.info(f"Received podcast generation request: {request}")
        
        # Validate the request
        if not request.topic:
            raise HTTPException(status_code=400, detail="No topic provided")
        
        try:
            # Build the podcast graph
            graph = build_podcast_graph()
            
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
                    "podcast_format": request.format or "interview",
                    "podcast_duration": request.duration or "medium",
                    "podcast_tone": request.tone or "casual"
                },
                config
            )
            
            # Return the podcast script
            return {
                "script": result.get("podcast_script", "No script generated"),
                "title": result.get("podcast_title", "Untitled Podcast"),
                "summary": result.get("podcast_summary", "No summary available")
            }
            
        except Exception as e:
            logger.error(f"Error generating podcast: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating podcast: {str(e)}")

