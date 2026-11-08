"""Python source analysis provider.

Reuses the existing AST analysis in
``fs_tool.core.analysis.python_analysis`` instead of duplicating parser logic.
The analyzed file is never imported or executed (plan.md decision D2 and the
security requirements).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fs_tool.core.analysis.python_analysis import analyze_python_file, module_to_dict
from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers.base import Provider, capabilities_from_registry


class PythonProvider(Provider):
    """Provider for Python source files."""

    @property
    def id(self) -> str:
        return "python"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, (CapabilityId.PYTHON_AST,))

    def supported_extensions(self) -> tuple[str, ...]:
        return (".py",)

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        return (CapabilityId.PYTHON_AST,)

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        if capability is not CapabilityId.PYTHON_AST:
            raise NotImplementedError(f"python does not implement {capability.value}")
        module = analyze_python_file(path)
        if module is None:
            raise FsToolError(
                "Python source could not be analyzed; it may be too large, "
                "unreadable or syntactically invalid.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
        return module_to_dict(module)
