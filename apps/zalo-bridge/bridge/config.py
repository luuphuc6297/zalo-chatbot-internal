"""Bridge configuration from the environment, with apps/zalo-bridge/.env as a fallback (env wins).

Variables:
  SERVER_URL [THOMHOUSE_API_URL]   backend base URL (default http://127.0.0.1:8787)
  RUNNER_TOKEN                     bearer token for the Bridge API (same token as the runner)
  BRIDGE_ID                        X-Bridge-Id header, [A-Za-z0-9._-]{1,64} (default mac-bridge-1)
  ZALO_AGENT_BIN                   zalo-agent executable: a path, or a name looked up on PATH. Default:
                                   <repo>/tools/zalo-agent/node_modules/.bin/zalo-agent when it exists, else
                                   "zalo-agent"
  ZALO_ACCOUNT                     optional exact Zalo account id, passed to the engine as --account
  ZALO_PERSONAL_WEBHOOK_SECRET     webhook signing secret shared with the server; handed to `zalo-agent listen`
                                   as env ZALO_WEBHOOK_SECRET (never as a flag: flags show up in `ps`)
  SEND_MIN_INTERVAL_S (2)          minimum gap between two sends, so the account does not flood
  SEND_JITTER_S (1)                extra random 0..N seconds added to that gap
  SEND_TIMEOUT_S (30)              timeout of one `zalo-agent msg send`; a timeout is reported as "unknown"
  LOGIN_PAUSE_S (60)               pause in claiming after a send failed because the account is not logged in
  THOMHOUSE_BOT_HOME               default ~/.thomhouse-bot; the send journal lives in <home>/bridge
  BRIDGE_STATE_DIR                 overrides the journal directory
  MENU_IMAGES_DIR                  menu image JPEGs + manifest.json built by scripts/build_menu_images.py
                                   (default <home>/menu-images)
  IMAGE_TIMEOUT_PER_IMAGE_S (15)   a `msg send-image` gets SEND_TIMEOUT_S plus this much per image ...
  IMAGE_TIMEOUT_MAX_S (240)        ... at most this long (the server's lease of an image row is 60 s + 20 s per image)
  LABEL_SYNC_EVERY_S (900)         `run` copies the Zalo labels to contact roles at start and every N seconds
                                   (labels.py); 0 disables the periodic sync. The staff token it needs is NOT a
                                   bridge setting: STAFF_TOKEN from the environment, else apps/server/.dev.vars
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # apps/zalo-bridge
REPO_ROOT = APP_DIR.parent.parent
LOCAL_ENGINE_BIN = REPO_ROOT / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent"
ENGINE_VERSION = "2.5.9"
BRIDGE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ACCOUNT_RE = re.compile(r"^[0-9]{1,40}$")


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


def default_engine_bin() -> str:
    return str(LOCAL_ENGINE_BIN) if LOCAL_ENGINE_BIN.exists() else "zalo-agent"


@dataclass
class Config:
    server_url: str
    runner_token: str
    bridge_id: str
    zalo_agent_bin: str
    state_dir: Path
    zalo_account: str | None = None
    webhook_secret: str = ""
    send_min_interval_s: float = 2.0
    send_jitter_s: float = 1.0
    send_timeout_s: float = 30.0
    login_pause_s: float = 60.0
    menu_images_dir: Path | None = None   # None: <THOMHOUSE_BOT_HOME>/menu-images
    image_timeout_per_image_s: float = 15.0
    image_timeout_max_s: float = 240.0
    label_sync_every_s: float = 900.0     # 0: no periodic label sync

    def image_timeout_s(self, count: int) -> float:
        """Timeout of one `msg send-image` with `count` images."""
        return min(self.send_timeout_s + self.image_timeout_per_image_s * max(1, count),
                   max(self.image_timeout_max_s, self.send_timeout_s))

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
        if not url.startswith(("http://", "https://")):
            raise ConfigError("SERVER_URL must start with http:// or https://")
        token = get("RUNNER_TOKEN") or ""
        if not token and require_token:
            raise ConfigError("RUNNER_TOKEN is not set (env or apps/zalo-bridge/.env)")
        bid = get("BRIDGE_ID", default="mac-bridge-1")
        if not BRIDGE_ID_RE.match(bid):
            raise ConfigError("BRIDGE_ID must match [A-Za-z0-9._-]{1,64}")
        account = get("ZALO_ACCOUNT")
        if account and not ACCOUNT_RE.match(account):
            raise ConfigError("ZALO_ACCOUNT must be the exact numeric Zalo account id")
        home = Path(os.path.expanduser(get("THOMHOUSE_BOT_HOME", default="~/.thomhouse-bot")))
        state = Path(os.path.expanduser(get("BRIDGE_STATE_DIR", default=str(home / "bridge"))))
        try:
            interval = max(0.0, float(get("SEND_MIN_INTERVAL_S", default="2")))
            jitter = max(0.0, float(get("SEND_JITTER_S", default="1")))
            timeout = max(1.0, float(get("SEND_TIMEOUT_S", default="30")))
            pause = max(0.0, float(get("LOGIN_PAUSE_S", default="60")))
            per_image = max(0.0, float(get("IMAGE_TIMEOUT_PER_IMAGE_S", default="15")))
            image_max = max(1.0, float(get("IMAGE_TIMEOUT_MAX_S", default="240")))
            label_every = max(0.0, float(get("LABEL_SYNC_EVERY_S", default="900")))
        except ValueError as e:
            raise ConfigError(f"bad number in config: {e}") from None
        return cls(server_url=url, runner_token=token, bridge_id=bid,
                   zalo_agent_bin=os.path.expanduser(get("ZALO_AGENT_BIN", default=default_engine_bin())),
                   state_dir=state, zalo_account=account or None,
                   webhook_secret=(get("ZALO_PERSONAL_WEBHOOK_SECRET") or "").strip(),
                   send_min_interval_s=interval, send_jitter_s=jitter, send_timeout_s=timeout,
                   login_pause_s=pause,
                   menu_images_dir=Path(os.path.expanduser(get("MENU_IMAGES_DIR", default=str(home / "menu-images")))),
                   image_timeout_per_image_s=per_image, image_timeout_max_s=image_max,
                   label_sync_every_s=label_every)
