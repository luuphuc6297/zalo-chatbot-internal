"""Stand-in for WP2 `runtimes.py` in the operations tests (16.3.3 signatures only).

The "installed" runtime versions live in <tmp>/stub-runtimes.json (defaults: the pins of install/versions.json);
`plan` compares them with the pins of the context's release, `install` creates the versioned folder (and a pnpm
shim) and `switch` changes the recorded version. Behaviour "stubs": {"fail_runtime": "<name>"}.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import _stubio
from .context import InstallerError

DEFAULTS = {"python": "3.14.6", "node": "24.19.0", "pnpm": "10.32.1", "claude_code": "2.1.319"}
SOURCES = {"python": "github.com", "node": "nodejs.org", "pnpm": "registry.npmjs.org", "claude_code": "claude.ai"}


class RuntimeInstallError(InstallerError):
    code = 1

    def __init__(self, name: str, kind: str) -> None:
        super().__init__(f"release.runtime_{kind}", 1, name=name)
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


def _state_file() -> Path:
    return Path(_stubio.test_dir()) / "stub-runtimes.json"


def current() -> dict:
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    out = dict(DEFAULTS)
    out.update(data)
    return out


def found(ctx, name: str) -> str | None:
    return current().get(name)


def _wanted(ctx) -> dict:
    p = ctx.pins
    return {"python": p.python.version, "node": p.node.version, "pnpm": p.pnpm_version, "claude_code": p.claude.version}


def _target(ctx, name: str, version: str) -> Path:
    if name == "claude_code":
        return ctx.paths.home / ".local" / "share" / "claude" / "versions" / version
    return ctx.paths.runtime / f"{name}-{version}"


def plan(ctx) -> list[RuntimeItem]:
    have = current()
    items = []
    for name, version in _wanted(ctx).items():
        action = "keep" if have.get(name) == version else "install"
        items.append(RuntimeItem(name=name, wanted=version, found=have.get(name), action=action,
                                 source=SOURCES[name], size_mb=40, target=_target(ctx, name, version), url=None,
                                 sha256=None))
    _stubio.record("runtimes.plan", install=[i.name for i in items if i.action == "install"])
    return items


def install(ctx, item: RuntimeItem, *, node_bin: Path | None = None) -> None:
    _stubio.record("runtimes.install", name=item.name, version=item.wanted,
                   node_bin=str(node_bin) if node_bin else None)
    if _stubio.behaviour().get("fail_runtime") == item.name:
        raise RuntimeInstallError(item.name, "unpack")
    target = Path(item.target)
    (target / "bin").mkdir(parents=True, exist_ok=True)
    if item.name == "pnpm":
        shim = target / "node_modules" / ".bin" / "pnpm"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(shim, 0o755)


def switch(ctx, name: str, version: str) -> None:
    _stubio.record("runtimes.switch", name=name, version=version)
    data = current()
    data[name] = version
    _state_file().write_text(json.dumps(data), encoding="utf-8")
