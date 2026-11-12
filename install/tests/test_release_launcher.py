"""The launcher (install/thomhouse.sh.in rendered by release.write_launcher, 16.4.2): only APP_HOME and BOT_HOME in
it, PY_VERSION read at run time, the bash doctor when the private Python is missing or too old, a clean environment
with loopback no_proxy and no ~/.local/bin (rev F4, F10, F15, rev check). Also keeps the helper functions that the
three shell files share identical."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tests.fakes_release.kit import ReleaseTestCase
from thomhouse_installer import release

INSTALL = Path(__file__).resolve().parent.parent
DOCTOR_STUB = '''import json
import os


def cmd_doctor(ctx, args):
    print("ENV " + json.dumps(dict(os.environ)))
    return 0
'''


class LauncherTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release("1.4.0")
        self.write_release_pins(self.root)
        (self.root / "install" / "thomhouse_installer" / "doctor.py").write_text(DOCTOR_STUB, encoding="utf-8")
        self.ctx_ = self.ctx()
        self.launcher = self.app_home / "bin" / "thomhouse"

    def run_launcher(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.launcher), *args], cwd="/", env=env if env is not None else dict(self.env),
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)

    def child_env(self, res: subprocess.CompletedProcess) -> dict:
        line = next(x for x in res.stdout.splitlines() if x.startswith("ENV "))
        return json.loads(line[4:])

    def test_rendered_launcher_holds_only_the_two_folders(self) -> None:
        self.assertTrue(release.write_launcher(self.ctx_, self.root))
        text = self.launcher.read_text(encoding="utf-8")
        self.assertIn(f'APP_HOME="{self.app_home}"', text)
        self.assertIn(f'BOT_HOME="{self.bot_home}"', text)
        self.assertNotIn("@APP_HOME@", text)
        self.assertNotIn("1.4.0", text)
        self.assertNotIn("3.14.6", text)
        self.assertEqual(self.launcher.stat().st_mode & 0o777, 0o700)
        self.assertFalse(release.write_launcher(self.ctx_, self.root))
        self.assertTrue(release.launcher_current(self.ctx_, self.root))
        self.launcher.chmod(0o755)
        self.assertFalse(release.launcher_current(self.ctx_, self.root))
        self.launcher.write_text("#!/bin/bash\n", encoding="utf-8")
        self.assertFalse(release.launcher_current(self.ctx_, self.root))

    def test_launcher_reads_pin_at_run_time(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        self.make_python_runtime("3.14.6")
        res = self.run_launcher("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        # A new release changes PY_VERSION and switches runtime/python; the same launcher still starts the CLI.
        env_file = self.root / "install" / "versions.env"
        env_file.write_text(env_file.read_text(encoding="utf-8").replace("PY_VERSION=3.14.6", "PY_VERSION=3.15.1"))
        self.make_python_runtime("3.15.1", version="3.15.1")
        res = self.run_launcher("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("ENV ", res.stdout)

    def test_missing_python_runs_the_bash_doctor(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        res = self.run_launcher("doctor")
        self.assertEqual(res.returncode, 1)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 5, res.stdout)
        self.assertEqual(lines[0], "[ĐẠT] Hệ điều hành: macOS 15.1")
        self.assertEqual(lines[4], "[LỖI] Python: chưa có Python 3.14.6. Cách sửa: anh chạy lại file "
                                   "thomhouse-1.4.0.command.")
        (self.app_home / "installed.json").write_text('{"schema": 1, "version": "1.4.0"}', encoding="utf-8")
        res = self.run_launcher("doctor")
        self.assertEqual(res.stdout.splitlines()[4], "[LỖI] Python: chưa có Python 3.14.6. Cách sửa: bash "
                                                      "~/ThomHouse/app/install/bootstrap.sh --python-only")

    def test_python_older_than_3_11_runs_the_bash_doctor(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        self.make_python_runtime("3.9.6")
        res = self.run_launcher("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("ENV ", res.stdout)
        self.assertIn("[LỖI] Python: chưa có Python 3.14.6.", res.stdout)

    def test_other_python_3_11_or_newer_still_starts(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        self.make_python_runtime("3.13.1")
        res = self.run_launcher("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("ENV ", res.stdout)

    def test_clean_environment(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        self.make_python_runtime("3.14.6")
        env = dict(self.env, ANTHROPIC_API_KEY="sk-ant-x", ANTHROPIC_AUTH_TOKEN="y", CLAUDE_CODE_OAUTH_TOKEN="z",
                   PROFILE_LLM_ENABLED="true", THOMHOUSE_APP_HOME="/elsewhere", THOMHOUSE_BOT_HOME="/elsewhere2",
                   no_proxy="corp.example", NO_PROXY="ignored.example", SOMETHING_ELSE="1")
        env["PATH"] = f"{self.home}/.local/bin:{env['PATH']}"
        child = self.child_env(self.run_launcher("doctor", env=env))
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "SOMETHING_ELSE"):
            self.assertNotIn(name, child)
        self.assertEqual(child["THOMHOUSE_APP_HOME"], str(self.app_home))
        self.assertEqual(child["THOMHOUSE_BOT_HOME"], str(self.bot_home))
        self.assertEqual(child["PROFILE_LLM_ENABLED"], "false")
        self.assertEqual(child["DISABLE_UPDATES"], "1")
        self.assertEqual(child["ZALO_AGENT_NO_UPDATE_CHECK"], "1")
        self.assertEqual(child["WRANGLER_SEND_METRICS"], "false")
        self.assertEqual(child["LANG"], "en_US.UTF-8")
        self.assertEqual(child["no_proxy"], "corp.example,127.0.0.1,localhost,::1")
        self.assertEqual(child["NO_PROXY"], child["no_proxy"])
        self.assertEqual(child["https_proxy"], self.env["https_proxy"])
        self.assertEqual(child["ZALO_CONFIG_DIR"], self.env["ZALO_CONFIG_DIR"])
        self.assertEqual(child["THOMHOUSE_SERVER_URL"], self.env["THOMHOUSE_SERVER_URL"])
        path = child["PATH"].split(":")
        self.assertEqual(path[:3], [f"{self.app_home}/runtime/node/bin", f"{self.app_home}/runtime/python/bin",
                                    f"{self.app_home}/runtime/bin"])
        self.assertNotIn(f"{self.home}/.local/bin", path)
        self.assertNotIn("/.local/bin", child["PATH"])

    def test_no_proxy_without_a_caller_value(self) -> None:
        release.write_launcher(self.ctx_, self.root)
        self.make_python_runtime("3.14.6")
        child = self.child_env(self.run_launcher("doctor", env=self.env_without_no_proxy()))
        self.assertEqual(child["no_proxy"], "127.0.0.1,localhost,::1")

    def test_folder_with_quotes_is_escaped(self) -> None:
        text = release._render_launcher(self.ctx_, self.root).decode("utf-8")  # noqa: SLF001
        self.assertEqual(release._sh_escape('a"b$c`d\\e'), 'a\\"b\\$c\\`d\\\\e')  # noqa: SLF001
        self.assertIn('APP_HOME="', text)


def _function(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}$", text, re.S | re.M)
    if m is None:
        m = re.search(rf"^{re.escape(name)}\(\) \{{.*?\}}$", text, re.M)
    assert m is not None, name
    return m.group(0)


class SharedShellTest(ReleaseTestCase):
    def test_doctor_block_identical_in_header_and_launcher(self) -> None:
        start, end = "# ---------------------------------------------------------------- bash doctor", \
            "# ---------------------------------------------------------------- end of the bash doctor"
        blocks = []
        for name in ("selfextract.sh.in", "thomhouse.sh.in"):
            text = (INSTALL / name).read_text(encoding="utf-8")
            blocks.append(text[text.index(start):text.index(end)])
        self.assertEqual(blocks[0], blocks[1])

    def test_helpers_identical(self) -> None:
        files = {n: (INSTALL / n).read_text(encoding="utf-8")
                 for n in ("selfextract.sh.in", "bootstrap.sh", "thomhouse.sh.in")}
        for name in ("venv", "first_version", "run_version", "num", "ver_ge", "build_env", "tilde"):
            bodies = {_function(text, name) for text in files.values()}
            self.assertEqual(len(bodies), 1, name)
        for name in ("expand_home", "host_of", "mb", "ask_ck"):
            self.assertEqual(_function(files["selfextract.sh.in"], name), _function(files["bootstrap.sh"], name), name)
        self.assertEqual(_function(files["selfextract.sh.in"], "tool_found"),
                         _function(files["thomhouse.sh.in"], "tool_found"))
