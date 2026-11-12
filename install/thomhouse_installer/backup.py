"""Backup, backup listing and restore of the chatbot data in BOT_HOME (16.8.2 to 16.8.4, rev F3, F12, F13).

A backup is the folder BOT_HOME/backups/<YYYYMMDD-HHMMSS>-<reason>/ (0700, files 0600), written as
`.partial-<id>` and renamed once every file verifies. It holds `d1/**` (every SQLite file copied through the SQLite
backup API and checked with `PRAGMA integrity_check`; `-wal`, `-shm` and `-journal` files skipped), the bridge
journal, the Claude pool files, `profiles/`, `sessions/`, `state/`, `conversations/`, the three env files under
`env/`, and `backup.json` with the SHA-256 of every file.

`backup` never takes `InstallLock`: `make()` takes only BOT_HOME/backups/.lock, so the `start_local.sh` hook can back
up while install, update, restore or move-in hold `InstallLock` (rev F3). The helpers that set the current data
aside and copy backup items in are shared with `move.py`; nothing here deletes customer data except the retention
pass over old backups.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from . import state
from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK, EXIT_REFUSED, EXIT_USAGE, InstallerError
from .text_vi import say, t

LOCK_WAIT_S = 300.0
SQLITE_MAGIC = b"SQLite format 3\x00"
SKIP_SUFFIXES = ("-wal", "-shm", "-journal")
JOURNAL = "bridge/journal.jsonl"
DATA_FILES = (JOURNAL, "accounts.json", "account-state.json")
DATA_DIRS = ("profiles", "sessions", "state", "conversations")
# Every item a backup can replace in BOT_HOME, in the order they are set aside and copied in.
ITEMS = ("d1",) + DATA_FILES + DATA_DIRS
ENV_COPIES = (("server", "env/server.dev.vars"), ("runner", "env/runner.env"), ("bridge", "env/bridge.env"))
KEEP_NEWEST = 5
ROTATED_REASONS = ("manual", "before-migration")
KEEP_UPDATE_DAYS = 30
_REASON = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


class BackupError(InstallerError):
    """A backup could not be made: kind `space`, `verify`, `copy` (code 1), `refused`, `locked` (code 3)."""

    CODES = {"space": 1, "verify": 1, "copy": 1, "refused": 3, "locked": 3}

    def __init__(self, kind: str, **fmt: object) -> None:
        super().__init__(f"ops.backup_{kind}", self.CODES.get(kind, 1), **fmt)
        self.kind = kind


# ---------------------------------------------------------------- small shared helpers

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def tilde(path: Path | str, paths) -> str:
    """`path` with the home folder written as "~" (for screen lines)."""
    text = str(path)
    home = str(paths.home).rstrip("/")
    if home and (text == home or text.startswith(home + "/")):
        return "~" + text[len(home):]
    return text


def tb(paths) -> str:
    """How the person types this program: the launcher of this installation, or the checkout form."""
    if paths.mode != "installed":
        return "python3 -I install/thomhouse.py"
    return tilde(paths.launcher, paths)


def start_cmd(paths) -> str:
    """The command that starts the chatbot: `<launcher> start`, or the start script in checkout mode."""
    return f"{tb(paths)} start" if paths.mode == "installed" else "scripts/start_local.sh"


def mkdir_private(folder: Path) -> None:
    """Create `folder` and its missing parents; every folder created here gets mode 0700."""
    missing = []
    cur = folder
    while not cur.exists() and not cur.is_symlink():
        missing.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    for f in reversed(missing):
        try:
            f.mkdir()
        except FileExistsError:
            pass
        try:
            os.chmod(f, 0o700)
        except OSError:
            pass


def unique_path(base: Path) -> Path:
    """`base`, or `base-2`, `base-3`, ... when it exists."""
    if not base.exists() and not base.is_symlink():
        return base
    n = 2
    while True:
        candidate = base.with_name(f"{base.name}-{n}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        n += 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_private(path: Path, data: object) -> None:
    """JSON to `path` with mode 0600, through a temporary file and `os.replace`."""
    mkdir_private(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copy_private(src: Path, dest: Path) -> None:
    """Copy the bytes of `src` to `dest` (mode 0600) through a temporary file; a symlink at `dest` is replaced."""
    mkdir_private(dest.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_meta(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "backup.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def version_tuple(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        return None
    return tuple(int(x) for x in value.split("."))


def code_version(paths) -> str:
    """The version of the running code: VERSION.json of code_root, or "checkout"."""
    try:
        data = json.loads((paths.code_root / "VERSION.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("version"), str) and data["version"]:
            return data["version"]
    except (OSError, ValueError):
        pass
    return "checkout"


def installed_version(paths) -> str | None:
    """`installed.json` version, else the VERSION.json version in installed mode; None in checkout mode."""
    inst = state.load_installed(paths) or {}
    if isinstance(inst.get("version"), str) and inst["version"]:
        return inst["version"]
    v = code_version(paths)
    return None if v == "checkout" else v


def device_id(paths) -> str | None:
    inst = state.load_installed(paths) or {}
    value = inst.get("device_id")
    return value if isinstance(value, str) and value else None


def newer_than_code(meta: dict, code_root: Path, current_version: str | None) -> bool:
    """True when a backup (or move image) is newer than this code (16.8.3 step 1): it names a migration that
    `code_root/apps/server/migrations` lacks, or its app_version is a higher X.Y.Z than `current_version`. A backup
    made in checkout mode ("checkout") is judged by its migrations alone."""
    folder = code_root / "apps" / "server" / "migrations"
    try:
        known = {p.name for p in folder.glob("*.sql") if p.is_file()}
    except OSError:
        known = set()
    names = meta.get("migrations_applied")
    if isinstance(names, list) and any(str(n) not in known for n in names):
        return True
    theirs = version_tuple(meta.get("app_version"))
    ours = version_tuple(current_version)
    return bool(theirs and ours and theirs > ours)


def oplog(ctx, event: str, *, log: str = "ops.log", **fields: object) -> None:
    """One redacted JSON line in logs/<log>; never prints, never raises (values of secrets never reach it)."""
    from . import proc

    try:
        record: dict[str, object] = {"at": now_iso(), "event": event}
        record.update(fields)
        line = proc.redact(json.dumps(record, ensure_ascii=False, default=str), proc.secret_values(ctx.paths))
        mkdir_private(ctx.paths.logs)
        fd = os.open(ctx.paths.logs / log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 - logging never stops a command
        pass


# ---------------------------------------------------------------- the backups lock

class _BackupsLock:
    """`fcntl.flock` on BOT_HOME/backups/.lock, waiting up to LOCK_WAIT_S seconds, else BackupError("locked")."""

    def __init__(self, paths) -> None:
        self.paths = paths
        self.fd: int | None = None

    def __enter__(self) -> "_BackupsLock":
        mkdir_private(self.paths.backups)
        fd = os.open(self.paths.backups_lock, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    os.close(fd)
                    raise
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise BackupError("locked") from None
                time.sleep(0.2)
        self.fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


# ---------------------------------------------------------------- making a backup

def _is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def _walk_files(root: Path, base: Path) -> list[tuple[Path, str]]:
    """Regular files under `root` (symlinks skipped), as (path, path relative to `base`)."""
    out = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            full = Path(folder) / name
            if full.is_symlink() or not full.is_file():
                continue
            out.append((full, full.relative_to(base).as_posix()))
    return out


def _sources(paths) -> list[tuple[Path, str, str]]:
    """What a backup copies: (source, path inside the backup, "sqlite" | "file")."""
    bot = paths.bot_home
    out: list[tuple[Path, str, str]] = []
    if paths.d1_dir.is_dir() and not paths.d1_dir.is_symlink():
        for full, rel in _walk_files(paths.d1_dir, bot):
            if full.name.endswith(SKIP_SUFFIXES):
                continue
            out.append((full, rel, "sqlite" if _is_sqlite(full) else "file"))
    for rel in DATA_FILES:
        f = bot / rel
        if f.is_file() and not f.is_symlink():
            out.append((f, rel, "file"))
    for name in DATA_DIRS:
        d = bot / name
        if d.is_dir() and not d.is_symlink():
            out.extend((full, rel, "file") for full, rel in _walk_files(d, bot))
    for name, rel in ENV_COPIES:
        f = paths.env_file(name)
        if f.is_file():
            out.append((f, rel, "file"))
    return out


def _source_bytes(src: Path, kind: str) -> int:
    size = src.stat().st_size
    if kind == "sqlite":
        wal = src.with_name(src.name + "-wal")
        if wal.is_file():
            size += wal.stat().st_size
    return size


SQLITE_FULL = 13  # sqlite3.SQLITE_FULL; the constant exists in the module from Python 3.11 on


def _sqlite_copy(src: Path, dest: Path) -> None:
    """Copy one SQLite file with the backup API (read-only source) and check the copy with integrity_check."""
    ok = False
    try:
        source = sqlite3.connect(f"file:{quote(str(src))}?mode=ro", uri=True, timeout=10.0)
        try:
            target = sqlite3.connect(str(dest))
            try:
                source.backup(target)
                row = target.execute("PRAGMA integrity_check").fetchone()
                ok = row is not None and row[0] == "ok"
            finally:
                target.close()
        finally:
            source.close()
    except sqlite3.Error as e:
        if getattr(e, "sqlite_errorcode", None) == SQLITE_FULL or "disk is full" in str(e):
            raise BackupError("space") from None  # the disk filled while copying: free space, not a broken copy
        ok = False
    if not ok:
        raise BackupError("verify")


def _free_bytes(folder: Path) -> int:
    cur = folder
    while not cur.exists() and cur.parent != cur:
        cur = cur.parent
    return shutil.disk_usage(cur).free


def make(ctx, *, mode: str, reason: str) -> state.BackupInfo:
    """Make one verified backup and run the retention pass; return its BackupInfo.

    mode "stopped" refuses with BackupError("refused") while the server runs; "online" copies a running stack.
    Takes BOT_HOME/backups/.lock (waits up to 300 s, else BackupError("locked")) and never InstallLock (rev F3).
    Raises BackupError("space") when the disk lacks twice the size of what is copied, ("verify") when a SQLite
    copy or a file hash does not check out, ("copy") when a file cannot be copied.
    """
    from . import stack

    if mode not in ("stopped", "online"):
        raise ValueError(f"unknown backup mode {mode!r}")
    if not _REASON.match(reason):
        raise ValueError(f"bad backup reason {reason!r}")
    paths = ctx.paths
    if mode == "stopped" and stack.is_running(paths, "server"):
        raise BackupError("refused")
    try:
        lock = _BackupsLock(paths).__enter__()
    except OSError as e:  # BOT_HOME/backups cannot be created or opened
        oplog(ctx, "backup_lock_failed", error=type(e).__name__)
        raise BackupError("copy") from None
    try:
        _remove_partials(ctx)
        info = _make_locked(ctx, mode, reason)
        try:
            _retention(ctx)
        except OSError as e:
            oplog(ctx, "backup_retention_failed", error=type(e).__name__)
    finally:
        lock.__exit__(None, None, None)
    oplog(ctx, "backup_made", id=info.id, mode=mode, reason=reason, bytes=info.bytes)
    return info


def _remove_partials(ctx) -> None:
    """Delete the `.partial-*` folders that an interrupted backup left (a power cut, a kill, a closed window).

    Called under BOT_HOME/backups/.lock, so no other backup is writing one. They are hidden from `backups` and from
    the retention pass, and each holds a copy of d1, profiles, sessions and the env files."""
    paths = ctx.paths
    root = os.path.realpath(paths.backups)
    try:
        entries = sorted(paths.backups.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.name.startswith(".partial-") or entry.is_symlink() or not entry.is_dir():
            continue
        if os.path.dirname(os.path.realpath(entry)) != root:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        oplog(ctx, "backup_partial_removed", id=entry.name[len(".partial-"):])


def _make_locked(ctx, mode: str, reason: str) -> state.BackupInfo:
    from . import migrations

    paths = ctx.paths
    mkdir_private(paths.backups)
    base = stamp() + "-" + reason
    bid = base
    n = 2
    while (paths.backups / bid).exists() or (paths.backups / f".partial-{bid}").exists():
        bid = f"{base}-{n}"
        n += 1
    sources = _sources(paths)
    try:
        need = 2 * sum(_source_bytes(src, kind) for src, _, kind in sources)
    except OSError:
        raise BackupError("copy") from None
    if need > _free_bytes(paths.backups):
        raise BackupError("space")
    partial = paths.backups / f".partial-{bid}"
    mkdir_private(partial)
    try:
        files: list[dict] = []
        checked: list[str] = []
        for src, rel, kind in sources:
            dest = partial / rel
            mkdir_private(dest.parent)
            if kind == "sqlite":
                _sqlite_copy(src, dest)
                os.chmod(dest, 0o600)
                checked.append(rel)
            else:
                copy_private(src, dest)
            files.append({"path": rel, "sha256": sha256_file(dest), "bytes": dest.stat().st_size})
        applied = migrations.applied(paths.bot_home)
        meta = {
            "schema": 1,
            "id": bid,
            "created_at": now_iso(),
            "reason": reason,
            "mode": mode,
            "app_version": code_version(paths),
            "device_id": device_id(paths),
            "bot_home": str(paths.bot_home),
            "migrations_applied": applied if applied is not None else [],
            "files": files,
            "sqlite_checked": checked,
        }
        write_json_private(partial / "backup.json", meta)
        if not verify(partial):
            raise BackupError("verify")
        final = paths.backups / bid
        os.rename(partial, final)
    except BackupError:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(partial, ignore_errors=True)
        oplog(ctx, "backup_failed", error=type(e).__name__)
        if e.errno == errno.ENOSPC:
            raise BackupError("space") from None
        raise BackupError("copy") from None
    return state.BackupInfo(
        id=bid, path=final, created_at=meta["created_at"], reason=reason, mode=mode,
        app_version=meta["app_version"], device_id=meta["device_id"],
        migrations_applied=list(meta["migrations_applied"]), bytes=sum(f["bytes"] for f in files),
    )


def _safe_rel(rel: object) -> bool:
    if not isinstance(rel, str) or not rel or rel.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def verify(backup_dir: Path) -> bool:
    """True when `backup.json` is readable and every file it lists exists with its size and SHA-256."""
    meta = read_meta(Path(backup_dir))
    if meta is None or not isinstance(meta.get("files"), list):
        return False
    for entry in meta["files"]:
        if not isinstance(entry, dict) or not _safe_rel(entry.get("path")):
            return False
        full = Path(backup_dir) / entry["path"]
        try:
            if full.is_symlink() or not full.is_file() or full.stat().st_size != entry.get("bytes"):
                return False
            if sha256_file(full) != entry.get("sha256"):
                return False
        except OSError:
            return False
    return True


def _created(info: state.BackupInfo) -> datetime | None:
    try:
        value = datetime.fromisoformat(info.created_at)
    except ValueError:
        return None
    return value if value.tzinfo else value.astimezone()


def _retention(ctx) -> None:
    """Keep the newest 5 of each of the reasons manual and before-migration; keep before-update-* for 30 days and
    always the newest one; never delete move, before-restore or any other reason."""
    paths = ctx.paths
    now = datetime.now().astimezone()
    counts: dict[str, int] = {}
    newest_update_seen = False
    root = os.path.realpath(paths.backups)
    for info in state.list_backups(paths):  # newest first
        doomed = False
        if info.reason in ROTATED_REASONS:
            counts[info.reason] = counts.get(info.reason, 0) + 1
            doomed = counts[info.reason] > KEEP_NEWEST
        elif info.reason.startswith("before-update-"):
            if not newest_update_seen:
                newest_update_seen = True
            else:
                created = _created(info)
                doomed = created is not None and now - created > timedelta(days=KEEP_UPDATE_DAYS)
        if doomed and not info.path.is_symlink() and os.path.dirname(os.path.realpath(info.path)) == root:
            shutil.rmtree(info.path, ignore_errors=True)
            oplog(ctx, "backup_pruned", id=info.id)


# ---------------------------------------------------------------- set aside, copy in, undo (restore, move-in)

def _item_of(rel: str) -> str | None:
    """The item of ITEMS that the backup path `rel` belongs to, or None (env/, env-settings.json, ...)."""
    if rel in ITEMS:
        return rel
    first = rel.split("/", 1)[0]
    if first in ("d1",) + DATA_DIRS:
        return first
    return None


def set_aside(paths, aside: Path, *, keep_journal: bool) -> list[str]:
    """Rename every current item of ITEMS into `aside` (same disk, nothing deleted); return the items moved. On an
    error the items already moved are moved back and the error is raised."""
    moved: list[str] = []
    try:
        for rel in ITEMS:
            if keep_journal and rel == JOURNAL:
                continue
            src = paths.bot_home / rel
            if not src.exists() and not src.is_symlink():
                continue
            dest = aside / rel
            mkdir_private(dest.parent)
            os.rename(src, dest)
            moved.append(rel)
    except OSError:
        _move_back(paths, aside, moved)
        raise
    return moved


def _move_back(paths, aside: Path, moved: list[str]) -> None:
    for rel in reversed(moved):
        src = aside / rel
        dest = paths.bot_home / rel
        if dest.exists() or dest.is_symlink():
            continue
        mkdir_private(dest.parent)
        os.rename(src, dest)


def copy_items_in(source_dir: Path, paths, meta: dict, *, include_journal: bool,
                  created: list[str] | None = None) -> list[str]:
    """Copy the items of a verified backup (or move image) into BOT_HOME and return the items created. Only files
    listed in its backup.json are copied, never `env/`. Each item is added to `created` before its first file is
    copied, so a caller that passes its own list can undo a copy that failed halfway."""
    created = created if created is not None else []
    for entry in meta.get("files") or []:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not _safe_rel(rel):
            continue
        item = _item_of(rel)
        if item is None or (item == JOURNAL and not include_journal):
            continue
        if item not in created:
            created.append(item)
        dest = paths.bot_home / rel
        mkdir_private(dest.parent)
        copy_private(source_dir / rel, dest)
    if "d1" not in created and (source_dir / "d1").is_dir():
        mkdir_private(paths.d1_dir)
        created.append("d1")
    return created


def copy_d1_back(backup_dir: Path, paths) -> None:
    """Copy the `d1/` files that backup.json lists into BOT_HOME/d1 (which must not exist); used by the update
    rollback of U10 and U11. Raises OSError when a file cannot be copied."""
    meta = read_meta(backup_dir) or {}
    mkdir_private(paths.d1_dir)
    for entry in meta.get("files") or []:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if _safe_rel(rel) and rel.startswith("d1/"):
            dest = paths.bot_home / rel
            mkdir_private(dest.parent)
            copy_private(backup_dir / rel, dest)


def undo_copy(paths, aside: Path, moved: list[str], created: list[str], env_saved: dict[Path, bytes | None]) -> None:
    """Remove what was copied in, move the set-aside items back and put the env files back as they were."""
    for item in created:
        target = paths.bot_home / item
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists() or target.is_symlink():
            try:
                target.unlink()
            except OSError:
                pass
    _move_back(paths, aside, moved)
    for path, content in env_saved.items():
        try:
            if content is None:
                path.unlink()
            else:
                fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
        except OSError:
            pass
    try:
        _remove_empty_dirs(aside)
    except OSError:
        pass


def _remove_empty_dirs(folder: Path) -> None:
    if not folder.is_dir():
        return
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_empty_dirs(child)
    try:
        folder.rmdir()
    except OSError:
        pass


def save_env(paths, names: tuple[str, ...]) -> dict[Path, bytes | None]:
    """The current bytes of the env files `names` (None for a missing file), kept in memory for undo_copy()."""
    out: dict[Path, bytes | None] = {}
    for name in names:
        f = paths.env_file(name)
        try:
            out[f] = f.read_bytes()
        except FileNotFoundError:
            out[f] = None
    return out


def _rehome_accounts(paths, old_home: str) -> None:
    """After a restore into another BOT_HOME: rewrite the config_dir prefix, recreate each `projects` link to
    BOT_HOME/sessions, and disable an account whose config folder does not exist (its login is redone)."""
    try:
        accounts = json.loads(paths.accounts_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(accounts, list):
        return
    old = old_home.rstrip("/")
    sessions = paths.bot_home / "sessions"
    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        cfg = acc.get("config_dir")
        if not isinstance(cfg, str) or not cfg:
            continue
        if cfg == old or cfg.startswith(old + "/"):
            cfg = str(paths.bot_home) + cfg[len(old):]
            acc["config_dir"] = cfg
        folder = Path(cfg)
        if folder.is_dir():
            link = folder / "projects"
            if link.is_symlink():
                link.unlink()
            if not link.exists():
                mkdir_private(sessions)
                link.symlink_to(sessions, target_is_directory=True)
        else:
            acc["enabled"] = False
    write_json_private(paths.accounts_json, accounts)


def restore_into(ctx, source_dir: Path, *, same_device: bool) -> None:
    """Steps 4 to 7 of 16.8.3: set the current items aside into backups/<stamp>-before-restore/, copy the backup in
    (on the same device the current bridge journal is kept and the env files are restored; on another device the
    backup's journal is used and this device's env files stay), and rehome accounts.json when BOT_HOME differs.
    On a failure everything set aside is moved back and the error is raised."""
    _restore_into(ctx, Path(source_dir), same_device=same_device)


def _restore_into(ctx, source_dir: Path, *, same_device: bool, aside: Path | None = None) -> Path:
    paths = ctx.paths
    meta = read_meta(source_dir)
    if meta is None:
        raise BackupError("verify")
    aside = aside or unique_path(paths.backups / f"{stamp()}-before-restore")
    mkdir_private(aside)
    moved = set_aside(paths, aside, keep_journal=same_device)
    created: list[str] = []
    env_saved: dict[Path, bytes | None] = {}
    try:
        copy_items_in(source_dir, paths, meta, include_journal=not same_device, created=created)
        if same_device:
            env_saved = save_env(paths, tuple(name for name, _ in ENV_COPIES))
            for name, rel in ENV_COPIES:
                src = source_dir / rel
                if src.is_file():
                    copy_private(src, paths.env_file(name))
        old_home = meta.get("bot_home")
        if isinstance(old_home, str) and old_home and old_home.rstrip("/") != str(paths.bot_home):
            _rehome_accounts(paths, old_home)
    except BaseException:
        undo_copy(paths, aside, moved, created, env_saved)
        raise
    oplog(ctx, "restore_into", backup=meta.get("id"), same_device=same_device, items=moved)
    return aside


# ---------------------------------------------------------------- commands

def fmt_time(created_at: str) -> str:
    """An ISO time as "HH:MM DD/MM/YYYY" for screen lines."""
    try:
        return datetime.fromisoformat(created_at).strftime("%H:%M %d/%m/%Y")
    except ValueError:
        return created_at or "?"


_fmt_time = fmt_time


def _mb(n: int) -> str:
    return f"{n / 1_000_000:.1f}"


def cmd_backup(ctx, args) -> int:
    """`thomhouse backup [--online | --stopped] [--reason R] [--if-pending-migrations] [--quiet]`: 0 done or not
    needed, 1 failed, 3 refused (the dispatcher prints the error line)."""
    from . import migrations, stack

    paths = ctx.paths
    if getattr(args, "if_pending_migrations", False):
        from .steps import restore_needed

        mark = restore_needed(paths)
        if mark is not None:  # the start_local.sh hook: d1 is not restored, so no migration and no start
            oplog(ctx, "backup_refused_restore_needed", backup=mark.get("backup"))
            given = mark.get("backup_path")
            say("setup.restore_needed", folder=tilde(given, paths) if isinstance(given, str) and given else "?",
                tb=tb(paths))
            return EXIT_FAILED
        pend = migrations.pending(paths.code_root, paths.bot_home)
        if pend is not None and (pend == [] or migrations.find_db(paths.bot_home) is None):
            oplog(ctx, "backup_not_needed", pending=len(pend))
            return EXIT_OK
    mode = getattr(args, "mode", None)
    if mode is None:
        mode = "online" if stack.is_running(paths, "server") else "stopped"
    reason = getattr(args, "reason", None) or "manual"
    info = make(ctx, mode=mode, reason=reason)
    if not ctx.quiet:
        say("ops.backup_done", id=info.id, mb=_mb(info.bytes), folder=tilde(info.path, paths))
    return EXIT_OK


def cmd_backups(ctx, args) -> int:
    """`thomhouse backups`: one line per backup, newest first."""
    paths = ctx.paths
    found = state.list_backups(paths)
    if not found:
        say("ops.backups_none", tb=tb(paths))
        return EXIT_OK
    for info in found:
        status = t("ops.backup_checked") if verify(info.path) else t("ops.backup_broken")
        say("ops.backups_line", id=info.id, time=_fmt_time(info.created_at), reason=info.reason,
            version=info.app_version or "?", mb=_mb(info.bytes), status=status)
    return EXIT_OK


def find_backup(paths, backup_id: str) -> state.BackupInfo | None:
    for info in state.list_backups(paths):
        if info.id == backup_id or info.path.name == backup_id:
            return info
    return None


def same_device(paths, meta: dict) -> bool:
    """The backup was made by this installation: equal device_id, or both without one and the same BOT_HOME."""
    ours = device_id(paths)
    theirs = meta.get("device_id") if isinstance(meta.get("device_id"), str) else None
    if ours or theirs:
        return ours == theirs
    return str(meta.get("bot_home") or "").rstrip("/") == str(paths.bot_home)


def print_failed_checks(results) -> int:
    """Print one line per doctor result whose status is "fail"; return how many."""
    n = 0
    for r in results or []:
        if getattr(r, "status", None) == "fail":
            n += 1
            fix = getattr(r, "fix", None)
            if fix:
                say("ops.check_failed_fix", label=r.label, detail=r.detail, fix=fix)
            else:
                say("ops.check_failed", label=r.label, detail=r.detail)
    return n


def _clear_restore_mark(ctx) -> None:
    """A restore replaced `d1` from a verified backup, so the mark of a failed step 12 copy (steps.restore_needed)
    no longer applies; without this the start_local.sh hook would refuse the start that follows."""
    from .steps import RESTORE_MARK

    mark = ctx.paths.bot_home / RESTORE_MARK
    if mark.exists():
        mark.unlink()
        oplog(ctx, "restore_mark_cleared")


def cmd_restore(ctx, args) -> int:
    """`thomhouse restore ID [--dry-run]` (16.8.3): 0 done, 1 failed, 2 unknown ID, 3 newer backup, 4 declined."""
    from . import consent, stack

    paths = ctx.paths
    info = find_backup(paths, args.id)
    if info is None:
        say("ops.restore_not_found", id=args.id, tb=tb(paths))
        return EXIT_USAGE
    if not verify(info.path):
        say("ops.restore_damaged", id=info.id)
        return EXIT_FAILED
    meta = read_meta(info.path) or {}
    if newer_than_code(meta, paths.code_root, installed_version(paths)):
        say("ops.restore_newer", id=info.id)
        return EXIT_REFUSED
    same = same_device(paths, meta)
    aside = unique_path(paths.backups / f"{stamp()}-before-restore")
    when = _fmt_time(info.created_at)
    if ctx.dry_run:
        say("ops.restore_dry_run", id=info.id, time=when, reason=info.reason, folder=tilde(aside, paths))
        say("ops.restore_dry_env_same" if same else "ops.restore_dry_env_other")
        return EXIT_OK
    if not consent.typed(ctx, "ops.restore_confirm", ("khoi phuc",), time=when, reason=info.reason,
                         folder=tilde(aside, paths)):
        say("ops.restore_declined")
        return EXIT_DECLINED
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(paths))
        stack.start(ctx, quiet=True)
        state.history_append(paths, {"event": "restore", "from": None, "to": None, "result": "failed",
                                     "backup": info.id})
        return EXIT_FAILED
    try:
        _restore_into(ctx, info.path, same_device=same, aside=aside)
        _clear_restore_mark(ctx)
    except (OSError, InstallerError) as e:
        oplog(ctx, "restore_failed", backup=info.id, error=type(e).__name__)
        say("ops.restore_failed", log=tilde(paths.logs / "ops.log", paths))
        stack.start(ctx, quiet=True)
        state.history_append(paths, {"event": "restore", "from": None, "to": None, "result": "failed",
                                     "backup": info.id})
        return EXIT_FAILED
    code = stack.start(ctx)
    failed = 0
    if code != 0:
        say("ops.start_failed", log=tilde(paths.logs / "start.log", paths), tb=tb(paths))
    else:
        from . import doctor

        failed = print_failed_checks(doctor.run_checks(ctx))
    state.history_append(paths, {"event": "restore", "from": None, "to": None,
                                 "result": "ok" if code == 0 else "failed", "backup": info.id})
    say("ops.restore_done", id=info.id, folder=tilde(aside, paths))
    say("ops.restore_queue_note")
    return EXIT_OK if code == 0 and failed == 0 else EXIT_FAILED
