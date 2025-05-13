# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import base64
import logging
from fastapi import FastAPI, HTTPException

from src.server.chat_request import TTSRequest
from src.tools import VolcengineTTS

logger = logging.getLogger(__name__)

def register_tts_routes(app: FastAPI):
    """Register text-to-speech routes with the FastAPI app."""
    
    @app.post("/api/tts")
    async def text_to_speech(request: TTSRequest):
        """Convert text to speech."""
        logger.info(f"Received TTS request: {request.text[:50]}...")
        
        # Validate the request
        if not request.text:
            raise HTTPException(status_code=400, detail="No text provided")
        
        try:
            # Initialize the TTS engine
            tts_engine = VolcengineTTS()
            
            # Convert text to speech
            audio_data = tts_engine.synthesize(
                text=request.text,
                voice=request.voice or "zh_female_qingxin",
                format=request.format or "mp3",
                sample_rate=request.sample_rate or 16000,
                volume=request.volume or 100,
                speed=request.speed or 100,
                pitch=request.pitch or 0
            )
            
            # Encode the audio data as base64
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            
            # Return the audio data
            return {
                "audio": audio_base64,
                "format": request.format or "mp3"
            }
            
        except Exception as e:
            logger.error(f"Error converting text to speech: {e}")
            raise HTTPException(status_code=500, detail=f"Error converting text to speech: {str(e)}")

