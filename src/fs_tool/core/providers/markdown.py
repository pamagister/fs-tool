"""Markdown structural analysis provider.

Extracts heading hierarchy and simple document structure from Markdown source
without returning the document text. Headings inside fenced code blocks are
ignored. Analysis belongs to ``inspect analyze`` (plan.md decision D2).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers.base import Provider, capabilities_from_registry

# Maximum file size for Markdown analysis (5 MiB).
MAX_MARKDOWN_ANALYSIS_SIZE = 5 * 1024 * 1024

_MARKDOWN_EXTENSIONS = (".md", ".markdown")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")


class MarkdownProvider(Provider):
    """Provider for Markdown documents."""

    @property
    def id(self) -> str:
        return "markdown"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, (CapabilityId.MARKDOWN_STRUCTURE,))

    def supported_extensions(self) -> tuple[str, ...]:
        return _MARKDOWN_EXTENSIONS

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        return (CapabilityId.MARKDOWN_STRUCTURE,)

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        if capability is not CapabilityId.MARKDOWN_STRUCTURE:
            raise NotImplementedError(f"markdown does not implement {capability.value}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise FsToolError(
                "Cannot read Markdown file.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if size > MAX_MARKDOWN_ANALYSIS_SIZE:
            raise FsToolError(
                "Markdown file exceeds the analysis size limit.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FsToolError(
                "Markdown file is not valid UTF-8 text.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        lines = source.splitlines()
        headings: list[dict[str, Any]] = []
        fence_marker: str | None = None
        for line_number, line in enumerate(lines, start=1):
            fence_match = _FENCE_RE.match(line)
            if fence_match:
                marker = fence_match.group(1)[0]
                if fence_marker is None:
                    fence_marker = marker
                elif fence_marker == marker:
                    fence_marker = None
                continue
            if fence_marker is not None:
                continue
            heading_match = _HEADING_RE.match(line.strip())
            if heading_match:
                headings.append(
                    {
                        "level": len(heading_match.group(1)),
                        "text": heading_match.group(2),
                        "line": line_number,
                    }
                )

        max_level = max((heading["level"] for heading in headings), default=0)
        return {
            "line_count": len(lines),
            "heading_count": len(headings),
            "max_heading_level": max_level,
            "headings": headings,
        }
