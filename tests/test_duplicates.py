"""Tests for the ``duplicates`` command (plan.md Phase 3, P3-T06..P3-T10)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_INCOMPLETE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "duplicates", str(source), *extra]


def duplicates_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def _write(path: Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8"))


def _make_dup_tree(tmp_path: Path) -> Path:
    # Two identical files
    _write(tmp_path / "a.txt", "same content")
    _write(tmp_path / "b.txt", "same content")
    # A third identical file in a subdirectory
    sub = tmp_path / "sub"
    sub.mkdir()
    _write(sub / "c.txt", "same content")
    # A unique file
    _write(tmp_path / "unique.txt", "different content")
    # Two more identical files of different size
    _write(tmp_path / "x.txt", "other content")
    _write(tmp_path / "y.txt", "other content")
    # Empty files (excluded by default)
    _write(tmp_path / "empty1.txt", "")
    _write(tmp_path / "empty2.txt", "")
    return tmp_path


def test_duplicates_json_shape(tmp_path: Path) -> None:
    root = _make_dup_tree(tmp_path)
    code, data = duplicates_json(root)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "duplicates"
    assert data["complete"] is True
    assert data["errors"] == []
    result = data["result"]
    assert result["root"] == str(root)
    assert result["duplicate_group_count"] == 2
    assert result["duplicate_file_count"] == 5  # 3 + 2
    groups = result["duplicate_groups"]
    assert len(groups) == 2
    # Larger group first
    assert groups[0]["count"] == 3
    assert groups[1]["count"] == 2
    for group in groups:
        assert "sha256" in group
        assert "size" in group
        assert "count" in group
        assert "files" in group
        assert len(group["files"]) == group["count"]


def test_duplicates_min_size(tmp_path: Path) -> None:
    root = _make_dup_tree(tmp_path)
    # All "same content" files are 12 bytes, "other content" is 14 bytes.
    # min-size=13 should exclude "same content" group (12 bytes each).
    code, data = duplicates_json(root, "--min-size", "13")
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["duplicate_group_count"] == 1
    assert result["duplicate_groups"][0]["count"] == 2


def test_duplicates_include_empty(tmp_path: Path) -> None:
    root = _make_dup_tree(tmp_path)
    # Without --include-empty, empty files excluded: 2 groups.
    code, data = duplicates_json(root)
    assert data["result"]["duplicate_group_count"] == 2
    # With --include-empty, empty files included: 3 groups.
    code, data = duplicates_json(root, "--include-empty")
    assert code == EXIT_SUCCESS
    assert data["result"]["duplicate_group_count"] == 3
    empty_group = [g for g in data["result"]["duplicate_groups"] if g["size"] == 0]
    assert len(empty_group) == 1
    assert empty_group[0]["count"] == 2


def test_duplicates_no_duplicates(tmp_path: Path) -> None:
    _write(tmp_path / "a.txt", "content one")
    _write(tmp_path / "b.txt", "content two")
    code, data = duplicates_json(tmp_path)
    assert code == EXIT_SUCCESS
    assert data["result"]["duplicate_group_count"] == 0
    assert data["result"]["duplicate_file_count"] == 0
    assert data["result"]["duplicate_groups"] == []


def test_duplicates_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "duplicates", "/etc/hostname"])
    assert code == EXIT_ACCESS_DENIED


def test_duplicates_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_dup_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "duplicates", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "duplicate groups:" in output
    assert "count=" in output


def test_duplicates_hash_failure_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_dup_tree(tmp_path)
    monkeypatch.setattr("fs_tool.core.analysis.duplicates.sha256_of_file", lambda path: None)
    code, data = duplicates_json(root)
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert data["result"]["complete"] is False
    assert data["result"]["duplicate_groups"] == []
    assert any("Cannot hash" in error["message"] for error in data["errors"])


def test_duplicates_invalid_min_size(tmp_path: Path) -> None:
    root = _make_dup_tree(tmp_path)
    code, data = duplicates_json(root, "--min-size", "not-a-number")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "Invalid --min-size value" in data["errors"][0]["message"]
