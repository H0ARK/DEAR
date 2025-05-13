#!/usr/bin/env python3
# Script to generate a fresh Mermaid diagram of the coding graph

import logging
from src.graph.coding_builder import build_coding_graph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Building a fresh coding graph...")
    coding_graph = build_coding_graph()
    
    # Generate Mermaid diagram
    mermaid_syntax = coding_graph.get_graph(xray=True).draw_mermaid()
    
    # Save to file
    output_file = "fresh_coding_graph.md"
    with open(output_file, "w") as f:
        f.write("```mermaid\n")
        f.write(mermaid_syntax)
        f.write("\n```")
    
    logger.info(f"Fresh Mermaid diagram saved to {output_file}")
    
    # Also print to console
    print("\n=== FRESH CODING GRAPH STRUCTURE (MERMAID) ===")
    print(mermaid_syntax)
    print("=== END FRESH CODING GRAPH STRUCTURE ===\n")

if __name__ == "__main__":
    main() 