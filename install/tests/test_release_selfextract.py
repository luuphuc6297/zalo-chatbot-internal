"""The .command header (install/selfextract.sh.in, 16.2.6, 16.4.6, 16.5): refusals that write nothing, the payload
hash, the release id question, the signature, the bootstrap lock, --dry-run, --doctor and the whole first-install
chain header -> bootstrap.sh -> Python CLI on one PID (rev F5, F6, F19, rev check).

Most chain tests reach the CLI through the probe steps.py of the kit, which records argv, environment and the
bootstrap lock; the dry-run plan and `test_real_chain_*` run the real steps.py."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
from pathlib import Path

from tests.fakes_release.kit import PY_URL, ReleaseTestCase, snapshot
from tests.test_core_text import STEP_TITLES
from thomhouse_installer import release
from thomhouse_installer.text_vi import t

INSTALL = Path(__file__).resolve().parent.parent


class HeaderRefusalTest(ReleaseTestCase):
    def assert_nothing_written(self, before: dict) -> None:
        self.assertEqual(snapshot(self.home), before)

    def test_corrupted_payload_exits_3_before_anything_is_written(self) -> None:
        command = self.release_file()
        data = bytearray(command.read_bytes())
        data[-100] ^= 0xFF
        command.write_bytes(bytes(data))
        before = snapshot(self.home)
        res = self.run_header(command, "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn(t("release.damaged"), res.stdout)
        self.assert_nothing_written(before)

    def test_truncated_file_is_damaged(self) -> None:
        command = self.release_file()
        command.write_bytes(command.read_bytes()[:-500])
        res = self.run_header(command, "--trust-channel")
        self.assertEqual(res.returncode, 3)
        self.assertIn(t("release.damaged"), res.stdout)

    def test_unsupported_systems_exit_3_with_their_sentence(self) -> None:
        proc_version = self.tmp / "proc-version"
        proc_version.write_text("Linux version 5.15.90.1-microsoft-standard-WSL2\n", encoding="utf-8")
        tail = "Anh báo người gửi file; chương trình chưa thay đổi gì trên máy này."
        cases = [
            ({"os": "Linux"}, {}, "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; máy Linux chưa được hỗ trợ.",
             tail),
            ({"os": "Linux"}, {"THOMHOUSE_PROC_VERSION": str(proc_version)},
             "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; Windows và WSL chưa được hỗ trợ.", tail),
            ({"os": "MINGW64_NT-10.0-22631"}, {},
             "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; máy Windows chưa được hỗ trợ.", tail),
            ({"os": "SunOS"}, {},
             "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; hệ điều hành SunOS chưa được hỗ trợ.", tail),
            ({"macos": "13.4"}, {},
             "Máy đang chạy macOS 13.4; chatbot cần macOS 13.5 trở lên. Anh cập nhật macOS rồi chạy lại.", None),
            ({"uid": 0}, {}, "Anh chạy lại lệnh cài bằng tài khoản thường của máy, không dùng sudo.", None),
        ]
        command = self.release_file()
        for system, extra, sentence, second in cases:
            with self.subTest(system=system):
                (self.tmp / "behaviour.json").write_text("{}", encoding="utf-8")
                self.behave(system=system)
                env = dict(self.env)
                env.update(extra)
                before = snapshot(self.home)
                res = self.run_header(command, "--trust-channel", "--yes", env=env)
                self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
                lines = res.stdout.splitlines()
                self.assertIn(sentence, lines)
                if second:
                    self.assertEqual(lines[-1], second)
                self.assert_nothing_written(before)

    def test_intel_mac(self) -> None:
        self.behave(system={"cpu": "x64"})
        command = self.release_file()
        res = self.run_header(command, "--trust-channel")  # no terminal: the question is answered k
        self.assertEqual(res.returncode, 4)
        self.assertIn("Máy Intel chưa được chạy thử. Anh vẫn cài? [c = có / k = không]", res.stdout)
        res = self.run_header(command, "--trust-channel", "--yes")  # c, but the test pins have no darwin-x64 build
        self.assertEqual(res.returncode, 3)
        self.assertIn("File cài này chưa có bản cho máy Intel.", res.stdout)
        self.assertFalse((self.app_home / "releases").exists())

    def test_whitespace_in_app_home(self) -> None:
        env = dict(self.env, THOMHOUSE_APP_HOME=str(self.home / "Thom House"))
        res = self.run_header(self.release_file(), "--trust-channel", env=env)
        self.assertEqual(res.returncode, 3)
        self.assertIn("có dấu cách", res.stdout)
        self.assertFalse((self.home / "Thom House").exists())

    def test_moved_out_mark_refuses(self) -> None:
        self.bot_home.mkdir(parents=True)
        (self.bot_home / "moved-out.json").write_text("{}", encoding="utf-8")
        res = self.run_header(self.release_file(), "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 3)
        self.assertIn(t("core.moved_out", tb="x").splitlines()[0], res.stdout)
        self.assertFalse(self.app_home.exists())

    def test_bad_option_exits_2(self) -> None:
        res = self.run_header(self.release_file(), "--frobnicate")
        self.assertEqual(res.returncode, 2)
        self.assertIn("Lệnh gõ chưa đúng", res.stdout)


class InstalledDeviceTest(ReleaseTestCase):
    def test_installed_device_refuses(self) -> None:
        self.app_home.mkdir(parents=True)
        (self.app_home / "installed.json").write_text('{"schema": 1, "version": "1.3.0"}', encoding="utf-8")
        command = self.release_file()
        expected = t("release.already_installed", file=str(command))
        for args in (("--trust-channel", "--yes"), ("--dry-run",)):
            with self.subTest(args=args):
                before = snapshot(self.home)
                res = self.run_header(command, *args)
                self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
                self.assertIn(expected, res.stdout)
                self.assertEqual(snapshot(self.home), before)
                self.assertFalse((self.app_home / "releases").exists())

    def test_doctor_still_runs_on_an_installed_device(self) -> None:
        self.app_home.mkdir(parents=True)
        (self.app_home / "installed.json").write_text('{"schema": 1, "version": "1.4.0"}', encoding="utf-8")
        res = self.run_header(self.release_file(), "--doctor")
        self.assertIn("[LỖI] Python: chưa có Python 3.14.6. Cách sửa: bash ~/ThomHouse/app/install/bootstrap.sh "
                      "--python-only", res.stdout)


class DoctorAndDryRunTest(ReleaseTestCase):
    def test_doctor_prints_lines_1_to_5_and_writes_nothing(self) -> None:
        command = self.release_file()
        before = snapshot(self.home)
        res = self.run_header(command, "--doctor")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 5, res.stdout)
        self.assertEqual(lines[0], "[ĐẠT] Hệ điều hành: macOS 15.1")
        self.assertEqual(lines[1], "[ĐẠT] Chip: Apple Silicon")
        self.assertRegex(lines[2], r"^\[ĐẠT\] Dung lượng trống: \d+ GB$")
        self.assertEqual(lines[3], "[ĐẠT] Công cụ của macOS: đủ")
        self.assertEqual(lines[4], "[LỖI] Python: chưa có Python 3.14.6. Cách sửa: anh chạy lại file "
                                   "thomhouse-1.4.0.command.")
        self.assertEqual(snapshot(self.home), before)

    def test_doctor_lines_for_old_macos_and_intel(self) -> None:
        self.behave(system={"macos": "13.4", "cpu": "x64"})
        res = self.run_header(self.release_file(), "--doctor")
        self.assertIn("[LỖI] Hệ điều hành: macOS 13.4, chatbot cần 13.5 trở lên. Cách sửa: anh cập nhật macOS "
                      "trong Cài đặt hệ thống rồi chạy lại.", res.stdout)
        self.assertIn("[CHÚ Ý] Chip: máy Intel chưa được chạy thử. Cách sửa: nếu gặp lỗi, anh gửi kết quả lệnh "
                      "này cho người phụ trách.", res.stdout)

    def test_dry_run_without_python_leaves_home_identical(self) -> None:
        command = self.release_file()
        env = dict(self.env)
        # The caller's PATH has no Python 3.11+ (only the fakes and the system folders); the header's own tools
        # still run with THOMHOUSE_TOOL_PATH.
        env["PATH"] = ":".join(p for p in env["PATH"].split(":") if p != str(self.pybin))
        before = snapshot(self.home)
        res = self.run_header(command, "--dry-run", env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(snapshot(self.home), before)
        lines = res.stdout.splitlines()
        self.assertEqual(lines[0], "Kế hoạch cài chatbot thom house bản 1.4.0 (chạy thử, máy không thay đổi gì):")
        self.assertEqual(lines[1], "  1. [đã xong] Kiểm tra file cài đặt")
        self.assertTrue(lines[4].startswith("  4. [sẽ làm] Cài Python: Python 3.14.6 từ github.com, "), lines[4])
        self.assertTrue(lines[4].endswith(" MB, vào ~/ThomHouse/runtime"), lines[4])
        self.assertEqual(lines[-1], " 25. [sẽ làm] Kiểm tra lần cuối")
        self.assertIn(" 10. [bỏ qua] Chuyển dữ liệu từ máy cũ", lines)
        self.assertEqual(list((self.tmp / "tmp").glob("thomhouse-*")), [])

    def test_dry_run_titles_equal_the_step_titles(self) -> None:
        text = (INSTALL / "selfextract.sh.in").read_text(encoding="utf-8")
        for n in range(1, 26):
            self.assertIn(STEP_TITLES[n], text, n)

    def test_dry_run_runs_the_payload_cli_and_takes_no_lock(self) -> None:
        command = self.release_file()
        before = snapshot(self.home)
        res = self.run_header(command, "--dry-run", "--skip-human")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls("steps.cmd_install")
        self.assertEqual(len(calls), 1, res.stdout)
        self.assertTrue(calls[0]["dry_run"] and calls[0]["from_bootstrap"])
        self.assertIn("--skip-human", calls[0]["argv"])
        self.assertEqual(calls[0]["release_file"], str(command))
        self.assertIn("/thomhouse-dry-run.", calls[0]["code_root"])
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.app_home / ".bootstrap.lock.d").exists())
        self.assertFalse((self.app_home / "releases").exists())
        self.assertEqual(list((self.tmp / "tmp").glob("thomhouse-*")), [])

    def test_dry_run_with_the_real_steps_prints_each_step_once(self) -> None:
        command = self.release_file(real_steps=True)
        before = snapshot(self.home)
        res = self.run_header(command, "--dry-run")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(snapshot(self.home), before)  # 16.4.5: the payload CLI writes no log either
        lines = res.stdout.splitlines()
        self.assertEqual(lines[0], "Kế hoạch cài chatbot thom house bản 1.4.0 (chạy thử, máy không thay đổi gì):")
        numbered = [x for x in lines if re.match(r"^ {0,2}\d{1,2}\. \[", x)]
        self.assertEqual([int(x.split(".")[0]) for x in numbered], list(range(1, 26)), res.stdout)
        for n in range(1, 26):
            self.assertIn(STEP_TITLES[n], numbered[n - 1])
        self.assertEqual(lines.count(lines[0]), 1)
        self.assertIn(" 10. [bỏ qua] Chuyển dữ liệu từ máy cũ", lines)
        self.assertFalse((self.app_home / ".bootstrap.lock.d").exists())
        self.assertFalse((self.app_home / "releases").exists())
        self.assertEqual(list((self.tmp / "tmp").glob("thomhouse-*")), [])


class ReleaseIdAndSignatureTest(ReleaseTestCase):
    def test_release_id_shown_and_k_exits_4(self) -> None:
        command = self.release_file()
        digest = subprocess.run(["shasum", "-a", "256", str(command)], capture_output=True, text=True).stdout[:16]
        expected = "-".join(digest.upper()[i:i + 4] for i in range(0, 16, 4))
        res = self.run_header(command, answers="k\n")
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertIn(f"Mã bản cài: {expected}. Anh so mã này với mã hiện trên máy đã tạo file cài.", res.stdout)
        self.assertEqual(release.read_header(command).release_id, expected)
        self.assertFalse(self.app_home.exists(), "the lock folder and APP_HOME are removed again")

    def test_no_terminal_answers_k_and_yes_does_not_answer_the_id(self) -> None:
        res = self.run_header(self.release_file(), "--yes")
        self.assertEqual(res.returncode, 4)
        self.assertIn("tự trả lời k", res.stdout)

    def test_changed_signature_in_header_is_refused(self) -> None:
        command = self.release_file()
        text = command.read_bytes()
        m = re.search(rb'PAYLOAD_SIG_B64="([^"]+)"', text)
        sig = bytearray(m.group(1))
        sig[60] = ord("A") if sig[60] != ord("A") else ord("B")
        command.write_bytes(text[:m.start(1)] + bytes(sig) + text[m.end(1):])
        res = self.run_header(command, "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn(t("release.signature"), res.stdout)
        self.assertFalse((self.app_home / "releases").exists())
        self.assertFalse((self.app_home / ".bootstrap.lock.d").exists())


class FirstInstallChainTest(ReleaseTestCase):
    def test_full_chain_on_one_pid(self) -> None:
        command = self.release_file()
        env = dict(self.env, ANTHROPIC_API_KEY="sk-ant-must-not-pass", PROFILE_LLM_ENABLED="true",
                   no_proxy="corp.example")
        res = self.run_header(command, "--skip-human", env=env, answers="c\nc\n")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("Máy cần thêm các phần mềm dưới đây.", res.stdout)
        rel_dir = self.app_home / "releases" / "1.4.0"
        self.assertEqual(release.verify_manifest(rel_dir), [])
        cached = self.app_home / "cache" / "releases" / "thomhouse-1.4.0.command"
        self.assertEqual(cached.read_bytes(), command.read_bytes())
        self.assertEqual(cached.stat().st_mode & 0o777, 0o600)
        self.assertEqual(os.readlink(self.app_home / "runtime" / "python"), "python-3.14.6-aarch64-apple-darwin")
        self.assertEqual([c["argv"][-1] for c in self.calls("curl")], [PY_URL])
        calls = self.calls("steps.cmd_install")
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertTrue(call["from_bootstrap"])
        self.assertFalse(call["dry_run"])
        self.assertEqual(call["consented"], ["python", "node", "pnpm", "claude_code"])
        self.assertEqual(call["release_file"], str(command))
        self.assertIn("--skip-human", call["argv"])
        self.assertEqual(call["code_root"], str(rel_dir))
        # The dispatcher removed .bootstrap.lock.d because its pid file held the CLI's own PID: one PID from the
        # header through bootstrap.sh to Python (rev F6).
        self.assertFalse(call["lock_dir"])
        self.assertFalse((self.app_home / ".bootstrap.lock.d").exists())
        e = call["env"]
        self.assertIsNone(e["ANTHROPIC_API_KEY"])
        self.assertEqual(e["DISABLE_UPDATES"], "1")
        self.assertEqual(e["PROFILE_LLM_ENABLED"], "false")
        self.assertEqual(e["no_proxy"], "corp.example,127.0.0.1,localhost,::1")
        self.assertEqual(e["NO_PROXY"], e["no_proxy"])
        self.assertTrue(e["PATH"].startswith(f"{self.app_home}/runtime/node/bin:{self.app_home}/runtime/python/bin:"
                                             f"{self.app_home}/runtime/bin:"))
        self.assertEqual(e["THOMHOUSE_APP_HOME"], str(self.app_home))
        self.assertEqual((self.app_home.stat().st_mode & 0o777), 0o700)

    def test_retry_after_failed_bootstrap(self) -> None:
        command = self.release_file()
        self.behave(curl={"fail": {PY_URL: 7}})
        res = self.run_header(command, "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn(f"Chưa tải được Python 3.14.6 từ github.com vì máy không kết nối được mạng.", res.stdout)
        self.assertIn(f"Anh kiểm tra mạng rồi chạy lại: bash {command}", res.stdout)
        self.behave(curl={"fail": {}})
        res = self.run_header(command, "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(len(self.calls("steps.cmd_install")), 1)

    def test_stale_lock_folder_is_replaced(self) -> None:
        lock = self.app_home / ".bootstrap.lock.d"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("999999\n", encoding="utf-8")  # no such process
        res = self.run_header(self.release_file(), "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def _held_by(self, name: str) -> subprocess.Popen:
        holder = subprocess.Popen(["/bin/bash", "-c", "sleep 60; true", name], start_new_session=True)
        self.addCleanup(self._stop, holder)
        lock = self.app_home / ".bootstrap.lock.d"
        lock.mkdir(parents=True, exist_ok=True)
        (lock / "pid").write_text(f"{holder.pid}\n", encoding="utf-8")
        return holder

    @staticmethod
    def _stop(p: subprocess.Popen) -> None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        p.wait()

    def test_lock_of_a_live_bootstrap_or_header_is_refused(self) -> None:
        command = self.release_file()
        for name in ("/x/releases/1.4.0/install/bootstrap.sh", "/Volumes/USB/thomhouse-1.4.0.command"):
            with self.subTest(holder=name):
                holder = self._held_by(name)
                res = self.run_header(command, "--trust-channel", "--yes")
                self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
                self.assertIn(t("core.locked"), res.stdout)
                self.assertEqual((self.app_home / ".bootstrap.lock.d" / "pid").read_text().strip(), str(holder.pid))
                self._stop(holder)

    def test_install_lock_of_a_live_cli_is_refused(self) -> None:
        holder = subprocess.Popen(["/bin/bash", "-c", "sleep 60; true", "/x/install/thomhouse.py"], start_new_session=True)
        self.addCleanup(FirstInstallChainTest._stop, holder)
        self.app_home.mkdir(parents=True)
        (self.app_home / ".install.lock").write_text(f"{holder.pid}\n", encoding="utf-8")
        res = self.run_header(self.release_file(), "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 3)
        self.assertIn(t("core.locked"), res.stdout)

    def test_existing_verified_release_is_not_unpacked_again(self) -> None:
        command = self.release_file()
        self.assertEqual(self.run_header(command, "--trust-channel", "--yes").returncode, 0)
        marker = self.app_home / "releases" / "1.4.0" / "node_modules"
        marker.mkdir()
        res = self.run_header(command, "--trust-channel", "--yes")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(marker.is_dir(), "a verified release folder is kept as it is")
        consented = [c["consented"] for c in self.calls("steps.cmd_install")]
        self.assertEqual(consented, [["python", "node", "pnpm", "claude_code"], ["node", "pnpm", "claude_code"]])
        self.assertEqual(len(self.calls("curl")), 1, "the second run downloads nothing")

    def test_options_reach_the_cli(self) -> None:
        command = self.release_file()
        menu = self.tmp / "usb" / "thomhouse-menu-x.tar"
        res = self.run_header(command, "--trust-channel", "--yes", "--menu", str(menu), "--move-in",
                              str(self.tmp / "img.dmg"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        argv = self.calls("steps.cmd_install")[0]["argv"]
        self.assertIn("--yes", argv)
        self.assertIn("--trust-channel", argv)
        self.assertEqual(argv[argv.index("--menu") + 1], str(menu))
        self.assertEqual(argv[argv.index("--move-in") + 1], str(self.tmp / "img.dmg"))
        self.assertEqual(json.loads(json.dumps(argv))[0], "install")
