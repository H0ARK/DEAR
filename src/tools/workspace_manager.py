# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
import subprocess
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class WorkspaceInfo:
    """Information about a workspace."""
    id: str
    branch_name: str
    base_branch: str
    created_at: str
    description: str
    status: str = "active"  # active, completed, abandoned
    linear_project_id: Optional[str] = None
    github_feature_branch: Optional[str] = None

class WorkspaceManager:
    """Manages isolated workspaces for agent sessions."""
    
    def __init__(self, repo_path: str):
        """Initialize the workspace manager.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.workspaces: Dict[str, WorkspaceInfo] = {}
        logger.info(f"Initialized workspace manager for {repo_path}")
    
    def create_workspace(self, description: str = "Agent workspace") -> WorkspaceInfo:
        """Create a new workspace with an isolated branch.
        
        Args:
            description: Description of the workspace
            
        Returns:
            WorkspaceInfo object for the created workspace
        """
        # Generate a unique ID for the workspace
        workspace_id = str(uuid.uuid4())[:8]
        
        # Get the current branch to use as base
        base_branch = self._get_current_branch()
        
        # Create a unique branch name for this workspace
        branch_name = f"workspace/{workspace_id}"
        
        try:
            # Create the branch
            self._create_branch(branch_name, base_branch)
            
            # Record the creation time
            from datetime import datetime
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Create workspace info
            workspace = WorkspaceInfo(
                id=workspace_id,
                branch_name=branch_name,
                base_branch=base_branch,
                created_at=created_at,
                description=description
            )
            
            # Store the workspace
            self.workspaces[workspace_id] = workspace
            
            logger.info(f"Created workspace {workspace_id} with branch {branch_name}")
            return workspace
            
        except Exception as e:
            logger.error(f"Error creating workspace: {e}")
            raise
    
    def switch_to_workspace(self, workspace_id: str) -> bool:
        """Switch to a workspace branch.
        
        Args:
            workspace_id: ID of the workspace to switch to
            
        Returns:
            True if successful
        """
        if workspace_id not in self.workspaces:
            logger.error(f"Workspace {workspace_id} not found")
            return False
        
        workspace = self.workspaces[workspace_id]
        
        try:
            # Check if we need to stash changes
            has_changes = self._has_uncommitted_changes()
            
            if has_changes:
                logger.info("Stashing uncommitted changes")
                self._run_git_command(['stash', 'push', '-m', f"Auto-stash before switching to {workspace.branch_name}"])
            
            # Switch to the workspace branch
            self._run_git_command(['checkout', workspace.branch_name])
            
            logger.info(f"Switched to workspace {workspace_id} (branch {workspace.branch_name})")
            return True
            
        except Exception as e:
            logger.error(f"Error switching to workspace {workspace_id}: {e}")
            return False
    
    def get_workspace(self, workspace_id: str) -> Optional[WorkspaceInfo]:
        """Get information about a workspace.
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            WorkspaceInfo object, or None if not found
        """
        return self.workspaces.get(workspace_id)
    
    def list_workspaces(self) -> List[WorkspaceInfo]:
        """List all workspaces.
        
        Returns:
            List of WorkspaceInfo objects
        """
        return list(self.workspaces.values())
    
    def _get_current_branch(self) -> str:
        """Get the current Git branch.
        
        Returns:
            Name of the current branch
        """
        try:
            result = self._run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'])
            return result.strip()
        except Exception as e:
            logger.error(f"Error getting current branch: {e}")
            return "main"  # Default to main if we can't determine the current branch
    
    def _create_branch(self, branch_name: str, base_branch: str) -> None:
        """Create a new Git branch.
        
        Args:
            branch_name: Name of the branch to create
            base_branch: Base branch to create from
        """
        # First, make sure we're on the base branch
        self._run_git_command(['checkout', base_branch])
        
        # Create the new branch
        self._run_git_command(['checkout', '-b', branch_name])
    
    def _has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes.
        
        Returns:
            True if there are uncommitted changes
        """
        result = self._run_git_command(['status', '--porcelain'])
        return bool(result.strip())
    
    def _run_git_command(self, args: List[str]) -> str:
        """Run a Git command.
        
        Args:
            args: Command arguments (without 'git')
            
        Returns:
            Command output
        """
        cmd = ['git'] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}")
            logger.error(f"Error output: {e.stderr}")
            raise
