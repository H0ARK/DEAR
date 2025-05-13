# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

def check_repo_status(state: State) -> Dict[str, Any]:
    """Check the status of the repository."""
    logger.info("Checking repository status...")
    
    # Get the repository URL
    repo_url = state.get("repository_url")
    if not repo_url:
        logger.warning("No repository URL found in state.")
        return {"repo_status": "unknown", "repo_error": "No repository URL found."}
    
    # Check if the repository exists
    try:
        # Use the python_repl_tool to run git commands
        check_command = f"git ls-remote {repo_url}"
        result = python_repl_tool.invoke(check_command)
        
        if "fatal:" in result or "error:" in result.lower():
            logger.error(f"Error checking repository: {result}")
            return {"repo_status": "error", "repo_error": result}
        
        logger.info(f"Repository exists: {repo_url}")
        return {"repo_status": "exists", "repo_error": None}
        
    except Exception as e:
        logger.error(f"Error checking repository status: {e}")
        return {"repo_status": "error", "repo_error": str(e)}

