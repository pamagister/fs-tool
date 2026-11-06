"""Tests for filesystem path normalization (plan.md Phase 1, P1-T01)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fs_tool.core.filesystem import normalize_path, resolve_path


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
