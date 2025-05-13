# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
from typing import Literal, Dict, Any, Optional, List

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.config.configuration import Configuration
from src.tools.github_service import GitHubService, GitHubContext
from src.tools.linear_service import LinearService, LinearTask
from src.tools.repo_analyzer import RepoAnalyzer, RepoAnalysisResult
from src.graph.types import State

logger = logging.getLogger(__name__)

def context_gathering_node(
    state: State, config: RunnableConfig
) -> Command[Literal["coding_planner", "__end__"]]:
    """Node that gathers context from Linear and the repository before planning."""
    logger.info("Context gathering node executing...")
    configurable = Configuration.from_runnable_config(config)

    # Initialize context information
    context_info = {
        "linear_tasks": [],
        "linear_epics": [],
        "repo_analysis": None,
        "git_info": None
    }

    # Analyze repository first to get the repository name
    try:
        repo_analyzer = RepoAnalyzer(configurable.repo_path or ".")
        repo_analysis = repo_analyzer.analyze()

        # Simplify the repo analysis for the context
        simplified_analysis = {
            "file_count": repo_analysis.file_count,
            "directory_count": repo_analysis.directory_count,
            "languages": repo_analysis.languages,
            "dependencies": repo_analysis.dependencies,
            "readme_summary": repo_analysis.readme_content[:500] + "..." if repo_analysis.readme_content and len(repo_analysis.readme_content) > 500 else repo_analysis.readme_content,
            "top_level_directories": [
                dir_path for dir_path in repo_analysis.directories.keys()
                if dir_path and "/" not in dir_path and not dir_path.startswith(".")
            ],
            "gitignore_patterns": repo_analysis.gitignore_patterns
        }

        # Get Git information
        git_info = RepoAnalyzer.get_git_info(configurable.repo_path or ".")

        context_info["repo_analysis"] = simplified_analysis
        context_info["git_info"] = git_info

        logger.info(f"Repository analysis complete: {repo_analysis.file_count} files, {repo_analysis.directory_count} directories")
    except Exception as e:
        logger.error(f"Error analyzing repository: {e}")
        context_info["repo_error"] = str(e)

    # Get Linear tasks and epics if configured
    if configurable.linear_api_key and configurable.linear_team_id:
        try:
            linear_service = LinearService(
                api_key=configurable.linear_api_key,
                team_id=configurable.linear_team_id
            )

            # Get or create project based on configuration or repository name
            project = None
            project_name = configurable.linear_project_name

            # If no project name is specified, use the repository name
            if not project_name and context_info.get("git_info") and context_info["git_info"].get("remote_url"):
                # Extract repo name from remote URL
                remote_url = context_info["git_info"]["remote_url"]
                logger.info(f"Extracting project name from remote URL: {remote_url}")

                # Handle both HTTPS and SSH URLs
                if remote_url.endswith(".git"):
                    remote_url = remote_url[:-4]  # Remove .git suffix
                    logger.info(f"Removed .git suffix: {remote_url}")

                repo_name = remote_url.split("/")[-1]  # Get the last part of the URL
                logger.info(f"Extracted repository name: {repo_name}")

                project_name = repo_name
                logger.info(f"Using repository name as project name: {project_name}")

            if project_name:
                project = linear_service.filter_or_create_project(
                    project_name=project_name,
                    description=f"Project created by DEAR agent for {configurable.linear_team_id}"
                )
                logger.info(f"Using Linear project: {project.name} (ID: {project.id})")
                context_info["linear_project"] = {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description[:200] + "..." if len(project.description) > 200 else project.description,
                    "state": project.state,
                    "team_ids": project.team_ids
                }

            # Get active tasks
            tasks = linear_service.get_team_tasks(include_completed=False)
            if tasks:
                # Filter tasks by project if a project is specified
                if project:
                    tasks = [task for task in tasks if task.project_id == project.id]

                context_info["linear_tasks"] = [
                    {
                        "id": task.id,
                        "title": task.title,
                        "description": task.description[:200] + "..." if len(task.description) > 200 else task.description,
                        "state": task.state,
                        "parent_id": task.parent_id,
                        "labels": task.labels,
                        "project_id": task.project_id
                    }
                    for task in tasks
                ]
            else:
                context_info["linear_tasks"] = []
                logger.info("No active tasks found in Linear or unable to fetch tasks")

            # Get epics
            epics = linear_service.get_epics()
            if epics:
                # Filter epics by project if a project is specified
                if project:
                    epics = [epic for epic in epics if epic.project_id == project.id]

                context_info["linear_epics"] = [
                    {
                        "id": epic.id,
                        "title": epic.title,
                        "description": epic.description[:200] + "..." if len(epic.description) > 200 else epic.description,
                        "state": epic.state,
                        "completed": epic.completed,
                        "labels": epic.labels,
                        "project_id": epic.project_id
                    }
                    for epic in epics
                ]
            else:
                context_info["linear_epics"] = []
                logger.info("No epics found in Linear or unable to fetch epics")

            logger.info(f"Retrieved {len(tasks)} active tasks and {len(epics)} epics from Linear")
        except Exception as e:
            logger.error(f"Error retrieving Linear context: {e}")
            context_info["linear_error"] = str(e)
            context_info["linear_tasks"] = []
            context_info["linear_epics"] = []

    # Repository analysis was already done at the beginning of the function

    # Create a summary message for the planner
    context_summary = "# Context Information\n\n"

    # Add Git information
    if context_info["git_info"]:
        context_summary += "## Git Information\n"
        context_summary += f"- Current Branch: {context_info['git_info']['current_branch']}\n"
        context_summary += f"- Remote URL: {context_info['git_info']['remote_url']}\n"
        if context_info["git_info"]["last_commit"]:
            context_summary += f"- Last Commit: {context_info['git_info']['last_commit']['hash']} - {context_info['git_info']['last_commit']['message']}\n"
        context_summary += f"- Uncommitted Changes: {context_info['git_info']['uncommitted_changes']}\n\n"

    # Add repository analysis
    if context_info["repo_analysis"]:
        context_summary += "## Repository Analysis\n"
        context_summary += f"- File Count: {context_info['repo_analysis']['file_count']}\n"
        context_summary += f"- Directory Count: {context_info['repo_analysis']['directory_count']}\n"

        # Add languages
        if context_info["repo_analysis"]["languages"]:
            context_summary += "- Languages:\n"
            for lang, count in context_info["repo_analysis"]["languages"].items():
                context_summary += f"  - {lang}: {count} files\n"

        # Add dependencies
        if context_info["repo_analysis"]["dependencies"]:
            context_summary += "- Dependencies:\n"
            for framework, deps in context_info["repo_analysis"]["dependencies"].items():
                context_summary += f"  - {framework}: {', '.join(deps[:5])}{'...' if len(deps) > 5 else ''}\n"

        # Add top-level directories
        if context_info["repo_analysis"]["top_level_directories"]:
            context_summary += "- Top-Level Directories:\n"
            for dir_name in context_info["repo_analysis"]["top_level_directories"]:
                context_summary += f"  - {dir_name}\n"

        # Add README summary
        if context_info["repo_analysis"]["readme_summary"]:
            context_summary += "- README Summary:\n"
            context_summary += f"  {context_info['repo_analysis']['readme_summary']}\n\n"

    # Add Linear project information
    if context_info.get("linear_project"):
        context_summary += "## Linear Project\n"
        context_summary += f"- **{context_info['linear_project']['name']}** ({context_info['linear_project']['id']})\n"
        if context_info['linear_project']['description']:
            context_summary += f"  - {context_info['linear_project']['description']}\n"
        context_summary += "\n"

    # Add Linear epics
    if context_info["linear_epics"]:
        context_summary += "## Linear Epics\n"
        for epic in context_info["linear_epics"]:
            status = "✅" if epic["completed"] else "🔄"
            project_info = f" [Project: {epic['project_id']}]" if epic.get("project_id") else ""
            context_summary += f"- {status} **{epic['title']}** ({epic['id']}){project_info}\n"
            if epic["description"]:
                context_summary += f"  - {epic['description']}\n"
        context_summary += "\n"

    # Add Linear tasks
    if context_info["linear_tasks"]:
        context_summary += "## Linear Tasks\n"

        # Group tasks by epic
        tasks_by_epic = {}
        standalone_tasks = []

        for task in context_info["linear_tasks"]:
            if task["parent_id"]:
                if task["parent_id"] not in tasks_by_epic:
                    tasks_by_epic[task["parent_id"]] = []
                tasks_by_epic[task["parent_id"]].append(task)
            else:
                standalone_tasks.append(task)

        # Add tasks grouped by epic
        for epic_id, tasks in tasks_by_epic.items():
            # Find the epic title
            epic_title = "Unknown Epic"
            for epic in context_info["linear_epics"]:
                if epic["id"] == epic_id:
                    epic_title = epic["title"]
                    break

            context_summary += f"- Epic: **{epic_title}** ({epic_id})\n"
            for task in tasks:
                project_info = f" [Project: {task['project_id']}]" if task.get("project_id") else ""
                context_summary += f"  - [{task['state']}] {task['title']} ({task['id']}){project_info}\n"

        # Add standalone tasks
        if standalone_tasks:
            context_summary += "- Standalone Tasks:\n"
            for task in standalone_tasks:
                project_info = f" [Project: {task['project_id']}]" if task.get("project_id") else ""
                context_summary += f"  - [{task['state']}] {task['title']} ({task['id']}){project_info}\n"

        context_summary += "\n"

    # Add errors if any
    if "linear_error" in context_info:
        context_summary += f"⚠️ Linear Error: {context_info['linear_error']}\n"
    if "repo_error" in context_info:
        context_summary += f"⚠️ Repository Analysis Error: {context_info['repo_error']}\n"

    # Determine where to go next based on the current workflow
    goto = "coding_planner"  # Default to coding planner
    # The research workflow also uses the coding_planner for now

    # Update state with context information
    return Command(
        update={
            "messages": state["messages"] + [AIMessage(content=context_summary, name="context_gatherer")],
            "context_info": context_info
        },
        goto=goto
    )
