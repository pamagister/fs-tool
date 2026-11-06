"""Tests for the ``inspect inventory`` command (plan.md Phase 2, P2-T15..P2-T20)."""

from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_ACCESS_DENIED, EXIT_INCOMPLETE, EXIT_SUCCESS, main


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "inventory", str(source), *extra]


def inventory_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def _make_tree(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "alpha.txt").write_text("alpha")
    (base / "beta.txt").write_text("beta")
    sub = base / "sub"
    sub.mkdir()
    (sub / "gamma.txt").write_text("gamma")
    (sub / "delta.log").write_text("delta")
    return base


def test_inventory_json_shape(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "inspect.inventory"
    assert data["complete"] is True
    assert data["errors"] == []
    result = data["result"]
    assert result["root"] == str(root)
    assert result["count"] == 5
    assert result["complete"] is True
    assert "generated_at" in result
    assert "entries" in result
    names = [e["name"] for e in result["entries"]]
    assert "alpha.txt" in names
    assert "beta.txt" in names
    assert "sub" in names
    assert "gamma.txt" in names
    assert "delta.log" in names


def test_inventory_entries_use_relative_paths_only(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root)
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        assert entry["rel_path"] is not None
        assert "path" not in entry
        assert not Path(entry["rel_path"]).is_absolute()


def test_inventory_with_hash(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--hash")
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        if entry["type"] == "file":
            expected = hashlib.sha256((root / entry["rel_path"]).read_bytes()).hexdigest()
            assert entry["sha256"] == expected
        else:
            assert entry["sha256"] is None


def test_inventory_tree_hash(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--tree-hash")
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert "tree_hash" in result
    assert result["tree_hash"] is not None
    assert isinstance(result["tree_hash"], str)
    assert len(result["tree_hash"]) == 64  # SHA-256 hex digest


def test_inventory_tree_hash_deterministic(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, data1 = inventory_json(root, "--tree-hash")
    _, data2 = inventory_json(root, "--tree-hash")
    assert data1["result"]["tree_hash"] == data2["result"]["tree_hash"]


def test_inventory_tree_hash_excludes_path(tmp_path: Path) -> None:
    # The tree hash must not depend on absolute paths; copying the tree
    # elsewhere must produce the same hash. Timestamps are normalized to
    # avoid time-dependent differences.
    root1 = _make_tree(tmp_path / "tree1")
    root2 = _make_tree(tmp_path / "tree2")
    for root in (root1, root2):
        for entry in root.rglob("*"):
            os.utime(entry, (1000000, 1000000))
    _, data1 = inventory_json(root1, "--tree-hash")
    _, data2 = inventory_json(root2, "--tree-hash")
    assert data1["result"]["tree_hash"] == data2["result"]["tree_hash"]


def test_inventory_max_depth(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-depth", "1")
    assert code == EXIT_SUCCESS
    names = [e["name"] for e in data["result"]["entries"]]
    assert "gamma.txt" not in names
    assert "sub" in names


def test_inventory_max_entries_truncates(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-entries", "2")
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert len(data["result"]["entries"]) == 2


def test_inventory_hash_failure_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_tree(tmp_path)
    monkeypatch.setattr("fs_tool.cli.sha256_of_file", lambda path: None)
    code, data = inventory_json(root, "--hash", "--tree-hash")
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert data["result"]["complete"] is False
    assert "tree_hash" not in data["result"]
    assert any("Cannot hash" in error["message"] for error in data["errors"])


def test_inventory_ignore_pattern(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--ignore-pattern", "*.log")
    assert code == EXIT_SUCCESS
    names = [e["name"] for e in data["result"]["entries"]]
    assert "delta.log" not in names


def test_inventory_dirs_only(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--dirs-only")
    assert code == EXIT_SUCCESS
    names = [e["name"] for e in data["result"]["entries"]]
    assert names == ["sub"]


def test_inventory_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "inspect", "inventory", "/etc"])
    assert code == EXIT_ACCESS_DENIED


def test_inventory_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    code, data = inventory_json(missing)
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False


def test_inventory_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "inventory", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "inventory:" in output
    assert "alpha.txt" in output
    assert "count:" in output
    assert "complete:" in output
