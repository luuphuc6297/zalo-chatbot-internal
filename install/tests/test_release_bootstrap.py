"""install/bootstrap.sh (16.4.6, step 4 of 16.4.3): detection at the launcher's locations only, the plan of 16.4.7,
the decline text, the Python install from the cache or with curl, the download failures and --python-only (rev F5,
F11, F18, rev check). The CLI it execs is the kit's probe steps.py, which records the
options and the environment it was reached with; tests/test_integration_flows.py runs the real chain."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from tests.fakes_release.kit import NODE_URL, PY_NAME, PY_URL, ReleaseTestCase, run_tty, sha256_bytes
from thomhouse_installer.text_vi import t


class BootstrapTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release("1.4.0", link_app=False)
        self.write_release_pins(self.root)
        self.plant_steps_stub(self.root)
        self.release = self.tmp / "usb" / "thomhouse-1.4.0.command"
        self.py_sha = self.kit.pins["python"]["platforms"]["darwin-arm64"]["sha256"]

    def bootstrap(self, *args: str, env: dict | None = None, answers: str | None = None, root: Path | None = None):
        script = (root or self.root) / "install" / "bootstrap.sh"
        cmd = ["/bin/bash", str(script), *args]
        env = env if env is not None else dict(self.env)
        if answers is not None:
            return run_tty(cmd, env=env, answers=answers)
        import subprocess

        return subprocess.run(cmd, cwd="/", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=180)

    def test_plan_lists_each_missing_item_and_k_downloads_nothing(self) -> None:
        res = self.bootstrap("--release-file", str(self.release))
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        out = res.stdout
        for line in (
            t("release.plan_head"),
            t("release.plan_python", v="3.14.6", host="github.com", n=1, folder="~/ThomHouse/runtime"),
            t("release.plan_node", v="24.19.0", host="nodejs.org", n=1, folder="~/ThomHouse/runtime"),
            t("release.plan_pnpm", v="10.32.1", host="registry.npmjs.org", n=3, folder="~/ThomHouse/runtime"),
            t("release.plan_claude", v="2.1.319", n=310),
            t("release.plan_ask"),
            t("release.decline_head", folder="~/ThomHouse"),
            f"  - Python 3.14.6: {PY_URL}",
            f"    SHA-256 {self.py_sha}",
            f"  - Node.js 24.19.0: {NODE_URL}",
            t("release.decline_pnpm", v="10.32.1"),
            t("release.decline_claude", v="2.1.319"),
            "    curl -fsSL https://claude.ai/install.sh | bash -s 2.1.319",
            t("release.decline_tail", folder="~/ThomHouse/cache/downloads/"),
        ):
            self.assertIn(line, out)
        self.assertEqual(self.calls("curl"), [])
        self.assertEqual(self.calls("steps.cmd_install"), [])
        self.assertFalse((self.app_home / "runtime").exists())

    def test_only_missing_items_are_planned(self) -> None:
        self.make_python_runtime()
        node = self.app_home / "runtime" / "node" / "bin"
        node.mkdir(parents=True)
        (node / "node").write_text(f'#!/bin/sh\nexec "{self.env["THOMHOUSE_FAKE_BIN"]}/node" "$@"\n')
        (node / "node").chmod(0o755)
        res = self.bootstrap("--release-file", str(self.release))
        self.assertEqual(res.returncode, 4)
        self.assertNotIn("  - Python", res.stdout)
        self.assertNotIn("  - Node.js", res.stdout)
        self.assertIn("  - pnpm 10.32.1", res.stdout)
        self.assertNotIn("Với Python và Node.js", res.stdout)

    def test_claude_elsewhere_is_only_looked_up(self) -> None:
        other = self.tmp / "otherbin"
        other.mkdir()
        marker = self.tmp / "other-claude-ran"
        (other / "claude").write_text(f"#!/bin/sh\ntouch '{marker}'\necho '9.9.9 (Claude Code)'\n")
        (other / "claude").chmod(0o755)
        env = dict(self.env, PATH=f"{other}:{self.env['PATH']}")
        res = self.bootstrap("--release-file", str(self.release), env=env)
        self.assertEqual(res.returncode, 4)
        self.assertIn(t("release.plan_claude", v="2.1.319", n=310), res.stdout)
        self.assertIn(t("release.plan_claude_other"), res.stdout)
        self.assertFalse(marker.exists(), "a claude outside ~/.local/bin is never run")

    def test_c_installs_python_and_execs_the_cli(self) -> None:
        res = self.bootstrap("--release-file", str(self.release), "--yes", "--skip-human")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([c["argv"][-1] for c in self.calls("curl")], [PY_URL])
        rt = self.app_home / "runtime"
        self.assertEqual(os.readlink(rt / "python"), "python-3.14.6-aarch64-apple-darwin")
        self.assertTrue((self.app_home / "cache" / "downloads" / f"{self.py_sha}.tar.gz").is_file())
        self.assertEqual(list(rt.glob(".tmp-*")), [])
        call = self.calls("steps.cmd_install")[0]
        self.assertTrue(call["from_bootstrap"])
        self.assertEqual(call["consented"], ["python", "node", "pnpm", "claude_code"])
        self.assertEqual(call["release_file"], str(self.release))
        self.assertIn("--skip-human", call["argv"])
        self.assertIn("--yes", call["argv"])

    def test_c_typed_on_a_terminal(self) -> None:
        res = self.bootstrap("--release-file", str(self.release), answers="c\n")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(len(self.calls("steps.cmd_install")), 1)

    def test_file_in_cache_under_its_download_name_is_used_without_curl(self) -> None:
        dl = self.app_home / "cache" / "downloads"
        dl.mkdir(parents=True)
        shutil.copy2(self.fixtures / PY_NAME, dl / PY_NAME)
        res = self.bootstrap("--release-file", str(self.release), "--yes")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.calls("curl"), [])
        self.assertTrue((dl / f"{self.py_sha}.tar.gz").is_file())
        self.assertFalse((dl / PY_NAME).exists())

    def test_wrong_sha256_deletes_the_file_and_exits_1(self) -> None:
        self.behave(curl={"corrupt": [PY_URL]})
        res = self.bootstrap("--release-file", str(self.release), "--yes")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("File Python 3.14.6 tải về không đúng mã kiểm tra nên chương trình đã xóa file đó.", res.stdout)
        self.assertIn(f"Anh chạy lại: bash {self.release}", res.stdout)
        self.assertEqual(list((self.app_home / "cache" / "downloads").iterdir()), [])
        self.assertFalse((self.app_home / "runtime" / "python").exists())
        self.assertEqual(self.calls("steps.cmd_install"), [])

    def test_curl_failures_print_their_text(self) -> None:
        for code, expected in ((7, "Chưa tải được Python 3.14.6 từ github.com vì máy không kết nối được mạng."),
                               (22, "Máy chủ github.com chưa trả file Python 3.14.6. Anh chờ một lúc rồi chạy lại: "
                                    f"bash {self.release}"),
                               (23, "Ổ đĩa của máy không đủ chỗ trống để tải Python 3.14.6.\n"
                                    f"Anh xóa bớt tệp rồi chạy lại: bash {self.release}")):
            with self.subTest(code=code):
                self.behave(curl={"fail": {PY_URL: code}})
                res = self.bootstrap("--release-file", str(self.release), "--yes")
                self.assertEqual(res.returncode, 1)
                self.assertIn(expected, res.stdout)
                if code == 23:
                    self.assertNotIn("không kết nối được mạng", res.stdout)

    def test_second_run_downloads_nothing(self) -> None:
        self.assertEqual(self.bootstrap("--release-file", str(self.release), "--yes").returncode, 0)
        res = self.bootstrap("--release-file", str(self.release), "--yes")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(len(self.calls("curl")), 1)
        self.assertEqual(self.calls("steps.cmd_install")[1]["consented"], ["node", "pnpm", "claude_code"])

    def test_nothing_missing_asks_nothing(self) -> None:
        self.assertEqual(self.bootstrap("--release-file", str(self.release), "--yes").returncode, 0)
        from tests.fakes_release.kit import node_wrapper

        rt = self.app_home / "runtime"
        (rt / "node" / "bin").mkdir(parents=True)
        (rt / "node" / "bin" / "node").write_bytes(node_wrapper())
        (rt / "node" / "bin" / "node").chmod(0o755)
        (rt / "bin").mkdir()
        (rt / "bin" / "pnpm").symlink_to(Path(self.env["THOMHOUSE_FAKE_BIN"]) / "pnpm")
        local = self.home / ".local" / "bin"
        local.mkdir(parents=True)
        (local / "claude").symlink_to(Path(self.env["THOMHOUSE_FAKE_BIN"]) / "claude")
        res =self.bootstrap("--release-file", str(self.release))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("Máy cần thêm", res.stdout)
        call = self.calls("steps.cmd_install")[-1]
        self.assertEqual(call["consented"], [])
        self.assertNotIn("--consented", call["argv"])

    def test_no_runtime_is_looked_up_on_path(self) -> None:
        fake = self.tmp / "py312"
        fake.mkdir()
        marker = self.tmp / "py312-ran"
        for name in ("python3", "python3.12", "node", "pnpm"):
            (fake / name).write_text(f"#!/bin/sh\ntouch '{marker}'\necho 'Python 3.12.7'\n")
            (fake / name).chmod(0o755)
        env = dict(self.env, PATH=f"{fake}:{self.env['PATH']}")
        res = self.bootstrap("--release-file", str(self.release), "--yes", env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(marker.exists(), "a runtime on the caller's PATH is never run")
        code = [line for line in (self.root / "install" / "bootstrap.sh").read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")]
        self.assertFalse([line for line in code if "/usr/bin/python3" in line or "command -v python" in line])

    def test_pins_missing_stop_with_exit_2(self) -> None:
        pins = json.loads(json.dumps(self.kit.pins))
        pins["python"]["platforms"]["darwin-arm64"]["sha256"] = None
        self.write_release_pins(self.root, pins)
        res = self.bootstrap("--release-file", str(self.release), "--yes")
        self.assertEqual(res.returncode, 2)
        self.assertIn("File cài thiếu thông tin phiên bản của Python", res.stdout)
        self.assertEqual(self.calls("curl"), [])

    def test_wrong_version_in_the_archive_is_removed(self) -> None:
        from tests.fakes_release.kit import python_archive

        wrong = python_archive(reported="3.13.0")
        pins = json.loads(json.dumps(self.kit.pins))
        pins["python"]["platforms"]["darwin-arm64"].update({"sha256": sha256_bytes(wrong), "bytes": len(wrong)})
        self.write_release_pins(self.root, pins)
        (self.fixtures / PY_NAME).write_bytes(wrong)
        res = self.bootstrap("--release-file", str(self.release), "--yes")
        self.assertEqual(res.returncode, 1)
        self.assertIn(t("release.runtime_version", name="Python 3.14.6").splitlines()[0], res.stdout)
        self.assertEqual(list((self.app_home / "cache" / "downloads").glob("*.tar.gz")), [])
        self.assertFalse((self.app_home / "runtime" / "python").exists())


class PythonOnlyTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release("1.4.0")
        self.write_release_pins(self.root)
        self.plant_steps_stub(self.root)
        (self.app_home / "installed.json").write_text('{"schema": 1, "version": "1.4.0"}', encoding="utf-8")
        self.script = self.app_home / "app" / "install" / "bootstrap.sh"

    def test_python_only_reinstalls_python_after_c_and_starts_no_cli(self) -> None:
        res = run_tty(["/bin/bash", str(self.script), "--python-only"], env=dict(self.env), answers="c\n")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("  - Python 3.14.6: tải từ github.com", res.stdout)
        self.assertNotIn("Node.js", res.stdout)
        self.assertEqual(os.readlink(self.app_home / "runtime" / "python"), "python-3.14.6-aarch64-apple-darwin")
        self.assertEqual(self.calls("steps.cmd_install"), [])

    def test_python_only_declined(self) -> None:
        import subprocess

        res = subprocess.run(["/bin/bash", str(self.script), "--python-only"], env=dict(self.env), cwd="/",
                             capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(res.returncode, 4)
        self.assertFalse((self.app_home / "runtime").exists())
        self.assertEqual(self.calls("curl"), [])

    def test_python_only_network_text_names_the_repair_command(self) -> None:
        self.behave(curl={"fail": {PY_URL: 7}})
        res = run_tty(["/bin/bash", str(self.script), "--python-only"], env=dict(self.env), answers="c\n")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Anh kiểm tra mạng rồi chạy lại: bash ~/ThomHouse/app/install/bootstrap.sh --python-only",
                      res.stdout)
