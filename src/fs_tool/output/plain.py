"""Plain-text presentation (plan.md section 10.2).

Terminal output is optional and never influences filesystem operations.
"""

from __future__ import annotations

from pathlib import Path

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
