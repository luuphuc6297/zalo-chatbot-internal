import os
import time
import unittest

from bridge.engine import EngineResult, parse_json_output
from bridge.sender import Sender, classify
from tests.helpers import THREAD, BridgeTestCase


class SenderTests(BridgeTestCase):
    def test_success_returns_msg_id_with_safe_argv_and_env(self):
        os.environ["RUNNER_TOKEN"] = "must-not-reach-engine"
        os.environ["ZALO_PERSONAL_WEBHOOK_SECRET"] = "must-not-reach-engine"
        os.environ["ZALO_SEND_FORMAT"] = "markdown"
        out = Sender(self.cfg()).send(THREAD, "Dạ giá gội đầu là 350.000đ ạ")
        self.assertEqual(out.status, "sent")
        self.assertEqual(out.zalo_msg_id, self.sent()[0]["msgId"])
        self.assertIsInstance(out.zalo_msg_id, str)
        call = self.send_calls()[0]
        self.assertEqual(call["argv"], ["--json", "msg", "send", "-t", "0", "--", THREAD,
                                        "Dạ giá gội đầu là 350.000đ ạ"])
        self.assertTrue(call["stdin_devnull"])
        self.assertFalse(call["env"]["runner_token"])
        self.assertFalse(call["env"]["personal_secret"])
        self.assertIsNone(call["env"]["send_format"])
        self.assertIsNone(call["env"]["webhook_secret_sha"])
        self.assertEqual(call["env"]["no_update_check"], "1")

    def test_account_is_pinned_when_configured(self):
        Sender(self.cfg(zalo_account="1000000000000001")).send(THREAD, "hi")
        argv = self.send_calls()[0]["argv"]
        self.assertEqual(argv[:3], ["--json", "--account", "1000000000000001"])
        self.assertEqual(self.sent()[0]["account"], "1000000000000001")

    def test_text_starting_with_dash_stays_text(self):
        text = "- Gội đầu: 350.000đ\n- Massage: 500.000đ"
        out = Sender(self.cfg()).send(THREAD, text)
        self.assertEqual(out.status, "sent")
        self.assertEqual(self.sent()[0]["text"], text)

    def test_split_send_is_sent_with_first_msg_id(self):
        self.write_fake(send="ok_split")
        out = Sender(self.cfg()).send(THREAD, "x" * 50)
        self.assertEqual(out.status, "sent")
        self.assertTrue(out.zalo_msg_id)

    def test_split_send_reports_every_part_msg_id(self):
        self.write_fake(send="ok_split")
        out = Sender(self.cfg()).send(THREAD, "x" * 50)
        self.assertEqual(out.part_msg_ids, ["1", "3"])
        self.assertEqual(out.result_body()["part_msg_ids"], ["1", "3"])
        single = Sender(self.cfg())
        self.write_fake(send="ok")
        self.assertNotIn("part_msg_ids", single.send(THREAD, "hi").result_body())

    def test_not_logged_in_is_failed_and_asks_for_login(self):
        self.write_fake(logged_in=False)
        out = Sender(self.cfg()).send(THREAD, "hi")
        self.assertEqual(out.status, "failed")
        self.assertTrue(out.login_required)
        self.assertTrue(out.error.startswith("not_logged_in"))

    def test_timeout_is_unknown_and_process_is_killed(self):
        self.write_fake(send="timeout", sleep_s=20)
        t0 = time.monotonic()
        out = Sender(self.cfg(send_timeout_s=1)).send(THREAD, "hi")
        self.assertEqual(out.status, "unknown")
        self.assertTrue(out.error.startswith("timeout"))
        self.assertLess(time.monotonic() - t0, 8)

    def test_garbled_output_is_unknown(self):
        self.write_fake(send="garbled")
        out = Sender(self.cfg()).send(THREAD, "hi")
        self.assertEqual((out.status, out.error.split(":")[0]), ("unknown", "garbled_output"))

    def test_crash_without_json_is_unknown(self):
        self.write_fake(send="crash")
        self.assertEqual(Sender(self.cfg()).send(THREAD, "hi").status, "unknown")

    def test_zalo_error_answer_is_failed(self):
        self.write_fake(send="zalo_error")
        out = Sender(self.cfg()).send(THREAD, "hi")
        self.assertEqual((out.status, out.login_required), ("failed", False))
        self.assertTrue(out.error.startswith("zalo_error"))

    def test_transport_error_is_unknown(self):
        self.write_fake(send="transport")
        self.assertEqual(Sender(self.cfg()).send(THREAD, "hi").status, "unknown")

    def test_partial_split_send_is_unknown(self):
        self.write_fake(send="partial")
        out = Sender(self.cfg()).send(THREAD, "hi")
        self.assertEqual((out.status, out.error.split(":")[0]), ("unknown", "partial_send"))

    def test_usage_error_is_failed(self):
        self.write_fake(send="usage")
        out = Sender(self.cfg()).send(THREAD, "hi")
        self.assertEqual((out.status, out.error.split(":")[0]), ("failed", "cli_usage"))

    def test_missing_binary_is_failed(self):
        out = Sender(self.cfg(zalo_agent_bin=str(self.tmp / "nope"))).send(THREAD, "hi")
        self.assertEqual((out.status, out.error.split(":")[0]), ("failed", "engine_missing"))

    def test_invalid_thread_or_empty_text_never_runs_engine(self):
        s = Sender(self.cfg())
        for thread, text in (("me", "hi"), ("--help", "hi"), (THREAD, "  "), (None, "hi")):
            self.assertEqual(s.send(thread, text).status, "failed")
        self.assertEqual(self.calls(), [])


class ClassifyTests(unittest.TestCase):
    def test_parse_tolerates_stray_lines(self):
        self.assertEqual(parse_json_output('warn line\n{\n  "message": {"msgId": 5}\n}\n'), {"message": {"msgId": 5}})
        self.assertIsNone(parse_json_output("  ✓ Message sent"))

    def test_success_json_with_nonzero_exit_is_still_sent(self):
        r = EngineResult(argv_tail=[], returncode=1, data={"message": {"msgId": 9}})
        self.assertEqual(classify(r).status, "sent")

    def test_json_without_msg_id_is_unknown(self):
        r = EngineResult(argv_tail=[], returncode=0, data={"message": None, "attachment": []})
        self.assertEqual(classify(r).status, "unknown")

    def test_errors_raised_after_zalo_answered_are_unknown_not_failed(self):
        # zca-js handleZaloResponse: Zalo got the request (HTTP 200 with an undecodable body, or a 5xx), so the
        # message may be delivered; "failed" would make the server send it again.
        for err in ("Failed to parse response data", "Request failed with status code 502",
                    "Request failed with status code 500"):
            out = classify(EngineResult(argv_tail=[], returncode=0, data={"error": err}))
            self.assertEqual((out.status, out.error.split(":")[0]), ("unknown", "transport_error"), err)
        refused = classify(EngineResult(argv_tail=[], returncode=0, data={"error": "Request failed with status code 404"}))
        self.assertEqual(refused.status, "failed")


if __name__ == "__main__":
    unittest.main()
