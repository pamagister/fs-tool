"""OOXML metadata and text provider (``.docx``, ``.xlsx``, ``.pptx``).

Extraction uses the standard library only (``zipfile`` and ``ElementTree``),
is read-only and never executes embedded content or macros. Format metadata
belongs to ``inspect info``; textual content belongs to ``inspect read``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.metadata import read_zip_member
from fs_tool.core.providers.base import Provider, capabilities_from_registry
from fs_tool.core.providers.content import ContentRead
from fs_tool.core.providers.document_text import extract_ooxml_text

_OOXML_EXTENSIONS = (".docx", ".xlsx", ".pptx")

# Namespaces for OOXML core.xml.
_OOXML_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}


class OoxmlProvider(Provider):
    """Provider for Office Open XML files."""

    _CAPABILITY_IDS = (CapabilityId.OOXML_METADATA, CapabilityId.OOXML_TEXT)

    @property
    def id(self) -> str:
        return "ooxml"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, self._CAPABILITY_IDS)

    def supported_extensions(self) -> tuple[str, ...]:
        return _OOXML_EXTENSIONS

    def metadata_capability(self) -> CapabilityId:
        return CapabilityId.OOXML_METADATA

    def content_capability(self) -> CapabilityId:
        return CapabilityId.OOXML_TEXT

    def read_content(self, path: Path, *, max_bytes: int) -> ContentRead:
        return extract_ooxml_text(path, max_bytes=max_bytes)

    def extract_metadata(self, path: Path) -> dict[str, Any] | None:
        try:
            with zipfile.ZipFile(path) as archive:
                try:
                    archive.getinfo("docProps/core.xml")
                except KeyError:
                    return None
                xml_text = read_zip_member(archive, "docProps/core.xml")
        except (zipfile.BadZipFile, OSError) as exc:
            raise FsToolError(
                "Cannot read OOXML metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if xml_text is None:
            raise FsToolError(
                "Cannot read OOXML metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise FsToolError(
                "Cannot parse OOXML metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        def find_text(local_name: str, prefix: str = "dc") -> str | None:
            ns = _OOXML_NS.get(prefix, "")
            element = root.find(f"{{{ns}}}{local_name}")
            return element.text if element is not None else None

        return {
            "author": find_text("creator"),
            "title": find_text("title"),
            "subject": find_text("subject"),
            "created": find_text("created", "dcterms"),
            "modified": find_text("modified", "dcterms"),
        }
