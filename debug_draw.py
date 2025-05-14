from src.graph.coding_builder import build_coding_graph
import traceback

if __name__ == "__main__":
    print("Building graph...")
    # Use the version of the graph as defined in your workflow.py for LangServe
    # This usually means the one *without* a checkpointer passed in by default for drawing.
    graph = build_coding_graph()
    print("Graph built. Attempting to draw...")
    try:
        # The draw_mermaid_png() method itself requires playwright and other dependencies
        # If these are not installed, this step will fail here.
        # Ensure pygraphviz and other mermaid rendering deps are installed if using .png output.
        img_data = graph.get_graph().draw_mermaid_png()
        with open("debug_graph.png", "wb") as f:
            f.write(img_data)
        print("Graph drawn to debug_graph.png successfully!")
    except ImportError as ie:
        print(f"ImportError during graph drawing: {type(ie).__name__}: {ie}")
        print("This might be due to missing dependencies for drawing, like 'playwright' or 'pygraphviz'.")
        print("Attempting to get Mermaid syntax instead (requires no extra drawing deps)...")
        try:
            mermaid_syntax = graph.get_graph(xray=True).draw_mermaid()
            with open("debug_graph.md", "w") as f:
                f.write("```mermaid\n")
                f.write(mermaid_syntax)
                f.write("\n```")
            print("Mermaid syntax saved to debug_graph.md")
        except Exception as e_mermaid:
            print(f"Error getting Mermaid syntax: {type(e_mermaid).__name__}: {e_mermaid}")
            traceback.print_exc()
    except Exception as e:
        print(f"Error during graph drawing: {type(e).__name__}: {e}")
        traceback.print_exc() 