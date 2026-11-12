"""Shared helpers of the stub scripts in the fake release tree (installer tests only, 16.10).

The test folder is THOMHOUSE_TEST_DIR, or the parent of HOME when it holds `.installer-test`. Calls are recorded in
`<tmp>/calls.jsonl` like the fakes of install/tests/fake_bin; behaviour comes from `<tmp>/behaviour.json`.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time

RECORDED_ENV = ("DISABLE_UPDATES", "no_proxy", "NO_PROXY", "PROFILE_LLM_ENABLED", "THOMHOUSE_BOT_HOME",
                "CLAUDE_CONFIG_DIR")


def test_dir():
    d = os.environ.get("THOMHOUSE_TEST_DIR")
    if d and os.path.isdir(d):
        return d
    home = os.environ.get("HOME")
    if home:
        parent = os.path.dirname(os.path.abspath(home))
        if os.path.exists(os.path.join(parent, ".installer-test")):
            return parent
    sys.stderr.write("stub: no test folder; refusing to run\n")
    sys.exit(99)


def behaviour(tool):
    try:
        with open(os.path.join(test_dir(), "behaviour.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    value = data.get(tool, {}) if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def record(tool, argv, **extra):
    entry = {
        "tool": tool,
        "argv": list(argv),
        "cwd": os.getcwd(),
        "env_names": sorted(os.environ),
        "env": {k: os.environ.get(k) for k in RECORDED_ENV},
        "pid": os.getpid(),
        "at": time.time(),
    }
    entry.update(extra)
    with open(os.path.join(test_dir(), "calls.jsonl"), "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
