import threading
import time
import unittest

from bridge.journal import Journal
from bridge.poller import Bridge
from tests.helpers import BRIDGE_ID, TOKEN, BridgeTestCase


class PollerTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.start_server()

    def bridge(self, **kw) -> Bridge:
        b = Bridge(self.cfg(**kw))
        b.report_backoff = (0.05, 0.1)
        return b

    def test_sent_item_is_reported_once(self):
        rid = self.server.enqueue("Dạ em chào anh/chị ạ")
        b = self.bridge()
        out = b.run_once()
        self.assertEqual((out["id"], out["status"], out["sent_now"]), (rid, "sent", True))
        row = self.server.row(rid)
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["zalo_msg_id"], self.sent()[0]["msgId"])
        self.assertEqual(len(self.server.results(rid)), 1)
        self.assertEqual(self.server.results(rid)[0]["body"],
                         {"status": "sent", "zalo_msg_id": row["zalo_msg_id"], "attempt": 1})
        self.assertEqual(b.run_once(), {"status": "idle"})
        self.assertEqual(len(self.send_calls()), 1)
        self.assertEqual(len(self.server.results(rid)), 1)

    def test_split_send_result_carries_part_ids_also_when_reposted_from_the_journal(self):
        self.write_fake(send="ok_split")
        self.server.result_fail_times = 1           # first result POST is lost, posted again from the journal
        rid = self.server.enqueue("x" * 50)
        b = self.bridge()
        self.assertEqual(b.run_once()["status"], "sent")
        bodies = [r["body"] for r in self.server.results(rid)]
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertEqual(body["part_msg_ids"], ["1", "3"])

    def test_every_request_carries_auth_bridge_id_and_user_agent(self):
        self.server.enqueue()
        self.bridge().run_once()
        reqs = [r for r in self.server.requests if r["path"] != "/health"]
        self.assertTrue(reqs)
        for r in reqs:
            self.assertEqual(r["auth"], f"Bearer {TOKEN}")
            self.assertEqual(r["bridge_id"], BRIDGE_ID)
            self.assertEqual(r["ua"], "thomhouse-bridge/1.0")

    def test_unknown_is_never_resent_even_if_handed_out_again(self):
        self.write_fake(send="timeout", sleep_s=20)
        rid = self.server.enqueue()
        b = self.bridge(send_timeout_s=1)
        self.assertEqual(b.run_once()["status"], "unknown")
        self.assertEqual(self.server.row(rid)["status"], "unknown")
        self.assertEqual(b.run_once(), {"status": "idle"})
        # The server hands the same row out again (lease ran out before the result, or a bug): no second send.
        self.write_fake(send="ok")
        self.server.requeue(rid)
        out = b.run_once()
        self.assertEqual((out["status"], out["sent_now"], out["replayed"]), ("unknown", False, True))
        self.assertEqual(len(self.send_calls()), 1)
        self.assertEqual(self.sent(), [])
        self.assertEqual([(r["body"]["status"], r["body"]["attempt"]) for r in self.server.results(rid)],
                         [("unknown", 1), ("unknown", 2)])

    def test_unknown_row_requeued_by_staff_is_sent_again_once(self):
        self.write_fake(send="timeout", sleep_s=20)
        rid = self.server.enqueue()
        b = self.bridge(send_timeout_s=1)
        self.assertEqual(b.run_once()["status"], "unknown")
        time.sleep(0.01)
        # Staff checked the phone, saw nothing arrived and pressed requeue: attempts restart at 1.
        self.write_fake(send="ok")
        self.server.requeue(rid, by_staff=True)
        out = b.run_once()
        self.assertEqual((out["status"], out["sent_now"]), ("sent", True))
        self.assertEqual(len(self.sent()), 1)
        self.assertEqual(self.server.row(rid)["status"], "sent")
        self.assertEqual([(r["body"]["status"], r["body"]["attempt"]) for r in self.server.results(rid)],
                         [("unknown", 1), ("sent", 1)])
        # The same claim handed out again later (result lost) is re-reported, not sent a second time.
        self.server.requeue(rid)
        out = b.run_once()
        self.assertEqual((out["status"], out["replayed"]), ("sent", True))
        self.assertEqual(len(self.sent()), 1)

    def test_sent_row_handed_out_again_is_rereported_not_resent(self):
        rid = self.server.enqueue()
        b = self.bridge()
        b.run_once()
        self.server.requeue(rid)
        out = b.run_once()
        self.assertEqual((out["status"], out["replayed"]), ("sent", True))
        self.assertEqual(len(self.sent()), 1)
        bodies = [r["body"] for r in self.server.results(rid)]
        self.assertEqual(bodies[0]["zalo_msg_id"], bodies[1]["zalo_msg_id"])
        self.assertEqual([x["attempt"] for x in bodies], [1, 2])

    def test_result_retry_after_server_error_does_not_resend(self):
        rid = self.server.enqueue()
        self.server.result_fail_times = 2
        out = self.bridge().run_once()
        self.assertTrue(out["reported"])
        self.assertEqual(self.server.row(rid)["status"], "sent")
        self.assertEqual(len(self.server.results(rid)), 3)
        self.assertEqual(len(self.sent()), 1)

    def test_result_lost_by_crash_is_posted_by_next_process(self):
        rid = self.server.enqueue()
        b = self.bridge()
        self.server.result_fail_times = 100
        b.stop.set()                                  # stopping: report gives up after 5 tries
        item = self.server.route("POST", "/bridge/outbox/claim", {}, BRIDGE_ID)[1]["item"]
        res = b.process_item(item)
        self.assertFalse(res["reported"])
        self.server.result_fail_times = 0
        b2 = self.bridge()                            # a new process reads the same journal
        self.assertEqual(b2.run_once(), {"status": "idle"})
        self.assertEqual(self.server.row(rid)["status"], "sent")
        self.assertEqual(len(self.sent()), 1)

    def test_stale_result_is_refused_then_reposted_with_the_new_attempt(self):
        self.write_fake(send="timeout", sleep_s=20)
        rid = self.server.enqueue()
        b = self.bridge(send_timeout_s=1)
        self.server.result_fail_times = 100           # server down while the bridge stops
        b.stop.set()
        item = self.server.route("POST", "/bridge/outbox/claim", {}, BRIDGE_ID)[1]["item"]
        self.assertFalse(b.process_item(item)["reported"])
        self.server.result_fail_times = 0
        self.server.expire_lease(rid)
        self.server.route("POST", "/bridge/outbox/claim", {}, BRIDGE_ID)   # attempt 2 leased, then lost too
        self.server.expire_lease(rid)
        self.write_fake(send="ok")
        b2 = self.bridge()
        out = b2.run_once()                           # flush: attempt 1 refused (stale); claim: attempt 3 replayed
        self.assertEqual((out["status"], out["replayed"], out["reported"]), ("unknown", True, True))
        self.assertEqual(self.server.row(rid)["status"], "unknown")
        self.assertEqual(len(self.send_calls()), 1)
        self.assertEqual(self.sent(), [])

    def test_group_thread_item_is_failed_without_sending(self):
        rid = self.server.enqueue(thread_type=1)
        out = self.bridge().run_once()
        self.assertEqual(out["status"], "failed")
        self.assertTrue(self.server.row(rid)["error"].startswith("invalid_item"))
        self.assertEqual(self.send_calls(), [])

    def test_idle_poll_follows_server_poll_after_ms(self):
        b = self.bridge()
        t = threading.Thread(target=b.run_forever, daemon=True)
        t.start()
        time.sleep(0.8)
        b.stop.set()
        t.join(5)
        claims = [r for r in self.server.requests if r["path"] == "/bridge/outbox/claim"]
        self.assertEqual(len(claims), 1)

    def test_crash_mid_send_is_reported_unknown_and_never_sent(self):
        rid = self.server.enqueue()
        self.server.route("POST", "/bridge/outbox/claim", {}, BRIDGE_ID)
        Journal(self.cfg().state_dir).record(rid, status="sending", attempt=1, reported=False)
        out = self.bridge().run_once()
        self.assertEqual(out, {"status": "idle"})
        self.assertEqual(self.server.row(rid)["status"], "unknown")
        self.assertTrue(self.server.row(rid)["error"].startswith("bridge_restarted"))
        self.assertEqual(self.send_calls(), [])

    def test_failed_rows_are_sent_again_on_each_server_retry(self):
        self.write_fake(send="zalo_error")
        rid = self.server.enqueue()
        b = self.bridge()
        for _ in range(4):
            self.assertEqual(b.run_once()["status"], "failed")
        self.assertEqual(self.server.row(rid)["status"], "failed")
        self.assertEqual(b.run_once(), {"status": "idle"})
        self.assertEqual(len(self.send_calls()), 4)
        self.assertEqual([r["body"]["attempt"] for r in self.server.results(rid)], [1, 2, 3, 4])

    def test_not_logged_in_pauses_claiming(self):
        self.write_fake(logged_in=False)
        rid = self.server.enqueue()
        b = self.bridge(login_pause_s=60)
        self.assertEqual(b.run_once()["status"], "failed")
        self.assertTrue(self.server.row(rid)["error"].startswith("not_logged_in"))
        self.assertGreater(b.pause_until - time.monotonic(), 50)

    def test_run_forever_paces_sends_and_stops_on_signal_flag(self):
        for i in range(2):
            self.server.enqueue(f"tin {i}")
        b = self.bridge(send_min_interval_s=0.6)
        t = threading.Thread(target=b.run_forever, daemon=True)
        t.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and len(self.server.results()) < 2:
            time.sleep(0.05)
        b.stop.set()
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertEqual([self.server.row(r["id"])["status"] for r in self.server.rows], ["sent", "sent"])
        self.assertEqual(len(self.server.results()), 2)
        self.assertEqual(len(self.sent()), 2)

    def test_pacing_gap_between_sends(self):
        for i in range(2):
            self.server.enqueue(f"tin {i}")
        b = self.bridge(send_min_interval_s=0.8)
        times: list[float] = []
        real_send = b.sender.send

        def timed_send(*a, **kw):
            times.append(time.monotonic())
            return real_send(*a, **kw)

        b.sender.send = timed_send
        t = threading.Thread(target=b.run_forever, daemon=True)
        t.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and len(times) < 2:
            time.sleep(0.05)
        b.stop.set()
        t.join(10)
        self.assertEqual(len(times), 2)
        self.assertGreaterEqual(times[1] - times[0], 0.8)

    def test_server_down_backs_off_without_crashing(self):
        b = self.bridge()
        b.api.base_url = "http://127.0.0.1:9"
        t = threading.Thread(target=b.run_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        b.stop.set()
        t.join(5)
        self.assertFalse(t.is_alive())


if __name__ == "__main__":
    unittest.main()
