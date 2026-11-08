"""Serialization helpers for capability results.

The core layer returns :class:`fs_tool.core.capabilities.models.CapabilityResult`
objects without formatting them. This module defines the single JSON shape
used for both metadata status information in ``inspect info`` and analysis
results in ``inspect analyze``.
"""

from __future__ import annotations

from typing import Any

from fs_tool.core.capabilities.models import CapabilityResult


def capability_result_to_dict(result: CapabilityResult) -> dict[str, Any]:
    """Serialize a capability result with a stable key order and shape."""
    return {
        "capability": result.capability.value,
        "status": result.status.value,
        "message": result.message,
        "help": result.help,
        "error_code": result.error_code,
        "data": result.data,
    }
