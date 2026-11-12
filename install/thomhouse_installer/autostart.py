"""Autostart at login (a LaunchAgent) and the three Desktop shortcuts (16.8.8, rev F14, F15, F18).

LaunchAgent ~/Library/LaunchAgents/vn.thomhouse.bot.plist (0644) from install/templates/vn.thomhouse.bot.plist.in:
`/bin/bash <APP_HOME>/bin/thomhouse start --quiet` at load, output in <APP_HOME>/logs/autostart.log. Loaded with
`launchctl bootstrap gui/<uid> <plist>`, removed with `launchctl bootout gui/<uid>/vn.thomhouse.bot` (launchd
behaviour not checked). While an update is unfinished, `start --quiet` exits 3 and leaves the stack stopped.

Desktop files (0755; first line `#!/bin/bash`, second line `# thomhouse-shortcut v1`): Bat-chatbot.command (start),
Kiem-tra-chatbot.command (doctor), Tat-chatbot.command (stop). Every template gets this installation's APP_HOME, so
a non-default THOMHOUSE_APP_HOME works (rev F15). A file is removed only when its content equals the template
output, so a file the person changed is left alone. The line `ops.desktop_prompt` is printed by the caller before
the files are written (rev F18).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import state
from .backup import oplog, tb, tilde
from .context import EXIT_FAILED, EXIT_OK, InstallerError
from .text_vi import say

LABEL = "vn.thomhouse.bot"
PLIST_TEMPLATE = "vn.thomhouse.bot.plist.in"
SHORTCUTS = (
    ("Bat-chatbot.command", "Bat-chatbot.command.in"),
    ("Kiem-tra-chatbot.command", "Kiem-tra-chatbot.command.in"),
    ("Tat-chatbot.command", "Tat-chatbot.command.in"),
)
MARK = "# thomhouse-shortcut v1"
PLACEHOLDER = "@APP_HOME@"


def plist_path(paths) -> Path:
    return paths.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def desktop(paths) -> Path:
    return paths.home / "Desktop"


def render(paths, template: str) -> str:
    """The template filled with this installation's APP_HOME (XML-escaped in the plist)."""
    text = (paths.code_root / "install" / "templates" / template).read_text(encoding="utf-8")
    value = str(paths.app_home)
    return text.replace(PLACEHOLDER, escape(value) if template.endswith(".plist.in") else value)


def _write(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _matches(path: Path, expected: str) -> bool:
    try:
        return not path.is_symlink() and path.is_file() and path.read_text(encoding="utf-8") == expected
    except (OSError, UnicodeDecodeError):
        return False


def _ours(path: Path) -> bool:
    """A Desktop file written by any version of this program (its second line is the marker)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    return len(lines) > 1 and lines[1].strip() == MARK


def _launchctl(ctx, *args: str) -> int:
    from . import proc

    res = proc.run(ctx, ["launchctl", *args], log=ctx.paths.logs / "ops.log", timeout=60)
    return res.returncode


def _set_flag(paths, value: bool) -> None:
    inst = state.load_installed(paths)
    if inst is not None and inst.get("autostart") != value:
        inst["autostart"] = value
        state.save_installed(paths, inst)


def enable(ctx) -> None:
    """Write the LaunchAgent and load it. Raises InstallerError("ops.autostart_failed") when it cannot."""
    paths = ctx.paths
    target = plist_path(paths)
    try:
        _write(target, render(paths, PLIST_TEMPLATE), 0o644)
        paths.logs.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        oplog(ctx, "autostart_write_failed", error=type(e).__name__)
        raise InstallerError("ops.autostart_failed", EXIT_FAILED, log=tilde(paths.logs / "ops.log", paths)) from None
    uid = os.getuid()
    _launchctl(ctx, "bootout", f"gui/{uid}/{LABEL}")  # an older copy may be loaded; not loaded is fine
    code = _launchctl(ctx, "bootstrap", f"gui/{uid}", str(target))
    if code != 0:
        oplog(ctx, "autostart_bootstrap_failed", exit=code)
        raise InstallerError("ops.autostart_failed", EXIT_FAILED, log=tilde(paths.logs / "ops.log", paths))
    _set_flag(paths, True)
    oplog(ctx, "autostart_on")


def disable(ctx) -> None:
    """Unload the LaunchAgent and remove its file when the content is ours."""
    paths = ctx.paths
    _launchctl(ctx, "bootout", f"gui/{os.getuid()}/{LABEL}")
    target = plist_path(paths)
    if target.exists() or target.is_symlink():
        try:
            expected = render(paths, PLIST_TEMPLATE)
        except OSError:
            expected = None
        if expected is not None and _matches(target, expected):
            target.unlink()
        else:
            say("ops.autostart_kept_edited", file=tilde(target, paths))
    _set_flag(paths, False)
    oplog(ctx, "autostart_off")


def shortcuts(ctx, on: bool) -> None:
    """Write (on) or remove (off) the three Desktop files. A file of the same name that this program did not
    write is never replaced, and one the person changed is never removed."""
    paths = ctx.paths
    folder = desktop(paths)
    for name, template in SHORTCUTS:
        dest = folder / name
        text = render(paths, template)
        if on:
            if (dest.exists() or dest.is_symlink()) and (dest.is_symlink() or not _ours(dest)):
                say("ops.shortcut_kept_other", file=tilde(dest, paths))
                continue
            _write(dest, text, 0o755)
        elif _matches(dest, text):
            dest.unlink()
    oplog(ctx, "shortcuts", on=on)


def owned_files(ctx) -> list[Path]:
    """The LaunchAgent and Desktop files whose content equals this installation's template output."""
    paths = ctx.paths
    out = []
    pairs = [(plist_path(paths), PLIST_TEMPLATE)] + [(desktop(paths) / n, tpl) for n, tpl in SHORTCUTS]
    for path, template in pairs:
        try:
            expected = render(paths, template)
        except OSError:
            continue
        if _matches(path, expected):
            out.append(path)
    return out


def remove_all(ctx) -> list[str]:
    """Unload the LaunchAgent and remove it and the Desktop files when their content equals the template output
    (uninstall). Returns the removed paths."""
    paths = ctx.paths
    _launchctl(ctx, "bootout", f"gui/{os.getuid()}/{LABEL}")
    removed = []
    for path in owned_files(ctx):
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            pass
    _set_flag(paths, False)
    return removed


def cmd_autostart(ctx, args) -> int:
    """`thomhouse autostart on|off`: 0 done, 1 failed (the dispatcher prints the error)."""
    if args.state == "on":
        enable(ctx)
        say("ops.autostart_on", tb=tb(ctx.paths))
    else:
        disable(ctx)
        say("ops.autostart_off")
    return EXIT_OK


def cmd_shortcuts(ctx, args) -> int:
    """`thomhouse shortcuts on|off`: 0 done, 1 failed."""
    paths = ctx.paths
    if args.state == "on":
        say("ops.desktop_prompt")
        try:
            shortcuts(ctx, True)
        except OSError as e:
            oplog(ctx, "shortcuts_failed", error=type(e).__name__)
            say("ops.shortcuts_failed", folder=tilde(desktop(paths), paths))
            return EXIT_FAILED
        say("ops.shortcuts_on", folder=tilde(desktop(paths), paths))
    else:
        shortcuts(ctx, False)
        say("ops.shortcuts_off")
    return EXIT_OK
