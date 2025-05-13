# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .common import *

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
    
    # If we don't have a complete plan or results, proceed to the researcher
    logger.info("Research plan incomplete. Proceeding to researcher.")
    return Command(update=state, goto="researcher")

