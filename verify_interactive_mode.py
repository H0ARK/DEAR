#!/usr/bin/env python3
# Verification script for interactive mode

import asyncio
import logging
import json
import os
import random
import time
from src.workflow import run_agent_workflow_async
from langgraph.types import InterruptValue

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("interactive_mode_verification.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("interactive_mode_verification")

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

# Test input
TEST_INPUT = "calculator app"

async def main():
    logger.info(f"Starting verification with input: {TEST_INPUT}")
    logger.info(f"Configuration: {json.dumps(config, indent=2)}")
    
    try:
        # Mock the interrupt function to print the message and return a response
        from src.graph.nodes import interrupt as original_interrupt
        
        def mock_interrupt(interrupt_value):
            if isinstance(interrupt_value, InterruptValue):
                message = interrupt_value.value
                node_id = interrupt_value.ns[0] if interrupt_value.ns else "unknown"
                logger.info(f"INTERRUPT CALLED FROM NODE: {node_id}")
                logger.info(f"INTERRUPT MESSAGE: {message}")
            else:
                message = str(interrupt_value)
                logger.info(f"INTERRUPT CALLED WITH SIMPLE MESSAGE: {message}")
            
            print(f"\n\n=== INTERRUPT FROM {node_id if 'node_id' in locals() else 'unknown'} ===")
            print(f"{message}")
            print("=== END INTERRUPT MESSAGE ===\n")
            print("Please enter your response: ", end="")
            response = input()
            return response
        
        # Replace the interrupt function temporarily
        import src.graph.nodes
        src.graph.nodes.interrupt = mock_interrupt
        
        # Run the workflow
        await run_agent_workflow_async(
            user_input=TEST_INPUT,
            debug=True,
            max_plan_iterations=config["max_plan_iterations"],
            max_step_num=config["max_step_num"],
            enable_background_investigation=config["enable_background_investigation"],
            auto_accepted_plan=config["auto_accepted_plan"],
            force_interactive=config["force_interactive"]
        )
        
        # Restore the original interrupt function
        src.graph.nodes.interrupt = original_interrupt
        
        logger.info("Verification completed successfully")
        
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
