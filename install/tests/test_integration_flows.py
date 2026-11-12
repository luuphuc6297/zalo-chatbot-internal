"""Integration of the five packages with no stand-in: signed test releases built by the real make_release.py from the
kit project (the fake tree with the real install/, including the real steps.py), run with bash through the header,
bootstrap.sh and the real CLI, then the rendered launcher `~/ThomHouse/bin/thomhouse` for every later command. Only the
fakes of install/tests/fake_bin stand for the outside world (16.10).

- `test_header_install_then_doctor`: the first install through the `.command` reaches exit 10 with the human steps
  postponed, and the launcher's `doctor --json` then reports the 48 checks with none `fail` (WP2 + WP3 + WP4 + WP5).
- `test_same_version_without_steps`: `update` with the installed version prints `ops.update_same`, exits 0 and
  never imports steps (16.4.1, rev check).
- `test_update_with_new_python_and_migration_then_rollback`: `update` to a release whose Python pin and migrations
  differ installs the new Python, switches it, applies the migration and leaves a launcher that still starts the CLI;
  `rollback` asks the typed words (the old release cannot read the new database), restores d1 from the U8 backup and
  switches Python back (16.8.1, rev F10, F13).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.fakes_release import kit
from thomhouse_installer import migrations, state
from thomhouse_installer.text_vi import t

NEW_MIGRATION = "0004_integration.sql"
NEW_PYTHON = "3.14.7"
FIRST_INSTALL_ANSWERS = "c\nc\ndong y\nc\nk\n"  # release id, runtime plan, licence notice, autostart, shortcuts


class IntegrationCase(kit.ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.launcher = self.app_home / "bin" / "thomhouse"

    def first_install(self) -> Path:
        command = self.release_file(menu=True, real_steps=True)
        res = self.run_header(command, "--skip-human", answers=FIRST_INSTALL_ANSWERS, timeout=300)
        self.assertEqual(res.returncode, 10, res.stdout)
        return command

    def tb(self, *args: str, answers: str | None = None) -> subprocess.CompletedProcess:
        cmd = ["/bin/bash", str(self.launcher), *args]
        if answers is not None:
            return kit.run_tty(cmd, env=dict(self.env), answers=answers, timeout=300)
        return subprocess.run(cmd, cwd="/", env=dict(self.env), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=300)

    def doctor_json(self) -> tuple[int, dict]:
        res = self.tb("doctor", "--json")
        return res.returncode, json.loads(res.stdout)

    def python_link(self) -> str:
        return os.readlink(self.app_home / "runtime" / "python")


class HeaderInstallTest(IntegrationCase):
    def test_header_install_then_doctor(self) -> None:
        command = self.first_install()
        steps = json.loads((self.app_home / "install-steps.json").read_text(encoding="utf-8"))["steps"]
        for step_id in ("claude_login", "staff_token"):
            self.assertEqual((steps[step_id]["status"], steps[step_id].get("reason")), ("pending", "later"))
        self.assertEqual(steps["final_check"]["status"], "done")
        self.assertEqual(os.readlink(self.app_home / "app"), "releases/1.4.0")
        code, data = self.doctor_json()
        self.assertEqual(code, 0, data)
        self.assertEqual(len(data["checks"]), 48)
        self.assertEqual([c["id"] for c in data["checks"] if c["status"] == "fail"], [])
        # The same file again is refused on an installed device and names update (16.4.1).
        res = self.run_header(command)
        self.assertEqual(res.returncode, 3, res.stdout)
        self.assertIn(t("release.already_installed", file=str(command)), res.stdout)


class SameVersionTest(IntegrationCase):
    def test_same_version_without_steps(self) -> None:
        """`update` with the installed version prints ops.update_same and exits 0 without importing steps (rev
        check): the installed steps.py is replaced by one that leaves a mark when imported."""
        command = self.first_install()
        steps_py = self.app_home / "releases" / "1.4.0" / "install" / "thomhouse_installer" / "steps.py"
        steps_py.chmod(0o644)
        steps_py.write_text("import os\nopen(os.path.join(os.environ['THOMHOUSE_TEST_DIR'], 'steps-imported'), "
                            "'w').close()\n", encoding="utf-8")
        res = self.tb("update", str(command))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), t("ops.update_same", version="1.4.0"))
        self.assertFalse((self.tmp / "steps-imported").exists())
        self.assertIsNone(state.update_get(self.paths()))


class UpdateRollbackTest(IntegrationCase):
    def test_update_with_new_python_and_migration_then_rollback(self) -> None:
        self.first_install()
        before = sorted(migrations.applied(self.bot_home) or [])
        launcher_before = self.launcher.read_text(encoding="utf-8")
        new_file = self.variant_file("1.5.0", migration=NEW_MIGRATION, python=NEW_PYTHON)
        res = self.tb("update", str(new_file), answers="c\nc\n")  # update, then the new Python
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(self.python_link(), f"python-{NEW_PYTHON}-aarch64-apple-darwin")
        self.assertEqual(os.readlink(self.app_home / "app"), "releases/1.5.0")
        self.assertEqual(sorted(migrations.applied(self.bot_home) or []), sorted(before + [NEW_MIGRATION]))
        inst = json.loads((self.app_home / "installed.json").read_text(encoding="utf-8"))
        self.assertEqual((inst["version"], inst["previous_version"]), ("1.5.0", "1.4.0"))
        self.assertEqual(state.update_get(self.paths())["state"], "done")
        # The launcher holds no version: after PY_VERSION changed it still starts the CLI (rev F10).
        self.assertEqual(self.launcher.read_text(encoding="utf-8"), launcher_before)
        code, data = self.doctor_json()
        self.assertEqual(code, 0, data)
        python = next(c for c in data["checks"] if c["id"] == "python")
        self.assertEqual((python["status"], python["detail"]), ("pass", NEW_PYTHON))
        res = self.tb("rollback", answers="khoi phuc\n")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(os.readlink(self.app_home / "app"), "releases/1.4.0")
        self.assertEqual(self.python_link(), f"python-{kit.PY_VERSION}-aarch64-apple-darwin")
        self.assertEqual(sorted(migrations.applied(self.bot_home) or []), before)
        res = self.tb("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn(f"[ĐẠT] Python: {kit.PY_VERSION}", res.stdout)


if __name__ == "__main__":
    import unittest

    unittest.main()
