"""The local stack: services and the PID rule of `start_local.sh`, other installations, start and stop through the
existing scripts, the health gate and loopback HTTP (14.10, 16.3.3, rev F4, F12, F14, F18, F20).

The commands `start`, `stop` and `restart` live in WP5 `service.py`; this module holds what they and the install
steps share.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .context import Exit
from .paths import Paths

SERVICES: tuple[tuple[str, str], ...] = (
    ("server", "<app>/apps/server/"),
    ("cron", "__scheduled"),
    ("runner", "runner.main"),
    ("bridge", "bridge.main"),
    ("console", "<app>/apps/console/"),
    ("openmausbot", "<app>/tools/openmausbot/"),
)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
DEFAULT_SERVER_URL = "http://127.0.0.1:8787"
DEFAULT_CONSOLE_URL = "http://127.0.0.1:5173"


@dataclass
class Service:
    """One service of `start_local.sh`; `pattern` with `<app>` filled in; `cwd` (a real path) only when alive."""

    name: str
    pattern: str
    pid: int | None
    alive: bool
    cwd: Path | None


def _ps(args: list[str]) -> str:
    try:
        cp = subprocess.run(["ps", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return cp.stdout if cp.returncode == 0 else ""


def _command_line(pid: int) -> str:
    return _ps(["-ww", "-o", "command=", "-p", str(pid)]).strip()


def _start_time(pid: int) -> str:
    return _ps(["-o", "lstart=", "-p", str(pid)]).strip()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_of(paths: Paths, name: str) -> int | None:
    try:
        text = (paths.run_dir / f"{name}.pid").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() and int(text) > 0 else None


def _pattern(paths: Paths, pattern: str) -> str:
    return pattern.replace("<app>", str(paths.app))


def _cwd_of(pid: int) -> Path | None:
    try:
        cp = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in cp.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            return Path(line[1:])
    return None


def _running(paths: Paths, name: str, pattern: str) -> tuple[int | None, bool]:
    pid = _pid_of(paths, name)
    if pid is None or not _alive(pid):
        return pid, False
    if _pattern(paths, pattern) not in _command_line(pid):
        return pid, False
    start_file = paths.run_dir / f"{name}.start"
    if start_file.exists():
        try:
            recorded = start_file.read_text(encoding="utf-8").strip()
        except OSError:
            recorded = ""
        if _start_time(pid) != recorded:
            return pid, False
    return pid, True


def services(paths: Paths) -> list[Service]:
    """Every service of SERVICES with its PID file and the `is_running` rule of `start_local.sh:83-93`: the PID is
    alive, its command line contains the pattern, and its start time equals `<name>.start` when that file exists."""
    out = []
    for name, pattern in SERVICES:
        pid, alive = _running(paths, name, pattern)
        cwd = _cwd_of(pid) if alive and pid is not None else None
        out.append(Service(name=name, pattern=_pattern(paths, pattern), pid=pid, alive=alive, cwd=cwd))
    return out


def is_running(paths: Paths, name: str) -> bool:
    """The `is_running` rule for one service name of SERVICES; False for an unknown name."""
    for svc_name, pattern in SERVICES:
        if svc_name == name:
            return _running(paths, name, pattern)[1]
    return False


def _under(child: Path, parent: str) -> bool:
    c = os.path.realpath(str(child))
    return c == parent or c.startswith(parent.rstrip("/") + "/")


def other_stacks(paths: Paths) -> list[Service]:
    """Live services of BOT_HOME/run that belong to another installation (rev F20, rev check).

    A PID file counts when its process is alive, its start time equals `<name>.start` (when that file exists) and
    its command line contains the path-free part of the service's pattern ("/apps/server/", "runner.main", ...),
    so a server or console that another installation started from its own folder is seen too. A service belongs
    to this installation when its command line contains "<app>/" (the logical path that `start_local.sh` passes)
    or "<realpath(app)>/", or when its working folder (`lsof -a -d cwd -p PID -Fn`, a real path) lies under
    realpath(app). The cron ticker, whose command line holds no path, belongs where the server belongs (and to
    this installation when no server runs). A command line is never compared with the real path alone.
    """
    logical = str(paths.app).rstrip("/") + "/"
    real = os.path.realpath(str(paths.app))
    real_slash = real.rstrip("/") + "/"
    seen: list[tuple[Service, str]] = []
    for name, pattern in SERVICES:
        pid = _pid_of(paths, name)
        if pid is None or not _alive(pid):
            continue
        cmd = _command_line(pid)
        if pattern.replace("<app>", "") not in cmd:
            continue
        start_file = paths.run_dir / f"{name}.start"
        if start_file.exists():
            try:
                recorded = start_file.read_text(encoding="utf-8").strip()
            except OSError:
                recorded = ""
            if _start_time(pid) != recorded:
                continue
        cwd = None if name == "cron" else _cwd_of(pid)
        seen.append((Service(name=name, pattern=_pattern(paths, pattern), pid=pid, alive=True, cwd=cwd), cmd))
    verdict: dict[str, bool] = {}
    for svc, cmd in seen:
        if svc.name != "cron":
            verdict[svc.name] = (logical in cmd or real_slash in cmd
                                 or (svc.cwd is not None and _under(svc.cwd, real)))
    out = []
    for svc, _ in seen:
        ours = verdict.get("server", True) if svc.name == "cron" else verdict[svc.name]
        if not ours:
            out.append(svc)
    return out


def start(ctx, *, quiet: bool = False, during_update: bool = False) -> int:
    """Run `<app>/scripts/start_local.sh` with cwd `<app>` and `proc.child_env`; return its exit code.

    Raises `Exit(3, "core.moved_out")` while `BOT_HOME/moved-out.json` exists (rev F12) and
    `Exit(3, "core.update_open")` while an update journal is open, unless `during_update` (rev F14). The script's
    stdout and stderr go only to `logs/start.log` (rev F18). Prints one line `core.starting` unless `quiet`.
    """
    from . import proc, state
    from .text_vi import say

    paths = ctx.paths
    if state.moved_out(paths) is not None:
        raise Exit(3, "core.moved_out")
    journal = state.update_open(paths)
    if journal is not None and not during_update:
        raise Exit(3, "core.update_open", file=str(journal.get("file") or ""))
    if not (quiet or ctx.quiet):
        say("core.starting")
    script = paths.app / "scripts" / "start_local.sh"
    res = proc.run(ctx, ["/bin/bash", str(script)], cwd=paths.app, log=paths.logs / "start.log")
    ctx.log("stack_start", exit=res.returncode, during_update=during_update)
    return res.returncode


def stop(ctx) -> bool:
    """Record the PIDs and start times of the running services, run `<app>/scripts/stop_local.sh` (output in
    `logs/start.log`), and return True when none of those processes is alive afterwards."""
    from . import proc

    paths = ctx.paths
    before = [(s.pid, _start_time(s.pid)) for s in services(paths) if s.alive and s.pid is not None]
    script = paths.app / "scripts" / "stop_local.sh"
    res = proc.run(ctx, ["/bin/bash", str(script)], cwd=paths.app, log=paths.logs / "start.log")
    survivors = []
    for pid, started in before:
        if _alive(pid) and (not started or _start_time(pid) == started):
            survivors.append(pid)
    ctx.log("stack_stop", exit=res.returncode, survivors=len(survivors))
    return not survivors


def _health_failures(ctx) -> list[str]:
    paths = ctx.paths
    failed = []
    mode = ctx.env.get("THOMHOUSE_ZALO_MODE", "personal")
    needed = ["server", "cron", "runner", "console"] + (["bridge"] if mode == "personal" else [])
    if not all(is_running(paths, n) for n in needed):
        failed.append("processes")
    code, body = http_json(ctx, "GET", "/health")
    if not (code == 200 and isinstance(body, dict) and body.get("zalo_mode") == mode):
        failed.append("server_health")
    console = ctx.env.get("THOMHOUSE_CONSOLE_URL") or DEFAULT_CONSOLE_URL
    code, _ = http_json(ctx, "GET", console.rstrip("/") + "/")
    if code == 0:
        failed.append("console")
    return failed


def health_gate(ctx) -> list[str]:
    """Wait up to THOMHOUSE_HEALTH_WAIT_S seconds (default 20) and return the ids among "processes",
    "server_health", "console" that still fail (the rules of doctor checks 31, 32, 35). Returns early when all
    pass; with 0 seconds it checks once."""
    try:
        wait = float(ctx.env.get("THOMHOUSE_HEALTH_WAIT_S", "20"))
    except ValueError:
        wait = 20.0
    deadline = time.monotonic() + max(wait, 0.0)
    while True:
        failed = _health_failures(ctx)
        if not failed or time.monotonic() >= deadline:
            return failed
        time.sleep(1.0)


def _check_loopback(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in LOOPBACK_HOSTS:
        raise ValueError("only loopback hosts are allowed")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: urllib would copy the Authorization header to the new host (invariant 4)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        return None


def http_json(
    ctx, method: str, path: str, *, token: str | None = None, body: object | None = None, timeout: float = 3.0
) -> tuple[int, object | None]:
    """One HTTP call to the loopback server and the parsed JSON answer.

    A `path` starting with "/" is appended to THOMHOUSE_SERVER_URL (default http://127.0.0.1:8787); otherwise it
    is a full URL. ValueError for a host other than 127.0.0.1, localhost or ::1. The opener has no proxy
    (invariant 11) and follows no redirect, so a 30x answer is returned as its status and the token never reaches
    another host. `token` is sent as a Bearer header. Returns (status, JSON or None); (0, None) without a
    connection.
    """
    base = ctx.env.get("THOMHOUSE_SERVER_URL") or DEFAULT_SERVER_URL
    url = base.rstrip("/") + path if path.startswith("/") else path
    _check_loopback(url)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read()
        except OSError:
            raw = b""
        finally:
            e.close()
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return 0, None
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        parsed = None
    return status, parsed
