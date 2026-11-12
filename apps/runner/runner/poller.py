"""Claim loop: claim -> process -> submit, with heartbeats, a concurrency cap, backoff and graceful shutdown.

- At most cfg.max_concurrency `claude -p` calls at once (default 3).
- While claude runs, POST /heartbeat every cfg.heartbeat_s (20 s). `cancel: true`, or a lease error (404,
  409 lease_expired / lease_not_owned / job_not_leased), kills the call; nothing is posted for that job.
- No work: wait poll_after_ms, growing up to 5 s while idle. Server down: exponential backoff 1 s .. 60 s.
- No usable account in the pool: stop claiming (the server's runner health sweep hands queued jobs to staff).
- First SIGINT/SIGTERM: stop claiming, let running jobs finish (up to timeout + 15 s). Second signal or the
  deadline: kill running calls and post /fail `cancelled` so the server hands off at once.
- Every cfg.status_every_s: POST /runner/status with the pool snapshot; apply `desired_account` with
  claude_pool `use` and report again.
- THOMHOUSE_DRAFT_ENGINE=rooms: jobs run through RoomEngine (room_engine.py), which wraps the direct engine. A
  daemon thread runs its observation tick every cfg.room_observe_every_s (0 = off); the tick shares a
  per-conversation lock with draft turns and never raises into this loop.
"""

from __future__ import annotations

import logging
import signal
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Any

from . import __version__
from .api import ApiClient, ServerUnavailable
from .claude_runner import CallHandle, ClaudeRunner, Outcome
from .config import Config
from .contract import ApiError, ClaimResponse, ClaimedJob, FailRequest
from .prompt import PromptCache
from .room_engine import RoomEngine
from .sessions import SessionStore

log = logging.getLogger("runner")
LEASE_LOST_CODES = {"lease_expired", "lease_not_owned", "job_not_leased", "not_found"}
LOGIN_REFRESH_EVERY = 10   # include `claude auth status` in every Nth status report
OBSERVE_OFF_RECHECK_S = 300.0   # rooms flag off on the server: ask again this often


class Backoff:
    def __init__(self, start: float, cap: float, factor: float = 2.0):
        self.start, self.cap, self.factor = start, cap, factor
        self.current = 0.0

    def next(self) -> float:
        self.current = self.start if self.current <= 0 else min(self.current * self.factor, self.cap)
        return self.current

    def reset(self) -> None:
        self.current = 0.0


class Runner:
    def __init__(self, cfg: Config, api: ApiClient | None = None):
        self.cfg = cfg
        self.api = api or ApiClient(cfg.server_url, cfg.runner_token, cfg.runner_id)
        self.sessions = SessionStore(cfg.home)
        self.prompts = PromptCache(self.api, cfg.home)
        self.claude = ClaudeRunner(cfg, self.prompts, self.sessions)
        if cfg.draft_engine == "rooms":
            self.claude = RoomEngine(cfg, self.api, self.claude)   # same seam; falls back to the direct engine
        self.stop = threading.Event()        # stop claiming
        self.kill = threading.Event()        # cancel running calls
        self._handles: dict[str, CallHandle] = {}
        self._hlock = threading.Lock()
        self.applied_desired_account = self.claude.pool_snapshot()["pinned"]
        self._failed_desired: str | None = None
        self._status_count = 0

    # ------------------------------------------------------------ one job

    def _heartbeat_loop(self, job: ClaimedJob, handle: CallHandle, done: threading.Event) -> None:
        while not done.wait(self.cfg.heartbeat_s):
            try:
                hb = self.api.heartbeat(job.job_id)
            except ServerUnavailable as e:
                log.warning("job %s: heartbeat failed (%s)", job.job_id, e)
                continue
            except ApiError as e:
                if e.status == 404 or e.code in LEASE_LOST_CODES:
                    handle.cancel("lease_lost")
                    return
                log.warning("job %s: heartbeat error %s", job.job_id, e.code)
                continue
            if hb.get("cancel"):
                handle.cancel(str(hb.get("cancel_reason") or "job_cancelled"))
                return

    def process_job(self, job: ClaimedJob) -> dict[str, Any]:
        handle = CallHandle()
        with self._hlock:
            self._handles[job.job_id] = handle
        if self.kill.is_set():
            handle.cancel("shutdown")
        done = threading.Event()
        hb = threading.Thread(target=self._heartbeat_loop, args=(job, handle, done), daemon=True,
                              name=f"hb-{job.job_id}")
        hb.start()
        try:
            try:
                outcome = self.claude.run_job(job, handle)
            except Exception as e:  # noqa: BLE001 - every failure must reach the server as /fail
                log.exception("job %s: internal error", job.job_id)
                outcome = Outcome("fail", fail=FailRequest(
                    error_kind="internal", error_message=f"{type(e).__name__}: {e}"[:500],
                    account_label=None, session_id=job.conversation.session_id, session_broken=False))
            if outcome.kind == "cancelled" and outcome.cancel_reason == "shutdown":
                outcome = Outcome("fail", fail=FailRequest(
                    error_kind="cancelled", error_message="runner shutting down", account_label=None,
                    session_id=job.conversation.session_id, session_broken=False), cancel_reason="shutdown")
        finally:
            done.set()
            with self._hlock:
                self._handles.pop(job.job_id, None)
        summary = {"job_id": job.job_id, **outcome.summary()}
        try:
            if outcome.kind == "draft":
                resp = self.api.draft(job.job_id, outcome.draft.to_dict())
                summary.update(draft_status=resp.get("status"), action=resp.get("action"))
            elif outcome.kind == "fail":
                body = outcome.fail.to_dict()
                if body.get("usage") is None:
                    body.pop("usage", None)
                if body.get("cost_usd_equiv") is None:
                    body.pop("cost_usd_equiv", None)
                resp = self.api.fail(job.job_id, body)
                summary.update(job_status=resp.get("job_status"))
        except ApiError as e:
            summary["post_error"] = e.code
            log.warning("job %s: posting %s failed: %s", job.job_id, outcome.kind, e.code)
        except ServerUnavailable as e:
            summary["post_error"] = "server_unavailable"
            log.warning("job %s: posting %s failed: %s", job.job_id, outcome.kind, e)
        log.info("job %s done: %s", job.job_id, {k: v for k, v in summary.items() if k != "job_id"})
        return summary

    # ------------------------------------------------------------ claim

    def claim_once(self) -> tuple[ClaimedJob | None, int]:
        cr = ClaimResponse.from_dict(self.api.claim())
        return cr.job, int(cr.poll_after_ms or 0)

    def run_once(self) -> dict[str, Any]:
        """Claim at most one job and process it (used by `main.py once` and tests)."""
        if not self.claude.pool_has_account():
            return {"job_id": None, "reason": "no_usable_account"}
        job, _ = self.claim_once()
        if job is None:
            return {"job_id": None, "reason": "no_work"}
        return self.process_job(job)

    # ------------------------------------------------------------ status

    def status_body(self, with_login: bool = False) -> dict[str, Any]:
        snap = self.claude.pool_snapshot(with_login=with_login)
        with self._hlock:
            active = len(self._handles)
        return {"runner_version": __version__, "hostname": socket.gethostname(), "active_jobs": active,
                "max_concurrency": self.cfg.max_concurrency, "accounts": snap["accounts"],
                "next_account": snap["next_account"], "applied_desired_account": self.applied_desired_account,
                "reported_at": int(time.time() * 1000)}

    def report_status(self, with_login: bool | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if with_login is None:
            with_login = self._status_count % LOGIN_REFRESH_EVERY == 0
        self._status_count += 1
        resp = self.api.status(body or self.status_body(with_login))
        desired = str(resp.get("desired_account") or "auto")
        if desired != self.applied_desired_account and desired != self._failed_desired:
            if self.claude.use_account(desired):
                log.info("account switch applied: %s", desired)
                self.applied_desired_account, self._failed_desired = desired, None
                resp = self.api.status(self.status_body(False))
            else:
                log.warning("desired account %r is not in the pool; keeping %s", desired,
                            self.applied_desired_account)
                self._failed_desired = desired
        return resp

    # ------------------------------------------------------------ rooms observation

    def observe_once(self) -> dict[str, Any] | None:
        """One observation tick of the rooms engine (None with the direct engine). Never raises."""
        if not isinstance(self.claude, RoomEngine):
            return None
        try:
            return self.claude.observe_once()
        except Exception as e:  # noqa: BLE001 - the tick must never take the runner down
            log.warning("room observation tick crashed (%s)", type(e).__name__)
            return {"enabled": True, "posted": 0, "skipped": 0, "failed": 1}

    def _observe_loop(self) -> None:
        every = self.cfg.room_observe_every_s
        delay = every
        while not self.stop.wait(delay):
            stats = self.observe_once() or {}
            # Flag off on the server (or migration missing): the loop is off; look again only now and then.
            delay = every if stats.get("enabled", True) else max(every, OBSERVE_OFF_RECHECK_S)

    def start_observer(self) -> threading.Thread | None:
        """Start the observation loop when the engine is rooms and ROOM_OBSERVE_EVERY_S is not 0."""
        if not isinstance(self.claude, RoomEngine) or self.cfg.room_observe_every_s <= 0:
            return None
        t = threading.Thread(target=self._observe_loop, daemon=True, name="room-observe")
        t.start()
        return t

    # ------------------------------------------------------------ loop

    def install_signals(self) -> None:
        def handler(signum, _frame):
            if self.stop.is_set():
                log.warning("second signal: cancelling running jobs")
                self.cancel_all("shutdown")
            else:
                log.info("signal %s: finishing running jobs, not claiming new ones", signum)
                self.stop.set()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def cancel_all(self, reason: str) -> None:
        self.kill.set()
        with self._hlock:
            handles = list(self._handles.values())
        for h in handles:
            h.cancel(reason)

    def run_forever(self, max_jobs: int | None = None) -> int:
        """Returns the number of jobs processed. `max_jobs` is for tests."""
        processed = 0
        server_backoff = Backoff(1.0, 60.0)
        idle_backoff = Backoff(0.5, 5.0, 1.5)
        next_status = 0.0
        active: set[Future] = set()
        pool = ThreadPoolExecutor(max_workers=self.cfg.max_concurrency, thread_name_prefix="job")
        self.start_observer()
        try:
            while not self.stop.is_set():
                if max_jobs is not None and processed >= max_jobs:
                    break
                if time.monotonic() >= next_status:
                    try:
                        self.report_status()
                    except (ServerUnavailable, ApiError) as e:
                        log.warning("status report failed: %s", getattr(e, "code", e))
                    next_status = time.monotonic() + self.cfg.status_every_s
                active = {f for f in active if not f.done()}
                if len(active) >= self.cfg.max_concurrency:
                    wait(active, timeout=0.5, return_when=FIRST_COMPLETED)
                    continue
                if not self.claude.pool_has_account():
                    log.warning("no usable Claude account in the pool; not claiming")
                    self.stop.wait(30)
                    continue
                try:
                    job, poll_after = self.claim_once()
                except ServerUnavailable as e:
                    delay = server_backoff.next()
                    log.warning("server unavailable (%s); retry in %.0fs", e, delay)
                    self.stop.wait(delay)
                    continue
                except ApiError as e:
                    delay = server_backoff.next()
                    log.error("claim rejected: %s %s; retry in %.0fs", e.status, e.code, delay)
                    self.stop.wait(delay)
                    continue
                server_backoff.reset()
                if job is None:
                    self.stop.wait(max(poll_after / 1000.0, idle_backoff.next()))
                    continue
                idle_backoff.reset()
                processed += 1
                active.add(pool.submit(self.process_job, job))
                if poll_after:
                    self.stop.wait(poll_after / 1000.0)
        finally:
            self.stop.set()
            grace = self.cfg.claude_timeout_s + 15
            if isinstance(self.claude, RoomEngine):
                grace += self.cfg.room_turn_timeout_s       # a room turn, then possibly the fallback call
            deadline = time.monotonic() + grace
            while active and time.monotonic() < deadline and not self.kill.is_set():
                active = {f for f in active if not f.done()}
                if active:
                    wait(active, timeout=0.5)
            if active:
                self.cancel_all("shutdown")
            pool.shutdown(wait=True)
        return processed
