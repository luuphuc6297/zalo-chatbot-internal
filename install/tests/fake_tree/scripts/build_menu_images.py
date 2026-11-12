"""Stub of scripts/build_menu_images.py for the installer tests (16.10).

`--check` exits with behaviour "build_menu_images".check_exit (default 0); a build exits with "exit" (default 0).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _teststub  # noqa: E402

TOOL = "build_menu_images"


def main() -> int:
    _teststub.record(TOOL, sys.argv[1:])
    b = _teststub.behaviour(TOOL)
    if "--check" in sys.argv[1:]:
        return int(b.get("check_exit", 0))
    return int(b.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
