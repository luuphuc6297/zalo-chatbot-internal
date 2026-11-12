"""The human steps of 16.6: Claude login, Zalo QR login, history sync, the two analyzers, labels and the staff token.

Each step has a flow that returns `(status, reason)` (status done, pending, skipped or failed; reason a 16.4.4 code),
used by the install steps 14 and 16 to 21 (`steps.py`) and by the commands `login-claude`, `add-claude`,
`login-zalo`, `sync-history`, `analyze`, `labels` and `staff-token`. Commands return 0 when done, 1 on a failure and
4 when the person answered `s` or nobody could answer.

Nothing personal leaves this module: the output of `claude auth status` is read through `accounts.auth_status`
(three fields), the events of `zalo-agent --json login` are read in memory and dropped (never the QR data URL,
the name or the Zalo id), the output of `zalo-agent sync` is discarded, the analyzers' output is read in memory
only, and `STAFF_TOKEN` goes only to `pbcopy` and to the loopback server (invariants 4 and 8).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import accounts, bridgecli, consent, envs, proc, stack, state
from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK
from .text_vi import say

QR_PORT = 18927  # the engine's QR page; it falls back to 8080, 3000, 9000 when this one is busy
ZALO_LOGIN_TIMEOUT_S = 300.0
SYNC_WINDOW_S = 180.0  # the phone shows its "sync now" button for about 3 minutes
SYNC_TICK_S = 30.0
DEFAULT_SYNC_TIMEOUT_S = 600.0
ANALYZER_TIMEOUT_S = 3600.0
DEFAULT_CLIPBOARD_S = 120
POSTPONED = ("later", "declined", "console_login", "no_subscription")


# ---------------------------------------------------------------- shared helpers

def tilde(path: Path, home: Path) -> str:
    """`path` with the home folder written as `~`."""
    text = str(path)
    base = str(home).rstrip("/")
    if base and (text == base or text.startswith(base + "/")):
        return "~" + text[len(base):]
    return text


def tb(ctx) -> str:
    """How the person types this program: the launcher (`~/ThomHouse/bin/thomhouse`), or the checkout form."""
    if ctx.paths.mode != "installed":
        return "python3 -I install/thomhouse.py"
    return tilde(ctx.paths.launcher, ctx.paths.home)


def _engine(ctx) -> Path:
    return ctx.paths.app / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent"


def _stop_group(child: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
        if child.poll() is not None:
            return
        try:
            os.killpg(child.pid, sig)
        except (ProcessLookupError, PermissionError):
            try:
                child.send_signal(sig)
            except ProcessLookupError:
                return
        try:
            child.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def _record(ctx, step_id: str, status: str, reason: str | None) -> None:
    state.step_set(ctx.paths, step_id, status, reason)


def _exit_for(status: str, reason: str | None) -> int:
    if status == "done":
        return EXIT_OK
    if status == "pending" and reason in POSTPONED:
        return EXIT_DECLINED
    return EXIT_FAILED


def _finish(ctx, step_id: str, outcome: tuple[str, str | None]) -> int:
    status, reason = outcome
    _record(ctx, step_id, status, reason)
    return _exit_for(status, reason)


# ---------------------------------------------------------------- Claude login (16.6.1, rev F8, F17)

def _needs_login(ctx, account: accounts.Account) -> bool:
    """True unless the account is enabled and logged in with a claude.ai login. An account the owner enabled by
    hand while Claude reports no plan counts as logged in (16.6.1, rev check)."""
    if not account.enabled:
        return True
    status = accounts.auth_status(ctx, account)
    return not (status.logged_in and status.auth_method == "claude.ai")


def claude_logins_ok(ctx) -> bool:
    """The check of step 14: the pool has accounts and none needs a login."""
    pool = accounts.load(ctx)
    return bool(pool) and not any(_needs_login(ctx, a) for a in pool)


def _claude_env(ctx, account: accounts.Account) -> dict[str, str]:
    extra = {"CLAUDE_CONFIG_DIR": str(account.config_dir)} if account.config_dir else None
    return proc.child_env(ctx.paths, extra)


def claude_login_flow(ctx, account: accounts.Account) -> tuple[str, str | None]:
    """16.6.1 for one pool account: `claude auth login` with its CLAUDE_CONFIG_DIR, then the three status fields.
    Only a claude.ai login with a plan enables and resets the account; a Console login is logged out again."""
    say("setup.claude_account", label=account.label)
    if consent.ask(ctx, "setup.claude_screen", "cs") != "c":
        say("setup.claude_later", tb=tb(ctx))
        return "pending", "later"
    env = _claude_env(ctx, account)
    login = True
    while True:
        if login:
            proc.run(ctx, ["claude", "auth", "login"], env=env, interactive=True)
        login = True
        status = accounts.auth_status(ctx, account)
        ctx.log("claude_login", label=account.label, logged_in=status.logged_in, method=status.auth_method,
                plan=bool(status.subscription))
        if status.ok:
            if accounts.pool(ctx, "enable", account.label) != 0 or accounts.pool(ctx, "reset", account.label) != 0:
                say("setup.claude_enable_failed", label=account.label, tb=tb(ctx))
                return "failed", None
            say("setup.claude_done")
            say("setup.claude_browser_logout")
            return "done", None
        if status.logged_in and status.auth_method != "claude.ai":
            proc.run(ctx, ["claude", "auth", "logout"], env=env, timeout=60)  # output discarded
            if consent.ask(ctx, "setup.claude_console", "cs") != "c":
                say("setup.claude_later", tb=tb(ctx))
                return "pending", "console_login"
            continue
        if status.logged_in:  # claude.ai without a plan: no logout, `c` reads the status again
            if consent.ask(ctx, "setup.claude_no_plan", "cs") != "c":
                say("setup.claude_later", tb=tb(ctx))
                return "pending", "no_subscription"
            login = False
            continue
        if consent.ask(ctx, "setup.claude_not_logged_in", "cs") != "c":
            say("setup.claude_later", tb=tb(ctx))
            return "pending", "later"


def claude_logins_flow(ctx) -> tuple[str, str | None]:
    """Step 14: every account that needs a login, in priority order; `s` postpones the remaining ones. After a
    move-in there are several such accounts and no `main` (rev check)."""
    pool = accounts.load(ctx)
    if not pool:
        say("setup.claude_no_pool", tb=tb(ctx))
        return "failed", None
    for account in pool:
        if not _needs_login(ctx, account):
            continue
        outcome = claude_login_flow(ctx, account)
        if outcome[0] != "done":
            return outcome
    return "done", None


def _finish_claude(ctx, outcome: tuple[str, str | None]) -> int:
    status, reason = outcome
    if status == "done":
        if claude_logins_ok(ctx):
            _record(ctx, "claude_login", "done", None)
        return EXIT_OK
    if status == "pending":
        _record(ctx, "claude_login", "pending", reason)
    return _exit_for(status, reason)


def cmd_login_claude(ctx, args) -> int:
    """`thomhouse login-claude [LABEL]`: LABEL, else `main` when it exists, else the first account step 14 would
    ask for (after a move-in there is no `main`)."""
    pool = accounts.load(ctx)
    if not pool:
        say("setup.claude_no_pool", tb=tb(ctx))
        return EXIT_FAILED
    label = getattr(args, "label", None)
    if label is None:
        if any(a.label == "main" for a in pool):
            label = "main"
        else:
            waiting = [a for a in pool if _needs_login(ctx, a)]
            label = (waiting or pool)[0].label
    account = next((a for a in pool if a.label == label), None)
    if account is None:
        say("setup.claude_unknown_label", label=label)
        return EXIT_FAILED
    return _finish_claude(ctx, claude_login_flow(ctx, account))


def cmd_add_claude(ctx, args) -> int:
    """`thomhouse add-claude LABEL [--priority N]`: add the account disabled, then log it in (16.6.1)."""
    label = str(args.label)
    if any(a.label == label for a in accounts.load(ctx)):
        say("setup.claude_label_exists", label=label, tb=tb(ctx))
        return EXIT_FAILED
    priority = str(getattr(args, "priority", 100))
    if accounts.pool(ctx, "add", label, "--priority", priority) != 0 or accounts.pool(ctx, "disable", label) != 0:
        say("setup.claude_add_failed", label=label)
        return EXIT_FAILED
    account = next((a for a in accounts.load(ctx) if a.label == label), None)
    if account is None:
        say("setup.claude_add_failed", label=label)
        return EXIT_FAILED
    code = _finish_claude(ctx, claude_login_flow(ctx, account))
    if stack.is_running(ctx.paths, "openmausbot"):  # rooms-setup runs only while the platform is stopped
        say("setup.claude_restart_rooms", tb=tb(ctx))
    return code


# ---------------------------------------------------------------- Zalo QR login (16.6.2)

def _port_free(port: int) -> bool:
    """True when nothing accepts connections on 127.0.0.1:`port` (probed by connecting; nothing listens here)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", port))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def _event(raw: bytes) -> dict | None:
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _login_once(ctx) -> bool:
    """One `zalo-agent --json login` (no QR address option, no credentials option); True on `login_success`.

    stdout is read line by line in memory; every event is dropped after its name (and, for the first `qr` event
    when the QR port was busy, its local file) was used. Nothing of it is printed or logged.
    """
    free = _port_free(QR_PORT)
    env = proc.child_env(ctx.paths)
    env["ZALO_AGENT_NO_UPDATE_CHECK"] = "1"
    try:
        child = subprocess.Popen([str(_engine(ctx)), "--json", "login"], cwd=str(ctx.paths.app), env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
    except OSError:
        return False
    assert child.stdout is not None
    fd = child.stdout.fileno()
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    deadline = time.monotonic() + ZALO_LOGIN_TIMEOUT_S
    buffer = b""
    opened = success = finished = False
    try:
        while not finished:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            if not selector.select(timeout=min(left, 0.5)):
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer and not finished:
                raw, buffer = buffer.split(b"\n", 1)
                data = _event(raw)
                name = data.get("event") if data else None
                if name == "qr" and not opened:
                    target = f"http://127.0.0.1:{QR_PORT}/qr" if free else data.get("file")
                    if isinstance(target, str) and target:
                        proc.run(ctx, ["open", target], timeout=30)
                    say("setup.zalo_qr_opened")
                    opened = True
                elif name == "qr_scanned":
                    say("setup.zalo_scanned")
                elif name in ("qr_declined", "login_error"):
                    finished = True
                elif name == "login_success":
                    success = finished = True
                data = None
    finally:
        selector.close()
        if success:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _stop_group(child)
        else:
            _stop_group(child)
        child.stdout.close()
        buffer = b""
    ctx.log("zalo_login", success=success, exit=child.returncode)
    return success


def _start_listener(ctx) -> str:
    """`listener start` after a login: "done", "retry" (exit 3, not logged in), "later" or "failed"."""
    while True:
        code, _ = bridgecli.listener(ctx, "start")
        if code == 0:
            return "done"
        if code == 3:
            return "retry"
        if code == 4:
            if consent.ask(ctx, "setup.zalo_foreign", "cs") != "c":
                return "later"
            proc.run(ctx, [str(_engine(ctx)), "listen", "--stop"], cwd=ctx.paths.app, timeout=60)
            continue
        return "failed"


def zalo_login_flow(ctx) -> tuple[str, str | None]:
    """16.6.2: the QR login through the engine's JSON events, then the listener."""
    if not _engine(ctx).exists():
        say("setup.zalo_no_engine", tb=tb(ctx))
        return "failed", None
    if consent.ask(ctx, "setup.zalo_screen", "cs") != "c":
        say("setup.zalo_later", tb=tb(ctx))
        return "pending", "later"
    while True:
        if _login_once(ctx):
            result = _start_listener(ctx)
            if result == "done":
                say("setup.zalo_done")
                return "done", None
            if result == "later":
                say("setup.zalo_later", tb=tb(ctx))
                return "pending", "later"
            if result == "failed":
                say("setup.zalo_listener_failed", tb=tb(ctx))
                return "pending", None
        if consent.ask(ctx, "setup.zalo_retry", "cs") != "c":
            say("setup.zalo_later", tb=tb(ctx))
            return "pending", "later"


def cmd_login_zalo(ctx, args) -> int:
    """`thomhouse login-zalo`."""
    return _finish(ctx, "zalo_login", zalo_login_flow(ctx))


# ---------------------------------------------------------------- history sync (16.6.3)

def _sync_timeout(ctx) -> float:
    try:
        value = float(ctx.env.get("THOMHOUSE_SYNC_TIMEOUT_S", DEFAULT_SYNC_TIMEOUT_S))
    except ValueError:
        return DEFAULT_SYNC_TIMEOUT_S
    return value if value > 0 else DEFAULT_SYNC_TIMEOUT_S


def _sync_once(ctx, *, force: bool) -> int:
    """`zalo-agent --json sync --days 365 --no-media --no-cloud [-F]`, output discarded; prints the countdown every
    SYNC_TICK_S during the first SYNC_WINDOW_S. Returns the exit code, 124 after THOMHOUSE_SYNC_TIMEOUT_S."""
    cmd = [str(_engine(ctx)), "--json", "sync", "--days", "365", "--no-media", "--no-cloud"]
    if force:
        cmd.append("-F")
    try:
        child = subprocess.Popen(cmd, cwd=str(ctx.paths.app), env=proc.child_env(ctx.paths),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
    except OSError:
        return 127
    limit = _sync_timeout(ctx)
    start = time.monotonic()
    next_tick = 0.0
    while True:
        code = child.poll()
        if code is not None:
            return code
        elapsed = time.monotonic() - start
        if next_tick < SYNC_WINDOW_S and elapsed >= next_tick:
            say("setup.sync_countdown", n=max(0, int(round(SYNC_WINDOW_S - next_tick))))
            next_tick += SYNC_TICK_S
        if elapsed >= limit:
            _stop_group(child)
            return 124
        time.sleep(0.05)


def _zalo_logged_in(ctx) -> bool:
    if (state.step_get(ctx.paths, "zalo_login") or {}).get("status") == "done":
        return True
    statuses = bridgecli.doctor(ctx) or {}
    return statuses.get("zalo_login") == "ok"


def sync_flow(ctx, *, force: bool) -> tuple[str, str | None]:
    """16.6.3: needs the Zalo login; `-F` on --force and on every retry; exit 0 is the only proof."""
    if not _zalo_logged_in(ctx):
        say("setup.sync_needs_zalo", tb=tb(ctx))
        return "pending", "later"
    if not _engine(ctx).exists():
        say("setup.zalo_no_engine", tb=tb(ctx))
        return "failed", None
    if consent.ask(ctx, "setup.sync_screen", "cs") != "c":
        say("setup.sync_later", tb=tb(ctx))
        return "pending", "later"
    retry = force
    while True:
        code = _sync_once(ctx, force=retry)
        ctx.log("history_sync", exit=code, force=retry)
        if code == 0:
            say("setup.sync_done")
            return "done", None
        if consent.ask(ctx, "setup.sync_retry", "cs") != "c":
            say("setup.sync_later", tb=tb(ctx))
            return "pending", "later"
        retry = True


def cmd_sync_history(ctx, args) -> int:
    """`thomhouse sync-history [--force]`."""
    return _finish(ctx, "history_sync", sync_flow(ctx, force=bool(getattr(args, "force", False))))


# ---------------------------------------------------------------- analyzers (steps 18 and 19, rev visits)

def has_cache(ctx) -> bool:
    """True when the engine's cache holds a `accounts/*/zalo.db` (the only thing checked in ZALO_CONFIG_DIR)."""
    try:
        return any(p.is_file() for p in ctx.paths.zalo_config.glob("accounts/*/zalo.db"))
    except OSError:
        return False


def _analyzer(ctx, script: str) -> proc.Result:
    """`cd app && python3 -I scripts/<script> --push` with PROFILE_LLM_ENABLED=false; output kept in memory."""
    extra = {}
    if ctx.env.get("THOMHOUSE_SERVER_URL"):
        extra["SERVER_URL"] = str(ctx.env["THOMHOUSE_SERVER_URL"])
    env = proc.child_env(ctx.paths, extra)
    return proc.run(ctx, [sys.executable, "-I", f"scripts/{script}", "--push"], cwd=ctx.paths.app, env=env,
                    capture=True, timeout=ANALYZER_TIMEOUT_S)


def contacts_flow(ctx) -> tuple[str, str | None]:
    """Step 18: the contact analyzer; skipped (`no_cache`) without a Zalo cache."""
    if not has_cache(ctx):
        say("setup.analyze_no_cache", tb=tb(ctx))
        return "skipped", "no_cache"
    res = _analyzer(ctx, "analyze_contacts.py")
    ctx.log("analyze_contacts", exit=res.returncode)
    if res.returncode == 0:
        say("setup.contacts_done")
        return "done", None
    say("setup.contacts_failed", tb=tb(ctx))
    return "pending", "timeout" if res.returncode == 124 else "exit_1"


def visits_flow(ctx) -> tuple[str, str | None]:
    """Step 19: the visit analyzer. A 404 from GET /staff/chat-facts/eligible, or an exit 1 whose stderr holds
    `(HTTP 404)`, means this server has no chat-facts endpoints: one line, pending `server_404`."""
    if not has_cache(ctx):
        say("setup.analyze_no_cache", tb=tb(ctx))
        return "skipped", "no_cache"
    token = envs.value(ctx.paths, "server", "STAFF_TOKEN")
    code, _ = stack.http_json(ctx, "GET", "/staff/chat-facts/eligible", token=token)
    token = None
    if code == 404:
        ctx.log("analyze_visits", server=404)
        say("setup.visits_server_404")
        return "pending", "server_404"
    res = _analyzer(ctx, "analyze_visits.py")
    not_found = res.returncode == 1 and "(HTTP 404)" in res.stderr
    ctx.log("analyze_visits", exit=res.returncode, server_404=not_found)
    if res.returncode == 0:
        say("setup.visits_done")
        return "done", None
    if not_found:
        say("setup.visits_server_404")
        return "pending", "server_404"
    say("setup.visits_failed", tb=tb(ctx))
    return "pending", "timeout" if res.returncode == 124 else "exit_1"


def cmd_analyze(ctx, args) -> int:
    """`thomhouse analyze [--contacts] [--visits]` (neither: both): 0 when every requested analyzer is done."""
    contacts = bool(getattr(args, "contacts", False))
    visits = bool(getattr(args, "visits", False))
    if not contacts and not visits:
        contacts = visits = True
    code = EXIT_OK
    for wanted, step_id, flow in ((contacts, "analyze_contacts", contacts_flow),
                                  (visits, "analyze_visits", visits_flow)):
        if not wanted:
            continue
        status, reason = flow(ctx)
        _record(ctx, step_id, status, reason)
        if status != "done":
            code = EXIT_FAILED
    return code


# ---------------------------------------------------------------- labels (16.6.4)

def labels_ok(ctx) -> bool:
    """`GET /staff/roles` returns at least one role (an array under `roles`, or a top-level array)."""
    code, body = stack.http_json(ctx, "GET", "/staff/roles", token=envs.value(ctx.paths, "server", "STAFF_TOKEN"))
    if code != 200:
        return False
    roles = body.get("roles") if isinstance(body, dict) else body
    return isinstance(roles, list) and len(roles) > 0


def _label_counts(data: object) -> tuple[int, int, int] | None:
    contacts = data.get("contacts") if isinstance(data, dict) else None
    if not isinstance(contacts, dict):
        return None
    out = []
    for name in ("customer", "manager", "staff"):
        value = contacts.get(name, 0)
        out.append(value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0)
    return out[0], out[1], out[2]


def _sync_labels(ctx) -> tuple[str, str | None]:
    code, _ = bridgecli.sync_labels(ctx, dry_run=False)
    if code == 0:
        say("setup.labels_done")
        return "done", None
    say("setup.labels_failed", tb=tb(ctx))
    return "pending", "exit_1"


def labels_flow(ctx, *, sync_only: bool = False) -> tuple[str, str | None]:
    """16.6.4: the counts come from `sync-labels --dry-run` (counts only); `c` copies them with `sync-labels`."""
    if sync_only:
        return _sync_labels(ctx)
    if consent.ask(ctx, "setup.labels_screen", "cs") != "c":
        say("setup.labels_later", tb=tb(ctx))
        return "pending", "later"
    while True:
        code, data = bridgecli.sync_labels(ctx, dry_run=True)
        counts = _label_counts(data)
        if code != 0 or counts is None:
            say("setup.labels_failed", tb=tb(ctx))
            return "pending", "exit_1"
        if sum(counts) == 0:
            if consent.ask(ctx, "setup.labels_none", "cs") != "c":
                say("setup.labels_later", tb=tb(ctx))
                return "pending", "later"
            continue
        if consent.ask(ctx, "setup.labels_found", "cs", customer=counts[0], manager=counts[1],
                       staff=counts[2]) != "c":
            say("setup.labels_later", tb=tb(ctx))
            return "pending", "later"
        return _sync_labels(ctx)


def cmd_labels(ctx, args) -> int:
    """`thomhouse labels [--sync]`: --sync copies the labels without the questions."""
    return _finish(ctx, "labels", labels_flow(ctx, sync_only=bool(getattr(args, "sync", False))))


# ---------------------------------------------------------------- staff token (16.6.5, rev F16, F17)

def _clear_seconds(ctx) -> int:
    try:
        value = int(str(ctx.env.get("THOMHOUSE_CLIPBOARD_CLEAR_S", DEFAULT_CLIPBOARD_S)).strip())
    except ValueError:
        return DEFAULT_CLIPBOARD_S
    return value if 1 <= value <= 300 else DEFAULT_CLIPBOARD_S


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clear_clipboard(ctx, digest: str) -> None:
    """Empty the clipboard (`pbcopy </dev/null`) only while it still holds the token (compared by SHA-256)."""
    current = proc.run(ctx, ["pbpaste"], capture=True, timeout=30).stdout
    if digest in (_digest(current), _digest(current.rstrip("\r\n"))):
        proc.run(ctx, ["pbcopy"], timeout=30)
    current = ""


def token_flow(ctx) -> tuple[str, str | None]:
    """16.6.5: STAFF_TOKEN to the clipboard (stdin of pbcopy, never shown), the console opened, the paste
    confirmed with `c`; the clipboard is cleared on the answer or after THOMHOUSE_CLIPBOARD_CLEAR_S seconds."""
    if not ctx.interactive:
        say("setup.needs_terminal")
        return "pending", "later"
    token = envs.value(ctx.paths, "server", "STAFF_TOKEN")
    if not token:
        say("setup.token_missing", tb=tb(ctx))
        return "failed", None
    digest = _digest(token)
    copied = proc.run(ctx, ["pbcopy"], stdin=token, timeout=30).returncode
    token = None
    if copied != 0:
        say("setup.token_copy_failed", tb=tb(ctx))
        return "failed", None
    console = ctx.env.get("THOMHOUSE_CONSOLE_URL") or stack.DEFAULT_CONSOLE_URL
    proc.run(ctx, ["open", console], timeout=30)
    seconds = _clear_seconds(ctx)
    timer = threading.Timer(seconds, _clear_clipboard, args=(ctx, digest))
    timer.daemon = True
    timer.start()
    try:
        answer = consent.ask(ctx, "setup.token_screen", "cs", minutes=max(1, math.ceil(seconds / 60)))
    finally:
        timer.cancel()
        _clear_clipboard(ctx, digest)
    ctx.log("staff_token", answer=answer)
    if answer == "c":
        say("setup.token_done")
        return "done", None
    say("setup.token_later", tb=tb(ctx))
    return "pending", "later"


def cmd_staff_token(ctx, args) -> int:
    """`thomhouse staff-token` (no InstallLock): `c` marks the step done; the browser cannot be inspected."""
    return _finish(ctx, "staff_token", token_flow(ctx))
