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
    research_team_node,
    researcher_node,
    human_prd_review_node, # NEW for PRD feedback
    linear_integration_node, # NEWLY ADDED
    human_initial_context_review_node, # Legacy node for initial context review
    # New specialized nodes for initial context review
    initial_context_query_generator_node,
    initial_context_wait_for_feedback_node,
    initial_context_feedback_handler_node,
    initial_context_approval_router_node,
    context_gatherer_node, # Ensure this is imported
    # human_plan_review_node, # Stays removed
)

# Import GitHub nodes
from .github_nodes import (
    github_manager_node,
    # github_planning_node, # Already removed
)

# Import the new utility
from .visualizer import save_graph_visualization, get_graph_mermaid_syntax

logger = logging.getLogger(__name__)

# --- Define passthrough end node functions ---
def initial_context_passthrough_end_node(state: State) -> State:
    logger.debug("Reached initial_context_passthrough_end_node")
    return state

def coordinator_passthrough_end_node(state: State) -> State:
    logger.debug("Reached coordinator_passthrough_end_node")
    return state

def orchestrator_passthrough_end_node(state: State) -> State:
    logger.debug("Reached orchestrator_passthrough_end_node")
    return state

# --- Define edge routing functions ---

def get_initial_context_routing_decision(state: State) -> str:
    """Reads the routing decision made by initial_context_approval_router_node."""
    decision = state.get("initial_context_routing_decision")
    if not decision: # E.g. if initial_context_approval_router_node didn't set it
        logger.error("Initial context routing decision not found in state! Defaulting to custom end for initial context.")
        return "go_to_initial_context_final_end" # MODIFIED: return unique string for END
    logger.info(f"Routing based on initial_context_routing_decision: {decision}")
    # Ensure 'decision' is one of the expected strings by the map later
    if decision not in ["coding_coordinator", "refine_initial_context_loop"]: # Assuming these are the only non-end paths
        logger.warning(f"Unexpected decision '{decision}' from initial_context_approval_router. Forcing to initial context end.")
        return "go_to_initial_context_final_end"
    return decision

def route_after_initial_context_review(state: State) -> Literal["coding_coordinator", "initial_context_query_generator"]:
    # The query generator is the start of the explicit loop
    if state.get("initial_context_approved"):
        logger.info("Initial context approved. Proceeding to coding_coordinator.")
        return "coding_coordinator"
    else:
        logger.info("Initial context not yet approved or awaiting further input. Looping back to initial_context_query_generator.")
        return "initial_context_query_generator"

def route_after_prd_review(state: State) -> Literal["coding_planner", "coding_coordinator", "human_prd_review"]:
    """Routes after human_prd_review_node based on approval and awaiting input flags."""
    if state.get("awaiting_prd_review_input"):
        logger.info("Awaiting PRD review input from user. Looping back to human_prd_review_node.")
        return "human_prd_review"
    elif state.get("prd_approved"):
        logger.info("PRD approved. Proceeding to coding_planner.")
        return "coding_planner"
    else:
        logger.info("PRD not approved (revisions requested). Returning to coding_coordinator.")
        return "coding_coordinator"

def route_after_plan_review(state: State) -> Literal["linear_integration", "coding_planner", "human_feedback_plan"]:
    """Routes after human_feedback_plan_node based on approval and awaiting input flags."""
    if state.get("awaiting_plan_review_input"):
        logger.info("Awaiting plan review input from user. Looping back to human_feedback_plan_node.")
        return "human_feedback_plan"
    elif state.get("plan_approved"):
        logger.info("Plan approved. Proceeding to linear_integration.") # Or task_orchestrator if that is the actual next step
        return "linear_integration"
    else:
        logger.info("Plan not approved (revisions requested). Returning to coding_planner.")
        return "coding_planner"

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
def route_from_coordinator(state: State) -> Literal["context_gatherer", "coding_planner", "go_to_coordinator_final_end"]:
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
        if state.get("prd_document") and state.get("prd_status") == "approved":
            logger.info("Simulated input mode: PRD already approved, proceeding to coding planner.")
            return "coding_planner"
        elif state.get("prd_document"):
            logger.info("Simulated input mode: PRD exists but needs review approval.")
            return "context_gatherer"
        else:
            logger.info("Simulated input mode: No PRD document yet, routing to context_gatherer to generate one.")
            return "context_gatherer"

    next_step = state.get("prd_next_step")
    if next_step:
        logger.info(f"Using explicit prd_next_step: {next_step}")
        # Ensure next_step is a valid key for this router's map, excluding the end case handled below
        if next_step not in ["context_gatherer", "coding_planner", "human_prd_review"]: # human_prd_review added as it's in map for coding_coordinator
             logger.warning(f"Invalid prd_next_step '{next_step}' for coordinator. Defaulting to coordinator end.")
             return "go_to_coordinator_final_end"
        return next_step

    if state.get("prd_approved") or state.get("prd_status") == "approved":
        logger.info("PRD is approved, routing to coding planner.")
        return "coding_planner"

    prd_review_feedback = state.get("prd_review_feedback", "").lower()
    if "approve" in prd_review_feedback or "accept" in prd_review_feedback or "good" in prd_review_feedback:
        logger.info("PRD approval detected in feedback, routing to coding planner.")
        return "coding_planner"

    if state.get("prd_document") and state.get("prd_status") == "awaiting_review":
        logger.info("PRD document exists and awaiting review, routing to context_gatherer.")
        return "context_gatherer"

    if not state.get("prd_document"):
        logger.info("No PRD document yet, letting coordinator try again.")
        return "context_gatherer"

    logger.info("No clear routing decision could be made by coordinator, defaulting to coordinator end.")
    return "go_to_coordinator_final_end" # MODIFIED: return unique string for END

MAX_CODEGEN_POLL_ATTEMPTS = 10 # Define a max attempts for polling

def should_continue_polling(state: State) -> Literal["continue", "success", "failure", "error"]:
    """Determines if codegen polling should continue, or if it's success/failure."""
    codegen_status = state.get("codegen_status")
    poll_attempts = state.get("codegen_poll_attempts", 0)

    logger.info(f"should_continue_polling: status='{codegen_status}', attempts={poll_attempts}")

    if codegen_status == "completed":
        logger.info("Polling: codegen_status is 'completed'. Routing to success.")
        return "success"
    elif codegen_status == "failed": # Assuming poll_codegen_status_node might set this
        logger.info("Polling: codegen_status is 'failed'. Routing to failure.")
        return "failure"
    
    if poll_attempts >= MAX_CODEGEN_POLL_ATTEMPTS:
        logger.warning(f"Polling: Max poll attempts ({MAX_CODEGEN_POLL_ATTEMPTS}) reached. Routing to failure.")
        return "failure" # Or "error" depending on desired handling

    # If not completed/failed and attempts not exceeded, continue polling
    logger.info("Polling: Status not terminal and attempts not exceeded. Routing to continue.")
    # Important: The poll_codegen_status_node should increment this
    # For safety, we could increment it here if the node doesn't, but it's better if the node does.
    # state["codegen_poll_attempts"] = poll_attempts + 1 # This might not persist correctly if not returned by the node
    return "continue"

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
    builder.add_node("context_gatherer", context_gatherer_node) # Ensure this is imported
    builder.add_node("research_team", research_team_node) # For research
    builder.add_node("researcher", researcher_node) # ADDED

    builder.add_node("coding_planner", coding_planner_node) # Takes approved PRD
    builder.add_node("human_feedback_plan", human_feedback_plan_node) # NEW for TASK PLAN review
    builder.add_node("linear_integration", linear_integration_node) # NEWLY ADDED

    builder.add_node("task_orchestrator", task_orchestrator_node) # Renamed from prepare_codegen_task
    builder.add_node("initiate_codegen", initiate_codegen_node)
    builder.add_node("poll_codegen_status", poll_codegen_status_node)
    builder.add_node("codegen_success", codegen_success_node)
    builder.add_node("codegen_failure", codegen_failure_node)

    builder.add_node("github_manager", github_manager_node)
    # Use dedicated functions for passthrough end nodes
    builder.add_node("initial_context_final_end_node", initial_context_passthrough_end_node)
    builder.add_node("coordinator_final_end_node", coordinator_passthrough_end_node)
    builder.add_node("orchestrator_final_end_node", orchestrator_passthrough_end_node)

    # --- Define Simplified Edges ---
    # START FLOW: Initial context gathering → specialized nodes for review → coordinator
    builder.add_edge(START, "initial_context")

    # Connect initial_context to the new specialized flow
    builder.add_edge("initial_context", "initial_context_query_generator")

    # Connect the specialized nodes in sequence
    builder.add_edge("initial_context_query_generator", "initial_context_wait_for_feedback")
    builder.add_edge("initial_context_wait_for_feedback", "initial_context_feedback_handler")
    builder.add_edge("initial_context_feedback_handler", "initial_context_approval_router")
    # REMOVED: builder.add_edge("initial_context_final_end_node", END) # ADDED <- Will be re-added after conditional

    # Conditional routing from the approval router (initial context)
    builder.add_conditional_edges(
        "initial_context_approval_router",
        get_initial_context_routing_decision,
        {
            "coding_coordinator": "coding_coordinator",
            "refine_initial_context_loop": "initial_context",
            "go_to_initial_context_final_end": "initial_context_final_end_node"
        }
    )
    # Ensure final end node is connected AFTER the conditional edge that might route to it
    builder.add_edge("initial_context_final_end_node", END)

    # PRD BUILDING LOOP: 
    # coding_coordinator decides if PRD needs creation/update, then goes to human_prd_review
    builder.add_conditional_edges(
        "coding_coordinator",
        route_from_coordinator,
        {
            "context_gatherer": "context_gatherer",
            "coding_planner": "coding_planner",
            "human_prd_review": "human_prd_review",
            "go_to_coordinator_final_end": "coordinator_final_end_node"
        }
    )
    builder.add_edge("coordinator_final_end_node", END)

    # After human reviews PRD, route based on their feedback
    builder.add_conditional_edges(
        "human_prd_review",
        route_after_prd_review,
        {
            "coding_planner": "coding_planner",
            "coding_coordinator": "coding_coordinator",
            "human_prd_review": "human_prd_review"
        }
    )

    # Context gathering (research) can be triggered by coding_coordinator or other nodes
    builder.add_edge("context_gatherer", "research_team")
    builder.add_conditional_edges(
        "research_team",
        route_from_research_team,
        {
            "researcher": "researcher",
            "task_orchestrator": "task_orchestrator",
            "coding_coordinator": "coding_coordinator",
            "coding_planner": "coding_planner"
        }
    )
    builder.add_edge("researcher", "research_team")

    # TASK PLANNING LOOP: 
    builder.add_edge("coding_planner", "human_feedback_plan")

    builder.add_conditional_edges(
        "human_feedback_plan",
        route_after_plan_review,
        {
            "linear_integration": "linear_integration",
            "coding_planner": "coding_planner",
            "human_feedback_plan": "human_feedback_plan"
        }
    )
    
    builder.add_edge("linear_integration", "task_orchestrator")

    # TASK EXECUTION LOOP (Task Orchestrator and Codegen)
    def route_from_orchestrator(state: State) -> Literal["initiate_codegen", "coding_planner", "research_team", "go_to_orchestrator_final_end"]:
        orchestrator_decision = state.get("orchestrator_next_step") # Default handled by map if key not found
        logger.info(f"Routing from task_orchestrator based on orchestrator_next_step: {orchestrator_decision}")

        if orchestrator_decision == "dispatch_task_for_codegen":
            return "initiate_codegen"
        elif orchestrator_decision == "forward_failure_to_planner":
            return "coding_planner"
        elif orchestrator_decision == "dispatch_task_for_research": # Assuming task_orchestrator can route to research
            return "research_team"
        elif orchestrator_decision == "all_tasks_complete" or not orchestrator_decision: # also if None or empty
            logger.info("Orchestrator: All tasks complete or no specific next step. Routing to orchestrator end.")
            return "go_to_orchestrator_final_end"
        
        # If orchestrator_decision is some other string not in the map, it will lead to an error.
        # Add a fallback or ensure task_orchestrator_node only sets valid strings.
        valid_steps = ["initiate_codegen", "coding_planner", "research_team", "go_to_orchestrator_final_end"]
        if orchestrator_decision not in valid_steps:
            logger.warning(f"Orchestrator: Invalid step '{orchestrator_decision}'. Defaulting to orchestrator end.")
            return "go_to_orchestrator_final_end"
        return orchestrator_decision # Should be one of the valid_steps or "go_to_orchestrator_final_end"

    builder.add_conditional_edges(
        "task_orchestrator",
        route_from_orchestrator,
        {
            "initiate_codegen": "initiate_codegen",
            "coding_planner": "coding_planner",
            "research_team": "research_team",
            "go_to_orchestrator_final_end": "orchestrator_final_end_node"
        }
    )
    builder.add_edge("orchestrator_final_end_node", END)

    # CODEGEN FLOW
    builder.add_edge("initiate_codegen", "poll_codegen_status")
    builder.add_conditional_edges(
        "poll_codegen_status",
        should_continue_polling, # type: ignore
        {
            "continue": "poll_codegen_status",
            "success": "codegen_success",
            "failure": "codegen_failure",
            "error": "codegen_failure",
        },
    )

    builder.add_edge("codegen_failure", "task_orchestrator")
    builder.add_edge("codegen_success", "github_manager")
    builder.add_edge("github_manager", "task_orchestrator")

    if use_interrupts and checkpointer is not None:
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=[
                "initial_context_wait_for_feedback",
            ]
        )
    else:
        return builder.compile(checkpointer=checkpointer)

# Create a fresh graph with no memory per call
def build_coding_graph():
    """Build a coding graph with no memory persistence."""
    return build_coding_graph_base(checkpointer=None, use_interrupts=False)

# Create a graph for interactive use (with interrupts)
def build_interactive_coding_graph(checkpointer: MemorySaver): # Accept checkpointer
    """Build a coding graph with memory persistence for interactive use."""
    # memory = MemorySaver() # No longer created here
    return build_coding_graph_base(checkpointer=checkpointer, use_interrupts=True)

# Create a persisted graph with memory
def build_coding_graph_with_memory(checkpointer: MemorySaver): # Accept checkpointer
    """Build a coding graph with memory persistence."""
    # memory = MemorySaver() # No longer created here
    return build_coding_graph_base(checkpointer=checkpointer, use_interrupts=False)

# Visualization helper
def visualize_coding_graph(graph=None):
    """Visualize the coding graph and save to file."""
    if graph is None:
        graph = build_coding_graph()
    save_graph_visualization(graph, filename="coding_graph_visualization.png")
    return get_graph_mermaid_syntax(graph)

# Don't create the graph instance here
# Only create it when actually needed by functions that use it
