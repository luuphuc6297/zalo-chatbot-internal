"""state.py: atomic 0600 files, the step and update journals, history, moved-out mark, backups, InstallLock
(16.4.4, 16.8.1, rev F3, F12, F14)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from datetime import datetime

from tests.support import INSTALL_DIR, InstallerTestCase
from thomhouse_installer import proc, state

HOLDER = textwrap.dedent("""
    import os, sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from thomhouse_installer import paths, state
    p = paths.resolve(os.environ, code_root=sys.argv[2])
    with state.InstallLock(p):
        print("LOCKED", os.getpid(), flush=True)
        sys.stdin.readline()
""")

PROBE = textwrap.dedent("""
    import os, sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from thomhouse_installer import paths, state
    p = paths.resolve(os.environ, code_root=sys.argv[2])
    print(state.held_by_us(p), state.lock_holder(p))
""")


def mode_of(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class StateTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.install_release()
        self.p = self.paths()

    def test_atomic_writes_with_mode_0600(self) -> None:
        state.save_installed(self.p, {"schema": 1, "version": "1.4.0"})
        self.assertEqual(state.load_installed(self.p)["version"], "1.4.0")
        self.assertEqual(mode_of(self.p.installed_json), 0o600)
        state.step_set(self.p, "deps", "done")
        self.assertEqual(mode_of(self.p.steps_json), 0o600)
        state.history_append(self.p, {"event": "install", "result": "ok"})
        self.assertEqual(mode_of(self.p.history), 0o600)
        state.set_moved_out(self.p, {"image_name": "x.dmg", "image_sha256": "0" * 64})
        self.assertEqual(mode_of(self.p.moved_out), 0o600)
        leftovers = [f.name for f in self.app_home.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_step_journal(self) -> None:
        self.assertIsNone(state.step_get(self.p, "claude_login"))
        state.step_set(self.p, "claude_login", "pending", "later")
        state.step_set(self.p, "analyze_visits", "pending", "server_404", tries=2)
        entry = state.step_get(self.p, "claude_login")
        self.assertEqual((entry["status"], entry["reason"]), ("pending", "later"))
        self.assertIsNotNone(datetime.fromisoformat(entry["at"]).utcoffset())
        self.assertEqual(state.step_get(self.p, "analyze_visits")["tries"], 2)
        self.assertEqual(set(state.steps_all(self.p)), {"claude_login", "analyze_visits"})
        data = json.loads(self.p.steps_json.read_text(encoding="utf-8"))
        self.assertEqual((data["schema"], data["release"], data["update"]), (1, "1.4.0", None))
        with self.assertRaises(ValueError):
            state.step_set(self.p, "x", "finished")

    def test_update_journal_and_open(self) -> None:
        self.assertIsNone(state.update_get(self.p))
        self.assertIsNone(state.update_open(self.p))
        journal = {"from": "1.4.0", "to": "1.5.0", "file": "/x.command", "from_runtimes": {}, "to_runtimes": {},
                   "backup": None, "phases": {"U1": "done", "U2": "done", "U6": "running"}, "state": "running"}
        state.update_set(self.p, journal)
        self.assertEqual(state.update_get(self.p), journal)
        self.assertIsNone(state.update_open(self.p))  # before U7 nothing live was touched
        journal["phases"]["U7"] = "running"
        state.update_set(self.p, journal)
        self.assertEqual(state.update_open(self.p)["to"], "1.5.0")
        journal["phases"]["U10"] = "rollback"
        state.update_set(self.p, journal)
        self.assertIsNotNone(state.update_open(self.p))
        journal["state"] = "done"
        state.update_set(self.p, journal)
        self.assertIsNone(state.update_open(self.p))
        state.step_set(self.p, "deps", "done")  # the step journal keeps the update journal
        self.assertEqual(state.update_get(self.p)["state"], "done")
        state.update_set(self.p, None)
        self.assertIsNone(state.update_get(self.p))

    def test_history(self) -> None:
        state.history_append(self.p, {"event": "install", "from": None, "to": "1.4.0", "result": "ok"})
        state.history_append(self.p, {"event": "update", "at": "fixed", "result": "failed"})
        lines = [json.loads(x) for x in self.p.history.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["event"] for x in lines], ["install", "update"])
        self.assertIn("at", lines[0])
        self.assertEqual(lines[1]["at"], "fixed")

    def test_moved_out_round_trip(self) -> None:
        self.assertIsNone(state.moved_out(self.p))
        state.set_moved_out(self.p, {"image_name": "thomhouse-chuyen-may-x.dmg", "image_sha256": "a" * 64})
        info = state.moved_out(self.p)
        self.assertEqual((info["schema"], info["image_name"]), (1, "thomhouse-chuyen-may-x.dmg"))
        self.assertIn("at", info)
        self.p.moved_out.write_text("{broken", encoding="utf-8")
        self.assertTrue(state.moved_out(self.p))
        state.clear_moved_out(self.p)
        state.clear_moved_out(self.p)
        self.assertIsNone(state.moved_out(self.p))

    def test_list_backups(self) -> None:
        base = self.bot_home / "backups"
        for name, created, reason in (("20261110-090000-manual", "2026-11-10T09:00:00+07:00", "manual"),
                                      ("20261112-090000-before-migration", "2026-11-12T09:00:00+07:00",
                                       "before-migration")):
            folder = base / name
            folder.mkdir(parents=True)
            (folder / "backup.json").write_text(json.dumps({
                "schema": 1, "id": name, "created_at": created, "reason": reason, "mode": "stopped",
                "app_version": "1.4.0", "device_id": "d" * 32, "migrations_applied": ["0001_init.sql"],
                "files": [{"path": "d1/x.sqlite", "sha256": "0" * 64, "bytes": 100},
                          {"path": "accounts.json", "sha256": "0" * 64, "bytes": 23}]}), encoding="utf-8")
        partial = base / ".partial-20261113-090000-manual"
        partial.mkdir()
        (partial / "backup.json").write_text("{}", encoding="utf-8")
        (base / "no-json").mkdir()
        (base / ".lock").write_text("", encoding="utf-8")
        found = state.list_backups(self.p)
        self.assertEqual([b.id for b in found], ["20261112-090000-before-migration", "20261110-090000-manual"])
        self.assertEqual(found[0].bytes, 123)
        self.assertEqual(found[0].migrations_applied, ["0001_init.sql"])
        self.assertEqual(found[0].path, base / "20261112-090000-before-migration")
        self.assertEqual(state.list_backups(self.paths(self.make_checkout()))[0].reason, "before-migration")

    # ------------------------------------------------------------ InstallLock

    def _holder(self) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, "-I", "-c", HOLDER, str(INSTALL_DIR), str(self.app_home / "app")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=dict(os.environ))
        self.addCleanup(self._release, p)
        line = p.stdout.readline()
        self.assertTrue(line.startswith("LOCKED"), line)
        return p

    def _release(self, p: subprocess.Popen) -> None:
        if p.poll() is None:
            p.stdin.write("\n")
            p.stdin.flush()
            p.wait(timeout=10)
        p.stdin.close()
        p.stdout.close()

    def test_second_process_is_locked_out(self) -> None:
        holder = self._holder()
        self.assertEqual(state.lock_holder(self.p), holder.pid)
        self.assertFalse(state.held_by_us(self.p))
        with self.assertRaises(state.Locked) as cm:
            with state.InstallLock(self.p):
                pass
        self.assertEqual((cm.exception.pid, cm.exception.code, cm.exception.key), (holder.pid, 3, "core.locked"))
        self._release(holder)
        self.assertIsNone(state.lock_holder(self.p))
        with state.InstallLock(self.p):
            self.assertEqual(state.lock_holder(self.p), os.getpid())

    def test_reentrant_in_one_process(self) -> None:
        self.assertIsNone(state.lock_holder(self.p))
        with state.InstallLock(self.p):
            self.assertEqual(os.environ["THOMHOUSE_LOCK_OWNER"], str(os.getpid()))
            self.assertEqual(self.p.lock_file.read_text(encoding="ascii"), f"{os.getpid()}\n")
            with state.InstallLock(self.p):
                self.assertTrue(state.held_by_us(self.p))
            self.assertTrue(state.held_by_us(self.p))
            self.assertEqual(state.lock_holder(self.p), os.getpid())
        self.assertIsNone(state.lock_holder(self.p))
        self.assertNotIn("THOMHOUSE_LOCK_OWNER", os.environ)
        self.assertEqual(self.p.lock_file.read_text(encoding="ascii"), "")
        self.assertEqual(mode_of(self.p.lock_file), 0o600)

    def test_held_by_us_in_child_with_owner_variable(self) -> None:
        with state.InstallLock(self.p):
            env = proc.child_env(self.p)
            self.assertEqual(env["THOMHOUSE_LOCK_OWNER"], str(os.getpid()))
            res = subprocess.run([sys.executable, "-I", "-c", PROBE, str(INSTALL_DIR), str(self.app_home / "app")],
                                 env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(res.stdout.split(), ["True", str(os.getpid())], res.stderr)
            env.pop("THOMHOUSE_LOCK_OWNER")
            res = subprocess.run([sys.executable, "-I", "-c", PROBE, str(INSTALL_DIR), str(self.app_home / "app")],
                                 env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(res.stdout.split(), ["False", str(os.getpid())], res.stderr)

    def test_checkout_lock_lives_in_bot_home(self) -> None:
        p = self.paths(self.make_checkout())
        with state.InstallLock(p):
            self.assertTrue((self.bot_home / ".install.lock").exists())
            self.assertIsNone(state.lock_holder(self.p))  # the device's lock is another file
        self.assertIsNone(state.lock_holder(p))
