"""Claude login of the pool accounts (16.6.1, rev F8, F17, rev check): only a claude.ai login with a plan enables
the account; a Console login is logged out and stays disabled; a login without a reported plan stays disabled
until the owner enables it by hand; the account email never reaches the output or the logs."""

from __future__ import annotations

import argparse
import json

from tests.fakes_setup import SetupTestCase
from thomhouse_installer import accounts, human, steps
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
EMAIL = "x@example.invalid"


def login_args(label: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(command="login-claude", label=label)


class ClaudeLoginTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device(accounts_main=True)
        self.main_dir = str(self.bot_home / "accounts" / "main")

    def main(self) -> dict:
        return next(a for a in self.pool() if a["label"] == "main")

    def assertNoEmail(self, out: str) -> None:
        self.assertNotIn(EMAIL, out)
        self.assertNotIn(EMAIL, self.install_log())

    def logins(self) -> list[dict]:
        return [c for c in self.calls("claude") if c["argv"][:2] == ["auth", "login"]]

    def test_postponed_login_leaves_main_disabled(self) -> None:
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="s\n")
        self.assertEqual(code, 4)
        self.assertFalse(self.main()["enabled"])
        self.assertEqual(self.logins(), [])
        self.assertIn(t("setup.claude_later", tb=TB), out)
        self.assertEqual(self.summary()["claude_login"], ("pending", "later"))

    def test_subscription_login_enables_and_resets(self) -> None:
        (self.bot_home / "account-state.json").write_text(json.dumps({"main": {"status": "login_expired"}}),
                                                          encoding="utf-8")
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="c\n")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.main()["enabled"])
        state_file = json.loads((self.bot_home / "account-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state_file["main"]["status"], "ok")
        self.assertEqual([c["env"]["CLAUDE_CONFIG_DIR"] for c in self.logins()], [self.main_dir])
        self.assertIn(t("setup.claude_done"), out)
        self.assertIn(t("setup.claude_browser_logout"), out)
        self.assertEqual(self.summary()["claude_login"], ("done", None))
        self.assertTrue(steps.STEPS[13].check(self.ctx()))
        self.assertNoEmail(out)

    def test_console_login_stays_disabled(self) -> None:
        self.behave(claude={"login": "api_key"})
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="c\ns\n")
        self.assertEqual(code, 4)
        self.assertFalse(self.main()["enabled"])
        logouts = [c for c in self.calls("claude") if c["argv"][:2] == ["auth", "logout"]]
        self.assertEqual([c["env"]["CLAUDE_CONFIG_DIR"] for c in logouts], [self.main_dir])
        self.assertIn(t("setup.claude_console"), out)
        self.assertEqual(self.summary()["claude_login"], ("pending", "console_login"))
        self.assertNoEmail(out)

    def test_console_login_then_retry_with_plan(self) -> None:
        self.behave(claude={"login": "api_key"})
        ctx = self.human_ctx()
        account = accounts.load(ctx)[0]
        outcome, out = self.run_flow(human.claude_login_flow, ctx, account, answers="c\ns\n")
        self.assertEqual(outcome, ("pending", "console_login"))
        self.behave(claude={"login": "max"})
        outcome, out = self.run_flow(human.claude_login_flow, ctx, account, answers="c\n")
        self.assertEqual(outcome, ("done", None))
        self.assertTrue(self.main()["enabled"])

    def test_null_subscription_stays_disabled_until_enabled_by_hand(self) -> None:
        self.behave(claude={"login": "null"})
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertFalse(self.main()["enabled"])
        self.assertEqual([c for c in self.calls("claude") if c["argv"][:2] == ["auth", "logout"]], [])
        self.assertEqual(len(self.logins()), 1)  # `c` reads the status again, it does not log in again
        self.assertEqual(out.count(t("setup.claude_no_plan")), 2)
        self.assertEqual(self.summary()["claude_login"], ("pending", "no_subscription"))
        ctx = self.ctx()
        self.assertFalse(human.claude_logins_ok(ctx))
        # The owner checked the plan on claude.ai and enables the account by hand (16.6.1): step 14 counts it.
        self.assertEqual(accounts.pool(ctx, "enable", "main"), 0)
        self.assertEqual(accounts.pool(ctx, "reset", "main"), 0)
        self.assertTrue(human.claude_logins_ok(ctx))
        self.assertTrue(steps.STEPS[13].check(ctx))
        self.assertNoEmail(out)

    def test_not_logged_in_asks_again(self) -> None:
        self.behave(claude={"login": "fail"})
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertEqual(len(self.logins()), 2)
        self.assertEqual(out.count(t("setup.claude_not_logged_in")), 2)
        self.assertFalse(self.main()["enabled"])

    def test_non_interactive_postpones(self) -> None:
        code, out = self.run_flow(human.cmd_login_claude, login_args(), interactive=False)
        self.assertEqual(code, 4)
        self.assertEqual(self.logins(), [])
        self.assertFalse(self.main()["enabled"])

    def test_unknown_label_and_missing_pool(self) -> None:
        code, out = self.run_flow(human.cmd_login_claude, login_args("nope"), answers="")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.claude_unknown_label", label="nope"), out)
        (self.bot_home / "accounts.json").unlink()
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.claude_no_pool", tb=TB), out)

    def test_add_claude(self) -> None:
        args = argparse.Namespace(command="add-claude", label="acc2", priority=5)
        code, out = self.run_flow(human.cmd_add_claude, args, answers="c\n")
        self.assertEqual(code, 0, out)
        acc2 = next(a for a in self.pool() if a["label"] == "acc2")
        self.assertEqual((acc2["priority"], acc2["enabled"]), (5, True))
        self.assertEqual(acc2["config_dir"], str(self.bot_home / "accounts" / "acc2"))
        self.assertNotIn(t("setup.claude_restart_rooms", tb=TB), out)  # OpenMausBot is not running
        self.assertEqual(self.summary().get("claude_login"), None)  # main still needs its login
        code, out = self.run_flow(human.cmd_add_claude, args, answers="")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.claude_label_exists", label="acc2", tb=TB), out)

    def test_default_label_without_main(self) -> None:
        cfg = self.bot_home / "accounts"
        entries = [{"label": "default", "config_dir": str(cfg / "default"), "priority": 1, "enabled": True},
                   {"label": "acc2", "config_dir": str(cfg / "acc2"), "priority": 2, "enabled": False}]
        (cfg / "default").mkdir(parents=True)
        (cfg / "acc2").mkdir(parents=True)
        (self.bot_home / "accounts.json").write_text(json.dumps(entries), encoding="utf-8")
        with open(self.tmp / "claude-auth.json", "w", encoding="utf-8") as f:  # default is logged in already
            json.dump({str(cfg / "default"): {"loggedIn": True, "authMethod": "claude.ai",
                                              "subscriptionType": "max"}}, f)
        code, out = self.run_flow(human.cmd_login_claude, login_args(), answers="c\n")
        self.assertEqual(code, 0, out)
        self.assertEqual([c["env"]["CLAUDE_CONFIG_DIR"] for c in self.logins()], [str(cfg / "acc2")])
        self.assertEqual(self.summary()["claude_login"], ("done", None))

    def test_console_login_doctor_check_30_fails(self) -> None:
        self.behave(claude={"login": "api_key"})
        self.run_flow(human.claude_login_flow, self.human_ctx(), accounts.load(self.ctx())[0], answers="c\ns\n")
        # The account is logged out after a Console login; a Console login that is still present is check 30's
        # LỖI case (rev F8).
        with open(self.tmp / "claude-auth.json", "w", encoding="utf-8") as f:
            json.dump({self.main_dir: {"loggedIn": True, "authMethod": "api_key"}}, f)
        res = self.run_cli(None, "doctor", "--json", "--only", "claude_login")
        data = json.loads(res.stdout)
        check = next(c for c in data["checks"] if c["id"] == "claude_login")
        self.assertEqual(check["status"], "fail")
        self.assertNotIn(EMAIL, res.stdout)
