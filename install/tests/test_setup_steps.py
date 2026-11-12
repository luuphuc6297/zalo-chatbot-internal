"""Single install steps of 16.4.3: runtime consent (rev F11, F15), preflight refusals (16.5, rev F3, F12, F20),
activation (rev F5, F10), configuration, migrations with the restore of a failed apply, start failures, the
consent steps 22 and 23, `--only` exit codes and dry-run markers."""

from __future__ import annotations

import errno
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from unittest import mock

from tests.fakes_setup import SetupTestCase
from tests.support import write_manifest
from thomhouse_installer import context, migrations, platforms, state, steps
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
STEP = {s.id: s for s in steps.STEPS}
SLEEP = "import sys, time; time.sleep(float(sys.argv[1]))"


class RuntimeStepTest(SetupTestCase):
    def test_not_consented_items_are_asked_and_k_exits_4(self) -> None:
        root = self.new_device(runtimes=("python",))
        code, out = self.run_steps(root, "install", "--from-bootstrap", interactive=False)
        self.assertEqual(code, 4, out)
        self.assertIn(t("setup.runtime_plan_head"), out)
        self.assertIn(t("setup.runtime_plan_claude", v="2.1.319", mb=310), out)
        self.assertIn(t("setup.runtime_declined_pnpm", v="10.32.1"), out)
        self.assertIn(t("setup.runtime_declined_claude", v="2.1.319", url="https://claude.ai/install.sh"), out)
        self.assertEqual(self.summary(root)["runtimes"], ("pending", "declined"))
        self.assertNotIn("install", [c[0] for c in self.stub_calls("runtimes")[4:]])
        self.assertNotIn("engine_notice", self.summary(root))  # no later step ran

    def test_consented_items_are_not_asked_again(self) -> None:
        root = self.new_device(runtimes=("python",))
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--consented", "node,pnpm,claude_code",
                                   interactive=False)
        self.assertEqual(code, 4, out)  # stops at the licence notice: nobody can type dong y
        self.assertNotIn(t("setup.runtime_plan_head"), out)
        self.assertEqual(self.summary(root)["runtimes"], ("done", None))
        self.assertEqual(self.summary(root)["engine_notice"], ("pending", "declined"))
        installed = [c[1] for c in self.stub_calls("runtimes") if c[0] == "install"]
        self.assertEqual(installed[-3:], ["node", "pnpm", "claude_code"])
        pnpm = [c for c in self.stub_calls("runtimes") if c[:2] == ["install", "pnpm"]][-1]
        self.assertEqual(pnpm[3], str(self.app_home / "runtime" / "node" / "bin"))

    def test_only_the_missing_consent_is_asked(self) -> None:
        root = self.new_device(runtimes=("python",))
        ctx = self.step_ctx(root, "install", "--from-bootstrap", "--consented", "node", "--yes")
        res, out = self.run_flow(steps._run_runtimes, ctx)
        self.assertEqual(res.status, "done")
        self.assertIn(t("setup.runtime_plan_claude", v="2.1.319", mb=310), out)
        self.assertIn("pnpm 10.32.1", out)
        self.assertNotIn("Node.js", out)

    def test_reused_claude_gets_its_runtime_link(self) -> None:
        root = self.new_device()
        (self.app_home / "runtime" / "bin" / "claude").unlink()
        ctx = self.step_ctx(root, "install")
        self.assertFalse(STEP["runtimes"].check(ctx))
        res, out = self.run_flow(steps._run_runtimes, ctx)
        self.assertEqual(res.status, "done")
        self.assertNotIn("install", [c[0] for c in self.stub_calls("runtimes")[8:]])
        self.assertTrue((self.app_home / "runtime" / "bin" / "claude").is_symlink())
        self.assertTrue(STEP["runtimes"].check(ctx))

    def test_runtime_failure_stops_with_its_error(self) -> None:
        root = self.new_device(runtimes=("python",))
        self.behave(stub_runtimes={"fail": "pnpm"})
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--consented", "node,pnpm,claude_code",
                                   interactive=False)
        self.assertEqual(code, 1)
        self.assertEqual(self.summary(root)["runtimes"], ("failed", None))
        self.assertIn(t("core.failed"), out)


class PreflightTest(SetupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.new_device()

    def preflight(self, *argv: str, answers: str = "", interactive: bool = False):
        ctx = self.step_ctx(self.root, *(argv or ("install", "--from-bootstrap")), interactive=interactive)
        return self.run_flow(steps._run_preflight, ctx, answers=answers)

    def test_passes_on_a_supported_mac(self) -> None:
        res, out = self.preflight()
        self.assertEqual((res.status, res.exit), ("done", None))

    def test_old_macos(self) -> None:
        self.behave(system={"macos": "13.4"})
        res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_macos", v="13.4", min="13.5"), out)

    def test_root(self) -> None:
        self.behave(system={"uid": 0})
        res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_root"), out)

    def test_not_a_mac(self) -> None:
        self.behave(system={"os": "Linux"})
        res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_not_mac", min="13.5", name="Linux"), out)

    def test_intel_asks_and_needs_its_pins(self) -> None:
        self.behave(system={"cpu": "x64"})
        res, out = self.preflight("install")
        self.assertEqual((res.status, res.reason, res.exit), ("pending", "declined", 4))
        self.assertIn(t("setup.preflight_intel"), out)
        res, out = self.preflight("install", answers="c\n", interactive=True)
        self.assertEqual(res.exit, 3)  # the darwin-x64 pins are still null in versions.json
        self.assertIn(t("setup.preflight_intel_no_pins"), out)

    def test_disk_and_tools(self) -> None:
        with mock.patch.object(platforms, "free_gb", return_value=1.25):
            res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_disk", n="1.2", m=3), out)
        empty = self.tmp / "no-tools"
        empty.mkdir()
        with mock.patch.object(steps, "TOOL_DIRS", (str(empty),)):
            res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_tools", name=", ".join(steps.STOCK_TOOLS)), out)

    def test_moved_out(self) -> None:
        p = self.paths(self.root)
        state.set_moved_out(p, {"image_name": "x.dmg", "image_sha256": "0" * 64})
        with self.assertRaises(context.Exit) as cm:
            self.preflight()
        self.assertEqual((cm.exception.code, cm.exception.key), (3, "core.moved_out"))

    def test_lock_held_by_another_process(self) -> None:
        lock = self.paths(self.root).lock_file
        lock.parent.mkdir(parents=True, exist_ok=True)
        code = ("import fcntl, os, sys, time\nfd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
                "fcntl.flock(fd, fcntl.LOCK_EX)\nos.write(fd, b'%d\\n' % os.getpid())\nprint('locked', flush=True)\n"
                "time.sleep(60)\n")
        holder = subprocess.Popen([sys.executable, "-c", code, str(lock)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "locked")
        with self.assertRaises(state.Locked) as cm:
            self.preflight()
        self.assertEqual(cm.exception.pid, holder.pid)

    def test_other_stack(self) -> None:
        other = self.tmp / "other" / "apps" / "server"
        other.mkdir(parents=True)
        p = self.paths(self.root)
        p.run_dir.mkdir(parents=True, exist_ok=True)
        sleeper = subprocess.Popen([sys.executable, "-c", SLEEP, "60", f"{self.tmp}/other/apps/server/"],
                                   cwd=str(other), start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        (p.run_dir / "server.pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")
        res, out = self.preflight()
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.preflight_other_stack", folder=os.path.realpath(self.tmp / "other")), out)


class StepUnitTest(SetupTestCase):
    def installed_run(self) -> tuple:
        root = self.new_device()
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--skip-human", "--yes", answers="dong y\n")
        self.assertEqual(code, 10, out)
        return root, self.app_home / "app"

    def test_activation_writes_installed_json_and_trust(self) -> None:
        root = self.new_device()
        trust = root / "install" / "trust"
        trust.mkdir(parents=True)
        key = self.tmp / "release-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "thomhouse-release", "-f", str(key)],
                       check=True, stdin=subprocess.DEVNULL)
        public = (self.tmp / "release-key.pub").read_text(encoding="utf-8").split()
        (trust / "allowed_signers").write_text(
            f'thomhouse-release namespaces="thomhouse-release" {public[0]} {public[1]}\n', encoding="utf-8")
        write_manifest(root)
        release_file = self.tmp / "thomhouse-1.4.0.command"
        release_file.write_text("#!/bin/bash\n", encoding="utf-8")
        code, out = self.run_steps(root, "install", "--from-bootstrap", "--release-file", str(release_file),
                                   "--skip-human", "--yes", answers="dong y\n")
        self.assertEqual(code, 10, out)
        data = self.installed()
        self.assertRegex(data["device_id"], r"^[0-9a-f]{32}$")
        self.assertEqual((data["version"], data["previous_version"]), ("1.4.0", None))
        self.assertEqual(data["release_id"], "ABCD-0123-4567-89EF")
        self.assertEqual(data["payload_sha256"], "ab" * 32)
        self.assertEqual(data["runtimes"], {"python": "3.14.6", "node": "24.19.0", "pnpm": "10.32.1",
                                            "claude_code": "2.1.319"})
        self.assertEqual(data["migrations_applied"], ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])
        self.assertTrue(data["install_completed_at"])
        self.assertTrue(data["autostart"])
        fingerprint = subprocess.run(["ssh-keygen", "-l", "-f", str(self.tmp / "release-key.pub")],
                                     capture_output=True, text=True, check=True).stdout.split()[1]
        self.assertEqual(data["signer"], fingerprint)
        stored = self.app_home / "trust" / "allowed_signers"
        self.assertEqual(stored.read_bytes(), (trust / "allowed_signers").read_bytes())
        self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(stored.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.app_home / "installed.json").stat().st_mode), 0o600)
        self.assertEqual(os.readlink(self.app_home / "app"), "releases/1.4.0")
        history = (self.app_home / "history.jsonl").read_text(encoding="utf-8")
        self.assertIn('"event": "install"', history)

    def test_activation_refuses_another_installed_version(self) -> None:
        root = self.new_device()
        state.save_installed(self.paths(root), {"schema": 1, "version": "1.3.0"})
        ctx = self.step_ctx(root, "install")
        res, out = self.run_flow(steps._run_activate, ctx)
        self.assertEqual(res.exit, 3)
        self.assertIn(t("setup.activate_other_version", v="1.3.0", version="1.4.0", tb=TB), out)

    def test_config_makes_env_files_private(self) -> None:
        root, app = self.installed_run()
        dev_vars = app / "apps" / "server" / ".dev.vars"
        dev_vars.chmod(0o644)
        res, out = self.run_flow(steps._run_config, self.step_ctx(app, "continue"))
        self.assertEqual(res.status, "done")
        self.assertEqual(stat.S_IMODE(dev_vars.stat().st_mode), 0o600)

    def test_failed_migration_restores_the_backup(self) -> None:
        root, app = self.installed_run()
        ctx = self.step_ctx(app, "continue")
        new = app / "apps" / "server" / "migrations" / "0004_new.sql"
        new.write_text("CREATE TABLE t4 (id INTEGER);\n", encoding="utf-8")
        newer = app / "apps" / "server" / "migrations" / "0005_newer.sql"
        newer.write_text("CREATE TABLE t5 (id INTEGER);\n", encoding="utf-8")
        self.behave(wrangler={"fail_at": "0005_newer.sql"})
        self.assertFalse(STEP["migrations"].check(ctx))
        before = migrations.applied(self.bot_home)
        res, out = self.run_flow(steps._run_migrations, ctx)
        self.assertEqual((res.status, res.exit), ("failed", 1))
        self.assertEqual(self.stub_calls("backup"), [["make", "stopped", "before-migration"]])
        self.assertIn(["stop_local.sh"], [[c["tool"]] for c in self.calls("stop_local.sh")])  # server stopped first
        self.assertEqual(migrations.applied(self.bot_home), before)  # 0004 rolled back with the D1 folder
        self.assertTrue(list(self.bot_home.glob("d1.failed-*")))
        self.assertIn(t("setup.migrations_failed", log="~/ThomHouse/logs/migrations.log"), out)
        backup = next(self.bot_home.glob("backups/*-before-migration"))
        self.assertIn(t("setup.migrations_restored", folder="~/" + str(backup.relative_to(self.home))), out)

    def test_failed_restore_blocks_until_d1_is_copied_back(self) -> None:
        root, app = self.installed_run()
        ctx = self.step_ctx(app, "continue")
        con = sqlite3.connect(migrations.find_db(self.bot_home))
        con.execute("CREATE TABLE customers (name TEXT)")
        con.execute("INSERT INTO customers VALUES ('khach-1')")
        con.commit()
        con.close()
        (app / "apps" / "server" / "migrations" / "0004_new.sql").write_text("CREATE TABLE t4 (id INTEGER);\n",
                                                                             encoding="utf-8")
        self.behave(wrangler={"fail_at": "0004_new.sql"})
        real_copytree = shutil.copytree
        d1 = self.bot_home / "d1"

        def full_disk(src, dst, *args, **kwargs):
            if os.path.abspath(dst) != str(d1):
                return real_copytree(src, dst, *args, **kwargs)  # the stand-in's backup copy still works
            os.makedirs(dst)
            raise OSError(errno.ENOSPC, "No space left on device")

        with mock.patch("shutil.copytree", full_disk):
            res, out = self.run_flow(steps._run_migrations, ctx)
        self.assertEqual((res.status, res.reason, res.exit), ("failed", "restore_failed", 1))
        mark = steps.restore_needed(self.paths(app))
        backup = next(self.bot_home.glob("backups/*-before-migration"))
        failed = next(self.bot_home.glob("d1.failed-*"))
        self.assertEqual((mark["backup_path"], mark["failed"]), (str(backup), str(failed)))
        self.assertIn(t("setup.migrations_restore_failed", folder="~/" + str(backup.relative_to(self.home)),
                        failed="~/" + str(failed.relative_to(self.home)), cmd=f"{TB} continue"), out)
        self.assertIsNone(migrations.find_db(self.bot_home))  # d1 is empty now
        # Nothing starts the bot on the empty d1 while the mark exists.
        self.behave(wrangler={"fail_at": None})
        starts = len(self.calls("start_local.sh"))
        res, out = self.run_flow(steps._run_start, ctx)
        self.assertEqual((res.status, res.exit), ("failed", 1))
        self.assertIn(t("setup.restore_needed", folder="~/" + str(backup.relative_to(self.home)), tb=TB), out)
        self.assertEqual(len(self.calls("start_local.sh")), starts)
        # `continue`: d1 is copied again from the recorded backup before any migration; the partial copy is set aside.
        backups_before = len(list(self.bot_home.glob("backups/*-before-migration*")))
        res, out = self.run_flow(steps._run_migrations, ctx)
        self.assertEqual(res.status, "done", out)
        self.assertIsNone(steps.restore_needed(self.paths(app)))
        self.assertEqual(len(list(self.bot_home.glob("d1.failed-*"))), 2)
        self.assertEqual(len(list(self.bot_home.glob("backups/*-before-migration*"))), backups_before + 1)
        live = sqlite3.connect(migrations.find_db(self.bot_home))
        self.assertEqual(live.execute("SELECT count(*) FROM customers").fetchone()[0], 1)
        live.close()
        self.assertIn("0004_new.sql", migrations.applied(self.bot_home))

    def test_restore_mark_without_its_backup_refuses(self) -> None:
        root, app = self.installed_run()
        ctx = self.step_ctx(app, "continue")
        steps._set_restore_mark(self.paths(app), {"backup": "x", "backup_path": str(self.tmp / "gone"),
                                                  "failed": str(self.tmp / "f")})
        (app / "apps" / "server" / "migrations" / "0004_new.sql").write_text("CREATE TABLE t4 (id INTEGER);\n",
                                                                             encoding="utf-8")
        before, makes = migrations.applied(self.bot_home), len(self.stub_calls("backup"))
        res, out = self.run_flow(steps._run_migrations, ctx)
        self.assertEqual((res.status, res.reason, res.exit), ("failed", "restore_failed", 1))
        self.assertIn(t("setup.migrations_restore_missing", folder=str(self.tmp / "gone")), out)
        self.assertEqual(migrations.applied(self.bot_home), before)  # 0004 not applied
        self.assertEqual(len(self.stub_calls("backup")), makes)

    def test_start_failure_prints_the_doctor_lines(self) -> None:
        root, app = self.installed_run()
        self.behave(stub_doctor={"status": {"listen_local_only": "fail"}})
        res, out = self.run_flow(steps._run_start, self.step_ctx(app, "continue"))
        self.assertEqual((res.status, res.exit), ("failed", 1))
        self.assertIn(t("setup.check_failed", label="check listen_local_only", detail="stub detail"), out)
        self.assertIn(t("setup.check_fix", fix="fix listen_local_only"), out)
        self.behave(stub_doctor={"status": {}}, start_local={"exit": 1})
        res, out = self.run_flow(steps._run_start, self.step_ctx(app, "continue"))
        self.assertEqual(res.exit, 1)
        self.assertIn(t("setup.start_failed", log="~/ThomHouse/logs/start.log"), out)

    def test_consent_steps_without_a_person_ask_again_later(self) -> None:
        root, app = self.installed_run()
        for step_id in ("autostart", "shortcuts"):
            state.step_set(self.paths(app), step_id, "pending", "later")
        code, out = self.run_steps(app, "continue", "--skip-human", interactive=False)
        self.assertEqual(code, 10, out)
        self.assertEqual(self.summary(app)["autostart"], ("pending", "later"))
        self.assertIn(t("setup.consent_later", tb=TB), out)
        code, out = self.run_steps(app, "continue", "--skip-human", answers="k\nk\n")
        self.assertEqual(self.summary(app)["autostart"], ("declined", None))
        self.assertEqual(self.summary(app)["shortcuts"], ("declined", None))
        code, out = self.run_steps(app, "continue", "--skip-human", answers="")
        self.assertNotIn(t("setup.autostart_ask"), out)  # an answered step is not asked again
        self.assertIn(t("setup.step_line_declined", n=22, title=t("setup.title_autostart")), out)
        self.assertEqual(self.summary(app)["autostart"], ("declined", None))  # k stays k
        self.assertEqual(self.summary(app)["shortcuts"], ("declined", None))

    def test_only_exit_codes(self) -> None:
        root, app = self.installed_run()
        code, out = self.run_steps(app, "install", "--only", "staff_token", interactive=False)
        self.assertEqual(code, 4)
        code, out = self.run_steps(app, "install", "--only", "menu_slides", interactive=False)
        self.assertEqual(code, 1)
        code, out = self.run_steps(app, "install", "--only", "24", interactive=False)
        self.assertEqual(code, 0)
        self.assertIn(t("setup.step_line_done", n=24, title=t("setup.title_menu_check")), out)

    def test_done_step_whose_check_fails_runs_again(self) -> None:
        root, app = self.installed_run()
        (app / "apps" / "server" / "node_modules" / ".bin" / "wrangler").unlink()
        self.assertEqual(self.summary(app)["deps"], ("done", None))
        deps_before = len(self.stub_calls("deps"))
        code, out = self.run_steps(app, "continue", "--skip-human", interactive=False)
        self.assertEqual(code, 10, out)
        self.assertEqual(len(self.stub_calls("deps")), deps_before + 1)
        self.assertTrue((app / "apps" / "server" / "node_modules" / ".bin" / "wrangler").exists())

    def test_dry_run_markers_on_an_installed_device(self) -> None:
        root, app = self.installed_run()
        code, out = self.run_steps(app, "continue", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn(f"  8. [{t('setup.mark_done')}] {t('setup.title_activate')}", out)
        self.assertIn(f" 14. [{t('setup.mark_todo')}] {t('setup.title_claude_login')}", out)
        self.assertIn(f" 18. [{t('setup.mark_todo')}] {t('setup.title_analyze_contacts')}", out)  # skipped: retried
        self.assertIn(f" 22. [{t('setup.mark_done')}] {t('setup.title_autostart')}", out)
        self.assertIn(f"  9. [{t('setup.mark_todo')}] {t('setup.title_config')}", out)
