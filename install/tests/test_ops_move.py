"""move.py: move-out marks the Mac and builds an encrypted image without secrets (installed and checkout mode),
move-in places the data with every Claude account disabled and this device's secrets kept, the newer-image rule,
move-back (16.8.5, rev F12, F16, F18, rev check)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase
from thomhouse_installer import backup, envs, move, state
from thomhouse_installer.text_vi import t


def _ns(**attrs: object) -> argparse.Namespace:
    ns = {"command": "move", "yes": False, "dry_run": False, "quiet": False, "offline": False, "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


class MoveTest(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.usb = self.tmp / "usb"
        self.usb.mkdir()

    def append_env(self, name: str, text: str) -> None:
        f = self.paths().env_file(name)
        f.write_text(f.read_text(encoding="utf-8") + text, encoding="utf-8")

    def move_out(self, code_root: Path | None = None) -> int:
        self.answer("c\n")
        return self.quiet(move.cmd_move_out, self.ctx(code_root, interactive=True), _ns(to=self.usb))

    def image_names(self, image: Path) -> list[str]:
        with tarfile.open(image) as tar:
            return tar.getnames()

    def image_member(self, image: Path, name: str) -> bytes:
        with tarfile.open(image) as tar:
            return tar.extractfile(name).read()

    def make_image(self, *, app_version: str | None = None, extra_migration: str | None = None) -> Path:
        """An image built like move-out does, with backup.json edited to look like another Mac's."""
        info = backup.make(self.ctx(), mode="online", reason="move")
        staging = self.tmp / "staging"
        move._build_staging(self.ctx(), info.path, staging)
        meta = json.loads((staging / "backup.json").read_text(encoding="utf-8"))
        if app_version:
            meta["app_version"] = app_version
        if extra_migration:
            meta["migrations_applied"].append(extra_migration)
        (staging / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
        image = self.tmp / "made.dmg"
        with tarfile.open(image, "w") as tar:
            for name in sorted(os.listdir(staging)):
                tar.add(staging / name, arcname=name)
        shutil.rmtree(staging)
        shutil.rmtree(info.path)
        return image

    # ------------------------------------------------------------ move-out

    def test_move_out_marks_the_mac_and_leaves_secrets_out(self) -> None:
        self.installed()
        self.append_env("runner", "ROOM_FALLBACK=claude\nTHOMHOUSE_DRAFT_ENGINE=rooms\nTHOMHOUSE_CLAUDE_MODEL=opus\n")
        self.append_env("bridge", "SEND_MIN_INTERVAL_S=3\n")
        staff = envs.value(self.paths(), "server", "STAFF_TOKEN")
        code = self.move_out()
        self.assertEqual(code, 0, self.out)
        mark = state.moved_out(self.paths())
        image = self.usb / mark["image_name"]
        self.assertTrue(image.name.startswith("thomhouse-chuyen-may-") and image.name.endswith(".dmg"))
        self.assertEqual(mark["image_sha256"], backup.sha256_file(image))
        self.assertEqual(oct(image.stat().st_mode & 0o777), "0o600")
        create = [c for c in self.calls("hdiutil") if c["argv"][0] == "create"][0]["argv"]
        self.assertEqual(create[:3], ["create", "-encryption", "AES-256"])
        self.assertEqual(create[-5:], ["-volname", "thomhouse-chuyen-may", "-format", "UDZO", str(image)])
        listener = [c["argv"] for c in self.calls("bridge") if c["argv"][:1] == ["listener"]]
        self.assertEqual(listener, [["listener", "stop"]])  # without --only-ours: the Zalo session is freed
        self.assertTrue(any(c["argv"][0] == "bootout" for c in self.calls("launchctl")))
        names = self.image_names(image)
        self.assertFalse([n for n in names if n.startswith("env/") or n == "env"])
        self.assertIn("env-settings.json", names)
        settings = json.loads(self.image_member(image, "env-settings.json"))
        self.assertEqual(settings["files"], {"runner": {"ROOM_FALLBACK": "claude", "THOMHOUSE_CLAUDE_MODEL": "opus"},
                                             "bridge": {"SEND_MIN_INTERVAL_S": "3"}})
        with tarfile.open(image) as tar:
            for member in tar.getmembers():
                if member.isfile():
                    data = tar.extractfile(member).read()
                    self.assertNotIn(b"THOMHOUSE_DRAFT_ENGINE", data, member.name)
                    self.assertNotIn(staff.encode(), data, member.name)
        self.assertFalse(list((self.bot_home / "backups").glob(".staging-move-*")))
        self.assertEqual(self.alive_services(), set())
        out = self.out
        self.assertLess(out.index(t("ops.hdiutil_create")), out.index(t("ops.move_out_last")))
        res = self.run_cli(None, "start")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn(t("core.moved_out", tb="~/ThomHouse/bin/thomhouse"), res.stdout)

    def test_move_out_checkout_mode(self) -> None:
        checkout = self.make_checkout()
        self.seed_d1(checkout)
        code = self.move_out(checkout)
        self.assertEqual(code, 0, self.out)
        self.assertEqual([c["cwd"] for c in self.stop_calls()], [os.path.realpath(checkout)])
        mark = state.moved_out(self.paths(checkout))
        self.assertTrue((self.usb / mark["image_name"]).is_file())
        self.assertEqual(self.calls("launchctl"), [])
        meta = json.loads(self.image_member(self.usb / mark["image_name"], "backup.json"))
        self.assertEqual(meta["app_version"], "checkout")
        self.assertFalse(self.app_home.exists())

    def test_move_out_declined_or_image_failure_leaves_no_mark(self) -> None:
        self.installed()
        self.answer("k\n")
        self.assertEqual(self.quiet(move.cmd_move_out, self.ctx(interactive=True), _ns(to=self.usb)), 4)
        self.assertIn("server", self.alive_services())
        self.behave(hdiutil={"fail": ["create"]})
        self.assertEqual(self.move_out(), 1, self.out)
        self.assertIsNone(state.moved_out(self.paths()))
        self.assertIn(t("ops.move_out_image_failed", start="~/ThomHouse/bin/thomhouse start"), self.out)

    def test_move_out_refused_while_d1_restore_needed(self) -> None:
        self.installed()
        folder = self.bot_home / "backups" / "20261112-120000-before-migration"
        (self.bot_home / "d1.restore-needed.json").write_text(
            json.dumps({"backup": folder.name, "backup_path": str(folder), "failed": "x"}), encoding="utf-8")
        self.assertEqual(self.move_out(), 1, self.out)
        self.assertIn(t("setup.restore_needed", folder="~/.thomhouse-bot/backups/" + folder.name,
                        tb="~/ThomHouse/bin/thomhouse"), self.out)
        self.assertIsNone(state.moved_out(self.paths()))
        self.assertEqual(self.stop_calls(), [])
        self.assertEqual(self.calls("hdiutil"), [])

    # ------------------------------------------------------------ move-in

    def test_move_in_default_account_disabled_and_secrets_kept(self) -> None:
        self.installed()
        b = self.bot_home
        (b / "accounts.json").write_text(json.dumps([
            {"label": "default", "config_dir": None, "priority": 1, "enabled": True},
            {"label": "acc2", "config_dir": "/Users/old/.thomhouse-bot/accounts/acc2", "priority": 2,
             "enabled": True}]), encoding="utf-8")
        (b / "account-state.json").write_text(json.dumps({"default": {"status": "ok"}}), encoding="utf-8")
        (b / "bridge").mkdir(exist_ok=True)
        (b / "bridge" / "journal.jsonl").write_text('{"from": "old"}\n', encoding="utf-8")
        self.append_env("runner", "ROOM_FALLBACK=claude\nTHOMHOUSE_DRAFT_ENGINE=rooms\n")
        old_db = self.dumps()
        self.assertEqual(self.move_out(), 0, self.out)
        image = self.usb / state.moved_out(self.paths())["image_name"]
        # Now play the new Mac: its own data, its own settings, no mark.
        state.clear_moved_out(self.paths())
        shutil.rmtree(b / "d1")
        (b / "accounts.json").unlink()
        (b / "bridge" / "journal.jsonl").write_text('{"from": "new"}\n', encoding="utf-8")
        runner = self.paths().env_file("runner")
        runner.write_text("\n".join(x for x in runner.read_text(encoding="utf-8").splitlines()
                                    if not x.startswith(("ROOM_FALLBACK", "THOMHOUSE_DRAFT_ENGINE"))) + "\n",
                          encoding="utf-8")
        staff = envs.value(self.paths(), "server", "STAFF_TOKEN")
        code = self.quiet(move.cmd_move_in, self.ctx(), _ns(file=image))
        self.assertEqual(code, 0, self.out)
        self.assertIn(t("ops.hdiutil_attach"), self.out)
        self.assertIn(t("ops.move_in_done", tb="~/ThomHouse/bin/thomhouse"), self.out)
        accounts = json.loads((b / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual([(a["label"], a["config_dir"], a["enabled"]) for a in accounts],
                         [("default", str(b / "accounts" / "default"), False),
                          ("acc2", str(b / "accounts" / "acc2"), False)])
        link = b / "accounts" / "default" / "projects"
        self.assertEqual(os.readlink(link), str(b / "sessions"))
        self.assertEqual(json.loads((b / "account-state.json").read_text(encoding="utf-8")), {})
        self.assertEqual((b / "bridge" / "journal.jsonl").read_text(encoding="utf-8"), '{"from": "old"}\n')
        self.assertEqual(self.dumps(), old_db)
        self.assertEqual(envs.value(self.paths(), "server", "STAFF_TOKEN"), staff)
        runner_vars = envs.read(runner)
        self.assertEqual(runner_vars.get("ROOM_FALLBACK"), "claude")
        self.assertNotIn("THOMHOUSE_DRAFT_ENGINE", runner_vars)
        aside = [p for p in (b / "backups").iterdir() if p.name.endswith("-before-move-in")]
        self.assertEqual(len(aside), 1)
        self.assertIn('"new"', (aside[0] / "bridge" / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertFalse(list((b / "backups").glob(".mount-*")))
        self.assertEqual(self.history()[-1]["event"], "move_in")
        self.assertIn("server", self.alive_services())

    def test_move_in_checkout_image_judged_by_migrations(self) -> None:
        self.installed()
        image = self.make_image(app_version="checkout")
        self.assertEqual(self.quiet(move.place_moved_data, self.ctx(), image), 0, self.out)
        image = self.make_image(app_version="checkout", extra_migration="0099_future.sql")
        before = self.dumps()
        self.assertEqual(self.quiet(move.place_moved_data, self.ctx(), image), 3, self.out)
        self.assertIn(t("ops.move_in_newer"), self.out)
        self.assertEqual(self.dumps(), before)
        self.assertEqual(len([p for p in (self.bot_home / "backups").iterdir()
                              if p.name.endswith("-before-move-in")]), 1)  # only the first, accepted image
        image = self.make_image(app_version="9.0.0")
        self.assertEqual(self.quiet(move.place_moved_data, self.ctx(), image), 3, self.out)

    def test_move_in_failure_moves_the_data_back(self) -> None:
        self.installed()
        self.append_env("runner", "ROOM_FALLBACK=claude\n")
        image = self.make_image()
        self.append_env("runner", "ROOM_FALLBACK=none\n")
        before = self.dumps()
        runner_before = self.paths().env_file("runner").read_text(encoding="utf-8")
        with mock.patch.object(move, "_rewrite_accounts", side_effect=ValueError("bad account label")):
            code = self.quiet(move.place_moved_data, self.ctx(), image)
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.dumps(), before)
        self.assertEqual(self.paths().env_file("runner").read_text(encoding="utf-8"), runner_before)
        self.assertIn(t("ops.move_in_failed", log="~/ThomHouse/logs/ops.log"), self.out)

    def test_attach_failure_is_no_passphrase(self) -> None:
        self.installed(start=False)
        image = self.make_image()
        self.behave(hdiutil={"fail": ["attach"]})
        self.assertEqual(self.quiet(move.place_moved_data, self.ctx(), image), 4)
        self.assertIn(t("ops.move_in_attach_failed"), self.out)
        self.assertFalse([p for p in (self.bot_home / "backups").iterdir() if "before-move-in" in p.name])

    # ------------------------------------------------------------ move-back

    def test_move_back_removes_the_mark(self) -> None:
        self.installed(start=False)
        state.set_moved_out(self.paths(), {"image_name": "x.dmg", "image_sha256": "0" * 64})
        res = self.run_cli(None, "move-back", input="")
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)  # nobody at the keyboard: k
        self.assertIsNotNone(state.moved_out(self.paths()))
        self.answer("c\n")
        code = self.quiet(move.cmd_move_back, self.ctx(interactive=True), _ns())
        self.assertEqual(code, 0, self.out)
        self.assertIsNone(state.moved_out(self.paths()))
        self.assertIn(t("ops.move_back_done", start="~/ThomHouse/bin/thomhouse start"), self.out)
        self.assertEqual(self.history()[-1]["event"], "move_back")
