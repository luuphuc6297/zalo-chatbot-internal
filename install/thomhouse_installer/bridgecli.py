"""Calls of the Zalo bridge's own CLI: `python3 -m bridge.main ...` in `<app>/apps/zalo-bridge` with the child
environment, output captured in memory (16.3.3, rev iface).

The bridge doctor prints the Zalo account id in its `zalo_login` detail (`doctor.py:121`), so only each check's
`name` and `status` are read; details are never kept, printed or logged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DOCTOR_TIMEOUT_S = 180
LISTENER_TIMEOUT_S = 180


def _bridge_dir(root: Path) -> Path:
    return root / "apps" / "zalo-bridge"


def _call(ctx, args: list[str], *, root: Path | None = None, timeout: float = 120):
    from . import proc

    base = root if root is not None else ctx.paths.app
    return proc.run(
        ctx,
        [sys.executable, "-m", "bridge.main", *args],
        cwd=_bridge_dir(base),
        capture=True,
        timeout=timeout,
    )


def _json_object(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def doctor(ctx) -> dict[str, str] | None:
    """`doctor --json` as {name: "ok" | "warn" | "fail"}; details are never read. None with `--offline`, when
    `apps/zalo-bridge/.env` is missing, or when the output is not the expected JSON."""
    if ctx.offline:
        return None
    if not ctx.paths.env_file("bridge").exists():
        return None
    res = _call(ctx, ["doctor", "--json"], timeout=DOCTOR_TIMEOUT_S)
    data = _json_object(res.stdout)
    if data is None or not isinstance(data.get("checks"), list):
        return None
    out: dict[str, str] = {}
    for check in data["checks"]:
        if isinstance(check, dict) and isinstance(check.get("name"), str):
            status = check.get("status")
            out[check["name"]] = status if status in ("ok", "warn", "fail") else "fail"
    ctx.log("bridge_doctor", names=sorted(out))
    return out


def listener(ctx, action: str, *, only_ours: bool = False) -> tuple[int, dict]:
    """`listener start|status|stop [--only-ours]`: the exit code and the parsed JSON ({} when none). Codes of
    `apps/zalo-bridge/bridge/listener.py:25-29`: 0 ok, 1 error, 2 config, 3 not logged in, 4 foreign daemon."""
    if action not in ("start", "status", "stop"):
        raise ValueError(f"unknown listener action {action!r}")
    args = ["listener", action]
    if only_ours and action == "stop":
        args.append("--only-ours")
    res = _call(ctx, args, timeout=LISTENER_TIMEOUT_S)
    data = _json_object(res.stdout) or {}
    ctx.log("bridge_listener", action=action, exit=res.returncode)
    return res.returncode, data


def sync_labels(ctx, *, dry_run: bool) -> tuple[int, dict | None]:
    """`sync-labels [--dry-run]`: the exit code and its JSON (counts only), or None when it printed none."""
    args = ["sync-labels"] + (["--dry-run"] if dry_run else [])
    res = _call(ctx, args, timeout=300)
    ctx.log("bridge_sync_labels", dry_run=dry_run, exit=res.returncode)
    return res.returncode, _json_object(res.stdout)


def init_env(ctx, code_root: Path, engine_bin: Path) -> int:
    """`init-env --mode personal --engine-bin <engine_bin> --repo-root <code_root>` in
    `<code_root>/apps/zalo-bridge`; output discarded (it names keys only, but is not needed). Returns the exit
    code. Existing values are kept by init-env itself (`envfiles.py`)."""
    from . import proc

    res = proc.run(
        ctx,
        [
            sys.executable, "-m", "bridge.main", "init-env",
            "--mode", "personal", "--engine-bin", str(engine_bin), "--repo-root", str(code_root),
        ],
        cwd=_bridge_dir(code_root),
        timeout=120,
    )
    ctx.log("bridge_init_env", exit=res.returncode)
    return res.returncode
