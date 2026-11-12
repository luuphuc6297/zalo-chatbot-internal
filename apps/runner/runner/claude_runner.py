"""Builds and runs the `claude -p` call for one job through scripts/runner/claude_pool.py (reused, not rewritten).

Flags (same as scripts/eval/run_eval_cli.py): --model <model> --effort <effort> --setting-sources project
--strict-mcp-config --tools "" --system-prompt <cli_system_prompt> --output-format json --mcp-config <per-job file>
--allowedTools mcp__thom [--resume <session_id>] -- <user text>; env CLAUDE_CODE_DISABLE_CLAUDE_MDS=1,
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1; stdin closed (claude_pool passes DEVNULL); timeout CLAUDE_TIMEOUT_S.
Exit code AND is_error are checked (claude_pool does both). Cost per turn = delta of the cumulative
total_cost_usd inside a resumed session (sessions.SessionStore.record_turn).

Cancellation: claude_pool calls `subprocess.run`, which gives no process handle. The pool module gets a drop-in
`subprocess` object whose `run` starts each call in its own process group and registers it on the calling
thread's CallHandle, so a heartbeat `cancel` or a timeout kills `claude` and the MCP proxy it started.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .config import Config
from .contract import ClaimedJob, DraftRequest, FailRequest, Usage
from .prompt import PromptBundle, PromptCache, build_user_text
from .sessions import SessionPlan, SessionStore

log = logging.getLogger("runner.claude")
SERVER_NAME = "thom"
MCP_PROXY = Path(__file__).resolve().parent / "mcp_proxy.py"
CLEAN_ENV = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


# ---------------------------------------------------------------- process tracking for claude_pool

class CallHandle:
    """Per-job handle: lets the heartbeat thread kill the running `claude -p` (and its MCP proxy)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: list[subprocess.Popen] = []
        self.cancelled = False
        self.cancel_reason: str | None = None
        self.timed_out = False

    def add(self, p: subprocess.Popen) -> None:
        with self._lock:
            self._procs.append(p)
            kill = self.cancelled
        if kill:
            _kill_group(p)

    def remove(self, p: subprocess.Popen) -> None:
        with self._lock:
            if p in self._procs:
                self._procs.remove(p)

    def cancel(self, reason: str) -> None:
        with self._lock:
            if self.cancelled:
                return
            self.cancelled, self.cancel_reason = True, reason
            procs = list(self._procs)
        for p in procs:
            _kill_group(p)


def _kill_group(p: subprocess.Popen) -> None:
    if p.returncode is not None:      # already reaped: its pid / group id may belong to someone else now
        return
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.kill()
        except OSError:
            pass


_local = threading.local()


class TrackedSubprocess:
    """Stands in for the `subprocess` module inside claude_pool (it only uses run, DEVNULL, TimeoutExpired)."""

    TimeoutExpired = subprocess.TimeoutExpired
    CalledProcessError = subprocess.CalledProcessError
    SubprocessError = subprocess.SubprocessError
    CompletedProcess = subprocess.CompletedProcess
    DEVNULL = subprocess.DEVNULL
    PIPE = subprocess.PIPE

    def run(self, cmd, *, cwd=None, capture_output=False, text=False, stdin=None, timeout=None, env=None, **kw):
        handle: CallHandle | None = getattr(_local, "handle", None)
        if handle is not None and handle.cancelled:
            return subprocess.CompletedProcess(cmd, -9, "" if text else b"", "cancelled" if text else b"cancelled")
        pipe = subprocess.PIPE if capture_output else None
        p = subprocess.Popen(cmd, cwd=cwd, stdout=kw.get("stdout", pipe), stderr=kw.get("stderr", pipe),
                             stdin=stdin, text=text, env=env, start_new_session=True)
        if handle is not None:
            handle.add(p)
        try:
            try:
                out, err = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                if handle is not None:
                    handle.timed_out = True
                _kill_group(p)
                p.communicate()
                raise subprocess.TimeoutExpired(cmd, timeout) from None
        finally:
            if handle is not None:
                handle.remove(p)
        return subprocess.CompletedProcess(cmd, p.returncode, out, err)


_pools: dict[tuple[str, str], ModuleType] = {}
_pools_lock = threading.Lock()


def load_pool(pool_path: Path, home: Path) -> ModuleType:
    """Import claude_pool.py by path and point it at `home` (it reads THOMHOUSE_BOT_HOME at import time)."""
    key = (str(pool_path.resolve()), str(home))
    with _pools_lock:
        if key in _pools:
            return _pools[key]
        spec = importlib.util.spec_from_file_location(f"claude_pool_{len(_pools)}", pool_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load claude_pool from {pool_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.HOME = home
        mod.ACCOUNTS = home / "accounts.json"
        mod.STATE = home / "account-state.json"
        mod.SESSIONS = home / "sessions"
        mod.subprocess = TrackedSubprocess()
        _pools[key] = mod
        return mod


# ---------------------------------------------------------------- outcome

@dataclass
class Outcome:
    kind: str                         # "draft" | "fail" | "cancelled"
    draft: DraftRequest | None = None
    fail: FailRequest | None = None
    cancel_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        d: dict[str, Any] = {"outcome": self.kind}
        if self.draft:
            d.update(account=self.draft.account_label, session_restarted=self.draft.error_kind is not None,
                     cost_usd_equiv=self.draft.cost_usd_equiv)
        if self.fail:
            d.update(error_kind=self.fail.error_kind, account=self.fail.account_label,
                     session_broken=self.fail.session_broken)
        if self.cancel_reason:
            d["cancel_reason"] = self.cancel_reason
        return d


def _usage(res: dict) -> Usage:
    u = res.get("usage") or {}

    def n(k: str) -> int:
        try:
            return int(u.get(k) or 0)
        except (TypeError, ValueError):
            return 0
    return Usage(input_tokens=n("input_tokens"), output_tokens=n("output_tokens"),
                 cache_read_input_tokens=n("cache_read_input_tokens"),
                 cache_creation_input_tokens=n("cache_creation_input_tokens"))


def _short(text: Any, limit: int = 500) -> str:
    return str(text or "").strip().replace("\n", " ")[:limit]


# ---------------------------------------------------------------- runner

class ClaudeRunner:
    def __init__(self, cfg: Config, prompts: PromptCache, sessions: SessionStore):
        self.cfg = cfg
        self.prompts = prompts
        self.sessions = sessions
        self.pool = load_pool(cfg.pool_path, cfg.home)

    # ------------------------------------------------------------ call building

    def base_flags(self, system_prompt: str) -> list[str]:
        return ["--model", self.cfg.model, "--effort", self.cfg.effort, "--setting-sources", "project",
                "--strict-mcp-config", "--tools", "", "--system-prompt", system_prompt, "--output-format", "json"]

    def write_mcp_config(self, job: ClaimedJob, bundle: PromptBundle) -> Path:
        if not JOB_ID_RE.match(job.job_id):
            raise ValueError("job_id is not a safe id")
        d = self.cfg.home / "run" / job.job_id
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        cfg = {"mcpServers": {SERVER_NAME: {
            "command": sys.executable, "args": ["-I", str(MCP_PROXY)],
            "env": {"THOMHOUSE_API_URL": self.cfg.server_url, "RUNNER_TOKEN": self.cfg.runner_token,
                    "RUNNER_ID": self.cfg.runner_id, "THOMHOUSE_JOB_ID": job.job_id,
                    "THOMHOUSE_TOOLS_FILE": str(bundle.tools_file)}}}}
        path = d / "mcp.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return path

    def args_for(self, bundle: PromptBundle, mcp_path: Path, resume_id: str | None, user_text: str) -> list[str]:
        return (self.base_flags(bundle.system_prompt)
                + ["--mcp-config", str(mcp_path), "--allowedTools", f"mcp__{SERVER_NAME}"]
                + (["--resume", resume_id] if resume_id else [])
                + ["--", user_text])

    def _call(self, args: list[str], cwd: Path, handle: CallHandle) -> dict:
        _local.handle = handle
        try:
            return self.pool.run(args, cwd, timeout=self.cfg.claude_timeout_s, extra_env=dict(CLEAN_ENV))
        except FileNotFoundError:
            return {"is_error": True, "result": "claude binary not found on PATH", "_missing_binary": True,
                    "_account": None, "_switched_from": []}
        finally:
            _local.handle = None

    # ------------------------------------------------------------ classification

    def _no_account_kind(self, res: dict) -> tuple[str, str]:
        tried = res.get("_switched_from") or []
        st = self.pool.state()
        statuses = {st.get(l, {}).get("status") for l in tried}
        if not tried:
            return "no_account", "no usable Claude account in the pool"
        if len(statuses) == 1 and statuses <= {"limited", "login_expired", "blocked"}:
            kind = statuses.pop()
            until = sorted(st[l].get("until") for l in tried if st.get(l, {}).get("until"))
            extra = f"; earliest reset {until[0]}" if kind == "limited" and until else ""
            return kind, f"every tried account is {kind} ({', '.join(tried)}){extra}"
        return "no_account", f"no usable Claude account; tried {', '.join(tried)}"

    def classify(self, res: dict, handle: CallHandle) -> tuple[str | None, str]:
        """(error_kind or None for success, message). Message never contains customer text."""
        if handle.cancelled:
            return "cancelled", f"cancelled: {handle.cancel_reason}"
        if handle.timed_out:
            return "timeout", f"claude -p exceeded {self.cfg.claude_timeout_s:g}s"
        if res.get("_missing_binary"):
            return "internal", "claude binary not found on PATH"
        if res.get("_no_account"):
            return self._no_account_kind(res)
        if res.get("stop_reason") == "refusal" or res.get("subtype") == "refusal":
            return "refusal", "model refused"
        if res.get("is_error"):
            return "model_error", _short(res.get("result"), 300)
        if not str(res.get("result") or "").strip():
            return "empty_output", "claude -p returned an empty result"
        if not res.get("session_id"):
            return "model_error", "claude -p result has no session_id"
        return None, ""

    # ------------------------------------------------------------ one job

    def run_job(self, job: ClaimedJob, handle: CallHandle) -> Outcome:
        cid = job.conversation.conversation_id
        bundle = self.prompts.get(job.prompt_hash or None)
        workdir = self.sessions.workdir(cid)
        plan: SessionPlan = self.sessions.plan(job)
        for sid in plan.drop:
            self._drop_session(cid, sid)
        if plan.runner_reset:
            self.sessions.clear(cid)
        mcp_path = self.write_mcp_config(job, bundle)
        try:
            return self._run(job, handle, bundle, workdir, mcp_path, plan)
        finally:
            shutil.rmtree(mcp_path.parent, ignore_errors=True)

    def _run(self, job, handle, bundle, workdir, mcp_path, plan: SessionPlan) -> Outcome:
        cid = job.conversation.conversation_id
        resume_id = plan.resume_id
        restarted = plan.runner_reset
        t0 = time.time()
        user_text = build_user_text(job, new_session=resume_id is None, runner_restarted=restarted)
        res = self._call(self.args_for(bundle, mcp_path, resume_id, user_text), workdir, handle)
        kind, msg = self.classify(res, handle)

        if kind == "model_error" and resume_id:
            # The resumed session is broken (not an account problem, not a timeout): drop it and retry once
            # with a new session seeded from what the server sent.
            log.warning("job %s: resume failed, retrying with a new session", job.job_id)
            self._drop_session(cid, resume_id)
            self.sessions.clear(cid)
            resume_id, restarted = None, True
            user_text = build_user_text(job, new_session=True, runner_restarted=True)
            res = self._call(self.args_for(bundle, mcp_path, None, user_text), workdir, handle)
            kind, msg = self.classify(res, handle)
            if kind is not None and kind != "cancelled":
                self._drop_orphan(cid, res)
                return Outcome("fail", fail=FailRequest(
                    error_kind="session_broken" if kind == "model_error" else kind,
                    error_message=f"resume failed, new session also failed: {msg}"[:500],
                    account_label=res.get("_account"), session_id=None, session_broken=True))

        if kind == "cancelled":
            if not resume_id:
                self._drop_orphan(cid, res)
            return Outcome("cancelled", cancel_reason=handle.cancel_reason)
        if kind is not None:
            if not resume_id:
                self._drop_orphan(cid, res)
            return Outcome("fail", fail=FailRequest(
                error_kind=kind, error_message=msg[:500], account_label=res.get("_account"),
                session_id=resume_id, session_broken=False,
                usage=_usage(res) if res.get("usage") else None))

        new_sid = str(res["session_id"])
        cost = self.sessions.record_turn(job, new_sid, resume_id, res.get("total_cost_usd"))
        if resume_id and new_sid != resume_id:
            self._drop_session(cid, resume_id)       # claude forked the session; the old copy is not used again
        duration = res.get("duration_ms")
        return Outcome("draft", draft=DraftRequest(
            text=str(res["result"]).strip(), session_id=new_sid, account_label=res.get("_account"),
            model=self.cfg.model, effort=self.cfg.effort, usage=_usage(res), cost_usd_equiv=cost,
            duration_ms=int(duration if isinstance(duration, (int, float)) else (time.time() - t0) * 1000),
            num_turns=int(res.get("num_turns") or 0),
            error_kind="session_restarted" if restarted else None))

    # ------------------------------------------------------------ session files

    def _drop_session(self, cid: str, sid: str) -> None:
        removed = self.sessions.delete_session_files(cid, sid)
        log.info("conversation %s: dropped session %s (%d paths)", cid, sid[:8], len(removed))

    def _drop_orphan(self, cid: str, res: dict) -> None:
        sid = res.get("session_id")
        if sid:
            self._drop_session(cid, str(sid))

    # ------------------------------------------------------------ pool status

    def pool_has_account(self) -> bool:
        return bool(self.pool.candidates())

    def pool_snapshot(self, with_login: bool = False) -> dict[str, Any]:
        st = self.pool.state()
        pinned = next((l for l, s in st.items() if s.get("pinned")), None)
        accs = []
        for a in sorted(self.pool.accounts(), key=lambda a: a.get("priority", 100)):
            s = st.get(a["label"], {})
            accs.append({"label": a["label"], "priority": a.get("priority"), "enabled": a.get("enabled", True),
                         "pinned": a["label"] == pinned, "pool_status": s.get("status", "ok"),
                         "until": s.get("until"), "usable_now": self.pool.healthy(a["label"]),
                         "login": self.pool._auth_status(a) if with_login else None,
                         "last_error": self._pool_error_kind(s.get("last_error")), "last_ok": s.get("last_ok")})
        cands = self.pool.candidates()
        return {"accounts": accs, "next_account": cands[0]["label"] if cands else None,
                "pinned": pinned or "auto"}

    def _pool_error_kind(self, text: Any) -> str:
        """claude_pool stores only an error kind in last_error; a file written by an older version can still hold
        the raw `claude` output (model output, possibly customer text). Only a kind leaves this machine."""
        if not text:
            return ""
        try:
            kinds = getattr(self.pool, "ERROR_KINDS", ())
            if str(text) in kinds:
                return str(text)
            if hasattr(self.pool, "error_kind"):
                return str(self.pool.error_kind(str(text)))
            return str(self.pool.classify(str(text)))
        except Exception:  # noqa: BLE001 - status reporting must not fail on this
            return "error"

    def use_account(self, label: str) -> bool:
        """Manual switch through claude_pool's own `use` command (`auto` unpins)."""
        try:
            with redirect_stdout(io.StringIO()):
                self.pool.cmd_use(label)
            return True
        except SystemExit:
            return False
