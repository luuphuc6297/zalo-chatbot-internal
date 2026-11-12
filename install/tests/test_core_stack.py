"""stack.py and the child environment: PID rule, start and stop through the scripts, other installations, loopback
bypass of proxies (14.10, 16.3.3, 16.4.2, rev F1, F4, F12, F14, F18, F20)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.support import InstallerTestCase
from thomhouse_installer import context, proc, stack, state

SLEEP = "import sys, time; time.sleep(float(sys.argv[1]))"


class StackTest(InstallerTestCase):
    def spawn(self, name: str, *args: str, cwd: Path | None = None) -> int:
        """A sleeper in its own session with `args` in its command line, registered like start_local.sh does."""
        run_dir = self.bot_home / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        p = subprocess.Popen([sys.executable, "-c", SLEEP, "120", *args], cwd=str(cwd or self.tmp),
                             start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(self._reap, p)
        (run_dir / f"{name}.pid").write_text(f"{p.pid}\n", encoding="utf-8")
        started = subprocess.run(["ps", "-o", "lstart=", "-p", str(p.pid)], capture_output=True,
                                 text=True).stdout.strip()
        (run_dir / f"{name}.start").write_text(started + "\n", encoding="utf-8")
        return p.pid

    def _reap(self, p: subprocess.Popen) -> None:
        if p.poll() is None:
            p.kill()
        p.wait()

    def set_cwd(self, **pids: str) -> None:
        self.behave(lsof={"cwd": {str(pid): path for pid, path in pids.items()}, "no_real_cwd": True})

    # ------------------------------------------------------------ PID rule

    def test_pid_rule(self) -> None:
        self.install_release()
        p = self.paths()
        pid = self.spawn("server", f"{p.app}/apps/server/")
        self.assertTrue(stack.is_running(p, "server"))
        (p.run_dir / "server.start").write_text("Mon Jan  1 00:00:00 2001\n", encoding="utf-8")
        self.assertFalse(stack.is_running(p, "server"))
        (p.run_dir / "server.start").unlink()  # an old PID file without .start: pattern only
        self.assertTrue(stack.is_running(p, "server"))
        (p.run_dir / "server.pid").write_text(f"{pid}\n", encoding="utf-8")
        self.spawn("console", "/somewhere/else/apps/console/")
        self.assertFalse(stack.is_running(p, "console"))
        self.assertFalse(stack.is_running(p, "runner"))
        self.assertFalse(stack.is_running(p, "nope"))
        names = [s.name for s in stack.services(p)]
        self.assertEqual(names, ["server", "cron", "runner", "bridge", "console", "openmausbot"])

    # ------------------------------------------------------------ start and stop

    def test_start_writes_only_to_start_log_and_stop_reports_survivor(self) -> None:
        self.install_release()
        ctx = self.ctx()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = stack.start(ctx, quiet=True)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        log = (self.app_home / "logs" / "start.log").read_text(encoding="utf-8")
        self.assertIn("1/9 Kiểm tra công cụ trên máy", log)
        self.assertIn("9/9 Console cho nhân viên", log)
        p = ctx.paths
        alive = {s.name for s in stack.services(p) if s.alive}
        self.assertEqual(alive, {"server", "cron", "runner", "bridge", "console"})
        start = self.calls("start_local.sh")[0]
        self.assertEqual(start["cwd"], os.path.realpath(self.app_home / "app"))
        self.behave(stop_local={"survive": ["runner"]})
        self.assertFalse(stack.stop(ctx))
        self.assertTrue(stack.is_running(p, "runner"))
        self.behave(stop_local={"survive": []})
        self.assertTrue(stack.stop(ctx))
        self.assertEqual({s.name for s in stack.services(p) if s.alive}, set())

    def test_start_prints_one_line_unless_quiet_and_returns_exit_code(self) -> None:
        self.install_release()
        self.behave(start_local={"fail_at_step": 4})
        ctx = self.ctx()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = stack.start(ctx)
        self.assertEqual(code, 1)
        from thomhouse_installer.text_vi import t

        self.assertEqual(out.getvalue().strip(), t("core.starting"))
        self.assertIn("stub failure at step 4", (self.app_home / "logs" / "start.log").read_text(encoding="utf-8"))

    def test_start_refused_when_moved_out_or_update_open(self) -> None:
        self.install_release()
        ctx = self.ctx()
        state.set_moved_out(ctx.paths, {"image_name": "x.dmg", "image_sha256": "0" * 64})
        with self.assertRaises(context.Exit) as cm:
            stack.start(ctx, during_update=True)
        self.assertEqual((cm.exception.code, cm.exception.key), (3, "core.moved_out"))
        state.clear_moved_out(ctx.paths)
        state.update_set(ctx.paths, {"state": "running", "file": "/x/f.command", "phases": {"U9": "done"}})
        with self.assertRaises(context.Exit) as cm:
            stack.start(ctx)
        self.assertEqual((cm.exception.code, cm.exception.key), (3, "core.update_open"))
        self.assertEqual(cm.exception.fmt["file"], "/x/f.command")
        self.assertEqual(self.calls("start_local.sh"), [])
        self.assertEqual(stack.start(ctx, quiet=True, during_update=True), 0)
        self.assertEqual(len(self.calls("start_local.sh")), 1)
        self.assertTrue(stack.stop(ctx))

    # ------------------------------------------------------------ child environment

    def test_child_env_contents(self) -> None:
        self.install_release()
        p = self.paths()
        os.environ.update({"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_AUTH_TOKEN": "x", "CLAUDE_CODE_OAUTH_TOKEN": "y",
                           "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_EFFORT": "high",
                           "CLAUDE_CONFIG_DIR": "/somewhere", "PROFILE_LLM_ENABLED": "true",
                           "ZALO_CONFIG_DIR": str(self.zalo_config), "THOMHOUSE_LOCK_OWNER": "123"})
        env = proc.child_env(p)
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE",
                     "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_EFFORT", "CLAUDE_CONFIG_DIR"):
            self.assertNotIn(name, env)
        self.assertEqual(env["PROFILE_LLM_ENABLED"], "false")
        self.assertEqual(env["DISABLE_UPDATES"], "1")
        self.assertEqual(env["ZALO_AGENT_NO_UPDATE_CHECK"], "1")
        self.assertEqual(env["WRANGLER_SEND_METRICS"], "false")
        self.assertEqual(env["npm_config_cache"], str(self.app_home / "cache" / "npm"))
        self.assertEqual(env["THOMHOUSE_APP_HOME"], str(self.app_home))
        self.assertEqual(env["THOMHOUSE_BOT_HOME"], str(self.bot_home))
        self.assertEqual(env["THOMHOUSE_LOCK_OWNER"], "123")
        self.assertEqual(env["ZALO_CONFIG_DIR"], str(self.zalo_config))
        first = env["PATH"].split(":")[:3]
        self.assertEqual(first, [str(self.app_home / "runtime" / "node" / "bin"),
                                 str(self.app_home / "runtime" / "python" / "bin"),
                                 str(self.app_home / "runtime" / "bin")])
        extra = proc.child_env(p, {"CLAUDE_CONFIG_DIR": "/acc/main", "ANTHROPIC_API_KEY": "z",
                                   "PROFILE_LLM_ENABLED": "true", "no_proxy": "example.org"})
        self.assertEqual(extra["CLAUDE_CONFIG_DIR"], "/acc/main")
        self.assertNotIn("ANTHROPIC_API_KEY", extra)
        self.assertEqual(extra["PROFILE_LLM_ENABLED"], "false")
        self.assertEqual(extra["no_proxy"], "example.org,127.0.0.1,localhost,::1")
        checkout = self.paths(self.make_checkout())
        self.assertEqual(proc.child_env(checkout)["PATH"], os.environ["PATH"])

    def test_child_env_claude_install(self) -> None:
        p = self.paths(self.make_checkout())
        os.environ["DISABLE_AUTOUPDATER"] = "1"
        env = proc.child_env(p, claude_install=True)
        self.assertNotIn("DISABLE_UPDATES", env)
        self.assertNotIn("DISABLE_AUTOUPDATER", env)
        self.assertEqual(proc.child_env(p)["DISABLE_UPDATES"], "1")

    def test_child_env_loopback_bypass(self) -> None:
        self.install_release()
        os.environ.clear()
        os.environ.update(self.env_without_no_proxy())
        self.assertEqual(os.environ["http_proxy"], "http://127.0.0.1:9")
        ctx = self.ctx()
        env = proc.child_env(ctx.paths)
        for name in ("no_proxy", "NO_PROXY"):
            items = env[name].split(",")
            for host in ("127.0.0.1", "localhost", "::1"):
                self.assertIn(host, items)
        self.assertEqual(env["http_proxy"], "http://127.0.0.1:9")
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:9")
        code = "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=5).read().decode())"
        url = self.server.url + "/health"
        ok = subprocess.run([sys.executable, "-I", "-c", code, url], env=env, capture_output=True, text=True,
                            timeout=30)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("zalo_mode", ok.stdout)
        # Control: the same call without no_proxy goes to the dead proxy and fails.
        raw = dict(env)
        raw.pop("no_proxy")
        raw.pop("NO_PROXY")
        bad = subprocess.run([sys.executable, "-I", "-c", code, url], env=raw, capture_output=True, text=True,
                             timeout=30)
        self.assertNotEqual(bad.returncode, 0)
        # The start_local.sh child gets the loopback names as well.
        self.assertEqual(stack.start(ctx, quiet=True), 0)
        recorded = json.loads((self.tmp / "start-env.json").read_text(encoding="utf-8"))
        for host in ("127.0.0.1", "localhost", "::1"):
            self.assertIn(host, recorded["no_proxy"].split(","))
            self.assertIn(host, recorded["NO_PROXY"].split(","))
        self.assertEqual(recorded["DISABLE_UPDATES"], "1")
        self.assertIn("http_proxy", recorded["names"])
        self.assertNotIn("ANTHROPIC_API_KEY", recorded["names"])
        self.assertTrue(stack.stop(ctx))

    # ------------------------------------------------------------ loopback HTTP

    def test_http_json(self) -> None:
        ctx = self.ctx(self.make_checkout())
        self.assertEqual(stack.http_json(ctx, "GET", "/health")[0], 200)
        self.assertEqual(stack.http_json(ctx, "GET", "/health")[1]["zalo_mode"], "personal")
        status, body = stack.http_json(ctx, "GET", "/staff/flags", token="t" * 20)
        self.assertEqual(status, 200)
        self.assertTrue(self.server_calls()[-1]["auth"])
        self.server.set_route("GET /staff/chat-facts/eligible", 404, {"error": "not_found"})
        self.assertEqual(stack.http_json(ctx, "GET", "/staff/chat-facts/eligible")[0], 404)
        self.assertEqual(stack.http_json(ctx, "POST", "/runner/status", body={})[0], 400)
        status, body = stack.http_json(ctx, "GET", self.server.url + "/")
        self.assertEqual((status, body), (200, None))
        with self.assertRaises(ValueError):
            stack.http_json(ctx, "GET", "http://example.org/health")
        dead = dict(ctx.env)
        dead["THOMHOUSE_SERVER_URL"] = "http://127.0.0.1:9"
        ctx.env = dead
        self.assertEqual(stack.http_json(ctx, "GET", "/health", timeout=1), (0, None))

    def test_health_gate(self) -> None:
        self.install_release()
        ctx = self.ctx()
        self.assertEqual(set(stack.health_gate(ctx)), {"processes"})
        self.assertEqual(stack.start(ctx, quiet=True), 0)
        self.assertEqual(stack.health_gate(ctx), [])
        self.server.set_route("GET /health", 200, {"ok": True, "zalo_mode": "mock"})
        self.assertEqual(stack.health_gate(ctx), ["server_health"])
        self.assertTrue(stack.stop(ctx))

    # ------------------------------------------------------------ other installations

    def test_other_stack_by_command_line_and_working_folder(self) -> None:
        self.install_release()
        p = self.paths()
        other = self.make_checkout("other-checkout")
        server = self.spawn("server", f"{other}/apps/server/")
        runner = self.spawn("runner", "runner.main", "run", cwd=other / "apps" / "runner")
        cron = self.spawn("cron", "cron-tick", "http://127.0.0.1:8787/__scheduled", cwd=self.tmp)
        self.set_cwd(**{str(server): str(other / "apps" / "server"), str(runner): str(other / "apps" / "runner"),
                        str(cron): str(self.tmp)})
        found = {s.name: s for s in stack.other_stacks(p)}
        # server by its command line, runner by its working folder, cron because it follows the server
        self.assertEqual(set(found), {"server", "runner", "cron"})
        self.assertEqual(found["server"].pid, server)
        # Seen from the checkout itself, the same services are its own.
        self.assertEqual(stack.other_stacks(self.paths(other)), [])
        # A stale PID file (another start time) is not a running stack.
        (p.run_dir / "server.start").write_text("Mon Jan  1 00:00:00 2001\n", encoding="utf-8")
        self.assertEqual({s.name for s in stack.other_stacks(p)}, {"runner"})

    def test_checkout_stack_seen_from_device(self) -> None:
        self.install_release()
        p = self.paths()
        other = self.make_checkout("other-checkout")
        # A checkout's server started by hand whose command line still matches this pattern is impossible, so the
        # device sees the checkout's runner (working folder) and the cron ticker that follows the checkout's server.
        runner = self.spawn("runner", "runner.main", "run", cwd=other / "apps" / "runner")
        bridge = self.spawn("bridge", "bridge.main", "run", cwd=other / "apps" / "zalo-bridge")
        self.set_cwd(**{str(runner): str(other / "apps" / "runner"), str(bridge): str(other / "apps" / "zalo-bridge")})
        found = {s.name for s in stack.other_stacks(p)}
        self.assertEqual(found, {"runner", "bridge"})

    def test_own_stack_not_other(self) -> None:
        self.install_release()
        ctx = self.ctx()
        p = ctx.paths
        self.behave(start_local={"rooms": True})
        self.assertEqual(stack.start(ctx, quiet=True), 0)
        real = os.path.realpath(p.app)
        services = {s.name: s for s in stack.services(p)}
        self.assertTrue(all(services[n].alive for n in ("server", "cron", "runner", "bridge", "console",
                                                         "openmausbot")))
        self.set_cwd(**{
            str(services["runner"].pid): f"{real}/apps/runner",
            str(services["bridge"].pid): f"{real}/apps/zalo-bridge",
            str(services["openmausbot"].pid): str(self.bot_home / "openmausbot"),
            str(services["server"].pid): f"{real}/apps/server",
            str(services["console"].pid): f"{real}/apps/console",
            str(services["cron"].pid): str(self.tmp / "elsewhere"),
        })
        self.assertEqual(stack.other_stacks(p), [])
        self.assertTrue(stack.stop(ctx))
        # The checkout's runner and server, seen from the checkout's own paths, are not "other" either; seen from
        # the device, the runner (working folder) and the cron ticker following a foreign server are.
        other = self.make_checkout("other-checkout")
        server = self.spawn("server", f"{p.app}/apps/server/", "--persist-to", str(other))
        runner = self.spawn("runner", "runner.main", "run", cwd=other / "apps" / "runner")
        self.set_cwd(**{str(server): str(other / "apps" / "server"), str(runner): str(other / "apps" / "runner")})
        found = {s.name for s in stack.other_stacks(p)}
        self.assertEqual(found, {"runner"})
