"""Zalo QR login through the engine's --json events (16.6.2): the QR page or file is opened, nothing of the events
(QR data URL, name, Zalo id) is shown or logged, no QR address option is passed, ZALO_AGENT_NO_UPDATE_CHECK=1 is set,
and the listener's exit codes 0, 3, 4 and others lead where the contract says."""

from __future__ import annotations

import argparse
import socket
import time
from unittest import mock

from tests.fakes_setup import SetupTestCase, free_port
from thomhouse_installer import human
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
PERSONAL = ("RkFLRVFS", "data:image", "Ten Gia", "999000111", "example.invalid")
ARGS = argparse.Namespace(command="login-zalo")


class ZaloLoginTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installed_device()
        self.port = free_port()
        patcher = mock.patch.object(human, "QR_PORT", self.port)
        patcher.start()
        self.addCleanup(patcher.stop)

    def logins(self) -> list[list]:
        return [c["argv"] for c in self.calls("zalo-agent") if "login" in c["argv"]]

    def opened(self) -> list[list]:
        return [c["argv"] for c in self.calls("open")]

    def test_qr_page_opened_when_port_free(self) -> None:
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.opened(), [[f"http://127.0.0.1:{self.port}/qr"]])
        for key in ("setup.zalo_qr_opened", "setup.zalo_scanned", "setup.zalo_done"):
            self.assertIn(t(key), out)
        self.assertEqual([c["argv"] for c in self.calls("bridge")][-1], ["listener", "start"])
        self.assertEqual(self.summary()["zalo_login"], ("done", None))

    def test_qr_file_opened_when_port_busy(self) -> None:
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.bind(("127.0.0.1", self.port))
        busy.listen(1)
        self.addCleanup(busy.close)
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.opened(), [[str(self.tmp / "qr.png")]])

    def test_events_never_shown_or_logged(self) -> None:
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(code, 0)
        log = self.install_log()
        for value in PERSONAL:
            self.assertNotIn(value, out)
            self.assertNotIn(value, log)

    def test_no_qr_address_option_and_no_update_check(self) -> None:
        self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(self.logins(), [["--json", "login"]])
        for argv in [c["argv"] for c in self.calls("zalo-agent")]:
            self.assertFalse([a for a in argv if a.startswith(("--qr-url", "--credentials"))], argv)
        values = (self.tmp / "zalo-nouc.txt").read_text(encoding="utf-8").split()
        self.assertEqual(set(values), {"1"})

    def test_postponed(self) -> None:
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="s\n")
        self.assertEqual(code, 4)
        self.assertEqual(self.logins(), [])
        self.assertIn(t("setup.zalo_later", tb=TB), out)
        self.assertEqual(self.summary()["zalo_login"], ("pending", "later"))

    def test_declined_on_phone_asks_again(self) -> None:
        self.behave(zalo_agent={"login": "declined"})
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertEqual(len(self.logins()), 2)
        self.assertEqual(out.count(t("setup.zalo_retry")), 2)
        self.assertNotIn(["listener", "start"], [c["argv"] for c in self.calls("bridge")])

    def test_login_error_asks_again(self) -> None:
        self.behave(zalo_agent={"login": "error"})
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\ns\n")
        self.assertEqual(code, 4)
        self.assertIn(t("setup.zalo_retry"), out)

    def test_no_success_within_the_limit(self) -> None:
        self.behave(zalo_agent={"login": "hang"})
        start = time.monotonic()
        with mock.patch.object(human, "ZALO_LOGIN_TIMEOUT_S", 1.0):
            code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\ns\n")
        self.assertEqual(code, 4)
        self.assertIn(t("setup.zalo_retry"), out)
        self.assertLess(time.monotonic() - start, 20)

    def test_foreign_daemon_offers_the_stop(self) -> None:
        self.behave(bridge={"listener": {"start": [4, {"foreign": True}]}})
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\nc\ns\n")
        self.assertEqual(code, 4)
        self.assertEqual(out.count(t("setup.zalo_foreign")), 2)
        stops = [c["argv"] for c in self.calls("zalo-agent") if c["argv"][:1] == ["listen"]]
        self.assertEqual(stops, [["listen", "--stop"]])
        starts = [c for c in self.calls("bridge") if c["argv"] == ["listener", "start"]]
        self.assertEqual(len(starts), 2)

    def test_listener_not_logged_in_goes_back_to_the_question(self) -> None:
        self.behave(bridge={"listener": {"start": [3, {}]}})
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\ns\n")
        self.assertEqual(code, 4)
        self.assertIn(t("setup.zalo_retry"), out)

    def test_listener_other_failure_is_pending(self) -> None:
        self.behave(bridge={"listener": {"start": [1, {}]}})
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.zalo_listener_failed", tb=TB), out)
        self.assertEqual(self.summary()["zalo_login"], ("pending", None))

    def test_engine_missing(self) -> None:
        (self.app_home / "app" / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent").unlink()
        code, out = self.run_flow(human.cmd_login_zalo, ARGS, answers="c\n")
        self.assertEqual(code, 1)
        self.assertIn(t("setup.zalo_no_engine", tb=TB), out)
