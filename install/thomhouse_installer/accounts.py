"""The Claude account pool of the runner, read through `scripts/runner/claude_pool.py`, and the login status of
each account (rev F8, F23).

`claude_pool.py` binds its paths when it is imported (`claude_pool.py:37-41`), so `load()` sets THOMHOUSE_BOT_HOME
first and loads the file into a new module object on every call, never stored in `sys.modules`. Output of
`claude_pool.py status` holds account emails, so `pool()` discards every output.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_counter = itertools.count(1)


@dataclass
class Account:
    """One pool account: `config_dir` None means the machine's default `~/.claude`."""

    label: str
    config_dir: Path | None
    priority: int
    enabled: bool
    pool_status: str
    usable_now: bool


@dataclass
class AuthStatus:
    """The three fields of `claude auth status` the installer reads."""

    logged_in: bool
    auth_method: str | None
    subscription: str | None

    @property
    def ok(self) -> bool:
        """Logged in with a claude.ai subscription login and a non-empty plan (rev F8)."""
        return self.logged_in and self.auth_method == "claude.ai" and bool(self.subscription)


def _pool_file(ctx) -> Path:
    return ctx.paths.code_root / "scripts" / "runner" / "claude_pool.py"


def _load_module(path: Path):
    name = f"_thomhouse_claude_pool_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(ctx) -> list[Account]:
    """Every account of `accounts.json`, sorted by priority.

    Sets `os.environ["THOMHOUSE_BOT_HOME"]` to this installation's BOT_HOME, then loads
    `<code_root>/scripts/runner/claude_pool.py` with `importlib.util.spec_from_file_location` into a new module
    object (never in `sys.modules`) and uses its `accounts()`, `state()` and `healthy(label)`. [] when
    `accounts.json` is missing.
    """
    paths = ctx.paths
    os.environ["THOMHOUSE_BOT_HOME"] = str(paths.bot_home)
    if not paths.accounts_json.exists():
        return []
    module = _load_module(_pool_file(ctx))
    try:
        accs = module.accounts()
        st = module.state()
    except Exception:  # noqa: BLE001 - an unreadable pool file means no account
        return []
    out = []
    for a in accs if isinstance(accs, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get("label"), str):
            continue
        label = a["label"]
        entry = st.get(label, {}) if isinstance(st, dict) else {}
        cfg = a.get("config_dir")
        try:
            usable = bool(module.healthy(label))
        except Exception:  # noqa: BLE001 - a malformed state entry
            usable = False
        priority = a.get("priority", 100)
        out.append(
            Account(
                label=label,
                config_dir=Path(cfg) if isinstance(cfg, str) and cfg else None,
                priority=priority if isinstance(priority, int) else 100,
                enabled=bool(a.get("enabled", True)),
                pool_status=str(entry.get("status", "ok")) if isinstance(entry, dict) else "ok",
                usable_now=usable,
            )
        )
    out.sort(key=lambda acc: acc.priority)
    return out


def auth_status(ctx, account: Account) -> AuthStatus:
    """`claude auth status` with CLAUDE_CONFIG_DIR = `account.config_dir` (unset when None), output captured in
    memory. Only `loggedIn`, `authMethod` and `subscriptionType` are read; output that is not a JSON object gives
    AuthStatus(False, None, None). The email in that output is never kept."""
    from . import proc

    extra = {"CLAUDE_CONFIG_DIR": str(account.config_dir)} if account.config_dir else None
    env = proc.child_env(ctx.paths, extra)
    res = proc.run(ctx, ["claude", "auth", "status"], env=env, capture=True, timeout=60)
    try:
        data = json.loads(res.stdout)
    except ValueError:
        return AuthStatus(False, None, None)
    if not isinstance(data, dict):
        return AuthStatus(False, None, None)
    method = data.get("authMethod")
    sub = data.get("subscriptionType")
    return AuthStatus(
        logged_in=data.get("loggedIn") is True,
        auth_method=method if isinstance(method, str) else None,
        subscription=sub if isinstance(sub, str) and sub else None,
    )


def pool(ctx, *args: str) -> int:
    """`python3 -I <code_root>/scripts/runner/claude_pool.py <args>` with the child environment (its
    THOMHOUSE_BOT_HOME is this installation's); every output discarded, because `status` prints emails. Returns the
    exit code."""
    from . import proc

    res = proc.run(ctx, [sys.executable, "-I", str(_pool_file(ctx)), *args], cwd=ctx.paths.code_root, timeout=120)
    ctx.log("pool", command=args[0] if args else "", exit=res.returncode)
    return res.returncode
