"""Tests for the ``find`` command (plan.md Phase 3, P3-T01..P3-T05)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_INCOMPLETE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)
from fs_tool.core.analysis.search import parse_size


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "find", str(source), *extra]


def find_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def names_of(data: dict) -> list[str]:
    return [Path(entry["rel_path"]).name for entry in data["result"]["entries"]]


def _make_tree(tmp_path: Path) -> Path:
    (tmp_path / "alpha.txt").write_text("alpha")
    (tmp_path / "beta.py").write_text("beta")
    (tmp_path / "gamma.PDF").write_text("gamma")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "delta.txt").write_text("delta")
    (sub / "epsilon.py").write_text("epsilon")
    nested = sub / "nested"
    nested.mkdir()
    (nested / "zeta.txt").write_text("zeta")
    link = tmp_path / "link.txt"
    link.symlink_to(tmp_path / "alpha.txt")
    return tmp_path


def test_find_json_shape(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "find"
    assert data["complete"] is True
    assert data["errors"] == []
    result = data["result"]
    assert result["root"] == str(root)
    assert result["count"] == 9
    assert names_of(data) == [
        "alpha.txt",
        "beta.py",
        "gamma.PDF",
        "link.txt",
        "sub",
        "delta.txt",
        "epsilon.py",
        "nested",
        "zeta.txt",
    ]
    for entry in result["entries"]:
        assert set(entry) == {"rel_path", "type", "size"}


def test_find_verbose_json_keeps_all_entry_fields(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--verbose")
    assert code == EXIT_SUCCESS
    entry = next(e for e in data["result"]["entries"] if e["rel_path"] == "alpha.txt")
    assert entry["name"] == "alpha.txt"
    assert Path(entry["path"]).is_absolute()
    assert entry["extension"] == ".txt"
    assert entry["size"] == 5
    assert entry["modified"] is not None


def test_find_name_pattern(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--name", "*.txt")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["alpha.txt", "link.txt", "delta.txt", "zeta.txt"]


def test_find_name_patterns_are_combined_with_or(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--name", "*.txt", "--name", "*.py")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == [
        "alpha.txt",
        "beta.py",
        "link.txt",
        "delta.txt",
        "epsilon.py",
        "zeta.txt",
    ]


def test_find_invalid_modified_timestamp_is_rejected(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--modified-after", "not-a-timestamp")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "--modified-after" in data["errors"][0]["message"]


def test_find_invalid_modified_before_timestamp_is_rejected(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--modified-before", "2024-99-99")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "--modified-before" in data["errors"][0]["message"]


def test_find_extension_filter(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--extension", "py")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["beta.py", "epsilon.py"]


def test_find_extension_with_dot(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--extension", ".PDF")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["gamma.PDF"]


def test_find_type_file(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--type", "file")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "sub" not in names
    assert "nested" not in names
    assert all(e["type"] == "file" for e in data["result"]["entries"])


def test_find_type_directory(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--type", "directory")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["sub", "nested"]


def test_find_type_symlink(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--type", "symlink")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["link.txt"]


def test_find_type_invalid(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--type", "invalid")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "Invalid --type value" in data["errors"][0]["message"]


def test_find_min_size(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (root / "tiny.txt").write_text("x")
    code, data = find_json(root, "--min-size", "5")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    # "tiny.txt" (1 byte) and directories (size None) excluded
    assert "tiny.txt" not in names
    for entry in data["result"]["entries"]:
        if entry["type"] == "file":
            assert entry["size"] >= 5


def test_find_max_size(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (root / "large.txt").write_text("x" * 100)
    code, data = find_json(root, "--max-size", "10")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "large.txt" not in names
    for entry in data["result"]["entries"]:
        if entry["type"] == "file":
            assert entry["size"] <= 10


def test_find_size_with_suffix(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (root / "medium.txt").write_text("x" * 2000)
    code, data = find_json(root, "--min-size", "1K")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert "medium.txt" in names


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "-1K"])
def test_parse_size_rejects_non_finite_and_negative_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_size(value)


def test_parse_size_accepts_binary_suffixes() -> None:
    assert parse_size("1024") == 1024
    assert parse_size("1K") == 1024
    assert parse_size("2.5M") == int(2.5 * 1024**2)


def test_find_rejects_infinite_size(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--min-size", "inf")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "Invalid --min-size value" in data["errors"][0]["message"]


def test_find_rejects_negative_size(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--min-size=-1K")
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "must not be negative" in data["errors"][0]["message"]


def test_find_modified_after(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    future = datetime.now(tz=UTC).replace(year=2099).isoformat()
    code, data = find_json(root, "--modified-after", future)
    assert code == EXIT_SUCCESS
    assert data["result"]["count"] == 0


def test_find_modified_before(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    past = datetime.now(tz=UTC).replace(year=1990).isoformat()
    code, data = find_json(root, "--modified-before", past)
    assert code == EXIT_SUCCESS
    assert data["result"]["count"] == 0


def test_find_combined_filters(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--name", "*.py", "--type", "file")
    assert code == EXIT_SUCCESS
    names = names_of(data)
    assert names == ["beta.py", "epsilon.py"]


def test_find_no_matches(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--name", "*.xyz")
    assert code == EXIT_SUCCESS
    assert data["result"]["count"] == 0
    assert data["result"]["entries"] == []


def test_find_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "find", "/etc/hostname"])
    assert code == EXIT_ACCESS_DENIED


def test_find_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "find", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert f"find: {root}" in output
    assert "alpha.txt" in output
    assert "count:" in output


def test_find_plain_verbose_shows_entry_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_tree(tmp_path)
    code = main(["--allow-root", str(tmp_path), "--plain", "--verbose", "find", str(root)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "alpha.txt [file] size=5" in output
    assert "extension: .txt" in output
    assert "modified:" in output


def test_find_incomplete_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    real_scandir = __import__("os").scandir

    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError("Permission denied")
        return real_scandir(path)

    monkeypatch.setattr("fs_tool.core.traversal.os.scandir", scandir)
    code, data = find_json(tmp_path)
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False


def test_find_max_entries_is_incomplete(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    code, data = find_json(root, "--max-entries", "2")
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert data["result"]["complete"] is False
    assert data["result"]["count"] == 2


def test_find_sort_by_size_and_no_default_ignore(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("abcdef")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    code, data = find_json(tmp_path, "--sort-by", "size", "--no-default-ignore")
    assert code == EXIT_SUCCESS
    rel_paths = [entry["rel_path"] for entry in data["result"]["entries"]]
    assert ".git/config" in rel_paths
    assert rel_paths.index("a.txt") < rel_paths.index("b.txt")
