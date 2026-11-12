"""The shared fakes of install/tests/fake_bin behave as 16.10 documents, so every package can rely on them."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.support import FAKE_BIN, InstallerTestCase


class FakesTest(InstallerTestCase):
    def run_tool(self, *args: str, cwd: Path | None = None, input: str | None = None,
                 env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(list(args), cwd=str(cwd or self.tmp), input=input, capture_output=True, text=True,
                              env=env if env is not None else dict(os.environ), timeout=60)

    def test_refuses_without_test_folder(self) -> None:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp / "a" / "b" / "home")}
        res = self.run_tool(str(FAKE_BIN / "curl"), "https://x.invalid/a", env=env)
        self.assertEqual(res.returncode, 99)

    def test_records_names_not_values(self) -> None:
        os.environ["STAFF_TOKEN"] = "do-not-record-this-value"
        self.run_tool("sw_vers", "-productVersion")
        call = self.calls("sw_vers")[0]
        self.assertIn("STAFF_TOKEN", call["env_names"])
        self.assertNotIn("do-not-record-this-value", json.dumps(call))
        self.assertEqual(call["env"]["no_proxy"], "127.0.0.1,localhost")

    def test_system_tools(self) -> None:
        self.assertEqual(self.run_tool("sw_vers", "-productVersion").stdout.strip(), "15.1")
        self.assertEqual(self.run_tool("sysctl", "-n", "hw.optional.arm64").stdout.strip(), "1")
        self.assertEqual(self.run_tool("uname", "-s").stdout.strip(), "Darwin")
        self.behave(system={"os": "MINGW64_NT-10.0", "cpu": "x64", "uid": 0, "macos": "13.4"})
        self.assertEqual(self.run_tool("uname", "-s").stdout.strip(), "MINGW64_NT-10.0")
        self.assertEqual(self.run_tool("uname", "-m").stdout.strip(), "x86_64")
        self.assertEqual(self.run_tool("sysctl", "-n", "hw.optional.arm64").returncode, 1)
        self.assertEqual(self.run_tool("id", "-u").stdout.strip(), "0")
        self.assertEqual(self.run_tool("id", "-un").stdout.strip(), "tester")

    def test_node_npm_pnpm(self) -> None:
        self.assertEqual(self.run_tool("node", "--version").stdout.strip(), "v24.19.0")
        engine = self.tmp / "engine"
        engine.mkdir()
        (engine / "package-lock.json").write_text(json.dumps({"packages": {
            "": {"dependencies": {"@ardennguyen/zalo-agent-cli": "2.5.9"}},
            "node_modules/@ardennguyen/zalo-agent-cli": {"version": "2.5.9"}}}), encoding="utf-8")
        res = self.run_tool("npm", "ci", "--prefix", str(engine), "--no-fund", "--no-audit")
        self.assertEqual(res.returncode, 0, res.stderr)
        pkg = json.loads((engine / "node_modules" / "@ardennguyen" / "zalo-agent-cli" / "package.json").read_text())
        self.assertEqual(pkg["version"], "2.5.9")
        shim = engine / "node_modules" / ".bin" / "zalo-agent"
        self.assertTrue(os.access(shim, os.X_OK))
        self.assertEqual(self.run_tool(str(shim), "--version").stdout.strip(), "2.5.9")
        npm_call = self.calls("npm")[0]
        self.assertEqual(npm_call["prefix"], str(engine))
        self.behave(npm={"fail": ["engine"]})
        self.assertEqual(self.run_tool("npm", "ci", "--prefix", str(engine)).returncode, 1)
        lockdir = self.tmp / "lockdir"
        lockdir.mkdir()
        (lockdir / "package.json").write_text(json.dumps({"dependencies": {"pnpm": "10.32.1"}}), encoding="utf-8")
        self.behave(npm={"fail": []})
        self.assertEqual(self.run_tool("npm", "install", "--package-lock-only", cwd=lockdir).returncode, 0)
        lock = json.loads((lockdir / "package-lock.json").read_text())
        self.assertEqual(lock["packages"][""]["dependencies"]["pnpm"], "10.32.1")
        self.assertTrue(lock["packages"]["node_modules/pnpm"]["resolved"].startswith("https://registry.npmjs.org/"))
        release = self.tmp / "release"
        release.mkdir()
        (release / ".npmrc").write_text(f"store-dir={self.tmp}/store\n", encoding="utf-8")
        self.assertEqual(self.run_tool("pnpm", "--version").stdout.strip(), "10.32.1")
        self.assertEqual(self.run_tool("pnpm", "install", "--frozen-lockfile", cwd=release).returncode, 0)
        self.assertEqual(self.calls("pnpm")[-1]["store_dir"], f"{self.tmp}/store")
        self.assertTrue(os.access(release / "apps" / "server" / "node_modules" / ".bin" / "wrangler", os.X_OK))
        self.assertTrue(os.access(release / "apps" / "console" / "node_modules" / ".bin" / "vite", os.X_OK))
        self.behave(pnpm={"fail": True})
        self.assertEqual(self.run_tool("pnpm", "install", "--frozen-lockfile", cwd=release).returncode, 1)

    def test_curl_resume_and_stdout(self) -> None:
        (self.fixtures / "f.bin").write_bytes(b"0123456789")
        part = self.tmp / "out.part"
        part.write_bytes(b"0123")
        res = self.run_tool("curl", "-fL", "-C", "-", "-o", str(part), "https://example.invalid/x/f.bin")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(part.read_bytes(), b"0123456789")
        res = self.run_tool("curl", "-fsSL", "https://claude.ai/install.sh")
        self.assertIn("install", res.stdout)
        self.assertEqual(self.run_tool("curl", "-o", str(part), "http://example.invalid/f.bin").returncode, 22)
        self.assertEqual(self.run_tool("curl", "-o", str(part), "https://example.invalid/missing").returncode, 22)

    def test_claude(self) -> None:
        res = self.run_tool("claude", "--version")
        self.assertEqual(res.stdout.strip(), "2.1.319 (Claude Code)")
        res = self.run_tool("claude", "auth", "status")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(json.loads(res.stdout), {"loggedIn": False, "authMethod": "none", "apiProvider": "firstParty"})
        self.run_tool("claude", "auth", "login")
        doc = json.loads(self.run_tool("claude", "auth", "status").stdout)
        self.assertEqual((doc["authMethod"], doc["subscriptionType"], doc["email"]),
                         ("claude.ai", "max", "x@example.invalid"))
        self.run_tool("claude", "auth", "logout")
        self.assertEqual(self.run_tool("claude", "auth", "status").returncode, 1)
        self.assertEqual(self.run_tool("claude", "-p", "hi").returncode, 2)

    def test_claude_installer_respects_disable_updates(self) -> None:
        env = dict(os.environ)
        env["DISABLE_UPDATES"] = "1"
        script = self.fixtures / "install.sh"
        res = self.run_tool("/bin/bash", str(script), "2.1.320", env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Updates are disabled", res.stdout)
        self.assertFalse((self.home / ".local" / "bin" / "claude").exists())
        env.pop("DISABLE_UPDATES")
        self.behave(claude={"binary_marker": "variant-b"})
        res = self.run_tool("/bin/bash", str(script), "2.1.320", env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        link = self.home / ".local" / "bin" / "claude"
        target = self.home / ".local" / "share" / "claude" / "versions" / "2.1.320"
        self.assertEqual(Path(os.readlink(link)), target)
        self.assertIn("variant-b", target.read_text())
        self.assertEqual(self.run_tool(str(link), "--version").stdout.strip(), "2.1.320 (Claude Code)")

    def test_zalo_agent(self) -> None:
        res = self.run_tool("zalo-agent", "--json", "login")
        events = [json.loads(x)["event"] for x in res.stdout.splitlines()]
        self.assertEqual(events, ["qr", "qr_scanned", "login_success"])
        self.assertIn('"ownId": "999000111"', res.stdout)
        self.behave(zalo_agent={"login": "declined", "sync_exit": 3})
        res = self.run_tool("zalo-agent", "--json", "login")
        self.assertEqual([json.loads(x)["event"] for x in res.stdout.splitlines()], ["qr", "qr_declined"])
        self.assertEqual(self.run_tool("zalo-agent", "--json", "sync", "--days", "365").returncode, 3)
        self.assertEqual(self.run_tool("zalo-agent", "listen", "--stop").returncode, 0)

    def test_lsof(self) -> None:
        self.behave(lsof={"listen": [["node", 101, "127.0.0.1", 8799], ["node", 101, "*", 8800],
                                     ["workerd", 202, "::1", 8787]], "cwd": {"101": "/some/folder"}})
        res = self.run_tool("lsof", "-nP", "-a", "-p", "101", "-iTCP", "-sTCP:LISTEN")
        self.assertIn("127.0.0.1:8799 (LISTEN)", res.stdout)
        self.assertIn("*:8800 (LISTEN)", res.stdout)
        self.assertNotIn("8787", res.stdout)
        res = self.run_tool("lsof", "-nP", "-iTCP:8787", "-sTCP:LISTEN", "-t")
        self.assertEqual(res.stdout.strip(), "202")
        self.assertEqual(self.run_tool("lsof", "-nP", "-iTCP:5173", "-sTCP:LISTEN", "-t").returncode, 1)
        res = self.run_tool("lsof", "-a", "-d", "cwd", "-p", "101", "-Fn")
        self.assertEqual(res.stdout.splitlines(), ["p101", "fcwd", "n/some/folder"])

    def test_clipboard_open_launchctl_hdiutil_sips(self) -> None:
        self.run_tool("pbcopy", input="token-value")
        self.assertEqual(self.run_tool("pbpaste").stdout, "token-value")
        self.assertNotIn("token-value", json.dumps(self.calls("pbcopy")))
        self.assertEqual(self.run_tool("open", "http://127.0.0.1:5173").returncode, 0)
        self.assertEqual(self.calls("open")[0]["argv"], ["http://127.0.0.1:5173"])
        self.assertEqual(self.run_tool("launchctl", "bootstrap", "gui/501", "x.plist").returncode, 0)
        src = self.tmp / "staging"
        (src / "d1").mkdir(parents=True)
        (src / "d1" / "x").write_text("data", encoding="utf-8")
        image = self.tmp / "out" / "thomhouse-chuyen-may-x.dmg"
        image.parent.mkdir()
        res = self.run_tool("hdiutil", "create", "-encryption", "AES-256", "-srcfolder", str(src), "-volname",
                            "thomhouse-chuyen-may", "-format", "UDZO", str(image))
        self.assertEqual(res.returncode, 0, res.stderr)
        mount = self.tmp / "mnt"
        self.assertEqual(self.run_tool("hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount),
                                       str(image)).returncode, 0)
        self.assertEqual((mount / "d1" / "x").read_text(), "data")
        self.assertEqual(self.run_tool("hdiutil", "detach", str(mount)).returncode, 0)
        self.assertFalse(mount.exists())
        jpg = self.tmp / "a.jpg"
        png = self.tmp / "a.png"
        png.write_bytes(b"png")
        self.assertEqual(self.run_tool("sips", "-s", "format", "jpeg", str(png), "--out", str(jpg)).returncode, 0)
        self.assertEqual(jpg.read_bytes(), b"png")
