# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
from typing import Literal, Dict, Any, Optional, List

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.config.configuration import Configuration
from src.tools.github_service import GitHubService, GitHubContext
from src.tools.linear_service import LinearService, LinearTask
from src.tools.repo_analyzer import RepoAnalyzer, RepoAnalysisResult
from src.graph.types import State
from src.prompts.planner_model import Plan, Step, StepType

logger = logging.getLogger(__name__)

def context_gathering_node(
    state: State,
) -> Command[Literal["research_team"]]:
    """Prepares context such as API reference docs, github repositories, or other info for the LLM."""
    logger.info("Preparing context for LLM...")

    # Initialize variables
    current_plan = None
    research_return_to = "coding_coordinator"  # Default return node for research_team

    # Check if we were redirected from coding_coordinator for clarification research
    is_clarification_research = state.get("clarification_prompt_from_coordinator") is not None

    # Setup research parameters based on whether this is a clarification research
    if is_clarification_research:
        logger.info("This research is for a clarification from the coding coordinator.")

        # Use the clarification prompt as the research query
        research_query = state.get("clarification_prompt_from_coordinator", "")

        # Using default research_return_to value

        # Create a research plan specifically for this clarification
        if not current_plan:
            # Simple research plan with a descriptive title
            query_preview = research_query[:50] + "..." if len(research_query) > 50 else research_query
            current_plan = Plan(
                locale="en-US",  # Default to English
                has_enough_context=False,  # We're doing research, so we don't have enough context
                title=f"Research for clarification: {query_preview}",
                thought=f"Gathering information to answer: {research_query}",
                steps=[
                    Step(
                        need_web_search=True,
                        title="Search for relevant information",
                        description=f"Research: {research_query}",
                        step_type=StepType.RESEARCH,
                        execution_res=None
                    )
                ]
            )
            logger.info(f"Created research plan for clarification with 1 step.")
            # We'll set this in the Command update at the end
    else:
        # For normal research from initial context gathering
        last_message = ""
        for msg in state.get("messages", []):
            if hasattr(msg, "type") and msg.type == "human":
                last_message = msg.content
            elif hasattr(msg, "role") and msg.role == "user":
                last_message = msg.content

        # Extract research keywords from the user's message if available
        research_query = last_message

        # Using default research_return_to value

        if not current_plan:
            # Create a proper research plan for the task
            logger.info(f"Creating research plan for query: {research_query[:50]}...")

            # Create a simple research plan
            current_plan = Plan(
                locale="en-US",  # Default to English
                has_enough_context=False,  # We're doing research
                title=f"Research for user request",
                thought=f"Gathering information about: {research_query}",
                steps=[
                    Step(
                        need_web_search=True,
                        title="Search for relevant information",
                        description=f"Research: {research_query}",
                        step_type=StepType.RESEARCH,
                        execution_res=None
                    )
                ]
            )
            logger.info(f"Created basic research plan with 1 step.")
            # We'll set this in the Command update at the end

    # Create a copy of the state for updates
    state_updates = {}

    # Add research_return_to to the updates
    state_updates["research_return_to"] = research_return_to

    # Add current_plan if it was created
    if current_plan is not None and current_plan != state.get("current_plan"):
        state_updates["current_plan"] = current_plan

    # Always return to research_team which will handle routing based on state flags
    return Command(update=state_updates, goto="research_team")

# Placeholder for a more detailed repository analysis function if needed separately
# def analyze_repository_node(state: State, config: RunnableConfig) -> State:
