"""Supervise the zalo-agent `listen` daemon that posts incoming personal Zalo messages to the server webhook.

    zalo-agent --json [--account X] listen -d --filter user -e message --webhook <SERVER_URL>/zalo/personal/webhook

- The webhook secret goes in env ZALO_WEBHOOK_SECRET of that process (the daemon child inherits it). It is never
  a flag: flags are visible in `ps`, and the engine writes its start line to daemon.log (it masks flag secrets).
- Self messages stay on (no --no-self): staff typing on the phone shows up as isSelf=true and the server takes
  the conversation over.
- One WebSocket per account: never start a second listener. `start` checks `listen --status` first; a daemon that
  was not started with this webhook URL (for example the owner's own `zalo-agent mcp`) is left alone.
- Webhook delivery is durable inside the engine (an outbox on disk with retries); the server dedupes by msgId.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .engine import EngineResult, resolve_bin, run_engine

WEBHOOK_PATH = "/zalo/personal/webhook"
START_MARK = "starting daemon:"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_NOT_LOGGED_IN = 3
EXIT_FOREIGN_DAEMON = 4


def webhook_url(cfg: Config) -> str:
    return cfg.server_url + WEBHOOK_PATH


def mask_id(value: Any) -> str | None:
    s = str(value or "")
    return f"...{s[-4:]}" if len(s) > 4 else (s or None)


def _err(res: EngineResult, fallback: str) -> str:
    if res.missing:
        return res.stderr
    if res.timed_out:
        return "zalo-agent timed out"
    if res.error_text:
        return res.error_text
    line = (res.stderr or "").strip().splitlines()
    return line[-1][:300] if line else fallback


def login_state(cfg: Config, timeout: float = 45.0) -> dict[str, Any]:
    """`zalo-agent --json status`: logs in with the saved credentials (an HTTP login, no WebSocket)."""
    res = run_engine(cfg, ["status"], timeout=timeout)
    if not isinstance(res.data, dict) or res.error_text is not None:
        return {"logged_in": None, "error": _err(res, "no JSON from `zalo-agent status`")}
    acc = res.data.get("activeAccount") if isinstance(res.data.get("activeAccount"), dict) else {}
    return {"logged_in": bool(res.data.get("loggedIn")), "account": mask_id(res.data.get("ownId") or acc.get("ownId")),
            "has_account": bool(acc)}


def _daemon_start_line(log_path: str | None) -> str | None:
    """The last 'starting daemon: <args>' header the engine wrote to daemon.log (secrets masked by the engine)."""
    if not log_path:
        return None
    p = Path(log_path)
    try:
        size = p.stat().st_size
        with p.open("rb") as f:
            f.seek(max(0, size - 256 * 1024))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [ln for ln in tail.splitlines() if START_MARK in ln]
    return lines[-1] if lines else None


def status(cfg: Config, timeout: float = 20.0) -> dict[str, Any]:
    res = run_engine(cfg, ["listen", "--status"], timeout=timeout)
    if not isinstance(res.data, dict) or res.error_text is not None:
        return {"running": None, "error": _err(res, "no JSON from `zalo-agent listen --status`")}
    d = res.data
    out: dict[str, Any] = {"running": bool(d.get("running")), "pid": d.get("pid"),
                           "account": mask_id(d.get("accountId"))}
    if out["running"]:
        line = _daemon_start_line(d.get("logPath"))
        out["ours"] = None if line is None else (webhook_url(cfg) in line and "--webhook" in line)
        health = d.get("health")
        if isinstance(health, dict):
            # Field names from src/core/daemon-health.js snapshot().
            sock = health.get("socket") if isinstance(health.get("socket"), dict) else {}
            hook = health.get("webhook") if isinstance(health.get("webhook"), dict) else {}
            out["health"] = {"socket": sock.get("state"), "uptime_s": health.get("uptimeSec"),
                             "webhook_pending": hook.get("pending"), "webhook_dead": hook.get("dead"),
                             "webhook_failing": hook.get("consecutiveFailures"),
                             "warnings": len(health.get("warnings") or [])}
    return out


def start(cfg: Config, check_login: bool = True) -> tuple[int, dict[str, Any]]:
    if not resolve_bin(cfg):
        return EXIT_CONFIG, {"started": False, "error": f"zalo-agent not found: {cfg.zalo_agent_bin}"}
    if not cfg.webhook_secret:
        return EXIT_CONFIG, {"started": False,
                             "error": "ZALO_PERSONAL_WEBHOOK_SECRET is empty; refusing to send unsigned webhooks"}
    st = status(cfg)
    if st.get("running"):
        if st.get("ours") is False:
            return EXIT_FOREIGN_DAEMON, {"started": False, "already_running": True, "ours": False, "pid": st.get("pid"),
                                         "error": "a listen/mcp daemon without the bridge webhook holds this "
                                                  "account's WebSocket; stop it first (zalo-agent listen --stop)"}
        return EXIT_OK, {"started": False, "already_running": True, "ours": st.get("ours"), "pid": st.get("pid")}
    if st.get("running") is None and "No active account" not in str(st.get("error")):
        return EXIT_ERROR, {"started": False, "error": st.get("error")}
    if check_login:
        ls = login_state(cfg)
        if not ls.get("logged_in"):
            return EXIT_NOT_LOGGED_IN, {"started": False, "logged_in": False, "error": ls.get("error") or "not logged in"}
    res = run_engine(cfg, ["listen", "-d", "--filter", "user", "-e", "message", "--webhook", webhook_url(cfg)],
                     timeout=60.0, extra_env={"ZALO_WEBHOOK_SECRET": cfg.webhook_secret})
    if isinstance(res.data, dict) and res.error_text is None and res.data.get("pid"):
        return EXIT_OK, {"started": True, "pid": res.data.get("pid"), "account": mask_id(res.data.get("accountId")),
                         "log": res.data.get("logPath")}
    err = _err(res, "zalo-agent listen -d printed no JSON")
    code = EXIT_NOT_LOGGED_IN if any(s in err.lower() for s in ("login", "credentials", "no active account")) \
        else EXIT_ERROR
    return code, {"started": False, "error": err}


def stop(cfg: Config, only_ours: bool = False) -> tuple[int, dict[str, Any]]:
    if not resolve_bin(cfg):
        return EXIT_CONFIG, {"stopped": False, "error": f"zalo-agent not found: {cfg.zalo_agent_bin}"}
    st = status(cfg)
    if not st.get("running"):
        return EXIT_OK, {"stopped": False, "running": False, **({"error": st["error"]} if st.get("error") else {})}
    if only_ours and st.get("ours") is not True:
        return EXIT_OK, {"stopped": False, "running": True, "ours": st.get("ours"),
                         "note": "daemon was not started by the bridge; left running"}
    res = run_engine(cfg, ["listen", "--stop"], timeout=30.0)
    if isinstance(res.data, dict) and res.error_text is None:
        return EXIT_OK, {"stopped": bool(res.data.get("stopped")), "graceful": res.data.get("graceful")}
    return EXIT_ERROR, {"stopped": False, "error": _err(res, "zalo-agent listen --stop printed no JSON")}
