"""Stub of scripts/analyze_contacts.py for the installer tests (16.10).

Records the call (with the value of PROFILE_LLM_ENABLED) and exits with behaviour "analyze_contacts".exit; prints
behaviour "stderr" on stderr when given.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _teststub  # noqa: E402

TOOL = "analyze_contacts"


def main() -> int:
    _teststub.record(TOOL, sys.argv[1:])
    b = _teststub.behaviour(TOOL)
    print('{"pushed": 3}')
    if b.get("stderr"):
        sys.stderr.write(str(b["stderr"]) + "\n")
    return int(b.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
