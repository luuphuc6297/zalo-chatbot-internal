"""`thomhouse repair [--paths] [--env]` (16.8.7).

Without options: `app` is linked again to `releases/<version of installed.json>` when it points elsewhere, files
that `release.verify_manifest` reports are restored from the cached release file (verified against the stored
trust, extracted to a staging folder, only the changed files copied), the launcher is rewritten when it differs,
and the folder modes of doctor check 23 are fixed. `--paths` removes the `ZALO_AGENT_BIN` and
`OPENMAUSBOT_NODE_DIR` lines (commented ones too) and restarts, so `init-env` writes this installation's paths.
`--env` copies `RUNNER_TOKEN` and `ZALO_PERSONAL_WEBHOOK_SECRET` from the server's `.dev.vars` into the runner and
bridge env files and restarts. Both act only after `c`; values are never printed or logged.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from .context import EXIT_DECLINED, EXIT_FAILED, EXIT_OK, InstallerError

PATH_KEYS = ("ZALO_AGENT_BIN", "OPENMAUSBOT_NODE_DIR")
_PATH_LINE = re.compile(r"^\s*#?\s*(?:export\s+)?(" + "|".join(PATH_KEYS) + r")\s*=")


def _tilde(paths, path: Path) -> str:
    home = str(paths.home).rstrip("/")
    text = str(path)
    if home and (text == home or text.startswith(home + "/")):
        return "~" + text[len(home):]
    return text


def _say(key: str, **fmt: object) -> None:
    from .text_vi import say

    say(key, **fmt)


# ---------------------------------------------------------------- env files

def _write_lines(path: Path, lines: list[str]) -> None:
    """Replace `path` with `lines` (mode 0600, temporary file and `os.replace`)."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _set_key(lines: list[str], key: str, value: str) -> list[str]:
    """`lines` with every active `key=` line replaced by one `key=value` line (appended when there was none)."""
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=")
    out, done = [], False
    for line in lines:
        if pattern.match(line):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    return out


def _drop_path_lines(paths) -> int:
    """Remove the ZALO_AGENT_BIN and OPENMAUSBOT_NODE_DIR lines (also commented ones) from every env file; returns
    how many lines were removed."""
    removed = 0
    for name in ("bridge", "runner", "server"):
        f = paths.env_file(name)
        lines = _read_lines(f)
        kept = [x for x in lines if not _PATH_LINE.match(x)]
        if len(kept) != len(lines):
            removed += len(lines) - len(kept)
            _write_lines(f, kept)
    return removed


def _copy_secrets(paths) -> bool:
    """Copy RUNNER_TOKEN to the runner and bridge files and ZALO_PERSONAL_WEBHOOK_SECRET to the bridge file, from
    the server's `.dev.vars`; False when the server file lacks one of them."""
    from . import envs

    server = envs.read(paths.env_file("server"))
    token = server.get("RUNNER_TOKEN")
    secret = server.get("ZALO_PERSONAL_WEBHOOK_SECRET")
    if not token or not secret:
        return False
    runner = paths.env_file("runner")
    _write_lines(runner, _set_key(_read_lines(runner), "RUNNER_TOKEN", token))
    bridge = paths.env_file("bridge")
    lines = _set_key(_read_lines(bridge), "RUNNER_TOKEN", token)
    _write_lines(bridge, _set_key(lines, "ZALO_PERSONAL_WEBHOOK_SECRET", secret))
    return True


def _restart(ctx, tb: str) -> bool:
    from . import stack

    stack.stop(ctx)
    code = stack.start(ctx)
    if code != 0:
        _say("release.repair_restart_failed", tb=tb)
        return False
    return True


# ---------------------------------------------------------------- program files

def _restore_files(ctx, version: str, folder: Path, changed: list[str]) -> list[str]:
    """Copy the files `changed` of `folder` from the cached release file of `version`; returns what still differs.
    Raises ReleaseError when the cached file does not verify."""
    from . import release

    paths = ctx.paths
    cached = paths.cache_releases / f"thomhouse-{version}.command"
    info = release.verify_file(ctx, cached, first_install=False)
    if info.version != version:
        raise release.ReleaseError("damaged")
    payload = cached.read_bytes()[info.payload_offset:]
    staging = Path(tempfile.mkdtemp(prefix=f".repair-{version}-", dir=str(paths.releases)))
    try:
        release._extract(payload, version, staging)  # noqa: SLF001 - WP2 internal
        for rel in changed:
            src = staging / rel
            if not src.is_file():
                continue
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink() or dest.is_dir():
                release._rmtree(dest)  # noqa: SLF001 - WP2 internal
            fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
            with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
                shutil.copyfileobj(inp, out)
            os.chmod(tmp, src.stat().st_mode & 0o777)
            os.replace(tmp, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return release.verify_manifest(folder)


def _repair_program(ctx, tb: str) -> bool:
    from . import release, state

    paths = ctx.paths
    installed = state.load_installed(paths)
    version = installed.get("version") if installed else None
    if not isinstance(version, str) or not version:
        _say("release.repair_not_installed")
        return False
    folder = paths.release_dir(version)
    if not folder.is_dir():
        _say("release.repair_no_release", v=version)
        return False
    ok = True
    changed = release.verify_manifest(folder)
    if changed:
        cached = paths.cache_releases / f"thomhouse-{version}.command"
        if not cached.is_file():
            _say("release.repair_no_cache", v=version, folder=_tilde(paths, paths.cache_releases))
            ok = False
        else:
            try:
                left = _restore_files(ctx, version, folder, changed)
            except InstallerError as err:
                ctx.log("repair_cache_refused", key=err.key)
                from .text_vi import t

                try:
                    print(t(err.key, **{"tb": tb, "cmd": f"{tb} repair", **err.fmt}), flush=True)
                except (KeyError, IndexError, ValueError):
                    pass
                left = changed
            restored = len(changed) - len(left)
            if restored:
                _say("release.repair_restored", n=restored)
            if left:
                ctx.log("repair_files_left", count=len(left), paths=left[:50])
                _say("release.repair_files_bad", n=len(left))
                ok = False
    else:
        _say("release.repair_files_ok")
    app_link = paths.app_home / "app"
    if os.path.realpath(str(app_link)) != os.path.realpath(str(folder)):
        if release.verify_manifest(folder) == []:
            release.switch_app(ctx, version)
            _say("release.repair_relinked", v=version)
        else:
            ok = False
    if release.write_launcher(ctx, folder):
        _say("release.repair_launcher", tb=tb)
    fixed = 0
    for d in (paths.app_home, paths.bot_home, paths.backups, paths.bot_home / "profiles"):
        try:
            if d.is_dir() and not d.is_symlink() and (d.stat().st_mode & 0o777) != 0o700:
                os.chmod(d, 0o700)
                fixed += 1
        except OSError:
            ok = False
    if fixed:
        _say("release.repair_modes", n=fixed)
    return ok


# ---------------------------------------------------------------- command

def cmd_repair(ctx, args) -> int:
    """`thomhouse repair [--paths] [--env]`: 0 done, 1 failed, 4 declined (16.8.7)."""
    from . import consent

    paths = ctx.paths
    tb = _tilde(paths, paths.launcher)
    want_paths = bool(getattr(args, "paths", False))
    want_env = bool(getattr(args, "env", False))
    if not want_paths and not want_env:
        ok = _repair_program(ctx, tb)
        ctx.log("repair", mode="program", ok=ok)
        if ok:
            _say("release.repair_done")
        return EXIT_OK if ok else EXIT_FAILED
    if want_paths and consent.ask(ctx, "release.repair_paths_ask", "ck") != "c":
        _say("release.repair_declined")
        return EXIT_DECLINED
    if want_env and consent.ask(ctx, "release.repair_env_ask", "ck") != "c":
        _say("release.repair_declined")
        return EXIT_DECLINED
    if want_env and not _copy_secrets(paths):
        _say("release.repair_env_missing", tb=tb)
        return EXIT_FAILED
    if want_paths:
        removed = _drop_path_lines(paths)
        ctx.log("repair_paths", removed=removed)
    restarted = _restart(ctx, tb)
    if want_paths:
        _say("release.repair_paths_done")
    if want_env:
        ctx.log("repair_env")
        _say("release.repair_env_done")
    if not restarted:
        return EXIT_FAILED
    _say("release.repair_done")
    return EXIT_OK
