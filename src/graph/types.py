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
    observations: Annotated[list[str], operator.add] = []
    plan_iterations: Annotated[int, operator.add] = 0
    current_plan: Annotated[Optional[Plan | str], None] = None # Explicitly LastValue
    final_report: Annotated[str, None] = "" # Explicitly LastValue
    auto_accepted_plan: Annotated[bool, operator.or_] = False
    enable_background_investigation: Annotated[bool, operator.or_] = True
    background_investigation_results: Annotated[Optional[str], None] = None # Explicitly LastValue
    create_workspace: Annotated[bool, operator.or_] = False
    repo_path: Annotated[Optional[str], None] = None # Explicitly LastValue

    # --- GitHub specific state from previous iterations ---
    feature_branch_name: Annotated[Optional[str], None] = None # Explicitly LastValue
    github_task_branches: Annotated[Optional[Dict[int, str]], None] = None  # Explicitly LastValue
    github_action: Annotated[Optional[str], None] = None  # Explicitly LastValue
    feature_branch_description: Annotated[Optional[str], None] = None # Explicitly LastValue

    # --- Codegen specific state ---
    codegen_task_description: Annotated[Optional[str], None] = None # Explicitly LastValue
    codegen_task_id: Annotated[Optional[str], None] = None # Explicitly LastValue
    codegen_task_status: Annotated[Optional[str], None] = None # Explicitly LastValue
    codegen_task_result: Annotated[Optional[Any], None] = None # Explicitly LastValue
    codegen_poll_attempts: Annotated[int, operator.add] = 0

    # --- Interrupt feedback ---
    interrupt_feedback: Annotated[Optional[str], None] = None # Explicitly LastValue
    clarification_prompt_from_coordinator: Annotated[Optional[str], None] = None # Explicitly LastValue

    # --- Initial Context ---
    initial_repo_check_done: Annotated[bool, operator.or_] = False
    repo_is_empty: Annotated[bool, operator.or_] = True
    linear_task_exists: Annotated[bool, operator.or_] = False
    initial_context_summary: Annotated[Optional[str], None] = None # Explicitly LastValue
    # --- New fields for iterative initial context gathering ---
    pending_initial_context_query: Annotated[Optional[str], None] = None # Explicitly LastValue
    awaiting_initial_context_input: Annotated[bool, operator.or_] = False # Should allow updates if somehow set multiple times
    initial_context_approved: Annotated[bool, operator.or_] = False
    initial_context_iterations: Annotated[int, operator.add] = 0
    last_initial_context_feedback: Annotated[Optional[str], None] = None # Explicitly LastValue
    # --- End new fields ---

    # --- Fields from PROJECT_PLAN.md Section II ---
    existing_project_summary: Annotated[Optional[Dict], None] = None  # Explicitly LastValue
    prd_document: Annotated[Optional[str], None] = None # Explicitly LastValue
    prd_review_feedback: Annotated[Optional[str], None] = None # Explicitly LastValue
    prd_approved: Annotated[bool, operator.or_] = False # This was bool, changing to Annotated for safety
    prd_next_step: Annotated[Optional[str], None] = None # Explicitly LastValue
    research_results: Annotated[Optional[Any], None] = None # Explicitly LastValue
    tasks_definition: Annotated[Optional[List[Dict]], None] = None  # Explicitly LastValue
    # tasks_definition Task Dict: {id, description, dependencies: List[id], branch_name, status_in_plan, execute_alone, etc.}
    tasks_live: Annotated[Optional[List[Dict]], None] = None  # Explicitly LastValue
    # tasks_live Task Dict: {linear_id, github_branch, status_live, ...}
    current_task_id: Annotated[Optional[str], None] = None # Explicitly LastValue
    current_task_details: Annotated[Optional[Dict], None] = None # Explicitly LastValue
    orchestrator_next_step: Annotated[Optional[str], None] = None # Explicitly LastValue
    failed_task_details: Annotated[Optional[Dict], None] = None # Explicitly LastValue

    # --- Task Completion/Failure Feedback for Orchestrator ---
    processed_task_id: Annotated[Optional[str], None] = None # Explicitly LastValue
    processed_task_outcome: Annotated[Optional[Literal["SUCCESS", "FAILURE"]], None] = None # Explicitly LastValue
    processed_task_failure_details: Annotated[Optional[Dict], None] = None # Explicitly LastValue

    # --- New fields for iterative PRD review ---
    pending_prd_review_query: Annotated[Optional[str], None] = None
    prd_review_iterations: Annotated[int, operator.add] = 0
    last_prd_feedback: Annotated[Optional[str], None] = None

    # --- New fields for iterative Plan review ---
    pending_plan_review_query: Annotated[Optional[str], None] = None
    plan_approved: Annotated[bool, operator.or_] = False # This was bool, changing to Annotated for safety
    plan_review_iterations: Annotated[int, operator.add] = 0
    last_plan_feedback: Annotated[Optional[str], None] = None


def get_current_human_message(state: State) -> Optional[BaseMessage]:
    pass
