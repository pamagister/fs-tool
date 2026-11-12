"""Tests for bounded ODF and OOXML text extraction through ``inspect read``."""

from __future__ import annotations

import io
import json
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from fs_tool.cli import EXIT_FAILURE, EXIT_SUCCESS, main

EXAMPLE_ODT = (
    Path(__file__).resolve().parent.parent
    / "res/example_filesystem_unstructured/Reise-Checkliste.odt"
)
EXAMPLE_DOCX = (
    Path(__file__).resolve().parent.parent
    / "res/example_filesystem_unstructured/Auslandssemester.docx"
)


def read_json(path: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(
            [
                "--allow-root",
                str(path.parent),
                "inspect",
                "read",
                str(path),
                *extra,
            ]
        )
    return code, json.loads(output.getvalue())


def make_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_read_odt_extracts_text(tmp_path: Path) -> None:
    path = make_zip(
        tmp_path / "notes.odt",
        {
            "content.xml": """
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <text:h>Heading</text:h>
    <text:p>Hello <text:span>world</text:span></text:p>
  </office:body>
</office:document-content>
"""
        },
    )

    code, data = read_json(path)

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["format"] == "odf"
    assert result["representation"] == "extracted_text"
    assert result["encoding"] == "utf-8"
    assert result["content"] == "Heading\nHello world"
    assert result["truncated"] is False


def test_read_odt_truncates_without_splitting_utf8(tmp_path: Path) -> None:
    path = make_zip(
        tmp_path / "notes.odt",
        {
            "content.xml": """
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><text:p>Héllo</text:p></office:body>
</office:document-content>
"""
        },
    )

    code, data = read_json(path, "--max-bytes", "2")

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["content"] == "H"
    assert result["truncated"] is True


def test_read_example_odt() -> None:
    assert EXAMPLE_ODT.is_file()

    code, data = read_json(EXAMPLE_ODT)

    assert code == EXIT_SUCCESS
    assert data["result"]["format"] == "odf"
    assert data["result"]["content"].strip()


def test_read_odt_malformed_container(tmp_path: Path) -> None:
    path = tmp_path / "broken.odt"
    path.write_bytes(b"not a zip")

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert data["errors"][0]["code"] == "CAPABILITY_FAILED"


def test_read_odt_missing_content_xml(tmp_path: Path) -> None:
    path = make_zip(tmp_path / "empty.odt", {"other.txt": "text"})

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert "content.xml" in data["errors"][0]["message"]


def test_read_odt_rejects_oversized_member(tmp_path: Path, monkeypatch: Any) -> None:
    import fs_tool.core.providers.document_text as document_text

    path = make_zip(
        tmp_path / "large.odt",
        {
            "content.xml": """
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><text:p>This text is longer than the test limit.</text:p></office:body>
</office:document-content>
"""
        },
    )
    monkeypatch.setattr(document_text, "_TEXT_MEMBER_LIMIT", 20)

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert "member limit" in data["errors"][0]["message"]


def test_read_odt_rejects_encrypted_member(tmp_path: Path, monkeypatch: Any) -> None:
    path = make_zip(
        tmp_path / "encrypted.odt",
        {"content.xml": "<office:document-content/>"},
    )
    real_getinfo = zipfile.ZipFile.getinfo

    def mark_encrypted(archive: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
        info = real_getinfo(archive, name)
        info.flag_bits |= 0x1
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", mark_encrypted)

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert "encrypted" in data["errors"][0]["message"].lower()


def test_read_docx_extracts_paragraphs(tmp_path: Path) -> None:
    path = make_zip(
        tmp_path / "document.docx",
        {
            "word/document.xml": """
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>
    <w:p><w:r><w:t>Second</w:t></w:r><w:r><w:t> paragraph</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
        },
    )

    code, data = read_json(path)

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["format"] == "ooxml"
    assert result["representation"] == "extracted_text"
    assert result["content"] == "First paragraph\nSecond paragraph"


def test_read_xlsx_extracts_shared_and_inline_strings(tmp_path: Path) -> None:
    path = make_zip(
        tmp_path / "sheet.xlsx",
        {
            "xl/sharedStrings.xml": """
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>Shared label</t></si>
</sst>
""",
            "xl/worksheets/sheet1.xml": """
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row><c t="inlineStr"><is><t>Inline value</t></is></c></row>
  </sheetData>
</worksheet>
""",
        },
    )

    code, data = read_json(path)

    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["format"] == "ooxml"
    assert result["content"] == "Shared label\nInline value"


def test_read_pptx_extracts_slides_in_natural_order(tmp_path: Path) -> None:
    path = make_zip(
        tmp_path / "deck.pptx",
        {
            "ppt/slides/slide10.xml": """
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <a:p><a:t>Tenth</a:t></a:p>
</p:sld>
""",
            "ppt/slides/slide2.xml": """
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <a:p><a:t>Second</a:t></a:p>
</p:sld>
""",
            "ppt/slides/slide1.xml": """
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <a:p><a:t>First</a:t></a:p>
</p:sld>
""",
        },
    )

    code, data = read_json(path)

    assert code == EXIT_SUCCESS
    assert data["result"]["content"] == "First\nSecond\nTenth"


def test_read_example_docx() -> None:
    assert EXAMPLE_DOCX.is_file()

    code, data = read_json(EXAMPLE_DOCX)

    assert code == EXIT_SUCCESS
    assert data["result"]["format"] == "ooxml"
    assert data["result"]["content"].strip()


def test_read_ooxml_malformed_container(tmp_path: Path) -> None:
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert data["errors"][0]["code"] == "CAPABILITY_FAILED"


def test_read_docx_missing_document_part(tmp_path: Path) -> None:
    path = make_zip(tmp_path / "empty.docx", {"other.xml": "<x/>"})

    code, data = read_json(path)

    assert code == EXIT_FAILURE
    assert "word/document.xml" in data["errors"][0]["message"]
