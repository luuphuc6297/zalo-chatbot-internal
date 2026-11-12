"""Stand-in for thomhouse_installer.deps (WP2) in the setup tests: runs the fake pnpm and npm like step 7.

`install` writes the release's .npmrc, runs `pnpm install --frozen-lockfile` and `npm ci --prefix tools/<x>`
through the fakes (which create the wrangler, vite and zalo-agent shims) and raises DepsError on a failure.
"""

from __future__ import annotations

import os
from pathlib import Path

from thomhouse_installer import _stubrec, proc
from thomhouse_installer.context import InstallerError


class DepsError(InstallerError):
    code = 1

    def __init__(self, which: str) -> None:
        super().__init__("core.failed", None)
        self.which = which


def stamp_ok(ctx, code_root: Path) -> dict[str, bool]:
    root = Path(code_root)
    return {
        "workspace": (root / "apps" / "server" / "node_modules" / ".bin" / "wrangler").exists(),
        "engine": (root / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent").exists(),
        "rooms": (root / "tools" / "openmausbot" / "node_modules" / ".bin" / "openmausbot").exists(),
    }


def install(ctx, code_root: Path, node_bin: Path, *, pnpm_bin: Path | None = None) -> dict[str, bool]:
    _stubrec.record("deps", "install", code_root, node_bin, pnpm_bin)
    root = Path(code_root)
    p = ctx.paths
    (root / ".npmrc").write_text(f"store-dir={p.cache / 'pnpm-store'}\n", encoding="utf-8")
    env = proc.child_env(p)
    env["PATH"] = os.pathsep.join([str(node_bin), env.get("PATH", "")])
    pnpm = str(pnpm_bin or p.runtime_bin / "pnpm")
    if not os.access(pnpm, os.X_OK):
        pnpm = "pnpm"
    log = p.logs / "deps.log"
    if proc.run(ctx, [pnpm, "install", "--frozen-lockfile"], cwd=root, env=env, log=log).returncode != 0:
        raise DepsError("workspace")
    engine = ["npm", "ci", "--prefix", str(root / "tools" / "zalo-agent"), "--no-fund", "--no-audit"]
    if proc.run(ctx, engine, cwd=root, env=env, log=log).returncode != 0:
        raise DepsError("engine")
    rooms = ["npm", "ci", "--prefix", str(root / "tools" / "openmausbot"), "--no-fund", "--no-audit"]
    ok = proc.run(ctx, rooms, cwd=root, env=env, log=log).returncode == 0
    return {"rooms": ok}
