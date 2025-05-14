# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.errors import GraphInterrupt

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
        updated_state["initial_context_summary"] = initial_context[:100] + "..." # Truncate to 100 chars for summary
        
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


def initial_context_query_generator_node(state: State, config: RunnableConfig) -> State:
    """Generates the query/summary for human review of initial context."""
    logger.info("Initial context query generator node executing...")
    
    # This node would typically:
    # 1. Get initial_context_summary or generate one if not present.
    # 2. Formulate a question for the user.
    initial_context_summary = state.get("initial_context_summary", "No initial context gathered yet.")
    query = f"I've gathered the following initial context about your project:\\n\\n{initial_context_summary}\\n\\nPlease review this information. Is this understanding correct and complete? If not, what should be changed or added?"
    
    iterations = state.get("initial_context_iterations", 0) + 1
    
    # THIS IS THE KEY: Signal to the graph to interrupt and wait for external feedback
    logger.critical(f"GRAPH: initial_context_query_generator_node DETECTED need for human input. Raising InterruptException.")
    raise GraphInterrupt()

def initial_context_wait_for_feedback_node(state: State, config: RunnableConfig) -> State:
    """(Placeholder) Waits for human feedback on the initial context.
    In a real interruptible system, this node might not do much if the interrupt
    is handled by the graph executor. If using explicit 'human_tool', this would invoke it.
    For our current explicit state-driven loop, this node might just ensure state is set for UI.
    """
    logger.info("Initial context wait for feedback node executing (placeholder)...")
    # The actual waiting/interrupt is managed by how the graph is run and how UI interacts.
    # This node ensures the state `awaiting_initial_context_input` is True if not already.
    if not state.get("awaiting_initial_context_input"):
        logger.warning("initial_context_wait_for_feedback_node: awaiting_initial_context_input was False. Forcing to True.")
        return {"awaiting_initial_context_input": True}
    return {} # No state change if already awaiting

def initial_context_feedback_handler_node(state: State, config: RunnableConfig) -> State:
    """Handles the feedback received from the user about the initial context."""
    logger.info("Initial context feedback handler node executing...")
    
    user_feedback = state.get("last_initial_context_feedback") # This should be populated by the streaming endpoint
    
    updated_messages = state.get("messages", [])
    if user_feedback:
        updated_messages = updated_messages + [HumanMessage(content=user_feedback, name="user_initial_context_feedback")]
        logger.info(f"Processed user feedback: {user_feedback[:100]}...")
    else:
        logger.warning("No user feedback found in last_initial_context_feedback.")

    # Logic to determine if feedback implies approval
    approved = False
    if user_feedback and any(kw in user_feedback.lower() for kw in ["approve", "looks good", "correct", "proceed"]):
        approved = True
        logger.info("User feedback indicates approval.")
        
    return {
        "initial_context_approved": approved,
        "awaiting_initial_context_input": False, # No longer awaiting input for this cycle
        "pending_initial_context_query": None, # Clear the last query
        "messages": updated_messages
        # last_initial_context_feedback is kept as a record, cleared by query_generator if new iteration starts
    }

def initial_context_approval_router_node(state: State, config: RunnableConfig) -> Command[Literal["coding_coordinator", "initial_context_query_generator"]]:
    """Routes based on whether the initial context was approved."""
    logger.info("Initial context approval router node executing...")
    if state.get("initial_context_approved"):
        logger.info("Initial context approved. Proceeding to coding_coordinator.")
        return Command(goto="coding_coordinator")
    else:
        logger.info("Initial context not approved or needs more iterations. Looping back to query generator.")
        return Command(goto="initial_context_query_generator")

