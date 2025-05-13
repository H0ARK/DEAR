# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the project to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "state": self.state,
            "team_ids": self.team_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "start_date": self.start_date,
            "target_date": self.target_date,
            "completed_at": self.completed_at,
            "completed": self.completed,
        }

