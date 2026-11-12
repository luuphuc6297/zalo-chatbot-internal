"""Stand-in for WP2 `release.py` in the operations tests (16.3.3 signatures only).

A stub "release file" is JSON: {"stub_release": 1, "version", "menu_id", "tree" (a prepared release folder),
"release_id", "payload_sha256", "bad": null | "damaged" | "signature" | "denylisted"}. `unpack` copies the tree into
APP_HOME/releases/<version>; `switch_app` replaces the relative `app` link; `write_launcher` writes a one-line
launcher naming the release it was rendered from. tests/test_integration_flows.py runs update and rollback with the
real module and real signed release files.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import _stubio
from .context import InstallerError


class ReleaseError(InstallerError):
    code = 3

    def __init__(self, kind: str) -> None:
        super().__init__(f"release.{kind}", 3)
        self.kind = kind


@dataclass
class ReleaseInfo:
    version: str
    path: Path
    payload_offset: int
    payload_bytes: int
    payload_sha256: str
    release_id: str
    signature: bytes
    menu_id: str


def read_header(path: Path) -> ReleaseInfo:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ReleaseError("not_release") from None
    if not isinstance(data, dict) or data.get("stub_release") != 1:
        raise ReleaseError("not_release")
    return ReleaseInfo(version=data["version"], path=Path(path), payload_offset=0, payload_bytes=0,
                       payload_sha256=data.get("payload_sha256") or "0" * 64,
                       release_id=data.get("release_id") or "STUB-0000-0000-0000", signature=b"",
                       menu_id=data.get("menu_id") or "0" * 16)


def verify_file(ctx, path: Path, *, first_install: bool) -> ReleaseInfo:
    info = read_header(path)
    bad = json.loads(Path(path).read_text(encoding="utf-8")).get("bad")
    _stubio.record("release.verify_file", path=str(path), first_install=first_install, bad=bad)
    if bad:
        raise ReleaseError(bad)
    return info


def _tree(info: ReleaseInfo) -> Path:
    return Path(json.loads(info.path.read_text(encoding="utf-8"))["tree"])


def unpack(ctx, info: ReleaseInfo) -> Path:
    dest = ctx.paths.releases / info.version
    _stubio.record("release.unpack", version=info.version)
    if _stubio.behaviour().get("fail_unpack"):
        raise ReleaseError("damaged")
    if not (dest / "VERSION.json").is_file():
        staging = ctx.paths.releases / f".staging-{info.version}"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(_tree(info), staging, symlinks=True)
        os.replace(staging, dest)
    return dest


def copy_to_cache(ctx, info: ReleaseInfo) -> Path:
    dest = ctx.paths.cache_releases / f"thomhouse-{info.version}.command"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(info.path, dest)
    os.chmod(dest, 0o600)
    _stubio.record("release.copy_to_cache", version=info.version)
    return dest


def switch_app(ctx, version: str) -> None:
    app = ctx.paths.app_home / "app"
    tmp = ctx.paths.app_home / ".app.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("releases") / version)
    os.replace(tmp, app)
    _stubio.record("release.switch_app", version=version)


def _version_of(code_root: Path) -> str:
    try:
        return json.loads((Path(code_root) / "VERSION.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def write_launcher(ctx, code_root: Path) -> bool:
    version = _version_of(code_root)
    launcher = ctx.paths.launcher
    launcher.parent.mkdir(parents=True, exist_ok=True)
    text = f"#!/bin/bash\n# stub launcher rendered from release {version}\n"
    same = launcher.is_file() and launcher.read_text(encoding="utf-8") == text
    launcher.write_text(text, encoding="utf-8")
    os.chmod(launcher, 0o700)
    _stubio.record("release.write_launcher", code_root=str(code_root), version=version)
    return not same


def launcher_current(ctx, code_root: Path) -> bool:
    return ctx.paths.launcher.is_file()


def verify_manifest(code_root: Path) -> list[str]:
    return []


def denylist(code_root: Path) -> list[str]:
    return []


def denylisted(rel_path: str, patterns: list[str]) -> bool:
    return False


def prune(ctx, keep_previous: int = 1) -> None:
    _stubio.record("release.prune", keep_previous=keep_previous)


def install_menu(ctx, menu_tar: Path) -> str:
    _stubio.record("release.install_menu", tar=str(menu_tar))
    name = Path(menu_tar).name
    return name[len("thomhouse-menu-"):-len(".tar")] if name.startswith("thomhouse-menu-") else "0" * 16


def link_menu(ctx, code_root: Path, menu_id: str) -> bool:
    _stubio.record("release.link_menu", code_root=str(code_root), menu_id=menu_id)
    return True


def menu_slides_ok(ctx, code_root: Path) -> bool:
    return True
