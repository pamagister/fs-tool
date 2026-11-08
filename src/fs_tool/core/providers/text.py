"""Simple text-file structural analysis provider.

Reports inexpensive structure (line, word, paragraph and character counts)
without returning the actual text. Reading content belongs to
``inspect read`` (plan.md decisions D1 and D2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers.base import Provider, capabilities_from_registry

# Maximum file size for text analysis (5 MiB).
MAX_TEXT_ANALYSIS_SIZE = 5 * 1024 * 1024

_TEXT_EXTENSIONS = (".txt", ".text", ".log")


class TextProvider(Provider):
    """Provider for plain-text files."""

    @property
    def id(self) -> str:
        return "text"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, (CapabilityId.TEXT_STRUCTURE,))

    def supported_extensions(self) -> tuple[str, ...]:
        return _TEXT_EXTENSIONS

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        return (CapabilityId.TEXT_STRUCTURE,)

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        if capability is not CapabilityId.TEXT_STRUCTURE:
            raise NotImplementedError(f"text does not implement {capability.value}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise FsToolError(
                "Cannot read text file.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        if size > MAX_TEXT_ANALYSIS_SIZE:
            raise FsToolError(
                "Text file exceeds the analysis size limit.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FsToolError(
                "File is not valid UTF-8 text.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        lines = source.splitlines()
        paragraph_count = 0
        previous_blank = True
        for line in lines:
            is_blank = not line.strip()
            if not is_blank and previous_blank:
                paragraph_count += 1
            previous_blank = is_blank

        return {
            "encoding": "utf-8",
            "line_count": len(lines),
            "non_empty_line_count": sum(1 for line in lines if line.strip()),
            "word_count": len(source.split()),
            "character_count": len(source),
            "paragraph_count": paragraph_count,
            "max_line_length": max((len(line) for line in lines), default=0),
        }
