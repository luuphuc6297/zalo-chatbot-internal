"""doctor.py: the 48 checks of 16.7, their exact lines, the rules before install, in checkout mode, offline and with
the stack stopped, `passes()`, `exit_code()`, `--json`, `--strict`, `--only`, and the subprocess run with -I (rev F2,
F7, F9, F20, F23, rev check).

The WP2 calls (`release`, `deps`, `runtimes`) are replaced by stand-ins in every in-process test (`stub_wp2`), so
these tests prove the doctor's own rules apart from WP2's stamp and manifest formats; tests/test_integration_stubs.py
keeps the stand-ins' parameters equal to the real functions'. `test_subprocess_json_from_root` runs the real program
with the real WP2 modules, and tests/test_integration_flows.py runs the doctor on an installation made by the real
header, bootstrap and steps.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tests.support import FAKE_BIN, InstallerTestCase
from thomhouse_installer import bridgecli, doctor, migrations, platforms, stack, state, text_vi
from thomhouse_installer.text_vi import t

TB = "~/ThomHouse/bin/thomhouse"
CHECKOUT_TB = "python3 -I install/thomhouse.py"
RUNTIME_VERSIONS = {"python": "3.14.6", "node": "24.19.0", "pnpm": "10.32.1", "claude_code": "2.1.319"}
CHECKOUT_ALLOWED = {"doctor", "backup", "backups", "restore", "move-out", "move-back"}


def _denylisted(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(rel_path, p.replace("**/", "")) for p in patterns)


def _shim(path: Path, tool: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nexec "{FAKE_BIN}/{tool}" "$@"\n', encoding="utf-8")
    path.chmod(0o755)


class DoctorFixture:
    """Mixin for InstallerTestCase: WP2 stand-ins and a complete fake installation."""

    def stub_wp2(self, **overrides: dict) -> dict[str, types.ModuleType]:
        """Put stand-ins of thomhouse_installer.release, deps and runtimes into sys.modules for this test.

        Defaults describe a healthy installation; `overrides` maps a module name to {function name: callable}.
        """
        defaults = {
            "release": {
                "verify_manifest": lambda code_root: [],
                "denylist": lambda code_root: ["**/.env", "**/.dev.vars", "sources/**"],
                "denylisted": _denylisted,
                "menu_slides_ok": lambda ctx, code_root: True,
            },
            "deps": {"stamp_ok": lambda ctx, code_root: {"workspace": True, "engine": True, "rooms": True}},
            "runtimes": {"found": lambda ctx, name: RUNTIME_VERSIONS.get(name)},
        }
        modules = {}
        for name, funcs in defaults.items():
            funcs = dict(funcs)
            funcs.update(overrides.get(name, {}))
            full = f"thomhouse_installer.{name}"
            module = types.ModuleType(full)
            for attr, fn in funcs.items():
                setattr(module, attr, fn)
            modules[full] = module
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        return modules

    def set_wp2(self, module: str, **funcs) -> None:
        """Replace functions of a stand-in installed by `stub_wp2`."""
        for attr, fn in funcs.items():
            setattr(sys.modules[f"thomhouse_installer.{module}"], attr, fn)

    def write_pool(self, *accounts: dict, logins: dict | None = None, pool_state: dict | None = None) -> None:
        """accounts.json, account-state.json and the fake claude's login state per config folder."""
        self.bot_home.mkdir(parents=True, exist_ok=True)
        entries = []
        for a in accounts:
            cfg = a.get("config_dir", self.bot_home / "accounts" / a["label"])
            if cfg is not None:
                Path(cfg).mkdir(parents=True, exist_ok=True)
            entries.append({"label": a["label"], "config_dir": str(cfg) if cfg else None,
                            "priority": a.get("priority", 1), "enabled": a.get("enabled", True)})
        (self.bot_home / "accounts.json").write_text(json.dumps(entries), encoding="utf-8")
        (self.bot_home / "account-state.json").write_text(json.dumps(pool_state or {}), encoding="utf-8")
        auth = {}
        for label, login in (logins or {}).items():
            key = str(self.bot_home / "accounts" / label)
            if login == "max":
                auth[key] = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
            elif login == "null":
                auth[key] = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": None}
            elif login == "api_key":
                auth[key] = {"loggedIn": True, "authMethod": "api_key", "subscriptionType": None}
        (self.tmp / "claude-auth.json").write_text(json.dumps(auth), encoding="utf-8")

    def make_installed(self, *, start: bool = True, rooms: bool = True, logged_in: bool = True) -> Path:
        """A complete installation of 1.4.0 that every check of 16.7 accepts; with `start` the stub stack runs.
        Returns the release folder."""
        self.stub_wp2()
        root = self.install_release("1.4.0")
        p = self.paths()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        state.save_installed(p, {"schema": 1, "device_id": "0" * 32, "version": "1.4.0", "installed_at": now,
                                 "install_completed_at": now, "menu_id": "0" * 16})
        local = self.home / ".local" / "bin" / "claude"
        _shim(local, "claude")
        (self.app_home / "runtime" / "bin").mkdir(parents=True, exist_ok=True)
        (self.app_home / "runtime" / "bin" / "claude").symlink_to(local)
        engine = root / "tools" / "zalo-agent" / "node_modules"
        (engine / "@ardennguyen" / "zalo-agent-cli").mkdir(parents=True)
        (engine / "@ardennguyen" / "zalo-agent-cli" / "package.json").write_text('{"version": "2.5.9"}')
        _shim(engine / ".bin" / "zalo-agent", "zalo-agent")
        rooms_dir = root / "tools" / "openmausbot" / "node_modules"
        (rooms_dir / "openmausbot").mkdir(parents=True)
        (rooms_dir / "openmausbot" / "package.json").write_text('{"version": "0.1.154"}')
        _shim(rooms_dir / ".bin" / "openmausbot", "openmausbot")
        _shim(root / "apps" / "server" / "node_modules" / ".bin" / "wrangler", "wrangler")
        self.behave(wrangler={"catalog": doctor._expected_catalog(root)},
                    bridge={"doctor": {"room_platform": "ok"}},
                    start_local={"rooms": rooms})
        ctx = self.ctx()
        self.assertEqual(migrations.apply(ctx, self.app_home / "app"), 0)
        self.write_pool({"label": "main", "enabled": logged_in}, logins={"main": "max"} if logged_in else {})
        for step in ("history_sync", "analyze_contacts", "analyze_visits", "staff_token"):
            state.step_set(p, step, "done")
        backup = self.bot_home / "backups" / "20261112-100000-manual"
        backup.mkdir(parents=True)
        (backup / "backup.json").write_text(json.dumps({
            "schema": 1, "id": backup.name, "created_at": now, "reason": "manual", "mode": "stopped",
            "app_version": "1.4.0", "device_id": "0" * 32, "migrations_applied": [], "files": []}))
        for folder in (self.app_home, self.bot_home, self.bot_home / "backups"):
            folder.chmod(0o700)
        if start:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(stack.start(ctx, quiet=True), 0)
        else:
            app_engine = self.app_home / "app" / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent"
            self.assertEqual(bridgecli.init_env(ctx, self.app_home / "app", app_engine), 0)
        return root

    def check(self, check_id: str, ctx=None) -> doctor.CheckResult:
        """Run one check with a fresh context and return its result."""
        results = doctor.run_checks(ctx or self.ctx(), only={check_id})
        self.assertEqual(len(results), 1)
        return results[0]

    def assert_line(self, check_id: str, expected: str, ctx=None) -> doctor.CheckResult:
        result = self.check(check_id, ctx)
        self.assertEqual(doctor.line(result), expected)
        return result

    def run_doctor(self, ctx=None, **args) -> tuple[int, str]:
        ns = {"command": "doctor", "json": False, "strict": False, "only": None, "offline": False}
        ns.update(args)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.cmd_doctor(ctx or self.ctx(offline=ns["offline"]), argparse.Namespace(**ns))
        return code, out.getvalue()


def _status(results: list[doctor.CheckResult]) -> dict[str, str]:
    return {r.id: r.status for r in results}


class DoctorTableTest(InstallerTestCase):
    def test_table_matches_16_7(self) -> None:
        self.assertEqual([d.n for d in doctor.CHECKS], list(range(1, 49)))
        self.assertEqual(len({d.id for d in doctor.CHECKS}), 48)
        net = {d.id for d in doctor.CHECKS if d.net}
        run = {d.id for d in doctor.CHECKS if d.run}
        self.assertEqual(net, {"claude_login", "zalo_login", "listener", "room_platform"})
        self.assertEqual(run, {"processes", "server_health", "runner_online", "catalog", "console", "listener",
                               "bridge_token", "room_platform", "listen_local_only", "openmausbot_options",
                               "reply_flags", "labels"})
        for d in doctor.CHECKS:
            self.assertIn(f"doctor.label_{d.id}", text_vi.TEXTS)

    def test_line_and_exit_code(self) -> None:
        ok = doctor.CheckResult(1, "macos", "machine", "pass", "Hệ điều hành", "macOS 15.1", "unused")
        bad = doctor.CheckResult(12, "node", "program", "fail", "Node.js", "chưa có bản 24.19.0.",
                                 f"{TB} install --only runtimes")
        self.assertEqual(doctor.line(ok), "[ĐẠT] Hệ điều hành: macOS 15.1")
        self.assertEqual(doctor.line(bad), "[LỖI] Node.js: chưa có bản 24.19.0. Cách sửa: "
                                           "~/ThomHouse/bin/thomhouse install --only runtimes")
        skip = doctor.CheckResult(30, "claude_login", "claude", "skip", "Đăng nhập Claude", "chạy với --offline", None)
        self.assertEqual(doctor.line(skip), "[BỎ QUA] Đăng nhập Claude: chạy với --offline")
        self.assertEqual(ok.as_dict(), {"n": 1, "id": "macos", "group": "machine", "status": "pass",
                                        "label": "Hệ điều hành", "detail": "macOS 15.1", "fix": "unused"})
        warn = doctor.CheckResult(2, "cpu", "machine", "warn", "Chip", "x", None)
        todo = doctor.CheckResult(26, "database", "data", "todo", "Cơ sở dữ liệu", "x", None)
        self.assertEqual(doctor.exit_code([ok, warn, todo], False), 0)
        self.assertEqual(doctor.exit_code([ok, warn], True), 1)
        self.assertEqual(doctor.exit_code([ok, todo], True), 1)
        self.assertEqual(doctor.exit_code([ok, bad], False), 1)
        crashed = doctor.CheckResult(3, "disk", "machine", "fail", "Dung lượng trống", "x", None, crashed=True)
        self.assertEqual(doctor.exit_code([ok, crashed], False), 2)
        self.assertNotIn("crashed", crashed.as_dict())


class BeforeInstallTest(DoctorFixture, InstallerTestCase):
    def test_before_install(self) -> None:
        self.stub_wp2()
        self.install_release("1.4.0")
        results = doctor.run_checks(self.ctx())
        self.assertEqual(len(results), 48)
        by_id = {r.id: r for r in results}
        self.assertEqual(doctor.line(by_id["release"]),
                         "[LỖI] Bản cài: chưa cài chương trình. Cách sửa: anh chạy file thomhouse-1.4.0.command.")
        for r in results[9:]:
            self.assertNotEqual(r.status, "pass", r.id)
            self.assertEqual(r.status, "todo", r.id)
            self.assertEqual(r.fix, "anh chạy file thomhouse-1.4.0.command", r.id)
        self.assertEqual(doctor.exit_code(results, False), 1)
        code, out = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertEqual(len(out.splitlines()), 48)
        self.assertIn("[CHƯA LÀM] Cơ sở dữ liệu: chưa làm được vì chương trình chưa cài. "
                      "Cách sửa: anh chạy file thomhouse-1.4.0.command", out)
        # The step checks of install look at the machine, not at the missing installed.json.
        self.assertFalse(doctor.passes(self.ctx(), {"node", "pnpm", "claude_cli"}))  # no runtime/bin/claude
        self.assertTrue(doctor.passes(self.ctx(), {"node", "pnpm"}))
        # Python missing before install: the fix names the release file.
        self.set_wp2("runtimes", found=lambda ctx, name: None)
        self.assert_line("python", "[LỖI] Python: chưa có Python 3.14.6. Cách sửa: anh chạy lại file "
                                   "thomhouse-1.4.0.command.")

    def test_subprocess_json_from_root(self) -> None:
        # The real program under python3 -I from cwd "/" (rev F2); WP2 modules are whatever this copy holds.
        self.install_release("1.4.0")
        res = self.run_cli(None, "doctor", "--json", cwd="/")
        self.assertEqual(res.returncode, 1, res.stderr)
        doc = json.loads(res.stdout)
        self.assertEqual(doc["schema"], 1)
        self.assertEqual(doc["exit"], 1)
        self.assertEqual([c["n"] for c in doc["checks"]], list(range(1, 49)))
        for entry in doc["checks"]:
            self.assertEqual(set(entry), {"n", "id", "group", "status", "label", "detail", "fix"})
            self.assertIn(entry["status"], doctor.STATUSES)
        self.assertEqual(doc["checks"][8]["status"], "fail")
        res = self.run_cli(None, "doctor", "--only", "macos,disk", cwd="/")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "[ĐẠT] Hệ điều hành: macOS 15.1")
        self.assertTrue(lines[1].startswith("[ĐẠT] Dung lượng trống: "), lines[1])
        res = self.run_cli(None, "doctor", "--only", "nope", cwd="/")
        self.assertEqual(res.returncode, 2)
        self.assertEqual(res.stdout.strip(), t("doctor.unknown_check", name="nope"))


class InstalledTest(DoctorFixture, InstallerTestCase):
    def test_all_pass_after_a_fake_install(self) -> None:
        self.make_installed()
        results = doctor.run_checks(self.ctx())
        self.assertEqual({r.id: (r.status, r.detail) for r in results if r.status != "pass"}, {})
        self.assertEqual(doctor.exit_code(results, True), 0)
        code, out = self.run_doctor(strict=True)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 48)
        self.assertTrue(all(x.startswith("[ĐẠT] ") for x in lines), out)
        for expected in ("[ĐẠT] Hệ điều hành: macOS 15.1", "[ĐẠT] Chip: Apple Silicon", "[ĐẠT] Python: 3.14.6",
                         "[ĐẠT] Lệnh cài khác: không có", "[ĐẠT] Máy đã chuyển đi: không",
                         "[ĐẠT] Bản chatbot khác: không có", "[ĐẠT] Node.js: 24.19.0", "[ĐẠT] pnpm: 10.32.1",
                         "[ĐẠT] Claude Code: 2.1.319", "[ĐẠT] Phiên bản ghi trong mã: khớp",
                         "[ĐẠT] Thư viện JavaScript: đúng cho máy này", "[ĐẠT] Bộ công cụ Zalo: 2.5.9",
                         "[ĐẠT] OpenMausBot: 0.1.154", "[ĐẠT] Ảnh menu gốc: bộ 0000000000000000",
                         "[ĐẠT] File cấu hình: đủ 3 file", "[ĐẠT] Mã bí mật khớp nhau: khớp",
                         "[ĐẠT] Cơ sở dữ liệu: có", "[ĐẠT] Bản cập nhật cơ sở dữ liệu: đủ 3 bản",
                         "[ĐẠT] Tài khoản Claude của chatbot: 1 tài khoản dùng được",
                         "[ĐẠT] Đăng nhập Claude: đã đăng nhập", "[ĐẠT] Các phần của chatbot: đang chạy",
                         "[ĐẠT] Runner: đang báo về máy chủ", "[ĐẠT] Console: đang mở",
                         "[ĐẠT] Nhận tin Zalo: đang nhận tin", "[ĐẠT] Chế độ trả lời: duyệt từng tin",
                         "[ĐẠT] Nhãn khách trong Zalo: 1 người có nhãn",
                         "[ĐẠT] Mã nhân viên trong console: đã đưa vào console"):
            self.assertIn(expected, lines)
        today = datetime.now().strftime("%d/%m/%Y")
        self.assertIn(f"[ĐẠT] Bản cài: bản 1.4.0, cài ngày {today}", lines)
        self.assertIn(f"[ĐẠT] Sao lưu: {today}", lines)
        code, out = self.run_doctor(json=True)
        doc = json.loads(out)
        self.assertEqual((doc["schema"], doc["exit"], len(doc["checks"])), (1, 0, 48))
        self.assertEqual(doc["checks"][0], {"n": 1, "id": "macos", "group": "machine", "status": "pass",
                                            "label": "Hệ điều hành", "detail": "macOS 15.1", "fix": None})
        # Each step's check() is passes(); every id of 16.4.3 passes here.
        self.assertTrue(doctor.passes(self.ctx(), {"node", "pnpm", "claude_cli", "deps_workspace", "deps_engine",
                                                    "zalo_login", "listener"}))
        with self.assertRaises(ValueError):
            doctor.passes(self.ctx(), {"no_such_check"})
        # --only takes ids and numbers.
        code, out = self.run_doctor(only={"1", "cpu"})
        self.assertEqual(out.splitlines(), ["[ĐẠT] Hệ điều hành: macOS 15.1", "[ĐẠT] Chip: Apple Silicon"])

    def test_doctor_never_calls_runner_api(self) -> None:
        self.make_installed()
        code, _ = self.run_doctor()
        self.assertEqual(code, 0)
        paths_called = [c["path"] for c in self.server_calls()]
        self.assertIn("/staff/runner", paths_called)
        self.assertFalse([p for p in paths_called if p.startswith("/runner/")], paths_called)
        self.assertTrue(all(c["auth"] for c in self.server_calls() if c["path"].startswith("/staff/")))
        self.assertFalse(any(c["runner_id"] for c in self.server_calls()))
        # Check 34 read the catalog id from the D1 file of the fixture.
        expected = doctor._expected_catalog(self.app_home / "app")
        self.assertEqual(self.check("catalog").detail, expected)
        db = migrations.find_db(self.bot_home)
        con = sqlite3.connect(db)
        con.execute("UPDATE catalog_versions SET id = 'cv_local_000000000000'")
        con.commit()
        con.close()
        self.assert_line("catalog", f"[LỖI] Danh mục dịch vụ: danh mục trên máy chủ chưa phải bản mới. "
                                    f"Cách sửa: {TB} restart")
        # Check 33 counts only the row of this device's RUNNER_ID (mac-local-1 from init-env).
        self.server.set_route("GET /staff/runner", 200, {"runners": [
            {"runner_id": "mac-runner-1", "online": True}, {"runner_id": "mac-local-1", "online": False}]})
        self.assert_line("runner_online", f"[LỖI] Runner: runner không báo về máy chủ. Cách sửa: xem "
                                          f"~/.thomhouse-bot/logs/runner.log rồi chạy: {TB} restart")
        runner_env = self.app_home / "app" / "apps" / "runner" / ".env"
        text = runner_env.read_text(encoding="utf-8")
        runner_env.write_text("\n".join(x for x in text.splitlines() if not x.startswith("RUNNER_ID=")) + "\n")
        self.assertEqual(self.check("runner_online").status, "pass")  # the default mac-runner-1 is online
        self.server.set_route("GET /staff/runner", 500, {"error": "x"})
        self.assert_line("runner_online", f"[LỖI] Runner: máy chủ chưa trả lời yêu cầu /staff/runner. "
                                          f"Cách sửa: {TB} restart")
        self.assertFalse([c["path"] for c in self.server_calls() if c["path"].startswith("/runner/")])

    def test_postponed_logins_are_todo(self) -> None:
        self.make_installed(logged_in=False)
        self.behave(bridge={"doctor": {"zalo_login": "fail", "listener": "fail", "room_platform": "ok"}})
        results = {r.id: r for r in doctor.run_checks(self.ctx())}
        for check_id in ("claude_pool", "claude_login", "zalo_login", "listener"):
            self.assertEqual(results[check_id].status, "todo", check_id)
        self.assertEqual(doctor.line(results["claude_pool"]),
                         "[CHƯA LÀM] Tài khoản Claude của chatbot: chưa đăng nhập tài khoản Claude nào; chatbot "
                         f"chưa soạn trả lời. Cách sửa: {TB} login-claude")
        self.assertEqual(doctor.line(results["claude_login"]),
                         "[CHƯA LÀM] Đăng nhập Claude: tài khoản main chưa đăng nhập; chatbot chưa soạn trả lời. "
                         f"Cách sửa: {TB} login-claude main")
        self.assertEqual(doctor.line(results["zalo_login"]),
                         f"[CHƯA LÀM] Đăng nhập Zalo: chưa đăng nhập Zalo; chatbot chưa nhận tin. Cách sửa: "
                         f"{TB} login-zalo")
        self.assertEqual(doctor.line(results["listener"]),
                         f"[CHƯA LÀM] Nhận tin Zalo: chưa nhận tin vì chưa đăng nhập Zalo. Cách sửa: {TB} login-zalo")
        self.assertEqual([r.id for r in results.values() if r.status == "fail"], [])
        self.assertEqual(self.run_doctor()[0], 0)
        self.assertEqual(self.run_doctor(strict=True)[0], 1)
        # Login done but the listener not running: LỖI with restart.
        self.behave(bridge={"doctor": {"zalo_login": "ok", "listener": "fail", "room_platform": "ok"}})
        self.assert_line("listener", f"[LỖI] Nhận tin Zalo: phần nhận tin Zalo chưa chạy. Cách sửa: {TB} restart")
        self.behave(bridge={"doctor": {"listener": "warn", "room_platform": "ok"}})
        self.assertEqual(self.check("listener").status, "warn")

    def test_offline_calls_neither_claude_nor_bridge(self) -> None:
        self.make_installed()
        before_claude = len([c for c in self.calls("claude") if c["argv"][:2] == ["auth", "status"]])
        before_bridge = len([c for c in self.calls("bridge") if c["argv"][:1] == ["doctor"]])
        code, out = self.run_doctor(offline=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(len([c for c in self.calls("claude") if c["argv"][:2] == ["auth", "status"]]), before_claude)
        self.assertEqual(len([c for c in self.calls("bridge") if c["argv"][:1] == ["doctor"]]), before_bridge)
        for label in ("Đăng nhập Claude", "Đăng nhập Zalo", "Nhận tin Zalo", "Bridge", "Phòng chat hai bot"):
            self.assertIn(f"[BỎ QUA] {label}: chạy với --offline", out.splitlines())

    def test_stopped_stack(self) -> None:
        self.make_installed()
        self.assertTrue(stack.stop(self.ctx()))
        results = {r.id: r for r in doctor.run_checks(self.ctx())}
        self.assertEqual(doctor.line(results["processes"]),
                         f"[LỖI] Các phần của chatbot: server, cron, runner, bridge, console chưa chạy. "
                         f"Cách sửa: {TB} start")
        for d in doctor.CHECKS:
            if d.run and d.id != "processes" and not d.net:
                self.assertEqual(doctor.line(results[d.id]), f"[BỎ QUA] {t('doctor.label_' + d.id)}: chatbot đang tắt")
        # Partly running: the missing ones are named.
        self.behave(start_local={"skip": ["runner", "console"], "rooms": True})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(stack.start(self.ctx(), quiet=True), 0)
        self.assert_line("processes", f"[LỖI] Các phần của chatbot: runner, console chưa chạy. Cách sửa: {TB} start")

    def test_running_stack_failures(self) -> None:
        self.make_installed(rooms=False)
        self.assert_line("processes", "[CHÚ Ý] Các phần của chatbot: OpenMausBot chưa chạy; phòng chat hai bot đang "
                                      f"tắt. Cách sửa: {TB} restart")
        self.assert_line("openmausbot_options", "[ĐẠT] Tùy chọn của OpenMausBot: OpenMausBot không chạy.")
        self.server.set_route("GET /health", 200, {"ok": True, "zalo_mode": "mock"})
        self.assert_line("server_health", "[LỖI] Máy chủ local: máy chủ đang chạy ở chế độ mock, không phải personal. "
                                          f"Cách sửa: {TB} restart; nếu vẫn lỗi, xem ~/.thomhouse-bot/logs/server.log")
        dead = self.ctx()
        dead.env = dict(dead.env, THOMHOUSE_SERVER_URL="http://127.0.0.1:9", THOMHOUSE_CONSOLE_URL="http://127.0.0.1:9")
        self.assert_line("server_health", "[LỖI] Máy chủ local: máy chủ chưa trả lời. Cách sửa: "
                                          f"{TB} restart; nếu vẫn lỗi, xem ~/.thomhouse-bot/logs/server.log", dead)
        self.assert_line("console", f"[LỖI] Console: console chưa mở. Cách sửa: {TB} start", dead)
        flags = {"ai_engine": "subscription", "auto_reply_mode": "approve_each", "outbound_enabled": True}
        for change, expected in (
            ({"ai_engine": "api_key"}, "[LỖI] Chế độ trả lời: ai_engine đang là api_key. Cách sửa: anh báo người "
                                       "phụ trách."),
            ({"auto_reply_mode": "auto_allowed"}, "[CHÚ Ý] Chế độ trả lời: chatbot đang tự gửi trả lời không chờ "
                                                  "duyệt. Cách sửa: nếu anh không chủ ý bật, tắt trong màn hình Cài "
                                                  "đặt của console."),
            ({"outbound_enabled": False}, "[CHÚ Ý] Chế độ trả lời: mọi tin gửi ra Zalo đang tắt. Cách sửa: bật lại "
                                          "trong màn hình Cài đặt sau khi anh xem hàng chờ gửi."),
            ({"auto_reply_mode": "draft_only"}, "[ĐẠT] Chế độ trả lời: draft_only"),
        ):
            self.server.set_route("GET /staff/flags", 200, {"flags": dict(flags, **change), "updated": {}})
            self.assert_line("reply_flags", expected)
        self.server.set_route("GET /staff/roles", 200, {"roles": []})
        self.assert_line("labels", "[CHƯA LÀM] Nhãn khách trong Zalo: chưa có ai được gắn nhãn Khách hàng, Quản lý "
                                   f"hoặc Nhân viên. Cách sửa: anh gắn nhãn trong app Zalo rồi chạy: {TB} labels")
        self.server.set_route("GET /staff/roles", 200, [{"role": "staff"}, {"role": "customer"}])
        self.assert_line("labels", "[ĐẠT] Nhãn khách trong Zalo: 2 người có nhãn")
        self.behave(bridge={"doctor": {"bridge_token": "fail", "room_platform": "warn"}})
        self.assert_line("bridge_token", f"[LỖI] Bridge: bridge chưa kết nối được máy chủ. Cách sửa: {TB} restart")
        self.assert_line("room_platform", "[CHÚ Ý] Phòng chat hai bot: chưa sẵn sàng; chatbot vẫn trả lời bình "
                                          "thường.")
        self.behave(bridge={"doctor": {"bridge_token": "warn", "room_platform": "ok"}})
        self.assertEqual(self.check("bridge_token").status, "warn")
        self.behave(build_menu_images={"check_exit": 1})
        self.assert_line("menu_images", "[CHÚ Ý] Ảnh menu cho Zalo: chưa đủ; bot chưa gửi được ảnh menu. Cách sửa: "
                                        f"{TB} restart")
        env = self.app_home / "app" / "apps" / "server" / ".dev.vars"
        env.write_text("\n".join(x for x in env.read_text().splitlines() if not x.startswith("STAFF_TOKEN=")) + "\n")
        self.assert_line("reply_flags", "[LỖI] Chế độ trả lời: thiếu STAFF_TOKEN trong apps/server/.dev.vars. "
                                        f"Cách sửa: {TB} install --only config")

    def test_release_and_update_journal(self) -> None:
        self.make_installed(start=False)
        p = self.paths()
        state.update_set(p, {"from": "1.4.0", "to": "1.5.0", "file": "/Volumes/USB/thomhouse-1.5.0.command",
                             "phases": {"U1": "done", "U9": "done"}, "state": "running"})
        self.assert_line("release", "[LỖI] Bản cài: lần cập nhật trước chưa xong. Cách sửa: "
                                    f"{TB} update /Volumes/USB/thomhouse-1.5.0.command")
        state.update_set(p, None)
        installed = state.load_installed(p)
        installed["version"] = "1.3.2"
        state.save_installed(p, installed)
        self.assert_line("release", f"[LỖI] Bản cài: bản cài không khớp với ghi chép cài đặt. Cách sửa: {TB} repair")

    def test_program_failures(self) -> None:
        root = self.make_installed(start=False)
        self.set_wp2("release", verify_manifest=lambda code_root: ["a.py", "b.py"])
        self.assert_line("release_files", f"[LỖI] Tệp chương trình: 2 tệp bị sửa hoặc bị mất. Cách sửa: {TB} repair")
        manifest = json.loads((root / "MANIFEST.json").read_text())
        manifest["files"].append({"path": "apps/runner/.env", "sha256": "0" * 64, "bytes": 1})
        (root / "MANIFEST.json").write_text(json.dumps(manifest))
        self.assert_line("release_clean", "[LỖI] Tệp không được mang theo: bản cài có tệp không được mang theo: "
                                          "1.4.0/apps/runner/.env. Cách sửa: anh tắt chatbot và báo người làm file "
                                          "cài.")
        self.set_wp2("runtimes", found=lambda ctx, name: {"node": "22.1.0", "pnpm": "9.0.0",
                                                           "claude_code": "2.1.300", "python": "3.13.1"}.get(name))
        self.assert_line("node", f"[LỖI] Node.js: chưa có bản 24.19.0. Cách sửa: {TB} install --only runtimes")
        self.assert_line("pnpm", f"[LỖI] pnpm: chưa có bản 10.32.1. Cách sửa: {TB} install --only runtimes")
        self.assert_line("claude_cli", "[LỖI] Claude Code: chưa có Claude Code 2.1.319 trở lên. "
                                       f"Cách sửa: {TB} install --only runtimes")
        self.assert_line("python", "[LỖI] Python: chưa có Python 3.14.6. Cách sửa: "
                                   "bash ~/ThomHouse/app/install/bootstrap.sh --python-only")
        self.set_wp2("runtimes", found=lambda ctx, name: "2.2.0" if name == "claude_code" else None)
        self.assert_line("claude_cli", "[CHÚ Ý] Claude Code: bản 2.2.0 mới hơn bản đã thử 2.1.319.")
        (self.app_home / "runtime" / "bin" / "claude").unlink()
        (self.app_home / "runtime" / "bin" / "claude").symlink_to(self.home / "elsewhere" / "claude")
        self.assert_line("claude_cli", "[LỖI] Claude Code: chương trình chưa nối tới Claude Code trong ~/.local/bin. "
                                       f"Cách sửa: {TB} install --only runtimes")
        self.set_wp2("deps", stamp_ok=lambda ctx, code_root: {"workspace": False, "engine": False, "rooms": False})
        self.assert_line("deps_workspace", "[LỖI] Thư viện JavaScript: chưa cài cho máy này hoặc đã cũ. "
                                           f"Cách sửa: {TB} install --only deps")
        self.assert_line("deps_engine", f"[LỖI] Bộ công cụ Zalo: chưa đúng bản 2.5.9. Cách sửa: {TB} install --only "
                                        "deps")
        self.assert_line("deps_rooms", "[CHÚ Ý] OpenMausBot: chưa cài; phòng chat hai bot sẽ tắt, chatbot vẫn trả lời "
                                       f"bình thường. Cách sửa: {TB} install --only deps")
        self.set_wp2("release", menu_slides_ok=lambda ctx, code_root: False)
        self.assert_line("menu_slides", "[CHÚ Ý] Ảnh menu gốc: chưa có bộ ảnh menu gốc 0000000000000000. Cách sửa: "
                                        "anh chép file thomhouse-menu-0000000000000000.tar vào máy rồi chạy: "
                                        f"{TB} install --only menu_slides --menu <file>")
        script = root / "scripts" / "start_local.sh"
        script.write_text(script.read_text().replace('ENGINE_VERSION="2.5.9"', 'ENGINE_VERSION="2.6.0"'))
        self.assert_line("pins", "[LỖI] Phiên bản ghi trong mã: các phiên bản ghi trong mã không khớp nhau: "
                                 "zalo-agent-cli. Cách sửa: anh báo người làm file cài.")
        # A WP2 module that is not part of this copy: a failure line, not a crash.
        with mock.patch.object(doctor, "_part", lambda name: None):
            self.assert_line("deps_workspace", "[LỖI] Thư viện JavaScript: thiếu phần deps của chương trình. "
                                               "Cách sửa: anh báo người làm file cài.")

    def test_config_failures(self) -> None:
        self.make_installed(start=False)
        app = self.app_home / "app"
        runner_env = app / "apps" / "runner" / ".env"
        bridge_env = app / "apps" / "zalo-bridge" / ".env"
        server_env = app / "apps" / "server" / ".dev.vars"
        self.assertEqual(self.check("env_files").status, "pass")
        runner_env.chmod(0o644)
        self.assert_line("env_files", "[LỖI] File cấu hình: apps/runner/.env thiếu, sai quyền hoặc thiếu SERVER_URL, "
                                      f"RUNNER_TOKEN. Cách sửa: {TB} install --only config")
        runner_env.chmod(0o600)
        original = runner_env.read_text()
        runner_env.write_text(original.replace("RUNNER_TOKEN=", "RUNNER_TOKEN=x"))
        self.assert_line("tokens_agree", "[LỖI] Mã bí mật khớp nhau: mã bí mật giữa các file cấu hình không khớp. "
                                         f"Cách sửa: {TB} repair --env")
        runner_env.write_text("\n".join(x for x in original.splitlines() if not x.startswith("RUNNER_TOKEN=")) + "\n")
        self.assert_line("env_files", "[LỖI] File cấu hình: apps/runner/.env thiếu, sai quyền hoặc thiếu "
                                      f"RUNNER_TOKEN. Cách sửa: {TB} install --only config")
        runner_env.write_text(original)
        self.assertEqual(self.check("tokens_agree").status, "pass")
        text = bridge_env.read_text()
        bridge_env.write_text(text.replace(f"ZALO_AGENT_BIN={app}", "ZALO_AGENT_BIN=/old/ThomHouse/app"))
        self.assert_line("paths_current", "[LỖI] Đường dẫn trong file cấu hình: ZALO_AGENT_BIN trỏ tới một thư mục "
                                          f"không còn dùng. Cách sửa: {TB} repair --paths")
        bridge_env.write_text(text)
        runner_env.write_text(original + f"OPENMAUSBOT_NODE_DIR={self.home}/.nvm/node/bin\n")
        self.assert_line("paths_current", "[LỖI] Đường dẫn trong file cấu hình: OPENMAUSBOT_NODE_DIR trỏ tới một thư "
                                          f"mục không còn dùng. Cách sửa: {TB} repair --paths")
        node_dir = self.app_home / "runtime" / "node" / "bin"
        node_dir.mkdir(parents=True)
        runner_env.write_text(original + "OPENMAUSBOT_NODE_DIR=~/ThomHouse/runtime/node/bin\n")
        self.assertEqual(self.check("paths_current").status, "pass")
        self.bot_home.chmod(0o755)
        self.assert_line("permissions", "[LỖI] Quyền thư mục: ~/.thomhouse-bot cho người khác đọc được. "
                                        f"Cách sửa: {TB} repair")
        self.bot_home.chmod(0o700)
        (self.bot_home / "profiles").mkdir(mode=0o755)
        (self.bot_home / "profiles").chmod(0o755)
        self.assert_line("permissions", "[LỖI] Quyền thư mục: ~/.thomhouse-bot/profiles cho người khác đọc được. "
                                        f"Cách sửa: {TB} repair")
        (self.bot_home / "profiles").chmod(0o700)
        self.assertEqual(self.check("permissions").status, "pass")
        server_env.write_text(server_env.read_text() + "ANTHROPIC_AUTH_TOKEN=planted-auth-token-value-0001\n")
        self.assert_line("no_api_key", "[LỖI] Khóa API Anthropic: apps/server/.dev.vars đặt ANTHROPIC_AUTH_TOKEN; "
                                       f"chatbot chỉ dùng gói Claude. Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart")
        server_env.write_text(server_env.read_text().replace("ANTHROPIC_AUTH_TOKEN=planted-auth-token-value-0001\n",
                                                             ""))
        ctx = self.ctx()
        ctx.env = dict(ctx.env, CLAUDE_CODE_OAUTH_TOKEN="planted-oauth-value-0002")
        self.assert_line("no_api_key", "[CHÚ Ý] Khóa API Anthropic: biến môi trường của Terminal đặt "
                                       "CLAUDE_CODE_OAUTH_TOKEN; biến này đè lên đăng nhập của các tài khoản Claude. "
                                       f"Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart", ctx)
        ctx = self.ctx()
        ctx.env = dict(ctx.env, PROFILE_LLM_ENABLED="Yes")
        self.assert_line("profile_llm_off", "[LỖI] Phân tích bằng model: biến môi trường của Terminal bật "
                                            f"PROFILE_LLM_ENABLED. Cách sửa: anh xóa dòng đó rồi chạy: {TB} restart",
                         ctx)
        ctx.env = dict(ctx.env, PROFILE_LLM_ENABLED="false")
        self.assert_line("profile_llm_off", "[ĐẠT] Phân tích bằng model: tắt", ctx)

    def test_data_failures(self) -> None:
        self.make_installed(start=False)
        db = migrations.find_db(self.bot_home)
        con = sqlite3.connect(db)
        con.execute("DELETE FROM d1_migrations WHERE name = '0003_profiles.sql'")
        con.commit()
        con.close()
        self.assert_line("migrations", "[LỖI] Bản cập nhật cơ sở dữ liệu: còn 1 bản chưa áp. Cách sửa: "
                                       f"{TB} restart (máy tự sao lưu trước)")
        shutil.rmtree(self.bot_home / "d1")
        self.assert_line("database", f"[CHƯA LÀM] Cơ sở dữ liệu: chưa tạo. Cách sửa: {TB} install --only migrations")
        self.assert_line("migrations", "[CHƯA LÀM] Bản cập nhật cơ sở dữ liệu: chưa có cơ sở dữ liệu. Cách sửa: "
                                       f"{TB} install --only migrations")
        folder = self.bot_home / "d1" / "v3" / "d1" / "miniflare-D1DatabaseObject"
        folder.mkdir(parents=True)
        (folder / ("a" * 64 + ".sqlite")).write_bytes(b"not sqlite")
        self.assert_line("migrations", "[CHÚ Ý] Bản cập nhật cơ sở dữ liệu: không đọc được danh sách đã áp.")
        backup = self.bot_home / "backups" / "20261112-100000-manual" / "backup.json"
        data = json.loads(backup.read_text())
        data["created_at"] = (datetime.now().astimezone() - timedelta(days=9)).isoformat(timespec="seconds")
        backup.write_text(json.dumps(data))
        self.assert_line("last_backup", f"[CHÚ Ý] Sao lưu: bản sao lưu mới nhất đã 9 ngày. Cách sửa: {TB} backup")
        shutil.rmtree(self.bot_home / "backups")
        self.assert_line("last_backup", f"[CHÚ Ý] Sao lưu: chưa có bản sao lưu. Cách sửa: {TB} backup")

    def test_journal_checks(self) -> None:
        self.make_installed(start=False)
        p = self.paths()
        state.step_set(p, "history_sync", "pending", "later")
        self.assert_line("history_sync", "[CHƯA LÀM] Tin nhắn cũ: chưa lấy tin nhắn cũ (không bắt buộc). "
                                         f"Cách sửa: {TB} sync-history")
        state.step_set(p, "analyze_contacts", "pending", "exit_1")
        self.assert_line("contacts_analyzed", "[CHƯA LÀM] Phân tích danh bạ: chưa phân tích danh bạ (không bắt buộc). "
                                              f"Cách sửa: {TB} analyze --contacts")
        state.step_set(p, "analyze_visits", "skipped", "no_cache")
        self.assert_line("visits_analyzed", "[BỎ QUA] Phân tích buổi làm: máy chưa có tin nhắn Zalo đã lấy về.")
        state.step_set(p, "analyze_visits", "pending", "server_404")
        self.assert_line("visits_analyzed", "[CHƯA LÀM] Phân tích buổi làm: máy chủ chưa nhận kết quả phân tích buổi "
                                            f"làm. Cách sửa: {TB} continue")
        state.step_set(p, "analyze_visits", "pending", "exit_1")
        self.assert_line("visits_analyzed", "[CHƯA LÀM] Phân tích buổi làm: chưa phân tích buổi làm (không bắt buộc). "
                                            f"Cách sửa: {TB} analyze --visits")
        state.step_set(p, "analyze_visits", "done")
        today = datetime.now().strftime("%d/%m/%Y")
        self.assert_line("visits_analyzed", f"[ĐẠT] Phân tích buổi làm: ngày {today}")
        state.step_set(p, "staff_token", "pending", "later")
        self.assert_line("staff_token_step", "[CHƯA LÀM] Mã nhân viên trong console: chưa đưa mã nhân viên vào "
                                             f"console. Cách sửa: {TB} staff-token")


class MachineTest(DoctorFixture, InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.stub_wp2()
        self.install_release("1.4.0")

    def test_machine_lines(self) -> None:
        self.behave(system={"macos": "13.4"})
        self.assert_line("macos", "[LỖI] Hệ điều hành: macOS 13.4, chatbot cần 13.5 trở lên. Cách sửa: anh cập nhật "
                                  "macOS trong Cài đặt hệ thống rồi chạy lại.")
        self.behave(system={"macos": "26.1", "cpu": "x64"})
        self.assert_line("macos", "[ĐẠT] Hệ điều hành: macOS 26.1")
        self.assert_line("cpu", "[CHÚ Ý] Chip: máy Intel chưa được chạy thử. Cách sửa: nếu gặp lỗi, anh gửi kết quả "
                                "lệnh này cho người phụ trách.")
        self.assertTrue(doctor.passes(self.ctx(), {"cpu"}))  # a warning passes a step check
        self.behave(system={"os": "Linux", "cpu": "x64"})
        with mock.patch.object(platforms, "PROC_VERSION", self.tmp / "no-proc-version"):
            self.assert_line("macos", "[LỖI] Hệ điều hành: Linux chưa được hỗ trợ. Cách sửa: chatbot chỉ chạy trên máy "
                                      "Mac.")
        self.behave(system={"os": "MINGW64_NT-10.0", "cpu": "x64"})
        self.assert_line("macos", "[LỖI] Hệ điều hành: Windows chưa được hỗ trợ. Cách sửa: chatbot chỉ chạy trên máy "
                                  "Mac.")
        self.behave(system={"os": "Darwin", "macos": "15.1", "cpu": "arm64"})
        with mock.patch.object(platforms, "free_gb", lambda path: 2.6):
            self.assert_line("disk", "[LỖI] Dung lượng trống: chỉ còn 2 GB, cần ít nhất 3 GB. Cách sửa: anh xóa bớt "
                                     "tệp rồi chạy lại.")
        with mock.patch.object(platforms, "free_gb", lambda path: 120.9):
            self.assert_line("disk", "[ĐẠT] Dung lượng trống: 120 GB")
        tools = self.tmp / "tools"
        tools.mkdir()
        for name in doctor.SYSTEM_TOOLS:
            if name not in ("hdiutil", "sips"):
                (tools / name).write_text("#!/bin/sh\n")
                (tools / name).chmod(0o755)
        with mock.patch.object(doctor, "SYSTEM_TOOL_DIRS", (str(tools),)):
            self.assert_line("system_tools", "[LỖI] Công cụ của macOS: thiếu sips, hdiutil. Cách sửa: đây là lỗi lạ "
                                             "trên macOS; anh báo người phụ trách.")
        self.assert_line("system_tools", "[ĐẠT] Công cụ của macOS: đủ")
        # A check that raises gives a failure line and exit 2, and the other lines still print.
        with mock.patch.object(doctor.BY_ID["disk"], "fn", side_effect=RuntimeError("boom-detail")):
            code, out = self.run_doctor(only={"macos", "disk"})
        self.assertEqual(code, 2)
        self.assertEqual(out.splitlines(), ["[ĐẠT] Hệ điều hành: macOS 15.1",
                                            "[LỖI] Dung lượng trống: kiểm tra này gặp lỗi lạ (RuntimeError). Cách sửa: "
                                            "anh báo người phụ trách."])
        self.assertNotIn("boom-detail", out)

    def test_lock_moved_out_and_other_stack(self) -> None:
        p = self.paths()
        self.assert_line("install_lock", "[ĐẠT] Lệnh cài khác: không có")
        with state.InstallLock(p):
            self.assert_line("install_lock", "[ĐẠT] Lệnh cài khác: không có")  # held by this command (rev F3)
        holder = subprocess.Popen(
            [sys.executable, "-c", textwrap.dedent(f"""
                import sys, time
                sys.path.insert(0, {str(Path(doctor.__file__).parent.parent)!r})
                from thomhouse_installer import paths, state
                with state.InstallLock(paths.resolve(code_root=__import__("pathlib").Path({str(p.code_root)!r}))):
                    print("held", flush=True)
                    time.sleep(60)
            """)], stdout=subprocess.PIPE, text=True, env=dict(os.environ))
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        self.assert_line("install_lock", "[LỖI] Lệnh cài khác: một lệnh cài hoặc cập nhật khác đang chạy. Cách sửa: "
                                         "anh chờ lệnh đó xong rồi chạy lại.")
        self.assertFalse(doctor.passes(self.ctx(), {"install_lock"}))
        holder.kill()
        state.set_moved_out(p, {"at": "2026-11-12T10:00:00+07:00", "image_name": "x.dmg", "image_sha256": "0" * 64})
        self.assert_line("moved_out", "[LỖI] Máy đã chuyển đi: dữ liệu của máy này đã chuyển sang máy khác ngày "
                                      f"12/11/2026. Cách sửa: đừng bật chatbot ở đây; muốn chạy lại trên máy này: "
                                      f"{TB} move-back")
        state.clear_moved_out(p)
        other = self.make_checkout("other-checkout")
        run_dir = self.bot_home / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        sleeper = subprocess.Popen([sys.executable, "-c", "import sys, time; time.sleep(float(sys.argv[1]))", "60",
                                    f"{other}/apps/server/"], start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        (run_dir / "server.pid").write_text(f"{sleeper.pid}\n")
        self.behave(lsof={"cwd": {str(sleeper.pid): str(other / "apps" / "server")}, "no_real_cwd": True})
        self.assert_line("other_stack", f"[LỖI] Bản chatbot khác: một bản chatbot khác ({other}) đang chạy với cùng dữ "
                                        "liệu. Cách sửa: anh tắt bản đó bằng scripts/stop_local.sh trong thư mục đó.")

    def test_claude_pool_and_login_variants(self) -> None:
        self.write_pool({"label": "main", "priority": 1}, {"label": "acc2", "priority": 2},
                        logins={"main": "max", "acc2": "max"},
                        pool_state={"acc2": {"status": "login_expired"}})
        self.assert_line("claude_pool", "[CHÚ Ý] Tài khoản Claude của chatbot: tài khoản acc2 đang tạm ngừng.")
        self.write_pool({"label": "main", "priority": 1}, logins={"main": "max"},
                        pool_state={"main": {"status": "blocked"}})
        self.assert_line("claude_pool", "[LỖI] Tài khoản Claude của chatbot: chưa có tài khoản Claude nào dùng được. "
                                        f"Cách sửa: {TB} login-claude")
        self.write_pool({"label": "main", "enabled": False}, logins={"main": "api_key"})
        self.assert_line("claude_login", "[LỖI] Đăng nhập Claude: tài khoản main đăng nhập bằng khóa API, không phải "
                                         f"gói Claude. Cách sửa: {TB} login-claude main")
        self.write_pool({"label": "main"}, logins={"main": "null"})
        self.assert_line("claude_login", "[CHÚ Ý] Đăng nhập Claude: tài khoản main có thể không có gói Claude.")
        self.assert_line("claude_pool", "[ĐẠT] Tài khoản Claude của chatbot: 1 tài khoản dùng được")
        (self.bot_home / "accounts.json").unlink()
        self.assert_line("claude_login", "[CHƯA LÀM] Đăng nhập Claude: chưa có tài khoản Claude nào cho chatbot. "
                                         f"Cách sửa: {TB} login-claude")
        # The pool is read once per call: one claude auth status per account.
        self.write_pool({"label": "main"}, {"label": "acc2", "priority": 2}, logins={"main": "max", "acc2": "max"})
        before = len(self.calls("claude"))
        doctor.run_checks(self.ctx(), only={"claude_pool", "claude_login"})
        self.assertEqual(len(self.calls("claude")) - before, 2)

    def test_two_bot_homes_in_one_process(self) -> None:
        self.write_pool({"label": "main"}, logins={"main": "max"})
        first = self.ctx()
        other = self.tmp / "bot-two"
        env = dict(os.environ, THOMHOUSE_BOT_HOME=str(other))
        with mock.patch.dict(os.environ, env):
            second = self.ctx()
        other.mkdir()
        (other / "accounts.json").write_text(json.dumps([{"label": "x1", "config_dir": None, "priority": 1,
                                                          "enabled": False}]))
        self.assertEqual(doctor.line(doctor.run_checks(first, only={"claude_pool"})[0]),
                         "[ĐẠT] Tài khoản Claude của chatbot: 1 tài khoản dùng được")
        self.assertEqual(doctor.run_checks(second, only={"claude_pool"})[0].status, "todo")
        self.assertEqual(doctor.run_checks(first, only={"claude_pool"})[0].status, "pass")
        self.assertFalse([m for m in sys.modules if "claude_pool" in m])


class CheckoutTest(DoctorFixture, InstallerTestCase):
    def test_checkout_mode(self) -> None:
        self.stub_wp2()
        root = self.make_checkout()
        ctx = self.ctx(root)
        self.assertEqual(ctx.paths.mode, "checkout")
        results = {r.id: r for r in doctor.run_checks(ctx)}
        skipped = {"release", "release_files", "release_clean", "deps_workspace", "deps_engine", "deps_rooms",
                   "menu_slides", "paths_current", "history_sync", "contacts_analyzed", "visits_analyzed",
                   "staff_token_step"}
        for check_id in skipped:
            self.assertEqual(doctor.line(results[check_id]),
                             f"[BỎ QUA] {t('doctor.label_' + check_id)}: máy phát triển")
        self.assertEqual(results["python"].status, "pass")
        self.assertEqual(results["python"].detail, f"{sys.version_info.major}.{sys.version_info.minor}."
                                                    f"{sys.version_info.micro}")
        self.assertEqual(doctor.line(results["node"]), "[ĐẠT] Node.js: 24.19.0")
        self.assertEqual(doctor.line(results["pnpm"]), "[ĐẠT] pnpm: 10.32.1")
        self.assertEqual(doctor.line(results["claude_cli"]), "[ĐẠT] Claude Code: 2.1.319")
        self.assertEqual(doctor.line(results["processes"]),
                         "[LỖI] Các phần của chatbot: server, cron, runner, bridge, console chưa chạy. Cách sửa: "
                         "scripts/start_local.sh")
        self.assertEqual(results["last_backup"].fix, f"{CHECKOUT_TB} backup")
        self.assertEqual(results["claude_login"].fix, t("doctor.see_docs"))
        self.assertEqual(results["env_files"].fix, t("doctor.see_docs"))
        for r in results.values():
            if r.fix and CHECKOUT_TB in r.fix:
                command = r.fix.split(CHECKOUT_TB, 1)[1].split()[0]
                self.assertIn(command, CHECKOUT_ALLOWED, r.id)
            self.assertNotIn("~/ThomHouse/bin/thomhouse", r.fix or "", r.id)
        # Checkout rules of 16.5 for Node.js and pnpm.
        self.behave(node={"version": "v22.10.0"}, pnpm={"version": "10.30.0"})
        self.assert_line("node", "[CHÚ Ý] Node.js: bản 22.10.0 cũ hơn bản đã thử (22.19.0).", self.ctx(root))
        self.assert_line("pnpm", "[CHÚ Ý] pnpm: bản 10.30.0 khác bản ghi trong package.json (10.32.1).",
                         self.ctx(root))
        self.behave(node={"version": "v22.19.0"}, pnpm={"version": "9.1.0"})
        self.assert_line("node", "[CHÚ Ý] Node.js: bản 22.19.0; phòng chat hai bot cần Node.js 24 trở lên.",
                         self.ctx(root))
        self.assert_line("pnpm", "[LỖI] pnpm: chưa có bản 10.32.1. Cách sửa: xem hướng dẫn trong docs/run-local.md",
                         self.ctx(root))
        self.behave(node={"version": "v20.1.0"})
        self.assert_line("node", "[LỖI] Node.js: bản 20.1.0 cũ hơn bản chatbot cần (22.19.0). Cách sửa: xem hướng dẫn "
                                 "trong docs/run-local.md", self.ctx(root))
        # Only BOT_HOME folders are checked for permissions; the restart fix uses the scripts.
        self.bot_home.mkdir(parents=True, exist_ok=True)
        self.bot_home.chmod(0o755)
        self.assert_line("permissions", "[LỖI] Quyền thư mục: ~/.thomhouse-bot cho người khác đọc được. Cách sửa: xem "
                                        "hướng dẫn trong docs/run-local.md", self.ctx(root))
        ctx = self.ctx(root)
        ctx.env = dict(ctx.env, ANTHROPIC_API_KEY="planted-api-key-0003")
        self.assert_line("no_api_key", "[LỖI] Khóa API Anthropic: biến môi trường của Terminal đặt ANTHROPIC_API_KEY; "
                                       "chatbot chỉ dùng gói Claude. Cách sửa: anh xóa dòng đó rồi chạy: "
                                       "scripts/stop_local.sh; scripts/start_local.sh", ctx)

    def test_checkout_python_skips_the_macos_shim(self) -> None:
        root = self.make_checkout()
        empty = self.tmp / "emptybin"
        empty.mkdir()
        os.environ["PATH"] = f"{empty}:/usr/bin:/bin"
        ctx = self.ctx(root)
        calls = []
        real_run = doctor.proc.run

        def spy(c, cmd, **kw):
            calls.append(list(cmd))
            return real_run(c, cmd, **kw)

        with mock.patch.object(doctor.proc, "run", spy):
            result = self.check("python", ctx)
        self.assertNotIn(["/usr/bin/python3", "--version"], calls)
        if result.status == "fail":
            self.assertEqual(doctor.line(result), "[LỖI] Python: chưa có Python 3.11 trở lên trên PATH. Cách sửa: xem "
                                                  "hướng dẫn trong docs/run-local.md")
