# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import json
import json_repair
from typing import Optional

logger = logging.getLogger(__name__)


def repair_json_output(content: str | None) -> str:
    """
    Repair and normalize JSON output. If the content is not valid JSON, return an empty string.

    Args:
        content (str | None): String content that may contain JSON

    Returns:
        str: Repaired JSON string, or an empty string if not JSON
    """
    if not content or not isinstance(content, str):
        logger.warning(f"Invalid content type: {type(content)}")
        return ""

    content = content.strip()

    # Extract JSON from code blocks
    if "```" in content:
        # Find all code blocks
        blocks = content.split("```")
        # Look for json blocks
        for i in range(1, len(blocks), 2):
            if i < len(blocks):
                block = blocks[i]
                if block.startswith("json") or block.startswith("ts"):
                    # Extract the content after "json" or "ts"
                    if block.startswith("json"):
                        content = block[4:].strip()
                    else:
                        content = block[2:].strip()
                    break

    # Try to repair and parse JSON
    if content.startswith(("{", "[")):
        try:
            repaired_content = json_repair.loads(content)
            return json.dumps(repaired_content, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"JSON repair failed: {e}")

            # Try a more aggressive approach
            try:
                # Remove any non-JSON content before the first { or [
                first_brace = content.find("{")
                first_bracket = content.find("[")

                if first_brace >= 0 and (first_bracket < 0 or first_brace < first_bracket):
                    content = content[first_brace:]
                elif first_bracket >= 0:
                    content = content[first_bracket:]

                # Remove any non-JSON content after the last } or ]
                last_brace = content.rfind("}")
                last_bracket = content.rfind("]")

                if last_brace >= 0 and (last_bracket < 0 or last_brace > last_bracket):
                    content = content[:last_brace+1]
                elif last_bracket >= 0:
                    content = content[:last_bracket+1]

                # Try again with the cleaned content
                repaired_content = json_repair.loads(content)
                return json.dumps(repaired_content, ensure_ascii=False)
            except Exception as e2:
                logger.warning(f"Aggressive JSON repair also failed: {e2}")
                pass

    return content  # Return the original content if it's not valid JSON
