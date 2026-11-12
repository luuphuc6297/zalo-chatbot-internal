"""Chat-derived customer facts from the personal Zalo account's local message cache: visits, phone, packages.

Contract: docs/contracts.md section 15 "Chat-derived customer facts" (15.2 invariants, 15.4 shapes, 15.6 model pass,
15.7 command line). Standard library only.

What it does
  1. Opens the zalo-agent-cli cache READ-ONLY through analyze_contacts (active_account, default_db, open_ro,
     read_threads: the same skip rules as the contact analyzer: groups, the account's own chat, system accounts ...)
     and classifies every 1:1 conversation with analyze_contacts.analyze_thread. A conversation classified family,
     staff or friend, at any confidence, is skipped and counted. Customer (any confidence) and unknown conversations
     are analyzed.
  2. Rules pass (always, no network): visit_rules.extract_visits with the analysis time --now,
     contact_facts_rules.extract_phone and extract_benefits. Phone: a "high" number from the chat wins; otherwise a
     valid number from the cache table contacts(userId, phone) for that id (source zalo_contact, high); otherwise the
     chat's "medium" number.
  3. Model pass, only when PROFILE_LLM_ENABLED is truthy (contract 15.6): scope "consented" asks the LOCAL server
     (GET /staff/chat-facts/eligible with the staff token); scope "customers" takes relationship customer at
     confidence high or medium. visit_model_pass.run_for_customer sends masked, filtered transcripts to `claude -p`
     through scripts/runner/claude_pool.py, at most PROFILE_LLM_MAX_CALLS calls in one run; the result is merged
     with merge_visits / merge_benefits (a rules value is never overwritten). --dry-run builds the transcripts and
     counts the calls; it makes none.
  4. Writes $THOMHOUSE_BOT_HOME/profiles/visits-<YYYYMMDD-HHMM>.json (file 0600, folder 0700; a folder given with
     --out-dir keeps its mode, with a warning when other users can list it) unless --dry-run, and prints counts.
     --push posts the customers to the LOCAL server (POST /staff/chat-facts/import, batches of 100).

Nothing printed carries a message text, a display name, a phone number, a thread id or a Zalo user id. An exception
that reaches the top prints its type name only.

Usage (from the project root):
  python3 -I scripts/analyze_visits.py                          # analyze, write the JSON, print counts
  python3 -I scripts/analyze_visits.py --dry-run                # analyze and print counts, write nothing
  python3 -I scripts/analyze_visits.py --push                   # also import into the local server
  python3 -I scripts/analyze_visits.py --now "2026-10-25 12:00" --db /path/zalo.db --owner-id 123

Environment: PROFILE_LLM_ENABLED (default false), PROFILE_LLM_SCOPE (consented | customers, default consented),
PROFILE_LLM_MODEL (default claude-sonnet-5-5), PROFILE_LLM_MAX_CALLS (default 40), PROFILE_LLM_TIMEOUT_S (default
180); SERVER_URL and STAFF_TOKEN from the environment or apps/server/.dev.vars (THOMHOUSE_DEV_VARS overrides);
THOMHOUSE_BOT_HOME, ZALO_CONFIG_DIR, ZALO_DATA_DIR as in analyze_contacts.py.

Exit codes: 0 done; 1 no cache, unreadable cache, push failure (also: output not writable, a rules module that
cannot be loaded, an unexpected error); 2 bad arguments or bad PROFILE_LLM_* values.

Choices where the contract is silent (the most conservative reading)
  - A conversation whose analysis raises is left out of "customers" (counted as skipped analysis_error), so a push
    never replaces that customer's facts with an empty list.
  - PROFILE_LLM_SCOPE is checked on every run; PROFILE_LLM_MODEL, _MAX_CALLS and _TIMEOUT_S only when the model pass
    is on. A model id must look like one (it becomes an argument of `claude`).
  - The push prerequisites (a local http(s) URL, a STAFF_TOKEN) are checked before anything is read, so a push that
    cannot happen also writes nothing. A failed push after the file is written exits 1 and keeps the file.
  - HTTP calls go to the local server without proxies and without following redirects (the token is never sent on).
  - Scope consented: every analyzed conversation the server lists is eligible (customer or unknown); family, staff
    and friend conversations are never analyzed, so never sent.
  - A model visit dated after the analysis date is ignored (the rules list bookings after it as "upcoming"); it is
    counted with the model's dropped items. After "no_account" no further conversation is sent.
  - The catalog file that cannot be read gives a warning and an empty catalog (no services, no list prices).
  - The display names of a conversation (the thread name and the contact's sender names) are passed to the model
    pass only to be masked there (visit_model_pass names=); they are never sent, printed or stored.
  - STAFF_TOKEN is removed from the environment while the model pass runs: claude_pool copies the environment into
    the `claude` process, which has no use for it. It is restored afterwards.
  - The cache is opened with analyze_contacts.open_ro, except a WAL cache that no process has open (no -wal and no
    -shm file next to it), which is opened read-only and immutable so SQLite creates no side file in the cache folder
    (and the cache can be read from a folder this user cannot write). With a -wal file present a writer may be live:
    the plain read-only open is used, and SQLite then updates the -shm file, as any reader of a live WAL database.
  - The relationship rules (analyze_contacts.analyze_thread) read the first 4 000 characters of each message: they
    slow down with the square of a message's length, and one very long message must not stall the run.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import re
import sqlite3
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import analyze_contacts as ac  # noqa: E402  (sibling module; python3 -I does not put this folder on sys.path)

# The pass modules are loaded defensively: main() reports a module that cannot be loaded (by its type name only).
_LOAD_ERRORS: dict[str, str] = {}
try:
    import visit_rules as vr  # noqa: E402
except Exception as _e:  # noqa: BLE001
    vr = None
    _LOAD_ERRORS["visit_rules"] = type(_e).__name__
try:
    import contact_facts_rules as cfr  # noqa: E402
except Exception as _e:  # noqa: BLE001
    cfr = None
    _LOAD_ERRORS["contact_facts_rules"] = type(_e).__name__
try:
    import visit_model_pass as vmp  # noqa: E402
except Exception as _e:  # noqa: BLE001
    vmp = None
    _LOAD_ERRORS["visit_model_pass"] = type(_e).__name__

ANALYZER_VERSION = "visits-rules-v1"
STAFF_ID = "chat-analyzer"
DEFAULT_SERVER = "http://127.0.0.1:8787"
PUSH_BATCH = 100
HTTP_TIMEOUT_S = 60
MAX_ANSWER_BYTES = 8 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4_000          # a message is read up to this length by the relationship rules
SKIP_RELATIONSHIPS = ("family", "staff", "friend")
SCOPES = ("consented", "customers")
SCOPE_CUSTOMER_CONFIDENCE = ("high", "medium")
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_CALLS = 40
DEFAULT_TIMEOUT_S = 180
REASONS = ("ok", "not_in_scope", "no_candidate_window", "call_cap", "no_account", "error")
PUSH_COUNTERS = ("customers", "visits_imported", "visits_updated", "visits_removed", "visits_kept_staff",
                 "phones_set", "benefits_upserted", "unmatched")
ERROR_CODE_RE = re.compile(r"[a-z_]{1,40}")
MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,99}")
TOKEN_RE = re.compile(r"[\x21-\x7e]{1,4096}")          # printable ASCII, no space: safe in a header
INT_RE = re.compile(r"-?[0-9]{1,9}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
NOW_FORMAT = "%Y-%m-%d %H:%M"


def _err(text: str) -> None:
    print(f"analyze_visits: {text}", file=sys.stderr)


# ---------------------------------------------------------------- settings


@dataclass(frozen=True)
class ModelSettings:
    enabled: bool
    scope: str
    model: str
    max_calls: int
    timeout_s: int


def _int_env(raw: str | None, default: int) -> int | None:
    s = (raw or "").strip()
    if not s:
        return default
    return int(s) if INT_RE.fullmatch(s) else None


def model_settings(env: Mapping[str, str]) -> ModelSettings | str:
    """The PROFILE_LLM_* settings, or the text of the problem (exit 2). The values are never echoed."""
    scope = (env.get("PROFILE_LLM_SCOPE") or "").strip().lower() or "consented"
    if scope not in SCOPES:
        return "PROFILE_LLM_SCOPE must be consented or customers"
    enabled = ac.truthy(env.get("PROFILE_LLM_ENABLED"))
    model = (env.get("PROFILE_LLM_MODEL") or "").strip() or DEFAULT_MODEL
    max_calls = _int_env(env.get("PROFILE_LLM_MAX_CALLS"), DEFAULT_MAX_CALLS)
    timeout_s = _int_env(env.get("PROFILE_LLM_TIMEOUT_S"), DEFAULT_TIMEOUT_S)
    if enabled:
        if not MODEL_ID_RE.fullmatch(model):
            return "PROFILE_LLM_MODEL must be a model id (letters, digits and . _ - : [ ] only)"
        if max_calls is None or max_calls < 0:
            return "PROFILE_LLM_MAX_CALLS must be a whole number, 0 or more"
        if timeout_s is None or timeout_s < 1:
            return "PROFILE_LLM_TIMEOUT_S must be a whole number of seconds, 1 or more"
    return ModelSettings(enabled, scope, model, max_calls if max_calls is not None and max_calls >= 0
                         else DEFAULT_MAX_CALLS, timeout_s if timeout_s is not None and timeout_s >= 1
                         else DEFAULT_TIMEOUT_S)


def parse_now(s: str | None) -> datetime | None:
    """The analysis time: --now "YYYY-MM-DD HH:MM" (local) or the clock; None when --now cannot be read."""
    if s is None:
        return datetime.now(ac.TZ_VN)
    try:
        return datetime.strptime(s.strip(), NOW_FORMAT).replace(tzinfo=ac.TZ_VN)
    except ValueError:
        return None


def since_ok(s: str | None) -> bool:
    if s is None:
        return True
    if not DATE_RE.fullmatch(s.strip()):
        return False
    try:
        datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        return False
    return True


def local_http(url: str) -> bool:
    """An http(s) URL on a local host (analyze_contacts.is_local_url)."""
    try:
        scheme = urllib.parse.urlsplit(url).scheme.lower()
    except ValueError:
        return False
    return scheme in ("http", "https") and ac.is_local_url(url)


# ---------------------------------------------------------------- cache and catalog


def contact_phones(con: sqlite3.Connection, ids: set[str]) -> dict[str, str]:
    """userId -> normalised phone from the cache table contacts(userId, phone); {} when the table is missing."""
    try:
        rows = con.execute("SELECT userId, phone FROM contacts").fetchall()
    except sqlite3.Error:
        return {}
    out: dict[str, str] = {}
    for uid, phone in rows:
        uid = str(uid or "")
        if uid not in ids or isinstance(phone, bool) or not isinstance(phone, (str, int)):
            continue
        value = cfr.normalize_phone(str(phone))
        if value:
            out[uid] = value
    return out


def _wal_header(db: Path) -> bool:
    """True when the SQLite header says WAL mode (bytes 18 and 19 are 2)."""
    try:
        with open(db, "rb") as f:
            head = f.read(100)
    except OSError:
        return False
    return len(head) == 100 and head[:16] == b"SQLite format 3\x00" and head[18] == 2 and head[19] == 2


def open_cache(db: Path) -> sqlite3.Connection:
    """The cache, read-only (analyze_contacts.open_ro). A WAL cache that no process has open (no -wal and no -shm
    file next to it) is opened with immutable=1 as well, so SQLite creates no -wal / -shm file in the cache folder and
    the cache can be read from a folder this user cannot write. With a -wal file present a writer may be live, and
    the plain read-only open is used (SQLite then needs the -shm file)."""
    side = [db.with_name(db.name + s) for s in ("-wal", "-shm")]
    if _wal_header(db) and not any(p.exists() for p in side):
        uri = "file:" + urllib.parse.quote(str(db.resolve())) + "?mode=ro&immutable=1"
        con = sqlite3.connect(uri, uri=True)
        con.execute("PRAGMA query_only = ON")
        return con
    return ac.open_ro(db)


def load_catalog(path: Path) -> tuple[Any, dict, bool]:
    """(analyze_contacts.Catalog, visit_rules prices, readable). An unreadable file gives an empty catalog."""
    ok = True
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        ok = isinstance(doc, dict) and isinstance(doc.get("services"), list)
    except (OSError, ValueError):
        ok = False
    try:
        catalog = ac.load_catalog(path)
    except Exception:  # noqa: BLE001 - a malformed catalog: no services rather than a crash
        catalog, ok = ac.Catalog(None, {}), False
    try:
        prices = vr.load_prices(path) if ok else {}
    except Exception:  # noqa: BLE001
        prices = {}
    return catalog, prices, ok


def choose_phone(chat: dict | None, table: str | None) -> dict | None:
    if chat and chat.get("confidence") == "high":
        return chat
    if table:
        return {"value": table, "confidence": "high", "source": "zalo_contact", "at": None}
    return chat


# ---------------------------------------------------------------- output


def write_output(doc: dict[str, Any], out_dir: Path, now: datetime, private_dir: bool = False) -> Path:
    """The JSON with mode 0600 (analyze_contacts.write_output rules, file name visits-<YYYYMMDD-HHMM>.json)."""
    created = not out_dir.exists()
    out_dir.mkdir(parents=True, exist_ok=True)
    if created or private_dir:
        try:
            os.chmod(out_dir, 0o700)
        except OSError as e:
            _err(f"warning: cannot set the output folder to mode 700 ({type(e).__name__})")
    else:
        try:
            if stat.S_IMODE(out_dir.stat().st_mode) & 0o077:
                _err("warning: other users of this Mac can list the output folder; the file itself is written "
                     "with mode 600")
        except OSError:
            pass
    path = out_dir / f"visits-{now.strftime('%Y%m%d-%H%M')}.json"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return path


# ---------------------------------------------------------------- local server


class PushFailed(Exception):
    """A push that did not go through. The text holds the HTTP status and the error code only."""

    def __init__(self, text: str, status: int | None = None):
        super().__init__(text)
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102, PLR0913
        return None                     # a 3xx answer becomes an HTTPError: the token never follows a redirect


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Staff-Id": STAFF_ID, "Accept": "application/json"}


def _error_code(e: urllib.error.HTTPError) -> str:
    """The server's error.code when it is a plain code (a-z and _), else ""; never its message or details."""
    try:
        raw = e.read(MAX_ERROR_BYTES)
        body = json.loads(raw.decode("utf-8") or "{}")
        err = body.get("error") if isinstance(body, dict) else None
        code = err.get("code") if isinstance(err, dict) else None
        return code if isinstance(code, str) and ERROR_CODE_RE.fullmatch(code) else ""
    except Exception:  # noqa: BLE001
        return ""
    finally:
        e.close()


def fetch_eligible(server_url: str, token: str) -> tuple[set[str] | None, str]:
    """GET /staff/chat-facts/eligible -> ({"p:..."}, "") or (None, a counts-only description of the problem)."""
    req = urllib.request.Request(server_url.rstrip("/") + "/staff/chat-facts/eligible", method="GET",
                                 headers=_headers(token))
    try:
        with _opener().open(req, timeout=HTTP_TIMEOUT_S) as resp:
            status = resp.status
            raw = resp.read(MAX_ANSWER_BYTES + 1)
    except urllib.error.HTTPError as e:
        e.close()
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        return None, f"server not reachable, {type(e).__name__}"
    if status != 200:
        return None, f"HTTP {status}"
    if len(raw) > MAX_ANSWER_BYTES:
        return None, "the answer is too large"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None, "the answer is not JSON"
    ids = doc.get("zalo_user_ids") if isinstance(doc, dict) else None
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return None, "the answer does not have the expected shape"
    return set(ids), ""


def _count(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return max(0, v)
    if isinstance(v, list):
        return len(v)
    return 0


def _post(opener: urllib.request.OpenerDirector, url: str, token: str, body: bytes) -> dict[str, Any]:
    headers = _headers(token)
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with opener.open(req, timeout=HTTP_TIMEOUT_S) as resp:
            raw = resp.read(MAX_ANSWER_BYTES + 1)
    except urllib.error.HTTPError as e:
        status = e.code
        code = _error_code(e)
        if status == 404:
            raise PushFailed("push failed: the local server does not have the chat-facts import endpoint yet "
                             "(HTTP 404)", 404) from None
        hint = " (the server did not accept STAFF_TOKEN)" if status in (401, 403) else ""
        raise PushFailed(f"push failed: HTTP {status} {code}".rstrip() + hint, status) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise PushFailed(f"push failed: server not reachable ({type(e).__name__})") from None
    if len(raw) > MAX_ANSWER_BYTES:
        raise PushFailed("push failed: the server's answer is too large")
    try:
        res = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise PushFailed("push failed: the server's answer was not JSON") from None
    if not isinstance(res, dict):
        raise PushFailed("push failed: the server's answer did not have the expected shape")
    return res


def push(customers: list[dict[str, Any]], generated_at: int, server_url: str, token: str) -> dict[str, int]:
    """POST /staff/chat-facts/import in batches of 100 customers; the answer counters are summed. Raises
    PushFailed (status and error code only) at the first batch that fails."""
    opener = _opener()
    url = server_url.rstrip("/") + "/staff/chat-facts/import"
    totals = {k: 0 for k in PUSH_COUNTERS}
    parts = (len(customers) + PUSH_BATCH - 1) // PUSH_BATCH
    for part, start in enumerate(range(0, len(customers), PUSH_BATCH), 1):
        body = json.dumps({"analyzer_version": ANALYZER_VERSION, "generated_at": generated_at, "dry_run": False,
                           "customers": customers[start:start + PUSH_BATCH]}, ensure_ascii=False).encode("utf-8")
        try:
            res = _post(opener, url, token, body)
        except PushFailed as e:
            where = f"; part {part} of {parts} failed, {start} customers were sent before it" if parts > 1 else ""
            raise PushFailed(str(e) + where, e.status) from None
        for k in PUSH_COUNTERS:
            totals[k] += _count(res.get(k))
    return totals


# ---------------------------------------------------------------- analysis


@dataclass
class _Conv:
    tid: str
    rel: str
    conf: str
    chat: list
    anchor_ts: list[int]
    entry: dict[str, Any]
    dropped: dict[str, int] = field(default_factory=dict)
    names: list[str] = field(default_factory=list)     # display names, only for masking in the model pass


def analyze(threads: dict, names: dict, catalog: Any, prices: dict, now_ms: int, table_phones: dict[str, str],
            skipped: Counter) -> list[_Conv]:
    """Rules pass over every conversation that is not family, staff or friend."""
    out: list[_Conv] = []
    for tid in sorted(threads):
        ms = threads[tid]
        try:
            # the relationship rules slow down with the square of a message's length: they read the first
            # MAX_TEXT_CHARS characters of each message (the visit and facts rules cut the text the same way)
            short = [m if len(m.text or "") <= MAX_TEXT_CHARS else
                     ac.Msg(m.sender, m.name, m.text[:MAX_TEXT_CHARS], m.ts, m.type) for m in ms]
            profile = ac.analyze_thread(tid, names.get(tid), short, catalog).profile
            rel = str(profile.get("relationship") or "unknown")
            conf = str(profile.get("relationship_confidence") or "low")
            if rel in SKIP_RELATIONSHIPS:
                skipped[rel] += 1
                continue
            chat = [vr.ChatMsg(int(m.ts or 0), m.sender != tid, m.text if isinstance(m.text, str) else "",
                               str(m.type or "")) for m in ms]
            found = vr.extract_visits(chat, catalog, now_ms, prices)
            phone = choose_phone(cfr.extract_phone(chat), table_phones.get(tid))
            benefits = cfr.extract_benefits(chat, catalog)
        except Exception:  # noqa: BLE001 - leave the conversation out; its data never reaches the output
            skipped["analysis_error"] += 1
            continue
        stamps = [m.ts for m in chat]
        entry = {
            "zalo_user_id": f"p:{tid}",
            "relationship": rel, "relationship_confidence": conf,
            "messages": len(chat), "first_at": min(stamps) if stamps else None,
            "last_at": max(stamps) if stamps else None,
            "visits": list(found.get("visits") or []), "upcoming": list(found.get("upcoming") or []),
            "phone": phone, "benefits": list(benefits or []),
            "model_pass": {"ran": False, "reason": "disabled"},
        }
        dropped = found.get("dropped") or {}
        display = [n for n in [names.get(tid)] + [m.name for m in ms if m.sender == tid]
                   if isinstance(n, str) and n.strip()]
        out.append(_Conv(tid, rel, conf, chat, list(found.get("anchor_ts") or []), entry,
                         {"cancelled": int(dropped.get("cancelled") or 0),
                          "no_show": int(dropped.get("no_show") or 0)},
                         sorted(set(display))))
    return out


@dataclass
class ModelRun:
    reasons: Counter = field(default_factory=Counter)
    customers_sent: int = 0
    calls: int = 0
    would_customers: int = 0
    would_calls: int = 0
    items_dropped: int = 0
    fields_dropped: int = 0
    unavailable: bool = False


def _empty_result(reason: str) -> dict[str, Any]:
    return {"reason": reason, "calls": 0, "would_call": 0, "visits": [], "packages": [],
            "dropped": {"items": 0, "fields": 0}}


def model_pass(convs: list[_Conv], eligible: set[str], settings: ModelSettings, catalog: Any, today: str,
               dry_run: bool) -> ModelRun:
    """Contract 15.6 for every conversation; fills entry["model_pass"] and merges the validated facts."""
    run = ModelRun()
    calls_left = settings.max_calls
    stop: str | None = None
    for c in convs:
        if c.tid not in eligible:
            c.entry["model_pass"] = {"ran": False, "reason": "not_in_scope"}
            run.reasons["not_in_scope"] += 1
            continue
        if stop is not None:
            c.entry["model_pass"] = {"ran": False, "reason": stop}
            run.reasons[stop] += 1
            continue
        try:
            anchors = sorted(set(c.anchor_ts) | set(cfr.anchor_timestamps(c.chat)))
            res = vmp.run_for_customer(c.chat, anchors, catalog, model=settings.model, timeout_s=settings.timeout_s,
                                       calls_left=calls_left, dry_run=dry_run, names=c.names)
            if not isinstance(res, dict):
                res = _empty_result("error")
        except Exception:  # noqa: BLE001 - reported as "error"; the rules result stays
            res = _empty_result("error")
        reason = res.get("reason") if res.get("reason") in REASONS else "error"
        calls = _count(res.get("calls"))
        run.calls += calls
        calls_left -= calls
        if calls:
            run.customers_sent += 1
        if dry_run and reason == "ok":
            would = _count(res.get("would_call"))
            calls_left -= would
            run.would_calls += would
            run.would_customers += 1 if would else 0
        if not dry_run and reason in ("ok", "error"):
            visits = [v for v in (res.get("visits") or []) if isinstance(v, dict)]
            current = [v for v in visits if isinstance(v.get("date"), str) and v["date"] <= today]
            run.items_dropped += len(visits) - len(current)
            try:
                if current:
                    c.entry["visits"] = vmp.merge_visits(c.entry["visits"], current)
                packages = [p for p in (res.get("packages") or []) if isinstance(p, dict)]
                if packages:
                    c.entry["benefits"] = vmp.merge_benefits(c.entry["benefits"], packages)
            except Exception:  # noqa: BLE001 - keep the rules result
                reason = "error"
        dropped = res.get("dropped") if isinstance(res.get("dropped"), dict) else {}
        run.items_dropped += _count(dropped.get("items"))
        run.fields_dropped += _count(dropped.get("fields"))
        c.entry["model_pass"] = {"ran": calls > 0, "reason": reason}
        run.reasons[reason] += 1
        if reason == "no_account":
            stop = "no_account"
    return run


# Variables the `claude` child process never needs: removed from the environment while the model pass runs
# (scripts/runner/claude_pool.py copies os.environ into the child).
CHILD_ENV_DROP = ("STAFF_TOKEN",)


@contextlib.contextmanager
def without_env(names: tuple[str, ...]):
    saved = {k: os.environ.pop(k) for k in names if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def eligible_ids(convs: list[_Conv], settings: ModelSettings, server_override: str | None) -> set[str]:
    if settings.scope == "customers":
        return {c.tid for c in convs if c.rel == "customer" and c.conf in SCOPE_CUSTOMER_CONFIDENCE}
    server = server_override or ac.dev_var("SERVER_URL") or DEFAULT_SERVER
    token = ac.dev_var("STAFF_TOKEN")
    ids: set[str] | None = None
    if not local_http(server):
        problem = "the server URL is not a local http(s) URL"
    elif not token:
        problem = "STAFF_TOKEN not found"
    elif not TOKEN_RE.fullmatch(token):
        problem = "STAFF_TOKEN cannot be sent in a header"
    else:
        ids, problem = fetch_eligible(server, token)
    if ids is None:
        _err(f"model pass skipped for every conversation: the consent list could not be read from the local server "
             f"({problem}); the rules results are kept")
        return set()
    return {x[2:] for x in ids if x.startswith("p:")}


# ---------------------------------------------------------------- counts


def counts_lines(convs: list[_Conv], skipped: dict[str, int], settings: ModelSettings, run: ModelRun | None,
                 dry_run: bool) -> list[str]:
    entries = [c.entry for c in convs]
    visits = [v for e in entries for v in e["visits"]]
    conf = Counter(v.get("confidence") for v in visits)
    upcoming = sum(len(e["upcoming"]) for e in entries)
    dropped = sum(c.dropped.get("cancelled", 0) + c.dropped.get("no_show", 0) for c in convs)
    with_visit = sum(1 for e in entries if any(v.get("confidence") in ("high", "medium") for v in e["visits"]))
    phones = Counter(e["phone"].get("confidence") for e in entries if e["phone"])
    skip_txt = ", ".join(f"{k} {v}" for k, v in skipped.items())
    lines = [
        f"customer conversations analyzed: {len(entries)}" + (f" (skipped: {skip_txt})" if skip_txt else ""),
        f"  visits found: {len(visits)} (high {conf['high']}, medium {conf['medium']}, low {conf['low']}); "
        f"upcoming bookings: {upcoming}; cancelled or no-show: {dropped}",
        f"  customers with at least one visit (high or medium): {with_visit}",
        f"  visits with a service: {sum(1 for v in visits if v.get('services'))}; "
        f"with a time: {sum(1 for v in visits if v.get('time') is not None)}; "
        f"with an amount: {sum(1 for v in visits if v.get('amount_vnd') is not None)}; "
        f"with a technician: {sum(1 for v in visits if v.get('technician'))}",
        f"  phone numbers found: {sum(phones.values())} (high {phones['high']}, medium {phones['medium']})",
        f"  packages or vouchers found: {sum(len(e['benefits']) for e in entries)}",
    ]
    if not settings.enabled or run is None:
        lines.append("  model pass: off")
    elif run.unavailable:
        lines.append(f"  model pass: unavailable, scope {settings.scope}: scripts/visit_model_pass.py could not be "
                     "loaded; no call made")
    else:
        rs = ", ".join(f"{r} {run.reasons[r]}" for r in REASONS if run.reasons.get(r))
        rs = f" ({rs})" if rs else ""
        if dry_run:
            lines.append(f"  model pass: dry run, scope {settings.scope}: customers that would be sent "
                         f"{run.would_customers}, calls that would be made {run.would_calls}{rs}; no call made")
        else:
            lines.append(f"  model pass: on, scope {settings.scope}: customers sent {run.customers_sent}, calls "
                         f"{run.calls}{rs}; model items dropped {run.items_dropped}, "
                         f"fields dropped {run.fields_dropped}")
    return lines


# ---------------------------------------------------------------- main


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="analyze_visits.py",
                                 description="Visits, phone and packages of every customer conversation in the local "
                                             "zalo.db (rules; optional model pass). Prints counts only.")
    ap.add_argument("--db", help="path to zalo.db (default: the active account under ~/.zalo-agent-cli)")
    ap.add_argument("--owner-id", help="the account's ownId (default: from accounts.json or the db folder)")
    ap.add_argument("--since", help="only messages from this local date on (YYYY-MM-DD)")
    ap.add_argument("--catalog", default=str(ac.ROOT / "data/services.json"),
                    help="catalog JSON (default data/services.json)")
    ap.add_argument("--out-dir", help="output folder (default $THOMHOUSE_BOT_HOME/profiles)")
    ap.add_argument("--push", action="store_true", help="import the customers into the local server")
    ap.add_argument("--server-url", help="local server (default SERVER_URL or http://127.0.0.1:8787)")
    ap.add_argument("--dry-run", action="store_true",
                    help="analyze and print counts; write nothing, push nothing, make no model call")
    ap.add_argument("--now", help='the analysis time, local "YYYY-MM-DD HH:MM" (default: now); decides "upcoming"')
    return ap


def _run(argv: list[str] | None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:                     # argparse: --help (0) or a bad argument (2)
        return e.code if isinstance(e.code, int) else 2
    now_dt = parse_now(args.now)
    if now_dt is None:
        _err('--now must be "YYYY-MM-DD HH:MM" (local time)')
        return 2
    if not since_ok(args.since):
        _err("--since must be YYYY-MM-DD")
        return 2
    settings = model_settings(os.environ)
    if isinstance(settings, str):
        _err(settings)
        return 2
    for name in ("visit_rules", "contact_facts_rules"):
        if name in _LOAD_ERRORS:
            _err(f"scripts/{name}.py could not be loaded ({_LOAD_ERRORS[name]})")
            return 1

    server, token = "", ""
    if args.push and not args.dry_run:
        server = args.server_url or ac.dev_var("SERVER_URL") or DEFAULT_SERVER
        if not local_http(server):
            _err("refusing to push to a non-local server (http or https on localhost, 127.0.0.1, ::1, *.localhost "
                 "or *.test only); nothing was analyzed")
            return 1
        token = ac.dev_var("STAFF_TOKEN")
        if not token:
            _err("STAFF_TOKEN not found (environment or apps/server/.dev.vars); nothing was analyzed")
            return 1
        if not TOKEN_RE.fullmatch(token):
            _err("STAFF_TOKEN has characters that cannot be sent in a header; nothing was analyzed")
            return 1

    owner_id = args.owner_id or None
    if args.db:
        db = Path(os.path.expanduser(args.db))
        if not owner_id and db.parent.name.isdigit():
            owner_id = db.parent.name
    else:
        owner_id = owner_id or ac.active_account()
        db = ac.default_db(owner_id)
        if db is None:
            _err("no active zalo-agent account found; pass --db and --owner-id")
            return 1
    if not db.is_file():
        _err("zalo.db not found at the given or default path")
        return 1
    try:
        con = open_cache(db)
        try:
            names, threads, cache_skipped = ac.read_threads(con, owner_id, ac.parse_since(args.since))
            table_phones = contact_phones(con, set(threads))
        finally:
            con.close()
    except sqlite3.Error as e:
        _err(f"cannot read zalo.db read-only ({type(e).__name__}); is it a zalo-agent-cli cache?")
        return 1

    catalog, prices, catalog_ok = load_catalog(Path(os.path.expanduser(args.catalog)))
    if not catalog_ok:
        _err("warning: the catalog file could not be read; visits are listed without services or list prices")

    now_ms = int(now_dt.timestamp() * 1000)
    rel_skipped: Counter = Counter()
    convs = analyze(threads, names, catalog, prices, now_ms, table_phones, rel_skipped)
    skipped: dict[str, int] = {}
    for k in SKIP_RELATIONSHIPS:
        if rel_skipped[k]:
            skipped[k] = rel_skipped[k]
    for k in sorted(cache_skipped):
        if cache_skipped[k]:
            skipped[k] = int(cache_skipped[k])
    if rel_skipped["analysis_error"]:
        skipped["analysis_error"] = rel_skipped["analysis_error"]

    run: ModelRun | None = None
    if settings.enabled:
        if vmp is None:
            run = ModelRun(unavailable=True)
            for c in convs:
                c.entry["model_pass"] = {"ran": False, "reason": "error"}
        else:
            eligible = eligible_ids(convs, settings, args.server_url)
            with without_env(CHILD_ENV_DROP):
                run = model_pass(convs, eligible, settings, catalog, now_dt.date().isoformat(), args.dry_run)

    for line in counts_lines(convs, skipped, settings, run, args.dry_run):
        print(line)
    if args.dry_run:
        print("dry run: nothing written, nothing pushed")
        return 0

    generated_at = int(time.time() * 1000)
    customers = [c.entry for c in convs]
    doc = {"analyzer_version": ANALYZER_VERSION, "generated_at": generated_at, "since": args.since,
           "owner_id": owner_id, "contacts": len(customers), "skipped": skipped,
           "model": {"enabled": settings.enabled, "scope": settings.scope if settings.enabled else None,
                     "customers_sent": run.customers_sent if run else 0, "calls": run.calls if run else 0},
           "customers": customers}
    try:
        if args.out_dir:
            out = write_output(doc, Path(os.path.expanduser(args.out_dir)), datetime.now(ac.TZ_VN))
        else:
            out = write_output(doc, ac.bot_home() / "profiles", datetime.now(ac.TZ_VN), private_dir=True)
    except OSError as e:
        _err(f"cannot write the output file ({type(e).__name__})")
        return 1
    print(f"written: {out} (mode 600)")

    if args.push:
        try:
            totals = push(customers, generated_at, server, token)
        except PushFailed as e:
            _err(f"{e}; the file is written, nothing more was imported")
            return 1
        print("pushed: " + ", ".join(f"{k} {totals[k]}" for k in PUSH_COUNTERS))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt:
        _err("interrupted")
        return 1
    except Exception as e:  # noqa: BLE001 - the message could carry data: the type name only
        _err(f"unexpected error ({type(e).__name__})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
