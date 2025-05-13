# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from .common import *

def linear_integration_node(state: State, config: RunnableConfig) -> Command[Literal["task_orchestrator"]]:
    """Node that integrates with Linear to create tasks."""
    logger.info("Integrating with Linear...")
    
    # Get the tasks definition
    tasks_definition = state.get("tasks_definition", [])
    if not tasks_definition:
        logger.error("No tasks definition found in state. Cannot integrate with Linear.")
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content="Error: No tasks definition found. Cannot integrate with Linear.", name="linear_integration")]
            },
            goto="__end__"
        )
    
    # Check if Linear integration is enabled
    configurable = Configuration.from_runnable_config(config)
    linear_enabled = configurable.linear_enabled
    
    if not linear_enabled:
        logger.info("Linear integration is disabled. Skipping Linear integration.")
        return Command(update=state, goto="task_orchestrator")
    
    # Get the Linear service
    try:
        linear_service = LinearService()
    except Exception as e:
        logger.error(f"Error initializing Linear service: {e}")
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=f"Error initializing Linear service: {e}", name="linear_integration")]
            },
            goto="task_orchestrator"  # Continue to task orchestrator even if Linear integration fails
        )
    
    # Create a project in Linear
    project_name = state.get("project_name", "Untitled Project")
    try:
        project = linear_service.create_project(project_name)
        logger.info(f"Created Linear project: {project_name}")
    except Exception as e:
        logger.error(f"Error creating Linear project: {e}")
        project = None
    
    # Create tasks in Linear
    linear_tasks = []
    for task in tasks_definition:
        try:
            # Create the task in Linear
            linear_task = linear_service.create_task(
                title=task.get("name", "Untitled Task"),
                description=task.get("description", ""),
                project_id=project.id if project else None
            )
            
            # Store the Linear task ID in the task definition
            task["linear_id"] = linear_task.id
            
            linear_tasks.append(linear_task)
            logger.info(f"Created Linear task: {task.get('name')}")
        except Exception as e:
            logger.error(f"Error creating Linear task: {e}")
            # Continue with the next task even if this one fails
    
    # Update the state with the Linear integration results
    state["linear_project"] = project.to_dict() if project else None
    state["linear_tasks"] = [task.to_dict() for task in linear_tasks]
    
    # Add a message about the Linear integration
    if project and linear_tasks:
        message = f"Successfully created Linear project '{project_name}' with {len(linear_tasks)} tasks."
    elif linear_tasks:
        message = f"Successfully created {len(linear_tasks)} Linear tasks."
    else:
        message = "Failed to create Linear project or tasks."
    
    state["messages"] = state.get("messages", []) + [AIMessage(content=message, name="linear_integration")]
    
    # Proceed to task orchestrator
    return Command(update=state, goto="task_orchestrator")

