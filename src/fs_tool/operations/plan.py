"""Declarative multi-step write plans.

A plan is a small JSON document with ``plan_version: 1`` and an ``operations``
list. Preflight simulates the complete plan in memory before any filesystem
change. Execution is sequential, never overwrites, and has no automatic
rollback.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.filesystem import normalize_path
from fs_tool.operations.common import lstat_or_none
from fs_tool.operations.copy import copy_path
from fs_tool.operations.mkdir import make_directory
from fs_tool.operations.move import move_path
from fs_tool.operations.rmdir import remove_directory
from fs_tool.safety.validation import validate_path

PLAN_VERSION = 1
_PLAN_OPERATIONS = {"mkdir", "move", "copy", "rmdir"}
_COPY_SYMLINK_POLICIES = {"error", "copy", "skip"}


@dataclass
class PlanResult:
    """Result of a plan dry-run or execution."""

    operations: list[dict[str, Any]] = field(default_factory=list)
    would_succeed: bool = False
    complete: bool = False
    dry_run: bool = True
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable plan result."""
        completed = sum(1 for item in self.operations if item["status"] == "completed")
        failed = sum(1 for item in self.operations if item["status"] == "failed")
        pending = sum(1 for item in self.operations if item["status"] == "pending")
        return {
            "plan_version": PLAN_VERSION,
            "dry_run": self.dry_run,
            "executed": self.executed,
            "would_succeed": self.would_succeed,
            "operations": self.operations,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "complete": self.complete,
        }


def _plan_error(message: str, path: Path | None = None) -> FsToolError:
    return FsToolError(
        message,
        code=ErrorCode.INVALID_ARGUMENT,
        path=str(path) if path is not None else None,
    )


def _require_string(raw: dict[str, Any], key: str, index: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise _plan_error(f"Operation {index} requires a non-empty {key!r} string.")
    return value


def _require_bool(raw: dict[str, Any], key: str, index: int, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise _plan_error(f"Operation {index} field {key!r} must be a boolean.")
    return value


def _reject_unknown(raw: dict[str, Any], allowed: set[str], index: int) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise _plan_error(
            f"Operation {index} has unknown field(s): {', '.join(unknown)}; "
            f"allowed fields: {', '.join(sorted(allowed))}."
        )


def load_plan(path: Path) -> list[dict[str, Any]]:
    """Load and validate a plan file.

    Relative paths are resolved against the current working directory. Every
    path is validated against the allowed roots later, during preflight, so a
    plan can refer to paths that do not exist yet.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise _plan_error(f"Cannot load plan file {path}: {exc}", path) from exc

    if not isinstance(data, dict):
        raise _plan_error(f"Invalid plan file {path}: expected a JSON object.", path)
    if data.get("plan_version") != PLAN_VERSION:
        raise _plan_error(
            f"Unsupported plan_version {data.get('plan_version')!r}; expected {PLAN_VERSION}.",
            path,
        )

    raw_operations = data.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise _plan_error(f"Invalid plan file {path}: 'operations' must be a non-empty list.", path)

    operations: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_operations, start=1):
        if not isinstance(raw, dict):
            raise _plan_error(f"Operation {index} must be an object.")
        operation = raw.get("op")
        if operation not in _PLAN_OPERATIONS:
            raise _plan_error(
                f"Operation {index} has unknown op {operation!r}; "
                f"use {', '.join(sorted(_PLAN_OPERATIONS))}."
            )

        if operation == "mkdir":
            _reject_unknown(raw, {"op", "destination", "parents"}, index)
            destination = normalize_path(_require_string(raw, "destination", index))
            normalized: dict[str, Any] = {
                "op": "mkdir",
                "destination": destination,
                "parents": _require_bool(raw, "parents", index, False),
            }
        elif operation == "rmdir":
            _reject_unknown(raw, {"op", "destination", "parents"}, index)
            destination = normalize_path(_require_string(raw, "destination", index))
            normalized = {
                "op": "rmdir",
                "destination": destination,
                "parents": _require_bool(raw, "parents", index, False),
            }
        elif operation == "move":
            _reject_unknown(raw, {"op", "source", "destination", "parents", "allow_rename"}, index)
            source = normalize_path(_require_string(raw, "source", index))
            destination = normalize_path(_require_string(raw, "destination", index))
            normalized = {
                "op": "move",
                "source": source,
                "destination": destination,
                "parents": _require_bool(raw, "parents", index, False),
                "allow_rename": _require_bool(raw, "allow_rename", index, False),
            }
        else:
            _reject_unknown(raw, {"op", "source", "destination", "parents", "symlinks"}, index)
            source = normalize_path(_require_string(raw, "source", index))
            destination = normalize_path(_require_string(raw, "destination", index))
            symlinks = raw.get("symlinks", "error")
            if symlinks not in _COPY_SYMLINK_POLICIES:
                raise _plan_error(
                    f"Operation {index} field 'symlinks' must be one of "
                    f"{', '.join(sorted(_COPY_SYMLINK_POLICIES))}."
                )
            normalized = {
                "op": "copy",
                "source": source,
                "destination": destination,
                "parents": _require_bool(raw, "parents", index, False),
                "symlinks": symlinks,
            }

        operations.append(normalized)

    return operations


class _PlanState:
    """In-memory overlay used by plan preflight."""

    def __init__(self, allowed_roots: tuple[Path, ...]) -> None:
        self.allowed_roots = allowed_roots
        self.virtual: dict[Path, str] = {}
        self.removed_paths: set[Path] = set()
        self.removed_subtrees: set[Path] = set()

    def _removed(self, path: Path) -> bool:
        if path in self.removed_paths:
            return True
        return any(path == root or root in path.parents for root in self.removed_subtrees)

    def kind(self, path: Path) -> str | None:
        """Return ``file``, ``directory``, ``symlink``, ``other`` or None."""
        if self._removed(path):
            return None
        if path in self.virtual:
            return self.virtual[path]
        info = lstat_or_none(path)
        if info is None:
            return None
        if stat.S_ISLNK(info.st_mode):
            return "symlink"
        if stat.S_ISDIR(info.st_mode):
            return "directory"
        if stat.S_ISREG(info.st_mode):
            return "file"
        return "other"

    def children(self, path: Path) -> dict[str, str]:
        """Return visible children of a virtual or real directory."""
        if self.kind(path) != "directory":
            return {}
        children: dict[str, str] = {}
        try:
            with os.scandir(path) as scan:
                for entry in scan:
                    child = path / entry.name
                    if self._removed(child):
                        continue
                    child_kind = self.kind(child)
                    if child_kind is not None:
                        children[entry.name] = child_kind
        except (FileNotFoundError, NotADirectoryError):
            pass
        except OSError as exc:
            raise FsToolError(
                f"Cannot inspect directory {path}: {exc.strerror or exc}",
                code=ErrorCode.OPERATION_FAILED,
                path=str(path),
            ) from exc

        for candidate, candidate_kind in self.virtual.items():
            if candidate.parent == path and not self._removed(candidate):
                children[candidate.name] = candidate_kind
        return children

    def add_subtree(self, source: Path, destination: Path) -> tuple[str, ...]:
        """Reserve a copy/move destination subtree and return its paths."""
        kind = self.kind(source)
        if kind is None:
            raise _plan_error(f"Source does not exist: {source}", source)
        self.virtual[destination] = kind
        affected = [str(destination)]
        if kind != "directory":
            return tuple(affected)

        for name, child_kind in self.children(source).items():
            child_affected = self.add_subtree(source / name, destination / name)
            affected.extend(child_affected)
            if child_kind == "other":
                raise FsToolError(
                    f"Cannot move or copy unsupported filesystem entry: {source / name}",
                    code=ErrorCode.OPERATION_FAILED,
                    path=str(source / name),
                )
        return tuple(affected)

    def remove(self, path: Path, kind: str) -> None:
        """Mark a path or directory subtree as removed."""
        if kind == "directory":
            self.removed_subtrees.add(path)
        else:
            self.removed_paths.add(path)

    def ensure_parents(self, destination: Path, parents: bool) -> tuple[str, ...]:
        """Return planned parent directories and reserve them when requested."""
        parent = destination.parent
        parent_kind = self.kind(parent)
        if parent_kind == "directory":
            return ()
        if parent_kind is not None:
            raise FsToolError(
                f"Parent is not a directory: {parent}",
                code=ErrorCode.TYPE_CONFLICT,
                path=str(parent),
            )
        if not parents:
            raise FsToolError(
                f"Parent directory does not exist: {parent}; use parents=true in the plan.",
                code=ErrorCode.INVALID_ARGUMENT,
                path=str(parent),
            )

        missing: list[Path] = []
        current = parent
        while self.kind(current) is None:
            missing.append(current)
            if current.parent == current:
                break
            current = current.parent
        if self.kind(current) != "directory":
            raise FsToolError(
                f"Parent is not a directory: {current}",
                code=ErrorCode.TYPE_CONFLICT,
                path=str(current),
            )
        for path in reversed(missing):
            self.virtual[path] = "directory"
        return tuple(str(path) for path in reversed(missing))

    def destination_for_existing_directory(self, source: Path, destination: Path) -> Path:
        """Apply existing-directory destination semantics to a virtual path."""
        if self.kind(destination) == "directory":
            return destination / source.name
        return destination

    def device(self, path: Path) -> int | None:
        """Return the device id for a real path or its nearest real ancestor."""
        info = lstat_or_none(path)
        if info is not None:
            return info.st_dev
        current = path
        while current.parent != current:
            current = current.parent
            info = lstat_or_none(current)
            if info is not None and stat.S_ISDIR(info.st_mode):
                return info.st_dev
        return None


def _report(
    operation: str,
    source: Path | None,
    destination: Path,
    *,
    affected: tuple[str, ...],
    created_directories: tuple[str, ...] = (),
    removed: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "op": operation,
        "source": str(source) if source is not None else None,
        "destination": str(destination),
        "affected": list(affected),
        "created_directories": list(created_directories),
        "removed": list(removed),
    }


def _simulate_operation(state: _PlanState, operation: dict[str, Any]) -> dict[str, Any]:
    """Simulate one operation against the virtual state."""
    op = operation["op"]
    if op == "mkdir":
        destination = validate_path(operation["destination"], state.allowed_roots)
        existing = state.kind(destination)
        if existing == "directory":
            return _report("mkdir", None, destination, affected=())
        if existing is not None:
            raise FsToolError(
                f"Destination is not a directory: {destination}",
                code=ErrorCode.TYPE_CONFLICT,
                path=str(destination),
            )
        parents = state.ensure_parents(destination, operation["parents"])
        state.virtual[destination] = "directory"
        return _report(
            "mkdir",
            None,
            destination,
            affected=parents + (str(destination),),
        )

    if op == "rmdir":
        destination = validate_path(operation["destination"], state.allowed_roots)
        kind = state.kind(destination)
        if kind is None:
            raise FsToolError(
                f"Directory does not exist: {destination}",
                code=ErrorCode.INVALID_ARGUMENT,
                path=str(destination),
            )
        if kind != "directory":
            raise FsToolError(
                f"Refusing to remove a non-directory entry: {destination}",
                code=ErrorCode.TYPE_CONFLICT,
                path=str(destination),
            )
        if state.children(destination):
            raise FsToolError(
                f"Cannot remove non-empty directory: {destination}",
                code=ErrorCode.OPERATION_FAILED,
                path=str(destination),
            )

        planned = [destination]
        planned_set = {destination}
        if operation["parents"]:
            allowed = {root.resolve(strict=False) for root in state.allowed_roots}
            current = destination.parent
            while current != current.parent and current.resolve(strict=False) not in allowed:
                children = state.children(current)
                if any((current / name) not in planned_set for name in children):
                    break
                planned.append(current)
                planned_set.add(current)
                current = current.parent
        state.remove(destination, "directory")
        for path in planned[1:]:
            state.remove(path, "directory")
        return _report(
            "rmdir",
            None,
            destination,
            affected=tuple(str(path) for path in planned),
            removed=(),
        )

    source = validate_path(operation["source"], state.allowed_roots)
    raw_destination = validate_path(operation["destination"], state.allowed_roots)
    source_kind = state.kind(source)
    if source_kind is None:
        raise FsToolError(
            f"Source does not exist: {source}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source),
        )
    if source_kind == "other":
        raise FsToolError(
            f"Cannot move or copy unsupported filesystem entry: {source}",
            code=ErrorCode.OPERATION_FAILED,
            path=str(source),
        )

    destination = state.destination_for_existing_directory(source, raw_destination)
    if destination == source:
        raise FsToolError(
            "Source and destination are the same path.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source),
        )
    if source_kind == "directory" and (destination == source or source in destination.parents):
        raise FsToolError(
            f"Cannot move or copy a directory into itself or a descendant: {destination}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(destination),
        )

    if op == "move" and source.name != destination.name and not operation["allow_rename"]:
        raise FsToolError(
            "Changing the filename requires allow_rename=true in the plan.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(destination),
        )

    parents = state.ensure_parents(destination, operation["parents"])
    if state.kind(destination) is not None:
        raise FsToolError(
            f"Destination already exists: {destination}",
            code=ErrorCode.TARGET_EXISTS,
            path=str(destination),
        )

    if op == "move":
        source_device = state.device(source)
        destination_device = state.device(destination.parent)
        if (
            source_device is not None
            and destination_device is not None
            and source_device != destination_device
        ):
            raise FsToolError(
                "Cross-device moves are not supported; use copy plus verification.",
                code=ErrorCode.OPERATION_FAILED,
                path=str(destination),
            )

    if op == "copy":
        affected_paths = state.add_subtree(source, destination)
        return _report(
            "copy",
            source,
            destination,
            affected=parents + affected_paths,
            created_directories=parents,
        )

    state.add_subtree(source, destination)
    state.remove(source, source_kind)
    return _report(
        "move",
        source,
        destination,
        affected=parents + (str(destination),),
        created_directories=parents,
    )


def _failed_operation(operation: dict[str, Any], error: FsToolError) -> dict[str, Any]:
    return {
        "status": "failed",
        "op": operation["op"],
        "source": str(operation["source"]) if "source" in operation else None,
        "destination": str(operation["destination"]),
        "affected": [],
        "created_directories": [],
        "removed": [],
        "error": {
            "code": error.code.value,
            "message": error.message,
            "path": error.path,
            "details": error.details,
        },
    }


def _pending_operation(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "op": operation["op"],
        "source": str(operation["source"]) if "source" in operation else None,
        "destination": str(operation["destination"]),
        "affected": [],
        "created_directories": [],
        "removed": [],
    }


def _preflight(operations: list[dict[str, Any]], allowed_roots: tuple[Path, ...]) -> PlanResult:
    """Simulate the complete plan without changing the filesystem."""
    state = _PlanState(allowed_roots)
    planned: list[dict[str, Any]] = []
    seen_destinations: set[Path] = set()
    for index, operation in enumerate(operations, start=1):
        try:
            report = _simulate_operation(state, operation)
            destination = Path(report["destination"])
            if destination in seen_destinations:
                raise _plan_error(f"Duplicate destination path in plan: {destination}")
            seen_destinations.add(destination)
        except FsToolError as exc:
            failed = _failed_operation(operation, exc)
            failed["index"] = index
            planned.append(failed)
            for pending_index, pending in enumerate(operations[index:], start=index + 1):
                item = _pending_operation(pending)
                item["index"] = pending_index
                planned.append(item)
            return PlanResult(
                operations=planned,
                would_succeed=False,
                complete=False,
                dry_run=True,
                executed=False,
            )
        item = {"index": index, "status": "planned", **report}
        planned.append(item)

    return PlanResult(
        operations=planned,
        would_succeed=True,
        complete=True,
        dry_run=True,
        executed=False,
    )


def _execute_operation(
    operation: dict[str, Any], allowed_roots: tuple[Path, ...]
) -> dict[str, Any]:
    """Execute one operation with the existing safe write primitives."""
    from dataclasses import asdict

    op = operation["op"]
    if op == "mkdir":
        report = make_directory(
            operation["destination"],
            allowed_roots=allowed_roots,
            dry_run=False,
            yes=True,
            parents=operation["parents"],
        )
    elif op == "rmdir":
        report = remove_directory(
            operation["destination"],
            allowed_roots=allowed_roots,
            dry_run=False,
            yes=True,
            parents=operation["parents"],
        )
    elif op == "move":
        report = move_path(
            operation["source"],
            operation["destination"],
            allowed_roots=allowed_roots,
            dry_run=False,
            yes=True,
            allow_rename=operation["allow_rename"],
            parents=operation["parents"],
        )
    else:
        report = copy_path(
            operation["source"],
            operation["destination"],
            allowed_roots=allowed_roots,
            dry_run=False,
            yes=True,
            symlinks=operation["symlinks"],
            parents=operation["parents"],
        )

    result = {"status": "completed", **asdict(report)}
    result["op"] = op
    result["affected"] = list(result["affected"])
    result["skipped"] = list(result["skipped"])
    result["created_directories"] = list(result["created_directories"])
    result["removed"] = list(result["removed"])
    return result


def apply_plan(
    plan_path: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
    on_error: str = "stop",
) -> PlanResult:
    """Preflight and optionally execute a multi-step write plan."""
    if dry_run == yes:
        raise FsToolError(
            "Specify exactly one of --dry-run or --yes.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if on_error not in {"stop", "continue"}:
        raise FsToolError(
            "Invalid --on-error value; use stop or continue.",
            code=ErrorCode.INVALID_ARGUMENT,
        )

    operations = load_plan(plan_path)
    preflight = _preflight(operations, allowed_roots)
    if dry_run:
        return preflight
    if not preflight.would_succeed:
        return PlanResult(
            operations=preflight.operations,
            would_succeed=False,
            complete=False,
            dry_run=False,
            executed=False,
        )

    executed: list[dict[str, Any]] = []
    stopped = False
    for index, operation in enumerate(operations, start=1):
        if stopped:
            item = _pending_operation(operation)
            item["index"] = index
            executed.append(item)
            continue
        try:
            result = _execute_operation(operation, allowed_roots)
        except FsToolError as exc:
            item = _failed_operation(operation, exc)
            item["index"] = index
            executed.append(item)
            if on_error == "stop":
                stopped = True
            continue
        result["index"] = index
        executed.append(result)

    failed = sum(1 for item in executed if item["status"] == "failed")
    pending = sum(1 for item in executed if item["status"] == "pending")
    complete = pending == 0
    return PlanResult(
        operations=executed,
        would_succeed=failed == 0 and complete,
        complete=complete,
        dry_run=False,
        executed=True,
    )
