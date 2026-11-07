"""Generate README.md from docs/index.md.

Relative links in ``docs/index.md`` are written for the documentation tree.
README.md lives at the repository root, so links to files below ``docs/`` are
prefixed with ``docs/`` while external links and anchors are left unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

SOURCE = Path("docs/index.md")
DESTINATION = Path("README.md")
DOCS_DIR = Path("docs")
PREFIX = "<!-- This README.md is auto-generated from docs/index.md -->\n\n"

LINK_PATTERN = re.compile(r"\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "/", "docs/")


def rewrite_doc_links(content: str) -> str:
    """Prefix links to files below ``docs/`` so they resolve from the repo root."""

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        title = match.group(2) or ""
        if target.startswith(SKIP_PREFIXES):
            return match.group(0)

        path_part, separator, anchor = target.partition("#")
        if not path_part:
            return match.group(0)

        relative = path_part.removeprefix("./")
        if not (DOCS_DIR / relative).exists():
            return match.group(0)
        return f"](docs/{relative}{separator}{anchor}{title})"

    return LINK_PATTERN.sub(replace, content)


def main() -> None:
    """Regenerate README.md from docs/index.md."""
    source_content = SOURCE.read_text(encoding="utf-8")
    DESTINATION.write_text(
        PREFIX + rewrite_doc_links(source_content),
        encoding="utf-8",
    )
    print(f"Generated: {DESTINATION} updated from {SOURCE}")


if __name__ == "__main__":
    main()
