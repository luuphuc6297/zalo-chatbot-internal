"""service.py: `start` runs the stack, the health gate and the two safety checks of the doctor; `stop` reports a
survivor; `restart`; the refusals of stack.start (16.3.3 WP5 service.py)."""

from __future__ import annotations

import argparse

from tests.fakes_ops.opscase import OpsTestCase
from thomhouse_installer import context, service, state, steps
from thomhouse_installer.text_vi import t


def _ns(**attrs: object) -> argparse.Namespace:
    ns = {"command": "start", "yes": False, "dry_run": False, "quiet": False, "offline": False, "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


class ServiceTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.use_stubs("doctor")
        self.installed(start=False)

    def test_start_stop_restart(self) -> None:
        code = self.quiet(service.cmd_start, self.ctx(), _ns())
        self.assertEqual(code, 0, self.out)
        self.assertIn(t("core.starting"), self.out)
        self.assertIn(t("ops.start_done"), self.out)
        self.assertEqual(self.stub_calls("doctor.run_checks")[-1]["only"],
                         ["listen_local_only", "openmausbot_options"])
        self.assertTrue({"server", "cron", "runner", "bridge", "console"} <= self.alive_services())
        code = self.quiet(service.cmd_restart, self.ctx(), _ns(command="restart"))
        self.assertEqual(code, 0, self.out)
        self.assertEqual(len(self.stop_calls()), 1)
        code = self.quiet(service.cmd_stop, self.ctx(), _ns(command="stop"))
        self.assertEqual(code, 0, self.out)
        self.assertEqual(self.alive_services(), set())

    def test_quiet_start_prints_only_errors(self) -> None:
        code = self.quiet(service.cmd_start, self.ctx(quiet=True), _ns(quiet=True))
        self.assertEqual((code, self.out), (0, ""))
        self.behave(stubs={"checks": {"openmausbot_options": "fail"}})
        code = self.quiet(service.cmd_start, self.ctx(quiet=True), _ns(quiet=True))
        self.assertEqual(code, 1)
        self.assertIn("[LỖI] stub openmausbot_options", self.out)
        self.assertIn(t("ops.start_unhealthy", tb="~/ThomHouse/bin/thomhouse"), self.out)

    def test_failed_start_and_survivor(self) -> None:
        self.behave(start_local={"exit": 1})
        self.assertEqual(self.quiet(service.cmd_start, self.ctx(), _ns()), 1)
        self.assertIn(t("ops.start_failed", log="~/ThomHouse/logs/start.log", tb="~/ThomHouse/bin/thomhouse"),
                      self.out)
        self.behave(start_local={"exit": 0}, stop_local={"survive": ["runner"]})
        self.assertEqual(self.quiet(service.cmd_start, self.ctx(), _ns()), 0, self.out)
        self.assertEqual(self.quiet(service.cmd_stop, self.ctx(), _ns(command="stop")), 1)
        self.assertIn(t("ops.stop_survivor", tb="~/ThomHouse/bin/thomhouse"), self.out)

    def test_refused_while_d1_restore_needed(self) -> None:
        folder = self.bot_home / "backups" / "20261112-120000-before-migration"
        steps._set_restore_mark(self.paths(), {"backup": folder.name, "backup_path": str(folder), "failed": "x"})
        for quiet in (False, True):
            code = self.quiet(service.cmd_start, self.ctx(quiet=quiet), _ns(quiet=quiet))
            self.assertEqual(code, 3)
            self.assertIn(t("setup.restore_needed", folder="~/.thomhouse-bot/backups/" + folder.name,
                            tb="~/ThomHouse/bin/thomhouse"), self.out)
        self.assertEqual(self.start_calls(), [])

    def test_refused_when_moved_out(self) -> None:
        state.set_moved_out(self.paths(), {"image_name": "x.dmg", "image_sha256": "0" * 64})
        with self.assertRaises(context.Exit) as caught:
            self.quiet(service.cmd_start, self.ctx(), _ns())
        self.assertEqual((caught.exception.code, caught.exception.key), (3, "core.moved_out"))
        self.assertEqual(self.start_calls(), [])
