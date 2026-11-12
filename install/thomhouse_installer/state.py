"""Install state: `installed.json`, the step and update journal, history, the moved-out mark, the backup listing
and `InstallLock` (16.4.4, 16.8.1, 16.8.2, rev F3, F12, F14).

Every file is written atomically (temporary file in the same folder, then `os.replace`) with mode 0600.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .context import InstallerError
from .paths import Paths

STEP_STATUSES = ("done", "pending", "skipped", "failed", "declined")
LATE_PHASES = ("U7", "U8", "U9", "U10", "U11", "U12", "U13")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _mkdir_private(folder: Path) -> None:
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(folder, 0o700)
        except OSError:
            pass


def _write_json_atomic(path: Path, data: object) -> None:
    """Write `data` as JSON to `path` with mode 0600 through a temporary file and `os.replace`."""
    _mkdir_private(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- installed.json

def load_installed(paths: Paths) -> dict | None:
    """`APP_HOME/installed.json`, or None when missing or unreadable."""
    data = _read_json(paths.installed_json)
    return data if isinstance(data, dict) else None


def save_installed(paths: Paths, data: dict) -> None:
    """Write `installed.json` (0600, atomic)."""
    _write_json_atomic(paths.installed_json, data)


# ---------------------------------------------------------------- install-steps.json

def _release_version(paths: Paths) -> str | None:
    data = _read_json(paths.code_root / "VERSION.json")
    if isinstance(data, dict) and isinstance(data.get("version"), str):
        return data["version"]
    return None


def _journal(paths: Paths) -> dict:
    data = _read_json(paths.steps_json)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", 1)
    data.setdefault("release", _release_version(paths))
    if not isinstance(data.get("steps"), dict):
        data["steps"] = {}
    data.setdefault("update", None)
    return data


def step_get(paths: Paths, step_id: str) -> dict | None:
    """The journal entry of `step_id` (`{"status", "at", "reason", ...}`), or None."""
    entry = _journal(paths)["steps"].get(step_id)
    return dict(entry) if isinstance(entry, dict) else None


def step_set(paths: Paths, step_id: str, status: str, reason: str | None = None, **extra: object) -> None:
    """Record `status` (done, pending, skipped, failed, declined) for `step_id`; ValueError for another status."""
    if status not in STEP_STATUSES:
        raise ValueError(f"unknown step status {status!r}")
    data = _journal(paths)
    entry: dict[str, object] = {"status": status, "at": _now(), "reason": reason}
    entry.update(extra)
    data["steps"][step_id] = entry
    current = _release_version(paths)
    if current:
        data["release"] = current
    _write_json_atomic(paths.steps_json, data)


def steps_all(paths: Paths) -> dict[str, dict]:
    """Every step entry of the journal, keyed by step id ({} when there is no journal)."""
    return {k: dict(v) for k, v in _journal(paths)["steps"].items() if isinstance(v, dict)}


def update_get(paths: Paths) -> dict | None:
    """The update journal (key "update" of install-steps.json, 16.8.1), or None."""
    data = _journal(paths).get("update")
    return dict(data) if isinstance(data, dict) else None


def update_set(paths: Paths, data: dict | None) -> None:
    """Replace the update journal; None writes `null`.

    Shape: {"from", "to", "file", "from_runtimes", "to_runtimes", "backup", "phases": {"U1": "done", ...},
    "state": "running" | "done" | "rolled_back" | "failed"}.
    """
    journal = _journal(paths)
    journal["update"] = data
    _write_json_atomic(paths.steps_json, journal)


def update_open(paths: Paths) -> dict | None:
    """The update journal while its "state" is "running" and phase U7 or a later one has started, else None.

    Before U7 nothing live was touched and the old stack still runs, so refusing commands then would only keep the
    bot down after a reboot; the next `update FILE` starts again at U1 (rev F14, rev check).
    """
    data = update_get(paths)
    if not data or data.get("state") != "running":
        return None
    phases = data.get("phases")
    if not isinstance(phases, dict):
        return None
    if any(p in phases for p in LATE_PHASES):
        return data
    return None


# ---------------------------------------------------------------- history.jsonl

def history_append(paths: Paths, event: dict) -> None:
    """Append one JSON line to `history.jsonl` (0600); "at" is added when missing."""
    record = dict(event)
    record.setdefault("at", _now())
    _mkdir_private(paths.history.parent)
    fd = os.open(paths.history, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- InstallLock

class Locked(InstallerError):
    """Another process holds `InstallLock`; `pid` is its PID (None or 0 when unknown). Exit code 3."""

    code = 3
    key = "core.locked"

    def __init__(self, pid: int | None) -> None:
        super().__init__(None, None)
        self.pid = pid


_HELD: dict[str, list[int]] = {}  # lock file -> [descriptor, depth], this process only


def _read_pid(fd: int) -> int:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        text = os.read(fd, 64).decode("ascii", errors="replace").strip()
        return int(text) if text else 0
    except (OSError, ValueError):
        return 0


class InstallLock:
    """Context manager on `paths.lock_file` with `fcntl.flock(LOCK_EX | LOCK_NB)` (rev F3).

    Re-entrant within one process (a depth counter shared by every instance on the same file). The first entry
    writes "<pid>\\n" into the file and sets `os.environ["THOMHOUSE_LOCK_OWNER"]`, which `proc.child_env` passes
    to children; the last exit empties the file, unlocks and removes the variable. Raises `Locked(pid)`.
    """

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self._key = os.path.abspath(str(paths.lock_file))

    def __enter__(self) -> "InstallLock":
        held = _HELD.get(self._key)
        if held is not None:
            held[1] += 1
            return self
        _mkdir_private(self.paths.lock_file.parent)
        fd = os.open(self._key, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            pid = _read_pid(fd) if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN) else None
            os.close(fd)
            raise Locked(pid) from None
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
        _HELD[self._key] = [fd, 1]
        os.environ["THOMHOUSE_LOCK_OWNER"] = str(os.getpid())
        return self

    def __exit__(self, *exc: object) -> None:
        held = _HELD.get(self._key)
        if held is None:
            return
        held[1] -= 1
        if held[1] > 0:
            return
        fd = held[0]
        del _HELD[self._key]
        try:
            os.ftruncate(fd, 0)
        except OSError:
            pass
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        os.environ.pop("THOMHOUSE_LOCK_OWNER", None)


def lock_holder(paths: Paths) -> int | None:
    """None when `InstallLock` is free; else the holder's PID from the file (0 when unreadable).

    Probed with a non-blocking flock on a new descriptor that is released at once.
    """
    key = os.path.abspath(str(paths.lock_file))
    if key in _HELD:
        return os.getpid()
    try:
        fd = os.open(key, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return _read_pid(fd)
            return None
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


def held_by_us(paths: Paths) -> bool:
    """True when this process holds `InstallLock`, or when its holder is the PID in THOMHOUSE_LOCK_OWNER (a child
    of the command that holds it)."""
    holder = lock_holder(paths)
    if holder is None:
        return False
    if holder == os.getpid():
        return True
    owner = os.environ.get("THOMHOUSE_LOCK_OWNER", "")
    return owner.isdigit() and holder == int(owner) and holder != 0


# ---------------------------------------------------------------- moved-out.json

def moved_out(paths: Paths) -> dict | None:
    """`BOT_HOME/moved-out.json` ({"schema": 1, "at", "image_name", "image_sha256"}), or None when absent.

    A file that exists but cannot be read still counts: it gives {"schema": 1, "unreadable": True}.
    """
    if not paths.moved_out.exists():
        return None
    data = _read_json(paths.moved_out)
    if isinstance(data, dict) and data:
        return data
    return {"schema": 1, "unreadable": True}


def set_moved_out(paths: Paths, info: dict) -> None:
    """Write the moved-out mark (0600, atomic); "schema" and "at" are added when missing."""
    data = {"schema": 1, "at": _now()}
    data.update(info)
    _write_json_atomic(paths.moved_out, data)


def clear_moved_out(paths: Paths) -> None:
    """Remove the moved-out mark (nothing happens when it is absent)."""
    try:
        paths.moved_out.unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- backups

@dataclass
class BackupInfo:
    """One verified-looking backup folder, read from its `backup.json` (no hashing)."""

    id: str
    path: Path
    created_at: str
    reason: str
    mode: str
    app_version: str
    device_id: str | None
    migrations_applied: list[str]
    bytes: int


def list_backups(paths: Paths) -> list[BackupInfo]:
    """Backups under BOT_HOME/backups, newest first: folders with a readable `backup.json`, skipping
    `.partial-` folders and hidden entries. Files are not hashed."""
    out: list[BackupInfo] = []
    try:
        entries = list(paths.backups.iterdir())
    except OSError:
        return out
    for folder in entries:
        if folder.name.startswith(".") or folder.name.startswith(".partial-") or not folder.is_dir():
            continue
        data = _read_json(folder / "backup.json")
        if not isinstance(data, dict):
            continue
        files = data.get("files") if isinstance(data.get("files"), list) else []
        total = 0
        for f in files:
            if isinstance(f, dict) and isinstance(f.get("bytes"), int):
                total += f["bytes"]
        migrations = data.get("migrations_applied")
        out.append(
            BackupInfo(
                id=str(data.get("id") or folder.name),
                path=folder,
                created_at=str(data.get("created_at") or ""),
                reason=str(data.get("reason") or ""),
                mode=str(data.get("mode") or ""),
                app_version=str(data.get("app_version") or ""),
                device_id=data.get("device_id") if isinstance(data.get("device_id"), str) else None,
                migrations_applied=[str(m) for m in migrations] if isinstance(migrations, list) else [],
                bytes=total,
            )
        )
    out.sort(key=lambda b: (b.created_at, b.id), reverse=True)
    return out
