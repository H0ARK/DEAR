# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from src.server.chat_request import GeneratePPTRequest
from src.graph import build_ppt_graph

logger = logging.getLogger(__name__)

def register_ppt_routes(app: FastAPI):
    """Register PowerPoint-related routes with the FastAPI app."""
    
    @app.post("/api/ppt/generate")
    async def generate_ppt(request: GeneratePPTRequest):
        try:
            report_content = request.content
            logger.info(f"Generating PowerPoint from content of length {len(report_content)}")
            
            workflow = build_ppt_graph()
            final_state = workflow.invoke({"input": report_content})
            generated_file_path = final_state["generated_file_path"]
            
            with open(generated_file_path, "rb") as f:
                ppt_bytes = f.read()
            
            # Clean up the temporary file
            try:
                os.remove(generated_file_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temporary file {generated_file_path}: {cleanup_error}")
            
            return Response(
                content=ppt_bytes,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                headers={"Content-Disposition": "attachment; filename=presentation.pptx"},
            )
        except Exception as e:
            logger.exception(f"Error occurred during PowerPoint generation: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

