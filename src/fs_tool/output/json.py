"""Common JSON response envelope.

Every command returns the envelope structure described in plan.md
section 4.3:

.. code-block:: json

   {
     "schema_version": 1,
     "success": true,
     "command": "inspect.info",
     "result": {},
     "errors": [],
     "warnings": [],
     "complete": true
   }

``--help`` and ``--version`` are documented exceptions to the JSON
envelope.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = 1

ENVELOPE_KEY_ORDER = (
    "schema_version",
    "success",
    "command",
    "result",
    "errors",
    "warnings",
    "complete",
)


@dataclass(frozen=True)
class Error:
    """A structured error entry in the JSON envelope."""

    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Warning:
    """A structured warning entry in the JSON envelope."""

    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Envelope:
    """The common JSON response envelope."""

    schema_version: int = SCHEMA_VERSION
    success: bool = True
    command: str = ""
    result: Any = None
    errors: tuple[Error, ...] = ()
    warnings: tuple[Warning, ...] = ()
    complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with stable key order."""
        ordered: dict[str, Any] = {}
        ordered["schema_version"] = self.schema_version
        ordered["success"] = self.success
        ordered["command"] = self.command
        ordered["result"] = self.result
        ordered["errors"] = [asdict(error) for error in self.errors]
        ordered["warnings"] = [asdict(warning) for warning in self.warnings]
        ordered["complete"] = self.complete
        return ordered

    def to_json(self, **kwargs: Any) -> str:
        """Serialize to deterministic JSON."""
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            success=bool(data.get("success", True)),
            command=str(data.get("command", "")),
            result=data.get("result"),
            errors=tuple(Error(**item) for item in data.get("errors", [])),
            warnings=tuple(Warning(**item) for item in data.get("warnings", [])),
            complete=bool(data.get("complete", True)),
        )

    @classmethod
    def from_json(cls, text: str) -> Envelope:
        return cls.from_dict(json.loads(text))


def success_result(
    command: str,
    result: Any = None,
    *,
    complete: bool = True,
    warnings: tuple[Warning, ...] = (),
) -> Envelope:
    """Build a successful envelope."""
    return Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command=command,
        result=result,
        errors=(),
        warnings=warnings,
        complete=complete,
    )


def failure_result(
    command: str,
    errors: tuple[Error, ...],
    *,
    complete: bool = False,
    result: Any = None,
    warnings: tuple[Warning, ...] = (),
) -> Envelope:
    """Build a failed envelope."""
    return Envelope(
        schema_version=SCHEMA_VERSION,
        success=False,
        command=command,
        result=result,
        errors=errors,
        warnings=warnings,
        complete=complete,
    )
