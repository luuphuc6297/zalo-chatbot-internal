"""Test fixtures: a fake backend implementing the Bridge API contract (http.server), a temp state dir, and the fake
`zalo-agent` executable in tests/fake_bin. Nothing here touches ~/.zalo-agent-cli, Zalo or the real server."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bridge.config import Config

FAKE_BIN_DIR = Path(__file__).resolve().parent / "fake_bin"
FAKE_ENGINE = FAKE_BIN_DIR / "zalo-agent"
TOKEN = "test-bridge-token"
STAFF_TOKEN = "test-staff-token"   # the staff API's token: never the bridge's
BRIDGE_ID = "test-bridge"
SECRET = "test-webhook-secret-0123456789abcdef"
THREAD = "2000000000000002"      # fake Zalo user id
LEASE_MS = 60_000
MAX_ATTEMPTS = 4                 # server: attempts < 4 are retried
IDLE_POLL_MS = 2000


class FakeBridgeServer:
    """In-memory outbox with the claim/result/status semantics of docs/contracts.md section 12 ("Personal Zalo
    channel"): 60 s lease, attempt counts claims, failed is re-queued while attempts < 4 (no backoff here), unknown
    is final, sent is accepted in any state, a failed/unknown result with a stale attempt is refused (409).

    Also POST /staff/roles/import of section 14.3 (staff token + X-Staff-Id): `label_roles` are the rows with source
    zalo_label, `staff_roles` the rows set in the console, which an import never overwrites."""

    def __init__(self):
        self.rows: list[dict] = []
        self.requests: list[dict] = []
        self.result_fail_times = 0          # answer 503 to this many result calls
        self.zalo_mode = "personal"
        self.last_claim_at: int | None = None
        self.label_roles: dict[str, str] = {}   # zalo_user_id -> role, source zalo_label
        self.staff_roles: dict[str, str] = {}   # zalo_user_id -> role, source staff
        self.roles_import_error: tuple[int, dict] | None = None   # answer this instead of importing
        self.lock = threading.Lock()
        srv = self

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
                with srv.lock:
                    srv.requests.append({"method": method, "path": self.path, "body": body,
                                         "auth": self.headers.get("Authorization"),
                                         "bridge_id": self.headers.get("X-Bridge-Id"),
                                         "staff_id": self.headers.get("X-Staff-Id"),
                                         "ua": self.headers.get("User-Agent")})
                if self.path == "/health":
                    return self._send(200, {"ok": True, "env": "dev", "zalo_mode": srv.zalo_mode})
                if self.path.startswith("/staff/"):
                    if self.headers.get("Authorization") != f"Bearer {STAFF_TOKEN}":
                        return self._send(401, {"error": {"code": "unauthorized", "message": "bad token"}})
                    status, out = srv.staff_route(method, self.path, body)
                    return self._send(status, out)
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"error": {"code": "unauthorized", "message": "bad token"}})
                if not self.headers.get("X-Bridge-Id"):
                    return self._send(400, {"error": {"code": "bad_request", "message": "missing X-Bridge-Id"}})
                status, out = srv.route(method, self.path, body, self.headers.get("X-Bridge-Id"))
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

    # ------------------------------------------------------------ test helpers

    def enqueue(self, text: str = "Dạ em chào anh/chị", thread_id: str = THREAD, kind: str = "cs_text",
                row_id: str | None = None, thread_type: int = 0, images: list | None = None) -> str:
        with self.lock:
            rid = row_id or f"obx_{len(self.rows) + 1:04d}"
            self.rows.append({"id": rid, "thread_id": thread_id, "text": text, "kind": kind, "status": "queued",
                              "attempt": 0, "lease_until": 0, "lease_owner": None, "zalo_msg_id": None,
                              "error": None, "thread_type": thread_type, "images": images, "part_msg_ids": None})
            return rid

    def enqueue_images(self, images: list, thread_id: str = THREAD, row_id: str | None = None) -> str:
        """A cs_images row (menu images); `text` is the staff-facing label, never sent."""
        return self.enqueue(text=f"[Ảnh menu, {len(images)} ảnh]", thread_id=thread_id, kind="cs_images",
                            row_id=row_id, images=images)

    def row(self, rid: str) -> dict:
        with self.lock:
            return dict(next(r for r in self.rows if r["id"] == rid))

    def requeue(self, rid: str, by_staff: bool = False) -> None:
        """Hand a row out again even though it is final. by_staff=True mirrors POST /staff/outbox/:id/decide
        requeue on the real server: attempts restart at 0 and the claim item carries requeued_at."""
        with self.lock:
            r = next(r for r in self.rows if r["id"] == rid)
            r["status"] = "queued"
            if by_staff:
                r["attempt"] = 0
                r["requeued_at"] = int(time.time() * 1000)

    def expire_lease(self, rid: str) -> None:
        """The 60 s lease ran out: the leased row becomes claimable again (next attempt)."""
        with self.lock:
            r = next(r for r in self.rows if r["id"] == rid)
            r["lease_until"] = 0

    def role_imports(self) -> list[dict]:
        return [q for q in self.requests if q["path"] == "/staff/roles/import"]

    def results(self, rid: str | None = None) -> list[dict]:
        return [q for q in self.requests if q["path"].endswith("/result")
                and (rid is None or q["path"] == f"/bridge/outbox/{rid}/result")]

    # ------------------------------------------------------------ routes

    def route(self, method: str, path: str, body, bridge_id: str):
        now = int(time.time() * 1000)
        with self.lock:
            if method == "POST" and path == "/bridge/outbox/claim":
                self.last_claim_at = now
                caps = (body or {}).get("capabilities") or []
                for r in self.rows:
                    expired = r["status"] == "leased" and r["lease_until"] < now and r["attempt"] < MAX_ATTEMPTS
                    if r["kind"] == "cs_images" and "images" not in caps:
                        continue                    # like the server: image rows only for an images-capable bridge
                    if r["status"] == "queued" or expired:
                        r.update(status="leased", attempt=r["attempt"] + 1, lease_until=now + LEASE_MS,
                                 lease_owner=bridge_id)
                        item = {k: r[k] for k in ("id", "thread_id", "text", "kind", "attempt", "lease_until")}
                        item["thread_type"] = r.get("thread_type", 0)
                        item["requeued_at"] = r.get("requeued_at")
                        if r["kind"] == "cs_images":
                            item["images"] = r.get("images")
                        return 200, {"item": item, "poll_after_ms": 0}
                return 200, {"item": None, "poll_after_ms": IDLE_POLL_MS, "reason": "no_work"}
            if method == "POST" and path.startswith("/bridge/outbox/") and path.endswith("/result"):
                if self.result_fail_times > 0:
                    self.result_fail_times -= 1
                    return 503, {}
                rid = path[len("/bridge/outbox/"):-len("/result")]
                r = next((x for x in self.rows if x["id"] == rid), None)
                if r is None:
                    return 404, {"error": {"code": "not_found", "message": "no such row"}}
                st = (body or {}).get("status")
                if st not in ("sent", "failed", "unknown"):
                    return 422, {"error": {"code": "validation_failed", "message": "status",
                                           "details": {"field": "status"}}}
                if st == "sent":
                    ignored = r["status"] == "sent"
                    r.update(status="sent", zalo_msg_id=r["zalo_msg_id"] or (body or {}).get("zalo_msg_id"),
                             part_msg_ids=r.get("part_msg_ids") or (body or {}).get("part_msg_ids"))
                    return 200, {"id": rid, "status": "sent", "ignored": ignored}
                if r["status"] == "sent" or r["status"] == st:
                    return 200, {"id": rid, "status": r["status"], "ignored": True}
                if r["status"] in ("failed", "unknown"):
                    return 409, {"error": {"code": "invalid_state", "message": r["status"]}}
                if r["status"] != "leased":
                    return 409, {"error": {"code": "lease_expired", "message": r["status"]}}
                if r["lease_owner"] != bridge_id:
                    return 409, {"error": {"code": "lease_not_owned", "message": "other bridge"}}
                att = (body or {}).get("attempt")
                if att is not None and att != r["attempt"]:
                    return 409, {"error": {"code": "lease_expired", "message": "stale attempt"}}
                r["error"] = (body or {}).get("error")
                if st == "failed" and r["attempt"] < MAX_ATTEMPTS:
                    r["status"] = "queued"          # the fake skips the retry backoff
                else:
                    r["status"] = st                # "unknown" is never re-queued
                return 200, {"id": rid, "status": r["status"], "ignored": False}
            if method == "GET" and path == "/bridge/status":
                counts: dict[str, int] = {}
                for r in self.rows:
                    counts[r["status"]] = counts.get(r["status"], 0) + 1
                return 200, {"last_claim_at": self.last_claim_at, "counts": counts}
        return 404, {"error": {"code": "not_found", "message": path}}

    def staff_route(self, method: str, path: str, body):
        with self.lock:
            if method == "POST" and path == "/staff/roles/import":
                if self.roles_import_error:
                    return self.roles_import_error
                body = body or {}
                roles = body.get("roles")
                bad = {"error": {"code": "validation_failed", "message": "roles"}}
                if body.get("source") != "zalo_label" or not isinstance(roles, list) or len(roles) > 5000:
                    return 422, bad
                for r in roles:
                    if not isinstance(r, dict) or not re.match(r"^p:[0-9]{1,40}$", str(r.get("zalo_user_id"))) \
                            or r.get("role") not in ("customer", "manager", "staff"):
                        return 422, bad
                out = {"imported": 0, "updated": 0, "unchanged": 0, "removed": 0, "kept_staff": 0}
                listed = set()
                for r in roles:
                    uid, role = r["zalo_user_id"], r["role"]
                    listed.add(uid)
                    if uid in self.staff_roles:
                        out["kept_staff"] += 1
                    elif uid not in self.label_roles:
                        out["imported"] += 1
                        self.label_roles[uid] = role
                    elif self.label_roles[uid] != role:
                        out["updated"] += 1
                        self.label_roles[uid] = role
                    else:
                        out["unchanged"] += 1
                if body.get("complete") is True:
                    for uid in [u for u in self.label_roles if u not in listed]:
                        del self.label_roles[uid]
                        out["removed"] += 1
                return 200, out
        return 404, {"error": {"code": "not_found", "message": path}}


class BridgeTestCase(unittest.TestCase):
    """Temp dir, fake engine config file, env isolation. Subclasses call self.cfg(...)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge-test-"))
        os.chmod(FAKE_ENGINE, 0o755)
        self.calls_log = self.tmp / "calls.jsonl"
        self.sent_log = self.tmp / "sent.jsonl"
        self.fake_cfg_path = self.tmp / "fake.json"
        self.fake: dict = {"send": "ok", "logged_in": True, "log": str(self.calls_log), "sent_log": str(self.sent_log),
                           "state": str(self.tmp / "daemon.json"), "daemon_log": str(self.tmp / "daemon.log")}
        self.write_fake()
        self._env = dict(os.environ)
        os.environ["FAKE_ZALO_CONFIG"] = str(self.fake_cfg_path)
        self.server: FakeBridgeServer | None = None

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        if self.server:
            self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_fake(self, **changes) -> None:
        self.fake.update(changes)
        self.fake_cfg_path.write_text(json.dumps(self.fake))

    def start_server(self) -> FakeBridgeServer:
        self.server = FakeBridgeServer().start()
        return self.server

    def cfg(self, **kw) -> Config:
        base = dict(server_url=self.server.url if self.server else "http://127.0.0.1:9", runner_token=TOKEN,
                    bridge_id=BRIDGE_ID, zalo_agent_bin=str(FAKE_ENGINE), state_dir=self.tmp / "state",
                    webhook_secret=SECRET, send_min_interval_s=0.0, send_jitter_s=0.0, send_timeout_s=10.0,
                    login_pause_s=60.0, label_sync_every_s=0.0)   # no periodic label sync unless a test asks
        base.update(kw)
        return Config(**base)

    def calls(self) -> list[dict]:
        try:
            return [json.loads(x) for x in self.calls_log.read_text().splitlines() if x.strip()]
        except FileNotFoundError:
            return []

    def send_calls(self) -> list[dict]:
        return [c for c in self.calls() if "send" in c["argv"] and "msg" in c["argv"]]

    def sent(self) -> list[dict]:
        try:
            return [json.loads(x) for x in self.sent_log.read_text().splitlines() if x.strip()]
        except FileNotFoundError:
            return []
