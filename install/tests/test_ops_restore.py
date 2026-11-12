"""backup.cmd_restore and restore_into: the current data is set aside, never deleted; the journal is kept on the same
device; env files are restored only for the same device_id; accounts.json is rehomed; the typed word is required;
a failure halfway moves the data back; the restart runs the real hook under the restore's lock (16.8.3, rev F3)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase
from thomhouse_installer import backup, migrations, state
from thomhouse_installer.text_vi import t


def _args(backup_id: str, dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="restore", id=backup_id, yes=False, dry_run=dry_run, quiet=False,
                              offline=False, json=False)


class RestoreTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.use_stubs("doctor")
        self.root = self.installed()  # running stack, env files from init-env, D1 with 0001-0003
        b = self.bot_home
        (b / "bridge").mkdir(parents=True, exist_ok=True)
        (b / "bridge" / "journal.jsonl").write_text('{"sent": "old"}\n', encoding="utf-8")
        (b / "profiles").mkdir(exist_ok=True)
        (b / "profiles" / "p1.json").write_text('{"v": 1}', encoding="utf-8")
        (b / "accounts.json").write_text(json.dumps([
            {"label": "main", "config_dir": str(b / "accounts" / "main"), "priority": 1, "enabled": True}]),
            encoding="utf-8")
        (b / "accounts" / "main").mkdir(parents=True)
        self.server_vars = self.app_home / "app" / "apps" / "server" / ".dev.vars"
        self.saved_vars = self.server_vars.read_text(encoding="utf-8")
        self.info = backup.make(self.ctx(), mode="online", reason="manual")
        self.before = self.dumps()
        # Changes made after the backup.
        db = migrations.find_db(b)
        con = sqlite3.connect(db)
        con.execute("INSERT INTO conversations VALUES ('late', 1)")
        con.commit()
        con.close()
        self.after = self.dumps()
        (b / "bridge" / "journal.jsonl").write_text('{"sent": "old"}\n{"sent": "new"}\n', encoding="utf-8")
        (b / "profiles" / "p2.json").write_text('{"v": 2}', encoding="utf-8")
        self.server_vars.write_text(self.saved_vars.replace("STAFF_TOKEN=", "STAFF_TOKEN=changed-"),
                                    encoding="utf-8")

    def restore(self, typed: str = "khoi phuc\n", dry_run: bool = False) -> int:
        self.answer(typed)
        ctx = self.ctx(interactive=True, dry_run=dry_run)
        return self.quiet(backup.cmd_restore, ctx, _args(self.info.id, dry_run))

    def aside(self) -> Path:
        found = [p for p in (self.bot_home / "backups").iterdir() if p.name.endswith("-before-restore")]
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_same_device_restore(self) -> None:
        code = self.restore()
        self.assertEqual(code, 0, self.out)
        self.assertEqual(self.dumps(), self.before)
        aside = self.aside()
        # The current data was set aside, not deleted.
        self.assertEqual(self.dumps(aside / "d1"), self.after)
        self.assertTrue((aside / "profiles" / "p2.json").exists())
        self.assertFalse((self.bot_home / "profiles" / "p2.json").exists())
        # Same device: the journal of what was really sent stays; the env files come back.
        self.assertIn('"new"', (self.bot_home / "bridge" / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertFalse((aside / "bridge" / "journal.jsonl").exists())
        self.assertEqual(self.server_vars.read_text(encoding="utf-8"), self.saved_vars)
        self.assertIn(t("ops.restore_queue_note"), self.out)
        self.assertEqual(self.history()[-1]["event"], "restore")
        self.assertEqual(len(self.stop_calls()), 1)
        self.assertEqual(self.stub_calls("doctor.run_checks")[-1]["only"], None)
        self.assertIn("server", self.alive_services())

    def test_other_device_restore(self) -> None:
        meta = json.loads((self.info.path / "backup.json").read_text(encoding="utf-8"))
        meta["device_id"] = "e" * 32
        meta["bot_home"] = "/Users/old/.thomhouse-bot"
        accounts = [{"label": "main", "config_dir": "/Users/old/.thomhouse-bot/accounts/main", "priority": 1,
                     "enabled": True},
                    {"label": "gone", "config_dir": "/Users/old/.thomhouse-bot/accounts/gone", "priority": 2,
                     "enabled": True}]
        acc_file = self.info.path / "accounts.json"
        acc_file.write_text(json.dumps(accounts), encoding="utf-8")
        for f in meta["files"]:
            if f["path"] == "accounts.json":
                f["sha256"] = backup.sha256_file(acc_file)
                f["bytes"] = acc_file.stat().st_size
        (self.info.path / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
        changed_vars = self.server_vars.read_text(encoding="utf-8")
        code = self.restore()
        self.assertEqual(code, 0, self.out)
        # Another device: the backup's journal is used; this device's env files stay.
        self.assertNotIn('"new"', (self.bot_home / "bridge" / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertTrue((self.aside() / "bridge" / "journal.jsonl").exists())
        self.assertEqual(self.server_vars.read_text(encoding="utf-8"), changed_vars)
        rehomed = json.loads((self.bot_home / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(rehomed[0]["config_dir"], str(self.bot_home / "accounts" / "main"))
        self.assertTrue(rehomed[0]["enabled"])
        link = self.bot_home / "accounts" / "main" / "projects"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(self.bot_home / "sessions"))
        self.assertFalse(rehomed[1]["enabled"])  # its config folder does not exist here

    def test_typed_word_required(self) -> None:
        code = self.restore("yes\n")
        self.assertEqual(code, 4)
        self.assertIn(t("ops.restore_declined"), self.out)
        self.assertEqual(self.dumps(), self.after)
        self.assertEqual(self.stop_calls(), [])
        res = self.run_cli(None, "restore", self.info.id, input="khoi phuc\n")  # not a terminal: never answered
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertEqual(self.dumps(), self.after)

    def test_failure_halfway_moves_data_back(self) -> None:
        real = backup.copy_private
        count = {"n": 0}

        def flaky(src, dest):
            count["n"] += 1
            if count["n"] == 3:
                raise OSError(28, "No space left on device")
            return real(src, dest)

        with mock.patch.object(backup, "copy_private", flaky):
            code = self.restore()
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.dumps(), self.after)
        self.assertTrue((self.bot_home / "profiles" / "p2.json").exists())
        self.assertIn('"new"', (self.bot_home / "bridge" / "journal.jsonl").read_text(encoding="utf-8"))
        leftovers = [p for p in (self.bot_home / "backups").iterdir() if p.name.endswith("-before-restore")]
        self.assertEqual([p for p in leftovers if any(p.rglob("*"))], [])
        self.assertIn("server", self.alive_services())  # started again
        self.assertEqual(self.history()[-1]["result"], "failed")

    def test_newer_backup_refused(self) -> None:
        meta = json.loads((self.info.path / "backup.json").read_text(encoding="utf-8"))
        meta["migrations_applied"].append("0099_future.sql")
        (self.info.path / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.restore(), 3)
        self.assertIn(t("ops.restore_newer", id=self.info.id), self.out)
        meta["migrations_applied"].remove("0099_future.sql")
        meta["app_version"] = "9.0.0"
        (self.info.path / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.restore(), 3)
        meta["app_version"] = "checkout"  # judged by its migrations alone
        (self.info.path / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.restore(), 0, self.out)

    def test_damaged_and_unknown(self) -> None:
        meta = json.loads((self.info.path / "backup.json").read_text(encoding="utf-8"))
        (self.info.path / meta["files"][-1]["path"]).write_text("tampered", encoding="utf-8")
        self.assertEqual(self.restore(), 1)
        self.assertIn(t("ops.restore_damaged", id=self.info.id), self.out)
        ctx = self.ctx(interactive=True)
        self.assertEqual(self.quiet(backup.cmd_restore, ctx, _args("nope")), 2)

    def test_dry_run_changes_nothing(self) -> None:
        res = self.run_cli(None, "restore", self.info.id, "--dry-run")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(self.info.id, res.stdout)
        self.assertEqual(self.dumps(), self.after)
        self.assertEqual(self.stop_calls(), [])
        self.assertFalse(any(p.name.endswith("-before-restore") for p in (self.bot_home / "backups").iterdir()))

    def test_restart_runs_real_hook_under_restore_lock(self) -> None:
        # A backup taken when only 0001 was applied: after the restore, 0002 and 0003 are pending again.
        old = self.tmp / "partial-d1"
        os.rename(self.bot_home / "d1", old)
        self.seed_d1(self.root, stop_before="0002_outbox.sql")
        self.info = backup.make(self.ctx(), mode="online", reason="manual")
        self.assertEqual(self.info.migrations_applied, ["0001_init.sql"])
        os.rename(self.bot_home / "d1", self.tmp / "d1-1")
        os.rename(old, self.bot_home / "d1")
        self.behave(start_local={"hook": True})
        with state.InstallLock(self.paths()):
            code = self.restore()
        self.assertEqual(code, 0, self.out)
        reasons = [b.reason for b in state.list_backups(self.paths())]
        self.assertIn("before-migration", reasons)  # made by the real hook, while the restore held InstallLock
        log = (self.bot_home / "logs" / "backup.log").read_text(encoding="utf-8")
        self.assertNotIn(t("core.locked"), log)
        self.assertEqual(self.applied(), ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])
