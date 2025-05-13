# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from .common import *

def context_gatherer_node(state: State) -> Command[Literal["planner", "coding_coordinator"]]:
    """Node that gathers context from the user."""
    logger.info("Gathering context from user...")
    
    # Check if we have a specific node to route to
    route_to = state.get("context_gatherer_route_to")
    
    # Create the interrupt message
    interrupt_message = (
        "I need to gather some additional context before proceeding. "
        "Please provide any relevant information about your request, such as:\n\n"
        "1. Project background\n"
        "2. Technical requirements\n"
        "3. Constraints or limitations\n"
        "4. Any specific technologies or frameworks to use\n"
        "5. Any other relevant details\n\n"
        "This will help me better understand your needs and provide a more accurate solution."
    )
    
    # Add a message to the state so the user sees it
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=interrupt_message, name="context_gatherer")
    ]
    
    # Check if we should wait for input
    wait_for_input = state.get("wait_for_input", True)
    
    if wait_for_input:
        # Interrupt the graph to wait for context
        context = interrupt(interrupt_message)
        
        logger.info(f"Context received: {context[:100]}...")
        
        # Add the user's context to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=context, name="user_context")
        ]
        
        # Store the context in state
        updated_state["additional_context"] = context
        
        # Determine where to go next based on the route_to value
        if route_to == "coding_coordinator":
            logger.info("Routing to coding coordinator with gathered context.")
            return Command(update=updated_state, goto="coding_coordinator")
        else:
            logger.info("Routing to planner with gathered context.")
            return Command(update=updated_state, goto="planner")
    else:
        # Simulate an automatic response if not waiting for input
        logger.info("Not waiting for input. Using simulated context...")
        simulated_context = "This is simulated context for the project."
        
        # Add the simulated context to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_context, name="user_context")
        ]
        
        # Store the context in state
        updated_state["additional_context"] = simulated_context
        updated_state["simulated_input"] = True
        
        # Determine where to go next based on the route_to value
        if route_to == "coding_coordinator":
            logger.info("Routing to coding coordinator with simulated context.")
            return Command(update=updated_state, goto="coding_coordinator")
        else:
            logger.info("Routing to planner with simulated context.")
            return Command(update=updated_state, goto="planner")

