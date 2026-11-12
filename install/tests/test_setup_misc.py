"""History sync (16.6.3), the two analyzers (steps 18 and 19, rev visits), labels (16.6.4) and the staff token
(16.6.5, rev F16, F17)."""

from __future__ import annotations

import argparse
import io
import os
import sys
import threading
import time
from unittest import mock

from tests.fakes_setup import SetupTestCase
from thomhouse_installer import envs, human, state, steps
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
SYNC = ["--json", "sync", "--days", "365", "--no-media", "--no-cloud"]


def ns(command: str, **attrs: object) -> argparse.Namespace:
    return argparse.Namespace(command=command, **attrs)


class HistorySyncTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device()
        state.step_set(self.paths(), "zalo_login", "done")
        for name, value in (("SYNC_TICK_S", 0.02), ("SYNC_WINDOW_S", 0.1)):
            patcher = mock.patch.object(human, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def syncs(self) -> list[list]:
        return [c["argv"] for c in self.calls("zalo-agent") if "sync" in c["argv"]]

    def test_countdown_and_retry_with_F(self) -> None:
        self.behave(zalo_agent={"sync_exit": 1})
        code, out = self.run_flow(human.cmd_sync_history, ns("sync-history", force=False), answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertEqual(self.syncs(), [SYNC, SYNC + ["-F"]])
        self.assertGreaterEqual(out.count("ĐỒNG BỘ NGAY trên điện thoại"), 4)  # at least two lines per run
        self.assertEqual(out.count(t("setup.sync_retry")), 2)
        self.assertEqual(self.summary()["history_sync"], ("pending", "later"))

    def test_done_and_force(self) -> None:
        code, out = self.run_flow(human.cmd_sync_history, ns("sync-history", force=True), answers="c\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.syncs(), [SYNC + ["-F"]])
        self.assertIn(t("setup.sync_done"), out)
        self.assertEqual(self.summary()["history_sync"], ("done", None))

    def test_limit_stops_the_sync(self) -> None:
        os.environ["THOMHOUSE_SYNC_TIMEOUT_S"] = "0.01"
        self.behave(zalo_agent={"sync_exit": 0})
        code, out = self.run_flow(human.cmd_sync_history, ns("sync-history", force=False), answers="c\ns\n")
        self.assertEqual(code, 4)
        self.assertIn(t("setup.sync_retry"), out)

    def test_needs_the_zalo_login(self) -> None:
        state.step_set(self.paths(), "zalo_login", "pending", "later")
        self.behave(bridge={"doctor": {"zalo_login": "fail"}})
        code, out = self.run_flow(human.cmd_sync_history, ns("sync-history", force=False), answers="c\n")
        self.assertEqual(code, 4)
        self.assertIn(t("setup.sync_needs_zalo", tb=TB), out)
        self.assertEqual(self.syncs(), [])


class AnalyzerTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device()
        os.environ["PROFILE_LLM_ENABLED"] = "true"  # the parent's value must never reach the analyzers

    def test_both_run_with_profile_llm_false(self) -> None:
        self.make_zalo_cache()
        code, out = self.run_flow(human.cmd_analyze, ns("analyze", contacts=False, visits=False), answers="")
        self.assertEqual(code, 0, out)
        for tool in ("analyze_contacts", "analyze_visits"):
            calls = self.calls(tool)
            self.assertEqual(len(calls), 1, tool)
            self.assertEqual(calls[0]["argv"], ["--push"])
            self.assertEqual(calls[0]["env"]["PROFILE_LLM_ENABLED"], "false")
            self.assertEqual(calls[0]["cwd"], os.path.realpath(self.app_home / "app"))
            self.assertIn("SERVER_URL", calls[0]["env_names"])
        self.assertNotIn('"pushed"', out)  # analyzer output is read in memory, never shown
        self.assertEqual(self.summary()["analyze_contacts"], ("done", None))
        self.assertEqual(self.summary()["analyze_visits"], ("done", None))
        self.assertIn("/staff/chat-facts/eligible", [c["path"] for c in self.server_calls()])
        self.assertTrue(all(c["auth"] for c in self.server_calls() if c["path"] == "/staff/chat-facts/eligible"))

    def test_skipped_without_cache(self) -> None:
        code, out = self.run_flow(human.cmd_analyze, ns("analyze", contacts=True, visits=True), answers="")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls("analyze_contacts") + self.calls("analyze_visits"), [])
        self.assertEqual(self.summary()["analyze_contacts"], ("skipped", "no_cache"))
        self.assertEqual(self.summary()["analyze_visits"], ("skipped", "no_cache"))
        self.assertIn(t("setup.analyze_no_cache", tb=TB), out)

    def test_visits_only(self) -> None:
        self.make_zalo_cache()
        code, out = self.run_flow(human.cmd_analyze, ns("analyze", contacts=False, visits=True), answers="")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls("analyze_contacts"), [])

    def test_analyzer_404_on_stderr_is_server_404(self) -> None:
        self.make_zalo_cache()
        self.behave(analyze_visits={"not_found": True})
        outcome, out = self.run_flow(human.visits_flow, answers="")
        self.assertEqual(outcome, ("pending", "server_404"))
        self.assertEqual(out.strip(), t("setup.visits_server_404"))
        self.assertNotIn("chat-facts/import", out)

    def test_other_analyzer_failure(self) -> None:
        self.make_zalo_cache()
        self.behave(analyze_visits={"exit": 1, "stderr": "analyze_visits: push failed: HTTP 500"},
                    analyze_contacts={"exit": 1})
        outcome, out = self.run_flow(human.visits_flow, answers="")
        self.assertEqual(outcome, ("pending", "exit_1"))
        self.assertIn(t("setup.visits_failed", tb=TB), out)
        self.assertNotIn("HTTP 500", out)
        outcome, out = self.run_flow(human.contacts_flow, answers="")
        self.assertEqual(outcome, ("pending", "exit_1"))


class VisitsServer404Test(SetupTestCase):
    def test_visits_404_pending(self) -> None:
        root = self.new_device(zalo_cache=True)
        self.server.set_route("GET /staff/chat-facts/eligible", 404, {"error": "not_found"})
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--skip-human", "--yes", answers="dong y\n")
        self.assertEqual(code, 10, out)
        block = out.split(t("setup.step_line", n=19, title=t("setup.title_analyze_visits")), 1)[1]
        block = block.split(t("setup.step_line", n=20, title=t("setup.title_labels")), 1)[0]
        self.assertEqual(block.strip(), t("setup.visits_server_404"))
        self.assertEqual(self.summary(root)["analyze_visits"], ("pending", "server_404"))
        self.assertEqual(self.calls("analyze_visits"), [])
        self.server.set_route("GET /staff/chat-facts/eligible", 200, {"conversations": []})
        code, out = self.run_steps(root, "continue", "--skip-human", answers="")
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(root)["analyze_visits"], ("done", None))
        self.assertEqual(len(self.calls("analyze_visits")), 1)


class LabelsTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device()

    def label_calls(self) -> list[list]:
        return [c["argv"] for c in self.calls("bridge") if c["argv"][:1] == ["sync-labels"]]

    def test_counts_from_the_dry_run(self) -> None:
        self.behave(bridge={"sync_labels": [0, {"contacts": {"customer": 5, "manager": 2, "staff": 3}}]})
        code, out = self.run_flow(human.cmd_labels, ns("labels", sync=False), answers="c\nc\n")
        self.assertEqual(code, 0, out)
        self.assertIn(t("setup.labels_found", customer=5, manager=2, staff=3), out)
        self.assertIn(t("setup.labels_done"), out)
        self.assertEqual(self.label_calls(), [["sync-labels", "--dry-run"], ["sync-labels"]])
        self.assertEqual(self.summary()["labels"], ("done", None))

    def test_nothing_labelled_asks_again(self) -> None:
        self.behave(bridge={"sync_labels": [0, {"contacts": {"customer": 0, "manager": 0, "staff": 0}}]})
        code, out = self.run_flow(human.cmd_labels, ns("labels", sync=False), answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertEqual(out.count(t("setup.labels_none")), 2)
        self.assertEqual(self.label_calls(), [["sync-labels", "--dry-run"]] * 2)

    def test_sync_option_skips_the_questions(self) -> None:
        code, out = self.run_flow(human.cmd_labels, ns("labels", sync=True), answers="")
        self.assertEqual(code, 0)
        self.assertEqual(self.label_calls(), [["sync-labels"]])
        self.assertNotIn(t("setup.labels_screen"), out)

    def test_sync_failure_is_pending(self) -> None:
        self.behave(bridge={"sync_labels": [1, None]})
        code, out = self.run_flow(human.cmd_labels, ns("labels", sync=True), answers="")
        self.assertEqual(code, 1)
        self.assertEqual(self.summary()["labels"], ("pending", "exit_1"))

    def test_step_check_reads_the_roles(self) -> None:
        check = steps.STEPS[19].check
        self.assertTrue(check(self.ctx()))
        self.server.set_route("GET /staff/roles", 200, {"roles": []})
        self.assertFalse(check(self.ctx()))
        self.server.set_route("GET /staff/roles", 200, [{"zalo_user_id": "1", "role": "staff"}])
        self.assertTrue(check(self.ctx()))


class StaffTokenTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device()
        self.token = envs.value(self.paths(), "server", "STAFF_TOKEN")
        self.assertTrue(self.token)
        self.clipboard = self.tmp / "clipboard"

    def copies(self) -> list[dict]:
        return self.calls("pbcopy")

    def test_token_reaches_the_clipboard_and_is_cleared(self) -> None:
        code, out = self.run_flow(human.cmd_staff_token, ns("staff-token"), answers="c\n")
        self.assertEqual(code, 0, out)
        copies = self.copies()
        self.assertEqual(copies[0]["bytes"], len(self.token))
        self.assertEqual(copies[-1]["bytes"], 0)
        self.assertEqual(self.clipboard.read_bytes(), b"")
        self.assertIn(t("setup.token_screen", minutes=1), out)
        self.assertIn("lịch sử bộ nhớ tạm", out)  # the clipboard-history line (rev F17)
        self.assertEqual([c["argv"] for c in self.calls("open")], [[self.server.url]])
        self.assertNotIn(self.token, out)
        self.assertNotIn(self.token, self.install_log())
        self.assertEqual(self.summary()["staff_token"], ("done", None))

    def test_later_also_clears(self) -> None:
        code, out = self.run_flow(human.cmd_staff_token, ns("staff-token"), answers="s\n")
        self.assertEqual(code, 4)
        self.assertEqual(self.clipboard.read_bytes(), b"")
        self.assertIn(t("setup.token_later", tb=TB), out)
        self.assertEqual(self.summary()["staff_token"], ("pending", "later"))

    def test_cleared_after_the_limit_while_waiting(self) -> None:
        read_fd, write_fd = os.pipe()
        seen = {"full": False, "empty": False}

        def watch() -> None:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                data = self.clipboard.read_bytes() if self.clipboard.exists() else None
                if data:
                    seen["full"] = True
                elif data == b"" and seen["full"]:
                    seen["empty"] = True
                    break
                time.sleep(0.05)
            os.write(write_fd, b"c\n")
            os.close(write_fd)

        watcher = threading.Thread(target=watch)
        watcher.start()
        ctx = self.human_ctx()
        out = io.StringIO()
        with os.fdopen(read_fd, "r") as stdin, mock.patch.object(sys, "stdin", stdin), \
                mock.patch("sys.stdout", out):
            code = human.cmd_staff_token(ctx, ns("staff-token"))
        watcher.join()
        self.assertEqual(code, 0)
        self.assertTrue(seen["full"] and seen["empty"], seen)  # emptied by the timer before the answer came

    def test_console_url_off_this_mac_is_refused_before_the_copy(self) -> None:
        for url in ("https://console.example.invalid/", "http://127.1:5173/", "file:///tmp/x.html"):
            ctx = self.human_ctx()
            ctx.env = dict(ctx.env, THOMHOUSE_CONSOLE_URL=url)
            code, out = self.run_flow(human.cmd_staff_token, ctx, ns("staff-token"), answers="c\n")
            self.assertEqual(code, 1, out)
            self.assertIn(t("setup.token_console_not_local", url=url, tb=TB), out)
            self.assertEqual(self.copies(), [])
            self.assertEqual(self.calls("open"), [])
            self.assertNotEqual(self.summary()["staff_token"], ("done", None))
        for url in ("http://localhost:5173/", "http://[::1]:5173"):
            self.assertTrue(human._local_console(url), url)

    def test_other_clipboard_content_is_kept(self) -> None:
        ctx = self.human_ctx()
        self.clipboard.write_bytes(b"something the person copied")
        before = len(self.copies())
        human._clear_clipboard(ctx, human._digest(self.token))
        self.assertEqual(len(self.copies()), before)
        self.assertEqual(self.clipboard.read_bytes(), b"something the person copied")

    def test_clear_seconds_bounds(self) -> None:
        for value, expected in (("1", 1), ("300", 300), ("0", 120), ("301", 120), ("abc", 120)):
            os.environ["THOMHOUSE_CLIPBOARD_CLEAR_S"] = value
            self.assertEqual(human._clear_seconds(self.ctx()), expected, value)
        os.environ["THOMHOUSE_CLIPBOARD_CLEAR_S"] = "121"
        code, out = self.run_flow(human.cmd_staff_token, ns("staff-token"), answers="c\n")
        self.assertIn(t("setup.token_screen", minutes=3), out)

    def test_non_interactive_does_nothing(self) -> None:
        code, out = self.run_flow(human.cmd_staff_token, ns("staff-token"), interactive=False)
        self.assertEqual(code, 4)
        self.assertEqual(self.copies(), [])
        self.assertIn(t("setup.needs_terminal"), out)

    def test_missing_token(self) -> None:
        dev_vars = self.app_home / "app" / "apps" / "server" / ".dev.vars"
        dev_vars.write_text("ENV=dev\n", encoding="utf-8")
        code, out = self.run_flow(human.cmd_staff_token, ns("staff-token"), answers="c\n")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.token_missing", tb=TB), out)
        self.assertEqual(self.copies(), [])
