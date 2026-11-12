"""`thomhouse uninstall [--data] [--dry-run]` (16.8.6, rev F24).

Default: offer a backup, stop the stack, remove the LaunchAgent and the Desktop files when their content equals the
template output, delete APP_HOME (program, runtimes, caches; all rebuildable) and name what stays: BOT_HOME,
~/.zalo-agent-cli, Claude Code in ~/.local and the staff token in the browser.

`--data`, after the typed words, in this order: a final verified backup inside BOT_HOME; the choice of where BOT_HOME
goes, probed before anything irreversible (~/.Trash, else ~/thomhouse-bot-da-xoa-<stamp>; neither: stop, nothing
logged out or stopped); then, with BOT_HOME still in place, the stack, the listener and every Claude account with a
config folder are stopped or logged out; then BOT_HOME is renamed; then APP_HOME goes as in the default.
~/.zalo-agent-cli and ~/.claude are never touched.

APP_HOME holds this very program, so everything the end of the command needs is imported before it is deleted,
and nothing is logged after it is gone.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Imported here, not inside the functions: APP_HOME, which holds this program, is deleted before the command ends.
from . import accounts, autostart, backup, bridgecli, consent, proc, stack, state
from .backup import oplog, stamp, tb, tilde, unique_path
from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK, EXIT_REFUSED, InstallerError
from .text_vi import say


def _app_home_ok(paths) -> bool:
    """APP_HOME looks like this installation's program folder: not HOME, not "/", not holding BOT_HOME."""
    app_home = os.path.realpath(paths.app_home)
    home = os.path.realpath(paths.home)
    bot = os.path.realpath(paths.bot_home)
    if app_home in ("/", home) or home.startswith(app_home + "/") or bot == app_home or bot.startswith(app_home + "/"):
        return False
    if paths.app_home.is_symlink() or not paths.app_home.is_dir():
        return False
    return paths.installed_json.exists() or (paths.app_home / "releases").is_dir()


def _say_error(ctx, err: InstallerError) -> None:
    try:
        say(err.key, **{"tb": tb(ctx.paths), **err.fmt})
    except (KeyError, IndexError, ValueError):
        pass


def _dry_run(ctx, data: bool) -> int:
    paths = ctx.paths
    say("ops.uninstall_dry_header")
    for path in autostart.owned_files(ctx):
        say("ops.uninstall_dry_item", path=tilde(path, paths))
    say("ops.uninstall_dry_item", path=tilde(paths.app_home, paths))
    if data:
        say("ops.uninstall_dry_data", folder=tilde(paths.bot_home, paths))
    else:
        say("ops.uninstall_dry_keep", folder=tilde(paths.bot_home, paths))
    return EXIT_OK


def _remove_program(ctx) -> bool:
    """Remove autostart and shortcuts, then APP_HOME. True when APP_HOME is gone."""
    paths = ctx.paths
    removed = autostart.remove_all(ctx)
    oplog(ctx, "uninstall_program", removed=len(removed))
    state.history_append(paths, {"event": "uninstall", "from": backup.installed_version(paths), "to": None,
                                 "result": "ok", "backup": None})
    shutil.rmtree(paths.app_home, ignore_errors=True)
    return not paths.app_home.exists()


def _choose_target(paths) -> tuple[Path, bool] | None:
    """Where BOT_HOME goes, decided by renaming an empty probe folder (rev F24): (target, in the Trash) or None."""
    s = stamp()
    probe = paths.bot_home / f".trash-probe-{s}"
    try:
        probe.mkdir(mode=0o700)
    except OSError:
        return None
    trash = paths.home / ".Trash"
    choices = (
        (trash / f"thomhouse-probe-{s}", trash / f"thomhouse-bot-{s}", True),
        (paths.home / f".thomhouse-probe-{s}", paths.home / f"thomhouse-bot-da-xoa-{s}", False),
    )
    try:
        for probe_target, target, in_trash in choices:
            try:
                os.rename(probe, probe_target)
            except OSError:
                continue
            try:
                probe_target.rmdir()
            except OSError:
                pass
            return unique_path(target), in_trash
        return None
    finally:
        try:
            probe.rmdir()
        except OSError:
            pass


def _logout_accounts(ctx) -> None:
    """`CLAUDE_CONFIG_DIR=<dir> claude auth logout` for every pool account with a config folder; output discarded."""
    try:
        accs = accounts.load(ctx)
    except Exception as e:  # noqa: BLE001 - an unreadable pool means nothing to log out
        oplog(ctx, "uninstall_pool_unreadable", error=type(e).__name__)
        accs = []
    for acc in accs:
        if acc.config_dir is None or not acc.config_dir.is_dir():
            continue
        env = proc.child_env(ctx.paths, {"CLAUDE_CONFIG_DIR": str(acc.config_dir)})
        res = proc.run(ctx, ["claude", "auth", "logout"], env=env, timeout=60)
        oplog(ctx, "uninstall_logout", label=acc.label, exit=res.returncode)


def _finish(ctx, *, data_target: tuple[Path, bool] | None) -> int:
    paths = ctx.paths
    app_home = tilde(paths.app_home, paths)
    zalo = tilde(paths.zalo_config, paths)
    bot = tilde(paths.bot_home, paths)
    if not _remove_program(ctx):
        say("ops.uninstall_partial", folder=app_home)
        return EXIT_FAILED
    say("ops.uninstall_done", folder=app_home)
    if data_target is None:
        say("ops.uninstall_kept", bot=bot, zalo=zalo)
    else:
        say("ops.uninstall_kept_without_data", zalo=zalo)
    return EXIT_OK


def cmd_uninstall(ctx, args) -> int:
    """0 done, 1 failed, 3 refused (APP_HOME does not look like a program folder), 4 declined."""
    paths = ctx.paths
    if not _app_home_ok(paths):
        say("ops.uninstall_odd_app_home", folder=tilde(paths.app_home, paths))
        return EXIT_REFUSED
    data = bool(getattr(args, "data", False))
    if ctx.dry_run:
        return _dry_run(ctx, data)
    if data:
        return _uninstall_with_data(ctx)
    if consent.ask(ctx, "ops.uninstall_offer_backup", "ck") == "c":
        mode = "online" if stack.is_running(paths, "server") else "stopped"
        try:
            info = backup.make(ctx, mode=mode, reason="before-uninstall")
        except InstallerError as e:
            _say_error(ctx, e)
            say("ops.uninstall_nothing_done", tb=tb(paths))
            return e.code
        say("ops.backup_done", id=info.id, mb=f"{info.bytes / 1_000_000:.1f}", folder=tilde(info.path, paths))
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        return EXIT_FAILED
    return _finish(ctx, data_target=None)


def _uninstall_with_data(ctx) -> int:
    paths = ctx.paths
    if not consent.typed(ctx, "ops.uninstall_data_confirm", ("xoa du lieu",)):
        say("ops.uninstall_declined")
        return EXIT_DECLINED
    target = None
    if paths.bot_home.exists():
        # 1. A final verified backup; it lives inside BOT_HOME and moves with it.
        mode = "online" if stack.is_running(paths, "server") else "stopped"
        try:
            backup.make(ctx, mode=mode, reason="before-uninstall")
        except InstallerError as e:
            _say_error(ctx, e)
            say("ops.uninstall_nothing_done", tb=tb(paths))
            return e.code
        # 2. Where BOT_HOME goes, before anything irreversible.
        target = _choose_target(paths)
        if target is None:
            say("ops.uninstall_no_target", folder=tilde(paths.bot_home, paths))
            return EXIT_FAILED
    # 3. With BOT_HOME still in place: stop, free the Zalo session, log the pool accounts out.
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        return EXIT_FAILED
    if target is not None:
        bridgecli.listener(ctx, "stop")
        _logout_accounts(ctx)
        # 4. Move BOT_HOME.
        dest, in_trash = target
        try:
            os.rename(paths.bot_home, dest)
        except OSError as e:
            oplog(ctx, "uninstall_move_failed", error=type(e).__name__)
            say("ops.uninstall_move_failed", bot=tilde(paths.bot_home, paths), target=tilde(dest, paths))
            return EXIT_FAILED
        if in_trash:
            say("ops.uninstall_in_trash", folder=tilde(dest, paths))
        else:
            say("ops.uninstall_drag_to_trash", folder=tilde(dest, paths))
    # 5. The program, as in the default.
    return _finish(ctx, data_target=target or (paths.bot_home, False))
