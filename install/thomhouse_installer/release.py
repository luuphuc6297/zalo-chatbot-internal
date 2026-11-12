"""Release files on a device: read the header as data, verify, unpack, switch `app`, the launcher, the denylist,
pruning and the menu slides (16.2.5 to 16.2.7, rev F5, F10, iface).

A release file is `thomhouse-<ver>.command`: a bash header with six variables, one marker line, then the signed
payload (a deterministic tar.gz of `thomhouse-<ver>/...`). Installed code never executes a release file: the header
variables are parsed as text only to find the payload, and everything that matters is checked on the payload
itself (its SHA-256, its SSH signature, its own VERSION.json and MANIFEST.json).

The glob helpers, `versions_env()` and `menu_id_of()` are shared with `scripts/release/make_release.py` (WP2).
"""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .context import InstallerError

MARKER = b"\n" + b"__PAY" + b"LOAD__" + b"\n"  # the marker line; written in two parts so no code holds it whole
HEADER_VARS = ("RELEASE_VERSION", "PAYLOAD_SHA256", "PAYLOAD_BYTES", "PAYLOAD_SIG_B64", "MENU_ID", "BUILT_AT")
SIGNER = "thomhouse-release"
NAMESPACE = "thomhouse-release"
KINDS = ("damaged", "signature", "not_release", "older", "same", "denylisted")
MENU_DIR = "sources/drive-resources/thomhouse-menu"
RUNTIME_WRITTEN = ("apps/server/src/seed-data.ts",)
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_HEADER_LINE = re.compile(r'^([A-Z0-9_]+)="([^"\\$`]*)"\s*$')


class ReleaseError(InstallerError):
    """A release file was refused; `kind` is damaged, signature, not_release, older, same or denylisted.
    Exit code 3, key `release.<kind>`."""

    code = 3

    def __init__(self, kind: str, **fmt: object) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown release error kind {kind!r}")
        super().__init__("release." + kind, None, **fmt)
        self.kind = kind


@dataclass
class ReleaseInfo:
    """What a release file holds. `release_id` is the first 16 hex characters of the SHA-256 of the whole file,
    upper case, in four groups (`3F9A-21C7-0B44-D1E8`, as `installed.json` stores it, rev F5)."""

    version: str
    path: Path
    payload_offset: int
    payload_bytes: int
    payload_sha256: str
    release_id: str
    signature: bytes
    menu_id: str


# ---------------------------------------------------------------- small helpers

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def version_tuple(text: str) -> tuple[int, ...]:
    """`"1.4.0"` -> (1, 4, 0); pieces that are not digits end the tuple."""
    out = []
    for piece in str(text).split("."):
        if not piece.isdigit():
            break
        out.append(int(piece))
    return tuple(out)


def compare_versions(installed: str, new: str) -> None:
    """Raise `ReleaseError("older")` or `ReleaseError("same")` when `new` is not newer than `installed`
    (16.8.1 U1; WP5 may compare itself, this is the WP2 helper its tests use)."""
    a, b = version_tuple(installed), version_tuple(new)
    if b < a:
        raise ReleaseError("older")
    if b == a:
        raise ReleaseError("same")


def group_id(hex16: str) -> str:
    """`3f9a21c70b44d1e8` -> `3F9A-21C7-0B44-D1E8`."""
    h = hex16.upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def _rmtree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _replace_link(link: Path, target: str) -> None:
    """Point the symlink `link` at `target` through a temporary link and `os.replace` (atomic)."""
    tmp = link.with_name(f".{link.name}.tmp-{os.getpid()}")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------- globs (allowlist and denylist)

@functools.lru_cache(maxsize=512)
def glob_regex(pattern: str) -> re.Pattern[str]:
    """A glob as a regular expression over a relative path: `*` and `?` stay inside one folder, `**/` is any
    number of folders (also none), a trailing `/**` is everything below, any other `**` is any text."""
    i, out, p = 0, [], pattern.strip()
    while i < len(p):
        if p.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif p.startswith("/**", i) and i + 3 == len(p):
            out.append("/.+")
            i += 3
        elif p.startswith("**", i):
            out.append(".*")
            i += 2
        elif p[i] == "*":
            out.append("[^/]*")
            i += 1
        elif p[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(p[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(rel_path: str, pattern: str) -> bool:
    """True when `rel_path` (a/b/c, no leading slash) matches the glob `pattern`."""
    return bool(glob_regex(pattern).match(rel_path))


def denylist(code_root: Path) -> list[str]:
    """The patterns of `code_root/install/denylist.txt` (16.2.4): one glob per line, `!glob` an exception, `#`
    comments; [] when the file is missing."""
    try:
        text = (Path(code_root) / "install" / "denylist.txt").read_text(encoding="utf-8")
    except OSError:
        return []
    return _patterns(text)


def _patterns(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def denylisted(rel_path: str, patterns: list[str]) -> bool:
    """True when `rel_path` or one of its parent folders matches a pattern and no `!` exception matches the path."""
    rel = rel_path.strip("/")
    if any(p.startswith("!") and glob_match(rel, p[1:]) for p in patterns):
        return False
    parts = rel.split("/")
    candidates = ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]
    return any(glob_match(c, p) for p in patterns if not p.startswith("!") for c in candidates)


# ---------------------------------------------------------------- shared with make_release.py

def versions_env(data: dict, pnpm_version: str) -> str:
    """`install/versions.env` (16.2.5): the pins of `versions.json` (and the pnpm version of `packageManager`) as
    KEY=value lines for bash; null is an empty value."""

    def val(v: object) -> str:
        if v is None:
            return ""
        return str(v)

    def plat(section: dict, key: str) -> dict:
        p = (section.get("platforms") or {}).get(key)
        return p if isinstance(p, dict) else {}

    py, node, claude = data.get("python") or {}, data.get("node") or {}, data.get("claude_code") or {}
    pnpm = data.get("pnpm") or {}
    lines = [
        f"MACOS_MIN={val(data.get('macos_min'))}",
        f"DISK_MIN_GB={val(data.get('disk_min_gb'))}",
        f"PY_VERSION={val(py.get('version'))}",
    ]
    for key, var in (("darwin-arm64", "darwin_arm64"), ("darwin-x64", "darwin_x64")):
        e = plat(py, key)
        lines += [f"PY_URL_{var}={val(e.get('url'))}", f"PY_SHA256_{var}={val(e.get('sha256'))}",
                  f"PY_BYTES_{var}={val(e.get('bytes'))}"]
    lines.append(f"NODE_VERSION={val(node.get('version'))}")
    for key, var in (("darwin-arm64", "darwin_arm64"), ("darwin-x64", "darwin_x64")):
        e = plat(node, key)
        lines += [f"NODE_URL_{var}={val(e.get('url'))}", f"NODE_SHA256_{var}={val(e.get('sha256'))}",
                  f"NODE_BYTES_{var}={val(e.get('bytes'))}"]
    lines += [
        f"PNPM_VERSION={val(pnpm_version)}",
        f"PNPM_BYTES={val(pnpm.get('bytes'))}",
        f"CLAUDE_VERSION={val(claude.get('version'))}",
        f"CLAUDE_MIN={val(claude.get('min'))}",
        f"CLAUDE_INSTALLER_URL={val(claude.get('installer_url'))}",
        f"CLAUDE_APPROX_MB={val(claude.get('approx_installed_mb'))}",
    ]
    for key, var in (("darwin-arm64", "darwin_arm64"), ("darwin-x64", "darwin_x64")):
        lines.append(f"CLAUDE_SHA256_{var}={val(plat(claude, key).get('sha256'))}")
    return "\n".join(lines) + "\n"


def menu_id_of(entries: list[tuple[str, str]]) -> str:
    """The menu id (16.2.1): the first 16 hex of the SHA-256 of `<path> <sha256>\\n` per slide, sorted by path.
    Paths are relative to `sources/drive-resources/thomhouse-menu`."""
    text = "".join(f"{p} {h}\n" for p, h in sorted(entries))
    return _sha256_bytes(text.encode("utf-8"))[:16]


# ---------------------------------------------------------------- reading and verifying a release file

def _split(data: bytes) -> tuple[bytes, int]:
    """The header bytes (without the marker) and the payload offset; ReleaseError("not_release") without one
    marker line."""
    if data.startswith(MARKER[1:]):
        raise ReleaseError("not_release")
    idx = data.find(MARKER)
    if idx < 0:
        raise ReleaseError("not_release")
    return data[:idx], idx + len(MARKER)


def _read(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError:
        raise ReleaseError("not_release") from None


def read_header(path: Path) -> ReleaseInfo:
    """Parse the header variables of the release file `path` as data; the file is never executed.

    Raises `ReleaseError("not_release")` without exactly one marker line or when a variable is missing or
    malformed. The payload hash and the signature are checked by `verify_file`.
    """
    data = _read(path)
    header, offset = _split(data)
    values: dict[str, str] = {}
    for line in header.decode("utf-8", errors="replace").splitlines():
        m = _HEADER_LINE.match(line)
        if m and m.group(1) in HEADER_VARS and m.group(1) not in values:
            values[m.group(1)] = m.group(2)
    if any(name not in values for name in HEADER_VARS):
        raise ReleaseError("not_release")
    version, sha = values["RELEASE_VERSION"], values["PAYLOAD_SHA256"].lower()
    size, menu_id = values["PAYLOAD_BYTES"], values["MENU_ID"].lower()
    if not _VERSION.match(version) or not _HEX64.match(sha) or not size.isdigit() or not _HEX16.match(menu_id):
        raise ReleaseError("not_release")
    try:
        signature = base64.b64decode(values["PAYLOAD_SIG_B64"], validate=True)
    except (binascii.Error, ValueError):
        raise ReleaseError("not_release") from None
    return ReleaseInfo(
        version=version,
        path=Path(os.path.abspath(str(path))),
        payload_offset=offset,
        payload_bytes=int(size),
        payload_sha256=sha,
        release_id=group_id(_sha256_bytes(data)[:16]),
        signature=signature,
        menu_id=menu_id,
    )


def _payload(info: ReleaseInfo) -> bytes:
    """The payload bytes of `info`, checked against the header's size and SHA-256; ReleaseError("damaged")."""
    data = _read(info.path)
    payload = data[info.payload_offset:]
    if len(payload) != info.payload_bytes or _sha256_bytes(payload) != info.payload_sha256:
        raise ReleaseError("damaged")
    return payload


def _members(payload: bytes, version: str, wanted: tuple[str, ...]) -> dict[str, bytes]:
    """The contents of the payload files named in `wanted` (relative paths); ReleaseError("damaged") for an
    unreadable archive or a member outside `thomhouse-<version>/`."""
    prefix = f"thomhouse-{version}/"
    found: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            for m in tar:
                if not (m.name == prefix.rstrip("/") or m.name.startswith(prefix)):
                    raise ReleaseError("damaged")
                rel = m.name[len(prefix):]
                if rel in wanted and m.isreg():
                    f = tar.extractfile(m)
                    found[rel] = f.read() if f is not None else b""
    except (tarfile.TarError, OSError, EOFError):
        raise ReleaseError("damaged") from None
    return found


def _ssh_verify(ctx, payload: bytes, signature: bytes, signers: bytes) -> bool:
    """`ssh-keygen -Y verify` of `payload` against `signers` (an allowed_signers file's bytes)."""
    from . import proc

    folder = Path(tempfile.mkdtemp(prefix="thomhouse-verify-"))
    try:
        sig = folder / "payload.sig"
        allowed = folder / "allowed_signers"
        sig.write_bytes(signature)
        allowed.write_bytes(signers)
        try:
            res = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", SIGNER, "-n", NAMESPACE, "-s", str(sig)],
                input=payload, capture_output=True, env=proc.child_env(ctx.paths), timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return res.returncode == 0
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def verify_file(ctx, path: Path, *, first_install: bool) -> ReleaseInfo:
    """Read and verify the release file `path` without executing it (16.2.6, rev F5).

    Checks, in order: the payload size and SHA-256 (`damaged`); the payload's own VERSION.json names the header's
    version (`damaged`); the SSH signature against the payload's own `install/trust/allowed_signers`
    (`first_install`) or against `APP_HOME/trust/allowed_signers` (`signature`); no MANIFEST.json path is
    denylisted by the installed release's `install/denylist.txt`, or by the payload's own one when no release is
    installed (`denylisted`). The menu id is taken from the payload, not from the header. The caller compares the
    versions (`compare_versions`). Raises ReleaseError (exit 3).
    """
    info = read_header(path)
    payload = _payload(info)
    files = _members(payload, info.version, ("VERSION.json", "MANIFEST.json", "install/trust/allowed_signers",
                                              "install/denylist.txt"))
    try:
        version_doc = json.loads(files["VERSION.json"].decode("utf-8"))
        manifest = json.loads(files["MANIFEST.json"].decode("utf-8"))
    except (KeyError, ValueError, UnicodeDecodeError):
        raise ReleaseError("damaged") from None
    if not isinstance(version_doc, dict) or version_doc.get("version") != info.version:
        raise ReleaseError("damaged")
    if first_install:
        signers = files.get("install/trust/allowed_signers")
    else:
        try:
            signers = ctx.paths.trust.read_bytes()
        except OSError:
            signers = None
    if not signers or not _ssh_verify(ctx, payload, info.signature, signers):
        ctx.log("release_signature_failed", version=info.version, first_install=first_install)
        raise ReleaseError("signature")
    patterns = [] if first_install else denylist(ctx.paths.app)
    if not patterns:
        patterns = _patterns(files.get("install/denylist.txt", b"").decode("utf-8", errors="replace"))
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise ReleaseError("damaged")
    for entry in entries:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or denylisted(rel, patterns):
            ctx.log("release_denylisted", version=info.version)
            raise ReleaseError("denylisted")
    menu_id = version_doc.get("menu_id")
    if isinstance(menu_id, str) and _HEX16.match(menu_id):
        info.menu_id = menu_id
    ctx.log("release_verified", version=info.version, release_id=info.release_id, first_install=first_install)
    return info


# ---------------------------------------------------------------- unpack, cache, switch

def _safe_rel(rel: str) -> bool:
    if not rel or rel.startswith("/") or "\\" in rel:
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def _extract(payload: bytes, version: str, dest: Path) -> None:
    prefix = f"thomhouse-{version}/"
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            for m in tar:
                if m.name == prefix.rstrip("/"):
                    continue
                if not m.name.startswith(prefix):
                    raise ReleaseError("damaged")
                rel = m.name[len(prefix):].rstrip("/")
                if not _safe_rel(rel):
                    raise ReleaseError("damaged")
                target = dest / rel
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not m.isreg():
                    raise ReleaseError("damaged")
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(m)
                mode = 0o755 if m.mode & 0o111 else 0o644
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as out:
                    if src is not None:
                        shutil.copyfileobj(src, out)
                os.chmod(target, mode)
    except (tarfile.TarError, OSError, EOFError):
        raise ReleaseError("damaged") from None


def _sha_list_bad(root: Path) -> list[str]:
    """Paths of `MANIFEST.sha256` under `root` that are missing or differ (what `shasum -a 256 -c` reports)."""
    try:
        lines = (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["MANIFEST.sha256"]
    bad = []
    for line in lines:
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        f = root / rel
        if not _safe_rel(rel) or not f.is_file() or f.is_symlink() or _sha256_file(f) != digest.strip():
            bad.append(rel)
    return bad


def _release_ok(folder: Path, version: str) -> bool:
    try:
        doc = json.loads((folder / "VERSION.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("version") == version and verify_manifest(folder) == []


def unpack(ctx, info: ReleaseInfo) -> Path:
    """Unpack the payload of `info` to `releases/.staging-<ver>`, check every file of MANIFEST.sha256 and rename
    the folder to `releases/<ver>`. A `releases/<ver>` that already verifies is returned as is. A folder that does
    not verify is replaced, except the live one (`app` points at it): that one raises ReleaseError("damaged") and
    is left for `thomhouse repair`. The staging folder is deleted on any failure."""
    paths = ctx.paths
    target = paths.release_dir(info.version)
    if target.is_dir() and _release_ok(target, info.version):
        return target
    payload = _payload(info)
    _private_dir(paths.app_home)
    paths.releases.mkdir(parents=True, exist_ok=True)
    staging = paths.releases / f".staging-{info.version}"
    _rmtree(staging)
    staging.mkdir()
    try:
        _extract(payload, info.version, staging)
        if _sha_list_bad(staging) or not _release_ok(staging, info.version):
            raise ReleaseError("damaged")
        if target.exists() or target.is_symlink():
            if os.path.realpath(str(paths.app)) == os.path.realpath(str(target)):
                raise ReleaseError("damaged")
            aside = paths.releases / f".broken-{info.version}-{_now_stamp()}"
            os.replace(target, aside)
            _rmtree(aside)
        os.replace(staging, target)
    except BaseException:
        _rmtree(staging)
        raise
    ctx.log("release_unpacked", version=info.version)
    return target


def copy_to_cache(ctx, info: ReleaseInfo) -> Path:
    """Copy the release file to `cache/releases/thomhouse-<ver>.command` (0600) for `repair`; returns that path."""
    paths = ctx.paths
    _private_dir(paths.cache)
    _private_dir(paths.cache_releases)
    dest = paths.cache_releases / f"thomhouse-{info.version}.command"
    if dest.is_file() and _sha256_file(dest) == _sha256_file(info.path):
        os.chmod(dest, 0o600)
        return dest
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(paths.cache_releases))
    try:
        with os.fdopen(fd, "wb") as out, open(info.path, "rb") as src:
            shutil.copyfileobj(src, out)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return dest


def switch_app(ctx, version: str) -> None:
    """Point `APP_HOME/app` at `releases/<version>` (relative link, temporary link and `os.replace`).
    FileNotFoundError when that release folder does not exist."""
    paths = ctx.paths
    if not paths.release_dir(version).is_dir():
        raise FileNotFoundError(str(paths.release_dir(version)))
    app_link = paths.app_home / "app"
    _replace_link(app_link, f"releases/{version}")
    ctx.log("app_switched", version=version)


# ---------------------------------------------------------------- the launcher

def _sh_escape(text: str) -> str:
    """`text` safe inside bash double quotes."""
    for ch in ("\\", '"', "$", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


def _render_launcher(ctx, code_root: Path) -> bytes:
    template = (Path(code_root) / "install" / "thomhouse.sh.in").read_text(encoding="utf-8")
    text = template.replace("@APP_HOME@", _sh_escape(str(ctx.paths.app_home)))
    text = text.replace("@BOT_HOME@", _sh_escape(str(ctx.paths.bot_home)))
    return text.encode("utf-8")


def write_launcher(ctx, code_root: Path) -> bool:
    """Render `code_root/install/thomhouse.sh.in` with APP_HOME and BOT_HOME only (nothing version-specific) into
    `bin/thomhouse` (temporary file, `os.replace`, 0700). False when the content was already equal (rev F10)."""
    content = _render_launcher(ctx, code_root)
    target = ctx.paths.launcher
    _private_dir(target.parent)
    try:
        if target.read_bytes() == content:
            os.chmod(target, 0o700)
            return False
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".thomhouse.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(tmp, 0o700)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    ctx.log("launcher_written")
    return True


def launcher_current(ctx, code_root: Path) -> bool:
    """True when `bin/thomhouse` equals the launcher rendered from `code_root` and has mode 0700."""
    try:
        content = _render_launcher(ctx, code_root)
        target = ctx.paths.launcher
        return target.read_bytes() == content and (target.stat().st_mode & 0o777) == 0o700
    except OSError:
        return False


# ---------------------------------------------------------------- manifest

def verify_manifest(code_root: Path) -> list[str]:
    """Paths of MANIFEST.json under `code_root` that are missing or changed (by SHA-256); `runtime_written`
    files are skipped. ["MANIFEST.json"] when the manifest itself cannot be read."""
    root = Path(code_root)
    try:
        doc = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
        entries = doc["files"]
        if not isinstance(entries, list):
            raise TypeError
    except (OSError, ValueError, KeyError, TypeError):
        return ["MANIFEST.json"]
    bad = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            bad.append("MANIFEST.json")
            continue
        if entry.get("runtime_written"):
            continue
        rel = entry["path"]
        f = root / rel
        try:
            if not _safe_rel(rel) or f.is_symlink() or not f.is_file() or _sha256_file(f) != entry.get("sha256"):
                bad.append(rel)
        except OSError:
            bad.append(rel)
    return sorted(set(bad))


# ---------------------------------------------------------------- prune

def _live_version(paths) -> str | None:
    link = paths.app_home / "app"
    try:
        target = os.readlink(link)
    except OSError:
        return None
    name = Path(target).name
    return name if _VERSION.match(name) else None


def _menu_id_of_release(folder: Path) -> str | None:
    try:
        doc = json.loads((folder / "VERSION.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = doc.get("menu_id") if isinstance(doc, dict) else None
    return value if isinstance(value, str) else None


def _runtime_keep(paths, installed: dict) -> dict[str, set[str]] | None:
    keep: dict[str, set[str]] = {"python": set(), "node": set(), "pnpm": set()}
    found = False
    for key in ("runtimes", "previous_runtimes"):
        data = installed.get(key)
        if isinstance(data, dict):
            for name in keep:
                if isinstance(data.get(name), str):
                    keep[name].add(data[name])
                    found = True
    return keep if found else None


def prune(ctx, keep_previous: int = 1) -> None:
    """Remove releases other than the live one and the `keep_previous` previous ones (the installed.json
    `previous_version` first, then the newest), staging leftovers, cached release files of removed releases,
    menu slide sets no kept release uses, and runtime folders whose version is neither in `runtimes` nor in
    `previous_runtimes` of installed.json (and is not a current link target). Never touches the live release."""
    from . import state

    paths = ctx.paths
    if not paths.releases.is_dir():
        return
    installed = state.load_installed(paths) or {}
    live = _live_version(paths)
    versions = [d.name for d in paths.releases.iterdir() if d.is_dir() and not d.is_symlink()
                and _VERSION.match(d.name)]
    others = sorted((v for v in versions if v != live), key=version_tuple, reverse=True)
    prev = installed.get("previous_version")
    ordered = ([prev] if prev in others else []) + [v for v in others if v != prev]
    keep = set(ordered[:max(keep_previous, 0)])
    if live:
        keep.add(live)
    for entry in paths.releases.iterdir():
        name = entry.name
        if name.startswith((".staging-", ".broken-", ".repair-")):
            _rmtree(entry)
        elif _VERSION.match(name) and name not in keep and name != live:
            _rmtree(entry)
            ctx.log("release_pruned", version=name)
    if paths.cache_releases.is_dir():
        for f in paths.cache_releases.iterdir():
            m = re.match(r"^thomhouse-(\d+\.\d+\.\d+)\.command$", f.name)
            if m and m.group(1) not in keep:
                f.unlink()
    menus = paths.shared / "menu-slides"
    if menus.is_dir():
        used = {_menu_id_of_release(paths.release_dir(v)) for v in keep}
        for d in menus.iterdir():
            if d.name.startswith(".staging-") or (_HEX16.match(d.name) and d.name not in used):
                _rmtree(d)
    runtime_keep = _runtime_keep(paths, installed)
    if runtime_keep is None or not paths.runtime.is_dir():
        return
    current = set()
    for link in (paths.runtime / "python", paths.runtime / "node", paths.runtime_bin / "pnpm"):
        try:
            current.add(os.path.realpath(str(link)))
        except OSError:
            pass
    for entry in paths.runtime.iterdir():
        name = entry.name
        if name.startswith(".tmp-"):
            _rmtree(entry)
            continue
        m = (re.match(r"^python-(\d+\.\d+\.\d+)-", name) or re.match(r"^node-v(\d+\.\d+\.\d+)-", name)
             or re.match(r"^pnpm-(\d+\.\d+\.\d+)$", name))
        if not m or entry.is_symlink():
            continue
        kind = "python" if name.startswith("python-") else "node" if name.startswith("node-") else "pnpm"
        real = os.path.realpath(str(entry))
        if m.group(1) in runtime_keep[kind] or any(c == real or c.startswith(real + "/") for c in current):
            continue
        _rmtree(entry)


# ---------------------------------------------------------------- menu slides

def _menu_error() -> InstallerError:
    return InstallerError("release.menu_damaged", 1)


def _menu_doc(raw: bytes) -> dict:
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _menu_error() from None
    files = doc.get("files") if isinstance(doc, dict) else None
    if (not isinstance(doc, dict) or doc.get("schema") != 1 or not isinstance(files, list)
            or not isinstance(doc.get("menu_id"), str) or not _HEX16.match(doc["menu_id"])):
        raise _menu_error()
    for f in files:
        if (not isinstance(f, dict) or not isinstance(f.get("path"), str) or not _safe_rel(f["path"])
                or not isinstance(f.get("sha256"), str) or not _HEX64.match(f["sha256"])
                or not isinstance(f.get("bytes"), int)):
            raise _menu_error()
    if menu_id_of([(f["path"], f["sha256"]) for f in files]) != doc["menu_id"]:
        raise _menu_error()
    return doc


def _menu_folder_ok(folder: Path, menu_id: str) -> bool:
    try:
        doc = _menu_doc((folder / "MENU.json").read_bytes())
    except (OSError, InstallerError):
        return False
    if doc["menu_id"] != menu_id:
        return False
    for f in doc["files"]:
        p = folder / f["path"]
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size != f["bytes"] or _sha256_file(p) != f["sha256"]:
                return False
        except OSError:
            return False
    return True


def install_menu(ctx, menu_tar: Path) -> str:
    """Verify `thomhouse-menu-<id>.tar` (MENU.json and every slide by SHA-256 and size) and unpack it to
    `shared/menu-slides/<menu_id>/` (MENU.json beside the slide folders); returns the menu id. A set that already
    verifies is kept. Raises InstallerError("release.menu_damaged") for a damaged or mismatched archive."""
    paths = ctx.paths
    root = paths.shared / "menu-slides"
    try:
        with tarfile.open(str(menu_tar), mode="r:") as tar:
            member = tar.getmember("MENU.json")
            raw = tar.extractfile(member).read()  # type: ignore[union-attr]
            doc = _menu_doc(raw)
            menu_id = doc["menu_id"]
            dest = root / menu_id
            if _menu_folder_ok(dest, menu_id):
                return menu_id
            root.mkdir(parents=True, exist_ok=True)
            staging = root / f".staging-{menu_id}"
            _rmtree(staging)
            staging.mkdir()
            try:
                for f in doc["files"]:
                    m = tar.getmember("slides/" + f["path"])
                    src = tar.extractfile(m)
                    if src is None:
                        raise _menu_error()
                    out_path = staging / f["path"]
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    h, size = hashlib.sha256(), 0
                    with open(out_path, "wb") as out:
                        for chunk in iter(lambda: src.read(1 << 20), b""):
                            h.update(chunk)
                            size += len(chunk)
                            out.write(chunk)
                    if h.hexdigest() != f["sha256"] or size != f["bytes"]:
                        raise _menu_error()
                    os.chmod(out_path, 0o644)
                (staging / "MENU.json").write_bytes(raw)
                if dest.exists() or dest.is_symlink():
                    _rmtree(dest)
                os.replace(staging, dest)
            except BaseException:
                _rmtree(staging)
                raise
    except (tarfile.TarError, KeyError, OSError, EOFError, AttributeError):
        raise _menu_error() from None
    ctx.log("menu_installed", menu_id=menu_id)
    return menu_id


def link_menu(ctx, code_root: Path, menu_id: str) -> bool:
    """Link `code_root/sources/drive-resources/thomhouse-menu` to `shared/menu-slides/<menu_id>` (relative link).
    False when that slide set is not installed, or when the release holds a real folder there (a checkout):
    a real folder is never replaced."""
    src = ctx.paths.shared / "menu-slides" / menu_id
    if not (src / "MENU.json").is_file():
        return False
    link = Path(code_root) / MENU_DIR
    if link.exists() and not link.is_symlink():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    target = os.path.relpath(os.path.realpath(str(src)), os.path.realpath(str(link.parent)))
    try:
        if link.is_symlink() and os.readlink(link) == target:
            return True
    except OSError:
        pass
    _replace_link(link, target)
    return True


def menu_slides_ok(ctx, code_root: Path) -> bool:
    """True when the release's `sources/drive-resources/thomhouse-menu` links to `shared/menu-slides/<menu_id>`
    (the menu id of its VERSION.json) and every file of that set's MENU.json verifies."""
    menu_id = _menu_id_of_release(Path(code_root))
    if not menu_id or not _HEX16.match(menu_id):
        return False
    link = Path(code_root) / MENU_DIR
    expected = ctx.paths.shared / "menu-slides" / menu_id
    if not link.is_symlink() or os.path.realpath(str(link)) != os.path.realpath(str(expected)):
        return False
    return _menu_folder_ok(expected, menu_id)
