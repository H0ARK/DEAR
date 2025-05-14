# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .types import State
from .nodes import (
    coordinator_node,
    coding_planner_node,
    reporter_node,
    research_team_node,
    researcher_node,
    coder_node,
    background_investigation_node,
)

from .context_nodes import context_gathering_node


def _build_base_graph():
    """Build and return the base state graph with all nodes and edges."""
    builder = StateGraph(State)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("background_investigator", background_investigation_node)
    builder.add_node("context_gatherer", context_gathering_node)
    builder.add_node("coding_planner", coding_planner_node)
    builder.add_node("reporter", reporter_node)
    builder.add_node("research_team", research_team_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("coder", coder_node)

    # Define Edges
    # Start node
    builder.add_edge(START, "coordinator")

    # Conditional edge from Coordinator (handoff or background)
    # Assumes coordinator_node returns Command with goto='background_investigator' or 'context_gatherer'
    builder.add_conditional_edges(
        "coordinator",
        lambda x: x.get("goto", "__end__"), # Route based on goto field from coordinator_node, default to __end__
        {
            "background_investigator": "background_investigator",
            "context_gatherer": "context_gatherer",  # Route to context gatherer
            "__end__": END, # Handle case where coordinator decides to end
        }
    )

    builder.add_edge("background_investigator", "context_gatherer")  # Go to context gatherer after background investigation

    # Context gatherer routes to the coding planner
    builder.add_edge("context_gatherer", "coding_planner")

    builder.add_conditional_edges(
        "coding_planner",
        # Route based on goto field from planner_node
        lambda x: x.get("goto", "__end__"),
         {
            "research_team": "research_team",
            "__end__": END, # Handle case where planner decides to end
        }
    )

    builder.add_conditional_edges(
        "research_team",
        # Route based on goto field from research_team_node
        lambda x: x.get("goto", "coding_planner"),
        {
            "researcher": "researcher",
            "coder": "coder",
            "coding_planner": "coding_planner", # Loop back to planner if done/error
        }
    )

    builder.add_edge("researcher", "research_team") # Agent nodes loop back to team
    builder.add_edge("coder", "research_team")      # Agent nodes loop back to team

    builder.add_edge("reporter", END)
    return builder


def build_graph_with_memory():
    """Build and return the agent workflow graph with memory."""
    # use persistent memory to save conversation history
    # TODO: be compatible with SQLite / PostgreSQL
    memory = MemorySaver()

    # build state graph
    builder = _build_base_graph()
    return builder.compile(checkpointer=memory)


def build_graph():
    """Build and return the agent workflow graph without memory."""
    # build state graph
    builder = _build_base_graph()
    return builder.compile()


# Create the graph instance
# graph = build_graph()
