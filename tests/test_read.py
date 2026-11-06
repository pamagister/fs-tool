"""Tests for the ``inspect read`` command (plan.md Phase 2, P2-T21..P2-T24)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_ACCESS_DENIED, EXIT_INVALID_ARGS, EXIT_SUCCESS, main


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "read", str(source), *extra]


def read_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def test_read_json_shape(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    content = "hello world\n"
    file_path.write_bytes(content.encode("utf-8"))
    code, data = read_json(file_path)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "inspect.read"
    assert data["complete"] is True
    result = data["result"]
    assert result["path"] == str(file_path)
    assert result["name"] == "notes.txt"
    assert result["size"] == len(content)
    assert result["content"] == content
    assert result["truncated"] is False
    assert result["encoding"] == "utf-8"


def test_read_truncation(tmp_path: Path) -> None:
    file_path = tmp_path / "long.txt"
    content = "x" * 200
    file_path.write_text(content)
    code, data = read_json(file_path, "--max-bytes", "100")
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["content"] == "x" * 100
    assert result["truncated"] is True
    assert result["size"] == 200


def test_read_symlink_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    code, data = read_json(link)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"
    assert "symbolic link" in data["errors"][0]["message"]


def test_read_binary_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "binary.bin"
    file_path.write_bytes(bytes(range(256)))
    code, data = read_json(file_path)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "binary" in data["errors"][0]["message"].lower()


def test_read_directory_rejected(tmp_path: Path) -> None:
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    code, data = read_json(subdir)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert "non-regular" in data["errors"][0]["message"]


def test_read_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "inspect", "read", "/etc/hostname"])
    assert code == EXIT_ACCESS_DENIED


def test_read_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    code, data = read_json(missing)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["complete"] is False


def test_read_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file_path = tmp_path / "notes.txt"
    content = "hello\n"
    file_path.write_text(content)
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "read", str(file_path)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert output.rstrip("\r\n") == content.rstrip("\r\n")


def test_read_plain_truncation_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file_path = tmp_path / "long.txt"
    file_path.write_text("x" * 200)
    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "inspect",
            "read",
            str(file_path),
            "--max-bytes",
            "100",
        ]
    )
    assert code == EXIT_SUCCESS
    err = capsys.readouterr().err
    assert "truncated" in err.lower()


def test_read_utf8_content(tmp_path: Path) -> None:
    file_path = tmp_path / "unicode.txt"
    content = "Héllo Wörld 🌍\n"
    file_path.write_bytes(content.encode("utf-8"))
    code, data = read_json(file_path)
    assert code == EXIT_SUCCESS
    assert data["result"]["content"] == content
