"""Tests for compact and verbose output profiles (v2-verbose plan, Phase 3)."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_FAILURE,
    EXIT_INCOMPLETE,
    EXIT_SUCCESS,
    main,
)

TREE_COMPACT = {"rel_path", "type"}
INVENTORY_COMPACT = {"rel_path", "type", "extension", "size", "modified"}
INVENTORY_COMPACT_HASH = INVENTORY_COMPACT | {"sha256"}
FIND_COMPACT = {"rel_path", "type", "size"}


def run_json(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


def run_text(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _make_tree(base: Path) -> Path:
    root = base / "root"
    root.mkdir(parents=True, exist_ok=True)
    (root / "alpha.txt").write_text("alpha")
    (root / "beta.py").write_text("beta")
    sub = root / "sub"
    sub.mkdir()
    (sub / "gamma.txt").write_text("gamma")
    (root / "link.txt").symlink_to(root / "alpha.txt")
    return root


def _argv(root: Path, command: list[str], *extra: str) -> list[str]:
    return ["--allow-root", str(root), *command, str(root), *extra]


def _entries(data: dict) -> list[dict]:
    return data["result"]["entries"]


def _rel_paths(data: dict) -> list[str]:
    return [entry["rel_path"] for entry in _entries(data)]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["inspect", "tree"], TREE_COMPACT),
        (["inspect", "inventory"], INVENTORY_COMPACT),
        (["find"], FIND_COMPACT),
    ],
)
def test_compact_profile_fields(tmp_path: Path, command: list[str], expected: set[str]) -> None:
    root = _make_tree(tmp_path)
    code, data = run_json(_argv(root, command))
    assert code == EXIT_SUCCESS
    assert data["schema_version"] == 1
    assert _entries(data)
    for entry in _entries(data):
        assert set(entry) == expected


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        (["inspect", "tree"], ()),
        (["inspect", "inventory"], ()),
        (["find"], ()),
    ],
)
def test_compact_and_verbose_return_the_same_entries(
    tmp_path: Path, command: list[str], extra: tuple[str, ...]
) -> None:
    root = _make_tree(tmp_path)
    compact_code, compact = run_json(_argv(root, command, *extra))
    verbose_code, verbose = run_json(_argv(root, command, *extra, "--verbose"))
    assert compact_code == verbose_code == EXIT_SUCCESS
    assert compact["result"]["count"] == verbose["result"]["count"]
    assert _rel_paths(compact) == _rel_paths(verbose)
    assert verbose["schema_version"] == 1
    assert verbose["complete"] == compact["complete"]


def test_verbose_json_includes_full_entry_representation(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, verbose = run_json(_argv(root, ["find"], "--verbose"))
    entry = next(e for e in _entries(verbose) if e["rel_path"] == "alpha.txt")
    for field in (
        "path",
        "name",
        "rel_path",
        "type",
        "extension",
        "size",
        "modified",
        "mode",
        "mime_type",
        "is_symlink",
        "dev_ino",
        "sha256",
    ):
        assert field in entry
    assert entry["path"].startswith(str(root))


def test_inventory_hash_and_tree_hash_ignore_output_profile(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    compact_code, compact = run_json(_argv(root, ["inspect", "inventory"], "--hash", "--tree-hash"))
    verbose_code, verbose = run_json(
        _argv(root, ["inspect", "inventory"], "--hash", "--tree-hash", "--verbose")
    )
    assert compact_code == verbose_code == EXIT_SUCCESS
    assert compact["result"]["tree_hash"] == verbose["result"]["tree_hash"]
    assert compact["result"]["tree_hash"] is not None
    for entry in _entries(compact):
        assert set(entry) == INVENTORY_COMPACT_HASH
    for entry in _entries(verbose):
        assert "path" not in entry
        assert "sha256" in entry


def test_inventory_without_hash_omits_sha256(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, data = run_json(_argv(root, ["inspect", "inventory"]))
    assert all("sha256" not in entry for entry in _entries(data))


def test_verbose_does_not_trigger_hashing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_tree(tmp_path)

    def unexpected_hash(path: Path) -> str | None:
        raise AssertionError(f"unexpected hashing of {path}")

    monkeypatch.setattr("fs_tool.cli.sha256_of_file", unexpected_hash)
    for command in (["inspect", "tree"], ["inspect", "inventory"], ["find"]):
        code, _ = run_json(_argv(root, command, "--verbose"))
        assert code == EXIT_SUCCESS


def test_compact_inventory_remains_verifiable(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = run_json(_argv(root, ["inspect", "inventory"]))
    assert code == EXIT_SUCCESS
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    (root / "alpha.txt").write_text("alpha changed")

    code, verification = run_json(
        ["--allow-root", str(root), "verify", "inventory", str(inventory_file), str(root)]
    )
    assert code == EXIT_FAILURE
    assert verification["result"]["size_mismatch"] == ["alpha.txt"]
    assert "alpha.txt" in verification["result"]["changed"]


def test_compact_inventory_skips_symlink_target_comparison(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = run_json(_argv(root, ["inspect", "inventory"]))
    assert code == EXIT_SUCCESS
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    link = root / "link.txt"
    link.unlink()
    link.symlink_to(root / "beta.py")

    code, verification = run_json(
        ["--allow-root", str(root), "verify", "inventory", str(inventory_file), str(root)]
    )
    assert code == EXIT_SUCCESS
    assert verification["result"]["changed"] == []


def test_verbose_option_positions_match_for_json_and_plain(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)

    def normalize_json(text: str) -> dict:
        data = json.loads(text)
        for entry in data["result"]["entries"]:
            # Access timestamps can change between two scans of the same tree.
            entry.pop("accessed", None)
            entry.pop("changed", None)
        return data

    def normalize_plain(text: str) -> str:
        volatile = ("accessed:", "changed:")
        return "\n".join(
            line for line in text.splitlines() if not line.strip().startswith(volatile)
        )

    def compare(command: list[str], *extra: str) -> None:
        before = ["--allow-root", str(root), "--verbose", *command, str(root), *extra]
        after = ["--allow-root", str(root), *command, str(root), *extra, "--verbose"]
        before_code, before_output = run_text(before)
        after_code, after_output = run_text(after)
        assert before_code == after_code == EXIT_SUCCESS
        if "--json" in extra:
            assert normalize_json(before_output) == normalize_json(after_output)
        else:
            assert normalize_plain(before_output) == normalize_plain(after_output)

    compare(["inspect", "tree"], "--json")
    compare(["inspect", "tree"], "--plain")
    compare(["find"], "--json")
    compare(["find"], "--plain")


def test_verbose_does_not_change_inspect_info_or_analyze(
    tmp_path: Path,
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def greet(name):\n    return name\n")

    for command in (["inspect", "info"], ["inspect", "analyze"]):
        plain_code, plain = run_json(["--allow-root", str(tmp_path), *command, str(source)])
        verbose_code, verbose = run_json(
            ["--allow-root", str(tmp_path), "--verbose", *command, str(source)]
        )
        assert plain_code == verbose_code == EXIT_SUCCESS
        assert plain == verbose


@pytest.mark.parametrize("command", [["inspect", "tree"], ["inspect", "inventory"], ["find"]])
def test_incomplete_scans_keep_their_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    root = _make_tree(tmp_path)
    blocked = root / "blocked"
    blocked.mkdir()
    real_scandir = os.scandir

    def scandir(path: str | Path) -> os.ScandirIterator[os.DirEntry[str]]:
        if Path(path) == blocked:
            raise PermissionError("Permission denied")
        return real_scandir(path)

    monkeypatch.setattr("fs_tool.core.traversal.os.scandir", scandir)

    for extra in ((), ("--verbose",)):
        code, data = run_json(_argv(root, command, *extra))
        assert code == EXIT_INCOMPLETE
        assert data["success"] is False
        assert data["complete"] is False
        assert data["errors"]
        assert data["schema_version"] == 1
