# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
import random
from typing import Annotated, Literal, Dict, Any, Optional, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import Command
from langchain.prompts import PromptTemplate

from src.agents.agents import coder_agent, research_agent, create_agent
from src.tools.search import LoggedTavilySearch
from src.tools import (
    crawl_tool,
    web_search_tool,
    python_repl_tool,
)
from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type
from src.prompts.planner_model import Plan, Step, StepType
from src.prompts.template import apply_prompt_template
from src.utils.json_utils import repair_json_output

from ..types import State
from ...config import SEARCH_MAX_RESULTS, SELECTED_SEARCH_ENGINE, SearchEngine
from src.tools.linear_service import LinearService

logger = logging.getLogger(__name__)

# Import any global constants or variables needed across modules

def initial_context_node(state: State, config: RunnableConfig) -> Command[Literal["initial_context_query_generator"]]:
    """Node that gathers initial context for the project."""
    logger.info("Gathering initial context for the project...")
    
    # Get the user's request from the messages
    user_messages = [msg for msg in state.get("messages", []) if isinstance(msg, HumanMessage)]
    if not user_messages:
        logger.error("No user messages found in state. Cannot gather initial context.")
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content="Error: No user request found. Please provide a request.", name="initial_context")]
            },
            goto="__end__"
        )
    
    user_request = user_messages[-1].content
    
    # Prepare messages for the LLM to gather initial context
    messages = [
        SystemMessage(content="You are an expert software architect. Your task is to understand a user's project request. Your goal is to start a conversation to clarify the project details."),
        HumanMessage(content=f"User Request:\n\n{user_request}"),
        HumanMessage(content="Based on the user's request, what is your high-level understanding of the project? Please state this in 1-2 sentences. If the request is unclear, or if you need more specific details to form a basic understanding (e.g., for a game, what kind of game? For a website, what is its main purpose?), ask 1-2 key clarifying questions. Do NOT generate a full project overview, requirements list, or technical considerations at this stage. Your response should be a brief summary for confirmation OR a couple of questions.")
    ]
    
    try:
        # Get the LLM response
        llm = get_llm_by_type(AGENT_LLM_MAP.get("initial_context", ""))
        response = llm.invoke(messages)
        initial_interaction_content = response.content # This is now a question or brief summary
        
        logger.info(f"Initial interaction from initial_context_node: {initial_interaction_content}")
        
        updated_state = state.copy()
        # Store the LLM's first response (question/summary)
        updated_state["initial_interaction_content"] = initial_interaction_content
        # Ensure the query generator uses this content
        updated_state["initial_context_summary"] = initial_interaction_content 
        
        # Add this initial AI response to the messages list to be displayed in the UI
        # Use a distinct agent name for clarity in the UI if needed
        updated_state["messages"] = state.get("messages", []) + [
            AIMessage(content=initial_interaction_content, name="initial_context_agent") 
        ]
        
        # Clear out old fields or set to placeholder, as the full context isn't generated yet.
        updated_state["initial_context"] = None 

        # Proceed to the query generator for human review
        return Command(update=updated_state, goto="initial_context_query_generator")

    except Exception as e:
        logger.error(f"Error gathering initial context: {e}")
        error_message = f"I encountered an error trying to gather initial context for your request. Error: {e}."
        
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=error_message, name="initial_context")]
            },
            goto="__end__"
        )
