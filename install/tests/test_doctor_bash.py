"""The bash doctor of the launcher (`install/thomhouse.sh.in`, 16.4.2) and of the release header
(`install/selfextract.sh.in --doctor`, 16.4.6) prints lines 1 to 5 of 16.7 exactly as the Python doctor does.

Both shell files, `release.write_launcher` and `runtimes.found` belong to WP2; the tests run against the real WP2
files. The expected lines come from
`doctor.run_checks` with the stock macOS tools on PATH (the bash doctor runs with /usr/bin:/bin:/usr/sbin:/sbin and
the real sw_vers, sysctl and df, which only read). Only the free-space number of line 3 may change between the two
runs, so it is compared as "N GB".

The header test builds a minimal `.command` the way 16.2.2 step 10 describes it: the template with its header
variables filled in, the `__PAYLOAD__` line, then a tar.gz holding `thomhouse-<ver>/install/versions.env`. That
relies on the template's `@NAME@` placeholders; a different syntax in WP2 makes this test fail.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import os
import re
import subprocess
import tarfile
import unittest
from datetime import datetime
from unittest import mock

from tests.support import INSTALL_DIR, InstallerTestCase
from thomhouse_installer import doctor, platforms, state

STOCK_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
FIRST_FIVE = {"macos", "cpu", "disk", "system_tools", "python"}
GB = re.compile(r"\b\d+ GB\b")
VERSIONS_ENV = "MACOS_MIN=13.5\nDISK_MIN_GB=3\nPY_VERSION=3.14.6\n"


def _normalize(lines: list[str]) -> list[str]:
    return [GB.sub("N GB", x) for x in lines]


def _payload(version: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = VERSIONS_ENV.encode("utf-8")
        info = tarfile.TarInfo(f"thomhouse-{version}/install/versions.env")
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class BashDoctorTest(InstallerTestCase):
    def expected(self) -> list[str]:
        """Lines 1 to 5 of the Python doctor for this test's installation, with the stock tools on PATH."""
        with mock.patch.dict(os.environ, {"PATH": STOCK_PATH}):
            ctx = self.ctx()
            ctx.platform = platforms.detect()
            results = doctor.run_checks(ctx, only=FIRST_FIVE)
        return [doctor.line(r) for r in results]

    def bash_env(self) -> dict[str, str]:
        env = dict(self.env)
        env["PATH"] = STOCK_PATH
        env["THOMHOUSE_TOOL_PATH"] = STOCK_PATH  # the stock tools, like the Python doctor of expected()
        return env

    def snapshot(self) -> list[str]:
        return sorted(str(p) for p in self.home.rglob("*"))

    def test_launcher_bash_doctor(self) -> None:
        template = INSTALL_DIR / "thomhouse.sh.in"
        release = importlib.import_module("thomhouse_installer.release")
        self.assertTrue(template.exists())
        root = self.install_release("1.4.0")
        (root / "install" / "versions.env").write_text(VERSIONS_ENV, encoding="utf-8")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        state.save_installed(self.paths(), {"schema": 1, "version": "1.4.0", "installed_at": now})
        release.write_launcher(self.ctx(), self.app_home / "app")
        launcher = self.app_home / "bin" / "thomhouse"
        self.assertTrue(launcher.exists())
        self.assertFalse((self.app_home / "runtime" / "python" / "bin" / "python3").exists())
        res = subprocess.run(["/bin/bash", str(launcher), "doctor"], env=self.bash_env(), cwd="/",
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        lines = [x for x in res.stdout.splitlines() if x.startswith("[")]
        expected = self.expected()
        self.assertEqual(_normalize(lines[:5]), _normalize(expected))
        self.assertTrue(expected[4].endswith("bash ~/ThomHouse/app/install/bootstrap.sh --python-only"), expected[4])

    def test_header_bash_doctor(self) -> None:
        template = INSTALL_DIR / "selfextract.sh.in"
        self.assertTrue(template.exists())
        self.install_release("1.4.0")  # no installed.json: a Mac before its first install
        payload = _payload("1.4.0")
        header = template.read_text(encoding="utf-8")
        for name, value in {"RELEASE_VERSION": "1.4.0", "PAYLOAD_SHA256": hashlib.sha256(payload).hexdigest(),
                            "PAYLOAD_BYTES": str(len(payload)), "PAYLOAD_SIG_B64": "", "MENU_ID": "0" * 16,
                            "BUILT_AT": "2026-11-12T00:00:00Z"}.items():
            header = header.replace(f"@{name}@", value)
        self.assertNotIn("@RELEASE_VERSION@", header)
        command = self.tmp / "thomhouse-1.4.0.command"
        command.write_bytes(header.encode("utf-8").rstrip(b"\n") + b"\n__PAYLOAD__\n" + payload)
        before = self.snapshot()
        res = subprocess.run(["/bin/bash", str(command), "--doctor"], env=self.bash_env(), cwd="/",
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        lines = [x for x in res.stdout.splitlines() if x.startswith("[")]
        expected = self.expected()
        self.assertEqual(_normalize(lines[:5]), _normalize(expected))
        self.assertTrue(expected[4].endswith("anh chạy lại file thomhouse-1.4.0.command."), expected[4])
        self.assertEqual(self.snapshot(), before)  # --doctor writes nothing


if __name__ == "__main__":
    unittest.main()
