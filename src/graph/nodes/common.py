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
from langgraph.checkpoint.memory import MemorySaver


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
from src.prompts.nodes.initial_context import initial_context_prompt

logger = logging.getLogger(__name__)

# Import any global constants or variables needed across modules

def initial_context_node(state: State, config: RunnableConfig) -> Command[Literal["initial_context_query_generator"]]:
    """Node that gathers initial context for the project."""
    logger.info("Gathering initial context for the project...")
    print("------------------------------------------------------------------------")
    history = state.get("messages", [])
    # Ensure there's at least one human message to start from
    user_messages_in_history = [msg for msg in history if isinstance(msg, HumanMessage)]   
    print(f"user_messages_in_history: {user_messages_in_history}")
    print("------------------------------------------------------------------------")

    if not user_messages_in_history:
        logger.error("No user messages found in state. Cannot gather initial context.")
        return Command(
            update={
                "messages": history + [AIMessage(content="Error: No user request found. Please provide a request.", name="initial_context")]
            },
            goto="__end__"
        )

    # Prepare messages for the LLM
    llm_messages = [SystemMessage(content=initial_context_prompt)]

    # Construct the dialogue history for the LLM from state["messages"]
    # Add all HumanMessages and AIMessages from 'initial_context_agent'
    dialogue_for_llm = []
    for msg in history:
        if isinstance(msg, HumanMessage):
            dialogue_for_llm.append(msg)
        elif isinstance(msg, AIMessage) and msg.name == "initial_context_agent":
            dialogue_for_llm.append(msg)
    
    llm_messages.extend(dialogue_for_llm)
    
    # Determine if this is the first pass by checking for prior 'initial_context_agent' AIMessages
    # in the dialogue we just constructed (i.e., in dialogue_for_llm).
    is_first_pass = not any(isinstance(m, AIMessage) and m.name == "initial_context_agent" for m in dialogue_for_llm)

    if is_first_pass:
        # The last message in llm_messages is the user's initial request.
        instruction = "Based on my request (the first message from me above), what is your high-level understanding of the project? Please state this in 1-2 sentences. If the request is unclear, or if you need more specific details to form a basic understanding (e.g., for a game, what kind of game? For a website, what is its main purpose?), ask 1-2 key clarifying questions. Do NOT generate a full project overview, requirements list, or technical considerations at this stage. Your response should be a brief summary for confirmation OR a couple of questions."
    else:
        # The last message in llm_messages is the user's most recent feedback.
        instruction = "Considering our conversation so far (especially my last message, which is my feedback), please provide an updated high-level understanding (1-2 sentences for my approval) OR ask more specific clarifying questions if you still need them. Your response should be concise and easy for me to confirm or correct."
    
    llm_messages.append(HumanMessage(content=instruction))
    
    logger.info(f"Final llm_messages being sent to LLM: {[str(m) for m in llm_messages]}")
    try:
        # Get the LLM response
        # Ensure AGENT_LLM_MAP["initial_context"] is defined and refers to an appropriate model
        llm = get_llm_by_type(AGENT_LLM_MAP.get("initial_context", AGENT_LLM_MAP.get("default", "gemini-1.5-pro-latest"))) # Fallback to default
        response = llm.invoke(llm_messages) # Pass the full conversational history
        initial_interaction_content = response.content
        
        logger.info(f"Initial interaction from initial_context_node: {initial_interaction_content}")
        
        updated_state_fields = {}
        updated_state_fields["initial_interaction_content"] = initial_interaction_content
        updated_state_fields["initial_context_summary"] = initial_interaction_content 
        updated_state_fields["initial_context"] = None # Clear out old field if it existed

        # Return only the new message to be appended by LangGraph
        new_ai_message = AIMessage(content=initial_interaction_content, name="initial_context_agent")
        updated_state_fields["messages"] = [new_ai_message] 
        
        logger.info("--- END initial_context_node ---")
        return Command(update=updated_state_fields, goto="initial_context_query_generator")

    except Exception as e:
        logger.error(f"Error gathering initial context: {e}")
        error_message = f"I encountered an error trying to gather initial context for your request. Error: {e}."
        logger.info("--- END initial_context_node (with error) ---")
        return Command(
            update={
                "messages": history + [AIMessage(content=error_message, name="initial_context")]
            },
            goto="__end__"
        )
