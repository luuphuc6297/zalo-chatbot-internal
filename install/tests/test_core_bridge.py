"""bridgecli.py against the stub bridge, and envs.py (16.3.3, rev iface)."""

from __future__ import annotations

import contextlib
import io
import os
import stat

from tests.support import InstallerTestCase
from thomhouse_installer import bridgecli, envs, proc


class BridgeCliTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release()
        self.ctx_ = self.ctx()
        engine = self.app_home / "app" / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent"
        self.assertEqual(bridgecli.init_env(self.ctx_, self.app_home / "app", engine), 0)

    def test_init_env_writes_three_files_0600(self) -> None:
        call = self.calls("bridge")[0]
        self.assertEqual(call["argv"][:5], ["init-env", "--mode", "personal", "--engine-bin",
                                            str(self.app_home / "app" / "tools" / "zalo-agent" / "node_modules"
                                                / ".bin" / "zalo-agent")])
        self.assertEqual(call["argv"][5:], ["--repo-root", str(self.app_home / "app")])
        self.assertEqual(call["cwd"], os.path.realpath(self.app_home / "app" / "apps" / "zalo-bridge"))
        for name in ("server", "runner", "bridge"):
            f = self.ctx_.paths.env_file(name)
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, name)
        self.assertEqual(envs.value(self.ctx_.paths, "runner", "RUNNER_ID"), "mac-local-1")
        token = envs.value(self.ctx_.paths, "server", "RUNNER_TOKEN")
        self.assertEqual(envs.value(self.ctx_.paths, "bridge", "RUNNER_TOKEN"), token)
        self.assertIn(token, proc.secret_values(self.ctx_.paths))

    def test_doctor_reads_statuses_only(self) -> None:
        self.behave(bridge={"doctor": {"listener": "fail"}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = bridgecli.doctor(self.ctx_)
        self.assertEqual(result["listener"], "fail")
        self.assertEqual(result["zalo_login"], "ok")
        self.assertEqual(result["room_platform"], "warn")
        self.assertEqual(out.getvalue(), "")
        log = (self.app_home / "logs" / "install.log").read_text(encoding="utf-8")
        self.assertNotIn("999000111", log)
        self.assertNotIn("999000111", repr(result))

    def test_doctor_none_offline_or_without_env(self) -> None:
        self.ctx_.offline = True
        self.assertIsNone(bridgecli.doctor(self.ctx_))
        self.ctx_.offline = False
        self.ctx_.paths.env_file("bridge").unlink()
        before = len(self.calls("bridge"))
        self.assertIsNone(bridgecli.doctor(self.ctx_))
        self.assertEqual(len(self.calls("bridge")), before)

    def test_listener(self) -> None:
        code, data = bridgecli.listener(self.ctx_, "status")
        self.assertEqual((code, data["running"]), (0, True))
        self.behave(bridge={"listener": {"start": [4, {"running": True, "foreign": True}]}})
        code, data = bridgecli.listener(self.ctx_, "start")
        self.assertEqual((code, data["foreign"]), (4, True))
        bridgecli.listener(self.ctx_, "stop", only_ours=True)
        self.assertEqual(self.calls("bridge")[-1]["argv"], ["listener", "stop", "--only-ours"])
        bridgecli.listener(self.ctx_, "stop")
        self.assertEqual(self.calls("bridge")[-1]["argv"], ["listener", "stop"])
        bridgecli.listener(self.ctx_, "start", only_ours=True)
        self.assertEqual(self.calls("bridge")[-1]["argv"], ["listener", "start"])
        with self.assertRaises(ValueError):
            bridgecli.listener(self.ctx_, "restart")

    def test_sync_labels(self) -> None:
        code, data = bridgecli.sync_labels(self.ctx_, dry_run=True)
        self.assertEqual((code, data["contacts"]["customer"]), (0, 2))
        self.assertEqual(self.calls("bridge")[-1]["argv"], ["sync-labels", "--dry-run"])
        self.behave(bridge={"sync_labels": [1, None]})
        code, data = bridgecli.sync_labels(self.ctx_, dry_run=False)
        self.assertEqual((code, data), (1, None))


class EnvsTest(InstallerTestCase):
    def test_read(self) -> None:
        f = self.tmp / "x.env"
        f.write_text("# comment\n\nA=1\nexport B = two \nC=\"quoted value\"\nD='single'\n# E=commented\n"
                     "A=last\nbroken line\n", encoding="utf-8")
        self.assertEqual(envs.read(f), {"A": "last", "B": "two", "C": "quoted value", "D": "single"})
        self.assertEqual(envs.read(self.tmp / "missing"), {})

    def test_value(self) -> None:
        root = self.make_checkout()
        p = self.paths(root)
        (root / "apps" / "server").mkdir(parents=True, exist_ok=True)
        (root / "apps" / "server" / ".dev.vars").write_text("STAFF_TOKEN=abc\nEMPTY=\n", encoding="utf-8")
        self.assertEqual(envs.value(p, "server", "STAFF_TOKEN"), "abc")
        self.assertIsNone(envs.value(p, "server", "EMPTY"))
        self.assertIsNone(envs.value(p, "runner", "RUNNER_ID"))
