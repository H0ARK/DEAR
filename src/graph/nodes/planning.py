# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langchain.prompts import PromptTemplate

from .common import *

@tool
def handoff_to_planner(
    task_title: Annotated[str, "The title of the task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return


def coding_planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["human_feedback_plan", "__end__"]]:
    """Planner node that generates a detailed task breakdown from the PRD."""
    logger.info("Coding Planner generating detailed task plan...")
    logger.debug(f"Coding planner state keys: {list(state.keys())}")
    logger.debug(f"simulated_input={state.get('simulated_input', False)}, wait_for_input={state.get('wait_for_input', True)}")
    
    plan_iterations = state.get("plan_iterations", 0) + 1
    configurable = Configuration.from_runnable_config(config)

    if plan_iterations > configurable.max_plan_iterations:
        logger.warning("Max plan iterations reached. Ending workflow.")
        return Command(
            update={"messages": state["messages"] + [AIMessage(content="Maximum plan refinement iterations reached. Please try refining your request.", name="coding_planner")]},
            goto="__end__"
        )

    # Inputs for the planner
    prd_document = state.get("prd_document")
    if not prd_document:
        logger.error("PRD document not found in state. Cannot generate plan.")
        return Command(
            update={"messages": state["messages"] + [AIMessage(content="Error: PRD document is missing. Cannot generate a plan.", name="coding_planner")]},
            goto="__end__" # Or route to coding_coordinator to generate PRD
        )

    # Initialize or retrieve current PRD
    prd_review_feedback = state.get("prd_review_feedback")
    
    # Check for research results in either format
    research_results = state.get("research_results")
    structured_research_results = state.get("structured_research_results")
    
    # If we have structured results but no formatted results, convert them
    if structured_research_results and not research_results:
        research_results = "\n\n## Research Results\n\n"
        for result in structured_research_results:
            research_results += f"### {result['title']}\n\n{result['content']}\n\n"
        state["research_results"] = research_results
        
    existing_project_summary = state.get("existing_project_summary")
    failed_task_details = state.get("failed_task_details") # For re-planning

    # Prepare prompt_state_input for apply_prompt_template
    # The "coding_planner" template should be updated to use these fields.
    prompt_state_input = state.copy() # Start with a copy of the current state
    prompt_state_input["prd_document"] = prd_document
    prompt_state_input["existing_project_summary"] = existing_project_summary
    prompt_state_input["failed_task_details"] = failed_task_details
    # Add any other relevant fields from state that the prompt might need
    # messages = apply_prompt_template("coding_planner", prompt_state_input, configurable)

    # Format prompt using the global constant
    # The old local PLANNING_PROMPT_TEMPLATE_V2 definition will be removed.
    prompt = PromptTemplate.from_template(CODING_PLANNER_TASK_LIST_PROMPT) # Use the global constant

    # Prepare variables for the prompt
    failed_task_details_str = "N/A"

    instruction_message = "Generate a detailed task plan based on the provided Product Requirements Document (PRD)."
    if existing_project_summary:
        instruction_message += " Consider the existing project context."
        # Potentially add existing_project_summary content to messages if not too large

    if failed_task_details:
        instruction_message += f" You are re-planning due to a failed task: {failed_task_details.get('description', 'N/A')}. Please provide a revised plan for this task or related tasks."
        # Add failed_task_details to messages

    # Simplified message construction for now. Real implementation uses apply_prompt_template with an updated template.
    messages = [
        HumanMessage(content=instruction_message),
        HumanMessage(content=f"PRD:\n{prd_document}"),
    ]
    if existing_project_summary:
        messages.append(HumanMessage(content=f"Existing Project Context:\n{json.dumps(existing_project_summary, indent=2)}"))
    if failed_task_details:
        messages.append(HumanMessage(content=f"Details of Failed Task for Re-planning:\n{json.dumps(failed_task_details, indent=2)}"))

    # Append original message history if needed, ensure `apply_prompt_template` handles this correctly.
    # messages = state.get("messages", []) + messages

    logger.info(f"Coding planner inputs: PRD (len {len(prd_document)}), Existing Summary (present: {bool(existing_project_summary)}), Failed Task (present: {bool(failed_task_details)})")

    try:
        # Try to get the LLM using get_llm_by_type first
        try:
            llm = get_llm_by_type("basic")  # Use basic LLM instead of looking up by agent type 
            logger.info("Using 'basic' LLM for coding planner")
        except Exception as llm_error:
            logger.error(f"Error getting basic LLM: {llm_error}. Trying fallback.")
            # Fallback to direct lookup
            llm = get_llm_by_type(AGENT_LLM_MAP.get("coding_planner", ""))
            logger.info(f"Using fallback LLM from AGENT_LLM_MAP for coding planner")
        
        response = llm.invoke(messages) # Pass the constructed messages
        full_response = response.content

        logger.debug(f"Coding Planner raw LLM response: {full_response}")

        # Expecting LLM to output a JSON list of task dictionaries
        # Each task dict should include: id, name, description, dependencies, acceptance_criteria,
        # estimated_effort_hours, assignee_suggestion, status_live (initially Todo), execute_alone, max_retries.
        repaired_json_str = repair_json_output(full_response) # Use repair_json_output here
        logger.debug(f"Coding Planner JSON after repair: {repaired_json_str[:500]}...")
        
        parsed_tasks_from_llm = json.loads(repaired_json_str) # And here
        logger.info(f"Successfully parsed JSON response from LLM")

        if not isinstance(parsed_tasks_from_llm, list): # Check if it's a list
            # If not a list, check if it's a dict with a "tasks" key
            if isinstance(parsed_tasks_from_llm, dict) and "tasks" in parsed_tasks_from_llm and isinstance(parsed_tasks_from_llm["tasks"], list):
                logger.info("LLM returned a dictionary with a 'tasks' key, extracting list from there.")
                parsed_tasks_from_llm = parsed_tasks_from_llm["tasks"]
            else:
                logger.error(f"LLM response for tasks is not a list, nor a dict with a 'tasks' list. Full response: {full_response[:500]}")
                raise ValueError("LLM response for tasks is not in the expected format (list of tasks or {'tasks': [...]}).")

        tasks_definition = []
        for i, task_data in enumerate(parsed_tasks_from_llm): # Iterate over the potentially extracted list
            if not isinstance(task_data, dict):
                logger.warning(f"Task item {i} is not a dictionary: {task_data}. Skipping.")
                continue

            # Validate and default essential fields
            task_id = task_data.get("id")
            if not task_id or not isinstance(task_id, str):
                task_id = f"task_{plan_iterations}_{i+1:03d}" # More unique default ID
                logger.warning(f"Task item {i} missing or invalid 'id'. Defaulting to '{task_id}'.")

            task_name = task_data.get("name")
            if not task_name or not isinstance(task_name, str):
                task_name = f"Unnamed Task {task_id}"
                logger.warning(f"Task item {i} missing or invalid 'name'. Defaulting to '{task_name}'.")

            description = task_data.get("description")
            if not description or not isinstance(description, str):
                description = "No description provided."
                logger.warning(f"Task item {i} missing or invalid 'description'. Defaulting to 'No description provided.'.")

            # Get other fields with defaults
            dependencies = task_data.get("dependencies", [])
            acceptance_criteria = task_data.get("acceptance_criteria", [])
            estimated_effort_hours = task_data.get("estimated_effort_hours", 0) # Default to 0 or None
            assignee_suggestion = task_data.get("assignee_suggestion", "any")
            status_live = task_data.get("status_live", "Todo") # Initial status
            execute_alone = task_data.get("execute_alone", False)
            max_retries = task_data.get("max_retries", 1) # Default from previous logic

            # branch_name and status_in_plan from existing code might be planner's suggestions
            # Let's keep them for now if planner is intended to suggest them.
            suggested_branch_name = task_data.get("branch_name", f"task/{task_id.replace('_', '-')[:20]}") # Cleaner default
            planner_status_suggestion = task_data.get("status_in_plan", "todo")


            if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
                logger.warning(f"Task {task_id} has invalid dependencies format: {dependencies}. Defaulting to empty list.")
                dependencies = []
            if not isinstance(acceptance_criteria, list) or not all(isinstance(ac, str) for ac in acceptance_criteria):
                logger.warning(f"Task {task_id} has invalid acceptance_criteria format: {acceptance_criteria}. Defaulting to empty list.")
                acceptance_criteria = []


            tasks_definition.append({
                "id": task_id,
                "name": task_name,
                "description": description,
                "dependencies": dependencies,
                "acceptance_criteria": acceptance_criteria,
                "estimated_effort_hours": estimated_effort_hours,
                "assignee_suggestion": assignee_suggestion,
                "status_live": status_live, # This will be the initial live status for task_orchestrator
                "execute_alone": execute_alone,
                "max_retries": max_retries,
                "suggested_branch_name": suggested_branch_name, # Planner's suggestion
                "planner_status_suggestion": planner_status_suggestion # Planner's suggested internal status
            })

        if not tasks_definition and parsed_tasks_from_llm: # If list was not empty but parsing all items failed
             logger.error("LLM provided tasks, but all failed detailed parsing. Resulting in empty task list.")
             # This case will lead to an error message below if full_response was not empty.

        if not tasks_definition: # Handles both empty LLM list and parsing failures leading to empty list
             logger.warning(f"LLM parsed response resulted in an empty task list. Raw response: {full_response[:500]}")
             # Fallback: attempt to use the old plan parsing if it looks like the old format
             try:
                 plan_obj = Plan.from_json(repaired_json_str) # Try old format as a last resort
                 logger.warning("LLM response was empty or invalid for new task format. Attempting to parse as old Plan format. This is deprecated.")
                 # Convert Plan object to tasks_definition (simplified)
                 for i_old, step in enumerate(plan_obj.steps):
                     tasks_definition.append({
                         "id": f"old_task_{plan_iterations}_{i_old:03d}",
                         "name": step.title,
                         "description": step.description,
                         "dependencies": [],
                         "acceptance_criteria": [step.validation] if step.validation else [],
                         "estimated_effort_hours": 0,
                         "assignee_suggestion": "any",
                         "status_live": "Todo",
                         "execute_alone": False,
                         "max_retries": 1,
                         "suggested_branch_name": f"task/old-{step.title.lower().replace(' ','-')[:20]}",
                         "planner_status_suggestion": "todo"
                     })
                 if not tasks_definition: # If old format also yielded nothing
                     raise ValueError("Old plan format conversion also resulted in no tasks.")
                 logger.info(f"Successfully converted {len(tasks_definition)} tasks from old Plan format.")
             except Exception as old_format_e:
                 logger.error(f"Failed to parse as new tasks format and also failed to parse/convert from old Plan format: {old_format_e}. Raising error to go to __end__.")
                 # Raise the error to be caught by the outer try-except, which goes to __end__
                 raise ValueError(f"Could not parse tasks from LLM, and fallback to old format also failed. Original error: {old_format_e}. LLM raw: {full_response[:200]}") from old_format_e


        logger.info(f"Successfully parsed and validated {len(tasks_definition)} tasks.")

        updated_state = {
            "messages": state["messages"] + [AIMessage(content=full_response, name="coding_planner")],
            "tasks_definition": tasks_definition, # New state field
            "plan_iterations": plan_iterations,
            "failed_task_details": None # Clear after re-planning
        }
        
        # Check if we're in non-interactive mode to automatically proceed
        if state.get("simulated_input", False) or not state.get("wait_for_input", True):
            logger.info("Non-interactive mode detected. Setting simulated approval for task plan.")
            updated_state["plan_feedback"] = "approve"
            updated_state["simulated_input"] = True
        
        logger.info("Successfully created tasks definition, routing to human_feedback_plan")
        return Command(update=updated_state, goto="human_feedback_plan")

    except Exception as e:
        logger.error(f"Error parsing detailed task plan from LLM: {e}")
        error_message = f"I encountered an error trying to structure the detailed task plan. Error: {e}."
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=error_message, name="coding_planner")],
                "plan_iterations": plan_iterations,
                "failed_task_details": None # Clear even on error if it was a re-plan attempt
            },
            goto="__end__"
        )


def human_feedback_plan_node(state: State) -> Command[Literal["coding_planner", "linear_integration"]]:
    """Node to wait for user feedback on the planning."""
    logger.info("Waiting for user feedback on the plan...")

    # Get the current plan and number of iterations
    current_plan = state.get("current_plan")
    plan_feedback_iterations = state.get("plan_feedback_iterations", 0)
    
    # Extract plan details for the interrupt message
    if isinstance(current_plan, (Plan, dict)):
        if isinstance(current_plan, dict) and "steps" in current_plan:
            steps = current_plan["steps"]
        elif hasattr(current_plan, "steps"):
            steps = current_plan.steps
        else:
            steps = []
        
        # Format steps for display
        formatted_steps = ""
        for i, step in enumerate(steps):
            step_desc = step.description if hasattr(step, "description") else step.get("description", "Unknown step")
            formatted_steps += f"\n{i+1}. {step_desc}"
    else:
        formatted_steps = "No detailed steps available."
    
    # Create the interrupt message
    interrupt_message = (
        f"Here's the proposed plan for implementing your request:\n\n"
        f"{formatted_steps}\n\n"
        f"Please review and provide feedback. You can:\n"
        f"- Approve by saying 'approve' or 'looks good'\n"
        f"- Request revisions by explaining what you'd like changed\n"
    )
    
    # Add a message to the state so the user sees it
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=interrupt_message, name="human_feedback_plan")
    ]
    
    # Check if we should wait for input
    wait_for_input = state.get("wait_for_input", True)
    
    if wait_for_input:
        # Interrupt the graph to wait for feedback
        plan_feedback = interrupt(interrupt_message)
        
        logger.info(f"Plan feedback received: {plan_feedback[:100]}...")
        
        # Add the user's feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=plan_feedback, name="user_plan_feedback")
        ]
        
        # Store the feedback in state
        updated_state["plan_feedback"] = plan_feedback
        updated_state["plan_feedback_iterations"] = plan_feedback_iterations + 1
        
        # Determine where to go next based on the feedback
        if "approve" in plan_feedback.lower() or "accept" in plan_feedback.lower() or "good" in plan_feedback.lower():
            logger.info("Plan approved by user. Proceeding to implementation.")
            return Command(update=updated_state, goto="linear_integration")
        else:
            logger.info("User requested revisions to the plan. Returning to planner.")
            return Command(update=updated_state, goto="coding_planner")
    else:
        # Simulate an automatic response if not waiting for input
        logger.info("Not waiting for input. Using simulated approval...")
        simulated_feedback = "approve"
        
        # Add the simulated feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_feedback, name="user_plan_feedback")
        ]
        
        # Store the feedback in state
        updated_state["plan_feedback"] = simulated_feedback
        updated_state["plan_feedback_iterations"] = plan_feedback_iterations + 1
        
        # Add a record of what happened
        updated_state["simulated_input"] = True
        
        logger.info("Plan auto-approved in non-interactive mode. Proceeding to implementation.")
        return Command(update=updated_state, goto="linear_integration")


def human_prd_review_node(state: State) -> Command[Literal["coding_coordinator"]]:
    """Node to wait for user feedback on the PRD."""
    logger.info("Waiting for user feedback on the PRD...")
    
    # Get the PRD document and number of iterations
    prd_document = state.get("prd_document", "")
    prd_review_iterations = state.get("prd_review_iterations", 0)
    
    # Create the interrupt message
    interrupt_message = (
        f"Here's the Product Requirements Document (PRD) I've created based on your request:\n\n"
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
        updated_state["prd_review_iterations"] = prd_review_iterations + 1
        
        # Always return to the coordinator to handle the feedback
        logger.info("PRD feedback received. Returning to coordinator.")
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
        updated_state["prd_review_iterations"] = prd_review_iterations + 1
        
        # Add a record of what happened
        updated_state["simulated_input"] = True
        
        logger.info("PRD auto-approved in non-interactive mode. Returning to coordinator.")
        return Command(update=updated_state, goto="coding_coordinator")


def human_initial_context_review_node(state: State) -> Command[Literal["coding_coordinator", "human_initial_context_review"]]:
    """Node to wait for user feedback on the initial context."""
    logger.info("Waiting for user feedback on the initial context...")
    
    # Get the initial context and number of iterations
    initial_context = state.get("initial_context", "")
    initial_context_review_iterations = state.get("initial_context_review_iterations", 0)
    
    # Create the interrupt message
    interrupt_message = (
        f"Here's the initial context I've gathered for your request:\n\n"
        f"{initial_context}\n\n"
        f"Please review and provide feedback. You can:\n"
        f"- Approve by saying 'approve' or 'looks good'\n"
        f"- Request revisions by explaining what you'd like changed\n"
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
        initial_context_feedback = interrupt(interrupt_message)
        
        logger.info(f"Initial context feedback received: {initial_context_feedback[:100]}...")
        
        # Add the user's feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=initial_context_feedback, name="user_initial_context_feedback")
        ]
        
        # Store the feedback in state
        updated_state["initial_context_feedback"] = initial_context_feedback
        updated_state["initial_context_review_iterations"] = initial_context_review_iterations + 1
        
        # Determine where to go next based on the feedback
        if "approve" in initial_context_feedback.lower() or "accept" in initial_context_feedback.lower() or "good" in initial_context_feedback.lower():
            logger.info("Initial context approved by user. Proceeding to coordinator.")
            return Command(update=updated_state, goto="coding_coordinator")
        else:
            logger.info("User requested revisions to the initial context. Returning to initial context review.")
            return Command(update=updated_state, goto="human_initial_context_review")
    else:
        # Simulate an automatic response if not waiting for input
        logger.info("Not waiting for input. Using simulated approval...")
        simulated_feedback = "approve"
        
        # Add the simulated feedback to the message history
        updated_state["messages"] = updated_state["messages"] + [
            HumanMessage(content=simulated_feedback, name="user_initial_context_feedback")
        ]
        
        # Store the feedback in state
        updated_state["initial_context_feedback"] = simulated_feedback
        updated_state["initial_context_review_iterations"] = initial_context_review_iterations + 1
        
        # Add a record of what happened
        updated_state["simulated_input"] = True
        
        logger.info("Initial context auto-approved in non-interactive mode. Proceeding to coordinator.")
        return Command(update=updated_state, goto="coding_coordinator")

