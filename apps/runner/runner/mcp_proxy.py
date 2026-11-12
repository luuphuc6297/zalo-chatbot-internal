"""Stdio MCP server that proxies the 8 chatbot tools to the backend (POST /runner/tools/{name}).

Started by `claude -p` through the per-job --mcp-config written by runner/claude_runner.py, as
`python3 -I .../mcp_proxy.py`, so it is self-contained (stdlib only, no package imports).
Newline-delimited JSON-RPC 2.0 over stdin/stdout, same pattern as scripts/eval/mock_mcp_server.py.

Env (from the per-job config, never from model-visible text):
  THOMHOUSE_API_URL   backend base URL
  RUNNER_TOKEN        bearer token
  RUNNER_ID           X-Runner-Id
  THOMHOUSE_JOB_ID    the leased job; the server acts only on that job's conversation
  THOMHOUSE_TOOLS_FILE  JSON {"tools": [{name, description, inputSchema}]} from GET /runner/prompt
                        (fallback: tools-schema.json next to this file)
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

TOOL_NAMES = ("search_services", "get_service_details", "quote_price", "list_active_promotions",
              "create_booking_request", "handoff_to_staff", "record_contact_preference",
              # menu images: the server picks slide keys from data/menu-images.json and refuses claim slides; the
              # keys it returns become the draft's attachments (the model never passes a file path).
              "attach_menu_images")
CALL_TIMEOUT_S = 20


def load_tools() -> list[dict]:
    path = os.environ.get("THOMHOUSE_TOOLS_FILE")
    src = Path(path) if path else Path(__file__).resolve().parent / "tools-schema.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for t in data.get("tools", []):
        if t.get("name") in TOOL_NAMES:
            out.append({"name": t["name"], "description": t.get("description", ""),
                        "inputSchema": t.get("inputSchema") or t.get("input_schema") or {"type": "object"}})
    return out


def call_backend(name: str, arguments: dict) -> tuple[object, bool]:
    """Returns (result passed to the model, is_error). Transport and lease errors become tool errors so the
    model can hand off instead of inventing an answer."""
    base = os.environ.get("THOMHOUSE_API_URL", "").rstrip("/")
    body = json.dumps({"job_id": os.environ.get("THOMHOUSE_JOB_ID", ""), "input": arguments},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base}/runner/tools/{name}", data=body, method="POST", headers={
        "Authorization": f"Bearer {os.environ.get('RUNNER_TOKEN', '')}",
        "X-Runner-Id": os.environ.get("RUNNER_ID", ""), "Content-Type": "application/json",
        "User-Agent": "thomhouse-runner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S) as r:
            resp = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            code = (json.loads(e.read() or b"{}").get("error") or {}).get("code", "http_error")
        except (json.JSONDecodeError, AttributeError):
            code = "http_error"
        return {"error": "tool_unavailable", "code": code, "http_status": e.code}, True
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, json.JSONDecodeError):
        return {"error": "tool_unavailable", "code": "backend_unreachable"}, True
    if not isinstance(resp, dict):
        return {"error": "tool_unavailable", "code": "bad_response"}, True
    return resp.get("result"), bool(resp.get("is_error"))


def main() -> None:
    tools = load_tools()
    names = {t["name"] for t in tools}

    def reply(msg_id, result=None, error=None):
        out = {"jsonrpc": "2.0", "id": msg_id}
        if error:
            out["error"] = error
        else:
            out["result"] = result
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
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
        if msg_id is None:  # notification
            continue
        if method == "initialize":
            reply(msg_id, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "thom", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(msg_id, {"tools": tools})
        elif method == "tools/call":
            p = msg.get("params") or {}
            name = p.get("name", "")
            if name not in names:
                reply(msg_id, {"content": [{"type": "text", "text": json.dumps({"error": "unknown_tool"})}],
                               "isError": True})
                continue
            out, is_err = call_backend(name, p.get("arguments") or {})
            reply(msg_id, {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                           "isError": is_err})
        elif method == "ping":
            reply(msg_id, {})
        else:
            reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
