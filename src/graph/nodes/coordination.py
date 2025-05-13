# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

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


def reporter_node(state: State):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    current_plan = state.get("current_plan")
    input_ = {
        "messages": [
            HumanMessage(
                f"# Research Requirements\n\n## Task\n\n{current_plan.title}\n\n## Description\n\n{current_plan.thought}"
            )
        ],
        "locale": state.get("locale", "en-US"),
    }
    invoke_messages = apply_prompt_template("reporter", input_)
    observations = state.get("observations", [])

    # Add a reminder about the new report format, citation style, and table usage
    invoke_messages.append(
        HumanMessage(
            content="IMPORTANT: Structure your report according to the format in the prompt. Remember to include:\n\n1. Key Points - A bulleted list of the most important findings\n2. Overview - A brief introduction to the topic\n3. Detailed Analysis - Organized into logical sections\n4. Survey Note (optional) - For more comprehensive reports\n5. Key Citations - List all references at the end\n\nFor citations, DO NOT include inline citations in the text. Instead, place all citations in the 'Key Citations' section at the end using the format: `- [Source Title](URL)`. Include an empty line between each citation for better readability.\n\nPRIORITIZE USING MARKDOWN TABLES for data presentation and comparison. Use tables whenever presenting comparative data, statistics, features, or options. Structure tables with clear headers and aligned columns. Example table format:\n\n| Feature | Description | Pros | Cons |\n|---------|-------------|------|------|\n| Feature 1 | Description 1 | Pros 1 | Cons 1 |\n| Feature 2 | Description 2 | Pros 2 | Cons 2 |",
            name="system",
        )
    )

    for observation in observations:
        invoke_messages.append(
            HumanMessage(
                content=f"Below are some observations for the research task:\n\n{observation}",
                name="observation",
            )
        )
    logger.debug(f"Current invoke messages: {invoke_messages}")
    response = get_llm_by_type(AGENT_LLM_MAP["reporter"]).invoke(invoke_messages)
    response_content = response.content
    logger.info(f"reporter response: {response_content}")

    return {"final_report": response_content}


def coding_coordinator_node(state: State) -> Command[Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]]:
    """Coordinator node for coding tasks that generates a PRD from user requirements."""
    logger.info("Coding Coordinator generating PRD...")
    
    # Check if we already have a PRD document
    if state.get("prd_document") and not state.get("prd_review_feedback"):
        logger.info("PRD already exists, proceeding to human review.")
        return Command(goto="human_prd_review")
    
    # Check if we have feedback on the PRD that requires revision
    if state.get("prd_review_feedback"):
        feedback = state.get("prd_review_feedback")
        logger.info(f"PRD review feedback received: {feedback[:100]}...")
        
        # If the feedback is approval, proceed to planning
        if "approve" in feedback.lower() or "accept" in feedback.lower() or "good" in feedback.lower():
            logger.info("PRD approved, proceeding to planning.")
            return Command(goto="coding_planner")
        
        # Otherwise, we need to revise the PRD based on feedback
        logger.info("Revising PRD based on feedback.")
        
        # Prepare the prompt for PRD revision
        messages = [
            SystemMessage(content="You are a product manager tasked with revising a Product Requirements Document (PRD) based on user feedback."),
            HumanMessage(content=f"Here is the current PRD:\n\n{state.get('prd_document')}"),
            HumanMessage(content=f"Here is the user's feedback on the PRD:\n\n{feedback}"),
            HumanMessage(content="Please revise the PRD to address the feedback. Maintain the same structure and format, but make the requested changes.")
        ]
        
        # Add any research results if available
        if state.get("research_results"):
            messages.append(HumanMessage(content=f"Here are some research results that may be helpful:\n\n{state.get('research_results')}"))
        
        try:
            # Get the LLM for the coding coordinator
            llm = get_llm_by_type(AGENT_LLM_MAP.get("coding_coordinator", "basic"))
            
            # Generate the revised PRD
            response = llm.invoke(messages)
            revised_prd = response.content
            
            logger.info(f"Generated revised PRD (length: {len(revised_prd)})")
            
            # Update the state with the revised PRD and clear the feedback
            return Command(
                update={
                    "prd_document": revised_prd,
                    "prd_review_feedback": None,  # Clear the feedback since we've addressed it
                    "messages": state.get("messages", []) + [AIMessage(content=revised_prd, name="coding_coordinator")]
                },
                goto="human_prd_review"  # Go back to human review for the revised PRD
            )
            
        except Exception as e:
            logger.error(f"Error revising PRD: {e}")
            error_message = f"I encountered an error trying to revise the PRD based on your feedback. Error: {e}."
            return Command(
                update={"messages": state.get("messages", []) + [AIMessage(content=error_message, name="coding_coordinator")]},
                goto="__end__"
            )
    
    # If we don't have a PRD or feedback, generate a new PRD
    logger.info("Generating new PRD from user requirements.")
    
    # Get the user's requirements from the messages
    user_requirements = ""
    for message in state.get("messages", []):
        if isinstance(message, HumanMessage):
            user_requirements += message.content + "\n\n"
    
    # Prepare the prompt for PRD generation
    messages = [
        SystemMessage(content="You are a product manager tasked with creating a detailed Product Requirements Document (PRD) based on user requirements."),
        HumanMessage(content=f"Here are the user's requirements:\n\n{user_requirements}"),
        HumanMessage(content="Please generate a comprehensive PRD that includes:\n1. Overview\n2. Problem Statement\n3. User Stories\n4. Functional Requirements\n5. Non-Functional Requirements\n6. Technical Constraints\n7. Success Metrics")
    ]
    
    # Add any research results if available
    if state.get("research_results"):
        messages.append(HumanMessage(content=f"Here are some research results that may be helpful:\n\n{state.get('research_results')}"))
    
    # Add any background investigation results if available
    if state.get("background_investigation_results"):
        try:
            bg_results = json.loads(state.get("background_investigation_results"))
            bg_content = "## Background Research\n\n"
            for result in bg_results:
                bg_content += f"### {result.get('title', 'Research Result')}\n\n{result.get('content', '')}\n\n"
            messages.append(HumanMessage(content=f"Here are some background investigation results that may be helpful:\n\n{bg_content}"))
        except Exception as e:
            logger.error(f"Error parsing background investigation results: {e}")
    
    try:
        # Get the LLM for the coding coordinator
        llm = get_llm_by_type(AGENT_LLM_MAP.get("coding_coordinator", "basic"))
        
        # Generate the PRD
        response = llm.invoke(messages)
        prd_document = response.content
        
        logger.info(f"Generated PRD (length: {len(prd_document)})")
        
        # Update the state with the PRD
        return Command(
            update={
                "prd_document": prd_document,
                "messages": state.get("messages", []) + [AIMessage(content=prd_document, name="coding_coordinator")]
            },
            goto="human_prd_review"  # Go to human review for the PRD
        )
        
    except Exception as e:
        logger.error(f"Error generating PRD: {e}")
        error_message = f"I encountered an error trying to generate a PRD from your requirements. Error: {e}."
        return Command(
            update={"messages": state.get("messages", []) + [AIMessage(content=error_message, name="coding_coordinator")]},
            goto="__end__"
        )

