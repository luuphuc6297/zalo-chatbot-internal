"""Stdio MCP server exposing the 7 chatbot tools backed by mock data.

Started by `claude -p` through an --mcp-config file. Env:
  EVAL_CONTEXT  path to a JSON file with the eval case context (active_promotions, ...)
  EVAL_CALL_LOG path to a JSONL file; every call and its output is appended there
No third-party dependencies: newline-delimited JSON-RPC 2.0 over stdin/stdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import MockTools, load_services, load_tools  # noqa: E402


def main():
    ctx_path = os.environ.get("EVAL_CONTEXT")
    ctx = json.loads(Path(ctx_path).read_text(encoding="utf-8")) if ctx_path else {}
    log_path = os.environ.get("EVAL_CALL_LOG")
    mock = MockTools(load_services(), ctx)
    tools = [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
             for t in load_tools()]

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
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:  # notification
            continue
        if method == "initialize":
            reply(msg_id, {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "thom-mock", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(msg_id, {"tools": tools})
        elif method == "tools/call":
            p = msg.get("params", {})
            out, is_err = mock.run(p.get("name", ""), p.get("arguments") or {})
            if log_path:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"name": p.get("name"), "input": p.get("arguments"), "output": out,
                                        "is_error": is_err}, ensure_ascii=False) + "\n")
            reply(msg_id, {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                           "isError": is_err})
        elif method == "ping":
            reply(msg_id, {})
        else:
            reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
