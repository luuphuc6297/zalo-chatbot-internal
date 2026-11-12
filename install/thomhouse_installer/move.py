"""Moving the chatbot data to another Mac: `move-out`, `move-in`, `move-back` and `place_moved_data` (16.8.5,
rev F12, F16, F18, rev check).

`move-out` stops this Mac, frees the Zalo session, makes a stopped backup, builds a staging copy of it without
`env/` but with `env-settings.json` (only the non-secret settings of MOVE_KEYS; THOMHOUSE_DRAFT_ENGINE never
travels), packs it with `hdiutil create -encryption AES-256` (hdiutil asks the passphrase itself) and writes
BOT_HOME/moved-out.json, so neither the installer nor a hand-run `start_local.sh` starts this Mac again. It works in
checkout mode too, which is how the build Mac's data reaches its first device.

`place_moved_data` (move-in and install step 10) mounts the image read-only, verifies it, refuses an image newer
than this code, sets the current data aside into backups/<stamp>-before-move-in/, copies the image in (its bridge
journal included), merges the settings with the bridge's own `EnvFile` (secrets stay this device's own), and gives
every Claude account its own config folder under BOT_HOME/accounts, disabled until its login is redone. `move-in`
prints the `continue` line instead of running the human steps (WP5 never calls WP3).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import backup, state
from .backup import (mkdir_private, oplog, sha256_file, stamp, start_cmd, tb, tilde, unique_path,
                     write_json_private)
from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK, EXIT_REFUSED, EXIT_USAGE, InstallerError
from .text_vi import say

MOVE_KEYS = (
    "ROOM_TURN_TIMEOUT_S", "ROOM_OBSERVE_EVERY_S", "ROOM_FALLBACK", "ROOM_REQUIRE_PROFILE_READ",
    "ROOM_CUSTOMER_MODEL", "ZALO_PERSONAL_IGNORE_THREADS", "ZALO_ACCOUNT", "SEND_MIN_INTERVAL_S",
    "LABEL_SYNC_EVERY_S", "THOMHOUSE_CLAUDE_MODEL", "THOMHOUSE_CLAUDE_EFFORT",
)
SETTINGS_FILES = ("server", "runner", "bridge")
SETTINGS_NAME = "env-settings.json"
VOLNAME = "thomhouse-chuyen-may"
_LABEL = re.compile(r"^[A-Za-z0-9._-]+$")

# Runs in <app>/apps/zalo-bridge with the bridge's own EnvFile, so the env files keep their format and mode 0600.
_MERGE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from bridge.envfiles import EnvFile\n"
    "for path, values in json.load(sys.stdin).items():\n"
    "    f = EnvFile(Path(path))\n"
    "    for key, value in values.items():\n"
    "        f.set(key, value)\n"
    "    f.save()\n"
)


# ---------------------------------------------------------------- move-out

def _env_settings(paths) -> dict[str, dict[str, str]]:
    """The values of MOVE_KEYS that the server, runner and bridge env files set, per file."""
    from . import envs

    out: dict[str, dict[str, str]] = {}
    for name in SETTINGS_FILES:
        data = envs.read(paths.env_file(name))
        kept = {k: data[k] for k in MOVE_KEYS if k in data}
        if kept:
            out[name] = kept
    return out


def _build_staging(ctx, backup_dir: Path, staging: Path) -> None:
    """A copy of the backup without env/, plus env-settings.json, with backup.json listing exactly those files."""
    meta = backup.read_meta(backup_dir) or {}
    mkdir_private(staging)
    files = []
    for entry in meta.get("files") or []:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or rel.startswith("env/"):
            continue
        backup.copy_private(backup_dir / rel, staging / rel)
        files.append(entry)
    settings = staging / SETTINGS_NAME
    write_json_private(settings, {"schema": 1, "files": _env_settings(ctx.paths)})
    files.append({"path": SETTINGS_NAME, "sha256": sha256_file(settings), "bytes": settings.stat().st_size})
    meta["files"] = files
    write_json_private(staging / "backup.json", meta)


def _image_path(folder: Path) -> Path:
    base = f"thomhouse-chuyen-may-{datetime.now().strftime('%Y%m%d-%H%M')}"
    candidate = folder / f"{base}.dmg"
    n = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = folder / f"{base}-{n}.dmg"
        n += 1
    return candidate


def cmd_move_out(ctx, args) -> int:
    """`thomhouse move-out --to DIR` (installed or checkout mode): 0 moved out, 1 failed, 2 no such folder,
    4 declined."""
    from . import bridgecli, consent, proc, stack

    paths = ctx.paths
    folder = Path(args.to)
    if not folder.is_dir():
        say("ops.move_out_no_dir", folder=tilde(folder, paths))
        return EXIT_USAGE
    if consent.ask(ctx, "ops.move_out_confirm", "ck") != "c":
        say("ops.move_out_declined")
        return EXIT_DECLINED
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        return EXIT_FAILED
    code, _ = bridgecli.listener(ctx, "stop")
    if code != 0:
        say("ops.move_out_listener_warn", tb=tb(paths))
    if paths.mode == "installed":
        from . import autostart

        try:
            autostart.disable(ctx)
        except (InstallerError, OSError) as e:
            oplog(ctx, "move_out_autostart_failed", error=type(e).__name__)
    try:
        info = backup.make(ctx, mode="stopped", reason="move")
    except InstallerError as e:
        try:
            say(e.key, **{"tb": tb(paths), **e.fmt})
        except (KeyError, IndexError, ValueError):
            pass
        say("ops.move_out_not_moved", start=start_cmd(paths))
        return e.code
    staging = unique_path(paths.backups / f".staging-move-{stamp()}")
    image = _image_path(folder)
    try:
        _build_staging(ctx, info.path, staging)
        say("ops.hdiutil_create")
        res = proc.run(ctx, ["hdiutil", "create", "-encryption", "AES-256", "-srcfolder", str(staging),
                             "-volname", VOLNAME, "-format", "UDZO", str(image)], interactive=True)
        returncode = res.returncode
    except OSError as e:
        oplog(ctx, "move_out_staging_failed", error=type(e).__name__)
        returncode = 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if returncode != 0 or not image.is_file():
        oplog(ctx, "move_out_image_failed", exit=returncode)
        say("ops.move_out_image_failed", start=start_cmd(paths))
        return EXIT_FAILED
    try:
        image.chmod(0o600)
    except OSError:
        pass
    digest = sha256_file(image)
    state.set_moved_out(paths, {"image_name": image.name, "image_sha256": digest})
    state.history_append(paths, {"event": "move_out", "from": backup.code_version(paths), "to": None,
                                 "result": "ok", "backup": info.id})
    oplog(ctx, "move_out", image=image.name, backup=info.id)
    say("ops.move_out_done", file=tilde(image, paths))
    say("ops.move_out_last")
    return EXIT_OK


# ---------------------------------------------------------------- move-in

def _merge_settings(ctx, settings_file: Path) -> None:
    """Write the settings of the image into this device's env files with the bridge's EnvFile."""
    from . import proc

    paths = ctx.paths
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return
    payload: dict[str, dict[str, str]] = {}
    for name in SETTINGS_FILES:
        values = files.get(name)
        if not isinstance(values, dict):
            continue
        clean = {}
        for key, value in values.items():
            text = str(value)
            if key in MOVE_KEYS and isinstance(value, (str, int, float)) and "\n" not in text and "\r" not in text:
                clean[key] = text
        if clean:
            payload[str(paths.env_file(name))] = clean
    if not payload:
        return
    res = proc.run(ctx, [sys.executable, "-c", _MERGE], cwd=paths.app / "apps" / "zalo-bridge",
                   stdin=json.dumps(payload), capture=True, timeout=60)
    if res.returncode != 0:
        raise InstallerError("ops.move_in_failed", EXIT_FAILED)


def _rewrite_accounts(paths) -> None:
    """Every account gets BOT_HOME/accounts/<label> (with its `projects` link to sessions/) and enabled false,
    including one whose config_dir was null (the build Mac's `default`), so no account uses this Mac's own
    ~/.claude login before it is logged in again (rev F12)."""
    try:
        accounts = json.loads(paths.accounts_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    if not isinstance(accounts, list):
        raise ValueError("accounts.json is not a list")
    sessions = paths.bot_home / "sessions"
    mkdir_private(sessions)
    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        label = acc.get("label")
        if not isinstance(label, str) or not _LABEL.match(label) or label in (".", ".."):
            raise ValueError("bad account label")
        cfg = paths.bot_home / "accounts" / label
        mkdir_private(cfg)
        link = cfg / "projects"
        if link.is_symlink():
            link.unlink()
        if not link.exists():
            link.symlink_to(sessions, target_is_directory=True)
        acc["config_dir"] = str(cfg)
        acc["enabled"] = False
    write_json_private(paths.accounts_json, accounts)


def _place_from(ctx, mount: Path) -> int:
    paths = ctx.paths
    if not backup.verify(mount):
        say("ops.move_in_damaged")
        return EXIT_FAILED
    meta = backup.read_meta(mount) or {}
    if backup.newer_than_code(meta, paths.code_root, backup.installed_version(paths)):
        say("ops.move_in_newer")
        return EXIT_REFUSED
    aside = unique_path(paths.backups / f"{stamp()}-before-move-in")
    mkdir_private(aside)
    moved = backup.set_aside(paths, aside, keep_journal=False)
    created: list[str] = []
    env_saved: dict = {}
    try:
        backup.copy_items_in(mount, paths, meta, include_journal=True, created=created)
        env_saved = backup.save_env(paths, SETTINGS_FILES)
        _merge_settings(ctx, mount / SETTINGS_NAME)
        _rewrite_accounts(paths)
        if "account-state.json" not in created:
            created.append("account-state.json")
        write_json_private(paths.account_state_json, {})
    except (OSError, ValueError, InstallerError) as e:
        oplog(ctx, "move_in_failed", error=type(e).__name__)
        backup.undo_copy(paths, aside, moved, created, env_saved)
        say("ops.move_in_failed", log=tilde(paths.logs / "ops.log", paths))
        return EXIT_FAILED
    oplog(ctx, "move_in", backup=meta.get("id"), items=moved)
    say("ops.move_in_placed", folder=tilde(aside, paths))
    return EXIT_OK


def place_moved_data(ctx, image: Path) -> int:
    """Put the data of a move image in place (16.8.5): 0 done; 1 failed (the data set aside was moved back);
    3 the image is newer than this code; 4 the image was not opened (no passphrase given). Does not stop or start
    the stack."""
    from . import proc

    paths = ctx.paths
    image = Path(image)
    if not image.is_file():
        say("ops.move_in_no_file", file=tilde(image, paths))
        return EXIT_FAILED
    mount = unique_path(paths.backups / f".mount-{stamp()}")
    mkdir_private(mount)
    say("ops.hdiutil_attach")
    res = proc.run(ctx, ["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(image)],
                   interactive=True)
    if res.returncode != 0:
        _rmdir_quiet(mount)
        oplog(ctx, "move_in_attach_failed", exit=res.returncode)
        say("ops.move_in_attach_failed")
        return EXIT_DECLINED
    try:
        code = _place_from(ctx, mount)
    finally:
        proc.run(ctx, ["hdiutil", "detach", str(mount)], capture=True, timeout=120)
        _rmdir_quiet(mount)
    state.history_append(paths, {"event": "move_in", "from": None, "to": backup.code_version(paths),
                                 "result": "ok" if code == EXIT_OK else "failed", "backup": None})
    return code


def _rmdir_quiet(folder: Path) -> None:
    try:
        folder.rmdir()
    except OSError:
        pass


def cmd_move_in(ctx, args) -> int:
    """`thomhouse move-in FILE`: stop, place the data, start, then the line that names `continue`."""
    from . import stack

    paths = ctx.paths
    was_running = any(s.alive for s in stack.services(paths))
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        return EXIT_FAILED
    code = place_moved_data(ctx, Path(args.file))
    if code != EXIT_OK:
        if was_running:
            stack.start(ctx, quiet=True)
        return code
    started = stack.start(ctx)
    if started != 0:
        say("ops.start_failed", log=tilde(paths.logs / "start.log", paths), tb=tb(paths))
    say("ops.move_in_done", tb=tb(paths))
    return EXIT_OK if started == 0 else EXIT_FAILED


# ---------------------------------------------------------------- move-back

def cmd_move_back(ctx, args) -> int:
    """`thomhouse move-back` (installed or checkout mode): remove the moved-out mark after `c`."""
    from . import consent

    paths = ctx.paths
    if state.moved_out(paths) is None:
        say("ops.move_back_not_needed")
        return EXIT_OK
    if consent.ask(ctx, "ops.move_back_confirm", "ck") != "c":
        say("ops.move_back_declined")
        return EXIT_DECLINED
    state.clear_moved_out(paths)
    state.history_append(paths, {"event": "move_back", "from": None, "to": None, "result": "ok", "backup": None})
    oplog(ctx, "move_back")
    say("ops.move_back_done", start=start_cmd(paths))
    return EXIT_OK
