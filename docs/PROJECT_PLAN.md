# Project DEAR - AI Development Team Workflow Plan

## Project Goal & Envisioned Workflow

 
**High-Level Envisioned Flow:**

The workflow is designed as a stateful graph where each node represents a specific function or decision point within the development lifecycle. The process is human-centric for strategic decisions and automated for execution, ensuring quality and alignment with user requirements.

1.  **Initiation & PRD Development (Human-AI Collaboration):**
    *   The user (acting as a "Shareholder" or Product Owner) initiates a request for a new feature or project enhancement.
    *   The system (`initial_context_node`) first determines if this pertains to a new or an existing project by checking integrated systems like GitHub and Linear.
    *   The `coding_coordinator_node` then takes the lead, acting like a project manager or tech lead. It iteratively collaborates with the user to build a detailed PRD. This phase includes:
        *   Presenting PRD drafts to the user for review (`human_prd_review_node`).
        *   Optionally triggering research (`context_gatherer_node` -> `research_team_node`) if more information is needed to define the PRD.
        *   Incorporating user feedback and research findings back into the PRD.
    *   This loop continues until the user formally approves the PRD.

2.  **Task Breakdown & Plan Approval (AI Planning, Human Review):**
    *   Once the PRD is approved, the `coding_planner_node` takes over. It analyzes the PRD and breaks it down into a detailed list of actionable development tasks, complete with dependencies, proposed branch names, and any flags for special handling (e.g., tasks to be done sequentially or in isolation).
    *   This detailed task plan is then presented to the user for a second round of human review (`human_feedback_plan_node`).
    *   The user can either accept the task plan or request revisions, looping back to the `coding_planner_node` until the plan is approved.

3.  **System Integration (Linear & GitHub Setup - Future):**
    *   (Conceptual `linear_integration_node`) Upon approval of the task plan, the system will integrate with Linear (or a similar task management tool). The PRD and all defined tasks (with their dependencies, epics, etc.) will be created or updated in Linear. The associated GitHub repository will also be linked or configured if necessary.

4.  **Orchestrated Task Execution (Automated with AI):**
    *   The `task_orchestrator_node` manages the execution of the approved (and Linear-synced) tasks one by one (with future potential for parallelism).
    *   It dispatches individual, ready tasks (respecting dependencies) to the automated code generation pipeline (`initiate_codegen_node` -> `poll_codegen_status_node`).
    *   **Success Path:** If codegen is successful (`codegen_success_node`), the generated code is passed to the `github_manager_node`, which will handle creating a pull request on a pre-defined task branch and (for now) automatically merge it upon success. The orchestrator is then notified to pick up the next task.
    *   **Failure Path:** If codegen fails (`codegen_failure_node`), the failure details are sent back to the `task_orchestrator_node`. The orchestrator can then decide (based on retry logic or severity) to escalate this specific task failure back to the `coding_planner_node` for strategic re-evaluation or modification of that task.

5.  **Project Completion:**
    *   Once all tasks in the plan are successfully executed and merged, the `task_orchestrator_node` transitions the graph to its `END` state, signifying project completion.

This flow prioritizes clear separation of concerns, iterative refinement with human-in-the-loop for critical decision points (PRD and Task Plan), and a robust mechanism for handling execution failures by re-engaging the planning phase. It aims to replicate the diligence and adaptability of a high-performing, safety-conscious agile team.

## I. Core Workflow & Node Responsibilities

**Phase 1: PRD Development & Approval (Iterative)**
- **Goal:** Collaboratively build a comprehensive Product Requirements Document (PRD) with human oversight.
- **Key Nodes:**
    - `initial_context_node`:
        - [ ] Gather initial user request/feature idea.
        - [ ] **NEW:** Determine if this relates to a new or existing project (check Linear/GitHub).
        - [ ] **NEW:** If existing, fetch high-level summary of project status (e.g., active tasks in Linear, main branches).
        - [ ] Set `state.is_existing_project` and `state.existing_project_summary`.
    - `coding_coordinator_node`:
        - [ ] **REVISED:** Manages the PRD lifecycle.
        - [ ] **REVISED:** Initializes PRD draft (incorporates `state.existing_project_summary` if applicable).
        - [ ] **REVISED:** Processes feedback from `human_prd_review_node`.
        - [ ] **REVISED:** Processes research results from `research_team`.
        - [ ] **REVISED:** Iteratively updates `state.prd_document`.
        - [ ] **REVISED:** Decides next step for PRD:
            - `state.prd_next_step = "human_prd_review"` (Get more human feedback)
            - `state.prd_next_step = "context_gatherer"` (Needs research)
        - [ ] **REVISED:** Sets `state.prd_approved = True` when human signals PRD completion.
    - `human_prd_review_node`:
        - [x] Interrupts graph for human input on the current `state.prd_document`.
        - [x] Stores feedback in `state.prd_review_feedback`.
    - `context_gatherer_node`:
        - [x] Prepares for research based on PRD needs.
    - `research_team_node` (uses `researcher_node`):
        - [x] Conducts research.
        - [x] Stores findings in `state.research_results`.

**Phase 2: Task Planning & Approval (Iterative)**
- **Goal:** Break down the approved PRD into a detailed, actionable task plan with human review.
- **Key Nodes:**
    - `coding_planner_node`:
        - [x] Receives approved `state.prd_document`.
        - [ ] **REVISED:** Generates a detailed task list (`state.tasks_definition`):
            - Including dependencies between tasks.
            - Estimations (future).
            - Proposed branch names.
            - Flags (e.g., `execute_alone_first`).
            - **NEW:** Incorporates/updates tasks from `state.existing_project_summary` if `is_existing_project`.
        - [ ] **NEW (Future):** Handles re-planning requests for specific failed tasks from `task_orchestrator_node`.
    - `human_feedback_plan_node`:
        - [x] Interrupts graph for human input on the `state.tasks_definition`.
        - [x] Stores feedback. ("accept" or "revise")

**Phase 3: Linear Integration (Post Task Plan Approval)**
- **Goal:** Persist the PRD and approved tasks into Linear.
- **Key Nodes:**
    - `linear_integration_node` (NEW placeholder node to be added to graph):
        - [ ] Takes approved `state.prd_document` and `state.tasks_definition`.
        - [ ] Creates/updates PRD page in Linear.
        - [ ] Creates/updates tasks, epics, subtasks, and dependencies in Linear.
        - [ ] Links GitHub repo to Linear project if not already.
        - [ ] Stores Linear task IDs/references in `state.tasks_live` (tasks with live IDs).

**Phase 4: Task Orchestration & Execution (Iterative, Task by Task)**
- **Goal:** Manage the execution of individual tasks from the Linear-synced plan.
- **Key Nodes:**
    - `task_orchestrator_node`:
        - [x] **EXISTING (Renamed & Placeholder):** Entry point after task plan approval (or Linear sync).
        - [ ] **REVISED (Implementation Needed):**
            - Manages queue from `state.tasks_live`.
            - Updates status of completed/failed task based on feedback from `github_manager` or `codegen_failure_node`.
            - Identifies next ready task (dependencies met, "execute alone" respected).
            - If task ready: Sets `state.current_task_details` (for codegen) and `state.orchestrator_next_step = "dispatch_task_for_codegen"`.
            - If all tasks done: Sets `state.orchestrator_next_step = "all_tasks_complete"` -> END.
            - If critical/persistent task failure: Sets `state.failed_task_details` and `state.orchestrator_next_step = "forward_failure_to_planner"`.
    - `initiate_codegen_node`:
        - [x] Takes `state.current_task_details`.
        - [x] Starts codegen job.
    - `poll_codegen_status_node`:
        - [x] Polls codegen job.
    - `codegen_success_node`:
        - [x] Handles successful codegen output for `state.current_task_id`.
    - `codegen_failure_node`:
        - [x] Handles failed codegen for `state.current_task_id`.
        - [x] Passes failure details back to `task_orchestrator_node`.
    - `github_manager_node`:
        - [x] Takes successful codegen output for `state.current_task_id`.
        - [ ] **REVISED:** Creates/updates PR for the specific task branch.
        - [ ] **REVISED:** On successful merge (can be automated for now, or a manual step later), signals success for `state.current_task_id` back to `task_orchestrator_node`.

## II. State Object (`src/graph/types.py`) Revisions Needed

- [ ] `is_existing_project: bool = False`
- [ ] `existing_project_summary: Optional[Dict] = None` (or a more structured object)
- [ ] `prd_document: Optional[str] = ""` (or a structured PRD object)
- [ ] `prd_review_feedback: Optional[str] = None`
- [ ] `prd_approved: bool = False`
- [ ] `prd_next_step: Optional[str] = None` (values: "human_prd_review", "context_gatherer", "coding_planner")
- [ ] `research_results: Optional[Any] = None`
- [ ] `tasks_definition: Optional[List[Dict]] = None` (Detailed plan from `coding_planner` before Linear)
    - Task Dict: `{id, description, dependencies: List[id], branch_name, status_in_plan, execute_alone, etc.}`
- [ ] `tasks_live: Optional[List[Dict]] = None` (Tasks after Linear sync, with Linear IDs)
    - Task Dict: `{linear_id, github_branch, status_live, ...}`
- [ ] `current_task_id: Optional[str] = None` (The ID of the task currently being processed by orchestrator->codegen->github)
- [ ] `current_task_details: Optional[Dict] = None` (Details of the task for `initiate_codegen`)
- [ ] `orchestrator_next_step: Optional[str] = None` (values: "dispatch_task_for_codegen", "forward_failure_to_planner", "all_tasks_complete")
- [ ] `failed_task_details: Optional[Dict] = None` (Info for planner if orchestrator escalates a failure)

## III. Node Implementation To-Do (in `src/graph/nodes.py`)

- [x] Rename `prepare_codegen_task_node` to `task_orchestrator_node` (placeholder exists).
- [ ] Implement full logic for `task_orchestrator_node`.
- [ ] Implement/Update `initial_context_node` for existing project checks.
- [ ] Implement/Update `coding_coordinator_node` for PRD lifecycle, existing project data, and routing logic.
- [ ] Implement `human_prd_review_node` (similar to `human_feedback_plan_node`).
- [ ] Update `coding_planner_node` to handle `is_existing_project` data and potential re-planning of failed tasks.
- [ ] Create placeholder for `linear_integration_node`.
- [ ] Update `github_manager_node` to signal task completion (with ID) to `task_orchestrator_node`.
- [ ] Update `codegen_failure_node` to pass rich failure details (with ID) to `task_orchestrator_node`.

## IV. Graph Structure (`src/graph/coding_builder.py`) To-Do

- [ ] Add `linear_integration_node` between `human_feedback_plan` ("accept") and `task_orchestrator_node`.
- [ ] Ensure all conditional routing functions (`route_from_coordinator`, `route_from_orchestrator`) correctly use `state` fields set by their preceding nodes.

This provides a good roadmap. The "NEW" and "REVISED" items are the main focus.
The `ImportError` is addressed by the placeholder for `task_orchestrator_node`. Now you can iteratively implement the node logic and state changes. 