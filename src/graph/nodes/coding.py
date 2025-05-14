# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from .common import *

def coding_dispatcher_node(state: State) -> Command[Literal["codegen_executor", "task_orchestrator", "__end__"]]:
    """Dispatcher node that routes to the appropriate coding node."""
    logger.info("Coding dispatcher routing...")
    
    # Check if we have a task to execute
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot dispatch.")
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content="Error: No current task found. Cannot proceed with coding.", name="coding_dispatcher")]
            },
            goto="__end__"
        )
    
    # Check if the task is a coding task
    task_type = current_task.get("type", "")
    if task_type == "coding":
        logger.info("Dispatching to codegen executor for coding task.")
        return Command(update=state, goto="codegen_executor")
    else:
        logger.info(f"Task type '{task_type}' is not a coding task. Returning to task orchestrator.")
        return Command(update=state, goto="task_orchestrator")


def codegen_executor_node(state: State) -> State:
    """Node that executes code generation tasks."""
    logger.info("Executing code generation task...")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot execute code generation.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot execute code generation.", name="codegen_executor")]
        return state
    
    # Update the state to indicate we're initiating code generation
    state["codegen_status"] = "initiating"
    
    logger.info("Code generation initiated. Proceeding to initiate_codegen_node.")
    return state


def initiate_codegen_node(state: State, config: RunnableConfig) -> State:
    """Node that initiates the code generation process."""
    logger.info("Initiating code generation process...")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot initiate code generation.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot initiate code generation.", name="initiate_codegen")]
        state["codegen_status"] = "failed"
        return state
    
    # Get the task description
    task_description = current_task.get("description", "")
    if not task_description:
        logger.error("Task description is empty. Cannot initiate code generation.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="Error: Task description is empty. Cannot initiate code generation.", name="initiate_codegen")]
        state["codegen_status"] = "failed"
        return state
    
    # Simulate initiating code generation
    logger.info(f"Initiated code generation for task: {task_description[:100]}...")
    
    # Update the state to indicate we're processing code generation
    state["codegen_status"] = "processing"
    state["codegen_id"] = f"codegen_{random.randint(1000, 9999)}"
    
    logger.info("Code generation process initiated. Proceeding to poll_codegen_status_node.")
    return state


def poll_codegen_status_node(state: State, config: RunnableConfig) -> State:
    """Node that polls the status of the code generation process."""
    logger.info("Polling code generation status...")
    
    # Get the codegen ID
    codegen_id = state.get("codegen_id")
    if not codegen_id:
        logger.error("No codegen ID found in state. Cannot poll status.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="Error: No codegen ID found. Cannot poll status.", name="poll_codegen_status")]
        state["codegen_status"] = "failed"
        return state
    
    # Increment poll attempts
    poll_attempts = state.get("codegen_poll_attempts", 0) + 1
    state["codegen_poll_attempts"] = poll_attempts
    logger.info(f"Poll attempt: {poll_attempts}")

    # Simulate polling status
    # In a real implementation, this would make an API call to check the status
    
    # For demonstration purposes, randomly determine if the code generation is complete
    is_complete = random.choice([True, False])
    
    if is_complete:
        logger.info(f"Code generation {codegen_id} is complete.")
        state["codegen_status"] = "completed"
        state["codegen_result"] = {
            "code": "# Generated code would be here",
            "message": "Code generation completed successfully."
        }
    else:
        logger.info(f"Code generation {codegen_id} is still processing.")
        # Keep the status as processing
    
    logger.info(f"Current codegen status: {state['codegen_status']}")
    return state


def codegen_success_node(state: State) -> State:
    """Node that handles successful code generation."""
    logger.info("Code generation succeeded.")
    
    # Get the codegen result
    codegen_result = state.get("codegen_result", {})
    
    # Update the state with the success message
    state["messages"] = state.get("messages", []) + [AIMessage(content=f"Code generation completed successfully: {codegen_result.get('message', '')}", name="codegen_success")]
    
    return state


def codegen_failure_node(state: State) -> State:
    """Node that handles failed code generation."""
    logger.info("Code generation failed.")
    
    # Update the state with the failure message
    state["messages"] = state.get("messages", []) + [AIMessage(content="Code generation failed. Please try again or modify the task description.", name="codegen_failure")]
    
    return state


def check_repo_status(repo_path: str | None = None) -> tuple[bool, str]:
    """Check if the repository is in a clean state."""
    # In a real implementation, this would check the git status
    # For demonstration purposes, always return success
    return True, "Repository is in a clean state."


def task_orchestrator_node(state: State) -> State:
    """Node that orchestrates the execution of tasks."""
    logger.info("Task orchestrator managing tasks...")
    
    # Get the tasks definition
    tasks_definition = state.get("tasks_definition", [])
    if not tasks_definition:
        logger.error("No tasks definition found in state. Cannot orchestrate tasks.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="Error: No tasks definition found. Cannot orchestrate tasks.", name="task_orchestrator")]
        return state
    
    # Get the current task index
    current_task_index = state.get("current_task_index", 0)
    
    # Check if we've completed all tasks
    if current_task_index >= len(tasks_definition):
        logger.info("All tasks completed. Ending orchestration.")
        state["messages"] = state.get("messages", []) + [AIMessage(content="All tasks have been completed successfully.", name="task_orchestrator")]
        return state
    
    # Get the current task
    current_task = tasks_definition[current_task_index]
    
    # Update the state with the current task
    state["current_task"] = current_task
    
    # Determine the task type based on the task description
    # In a real implementation, this would be more sophisticated
    task_description = current_task.get("description", "").lower()
    if "code" in task_description or "implement" in task_description or "develop" in task_description:
        current_task["type"] = "coding"
    else:
        current_task["type"] = "other"
    
    logger.info(f"Current task: {current_task.get('name')} (Type: {current_task.get('type')})")
    
    # Increment the task index for the next iteration
    state["current_task_index"] = current_task_index + 1
    
    return state

