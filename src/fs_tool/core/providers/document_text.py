"""Bounded text extraction from ODF and OOXML ZIP containers.

The implementation uses only the standard library. It reads a small set of XML
parts, extracts text nodes, and never executes macros or embedded objects.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.metadata import MAX_METADATA_SIZE, MAX_ZIP_MEMBER_SIZE
from fs_tool.core.providers.content import EXTRACTED_TEXT_REPRESENTATION, ContentRead

_TEXT_MEMBER_LIMIT = MAX_ZIP_MEMBER_SIZE


def _local_name(tag: object) -> str:
    """Return an XML local name without its namespace."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _read_member(
    archive: zipfile.ZipFile,
    name: str,
    *,
    label: str,
    required: bool = True,
) -> bytes | None:
    """Read one ZIP member under the text-extraction size limit."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise FsToolError(
                f"Cannot extract {label} text: archive does not contain {name}.",
                code=ErrorCode.CAPABILITY_FAILED,
            ) from None
        return None
    if info.flag_bits & 0x1:
        raise FsToolError(
            f"Cannot extract {label} text: {name} is encrypted.",
            code=ErrorCode.CAPABILITY_FAILED,
        )
    if info.file_size > _TEXT_MEMBER_LIMIT:
        raise FsToolError(
            f"Cannot extract {label} text: {name} exceeds the "
            f"{_TEXT_MEMBER_LIMIT}-byte member limit.",
            code=ErrorCode.CAPABILITY_FAILED,
        )
    try:
        data = archive.read(name)
    except RuntimeError as exc:
        raise FsToolError(
            f"Cannot extract {label} text: {name} is encrypted or unreadable.",
            code=ErrorCode.CAPABILITY_FAILED,
        ) from exc
    except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
        raise FsToolError(
            f"Cannot extract {label} text from {name}.",
            code=ErrorCode.CAPABILITY_FAILED,
        ) from exc
    if len(data) > _TEXT_MEMBER_LIMIT:
        raise FsToolError(
            f"Cannot extract {label} text: {name} exceeds the "
            f"{_TEXT_MEMBER_LIMIT}-byte member limit.",
            code=ErrorCode.CAPABILITY_FAILED,
        )
    return data


def _parse_xml(data: bytes, *, label: str) -> ElementTree.Element:
    """Parse XML or raise a structured capability error."""
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise FsToolError(
            f"Cannot parse {label} XML.",
            code=ErrorCode.CAPABILITY_FAILED,
        ) from exc


def _clean(text: str) -> str:
    """Normalize whitespace within one extracted text block."""
    return " ".join(text.split())


def _content_read(text: str, max_bytes: int, *, format_name: str) -> ContentRead:
    """Return a bounded ContentRead for extracted text."""
    original = text
    encoded = original.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if max_bytes <= 0:
        content = ""
    else:
        content = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return ContentRead(
        content=content,
        truncated=truncated,
        encoding="utf-8",
        format=format_name,
        representation=EXTRACTED_TEXT_REPRESENTATION,
    )


def extract_odf_text(path: Path, *, max_bytes: int) -> ContentRead:
    """Extract text from the body of an ODF ``content.xml``."""
    try:
        source_size = path.stat().st_size
    except OSError as exc:
        raise FsToolError(
            "Cannot read ODF file.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        ) from exc
    if source_size > MAX_METADATA_SIZE:
        raise FsToolError(
            "ODF file exceeds the text-extraction source size limit.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        )

    try:
        with zipfile.ZipFile(path) as archive:
            data = _read_member(archive, "content.xml", label="ODF")
    except FsToolError:
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        raise FsToolError(
            "Cannot read ODF text.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        ) from exc
    if data is None:
        raise FsToolError(
            "Cannot extract ODF text: archive does not contain content.xml.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        )

    root = _parse_xml(data, label="ODF")
    body = next((item for item in root.iter() if _local_name(item.tag) == "body"), root)
    blocks: list[str] = []
    for item in body.iter():
        if _local_name(item.tag) in {"p", "h"}:
            text = _clean("".join(item.itertext()))
            if text:
                blocks.append(text)
    if not blocks:
        text = _clean("".join(body.itertext()))
        if text:
            blocks.append(text)
    return _content_read("\n".join(blocks), max_bytes, format_name="odf")


def _natural_key(name: str) -> tuple[object, ...]:
    """Sort names such as slide2 before slide10."""
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name))


def _docx_text(archive: zipfile.ZipFile) -> str:
    """Extract paragraphs from a Word document."""
    data = _read_member(archive, "word/document.xml", label="OOXML")
    assert data is not None
    root = _parse_xml(data, label="OOXML")
    blocks: list[str] = []
    for item in root.iter():
        if _local_name(item.tag) != "p":
            continue
        parts: list[str] = []
        for node in item.iter():
            local = _local_name(node.tag)
            if local == "t":
                parts.append(node.text or "")
            elif local == "tab":
                parts.append("\t")
            elif local == "br":
                parts.append("\n")
        text = _clean("".join(parts))
        if text:
            blocks.append(text)
    return "\n".join(blocks)


def _xlsx_text(archive: zipfile.ZipFile) -> str:
    """Extract shared and inline strings from a spreadsheet."""
    blocks: list[str] = []
    shared = _read_member(archive, "xl/sharedStrings.xml", label="OOXML", required=False)
    if shared is not None:
        root = _parse_xml(shared, label="OOXML")
        for item in root.iter():
            if _local_name(item.tag) != "si":
                continue
            text = _clean(
                "".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t")
            )
            if text:
                blocks.append(text)

    worksheet_names = sorted(
        (
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/")
            and name.endswith(".xml")
            and not name.endswith("_rels")
        ),
        key=_natural_key,
    )
    for name in worksheet_names:
        data = _read_member(archive, name, label="OOXML")
        assert data is not None
        root = _parse_xml(data, label="OOXML")
        for cell in root.iter():
            if _local_name(cell.tag) != "c":
                continue
            parts: list[str] = []
            for node in cell.iter():
                local = _local_name(node.tag)
                if local == "t":
                    parts.append(node.text or "")
                elif local == "v" and cell.get("t") != "s":
                    parts.append(node.text or "")
            text = _clean("".join(parts))
            if text:
                blocks.append(text)
    return "\n".join(blocks)


def _pptx_text(archive: zipfile.ZipFile) -> str:
    """Extract paragraph text from presentation slides."""
    slide_names = sorted(
        (
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ),
        key=_natural_key,
    )
    blocks: list[str] = []
    for name in slide_names:
        data = _read_member(archive, name, label="OOXML")
        assert data is not None
        root = _parse_xml(data, label="OOXML")
        for item in root.iter():
            if _local_name(item.tag) != "p":
                continue
            text = _clean(
                "".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t")
            )
            if text:
                blocks.append(text)
    return "\n".join(blocks)


def extract_ooxml_text(path: Path, *, max_bytes: int) -> ContentRead:
    """Extract text from a Word, Excel or PowerPoint OOXML container."""
    try:
        source_size = path.stat().st_size
    except OSError as exc:
        raise FsToolError(
            "Cannot read OOXML file.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        ) from exc
    if source_size > MAX_METADATA_SIZE:
        raise FsToolError(
            "OOXML file exceeds the text-extraction source size limit.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        )

    try:
        with zipfile.ZipFile(path) as archive:
            if path.suffix.lower() == ".docx":
                text = _docx_text(archive)
            elif path.suffix.lower() == ".xlsx":
                text = _xlsx_text(archive)
            elif path.suffix.lower() == ".pptx":
                text = _pptx_text(archive)
            else:
                raise FsToolError(
                    "Unsupported OOXML extension.",
                    code=ErrorCode.CAPABILITY_FAILED,
                    path=str(path),
                )
    except FsToolError:
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        raise FsToolError(
            "Cannot read OOXML text.",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        ) from exc
    return _content_read(text, max_bytes, format_name="ooxml")
