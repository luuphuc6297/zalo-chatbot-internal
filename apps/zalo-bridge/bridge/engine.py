"""Run the zalo-agent CLI (@ardennguyen/zalo-agent-cli) as a subprocess.

Facts this module relies on (checked in sources/repos/arden-zalo-agent-cli, v2.5.9):
- `--json` puts exactly one JSON value on stdout (src/utils/output.js); failures print {"error": "..."}. Many
  commands report a failure that way and still exit 0, so callers must read the JSON, not only the exit code.
- Commander ends option parsing at `--`, so `msg send -- <threadId> <text>` is safe for a text that starts with
  "-" (checked with commander 14; the engine depends on commander ^15).
- ZALO_AGENT_NO_UPDATE_CHECK=1 skips the npm registry check that runs before every command.
- ZALO_SEND_FORMAT=markdown would make `msg send` reformat the text, so it is removed from the child env.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Config

# Never handed to the engine: the bridge's own secrets, and webhook settings that would override the flags.
_DROP_EXACT = {"RUNNER_TOKEN", "STAFF_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET", "ZALO_SEND_FORMAT", "ZALO_JSON_MODE"}
_DROP_PREFIX = ("ZALO_WEBHOOK_SECRET", "ZALO_WEBHOOK_URL")


@dataclass
class EngineResult:
    argv_tail: list[str]
    returncode: int | None = None       # None when the process was killed (timeout / cancel) or never started
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    missing: bool = False               # executable not found / not runnable
    data: Any = None                    # parsed JSON from stdout, or None
    extra: dict = field(default_factory=dict)

    @property
    def error_text(self) -> str | None:
        if isinstance(self.data, dict) and self.data.get("error") is not None:
            return str(self.data["error"])
        return None


def resolve_bin(cfg: Config) -> str | None:
    b = cfg.zalo_agent_bin
    if os.sep in b or (os.altsep and os.altsep in b):
        return b if os.path.isfile(b) and os.access(b, os.X_OK) else None
    return shutil.which(b)


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in _DROP_EXACT and not k.startswith(_DROP_PREFIX)}
    env["ZALO_AGENT_NO_UPDATE_CHECK"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    if extra:
        env.update(extra)
    return env


def parse_json_output(stdout: str) -> Any:
    """The one JSON value on stdout. Tolerates stray lines around it; returns None when none parses."""
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    lines = s.splitlines(keepends=True)
    offset = 0
    for line in lines:
        if line.lstrip().startswith(("{", "[")):
            start = offset + (len(line) - len(line.lstrip()))
            try:
                value, _ = dec.raw_decode(s, start)
                return value
            except json.JSONDecodeError:
                pass
        offset += len(line)
    return None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError):
        return
    for sig, wait_s in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait_s)
            return
        except subprocess.TimeoutExpired:
            continue


def run_engine(cfg: Config, args: list[str], timeout: float, *, json_mode: bool = True, account: bool = True,
               extra_env: dict[str, str] | None = None, cancel: threading.Event | None = None) -> EngineResult:
    """Run `zalo-agent [--json] [--account X] <args>` with stdin closed, in its own process group."""
    res = EngineResult(argv_tail=list(args))
    exe = resolve_bin(cfg)
    if not exe:
        res.missing = True
        res.stderr = f"zalo-agent executable not found: {cfg.zalo_agent_bin}"
        return res
    argv = [exe] + (["--json"] if json_mode else [])
    if cfg.zalo_account and account:
        argv += ["--account", cfg.zalo_account]
    argv += args
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=child_env(extra_env), start_new_session=True, text=True,
                                encoding="utf-8", errors="replace")
    except OSError as e:
        res.missing = True
        res.stderr = f"cannot run zalo-agent: {type(e).__name__}: {e}"
        return res
    deadline = time.monotonic() + timeout
    out, err = "", ""
    while True:
        step = min(0.5, max(0.01, deadline - time.monotonic()))
        try:
            out, err = proc.communicate(timeout=step)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                res.cancelled = True
            elif time.monotonic() >= deadline:
                res.timed_out = True
            else:
                continue
            _kill_group(proc)
            try:
                out, err = proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError):
                out, err = "", ""
            break
    res.stdout, res.stderr = out or "", err or ""
    res.returncode = None if (res.timed_out or res.cancelled) else proc.returncode
    res.data = parse_json_output(res.stdout) if json_mode else None
    return res
