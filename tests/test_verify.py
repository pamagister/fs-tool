"""Tests for the ``verify`` command (plan.md Phase 3, P3-T19..P3-T24)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_FAILURE,
    EXIT_INCOMPLETE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)


def argv_inventory(inventory_file: Path, target: Path, *extra: str) -> list[str]:
    return [
        "--allow-root",
        str(target.parent),
        "verify",
        "inventory",
        str(inventory_file),
        str(target),
        *extra,
    ]


def argv_tree(source: Path, destination: Path, *extra: str) -> list[str]:
    return [
        "--allow-root",
        str(source.parent),
        "verify",
        "tree",
        str(source),
        str(destination),
        *extra,
    ]


def run_json(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


def _write(path: Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8"))


def _make_inventory(tmp_path: Path, root: Path, *extra: str) -> Path:
    """Create an inventory JSON file using the real CLI output envelope."""
    code, data = run_json(
        ["--allow-root", str(root), "inspect", "inventory", str(root), "--hash", *extra]
    )
    assert code == 0
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")
    return inventory_file


def test_verify_inventory_matching(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")
    _write(root / "b.txt", "world")

    inventory_file = _make_inventory(tmp_path, root)

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "verify.inventory"
    assert data["complete"] is True
    assert data["result"]["missing"] == []
    assert data["result"]["unexpected"] == []
    assert data["result"]["changed"] == []


def test_verify_inventory_accepts_bare_inventory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")

    code, data = run_json(["--allow-root", str(root), "inspect", "inventory", str(root), "--hash"])
    assert code == 0
    inventory_data = data["result"]
    inventory_data["schema_version"] = 1
    inventory_file = tmp_path / "bare-inventory.json"
    inventory_file.write_text(json.dumps(inventory_data), encoding="utf-8")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_SUCCESS
    assert data["complete"] is True
    assert data["result"]["missing"] == []
    assert data["result"]["unexpected"] == []


def test_verify_inventory_rejects_non_object_json(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text("[]", encoding="utf-8")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "expected a JSON object" in data["errors"][0]["message"]


def test_verify_inventory_rejects_invalid_entry(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(
        json.dumps({"schema_version": 1, "entries": [{"type": "file"}]}),
        encoding="utf-8",
    )

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_INVALID_ARGS
    assert "rel_path" in data["errors"][0]["message"]


def test_verify_inventory_incomplete_inventory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")
    _write(root / "b.txt", "world")

    code, data = run_json(
        ["--allow-root", str(root), "inspect", "inventory", str(root), "--max-entries", "1"]
    )
    assert code == EXIT_INCOMPLETE
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_INCOMPLETE
    assert data["complete"] is False
    assert data["result"]["complete"] is False
    assert any("incomplete scan" in error["message"] for error in data["errors"])


def test_verify_inventory_hash_failure_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")
    inventory_file = _make_inventory(tmp_path, root)

    monkeypatch.setattr("fs_tool.core.analysis.verification.sha256_of_file", lambda path: None)
    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_INCOMPLETE
    assert data["complete"] is False
    assert data["result"]["changed"] == []
    assert any("Cannot hash" in error["message"] for error in data["errors"])


def test_verify_inventory_missing(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")
    _write(root / "b.txt", "world")

    inventory_file = _make_inventory(tmp_path, root)

    # Delete a file from root
    (root / "b.txt").unlink()

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "b.txt" in data["result"]["missing"]
    assert data["complete"] is True


def test_verify_inventory_unexpected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")

    inventory_file = _make_inventory(tmp_path, root)

    # Add a new file to root
    _write(root / "new.txt", "new content")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "new.txt" in data["result"]["unexpected"]


def test_verify_inventory_changed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "original content")

    inventory_file = _make_inventory(tmp_path, root)

    # Modify the file
    _write(root / "a.txt", "modified content")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "a.txt" in data["result"]["changed"]
    assert "a.txt" in data["result"]["hash_mismatch"]


def test_verify_inventory_schema_version(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")

    # Create inventory with wrong schema version
    inventory_file = tmp_path / "inventory.json"
    bad_inventory = {
        "schema_version": 99,
        "entries": [],
        "count": 0,
        "root": str(root),
        "complete": True,
    }
    inventory_file.write_text(json.dumps(bad_inventory), encoding="utf-8")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "schema_version" in data["errors"][0]["message"]


def test_verify_inventory_outside_allowed_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")
    inventory_file = _make_inventory(tmp_path, root)

    # Target outside allowed root: use /tmp as allow-root, /etc as target
    code = main(
        [
            "--allow-root",
            "/tmp",
            "verify",
            "inventory",
            str(inventory_file),
            "/etc/hostname",
        ]
    )
    assert code == EXIT_ACCESS_DENIED


def run_plain(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def test_verify_inventory_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "a.txt", "hello")

    inventory_file = _make_inventory(tmp_path, root)

    code, output = run_plain(
        [
            "--allow-root",
            str(root),
            "--plain",
            "verify",
            "inventory",
            str(inventory_file),
            str(root),
        ]
    )
    assert code == EXIT_SUCCESS
    assert "complete:" in output


def test_verify_tree_matching(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "hello")
    _write(destination / "a.txt", "hello")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "verify.tree"
    assert data["result"]["missing"] == []
    assert data["result"]["unexpected"] == []
    assert data["result"]["changed"] == []


def test_verify_tree_missing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "hello")
    _write(source / "b.txt", "world")
    _write(destination / "a.txt", "hello")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "b.txt" in data["result"]["missing"]


def test_verify_tree_unexpected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "hello")
    _write(destination / "a.txt", "hello")
    _write(destination / "extra.txt", "extra")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "extra.txt" in data["result"]["unexpected"]


def test_verify_tree_hash_failure_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "hello")
    _write(destination / "a.txt", "hello")

    monkeypatch.setattr("fs_tool.core.analysis.verification.sha256_of_file", lambda path: None)
    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_INCOMPLETE
    assert data["complete"] is False
    assert data["result"]["changed"] == []
    assert any("Cannot hash" in error["message"] for error in data["errors"])


def test_verify_tree_changed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "a.txt", "same size content")
    _write(destination / "a.txt", "different size content")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert "a.txt" in data["result"]["changed"]
    assert "a.txt" in data["result"]["size_mismatch"]


def test_verify_inventory_ignores_directory_size_differences(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "sub").mkdir()
    _write(root / "sub" / "a.txt", "hello")

    inventory_file = _make_inventory(tmp_path, root)
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    directory_entries = [
        entry for entry in inventory["result"]["entries"] if entry["type"] == "directory"
    ]
    assert directory_entries
    # Directory sizes are filesystem-specific; a different value must
    # not make verification fail.
    for entry in directory_entries:
        entry["size"] = (entry["size"] or 0) + 4096
    inventory_file.write_text(json.dumps(inventory), encoding="utf-8")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_SUCCESS
    assert data["result"]["size_mismatch"] == []
    assert data["result"]["changed"] == []


def test_verify_inventory_detects_changed_symlink_target(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "aaa", "one")
    _write(root / "bbb", "two")
    link = root / "link"
    link.symlink_to("aaa")

    inventory_file = _make_inventory(tmp_path, root, "--verbose")

    link.unlink()
    link.symlink_to("bbb")

    code, data = run_json(argv_inventory(inventory_file, root))
    assert code == EXIT_FAILURE
    assert "link" in data["result"]["changed"]
    assert data["result"]["size_mismatch"] == []


def test_verify_tree_detects_changed_symlink_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "target.txt", "same")
    _write(destination / "target.txt", "same")
    (source / "link").symlink_to("target.txt")
    (destination / "link").symlink_to("other.txt")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_FAILURE
    assert data["result"]["changed"] == ["link"]
    assert data["result"]["size_mismatch"] == []
    assert data["result"]["hash_mismatch"] == []


def test_verify_tree_identical_symlink_targets(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    _write(source / "target.txt", "same")
    _write(destination / "target.txt", "same")
    (source / "link").symlink_to("target.txt")
    (destination / "link").symlink_to("target.txt")

    code, data = run_json(argv_tree(source, destination))
    assert code == EXIT_SUCCESS
    assert data["result"]["changed"] == []
