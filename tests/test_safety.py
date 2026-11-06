"""Tests for allowed-root validation (plan.md Phase 1, P1-T02, D6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fs_tool.core.errors import EXIT_CODES, ErrorCode
from fs_tool.core.filesystem import normalize_path
from fs_tool.safety.validation import (
    PathNotAllowedError,
    default_allowed_roots,
    is_within_root,
    validate_path,
)


def test_default_roots_are_home_and_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    roots = default_allowed_roots()
    assert Path.home() in roots
    assert tmp_path in roots


def test_default_roots_do_not_implicitly_allow_root_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir("/")
    roots = default_allowed_roots()
    assert roots == (Path.home(),)


def test_path_under_home_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert validate_path(Path.home() / "file.txt") == Path.home() / "file.txt"


def test_path_under_cwd_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert validate_path(tmp_path / "sub" / "file.txt") == tmp_path / "sub" / "file.txt"


def test_path_outside_roots_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    other = Path("/tmp/fs-tool-safety-test-outside")
    other.mkdir(exist_ok=True)
    with pytest.raises(PathNotAllowedError) as exc:
        validate_path(other / "file.txt")
    assert exc.value.code.name == "ROOT_NOT_ALLOWED"
    assert exc.value.exit_code == 3
    assert str(exc.value.path).endswith("file.txt")


def test_explicit_allow_root_grants_access(tmp_path: Path) -> None:
    assert validate_path(tmp_path / "file.txt", allowed_roots=(tmp_path,)) == (
        tmp_path / "file.txt"
    )


def test_error_exit_code_is_three() -> None:
    assert EXIT_CODES[ErrorCode.ROOT_NOT_ALLOWED] == 3


def test_is_within_root() -> None:
    root = Path("/home/user")
    assert is_within_root(root / "file.txt", root)
    assert is_within_root(root, root)
    assert not is_within_root(Path("/home/other"), root)
    assert not is_within_root(Path("/etc/passwd"), root)


def test_normalize_path_inside_root_passes(tmp_path: Path) -> None:
    assert normalize_path(str(tmp_path / "a" / ".." / "b")) == tmp_path / "b"
