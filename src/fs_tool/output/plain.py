"""Plain-text presentation (plan.md section 10.2).

Terminal output is optional and never influences filesystem operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import CapabilityResult, CapabilityStatus
from fs_tool.core.models import EntryType, FilesystemEntry


def render_tree(entries: list[FilesystemEntry], root: Path) -> str:
    """Render traversal entries as a plain-text tree rooted at ``root``.

    Entries must be ordered as produced by the traversal (pre-order,
    siblings sorted by name).
    """

    def parts_of(entry: FilesystemEntry) -> tuple[str, ...]:
        assert entry.rel_path is not None
        return Path(entry.rel_path).parts

    def parent_of(entry: FilesystemEntry) -> tuple[str, ...]:
        return parts_of(entry)[:-1]

    def depth_of(entry: FilesystemEntry) -> int:
        return len(parts_of(entry))

    def is_last(index: int) -> bool:
        entry = entries[index]
        parent = parent_of(entry)
        depth = depth_of(entry)
        for later in entries[index + 1 :]:
            later_parts = parts_of(later)
            if len(later_parts) == depth and later_parts[:-1] == parent:
                return False  # a sibling follows
            if len(later_parts) <= len(parent):
                return True  # moved past this entry's subtree
        return True

    root_name = root.name or str(root)
    lines = [f"{root_name}/"]
    stack: list[bool] = []  # is_last flag of each ancestor level

    for index, entry in enumerate(entries):
        depth = depth_of(entry)
        while len(stack) > depth - 1:
            stack.pop()
        prefix = "".join("    " if was_last else "│   " for was_last in stack)
        connector = "└── " if is_last(index) else "├── "
        marker = "/" if entry.type == EntryType.DIRECTORY else ""
        if entry.is_symlink and entry.target:
            marker += f" -> {entry.target}"
        lines.append(f"{prefix}{connector}{entry.name}{marker}")
        stack.append(is_last(index))

    return "\n".join(lines)


def render_info(
    entry: FilesystemEntry,
    metadata_result: CapabilityResult | None = None,
) -> str:
    """Render a single entry's metadata as plain-text key-value pairs."""
    lines: list[str] = [
        f"path: {entry.path}",
        f"name: {entry.name}",
        f"type: {entry.type.value}",
    ]
    if entry.rel_path is not None:
        lines.append(f"rel_path: {entry.rel_path}")
    if entry.extension is not None:
        lines.append(f"extension: {entry.extension}")
    if entry.size is not None:
        lines.append(f"size: {entry.size}")
    if entry.modified is not None:
        lines.append(f"modified: {entry.modified}")
    if entry.created is not None:
        lines.append(f"created: {entry.created}")
    if entry.accessed is not None:
        lines.append(f"accessed: {entry.accessed}")
    if entry.changed is not None:
        lines.append(f"changed: {entry.changed}")
    if entry.mode is not None:
        lines.append(f"mode: {entry.mode}")
    if entry.owner is not None:
        lines.append(f"owner: {entry.owner}")
    if entry.mime_type is not None:
        lines.append(f"mime_type: {entry.mime_type}")
    if entry.is_symlink:
        lines.append(f"is_symlink: {entry.is_symlink}")
        if entry.target is not None:
            lines.append(f"target: {entry.target}")
    if entry.sha256 is not None:
        lines.append(f"sha256: {entry.sha256}")
    if entry.metadata:
        lines.append(f"metadata: {entry.metadata}")
    if metadata_result is not None and (
        metadata_result.status is not CapabilityStatus.AVAILABLE or entry.metadata is None
    ):
        lines.append(f"metadata_status: {metadata_result.status.value}")
        lines.append(f"metadata_capability: {metadata_result.capability.value}")
        lines.append(f"metadata_message: {metadata_result.message}")
        if metadata_result.error_code is not None:
            lines.append(f"metadata_error_code: {metadata_result.error_code}")
        if metadata_result.status is CapabilityStatus.UNAVAILABLE:
            lines.append(f"metadata_help: {metadata_result.help}")
    return "\n".join(lines)


def _render_python_analysis(data: dict[str, Any]) -> list[str]:
    """Render Python AST analysis without returning source code."""
    lines: list[str] = []
    if data.get("docstring"):
        lines.append(f"    docstring: {data['docstring']}")
    if data.get("imports"):
        lines.append(f"    imports: {', '.join(data['imports'])}")
    for func in data.get("functions", []):
        args = ", ".join(func.get("args", []))
        returns = func.get("returns")
        return_str = f" -> {returns}" if returns else ""
        async_str = "async " if func.get("is_async") else ""
        lines.append(
            f"    {async_str}def {func['name']}({args}){return_str} at line {func['line']}"
        )
    for cls in data.get("classes", []):
        bases = f"({', '.join(cls['bases'])})" if cls.get("bases") else ""
        lines.append(f"    class {cls['name']}{bases} at line {cls['line']}")
        for method in cls.get("methods", []):
            args = ", ".join(method.get("args", []))
            lines.append(f"      def {method['name']}({args}) at line {method['line']}")
        for attribute in cls.get("attributes", []):
            lines.append(f"      attr {attribute['name']} at line {attribute['line']}")
    return lines


def _render_markdown_structure(data: dict[str, Any]) -> list[str]:
    lines = [
        f"    lines: {data.get('line_count', 0)}",
        f"    headings: {data.get('heading_count', 0)}",
    ]
    for heading in data.get("headings", []):
        marker = "#" * heading["level"]
        lines.append(f"      {marker} {heading['text']} (line {heading['line']})")
    return lines


def _render_text_structure(data: dict[str, Any]) -> list[str]:
    return [
        f"    encoding: {data.get('encoding')}",
        f"    lines: {data.get('line_count', 0)}",
        f"    non-empty lines: {data.get('non_empty_line_count', 0)}",
        f"    paragraphs: {data.get('paragraph_count', 0)}",
        f"    words: {data.get('word_count', 0)}",
        f"    characters: {data.get('character_count', 0)}",
        f"    longest line: {data.get('max_line_length', 0)}",
    ]


def _render_pdf_pages(data: dict[str, Any]) -> list[str]:
    lines = [f"    pages: {data.get('page_count', 0)}"]
    for page in data.get("pages", []):
        lines.append(
            f"      page {page['index']}: {page['width']} x {page['height']} "
            f"{page['orientation']} rotation={page['rotation']}"
        )
    return lines


_ANALYSIS_RENDERERS = {
    "python_ast": _render_python_analysis,
    "markdown_structure": _render_markdown_structure,
    "text_structure": _render_text_structure,
    "pdf_pages": _render_pdf_pages,
}


def render_analyze(result: dict[str, Any]) -> str:
    """Render structured analysis results as plain-text lines."""
    supported = "true" if result.get("supported") else "false"
    lines: list[str] = [f"analyze: {result.get('path')}", f"supported: {supported}"]
    if result.get("sha256") is not None:
        lines.append(f"sha256: {result['sha256']}")
    analyses = result.get("analyses", [])
    if not analyses:
        lines.append("analyses: none")
        return "\n".join(lines)
    for analysis in analyses:
        lines.append(f"  {analysis['capability']} [{analysis['status']}]")
        lines.append(f"    message: {analysis['message']}")
        if analysis.get("error_code") is not None:
            lines.append(f"    error_code: {analysis['error_code']}")
        if analysis["status"] == CapabilityStatus.UNAVAILABLE.value:
            lines.append(f"    help: {analysis['help']}")
        data = analysis.get("data")
        if isinstance(data, dict):
            renderer = _ANALYSIS_RENDERERS.get(analysis["capability"])
            if renderer is not None:
                lines.extend(renderer(data))
            else:
                lines.append(f"    data: {data}")
    return "\n".join(lines)


def render_inventory(inventory: dict[str, Any], root: Path) -> str:
    """Render an inventory as plain-text lines.

    Each line shows rel_path, type, size, and optional SHA-256 hash.
    """
    lines: list[str] = [f"inventory: {root}"]
    entries = inventory.get("entries", [])
    for entry in entries:
        rel_path = entry.get("rel_path", ".")
        entry_type = entry.get("type", "unknown")
        size = entry.get("size")
        sha256 = entry.get("sha256")
        line = f"  {rel_path} [{entry_type}]"
        if size is not None:
            line += f" size={size}"
        if sha256 is not None:
            line += f" sha256={sha256}"
        lines.append(line)
    lines.append(f"count: {inventory.get('count', len(entries))}")
    lines.append(f"complete: {inventory.get('complete', False)}")
    if inventory.get("tree_hash"):
        lines.append(f"tree_hash: {inventory['tree_hash']}")
    return "\n".join(lines)


def render_find(entries: list[FilesystemEntry], root: Path) -> str:
    """Render search results as plain-text lines.

    Each line shows rel_path, type, and size.
    """
    lines: list[str] = [f"find: {root}"]
    for entry in entries:
        rel_path = entry.rel_path or entry.name
        line = f"  {rel_path} [{entry.type.value}]"
        if entry.size is not None:
            line += f" size={entry.size}"
        lines.append(line)
    lines.append(f"count: {len(entries)}")
    return "\n".join(lines)


def render_duplicates(groups: list[dict[str, Any]]) -> str:
    """Render duplicate groups as plain-text lines."""
    lines: list[str] = [f"duplicate groups: {len(groups)}"]
    for group in groups:
        sha256 = group.get("sha256", "")
        size = group.get("size", 0)
        count = group.get("count", 0)
        files = group.get("files", [])
        lines.append(f"  {sha256} size={size} count={count}")
        for file_path in files:
            lines.append(f"    {file_path}")
    return "\n".join(lines)


def render_compare(result: dict[str, Any]) -> str:
    """Render comparison results as plain-text lines."""
    lines: list[str] = []
    for category in (
        "identical",
        "missing",
        "changed",
        "unexpected",
        "type_conflicts",
        "unsupported",
    ):
        items = result.get(category, [])
        if items:
            lines.append(f"{category} ({len(items)}):")
            for item in items:
                lines.append(f"  {item}")
    lines.append(f"complete: {result.get('complete', False)}")
    return "\n".join(lines)


def render_verify(result: dict[str, Any]) -> str:
    """Render verification results as plain-text lines."""
    lines: list[str] = []
    for category in ("missing", "unexpected", "changed", "size_mismatch", "hash_mismatch"):
        items = result.get(category, [])
        if items:
            lines.append(f"{category} ({len(items)}):")
            for item in items:
                lines.append(f"  {item}")
    lines.append(f"complete: {result.get('complete', False)}")
    return "\n".join(lines)
