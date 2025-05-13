# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
import logging
from typing import Literal

# Import the shared State type
from .types import State # Assume State will be expanded to include prd_document, prd_status, etc.

# Import the StepType enum and Plan classes
from src.prompts.planner_model import StepType, Plan, Step

# Import the nodes specific to the coding flow
from .nodes import (
    initial_context_node,
    coding_coordinator_node, # Will need internal logic for PRD iteration
    initiate_codegen_node,
    poll_codegen_status_node,
    task_orchestrator_node, # NEW - repurposed from prepare_codegen_task
    codegen_success_node,
    codegen_failure_node,
    coding_planner_node,
    human_feedback_plan_node, # This is for TASK PLAN review
    # coder_node, # Temporarily disconnected
    research_team_node,
    researcher_node,
    human_prd_review_node, # NEW node for PRD review
    linear_integration_node, # NEWLY ADDED
    human_initial_context_review_node, # Legacy node for initial context review
    # New specialized nodes for initial context review
    initial_context_query_generator_node,
    initial_context_wait_for_feedback_node,
    initial_context_feedback_handler_node,
    initial_context_approval_router_node,
)

# Import GitHub nodes
from .github_nodes import (
    github_manager_node,
    # github_planning_node, # Already removed
)

# Import context gathering node
from .context_nodes import context_gathering_node

# Import the new utility
from .visualizer import save_graph_visualization, get_graph_mermaid_syntax

logger = logging.getLogger(__name__)

# --- Define edge routing functions ---

def route_after_initial_context_review(state: State) -> Literal["coding_coordinator", "human_initial_context_review"]:
    if state.get("initial_context_approved"):
        logger.info("Initial context approved. Proceeding to coding_coordinator.")
        return "coding_coordinator"
    else:
        # This implies awaiting_initial_context_input is true and a query has been set by the node.
        logger.info("Initial context not yet approved or awaiting further input. Looping back to human_initial_context_review.")
        return "human_initial_context_review"

# NEW conditional routing function for research_team
def route_from_research_team(state: State) -> Literal["researcher", "task_orchestrator", "coding_coordinator", "coding_planner"]:
    """Determines the next step after the research_team node has processed a task or PRD research."""

    # FIRST PRIORITY: Check if we should return to a specific node based on the flag from context_gatherer
    return_to_node = state.get("research_return_to")
    if return_to_node in ["coding_coordinator", "coding_planner"]:
        logger.info(f"route_from_research_team: Explicit return path to {return_to_node} specified")
        # Clear the flag to prevent loops
        if "research_return_to" in state:
            del state["research_return_to"]
        return return_to_node

    # SECOND PRIORITY: If there's a current active step that needs execution, process it
    current_plan = state.get("current_plan")
    if current_plan and hasattr(current_plan, 'steps') and current_plan.steps:
        # Check if there's an unexecuted step
        for step in current_plan.steps:
            if not step.execution_res:  # Found an unexecuted step
                if step.step_type == StepType.RESEARCH:
                    logger.info(f"route_from_research_team: Active step is RESEARCH, routing to researcher")
                    return "researcher"
                elif step.step_type == StepType.PROCESSING:
                    logger.info(f"route_from_research_team: Active step is PROCESSING, routing to task_orchestrator")
                    return "task_orchestrator"
                break  # Only handle the first unexecuted step

    # THIRD PRIORITY (default): If no other condition applies, always return to coding_coordinator
    # This simplifies the graph and ensures we don't have multiple possible destinations
    logger.info("route_from_research_team: No active research or specific return path, defaulting to coding_coordinator")
    return "coding_coordinator"

# Placeholder for PRD review logic (similar to above but for PRD)
# The human_prd_review_node will set 'prd_review_feedback' in state.
# coding_coordinator_node will use 'prd_review_feedback'
def route_after_prd_review(state: State) -> Literal["request_research", "iterate_prd", "prd_approved_to_planner"]:
    # This logic is effectively part of coding_coordinator_node's decision making
    # For now, the connections will be:
    # human_prd_review_node -> coding_coordinator
    # coding_coordinator then decides where to go next based on state.
    # This function itself isn't directly used for a conditional_edge from human_prd_review_node itself,
    # but coding_coordinator_node will implement this routing.
    feedback = state.get("prd_review_feedback", "").lower() # human_prd_review_node sets this
    if "research" in feedback:
        return "request_research"
    if "approved" in feedback or "approve" in feedback : # Simplified approval
        return "prd_approved_to_planner"
    return "iterate_prd" # Default to iterating on PRD with new feedback

# For task plan revision routing
def should_revise_task_plan(state: State) -> Literal["revise", "accept"]:
    feedback = state.get("task_plan_feedback", "").lower()
    if "revise" in feedback or "change" in feedback or "modify" in feedback:
        return "revise"
    return "accept" # Default to accepting

# For codegen status polling routing
MAX_TRANSIENT_ERROR_ATTEMPTS = 3  # Allow a few retries for transient errors
def should_continue_polling(state: State) -> Literal["continue", "success", "failure", "error"]:
    status = state.get("codegen_task_status", "none").lower()
    poll_attempts = state.get("codegen_poll_attempts", 0)

    if status == "pending" or status == "running":
        return "continue"
    elif status == "success":
        return "success"
    elif status == "failure_coding" or status == "failure_review" or status == "timeout":
        return "failure"
    elif status == "none" or status == "error_during_poll":
        if poll_attempts < MAX_TRANSIENT_ERROR_ATTEMPTS: return "continue"
        else: return "error"
    return "error"


def build_coding_graph_base(checkpointer=None, use_interrupts=True): # Renamed to base, memory passed in
    builder = StateGraph(State)

    # Add nodes
    builder.add_node("initial_context", initial_context_node)

    # Legacy node (kept for backward compatibility)
    builder.add_node("human_initial_context_review", human_initial_context_review_node)

    # New specialized nodes for initial context review
    builder.add_node("initial_context_query_generator", initial_context_query_generator_node)
    builder.add_node("initial_context_wait_for_feedback", initial_context_wait_for_feedback_node)
    builder.add_node("initial_context_feedback_handler", initial_context_feedback_handler_node)
    builder.add_node("initial_context_approval_router", initial_context_approval_router_node)

    builder.add_node("coding_coordinator", coding_coordinator_node) # Central for PRD
    builder.add_node("human_prd_review", human_prd_review_node) # NEW for PRD feedback
    builder.add_node("context_gatherer", context_gathering_node) # For research
    builder.add_node("research_team", research_team_node) # For research
    builder.add_node("researcher", researcher_node) # ADDED

    builder.add_node("coding_planner", coding_planner_node) # Takes approved PRD
    builder.add_node("human_feedback_plan", human_feedback_plan_node) # For TASK PLAN review
    builder.add_node("linear_integration", linear_integration_node) # NEWLY ADDED

    builder.add_node("task_orchestrator", task_orchestrator_node) # Renamed from prepare_codegen_task
    builder.add_node("initiate_codegen", initiate_codegen_node)
    builder.add_node("poll_codegen_status", poll_codegen_status_node)
    builder.add_node("codegen_success", codegen_success_node)
    builder.add_node("codegen_failure", codegen_failure_node)

    builder.add_node("github_manager", github_manager_node)
    # builder.add_node("coder", coder_node) # Temporarily disconnected

    # --- Define Simplified Edges ---
    # START FLOW: Initial context gathering → specialized nodes for review → coordinator
    builder.add_edge(START, "initial_context")

    # Connect initial_context to the new specialized flow
    builder.add_edge("initial_context", "initial_context_query_generator")

    # Connect the specialized nodes in sequence
    builder.add_edge("initial_context_query_generator", "initial_context_wait_for_feedback")
    builder.add_edge("initial_context_wait_for_feedback", "initial_context_feedback_handler")
    builder.add_edge("initial_context_feedback_handler", "initial_context_approval_router")

    # Conditional routing from the approval router
    builder.add_conditional_edges(
        "initial_context_approval_router",
        lambda state: "coding_coordinator" if state.get("initial_context_approved") else "initial_context_query_generator",
        {
            "coding_coordinator": "coding_coordinator",
            "initial_context_query_generator": "initial_context_query_generator", # Loop back for more iterations
        }
    )

    # Keep the legacy node connected but route to the new flow
    builder.add_edge("human_initial_context_review", "initial_context_query_generator")

    # PRD BUILDING LOOP: Coordinator manages the PRD loop
    def route_from_coordinator(state: State) -> Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]:
        # This function will read state set by coding_coordinator_node

        # Add detailed logging
        logger.info("route_from_coordinator: Determining next node...")
        logger.info(f"route_from_coordinator: simulated_input={state.get('simulated_input', False)}")
        logger.info(f"route_from_coordinator: wait_for_input={state.get('wait_for_input', True)}")
        logger.info(f"route_from_coordinator: prd_document exists={bool(state.get('prd_document', ''))}")
        logger.info(f"route_from_coordinator: prd_status={state.get('prd_status', 'None')}")
        logger.info(f"route_from_coordinator: prd_approved={state.get('prd_approved', False)}")
        logger.info(f"route_from_coordinator: prd_next_step={state.get('prd_next_step', 'None')}")
        logger.info(f"route_from_coordinator: prd_review_feedback={state.get('prd_review_feedback', 'None')}")

        # Direct bypass in non-interactive mode
        if state.get("simulated_input", False):
            # Check if we have a PRD document and approved status
            if state.get("prd_document") and state.get("prd_status") == "approved":
                logger.info("Simulated input mode: PRD already approved, proceeding to coding planner.")
                return "coding_planner"
            # If we have a PRD document but not explicit approval yet
            elif state.get("prd_document"):
                logger.info("Simulated input mode: PRD exists but needs review approval.")
                return "human_prd_review"
            # In non-interactive mode with no PRD, the coding_coordinator should have created one
            # If we reach here, something might have gone wrong but we try to proceed
            else:
                logger.info("Simulated input mode: No PRD document yet, routing to human_prd_review to generate one.")
                return "human_prd_review"

        # Check if coordinator specifically set the prd_next_step
        next_step = state.get("prd_next_step")
        if next_step:
            logger.info(f"Using explicit prd_next_step: {next_step}")
            return next_step

        # Check for approval flag or feedback that indicates approval
        if state.get("prd_approved") or state.get("prd_status") == "approved":
            logger.info("PRD is approved, routing to coding planner.")
            return "coding_planner"

        # Check for approval in feedback
        prd_review_feedback = state.get("prd_review_feedback", "").lower()
        if "approve" in prd_review_feedback or "accept" in prd_review_feedback or "good" in prd_review_feedback:
            logger.info("PRD approval detected in feedback, routing to coding planner.")
            return "coding_planner"

        # If we have a PRD document but no specific next step or approval
        if state.get("prd_document") and state.get("prd_status") == "awaiting_review":
            logger.info("PRD document exists and awaiting review, routing to human_prd_review.")
            return "human_prd_review"

        # If we have no PRD document yet
        if not state.get("prd_document"):
            # The coordinator should have created one, but if not for some reason...
            logger.info("No PRD document yet, letting coordinator try again.")
            return "human_prd_review"

        # Default to ending if we hit an unexpected state
        logger.info("No clear routing decision could be made, defaulting to __end__")
        return "__end__"

    builder.add_conditional_edges(
        "coding_coordinator",
        route_from_coordinator, # Decision made by coordinator node's logic reflected in state
        {
            "human_prd_review": "human_prd_review",   # For PRD feedback
            "context_gatherer": "context_gatherer",   # For research
            "coding_planner": "coding_planner",       # Exit PRD loop to planning
            "__end__": END                            # Fallback
        }
    )

    # FEEDBACK LOOP: PRD feedback always goes back to coordinator
    builder.add_edge("human_prd_review", "coding_coordinator")

    # RESEARCH FLOW: One-way path through the research process
    builder.add_edge("context_gatherer", "research_team")  # Context gatherer always goes to research team

    # Research team can go to researcher for more research, or back to coordinator with results
    builder.add_conditional_edges(
        "research_team",
        route_from_research_team,  # Use our simplified routing function
        {
            "researcher": "researcher",               # For performing research
            "coding_coordinator": "coding_coordinator", # Return research to coordinator
            "coding_planner": "coding_planner",       # For direct return to planner
            "task_orchestrator": "task_orchestrator"  # For direct task execution based on research
        }
    )

    # Researcher always goes back to research team to evaluate results and decide next step
    builder.add_edge("researcher", "research_team")

    # PLANNING FLOW
    builder.add_edge("coding_planner", "human_feedback_plan")
    builder.add_conditional_edges(
        "human_feedback_plan",
        should_revise_task_plan,
        {
            "revise": "coding_planner",
            "accept": "linear_integration"
        }
    )
    builder.add_edge("linear_integration", "task_orchestrator")

    # TASK ORCHESTRATION AND CODEGEN LOOP
    def route_from_orchestrator(state: State) -> Literal["initiate_codegen", "coding_planner", "__end__"]:
        # This logic will be implemented in task_orchestrator_node Python function.
        # It will check the task queue, dependencies, and outcomes.
        # It sets a 'orchestrator_next_step' in state.
        orchestrator_decision = state.get("orchestrator_next_step", "__end__") # Default to end if no decision
        if orchestrator_decision == "dispatch_task_for_codegen":
            return "initiate_codegen"
        elif orchestrator_decision == "forward_failure_to_planner":
            return "coding_planner"
        elif orchestrator_decision == "all_tasks_complete":
            return "__end__"
        return "__end__" # Fallback

    builder.add_conditional_edges(
        "task_orchestrator",
        route_from_orchestrator,
        {
            "initiate_codegen": "initiate_codegen",     # Orchestrator dispatches a task
            "coding_planner": "coding_planner",         # Send failures back to planner
            "__end__": END                              # All tasks done
        }
    )

    # CODEGEN FLOW
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

    # Codegen outcomes feed back to the orchestrator
    builder.add_edge("codegen_failure", "task_orchestrator")
    builder.add_edge("codegen_success", "github_manager")

    # GitHub manager feeds back to orchestrator on successful merge/completion of a task
    builder.add_edge("github_manager", "task_orchestrator")

    if use_interrupts and checkpointer is not None:
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=[
                "initial_context_wait_for_feedback",  # New specialized node for waiting for feedback
                "human_prd_review",
                "human_feedback_plan"
            ]
        )
    else:
        return builder.compile(checkpointer=checkpointer)

# Create a fresh graph with no memory per call
def build_coding_graph():
    """Build a coding graph with no memory persistence."""
    return build_coding_graph_base(checkpointer=None, use_interrupts=False)

# Create a graph for interactive use (with interrupts)
def build_interactive_coding_graph():
    """Build a coding graph with memory persistence for interactive use."""
    memory = MemorySaver()
    return build_coding_graph_base(checkpointer=memory, use_interrupts=True)

# Create a persisted graph with memory
def build_coding_graph_with_memory():
    """Build a coding graph with memory persistence."""
    memory = MemorySaver()
    return build_coding_graph_base(checkpointer=memory, use_interrupts=False)

# Visualization helper
def visualize_coding_graph(graph=None):
    """Visualize the coding graph and save to file."""
    if graph is None:
        graph = build_coding_graph()
    save_graph_visualization(graph, filename="coding_graph_visualization.png")
    return get_graph_mermaid_syntax(graph)

# Don't create the graph instance here
# Only create it when actually needed by functions that use it
