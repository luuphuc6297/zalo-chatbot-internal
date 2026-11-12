"""scripts/stop_local.sh trusts a PID file only for the process start_local.sh started (start time + pattern).

The script is copied into a temp project root, so ROOT points there: no zalo-agent is installed in it (the listener
step is skipped) and THOMHOUSE_BOT_HOME is a temp dir. Only dummy `sleep` processes started here get signals.

StartLocalTests runs copies of start_local.sh and stop_local.sh in such a temp root too, with a stub for every
program the scripts call (node, npm, pnpm, claude, curl, lsof, wrangler, vite, the runner, the room platform), a
temp HOME and a temp THOMHOUSE_BOT_HOME, in mock Zalo mode. The real scripts are never run, no real port is
opened or asked, nothing is installed, and the real ~/.thomhouse-bot is never touched."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path

from bridge.config import REPO_ROOT
from tests.helpers import FAKE_ENGINE, BridgeTestCase


def proc_start(pid: int) -> str:
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True).stdout
    return out.strip()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class StopLocalTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "scripts" / "stop_local.sh", self.root / "scripts" / "stop_local.sh")
        self.home = self.tmp / "home"
        self.run_dir = self.home / "run"
        self.run_dir.mkdir(parents=True)
        self.pids: list[int] = []

    def tearDown(self):
        for pid in self.pids:
            if alive(pid):
                os.kill(pid, signal.SIGKILL)
        super().tearDown()

    def dummy(self, marker: str) -> int:
        """A sleeping process in its own session whose command line contains `marker`. Started through a shell that
        exits at once, so it is not a child of the test (a killed child would stay a zombie and look alive)."""
        code = "import os, time; os.setsid(); time.sleep(120)"
        out = subprocess.run(["bash", "-c", '"$0" -c "$1" "$2" >/dev/null 2>&1 </dev/null & echo $!',
                              sys.executable, code, marker], capture_output=True, text=True, timeout=30).stdout
        pid = int(out.strip())
        self.pids.append(pid)
        for _ in range(50):
            if proc_start(pid):
                break
            time.sleep(0.05)
        return pid

    def gone(self, pid: int, secs: float = 10) -> bool:
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if not alive(pid):
                return True
            time.sleep(0.1)
        return False

    def stop_local(self) -> str:
        env = dict(os.environ, THOMHOUSE_BOT_HOME=str(self.home))
        r = subprocess.run(["bash", str(self.root / "scripts" / "stop_local.sh")], env=env, capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write_pid(self, name: str, pid: int, start: str | None) -> None:
        (self.run_dir / f"{name}.pid").write_text(f"{pid}\n")
        if start is not None:
            (self.run_dir / f"{name}.start").write_text(start + "\n")

    def test_stops_the_console_it_started(self):
        pid = self.dummy(f"{self.root}/apps/console/node_modules/.bin/../vite/bin/vite.js")
        self.write_pid("console", pid, proc_start(pid))
        out = self.stop_local()
        self.assertIn("console: đã dừng", out)
        self.assertTrue(self.gone(pid))
        self.assertFalse((self.run_dir / "console.pid").exists())
        self.assertFalse((self.run_dir / "console.start").exists())

    def test_reused_pid_with_another_start_time_is_left_alone(self):
        # After a reboot the PID belongs to another process (same pattern even): different start time.
        pid = self.dummy(f"{self.root}/apps/console/vite")
        self.write_pid("console", pid, "Mon Jan  1 00:00:00 2024")
        out = self.stop_local()
        self.assertIn("console: không chạy (đã xóa PID file cũ)", out)
        time.sleep(0.3)
        self.assertTrue(alive(pid))
        self.assertFalse((self.run_dir / "console.pid").exists())
        self.assertFalse((self.run_dir / "console.start").exists())

    def test_vite_of_another_project_is_left_alone(self):
        # Old-style PID file without a start time: only the pattern protects, and it names this project's path.
        pid = self.dummy("/Users/someone/other-project/node_modules/.bin/vite")
        self.write_pid("console", pid, None)
        out = self.stop_local()
        self.assertIn("console: không chạy", out)
        time.sleep(0.3)
        self.assertTrue(alive(pid))


SCRIPTS = REPO_ROOT / "scripts"
PAIRING = "SYNTHETIC-PAIRING-CODE-0000"       # what the fake platform prints: must stay in its log file
STEP_TITLES = ["1/9 Kiểm tra công cụ trên máy", "2/9 Engine zalo-agent-cli", "3/9 File cấu hình", "4/9 Server local",
               "5/9 Danh sách tài khoản Claude cho runner", "6/9 OpenMausBot", "7/9 Runner và bridge",
               "8/9 Listener nhận tin Zalo", "9/9 Console cho nhân viên"]
FORBIDDEN_OPTIONS = ("--tunnel", "--lan", "--public-url", "--domain", "--tailscale", "--relay", "login")

FAKE_CURL = """#!/bin/sh
# Every request succeeds; /health answers with the Zalo mode unless the output goes to -o.
quiet=0
last=""
for a in "$@"; do
  [ "$a" = "-o" ] && quiet=1
  last="$a"
done
if [ "$quiet" = 0 ]; then
  case "$last" in */health) printf '{"ok":true,"zalo_mode":"%s"}\\n' "${THOMHOUSE_ZALO_MODE:-personal}" ;; esac
fi
exit 0
"""

FAKE_LSOF = """#!/bin/sh
# lsof -nP -iTCP:<port> -sTCP:LISTEN -t: a port "listens" when the state folder holds listen-<port>.
port=""
for a in "$@"; do
  case "$a" in -iTCP:*) port="${a#-iTCP:}" ;; esac
done
if [ -n "$port" ] && [ -f "@STATE@/listen-$port" ]; then echo 1; exit 0; fi
exit 1
"""

FAKE_SERVICE = """#!/bin/sh
# wrangler or vite: records the call; `dev` (wrangler) and a call without a subcommand (vite) stay up.
echo "@NAME@ $*" >>"@STATE@/calls.log"
case "$1" in d1) exit 0 ;; esac
sleep 300 &
wait
"""

FAKE_NPM = """#!@PYTHON@
# npm: records the call and the first PATH entry; with the marker file it "installs" the fake platform.
import os, shutil, sys
state = "@STATE@"
with open(state + "/calls.log", "a") as f:
    f.write("npm " + " ".join(sys.argv[1:]) + "\\n")
with open(state + "/npm-path-head", "w") as f:
    f.write(os.environ.get("PATH", "").split(":")[0])
if os.path.exists(state + "/npm-fails"):
    sys.exit(1)
if "--prefix" in sys.argv:
    exe = os.path.join(sys.argv[sys.argv.index("--prefix") + 1], "node_modules", ".bin", "openmausbot")
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    shutil.copy(state + "/openmausbot.template", exe)
    os.chmod(exe, 0o755)
"""

FAKE_PLATFORM = """#!@PYTHON@
# The room platform: records argv, environment and cwd, prints a pairing code (to its log), "listens" by writing
# the marker the fake lsof reads, and stays up. Modes (state/platform-mode): listen (default), mute, exit.
import json, os, signal, sys, time
state = "@STATE@"
marker = state + "/listen-8799"
with open(state + "/calls.log", "a") as f:
    f.write("openmausbot " + " ".join(sys.argv[1:]) + "\\n")
with open(state + "/openmausbot.json", "w") as f:
    json.dump({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd()}, f)
print("pairing code: @PAIRING@", flush=True)
try:
    mode = open(state + "/platform-mode").read().strip()
except OSError:
    mode = "listen"
if mode == "exit":
    sys.exit(3)


def stop(*_):
    try:
        os.unlink(marker)
    except OSError:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
if mode == "listen":
    open(marker, "w").close()
time.sleep(300)
"""

FAKE_RUNNER = """# Stub of apps/runner/runner/main.py: `rooms-setup` and `run` record that they ran and what they were given.
import json, os, sys, time
state = "@STATE@"
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
with open(state + "/calls.log", "a") as f:
    f.write("runner " + cmd + "\\n")
keys = ("THOMHOUSE_BOT_HOME", "OPENMAUSBOT_NODE_DIR", "OPENMAUSBOT_DATA_DIR", "OPENMAUSBOT_BIN",
        "THOMHOUSE_DRAFT_ENGINE", "CLAUDE_EFFORT")
with open(state + "/runner-" + cmd + "-env.json", "w") as f:
    json.dump({k: os.environ[k] for k in keys if k in os.environ}, f)
if cmd == "rooms-setup":
    try:
        code = int(open(state + "/rooms-setup-exit").read())
    except OSError:
        code = 0
    if code == 0:
        data = os.path.join(os.environ["THOMHOUSE_BOT_HOME"], "openmausbot")
        os.makedirs(data, exist_ok=True)
        with open(os.path.join(data, "config.json"), "w") as f:
            f.write("{}")
    sys.exit(code)
if cmd == "run":
    time.sleep(300)
"""


class StartLocalTests(BridgeTestCase):
    def setUp(self):
        super().setUp()
        base = self.tmp.resolve()
        self.root = base / "root"
        self.state = base / "state"
        self.bin = base / "bin"
        self.user_home = base / "userhome"
        self.home = base / "bot-home"                       # THOMHOUSE_BOT_HOME
        self.run_dir = self.home / "run"
        self.platform_dir = self.root / "tools" / "openmausbot"
        self.platform_bin = self.platform_dir / "node_modules" / ".bin" / "openmausbot"
        self.node24 = self.user_home / ".nvm" / "versions" / "node" / "v24.19.0" / "bin"
        self.pids: set[int] = set()
        for d in (self.state, self.bin, self.user_home, self.home):
            d.mkdir(parents=True)
        (self.home / "accounts.json").write_text("{}")     # so the Claude account step runs nothing

        # The project root: both scripts, the bridge package (it finds the root from its own file), stubs.
        (self.root / "scripts").mkdir(parents=True)
        for name in ("start_local.sh", "stop_local.sh"):
            shutil.copy(SCRIPTS / name, self.root / "scripts" / name)
        shutil.copytree(REPO_ROOT / "apps" / "zalo-bridge" / "bridge", self.root / "apps" / "zalo-bridge" / "bridge",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.write(self.root / "apps" / "runner" / "runner" / "__init__.py", "")
        self.write(self.root / "apps" / "runner" / "runner" / "main.py", FAKE_RUNNER)
        self.write(self.root / "apps" / "server" / "scripts" / "gen-seed-data.mjs", "")
        self.write(self.root / "apps" / "server" / "node_modules" / ".bin" / "wrangler",
                   FAKE_SERVICE.replace("@NAME@", "wrangler"), exe=True)
        self.write(self.root / "apps" / "console" / "node_modules" / ".bin" / "vite",
                   FAKE_SERVICE.replace("@NAME@", "vite"), exe=True)
        for name in ("seed_dev.py", "build_menu_images.py"):
            self.write(self.root / "scripts" / name, "")
        for rel in ("data/services.json", "data/business-facts.json", "design/system-prompt-draft.md",
                    "design/tools-schema.json"):
            self.write(self.root / rel, "{}")
        engine = self.root / "tools" / "zalo-agent" / "node_modules"
        self.write(engine / "@ardennguyen" / "zalo-agent-cli" / "package.json", json.dumps({"version": "2.5.9"}))
        (engine / ".bin").mkdir(parents=True)
        shutil.copy(FAKE_ENGINE, engine / ".bin" / "zalo-agent")
        os.chmod(engine / ".bin" / "zalo-agent", 0o755)

        # Programs on PATH. The node on PATH is a 22 (enough for the stack); a 24 exists only under ~/.nvm.
        self.write(self.bin / "node", '#!/bin/sh\n[ "$1" = "--version" ] && echo v22.11.0\nexit 0\n', exe=True)
        self.write(self.bin / "pnpm", '#!/bin/sh\n[ "$1" = "--version" ] && echo 10.0.0\nexit 0\n', exe=True)
        self.write(self.bin / "claude", "#!/bin/sh\nexit 0\n", exe=True)
        self.write(self.bin / "curl", FAKE_CURL, exe=True)
        self.write(self.bin / "lsof", FAKE_LSOF, exe=True)
        self.write(self.bin / "npm", FAKE_NPM, exe=True)
        self.write(self.node24 / "node", "#!/bin/sh\necho v24.19.0\n", exe=True)
        self.write(self.state / "openmausbot.template", FAKE_PLATFORM)

    def tearDown(self):
        self.collect_pids()
        try:
            subprocess.run(["bash", str(self.root / "scripts" / "stop_local.sh")], env=self.script_env(),
                           capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        finally:
            for pid in self.pids:
                for kill in (os.killpg, os.kill):
                    try:
                        kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
            super().tearDown()

    def write(self, path: Path, text: str, exe: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = text.replace("@STATE@", str(self.state)).replace("@PYTHON@", sys.executable)
        path.write_text(text.replace("@PAIRING@", PAIRING))
        if exe:
            path.chmod(0o755)

    def install_platform(self) -> None:
        self.write(self.platform_bin, FAKE_PLATFORM, exe=True)

    def script_env(self, **extra: str) -> dict[str, str]:
        python_dir = str(Path(shutil.which("python3") or sys.executable).parent)
        env = {"PATH": os.pathsep.join([str(self.bin), python_dir, "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
               "HOME": str(self.user_home), "USER": "tester", "LANG": "en_US.UTF-8", "TMPDIR": str(self.tmp),
               "THOMHOUSE_BOT_HOME": str(self.home), "THOMHOUSE_ZALO_MODE": "mock", "THOMHOUSE_ROOMS_WAIT_S": "20",
               "CLAUDE_EFFORT": "high", "FAKE_ZALO_CONFIG": str(self.fake_cfg_path)}
        env.update(extra)
        return env

    def collect_pids(self) -> None:
        if self.run_dir.is_dir():
            for f in self.run_dir.glob("*.pid"):
                try:
                    self.pids.add(int(f.read_text().strip()))
                except ValueError:
                    pass

    def start_local(self, **extra: str) -> subprocess.CompletedProcess:
        r = subprocess.run(["bash", str(self.root / "scripts" / "start_local.sh")], env=self.script_env(**extra),
                           capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL)
        self.collect_pids()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertNotIn(PAIRING, r.stdout + r.stderr)
        # The script does not wait for the runner; give the stub a moment to record that it started.
        end = time.monotonic() + 15
        while time.monotonic() < end:
            try:
                self.recorded("runner-run-env.json")
                break
            except (FileNotFoundError, ValueError):
                time.sleep(0.1)
        return r

    def stop_local(self) -> str:
        r = subprocess.run(["bash", str(self.root / "scripts" / "stop_local.sh")], env=self.script_env(),
                           capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertNotIn(PAIRING, r.stdout + r.stderr)
        return r.stdout

    def calls(self, prefix: str = "") -> list[str]:
        try:
            lines = (self.state / "calls.log").read_text().splitlines()
        except FileNotFoundError:
            return []
        return [line for line in lines if line.startswith(prefix)]

    def recorded(self, name: str) -> dict:
        return json.loads((self.state / name).read_text())

    def pid(self, name: str) -> int | None:
        try:
            return int((self.run_dir / f"{name}.pid").read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def assert_stack_started(self, r: subprocess.CompletedProcess) -> None:
        positions = [r.stdout.find(title) for title in STEP_TITLES]
        self.assertNotIn(-1, positions, r.stdout)
        self.assertEqual(positions, sorted(positions))
        for name in ("server", "cron", "runner", "console"):
            pid = self.pid(name)
            self.assertIsNotNone(pid, name)
            self.assertTrue(alive(pid), name)
        self.assertIsNone(self.pid("bridge"))               # mock mode
        self.assertIn("runner run", self.calls("runner"))
        self.assertIn("Chatbot thom house đang chạy trên máy này (ZALO_MODE=mock).", r.stdout)

    def platform_lines(self, r: subprocess.CompletedProcess) -> list[str]:
        """Lines about the platform, without the step title."""
        text = r.stdout + r.stderr
        return [line for line in text.splitlines() if "OpenMausBot" in line and "6/9" not in line]

    def test_without_the_platform_the_step_is_one_line_and_the_stack_starts_as_before(self):
        r = self.start_local()
        self.assert_stack_started(r)
        lines = self.platform_lines(r)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("[ok] chưa cài OpenMausBot", lines[0])
        self.assertEqual(r.stderr, "")
        self.assertEqual(self.calls("openmausbot"), [])
        self.assertEqual(self.calls("npm"), [])
        self.assertEqual(self.calls("runner"), ["runner run"])
        self.assertEqual(self.recorded("runner-run-env.json"), {"THOMHOUSE_BOT_HOME": str(self.home)})
        self.assertIsNone(self.pid("openmausbot"))
        self.assertFalse((self.home / "openmausbot").exists())
        self.assertFalse((self.home / "logs" / "openmausbot.log").exists())

        out = self.stop_local()
        self.assertIn("openmausbot: không chạy", out)
        order = [out.find(f"  {name}: ") for name in ("console", "cron", "listener", "runner", "openmausbot",
                                                        "bridge", "server")]
        self.assertNotIn(-1, order, out)
        self.assertEqual(order, sorted(order))

    def test_platform_starts_after_rooms_setup_with_a_clean_environment_and_stops_after_the_runner(self):
        self.install_platform()
        r = self.start_local()
        self.assert_stack_started(r)
        self.assertEqual(r.stderr, "")
        self.assertEqual(self.calls("npm"), [])               # node_modules is there: nothing is installed
        data_dir = self.home / "openmausbot"
        serve = f"openmausbot serve --port 8799 --data-dir {data_dir} --label thomhouse --no-open"
        self.assertEqual([c for c in self.calls() if c.startswith(("runner", "openmausbot"))],
                         ["runner rooms-setup", serve, "runner run"])

        seen = self.recorded("openmausbot.json")
        self.assertEqual(seen["argv"], ["serve", "--port", "8799", "--data-dir", str(data_dir), "--label",
                                        "thomhouse", "--no-open"])
        for option in FORBIDDEN_OPTIONS:
            self.assertNotIn(option, seen["argv"])
        env = seen["env"]
        # macOS adds __CF_USER_TEXT_ENCODING to every process; everything else is what the script passed.
        self.assertEqual(set(env) - {"__CF_USER_TEXT_ENCODING"},
                         {"HOME", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "PATH", "OMB_SESSION_IDLE_MS"})
        self.assertEqual((env["HOME"], env["USER"], env["LOGNAME"], env["OMB_SESSION_IDLE_MS"]),
                         (str(self.user_home), "tester", "tester", "120000"))
        self.assertEqual(env["PATH"].split(":")[0], str(self.node24))
        self.assertNotIn(str(self.bin), env["PATH"].split(":"))

        # rooms-setup ran with the runner's environment; the runner got the node, the data folder and the CLI the
        # platform runs with, and the script did not choose the draft engine for it.
        setup_env = self.recorded("runner-rooms-setup-env.json")
        self.assertEqual(setup_env, {"THOMHOUSE_BOT_HOME": str(self.home), "OPENMAUSBOT_NODE_DIR": str(self.node24),
                                     "OPENMAUSBOT_DATA_DIR": str(data_dir), "OPENMAUSBOT_BIN": str(self.platform_bin)})
        self.assertEqual(self.recorded("runner-run-env.json"), setup_env)

        # The pairing code is in the log (owner only) and nowhere on screen (start_local asserts that).
        log = self.home / "logs" / "openmausbot.log"
        self.assertIn(PAIRING, log.read_text())
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertEqual(len(self.platform_lines(r)), 2, self.platform_lines(r))
        self.assertIn("OpenMausBot đã chạy", r.stdout)
        self.assertIn("OpenMausBot:  http://127.0.0.1:8799", r.stdout)
        platform_pid = self.pid("openmausbot")
        self.assertTrue(alive(platform_pid))

        # A second run leaves the running platform alone: no second rooms-setup, no second serve.
        again = self.start_local()
        self.assertIn("OpenMausBot đang chạy", again.stdout)
        self.assertEqual(self.calls("openmausbot"), [serve])
        self.assertEqual(self.calls("runner"), ["runner rooms-setup", "runner run"])
        self.assertEqual(self.pid("openmausbot"), platform_pid)

        out = self.stop_local()
        self.assertIn("runner: đã dừng", out)
        self.assertIn("openmausbot: đã dừng", out)
        self.assertLess(out.find("runner: đã dừng"), out.find("openmausbot: đã dừng"))
        self.assertLess(out.find("openmausbot: đã dừng"), out.find("  bridge: "))
        self.assertFalse(alive(platform_pid))
        self.assertIsNone(self.pid("openmausbot"))

    def test_failing_rooms_setup_skips_the_platform(self):
        self.install_platform()
        (self.state / "rooms-setup-exit").write_text("2")
        r = self.start_local()
        self.assert_stack_started(r)
        lines = self.platform_lines(r)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("[!!]", lines[0])
        self.assertIn("rooms-setup", lines[0])
        self.assertEqual(self.calls("openmausbot"), [])
        self.assertEqual(self.calls("runner"), ["runner rooms-setup", "runner run"])
        self.assertEqual(self.recorded("runner-run-env.json"), {"THOMHOUSE_BOT_HOME": str(self.home)})
        self.assertIsNone(self.pid("openmausbot"))
        self.assertNotIn("OpenMausBot:  http", r.stdout)

    def test_platform_that_never_opens_its_port_is_stopped_and_the_stack_goes_on(self):
        self.install_platform()
        (self.state / "platform-mode").write_text("mute")
        r = self.start_local(THOMHOUSE_ROOMS_WAIT_S="2")
        self.assert_stack_started(r)
        lines = self.platform_lines(r)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("chưa mở cổng 8799 sau 2 giây", lines[0])
        self.assertEqual(len(self.calls("openmausbot")), 1)
        self.assertIn(PAIRING, (self.home / "logs" / "openmausbot.log").read_text())
        self.assertIsNone(self.pid("openmausbot"))
        self.assertFalse((self.run_dir / "openmausbot.start").exists())
        self.assertEqual(self.recorded("runner-run-env.json"), {"THOMHOUSE_BOT_HOME": str(self.home)})
        # The process the script started is gone a moment later.
        started = subprocess.run(["pgrep", "-f", str(self.platform_bin)], capture_output=True, text=True).stdout
        end = time.monotonic() + 10
        while started.strip() and time.monotonic() < end:
            time.sleep(0.2)
            started = subprocess.run(["pgrep", "-f", str(self.platform_bin)], capture_output=True, text=True).stdout
        self.assertEqual(started.strip(), "")

    def test_platform_that_exits_at_once_does_not_stop_the_start(self):
        self.install_platform()
        (self.state / "platform-mode").write_text("exit")
        r = self.start_local(THOMHOUSE_ROOMS_WAIT_S="2")
        self.assert_stack_started(r)
        self.assertIn("chưa mở cổng 8799", "\n".join(self.platform_lines(r)))
        self.assertIsNone(self.pid("openmausbot"))

    def test_busy_port_and_missing_node_24_each_skip_the_platform(self):
        self.install_platform()
        (self.state / "listen-8799").write_text("")           # another program holds the port
        r = self.start_local()
        self.assert_stack_started(r)
        lines = self.platform_lines(r)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("cổng 8799 đang có tiến trình khác", lines[0])
        self.assertEqual(self.calls("openmausbot"), [])
        self.assertEqual(self.calls("runner"), ["runner run"])

        (self.state / "listen-8799").unlink()
        shutil.rmtree(self.user_home / ".nvm")                # only the node 22 on PATH is left
        (self.root / "apps" / "runner" / ".env").unlink()     # and no folder from an earlier init-env
        r = self.start_local()
        lines = self.platform_lines(r)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("OpenMausBot cần Node.js 24 trở lên", lines[0])
        self.assertIn("node v22.11.0", r.stdout)              # the rest of the stack keeps its Node 22 gate
        self.assertEqual(self.calls("openmausbot"), [])
        self.assertEqual(self.calls("runner"), ["runner run"])

    def test_pinned_install_runs_only_with_a_package_file_and_without_node_modules(self):
        self.write(self.platform_dir / "package.json", json.dumps({"dependencies": {"openmausbot": "0.1.154"}}))
        self.write(self.platform_dir / "package-lock.json", "{}")
        (self.state / "npm-fails").write_text("")
        r = self.start_local()
        self.assert_stack_started(r)
        install = f"npm ci --prefix {self.platform_dir} --no-fund --no-audit"
        self.assertEqual(self.calls("npm"), [install])
        self.assertEqual((self.state / "npm-path-head").read_text(), str(self.node24))
        self.assertIn("cài OpenMausBot lỗi", "\n".join(self.platform_lines(r)))
        self.assertEqual(self.calls("openmausbot"), [])

        (self.state / "npm-fails").unlink()
        r = self.start_local()
        self.assertEqual(self.calls("npm"), [install, install])
        self.assertIn("OpenMausBot đã chạy", r.stdout)
        self.assertEqual(len(self.calls("openmausbot")), 1)

        self.stop_local()
        r = self.start_local()                                # node_modules exists now: no third install
        self.assertEqual(self.calls("npm"), [install, install])
        self.assertIn("OpenMausBot đã chạy", r.stdout)

    def test_install_without_a_lock_file_uses_npm_install(self):
        self.write(self.platform_dir / "package.json", json.dumps({"dependencies": {"openmausbot": "0.1.154"}}))
        r = self.start_local()
        self.assertEqual(self.calls("npm"), [f"npm install --prefix {self.platform_dir} --no-fund --no-audit"])
        self.assertIn("OpenMausBot đã chạy", r.stdout)


class ScriptTextTests(unittest.TestCase):
    """Static checks on the real scripts: syntax, and what must never appear in them."""

    def test_both_scripts_pass_bash_and_zsh_syntax_checks(self):
        shells = ["bash"] + (["zsh"] if shutil.which("zsh") else [])
        for name in ("start_local.sh", "stop_local.sh"):
            for shell in shells:
                r = subprocess.run([shell, "-n", str(SCRIPTS / name)], capture_output=True, text=True, timeout=60)
                self.assertEqual((r.returncode, r.stderr), (0, ""), f"{shell} -n {name}")

    def test_platform_is_started_local_only_and_its_log_is_never_read(self):
        text = (SCRIPTS / "start_local.sh").read_text()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for option in FORBIDDEN_OPTIONS[:-1]:
            self.assertNotIn(option, code)
        self.assertNotIn("openmausbot login", code)
        self.assertNotIn('"$ROOMS_BIN" login', code)
        self.assertIn("env -i HOME=", code)
        self.assertIn("OMB_SESSION_IDLE_MS=120000", code)
        for script in ("start_local.sh", "stop_local.sh"):
            for line in (SCRIPTS / script).read_text().splitlines():
                if line.lstrip().startswith("#") or not ("ROOMS_LOG" in line or "openmausbot.log" in line):
                    continue
                for reader in ("cat ", "tail ", "head ", "less ", "grep ", "sed ", "awk "):
                    self.assertNotIn(reader, line, f"{script} must never print the platform log")

    def test_steps_are_numbered_one_to_nine(self):
        text = (SCRIPTS / "start_local.sh").read_text()
        for title in STEP_TITLES:
            self.assertIn(f'say "{title}', text)
        self.assertNotIn("/8 ", text)
