import os
import subprocess
import sys

from bridge import main as bridge_main
from bridge.journal import StateLocked, acquire_state_lock
from tests.helpers import BridgeTestCase

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StateLockTests(BridgeTestCase):
    def test_second_holder_is_refused_and_lock_frees_on_close(self):
        state = self.tmp / "state"
        fd = acquire_state_lock(state)
        with self.assertRaises(StateLocked):
            acquire_state_lock(state)
        os.close(fd)
        os.close(acquire_state_lock(state))

    def test_lock_is_held_across_processes(self):
        state = self.tmp / "state"
        fd = acquire_state_lock(state)
        try:
            code = ("import sys; from bridge.journal import acquire_state_lock, StateLocked\n"
                    "try:\n    acquire_state_lock(sys.argv[1])\nexcept StateLocked:\n    sys.exit(7)\n")
            r = subprocess.run([sys.executable, "-c", code, str(state)], cwd=APP_DIR, timeout=30)
            self.assertEqual(r.returncode, 7)
        finally:
            os.close(fd)

    def test_once_exits_5_while_another_bridge_holds_the_state_dir(self):
        state = self.tmp / "state"
        os.environ.update({"RUNNER_TOKEN": "t", "BRIDGE_STATE_DIR": str(state), "THOMHOUSE_BOT_HOME": str(self.tmp),
                           "SERVER_URL": "http://127.0.0.1:9"})
        fd = acquire_state_lock(state)
        try:
            self.assertEqual(bridge_main.main(["once"]), 5)
            self.assertEqual(bridge_main.main(["run"]), 5)
        finally:
            os.close(fd)
        self.assertEqual(self.calls(), [])        # zalo-agent never ran
