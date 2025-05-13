#!/usr/bin/env python3
# Debug script for coding workflow structure

import asyncio
import logging
from src.graph.coding_builder import build_coding_graph

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("coding_workflow_debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("coding_workflow_debug")

async def main():
    logger.info("Creating coding graph for debugging structure")
    
    # Create a fresh graph instance
    coding_graph = build_coding_graph()
    
    # Print the Mermaid diagram
    print("\n=== CODING GRAPH STRUCTURE (MERMAID) ===")
    print(coding_graph.get_graph(xray=True).draw_mermaid())
    print("=== END CODING GRAPH STRUCTURE ===\n")
    
    logger.info("Coding graph structure printed")

if __name__ == "__main__":
    asyncio.run(main()) 