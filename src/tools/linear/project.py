# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class LinearProject:
    """Representation of a project in Linear."""
    id: str
    name: str
    description: str
    state: str
    team_ids: List[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    completed_at: Optional[str] = None
    completed: bool = False
    url: Optional[str] = None  # URL to the project in Linear
    
    def __post_init__(self):
        if self.team_ids is None:
            self.team_ids = []
            
    @classmethod
    def from_api_response(cls, data: dict) -> 'LinearProject':
        """Create a LinearProject instance from an API response."""
        project_id = data.get('id')
        name = data.get('name', '')
        description = data.get('description', '')
        state = data.get('state', 'Unknown')
        
        # Extract team IDs
        team_ids = []
        if data.get('teams', {}).get('nodes'):
            team_ids = [team.get('id') for team in data.get('teams', {}).get('nodes', [])]
        
        # Extract timestamps
        created_at = data.get('createdAt')
        updated_at = data.get('updatedAt')
        start_date = data.get('startDate')
        target_date = data.get('targetDate')
        completed_at = data.get('completedAt')
        
        # Extract completion status
        completed = completed_at is not None
        
        # Extract URL
        url = data.get('url')
        
        return cls(
            id=project_id,
            name=name,
            description=description,
            state=state,
            team_ids=team_ids,
            created_at=created_at,
            updated_at=updated_at,
            start_date=start_date,
            target_date=target_date,
            completed_at=completed_at,
            completed=completed,
            url=url
        )
        
    def to_dict(self) -> dict:
        """Convert the project to a dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'state': self.state,
            'team_ids': self.team_ids,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'start_date': self.start_date,
            'target_date': self.target_date,
            'completed_at': self.completed_at,
            'completed': self.completed,
            'url': self.url
        }

