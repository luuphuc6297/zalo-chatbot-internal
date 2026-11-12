"""End-to-end job processing: stub backend + fake `claude` + real MCP proxy + real claude_pool."""

import io
import json
import os
import stat
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.helpers import RUNNER_ID, TOKEN, RunnerTestCase, make_job

from runner.poller import Runner
from runner.sessions import project_dir_name


class JobFlowTest(RunnerTestCase):
    def runner(self, **kw) -> Runner:
        return Runner(self.config(**kw))

    def session_files(self, cid: str) -> list[Path]:
        wd = self.home / "conversations" / cid
        d = self.home / "sessions" / project_dir_name(str(wd))
        d2 = self.home / "sessions" / project_dir_name(str(wd.resolve()))
        return sorted({*d.glob("*.jsonl"), *d2.glob("*.jsonl")})

    def test_new_session_draft_flags_env_and_workdir(self):
        self.backend.jobs.append(make_job())
        out = self.runner().run_once()
        self.assertEqual(out["outcome"], "draft")
        self.assertEqual(out["draft_status"], "pending")

        call = self.claude_calls()[0]
        flags = call["flags"]
        for f in ("--model", "claude-opus-5-5", "--effort", "low", "--setting-sources", "project",
                  "--strict-mcp-config", "--output-format", "json", "--allowedTools", "mcp__thom", "--mcp-config"):
            self.assertIn(f, flags)
        self.assertEqual(flags[flags.index("--tools") + 1], "")
        self.assertNotIn("--resume", flags)
        self.assertEqual(call["system_prompt"].split("<tool_naming>")[0].strip(), "BOT SYSTEM PROMPT h1")
        self.assertIn("mcp__thom__<name>", call["system_prompt"])
        self.assertEqual(call["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
        self.assertEqual(call["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
        self.assertIsNone(call["env"]["ANTHROPIC_API_KEY"])
        self.assertEqual(call["stdin"], "")
        self.assertTrue(call["cwd"].endswith("/conversations/cnv_abc"))
        self.assertIn("<turn_context>", call["text"])
        self.assertIn("<customer_message>\ngội đầu bao nhiêu tiền ạ\n</customer_message>", call["text"])
        self.assertEqual(call["account"], "a")

        body = self.backend.find("/draft")[0]["body"]
        self.assertEqual(body["text"], "Dạ em chào anh/chị ạ.")
        self.assertEqual(body["account_label"], "a")
        self.assertEqual((body["model"], body["effort"]), ("claude-opus-5-5", "low"))
        self.assertAlmostEqual(body["cost_usd_equiv"], 0.02)
        self.assertEqual(body["usage"]["cache_read_input_tokens"], 34605)
        self.assertEqual((body["num_turns"], body["duration_ms"]), (2, 1234))
        self.assertIsNone(body["error_kind"])
        self.assertTrue(body["session_id"])
        # the per-job MCP config (which carries the token) is removed after the call
        self.assertFalse((self.home / "run" / "job_1").exists())
        reqs = self.backend.requests
        self.assertTrue(all(r["auth"] == f"Bearer {TOKEN}" and r["runner_id"] == RUNNER_ID for r in reqs))
        self.assertNotIn("<customer_profile>", call["text"])

    def test_customer_profile_reaches_the_model_text(self):
        job = make_job()
        job["customer_profile"] = {"relationship": "customer", "address_term": "cô", "name_to_use": "Hoa",
                                   "services_likely_used": ["Massage body thư giãn"], "services_mentioned": []}
        self.backend.jobs.append(job)
        out = self.runner().run_once()
        self.assertEqual(out["outcome"], "draft")
        text = self.claude_calls()[0]["text"]
        self.assertIn('call the customer "cô"', text)
        self.assertIn('"cô Hoa"', text)
        self.assertIn("Massage body thư giãn", text)
        self.assertLess(text.index("<customer_profile>"), text.index("<customer_message>"))

    def test_resume_flow_cost_is_per_turn_delta(self):
        r = self.runner()
        self.backend.jobs.append(make_job("job_1"))
        r.run_once()
        sid = self.backend.find("/draft")[0]["body"]["session_id"]
        self.backend.jobs.append(make_job("job_2", session_id=sid, texts=("còn massage cổ vai gáy?",)))
        out = r.run_once()
        self.assertEqual(out["outcome"], "draft")
        flags = self.claude_calls()[1]["flags"]
        self.assertEqual(flags[flags.index("--resume") + 1], sid)
        second = self.backend.find("/draft")[1]["body"]
        self.assertEqual(second["session_id"], sid)
        self.assertAlmostEqual(second["cost_usd_equiv"], 0.02)   # cumulative 0.04 minus 0.02 of turn 1
        self.assertIsNone(second["error_kind"])
        rec = r.sessions.load("cnv_abc")
        self.assertEqual((rec.session_id, rec.customer_messages), (sid, 2))
        # resumed turns do not resend history
        self.assertNotIn("<conversation_so_far>", self.claude_calls()[1]["text"])

    def test_tool_call_through_mcp_proxy(self):
        self.set_fake(mode="tool")
        self.backend.jobs.append(make_job("job_tool"))
        out = self.runner().run_once()
        self.assertEqual(out["outcome"], "draft")
        tool_reqs = self.backend.find("/runner/tools/quote_price")
        self.assertEqual(len(tool_reqs), 1)
        self.assertEqual(tool_reqs[0]["body"]["job_id"], "job_tool")
        self.assertEqual(tool_reqs[0]["body"]["input"]["duration_min"], 50)
        self.assertEqual(tool_reqs[0]["auth"], f"Bearer {TOKEN}")
        self.assertEqual(tool_reqs[0]["runner_id"], RUNNER_ID)
        text = self.backend.find("/draft")[0]["body"]["text"]
        self.assertIn("199.000đ", text)
        self.assertIn("(8 tools)", text)  # 7 + attach_menu_images (menu images)

    def test_oauth_expired_switches_account(self):
        self.set_fake(accounts={"a": "oauth"})
        self.backend.jobs.append(make_job())
        out = self.runner().run_once()
        self.assertEqual(out["outcome"], "draft")
        self.assertEqual(self.backend.find("/draft")[0]["body"]["account_label"], "b")
        self.assertEqual([c["account"] for c in self.claude_calls()], ["a", "b"])
        self.assertEqual(self.pool_state()["a"]["status"], "login_expired")
        self.assertEqual(self.pool_state()["a"]["last_error"], "login_expired")
        self.assertEqual(self.pool_state()["b"]["status"], "ok")

    def test_weekly_limit_on_every_account_fails_limited(self):
        self.set_fake(accounts={"a": "weekly_limit", "b": "weekly_limit"})
        self.backend.jobs.append(make_job())

        def reset_day() -> str:      # the fake claude's reset: 2pm three days from now, Asia/Ho_Chi_Minh (UTC+7)
            return (datetime.now(timezone(timedelta(hours=7))) + timedelta(days=3)).strftime("%Y-%m-%dT14:00")

        before = reset_day()
        out = self.runner().run_once()
        after = reset_day()          # differs from `before` only when the run crosses midnight
        self.assertEqual(out["outcome"], "fail")
        body = self.backend.find("/fail")[0]["body"]
        self.assertEqual(body["error_kind"], "limited")
        self.assertIn("earliest reset", body["error_message"])
        st = self.pool_state()
        self.assertEqual(st["a"]["status"], "limited")
        self.assertEqual((st["a"]["last_error"], st["b"]["last_error"]), ("limited", "limited"))
        self.assertTrue(st["a"]["until"].startswith((before, after)), st["a"]["until"])
        self.assertFalse(body["session_broken"])
        # with every account resting, the runner stops claiming
        self.backend.jobs.append(make_job("job_2"))
        self.assertEqual(self.runner().run_once()["reason"], "no_usable_account")
        self.assertEqual(len(self.backend.find("/runner/jobs/claim")), 1)

    def test_mixed_account_failures_report_no_account(self):
        self.set_fake(accounts={"a": "oauth", "b": "weekly_limit"})
        self.backend.jobs.append(make_job())
        self.runner().run_once()
        self.assertEqual(self.backend.find("/fail")[0]["body"]["error_kind"], "no_account")

    def test_broken_resume_retries_once_with_new_session(self):
        r = self.runner()
        missing = "11111111-2222-4333-8444-555555555555"
        hist = [{"source": "customer", "text": "chào em", "at": 1762400000000},
                {"source": "bot", "text": "Dạ em chào anh/chị", "at": 1762400001000}]
        self.backend.jobs.append(make_job("job_r", session_id=missing, history=hist,
                                          sent=[{"message_id": "msg_s", "source": "staff", "text": "Dạ chị đợi em",
                                                 "sent_at": 1762400002000, "from_draft_id": None,
                                                 "edited_by_staff": False}]))
        out = r.run_once()
        self.assertEqual(out["outcome"], "draft")
        calls = self.claude_calls()
        self.assertEqual(len(calls), 2)
        self.assertIn("--resume", calls[0]["flags"])
        self.assertNotIn("--resume", calls[1]["flags"])
        self.assertIn("Dạ chị đợi em", calls[1]["text"])
        body = self.backend.find("/draft")[0]["body"]
        self.assertEqual(body["error_kind"], "session_restarted")
        self.assertNotEqual(body["session_id"], missing)
        # account is not blamed for a session error; the CLI printed no JSON, only that kind is kept
        self.assertEqual(self.pool_state()["a"].get("status", "ok"), "ok")
        self.assertEqual(self.pool_state()["a"]["last_error"], "parse_error")

    def test_broken_resume_then_failure_reports_session_broken(self):
        r = self.runner()
        self.backend.jobs.append(make_job("job_1"))
        r.run_once()
        sid = self.backend.find("/draft")[0]["body"]["session_id"]
        self.set_fake(mode="model_error")
        self.backend.jobs.append(make_job("job_2", session_id=sid))
        out = r.run_once()
        self.assertEqual(out["outcome"], "fail")
        body = self.backend.find("/fail")[0]["body"]
        self.assertEqual(body["error_kind"], "session_broken")
        self.assertTrue(body["session_broken"])
        self.assertEqual(len(self.claude_calls()), 3)
        self.assertEqual(self.pool_state()["a"]["last_error"], "cli_error")       # JSON with is_error
        # the broken session and the orphan of the failed retry are both deleted
        self.assertEqual(self.session_files("cnv_abc"), [])

    def test_timeout_kills_call_and_fails_timeout(self):
        self.set_fake(mode="sleep", sleep_s=30)
        self.backend.jobs.append(make_job())
        t0 = time.time()
        out = self.runner(claude_timeout_s=1.5).run_once()
        self.assertLess(time.time() - t0, 10)
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(self.backend.find("/fail")[0]["body"]["error_kind"], "timeout")
        self.assertEqual(self.pool_state()["a"].get("status", "ok"), "ok")
        self.assertEqual(self.pool_state()["a"]["last_error"], "timeout")

    def test_heartbeat_cancel_kills_call_and_posts_nothing(self):
        self.set_fake(mode="sleep", sleep_s=30)
        self.backend.heartbeat_response = {"lease_until": 0, "stale": False, "cancel": True,
                                           "cancel_reason": "takeover"}
        self.backend.jobs.append(make_job())
        t0 = time.time()
        out = self.runner().run_once()
        self.assertLess(time.time() - t0, 10)
        self.assertEqual(out["outcome"], "cancelled")
        self.assertEqual(out["cancel_reason"], "takeover")
        self.assertEqual(self.backend.find("/draft") + self.backend.find("/fail"), [])
        self.assertGreaterEqual(len(self.backend.find("/heartbeat")), 1)

    def test_lease_lost_on_heartbeat_cancels(self):
        self.set_fake(mode="sleep", sleep_s=30)
        self.backend.heartbeat_status = 409
        self.backend.heartbeat_response = {"error": {"code": "lease_expired", "message": "late"}}
        self.backend.jobs.append(make_job())
        out = self.runner().run_once()
        self.assertEqual((out["outcome"], out["cancel_reason"]), ("cancelled", "lease_lost"))
        self.assertEqual(self.backend.find("/draft") + self.backend.find("/fail"), [])

    def test_empty_output_and_refusal(self):
        self.set_fake(mode="empty")
        self.backend.jobs.append(make_job("job_e"))
        self.runner().run_once()
        self.assertEqual(self.backend.find("/fail")[0]["body"]["error_kind"], "empty_output")
        self.assertEqual(self.session_files("cnv_abc"), [])   # orphan of a failed new session removed
        self.set_fake(mode="refusal")
        self.backend.jobs.append(make_job("job_f"))
        self.runner().run_once()
        self.assertEqual(self.backend.find("/fail")[1]["body"]["error_kind"], "refusal")

    def test_server_reset_drops_old_session_files(self):
        r = self.runner()
        self.backend.jobs.append(make_job("job_1"))
        r.run_once()
        old = self.backend.find("/draft")[0]["body"]["session_id"]
        self.assertEqual([p.stem for p in self.session_files("cnv_abc")], [old])
        hist = [{"source": "customer", "text": "chào em", "at": 1762400000000}]
        self.backend.jobs.append(make_job("job_2", session_id=None, reason="released_by_staff", history=hist))
        r.run_once()
        new = self.backend.find("/draft")[1]["body"]["session_id"]
        self.assertNotEqual(new, old)
        self.assertEqual([p.stem for p in self.session_files("cnv_abc")], [new])
        self.assertFalse((self.session_files("cnv_abc")[0].parent / old).exists())
        self.assertIn("<conversation_so_far>", self.claude_calls()[1]["text"])
        self.assertIsNone(self.backend.find("/draft")[1]["body"]["error_kind"])

    def test_room_session_from_the_server_starts_a_new_session(self):
        # The last draft of this conversation came from a two-bot room (THOMHOUSE_DRAFT_ENGINE was rooms):
        # claude -p cannot resume "room.<cnv_id>", so the direct engine starts a new session and says so.
        r = self.runner()
        self.backend.jobs.append(make_job("job_room", session_id="room.cnv_abc"))
        out = r.run_once()
        self.assertEqual(out["outcome"], "draft")
        calls = self.claude_calls()
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--resume", calls[0]["flags"])
        self.assertIn("This is a new session", calls[0]["text"])
        body = self.backend.find("/draft")[0]["body"]
        self.assertEqual(body["error_kind"], "session_restarted")
        self.assertFalse(body["session_id"].startswith("room."))

    def test_runner_ages_session_after_20_customer_messages(self):
        r = self.runner()
        self.backend.jobs.append(make_job("job_1", texts=tuple(f"tin {i}" for i in range(20))))
        r.run_once()
        sid = self.backend.find("/draft")[0]["body"]["session_id"]
        self.backend.jobs.append(make_job("job_2", session_id=sid))
        r.run_once()
        self.assertNotIn("--resume", self.claude_calls()[1]["flags"])
        body = self.backend.find("/draft")[1]["body"]
        self.assertEqual(body["error_kind"], "session_restarted")
        self.assertNotEqual(body["session_id"], sid)
        self.assertNotIn(sid, [p.stem for p in self.session_files("cnv_abc")])

    def test_prompt_refetched_when_hash_changes(self):
        r = self.runner()
        self.backend.jobs.append(make_job("job_1"))
        r.run_once()
        self.backend.jobs.append(make_job("job_2", cid="cnv_other"))
        r.run_once()
        self.assertEqual(len(self.backend.find("/runner/prompt", "GET")), 1)
        self.backend.prompt_hash = "h2"
        self.backend.jobs.append(make_job("job_3", cid="cnv_third", prompt_hash="h2"))
        r.run_once()
        self.assertEqual(len(self.backend.find("/runner/prompt", "GET")), 2)
        self.assertIn("BOT SYSTEM PROMPT h2", self.claude_calls()[2]["system_prompt"])

    def test_missing_claude_binary_fails_internal(self):
        import os
        os.environ["PATH"] = "/nonexistent"
        self.backend.jobs.append(make_job())
        out = self.runner().run_once()
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(self.backend.find("/fail")[0]["body"]["error_kind"], "internal")


class PoolStatusRedactionTest(RunnerTestCase):
    # what a failing call can print: the transcript echoes customer text (synthetic here)
    CUSTOMER_TEXT = '{"result": "Dạ chị Lan 0912345678 bị đau lưng ạ"}'

    def mode(self, name: str) -> int:
        return stat.S_IMODE((self.home / name).stat().st_mode)

    def test_pool_status_reports_only_the_error_kind(self):
        r = Runner(self.config())
        pool = r.claude.pool
        label = pool.accounts()[0]["label"]
        pool._set_state(label, last_error=self.CUSTOMER_TEXT)
        self.assertEqual(self.pool_state()[label]["last_error"], "cli_error")
        snap = r.claude.pool_snapshot()
        acc = next(a for a in snap["accounts"] if a["label"] == label)
        self.assertEqual(acc["last_error"], "cli_error")
        self.assertNotIn("0912345678", json.dumps(snap, ensure_ascii=False))
        pool._set_state(label, last_error="You've hit your usage limit · resets 5pm")
        self.assertEqual(self.pool_state()[label]["last_error"], "limited")
        acc = next(a for a in r.claude.pool_snapshot()["accounts"] if a["label"] == label)
        self.assertEqual(acc["last_error"], "limited")
        self.assertNotIn("0912345678", (self.home / "account-state.json").read_text(encoding="utf-8"))

    def test_raw_text_left_by_an_older_version_is_reported_and_rewritten_as_a_kind(self):
        r = Runner(self.config())
        old = {"a": {"status": "ok", "last_error": self.CUSTOMER_TEXT},
               "b": {"status": "login_expired", "last_error": "API Error: 401 Unauthorized"}}
        (self.home / "account-state.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        os.chmod(self.home / "account-state.json", 0o644)
        snap = r.claude.pool_snapshot()
        self.assertEqual({a["label"]: a["last_error"] for a in snap["accounts"]},
                         {"a": "cli_error", "b": "login_expired"})
        self.assertNotIn("0912345678", json.dumps(snap, ensure_ascii=False))
        # the next write of the state file (any account) reduces every entry to its kind
        r.claude.use_account("a")
        st = self.pool_state()
        self.assertEqual((st["a"]["last_error"], st["b"]["last_error"]), ("cli_error", "login_expired"))
        self.assertIs(st["a"]["pinned"], True)
        self.assertEqual(st["b"]["status"], "login_expired")
        self.assertNotIn("0912345678", (self.home / "account-state.json").read_text(encoding="utf-8"))
        self.assertEqual(self.mode("account-state.json"), 0o600)

    def test_state_files_are_private_and_written_atomically(self):
        r = Runner(self.config())
        pool = r.claude.pool
        pool._set_state("a", status="ok")
        with redirect_stdout(io.StringIO()):
            pool.cmd_toggle("b", False)
        self.assertEqual((self.mode("account-state.json"), self.mode("accounts.json")), (0o600, 0o600))
        self.assertEqual(sorted(p.name for p in self.home.iterdir() if p.name.endswith(".tmp")), [])
        self.assertIs(next(a for a in pool.accounts() if a["label"] == "b")["enabled"], False)
        self.assertEqual(pool.error_kind(""), "")
        for kind in pool.ERROR_KINDS:
            self.assertEqual(pool.error_kind(kind), kind)
        self.assertEqual(pool.error_kind("HTTP 429 Too Many Requests"), "limited")
        self.assertEqual(pool.error_kind("status=403"), "blocked")
        self.assertEqual(pool.error_kind("No conversation found with session ID: x"), "cli_error")


if __name__ == "__main__":
    unittest.main()
