"""Runner configuration from the environment, with apps/runner/.env as a fallback (env wins).

Variables (aliases in brackets are accepted for compatibility with docs/contracts.md):
  SERVER_URL [THOMHOUSE_API_URL]          backend base URL, e.g. http://127.0.0.1:8787
  RUNNER_TOKEN                            bearer token; if unset, read from the macOS Keychain item
                                          RUNNER_TOKEN_KEYCHAIN_SERVICE (default "thomhouse-runner")
  RUNNER_ID                               [A-Za-z0-9._-]{1,64}
  THOMHOUSE_BOT_HOME                      pool + sessions + conversation workdirs (default ~/.thomhouse-bot)
  MAX_CONCURRENCY [RUNNER_MAX_CONCURRENCY] parallel claude -p calls (default 3)
  CLAUDE_TIMEOUT_S [CLAUDE_CALL_TIMEOUT_S] per call timeout (default 60)
  HEARTBEAT_S (20), STATUS_EVERY_S (60), THOMHOUSE_CLAUDE_MODEL (claude-opus-5-5),
  THOMHOUSE_CLAUDE_EFFORT (low). Not CLAUDE_MODEL/CLAUDE_EFFORT: Claude Code exports CLAUDE_EFFORT in its own
  sessions, so a runner started from one would silently inherit that effort.
  CLAUDE_POOL_PATH                        path to claude_pool.py (default: <repo>/scripts/runner/claude_pool.py)

Two-bot rooms (docs/contracts.md 14.8):
  THOMHOUSE_DRAFT_ENGINE                  "claude" (default: one claude -p call per job) or "rooms"
  OPENMAUSBOT_BIN                         platform CLI (default: <repo>/tools/openmausbot/node_modules/.bin/openmausbot)
  OPENMAUSBOT_DATA_DIR                    platform data folder, passed to the CLI as OMB_DATA_DIR
                                          (default: <THOMHOUSE_BOT_HOME>/openmausbot)
  OPENMAUSBOT_NODE_DIR                    folder with a node >= 24, put first on PATH for the CLI (default: empty)
  ROOM_TURN_TIMEOUT_S (240)               whole room turn
  ROOM_OBSERVE_EVERY_S (30)               observation loop period; 0 turns the loop off
  ROOM_FALLBACK                           "claude" (default: run the direct engine when a room turn fails) or "fail"
  ROOM_REQUIRE_PROFILE_READ (1)           reject a room reply written without a successful get_customer_profile
  ROOM_CUSTOMER_MODEL                     model of the customer bot (default: empty = same as the lead bot)
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # apps/runner
REPO_ROOT = APP_DIR.parent.parent
DEFAULT_POOL = REPO_ROOT / "scripts" / "runner" / "claude_pool.py"
DEFAULT_OPENMAUSBOT_BIN = REPO_ROOT / "tools" / "openmausbot" / "node_modules" / ".bin" / "openmausbot"
DRAFT_ENGINES = ("claude", "rooms")
ROOM_FALLBACKS = ("claude", "fail")
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")
RUNNER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ConfigError(Exception):
    pass


def read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("export "):
            k = k[7:].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


def _keychain_token(service: str) -> str | None:
    try:
        p = subprocess.run(["security", "find-generic-password", "-s", service, "-w"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() or None if p.returncode == 0 else None


@dataclass
class Config:
    server_url: str
    runner_token: str
    runner_id: str
    home: Path
    max_concurrency: int = 3
    claude_timeout_s: float = 60.0
    heartbeat_s: float = 20.0
    status_every_s: float = 60.0
    model: str = "claude-opus-5-5"
    effort: str = "low"
    pool_path: Path = DEFAULT_POOL
    draft_engine: str = "claude"
    openmausbot_bin: Path = DEFAULT_OPENMAUSBOT_BIN
    openmausbot_data_dir: Path | None = None               # None = <home>/openmausbot
    openmausbot_node_dir: str = ""
    room_turn_timeout_s: float = 240.0
    room_observe_every_s: float = 30.0
    room_fallback: str = "claude"
    room_require_profile_read: bool = True
    room_customer_model: str = ""

    def __post_init__(self) -> None:
        if self.draft_engine not in DRAFT_ENGINES:
            raise ConfigError(f"THOMHOUSE_DRAFT_ENGINE must be one of {', '.join(DRAFT_ENGINES)} "
                              f"(got {self.draft_engine!r})")
        if self.room_fallback not in ROOM_FALLBACKS:
            raise ConfigError(f"ROOM_FALLBACK must be one of {', '.join(ROOM_FALLBACKS)} (got {self.room_fallback!r})")

    @property
    def platform_data_dir(self) -> Path:
        """Data folder of the rooms platform (config.json lives here; the CLI gets it as OMB_DATA_DIR)."""
        return Path(self.openmausbot_data_dir) if self.openmausbot_data_dir else self.home / "openmausbot"

    @property
    def rooms_dir(self) -> Path:
        return self.home / "rooms"

    @classmethod
    def load(cls, env: dict[str, str] | None = None, dotenv: Path | None = None,
             require_token: bool = True) -> "Config":
        merged = read_dotenv(dotenv if dotenv is not None else APP_DIR / ".env")
        merged.update(env if env is not None else os.environ)

        def get(*names: str, default: str | None = None) -> str | None:
            for n in names:
                if merged.get(n):
                    return merged[n]
            return default

        url = get("SERVER_URL", "THOMHOUSE_API_URL", default="http://127.0.0.1:8787").rstrip("/")
        token = get("RUNNER_TOKEN")
        if not token and require_token:
            token = _keychain_token(get("RUNNER_TOKEN_KEYCHAIN_SERVICE", default="thomhouse-runner"))
        if not token and require_token:
            raise ConfigError("RUNNER_TOKEN is not set (env, apps/runner/.env or Keychain)")
        rid = get("RUNNER_ID", default="mac-runner-1")
        if not RUNNER_ID_RE.match(rid):
            raise ConfigError("RUNNER_ID must match [A-Za-z0-9._-]{1,64}")
        home = Path(os.path.expanduser(get("THOMHOUSE_BOT_HOME", default="~/.thomhouse-bot")))
        try:
            conc = max(1, int(get("MAX_CONCURRENCY", "RUNNER_MAX_CONCURRENCY", default="3")))
            timeout = float(get("CLAUDE_TIMEOUT_S", "CLAUDE_CALL_TIMEOUT_S", default="60"))
            hb = float(get("HEARTBEAT_S", default="20"))
            st = float(get("STATUS_EVERY_S", default="60"))
            room_timeout = float(get("ROOM_TURN_TIMEOUT_S", default="240"))
            observe = max(0.0, float(get("ROOM_OBSERVE_EVERY_S", default="30")))
        except ValueError as e:
            raise ConfigError(f"bad number in config: {e}") from None
        if room_timeout <= 0:
            raise ConfigError("ROOM_TURN_TIMEOUT_S must be greater than 0")
        need_profile = get("ROOM_REQUIRE_PROFILE_READ", default="1").strip().lower()
        if need_profile not in _TRUE + _FALSE:
            raise ConfigError("ROOM_REQUIRE_PROFILE_READ must be 1 or 0")
        data_dir = get("OPENMAUSBOT_DATA_DIR")
        return cls(server_url=url, runner_token=token or "", runner_id=rid, home=home, max_concurrency=conc,
                   claude_timeout_s=timeout, heartbeat_s=hb, status_every_s=st,
                   model=get("THOMHOUSE_CLAUDE_MODEL", default="claude-opus-5-5"),
                   effort=get("THOMHOUSE_CLAUDE_EFFORT", default="low"),
                   pool_path=Path(os.path.expanduser(get("CLAUDE_POOL_PATH", default=str(DEFAULT_POOL)))),
                   draft_engine=get("THOMHOUSE_DRAFT_ENGINE", default="claude").strip().lower(),
                   openmausbot_bin=Path(os.path.expanduser(get("OPENMAUSBOT_BIN",
                                                                 default=str(DEFAULT_OPENMAUSBOT_BIN)))),
                   openmausbot_data_dir=Path(os.path.expanduser(data_dir)) if data_dir else None,
                   openmausbot_node_dir=os.path.expanduser(get("OPENMAUSBOT_NODE_DIR", default="")),
                   room_turn_timeout_s=room_timeout, room_observe_every_s=observe,
                   room_fallback=get("ROOM_FALLBACK", default="claude").strip().lower(),
                   room_require_profile_read=need_profile in _TRUE,
                   room_customer_model=get("ROOM_CUSTOMER_MODEL", default="").strip())
