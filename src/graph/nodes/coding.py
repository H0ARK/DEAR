# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

def coding_dispatcher_node(state: State) -> Command[Literal["codegen_executor", "task_orchestrator", "__end__"]]: # Changed coder to task_orchestrator
    """Dispatcher node that routes to the appropriate coding node."""
    logger.info("Coding dispatcher routing...")
    
    # Check if we have a task to execute
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot dispatch.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot proceed with coding.", name="coding_dispatcher")]},
            goto="__end__"
        )
    
    # Check if the task is a coding task
    task_type = current_task.get("type", "coding")
    if task_type != "coding":
        logger.info(f"Task is not a coding task (type: {task_type}). Routing to task orchestrator.")
        return Command(goto="task_orchestrator")
    
    # Route to the codegen executor
    logger.info("Task is a coding task. Routing to codegen executor.")
    return Command(goto="codegen_executor")


def codegen_executor_node(state: State) -> State:
    """Execute a coding task using the codegen service."""
    logger.info("Executing coding task with codegen...")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot execute.")
        return {
            "messages": state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot execute coding task.", name="codegen_executor")],
            "task_execution_status": "failed",
            "task_execution_error": "No current task found in state."
        }
    
    # Get the task details
    task_id = current_task.get("id")
    task_description = current_task.get("description")
    
    logger.info(f"Executing coding task {task_id}: {task_description[:100]}...")
    
    # Check if we have a codegen client
    codegen_client = state.get("codegen_client")
    if not codegen_client:
        # Initialize the codegen client
        try:
            codegen_client = MultiServerMCPClient()
            logger.info("Initialized codegen client.")
        except Exception as e:
            logger.error(f"Error initializing codegen client: {e}")
            return {
                "messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to initialize codegen client. {e}", name="codegen_executor")],
                "task_execution_status": "failed",
                "task_execution_error": f"Failed to initialize codegen client: {e}"
            }
    
    # Start the codegen execution
    try:
        # Prepare the execution context
        execution_context = {
            "task_id": task_id,
            "task_description": task_description,
            "acceptance_criteria": current_task.get("acceptance_criteria", []),
            "dependencies": current_task.get("dependencies", []),
            "project_context": state.get("project_context", {}),
            "repository_url": state.get("repository_url"),
            "branch_name": current_task.get("branch_name", f"task/{task_id}")
        }
        
        # Submit the task to codegen
        execution_id = codegen_client.submit_task(
            task_description=task_description,
            context=execution_context
        )
        
        logger.info(f"Submitted task to codegen. Execution ID: {execution_id}")
        
        # Update the state with the execution ID
        return {
            "codegen_client": codegen_client,
            "codegen_execution_id": execution_id,
            "task_execution_status": "running",
            "messages": state.get("messages", []) + [AIMessage(content=f"Started execution of coding task: {task_description[:100]}...", name="codegen_executor")]
        }
        
    except Exception as e:
        logger.error(f"Error executing coding task: {e}")
        return {
            "messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to execute coding task. {e}", name="codegen_executor")],
            "task_execution_status": "failed",
            "task_execution_error": f"Failed to execute coding task: {e}"
        }


def initiate_codegen_node(state: State) -> Command[Literal["poll_codegen_status"]]:
    """Initiate a codegen execution."""
    logger.info("Initiating codegen execution...")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot initiate codegen.")
        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot initiate codegen.", name="initiate_codegen")],
                "task_execution_status": "failed",
                "task_execution_error": "No current task found in state."
            },
            goto="codegen_failure"
        )
    
    # Initialize the codegen client if needed
    codegen_client = state.get("codegen_client")
    if not codegen_client:
        try:
            codegen_client = MultiServerMCPClient()
            logger.info("Initialized codegen client.")
        except Exception as e:
            logger.error(f"Error initializing codegen client: {e}")
            return Command(
                update={
                    "messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to initialize codegen client. {e}", name="initiate_codegen")],
                    "task_execution_status": "failed",
                    "task_execution_error": f"Failed to initialize codegen client: {e}"
                },
                goto="codegen_failure"
            )
    
    # Prepare the task for codegen
    task_id = current_task.get("id")
    task_description = current_task.get("description")
    
    # Prepare the execution context
    execution_context = {
        "task_id": task_id,
        "task_description": task_description,
        "acceptance_criteria": current_task.get("acceptance_criteria", []),
        "dependencies": current_task.get("dependencies", []),
        "project_context": state.get("project_context", {}),
        "repository_url": state.get("repository_url"),
        "branch_name": current_task.get("branch_name", f"task/{task_id}")
    }
    
    # Submit the task to codegen
    try:
        execution_id = codegen_client.submit_task(
            task_description=task_description,
            context=execution_context
        )
        
        logger.info(f"Submitted task to codegen. Execution ID: {execution_id}")
        
        # Update the state with the execution ID and proceed to polling
        return Command(
            update={
                "codegen_client": codegen_client,
                "codegen_execution_id": execution_id,
                "task_execution_status": "running",
                "messages": state.get("messages", []) + [AIMessage(content=f"Started execution of coding task: {task_description[:100]}...", name="initiate_codegen")]
            },
            goto="poll_codegen_status"
        )
        
    except Exception as e:
        logger.error(f"Error initiating codegen: {e}")
        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to initiate codegen. {e}", name="initiate_codegen")],
                "task_execution_status": "failed",
                "task_execution_error": f"Failed to initiate codegen: {e}"
            },
            goto="codegen_failure"
        )


def poll_codegen_status_node(state: State) -> Command[Literal["poll_codegen_status", "codegen_success", "codegen_failure"]]:
    """Poll the status of a codegen execution."""
    logger.info("Polling codegen status...")
    
    # Get the codegen client and execution ID
    codegen_client = state.get("codegen_client")
    execution_id = state.get("codegen_execution_id")
    
    if not codegen_client or not execution_id:
        logger.error("Missing codegen client or execution ID. Cannot poll status.")
        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content="Error: Missing codegen client or execution ID. Cannot poll status.", name="poll_codegen_status")],
                "task_execution_status": "failed",
                "task_execution_error": "Missing codegen client or execution ID."
            },
            goto="codegen_failure"
        )
    
    # Poll the status
    try:
        status = codegen_client.get_task_status(execution_id)
        logger.info(f"Codegen status: {status}")
        
        # Check if the execution is complete
        if status == "completed":
            # Get the execution result
            result = codegen_client.get_task_result(execution_id)
            
            # Update the state with the result and proceed to success
            return Command(
                update={
                    "codegen_result": result,
                    "task_execution_status": "completed",
                    "messages": state.get("messages", []) + [AIMessage(content=f"Coding task completed successfully.", name="poll_codegen_status")]
                },
                goto="codegen_success"
            )
            
        elif status == "failed":
            # Get the error message
            error = codegen_client.get_task_error(execution_id)
            
            # Update the state with the error and proceed to failure
            return Command(
                update={
                    "codegen_error": error,
                    "task_execution_status": "failed",
                    "task_execution_error": error,
                    "messages": state.get("messages", []) + [AIMessage(content=f"Coding task failed: {error}", name="poll_codegen_status")]
                },
                goto="codegen_failure"
            )
            
        else:
            # Still running, continue polling
            return Command(
                update={
                    "messages": state.get("messages", []) + [AIMessage(content=f"Coding task still running. Status: {status}", name="poll_codegen_status")]
                },
                goto="poll_codegen_status"
            )
            
    except Exception as e:
        logger.error(f"Error polling codegen status: {e}")
        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to poll codegen status. {e}", name="poll_codegen_status")],
                "task_execution_status": "failed",
                "task_execution_error": f"Failed to poll codegen status: {e}"
            },
            goto="codegen_failure"
        )


def task_orchestrator_node(state: State) -> Command[Literal["coding_dispatcher", "research_team", "coding_planner", "__end__"]]:
    """Orchestrate the execution of tasks in the plan."""
    logger.info("Task orchestrator orchestrating tasks...")
    
    # Get the tasks definition
    tasks_definition = state.get("tasks_definition")
    if not tasks_definition:
        logger.error("No tasks definition found in state. Cannot orchestrate.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No tasks definition found. Cannot orchestrate tasks.", name="task_orchestrator")]},
            goto="__end__"
        )
    
    # Get the current task index
    current_task_index = state.get("current_task_index", 0)
    
    # Check if we've completed all tasks
    if current_task_index >= len(tasks_definition):
        logger.info("All tasks completed. Ending workflow.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="All tasks completed successfully.", name="task_orchestrator")]},
            goto="__end__"
        )
    
    # Get the current task
    current_task = tasks_definition[current_task_index]
    
    # Check if the task has dependencies
    dependencies = current_task.get("dependencies", [])
    if dependencies:
        # Check if all dependencies are completed
        completed_tasks = state.get("completed_tasks", [])
        for dependency in dependencies:
            if dependency not in completed_tasks:
                logger.info(f"Task {current_task.get('id')} has unmet dependency: {dependency}. Re-planning.")
                return Command(
                    update={
                        "messages": state.get("messages", []) + [AIMessage(content=f"Task {current_task.get('id')} has unmet dependency: {dependency}. Re-planning.", name="task_orchestrator")],
                        "failed_task_details": {
                            "id": current_task.get("id"),
                            "description": current_task.get("description"),
                            "failure_reason": f"Unmet dependency: {dependency}"
                        }
                    },
                    goto="coding_planner"
                )
    
    # Check if the task requires research
    if current_task.get("type") == "research":
        logger.info(f"Task {current_task.get('id')} requires research. Routing to research team.")
        return Command(
            update={
                "current_task": current_task,
                "research_return_to": "task_orchestrator"
            },
            goto="research_team"
        )
    
    # Route to the coding dispatcher for coding tasks
    logger.info(f"Task {current_task.get('id')} is ready for execution. Routing to coding dispatcher.")
    return Command(
        update={"current_task": current_task},
        goto="coding_dispatcher"
    )


def codegen_success_node(state: State) -> Command[Literal["task_orchestrator"]]:
    """Handle successful completion of a codegen execution."""
    logger.info("Codegen execution completed successfully.")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot process success.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot process success.", name="codegen_success")]},
            goto="task_orchestrator"
        )
    
    # Get the task ID
    task_id = current_task.get("id")
    
    # Update the completed tasks list
    completed_tasks = state.get("completed_tasks", [])
    completed_tasks.append(task_id)
    
    # Increment the current task index
    current_task_index = state.get("current_task_index", 0) + 1
    
    # Update the state and proceed to the next task
    return Command(
        update={
            "completed_tasks": completed_tasks,
            "current_task_index": current_task_index,
            "current_task": None,
            "messages": state.get("messages", []) + [AIMessage(content=f"Task {task_id} completed successfully.", name="codegen_success")]
        },
        goto="task_orchestrator"
    )


def codegen_failure_node(state: State) -> Command[Literal["coding_planner", "task_orchestrator"]]:
    """Handle failure of a codegen execution."""
    logger.info("Codegen execution failed.")
    
    # Get the current task
    current_task = state.get("current_task")
    if not current_task:
        logger.error("No current task found in state. Cannot process failure.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No current task found. Cannot process failure.", name="codegen_failure")]},
            goto="task_orchestrator"
        )
    
    # Get the task ID and error
    task_id = current_task.get("id")
    error = state.get("task_execution_error", "Unknown error")
    
    # Check if we should retry the task
    max_retries = current_task.get("max_retries", 1)
    retries = state.get("task_retries", {}).get(task_id, 0)
    
    if retries < max_retries:
        # Increment the retry count
        task_retries = state.get("task_retries", {})
        task_retries[task_id] = retries + 1
        
        logger.info(f"Retrying task {task_id}. Retry {retries + 1} of {max_retries}.")
        
        # Update the state and retry the task
        return Command(
            update={
                "task_retries": task_retries,
                "messages": state.get("messages", []) + [AIMessage(content=f"Task {task_id} failed: {error}. Retrying ({retries + 1}/{max_retries}).", name="codegen_failure")]
            },
            goto="task_orchestrator"
        )
    else:
        logger.info(f"Task {task_id} failed after {retries} retries. Re-planning.")
        
        # Update the state and re-plan
        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content=f"Task {task_id} failed after {retries} retries: {error}. Re-planning.", name="codegen_failure")],
                "failed_task_details": {
                    "id": task_id,
                    "description": current_task.get("description"),
                    "failure_reason": error
                }
            },
            goto="coding_planner"
        )

