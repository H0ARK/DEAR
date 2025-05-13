# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
import requests
from typing import Dict, List, Optional, Any

from .task import LinearTask
from .project import LinearProject

logger = logging.getLogger(__name__)

class LinearService:
    """Service for interacting with Linear API."""

    def __init__(self, api_key: str, team_id: Optional[str] = None):
        """Initialize the Linear service.
        
        Args:
            api_key: Linear API key
            team_id: Optional default team ID
        """
        self.api_key = api_key
        self.team_id = team_id
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": f"{api_key}",
            "Content-Type": "application/json"
        }
        
    def execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against the Linear API.
        
        Args:
            query: GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            Response data from the API
        """
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        response = requests.post(
            self.base_url,
            json=payload,
            headers=self.headers
        )
        
        if response.status_code != 200:
            logger.error(f"Error executing query: {response.status_code} - {response.text}")
            response.raise_for_status()
            
        data = response.json()
        
        if "errors" in data:
            logger.error(f"GraphQL errors: {data['errors']}")
            raise Exception(f"GraphQL errors: {data['errors']}")
            
        return data.get("data", {})
    
    def get_teams(self) -> List[Dict[str, Any]]:
        """Get all teams the user has access to.
        
        Returns:
            List of team objects
        """
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    key
                    description
                }
            }
        }
        """
        
        data = self.execute_query(query)
        return data.get("teams", {}).get("nodes", [])
    
    def get_team(self, team_id: Optional[str] = None) -> Dict[str, Any]:
        """Get a specific team by ID.
        
        Args:
            team_id: ID of the team to get. If not provided, uses the default team ID.
            
        Returns:
            Team object
        """
        team_id = team_id or self.team_id
        if not team_id:
            raise ValueError("No team ID provided and no default team ID set.")
            
        query = """
        query GetTeam($id: ID!) {
            team(id: $id) {
                id
                name
                key
                description
                states {
                    nodes {
                        id
                        name
                        type
                        color
                    }
                }
            }
        }
        """
        
        variables = {"id": team_id}
        data = self.execute_query(query, variables)
        return data.get("team", {})
    
    def create_task(self, title: str, description: str, team_id: Optional[str] = None, 
                   assignee_id: Optional[str] = None, priority: Optional[int] = None,
                   parent_id: Optional[str] = None, project_id: Optional[str] = None) -> LinearTask:
        """Create a new task in Linear.
        
        Args:
            title: Title of the task
            description: Description of the task
            team_id: ID of the team to create the task in. If not provided, uses the default team ID.
            assignee_id: Optional ID of the user to assign the task to
            priority: Optional priority of the task (0-4)
            parent_id: Optional ID of the parent issue (epic)
            project_id: Optional ID of the project to add the task to
            
        Returns:
            Created task object
        """
        team_id = team_id or self.team_id
        if not team_id:
            raise ValueError("No team ID provided and no default team ID set.")
            
        query = """
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
                        name
                    }
                    team {
                        id
                        name
                    }
                    priority
                    parent {
                        id
                    }
                    project {
                        id
                    }
                    createdAt
                    updatedAt
                    url
                }
            }
        }
        """
        
        variables = {
            "input": {
                "title": title,
                "description": description,
                "teamId": team_id,
                "priority": priority
            }
        }
        
        if assignee_id:
            variables["input"]["assigneeId"] = assignee_id
            
        if parent_id:
            variables["input"]["parentId"] = parent_id
            
        if project_id:
            variables["input"]["projectId"] = project_id
            
        data = self.execute_query(query, variables)
        issue_data = data.get("issueCreate", {}).get("issue", {})
        
        return LinearTask.from_api_response(issue_data)
    
    def get_task(self, task_id: str) -> LinearTask:
        """Get a specific task by ID.
        
        Args:
            task_id: ID of the task to get
            
        Returns:
            Task object
        """
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
                    name
                }
                team {
                    id
                    name
                }
                priority
                parent {
                    id
                }
                project {
                    id
                }
                createdAt
                updatedAt
                completedAt
                labels {
                    nodes {
                        id
                        name
                    }
                }
                url
            }
        }
        """
        
        variables = {"id": task_id}
        data = self.execute_query(query, variables)
        issue_data = data.get("issue", {})
        
        return LinearTask.from_api_response(issue_data)
    
    def update_task(self, task_id: str, title: Optional[str] = None, description: Optional[str] = None,
                   state_id: Optional[str] = None, assignee_id: Optional[str] = None,
                   priority: Optional[int] = None, project_id: Optional[str] = None) -> LinearTask:
        """Update an existing task in Linear.
        
        Args:
            task_id: ID of the task to update
            title: Optional new title for the task
            description: Optional new description for the task
            state_id: Optional new state ID for the task
            assignee_id: Optional new assignee ID for the task
            priority: Optional new priority for the task
            project_id: Optional new project ID for the task
            
        Returns:
            Updated task object
        """
        query = """
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
                        name
                    }
                    team {
                        id
                        name
                    }
                    priority
                    parent {
                        id
                    }
                    project {
                        id
                    }
                    createdAt
                    updatedAt
                    completedAt
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                    url
                }
            }
        }
        """
        
        variables = {
            "id": task_id,
            "input": {}
        }
        
        if title is not None:
            variables["input"]["title"] = title
            
        if description is not None:
            variables["input"]["description"] = description
            
        if state_id is not None:
            variables["input"]["stateId"] = state_id
            
        if assignee_id is not None:
            variables["input"]["assigneeId"] = assignee_id
            
        if priority is not None:
            variables["input"]["priority"] = priority
            
        if project_id is not None:
            variables["input"]["projectId"] = project_id
            
        data = self.execute_query(query, variables)
        issue_data = data.get("issueUpdate", {}).get("issue", {})
        
        return LinearTask.from_api_response(issue_data)
    
    def create_project(self, name: str, description: str, team_id: Optional[str] = None,
                      start_date: Optional[str] = None, target_date: Optional[str] = None) -> LinearProject:
        """Create a new project in Linear.
        
        Args:
            name: Name of the project
            description: Description of the project
            team_id: ID of the team to create the project in. If not provided, uses the default team ID.
            start_date: Optional start date for the project (ISO format)
            target_date: Optional target date for the project (ISO format)
            
        Returns:
            Created project object
        """
        team_id = team_id or self.team_id
        if not team_id:
            raise ValueError("No team ID provided and no default team ID set.")
            
        query = """
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
                            name
                        }
                    }
                    createdAt
                    updatedAt
                    startDate
                    targetDate
                    completedAt
                    url
                }
            }
        }
        """
        
        variables = {
            "input": {
                "name": name,
                "description": description,
                "teamIds": [team_id]
            }
        }
        
        if start_date:
            variables["input"]["startDate"] = start_date
            
        if target_date:
            variables["input"]["targetDate"] = target_date
            
        data = self.execute_query(query, variables)
        project_data = data.get("projectCreate", {}).get("project", {})
        
        return LinearProject.from_api_response(project_data)
    
    def get_project(self, project_id: str) -> LinearProject:
        """Get a specific project by ID.
        
        Args:
            project_id: ID of the project to get
            
        Returns:
            Project object
        """
        query = """
        query GetProject($id: ID!) {
            project(id: $id) {
                id
                name
                description
                state
                teams {
                    nodes {
                        id
                        name
                    }
                }
                createdAt
                updatedAt
                startDate
                targetDate
                completedAt
                url
            }
        }
        """
        
        variables = {"id": project_id}
        data = self.execute_query(query, variables)
        project_data = data.get("project", {})
        
        return LinearProject.from_api_response(project_data)
    
    def add_task_to_project(self, task_id: str, project_id: str) -> LinearTask:
        """Add a task to a project.
        
        Args:
            task_id: ID of the task to add
            project_id: ID of the project to add the task to
            
        Returns:
            Updated task object
        """
        return self.update_task(task_id, project_id=project_id)
    
    def add_task_dependency(self, task_id: str, dependency_id: str) -> bool:
        """Add a dependency relationship between two tasks.
        
        Args:
            task_id: ID of the task that depends on another
            dependency_id: ID of the task that is depended upon
            
        Returns:
            True if successful, False otherwise
        """
        query = """
        mutation CreateIssueDependency($input: IssueDependencyCreateInput!) {
            issueDependencyCreate(input: $input) {
                success
            }
        }
        """
        
        variables = {
            "input": {
                "issueId": task_id,
                "dependencyId": dependency_id
            }
        }
        
        data = self.execute_query(query, variables)
        return data.get("issueDependencyCreate", {}).get("success", False)
    
    def get_task_dependencies(self, task_id: str) -> Dict[str, List[str]]:
        """Get dependencies for a task.
        
        Args:
            task_id: ID of the task to get dependencies for
            
        Returns:
            Dictionary with "depends_on" and "depended_by" lists of task IDs
        """
        query = """
        query GetIssueDependencies($id: ID!) {
            issue(id: $id) {
                dependencies {
                    nodes {
                        id
                        dependencyId
                    }
                }
                dependents {
                    nodes {
                        id
                        issueId
                    }
                }
            }
        }
        """
        
        variables = {"id": task_id}
        data = self.execute_query(query, variables)
        issue_data = data.get("issue", {})
        
        depends_on = []
        if issue_data.get("dependencies", {}).get("nodes"):
            depends_on = [dep.get("dependencyId") for dep in issue_data.get("dependencies", {}).get("nodes", [])]
            
        depended_by = []
        if issue_data.get("dependents", {}).get("nodes"):
            depended_by = [dep.get("issueId") for dep in issue_data.get("dependents", {}).get("nodes", [])]
            
        return {
            "depends_on": depends_on,
            "depended_by": depended_by
        }
    
    def get_project_tasks(self, project_id: str) -> List[LinearTask]:
        """Get all tasks in a project.
        
        Args:
            project_id: ID of the project to get tasks for
            
        Returns:
            List of task objects
        """
        query = """
        query GetProjectIssues($id: ID!) {
            project(id: $id) {
                issues {
                    nodes {
                        id
                        title
                        description
                        state {
                            id
                            name
                        }
                        assignee {
                            id
                            name
                        }
                        team {
                            id
                            name
                        }
                        priority
                        parent {
                            id
                        }
                        project {
                            id
                        }
                        createdAt
                        updatedAt
                        completedAt
                        labels {
                            nodes {
                                id
                                name
                            }
                        }
                        url
                    }
                }
            }
        }
        """
        
        variables = {"id": project_id}
        data = self.execute_query(query, variables)
        issues_data = data.get("project", {}).get("issues", {}).get("nodes", [])
        
        return [LinearTask.from_api_response(issue) for issue in issues_data]

