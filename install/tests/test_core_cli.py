"""install/thomhouse.py: the real entry point under python3 -I from cwd "/" (rev F2), dispatch, refusals, errors and
the lock (16.3.3, 16.4.1, rev F3, F6, F12, F14)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from tests.support import INSTALL_DIR, InstallerTestCase
from thomhouse_installer import state
from thomhouse_installer.text_vi import t

HANDLER_MODULES = {
    "service": ("cmd_start", "cmd_stop", "cmd_restart"),
    "doctor": ("cmd_doctor",),
    "update": ("cmd_update", "cmd_rollback"),
    "backup": ("cmd_backup", "cmd_backups", "cmd_restore"),
    "move": ("cmd_move_out", "cmd_move_in", "cmd_move_back"),
    "human": ("cmd_login_claude", "cmd_add_claude", "cmd_login_zalo", "cmd_sync_history", "cmd_analyze",
              "cmd_labels", "cmd_staff_token"),
    "steps": ("cmd_install", "cmd_continue"),
    "repair": ("cmd_repair",),
    "uninstall": ("cmd_uninstall",),
    "autostart": ("cmd_autostart", "cmd_shortcuts"),
}

FAKE_HANDLER = '''
import json
import os
from thomhouse_installer import state


def _report(name, ctx, args):
    print("HANDLER " + name + " " + json.dumps({
        "command": args.command,
        "held": state.held_by_us(ctx.paths),
        "owner": os.environ.get("THOMHOUSE_LOCK_OWNER"),
        "holder": state.lock_holder(ctx.paths),
        "pid": os.getpid(),
    }))
    return 0
'''


def _plant_handlers(root: Path, overrides: dict[str, str] | None = None) -> None:
    """Write stand-in handler modules into the copied release (never into the real install/)."""
    pkg = root / "install" / "thomhouse_installer"
    for module, funcs in HANDLER_MODULES.items():
        body = FAKE_HANDLER
        for func in funcs:
            body += f"\n\ndef {func}(ctx, args):\n    return _report({func!r}, ctx, args)\n"
        body += (overrides or {}).get(module, "")
        (pkg / f"{module}.py").write_text(body, encoding="utf-8")


def _remove_module(root: Path, module: str) -> None:
    f = root / "install" / "thomhouse_installer" / f"{module}.py"
    if f.exists():
        f.unlink()


class CliTest(InstallerTestCase):
    def test_version_with_isolated_python_from_root(self) -> None:
        self.install_release("1.4.0")
        res = self.run_cli(self.app_home / "app", "--version", cwd="/")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "1.4.0")
        checkout = self.make_checkout()
        res = self.run_cli(checkout, "--version", cwd="/")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "checkout")

    def test_version_imports_no_installer_module(self) -> None:
        self.install_release("1.4.0")
        script = self.app_home / "app" / "install" / "thomhouse.py"
        code = textwrap.dedent("""
            import runpy, sys
            sys.argv = [sys.argv[1], "--version"]
            try:
                runpy.run_path(sys.argv[0], run_name="__main__")
            except SystemExit:
                pass
            print("LOADED", sorted(m for m in sys.modules if m.startswith("thomhouse_installer")))
        """)
        res = subprocess.run([sys.executable, "-I", "-c", code, str(script)], cwd="/", env=dict(self.env),
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1.4.0", res.stdout)
        self.assertIn("LOADED []", res.stdout)

    def test_help_and_bad_arguments(self) -> None:
        self.install_release()
        res = self.run_cli(None, "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("doctor", res.stdout)
        res = self.run_cli(None, "frobnicate")
        self.assertEqual(res.returncode, 2)
        res = self.run_cli(None, "update")  # FILE missing
        self.assertEqual(res.returncode, 2)
        res = self.run_cli(None)
        self.assertEqual(res.returncode, 2)

    def test_missing_module_exits_2_with_not_built_line(self) -> None:
        root = self.install_release()
        _remove_module(root, "doctor")
        res = self.run_cli(None, "doctor", "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), t("core.not_built", part="doctor", command="doctor"))

    def test_checkout_mode_refuses_install_and_accepts_move_out(self) -> None:
        root = self.make_checkout()
        _plant_handlers(root)
        res = self.run_cli(root, "install")
        self.assertEqual(res.returncode, 3)
        self.assertIn(t("core.checkout_only"), res.stdout)
        res = self.run_cli(root, "move-out", "--to", str(self.tmp / "out"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("HANDLER cmd_move_out", res.stdout)
        for command in ("start", "login-zalo", "repair", "continue", "staff-token"):
            res = self.run_cli(root, command)
            self.assertEqual(res.returncode, 3, command)

    def test_installer_error_gives_its_code_and_text(self) -> None:
        root = self.install_release()
        _plant_handlers(root, {"backup": textwrap.dedent('''
            from thomhouse_installer.context import InstallerError


            class Refused(InstallerError):
                code = 4
                key = "core.interrupted"


            def cmd_backups(ctx, args):
                raise Refused()
            ''')})
        res = self.run_cli(None, "backups")
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), t("core.interrupted"))

    def test_exit_with_formatted_text_and_silent_exit(self) -> None:
        root = self.install_release()
        _plant_handlers(root, {"backup": textwrap.dedent('''
            from thomhouse_installer.context import Exit


            def cmd_backups(ctx, args):
                raise Exit(3, "core.whitespace_path", folder="/x y")


            def cmd_backup(ctx, args):
                raise Exit(7)
            ''')})
        res = self.run_cli(None, "backups")
        self.assertEqual(res.returncode, 3)
        self.assertEqual(res.stdout.strip(), t("core.whitespace_path", folder="/x y"))
        res = self.run_cli(None, "backup")
        self.assertEqual(res.returncode, 7)
        self.assertEqual(res.stdout.strip(), "")

    def test_other_exception_gives_exit_2_and_type_name_only(self) -> None:
        root = self.install_release()
        _plant_handlers(root, {"backup": textwrap.dedent('''
            def cmd_backups(ctx, args):
                raise RuntimeError("secret-detail-4711")
            ''')})
        res = self.run_cli(None, "backups")
        self.assertEqual(res.returncode, 2)
        self.assertIn("RuntimeError", res.stdout)
        self.assertNotIn("secret-detail-4711", res.stdout + res.stderr)
        log = (self.app_home / "logs" / "install.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError", log)

    def test_dispatcher_refusals_when_moved_out(self) -> None:
        root = self.install_release()
        _plant_handlers(root)
        p = self.paths()
        state.set_moved_out(p, {"image_name": "thomhouse-chuyen-may-x.dmg", "image_sha256": "0" * 64})
        refused = {
            "start": [],
            "login-zalo": [],
            "restore": ["20261112-000000-manual"],
            "update": [str(self.tmp / "thomhouse-1.5.0.command")],
        }
        for command, extra in refused.items():
            res = self.run_cli(None, command, *extra)
            self.assertEqual(res.returncode, 3, command)
            self.assertIn(t("core.moved_out", tb="~/ThomHouse/bin/thomhouse"), res.stdout, command)
            self.assertNotIn("HANDLER", res.stdout)
        for command, func in (("doctor", "cmd_doctor"), ("stop", "cmd_stop"), ("move-back", "cmd_move_back")):
            res = self.run_cli(None, command)
            self.assertEqual(res.returncode, 0, command + res.stdout + res.stderr)
            self.assertIn(f"HANDLER {func}", res.stdout)

    def test_dispatcher_refusals_while_update_open(self) -> None:
        root = self.install_release()
        _plant_handlers(root)
        p = self.paths()
        journal = {"from": "1.4.0", "to": "1.5.0", "file": "/Volumes/USB/thomhouse-1.5.0.command",
                   "phases": {"U1": "done", "U7": "running"}, "state": "running"}
        state.update_set(p, journal)
        for command in ("repair", "continue", "restart"):
            res = self.run_cli(None, command)
            self.assertEqual(res.returncode, 3, command)
            self.assertIn(t("core.update_open", file="/Volumes/USB/thomhouse-1.5.0.command"), res.stdout)
        for command, extra, func in (("update", ["/Volumes/USB/thomhouse-1.5.0.command"], "cmd_update"),
                                     ("rollback", [], "cmd_rollback"), ("doctor", [], "cmd_doctor")):
            res = self.run_cli(None, command, *extra)
            self.assertEqual(res.returncode, 0, command + res.stdout + res.stderr)
            self.assertIn(f"HANDLER {func}", res.stdout)
        # Before U7 nothing live changed: commands run (rev check).
        journal["phases"] = {"U1": "done", "U3": "running"}
        state.update_set(p, journal)
        res = self.run_cli(None, "restart")
        self.assertEqual(res.returncode, 0)
        self.assertIn("HANDLER cmd_restart", res.stdout)

    def test_changing_command_holds_install_lock(self) -> None:
        root = self.install_release()
        _plant_handlers(root)
        res = self.run_cli(None, "restart")
        self.assertEqual(res.returncode, 0, res.stderr)
        info = json.loads(res.stdout.split("HANDLER cmd_restart ", 1)[1])
        self.assertTrue(info["held"])
        self.assertEqual(info["owner"], str(info["pid"]))
        self.assertEqual(info["holder"], info["pid"])
        # Released afterwards.
        self.assertIsNone(state.lock_holder(self.paths()))
        # doctor and every --dry-run take no lock.
        for args, func in ((["doctor"], "cmd_doctor"), (["install", "--dry-run"], "cmd_install"),
                           (["staff-token"], "cmd_staff_token"), (["backups"], "cmd_backups")):
            res = self.run_cli(None, *args)
            info = json.loads(res.stdout.split(f"HANDLER {func} ", 1)[1])
            self.assertFalse(info["held"], args)
            self.assertIsNone(info["owner"], args)

    def test_locked_by_another_process(self) -> None:
        root = self.install_release()
        _plant_handlers(root)
        with state.InstallLock(self.paths()):
            res = self.run_cli(None, "restart")
        self.assertEqual(res.returncode, 3)
        self.assertEqual(res.stdout.strip(), t("core.locked"))
        self.assertNotIn("HANDLER", res.stdout)

    def test_bootstrap_lock_removed_only_for_own_pid(self) -> None:
        root = self.install_release()
        _plant_handlers(root)
        lock_dir = self.app_home / ".bootstrap.lock.d"
        script = self.tmp / "chain.sh"
        script.write_text(textwrap.dedent(f"""\
            #!/bin/bash
            mkdir -p "{lock_dir}"
            echo $$ > "{lock_dir}/pid"
            exec "{sys.executable}" -I "{root}/install/thomhouse.py" restart
            """), encoding="utf-8")
        res = subprocess.run(["/bin/bash", str(script)], env=dict(self.env), cwd="/", capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(lock_dir.exists())
        # A lock folder of another PID stays.
        lock_dir.mkdir()
        (lock_dir / "pid").write_text("1\n", encoding="ascii")
        res = self.run_cli(None, "restart")
        self.assertEqual(res.returncode, 0)
        self.assertTrue((lock_dir / "pid").exists())

    def test_namespace_common_attributes(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_thomhouse_entry", INSTALL_DIR / "thomhouse.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.parse_args(["stop"])
        for name in ("yes", "dry_run", "quiet", "offline", "json"):
            self.assertIs(getattr(args, name), False)
        self.assertEqual(args.command, "stop")
        args = module.parse_args(["doctor", "--json", "--only", "macos,cpu", "--strict"])
        self.assertEqual(args.only, {"macos", "cpu"})
        self.assertTrue(args.json and args.strict)
        args = module.parse_args(["backup", "--stopped", "--reason", "before-migration", "--if-pending-migrations",
                                  "--quiet"])
        self.assertEqual((args.mode, args.reason, args.if_pending_migrations, args.quiet),
                         ("stopped", "before-migration", True, True))
        args = module.parse_args(["install", "--from-bootstrap", "--consented", "python,claude_code",
                                  "--release-file", "/x/thomhouse-1.4.0.command", "--skip-human"])
        self.assertEqual(args.consented, ["python", "claude_code"])
        self.assertEqual(args.release_file, Path("/x/thomhouse-1.4.0.command"))
        self.assertTrue(args.from_bootstrap and args.skip_human)
        args = module.parse_args(["add-claude", "acc2"])
        self.assertEqual((args.label, args.priority), ("acc2", 100))
        args = module.parse_args(["login-claude"])
        self.assertIsNone(args.label)
        args = module.parse_args(["autostart", "on"])
        self.assertEqual(args.state, "on")
        args = module.parse_args(["move-out", "--to", "/tmp/x"])
        self.assertEqual(args.to, Path("/tmp/x"))
        self.assertEqual(set(module.DISPATCH), {
            "install", "continue", "start", "stop", "restart", "doctor", "update", "rollback", "backup", "backups",
            "restore", "move-out", "move-in", "move-back", "uninstall", "login-claude", "add-claude", "login-zalo",
            "sync-history", "analyze", "labels", "staff-token", "autostart", "shortcuts", "repair"})
        no_lock = {c for c, row in module.DISPATCH.items() if not row[2]}
        self.assertEqual(no_lock, {"doctor", "backup", "backups", "staff-token"})
        checkout = {c for c, row in module.DISPATCH.items() if row[3]}
        self.assertEqual(checkout, {"doctor", "backup", "backups", "restore", "move-out", "move-back"})
        self.assertNotIn(os.environ.get("THOMHOUSE_LOCK_OWNER"), (str(os.getpid()),))
