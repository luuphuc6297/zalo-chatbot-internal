"""Claim loop: claim one outbox row -> send it with zalo-agent -> post the result. One row at a time.

- Pacing: at least SEND_MIN_INTERVAL_S (+ 0..SEND_JITTER_S) between the end of one send and the next claim, so
  the personal account does not burst and the 60 s lease is not spent waiting.
- No work: wait the server's poll_after_ms (2 s idle, 5 s while outbound_enabled=false), else 1 s growing to 3 s.
  Server down: back off 1 s .. 30 s. Token rejected or no Bridge API: wait 30 s and log once per minute.
- The result carries the claim's `attempt`, so the server can refuse a stale failed/unknown result.
- Not logged in: the row is reported "failed" (the server retries it later) and claiming pauses LOGIN_PAUSE_S.
- At most once: see journal.py. A result that cannot be posted stays in the journal and is posted before the next
  claim; the row is never sent again while it waits.
- First SIGINT/SIGTERM: stop claiming, finish the send in progress and post its result. Second signal: kill the
  running zalo-agent (outcome "unknown"), try to post once, exit.
- Menu images: the claim says capabilities ["images"]; a cs_images item is sent with `msg send-image` (keys resolved
  through the local manifest, see menu_images.py) under the same journal rules, and reports every image's msgId.
- Label sync: `run` copies the Zalo role labels to the server (labels.py) at start and every LABEL_SYNC_EVERY_S
  seconds, on its own thread, so a slow or failing `label list` never delays a claim or a send. A failed sync is
  logged (counts and fixed words only) and tried again at the next period; 0 disables it.
"""

from __future__ import annotations

import logging
import random
import re
import signal
import threading
import time
from typing import Any

from . import labels
from .api import ApiError, BridgeApi, ServerUnavailable
from .config import Config
from .journal import Journal
from .sender import Sender, SendOutcome

log = logging.getLogger("bridge")
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
REPLAY = {"sent", "unknown", "sending"}


def _with_attempt(body: dict[str, Any], attempt: Any) -> dict[str, Any]:
    if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1:
        body["attempt"] = attempt
    return body


def mask(thread_id: Any) -> str:
    s = str(thread_id or "")
    return f"...{s[-4:]}" if len(s) > 4 else "..."


class Backoff:
    def __init__(self, start: float, cap: float, factor: float = 2.0):
        self.start, self.cap, self.factor = start, cap, factor
        self.current = 0.0

    def next(self) -> float:
        self.current = self.start if self.current <= 0 else min(self.current * self.factor, self.cap)
        return self.current

    def reset(self) -> None:
        self.current = 0.0


class Bridge:
    def __init__(self, cfg: Config, api: BridgeApi | None = None, sender: Sender | None = None,
                 journal: Journal | None = None):
        self.cfg = cfg
        self.api = api or BridgeApi(cfg.server_url, cfg.runner_token, cfg.bridge_id)
        self.sender = sender or Sender(cfg)
        self.journal = journal or Journal(cfg.state_dir)
        self.stop = threading.Event()        # stop claiming
        self.kill = threading.Event()        # cancel the running send
        self.next_send_at = 0.0              # monotonic time before which no row is claimed
        self.pause_until = 0.0               # monotonic; set after a not-logged-in failure
        self._last_warn: dict[str, float] = {}
        self.report_backoff = (1.0, 30.0)    # start, cap (seconds) between result retries
        self.label_sync = labels.sync_labels  # (cfg, cancel=...) -> (exit status, summary); replaced in tests
        self.label_thread: threading.Thread | None = None

    # ------------------------------------------------------------ helpers

    def _sleep(self, seconds: float, event: threading.Event | None = None) -> bool:
        """Sleep, waking early when `event` (default: stop) is set. Returns True if woken by the event."""
        return (event or self.stop).wait(max(0.0, seconds))

    def _warn_once(self, key: str, msg: str, *args: Any, every: float = 60.0) -> None:
        now = time.monotonic()
        if now - self._last_warn.get(key, -1e9) >= every:
            self._last_warn[key] = now
            log.warning(msg, *args)

    # ------------------------------------------------------------ results

    def report(self, item_id: str, body: dict[str, Any], max_tries: int | None = None) -> bool:
        """POST the result, retrying while the server is unreachable. Marks the journal row reported."""
        backoff = Backoff(*self.report_backoff)
        tries = 0
        while True:
            tries += 1
            try:
                self.api.result(item_id, body)
                self.journal.record(item_id, reported=True)
                return True
            except ApiError as e:
                if e.status == 401:
                    self._warn_once("report401", "result for %s: token rejected (401); will retry", item_id)
                else:
                    # The server refused this result (e.g. the lease moved on). Keep the outcome: if the row comes
                    # back, it is re-reported from the journal instead of being sent again.
                    log.warning("result for %s refused: %s", item_id, e)
                    self.journal.record(item_id, reported=True, report_refused=e.code)
                    return False
            except ServerUnavailable as e:
                self._warn_once("report_down", "result for %s not posted (%s); will retry", item_id, e)
            if self.kill.is_set():
                return False
            limit = max_tries if max_tries is not None else (5 if self.stop.is_set() else None)
            if limit is not None and tries >= limit:
                return False
            if self._sleep(backoff.next(), self.kill):
                return False

    def flush_unreported(self, max_tries: int | None = 1) -> int:
        """Post results that an earlier loop or an earlier process could not post. Returns how many remain."""
        left = 0
        for row in self.journal.unreported():
            status = row.get("status")
            if status == "sending":
                # The process died (or was killed) while zalo-agent was sending: nobody knows if it went out.
                self.journal.record(row["id"], status="unknown",
                                    error="bridge_restarted: bridge stopped while zalo-agent was sending")
                row = self.journal.get(row["id"]) or row
                status = "unknown"
            if status not in ("sent", "failed", "unknown"):
                continue
            body = _with_attempt(SendOutcome(status, row.get("zalo_msg_id"), row.get("error"),
                                             part_msg_ids=row.get("part_msg_ids")).result_body(),
                                 row.get("attempt"))
            if not self.report(row["id"], body, max_tries=max_tries):
                left += 1
        return left

    # ------------------------------------------------------------ one row

    def process_item(self, item: dict[str, Any]) -> dict[str, Any]:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not ITEM_ID_RE.match(item_id):
            log.error("claimed item has no usable id; skipped")
            return {"status": "skipped", "error": "invalid_item_id"}
        attempt = item.get("attempt")
        prev = self.journal.get(item_id)
        requeued_at = item.get("requeued_at")
        if prev and prev.get("status") in REPLAY and isinstance(requeued_at, int) and not isinstance(requeued_at, bool) \
                and requeued_at > int(prev.get("at") or 0):
            # Staff looked at the phone and chose "requeue" (POST /staff/outbox/:id/decide) after this bridge recorded
            # its outcome: that is a decision to send again, not a redelivery of the same claim.
            log.warning("item %s was %s on this bridge, then requeued by staff; sending it again",
                        item_id, prev["status"])
            prev = None
        if prev and prev.get("status") in REPLAY:
            status = "unknown" if prev["status"] == "sending" else prev["status"]
            error = prev.get("error") if status == prev["status"] else \
                "bridge_restarted: bridge stopped while zalo-agent was sending"
            # Re-posted for the current claim, so it carries the current attempt.
            self.journal.record(item_id, status=status, error=error, attempt=attempt, reported=False)
            log.warning("item %s was already %s on this bridge; re-posting the result, not sending again",
                        item_id, prev["status"])
            outcome = SendOutcome(status, prev.get("zalo_msg_id"), error, part_msg_ids=prev.get("part_msg_ids"))
            reported = self.report(item_id, _with_attempt(outcome.result_body(), attempt))
            return {"id": item_id, "status": status, "sent_now": False, "replayed": True, "reported": reported}

        self.journal.record(item_id, status="sending", attempt=attempt, reported=False,
                            zalo_msg_id=None, error=None, part_msg_ids=None)
        if item.get("thread_type") not in (None, 0):
            outcome = SendOutcome("failed", error="invalid_item: only 1-1 threads (thread_type 0) are sent")
        elif item.get("kind") == "cs_images":
            # Menu images: send the keys' JPEGs, never the row's text (a staff-facing label).
            outcome = self.sender.send_images(item.get("thread_id"), item.get("images"), cancel=self.kill)
        else:
            outcome = self.sender.send(item.get("thread_id"), item.get("text"), cancel=self.kill)
        self.journal.record(item_id, status=outcome.status, zalo_msg_id=outcome.zalo_msg_id, error=outcome.error,
                            part_msg_ids=outcome.part_msg_ids)
        gap = self.cfg.send_min_interval_s + (random.uniform(0, self.cfg.send_jitter_s)
                                              if self.cfg.send_jitter_s > 0 else 0.0)
        self.next_send_at = time.monotonic() + gap
        if outcome.login_required:
            self.pause_until = time.monotonic() + self.cfg.login_pause_s
            log.error("zalo-agent is not logged in; pausing sends for %.0f s. Owner: run `zalo-agent login`",
                      self.cfg.login_pause_s)
        log.info("item %s (%s, thread %s, attempt %s): %s%s", item_id, item.get("kind"), mask(item.get("thread_id")),
                 attempt, outcome.status, f" [{outcome.error.split(':')[0]}]" if outcome.error else "")
        reported = self.report(item_id, _with_attempt(outcome.result_body(), attempt))
        return {"id": item_id, "status": outcome.status, "sent_now": outcome.status == "sent",
                "replayed": False, "reported": reported, "error": outcome.error}

    # ------------------------------------------------------------ label sync

    def sync_labels_once(self) -> bool:
        """One label sync that never raises: a failure is logged and left to the next period."""
        try:
            code, summary = self.label_sync(self.cfg, cancel=self.stop)
        except Exception as e:   # noqa: BLE001 - the sync must never take the bridge down
            log.error("label sync crashed (%s); will retry next period", type(e).__name__)
            return False
        if self.stop.is_set() and summary.get("error") == "cancelled":
            return False
        if code == 0:
            log.info("label sync: %s", labels.describe(summary))
        else:
            log.warning("label sync: %s; will retry next period", labels.describe(summary))
        return code == 0

    def _label_sync_loop(self, every: float) -> None:
        while not self.stop.is_set():
            self.sync_labels_once()
            if self._sleep(every):
                return

    def start_label_sync(self) -> threading.Thread | None:
        """Start the periodic sync (now, then every LABEL_SYNC_EVERY_S) on a daemon thread; None when disabled."""
        every = self.cfg.label_sync_every_s
        if every <= 0 or (self.label_thread is not None and self.label_thread.is_alive()):
            return self.label_thread if every > 0 else None
        self.label_thread = threading.Thread(target=self._label_sync_loop, args=(every,), name="label-sync",
                                             daemon=True)
        self.label_thread.start()
        return self.label_thread

    # ------------------------------------------------------------ loop

    def run_once(self) -> dict[str, Any]:
        """Post pending results, then claim and process at most one row (no pacing wait)."""
        self.flush_unreported()
        item, _poll = self.api.claim()
        if not item:
            return {"status": "idle"}
        return self.process_item(item)

    def run_forever(self) -> None:
        idle = Backoff(1.0, 3.0, 1.5)
        down = Backoff(1.0, 30.0)
        log.info("bridge %s polling %s", self.cfg.bridge_id, self.cfg.server_url)
        self.start_label_sync()
        while not self.stop.is_set():
            if self.journal.unreported() and self.flush_unreported() > 0:
                if self._sleep(down.next()):
                    break
                continue
            wait = max(self.next_send_at, self.pause_until) - time.monotonic()
            if wait > 0:
                if self._sleep(wait):
                    break
                continue
            try:
                item, poll_s = self.api.claim()
            except ServerUnavailable as e:
                self._warn_once("claim_down", "server unavailable (%s); backing off", e)
                if self._sleep(down.next()):
                    break
                continue
            except ApiError as e:
                hint = {401: "token rejected: RUNNER_TOKEN differs from apps/server/.dev.vars",
                        404: "server has no Bridge API: is it a build with the personal Zalo channel?"}
                self._warn_once(f"claim{e.status}", "claim failed: %s (%s)", e, hint.get(e.status, e.code))
                if self._sleep(30.0):
                    break
                continue
            down.reset()
            if not item:
                wait = min(poll_s, 30.0) if poll_s else idle.next()
                if self._sleep(wait):
                    break
                continue
            idle.reset()
            self.process_item(item)
        if self.journal.unreported():
            self.flush_unreported(max_tries=3)
        log.info("bridge stopped")

    def install_signals(self) -> None:
        def handler(signum, _frame):
            if not self.stop.is_set():
                log.info("signal %s: finishing the send in progress, then exiting (again to abort it)", signum)
                self.stop.set()
            else:
                log.warning("second signal: aborting the send in progress (its outcome becomes unknown)")
                self.kill.set()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
