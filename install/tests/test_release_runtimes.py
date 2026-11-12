"""runtimes.py (step 5 of 16.4.3, 16.5): detection at the launcher's locations, the plan, Node.js, pnpm, Python and
Claude Code from fixtures, the links, and the Claude Code installer environment and binary check (rev F1, F11, F15,
F22, rev check)."""

from __future__ import annotations

import dataclasses
import importlib
import io
import os
from contextlib import redirect_stdout

from tests.fakes_release import kit
from tests.fakes_release.kit import NODE_NAME, ReleaseTestCase
from thomhouse_installer import pins as pins_mod
from thomhouse_installer import proc, runtimes
from thomhouse_installer.download import DownloadError
from thomhouse_installer.runtimes import RuntimeInstallError


class RuntimesTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release("1.4.0")
        self.write_release_pins(self.root)
        self.ctx_ = self.ctx()
        self.ctx_.quiet = True
        self.local = self.home / ".local"

    def item(self, name: str) -> runtimes.RuntimeItem:
        return next(i for i in runtimes.plan(self.ctx_) if i.name == name)

    def test_plan_before_anything_is_installed(self) -> None:
        plan = {i.name: i for i in runtimes.plan(self.ctx_)}
        self.assertEqual(list(plan), ["python", "node", "pnpm", "claude_code"])
        self.assertTrue(all(i.action == "install" and i.found is None for i in plan.values()))
        self.assertEqual(plan["python"].source, "github.com")
        self.assertEqual(plan["node"].source, "nodejs.org")
        self.assertEqual(plan["pnpm"].source, "registry.npmjs.org")
        self.assertEqual(plan["claude_code"].source, "claude.ai")
        self.assertEqual(plan["claude_code"].size_mb, 310)
        self.assertEqual(plan["node"].target, self.app_home / "runtime" / "node-v24.19.0-darwin-arm64")
        self.assertEqual(plan["python"].target, self.app_home / "runtime" / "python-3.14.6-aarch64-apple-darwin")
        self.assertEqual(plan["pnpm"].target, self.app_home / "runtime" / "pnpm-10.32.1")
        self.assertEqual(plan["node"].sha256, self.kit.pins["node"]["platforms"]["darwin-arm64"]["sha256"])

    def test_node_pnpm_python_from_fixtures(self) -> None:
        runtimes.install(self.ctx_, self.item("node"))
        self.assertEqual(self.calls("curl")[-1]["argv"][-1], kit.NODE_URL)
        self.assertIsNone(runtimes.found(self.ctx_, "node"), "install never switches the link")
        runtimes.switch(self.ctx_, "node", "24.19.0")
        self.assertEqual(os.readlink(self.app_home / "runtime" / "node"), "node-v24.19.0-darwin-arm64")
        self.assertEqual(runtimes.found(self.ctx_, "node"), "24.19.0")

        runtimes.install(self.ctx_, self.item("pnpm"))
        npm = [c for c in self.calls("npm") if c["argv"][:1] == ["ci"]][-1]
        target = self.app_home / "runtime" / "pnpm-10.32.1"
        self.assertEqual(npm["argv"], ["ci", "--prefix", str(target), "--no-fund", "--no-audit"])
        self.assertEqual(npm["path0"], str(self.app_home / "runtime" / "node" / "bin"))
        self.assertEqual(npm["cache"], str(self.app_home / "cache" / "npm"))
        runtimes.switch(self.ctx_, "pnpm", "10.32.1")
        self.assertEqual(os.readlink(self.app_home / "runtime" / "bin" / "pnpm"),
                         "../pnpm-10.32.1/node_modules/.bin/pnpm")
        self.assertEqual(runtimes.found(self.ctx_, "pnpm"), "10.32.1")

        runtimes.install(self.ctx_, self.item("python"))
        runtimes.switch(self.ctx_, "python", "3.14.6")
        self.assertEqual(runtimes.found(self.ctx_, "python"), "3.14.6")
        self.assertEqual(list((self.app_home / "runtime").glob(".tmp-*")), [])
        before = len(self.calls("curl"))
        runtimes.install(self.ctx_, self.item("python"))  # already there: nothing downloaded
        self.assertEqual(len(self.calls("curl")), before)
        self.assertEqual({i.name: i.action for i in runtimes.plan(self.ctx_)},
                         {"python": "keep", "node": "keep", "pnpm": "keep", "claude_code": "install"})

    def test_interrupted_unpack_leaves_no_switched_link(self) -> None:
        runtimes.install(self.ctx_, self.item("node"))
        runtimes.switch(self.ctx_, "node", "24.19.0")
        broken = kit.tar_gz({})[:-8] + b"broken!!"  # gzip that tar cannot read
        (self.fixtures / "node-v24.20.0-darwin-arm64.tar.gz").write_bytes(broken)
        pins = self.ctx_.pins
        self.ctx_.pins = dataclasses.replace(pins, node=pins_mod.RuntimePin(
            "24.20.0", "https://nodejs.org/dist/v24.20.0/node-v24.20.0-darwin-arm64.tar.gz",
            kit.sha256_bytes(broken), len(broken)))
        with self.assertRaises(RuntimeInstallError) as cm:
            runtimes.install(self.ctx_, self.item("node"))
        self.assertEqual((cm.exception.kind, cm.exception.key), ("unpack", "release.runtime_unpack"))
        self.assertEqual(cm.exception.fmt["name"], "Node.js 24.20.0")
        rt = self.app_home / "runtime"
        self.assertEqual(os.readlink(rt / "node"), "node-v24.19.0-darwin-arm64")
        self.assertFalse((rt / "node-v24.20.0-darwin-arm64").exists())
        self.assertEqual(list(rt.glob(".tmp-*")), [])

    def test_failed_download_raises_download_error(self) -> None:
        self.behave(curl={"fail": {kit.NODE_URL: 7}})
        with self.assertRaises(DownloadError) as cm:
            runtimes.install(self.ctx_, self.item("node"))
        self.assertEqual(cm.exception.kind, "network")
        self.assertFalse((self.app_home / "runtime" / NODE_NAME[:-7]).exists())

    def test_pnpm_failure_removes_the_half_made_folder(self) -> None:
        runtimes.install(self.ctx_, self.item("node"))
        runtimes.switch(self.ctx_, "node", "24.19.0")
        self.behave(npm={"fail": ["pnpm-10.32.1"]})
        with self.assertRaises(RuntimeInstallError) as cm:
            runtimes.install(self.ctx_, self.item("pnpm"))
        self.assertEqual(cm.exception.kind, "unpack")
        self.assertFalse((self.app_home / "runtime" / "pnpm-10.32.1").exists())

    def test_claude_code_from_the_fixture_installer(self) -> None:
        runtimes.install(self.ctx_, self.item("claude_code"))
        link = self.local / "bin" / "claude"
        binary = self.local / "share" / "claude" / "versions" / "2.1.319"
        self.assertTrue(link.is_symlink())
        self.assertEqual(kit.sha256_bytes(binary.read_bytes()),
                         self.kit.pins["claude_code"]["platforms"]["darwin-arm64"]["sha256"])
        self.assertTrue((self.app_home / "cache" / "downloads" / "claude-install.sh").is_file())
        runtimes.switch(self.ctx_, "claude_code", "2.1.319")
        self.assertEqual(os.readlink(self.app_home / "runtime" / "bin" / "claude"), str(link))
        self.assertEqual(runtimes.found(self.ctx_, "claude_code"), "2.1.319")

    def test_claude_installer_env_lacks_disable_updates(self) -> None:
        runtimes.install(self.ctx_, self.item("claude_code"))
        install = [c for c in self.calls("claude") if c["argv"][:1] == ["install"]]
        self.assertEqual(len(install), 1)
        self.assertIsNone(install[0]["env"]["DISABLE_UPDATES"])
        self.assertIsNone(install[0]["env"]["DISABLE_AUTOUPDATER"])
        version_checks = [c for c in self.calls("claude") if c["argv"] == ["--version"]]
        self.assertTrue(version_checks and all(c["env"]["DISABLE_UPDATES"] == "1" for c in version_checks))
        self.assertEqual(proc.child_env(self.ctx_.paths)["DISABLE_UPDATES"], "1")

    def test_with_disable_updates_forced_the_install_fails(self) -> None:
        real = proc.child_env

        def forced(paths, extra=None, *, claude_install=False):
            env = real(paths, extra, claude_install=claude_install)
            env["DISABLE_UPDATES"] = "1"
            return env

        proc.child_env = forced
        self.addCleanup(setattr, proc, "child_env", real)
        with self.assertRaises(RuntimeInstallError) as cm:
            runtimes.install(self.ctx_, self.item("claude_code"))
        self.assertEqual(cm.exception.key, "release.runtime_installer")
        self.assertFalse((self.local / "bin" / "claude").exists())

    def test_claude_binary_hash_mismatch(self) -> None:
        self.behave(claude={"binary_marker": "not the tested build"})
        with self.assertRaises(RuntimeInstallError) as cm:
            runtimes.install(self.ctx_, self.item("claude_code"))
        self.assertEqual((cm.exception.kind, cm.exception.code), ("checksum", 1))
        self.assertFalse((self.local / "share" / "claude" / "versions" / "2.1.319").exists())
        self.assertFalse((self.local / "bin" / "claude").exists() or (self.local / "bin" / "claude").is_symlink())

    def test_claude_mismatch_restores_the_previous_link(self) -> None:
        old = self.local / "share" / "claude" / "versions" / "2.1.200"
        old.parent.mkdir(parents=True)
        old.write_bytes(kit.claude_binary("2.1.200"))
        old.chmod(0o755)
        link = self.local / "bin" / "claude"
        link.parent.mkdir(parents=True)
        link.symlink_to(old)
        self.behave(claude={"binary_marker": "not the tested build"})
        with self.assertRaises(RuntimeInstallError):
            runtimes.install(self.ctx_, self.item("claude_code"))
        self.assertEqual(os.readlink(link), str(old))
        self.assertTrue(old.is_file())
        self.assertFalse((old.parent / "2.1.319").exists())

    def test_claude_existing_new_enough_is_reused(self) -> None:
        for version, action in (("2.1.400", "keep"), ("2.1.319", "keep"), ("2.1.100", "install")):
            with self.subTest(version=version):
                binary = self.local / "share" / "claude" / "versions" / version
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(kit.claude_binary(version))
                binary.chmod(0o755)
                link = self.local / "bin" / "claude"
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.is_symlink():
                    link.unlink()
                link.symlink_to(binary)
                item = self.item("claude_code")
                self.assertEqual((item.found, item.action), (version, action))
        runtimes.switch(self.ctx_, "claude_code", "2.1.319")
        self.assertEqual(os.readlink(self.app_home / "runtime" / "bin" / "claude"), str(self.local / "bin" / "claude"))
        self.assertEqual(self.calls("curl"), [])

    def test_installing_line_is_printed(self) -> None:
        self.ctx_.quiet = False
        out = io.StringIO()
        with redirect_stdout(out):
            runtimes.install(self.ctx_, self.item("node"))
        self.assertIn("Đang cài Node.js 24.19.0", out.getvalue())

    def test_switch_needs_the_target(self) -> None:
        for name, version in (("python", "3.14.6"), ("node", "24.19.0"), ("pnpm", "10.32.1"),
                              ("claude_code", "2.1.319")):
            with self.assertRaises(FileNotFoundError):
                runtimes.switch(self.ctx_, name, version)


class ConsentedTest(ReleaseTestCase):
    """Step 5 asks again for an item that is missing from --consented (rev F11), with WP3's real steps.py."""

    def test_item_missing_from_consented_is_asked_not_failed(self) -> None:
        steps = importlib.import_module("thomhouse_installer.steps")
        step = next(s for s in steps.STEPS if s.id == "runtimes")
        root = self.install_release("1.4.0")
        self.write_release_pins(root)
        ctx = self.ctx(command="install", consented=["python"], from_bootstrap=True, skip_human=False, only=None,
                       menu=None, move_in=None, release_file=None, trust_channel=False)
        out = io.StringIO()
        with redirect_stdout(out):
            result = step.run(ctx)
        self.assertIn("Node.js 24.19.0", out.getvalue())
        self.assertNotEqual(result.status, "failed")
        self.assertEqual(result.exit, 4)
        self.assertEqual(self.calls("curl"), [])
