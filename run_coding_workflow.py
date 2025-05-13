#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import logging
from src.graph.coding_builder import build_coding_graph, visualize_coding_graph
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

async def run_coding_workflow_async(
    user_input: str,
    debug: bool = False,
    max_plan_iterations: int = 1,
    max_step_num: int = 3,
    enable_background_investigation: bool = True,
    wait_for_input: bool = True,
):
    """Run the coding workflow asynchronously with the given user input.

    Args:
        user_input: The user's query or request
        debug: If True, enables debug level logging
        max_plan_iterations: Maximum number of plan iterations
        max_step_num: Maximum number of steps in a plan
        enable_background_investigation: If True, performs web search before planning to enhance context
        wait_for_input: If True, wait for user input at interruption points

    Returns:
        The final state after the workflow completes
    """
    if not user_input:
        raise ValueError("Input could not be empty")

    if debug:
        logging.getLogger("src").setLevel(logging.DEBUG)

    # Create a fresh graph instance for this run
    coding_graph = build_coding_graph()

    # Print the graph structure in debug mode
    if debug:
        print("\n=== CODING GRAPH STRUCTURE (MERMAID) ===")
        print(coding_graph.get_graph(xray=True).draw_mermaid())
        print("=== END CODING GRAPH STRUCTURE ===\n")

    logger.info(f"Starting coding workflow with user input: {user_input}")
    initial_state = {
        # Runtime Variables
        "messages": [{"role": "user", "content": user_input}],
        "auto_accepted_plan": not wait_for_input,  # For non-interactive running
        "enable_background_investigation": enable_background_investigation,
        "current_workflow": "coding",  # Set the workflow type to coding
        "wait_for_input": wait_for_input,  # Add this to state
    }
    config = {
        "configurable": {
            "thread_id": "default",
            "max_plan_iterations": max_plan_iterations,
            "max_step_num": max_step_num,
            "mcp_settings": {
                "servers": {
                    "mcp-github-trending": {
                        "transport": "stdio",
                        "command": "uvx",
                        "args": ["mcp-github-trending"],
                        "enabled_tools": ["get_github_trending_repositories"],
                        "add_to_agents": ["researcher"],
                    }
                }
            },
        },
        "recursion_limit": 100,
    }

    # Set up stream mode based on whether we want interruptions
    stream_mode = "interrupt" if wait_for_input else "values"
    last_message_cnt = 0

    # Define an on_interrupt handler for interrupts
    async def on_interrupt(position, interrupt_value, state):
        """Handle interrupts from the graph."""
        if position[0] == "human_initial_context_review":
            print(f"\n=== INTERRUPT: Initial Context Review ===")
            print(interrupt_value.value)
            user_input = input("\nYour feedback: ")
            return user_input
        elif position[0] == "human_prd_review":
            print(f"\n=== INTERRUPT: PRD Review ===")
            print(interrupt_value.value)
            user_input = input("\nYour feedback: ")
            return user_input
        elif position[0] == "human_feedback_plan":
            print(f"\n=== INTERRUPT: Plan Review ===")
            print(interrupt_value.value)
            user_input = input("\nYour feedback (accept or revise): ")
            return user_input
        else:
            print(f"\n=== UNEXPECTED INTERRUPT AT {position} ===")
            print(interrupt_value.value)
            return "continue"

    # Get the list of interrupt nodes directly from the graph configuration
    async for s in coding_graph.astream(
        input=initial_state,
        config=config,
        stream_mode=stream_mode,
        # on_interrupt parameter removed as it's not supported in LangGraph 0.3.5
    ):
        try:
            if isinstance(s, dict) and "messages" in s:
                if len(s["messages"]) <= last_message_cnt:
                    continue
                last_message_cnt = len(s["messages"])
                message = s["messages"][-1]
                if isinstance(message, tuple):
                    print(message)
                else:
                    message.pretty_print()
            else:
                # For any other output format
                print(f"Output: {s}")
        except Exception as e:
            logger.error(f"Error processing stream output: {e}")
            print(f"Error processing output: {str(e)}")

    logger.info("Coding workflow completed successfully")

if __name__ == "__main__":
    import sys

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Run the coding workflow")
    parser.add_argument("input", nargs="*", help="User input query")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--visualize", action="store_true", help="Generate graph visualization")
    parser.add_argument("--wait", action="store_true", help="Wait for user input at interruption points")
    parser.add_argument("--max-plan", type=int, default=1, help="Maximum number of plan iterations")
    parser.add_argument("--max-steps", type=int, default=3, help="Maximum number of steps in a plan")

    args = parser.parse_args()

    # Get user input from arguments or use default
    if args.input:
        user_input = " ".join(args.input)
    else:
        user_input = "Build a 2D Diablo-like game using Pygame"

    # Optionally visualize the graph
    if args.visualize:
        visualize_coding_graph()
        print("Graph visualization completed. See coding_graph_visualization.png")

    # Run the workflow with provided arguments
    asyncio.run(run_coding_workflow_async(
        user_input=user_input,
        debug=args.debug,
        max_plan_iterations=args.max_plan,
        max_step_num=args.max_steps,
        wait_for_input=args.wait
    ))
