#!/usr/bin/env python3
"""stdio MCP server "thom" for the two-bot rooms (docs/contracts.md 14.8).

The rooms platform starts this file once per bot turn as `python3 -I <absolute path>/room_tools.py`, with
THOMHOUSE_BOT_HOME in its configured environment. Standard library only, single file: it cannot import the runner
package. The protocol code has the same shape as mcp_proxy.py (newline-delimited JSON-RPC 2.0).

Differences from mcp_proxy.py:
  - nine tools (the eight business tools plus get_customer_profile), each with a required string `ticket`;
  - the platform passes no job id, so every call names the turn with the ticket from the room message. The ticket
    file <home>/rooms/tickets/<ticket>.json binds it to the leased job; `ticket` is removed before forwarding;
  - backend URL, runner id and token come from <home>/rooms/credentials.json, never from the environment, and are
    never written to a tool result, a log line or an error text;
  - every forwarded call appends { tool, is_error, bot, at } to <home>/rooms/tickets/<ticket>.calls.jsonl.

An unknown, expired or malformed ticket answers { "error": "ticket_invalid" } as a tool error and contacts nothing.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TOOL_NAMES = ("search_services", "get_service_details", "quote_price", "list_active_promotions",
              "create_booking_request", "handoff_to_staff", "record_contact_preference", "attach_menu_images",
              "get_customer_profile")
CALL_TIMEOUT_S = 20
TICKET_RE = re.compile(r"tk_[0-9a-f]{32}")
TICKET_PROPERTY = {
    "type": "string",
    "description": "Mã phiếu của lượt này, chép nguyên văn từ dòng [phiếu: ...] ở đầu tin nhắn mới nhất trong phòng.",
}
TICKET_INVALID = {"error": "ticket_invalid"}


def home() -> Path:
    return Path(os.path.expanduser(os.environ.get("THOMHOUSE_BOT_HOME") or "~/.thomhouse-bot"))


def rooms_dir() -> Path:
    return home() / "rooms"


def _read_tools(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    tools = data.get("tools") if isinstance(data, dict) else data
    return [t for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []


def with_ticket(schema: object) -> dict:
    """A copy of a tool's input schema with the required string property `ticket`."""
    out = dict(schema) if isinstance(schema, dict) else {}
    out["type"] = "object"
    props = dict(out.get("properties") or {})
    props["ticket"] = dict(TICKET_PROPERTY)
    out["properties"] = props
    required = [r for r in (out.get("required") or []) if r != "ticket"]
    out["required"] = required + ["ticket"]
    return out


def load_tools() -> list[dict]:
    """The nine tools. The shipped file is the base; <home>/rooms/tools.json (the server's current definitions,
    written by the runner) wins per tool. THOMHOUSE_TOOLS_FILE replaces both (tests)."""
    override = os.environ.get("THOMHOUSE_TOOLS_FILE")
    sources = [Path(override)] if override else [Path(__file__).resolve().parent / "tools-schema.json",
                                                 rooms_dir() / "tools.json"]
    by_name: dict[str, dict] = {}
    for src in sources:
        for t in _read_tools(src):
            if t.get("name") in TOOL_NAMES:
                by_name[t["name"]] = t
    out = []
    for name in TOOL_NAMES:
        t = by_name.get(name)
        if t is None:
            continue
        out.append({"name": name, "description": t.get("description", ""),
                    "inputSchema": with_ticket(t.get("inputSchema") or t.get("input_schema"))})
    return out


def read_ticket(ticket: object) -> dict | None:
    """The ticket record when `ticket` is well formed, known and not expired; None otherwise."""
    if not isinstance(ticket, str) or not TICKET_RE.fullmatch(ticket):
        return None
    try:
        data = json.loads((rooms_dir() / "tickets" / f"{ticket}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    job_id, expires_at = data.get("job_id"), data.get("expires_at")
    if not isinstance(job_id, str) or not job_id:
        return None
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) or expires_at <= time.time() * 1000:
        return None
    return data


def read_credentials() -> dict | None:
    try:
        data = json.loads((rooms_dir() / "credentials.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not all(isinstance(data.get(k), str) and data.get(k) for k in ("api_url", "runner_id", "token")):
        return None
    return data


def log_call(ticket: str, tool: str, is_error: bool) -> None:
    """One line per forwarded call. The bot is the platform's bot id: the server's working folder is
    <data dir>/workspaces/<botId>."""
    line = json.dumps({"tool": tool, "is_error": bool(is_error), "bot": os.path.basename(os.getcwd()),
                       "at": int(time.time() * 1000)}, ensure_ascii=False)
    path = rooms_dir() / "tickets" / f"{ticket}.calls.jsonl"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def call_backend(name: str, job_id: str, arguments: dict) -> tuple[object, bool]:
    creds = read_credentials()
    if creds is None:
        return {"error": "tool_unavailable", "code": "credentials_missing"}, True
    body = json.dumps({"job_id": job_id, "input": arguments}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{creds['api_url'].rstrip('/')}/runner/tools/{name}", data=body, method="POST",
                                 headers={
                                     "Authorization": f"Bearer {creds['token']}",
                                     "X-Runner-Id": creds["runner_id"],
                                     "Content-Type": "application/json",
                                     "User-Agent": "thomhouse-runner/1.0",
                                 })
    try:
        with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S) as r:
            resp = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            code = (json.loads(e.read() or b"{}").get("error") or {}).get("code", "http_error")
        except (json.JSONDecodeError, AttributeError):
            code = "http_error"
        return {"error": "tool_unavailable", "code": code, "http_status": e.code}, True
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, json.JSONDecodeError, ValueError):
        return {"error": "tool_unavailable", "code": "backend_unreachable"}, True
    if not isinstance(resp, dict):
        return {"error": "tool_unavailable", "code": "bad_response"}, True
    return resp.get("result"), bool(resp.get("is_error"))


def call_tool(name: str, arguments: dict) -> tuple[object, bool]:
    ticket = arguments.get("ticket")
    record = read_ticket(ticket)
    if record is None:
        return dict(TICKET_INVALID), True
    rest = {k: v for k, v in arguments.items() if k != "ticket"}
    out, is_err = call_backend(name, record["job_id"], rest)
    log_call(ticket, name, is_err)
    return out, is_err


def main() -> None:
    tools = load_tools()
    names = {t["name"] for t in tools}

    def reply(msg_id, result=None, error=None) -> None:
        msg = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:
            continue                                    # notifications need no answer
        if method == "initialize":
            params = msg.get("params") or {}
            reply(msg_id, {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "thom", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(msg_id, {"tools": tools})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            if name not in names:
                reply(msg_id, {"content": [{"type": "text", "text": json.dumps({"error": "unknown_tool"})}],
                               "isError": True})
                continue
            args = params.get("arguments")
            out, is_err = call_tool(name, args if isinstance(args, dict) else {})
            reply(msg_id, {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                           "isError": is_err})
        elif method == "ping":
            reply(msg_id, {})
        else:
            reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
