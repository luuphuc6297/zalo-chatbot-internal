"""Helpers of the release tests (WP2): fixture runtimes, test pins, throwaway signing keys, a temporary project to
build releases from, builds cached for the whole test run, and running shell files with or without a terminal.

Nothing here touches the real home folder or the network. A build runs the project's real
`scripts/release/make_release.py` on a temporary copy of the project (the fake tree, the real `install/` without
tests, the real `scripts/release/`, stubs for the other allowlisted files) with the documented test-only pins
(`THOMHOUSE_RELEASE_TEST_PINS`, `"hash_source": "test"`). The integration step can build the same way with
`built_release()`.

The probe steps.py (`STEPS_STUB`) records how the header and bootstrap.sh reached the CLI (argv, environment, the
bootstrap lock); the WP2 tests that check that passing use it. Builds with `real_steps=True` ship the real steps.py
and run the real install chain (the dry-run plan and the integration tests).
"""

from __future__ import annotations

import atexit
import gzip
import hashlib
import io
import json
import os
import pty
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from tests.support import FAKE_BIN, FAKE_TREE, INSTALL_DIR, PROJECT_ROOT, InstallerTestCase, copy_real_bridge

RELEASE_SCRIPTS = PROJECT_ROOT / "scripts" / "release"
MAKE_RELEASE = "scripts/release/make_release.py"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
PY_VERSION = "3.14.6"
NODE_VERSION = "24.19.0"
PNPM_VERSION = "10.32.1"
CLAUDE_VERSION = "2.1.319"
PY_NAME = f"cpython-{PY_VERSION}+20260101-aarch64-apple-darwin-install_only.tar.gz"
PY_URL = f"https://github.com/astral-sh/python-build-standalone/releases/download/20260101/{PY_NAME}"
NODE_NAME = f"node-v{NODE_VERSION}-darwin-arm64.tar.gz"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_NAME}"
STUBS = {
    "apps/server/src/index.ts": "export default {};\n",
    "apps/server/src/seed-data.ts": "export const SEED = [];\n",
    "apps/server/scripts/check.mjs": "console.log('ok');\n",
    "apps/server/tsconfig.json": "{}\n",
    "apps/server/wrangler.toml": 'name = "thomhouse-bot"\n',
    "apps/server/.dev.vars.example": "RUNNER_TOKEN=\nSTAFF_TOKEN=\n",
    "apps/console/src/main.tsx": "export {};\n",
    "apps/console/index.html": "<!doctype html>\n",
    "apps/console/tsconfig.json": "{}\n",
    "apps/console/vite.config.ts": "export default {};\n",
    "apps/console/.env.example": "VITE_SERVER_URL=\n",
    "apps/desktop/main.js": "// stub\n",
    "apps/desktop/preload.js": "// stub\n",
    "apps/desktop/package.json": '{"name": "desktop", "private": true}\n',
    "apps/runner/runner/__init__.py": "",
    "scripts/seed_dev.py": "",
    "scripts/import_visits.py": "",
    "scripts/visit_rules.py": "",
    "scripts/contact_facts_rules.py": "",
    "scripts/visit_model_pass.py": "",
    "data/reply-templates.json": "{}\n",
    "docs/cai-dat-may-moi.md": "# Cài đặt chatbot thom house trên máy mới\n",
}
STEPS_STUB = '''"""Probe in place of steps.py in the WP2 tests: records how the CLI was reached."""
import json
import os
import sys


def _record(name, ctx, args):
    entry = {
        "tool": "steps." + name,
        "argv": sys.argv[1:],
        "pid": os.getpid(),
        "dry_run": bool(args.dry_run),
        "consented": list(getattr(args, "consented", None) or []),
        "release_file": str(getattr(args, "release_file", None) or ""),
        "from_bootstrap": bool(getattr(args, "from_bootstrap", False)),
        "yes": bool(getattr(args, "yes", False)),
        "lock_dir": os.path.exists(str(ctx.paths.bootstrap_lock_dir)),
        "code_root": str(ctx.paths.code_root),
        "env": {k: os.environ.get(k) for k in ("PATH", "no_proxy", "NO_PROXY", "DISABLE_UPDATES",
                                               "PROFILE_LLM_ENABLED", "THOMHOUSE_APP_HOME", "THOMHOUSE_BOT_HOME",
                                               "ANTHROPIC_API_KEY", "LANG")},
    }
    with open(os.path.join(os.environ["THOMHOUSE_TEST_DIR"], "calls.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\\n")
    return 0


def cmd_install(ctx, args):
    return _record("cmd_install", ctx, args)


def cmd_continue(ctx, args):
    return _record("cmd_continue", ctx, args)
'''


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tar_gz(members: dict[str, tuple[bytes, int]]) -> bytes:
    """A deterministic tar.gz of `members` (path -> (bytes, mode))."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in sorted(members):
            data, mode = members[path]
            info = tarfile.TarInfo(path)
            info.size, info.mtime, info.mode = len(data), 0, mode
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def python_wrapper(reported: str = PY_VERSION) -> bytes:
    """A stand-in `python3`: prints `Python <reported>` for --version and runs the test's own Python otherwise."""
    return (f'#!/bin/sh\ncase "${{1:-}}" in --version | -V) echo "Python {reported}"; exit 0 ;; esac\n'
            f'exec "{sys.executable}" "$@"\n').encode("utf-8")


def node_wrapper(version: str = NODE_VERSION) -> bytes:
    return f'#!/bin/sh\nTHOMHOUSE_FAKE_NODE_VERSION=v{version} exec "{FAKE_BIN}/node" "$@"\n'.encode("utf-8")


def npm_wrapper() -> bytes:
    return f'#!/bin/sh\nexec "{FAKE_BIN}/npm" "$@"\n'.encode("utf-8")


def python_archive(reported: str = PY_VERSION) -> bytes:
    return tar_gz({"python/bin/python3": (python_wrapper(reported), 0o755),
                   "python/lib/README": (b"stand-in\n", 0o644)})


def node_archive(version: str = NODE_VERSION) -> bytes:
    top = f"node-v{version}-darwin-arm64"
    return tar_gz({f"{top}/bin/node": (node_wrapper(version), 0o755), f"{top}/bin/npm": (npm_wrapper(), 0o755)})


def claude_binary(version: str = CLAUDE_VERSION, marker: str | None = None) -> bytes:
    """The bytes the fake `claude install <version>` writes to ~/.local/share/claude/versions/<version>."""
    text = "#!/bin/sh\n# fake claude %s\n" % version
    if marker:
        text += "# %s\n" % marker
    text += 'THOMHOUSE_FAKE_CLAUDE_VERSION=%s exec "%s/claude" "$@"\n' % (version, FAKE_BIN)
    return text.encode("utf-8")


def pnpm_lock(version: str = PNPM_VERSION) -> str:
    lock = {"name": "thomhouse-pnpm", "lockfileVersion": 3, "requires": True,
            "packages": {"": {"name": "thomhouse-pnpm", "dependencies": {"pnpm": version}},
                         "node_modules/pnpm": {"version": version,
                                               "resolved": f"https://registry.npmjs.org/pnpm/-/pnpm-{version}.tgz",
                                               "integrity": "sha512-ZmFrZQ=="}}}
    return json.dumps(lock, indent=1) + "\n"


def make_pins(python_bytes: bytes, node_bytes: bytes, *, claude_sha: str | None = "auto") -> dict:
    """versions.json with "hash_source": "test" and the fixture runtimes as the darwin-arm64 pins."""
    data = json.loads((INSTALL_DIR / "versions.json").read_text(encoding="utf-8"))
    data["hash_source"] = "test"
    data["python"]["version"] = PY_VERSION
    data["python"]["platforms"]["darwin-arm64"] = {"url": PY_URL, "sha256": sha256_bytes(python_bytes),
                                                   "bytes": len(python_bytes)}
    data["node"]["version"] = NODE_VERSION
    data["node"]["platforms"]["darwin-arm64"] = {"url": NODE_URL, "sha256": sha256_bytes(node_bytes),
                                                 "bytes": len(node_bytes)}
    data["pnpm"]["bytes"] = 2345678
    binary = claude_binary()
    sha = sha256_bytes(binary) if claude_sha == "auto" else claude_sha
    data["claude_code"]["version"] = CLAUDE_VERSION
    data["claude_code"]["min"] = CLAUDE_VERSION
    data["claude_code"]["platforms"]["darwin-arm64"] = {"sha256": sha, "bytes": len(binary) if sha else None}
    return data


# ---------------------------------------------------------------- the session: keys, fixtures, builds

class Session:
    """Everything built once per test run, in a folder outside every test's temporary home."""

    def __init__(self) -> None:
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="thomhouse-wp2-")))
        atexit.register(shutil.rmtree, str(self.dir), True)
        self.fixtures = self.dir / "fixtures"
        self.fixtures.mkdir()
        self.python_bytes = python_archive()
        self.node_bytes = node_archive()
        (self.fixtures / PY_NAME).write_bytes(self.python_bytes)
        (self.fixtures / NODE_NAME).write_bytes(self.node_bytes)
        self.pins = make_pins(self.python_bytes, self.node_bytes)
        self.pins_file = self.dir / "test-pins.json"
        self.pins_file.write_text(json.dumps(self.pins, indent=1) + "\n", encoding="utf-8")
        self.keys: dict[str, Path] = {}
        self.builds: dict[tuple, Path] = {}

    def key(self, name: str = "main") -> Path:
        if name not in self.keys:
            folder = self.dir / "keys"
            folder.mkdir(exist_ok=True)
            key = folder / name
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "thomhouse-release", "-q", "-f", str(key)],
                           check=True, stdin=subprocess.DEVNULL, capture_output=True)
            self.keys[name] = key
        return self.keys[name]

    def signers_line(self, name: str = "main") -> str:
        kind, blob = (Path(str(self.key(name)) + ".pub").read_text(encoding="utf-8").split()[:2])
        return f'thomhouse-release namespaces="thomhouse-release" {kind} {blob}\n'


_SESSION: Session | None = None


def session() -> Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = Session()
    return _SESSION


def _ignore(folder: str, names: list[str]) -> set[str]:
    skip = {n for n in names if n == "__pycache__" or n.endswith(".pyc") or n == ".DS_Store"}
    if os.path.realpath(folder) == os.path.realpath(str(INSTALL_DIR)):
        skip.add("tests")
    return skip


def make_project(root: Path, *, key: str = "main", steps_stub: bool = True) -> Path:
    """A temporary project that make_release.py can build: the fake tree, the real install/ (without tests) and
    scripts/release/, the real claude_pool.py, stubs for the other allowlisted files, a pnpm lock and the trust of
    the session key `key`. With `steps_stub`, install/thomhouse_installer/steps.py is the probe that records how
    the CLI was reached; without it the real steps.py ships."""
    s = session()
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FAKE_TREE, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(INSTALL_DIR, root / "install", dirs_exist_ok=True, ignore=_ignore)
    shutil.copytree(RELEASE_SCRIPTS, root / "scripts" / "release", dirs_exist_ok=True, ignore=_ignore)
    (root / "scripts" / "runner").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "scripts" / "runner" / "claude_pool.py", root / "scripts" / "runner" / "claude_pool.py")
    copy_real_bridge(root)
    for rel, text in STUBS.items():
        target = root / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    with open(root / "scripts" / "release" / "allowlist.txt", "a", encoding="utf-8") as f:
        f.write("scripts/_teststub.py\n")  # the fake tree's stubs import it
    (root / "install" / "lock" / "pnpm" / "package-lock.json").write_text(pnpm_lock(), encoding="utf-8")
    trust = root / "install" / "trust"
    trust.mkdir(parents=True, exist_ok=True)
    (trust / "allowed_signers").write_text(s.signers_line(key), encoding="utf-8")
    if steps_stub:
        (root / "install" / "thomhouse_installer" / "steps.py").write_text(STEPS_STUB, encoding="utf-8")
    return root


def build_env(home: Path, *, pins: Path | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    s = session()
    tmp = s.dir / "tmp"
    tmp.mkdir(exist_ok=True)
    env = {"HOME": str(home), "PATH": SYSTEM_PATH, "LANG": "en_US.UTF-8", "TMPDIR": str(tmp),
           "PYTHONDONTWRITEBYTECODE": "1", "THOMHOUSE_RELEASE_TEST_PINS": str(pins or s.pins_file)}
    env.update(extra or {})
    return env


def run_make_release(project: Path, *args: str, home: Path, env: dict[str, str] | None = None,
                     timeout: float = 300) -> subprocess.CompletedProcess:
    """`python3 -I <project>/scripts/release/make_release.py <args>` with a temporary HOME and the test pins."""
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, "-I", str(project / MAKE_RELEASE), *args], cwd="/",
                          env=env if env is not None else build_env(home), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=timeout)


def built_release(version: str = "1.4.0", *, key: str = "main", menu: bool = False,
                  real_steps: bool = False) -> Path:
    """The `.command` of a test build (cached for the run); never modify it, copy it first. With `real_steps` the
    build ships the real steps.py instead of the probe."""
    s = session()
    cache_key = (version, key, menu, real_steps)
    if cache_key not in s.builds:
        name = f"{version}-{key}-{'menu' if menu else 'plain'}{'-real' if real_steps else ''}"
        project = make_project(s.dir / f"project-{name}", key=key, steps_stub=not real_steps)
        if menu:
            add_menu(project)
        out = s.dir / f"out-{name}"
        args = ["--version", version, "--out", str(out), "--sign-key", str(s.key(key))]
        res = run_make_release(project, *args, *(["--menu"] if menu else []), home=s.dir / "buildhome")
        if res.returncode != 0:
            raise AssertionError(f"test build failed: {res.stdout}\n{res.stderr}")
        s.builds[cache_key] = out / f"thomhouse-{version}.command"
    return s.builds[cache_key]


def python_variant(version: str) -> tuple[str, bytes]:
    """(file name, bytes) of a fixture Python archive that reports `version` (for a release with another pin)."""
    return (f"cpython-{version}+20260101-aarch64-apple-darwin-install_only.tar.gz", python_archive(version))


def built_variant(version: str, *, migration: str | None = None, python: str | None = None) -> Path:
    """A real-steps test build of `version` with the menu, optionally one more migration file named `migration` and
    a Python pin `python` other than PY_VERSION (its fixture comes from `python_variant`). Cached for the run."""
    s = session()
    cache_key = ("variant", version, migration, python)
    if cache_key not in s.builds:
        name = f"variant-{version}-{migration or 'nomig'}-{python or PY_VERSION}"
        project = make_project(s.dir / f"project-{name}", steps_stub=False)
        add_menu(project)
        if migration:
            (project / "apps" / "server" / "migrations" / migration).write_text(
                "CREATE TABLE IF NOT EXISTS integration_marker (id INTEGER PRIMARY KEY);\n", encoding="utf-8")
        pins_file = s.pins_file
        if python:
            file_name, data = python_variant(python)
            (s.fixtures / file_name).write_bytes(data)
            pins = json.loads(json.dumps(s.pins))
            pins["python"]["version"] = python
            pins["python"]["platforms"]["darwin-arm64"] = {
                "url": f"https://github.com/astral-sh/python-build-standalone/releases/download/20260101/{file_name}",
                "sha256": sha256_bytes(data), "bytes": len(data)}
            pins_file = s.dir / f"test-pins-python-{python}.json"
            pins_file.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")
        out = s.dir / f"out-{name}"
        home = s.dir / "buildhome"
        res = run_make_release(project, "--version", version, "--out", str(out), "--sign-key", str(s.key()), "--menu",
                               home=home, env=build_env(home, pins=pins_file))
        if res.returncode != 0:
            raise AssertionError(f"test build {name} failed: {res.stdout}\n{res.stderr}")
        s.builds[cache_key] = out / f"thomhouse-{version}.command"
    return s.builds[cache_key]


def add_menu(project: Path) -> list[str]:
    """Two indexed slides and one unindexed file under the project's menu folder; returns the indexed paths."""
    base = project / "sources" / "drive-resources" / "thomhouse-menu"
    (base / "facial").mkdir(parents=True, exist_ok=True)
    (base / "facial" / "1.png").write_bytes(b"\x89PNG slide one")
    (base / "facial" / "2.png").write_bytes(b"\x89PNG slide two")
    (base / "facial" / "unindexed.png").write_bytes(b"\x89PNG not in the index")
    files = ["sources/drive-resources/thomhouse-menu/facial/1.png", "sources/drive-resources/thomhouse-menu/facial/2.png"]
    index = {"slides": [{"key": f"facial/{n}", "group": "facial", "n": n, "file": f} for n, f in enumerate(files, 1)]}
    (project / "data" / "menu-images.json").write_text(json.dumps(index), encoding="utf-8")
    return files


def run_tty(cmd: list[str], *, env: dict[str, str], answers: str, cwd: str = "/",
            timeout: float = 120) -> subprocess.CompletedProcess:
    """Run `cmd` with a terminal on stdin (so `[ -t 0 ]` and isatty() are true) and `answers` typed into it."""
    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(cmd, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd)
    finally:
        os.close(slave)
    try:
        os.write(master, answers.encode("utf-8"))
        out, _ = proc.communicate(timeout=timeout)
    finally:
        os.close(master)
    return subprocess.CompletedProcess(cmd, proc.returncode, out.decode("utf-8", errors="replace"), "")


def snapshot(folder: Path) -> dict[str, tuple]:
    """Every entry under `folder` with its type, mode and content digest (or link target)."""
    out: dict[str, tuple] = {}
    if not folder.exists():
        return out
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        st = path.lstat()
        if path.is_symlink():
            out[rel] = ("link", os.readlink(path))
        elif path.is_dir():
            out[rel] = ("dir", st.st_mode & 0o777)
        else:
            out[rel] = ("file", st.st_mode & 0o777, sha256_bytes(path.read_bytes()))
    return out


class ReleaseTestCase(InstallerTestCase):
    """InstallerTestCase plus the session kit: the fixture runtimes in `<tmp>/fixtures`, THOMHOUSE_TOOL_PATH set to
    the test PATH (so the shell files run the fakes, never the real curl), and helpers for release files."""

    def setUp(self) -> None:
        super().setUp()
        self.kit = session()
        for f in self.kit.fixtures.iterdir():
            shutil.copy2(f, self.fixtures / f.name)
        self.env["THOMHOUSE_TOOL_PATH"] = self.env["PATH"]
        os.environ["THOMHOUSE_TOOL_PATH"] = self.env["PATH"]

    # ------------------------------------------------------------ release files
    def release_file(self, version: str = "1.4.0", *, key: str = "main", menu: bool = False,
                     real_steps: bool = False) -> Path:
        """A copy of a cached test build in `<tmp>/usb/` (with the menu archive when `menu`)."""
        src = built_release(version, key=key, menu=menu, real_steps=real_steps)
        usb = self.tmp / "usb"
        usb.mkdir(exist_ok=True)
        dest = usb / src.name
        shutil.copy2(src, dest)
        if menu:
            for tar in src.parent.glob("thomhouse-menu-*.tar"):
                shutil.copy2(tar, usb / tar.name)
        return dest

    def variant_file(self, version: str, *, migration: str | None = None, python: str | None = None) -> Path:
        """A copy of `built_variant(...)` and its menu archive in `<tmp>/usb-<version>/`; the fixture runtimes
        (with the variant's Python) are copied to `<tmp>/fixtures` again."""
        src = built_variant(version, migration=migration, python=python)
        for f in self.kit.fixtures.iterdir():
            shutil.copy2(f, self.fixtures / f.name)
        usb = self.tmp / f"usb-{version}"
        usb.mkdir(exist_ok=True)
        dest = usb / src.name
        shutil.copy2(src, dest)
        for tar in src.parent.glob("thomhouse-menu-*.tar"):
            shutil.copy2(tar, usb / tar.name)
        return dest

    def run_header(self, command: Path, *args: str, env: dict[str, str] | None = None,
                   answers: str | None = None, timeout: float = 180) -> subprocess.CompletedProcess:
        """`bash <command> <args>`: with `answers` on a terminal, else with stdin from /dev/null."""
        cmd = ["/bin/bash", str(command), *args]
        env = env if env is not None else dict(self.env)
        if answers is not None:
            return run_tty(cmd, env=env, answers=answers, timeout=timeout)
        return subprocess.run(cmd, cwd="/", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=timeout)

    def write_release_pins(self, root: Path, pins: dict | None = None) -> None:
        """Write the test pins and their versions.env into a release tree from `install_release()`."""
        from thomhouse_installer import release

        data = pins if pins is not None else self.kit.pins
        (root / "install" / "versions.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        (root / "install" / "versions.env").write_text(release.versions_env(data, PNPM_VERSION), encoding="utf-8")
        lock = root / "install" / "lock" / "pnpm" / "package-lock.json"
        lock.write_text(pnpm_lock(), encoding="utf-8")

    def plant_steps_stub(self, root: Path) -> None:
        (root / "install" / "thomhouse_installer" / "steps.py").write_text(STEPS_STUB, encoding="utf-8")

    def make_python_runtime(self, reported: str = PY_VERSION, *, version: str = PY_VERSION) -> Path:
        """runtime/python-<version>-aarch64-apple-darwin with the stand-in python3, linked as runtime/python."""
        rt = self.app_home / "runtime"
        folder = rt / f"python-{version}-aarch64-apple-darwin"
        (folder / "bin").mkdir(parents=True, exist_ok=True)
        exe = folder / "bin" / "python3"
        exe.write_bytes(python_wrapper(reported))
        exe.chmod(0o755)
        link = rt / "python"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(folder.name)
        return folder

    def install_built(self, version: str = "1.4.0", *, key: str = "main") -> Path:
        """An installed device from a test build: unpacked, `app` linked, the release file cached, the trust and
        installed.json written, the launcher rendered. Returns the release folder."""
        from thomhouse_installer import release, state

        command = self.release_file(version, key=key)
        ctx = self.ctx()
        info = release.verify_file(ctx, command, first_install=True)
        folder = release.unpack(ctx, info)
        release.switch_app(ctx, info.version)
        release.copy_to_cache(ctx, info)
        trust = self.app_home / "trust" / "allowed_signers"
        trust.parent.mkdir(parents=True, exist_ok=True)
        trust.write_text(self.kit.signers_line(key), encoding="utf-8")
        trust.chmod(0o600)
        ctx = self.ctx()
        state.save_installed(ctx.paths, {"schema": 1, "version": info.version, "previous_version": None,
                                         "release_id": info.release_id, "menu_id": info.menu_id})
        release.write_launcher(ctx, folder)
        return folder
