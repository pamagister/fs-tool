"""Document metadata extraction (plan.md Phase 2, P2-T14; decision D5).

Extracts document metadata from PDF (via optional pypdf) and from
ODF/OOXML files via stdlib zipfile/ElementTree. Extraction is read-only,
never executes embedded content, and respects a size limit. Unavailable
metadata is represented as None, never silently omitted.
"""

from __future__ import annotations

import importlib
import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

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

# Document extensions grouped by format.
_PDF_EXTENSIONS = {".pdf"}
_ODF_EXTENSIONS = {".odt", ".ods", ".odp", ".odg"}
_OOXML_EXTENSIONS = {".docx", ".xlsx", ".pptx"}

# PDF date pattern: D:YYYYMMDDHHmmSSOHHmm'
_PDF_DATE_RE = re.compile(
    r"^D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})([Z+\-])?(\d{2})'?(\d{2})'?$"
)

# Namespaces for ODF meta.xml.
_ODF_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
}

# Namespaces for OOXML core.xml.
_OOXML_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}


def extract_metadata(path: Path) -> dict[str, str | None] | None:
    """Extract document metadata from ``path``.

    Returns a dict with keys ``author``, ``title``, ``subject``,
    ``created``, ``modified`` (ISO-8601 UTC strings or ``None``), or
    ``None`` when the format is unsupported, the file is too large, or
    extraction fails.
    """
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_METADATA_SIZE:
        return None

    suffix = path.suffix.lower()
    if suffix in _PDF_EXTENSIONS:
        return _extract_pdf_metadata(path)
    if suffix in _ODF_EXTENSIONS:
        return _extract_odf_metadata(path)
    if suffix in _OOXML_EXTENSIONS:
        return _extract_ooxml_metadata(path)
    return None


def _parse_pdf_date(value: str) -> str | None:
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


def _extract_pdf_metadata(path: Path) -> dict[str, str | None] | None:
    """Extract metadata from a PDF via pypdf."""
    if not HAS_PYPDF:
        return None
    try:
        pypdf = importlib.import_module("pypdf")
        reader = pypdf.PdfReader(str(path))
        info = reader.metadata
        if info is None:
            return None
    except Exception:  # pragma: no cover - defensive, never crash on bad PDF
        return None

    creation_date = info.get("/CreationDate")
    mod_date = info.get("/ModDate")
    return {
        "author": info.get("/Author"),
        "title": info.get("/Title"),
        "subject": info.get("/Subject"),
        "created": _parse_pdf_date(creation_date) if isinstance(creation_date, str) else None,
        "modified": _parse_pdf_date(mod_date) if isinstance(mod_date, str) else None,
    }


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes | None:
    """Read one metadata member without exceeding the zip-bomb limit."""
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


def _extract_odf_metadata(path: Path) -> dict[str, str | None] | None:
    """Extract metadata from an ODF file (ODT/ODS/ODP/ODG) via zipfile/ElementTree."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml_text = _read_zip_member(archive, "meta.xml")
    except (zipfile.BadZipFile, OSError):
        return None
    if xml_text is None:
        return None

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None

    def find_text(local_name: str, prefix: str = "dc") -> str | None:
        ns = _ODF_NS.get(prefix, "")
        element = root.find(f".//{{{ns}}}{local_name}")
        return element.text if element is not None and element.text else None

    # ODF stores bibliographic fields (dc:creator, dc:title, dc:subject)
    # and system dates (meta:creation-date, dc:date) below office:meta.
    # Use a descendant search because the root element is
    # office:document-meta.
    return {
        "author": find_text("creator") or find_text("initial-creator", "meta"),
        "title": find_text("title"),
        "subject": find_text("subject"),
        "created": find_text("creation-date", "meta"),
        "modified": find_text("date") or find_text("modification-date", "meta"),
    }


def _extract_ooxml_metadata(path: Path) -> dict[str, str | None] | None:
    """Extract metadata from an OOXML file (DOCX/XLSX/PPTX) via zipfile/ElementTree."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml_text = _read_zip_member(archive, "docProps/core.xml")
    except (zipfile.BadZipFile, OSError):
        return None
    if xml_text is None:
        return None

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None

    def find_text(local_name: str, prefix: str = "dc") -> str | None:
        ns = _OOXML_NS.get(prefix, "")
        tag = f"{{{ns}}}{local_name}"
        element = root.find(tag)
        return element.text if element is not None else None

    return {
        "author": find_text("creator"),
        "title": find_text("title"),
        "subject": find_text("subject"),
        "created": find_text("created", "dcterms"),
        "modified": find_text("modified", "dcterms"),
    }
