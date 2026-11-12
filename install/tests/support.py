"""Test support for every installer package (16.10).

`InstallerTestCase` gives each test a temporary folder with its own HOME, THOMHOUSE_APP_HOME, THOMHOUSE_BOT_HOME and
ZALO_CONFIG_DIR, the fake binaries of `install/tests/fake_bin` first on PATH, proxy variables that point at a dead
loopback port (so a real network call fails), `no_proxy=127.0.0.1,localhost`, and a loopback stub server for
`/health`, `/staff/*` and `/runner/*`. `os.environ` is replaced by that environment for the whole test, because
`proc.child_env()` builds every child environment from it. A test fails at once when any of these folders lies
under the real home folder.

`install_release()` copies `install/tests/fake_tree` into `APP_HOME/releases/<ver>` and the real `install/`
(without `install/tests/`) into it, so subprocesses run the real `install/thomhouse.py`; `make_checkout()` does the
same as a checkout (no VERSION.json). The real `scripts/runner/claude_pool.py` and the real bridge modules of
`REAL_BRIDGE_FILES` (the `EnvFile` that move-in merges settings with) are copied in too.

Fakes and stubs record their calls in `<tmp>/calls.jsonl` (`self.calls()`) and read `<tmp>/behaviour.json`
(`self.behave()`); the stub server records request paths in `<tmp>/server-calls.jsonl` (`self.server_calls()`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

INSTALL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = INSTALL_DIR.parent
TESTS_DIR = INSTALL_DIR / "tests"
FAKE_BIN = TESTS_DIR / "fake_bin"
FAKE_TREE = TESTS_DIR / "fake_tree"
REAL_HOME = Path(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir))
DEAD_PROXY = "http://127.0.0.1:9"
SLEEPER_MARK = "time.sleep(float(sys.argv[1]))"
REAL_BRIDGE_FILES = ("envfiles.py", "rooms.py")  # from apps/zalo-bridge/bridge/, beside the fake tree's stubs

if str(INSTALL_DIR) not in sys.path:
    sys.path.insert(0, str(INSTALL_DIR))

DEFAULT_ROUTES: dict[str, list] = {
    "GET /health": [200, {"ok": True, "env": "dev", "zalo_mode": "personal"}],
    "GET /staff/flags": [200, {"flags": {"ai_engine": "subscription", "auto_reply_mode": "approve_each",
                                         "outbound_enabled": True}, "updated": {}}],
    "GET /staff/runner": [200, {"runners": [{"runner_id": "mac-local-1", "online": True, "last_seen_at": 0,
                                             "last_claim_at": None, "status": None, "last_error": None}],
                                "desired_account": None, "queue": {"queued": 0, "leased": 0}}],
    "GET /staff/roles": [200, {"roles": [{"zalo_user_id": "999000111", "role": "customer"}]}],
    "GET /staff/chat-facts/eligible": [200, {"conversations": []}],
    "POST /staff/chat-facts/import": [200, {"ok": True}],
    "GET /": [200, "<!doctype html><title>console</title>"],
}


def is_under(path: Path | str, parent: Path | str) -> bool:
    """True when `path` (after resolving symlinks) is `parent` or inside it."""
    p = os.path.realpath(str(path))
    q = os.path.realpath(str(parent))
    return p == q or p.startswith(q.rstrip("/") + "/")


class StubServer:
    """A stdlib HTTP server on 127.0.0.1 (port 0) answering from `<tmp>/server.json`.

    Routes are "METHOD /path" -> [status, body]; a str body is sent as text/html, anything else as JSON. Every
    `/runner/*` request without `X-Runner-Id` gets 400 like `requireRunner`. Every request is recorded in
    `<tmp>/server-calls.jsonl` as {"method", "path", "auth", "runner_id"} (whether those headers were present).
    """

    def __init__(self, tmp: Path) -> None:
        self.data_file = tmp / "server.json"
        self.calls_file = tmp / "server-calls.jsonl"
        self.data_file.write_text(json.dumps({"routes": {}}), encoding="utf-8")
        self.calls_file.write_text("", encoding="utf-8")
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silence
                pass

            def _handle(self) -> None:
                path = urlsplit(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                server._record(self.command, path, self.headers)
                if path.startswith("/runner/") and not self.headers.get("X-Runner-Id"):
                    self._send(400, {"error": "bad_request", "message": "X-Runner-Id header required"})
                    return
                status, body = server.route(f"{self.command} {path}")
                self._send(status, body)

            def _send(self, status: int, body: object) -> None:
                if isinstance(body, str):
                    raw, ctype = body.encode("utf-8"), "text/html; charset=utf-8"
                else:
                    raw, ctype = json.dumps(body).encode("utf-8"), "application/json"
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def start(self) -> "StubServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def set_route(self, route: str, status: int, body: object = None) -> None:
        """Answer `route` ("GET /path") with `status` and `body` from now on."""
        with self._lock:
            data = json.loads(self.data_file.read_text(encoding="utf-8"))
            data["routes"][route] = [status, body if body is not None else {}]
            self.data_file.write_text(json.dumps(data), encoding="utf-8")

    def route(self, route: str) -> tuple[int, object]:
        with self._lock:
            data = json.loads(self.data_file.read_text(encoding="utf-8"))
        found = data["routes"].get(route) or DEFAULT_ROUTES.get(route)
        if found is None:
            return 404, {"error": "not_found"}
        return int(found[0]), found[1]

    def _record(self, method: str, path: str, headers) -> None:
        entry = {"method": method, "path": path, "auth": bool(headers.get("Authorization")),
                 "runner_id": bool(headers.get("X-Runner-Id"))}
        with self._lock, open(self.calls_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def _copy_install(dest: Path) -> None:
    """Copy the real install/ (without tests and caches) to dest/install."""

    def ignore(folder: str, names: list[str]) -> set[str]:
        skip = {n for n in names if n == "__pycache__" or n.endswith(".pyc") or n == ".DS_Store"}
        if os.path.realpath(folder) == os.path.realpath(str(INSTALL_DIR)):
            skip.add("tests")
        return skip

    shutil.copytree(INSTALL_DIR, dest / "install", ignore=ignore, dirs_exist_ok=True)


def write_manifest(root: Path, runtime_written: tuple[str, ...] = ()) -> None:
    """MANIFEST.json and MANIFEST.sha256 of every file under `root` (16.2.5), as make_release.py writes them."""
    entries = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and d != "node_modules")
        for name in sorted(files):
            full = Path(folder) / name
            rel = full.relative_to(root).as_posix()
            if rel in ("MANIFEST.json", "MANIFEST.sha256") or full.is_symlink():
                continue
            data = full.read_bytes()
            mode = "0755" if os.access(full, os.X_OK) else "0644"
            entries.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                            "mode": mode, "runtime_written": rel in runtime_written})
    entries.sort(key=lambda e: e["path"])
    (root / "MANIFEST.json").write_text(json.dumps({"schema": 1, "files": entries}, indent=1), encoding="utf-8")
    (root / "MANIFEST.sha256").write_text("".join(f"{e['sha256']}  {e['path']}\n" for e in entries),
                                          encoding="utf-8")


def copy_real_bridge(root: Path) -> None:
    """Copy the real bridge modules of REAL_BRIDGE_FILES into the tree at `root`."""
    target = root / "apps" / "zalo-bridge" / "bridge"
    target.mkdir(parents=True, exist_ok=True)
    for name in REAL_BRIDGE_FILES:
        shutil.copy2(PROJECT_ROOT / "apps" / "zalo-bridge" / "bridge" / name, target / name)


class InstallerTestCase(unittest.TestCase):
    """Base class of every installer test. Subclasses may set FAKE_DIRS to put their own fakes before fake_bin."""

    FAKE_DIRS: tuple[Path, ...] = ()

    def setUp(self) -> None:
        super().setUp()
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="thomhouse-test-")))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.app_home = self.home / "ThomHouse"
        self.bot_home = self.home / ".thomhouse-bot"
        self.zalo_config = self.home / ".zalo-agent-cli"
        self.fixtures = self.tmp / "fixtures"
        self.pybin = self.tmp / "pybin"
        for folder in (self.home, self.fixtures, self.pybin, self.tmp / "tmp"):
            folder.mkdir(parents=True, exist_ok=True)
        self.assert_not_real_home(self.tmp, self.home, self.app_home, self.bot_home, self.zalo_config)
        (self.tmp / ".installer-test").write_text("", encoding="utf-8")
        (self.tmp / "behaviour.json").write_text("{}", encoding="utf-8")
        (self.tmp / "calls.jsonl").write_text("", encoding="utf-8")
        (self.pybin / "python3").symlink_to(sys.executable)
        installer = (FAKE_BIN / "fake_installer.sh").read_text(encoding="utf-8")
        target = self.fixtures / "install.sh"
        target.write_text(installer.replace("@FAKE_BIN@", str(FAKE_BIN)), encoding="utf-8")
        target.chmod(0o755)
        self.server = StubServer(self.tmp).start()
        self.addCleanup(self.server.stop)
        path = [str(d) for d in self.FAKE_DIRS] + [str(FAKE_BIN), str(self.pybin), "/usr/bin", "/bin", "/usr/sbin",
                                                    "/sbin"]
        self.env: dict[str, str] = {
            "HOME": str(self.home),
            "USER": "tester",
            "LOGNAME": "tester",
            "LANG": "en_US.UTF-8",
            "TERM": "dumb",
            "TMPDIR": str(self.tmp / "tmp"),
            "PATH": os.pathsep.join(path),
            # The header, bootstrap.sh and the launcher use this in place of /usr/bin:/bin:/usr/sbin:/sbin, so the
            # shell files of every package's tests run the fakes, never the real curl or uname.
            "THOMHOUSE_TOOL_PATH": os.pathsep.join(path),
            "THOMHOUSE_APP_HOME": str(self.app_home),
            "THOMHOUSE_BOT_HOME": str(self.bot_home),
            "ZALO_CONFIG_DIR": str(self.zalo_config),
            "THOMHOUSE_TEST_DIR": str(self.tmp),
            "THOMHOUSE_FAKE_BIN": str(FAKE_BIN),
            "THOMHOUSE_SERVER_URL": self.server.url,
            "THOMHOUSE_CONSOLE_URL": self.server.url,
            "THOMHOUSE_CLIPBOARD_CLEAR_S": "1",
            "THOMHOUSE_HEALTH_WAIT_S": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "http_proxy": DEAD_PROXY,
            "https_proxy": DEAD_PROXY,
            "HTTP_PROXY": DEAD_PROXY,
            "HTTPS_PROXY": DEAD_PROXY,
            "ALL_PROXY": DEAD_PROXY,
            "no_proxy": "127.0.0.1,localhost",
        }
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._kill_leftovers)

    # ------------------------------------------------------------ guards and environment

    def assert_not_real_home(self, *paths: Path | str) -> None:
        """Fail the test when any path lies under the real home folder."""
        for p in paths:
            if is_under(p, REAL_HOME):
                self.fail(f"test path {p} lies under the real home folder")

    def env_without_no_proxy(self) -> dict[str, str]:
        """The test environment without no_proxy and NO_PROXY (for the proxy tests, rev F4)."""
        env = dict(self.env)
        env.pop("no_proxy", None)
        env.pop("NO_PROXY", None)
        return env

    def behave(self, **sections: dict) -> None:
        """Merge `sections` (tool name -> settings) into `<tmp>/behaviour.json`; use "zalo_agent" for "zalo-agent"."""
        path = self.tmp / "behaviour.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for name, settings in sections.items():
            key = "zalo-agent" if name == "zalo_agent" else name
            data.setdefault(key, {}).update(settings)
        path.write_text(json.dumps(data), encoding="utf-8")

    def calls(self, tool: str | None = None) -> list[dict]:
        """Recorded calls of the fakes and stubs, optionally of one tool."""
        out = []
        for line in (self.tmp / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if tool is None or entry.get("tool") == tool:
                    out.append(entry)
        return out

    def server_calls(self) -> list[dict]:
        """Requests the stub server received."""
        lines = self.server.calls_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]

    # ------------------------------------------------------------ trees

    def _fill_tree(self, root: Path) -> None:
        shutil.copytree(FAKE_TREE, root, dirs_exist_ok=True, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        _copy_install(root)
        pool = PROJECT_ROOT / "scripts" / "runner" / "claude_pool.py"
        (root / "scripts" / "runner").mkdir(parents=True, exist_ok=True)
        shutil.copy2(pool, root / "scripts" / "runner" / "claude_pool.py")
        copy_real_bridge(root)

    def install_release(self, version: str = "1.4.0", *, link_app: bool = True, menu_id: str = "0" * 16) -> Path:
        """A fake release at APP_HOME/releases/<version> with VERSION.json and MANIFEST files; with `link_app`,
        APP_HOME/app links to it (relative link). Returns the release folder."""
        root = self.app_home / "releases" / version
        root.mkdir(parents=True, exist_ok=True)
        self._fill_tree(root)
        (root / "VERSION.json").write_text(
            json.dumps({"schema": 1, "version": version, "menu_id": menu_id}), encoding="utf-8")
        write_manifest(root)
        if link_app:
            app = self.app_home / "app"
            if app.is_symlink() or app.exists():
                app.unlink()
            app.symlink_to(Path("releases") / version)
        return root

    def make_checkout(self, name: str = "checkout") -> Path:
        """A fake project checkout (no VERSION.json) at <tmp>/<name>."""
        root = self.tmp / name
        root.mkdir(parents=True, exist_ok=True)
        self._fill_tree(root)
        return root

    # ------------------------------------------------------------ installer objects

    def paths(self, code_root: Path | None = None):
        """`paths.resolve()` for the test environment; `code_root` defaults to APP_HOME/app."""
        from thomhouse_installer import paths as paths_mod

        root = code_root if code_root is not None else self.app_home / "app"
        return paths_mod.resolve(os.environ, code_root=root)

    def ctx(self, code_root: Path | None = None, *, interactive: bool = False, **attrs: object):
        """A `Ctx` for the test environment; `attrs` become Namespace attributes (yes, dry_run, quiet, ...)."""
        from thomhouse_installer import context

        ns = {"command": "test", "yes": False, "dry_run": False, "quiet": False, "offline": False, "json": False}
        ns.update(attrs)
        ctx = context.make_ctx(argparse.Namespace(**ns), env=dict(os.environ), paths=self.paths(code_root))
        ctx.interactive = interactive
        return ctx

    def run_cli(self, code_root: Path | None, *args: str, cwd: str = "/", input: str | None = None,
                env: dict[str, str] | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
        """Run `python3 -I <code_root>/install/thomhouse.py <args>` as a subprocess (cwd "/" by default).

        With `input` None, stdin is /dev/null: a command that asks never waits for the keyboard of the test run."""
        root = code_root if code_root is not None else self.app_home / "app"
        cmd = [sys.executable, "-I", str(root / "install" / "thomhouse.py"), *args]
        stdin = subprocess.DEVNULL if input is None else None
        return subprocess.run(cmd, cwd=cwd, input=input, stdin=stdin, env=env if env is not None else dict(self.env),
                              capture_output=True, text=True, timeout=timeout)

    # ------------------------------------------------------------ cleanup

    def _kill_leftovers(self) -> None:
        """Kill every sleeper or fake that a test left running (only processes that belong to this test)."""
        pids: set[int] = set()
        run_dir = self.bot_home / "run"
        if run_dir.is_dir():
            for f in run_dir.glob("*.pid"):
                text = f.read_text(encoding="utf-8").strip()
                if text.isdigit():
                    pids.add(int(text))
        try:
            ps = subprocess.run(["/bin/ps", "-ax", "-o", "pid=,command="], capture_output=True, text=True,
                                timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            ps = ""
        table = {}
        for line in ps.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                table[int(parts[0])] = parts[1]
        for pid, command in table.items():
            if str(self.tmp) in command:
                pids.add(pid)
        for pid in pids:
            command = table.get(pid, "")
            if pid == os.getpid() or not (str(self.tmp) in command or SLEEPER_MARK in command):
                continue
            for target in (lambda: os.killpg(pid, signal.SIGKILL), lambda: os.kill(pid, signal.SIGKILL)):
                try:
                    target()
                    break
                except (ProcessLookupError, PermissionError):
                    continue
