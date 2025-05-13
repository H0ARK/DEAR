# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from .common import *
from .planning import handoff_to_planner

def coordinator_node(
    state: State,
) -> Command[Literal["context_gatherer", "background_investigator", "__end__"]]:
    """Coordinator node that communicate with customers."""
    logger.info("Coordinator talking.")
    messages = apply_prompt_template("coordinator", state)
    response = (
        get_llm_by_type(AGENT_LLM_MAP["coordinator"])
        .bind_tools([handoff_to_planner])  # Restore tool binding
        .invoke(messages)
    )
    logger.debug(f"Current state messages: {state['messages']}")

    goto = "__end__"
    locale = state.get("locale", "en-US")  # Default locale if not specified

    # Restore original logic for checking tool calls
    if len(response.tool_calls) > 0:
        goto = "context_gatherer"
        if state.get("enable_background_investigation"):
            # if the search_before_planning is True, add the web search tool to the planner agent
            goto = "background_investigator"
        try:
            for tool_call in response.tool_calls:
                if tool_call.get("name", "") != "handoff_to_planner":
                    continue
                if tool_locale := tool_call.get("args", {}).get("locale"):
                    locale = tool_locale
                    break
        except Exception as e:
            logger.error(f"Error processing tool calls: {e}")
    else:
        logger.warning(
            "Coordinator response contains no tool calls. Terminating workflow execution."
        )
        logger.debug(f"Coordinator response: {response}")

    return Command(
        update={
            "locale": locale,
            # The original didn't add the coordinator's direct response to messages here,
            # as it relied on the tool call for the next step.
            # If there was a direct response without a tool call, it was usually just an end to the conversation.
        },
        goto=goto,
    )


def coding_coordinator_node(state: State) -> Command[Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]]:
    """Coordinator node for coding tasks that generates PRD and handles feedback."""
    logger.info("Coding Coordinator processing request...")
    
    # Check if we have PRD feedback to process
    prd_review_feedback = state.get("prd_review_feedback")
    prd_document = state.get("prd_document")
    
    # If we have feedback but it's not an approval, we need to update the PRD
    if prd_review_feedback and prd_document and not any(keyword in prd_review_feedback.lower() for keyword in ["approve", "accept", "good"]):
        logger.info("Processing PRD feedback to update the document...")
        
        # Prepare messages for the LLM to update the PRD
        messages = [
            SystemMessage(content="You are an expert product manager. Your task is to update a Product Requirements Document (PRD) based on user feedback."),
            HumanMessage(content=f"Here is the current PRD:\n\n{prd_document}"),
            HumanMessage(content=f"Here is the user's feedback:\n\n{prd_review_feedback}"),
            HumanMessage(content="Please provide an updated PRD that addresses the feedback. Maintain the same structure and format, but incorporate the requested changes.")
        ]
        
        try:
            # Get the LLM response
            llm = get_llm_by_type(AGENT_LLM_MAP.get("coding_coordinator", ""))
            response = llm.invoke(messages)
            updated_prd = response.content
            
            logger.info("Successfully updated PRD based on feedback.")
            
            # Update the state with the new PRD
            updated_state = state.copy()
            updated_state["prd_document"] = updated_prd
            updated_state["prd_review_feedback"] = None  # Clear the feedback
            
            # Send the updated PRD back for review
            return Command(update=updated_state, goto="human_prd_review")
        
        except Exception as e:
            logger.error(f"Error updating PRD based on feedback: {e}")
            error_message = f"I encountered an error trying to update the PRD based on your feedback. Error: {e}."
            
            return Command(
                update={
                    "messages": state["messages"] + [AIMessage(content=error_message, name="coding_coordinator")]
                },
                goto="__end__"
            )
    
    # If we have an approved PRD, proceed to planning
    if prd_document and prd_review_feedback and any(keyword in prd_review_feedback.lower() for keyword in ["approve", "accept", "good"]):
        logger.info("PRD approved. Proceeding to planning phase.")
        return Command(update=state, goto="coding_planner")
    
    # If we don't have a PRD yet, generate one
    if not prd_document:
        logger.info("Generating PRD from user request...")
        
        # Get the user's request from the messages
        user_messages = [msg for msg in state.get("messages", []) if isinstance(msg, HumanMessage)]
        if not user_messages:
            logger.error("No user messages found in state. Cannot generate PRD.")
            return Command(
                update={
                    "messages": state["messages"] + [AIMessage(content="Error: No user request found. Please provide a request.", name="coding_coordinator")]
                },
                goto="__end__"
            )
        
        user_request = user_messages[-1].content
        
        # Check if we have research results to include
        research_results = state.get("research_results", "")
        
        # Prepare messages for the LLM to generate the PRD
        messages = [
            SystemMessage(content="You are an expert product manager. Your task is to create a detailed Product Requirements Document (PRD) based on a user's request."),
            HumanMessage(content=f"User Request:\n\n{user_request}")
        ]
        
        if research_results:
            messages.append(HumanMessage(content=f"Research Results:\n\n{research_results}"))
        
        messages.append(HumanMessage(content="Please create a comprehensive PRD that includes:\n\n1. Overview\n2. Problem Statement\n3. Goals and Objectives\n4. User Stories\n5. Functional Requirements\n6. Non-Functional Requirements\n7. Constraints\n8. Success Metrics"))
        
        try:
            # Get the LLM response
            llm = get_llm_by_type(AGENT_LLM_MAP.get("coding_coordinator", ""))
            response = llm.invoke(messages)
            prd_document = response.content
            
            logger.info("Successfully generated PRD from user request.")
            
            # Update the state with the new PRD
            updated_state = state.copy()
            updated_state["prd_document"] = prd_document
            
            # Send the PRD for review
            return Command(update=updated_state, goto="human_prd_review")
        
        except Exception as e:
            logger.error(f"Error generating PRD from user request: {e}")
            error_message = f"I encountered an error trying to generate a PRD from your request. Error: {e}."
            
            return Command(
                update={
                    "messages": state["messages"] + [AIMessage(content=error_message, name="coding_coordinator")]
                },
                goto="__end__"
            )
    
    # If we reach here, something unexpected happened
    logger.warning("Unexpected state in coding_coordinator_node. Ending workflow.")
    return Command(
        update={
            "messages": state["messages"] + [AIMessage(content="I encountered an unexpected state in the workflow. Please try again with a clearer request.", name="coding_coordinator")]
        },
        goto="__end__"
    )


def initial_context_node(state: State, config: RunnableConfig) -> Command[Literal["coding_coordinator"]]:
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
        SystemMessage(content="You are an expert software architect. Your task is to gather initial context for a project based on a user's request."),
        HumanMessage(content=f"User Request:\n\n{user_request}"),
        HumanMessage(content="Please provide initial context for this project, including:\n\n1. Project Overview\n2. Key Requirements\n3. Technical Considerations\n4. Potential Challenges\n5. Recommended Approach")
    ]
    
    try:
        # Get the LLM response
        llm = get_llm_by_type(AGENT_LLM_MAP.get("initial_context", ""))
        response = llm.invoke(messages)
        initial_context = response.content
        
        logger.info("Successfully gathered initial context.")
        
        # Update the state with the initial context
        updated_state = state.copy()
        updated_state["initial_context"] = initial_context
        
        # Proceed to the coding coordinator
        return Command(update=updated_state, goto="coding_coordinator")
    
    except Exception as e:
        logger.error(f"Error gathering initial context: {e}")
        error_message = f"I encountered an error trying to gather initial context for your request. Error: {e}."
        
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=error_message, name="initial_context")]
            },
            goto="__end__"
        )

