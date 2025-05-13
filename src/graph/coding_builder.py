# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
import logging
from typing import Literal

# Import the shared State type
from .types import State # Assume State will be expanded to include prd_document, prd_status, etc.

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

# Moved should_revise_plan to module level (for task plan review)
def should_revise_task_plan(state: State) -> Literal["revise", "accept"]: # Renamed for clarity
    feedback = state.get("interrupt_feedback") # Assumes human_feedback_plan_node puts feedback here
    if feedback is None and state.get("messages"):
            feedback_candidate = state["messages"][-1]
            if hasattr(feedback_candidate, 'name') and feedback_candidate.name == 'user_feedback':
                feedback = feedback_candidate.content
            elif hasattr(feedback_candidate, 'type') and feedback_candidate.type == 'human':
                feedback = feedback_candidate.content
    feedback_str = str(feedback).strip().upper()
    logger.info(f"Task plan review feedback processing: '{feedback_str}'")
    if feedback_str.startswith("ACCEPT") or feedback_str.startswith("YES"):
        return "accept"
    return "revise"

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


# NEW conditional routing function for research_team
def route_from_research_team(state: State) -> Literal["researcher", "task_orchestrator", "coding_coordinator"]:
    """Determines the next step after the research_team node has processed a task or PRD research."""
    
    # Decision should ideally be based on a state field explicitly set by research_team_node,
    # or by interpreting the current_plan's active step.
    
    current_plan = state.get("current_plan")
    
    # Check if research_team_node itself made a decision (e.g., by setting a specific state field)
    # This part is hypothetical, research_team_node would need to be updated to set such a field.
    # For now, we rely on interpreting the plan.
    # research_goto_decision = state.get("research_team_decision") 
    # if research_goto_decision in ["researcher", "task_orchestrator", "coding_coordinator", "coding_planner"]:
    #     return research_goto_decision

    if not current_plan or not current_plan.steps:
        # This can happen if context_gatherer went to research_team for general PRD research
        # without a detailed micro-plan within the research phase.
        logger.debug("route_from_research_team: No current plan or steps, routing to coding_coordinator for PRD.")
        return "coding_coordinator"

    active_step = None
    all_steps_done = True
    for step in current_plan.steps:
        if not step.execution_res: # Found an unexecuted step
            active_step = step
            all_steps_done = False
            break
    
    if all_steps_done:
        logger.debug("route_from_research_team: All plan steps done, routing to coding_coordinator.")
        return "coding_coordinator" # Research plan complete, results for PRD

    if active_step:
        if active_step.step_type == StepType.RESEARCH:
            logger.debug(f"route_from_research_team: Active step is RESEARCH ('{active_step.title}'), routing to researcher.")
            return "researcher"
        elif active_step.step_type == StepType.PROCESSING:
            logger.debug(f"route_from_research_team: Active step is PROCESSING ('{active_step.title}'), routing to task_orchestrator.")
            return "task_orchestrator" # Vision: research identifies direct coding task
        else: # Other step types or undefined
            logger.warning(f"route_from_research_team: Active step ('{active_step.title}') has unhandled type {active_step.step_type}, routing to coding_coordinator.")
            return "coding_coordinator"
    
    # Fallback if no active step could be determined (should ideally not happen if all_steps_done is false)
    logger.warning("route_from_research_team: Fallback, no active step found despite not all steps being done. Routing to coding_coordinator.")
    return "coding_coordinator"


# Placeholder node functions
def prepare_codegen_task_node(state: State) -> State:
    logger.warning("prepare_codegen_task_node is a placeholder.")
    return state

def codegen_success_node(state: State) -> State:
    logger.info(f"Codegen task succeeded. Final Result: {state.get('codegen_task_result')}")
    return state

def codegen_failure_node(state: State) -> State:
    logger.error(f"Codegen task failed. Status: {state.get('codegen_task_status')}, Reason: {state.get('codegen_task_result')}")
    return state

MAX_POLL_ATTEMPTS = 10 
MAX_TRANSIENT_ERROR_ATTEMPTS = 3

def should_continue_polling(state: State) -> Literal["continue", "success", "failure", "error"]:
    status = state.get("codegen_task_status")
    poll_attempts = state.get("codegen_poll_attempts", 0)
    normalized_status = str(status).lower() if status is not None else "none"
    if normalized_status in ["pending", "running", "processing", "in_progress"]:
        if poll_attempts < MAX_POLL_ATTEMPTS: return "continue"
        else: return "failure"
    elif normalized_status == "completed" or normalized_status == "success": return "success"
    elif normalized_status.startswith("fail") or normalized_status.startswith("error"):
        if status != "error_during_poll": return "failure"
    if normalized_status == "none" or status == "error_during_poll":
        if poll_attempts < MAX_TRANSIENT_ERROR_ATTEMPTS: return "continue"
        else: return "error"
    return "error"


def build_coding_graph_base(checkpointer=None): # Renamed to base, memory passed in
    builder = StateGraph(State)

    # Add nodes
    builder.add_node("initial_context", initial_context_node)
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

    # --- Define Edges ---
    builder.add_edge(START, "initial_context")
    builder.add_edge("initial_context", "coding_coordinator")

    # PRD Building Loop managed by coding_coordinator
    # coding_coordinator_node's internal logic will update state.prd_status and state.goto_prd_next_step
    # Then its conditional edges will route based on that.
    # Example: state.prd_next_step can be "human_prd_review", "context_gatherer", "coding_planner"
    def route_from_coordinator(state: State) -> Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]:
        # This function will read state set by coding_coordinator_node
        # (e.g., state.get('prd_next_step', 'human_prd_review'))
        # It reflects the decision made *inside* coding_coordinator_node's execution
        next_step = state.get("prd_next_step", "human_prd_review") # Default to getting PRD feedback
        if state.get("prd_approved"): # Explicit flag set by coordinator after processing feedback
             return "coding_planner"
        return next_step
        
    builder.add_conditional_edges(
        "coding_coordinator",
        route_from_coordinator, # Decision made by coordinator node's logic reflected in state
        {
            "human_prd_review": "human_prd_review",
            "context_gatherer": "context_gatherer",
            "coding_planner": "coding_planner", # Exit PRD loop to planning
            "__end__": END # Fallback, should ideally not be hit if logic is sound
        }
    )
    
    builder.add_edge("human_prd_review", "coding_coordinator") # Feedback goes back to coordinator
    builder.add_edge("context_gatherer", "research_team") # Research path
    builder.add_conditional_edges(
        "research_team",
        route_from_research_team,
        {
            "researcher": "researcher",
            "task_orchestrator": "task_orchestrator",
            "coding_coordinator": "coding_coordinator",
            # "coding_planner": "coding_planner" # REMOVED - Not a direct path from research_team
        }
    )
    builder.add_edge("researcher", "research_team") # Researcher always feeds back to the research_team to re-evaluate

    # Task Planning and Review Loop
    builder.add_edge("coding_planner", "human_feedback_plan") # Planner sends task plan for review
    builder.add_conditional_edges(
        "human_feedback_plan",
        should_revise_task_plan, # Uses the renamed function for task plan feedback
        {
            "revise": "coding_planner", 
            "accept": "linear_integration" # Approved task plan goes to Linear integration
        }
    )
    builder.add_edge("linear_integration", "task_orchestrator") # After Linear sync, go to orchestrator

    # Task Orchestration and Codegen Loop
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
            "initiate_codegen": "initiate_codegen",       # Orchestrator dispatches a task
            "coding_planner": "coding_planner",           # Orchestrator sends a persistent failure back to planner
            "__end__": END                               # All tasks done
        }
    )

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
    
    # ---- START DEBUG PRINT ----
    print("--- DEBUG: Builder Nodes ---")
    for node_name, node_obj in builder.nodes.items():
        print(f"Node: {node_name}, Object: {getattr(node_obj, '__name__', str(node_obj))}")
    print("--- DEBUG: Builder Edges ---")
    for edge_tuple in builder.edges:
        # Edge tuple can be (source, target) or (source, target, data)
        source_node, target_node = edge_tuple[0], edge_tuple[1]
        edge_data = edge_tuple[2] if len(edge_tuple) > 2 else None
        print(f"Edge: source='{source_node}', target='{target_node}', data={edge_data}")
    print("--- DEBUG: Builder Branches ---")
    for branch_source_node_name, branch_obj in builder.branches.items():
        print(f"Branch from '{branch_source_node_name}':")
        # branch_obj can be a callable or a Branch instance
        if hasattr(branch_obj, 'ends') and branch_obj.ends:
            print(f"  Conditional ends: {branch_obj.ends}")
        elif callable(branch_obj):
            print(f"  Conditional callable: {getattr(branch_obj, '__name__', str(branch_obj))}")
        else:
            print(f"  Branch info: {branch_obj}") # Fallback for other structures

    print("--- END DEBUG PRINT ---")
    return builder.compile(checkpointer=checkpointer, 
                           interrupt_before=["human_prd_review", "human_feedback_plan"])

def build_coding_graph():
    return build_coding_graph_base(checkpointer=None) # No memory / checkpointer by default

def build_coding_graph_with_memory():
    return build_coding_graph_base(checkpointer=MemorySaver())


# Create the graph instance (for visualization and potentially direct use if no memory needed)
coding_graph = build_coding_graph()

# Visualize the graph after compilation
if coding_graph:
    mermaid_syntax = get_graph_mermaid_syntax(coding_graph)
    if mermaid_syntax:
        print("--- Mermaid Syntax START ---")
        print(mermaid_syntax)
        print("--- Mermaid Syntax END ---")
        md_file_path = "coding_graph.md"
        try:
            with open(md_file_path, "w") as f:
                f.write("```mermaid\n") # Ensure mermaid language identifier is on its own line
                f.write(mermaid_syntax) # The syntax itself should control its internal newlines
                f.write("\n```")       # Ensure closing backticks are on their own line after the syntax
            print(f"Mermaid syntax saved to {md_file_path}")
        except Exception as e:
            print(f"Error saving Mermaid syntax to {md_file_path}: {e}")
            
    save_graph_visualization(coding_graph, output_path="coding_graph_visualization.png")
