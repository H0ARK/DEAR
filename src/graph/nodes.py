# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# This file is maintained for backward compatibility
# It re-exports all functions from the nodes package

from .nodes import *


@tool
def handoff_to_planner(
    task_title: Annotated[str, "The title of the task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return


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

        # Default path - research complete, proceed to coding coordinator
        logger.info("Research complete. Proceeding to coding coordinator.")
        return Command(update=state, goto="coding_coordinator")

    # If we have a plan but still have steps to execute
    if current_plan and hasattr(current_plan, 'steps') and current_plan.steps and any(step.execution_res is None for step in current_plan.steps):
        # Find the first step that hasn't been executed yet
        for step in current_plan.steps:
            if step.execution_res is None:
                logger.info(f"Executing research step: {step.title}")
                return Command(update=state, goto="researcher")

    # If no plan exists or no steps to execute
    if return_to_node:
        logger.info(f"No research plan or all steps complete. Returning to {return_to_node}.")
        return Command(update=state, goto=return_to_node)

    # Default fallback path
    logger.info("No research plan. Default to researcher for initial research.")
    return Command(update=state, goto="researcher")


async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team"]]:
    """Helper function to execute a step using the specified agent."""
    current_plan = state.get("current_plan")
    observations = state.get("observations", [])

    # Check if current_plan is None or doesn't have steps
    if current_plan is None or not hasattr(current_plan, 'steps') or not current_plan.steps:
        logger.warning(f"No current plan or plan has no steps. Agent: {agent_name}")
        # Handle the case where there's no plan - use the last message as the task
        last_message = state["messages"][-1].content if state.get("messages") else "No task specified"

        # Prepare a simple input for the agent based on the last message
        agent_input = {
            "messages": [
                HumanMessage(
                    content=f"#Task\n\n##description\n\n{last_message}\n\n##locale\n\n{state.get('locale', 'en-US')}"
                )
            ]
        }

        # Set a placeholder step for logging
        step = type('Step', (), {'title': 'Direct task', 'description': last_message, 'execution_res': None})
    else:
        # Find the first unexecuted step
        step = None
        for s in current_plan.steps:
            if not s.execution_res:
                step = s
                break

        # If all steps are executed or no steps found, use a default task
        if step is None:
            logger.warning(f"All steps in plan are already executed or no steps found. Agent: {agent_name}")
            last_message = state["messages"][-1].content if state.get("messages") else "No task specified"
            step = type('Step', (), {'title': 'Additional task', 'description': last_message, 'execution_res': None})

        logger.info(f"Executing step: {step.title}")

        # Prepare the input for the agent
        agent_input = {
            "messages": [
                HumanMessage(
                    content=f"#Task\n\n##title\n\n{step.title}\n\n##description\n\n{step.description}\n\n##locale\n\n{state.get('locale', 'en-US')}"
                )
            ]
        }

    # Add citation reminder for researcher agent
    if agent_name == "researcher":
        agent_input["messages"].append(
            HumanMessage(
                content="IMPORTANT: DO NOT include inline citations in the text. Instead, track all sources and include a References section at the end using link reference format. Include an empty line between each citation for better readability. Use this format for each reference:\n- [Source Title](URL)\n\n- [Another Source](URL)",
                name="system",
            )
        )

    # Invoke the agent
    result = await agent.ainvoke(input=agent_input)

    # Process the result
    response_content = result["messages"][-1].content
    logger.debug(f"{agent_name.capitalize()} full response: {response_content}")

    # Update the step with the execution result if it's a real step from a plan
    if hasattr(step, 'execution_res') and step.execution_res is None:
        step.execution_res = response_content
        logger.info(f"Step '{step.title}' execution completed by {agent_name}")
    else:
        logger.info(f"Task '{step.title}' completed by {agent_name} (not part of a formal plan)")

    # Always return to research_team for routing
    # The research_team_node and route_from_research_team will determine the next node
    logger.debug(f"Agent step completed. Returning to research_team for routing.")

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response_content,
                    name=agent_name,
                )
            ],
            "observations": observations + [response_content],
        },
        goto="research_team",  # Always go back to research_team for routing
    )


async def _setup_and_execute_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_agent,
    default_tools: list,
) -> Command[Literal["research_team"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_agent: The default agent to use if no MCP servers are configured
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team
    """
    configurable = Configuration.from_runnable_config(config)
    mcp_servers = {}
    enabled_tools = {}

    # Extract MCP server configuration for this agent type
    if configurable.mcp_settings:
        for server_name, server_config in configurable.mcp_settings["servers"].items():
            if (
                server_config["enabled_tools"]
                and agent_type in server_config["add_to_agents"]
            ):
                mcp_servers[server_name] = {
                    k: v
                    for k, v in server_config.items()
                    if k in ("transport", "command", "args", "url", "env")
                }
                for tool_name in server_config["enabled_tools"]:
                    enabled_tools[tool_name] = server_name

    # Create and execute agent with MCP tools if available
    if mcp_servers:
        async with MultiServerMCPClient(mcp_servers) as client:
            loaded_tools = default_tools[:]
            for tool in client.get_tools():
                if tool.name in enabled_tools:
                    tool.description = (
                        f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                    )
                    loaded_tools.append(tool)
            agent = create_agent(agent_type, agent_type, loaded_tools, agent_type)
            return await _execute_agent_step(state, agent, agent_type)
    else:
        # Use default agent if no MCP servers are configured
        return await _execute_agent_step(state, default_agent, agent_type)


async def researcher_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Researcher node that do research"""
    logger.info("Researcher node is researching.")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "researcher",
        research_agent,
        [web_search_tool, crawl_tool],
    )


async def coder_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team", "__end__"]]:
    """Coder node that do code analysis."""
    logger.warning("coder_node is entirely commented out and should not be called.")
    # Original content commented out to prevent any potential interference:
    # logger.info("Coder node is coding.")
    #
    # # Check if we have workspace information and switch to the workspace branch
    # if state.get("context_info") and state["context_info"].get("workspace"):
    #     try:
    #         import os
    #         workspace = state["context_info"]["workspace"]
    #         logger.info(f"Ensuring coder is on workspace branch {workspace['branch_name']}")
    #
    #         # Import the workspace manager
    #         from src.tools.workspace_manager import WorkspaceManager
    #
    #         # Create the workspace manager
    #         workspace_manager = WorkspaceManager(os.getcwd())
    #
    #         # Switch to the workspace branch
    #         workspace_manager.switch_to_workspace(workspace["id"])
    #         logger.info(f"Successfully switched to workspace branch {workspace['branch_name']}")
    #     except Exception as ws_error:
    #         logger.error(f"Error switching to workspace branch: {ws_error}", exc_info=True)
    # elif state.get("context_info") and state["context_info"].get("current_branch"):
    #     # If we're not using workspaces, log the current branch
    #     current_branch = state["context_info"]["current_branch"]
    #     logger.info(f"Using current branch: {current_branch}")
    #
    # return await _setup_and_execute_agent_step(
    #     state,
    #     config,
    #     "coder",
    #     coder_agent,
    #     [python_repl_tool],
    # )
    # Return a dummy command to satisfy type hints if absolutely necessary,
    # though this node should not be reached.
    return Command(goto="__end__")


# === Coding Flow Nodes ===

def coding_coordinator_node(state: State) -> Command[Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]]:
    """Node that coordinates coding planning."""

    logger.info("Coding coordinator is processing...")
    logger.debug(f"Coding coordinator state keys: {list(state.keys())}")
    logger.debug(f"simulated_input={state.get('simulated_input', False)}, wait_for_input={state.get('wait_for_input', True)}")

    # If we're in non-interactive mode and no PRD document exists yet,
    # generate one and skip the review phase
    if state.get("simulated_input", False) or not state.get("wait_for_input", True):
        logger.info("Non-interactive mode detected in coding coordinator")

        # If we already have a PRD document and it's been auto-approved, go to planning
        if state.get("prd_document") and (state.get("prd_review_feedback", "").lower() == "approve"
                                         or state.get("prd_status") == "auto_approved"
                                         or state.get("prd_status") == "approved"):
            logger.info("PRD exists and has been auto-approved. Proceeding to coding planner.")
            updated_state = state.copy()
            updated_state.update({
                "messages": state.get("messages", []) + [
                    AIMessage(content="PRD has been approved. Proceeding to create a detailed coding plan.", name="coding_coordinator")
                ],
                "prd_status": "approved"
            })
            # Ensure simulated_input flag is preserved
            if "simulated_input" not in updated_state:
                updated_state["simulated_input"] = state.get("simulated_input", False)

            logger.debug(f"Updated state flags when going to planner: simulated_input={updated_state.get('simulated_input', False)}")
            return Command(update=updated_state, goto="coding_planner")

        # If no PRD document exists yet, create one
        if not state.get("prd_document"):
            logger.info("Creating PRD in non-interactive mode.")

            # Parse the messages to get context
            original_query = ""
            messages = state.get("messages", [])
            for message in messages:
                if hasattr(message, "type") and message.type == "human" and not original_query:
                    original_query = message.content
                elif hasattr(message, "role") and message.role == "user" and not original_query:
                    original_query = message.content

            try:
                # Use the "basic" LLM instead of looking up by "coding_coordinator"
                llm = get_llm_by_type("basic")
                context = f"""Original request: {original_query}\n"""

                prompt = "Create a comprehensive PRD (Product Requirements Document) for this request."

                system_message = SystemMessage(content=f"You are an expert software architect creating a Product Requirements Document. {prompt}")

                llm_response = llm.invoke([
                    system_message,
                    HumanMessage(content=context),
                ])

                updated_state = state.copy()
                updated_state["prd_document"] = llm_response.content
                updated_state["prd_status"] = "approved"  # Auto-approve in non-interactive mode
                updated_state["prd_review_feedback"] = "approve"  # Simulate approval feedback

                # Add the PRD to the message history
                updated_state["messages"] = updated_state["messages"] + [
                    AIMessage(content=f"I've prepared a Product Requirements Document and auto-approved it in non-interactive mode:\n\n{llm_response.content}",
                             name="coding_coordinator")
                ]

                # Ensure simulated_input flag is preserved
                if "simulated_input" not in updated_state:
                    updated_state["simulated_input"] = state.get("simulated_input", False)

                logger.info("PRD created and auto-approved in non-interactive mode. Proceeding to coding planner.")
                logger.debug(f"Updated state flags: simulated_input={updated_state.get('simulated_input', False)}, prd_status={updated_state.get('prd_status')}")
                return Command(update=updated_state, goto="coding_planner")

            except Exception as e:
                logger.error(f"Error creating PRD in non-interactive mode: {str(e)}")
                return Command(
                    update={
                        "messages": state.get("messages", []) + [
                            AIMessage(content=f"I encountered an error while preparing your PRD: {str(e)}", name="coding_coordinator")
                        ],
                        "error": str(e),
                        "simulated_input": state.get("simulated_input", False)  # Preserve the flag
                    },
                    goto="__end__"
                )

    # Check for existing PRD
    prd_document = state.get("prd_document", "")
    prd_status = state.get("prd_status", "")

    # Get the previous feedback if any
    prd_review_feedback = state.get("prd_review_feedback", "")

    # Parse the messages to get context
    original_query = ""
    messages = state.get("messages", [])
    for message in messages:
        if hasattr(message, "type") and message.type == "human" and not original_query:
            original_query = message.content
        elif hasattr(message, "role") and message.role == "user" and not original_query:
            original_query = message.content

    # If we don't have a PRD yet or the PRD needs revision
    if not prd_document or "revision" in prd_status.lower():
        # Check if we need to gather more context
        if "research needed" in prd_review_feedback.lower() or "more information" in prd_review_feedback.lower():
            logger.info("Coordinator detected request for more research.")
            updated_state = state.copy()
            updated_state.update({
                "messages": state.get("messages", []) + [
                    AIMessage(content="I'll gather more information to help clarify your request.", name="coding_coordinator")
                ],
                "research_context": original_query,
                "research_question": prd_review_feedback,
                "research_return_to": "coding_coordinator"
            })
            return Command(update=updated_state, goto="context_gatherer")
        else:
            # Either create initial PRD or update existing one
            updated_state = state.copy()

            # This would call an LLM to create or update the PRD based on all available information
            try:
                # Use the "basic" LLM instead of looking up by "coding_coordinator"
                llm = get_llm_by_type("basic")
                context = f"""Original request: {original_query}\n"""

                if prd_document:
                    context += f"""Existing PRD:\n{prd_document}\n"""
                    context += f"""Feedback on PRD:\n{prd_review_feedback}\n"""
                    prompt = "Based on the user's feedback, please revise the PRD to better meet their requirements."
                else:
                    context += """Create a comprehensive PRD (Product Requirements Document) for this request."""
                    prompt = "Please create a clear and comprehensive PRD that details the requirements for this project."

                system_message = SystemMessage(content=f"You are an expert software architect creating a Product Requirements Document. {prompt}")

                llm_response = llm.invoke([
                    system_message,
                    HumanMessage(content=context),
                ])

                updated_state["prd_document"] = llm_response.content
                updated_state["prd_status"] = "awaiting_review"

                # Add the PRD to the message history
                updated_state["messages"] = updated_state["messages"] + [
                    AIMessage(content=f"I've prepared a Product Requirements Document for your review:\n\n{llm_response.content}",
                             name="coding_coordinator")
                ]

                logger.info("PRD created or updated, routing to human review.")
                return Command(update=updated_state, goto="human_prd_review")

            except Exception as e:
                logger.error(f"Error creating PRD: {str(e)}")
                return Command(
                    update={
                        "messages": state.get("messages", []) + [
                            AIMessage(content=f"I encountered an error while preparing your PRD: {str(e)}", name="coding_coordinator")
                        ],
                        "error": str(e),
                        "simulated_input": state.get("simulated_input", False)  # Preserve the flag
                    },
                    goto="__end__"
                )

    # If we have an approved PRD, proceed to planning
    elif "approve" in prd_review_feedback.lower() or "accepted" in prd_review_feedback.lower() or "approved" in prd_status.lower():
        logger.info("PRD approved, proceeding to coding planning.")
        updated_state = state.copy()
        updated_state.update({
            "messages": state.get("messages", []) + [
                AIMessage(content="PRD approved. Proceeding to create a detailed coding plan.", name="coding_coordinator")
            ],
            "prd_status": "approved"
        })
        return Command(update=updated_state, goto="coding_planner")

    # If we're not sure what to do, ask for review
    else:
        logger.info("PRD status unclear, asking for review.")
        return Command(
            update=state,
            goto="human_prd_review"
        )

def coding_dispatcher_node(state: State) -> Command[Literal["codegen_executor", "task_orchestrator", "__end__"]]: # Changed coder to task_orchestrator
    """Dispatcher node to route coding tasks."""
    logger.info("Coding Dispatcher deciding next step...")
    # TODO: Implement logic to analyze state (user request, coordinator response)
    # and decide the next action (e.g., use Codegen, plan, execute directly).
    # For now, placeholder logic: always try Codegen if description exists.

    last_message = state["messages"][-1].content
    # Extremely basic check - improve this significantly
    if "codegen" in last_message.lower() or state.get("codegen_task_description"):
        logger.info("Routing to Codegen Executor.")
        # Ensure task description is set (might need better logic)
        if not state.get("codegen_task_description"):
             state["codegen_task_description"] = state["messages"][-2].content # Tentative
        return Command(goto="codegen_executor")
    else:
        # Placeholder: maybe route to existing coder or end?
        logger.info("No clear Codegen instruction, routing to end (placeholder).")
        return Command(goto="__end__")

def codegen_executor_node(state: State) -> State:
    """Node to execute tasks using Codegen.com service."""
    logger.info("Codegen Executor node executing...")
    # TODO: Implement CodegenService interaction
    # 1. Instantiate CodegenService (get credentials from config/env)
    # 2. Check current task status (polling?)
    # 3. If no task running, start task using state['codegen_task_description']
    # 4. Update state with task ID, status, object, results etc.
    # 5. Decide if polling is needed or if task is complete/failed.

    task_description = state.get("codegen_task_description")
    task_status = state.get("codegen_task_status")

    logger.warning(f"Codegen Executor is a placeholder. Task: {task_description}, Status: {task_status}")

    # Placeholder: Just update status and return state
    updated_state = state.copy()
    updated_state["codegen_task_status"] = "EXECUTING_PLACEHOLDER"
    updated_state["messages"] = state["messages"] + [AIMessage(content="Codegen task submitted (placeholder).")]

    # This node likely needs to return a Command to decide the next step
    # (e.g., poll again, report results, end). For now, just returns updated state.
    # Returning state directly implies it's a terminal node in this simple setup,
    # which is incorrect for a real implementation.
    return updated_state


# === New Codegen Flow Nodes ===

def initiate_codegen_node(state: State, config: RunnableConfig) -> State: # Added config argument
    """Initiates a task with the Codegen.com service."""
    logger.info("Initiating Codegen.com task...")
    configurable = Configuration.from_runnable_config(config) # Load config

    task_description = state.get("codegen_task_description")
    if not task_description:
        logger.error("Codegen task description not found in state.")
        # Update state to reflect error? Or raise exception?
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_NO_DESCRIPTION"
        updated_state["messages"] = state["messages"] + [AIMessage(content="Error: Codegen task description missing.")]
        return updated_state # Or raise?

    # Get credentials from Configuration object
    org_id = configurable.codegen_org_id
    token = configurable.codegen_token

    if not org_id or not token:
         logger.error("Codegen ORG_ID or TOKEN not found in environment or config.") # Updated log message
         updated_state = state.copy()

    try:
        # Import moved inside function to avoid top-level dependency if not used
        from src.tools.codegen_service import CodegenService
        codegen_service = CodegenService(org_id=org_id, token=token)
        result = codegen_service.start_task(task_description)
        logger.info(f"Codegen start_task result: {result}")
        updated_state = state.copy()
        if result.get("status") == "success":
            updated_state["codegen_task_id"] = result.get("codegen_task_id")
            updated_state["codegen_task_status"] = "PENDING"
            updated_state["codegen_poll_attempts"] = 0
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Codegen task initiated (ID: {result.get("codegen_task_id")}).')]
        else:
            updated_state["codegen_task_status"] = "FAILURE_START_FAILED"
            updated_state["codegen_task_result"] = result.get("message", "Unknown error during task start.")
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Error starting Codegen task: {result.get("message")}.')]
        return updated_state
    except ImportError:
        logger.error("CodegenService could not be imported. Is 'codegen' installed?")
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_IMPORT_ERROR"
        return updated_state
    except Exception as e:
        logger.error(f"Error initiating Codegen task: {e}", exc_info=True)
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_EXCEPTION"
        updated_state["codegen_task_result"] = str(e)
        updated_state["messages"] = state["messages"] + [AIMessage(content=f'Exception during Codegen initiation: {e}')]
        return updated_state


def poll_codegen_status_node(state: State, config: RunnableConfig) -> State: # Added config argument
    """Polls the status of the ongoing Codegen.com task."""
    logger.info("Polling Codegen.com task status...")
    configurable = Configuration.from_runnable_config(config) # Load config

    task_id = state.get("codegen_task_id")
    if not task_id: # or not sdk_object:
        logger.error("Codegen task ID or object not found in state for polling.")
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_POLL_NO_ID"
        updated_state["messages"] = state["messages"] + [AIMessage(content="Error: Cannot poll Codegen status without Task ID.")]
        return updated_state

    # Get credentials from Configuration object
    org_id = configurable.codegen_org_id
    token = configurable.codegen_token

    if not org_id or not token:
         logger.error("Codegen ORG_ID or TOKEN not found in environment or config for polling.") # Updated log message
         updated_state = state.copy()

    try:
        from src.tools.codegen_service import CodegenService
        codegen_service = CodegenService(org_id=org_id, token=token)
        # Pass task_id or sdk_object as required by your poll_task implementation
        # Assuming poll_task needs the task_id
        poll_result = codegen_service.poll_task(task_id=task_id)
        logger.info(f"Codegen poll_task result: {poll_result}")
        updated_state = state.copy()
        new_status = poll_result.get("status", "UNKNOWN_STATUS")
        updated_state["codegen_task_status"] = new_status
        updated_state["codegen_poll_attempts"] = state.get("codegen_poll_attempts", 0) + 1

        if new_status == "SUCCESS":
            updated_state["codegen_task_result"] = poll_result.get("result")
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Codegen task succeeded. Result: {poll_result.get("result")}.')]
        elif new_status == "FAILURE":
            updated_state["codegen_task_result"] = poll_result.get("message", "Unknown failure reason.")
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Codegen task failed: {poll_result.get("message")}.')]
        elif new_status in ["PENDING", "RUNNING"]:
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Codegen task status: {new_status}. Polling again.')]
            pass
        else:
            logger.warning(f"Unexpected Codegen task status received: {new_status}")
            updated_state["codegen_task_result"] = f"Unexpected status: {new_status}"
            updated_state["messages"] = state["messages"] + [AIMessage(content=f'Codegen task has unexpected status: {new_status}.')]
        return updated_state

    except ImportError:
        logger.error("CodegenService could not be imported. Is 'codegen' installed?")
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_IMPORT_ERROR"
        return updated_state
    except Exception as e:
        logger.error(f"Error polling Codegen task status: {e}", exc_info=True)
        updated_state = state.copy()
        updated_state["codegen_task_status"] = "FAILURE_POLL_EXCEPTION"
        updated_state["codegen_task_result"] = str(e)
        updated_state["messages"] = state["messages"] + [AIMessage(content=f'Exception during Codegen polling: {e}')]
        return updated_state


# Placeholder node functions (to be implemented)
def task_orchestrator_node(state: State) -> State:
    logger.info("Task Orchestrator node executing...")

    tasks_live = state.get("tasks_live", [])
    if not isinstance(tasks_live, list):
        logger.error(f"tasks_live is not a list or not found in state: {tasks_live}")
        tasks_live = [] # Default to empty list to prevent further errors

    # --- Process outcome of the previously dispatched task ---
    processed_id = state.get("processed_task_id")
    processed_outcome = state.get("processed_task_outcome")
    processed_failure_details = state.get("processed_task_failure_details")

    if processed_id:
        task_updated = False
        for task in tasks_live: # Iterate by index to safely modify/replace items if needed for retry counts
            if task.get("id") == processed_id:
                if processed_outcome == "SUCCESS":
                    task["status_live"] = "CompletedSuccess"
                    logger.info(f"Task '{processed_id}' marked as CompletedSuccess.")
                elif processed_outcome == "FAILURE":
                    max_retries = task.get("max_retries", 1) # Default to 1 retry if not specified
                    current_retry_count = task.get("current_retry_count", 0)

                    logger.error(f"Task '{processed_id}' failed. Attempt {current_retry_count + 1} of {max_retries + 1}. Details: {processed_failure_details}")

                    if current_retry_count < max_retries:
                        task["current_retry_count"] = current_retry_count + 1
                        task["status_live"] = "Todo" # Mark for retry by setting back to Todo
                        logger.info(f"Task '{processed_id}' scheduled for retry ({task['current_retry_count']}/{max_retries} retries used). Status set to Todo.")
                        # No need to set orchestrator_next_step here, normal loop will pick it up if ready
                    else:
                        task["status_live"] = "CompletedCriticalFailure" # New status for permanent failure after retries
                        logger.error(f"Task '{processed_id}' has reached max retries ({max_retries}) and failed critically.")
                        # This task will now be handled by the logic that checks for overall completion or deadlocks
                        # If a critical failure occurs, we might want to immediately try to forward to planner
                        # This part of the logic will be handled below in the "Set next step based on findings" block
                else:
                    logger.warning(f"Task '{processed_id}' had an unknown outcome: {processed_outcome}. Status not changed.")
                task_updated = True
                break
        if not task_updated:
            logger.warning(f"Processed task ID '{processed_id}' not found in tasks_live.")

    # --- Find the next task to dispatch ---
    next_task_to_dispatch = None

    # First, check if an "execute_alone" task is currently InProgress.
    # If so, no other task can be dispatched.
    active_execute_alone_task_in_progress = False
    for t in tasks_live:
        if t.get("status_live") == "InProgress" and t.get("execute_alone") is True:
            logger.info(f"Task {t.get('id')} is an 'execute_alone' task and is InProgress. No other tasks will be dispatched.")
            active_execute_alone_task_in_progress = True
            break

    if not active_execute_alone_task_in_progress:
        for task in tasks_live:
            if task.get("status_live") == "Todo":
                # Check dependencies
                dependencies = task.get("dependencies", [])
                dependencies_met = True
                if dependencies:
                    for dep_id in dependencies:
                        dep_task_found = False
                        for t_dep in tasks_live:
                            if t_dep.get("id") == dep_id:
                                dep_task_found = True
                                if t_dep.get("status_live") != "CompletedSuccess":
                                    dependencies_met = False
                                    logger.debug(f"Task {task.get('id')} dependency {dep_id} not met (status: {t_dep.get('status_live')}).")
                                    break
                                break
                        if not dep_task_found:
                            logger.warning(f"Task {task.get('id')} has an unknown dependency ID: {dep_id}. Assuming dependency not met.")
                            dependencies_met = False
                            break
                        if not dependencies_met:
                            break

                if dependencies_met:
                    task_is_execute_alone = task.get("execute_alone", False)
                    can_dispatch_this_task = True

                    if task_is_execute_alone:
                        # If this task is execute_alone, check if any *other* task is InProgress
                        for other_task in tasks_live:
                            if other_task.get("status_live") == "InProgress" and other_task.get("id") != task.get("id"):
                                logger.info(f"Cannot dispatch 'execute_alone' task {task.get('id')} because other task {other_task.get('id')} is InProgress.")
                                can_dispatch_this_task = False
                                break

                    if can_dispatch_this_task:
                        logger.info(f"Task {task.get('id')} is ready. Selecting for dispatch.")
                        next_task_to_dispatch = task
                        break # Found a ready task
                    else:
                        logger.info(f"Task {task.get('id')} is 'Todo' and dependencies met, but cannot be dispatched due to 'execute_alone' constraints.")
                else:
                    logger.info(f"Task {task.get('id')} is 'Todo' but dependencies are not met yet.")
            # If next_task_to_dispatch is found, no need to check further tasks in this iteration
            if next_task_to_dispatch:
                break

    # --- Set next step based on findings ---
    updated_state_dict = state.copy()
    if next_task_to_dispatch:
        logger.info(f"Dispatching next task: {next_task_to_dispatch.get('id')}")
        next_task_to_dispatch["status_live"] = "InProgress" # Mark as InProgress
        updated_state_dict["current_task_id"] = next_task_to_dispatch.get("id")
        # Pass necessary details for codegen. For now, pass the whole task dict.
        # codegen_task_description could be task_def.get('description')
        # github_branch_name could be task_def.get('branch_name')
        updated_state_dict["current_task_details"] = next_task_to_dispatch
        updated_state_dict["codegen_task_description"] = next_task_to_dispatch.get("description") # For initiate_codegen_node
        updated_state_dict["orchestrator_next_step"] = "dispatch_task_for_codegen"
    else:
        # No more tasks marked "Todo" that are ready.
        # Check for overall completion or critical failures needing re-planning.
        all_successfully_completed = True
        critically_failed_task_to_replan = None

        if not tasks_live:
            logger.info("No tasks found in tasks_live. Considering project complete.")
        else:
            for task in tasks_live:
                task_status = task.get("status_live")
                if task_status == "CompletedCriticalFailure":
                    logger.warning(f"Task '{task.get('id')}' is in CompletedCriticalFailure state.")
                    critically_failed_task_to_replan = task # Prioritize re-planning critical failures
                    all_successfully_completed = False # A critical failure means not all successful
                    break # Found a critical failure, stop checking others for now
                elif task_status != "CompletedSuccess":
                    all_successfully_completed = False
                    # If any task is still Todo, InProgress, or non-critically failed, we are not done
                    # and not necessarily in a re-plan state unless all those are blocked by a critical failure.
                    # This break is removed so we check all tasks for a potential critical failure first.

        if critically_failed_task_to_replan:
            logger.error(f"Task '{critically_failed_task_to_replan.get('id')}' failed critically after retries. Forwarding to planner.")
            updated_state_dict["failed_task_details"] = critically_failed_task_to_replan # Send this task's details for re-planning
            # Add more context from processed_failure_details if available and relevant to this critically_failed_task
            # This assumes processed_failure_details corresponds to the *last* failure attempt of this task.
            # We might need to store last failure details directly within the task object in tasks_live.
            if critically_failed_task_to_replan.get("id") == processed_id and processed_outcome == "FAILURE":
                 updated_state_dict["failed_task_details"]["last_known_failure_details"] = processed_failure_details

            updated_state_dict["orchestrator_next_step"] = "forward_failure_to_planner"
        elif all_successfully_completed:
            logger.info("All tasks successfully completed.")
            updated_state_dict["orchestrator_next_step"] = "all_tasks_complete"
        else:
            # No new task to dispatch, not all complete, and no critical failure identified for immediate re-plan.
            # This could mean tasks are still InProgress, or Todo but blocked (deadlock).
            logger.warning("No new task to dispatch, not all tasks successfully completed, and no immediate critical failure for re-planning. Possible deadlock or tasks still running.")
            # TODO: Implement deadlock detection. If deadlock, set orchestrator_next_step = "forward_failure_to_planner" with deadlock info.
            # For now, if tasks are still InProgress elsewhere (e.g. execute_alone), this state is fine.
            # If truly stuck (all Todo but none ready, and nothing InProgress), then it's an issue.
            is_any_task_in_progress = any(t.get("status_live") == "InProgress" for t in tasks_live)
            if not is_any_task_in_progress:
                logger.error("DEADLOCK DETECTED (heuristic): No tasks InProgress, but not all are CompletedSuccess and no new tasks can be dispatched.")
                # For now, just end. A more robust solution would be to send to planner.
                # updated_state_dict["orchestrator_next_step"] = "forward_failure_to_planner"
                # updated_state_dict["failed_task_details"] = {"reason": "Deadlock detected in task orchestration"}
                updated_state_dict["orchestrator_next_step"] = "__end__" # Fallback
            else:
                logger.info("Tasks are still InProgress or waiting for dependencies. Orchestrator will loop.")
                # If an execute_alone task is running, orchestrator_next_step will be re-evaluated in next cycle.
                # If other tasks are InProgress, this path means we didn't find a new one to dispatch *additionally*.
                # The graph will loop back to task_orchestrator implicitly if no explicit goto is set by a Command from a node.
                # However, our orchestrator always sets orchestrator_next_step. So if it's not dispatch, not complete, not replan -> default to end for now.
                # This case might need to point back to itself if it's waiting for an InProgress task that is NOT execute_alone
                # For now, the existing __end__ fallback is okay. The key is the external graph loops back.
                updated_state_dict["orchestrator_next_step"] = "__end__" # Fallback for now

    # Clear processed task feedback from state
    updated_state_dict["processed_task_id"] = None
    updated_state_dict["processed_task_outcome"] = None
    updated_state_dict["processed_task_failure_details"] = None

    # Persist changes to tasks_live in the state dictionary that will be returned
    updated_state_dict["tasks_live"] = tasks_live

    return updated_state_dict

def codegen_success_node(state: State) -> State:
    logger.info(f"Codegen task SUCCEEDED. Final Result: {state.get('codegen_task_result')}")
    updated_state = state.copy()
    success_message = f"Codegen task completed successfully. Result: {state.get('codegen_task_result')}"
    updated_state["messages"] = updated_state["messages"] + [AIMessage(content=success_message)]

    # Feedback for Orchestrator
    current_task_id = state.get("current_task_id")
    if current_task_id:
        updated_state["processed_task_id"] = current_task_id
        updated_state["processed_task_outcome"] = "SUCCESS" # Codegen itself was a success
        updated_state["processed_task_failure_details"] = None # Clear any previous failure details for this task stage
    else:
        logger.warning("codegen_success_node: current_task_id not found in state. Cannot set orchestrator feedback.")
    return updated_state

def codegen_failure_node(state: State) -> State:
    logger.error(f"Codegen task FAILED. Status: {state.get('codegen_task_status')}, Reason: {state.get('codegen_task_result')}")
    updated_state = state.copy()
    failure_message = f"Codegen task failed. Status: {state.get('codegen_task_status')}. Reason: {state.get('codegen_task_result')}"
    updated_state["messages"] = updated_state["messages"] + [AIMessage(content=failure_message)]

    # Feedback for Orchestrator
    current_task_id = state.get("current_task_id")
    if current_task_id:
        updated_state["processed_task_id"] = current_task_id
        updated_state["processed_task_outcome"] = "FAILURE"
        updated_state["processed_task_failure_details"] = {
            "reason": "Codegen process failed",
            "codegen_status": state.get("codegen_task_status"),
            "codegen_result": state.get("codegen_task_result")
        }
    else:
        logger.warning("codegen_failure_node: current_task_id not found in state. Cannot set orchestrator feedback.")
    return updated_state

# Placeholder for a more sophisticated repo check
def check_repo_status(repo_path: str | None = None) -> tuple[bool, str]: # Allow None, default to None
    """Checks if the repo is empty and provides a summary."""
    if repo_path is None:
        logger.info("check_repo_status: repo_path is None, treating as a new project.")
        return True, "New project (no existing repository path specified)."

    # Try to list files. If only .git or very few files, consider it empty for this purpose.
    # A real implementation would be more robust.
    try:
        # Run 'git ls-files' to see tracked files. If it fails, repo might not exist or be initialized.
        # Redirect stderr to stdout to capture potential errors from git itself.
        process = os.popen(f'cd "{repo_path}" && git ls-files && git status --porcelain')
        output = process.read()
        exit_code = process.close()

        if exit_code is not None and exit_code != 0:
            logger.warning(f"'git ls-files' or 'git status' failed in {repo_path}. Assuming new/uninitialized repo.")
            return True, "Repository is likely new or not a git repository."

        if not output.strip():
            # No tracked files, likely empty or just initialized
            return True, "Repository is empty or contains no tracked files."
        else:
            # Count files; this is a rough heuristic
            # For a more robust check, one might analyze file types, project structure files etc.
            file_count = len(output.strip().split('\n'))
            if file_count < 5: # Arbitrary threshold for "nearly empty"
                 return True, f"Repository contains very few files ({file_count}). Treating as new project for planning."
            return False, f"Repository contains existing files ({file_count} found)."

    except Exception as e:
        logger.error(f"Error checking repo status: {e}")
        return True, f"Could not determine repository status due to error: {e}"

# === New Initial Context Node ===
def initial_context_node(state: State, config: RunnableConfig) -> Command[Literal["coding_coordinator"]]:
    """Gathers initial context about the repository and Linear tasks before planning."""
    logger.info("Gathering initial context (repo status, Linear tasks)...")
    configurable = Configuration.from_runnable_config(config)
    workspace_path = configurable.workspace_path # Assuming workspace_path is in config

    repo_is_empty, repo_summary = check_repo_status(workspace_path)
    logger.info(f"Repo status: empty={repo_is_empty}, summary='{repo_summary}'")

    # Simulated Linear task check
    if repo_is_empty:
        linear_task_exists_simulated = False # For a new (empty) repo, assume no existing Linear tasks
        logger.info("Simulated Linear task check: Repo is empty, assuming no existing Linear tasks.")
    else:
        # For existing repos, simulate randomly for now
        linear_task_exists_simulated = random.choice([True, False])
        logger.info(f"Simulated Linear task check (existing repo): Randomly determined task_exists={linear_task_exists_simulated}")

    simulated_linear_tasks = []
    if linear_task_exists_simulated: # This block will now only run if repo is not empty AND random choice was True
        simulated_linear_tasks = [
            {"id": "TASK-123", "title": "Implement feature X", "status": "Todo"},
            {"id": "TASK-124", "title": "Fix bug Y", "status": "In Progress"},
        ]
        linear_summary_str = f"Found {len(simulated_linear_tasks)} simulated Linear tasks for existing project."
        logger.info(f"Simulated Linear task details: {linear_summary_str}")
    elif not repo_is_empty and not linear_task_exists_simulated:
        linear_summary_str = "No simulated Linear tasks found for this existing project."
        logger.info(linear_summary_str)
    else: # repo_is_empty is True, so linear_task_exists_simulated is False
        linear_summary_str = "No Linear tasks found (new project)."
        logger.info(linear_summary_str)

    project_summary_dict = {
        "repository_status": {
            "is_empty": repo_is_empty,
            "summary": repo_summary,
        },
        "linear_status": {
            "task_exists": linear_task_exists_simulated,
            "tasks": simulated_linear_tasks,
            "summary": linear_summary_str,
        }
    }

    # Determine if it's an existing project
    is_existing_project = not repo_is_empty or linear_task_exists_simulated

    # initial_context_summary string can be built from the dict for logging or simple display
    initial_context_summary_str = f"Repository: {repo_summary}. Linear: {linear_summary_str}. Existing project: {is_existing_project}"

    return Command(
        update={
            "repo_is_empty": repo_is_empty, # Keep for direct access
            "linear_task_exists": linear_task_exists_simulated, # Keep for direct access
            "existing_project_summary": project_summary_dict, # New detailed dictionary
            "initial_context_summary": initial_context_summary_str, # Updated string summary
            "initial_repo_check_done": True,
             # Add to messages so coordinator LLM sees it directly
            "messages": state["messages"] + [
                AIMessage(content=f"[System Note: Initial context gathered. {initial_context_summary_str}]", name="system_context_gatherer")
            ]
        },
        goto="coding_coordinator",
    )

def human_prd_review_node(state: State) -> Command[Literal["coding_coordinator"]]:
    """Node to wait for user feedback on the PRD."""
    logger.info("Waiting for user feedback on the PRD...")
    logger.debug(f"PRD review node state keys: {list(state.keys())}")
    logger.debug(f"simulated_input={state.get('simulated_input', False)}, wait_for_input={state.get('wait_for_input', True)}")

    # Get the current PRD document to show to the user
    prd_document = state.get("prd_document", "")
    prd_iterations = state.get("prd_iterations", 0)
    original_message = ""

    # Get the original user message
    for msg in state.get("messages", []):
        if hasattr(msg, "type") and msg.type == "human" and not original_message:
            original_message = msg.content
        elif hasattr(msg, "role") and msg.role == "user" and not original_message:
            original_message = msg.content

    # Check if there's a clarification question from the coordinator
    clarification_prompt = state.get("clarification_prompt_from_coordinator", "")

    # Prepare the interrupt message
    if clarification_prompt:
        interrupt_message = (
            f"I need some clarification to better understand your requirements:\n\n"
            f"{clarification_prompt}\n\n"
        )
    else:
        interrupt_message = (
            f"I've prepared a Product Requirements Document (PRD) based on your request:\n\n"
            f"{prd_document}\n\n"
            f"Please review and provide feedback. You can:\n"
            f"- Approve it by saying 'approve' or 'looks good'\n"
            f"- Request changes by describing what needs to be modified\n"
            f"- Ask for more research if needed\n"
        )

    # Add a message to the state so the user sees it
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [
        AIMessage(content=interrupt_message, name="human_prd_review")
    ]

    # Check if we should wait for input
    wait_for_input = state.get("wait_for_input", True)

    if wait_for_input and not state.get("simulated_input", False):
        # Interrupt the graph to wait for feedback
        try:
            prd_feedback = interrupt(interrupt_message)
            logger.info(f"PRD feedback received: {prd_feedback[:100]}...")

            # Add the user's feedback to the message history
            updated_state["messages"] = updated_state["messages"] + [
                HumanMessage(content=prd_feedback, name="user_prd_feedback")
            ]

            # Store the feedback in state
            updated_state["prd_review_feedback"] = prd_feedback
            updated_state["prd_iterations"] = prd_iterations + 1
        except Exception as e:
            logger.error(f"Error during interrupt: {e}")
            # Fall back to simulated mode if interrupt fails
            logger.warning("Falling back to simulated approval due to interrupt failure")
            simulated_feedback = "approve"
            updated_state["messages"] = updated_state["messages"] + [
                HumanMessage(content=simulated_feedback, name="user_prd_feedback")
            ]
            updated_state["prd_review_feedback"] = simulated_feedback
            updated_state["prd_iterations"] = prd_iterations + 1
            updated_state["prd_status"] = "approved"
            updated_state["simulated_input"] = True
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
        updated_state["prd_iterations"] = prd_iterations + 1
        updated_state["prd_status"] = "approved"

        # Add a record of what happened
        updated_state["simulated_input"] = True

        logger.info("PRD auto-approved in non-interactive mode.")

    return Command(
        update=updated_state,
        goto="coding_coordinator"
    )

# === New Linear Integration Node ===
def linear_integration_node(state: State, config: RunnableConfig) -> Command[Literal["task_orchestrator"]]: # Added config
    """Integrates the PRD and task definitions with Linear by creating tasks.
    Populates tasks_live with Linear IDs, URLs, and other task details.
    """
    logger.info("Linear Integration Node: Syncing with Linear...")
    configurable = Configuration.from_runnable_config(config)

    prd_document = state.get("prd_document") # May be useful for context or parent task
    tasks_definition = state.get("tasks_definition")
    tasks_live = []
    integration_messages = []

    if not configurable.linear_api_key or not configurable.linear_team_id:
        logger.warning("Linear API key or Team ID not configured. Skipping actual Linear integration. Falling back to simulation.")
        # Fallback to simulation logic (simplified from original)
        if tasks_definition:
            for i, task_def in enumerate(tasks_definition):
                sim_linear_id = f"SIMLIN-{random.randint(1000, 9999)}"
                task_live_item = {
                    **task_def,
                    "linear_id": sim_linear_id,
                    "linear_url": f"https://linear.app/simulated/{sim_linear_id}",
                }
                tasks_live.append(task_live_item)
            integration_messages.append(f"Simulated Linear integration: {len(tasks_live)} tasks prepared for tasks_live due to missing Linear config.")
        else:
            logger.warning("No tasks_definition found to integrate with Linear (simulation mode).")
            integration_messages.append("No tasks defined for Linear integration (simulation mode).")
    elif tasks_definition:
        try:
            linear_service = LinearService(
                api_key=configurable.linear_api_key,
                team_id=configurable.linear_team_id
            )
            logger.info(f"Attempting to create {len(tasks_definition)} tasks in Linear team {configurable.linear_team_id}.")

            # Optionally, create a parent PRD/Epic task in Linear first if prd_document exists
            # prd_linear_task = None
            # if prd_document: # And maybe a flag like state.get("create_prd_linear_epic", False)
            #     try:
            #         prd_title = f"Project PRD: {state.get('project_name', 'Untitled Project')}"
            #         # Truncate PRD for description or use a summary
            #         prd_description = prd_document[:1500] + ("..." if len(prd_document) > 1500 else "")
            #         prd_linear_task = linear_service.create_task(title=prd_title, description=prd_description, is_epic=True) # Assuming an is_epic param or similar
            #         integration_messages.append(f"Created parent PRD task in Linear: {prd_linear_task.id} ({prd_linear_task.url})")
            #     except Exception as e_epic:
            #         logger.error(f"Failed to create parent PRD task in Linear: {e_epic}")
            #         integration_messages.append(f"Error creating parent PRD task in Linear: {e_epic}")

            for i, task_def in enumerate(tasks_definition):
                try:
                    task_title = task_def.get("name", f"Untitled Task {i+1}")
                    task_description = task_def.get("description", "No description provided.")
                    # TODO: Consider adding acceptance criteria to description or as sub-tasks if Linear supports
                    # TODO: Handle task_def.get("dependencies") - Linear API might allow setting relations post-creation

                    # Create the task in Linear
                    linear_task = linear_service.create_task(
                        title=task_title,
                        description=task_description,
                        # parent_id=prd_linear_task.id if prd_linear_task else None
                        # Other fields like assignee, priority might be set here if available in task_def
                        # and supported by linear_service.create_task
                    )

                    task_live_item = {
                        **task_def, # Copy all fields from tasks_definition
                        "linear_id": linear_task.id,
                        "linear_url": linear_task.url,
                        # status_live is already part of task_def, Linear starts new tasks in a default state
                    }
                    tasks_live.append(task_live_item)
                    integration_messages.append(f"Successfully created Linear task: {linear_task.id} - '{task_title}'.")
                    logger.info(f"Created Linear task {linear_task.id} for task_def '{task_def.get('id')}'.")
                except Exception as e_task:
                    logger.error(f"Failed to create Linear task for task_def '{task_def.get('id', task_title)}': {e_task}")
                    integration_messages.append(f"Error creating Linear task for '{task_def.get('id', task_title)}': {e_task}. Task will be missing Linear ID.")
                    # Add the task_def to tasks_live anyway, but without linear_id/url, or with error markers
                    tasks_live.append({
                        **task_def,
                        "linear_integration_error": str(e_task)
                    })
            logger.info(f"Linear integration complete. {len(tasks_live)} items in tasks_live.")

        except Exception as e_service:
            logger.error(f"Failed to initialize LinearService or during batch operation: {e_service}")
            integration_messages.append(f"Major error during Linear integration: {e_service}. Falling back to tasks_definition without IDs.")
            # Fallback: use tasks_definition as tasks_live but without Linear IDs
            if tasks_definition:
                tasks_live = [ {**td, "linear_integration_error": "Service init failed"} for td in tasks_definition]
            else:
                tasks_live = [] # Ensure it's an empty list if tasks_definition was also empty
    else:
        logger.warning("No tasks_definition found to integrate with Linear.")
        integration_messages.append("No tasks defined for Linear integration.")

    final_ai_message = "Linear Integration Summary:\n" + "\n".join(integration_messages)
    updated_state = {
        "tasks_live": tasks_live,
        "messages": state.get("messages", []) + [AIMessage(content=final_ai_message, name="linear_integration")]
    }
    return Command(update=updated_state, goto="task_orchestrator")

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

# === New Specialized Nodes for Initial Context Review ===

def initial_context_query_generator_node(state: State) -> Command[Literal["initial_context_wait_for_feedback"]]:
    """Node that generates a query to ask the user for feedback on the initial context."""
    logger.info("Generating initial context query...")

    # Create a new state dictionary for updates
    updated_state = {}
    current_messages = state.get("messages", [])
    last_feedback = state.get("last_initial_context_feedback")
    initial_context_summary = state.get("initial_context_summary", "No initial context available.")
    iterations = state.get("initial_context_iterations", 0) + 1
    updated_state["initial_context_iterations"] = iterations

    # Generate the query based on iteration count
    if iterations == 1:  # First time through
        query_to_user = (
            f"I've gathered the following initial context about your project:\\n\\n"
            f"{initial_context_summary}\\n\\n"
            "Please review this information. What would you like to do next? "
            "You can provide additional context, ask me to clarify something, or tell me to 'proceed' if this looks good."
        )
    else:  # Subsequent iterations after non-approving feedback
        query_to_user = (
            f"OK, I've noted your feedback: '{last_feedback}'.\\n\\n"
            f"Current context summary is still:\\n{initial_context_summary}\\n\\n"
            "What would you like to do now? You can provide more details, ask for changes, or tell me to 'proceed' if you're ready."
        )

    # Set the query and awaiting flag
    updated_state["pending_initial_context_query"] = query_to_user
    updated_state["awaiting_initial_context_input"] = True

    # Add the query to messages so user sees it
    if not current_messages or current_messages[-1].content != query_to_user:
        updated_state["messages"] = current_messages + [AIMessage(content=query_to_user, name="initial_context_query")]

    logger.info(f"Iteration {iterations}: Generated query for initial context: {query_to_user[:100]}...")
    return Command(update=updated_state, goto="initial_context_wait_for_feedback")

def initial_context_wait_for_feedback_node(state: State) -> Command[Literal["initial_context_feedback_handler"]]:
    """Node that waits for user feedback on the initial context."""
    logger.info("Waiting for user feedback on initial context...")

    # Set the awaiting_initial_context_input flag to ensure the interrupt happens
    updated_state = {}
    updated_state["awaiting_initial_context_input"] = True

    # In LangGraph 0.3.5, we need to handle interrupts differently
    # Print the query to the user and get their feedback directly
    pending_query = state.get("pending_initial_context_query")
    if pending_query:
        print(f"\n=== INITIAL CONTEXT REVIEW ===")
        print(pending_query.replace("\\n", "\n"))  # Replace escaped newlines

        try:
            user_input = input("\nYour feedback: ")

            # Store the feedback in the state for the feedback handler
            updated_state["interrupt_value"] = user_input
            updated_state["last_initial_context_feedback"] = user_input

            logger.info(f"Received user feedback: {user_input[:100]}...")
        except Exception as e:
            logger.error(f"Error getting user input: {e}")
            # Provide a default response to avoid blocking
            updated_state["interrupt_value"] = "proceed"
            updated_state["last_initial_context_feedback"] = "proceed"

    # After getting feedback, control passes to the feedback handler
    return Command(update=updated_state, goto="initial_context_feedback_handler")

def initial_context_feedback_handler_node(state: State) -> Command[Literal["initial_context_approval_router"]]:
    """Node that processes user feedback on the initial context."""
    logger.info("Processing user feedback on initial context...")

    # Create a new state dictionary for updates
    updated_state = {}
    current_messages = state.get("messages", [])

    # Get the feedback from the interrupt value
    # This is set by the on_interrupt handler in run_coding_workflow.py
    interrupt_value = state.get("interrupt_value")

    if interrupt_value:
        logger.info(f"Processing feedback from interrupt: {interrupt_value[:100]}...")
        # Store the feedback in the state for the approval router
        updated_state["last_initial_context_feedback"] = interrupt_value

        # Add the feedback to messages if not already there
        if not current_messages or not isinstance(current_messages[-1], HumanMessage) or current_messages[-1].content != interrupt_value:
            updated_state["messages"] = current_messages + [HumanMessage(content=interrupt_value, name="user_initial_context_feedback")]
    else:
        # If no interrupt value, check for last_initial_context_feedback
        last_feedback = state.get("last_initial_context_feedback")
        if last_feedback:
            logger.info(f"Processing feedback from state: {last_feedback[:100]}...")
            # Add the feedback to messages if not already there
            if not current_messages or not isinstance(current_messages[-1], HumanMessage) or current_messages[-1].content != last_feedback:
                updated_state["messages"] = current_messages + [HumanMessage(content=last_feedback, name="user_initial_context_feedback")]

    # Reset the awaiting flag
    updated_state["awaiting_initial_context_input"] = False

    return Command(update=updated_state, goto="initial_context_approval_router")

def initial_context_approval_router_node(state: State) -> Command[Literal["coding_coordinator", "initial_context_query_generator"]]:
    """Node that determines whether to proceed or continue gathering context."""
    logger.info("Routing based on initial context approval...")

    # Create a new state dictionary for updates
    updated_state = {}
    current_messages = state.get("messages", [])
    last_feedback = state.get("last_initial_context_feedback")

    # Check if we already have approval
    if state.get("initial_context_approved"):
        logger.info("Initial context already approved, proceeding to coordinator.")
        return Command(goto="coding_coordinator")

    # Check for approval in the last feedback
    if last_feedback:
        approval_keywords = ["proceed", "continue", "approved", "ok", "yes", "looks good", "move on", "correct"]
        if any(keyword in last_feedback.lower() for keyword in approval_keywords):
            logger.info("Initial context approved by user.")
            updated_state["initial_context_approved"] = True
            updated_state["awaiting_initial_context_input"] = False

            # Add a confirmation message
            updated_state["messages"] = current_messages + [AIMessage(content="Great! Moving on to the PRD phase.", name="initial_context_approval")]
            return Command(update=updated_state, goto="coding_coordinator")

    # If not approved, go back to query generator
    logger.info("Initial context not yet approved, generating new query.")
    return Command(update=updated_state, goto="initial_context_query_generator")

# Keep the original function as a fallback but rename it
def human_initial_context_review_node(state: State) -> Command[Literal["coding_coordinator", "initial_context_query_generator"]]:
    """Legacy node to manage iterative user feedback on initial context information."""
    logger.info("Using legacy human_initial_context_review_node...")

    # This is now just a router to the new specialized nodes
    if state.get("initial_context_approved"):
        return Command(goto="coding_coordinator")
    else:
        return Command(goto="initial_context_query_generator")
