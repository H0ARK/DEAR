# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import base64
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from src.server.chat_request import TTSRequest
from src.tools import VolcengineTTS

logger = logging.getLogger(__name__)

def register_tts_routes(app: FastAPI):
    """Register TTS-related routes with the FastAPI app."""
    
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
            
            tts = VolcengineTTS(app_id=app_id, access_token=access_token)
            audio_data = tts.synthesize(
                text=request.text,
                voice=request.voice,
                speed=request.speed,
                volume=request.volume,
                pitch=request.pitch,
            )
            
            if request.return_base64:
                # Return base64-encoded audio data
                base64_audio = base64.b64encode(audio_data).decode("utf-8")
                return {"audio_base64": base64_audio}
            else:
                # Return raw audio data
                return Response(
                    content=audio_data,
                    media_type="audio/mpeg",
                    headers={"Content-Disposition": "attachment; filename=speech.mp3"},
                )
        except Exception as e:
            logger.error(f"Error in TTS: {e}")
            raise HTTPException(status_code=500, detail=str(e))

