# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

from .common import *

def parse_json_response(response: str) -> Dict[str, Any]:
    """Parse a JSON response from an LLM."""
    try:
        # Try to parse the JSON directly
        return json.loads(response)
    except json.JSONDecodeError:
        # If that fails, try to extract JSON from the response
        try:
            # Look for JSON-like content between triple backticks
            if "```json" in response and "```" in response.split("```json", 1)[1]:
                json_content = response.split("```json", 1)[1].split("```", 1)[0]
                return json.loads(json_content)
            # Look for JSON-like content between regular backticks
            elif "```" in response and "```" in response.split("```", 1)[1]:
                json_content = response.split("```", 1)[1].split("```", 1)[0]
                return json.loads(json_content)
            # Look for JSON-like content between curly braces
            elif "{" in response and "}" in response:
                json_content = response[response.find("{"):response.rfind("}") + 1]
                return json.loads(json_content)
            else:
                raise ValueError("Could not find JSON-like content in the response")
        except Exception as e:
            # If all parsing attempts fail, use the repair_json_output function
            repaired_json = repair_json_output(response)
            return json.loads(repaired_json)


def format_task_for_display(task: Dict[str, Any]) -> str:
    """Format a task for display to the user."""
    formatted_task = f"# {task.get('name', 'Untitled Task')}\n\n"
    formatted_task += f"## Description\n{task.get('description', 'No description provided.')}\n\n"
    
    if task.get('acceptance_criteria'):
        formatted_task += "## Acceptance Criteria\n"
        for i, criterion in enumerate(task['acceptance_criteria']):
            formatted_task += f"{i+1}. {criterion}\n"
        formatted_task += "\n"
    
    if task.get('dependencies'):
        formatted_task += "## Dependencies\n"
        for i, dependency in enumerate(task['dependencies']):
            formatted_task += f"{i+1}. {dependency}\n"
        formatted_task += "\n"
    
    formatted_task += f"**Estimated Effort:** {task.get('estimated_effort_hours', 0)} hours\n"
    formatted_task += f"**Status:** {task.get('status_live', 'Todo')}\n"
    
    return formatted_task


def get_task_dependencies(tasks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Get a dictionary of task dependencies."""
    dependencies = {}
    for task in tasks:
        task_id = task.get('id')
        if task_id:
            dependencies[task_id] = task.get('dependencies', [])
    return dependencies


def sort_tasks_by_dependencies(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort tasks by dependencies."""
    # Create a dictionary of task IDs to tasks
    task_dict = {task.get('id'): task for task in tasks if task.get('id')}
    
    # Create a dictionary of task dependencies
    dependencies = get_task_dependencies(tasks)
    
    # Create a list to store the sorted tasks
    sorted_tasks = []
    
    # Create a set to track visited tasks
    visited = set()
    
    # Define a recursive function to visit tasks
    def visit(task_id):
        if task_id in visited:
            return
        visited.add(task_id)
        for dep_id in dependencies.get(task_id, []):
            if dep_id in task_dict:
                visit(dep_id)
        sorted_tasks.append(task_dict[task_id])
    
    # Visit all tasks
    for task_id in task_dict:
        if task_id not in visited:
            visit(task_id)
    
    return sorted_tasks

