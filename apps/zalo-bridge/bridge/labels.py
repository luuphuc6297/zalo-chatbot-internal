"""Zalo label sync: copy the three role labels of the personal Zalo account to the server's contact roles.

Contract: docs/contracts.md 14.3 ("Label sync"). Command `python3 -m bridge.main sync-labels [--dry-run]`; `run`
repeats it at start and every LABEL_SYNC_EVERY_S seconds (poller.py).

- Source: `zalo-agent --json label list` (src/commands/label.js prints the answer of zca-js getLabels):
    {"labelData": [{"id": int, "text": str, "conversations": [str], ...}], "version": int, "lastUpdateTime": int}
  A personal conversation id is a string of digits and becomes `p:<id>`; a group id starts with "g" and is skipped.
- Label text is normalised (NFD without marks, đ to d, lower case, single spaces): "khach hang" is customer,
  "quan ly" is manager, "nhan vien" is staff. Other labels are ignored. A contact under several of the three
  labels gets the first of manager, staff, customer.
- The result goes to POST /staff/roles/import with `complete: true`, so the server deletes the label roles that are
  no longer listed. That is why nothing is posted unless the whole document was understood: an engine failure, a
  document without `labelData`, or a role label whose `conversations` is not a list of strings ends the sync with a
  non-zero status. An empty, well-formed label list IS a complete list and is posted.
- Auth is the staff API's (the same lookup as scripts/analyze_contacts.py): STAFF_TOKEN from the environment, else
  from apps/server/.dev.vars (path override: THOMHOUSE_DEV_VARS), header X-Staff-Id "label-sync". The token of the
  dev vars file is the local server's, so it is only sent to a local SERVER_URL.
- Output and logs carry counts only: never a label text, a contact id or a name.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any

from .api import ApiError, ServerUnavailable, StaffApi
from .config import REPO_ROOT, Config, read_dotenv
from .engine import run_engine
from .sender import NOT_LOGGED_IN_RE

log = logging.getLogger("bridge.labels")

ROLE_BY_LABEL = {"khach hang": "customer", "quan ly": "manager", "nhan vien": "staff"}
ROLE_PRIORITY = ("manager", "staff", "customer")     # a contact under several labels gets the first of these
MAX_ROLES = 5000                                     # limit of one POST /staff/roles/import
ENGINE_TIMEOUT_S = 45.0
STAFF_ID = "label-sync"
SERVER_COUNTS = ("imported", "updated", "unchanged", "removed", "kept_staff")
# The server's limit for a role id (`p:` + 1 to 32 digits, apps/server/src/lib/roles.ts ROLE_ID_RE): a longer id
# would make it refuse the whole list, so such an id is counted in other_ids and left out.
PERSONAL_ID_RE = re.compile(r"^[0-9]{1,32}$")
ERROR_CODE_RE = re.compile(r"^[a-z0-9_]{1,40}$")
EXIT_OK, EXIT_FAILED, EXIT_CONFIG = 0, 1, 2


class LabelSyncError(Exception):
    """`code` is a fixed word that is safe to print: it never carries engine output."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_label(text: str) -> str:
    """NFD without combining marks, đ to d, lower case, single spaces."""
    s = unicodedata.normalize("NFD", text)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().replace("đ", "d")
    return " ".join(s.split())


def roles_from_labels(doc: Any) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """(roles for the import, counts) from the engine's document. Raises LabelSyncError when it is not understood."""
    if not isinstance(doc, dict):
        raise LabelSyncError("malformed_output")
    if "labelData" not in doc:
        raise LabelSyncError("no_label_data")
    labels = doc["labelData"]
    if not isinstance(labels, list):
        raise LabelSyncError("malformed_output")
    members: dict[str, set[str]] = {role: set() for role in ROLE_PRIORITY}
    role_labels = groups = other_ids = 0
    for label in labels:
        if not isinstance(label, dict) or not isinstance(label.get("text"), str):
            raise LabelSyncError("malformed_output")
        role = ROLE_BY_LABEL.get(normalize_label(label["text"]))
        if role is None:
            continue
        role_labels += 1
        conversations = label.get("conversations")
        # Strict on purpose: with `complete: true` a half-read label would delete roles on the server.
        if not isinstance(conversations, list) or not all(isinstance(c, str) for c in conversations):
            raise LabelSyncError("malformed_output")
        for conv in conversations:
            conv = conv.strip()
            if PERSONAL_ID_RE.match(conv):
                members[role].add(conv)
            elif conv.startswith("g"):
                groups += 1
            else:
                other_ids += 1
    roles: list[dict[str, str]] = []
    contacts = {role: 0 for role in ROLE_PRIORITY}
    seen: set[str] = set()
    for role in ROLE_PRIORITY:
        for conv in sorted(members[role] - seen, key=lambda c: (len(c), c)):
            roles.append({"zalo_user_id": f"p:{conv}", "role": role})
            contacts[role] += 1
        seen |= members[role]
    counts = {"labels": len(labels), "role_labels": role_labels, "contacts": contacts,
              "skipped": {"groups": groups, "other_ids": other_ids}}
    return roles, counts


def fetch_labels(cfg: Config, timeout: float = ENGINE_TIMEOUT_S, cancel: threading.Event | None = None) -> Any:
    """The document of `zalo-agent --json label list`. Raises LabelSyncError on any engine failure."""
    res = run_engine(cfg, ["label", "list"], timeout, cancel=cancel)
    if res.missing:
        raise LabelSyncError("engine_missing")
    if res.cancelled:
        raise LabelSyncError("cancelled")
    if res.timed_out:
        raise LabelSyncError("engine_timeout")
    err = res.error_text
    if err is not None or res.returncode != 0:
        if NOT_LOGGED_IN_RE.search(err or "") or NOT_LOGGED_IN_RE.search(res.stderr or ""):
            raise LabelSyncError("not_logged_in")
        raise LabelSyncError("engine_error")
    if res.data is None:
        raise LabelSyncError("malformed_output")
    return res.data


def is_local_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost") or host.endswith(".test")


def staff_token(server_url: str, env: dict[str, str] | None = None) -> str:
    """STAFF_TOKEN from the environment, else from the local server's dev vars (only for a local server URL)."""
    env = os.environ if env is None else env
    token = (env.get("STAFF_TOKEN") or "").strip()
    if token or not is_local_url(server_url):
        return token
    path = Path(env.get("THOMHOUSE_DEV_VARS") or (REPO_ROOT / "apps" / "server" / ".dev.vars"))
    try:
        return (read_dotenv(path).get("STAFF_TOKEN") or "").strip()
    except OSError:
        return ""


def _server_counts(out: dict[str, Any]) -> dict[str, int]:
    return {k: out[k] for k in SERVER_COUNTS if isinstance(out.get(k), int) and not isinstance(out.get(k), bool)}


def sync_labels(cfg: Config, dry_run: bool = False, api: StaffApi | None = None,
                timeout: float = ENGINE_TIMEOUT_S, cancel: threading.Event | None = None) -> tuple[int, dict[str, Any]]:
    """Run one sync. Returns (exit status, summary with counts only). Never raises for an expected failure."""
    try:
        roles, summary = roles_from_labels(fetch_labels(cfg, timeout, cancel))
    except LabelSyncError as e:
        return EXIT_FAILED, {"ok": False, "error": e.code, "posted": False}
    summary = {"ok": True, "dry_run": dry_run, **summary, "posted": False}
    if dry_run:
        return EXIT_OK, summary
    if len(roles) > MAX_ROLES:
        # A partial list cannot be posted with `complete: true`: the server would delete the rest.
        return EXIT_FAILED, {**summary, "ok": False, "error": "too_many_roles"}
    if api is None:
        token = staff_token(cfg.server_url)
        if not token:
            return EXIT_CONFIG, {**summary, "ok": False, "error": "no_staff_token"}
        api = StaffApi(cfg.server_url, token, STAFF_ID)
    try:
        out = api.import_roles(roles)
    except ServerUnavailable:
        return EXIT_FAILED, {**summary, "ok": False, "error": "server_unavailable"}
    except ApiError as e:
        code = e.code if ERROR_CODE_RE.match(e.code) else "http_error"
        return EXIT_FAILED, {**summary, "ok": False, "error": code, "status": e.status}
    return EXIT_OK, {**summary, "posted": True, "server": _server_counts(out)}


def describe(summary: dict[str, Any]) -> str:
    """One log line for a summary (counts and fixed words only)."""
    if "labels" not in summary:
        return f"failed ({summary.get('error')}); nothing posted"
    c = summary["contacts"]
    head = (f"{summary['labels']} labels, {summary['role_labels']} role labels, contacts: "
            f"{c['manager']} manager, {c['staff']} staff, {c['customer']} customer")
    if not summary.get("ok"):
        return f"{head}; failed ({summary.get('error')}); nothing imported"
    if not summary.get("posted"):
        return f"{head}; dry run, nothing posted"
    return f"{head}; server: " + ", ".join(f"{k} {v}" for k, v in summary.get("server", {}).items())
