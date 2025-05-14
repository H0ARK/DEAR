# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.server.mcp_models import (
    MCPServerMetadataRequest,
    MCPServerMetadataResponse,
    MCPExecuteRequest,
    MCPExecuteResponse,
)

logger = logging.getLogger(__name__)

def register_mcp_routes(app: FastAPI):
    """Register MCP-related routes with the FastAPI app."""
    
    @app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
    async def mcp_server_metadata(request: MCPServerMetadataRequest):
        """Get information about an MCP server."""
        try:
            # Set default timeout with a longer value for this endpoint
            timeout = 300  # Default to 300 seconds for this endpoint

            # Use custom timeout from request if provided
            if request.timeout_seconds is not None:
                timeout = request.timeout_seconds
                
            # Create MCP client
            client = MultiServerMCPClient(
                server_url=request.server_url,
                api_key=request.api_key,
                timeout=timeout,
            )
            
            # Get server metadata
            metadata = client.get_server_metadata()
            
            # Return the metadata
            return MCPServerMetadataResponse(
                server_url=request.server_url,
                metadata=metadata,
            )
        except Exception as e:
            logger.exception(f"Error getting MCP server metadata: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/mcp/execute", response_model=MCPExecuteResponse)
    async def mcp_execute(request: MCPExecuteRequest):
        """Execute code on an MCP server."""
        try:
            # Set default timeout
            timeout = request.timeout_seconds or 60
            
            # Create MCP client
            client = MultiServerMCPClient(
                server_url=request.server_url,
                api_key=request.api_key,
                timeout=timeout,
            )
            
            # Execute the code
            result = client.execute(
                code=request.code,
                language=request.language,
                working_directory=request.working_directory,
                environment_variables=request.environment_variables,
            )
            
            # Return the result
            return MCPExecuteResponse(
                server_url=request.server_url,
                result=result,
            )
        except Exception as e:
            logger.exception(f"Error executing code on MCP server: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

