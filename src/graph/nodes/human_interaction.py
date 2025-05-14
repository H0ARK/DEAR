# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from .common import *

def context_gatherer_node(state: State) -> Command[Literal["coding_planner", "coding_coordinator"]]:
    """Node that gathers context from the user."""
    logger.info("Gathering context from user...")
    
    # Check if we have a specific node to route to
    route_to = state.get("context_gatherer_route_to")
    
    # Create the interrupt message (or query for context)
    # This message could be more dynamic based on what context is needed.
    context_query_message = (
        "I need to gather some additional context before proceeding. "
        "Please provide any relevant information about your request, such as:\n\n"
        "1. Project overview and goals\\n"
        "2. Key features or requirements\\n"
        "3. Any existing code or technical constraints\\n"
        "4. Specific deliverables expected\n\n"
        "The more details you provide, the better I can assist you."
    )
    
    updated_state = state.copy()
    # Add the query to messages so user sees it.
    # This assumes this node is part of an interruptible flow or a flow that signals UI for input.
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=context_query_message, name="context_gatherer")
    ]
    
    force_interactive = state.get("force_interactive", True) # Check if interactive mode is forced

    if force_interactive:
        # In a true interrupt system, this would pause and wait for external input.
        # For this example, we'll assume the input is passed in `last_initial_context_feedback`
        # or a similar field if this node is being repurposed.
        # If this node is meant to use LangGraph's interrupt():
        # context_input = interrupt(context_query_message) # This would be the actual interrupt call.
        
        # For now, let's assume context comes from 'last_initial_context_feedback' if available,
        # otherwise, it indicates an issue or a need for actual interruption.
        context_input = state.get("last_initial_context_feedback") # Or a more generic "user_input_for_context_gatherer"

        if context_input is None:
            # This is where we'd typically interrupt or signal UI.
            # For now, we log and proceed to default, which might need adjustment
            # depending on how this node is used in the new state-driven HITL.
            logger.warning("No context input found (e.g. last_initial_context_feedback). Actual interruption or UI signal needed.")
            # If no input, and we must proceed, what should be the default? Forcing a decision:
            # Defaulting to coding_coordinator if route_to is not specified, assuming it's a safer general next step.
            # This part needs careful review based on the graph's intent for this node.
            final_goto = "coding_coordinator" if route_to != "coding_planner" else "coding_planner" # Corrected
            logger.info(f"No input, proceeding to default: {final_goto}")
            # Ensure additional_context is None or empty if no input
            updated_state["additional_context"] = None
            return Command(update=updated_state, goto=final_goto)


        logger.info(f"Context received via state: {context_input[:100]}...")
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=context_input, name="user_context")
        ]
        updated_state["additional_context"] = context_input
        # Clear the feedback field after processing
        if "last_initial_context_feedback" in updated_state:
             del updated_state["last_initial_context_feedback"]

    else: # Non-interactive / simulated input
        logger.info("Non-interactive mode: Using simulated context for context_gatherer_node.")
        simulated_context = "This is simulated additional context for the project provided in non-interactive mode."
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_context, name="user_context_simulated")
        ]
        updated_state["additional_context"] = simulated_context
        # updated_state["simulated_input"] = True # This flag might be set elsewhere if globally non-interactive

    # Determine where to go next based on the route_to value or a default
    # Default to coding_planner if route_to is not coding_coordinator
    final_goto = "coding_coordinator" if route_to == "coding_coordinator" else "coding_planner" # Corrected

    logger.info(f"Context gathering complete. Routing to {final_goto}.")
    return Command(update=updated_state, goto=final_goto)

