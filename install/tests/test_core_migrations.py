"""migrations.py: the miniflare D1 file, applied and pending migrations, apply, the active catalog (rev F7, F13)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path

from tests.support import FAKE_BIN, InstallerTestCase
from thomhouse_installer import migrations

ALL = ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"]


class MigrationsTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release()
        shim = self.root / "apps" / "server" / "node_modules" / ".bin" / "wrangler"
        shim.parent.mkdir(parents=True)
        shim.write_text(f'#!/bin/sh\nexec "{FAKE_BIN}/wrangler" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        self.ctx_ = self.ctx()
        self.folder = self.bot_home / "d1" / "v3" / "d1" / "miniflare-D1DatabaseObject"

    def snapshot(self) -> dict[str, tuple[str, float]]:
        out = {}
        for f in sorted(self.folder.iterdir()):
            out[f.name] = (hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime)
        return out

    def test_no_database(self) -> None:
        self.assertIsNone(migrations.find_db(self.bot_home))
        self.assertEqual(migrations.applied(self.bot_home), [])
        self.assertEqual(migrations.pending(self.app_home / "app", self.bot_home), ALL)
        self.assertIsNone(migrations.active_catalog(self.bot_home))
        self.folder.mkdir(parents=True)
        sqlite3.connect(self.folder / "metadata.sqlite").close()
        self.assertEqual(migrations.applied(self.bot_home), [])

    def test_apply_find_and_pending(self) -> None:
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 0)
        db = migrations.find_db(self.bot_home)
        self.assertIsNotNone(db)
        self.assertNotEqual(db.name, "metadata.sqlite")
        self.assertEqual(len(db.stem), 64)
        self.assertEqual(migrations.applied(self.bot_home), ALL)
        self.assertEqual(migrations.pending(self.app_home / "app", self.bot_home), [])
        self.assertTrue((self.bot_home / "d1" / "v3" / "do" / "thomhouse-bot-ConversationDO").is_dir())
        call = self.calls("wrangler")[0]
        self.assertEqual(call["argv"], ["d1", "migrations", "apply", "thomhouse-main", "--local", "--persist-to",
                                        str(self.bot_home / "d1")])
        self.assertEqual(call["cwd"], os.path.realpath(self.app_home / "app" / "apps" / "server"))
        self.assertEqual(call["env"]["DISABLE_UPDATES"], "1")
        self.assertIn("applied 0001_init.sql", (self.app_home / "logs" / "migrations.log").read_text())

    def test_failure_mid_way(self) -> None:
        self.behave(wrangler={"fail_at": 3})
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 1)
        self.assertEqual(migrations.applied(self.bot_home), ALL[:2])
        self.assertEqual(migrations.pending(self.app_home / "app", self.bot_home), ["0003_profiles.sql"])

    def test_newest_file_with_table_wins(self) -> None:
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 0)
        current = migrations.find_db(self.bot_home)
        old = self.folder / ("a" * 64 + ".sqlite")
        con = sqlite3.connect(old)
        con.execute("CREATE TABLE d1_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
        con.execute("INSERT INTO d1_migrations (name) VALUES ('0001_init.sql')")
        con.commit()
        con.close()
        past = time.time() - 3600
        os.utime(old, (past, past))
        newer_without_table = self.folder / ("b" * 64 + ".sqlite")
        con = sqlite3.connect(newer_without_table)
        con.execute("CREATE TABLE other (x)")
        con.commit()
        con.close()
        future = time.time() + 3600
        os.utime(newer_without_table, (future, future))
        self.assertEqual(migrations.find_db(self.bot_home), current)
        os.utime(old, (future + 10, future + 10))
        self.assertEqual(migrations.find_db(self.bot_home), old)
        self.assertEqual(migrations.applied(self.bot_home), ["0001_init.sql"])

    def test_files_without_table_give_none(self) -> None:
        self.folder.mkdir(parents=True)
        con = sqlite3.connect(self.folder / ("c" * 64 + ".sqlite"))
        con.execute("CREATE TABLE other (x)")
        con.commit()
        con.close()
        self.assertIsNone(migrations.find_db(self.bot_home))
        self.assertIsNone(migrations.applied(self.bot_home))
        self.assertIsNone(migrations.pending(self.app_home / "app", self.bot_home))
        (self.folder / ("d" * 64 + ".sqlite")).write_bytes(b"not a database at all")
        self.assertIsNone(migrations.applied(self.bot_home))

    def test_active_catalog(self) -> None:
        self.behave(wrangler={"catalog": "cv_local_0123456789ab"})
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 0)
        self.assertEqual(migrations.active_catalog(self.bot_home), "cv_local_0123456789ab")

    def test_read_only_open_changes_nothing(self) -> None:
        self.behave(wrangler={"catalog": "cv_local_0123456789ab"})
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 0)
        before = self.snapshot()
        time.sleep(0.05)
        migrations.find_db(self.bot_home)
        migrations.applied(self.bot_home)
        migrations.pending(self.app_home / "app", self.bot_home)
        migrations.active_catalog(self.bot_home)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), sorted(before))

    def test_apply_without_wrangler(self) -> None:
        (self.root / "apps" / "server" / "node_modules" / ".bin" / "wrangler").unlink()
        self.assertEqual(migrations.apply(self.ctx_, self.app_home / "app"), 127)

    def test_pending_lists_only_sql(self) -> None:
        (self.root / "apps" / "server" / "migrations" / "README.md").write_text("x", encoding="utf-8")
        self.assertEqual(migrations.pending(Path(self.app_home / "app"), self.bot_home), ALL)
