# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Server script for running the DeerFlow API.
"""

import argparse
import logging

import uvicorn

# # Configure logging # Commented out basicConfig
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# )

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the DeerFlow API server")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (default: True except on Windows)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind the server to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    # Enhanced logging configuration
    # Get the numeric level from the string
    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {args.log_level}")

    # logging.basicConfig(
    #     level=numeric_level, # Set root logger level
    #     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    # )
    
    # Silence overly verbose libraries by setting their log level higher
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("httpcore").setLevel(logging.WARNING)
    # logging.getLogger("uvicorn.access").setLevel(logging.ERROR) 
    # Keep uvicorn.error at the general log level or INFO to see server startup/errors.
    # If you still see too much from uvicorn.error, you can set it to WARNING:
    # logging.getLogger("uvicorn.error").setLevel(logging.WARNING) 
    # logging.getLogger("watchfiles").setLevel(logging.ERROR) # Changed from WARNING to ERROR to silence "changes detected" warnings

    # If LangGraph itself is too chatty even with stream_mode="updates", you can try:
    # logging.getLogger("langgraph").setLevel(logging.WARNING)

    # Determine reload setting
    reload = False

    # Command line arguments override defaults
    if args.reload:
        reload = True

    logger.info("Starting DeerFlow API server")
    uvicorn.run(
        "src.server:app",
        host=args.host,
        port=args.port,
        reload=reload,
        log_level=args.log_level,
        reload_dirs=["src"],
        reload_excludes=[".venv/*", "*.pyc", "*~"]
    )
