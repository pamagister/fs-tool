"""ODF metadata provider (``.odt``, ``.ods``, ``.odp``, ``.odg``).

Extraction uses the standard library only (``zipfile`` and ``ElementTree``),
is read-only and never executes embedded content or macros. Format metadata
belongs to ``inspect info`` (plan.md decision D2).
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

_ODF_EXTENSIONS = (".odt", ".ods", ".odp", ".odg")

# Namespaces for ODF meta.xml.
_ODF_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
}


class OdfProvider(Provider):
    """Provider for OpenDocument Format files."""

    @property
    def id(self) -> str:
        return "odf"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, (CapabilityId.ODF_METADATA,))

    def supported_extensions(self) -> tuple[str, ...]:
        return _ODF_EXTENSIONS

    def metadata_capability(self) -> CapabilityId:
        return CapabilityId.ODF_METADATA

    def extract_metadata(self, path: Path) -> dict[str, Any] | None:
        try:
            with zipfile.ZipFile(path) as archive:
                try:
                    archive.getinfo("meta.xml")
                except KeyError:
                    return None
                xml_text = read_zip_member(archive, "meta.xml")
        except (zipfile.BadZipFile, OSError) as exc:
            raise FsToolError(
                "Cannot read ODF metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if xml_text is None:
            raise FsToolError(
                "Cannot read ODF metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise FsToolError(
                "Cannot parse ODF metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        def find_text(local_name: str, prefix: str = "dc") -> str | None:
            ns = _ODF_NS.get(prefix, "")
            element = root.find(f".//{{{ns}}}{local_name}")
            return element.text if element is not None and element.text else None

        # ODF stores bibliographic fields (dc:creator, dc:title, dc:subject)
        # and system dates (meta:creation-date, dc:date) below office:meta.
        # Use a descendant search because the root element is
        # office:document-meta.
        return {
            "author": find_text("creator") or find_text("initial-creator", "meta"),
            "title": find_text("title"),
            "subject": find_text("subject"),
            "created": find_text("creation-date", "meta"),
            "modified": find_text("date") or find_text("modification-date", "meta"),
        }
