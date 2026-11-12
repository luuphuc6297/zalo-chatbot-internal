#!/usr/bin/env python3
"""Build the JPEG copies of the menu slides that the Zalo bridge sends (task B, menu images).

  python3 -I scripts/build_menu_images.py [--home ~/.thomhouse-bot] [--check] [--force] [--quiet]

Reads data/menu-images.json (the slide index) and writes, for every slide, a JPEG copy with the long side at most
1600 px and quality 85, made with macOS `sips`, to <home>/menu-images/<group>/<n>.jpg, plus
<home>/menu-images/manifest.json: {"images": {"<group>/<n>": {"path", "sha256", "bytes", "width", "height",
"has_medical_claim", ...}}}. The bridge resolves image keys to files only through this manifest and checks sha256.

Idempotent: a slide whose source file (size + mtime) and settings are unchanged and whose JPEG still matches the
recorded sha256 is skipped. JPEGs of slides no longer in the index are removed. Files are replaced atomically.
Exit codes: 0 up to date (or built), 1 --check found work to do, 2 cannot build (no sips, index unreadable, a slide
failed). scripts/start_local.sh runs it on every start and never stops the start when it fails.
Output names slide keys and counts only.
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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "menu-images.json"
MAX_LONG_SIDE = 1600
QUALITY = 85
MANIFEST_VERSION = 1
KEY_RE = re.compile(r"^(facial|healing|thu-gian-toc|hair-removal)/([1-9][0-9]?)$")
SIPS_TIMEOUT_S = 60


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_index(path: Path = INDEX) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("slides"), list):
        raise ValueError("index has no slides list")
    for s in data["slides"]:
        if not isinstance(s, dict) or not KEY_RE.match(str(s.get("key", ""))):
            raise ValueError(f"bad slide key: {s.get('key') if isinstance(s, dict) else s!r}")
        if s["key"] != f"{s.get('group')}/{s.get('n')}":
            raise ValueError(f"slide key does not match group/n: {s['key']}")
    return data


def find_sips(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
    return shutil.which("sips")


def image_size(sips: str, path: Path) -> tuple[int | None, int | None]:
    try:
        out = subprocess.run([sips, "-g", "pixelWidth", "-g", "pixelHeight", str(path)], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=SIPS_TIMEOUT_S).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    w = re.search(r"pixelWidth:\s*(\d+)", out)
    h = re.search(r"pixelHeight:\s*(\d+)", out)
    return (int(w.group(1)) if w else None), (int(h.group(1)) if h else None)


def convert(sips: str, src: Path, dst: Path) -> None:
    """sips: JPEG, quality QUALITY, long side at most MAX_LONG_SIDE (-Z never upscales a smaller image)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".jpg", dir=dst.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        r = subprocess.run([sips, "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY), "-Z", str(MAX_LONG_SIDE),
                            str(src), "--out", str(tmp)], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=SIPS_TIMEOUT_S)
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError(f"sips exit {r.returncode}")
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("images"), dict) else {"images": {}}
    except (OSError, ValueError):
        return {"images": {}}


def entry_is_current(entry: dict | None, src: Path, out_dir: Path, rel: str) -> bool:
    if not isinstance(entry, dict):
        return False
    try:
        st = src.stat()
    except OSError:
        return False
    if entry.get("path") != rel or entry.get("source_size") != st.st_size or entry.get("source_mtime_ns") != st.st_mtime_ns:
        return False
    if entry.get("max_long_side") != MAX_LONG_SIDE or entry.get("quality") != QUALITY:
        return False
    dst = out_dir / rel
    return dst.is_file() and dst.stat().st_size == entry.get("bytes") and sha256_file(dst) == entry.get("sha256")


def build(home: Path, *, check: bool = False, force: bool = False, sips: str | None = None, root: Path = ROOT,
          index_path: Path | None = None, log=print) -> int:
    try:
        index = load_index(index_path or root / "data" / "menu-images.json")
    except (OSError, ValueError) as e:
        log(f"menu index unreadable: {type(e).__name__}: {e}")
        return 2
    out_dir = home / "menu-images"
    manifest_path = out_dir / "manifest.json"
    old = read_manifest(manifest_path)
    images: dict[str, dict] = {}
    built = 0
    todo: list[tuple[dict, Path, str]] = []
    missing: list[str] = []
    for s in index["slides"]:
        key = s["key"]
        src = root / s["file"]
        rel = f"{s['group']}/{s['n']}.jpg"
        if not src.is_file():
            missing.append(key)
            continue
        entry = old["images"].get(key)
        if not force and entry_is_current(entry, src, out_dir, rel):
            images[key] = dict(entry, has_medical_claim=bool(s.get("has_medical_claim")), kind=s.get("kind"))
        else:
            todo.append((s, src, rel))
    keep = {f"{s['group']}/{s['n']}.jpg" for s in index["slides"]}
    stale = sorted(str(p.relative_to(out_dir)) for p in out_dir.glob("*/*.jpg") if str(p.relative_to(out_dir)) not in keep) \
        if out_dir.is_dir() else []
    flags_changed = any(old["images"].get(k, {}).get("has_medical_claim") != v.get("has_medical_claim") for k, v in images.items())
    if missing:
        log(f"source slides missing: {', '.join(missing)}")
    if check:
        outdated = bool(todo or stale or missing or flags_changed or not manifest_path.exists())
        log(f"menu images: {len(images)} current, {len(todo)} to build, {len(stale)} stale" + (" (outdated)" if outdated else ""))
        return 1 if outdated else 0
    if todo:
        exe = find_sips(sips)
        if not exe:
            log("sips not found (macOS only); menu images not built")
            return 2
        failed = []
        for s, src, rel in todo:
            dst = out_dir / rel
            try:
                convert(exe, src, dst)
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
                failed.append(s["key"])
                log(f"{s['key']}: conversion failed ({type(e).__name__})")
                continue
            w, h = image_size(exe, dst)
            st = src.stat()
            images[s["key"]] = {"path": rel, "sha256": sha256_file(dst), "bytes": dst.stat().st_size, "width": w,
                                "height": h, "source": s["file"], "source_size": st.st_size,
                                "source_mtime_ns": st.st_mtime_ns, "max_long_side": MAX_LONG_SIDE, "quality": QUALITY,
                                "has_medical_claim": bool(s.get("has_medical_claim")), "kind": s.get("kind")}
            built += 1
        if failed:
            missing.extend(failed)
    for rel in stale:
        try:
            (out_dir / rel).unlink()
        except OSError:
            pass
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"version": MANIFEST_VERSION, "generated_at": int(time.time() * 1000),
                "index": "data/menu-images.json", "index_sha256": sha256_file(index_path or root / "data" / "menu-images.json"),
                "max_long_side": MAX_LONG_SIDE, "quality": QUALITY,
                "images": {k: images[k] for k in sorted(images)}}
    fd, tmp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".json", dir=out_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_name, 0o644)
    os.replace(tmp_name, manifest_path)
    log(f"menu images: {len(images)} ready ({built} built), {len(stale)} stale removed, {len(missing)} missing")
    return 2 if missing else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", default=os.environ.get("THOMHOUSE_BOT_HOME", "~/.thomhouse-bot"))
    ap.add_argument("--check", action="store_true", help="exit 1 when anything is missing or outdated; write nothing")
    ap.add_argument("--force", action="store_true", help="rebuild every JPEG")
    ap.add_argument("--quiet", action="store_true", help="print only problems")
    ap.add_argument("--sips", default=None, help=argparse.SUPPRESS)
    ns = ap.parse_args(argv)
    lines: list[str] = []
    code = build(Path(os.path.expanduser(ns.home)), check=ns.check, force=ns.force, sips=ns.sips, root=ROOT,
                 log=lines.append)
    for line in lines:
        if not ns.quiet or code != 0:
            print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
