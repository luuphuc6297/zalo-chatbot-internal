"""Child environment (16.4.2), the process runner and the secret filter (invariant 4).

Every child the installer starts gets `child_env()`: the launcher's variables, never an Anthropic API key or a
Claude Code session variable, `DISABLE_UPDATES=1` (except Anthropic's installer, F1), `PROFILE_LLM_ENABLED=false`,
and `no_proxy`/`NO_PROXY` that always contain the loopback names while proxy variables are passed on (F4).
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .paths import Paths

LOOPBACK = ("127.0.0.1", "localhost", "::1")
PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
SECRET_KEYS = (
    "RUNNER_TOKEN",
    "STAFF_TOKEN",
    "ZALO_PERSONAL_WEBHOOK_SECRET",
    "ZALO_OA_SECRET_KEY",
    "ZALO_APP_SECRET_KEY",
)
NEVER_PASS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE", "CLAUDE_EFFORT")
SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
_SECRET_LINE = re.compile(r"\b(" + "|".join(SECRET_KEYS) + r")(\s*[=:]\s*[\"']?)([^\s\"']{16,})")


@dataclass
class Result:
    """Outcome of `run()`; `stdout` and `stderr` are filled only with `capture=True`."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


def _no_proxy_value(current: str | None) -> str:
    """`current` (comma list, may be empty) followed by the loopback names that are not in it yet."""
    items = [x.strip() for x in (current or "").split(",") if x.strip()]
    for name in LOOPBACK:
        if name not in items:
            items.append(name)
    return ",".join(items)


def _forbidden(name: str) -> bool:
    return name in NEVER_PASS or name.startswith("CLAUDE_CODE_")


def _path_value(paths: Paths, caller_path: str | None) -> str:
    caller = [p for p in (caller_path or "").split(os.pathsep) if p]
    if not caller:
        caller = list(SYSTEM_PATH)
    if paths.mode != "installed":
        return os.pathsep.join(caller)
    first = [str(paths.runtime / "node" / "bin"), str(paths.runtime / "python" / "bin"), str(paths.runtime_bin)]
    rest = [p for p in caller if p not in first]
    return os.pathsep.join(first + rest)


def child_env(
    paths: Paths, extra: Mapping[str, str] | None = None, *, claude_install: bool = False
) -> dict[str, str]:
    """The environment of every child process (16.4.2), built from `os.environ` and `paths`.

    Kept from the caller: HOME, USER, LOGNAME, LANG, TERM, TMPDIR, the proxy variables, ZALO_CONFIG_DIR,
    THOMHOUSE_LOCK_OWNER and every other THOMHOUSE_* setting. PATH: in installed mode the runtime folders
    (node, python, runtime/bin) first, then the caller's PATH (the launcher's fixed PATH on a device); in checkout
    mode the caller's PATH. Set: THOMHOUSE_APP_HOME, THOMHOUSE_BOT_HOME, DISABLE_UPDATES=1,
    ZALO_AGENT_NO_UPDATE_CHECK=1, WRANGLER_SEND_METRICS=false, PROFILE_LLM_ENABLED=false,
    npm_config_cache=APP_HOME/cache/npm, no_proxy and NO_PROXY with 127.0.0.1,localhost,::1 appended.
    Never: Anthropic API keys or tokens, CLAUDECODE, CLAUDE_CODE_*, CLAUDE_EFFORT, and CLAUDE_CONFIG_DIR only when
    `extra` gives it. `extra` is applied last (forbidden names dropped; PROFILE_LLM_ENABLED stays false and the
    loopback names stay in no_proxy). `claude_install=True` also removes DISABLE_UPDATES and DISABLE_AUTOUPDATER,
    for Anthropic's installer only (F1).
    """
    src = os.environ
    home = src.get("HOME") or str(paths.home)
    user = src.get("USER") or src.get("LOGNAME") or ""
    env: dict[str, str] = {
        "HOME": home,
        "USER": user,
        "LOGNAME": src.get("LOGNAME") or user,
        "LANG": src.get("LANG") or "en_US.UTF-8",
        "TERM": src.get("TERM") or "xterm-256color",
        "TMPDIR": src.get("TMPDIR") or "/tmp",
        "PATH": _path_value(paths, src.get("PATH")),
    }
    for name, value in src.items():
        if name.startswith("THOMHOUSE_") and not _forbidden(name):
            env[name] = value
    for name in PROXY_VARS + ("ZALO_CONFIG_DIR",):
        if src.get(name):
            env[name] = src[name]
    env.update(
        {
            "THOMHOUSE_APP_HOME": str(paths.app_home),
            "THOMHOUSE_BOT_HOME": str(paths.bot_home),
            "DISABLE_UPDATES": "1",
            "ZALO_AGENT_NO_UPDATE_CHECK": "1",
            "WRANGLER_SEND_METRICS": "false",
            "PROFILE_LLM_ENABLED": "false",
            "npm_config_cache": str(paths.cache / "npm"),
        }
    )
    np = _no_proxy_value(src.get("no_proxy") or src.get("NO_PROXY"))
    env["no_proxy"] = np
    env["NO_PROXY"] = np
    for name, value in (extra or {}).items():
        if _forbidden(name):
            continue
        env[name] = str(value)
    env["PROFILE_LLM_ENABLED"] = "false"
    env["no_proxy"] = _no_proxy_value(env.get("no_proxy"))
    env["NO_PROXY"] = _no_proxy_value(env.get("NO_PROXY"))
    if claude_install:
        env.pop("DISABLE_UPDATES", None)
        env.pop("DISABLE_AUTOUPDATER", None)
    return env


def _env_files(paths: Paths) -> list[Path]:
    from .paths import ENV_FILES

    roots = [paths.app]
    if paths.code_root != paths.app:
        roots.append(paths.code_root)
    files = []
    for root in roots:
        for parts in ENV_FILES.values():
            f = root.joinpath(*parts)
            if f not in files:
                files.append(f)
    return files


def secret_values(paths: Paths) -> set[str]:
    """Values of 16 or more characters of the five secret keys of invariant 4, from the env files under `app` and
    `code_root` and from the environment. Never printed or logged."""
    from . import envs

    out: set[str] = set()
    for f in _env_files(paths):
        data = envs.read(f)
        for key in SECRET_KEYS:
            v = data.get(key)
            if v and len(v) >= 16:
                out.add(v)
    for key in SECRET_KEYS:
        v = os.environ.get(key)
        if v and len(v) >= 16:
            out.add(v)
    return out


def redact(text: str, secrets: set[str]) -> str:
    """`text` with every value of `secrets` and every `KEY=value` of the five secret keys replaced by `***`."""
    for s in sorted(secrets, key=len, reverse=True):
        if s:
            text = text.replace(s, "***")
    return _SECRET_LINE.sub(lambda m: m.group(1) + m.group(2) + "***", text)


def _kill_group(proc: subprocess.Popen, sig: int, own_group: bool) -> None:
    try:
        if own_group:
            os.killpg(proc.pid, sig)
        else:
            proc.send_signal(sig)
    except (ProcessLookupError, PermissionError):
        pass


def _read_back(fh) -> str:
    if fh is None:
        return ""
    fh.flush()
    fh.seek(0)
    return fh.read().decode("utf-8", errors="replace")


def run(
    ctx,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    log: Path | None = None,
    timeout: float | None = None,
    stdin: str | None = None,
    capture: bool = False,
    interactive: bool = False,
) -> Result:
    """Run `cmd` and return its `Result`.

    env None = `child_env(ctx.paths)`. stdin None = /dev/null unless `interactive`; a string is sent to the child.
    `capture`: stdout and stderr kept in memory only, never logged. `log` (without `capture`): both appended to that
    file through `redact`, never shown. Neither: discarded. `interactive`: the child inherits the terminal and
    nothing is logged. Non-interactive children run in their own session; a timeout sends SIGTERM to the group,
    SIGKILL after 5 s, and gives returncode 124. A missing executable gives 127 (126 when not executable).
    Output is collected through temporary files, so a daemon that keeps an inherited descriptor never blocks.
    """
    child = dict(env) if env is not None else child_env(ctx.paths)
    out_fh = err_fh = None
    stdin_arg: object
    if stdin is not None:
        stdin_arg = subprocess.PIPE
    elif interactive:
        stdin_arg = None
    else:
        stdin_arg = subprocess.DEVNULL
    if interactive:
        stdout_arg = stderr_arg = None
    elif capture or log is not None:
        out_fh = tempfile.TemporaryFile()
        err_fh = tempfile.TemporaryFile()
        stdout_arg, stderr_arg = out_fh, err_fh
    else:
        stdout_arg = stderr_arg = subprocess.DEVNULL
    own_group = not interactive
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            cwd=str(cwd) if cwd is not None else None,
            env=child,
            stdin=stdin_arg,
            stdout=stdout_arg,
            stderr=stderr_arg,
            start_new_session=own_group,
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        for fh in (out_fh, err_fh):
            if fh is not None:
                fh.close()
        return Result(126 if isinstance(e, PermissionError) else 127)
    try:
        if stdin is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin.encode("utf-8"))
                proc.stdin.close()
            except BrokenPipeError:
                pass
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc, signal.SIGTERM, own_group)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(proc, signal.SIGKILL, own_group)
                proc.wait()
            code = 124
        except KeyboardInterrupt:
            _kill_group(proc, signal.SIGTERM, own_group)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(proc, signal.SIGKILL, own_group)
            raise
        out = _read_back(out_fh)
        err = _read_back(err_fh)
    finally:
        for fh in (out_fh, err_fh):
            if fh is not None:
                fh.close()
    if capture:
        return Result(code, out, err)
    if log is not None:
        _append_log(ctx, log, cmd, code, out, err)
    return Result(code)


def _append_log(ctx, log: Path, cmd: list[str], code: int, out: str, err: str) -> None:
    try:
        secrets = secret_values(ctx.paths)
        log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        head = redact(" ".join(str(c) for c in cmd), secrets)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"--- {stamp} {head}\n")
            if out:
                f.write(redact(out, secrets))
                if not out.endswith("\n"):
                    f.write("\n")
            if err:
                f.write(redact(err, secrets))
                if not err.endswith("\n"):
                    f.write("\n")
            f.write(f"--- exit {code}\n")
    except OSError:
        pass
