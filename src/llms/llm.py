# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from pathlib import Path
import os
from typing import Any, Dict, Union

# Try to import Google Gemini with fallback
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    # Create a stub class if import fails
    class ChatGoogleGenerativeAI:
        def __init__(self, *args, **kwargs):
            raise ImportError("Google Gemini is not properly installed. Please install langchain-google-genai")

# Also try to import OpenAI as a fallback
try:
    from langchain_openai import ChatOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    # Create a stub class if import fails
    class ChatOpenAI:
        def __init__(self, *args, **kwargs):
            raise ImportError("OpenAI is not properly installed.")

from src.config import load_yaml_config
from src.config.agents import LLMType

# Cache for LLM instances
_llm_cache = {}


def _create_llm_use_conf(llm_type: LLMType, conf: Dict[str, Any]) -> Any:
    llm_type_map = {
        "reasoning": conf.get("REASONING_MODEL"),
        "basic": conf.get("BASIC_MODEL"),
        "vision": conf.get("VISION_MODEL"),
    }
    llm_conf = llm_type_map.get(llm_type)
    if not llm_conf:
        raise ValueError(f"Unknown LLM type: {llm_type}")
    if not isinstance(llm_conf, dict):
        raise ValueError(f"Invalid LLM Conf: {llm_type}")

    # Check if model name indicates Gemini
    model_name = llm_conf.get("model", "")
    if model_name.startswith("gemini") and GEMINI_AVAILABLE:
        # Use Gemini
        print(f"Using Google Gemini model: {model_name}")

        # Make a copy to avoid modifying the original config
        gemini_params = llm_conf.copy()

        # Set Google API key from environment if not provided
        if "api_key" not in gemini_params and os.environ.get("GOOGLE_API_KEY"):
            gemini_params["google_api_key"] = os.environ.get("GOOGLE_API_KEY")

        return ChatGoogleGenerativeAI(**gemini_params)
    elif OPENAI_AVAILABLE:
        # Fallback to OpenAI
        print(f"Using OpenAI model: {model_name}")
        return ChatOpenAI(**llm_conf)
    else:
        raise ImportError("Neither Google Gemini nor OpenAI is properly installed.")


def get_llm_by_type(
    llm_type: LLMType,
) -> Any:
    """
    Get LLM instance by type. Returns cached instance if available.
    Could be either ChatGoogleGenerativeAI or ChatOpenAI depending on configuration.
    """
    if llm_type in _llm_cache:
        return _llm_cache[llm_type]

    conf = load_yaml_config(
        str((Path(__file__).parent.parent.parent / "conf.yaml").resolve())
    )
    llm = _create_llm_use_conf(llm_type, conf)
    _llm_cache[llm_type] = llm
    return llm


# Initialize LLMs for different purposes - now these will be cached
try:
    basic_llm = get_llm_by_type("basic")
    print("Successfully initialized LLM")
except ImportError as e:
    # Create a dummy LLM for testing
    basic_llm = None
    print(f"Warning: {str(e)} Using dummy LLM.")
except Exception as e:
    # Handle other exceptions
    basic_llm = None
    print(f"Warning: Error initializing LLM: {str(e)}. Using dummy LLM.")

# In the future, we will use reasoning_llm and vl_llm for different purposes
# reasoning_llm = get_llm_by_type("reasoning")
# vl_llm = get_llm_by_type("vision")


if __name__ == "__main__":
    if basic_llm:
        print(basic_llm.invoke("Hello"))
    else:
        print("LLM not available")
