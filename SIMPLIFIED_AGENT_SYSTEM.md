# Simplified 4-Agent System for DEAR

This document describes the simplified 4-agent system implemented for the DEAR project.

## Overview

The simplified system consists of 4 main agents:

1. **Planner Agent** - Talks to the user and iterates on a plan/PDR
2. **Task Planner Agent** - Takes the PDR and breaks it into individual tasks
3. **Orchestration Agent** - Prioritizes tasks based on dependencies and starts Codegen agents
4. **Codegen Agent** - Executes coding tasks and is monitored by the Orchestration Agent

## Workflow

The workflow follows these steps:

1. **Initial Context & PDR Creation**:
   - User provides a request
   - Planner Agent gathers initial context
   - Planner Agent creates a PDR (Product Development Request)
   - User reviews and approves the PDR

2. **Task Planning**:
   - Task Planner Agent breaks down the PDR into individual tasks
   - Tasks include dependencies, acceptance criteria, etc.
   - User reviews and approves the task plan

3. **Task Orchestration**:
   - Orchestration Agent prioritizes tasks based on dependencies
   - Tasks are created in Linear (if enabled)
   - Orchestration Agent starts Codegen agents for each task in order

4. **Task Execution**:
   - Codegen Agent executes each task
   - Orchestration Agent monitors the progress
   - On success, PR is validated and merged
   - On failure, Orchestration Agent handles retries or reports issues

5. **Completion**:
   - When all tasks are complete, the workflow ends

## Graph Structure

The graph structure is simplified compared to the original implementation:

- Clear, linear flow between the main agents
- Explicit human review steps for PDR and task plan
- Simplified error handling and retry logic
- Focused on the core workflow without extraneous nodes

## Running the Simplified System

To run the simplified system:

```bash
# Non-interactive mode
python run_simplified_workflow.py "Create a web application for task tracking"

# Interactive mode (with human input for reviews)
python run_simplified_workflow.py --interactive "Create a web application for task tracking"
```

## Visualizing the Graph

To visualize the simplified graph structure:

```bash
python generate_simplified_mermaid.py
```

This will generate a Mermaid diagram in `simplified_4agent_graph.md` that shows the structure of the simplified graph.

## Implementation Details

The simplified system is implemented in:

- `src/graph/simplified_builder.py` - Main graph definition
- `run_simplified_workflow.py` - Script to run the workflow
- `generate_simplified_mermaid.py` - Script to visualize the graph

The implementation focuses on clarity and simplicity while maintaining the core functionality of the 4-agent system.

