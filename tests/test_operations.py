"""Tests for safe filesystem write operations (plan.md Phase 4)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from fs_tool.cli import EXIT_ACCESS_DENIED, EXIT_CONFLICT, EXIT_INVALID_ARGS, EXIT_SUCCESS


def run_json(cli: Any, argv: list[str]) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = cli(argv)
    return code, json.loads(output.getvalue())


def test_write_mkdir_dry_run_does_not_create_directory(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "new"
    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "mkdir", str(destination), "--dry-run"],
    )

    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "write.mkdir"
    assert data["result"]["dry_run"] is True
    assert data["result"]["executed"] is False
    assert destination in [Path(path) for path in data["result"]["affected"]]
    assert not destination.exists()


def test_write_mkdir_requires_exactly_one_authorization(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "new"
    for options in ([], ["--dry-run", "--yes"]):
        code, data = run_json(
            cli,
            ["--allow-root", str(tmp_path), "write", "mkdir", str(destination), *options],
        )
        assert code == EXIT_INVALID_ARGS
        assert data["success"] is False
        assert data["errors"][0]["code"] == "INVALID_ARGUMENT"
        assert not destination.exists()


def test_write_mkdir_creates_missing_parents_with_yes(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "parent" / "child"
    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "mkdir",
            str(destination),
            "--parents",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["executed"] is True
    assert data["result"]["created"] is True
    assert destination.is_dir()
    assert (tmp_path / "parent").is_dir()


def test_write_mkdir_without_parents_rejects_missing_parent(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "parent" / "child"
    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "mkdir", str(destination), "--yes"],
    )

    assert code != EXIT_SUCCESS
    assert data["success"] is False
    assert not destination.exists()


def test_write_mkdir_existing_directory_is_idempotent(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "mkdir", str(destination), "--yes"],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["created"] is False


def test_write_mkdir_file_conflict_is_reported(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.write_text("keep", encoding="utf-8")
    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "mkdir", str(destination), "--yes"],
    )

    assert code == EXIT_CONFLICT
    assert data["success"] is False
    assert data["errors"][0]["code"] == "TYPE_CONFLICT"
    assert destination.read_text(encoding="utf-8") == "keep"


def test_write_mkdir_rejects_destination_outside_allowed_roots(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path.parent / f"{tmp_path.name}-outside"
    code = cli(
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "mkdir",
            str(destination),
            "--yes",
        ]
    )

    assert code == EXIT_ACCESS_DENIED
    assert not destination.exists()
