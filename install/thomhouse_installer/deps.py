"""Dependencies of a release from its lockfiles only, the release's `.npmrc`, and the stamp
`.thomhouse-deps.json` (16.4.3 step 7, rev F21).

The stamp records the platform (`uname -s` and `uname -m`), the Node.js major version and the SHA-256 of the three
lockfiles at install time; `stamp_ok()` compares them with the machine now and checks that `wrangler`, `vite`,
`zalo-agent` and `openmausbot` exist, so a release copied to another Mac or a changed lockfile is never taken as
installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .context import InstallerError

STAMP = ".thomhouse-deps.json"
LOCKS = {
    "workspace": "pnpm-lock.yaml",
    "engine": "tools/zalo-agent/package-lock.json",
    "rooms": "tools/openmausbot/package-lock.json",
}
BINS = {
    "workspace": ("apps/server/node_modules/.bin/wrangler", "apps/console/node_modules/.bin/vite"),
    "engine": ("tools/zalo-agent/node_modules/.bin/zalo-agent",),
    "rooms": ("tools/openmausbot/node_modules/.bin/openmausbot",),
}
ENGINE_PACKAGE = "@ardennguyen/zalo-agent-cli"
WHICH = ("workspace", "engine")


class DepsError(InstallerError):
    """Installing the libraries failed; `which` is workspace or engine. Exit code 1, key `release.deps_<which>`."""

    code = 1

    def __init__(self, which: str) -> None:
        if which not in WHICH:
            raise ValueError(f"unknown dependency set {which!r}")
        super().__init__("release.deps_" + which, None)
        self.which = which


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _out(cmd: list[str]) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return cp.stdout.strip() if cp.returncode == 0 else ""


def _platform() -> str:
    """`uname -s` and `uname -m`, as the stamp records them."""
    return f"{_out(['uname', '-s'])} {_out(['uname', '-m'])}".strip()


def _node_major(ctx, node_bin: Path | None = None) -> int | None:
    """The major version of the Node.js the stack uses: `node_bin/node`, else `runtime/node/bin/node`, else (checkout
    mode) `node` on PATH."""
    from . import proc

    candidates = []
    if node_bin is not None:
        candidates.append(str(Path(node_bin) / "node"))
    candidates.append(str(ctx.paths.runtime / "node" / "bin" / "node"))
    if ctx.paths.mode != "installed":
        candidates.append("node")
    for exe in candidates:
        if exe != "node" and not os.access(exe, os.X_OK):
            continue
        res = proc.run(ctx, [exe, "--version"], capture=True, timeout=30)
        m = re.search(r"(\d+)\.\d+\.\d+", res.stdout or "")
        if res.returncode == 0 and m:
            return int(m.group(1))
    return None


def _engine_version(code_root: Path) -> tuple[str | None, str | None]:
    """(pinned, installed) version of the Zalo engine."""
    def read(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    pinned = (read(code_root / "tools" / "zalo-agent" / "package.json").get("dependencies") or {}).get(ENGINE_PACKAGE)
    installed = read(code_root / "tools" / "zalo-agent" / "node_modules" / ENGINE_PACKAGE / "package.json")
    return pinned, installed.get("version")


def _read_stamp(code_root: Path) -> dict:
    try:
        data = json.loads((code_root / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def stamp_ok(ctx, code_root: Path) -> dict[str, bool]:
    """{"workspace", "engine", "rooms"}: True when the stamp says that set was installed on this platform
    (`uname -s` and `uname -m`), with this Node.js major version and the lockfile of the same SHA-256, and its
    programs exist (`wrangler` and `vite`; `zalo-agent`, whose installed version also equals the pin;
    `openmausbot`)."""
    root = Path(code_root)
    stamp = _read_stamp(root)
    result = {name: False for name in LOCKS}
    if not stamp:
        return result
    same_host = stamp.get("platform") == _platform() and stamp.get("node_major") == _node_major(ctx)
    locks = stamp.get("locks") if isinstance(stamp.get("locks"), dict) else {}
    done = stamp.get("ok") if isinstance(stamp.get("ok"), dict) else {}
    for name, lock in LOCKS.items():
        digest = _sha256(root / lock)
        ok = (same_host and done.get(name) is True and digest is not None and locks.get(lock) == digest
              and all(os.access(root / b, os.X_OK) for b in BINS[name]))
        if ok and name == "engine":
            pinned, installed = _engine_version(root)
            ok = pinned is not None and pinned == installed
        result[name] = bool(ok)
    return result


def _write_npmrc(ctx, code_root: Path) -> None:
    """The release's `.npmrc`: the single line `store-dir=<APP_HOME>/cache/pnpm-store` (rev F21)."""
    target = code_root / ".npmrc"
    content = f"store-dir={ctx.paths.cache / 'pnpm-store'}\n"
    try:
        if target.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".npmrc.", dir=str(code_root))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)


def _write_stamp(ctx, code_root: Path, node_bin: Path, ok: dict[str, bool]) -> None:
    data = {
        "schema": 1,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": _platform(),
        "node_major": _node_major(ctx, node_bin),
        "locks": {lock: _sha256(code_root / lock) for lock in LOCKS.values()},
        "ok": ok,
    }
    fd, tmp = tempfile.mkstemp(prefix=".deps.", dir=str(code_root))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, code_root / STAMP)


def install(ctx, code_root: Path, node_bin: Path, *, pnpm_bin: Path | None = None) -> dict[str, bool]:
    """Step 7 of 16.4.3 in the release `code_root`, with `node_bin` first on PATH.

    Writes `.npmrc`; runs `pnpm install --frozen-lockfile` (`pnpm_bin`, default `runtime/bin/pnpm`; update phase U4
    passes the new pnpm), then `npm ci --prefix tools/zalo-agent --no-fund --no-audit` and the same for
    `tools/openmausbot` when it exists; output goes to `logs/deps.log`. Writes the stamp. Returns {"rooms": ok};
    an OpenMausBot failure is a warning only (rooms are optional, 14.10). Raises DepsError("workspace") or
    DepsError("engine").
    """
    from . import proc
    from .text_vi import say

    paths = ctx.paths
    root = Path(code_root)
    node_bin = Path(node_bin)
    pnpm = Path(pnpm_bin) if pnpm_bin is not None else paths.runtime_bin / "pnpm"
    log = paths.logs / "deps.log"
    env = proc.child_env(paths)
    env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    npm_path = node_bin / "npm"
    npm = str(npm_path) if npm_path.exists() else "npm"
    _write_npmrc(ctx, root)
    ok = {"workspace": False, "engine": False, "rooms": False}
    _write_stamp(ctx, root, node_bin, ok)  # a stamp that says "not installed" while the installs run
    res = proc.run(ctx, [str(pnpm), "install", "--frozen-lockfile"], cwd=root, env=env, log=log)
    if res.returncode != 0:
        ctx.log("deps_failed", which="workspace", exit=res.returncode)
        raise DepsError("workspace")
    ok["workspace"] = True
    res = proc.run(ctx, [npm, "ci", "--prefix", "tools/zalo-agent", "--no-fund", "--no-audit"], cwd=root, env=env,
                   log=log)
    if res.returncode != 0:
        _write_stamp(ctx, root, node_bin, ok)
        ctx.log("deps_failed", which="engine", exit=res.returncode)
        raise DepsError("engine")
    ok["engine"] = True
    if (root / "tools" / "openmausbot" / "package.json").is_file():
        res = proc.run(ctx, [npm, "ci", "--prefix", "tools/openmausbot", "--no-fund", "--no-audit"], cwd=root,
                       env=env, log=log)
        ok["rooms"] = res.returncode == 0
        if not ok["rooms"]:
            ctx.log("deps_failed", which="rooms", exit=res.returncode)
            if not ctx.quiet:
                say("release.deps_rooms_warn")
    _write_stamp(ctx, root, node_bin, ok)
    ctx.log("deps_installed", rooms=ok["rooms"])
    return {"rooms": ok["rooms"]}
