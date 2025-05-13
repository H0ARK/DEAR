# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
from typing import Literal, Dict, Any, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.config.configuration import Configuration
from src.tools.github_service import GitHubService, GitHubContext, BranchInfo
from src.tools.linear_service import LinearService, LinearTask
from src.graph.types import State

logger = logging.getLogger(__name__)

def github_manager_node(
    state: State, config: RunnableConfig
) -> Command[Literal["task_orchestrator", "coding_planner", "__end__"]]:
    """Node that manages GitHub operations like branch creation, merging, and PR creation."""
    logger.info("GitHub Manager node executing...")
    configurable = Configuration.from_runnable_config(config)

    # Get GitHub action from state
    github_action = state.get("github_action")
    if not github_action:
        logger.warning("No GitHub action specified. Returning to coding planner.")
        return Command(goto="coding_planner")

    # Initialize GitHub context if not present
    github_context = state.get("github_context")
    if not github_context:
        # Create a new GitHub context
        github_context = GitHubContext(
            repo_owner=configurable.github_repo_owner,
            repo_name=configurable.github_repo_name,
            base_branch=configurable.github_base_branch or "main"
        )

    # Initialize GitHub service
    github_service = GitHubService(
        token=configurable.github_token,
        context=github_context
    )

    # Initialize Linear service if configured
    linear_service = None
    if configurable.linear_api_key:
        linear_service = LinearService(
            api_key=configurable.linear_api_key,
            team_id=configurable.linear_team_id
        )

    result_message = ""
    goto = "coding_planner"  # Default next node

    try:
        # Execute the requested GitHub action
        if github_action == "get_repo_info":
            # Get repository structure
            repo_info = github_service.get_repo_structure()
            result_message = f"Repository information retrieved for {github_context.repo_owner}/{github_context.repo_name}"

            # Update state with repo info
            state["github_repo_info"] = repo_info

        elif github_action == "create_feature_branch":
            # Get branch details from state
            branch_name = state.get("feature_branch_name")
            description = state.get("feature_branch_description", "")

            if not branch_name:
                raise ValueError("Feature branch name is required")

            # Create the feature branch
            branch_info = github_service.create_feature_branch(branch_name, description)
            result_message = f"Created feature branch: {branch_info.name}"

            # Create Linear task if configured
            if linear_service and state.get("create_linear_task"):
                task_title = state.get("linear_task_title", f"Feature: {branch_name}")
                task_description = state.get("linear_task_description", description)

                task = linear_service.create_task(
                    title=task_title,
                    description=task_description,
                    team_id=configurable.linear_team_id
                )

                # Update branch info with task ID
                branch_info.associated_task_id = task.id
                result_message += f"\nCreated Linear task: {task.id} - {task.title}"

        elif github_action == "create_task_branch":
            # Get branch details from state
            branch_name = state.get("task_branch_name")
            description = state.get("task_branch_description", "")

            if not branch_name:
                raise ValueError("Task branch name is required")

            # Create the task branch
            branch_info = github_service.create_task_branch(branch_name, description)
            result_message = f"Created task branch: {branch_info.name} from {branch_info.parent_branch}"

            # Create Linear task if configured
            if linear_service and state.get("create_linear_task"):
                task_title = state.get("linear_task_title", f"Task: {branch_name}")
                task_description = state.get("linear_task_description", description)

                task = linear_service.create_task(
                    title=task_title,
                    description=task_description,
                    team_id=configurable.linear_team_id
                )

                # Update branch info with task ID
                branch_info.associated_task_id = task.id

                # Update Linear task with branch info
                linear_service.update_task_with_github_info(task.id, branch_info.name)

                result_message += f"\nCreated Linear task: {task.id} - {task.title}"

            # Set next node to task_orchestrator to start implementing the task
            goto = "task_orchestrator"

        elif github_action == "merge_task_branch":
            # Get branch details from state
            task_branch = state.get("task_branch_to_merge")

            if not task_branch:
                raise ValueError("Task branch name is required for merging")

            # Get the parent branch (should be a feature branch)
            branch_info = github_context.branches.get(task_branch)
            if not branch_info:
                raise ValueError(f"Branch info not found for {task_branch}")

            parent_branch = branch_info.parent_branch

            # Check CI status before merging
            ci_status = github_service.check_ci_status(task_branch)
            if ci_status != "success":
                result_message = f"CI checks are not passing for {task_branch}. Status: {ci_status}. Skipping merge."
            else:
                # Merge the task branch into its parent feature branch
                commit_message = f"Merge task branch {task_branch} into {parent_branch}"
                merge_success = github_service.merge_branch(task_branch, parent_branch, commit_message)

                if merge_success:
                    result_message = f"Successfully merged {task_branch} into {parent_branch}"

                    # Update Linear task if applicable
                    if linear_service and branch_info.associated_task_id:
                        # Update task status to indicate completion
                        linear_service.update_task(
                            branch_info.associated_task_id,
                            {"stateId": configurable.linear_completed_state_id}
                        )
                        result_message += f"\nUpdated Linear task {branch_info.associated_task_id} status to completed"
                else:
                    result_message = f"Failed to merge {task_branch} into {parent_branch}"

        elif github_action == "create_feature_pr":
            # Get feature branch details from state
            feature_branch = state.get("feature_branch_for_pr")

            if not feature_branch:
                raise ValueError("Feature branch name is required for PR creation")

            # Get PR details
            pr_title = state.get("pr_title", f"Merge {feature_branch} into {github_context.base_branch}")
            pr_body = state.get("pr_body", "Automated PR created by DEAR agent")

            # Create the PR
            pr = github_service.create_pull_request(
                title=pr_title,
                body=pr_body,
                head_branch=feature_branch,
                base_branch=github_context.base_branch
            )

            result_message = f"Created PR #{pr.number}: {feature_branch} → {github_context.base_branch}"

            # Update all associated Linear tasks
            if linear_service:
                for branch_name, branch_info in github_context.branches.items():
                    if (branch_info.parent_branch == feature_branch or branch_name == feature_branch) and branch_info.associated_task_id:
                        linear_service.update_task_with_github_info(
                            branch_info.associated_task_id,
                            branch_info.name,
                            pr.html_url
                        )
                        result_message += f"\nUpdated Linear task {branch_info.associated_task_id} with PR link"

        else:
            result_message = f"Unknown GitHub action: {github_action}"
            logger.warning(result_message)

    except Exception as e:
        logger.error(f"Error in GitHub Manager: {e}", exc_info=True)
        result_message = f"Error executing GitHub action {github_action}: {str(e)}"
        goto = "coding_planner"  # Return to planner on error

    # Update state with GitHub context
    updated_state = {
        "messages": state["messages"] + [AIMessage(content=result_message, name="github_manager")],
        "github_context": github_context,
        "github_action": None  # Clear the action to prevent re-execution
    }

    return Command(update=updated_state, goto=goto)

def github_planning_node(
    state: State, config: RunnableConfig
) -> Command[Literal["github_manager", "coding_planner", "__end__"]]:
    """Node that plans GitHub operations based on the coding plan."""
    logger.info("GitHub Planning node executing...")
    configurable = Configuration.from_runnable_config(config)

    # Get the current plan
    current_plan = state.get("current_plan")
    if not current_plan:
        logger.warning("No current plan found. Returning to coding planner.")
        return Command(goto="coding_planner")

    # Initialize GitHub context if not present
    github_context = state.get("github_context")
    if not github_context:
        # Create a new GitHub context
        github_context = GitHubContext(
            repo_owner=configurable.github_repo_owner,
            repo_name=configurable.github_repo_name,
            base_branch=configurable.github_base_branch or "main"
        )

    # Determine what GitHub action is needed based on the plan
    # This is a simplified example - in a real implementation, you would analyze the plan more thoroughly

    # If we don't have a feature branch yet, create one
    if not github_context.current_feature_branch:
        # Use the feature branch name from the plan if available
        feature_branch_name = state.get("feature_branch_name")
        if not feature_branch_name:
            # Fall back to extracting a name from the plan title
            feature_branch_name = current_plan.title.lower().replace(" ", "_").replace("/", "-")

        # Make sure it doesn't have the feature/ prefix already
        if feature_branch_name.startswith("feature/"):
            feature_branch_name = feature_branch_name[8:]

        return Command(
            update={
                "github_action": "create_feature_branch",
                "feature_branch_name": feature_branch_name,
                "feature_branch_description": current_plan.thought,
                "create_linear_task": True,
                "linear_task_title": current_plan.title,
                "linear_task_description": current_plan.thought,
                "github_context": github_context
            },
            goto="github_manager"
        )

    # If we have a feature branch but no task branch, create one for the first step
    elif not github_context.current_task_branch and current_plan.steps:
        # Get the first step that needs to be implemented
        first_step = None
        step_number = 0
        for i, step in enumerate(current_plan.steps):
            if not step.execution_res:
                first_step = step
                step_number = i + 1  # 1-based step number
                break

        if first_step:
            # Get task branches from the plan if available
            github_task_branches = state.get("github_task_branches", {})

            # Use the task branch name from the plan if available for this step
            task_branch_name = github_task_branches.get(step_number)
            if not task_branch_name:
                # Fall back to extracting a name from the step title
                task_branch_name = first_step.title.lower().replace(" ", "-").replace("/", "-")

            # Make sure it doesn't have the task/ prefix already
            if task_branch_name.startswith("task/"):
                task_branch_name = task_branch_name[5:]

            return Command(
                update={
                    "github_action": "create_task_branch",
                    "task_branch_name": task_branch_name,
                    "task_branch_description": first_step.description,
                    "create_linear_task": True,
                    "linear_task_title": first_step.title,
                    "linear_task_description": first_step.description,
                    "github_context": github_context
                },
                goto="github_manager"
            )

    # If all steps are complete, create a PR for the feature branch
    elif all(step.execution_res for step in current_plan.steps):
        return Command(
            update={
                "github_action": "create_feature_pr",
                "feature_branch_for_pr": github_context.current_feature_branch,
                "pr_title": f"Feature: {current_plan.title}",
                "pr_body": f"Implements {current_plan.title}\n\n{current_plan.thought}",
                "github_context": github_context
            },
            goto="github_manager"
        )

    # Otherwise, continue with coding
    return Command(
        update={"github_context": github_context},
        goto="coder"
    )
