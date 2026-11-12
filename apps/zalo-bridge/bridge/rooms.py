"""The optional room platform (OpenMausBot, docs/contracts.md 14.8 and 14.10) as seen from this machine.

Used by `init-env` and `rooms-node` (which node runs it) and by `doctor` (is it installed, is it up). The platform
is optional: when it is not installed the runner drafts with the direct engine, so nothing here is ever an error.

- Install: <repo>/tools/openmausbot (pinned in its package.json), CLI at node_modules/.bin/openmausbot. The runner's
  OPENMAUSBOT_BIN overrides the CLI path.
- It needs Node 24 or newer (the rest of the stack needs Node 22). The node is looked up on PATH, then under
  ~/.nvm/versions/node (newest first).
- scripts/start_local.sh starts `openmausbot serve` on 127.0.0.1:8799 with <THOMHOUSE_BOT_HOME>/openmausbot as its
  data folder; `python3 -m runner.main rooms-setup` writes config.json there before the start.

Nothing here reads the platform's log or its config (the log holds pairing codes): only "does the file exist".
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, read_dotenv

NODE_MIN_MAJOR = 24
PLATFORM_HOST = "127.0.0.1"
PLATFORM_PORT = 8799
DRAFT_ENGINES = ("claude", "rooms")
VERSION_DIR_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def platform_dir(repo_root: Path = REPO_ROOT) -> Path:
    return Path(repo_root) / "tools" / "openmausbot"


def default_platform_bin(repo_root: Path = REPO_ROOT) -> Path:
    return platform_dir(repo_root) / "node_modules" / ".bin" / "openmausbot"


def node_major(node: str | os.PathLike[str] | None) -> int | None:
    """Major version of that `node` executable, or None when it cannot be run."""
    if not node:
        return None
    try:
        out = subprocess.run([str(node), "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v?(\d+)", out.strip())
    return int(m.group(1)) if m else None


def find_node_dir(min_major: int = NODE_MIN_MAJOR, env: dict[str, str] | None = None,
                  home: Path | None = None) -> str | None:
    """Directory of a `node` of at least `min_major`: the one on PATH, else the newest under ~/.nvm/versions/node."""
    env = os.environ if env is None else env
    on_path = shutil.which("node", path=env.get("PATH", os.defpath))
    major = node_major(on_path)
    if major is not None and major >= min_major:
        return str(Path(on_path).parent)
    home = Path(home) if home is not None else Path(os.path.expanduser(env.get("HOME") or "~"))
    found: list[tuple[tuple[int, int, int], Path]] = []
    try:
        entries = list((home / ".nvm" / "versions" / "node").iterdir())
    except OSError:
        entries = []
    for entry in entries:
        m = VERSION_DIR_RE.match(entry.name)
        if m and int(m.group(1)) >= min_major and os.access(entry / "bin" / "node", os.X_OK):
            found.append(((int(m.group(1)), int(m.group(2)), int(m.group(3))), entry / "bin"))
    for _, bin_dir in sorted(found, reverse=True):
        major = node_major(bin_dir / "node")       # the folder name is a hint; the executable decides
        if major is not None and major >= min_major:
            return str(bin_dir)
    return None


def platform_node_dir(repo_root: Path = REPO_ROOT, env: dict[str, str] | None = None) -> str | None:
    """Directory of the node that runs the platform (`python3 -m bridge.main rooms-node`, used by
    scripts/start_local.sh): the runner's OPENMAUSBOT_NODE_DIR (environment, else apps/runner/.env) when it holds a
    node 24 or newer, else the one `find_node_dir` finds. None when this machine has none."""
    env = os.environ if env is None else env
    runner_env = read_dotenv(Path(repo_root) / "apps" / "runner" / ".env")
    configured = (env.get("OPENMAUSBOT_NODE_DIR") or runner_env.get("OPENMAUSBOT_NODE_DIR") or "").strip()
    if configured:
        configured = os.path.expanduser(configured)
        major = node_major(Path(configured) / "node")
        if major is not None and major >= NODE_MIN_MAJOR:
            return configured
    return find_node_dir(env=env)


def port_open(host: str = PLATFORM_HOST, port: int = PLATFORM_PORT, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def platform_facts(repo_root: Path = REPO_ROOT, env: dict[str, str] | None = None,
                   port: int = PLATFORM_PORT) -> dict[str, Any]:
    """What `doctor` reports about the platform. Runner settings come from the environment, else apps/runner/.env
    (the same order as the runner). No secret is read: only the room settings of contract 14.8."""
    env = os.environ if env is None else env
    repo_root = Path(repo_root)
    runner_env = read_dotenv(repo_root / "apps" / "runner" / ".env")

    def get(name: str, default: str = "") -> str:
        return (env.get(name) or runner_env.get(name) or default).strip()

    exe = Path(os.path.expanduser(get("OPENMAUSBOT_BIN", str(default_platform_bin(repo_root)))))
    home = Path(os.path.expanduser(env.get("THOMHOUSE_BOT_HOME") or "~/.thomhouse-bot"))
    data_dir = Path(os.path.expanduser(get("OPENMAUSBOT_DATA_DIR", str(home / "openmausbot"))))
    installed = exe.is_file() and os.access(exe, os.X_OK)
    facts: dict[str, Any] = {"installed": installed, "bin": str(exe),
                             "engine": get("THOMHOUSE_DRAFT_ENGINE", "claude").lower(), "node_dir": None,
                             "node_dir_configured": False, "node_major": None, "listening": None, "config": None,
                             "port": port}
    if not installed:
        return facts                                # nothing else to look at: the platform is optional
    configured = get("OPENMAUSBOT_NODE_DIR")
    node_dir = os.path.expanduser(configured) if configured else find_node_dir(env=env)
    facts["node_dir"] = node_dir
    facts["node_dir_configured"] = bool(configured)
    facts["node_major"] = node_major(Path(node_dir) / "node") if node_dir else None
    facts["listening"] = port_open(port=port)
    facts["config"] = (data_dir / "config.json").is_file()
    return facts
