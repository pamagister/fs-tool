"""Tests for the ``inspect inventory`` command (plan.md Phase 2, P2-T15..P2-T20)."""

from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_INCOMPLETE,
    EXIT_SUCCESS,
    _compute_tree_hash,
    main,
)


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


def names_of(data: dict) -> list[str]:
    return [Path(entry["rel_path"]).name for entry in data["result"]["entries"]]


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
    assert names_of(data) == ["alpha.txt", "beta.txt", "sub", "delta.log", "gamma.txt"]
    for entry in result["entries"]:
        assert set(entry) == {"rel_path", "type", "extension", "size", "modified"}


def test_inventory_entries_use_relative_paths_only(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root)
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        assert entry["rel_path"] is not None
        assert "path" not in entry
        assert not Path(entry["rel_path"]).is_absolute()


def test_inventory_verbose_json_keeps_all_entry_fields(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--verbose")
    assert code == EXIT_SUCCESS
    entry = next(e for e in data["result"]["entries"] if e["rel_path"] == "alpha.txt")
    assert entry["name"] == "alpha.txt"
    assert "path" not in entry
    assert entry["extension"] == ".txt"
    assert entry["size"] == 5
    assert entry["modified"] is not None
    assert entry["mode"] is not None
    assert "dev_ino" in entry
    assert entry["sha256"] is None


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


def _tree_hash_entry(**overrides: object) -> dict:
    entry = {
        "rel_path": "alpha.txt",
        "type": "file",
        "extension": ".txt",
        "size": 5,
        "sha256": None,
        "path": "/tmp/alpha.txt",
        "dev_ino": "1:2",
        "modified": "2026-01-01T00:00:00+00:00",
        "accessed": "2026-01-01T00:00:00+00:00",
        "changed": "2026-01-01T00:00:00+00:00",
        "created": None,
        "mode": "-rw-r--r--",
        "owner": "user",
        "mime_type": "text/plain",
        "is_symlink": False,
        "target": None,
        "metadata": None,
    }
    entry.update(overrides)
    return entry


def test_compute_tree_hash_ignores_environment_specific_fields() -> None:
    base = _tree_hash_entry()
    environment_changed = _tree_hash_entry(
        mode="-rw-------",
        owner="other",
        mime_type="application/octet-stream",
        target="/somewhere/else",
        dev_ino="9:9",
        modified="2030-01-01T00:00:00+00:00",
        accessed="2030-01-01T00:00:00+00:00",
        changed="2030-01-01T00:00:00+00:00",
        created="2030-01-01T00:00:00+00:00",
        path="/other/alpha.txt",
    )
    assert _compute_tree_hash([base]) == _compute_tree_hash([environment_changed])


def test_compute_tree_hash_changes_with_content_fields() -> None:
    base = _tree_hash_entry()
    changed_fields = (
        _tree_hash_entry(rel_path="beta.txt"),
        _tree_hash_entry(type="directory"),
        _tree_hash_entry(extension=".md"),
        _tree_hash_entry(size=6),
        _tree_hash_entry(sha256="a" * 64),
    )
    for changed in changed_fields:
        assert _compute_tree_hash([base]) != _compute_tree_hash([changed])


def test_compute_tree_hash_normalizes_non_file_sizes() -> None:
    directory = _tree_hash_entry(type="directory", size=4096)
    directory_other_size = _tree_hash_entry(type="directory", size=8192)
    symlink = _tree_hash_entry(type="symlink", size=10, target="a")
    symlink_other_size = _tree_hash_entry(type="symlink", size=200, target="b")
    assert _compute_tree_hash([directory]) == _compute_tree_hash([directory_other_size])
    assert _compute_tree_hash([symlink]) == _compute_tree_hash([symlink_other_size])


def test_inventory_tree_hash_ignores_mode_changes(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, before = inventory_json(root, "--tree-hash")
    os.chmod(root / "alpha.txt", 0o600)
    _, after = inventory_json(root, "--tree-hash")
    assert before["result"]["tree_hash"] == after["result"]["tree_hash"]


def test_inventory_tree_hash_changes_with_content(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, before = inventory_json(root, "--tree-hash")
    (root / "alpha.txt").write_text("changed")
    _, after = inventory_json(root, "--tree-hash")
    assert before["result"]["tree_hash"] != after["result"]["tree_hash"]


def test_inventory_tree_hash_ignores_symlink_target(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    link = root / "link"
    link.symlink_to(root / "alpha.txt")
    _, before = inventory_json(root, "--tree-hash")
    link.unlink()
    link.symlink_to(root / "sub" / "gamma.txt")
    _, after = inventory_json(root, "--tree-hash")
    assert before["result"]["tree_hash"] == after["result"]["tree_hash"]


def test_inventory_max_depth(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-depth", "1")
    assert code == EXIT_SUCCESS
    names = names_of(data)
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
    names = names_of(data)
    assert "delta.log" not in names


def test_inventory_dirs_only(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--dirs-only")
    assert code == EXIT_SUCCESS
    names = names_of(data)
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


def test_inventory_plain_verbose_shows_entry_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "--verbose",
            "inspect",
            "inventory",
            str(root),
        ]
    )
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "alpha.txt [file]" in output
    assert "extension: .txt" in output
    assert "mode:" in output


def test_inventory_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "inventory", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "inventory:" in output
    assert "alpha.txt" in output
    assert "count:" in output
    assert "complete:" in output
