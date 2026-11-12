"""Local send journal: makes the bridge send an outbox row at most once, even across crashes and lost reports.

One JSON line per change, the last line for an id wins. A "sending" line is fsynced before zalo-agent runs, so a
crash mid-send leaves "sending" behind, which is later reported as "unknown" and never sent again.

Rules applied by the poller when the server hands out a row:
- journal says sent / unknown / sending: do not send; (re)post the stored outcome ("sending" becomes "unknown").
  Exception: the claim item's requeued_at is later than the journal entry, i.e. staff chose "requeue" for a
  failed / unknown row after this bridge recorded it: send again.
- journal says failed: the server chose to retry the row, so send again.
- not in the journal: send.

Stored per id: status, attempt, zalo_msg_id, part_msg_ids, error, reported, at. Never the text or the thread id.

One process per state directory: `run` and `once` hold an exclusive flock on <state_dir>/bridge.lock (see
acquire_state_lock). Two bridges on one journal would each keep their own copy in memory, the second one's start-up
compaction would overwrite the first one's lines, and a row whose lease expired could be sent by both.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

KEEP_MS = 7 * 24 * 3600 * 1000
FINAL = {"sent", "failed", "unknown"}
LOCK_NAME = "bridge.lock"


class StateLocked(Exception):
    """Another bridge process holds the state directory."""


def acquire_state_lock(state_dir: Path) -> int:
    """Takes the exclusive, non-blocking flock on <state_dir>/bridge.lock and returns its fd. The lock lasts until the
    fd is closed or the process exits (also after a crash, so a stale file never blocks a restart)."""
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(d / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        os.close(fd)
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
            raise StateLocked(f"another bridge process is using {d}") from None
        raise
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def now_ms() -> int:
    return int(time.time() * 1000)


class Journal:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)
        self.path = self.dir / "journal.jsonl"
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, Any]] = {}
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass
        self._load()
        self._compact()

    def _load(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue          # a torn last line after a crash
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                self._rows[row["id"]] = row

    def _compact(self) -> None:
        cutoff = now_ms() - KEEP_MS
        keep = {k: v for k, v in self._rows.items()
                if not (v.get("reported") and int(v.get("at") or 0) < cutoff)}
        self._rows = keep
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in keep.values():
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._rows.get(item_id)
            return dict(row) if row else None

    def record(self, item_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            row = dict(self._rows.get(item_id) or {"id": item_id})
            row.update(fields)
            row["at"] = now_ms()
            self._rows[item_id] = row
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return dict(row)

    def unreported(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._rows.values() if not r.get("reported")]
