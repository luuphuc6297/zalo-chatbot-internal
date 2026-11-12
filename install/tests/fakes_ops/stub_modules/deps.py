"""Stand-in for WP2 `deps.py` in the operations tests (16.3.3 signatures only).

`install` records its arguments and writes the `wrangler` and `vite` shims of a frozen install (they run the fakes of
install/tests/fake_bin), so `migrations.apply` works on the new release. Behaviour "stubs": {"fail_deps": true}
leaves a half-made node_modules and raises DepsError("workspace").
"""

from __future__ import annotations

import os
from pathlib import Path

from . import _stubio
from .context import InstallerError


class DepsError(InstallerError):
    code = 1

    def __init__(self, which: str) -> None:
        super().__init__(f"release.deps_{which}", 1)
        self.which = which


def _shim(path: Path, tool: str) -> None:
    fake_bin = os.environ.get("THOMHOUSE_FAKE_BIN", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nexec "{fake_bin}/{tool}" "$@"\n', encoding="utf-8")
    os.chmod(path, 0o755)


def stamp_ok(ctx, code_root: Path) -> dict[str, bool]:
    return {"workspace": True, "engine": True, "rooms": True}


def install(ctx, code_root: Path, node_bin: Path, *, pnpm_bin: Path | None = None) -> dict[str, bool]:
    _stubio.record("deps.install", code_root=str(code_root), node_bin=str(node_bin),
                   pnpm_bin=str(pnpm_bin) if pnpm_bin else None)
    root = Path(code_root)
    if _stubio.behaviour().get("fail_deps"):
        (root / "node_modules" / ".pnpm").mkdir(parents=True, exist_ok=True)
        (root / "apps" / "server" / "node_modules").mkdir(parents=True, exist_ok=True)
        raise DepsError("workspace")
    _shim(root / "apps" / "server" / "node_modules" / ".bin" / "wrangler", "wrangler")
    _shim(root / "apps" / "console" / "node_modules" / ".bin" / "vite", "vite")
    return {"rooms": True}
