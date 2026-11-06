"""Shared fixtures and helpers for the fs-tool test suite."""

from __future__ import annotations

from typing import Any

import pytest

from fs_tool.cli import EXIT_ACCESS_DENIED, EXIT_CONFLICT, EXIT_INCOMPLETE, main


@pytest.fixture
def cli() -> Any:
    """The :func:`fs_tool.cli.main` entry point, invokable with argv."""
    return main


@pytest.fixture
def exit_codes() -> dict[str, int]:
    """Documented process exit codes (plan.md section 4.3)."""
    return {
        "success": 0,
        "failure": 1,
        "invalid_args": 2,
        "access_denied": EXIT_ACCESS_DENIED,
        "conflict": EXIT_CONFLICT,
        "incomplete": EXIT_INCOMPLETE,
    }
