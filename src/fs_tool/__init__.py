"""fs-tool – lightweight, secure and agent-friendly filesystem CLI."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    __version__ = _distribution_version("fs-tool")
except PackageNotFoundError:
    __version__ = "0.1.0"
