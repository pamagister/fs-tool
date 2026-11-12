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


def test_write_copy_falls_back_when_fd_timestamps_are_unavailable(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fs_tool.operations import copy as copy_module

    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("copy", encoding="utf-8")
    set_timestamp = copy_module.os.utime
    fallback_used = False

    def unsupported_fd_utime(path: Any, **kwargs: Any) -> None:
        nonlocal fallback_used
        if isinstance(path, int):
            raise NotImplementedError
        fallback_used = True
        assert "follow_symlinks" not in kwargs
        set_timestamp(path, **kwargs)

    monkeypatch.setattr(copy_module.os, "utime", unsupported_fd_utime)
    code, _ = run_json(
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
    assert fallback_used
    assert destination.read_text(encoding="utf-8") == "copy"


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


def test_write_move_file_preserves_contents_and_removes_source(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "moved" / "source.txt"
    destination.parent.mkdir()
    source.write_text("move me", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "move me"
    assert data["command"] == "write.move"
    assert data["result"]["executed"] is True
    assert data["result"]["affected"] == [str(destination)]


def test_write_move_dry_run_does_not_change_filesystem(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "moved" / "source.txt"
    destination.parent.mkdir()
    source.write_text("keep", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["dry_run"] is True
    assert data["result"]["executed"] is False
    assert source.read_text(encoding="utf-8") == "keep"
    assert not destination.exists()


def test_write_move_never_overwrites_existing_destination(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source" / "source.txt"
    destination = tmp_path / "destination" / "source.txt"
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    destination.write_text("destination", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_CONFLICT
    assert data["errors"][0]["code"] == "TARGET_EXISTS"
    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "destination"


def test_write_move_does_not_replace_destination_created_after_preflight(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fs_tool.operations import move as move_module

    source = tmp_path / "source" / "source.txt"
    destination = tmp_path / "destination" / "source.txt"
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    atomic_rename = move_module._rename_no_replace

    def create_conflicting_destination(source_path: Path, destination_path: Path) -> None:
        destination_path.write_text("raced", encoding="utf-8")
        atomic_rename(source_path, destination_path)

    monkeypatch.setattr(move_module, "_rename_no_replace", create_conflicting_destination)
    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_CONFLICT
    assert data["errors"][0]["code"] == "TARGET_EXISTS"
    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "raced"


def test_write_move_requires_explicit_rename_authorization(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "old.txt"
    destination = tmp_path / "new.txt"
    source.write_text("content", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert source.exists()
    assert not destination.exists()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--allow-rename",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "content"


def test_write_move_directory_tree(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination" / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "file.txt").write_text("content", encoding="utf-8")
    destination.parent.mkdir()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert (destination / "nested" / "file.txt").read_text(encoding="utf-8") == "content"
    assert data["result"]["verified"] is True


def test_write_move_symlink_does_not_move_its_target(cli: Any, tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    source = tmp_path / "link.txt"
    destination = tmp_path / "moved-link.txt"
    target.write_text("target", encoding="utf-8")
    try:
        source.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--allow-rename",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.is_symlink()
    assert destination.is_symlink()
    assert target.read_text(encoding="utf-8") == "target"
    assert data["result"]["verified"] is True


def test_write_move_rejects_symlink_escape(cli: Any, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-target"
    outside.write_text("outside", encoding="utf-8")
    source = tmp_path / "link.txt"
    destination = tmp_path / "moved" / "link.txt"
    destination.parent.mkdir()
    try:
        source.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    code = cli(
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ]
    )

    assert code == EXIT_ACCESS_DENIED
    assert source.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.skipif(os.name == "nt", reason="FIFO special files are POSIX-only")
def test_write_move_rejects_special_files(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "source" / "pipe"
    destination = tmp_path / "destination" / "pipe"
    source.parent.mkdir()
    destination.parent.mkdir()
    os.mkfifo(source)

    code = cli(
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ]
    )

    assert code != EXIT_SUCCESS
    assert source.exists()
    assert not destination.exists()


def test_write_move_refuses_filesystem_root(cli: Any, tmp_path: Path) -> None:
    filesystem_root = Path(tmp_path.anchor)
    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(filesystem_root),
            "write",
            "move",
            str(filesystem_root),
            str(tmp_path / "root-moved"),
            "--dry-run",
        ],
    )

    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "root" in data["errors"][0]["message"].lower()


def test_write_move_into_existing_directory_appends_basename(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    destination = tmp_path / "archive"
    destination.mkdir()
    source.write_text("report", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert (destination / "report.txt").read_text(encoding="utf-8") == "report"
    assert data["result"]["destination"] == str(destination / "report.txt")


def test_write_copy_tree_into_existing_directory_appends_basename(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "site"
    destination = tmp_path / "backups"
    (source / "assets").mkdir(parents=True)
    (source / "index.html").write_text("index", encoding="utf-8")
    (source / "assets" / "logo.txt").write_text("logo", encoding="utf-8")
    destination.mkdir()

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
    assert (destination / "site" / "index.html").read_text(encoding="utf-8") == "index"
    assert (destination / "site" / "assets" / "logo.txt").read_text(encoding="utf-8") == "logo"
    assert data["result"]["destination"] == str(destination / "site")


def test_write_copy_into_existing_directory_reports_conflict(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    destination = tmp_path / "archive"
    destination.mkdir()
    source.write_text("new", encoding="utf-8")
    (destination / "report.txt").write_text("keep", encoding="utf-8")

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
    assert (destination / "report.txt").read_text(encoding="utf-8") == "keep"


def test_write_move_parents_dry_run_does_not_create_directories(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    destination = tmp_path / "new" / "nested" / "report.txt"
    source.write_text("report", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--parents",
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["dry_run"] is True
    assert data["result"]["created_directories"] == [
        str(tmp_path / "new"),
        str(tmp_path / "new" / "nested"),
    ]
    assert str(destination) in data["result"]["affected"]
    assert source.exists()
    assert not destination.parent.exists()


def test_write_move_parents_creates_directories(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    destination = tmp_path / "new" / "nested" / "report.txt"
    source.write_text("report", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "move",
            str(source),
            str(destination),
            "--parents",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "report"
    assert data["result"]["created_directories"] == [
        str(tmp_path / "new"),
        str(tmp_path / "new" / "nested"),
    ]


def test_write_copy_parents_creates_directories(cli: Any, tmp_path: Path) -> None:
    source = tmp_path / "site"
    destination = tmp_path / "new" / "backups" / "site"
    source.mkdir()
    (source / "index.html").write_text("index", encoding="utf-8")

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--parents",
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["created_directories"] == [
        str(tmp_path / "new"),
        str(tmp_path / "new" / "backups"),
    ]
    assert not destination.parent.exists()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "copy",
            str(source),
            str(destination),
            "--parents",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert (destination / "index.html").read_text(encoding="utf-8") == "index"


def test_write_rmdir_dry_run_does_not_remove_directory(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "empty"
    destination.mkdir()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "rmdir",
            str(destination),
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["dry_run"] is True
    assert data["result"]["affected"] == [str(destination)]
    assert destination.is_dir()


def test_write_rmdir_removes_empty_directory(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "empty"
    destination.mkdir()

    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "rmdir", str(destination), "--yes"],
    )

    assert code == EXIT_SUCCESS
    assert not destination.exists()
    assert data["result"]["removed"] == [str(destination)]


def test_write_rmdir_refuses_non_empty_directory(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "full"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")

    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "rmdir", str(destination), "--yes"],
    )

    assert code != EXIT_SUCCESS
    assert destination.is_dir()
    assert (destination / "keep.txt").exists()


def test_write_rmdir_refuses_symlink_and_non_directory(cli: Any, tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    file_path = tmp_path / "file.txt"
    file_path.write_text("file", encoding="utf-8")

    for destination in (link, file_path):
        code, data = run_json(
            cli,
            ["--allow-root", str(tmp_path), "write", "rmdir", str(destination), "--yes"],
        )
        assert code != EXIT_SUCCESS
        assert destination.exists() or destination.is_symlink()

    assert target.is_dir()
    assert file_path.read_text(encoding="utf-8") == "file"


def test_write_rmdir_parents_removes_empty_chain_only(cli: Any, tmp_path: Path) -> None:
    target = tmp_path / "one" / "two" / "three"
    target.mkdir(parents=True)

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "rmdir",
            str(target),
            "--parents",
            "--dry-run",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["result"]["affected"] == [
        str(target),
        str(target.parent),
        str(target.parent.parent),
    ]
    assert target.is_dir()

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(tmp_path),
            "write",
            "rmdir",
            str(target),
            "--parents",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not target.exists()
    assert not target.parent.exists()
    assert not target.parent.parent.exists()
    assert tmp_path.is_dir()


def test_write_rmdir_missing_directory_is_invalid(cli: Any, tmp_path: Path) -> None:
    destination = tmp_path / "missing"
    code, data = run_json(
        cli,
        ["--allow-root", str(tmp_path), "write", "rmdir", str(destination), "--yes"],
    )
    assert code == EXIT_INVALID_ARGS
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_write_plain_report_includes_source_and_affected_paths(
    cli: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "moved.txt"
    source.write_text("move", encoding="utf-8")

    code = cli(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "write",
            "move",
            str(source),
            str(destination),
            "--allow-rename",
            "--yes",
        ]
    )

    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert f"source: {source}" in output
    assert f"destination: {destination}" in output
    assert f"  {destination}" in output
