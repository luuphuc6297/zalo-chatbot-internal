"""bridge/rooms.py: where the room platform's node is, and what the doctor learns about the platform.

Everything runs against temp folders: fake `node` scripts that print a version, a fake platform CLI, a temp
THOMHOUSE_BOT_HOME and a listening socket on a free port. The real install and the real data folder are never
looked at."""

import contextlib
import io
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bridge import main as bridge_main
from bridge import rooms


def fake_node(bin_dir: Path, version: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    node = bin_dir / "node"
    node.write_text(f"#!/bin/sh\necho {version}\n")
    node.chmod(0o755)
    return bin_dir


class RoomsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge-rooms-")).resolve()
        self.home = self.tmp / "home"
        self.nvm = self.home / ".nvm" / "versions" / "node"
        self.nvm.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, *path_dirs: Path, **extra: str) -> dict[str, str]:
        return {"PATH": os.pathsep.join(str(d) for d in path_dirs) or str(self.tmp / "empty"),
                "HOME": str(self.home), **extra}


class FindNodeDirTests(RoomsTestCase):
    def test_node_on_path_wins_when_new_enough(self):
        on_path = fake_node(self.tmp / "bin", "v24.3.0")
        fake_node(self.nvm / "v25.0.0" / "bin", "v25.0.0")
        self.assertEqual(rooms.find_node_dir(env=self.env(on_path)), str(on_path))

    def test_old_node_on_path_falls_back_to_the_newest_under_nvm(self):
        on_path = fake_node(self.tmp / "bin", "v22.11.0")
        fake_node(self.nvm / "v22.5.0" / "bin", "v22.5.0")
        fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        newest = fake_node(self.nvm / "v24.19.0" / "bin", "v24.19.0")
        self.assertEqual(rooms.find_node_dir(env=self.env(on_path)), str(newest))

    def test_the_executable_decides_not_the_folder_name(self):
        fake_node(self.nvm / "v26.0.0" / "bin", "v20.0.0")              # mislabelled folder
        (self.nvm / "v27.0.0" / "bin").mkdir(parents=True)              # no node inside
        (self.nvm / "current").mkdir()                                  # not a version folder
        good = fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        self.assertEqual(rooms.find_node_dir(env=self.env()), str(good))

    def test_none_when_no_node_is_new_enough(self):
        on_path = fake_node(self.tmp / "bin", "v22.11.0")
        fake_node(self.nvm / "v23.9.0" / "bin", "v23.9.0")
        self.assertIsNone(rooms.find_node_dir(env=self.env(on_path)))
        self.assertIsNone(rooms.find_node_dir(env=self.env(), home=self.tmp / "no-such-home"))

    def test_node_major(self):
        self.assertEqual(rooms.node_major(fake_node(self.tmp / "a", "v24.19.0") / "node"), 24)
        self.assertIsNone(rooms.node_major(fake_node(self.tmp / "b", "not-a-version") / "node"))
        self.assertIsNone(rooms.node_major(self.tmp / "missing" / "node"))
        self.assertIsNone(rooms.node_major(None))


class PlatformNodeDirTests(RoomsTestCase):
    """`rooms-node`: the node scripts/start_local.sh starts the platform with."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "apps" / "runner").mkdir(parents=True)

    def runner_env(self, text: str) -> None:
        (self.root / "apps" / "runner" / ".env").write_text(text)

    def test_configured_folder_wins_when_it_holds_a_new_enough_node(self):
        configured = fake_node(self.tmp / "chosen", "v24.2.0")
        fake_node(self.nvm / "v25.0.0" / "bin", "v25.0.0")
        self.runner_env(f"# OPENMAUSBOT_NODE_DIR=/commented/out\nOPENMAUSBOT_NODE_DIR={configured}\n")
        self.assertEqual(rooms.platform_node_dir(self.root, env=self.env()), str(configured))

    def test_environment_wins_over_the_runner_file(self):
        in_file = fake_node(self.tmp / "in-file", "v24.2.0")
        in_env = fake_node(self.tmp / "in-env", "v24.5.0")
        self.runner_env(f"OPENMAUSBOT_NODE_DIR={in_file}\n")
        env = self.env(OPENMAUSBOT_NODE_DIR=str(in_env))
        self.assertEqual(rooms.platform_node_dir(self.root, env=env), str(in_env))

    def test_stale_configured_folder_falls_back_to_the_lookup(self):
        old = fake_node(self.tmp / "old", "v22.3.0")
        found = fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        self.runner_env(f"OPENMAUSBOT_NODE_DIR={old}\n")
        self.assertEqual(rooms.platform_node_dir(self.root, env=self.env()), str(found))
        self.runner_env(f"OPENMAUSBOT_NODE_DIR={self.tmp / 'removed'}\n")
        self.assertEqual(rooms.platform_node_dir(self.root, env=self.env()), str(found))

    def test_none_without_any_new_enough_node(self):
        self.runner_env(f"OPENMAUSBOT_NODE_DIR={fake_node(self.tmp / 'old', 'v22.3.0')}\n")
        self.assertIsNone(rooms.platform_node_dir(self.root, env=self.env()))

    def test_rooms_node_command_prints_the_folder_or_exits_1(self):
        found = fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env(), clear=True), contextlib.redirect_stdout(out):
            code = bridge_main.main(["rooms-node", "--repo-root", str(self.root)])
        self.assertEqual((code, out.getvalue()), (0, f"{found}\n"))
        (self.nvm / "v24.1.0" / "bin" / "node").unlink()
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env(), clear=True), contextlib.redirect_stdout(out):
            code = bridge_main.main(["rooms-node", "--repo-root", str(self.root)])
        self.assertEqual((code, out.getvalue()), (1, ""))


class PlatformFactsTests(RoomsTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "apps" / "runner").mkdir(parents=True)
        self.bot_home = self.tmp / "bot-home"

    def install(self) -> Path:
        exe = rooms.default_platform_bin(self.root)
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
        return exe

    def runner_env(self, text: str) -> None:
        (self.root / "apps" / "runner" / ".env").write_text(text)

    def facts(self, *path_dirs: Path, port: int = 1, **extra: str):
        env = self.env(*path_dirs, THOMHOUSE_BOT_HOME=str(self.bot_home), **extra)
        return rooms.platform_facts(repo_root=self.root, env=env, port=port)

    def test_not_installed_looks_at_nothing_else(self):
        fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        facts = self.facts()
        self.assertEqual((facts["installed"], facts["engine"]), (False, "claude"))
        self.assertEqual((facts["node_dir"], facts["node_major"], facts["listening"], facts["config"]),
                         (None, None, None, None))
        self.assertEqual(facts["bin"], str(self.root / "tools/openmausbot/node_modules/.bin/openmausbot"))

    def test_engine_setting_comes_from_the_environment_then_the_runner_file(self):
        self.assertEqual(self.facts()["engine"], "claude")
        self.runner_env("# THOMHOUSE_DRAFT_ENGINE=claude\nTHOMHOUSE_DRAFT_ENGINE=Rooms\n")
        self.assertEqual(self.facts()["engine"], "rooms")
        self.assertEqual(self.facts(THOMHOUSE_DRAFT_ENGINE="claude")["engine"], "claude")

    def test_installed_running_and_configured(self):
        self.install()
        node_dir = fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        (self.bot_home / "openmausbot").mkdir(parents=True)
        (self.bot_home / "openmausbot" / "config.json").write_text("{}")
        with socket.socket() as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            facts = self.facts(port=srv.getsockname()[1])
            self.assertEqual((facts["installed"], facts["listening"], facts["config"]), (True, True, True))
            self.assertEqual((facts["node_dir"], facts["node_major"], facts["node_dir_configured"]),
                             (str(node_dir), 24, False))
            closed_port = srv.getsockname()[1]
        self.assertFalse(self.facts(port=closed_port)["listening"])

    def test_installed_without_node_server_or_config(self):
        self.install()
        with socket.socket() as srv:                 # a port that was just free: nothing listens on it now
            srv.bind(("127.0.0.1", 0))
            port = srv.getsockname()[1]
        facts = self.facts(port=port)
        self.assertEqual((facts["installed"], facts["listening"], facts["config"]), (True, False, False))
        self.assertEqual((facts["node_dir"], facts["node_major"]), (None, None))

    def test_runner_settings_override_node_dir_bin_and_data_dir(self):
        old = fake_node(self.tmp / "old-node", "v22.3.0")
        fake_node(self.nvm / "v24.1.0" / "bin", "v24.1.0")
        other_bin = self.tmp / "elsewhere" / "openmausbot"
        other_bin.parent.mkdir()
        other_bin.write_text("#!/bin/sh\nexit 0\n")
        other_bin.chmod(0o755)
        data = self.tmp / "data"
        data.mkdir()
        (data / "config.json").write_text("{}")
        self.runner_env(f"OPENMAUSBOT_NODE_DIR={old}\nOPENMAUSBOT_BIN={other_bin}\nOPENMAUSBOT_DATA_DIR={data}\n")
        facts = self.facts()
        self.assertEqual((facts["installed"], facts["bin"], facts["config"]), (True, str(other_bin), True))
        # The configured folder is reported as it is, even though a newer node exists under ~/.nvm.
        self.assertEqual((facts["node_dir"], facts["node_major"], facts["node_dir_configured"]), (str(old), 22, True))


if __name__ == "__main__":
    unittest.main()
