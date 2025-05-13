#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from src.tools.linear_service import LinearService

# Load environment variables from .env file
load_dotenv()

def main():
    # Initialize Linear service
    api_key = os.getenv("LINEAR_API_KEY")
    team_id = os.getenv("LINEAR_TEAM_ID")
    linear_service = LinearService(api_key=api_key, team_id=team_id)

    # Get all projects
    print("\n=== Getting all projects ===")
    projects = linear_service.get_projects()
    print(f"Found {len(projects)} projects:")
    for project in projects:
        print(f"- {project.name} (ID: {project.id})")

    # Test filter_or_create_project
    project_name = "Test Project"
    project_description = "A test project created by the filter_or_create_project function"

    print(f"\n=== Filtering or creating project '{project_name}' ===")
    project = linear_service.filter_or_create_project(project_name, project_description)
    print(f"Project: {project.name} (ID: {project.id})")
    print(f"Description: {project.description}")
    print(f"State: {project.state}")
    print(f"Team IDs: {project.team_ids}")

    # Get all tasks
    print("\n=== Getting all tasks ===")
    tasks = linear_service.get_team_tasks()
    print(f"Found {len(tasks)} tasks")

    # Add a task to the project (if there are any tasks)
    if tasks:
        task = tasks[0]
        print(f"\n=== Adding task '{task.title}' to project '{project.name}' ===")
        updated_task = linear_service.add_task_to_project(task.id, project.id)
        print(f"Task: {updated_task.title} (ID: {updated_task.id})")
        print(f"Project ID: {updated_task.project_id}")
    else:
        print("\nNo tasks found to add to the project")

    # Get all tasks for the project
    print(f"\n=== Getting all tasks for project '{project.name}' ===")
    project_tasks = [task for task in tasks if task.project_id == project.id]
    print(f"Found {len(project_tasks)} tasks in the project")
    for task in project_tasks:
        print(f"- {task.title} (ID: {task.id})")

if __name__ == "__main__":
    main()
