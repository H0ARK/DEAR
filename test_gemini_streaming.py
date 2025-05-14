import os
import sys
from typing import Any, Dict

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMOutput

# Add project root to path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llms.llm import get_llm_by_type, GEMINI_AVAILABLE

# Create a simple streaming callback handler
class StreamingCallbackHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized: Dict[str, Any], **kwargs: Any) -> None:
        print(f"\n🚀 Starting LLM generation")
        print("-" * 50)
    
    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        # Just print the token without newline to demonstrate streaming
        print(token, end="", flush=True)
    
    def on_llm_end(self, response: LLMOutput, **kwargs: Any) -> None:
        print("\n" + "-" * 50)
        print("✅ LLM generation complete")
        
    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        print(f"\n❌ Error during LLM generation: {error}")

def main():
    # Check if Gemini is available
    if not GEMINI_AVAILABLE:
        print("❌ Google Gemini is not available. Please install langchain-google-genai.")
        return
        
    # Check for API key
    if not os.environ.get("GOOGLE_API_KEY"):
        print("❌ GOOGLE_API_KEY environment variable is not set.")
        return
    
    # Get the LLM instance
    try:
        llm = get_llm_by_type("basic")
        print(f"✅ Successfully initialized LLM: {llm}")
    except Exception as e:
        print(f"❌ Failed to initialize LLM: {e}")
        return

    # Test streaming with a simple prompt
    prompt = "Write a short poem about using LangChain with Google Gemini models"
    print(f"\n📝 Testing streaming with prompt: '{prompt}'")
    
    handler = StreamingCallbackHandler()
    try:
        # Create a message to send to the model
        human_message = HumanMessage(content=prompt)
        
        # Invoke the LLM with streaming enabled - correct way to pass callbacks
        response = llm.invoke([human_message], config={"callbacks": [handler]})
        
        # Print the complete response for verification
        print("\n\n📋 Complete response:")
        print(response.content)
        
        print("\n✅ Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main() 