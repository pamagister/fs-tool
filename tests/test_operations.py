"""Tests for safe filesystem write operations (plan.md Phase 4)."""

from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_CONFLICT,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
)


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


def test_write_copy_file_dry_run_does_not_create_destination(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("copy me", encoding="utf-8")
    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["command"] == "write.copy"
    assert data["result"]["dry_run"] is True
    assert data["result"]["verified"] is None
    assert not destination.exists()


def test_write_copy_file_verifies_content_and_preserves_metadata(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_bytes(b"copy content\n")
    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert destination.read_bytes() == source.read_bytes()
    assert data["result"]["verified"] is True
    assert data["result"]["sha256"] == expected_hash
    assert data["result"]["executed"] is True
    assert not list(tmp_path.glob(".fs-tool-copy-*"))


def test_write_copy_never_overwrites_existing_destination(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("new", encoding="utf-8")
    destination.write_text("keep", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_CONFLICT
    assert data["errors"][0]["code"] == "TARGET_EXISTS"
    assert destination.read_text(encoding="utf-8") == "keep"


def test_write_copy_recursively_copies_directory_tree(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    (source / "nested").mkdir(parents=True)
    (source / "first.txt").write_text("first", encoding="utf-8")
    (source / "nested" / "second.txt").write_text("second", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert (destination / "first.txt").read_text(encoding="utf-8") == "first"
    assert (destination / "nested" / "second.txt").read_text(encoding="utf-8") == "second"
    assert data["result"]["verified"] is True
    assert set(data["result"]["affected"]) == {
        str(destination),
        str(destination / "first.txt"),
        str(destination / "nested"),
        str(destination / "nested" / "second.txt"),
    }


def test_write_copy_rejects_destination_inside_source(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "existing.txt").write_text("content", encoding="utf-8")
    destination = source / "nested-copy"

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert not destination.exists()


def test_write_copy_symlink_error_preflights_before_writing(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "link").symlink_to("missing-target")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert not destination.exists()


def test_write_copy_symlink_copy_and_skip_policies(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.txt").write_text("target", encoding="utf-8")
    link = source / "link.txt"
    try:
        link.symlink_to("target.txt")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    copied = tmp_path / "copied"
    copied_code, copied_data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(copied),
            "--symlinks",
            "copy",
            "--yes",
        ],
    )
    assert copied_code == EXIT_SUCCESS
    assert (copied / "link.txt").is_symlink()
    assert os.readlink(copied / "link.txt") == "target.txt"
    assert copied_data["result"]["verified"] is True

    skipped = tmp_path / "skipped"
    skipped_code, skipped_data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(skipped),
            "--symlinks",
            "skip",
            "--yes",
        ],
    )
    assert skipped_code == EXIT_SUCCESS
    assert not (skipped / "link.txt").exists()
    assert skipped_data["result"]["skipped"] == [str(Path("link.txt"))]


@pytest.mark.skipif(os.name == "nt", reason="FIFO special files are POSIX-only")
def test_write_copy_rejects_special_files_during_preflight(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    os.mkfifo(source / "pipe")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code != EXIT_SUCCESS
    assert data["success"] is False
    assert not destination.exists()


def test_write_copy_reports_partial_failures(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fs_tool.core.errors import ErrorCode, FsToolError
    from fs_tool.operations import copy as copy_module

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "a.txt").write_text("first", encoding="utf-8")
    (source / "b.txt").write_text("second", encoding="utf-8")
    copy_regular_file = copy_module._copy_regular_file

    def fail_second_file(source_path: Path, destination_path: Path) -> str:
        if source_path.name == "b.txt":
            raise FsToolError("simulated write failure", code=ErrorCode.OPERATION_FAILED)
        return copy_regular_file(source_path, destination_path)

    monkeypatch.setattr(copy_module, "_copy_regular_file", fail_second_file)
    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code != EXIT_SUCCESS
    assert data["success"] is False
    assert data["complete"] is False
    assert data["errors"][0]["details"]["complete"] is False
    assert data["errors"][0]["details"]["affected"] == [
        str(destination),
        str(destination / "a.txt"),
    ]
    assert (destination / "a.txt").read_text(encoding="utf-8") == "first"
