"""uninstall.py: the default keeps BOT_HOME; --data needs the typed words, logs out and stops the listener before
BOT_HOME moves, and goes to the Trash or the home-folder fallback, or stops with nothing logged out when neither
probe works; the LaunchAgent and shortcuts go only when their content matches; --dry-run only lists
(16.8.6, rev F24)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase
from thomhouse_installer import autostart, uninstall
from thomhouse_installer.text_vi import t


def _ns(**attrs: object) -> argparse.Namespace:
    ns = {"command": "uninstall", "data": False, "yes": False, "dry_run": False, "quiet": False, "offline": False,
          "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


class UninstallTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed()
        (self.home / "Desktop").mkdir()
        ctx = self.ctx()
        self.quiet(autostart.enable, ctx)
        self.quiet(autostart.shortcuts, ctx, True)
        self.plist = self.home / "Library" / "LaunchAgents" / "vn.thomhouse.bot.plist"
        self.desktop = [self.home / "Desktop" / n for n, _ in autostart.SHORTCUTS]
        b = self.bot_home
        (b / "accounts" / "main").mkdir(parents=True)
        (b / "accounts.json").write_text(json.dumps([
            {"label": "main", "config_dir": str(b / "accounts" / "main"), "priority": 1, "enabled": True},
            {"label": "default", "config_dir": None, "priority": 2, "enabled": True}]), encoding="utf-8")
        self.trash = self.home / ".Trash"
        self.trash.mkdir(mode=0o700)

    def with_data(self, typed: str = "xoa du lieu\n") -> int:
        self.answer(typed)
        return self.quiet(uninstall.cmd_uninstall, self.ctx(interactive=True), _ns(data=True))

    def lock_down(self, *folders: Path) -> None:
        for f in folders:
            os.chmod(f, 0o500)
            self.addCleanup(os.chmod, f, 0o700)

    def test_default_keeps_bot_home(self) -> None:
        res = self.run_cli(None, "uninstall", input="")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(self.app_home.exists())
        self.assertTrue((self.bot_home / "d1").is_dir())
        self.assertFalse(self.plist.exists())
        self.assertFalse(any(p.exists() for p in self.desktop))
        self.assertIn(t("ops.uninstall_kept", bot="~/.thomhouse-bot", zalo="~/.zalo-agent-cli"), res.stdout)
        self.assertEqual(len(self.stop_calls()), 1)
        self.assertEqual(self.alive_services(), set())
        self.assertEqual(self.calls("claude"), [])  # the default never logs out

    def test_data_needs_the_typed_words(self) -> None:
        res = self.run_cli(None, "uninstall", "--data", input="xoa du lieu\n")  # not a terminal
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertTrue(self.app_home.exists())
        self.assertTrue(self.bot_home.exists())
        self.assertEqual(self.with_data("xoa\n"), 4)
        self.assertTrue(self.bot_home.exists())

    def _record_renames(self):
        moves: list[tuple[float, str, str]] = []
        real = os.rename

        def rename(src, dst, *a, **kw):
            moves.append((time.time(), str(src), str(dst)))
            return real(src, dst, *a, **kw)

        patcher = mock.patch("os.rename", rename)
        patcher.start()
        self.addCleanup(patcher.stop)
        return moves

    def test_data_goes_to_the_trash_after_logout_and_listener_stop(self) -> None:
        moves = self._record_renames()
        code = self.with_data()
        self.assertEqual(code, 0, self.out)
        moved = [m for m in moves if m[1] == str(self.bot_home)]
        self.assertEqual(len(moved), 1)
        when, _, target = moved[0]
        self.assertTrue(target.startswith(str(self.trash / "thomhouse-bot-")))
        self.assertFalse(self.bot_home.exists())
        self.assertTrue((Path(target) / "d1").is_dir())
        reasons = [p.name for p in (Path(target) / "backups").iterdir()]
        self.assertTrue(any(n.endswith("-before-uninstall") for n in reasons), reasons)
        logout = [c for c in self.calls("claude") if c["argv"][:2] == ["auth", "logout"]]
        self.assertEqual([c["env"]["CLAUDE_CONFIG_DIR"] for c in logout], [str(self.bot_home / "accounts" / "main")])
        self.assertLess(logout[0]["at"], when)
        listener = [c for c in self.calls("bridge") if c["argv"][:2] == ["listener", "stop"]]
        self.assertEqual(len(listener), 1)
        self.assertLess(listener[0]["at"], when)
        self.assertFalse(self.app_home.exists())
        self.assertIn(t("ops.uninstall_in_trash", folder="~/.Trash/" + Path(target).name), self.out)
        self.assertFalse(list(self.trash.glob("thomhouse-probe-*")))

    def test_trash_refused_goes_to_the_home_folder(self) -> None:
        self.lock_down(self.trash)
        code = self.with_data()
        self.assertEqual(code, 0, self.out)
        fallback = list(self.home.glob("thomhouse-bot-da-xoa-*"))
        self.assertEqual(len(fallback), 1)
        self.assertTrue((fallback[0] / "d1").is_dir())
        self.assertIn(t("ops.uninstall_drag_to_trash", folder="~/" + fallback[0].name), self.out)
        self.assertFalse(list(self.home.glob(".thomhouse-probe-*")))

    def test_no_probe_works_nothing_logged_out_or_stopped(self) -> None:
        self.lock_down(self.trash, self.home)
        code = self.with_data()
        self.assertEqual(code, 1, self.out)
        self.assertIn(t("ops.uninstall_no_target", folder="~/.thomhouse-bot"), self.out)
        self.assertEqual([c for c in self.calls("claude") if c["argv"][:2] == ["auth", "logout"]], [])
        self.assertEqual([c for c in self.calls("bridge") if c["argv"][:2] == ["listener", "stop"]], [])
        self.assertEqual(self.stop_calls(), [])
        self.assertTrue(self.bot_home.is_dir())
        self.assertTrue(self.app_home.is_dir())
        self.assertIn("server", self.alive_services())
        self.assertFalse(list(self.bot_home.glob(".trash-probe-*")))

    def test_files_removed_only_when_their_content_matches(self) -> None:
        self.plist.write_text(self.plist.read_text(encoding="utf-8") + "<!-- edited -->\n", encoding="utf-8")
        edited = self.desktop[1]
        edited.write_text(edited.read_text(encoding="utf-8") + "echo mine\n", encoding="utf-8")
        res = self.run_cli(None, "uninstall", input="")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(self.plist.exists())
        self.assertTrue(edited.exists())
        self.assertFalse(self.desktop[0].exists())
        self.assertFalse(self.desktop[2].exists())

    def test_dry_run_only_lists(self) -> None:
        res = self.run_cli(None, "uninstall", "--dry-run", input="")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(t("ops.uninstall_dry_item", path="~/ThomHouse"), res.stdout)
        self.assertIn(t("ops.uninstall_dry_item", path="~/Library/LaunchAgents/vn.thomhouse.bot.plist"), res.stdout)
        self.assertIn(t("ops.uninstall_dry_keep", folder="~/.thomhouse-bot"), res.stdout)
        res = self.run_cli(None, "uninstall", "--data", "--dry-run", input="")
        self.assertIn(t("ops.uninstall_dry_data", folder="~/.thomhouse-bot"), res.stdout)
        self.assertTrue(self.app_home.exists() and self.bot_home.exists() and self.plist.exists())
        self.assertEqual(self.stop_calls(), [])

    def test_refuses_a_bot_home_inside_app_home(self) -> None:
        env = dict(self.env, THOMHOUSE_BOT_HOME=str(self.app_home / "data"))
        res = self.run_cli(None, "uninstall", input="", env=env)
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertTrue(self.app_home.exists())
