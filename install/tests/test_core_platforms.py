"""platforms.py: OS, macOS version and CPU from the fake uname, sw_vers and sysctl; free disk (16.5)."""

from __future__ import annotations

from unittest import mock

from tests.support import InstallerTestCase
from thomhouse_installer import platforms


class PlatformsTest(InstallerTestCase):
    def detect(self, **system: object) -> platforms.Platform:
        self.behave(system=system)
        return platforms.detect()

    def test_apple_silicon(self) -> None:
        p = self.detect(os="Darwin", macos="15.1", cpu="arm64")
        self.assertEqual((p.os, p.uname, p.macos, p.cpu, p.key), ("darwin", "Darwin", (15, 1), "arm64", "darwin-arm64"))

    def test_intel_and_old_macos(self) -> None:
        p = self.detect(os="Darwin", macos="13.4", cpu="x64")
        self.assertEqual((p.os, p.macos, p.cpu, p.key), ("darwin", (13, 4), "x64", "darwin-x64"))

    def test_linux_wsl_windows_other(self) -> None:
        proc_version = self.tmp / "proc-version"
        proc_version.write_text("Linux version 6.1 (gcc)", encoding="utf-8")
        with mock.patch.object(platforms, "PROC_VERSION", proc_version):
            p = self.detect(os="Linux", cpu="x64")
            self.assertEqual((p.os, p.cpu, p.key, p.macos), ("linux", "x64", None, None))
            proc_version.write_text("Linux version 5.15.0-microsoft-standard-WSL2", encoding="utf-8")
            self.assertEqual(self.detect(os="Linux").os, "wsl")
        self.assertEqual(self.detect(os="MINGW64_NT-10.0-22631").os, "windows")
        self.assertEqual(self.detect(os="CYGWIN_NT-10.0").os, "windows")
        self.assertEqual(self.detect(os="FreeBSD").os, "other")

    def test_missing_tools(self) -> None:
        def run(*args, **kwargs):
            raise FileNotFoundError("no such tool")

        p = platforms.detect(run=run)
        self.assertEqual((p.os, p.key), ("other", None))

    def test_free_gb(self) -> None:
        self.assertGreater(platforms.free_gb(self.tmp), 0)
        self.assertGreater(platforms.free_gb(self.tmp / "does" / "not" / "exist"), 0)
