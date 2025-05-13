# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from fastapi import FastAPI

from .chat import register_chat_routes
from .tts import register_tts_routes
from .podcast import register_podcast_routes
from .ppt import register_ppt_routes
from .prose import register_prose_routes
from .mcp import register_mcp_routes

def register_all_routes(app: FastAPI):
    """Register all routes with the FastAPI app."""
    register_chat_routes(app)
    register_tts_routes(app)
    register_podcast_routes(app)
    register_ppt_routes(app)
    register_prose_routes(app)
    register_mcp_routes(app)
    
    return app

