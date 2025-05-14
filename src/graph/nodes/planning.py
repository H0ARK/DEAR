# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal, Annotated
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langchain_core.tools import tool
from langchain.prompts import PromptTemplate
from langgraph.errors import GraphInterrupt # Import GraphInterrupt

from .common import *
from src.prompts.planner_model import Plan

# === New Global Prompt for Coding Planner ===
CODING_PLANNER_TASK_LIST_PROMPT = """You are an expert software architect. Your goal is to create a detailed, actionable task plan based on the provided Product Requirements Document (PRD).
Consider the existing project context, conversation history, and any specific failed tasks that require re-planning.

Inputs:
- PRD: {prd_document}
- Existing Project Summary: {existing_project_summary}
- Conversation History (for context): {conversation_history}
- Failed Task Details (for re-planning, if any): {failed_task_details_str}

Your output MUST be a single JSON list of task objects. Do NOT include any text or markdown formatting outside of this JSON list.
Each task object in the list MUST conform to the following structure:
{{
  "id": "string (globally unique task identifier, e.g., task_001)",
  "name": "string (concise and descriptive name for the task)",
  "description": "string (detailed explanation of what needs to be done for this task, including specific deliverables or outcomes)",
  "dependencies": ["list of strings (IDs of other tasks this task depends on, empty if none)"],
  "acceptance_criteria": ["list of strings (specific, measurable criteria for task completion)"],
  "estimated_effort_hours": "integer (optional, estimated hours to complete the task, e.g., 4)",
  "assignee_suggestion": "string (optional, suggested role or type of assignee, e.g., frontend_dev, backend_dev, any)",
  "status_live": "string (initial status, should usually be 'Todo')",
  "execute_alone": "boolean (true if this task must be executed alone without other parallel tasks, default false)",
  "max_retries": "integer (how many times this task should be retried on failure, e.g., 1)",
  "suggested_branch_name": "string (optional, a suggested Git branch name for this task, e.g., task/setup-database-schema)",
  "planner_status_suggestion": "string (optional, your internal status suggestion for this task in the plan, e.g., todo, needs_clarification)"
}}

Example of the expected JSON list output:
```json
[
  {{
    "id": "task_001",
    "name": "Setup Database Schema",
    "description": "Define and implement the initial database schema based on Appendix A of the PRD. Include tables for Users, Products, and Orders.",
    "dependencies": [],
    "acceptance_criteria": [
      "Users table created with all specified fields.",
      "Products table created with all specified fields.",
      "Orders table created with all specified fields and foreign keys."
    ],
    "estimated_effort_hours": 3,
    "assignee_suggestion": "backend_dev",
    "status_live": "Todo",
    "execute_alone": false,
    "max_retries": 1,
    "suggested_branch_name": "task/setup-db-schema",
    "planner_status_suggestion": "todo"
  }},
  {{
    "id": "task_002",
    "name": "Implement User Authentication API",
    "description": "Develop API endpoints for user registration, login, and logout. Refer to PRD section 3.2 for requirements.",
    "dependencies": ["task_001"],
    "acceptance_criteria": [
      "POST /register endpoint works as specified.",
      "POST /login endpoint authenticates users and returns a token.",
      "POST /logout endpoint invalidates user session."
    ],
    "estimated_effort_hours": 5,
    "assignee_suggestion": "backend_dev",
    "status_live": "Todo",
    "execute_alone": false,
    "max_retries": 1,
    "suggested_branch_name": "task/user-auth-api",
    "planner_status_suggestion": "todo"
  }}
]
```

Ensure all task IDs are unique within the generated plan.
Focus on breaking down the PRD into actionable development tasks that can be implemented and tested.
If re-planning due to a failed task ({failed_task_details_str}), integrate the necessary revisions smoothly, focusing on the failed task and its direct dependents or prerequisites. You may need to modify existing tasks, add new ones, or remove obsolete ones related to the failure.

Now, generate the JSON task list.
"""

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
    conversation_history = state.get("messages", []) # For context

    # Prepare prompt_state_input for apply_prompt_template
    # The "coding_planner" template should be updated to use these fields.
    prompt_state_input = state.copy() # Start with a copy of the current state
    prompt_state_input["prd_document"] = prd_document
    prompt_state_input["existing_project_summary"] = existing_project_summary
    prompt_state_input["failed_task_details"] = failed_task_details
    prompt_state_input["conversation_history"] = conversation_history
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


def human_feedback_plan_node(state: State) -> dict:
    """Node to manage iterative user feedback on the generated plan."""
    logger.info("Human reviewing generated plan...")
    
    updated_state_dict = {}
    current_messages = list(state.get("messages", []))
    feedback = state.get("last_plan_feedback")
    iterations = state.get("plan_review_iterations", 0) + 1
    updated_state_dict["plan_review_iterations"] = iterations

    # Clear pending query and awaiting flag from previous turn
    updated_state_dict["pending_plan_review_query"] = None
    # awaiting_plan_review_input will be set to True later if we need to wait

    if feedback:
        logger.info(f"Plan feedback received: {feedback[:100]}...")
        current_messages.append(HumanMessage(content=feedback, name="user_plan_feedback"))
        updated_state_dict["last_plan_feedback"] = None # Clear feedback after processing

        if "approve" in feedback.lower() or "accept" in feedback.lower() or "good" in feedback.lower():
            logger.info("Plan approved by user.")
            updated_state_dict["plan_approved"] = True
            current_messages.append(AIMessage(content="Plan approved. Proceeding to implementation.", name="human_feedback_plan"))
        else:
            logger.info("User requested revisions to the plan.")
            updated_state_dict["plan_approved"] = False
            # The feedback itself (stored in messages) will be used by coding_planner
            current_messages.append(AIMessage(content=f"Revisions requested for the plan: {feedback}", name="human_feedback_plan"))
        updated_state_dict["awaiting_plan_review_input"] = False
    else:
        # No feedback, so generate query and wait
        logger.info("No plan feedback yet. Generating query for user.")
        tasks_definition = state.get("tasks_definition")
        
        formatted_steps = "No detailed task steps available in the current plan."
        if tasks_definition and isinstance(tasks_definition, list):
            formatted_steps = ""
            for i, task in enumerate(tasks_definition):
                task_name = task.get("name", f"Unnamed Task {i+1}")
                task_desc = task.get("description", "No description.")
                dependencies = task.get("dependencies", [])
                deps_str = f"(depends on: {', '.join(dependencies)})" if dependencies else ""
                formatted_steps += f"\n{i+1}. {task_name}: {task_desc} {deps_str}"

        query_message = (
            f"Here's the proposed task plan:\n"
            f"{formatted_steps}\n\n"
            f"Please review and provide feedback. You can:\n"
            f"- Type 'approve' or 'looks good' to accept the plan.\n"
            f"- Describe the changes you'd like if revisions are needed."
        )
        current_messages.append(AIMessage(content=query_message, name="human_feedback_plan"))
        updated_state_dict["pending_plan_review_query"] = query_message
        updated_state_dict["awaiting_plan_review_input"] = True
        updated_state_dict["plan_approved"] = False # Ensure not approved while waiting

    updated_state_dict["messages"] = current_messages
    # return updated_state_dict # OLD: returning state, causing loop
    
    # THIS IS THE KEY: Signal to the graph to interrupt and wait for external feedback
    if updated_state_dict.get("awaiting_plan_review_input", False):
        logger.critical(f"GRAPH: human_feedback_plan_node DETECTED need for human input. Raising GraphInterrupt.")
        # Update state before raising exception so it's saved
        raise GraphInterrupt()
        
    # If not awaiting input (i.e., feedback was processed), return the state
    return updated_state_dict


def human_prd_review_node(state: State) -> dict:
    """Node to manage iterative user feedback on the PRD."""
    logger.info("Human reviewing PRD...")

    updated_state_dict = {}
    current_messages = list(state.get("messages", []))
    feedback = state.get("last_prd_feedback") 
    iterations = state.get("prd_review_iterations", 0) + 1
    updated_state_dict["prd_review_iterations"] = iterations

    updated_state_dict["pending_prd_review_query"] = None
    # awaiting_prd_review_input will be set to True later if we need to wait

    if feedback:
        logger.info(f"PRD feedback received: {feedback[:100]}...")
        current_messages.append(HumanMessage(content=feedback, name="user_prd_feedback"))
        updated_state_dict["last_prd_feedback"] = None # Clear feedback

        if "approve" in feedback.lower() or "accept" in feedback.lower() or "good" in feedback.lower():
            logger.info("PRD approved by user.")
            updated_state_dict["prd_approved"] = True
            current_messages.append(AIMessage(content="PRD approved. Proceeding to planning.", name="human_prd_review"))
        else:
            logger.info("User requested revisions to the PRD.")
            updated_state_dict["prd_approved"] = False
            current_messages.append(AIMessage(content=f"Revisions requested for the PRD: {feedback}", name="human_prd_review"))
        updated_state_dict["awaiting_prd_review_input"] = False
    else:
        logger.info("No PRD feedback yet. Generating query for user.")
        prd_document = state.get("prd_document", "No PRD document available.")
        
        query_message = (
            f"Here's the Product Requirements Document (PRD) I've drafted or updated:\n\n"
            f"{prd_document}\n\n"
            f"Please review and provide feedback. You can:\n"
            f"- Type 'approve' or 'looks good' to accept the PRD.\n"
            f"- Describe the changes you'd like if revisions are needed."
        )
        current_messages.append(AIMessage(content=query_message, name="human_prd_review"))
        updated_state_dict["pending_prd_review_query"] = query_message
        updated_state_dict["awaiting_prd_review_input"] = True
        updated_state_dict["prd_approved"] = False # Ensure not approved

    updated_state_dict["messages"] = current_messages
    
    # THIS IS THE KEY: Signal to the graph to interrupt and wait for external feedback
    if updated_state_dict.get("awaiting_prd_review_input", False):
        logger.critical(f"GRAPH: human_prd_review_node DETECTED need for human input. Raising GraphInterrupt.")
        # Update state before raising exception so it's saved
        # The state is already updated in updated_state_dict, just need to ensure it's the last thing before the raise
        raise GraphInterrupt()
    
    # If not awaiting input (i.e., feedback was processed), return the state
    return updated_state_dict


def human_initial_context_review_node(state: State) -> dict:
    """Node to manage iterative user feedback on initial context information."""
    logger.info("Human reviewing initial context...")
    
    updated_state_dict = {}
    current_messages = list(state.get("messages", []))
    feedback = state.get("last_initial_context_feedback")
    iterations = state.get("initial_context_iterations", 0) + 1 # Note: state key is initial_context_iterations
    updated_state_dict["initial_context_iterations"] = iterations

    updated_state_dict["pending_initial_context_query"] = None
    # awaiting_initial_context_input will be set to True later if we need to wait

    if feedback:
        logger.info(f"Initial context feedback received: {feedback[:100]}...")
        current_messages.append(HumanMessage(content=feedback, name="user_initial_context_feedback"))
        updated_state_dict["last_initial_context_feedback"] = None # Clear feedback

        if "approve" in feedback.lower() or "accept" in feedback.lower() or "good" in feedback.lower():
            logger.info("Initial context approved by user.")
            updated_state_dict["initial_context_approved"] = True
            current_messages.append(AIMessage(content="Initial context approved. Proceeding.", name="human_initial_context_review"))
        else:
            logger.info("User requested revisions to the initial context.")
            updated_state_dict["initial_context_approved"] = False
            current_messages.append(AIMessage(content=f"Revisions requested for initial context: {feedback}", name="human_initial_context_review"))
        updated_state_dict["awaiting_initial_context_input"] = False
    else:
        logger.info("No initial context feedback yet. Generating query for user.")
        # This node assumes initial_context_summary is already populated by a previous node.
        initial_context_summary = state.get("initial_context_summary", "No initial context summary available.")
        
        query_message = (
            f"I've gathered the following initial context about your project:\n\n"
            f"{initial_context_summary}\n\n"
            f"Please review this. Is this understanding correct and complete? You can:\n"
            f"- Type 'approve' or 'looks good' to confirm.\n"
            f"- Provide corrections or additional details if needed."
        )
        current_messages.append(AIMessage(content=query_message, name="human_initial_context_review"))
        updated_state_dict["pending_initial_context_query"] = query_message
        updated_state_dict["awaiting_initial_context_input"] = True
        updated_state_dict["initial_context_approved"] = False # Ensure not approved

    updated_state_dict["messages"] = current_messages
    # return updated_state_dict # OLD: returning state, causing loop
    
    # THIS IS THE KEY: Signal to the graph to interrupt and wait for external feedback
    if updated_state_dict.get("awaiting_initial_context_input", False):
        logger.critical(f"GRAPH: human_initial_context_review_node DETECTED need for human input. Raising GraphInterrupt.")
        # Update state before raising exception so it's saved
        raise GraphInterrupt()
        
    # If not awaiting input (i.e., feedback was processed), return the state
    return updated_state_dict

