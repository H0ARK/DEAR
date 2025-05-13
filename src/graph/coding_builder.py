# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
import logging
from typing import Literal

# Import the shared State type
from .types import State

# Import the nodes specific to the coding flow
from .nodes import (
    initial_context_node,
    coding_coordinator_node,
    initiate_codegen_node,
    poll_codegen_status_node,
    prepare_codegen_task_node,
    codegen_success_node,
    codegen_failure_node,
    coding_planner_node,
    human_feedback_plan_node,
    coder_node,
    research_team_node,
    researcher_node,
)

# Import GitHub nodes
from .github_nodes import (
    github_manager_node,
    github_planning_node,
)

# Import context gathering node
from .context_nodes import context_gathering_node

logger = logging.getLogger(__name__)

# Placeholder node functions (replace with actual implementations)
def prepare_codegen_task_node(state: State) -> State:
    logger.warning("prepare_codegen_task_node is a placeholder.")
    # TODO: Implement logic to refine task description
    # For now, just pass state through
    return state

def codegen_success_node(state: State) -> State:
    logger.info(f"Codegen task succeeded. Final Result: {state.get('codegen_task_result')}")
    # TODO: Process success, maybe pass result to reporter
    return state

def codegen_failure_node(state: State) -> State:
    logger.error(f"Codegen task failed. Status: {state.get('codegen_task_status')}, Reason: {state.get('codegen_task_result')}")
    # TODO: Handle failure appropriately
    return state

# Conditional edge logic
MAX_POLL_ATTEMPTS = 10 # Example limit
MAX_TRANSIENT_ERROR_ATTEMPTS = 3 # Limit for retrying None/error statuses

def should_continue_polling(state: State) -> Literal["continue", "success", "failure", "error"]:
    """Determines the next step based on Codegen task status."""
    status = state.get("codegen_task_status")
    poll_attempts = state.get("codegen_poll_attempts", 0)

    logger.info(f"Checking poll status: '{status}', Attempts: {poll_attempts}")

    # Normalize status for case-insensitive comparison
    normalized_status = str(status).lower() if status is not None else "none"

    if normalized_status in ["pending", "running", "processing", "in_progress"]: # Add known in-progress statuses (lowercase)
        if poll_attempts < MAX_POLL_ATTEMPTS:
            return "continue"
        else:
            logger.warning(f"Max poll attempts ({MAX_POLL_ATTEMPTS}) reached for status '{status}'. Treating as failure.")
            return "failure" # Treat timeout as failure
    elif normalized_status == "completed" or normalized_status == "success": # Add known success statuses (lowercase)
        return "success"
    elif normalized_status.startswith("fail") or normalized_status.startswith("error"): # Catch variations of failure/error
        # Don't retry definitive failures reported by the service
        if status != "error_during_poll": # Assuming "error_during_poll" is *our* internal status
             logger.error(f"Codegen task reported definitive failure status: '{status}'. Routing to failure.")
             return "failure"
        # Fallthrough to handle potential transient 'error_during_poll'

    # Handle None status or our internal "error_during_poll"
    if normalized_status == "none" or status == "error_during_poll":
        if poll_attempts < MAX_TRANSIENT_ERROR_ATTEMPTS:
             logger.warning(f"Codegen status is '{status}', attempting retry {poll_attempts + 1}/{MAX_TRANSIENT_ERROR_ATTEMPTS} for transient issues.")
             return "continue"
        else:
             logger.error(f"Codegen status is '{status}' after {MAX_TRANSIENT_ERROR_ATTEMPTS} attempts. Routing to failure.")
             return "error" # Treat persistent None/internal error as error

    # Handle truly unexpected status values from codegen.com
    logger.error(f"Codegen polling received completely unexpected status: '{status}'. Routing to failure.")
    return "error"

def build_coding_graph():
    """Build and return the coding agent workflow graph with polling."""
    builder = StateGraph(State)

    # Add nodes
    builder.add_node("initial_context", initial_context_node)
    builder.add_node("coding_coordinator", coding_coordinator_node)
    builder.add_node("prepare_codegen_task", prepare_codegen_task_node)
    builder.add_node("initiate_codegen", initiate_codegen_node)
    builder.add_node("poll_codegen_status", poll_codegen_status_node)
    builder.add_node("codegen_success", codegen_success_node)
    builder.add_node("codegen_failure", codegen_failure_node)
    builder.add_node("context_gatherer", context_gathering_node)
    builder.add_node("coding_planner", coding_planner_node)
    builder.add_node("human_feedback_plan", human_feedback_plan_node)
    builder.add_node("coder", coder_node)
    builder.add_node("research_team", research_team_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("github_manager", github_manager_node)
    builder.add_node("github_planning", github_planning_node)

    # --- Define a new simple routing node ---
    def route_after_plan_acceptance_node(state: State) -> Command[Literal["github_planning", "coder"]]:
        logger.info("Routing after plan acceptance...")
        if state.get("feature_branch_name"):
            logger.info("Feature branch planned, routing to github_planning.")
            return Command(goto="github_planning")
        else:
            logger.info("No feature branch planned, routing to coder.")
            return Command(goto="coder")
    builder.add_node("route_after_plan_acceptance", route_after_plan_acceptance_node)
    # --- End new routing node ---

    # Define edges
    builder.add_edge(START, "initial_context")
    builder.add_edge("initial_context", "coding_coordinator")

    builder.add_conditional_edges(
        "coding_coordinator",
        lambda state: state.get("goto", "__end__"),
        {
            "prepare_codegen_task": "prepare_codegen_task",
            "context_gatherer": "context_gatherer",
            "coder": "coder",
            "coding_coordinator": "coding_coordinator",
            "__end__": END
        }
    )
    builder.add_edge("context_gatherer", "coding_planner")
    builder.add_edge("prepare_codegen_task", "initiate_codegen")
    builder.add_edge("initiate_codegen", "poll_codegen_status")
    builder.add_conditional_edges(
        "poll_codegen_status",
        should_continue_polling,
        {
            "continue": "poll_codegen_status",
            "success": "codegen_success",
            "failure": "codegen_failure",
            "error": "codegen_failure",
        },
    )
    builder.add_edge("codegen_success", END)
    builder.add_edge("codegen_failure", END)

    # --- Plan Feedback Loop ---
    builder.add_edge("coding_planner", "human_feedback_plan")

    def should_revise_plan(state: State) -> Literal["revise", "accept"]:
        feedback = state.get("interrupt_feedback") # Primary source of feedback
        if feedback is None and state.get("messages"):
             feedback_candidate = state["messages"][-1]
             if hasattr(feedback_candidate, 'name') and feedback_candidate.name == 'user_feedback':
                 feedback = feedback_candidate.content
             elif hasattr(feedback_candidate, 'type') and feedback_candidate.type == 'human': # LlamaParse HumanMessage
                 feedback = feedback_candidate.content

        feedback_str = str(feedback).strip().upper()
        logger.info(f"Plan feedback processing: '{feedback_str}'")
        if feedback_str.startswith("ACCEPT") or feedback_str.startswith("YES"):
            return "accept"
        # Any other structured feedback like NO, EDIT, REVISE, or even just free text implies revision
        return "revise"

    builder.add_conditional_edges(
        "human_feedback_plan",
        should_revise_plan,
        {
            "revise": "coding_planner",
            "accept": "route_after_plan_acceptance" # Route to the new decision node
        }
    )
    # Edges from the new decision node
    builder.add_conditional_edges(
        "route_after_plan_acceptance",
        lambda state: "github_planning" if state.get("feature_branch_name") else "coder",
        {
            "github_planning": "github_planning",
            "coder": "coder"
        }
    )
    # --- End Plan Feedback Loop ---

    builder.add_conditional_edges(
        "github_planning",
        lambda x: x.get("goto", "github_manager"),
        {
            "github_manager": "github_manager",
            "coder": "coder",
            "__end__": END
        }
    )
    builder.add_conditional_edges(
        "github_manager",
        lambda x: x.get("goto", "coder"),
        {
            "coding_planner": "coding_planner",
            "coder": "coder",
            "__end__": END
        }
    )
    builder.add_edge("coder", END)
    builder.add_edge("researcher", "research_team")
    builder.add_conditional_edges(
        "research_team",
        lambda x: x.get("goto", "coding_planner"),
        {
            "researcher": "researcher",
            "coder": "coder",
            "coding_planner": "coding_planner"
        }
    )

    memory = MemorySaver()
    # Ensure human_feedback_plan_node is in interrupt_before
    graph = builder.compile(checkpointer=memory, interrupt_before=["human_feedback_plan"])
    return graph


# Create the graph instance
coding_graph = build_coding_graph()
