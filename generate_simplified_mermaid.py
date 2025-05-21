#!/usr/bin/env python3
# Script to generate a Mermaid diagram of the simplified 4-agent system graph

import logging
from src.graph.simplified_builder import build_simplified_graph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Building the simplified 4-agent system graph...")
    simplified_graph = build_simplified_graph()
    
    # Generate Mermaid diagram
    mermaid_syntax = simplified_graph.get_graph(xray=True).draw_mermaid()
    
    # Save to file
    output_file = "simplified_4agent_graph.md"
    with open(output_file, "w") as f:
        f.write("```mermaid\n")
        f.write(mermaid_syntax)
        f.write("\n```")
    
    logger.info(f"Simplified 4-agent system Mermaid diagram saved to {output_file}")
    
    # Also print to console
    print("\n=== SIMPLIFIED 4-AGENT SYSTEM GRAPH STRUCTURE (MERMAID) ===")
    print(mermaid_syntax)
    print("=== END SIMPLIFIED 4-AGENT SYSTEM GRAPH STRUCTURE ===\n")

if __name__ == "__main__":
    main()

