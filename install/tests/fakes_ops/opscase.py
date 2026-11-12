"""`OpsTestCase`: InstallerTestCase plus what the operations tests share (16.10).

- `use_stubs()` puts the stand-ins of WP2 (`release`, `runtimes`, `deps`) and WP4 (`doctor`) from
  `fakes_ops/stub_modules/` in place of `thomhouse_installer.<name>` for one test (in this process only), to
  inject failures at the package boundary; tests/test_integration_stubs.py keeps them in step with the real
  modules, and tests/test_integration_flows.py runs update and rollback with the real ones. Subprocess runs always
  use the real modules.
- `installed()` gives an installed device: release 1.4.0 linked as `app`, `installed.json`, the stack started from
  the stub `start_local.sh` (which writes the env files) and a D1 database with the release's migrations.
- `release_tree()` and `release_file()` prepare a newer (or older) release and its stub release file.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

from tests.support import FAKE_BIN, InstallerTestCase, write_manifest

FAKES_OPS = Path(__file__).resolve().parent
STUBS = FAKES_OPS / "stub_modules"
STUB_NAMES = ("release", "runtimes", "deps", "doctor")
DEVICE_ID = "d" * 32
RUNTIMES = {"python": "3.14.6", "node": "24.19.0", "pnpm": "10.32.1", "claude_code": "2.1.319"}
OLD_MIGRATIONS = ("0001_init.sql", "0002_outbox.sql", "0003_profiles.sql")


class PowerCut(BaseException):
    """Raised by a test to stop a command the way a power cut would: no handler of the code under test catches it."""


class OpsTestCase(InstallerTestCase):
    # ------------------------------------------------------------ stand-ins for other packages

    def use_stubs(self, *names: str) -> dict:
        import thomhouse_installer as pkg

        names = names or STUB_NAMES
        loaded = {}
        for name in ("_stubio",) + tuple(names):
            full = f"thomhouse_installer.{name}"
            spec = importlib.util.spec_from_file_location(full, STUBS / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            patcher = mock.patch.dict(sys.modules, {full: module})
            patcher.start()
            self.addCleanup(patcher.stop)
            spec.loader.exec_module(module)
            attr = mock.patch.object(pkg, name, module, create=True)
            attr.start()
            self.addCleanup(attr.stop)
            loaded[name] = module
        return loaded

    def stub_calls(self, fn: str | None = None) -> list[dict]:
        return [c for c in self.calls("stub") if fn is None or c.get("fn") == fn]

    # ------------------------------------------------------------ trees, releases, data

    def wrangler_shim(self, root: Path) -> None:
        shim = root / "apps" / "server" / "node_modules" / ".bin" / "wrangler"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_text(f'#!/bin/sh\nexec "{FAKE_BIN}/wrangler" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)

    def add_migration(self, root: Path, name: str) -> None:
        table = name.split(".", 1)[0].split("_", 1)[-1] + "_t"
        (root / "apps" / "server" / "migrations" / name).write_text(
            f"-- Fake migration for the installer tests.\nCREATE TABLE IF NOT EXISTS {table} (id TEXT);\n",
            encoding="utf-8")

    def release_tree(self, version: str, *, migrations: tuple[str, ...] = (), node: str | None = None,
                     pnpm: str | None = None, start_fails: bool = False) -> Path:
        """A prepared release folder (what a release file's payload would unpack to)."""
        root = self.tmp / f"tree-{version}"
        root.mkdir(parents=True, exist_ok=True)
        self._fill_tree(root)
        (root / "VERSION.json").write_text(json.dumps({"schema": 1, "version": version, "menu_id": "0" * 16}),
                                           encoding="utf-8")
        for name in migrations:
            self.add_migration(root, name)
        if node:
            pins = json.loads((root / "install" / "versions.json").read_text(encoding="utf-8"))
            pins["node"]["version"] = node
            (root / "install" / "versions.json").write_text(json.dumps(pins, indent=1), encoding="utf-8")
        if pnpm:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            pkg["packageManager"] = f"pnpm@{pnpm}"
            (root / "package.json").write_text(json.dumps(pkg, indent=1), encoding="utf-8")
        if start_fails:
            script = root / "scripts" / "start_local.sh"
            text = script.read_text(encoding="utf-8")
            marker = 'FAIL_AT="$(beh fail_at_step 0)"'
            script.write_text(text.replace(marker, 'FAIL_AT="1"'), encoding="utf-8")
        write_manifest(root)
        return root

    def release_file(self, version: str, tree: Path | None, *, bad: str | None = None,
                     menu_id: str = "0" * 16) -> Path:
        folder = self.tmp / "usb"
        folder.mkdir(exist_ok=True)
        f = folder / f"thomhouse-{version}.command"
        f.write_text(json.dumps({"stub_release": 1, "version": version, "menu_id": menu_id,
                                 "tree": str(tree) if tree else "", "release_id": f"NEW-{version}",
                                 "payload_sha256": hashlib.sha256(version.encode()).hexdigest(), "bad": bad}),
                     encoding="utf-8")
        return f

    def seed_d1(self, root: Path, *, stop_before: str | None = None) -> None:
        """Apply the migrations of `root` with the fake wrangler (all, or those before `stop_before`)."""
        self.behave(wrangler={"fail_at": stop_before})
        subprocess.run([str(FAKE_BIN / "wrangler"), "d1", "migrations", "apply", "thomhouse-main", "--local",
                        "--persist-to", str(self.bot_home / "d1")], cwd=str(root / "apps" / "server"),
                       env=dict(self.env), capture_output=True, text=True, timeout=60)
        self.behave(wrangler={"fail_at": None})

    def installed(self, version: str = "1.4.0", *, start: bool = True, seed: bool = True) -> Path:
        root = self.install_release(version)
        self.wrangler_shim(root)
        installed = {"schema": 1, "device_id": DEVICE_ID, "version": version, "previous_version": None,
                     "installed_at": "2026-11-20T09:12:03+07:00", "install_completed_at": None,
                     "payload_sha256": "a" * 64, "release_id": "OLD-ID", "menu_id": "0" * 16,
                     "runtimes": dict(RUNTIMES), "previous_runtimes": None, "engine_notice_accepted_at": None,
                     "migrations_applied": list(OLD_MIGRATIONS), "backup_before_update": None, "autostart": False}
        from thomhouse_installer import state

        state.save_installed(self.paths(), installed)
        if seed:
            self.seed_d1(root)
        if start:
            from thomhouse_installer import stack

            self.assertEqual(self.quiet(stack.start, self.ctx(), quiet=True), 0)
        return root

    # ------------------------------------------------------------ helpers

    def quiet(self, fn, *args, **kwargs):
        """Call `fn` with stdout captured; the text is kept in self.out."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                return fn(*args, **kwargs)
            finally:
                self.out = buf.getvalue()

    def answer(self, text: str):
        """Patch stdin with `text` (for an interactive ctx)."""
        patcher = mock.patch("sys.stdin", io.StringIO(text))
        patcher.start()
        self.addCleanup(patcher.stop)

    def journal(self) -> dict | None:
        from thomhouse_installer import state

        return state.update_get(self.paths())

    def app_target(self) -> str:
        return os.readlink(self.app_home / "app")

    def dumps(self, d1: Path | None = None) -> dict[str, list[str]]:
        """iterdump() of every SQLite file under d1, keyed by its path relative to d1."""
        d1 = d1 or self.bot_home / "d1"
        out = {}
        for f in sorted(d1.rglob("*.sqlite")):
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            try:
                out[str(f.relative_to(d1))] = list(con.iterdump())
            finally:
                con.close()
        return out

    def applied(self) -> list[str] | None:
        from thomhouse_installer import migrations

        return migrations.applied(self.bot_home)

    def history(self) -> list[dict]:
        f = self.app_home / "history.jsonl"
        if not f.exists():
            return []
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]

    def start_calls(self) -> list[dict]:
        return self.calls("start_local.sh")

    def stop_calls(self) -> list[dict]:
        return self.calls("stop_local.sh")

    def alive_services(self) -> set[str]:
        from thomhouse_installer import stack

        return {s.name for s in stack.services(self.paths()) if s.alive}
