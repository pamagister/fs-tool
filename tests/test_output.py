"""Tests for the common JSON response envelope (plan.md sections 4.3 and 8).

Acceptance: envelope matches plan.md section 4.3; stable round-trip JSON.
"""

from __future__ import annotations

import json

from fs_tool.core.errors import EXIT_CODES, ErrorCode
from fs_tool.output.json import (
    ENVELOPE_KEY_ORDER,
    SCHEMA_VERSION,
    Envelope,
    Error,
    Warning,
    failure_result,
    success_result,
)


def test_envelope_defaults() -> None:
    """A fresh envelope matches the plan.md section 4.3 skeleton."""
    envelope = Envelope(success=True, command="inspect.info", result={})
    data = envelope.to_dict()
    assert data == {
        "schema_version": 1,
        "success": True,
        "command": "inspect.info",
        "result": {},
        "errors": [],
        "warnings": [],
        "complete": True,
    }


def test_envelope_key_order_is_stable() -> None:
    """JSON serialization keeps the documented key order."""
    envelope = Envelope(success=True, command="inspect.info", result={})
    text = envelope.to_json()
    assert list(json.loads(text).keys()) == list(ENVELOPE_KEY_ORDER)


def test_failure_envelope() -> None:
    """A failure envelope carries structured errors and complete=false."""
    envelope = failure_result(
        command="write.copy",
        errors=(
            Error(
                code="TARGET_EXISTS",
                message="Destination already exists.",
                path="/home/user/file.txt",
                details={},
            ),
        ),
        complete=False,
    )
    data = envelope.to_dict()
    assert data["success"] is False
    assert data["command"] == "write.copy"
    assert data["result"] is None
    assert data["complete"] is False
    assert data["errors"] == [
        {
            "code": "TARGET_EXISTS",
            "message": "Destination already exists.",
            "path": "/home/user/file.txt",
            "details": {},
        }
    ]
    assert data["warnings"] == []


def test_success_result_helper() -> None:
    """success_result builds a valid success envelope."""
    envelope = success_result(command="inspect.tree", result={"entries": []})
    assert envelope.success is True
    assert envelope.complete is True
    assert envelope.errors == ()
    assert envelope.schema_version == SCHEMA_VERSION


def test_json_round_trip_is_stable() -> None:
    """Envelope -> JSON -> Envelope is a stable round trip."""
    original = Envelope(
        schema_version=SCHEMA_VERSION,
        success=False,
        command="verify.tree",
        result=None,
        errors=(Error(code="MISSING_ENTRY", message="Expected file missing.", path="a.txt"),),
        warnings=(Warning(code="SKIPPED_FILE", message="File unreadable.", path="b.bin"),),
        complete=False,
    )
    restored = Envelope.from_json(original.to_json())
    assert restored == original
    assert restored.to_json() == original.to_json()


def test_from_dict_missing_fields_use_defaults() -> None:
    """Deserialization fills documented defaults for missing fields."""
    envelope = Envelope.from_dict({"command": "inspect.info"})
    assert envelope.schema_version == SCHEMA_VERSION
    assert envelope.success is True
    assert envelope.complete is True
    assert envelope.result is None
    assert envelope.errors == ()
    assert envelope.warnings == ()


def test_error_exit_code_mapping() -> None:
    """Every stable error code maps to exactly one exit code 1..5."""
    seen: set[int] = set()
    for code in ErrorCode:
        exit_code = EXIT_CODES[code]
        assert 1 <= exit_code <= 5
        seen.add(exit_code)
    assert seen == {1, 2, 3, 4, 5}
