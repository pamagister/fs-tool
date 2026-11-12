"""Tests for declarative multi-step write plans."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from fs_tool.cli import (
    EXIT_FAILURE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)


def run_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(argv)
    return code, json.loads(output.getvalue())


def write_plan(path: Path, operations: list[dict[str, Any]], version: int = 1) -> Path:
    path.write_text(
        json.dumps({"plan_version": version, "operations": operations}), encoding="utf-8"
    )
    return path


def argv(plan_file: Path, root: Path, *extra: str) -> list[str]:
    return [
        "--allow-root",
        str(root),
        "write",
        "apply",
        str(plan_file),
        *extra,
    ]


def test_apply_dry_run_simulates_mkdir_then_move_without_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {"op": "mkdir", "destination": str(tmp_path / "archive")},
            {"op": "move", "source": str(source), "destination": str(tmp_path / "archive")},
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["would_succeed"] is True
    assert result["complete"] is True
    assert [item["status"] for item in result["operations"]] == ["planned", "planned"]
    assert result["operations"][1]["destination"] == str(tmp_path / "archive" / "source.txt")
    assert source.exists()
    assert not (tmp_path / "archive").exists()


def test_apply_executes_mkdir_move_copy_and_rmdir(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("move me", encoding="utf-8")
    copy_source = tmp_path / "copy.txt"
    copy_source.write_text("copy me", encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {"op": "mkdir", "destination": str(tmp_path / "archive" / "nested"), "parents": True},
            {
                "op": "move",
                "source": str(source),
                "destination": str(tmp_path / "archive" / "nested"),
            },
            {
                "op": "copy",
                "source": str(copy_source),
                "destination": str(tmp_path / "archive" / "nested"),
            },
            {"op": "rmdir", "destination": str(empty)},
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--yes"))

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["executed"] is True
    assert result["would_succeed"] is True
    assert result["failed"] == 0
    assert [item["status"] for item in result["operations"]] == [
        "completed",
        "completed",
        "completed",
        "completed",
    ]
    assert (tmp_path / "archive" / "nested" / "source.txt").read_text(encoding="utf-8") == "move me"
    assert (tmp_path / "archive" / "nested" / "copy.txt").read_text(encoding="utf-8") == "copy me"
    assert not empty.exists()


def test_apply_preflight_reports_conflict_without_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("keep", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {
                "op": "move",
                "source": str(source),
                "destination": str(destination),
                "allow_rename": True,
            }
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_FAILURE
    result = data["result"]
    assert result["would_succeed"] is False
    assert result["operations"][0]["status"] == "failed"
    assert result["operations"][0]["error"]["code"] == "TARGET_EXISTS"
    assert source.exists()
    assert destination.read_text(encoding="utf-8") == "keep"


def test_apply_missing_source_fails_preflight(tmp_path: Path) -> None:
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {
                "op": "move",
                "source": str(tmp_path / "missing.txt"),
                "destination": str(tmp_path / "destination.txt"),
            }
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_FAILURE
    assert data["result"]["operations"][0]["error"]["code"] == "INVALID_ARGUMENT"


def test_apply_parents_option_creates_missing_parents(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    destination = tmp_path / "new" / "nested" / "source.txt"
    plan = write_plan(
        tmp_path / "plan.json",
        [{"op": "move", "source": str(source), "destination": str(destination), "parents": True}],
    )

    code, data = run_json(argv(plan, tmp_path, "--yes"))

    assert code == EXIT_SUCCESS
    assert destination.read_text(encoding="utf-8") == "content"
    assert data["result"]["operations"][0]["created_directories"] == [
        str(tmp_path / "new"),
        str(tmp_path / "new" / "nested"),
    ]


def test_apply_rejects_duplicate_actual_destinations(tmp_path: Path) -> None:
    destination = str(tmp_path / "same.txt")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {"op": "mkdir", "destination": destination},
            {"op": "mkdir", "destination": destination},
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_FAILURE
    assert data["result"]["operations"][-1]["status"] == "failed"
    assert "Duplicate destination" in data["result"]["operations"][-1]["error"]["message"]
    assert not Path(destination).exists()


def test_apply_rejects_malformed_plan(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"plan_version": 1, "operations": [{"op": "unknown"}]}), encoding="utf-8"
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_INVALID_ARGS
    assert "unknown op" in data["errors"][0]["message"].lower()


def test_apply_rejects_unknown_operation_field(tmp_path: Path) -> None:
    plan = write_plan(
        tmp_path / "plan.json",
        [{"op": "mkdir", "destination": str(tmp_path / "new"), "typo": True}],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_INVALID_ARGS
    assert "unknown field" in data["errors"][0]["message"].lower()


def test_apply_rejects_unsupported_plan_version(tmp_path: Path) -> None:
    plan = write_plan(tmp_path / "plan.json", [], version=2)

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_INVALID_ARGS
    assert "plan_version" in data["errors"][0]["message"]


def test_apply_stop_marks_remaining_operations_pending(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    later = tmp_path / "later.txt"
    later.write_text("later", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {"op": "move", "source": str(missing), "destination": str(tmp_path / "a.txt")},
            {"op": "move", "source": str(later), "destination": str(tmp_path / "b.txt")},
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--yes"))

    assert code == EXIT_FAILURE
    result = data["result"]
    assert result["complete"] is False
    assert [item["status"] for item in result["operations"]] == ["failed", "pending"]
    assert later.exists()


def test_apply_continue_attempts_later_operations(tmp_path: Path, monkeypatch: Any) -> None:
    import fs_tool.operations.plan as plan_module
    from fs_tool.core.errors import ErrorCode, FsToolError

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {
                "op": "move",
                "source": str(first),
                "destination": str(tmp_path / "a.txt"),
                "allow_rename": True,
            },
            {
                "op": "move",
                "source": str(second),
                "destination": str(tmp_path / "b.txt"),
                "allow_rename": True,
            },
        ],
    )
    original_execute = plan_module._execute_operation

    def fail_first(operation: dict[str, Any], allowed_roots: tuple[Path, ...]) -> dict[str, Any]:
        if str(operation["destination"]).endswith("a.txt"):
            raise FsToolError("simulated runtime failure", code=ErrorCode.OPERATION_FAILED)
        return original_execute(operation, allowed_roots)

    monkeypatch.setattr(plan_module, "_execute_operation", fail_first)

    code, data = run_json(argv(plan, tmp_path, "--yes", "--on-error", "continue"))

    assert code == EXIT_FAILURE
    result = data["result"]
    assert result["complete"] is True
    assert [item["status"] for item in result["operations"]] == ["failed", "completed"]
    assert first.exists()
    assert not second.exists()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "second"


def test_apply_respects_allowed_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {
                "op": "move",
                "source": str(source),
                "destination": str(outside / "source.txt"),
            }
        ],
    )

    code = main(["--allow-root", str(tmp_path), "write", "apply", str(plan), "--dry-run"])
    assert code != EXIT_SUCCESS
    assert source.exists()
    assert not (outside / "source.txt").exists()


def test_apply_plain_output_contains_operation_status(tmp_path: Path, capsys: Any) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {
                "op": "move",
                "source": str(source),
                "destination": str(tmp_path / "moved.txt"),
                "allow_rename": True,
            }
        ],
    )

    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "write",
            "apply",
            str(plan),
            "--dry-run",
        ]
    )

    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "apply: planned" in output
    assert "[planned] move" in output
    assert str(tmp_path / "moved.txt") in output


def test_apply_dry_run_succeeds_when_mkdir_target_already_exists(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    plan = write_plan(
        tmp_path / "plan.json",
        [
            {"op": "mkdir", "destination": str(archive)},
            {"op": "move", "source": str(source), "destination": str(archive)},
        ],
    )

    code, data = run_json(argv(plan, tmp_path, "--dry-run"))

    assert code == EXIT_SUCCESS
    assert data["result"]["would_succeed"] is True
    assert data["result"]["operations"][0]["status"] == "planned"
    assert data["result"]["operations"][1]["destination"] == str(archive / "source.txt")
    assert source.exists()


def test_apply_mkdir_is_idempotent_when_executed_twice(tmp_path: Path) -> None:
    destination = tmp_path / "archive"
    plan = write_plan(
        tmp_path / "plan.json",
        [{"op": "mkdir", "destination": str(destination)}],
    )

    first_code, first_data = run_json(argv(plan, tmp_path, "--yes"))
    second_code, second_data = run_json(argv(plan, tmp_path, "--yes"))

    assert first_code == EXIT_SUCCESS
    assert first_data["result"]["operations"][0]["created"] is True
    assert second_code == EXIT_SUCCESS
    assert second_data["result"]["operations"][0]["created"] is False
    assert destination.is_dir()
