"""Shared helpers for document metadata extraction.

Format-specific extraction lives in the provider modules under
``fs_tool/core/providers``; this module only contains format-neutral helpers
and constants. Extraction is read-only, never executes embedded content and
respects size limits.
"""

from __future__ import annotations

import importlib
import re
import zipfile
from datetime import UTC, datetime, timedelta

# pypdf is an optional dependency (``[metadata]`` extra). Detect at runtime
# so the module imports cleanly without it.
try:
    importlib.import_module("pypdf")
    HAS_PYPDF = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_PYPDF = False

# Maximum file size for metadata extraction (100 MiB) to avoid
# reading excessively large documents.
MAX_METADATA_SIZE = 100 * 1024 * 1024

# Maximum uncompressed size accepted for a single metadata XML member.
# Guards against zip bombs that declare a small archive containing a
# huge XML document.
MAX_ZIP_MEMBER_SIZE = 10 * 1024 * 1024

# PDF date pattern: D:YYYYMMDDHHmmSSOHHmm'
_PDF_DATE_RE = re.compile(
    r"^D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})([Z+\-])?(\d{2})'?(\d{2})'?$"
)


def parse_pdf_date(value: str) -> str | None:
    """Parse a PDF date string into ISO-8601 UTC."""
    match = _PDF_DATE_RE.match(value.strip())
    if not match:
        return None
    year, month, day, hour, minute, second = map(int, match.groups()[:6])
    tz_sign = match.group(7)
    tz_hour = int(match.group(8) or 0)
    tz_minute = int(match.group(9) or 0)
    try:
        dt = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return None
    if tz_sign == "+":
        dt = dt.replace(tzinfo=None) - timedelta(hours=tz_hour, minutes=tz_minute)
        dt = dt.replace(tzinfo=UTC)
    elif tz_sign == "-":
        dt = dt.replace(tzinfo=None) + timedelta(hours=tz_hour, minutes=tz_minute)
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes | None:
    """Read one member without exceeding the zip-bomb limit."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_ZIP_MEMBER_SIZE:
        return None
    try:
        data = archive.read(name)
    except (zipfile.BadZipFile, OSError, KeyError, RuntimeError, EOFError, ValueError):
        return None
    if len(data) > MAX_ZIP_MEMBER_SIZE:
        return None
    return data
