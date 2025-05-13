# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
from dataclasses import dataclass, fields
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig


@dataclass(kw_only=True)
class Configuration:
    """The configurable fields."""

    max_plan_iterations: int = 1  # Maximum number of plan iterations
    max_step_num: int = 3  # Maximum number of steps in a plan
    mcp_settings: dict = None  # MCP settings, including dynamic loaded tools
    create_workspace: bool = False  # Whether to create a workspace for each session
    workspace_path: Optional[str] = None  # Path to the workspace (repository root or new project indicator)
    linear_api_key: Optional[str] = None  # Linear API key
    linear_team_id: Optional[str] = None  # Linear team ID
    linear_project_name: Optional[str] = None  # Linear project name
    github_token: Optional[str] = None  # GitHub token
    force_interactive: bool = True  # Whether to force interactive mode for brief inputs

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )
        values: dict[str, Any] = {
            f.name: os.environ.get(f.name.upper(), configurable.get(f.name))
            for f in fields(cls)
            if f.init
        }
        return cls(**{k: v for k, v in values.items() if v})
