"""Tests for the ``inspect tree`` command (plan.md Phase 2, P2-T01..P2-T06)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_INCOMPLETE, EXIT_SUCCESS, main


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "tree", str(source), *extra]


def tree_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def test_tree_json_shape(tmp_path: Path) -> None:
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "gamma.txt").write_text("g")
    code, data = tree_json(tmp_path)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "inspect.tree"
    assert data["complete"] is True
    assert data["errors"] == []
    assert data["result"]["root"] == str(tmp_path)
    names = [entry["name"] for entry in data["result"]["entries"]]
    assert names == ["alpha.txt", "beta", "gamma.txt"]
    assert data["result"]["count"] == 3
    for entry in data["result"]["entries"]:
        assert Path(entry["path"]).is_absolute()
        assert Path(entry["path"]).relative_to(tmp_path) == Path(entry["rel_path"])


def test_tree_max_depth(tmp_path: Path) -> None:
    (tmp_path / "top").mkdir()
    (tmp_path / "top" / "inner").mkdir()
    (tmp_path / "top" / "inner" / "deep.txt").write_text("x")
    code, data = tree_json(tmp_path, "--max-depth", "1")
    assert code == EXIT_SUCCESS
    names = [entry["name"] for entry in data["result"]["entries"]]
    assert names == ["top"]
    assert "inner" not in names


def test_tree_max_entries_truncates(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    code, data = tree_json(tmp_path, "--max-entries", "1")
    assert code == EXIT_INCOMPLETE
    assert data["complete"] is False
    assert len(data["result"]["entries"]) == 1


def test_tree_ignores_default_dirs(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("k")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    code, data = tree_json(tmp_path)
    assert code == EXIT_SUCCESS
    names = [entry["name"] for entry in data["result"]["entries"]]
    assert ".git" not in names
    assert "config" not in names


def test_tree_ignore_pattern(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("k")
    (tmp_path / "secret.py").write_text("x")
    code, data = tree_json(tmp_path, "--ignore-pattern", "*.py")
    names = [entry["name"] for entry in data["result"]["entries"]]
    assert "secret.py" not in names
    assert "keep.txt" in names


def test_tree_dirs_only(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    code, data = tree_json(tmp_path, "--dirs-only")
    names = [entry["name"] for entry in data["result"]["entries"]]
    assert names == ["sub"]


def test_tree_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "beta").mkdir()
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "tree", str(tmp_path)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert output.startswith(f"{tmp_path.name}/")
    assert "alpha.txt" in output
    assert "beta" in output


def test_tree_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "inspect", "tree", "/etc/hostname"])
    assert code == 3


def test_tree_missing_root_reports_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    code, data = tree_json(missing)
    assert code == EXIT_SUCCESS
    assert data["complete"] is True
    assert data["errors"]


def test_tree_symlink_recorded_not_followed(tmp_path: Path) -> None:
    target = tmp_path.parent / f"symlink-target-{tmp_path.name}.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    code, data = tree_json(tmp_path)
    assert code == EXIT_SUCCESS
    links = [e for e in data["result"]["entries"] if e["is_symlink"]]
    assert len(links) == 1
    recorded = links[0]["target"]
    if recorded.startswith("\\\\?\\"):
        recorded = recorded[4:]
    assert recorded == str(target)
    assert not any(e["name"] == target.name for e in data["result"]["entries"])
