"""Centralized error handling for fs-tool.

Stable error codes mapped to process exit codes (plan.md section 4.3).
All application errors inherit from :class:`FsToolError` and carry an
error code, a human-readable message, and optional context (path,
details). Unexpected bugs are not swallowed silently: they propagate
to the CLI boundary, which reports them as a generic failure.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Stable machine-readable error codes.

    The numeric process exit code is derived from the error code via
    :data:`EXIT_CODES`.
    """

    # 1 - Operation failed or verification found discrepancies.
    OPERATION_FAILED = "OPERATION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"

    # 2 - Invalid arguments or incomplete analysis.
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INCOMPLETE_ANALYSIS = "INCOMPLETE_ANALYSIS"

    # 3 - Access denied or safety restriction.
    ACCESS_DENIED = "ACCESS_DENIED"
    ROOT_NOT_ALLOWED = "ROOT_NOT_ALLOWED"

    # 4 - Operation conflict.
    TARGET_EXISTS = "TARGET_EXISTS"
    TYPE_CONFLICT = "TYPE_CONFLICT"

    # 5 - Incomplete scan or verification (not fully verifiable).
    INCOMPLETE_SCAN = "INCOMPLETE_SCAN"
    INCOMPLETE_VERIFICATION = "INCOMPLETE_VERIFICATION"

    # Capability and setup results (plan.md decisions D6 and D8).
    # 2 - Invalid arguments or incomplete analysis.
    CAPABILITY_NOT_SUPPORTED = "CAPABILITY_NOT_SUPPORTED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    # 1 - Operation failed.
    CAPABILITY_FAILED = "CAPABILITY_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CORRUPT = "RESOURCE_CORRUPT"
    SETUP_FAILED = "SETUP_FAILED"


EXIT_CODES: dict[ErrorCode, int] = {
    ErrorCode.OPERATION_FAILED: 1,
    ErrorCode.VERIFICATION_FAILED: 1,
    ErrorCode.INVALID_ARGUMENT: 2,
    ErrorCode.INCOMPLETE_ANALYSIS: 2,
    ErrorCode.ACCESS_DENIED: 3,
    ErrorCode.ROOT_NOT_ALLOWED: 3,
    ErrorCode.TARGET_EXISTS: 4,
    ErrorCode.TYPE_CONFLICT: 4,
    ErrorCode.INCOMPLETE_SCAN: 5,
    ErrorCode.INCOMPLETE_VERIFICATION: 5,
    ErrorCode.CAPABILITY_NOT_SUPPORTED: 2,
    ErrorCode.CAPABILITY_UNAVAILABLE: 2,
    ErrorCode.CAPABILITY_FAILED: 1,
    ErrorCode.RESOURCE_NOT_FOUND: 1,
    ErrorCode.RESOURCE_CORRUPT: 1,
    ErrorCode.SETUP_FAILED: 1,
}


class FsToolError(Exception):
    """Base class for all fs-tool errors.

    Attributes:
        code: Stable error code.
        message: Human-readable, actionable error message.
        path: Filesystem path related to the error, if any.
        details: Additional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.OPERATION_FAILED,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.details = details or {}

    @property
    def exit_code(self) -> int:
        """Process exit code for this error code."""
        return EXIT_CODES[self.code]

    def __str__(self) -> str:
        return self.message
