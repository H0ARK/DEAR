# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Optional

# Optional dependencies - try to import, but gracefully handle missing
try:
    from IPython.display import Image, display # type: ignore
    import matplotlib.pyplot as plt # type: ignore
    import networkx as nx # type: ignore
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False

logger = logging.getLogger(__name__)

def save_graph_visualization(graph, filename="graph_visualization.png"):
    """
    Visualize the graph and save it to a file.
    
    Args:
        graph: The compiled langgraph graph object
        filename: The name of the output image file
        
    Returns:
        None
    """
    if not VISUALIZATION_AVAILABLE:
        logger.warning("Graph visualization requires matplotlib and networkx. Install with: pip install matplotlib networkx")
        return
    
    try:
        # Get the NetworkX graph from the langgraph
        G = graph.get_graph().to_networkx()
        
        # Create a figure with a reasonable size
        plt.figure(figsize=(12, 8))
        
        # Use a layout that works well for workflow visualization
        pos = nx.spring_layout(G, k=0.5, iterations=50)
        
        # Draw the nodes
        nx.draw_networkx_nodes(G, pos, node_size=2000, node_color="lightblue", alpha=0.8)
        
        # Draw the edges
        nx.draw_networkx_edges(G, pos, width=1.5, alpha=0.7, arrows=True, arrowsize=20)
        
        # Add node labels
        nx.draw_networkx_labels(G, pos, font_size=10, font_family="sans-serif")
        
        # Add edge labels when available
        edge_labels = {}
        for u, v, data in G.edges(data=True):
            if "condition" in data and data["condition"] != "":
                edge_labels[(u, v)] = data["condition"]
        
        nx.draw_networkx_edge_labels(
            G, pos, edge_labels=edge_labels, font_size=8
        )
        
        # Remove the axes
        plt.axis("off")
        
        # Save the figure
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        logger.info(f"Graph visualization saved to {filename}")
    except Exception as e:
        logger.error(f"Error visualizing graph: {e}")

def get_graph_mermaid_syntax(graph):
    """
    Generate Mermaid syntax for the graph.
    
    Args:
        graph: The compiled langgraph graph object
        
    Returns:
        str: Mermaid syntax for the graph
    """
    try:
        # Extract Mermaid syntax directly from the graph
        mermaid_output = graph.get_graph(xray=True).draw_mermaid()
        return mermaid_output
    except Exception as e:
        logger.error(f"Error generating Mermaid syntax: {e}")
        return None 