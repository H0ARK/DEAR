# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Dict, List, Optional, Any
import requests

from .task import LinearTask
from .project import LinearProject

logger = logging.getLogger(__name__)

class LinearService:
    """Service for interacting with the Linear API."""
    
    def __init__(self, api_key: str = None, team_id: Optional[str] = None):
        """Initialize the Linear service.
        
        Args:
            api_key: The Linear API key. If not provided, will try to get from environment.
            team_id: The default team ID to use for operations.
        """
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY")
        if not self.api_key:
            logger.warning("No Linear API key provided. Linear integration will not work.")
        
        self.team_id = team_id or os.environ.get("LINEAR_TEAM_ID")
        if not self.team_id:
            logger.warning("No Linear team ID provided. Will try to get from API or use default.")
        
        self.api_url = "https://api.linear.app/graphql"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
        }
    
    def create_task(self, title: str, description: str, team_id: Optional[str] = None,
                   assignee_id: Optional[str] = None, priority: Optional[int] = None,
                   parent_id: Optional[str] = None, project_id: Optional[str] = None,
                   labels: Optional[List[str]] = None) -> LinearTask:
        """Create a task in Linear.
        
        Args:
            title: The title of the task.
            description: The description of the task.
            team_id: The ID of the team to create the task in. Defaults to the service's team_id.
            assignee_id: The ID of the user to assign the task to.
            priority: The priority of the task (0-4).
            parent_id: The ID of the parent task (epic).
            project_id: The ID of the project to add the task to.
            labels: A list of label IDs to add to the task.
            
        Returns:
            The created task.
        """
        if not self.api_key:
            logger.error("Cannot create task: No Linear API key provided.")
            raise ValueError("No Linear API key provided.")
        
        team_id = team_id or self.team_id
        if not team_id:
            logger.error("Cannot create task: No team ID provided.")
            raise ValueError("No team ID provided.")
        
        # Prepare the mutation
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    title
                    description
                    state {
                        id
                        name
                    }
                    assignee {
                        id
                    }
                    team {
                        id
                    }
                    priority
                    parent {
                        id
                    }
                    createdAt
                    updatedAt
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                    project {
                        id
                    }
                }
            }
        }
        """
        
        # Prepare the variables
        variables = {
            "input": {
                "title": title,
                "description": description,
                "teamId": team_id,
            }
        }
        
        if assignee_id:
            variables["input"]["assigneeId"] = assignee_id
        
        if priority is not None:
            variables["input"]["priority"] = priority
        
        if parent_id:
            variables["input"]["parentId"] = parent_id
        
        if project_id:
            variables["input"]["projectId"] = project_id
        
        if labels:
            variables["input"]["labelIds"] = labels
        
        # Make the request
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={"query": mutation, "variables": variables},
        )
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Error creating task: {response.text}")
            raise Exception(f"Error creating task: {response.text}")
        
        data = response.json()
        if "errors" in data:
            logger.error(f"Error creating task: {data['errors']}")
            raise Exception(f"Error creating task: {data['errors']}")
        
        # Extract the task data
        issue_data = data["data"]["issueCreate"]["issue"]
        
        # Create and return the task
        return LinearTask(
            id=issue_data["id"],
            title=issue_data["title"],
            description=issue_data["description"],
            state=issue_data["state"]["name"],
            assignee_id=issue_data["assignee"]["id"] if issue_data["assignee"] else None,
            team_id=issue_data["team"]["id"],
            priority=issue_data["priority"],
            parent_id=issue_data["parent"]["id"] if issue_data["parent"] else None,
            created_at=issue_data["createdAt"],
            updated_at=issue_data["updatedAt"],
            labels=[label["id"] for label in issue_data["labels"]["nodes"]] if issue_data["labels"]["nodes"] else [],
            project_id=issue_data["project"]["id"] if issue_data["project"] else None,
        )
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> LinearTask:
        """Update a task in Linear.
        
        Args:
            task_id: The ID of the task to update.
            updates: A dictionary of updates to apply to the task.
            
        Returns:
            The updated task.
        """
        if not self.api_key:
            logger.error("Cannot update task: No Linear API key provided.")
            raise ValueError("No Linear API key provided.")
        
        # Prepare the mutation
        mutation = """
        mutation UpdateIssue($id: ID!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    title
                    description
                    state {
                        id
                        name
                    }
                    assignee {
                        id
                    }
                    team {
                        id
                    }
                    priority
                    parent {
                        id
                    }
                    createdAt
                    updatedAt
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                    project {
                        id
                    }
                }
            }
        }
        """
        
        # Prepare the variables
        variables = {
            "id": task_id,
            "input": updates,
        }
        
        # Make the request
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={"query": mutation, "variables": variables},
        )
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Error updating task: {response.text}")
            raise Exception(f"Error updating task: {response.text}")
        
        data = response.json()
        if "errors" in data:
            logger.error(f"Error updating task: {data['errors']}")
            raise Exception(f"Error updating task: {data['errors']}")
        
        # Extract the task data
        issue_data = data["data"]["issueUpdate"]["issue"]
        
        # Create and return the task
        return LinearTask(
            id=issue_data["id"],
            title=issue_data["title"],
            description=issue_data["description"],
            state=issue_data["state"]["name"],
            assignee_id=issue_data["assignee"]["id"] if issue_data["assignee"] else None,
            team_id=issue_data["team"]["id"],
            priority=issue_data["priority"],
            parent_id=issue_data["parent"]["id"] if issue_data["parent"] else None,
            created_at=issue_data["createdAt"],
            updated_at=issue_data["updatedAt"],
            labels=[label["id"] for label in issue_data["labels"]["nodes"]] if issue_data["labels"]["nodes"] else [],
            project_id=issue_data["project"]["id"] if issue_data["project"] else None,
        )
    
    def update_task_with_github_info(self, task_id: str, branch_name: str, pr_url: Optional[str] = None) -> LinearTask:
        """Update a task with GitHub information.
        
        Args:
            task_id: The ID of the task to update.
            branch_name: The name of the branch.
            pr_url: The URL of the pull request.
            
        Returns:
            The updated task.
        """
        updates = {
            "branchName": branch_name,
        }
        
        if pr_url:
            updates["description"] = f"PR: {pr_url}\n\n" + self.get_task(task_id).description
        
        return self.update_task(task_id, updates)
    
    def get_task(self, task_id: str) -> LinearTask:
        """Get a task from Linear.
        
        Args:
            task_id: The ID of the task to get.
            
        Returns:
            The task.
        """
        if not self.api_key:
            logger.error("Cannot get task: No Linear API key provided.")
            raise ValueError("No Linear API key provided.")
        
        # Prepare the query
        query = """
        query GetIssue($id: ID!) {
            issue(id: $id) {
                id
                title
                description
                state {
                    id
                    name
                }
                assignee {
                    id
                }
                team {
                    id
                }
                priority
                parent {
                    id
                }
                createdAt
                updatedAt
                labels {
                    nodes {
                        id
                        name
                    }
                }
                project {
                    id
                }
                branchName
                completed
            }
        }
        """
        
        # Prepare the variables
        variables = {
            "id": task_id,
        }
        
        # Make the request
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={"query": query, "variables": variables},
        )
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Error getting task: {response.text}")
            raise Exception(f"Error getting task: {response.text}")
        
        data = response.json()
        if "errors" in data:
            logger.error(f"Error getting task: {data['errors']}")
            raise Exception(f"Error getting task: {data['errors']}")
        
        # Extract the task data
        issue_data = data["data"]["issue"]
        
        # Create and return the task
        return LinearTask(
            id=issue_data["id"],
            title=issue_data["title"],
            description=issue_data["description"],
            state=issue_data["state"]["name"],
            assignee_id=issue_data["assignee"]["id"] if issue_data["assignee"] else None,
            team_id=issue_data["team"]["id"],
            priority=issue_data["priority"],
            parent_id=issue_data["parent"]["id"] if issue_data["parent"] else None,
            created_at=issue_data["createdAt"],
            updated_at=issue_data["updatedAt"],
            labels=[label["id"] for label in issue_data["labels"]["nodes"]] if issue_data["labels"]["nodes"] else [],
            project_id=issue_data["project"]["id"] if issue_data["project"] else None,
            branch_name=issue_data["branchName"],
            completed=issue_data["completed"],
        )
    
    def create_project(self, name: str, description: str = "", team_ids: Optional[List[str]] = None,
                      start_date: Optional[str] = None, target_date: Optional[str] = None) -> LinearProject:
        """Create a project in Linear.
        
        Args:
            name: The name of the project.
            description: The description of the project.
            team_ids: The IDs of the teams to add to the project.
            start_date: The start date of the project (ISO format).
            target_date: The target date of the project (ISO format).
            
        Returns:
            The created project.
        """
        if not self.api_key:
            logger.error("Cannot create project: No Linear API key provided.")
            raise ValueError("No Linear API key provided.")
        
        team_ids = team_ids or [self.team_id] if self.team_id else []
        if not team_ids:
            logger.error("Cannot create project: No team IDs provided.")
            raise ValueError("No team IDs provided.")
        
        # Prepare the mutation
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    description
                    state
                    teams {
                        nodes {
                            id
                        }
                    }
                    createdAt
                    updatedAt
                    startDate
                    targetDate
                    completedAt
                }
            }
        }
        """
        
        # Prepare the variables
        variables = {
            "input": {
                "name": name,
                "description": description,
                "teamIds": team_ids,
            }
        }
        
        if start_date:
            variables["input"]["startDate"] = start_date
        
        if target_date:
            variables["input"]["targetDate"] = target_date
        
        # Make the request
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={"query": mutation, "variables": variables},
        )
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Error creating project: {response.text}")
            raise Exception(f"Error creating project: {response.text}")
        
        data = response.json()
        if "errors" in data:
            logger.error(f"Error creating project: {data['errors']}")
            raise Exception(f"Error creating project: {data['errors']}")
        
        # Extract the project data
        project_data = data["data"]["projectCreate"]["project"]
        
        # Create and return the project
        return LinearProject(
            id=project_data["id"],
            name=project_data["name"],
            description=project_data["description"],
            state=project_data["state"],
            team_ids=[team["id"] for team in project_data["teams"]["nodes"]],
            created_at=project_data["createdAt"],
            updated_at=project_data["updatedAt"],
            start_date=project_data["startDate"],
            target_date=project_data["targetDate"],
            completed_at=project_data["completedAt"],
            completed=bool(project_data["completedAt"]),
        )

