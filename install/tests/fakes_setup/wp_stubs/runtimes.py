"""Stand-in for thomhouse_installer.runtimes (WP2) in the setup tests: the 16.3.3 interface, offline.

`install` writes shims that run the fakes of fake_bin (node, pnpm, claude) at the places the real module uses;
`switch` makes the links. Behaviour "stub_runtimes": {"fail": name or [names]} raises RuntimeInstallError.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from thomhouse_installer import _stubrec, proc
from thomhouse_installer.context import InstallerError

NAMES = ("python", "node", "pnpm", "claude_code")
HOSTS = {"python": "github.com", "node": "nodejs.org", "pnpm": "registry.npmjs.org", "claude_code": "claude.ai"}
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class RuntimeInstallError(InstallerError):
    code = 1

    def __init__(self, name: str, kind: str) -> None:
        super().__init__("core.failed", None)
        self.name = name
        self.kind = kind


@dataclass
class RuntimeItem:
    name: str
    wanted: str
    found: str | None
    action: str
    source: str
    size_mb: int
    target: Path
    url: str | None
    sha256: str | None


def _vt(text: str | None) -> tuple[int, ...]:
    m = _VERSION.search(text or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def _exe(ctx, name: str) -> Path:
    p = ctx.paths
    return {
        "python": p.runtime / "python" / "bin" / "python3",
        "node": p.runtime / "node" / "bin" / "node",
        "pnpm": p.runtime_bin / "pnpm",
        "claude_code": p.home / ".local" / "bin" / "claude",
    }[name]


def found(ctx, name: str) -> str | None:
    exe = _exe(ctx, name)
    if not os.access(exe, os.X_OK):
        return None
    try:
        cp = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30,
                            env=proc.child_env(ctx.paths), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VERSION.search(cp.stdout or "")
    return m.group(0) if m and cp.returncode == 0 else None


def _wanted(ctx, name: str) -> str:
    pins = ctx.pins
    return {"python": pins.python.version, "node": pins.node.version, "pnpm": pins.pnpm_version,
            "claude_code": pins.claude.version}[name]


def plan(ctx) -> list[RuntimeItem]:
    _stubrec.record("runtimes", "plan")
    pins = ctx.pins
    items = []
    for name in NAMES:
        have = found(ctx, name)
        wanted = _wanted(ctx, name)
        if name == "claude_code":
            keep = have is not None and _vt(have) >= _vt(pins.claude_min)
        else:
            keep = have == wanted
        size = {"python": pins.python.bytes, "node": pins.node.bytes, "pnpm": pins.pnpm_bytes,
                "claude_code": None}[name]
        mb = math.ceil(size / 1e6) if size else (pins.claude_approx_mb if name == "claude_code" else 0)
        pin = {"python": pins.python, "node": pins.node, "claude_code": pins.claude}.get(name)
        target = ctx.paths.home / ".local" if name == "claude_code" else ctx.paths.runtime
        items.append(RuntimeItem(name, wanted, have, "keep" if keep else "install", HOSTS[name], mb, target,
                                 pin.url if pin else None, pin.sha256 if pin else None))
    return items


def _fake(tool: str) -> str:
    return os.path.join(os.environ["THOMHOUSE_FAKE_BIN"], tool)


def install(ctx, item: RuntimeItem, *, node_bin: Path | None = None) -> None:
    _stubrec.record("runtimes", "install", item.name, item.wanted, node_bin)
    if _stubrec.fails("runtimes", item.name):
        raise RuntimeInstallError(item.name, "installer")
    p = ctx.paths
    v = item.wanted
    if item.name == "python":
        _stubrec.write_exec(p.runtime / f"python-{v}" / "bin" / "python3",
                            f'#!/bin/sh\nif [ "$1" = "--version" ]; then echo "Python {v}"; exit 0; fi\n'
                            f'exec "{sys.executable}" "$@"\n')
    elif item.name == "node":
        _stubrec.write_exec(p.runtime / f"node-v{v}-darwin-arm64" / "bin" / "node",
                            f'#!/bin/sh\nTHOMHOUSE_FAKE_NODE_VERSION=v{v} exec "{_fake("node")}" "$@"\n')
    elif item.name == "pnpm":
        _stubrec.write_exec(p.runtime / f"pnpm-{v}" / "node_modules" / ".bin" / "pnpm",
                            f'#!/bin/sh\nexec "{_fake("pnpm")}" "$@"\n')
    else:
        target = p.home / ".local" / "share" / "claude" / "versions" / v
        _stubrec.write_exec(target, f'#!/bin/sh\nTHOMHOUSE_FAKE_CLAUDE_VERSION={v} exec "{_fake("claude")}" "$@"\n')
        _stubrec.replace_link(p.home / ".local" / "bin" / "claude", str(target))


def switch(ctx, name: str, version: str) -> None:
    _stubrec.record("runtimes", "switch", name, version)
    p = ctx.paths
    if name == "python":
        _stubrec.replace_link(p.runtime / "python", f"python-{version}")
    elif name == "node":
        _stubrec.replace_link(p.runtime / "node", f"node-v{version}-darwin-arm64")
    elif name == "pnpm":
        _stubrec.replace_link(p.runtime_bin / "pnpm", f"../pnpm-{version}/node_modules/.bin/pnpm")
    else:
        _stubrec.replace_link(p.runtime_bin / "claude", str(p.home / ".local" / "bin" / "claude"))
