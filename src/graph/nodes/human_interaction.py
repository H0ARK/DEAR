# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

def initial_context_node(state: State) -> Command[Literal["human_initial_context_review"]]:
    """Generate initial context for the user to review."""
    logger.info("Generating initial context...")
    
    # Get the user's query
    query = state.get("messages", [])[-1].content if state.get("messages") else ""
    
    # Generate initial context using web search
    try:
        if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY:
            search_results = LoggedTavilySearch(max_results=SEARCH_MAX_RESULTS).invoke(
                {"query": query}
            )
            
            # Format the search results
            formatted_results = "## Initial Context\n\n"
            
            if isinstance(search_results, list):
                for i, result in enumerate(search_results):
                    formatted_results += f"### {result.get('title', f'Result {i+1}')}\n\n"
                    formatted_results += f"{result.get('content', 'No content available.')}\n\n"
            else:
                formatted_results += "No search results available."
        else:
            search_results = web_search_tool.invoke(query)
            
            # Format the search results
            formatted_results = "## Initial Context\n\n"
            
            if isinstance(search_results, list):
                for i, result in enumerate(search_results):
                    formatted_results += f"### {result.get('title', f'Result {i+1}')}\n\n"
                    formatted_results += f"{result.get('content', 'No content available.')}\n\n"
            else:
                formatted_results += "No search results available."
        
        # Update the state with the initial context
        return Command(
            update={
                "initial_context": formatted_results,
                "messages": state.get("messages", []) + [AIMessage(content=formatted_results, name="initial_context")]
            },
            goto="human_initial_context_review"
        )
        
    except Exception as e:
        logger.error(f"Error generating initial context: {e}")
        error_message = f"I encountered an error trying to generate initial context. Error: {e}."
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content=error_message, name="initial_context")]},
            goto="human_initial_context_review"
        )


def human_prd_review_node(state: State) -> Command[Literal["coding_coordinator", "coding_planner"]]:
    """Node to wait for user feedback on the PRD."""
    logger.info("Waiting for user feedback on the PRD...")
    
    # Get the PRD document
    prd_document = state.get("prd_document")
    if not prd_document:
        logger.error("No PRD document found in state. Cannot review.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No PRD document found. Cannot review.", name="human_prd_review")]},
            goto="coding_coordinator"
        )
    
    # Create the interrupt message
    interrupt_message = (
        f"Here's the Product Requirements Document (PRD) for your request:\n\n"
        f"{prd_document}\n\n"
        f"Please review and provide feedback. You can:\n"
        f"- Approve by saying 'approve' or 'looks good'\n"
        f"- Request revisions by explaining what you'd like changed\n"
    )
    
    # Add a message to the state so the user sees it
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=interrupt_message, name="human_prd_review")
    ]
    
    # Check if we should wait for input
    wait_for_input = state.get("wait_for_input", True)
    
    if wait_for_input:
        # Interrupt the graph to wait for feedback
        prd_feedback = interrupt(interrupt_message)
        
        logger.info(f"PRD feedback received: {prd_feedback[:100]}...")
        
        # Add the user's feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=prd_feedback, name="user_prd_feedback")
        ]
        
        # Store the feedback in state
        updated_state["prd_review_feedback"] = prd_feedback
        
        # Determine where to go next based on the feedback
        if "approve" in prd_feedback.lower() or "accept" in prd_feedback.lower() or "good" in prd_feedback.lower():
            logger.info("PRD approved by user. Proceeding to planning.")
            return Command(update=updated_state, goto="coding_planner")
        else:
            logger.info("User requested revisions to the PRD. Returning to coordinator.")
            return Command(update=updated_state, goto="coding_coordinator")
    else:
        # Simulate an automatic response if not waiting for input
        logger.info("Not waiting for input. Using simulated approval...")
        simulated_feedback = "approve"
        
        # Add the simulated feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_feedback, name="user_prd_feedback")
        ]
        
        # Store the feedback in state
        updated_state["prd_review_feedback"] = simulated_feedback
        
        # Add a record of what happened
        updated_state["simulated_input"] = True
        
        logger.info("PRD auto-approved in non-interactive mode. Proceeding to planning.")
        return Command(update=updated_state, goto="coding_planner")


def human_initial_context_review_node(state: State) -> Command[Literal["coordinator", "context_gatherer"]]:
    """Node to wait for user feedback on the initial context."""
    logger.info("Waiting for user feedback on the initial context...")
    
    # Get the initial context
    initial_context = state.get("initial_context")
    if not initial_context:
        logger.error("No initial context found in state. Cannot review.")
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content="Error: No initial context found. Cannot review.", name="human_initial_context_review")]},
            goto="coordinator"
        )
    
    # Create the interrupt message
    interrupt_message = (
        f"Here's the initial context for your request:\n\n"
        f"{initial_context}\n\n"
        f"Please review and provide feedback. You can:\n"
        f"- Approve by saying 'approve' or 'looks good'\n"
        f"- Request additional information by explaining what you'd like to know more about\n"
    )
    
    # Add a message to the state so the user sees it
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=interrupt_message, name="human_initial_context_review")
    ]
    
    # Check if we should wait for input
    wait_for_input = state.get("wait_for_input", True)
    
    if wait_for_input:
        # Interrupt the graph to wait for feedback
        context_feedback = interrupt(interrupt_message)
        
        logger.info(f"Initial context feedback received: {context_feedback[:100]}...")
        
        # Add the user's feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=context_feedback, name="user_context_feedback")
        ]
        
        # Store the feedback in state
        updated_state["initial_context_feedback"] = context_feedback
        
        # Determine where to go next based on the feedback
        if "approve" in context_feedback.lower() or "accept" in context_feedback.lower() or "good" in context_feedback.lower():
            logger.info("Initial context approved by user. Proceeding to coordinator.")
            return Command(update=updated_state, goto="coordinator")
        else:
            logger.info("User requested additional information. Returning to context gatherer.")
            return Command(update=updated_state, goto="context_gatherer")
    else:
        # Simulate an automatic response if not waiting for input
        logger.info("Not waiting for input. Using simulated approval...")
        simulated_feedback = "approve"
        
        # Add the simulated feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_feedback, name="user_context_feedback")
        ]
        
        # Store the feedback in state
        updated_state["initial_context_feedback"] = simulated_feedback
        
        # Add a record of what happened
        updated_state["simulated_input"] = True
        
        logger.info("Initial context auto-approved in non-interactive mode. Proceeding to coordinator.")
        return Command(update=updated_state, goto="coordinator")

