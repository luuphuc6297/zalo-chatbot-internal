"""Verified downloads with curl into `APP_HOME/cache/downloads` (16.2.6, rev F11, F18).

A pin whose SHA-256 is still the documented placeholder (`null` in `install/versions.json`, `None` in `Pins`) is never
downloaded: `fetch` raises `PinError` before any curl call.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .context import InstallerError
from .pins import PinError

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CACHE_NAME = re.compile(r"^[0-9a-f]{64}\.")
NETWORK_CODES = (6, 7, 28, 35)
HTTP_CODES = (22,)
DISK_CODES = (23,)  # curl could not write the file, for example on a full disk
KINDS = ("not_https", "network", "http", "size", "checksum", "disk")


class DownloadError(InstallerError):
    """A download failed; `kind` is not_https, network, http, size, checksum or disk. Exit code 1, key
    `core.download_<kind>` with {name} and {host}."""

    code = 1

    def __init__(self, kind: str, name: str, *, host: str = "") -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown download error kind {kind!r}")
        super().__init__(f"core.download_{kind}", None, name=name, host=host)
        self.kind = kind
        self.name = name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ext(url: str) -> str:
    name = urlsplit(url).path.rsplit("/", 1)[-1].lower()
    for ext in (".tar.gz", ".tar.xz", ".tar.zst", ".tgz", ".zip", ".sh", ".json", ".txt"):
        if name.endswith(ext):
            return ext
    if "." in name:
        return "." + name.rsplit(".", 1)[-1]
    return ".bin"


def _matches(path: Path, sha256: str, size: int | None) -> bool:
    try:
        if size is not None and path.stat().st_size != size:
            return False
        return _sha256(path) == sha256
    except OSError:
        return False


def _find_in_cache(folder: Path, target: Path, sha256: str, size: int | None) -> Path | None:
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return None
    for f in entries:
        if f == target or f.name.endswith(".part") or f.name.startswith("."):
            continue
        if not f.is_file() or f.is_symlink():
            continue
        if _CACHE_NAME.match(f.name) and not f.name.startswith(sha256):
            continue  # another pin's verified file; its name is its hash
        if _matches(f, sha256, size):
            return f
    return None


def fetch(ctx, url: str, sha256: str, size: int | None, *, name: str) -> Path:
    """Return `cache/downloads/<sha256>.<ext>` holding the verified file.

    Before any call: `PinError(name)` when `url` or `sha256` is a placeholder (None, or not 64 hex characters);
    `DownloadError("not_https")` for a URL that is not https. Reuses the cache file, or any other regular file in
    `cache/downloads` whose SHA-256 matches (renamed to the cache name), with no curl call (rev F11). Otherwise
    `curl --proto =https --tlsv1.2 -fL --retry 3 -C - -o <sha256>.part <url>` (output in logs/runtimes.log), then
    the size and hash checks and the rename. curl 6, 7, 28, 35 give `network`, 22 `http`, 23 (write error) and
    ENOSPC on the rename `disk`, any other failure `network`; a wrong size or hash deletes the .part file and gives
    `size` or `checksum`.
    """
    from . import proc

    want = (sha256 or "").lower()
    if not url or not _HEX64.match(want):
        raise PinError(name)
    host = urlsplit(url).hostname or ""
    if urlsplit(url).scheme != "https":
        raise DownloadError("not_https", name, host=host)
    folder = ctx.paths.downloads
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    target = folder / f"{want}{_ext(url)}"
    if target.is_file():
        if _matches(target, want, size):
            return target
        target.unlink()
    found = _find_in_cache(folder, target, want, size)
    if found is not None:
        os.replace(found, target)
        ctx.log("download_reused", name=name)
        return target
    part = folder / f"{want}.part"
    complete_part = part.is_file() and size is not None and part.stat().st_size == size
    if not complete_part:
        res = proc.run(
            ctx,
            ["curl", "--proto", "=https", "--tlsv1.2", "-fL", "--retry", "3", "-C", "-", "-o", str(part), url],
            log=ctx.paths.logs / "runtimes.log",
        )
        if res.returncode != 0:
            ctx.log("download_failed", name=name, curl_exit=res.returncode)
            if res.returncode in HTTP_CODES:
                raise DownloadError("http", name, host=host)
            if res.returncode in DISK_CODES:
                raise DownloadError("disk", name, host=host)
            raise DownloadError("network", name, host=host)
    if size is not None and (not part.is_file() or part.stat().st_size != size):
        part.unlink(missing_ok=True)
        raise DownloadError("size", name, host=host)
    if not part.is_file() or _sha256(part) != want:
        part.unlink(missing_ok=True)
        raise DownloadError("checksum", name, host=host)
    try:
        os.replace(part, target)
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise DownloadError("disk", name, host=host) from e
        raise
    ctx.log("download_done", name=name)
    return target
