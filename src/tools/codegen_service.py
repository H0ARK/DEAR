# tools/codegen_service.py
import os
import time
import logging
from typing import Dict, Any, Optional

# Attempt to import the codegen library. Handle ImportError if not installed.
try:
    from codegen import Agent as CodegenAPIAgent # Alias to avoid confusion
except ImportError:
    CodegenAPIAgent = None
    logging.warning(
        "The 'codegen' library is not installed. CodegenService will not function. "
        "Please install it (e.g., 'pip install codegen')."
    )

logger = logging.getLogger(__name__)

class CodegenService:
    """
    A wrapper class to interact with the codegen.com service via its SDK.
    Handles task initiation and status polling.
    """
    def __init__(self, org_id: Optional[str] = None, token: Optional[str] = None):
        """
        Initializes the CodegenService.

        Reads credentials from arguments or environment variables (CODEGEN_ORG_ID, CODEGEN_TOKEN).
        Raises ValueError if credentials are not found.
        Raises RuntimeError if the codegen library is not installed.
        """
        if CodegenAPIAgent is None:
            logger.error("Codegen library is required but not installed.")
            raise RuntimeError("The 'codegen' library must be installed to use CodegenService.")

        self.org_id = org_id or os.getenv("CODEGEN_ORG_ID")
        self.token = token or os.getenv("CODEGEN_TOKEN")

        if not self.org_id or not self.token:
            logger.error("Codegen.com ORG_ID or TOKEN not found in environment or arguments.")
            raise ValueError("Codegen.com ORG_ID and TOKEN must be provided via arguments or environment variables (CODEGEN_ORG_ID, CODEGEN_TOKEN).")

        try:
            # TODO: Add optional base_url parameter if needed
            self.client = CodegenAPIAgent(org_id=self.org_id, token=self.token)
            logger.info(f"Codegen.com client initialized for org_id: {self.org_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Codegen.com client: {e}", exc_info=True)
            raise ConnectionError(f"Failed to initialize Codegen.com client: {e}") from e

    def start_task(self, task_description: str) -> Dict[str, Any]:
        """
        Starts a task on Codegen.com using the provided description.

        Args:
            task_description: The detailed prompt for the Codegen.com agent.

        Returns:
            A dictionary containing:
                - status: "success" or "error"
                - message: A status message.
                - codegen_task_id: The ID of the initiated task (if successful).
                - codegen_initial_status: The initial status reported by the SDK (if successful).
                - _sdk_task_object: The raw task object returned by the SDK (if successful).
                This object is needed for polling.
        """
        if not isinstance(task_description, str) or not task_description:
            logger.error("Invalid task_description provided to start_task.")
            return {"status": "error", "message": "Task description cannot be empty."}

        try:
            logger.info(f"Starting Codegen.com task with description: '{task_description[:100]}...'")
            # Assuming self.client.run returns the task object needed for refresh()
            sdk_task_object = self.client.run(prompt=task_description) # Ensure 'prompt' is the correct kwarg

            # Validate the returned object has expected attributes (basic check)
            if not hasattr(sdk_task_object, 'id') or not hasattr(sdk_task_object, 'status') or not hasattr(sdk_task_object, 'refresh'):
                 logger.error("Codegen SDK's run() method did not return the expected task object structure.")
                 return {"status": "error", "message": "Received unexpected response object from Codegen SDK."}

            task_id = getattr(sdk_task_object, 'id')
            initial_status = getattr(sdk_task_object, 'status')
            logger.info(f"Codegen.com task initiated successfully. Task ID: {task_id}, Initial Status: {initial_status}")

            return {
                "status": "success",
                "message": "Codegen.com task initiated.",
                "codegen_task_id": task_id,
                "codegen_initial_status": initial_status,
                "_sdk_task_object": sdk_task_object, # Return the object itself
            }
        except Exception as e:
            logger.error(f"Error starting Codegen.com task: {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to start Codegen.com task: {str(e)}"}

    def check_task_status(self, sdk_task_object: Any) -> Dict[str, Any]:
        """
        Refreshes and checks the status of an ongoing Codegen.com task using its SDK object.

        Args:
            sdk_task_object: The task object previously returned by start_task (or an updated one from a previous check).

        Returns:
            A dictionary containing:
                - status: "success" or "error"
                - message: A status message (especially on error).
                - codegen_task_id: The ID of the task being checked.
                - codegen_task_status: The current status from Codegen.com.
                - codegen_task_result: The result payload if the task is completed or failed.
                - _sdk_task_object: The updated SDK task object after refresh.
        """
        # Validate the input is likely the SDK object we need
        if not hasattr(sdk_task_object, 'id') or not hasattr(sdk_task_object, 'refresh') or not hasattr(sdk_task_object, 'status'):
            logger.error(f"Invalid object provided to check_task_status. Expected Codegen SDK task object, got: {type(sdk_task_object)}")
            return {
                "status": "error",
                "message": "Invalid task object provided for status check.",
                "codegen_task_id": None,
                "codegen_task_status": "polling_error_bad_object",
                "_sdk_task_object": sdk_task_object # Return original object on error
            }

        task_id = getattr(sdk_task_object, 'id')

        try:
            logger.debug(f"Polling Codegen.com task status for ID: {task_id}")
            # The core SDK call to update the status
            sdk_task_object.refresh()

            current_status = getattr(sdk_task_object, 'status')
            result_payload = None

            # Check for terminal states
            if current_status == "completed":
                # Access the result if completed. Ensure 'result' is the correct attribute.
                result_payload = getattr(sdk_task_object, 'result', None)
                logger.info(f"Codegen.com task {task_id} completed. Result snippet: '{str(result_payload)[:100]}...'")
            elif current_status == "failed":
                # Access the result/error details if failed.
                result_payload = getattr(sdk_task_object, 'result', "No failure details provided by SDK.")
                logger.error(f"Codegen.com task {task_id} failed. Result/Error: '{str(result_payload)[:100]}...'")
            elif current_status not in ["pending", "running", "processing", "in_progress"]: # Assuming non-terminal statuses
                # Log unexpected statuses
                 logger.warning(f"Codegen.com task {task_id} has unexpected status: {current_status}")

            return {
                "status": "success",
                "codegen_task_id": task_id,
                "codegen_task_status": current_status,
                "codegen_task_result": result_payload,
                "_sdk_task_object": sdk_task_object, # Return the refreshed object
            }
        except Exception as e:
            logger.error(f"Error checking Codegen.com task status for ID {task_id}: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to check Codegen.com task status: {str(e)}",
                "codegen_task_id": task_id,
                "codegen_task_status": "polling_error_exception",
                "_sdk_task_object": sdk_task_object # Return original object on error
            }

# Example Usage (can be run standalone for basic testing if needed)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Ensure CODEGEN_ORG_ID and CODEGEN_TOKEN are set as environment variables for this test
    if not os.getenv("CODEGEN_ORG_ID") or not os.getenv("CODEGEN_TOKEN"):
        print("Please set CODEGEN_ORG_ID and CODEGEN_TOKEN environment variables to run this example.")
    else:
        try:
            print("Initializing CodegenService...")
            service = CodegenService()

            print("Starting a test task...")
            # Replace with a real task description for actual testing
            test_task_description = "Create a simple Python function that adds two numbers."
            start_result = service.start_task(test_task_description)
            print(f"Start Task Result: {start_result}")

            if start_result["status"] == "success":
                task_object = start_result["_sdk_task_object"]
                task_id = start_result["codegen_task_id"]
                print(f"Polling status for task {task_id} (will poll up to 5 times)...")

                for i in range(5): # Poll a few times for demonstration
                    print(f"Poll attempt {i+1}...")
                    time.sleep(5) # Wait before polling
                    status_result = service.check_task_status(task_object)
                    print(f"Status Check Result: {status_result}")

                    if status_result["status"] == "success":
                        task_object = status_result["_sdk_task_object"] # Update object for next poll
                        task_status = status_result["codegen_task_status"]
                        if task_status in ["completed", "failed"]:
                            print(f"Task reached terminal state: {task_status}")
                            break
                    else:
                        print("Error during polling, stopping.")
                        break
                else:
                    print("Polling finished (max attempts reached or non-terminal state).")

        except (ValueError, RuntimeError, ConnectionError) as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}") 