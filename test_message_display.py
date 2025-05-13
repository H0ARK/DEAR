#!/usr/bin/env python3
# Test script for message display

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
        logging.FileHandler("message_display_test.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("message_display_test")

# Load configuration
config_path = "config/interactive_mode.json"
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
    # Use a very brief input to test the interactive mode
    user_input = "calculator app"
    
    logger.info("Starting workflow with interactive mode enabled")
    logger.info(f"Configuration: {json.dumps(config, indent=2)}")
    
    try:
        # Mock the interrupt function to print the message
        from src.graph.nodes import interrupt as original_interrupt
        
        def mock_interrupt(message):
            logger.info(f"INTERRUPT CALLED WITH MESSAGE: {message}")
            return "This is a test response from the user"
        
        # Replace the interrupt function temporarily
        import src.graph.nodes
        src.graph.nodes.interrupt = mock_interrupt
        
        await run_agent_workflow_async(
            user_input=user_input,
            debug=True,
            max_plan_iterations=config["max_plan_iterations"],
            max_step_num=config["max_step_num"],
            enable_background_investigation=config["enable_background_investigation"],
            auto_accepted_plan=config["auto_accepted_plan"],
            force_interactive=config["force_interactive"]
        )
        
        # Restore the original interrupt function
        src.graph.nodes.interrupt = original_interrupt
        
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
