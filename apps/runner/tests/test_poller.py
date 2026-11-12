"""Claim loop: concurrency cap, backoff, status reporting with manual account switch, graceful shutdown."""

import json
import threading
import time
import unittest

from tests.helpers import RunnerTestCase, make_job

from runner.api import ApiClient, ServerUnavailable
from runner.poller import Backoff, Runner


class PollerTest(RunnerTestCase):
    def test_runs_jobs_concurrently_up_to_cap(self):
        self.set_fake(mode="sleep", sleep_s=1.0)
        for i in range(4):
            self.backend.jobs.append(make_job(f"job_{i}", cid=f"cnv_{i}"))
        r = Runner(self.config(max_concurrency=2))
        t0 = time.time()
        self.assertEqual(r.run_forever(max_jobs=4), 4)
        elapsed = time.time() - t0
        self.assertEqual(len(self.backend.find("/draft")), 4)
        # 4 jobs of ~1 s with 2 slots: about 2 s, clearly less than serial (4 s)
        self.assertGreater(elapsed, 1.8)
        self.assertLess(elapsed, 3.8)
        cwds = {c["cwd"].rsplit("/", 1)[1] for c in self.claude_calls()}
        self.assertEqual(cwds, {"cnv_0", "cnv_1", "cnv_2", "cnv_3"})

    def test_status_report_applies_desired_account(self):
        r = Runner(self.config())
        self.backend.desired_account = "b"
        resp = r.report_status(with_login=True)
        self.assertEqual(resp["desired_account"], "b")
        self.assertEqual(r.applied_desired_account, "b")
        st = self.pool_state()
        self.assertTrue(st["b"]["pinned"])
        posts = self.backend.find("/runner/status")
        self.assertEqual(len(posts), 2)                    # report, switch, report again
        first, second = posts[0]["body"], posts[1]["body"]
        self.assertEqual(first["applied_desired_account"], "auto")
        self.assertEqual(second["applied_desired_account"], "b")
        self.assertEqual(second["next_account"], "b")
        self.assertEqual(first["accounts"][0]["login"]["email"], "a@example.test")
        self.assertEqual(first["max_concurrency"], 3)
        # the pinned account is used for the next job
        self.backend.jobs.append(make_job())
        r.run_once()
        self.assertEqual(self.backend.find("/draft")[0]["body"]["account_label"], "b")
        # unknown label: not applied, not retried every report
        self.backend.desired_account = "ghost"
        r.report_status(with_login=False)
        r.report_status(with_login=False)
        self.assertEqual(r.applied_desired_account, "b")
        # back to auto
        self.backend.desired_account = "auto"
        r.report_status(with_login=False)
        self.assertEqual(r.applied_desired_account, "auto")
        self.assertFalse(any(v.get("pinned") for v in self.pool_state().values()))

    def test_graceful_shutdown_lets_running_job_finish(self):
        self.set_fake(mode="sleep", sleep_s=1.0)
        self.backend.jobs.append(make_job())
        r = Runner(self.config())
        th = threading.Thread(target=r.run_forever)
        th.start()
        deadline = time.time() + 5
        while not self.claude_calls() and time.time() < deadline:
            time.sleep(0.05)
        r.stop.set()                     # first signal
        th.join(15)
        self.assertFalse(th.is_alive())
        self.assertEqual(len(self.backend.find("/draft")), 1)

    def test_forced_shutdown_kills_and_posts_cancelled(self):
        self.set_fake(mode="sleep", sleep_s=30)
        self.backend.jobs.append(make_job())
        r = Runner(self.config())
        th = threading.Thread(target=r.run_forever)
        th.start()
        deadline = time.time() + 5
        while not self.claude_calls() and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        r.stop.set()
        r.cancel_all("shutdown")         # second signal
        th.join(15)
        self.assertFalse(th.is_alive())
        fails = self.backend.find("/fail")
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0]["body"]["error_kind"], "cancelled")
        self.assertEqual(self.backend.find("/draft"), [])

    def test_server_down_backs_off(self):
        api = ApiClient("http://127.0.0.1:9", "t", "r", timeout=1)
        with self.assertRaises(ServerUnavailable):
            api.claim()
        b = Backoff(1.0, 60.0)
        self.assertEqual([b.next() for _ in range(8)], [1, 2, 4, 8, 16, 32, 60, 60])
        b.reset()
        self.assertEqual(b.next(), 1)
        cfg = self.config(server_url="http://127.0.0.1:9")
        r = Runner(cfg)
        waits = []
        orig = r.stop.wait

        def fake_wait(t):
            waits.append(t)
            if len(waits) >= 3:
                r.stop.set()
            return orig(0)
        r.stop.wait = fake_wait
        r.run_forever()
        self.assertEqual(waits[:3], [1.0, 2.0, 4.0])

    def test_wrong_token_is_reported_not_crashing(self):
        r = Runner(self.config(runner_token="wrong"))
        from runner.contract import ApiError
        with self.assertRaises(ApiError) as ctx:
            r.run_once()
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, "unauthorized"))

    def test_main_once_cli(self):
        import os
        import subprocess
        import sys
        from pathlib import Path
        app = Path(__file__).resolve().parent.parent
        self.backend.jobs.append(make_job())
        env = {**os.environ, "SERVER_URL": self.backend.url, "RUNNER_TOKEN": "test-runner-token",
               "RUNNER_ID": "test-runner", "THOMHOUSE_BOT_HOME": str(self.home)}
        p = subprocess.run([sys.executable, "-m", "runner.main", "once"], cwd=app, env=env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual((out["job_id"], out["outcome"]), ("job_1", "draft"))
        self.assertNotIn("gội đầu", p.stdout + p.stderr)           # no message text in output or logs
        self.assertNotIn("test-runner-token", p.stdout + p.stderr)
        p = subprocess.run([sys.executable, "-m", "runner.main", "status"], cwd=app, env=env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"posted": true', p.stdout)


if __name__ == "__main__":
    unittest.main()
