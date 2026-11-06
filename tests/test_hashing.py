"""Tests for SHA-256 hashing (plan.md Phase 1, P1-T09)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from fs_tool.core.hashing import sha256_of_file

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_of_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    assert sha256_of_file(path) == EMPTY_SHA256


def test_sha256_of_file_matches_hashlib(tmp_path: Path) -> None:
    content = b"fs-tool deterministic hashing test"
    path = tmp_path / "data.bin"
    path.write_bytes(content)
    assert sha256_of_file(path) == hashlib.sha256(content).hexdigest()


def test_sha256_large_file_is_chunked(tmp_path: Path) -> None:
    content = b"x" * (3 * 1024 * 1024 + 123)
    path = tmp_path / "large.bin"
    path.write_bytes(content)
    assert sha256_of_file(path) == hashlib.sha256(content).hexdigest()


def test_sha256_of_nonexistent_file(tmp_path: Path) -> None:
    assert sha256_of_file(tmp_path / "missing") is None


def test_sha256_of_symlink_is_none(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    assert sha256_of_file(link) is None


def test_sha256_of_symlink_to_nonexistent_is_none(tmp_path: Path) -> None:
    link = tmp_path / "broken-link"
    link.symlink_to(tmp_path / "does-not-exist")
    assert sha256_of_file(link) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo not available")
def test_sha256_of_special_file_is_none(tmp_path: Path) -> None:
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    assert sha256_of_file(pipe) is None


def test_sha256_distinguishes_different_contents(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("aaa")
    b.write_text("bbb")
    assert sha256_of_file(a) != sha256_of_file(b)


def test_sha256_rejects_path_replaced_after_lstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"content")
    # Simulate the path being replaced by a directory between lstat and open.
    monkeypatch.setattr("fs_tool.core.hashing.os.fstat", lambda fd: tmp_path.stat())
    assert sha256_of_file(path) is None


def test_sha256_identical_contents_same_digest(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same content")
    b.write_text("same content")
    assert sha256_of_file(a) == sha256_of_file(b)
