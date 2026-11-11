"""CSV/TSV rendering for inventory output.

CSV/TSV is an inventory-only export format. It uses the same selected entry
profile as JSON: compact by default, all non-path fields with ``--verbose``,
or exactly the requested fields with ``--fields``.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fs_tool.core.models import EntryType


def _tabular_value(value: Any) -> str:
    """Render one value for a CSV/TSV cell."""
    if value is None:
        return ""
    if isinstance(value, EntryType):
        return value.value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def render_inventory_tabular(inventory: dict[str, Any], *, delimiter: str = ",") -> str:
    """Render inventory entries as CSV or TSV with a header row."""
    entries = inventory.get("entries", [])
    fieldnames: list[str] = []
    for entry in entries:
        for field_name in entry:
            if field_name not in fieldnames:
                fieldnames.append(field_name)
    if not fieldnames:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        delimiter=delimiter,
        lineterminator="\n",
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow({name: _tabular_value(entry.get(name)) for name in fieldnames})
    return buffer.getvalue()
