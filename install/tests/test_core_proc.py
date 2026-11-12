"""proc.py: the process runner, logs through the secret filter, timeouts, and context.py: errors and Ctx.log
(16.3.3, invariant 4)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time

from tests.support import InstallerTestCase
from thomhouse_installer import context, proc

SECRET = "staff-" + "a1b2c3d4" * 6


class ProcTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release()
        server_vars = self.root / "apps" / "server" / ".dev.vars"
        server_vars.write_text(f"STAFF_TOKEN={SECRET}\nRUNNER_TOKEN=short\nENV=dev\n", encoding="utf-8")
        self.ctx_ = self.ctx()

    def test_capture(self) -> None:
        res = proc.run(self.ctx_, [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
                       capture=True)
        self.assertEqual((res.returncode, res.stdout.strip(), res.stderr.strip()), (0, "out", "err"))

    def test_stdin_text_and_default_devnull(self) -> None:
        res = proc.run(self.ctx_, [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                       stdin="hello", capture=True)
        self.assertEqual(res.stdout.strip(), "HELLO")
        res = proc.run(self.ctx_, [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], capture=True)
        self.assertEqual(res.stdout.strip(), "''")

    def test_log_is_redacted_and_nothing_shown(self) -> None:
        log = self.app_home / "logs" / "test.log"
        out, err = io.StringIO(), io.StringIO()
        code = f"print('token is {SECRET}'); print('STAFF_TOKEN=zzzzzzzzzzzzzzzzzzzz')"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            res = proc.run(self.ctx_, [sys.executable, "-c", code], log=log)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))
        self.assertEqual(out.getvalue() + err.getvalue(), "")
        text = log.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn("zzzzzzzzzzzzzzzzzzzz", text)
        self.assertIn("token is ***", text)
        self.assertIn("STAFF_TOKEN=***", text)
        self.assertIn("--- exit 0", text)

    def test_missing_executable_and_exit_codes(self) -> None:
        self.assertEqual(proc.run(self.ctx_, ["/nonexistent/tool"]).returncode, 127)
        self.assertEqual(proc.run(self.ctx_, [sys.executable, "-c", "raise SystemExit(5)"]).returncode, 5)

    def test_timeout_kills_the_group(self) -> None:
        marker = self.tmp / "child.pid"
        code = ("import subprocess, sys, time\n"
                f"c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"open({str(marker)!r}, 'w').write(str(c.pid))\n"
                "time.sleep(60)\n")
        started = time.monotonic()
        res = proc.run(self.ctx_, [sys.executable, "-c", code], timeout=1.5)
        self.assertEqual(res.returncode, 124)
        self.assertLess(time.monotonic() - started, 20)
        child = int(marker.read_text())
        time.sleep(0.3)
        with self.assertRaises(ProcessLookupError):
            for _ in range(20):
                os.kill(child, 0)
                time.sleep(0.2)
            raise AssertionError("grandchild still alive")

    def test_default_env_is_child_env(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-not-passed"
        res = proc.run(self.ctx_, [sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
                       capture=True)
        env = json.loads(res.stdout)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env["PROFILE_LLM_ENABLED"], "false")

    def test_secret_values_and_redact(self) -> None:
        secrets = proc.secret_values(self.ctx_.paths)
        self.assertIn(SECRET, secrets)
        self.assertNotIn("short", secrets)
        self.assertEqual(proc.redact(f"a {SECRET} b", secrets), "a *** b")
        self.assertEqual(proc.redact('RUNNER_TOKEN="abcdefghijklmnopqrstu"', set()), 'RUNNER_TOKEN="***"')
        self.assertEqual(proc.redact("RUNNER_TOKEN=short", set()), "RUNNER_TOKEN=short")


class ContextTest(InstallerTestCase):
    def test_errors(self) -> None:
        err = context.InstallerError()
        self.assertEqual((err.code, err.key, err.fmt), (1, "core.failed", {}))
        err = context.InstallerError("core.locked", 3, name="x")
        self.assertEqual((err.code, err.key, err.fmt), (3, "core.locked", {"name": "x"}))
        ex = context.Exit(4)
        self.assertEqual((ex.code, ex.key), (4, None))
        ex = context.Exit(3, "core.moved_out", tb="tb")
        self.assertEqual((ex.code, ex.key, ex.fmt), (3, "core.moved_out", {"tb": "tb"}))
        self.assertTrue(issubclass(context.Exit, context.InstallerError))
        self.assertEqual((context.EXIT_OK, context.EXIT_FAILED, context.EXIT_USAGE, context.EXIT_REFUSED,
                          context.EXIT_DECLINED, context.EXIT_HUMAN_PENDING), (0, 1, 2, 3, 4, 10))

    def test_make_ctx_and_log(self) -> None:
        root = self.install_release()
        (root / "apps" / "server" / ".dev.vars").write_text(f"STAFF_TOKEN={SECRET}\n", encoding="utf-8")
        import argparse

        args = argparse.Namespace(command="doctor", yes=True, dry_run=False, quiet=True, offline=True, json=False)
        ctx = context.make_ctx(args, env=dict(os.environ), paths=self.paths())
        self.assertEqual((ctx.yes, ctx.dry_run, ctx.quiet, ctx.offline), (True, False, True, True))
        self.assertFalse(ctx.interactive)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ctx.log("test_event", detail=f"has {SECRET}", n=3)
        self.assertEqual(out.getvalue(), "")
        line = (self.app_home / "logs" / "install.log").read_text(encoding="utf-8").splitlines()[-1]
        record = json.loads(line)
        self.assertEqual((record["event"], record["n"], record["detail"]), ("test_event", 3, "has ***"))
        self.assertIn("at", record)
        self.assertEqual(ctx.platform.key, "darwin-arm64")
        self.assertEqual(ctx.pins.engine_version, "2.5.9")
        default = context.make_ctx(argparse.Namespace(command="x"), env={"HOME": str(self.home)})
        self.assertFalse(default.yes)
        self.assertEqual(default.paths.app_home, self.home / "ThomHouse")

    def test_pins_property_raises_pin_error(self) -> None:
        root = self.install_release()
        (root / "install" / "versions.json").unlink()
        ctx = self.ctx()
        from thomhouse_installer.pins import PinError

        with self.assertRaises(PinError):
            ctx.pins  # noqa: B018
