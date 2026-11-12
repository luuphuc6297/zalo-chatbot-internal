"""The install sequence of 16.4.3: order, the real InstallLock, exit codes 0, 4 and 10, the dry-run plan, resuming
after a failure, the pool account, the shared-data question, the licence notice, menu slides and a move-in
(16.10 test_setup_sequence, rev F3, F9, F18, F20, rev check).

Tests named `test_cli_*` run the real `install/thomhouse.py` (real dispatcher and InstallLock) on a pseudo-terminal;
the others run `steps.cmd_install` / `cmd_continue` in this process the way the dispatcher does. The `test_cli_*`
tests run the real WP2, WP4 and WP5 modules; the in-process tests use the stand-ins of tests/fakes_setup.
"""

from __future__ import annotations

import json
import os
import sqlite3

from tests.fakes_setup import DESKTOP_PROMPT, SetupTestCase
from thomhouse_installer import paths as paths_mod, state, steps
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
EVERY_HUMAN_STEP = "dong y\nc\nc\nc\nc\nc\nc\nc\nk\n"  # notice, Claude, Zalo, sync, labels x2, token, autostart, shortcuts
DONE = ("done", None)
LATER = ("pending", "later")
# The journal after `install --skip-human --yes` with a Zalo cache and the stub server's default routes.
CLEAN = {
    "verify": DONE, "preflight": DONE, "unpack": DONE, "python": DONE, "runtimes": DONE, "engine_notice": DONE,
    "deps": DONE, "activate": DONE, "config": DONE, "move_in": ("skipped", None), "menu_slides": ("pending", None),
    "migrations": DONE, "pool": DONE, "claude_login": LATER, "start": DONE, "zalo_login": DONE,
    "history_sync": LATER, "analyze_contacts": DONE, "analyze_visits": DONE, "labels": DONE, "staff_token": LATER,
    "autostart": DONE, "shortcuts": DONE, "menu_check": DONE, "final_check": DONE,
}
FIRST_INSTALL = ("install", "--from-bootstrap", "--consented", "node,pnpm,claude_code", "--skip-human", "--yes")


def first_index(calls: list[dict], tool: str, *argv_start: str) -> int:
    for i, call in enumerate(calls):
        if call["tool"] == tool and call["argv"][:len(argv_start)] == list(argv_start):
            return i
    raise AssertionError(f"no call of {tool} {' '.join(argv_start)}")


class CliSequenceTest(SetupTestCase):
    def test_cli_full_install_in_order_exit_0(self) -> None:
        root = self.new_device(zalo_cache=True)
        self.behave(bridge={"doctor": {"zalo_login": "fail", "listener": "fail"}})  # so step 16 asks
        self.server.set_route("GET /staff/roles", 200, {"roles": []})  # so step 20 asks
        res = self.run_cli_tty(root, "install", "--from-bootstrap", answers=EVERY_HUMAN_STEP)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for step in steps.STEPS:
            self.assertIn(t("setup.step_line", n=step.n, title=t(step.title_key)), res.stdout)
        journal = self.summary(root)
        for step_id in ("preflight", "claude_login", "zalo_login", "history_sync", "labels", "staff_token",
                        "final_check"):
            self.assertEqual(journal[step_id], DONE, step_id)
        self.assertEqual(journal["shortcuts"], ("declined", None))
        self.assertIn(t("setup.summary_running", version="1.4.0", url=self.server.url), res.stdout)
        self.assertNotIn("[LỖI]", res.stdout)
        # R4 order: config, migrations, pool and Claude login, start, Zalo, history, analyzers, labels, token,
        # autostart, menu images, final check (16.4.3).
        calls = self.calls()
        order = [
            first_index(calls, "npm", "ci"),
            first_index(calls, "bridge", "init-env"),
            first_index(calls, "wrangler", "d1", "migrations", "apply"),
            first_index(calls, "claude", "auth", "login"),
            first_index(calls, "start_local.sh"),
            first_index(calls, "zalo-agent", "--json", "login"),
            first_index(calls, "bridge", "listener", "start"),
            first_index(calls, "zalo-agent", "--json", "sync"),
            first_index(calls, "analyze_contacts", "--push"),
            first_index(calls, "analyze_visits", "--push"),
            first_index(calls, "bridge", "sync-labels", "--dry-run"),
            first_index(calls, "pbcopy"),
            first_index(calls, "launchctl", "bootstrap"),  # autostart.enable (16.8.8)
            first_index(calls, "build_menu_images"),
        ]
        self.assertEqual(order, sorted(order))
        # The pool existed before the start (step 13 before the catalog seed of step 15), main logged in.
        self.assertEqual([(a["label"], a["enabled"]) for a in self.pool()], [("main", True)])
        p = paths_mod.resolve(os.environ, code_root=root)
        self.assertIsNone(state.lock_holder(p))  # released at the end
        installed = self.installed()
        self.assertTrue(installed["install_completed_at"])
        self.assertTrue(installed["engine_notice_accepted_at"])

    def test_cli_skip_human_exits_10(self) -> None:
        root = self.new_device()
        self.behave(bridge={"doctor": {"zalo_login": "fail", "listener": "fail"}})
        res = self.run_cli_tty(root, "install", "--from-bootstrap", "--skip-human", answers="dong y\nk\nk\n")
        self.assertEqual(res.returncode, 10, res.stdout + res.stderr)
        self.assertNotIn("[LỖI]", res.stdout)
        journal = self.summary(root)
        for step_id in ("claude_login", "zalo_login", "staff_token"):
            self.assertEqual(journal[step_id], LATER, step_id)
        # Step 2 and the final doctor's install_lock check passed while the command held its own lock (rev F3).
        self.assertEqual(journal["preflight"], DONE)
        self.assertEqual(journal["final_check"], DONE)
        self.assertIn(t("setup.step_postponed", tb=TB), res.stdout)
        self.assertNotIn(t("setup.claude_screen"), res.stdout)

    def test_cli_dry_run_changes_nothing(self) -> None:
        root = self.new_device()
        before = self.tree_snapshot()
        res = self.run_cli(root, "install", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        after = self.tree_snapshot()
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        self.assertEqual(changed, set())  # 16.4.5: not even the dispatcher's log line
        self.assertIsNone(state.lock_holder(paths_mod.resolve(os.environ, code_root=root)))
        self.assertIn(t("setup.plan_head", version="1.4.0"), res.stdout)


class SequenceTest(SetupTestCase):
    def test_dry_run_writes_nothing_and_prints_every_title(self) -> None:
        root = self.new_device(runtimes=("python",))
        before = self.tree_snapshot()
        runtime_calls = len(self.calls("stub.runtimes"))
        code, out = self.run_steps(root, "install", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.tree_snapshot(), before)
        self.assertEqual(len(self.calls("stub.runtimes")), runtime_calls)  # no plan, no install
        lines = out.splitlines()
        self.assertEqual(lines[0], t("setup.plan_head", version="1.4.0"))
        for step in steps.STEPS:
            self.assertTrue(any(line.startswith(f"{step.n:>3}. [") and t(step.title_key) in line for line in lines),
                            step.id)
        self.assertIn(f"  4. [{t('setup.mark_done')}] {t('setup.title_python')}", out)
        self.assertIn(f"  5. [{t('setup.mark_todo')}] {t('setup.title_runtimes')}", out)
        self.assertIn("Node.js 24.19.0", out)
        self.assertIn(t("setup.plan_claude", v="2.1.319", mb=310), out)
        self.assertIn(f" 10. [{t('setup.mark_skip')}] {t('setup.title_move_in')}", out)
        self.assertIn(f" 25. [{t('setup.mark_todo')}] {t('setup.title_final_check')}", out)

    def test_dry_run_python_line(self) -> None:
        root = self.new_device(runtimes=())
        code, out = self.run_steps(root, "install", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"  4. [{t('setup.mark_todo')}] {t('setup.title_python')}: Python 3.14.6", out)

    def test_pool_is_main_with_own_folder_disabled_until_login(self) -> None:
        root = self.new_device()
        code, out = self.run_steps(root, *FIRST_INSTALL, answers="dong y\n")
        self.assertEqual(code, 10, out)
        main = self.bot_home / "accounts" / "main"
        self.assertEqual(self.pool(), [{"label": "main", "config_dir": str(main), "priority": 1, "enabled": False}])
        self.assertTrue((main / "projects").is_symlink())
        self.assertFalse((self.home / ".claude").exists())

    def test_shared_data_question_not_answered_by_yes(self) -> None:
        root = self.new_device()
        folder = self.bot_home / "d1" / "v3" / "d1" / "miniflare-D1DatabaseObject"
        folder.mkdir(parents=True)
        con = sqlite3.connect(folder / ("a" * 64 + ".sqlite"))
        con.execute("CREATE TABLE d1_migrations (id INTEGER PRIMARY KEY, name TEXT)")
        con.execute("INSERT INTO d1_migrations (name) VALUES ('0001_init.sql')")
        con.commit()
        con.close()
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--yes", interactive=False)
        self.assertEqual(code, 4, out)
        self.assertIn(t("setup.shared_data", folder="~/.thomhouse-bot"), out)
        self.assertIn(t("core.answer_noninteractive", answer="k"), out)
        self.assertNotIn(t("core.answer_yes"), out)
        self.assertNotIn(t("setup.step_line", n=3, title=t("setup.title_unpack")), out)
        self.assertEqual(self.summary(root)["preflight"], ("pending", "declined"))
        # The person answers c: the answer is journaled and not asked again.
        code, out = self.run_steps(root, *FIRST_INSTALL, answers="c\ndong y\n")
        self.assertEqual(code, 10, out)
        entry = self.journal(root)["preflight"]
        self.assertEqual((entry["status"], entry["shared_data_accepted"]), ("done", True))
        code, out = self.run_steps(root, "continue", "--skip-human", answers="")
        self.assertEqual(code, 10, out)
        self.assertNotIn(t("setup.shared_data", folder="~/.thomhouse-bot"), out)

    def test_declined_notice_asked_again(self) -> None:
        root = self.new_device()
        for _ in range(2):
            code, out = self.run_steps(root, "install", "--from-bootstrap", answers="\n")
            self.assertEqual(code, 4, out)
            self.assertIn(t("setup.engine_notice", v="2.5.9"), out)
            self.assertEqual(self.summary(root)["engine_notice"], ("pending", "declined"))
            self.assertFalse([c for c in self.calls("npm") if "tools/zalo-agent" in " ".join(c["argv"])])
            self.assertNotIn("deps", self.summary(root))
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--skip-human", answers="đồng ý\nk\nk\n")
        self.assertEqual(code, 10, out)
        self.assertTrue([c for c in self.calls("npm") if "tools/zalo-agent" in " ".join(c["argv"])])
        accepted = self.journal(root)["engine_notice"]["accepted_at"]
        self.assertEqual(self.installed()["engine_notice_accepted_at"], accepted)

    def test_shortcuts_step_prints_desktop_line_first(self) -> None:
        root = self.new_device()
        code, out = self.run_steps(root, *FIRST_INSTALL, answers="dong y\n")
        self.assertEqual(code, 10, out)
        mark = self.stubs["autostart"].SHORTCUTS_MARK
        self.assertLess(out.index(DESKTOP_PROMPT), out.index(mark))
        self.assertEqual(out.count(DESKTOP_PROMPT), 1)
        self.assertIn(["shortcuts", "True"], self.stub_calls("autostart"))
        self.assertEqual(self.summary(root)["shortcuts"], DONE)

    def test_menu_archive_missing_then_found_by_continue(self) -> None:
        root = self.new_device()
        usb = self.tmp / "usb"
        usb.mkdir()
        release_file = usb / "thomhouse-1.4.0.command"
        release_file.write_text("#!/bin/bash\n", encoding="utf-8")
        code, out = self.run_steps(root, *FIRST_INSTALL, "--release-file", str(release_file), answers="dong y\n")
        self.assertEqual(code, 10, out)
        self.assertIn(t("setup.menu_missing", menu_id="0" * 16, tb=TB), out)
        self.assertEqual(self.summary(root)["menu_slides"], ("pending", None))
        self.assertEqual(self.installed()["release_id"], "ABCD-0123-4567-89EF")
        (usb / f"thomhouse-menu-{'0' * 16}.tar").write_bytes(b"tar")
        code, out = self.run_steps(root, "continue", "--skip-human", answers="")
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(root)["menu_slides"], DONE)
        self.assertIn(["install_menu", str(usb / f"thomhouse-menu-{'0' * 16}.tar")], self.stub_calls("release"))

    def test_menu_archive_given_with_only(self) -> None:
        root = self.new_device()
        self.run_steps(root, *FIRST_INSTALL, answers="dong y\n")
        archive = self.tmp / f"thomhouse-menu-{'0' * 16}.tar"
        archive.write_bytes(b"tar")
        code, out = self.run_steps(root, "install", "--only", "menu_slides", "--menu", str(archive), answers="")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.summary(root)["menu_slides"], DONE)
        code, out = self.run_steps(root, "install", "--only", "no_such_step", answers="")
        self.assertEqual(code, 2)
        self.assertIn(t("setup.only_unknown", name="no_such_step"), out)

    def test_move_in_then_login_for_each_account(self) -> None:
        root = self.new_device()
        image = self.tmp / "thomhouse-chuyen-may.json"
        image.write_text(json.dumps({"accounts": [{"label": "default", "config_dir": None, "priority": 1},
                                                  {"label": "acc2", "priority": 2}]}), encoding="utf-8")
        code, out = self.run_steps(root, *FIRST_INSTALL, "--move-in", str(image), answers="dong y\n")
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(root)["move_in"], DONE)
        self.assertEqual([(a["label"], a["enabled"]) for a in self.pool()], [("default", False), ("acc2", False)])
        before = len(self.calls("claude"))
        code, out = self.run_steps(self.app_home / "app", "install", "--only", "claude_login", answers="c\nc\n")
        self.assertEqual(code, 0, out)
        logins = [c["env"]["CLAUDE_CONFIG_DIR"] for c in self.calls("claude")[before:] if c["argv"][:2] == ["auth", "login"]]
        self.assertEqual(logins, [str(self.bot_home / "accounts" / "default"), str(self.bot_home / "accounts" / "acc2")])
        self.assertEqual([(a["label"], a["enabled"]) for a in self.pool()], [("default", True), ("acc2", True)])
        self.assertEqual(self.summary()["claude_login"], DONE)
        # The same image again: step 10 is done by its check.
        code, out = self.run_steps(root, "install", "--only", "move_in", "--move-in", str(image), answers="")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.stub_calls("move")), 1)

    def test_refusals(self) -> None:
        root = self.new_device()
        p = paths_mod.resolve(os.environ, code_root=root)
        state.update_set(p, {"from": "1.3.0", "to": "1.4.0", "file": "/Volumes/USB/thomhouse-1.4.0.command",
                             "phases": {"U7": "running"}, "state": "running"})
        code, out = self.run_steps(root, "install", "--from-bootstrap", answers="")
        self.assertEqual(code, 3)
        self.assertIn(t("core.update_open", file="/Volumes/USB/thomhouse-1.4.0.command"), out)
        state.update_set(p, None)
        state.set_moved_out(p, {"image_name": "x.dmg", "image_sha256": "0" * 64})
        code, out = self.run_steps(root, "continue", answers="")
        self.assertEqual(code, 3)
        self.assertIn(t("core.moved_out", tb=TB), out)
        self.assertEqual(self.summary(root), {})


def _set_uid_root(tc) -> None:
    tc.behave(system={"uid": 0})


def _unset_uid_root(tc) -> None:
    tc.behave(system={"uid": os.getuid()})


def _block_pool(tc) -> None:
    tc.bot_home.mkdir(parents=True, exist_ok=True)
    (tc.bot_home / "accounts").write_text("not a folder", encoding="utf-8")


def _unblock_pool(tc) -> None:
    (tc.bot_home / "accounts").unlink()


# step id: (break the step, repair it, exit code of the broken run)
FAILURES = {
    "preflight": (_set_uid_root, _unset_uid_root, 3),
    "runtimes": (lambda tc: tc.behave(stub_runtimes={"fail": "node"}),
                 lambda tc: tc.behave(stub_runtimes={"fail": None}), 1),
    "deps": (lambda tc: tc.behave(pnpm={"fail": True}), lambda tc: tc.behave(pnpm={"fail": False}), 1),
    "activate": (lambda tc: tc.behave(stub_release={"fail": "switch_app"}),
                 lambda tc: tc.behave(stub_release={"fail": None}), 3),  # ReleaseError has exit code 3
    "config": (lambda tc: tc.behave(bridge={"init_env_exit": 1}), lambda tc: tc.behave(bridge={"init_env_exit": 0}),
               1),
    "migrations": (lambda tc: tc.behave(wrangler={"fail_at": 2}), lambda tc: tc.behave(wrangler={"fail_at": None}),
                   1),
    "pool": (_block_pool, _unblock_pool, 1),
    "start": (lambda tc: tc.behave(start_local={"exit": 1}), lambda tc: tc.behave(start_local={"exit": 0}), 1),
    "analyze_contacts": (lambda tc: tc.behave(analyze_contacts={"exit": 1}),
                         lambda tc: tc.behave(analyze_contacts={"exit": 0}), 10),
    "analyze_visits": (lambda tc: tc.behave(analyze_visits={"not_found": True}),
                       lambda tc: tc.behave(analyze_visits={"not_found": False}), 10),
    "autostart": (lambda tc: tc.behave(stub_autostart={"fail": "enable"}),
                  lambda tc: tc.behave(stub_autostart={"fail": None}), 10),
    "menu_check": (lambda tc: tc.behave(build_menu_images={"check_exit": 1, "exit": 1}),
                   lambda tc: tc.behave(build_menu_images={"check_exit": 0, "exit": 0}), 10),
    "final_check": (lambda tc: tc.behave(stub_doctor={"status": {"processes": "fail"}}),
                    lambda tc: tc.behave(stub_doctor={"status": {}}), 1),
}


class ResumeTest(SetupTestCase):
    """A failure injected at a step, then `continue`, ends in the journal of a clean run (16.10)."""

    def _first_install(self) -> tuple:
        root = self.new_device(runtimes=("python",), zalo_cache=True)
        return root, self.run_steps(root, *FIRST_INSTALL, answers="dong y\n")

    def test_clean_run(self) -> None:
        root, (code, out) = self._first_install()
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(root), CLEAN)

    def _resume(self, step_id: str) -> None:
        breaker, repair, expected = FAILURES[step_id]
        breaker(self)
        root, (code, out) = self._first_install()
        self.assertEqual(code, expected, out)
        self.assertNotEqual(self.summary(root).get(step_id), CLEAN[step_id], out)
        repair(self)
        code, out = self.run_steps(root, "continue", "--skip-human", "--yes", answers="dong y\n")
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(root), CLEAN)


def _make_resume_test(step_id: str):
    def test(self) -> None:
        self._resume(step_id)
    test.__doc__ = f"failure at {step_id}, then continue"
    return test


for _step_id in FAILURES:
    setattr(ResumeTest, f"test_resume_after_{_step_id}", _make_resume_test(_step_id))
