# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
This file is maintained for backward compatibility.
It re-exports the Linear service classes from the linear package.
For new code, please import directly from the appropriate module in the linear package.
"""

from .linear import LinearTask, LinearProject, LinearService

__all__ = ["LinearTask", "LinearProject", "LinearService"]

