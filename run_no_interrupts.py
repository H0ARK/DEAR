#!/usr/bin/env python3
# A simplified direct version that skips the langgraph complexities

import logging
from src.llms.llm import get_llm_by_type
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import json
import os
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# JSON repair utility
def repair_json_output(json_str):
    """
    Simple utility to attempt to repair invalid JSON by:
    1. Stripping markdown code block markers
    2. Removing leading/trailing non-JSON text
    3. Fixing common JSON syntax errors
    """
    # Check if it's already valid JSON
    try:
        json.loads(json_str)
        return json_str
    except:
        pass
        
    # Strip markdown code blocks
    if "```json" in json_str:
        parts = json_str.split("```json")
        if len(parts) > 1:
            json_str = parts[1]
            
    if "```" in json_str:
        parts = json_str.split("```")
        if len(parts) > 1:
            json_str = parts[1]
    
    # Remove trailing ```
    json_str = json_str.replace("```", "").strip()
    
    # Try to find JSON brackets
    first_brace = json_str.find('{')
    last_brace = json_str.rfind('}')
    
    if first_brace >= 0 and last_brace > first_brace:
        json_str = json_str[first_brace:last_brace+1]
    
    # Remove extra commas before closing brackets
    json_str = json_str.replace(",]", "]").replace(",}", "}")
    
    # Fix missing quotes around keys
    import re
    json_str = re.sub(r'(\s*)(\w+)(\s*):', r'\1"\2"\3:', json_str)
    
    # Check if valid before returning
    try:
        json.loads(json_str)
        logger.info("Successfully repaired JSON")
    except Exception as e:
        logger.warning(f"Repair attempt failed: {str(e)[:200]}")
    
    return json_str

# Helper function to extract JSON from text with markdown
def extract_json_from_text(text):
    """Extract JSON from text that might include markdown and other content."""
    # Check if it's already valid JSON
    try:
        json.loads(text)
        return text
    except:
        pass

    # First, check if it's wrapped in code blocks
    if "```json" in text:
        # Extract content between ```json and ```
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            json_text = text[start:end].strip()
            try:
                json.loads(json_text)
                return json_text
            except:
                pass  # If it's not valid, continue trying other methods
    
    # Check for regular code blocks
    if "```" in text:
        # Extract content between ``` and ```
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            json_text = text[start:end].strip()
            try:
                json.loads(json_text)
                return json_text
            except:
                pass  # If it's not valid, continue trying other methods
    
    # Try to find valid JSON based on braces
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        json_text = text[start:end]
        try:
            json.loads(json_text)
            return json_text
        except:
            pass  # If it's not valid, continue trying other methods
    
    # If all else fails, attempt to repair
    return repair_json_output(text)

def generate_player_movement_code():
    """Generate code for the player movement task."""
    system_message = SystemMessage(content="""You are an expert Python developer implementing player movement for a simple 2D game.
Generate working Python code that builds on the base game setup to add player character movement using keyboard controls.

The code should:
1. Create a player object with position, size, and speed attributes
2. Handle keyboard input to move the player in all four directions (up, down, left, right)
3. Implement boundary checking to prevent the player from moving off-screen
4. Display the player as a colored rectangle or circle

The code should be complete, runnable, and follow best practices.
""")

    task_context = """
The base game setup has already been implemented with:
- A game window of 800x600 pixels
- Basic Pygame initialization and game loop structure
- Event handling for quitting the game
- The ability to close the game with ESC key

Now we need to add a controllable player character.
"""

    try:
        # Get the LLM to generate the code
        llm = get_llm_by_type("basic")
        response = llm.invoke([system_message, HumanMessage(content=task_context)])
        player_code = response.content
        
        # Save the implementation to a file
        task_filename = "player_movement.py"
        with open(task_filename, "w") as f:
            f.write(player_code)
        logger.info(f"Player movement code saved to {task_filename}")
        
        return player_code
    except Exception as e:
        logger.error(f"Error generating player movement code: {e}")
        traceback.print_exc()
        return None

def main(user_input="Build a simple 2D game in Python"):
    """Run a direct coding workflow without langgraph."""
    print(f"Starting direct workflow with input: {user_input}")
    
    # Initialize variables
    prd_document = ""
    task_plan_text = ""
    code_implementation = ""
    first_task_name = ""
    
    # 1. Generate a PRD
    print("\n=== Step 1: Generating PRD ===")
    try:
        # Set up prompt
        system_message = SystemMessage(content="You are an expert software architect creating a Product Requirements Document. Create a comprehensive PRD for this request.")
        user_message = HumanMessage(content=f"Original request: {user_input}")
        
        # Get response from LLM
        llm = get_llm_by_type("basic")
        prd_response = llm.invoke([system_message, user_message])
        prd_document = prd_response.content
        
        print(f"PRD generated successfully ({len(prd_document)} characters)")
        print("\n--- PRD Preview ---")
        print(prd_document[:500] + "...\n")
    except Exception as e:
        logger.error(f"Error generating PRD: {e}")
        return
    
    # 2. Generate a Task Plan
    print("\n=== Step 2: Generating Task Plan ===")
    try:
        # Set up prompt for the task plan with specific JSON structure
        system_message = SystemMessage(content="""You are an expert software architect creating a detailed task plan. 
Break down the PRD into specific implementation tasks.

Your response should be VALID JSON in the following format:
{
  "title": "Implementation Task Plan for [Game Name]",
  "tasks": [
    {
      "id": "1.1",
      "name": "Task name",
      "description": "Detailed task description",
      "estimated_hours": 2,
      "dependencies": [],
      "subtasks": [
        {
          "id": "1.1.1",
          "description": "Subtask description"
        }
      ]
    }
  ]
}

Make sure your response is ONLY the JSON object without any code blocks, markdown formatting, or additional explanations.
""")
        user_message = HumanMessage(content=f"PRD Document:\n\n{prd_document}")
        
        # Get response from LLM
        llm = get_llm_by_type("basic")
        task_response = llm.invoke([system_message, user_message])
        task_plan_text = task_response.content
        
        print(f"Task plan generated successfully ({len(task_plan_text)} characters)")
        print("\n--- Task Plan Preview ---")
        print(task_plan_text[:500] + "...\n" if len(task_plan_text) > 500 else task_plan_text)
        
        # Try to parse the task plan into JSON
        try:
            # Try to extract JSON from the text, handling markdown and other formats
            json_text = extract_json_from_text(task_plan_text)
            task_plan_json = json.loads(json_text)
            print("\n--- Task Plan JSON Structure ---")
            print(f"Type: {type(task_plan_json)}")
            if isinstance(task_plan_json, list):
                print(f"Number of tasks: {len(task_plan_json)}")
                if len(task_plan_json) > 0:
                    print(f"First task sample keys: {list(task_plan_json[0].keys())}")
            elif isinstance(task_plan_json, dict) and "tasks" in task_plan_json:
                print(f"Number of tasks: {len(task_plan_json['tasks'])}")
                if len(task_plan_json["tasks"]) > 0:
                    print(f"First task sample keys: {list(task_plan_json['tasks'][0].keys())}")
                    
            # Generate a task plan for the next phase
            print("\n=== Step 3: Generate First Task Implementation ===")
            try:
                # Find the first coding task
                first_task = None
                if isinstance(task_plan_json, dict) and "tasks" in task_plan_json:
                    if len(task_plan_json["tasks"]) > 0:
                        first_task = task_plan_json["tasks"][0]
                
                if first_task:
                    first_task_name = first_task['name']
                    # Generate code for the first task
                    system_message = SystemMessage(content=f"""You are an expert Python developer implementing the first task for a simple 2D game.
Generate working Python code that implements this task completely. Provide clear code comments.

The code should be complete, runnable, and follow best practices.
""")
                    task_context = f"""
PRD: {prd_document[:1000]}...

TASK TO IMPLEMENT:
ID: {first_task['id']}
Name: {first_task['name']}
Description: {first_task['description']}
"""
                    user_message = HumanMessage(content=task_context)
                    
                    # Get code implementation
                    code_response = llm.invoke([system_message, user_message])
                    code_implementation = code_response.content
                    
                    print(f"Code implementation generated ({len(code_implementation)} characters)")
                    print("\n--- Code Preview ---")
                    print(code_implementation[:500] + "..." if len(code_implementation) > 500 else code_implementation)
                    
                    # Save the implementation to a file
                    task_filename = first_task['name'].lower().replace(" ", "_") + ".py"
                    with open(task_filename, "w") as f:
                        f.write(code_implementation)
                    print(f"\nImplementation saved to {task_filename}")
                    
                    # After the base setup is done, generate player movement code
                    print("\n=== Step 4: Generate Player Movement Implementation ===")
                    player_code = generate_player_movement_code()
                    if player_code:
                        print(f"Player movement code implementation generated ({len(player_code)} characters)")
                        print("\n--- Player Movement Code Preview ---")
                        print(player_code[:500] + "..." if len(player_code) > 500 else player_code)
                    
            except Exception as e:
                logger.error(f"Error generating code implementation: {e}")
                traceback.print_exc()
                
        except Exception as e:
            print(f"Not valid JSON: {e}")
            traceback.print_exc()
                
    except Exception as e:
        logger.error(f"Error generating task plan: {e}")
        traceback.print_exc()
        return
    
    print("\n=== Workflow completed successfully ===")
    
    # Save output to a file
    output_file = "direct_workflow_output.md"
    with open(output_file, "w") as f:
        f.write("# Direct Workflow Output\n\n")
        f.write("## PRD Document\n\n")
        f.write(prd_document)
        f.write("\n\n## Task Plan\n\n")
        f.write(task_plan_text)
        if code_implementation:
            f.write(f"\n\n## Task Implementation: {first_task_name}\n\n")
            f.write("```python\n")
            f.write(code_implementation)
            f.write("\n```\n")
        if player_code:
            f.write(f"\n\n## Player Movement Implementation\n\n")
            f.write("```python\n")
            f.write(player_code)
            f.write("\n```\n")
    
    print(f"\nOutput saved to {output_file}")

if __name__ == "__main__":
    import sys
    
    # Get user input from command line args if provided
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Build a simple 2D game in Python"
    
    main(user_input) 