"""Stand-in for thomhouse_installer.release (WP2) in the setup tests: the functions steps.py calls.

A "release file" here is any existing file; `read_header` returns a fixed ReleaseInfo for the version in behaviour
"stub_release".version (default 1.4.0). `switch_app` and `write_launcher` act on APP_HOME like the real module;
`verify_manifest` checks the MANIFEST.json hashes; the menu functions use shared/menu-slides/<menu_id>.
Behaviour "stub_release": {"fail": function name or [names]} raises ReleaseError from that function.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from thomhouse_installer import _stubrec
from thomhouse_installer.context import InstallerError

MENU_DIR = "sources/drive-resources/thomhouse-menu"


class ReleaseError(InstallerError):
    code = 3

    def __init__(self, kind: str) -> None:
        super().__init__("core.failed", None)
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


def _check(name: str) -> None:
    if _stubrec.fails("release", name):
        raise ReleaseError("damaged")


def read_header(path: Path) -> ReleaseInfo:
    _stubrec.record("release", "read_header", path)
    _check("read_header")
    if not Path(path).is_file():
        raise ReleaseError("not_release")
    version = str(_stubrec.behaviour("release").get("version", "1.4.0"))
    return ReleaseInfo(version, Path(path), 0, 0, "ab" * 32, "ABCD-0123-4567-89EF", b"", "0" * 16)


def verify_file(ctx, path: Path, *, first_install: bool) -> ReleaseInfo:
    _stubrec.record("release", "verify_file", path, first_install)
    _check("verify_file")
    return read_header(path)


def unpack(ctx, info: ReleaseInfo) -> Path:
    _stubrec.record("release", "unpack", info.version)
    _check("unpack")
    return ctx.paths.release_dir(info.version)


def copy_to_cache(ctx, info: ReleaseInfo) -> Path:
    _stubrec.record("release", "copy_to_cache", info.version)
    target = ctx.paths.cache_releases / f"thomhouse-{info.version}.command"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(Path(info.path).read_bytes())
    os.chmod(target, 0o600)
    return target


def switch_app(ctx, version: str) -> None:
    _stubrec.record("release", "switch_app", version)
    _check("switch_app")
    _stubrec.replace_link(ctx.paths.app, f"releases/{version}")


def _launcher_text(ctx) -> str:
    p = ctx.paths
    return f'#!/bin/bash\nexec python3 -I "{p.app_home}/app/install/thomhouse.py" "$@"\n'


def write_launcher(ctx, code_root: Path) -> bool:
    _stubrec.record("release", "write_launcher", code_root)
    if launcher_current(ctx, code_root):
        return False
    _stubrec.write_exec(ctx.paths.launcher, _launcher_text(ctx))
    os.chmod(ctx.paths.launcher, 0o700)
    return True


def launcher_current(ctx, code_root: Path) -> bool:
    try:
        return ctx.paths.launcher.read_text(encoding="utf-8") == _launcher_text(ctx)
    except OSError:
        return False


def verify_manifest(code_root: Path) -> list[str]:
    root = Path(code_root)
    try:
        entries = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["MANIFEST.json"]
    bad = []
    for entry in entries:
        if entry.get("runtime_written"):
            continue
        f = root / entry["path"]
        try:
            if hashlib.sha256(f.read_bytes()).hexdigest() != entry["sha256"]:
                bad.append(entry["path"])
        except OSError:
            bad.append(entry["path"])
    return bad


def denylist(code_root: Path) -> list[str]:
    return []


def denylisted(rel_path: str, patterns: list[str]) -> bool:
    return False


def prune(ctx, keep_previous: int = 1) -> None:
    _stubrec.record("release", "prune", keep_previous)


def install_menu(ctx, menu_tar: Path) -> str:
    _stubrec.record("release", "install_menu", menu_tar)
    _check("install_menu")
    menu_id = Path(menu_tar).name[len("thomhouse-menu-"):-len(".tar")]
    folder = ctx.paths.shared / "menu-slides" / menu_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "MENU.json").write_text(json.dumps({"schema": 1, "menu_id": menu_id, "files": []}), encoding="utf-8")
    return menu_id


def link_menu(ctx, code_root: Path, menu_id: str) -> bool:
    _stubrec.record("release", "link_menu", code_root, menu_id)
    _stubrec.replace_link(Path(code_root) / MENU_DIR, str(ctx.paths.shared / "menu-slides" / menu_id))
    return True


def menu_slides_ok(ctx, code_root: Path) -> bool:
    _stubrec.record("release", "menu_slides_ok", code_root)
    link = Path(code_root) / MENU_DIR
    return link.is_symlink() and (link / "MENU.json").is_file()
