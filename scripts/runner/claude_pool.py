"""Pool of Claude subscription accounts for `claude -p`, with automatic and manual switching.

Each account is a separate Claude Code config dir (CLAUDE_CONFIG_DIR). Claude Code keeps one login per
config dir (its own Keychain item), so switching account = choosing the config dir for a call.
Every account dir's `projects/` is a symlink to one shared sessions dir, so a `--resume` session
started on one account can be found when the next call runs on another account.

Files (default root ~/.thomhouse-bot, override with THOMHOUSE_BOT_HOME), written atomically with mode 0600:
  accounts.json        [{"label", "config_dir" (null = default ~/.claude), "priority", "enabled"}]
  account-state.json   {label: {"status", "until", "last_error", "last_ok", "pinned"}}
  sessions/            shared `projects/` target for all pool accounts

last_error is only a short kind from ERROR_KINDS, never the CLI's output: that output can echo the transcript of the
call, which holds customer text. A raw text left by an older version is reduced to its kind on the next write.

CLI:
  python3 claude_pool.py add <label> [--priority N]   create the config dir; prints the login command
  python3 claude_pool.py add-default <label>          register the machine's default login (~/.claude)
  python3 claude_pool.py status                       login + plan + pool state of every account
  python3 claude_pool.py use <label>                  pin an account (manual switch); `use auto` unpins
  python3 claude_pool.py enable|disable <label>
  python3 claude_pool.py reset <label>                clear a limited / login_expired mark
  python3 claude_pool.py probe                        one tiny call through the pool, shows which account answered
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HOME = Path(os.environ.get("THOMHOUSE_BOT_HOME", Path.home() / ".thomhouse-bot"))
ACCOUNTS = HOME / "accounts.json"
STATE = HOME / "account-state.json"
SESSIONS = HOME / "sessions"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_lock = threading.Lock()

# Status values: ok | limited (until reset) | login_expired | blocked | error
LOGIN_MARKERS = ("oauth", "authenticate", "unauthorized", "401", "not logged in", "please run /login")
LIMIT_MARKERS = ("hit your weekly limit", "hit your session limit", "usage limit", "limit reached",
                 "rate limit", "429", "quota")
BLOCK_MARKERS = ("disabled", "suspended", "banned", "403", "forbidden")
# last_error values. limited / login_expired / blocked: the account's own problem (see classify). timeout: the call
# ran out of time. cli_error: the CLI answered with an error (non-zero exit or is_error) in JSON. parse_error: the
# CLI failed without a JSON object on stdout (crash, empty or garbled output).
ERROR_KINDS = ("limited", "login_expired", "blocked", "timeout", "cli_error", "parse_error")


# ---------------------------------------------------------------- storage

def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    """Atomic write with mode 0600: a temp file in the same folder, then rename over the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def accounts() -> list[dict]:
    return _read(ACCOUNTS, [])


def state() -> dict:
    return _read(STATE, {})


def error_kind(value) -> str:
    """The kind stored as last_error: a known kind stays; any other text (a raw CLI output written by an older
    version) becomes its classification, with the unclassified case as cli_error. Empty stays empty."""
    if not value:
        return ""
    text = str(value)
    if text in ERROR_KINDS:
        return text
    kind = classify(text)
    return kind if kind in ERROR_KINDS else "cli_error"


def _write_state(st: dict) -> None:
    """Every write of account-state.json goes here; it also cleans what an older version left in the file."""
    for entry in st.values():
        if isinstance(entry, dict) and entry.get("last_error"):
            entry["last_error"] = error_kind(entry["last_error"])
    _write(STATE, st)


def _set_state(label: str, **fields) -> None:
    with _lock:
        st = state()
        st.setdefault(label, {}).update(fields)
        _write_state(st)


# ---------------------------------------------------------------- error classification

def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """'resets Nov 11 at 2pm (Asia/Saigon)' / 'resets 5:30pm' -> aware datetime in Asia/Ho_Chi_Minh."""
    now = now or datetime.now(TZ)
    m = re.search(r"resets\s+(?:(\w{3})\s+(\d{1,2})\s+at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text, re.I)
    if not m:
        return None
    mon, day, hour, minute, ampm = m.groups()
    hour = int(hour) % 12 + (12 if ampm.lower() == "pm" else 0)
    minute = int(minute or 0)
    if mon:
        month = datetime.strptime(mon[:3].title(), "%b").month
        cand = datetime(now.year, month, int(day), hour, minute, tzinfo=TZ)
        if cand < now - timedelta(days=1):
            cand = cand.replace(year=now.year + 1)
        return cand
    cand = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return cand if cand > now else cand + timedelta(days=1)


def _has_marker(t: str, markers: tuple[str, ...]) -> bool:
    # Numeric HTTP codes must stand alone: the error text includes the CLI's JSON, whose session_id UUID
    # (e.g. "3f1c4019-...") would otherwise match "401" / "403" / "429" and mark a healthy account.
    for k in markers:
        if k.isdigit():
            if re.search(rf"(?<![\w-]){k}(?![\w-])", t):
                return True
        elif k in t:
            return True
    return False


def classify(text: str) -> str:
    t = text.lower()
    if _has_marker(t, LIMIT_MARKERS):
        return "limited"
    if _has_marker(t, LOGIN_MARKERS):
        return "login_expired"
    if _has_marker(t, BLOCK_MARKERS):
        return "blocked"
    return "error"


# ---------------------------------------------------------------- selection

def _env_for(acc: dict) -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # an API key would silently win over the subscription login
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    if acc.get("config_dir"):
        env["CLAUDE_CONFIG_DIR"] = acc["config_dir"]
    else:
        env.pop("CLAUDE_CONFIG_DIR", None)
    return env


def healthy(label: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    s = state().get(label, {})
    status = s.get("status", "ok")
    if status in ("ok", "error"):
        return True
    if status == "limited" and s.get("until"):
        return datetime.fromisoformat(s["until"]) <= now
    return False  # login_expired / blocked need a human


def candidates() -> list[dict]:
    """Pinned account first (if healthy), then enabled healthy accounts by priority."""
    accs = [a for a in accounts() if a.get("enabled", True)]
    accs.sort(key=lambda a: a.get("priority", 100))
    pinned = next((l for l, s in state().items() if s.get("pinned")), None)
    ordered = [a for a in accs if a["label"] == pinned] + [a for a in accs if a["label"] != pinned]
    return [a for a in ordered if healthy(a["label"])]


def run(args: list[str], cwd: Path, timeout: int = 600, extra_env: dict | None = None) -> dict:
    """Run `claude -p <args>` on the first healthy account; on a limit / login / block error,
    mark that account and retry once on the next one. Returns the CLI's JSON plus `_account`,
    `_switched_from` and `_wall_s`. When no account is usable, returns is_error with `_no_account`."""
    tried = []
    for acc in candidates():
        env = _env_for(acc)
        env.update(extra_env or {})
        t0 = time.time()
        try:
            p = subprocess.run(["claude", "-p", *args], cwd=cwd, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=timeout, env=env)
            out, err, code = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "timeout", -1
        try:
            res = json.loads(out)
            if not isinstance(res, dict):
                res = {}
        except json.JSONDecodeError:
            res = {}
        parsed = bool(res)
        res["_wall_s"] = round(time.time() - t0, 1)
        res["_account"] = acc["label"]
        res["_switched_from"] = tried[:]
        failed = code != 0 or bool(res.get("is_error")) or not res
        if not failed:
            _set_state(acc["label"], status="ok", last_ok=datetime.now(TZ).isoformat(), until=None)
            return res
        # The text stays in memory: it decides the kind and the reset time; only the kind is stored.
        text = f"{res.get('result', '')}\n{out}\n{err}"
        kind = classify(text) if err != "timeout" else "error"
        if kind == "limited":
            until = parse_reset(text) or datetime.now(TZ) + timedelta(hours=1)
            _set_state(acc["label"], status="limited", until=until.isoformat(), last_error="limited")
        elif kind in ("login_expired", "blocked"):
            _set_state(acc["label"], status=kind, last_error=kind)
        else:
            # Not the account's fault (bad session id, timeout, model error): do not switch account.
            failure = "timeout" if err == "timeout" else "cli_error" if parsed else "parse_error"
            _set_state(acc["label"], last_error=failure)
            res["is_error"] = True
            res.setdefault("result", text.strip()[:500])
            return res
        tried.append(acc["label"])
    return {"is_error": True, "result": "no usable Claude account in the pool", "_no_account": True,
            "_switched_from": tried, "_account": None}


# ---------------------------------------------------------------- CLI

def _auth_status(acc: dict) -> dict:
    try:
        p = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, env=_env_for(acc),
                           stdin=subprocess.DEVNULL, timeout=30)
        d = json.loads(p.stdout)
        return {k: d.get(k) for k in ("loggedIn", "email", "subscriptionType", "planTier")}
    except Exception as e:  # noqa: BLE001 - status display only
        return {"error": f"{type(e).__name__}: {e}"}


def cmd_add(label: str, priority: int, default: bool) -> None:
    accs = accounts()
    if any(a["label"] == label for a in accs):
        sys.exit(f"account {label!r} already exists")
    cfg = None
    if not default:
        cfg = HOME / "accounts" / label
        cfg.mkdir(parents=True, exist_ok=True)
        SESSIONS.mkdir(parents=True, exist_ok=True)
        link = cfg / "projects"
        if not link.exists():
            link.symlink_to(SESSIONS, target_is_directory=True)
    accs.append({"label": label, "config_dir": str(cfg) if cfg else None, "priority": priority, "enabled": True})
    _write(ACCOUNTS, accs)
    print(f"added {label}")
    if cfg:
        print(f"log this account in once (opens the browser):\n  CLAUDE_CONFIG_DIR={cfg} claude auth login")


def cmd_status() -> None:
    st = state()
    pinned = next((l for l, s in st.items() if s.get("pinned")), None)
    for a in sorted(accounts(), key=lambda a: a.get("priority", 100)):
        s = st.get(a["label"], {})
        print(json.dumps({"label": a["label"], "priority": a.get("priority"), "enabled": a.get("enabled", True),
                          "pinned": a["label"] == pinned, "pool_status": s.get("status", "ok"),
                          "until": s.get("until"), "usable_now": healthy(a["label"]),
                          "login": _auth_status(a), "last_error": error_kind(s.get("last_error"))},
                         ensure_ascii=False))
    print("next account:", (candidates() or [{"label": None}])[0]["label"])


def cmd_use(label: str) -> None:
    with _lock:
        st = state()
        for v in st.values():
            v["pinned"] = False
        if label != "auto":
            if not any(a["label"] == label for a in accounts()):
                sys.exit(f"unknown account {label!r}")
            st.setdefault(label, {})["pinned"] = True
        _write_state(st)
    print("pinned:", label)


def cmd_toggle(label: str, enabled: bool) -> None:
    accs = accounts()
    for a in accs:
        if a["label"] == label:
            a["enabled"] = enabled
    _write(ACCOUNTS, accs)
    print(label, "enabled" if enabled else "disabled")


def cmd_probe() -> None:
    probe_dir = HOME / "probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    res = run(["--model", "claude-opus-5-5", "--effort", "low", "--setting-sources", "project",
               "--strict-mcp-config", "--tools", "", "--no-session-persistence", "--output-format", "json",
               "--system-prompt", "Reply with exactly: ok", "--", "ping"], probe_dir, timeout=120,
              extra_env={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
    print(json.dumps({k: res.get(k) for k in ("_account", "_switched_from", "is_error", "result", "_wall_s")},
                     ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("label"); a.add_argument("--priority", type=int, default=100)
    d = sub.add_parser("add-default"); d.add_argument("label"); d.add_argument("--priority", type=int, default=100)
    sub.add_parser("status")
    u = sub.add_parser("use"); u.add_argument("label")
    e = sub.add_parser("enable"); e.add_argument("label")
    x = sub.add_parser("disable"); x.add_argument("label")
    r = sub.add_parser("reset"); r.add_argument("label")
    sub.add_parser("probe")
    ns = ap.parse_args()
    if ns.cmd == "add":
        cmd_add(ns.label, ns.priority, default=False)
    elif ns.cmd == "add-default":
        cmd_add(ns.label, ns.priority, default=True)
    elif ns.cmd == "status":
        cmd_status()
    elif ns.cmd == "use":
        cmd_use(ns.label)
    elif ns.cmd in ("enable", "disable"):
        cmd_toggle(ns.label, ns.cmd == "enable")
    elif ns.cmd == "reset":
        _set_state(ns.label, status="ok", until=None)
        print("reset", ns.label)
    elif ns.cmd == "probe":
        cmd_probe()


if __name__ == "__main__":
    main()
