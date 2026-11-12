"""update.py: phase order, failures before and after the stop, the U10 and U11 rollbacks with d1 restored as it was,
the unfinished rollback finished by a later `update FILE`, the health gate, refusals, the start hook under the
update's lock, the launcher, interrupted updates and `rollback` (16.8.1, rev F3, F10, F13, F14, rev check).

WP2 (`release`, `runtimes`, `deps`) and WP4 (`doctor`) are the stand-ins of tests/fakes_ops/stub_modules, so failures
can be injected at the package boundary; the stack, the start and stop scripts (stubs of the fake release tree),
backups, migrations and the journal are real. tests/test_integration_flows.py runs update, the same-version case and
rollback with the real modules and signed release files.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest import mock

from tests.fakes_ops.opscase import OpsTestCase, PowerCut
from thomhouse_installer import backup, context, service, state, update
from thomhouse_installer.text_vi import t

ALL = list(update.PHASES)


def _args(file: Path, **attrs: object) -> argparse.Namespace:
    ns = {"command": "update", "file": Path(file), "menu": None, "yes": False, "dry_run": False, "quiet": False,
          "offline": False, "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


def _rb_args(**attrs: object) -> argparse.Namespace:
    ns = {"command": "rollback", "yes": False, "dry_run": False, "quiet": False, "offline": False, "json": False}
    ns.update(attrs)
    return argparse.Namespace(**ns)


def cut_at(phase: str):
    def hook(name: str) -> None:
        if name == phase:
            raise PowerCut(name)
    return hook


class UpdateBase(OpsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.use_stubs()
        self.old_root = self.installed()
        self.old_real = os.path.realpath(self.app_home / "releases" / "1.4.0")

    def update(self, file: Path, **ctx_attrs: object) -> int:
        attrs = {"yes": True}
        attrs.update(ctx_attrs)
        return self.quiet(update.cmd_update, self.ctx(**attrs), _args(file))

    def new_release(self, version: str = "1.5.0", **kw) -> Path:
        return self.release_file(version, self.release_tree(version, **kw))

    def started_from(self) -> list[str]:
        return [c["cwd"] for c in self.start_calls()]


class UpdateTest(UpdateBase):
    def test_phase_order_and_success(self) -> None:
        (self.app_home / "shared" / "menu-slides" / ("0" * 16)).mkdir(parents=True)
        f = self.new_release(migrations=("0004_new.sql",))
        phases: list[str] = []
        with mock.patch.object(update, "_after_phase", phases.append):
            code = self.update(f)
        self.assertEqual(code, 0, self.out)
        self.assertEqual(phases, ALL)
        self.assertIn(t("ops.update_done", version="1.5.0"), self.out)
        self.assertEqual(self.app_target(), "releases/1.5.0")
        inst = state.load_installed(self.paths())
        self.assertEqual((inst["version"], inst["previous_version"]), ("1.5.0", "1.4.0"))
        self.assertTrue(inst["backup_before_update"].endswith("-before-update-1.5.0"))
        self.assertEqual(inst["release_id"], "NEW-1.5.0")
        self.assertEqual(inst["migrations_applied"][-1], "0004_new.sql")
        self.assertEqual(self.applied()[-1], "0004_new.sql")
        j = self.journal()
        self.assertEqual(j["state"], "done")
        self.assertEqual(j["phases"], {p: "done" for p in ALL})
        fns = [c["fn"] for c in self.stub_calls() if c["fn"] != "runtimes.plan"]
        self.assertEqual(fns, ["release.verify_file", "release.unpack", "release.copy_to_cache", "deps.install",
                               "release.link_menu", "release.switch_app", "release.write_launcher",
                               "doctor.run_checks", "release.prune"])
        self.assertEqual(self.stub_calls("doctor.run_checks")[0]["only"],
                         ["listen_local_only", "openmausbot_options"])
        # The old release was stopped, then the new one started.
        new_real = os.path.realpath(self.app_home / "releases" / "1.5.0")
        self.assertEqual(self.started_from(), [self.old_real, new_real])
        self.assertEqual([c["cwd"] for c in self.stop_calls()], [self.old_real])
        self.assertEqual(self.history()[-1]["event"], "update")
        self.assertEqual(self.history()[-1]["result"], "ok")
        self.assertTrue({"server", "cron", "runner", "bridge", "console"} <= self.alive_services())
        # U6 copied the env files (copies, mode 0600).
        env = self.app_home / "releases" / "1.5.0" / "apps" / "server" / ".dev.vars"
        self.assertFalse(env.is_symlink())
        self.assertEqual(oct(env.stat().st_mode & 0o777), "0o600")
        self.assertEqual(env.read_text(encoding="utf-8"),
                         (self.app_home / "releases" / "1.4.0" / "apps" / "server" / ".dev.vars").read_text(
                             encoding="utf-8"))
        log = (self.app_home / "logs" / "update.log").read_text(encoding="utf-8")
        self.assertIn('"phase_done"', log)

    def test_dependency_failure_never_stops_the_stack(self) -> None:
        self.behave(stubs={"fail_deps": True})
        code = self.update(self.new_release())
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.stop_calls(), [])
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(self.journal()["state"], "failed")
        self.assertIsNone(state.update_open(self.paths()))
        self.assertFalse(list((self.app_home / "releases" / "1.5.0").rglob("node_modules")))
        self.assertIn("server", self.alive_services())
        self.assertIn(t("ops.update_failed_before_stop", title=t("ops.phase_u4"), old="1.4.0",
                        log="~/ThomHouse/logs/update.log"), self.out)

    def test_migration_failure_restores_d1_and_old_release(self) -> None:
        before = self.dumps()
        self.behave(wrangler={"fail_at": "0005_more.sql"})
        code = self.update(self.new_release(migrations=("0004_new.sql", "0005_more.sql")))
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.dumps(), before)  # the same iterdump() for every database (rev F13)
        self.assertTrue(list(self.bot_home.glob("d1.failed-*")))
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(self.stub_calls("release.write_launcher")[-1]["version"], "1.4.0")
        j = self.journal()
        self.assertEqual((j["state"], j["phases"]["U10"]), ("rolled_back", "rollback"))
        self.assertEqual(self.started_from()[-1], self.old_real)
        self.assertIn("server", self.alive_services())
        self.assertIn(t("ops.update_rolled_back", title=t("ops.phase_u10"), old="1.4.0",
                        log="~/ThomHouse/logs/update.log"), self.out)
        self.assertEqual(self.history()[-1]["result"], "rolled_back")
        self.assertEqual(state.load_installed(self.paths())["version"], "1.4.0")

    def test_d1_copy_failure_then_update_finishes_the_rollback(self) -> None:
        before = self.dumps()
        self.behave(wrangler={"fail_at": "0005_more.sql"})
        f = self.new_release(migrations=("0004_new.sql", "0005_more.sql"))
        starts = len(self.start_calls())
        with mock.patch.object(backup, "copy_d1_back", side_effect=OSError(28, "No space left on device")):
            code = self.update(f)
        self.assertEqual(code, 1, self.out)
        j = self.journal()
        self.assertEqual((j["state"], j["phases"]["U10"]), ("running", "rollback"))
        self.assertIn(j["backup"], self.out)  # the backup folder is named
        self.assertIn("d1.failed-", self.out)
        self.assertEqual(len(self.start_calls()), starts)  # nothing started
        res = self.run_cli(None, "start")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn(t("core.update_open", file=str(f)), res.stdout)
        applies = len([c for c in self.calls("wrangler") if c["argv"][:3] == ["d1", "migrations", "apply"]])
        code = self.update(f)
        self.assertEqual(code, 1, self.out)
        self.assertEqual(len([c for c in self.calls("wrangler") if c["argv"][:3] == ["d1", "migrations", "apply"]]),
                         applies)
        self.assertEqual(self.dumps(), before)
        self.assertEqual(self.journal()["state"], "rolled_back")
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(self.started_from()[-1], self.old_real)

    def test_new_runtimes_and_u4_uses_the_new_pnpm(self) -> None:
        f = self.new_release(node="24.20.0", pnpm="10.33.0")
        code = self.update(f)
        self.assertEqual(code, 0, self.out)
        self.assertIn(t("ops.update_runtime_ask"), self.out)
        installs = self.stub_calls("runtimes.install")
        self.assertEqual([c["name"] for c in installs], ["node", "pnpm"])
        node_bin = str(self.app_home / "runtime" / "node-24.20.0" / "bin")
        self.assertEqual(installs[1]["node_bin"], node_bin)
        deps = self.stub_calls("deps.install")[0]
        self.assertEqual(deps["node_bin"], node_bin)
        self.assertEqual(deps["pnpm_bin"],
                         str(self.app_home / "runtime" / "pnpm-10.33.0" / "node_modules" / ".bin" / "pnpm"))
        switched = [(c["name"], c["version"]) for c in self.stub_calls("runtimes.switch")]
        self.assertEqual(switched, [("node", "24.20.0"), ("pnpm", "10.33.0")])
        inst = state.load_installed(self.paths())
        self.assertEqual((inst["runtimes"]["node"], inst["previous_runtimes"]["node"]), ("24.20.0", "24.19.0"))

    def test_declined_runtime_consent_changes_nothing(self) -> None:
        f = self.new_release(node="24.20.0")
        self.answer("c\nk\n")
        code = self.quiet(update.cmd_update, self.ctx(interactive=True), _args(f))
        self.assertEqual(code, 4, self.out)
        self.assertEqual(self.stub_calls("runtimes.install"), [])
        self.assertEqual(self.stop_calls(), [])
        self.assertEqual(self.journal()["state"], "failed")

    def test_start_failure_rolls_back(self) -> None:
        before = self.dumps()
        code = self.update(self.new_release(migrations=("0004_new.sql",), start_fails=True))
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.dumps(), before)
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(self.journal()["state"], "rolled_back")
        self.assertEqual(len(self.stop_calls()), 2)  # U7, then after the failed start
        self.assertEqual(self.started_from()[-1], self.old_real)
        self.assertIn(t("ops.update_rolled_back", title=t("ops.phase_u11"), old="1.4.0",
                        log="~/ThomHouse/logs/update.log"), self.out)

    def test_health_gate_failure_does_not_roll_back(self) -> None:
        self.behave(stubs={"checks": {"listen_local_only": "fail"}})
        code = self.update(self.new_release(migrations=("0004_new.sql",)))
        self.assertEqual(code, 1, self.out)
        self.assertEqual(self.app_target(), "releases/1.5.0")
        inst = state.load_installed(self.paths())
        self.assertEqual((inst["version"], inst["previous_version"]), ("1.5.0", "1.4.0"))
        self.assertEqual(self.history()[-1]["result"], "failed")
        self.assertEqual(self.journal()["state"], "done")
        self.assertIn(t("ops.update_health_failed", version="1.5.0", tb="~/ThomHouse/bin/thomhouse"), self.out)
        self.assertIn("[LỖI] stub listen_local_only", self.out)

    def test_downgrade_and_bad_signature_refused(self) -> None:
        code = self.update(self.release_file("1.3.0", None))
        self.assertEqual(code, 3, self.out)
        self.assertIn(t("ops.update_older", new="1.3.0", current="1.4.0", tb="~/ThomHouse/bin/thomhouse"), self.out)
        with self.assertRaises(context.InstallerError) as caught:
            self.update(self.release_file("1.5.0", None, bad="signature"))
        self.assertEqual((caught.exception.code, caught.exception.key), (3, "release.signature"))
        self.assertEqual(self.stub_calls("release.unpack"), [])

    def test_update_start_runs_real_hook_under_the_lock(self) -> None:
        f = self.new_release(migrations=("0004_new.sql",))
        self.behave(start_local={"hook": True})
        with mock.patch.object(update.migrations, "apply", return_value=0):  # 0004 stays pending for the hook
            with state.InstallLock(self.paths()):
                code = self.update(f)
        self.assertEqual(code, 0, self.out)
        reasons = [b.reason for b in state.list_backups(self.paths())]
        self.assertIn("before-update-1.5.0", reasons)
        self.assertIn("before-migration", reasons)  # the real hook, run by the new release's start
        self.assertEqual(self.applied()[-1], "0004_new.sql")

    def test_update_and_rollback_rewrite_the_launcher(self) -> None:
        code = self.update(self.new_release(migrations=("0004_new.sql",)))
        self.assertEqual(code, 0, self.out)
        launcher = self.app_home / "bin" / "thomhouse"
        self.assertIn("release 1.5.0", launcher.read_text(encoding="utf-8"))
        self.assertEqual(self.stub_calls("release.write_launcher")[-1]["code_root"],
                         str(self.app_home / "releases" / "1.5.0"))
        # 0004 is applied and 1.4.0 lacks it: rollback needs the typed word.
        code = self.quiet(update.cmd_rollback, self.ctx(), _rb_args())
        self.assertEqual(code, 4, self.out)
        self.assertEqual(self.app_target(), "releases/1.5.0")
        self.answer("khoi phuc\n")
        code = self.quiet(update.cmd_rollback, self.ctx(interactive=True), _rb_args())
        self.assertEqual(code, 0, self.out)
        self.assertIn("release 1.4.0", launcher.read_text(encoding="utf-8"))
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(self.applied(), ["0001_init.sql", "0002_outbox.sql", "0003_profiles.sql"])
        inst = state.load_installed(self.paths())
        self.assertEqual((inst["version"], inst["previous_version"], inst["release_id"]), ("1.4.0", None, "OLD-ID"))
        self.assertEqual(self.history()[-1]["event"], "rollback")
        self.assertEqual(self.started_from()[-1], self.old_real)
        self.assertEqual(self.quiet(update.cmd_rollback, self.ctx(), _rb_args()), 3)
        self.assertIn(t("ops.rollback_none"), self.out)

    def test_rollback_without_new_migrations_needs_no_word(self) -> None:
        self.assertEqual(self.update(self.new_release()), 0, self.out)
        res = self.run_cli(None, "rollback", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.app_target(), "releases/1.5.0")
        code = self.quiet(update.cmd_rollback, self.ctx(), _rb_args())
        self.assertEqual(code, 0, self.out)
        self.assertEqual(self.app_target(), "releases/1.4.0")

    def test_interrupted_update_blocks_start_and_resumes_at_u10(self) -> None:
        f = self.new_release(migrations=("0004_new.sql",))
        with mock.patch.object(update, "_after_phase", cut_at("U9")):
            with self.assertRaises(PowerCut):
                self.update(f)
        self.assertIsNotNone(state.update_open(self.paths()))
        for command in ("start", "continue"):
            res = self.run_cli(None, command)
            self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
            self.assertIn(t("core.update_open", file=str(f)), res.stdout)
        with self.assertRaises(context.Exit) as caught:  # another file while the journal is open
            self.update(self.release_file("1.6.0", None))
        self.assertEqual((caught.exception.code, caught.exception.key), (3, "core.update_open"))
        phases: list[str] = []
        with mock.patch.object(update, "_after_phase", phases.append):
            code = self.update(f)
        self.assertEqual(code, 0, self.out)
        self.assertEqual(phases, ["U10", "U11", "U12", "U13"])
        self.assertEqual(state.load_installed(self.paths())["version"], "1.5.0")

    def test_power_cut_in_u3_leaves_start_working(self) -> None:
        f = self.new_release(node="24.20.0")
        stub = sys.modules["thomhouse_installer.runtimes"]
        with mock.patch.object(stub, "install", side_effect=PowerCut("U3")):
            with self.assertRaises(PowerCut):
                self.update(f)
        self.assertEqual(self.journal()["phases"]["U3"], "running")
        self.assertIsNone(state.update_open(self.paths()))
        code = self.quiet(service.cmd_start, self.ctx(), argparse.Namespace(quiet=True))
        self.assertEqual(code, 0, self.out)
        phases: list[str] = []
        with mock.patch.object(update, "_after_phase", phases.append):
            code = self.update(f)
        self.assertEqual(code, 0, self.out)
        self.assertEqual(phases, ALL)

    def test_k_after_a_power_cut_in_u8_starts_the_old_release(self) -> None:
        f = self.new_release(migrations=("0004_new.sql",))
        with mock.patch.object(update, "_after_phase", cut_at("U8")):
            with self.assertRaises(PowerCut):
                self.update(f)
        self.assertNotIn("server", self.alive_services())
        code = self.update(f, yes=False, dry_run=True)  # a dry run changes nothing, the journal stays open
        self.assertEqual(code, 0, self.out)
        self.assertIsNotNone(state.update_open(self.paths()))
        starts = len(self.start_calls())
        code = self.update(f, yes=False)  # nobody types: the answer is k
        self.assertEqual(code, 4, self.out)
        self.assertIn(t("ops.update_declined_unfinished"), self.out)
        self.assertNotIn(t("ops.update_declined"), self.out)
        self.assertIn(t("ops.update_unfinished_closed", old="1.4.0"), self.out)
        self.assertIsNone(state.update_open(self.paths()))
        self.assertEqual(self.journal()["state"], "rolled_back")
        self.assertEqual(len(self.start_calls()), starts + 1)
        self.assertEqual(self.started_from()[-1], self.old_real)
        self.assertTrue({"server", "runner", "console"} <= self.alive_services())
        self.assertEqual(self.app_target(), "releases/1.4.0")
        self.assertEqual(state.load_installed(self.paths())["version"], "1.4.0")
        res = self.run_cli(None, "start")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        code = self.update(f)  # a later `update FILE` runs from U1
        self.assertEqual(code, 0, self.out)
        self.assertEqual(state.load_installed(self.paths())["version"], "1.5.0")

    def test_file_that_fails_after_a_power_cut_in_u7_starts_the_old_release(self) -> None:
        f = self.new_release()
        with mock.patch.object(update, "_after_phase", cut_at("U7")):
            with self.assertRaises(PowerCut):
                self.update(f)
        self.assertIsNotNone(state.update_open(self.paths()))
        stub = sys.modules["thomhouse_installer.release"]
        with mock.patch.object(stub, "verify_file", side_effect=context.InstallerError("core.failed", 1)):
            with self.assertRaises(context.InstallerError):
                self.update(f)
        self.assertIsNone(state.update_open(self.paths()))
        self.assertIn(t("ops.update_unfinished_closed", old="1.4.0"), self.out)
        self.assertTrue({"server", "runner", "console"} <= self.alive_services())

    def test_dry_run_changes_nothing(self) -> None:
        f = self.new_release(migrations=("0004_new.sql",))
        code = self.update(f, dry_run=True)
        self.assertEqual(code, 0, self.out)
        self.assertIn(t("ops.update_dry_run", old="1.4.0", new="1.5.0"), self.out)
        self.assertIsNone(self.journal())
        self.assertEqual(self.stub_calls("release.unpack"), [])
        self.assertEqual(self.stop_calls(), [])


class UpdatePowerCutTest(UpdateBase):
    """A power cut after each phase: the next `update FILE` resumes (from U9 on) or starts again at U1 (before),
    and `start` is refused exactly while the journal is open (U7 or later started)."""


def _power_cut_test(phase: str):
    def test(self: UpdatePowerCutTest) -> None:
        f = self.new_release(migrations=("0004_new.sql",))
        with mock.patch.object(update, "_after_phase", cut_at(phase)):
            with self.assertRaises(PowerCut):
                self.update(f)
        late = ALL.index(phase) >= ALL.index("U7")
        self.assertEqual(state.update_open(self.paths()) is not None, late, phase)
        code = self.update(f)
        self.assertEqual(code, 0, self.out)
        self.assertEqual(state.load_installed(self.paths())["version"], "1.5.0")
        self.assertEqual(self.app_target(), "releases/1.5.0")
        self.assertEqual(self.journal()["state"], "done")
        self.assertEqual(self.applied()[-1], "0004_new.sql")
        self.assertTrue({"server", "runner", "console"} <= self.alive_services())
    test.__doc__ = f"power cut right after {phase}"
    return test


for _phase in ALL[:-1]:
    setattr(UpdatePowerCutTest, f"test_power_cut_after_{_phase.lower()}", _power_cut_test(_phase))
