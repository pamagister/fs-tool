"""Tests for the ``inspect read`` command (plan.md Phase 3).

Covers bounded UTF-8 text reading and PDF text extraction, page boundaries,
consistent content metadata, explicit missing-dependency reporting and the
existing read safety restrictions.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_FAILURE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)
from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.metadata import HAS_PYPDF
from fs_tool.core.providers.content import assemble_page_content

EXAMPLE_PDF = Path(__file__).resolve().parent / "example_pdf.pdf"


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
    assert result["format"] == "text"
    assert result["representation"] == "utf-8_text"
    assert "pages" not in result


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


def test_read_negative_max_bytes_is_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello\n", encoding="utf-8")
    code, data = read_json(file_path, "--max-bytes", "-1")
    assert code == EXIT_INVALID_ARGS
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_read_pdf_extracts_text() -> None:
    assert EXAMPLE_PDF.is_file(), f"test fixture missing: {EXAMPLE_PDF}"

    code, data = read_json(EXAMPLE_PDF)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["complete"] is True
    result = data["result"]
    assert result["path"] == str(EXAMPLE_PDF)
    assert result["name"] == "example_pdf.pdf"
    assert result["format"] == "pdf"
    assert result["representation"] == "extracted_text"
    assert result["encoding"] == "utf-8"
    assert result["truncated"] is False
    assert "This is an example PDF file." in result["content"]
    assert "this is a chapter heading" in result["content"]
    assert result["page_count"] == 1
    assert len(result["pages"]) == 1
    assert result["pages"][0]["index"] == 1
    assert result["pages"][0]["content"] in result["content"]


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_read_pdf_truncates_extracted_text() -> None:
    code, data = read_json(EXAMPLE_PDF, "--max-bytes", "20")
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["truncated"] is True
    assert result["content"]
    assert len(result["content"].encode("utf-8")) <= 20
    assert len(result["pages"]) == 1
    assert result["pages"][0]["content"] in result["content"]


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_read_pdf_invalid_document_reports_failure(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.4\nnot a real document\n")

    code, data = read_json(source)
    assert code == EXIT_FAILURE
    assert data["success"] is False
    assert data["errors"][0]["code"] == "CAPABILITY_FAILED"
    assert "PDF" in data["errors"][0]["message"]


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_read_pdf_source_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("fs_tool.core.providers.pdf.MAX_PDF_SOURCE_SIZE", 0)

    code, data = read_json(EXAMPLE_PDF)
    assert code == EXIT_FAILURE
    assert data["errors"][0]["code"] == "CAPABILITY_FAILED"
    assert "size limit" in data["errors"][0]["message"]


def test_read_pdf_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original = AvailabilityChecker.python_package_available

    def fake_available(name: str) -> bool:
        if name == "pypdf":
            return False
        return original(name)

    monkeypatch.setattr(
        AvailabilityChecker, "python_package_available", staticmethod(fake_available)
    )

    code, data = read_json(EXAMPLE_PDF)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["complete"] is False
    assert data["errors"][0]["code"] == "CAPABILITY_UNAVAILABLE"
    assert "pypdf" in data["errors"][0]["message"]
    assert "fs-tool capabilities" in data["errors"][0]["message"]


def test_assemble_page_content_preserves_boundaries() -> None:
    content, pages, truncated = assemble_page_content(["first", "second"], 100)
    assert content == "first\n\nsecond"
    assert [page.index for page in pages] == [1, 2]
    assert [page.content for page in pages] == ["first", "second"]
    assert truncated is False


def test_assemble_page_content_truncates_within_a_page() -> None:
    content, pages, truncated = assemble_page_content(["first", "second"], 8)
    assert content == "first\n\ns"
    assert len(content.encode("utf-8")) == 8
    assert [page.index for page in pages] == [1, 2]
    assert [page.content for page in pages] == ["first", "s"]
    assert truncated is True


def test_assemble_page_content_does_not_split_utf8_characters() -> None:
    content, _, truncated = assemble_page_content(["Grüße"], 3)
    assert content == "Gr"
    assert truncated is True
