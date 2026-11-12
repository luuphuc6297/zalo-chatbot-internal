"""Per-conversation working directories, session aging and deletion of Claude Code session files.

Layout under $THOMHOUSE_BOT_HOME (default ~/.thomhouse-bot):
  conversations/<conversation_id>/   cwd of every `claude -p` call for that conversation (internal cnv_ id,
                                     never the Zalo id, so Claude Code's project dir name carries no Zalo id)
  state/sessions/<conversation_id>.json  local session record: session_id, started/last turn, customer
                                     message count, catalog_version, last cumulative total_cost_usd
  sessions/                          claude_pool's shared `projects/` target; Claude Code writes
                                     sessions/<project dir name>/<session_id>.jsonl (+ <session_id>/ for extras)
  rooms/<conversation_id>.json       two-bot rooms only: the room (channel id) of that conversation, written by
                                     room_engine.py; removed by forget_conversation

The server decides sessions (session_id null + reason). The runner also ages a session the server handed out
when its own record shows: 20 customer messages, 24 h idle, or a catalog_version change. That restart is reported
to the server as error_kind "session_restarted".

Deletion only touches paths that are provably this session's: inside $THOMHOUSE_BOT_HOME/sessions, named exactly
<session_id>.jsonl / <session_id>/, in the project dir derived from this conversation's workdir (or whose
transcript records that workdir as cwd). Nothing under ~/.claude is ever touched, so sessions run on an account
registered with `add-default` (config_dir null -> ~/.claude/projects) are not deleted by the runner.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .contract import ClaimedJob

MAX_CUSTOMER_MESSAGES = 20
MAX_IDLE_MS = 24 * 3600 * 1000
CONV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SESSION_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]{7,63}$")
ROOM_SESSION_PREFIX = "room."                       # session id of a draft written in a two-bot room


def now_ms() -> int:
    return int(time.time() * 1000)


def project_dir_name(path: str) -> str:
    """Claude Code's projects/ folder name for a cwd: every non-alphanumeric character becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


@dataclass
class SessionRecord:
    session_id: str
    started_at: int
    last_turn_at: int
    customer_messages: int
    catalog_version: str
    last_total_cost_usd: float | None = None


@dataclass
class SessionPlan:
    resume_id: str | None             # pass --resume when set
    reason: str | None                # why a new session starts (server reason or runner rule)
    runner_reset: bool = False        # runner discarded the server's session -> error_kind session_restarted
    drop: list[str] = field(default_factory=list)   # session ids whose local files should be deleted


class SessionStore:
    def __init__(self, home: Path):
        self.home = home
        self.conv_root = home / "conversations"
        self.state_root = home / "state" / "sessions"
        self.sessions_root = home / "sessions"

    # ------------------------------------------------------------ paths and records

    def workdir(self, conversation_id: str) -> Path:
        if not CONV_ID_RE.match(conversation_id or ""):
            raise ValueError("conversation_id is not a safe internal id")
        d = self.conv_root / conversation_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _record_path(self, conversation_id: str) -> Path:
        if not CONV_ID_RE.match(conversation_id or ""):
            raise ValueError("conversation_id is not a safe internal id")
        return self.state_root / f"{conversation_id}.json"

    def load(self, conversation_id: str) -> SessionRecord | None:
        try:
            d = json.loads(self._record_path(conversation_id).read_text(encoding="utf-8"))
            return SessionRecord(**{k: d.get(k) for k in SessionRecord.__dataclass_fields__})
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def save(self, conversation_id: str, rec: SessionRecord) -> None:
        p = self._record_path(conversation_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(rec)), encoding="utf-8")
        tmp.replace(p)

    def clear(self, conversation_id: str) -> None:
        self._record_path(conversation_id).unlink(missing_ok=True)

    # ------------------------------------------------------------ aging

    def plan(self, job: ClaimedJob, now: int | None = None) -> SessionPlan:
        now = now or now_ms()
        conv = job.conversation
        rec = self.load(conv.conversation_id)
        sid = conv.session_id
        if not sid:
            drop = [rec.session_id] if rec and rec.session_id else []
            return SessionPlan(None, conv.session_reset_reason or "new_conversation", drop=drop)
        if sid.startswith(ROOM_SESSION_PREFIX):
            # The last draft came from a two-bot room (docs/contracts.md 14.8): claude -p cannot resume it, so a new
            # session starts and the server is told the session restarted.
            drop = [rec.session_id] if rec and rec.session_id else []
            return SessionPlan(None, "room_session", runner_reset=True, drop=drop)
        if rec and rec.session_id == sid:
            reason = None
            if rec.customer_messages >= MAX_CUSTOMER_MESSAGES:
                reason = "turn_limit"
            elif rec.last_turn_at and now - rec.last_turn_at > MAX_IDLE_MS:
                reason = "idle"
            elif rec.catalog_version and conv.catalog_version and rec.catalog_version != conv.catalog_version:
                reason = "catalog_changed"
            if reason:
                return SessionPlan(None, reason, runner_reset=True, drop=[sid])
            return SessionPlan(sid, None)
        # Server knows a session this runner has no record of (record lost, or another runner): trust it.
        drop = [rec.session_id] if rec and rec.session_id and rec.session_id != sid else []
        return SessionPlan(sid, None, drop=drop)

    def record_turn(self, job: ClaimedJob, new_sid: str, resumed_id: str | None, total_cost: float | None,
                    now: int | None = None) -> float:
        """Store the session after a successful call; returns this turn's cost (delta of the cumulative
        total_cost_usd inside a resumed session)."""
        now = now or now_ms()
        cid = job.conversation.conversation_id
        rec = self.load(cid)
        same = bool(resumed_id) and rec is not None and rec.session_id == resumed_id
        total = float(total_cost or 0.0)
        if resumed_id and same and rec.last_total_cost_usd is not None:
            delta = max(total - rec.last_total_cost_usd, 0.0)
        else:
            # New session: the total is this turn. Resumed without a local baseline: the total is an upper bound.
            delta = total
        count = (rec.customer_messages if same else 0) + len(job.new_customer_messages)
        if same and rec.started_at:
            started = rec.started_at
        elif resumed_id and job.conversation.session_started_at:
            started = job.conversation.session_started_at
        else:
            started = now
        self.save(cid, SessionRecord(session_id=new_sid, started_at=started, last_turn_at=now,
                                     customer_messages=count, catalog_version=job.conversation.catalog_version,
                                     last_total_cost_usd=total))
        return round(delta, 6)

    # ------------------------------------------------------------ deletion

    def _forbidden_roots(self) -> list[Path]:
        return [(Path.home() / ".claude").resolve()]

    def _safe(self, p: Path, root: Path) -> bool:
        try:
            rp = p.resolve()
        except OSError:
            return False
        if any(rp == f or f in rp.parents for f in self._forbidden_roots()):
            return False
        return root in rp.parents

    def _project_dirs(self, conversation_id: str) -> list[Path]:
        wd = self.conv_root / conversation_id
        names = {project_dir_name(str(wd))}
        try:
            names.add(project_dir_name(str(wd.resolve())))
        except OSError:
            pass
        return [self.sessions_root / n for n in sorted(names)]

    @staticmethod
    def _transcript_cwd(path: Path) -> str | None:
        try:
            with path.open(encoding="utf-8") as f:
                for _, line in zip(range(50), f):
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(d, dict) and d.get("cwd"):
                        return str(d["cwd"])
        except OSError:
            return None
        return None

    def delete_session_files(self, conversation_id: str, session_id: str) -> list[Path]:
        if not session_id or not SESSION_ID_RE.match(session_id) or not CONV_ID_RE.match(conversation_id or ""):
            return []
        if not self.sessions_root.is_dir():
            return []
        root = self.sessions_root.resolve()
        wd = self.conv_root / conversation_id
        cwds = {str(wd)}
        try:
            cwds.add(str(wd.resolve()))
        except OSError:
            pass
        dirs = {d for d in self._project_dirs(conversation_id) if d.is_dir()}
        # Project dir naming is Claude Code internals (long paths get hashed); fall back to transcripts that
        # record this conversation's workdir as cwd.
        for t in self.sessions_root.glob(f"*/{session_id}.jsonl"):
            if self._transcript_cwd(t) in cwds:
                dirs.add(t.parent)
        deleted: list[Path] = []
        for d in dirs:
            for p in (d / f"{session_id}.jsonl", d / session_id):
                if not (p.exists() or p.is_symlink()) or not self._safe(p, root):
                    continue
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                deleted.append(p)
        return deleted

    def forget_conversation(self, conversation_id: str) -> list[Path]:
        """Customer data deletion: every session file of this conversation's project dir, the workdir, the room
        map file and the local record. ~/.claude is not touched."""
        if not CONV_ID_RE.match(conversation_id or ""):
            raise ValueError("conversation_id is not a safe internal id")
        deleted: list[Path] = []
        rec = self.load(conversation_id)
        if rec and rec.session_id:
            deleted += self.delete_session_files(conversation_id, rec.session_id)
        if self.sessions_root.is_dir():
            root = self.sessions_root.resolve()
            for d in self._project_dirs(conversation_id):
                if d.is_dir() and not d.is_symlink() and self._safe(d / "x", root):
                    shutil.rmtree(d)
                    deleted.append(d)
        wd = self.conv_root / conversation_id
        if wd.is_dir() and not wd.is_symlink():
            shutil.rmtree(wd)
            deleted.append(wd)
        room_map = self.home / "rooms" / f"{conversation_id}.json"
        if room_map.is_file() and not room_map.is_symlink():
            room_map.unlink()
            deleted.append(room_map)
        self.clear(conversation_id)
        return deleted


def default_account_in_pool(accounts: list[dict]) -> bool:
    """True when an account uses the machine's default login (~/.claude): its session files are outside
    $THOMHOUSE_BOT_HOME/sessions and the runner cannot delete them."""
    return any(a.get("enabled", True) and not a.get("config_dir") for a in accounts)


__all__ = ["SessionStore", "SessionPlan", "SessionRecord", "project_dir_name", "default_account_in_pool",
           "MAX_CUSTOMER_MESSAGES", "MAX_IDLE_MS", "now_ms"]
