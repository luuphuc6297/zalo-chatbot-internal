"""Read-only access to the env files (`apps/server/.dev.vars`, `apps/runner/.env`, `apps/zalo-bridge/.env`,
`apps/console/.env.local`). Values are never logged or printed; writing stays with the bridge's `init-env`."""

from __future__ import annotations

import re
from pathlib import Path

from .paths import Paths

_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def read(path: Path) -> dict[str, str]:
    """KEY=value lines of `path` (an `export ` prefix is allowed); blank and "#" lines skipped; one pair of
    surrounding quotes removed; the last line of a key wins; {} when the file is missing or unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _KEY.match(line)
        if not m:
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[m.group(1)] = value
    return out


def value(paths: Paths, name: str, key: str) -> str | None:
    """The value of `key` in the env file `name` (as `Paths.env_file`), or None when missing or empty."""
    v = read(paths.env_file(name)).get(key)
    return v or None
