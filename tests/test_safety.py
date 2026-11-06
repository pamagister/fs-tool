"""Tests for allowed-root validation (plan.md Phase 1, P1-T02, D6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fs_tool.core.errors import EXIT_CODES, ErrorCode
from fs_tool.core.filesystem import normalize_path
from fs_tool.safety.validation import (
    PathNotAllowedError,
    default_allowed_roots,
    is_within_root,
    symlink_components,
    validate_path,
)


def test_default_roots_are_home_and_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    roots = default_allowed_roots()
    assert Path.home() in roots
    assert tmp_path in roots


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX '/' root semantics")
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


def test_symlink_within_roots_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    escape_target = tmp_path / "escape_target.txt"
    escape_target.write_text("secret")
    link_dir = tmp_path / "linkdir"
    link_dir.symlink_to(tmp_path)  # symlink to an allowed directory
    # Lexically under cwd, but resolution stays under cwd here: allowed.
    assert validate_path(link_dir / "escape_target.txt") == normalize_path(
        link_dir / "escape_target.txt"
    )


def test_symlink_outside_roots_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    outside = Path("/tmp/fs-tool-safety-outside")
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("secret")
    link = tmp_path / "link.outside"
    link.symlink_to(outside)
    with pytest.raises(PathNotAllowedError):
        validate_path(link / "secret.txt")


def test_broken_symlink_is_reported_as_symlink(tmp_path: Path) -> None:
    link = tmp_path / "broken"
    link.symlink_to(tmp_path / "nonexistent")
    assert symlink_components(link) == [link]


def test_symlink_components_are_detected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "file.txt").write_text("x")
    link = tmp_path / "link"
    link.symlink_to(real)
    assert symlink_components(link / "file.txt") == [link]
