"""Tests for the ``compare trees`` command (plan.md Phase 3, P3-T11..P3-T18)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_ACCESS_DENIED, EXIT_SUCCESS, main


def argv_for(source: Path, destination: Path, *extra: str) -> list[str]:
    return [
        "--allow-root",
        str(source.parent),
        "compare",
        "trees",
        str(source),
        str(destination),
        *extra,
    ]


def compare_json(source: Path, destination: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, destination, *extra))
    return code, json.loads(buffer.getvalue())


def _write(path: Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8"))


def _make_compare_trees(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()

    # Identical file
    _write(source / "same.txt", "identical content")
    _write(destination / "same.txt", "identical content")

    # Missing in destination
    _write(source / "only_source.txt", "only in source")

    # Changed file
    _write(source / "changed.txt", "source version")
    _write(destination / "changed.txt", "dest version")

    # Unexpected in destination
    _write(destination / "only_dest.txt", "only in dest")

    # Type conflict: file in source, directory in destination
    _write(source / "conflict.txt", "file")
    (destination / "conflict.txt").mkdir()

    # Subdirectory with identical file
    sub_src = source / "sub"
    sub_src.mkdir()
    sub_dst = destination / "sub"
    sub_dst.mkdir()
    _write(sub_src / "nested.txt", "nested content")
    _write(sub_dst / "nested.txt", "nested content")

    return source, destination


def test_compare_json_shape(tmp_path: Path) -> None:
    source, destination = _make_compare_trees(tmp_path)
    code, data = compare_json(source, destination)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "compare.trees"
    assert data["complete"] is True
    assert data["errors"] == []
    result = data["result"]
    assert result["source"] == str(source)
    assert result["destination"] == str(destination)
    assert "same.txt" in result["identical"]
    assert "only_source.txt" in result["missing"]
    assert "changed.txt" in result["changed"]
    assert "only_dest.txt" in result["unexpected"]
    assert "conflict.txt" in result["type_conflicts"]
    assert result["complete"] is True


def test_compare_identical_trees(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "hello")
    _write(destination / "a.txt", "hello")
    code, data = compare_json(source, destination)
    assert code == EXIT_SUCCESS
    assert data["result"]["identical"] == ["a.txt"]
    assert data["result"]["missing"] == []
    assert data["result"]["changed"] == []
    assert data["result"]["unexpected"] == []


def test_compare_outside_allowed_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "compare",
            "trees",
            str(source),
            "/etc/hostname",
        ]
    )
    assert code == EXIT_ACCESS_DENIED


def test_compare_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, destination = _make_compare_trees(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "compare",
            "trees",
            str(source),
            str(destination),
        ]
    )
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "identical" in output
    assert "missing" in output
    assert "changed" in output
    assert "unexpected" in output
    assert "type_conflicts" in output
    assert "complete:" in output


def test_compare_subdirectory(tmp_path: Path) -> None:
    source, destination = _make_compare_trees(tmp_path)
    code, data = compare_json(source, destination)
    assert code == EXIT_SUCCESS
    nested_path = str(Path("sub") / "nested.txt")
    assert nested_path in data["result"]["identical"]
