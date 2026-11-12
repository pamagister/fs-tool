"""Tests for the ``inspect inventory`` command (plan.md Phase 2, P2-T15..P2-T20)."""

from __future__ import annotations

import csv
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
    EXIT_INVALID_ARGS,
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
    assert "extension=.txt" in output
    assert "mode:" in output


def test_inventory_plain_verbose_includes_null_and_false_values(
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
    assert "sha256: null" in output
    assert "is_symlink: false" in output
    assert "target: null" in output
    assert "metadata: null" in output
    # Directory entries have no extension; the detail block must show it.
    assert "extension: null" in output


def test_inventory_plain_verbose_with_hash_does_not_repeat_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "flat"
    root.mkdir()
    (root / "only.txt").write_text("only")
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "--verbose",
            "inspect",
            "inventory",
            str(root),
            "--hash",
        ]
    )
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "sha256: null" not in output
    assert "sha256=" in output


def test_inventory_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "inventory", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "inventory:" in output
    assert "alpha.txt" in output
    assert "count:" in output
    assert "complete:" in output
    assert "modified=" in output
    assert "extension=.txt" in output


def test_inventory_plain_compact_matches_json_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    _, data = inventory_json(root)
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "inventory", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    for entry in data["result"]["entries"]:
        assert entry["rel_path"] in output
        assert f"size={entry['size']}" in output
        assert f"modified={entry['modified']}" in output
        if entry["extension"] is not None:
            assert f"extension={entry['extension']}" in output
        if entry.get("sha256") is not None:
            assert f"sha256={entry['sha256']}" in output


def test_inventory_sort_by_size_and_no_default_ignore(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    code, data = inventory_json(root, "--sort-by", "size", "--no-default-ignore")
    assert code == EXIT_SUCCESS
    rel_paths = [entry["rel_path"] for entry in data["result"]["entries"]]
    assert ".git" in rel_paths
    assert rel_paths.index("beta.txt") < rel_paths.index("alpha.txt")


def test_inventory_invalid_sort_by(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "inspect",
            "inventory",
            str(root),
            "--sort-by",
            "bogus",
        ]
    )
    assert code == EXIT_INVALID_ARGS
    assert "Invalid --sort-by" in capsys.readouterr().err


def test_inventory_reports_skipped_entries(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    code, data = inventory_json(root)
    assert code == EXIT_SUCCESS
    assert data["result"]["skipped"] == 1
    assert data["result"]["truncated"] is False


def test_inventory_reports_truncation(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-entries", "2")
    assert code == EXIT_INCOMPLETE
    assert data["result"]["truncated"] is True
    assert data["result"]["complete"] is False


def test_inventory_plain_reports_skipped_and_truncated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "inspect",
            "inventory",
            str(root),
            "--max-entries",
            "2",
        ]
    )
    assert code == EXIT_INCOMPLETE
    output = capsys.readouterr().out
    assert "skipped: 1" in output
    assert "truncated: True" in output


def test_inventory_extension_filter(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--extension", "txt")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "delta.log" not in names
    assert "alpha.txt" in names
    assert data["result"]["filtered"] == 1
    assert data["result"]["complete"] is True


def test_inventory_min_size_filter(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--min-size", "5")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "beta.txt" not in names
    assert "alpha.txt" in names
    assert data["result"]["filtered"] == 1


def test_inventory_max_size_filter(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-size", "4")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "beta.txt" in names
    assert "alpha.txt" not in names
    assert data["result"]["filtered"] == 3


def test_inventory_filters_run_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_tree(tmp_path)
    import fs_tool.cli as cli_module

    hashed: list[str] = []

    def tracking_hash(path: Path) -> str:
        hashed.append(str(path))
        return "0" * 64

    monkeypatch.setattr(cli_module, "sha256_of_file", tracking_hash)
    code, data = inventory_json(root, "--extension", "txt", "--hash")

    assert code == EXIT_SUCCESS
    assert not any(path.endswith("delta.log") for path in hashed)
    assert all(Path(path).suffix == ".txt" for path in hashed)
    assert data["result"]["filtered"] == 1


def test_inventory_filters_define_tree_hash_scope(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--extension", "txt", "--tree-hash")

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["count"] == 4
    assert result["filtered"] == 1
    assert result["tree_hash"] == _compute_tree_hash(result["entries"])
    assert result["tree_hash"] != _compute_tree_hash(
        [entry for entry in result["entries"] if entry["rel_path"] != "alpha.txt"]
    )


def test_inventory_invalid_size_filter(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--min-size", "bogus")
    assert code == EXIT_INVALID_ARGS
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_inventory_fields_subset_and_order(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--fields", "size,rel_path")
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        assert list(entry) == ["size", "rel_path"]


def test_inventory_fields_reject_path(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--fields", "path")
    assert code == EXIT_INVALID_ARGS
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_inventory_fields_override_verbose(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--fields", "size", "--verbose")
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        assert list(entry) == ["size"]


def test_inventory_fields_do_not_change_tree_hash(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    _, compact = inventory_json(root, "--tree-hash")
    _, selected = inventory_json(root, "--tree-hash", "--fields", "size,rel_path")
    assert compact["result"]["tree_hash"] == selected["result"]["tree_hash"]


def test_inventory_max_hash_bytes_skips_large_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "small.txt").write_text("a")
    (root / "large.bin").write_bytes(b"x" * 100)
    code, data = inventory_json(root, "--hash", "--max-hash-bytes", "10")
    assert code == EXIT_SUCCESS
    entries = {entry["rel_path"]: entry for entry in data["result"]["entries"]}
    assert entries["small.txt"]["sha256"] is not None
    assert entries["large.bin"]["sha256"] is None
    assert any(warning["code"] == "HASH_SKIPPED" for warning in data["warnings"])


def test_inventory_invalid_max_hash_bytes(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-hash-bytes", "bogus")
    assert code == EXIT_INVALID_ARGS
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_inventory_progress_writes_to_stderr_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "inspect",
            "inventory",
            str(root),
            "--progress",
        ]
    )
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["result"]["count"] == 5
    assert "fs-tool: scan finished" in captured.err
    assert "fs-tool:" not in captured.out


def test_inventory_short_verbose_flag(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "-v")
    assert code == EXIT_SUCCESS
    assert "mode" in data["result"]["entries"][0]


def test_inventory_no_verbose_flag_overrides_verbose(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--verbose", "--no-verbose")
    assert code == EXIT_SUCCESS
    for entry in data["result"]["entries"]:
        assert set(entry) == {"rel_path", "type", "extension", "size", "modified"}


def test_inventory_csv_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--format",
            "csv",
            "inspect",
            "inventory",
            str(root),
        ]
    )
    assert code == EXIT_SUCCESS
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert len(rows) == 5
    assert rows[0]["rel_path"] == "alpha.txt"
    assert rows[0]["type"] == "file"
    assert rows[0]["extension"] == ".txt"


def test_inventory_tsv_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--format",
            "tsv",
            "inspect",
            "inventory",
            str(root),
        ]
    )
    assert code == EXIT_SUCCESS
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out), delimiter="\t"))
    assert len(rows) == 5
    assert rows[0]["rel_path"] == "alpha.txt"


def test_inventory_csv_respects_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--format",
            "csv",
            "inspect",
            "inventory",
            str(root),
            "--fields",
            "rel_path,size",
        ]
    )
    assert code == EXIT_SUCCESS
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert list(rows[0]) == ["rel_path", "size"]


def test_inventory_csv_quotes_commas_in_filenames(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a,b.txt").write_text("x")
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--format",
            "csv",
            "inspect",
            "inventory",
            str(root),
        ]
    )
    assert code == EXIT_SUCCESS
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert rows[0]["rel_path"] == "a,b.txt"


def test_inventory_csv_rejected_for_other_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--format",
            "csv",
            "inspect",
            "tree",
            str(root),
        ]
    )
    assert code == EXIT_INVALID_ARGS
    assert "only supported by inspect inventory" in capsys.readouterr().err


def test_inventory_rejects_negative_bounds(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    for option in ("--max-depth", "--max-entries"):
        code = main(argv_for(root, option, "-1"))
        assert code == EXIT_INVALID_ARGS


def test_inventory_max_depth_zero_returns_no_entries(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-depth", "0")
    assert code == EXIT_SUCCESS
    assert data["result"]["entries"] == []
    assert data["result"]["count"] == 0
    assert data["result"]["complete"] is True


def test_inventory_max_entries_zero_is_incomplete(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = inventory_json(root, "--max-entries", "0")
    assert code == EXIT_INCOMPLETE
    assert data["result"]["entries"] == []
    assert data["result"]["complete"] is False
    assert data["result"]["truncated"] is True
