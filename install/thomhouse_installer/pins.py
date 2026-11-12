"""Runtime and package pins (16.2.5) and their agreement across the project files (16.2.2 step 3).

`install/versions.json` holds the runtime pins. A hash or size that `scripts/release/refresh_pins.py` has not filled
yet is `null` there (the documented placeholder) and is `None` here; `download.fetch` refuses to download anything
whose hash is `None`. The pnpm version comes from `package.json` `packageManager`, the Zalo engine and OpenMausBot
versions from `tools/*/package.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .context import InstallerError

ENGINE_PACKAGE = "@ardennguyen/zalo-agent-cli"
ROOMS_PACKAGE = "openmausbot"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class PinError(InstallerError):
    """A pin is missing or unreadable; `name` says which (never a value). Exit code 2."""

    code = 2
    key = "core.pin_missing"

    def __init__(self, name: str) -> None:
        super().__init__(None, None, name=name)
        self.name = name


@dataclass(frozen=True)
class RuntimePin:
    """One runtime for one platform. `url`, `sha256` and `bytes` are None while they are placeholders."""

    version: str
    url: str | None
    sha256: str | None
    bytes: int | None


@dataclass(frozen=True)
class Pins:
    """Everything `load()` read."""

    macos_min: tuple[int, ...]
    disk_min_gb: int
    python: RuntimePin
    python_min: str
    node: RuntimePin
    node_min_stack: str
    node_min_rooms_major: int
    pnpm_version: str
    pnpm_bytes: int | None
    claude: RuntimePin  # url = installer_url; sha256/bytes of the binary for this platform (may be None)
    claude_min: str
    claude_approx_mb: int
    engine_version: str
    openmausbot_version: str | None


def _read_json(path: Path, name: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PinError(name) from None
    if not isinstance(data, dict):
        raise PinError(name)
    return data


def _get(data: dict, dotted: str, kind: type) -> object:
    cur: object = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise PinError(dotted)
        cur = cur[part]
    if kind is int and isinstance(cur, bool):
        raise PinError(dotted)
    if not isinstance(cur, kind):
        raise PinError(dotted)
    return cur


def _hash_or_none(value: object) -> str | None:
    return value.lower() if isinstance(value, str) and _HEX64.match(value) else None


def _bytes_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _url_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and "://" in value else None


def _platform_entry(section: dict, platform_key: str | None) -> dict:
    plats = section.get("platforms")
    if not isinstance(plats, dict) or platform_key is None:
        return {}
    entry = plats.get(platform_key)
    return entry if isinstance(entry, dict) else {}


def _version_tuple(text: str) -> tuple[int, ...]:
    out = []
    for piece in text.split("."):
        if not piece.isdigit():
            break
        out.append(int(piece))
    return tuple(out)


def _package_dep(path: Path, package: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    deps = data.get("dependencies") if isinstance(data, dict) else None
    value = deps.get(package) if isinstance(deps, dict) else None
    return value if isinstance(value, str) and value else None


def _lock_root_dep(path: Path, package: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    packages = data.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    deps = root.get("dependencies") if isinstance(root, dict) else None
    value = deps.get(package) if isinstance(deps, dict) else None
    if value is None and isinstance(data.get("dependencies"), dict):  # lockfileVersion 1
        entry = data["dependencies"].get(package)
        value = entry.get("version") if isinstance(entry, dict) else None
    return value if isinstance(value, str) and value else None


def _pnpm_version(code_root: Path) -> str | None:
    """The version of `packageManager` in `code_root/package.json` (`pnpm@X.Y.Z`), or None."""
    try:
        data = json.loads((code_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pm = data.get("packageManager") if isinstance(data, dict) else None
    if not isinstance(pm, str) or not pm.startswith("pnpm@"):
        return None
    version = pm[len("pnpm@"):].split("+", 1)[0]
    return version or None


def load(code_root: Path, platform_key: str | None = "darwin-arm64") -> Pins:
    """Read every pin for `platform_key` from the files of `code_root`; raises `PinError(name)`.

    A platform entry that is missing or still holds placeholders gives `url`, `sha256`, `bytes` = None.
    """
    v = _read_json(code_root / "install" / "versions.json", "versions.json")
    python = _get(v, "python", dict)
    node = _get(v, "node", dict)
    claude = _get(v, "claude_code", dict)
    pnpm_section = v.get("pnpm") if isinstance(v.get("pnpm"), dict) else {}
    py_entry = _platform_entry(python, platform_key)  # type: ignore[arg-type]
    node_entry = _platform_entry(node, platform_key)  # type: ignore[arg-type]
    claude_entry = _platform_entry(claude, platform_key)  # type: ignore[arg-type]
    pnpm = _pnpm_version(code_root)
    if pnpm is None:
        raise PinError("packageManager")
    engine = _package_dep(code_root / "tools" / "zalo-agent" / "package.json", ENGINE_PACKAGE)
    if engine is None:
        raise PinError(ENGINE_PACKAGE)
    macos_min = _version_tuple(str(_get(v, "macos_min", str)))
    if not macos_min:
        raise PinError("macos_min")
    return Pins(
        macos_min=macos_min,
        disk_min_gb=int(_get(v, "disk_min_gb", int)),  # type: ignore[arg-type]
        python=RuntimePin(
            version=str(_get(v, "python.version", str)),
            url=_url_or_none(py_entry.get("url")),
            sha256=_hash_or_none(py_entry.get("sha256")),
            bytes=_bytes_or_none(py_entry.get("bytes")),
        ),
        python_min=str(_get(v, "python.min", str)),
        node=RuntimePin(
            version=str(_get(v, "node.version", str)),
            url=_url_or_none(node_entry.get("url")),
            sha256=_hash_or_none(node_entry.get("sha256")),
            bytes=_bytes_or_none(node_entry.get("bytes")),
        ),
        node_min_stack=str(_get(v, "node.min_stack", str)),
        node_min_rooms_major=int(_get(v, "node.min_rooms_major", int)),  # type: ignore[arg-type]
        pnpm_version=pnpm,
        pnpm_bytes=_bytes_or_none(pnpm_section.get("bytes")),
        claude=RuntimePin(
            version=str(_get(v, "claude_code.version", str)),
            url=_url_or_none(claude.get("installer_url")),  # type: ignore[union-attr]
            sha256=_hash_or_none(claude_entry.get("sha256")),
            bytes=_bytes_or_none(claude_entry.get("bytes")),
        ),
        claude_min=str(_get(v, "claude_code.min", str)),
        claude_approx_mb=int(_get(v, "claude_code.approx_installed_mb", int)),  # type: ignore[arg-type]
        engine_version=engine,
        openmausbot_version=_package_dep(code_root / "tools" / "openmausbot" / "package.json", ROOMS_PACKAGE),
    )


_SH_ENGINE = re.compile(r'^ENGINE_VERSION="([^"]+)"', re.M)
_PY_ENGINE = re.compile(r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']', re.M)


def _first(pattern: re.Pattern[str], path: Path) -> str | None:
    try:
        m = pattern.search(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1) if m else None


def agreement(code_root: Path) -> list[str]:
    """Names of the pins of 16.2.2 step 3 that disagree; [] when all agree.

    "zalo-agent-cli": `ENGINE_VERSION` of `scripts/start_local.sh` and of `apps/zalo-bridge/bridge/config.py`, the
    dependency in `tools/zalo-agent/package.json` and the root dependency of its `package-lock.json` must all exist
    and be equal. "openmausbot": when `tools/openmausbot/package.json` exists, its dependency must equal the root
    dependency of its lock. Values are never returned.
    """
    bad: list[str] = []
    engine_values = [
        _first(_SH_ENGINE, code_root / "scripts" / "start_local.sh"),
        _first(_PY_ENGINE, code_root / "apps" / "zalo-bridge" / "bridge" / "config.py"),
        _package_dep(code_root / "tools" / "zalo-agent" / "package.json", ENGINE_PACKAGE),
        _lock_root_dep(code_root / "tools" / "zalo-agent" / "package-lock.json", ENGINE_PACKAGE),
    ]
    if any(x is None for x in engine_values) or len(set(engine_values)) != 1:
        bad.append("zalo-agent-cli")
    rooms_pkg = code_root / "tools" / "openmausbot" / "package.json"
    if rooms_pkg.exists():
        rooms = _package_dep(rooms_pkg, ROOMS_PACKAGE)
        rooms_lock = _lock_root_dep(code_root / "tools" / "openmausbot" / "package-lock.json", ROOMS_PACKAGE)
        if rooms is None or rooms != rooms_lock:
            bad.append("openmausbot")
    return bad
