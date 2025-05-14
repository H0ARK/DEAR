# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import logging
# from src.graph import build_graph # Keep this if run_agent_workflow_async uses it
from langgraph.checkpoint.memory import MemorySaver # No longer needed here for the LangServe graph
# from src.graph.coding_builder import build_coding_graph_with_memory # Switching to build_coding_graph
from src.graph.coding_builder import build_coding_graph # Import the correct builder

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default level is INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def enable_debug_logging():
    """Enable debug level logging for more detailed execution information."""
    logging.getLogger("src").setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)

# The LangGraph API / LangServe platform handles persistence automatically.
# We should not provide a custom checkpointer when defining the 'graph' for LangServe.
# checkpointer = MemorySaver() # REMOVED

# Instantiate the graph using the builder function that does NOT pass a checkpointer.
# This graph instance will be picked up by LangServe.
graph = build_coding_graph() # CHANGED: Use the builder that compiles with checkpointer=None

# If you have other configurations or helper functions LangServe might need,
# they can be exposed here as well. For now, exposing 'graph' is key.

# You might also want to add a way for LangServe to pick up
# any necessary configuration for your graph if it's not handled
# entirely by the checkpointer or default values.
# For example, if specific API keys are needed at graph construction time
# and are not passed via RunnableConfig during invocation.

# Example of how you might add other things if needed:
# from some_config_module import app_config
# from some_tool_module import some_tool

# For LangServe to work with `langchain app up --path src/workflow.py`
# it primarily needs the `graph` variable.


async def run_agent_workflow_async(
    user_input: str,
    debug: bool = False,
    max_plan_iterations: int = 1,
    max_step_num: int = 3,
    enable_background_investigation: bool = True,
    auto_accepted_plan: bool = False,
    force_interactive: bool = True,
):
    """Run the agent workflow asynchronously with the given user input.

    Args:
        user_input: The user's query or request
        debug: If True, enables debug level logging
        max_plan_iterations: Maximum number of plan iterations
        max_step_num: Maximum number of steps in a plan
        enable_background_investigation: If True, performs web search before planning to enhance context
        auto_accepted_plan: If True, automatically accepts plans without waiting for user feedback
        force_interactive: If True, forces interactive mode for brief inputs

    Returns:
        The final state after the workflow completes
    """
    if not user_input:
        raise ValueError("Input could not be empty")

    if debug:
        enable_debug_logging()
        
    # Create a fresh graph instance for this run - this part is for the async runner,
    # not for the LangServe 'graph' instance.
    # It seems run_agent_workflow_async might need its own way to handle memory if desired,
    # or also use a globally defined checkpointer (but not the langserve one).
    # For now, ensure it uses the correct `build_graph` from `src.graph` which resolves to coding_builder.
    from src.graph import build_graph as build_graph_for_runner # Alias to avoid confusion
    runner_graph = build_graph_for_runner()
    
    # Print the graph's Mermaid diagram for debugging
    if debug:
        print("\n=== RUNNER GRAPH STRUCTURE (MERMAID) ===")
        print(runner_graph.get_graph(xray=True).draw_mermaid())
        print("=== END RUNNER GRAPH STRUCTURE ===\n")

    logger.info(f"Starting async workflow with user input: {user_input}")
    logger.info(f"Auto-accepted plan: {auto_accepted_plan}")
    logger.info(f"Force interactive mode: {force_interactive}")
    initial_state = {
        # Runtime Variables
        "messages": [{"role": "user", "content": user_input}],
        "auto_accepted_plan": auto_accepted_plan,
        "enable_background_investigation": enable_background_investigation,
        "force_interactive": force_interactive,
        "prd_iterations": 0,
    }
    # Config for the runner_graph - this thread_id will be independent of LangServe's
    config = {
        "configurable": {
            "thread_id": "runner_default_thread", # Separate thread_id for this runner
            "max_plan_iterations": max_plan_iterations,
            "max_step_num": max_step_num,
            "force_interactive": force_interactive,
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
    last_message_cnt = 0
    async for s in runner_graph.astream(
        input=initial_state, config=config, stream_mode="values"
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

    logger.info("Async workflow completed successfully")


if __name__ == "__main__":
    # Import after removing global graph instance
    from src.graph.coding_builder import visualize_coding_graph
    
    # Create a graph just for visualization (uses build_coding_graph which is checkpointer=None)
    # viz_graph = build_graph() # build_graph here refers to the one re-exported in src.graph.__init__
    from src.graph.coding_builder import build_coding_graph as build_viz_graph # Use explicit import
    viz_graph = build_viz_graph()

    # Visualize and print Mermaid diagram
    visualize_coding_graph(viz_graph)
    print(viz_graph.get_graph(xray=True).draw_mermaid())
