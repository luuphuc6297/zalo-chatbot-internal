"""Every path of the device layout (16.2.7), from HOME, THOMHOUSE_APP_HOME and THOMHOUSE_BOT_HOME.

Paths keep the logical form: symlinks are never resolved here, because `start_local.sh` passes the logical
`~/ThomHouse/app` path to its services and the env files hold paths through `app` (16.2.7).

Installed mode: `code_root/VERSION.json` exists (a release). Checkout mode: the project on the build Mac. In checkout
mode the lock file, the logs and the history file live under BOT_HOME, so a command run on the build Mac never
creates a `~/ThomHouse` folder there.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .context import Exit

ENV_FILES = {
    "server": ("apps", "server", ".dev.vars"),
    "runner": ("apps", "runner", ".env"),
    "bridge": ("apps", "zalo-bridge", ".env"),
    "console_local": ("apps", "console", ".env.local"),
}


@dataclass(frozen=True)
class Paths:
    """Resolved locations of one installation (installed mode) or of the build Mac's checkout."""

    home: Path
    app_home: Path
    bot_home: Path
    code_root: Path  # folder holding install/ (logical path)
    mode: str  # "installed" when code_root/VERSION.json exists, else "checkout"
    app: Path  # APP_HOME/app (installed) or code_root (checkout)
    releases: Path
    runtime: Path
    runtime_bin: Path
    shared: Path
    cache: Path
    downloads: Path
    cache_releases: Path
    trust: Path  # APP_HOME/trust/allowed_signers
    launcher: Path  # APP_HOME/bin/thomhouse
    installed_json: Path
    steps_json: Path
    history: Path
    logs: Path
    lock_file: Path  # APP_HOME/.install.lock (installed) or BOT_HOME/.install.lock (checkout)
    bootstrap_lock_dir: Path  # APP_HOME/.bootstrap.lock.d
    run_dir: Path
    bot_logs: Path
    d1_dir: Path
    accounts_json: Path
    account_state_json: Path
    backups: Path
    backups_lock: Path
    moved_out: Path  # BOT_HOME/moved-out.json
    zalo_config: Path  # ZALO_CONFIG_DIR or ~/.zalo-agent-cli (only checked for accounts/*/zalo.db)

    def release_dir(self, ver: str) -> Path:
        """`APP_HOME/releases/<ver>`."""
        return self.releases / ver

    def env_file(self, name: str) -> Path:
        """The env file `name` under `app`: "server" apps/server/.dev.vars, "runner" apps/runner/.env,
        "bridge" apps/zalo-bridge/.env, "console_local" apps/console/.env.local. ValueError for another name."""
        try:
            parts = ENV_FILES[name]
        except KeyError:
            raise ValueError(f"unknown env file {name!r}") from None
        return self.app.joinpath(*parts)


def _expand(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    return Path(os.path.abspath(value))


def _has_space(p: Path) -> bool:
    return any(ch.isspace() for ch in str(p))


def default_code_root() -> Path:
    """The folder that holds `install/` for this copy of the package (absolute, symlinks not resolved)."""
    return Path(os.path.abspath(__file__)).parent.parent.parent


def resolve(env: Mapping[str, str] | None = None, code_root: Path | None = None) -> Paths:
    """Compute every path from `env` (default `os.environ`) and `code_root` (default: this package's code root).

    Raises `Exit(3, "core.whitespace_path")` when APP_HOME or BOT_HOME contains whitespace (16.2.7).
    """
    env = os.environ if env is None else env
    home_value = env.get("HOME") or str(Path.home())
    home = Path(os.path.abspath(home_value))
    app_home = _expand(env.get("THOMHOUSE_APP_HOME") or str(home / "ThomHouse"), home)
    bot_home = _expand(env.get("THOMHOUSE_BOT_HOME") or str(home / ".thomhouse-bot"), home)
    for folder in (app_home, bot_home):
        if _has_space(folder):
            raise Exit(3, "core.whitespace_path", folder=str(folder))
    root = Path(os.path.abspath(str(code_root))) if code_root is not None else default_code_root()
    installed = (root / "VERSION.json").is_file()
    mode = "installed" if installed else "checkout"
    zalo_value = env.get("ZALO_CONFIG_DIR")
    zalo_config = _expand(zalo_value, home) if zalo_value else home / ".zalo-agent-cli"
    cache = app_home / "cache"
    runtime = app_home / "runtime"
    backups = bot_home / "backups"
    return Paths(
        home=home,
        app_home=app_home,
        bot_home=bot_home,
        code_root=root,
        mode=mode,
        app=(app_home / "app") if installed else root,
        releases=app_home / "releases",
        runtime=runtime,
        runtime_bin=runtime / "bin",
        shared=app_home / "shared",
        cache=cache,
        downloads=cache / "downloads",
        cache_releases=cache / "releases",
        trust=app_home / "trust" / "allowed_signers",
        launcher=app_home / "bin" / "thomhouse",
        installed_json=app_home / "installed.json",
        steps_json=app_home / "install-steps.json",
        history=(app_home / "history.jsonl") if installed else (bot_home / "history.jsonl"),
        logs=(app_home / "logs") if installed else (bot_home / "logs"),
        lock_file=(app_home / ".install.lock") if installed else (bot_home / ".install.lock"),
        bootstrap_lock_dir=app_home / ".bootstrap.lock.d",
        run_dir=bot_home / "run",
        bot_logs=bot_home / "logs",
        d1_dir=bot_home / "d1",
        accounts_json=bot_home / "accounts.json",
        account_state_json=bot_home / "account-state.json",
        backups=backups,
        backups_lock=backups / ".lock",
        moved_out=bot_home / "moved-out.json",
        zalo_config=zalo_config,
    )
