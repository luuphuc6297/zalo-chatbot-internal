"""scripts/simulate_personal_zalo.py must not make a running bridge message a real Zalo user.

The script lives outside the bridge package; it is loaded from its file. A tiny local HTTP server stands in for
GET /bridge/status. Nothing is posted to a webhook and nothing touches Zalo."""

from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bridge.config import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "simulate_personal_zalo.py"


def load_script():
    spec = importlib.util.spec_from_file_location("simulate_personal_zalo", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class StatusServer:
    def __init__(self, last_claim_at):
        self.last_claim_at = last_claim_at
        self.auth: list[str | None] = []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                srv.auth.append(self.headers.get("Authorization"))
                raw = json.dumps({"last_claim_at": srv.last_claim_at, "counts": {}}).encode()
                self.send_response(200 if self.path == "/bridge/status" else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.webhook = f"http://127.0.0.1:{self.httpd.server_address[1]}/zalo/personal/webhook"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class SimulateGuardTests(unittest.TestCase):
    def setUp(self):
        self.sim = load_script()
        self._env = dict(os.environ)
        os.environ["STAFF_TOKEN"] = "test-staff-token"     # never read apps/server/.dev.vars in tests

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def body(self, thread: str) -> bytes:
        return self.sim.build_body(self.parse(["--thread", thread, "--text", "chào shop"]))

    def parse(self, argv):
        # The namespace build_body() reads; main() would also post, so it is built here.
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--thread", default=self.sim.DEFAULT_THREAD)
        p.add_argument("--text", action="append")
        ns = p.parse_args(argv)
        for k, v in dict(name=None, image=None, sticker=False, self_sent=False, msg_id=None, cli_msg_id=None,
                         catch_up=False, group_event=False, group_thread="5550001", group_sender="9100999",
                         reaction=False, batch=False, account_id=self.sim.FAKE_OWN_ID).items():
            setattr(ns, k, v)
        return ns

    def test_default_thread_is_not_numeric_so_no_bridge_can_send_to_it(self):
        self.assertFalse(self.sim.NUMERIC_RE.match(self.sim.DEFAULT_THREAD))
        body = self.body(self.sim.DEFAULT_THREAD)
        # unreachable server: still fine, no status lookup is needed for a non-numeric id
        self.assertIsNone(self.sim.guard_real_sends("http://127.0.0.1:9/zalo/personal/webhook", body, False))

    def test_numeric_thread_is_refused_while_a_bridge_claims(self):
        st = StatusServer(last_claim_at=int(time.time() * 1000) - 5_000)
        try:
            msg = self.sim.guard_real_sends(st.webhook, self.body("9162891863420"), False)
            self.assertIsNotNone(msg)
            self.assertIn("refused", msg)
            self.assertNotIn("9162891863420", msg)          # the id is masked in the message
            self.assertEqual(st.auth, ["Bearer test-staff-token"])
            self.assertIsNone(self.sim.guard_real_sends(st.webhook, self.body("9162891863420"), True))
            # a batch with a numeric DM thread is checked too (replayed bodies)
            batch = json.dumps({"event": "batch", "events": [{"event": "message", "type": 0, "threadId": "9100123"}]}).encode()
            self.assertIsNotNone(self.sim.guard_real_sends(st.webhook, batch, False))
        finally:
            st.close()

    def test_numeric_thread_is_allowed_when_no_bridge_claimed_recently(self):
        st = StatusServer(last_claim_at=int(time.time() * 1000) - 10 * 60_000)
        try:
            self.assertIsNone(self.sim.guard_real_sends(st.webhook, self.body("9162891863420"), False))
        finally:
            st.close()

    def test_numeric_thread_is_refused_when_the_status_cannot_be_read(self):
        msg = self.sim.guard_real_sends("http://127.0.0.1:9/zalo/personal/webhook", self.body("9162891863420"), False)
        self.assertIsNotNone(msg)

    def test_main_exits_3_without_posting(self):
        code = self.sim.main(["--url", "http://127.0.0.1:9/zalo/personal/webhook", "--secret", "s",
                              "--thread", "9162891863420", "--text", "hi"])
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
