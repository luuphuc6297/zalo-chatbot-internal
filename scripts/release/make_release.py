#!/usr/bin/env python3
"""Build a release of the thom house chatbot on the build Mac (docs/contracts.md 16.2.2).

    python3 -I scripts/release/make_release.py --init-key [--sign-key PATH]
    python3 -I scripts/release/make_release.py --version X.Y.Z [--menu] [--out DIR] [--sign-key PATH] [--check-only]

--init-key runs `ssh-keygen -t ed25519` (ssh-keygen asks for the passphrase) and writes
install/trust/allowed_signers; it refuses when the key exists. --version checks and packs the allowlist of
scripts/release/allowlist.txt into thomhouse-<ver>.command (a bash header from install/selfextract.sh.in, a marker
line, then the signed deterministic payload), writes thomhouse-<ver>.sha256 and thomhouse-<ver>-DOC-TRUOC.txt, and
with --menu also thomhouse-menu-<menu_id>.tar. --check-only runs the checks (steps 1 to 6) and writes nothing.
Every failure names a path, a pin or a check, never a value. Exit codes: 0 built (or checked), 1 a check failed,
2 bad arguments, 3 refused (this is an installed copy, not a checkout).

Pins: install/versions.json must hold "hash_source": "https" and complete darwin-arm64 pins (url, sha256, bytes)
for Python and Node.js; scripts/release/refresh_pins.py writes them. A null placeholder refuses the build.
Test-only builds: when the environment variable THOMHOUSE_RELEASE_TEST_PINS names a versions.json whose
"hash_source" is "test", that file replaces install/versions.json for the checks and inside the payload, and the
builder warns on stderr that the release is a test build. A file without "hash_source": "test" is refused there,
and install/versions.json itself is refused with "hash_source": "test", so test pins never reach a device by
accident. The tests and the integration step build from a temporary copy of the project this way.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT / "install"))
sys.dont_write_bytecode = True

from thomhouse_installer import pins as pins_mod  # noqa: E402
from thomhouse_installer import release as rel  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3
TEST_PINS_ENV = "THOMHOUSE_RELEASE_TEST_PINS"
KEY_ENV = "THOMHOUSE_RELEASE_KEY"
NAMESPACE = "thomhouse-release"
SILENT_DROP = ("**/__pycache__/**", "**/*.pyc", "**/*.test.ts", "**/*.test.tsx", "**/.DS_Store")
MAX_BYTES = 5 * 1024 * 1024
SECRET_ENV_FILES = ("apps/server/.dev.vars", "apps/runner/.env", "apps/zalo-bridge/.env")
MENU_PREFIX = rel.MENU_DIR + "/"
_SPLIT = re.compile(r"[\s=:?&/\"',;]+")
_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Boundaries are letters and digits, not only digits, so a hex digest never counts as a phone number or an id.
_PHONE = re.compile(r"(?<![0-9A-Za-z])(\+?84|0)[35789]\d{8}(?![0-9A-Za-z])")
_LONG_ID = re.compile(r"(?<![0-9A-Za-z])\d{15,20}(?![0-9A-Za-z])")
_KEY_BLOCK = re.compile("-----" + "BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_PLACEHOLDER = re.compile(r"@[A-Z][A-Z0-9_]*@")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class BuildError(Exception):
    """A check failed; the message names a path, a pin or a check, never a value."""


def _err(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BuildError(f"{label}: missing or not valid JSON") from None
    if not isinstance(data, dict):
        raise BuildError(f"{label}: not a JSON object")
    return data


def _write_atomic(path: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- step 2: pins, pnpm lock, trust

def load_pins_file() -> tuple[Path, dict, bool]:
    """The versions.json used for this build: (path, data, test build?)."""
    test = os.environ.get(TEST_PINS_ENV, "").strip()
    if test:
        path = Path(os.path.expanduser(test))
        data = _read_json(path, f"{TEST_PINS_ENV} file")
        if data.get("hash_source") != "test":
            raise BuildError(f"{TEST_PINS_ENV}: the file must hold \"hash_source\": \"test\"")
        _err(f"WARNING: TEST BUILD with pins from {TEST_PINS_ENV}; never give this release to a device.")
        return path, data, True
    path = PROJECT / "install" / "versions.json"
    data = _read_json(path, "install/versions.json")
    if data.get("hash_source") != "https":
        raise BuildError("install/versions.json: hash_source is not \"https\"; run scripts/release/refresh_pins.py")
    return path, data, False


def check_pins(data: dict) -> None:
    for name in ("python", "node"):
        section = data.get(name)
        entry = ((section or {}).get("platforms") or {}).get("darwin-arm64") if isinstance(section, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        where = f"pin {name}.platforms.darwin-arm64"
        if not isinstance(url, str) or not url.startswith("https://"):
            raise BuildError(f"{where}.url is missing or not https (run scripts/release/refresh_pins.py)")
        if not isinstance(sha, str) or not _HEX64.match(sha.lower()):
            raise BuildError(f"{where}.sha256 is missing (run scripts/release/refresh_pins.py)")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise BuildError(f"{where}.bytes is missing (run scripts/release/refresh_pins.py)")
        if not isinstance(section.get("version"), str):
            raise BuildError(f"pin {name}.version is missing")
    claude = data.get("claude_code")
    if not isinstance(claude, dict) or not all(isinstance(claude.get(k), str) for k in ("version", "min",
                                                                                       "installer_url")):
        raise BuildError("pin claude_code (version, min, installer_url) is missing")


def pnpm_version() -> str:
    data = _read_json(PROJECT / "package.json", "package.json")
    pm = data.get("packageManager")
    if not isinstance(pm, str) or not pm.startswith("pnpm@"):
        raise BuildError("package.json: packageManager is not pnpm@X.Y.Z")
    return pm[len("pnpm@"):].split("+", 1)[0]


def check_pnpm_lock(version: str) -> None:
    folder = PROJECT / "install" / "lock" / "pnpm"
    pkg = _read_json(folder / "package.json", "install/lock/pnpm/package.json")
    if (pkg.get("dependencies") or {}).get("pnpm") != version:
        raise BuildError("install/lock/pnpm/package.json: pnpm differs from packageManager")
    lock = _read_json(folder / "package-lock.json",
                      "install/lock/pnpm/package-lock.json (run scripts/release/refresh_pins.py)")
    root = (lock.get("packages") or {}).get("") or {}
    locked = (root.get("dependencies") or {}).get("pnpm")
    if locked is None and isinstance(lock.get("dependencies"), dict):
        locked = (lock["dependencies"].get("pnpm") or {}).get("version")
    if locked != version:
        raise BuildError("install/lock/pnpm/package-lock.json: root dependency pnpm differs from packageManager")


def public_key(key: Path) -> tuple[str, str]:
    """(type, base64 blob) of the public half of `key`, from `<key>.pub` or `ssh-keygen -y`."""
    pub = Path(str(key) + ".pub")
    if pub.is_file():
        text = pub.read_text(encoding="utf-8", errors="replace")
    elif key.is_file():
        res = subprocess.run(["ssh-keygen", "-y", "-f", str(key)], stdout=subprocess.PIPE, text=True)
        text = res.stdout if res.returncode == 0 else ""
    else:
        text = ""
    parts = text.split()
    if len(parts) < 2:
        raise BuildError(f"signing key {key}: missing or unreadable (create it with --init-key)")
    return parts[0], parts[1]


def check_trust(key: Path) -> None:
    signers = PROJECT / "install" / "trust" / "allowed_signers"
    try:
        lines = signers.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise BuildError("install/trust/allowed_signers is missing (run --init-key)") from None
    kind, blob = public_key(key)
    for line in lines:
        parts = line.split()
        if (len(parts) >= 4 and parts[0] == NAMESPACE and parts[1] == f'namespaces="{NAMESPACE}"'
                and parts[2] == kind and parts[3] == blob):
            return
    raise BuildError("install/trust/allowed_signers does not hold the public key of the signing key")


# ---------------------------------------------------------------- step 4: the allowlist

def parse_allowlist(text: str) -> list[dict]:
    entries = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        glob = line.split()[0]
        rest = line[len(glob):]
        excepts = []
        for m in re.finditer(r"\(except\s+([^)]*)\)", rest):
            excepts += [x.strip() for x in m.group(1).split(",") if x.strip()]
        optional = "(optional)" in rest
        entries.append({"line": n, "glob": glob, "except": excepts, "optional": optional})
    return entries


def _literal_root(glob: str) -> str:
    parts = []
    for part in glob.split("/"):
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


def _candidates(root_rel: str) -> list[tuple[str, bool]]:
    """(relative path, is a symlink) of every file and symlink under `root_rel` (or `root_rel` itself)."""
    root = PROJECT / root_rel if root_rel else PROJECT
    out: list[tuple[str, bool]] = []
    if root.is_symlink():
        return [(root_rel, True)]
    if root.is_file():
        return [(root_rel, False)]
    if not root.is_dir():
        return out
    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        for d in list(dirs):
            if (base / d).is_symlink():
                out.append(((base / d).relative_to(PROJECT).as_posix(), True))
        for f in files:
            p = base / f
            out.append((p.relative_to(PROJECT).as_posix(), p.is_symlink()))
    return out


def collect(entries: list[dict], deny: list[str]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for entry in entries:
        glob = entry["glob"]
        matched = []
        for path, is_link in _candidates(_literal_root(glob)):
            probe = path + "/x" if is_link and (PROJECT / path).is_dir() else path
            if not (rel.glob_match(path, glob) or (is_link and rel.glob_match(probe, glob))):
                continue
            if any(rel.glob_match(path, e) for e in entry["except"]):
                continue
            if any(rel.glob_match(path, d) for d in SILENT_DROP):
                continue
            if is_link:
                raise BuildError(f"{path}: a symlink (allowlist line {entry['line']})")
            matched.append(path)
        if not matched and not entry["optional"]:
            raise BuildError(f"allowlist line {entry['line']} matches no file: {glob}")
        for path in matched:
            if rel.denylisted(path, deny):
                raise BuildError(f"{path}: denylisted by install/denylist.txt (allowlist line {entry['line']})")
            st = (PROJECT / path).stat()
            if stat.S_IMODE(st.st_mode) & 0o077 == 0:
                raise BuildError(f"{path}: private file mode {oct(stat.S_IMODE(st.st_mode))}")
            if st.st_size > MAX_BYTES:
                raise BuildError(f"{path}: larger than 5 MB")
            files[path] = PROJECT / path
    return files


# ---------------------------------------------------------------- step 5: secrets, ids, home path

def _tokens(text: str) -> set[str]:
    out = set()
    for t in _SPLIT.split(text):
        if len(t) < 16:
            continue
        if _HOST.match(t) and "." in t:  # a host name
            continue
        if _ENV_NAME.match(t):  # a variable name such as ZALO_PERSONAL_WEBHOOK_SECRET
            continue
        out.add(t)
    return out


def live_secrets() -> set[str]:
    """Values of 16+ characters of the build Mac's env files and tokens of every file in .secrets/ (16.2.2 step 5).
    Env values are split like .secrets lines, so a loopback URL or a path is not taken as a secret."""
    out: set[str] = set()
    for name in SECRET_ENV_FILES:
        try:
            text = (PROJECT / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = re.match(r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=(.*)$", line)
            if m and not line.lstrip().startswith("#"):
                value = m.group(1).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                out |= _tokens(value)
    secrets_dir = PROJECT / ".secrets"
    if secrets_dir.is_dir():
        for folder, _dirs, names in os.walk(secrets_dir):
            for name in names:
                if name.endswith(".example"):
                    continue
                try:
                    text = (Path(folder) / name).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line in text.splitlines():
                    out |= _tokens(line)
    return out


def placeholders() -> set[str]:
    out = set()
    try:
        text = (PROJECT / "scripts" / "release" / "placeholders.txt").read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        word = line.split("#", 1)[0].strip().split()
        if word and _HEX64.match(word[0].lower()):
            out.add(word[0].lower())
    return out


def scan(files: dict[str, bytes], secrets: set[str], allowed: set[str], homes: list[str]) -> list[str]:
    problems = []
    for path in sorted(files):
        text = files[path].decode("utf-8", errors="replace")
        hits = [s for s in secrets if s in text]
        homes_here = [h for h in homes if h in text]
        for n, line in enumerate(text.splitlines(), start=1):
            if any(s in line for s in hits):
                problems.append(f"{path}:{n}: live secret value of the build Mac")
            if _KEY_BLOCK.search(line):
                problems.append(f"{path}:{n}: private key block")
            for m in _PHONE.finditer(line):
                if _sha256(m.group(0).encode("utf-8")) not in allowed:
                    problems.append(f"{path}:{n}: Vietnamese phone number")
            for m in _LONG_ID.finditer(line):
                if _sha256(m.group(0).encode("utf-8")) not in allowed:
                    problems.append(f"{path}:{n}: run of 15 to 20 digits (Zalo id)")
            if any(h in line for h in homes_here):
                problems.append(f"{path}:{n}: the build Mac's home folder path")
    return problems


# ---------------------------------------------------------------- step 6: syntax

def syntax_problems(files: dict[str, bytes]) -> list[str]:
    problems = []
    for path in sorted(files):
        data = files[path]
        if path.endswith(".py"):
            try:
                compile(data, path, "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as e:
                problems.append(f"{path}: does not compile ({type(e).__name__} line {getattr(e, 'lineno', '?')})")
        elif path.endswith(".json"):
            try:
                json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                problems.append(f"{path}: not valid JSON")
        elif path.endswith((".sh", ".sh.in")):
            res = subprocess.run(["/bin/bash", "-n", str(PROJECT / path)], capture_output=True)
            if res.returncode != 0:
                problems.append(f"{path}: bash -n fails")
    return problems


# ---------------------------------------------------------------- menu

def menu_slides() -> list[tuple[str, Path]]:
    """(path relative to the menu folder, file) of every slide of data/menu-images.json."""
    index = _read_json(PROJECT / "data" / "menu-images.json", "data/menu-images.json")
    slides = index.get("slides")
    if not isinstance(slides, list):
        raise BuildError("data/menu-images.json: no slides list")
    out = []
    for s in slides:
        f = s.get("file") if isinstance(s, dict) else None
        if not isinstance(f, str) or not f.startswith(MENU_PREFIX):
            raise BuildError(f"data/menu-images.json: a slide file is not under {MENU_PREFIX}")
        path = PROJECT / f
        if not path.is_file():
            raise BuildError(f"{f}: menu slide missing")
        out.append((f[len(MENU_PREFIX):], path))
    return sorted(set(out))


# ---------------------------------------------------------------- steps 7 to 11

def _mode(path: Path) -> int:
    return 0o755 if os.stat(path).st_mode & 0o111 else 0o644


def payload_files(collected: dict[str, Path], pins_bytes: bytes, pins_data: dict, pnpm: str, version: str,
                  menu_id: str) -> dict[str, tuple[bytes, int]]:
    files = {p: (f.read_bytes(), _mode(f)) for p, f in collected.items()}
    files["install/versions.json"] = (pins_bytes, 0o644)
    files["install/versions.env"] = (rel.versions_env(pins_data, pnpm).encode("utf-8"), 0o644)
    version_doc = {"schema": 1, "version": version, "menu_id": menu_id}
    files["VERSION.json"] = ((json.dumps(version_doc, indent=1) + "\n").encode("utf-8"), 0o644)
    entries = []
    for path in sorted(files):
        data, mode = files[path]
        entries.append({"path": path, "sha256": _sha256(data), "bytes": len(data), "mode": f"0{mode:o}",
                        "runtime_written": path in rel.RUNTIME_WRITTEN})
    manifest = json.dumps({"schema": 1, "files": entries}, indent=1) + "\n"
    files["MANIFEST.json"] = (manifest.encode("utf-8"), 0o644)
    files["MANIFEST.sha256"] = ("".join(f"{e['sha256']}  {e['path']}\n" for e in entries).encode("utf-8"), 0o644)
    return files


def pack(files: dict[str, tuple[bytes, int]], version: str) -> bytes:
    """Deterministic tar.gz: members sorted by path, mtime 0, uid and gid 0, empty names, gzip mtime 0."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in sorted(files):
            data, mode = files[path]
            info = tarfile.TarInfo(f"thomhouse-{version}/{path}")
            info.size, info.mtime, info.mode = len(data), 0, mode
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def sign(payload: bytes, key: Path) -> bytes:
    """`ssh-keygen -Y sign` of the payload (ssh-keygen asks for the passphrase itself), then a verify against
    install/trust/allowed_signers."""
    with tempfile.TemporaryDirectory(prefix="thomhouse-sign-") as d:
        p = Path(d) / "payload.tar.gz"
        p.write_bytes(payload)
        res = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(p)],
                             stdout=subprocess.DEVNULL)
        sig = Path(str(p) + ".sig")
        if res.returncode != 0 or not sig.is_file():
            raise BuildError("ssh-keygen -Y sign failed")
        res = subprocess.run(["ssh-keygen", "-Y", "verify", "-f",
                              str(PROJECT / "install" / "trust" / "allowed_signers"), "-I", NAMESPACE, "-n",
                              NAMESPACE, "-s", str(sig)], input=payload, capture_output=True)
        if res.returncode != 0:
            raise BuildError("the new signature does not verify against install/trust/allowed_signers")
        return sig.read_bytes()


def header(version: str, payload: bytes, signature: bytes, menu_id: str) -> bytes:
    template = (PROJECT / "install" / "selfextract.sh.in").read_text(encoding="utf-8")
    values = {
        "RELEASE_VERSION": version,
        "PAYLOAD_SHA256": _sha256(payload),
        "PAYLOAD_BYTES": str(len(payload)),
        "PAYLOAD_SIG_B64": base64.b64encode(signature).decode("ascii"),
        "MENU_ID": menu_id,
        "BUILT_AT": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    text = template
    for name, value in values.items():
        text = text.replace(f"@{name}@", value)
    if _PLACEHOLDER.search(text):
        raise BuildError("install/selfextract.sh.in: a header variable was not filled in")
    if not text.endswith("\n"):
        text += "\n"
    data = text.encode("utf-8")
    if rel.MARKER[1:-1] in data:
        raise BuildError("install/selfextract.sh.in: holds the marker string")
    return data


def write_menu(out: Path, slides: list[tuple[str, Path]], menu_id: str) -> Path:
    entries = [{"path": p, "sha256": _sha256_file(f), "bytes": f.stat().st_size} for p, f in slides]
    doc = (json.dumps({"schema": 1, "menu_id": menu_id, "files": entries}, indent=1) + "\n").encode("utf-8")
    target = out / f"thomhouse-menu-{menu_id}.tar"
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(out))
    os.close(fd)
    try:
        with tarfile.open(tmp, mode="w", format=tarfile.GNU_FORMAT) as tar:
            info = tarfile.TarInfo("MENU.json")
            info.size, info.mtime, info.mode, info.uid, info.gid, info.uname, info.gname = (
                len(doc), 0, 0o644, 0, 0, "", "")
            tar.addfile(info, io.BytesIO(doc))
            for p, f in slides:
                info = tarfile.TarInfo(f"slides/{p}")
                info.size, info.mtime, info.mode, info.uid, info.gid, info.uname, info.gname = (
                    f.stat().st_size, 0, 0o644, 0, 0, "", "")
                with open(f, "rb") as src:
                    tar.addfile(info, src)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def build(args: argparse.Namespace) -> int:
    version = args.version
    # 1. an installed copy is not a checkout
    if (PROJECT / "VERSION.json").exists():
        _err("refused: VERSION.json exists at the project root; this is an installed copy, not a checkout")
        return EXIT_REFUSED
    key = Path(os.path.expanduser(args.sign_key)) if args.sign_key else Path(
        os.path.expanduser(os.environ.get(KEY_ENV) or "~/.ssh/thomhouse-release"))
    # 2. pins complete
    pins_path, pins_data, test_build = load_pins_file()
    check_pins(pins_data)
    pnpm = pnpm_version()
    check_pnpm_lock(pnpm)
    check_trust(key)
    # 3. pins agree
    bad = pins_mod.agreement(PROJECT)
    if bad:
        raise BuildError("pins disagree: " + ", ".join(bad))
    # 4. collect
    allow_text = (PROJECT / "scripts" / "release" / "allowlist.txt").read_text(encoding="utf-8")
    deny = rel.denylist(PROJECT)
    if not deny:
        raise BuildError("install/denylist.txt is missing or empty")
    collected = collect(parse_allowlist(allow_text), deny)
    contents = {p: f.read_bytes() for p, f in collected.items()}
    contents["install/versions.json"] = pins_path.read_bytes()
    # 5. scan
    home = os.environ.get("HOME", "").rstrip("/")
    homes = sorted({h for h in (home, os.path.realpath(home) if home else "") if h and h != "/"})
    problems = scan(contents, live_secrets(), placeholders(), homes)
    if problems:
        raise BuildError("scan failed:\n  " + "\n  ".join(problems))
    # 6. syntax
    problems = syntax_problems(contents)
    if problems:
        raise BuildError("syntax checks failed:\n  " + "\n  ".join(problems))
    slides = menu_slides()
    menu_id = rel.menu_id_of([(p, _sha256_file(f)) for p, f in slides])
    if args.check_only:
        print(f"check-only: {len(collected)} files, every check passed; menu_id {menu_id}")
        return EXIT_OK
    # 7. generated files, 8. pack, 9. sign
    files = payload_files(collected, pins_path.read_bytes(), pins_data, pnpm, version, menu_id)
    payload = pack(files, version)
    signature = sign(payload, key)
    # 10. the .command file (and the menu archive)
    out = Path(os.path.expanduser(args.out)) if args.out else Path.home() / "thomhouse-releases"
    if not out.exists():
        out.mkdir(parents=True)
        os.chmod(out, 0o700)
    command = out / f"thomhouse-{version}.command"
    whole = header(version, payload, signature, menu_id) + rel.MARKER[1:] + payload
    _write_atomic(command, whole, 0o755)
    menu_tar = write_menu(out, slides, menu_id) if args.menu else None
    # 11. the checksum line and the note beside the file
    digest = _sha256(whole)
    _write_atomic(out / f"thomhouse-{version}.sha256", f"{digest}  {command.name}\n".encode("utf-8"), 0o644)
    note = (PROJECT / "scripts" / "release" / "DOC-TRUOC.txt.in").read_text(encoding="utf-8")
    _write_atomic(out / f"thomhouse-{version}-DOC-TRUOC.txt", note.replace("{version}", version).encode("utf-8"),
                  0o644)
    print(f"{command}  {len(whole)} bytes")
    if menu_tar is not None:
        print(f"{menu_tar}  {menu_tar.stat().st_size} bytes")
    print(f"{out / f'thomhouse-{version}.sha256'}")
    print(f"{out / f'thomhouse-{version}-DOC-TRUOC.txt'}")
    print(f"files: {len(files)}")
    print(f"release id: {rel.group_id(digest[:16])}")
    print(f"menu_id: {menu_id}")
    if test_build:
        _err("WARNING: TEST BUILD; never give this release to a device.")
    return EXIT_OK


def init_key(args: argparse.Namespace) -> int:
    key = Path(os.path.expanduser(args.sign_key)) if args.sign_key else Path(
        os.path.expanduser(os.environ.get(KEY_ENV) or "~/.ssh/thomhouse-release"))
    if key.exists():
        _err(f"refused: {key} exists already")
        return EXIT_FAILED
    if not key.parent.exists():
        key.parent.mkdir(parents=True)
        os.chmod(key.parent, 0o700)
    res = subprocess.run(["ssh-keygen", "-t", "ed25519", "-C", NAMESPACE, "-f", str(key)])
    if res.returncode != 0:
        _err("ssh-keygen failed")
        return EXIT_FAILED
    kind, blob = public_key(key)
    signers = PROJECT / "install" / "trust" / "allowed_signers"
    signers.parent.mkdir(parents=True, exist_ok=True)
    if signers.exists():
        _err("WARNING: install/trust/allowed_signers is replaced; every device must trust the new key again")
    _write_atomic(signers, f'{NAMESPACE} namespaces="{NAMESPACE}" {kind} {blob}\n'.encode("utf-8"), 0o644)
    print(f"key: {key}")
    print(f"trust: {signers}")
    return EXIT_OK


def _version_arg(text: str) -> str:
    if not _VERSION.match(text):
        raise argparse.ArgumentTypeError("the version must be MAJOR.MINOR.PATCH")
    return text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="make_release.py", description="Build a thom house release (16.2.2).")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init-key", action="store_true", help="create the signing key and install/trust")
    mode.add_argument("--version", type=_version_arg, metavar="X.Y.Z", help="build this release")
    p.add_argument("--menu", action="store_true", help="also write thomhouse-menu-<menu_id>.tar")
    p.add_argument("--out", metavar="DIR", help="output folder (default ~/thomhouse-releases)")
    p.add_argument("--sign-key", metavar="PATH", help=f"signing key (default ${KEY_ENV} or ~/.ssh/thomhouse-release)")
    p.add_argument("--check-only", action="store_true", help="run the checks only and write nothing")
    args = p.parse_args(argv)
    try:
        if args.init_key:
            return init_key(args)
        return build(args)
    except BuildError as e:
        _err(f"build failed: {e}")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
