"""Resolve menu image keys ('<group>/<n>') of a cs_images outbox row to local JPEG files.

The server only ever sends keys. The files and their sha256 come from <menu_images_dir>/manifest.json, written by
scripts/build_menu_images.py from data/menu-images.json. A key is accepted only when it matches the key pattern, is in
the manifest, its file stays inside menu_images_dir (no `..`, no symlink escape), is a regular .jpg file, and its
sha256 equals the manifest's. Anything else is an explicit refusal before `zalo-agent` runs, so nothing is sent.
Error strings name keys and reasons only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

KEY_RE = re.compile(r"^(facial|healing|thu-gian-toc|hair-removal)/([1-9][0-9]?)$")
MAX_IMAGES = 10


class MenuImageError(Exception):
    """A key that cannot be sent; str() is short and safe for logs and the result's error field."""


@dataclass(frozen=True)
class ResolvedImage:
    key: str
    path: Path
    sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(menu_dir: Path) -> dict:
    try:
        data = json.loads((menu_dir / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MenuImageError("manifest_missing: run scripts/build_menu_images.py") from None
    except (OSError, ValueError):
        raise MenuImageError("manifest_unreadable") from None
    if not isinstance(data, dict) or not isinstance(data.get("images"), dict):
        raise MenuImageError("manifest_unreadable")
    return data


def resolve(menu_dir: Path, keys) -> list[ResolvedImage]:
    """Keys -> verified local files, in order. Raises MenuImageError for the first problem."""
    if not isinstance(keys, list) or not keys:
        raise MenuImageError("invalid_item: images is empty")
    if len(keys) > MAX_IMAGES:
        raise MenuImageError(f"invalid_item: more than {MAX_IMAGES} images")
    if len(set(map(str, keys))) != len(keys):
        raise MenuImageError("invalid_item: duplicate image keys")
    base = Path(menu_dir).resolve()
    images = load_manifest(base)["images"]
    out: list[ResolvedImage] = []
    for key in keys:
        if not isinstance(key, str) or not KEY_RE.match(key):
            raise MenuImageError("invalid_item: bad image key")
        entry = images.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
            raise MenuImageError(f"menu_image_unavailable: {key} not in manifest")
        path = (base / entry["path"]).resolve()
        if base not in path.parents or path.suffix.lower() not in (".jpg", ".jpeg"):
            raise MenuImageError(f"menu_image_unavailable: {key} path outside the menu folder")
        if not path.is_file():
            raise MenuImageError(f"menu_image_unavailable: {key} file missing")
        if _sha256(path) != entry["sha256"]:
            raise MenuImageError(f"menu_image_unavailable: {key} sha256 mismatch")
        out.append(ResolvedImage(key=key, path=path, sha256=entry["sha256"]))
    return out
