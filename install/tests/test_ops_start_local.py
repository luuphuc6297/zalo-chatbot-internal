"""The changed scripts/start_local.sh and scripts/stop_local.sh (16.3.2), run in a temporary root with stubs, in the
manner of apps/zalo-bridge/tests/test_local_scripts.py: the frozen engine install, the runtime PATH of an installed
device in both scripts (without ~/.local/bin, rev F15), the backup hook that runs the real install/thomhouse.py with
python3 -I before `d1 migrations apply` (rev F2), a failing hook that stops the start, no hook without install/, and
the refusal while moved-out.json exists (rev F12). The real stack, npm and wrangler are never run."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from tests.fakes_ops.opscase import OpsTestCase
from tests.support import FAKE_BIN, PROJECT_ROOT
from thomhouse_installer import backup, state

SLEEPER = "import sys, time; time.sleep(float(sys.argv[1]))"
CURL = """#!/bin/sh
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
SERVICE = """#!/bin/sh
# wrangler (d1 commands go to the fake wrangler of install/tests/fake_bin) or vite: a sleeper.
case "$1" in d1) exec "@FAKE_BIN@/wrangler" "$@" ;; esac
exec python3 -c '@SLEEPER@' 300 "$0" "$@"
"""
RUNNER = """import sys, time
if sys.argv[1:2] == ["run"]:
    time.sleep(float("300"))  # time.sleep(float(sys.argv[1])) style sleeper, killed by the test cleanup
"""
PROBE = """#!/bin/sh
printf '%s\\n' "$PATH" >>"@LOG@"
exec "@REAL@" "$@"
"""
HOOK_LINE = ('python3 -I "$ROOT/install/thomhouse.py" backup --stopped --reason before-migration '
             '--if-pending-migrations --quiet')


class StartLocalScriptTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.tmp / "root"
        self.root.mkdir()
        self._fill_tree(self.root)
        for name in ("start_local.sh", "stop_local.sh"):
            shutil.copy(PROJECT_ROOT / "scripts" / name, self.root / "scripts" / name)
        shutil.rmtree(self.root / "tools" / "openmausbot")
        self.write(self.root / "apps" / "server" / "scripts" / "gen-seed-data.mjs", "")
        service = SERVICE.replace("@FAKE_BIN@", str(FAKE_BIN)).replace("@SLEEPER@", SLEEPER)
        self.write(self.root / "apps" / "server" / "node_modules" / ".bin" / "wrangler", service, exe=True)
        self.write(self.root / "apps" / "console" / "node_modules" / ".bin" / "vite", service, exe=True)
        self.write(self.root / "scripts" / "seed_dev.py", "import sys\nsys.exit(0)\n")
        self.write(self.root / "apps" / "runner" / "runner" / "__init__.py", "")
        self.write(self.root / "apps" / "runner" / "runner" / "main.py", RUNNER)
        self.bin = self.tmp / "bin"
        self.write(self.bin / "curl", CURL, exe=True)
        self.bot_home.mkdir(parents=True, exist_ok=True)
        (self.bot_home / "accounts.json").write_text("[]", encoding="utf-8")
        self.addCleanup(self.stop_everything)

    def write(self, path: Path, text: str, exe: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if exe:
            path.chmod(0o755)

    def script_env(self) -> dict[str, str]:
        return dict(self.env, PATH=f"{self.bin}:{self.env['PATH']}", THOMHOUSE_ZALO_MODE="mock")

    def run_script(self, name: str) -> subprocess.CompletedProcess:
        return subprocess.run(["/bin/bash", str(self.root / "scripts" / name)], env=self.script_env(),
                              capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL)

    def stop_everything(self) -> None:
        try:
            self.run_script("stop_local.sh")
        except (OSError, subprocess.SubprocessError):
            pass
        run = self.bot_home / "run"
        for f in run.glob("*.pid") if run.is_dir() else []:
            text = f.read_text(encoding="utf-8").strip()
            if not text.isdigit():
                continue
            pid = int(text)
            command = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                                     text=True).stdout
            started = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                                     text=True).stdout.strip()
            start_file = f.with_suffix(".start")
            recorded = start_file.read_text(encoding="utf-8").strip() if start_file.exists() else None
            if recorded != started:  # only a process this test started (same rule as stop_local.sh)
                continue
            if "cron-tick" in command or str(self.tmp) in command:
                for kill in (os.killpg, os.kill):
                    try:
                        kill(pid, signal.SIGKILL)
                        break
                    except OSError:
                        continue

    def install_engine(self) -> None:
        engine = self.root / "tools" / "zalo-agent" / "node_modules"
        self.write(engine / "@ardennguyen" / "zalo-agent-cli" / "package.json", json.dumps({"version": "2.5.9"}))
        self.write(engine / ".bin" / "zalo-agent", f'#!/bin/sh\nexec "{FAKE_BIN}/zalo-agent" "$@"\n', exe=True)

    def migration_applies(self) -> list[dict]:
        return [c for c in self.calls("wrangler") if c["argv"][:3] == ["d1", "migrations", "apply"]]

    # ------------------------------------------------------------ engine install

    def test_engine_npm_ci_with_lock_and_npm_install_without(self) -> None:
        engine = self.root / "tools" / "zalo-agent"
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        npm = [c["argv"] for c in self.calls("npm")]
        self.assertEqual(npm, [["ci", "--prefix", str(engine), "--no-fund", "--no-audit"]])
        self.assertIn("2/9 Engine zalo-agent-cli 2.5.9", res.stdout)
        self.run_script("stop_local.sh")
        shutil.rmtree(engine / "node_modules")
        (engine / "package-lock.json").unlink()
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        npm = [c["argv"] for c in self.calls("npm")]
        self.assertEqual(npm[-1], ["install", "--prefix", str(engine), "--save-exact", "--no-fund", "--no-audit",
                                   "@ardennguyen/zalo-agent-cli@2.5.9"])

    # ------------------------------------------------------------ runtime PATH

    def runtime_probes(self) -> tuple[list[Path], Path]:
        log = self.tmp / "path-seen"
        dirs = [self.app_home / "runtime" / "node" / "bin", self.app_home / "runtime" / "python" / "bin",
                self.app_home / "runtime" / "bin"]
        self.write(dirs[0] / "node", PROBE.replace("@LOG@", str(log)).replace("@REAL@", str(FAKE_BIN / "node")),
                   exe=True)
        self.write(dirs[1] / "python3", PROBE.replace("@LOG@", str(log)).replace("@REAL@", sys.executable),
                   exe=True)
        dirs[2].mkdir(parents=True, exist_ok=True)
        return dirs, log

    def test_runtime_path_only_on_an_installed_device(self) -> None:
        self.install_engine()
        dirs, log = self.runtime_probes()
        res = self.run_script("start_local.sh")  # no VERSION.json: the build Mac's checkout
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        self.assertFalse(log.exists())
        self.run_script("stop_local.sh")
        self.assertFalse(log.exists())
        (self.root / "VERSION.json").write_text(json.dumps({"schema": 1, "version": "1.4.0"}), encoding="utf-8")
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        caller = self.script_env()["PATH"].split(":")
        seen = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(seen)
        for line in seen:
            entries = line.split(":")
            self.assertEqual(entries[:3], [str(d) for d in dirs])
            self.assertNotIn(str(self.home / ".local" / "bin"), entries)
            self.assertEqual([e for e in entries if e not in caller][:3], [str(d) for d in dirs])
        log.unlink()
        res = self.run_script("stop_local.sh")  # stop calls python3 for the listener: the runtime one
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        seen = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(seen)
        self.assertEqual(seen[0].split(":")[:3], [str(d) for d in dirs])
        self.assertNotIn(str(self.home / ".local" / "bin"), seen[0].split(":"))

    # ------------------------------------------------------------ backup hook

    def test_hook_runs_real_cli(self) -> None:
        self.install_engine()
        self.assertIn(HOOK_LINE, (PROJECT_ROOT / "scripts" / "start_local.sh").read_text(encoding="utf-8"))
        self.seed_d1(self.root, stop_before="0002_outbox.sql")
        calls_before = len(self.migration_applies())
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        found = state.list_backups(self.paths(self.root))
        self.assertEqual([b.reason for b in found], ["before-migration"])
        # The copy holds only 0001: it was taken before `d1 migrations apply` ran.
        self.assertEqual(found[0].migrations_applied, ["0001_init.sql"])
        self.assertTrue(backup.verify(found[0].path))
        self.assertEqual(found[0].app_version, "checkout")
        self.assertEqual(len(self.migration_applies()), calls_before + 1)
        self.assertEqual(self.applied(), ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])
        self.assertTrue((self.bot_home / "logs" / "backup.log").exists())

    def test_failing_hook_stops_the_start_before_migrations(self) -> None:
        self.install_engine()
        self.seed_d1(self.root, stop_before="0002_outbox.sql")
        (self.bot_home / "backups").write_text("not a folder", encoding="utf-8")
        calls_before = len(self.migration_applies())
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 1, res.stdout[-2000:])
        self.assertIn("chưa sao lưu được dữ liệu nên chưa áp migration", res.stderr)
        self.assertEqual(len(self.migration_applies()), calls_before)
        self.assertFalse((self.bot_home / "run" / "server.pid").exists())

    def test_hook_refuses_while_d1_restore_needed(self) -> None:
        self.install_engine()
        # Step 12 left an empty d1 behind (the copy from its backup failed): no database, so the hook alone would
        # skip the backup and wrangler would create a new, empty database.
        (self.bot_home / "d1").mkdir(parents=True, exist_ok=True)
        folder = self.bot_home / "backups" / "20261112-120000-before-migration"
        (self.bot_home / "d1.restore-needed.json").write_text(json.dumps(
            {"backup": folder.name, "backup_path": str(folder), "failed": "x"}), encoding="utf-8")
        calls_before = len(self.migration_applies())
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 1, res.stdout[-2000:])
        self.assertIn("chưa sao lưu được dữ liệu nên chưa áp migration", res.stderr)
        self.assertEqual(len(self.migration_applies()), calls_before)
        self.assertFalse((self.bot_home / "run" / "server.pid").exists())
        self.assertIn("chưa được chép lại", (self.bot_home / "logs" / "backup.log").read_text(encoding="utf-8"))

    def test_no_hook_without_install(self) -> None:
        self.install_engine()
        shutil.rmtree(self.root / "install")
        self.seed_d1(self.root, stop_before="0002_outbox.sql")
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        self.assertFalse((self.bot_home / "backups").exists())
        self.assertFalse((self.bot_home / "logs" / "backup.log").exists())
        self.assertEqual(self.applied(), ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])

    # ------------------------------------------------------------ moved-out guard

    def test_refuses_when_moved_out(self) -> None:
        self.install_engine()
        (self.bot_home / "moved-out.json").write_text('{"schema": 1}', encoding="utf-8")
        res = self.run_script("start_local.sh")
        self.assertEqual(res.returncode, 1)
        self.assertIn("đã chuyển sang máy khác", res.stderr)
        self.assertIn("move-back", res.stderr)
        self.assertNotIn("1/9", res.stdout)
        self.assertFalse((self.bot_home / "run").exists())
        self.assertEqual(self.calls("bridge"), [])
        self.assertEqual(self.migration_applies(), [])
