"""Runner API wire shapes (mirror of docs/contracts.md "Runner API" and apps/server/src/types.ts).

Stdlib only. Every dataclass has from_dict (tolerates unknown keys, so additive server changes do not break the
runner) and to_dict. Times are integer milliseconds since epoch (UTC).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

RunnerErrorKind = Literal[
    "login_expired", "limited", "blocked", "no_account", "timeout", "session_broken",
    "model_error", "empty_output", "refusal", "cancelled", "internal",
]
ConversationMode = Literal["off", "draft_only", "approve_each", "auto_allowed"]
TOOL_NAMES = (
    "search_services", "get_service_details", "quote_price", "list_active_promotions",
    "create_booking_request", "handoff_to_staff", "record_contact_preference",
    "attach_menu_images",  # menu images (task B): attaches menu slide keys to the draft
)


def _pick(cls, d: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (d or {}).items() if k in names}


class _Wire:
    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        return cls(**_pick(cls, d))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- claim

@dataclass
class Attachment(_Wire):
    type: str
    url: str | None = None
    thumbnail: str | None = None
    name: str | None = None


@dataclass
class CustomerMessage(_Wire):
    message_id: str
    text: str
    kind: str
    sent_at: int
    attachments: list[Attachment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        kw = _pick(cls, d)
        kw["attachments"] = [Attachment.from_dict(a) for a in d.get("attachments") or []]
        return cls(**kw)


@dataclass
class SentMessage(_Wire):
    message_id: str
    source: Literal["bot", "staff", "server"]
    text: str
    sent_at: int
    from_draft_id: str | None = None
    edited_by_staff: bool = False


@dataclass
class UnsentDraft(_Wire):
    draft_id: str
    status: Literal["rejected", "blocked", "superseded", "discarded", "send_failed"]
    text: str


@dataclass
class HistoryMessage(_Wire):
    source: Literal["customer", "bot", "staff", "server"]
    text: str
    at: int


@dataclass
class ConversationRef(_Wire):
    conversation_id: str          # internal cnv_ id; use it (never a Zalo id) for the per-conversation workdir
    session_id: str | None        # None => start a new Claude Code session
    session_turns: int
    session_started_at: int | None
    session_reset_reason: str | None
    catalog_version: str


@dataclass
class ClaimedJob(_Wire):
    job_id: str
    type: Literal["draft_reply"]
    lease_until: int
    attempt: int
    conversation: ConversationRef
    turn_context: dict[str, Any]
    turn_context_text: str
    new_customer_messages: list[CustomerMessage]
    sent_since_last_draft: list[SentMessage]
    unsent_drafts_since_last: list[UnsentDraft]
    history: list[HistoryMessage]
    prompt_hash: str
    # Contact profiles (docs/contracts.md section 13, additive): derived facts only, or None. Keys: relationship
    # ('customer' | 'unknown'), address_term, name_to_use, services_likely_used, services_mentioned, and (additive,
    # profiles v2) last_service {name, date 'YYYY-MM-DD'} or absent.
    customer_profile: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, d):
        cp = d.get("customer_profile")
        return cls(
            job_id=d["job_id"], type=d["type"], lease_until=d["lease_until"], attempt=d.get("attempt", 1),
            conversation=ConversationRef.from_dict(d["conversation"]),
            turn_context=d.get("turn_context") or {},
            turn_context_text=d.get("turn_context_text", ""),
            new_customer_messages=[CustomerMessage.from_dict(m) for m in d.get("new_customer_messages") or []],
            sent_since_last_draft=[SentMessage.from_dict(m) for m in d.get("sent_since_last_draft") or []],
            unsent_drafts_since_last=[UnsentDraft.from_dict(m) for m in d.get("unsent_drafts_since_last") or []],
            history=[HistoryMessage.from_dict(m) for m in d.get("history") or []],
            prompt_hash=d.get("prompt_hash", ""),
            customer_profile=cp if isinstance(cp, dict) else None,
        )


@dataclass
class ClaimResponse(_Wire):
    job: ClaimedJob | None
    poll_after_ms: int
    reason: str | None = None

    @classmethod
    def from_dict(cls, d):
        j = d.get("job")
        return cls(job=ClaimedJob.from_dict(j) if j else None, poll_after_ms=d.get("poll_after_ms", 2000),
                   reason=d.get("reason"))


# ---------------------------------------------------------------- heartbeat / draft / fail

@dataclass
class HeartbeatResponse(_Wire):
    lease_until: int
    stale: bool = False
    cancel: bool = False
    cancel_reason: str | None = None


@dataclass
class Usage(_Wire):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class DraftRequest(_Wire):
    text: str
    session_id: str
    account_label: str | None
    model: str
    effort: str
    usage: Usage
    cost_usd_equiv: float          # this turn only: delta of total_cost_usd within the session
    duration_ms: int
    num_turns: int
    error_kind: Literal["session_restarted"] | None = None


@dataclass
class DraftResponse(_Wire):
    draft_id: str | None
    status: str
    action: str
    checker: dict[str, Any] | None = None
    message_id: str | None = None


@dataclass
class FailRequest(_Wire):
    error_kind: RunnerErrorKind
    error_message: str
    account_label: str | None
    session_id: str | None
    session_broken: bool
    usage: Usage | None = None
    cost_usd_equiv: float | None = None


@dataclass
class FailResponse(_Wire):
    job_status: str
    handoff_id: str | None = None


# ---------------------------------------------------------------- tools / prompt / status

@dataclass
class ToolRequest(_Wire):
    job_id: str
    input: dict[str, Any]


@dataclass
class ToolResponse(_Wire):
    result: Any
    is_error: bool
    tool_call_id: str
    replayed: bool = False


@dataclass
class PromptResponse(_Wire):
    catalog_version: str
    prompt_hash: str
    blocks: dict[str, str]
    cli_system_prompt: str
    tools: list[dict[str, Any]]


@dataclass
class PoolAccountStatus(_Wire):
    label: str
    priority: int | None
    enabled: bool
    pinned: bool
    pool_status: Literal["ok", "limited", "login_expired", "blocked", "error"]
    until: str | None
    usable_now: bool
    login: dict[str, Any] | None
    last_error: str
    last_ok: str | None = None


@dataclass
class StatusRequest(_Wire):
    runner_version: str
    hostname: str
    active_jobs: int
    max_concurrency: int
    accounts: list[PoolAccountStatus]
    next_account: str | None
    applied_desired_account: str
    reported_at: int


@dataclass
class StatusResponse(_Wire):
    ok: bool
    desired_account: str
    flags: dict[str, Any]


@dataclass
class ApiError(Exception):
    status: int
    code: str
    message: str
    details: dict[str, Any] | None = None

    @classmethod
    def from_body(cls, status: int, body: dict[str, Any] | None):
        e = (body or {}).get("error") or {}
        return cls(status=status, code=e.get("code", "unknown"), message=e.get("message", ""), details=e.get("details"))
