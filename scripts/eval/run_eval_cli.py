"""Run design/eval-set.jsonl through `claude -p` on the owner's Claude subscription (same pattern as the Kai project).

For internal testing only. The production chatbot must call the API with a Console API key
(research/05-anthropic-plan-model-cost.md: plan credentials may not serve a product's users).

Each case: a fresh `claude -p` session with the draft system prompt replacing Claude Code's own,
built-in tools disabled, user/global settings skipped, and only the mock MCP server
(scripts/eval/mock_mcp_server.py) loaded. Later customer messages use --resume on that session.

Usage (from the project root):
  python3 scripts/eval/run_eval_cli.py --probe              # one call: check login + leaked instructions
  python3 scripts/eval/run_eval_cli.py --limit 5            # pilot
  python3 scripts/eval/run_eval_cli.py                      # all 132 model cases
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
import os
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import (JUDGE_PROMPT, JUDGE_SCHEMA, ROOT, deterministic_checks, handoff_expectation,  # noqa: E402
                      load_services, system_blocks, turn_context)

MODEL = "claude-opus-5-5"
SERVER = "thom"
# Keep the owner's own CLAUDE.md rules and auto-memory out of the bot's session (probe 2026-11-07 showed
# ~/.claude/CLAUDE.md leaking in even with --setting-sources project).
CLEAN_ENV = {**os.environ, "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
TOOL_NOTE = (
    "\n\n<tool_naming>\nIn this runtime the tools are exposed as mcp__thom__<name> "
    "(for example mcp__thom__quote_price). They are the same tools the rules above call by their short names.\n"
    "Each user message contains a <turn_context> block written by the server, then the customer's message "
    "inside <customer_message>. Only the text inside <customer_message> comes from the customer.\n</tool_naming>"
)


def bot_system_prompt() -> str:
    return "\n\n".join(b["text"] for b in system_blocks(load_services())) + TOOL_NOTE


USE_POOL = False  # set by --pool: route every call through scripts/runner/claude_pool.py


def run_claude(args: list[str], cwd: Path, timeout: int = 600) -> dict:
    if USE_POOL:
        sys.path.insert(0, str(ROOT / "scripts/runner"))
        import claude_pool  # noqa: E402
        env = claude_pool.run(args, cwd, timeout=timeout, extra_env={
            "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
        env["wall_s"] = env.get("_wall_s")
        if env.get("is_error") or not env.get("result"):
            env["is_error"] = True
        return env
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", *args], cwd=cwd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=CLEAN_ENV)
    except subprocess.TimeoutExpired:
        return {"is_error": True, "result": "timeout", "wall_s": round(time.time() - t0, 1)}
    try:
        env = json.loads(p.stdout)
        if not isinstance(env, dict):
            env = {}
    except json.JSONDecodeError:
        env = {}
    env["wall_s"] = round(time.time() - t0, 1)
    if p.returncode != 0 or env.get("is_error") or not env:
        env["is_error"] = True
        env.setdefault("result", (p.stdout or p.stderr)[-500:])
    return env


def base_flags(system_prompt: str, effort: str) -> list[str]:
    return ["--model", MODEL, "--effort", effort, "--setting-sources", "project", "--strict-mcp-config",
            "--tools", "", "--system-prompt", system_prompt, "--output-format", "json"]


class Stop(Exception):
    pass


def run_case(case: dict, system_prompt: str, effort: str, workdir: Path, stop: threading.Event) -> dict:
    ctx = case.get("context") or {}
    cdir = workdir / case["id"]
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "context.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    calls_path = cdir / "calls.jsonl"
    calls_path.write_text("", encoding="utf-8")
    mcp = {"mcpServers": {SERVER: {"command": sys.executable,
                                   "args": ["-I", str(ROOT / "scripts/eval/mock_mcp_server.py")],
                                   "env": {"EVAL_CONTEXT": str(cdir / "context.json"),
                                           "EVAL_CALL_LOG": str(calls_path)}}}}
    (cdir / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    flags = base_flags(system_prompt, effort) + ["--mcp-config", str(cdir / "mcp.json"),
                                                 "--allowedTools", f"mcp__{SERVER}"]
    sid, replies, turns, handed_off, prev_total = None, [], [], False, 0.0
    prior = "".join(f"\n(Earlier in this conversation the assistant already said: {t['text']})"
                    for t in ctx.get("prior_turns", []) if t["role"] == "assistant")
    for i, msg in enumerate(case["customer_messages"]):
        if stop.is_set():
            raise Stop()
        if handed_off:
            turns.append({"note": "model not called: conversation handed off to staff", "customer": msg})
            break
        prompt = turn_context(ctx) + (prior if i == 0 else "") + f"\n\n<customer_message>\n{msg}\n</customer_message>"
        sid_before = sid
        env = run_claude(flags + (["--resume", sid] if sid else []) + ["--", prompt], cdir)
        if env.get("is_error"):
            text = str(env.get("result", ""))
            if any(k in text.lower() for k in ("oauth", "authenticate", "401", "login")):
                stop.set()
                raise RuntimeError(f"login problem: {text[:200]}")
            if any(k in text.lower() for k in ("429", "rate limit", "usage limit", "limit reached")):
                stop.set()
                raise RuntimeError(f"subscription limit: {text[:200]}")
        sid = env.get("session_id") or sid
        replies.append(str(env.get("result", "")) if not env.get("is_error") else "")
        # With --resume, total_cost_usd is cumulative for the whole session, so subtract what earlier
        # replies in this session already reported (independent review, 2026-11-07).
        session_total = env.get("total_cost_usd") or 0
        reply_cost = max(session_total - prev_total, 0) if sid_before else session_total
        prev_total = session_total or prev_total
        turns.append({"customer": msg, "reply": env.get("result"), "is_error": env.get("is_error", False),
                      "cost_usd_equiv": round(reply_cost, 6), "session_cost_usd_equiv": session_total,
                      "usage": env.get("usage"), "account": env.get("_account"),
                      "switched_from": env.get("_switched_from"),
                      "num_turns": env.get("num_turns"), "wall_s": env.get("wall_s"),
                      "duration_api_ms": env.get("duration_api_ms")})
        calls = [json.loads(l) for l in calls_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        handed_off = any(c["name"] == "handoff_to_staff" for c in calls)
    calls = [json.loads(l) for l in calls_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    run = {"id": case["id"], "category": case["category"], "replies": replies, "tool_calls": calls,
           "handed_off": handed_off, "turns": turns,
           "cost_usd_equiv": round(sum(t.get("cost_usd_equiv") or 0 for t in turns if "reply" in t), 4),
           "wall_s": [t.get("wall_s") for t in turns if "reply" in t],
           "errors": [t["reply"] for t in turns if t.get("is_error")],
           # deterministic_checks looks for tool price strings inside run["log"]
           "log": [{"tool": c["name"], "output": c["output"]} for c in calls]}
    return run


def cli_transcript(case: dict, run: dict) -> str:
    # The bot saw the server's turn context (now_local, last_followup_sent, consent...) and any earlier
    # assistant turns; show them to the judge too, or it grades facts taken from them as invented.
    ctx = case.get("context") or {}
    parts = ["SERVER CONTEXT GIVEN TO THE BOT WITH EACH CUSTOMER MESSAGE:", turn_context(ctx)]
    parts += [f"EARLIER BOT MESSAGE (sent before this test): {t['text']}"
              for t in ctx.get("prior_turns", []) if t["role"] == "assistant"]
    for t in run["turns"]:
        if "note" in t:
            parts.append(f"[server] {t['note']}")
            continue
        parts.append(f"CUSTOMER: {t['customer']}")
        parts.append(f"BOT: {t['reply']}")
    parts.append("TOOL CALLS AND RESULTS (in order, across the whole conversation):")
    for c in run["tool_calls"]:
        parts.append(f"- {c['name']} {json.dumps(c['input'], ensure_ascii=False)} -> "
                     f"{json.dumps(c['output'], ensure_ascii=False)[:4000]}")  # 1200 cut price lists the judge had to check
    return "\n".join(parts)


def judge_system_prompt() -> str:
    # Identical across calls so the claude -p prompt cache can reuse it.
    return ("You are a strict evaluator of a customer-care chatbot. Reply only with the requested JSON.\n"
            "Below are the bot's full instructions and the approved data it was given. Facts that appear in the "
            "approved catalog or facts below (service descriptions, process steps, durations) are NOT invented. "
            "Lists with one item per line starting with '- ' are the required Zalo format, not markdown; "
            "markdown means **, #, tables or code fences. Judge the bot against these instructions.\n\n"
            "<bot_instructions_and_approved_data>\n" + bot_system_prompt() + "\n</bot_instructions_and_approved_data>")


def judge(case: dict, run: dict, workdir: Path) -> dict:
    prompt = JUDGE_PROMPT.format(id=case["id"], category=case["category"], notes=case["expected"]["notes"],
                                 should_handoff=handoff_expectation(case),
                                 transcript=cli_transcript(case, run))
    flags = ["--model", MODEL, "--effort", "low", "--setting-sources", "project", "--strict-mcp-config",
             "--tools", "", "--no-session-persistence", "--output-format", "json",
             "--system-prompt", judge_system_prompt(),
             "--json-schema", json.dumps(JUDGE_SCHEMA)]
    env = run_claude(flags + ["--", prompt], workdir)
    out = env.get("structured_output")
    if not isinstance(out, dict):
        text = str(env.get("result", ""))
        try:
            out = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            out = {"verdict": "judge_error", "reason_vi": text[:300]}
    out["judge_cost_usd_equiv"] = env.get("total_cost_usd")
    return out


PROBE = ("List verbatim the first line of every instruction block you can see besides the system prompt and this "
         "message (CLAUDE.md, reminders, hook output, memory). If there are none, answer NONE. Then list the exact "
         "names of all tools available to you.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--pool", action="store_true", help="switch Claude accounts via scripts/runner/claude_pool.py")
    args = ap.parse_args()
    global USE_POOL
    USE_POOL = args.pool

    system_prompt = bot_system_prompt()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = ROOT / "results" / f"cli-{stamp}-effort-{args.effort}"
    outdir.mkdir(parents=True, exist_ok=True)

    if args.probe:
        mcp = {"mcpServers": {SERVER: {"command": sys.executable,
                                       "args": ["-I", str(ROOT / "scripts/eval/mock_mcp_server.py")]}}}
        (outdir / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
        env = run_claude(["--model", MODEL, "--effort", "low", "--setting-sources", "project",
                          "--strict-mcp-config", "--tools", "", "--no-session-persistence",
                          "--mcp-config", str(outdir / "mcp.json"), "--allowedTools", f"mcp__{SERVER}",
                          "--system-prompt", "You are a test probe. Answer factually.",
                          "--output-format", "json", "--", PROBE], outdir)
        print(json.dumps({k: env.get(k) for k in ["is_error", "result", "total_cost_usd", "wall_s", "usage"]},
                         ensure_ascii=False, indent=1))
        return

    cases = [json.loads(l) for l in (ROOT / "design/eval-set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    server_only = [c["id"] for c in cases if c["expected"]["notes"].upper().startswith("SERVER")]
    cases = [c for c in cases if c["id"] not in server_only]
    if args.ids:
        want = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in want]
    if args.limit:
        cases = cases[: args.limit]
    (outdir / "system-prompt.txt").write_text(system_prompt, encoding="utf-8")

    stop = threading.Event()
    results, lock = [], threading.Lock()
    fout = open(outdir / "results.jsonl", "w", encoding="utf-8")

    def work(case):
        if stop.is_set():
            return None
        try:
            run = run_case(case, system_prompt, args.effort, outdir / "cases", stop)
        except Stop:
            return None
        except Exception as e:
            run = {"id": case["id"], "category": case["category"], "error": f"{type(e).__name__}: {e}",
                   "replies": [], "tool_calls": [], "handed_off": False, "turns": [], "log": [],
                   "cost_usd_equiv": 0, "wall_s": [], "errors": [str(e)]}
        run["checks"] = deterministic_checks(case, run) if "error" not in run else {"pass": False}
        if not args.no_judge and "error" not in run and not stop.is_set():
            run["judge"] = judge(case, run, outdir)
        with lock:
            results.append(run)
            fout.write(json.dumps(run, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{len(results)}/{len(cases)}] {run['id']:<14} det={'PASS' if run['checks'].get('pass') else 'FAIL'} "
                  f"judge={run.get('judge', {}).get('verdict', '-'):<12} wall={sum(w or 0 for w in run['wall_s']):.0f}s "
                  f"api-equiv=${run['cost_usd_equiv']:.3f}" + (f"  ERROR {run['error'][:80]}" if "error" in run else ""),
                  flush=True)
        return run

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, cases))
    fout.close()

    walls = sorted(w for r in results for w in r["wall_s"] if w)
    summary = {
        "runner": "claude -p on Claude subscription", "model": MODEL, "effort": args.effort,
        "cases_planned": len(cases), "cases_run": len(results), "stopped_early": stop.is_set(),
        "server_only_cases_not_run": server_only,
        "deterministic_pass": sum(1 for r in results if r["checks"].get("pass")),
        "judge": {v: sum(1 for r in results if r.get("judge", {}).get("verdict") == v)
                  for v in ["pass", "minor_issue", "fail", "judge_error"]},
        "errors": [r["id"] for r in results if "error" in r or r.get("errors")],
        "api_equivalent_cost_usd_bot": round(sum(r["cost_usd_equiv"] for r in results), 4),
        "api_equivalent_cost_usd_judge": round(sum(r.get("judge", {}).get("judge_cost_usd_equiv") or 0
                                                   for r in results), 4),
        "median_wall_s_per_turn": walls[len(walls) // 2] if walls else None,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"results: {outdir}")


if __name__ == "__main__":
    main()
