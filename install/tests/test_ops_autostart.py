"""autostart.py: the LaunchAgent and the three Desktop files hold this installation's APP_HOME, also a non-default
one (rev F15); launchctl bootstrap and bootout; files the person changed or did not get from the installer are left
alone; `start --quiet` from the LaunchAgent exits 3 during an unfinished update (rev F14)."""

from __future__ import annotations

import argparse
import os
import plistlib
import stat
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase
from thomhouse_installer import autostart, context, paths as paths_mod, state
from thomhouse_installer.text_vi import t


def _ns(**attrs: object) -> argparse.Namespace:
    ns = {"command": "autostart", "yes": False, "dry_run": False, "quiet": False, "offline": False, "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


class AutostartTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release()
        (self.home / "Desktop").mkdir()
        self.plist = self.home / "Library" / "LaunchAgents" / "vn.thomhouse.bot.plist"

    def ctx_for(self, app_home: Path):
        """A context whose APP_HOME is `app_home` (code from the installed release)."""
        env = dict(os.environ, THOMHOUSE_APP_HOME=str(app_home))
        with mock.patch.dict(os.environ, env):
            p = paths_mod.resolve(env, code_root=self.root)
        ctx = context.make_ctx(_ns(), env=env, paths=p)
        ctx.interactive = False
        return ctx

    def check_files(self, app_home: Path) -> None:
        data = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(data["Label"], "vn.thomhouse.bot")
        self.assertEqual(data["ProgramArguments"], ["/bin/bash", f"{app_home}/bin/thomhouse", "start", "--quiet"])
        self.assertTrue(data["RunAtLoad"])
        self.assertTrue(data["AbandonProcessGroup"])
        self.assertEqual(data["StandardOutPath"], f"{app_home}/logs/autostart.log")
        self.assertEqual(data["StandardErrorPath"], f"{app_home}/logs/autostart.log")
        self.assertEqual(stat.S_IMODE(self.plist.stat().st_mode), 0o644)
        for name, command in (("Bat-chatbot.command", "start"), ("Kiem-tra-chatbot.command", "doctor"),
                              ("Tat-chatbot.command", "stop")):
            f = self.home / "Desktop" / name
            lines = f.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["#!/bin/bash", "# thomhouse-shortcut v1", f'exec "{app_home}/bin/thomhouse" {command}'])
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o755)

    def test_default_and_custom_app_home(self) -> None:
        for app_home in (self.app_home, self.tmp / "Other" / "TH"):
            with self.subTest(app_home=str(app_home)):
                ctx = self.ctx_for(app_home)
                self.quiet(autostart.enable, ctx)
                self.quiet(autostart.shortcuts, ctx, True)
                self.check_files(app_home)
        uid = os.getuid()
        argvs = [c["argv"] for c in self.calls("launchctl")]
        self.assertIn(["bootstrap", f"gui/{uid}", str(self.plist)], argvs)
        self.assertEqual(argvs[0], ["bootout", f"gui/{uid}/vn.thomhouse.bot"])

    def test_commands_and_flag(self) -> None:
        from thomhouse_installer import state as st

        st.save_installed(self.paths(), {"schema": 1, "version": "1.4.0", "autostart": False})
        ctx = self.ctx()
        self.assertEqual(self.quiet(autostart.cmd_autostart, ctx, _ns(state="on")), 0)
        self.assertTrue(st.load_installed(self.paths())["autostart"])
        self.assertTrue(self.plist.exists())
        self.assertEqual(self.quiet(autostart.cmd_shortcuts, ctx, _ns(state="on")), 0)
        self.assertTrue(self.out.startswith(t("ops.desktop_prompt")))  # shown before the files are written
        self.assertEqual(self.quiet(autostart.cmd_autostart, ctx, _ns(state="off")), 0)
        self.assertFalse(self.plist.exists())
        self.assertFalse(st.load_installed(self.paths())["autostart"])
        self.assertEqual(self.quiet(autostart.cmd_shortcuts, ctx, _ns(state="off")), 0)
        self.assertEqual(list((self.home / "Desktop").iterdir()), [])

    def test_changed_or_foreign_files_left_alone(self) -> None:
        ctx = self.ctx()
        foreign = self.home / "Desktop" / "Bat-chatbot.command"
        foreign.write_text("#!/bin/bash\necho someone else's file\n", encoding="utf-8")
        self.quiet(autostart.shortcuts, ctx, True)
        self.assertIn("someone else", foreign.read_text(encoding="utf-8"))
        self.assertIn(t("ops.shortcut_kept_other", file="~/Desktop/Bat-chatbot.command"), self.out)
        self.quiet(autostart.enable, ctx)
        self.plist.write_text(self.plist.read_text(encoding="utf-8").replace("--quiet", "--quiet "),
                              encoding="utf-8")
        self.quiet(autostart.disable, ctx)
        self.assertTrue(self.plist.exists())
        self.assertIn(t("ops.autostart_kept_edited", file="~/Library/LaunchAgents/vn.thomhouse.bot.plist"),
                      self.out)
        self.assertEqual(sorted(str(p) for p in autostart.owned_files(ctx)),
                         sorted(str(self.home / "Desktop" / n) for n in
                                ("Kiem-tra-chatbot.command", "Tat-chatbot.command")))
        removed = autostart.remove_all(ctx)
        self.assertEqual(len(removed), 2)
        self.assertTrue(foreign.exists())

    def test_bootstrap_failure(self) -> None:
        self.behave(launchctl={"fail": ["bootstrap"]})
        with self.assertRaises(context.InstallerError) as caught:
            self.quiet(autostart.enable, self.ctx())
        self.assertEqual((caught.exception.code, caught.exception.key), (1, "ops.autostart_failed"))

    def test_launch_agent_start_refused_during_unfinished_update(self) -> None:
        state.save_installed(self.paths(), {"schema": 1, "version": "1.4.0"})
        f = "/Volumes/USB/thomhouse-1.5.0.command"
        state.update_set(self.paths(), {"from": "1.4.0", "to": "1.5.0", "file": f, "phases": {
            p: "done" for p in ("U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9")}, "state": "running"})
        ctx = self.ctx()
        self.quiet(autostart.enable, ctx)
        args = plistlib.loads(self.plist.read_bytes())["ProgramArguments"]
        self.assertEqual(args[2:], ["start", "--quiet"])
        res = self.run_cli(None, *args[2:], input="")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), t("core.update_open", file=f))
        self.assertEqual(self.start_calls(), [])
