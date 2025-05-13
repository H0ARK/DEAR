#!/usr/bin/env python3
# Debug script for workflow execution

import asyncio
import logging
import json
import os
from src.workflow import run_agent_workflow_async

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("workflow_debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("workflow_debug")

# Load configuration
config_path = "config/workflow_settings.json"
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        config = json.load(f)
else:
    logger.warning(f"Config file {config_path} not found. Using defaults.")
    config = {
        "auto_accepted_plan": False,
        "max_plan_iterations": 3,
        "max_step_num": 10,
        "enable_background_investigation": True,
        "force_interactive": True,
        "min_prd_iterations": 2
    }

async def main():
    user_input = "Create a simple calculator app with add, subtract, multiply, and divide functions"

    logger.info("Starting workflow with debug enabled")
    logger.info(f"Configuration: {json.dumps(config, indent=2)}")

    try:
        await run_agent_workflow_async(
            user_input=user_input,
            debug=True,
            max_plan_iterations=config["max_plan_iterations"],
            max_step_num=config["max_step_num"],
            enable_background_investigation=config["enable_background_investigation"],
            auto_accepted_plan=config["auto_accepted_plan"],
            force_interactive=config["force_interactive"]
        )
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
