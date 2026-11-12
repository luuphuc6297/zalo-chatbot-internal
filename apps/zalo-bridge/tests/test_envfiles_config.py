import contextlib
import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from bridge.config import Config, ConfigError, read_dotenv
from bridge.envfiles import init_env
from bridge.main import main


class InitEnvTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="bridge-env-"))
        for d in ("apps/server", "apps/runner", "apps/zalo-bridge"):
            (self.root / d).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def files(self):
        return (read_dotenv(self.root / "apps/server/.dev.vars"), read_dotenv(self.root / "apps/runner/.env"),
                read_dotenv(self.root / "apps/zalo-bridge/.env"))

    def test_creates_three_files_that_agree(self):
        init_env(self.root, engine_bin="/x/zalo-agent")
        server, runner, bridge = self.files()
        self.assertEqual((server["ENV"], server["ZALO_MODE"]), ("dev", "personal"))
        for key in ("RUNNER_TOKEN", "STAFF_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET"):
            self.assertGreaterEqual(len(server[key]), 32)
        self.assertEqual(runner["RUNNER_TOKEN"], server["RUNNER_TOKEN"])
        self.assertEqual(bridge["RUNNER_TOKEN"], server["RUNNER_TOKEN"])
        self.assertEqual(bridge["ZALO_PERSONAL_WEBHOOK_SECRET"], server["ZALO_PERSONAL_WEBHOOK_SECRET"])
        self.assertEqual(runner["SERVER_URL"], "http://127.0.0.1:8787")
        self.assertEqual(bridge["SERVER_URL"], "http://127.0.0.1:8787")
        self.assertEqual(bridge["ZALO_AGENT_BIN"], "/x/zalo-agent")
        self.assertNotIn("STAFF_TOKEN", bridge)
        for p in ("apps/server/.dev.vars", "apps/runner/.env", "apps/zalo-bridge/.env"):
            self.assertEqual(stat.S_IMODE(os.stat(self.root / p).st_mode), 0o600)

    def test_keeps_existing_values_comments_and_unrelated_keys(self):
        (self.root / "apps/server/.dev.vars").write_text(
            "# my comment\nRUNNER_TOKEN=keep-runner\nSTAFF_TOKEN=keep-staff\nZALO_MODE=mock\nOTHER=1\n")
        (self.root / "apps/runner/.env").write_text("SERVER_URL=http://old\nRUNNER_TOKEN=stale\nRUNNER_ID=mac-x\n")
        init_env(self.root)
        text = (self.root / "apps/server/.dev.vars").read_text()
        self.assertTrue(text.startswith("# my comment\nRUNNER_TOKEN=keep-runner\nSTAFF_TOKEN=keep-staff\n"))
        server, runner, _ = self.files()
        self.assertEqual((server["ZALO_MODE"], server["OTHER"]), ("personal", "1"))
        self.assertEqual((runner["RUNNER_TOKEN"], runner["RUNNER_ID"], runner["SERVER_URL"]),
                         ("keep-runner", "mac-x", "http://127.0.0.1:8787"))

    def test_second_run_changes_nothing(self):
        init_env(self.root, engine_bin="/x/zalo-agent")
        before = [p.read_bytes() for p in self.root.glob("apps/*/.[de]*")]
        summary = init_env(self.root, engine_bin="/y/other")
        after = [p.read_bytes() for p in self.root.glob("apps/*/.[de]*")]
        self.assertEqual(before, after)
        for part in summary.values():
            self.assertEqual((part["created"], part["updated"]), ([], []))

    def runner_text(self) -> str:
        return (self.root / "apps/runner/.env").read_text()

    def test_runner_gets_the_room_settings(self):
        summary = init_env(self.root, node_dir="/n/v24.1.0/bin")
        _, runner, _ = self.files()
        self.assertEqual(runner["THOMHOUSE_DRAFT_ENGINE"], "claude")
        self.assertEqual(runner["OPENMAUSBOT_NODE_DIR"], "/n/v24.1.0/bin")
        self.assertLessEqual({"THOMHOUSE_DRAFT_ENGINE", "OPENMAUSBOT_NODE_DIR"}, set(summary["runner"]["created"]))
        # The other settings keep the runner's defaults: they are written as commented lines only.
        lines = self.runner_text().splitlines()
        for key, value in (("OPENMAUSBOT_BIN", f"{self.root}/tools/openmausbot/node_modules/.bin/openmausbot"),
                           ("OPENMAUSBOT_DATA_DIR", "~/.thomhouse-bot/openmausbot"), ("ROOM_TURN_TIMEOUT_S", "240"),
                           ("ROOM_OBSERVE_EVERY_S", "30"), ("ROOM_FALLBACK", "claude"),
                           ("ROOM_REQUIRE_PROFILE_READ", "1"), ("ROOM_CUSTOMER_MODEL", "")):
            self.assertNotIn(key, runner)
            self.assertIn(f"# {key}={value}", lines)
            self.assertNotIn(key, summary["runner"]["created"])

    def test_node_dir_is_left_out_without_a_node_and_filled_by_a_later_run(self):
        init_env(self.root, node_dir=None)
        self.assertNotIn("OPENMAUSBOT_NODE_DIR", self.runner_text())
        self.assertEqual(self.files()[1]["THOMHOUSE_DRAFT_ENGINE"], "claude")
        summary = init_env(self.root, node_dir="/n/v24.1.0/bin")
        self.assertEqual(self.files()[1]["OPENMAUSBOT_NODE_DIR"], "/n/v24.1.0/bin")
        self.assertEqual(summary["runner"]["created"], ["OPENMAUSBOT_NODE_DIR"])
        self.assertEqual(summary["runner"]["updated"], [])

    def test_existing_room_settings_are_never_overwritten(self):
        mine = ("SERVER_URL=http://127.0.0.1:8787\nTHOMHOUSE_DRAFT_ENGINE=rooms\nOPENMAUSBOT_NODE_DIR=/mine/bin\n"
                "ROOM_TURN_TIMEOUT_S=120\n# ROOM_FALLBACK=none\n#OPENMAUSBOT_BIN=/mine/openmausbot\n")
        (self.root / "apps/runner/.env").write_text(mine)
        summary = init_env(self.root, node_dir="/n/v24.1.0/bin")
        text = self.runner_text()
        self.assertTrue(text.startswith(mine))
        _, runner, _ = self.files()
        self.assertEqual((runner["THOMHOUSE_DRAFT_ENGINE"], runner["OPENMAUSBOT_NODE_DIR"],
                          runner["ROOM_TURN_TIMEOUT_S"]), ("rooms", "/mine/bin", "120"))
        for key in ("THOMHOUSE_DRAFT_ENGINE", "OPENMAUSBOT_NODE_DIR", "ROOM_TURN_TIMEOUT_S", "ROOM_FALLBACK",
                    "OPENMAUSBOT_BIN"):
            self.assertEqual(sum(1 for line in text.splitlines() if key + "=" in line), 1, key)
            self.assertNotIn(key, summary["runner"]["created"] + summary["runner"]["updated"])
        self.assertIn("# ROOM_OBSERVE_EVERY_S=30", text.splitlines())     # a setting the file did not mention

    def test_room_keys_the_owner_commented_out_stay_commented(self):
        (self.root / "apps/runner/.env").write_text("# THOMHOUSE_DRAFT_ENGINE=rooms\n# OPENMAUSBOT_NODE_DIR=/old/bin\n")
        init_env(self.root, node_dir="/n/v24.1.0/bin")
        _, runner, _ = self.files()
        self.assertNotIn("THOMHOUSE_DRAFT_ENGINE", runner)
        self.assertNotIn("OPENMAUSBOT_NODE_DIR", runner)

    def test_second_run_with_room_settings_changes_nothing(self):
        init_env(self.root, node_dir="/n/v24.1.0/bin")
        before = self.runner_text()
        summary = init_env(self.root, node_dir="/n/v26.0.0/bin")
        self.assertEqual(self.runner_text(), before)
        self.assertEqual((summary["runner"]["created"], summary["runner"]["updated"]), ([], []))

    def test_bridge_gets_the_label_sync_period_and_keeps_an_existing_one(self):
        init_env(self.root, node_dir=None)
        self.assertEqual(self.files()[2]["LABEL_SYNC_EVERY_S"], "900")
        path = self.root / "apps/zalo-bridge/.env"
        path.write_text(path.read_text().replace("LABEL_SYNC_EVERY_S=900", "LABEL_SYNC_EVERY_S=0"))
        summary = init_env(self.root, node_dir=None)
        self.assertEqual(self.files()[2]["LABEL_SYNC_EVERY_S"], "0")
        self.assertEqual((summary["bridge"]["created"], summary["bridge"]["updated"]), ([], []))

    def test_mock_mode(self):
        init_env(self.root, mode="mock")
        self.assertEqual(self.files()[0]["ZALO_MODE"], "mock")

    def test_cli_output_names_keys_but_never_values(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["init-env", "--repo-root", str(self.root)]), 0)
        printed = buf.getvalue()
        server, _, _ = self.files()
        self.assertIn("ZALO_PERSONAL_WEBHOOK_SECRET", printed)
        for key in ("RUNNER_TOKEN", "STAFF_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET", "ZALO_OA_SECRET_KEY"):
            self.assertNotIn(server[key], printed)
        json.loads(printed)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge-cfg-"))
        self.dotenv = self.tmp / ".env"
        self.dotenv.write_text("RUNNER_TOKEN=from-file\nBRIDGE_ID=file-id\nSEND_MIN_INTERVAL_S=3\n"
                               "ZALO_PERSONAL_WEBHOOK_SECRET=s3cret\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_wins_over_file(self):
        cfg = Config.load(env={"BRIDGE_ID": "env-id", "THOMHOUSE_BOT_HOME": str(self.tmp)}, dotenv=self.dotenv)
        self.assertEqual((cfg.runner_token, cfg.bridge_id, cfg.send_min_interval_s, cfg.webhook_secret),
                         ("from-file", "env-id", 3.0, "s3cret"))
        self.assertEqual(cfg.state_dir, self.tmp / "bridge")
        self.assertEqual(cfg.server_url, "http://127.0.0.1:8787")
        self.assertEqual(cfg.send_timeout_s, 30.0)

    def test_label_sync_period(self):
        self.assertEqual(Config.load(env={}, dotenv=self.dotenv).label_sync_every_s, 900.0)
        self.assertEqual(Config.load(env={"LABEL_SYNC_EVERY_S": "60"}, dotenv=self.dotenv).label_sync_every_s, 60.0)
        for off in ("0", "-5"):
            self.assertEqual(Config.load(env={"LABEL_SYNC_EVERY_S": off}, dotenv=self.dotenv).label_sync_every_s, 0.0)

    def test_rejects_bad_values(self):
        for env in ({"BRIDGE_ID": "bad id"}, {"ZALO_ACCOUNT": "me"}, {"SEND_TIMEOUT_S": "x"},
                    {"SERVER_URL": "ftp://x"}, {"LABEL_SYNC_EVERY_S": "often"}):
            with self.assertRaises(ConfigError):
                Config.load(env=env, dotenv=self.dotenv)
        with self.assertRaises(ConfigError):
            Config.load(env={}, dotenv=self.tmp / "missing")


if __name__ == "__main__":
    unittest.main()
