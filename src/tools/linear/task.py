# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class LinearTask:
    """Representation of a task in Linear."""
    id: str
    title: str
    description: str
    state: str
    assignee_id: Optional[str] = None
    team_id: Optional[str] = None
    priority: Optional[int] = None
    branch_name: Optional[str] = None
    github_pr_url: Optional[str] = None
    parent_id: Optional[str] = None  # ID of parent issue (epic)
    completed: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    labels: List[str] = None
    project_id: Optional[str] = None
    url: Optional[str] = None  # URL to the task in Linear

    def __post_init__(self):
        if self.labels is None:
            self.labels = []
            
    @classmethod
    def from_api_response(cls, data: dict) -> 'LinearTask':
        """Create a LinearTask instance from an API response."""
        task_id = data.get('id')
        title = data.get('title', '')
        description = data.get('description', '')
        state = data.get('state', {}).get('name', 'Unknown')
        
        # Extract other fields
        assignee_id = data.get('assignee', {}).get('id') if data.get('assignee') else None
        team_id = data.get('team', {}).get('id') if data.get('team') else None
        priority = data.get('priority')
        branch_name = data.get('branchName')
        
        # Extract PR URL from integrations if available
        github_pr_url = None
        if data.get('integrations'):
            for integration in data.get('integrations', []):
                if integration.get('type') == 'github' and integration.get('url'):
                    github_pr_url = integration.get('url')
                    break
        
        # Extract parent ID if available
        parent_id = data.get('parent', {}).get('id') if data.get('parent') else None
        
        # Extract completion status
        completed = data.get('completedAt') is not None
        
        # Extract timestamps
        created_at = data.get('createdAt')
        updated_at = data.get('updatedAt')
        
        # Extract labels
        labels = []
        if data.get('labels', {}).get('nodes'):
            labels = [label.get('name') for label in data.get('labels', {}).get('nodes', [])]
        
        # Extract project ID
        project_id = data.get('project', {}).get('id') if data.get('project') else None
        
        # Extract URL
        url = data.get('url')
        
        return cls(
            id=task_id,
            title=title,
            description=description,
            state=state,
            assignee_id=assignee_id,
            team_id=team_id,
            priority=priority,
            branch_name=branch_name,
            github_pr_url=github_pr_url,
            parent_id=parent_id,
            completed=completed,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            project_id=project_id,
            url=url
        )
        
    def to_dict(self) -> dict:
        """Convert the task to a dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'state': self.state,
            'assignee_id': self.assignee_id,
            'team_id': self.team_id,
            'priority': self.priority,
            'branch_name': self.branch_name,
            'github_pr_url': self.github_pr_url,
            'parent_id': self.parent_id,
            'completed': self.completed,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'labels': self.labels,
            'project_id': self.project_id,
            'url': self.url
        }

