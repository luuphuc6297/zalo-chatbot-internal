"""Shared plumbing of the WP2/WP4 stand-ins used by the operations tests (never shipped; install/tests/** is not
copied into a release). Calls are recorded in <tmp>/calls.jsonl as {"tool": "stub", "fn": "<module>.<name>", ...};
behaviour comes from the "stubs" section of <tmp>/behaviour.json."""

from __future__ import annotations

import fcntl
import json
import os
import time


def test_dir() -> str:
    d = os.environ.get("THOMHOUSE_TEST_DIR")
    if not d or not os.path.isdir(d):
        raise RuntimeError("stub module used outside an installer test")
    return d


def behaviour() -> dict:
    try:
        with open(os.path.join(test_dir(), "behaviour.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    value = data.get("stubs", {}) if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def record(fn: str, **fields: object) -> None:
    entry = {"tool": "stub", "fn": fn, "pid": os.getpid(), "at": time.time()}
    entry.update({k: (str(v) if not isinstance(v, (int, float, bool, list, dict, type(None))) else v)
                  for k, v in fields.items()})
    with open(os.path.join(test_dir(), "calls.jsonl"), "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(entry) + "\n")
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
