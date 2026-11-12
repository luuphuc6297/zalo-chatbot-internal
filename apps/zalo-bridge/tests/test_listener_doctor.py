import hashlib
import json
import unittest
from unittest import mock

from bridge import doctor, listener
from tests.helpers import SECRET, BridgeTestCase


class ListenerTests(BridgeTestCase):
    def listen_calls(self, flag: str) -> list[dict]:
        return [c for c in self.calls() if "listen" in c["argv"] and flag in c["argv"]]

    def test_start_puts_secret_in_env_never_in_argv(self):
        self.start_server()
        cfg = self.cfg()
        code, out = listener.start(cfg)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["started"])
        call = self.listen_calls("-d")[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--webhook") + 1], f"{self.server.url}/zalo/personal/webhook")
        self.assertEqual(argv[argv.index("--filter") + 1], "user")
        self.assertEqual(argv[argv.index("-e") + 1], "message")
        self.assertNotIn("--no-self", argv)
        self.assertNotIn("--webhook-secret", argv)
        self.assertFalse(any(SECRET in a for a in argv))
        self.assertEqual(call["env"]["webhook_secret_sha"], hashlib.sha256(SECRET.encode()).hexdigest())
        self.assertFalse(call["env"]["personal_secret"])
        self.assertFalse(call["env"]["runner_token"])
        self.assertNotIn(SECRET, json.dumps(out))

    def test_start_is_idempotent(self):
        self.start_server()
        listener.start(self.cfg())
        code, out = listener.start(self.cfg())
        self.assertEqual(code, 0)
        self.assertEqual((out["started"], out["already_running"], out["ours"]), (False, True, True))
        self.assertEqual(len(self.listen_calls("-d")), 1)
        st = listener.status(self.cfg())
        self.assertEqual((st["running"], st["ours"], st["health"]["socket"]), (True, True, "up"))

    def test_start_leaves_a_foreign_daemon_alone(self):
        (self.tmp / "daemon.json").write_text(json.dumps({"running": True, "pid": 77}))
        (self.tmp / "daemon.log").write_text("--- [x] starting daemon: /x/zalo-agent mcp start --http ---\n")
        code, out = listener.start(self.cfg())
        self.assertEqual(code, listener.EXIT_FOREIGN_DAEMON)
        self.assertEqual(self.listen_calls("-d"), [])
        code, out = listener.stop(self.cfg(), only_ours=True)
        self.assertEqual((code, out["stopped"]), (0, False))
        self.assertEqual(self.listen_calls("--stop"), [])

    def test_start_refuses_when_not_logged_in(self):
        self.write_fake(logged_in=False)
        code, out = listener.start(self.cfg())
        self.assertEqual(code, listener.EXIT_NOT_LOGGED_IN)
        self.assertEqual(self.listen_calls("-d"), [])

    def test_start_without_any_account_is_not_logged_in(self):
        self.write_fake(has_account=False, logged_in=False)
        code, _ = listener.start(self.cfg())
        self.assertEqual(code, listener.EXIT_NOT_LOGGED_IN)

    def test_start_requires_secret_and_engine(self):
        self.assertEqual(listener.start(self.cfg(webhook_secret=""))[0], listener.EXIT_CONFIG)
        self.assertEqual(listener.start(self.cfg(zalo_agent_bin=str(self.tmp / "nope")))[0], listener.EXIT_CONFIG)
        self.assertEqual(self.calls(), [])

    def test_daemon_start_failure_is_reported(self):
        self.write_fake(daemon_fails="AutoLogin failed: no saved credentials")
        code, out = listener.start(self.cfg(), check_login=False)
        self.assertEqual(code, listener.EXIT_NOT_LOGGED_IN)
        self.assertFalse(out["started"])

    def test_stop_ours(self):
        self.start_server()
        listener.start(self.cfg())
        code, out = listener.stop(self.cfg(), only_ours=True)
        self.assertEqual((code, out["stopped"]), (0, True))
        self.assertFalse(listener.status(self.cfg())["running"])
        self.assertEqual(listener.stop(self.cfg())[1]["stopped"], False)


NO_PLATFORM = {"installed": False, "bin": "/x/tools/openmausbot/node_modules/.bin/openmausbot", "engine": "claude",
               "node_dir": None, "node_dir_configured": False, "node_major": None, "listening": None, "config": None,
               "port": 8799}
PLATFORM_UP = dict(NO_PLATFORM, installed=True, node_dir="/n/v24.1.0/bin", node_major=24, listening=True, config=True)


class DoctorTests(BridgeTestCase):
    def run_doctor(self, facts=None, **kw):
        # The platform facts are patched: the doctor of a test never looks at this machine's real install.
        with mock.patch.object(doctor, "_node_major", return_value=24), \
                mock.patch.object(doctor.rooms, "platform_facts", return_value=dict(facts or NO_PLATFORM)):
            return {c["name"]: c for c in doctor.run_checks(self.cfg(**kw))}

    def test_all_ok(self):
        self.start_server()
        listener.start(self.cfg())
        checks = self.run_doctor()
        self.assertEqual({k: v["status"] for k, v in checks.items()},
                         {"node": "ok", "engine": "ok", "webhook_secret": "ok", "zalo_login": "ok",
                          "listener": "ok", "server": "ok", "bridge_token": "ok", "room_platform": "ok"})
        self.assertIn("not installed (optional", checks["room_platform"]["detail"])
        self.assertEqual(doctor.summary_exit(list(checks.values())), 0)
        self.assertNotIn(SECRET, json.dumps(checks))
        self.assertNotIn("1000000000000001", json.dumps(checks))

    def test_wrong_token_and_missing_listener_fail(self):
        self.start_server()
        checks = self.run_doctor(runner_token="wrong")
        self.assertEqual(checks["bridge_token"]["status"], "fail")
        self.assertIn("token rejected", checks["bridge_token"]["detail"])
        self.assertEqual(checks["listener"]["status"], "fail")
        self.assertEqual(doctor.summary_exit(list(checks.values())), 1)

    def test_not_logged_in_names_the_login_command(self):
        self.start_server()
        self.write_fake(logged_in=False)
        checks = self.run_doctor()
        self.assertEqual(checks["zalo_login"]["status"], "fail")
        self.assertIn("login", checks["zalo_login"]["detail"])

    def test_version_mismatch_warns_and_server_down_fails(self):
        self.write_fake(version="2.6.0")
        checks = self.run_doctor()
        self.assertEqual(checks["engine"]["status"], "warn")
        self.assertEqual(checks["server"]["status"], "fail")
        self.assertEqual(checks["bridge_token"]["status"], "fail")

    def test_server_not_in_personal_mode_warns(self):
        self.start_server()
        self.server.zalo_mode = "mock"
        self.assertEqual(self.run_doctor()["server"]["status"], "warn")

    def test_room_platform_is_the_last_check_and_never_fails_the_doctor(self):
        self.start_server()
        listener.start(self.cfg())
        for facts in (NO_PLATFORM, dict(NO_PLATFORM, engine="rooms"), PLATFORM_UP,
                      dict(PLATFORM_UP, engine="rooms", listening=False, config=False, node_major=None)):
            checks = self.run_doctor(facts=facts)
            self.assertEqual(list(checks)[-1], "room_platform")
            self.assertIn(checks["room_platform"]["status"], ("ok", "warn"))
            self.assertEqual(doctor.summary_exit(list(checks.values())), 0)

    def test_room_platform_inspection_error_is_a_warning(self):
        self.start_server()
        listener.start(self.cfg())
        with mock.patch.object(doctor, "_node_major", return_value=24), \
                mock.patch.object(doctor.rooms, "platform_facts", side_effect=RuntimeError("synthetic detail")):
            checks = {c["name"]: c for c in doctor.run_checks(self.cfg())}
        self.assertEqual(checks["room_platform"]["status"], "warn")
        self.assertNotIn("synthetic detail", checks["room_platform"]["detail"])
        self.assertEqual(doctor.summary_exit(list(checks.values())), 0)


class RoomPlatformCheckTests(unittest.TestCase):
    def check(self, **facts):
        return doctor.room_platform_check(dict(PLATFORM_UP, **facts))

    def test_not_installed_is_ok_while_the_runner_uses_the_direct_engine(self):
        c = doctor.room_platform_check(dict(NO_PLATFORM))
        self.assertEqual((c["name"], c["status"]), ("room_platform", "ok"))
        self.assertIn("not installed (optional", c["detail"])
        self.assertIn("THOMHOUSE_DRAFT_ENGINE=claude", c["detail"])

    def test_not_installed_warns_when_the_runner_is_set_to_rooms(self):
        c = doctor.room_platform_check(dict(NO_PLATFORM, engine="rooms"))
        self.assertEqual(c["status"], "warn")
        self.assertIn("falls back to the direct engine", c["detail"])

    def test_installed_and_running_reports_every_part(self):
        for engine in ("claude", "rooms"):
            c = self.check(engine=engine)
            self.assertEqual(c["status"], "ok", c)
            for part in ("installed", "node 24", "server answers on 127.0.0.1:8799", "config file present",
                         f"THOMHOUSE_DRAFT_ENGINE={engine}"):
                self.assertIn(part, c["detail"])

    def test_installed_but_idle_is_ok_while_the_runner_uses_the_direct_engine(self):
        c = self.check(listening=False, config=False, node_major=None, node_dir=None)
        self.assertEqual(c["status"], "ok", c)
        self.assertIn("no server on 127.0.0.1:8799", c["detail"])
        self.assertIn("config file missing", c["detail"])
        self.assertIn("no node", c["detail"])

    def test_rooms_engine_warns_about_each_missing_part(self):
        self.assertIn("until this is fixed: server", self.check(engine="rooms", listening=False)["detail"])
        self.assertIn("until this is fixed: config file", self.check(engine="rooms", config=False)["detail"])
        c = self.check(engine="rooms", listening=False, config=False, node_major=22)
        self.assertEqual(c["status"], "warn")
        self.assertIn("node 22", c["detail"])
        self.assertIn("until this is fixed: node, server, config file", c["detail"])

    def test_configured_node_dir_without_node_24_warns_for_any_engine(self):
        c = self.check(node_dir_configured=True, node_major=22)
        self.assertEqual(c["status"], "warn")
        self.assertIn("OPENMAUSBOT_NODE_DIR has no node 24+", c["detail"])

    def test_unknown_engine_setting_warns(self):
        self.assertEqual(self.check(engine="room")["status"], "warn")
        self.assertEqual(doctor.room_platform_check(dict(NO_PLATFORM, engine="x"))["status"], "warn")


if __name__ == "__main__":
    unittest.main()
