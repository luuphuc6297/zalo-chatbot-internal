"""safety.py and the safety checks of the doctor: listeners beyond this Mac (check 41), forbidden OpenMausBot options
(check 42), API keys and PROFILE_LLM_ENABLED (checks 24, 25), and no secret, email, Zalo id or name in any doctor
output (invariants 1, 2, 4, 6, 7, 8; rev F16)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time

from tests.support import InstallerTestCase
from tests.test_doctor_checks import TB, DoctorFixture
from thomhouse_installer import doctor, envs, safety, stack

LEADER = textwrap.dedent("""
    import subprocess, sys, time
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", sys.argv[1]])
    with open(sys.argv[2], "w") as f:
        f.write(str(child.pid))
    time.sleep(120)
""")


def _kill_group(leader: subprocess.Popen) -> None:
    try:
        os.killpg(leader.pid, 9)
    except ProcessLookupError:
        pass
    leader.wait()


class SafetyHelpersTest(InstallerTestCase):
    def test_forbidden_platform_args(self) -> None:
        f = safety.forbidden_platform_args
        self.assertEqual(f(["node", "/x/openmausbot", "serve", "--port", "8799"]), [])
        self.assertEqual(f(["openmausbot", "serve", "--tunnel"]), ["--tunnel"])
        self.assertEqual(f(["openmausbot", "login"]), ["login"])
        self.assertEqual(f(["openmausbot", "serve", "--domain=bot.example.org", "--lan", "--lan"]),
                         ["--domain", "--lan"])
        self.assertEqual(f(["openmausbot", "serve", "--public-url=https://x.example/?t=secret-value"]),
                         ["--public-url"])
        self.assertEqual(f(["openmausbot", "serve", "--data-dir", "/Users/a/login-x/data", "--label", "thomhouse"]),
                         [])
        self.assertEqual(f(["--tunnelx", "--relayed", "logins", "relogin", "--tailscale-ish"]), [])
        self.assertEqual(f(["--relay", "--tailscale"]), ["--relay", "--tailscale"])
        self.assertEqual(safety.FORBIDDEN_PLATFORM_ARGS,
                         ("--tunnel", "--lan", "--relay", "--domain", "--public-url", "--tailscale", "login"))

    def _leader(self, *args: str) -> tuple[subprocess.Popen, int]:
        pid_file = self.tmp / f"child-{len(args)}-{time.monotonic_ns()}.pid"
        leader = subprocess.Popen([sys.executable, "-c", LEADER, str(self.tmp), str(pid_file), *args],
                                  start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(_kill_group, leader)
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        return leader, int(pid_file.read_text().strip())

    def test_group_pids_process_argv_and_listen_sockets(self) -> None:
        leader, child = self._leader("--label", "thomhouse")
        members = safety.group_pids([leader.pid])
        self.assertIn(leader.pid, members)
        self.assertIn(child, members)
        self.assertEqual(safety.group_pids([]), [])
        argv = safety.process_argv(leader.pid)
        self.assertEqual(argv[-2:], ["--label", "thomhouse"])
        self.assertEqual(safety.process_argv(999999), [])
        self.behave(lsof={"listen": [["node", child, "127.0.0.1", 8787], ["node", child, "*", 8800],
                                     ["workerd", leader.pid, "::1", 9229], ["other", 4242, "*", 22]]})
        found = safety.listen_sockets([leader.pid, child])
        self.assertEqual(sorted(found), sorted([(child, "127.0.0.1", 8787), (child, "*", 8800),
                                                (leader.pid, "[::1]", 9229)]))
        before = len(self.calls("lsof"))
        self.assertEqual(safety.listen_sockets([]), [])
        self.assertEqual(len(self.calls("lsof")), before)  # never `lsof -p ""`
        call = self.calls("lsof")[-1]["argv"]
        self.assertEqual(call[:4], ["-nP", "-a", "-p", ",".join(str(p) for p in sorted([leader.pid, child]))])
        self.assertEqual(call[4:], ["-iTCP", "-sTCP:LISTEN"])


class SafetyChecksTest(DoctorFixture, InstallerTestCase):
    def spawn_rooms(self, *extra: str) -> tuple[subprocess.Popen, int]:
        """An OpenMausBot stand-in registered in BOT_HOME/run like start_local.sh does, with one child in its
        process group; returns the leader and the child's PID."""
        app = self.app_home / "app"
        pid_file = self.tmp / f"rooms-child-{time.monotonic_ns()}.pid"
        leader = subprocess.Popen([sys.executable, "-c", LEADER, str(self.tmp), str(pid_file),
                                   f"{app}/tools/openmausbot/node_modules/.bin/openmausbot", "serve", *extra],
                                  start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(_kill_group, leader)
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        run_dir = self.bot_home / "run"
        (run_dir / "openmausbot.pid").write_text(f"{leader.pid}\n")
        started = subprocess.run(["ps", "-o", "lstart=", "-p", str(leader.pid)], capture_output=True,
                                 text=True).stdout.strip()
        (run_dir / "openmausbot.start").write_text(started + "\n")
        return leader, int(pid_file.read_text().strip())

    def test_listeners_beyond_this_mac(self) -> None:
        self.make_installed(rooms=False)
        services = {s.name: s for s in stack.services(self.paths())}
        server = services["server"].pid
        self.assert_line("listen_local_only", "[ĐẠT] Chỉ mở trên máy này: đúng")
        self.behave(lsof={"listen": [["node", server, "127.0.0.1", 8787], ["node", server, "::1", 8787]]})
        self.assert_line("listen_local_only", "[ĐẠT] Chỉ mở trên máy này: đúng")
        self.behave(lsof={"listen": [["node", server, "*", 8787]]})
        stop_fix = f"Cách sửa: anh tắt chatbot ngay bằng {TB} stop và báo người phụ trách."
        self.assert_line("listen_local_only", f"[LỖI] Chỉ mở trên máy này: server đang mở cổng 8787 ra ngoài máy. "
                                              f"{stop_fix}")
        # A *:8800 socket of a process in OpenMausBot's group (its second port).
        leader, child = self.spawn_rooms("--port", "8799")
        self.behave(lsof={"listen": [["node", leader.pid, "127.0.0.1", 8799], ["node", child, "*", 8800]]})
        self.assert_line("listen_local_only", f"[LỖI] Chỉ mở trên máy này: openmausbot đang mở cổng 8800 ra ngoài "
                                              f"máy. {stop_fix}")
        # The listener daemon, found through `listener status`, on a LAN address.
        daemon = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", str(self.tmp)],
                                  start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(daemon.wait)
        self.addCleanup(daemon.kill)
        self.behave(bridge={"listener": {"status": [0, {"running": True, "pid": daemon.pid}]}},
                    lsof={"listen": [["node", daemon.pid, "192.168.1.5", 18927]]})
        self.assert_line("listen_local_only", f"[LỖI] Chỉ mở trên máy này: listener đang mở cổng 18927 ra ngoài máy. "
                                              f"{stop_fix}")
        self.behave(lsof={"listen": [["node", daemon.pid, "127.0.0.1", 18927]]})
        self.assert_line("listen_local_only", "[ĐẠT] Chỉ mở trên máy này: đúng")

    def test_forbidden_openmausbot_option(self) -> None:
        self.make_installed(rooms=False)
        leader, _ = self.spawn_rooms("--tunnel")
        self.assert_line("openmausbot_options", "[LỖI] Tùy chọn của OpenMausBot: OpenMausBot đang chạy với --tunnel. "
                                                f"Cách sửa: anh tắt chatbot ngay bằng {TB} stop và báo người phụ "
                                                "trách.")
        _kill_group(leader)
        self.spawn_rooms("--data-dir", "/Users/a/login-x/data", "--label", "thomhouse")
        self.assert_line("openmausbot_options", "[ĐẠT] Tùy chọn của OpenMausBot: đúng")

    def test_api_key_and_profile_llm_in_env_files(self) -> None:
        self.make_installed(start=False)
        app = self.app_home / "app"
        runner_env = app / "apps" / "runner" / ".env"
        original = runner_env.read_text()
        runner_env.write_text(original + "ANTHROPIC_API_KEY=sk-ant-planted-key-0000000004\n")
        self.assert_line("no_api_key", "[LỖI] Khóa API Anthropic: apps/runner/.env đặt ANTHROPIC_API_KEY; chatbot chỉ "
                                       f"dùng gói Claude. Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart")
        runner_env.write_text(original)
        bridge_env = app / "apps" / "zalo-bridge" / ".env"
        bridge_env.write_text(bridge_env.read_text() + "PROFILE_LLM_ENABLED=true\n")
        self.assert_line("profile_llm_off", "[LỖI] Phân tích bằng model: apps/zalo-bridge/.env bật PROFILE_LLM_ENABLED. "
                                            f"Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart")
        console = app / "apps" / "console" / ".env.local"
        console.write_text("ANTHROPIC_AUTH_TOKEN=planted-console-token-0005\n")
        bridge_env.write_text(bridge_env.read_text().replace("PROFILE_LLM_ENABLED=true\n", ""))
        self.assert_line("no_api_key", "[LỖI] Khóa API Anthropic: apps/console/.env.local đặt ANTHROPIC_AUTH_TOKEN; "
                                       f"chatbot chỉ dùng gói Claude. Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart")

    def test_no_secret_email_zalo_id_or_name_in_output(self) -> None:
        self.make_installed()
        app = self.app_home / "app"
        planted = ["sk-ant-planted-key-0000000006", "planted-oauth-0000000007"]
        runner_env = app / "apps" / "runner" / ".env"
        runner_env.write_text(runner_env.read_text() + f"ANTHROPIC_API_KEY={planted[0]}\n")
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = planted[1]
        self.write_pool({"label": "main"}, logins={"main": "max"})
        secrets = set(planted)
        for name in ("server", "runner", "bridge"):
            for key, value in envs.read(self.paths().env_file(name)).items():
                if key in ("RUNNER_TOKEN", "STAFF_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET", "ZALO_OA_SECRET_KEY",
                           "ZALO_APP_SECRET_KEY"):
                    secrets.add(value)
        self.assertGreaterEqual(len(secrets), 5)
        forbidden = secrets | {"x@example.invalid", "999000111", "Ten Gia"}
        # The bridge doctor's zalo_login detail holds the Zalo id, and roles hold Zalo user ids.
        self.behave(bridge={"doctor": {"zalo_login": "ok", "listener": "fail", "room_platform": "ok"}})
        texts = []
        for kwargs in ({}, {"json": True}, {"strict": True}):
            code, out = self.run_doctor(self.ctx(), **kwargs)
            texts.append(out)
            if kwargs.get("json"):
                json.loads(out)
        joined = "\n".join(texts)
        self.assertIn("ANTHROPIC_API_KEY", joined)  # the name is shown, the value never
        for value in forbidden:
            self.assertNotIn(value, joined, value)
        for log in (self.app_home / "logs").glob("*.log"):
            text = log.read_text(encoding="utf-8", errors="replace")
            for value in forbidden:
                self.assertNotIn(value, text, f"{log.name}: {value}")
        # No staff call carries anything but GET; no runner call at all.
        self.assertTrue(all(c["method"] == "GET" for c in self.server_calls()))
        self.assertFalse([c for c in self.server_calls() if c["path"].startswith("/runner/")])
