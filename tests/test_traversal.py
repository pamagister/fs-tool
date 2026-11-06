"""Tests for filesystem path normalization (plan.md Phase 1, P1-T01)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from fs_tool.core.filesystem import normalize_path, resolve_path
from fs_tool.core.models import EntryType
from fs_tool.core.traversal import traverse


def test_normalize_path_makes_relative_paths_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert normalize_path("sub/../file.txt") == tmp_path / "file.txt"


def test_normalize_path_keeps_absolute_paths(tmp_path: Path) -> None:
    assert normalize_path(tmp_path / "a" / ".." / "b") == tmp_path / "b"


def test_normalize_path_expands_user() -> None:
    assert normalize_path("~/file.txt") == Path.home() / "file.txt"


def test_normalize_path_collapses_dot_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert normalize_path("a/./b/../c") == tmp_path / "a" / "c"


def test_resolve_path_resolves_existing_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    assert resolve_path(link) == target


def test_normalize_path_does_not_access_filesystem(tmp_path: Path) -> None:
    """Normalization must be lexical: a nonexistent path is normalized anyway."""
    assert normalize_path(str(tmp_path / "nonexistent" / ".." / "file.txt")) == (
        tmp_path / "file.txt"
    )


def _make_tree(tmp_path: Path) -> Path:
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "z.py").write_text("z")
    beta = tmp_path / "beta"
    beta.mkdir()
    (beta / "gamma.txt").write_text("g")
    (beta / ".hidden").write_text("h")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("c")
    return tmp_path


def test_traversal_returns_sorted_entries(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root)
    names = [entry.name for entry in result.entries]
    assert names == ["alpha.txt", "beta", ".hidden", "gamma.txt", "z.py"]
    assert result.complete is True
    assert result.errors == []


def test_traversal_relative_paths(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root)
    for entry in result.entries:
        assert Path(entry.path).relative_to(root) == Path(entry.rel_path)


def test_traversal_max_depth(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root, max_depth=1)
    names = [entry.name for entry in result.entries]
    assert "gamma.txt" not in names
    assert ".hidden" not in names
    assert "beta" in names


def test_traversal_max_depth_two(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root, max_depth=2)
    names = [entry.name for entry in result.entries]
    assert "gamma.txt" in names
    assert ".hidden" in names


def test_traversal_max_entries_truncates(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root, max_entries=2)
    assert result.complete is False
    assert len(result.entries) == 2
    assert [e.name for e in result.entries] == ["alpha.txt", "beta"]


def test_traversal_ignores_default_dirs(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root)
    assert all(entry.name != "config" for entry in result.entries)
    assert result.skipped >= 1


def test_traversal_ignore_patterns(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root, ignore_patterns=("*.py",))
    assert all(entry.name != "z.py" for entry in result.entries)


def test_traversal_dirs_only(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    result = traverse(root, dirs_only=True)
    assert all(entry.type is EntryType.DIRECTORY for entry in result.entries)
    assert any(entry.name == "beta" for entry in result.entries)


def test_traversal_records_symlink_without_following(tmp_path: Path) -> None:
    target = tmp_path.parent / f"symlink-target-{tmp_path.name}.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    result = traverse(tmp_path)
    links = [e for e in result.entries if e.is_symlink]
    assert len(links) == 1
    recorded = links[0].target
    if recorded.startswith("\\\\?\\"):
        recorded = recorded[4:]
    assert recorded == str(target)
    assert not any(e.name == target.name for e in result.entries)


def test_traversal_nonexistent_root_reports_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = traverse(missing)
    assert result.entries == []
    assert len(result.errors) == 1
    assert "does-not-exist" in result.errors[0].path


def test_traversal_deterministic(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    first = traverse(root)
    second = traverse(root)
    assert [e.path for e in first.entries] == [e.path for e in second.entries]


def test_traversal_special_file_is_unsupported(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo not available")
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    result = traverse(tmp_path)
    pipes = [e for e in result.entries if e.name == "pipe"]
    assert len(pipes) == 1
    assert pipes[0].type is EntryType.OTHER


def test_traversal_entries_have_metadata(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello")
    result = traverse(tmp_path)
    entry = result.entries[0]
    assert entry.mode is not None and entry.mode.startswith(("-", "d", "l"))
    assert entry.modified.endswith("+00:00")
    assert entry.accessed.endswith("+00:00")
    assert entry.changed.endswith("+00:00")
    assert entry.created is None or entry.created.endswith("+00:00")
    assert entry.owner is None or isinstance(entry.owner, str)
    assert entry.dev_ino is not None


@pytest.mark.parametrize(
    "name,expected",
    [("report.txt", "text/plain"), ("archive.pdf", "application/pdf"), ("data", None)],
)
def test_traversal_mime_type(tmp_path: Path, name: str, expected: str | None) -> None:
    if name == "data":
        (tmp_path / name).mkdir()
    else:
        (tmp_path / name).write_text("x")
    result = traverse(tmp_path)
    entry = next(e for e in result.entries if e.name == name)
    if sys.platform == "win32":
        assert entry.mime_type is None or isinstance(entry.mime_type, str)
    else:
        assert entry.mime_type == expected
