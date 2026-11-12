"""Stub of `python3 -m bridge.main` for the installer tests (16.10).

    init-env [--mode M] [--engine-bin P] [--repo-root R]   writes the three env files with synthetic tokens (0600),
                                                          keeping values that exist; prints key names only
    doctor --json                                         {"checks": [...]} from behaviour "bridge".doctor
                                                          (name -> status); the zalo_login detail holds 999000111
    listener start|status|stop [--only-ours]              behaviour "bridge".listener.<action> = [code, json]
    sync-labels [--dry-run]                               behaviour "bridge".sync_labels = [code, json]
    rooms-node                                            behaviour "bridge".rooms_node (a folder), else exit 1
    run                                                   sleeps (a stand-in for the poller)
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT_GUESS = Path(os.path.abspath(__file__)).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_GUESS / "scripts"))
import _teststub  # noqa: E402

DEFAULT_DOCTOR = {
    "engine": "ok",
    "zalo_login": "ok",
    "listener": "ok",
    "server": "ok",
    "bridge_token": "ok",
    "room_platform": "warn",
}
DETAILS = {"zalo_login": "logged in as 999000111", "listener": "running"}


def _opt(argv, name, default=None):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return default


def _read_env(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _get(lines: list[str], key: str) -> str | None:
    for line in lines:
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    return None


def _set(lines: list[str], key: str, value: str, only_if_missing: bool = True) -> None:
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            if not only_if_missing:
                lines[i] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")


def _save(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def init_env(argv) -> int:
    root = Path(_opt(argv, "--repo-root", str(ROOT_GUESS)))
    mode = _opt(argv, "--mode", "personal")
    engine = _opt(argv, "--engine-bin")
    server_path = root / "apps" / "server" / ".dev.vars"
    runner_path = root / "apps" / "runner" / ".env"
    bridge_path = root / "apps" / "zalo-bridge" / ".env"
    server = _read_env(server_path)
    _set(server, "RUNNER_TOKEN", "runner-" + secrets.token_hex(24))
    _set(server, "STAFF_TOKEN", "staff-" + secrets.token_hex(24))
    _set(server, "ZALO_PERSONAL_WEBHOOK_SECRET", secrets.token_hex(32))
    _set(server, "ZALO_OA_SECRET_KEY", "dev-oa-" + secrets.token_hex(16))
    _set(server, "ZALO_APP_SECRET_KEY", "dev-app-" + secrets.token_hex(16))
    _set(server, "ENV", "dev", only_if_missing=False)
    _set(server, "ZALO_MODE", mode, only_if_missing=False)
    token = _get(server, "RUNNER_TOKEN") or ""
    secret = _get(server, "ZALO_PERSONAL_WEBHOOK_SECRET") or ""
    runner = _read_env(runner_path)
    _set(runner, "SERVER_URL", "http://127.0.0.1:8787", only_if_missing=False)
    _set(runner, "RUNNER_TOKEN", token, only_if_missing=False)
    _set(runner, "RUNNER_ID", "mac-local-1")
    bridge = _read_env(bridge_path)
    _set(bridge, "SERVER_URL", "http://127.0.0.1:8787", only_if_missing=False)
    _set(bridge, "RUNNER_TOKEN", token, only_if_missing=False)
    _set(bridge, "ZALO_PERSONAL_WEBHOOK_SECRET", secret, only_if_missing=False)
    _set(bridge, "BRIDGE_ID", "mac-bridge-1")
    if engine:
        _set(bridge, "ZALO_AGENT_BIN", engine)
    _save(server_path, server)
    _save(runner_path, runner)
    _save(bridge_path, bridge)
    print(json.dumps({"files": [str(server_path), str(runner_path), str(bridge_path)]}))
    return 0


def main(argv: list[str]) -> int:
    _teststub.record("bridge", argv)
    b = _teststub.behaviour("bridge")
    cmd = argv[0] if argv else ""
    if cmd == "init-env":
        return int(b.get("init_env_exit", 0)) or init_env(argv[1:])
    if cmd == "doctor":
        statuses = dict(DEFAULT_DOCTOR)
        statuses.update(b.get("doctor", {}))
        checks = [{"name": n, "status": s, "detail": DETAILS.get(n, n)} for n, s in statuses.items()]
        print(json.dumps({"checks": checks}, indent=1))
        return 1 if any(s == "fail" for s in statuses.values()) else 0
    if cmd == "listener":
        action = argv[1] if len(argv) > 1 else "status"
        defaults = {"start": [0, {"started": True}], "status": [0, {"running": True, "pid": 424242}],
                    "stop": [0, {"stopped": True}]}
        code, doc = (b.get("listener") or {}).get(action, defaults.get(action, [1, {}]))
        print(json.dumps(doc, indent=1))
        return int(code)
    if cmd == "sync-labels":
        code, doc = b.get("sync_labels", [0, {"contacts": {"customer": 2, "manager": 1, "staff": 1}}])
        print(json.dumps(doc, indent=1))
        return int(code)
    if cmd == "rooms-node":
        folder = b.get("rooms_node")
        if not folder:
            return 1
        print(folder)
        return 0
    if cmd == "run":
        time.sleep(300)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
