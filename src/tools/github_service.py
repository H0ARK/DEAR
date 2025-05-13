# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from github import Github, GithubException
from github.Repository import Repository
from github.Branch import Branch
from github.PullRequest import PullRequest

logger = logging.getLogger(__name__)

@dataclass
class BranchInfo:
    """Information about a branch in the repository."""
    name: str
    parent_branch: str  # The branch this was created from
    type: str  # 'feature' or 'task'
    description: str
    status: str = "active"  # active, merged, abandoned
    associated_task_id: Optional[str] = None  # Linear task ID if applicable
    ci_status: Optional[str] = None  # passing, failing, pending
    pr_number: Optional[int] = None  # PR number if one exists

@dataclass
class GitHubContext:
    """Context information about the GitHub repository and current work."""
    repo_owner: str
    repo_name: str
    base_branch: str = "main"  # Default base branch
    current_feature_branch: Optional[str] = None
    current_task_branch: Optional[str] = None
    branches: Dict[str, BranchInfo] = None
    
    def __post_init__(self):
        if self.branches is None:
            self.branches = {}

class GitHubService:
    """Service for interacting with GitHub repositories."""
    
    def __init__(self, token: str, context: GitHubContext):
        """Initialize the GitHub service.
        
        Args:
            token: GitHub personal access token
            context: GitHubContext object with repository information
        """
        self.token = token
        self.context = context
        self.github = Github(token)
        self.repo = self.github.get_repo(f"{context.repo_owner}/{context.repo_name}")
        logger.info(f"Initialized GitHub service for {context.repo_owner}/{context.repo_name}")
    
    def get_repo_structure(self) -> Dict[str, Any]:
        """Get the structure of the repository.
        
        Returns:
            Dictionary with repository structure information
        """
        try:
            # Get basic repo info
            repo_info = {
                "name": self.repo.name,
                "description": self.repo.description,
                "default_branch": self.repo.default_branch,
                "branches": [branch.name for branch in self.repo.get_branches()],
                "open_issues_count": self.repo.open_issues_count,
                "open_pull_requests": len(list(self.repo.get_pulls(state="open"))),
            }
            
            # Get directory structure of default branch
            contents = self.repo.get_contents("")
            files_and_dirs = []
            
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    files_and_dirs.append({"name": file_content.name, "type": "dir", "path": file_content.path})
                    # Add subdirectory contents to the stack
                    contents.extend(self.repo.get_contents(file_content.path))
                else:
                    files_and_dirs.append({"name": file_content.name, "type": "file", "path": file_content.path})
            
            repo_info["structure"] = files_and_dirs
            return repo_info
            
        except GithubException as e:
            logger.error(f"Error getting repository structure: {e}")
            return {"error": str(e)}
    
    def create_feature_branch(self, branch_name: str, description: str) -> BranchInfo:
        """Create a new feature branch from the base branch.
        
        Args:
            branch_name: Name of the feature branch to create
            description: Description of the feature branch
            
        Returns:
            BranchInfo object for the created branch
        """
        # Standardize branch name format
        feature_branch_name = f"feature/{branch_name}"
        
        try:
            # Get the base branch
            base_branch = self.repo.get_branch(self.context.base_branch)
            
            # Create the new branch
            self.repo.create_git_ref(
                ref=f"refs/heads/{feature_branch_name}",
                sha=base_branch.commit.sha
            )
            
            # Create branch info and update context
            branch_info = BranchInfo(
                name=feature_branch_name,
                parent_branch=self.context.base_branch,
                type="feature",
                description=description
            )
            
            self.context.branches[feature_branch_name] = branch_info
            self.context.current_feature_branch = feature_branch_name
            
            logger.info(f"Created feature branch: {feature_branch_name}")
            return branch_info
            
        except GithubException as e:
            logger.error(f"Error creating feature branch: {e}")
            raise
    
    def create_task_branch(self, branch_name: str, description: str, task_id: Optional[str] = None) -> BranchInfo:
        """Create a new task branch from the current feature branch.
        
        Args:
            branch_name: Name of the task branch to create
            description: Description of the task branch
            task_id: Optional Linear task ID
            
        Returns:
            BranchInfo object for the created branch
        """
        if not self.context.current_feature_branch:
            raise ValueError("No current feature branch set. Create a feature branch first.")
        
        # Standardize branch name format
        task_branch_name = f"task/{branch_name}"
        
        try:
            # Get the feature branch
            feature_branch = self.repo.get_branch(self.context.current_feature_branch)
            
            # Create the new branch
            self.repo.create_git_ref(
                ref=f"refs/heads/{task_branch_name}",
                sha=feature_branch.commit.sha
            )
            
            # Create branch info and update context
            branch_info = BranchInfo(
                name=task_branch_name,
                parent_branch=self.context.current_feature_branch,
                type="task",
                description=description,
                associated_task_id=task_id
            )
            
            self.context.branches[task_branch_name] = branch_info
            self.context.current_task_branch = task_branch_name
            
            logger.info(f"Created task branch: {task_branch_name}")
            return branch_info
            
        except GithubException as e:
            logger.error(f"Error creating task branch: {e}")
            raise
    
    def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str) -> PullRequest:
        """Create a pull request.
        
        Args:
            title: PR title
            body: PR description
            head_branch: Source branch
            base_branch: Target branch
            
        Returns:
            Created PullRequest object
        """
        try:
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch
            )
            
            # Update branch info if we're tracking this branch
            if head_branch in self.context.branches:
                self.context.branches[head_branch].pr_number = pr.number
            
            logger.info(f"Created PR #{pr.number}: {head_branch} → {base_branch}")
            return pr
            
        except GithubException as e:
            logger.error(f"Error creating pull request: {e}")
            raise
    
    def merge_branch(self, head_branch: str, base_branch: str, commit_message: str) -> bool:
        """Merge a branch into another branch.
        
        Args:
            head_branch: Source branch to merge from
            base_branch: Target branch to merge into
            commit_message: Merge commit message
            
        Returns:
            True if merge was successful
        """
        try:
            # Create a PR if one doesn't exist
            existing_prs = list(self.repo.get_pulls(state="open", head=head_branch, base=base_branch))
            
            if existing_prs:
                pr = existing_prs[0]
                logger.info(f"Using existing PR #{pr.number}")
            else:
                pr = self.create_pull_request(
                    title=f"Merge {head_branch} into {base_branch}",
                    body=commit_message,
                    head_branch=head_branch,
                    base_branch=base_branch
                )
            
            # Check if PR can be merged
            if not pr.mergeable:
                logger.error(f"PR #{pr.number} cannot be merged. Resolve conflicts first.")
                return False
            
            # Merge the PR
            merge_result = pr.merge(
                commit_message=commit_message,
                merge_method="merge"  # Could be "merge", "squash", or "rebase"
            )
            
            # Update branch info
            if head_branch in self.context.branches:
                self.context.branches[head_branch].status = "merged"
            
            logger.info(f"Merged {head_branch} into {base_branch}")
            return True
            
        except GithubException as e:
            logger.error(f"Error merging branch: {e}")
            return False
    
    def check_ci_status(self, branch_name: str) -> str:
        """Check the CI status of a branch.
        
        Args:
            branch_name: Name of the branch to check
            
        Returns:
            Status string: "success", "failure", "pending", or "unknown"
        """
        try:
            branch = self.repo.get_branch(branch_name)
            commit = branch.commit
            statuses = list(commit.get_statuses())
            
            if not statuses:
                return "unknown"
            
            # Get the latest status
            latest_status = statuses[0].state
            
            # Update branch info
            if branch_name in self.context.branches:
                self.context.branches[branch_name].ci_status = latest_status
            
            return latest_status
            
        except GithubException as e:
            logger.error(f"Error checking CI status: {e}")
            return "unknown"
