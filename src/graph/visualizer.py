# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def save_graph_visualization(
    graph,
    output_path: str = "graph_visualization.png",
    draw_method: str = "api",
):
    """Generates and saves a visualization of the LangGraph graph.

    Args:
        graph: The compiled LangGraph instance.
        output_path: The path to save the visualization image.
        draw_method: Method to use for drawing. 
                     Supported: "mermaid.ink", "pyppeteer", "graphviz".
                     "mermaid.ink" is used by default and requires no extra deps for PNG.
                     "pyppeteer" requires pyppeteer and nest_asyncio.
                     "graphviz" requires pygraphviz and its system dependencies.
    """
    try:
        if not hasattr(graph, "get_graph") or not callable(graph.get_graph):
            logger.error(
                "The provided graph object does not have a callable 'get_graph' method."
            )
            return

        runnable_graph = graph.get_graph()

        if draw_method == "api" or draw_method == "pyppeteer":
            from langchain_core.runnables.graph import MermaidDrawMethod

            method_enum = (
                MermaidDrawMethod.PYPPETEER
                if draw_method == "pyppeteer"
                else MermaidDrawMethod.API
            )
            
            # Ensure nest_asyncio is applied if using pyppeteer in a Jupyter-like environment
            # This might be needed if the environment blocks the asyncio event loop.
            if draw_method == "pyppeteer":
                try:
                    import nest_asyncio
                    nest_asyncio.apply()
                    logger.info("nest_asyncio applied for pyppeteer visualization.")
                except ImportError:
                    logger.warning(
                        "nest_asyncio not found. Pyppeteer might have issues in some environments (e.g., Jupyter notebooks) without it."
                    )
                except RuntimeError as e:
                    if "cannot apply loop ELOOP" in str(e).lower() or "another loop is running" in str(e).lower():
                         logger.info(f"nest_asyncio: {e}. Assuming already applied or not needed.")
                    else:
                        logger.warning(f"Error applying nest_asyncio: {e}")

            image_bytes = runnable_graph.draw_mermaid_png(draw_method=method_enum)
        elif draw_method == "graphviz":
            image_bytes = runnable_graph.draw_png()
        else:
            logger.error(f"Unsupported draw_method: {draw_method}")
            return

        with open(output_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"Graph visualization saved to {Path(output_path).resolve()}")

    except ImportError as e:
        if draw_method == "pyppeteer" and "pyppeteer" in str(e).lower():
            logger.error(
                f"ImportError: {e}. Please install pyppeteer (`pip install pyppeteer`) and its browser dependencies to use the 'pyppeteer' draw method."
            )
        elif draw_method == "graphviz" and "pygraphviz" in str(e).lower():
            logger.error(
                f"ImportError: {e}. Please install pygraphviz (`pip install pygraphviz`) and its system dependencies (e.g., graphviz library) to use the 'graphviz' draw method."
            )
        else:
            logger.error(f"Error during graph visualization: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during graph visualization: {e}")


def get_graph_mermaid_syntax(graph) -> str | None:
    """Returns the Mermaid syntax for the LangGraph graph."""
    try:
        if not hasattr(graph, "get_graph") or not callable(graph.get_graph):
            logger.error(
                "The provided graph object does not have a callable 'get_graph' method."
            )
            return None
        return graph.get_graph().draw_mermaid()
    except Exception as e:
        logger.error(f"An unexpected error occurred while generating Mermaid syntax: {e}")
        return None 