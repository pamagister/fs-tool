"""Allow running the package as ``python -m fs_tool``."""

import sys

from fs_tool.cli import main

if __name__ == "__main__":
    sys.exit(main())
