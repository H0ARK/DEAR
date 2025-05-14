# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig

from .common import *

def background_investigation_node(state: State) -> Command[Literal["context_gatherer"]]:
    logger.info("background investigation node is running.")
    query = state["messages"][-1].content
    if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY:
        searched_content = LoggedTavilySearch(max_results=SEARCH_MAX_RESULTS).invoke(
            {"query": query}
        )
        background_investigation_results = None
        if isinstance(searched_content, list):
            background_investigation_results = [
                {"title": elem["title"], "content": elem["content"]}
                for elem in searched_content
            ]
        else:
            logger.error(
                f"Tavily search returned malformed response: {searched_content}"
            )
    else:
        background_investigation_results = web_search_tool.invoke(query)
    return Command(
        update={
            "background_investigation_results": json.dumps(
                background_investigation_results, ensure_ascii=False
            )
        },
        goto="context_gatherer",
    )


def research_team_node(
    state: State,
) -> Command[Literal["researcher", "task_orchestrator", "coding_coordinator", "coding_planner"]]:
    """Research team node that collaborates on tasks."""
    logger.info("Research team is collaborating on tasks.")
    
    # Check if we should return to a specific node after research
    return_to_node = state.get("research_return_to")
    
    # Check for results that need to be stored
    current_plan = state.get("current_plan")
    observations = state.get("observations", [])
    
    # If we have a clarification request and observations, format them for the coordinator
    if return_to_node == "coding_coordinator" and observations:
        logger.info(f"Storing research results for clarification request.")
        
        # Format clarification research results for the coordinator
        research_results = "## Research Results for Clarification\n\n"
        
        # Add each observation
        for i, observation in enumerate(observations):
            title = f"Research Result {i+1}"
            content = observation
            
            # Check if observation is an object with title and content attributes
            if hasattr(observation, "title") and observation.title:
                title = observation.title
            if hasattr(observation, "content"):
                content = observation.content
            
            research_results += f"### {title}\n\n"
            research_results += f"{content}\n\n"
        
        # Store results in the state for the coordinator
        state["research_results"] = research_results
        
        logger.info(f"Completed research for clarification. Returning to {return_to_node}.")
        return Command(update=state, goto=return_to_node)
    
    # If we have a complete research plan, store results and proceed
    if current_plan and hasattr(current_plan, 'steps') and current_plan.steps and all(step.execution_res for step in current_plan.steps):
        logger.info("All research steps completed. Storing research results.")
        
        # Combine all research results into a consolidated format
        research_results = []
        for step in current_plan.steps:
            # Store each step's result as a separate research result
            result = {
                "title": step.title,
                "content": step.execution_res
            }
            research_results.append(result)
        
        # Store the structured research results in the state
        state["structured_research_results"] = research_results
        
        # If we have a specific node to return to, go there
        if return_to_node:
            logger.info(f"Research complete. Returning to {return_to_node} as specified.")
            return Command(update=state, goto=return_to_node)
        
        # Default to returning to the task orchestrator
        logger.info("Research complete. Returning to task orchestrator.")
        return Command(update=state, goto="task_orchestrator")
    
    # If we don't have a complete plan yet, continue with research
    logger.info("Research plan not complete. Continuing with research.")
    return Command(update=state, goto="researcher")


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


async def researcher_node(state: State, config: RunnableConfig) -> Command[Literal["research_team"]]:
    """Placeholder for the researcher node. Performs a research step."""
    logger.info("Researcher node executing (placeholder)...")
    
    # In a real implementation, this node would:
    # 1. Get the current research step from current_plan.steps
    # 2. Execute the research (e.g., call an LLM with search tools)
    # 3. Store the result in the step's execution_res
    # 4. Update observations or other relevant state fields
    
    # For now, just log and return to research_team
    # Simulate finding some observation
    current_observations = state.get("observations", [])
    new_observation = "Placeholder research observation from researcher_node."
    updated_observations = current_observations + [new_observation]
    
    # Assume the research step (if any was being tracked) is now done
    # and the result is in updated_observations or directly in a step object (not modeled here yet)
    
    return Command(
        update={"observations": updated_observations, "messages": state.get("messages", []) + [AIMessage(content="[Placeholder] Researcher finished a step.", name="researcher")]},
        goto="research_team"
    )

