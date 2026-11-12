"""paths.py: defaults, overrides, whitespace refusal, installed and checkout mode, logical code_root (16.2.7)."""

from __future__ import annotations

import os
from pathlib import Path

from tests.support import REAL_HOME, InstallerTestCase
from thomhouse_installer import context, paths


class PathsTest(InstallerTestCase):
    def test_defaults_from_home(self) -> None:
        env = {"HOME": str(self.home)}
        p = paths.resolve(env, code_root=self.tmp / "nowhere")
        self.assertEqual(p.app_home, self.home / "ThomHouse")
        self.assertEqual(p.bot_home, self.home / ".thomhouse-bot")
        self.assertEqual(p.zalo_config, self.home / ".zalo-agent-cli")
        self.assertEqual(p.launcher, self.home / "ThomHouse" / "bin" / "thomhouse")
        self.assertEqual(p.trust, self.home / "ThomHouse" / "trust" / "allowed_signers")
        self.assertEqual(p.d1_dir, self.home / ".thomhouse-bot" / "d1")
        self.assertEqual(p.backups_lock, self.home / ".thomhouse-bot" / "backups" / ".lock")
        self.assertEqual(p.moved_out, self.home / ".thomhouse-bot" / "moved-out.json")
        self.assertEqual(p.release_dir("1.4.0"), self.home / "ThomHouse" / "releases" / "1.4.0")

    def test_overrides(self) -> None:
        env = {
            "HOME": str(self.home),
            "THOMHOUSE_APP_HOME": str(self.tmp / "app-home"),
            "THOMHOUSE_BOT_HOME": str(self.tmp / "bot-home"),
            "ZALO_CONFIG_DIR": str(self.tmp / "zalo"),
        }
        p = paths.resolve(env, code_root=self.tmp / "nowhere")
        self.assertEqual(p.app_home, self.tmp / "app-home")
        self.assertEqual(p.bot_home, self.tmp / "bot-home")
        self.assertEqual(p.zalo_config, self.tmp / "zalo")
        self.assertEqual(p.run_dir, self.tmp / "bot-home" / "run")
        tilde = paths.resolve({"HOME": str(self.home), "THOMHOUSE_APP_HOME": "~/Other"}, code_root=self.tmp)
        self.assertEqual(tilde.app_home, self.home / "Other")

    def test_whitespace_refused(self) -> None:
        for key in ("THOMHOUSE_APP_HOME", "THOMHOUSE_BOT_HOME"):
            env = {"HOME": str(self.home), key: str(self.tmp / "with space")}
            with self.assertRaises(context.Exit) as cm:
                paths.resolve(env, code_root=self.tmp)
            self.assertEqual(cm.exception.code, 3)
            self.assertEqual(cm.exception.key, "core.whitespace_path")

    def test_installed_mode(self) -> None:
        release = self.install_release("1.4.0")
        p = self.paths(self.app_home / "app")
        self.assertEqual(p.mode, "installed")
        self.assertEqual(p.app, self.app_home / "app")
        self.assertEqual(p.lock_file, self.app_home / ".install.lock")
        self.assertEqual(p.logs, self.app_home / "logs")
        self.assertEqual(p.history, self.app_home / "history.jsonl")
        self.assertEqual(p.env_file("server"), self.app_home / "app" / "apps" / "server" / ".dev.vars")
        self.assertEqual(p.env_file("console_local"), self.app_home / "app" / "apps" / "console" / ".env.local")
        # From the release folder itself (bootstrap runs there before step 8): still installed mode, app unchanged.
        q = self.paths(release)
        self.assertEqual(q.mode, "installed")
        self.assertEqual(q.code_root, release)
        self.assertEqual(q.app, self.app_home / "app")

    def test_checkout_mode(self) -> None:
        root = self.make_checkout()
        p = self.paths(root)
        self.assertEqual(p.mode, "checkout")
        self.assertEqual(p.app, root)
        self.assertEqual(p.lock_file, self.bot_home / ".install.lock")
        self.assertEqual(p.logs, self.bot_home / "logs")
        self.assertEqual(p.history, self.bot_home / "history.jsonl")
        self.assertEqual(p.env_file("runner"), root / "apps" / "runner" / ".env")

    def test_code_root_keeps_logical_path(self) -> None:
        self.install_release("1.4.0")
        app = self.app_home / "app"
        self.assertTrue(app.is_symlink())
        p = self.paths(app)
        self.assertEqual(p.code_root, app)
        self.assertNotEqual(str(p.code_root), os.path.realpath(app))
        self.assertEqual(p.app, app)

    def test_env_file_unknown_name(self) -> None:
        p = self.paths(self.tmp)
        with self.assertRaises(ValueError):
            p.env_file("nope")

    def test_default_code_root_is_package_parent(self) -> None:
        here = Path(os.path.abspath(paths.__file__)).parent.parent.parent
        self.assertEqual(paths.default_code_root(), here)

    def test_support_guard_catches_real_home(self) -> None:
        with self.assertRaises(AssertionError):
            self.assert_not_real_home(REAL_HOME / "x")
        self.assert_not_real_home(self.tmp / "x")
        for value in (self.env["HOME"], self.env["THOMHOUSE_APP_HOME"], self.env["THOMHOUSE_BOT_HOME"],
                      self.env["ZALO_CONFIG_DIR"]):
            self.assert_not_real_home(value)
        self.assertEqual(os.environ["HOME"], str(self.home))
