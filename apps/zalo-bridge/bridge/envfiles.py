"""`bridge init-env`: create or update the three local env files so server, runner and bridge agree.

  apps/server/.dev.vars   ENV=dev, ZALO_MODE=<mode>, RUNNER_TOKEN, STAFF_TOKEN, ZALO_PERSONAL_WEBHOOK_SECRET
                          (existing secret values are kept; missing ones are generated), OA placeholders if missing
  apps/runner/.env        SERVER_URL, RUNNER_TOKEN (copied from .dev.vars), RUNNER_ID if missing; the room settings
                          of docs/contracts.md 14.8 if missing: THOMHOUSE_DRAFT_ENGINE=claude, OPENMAUSBOT_NODE_DIR
                          when a node 24 or newer is found, and the other settings as commented lines that show
                          their defaults (the runner's own defaults stay in force until the owner removes the #)
  apps/zalo-bridge/.env   SERVER_URL, RUNNER_TOKEN, ZALO_PERSONAL_WEBHOOK_SECRET (copied), BRIDGE_ID,
                          ZALO_AGENT_BIN, SEND_MIN_INTERVAL_S, LABEL_SYNC_EVERY_S if missing

Other lines, comments and order are preserved: a key that is already in a file, set or commented out, is never
overwritten by the "if missing" settings. Files are written with mode 0600. Values are never printed: the returned
summary names keys only.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from .rooms import default_platform_bin, find_node_dir

KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
COMMENTED_KEY_RE = re.compile(r"^\s*#\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
LOCAL_URL = "http://127.0.0.1:8787"
ROOMS_HEADER = "# Two-bot rooms (docs/contracts.md 14.8). A commented line shows a default: remove the # to change it."
AUTO = object()     # init_env(node_dir=AUTO): look for a node 24 or newer on this machine


class EnvFile:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.lines = path.read_text(encoding="utf-8").splitlines()
            self.existed = True
        except FileNotFoundError:
            self.lines = []
            self.existed = False
        self.created: list[str] = []
        self.updated: list[str] = []

    def _index(self, key: str) -> int | None:
        found = None
        for i, line in enumerate(self.lines):
            m = KEY_RE.match(line)
            if m and m.group(1) == key and not line.lstrip().startswith("#"):
                found = i
        return found

    def get(self, key: str) -> str | None:
        i = self._index(key)
        if i is None:
            return None
        v = self.lines[i].split("=", 1)[1].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        return v or None

    def set(self, key: str, value: str, only_if_missing: bool = False) -> None:
        if any(c in value for c in "\n\r"):
            raise ValueError(f"{key}: value must be one line")
        i = self._index(key)
        if i is None:
            self.lines.append(f"{key}={value}")
            self.created.append(key)
        elif not only_if_missing and self.get(key) != value:
            self.lines[i] = f"{key}={value}"
            self.updated.append(key)

    def mentions(self, key: str) -> bool:
        """The key is in the file, set or commented out (`# KEY=...`)."""
        if self._index(key) is not None:
            return True
        for line in self.lines:
            m = COMMENTED_KEY_RE.match(line)
            if m and m.group(1) == key:
                return True
        return False

    def suggest(self, key: str, value: str) -> None:
        """Append `# KEY=value` (a default the owner may change) unless the file already mentions the key."""
        if any(c in value for c in "\n\r"):
            raise ValueError(f"{key}: value must be one line")
        if not self.mentions(key):
            self.lines.append(f"# {key}={value}")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def summary(self) -> dict:
        return {"path": str(self.path), "existed": self.existed, "created": self.created, "updated": self.updated}


def init_env(repo_root: Path, mode: str = "personal", engine_bin: str | None = None,
             server_url: str = LOCAL_URL, node_dir: str | None | object = AUTO) -> dict:
    """`node_dir`: directory of a node 24 or newer for the room platform; None when this machine has none."""
    if mode not in ("personal", "mock"):
        raise ValueError("mode must be personal or mock")
    repo_root = Path(repo_root)
    if node_dir is AUTO:
        node_dir = find_node_dir()
    server = EnvFile(repo_root / "apps" / "server" / ".dev.vars")
    runner = EnvFile(repo_root / "apps" / "runner" / ".env")
    bridge = EnvFile(repo_root / "apps" / "zalo-bridge" / ".env")

    if not server.existed:
        server.lines.append("# Local secrets, generated by scripts/start_local.sh. gitignored; never commit.")
    server.set("RUNNER_TOKEN", f"runner-{secrets.token_hex(24)}", only_if_missing=True)
    server.set("STAFF_TOKEN", f"staff-{secrets.token_hex(24)}", only_if_missing=True)
    server.set("ZALO_PERSONAL_WEBHOOK_SECRET", secrets.token_hex(32), only_if_missing=True)
    # Unused OA path; placeholders keep the server's OA code paths configured.
    server.set("ZALO_APP_ID", "dev-app-id", only_if_missing=True)
    server.set("ZALO_OA_ID", "dev-oa-id", only_if_missing=True)
    server.set("ZALO_OA_SECRET_KEY", f"dev-oa-{secrets.token_hex(16)}", only_if_missing=True)
    server.set("ZALO_APP_SECRET_KEY", f"dev-app-{secrets.token_hex(16)}", only_if_missing=True)
    server.set("ENV", "dev")
    server.set("ZALO_MODE", mode)
    token = server.get("RUNNER_TOKEN") or ""
    secret = server.get("ZALO_PERSONAL_WEBHOOK_SECRET") or ""

    runner.set("SERVER_URL", server_url)
    runner.set("RUNNER_TOKEN", token)
    runner.set("RUNNER_ID", "mac-local-1", only_if_missing=True)
    # Room engine (14.8). The engine stays "claude" until the owner writes "rooms" here. A key the owner commented
    # out counts as present. OPENMAUSBOT_NODE_DIR is written only when a node is found, so a later run fills it in.
    if not runner.mentions("THOMHOUSE_DRAFT_ENGINE"):
        if ROOMS_HEADER not in runner.lines:
            runner.lines.append(ROOMS_HEADER)
        runner.set("THOMHOUSE_DRAFT_ENGINE", "claude", only_if_missing=True)
    if node_dir and not runner.mentions("OPENMAUSBOT_NODE_DIR"):
        runner.set("OPENMAUSBOT_NODE_DIR", str(node_dir), only_if_missing=True)
    runner.suggest("OPENMAUSBOT_BIN", str(default_platform_bin(repo_root)))
    runner.suggest("OPENMAUSBOT_DATA_DIR", "~/.thomhouse-bot/openmausbot")
    runner.suggest("ROOM_TURN_TIMEOUT_S", "240")
    runner.suggest("ROOM_OBSERVE_EVERY_S", "30")
    runner.suggest("ROOM_FALLBACK", "claude")
    runner.suggest("ROOM_REQUIRE_PROFILE_READ", "1")
    runner.suggest("ROOM_CUSTOMER_MODEL", "")

    bridge.set("SERVER_URL", server_url)
    bridge.set("RUNNER_TOKEN", token)
    bridge.set("ZALO_PERSONAL_WEBHOOK_SECRET", secret)
    bridge.set("BRIDGE_ID", "mac-bridge-1", only_if_missing=True)
    if engine_bin:
        bridge.set("ZALO_AGENT_BIN", engine_bin, only_if_missing=True)
    bridge.set("SEND_MIN_INTERVAL_S", "2", only_if_missing=True)
    bridge.set("LABEL_SYNC_EVERY_S", "900", only_if_missing=True)

    for f in (server, runner, bridge):
        f.save()
    return {"server": server.summary(), "runner": runner.summary(), "bridge": bridge.summary()}
