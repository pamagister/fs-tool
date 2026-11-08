"""PDF metadata, page-structure and text-reading provider.

Metadata extraction belongs to ``inspect info`` and page structure to
``inspect analyze``. Text extraction belongs to ``inspect read`` and is kept
separate from both (plan.md decisions D1 and D2). All three use the optional
``pypdf`` dependency and respect bounded output limits.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.metadata import HAS_PYPDF, MAX_METADATA_SIZE, parse_pdf_date
from fs_tool.core.providers.base import Provider, capabilities_from_registry
from fs_tool.core.providers.content import (
    PDF_TEXT_REPRESENTATION,
    ContentRead,
    assemble_page_content,
)

# Maximum PDF size accepted for text extraction. Parsing a PDF requires
# reading the complete document, so the source itself is bounded as well.
MAX_PDF_SOURCE_SIZE = MAX_METADATA_SIZE


def _text(value: object) -> str | None:
    """Return ``value`` as text when it is a string-like PDF value."""
    return str(value) if isinstance(value, str) else None


class PdfProvider(Provider):
    """Provider for PDF files."""

    _CAPABILITY_IDS = (
        CapabilityId.PDF_METADATA,
        CapabilityId.PDF_PAGES,
        CapabilityId.PDF_TEXT,
    )

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

    def content_capability(self) -> CapabilityId:
        return CapabilityId.PDF_TEXT

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

    def read_content(self, path: Path, *, max_bytes: int) -> ContentRead:
        if not HAS_PYPDF:
            raise FsToolError(
                "PDF text extraction requires the optional pypdf package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        try:
            source_size = path.stat().st_size
        except OSError as exc:
            raise FsToolError(
                "Cannot read PDF file.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if source_size > MAX_PDF_SOURCE_SIZE:
            raise FsToolError(
                "PDF exceeds the text-extraction source size limit.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
        try:
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(str(path))
            page_texts: list[str] = []
            for page in reader.pages:
                extracted = page.extract_text()
                page_texts.append(extracted if isinstance(extracted, str) else "")
        except Exception as exc:
            raise FsToolError(
                "Cannot extract PDF text.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        content, pages, truncated = assemble_page_content(page_texts, max_bytes)
        return ContentRead(
            content=content,
            truncated=truncated,
            encoding="utf-8",
            format="pdf",
            representation=PDF_TEXT_REPRESENTATION,
            page_count=len(page_texts),
            pages=pages,
        )

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
