# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
from fastapi import FastAPI, HTTPException

from src.server.mcp_request import MCPServerMetadataRequest, MCPServerMetadataResponse
from src.server.mcp_utils import load_mcp_tools

logger = logging.getLogger(__name__)

def register_mcp_routes(app: FastAPI):
    """Register MCP server routes with the FastAPI app."""
    
    @app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
    async def mcp_server_metadata(request: MCPServerMetadataRequest):
        """Get MCP server metadata."""
        logger.info(f"Received MCP server metadata request: {request}")
        
        try:
            # Load the MCP tools
            tools = load_mcp_tools()
            
            # Return the metadata
            return MCPServerMetadataResponse(
                server_name="DeerFlow MCP Server",
                server_version="0.1.0",
                tools=tools
            )
            
        except Exception as e:
            logger.error(f"Error getting MCP server metadata: {e}")
            raise HTTPException(status_code=500, detail=f"Error getting MCP server metadata: {str(e)}")

