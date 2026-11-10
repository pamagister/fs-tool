"""Setup orchestration for optional capability resources.

Setup prepares external resources such as the YOLO model. It never installs
Python packages: missing packages are reported with exact installation
commands instead. Each target is independent, so ``setup --all`` keeps going
when one target fails.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.capabilities.models import (
    CapabilityId,
    ExternalResourceRequirement,
    Requirement,
)
from fs_tool.core.capabilities.registry import CapabilityRegistry, default_registry
from fs_tool.core.capabilities.report import requirement_to_dict
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.setup.models import Opener, SetupResult, expected_model_path
from fs_tool.setup.yolo import setup_yolo

#: Setup targets in deterministic order.
SETUP_TARGET_NAMES = ("pdf", "image", "yolo")


@dataclass(frozen=True)
class SetupTarget:
    """A named setup target and the capabilities it prepares.

    ``include_external_resources`` is false for ``image``: that target only
    checks the image Python dependencies, while the model belongs to ``yolo``.
    """

    name: str
    capability_ids: tuple[CapabilityId, ...]
    include_external_resources: bool = True
    prepare_model: bool = False


SETUP_TARGETS: dict[str, SetupTarget] = {
    "pdf": SetupTarget(
        name="pdf",
        capability_ids=(
            CapabilityId.PDF_METADATA,
            CapabilityId.PDF_PAGES,
            CapabilityId.PDF_TEXT,
        ),
    ),
    "image": SetupTarget(
        name="image",
        capability_ids=(
            CapabilityId.IMAGE_METADATA,
            CapabilityId.IMAGE_OBJECT_DETECTION,
        ),
        include_external_resources=False,
    ),
    "yolo": SetupTarget(
        name="yolo",
        capability_ids=(CapabilityId.IMAGE_OBJECT_DETECTION,),
        prepare_model=True,
    ),
}


def _unique_requirements(requirements: Iterable[Requirement]) -> tuple[Requirement, ...]:
    """Return requirements without duplicates, preserving first-seen order."""
    unique: list[Requirement] = []
    seen: set[tuple[str, str]] = set()
    for requirement in requirements:
        if isinstance(requirement, ExternalResourceRequirement):
            key = ("external_resource", requirement.name)
        else:
            key = ("python_package", requirement.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(requirement)
    return tuple(unique)


def _target_requirements(
    target: SetupTarget,
    *,
    registry: CapabilityRegistry,
    checker: AvailabilityChecker,
) -> tuple[Requirement, ...]:
    """Collect and check the requirements declared for ``target``."""
    requirements: list[Requirement] = []
    for capability_id in target.capability_ids:
        capability = registry.get(capability_id)
        if capability is not None:
            requirements.extend(capability.requirements)
    selected = _unique_requirements(requirements)
    if not target.include_external_resources:
        selected = tuple(
            requirement
            for requirement in selected
            if not isinstance(requirement, ExternalResourceRequirement)
        )
    return tuple(checker.check_requirement(requirement) for requirement in selected)


def _next_steps(missing: list[dict[str, Any]]) -> list[str]:
    """Return unique, actionable steps for missing requirements."""
    steps: list[str] = []
    for requirement in missing:
        if "install_command" in requirement:
            command = requirement["install_command"]
        else:
            command = "fs-tool setup yolo"
        if command not in steps:
            steps.append(command)
    return steps


def _resource_dict(
    result: SetupResult | None,
    *,
    error: FsToolError | None,
    model_dir: Path | None,
) -> dict[str, Any] | None:
    """Serialize the external resource prepared by a setup target."""
    if result is not None:
        return {
            "name": result.path.name,
            "path": str(result.path),
            "status": result.status,
            "message": result.message,
        }
    if error is not None:
        path = error.path or str(expected_model_path(model_dir))
        return {
            "name": Path(path).name,
            "path": path,
            "status": "failed",
            "message": error.message,
        }
    return None


def setup_target(
    target_name: str,
    *,
    force: bool = False,
    opener: Opener | None = None,
    model_dir: Path | None = None,
    checker: AvailabilityChecker | None = None,
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any]:
    """Prepare one setup target and return its structured result.

    Missing Python packages are reported but do not raise. Only a failed
    external-resource setup produces a ``failed`` status and an error code.
    """
    target = SETUP_TARGETS[target_name]
    active_checker = checker if checker is not None else AvailabilityChecker()
    active_registry = registry if registry is not None else default_registry()

    requirements = _target_requirements(
        target,
        registry=active_registry,
        checker=active_checker,
    )
    resource: dict[str, Any] | None = None
    error: FsToolError | None = None

    if target.prepare_model:
        try:
            result = setup_yolo(model_dir=model_dir, force=force, opener=opener)
        except FsToolError as exc:
            error = exc
            resource = _resource_dict(None, error=exc, model_dir=model_dir)
        else:
            resource = _resource_dict(result, error=None, model_dir=model_dir)
        # Re-check requirements so a freshly downloaded model is reflected.
        requirements = _target_requirements(
            target,
            registry=active_registry,
            checker=active_checker,
        )

    requirement_dicts = [requirement_to_dict(requirement) for requirement in requirements]
    missing = [requirement for requirement in requirement_dicts if not requirement["available"]]
    next_steps = _next_steps(missing)

    if error is not None:
        status = "failed"
        message = error.message
        error_code: str | None = error.code.value
        if error.code is ErrorCode.RESOURCE_CORRUPT and not force:
            next_steps.append("fs-tool setup yolo --force")
    elif missing:
        status = "missing-dependencies"
        message = "Missing Python dependencies; install them and run setup again."
        error_code = None
    else:
        status = "ready"
        message = resource["message"] if resource is not None else "All requirements are available."
        error_code = None

    return {
        "capability": target.name,
        "status": status,
        "message": message,
        "requirements": requirement_dicts,
        "missing_requirements": missing,
        "next_steps": next_steps,
        "resource": resource,
        "error_code": error_code,
    }


def setup_report(
    target_names: Iterable[str],
    *,
    force: bool = False,
    opener: Opener | None = None,
    model_dir: Path | None = None,
    checker: AvailabilityChecker | None = None,
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any]:
    """Prepare every requested target independently and summarize the results."""
    targets = [
        setup_target(
            name,
            force=force,
            opener=opener,
            model_dir=model_dir,
            checker=checker,
            registry=registry,
        )
        for name in target_names
    ]
    return {
        "targets": targets,
        "count": len(targets),
        "failed_count": sum(1 for target in targets if target["status"] == "failed"),
    }


def setup_all(
    *,
    force: bool = False,
    opener: Opener | None = None,
    model_dir: Path | None = None,
    checker: AvailabilityChecker | None = None,
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any]:
    """Prepare all setup targets in deterministic order."""
    return setup_report(
        SETUP_TARGET_NAMES,
        force=force,
        opener=opener,
        model_dir=model_dir,
        checker=checker,
        registry=registry,
    )


__all__ = [
    "SETUP_TARGET_NAMES",
    "SETUP_TARGETS",
    "SetupTarget",
    "setup_all",
    "setup_report",
    "setup_target",
]
