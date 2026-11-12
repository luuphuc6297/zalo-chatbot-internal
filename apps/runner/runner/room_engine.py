"""Two-bot rooms engine (docs/contracts.md 14.8).

RoomEngine has the same seam as ClaudeRunner (run_job, pool_snapshot, pool_has_account, use_account, pool) and wraps
it: the pool and the fallback are the wrapped direct engine's. One draft turn:

  1. make sure the team is applied and the conversation's room exists; keep the channel id; when the reply rules
     live in CLAUDE.md, keep a copy in the lead bot's platform workspace, where its room turns run
  2. a new room first gets the `seed` feed as one unmentioned message
  3. create the ticket tk_<32 hex> bound to the leased job
  4. post one message that mentions the lead bot (ticket line, turn context, what happened since, whether this is the
     assistant's first reply to the customer, messages to answer)
  5. wait for the room job; obey cancel, the lease and ROOM_TURN_TIMEOUT_S
  6. validate the lead bot's final text and return it as the draft (session_id "room.<cnv_id>")
  7. always delete the ticket

On any failure before a valid reply, ROOM_FALLBACK=claude runs the wrapped engine on a copy of the job (room session
id cleared, history from the seed feed); ROOM_FALLBACK=fail answers /fail with `internal` or `timeout`.

Every call to the platform CLI goes through PlatformCli.run: minimal environment (no runner token, no Claude
tokens), OMB_DATA_DIR, OPENMAUSBOT_NODE_DIR first on PATH, a timeout, its own process group, defensive JSON parsing.
Log lines carry ids, exit codes and reason codes only: never message text, never a ticket.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import room_setup as setup
from .api import ApiClient, ServerUnavailable
from .claude_runner import CallHandle, ClaudeRunner, Outcome, _kill_group, _short
from .config import Config
from .contract import ApiError, ClaimedJob, DraftRequest, FailRequest, HistoryMessage, Usage
from .prompt import TZ, neutralize, profile_block

log = logging.getLogger("runner.rooms")

CONV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SEND_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
TICKET_IN_TEXT_RE = re.compile(r"tk_[0-9a-f]{8,}|[\[［]\s*phiếu", re.IGNORECASE)
MENTION_IN_TEXT_RE = re.compile(r"[@＠]\s*bot", re.IGNORECASE)
TICKET_LINE_RE = re.compile(r"\[(\s*phiếu)", re.IGNORECASE)
SOURCE_LABEL = {"customer": "Khách", "staff": "Lễ tân", "bot": "Bot", "server": "Hệ thống"}
HISTORY_SOURCES = ("customer", "bot", "staff", "server")
CLI_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CLI_ENV_KEEP = ("HOME", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR")
EXIT_TIMEOUT = 4                                       # platform CLI: the wait timed out
SHORT_CALL_S = 20.0
APPLY_CALL_S = 75.0
TICKET_SLACK_S = 60
STALE_TICKET_S = 3600

SEED_HEADER = "Bối cảnh: các tin trước đây trong cuộc trò chuyện này với khách. Không bot nào cần trả lời tin này."
OBSERVE_HEADER = ("Bối cảnh: tin mới trong cuộc trò chuyện với khách, đã có người xử lý. "
                  "Không bot nào cần trả lời tin này.")
SINCE_HEADER = "Từ lượt trước đến giờ (những việc đã xảy ra với khách, không cần trả lời từng dòng):"
UNSENT_HEADER = "Các bản nháp trước của bạn CHƯA được gửi cho khách, đừng coi như đã nói:"
ANSWER_HEADER = "Tin khách cần trả lời:"
# The direct engine knows whether it already answered this customer: its resumed session holds its own replies, and a
# new session gets the sent ones as "assistant (sent)" history. The system prompt makes the assistant introduce itself
# only in its first reply. A room turn states the same fact: has a bot message reached the customer.
FIRST_REPLY_NOTE = ("Bạn (trợ lý AI của thom house) chưa có tin nào gửi tới khách trong cuộc trò chuyện này, "
                    "nên câu trả lời lần này là câu trả lời đầu tiên của bạn.")
LATER_REPLY_NOTE = ("Bạn (trợ lý AI của thom house) đã có tin gửi tới khách trong cuộc trò chuyện này, nên câu trả "
                    "lời lần này không phải câu trả lời đầu tiên: không giới thiệu lại mình là trợ lý AI.")


class RoomFailure(Exception):
    """A room turn that cannot give a valid reply. `reason` is a short code, safe to log and to send to the server."""

    def __init__(self, reason: str, kind: str = "internal"):
        super().__init__(reason)
        self.reason, self.kind = reason, kind


class RoomsOff(Exception):
    """The server answered enabled: false (flag off or migration missing)."""


class RoomIneligible(Exception):
    """The draft-turn feed has no entry for the conversation: it may not have a room (14.7 eligibility: not a
    one-to-one personal conversation, no ai_assistant consent, a minor, or an internal contact). The server answers
    one entry, with `messages: []` when nothing waits, for every eligible conversation."""


class _Cancelled(Exception):
    pass


# ---------------------------------------------------------------- text helpers

def at_safe(text: str) -> str:
    """A copied text can never wake a bot: the ASCII at-sign becomes the full-width one."""
    return (text or "").replace("@", "＠")


def ticket_safe(text: str) -> str:
    """No mention and no look-alike of the system's ticket line (server-built blocks can carry a display name)."""
    return TICKET_LINE_RE.sub(r"［\1", at_safe(text))


def guard(text: str) -> str:
    """Untrusted text for a room message: no fake blocks, no mention, no look-alike of the system's ticket line."""
    return ticket_safe(neutralize(text or ""))


def one_line(text: str) -> str:
    return " ".join(guard(text).split())


def row_time(ms: Any, now: datetime | None = None) -> str:
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or ms <= 0:
        return "?"
    at = datetime.fromtimestamp(ms / 1000, TZ)
    today = (now or datetime.now(TZ)).date()
    return at.strftime("%H:%M") if at.date() == today else at.strftime("%d/%m %H:%M")


def row_line(row: dict[str, Any]) -> str:
    """One feed row as `[Lễ tân 14:02] text`; a row without text shows its kind."""
    label = SOURCE_LABEL.get(row.get("source"), "Hệ thống")
    text = one_line(row.get("text") if isinstance(row.get("text"), str) else "")
    if not text:
        text = f"({one_line(str(row.get('kind') or 'tin không có chữ'))})"
    return f"[{label} {row_time(row.get('at'))}] {text}"


def send_id(kind: str, key: str) -> str:
    """Idempotency key of a room message: 16 to 80 characters of letters, digits, `-` and `_`."""
    sid = f"thom-{kind}-{key}"
    if SEND_ID_RE.match(sid):
        return sid
    return f"thom-{kind}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:40]}"


def parse_json(out: str | None) -> dict[str, Any] | None:
    """The JSON object a CLI call printed: the whole output, else its last line that is an object."""
    out = (out or "").strip()
    if not out:
        return None
    try:
        v = json.loads(out)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            v = json.loads(line)
        except ValueError:
            continue
        if isinstance(v, dict):
            return v
    return None


def feed_rows(feed: dict[str, Any], conversation_id: str) -> list[dict[str, Any]]:
    """The rows of one conversation in a feed answer, well formed ones only."""
    for conv in feed.get("conversations") or []:
        if isinstance(conv, dict) and conv.get("conversation_id") == conversation_id:
            return [r for r in conv.get("messages") or []
                    if isinstance(r, dict) and isinstance(r.get("message_id"), str) and r["message_id"]]
    return []


def has_bot_row(rows: Any) -> bool:
    """True when a list of feed rows holds a bot message that reached the customer (the feed's row rule)."""
    return any(isinstance(r, dict) and r.get("source") == "bot" for r in rows or [])


def feed_has(feed: dict[str, Any], conversation_id: str) -> bool:
    """True when a feed answer has an entry for the conversation (even one without rows)."""
    return any(isinstance(conv, dict) and conv.get("conversation_id") == conversation_id
               for conv in feed.get("conversations") or [])


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


# ---------------------------------------------------------------- platform CLI

@dataclass
class CliResult:
    rc: int
    data: dict[str, Any] | None
    stderr: str = ""
    timed_out: bool = False


class PlatformCli:
    """The one way to call the rooms platform CLI."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in CLI_ENV_KEEP if os.environ.get(k)}
        env.setdefault("LANG", "en_US.UTF-8")
        node_dir = self.cfg.openmausbot_node_dir
        env["PATH"] = f"{node_dir}{os.pathsep}{CLI_PATH}" if node_dir else CLI_PATH
        env["OMB_DATA_DIR"] = str(self.cfg.platform_data_dir)
        return env

    def run(self, args: list[str], handle: CallHandle | None = None, timeout: float = SHORT_CALL_S,
            stdin_text: str | None = None) -> CliResult:
        if handle is not None and handle.cancelled:
            return CliResult(-9, None, "cancelled")
        cmd = [str(self.cfg.openmausbot_bin), *args, "--json"]
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                 errors="replace", env=self.env(), start_new_session=True)
        except OSError as e:
            return CliResult(127, None, type(e).__name__)
        if handle is not None:
            handle.add(p)
        timed_out = False
        try:
            try:
                out, err = p.communicate(stdin_text, timeout=max(1.0, timeout))
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(p)
                out, err = p.communicate()
        finally:
            if handle is not None:
                handle.remove(p)
        return CliResult(p.returncode, parse_json(out), err or "", timed_out)


# ---------------------------------------------------------------- engine

class RoomEngine:
    def __init__(self, cfg: Config, api: ApiClient, claude: ClaudeRunner):
        self.cfg, self.api, self.claude = cfg, api, claude
        self.cli = PlatformCli(cfg)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._team_lock = threading.Lock()              # one team.json, one `team apply` at a time
        self._prompt: dict[str, Any] | None = None      # {"hash", "system"} of the last GET /runner/prompt
        # (lead bot id, sha256 of the CLAUDE.md text) last written to the lead's platform workspace; ("", "none")
        # once the copies were removed because the rules fit the instructions. Guarded by _team_lock.
        self._lead_rules: tuple[str, str] | None = None

    # -- the pool belongs to the wrapped direct engine

    @property
    def pool(self):
        return self.claude.pool

    def pool_snapshot(self, with_login: bool = False) -> dict[str, Any]:
        return self.claude.pool_snapshot(with_login=with_login)

    def pool_has_account(self) -> bool:
        return self.claude.pool_has_account()

    def use_account(self, label: str):
        return self.claude.use_account(label)

    def conversation_lock(self, conversation_id: str) -> threading.Lock:
        """Shared by draft turns and the observation loop, so the two never post the same rows."""
        with self._locks_guard:
            return self._locks.setdefault(conversation_id, threading.Lock())

    # ------------------------------------------------------------ draft turn

    def run_job(self, job: ClaimedJob, handle: CallHandle) -> Outcome:
        started = time.monotonic()
        cid = job.conversation.conversation_id
        try:
            with self.conversation_lock(cid):
                return self._room_turn(job, handle, started)
        except _Cancelled:
            return Outcome("cancelled", cancel_reason=handle.cancel_reason)
        except RoomsOff:
            log.info("rooms are off on the server; job %s runs on the direct engine", job.job_id)
            return self.claude.run_job(self._direct_job(job, with_seed=False), handle)
        except RoomIneligible:
            log.info("conversation of job %s may not use a room; it runs on the direct engine", job.job_id)
            return self.claude.run_job(self._direct_job(job, with_seed=False), handle)
        except RoomFailure as e:
            failure = e
        except (ApiError, ServerUnavailable) as e:
            failure = RoomFailure(f"server_{type(e).__name__}")
        except Exception as e:  # noqa: BLE001 - a room problem must end in the fallback, not in /fail internal
            log.exception("room turn crashed for job %s", job.job_id)
            failure = RoomFailure(f"crash_{type(e).__name__}")
        if handle.cancelled:
            return Outcome("cancelled", cancel_reason=handle.cancel_reason)
        log.warning("room turn failed for job %s (%s, %s); fallback=%s", job.job_id, failure.reason, failure.kind,
                    self.cfg.room_fallback)
        if self.cfg.room_fallback == "fail":
            return Outcome("fail", fail=FailRequest(
                error_kind=failure.kind, error_message=_short(f"room turn failed: {failure.reason}"),
                account_label=self._account(required=False), session_id=None, session_broken=False))
        handle.timed_out = False                        # the room's timeout is not the direct engine's
        return self.claude.run_job(self._direct_job(job), handle)

    def _room_turn(self, job: ClaimedJob, handle: CallHandle, started: float) -> Outcome:
        cid = job.conversation.conversation_id
        if not CONV_ID_RE.match(cid or ""):
            raise RoomFailure("bad_conversation_id")
        deadline = started + self.cfg.room_turn_timeout_s
        feed = self.api.rooms_feed(cid)                                             # step 4 reads it; read once
        if feed.get("enabled") is False:
            raise RoomsOff()
        if not feed_has(feed, cid):
            raise RoomIneligible()
        pending = feed_rows(feed, cid)
        account = self._account()
        room = self._ensure_room(cid, account, job.prompt_hash, handle, deadline)     # step 1
        self._check(handle)
        new_ids = [m.message_id for m in job.new_customer_messages]
        if not room.get("seeded"):                                                  # step 2
            self._seed(cid, room, {r["message_id"] for r in pending} | set(new_ids), handle, deadline)
        replied = self._bot_replied(cid, room, pending, job)
        ticket = self._new_ticket(job)                                              # step 3
        sent = False
        try:
            text = self.turn_message(job, ticket, pending, replied)                 # step 4
            sent = True     # from here a room job may run, even when the send call itself is cut short by a cancel
            send = self._send(cid, room, text, send_id("turn", f"{job.job_id}-a{job.attempt}"), handle, deadline)
            ack_ids = list(dict.fromkeys([r["message_id"] for r in pending] + new_ids))
            self.api.rooms_ack(cid, ack_ids, room["channel_id"])
            data = self._wait(room, send.get("at"), handle, deadline)               # step 5
            sent = False                                                            # the room job is over
            reply, turns = self.final_reply(data, send.get("at"))                   # step 6
            self._validate(reply, ticket)
            return Outcome("draft", draft=DraftRequest(
                text=reply, session_id=f"room.{cid}", account_label=account, model=self.cfg.model,
                effort=self.cfg.effort, usage=Usage(), cost_usd_equiv=0.0,
                duration_ms=int((time.monotonic() - started) * 1000), num_turns=turns))
        finally:
            if sent:
                self._interrupt(room)   # cancel, lease lost, timeout, a failed send or a failed wait: stop the bots
            self._drop_ticket(ticket)                                               # step 7

    def _check(self, handle: CallHandle | None) -> None:
        if handle is not None and handle.cancelled:
            raise _Cancelled()

    def _left(self, deadline: float | None, cap: float) -> float:
        if deadline is None:
            return cap
        left = deadline - time.monotonic()
        if left <= 0:
            raise RoomFailure("timeout", "timeout")
        return min(cap, left)

    def _account(self, required: bool = True) -> str | None:
        """The pool account the bots run on: the one the direct engine would use next."""
        try:
            cands = self.claude.pool.candidates()
        except Exception:  # noqa: BLE001 - pool files are operator edited
            cands = []
        label = cands[0].get("label") if cands and isinstance(cands[0], dict) else None
        if not label and required:
            raise RoomFailure("no_usable_account")
        return label

    # ------------------------------------------------------------ step 1: team and room

    def _system_prompt(self, prompt_hash: str | None) -> dict[str, Any]:
        cached = self._prompt
        if cached is not None and (not prompt_hash or cached["hash"] == prompt_hash):
            return cached
        body = self.api.prompt()
        system = body.get("cli_system_prompt")
        if not isinstance(system, str) or not system.strip():
            raise RoomFailure("prompt_unavailable")
        tools = [t for t in body.get("tools") or [] if isinstance(t, dict) and t.get("name") in setup.ROOM_TOOL_NAMES]
        if tools:                                       # the tools server prefers the server's definitions
            setup.write_json(self.cfg.rooms_dir / "tools.json", {"tools": tools})
        self._prompt = {"hash": str(body.get("prompt_hash") or prompt_hash or ""), "system": system}
        return self._prompt

    def _ensure_room(self, cid: str, account: str, prompt_hash: str | None, handle: CallHandle | None,
                     deadline: float | None, need_rules: bool = True) -> dict[str, Any]:
        """Apply the team when needed and keep the lead's rules in its platform workspace. `need_rules` False (the
        observation loop, where no bot runs): a failure to place the rules is logged, not raised."""
        setup.ensure_dirs(self.cfg)
        prompt = self._system_prompt(prompt_hash)
        instance = setup.instance_name(account)
        doc, claude_md = setup.build_team(self.cfg, instance, prompt["system"], cid)
        fingerprint = hashlib.sha256(json.dumps(
            {"defaults": doc["defaults"], "teams": doc["teams"], "bots": doc["bots"], "claude_md": claude_md},
            sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        map_path = self.cfg.rooms_dir / f"{cid}.json"
        room = read_json(map_path)
        if room is not None and not (isinstance(room.get("channel_id"), str) and room["channel_id"]):
            room = None
        state_path = self.cfg.rooms_dir / "state.json"
        with self._team_lock:
            state = read_json(state_path) or {}
            applied = False
            if state.get("fingerprint") != fingerprint or room is None:
                setup.write_lead_rules_file(self.cfg, claude_md)
                team_path = self.cfg.rooms_dir / "team.json"
                setup.write_json(team_path, doc)
                res = self.cli.run(["team", "apply", str(team_path), "--wait-idle", "30s"], handle,
                                   timeout=self._left(deadline, APPLY_CALL_S))
                self._check(handle)
                if res.rc != 0:
                    log.warning("team apply failed (exit %s): %s", res.rc, _short(res.stderr, 300))
                    raise RoomFailure("team_apply_timeout" if res.timed_out else f"team_apply_exit_{res.rc}")
                setup.write_json(state_path, {
                    "prompt_hash": prompt["hash"], "instance": instance, "model": self.cfg.model,
                    "customer_model": self.cfg.room_customer_model or self.cfg.model, "fingerprint": fingerprint,
                    "applied_at": int(time.time() * 1000)})
                applied = True
            if need_rules or applied:
                try:
                    self._sync_lead_rules(claude_md, applied, handle, deadline)
                except RoomFailure as e:
                    if e.reason == "lead_bot_missing":
                        # The next turn applies the team again, which creates the lead bot when it is gone.
                        try:
                            state_path.unlink()
                        except OSError:
                            pass
                    if need_rules:
                        raise
                    log.warning("lead rules not placed in the platform workspace (%s)", e.reason)
        if room is None:
            room = {"channel_id": self._find_channel(cid, handle, deadline), "room": setup.room_name(cid),
                    "seeded": False}
            setup.write_json(map_path, room)
        return room

    def _find_channel(self, cid: str, handle: CallHandle | None, deadline: float | None) -> str:
        res = self.cli.run(["channels"], handle, timeout=self._left(deadline, SHORT_CALL_S))
        self._check(handle)
        name = setup.room_name(cid)
        for ch in (res.data or {}).get("channels") or [] if res.rc == 0 else []:
            if isinstance(ch, dict) and ch.get("name") == name and isinstance(ch.get("id"), str) and ch["id"]:
                return ch["id"]
        raise RoomFailure("room_missing" if res.rc == 0 else f"channels_exit_{res.rc}")

    # ------------------------------------------------------------ step 1: the lead's rules in its platform workspace

    def _sync_lead_rules(self, claude_md: str | None, applied: bool, handle: CallHandle | None,
                         deadline: float | None) -> None:
        """A room turn of the lead bot runs in <data dir>/workspaces/<lead bot id>, so the CLAUDE.md of work/lead must
        also be there (room_setup module docstring). After a team apply the lead bot id is looked up again and the
        file written when its text differs; before any other turn a cheap check (file text, bots.json) decides
        whether that is needed. Copies in every other workspace (the customer bot's, a replaced lead's) are removed.
        Called under _team_lock."""
        if claude_md is None:                           # the rules fit the instructions: no copy anywhere
            if applied or self._lead_rules != ("", "none"):
                removed = setup.remove_workspace_rules(self.cfg)
                if removed:
                    log.info("removed the lead rules from %d platform workspaces", len(removed))
                self._lead_rules = ("", "none")
            return
        digest = hashlib.sha256(claude_md.encode("utf-8")).hexdigest()
        cached = self._lead_rules
        if (not applied and cached is not None and cached[1] == digest
                and setup.workspace_rules_match(self.cfg, cached[0], claude_md)
                and self._registry_lead(cached[0]) is not False):
            return
        bot_id = self._lead_bot_id(handle, deadline)
        try:
            written = setup.write_workspace_rules(self.cfg, bot_id, claude_md)
        except (OSError, ValueError) as e:
            log.warning("lead rules could not be written to the platform workspace (%s)", type(e).__name__)
            raise RoomFailure("lead_rules_unwritable") from None
        removed = setup.remove_workspace_rules(self.cfg, keep=bot_id)
        if written or removed:
            log.info("lead rules %s in the workspace of bot %s; removed from %d other workspaces",
                     "written" if written else "unchanged", bot_id, len(removed))
        self._lead_rules = (bot_id, digest)

    def _lead_bot_id(self, handle: CallHandle | None, deadline: float | None) -> str:
        """The platform id of the lead bot: `bots --json` first, <data dir>/bots.json (read only) when the CLI fails."""
        res = self.cli.run(["bots"], handle, timeout=self._left(deadline, SHORT_CALL_S))
        self._check(handle)
        listing = (res.data or {}).get("bots") if res.rc == 0 else None
        if not isinstance(listing, list):
            listing = setup.read_bots_file(self.cfg)
            if listing is None:
                raise RoomFailure("bots_timeout" if res.timed_out else f"bots_exit_{res.rc}")
            log.info("platform CLI `bots` failed (exit %s); the lead bot is read from bots.json", res.rc)
        lead_dir, _ = setup.work_dirs(self.cfg)
        bot_id, reason = setup.pick_lead_bot(listing, lead_dir)
        if bot_id is None:
            raise RoomFailure(reason)
        return bot_id

    def _registry_lead(self, bot_id: str) -> bool | None:
        """Whether bots.json still names `bot_id` as the lead bot; None when the file cannot be read."""
        listing = setup.read_bots_file(self.cfg)
        if listing is None:
            return None
        return setup.pick_lead_bot(listing, setup.work_dirs(self.cfg)[0])[0] == bot_id

    # ------------------------------------------------------------ steps 2 to 4: messages into the room

    def _send(self, cid: str, room: dict[str, Any], text: str, sid: str, handle: CallHandle | None,
              deadline: float | None) -> dict[str, Any]:
        res = self.cli.run(["send", "--channel", room["channel_id"], "-", "--send-id", sid], handle,
                           timeout=self._left(deadline, SHORT_CALL_S), stdin_text=text)
        self._check(handle)
        data = res.data or {}
        if res.rc != 0 or data.get("success") is False:
            # The room may be gone (platform data reset): forget it so that the next turn applies the team again.
            for stale in (self.cfg.rooms_dir / f"{cid}.json", self.cfg.rooms_dir / "state.json"):
                try:
                    stale.unlink()
                except OSError:
                    pass
            raise RoomFailure("send_timeout" if res.timed_out else f"send_exit_{res.rc}")
        return data

    def _seed(self, cid: str, room: dict[str, Any], skip: set[str], handle: CallHandle | None,
              deadline: float | None) -> None:
        """A new room gets the earlier context as one unmentioned message; then the rows are acked."""
        seed_rows = feed_rows(self.api.rooms_feed(cid, seed=True), cid)
        room["bot_replied"] = room.get("bot_replied") is True or has_bot_row(seed_rows)
        rows = [r for r in seed_rows if r["message_id"] not in skip]
        if rows:
            text = SEED_HEADER + "\n" + "\n".join(row_line(r) for r in rows)
            self._send(cid, room, text, send_id("seed", cid), handle, deadline)
            self.api.rooms_ack(cid, [r["message_id"] for r in rows], room["channel_id"])
        room["seeded"] = True
        setup.write_json(self.cfg.rooms_dir / f"{cid}.json", room)

    def _bot_replied(self, cid: str, room: dict[str, Any], pending: list[dict[str, Any]], job: ClaimedJob) -> bool:
        """Whether a bot message already reached the customer in this conversation. Every such message passes through
        the seed, a draft turn's pending rows or the observation loop, so the room map keeps the answer (`bot_replied`);
        a map written before the runner kept it asks the seed feed once."""
        seen = (room.get("bot_replied") is True or has_bot_row(pending)
                or any(m.source == "bot" for m in job.sent_since_last_draft)
                or any(h.source == "bot" for h in job.history))
        if not seen and "bot_replied" not in room:
            seen = has_bot_row(feed_rows(self.api.rooms_feed(cid, seed=True), cid))
        if room.get("bot_replied") is not seen:
            room["bot_replied"] = seen
            setup.write_json(self.cfg.rooms_dir / f"{cid}.json", room)
        return seen

    def turn_message(self, job: ClaimedJob, ticket: str, pending: list[dict[str, Any]],
                     replied: bool = False) -> str:
        new_ids = {m.message_id for m in job.new_customer_messages}
        parts = [f"@{setup.LEAD_BOT}\n[phiếu: {ticket}]"]
        if job.turn_context_text.strip():
            parts.append(ticket_safe(job.turn_context_text.strip()))
        pblock = profile_block(job.customer_profile)
        if pblock:
            parts.append(ticket_safe(pblock))
        since = [r for r in pending if r["message_id"] not in new_ids]
        if since:
            parts.append(SINCE_HEADER + "\n" + "\n".join(row_line(r) for r in since))
        if job.unsent_drafts_since_last:
            parts.append(UNSENT_HEADER + "\n" + "\n".join(f"- {one_line(d.text)}"
                                                         for d in job.unsent_drafts_since_last))
        parts.append(LATER_REPLY_NOTE if replied else FIRST_REPLY_NOTE)
        lines = [ANSWER_HEADER]
        for m in job.new_customer_messages:
            lines.append(f"<customer_message>\n{guard(m.text).strip()}\n</customer_message>")
            if m.attachments:
                kinds = ", ".join(sorted({one_line(a.type) for a in m.attachments}))
                lines.append(f"<attachment_note>With the message above the customer also sent: {kinds}. "
                             "You cannot view attachments.</attachment_note>")
        parts.append("\n".join(lines))
        return "\n\n".join(parts)

    # ------------------------------------------------------------ step 3 and 7: ticket

    def _new_ticket(self, job: ClaimedJob) -> str:
        tickets = self.cfg.rooms_dir / "tickets"
        tickets.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - STALE_TICKET_S
        for old in tickets.iterdir():                   # leftovers of a crashed runner
            try:
                if old.name.startswith("tk_") and old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                pass
        ticket = "tk_" + secrets.token_hex(16)
        setup.write_json(tickets / f"{ticket}.json", {
            "job_id": job.job_id, "conversation_id": job.conversation.conversation_id,
            "expires_at": int((time.time() + self.cfg.room_turn_timeout_s + TICKET_SLACK_S) * 1000)})
        return ticket

    def _drop_ticket(self, ticket: str) -> None:
        for name in (f"{ticket}.json", f"{ticket}.calls.jsonl"):
            try:
                (self.cfg.rooms_dir / "tickets" / name).unlink()
            except OSError:
                pass

    def _profile_was_read(self, ticket: str) -> bool:
        try:
            lines = (self.cfg.rooms_dir / "tickets" / f"{ticket}.calls.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        for line in lines:
            try:
                call = json.loads(line)
            except ValueError:
                continue
            if isinstance(call, dict) and call.get("tool") == setup.PROFILE_TOOL and call.get("is_error") is False:
                return True
        return False

    # ------------------------------------------------------------ step 5: wait

    def _wait(self, room: dict[str, Any], since: Any, handle: CallHandle, deadline: float) -> dict[str, Any]:
        args = ["wait", "--channel", room["channel_id"], "--for", "job"]
        if isinstance(since, (int, float)) and not isinstance(since, bool):
            args += ["--since", str(int(since))]
        for attempt in range(4):
            left = self._left(deadline, self.cfg.room_turn_timeout_s)
            res = self.cli.run([*args, "--timeout", f"{max(1, int(left))}s"], handle, timeout=left + 10)
            self._check(handle)
            if res.timed_out or res.rc == EXIT_TIMEOUT:
                raise RoomFailure("timeout", "timeout")
            if res.rc != 0:
                raise RoomFailure(f"wait_exit_{res.rc}")
            if res.data is None:
                raise RoomFailure("wait_output_unreadable")
            if res.data.get("state") == "completed" or self._bot_texts(res.data, since):
                return res.data
            # Exit 0 without a finished job: the wait may have run before the room job started.
            if attempt < 3:
                time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        raise RoomFailure("no_reply")

    def _interrupt(self, room: dict[str, Any]) -> None:
        """Stop the room job and every teammate still working on it. Never raises; not bound to the job handle."""
        try:
            res = self.cli.run(["interrupt", "--channel", room["channel_id"], "--tree"], None, timeout=SHORT_CALL_S)
            if res.rc != 0:
                log.warning("room interrupt failed (exit %s)", res.rc)
        except Exception:  # noqa: BLE001
            log.warning("room interrupt crashed")

    # ------------------------------------------------------------ step 6: the reply

    @staticmethod
    def _bot_texts(data: dict[str, Any], since: Any) -> list[dict[str, Any]]:
        floor = since if isinstance(since, (int, float)) and not isinstance(since, bool) else None
        out = []
        for m in data.get("messages") or []:
            if not isinstance(m, dict) or m.get("role") != "bot" or m.get("kind") != "text":
                continue                                # activity and digest entries are not replies
            if not isinstance(m.get("text"), str):
                continue
            at = m.get("at")
            if floor is not None and isinstance(at, (int, float)) and at < floor:
                continue
            out.append(m)
        return out

    def final_reply(self, data: dict[str, Any], since: Any) -> tuple[str, int]:
        """(final text of the lead bot, number of bot executions)."""
        job = data.get("job") if isinstance(data.get("job"), dict) else {}
        nodes = [n for n in job.get("nodes") or [] if isinstance(n, dict)]
        turns = sum(n["executions"] for n in nodes
                    if isinstance(n.get("executions"), int) and not isinstance(n.get("executions"), bool))
        turns = max(1, turns or len(nodes))
        texts = self._bot_texts(data, since)
        if texts:
            last = texts[-1]
            sender = last.get("from") if isinstance(last.get("from"), dict) else {}
            if sender.get("name") != setup.LEAD_BOT:
                raise RoomFailure("wrong_bot")
            return last["text"].strip(), turns
        roots = set(job.get("roots") or [])
        for n in nodes:                                 # no message list: the lead's own result
            if n.get("id") in roots and n.get("botName") == setup.LEAD_BOT and isinstance(n.get("result"), str):
                return n["result"].strip(), turns
        raise RoomFailure("no_reply")

    def _validate(self, reply: str, ticket: str) -> None:
        low = reply.lower()
        if not reply.strip():
            raise RoomFailure("empty_reply")
        if TICKET_IN_TEXT_RE.search(reply):
            raise RoomFailure("ticket_in_reply")
        if MENTION_IN_TEXT_RE.search(reply) or setup.LEAD_BOT.lower() in low or setup.CUSTOMER_BOT.lower() in low:
            raise RoomFailure("bot_name_in_reply")
        if setup.RULES_SENTINEL.lower() in low:
            raise RoomFailure("rules_not_loaded")
        if self.cfg.room_require_profile_read and not self._profile_was_read(ticket):
            raise RoomFailure("no_profile_read")

    # ------------------------------------------------------------ fallback

    def _direct_job(self, job: ClaimedJob, with_seed: bool = True) -> ClaimedJob:
        """The copy the direct engine runs: a room session id cannot be resumed by claude -p, and the history comes
        from the seed feed (the claim sends none for a conversation that already has a session)."""
        conv = job.conversation
        if isinstance(conv.session_id, str) and conv.session_id.startswith("room."):
            conv = dataclasses.replace(conv, session_id=None)
        history = job.history
        if with_seed:
            try:
                new_ids = {m.message_id for m in job.new_customer_messages}
                rows = feed_rows(self.api.rooms_feed(conv.conversation_id, seed=True), conv.conversation_id)
                seeded = [HistoryMessage(source=r["source"], text=r["text"], at=r["at"]) for r in rows
                          if r["message_id"] not in new_ids and r.get("source") in HISTORY_SOURCES
                          and isinstance(r.get("text"), str) and r["text"].strip()
                          and isinstance(r.get("at"), (int, float)) and not isinstance(r.get("at"), bool)]
                if seeded:
                    history = seeded
            except (ApiError, ServerUnavailable) as e:
                log.warning("seed feed unavailable for the fallback (%s); keeping the claimed history",
                            type(e).__name__)
        return dataclasses.replace(job, conversation=conv, history=history)

    # ------------------------------------------------------------ observation loop

    def observe_once(self) -> dict[str, Any]:
        """One tick of the observation loop: mirror pending rows of conversations without a draft turn into their
        rooms as unmentioned messages (no bot runs), then ack. Never raises."""
        stats: dict[str, Any] = {"enabled": True, "posted": 0, "skipped": 0, "failed": 0}
        try:
            feed = self.api.rooms_feed()
            if feed.get("enabled") is False:
                stats["enabled"] = False
                return stats
            for conv in feed.get("conversations") or []:
                cid = conv.get("conversation_id") if isinstance(conv, dict) else None
                if not isinstance(cid, str) or not CONV_ID_RE.match(cid):
                    continue
                lock = self.conversation_lock(cid)
                if not lock.acquire(blocking=False):    # a draft turn owns this conversation right now
                    stats["skipped"] += 1
                    continue
                try:
                    stats["posted"] += 1 if self._observe(cid, feed_rows(feed, cid)) else 0
                except RoomFailure as e:
                    stats["failed"] += 1
                    log.warning("observation of %s failed (%s)", cid, e.reason)
                except Exception as e:  # noqa: BLE001
                    stats["failed"] += 1
                    log.warning("observation of %s crashed (%s)", cid, type(e).__name__)
                finally:
                    lock.release()
        except Exception as e:  # noqa: BLE001 - the loop must never raise into the runner
            stats["failed"] += 1
            log.warning("observation tick failed (%s)", type(e).__name__)
        return stats

    def _observe(self, cid: str, rows: list[dict[str, Any]]) -> bool:
        if not rows:
            return False
        deadline = time.monotonic() + APPLY_CALL_S + 3 * SHORT_CALL_S
        room = self._ensure_room(cid, self._account(), None, None, deadline, need_rules=False)
        if not room.get("seeded"):
            self._seed(cid, room, {r["message_id"] for r in rows}, None, deadline)
        if has_bot_row(rows) and room.get("bot_replied") is not True:
            room["bot_replied"] = True              # these rows are acked below: the next turn no longer sees them
            setup.write_json(self.cfg.rooms_dir / f"{cid}.json", room)
        ids = [r["message_id"] for r in rows]
        text = OBSERVE_HEADER + "\n" + "\n".join(row_line(r) for r in rows)
        key = hashlib.sha256((cid + "\n" + "\n".join(ids)).encode("utf-8")).hexdigest()[:40]
        self._send(cid, room, text, send_id("obs", key), None, deadline)
        self.api.rooms_ack(cid, ids, room["channel_id"])
        return True
