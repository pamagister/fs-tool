"""PDF metadata and page-structure provider.

Metadata extraction belongs to ``inspect info``; page structure belongs to
``inspect analyze``. Both use the optional ``pypdf`` dependency. The provider
never extracts full text here: that responsibility belongs to ``inspect read``
(plan.md decisions D1 and D2).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.metadata import HAS_PYPDF, parse_pdf_date
from fs_tool.core.providers.base import Provider, capabilities_from_registry


def _text(value: object) -> str | None:
    """Return ``value`` as text when it is a string-like PDF value."""
    return str(value) if isinstance(value, str) else None


class PdfProvider(Provider):
    """Provider for PDF files."""

    _CAPABILITY_IDS = (CapabilityId.PDF_METADATA, CapabilityId.PDF_PAGES)

    @property
    def id(self) -> str:
        return "pdf"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, self._CAPABILITY_IDS)

    def supported_extensions(self) -> tuple[str, ...]:
        return (".pdf",)

    def metadata_capability(self) -> CapabilityId:
        return CapabilityId.PDF_METADATA

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        return (CapabilityId.PDF_PAGES,)

    def extract_metadata(self, path: Path) -> dict[str, Any] | None:
        if not HAS_PYPDF:
            raise FsToolError(
                "PDF metadata extraction requires the optional pypdf package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        try:
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(str(path))
            info = reader.metadata
        except Exception as exc:
            raise FsToolError(
                "Cannot read PDF metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if info is None:
            return None

        creation_date = info.get("/CreationDate")
        mod_date = info.get("/ModDate")
        return {
            "author": _text(info.get("/Author")),
            "title": _text(info.get("/Title")),
            "subject": _text(info.get("/Subject")),
            "created": parse_pdf_date(creation_date) if isinstance(creation_date, str) else None,
            "modified": parse_pdf_date(mod_date) if isinstance(mod_date, str) else None,
        }

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        if capability is not CapabilityId.PDF_PAGES:
            raise NotImplementedError(f"pdf does not implement {capability.value}")
        if not HAS_PYPDF:
            raise FsToolError(
                "PDF page analysis requires the optional pypdf package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        try:
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(str(path))
            pages = [self._page_dict(index, page) for index, page in enumerate(reader.pages, 1)]
        except Exception as exc:
            raise FsToolError(
                "Cannot read PDF page structure.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        return {"page_count": len(pages), "pages": pages}

    @staticmethod
    def _page_dict(index: int, page: Any) -> dict[str, Any]:
        box = page.mediabox
        width = round(float(box.width), 3)
        height = round(float(box.height), 3)
        if width > height:
            orientation = "landscape"
        elif width < height:
            orientation = "portrait"
        else:
            orientation = "square"
        try:
            rotation = int(page.get("/Rotate", 0) or 0)
        except (TypeError, ValueError):
            rotation = 0
        return {
            "index": index,
            "width": width,
            "height": height,
            "orientation": orientation,
            "rotation": rotation,
        }
