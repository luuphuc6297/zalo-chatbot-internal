"""Test support of the setup package (WP3, 16.10): stand-ins for the other packages, a prepared device, and runs
of `install` / `continue` in-process or as the real CLI on a pseudo-terminal.

Stand-ins (`wp_stubs/`): release, runtimes, deps (WP2), doctor (WP4), backup, move, autostart (WP5), written
against the interfaces of 16.3.3. In-process tests use them to test WP3's own logic with failures injected at the
package boundary; tests/test_integration_stubs.py keeps each stand-in's functions in step with the real module's signatures.
Subprocess tests (the real CLI) always run the real modules of the copied release.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pty
import socket
import subprocess
import sys
import termios
from pathlib import Path
from unittest import mock

from tests.support import FAKE_BIN, INSTALL_DIR, InstallerTestCase
from thomhouse_installer import bridgecli, context, paths as paths_mod, state, text_vi

HERE = Path(__file__).resolve().parent
STUB_DIR = HERE / "wp_stubs"
STUBS = ("release", "runtimes", "deps", "doctor", "backup", "move", "autostart")
DESKTOP_PROMPT = text_vi.t("ops.desktop_prompt")
ENGINE_REL = ("tools", "zalo-agent", "node_modules", ".bin", "zalo-agent")


def _load_entry():
    spec = importlib.util.spec_from_file_location("_thomhouse_entry_setup", INSTALL_DIR / "thomhouse.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENTRY = _load_entry()


def _load_stub(name: str):
    full = f"thomhouse_installer.{name}"
    spec = importlib.util.spec_from_file_location(full, STUB_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class SetupTestCase(InstallerTestCase):
    """InstallerTestCase with the stand-ins loaded in-process and helpers for install runs."""

    def setUp(self) -> None:
        super().setUp()
        saved = {}
        for name in ("_stubrec",) + STUBS:
            full = f"thomhouse_installer.{name}"
            saved[full] = sys.modules.get(full)
        self.addCleanup(self._restore_modules, saved)
        self.stubs = {name: _load_stub(name) for name in ("_stubrec",) + STUBS}

    @staticmethod
    def _restore_modules(saved: dict) -> None:
        for full, module in saved.items():
            if module is None:
                sys.modules.pop(full, None)
            else:
                sys.modules[full] = module

    # ------------------------------------------------------------ devices

    def provision_runtimes(self, root: Path, names: tuple[str, ...] = ("python", "node", "pnpm", "claude_code")) -> None:
        """The runtimes as bootstrap.sh and step 5 leave them, made of shims to the fakes."""
        rt = self.stubs["runtimes"]
        ctx = self.ctx(root)
        for item in rt.plan(ctx):
            if item.name in names:
                rt.install(ctx, item)
                rt.switch(ctx, item.name, item.wanted)

    def make_zalo_cache(self) -> None:
        db = self.zalo_config / "accounts" / "acc1" / "zalo.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"")

    def new_device(self, version: str = "1.4.0", *,
                   runtimes: tuple[str, ...] = ("python", "node", "pnpm", "claude_code"),
                   zalo_cache: bool = False) -> Path:
        """A device right after the header and bootstrap.sh: releases/<version> unpacked, no `app`, no
        installed.json; the runtimes named in `runtimes` are present (bootstrap.sh always leaves Python)."""
        root = self.install_release(version, link_app=False)
        if runtimes:
            self.provision_runtimes(root, runtimes)
        if zalo_cache:
            self.make_zalo_cache()
        return root

    def engine_shim(self, root: Path) -> Path:
        """The engine shim at app/tools/zalo-agent/...; it records the value of ZALO_AGENT_NO_UPDATE_CHECK."""
        engine = root.joinpath(*ENGINE_REL)
        engine.parent.mkdir(parents=True, exist_ok=True)
        engine.write_text('#!/bin/sh\nprintf "%s\\n" "${ZALO_AGENT_NO_UPDATE_CHECK-unset}" >> '
                          f'"{self.tmp}/zalo-nouc.txt"\nexec "{FAKE_BIN}/zalo-agent" "$@"\n', encoding="utf-8")
        engine.chmod(0o755)
        return engine

    def installed_device(self, *, accounts_main: bool = False) -> Path:
        """An installed device (app linked, env files, installed.json, engine shim) for the human steps."""
        root = self.install_release("1.4.0", link_app=True)
        app = self.app_home / "app"
        ctx = self.ctx()
        self.assertEqual(bridgecli.init_env(ctx, app, app.joinpath(*ENGINE_REL)), 0)
        state.save_installed(ctx.paths, {"schema": 1, "version": "1.4.0", "device_id": "0" * 32,
                                         "engine_notice_accepted_at": "2026-11-12T10:00:00+07:00"})
        self.engine_shim(app)
        if accounts_main:
            from thomhouse_installer import accounts

            self.assertEqual(accounts.pool(ctx, "add", "main", "--priority", "1"), 0)
            self.assertEqual(accounts.pool(ctx, "disable", "main"), 0)
        return root

    # ------------------------------------------------------------ runs

    def human_ctx(self, *, interactive: bool = True, **attrs: object):
        ctx = self.ctx(interactive=interactive, **attrs)
        return ctx

    def run_flow(self, func, *args, answers: str = "", interactive: bool = True, **kwargs):
        """Call `func(ctx, *args)` with typed `answers`; returns (result, printed text)."""
        ctx = args[0] if args and isinstance(args[0], context.Ctx) else None
        if ctx is None:
            ctx = self.human_ctx(interactive=interactive)
            call_args = (ctx,) + args
        else:
            call_args = args
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO(answers)):
            result = func(*call_args, **kwargs)
        return result, out.getvalue()

    def step_ctx(self, root: Path, *argv: str, interactive: bool = False):
        """A Ctx for `argv` (parsed by the real CLI parser) on the release `root`, for calling one step."""
        args = ENTRY.parse_args(list(argv) or ["install"])
        ctx = context.make_ctx(args, env=dict(os.environ), paths=paths_mod.resolve(os.environ, code_root=root))
        ctx.interactive = interactive
        return ctx

    def run_steps(self, root: Path, *argv: str, answers: str | None = None, interactive: bool | None = None,
                  lock: bool = True) -> tuple[int, str]:
        """`install` / `continue` in this process with the stand-ins, like the dispatcher: InstallLock (unless
        --dry-run), and an InstallerError printed and turned into its exit code."""
        from thomhouse_installer import steps

        args = ENTRY.parse_args(list(argv))
        handler = steps.cmd_install if args.command == "install" else steps.cmd_continue
        p = paths_mod.resolve(os.environ, code_root=root)
        ctx = context.make_ctx(args, env=dict(os.environ), paths=p)
        ctx.interactive = (answers is not None) if interactive is None else interactive
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO(answers or "")):
            try:
                if lock and not args.dry_run:
                    with state.InstallLock(p):
                        code = handler(ctx, args)
                else:
                    code = handler(ctx, args)
            except context.InstallerError as err:
                ENTRY._say_error(err, p, args)
                code = err.code
        return int(code), out.getvalue()

    def run_cli_tty(self, root: Path, *args: str, answers: str = "", timeout: float = 150,
                    env: dict | None = None) -> subprocess.CompletedProcess:
        """The real `python3 -I <root>/install/thomhouse.py <args>` with stdin on a pseudo-terminal holding
        `answers` (so stdin is interactive), stdout and stderr captured."""
        master, slave = pty.openpty()
        try:
            attrs = termios.tcgetattr(slave)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
            if answers:
                os.write(master, answers.encode("utf-8"))
            return subprocess.run([sys.executable, "-I", str(root / "install" / "thomhouse.py"), *args],
                                  stdin=slave, capture_output=True, text=True, cwd="/",
                                  env=env if env is not None else dict(self.env), timeout=timeout)
        finally:
            os.close(slave)
            os.close(master)

    # ------------------------------------------------------------ reading results

    def journal(self, root: Path | None = None) -> dict[str, dict]:
        p = paths_mod.resolve(os.environ, code_root=root or self.app_home / "app")
        return state.steps_all(p)

    def summary(self, root: Path | None = None) -> dict[str, tuple]:
        return {k: (v.get("status"), v.get("reason")) for k, v in self.journal(root).items()}

    def installed(self) -> dict | None:
        p = paths_mod.resolve(os.environ, code_root=self.app_home / "app")
        return state.load_installed(p)

    def pool(self) -> list[dict]:
        return json.loads((self.bot_home / "accounts.json").read_text(encoding="utf-8"))

    def stub_calls(self, module: str) -> list[list]:
        return [c["argv"] for c in self.calls(f"stub.{module}")]

    def install_log(self) -> str:
        f = self.app_home / "logs" / "install.log"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    def tree_snapshot(self) -> dict[str, tuple]:
        """Every path under HOME with its type, size and mtime (for "changes nothing")."""
        out = {}
        for folder, dirs, files in os.walk(self.home):
            for name in dirs + files:
                full = Path(folder) / name
                st = full.lstat()
                out[str(full.relative_to(self.home))] = (st.st_mode, st.st_size if not full.is_dir() else 0,
                                                         st.st_mtime_ns if not full.is_dir() else 0)
        return out
