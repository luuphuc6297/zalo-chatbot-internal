"""backup.py: what a backup holds and leaves out, modes, hashes, the pending-migration shortcut, the stopped-mode
refusal, the backups lock that is independent of InstallLock, retention and the listing (16.8.2, rev F3, F13)."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase
from tests.support import INSTALL_DIR
from thomhouse_installer import backup, state
from thomhouse_installer.text_vi import t

HOLD = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
open(sys.argv[2], "w").close()
time.sleep(float(sys.argv[3]))
"""

HOLD_INSTALL_LOCK = """
import os, sys, time
sys.path.insert(0, sys.argv[1])
from thomhouse_installer import paths, state
with state.InstallLock(paths.resolve(os.environ, code_root=__import__("pathlib").Path(sys.argv[2]))):
    open(sys.argv[3], "w").close()
    time.sleep(float(sys.argv[4]))
"""


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


class BackupTest(OpsTestCase):
    def data(self) -> None:
        """BOT_HOME items that a backup copies, and items it must leave out."""
        b = self.bot_home
        for rel, text in {
            "bridge/journal.jsonl": '{"k": 1}\n', "accounts.json": "[]", "account-state.json": "{}",
            "profiles/c1.json": "{}", "sessions/s/1.jsonl": "x", "state/s.json": "{}", "conversations/c.json": "{}",
            "run/server.pid": "1", "logs/server.log": "log", "menu-images/a.jpg": "j", "prompt/p.txt": "p",
            "probe/x": "x", "accounts/main/.credentials": "secret", "rooms/r.json": "{}",
            "openmausbot/pairing.txt": "code", "d1.failed-20260101-000000/x.sqlite": "x", "moved-out.json": "{}",
            "d1/v3/d1/miniflare-D1DatabaseObject/notes.txt": "plain",
            "d1/v3/d1/miniflare-D1DatabaseObject/x.sqlite-wal": "wal", "d1/v3/d1/x.sqlite-shm": "shm",
        }.items():
            (b / rel).parent.mkdir(parents=True, exist_ok=True)
            (b / rel).write_text(text, encoding="utf-8")

    def test_wal_database_round_trip_with_integrity_check(self) -> None:
        self.installed(start=False)
        db = next((self.bot_home / "d1").rglob("miniflare-D1DatabaseObject/*.sqlite"))
        if db.name == "metadata.sqlite":
            db = [p for p in db.parent.glob("*.sqlite") if p.name != "metadata.sqlite"][0]
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL)")
        con.executemany("INSERT INTO conversations VALUES (?, ?)", [(f"c{i}", i) for i in range(50)])
        con.commit()  # the rows sit in the -wal file while this connection stays open
        self.assertTrue(Path(str(db) + "-wal").exists())
        before = self.dumps()
        info = backup.make(self.ctx(), mode="stopped", reason="manual")
        con.close()
        self.assertFalse([p for p in info.path.rglob("*") if p.name.endswith(("-wal", "-shm"))])
        meta = json.loads((info.path / "backup.json").read_text(encoding="utf-8"))
        rel = str(db.relative_to(self.bot_home))
        self.assertIn(rel, meta["sqlite_checked"])
        copy = sqlite3.connect(info.path / rel)
        self.assertEqual(copy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(copy.execute("SELECT count(*) FROM conversations").fetchone()[0], 50)
        copy.close()
        self.assertEqual(self.dumps(info.path / "d1"), before)

    def test_items_modes_and_hashes(self) -> None:
        self.installed(start=False)  # no start, so the env files are written by hand here
        for rel, text in (("apps/server/.dev.vars", "STAFF_TOKEN=staff-0123456789abcdef0123\n"),
                          ("apps/runner/.env", "RUNNER_ID=mac-local-1\n"), ("apps/zalo-bridge/.env", "BRIDGE_ID=b\n")):
            (self.app_home / "app" / rel).write_text(text, encoding="utf-8")
        self.data()
        info = backup.make(self.ctx(), mode="stopped", reason="manual")
        names = {p.relative_to(info.path).as_posix() for p in info.path.rglob("*") if p.is_file()}
        for rel in ("bridge/journal.jsonl", "accounts.json", "account-state.json", "profiles/c1.json",
                    "sessions/s/1.jsonl", "state/s.json", "conversations/c.json", "env/server.dev.vars",
                    "env/runner.env", "env/bridge.env", "backup.json",
                    "d1/v3/d1/miniflare-D1DatabaseObject/notes.txt"):
            self.assertIn(rel, names)
        for rel in names:
            self.assertFalse(rel.startswith(("run/", "logs/", "menu-images/", "prompt/", "probe/", "accounts/",
                                             "rooms/", "openmausbot/", "d1.failed-", "backups/")), rel)
            self.assertNotEqual(rel, "moved-out.json")
            self.assertFalse(rel.endswith(("-wal", "-shm", "-journal")), rel)
        self.assertEqual(_mode(info.path), 0o700)
        self.assertEqual(_mode(self.bot_home / "backups"), 0o700)
        for p in info.path.rglob("*"):
            self.assertEqual(_mode(p), 0o700 if p.is_dir() else 0o600, p)
        meta = json.loads((info.path / "backup.json").read_text(encoding="utf-8"))
        for key in ("schema", "id", "created_at", "reason", "mode", "app_version", "device_id", "bot_home",
                    "migrations_applied", "files", "sqlite_checked"):
            self.assertIn(key, meta)
        self.assertEqual((meta["app_version"], meta["device_id"], meta["mode"]), ("1.4.0", "d" * 32, "stopped"))
        self.assertEqual(meta["migrations_applied"], ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])
        self.assertTrue(backup.verify(info.path))
        self.assertEqual(info.bytes, sum(f["bytes"] for f in meta["files"]))
        (info.path / "profiles" / "c1.json").write_text('{"changed": true}', encoding="utf-8")
        self.assertFalse(backup.verify(info.path))
        self.assertEqual(list(self.bot_home.joinpath("backups").glob(".partial-*")), [])

    def test_if_pending_migrations(self) -> None:
        root = self.install_release()
        res = self.run_cli(None, "backup", "--stopped", "--reason", "before-migration", "--if-pending-migrations",
                           "--quiet")
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)  # no database yet
        self.seed_d1(root)
        res = self.run_cli(None, "backup", "--if-pending-migrations", "--quiet")
        self.assertEqual(res.returncode, 0, res.stdout)  # nothing pending
        self.assertEqual(state.list_backups(self.paths()), [])
        self.add_migration(root, "0004_new.sql")
        res = self.run_cli(None, "backup", "--stopped", "--reason", "before-migration", "--if-pending-migrations",
                           "--quiet")
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)
        found = state.list_backups(self.paths())
        self.assertEqual([b.reason for b in found], ["before-migration"])

    def test_stopped_refuses_while_server_runs_and_online_copies(self) -> None:
        self.installed()
        res = self.run_cli(None, "backup", "--stopped")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn(t("ops.backup_refused", tb="~/ThomHouse/bin/thomhouse"), res.stdout)
        res = self.run_cli(None, "backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([b.mode for b in state.list_backups(self.paths())], ["online"])
        self.assertIn("server", self.alive_services())

    def test_backup_ignores_install_lock(self) -> None:
        self.installed(start=False)
        ready = self.tmp / "locked"
        holder = subprocess.Popen([sys.executable, "-c", HOLD_INSTALL_LOCK, str(INSTALL_DIR),
                                   str(self.app_home / "app"), str(ready), "30"], env=dict(self.env))
        self.addCleanup(holder.kill)
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.05)
        self.assertEqual(state.lock_holder(self.paths()), holder.pid)
        res = self.run_cli(None, "backup", "--quiet")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(len(state.list_backups(self.paths())), 1)
        holder.kill()
        holder.wait()

    def test_two_backups_never_overlap(self) -> None:
        self.installed(start=False)
        (self.bot_home / "backups").mkdir(mode=0o700, exist_ok=True)
        ready = self.tmp / "held"
        holder = subprocess.Popen([sys.executable, "-c", HOLD, str(self.bot_home / "backups" / ".lock"), str(ready),
                                   "1.5"])
        self.addCleanup(holder.kill)
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.05)
        started = time.monotonic()
        res = self.run_cli(None, "backup", "--quiet")
        waited = time.monotonic() - started
        holder.wait()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertGreaterEqual(waited, 1.0)
        # Within one process: a lock held longer than the wait gives the "locked" error, code 3.
        holder = subprocess.Popen([sys.executable, "-c", HOLD, str(self.bot_home / "backups" / ".lock"),
                                   str(self.tmp / "held2"), "5"])
        self.addCleanup(holder.kill)
        for _ in range(100):
            if (self.tmp / "held2").exists():
                break
            time.sleep(0.05)
        with mock.patch.object(backup, "LOCK_WAIT_S", 0.3):
            with self.assertRaises(backup.BackupError) as caught:
                backup.make(self.ctx(), mode="stopped", reason="manual")
        self.assertEqual((caught.exception.code, caught.exception.key), (3, "ops.backup_locked"))
        holder.kill()

    def _fake_backup(self, name: str, reason: str, when: datetime) -> Path:
        folder = self.bot_home / "backups" / name
        folder.mkdir(parents=True)
        (folder / "backup.json").write_text(json.dumps({
            "schema": 1, "id": name, "created_at": when.isoformat(timespec="seconds"), "reason": reason,
            "mode": "stopped", "app_version": "1.4.0", "device_id": None, "bot_home": str(self.bot_home),
            "migrations_applied": [], "files": [], "sqlite_checked": []}), encoding="utf-8")
        return folder

    def test_retention(self) -> None:
        self.installed(start=False)
        now = datetime.now().astimezone()
        made = {}
        for i in range(7):
            made[f"manual-{i}"] = self._fake_backup(f"m{i}", "manual", now - timedelta(days=i + 1))
        for i in range(6):
            made[f"mig-{i}"] = self._fake_backup(f"g{i}", "before-migration", now - timedelta(days=i + 1))
        made["upd-new"] = self._fake_backup("u0", "before-update-1.5.0", now - timedelta(days=60))
        made["upd-old"] = self._fake_backup("u1", "before-update-1.4.0", now - timedelta(days=90))
        made["upd-recent"] = self._fake_backup("u2", "before-update-1.4.1", now - timedelta(days=70))
        made["move"] = self._fake_backup("mv", "move", now - timedelta(days=400))
        made["restore"] = self._fake_backup("rs", "before-restore", now - timedelta(days=400))
        backup.make(self.ctx(), mode="stopped", reason="manual")
        kept = {k for k, p in made.items() if p.exists()}
        # manual: the new one plus the newest 4 old ones; before-migration: newest 5; before-update: newest only.
        self.assertEqual({k for k in kept if k.startswith("manual")}, {f"manual-{i}" for i in range(4)})
        self.assertEqual({k for k in kept if k.startswith("mig")}, {f"mig-{i}" for i in range(5)})
        self.assertEqual({k for k in kept if k.startswith("upd")}, {"upd-new"})
        self.assertIn("move", kept)
        self.assertIn("restore", kept)

    def test_not_enough_space(self) -> None:
        self.installed(start=False)
        usage = mock.Mock(free=10)
        with mock.patch.object(backup.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(backup.BackupError) as caught:
                backup.make(self.ctx(), mode="stopped", reason="manual")
        self.assertEqual((caught.exception.code, caught.exception.key), (1, "ops.backup_space"))
        self.assertEqual([p.name for p in (self.bot_home / "backups").iterdir()], [".lock"])

    def test_backups_listing(self) -> None:
        self.installed(start=False)
        res = self.run_cli(None, "backups")
        self.assertEqual(res.stdout.strip(), t("ops.backups_none", tb="~/ThomHouse/bin/thomhouse"))
        info = backup.make(self.ctx(), mode="stopped", reason="manual")
        res = self.run_cli(None, "backups")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(info.id, res.stdout)
        self.assertIn("bản 1.4.0", res.stdout)
        self.assertIn(t("ops.backup_checked"), res.stdout)
        meta = json.loads((info.path / "backup.json").read_text(encoding="utf-8"))
        victim = info.path / meta["files"][0]["path"]
        os.chmod(victim, 0o600)
        victim.write_bytes(b"changed")
        res = self.run_cli(None, "backups")
        self.assertIn(t("ops.backup_broken"), res.stdout)

    def test_checkout_mode_backup(self) -> None:
        checkout = self.make_checkout()
        self.seed_d1(checkout)
        (checkout / "apps" / "runner").mkdir(parents=True, exist_ok=True)
        (checkout / "apps" / "runner" / ".env").write_text("RUNNER_ID=mac-local-1\n", encoding="utf-8")
        res = self.run_cli(checkout, "backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(self.app_home.exists())  # checkout mode never creates ~/ThomHouse
        found = state.list_backups(self.paths(checkout))
        self.assertEqual([(b.app_version, b.device_id) for b in found], [("checkout", None)])
        self.assertTrue((found[0].path / "env" / "runner.env").is_file())
