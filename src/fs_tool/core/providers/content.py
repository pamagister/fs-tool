"""Content-reading models and the bounded UTF-8 text reader.

Content reading stays independent of metadata extraction and structured
analysis (plan.md decisions D1 and D2). Providers that return a non-default
textual representation declare a content capability; every other regular file
falls back to the existing bounded UTF-8 text reader implemented here.

The result identifies both the source format and the returned representation,
never includes binary data and never substitutes analysis results for content.
Orchestration lives in :mod:`fs_tool.core.providers.inspection`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError

#: Representation identifier for bounded UTF-8 text.
TEXT_REPRESENTATION = "utf-8_text"
#: Representation identifier for text extracted from a PDF document.
PDF_TEXT_REPRESENTATION = "extracted_text"
#: Separator inserted between extracted PDF pages in the concatenated content.
PAGE_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class ContentPage:
    """One extracted page of textual content."""

    index: int
    content: str


@dataclass(frozen=True)
class ContentRead:
    """Bounded textual content returned by ``inspect read``."""

    content: str
    truncated: bool
    encoding: str
    format: str
    representation: str
    page_count: int | None = None
    pages: tuple[ContentPage, ...] = ()


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Return at most ``max_bytes`` bytes of ``text`` without splitting a character."""
    if max_bytes <= 0:
        return ""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def assemble_page_content(
    page_texts: list[str], max_bytes: int
) -> tuple[str, tuple[ContentPage, ...], bool]:
    """Join page texts with :data:`PAGE_SEPARATOR` under a UTF-8 byte limit.

    Page boundaries are preserved in the returned pages. When the limit falls
    inside a page, the last page contains only the returned portion and
    ``truncated`` is ``True``. If only empty page texts are lost, the content
    itself is complete and ``truncated`` stays ``False``.
    """
    parts: list[str] = []
    pages: list[ContentPage] = []
    used = 0
    for index, text in enumerate(page_texts, start=1):
        separator = PAGE_SEPARATOR if parts else ""
        candidate = separator + text
        candidate_size = len(candidate.encode("utf-8"))
        if used + candidate_size <= max_bytes:
            parts.append(candidate)
            pages.append(ContentPage(index=index, content=text))
            used += candidate_size
            continue

        remaining = max(0, max_bytes - used)
        partial = _truncate_utf8(candidate, remaining)
        partial_text = partial[len(separator) :] if partial.startswith(separator) else ""
        if partial_text:
            parts.append(separator + partial_text)
            pages.append(ContentPage(index=index, content=partial_text))
        truncated = any(later for later in page_texts[index - 1 :])
        return "".join(parts), tuple(pages), truncated

    return "".join(parts), tuple(pages), False


def read_text_content(path: Path, *, max_bytes: int) -> ContentRead:
    """Read bounded UTF-8 text, preserving the original ``inspect read`` behavior."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        raise FsToolError(
            f"Cannot read {path}: {exc.strerror or exc}",
            code=ErrorCode.ACCESS_DENIED,
            path=str(path),
        ) from exc

    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FsToolError(
            "File is not valid UTF-8 text (binary file).",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path),
        ) from exc

    return ContentRead(
        content=content,
        truncated=truncated,
        encoding="utf-8",
        format="text",
        representation=TEXT_REPRESENTATION,
    )
