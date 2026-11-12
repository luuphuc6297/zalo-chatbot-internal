"""Private runtimes: detection at the launcher's fixed locations, the plan, installs of Python, Node.js, pnpm and
Claude Code, the Claude Code binary check and the runtime links (16.4.3 step 5, 16.5, rev F1, F11, F15, F22).

Nothing here looks a runtime up on PATH (rev F11, rev check): Python, Node.js and pnpm are the installer's own
copies under `APP_HOME/runtime`, and Claude Code is `~/.local/bin/claude`, the place Anthropic's installer owns.
`install()` puts a runtime into its versioned folder and never switches a link; `switch()` does that.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .context import InstallerError

NAMES = ("python", "node", "pnpm", "claude_code")
KINDS = ("unpack", "version", "installer", "checksum")
LABELS = {"python": "Python", "node": "Node.js", "pnpm": "pnpm", "claude_code": "Claude Code"}
_FIRST_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class RuntimeInstallError(InstallerError):
    """A runtime could not be installed; `kind` is unpack, version, installer or checksum. Exit code 1, key
    `release.runtime_<kind>` with {name} (the runtime's label and version)."""

    code = 1

    def __init__(self, name: str, kind: str, *, version: str = "") -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown runtime error kind {kind!r}")
        label = LABELS.get(name, name) + (f" {version}" if version else "")
        super().__init__("release.runtime_" + kind, None, name=label)
        self.name = name
        self.kind = kind


@dataclass
class RuntimeItem:
    """One line of the runtime plan."""

    name: str  # "python" | "node" | "pnpm" | "claude_code"
    wanted: str
    found: str | None
    action: str  # "keep" | "install"
    source: str  # host shown to the person
    size_mb: int
    target: Path
    url: str | None
    sha256: str | None


# ---------------------------------------------------------------- helpers

def _first_version(text: str) -> str | None:
    m = _FIRST_VERSION.search(text or "")
    return ".".join(m.groups()) if m else None


def _vt(text: str | None) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split(".")) if text else ()


def _arch(ctx) -> str:
    key = ctx.platform.key or "darwin-arm64"
    return "x64" if key.endswith("x64") else "arm64"


def _triple(ctx) -> str:
    return "x86_64-apple-darwin" if _arch(ctx) == "x64" else "aarch64-apple-darwin"


def _mb(size: int | None) -> int:
    return int(math.ceil(size / 1e6)) if size else 0


def _host(url: str | None, default: str) -> str:
    return (urlsplit(url).hostname or default) if url else default


def _rmtree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _replace_link(link: Path, target: str) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.with_name(f".{link.name}.tmp-{os.getpid()}")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _say(ctx, key: str, **fmt: object) -> None:
    if not ctx.quiet:
        from .text_vi import say

        say(key, **fmt)


def _exe(ctx, name: str) -> Path:
    paths = ctx.paths
    if name == "python":
        return paths.runtime / "python" / "bin" / "python3"
    if name == "node":
        return paths.runtime / "node" / "bin" / "node"
    if name == "pnpm":
        return paths.runtime_bin / "pnpm"
    if name == "claude_code":
        return paths.home / ".local" / "bin" / "claude"
    raise ValueError(f"unknown runtime {name!r}")


def _version_of(ctx, exe: Path, *, node_bin: Path | None = None) -> str | None:
    """The first x.y.z that `exe --version` prints, or None when it is missing or fails (output never logged)."""
    from . import proc

    if not (exe.is_file() or exe.is_symlink()) or not os.access(exe, os.X_OK):
        return None
    env = proc.child_env(ctx.paths)
    if node_bin is not None:
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    res = proc.run(ctx, [str(exe), "--version"], env=env, capture=True, timeout=60)
    if res.returncode != 0:
        return None
    return _first_version(res.stdout) or _first_version(res.stderr)


# ---------------------------------------------------------------- detection and plan

def found(ctx, name: str) -> str | None:
    """The first x.y.z of `--version` at the launcher's locations only (`runtime/python/bin/python3`,
    `runtime/node/bin/node`, `runtime/bin/pnpm`, `$HOME/.local/bin/claude`); None when missing or not runnable
    (rev F11). pnpm runs with `runtime/node/bin` first on PATH, as the launcher gives it."""
    node_bin = ctx.paths.runtime / "node" / "bin" if name == "pnpm" else None
    return _version_of(ctx, _exe(ctx, name), node_bin=node_bin)


def plan(ctx) -> list[RuntimeItem]:
    """One item per runtime: "keep" when the found version equals the pin (Claude Code: is the pin's minimum or
    newer), else "install". Raises PinError like `ctx.pins`."""
    pins = ctx.pins
    paths = ctx.paths
    arch, triple = _arch(ctx), _triple(ctx)
    items = []
    v = pins.python.version
    f = found(ctx, "python")
    items.append(RuntimeItem("python", v, f, "keep" if f == v else "install", _host(pins.python.url, "github.com"),
                             _mb(pins.python.bytes), paths.runtime / f"python-{v}-{triple}", pins.python.url,
                             pins.python.sha256))
    v = pins.node.version
    f = found(ctx, "node")
    items.append(RuntimeItem("node", v, f, "keep" if f == v else "install", _host(pins.node.url, "nodejs.org"),
                             _mb(pins.node.bytes), paths.runtime / f"node-v{v}-darwin-{arch}", pins.node.url,
                             pins.node.sha256))
    v = pins.pnpm_version
    f = found(ctx, "pnpm")
    items.append(RuntimeItem("pnpm", v, f, "keep" if f == v else "install", "registry.npmjs.org",
                             _mb(pins.pnpm_bytes), paths.runtime / f"pnpm-{v}", None, None))
    v = pins.claude.version
    f = found(ctx, "claude_code")
    keep = f is not None and _vt(f) >= _vt(pins.claude_min)
    items.append(RuntimeItem("claude_code", v, f, "keep" if keep else "install", _host(pins.claude.url, "claude.ai"),
                             pins.claude_approx_mb, paths.home / ".local", pins.claude.url, pins.claude.sha256))
    return items


# ---------------------------------------------------------------- installs

def install(ctx, item: RuntimeItem, *, node_bin: Path | None = None) -> None:
    """Install `item` into its versioned folder without switching any link.

    python, node: `download.fetch` (the pinned SHA-256 and size), `tar -xzf` into `runtime/.tmp-<name>-<v>`, a
    `--version` check, then a rename to the target folder. pnpm: `npm ci --prefix runtime/pnpm-<v> --no-fund
    --no-audit` of this release's `install/lock/pnpm`, with `node_bin` (default `runtime/node/bin`) first on PATH.
    claude_code: step 5 of 16.4.3 (Anthropic's installer with `child_env(claude_install=True)`, the version, the
    binary SHA-256). Raises DownloadError, PinError or RuntimeInstallError; a half-made folder is removed.
    """
    if item.name in ("python", "node"):
        _install_tarball(ctx, item)
    elif item.name == "pnpm":
        _install_pnpm(ctx, item, node_bin or ctx.paths.runtime / "node" / "bin")
    elif item.name == "claude_code":
        _install_claude(ctx, item)
    else:
        raise ValueError(f"unknown runtime {item.name!r}")


def _install_tarball(ctx, item: RuntimeItem) -> None:
    from . import download, proc

    paths = ctx.paths
    pin = ctx.pins.python if item.name == "python" else ctx.pins.node
    exe = "python3" if item.name == "python" else "node"
    inner = "python" if item.name == "python" else item.target.name
    if item.target.is_dir() and _version_of(ctx, item.target / "bin" / exe) == item.wanted:
        return
    label = f"{LABELS[item.name]} {item.wanted}"
    archive = download.fetch(ctx, pin.url, pin.sha256, pin.bytes, name=label)
    _say(ctx, "release.installing", name=label)
    paths.runtime.mkdir(parents=True, exist_ok=True)
    tmp = paths.runtime / f".tmp-{item.name}-{item.wanted}"
    _rmtree(tmp)
    tmp.mkdir()
    try:
        res = proc.run(ctx, ["tar", "-xzf", str(archive), "-C", str(tmp)], log=paths.logs / "runtimes.log")
        folder = tmp / inner
        if res.returncode != 0 or not folder.is_dir():
            raise RuntimeInstallError(item.name, "unpack", version=item.wanted)
        if _version_of(ctx, folder / "bin" / exe) != item.wanted:
            raise RuntimeInstallError(item.name, "version", version=item.wanted)
        if item.target.exists() or item.target.is_symlink():
            _rmtree(item.target)
        os.replace(folder, item.target)
    finally:
        _rmtree(tmp)
    ctx.log("runtime_installed", name=item.name, version=item.wanted)


def _install_pnpm(ctx, item: RuntimeItem, node_bin: Path) -> None:
    from . import proc
    from .pins import PinError

    paths = ctx.paths
    target = item.target
    shim = target / "node_modules" / ".bin" / "pnpm"
    if _version_of(ctx, shim, node_bin=node_bin) == item.wanted:
        return
    lock_dir = paths.code_root / "install" / "lock" / "pnpm"
    if not (lock_dir / "package-lock.json").is_file() or not (lock_dir / "package.json").is_file():
        raise PinError("install/lock/pnpm/package-lock.json")
    _say(ctx, "release.installing", name=f"pnpm {item.wanted}")
    _rmtree(target)
    target.mkdir(parents=True)
    try:
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(lock_dir / name, target / name)
        env = proc.child_env(paths)
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
        npm = node_bin / "npm"
        res = proc.run(ctx, [str(npm) if npm.exists() else "npm", "ci", "--prefix", str(target), "--no-fund",
                             "--no-audit"], cwd=target, env=env, log=paths.logs / "runtimes.log")
        if res.returncode != 0:
            raise RuntimeInstallError("pnpm", "unpack", version=item.wanted)
        if _version_of(ctx, shim, node_bin=node_bin) != item.wanted:
            raise RuntimeInstallError("pnpm", "version", version=item.wanted)
    except BaseException:
        _rmtree(target)
        raise
    ctx.log("runtime_installed", name="pnpm", version=item.wanted)


def _install_claude(ctx, item: RuntimeItem) -> None:
    """Step 5 of 16.4.3 for Claude Code (rev F1, F22, rev check)."""
    from . import proc
    from .download import DownloadError

    paths = ctx.paths
    pins = ctx.pins
    version = pins.claude.version
    url = pins.claude.url or ""
    host = urlsplit(url).hostname or ""
    if urlsplit(url).scheme != "https":
        raise DownloadError("not_https", "Claude Code", host=host)
    link = paths.home / ".local" / "bin" / "claude"
    binary = paths.home / ".local" / "share" / "claude" / "versions" / version
    link_target = os.readlink(link) if link.is_symlink() else None
    backup: Path | None = None
    if link.is_file() and not link.is_symlink():
        fd, name = tempfile.mkstemp(prefix=".claude-before-", dir=str(link.parent))
        os.close(fd)
        backup = Path(name)
        shutil.copy2(link, backup)
    binary_existed = binary.exists()
    try:
        paths.downloads.mkdir(parents=True, exist_ok=True)
        script = paths.downloads / "claude-install.sh"
        part = paths.downloads / "claude-install.sh.part"
        part.unlink(missing_ok=True)
        res = proc.run(ctx, ["curl", "--proto", "=https", "--tlsv1.2", "-fL", "--retry", "3", "-o", str(part), url],
                       log=paths.logs / "runtimes.log")
        if res.returncode != 0 or not part.is_file():
            part.unlink(missing_ok=True)
            raise DownloadError("http" if res.returncode == 22 else "network", "Claude Code", host=host)
        os.replace(part, script)
        ctx.log("claude_installer", sha256=_sha256_file(script))
        _say(ctx, "release.installing", name=f"Claude Code {version}")
        res = proc.run(ctx, ["/bin/bash", str(script), version], env=proc.child_env(paths, claude_install=True),
                       log=paths.logs / "runtimes.log", timeout=1800)
        if res.returncode != 0 or _version_of(ctx, link) != version:
            ctx.log("claude_install_failed", exit=res.returncode)
            raise RuntimeInstallError("claude_code", "installer", version=version)
        want = pins.claude.sha256
        if want:
            actual = _sha256_file(binary) if binary.is_file() else None
            if actual != want:
                ctx.log("claude_binary_mismatch", version=version)
                if not binary_existed:
                    binary.unlink(missing_ok=True)
                if link_target is not None:
                    _replace_link(link, link_target)
                elif backup is not None:
                    os.replace(backup, link)
                    backup = None
                else:
                    link.unlink(missing_ok=True)
                raise RuntimeInstallError("claude_code", "checksum", version=version)
    finally:
        if backup is not None:
            backup.unlink(missing_ok=True)
    ctx.log("runtime_installed", name="claude_code", version=version)


# ---------------------------------------------------------------- links

def switch(ctx, name: str, version: str) -> None:
    """Point the runtime link of `name` at `version`: `runtime/python` and `runtime/node` at their versioned
    folders, `runtime/bin/pnpm` at `../pnpm-<v>/node_modules/.bin/pnpm`, and `runtime/bin/claude` at
    `$HOME/.local/bin/claude` (absolute, rev F15; `version` is not used there). FileNotFoundError when the target
    does not exist. Each link is replaced atomically."""
    paths = ctx.paths
    if name == "python":
        folder = f"python-{version}-{_triple(ctx)}"
        if not (paths.runtime / folder).is_dir():
            raise FileNotFoundError(str(paths.runtime / folder))
        _replace_link(paths.runtime / "python", folder)
    elif name == "node":
        folder = f"node-v{version}-darwin-{_arch(ctx)}"
        if not (paths.runtime / folder).is_dir():
            raise FileNotFoundError(str(paths.runtime / folder))
        _replace_link(paths.runtime / "node", folder)
    elif name == "pnpm":
        if not (paths.runtime / f"pnpm-{version}" / "node_modules" / ".bin" / "pnpm").exists():
            raise FileNotFoundError(str(paths.runtime / f"pnpm-{version}"))
        _replace_link(paths.runtime_bin / "pnpm", f"../pnpm-{version}/node_modules/.bin/pnpm")
    elif name == "claude_code":
        target = paths.home / ".local" / "bin" / "claude"
        if not (target.exists() or target.is_symlink()):
            raise FileNotFoundError(str(target))
        _replace_link(paths.runtime_bin / "claude", str(target))
    else:
        raise ValueError(f"unknown runtime {name!r}")
    ctx.log("runtime_switched", name=name, version=version)
