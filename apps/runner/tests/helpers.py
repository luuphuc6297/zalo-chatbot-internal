"""Test fixtures: a stub backend (http.server), a temp THOMHOUSE_BOT_HOME with a two-account pool, and the fake
`claude` executable in tests/fake_bin put first on PATH. RoomsTestCase adds the fake rooms platform CLI
(tests/fake_bin/openmausbot) with its own data folder."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from runner.config import Config, DEFAULT_POOL
from runner.prompt import shipped_tools

FAKE_BIN = Path(__file__).resolve().parent / "fake_bin"
TOKEN = "test-runner-token"
RUNNER_ID = "test-runner"
# A synthetic CustomerFacts answer of get_customer_profile (docs/contracts.md 14.6).
PROFILE_RESULT = {
    "found": True, "role": "customer", "address_term": "chị", "name_to_use": "Lan", "has_phone": True,
    "status": "returning", "visits_total": 7,
    "last_visit": {"date": "2026-10-30", "services": ["Gội đầu dưỡng sinh"], "staff": "Kỹ thuật viên thử"},
    "days_since_last_visit": 13, "usual_gap_days": 21, "gap_basis": "own", "absent_after_days": 42,
    "window": {"days": 183, "visits": 3, "spend_vnd": 1350000, "avg_spend_vnd": 450000,
               "usual_services": [{"name": "Gội đầu dưỡng sinh", "count": 3}], "other_services": 0},
    "unused_benefits": [], "services_mentioned": [],
}


class StubBackend:
    def __init__(self):
        self.jobs: list[dict] = []
        self.requests: list[dict] = []
        self.heartbeat_response: dict = {"lease_until": 0, "stale": False, "cancel": False}
        self.heartbeat_status = 200
        self.desired_account = "auto"
        self.prompt_hash = "h1"
        self.cli_system_prompt: str | None = None       # None = "BOT SYSTEM PROMPT <hash>"
        # two-bot rooms (docs/contracts.md 14.7): rows per conversation id for the three kinds of feed
        self.rooms_enabled = True
        self.rooms_status = 200                         # another status: the feed answers that error
        self.feed_pending: dict[str, list[dict]] = {}
        self.feed_seed: dict[str, list[dict]] = {}
        self.feed_observe: dict[str, list[dict]] = {}
        # conversation ids the server finds not eligible for a room: their draft-turn feed has no entry
        self.feed_ineligible: set[str] = set()
        self.profile_result: dict = dict(PROFILE_RESULT)
        self.lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status: int, body: dict):
                raw = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self, method: str):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else None
                with stub.lock:
                    stub.requests.append({"method": method, "path": self.path, "body": body,
                                          "auth": self.headers.get("Authorization"),
                                          "runner_id": self.headers.get("X-Runner-Id")})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"error": {"code": "unauthorized", "message": "bad token"}})
                status, out = stub.route(method, self.path, body)
                self._send(status, out)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def route(self, method: str, path: str, body):
        if path == "/runner/jobs/claim":
            with self.lock:
                job = self.jobs.pop(0) if self.jobs else None
            return 200, ({"job": job, "poll_after_ms": 0} if job else
                         {"job": None, "poll_after_ms": 20, "reason": "no_work"})
        if path == "/runner/prompt":
            return 200, {"catalog_version": "cv1", "prompt_hash": self.prompt_hash, "blocks": {"a": "", "b": "", "c": ""},
                         "cli_system_prompt": self.cli_system_prompt or "BOT SYSTEM PROMPT " + self.prompt_hash,
                         "tools": [{"name": t["name"], "description": t["description"],
                                    "input_schema": t["input_schema"], "strict": True} for t in shipped_tools()]}
        if m := re.fullmatch(r"/runner/jobs/([^/]+)/heartbeat", path):
            return self.heartbeat_status, self.heartbeat_response
        if re.fullmatch(r"/runner/jobs/([^/]+)/draft", path):
            return 200, {"draft_id": "drf_1", "status": "pending", "action": "queued_for_staff",
                         "checker": {"passed": True, "issues": [], "checked_at": 1}, "message_id": None}
        if re.fullmatch(r"/runner/jobs/([^/]+)/fail", path):
            return 200, {"job_status": "failed", "handoff_id": "hof_1"}
        if path == "/runner/rooms/feed":
            if self.rooms_status != 200:
                return self.rooms_status, {"error": {"code": "internal", "message": "feed failed"}}
            if not self.rooms_enabled:
                return 200, {"enabled": False, "conversations": []}
            cid, seed = (body or {}).get("conversation_id"), bool((body or {}).get("seed"))
            with self.lock:
                # As the server: one conversation answers one entry, also without rows, unless it is not
                # eligible; the observation list names only conversations that have rows.
                if cid:
                    feeds = {} if cid in self.feed_ineligible else {
                        cid: (self.feed_seed if seed else self.feed_pending).get(cid) or []}
                else:
                    feeds = {c: rows for c, rows in self.feed_observe.items() if rows}
                convs = [{"conversation_id": c, "customer_display_name": "Khách thử", "messages": list(rows)}
                         for c, rows in feeds.items()]
            return 200, {"enabled": True, "conversations": convs}
        if path == "/runner/rooms/ack":
            cid, ids = (body or {}).get("conversation_id"), set((body or {}).get("message_ids") or [])
            marked = 0
            with self.lock:
                for feed in (self.feed_pending, self.feed_observe):
                    rows = feed.get(cid) or []
                    keep = [r for r in rows if r["message_id"] not in ids]
                    marked += len(rows) - len(keep)
                    if cid in feed:
                        feed[cid] = keep
            return 200, {"ok": True, "marked": marked}
        if m := re.fullmatch(r"/runner/tools/([a-z_]+)", path):
            if m.group(1) == "get_customer_profile":
                return 200, {"result": self.profile_result, "is_error": False, "tool_call_id": "tcl_3",
                             "replayed": False}
            if m.group(1) == "quote_price":
                return 200, {"result": {"status": "ok", "price_vnd": 199000, "price_text": "199.000đ"},
                             "is_error": False, "tool_call_id": "tcl_1", "replayed": False}
            return 200, {"result": {"services": []}, "is_error": False, "tool_call_id": "tcl_2", "replayed": False}
        if path == "/runner/status":
            return 200, {"ok": True, "desired_account": self.desired_account,
                         "flags": {"ai_calls_enabled": True, "ai_engine": "subscription",
                                   "auto_reply_mode": "approve_each"}}
        return 404, {"error": {"code": "not_found", "message": path}}

    def find(self, suffix: str, method: str = "POST") -> list[dict]:
        with self.lock:
            return [r for r in self.requests if r["method"] == method and r["path"].endswith(suffix)]


def make_job(job_id="job_1", cid="cnv_abc", session_id=None, texts=("gội đầu bao nhiêu tiền ạ",), history=(),
             catalog="cv1", prompt_hash="h1", reason="new_conversation", sent=(), unsent=()):
    return {
        "job_id": job_id, "type": "draft_reply", "lease_until": 9_999_999_999_999, "attempt": 1,
        "conversation": {"conversation_id": cid, "session_id": session_id, "session_turns": 0,
                         "session_started_at": None, "session_reset_reason": None if session_id else reason,
                         "catalog_version": catalog},
        "turn_context": {}, "turn_context_text": "<turn_context>\nnow_local: 2026-11-07T19:42\n</turn_context>",
        "new_customer_messages": [{"message_id": f"msg_{i}", "text": t, "kind": "text", "attachments": [],
                                   "sent_at": 1762500000000 + i} for i, t in enumerate(texts)],
        "sent_since_last_draft": list(sent), "unsent_drafts_since_last": list(unsent),
        "history": list(history), "prompt_hash": prompt_hash,
    }


def feed_row(message_id: str, text: str, source: str = "customer", at: int = 1762500000000, kind: str = "text",
             seq: int = 1) -> dict:
    """One row of POST /runner/rooms/feed."""
    return {"message_id": message_id, "seq": seq, "source": source,
            "direction": "inbound" if source == "customer" else "outbound", "kind": kind, "text": text, "at": at}


class RunnerTestCase(unittest.TestCase):
    """Temp home with pool accounts `a` (priority 1) and `b` (priority 2), fake claude on PATH, stub backend."""

    accounts = ("a", "b")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thom-runner-test-"))
        self.home = self.tmp / "home"
        (self.home / "sessions").mkdir(parents=True)
        accs = []
        for i, label in enumerate(self.accounts):
            d = self.home / "accounts" / label
            d.mkdir(parents=True)
            (d / "projects").symlink_to(self.home / "sessions", target_is_directory=True)
            accs.append({"label": label, "config_dir": str(d), "priority": i + 1, "enabled": True})
        (self.home / "accounts.json").write_text(json.dumps(accs))
        self.fake_log = self.tmp / "claude-calls.jsonl"
        self.fake_cfg = self.tmp / "fake-claude.json"
        self.set_fake()
        self._env = {k: os.environ.get(k) for k in ("PATH", "FAKE_CLAUDE_CONFIG", "THOMHOUSE_BOT_HOME")}
        os.environ["PATH"] = f"{FAKE_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["FAKE_CLAUDE_CONFIG"] = str(self.fake_cfg)
        os.environ["THOMHOUSE_BOT_HOME"] = str(self.home)
        os.chmod(FAKE_BIN / "claude", 0o755)
        self.backend = StubBackend().start()

    def tearDown(self):
        self.backend.close()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_fake(self, **kw):
        cfg = {"accounts": {}, "mode": "reply", "log": str(self.fake_log), **kw}
        self.fake_cfg.write_text(json.dumps(cfg))

    def config(self, **kw) -> Config:
        base = dict(server_url=self.backend.url, runner_token=TOKEN, runner_id=RUNNER_ID, home=self.home,
                    max_concurrency=3, claude_timeout_s=15, heartbeat_s=0.2, status_every_s=3600,
                    pool_path=DEFAULT_POOL)
        base.update(kw)
        return Config(**base)

    def claude_calls(self) -> list[dict]:
        if not self.fake_log.exists():
            return []
        return [json.loads(l) for l in self.fake_log.read_text().splitlines() if l.strip()]

    def pool_state(self) -> dict:
        p = self.home / "account-state.json"
        return json.loads(p.read_text()) if p.exists() else {}


class RoomsTestCase(RunnerTestCase):
    """RunnerTestCase plus the fake rooms platform CLI: its data folder (OMB_DATA_DIR), its behaviour file and its
    call log. The fake `claude` stays on PATH for the fallback to the direct engine."""

    def setUp(self):
        super().setUp()
        self.platform_dir = self.tmp / "platform"
        self.platform_dir.mkdir()
        self.node_dir = self.tmp / "node-bin"
        self.node_dir.mkdir()
        self.platform_log = self.tmp / "platform-calls.jsonl"
        os.chmod(FAKE_BIN / "openmausbot", 0o755)
        self.set_platform()

    def set_platform(self, **kw):
        cfg = {"mode": "reply", "log": str(self.platform_log), "home": str(self.home), **kw}
        (self.platform_dir / "fake-openmausbot.json").write_text(json.dumps(cfg, ensure_ascii=False),
                                                                 encoding="utf-8")

    def rooms_config(self, **kw) -> Config:
        base = dict(draft_engine="rooms", openmausbot_bin=FAKE_BIN / "openmausbot",
                    openmausbot_data_dir=self.platform_dir, openmausbot_node_dir=str(self.node_dir),
                    room_turn_timeout_s=20, room_observe_every_s=0)
        base.update(kw)
        return self.config(**base)

    def platform_calls(self, cmd: str | None = None) -> list[dict]:
        """Logged CLI calls, optionally only those of one command (`team` = team apply)."""
        if not self.platform_log.exists():
            return []
        calls = [json.loads(l) for l in self.platform_log.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [c for c in calls if cmd is None or c["argv"][:1] == [cmd]]

    def platform_state(self) -> dict:
        p = self.platform_dir / "fake-state.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
