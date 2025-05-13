# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

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

    def __post_init__(self):
        if self.labels is None:
            self.labels = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "assignee_id": self.assignee_id,
            "team_id": self.team_id,
            "priority": self.priority,
            "branch_name": self.branch_name,
            "github_pr_url": self.github_pr_url,
            "parent_id": self.parent_id,
            "completed": self.completed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "labels": self.labels,
            "project_id": self.project_id,
        }

