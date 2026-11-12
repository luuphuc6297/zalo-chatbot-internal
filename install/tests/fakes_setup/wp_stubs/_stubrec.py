"""Shared helpers of the setup tests' stand-ins for other packages (test support only, never shipped).

The stand-ins record each call in `<tmp>/calls.jsonl` as {"tool": "stub.<module>", "argv": [function, ...]} and
read their behaviour from the key "stub_<module>" of `<tmp>/behaviour.json`, like the fakes of fake_bin.
"""

from __future__ import annotations

import fcntl
import json
import os
import time


def test_dir() -> str:
    d = os.environ.get("THOMHOUSE_TEST_DIR")
    if not d or not os.path.isfile(os.path.join(d, ".installer-test")):
        raise RuntimeError("setup stub used outside an installer test")
    return d


def behaviour(module: str) -> dict:
    try:
        with open(os.path.join(test_dir(), "behaviour.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    value = data.get(f"stub_{module}", {}) if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def record(module: str, *argv: object) -> None:
    entry = {"tool": f"stub.{module}", "argv": [str(a) if a is not None else None for a in argv],
             "pid": os.getpid(), "at": time.time()}
    with open(os.path.join(test_dir(), "calls.jsonl"), "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(entry) + "\n")
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def fails(module: str, name: str) -> bool:
    """True when behaviour "stub_<module>".fail names `name` (a string or a list)."""
    fail = behaviour(module).get("fail")
    return fail == name or (isinstance(fail, list) and name in fail)


def write_exec(path, text: str) -> None:
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def replace_link(link, target: str) -> None:
    link = str(link)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    tmp = link + ".tmp-link"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)
