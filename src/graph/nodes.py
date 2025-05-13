# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
from typing import Annotated, Literal
import os

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
    """Planner node that generates a code implementation plan."""
    logger.info("Coding Planner generating code plan...")
    # Increment plan iterations (for loop prevention)
    plan_iterations = state.get("plan_iterations", 0) + 1
    configurable = Configuration.from_runnable_config(config)

    # Prevent potential infinite loops
    if plan_iterations > configurable.max_plan_iterations:
        logger.warning("Max plan iterations reached. Ending workflow.")
        return Command(
            update={"messages": state["messages"] + [AIMessage(content="Maximum plan refinement iterations reached. Please try refining your request.", name="coding_planner")]},
            goto="__end__"
        )

    # Use the new coding_planner prompt
    messages = apply_prompt_template("coding_planner", state, configurable)

    # Add background investigation results if available
    if state.get("enable_background_investigation") and state.get("background_investigation_results") and plan_iterations == 1: # Only add on first iteration
        messages += [
            {
                "role": "user",
                "content": (
                    "background investigation results of user query:\n"
                    + state["background_investigation_results"]
                    + "\n"
                ),
            }
        ]

    # Use the LLM to generate a plan
    llm = get_llm_by_type(AGENT_LLM_MAP["coding_planner"])
    response = llm.invoke(messages)
    full_response = response.content

    logger.debug(f"Coding Planner state messages: {state['messages']}")
    logger.info(f"Coding Planner response: {full_response}")

    # Try to parse the response as JSON
    try:
        plan_json = json.loads(repair_json_output(full_response))
        github_feature_branch = plan_json.get("feature_branch")
        github_task_branches = {}

        adapted_plan = {
            "locale": plan_json.get("locale", state.get("locale", "en-US")),\
            "has_enough_context": True,\
            "thought": plan_json.get("thought", "Code implementation plan"),
            "title": plan_json.get("title", "Coding Task"),
            "steps": []
        }

        if "steps" in plan_json:
            steps = plan_json["steps"]
            if isinstance(steps, list):
                for i, step in enumerate(steps):
                    if not isinstance(step, dict):
                        logger.warning(f"Step {i+1} is not a dictionary: {step}")
                        continue
                    task_branch = None
                    if "task_branch" in step:
                        task_branch = step.get("task_branch")
                        github_task_branches[i+1] = task_branch
                    step_title = f"Step {i+1}"
                    step_description = ""
                    if "title" in step and isinstance(step["title"], str):
                        step_title = step["title"]
                    if "description" in step and isinstance(step["description"], str):
                        step_description = step["description"]
                    adapted_plan["steps"].append({
                        "need_web_search": False,
                        "title": step_title,
                        "description": step_description,
                        "step_type": StepType.PROCESSING
                    })
            else:
                logger.warning(f"Steps is not a list: {steps}")
                adapted_plan["steps"].append({
                    "need_web_search": False,
                    "title": "Default Step",
                    "description": "No valid steps were found in the plan.",
                    "step_type": StepType.PROCESSING
                })

        validated_plan = Plan.model_validate(adapted_plan)
        logger.info(f"Successfully parsed and validated coding plan: {validated_plan.title}")

        # Update state with the plan and GitHub info, then go to feedback
        updated_state = {
            "messages": state["messages"] + [AIMessage(content=full_response, name="coding_planner")],
            "current_plan": validated_plan,
            "current_workflow": "coding",
            "feature_branch_name": github_feature_branch,
            "github_task_branches": github_task_branches,
            "github_action": "create_feature_branch" if github_feature_branch else None,
            "feature_branch_description": plan_json.get("thought", ""),
            "plan_iterations": plan_iterations # Store iteration count
        }

        # Route to human feedback for the plan
        return Command(update=updated_state, goto="human_feedback_plan")

    except Exception as e:
        logger.error(f"Error parsing coding plan: {e}")
        error_message = f"I encountered an error trying to structure the coding plan. Please check the format or try rephrasing your request. Error: {e}"
        return Command(
            update={
                "messages": state["messages"] + [
                    AIMessage(content=error_message, name="coding_planner"),
                    # Optionally include the raw response for debugging?
                    # AIMessage(content=f"Raw LLM Response:\n```\n{full_response}\n```", name="coding_planner")
                ],
                 "plan_iterations": plan_iterations # Store iteration count even on error
            },
            goto="__end__"
        )


def human_feedback_plan_node(
    state: State,
) -> Command[Literal["coding_planner", "github_planning", "coder"]]:
    """Node to wait for user feedback on the generated coding plan."""
    logger.info("Waiting for user feedback on the coding plan...")

    # Interrupt the graph to wait for feedback
    # The feedback string is expected to be injected into the state by the caller
    # (e.g., via the interruptFeedback field in sendMessage)
    feedback = interrupt("Please review the generated coding plan. Respond with 'accept' or provide feedback for revision.")

    # The interrupt() call pauses execution. When resumed, 
    # the user's feedback should be the last message or in a specific state field.
    # For now, let's assume the feedback comes via the interrupt mechanism directly.
    # Note: Actual feedback injection needs to be handled by the environment running the graph.

    feedback_str = str(feedback).strip().upper()
    logger.info(f"Received feedback on plan: {feedback_str}")

    if feedback_str.startswith("ACCEPT") or feedback_str.startswith("YES") :
        logger.info("Plan accepted by user. Proceeding...")
        # Check if a feature branch was planned
        feature_branch_name = state.get("feature_branch_name")
        next_node = "github_planning" if feature_branch_name else "coder"
        # No state update needed here, just route
        return Command(goto=next_node)

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
) -> Command[Literal["researcher", "coder", "coding_planner"]]:
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
        return Command(goto="coder")
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
) -> Command[Literal["research_team", "__end__"]]:
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
) -> Command[Literal["research_team", "__end__"]]:
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
    logger.info("Coder node is coding.")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "coder",
        coder_agent,
        [python_repl_tool],
    )


# === Coding Flow Nodes ===

def coding_coordinator_node(
    state: State,
) -> Command[Literal["prepare_codegen_task", "coding_planner", "coder", "coding_coordinator", "__end__"]]:
    """Coordinator node for the coding workflow. Determines strategy based on user request and initial context."""
    logger.info("Coding Coordinator talking. Determining strategy...")

    # Ensure initial context has been gathered if this workflow expects it.
    # This is a fallback if graph isn't started at initial_context_node for some reason.
    if not state.get("initial_repo_check_done"):
        logger.warning("Initial repo check not done! Coordinator might lack full context.")
        # Ideally, graph should always start at initial_context_node for this flow.

    # The prompt for "coding_coordinator" should be designed to use
    # state["initial_context_summary"], state["repo_is_empty"], etc.
    messages = apply_prompt_template("coding_coordinator", state) # Assuming template handles new state fields
    response = get_llm_by_type(AGENT_LLM_MAP["coordinator"]).invoke(messages)
    logger.debug(f"Coding Coordinator state messages: {state['messages']}")
    response_content = response.content
    logger.info(f"Coding Coordinator LLM response: {response_content}")

    goto = "__end__"  # Default to ending
    locale = state.get("locale", "en-US")
    strategy = "CLARIFY" # Default strategy if not found

    if response_content and response_content.strip():
        # Parse strategy from response
        if "STRATEGY: CODEGEN" in response_content.upper():
            strategy = "CODEGEN"
            goto = "prepare_codegen_task"
            logger.info("Strategy: CODEGEN. Routing to prepare_codegen_task.")
        elif "STRATEGY: PLAN" in response_content.upper():
            strategy = "PLAN"
            goto = "context_gatherer"  # Route to context gatherer first
            logger.info("Strategy: PLAN. Routing to context_gatherer.")
        elif "STRATEGY: DIRECT" in response_content.upper():
            strategy = "DIRECT"
            goto = "coder"
            logger.info("Strategy: DIRECT. Routing to coder.")
        elif "STRATEGY: CLARIFY" in response_content.upper():
            strategy = "CLARIFY"
            # Loop back to self (coding_coordinator) by not changing goto from default if it means asking user
            # Or, if LLM asks question, it will be added to messages, and next run it re-evaluates.
            # For now, explicit loop back if LLM wants to clarify to ensure it retries with new message.
            goto = "coding_coordinator" # This will re-run the coordinator with the new AI message
            logger.info("Strategy: CLARIFY. LLM will ask clarifying questions. Looping back to coding_coordinator.")
        else:
            # If the response contains a plan or mentions planning, route to context_gatherer
            if "PLAN" in response_content.upper() or "HERE'S THE PLAN" in response_content.upper():
                strategy = "PLAN"
                goto = "context_gatherer"  # Route to context gatherer first
                logger.info("Strategy detected from content: PLAN. Routing to context_gatherer.")
            else:
                # If no clear strategy, but there is content, assume clarification or simple response.
                # Let it go to __end__ if no strategy, or loop to ask for clarification if content seems like a question.
                logger.warning(f"No explicit STRATEGY found in coordinator response. Content: {response_content[:100]}... Defaulting to context_gatherer.")
                # For now, if no strategy, but content exists, route to context_gatherer
                goto = "context_gatherer"  # Route to context gatherer by default

    else:
        logger.warning(
            "Coding Coordinator response was empty. Terminating workflow execution."
        )
        goto = "__end__"

    return Command(
        update={
            "locale": locale,
            "messages": state["messages"] + [response] # Add LLM response to messages
        },
        goto=goto,
    )

def coding_dispatcher_node(
    state: State,
) -> Command[Literal["codegen_executor", "coder", "__end__"]]: # Add potential destinations
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
def prepare_codegen_task_node(state: State) -> State:
    logger.info("Preparing Codegen task description...")
    updated_state = state.copy()
    # Attempt to get description from various sources if not already set
    if not updated_state.get("codegen_task_description"):
        # Priority: last message content from coordinator, then last user message
        # This logic might need to be more robust based on actual flow
        if updated_state["messages"][-1].type == "ai": # Assuming last is AI (coordinator)
            description_source = updated_state["messages"][-1].content
        elif len(updated_state["messages"]) > 1 and updated_state["messages"][-2].type == "ai":
            description_source = updated_state["messages"][-2].content # if last is human feedback
        else:
            description_source = "No suitable task description found in recent messages."
            logger.warning(description_source)

        # Basic refinement: just use the content. Could be an LLM call here for actual refinement.
        updated_state["codegen_task_description"] = description_source
        logger.info(f"Set codegen_task_description from: {description_source}")
    else:
        logger.info(f"Using existing codegen_task_description: {updated_state.get('codegen_task_description')}")

    # Ensure it's a string
    if not isinstance(updated_state.get("codegen_task_description"), str):
        logger.warning(f"codegen_task_description was not a string, converting. Value: {updated_state.get('codegen_task_description')}")
        updated_state["codegen_task_description"] = str(updated_state.get("codegen_task_description"))

    return updated_state

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

    # Placeholder for Linear task check
    linear_task_exists = False
    linear_summary = "Linear task check not implemented yet."
    logger.info("Linear task check: placeholder, defaulting to no existing task.")

    initial_context_summary = f"Repository check: {repo_summary}. Linear check: {linear_summary}"

    return Command(
        update={
            "repo_is_empty": repo_is_empty,
            "linear_task_exists": linear_task_exists,
            "initial_context_summary": initial_context_summary,
            "initial_repo_check_done": True,
             # Add to messages so coordinator LLM sees it directly if prompt is not updated yet
            "messages": state["messages"] + [
                AIMessage(content=f"[System Note: Initial context gathered. {initial_context_summary}]", name="system_context_gatherer")
            ]
        },
        goto="coding_coordinator",
    )
