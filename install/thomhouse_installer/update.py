"""`thomhouse update FILE` and `thomhouse rollback` (16.8.1, rev F1, F3, F5, F10, F13, F14, rev check).

An update runs the phases U1 to U13 of 16.8.1. The update journal (key "update" of install-steps.json) is written
before each phase starts and when it ends, with "state" "running" until the end. The release file is read as data
and never executed (`release.verify_file`). Downtime is U7 to U11 only.

Failures: before U7 nothing live is touched and the old stack keeps running (journal "failed"); in U7 and U8 the old
stack is started again; a migration failure in U10 or a start failure in U11 restores `d1` from the U8 backup,
switches `app`, the runtimes and the launcher back and starts the old release (journal "rolled_back"); a failed
health gate in U12 does not roll back, but U13 still stamps `installed.json` so that `rollback` knows the previous
version. An interrupted update resumes: before U9 it starts again at U1, from U9 on it continues at the first phase
not done, and a U10 marked "rollback" is finished as a rollback.

Calls into WP2 (`release`, `runtimes`, `deps`) and WP4 (`doctor.run_checks`) go only through the interfaces of
16.3.3. This module never imports `steps` (WP3).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import backup, migrations, state
from .backup import copy_private, oplog, stamp, tb, tilde, unique_path
from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK, EXIT_REFUSED, Exit, InstallerError
from .text_vi import say, t

PHASES = tuple(f"U{n}" for n in range(1, 14))
RUNTIMES = ("python", "node", "pnpm", "claude_code")
SWITCHED_BACK = ("python", "node", "pnpm")  # Anthropic's installer owns ~/.local/bin/claude (16.13 item 24)
SAFETY_CHECKS = ("listen_local_only", "openmausbot_options")
ENV_NAMES = ("server", "runner", "bridge", "console_local")
UPDATE_LOG = "update.log"


def _after_phase(name: str) -> None:
    """Called after each phase is recorded as done. The tests replace it to simulate a power cut."""


def _ulog(ctx, event: str, **fields: object) -> None:
    oplog(ctx, event, log=UPDATE_LOG, **fields)


def _title(phase: str) -> str:
    return t(f"ops.phase_{phase.lower()}")


def _log_path(ctx) -> str:
    return tilde(ctx.paths.logs / UPDATE_LOG, ctx.paths)


def _compare(a: str | None, b: str | None) -> int | None:
    ta, tb_ = backup.version_tuple(a), backup.version_tuple(b)
    if ta is None or tb_ is None:
        return None
    return (ta > tb_) - (ta < tb_)


def _runtimes_of(ctx) -> dict[str, str]:
    """The runtime versions pinned by the release of `ctx` ({} when its pins cannot be read)."""
    try:
        p = ctx.pins
    except InstallerError:
        return {}
    return {"python": p.python.version, "node": p.node.version, "pnpm": p.pnpm_version,
            "claude_code": p.claude.version}


def _from_runtimes(ctx) -> dict[str, str]:
    inst = state.load_installed(ctx.paths) or {}
    current = inst.get("runtimes")
    if isinstance(current, dict) and all(isinstance(current.get(k), str) for k in RUNTIMES):
        return {k: current[k] for k in RUNTIMES}
    return _runtimes_of(ctx)


def _same_file(paths, file: Path, journal: dict) -> bool:
    """`file` is the journal's release file, or its copy in cache/releases."""
    candidates = []
    if isinstance(journal.get("file"), str) and journal["file"]:
        candidates.append(os.path.realpath(journal["file"]))
    if isinstance(journal.get("to"), str) and journal["to"]:
        candidates.append(os.path.realpath(paths.cache_releases / f"thomhouse-{journal['to']}.command"))
    return os.path.realpath(str(file)) in candidates


def _say_error(ctx, err: InstallerError, file: object) -> None:
    """Print the text of an error raised by another package, with the dispatcher's defaults for its placeholders."""
    fmt: dict[str, object] = {"tb": tb(ctx.paths), "cmd": f"{tb(ctx.paths)} update {file}", "file": str(file),
                              "name": "", "host": ""}
    fmt.update(getattr(err, "fmt", {}) or {})
    key = getattr(err, "key", None)
    if not key:
        return
    try:
        say(key, **fmt)
    except (KeyError, IndexError, ValueError):
        pass


@dataclass
class _Run:
    """One update run: the context, the verified release, the journal and what the phases found."""

    ctx: object
    args: object
    file: Path
    info: object
    journal: dict
    new_dir: Path
    nctx: object = None
    new_node_bin: Path | None = None
    new_pnpm_bin: Path | None = None
    health_failed: list = field(default_factory=list)
    failed_checks: list = field(default_factory=list)


def _save(run: _Run) -> None:
    state.update_set(run.ctx.paths, run.journal)


def _nctx(run: _Run):
    """A context whose code_root is the new release (its pins, its install/), sharing the platform."""
    if run.nctx is None:
        from . import context, paths as paths_mod

        ctx = run.ctx
        p = paths_mod.resolve(ctx.env, code_root=run.new_dir)
        n = context.Ctx(paths=p, env=ctx.env, args=ctx.args, yes=ctx.yes, dry_run=ctx.dry_run, quiet=ctx.quiet,
                        offline=ctx.offline, interactive=ctx.interactive)
        n.platform = ctx.platform
        run.nctx = n
    return run.nctx


def _history(paths, journal: dict, result: str, event: str = "update") -> None:
    state.history_append(paths, {"event": event, "from": journal.get("from"), "to": journal.get("to"),
                                 "result": result, "backup": journal.get("backup")})


def _fail(run: _Run, code: int, phase: str, *, err: InstallerError | None = None, restart: bool = False,
          key: str | None = None) -> int:
    """Close the journal as "failed" (nothing live was switched), start the old stack again when it was stopped,
    print the error and the phase line, and return `code`."""
    from . import stack

    ctx = run.ctx
    run.journal["state"] = "failed"
    _save(run)
    _ulog(ctx, "update_failed", phase=phase, error=type(err).__name__ if err else None)
    if restart:
        stack.start(ctx, quiet=True, during_update=True)
    if err is not None:
        _say_error(ctx, err, run.file)
    if key is None:
        key = "ops.update_failed_restarted" if restart else "ops.update_failed_before_stop"
    say(key, title=_title(phase), old=run.journal.get("from"), log=_log_path(ctx))
    _history(ctx.paths, run.journal, "failed")
    return code


# ---------------------------------------------------------------- the phases

def _u1(run: _Run) -> int | None:
    return None  # the file was verified before the journal was opened


def _u2(run: _Run) -> int | None:
    from . import release

    try:
        run.new_dir = Path(release.unpack(run.ctx, run.info))
        release.copy_to_cache(run.ctx, run.info)
    except (InstallerError, OSError) as e:
        return _fail(run, EXIT_FAILED, "U2", err=e if isinstance(e, InstallerError) else None)
    return None


def _live_target(paths, name: str) -> str:
    link = paths.runtime / name if name in ("python", "node") else paths.runtime_bin / name
    return os.path.realpath(link)


def _remove_new_runtimes(ctx, items: list) -> None:
    """Delete the runtime folders this run installed (never the live one, never Claude Code)."""
    root = os.path.realpath(ctx.paths.runtime)
    for item in items:
        if item.name not in SWITCHED_BACK:
            continue
        target = os.path.realpath(str(item.target))
        live = _live_target(ctx.paths, item.name)
        if not target.startswith(root + "/") or live == target or live.startswith(target + "/"):
            continue
        shutil.rmtree(target, ignore_errors=True)


def _u3(run: _Run) -> int | None:
    from . import consent, runtimes

    ctx, nctx = run.ctx, _nctx(run)
    to_rt = _runtimes_of(nctx)
    run.journal["to_runtimes"] = to_rt
    run.journal["new_runtimes"] = []
    from_rt = run.journal.get("from_runtimes") or {}
    if to_rt and all(from_rt.get(k) == to_rt.get(k) for k in RUNTIMES):
        return None
    order = {name: i for i, name in enumerate(RUNTIMES)}
    try:
        planned = runtimes.plan(nctx)
    except InstallerError as e:  # the new release's pins cannot be read
        return _fail(run, EXIT_FAILED, "U3", err=e)
    items = sorted((i for i in planned if i.action == "install"), key=lambda i: order.get(i.name, 9))
    if not items:
        return None
    say("ops.update_runtime_plan")
    for item in items:
        folder = "~/.local" if item.name == "claude_code" else tilde(ctx.paths.runtime, ctx.paths)
        say(f"ops.runtime_line_{item.name}", version=item.wanted, source=item.source, mb=item.size_mb,
            folder=folder)
    if consent.ask(ctx, "ops.update_runtime_ask", "ck") != "c":
        return _fail(run, EXIT_DECLINED, "U3", key="ops.update_runtime_declined")
    done: list = []
    node_bin: Path | None = None
    for item in items:
        try:
            runtimes.install(nctx, item, node_bin=node_bin)
        except (InstallerError, OSError) as e:
            _remove_new_runtimes(ctx, done)
            return _fail(run, EXIT_FAILED, "U3", err=e if isinstance(e, InstallerError) else None)
        done.append(item)
        if item.name == "node":
            node_bin = Path(item.target) / "bin"
            run.new_node_bin = node_bin
        elif item.name == "pnpm":
            run.new_pnpm_bin = Path(item.target) / "node_modules" / ".bin" / "pnpm"
    run.journal["new_runtimes"] = [i.name for i in done]
    return None


def _remove_node_modules(ctx, root: Path) -> None:
    """Delete every node_modules folder of a release that is not live."""
    if os.path.realpath(root) == os.path.realpath(ctx.paths.app):
        return
    for folder, dirs, _ in os.walk(root):
        for d in list(dirs):
            full = Path(folder) / d
            if d == "node_modules" and not full.is_symlink():
                shutil.rmtree(full, ignore_errors=True)
                dirs.remove(d)
            elif full.is_symlink():
                dirs.remove(d)


def _u4(run: _Run) -> int | None:
    from . import deps

    node_bin = run.new_node_bin or (run.ctx.paths.runtime / "node" / "bin")
    try:
        result = deps.install(_nctx(run), run.new_dir, node_bin, pnpm_bin=run.new_pnpm_bin)
    except (InstallerError, OSError) as e:
        _remove_node_modules(run.ctx, run.new_dir)
        return _fail(run, EXIT_FAILED, "U4", err=e if isinstance(e, InstallerError) else None)
    if isinstance(result, dict) and result.get("rooms") is False:
        say("ops.update_rooms_warn")
    return None


def _u5(run: _Run) -> int | None:
    from . import release

    ctx = run.ctx
    menu_id = getattr(run.info, "menu_id", None)
    if not menu_id:
        return None
    try:
        if (ctx.paths.shared / "menu-slides" / menu_id).is_dir():
            release.link_menu(_nctx(run), run.new_dir, menu_id)
            return None
        given = getattr(run.args, "menu", None)
        tar = Path(given) if given else run.file.parent / f"thomhouse-menu-{menu_id}.tar"
        if tar.is_file():
            got = release.install_menu(_nctx(run), tar)
            release.link_menu(_nctx(run), run.new_dir, got)
            return None
        say("ops.update_menu_missing", menu_id=menu_id, tb=tb(ctx.paths))
    except (InstallerError, OSError, ValueError) as e:
        _ulog(ctx, "menu_warning", error=type(e).__name__)
        say("ops.update_menu_warn", menu_id=menu_id)
    return None


def _u6(run: _Run) -> int | None:
    from .paths import ENV_FILES

    paths = run.ctx.paths
    try:
        for name in ENV_NAMES:
            src = paths.env_file(name)
            if not src.is_file():
                continue
            dest = run.new_dir.joinpath(*ENV_FILES[name])
            if dest.is_symlink():
                dest.unlink()
            copy_private(src, dest)
    except OSError as e:
        _ulog(run.ctx, "env_copy_failed", error=type(e).__name__)
        return _fail(run, EXIT_FAILED, "U6")
    return None


def _u7(run: _Run) -> int | None:
    from . import stack

    if not stack.stop(run.ctx):
        return _fail(run, EXIT_FAILED, "U7", restart=True)
    return None


def _u8(run: _Run) -> int | None:
    try:
        info = backup.make(run.ctx, mode="stopped", reason=f"before-update-{run.info.version}")
    except (InstallerError, OSError) as e:
        return _fail(run, EXIT_FAILED, "U8", err=e if isinstance(e, InstallerError) else None, restart=True)
    run.journal["backup"] = info.id
    return None


def _u9(run: _Run) -> int | None:
    from . import release, runtimes

    ctx = run.ctx
    if not run.journal.get("to_runtimes"):
        run.journal["to_runtimes"] = _runtimes_of(_nctx(run))
    _save(run)  # from_runtimes and to_runtimes are on disk before anything is switched
    to_rt = run.journal.get("to_runtimes") or {}
    try:
        for name in run.journal.get("new_runtimes") or []:
            if to_rt.get(name):
                runtimes.switch(ctx, name, to_rt[name])
        release.switch_app(ctx, run.info.version)
        release.write_launcher(ctx, run.new_dir)
    except (InstallerError, OSError) as e:
        _ulog(ctx, "switch_failed", error=type(e).__name__)
        say("ops.update_switch_failed", tb=tb(ctx.paths), file=str(run.file))
        return EXIT_FAILED  # the journal stays open: `update FILE` continues here, `rollback` goes back
    return None


def _u10(run: _Run) -> int | None:
    pend = migrations.pending(run.new_dir, run.ctx.paths.bot_home)
    if pend == []:
        return None
    code = migrations.apply(run.ctx, run.new_dir)
    if code != 0:
        _ulog(run.ctx, "migrations_failed", exit=code)
        return _roll_back(run, "U10")
    return None


def _u11(run: _Run) -> int | None:
    from . import stack

    code = stack.start(run.ctx, during_update=True)
    if code != 0:
        _ulog(run.ctx, "start_failed", exit=code)
        stack.stop(run.ctx)
        return _roll_back(run, "U11")
    return None


def _u12(run: _Run) -> int | None:
    from . import doctor, stack

    run.health_failed = list(stack.health_gate(run.ctx))
    results = doctor.run_checks(run.ctx, only=set(SAFETY_CHECKS))
    run.failed_checks = [r for r in results if getattr(r, "status", None) == "fail"]
    if run.health_failed or run.failed_checks:
        _ulog(run.ctx, "health_failed", ids=run.health_failed + [r.id for r in run.failed_checks])
    return None


def _u13(run: _Run) -> int | None:
    from . import release

    ctx = run.ctx
    paths = ctx.paths
    j = run.journal
    info = run.info
    inst = state.load_installed(paths) or {}
    if inst.get("version") != info.version:
        inst["previous_version"] = j.get("from")
        inst["previous_runtimes"] = j.get("from_runtimes")
        inst["previous_release_id"] = inst.get("release_id")
        inst["previous_payload_sha256"] = inst.get("payload_sha256")
        inst["previous_menu_id"] = inst.get("menu_id")
    applied = migrations.applied(paths.bot_home)
    inst.update({
        "version": info.version,
        "runtimes": j.get("to_runtimes") or inst.get("runtimes"),
        "backup_before_update": j.get("backup"),
        "migrations_applied": applied if applied is not None else [],
        "release_id": getattr(info, "release_id", None),
        "payload_sha256": getattr(info, "payload_sha256", None),
        "menu_id": getattr(info, "menu_id", None),
        "updated_at": backup.now_iso(),
    })
    state.save_installed(paths, inst)
    _history(paths, j, "failed" if (run.health_failed or run.failed_checks) else "ok")
    try:
        release.prune(ctx, keep_previous=1)
    except (InstallerError, OSError) as e:
        _ulog(ctx, "prune_failed", error=type(e).__name__)
    j["state"] = "done"
    j["finished_at"] = backup.now_iso()
    return None


_FUNCS = {"U1": _u1, "U2": _u2, "U3": _u3, "U4": _u4, "U5": _u5, "U6": _u6, "U7": _u7, "U8": _u8, "U9": _u9,
          "U10": _u10, "U11": _u11, "U12": _u12, "U13": _u13}


def _phases(run: _Run, start_at: str) -> int:
    for name in PHASES[PHASES.index(start_at):]:
        run.journal.setdefault("phases", {})[name] = "running"
        _save(run)
        _ulog(run.ctx, "phase_start", phase=name)
        code = _FUNCS[name](run)
        if code is not None:
            _ulog(run.ctx, "phase_stop", phase=name, exit=code)
            return code
        run.journal["phases"][name] = "done"
        _save(run)
        _ulog(run.ctx, "phase_done", phase=name)
        _after_phase(name)
    paths = run.ctx.paths
    if run.health_failed or run.failed_checks:
        for check_id in run.health_failed:
            say(f"ops.health_{check_id}")
        backup.print_failed_checks(run.failed_checks)
        say("ops.update_health_failed", version=run.info.version, tb=tb(paths))
        return EXIT_FAILED
    say("ops.update_done", version=run.info.version)
    return EXIT_OK


# ---------------------------------------------------------------- rollback after U10 or U11, and switching back

def _switch_back(ctx, journal: dict) -> None:
    """Undo U9: the runtimes this update installed, `app` and the launcher (nothing when U9 never started)."""
    from . import release, runtimes

    if "U9" not in (journal.get("phases") or {}):
        return
    from_rt = journal.get("from_runtimes") or {}
    for name in journal.get("new_runtimes") or []:
        if name in SWITCHED_BACK and from_rt.get(name):
            runtimes.switch(ctx, name, from_rt[name])
    old = journal["from"]
    release.switch_app(ctx, old)
    release.write_launcher(ctx, ctx.paths.release_dir(old))


def _roll_back(run: _Run, phase: str) -> int:
    run.journal["phases"]["U10"] = "rollback"
    _save(run)
    return _finish_rollback(run.ctx, run.journal, phase=phase, command="update")


def _finish_rollback(ctx, journal: dict, *, phase: str | None, command: str) -> int:
    """Rollback of U10 (rev F14, rev check): set the current `d1` aside as `d1.failed-<stamp>`, copy `d1` back from
    the journal's backup, switch back, close the journal as "rolled_back" and start the old release. When the copy
    fails, nothing is started and the journal keeps its mark, so a later `update FILE` or `rollback` finishes it."""
    from . import stack

    paths = ctx.paths
    bid = journal.get("backup")
    bdir = paths.backups / bid if isinstance(bid, str) and bid else None
    if bdir is None or backup.read_meta(bdir) is None:
        say("ops.update_rollback_no_backup", tb=tb(paths))
        return EXIT_FAILED
    if paths.d1_dir.exists() or paths.d1_dir.is_symlink():
        failed_dir = unique_path(paths.bot_home / f"d1.failed-{stamp()}")
        os.rename(paths.d1_dir, failed_dir)
        try:
            os.chmod(failed_dir, 0o700)
        except OSError:
            pass
        journal.setdefault("d1_failed", []).append(str(failed_dir))
        state.update_set(paths, journal)
    kept = (journal.get("d1_failed") or ["?"])[-1]
    try:
        backup.copy_d1_back(bdir, paths)
    except OSError as e:
        _ulog(ctx, "rollback_copy_failed", error=type(e).__name__)
        say("ops.update_d1_copy_failed", backup=tilde(bdir, paths), failed=tilde(kept, paths), tb=tb(paths),
            file=str(journal.get("file") or "FILE"))
        return EXIT_FAILED
    try:
        _switch_back(ctx, journal)
    except (InstallerError, OSError) as e:
        _ulog(ctx, "switch_back_failed", error=type(e).__name__)
        say("ops.update_switch_back_failed", tb=tb(paths), file=str(journal.get("file") or "FILE"))
        return EXIT_FAILED
    journal["state"] = "rolled_back"
    state.update_set(paths, journal)
    _history(paths, journal, "rolled_back", event="update" if command == "update" else "rollback")
    _ulog(ctx, "rolled_back", phase=phase)
    code = stack.start(ctx, during_update=True)
    if command == "rollback":
        say("ops.rollback_done", version=journal.get("from"))
        return EXIT_OK if code == 0 else EXIT_FAILED
    say("ops.update_rolled_back", title=_title(phase or "U10"), old=journal.get("from"), log=_log_path(ctx))
    return EXIT_FAILED


# ---------------------------------------------------------------- commands

def cmd_update(ctx, args) -> int:
    """`thomhouse update FILE [--menu FILE] [--dry-run] [--yes]`: 0 done (or the same version), 1 failed or rolled
    back, 3 refused, 4 declined."""
    paths = ctx.paths
    file = Path(args.file)
    opened = state.update_open(paths)
    if opened is not None:
        if not _same_file(paths, file, opened):
            raise Exit(EXIT_REFUSED, "core.update_open", file=str(opened.get("file") or "FILE"))
        phases = opened.get("phases") or {}
        if phases.get("U10") == "rollback":
            if ctx.dry_run:
                say("ops.update_dry_rollback", old=opened.get("from"))
                return EXIT_OK
            return _finish_rollback(ctx, opened, phase=None, command="update")
        if "U9" in phases:
            return _resume(ctx, args, file, opened)
        return _start_again(ctx, args, file, opened)
    return _start(ctx, args, file)


def _still_open(paths, opened: dict) -> bool:
    current = state.update_open(paths)
    return current is not None and current.get("started_at") == opened.get("started_at")


def _start_again(ctx, args, file: Path, opened: dict) -> int:
    """An update interrupted before U9 (a power cut or a closed window): `app` still points at the old release, but
    the stack may be down since U7 and `start` is refused while the journal is open. `update FILE` asks again and
    starts at U1; any other outcome (k, a file that does not verify, the same or an older version) closes the old
    journal as "rolled_back" and starts the old release, so the bot does not stay off. A dry run changes nothing."""
    try:
        code = _start(ctx, args, file, unfinished=True)
    except InstallerError:
        if not ctx.dry_run and _still_open(ctx.paths, opened):
            _close_unfinished(ctx, opened)
        raise
    if not ctx.dry_run and _still_open(ctx.paths, opened):
        if _close_unfinished(ctx, opened) != EXIT_OK and code == EXIT_OK:
            code = EXIT_FAILED
    return code


def _close_unfinished(ctx, journal: dict) -> int:
    """Close an update journal that never reached U9 (nothing was switched) and start the old release."""
    from . import stack

    paths = ctx.paths
    journal["state"] = "rolled_back"
    state.update_set(paths, journal)
    _history(paths, journal, "rolled_back")
    _ulog(ctx, "unfinished_closed", phases=sorted(journal.get("phases") or {}))
    code = stack.start(ctx, during_update=True)
    if code == 0:
        say("ops.update_unfinished_closed", old=journal.get("from"))
        return EXIT_OK
    say("ops.update_unfinished_start_failed", old=journal.get("from"), log=tilde(paths.logs / "start.log", paths),
        tb=tb(paths))
    return EXIT_FAILED


def _start(ctx, args, file: Path, *, unfinished: bool = False) -> int:
    from . import consent, release

    paths = ctx.paths
    current = backup.installed_version(paths)
    if state.load_installed(paths) is None or current is None:
        raise Exit(EXIT_REFUSED, "ops.update_not_installed", tb=tb(paths))
    info = release.verify_file(ctx, file, first_install=False)
    order = _compare(info.version, current)
    if order is None:
        say("ops.update_bad_version")
        return EXIT_REFUSED
    if order == 0:
        say("ops.update_same", version=info.version)
        return EXIT_OK
    if order < 0:
        say("ops.update_older", new=info.version, current=current, tb=tb(paths))
        return EXIT_REFUSED
    if ctx.dry_run:
        say("ops.update_dry_run", old=current, new=info.version)
        for name in PHASES:
            say("ops.update_dry_phase", phase=name, title=_title(name))
        return EXIT_OK
    if consent.ask(ctx, "ops.update_confirm", "ck", old=current, new=info.version) != "c":
        say("ops.update_declined_unfinished" if unfinished else "ops.update_declined")
        return EXIT_DECLINED
    journal = {"from": current, "to": info.version, "file": str(file), "from_runtimes": _from_runtimes(ctx),
               "to_runtimes": None, "new_runtimes": [], "backup": None, "phases": {}, "state": "running",
               "started_at": backup.now_iso()}
    state.update_set(paths, journal)
    _ulog(ctx, "update_start", old=current, new=info.version)
    run = _Run(ctx=ctx, args=args, file=file, info=info, journal=journal, new_dir=paths.release_dir(info.version))
    return _phases(run, "U1")


def _resume(ctx, args, file: Path, journal: dict) -> int:
    from . import release

    paths = ctx.paths
    info = release.verify_file(ctx, file, first_install=False)
    if info.version != journal.get("to"):
        raise Exit(EXIT_REFUSED, "core.update_open", file=str(journal.get("file") or "FILE"))
    phases = journal.get("phases") or {}
    start_at = next((p for p in PHASES[8:] if phases.get(p) != "done"), None)
    if ctx.dry_run:
        say("ops.update_dry_resume", phase=start_at or "U13", title=_title(start_at or "U13"))
        return EXIT_OK
    if start_at is None:
        journal["state"] = "done"
        state.update_set(paths, journal)
        say("ops.update_done", version=info.version)
        return EXIT_OK
    say("ops.update_resuming", phase=start_at, title=_title(start_at), new=info.version)
    _ulog(ctx, "update_resume", phase=start_at)
    run = _Run(ctx=ctx, args=args, file=file, info=info, journal=journal, new_dir=paths.release_dir(info.version))
    return _phases(run, start_at)


def _needs_restore(paths, prev_dir: Path, recorded: object) -> bool:
    """A migration applied now (or recorded in installed.json) that the previous release lacks."""
    names = set(recorded) if isinstance(recorded, list) else set()
    live = migrations.applied(paths.bot_home)
    if live:
        names |= set(live)
    try:
        known = {p.name for p in (prev_dir / "apps" / "server" / "migrations").glob("*.sql")}
    except OSError:
        known = set()
    return any(str(n) not in known for n in names)


def _confirm_restore(ctx, bdir: Path, aside: Path, version: str) -> bool:
    from . import consent

    meta = backup.read_meta(bdir) or {}
    when = backup.fmt_time(str(meta.get("created_at") or ""))
    return consent.typed(ctx, "ops.rollback_confirm", ("khoi phuc",), version=version, time=when,
                         reason=str(meta.get("reason") or ""), folder=tilde(aside, ctx.paths))


def cmd_rollback(ctx, args) -> int:
    """`thomhouse rollback [--dry-run]`: 0 done, 1 failed, 3 no previous release, 4 declined."""
    from . import release, runtimes, stack

    paths = ctx.paths
    opened = state.update_open(paths)
    if opened is not None:
        return _rollback_open(ctx, opened)
    inst = state.load_installed(paths)
    if inst is None:
        raise Exit(EXIT_REFUSED, "ops.update_not_installed", tb=tb(paths))
    prev = inst.get("previous_version")
    if not isinstance(prev, str) or not prev:
        say("ops.rollback_none")
        return EXIT_REFUSED
    prev_dir = paths.release_dir(prev)
    if not (prev_dir / "VERSION.json").is_file():
        say("ops.rollback_missing", version=prev)
        return EXIT_REFUSED
    current = inst.get("version")
    restore = _needs_restore(paths, prev_dir, inst.get("migrations_applied"))
    bdir = None
    if restore:
        bid = inst.get("backup_before_update")
        bdir = paths.backups / bid if isinstance(bid, str) and bid else None
        if bdir is None or not backup.verify(bdir):
            say("ops.rollback_no_backup", version=prev)
            return EXIT_REFUSED
    if ctx.dry_run:
        say("ops.rollback_dry_run", old=prev, current=current)
        if restore and bdir is not None:
            say("ops.rollback_dry_restore", id=bdir.name)
        return EXIT_OK
    aside = unique_path(paths.backups / f"{stamp()}-before-restore")
    if restore and bdir is not None and not _confirm_restore(ctx, bdir, aside, prev):
        say("ops.restore_declined")
        return EXIT_DECLINED
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        stack.start(ctx, quiet=True)
        return EXIT_FAILED
    if restore and bdir is not None:
        try:
            backup._restore_into(ctx, bdir, same_device=True, aside=aside)
        except (OSError, InstallerError) as e:
            _ulog(ctx, "rollback_restore_failed", error=type(e).__name__)
            say("ops.restore_failed", log=tilde(paths.logs / "ops.log", paths))
            stack.start(ctx, quiet=True)
            state.history_append(paths, {"event": "rollback", "from": current, "to": prev, "result": "failed",
                                         "backup": bdir.name})
            return EXIT_FAILED
    from_rt = inst.get("runtimes") if isinstance(inst.get("runtimes"), dict) else {}
    to_rt = inst.get("previous_runtimes") if isinstance(inst.get("previous_runtimes"), dict) else {}
    for name in SWITCHED_BACK:
        if to_rt.get(name) and from_rt.get(name) != to_rt.get(name):
            runtimes.switch(ctx, name, to_rt[name])
    release.switch_app(ctx, prev)
    release.write_launcher(ctx, prev_dir)
    applied = migrations.applied(paths.bot_home)
    inst.update({
        "version": prev,
        "previous_version": None,
        "runtimes": to_rt or from_rt or None,
        "previous_runtimes": None,
        "backup_before_update": None,
        "release_id": inst.get("previous_release_id"),
        "payload_sha256": inst.get("previous_payload_sha256"),
        "menu_id": inst.get("previous_menu_id"),
        "previous_release_id": None,
        "previous_payload_sha256": None,
        "previous_menu_id": None,
        "migrations_applied": applied if applied is not None else [],
        "rolled_back_at": backup.now_iso(),
    })
    state.save_installed(paths, inst)
    code = stack.start(ctx)
    state.history_append(paths, {"event": "rollback", "from": current, "to": prev,
                                 "result": "ok" if code == 0 else "failed",
                                 "backup": bdir.name if bdir is not None else None})
    _ulog(ctx, "rollback", old=current, new=prev, restored=restore)
    say("ops.rollback_done", version=prev)
    return EXIT_OK if code == 0 else EXIT_FAILED


def _rollback_open(ctx, journal: dict) -> int:
    """`rollback` while an update journal is open: use the journal's from, from_runtimes and backup."""
    from . import stack

    paths = ctx.paths
    phases = journal.get("phases") or {}
    if phases.get("U10") == "rollback":
        if ctx.dry_run:
            say("ops.update_dry_rollback", old=journal.get("from"))
            return EXIT_OK
        return _finish_rollback(ctx, journal, phase=None, command="rollback")
    restore = "U10" in phases
    if ctx.dry_run:
        say("ops.rollback_dry_run", old=journal.get("from"), current=journal.get("to"))
        if restore:
            say("ops.rollback_dry_restore", id=str(journal.get("backup") or "?"))
        return EXIT_OK
    if restore and "U11" in phases:
        # The new release may have run and stored messages after the U8 backup: ask before replacing d1.
        bid = journal.get("backup")
        bdir = paths.backups / bid if isinstance(bid, str) and bid else None
        aside = unique_path(paths.bot_home / f"d1.failed-{stamp()}")
        if bdir is None or not _confirm_restore(ctx, bdir, aside, str(journal.get("from"))):
            say("ops.restore_declined")
            return EXIT_DECLINED
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        return EXIT_FAILED
    if restore:
        journal["phases"]["U10"] = "rollback"
        state.update_set(paths, journal)
        return _finish_rollback(ctx, journal, phase=None, command="rollback")
    try:
        _switch_back(ctx, journal)
    except (InstallerError, OSError) as e:
        _ulog(ctx, "switch_back_failed", error=type(e).__name__)
        say("ops.update_switch_back_failed", tb=tb(paths), file=str(journal.get("file") or "FILE"))
        return EXIT_FAILED
    journal["state"] = "rolled_back"
    state.update_set(paths, journal)
    _history(paths, journal, "rolled_back", event="rollback")
    code = stack.start(ctx, during_update=True)
    say("ops.rollback_done", version=journal.get("from"))
    return EXIT_OK if code == 0 else EXIT_FAILED
