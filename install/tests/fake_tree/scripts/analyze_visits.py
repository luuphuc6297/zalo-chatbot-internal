"""Stub of scripts/analyze_visits.py for the installer tests (16.10).

Records the call (with the value of PROFILE_LLM_ENABLED) and exits with behaviour "analyze_visits".exit. With
behaviour "not_found": true it prints `analyze_visits: push failed (HTTP 404) ...` on stderr and exits 1, like the
real script when the server has no chat-facts endpoint.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _teststub  # noqa: E402

TOOL = "analyze_visits"


def main() -> int:
    _teststub.record(TOOL, sys.argv[1:])
    b = _teststub.behaviour(TOOL)
    if b.get("not_found"):
        sys.stderr.write("analyze_visits: push failed: /staff/chat-facts/import (HTTP 404) not found\n")
        return 1
    print('{"visits": 2}')
    if b.get("stderr"):
        sys.stderr.write(str(b["stderr"]) + "\n")
    return int(b.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
