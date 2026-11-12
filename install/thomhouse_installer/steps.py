"""The 25 install steps of 16.4.3, the commands `install` and `continue`, and the dry-run plan (16.4.5).

Every step first runs its `check()` on the real machine; a step whose check passes is marked `done` and skipped.
The journal (`install-steps.json`) is a cache: a `done` step whose check fails runs again, and steps 17 to 23,
which cannot be seen on the machine, rely on the journal. Human steps (14, 16, 17, 20, 21) are marked `pending`
without a question with `--skip-human` or a non-interactive stdin. A `k` (or Enter) at a required question (the
shared-data question of step 2, the runtime consent of step 5, the licence notice of step 6) exits 4 and leaves the
step `pending` with reason `declined`, so no later step runs without that answer.

Other packages are called only through the interfaces of 16.3.3, imported when a step needs them (`_wp`), so a
package that is not built yet stops the command with `core.not_built` instead of an import error.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import secrets
import shutil
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import accounts, bridgecli, consent, human, migrations, platforms, proc, stack, state
from .context import (EXIT_DECLINED, EXIT_FAILED, EXIT_HUMAN_PENDING, EXIT_OK, EXIT_REFUSED, EXIT_USAGE, Ctx,
                      Exit, InstallerError)
from .text_vi import say, t

# Stock macOS tools of 16.5. launchctl lives in /bin on macOS, so /bin and /sbin are searched too.
STOCK_TOOLS = ("curl", "shasum", "tar", "lsof", "ssh-keygen", "pbcopy", "pbpaste", "open", "sips", "hdiutil",
               "launchctl", "sw_vers", "sysctl")
TOOL_DIRS = ("/usr/bin", "/usr/sbin", "/bin", "/sbin")
REQUIRED_HUMAN = ("claude_login", "zalo_login", "staff_token")  # exit 10 while one is not done (rev F9)
RUNTIME_NAMES = {"python": "Python", "node": "Node.js", "pnpm": "pnpm", "claude_code": "Claude Code"}
RUNTIME_HOSTS = {"python": "github.com", "node": "nodejs.org", "pnpm": "registry.npmjs.org", "claude_code": "claude.ai"}


@dataclass
class StepResult:
    """Outcome of one step's `run()`.

    `status` is done, pending, skipped, failed or declined; `reason` a 16.4.4 code; `exit` not None stops the run
    with that exit code. `extra` holds fields kept in the step's journal entry (WP3 only, for example the licence
    acceptance time that step 8 copies into installed.json).
    """

    status: str
    reason: str | None = None
    exit: int | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class Step:
    """One row of 16.4.3."""

    n: int
    id: str
    title_key: str
    optional: bool
    human: bool
    network: bool
    check: Callable[[Ctx], bool]
    run: Callable[[Ctx], StepResult]


# ---------------------------------------------------------------- helpers

def _wp(name: str):
    """The module `name` of another package (16.3.3); Exit 2 with core.not_built while it does not exist."""
    full = f"{__package__}.{name}"
    try:
        return importlib.import_module(full)
    except ModuleNotFoundError as e:
        if e.name == full:
            raise Exit(EXIT_USAGE, "core.not_built", part=name, command="install") from None
        raise


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _version_json(ctx: Ctx) -> dict:
    try:
        data = json.loads((ctx.paths.code_root / "VERSION.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _version(ctx: Ctx) -> str:
    return str(_version_json(ctx).get("version") or "?")


def _menu_id(ctx: Ctx) -> str:
    return str(_version_json(ctx).get("menu_id") or "")


def _arg(ctx: Ctx, name: str, default: object = None) -> object:
    return getattr(ctx.args, name, default)


def _release_file(ctx: Ctx) -> Path | None:
    """The `.command` the header ran (`--release-file`), else its copy in cache/releases, else None."""
    given = _arg(ctx, "release_file")
    if given:
        return Path(str(given))
    cached = ctx.paths.cache_releases / f"thomhouse-{_version(ctx)}.command"
    return cached if cached.is_file() else None


def _again(ctx: Ctx) -> str:
    """The command that resumes the install: the launcher's `continue` once installed.json exists, else the file."""
    if ctx.paths.installed_json.exists():
        return f"{human.tb(ctx)} continue"
    given = _arg(ctx, "release_file")
    if given:
        return f"bash {given}"
    return f"bash thomhouse-{_version(ctx)}.command"


def _log(ctx: Ctx, event: str, **fields: object) -> None:
    if not ctx.dry_run:
        ctx.log(event, **fields)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_tuple(text: str | None) -> tuple[int, ...]:
    out = []
    for piece in (text or "").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def _journal_done(step_id: str) -> Callable[[Ctx], bool]:
    def check(ctx: Ctx) -> bool:
        return (state.step_get(ctx.paths, step_id) or {}).get("status") == "done"
    return check


def _never(ctx: Ctx) -> bool:
    return False


def _print_failures(results: list) -> None:
    for r in results:
        say("setup.check_failed", label=r.label, detail=r.detail)
        if r.fix:
            say("setup.check_fix", fix=r.fix)


def _human_result(outcome: tuple[str, str | None]) -> StepResult:
    status, reason = outcome
    return StepResult(status, reason)


# ---------------------------------------------------------------- step 1: verify (header only, rev F5)

def _check_verify(ctx: Ctx) -> bool:
    return bool(_arg(ctx, "from_bootstrap", False)) or ctx.paths.installed_json.exists()


def _run_verify(ctx: Ctx) -> StepResult:
    release = _wp("release")
    given = _arg(ctx, "release_file")
    if given:
        release.verify_file(ctx, Path(str(given)), first_install=not ctx.paths.installed_json.exists())
        return StepResult("done")
    if release.verify_manifest(ctx.paths.code_root):
        say("setup.release_damaged", version=_version(ctx))
        return StepResult("failed", exit=EXIT_REFUSED)
    return StepResult("done")


# ---------------------------------------------------------------- step 2: preflight (16.5, rev F3, F12, F20)

def _uid(ctx: Ctx) -> int:
    res = proc.run(ctx, ["id", "-u"], capture=True, timeout=15)
    try:
        return int(res.stdout.strip())
    except ValueError:
        return os.getuid()


def _has_d1_data(ctx: Ctx) -> bool:
    bot = ctx.paths.bot_home
    return migrations.find_db(bot) is not None or migrations.applied(bot) is None


def _stack_folder(ctx: Ctx, svc) -> str:
    if svc.cwd is not None:
        text = str(svc.cwd)
        cut = text.find("/apps/")
        return human.tilde(Path(text[:cut] if cut > 0 else text), ctx.paths.home)
    return svc.name


def _run_preflight(ctx: Ctx) -> StepResult:
    p = ctx.paths
    plat = ctx.platform
    pins = ctx.pins
    minimum = ".".join(str(x) for x in pins.macos_min)
    previous = state.step_get(p, "preflight") or {}
    extra: dict[str, object] = {}
    if plat.os != "darwin":
        say("setup.preflight_not_mac", min=minimum, name=plat.uname or plat.os)
        return StepResult("failed", exit=EXIT_REFUSED)
    if plat.macos is None or tuple(plat.macos) < tuple(pins.macos_min):
        say("setup.preflight_macos", v=".".join(str(x) for x in plat.macos or ()) or "?", min=minimum)
        return StepResult("failed", exit=EXIT_REFUSED)
    if _uid(ctx) == 0:
        say("setup.preflight_root")
        return StepResult("failed", exit=EXIT_REFUSED)
    if plat.cpu != "arm64":
        if not previous.get("intel_accepted") and not _arg(ctx, "from_bootstrap", False):
            if consent.ask(ctx, "setup.preflight_intel", "ck") != "c":
                return StepResult("pending", "declined", exit=EXIT_DECLINED)
        if pins.node.url is None or pins.node.sha256 is None:
            say("setup.preflight_intel_no_pins")
            return StepResult("failed", exit=EXIT_REFUSED)
        extra["intel_accepted"] = True
    free = platforms.free_gb(p.home)
    if free < pins.disk_min_gb:
        say("setup.preflight_disk", n=f"{free:.1f}", m=pins.disk_min_gb)
        return StepResult("failed", exit=EXIT_REFUSED)
    missing = [tool for tool in STOCK_TOOLS if not any(os.path.exists(os.path.join(d, tool)) for d in TOOL_DIRS)]
    if missing:
        say("setup.preflight_tools", name=", ".join(missing))
        return StepResult("failed", exit=EXIT_REFUSED)
    holder = state.lock_holder(p)
    if holder is not None and not state.held_by_us(p):
        raise state.Locked(holder)
    if state.moved_out(p) is not None:
        raise Exit(EXIT_REFUSED, "core.moved_out", tb=human.tb(ctx))
    others = stack.other_stacks(p)
    if others:
        say("setup.preflight_other_stack", folder=_stack_folder(ctx, others[0]))
        return StepResult("failed", exit=EXIT_REFUSED)
    if not p.installed_json.exists() and _has_d1_data(ctx) and not previous.get("shared_data_accepted"):
        answer = consent.ask(ctx, "setup.shared_data", "ck", allow_yes=False,
                             folder=human.tilde(p.bot_home, p.home))
        if answer != "c":
            say("setup.shared_data_declined", cmd=_again(ctx))
            return StepResult("pending", "declined", exit=EXIT_DECLINED)
        extra["shared_data_accepted"] = True
        _log(ctx, "shared_data_accepted")
    return StepResult("done", extra=extra)


# ---------------------------------------------------------------- step 3: unpack (header, rev F5)

def _check_unpack(ctx: Ctx) -> bool:
    folder = ctx.paths.release_dir(_version(ctx))
    if not folder.is_dir():
        return False
    return not _wp("release").verify_manifest(folder)


def _run_unpack(ctx: Ctx) -> StepResult:
    release = _wp("release")
    source = _release_file(ctx)
    if source is None or not source.is_file():
        say("setup.release_file_missing", version=_version(ctx))
        return StepResult("failed", exit=EXIT_REFUSED)
    info = release.verify_file(ctx, source, first_install=not ctx.paths.installed_json.exists())
    release.unpack(ctx, info)
    release.copy_to_cache(ctx, info)
    return StepResult("done")


# ---------------------------------------------------------------- steps 4 and 5: runtimes (rev F1, F11, F15, F22)

def _runtime_ok(ctx: Ctx, name: str) -> bool:
    """True when the launcher's copy of `name` is the pinned version (claude_code: at least the minimum)."""
    try:
        found = _wp("runtimes").found(ctx, name)
    except Exit:
        return False
    pins = ctx.pins
    if name == "python":
        return found == pins.python.version
    if name == "node":
        return found == pins.node.version
    if name == "pnpm":
        return found == pins.pnpm_version
    return found is not None and _version_tuple(found) >= _version_tuple(pins.claude_min)


def _check_python(ctx: Ctx) -> bool:
    return _runtime_ok(ctx, "python")


def _run_python(ctx: Ctx) -> StepResult:
    # Python is installed by bootstrap.sh before this program can run; here only the repair path is named.
    say("setup.python_wrong", v=ctx.pins.python.version, folder=human.tilde(ctx.paths.app, ctx.paths.home))
    return StepResult("failed")


def _check_runtimes(ctx: Ctx) -> bool:
    return bool(_wp("doctor").passes(ctx, {"node", "pnpm", "claude_cli"}))


def _say_runtime_item(ctx: Ctx, item) -> None:
    folder = human.tilde(ctx.paths.runtime, ctx.paths.home)
    if item.name == "claude_code":
        say("setup.runtime_plan_claude", v=item.wanted, mb=item.size_mb or ctx.pins.claude_approx_mb)
    elif item.size_mb:
        say("setup.runtime_plan_item", name=RUNTIME_NAMES.get(item.name, item.name), v=item.wanted,
            host=item.source, mb=item.size_mb, folder=folder)
    else:
        say("setup.runtime_plan_item_nosize", name=RUNTIME_NAMES.get(item.name, item.name), v=item.wanted,
            host=item.source, folder=folder)


def _say_runtime_declined(ctx: Ctx, items: list) -> None:
    say("setup.runtime_declined_head", folder=human.tilde(ctx.paths.app_home, ctx.paths.home))
    for item in items:
        if item.name == "pnpm":
            say("setup.runtime_declined_pnpm", v=item.wanted)
        elif item.name == "claude_code":
            say("setup.runtime_declined_claude", v=item.wanted, url=item.url or ctx.pins.claude.url or "")
        else:
            say("setup.runtime_declined_node", v=item.wanted, url=item.url or "", sha256=item.sha256 or "")
    say("setup.runtime_declined_tail", cmd=_again(ctx))


def _run_runtimes(ctx: Ctx) -> StepResult:
    runtimes = _wp("runtimes")
    items = [i for i in runtimes.plan(ctx) if i.name in ("node", "pnpm", "claude_code")]
    todo = [i for i in items if i.action == "install"]
    consented = set(_arg(ctx, "consented", None) or [])
    unasked = [i for i in todo if i.name not in consented]
    if unasked:  # an item missing from --consented is shown and asked, never failed (rev F11)
        say("setup.runtime_plan_head")
        for item in unasked:
            _say_runtime_item(ctx, item)
        if consent.ask(ctx, "setup.runtime_ask", "ck") != "c":
            _say_runtime_declined(ctx, unasked)
            return StepResult("pending", "declined", exit=EXIT_DECLINED)
    node_bin = ctx.paths.runtime / "node" / "bin"
    for name in ("node", "pnpm", "claude_code"):
        item = next((i for i in items if i.name == name), None)
        if item is None:
            continue
        if item.action == "install":
            if name == "pnpm":
                runtimes.install(ctx, item, node_bin=node_bin)
            else:
                runtimes.install(ctx, item)
            runtimes.switch(ctx, name, item.wanted)
            _log(ctx, "runtime_installed", name=name, version=item.wanted)
        elif name == "claude_code":  # a reused ~/.local/bin/claude still gets runtime/bin/claude (rev F15)
            runtimes.switch(ctx, name, item.found or item.wanted)
    return StepResult("done")


# ---------------------------------------------------------------- step 6: licence notice (rev owner)

def _check_engine_notice(ctx: Ctx) -> bool:
    installed = state.load_installed(ctx.paths) or {}
    if installed.get("engine_notice_accepted_at"):
        return True
    entry = state.step_get(ctx.paths, "engine_notice") or {}
    return entry.get("status") == "done" and bool(entry.get("accepted_at"))


def _run_engine_notice(ctx: Ctx) -> StepResult:
    if consent.typed(ctx, "setup.engine_notice", ("dong y",), v=ctx.pins.engine_version):
        return StepResult("done", extra={"accepted_at": _now()})
    say("setup.engine_declined", cmd=_again(ctx))
    return StepResult("pending", "declined", exit=EXIT_DECLINED)


# ---------------------------------------------------------------- step 7: dependencies (rev F21)

def _check_deps(ctx: Ctx) -> bool:
    return bool(_wp("doctor").passes(ctx, {"deps_workspace", "deps_engine"}))


def _run_deps(ctx: Ctx) -> StepResult:
    result = _wp("deps").install(ctx, ctx.paths.code_root, ctx.paths.runtime / "node" / "bin")
    if isinstance(result, dict) and not result.get("rooms", True):
        say("setup.deps_rooms_warn")  # rooms are optional (14.10): a warning only
    return StepResult("done")


# ---------------------------------------------------------------- step 8: activate (rev F5, F10)

def _app_is_release(ctx: Ctx) -> bool:
    app = ctx.paths.app
    if not os.path.lexists(app):
        return False
    return os.path.realpath(app) == os.path.realpath(ctx.paths.release_dir(_version(ctx)))


def _check_activate(ctx: Ctx) -> bool:
    installed = state.load_installed(ctx.paths)
    if not installed or installed.get("version") != _version(ctx) or not _app_is_release(ctx):
        return False
    return bool(_wp("release").launcher_current(ctx, ctx.paths.code_root))


def _signer(path: Path) -> str | None:
    """`SHA256:<base64>` of the public key in an allowed_signers file (the form ssh-keygen -l prints)."""
    try:
        words = path.read_text(encoding="utf-8").split()
    except OSError:
        return None
    for i, word in enumerate(words[:-1]):
        if word.startswith(("ssh-", "ecdsa-", "sk-")):
            try:
                blob = base64.b64decode(words[i + 1], validate=True)
            except ValueError:
                return None
            digest = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
            return f"SHA256:{digest}"
    return None


def _store_trust(ctx: Ctx) -> None:
    """Copy the payload's install/trust/allowed_signers to APP_HOME/trust (0600): trust on first use (16.2.6)."""
    source = ctx.paths.code_root / "install" / "trust" / "allowed_signers"
    if not source.is_file():
        _log(ctx, "trust_missing")
        return
    target = ctx.paths.trust
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    tmp = target.with_name(f".{target.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(source.read_bytes())
    os.replace(tmp, target)


def _release_info(ctx: Ctx):
    source = _release_file(ctx)
    if source is None or not source.is_file():
        return None
    try:
        return _wp("release").read_header(source)
    except (InstallerError, OSError):
        return None


def _new_installed(ctx: Ctx, version: str) -> dict:
    info = _release_info(ctx)
    runtimes = _wp("runtimes")
    found = {name: runtimes.found(ctx, name) for name in ("python", "node", "pnpm", "claude_code")}
    notice = (state.step_get(ctx.paths, "engine_notice") or {}).get("accepted_at")
    return {
        "schema": 1,
        "device_id": secrets.token_hex(16),
        "version": version,
        "previous_version": None,
        "installed_at": _now(),
        "install_completed_at": None,
        "payload_sha256": getattr(info, "payload_sha256", None),
        "release_id": getattr(info, "release_id", None),
        "signer": _signer(ctx.paths.trust),
        "menu_id": _menu_id(ctx) or None,
        "runtimes": found,
        "previous_runtimes": None,
        "engine_notice_accepted_at": notice,
        "migrations_applied": migrations.applied(ctx.paths.bot_home) or [],
        "backup_before_update": None,
        "autostart": False,
    }


def _run_activate(ctx: Ctx) -> StepResult:
    release = _wp("release")
    p = ctx.paths
    version = _version(ctx)
    installed = state.load_installed(p)
    if installed and installed.get("version") not in (None, version):
        say("setup.activate_other_version", v=installed.get("version"), version=version, tb=human.tb(ctx))
        return StepResult("failed", exit=EXIT_REFUSED)
    for folder in (p.app_home, p.bot_home):  # both 0700 (16.2.7, doctor check 23), whoever created them
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o700)
    if installed is None:
        _store_trust(ctx)
    # installed.json is written last: once it exists the header refuses to run again, so `app` and the launcher
    # must already be there for `thomhouse continue` (16.2.6).
    release.switch_app(ctx, version)
    release.write_launcher(ctx, p.code_root)
    if installed is None:
        state.save_installed(p, _new_installed(ctx, version))
        state.history_append(p, {"event": "install", "from": None, "to": version, "result": "ok", "backup": None})
    return StepResult("done")


# ---------------------------------------------------------------- step 9: config

def _run_config(ctx: Ctx) -> StepResult:
    p = ctx.paths
    engine = p.app / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent"
    if bridgecli.init_env(ctx, p.app, engine) != 0:
        say("setup.config_failed", cmd=_again(ctx))
        return StepResult("failed", exit=EXIT_FAILED)
    for name in ("server", "runner", "bridge"):
        f = p.env_file(name)
        if not f.is_file():
            say("setup.config_missing", file=human.tilde(f, p.home), cmd=_again(ctx))
            return StepResult("failed", exit=EXIT_FAILED)
        if stat.S_IMODE(f.stat().st_mode) != 0o600:
            os.chmod(f, 0o600)
    return StepResult("done")


# ---------------------------------------------------------------- step 10: move-in

def _move_in_file(ctx: Ctx) -> Path | None:
    given = _arg(ctx, "move_in")
    return Path(str(given)) if given else None


def _check_move_in(ctx: Ctx) -> bool:
    image = _move_in_file(ctx)
    if image is None or not image.is_file():
        return False
    entry = state.step_get(ctx.paths, "move_in") or {}
    return entry.get("status") == "done" and entry.get("image_sha256") == _sha256_file(image)


def _run_move_in(ctx: Ctx) -> StepResult:
    image = _move_in_file(ctx)
    if image is None:
        return StepResult("skipped")
    if not image.exists():
        say("setup.file_missing", file=str(image))
        return StepResult("failed", exit=EXIT_FAILED)
    digest = _sha256_file(image) if image.is_file() else None
    code = _wp("move").place_moved_data(ctx, image)
    if code == 0:
        return StepResult("done", extra={"image_sha256": digest})
    if code == 3:
        say("setup.move_in_refused")
        return StepResult("failed", exit=EXIT_REFUSED)
    if code == 4:
        say("setup.move_in_declined")
        return StepResult("pending", "declined", exit=EXIT_DECLINED)
    say("setup.move_in_failed")
    return StepResult("failed", exit=EXIT_FAILED)


# ---------------------------------------------------------------- step 11: menu slides (rev check)

def _check_menu_slides(ctx: Ctx) -> bool:
    if not os.path.lexists(ctx.paths.app):
        return False
    return bool(_wp("release").menu_slides_ok(ctx, ctx.paths.app))


def _find_menu_tar(ctx: Ctx, menu_id: str) -> Path | None:
    given = _arg(ctx, "menu")
    if given:
        path = Path(str(given))
        return path if path.is_file() else None
    name = f"thomhouse-menu-{menu_id}.tar"
    folders = []
    if _arg(ctx, "release_file"):
        folders.append(Path(str(_arg(ctx, "release_file"))).parent)
    remembered = (state.step_get(ctx.paths, "menu_slides") or {}).get("release_file")
    if isinstance(remembered, str) and remembered:
        folders.append(Path(remembered).parent)
    for folder in folders:
        if (folder / name).is_file():
            return folder / name
    return None


def _run_menu_slides(ctx: Ctx) -> StepResult:
    menu_id = _menu_id(ctx)
    archive = _find_menu_tar(ctx, menu_id)
    if archive is None:
        say("setup.menu_missing", menu_id=menu_id, tb=human.tb(ctx))
        extra: dict[str, object] = {}
        if _arg(ctx, "release_file"):
            extra["release_file"] = str(_arg(ctx, "release_file"))
        return StepResult("pending", extra=extra)  # the bot runs without menu images; `continue` tries again
    release = _wp("release")
    installed_id = release.install_menu(ctx, archive)
    release.link_menu(ctx, ctx.paths.app, installed_id)
    return StepResult("done")


# ---------------------------------------------------------------- step 12: migrations (rev F7, F13)

def _live_root(ctx: Ctx) -> Path:
    """`app` once step 8 linked it, else the release this command runs from (dry run before activation)."""
    return ctx.paths.app if os.path.lexists(ctx.paths.app) else ctx.paths.code_root


def _check_migrations(ctx: Ctx) -> bool:
    return migrations.pending(_live_root(ctx), ctx.paths.bot_home) == []


def _restore_d1(ctx: Ctx, backup) -> None:
    """Put BOT_HOME/d1 back from `backup` (its d1/ folder); the failed folder is kept as d1.failed-<stamp>."""
    p = ctx.paths
    source = Path(backup.path) / "d1"
    failed = p.bot_home / f"d1.failed-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        if p.d1_dir.exists():
            os.rename(p.d1_dir, failed)
            os.chmod(failed, 0o700)
        shutil.copytree(source, p.d1_dir, symlinks=True)
        os.chmod(p.d1_dir, 0o700)
    except OSError:
        say("setup.migrations_restore_failed", folder=human.tilde(Path(backup.path), p.home),
            failed=human.tilde(failed, p.home))
        _log(ctx, "migrations_restore_failed")
        return
    say("setup.migrations_restored", folder=human.tilde(Path(backup.path), p.home))
    _log(ctx, "migrations_restored")


def _run_migrations(ctx: Ctx) -> StepResult:
    p = ctx.paths
    taken = None
    if migrations.find_db(p.bot_home) is not None or migrations.applied(p.bot_home) is None:
        pending = migrations.pending(p.app, p.bot_home)
        if pending is None or pending:
            if stack.is_running(p, "server"):
                stack.stop(ctx)  # a stopped backup is refused while the server runs (16.8.2)
            taken = _wp("backup").make(ctx, mode="stopped", reason="before-migration")
    if migrations.apply(ctx, p.app) != 0:
        say("setup.migrations_failed", log=human.tilde(p.logs / "migrations.log", p.home))
        if taken is not None:
            _restore_d1(ctx, taken)
        return StepResult("failed", exit=EXIT_FAILED)
    installed = state.load_installed(p)
    if installed is not None:
        installed["migrations_applied"] = migrations.applied(p.bot_home) or []
        state.save_installed(p, installed)
    return StepResult("done")


# ---------------------------------------------------------------- step 13: the pool account `main`

def _check_pool(ctx: Ctx) -> bool:
    return ctx.paths.accounts_json.exists()


def _run_pool(ctx: Ctx) -> StepResult:
    # `main` gets its own config folder BOT_HOME/accounts/main and stays disabled until its login is verified,
    # so a first job cannot mark it login_expired (16.4.3).
    if accounts.pool(ctx, "add", "main", "--priority", "1") != 0 or accounts.pool(ctx, "disable", "main") != 0:
        say("setup.pool_failed", cmd=_again(ctx))
        return StepResult("failed", exit=EXIT_FAILED)
    return StepResult("done")


# ---------------------------------------------------------------- human steps 14, 16 to 21

def _run_claude_login(ctx: Ctx) -> StepResult:
    return _human_result(human.claude_logins_flow(ctx))


def _check_zalo(ctx: Ctx) -> bool:
    return bool(_wp("doctor").passes(ctx, {"zalo_login", "listener"}))


def _run_zalo(ctx: Ctx) -> StepResult:
    return _human_result(human.zalo_login_flow(ctx))


def _run_history_sync(ctx: Ctx) -> StepResult:
    return _human_result(human.sync_flow(ctx, force=False))


def _run_contacts(ctx: Ctx) -> StepResult:
    return _human_result(human.contacts_flow(ctx))


def _run_visits(ctx: Ctx) -> StepResult:
    return _human_result(human.visits_flow(ctx))


def _check_labels(ctx: Ctx) -> bool:
    return _journal_done("labels")(ctx) or human.labels_ok(ctx)


def _run_labels(ctx: Ctx) -> StepResult:
    return _human_result(human.labels_flow(ctx))


def _run_staff_token(ctx: Ctx) -> StepResult:
    return _human_result(human.token_flow(ctx))


# ---------------------------------------------------------------- step 15: start (rev F16, F18)

def _run_start(ctx: Ctx) -> StepResult:
    p = ctx.paths
    if stack.start(ctx) != 0:
        say("setup.start_failed", log=human.tilde(p.logs / "start.log", p.home))
        return StepResult("failed", exit=EXIT_FAILED)
    failed = stack.health_gate(ctx)
    results = _wp("doctor").run_checks(ctx, only=set(failed) | {"listen_local_only", "openmausbot_options"})
    bad = [r for r in results if r.status == "fail"]
    _print_failures(bad)
    if failed and not bad:
        say("setup.start_failed", log=human.tilde(p.logs / "start.log", p.home))
    if failed or bad:
        return StepResult("failed", exit=EXIT_FAILED)
    return StepResult("done")


# ---------------------------------------------------------------- steps 22 and 23: autostart and shortcuts

def _check_answered(step_id: str) -> Callable[[Ctx], bool]:
    def check(ctx: Ctx) -> bool:
        return (state.step_get(ctx.paths, step_id) or {}).get("status") in ("done", "declined")
    return check


def _consent_step(ctx: Ctx, key: str) -> str | None:
    """`c` or `k` from the person; None (ask again on a later run) when nobody can answer and --yes is not given."""
    if not ctx.interactive and not ctx.yes:
        say("setup.consent_later", tb=human.tb(ctx))
        return None
    return consent.ask(ctx, key, "ck")


def _run_autostart(ctx: Ctx) -> StepResult:
    answer = _consent_step(ctx, "setup.autostart_ask")
    if answer is None:
        return StepResult("pending", "later")
    if answer != "c":
        return StepResult("declined")
    try:
        _wp("autostart").enable(ctx)
    except (InstallerError, OSError):
        say("setup.autostart_failed", tb=human.tb(ctx))
        return StepResult("failed")
    installed = state.load_installed(ctx.paths)
    if installed is not None:
        installed["autostart"] = True
        state.save_installed(ctx.paths, installed)
    say("setup.autostart_done")
    return StepResult("done")


def _run_shortcuts(ctx: Ctx) -> StepResult:
    answer = _consent_step(ctx, "setup.shortcuts_ask")
    if answer is None:
        return StepResult("pending", "later")
    if answer != "c":
        return StepResult("declined")
    say("ops.desktop_prompt")  # macOS asks in English before Terminal may write to the Desktop (rev F18)
    try:
        _wp("autostart").shortcuts(ctx, True)
    except (InstallerError, OSError):
        say("setup.shortcuts_failed", tb=human.tb(ctx))
        return StepResult("failed")
    say("setup.shortcuts_done")
    return StepResult("done")


# ---------------------------------------------------------------- step 24: menu images

def _menu_images(ctx: Ctx, *, check: bool) -> int:
    p = ctx.paths
    cmd = [sys.executable, "-I", str(p.app / "scripts" / "build_menu_images.py"), "--home", str(p.bot_home)]
    if check:
        cmd.append("--check")
    log = None if ctx.dry_run else p.logs / "menu.log"
    return proc.run(ctx, cmd, cwd=p.app, log=log, timeout=1800).returncode


def _check_menu_images(ctx: Ctx) -> bool:
    if not (ctx.paths.app / "scripts" / "build_menu_images.py").is_file():
        return False
    return _menu_images(ctx, check=True) == 0


def _run_menu_images(ctx: Ctx) -> StepResult:
    if _menu_images(ctx, check=False) == 0:
        return StepResult("done")
    say("setup.menu_check_failed", tb=human.tb(ctx))
    return StepResult("failed")


# ---------------------------------------------------------------- step 25: final check (rev F9)

def _left_titles(ctx: Ctx) -> list[str]:
    journal = state.steps_all(ctx.paths)
    out = []
    for step in STEPS:
        if step.id == "final_check":
            continue
        if (journal.get(step.id) or {}).get("status") in ("pending", "failed"):
            out.append(t(step.title_key))
    return out


def _run_final(ctx: Ctx) -> StepResult:
    doctor = _wp("doctor")
    p = ctx.paths
    results = doctor.run_checks(ctx)
    bad = [r for r in results if r.status == "fail"]
    code = doctor.exit_code(results, False)
    if not bad and code == 0:
        installed = state.load_installed(p)
        if installed is not None and not installed.get("install_completed_at"):
            installed["install_completed_at"] = _now()
            state.save_installed(p, installed)
    if bad or code != 0:
        _print_failures(bad)
        say("setup.summary_errors", n=len(bad), tb=human.tb(ctx))
        return StepResult("failed", exit=EXIT_FAILED)
    console = ctx.env.get("THOMHOUSE_CONSOLE_URL") or stack.DEFAULT_CONSOLE_URL
    say("setup.summary_running", version=_version(ctx), url=console)
    left = _left_titles(ctx)
    if left:
        say("setup.summary_left", n=len(left), names=", ".join(left), tb=human.tb(ctx))
    else:
        say("setup.summary_none")
    journal = state.steps_all(p)
    waiting = [sid for sid in REQUIRED_HUMAN if (journal.get(sid) or {}).get("status") != "done"]
    return StepResult("done", exit=EXIT_HUMAN_PENDING if waiting else EXIT_OK)


# ---------------------------------------------------------------- the table of 16.4.3

STEPS: list[Step] = [
    Step(1, "verify", "setup.title_verify", False, False, False, _check_verify, _run_verify),
    Step(2, "preflight", "setup.title_preflight", False, False, False, _never, _run_preflight),
    Step(3, "unpack", "setup.title_unpack", False, False, False, _check_unpack, _run_unpack),
    Step(4, "python", "setup.title_python", False, False, True, _check_python, _run_python),
    Step(5, "runtimes", "setup.title_runtimes", False, False, True, _check_runtimes, _run_runtimes),
    Step(6, "engine_notice", "setup.title_engine_notice", False, False, False, _check_engine_notice,
         _run_engine_notice),
    Step(7, "deps", "setup.title_deps", False, False, True, _check_deps, _run_deps),
    Step(8, "activate", "setup.title_activate", False, False, False, _check_activate, _run_activate),
    Step(9, "config", "setup.title_config", False, False, False, _never, _run_config),
    Step(10, "move_in", "setup.title_move_in", False, False, False, _check_move_in, _run_move_in),
    Step(11, "menu_slides", "setup.title_menu_slides", False, False, False, _check_menu_slides, _run_menu_slides),
    Step(12, "migrations", "setup.title_migrations", False, False, False, _check_migrations, _run_migrations),
    Step(13, "pool", "setup.title_pool", False, False, False, _check_pool, _run_pool),
    Step(14, "claude_login", "setup.title_claude_login", False, True, True, human.claude_logins_ok,
         _run_claude_login),
    Step(15, "start", "setup.title_start", False, False, True, _never, _run_start),
    Step(16, "zalo_login", "setup.title_zalo_login", False, True, True, _check_zalo, _run_zalo),
    Step(17, "history_sync", "setup.title_history_sync", True, True, True, _journal_done("history_sync"),
         _run_history_sync),
    Step(18, "analyze_contacts", "setup.title_analyze_contacts", True, False, False,
         _journal_done("analyze_contacts"), _run_contacts),
    Step(19, "analyze_visits", "setup.title_analyze_visits", True, False, False, _journal_done("analyze_visits"),
         _run_visits),
    Step(20, "labels", "setup.title_labels", True, True, True, _check_labels, _run_labels),
    Step(21, "staff_token", "setup.title_staff_token", False, True, False, _journal_done("staff_token"),
         _run_staff_token),
    Step(22, "autostart", "setup.title_autostart", True, False, False, _check_answered("autostart"),
         _run_autostart),
    Step(23, "shortcuts", "setup.title_shortcuts", True, False, False, _check_answered("shortcuts"),
         _run_shortcuts),
    Step(24, "menu_check", "setup.title_menu_check", False, False, False, _check_menu_images, _run_menu_images),
    Step(25, "final_check", "setup.title_final_check", False, False, True, _never, _run_final),
]

_NOT_APPLICABLE: dict[str, Callable[[Ctx], bool]] = {"move_in": lambda ctx: _move_in_file(ctx) is None}


# ---------------------------------------------------------------- the runner

def _record(ctx: Ctx, step: Step, res: StepResult) -> None:
    """Write `res` into the journal, keeping the extra fields an earlier run stored for this step."""
    if ctx.dry_run:
        return
    previous = state.step_get(ctx.paths, step.id) or {}
    extra = {k: v for k, v in previous.items() if k not in ("status", "at", "reason")}
    extra.update(res.extra)
    state.step_set(ctx.paths, step.id, res.status, res.reason, **extra)


def _run_one(ctx: Ctx, step: Step) -> StepResult:
    title = t(step.title_key)
    if step.check(ctx):
        current = (state.step_get(ctx.paths, step.id) or {}).get("status")
        if current == "declined":  # steps 22 and 23: the answer k is kept, not turned into done
            say("setup.step_line_declined", n=step.n, title=title)
            return StepResult("declined")
        say("setup.step_line_done", n=step.n, title=title)
        if current != "done":
            _record(ctx, step, StepResult("done"))
        return StepResult("done")
    say("setup.step_line", n=step.n, title=title)
    if step.human and (_arg(ctx, "skip_human", False) or not ctx.interactive):
        say("setup.step_postponed", tb=human.tb(ctx))
        res = StepResult("pending", "later")
        _record(ctx, step, res)
        return res
    try:
        res = step.run(ctx)
    except Exception:
        _record(ctx, step, StepResult("failed"))
        _log(ctx, "step_failed", step=step.id)
        raise
    _record(ctx, step, res)
    _log(ctx, "step", step=step.id, status=res.status, reason=res.reason)
    return res


def _find_step(name: str) -> Step | None:
    for step in STEPS:
        if step.id == name or str(step.n) == name.strip():
            return step
    return None


def _run_only(ctx: Ctx, name: str) -> int:
    step = _find_step(name)
    if step is None:
        say("setup.only_unknown", name=name)
        return EXIT_USAGE
    res = _run_one(ctx, step)
    if res.exit is not None:
        return res.exit
    if res.status in ("done", "skipped", "declined"):
        return EXIT_OK
    if res.status == "pending" and (step.human or res.reason in ("later", "declined")):
        return EXIT_DECLINED
    return EXIT_FAILED


def _run_all(ctx: Ctx) -> int:
    for step in STEPS:
        res = _run_one(ctx, step)
        if res.exit is not None:
            return res.exit
    return EXIT_OK


def _refuse(ctx: Ctx) -> None:
    if state.moved_out(ctx.paths) is not None:
        raise Exit(EXIT_REFUSED, "core.moved_out", tb=human.tb(ctx))
    journal = state.update_open(ctx.paths)
    if journal is not None:
        raise Exit(EXIT_REFUSED, "core.update_open", file=str(journal.get("file") or "FILE"))


# ---------------------------------------------------------------- the dry-run plan (16.4.5)

def _plan_item(ctx: Ctx, name: str) -> str:
    pins = ctx.pins
    folder = human.tilde(ctx.paths.runtime, ctx.paths.home)
    if name == "claude_code":
        return t("setup.plan_claude", v=pins.claude.version, mb=pins.claude_approx_mb)
    if name == "python":
        version, size = pins.python.version, pins.python.bytes
    elif name == "node":
        version, size = pins.node.version, pins.node.bytes
    else:
        version, size = pins.pnpm_version, pins.pnpm_bytes
    label = RUNTIME_NAMES[name]
    if size:
        return t("setup.plan_item", name=label, v=version, host=RUNTIME_HOSTS[name], mb=max(1, round(size / 1e6)),
                 folder=folder)
    return t("setup.plan_item_nosize", name=label, v=version, host=RUNTIME_HOSTS[name], folder=folder)


def _plan_marker(ctx: Ctx, step: Step) -> str:
    applies = _NOT_APPLICABLE.get(step.id)
    if applies is not None and applies(ctx):
        return "setup.mark_skip"
    try:
        return "setup.mark_done" if step.check(ctx) else "setup.mark_todo"
    except (InstallerError, OSError, ValueError):
        return "setup.mark_todo"


def _plan(ctx: Ctx) -> int:
    """Print the plan; changes nothing, downloads nothing, asks nothing.

    With --from-bootstrap the `.command` header runs this plan after it has printed the heading and steps 1 to 4
    itself (16.4.5), so only steps 5 to 25 are printed here."""
    from_header = bool(_arg(ctx, "from_bootstrap", False))
    if not from_header:
        say("setup.plan_head", version=_version(ctx))
    for step in STEPS:
        if from_header and step.n <= 4:
            continue
        marker = _plan_marker(ctx, step)
        line = f"{step.n:>3}. [{t(marker)}] {t(step.title_key)}"
        details: list[str] = []
        if marker == "setup.mark_todo" and step.id == "python":
            line += ": " + _plan_item(ctx, "python")
        elif marker == "setup.mark_todo" and step.id == "runtimes":
            details = [_plan_item(ctx, n) for n in ("node", "pnpm", "claude_code") if not _runtime_ok(ctx, n)]
        print(line, flush=True)
        for detail in details:
            print(f"       - {detail}", flush=True)
    return EXIT_OK


# ---------------------------------------------------------------- commands

def cmd_install(ctx: Ctx, args) -> int:
    """`thomhouse install [--yes] [--dry-run] [--skip-human] [--only STEP] [--menu FILE] [--move-in FILE]`.

    Exit 0 done; 1 a step failed; 2 an unknown --only step or a package not built; 3 refused; 4 a required answer
    was no; 10 no doctor check fails but claude_login, zalo_login or staff_token is still pending (rev F9).
    """
    _refuse(ctx)
    if ctx.dry_run:
        return _plan(ctx)
    only = getattr(args, "only", None)
    if only:
        return _run_only(ctx, str(only))
    return _run_all(ctx)


def cmd_continue(ctx: Ctx, args) -> int:
    """`thomhouse continue [--yes] [--dry-run] [--skip-human]`: every step again from its check; same exit codes."""
    _refuse(ctx)
    if ctx.dry_run:
        return _plan(ctx)
    return _run_all(ctx)
