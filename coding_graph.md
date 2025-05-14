```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	initial_context(initial_context)
	human_initial_context_review(human_initial_context_review)
	coding_coordinator(coding_coordinator)
	human_prd_review(human_prd_review)
	context_gatherer(context_gatherer)
	research_team(research_team)
	coding_planner(coding_planner)
	human_feedback_plan(human_feedback_plan)
	linear_integration(linear_integration)
	human_plan_review(human_plan_review)
	task_orchestrator(task_orchestrator)
	initiate_codegen(initiate_codegen)
	poll_codegen_status(poll_codegen_status)
	codegen_success(codegen_success)
	codegen_failure(codegen_failure)
	github_manager(github_manager)
	__end__([<p>__end__</p>]):::last
	__start__ --> initial_context;
	codegen_failure --> task_orchestrator;
	codegen_success --> github_manager;
	coding_planner --> human_feedback_plan;
	context_gatherer --> research_team;
	github_manager --> task_orchestrator;
	human_initial_context_review --> coding_coordinator;
	human_prd_review --> coding_coordinator;
	initial_context --> human_initial_context_review;
	initiate_codegen --> poll_codegen_status;
	linear_integration --> task_orchestrator;
	human_plan_review --> linear_integration;
	researcher___end__ --> research_team;
	coding_coordinator -.-> human_prd_review;
	coding_coordinator -.-> context_gatherer;
	coding_coordinator -.-> coding_planner;
	coding_coordinator -.-> __end__;
	research_team -.-> researcher___start__;
	research_team -.-> coding_coordinator;
	research_team -.-> coding_planner;
	research_team -.-> task_orchestrator;
	human_feedback_plan -. &nbsp;revise&nbsp; .-> coding_planner;
	human_feedback_plan -. &nbsp;accept&nbsp; .-> human_plan_review;
	task_orchestrator -.-> initiate_codegen;
	task_orchestrator -.-> coding_planner;
	task_orchestrator -.-> __end__;
	poll_codegen_status -. &nbsp;success&nbsp; .-> codegen_success;
	poll_codegen_status -. &nbsp;failure&nbsp; .-> codegen_failure;
	poll_codegen_status -. &nbsp;error&nbsp; .-> codegen_failure;
	initial_context -.-> coding_coordinator;
	human_initial_context_review -.-> coding_coordinator;
	coding_coordinator -.-> human_prd_review;
	coding_coordinator -.-> context_gatherer;
	coding_coordinator -.-> coding_planner;
	coding_coordinator -.-> __end__;
	human_prd_review -.-> coding_coordinator;
	context_gatherer -.-> research_team;
	research_team -.-> researcher___start__;
	research_team -.-> task_orchestrator;
	research_team -.-> coding_coordinator;
	research_team -.-> coding_planner;
	researcher___end__ -.-> research_team;
	coding_planner -.-> human_feedback_plan;
	coding_planner -.-> __end__;
	human_feedback_plan -.-> coding_planner;
	human_feedback_plan -.-> linear_integration;
	human_plan_review -.-> linear_integration;
	linear_integration -.-> task_orchestrator;
	github_manager -.-> task_orchestrator;
	github_manager -.-> coding_planner;
	github_manager -.-> __end__;
	subgraph researcher
	researcher___start__(<p>__start__</p>)
	researcher_agent(agent)
	researcher_tools(tools)
	researcher___end__(<p>__end__</p>)
	researcher___start__ --> researcher_agent;
	researcher_tools --> researcher_agent;
	researcher_agent -.-> researcher_tools;
	researcher_agent -.-> researcher___end__;
	end
	poll_codegen_status -. &nbsp;continue&nbsp; .-> poll_codegen_status;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```