"""Backend HTTP client for the Bridge API (urllib, stdlib only). Never logs tokens or message text.

Contract (docs/contracts.md, "Personal Zalo channel"), auth `Authorization: Bearer <RUNNER_TOKEN>` + `X-Bridge-Id`:
  POST /bridge/outbox/claim        {"capabilities": ["images"]}
                                   -> {"item": {id, thread_id, thread_type, text, kind, images?, attempt, lease_until, ...}
                                       | null, "poll_after_ms": n, "reason"?: "no_work" | "outbound_disabled"}
  POST /bridge/outbox/:id/result   {"status": "sent"|"failed"|"unknown", "zalo_msg_id"?, "error"?, "attempt"?}
  GET  /bridge/status              last claim time and counts by status (for the console)
  GET  /health                     no auth

Staff API (StaffApi; auth `Authorization: Bearer <STAFF_TOKEN>` + `X-Staff-Id`), used by the label sync only:
  POST /staff/roles/import         {"source": "zalo_label", "complete": true, "roles": [{zalo_user_id, role}]}
                                   -> {"imported": n, "updated": n, "unchanged": n, "removed": n, "kept_staff": n}
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import USER_AGENT


CAPABILITIES = ("images",)


class ServerUnavailable(Exception):
    """Connection refused, DNS failure, timeout or a 5xx without an error body: back off and retry."""


@dataclass
class ApiError(Exception):
    status: int
    code: str
    message: str = ""

    def __str__(self) -> str:
        return f"HTTP {self.status} {self.code}"

    @classmethod
    def from_body(cls, status: int, body: Any) -> "ApiError":
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return cls(status=status, code=str(err.get("code") or "unknown"), message=str(err.get("message") or ""))
        return cls(status=status, code="http_error" if err is None else str(err), message="")


class BridgeApi:
    def __init__(self, base_url: str, token: str, bridge_id: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.bridge_id = bridge_id
        self.timeout = timeout

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Bridge-Id": self.bridge_id}

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, auth: bool = True,
                timeout: float | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json",
                   # Cloudflare answers 403 (error 1010) to the default Python-urllib user agent.
                   "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            headers.update(self.auth_headers())
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            e.close()
            try:
                parsed = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                parsed = None
            if e.code >= 500 and not (isinstance(parsed, dict) and "error" in parsed):
                raise ServerUnavailable(f"HTTP {e.code}") from None
            raise ApiError.from_body(e.code, parsed) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise ServerUnavailable(f"{type(e).__name__}: {getattr(e, 'reason', e)}") from None
        if not raw:
            return {}
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            raise ServerUnavailable("response is not JSON") from None
        return out if isinstance(out, dict) else {"_": out}

    # -------------------------------------------------------------- bridge endpoints

    def claim(self) -> tuple[dict[str, Any] | None, float | None]:
        """(item or None, server's poll_after_ms in seconds or None)."""
        # capabilities: this bridge sends menu image rows (kind cs_images) with `msg send-image`.
        out = self.request("POST", "/bridge/outbox/claim", {"capabilities": list(CAPABILITIES)})
        item = out.get("item")
        poll = out.get("poll_after_ms")
        poll_s = poll / 1000.0 if isinstance(poll, (int, float)) and not isinstance(poll, bool) and poll >= 0 else None
        return (item if isinstance(item, dict) else None), poll_s

    def result(self, item_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/bridge/outbox/{urllib.parse.quote(item_id, safe='')}/result", body)

    def status(self) -> dict[str, Any]:
        return self.request("GET", "/bridge/status")

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health", auth=False, timeout=5)


class StaffApi(BridgeApi):
    """The same HTTP client with the staff credentials (STAFF_TOKEN + X-Staff-Id) instead of the bridge's."""

    def __init__(self, base_url: str, token: str, staff_id: str, timeout: float = 15.0):
        super().__init__(base_url, token, staff_id, timeout)
        self.staff_id = staff_id

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Staff-Id": self.staff_id}

    def import_roles(self, roles: list[dict[str, str]]) -> dict[str, Any]:
        """Replace the label-sourced roles with this complete list (rows set by staff are kept by the server)."""
        return self.request("POST", "/staff/roles/import",
                            {"source": "zalo_label", "complete": True, "roles": roles}, timeout=30)
