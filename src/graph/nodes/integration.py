# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

def linear_integration_node(state: State) -> Command[Literal["task_orchestrator", "__end__"]]:
    """Integrate tasks with Linear project management."""
    logger.info("Integrating tasks with Linear...")
    
    # Get the tasks definition
    tasks_definition = state.get("tasks_definition")
    if not tasks_definition:
        logger.error("No tasks definition found in state. Cannot integrate with Linear.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No tasks definition found. Cannot integrate with Linear.", name="linear_integration")]},
            goto="__end__"
        )
    
    # Check if Linear integration is enabled
    linear_api_key = os.environ.get("LINEAR_API_KEY")
    linear_team_id = os.environ.get("LINEAR_TEAM_ID")
    
    if not linear_api_key:
        logger.info("Linear API key not found. Skipping Linear integration.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Linear integration is not configured. Proceeding with local task execution.", name="linear_integration")]},
            goto="task_orchestrator"
        )
    
    # Initialize Linear service
    try:
        linear_service = LinearService(api_key=linear_api_key, team_id=linear_team_id)
        logger.info("Initialized Linear service.")
        
        # Create a project for the tasks
        project_name = state.get("project_name", "DEAR Project")
        project_description = state.get("prd_document", "No PRD available.")[:1000]  # Truncate if too long
        
        project = linear_service.create_project(
            name=project_name,
            description=project_description
        )
        
        logger.info(f"Created Linear project: {project.id} - {project.name}")
        
        # Create tasks in Linear
        linear_tasks = []
        for task in tasks_definition:
            task_title = task.get("name", "Unnamed Task")
            task_description = task.get("description", "No description available.")
            
            # Format acceptance criteria
            acceptance_criteria = task.get("acceptance_criteria", [])
            formatted_criteria = ""
            if acceptance_criteria:
                formatted_criteria = "\n\n## Acceptance Criteria\n\n"
                for i, criterion in enumerate(acceptance_criteria):
                    formatted_criteria += f"{i+1}. {criterion}\n"
            
            # Create the task in Linear
            linear_task = linear_service.create_task(
                title=task_title,
                description=task_description + formatted_criteria,
                project_id=project.id
            )
            
            logger.info(f"Created Linear task: {linear_task.id} - {linear_task.title}")
            
            # Store the Linear task ID in the task definition
            task["linear_id"] = linear_task.id
            linear_tasks.append(linear_task)
        
        # Update dependencies in Linear
        for task in tasks_definition:
            dependencies = task.get("dependencies", [])
            if dependencies and task.get("linear_id"):
                for dependency in dependencies:
                    # Find the Linear task ID for the dependency
                    dependency_task = next((t for t in tasks_definition if t.get("id") == dependency), None)
                    if dependency_task and dependency_task.get("linear_id"):
                        # Add the dependency in Linear
                        linear_service.add_task_dependency(
                            task_id=task["linear_id"],
                            dependency_id=dependency_task["linear_id"]
                        )
                        logger.info(f"Added dependency: {task['linear_id']} depends on {dependency_task['linear_id']}")
        
        # Update the state with Linear integration info
        return Command(
            update={
                "linear_project_id": project.id,
                "linear_project_url": project.url,
                "tasks_definition": tasks_definition,  # Updated with Linear IDs
                "messages": state.get("messages", []) + [AIMessage(content=f"Tasks integrated with Linear project: {project.name}. You can view the project at {project.url}", name="linear_integration")]
            },
            goto="task_orchestrator"
        )
        
    except Exception as e:
        logger.error(f"Error integrating with Linear: {e}")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content=f"Error: Failed to integrate with Linear. {e}. Proceeding with local task execution.", name="linear_integration")]},
            goto="task_orchestrator"
        )

