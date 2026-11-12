"""Backend HTTP client for the Runner API (urllib, stdlib only). Never logs tokens or message text."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from .contract import ApiError


class ServerUnavailable(Exception):
    """Connection refused, DNS failure, timeout or a 5xx without an error body: back off and retry."""


class ApiClient:
    def __init__(self, base_url: str, token: str, runner_id: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.runner_id = runner_id
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None,
                timeout: float | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "X-Runner-Id": self.runner_id,
            "Content-Type": "application/json", "Accept": "application/json",
            # Cloudflare answers 403 (error 1010) to the default Python-urllib user agent.
            "User-Agent": "thomhouse-runner/1.0"})
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
            raise ApiError.from_body(e.code, parsed if isinstance(parsed, dict) else None) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise ServerUnavailable(f"{type(e).__name__}: {getattr(e, 'reason', e)}") from None
        if not raw:
            return {}
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            raise ServerUnavailable("response is not JSON") from None
        return out if isinstance(out, dict) else {"_": out}

    # -------------------------------------------------------------- runner endpoints

    def claim(self) -> dict[str, Any]:
        return self.request("POST", "/runner/jobs/claim", {})

    def heartbeat(self, job_id: str) -> dict[str, Any]:
        return self.request("POST", f"/runner/jobs/{job_id}/heartbeat", {})

    def draft(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/runner/jobs/{job_id}/draft", body)

    def fail(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/runner/jobs/{job_id}/fail", body)

    def prompt(self) -> dict[str, Any]:
        return self.request("GET", "/runner/prompt")

    def status(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/runner/status", body)

    # -------------------------------------------------------------- two-bot rooms (docs/contracts.md 14.7)

    def rooms_feed(self, conversation_id: str | None = None, seed: bool = False,
                   limit: int | None = None) -> dict[str, Any]:
        """Without a conversation: the observation feed. With one: its pending rows, or its last rows (`seed`)."""
        body: dict[str, Any] = {}
        if conversation_id:
            body["conversation_id"] = conversation_id
        if seed:
            body["seed"] = True
        if limit is not None:
            body["limit"] = limit
        return self.request("POST", "/runner/rooms/feed", body)

    def rooms_ack(self, conversation_id: str, message_ids: list[str], channel_id: str | None = None) -> int:
        """Mark rows as mirrored into the room (at most 200 ids per call). Returns the number marked."""
        marked = 0
        for i in range(0, len(message_ids), 200):
            body: dict[str, Any] = {"conversation_id": conversation_id, "message_ids": message_ids[i:i + 200]}
            if channel_id:
                body["room"] = {"channel_id": channel_id}
            marked += int(self.request("POST", "/runner/rooms/ack", body).get("marked") or 0)
        return marked
