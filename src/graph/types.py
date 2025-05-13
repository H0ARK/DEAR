# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import operator
from typing import Annotated, Any, Dict, List, Optional, Literal

from langgraph.graph import MessagesState
from langchain_core.messages import BaseMessage

from src.prompts.planner_model import Plan


class State(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = "en-US"
    observations: list[str] = []
    plan_iterations: int = 0
    current_plan: Plan | str = None
    final_report: str = ""
    auto_accepted_plan: bool = False
    enable_background_investigation: bool = True
    background_investigation_results: str = None
    create_workspace: bool = False
    repo_path: str = None

    # --- GitHub specific state from previous iterations ---
    feature_branch_name: Optional[str] = None
    github_task_branches: Optional[Dict[int, str]] = None # Maps step number to task branch name
    github_action: Optional[str] = None # e.g., "create_feature_branch", "create_task_branch"
    feature_branch_description: Optional[str] = None

    # --- Codegen specific state ---
    codegen_task_description: Optional[str] = None
    codegen_task_id: Optional[str] = None
    codegen_task_status: Optional[str] = None # PENDING, RUNNING, SUCCESS, FAILURE_CODING, FAILURE_REVIEW, TIMEOUT
    codegen_task_result: Optional[Any] = None # Could be code, error message, etc.
    codegen_poll_attempts: int = 0

    # --- Interrupt feedback ---
    interrupt_feedback: Optional[str] = None # General purpose feedback from an interrupt

    # --- Initial Context ---
    initial_repo_check_done: bool = False
    repo_is_empty: bool = True # Default to true, initial_context_node will update
    linear_task_exists: bool = False # Default to false
    initial_context_summary: Optional[str] = None # Consider upgrading or replacing with existing_project_summary

    # --- Fields from PROJECT_PLAN.md Section II ---
    existing_project_summary: Optional[Dict] = None
    prd_document: Optional[str] = ""
    prd_review_feedback: Optional[str] = None
    prd_approved: bool = False
    prd_next_step: Optional[str] = None # Expected values: "human_prd_review", "context_gatherer", "coding_planner"
    research_results: Optional[Any] = None
    tasks_definition: Optional[List[Dict]] = None # Detailed plan from coding_planner
    # tasks_definition Task Dict: {id, description, dependencies: List[id], branch_name, status_in_plan, execute_alone, etc.}
    tasks_live: Optional[List[Dict]] = None # Tasks after Linear sync, with Linear IDs
    # tasks_live Task Dict: {linear_id, github_branch, status_live, ...}
    current_task_id: Optional[str] = None # ID of the task currently being processed
    current_task_details: Optional[Dict] = None # Details of the current_task_id for codegen
    orchestrator_next_step: Optional[str] = None # Expected values: "dispatch_task_for_codegen", "forward_failure_to_planner", "all_tasks_complete"
    failed_task_details: Optional[Dict] = None # Info for planner if orchestrator escalates a failure

    # --- Task Completion/Failure Feedback for Orchestrator ---
    processed_task_id: Optional[str] = None
    processed_task_outcome: Optional[Literal["SUCCESS", "FAILURE"]] = None
    processed_task_failure_details: Optional[Dict] = None


def get_current_human_message(state: State) -> Optional[BaseMessage]:
    pass
