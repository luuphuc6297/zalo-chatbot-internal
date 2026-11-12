"""accounts.py: a fresh claude_pool module per call (rev F23), the login status (rev F8), pool output discarded."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys

from tests.support import InstallerTestCase
from thomhouse_installer import accounts, paths

EMAIL = "x@example.invalid"


class AccountsTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.install_release()
        self.ctx_ = self.ctx()

    def write_pool(self, bot_home, entries, account_state=None) -> None:
        bot_home.mkdir(parents=True, exist_ok=True)
        (bot_home / "accounts.json").write_text(json.dumps(entries), encoding="utf-8")
        if account_state is not None:
            (bot_home / "account-state.json").write_text(json.dumps(account_state), encoding="utf-8")

    def test_missing_accounts_file(self) -> None:
        self.assertEqual(accounts.load(self.ctx_), [])
        self.assertEqual(os.environ["THOMHOUSE_BOT_HOME"], str(self.bot_home))

    def test_two_bot_homes_in_one_process(self) -> None:
        other = self.tmp / "bot-two"
        self.write_pool(self.bot_home, [{"label": "main", "config_dir": str(self.bot_home / "accounts" / "main"),
                                         "priority": 1, "enabled": False}])
        self.write_pool(other, [{"label": "acc2", "config_dir": None, "priority": 5, "enabled": True},
                                {"label": "acc1", "config_dir": None, "priority": 2, "enabled": True}],
                        {"acc1": {"status": "login_expired"}})
        first = accounts.load(self.ctx_)
        self.assertEqual([(a.label, a.enabled, a.priority) for a in first], [("main", False, 1)])
        self.assertEqual(first[0].config_dir, self.bot_home / "accounts" / "main")
        ctx2 = self.ctx()
        env2 = dict(os.environ)
        env2["THOMHOUSE_BOT_HOME"] = str(other)
        ctx2.paths = paths.resolve(env2, code_root=self.app_home / "app")
        second = accounts.load(ctx2)
        self.assertEqual([a.label for a in second], ["acc1", "acc2"])  # by priority
        self.assertEqual(second[0].pool_status, "login_expired")
        self.assertFalse(second[0].usable_now)
        self.assertTrue(second[1].usable_now)
        self.assertIsNone(second[1].config_dir)
        self.assertEqual([a.label for a in accounts.load(self.ctx_)], ["main"])
        self.assertFalse([m for m in sys.modules if "claude_pool" in m])

    def _login(self, label: str, mode: str | None) -> accounts.Account:
        cfg = self.bot_home / "accounts" / label
        cfg.mkdir(parents=True, exist_ok=True)
        if mode is not None:
            self.behave(claude={"login_by_dir": {str(cfg): mode}})
            from thomhouse_installer import proc

            env = proc.child_env(self.ctx_.paths, {"CLAUDE_CONFIG_DIR": str(cfg)})
            self.assertEqual(proc.run(self.ctx_, ["claude", "auth", "login"], env=env).returncode, 0)
        return accounts.Account(label, cfg, 1, False, "ok", True)

    def test_auth_status_ok_only_for_claude_ai_with_plan(self) -> None:
        cases = {"max": (True, "claude.ai", "max", True), "null": (True, "claude.ai", None, False),
                 "api_key": (True, "api_key", None, False), None: (False, "none", None, False)}
        for i, (mode, expected) in enumerate(cases.items()):
            account = self._login(f"acc{i}", mode)
            status = accounts.auth_status(self.ctx_, account)
            self.assertEqual((status.logged_in, status.auth_method, status.subscription, status.ok), expected, mode)
        last = self.calls("claude")[-1]
        self.assertEqual(last["argv"], ["auth", "status"])
        self.assertEqual(last["env"]["CLAUDE_CONFIG_DIR"], str(self.bot_home / "accounts" / "acc3"))
        default = accounts.Account("default", None, 1, True, "ok", True)
        accounts.auth_status(self.ctx_, default)
        self.assertIsNone(self.calls("claude")[-1]["env"]["CLAUDE_CONFIG_DIR"])

    def test_auth_status_not_json(self) -> None:
        bad = self.tmp / "badbin"
        bad.mkdir()
        (bad / "claude").write_text("#!/bin/sh\necho 'not json'\n", encoding="utf-8")
        (bad / "claude").chmod(0o755)
        os.environ["PATH"] = f"{bad}:{os.environ['PATH']}"
        status = accounts.auth_status(self.ctx_, accounts.Account("main", None, 1, False, "ok", True))
        self.assertEqual((status.logged_in, status.auth_method, status.subscription), (False, None, None))
        self.assertFalse(status.ok)

    def test_pool_output_never_shown_or_logged(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(accounts.pool(self.ctx_, "add", "main", "--priority", "1"), 0)
            self.assertEqual(accounts.pool(self.ctx_, "disable", "main"), 0)
            self._login("main", "max")
            self.assertEqual(accounts.pool(self.ctx_, "status"), 0)
        self.assertNotIn(EMAIL, out.getvalue() + err.getvalue())
        loaded = accounts.load(self.ctx_)
        self.assertEqual([(a.label, a.enabled, a.priority) for a in loaded], [("main", False, 1)])
        self.assertEqual(loaded[0].config_dir, self.bot_home / "accounts" / "main")
        self.assertTrue((self.bot_home / "accounts" / "main" / "projects").is_symlink())
        for f in (self.app_home / "logs").rglob("*"):
            if f.is_file():
                self.assertNotIn(EMAIL, f.read_text(encoding="utf-8", errors="replace"), f.name)
        status_calls = [c for c in self.calls("claude") if c["argv"] == ["auth", "status"]]
        self.assertTrue(status_calls)  # claude_pool.py status asked for the login, and its output was dropped
        self.assertEqual(accounts.pool(self.ctx_, "add", "main"), 1)  # already exists
