# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
from typing import Annotated, Literal
import os
import random

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import Command, interrupt
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agents.agents import coder_agent, research_agent, create_agent

from src.tools.search import LoggedTavilySearch
from src.tools import (
    crawl_tool,
    web_search_tool,
    python_repl_tool,
)

from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type
from src.prompts.planner_model import Plan, StepType
from src.prompts.template import apply_prompt_template
from src.utils.json_utils import repair_json_output

from .types import State
from ..config import SEARCH_MAX_RESULTS, SELECTED_SEARCH_ENGINE, SearchEngine

logger = logging.getLogger(__name__)


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
    # For now, let's construct messages more directly to highlight new inputs:
    
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

    llm = get_llm_by_type(AGENT_LLM_MAP["coding_planner"])
    response = llm.invoke(messages) # Pass the constructed messages
    full_response = response.content

    logger.debug(f"Coding Planner raw LLM response: {full_response}")

    try:
        # Expecting LLM to output a JSON list of task dictionaries
        # Example Task Dict: {id, description, dependencies: List[id], branch_name, status_in_plan, execute_alone}
        parsed_tasks = json.loads(repair_json_output(full_response))
        if not isinstance(parsed_tasks, list):
            raise ValueError("LLM response for tasks is not a list.")
        
        tasks_definition = []
        for i, task_data in enumerate(parsed_tasks):
            if not isinstance(task_data, dict):
                logger.warning(f"Task item {i} is not a dictionary: {task_data}")
                # Optionally skip or add a default error task
                continue
            
            # Basic validation/defaulting (can be more robust with Pydantic model for TaskDefinitionItem)
            task_id = task_data.get("id", f"task_{i+1}")
            description = task_data.get("description", "No description provided.")
            dependencies = task_data.get("dependencies", [])
            branch_name = task_data.get("branch_name", f"task/{task_id}")
            status_in_plan = task_data.get("status_in_plan", "todo")
            execute_alone = task_data.get("execute_alone", False)

            tasks_definition.append({
                "id": task_id,
                "description": description,
                "dependencies": dependencies,
                "branch_name": branch_name,
                "status_in_plan": status_in_plan,
                "execute_alone": execute_alone,
                # Add other fields from your Task Dict spec if needed
            })
        
        if not tasks_definition:
             logger.warning("LLM parsed response resulted in an empty task list.")
             # Handle empty task list - maybe raise error or default to __end__?

        logger.info(f"Successfully parsed {len(tasks_definition)} tasks.")

        updated_state = {
            "messages": state["messages"] + [AIMessage(content=full_response, name="coding_planner")],
            "tasks_definition": tasks_definition, # New state field
            "current_plan": None, # Deprecate or redefine current_plan if tasks_definition is the source of truth
            "plan_iterations": plan_iterations,
            "failed_task_details": None # Clear after re-planning
        }
        return Command(update=updated_state, goto="human_feedback_plan")

    except Exception as e:
        logger.error(f"Error parsing detailed task plan from LLM: {e}")
        error_message = f"I encountered an error trying to structure the detailed task plan. Error: {e}. LLM response was: {full_response[:500]}..."
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=error_message, name="coding_planner")],
                "plan_iterations": plan_iterations,
                "failed_task_details": None # Clear even on error if it was a re-plan attempt
            },
            goto="__end__"
        )


def human_feedback_plan_node(
    state: State,
) -> Command[Literal["coding_planner", "task_orchestrator"]]:
    """Node to wait for user feedback on the generated coding plan."""
    logger.info("Waiting for user feedback on the coding plan...")

    feedback = interrupt("Please review the generated coding plan. Respond with 'accept' or provide feedback for revision.")

    feedback_str = str(feedback).strip().upper()
    logger.info(f"Received feedback on plan: {feedback_str}")

    if feedback_str.startswith("ACCEPT") or feedback_str.startswith("YES") :
        logger.info("Plan accepted by user. Proceeding to Task Orchestrator...")
        # On accept, always go to task_orchestrator based on current plan
        return Command(goto="task_orchestrator")

    elif feedback_str.startswith("REVISE") or feedback_str.startswith("EDIT") or feedback_str.startswith("NO"):
        logger.info("Plan revision requested. Routing back to coding_planner.")
        # Extract the revision request (assuming format like "REVISE: Change step 3...")
        revision_details = str(feedback).strip()
        # Add the user's revision request to the message history for the planner
        return Command(
            update={
                "messages": state["messages"] + [
                    HumanMessage(content=revision_details, name="user_feedback")
                ],
                # plan_iterations already updated in coding_planner_node
            },
            goto="coding_planner",
        )
    else:
        # Handle unclear feedback - perhaps ask again or default to revision?
        logger.warning(f"Unclear feedback received: '{feedback_str}'. Asking for revision.")
        return Command(
            update={
                 "messages": state["messages"] + [
                     HumanMessage(content=f"Unclear feedback: '{str(feedback)}'. Please clarify if you want to accept or revise the plan.", name="user_feedback")
                 ]
            },
            goto="coding_planner", # Go back to planner with the clarification request
        )


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
) -> Command[Literal["researcher", "task_orchestrator", "coding_coordinator"]]:
    """Research team node that collaborates on tasks."""
    logger.info("Research team is collaborating on tasks.")
    current_plan = state.get("current_plan")
    if not current_plan or not current_plan.steps:
        return Command(goto="coding_planner")
    if all(step.execution_res for step in current_plan.steps):
        return Command(goto="coding_planner")
    for step in current_plan.steps:
        if not step.execution_res:
            break
    if step.step_type and step.step_type == StepType.RESEARCH:
        return Command(goto="researcher")
    if step.step_type and step.step_type == StepType.PROCESSING:
        return Command(goto="task_orchestrator")
    return Command(goto="coding_planner")


async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team", "__end__"]]:
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

    # Determine the next node based on the workflow context
    if state.get("current_workflow") == "coding":
        next_node = "context_gatherer"  # Continue to context gatherer for coding workflow
        logger.debug("Coding workflow context detected, setting next node to context_gatherer")
    else:
        next_node = "research_team" # Default for research workflow
        logger.debug("Research workflow context detected, setting next node to research_team")

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
        goto=next_node, # Use the determined next node
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

def coding_coordinator_node(
    state: State,
) -> Command[Literal["human_prd_review", "context_gatherer", "coding_planner", "__end__"]]:
    """
    Manages the PRD development lifecycle.
    Initializes or updates the PRD based on project context, user feedback, and research.
    Determines the next step in the PRD process (review, research, or move to planning).
    """
    logger.info("Coding Coordinator: Managing PRD development...")

    # Initialize or retrieve current PRD
    prd_document = state.get("prd_document", "")
    prd_review_feedback = state.get("prd_review_feedback")
    research_results = state.get("research_results")
    existing_project_summary = state.get("existing_project_summary")
    
    # Prepare state for the prompt template
    # The prompt template "coding_coordinator_prd" should be designed to handle these fields.
    prompt_state_input = {
        "messages": state.get("messages", []), # Original messages
        "prd_document": prd_document,
        "prd_review_feedback": prd_review_feedback,
        "research_results": research_results,
        "existing_project_summary": existing_project_summary,
        "initial_context_summary": state.get("initial_context_summary", "") # Fallback or complementary
    }

    # Handle direct approval from human_prd_review_node
    if prd_review_feedback and "approve".lower() in prd_review_feedback.lower():
        logger.info("PRD approved by user via feedback.")
        updated_state = {
            "prd_approved": True,
            "prd_next_step": "coding_planner",
            "prd_review_feedback": None, # Clear feedback
            "research_results": None, # Clear research results
            "messages": state["messages"] + [AIMessage(content="[System Note: PRD has been approved by the user. Proceeding to planning.]", name="coding_coordinator")]
        }
        return Command(update=updated_state, goto="coding_planner")

    # LLM call to update PRD and decide next step
    # Assuming a new prompt template "coding_coordinator_prd"
    # This template should guide the LLM to:
    # 1. Initialize PRD if prd_document is empty, using user request and existing_project_summary.
    # 2. Incorporate prd_review_feedback if present.
    # 3. Incorporate research_results if present.
    # 4. Output the updated prd_document.
    # 5. Output a structured decision for prd_next_step (e.g., "NEXT_STEP: human_prd_review", "NEXT_STEP: context_gatherer", "NEXT_STEP: prd_ready_for_final_review")
    
    # For now, we'll simulate the LLM's structured output for next_step parsing.
    # In a real scenario, this comes from parsing the LLM response.
    
    messages_for_llm = apply_prompt_template("coding_coordinator_prd", prompt_state_input)
    
    logger.debug(f"Messages for PRD coordinator LLM: {messages_for_llm}")
    response = get_llm_by_type(AGENT_LLM_MAP["coordinator"]).invoke(messages_for_llm)
    response_content = response.content
    logger.info(f"Coding Coordinator (PRD) LLM raw response: {response_content}")

    # --- Parse LLM Response ---
    # This part needs robust parsing for the PRD document and the next_step directive.
    # Example: LLM might output JSON, or use specific keywords.
    # Let's assume LLM outputs:
    # { "updated_prd": "...", "next_action": "human_prd_review" }
    # Or it might be plain text with markers, e.g.:
    # PRD_DOCUMENT_START
    # ... new prd ...
    # PRD_DOCUMENT_END
    # NEXT_ACTION: human_prd_review
    
    # Simulated parsing:
    parsed_prd_document = response_content # Simplistic: assume LLM just returns the new PRD
    parsed_next_step = "human_prd_review" # Default if not parsed
    
    if "NEXT_ACTION: human_prd_review".lower() in response_content.lower():
        parsed_next_step = "human_prd_review"
    elif "NEXT_ACTION: context_gatherer".lower() in response_content.lower():
        parsed_next_step = "context_gatherer"
    elif "NEXT_ACTION: prd_complete".lower() in response_content.lower(): # LLM thinks PRD is good
        # This doesn't mean auto-approved. It still goes to human_prd_review,
        # but the prompt to human might be "LLM considers this PRD complete. Please review for approval."
        parsed_next_step = "human_prd_review" 
        logger.info("LLM suggests PRD is complete, routing for final human review/approval.")
    else:
        # Fallback if no clear directive, assume it needs more review
        logger.warning(f"No clear NEXT_ACTION in LLM response for PRD. Defaulting to human_prd_review. Response: {response_content[:200]}")
        parsed_next_step = "human_prd_review"

    # Update state
    updated_state_fields = {
        "prd_document": parsed_prd_document,
        "prd_next_step": parsed_next_step,
        "prd_approved": False, # Approval only happens after human_prd_review node signals it
        "prd_review_feedback": None, # Clear feedback after processing
        "research_results": None, # Clear research results after processing
        "messages": state["messages"] + [response] # Add LLM response
    }
    
    logger.info(f"Coding Coordinator updated PRD. Next step for PRD: {parsed_next_step}")

    return Command(update=updated_state_fields, goto=parsed_next_step)

def coding_dispatcher_node(
    state: State,
) -> Command[Literal["codegen_executor", "task_orchestrator", "__end__"]]: # Changed coder to task_orchestrator
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
        for task in tasks_live:
            if task.get("id") == processed_id:
                if processed_outcome == "SUCCESS":
                    task["status_live"] = "CompletedSuccess"
                    logger.info(f"Task '{processed_id}' marked as CompletedSuccess.")
                elif processed_outcome == "FAILURE":
                    task["status_live"] = "CompletedFailure"
                    # TODO: Handle retries or forward_failure_to_planner based on processed_failure_details
                    logger.error(f"Task '{processed_id}' marked as CompletedFailure. Details: {processed_failure_details}")
                else:
                    logger.warning(f"Task '{processed_id}' had an unknown outcome: {processed_outcome}. Status not changed.")
                task_updated = True
                break
        if not task_updated:
            logger.warning(f"Processed task ID '{processed_id}' not found in tasks_live.")

    # --- Find the next task to dispatch (simple version: first "Todo" task, no dependency check yet) ---
    next_task_to_dispatch = None
    for task in tasks_live:
        if task.get("status_live") == "Todo":
            # TODO: Implement dependency checking: check task.get("dependencies", [])
            # TODO: Implement "execute_alone" logic
            next_task_to_dispatch = task
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
        # No more tasks marked "Todo". Check if all are "CompletedSuccess".
        all_successfully_completed = True
        if not tasks_live: # No tasks to begin with
            logger.info("No tasks found in tasks_live. Considering project complete.")
            all_successfully_completed = True 
        else:
            for task in tasks_live:
                if task.get("status_live") != "CompletedSuccess":
                    all_successfully_completed = False
                    # TODO: If there are tasks in other states (e.g., CompletedFailure not yet handled for re-plan), 
                    # this logic might need to be more nuanced. For now, any non-success means not all done.
                    if task.get("status_live") == "CompletedFailure":
                        logger.warning(f"Found task '{task.get('id')}' with status CompletedFailure. Project not fully complete or needs re-planning.")
                        # Placeholder: For now, if there's a failure, we don't consider it all_tasks_complete.
                        # Later, this could trigger "forward_failure_to_planner"
                        # updated_state_dict["orchestrator_next_step"] = "forward_failure_to_planner"
                        # updated_state_dict["failed_task_details"] = task # Send this task for re-planning
                        # For this simplified version, let's assume it blocks completion
                        break # Exit loop, all_successfully_completed is False
            
        if all_successfully_completed:
            logger.info("All tasks successfully completed.")
            updated_state_dict["orchestrator_next_step"] = "all_tasks_complete"
        else:
            # If not dispatching and not all complete, what to do? Could be failures or deadlocks.
            logger.warning("No new task to dispatch, but not all tasks are successfully completed. Possible failures or deadlock.")
            # For now, default to __end__ if stuck. Proper handling needs failure/deadlock logic.
            # This could also be where "forward_failure_to_planner" is set if unhandled failures exist.
            updated_state_dict["orchestrator_next_step"] = "__end__" # Placeholder, might need re-planning route

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
    return updated_state

def codegen_failure_node(state: State) -> State:
    logger.error(f"Codegen task FAILED. Status: {state.get('codegen_task_status')}, Reason: {state.get('codegen_task_result')}")
    updated_state = state.copy()
    failure_message = f"Codegen task failed. Status: {state.get('codegen_task_status')}. Reason: {state.get('codegen_task_result')}"
    updated_state["messages"] = updated_state["messages"] + [AIMessage(content=failure_message)]
    return updated_state

# Placeholder for a more sophisticated repo check
def check_repo_status(repo_path: str = ".") -> tuple[bool, str]:
    """Checks if the repo is empty and provides a summary."""
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
    # For simulation, let's randomly decide if a Linear task exists
    linear_task_exists_simulated = random.choice([True, False])
    simulated_linear_tasks = []
    if linear_task_exists_simulated and not repo_is_empty: # Let's say Linear tasks usually exist for non-empty repos
        simulated_linear_tasks = [
            {"id": "TASK-123", "title": "Implement feature X", "status": "Todo"},
            {"id": "TASK-124", "title": "Fix bug Y", "status": "In Progress"},
        ]
        linear_summary_str = f"Found {len(simulated_linear_tasks)} simulated Linear tasks."
        logger.info(f"Simulated Linear task check: {linear_summary_str}")
    elif linear_task_exists_simulated:
        simulated_linear_tasks = [{"id": "TASK-001", "title": "Initial project setup", "status": "Done"}]
        linear_summary_str = "Found 1 simulated initial Linear task."
        logger.info(f"Simulated Linear task check: {linear_summary_str}")
    else:
        linear_summary_str = "No simulated Linear tasks found."
        logger.info("Simulated Linear task check: No existing Linear task.")

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

# Placeholder for human_prd_review_node
def human_prd_review_node(state: State) -> State: # Should return State, feedback goes into state
    """Node to wait for user feedback on the PRD."""
    logger.info("Waiting for user feedback on the PRD...")
    
    # Interrupt the graph to wait for PRD feedback
    # The actual feedback will be injected into the state by the calling environment
    # when the interrupt is resolved.
    prd_feedback = interrupt("Please review the PRD. Provide feedback, or type 'approve' or 'research needed'.")
    
    # The calling environment should place this feedback into state["prd_review_feedback"]
    # For now, this node itself doesn't need to return the feedback directly in the Command,
    # as coding_coordinator will pick it up from the state.
    # However, the state object within this node's execution might be updated by the interrupt mechanism.

    # Simulate that the interrupt mechanism updated the state if needed for direct testing here,
    # but in live use, the external resume call updates the shared state object.
    # state["prd_review_feedback"] = prd_feedback # Example if feedback was directly returned

    logger.info(f"PRD feedback interrupt completed. Feedback should be in state for coordinator. Raw feedback if available here: {prd_feedback}")
    # This node primarily serves as an interrupt point. 
    # The 'coding_coordinator' will read the feedback from the state when the graph resumes.
    # It doesn't direct the graph via Command, it just updates its part of the state (or rather, allows interruption for it to be updated).
    return state # Return the current state, expecting prd_review_feedback to be set by the interrupt resolution

# === New Linear Integration Node ===
def linear_integration_node(state: State) -> Command[Literal["task_orchestrator"]]:
    """Simulates integrating the PRD and task definitions with Linear.
    Populates tasks_live with simulated Linear IDs and statuses.
    """
    logger.info("Linear Integration Node: Simulating Linear sync...")

    prd_document = state.get("prd_document")
    tasks_definition = state.get("tasks_definition")

    if not prd_document or not tasks_definition:
        logger.error("PRD document or tasks_definition missing. Cannot sync with Linear.")
        return Command(
            update={"messages": state["messages"] + [AIMessage(content="[System Error: PRD or Task Definition missing for Linear sync.]", name="linear_integration")]},
            goto="task_orchestrator" # Or an error handling node
        )

    logger.info(f"Simulating creation/update of PRD in Linear: {prd_document[:100]}...")

    tasks_live = []
    for i, task_def in enumerate(tasks_definition):
        simulated_linear_id = f"LIN-{random.randint(1000, 9999)}-{i+1}"
        live_task = task_def.copy()
        live_task["linear_id"] = simulated_linear_id
        live_task["status_live"] = "Todo"
        live_task["linear_url"] = f"https://simulated.linear.app/task/{simulated_linear_id}"
        tasks_live.append(live_task)
        logger.info(f"Simulated creation of task '{task_def.get('description','N/A')[:50]}...' in Linear with ID {simulated_linear_id}")

    logger.info(f"Successfully simulated Linear sync. {len(tasks_live)} tasks processed.")

    return Command(
        update={
            "tasks_live": tasks_live,
            "messages": state["messages"] + [AIMessage(content=f"[System Note: PRD and {len(tasks_live)} tasks simulated in Linear.]", name="linear_integration")]
        },
        goto="task_orchestrator"
    )
