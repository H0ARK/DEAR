# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class MCPServerMetadataRequest(BaseModel):
    server_url: str = Field(..., description="The URL of the MCP server.")
    api_key: Optional[str] = Field(None, description="Optional API key for the MCP server.")
    timeout_seconds: Optional[int] = Field(None, description="Optional timeout in seconds for the request.")

class MCPServerMetadataResponse(BaseModel):
    server_url: str = Field(..., description="The URL of the MCP server.")
    metadata: Dict[str, Any] = Field(..., description="The metadata returned by the MCP server.")
    tools: List = Field(..., description="The tools available on the MCP server.")

class MCPExecuteRequest(BaseModel):
    server_url: str = Field(..., description="The URL of the MCP server.")
    api_key: Optional[str] = Field(None, description="Optional API key for the MCP server.")
    timeout_seconds: Optional[int] = Field(60, description="Optional timeout in seconds for the execution.")
    code: str = Field(..., description="The code to execute on the MCP server.")
    language: str = Field(..., description="The language of the code.")
    working_directory: Optional[str] = Field(None, description="Optional working directory for execution.")
    environment_variables: Optional[Dict[str, str]] = Field(None, description="Optional environment variables for execution.")

class MCPExecuteResponse(BaseModel):
    server_url: str = Field(..., description="The URL of the MCP server.")
    result: Any = Field(..., description="The result of the code execution from the MCP server.") 