#!/usr/bin/env python3
# Script to run the simplified 4-agent system workflow

import logging
import sys
from langchain_core.messages import HumanMessage
from src.graph.simplified_builder import build_simplified_graph, build_interactive_simplified_graph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Check if interactive mode is requested
    interactive = "--interactive" in sys.argv
    
    logger.info(f"Building the simplified 4-agent system graph (interactive: {interactive})...")
    
    if interactive:
        graph = build_interactive_simplified_graph()
        logger.info("Running in interactive mode with checkpointing enabled.")
    else:
        graph = build_simplified_graph()
        logger.info("Running in non-interactive mode.")
    
    # Initialize state with a user message
    initial_message = "Create a simple web application that allows users to track their daily tasks."
    if len(sys.argv) > 1 and sys.argv[1] != "--interactive":
        initial_message = sys.argv[1]
    
    logger.info(f"Initial message: {initial_message}")
    
    # Initialize state
    state = {
        "messages": [HumanMessage(content=initial_message)],
        "simulated_input": not interactive,  # Set to True for non-interactive mode
    }
    
    # Run the graph
    try:
        logger.info("Starting the workflow...")
        result = graph.invoke(state)
        
        # Print the final messages
        logger.info("Workflow completed. Final messages:")
        for message in result.get("messages", []):
            print(f"{message.name}: {message.content[:100]}...")
        
    except Exception as e:
        logger.error(f"Error running the workflow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

