#!/usr/bin/env python3
# Test script for interrupt display

import asyncio
import logging
import json
import os
import random
from src.workflow import run_agent_workflow_async

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("interrupt_display_test.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("interrupt_display_test")

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

# List of test inputs
TEST_INPUTS = [
    "calculator app",
    "todo list",
    "weather app",
    "chat application",
    "blog website"
]

async def main():
    # Use a random brief input to test the interactive mode
    user_input = random.choice(TEST_INPUTS)
    
    logger.info(f"Starting workflow with interactive mode enabled for input: {user_input}")
    logger.info(f"Configuration: {json.dumps(config, indent=2)}")
    
    try:
        # Mock the interrupt function to print the message and return a response
        from src.graph.nodes import interrupt as original_interrupt
        
        def mock_interrupt(message):
            logger.info(f"INTERRUPT CALLED WITH MESSAGE: {message}")
            print(f"\n\n=== INTERRUPT MESSAGE ===\n{message}\n=== END INTERRUPT MESSAGE ===\n")
            print("Please enter your response: ", end="")
            response = input()
            return response
        
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
