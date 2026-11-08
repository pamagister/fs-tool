"""Tests for the ``inspect info`` command (plan.md Phase 2, P2-T09..P2-T14)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_INCOMPLETE,
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    main,
)
from fs_tool.core.metadata import HAS_PYPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_FILES = PROJECT_ROOT / "res" / "example_filesystem_unstructured"


def argv_for(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "info", str(source), *extra]


def info_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_for(source, *extra))
    return code, json.loads(buffer.getvalue())


def test_info_json_shape_for_file(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world")
    code, data = info_json(file_path)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "inspect.info"
    assert data["complete"] is True
    assert data["errors"] == []
    result = data["result"]
    assert result["name"] == "note.txt"
    assert result["type"] == "file"
    assert result["extension"] == ".txt"
    assert result["size"] == 11
    assert Path(result["path"]).is_absolute()
    assert Path(result["path"]).resolve() == file_path.resolve()
    assert result["rel_path"] == "."
    assert result["modified"].endswith("+00:00")
    assert result["accessed"].endswith("+00:00")
    assert result["changed"].endswith("+00:00")
    assert result["mode"] is not None and result["mode"].startswith("-")
    assert result["mime_type"] == "text/plain"
    assert result["is_symlink"] is False
    assert result["target"] is None
    assert result["sha256"] is None
    assert result["metadata"] is None


def test_info_json_shape_for_directory(tmp_path: Path) -> None:
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    code, data = info_json(subdir)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    result = data["result"]
    assert result["name"] == "subdir"
    assert result["type"] == "directory"
    assert result["extension"] is None
    assert result["mode"] is not None and result["mode"].startswith("d")
    assert result["is_symlink"] is False


def test_info_symlink_information(tmp_path: Path) -> None:
    target = tmp_path / "info-symlink-target.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    code, data = info_json(link)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["type"] == "symlink"
    assert result["is_symlink"] is True
    recorded = result["target"]
    if recorded.startswith("\\\\?\\"):
        recorded = recorded[4:]
    assert recorded == str(target)


def test_info_outside_allowed_root(tmp_path: Path) -> None:
    code = main(["--allow-root", str(tmp_path), "inspect", "info", "/etc/hostname"])
    assert code == EXIT_ACCESS_DENIED


def test_info_missing_path_reports_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    code, data = info_json(missing)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["complete"] is False
    assert data["errors"]
    assert data["errors"][0]["path"] == str(missing)


def test_info_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello")
    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "info", str(file_path)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert f"path: {file_path}" in output
    assert "type: file" in output
    assert "size: 5" in output


def test_info_timestamps_are_utc(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello")
    code, data = info_json(file_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    for field in ("modified", "accessed", "changed"):
        assert result[field].endswith("+00:00"), f"{field} is not UTC: {result[field]}"


def test_info_owner_information(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("owner lookup is POSIX-only")
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello")
    code, data = info_json(file_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["owner"] is None or isinstance(result["owner"], str)


def test_info_mime_type(tmp_path: Path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_text("%PDF-1.4 dummy")
    code, data = info_json(pdf_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["mime_type"] == "application/pdf"


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_info_metadata_pdf() -> None:
    pdf_path = EXAMPLE_FILES / "Der Goldschatz partygame.pdf"
    assert pdf_path.is_file(), f"test fixture missing: {pdf_path}"
    code, data = info_json(pdf_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["metadata"] is not None
    metadata = result["metadata"]
    for key in ("author", "title", "subject", "created", "modified"):
        assert key in metadata, f"metadata missing key: {key}"
        assert metadata[key] is None or isinstance(metadata[key], str)
    assert result["metadata_result"]["capability"] == "pdf_metadata"
    assert result["metadata_result"]["status"] == "available"


def test_info_metadata_odf() -> None:
    odt_path = EXAMPLE_FILES / "Reise-Checkliste.odt"
    assert odt_path.is_file(), f"test fixture missing: {odt_path}"
    code, data = info_json(odt_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["metadata"] is not None
    metadata = result["metadata"]
    for key in ("author", "title", "subject", "created", "modified"):
        assert key in metadata, f"metadata missing key: {key}"
        assert metadata[key] is None or isinstance(metadata[key], str)
    assert metadata["author"] == "Paul L."
    assert metadata["title"] is None
    assert metadata["subject"] is None
    assert metadata["created"] == "2011-06-05T22:57:17.68"
    assert metadata["modified"] == "2011-06-08T12:58:03.17"
    assert result["metadata_result"]["capability"] == "odf_metadata"
    assert result["metadata_result"]["status"] == "available"


def test_info_metadata_ooxml() -> None:
    docx_path = EXAMPLE_FILES / "Auslandssemester.docx"
    assert docx_path.is_file(), f"test fixture missing: {docx_path}"
    code, data = info_json(docx_path)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["metadata"] is not None
    metadata = result["metadata"]
    for key in ("author", "title", "subject", "created", "modified"):
        assert key in metadata, f"metadata missing key: {key}"
        assert metadata[key] is None or isinstance(metadata[key], str)
    assert metadata["author"] == "Paul"
    assert metadata["title"] == "Allgemeine Hinweise"
    assert metadata["subject"] is None
    assert metadata["created"] == "2005-11-05T19:28:00Z"
    assert metadata["modified"] is not None
    assert result["metadata_result"]["capability"] == "ooxml_metadata"
    assert result["metadata_result"]["status"] == "available"


def test_info_metadata_compatibility_flag_matches_default() -> None:
    odt_path = EXAMPLE_FILES / "Reise-Checkliste.odt"
    assert odt_path.is_file(), f"test fixture missing: {odt_path}"
    code_default, data_default = info_json(odt_path)
    code_flag, data_flag = info_json(odt_path, "--metadata")
    assert code_default == code_flag == EXIT_SUCCESS
    assert data_default["result"] == data_flag["result"]


def test_info_metadata_unsupported_returns_none(tmp_path: Path) -> None:
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello")
    code, data = info_json(txt_path, "--metadata")
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["metadata"] is None
    assert result["metadata_result"] is None


def test_info_hash(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    content = b"hello world"
    file_path.write_bytes(content)

    code, data = info_json(file_path, "--hash")
    assert code == EXIT_SUCCESS
    assert data["result"]["sha256"] == hashlib.sha256(content).hexdigest()


def test_info_hash_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file_path = tmp_path / "note.txt"
    content = b"hello world"
    file_path.write_bytes(content)

    code = main(
        ["--allow-root", str(tmp_path), "--plain", "inspect", "info", str(file_path), "--hash"]
    )
    assert code == EXIT_SUCCESS
    assert f"sha256: {hashlib.sha256(content).hexdigest()}" in capsys.readouterr().out


def test_info_hash_failure_is_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello")
    monkeypatch.setattr("fs_tool.cli.sha256_of_file", lambda path: None)

    code, data = info_json(file_path, "--hash")
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert data["result"]["sha256"] is None
    assert data["errors"][0]["code"] == "INCOMPLETE_SCAN"


def test_info_hash_directory_has_no_hash(tmp_path: Path) -> None:
    directory = tmp_path / "subdir"
    directory.mkdir()

    code, data = info_json(directory, "--hash")
    assert code == EXIT_SUCCESS
    assert data["result"]["sha256"] is None


def test_metadata_rejects_oversized_zip_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    odt_path = tmp_path / "oversized.odt"
    with zipfile.ZipFile(odt_path, "w") as archive:
        archive.writestr("meta.xml", "<meta>" + ("x" * 512) + "</meta>")
    monkeypatch.setattr("fs_tool.core.metadata.MAX_ZIP_MEMBER_SIZE", 32)

    code, data = info_json(odt_path, "--metadata")
    assert code == EXIT_SUCCESS
    assert data["result"]["metadata"] is None
    assert data["result"]["metadata_result"]["status"] == "failed"
    assert data["result"]["metadata_result"]["error_code"] == "CAPABILITY_FAILED"
