#!/usr/bin/env python3
"""thom house installer CLI (docs/contracts.md 16.4.1).

    ~/ThomHouse/bin/thomhouse <command> [options]        on a device (the launcher runs this file with python3 -I)
    python3 -I install/thomhouse.py <command> [options]  in the project on the build Mac (checkout mode)

The dispatcher parses the command line, resolves the paths from the logical location of this file, refuses what
checkout mode, a moved-out device or an unfinished update does not allow, takes `InstallLock` for changing
commands, and calls `cmd_<name>(ctx, args)` of the package that owns the command. A package that is not built yet
gives exit 2 with one line. Exit codes: 0 done, 1 failed, 2 bad arguments or internal error, 3 refused,
4 declined, 10 human steps pending (install, continue).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# python3 -I does not put this file's folder on sys.path (rev F2), so the package beside it is added here.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# -I also ignores PYTHONDONTWRITEBYTECODE; no __pycache__ is written into a release or the checkout.
sys.dont_write_bytecode = True

CODE_ROOT = Path(os.path.abspath(__file__)).parent.parent  # logical: symlinks kept

# command: (module, handler, takes InstallLock, allowed in checkout mode)
DISPATCH: dict[str, tuple[str, str, bool, bool]] = {
    "install": ("steps", "cmd_install", True, False),
    "continue": ("steps", "cmd_continue", True, False),
    "start": ("service", "cmd_start", True, False),
    "stop": ("service", "cmd_stop", True, False),
    "restart": ("service", "cmd_restart", True, False),
    "doctor": ("doctor", "cmd_doctor", False, True),
    "update": ("update", "cmd_update", True, False),
    "rollback": ("update", "cmd_rollback", True, False),
    "backup": ("backup", "cmd_backup", False, True),
    "backups": ("backup", "cmd_backups", False, True),
    "restore": ("backup", "cmd_restore", True, True),
    "move-out": ("move", "cmd_move_out", True, True),
    "move-in": ("move", "cmd_move_in", True, False),
    "move-back": ("move", "cmd_move_back", True, True),
    "uninstall": ("uninstall", "cmd_uninstall", True, False),
    "login-claude": ("human", "cmd_login_claude", True, False),
    "add-claude": ("human", "cmd_add_claude", True, False),
    "login-zalo": ("human", "cmd_login_zalo", True, False),
    "sync-history": ("human", "cmd_sync_history", True, False),
    "analyze": ("human", "cmd_analyze", True, False),
    "labels": ("human", "cmd_labels", True, False),
    "staff-token": ("human", "cmd_staff_token", False, False),
    "autostart": ("autostart", "cmd_autostart", True, False),
    "shortcuts": ("autostart", "cmd_shortcuts", True, False),
    "repair": ("repair", "cmd_repair", True, False),
}
ALLOWED_MOVED_OUT = frozenset({"doctor", "backup", "backups", "stop", "move-back", "uninstall"})
ALLOWED_UPDATE_OPEN = frozenset({"update", "rollback", "doctor", "backup", "backups", "stop", "uninstall"})
COMMON = ("yes", "dry_run", "quiet", "offline", "json")


def _version_text(code_root: Path) -> str:
    try:
        data = json.loads((code_root / "VERSION.json").read_text(encoding="utf-8"))
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "checkout"


def _tilde(path: Path, home: str) -> str:
    text = str(path)
    home = home.rstrip("/")
    if home and (text == home or text.startswith(home + "/")):
        return "~" + text[len(home):]
    return text


def _tb(code_root: Path) -> str:
    """How the person types this program: the launcher, or the checkout form."""
    if not (code_root / "VERSION.json").is_file():
        return "python3 -I install/thomhouse.py"
    home = os.environ.get("HOME", "")
    app_home = os.environ.get("THOMHOUSE_APP_HOME") or os.path.join(home, "ThomHouse")
    return _tilde(Path(app_home) / "bin" / "thomhouse", home)


def _abs_path(value: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(value)))


def _check_set(value: str) -> set[str]:
    return {x.strip() for x in value.split(",") if x.strip()}


def _consented(value: str) -> list[str]:
    allowed = ("python", "node", "pnpm", "claude_code")
    items = [x.strip() for x in value.split(",") if x.strip()]
    for item in items:
        if item not in allowed:
            raise argparse.ArgumentTypeError(f"unknown runtime {item!r}")
    return items


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        try:
            from thomhouse_installer.text_vi import t

            print(t("core.bad_args", tb=_tb(CODE_ROOT)), file=sys.stderr)
        except Exception:  # noqa: BLE001 - the English line above is enough
            pass
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """The argparse tree of every command of 16.4.1."""
    p = _Parser(prog="thomhouse", description="thom house chatbot installer")
    p.add_argument("--version", action="store_true", help="print the installed version")
    sub = p.add_subparsers(dest="command", parser_class=_Parser, metavar="COMMAND")

    def cmd(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text)

    hidden = argparse.SUPPRESS
    c = cmd("install", "install or resume the install on this Mac")
    c.add_argument("--yes", action="store_true")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--skip-human", action="store_true")
    c.add_argument("--only", metavar="STEP")
    c.add_argument("--menu", type=_abs_path, metavar="FILE")
    c.add_argument("--move-in", type=_abs_path, metavar="FILE")
    c.add_argument("--from-bootstrap", action="store_true", help=hidden)
    c.add_argument("--consented", type=_consented, default=[], help=hidden)
    c.add_argument("--release-file", type=_abs_path, help=hidden)
    c.add_argument("--trust-channel", action="store_true", help=hidden)

    c = cmd("continue", "run the steps that are not done yet")
    c.add_argument("--yes", action="store_true")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--skip-human", action="store_true")

    c = cmd("start", "start the chatbot")
    c.add_argument("--quiet", action="store_true")
    cmd("stop", "stop the chatbot")
    cmd("restart", "stop and start the chatbot")

    c = cmd("doctor", "check every prerequisite and step")
    c.add_argument("--json", action="store_true")
    c.add_argument("--offline", action="store_true")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--only", type=_check_set, metavar="CHECK[,CHECK...]")

    c = cmd("update", "update from a release file")
    c.add_argument("file", type=_abs_path, metavar="FILE")
    c.add_argument("--menu", type=_abs_path, metavar="FILE")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--yes", action="store_true")

    c = cmd("rollback", "go back to the previous release")
    c.add_argument("--dry-run", action="store_true")

    c = cmd("backup", "back up the chatbot data")
    mode = c.add_mutually_exclusive_group()
    mode.add_argument("--online", dest="mode", action="store_const", const="online")
    mode.add_argument("--stopped", dest="mode", action="store_const", const="stopped")
    c.add_argument("--reason", choices=("manual", "before-migration"), default="manual")
    c.add_argument("--if-pending-migrations", action="store_true")
    c.add_argument("--quiet", action="store_true")

    cmd("backups", "list the backups")

    c = cmd("restore", "restore a backup")
    c.add_argument("id", metavar="ID")
    c.add_argument("--dry-run", action="store_true")

    c = cmd("move-out", "move the data to another Mac")
    c.add_argument("--to", type=_abs_path, required=True, metavar="DIR")
    c = cmd("move-in", "take the data of another Mac")
    c.add_argument("file", type=_abs_path, metavar="FILE")
    cmd("move-back", "run the chatbot on this Mac again after a move-out")

    c = cmd("uninstall", "remove the program (data kept unless --data)")
    c.add_argument("--data", action="store_true")
    c.add_argument("--dry-run", action="store_true")

    c = cmd("login-claude", "log a Claude account of the chatbot in")
    c.add_argument("label", nargs="?", default=None, metavar="LABEL")
    c = cmd("add-claude", "add another Claude account to the chatbot")
    c.add_argument("label", metavar="LABEL")
    c.add_argument("--priority", type=int, default=100, metavar="N")
    cmd("login-zalo", "log the studio's Zalo account in")
    c = cmd("sync-history", "fetch older Zalo messages")
    c.add_argument("--force", action="store_true")
    c = cmd("analyze", "run the contact and visit analyzers")
    c.add_argument("--contacts", action="store_true")
    c.add_argument("--visits", action="store_true")
    c = cmd("labels", "check and copy the Zalo labels")
    c.add_argument("--sync", action="store_true")
    cmd("staff-token", "put the staff token on the clipboard for the console")

    c = cmd("autostart", "start the chatbot at login")
    c.add_argument("state", choices=("on", "off"))
    c = cmd("shortcuts", "Desktop buttons")
    c.add_argument("state", choices=("on", "off"))

    c = cmd("repair", "repair the program files")
    c.add_argument("--paths", action="store_true")
    c.add_argument("--env", action="store_true")
    return p


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse `argv`; every Namespace gets `command` and the common flags (False unless the command has them)."""
    args = build_parser().parse_args(argv)
    for name in COMMON:
        if not hasattr(args, name):
            setattr(args, name, False)
    return args


def _defaults(paths, args: argparse.Namespace) -> dict[str, object]:
    """Format values the dispatcher supplies when an error's own `fmt` lacks them ({tb}, {cmd}, {file})."""
    from thomhouse_installer import state

    tb = _tb(paths.code_root)
    if paths.installed_json.exists():
        again = f"{tb} continue"
    elif getattr(args, "release_file", None):
        again = f"bash {args.release_file}"
    else:
        again = f"bash thomhouse-{_version_text(paths.code_root)}.command"
    journal = state.update_get(paths) or {}
    return {"tb": tb, "cmd": again, "file": journal.get("file") or "FILE", "name": "", "host": ""}


def _say_error(err, paths, args) -> None:
    from thomhouse_installer.text_vi import t

    if getattr(err, "key", None) is None:
        return
    fmt: dict[str, object] = {}
    if paths is not None:
        try:
            fmt.update(_defaults(paths, args))
        except Exception:  # noqa: BLE001 - defaults are a convenience
            pass
    else:
        fmt.update({"tb": _tb(CODE_ROOT), "cmd": "", "file": "FILE", "name": "", "host": ""})
    fmt.update(getattr(err, "fmt", {}) or {})
    try:
        print(t(err.key, **fmt), flush=True)
    except (KeyError, IndexError, ValueError):
        print(t("core.failed"), flush=True)


def _log_crash(paths, exc: BaseException) -> None:
    import traceback

    if paths is None:
        return
    try:
        from thomhouse_installer import proc

        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        text = proc.redact(text, proc.secret_values(paths))
        paths.logs.mkdir(parents=True, exist_ok=True)
        fd = os.open(paths.logs / "install.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "internal_error", "type": type(exc).__name__, "traceback": text},
                               ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - nothing more can be done
        pass


def _drop_bootstrap_lock(paths) -> None:
    """Remove APP_HOME/.bootstrap.lock.d when its pid file holds this process's PID (rev F6)."""
    lock_dir = paths.bootstrap_lock_dir
    pid_file = lock_dir / "pid"
    try:
        holder = pid_file.read_text(encoding="ascii").strip()
    except OSError:
        return
    if holder == str(os.getpid()):
        try:
            pid_file.unlink()
            lock_dir.rmdir()
        except OSError:
            pass


def _load_handler(module_name: str, func_name: str):
    """The handler function, or None when its module (or function) is not built yet."""
    import importlib

    full = f"thomhouse_installer.{module_name}"
    try:
        module = importlib.import_module(full)
    except ModuleNotFoundError as e:
        if e.name == full:
            return None
        raise
    return getattr(module, func_name, None)


def main(argv: list[str] | None = None) -> int:
    """Run one command and return its exit code."""
    try:
        args = parse_args(argv)
    except SystemExit as e:  # argparse: --help gives 0, an error gives 2
        return int(e.code or 0) if isinstance(e.code, int) else 2
    if args.version:
        print(_version_text(CODE_ROOT))
        return 0
    if not args.command:
        build_parser().print_help()
        return 2

    from thomhouse_installer import context, paths as paths_mod, state

    paths = None
    try:
        paths = paths_mod.resolve(os.environ, code_root=CODE_ROOT)
        module_name, func_name, takes_lock, checkout_ok = DISPATCH[args.command]
        if paths.mode == "checkout" and not checkout_ok:
            raise context.Exit(3, "core.checkout_only")
        if state.moved_out(paths) is not None and args.command not in ALLOWED_MOVED_OUT:
            raise context.Exit(3, "core.moved_out")
        journal = state.update_open(paths)
        if journal is not None and args.command not in ALLOWED_UPDATE_OPEN:
            raise context.Exit(3, "core.update_open", file=str(journal.get("file") or "FILE"))
        ctx = context.make_ctx(args, paths=paths)
        handler = _load_handler(module_name, func_name)
        if handler is None:
            from thomhouse_installer.text_vi import say

            say("core.not_built", part=module_name, command=args.command)
            return context.EXIT_USAGE
        ctx.log("command", command=args.command)
        if takes_lock and not args.dry_run:
            with state.InstallLock(paths):
                _drop_bootstrap_lock(paths)
                code = handler(ctx, args)
        else:
            code = handler(ctx, args)
        return int(code) if code is not None else 0
    except context.InstallerError as err:
        _say_error(err, paths, args)
        return int(err.code)
    except KeyboardInterrupt:
        from thomhouse_installer.text_vi import say

        print()
        say("core.interrupted")
        return context.EXIT_FAILED
    except Exception as exc:  # noqa: BLE001 - every crash ends as exit 2 with the type name only
        from thomhouse_installer.text_vi import say

        _log_crash(paths, exc)
        say("core.internal_error", name=type(exc).__name__)
        return context.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
