"""`thomhouse repair [--paths] [--env]` (16.8.7): changed program files come back from the cached release file
(checked against the stored trust), runtime-written files are left alone, `app`, the launcher and folder modes are
fixed, and --paths and --env act only after c and never print a secret value."""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from contextlib import redirect_stdout

from tests.fakes_release.kit import ReleaseTestCase, run_tty
from thomhouse_installer import release, repair
from thomhouse_installer.text_vi import t

TOKEN = "runner-" + "a1" * 24
STAFF = "staff-" + "b2" * 24
SECRET = "c3" * 32


class RepairTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.folder = self.install_built("1.4.0")
        self.app = self.app_home / "app"

    def cli(self, *args: str, answers: str | None = None):
        cmd = [sys.executable, "-I", str(self.app / "install" / "thomhouse.py"), "repair", *args]
        if answers is not None:
            return run_tty(cmd, env=dict(self.env), answers=answers)
        return subprocess.run(cmd, cwd="/", env=dict(self.env), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=180)

    def test_changed_file_is_restored_from_the_cached_release(self) -> None:
        target = self.folder / "scripts" / "stop_local.sh"
        original = target.read_bytes()
        target.write_text("#!/bin/bash\necho tampered\n", encoding="utf-8")
        (self.folder / "data" / "services.json").unlink()
        res = self.cli()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(t("release.repair_restored", n=2), res.stdout)
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(os.access(target, os.X_OK))
        self.assertEqual(release.verify_manifest(self.folder), [])
        self.assertEqual(list((self.app_home / "releases").glob(".repair-*")), [])

    def test_runtime_written_file_is_skipped(self) -> None:
        seed = self.folder / "apps" / "server" / "src" / "seed-data.ts"
        seed.write_text("regenerated at start\n", encoding="utf-8")
        res = self.cli()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(t("release.repair_files_ok"), res.stdout)
        self.assertEqual(seed.read_text(encoding="utf-8"), "regenerated at start\n")

    def test_app_link_launcher_and_modes_are_fixed(self) -> None:
        other = self.app_home / "releases" / "1.3.0"
        other.mkdir()
        os.unlink(self.app)
        self.app.symlink_to("releases/1.3.0")
        os.chmod(self.app_home, 0o755)
        self.bot_home.mkdir(parents=True, exist_ok=True)
        os.chmod(self.bot_home, 0o755)
        self.app_home.joinpath("bin", "thomhouse").write_text("#!/bin/bash\nold\n", encoding="utf-8")
        cmd = [sys.executable, "-I", str(self.folder / "install" / "thomhouse.py"), "repair"]
        res = subprocess.run(cmd, cwd="/", env=dict(self.env), capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=180)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(os.readlink(self.app), "releases/1.4.0")
        self.assertIn(t("release.repair_relinked", v="1.4.0"), res.stdout)
        self.assertEqual(self.app_home.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.bot_home.stat().st_mode & 0o777, 0o700)
        self.assertTrue(release.launcher_current(self.ctx(), self.folder))

    def test_without_the_cached_file(self) -> None:
        (self.app_home / "cache" / "releases" / "thomhouse-1.4.0.command").unlink()
        (self.folder / "package.json").write_text("{}", encoding="utf-8")
        res = self.cli()
        self.assertEqual(res.returncode, 1)
        self.assertIn("Máy không còn file cài bản 1.4.0 đã lưu", res.stdout)

    def test_tampered_cached_file_is_not_used(self) -> None:
        cached = self.app_home / "cache" / "releases" / "thomhouse-1.4.0.command"
        data = bytearray(cached.read_bytes())
        data[-40] ^= 0x01
        cached.write_bytes(bytes(data))
        (self.folder / "package.json").write_text("{}", encoding="utf-8")
        res = self.cli()
        self.assertEqual(res.returncode, 1)
        self.assertIn(t("release.damaged"), res.stdout)
        self.assertEqual((self.folder / "package.json").read_text(encoding="utf-8"), "{}")

    def test_not_installed(self) -> None:
        (self.app_home / "installed.json").unlink()
        out = io.StringIO()
        with redirect_stdout(out):
            code = repair.cmd_repair(self.ctx(), argparse.Namespace(paths=False, env=False))
        self.assertEqual(code, 1)
        self.assertIn(t("release.repair_not_installed"), out.getvalue())


class RepairEnvTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.folder = self.install_built("1.4.0")
        self.app = self.app_home / "app"
        self.write_env("server", f"RUNNER_TOKEN={TOKEN}\nSTAFF_TOKEN={STAFF}\nZALO_PERSONAL_WEBHOOK_SECRET={SECRET}\n")
        self.write_env("runner", "SERVER_URL=http://127.0.0.1:8787\nRUNNER_TOKEN=runner-old-old-old-old-old\n"
                                 "# OPENMAUSBOT_NODE_DIR=/old/node/bin\nRUNNER_ID=mac-local-1\n")
        self.write_env("bridge", "SERVER_URL=http://127.0.0.1:8787\nRUNNER_TOKEN=runner-old-old-old-old-old\n"
                                 "ZALO_PERSONAL_WEBHOOK_SECRET=old-secret-old-secret\n"
                                 "ZALO_AGENT_BIN=/Users/old/tools/zalo-agent/node_modules/.bin/zalo-agent\n")

    def write_env(self, name: str, text: str) -> None:
        f = self.ctx().paths.env_file(name)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        f.chmod(0o600)

    def read_env(self, name: str) -> str:
        return self.ctx().paths.env_file(name).read_text(encoding="utf-8")

    def test_env_and_paths_need_c(self) -> None:
        before = {n: self.read_env(n) for n in ("server", "runner", "bridge")}
        for args in (("--env",), ("--paths",), ("--env", "--paths")):
            with self.subTest(args=args):
                res = subprocess.run([sys.executable, "-I", str(self.app / "install" / "thomhouse.py"), "repair",
                                      *args], cwd="/", env=dict(self.env), capture_output=True, text=True,
                                     stdin=subprocess.DEVNULL, timeout=120)
                self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
                self.assertIn(t("release.repair_declined"), res.stdout)
                self.assertEqual({n: self.read_env(n) for n in before}, before)
        self.assertEqual(self.calls("start_local.sh"), [])

    def test_env_after_c_copies_tokens_and_prints_no_value(self) -> None:
        res = run_tty([sys.executable, "-I", str(self.app / "install" / "thomhouse.py"), "repair", "--env"],
                      env=dict(self.env), answers="c\n")
        self.assertEqual(res.returncode, 0, res.stdout)
        runner, bridge = self.read_env("runner"), self.read_env("bridge")
        self.assertIn(f"RUNNER_TOKEN={TOKEN}\n", runner)
        self.assertEqual(runner.count("RUNNER_TOKEN="), 1)
        self.assertIn(f"RUNNER_TOKEN={TOKEN}\n", bridge)
        self.assertIn(f"ZALO_PERSONAL_WEBHOOK_SECRET={SECRET}\n", bridge)
        self.assertIn("RUNNER_ID=mac-local-1", runner)
        for f in ("runner", "bridge"):
            self.assertEqual(self.ctx().paths.env_file(f).stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.calls("stop_local.sh")), 1)
        self.assertEqual(len(self.calls("start_local.sh")), 1)
        logs = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (self.app_home / "logs").glob("*.log"))
        for value in (TOKEN, STAFF, SECRET):
            self.assertNotIn(value, res.stdout)
            self.assertNotIn(value, logs)
        self.assertIn(t("release.repair_env_done"), res.stdout)

    def test_paths_after_c_removes_old_paths_and_restarts(self) -> None:
        out = io.StringIO()
        ctx = self.ctx(yes=True)
        with redirect_stdout(out):
            code = repair.cmd_repair(ctx, argparse.Namespace(paths=True, env=False))
        self.assertEqual(code, 0, out.getvalue())
        runner, bridge = self.read_env("runner"), self.read_env("bridge")
        self.assertNotIn("/old/node/bin", runner)
        self.assertNotIn("/Users/old/", bridge)
        # The restart ran init-env (the stub start_local.sh), which wrote this installation's engine path.
        self.assertIn(f"ZALO_AGENT_BIN={self.app}/tools/zalo-agent/node_modules/.bin/zalo-agent", bridge)
        self.assertEqual(len(self.calls("start_local.sh")), 1)
        for value in (TOKEN, STAFF, SECRET):
            self.assertNotIn(value, out.getvalue())

    def test_env_with_a_server_file_without_secrets(self) -> None:
        self.write_env("server", "ENV=dev\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = repair.cmd_repair(self.ctx(yes=True), argparse.Namespace(paths=False, env=True))
        self.assertEqual(code, 1)
        self.assertIn(t("release.repair_env_missing", tb="~/ThomHouse/bin/thomhouse").splitlines()[0], out.getvalue())
