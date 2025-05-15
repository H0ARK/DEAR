# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
import logging
from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage

# Import the shared State type
from .types import State

# Import the nodes we'll need
from .nodes.planning import human_prd_review_node, human_feedback_plan_node
from .nodes.coordination import coding_coordinator_node, initial_context_node
from .nodes.integration import linear_integration_node
from .nodes.coding import task_orchestrator_node, initiate_codegen_node, poll_codegen_status_node, codegen_success_node, codegen_failure_node

# Import the visualizer
from .visualizer import save_graph_visualization, get_graph_mermaid_syntax

logger = logging.getLogger(__name__)

# --- Define edge routing functions ---

def route_after_prd_review(state: State) -> Literal["planner_agent", "coding_coordinator", "human_prd_review"]:
    """Routes after human_prd_review_node based on approval and awaiting input flags."""
    if state.get("awaiting_prd_review_input"):
        logger.info("Awaiting PRD review input from user. Looping back to human_prd_review_node.")
        return "human_prd_review"
    elif state.get("prd_approved"):
        logger.info("PRD approved. Proceeding to planner_agent.")
        return "planner_agent"
    else:
        logger.info("PRD not approved (revisions requested). Returning to coding_coordinator.")
        return "coding_coordinator"

def route_after_plan_review(state: State) -> Literal["orchestration_agent", "planner_agent", "human_feedback_plan"]:
    """Routes after human_feedback_plan_node based on approval and awaiting input flags."""
    if state.get("awaiting_plan_review_input"):
        logger.info("Awaiting plan review input from user. Looping back to human_feedback_plan_node.")
        return "human_feedback_plan"
    elif state.get("plan_approved"):
        logger.info("Plan approved. Proceeding to orchestration_agent.")
        return "orchestration_agent"
    else:
        logger.info("Plan not approved (revisions requested). Returning to planner_agent.")
        return "planner_agent"

def should_continue_polling(state: State) -> Literal["continue", "success", "failure", "error"]:
    """Determines if codegen polling should continue, or if it's success/failure."""
    codegen_status = state.get("codegen_status", "")
    poll_attempts = state.get("codegen_poll_attempts", 0)
    max_attempts = 10  # Define a max attempts for polling
    
    logger.info(f"Polling codegen status: {codegen_status}, attempt {poll_attempts}/{max_attempts}")
    
    if codegen_status == "completed":
        logger.info("Codegen completed successfully.")
        return "success"
    elif codegen_status == "failed":
        logger.info("Codegen failed.")
        return "failure"
    elif codegen_status == "error":
        logger.info("Codegen encountered an error.")
        return "error"
    elif poll_attempts >= max_attempts:
        logger.warning(f"Max poll attempts ({max_attempts}) reached. Treating as failure.")
        return "failure"
    else:
        logger.info(f"Codegen still in progress. Continuing to poll.")
        return "continue"

# New node implementations for the simplified system

def planner_agent_node(state: State) -> State:
    """Planner agent that creates a detailed task breakdown from the PDR."""
    logger.info("Planner agent generating detailed task plan...")
    
    # This would contain the logic to break down the PDR into tasks
    # For now, we'll just add a placeholder message
    
    state["messages"] = state.get("messages", []) + [
        AIMessage(content="I've analyzed the PDR and created a detailed task breakdown.", name="planner_agent")
    ]
    
    # In a real implementation, this would generate the tasks_definition
    # For now, we'll create a simple placeholder
    if not state.get("tasks_definition"):
        state["tasks_definition"] = [
            {
                "id": "task_001",
                "name": "Setup Project Structure",
                "description": "Create the initial project structure and configuration files.",
                "dependencies": [],
                "status": "Todo"
            },
            {
                "id": "task_002",
                "name": "Implement Core Functionality",
                "description": "Implement the core functionality described in the PDR.",
                "dependencies": ["task_001"],
                "status": "Todo"
            }
        ]
    
    return state

def orchestration_agent_node(state: State) -> State:
    """Orchestration agent that manages task execution and monitors Codegen."""
    logger.info("Orchestration agent managing tasks...")
    
    # Get the tasks definition
    tasks_definition = state.get("tasks_definition", [])
    if not tasks_definition:
        logger.error("No tasks definition found in state. Cannot orchestrate tasks.")
        state["messages"] = state.get("messages", []) + [
            AIMessage(content="Error: No tasks definition found. Cannot orchestrate tasks.", name="orchestration_agent")
        ]
        state["has_pending_tasks"] = False
        return state
    
    # Find the next task to execute
    next_task = None
    for task in tasks_definition:
        if task.get("status") == "Todo":
            # Check if all dependencies are completed
            dependencies = task.get("dependencies", [])
            all_deps_completed = True
            for dep_id in dependencies:
                dep_task = next((t for t in tasks_definition if t.get("id") == dep_id), None)
                if not dep_task or dep_task.get("status") != "Done":
                    all_deps_completed = False
                    break
            
            if all_deps_completed:
                next_task = task
                break
    
    if next_task:
        logger.info(f"Next task to execute: {next_task.get('name')}")
        state["current_task"] = next_task
        state["has_pending_tasks"] = True
        
        # Update the task status to In Progress
        next_task["status"] = "In Progress"
        
        state["messages"] = state.get("messages", []) + [
            AIMessage(content=f"Starting work on task: {next_task.get('name')}", name="orchestration_agent")
        ]
    else:
        logger.info("No more tasks to execute or all tasks have dependencies that are not yet completed.")
        state["has_pending_tasks"] = False
        
        # Check if all tasks are done
        all_done = all(task.get("status") == "Done" for task in tasks_definition)
        if all_done:
            state["messages"] = state.get("messages", []) + [
                AIMessage(content="All tasks have been completed successfully!", name="orchestration_agent")
            ]
        else:
            state["messages"] = state.get("messages", []) + [
                AIMessage(content="Waiting for task dependencies to be completed.", name="orchestration_agent")
            ]
    
    return state

def pr_validation_node(state: State) -> State:
    """Node that validates the PR and merges it if valid."""
    logger.info("Validating PR...")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot validate PR.")
        state["messages"] = state.get("messages", []) + [
            AIMessage(content="Error: No current task found. Cannot validate PR.", name="pr_validation")
        ]
        return state
    
    # In a real implementation, this would check the PR status and validate it
    # For now, we'll just simulate a successful validation
    
    logger.info(f"PR for task {current_task.get('name')} validated successfully.")
    
    # Update the task status to Done
    current_task["status"] = "Done"
    
    state["messages"] = state.get("messages", []) + [
        AIMessage(content=f"PR for task '{current_task.get('name')}' has been validated and merged.", name="pr_validation")
    ]
    
    return state

def build_simplified_graph_base(checkpointer=None, use_interrupts=True):
    """Build a simplified graph with the 4-agent system."""
    builder = StateGraph(State)
    
    # Add nodes for the 4-agent system
    
    # 1. Planner Agent - talks to user and iterates on a plan/PDR
    builder.add_node("initial_context", initial_context_node)
    builder.add_node("coding_coordinator", coding_coordinator_node)  # Handles PDR creation
    builder.add_node("human_prd_review", human_prd_review_node)      # For PDR feedback
    
    # 2. Planner Agent - creates detailed task breakdown
    builder.add_node("planner_agent", planner_agent_node)            # New simplified planner
    builder.add_node("human_feedback_plan", human_feedback_plan_node) # For plan feedback
    
    # 3. Orchestration Agent - breaks PDR into tasks and monitors Codegen
    builder.add_node("orchestration_agent", orchestration_agent_node) # New simplified orchestrator
    builder.add_node("linear_integration", linear_integration_node)   # Creates tasks in Linear
    
    # 4. Codegen execution and monitoring
    builder.add_node("initiate_codegen", initiate_codegen_node)
    builder.add_node("poll_codegen_status", poll_codegen_status_node)
    builder.add_node("codegen_success", codegen_success_node)
    builder.add_node("codegen_failure", codegen_failure_node)
    builder.add_node("pr_validation", pr_validation_node)            # New node for PR validation
    
    # --- Define Simplified Edges ---
    
    # START FLOW: Initial context gathering → coordinator → PDR review
    builder.add_edge(START, "initial_context")
    builder.add_edge("initial_context", "coding_coordinator")
    
    # PDR BUILDING LOOP
    builder.add_edge("coding_coordinator", "human_prd_review")
    
    # After human reviews PDR, route based on their feedback
    builder.add_conditional_edges(
        "human_prd_review",
        route_after_prd_review,
        {
            "planner_agent": "planner_agent",           # PDR approved, proceed to planning
            "coding_coordinator": "coding_coordinator",  # Loop back for revisions
            "human_prd_review": "human_prd_review"      # Loop back if still awaiting input
        }
    )
    
    # TASK PLANNING LOOP
    builder.add_edge("planner_agent", "human_feedback_plan")
    
    # After human reviews the plan, route based on their feedback
    builder.add_conditional_edges(
        "human_feedback_plan",
        route_after_plan_review,
        {
            "orchestration_agent": "orchestration_agent", # Plan approved
            "planner_agent": "planner_agent",             # Revisions requested
            "human_feedback_plan": "human_feedback_plan"  # Loop back if still awaiting input
        }
    )
    
    # ORCHESTRATION FLOW
    builder.add_edge("orchestration_agent", "linear_integration")
    builder.add_edge("linear_integration", "initiate_codegen")
    
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
    
    # Codegen outcomes
    builder.add_edge("codegen_success", "pr_validation")
    builder.add_edge("codegen_failure", "orchestration_agent")  # Return to orchestrator on failure
    
    # PR validation
    builder.add_edge("pr_validation", "orchestration_agent")    # Return to orchestrator after validation
    
    # End condition from orchestrator when all tasks are complete
    builder.add_conditional_edges(
        "orchestration_agent",
        lambda x: "initiate_codegen" if x.get("has_pending_tasks", True) else "__end__",
        {
            "initiate_codegen": "initiate_codegen",  # More tasks to process
            "__end__": END                           # All tasks complete
        }
    )
    
    if use_interrupts and checkpointer is not None:
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=[
                "human_prd_review",
                "human_feedback_plan",
            ]
        )
    else:
        return builder.compile(checkpointer=checkpointer)

# Create a fresh graph with no memory per call
def build_simplified_graph():
    """Build a simplified graph with no memory persistence."""
    return build_simplified_graph_base(checkpointer=None, use_interrupts=False)

# Create a graph for interactive use (with interrupts)
def build_interactive_simplified_graph():
    """Build a simplified graph with memory persistence for interactive use."""
    memory = MemorySaver()
    return build_simplified_graph_base(checkpointer=memory, use_interrupts=True)

# Create a persisted graph with memory
def build_simplified_graph_with_memory():
    """Build a simplified graph with memory persistence."""
    memory = MemorySaver()
    return build_simplified_graph_base(checkpointer=memory, use_interrupts=False)

# Visualization helper
def visualize_simplified_graph(graph=None):
    """Visualize the simplified graph and save to file."""
    if graph is None:
        graph = build_simplified_graph()
    save_graph_visualization(graph, filename="simplified_graph_visualization.png")
    return get_graph_mermaid_syntax(graph)

