#!/usr/bin/env python3
"""Refresh the runtime pins of install/versions.json on the build Mac (docs/contracts.md 16.2.2). Needs the network.

    python3 -I scripts/release/refresh_pins.py [--python 3.14.6] [--node 24.19.0] [--claude 2.1.319]
                                              [--platforms darwin-arm64,darwin-x64] [--pbs-release TAG]

Downloads https://nodejs.org/dist/v<node>/SHASUMS256.txt and the SHA256SUMS list of a python-build-standalone
release (the newest one that has every requested `install_only` archive, or --pbs-release) over HTTPS, and writes
URL, SHA-256 and byte size per platform into install/versions.json with "hash_source": "https". It regenerates
install/lock/pnpm/package-lock.json with `npm install --package-lock-only --ignore-scripts` in a temporary folder from
install/lock/pnpm/package.json and records the byte size of the pnpm tarball named by the lock's `resolved` URL. It
records claude_code.platforms.darwin-arm64.{sha256, bytes} from this Mac's own binary
~/.local/share/claude/versions/<claude> (no network); darwin-x64 stays null (rev F22). --claude also sets
claude_code.min, because the pinned version is the one tested. Platforms not asked for keep their entries.
It never edits any other file. Exit codes: 0 written; 1 a download, a checksum list, the pnpm lock or the Claude
binary is missing (nothing written); 2 bad arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
VERSIONS = PROJECT / "install" / "versions.json"
LOCK_DIR = PROJECT / "install" / "lock" / "pnpm"
PBS_API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases"
TRIPLES = {"darwin-arm64": "aarch64-apple-darwin", "darwin-x64": "x86_64-apple-darwin"}
PLATFORMS = tuple(TRIPLES)
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class RefreshError(Exception):
    """Something needed is missing; nothing is written."""


# ---------------------------------------------------------------- network (replaced in the offline tests)

def _https_only(url: str) -> None:
    if not url.startswith("https://"):
        raise RefreshError(f"not an https URL: {url}")


def fetch_bytes(url: str) -> bytes:
    """GET `url` over HTTPS (proxy variables of the environment are honoured)."""
    _https_only(url)
    req = urllib.request.Request(url, headers={"User-Agent": "thomhouse-refresh-pins"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except OSError as e:
        raise RefreshError(f"download failed: {url} ({type(e).__name__})") from None


def fetch_size(url: str) -> int:
    """Content-Length of `url` from a HEAD request (redirects followed)."""
    _https_only(url)
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "thomhouse-refresh-pins"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            size = resp.headers.get("Content-Length")
    except OSError as e:
        raise RefreshError(f"size request failed: {url} ({type(e).__name__})") from None
    if not size or not size.isdigit() or int(size) <= 0:
        raise RefreshError(f"no size for {url}")
    return int(size)


# ---------------------------------------------------------------- pins

def parse_sums(text: str) -> dict[str, str]:
    """`<sha256>  <name>` lines (SHASUMS256.txt, SHA256SUMS) as {name: sha256}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and _HEX64.match(parts[0].lower()):
            out[parts[1].lstrip("*")] = parts[0].lower()
    return out


def node_pins(version: str, platforms: list[str]) -> dict[str, dict]:
    base = f"https://nodejs.org/dist/v{version}"
    sums = parse_sums(fetch_bytes(f"{base}/SHASUMS256.txt").decode("utf-8", errors="replace"))
    out = {}
    for plat in platforms:
        name = f"node-v{version}-{plat}.tar.gz"
        if name not in sums:
            raise RefreshError(f"SHASUMS256.txt of Node.js {version} has no {name}")
        url = f"{base}/{name}"
        out[plat] = {"url": url, "sha256": sums[name], "bytes": fetch_size(url)}
    return out


def _pbs_asset_name(version: str, tag: str, plat: str) -> str:
    return f"cpython-{version}+{tag}-{TRIPLES[plat]}-install_only.tar.gz"


def python_pins(version: str, platforms: list[str], tag: str | None = None) -> dict[str, dict]:
    if tag:
        releases = [json.loads(fetch_bytes(f"{PBS_API}/tags/{tag}"))]
    else:
        releases = json.loads(fetch_bytes(f"{PBS_API}?per_page=30"))
    if not isinstance(releases, list):
        raise RefreshError("python-build-standalone: unexpected release list")
    for release in releases:
        rtag = release.get("tag_name") if isinstance(release, dict) else None
        if not isinstance(rtag, str):
            continue
        assets = {a.get("name"): a for a in release.get("assets") or [] if isinstance(a, dict)}
        wanted = {plat: _pbs_asset_name(version, rtag, plat) for plat in platforms}
        if not all(name in assets for name in wanted.values()) or "SHA256SUMS" not in assets:
            continue
        sums = parse_sums(fetch_bytes(assets["SHA256SUMS"]["browser_download_url"]).decode("utf-8", "replace"))
        out = {}
        for plat, name in wanted.items():
            if name not in sums:
                raise RefreshError(f"SHA256SUMS of python-build-standalone {rtag} has no {name}")
            asset = assets[name]
            size = asset.get("size")
            url = asset.get("browser_download_url")
            if not isinstance(size, int) or size <= 0 or not isinstance(url, str):
                raise RefreshError(f"python-build-standalone {rtag}: no size or URL for {name}")
            _https_only(url)
            out[plat] = {"url": url, "sha256": sums[name], "bytes": size}
        return out
    raise RefreshError(f"no python-build-standalone release has Python {version} for {', '.join(platforms)}")


def pnpm_version() -> str:
    data = json.loads((PROJECT / "package.json").read_text(encoding="utf-8"))
    pm = data.get("packageManager") or ""
    if not pm.startswith("pnpm@"):
        raise RefreshError("package.json: packageManager is not pnpm@X.Y.Z")
    return pm[len("pnpm@"):].split("+", 1)[0]


def pnpm_lock(version: str) -> tuple[bytes, int]:
    """(package-lock.json bytes, pnpm tarball size) from `npm install --package-lock-only` in a temporary folder."""
    try:
        pkg = json.loads((LOCK_DIR / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RefreshError("install/lock/pnpm/package.json is missing or not JSON") from None
    if (pkg.get("dependencies") or {}).get("pnpm") != version:
        raise RefreshError("install/lock/pnpm/package.json: pnpm differs from packageManager")
    with tempfile.TemporaryDirectory(prefix="thomhouse-pnpm-lock-") as d:
        shutil.copyfile(LOCK_DIR / "package.json", Path(d) / "package.json")
        res = subprocess.run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                             cwd=d, stdin=subprocess.DEVNULL)
        lock_path = Path(d) / "package-lock.json"
        if res.returncode != 0 or not lock_path.is_file():
            raise RefreshError("npm install --package-lock-only failed")
        raw = lock_path.read_bytes()
    lock = json.loads(raw)
    root = (lock.get("packages") or {}).get("") or {}
    if (root.get("dependencies") or {}).get("pnpm") != version:
        raise RefreshError("the new pnpm lock does not pin pnpm " + version)
    entry = (lock.get("packages") or {}).get("node_modules/pnpm") or {}
    url = entry.get("resolved")
    if not isinstance(url, str) or not isinstance(entry.get("integrity"), str):
        raise RefreshError("the new pnpm lock has no resolved URL or integrity for pnpm")
    return raw, fetch_size(url)


def claude_pin(version: str) -> dict:
    binary = Path.home() / ".local" / "share" / "claude" / "versions" / version
    if not binary.is_file():
        raise RefreshError(f"Claude Code {version} is not installed on this Mac ({binary})")
    h = hashlib.sha256()
    with open(binary, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "bytes": binary.stat().st_size}


# ---------------------------------------------------------------- main

def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _version(text: str) -> str:
    if not _VERSION.match(text):
        raise argparse.ArgumentTypeError("a version is MAJOR.MINOR.PATCH")
    return text


def _platforms(text: str) -> list[str]:
    items = [x.strip() for x in text.split(",") if x.strip()]
    if not items or any(x not in PLATFORMS for x in items):
        raise argparse.ArgumentTypeError("platforms are darwin-arm64 and darwin-x64")
    return items


def refresh(args: argparse.Namespace) -> tuple[dict, bytes]:
    """The new versions.json document and pnpm lock bytes; raises RefreshError and writes nothing."""
    data = json.loads(VERSIONS.read_text(encoding="utf-8"))
    py_v = args.python or data["python"]["version"]
    node_v = args.node or data["node"]["version"]
    claude_v = args.claude or data["claude_code"]["version"]
    platforms = args.platforms or ["darwin-arm64"]
    py = python_pins(py_v, platforms, args.pbs_release)
    node = node_pins(node_v, platforms)
    lock_bytes, pnpm_bytes = pnpm_lock(pnpm_version())
    claude = claude_pin(claude_v)
    data["python"]["version"] = py_v
    data["node"]["version"] = node_v
    data["claude_code"]["version"] = claude_v
    if args.claude:
        data["claude_code"]["min"] = claude_v
    for plat in platforms:
        data["python"].setdefault("platforms", {})[plat] = py[plat]
        data["node"].setdefault("platforms", {})[plat] = node[plat]
    data.setdefault("pnpm", {})["bytes"] = pnpm_bytes
    plats = data["claude_code"].setdefault("platforms", {})
    plats["darwin-arm64"] = claude
    plats["darwin-x64"] = {"sha256": None, "bytes": None}
    data["hash_source"] = "https"
    return data, lock_bytes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="refresh_pins.py", description="Refresh install/versions.json (16.2.2).")
    p.add_argument("--python", type=_version, metavar="X.Y.Z")
    p.add_argument("--node", type=_version, metavar="X.Y.Z")
    p.add_argument("--claude", type=_version, metavar="X.Y.Z")
    p.add_argument("--platforms", type=_platforms, metavar="LIST", help="darwin-arm64 (default) and/or darwin-x64")
    p.add_argument("--pbs-release", metavar="TAG", help="python-build-standalone release tag (default: newest match)")
    args = p.parse_args(argv)
    try:
        data, lock_bytes = refresh(args)
    except (RefreshError, OSError, ValueError, KeyError) as e:
        print(f"refresh failed, nothing written: {e}", file=sys.stderr)
        return 1
    _write(LOCK_DIR / "package-lock.json", lock_bytes)
    _write(VERSIONS, (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"wrote {VERSIONS} and {LOCK_DIR / 'package-lock.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
