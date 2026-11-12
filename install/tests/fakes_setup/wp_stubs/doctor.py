"""Stand-in for thomhouse_installer.doctor (WP4) in the setup tests: `run_checks`, `passes`, `exit_code`.

Only the checks the install steps use look at the machine: node, pnpm, claude_cli (through `runtimes.found`),
deps_workspace and deps_engine (`deps.stamp_ok`), zalo_login and listener (`bridgecli.doctor`, a missing login is
"todo" as in 16.7) and install_lock (`state.lock_holder` / `held_by_us`, rev F3). Every other check passes.
Behaviour "stub_doctor": {"status": {check_id: status}} forces a status.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass

from thomhouse_installer import _stubrec, bridgecli, state

CHECK_IDS = (
    "macos", "cpu", "disk", "system_tools", "python", "install_lock", "moved_out", "other_stack", "release",
    "release_files", "release_clean", "node", "pnpm", "claude_cli", "pins", "deps_workspace", "deps_engine",
    "deps_rooms", "menu_slides", "env_files", "tokens_agree", "paths_current", "permissions", "no_api_key",
    "profile_llm_off", "database", "migrations", "last_backup", "claude_pool", "claude_login", "processes",
    "server_health", "runner_online", "catalog", "console", "zalo_login", "listener", "bridge_token",
    "room_platform", "menu_images", "listen_local_only", "openmausbot_options", "reply_flags", "history_sync",
    "contacts_analyzed", "visits_analyzed", "labels", "staff_token_step",
)


@dataclass
class CheckResult:
    n: int
    id: str
    group: str
    status: str
    label: str
    detail: str
    fix: str | None

    def as_dict(self) -> dict:
        return {"n": self.n, "id": self.id, "group": self.group, "status": self.status, "label": self.label,
                "detail": self.detail, "fix": self.fix}


def _module(name: str):
    return importlib.import_module(f"thomhouse_installer.{name}")


def _vt(text):
    out = []
    for piece in (text or "").split("."):
        if not piece.isdigit():
            break
        out.append(int(piece))
    return tuple(out)


def _root(ctx):
    return ctx.paths.app if os.path.lexists(ctx.paths.app) else ctx.paths.code_root


def _status(ctx, cid: str, cache: dict) -> str:
    forced = (_stubrec.behaviour("doctor").get("status") or {}).get(cid)
    if forced:
        return forced
    ok = None
    if cid in ("node", "pnpm", "claude_cli"):
        runtimes = _module("runtimes")
        pins = ctx.pins
        if cid == "node":
            ok = runtimes.found(ctx, "node") == pins.node.version
        elif cid == "pnpm":
            ok = runtimes.found(ctx, "pnpm") == pins.pnpm_version
        else:
            have = runtimes.found(ctx, "claude_code")
            ok = have is not None and _vt(have) >= _vt(pins.claude_min) and (ctx.paths.runtime_bin / "claude").exists()
    elif cid in ("deps_workspace", "deps_engine"):
        stamp = cache.setdefault("stamp", _module("deps").stamp_ok(ctx, _root(ctx)))
        ok = bool(stamp.get(cid.split("_", 1)[1]))
    elif cid in ("zalo_login", "listener"):
        if "bridge" not in cache:
            cache["bridge"] = bridgecli.doctor(ctx) or {}
        bridge = cache["bridge"]
        if bridge.get("zalo_login") != "ok":
            return "todo"
        ok = cid == "zalo_login" or bridge.get("listener") == "ok"
    elif cid == "install_lock":
        ok = state.lock_holder(ctx.paths) is None or state.held_by_us(ctx.paths)
    return "pass" if ok is None or ok else "fail"


def run_checks(ctx, *, only: set[str] | None = None) -> list[CheckResult]:
    _stubrec.record("doctor", "run_checks", ",".join(sorted(only)) if only else None)
    cache: dict = {}
    out = []
    for n, cid in enumerate(CHECK_IDS, start=1):
        if only is not None and cid not in only:
            continue
        status = _status(ctx, cid, cache)
        out.append(CheckResult(n, cid, "stub", status, f"check {cid}", "stub detail",
                               None if status == "pass" else f"fix {cid}"))
    return out


def passes(ctx, ids: set[str]) -> bool:
    _stubrec.record("doctor", "passes", ",".join(sorted(ids)))
    cache: dict = {}
    return all(_status(ctx, cid, cache) not in ("fail", "todo") for cid in ids)


def exit_code(results: list, strict: bool) -> int:
    bad = ("fail", "warn", "todo") if strict else ("fail",)
    return 1 if any(r.status in bad for r in results) else 0
