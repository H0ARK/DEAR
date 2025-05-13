# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from src.server.chat_request import GeneratePodcastRequest
from src.graph import build_podcast_graph

logger = logging.getLogger(__name__)

def register_podcast_routes(app: FastAPI):
    """Register podcast-related routes with the FastAPI app."""
    
    @app.post("/api/podcast/generate")
    async def generate_podcast(request: GeneratePodcastRequest):
        try:
            report_content = request.content
            logger.info(f"Generating podcast from content of length {len(report_content)}")
            
            workflow = build_podcast_graph()
            final_state = workflow.invoke({"input": report_content})
            audio_bytes = final_state["output"]
            
            return Response(content=audio_bytes, media_type="audio/mp3")
        except Exception as e:
            logger.exception(f"Error occurred during podcast generation: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

