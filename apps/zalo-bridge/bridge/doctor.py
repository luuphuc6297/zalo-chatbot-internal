"""`bridge doctor`: check every link between the owner's Zalo account, the engine, the bridge and the server.

Each check is {"name", "status": ok|warn|fail, "detail"}. Never prints a token, a secret or a full Zalo id.
The login check runs `zalo-agent --json status`, which logs in with the saved credentials over HTTP.

The last check, `room_platform`, reports the optional room platform (rooms.py; docs/contracts.md 14.10): installed
or not, its node, whether its server answers on 127.0.0.1:8799, whether its config file is there, and the runner's
engine setting. It is `ok` or `warn`, never `fail`: without the platform the runner drafts with the direct engine.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from . import listener, rooms
from .api import ApiError, BridgeApi, ServerUnavailable
from .config import ENGINE_VERSION, Config
from .engine import resolve_bin, run_engine


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _node_major() -> int | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v?(\d+)", out.strip())
    return int(m.group(1)) if m else None


def room_platform_check(facts: dict[str, Any]) -> dict[str, str]:
    """One check from rooms.platform_facts(). Warns only when the runner is set to use the rooms and a part of the
    platform is missing, or when a configured setting is wrong."""
    engine = str(facts.get("engine") or "claude")
    setting = f"runner THOMHOUSE_DRAFT_ENGINE={engine}"
    problems: list[str] = []
    if engine not in rooms.DRAFT_ENGINES:
        problems.append("unknown engine setting (expected claude or rooms)")
    if not facts.get("installed"):
        if engine == "rooms":
            problems.append("the runner falls back to the direct engine")
        detail = f"not installed (optional; tools/openmausbot); {setting}"
        return _check("room_platform", "warn" if problems else "ok",
                      detail + ("; " + "; ".join(problems) if problems else ""))

    parts = ["installed"]
    missing: list[str] = []          # matters only when the runner is set to use the rooms
    major = facts.get("node_major")
    if major is not None and major >= rooms.NODE_MIN_MAJOR:
        parts.append(f"node {major}")
    else:
        found = "no node" if major is None else f"node {major}"
        where = "OPENMAUSBOT_NODE_DIR" if facts.get("node_dir_configured") else "PATH or ~/.nvm/versions/node"
        parts.append(f"{found} in {where} (needs Node {rooms.NODE_MIN_MAJOR}+)")
        if facts.get("node_dir_configured"):
            problems.append(f"OPENMAUSBOT_NODE_DIR has no node {rooms.NODE_MIN_MAJOR}+")
        else:
            missing.append("node")
    where = f"{rooms.PLATFORM_HOST}:{facts.get('port', rooms.PLATFORM_PORT)}"
    if facts.get("listening"):
        parts.append(f"server answers on {where}")
    else:
        parts.append(f"no server on {where} (scripts/start_local.sh starts it)")
        missing.append("server")
    if facts.get("config"):
        parts.append("config file present")
    else:
        parts.append("config file missing (python3 -m runner.main rooms-setup writes it)")
        missing.append("config file")
    if engine == "rooms" and missing:
        problems.append("the runner falls back to the direct engine until this is fixed: " + ", ".join(missing))
    parts.append(setting)
    return _check("room_platform", "warn" if problems else "ok",
                  "; ".join(parts) + ("; " + "; ".join(problems) if problems else ""))


def run_checks(cfg: Config, api: BridgeApi | None = None) -> list[dict[str, str]]:
    api = api or BridgeApi(cfg.server_url, cfg.runner_token, cfg.bridge_id)
    checks: list[dict[str, str]] = []
    login_cmd = f"{cfg.zalo_agent_bin} login"

    major = _node_major()
    if major is None:
        checks.append(_check("node", "fail", "node not found on PATH (the engine needs Node 22+)"))
    elif major < 22:
        checks.append(_check("node", "fail", f"node {major}; the engine needs Node 22+"))
    else:
        checks.append(_check("node", "ok", f"node {major}"))

    exe = resolve_bin(cfg)
    if not exe:
        checks.append(_check("engine", "fail", f"zalo-agent not found ({cfg.zalo_agent_bin}); run scripts/start_local.sh"))
    else:
        res = run_engine(cfg, ["--version"], timeout=30, json_mode=False, account=False)
        version = (res.stdout or "").strip().splitlines()[-1:] or [""]
        v = version[0].strip()
        if res.returncode == 0 and v == ENGINE_VERSION:
            checks.append(_check("engine", "ok", f"zalo-agent {v} at {exe}"))
        elif res.returncode == 0 and v:
            checks.append(_check("engine", "warn", f"zalo-agent {v} at {exe}; the bridge was checked against {ENGINE_VERSION}"))
        else:
            checks.append(_check("engine", "fail", f"`zalo-agent --version` failed: {(res.stderr or '').strip()[:200]}"))

    checks.append(_check("webhook_secret", "ok" if cfg.webhook_secret else "fail",
                         "ZALO_PERSONAL_WEBHOOK_SECRET is set" if cfg.webhook_secret
                         else "ZALO_PERSONAL_WEBHOOK_SECRET is empty in apps/zalo-bridge/.env"))

    if exe:
        ls = listener.login_state(cfg)
        if ls.get("logged_in"):
            checks.append(_check("zalo_login", "ok", f"logged in (account {ls.get('account')})"))
        elif ls.get("logged_in") is False:
            checks.append(_check("zalo_login", "fail", f"not logged in; the owner runs: {login_cmd}"))
        else:
            checks.append(_check("zalo_login", "fail", f"could not read login state: {ls.get('error')}"))

        st = listener.status(cfg)
        if st.get("running") and st.get("ours"):
            h = st.get("health") or {}
            detail = f"running (pid {st.get('pid')}), webhook {listener.webhook_url(cfg)}"
            problems = []
            if h.get("socket") not in (None, "up"):
                problems.append(f"socket {h.get('socket')}")
            if h.get("webhook_dead"):
                problems.append(f"{h['webhook_dead']} webhook event(s) dead-lettered (server refused them)")
            if h.get("webhook_failing"):
                problems.append(f"webhook failing x{h['webhook_failing']}")
            checks.append(_check("listener", "warn" if problems else "ok",
                                 detail + ("; " + "; ".join(problems) if problems else "")))
        elif st.get("running"):
            checks.append(_check("listener", "warn" if st.get("ours") is None else "fail",
                                 f"a daemon runs (pid {st.get('pid')}) but "
                                 + ("its webhook could not be read from daemon.log" if st.get("ours") is None
                                    else "not with the bridge webhook; stop it: zalo-agent listen --stop")))
        elif st.get("running") is False:
            checks.append(_check("listener", "fail", "not running; start it: python3 -m bridge.main listener start"))
        else:
            checks.append(_check("listener", "fail", f"could not read listener status: {st.get('error')}"))
    else:
        checks.append(_check("zalo_login", "fail", "skipped: zalo-agent not installed"))
        checks.append(_check("listener", "fail", "skipped: zalo-agent not installed"))

    try:
        h = api.health()
        mode = h.get("zalo_mode")
        checks.append(_check("server", "ok" if mode == "personal" else "warn",
                             f"{cfg.server_url} answers, ZALO_MODE={mode}"
                             + ("" if mode == "personal" else " (expected personal; outbox rows are not for the bridge)")))
    except (ServerUnavailable, ApiError) as e:
        checks.append(_check("server", "fail", f"{cfg.server_url}/health: {e}"))

    try:
        s = api.status()
        counts = s.get("counts") if isinstance(s.get("counts"), dict) else {}
        unknown = int(counts.get("unknown") or 0)
        detail = "bridge token accepted" + (f"; outbox {counts}" if counts else "")
        if unknown:
            detail += f"; {unknown} message(s) with unknown outcome need staff"
        checks.append(_check("bridge_token", "warn" if unknown else "ok", detail))
    except ApiError as e:
        why = {401: "token rejected: RUNNER_TOKEN in apps/zalo-bridge/.env differs from apps/server/.dev.vars",
               404: "server has no /bridge API (needs the personal Zalo channel build)"}.get(e.status, str(e))
        checks.append(_check("bridge_token", "fail", why))
    except ServerUnavailable as e:
        checks.append(_check("bridge_token", "fail", f"server unavailable: {e}"))

    try:
        checks.append(room_platform_check(rooms.platform_facts()))
    except Exception as e:  # noqa: BLE001 - an optional part must never break the doctor
        checks.append(_check("room_platform", "warn", f"could not be inspected ({type(e).__name__})"))
    return checks


def summary_exit(checks: list[dict[str, Any]]) -> int:
    return 1 if any(c["status"] == "fail" for c in checks) else 0
