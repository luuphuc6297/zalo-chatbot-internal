"""Label sync (bridge/labels.py, docs/contracts.md 14.3): fake engine, fake server, synthetic ids and labels."""

import contextlib
import io
import logging
import threading
import time
import unittest
from unittest import mock

from bridge import labels
from bridge import main as bridge_main
from bridge.api import StaffApi
from bridge.labels import LabelSyncError, normalize_label, roles_from_labels, staff_token, sync_labels
from bridge.poller import Bridge
from tests.helpers import STAFF_TOKEN, TOKEN, BridgeTestCase

# Fake Zalo ids (never real accounts).
C1, C2, C3 = "2000000000000011", "2000000000000012", "2000000000000013"
M1, S1, BOTH = "2000000000000021", "2000000000000031", "2000000000000041"
GROUP = "g3000000000000051"
FIXTURE = [
    {"text": "  KHÁCH   Hàng ", "conversations": [C1, C2, GROUP, BOTH, C1]},
    {"text": "Quản lý", "conversations": [M1, BOTH]},
    {"text": "nhân viên", "conversations": [S1, BOTH, C2]},
    {"text": "Bạn thân", "conversations": [C3, "2000000000000099"]},
]
EXPECTED_ROLES = [
    {"zalo_user_id": f"p:{M1}", "role": "manager"},
    {"zalo_user_id": f"p:{BOTH}", "role": "manager"},
    {"zalo_user_id": f"p:{C2}", "role": "staff"},
    {"zalo_user_id": f"p:{S1}", "role": "staff"},
    {"zalo_user_id": f"p:{C1}", "role": "customer"},
]
# Nothing of the fixture may reach stdout, stderr or a log line.
PRIVATE = [C1, C2, C3, M1, S1, BOTH, GROUP, GROUP[1:], "2000000000000099", "KHÁCH", "Hàng", "Quản", "nhân viên",
           "Bạn thân", "khach", "quan ly", "nhan vien", "ban than"]


def doc(labels_):
    return {"labelData": [{"id": n + 1, "color": "#77D9A0", "emoji": "", "offset": n, "createTime": 1, **x}
                          for n, x in enumerate(labels_)], "version": 3, "lastUpdateTime": 2}


class NormalizeTests(unittest.TestCase):
    def test_accents_case_spaces_and_d_bar(self):
        for raw in ("Khách hàng", "KHÁCH HÀNG", "  khách   hàng ", "Khách hàng", "khach hang",
                    "Khách\thàng"):
            self.assertEqual(normalize_label(raw), "khach hang", raw)
        self.assertEqual(normalize_label("Quản lý"), "quan ly")
        self.assertEqual(normalize_label("QUẢN  LÝ"), "quan ly")
        self.assertEqual(normalize_label("Nhân viên"), "nhan vien")
        self.assertEqual(normalize_label("Đối tác"), "doi tac")
        self.assertEqual(normalize_label("đặt lịch Đêm"), "dat lich dem")

    def test_only_the_three_exact_names_are_roles(self):
        for raw in ("Khách hàng VIP", "Khách", "Quản lý cũ", "Nhân viên mới", "khachhang", "", "Gia đình"):
            roles, counts = roles_from_labels(doc([{"text": raw, "conversations": [C1]}]))
            self.assertEqual(roles, [], raw)
            self.assertEqual(counts["role_labels"], 0)


class MappingTests(unittest.TestCase):
    def test_priority_groups_and_duplicates(self):
        roles, counts = roles_from_labels(doc(FIXTURE))
        self.assertEqual(roles, EXPECTED_ROLES)
        self.assertEqual(counts, {"labels": 4, "role_labels": 3,
                                  "contacts": {"manager": 2, "staff": 2, "customer": 1},
                                  "skipped": {"groups": 1, "other_ids": 0}})

    def test_contact_under_staff_and_customer_is_staff(self):
        roles, _ = roles_from_labels(doc([{"text": "Khách hàng", "conversations": [C1]},
                                          {"text": "Nhân viên", "conversations": [C1]}]))
        self.assertEqual(roles, [{"zalo_user_id": f"p:{C1}", "role": "staff"}])

    def test_two_labels_with_the_same_normalised_name_are_merged(self):
        roles, counts = roles_from_labels(doc([{"text": "Khách hàng", "conversations": [C1]},
                                               {"text": "khach  hang", "conversations": [C2, C1]}]))
        self.assertEqual(roles, [{"zalo_user_id": f"p:{C1}", "role": "customer"},
                                 {"zalo_user_id": f"p:{C2}", "role": "customer"}])
        self.assertEqual(counts["role_labels"], 2)

    def test_ids_that_are_neither_digits_nor_groups_are_skipped_and_counted(self):
        roles, counts = roles_from_labels(doc([{"text": "Khách hàng", "conversations": ["u-abc", "", GROUP, "12a"]}]))
        self.assertEqual(roles, [])
        self.assertEqual(counts["skipped"], {"groups": 1, "other_ids": 3})

    def test_ids_longer_than_the_server_accepts_are_skipped_and_counted(self):
        # The server takes `p:` + 1 to 32 digits (ROLE_ID_RE) and refuses the whole list for a longer id.
        longest, too_long = "1" * 32, "2" * 33
        roles, counts = roles_from_labels(doc([{"text": "Khách hàng", "conversations": [longest, too_long]}]))
        self.assertEqual(roles, [{"zalo_user_id": f"p:{longest}", "role": "customer"}])
        self.assertEqual(counts["skipped"], {"groups": 0, "other_ids": 1})

    def test_empty_label_list_is_a_valid_complete_list(self):
        roles, counts = roles_from_labels({"labelData": [], "version": 1, "lastUpdateTime": 1})
        self.assertEqual(roles, [])
        self.assertEqual(counts["labels"], 0)
        roles, _ = roles_from_labels(doc([{"text": "Khách hàng", "conversations": []}]))
        self.assertEqual(roles, [])

    def test_malformed_documents_are_refused(self):
        bad = [None, [], "x", 3, {"labelData": None}, {"labelData": {}}, {"labelData": ["x"]},
               {"labelData": [{"conversations": [C1]}]}, {"labelData": [{"text": 5, "conversations": [C1]}]},
               doc([{"text": "Khách hàng"}]), doc([{"text": "Khách hàng", "conversations": None}]),
               doc([{"text": "Quản lý", "conversations": C1}]),
               doc([{"text": "Nhân viên", "conversations": [int(C1)]}])]
        for d in bad:
            with self.assertRaises(LabelSyncError, msg=repr(d)) as cm:
                roles_from_labels(d)
            self.assertEqual(cm.exception.code, "malformed_output")
        with self.assertRaises(LabelSyncError) as cm:
            roles_from_labels({"version": 1})
        self.assertEqual(cm.exception.code, "no_label_data")

    def test_a_label_that_is_not_a_role_may_have_any_member_list(self):
        roles, _ = roles_from_labels({"labelData": [{"text": "Bạn thân"}, {"text": "Khách hàng", "conversations": [C1]}]})
        self.assertEqual(roles, [{"zalo_user_id": f"p:{C1}", "role": "customer"}])


class LabelSyncTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.start_server()
        self.write_fake(labels=FIXTURE)
        import os
        os.environ["STAFF_TOKEN"] = STAFF_TOKEN
        os.environ.pop("THOMHOUSE_DEV_VARS", None)

    def label_calls(self):
        return [c for c in self.calls() if c["argv"][-2:] == ["label", "list"]]

    def test_posts_the_complete_list_with_staff_auth(self):
        code, out = sync_labels(self.cfg())
        self.assertEqual(code, 0)
        self.assertEqual(out, {"ok": True, "dry_run": False, "labels": 4, "role_labels": 3,
                               "contacts": {"manager": 2, "staff": 2, "customer": 1},
                               "skipped": {"groups": 1, "other_ids": 0}, "posted": True,
                               "server": {"imported": 5, "updated": 0, "unchanged": 0, "removed": 0, "kept_staff": 0}})
        (req,) = self.server.requests
        self.assertEqual((req["method"], req["path"]), ("POST", "/staff/roles/import"))
        self.assertEqual(req["body"], {"source": "zalo_label", "complete": True, "roles": EXPECTED_ROLES})
        self.assertEqual(req["auth"], f"Bearer {STAFF_TOKEN}")
        self.assertEqual(req["staff_id"], "label-sync")
        self.assertIsNone(req["bridge_id"])
        self.assertEqual(req["ua"], "thomhouse-bridge/1.0")
        (call,) = self.calls()
        self.assertEqual(call["argv"], ["--json", "label", "list"])
        self.assertTrue(call["stdin_devnull"])
        self.assertFalse(call["env"]["staff_token"])     # the engine never sees the staff token
        self.assertFalse(call["env"]["runner_token"])

    def test_account_is_passed_to_the_engine(self):
        sync_labels(self.cfg(zalo_account="1000000000000001"), dry_run=True)
        self.assertEqual(self.calls()[0]["argv"], ["--json", "--account", "1000000000000001", "label", "list"])

    def test_second_sync_reports_changes_and_removals(self):
        self.server.staff_roles[f"p:{S1}"] = "manager"           # set in the console: never overwritten
        self.assertEqual(sync_labels(self.cfg())[1]["server"],
                         {"imported": 4, "updated": 0, "unchanged": 0, "removed": 0, "kept_staff": 1})
        self.write_fake(labels=[{"text": "Khách hàng", "conversations": [C1, M1]}])
        code, out = sync_labels(self.cfg())
        self.assertEqual(code, 0)
        self.assertEqual(out["server"], {"imported": 0, "updated": 1, "unchanged": 1, "removed": 2, "kept_staff": 0})
        self.assertEqual(self.server.label_roles, {f"p:{C1}": "customer", f"p:{M1}": "customer"})

    def test_empty_label_list_is_posted_and_clears_label_roles(self):
        self.server.label_roles[f"p:{C1}"] = "customer"
        self.write_fake(labels=[])
        code, out = sync_labels(self.cfg())
        self.assertEqual(code, 0)
        self.assertEqual(self.server.role_imports()[0]["body"], {"source": "zalo_label", "complete": True, "roles": []})
        self.assertEqual(out["server"]["removed"], 1)
        self.assertEqual(self.server.label_roles, {})

    def test_dry_run_posts_nothing_and_needs_no_token(self):
        import os
        del os.environ["STAFF_TOKEN"]
        code, out = sync_labels(self.cfg(), dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, {"ok": True, "dry_run": True, "labels": 4, "role_labels": 3,
                               "contacts": {"manager": 2, "staff": 2, "customer": 1},
                               "skipped": {"groups": 1, "other_ids": 0}, "posted": False})
        self.assertEqual(self.server.requests, [])
        self.assertEqual(len(self.label_calls()), 1)

    def test_engine_failures_post_nothing(self):
        cases = [({"label_list": "not_logged_in"}, "not_logged_in"), ({"logged_in": False}, "not_logged_in"),
                 ({"label_list": "zalo_error"}, "engine_error"), ({"label_list": "crash"}, "engine_error"),
                 ({"label_list": "garbled"}, "malformed_output"), ({"label_list": "array"}, "malformed_output"),
                 ({"label_list": "no_label_data"}, "no_label_data")]
        for changes, error in cases:
            self.write_fake(label_list="ok", logged_in=True)
            self.write_fake(**changes)
            code, out = sync_labels(self.cfg())
            self.assertEqual((code, out), (1, {"ok": False, "error": error, "posted": False}), changes)
        self.assertEqual(self.server.requests, [])

    def test_malformed_role_label_posts_nothing(self):
        for bad in ([{"text": "Khách hàng", "drop": ["conversations"]}],
                    [{"text": "Khách hàng", "conversations": [C1]}, {"text": "Quản lý", "conversations": None}],
                    [{"text": "Khách hàng", "conversations": [C1]}, "oops"],
                    [{"conversations": [C1], "drop": ["text"]}]):
            self.write_fake(labels=bad)
            code, out = sync_labels(self.cfg())
            self.assertEqual((code, out), (1, {"ok": False, "error": "malformed_output", "posted": False}), bad)
        self.assertEqual(self.server.requests, [])

    def test_engine_timeout_and_missing_engine_post_nothing(self):
        self.write_fake(label_list="timeout", label_sleep_s=20)
        t0 = time.monotonic()
        code, out = sync_labels(self.cfg(), timeout=0.5)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual((code, out), (1, {"ok": False, "error": "engine_timeout", "posted": False}))
        code, out = sync_labels(self.cfg(zalo_agent_bin=str(self.tmp / "no-such-engine")))
        self.assertEqual((code, out), (1, {"ok": False, "error": "engine_missing", "posted": False}))
        self.assertEqual(self.server.requests, [])

    def test_cancel_stops_a_running_engine_call(self):
        self.write_fake(label_sleep_s=20)
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        t0 = time.monotonic()
        code, out = sync_labels(self.cfg(), cancel=cancel)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual((code, out["error"]), (1, "cancelled"))
        self.assertEqual(self.server.requests, [])

    def test_too_many_roles_are_not_posted_in_part(self):
        many = [str(2000000000100000 + n) for n in range(labels.MAX_ROLES + 1)]
        self.write_fake(labels=[{"text": "Khách hàng", "conversations": many}])
        code, out = sync_labels(self.cfg())
        self.assertEqual((code, out["error"], out["posted"]), (1, "too_many_roles", False))
        self.assertEqual(out["contacts"]["customer"], labels.MAX_ROLES + 1)
        self.assertEqual(self.server.requests, [])

    def test_server_refusals_are_reported_by_code(self):
        self.server.roles_import_error = (409, {"error": {"code": "invalid_state", "message": "migration 0010"}})
        code, out = sync_labels(self.cfg())
        self.assertEqual((code, out["ok"], out["error"], out["status"], out["posted"]),
                         (1, False, "invalid_state", 409, False))
        self.server.roles_import_error = (422, {"error": {"code": f"bad id p:{C1}", "message": "x"}})
        code, out = sync_labels(self.cfg())
        self.assertEqual((code, out["error"], out["status"]), (1, "http_error", 422))   # odd codes are not echoed
        self.server.roles_import_error = (503, {})
        code, out = sync_labels(self.cfg())
        self.assertEqual((code, out["error"]), (1, "server_unavailable"))
        code, out = sync_labels(self.cfg(), api=StaffApi(self.server.url, "wrong-token", "label-sync"))
        self.assertEqual((code, out["error"], out["status"]), (1, "unauthorized", 401))

    def test_staff_token_lookup(self):
        import os
        local, remote = "http://127.0.0.1:8787", "https://bot.example.com"
        self.assertEqual(staff_token(local, {"STAFF_TOKEN": " env-token "}), "env-token")
        self.assertEqual(staff_token(remote, {"STAFF_TOKEN": "env-token"}), "env-token")
        dev_vars = self.tmp / "dev.vars"
        dev_vars.write_text('RUNNER_TOKEN=r\nSTAFF_TOKEN="file-token"\n')
        env = {"THOMHOUSE_DEV_VARS": str(dev_vars)}
        self.assertEqual(staff_token(local, env), "file-token")
        self.assertEqual(staff_token("http://thomhouse.localhost:8787", env), "file-token")
        self.assertEqual(staff_token(remote, env), "")           # the local dev token never leaves the machine
        self.assertEqual(staff_token(local, {"THOMHOUSE_DEV_VARS": str(self.tmp / "missing")}), "")
        # No token: the sync reads the labels, posts nothing and reports a config problem.
        del os.environ["STAFF_TOKEN"]
        os.environ["THOMHOUSE_DEV_VARS"] = str(self.tmp / "missing")
        code, out = sync_labels(self.cfg())
        self.assertEqual((code, out["error"], out["posted"]), (2, "no_staff_token", False))
        self.assertEqual(self.server.requests, [])
        # The token of the dev vars file is used when the environment has none.
        dev_vars.write_text(f"STAFF_TOKEN={STAFF_TOKEN}\n")
        os.environ["THOMHOUSE_DEV_VARS"] = str(dev_vars)
        self.assertEqual(sync_labels(self.cfg())[0], 0)
        self.assertEqual(len(self.server.role_imports()), 1)


@contextlib.contextmanager
def logging_enabled():
    """tests/__init__.py silences logging for the whole suite: switch it back on for one block."""
    logging.disable(logging.NOTSET)
    try:
        yield
    finally:
        logging.disable(logging.CRITICAL)


@contextlib.contextmanager
def captured():
    """Everything a command shows: stdout, stderr and every log record of the process."""
    out, err, logs = io.StringIO(), io.StringIO(), io.StringIO()
    handler = logging.StreamHandler(logs)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    box: dict = {}
    try:
        with logging_enabled(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield box
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        box["text"] = out.getvalue() + err.getvalue() + logs.getvalue()
        box["stdout"] = out.getvalue()


class SyncLabelsCommandTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.start_server()
        self.write_fake(labels=FIXTURE)
        import os
        from tests.helpers import FAKE_ENGINE
        # No RUNNER_TOKEN: the command needs the staff token only. The real apps/zalo-bridge/.env is not read.
        for k in ("RUNNER_TOKEN", "ZALO_ACCOUNT", "THOMHOUSE_DEV_VARS", "THOMHOUSE_API_URL"):
            os.environ.pop(k, None)
        os.environ.update({"SERVER_URL": self.server.url, "STAFF_TOKEN": STAFF_TOKEN,
                           "ZALO_AGENT_BIN": str(FAKE_ENGINE), "THOMHOUSE_BOT_HOME": str(self.tmp / "home")})
        patcher = mock.patch("bridge.config.APP_DIR", self.tmp / "no-app-dir")
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_counts_only(self, text: str):
        low = text.lower()
        for secret in PRIVATE + [STAFF_TOKEN, TOKEN]:
            self.assertNotIn(secret.lower(), low)

    def test_sync_prints_counts_only(self):
        with captured() as box:
            code = bridge_main.main(["sync-labels"])
        self.assertEqual(code, 0)
        self.assertIn('"imported": 5', box["stdout"])
        self.assertIn('"customer": 1', box["stdout"])
        self.assertIn('"labels": 4', box["stdout"])
        self.assert_counts_only(box["text"])
        self.assertEqual(self.server.role_imports()[0]["body"]["roles"], EXPECTED_ROLES)

    def test_dry_run_prints_counts_and_posts_nothing(self):
        with captured() as box:
            code = bridge_main.main(["sync-labels", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn('"dry_run": true', box["stdout"])
        self.assertIn('"manager": 2', box["stdout"])
        self.assert_counts_only(box["text"])
        self.assertEqual(self.server.requests, [])

    def test_failures_exit_non_zero_without_engine_text(self):
        for mode, error in (("zalo_error", "engine_error"), ("not_logged_in", "not_logged_in"),
                            ("no_label_data", "no_label_data"), ("garbled", "malformed_output")):
            self.write_fake(label_list=mode)
            with captured() as box:
                code = bridge_main.main(["sync-labels"])
            self.assertEqual(code, 1, mode)
            self.assertIn(f'"error": "{error}"', box["stdout"])
            self.assertNotIn("Tham số", box["text"])
            self.assert_counts_only(box["text"])
        self.assertEqual(self.server.requests, [])

    def test_missing_staff_token_exits_2(self):
        import os
        del os.environ["STAFF_TOKEN"]
        os.environ["THOMHOUSE_DEV_VARS"] = str(self.tmp / "missing")
        with captured() as box:
            code = bridge_main.main(["sync-labels"])
        self.assertEqual(code, 2)
        self.assertIn('"error": "no_staff_token"', box["stdout"])
        self.assertEqual(self.server.requests, [])


class PeriodicLabelSyncTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.start_server()
        self.write_fake(labels=FIXTURE)
        import os
        os.environ["STAFF_TOKEN"] = STAFF_TOKEN

    def bridge(self, **kw) -> Bridge:
        b = Bridge(self.cfg(**kw))
        b.report_backoff = (0.05, 0.1)
        return b

    def label_calls(self):
        return [c for c in self.calls() if c["argv"][-2:] == ["label", "list"]]

    def run_bridge(self, b: Bridge, until, timeout: float = 15.0) -> threading.Thread:
        t = threading.Thread(target=b.run_forever, daemon=True)
        t.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not until():
            time.sleep(0.05)
        return t

    def stop(self, b: Bridge, t: threading.Thread):
        b.stop.set()
        t.join(10)
        self.assertFalse(t.is_alive())
        if b.label_thread is not None:
            b.label_thread.join(10)
            self.assertFalse(b.label_thread.is_alive())

    def test_config_default_and_zero_disables(self):
        from bridge.config import Config
        base = {"RUNNER_TOKEN": "t"}
        self.assertEqual(Config.load(env=base, dotenv=self.tmp / "none").label_sync_every_s, 900.0)
        self.assertEqual(Config.load(env={**base, "LABEL_SYNC_EVERY_S": "0"}, dotenv=self.tmp / "none")
                         .label_sync_every_s, 0.0)
        self.assertEqual(Config.load(env={**base, "LABEL_SYNC_EVERY_S": "120"}, dotenv=self.tmp / "none")
                         .label_sync_every_s, 120.0)
        b = self.bridge()                                  # helpers: label_sync_every_s=0
        self.assertIsNone(b.start_label_sync())
        t = self.run_bridge(b, lambda: False, timeout=0.6)
        self.stop(b, t)
        self.assertEqual(self.label_calls(), [])
        self.assertEqual(self.server.role_imports(), [])

    def test_runs_at_start_and_then_every_period(self):
        b = self.bridge(label_sync_every_s=0.4)
        with logging_enabled(), self.assertLogs("bridge", level="INFO") as logs:
            t = self.run_bridge(b, lambda: len(self.server.role_imports()) >= 3)
            self.stop(b, t)
        imports = self.server.role_imports()
        self.assertGreaterEqual(len(imports), 3)
        self.assertEqual(imports[0]["body"], {"source": "zalo_label", "complete": True, "roles": EXPECTED_ROLES})
        text = "\n".join(logs.output)
        self.assertIn("label sync: 4 labels, 3 role labels, contacts: 2 manager, 2 staff, 1 customer; "
                      "server: imported 5, updated 0, unchanged 0, removed 0, kept_staff 0", text)
        self.assertIn("unchanged 5", text)
        for secret in PRIVATE + [STAFF_TOKEN]:
            self.assertNotIn(secret.lower(), text.lower())

    def test_period_is_respected(self):
        b = self.bridge(label_sync_every_s=30)
        t = self.run_bridge(b, lambda: len(self.server.role_imports()) >= 1)
        time.sleep(0.8)
        self.stop(b, t)
        self.assertEqual(len(self.label_calls()), 1)       # once at start, the next one is 30 s away

    def test_slow_label_list_never_delays_a_send(self):
        self.write_fake(label_sleep_s=20)
        rid = self.server.enqueue("Dạ em chào anh/chị ạ")
        b = self.bridge(label_sync_every_s=60)
        t0 = time.monotonic()
        t = self.run_bridge(b, lambda: self.server.row(rid)["status"] == "sent")
        self.assertEqual(self.server.row(rid)["status"], "sent")
        self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual(self.server.role_imports(), [])   # the label list is still running
        t1 = time.monotonic()
        self.stop(b, t)                                    # stopping cancels the engine call
        self.assertLess(time.monotonic() - t1, 10)
        self.assertEqual(len(self.sent()), 1)

    def test_failing_sync_is_logged_and_retried_while_messages_flow(self):
        self.write_fake(label_list="zalo_error")
        rid = self.server.enqueue("Dạ em chào anh/chị ạ")
        b = self.bridge(label_sync_every_s=0.3)
        with logging_enabled(), self.assertLogs("bridge", level="WARNING") as logs:
            t = self.run_bridge(b, lambda: len(self.label_calls()) >= 2 and self.server.row(rid)["status"] == "sent")
            self.assertEqual(self.server.role_imports(), [])
            self.write_fake(label_list="ok")               # the next period succeeds
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not self.server.role_imports():
                time.sleep(0.05)
            self.stop(b, t)
        self.assertEqual(self.server.row(rid)["status"], "sent")
        self.assertGreaterEqual(len(self.server.role_imports()), 1)
        text = "\n".join(logs.output)
        self.assertIn("label sync: failed (engine_error); nothing posted; will retry next period", text)
        self.assertNotIn("Tham số", text)

    def test_crashing_sync_does_not_stop_the_bridge_or_the_schedule(self):
        seen = []

        def boom(cfg, cancel=None):
            seen.append(1)
            if len(seen) == 1:
                raise RuntimeError(f"contact {C1} exploded")
            return 0, {"ok": True, "dry_run": False, "labels": 0, "role_labels": 0,
                       "contacts": {"manager": 0, "staff": 0, "customer": 0},
                       "skipped": {"groups": 0, "other_ids": 0}, "posted": True, "server": {}}

        rid = self.server.enqueue("Dạ em chào anh/chị ạ")
        b = self.bridge(label_sync_every_s=0.2)
        b.label_sync = boom
        with logging_enabled(), self.assertLogs("bridge", level="ERROR") as logs:
            t = self.run_bridge(b, lambda: len(seen) >= 2 and self.server.row(rid)["status"] == "sent")
            self.stop(b, t)
        self.assertGreaterEqual(len(seen), 2)
        self.assertEqual(self.server.row(rid)["status"], "sent")
        text = "\n".join(logs.output)
        self.assertIn("label sync crashed (RuntimeError); will retry next period", text)
        self.assertNotIn(C1, text)                          # the exception text is not logged

    def test_missing_staff_token_is_a_warning_not_a_crash(self):
        import os
        del os.environ["STAFF_TOKEN"]
        os.environ["THOMHOUSE_DEV_VARS"] = str(self.tmp / "missing")
        b = self.bridge(label_sync_every_s=60)
        with logging_enabled(), self.assertLogs("bridge", level="WARNING") as logs:
            t = self.run_bridge(b, lambda: len(self.label_calls()) >= 1)
            time.sleep(0.5)
            self.stop(b, t)
        self.assertIn("failed (no_staff_token); nothing imported; will retry next period", "\n".join(logs.output))
        self.assertEqual(self.server.role_imports(), [])


if __name__ == "__main__":
    unittest.main()
