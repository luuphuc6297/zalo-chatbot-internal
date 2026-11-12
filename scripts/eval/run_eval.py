"""Run design/eval-set.jsonl against claude-opus-5-5 with the draft prompt and mock tools.

Usage (from the project root):
  .venv/bin/python scripts/eval/run_eval.py --dry-run            # build prompt + mocks, no API call
  .venv/bin/python scripts/eval/run_eval.py --limit 5 --max-usd 3 # pilot on 5 cases
  .venv/bin/python scripts/eval/run_eval.py --max-usd 25          # full run with a hard spend cap

Credentials: ANTHROPIC_API_KEY in the environment, or the file .secrets/anthropic_api_key
(one line, created by the owner; never printed or logged by this script).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"

# USD per million tokens, claude-opus-5-5 (claude-api skill, cached 2026-10-06; research/05 re-verified 2026-11-07).
PRICE = {"input": 4.00, "output": 20.00, "cache_write_5m": 5.00, "cache_write_1h": 8.00, "cache_read": 0.20}

DEFAULT_NOW = "2026-11-07T15:00+07:00 (thứ Bảy)"


# ---------------------------------------------------------------- prompt blocks

def strip_marks(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def block_a() -> str:
    text = (ROOT / "design/system-prompt-draft.md").read_text(encoding="utf-8")
    start = text.index("## Khối A")
    fence = text.index("```text\n", start) + len("```text\n")
    end = text.index("\n```", fence)
    return text[fence:end].strip()


def load_services() -> list[dict]:
    return json.loads((ROOT / "data/services.json").read_text(encoding="utf-8"))["services"]


def block_b(services: list[dict]) -> str:
    group_order = ["relaxation", "health", "women", "skin", "hair"]
    lines = [
        '<approved_catalog version="cv_eval_draft_unapproved">',
        "Groups: relaxation = menu thư giãn (4 services), health = menu khỏe (6), women = menu chăm sóc sức khỏe phụ nữ (5), skin = menu da (5), hair = menu tóc (3). Total 23 services.",
        "Prices are NOT listed here. Use tools for every price.",
        "",
    ]
    for s in sorted(services, key=lambda x: (group_order.index(x["group"]), x["id"])):
        durations = sorted({v["duration_min"] for v in s["variants"]})
        windows = any(v.get("time_window") for v in s["variants"])
        steps = "; ".join(s.get("process_steps_vi") or []) or "[chưa có]"
        lines.append(
            f"[service_id: {s['id']}] group: {s['group']} | display_name_vi: {s['name_vi']} | "
            f"durations: {', '.join(map(str, durations))} | has_time_windows: {'yes' if windows else 'no'} | "
            f"signature: {'yes' if s.get('is_signature') else 'no'}"
        )
        lines.append(f"short_description_vi: {s.get('short_description_vi') or '[chưa có]'}")
        lines.append(f"process_steps_vi: {steps}")
        lines.append("")
    lines.append("</approved_catalog>")
    return "\n".join(lines)


def block_c() -> str:
    """Approved facts block. Only facts with status 'documented' carry a value (the owner has not approved
    anything yet, so 'documented' is the closest stand-in); conflict / missing / derived_unapproved -> [chưa có].
    Prices are stripped: the bot may state prices only from tool results."""
    facts = json.loads((ROOT / "data/business-facts.json").read_text(encoding="utf-8"))["facts"]
    out = ['<approved_facts version="fv_eval_draft_unapproved">']
    for k in sorted(facts):
        f = facts[k]
        v = f.get("value")
        if f.get("status") != "documented" or v in (None, "", []):
            out.append(f"{k}: [chưa có]")
            continue
        if k == "combos":
            v = [{kk: vv for kk, vv in c.items() if kk != "price_vnd"} for c in v]
        out.append(f"{k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
    out.append("</approved_facts>")
    out.append("")
    out.append('<approved_knowledge version="kb_eval_none">')
    out.append("No knowledge entries are approved yet. For questions about techniques, herbs, devices or health effects, describe only the approved process steps from the catalog, or hand off.")
    out.append("</approved_knowledge>")
    return "\n".join(out)


def system_blocks(services: list[dict]) -> list[dict]:
    return [
        {"type": "text", "text": block_a()},
        {"type": "text", "text": block_b(services)},
        {"type": "text", "text": block_c(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
    ]


def load_tools() -> list[dict]:
    d = json.loads((ROOT / "design/tools-schema.json").read_text(encoding="utf-8"))
    return [{k: v for k, v in t.items() if not k.startswith("x_")} for t in d["tools"]]


def turn_context(ctx: dict) -> str:
    consent = ctx.get("consent") or {"ai_assistant": "granted"}
    consent_txt = "; ".join(f"{k}={v}" for k, v in consent.items())
    promos = ctx.get("active_promotions")
    lines = [
        "<turn_context>",
        f"now_local: {ctx.get('now_local', DEFAULT_NOW)} Asia/Ho_Chi_Minh",
        "conversation_mode: approve_each",
        'customer_display_name: "Khách"',
        "customer_gender_hint: unknown",
        "minor_flag: unknown",
        f"consent: {consent_txt}; followup_care=none; promotions=none",
        "open_booking_requests: none",
        f"last_followup_sent: {ctx.get('last_followup_sent', 'none')}",
    ]
    notes = []
    if ctx.get("recent_visit"):
        notes.append(f"recent visit: {ctx['recent_visit']}")
    if ctx.get("server_state"):
        notes.append(f"server_state: {ctx['server_state']}")
    if ctx.get("bot_state_history"):
        notes.append(f"bot_state history: {' -> '.join(ctx['bot_state_history'])}")
    if promos is not None:
        notes.append(f"active approved promotions: {len(promos)}")
    lines.append(f"notes: {'; '.join(notes) if notes else 'none'}")
    lines.append("</turn_context>")
    return "\n".join(lines)


# ---------------------------------------------------------------- mock tools

def fmt_vnd(n: int) -> str:
    return f"{n:,}".replace(",", ".") + "đ"


def to_min(hhmm: str) -> int | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


class MockTools:
    def __init__(self, services: list[dict], ctx: dict):
        self.by_id = {s["id"]: s for s in services}
        self.services = services
        self.promotions = ctx.get("active_promotions") or []
        self.calls: list[dict] = []

    def _variants(self, s, include_prices=True):
        out = []
        for v in s["variants"]:
            item = {"duration_min": v["duration_min"], "time_window": v.get("time_window")}
            if include_prices:
                item.update(price_vnd=v["price_vnd"], price_text=fmt_vnd(v["price_vnd"]))
            out.append(item)
        return out

    def search_services(self, query: str, group: str, include_prices: bool):
        q = strip_marks(query or "")
        tokens = [t for t in re.split(r"\W+", q) if len(t) > 1]
        hits = []
        for s in self.services:
            if group != "any" and s["group"] != group:
                continue
            hay = strip_marks(" ".join([s["id"].replace("-", " "), s["name_vi"], s.get("short_description_vi") or "",
                                        " ".join(s.get("process_steps_vi") or [])]))
            name = strip_marks(s["id"].replace("-", " ") + " | " + s["name_vi"])
            score = sum(1 for t in tokens if t in hay) if tokens else 1
            score += sum(2 for t in tokens if t in name.split())
            if q.strip() and q.strip() in name:
                score += 10
            if score:
                hits.append((score, s))
        hits.sort(key=lambda x: -x[0])
        res = [{"service_id": s["id"], "group": s["group"], "display_name_vi": s["name_vi"],
                "is_signature": bool(s.get("is_signature")), "variants": self._variants(s, include_prices)}
               for _, s in hits[:8]]
        return {"catalog_version_id": "cv_eval_draft_unapproved", "services": res}

    def get_service_details(self, service_id: str):
        s = self.by_id.get(service_id)
        if not s:
            return {"status": "not_found"}
        return {"service_id": s["id"], "group": s["group"], "display_name_vi": s["name_vi"],
                "short_description_vi": s.get("short_description_vi") or {"status": "missing"},
                "process_steps_vi": s.get("process_steps_vi") or {"status": "missing"},
                "variants": self._variants(s), "who_should_avoid_or_consult": {"status": "unapproved"},
                "ingredients_or_devices": {"status": "unapproved"}}

    def quote_price(self, service_id: str, duration_min: int, start_time_local: str, date_local: str):
        s = self.by_id.get(service_id)
        if not s:
            return {"status": "not_found"}
        variants = s["variants"]
        durations = sorted({v["duration_min"] for v in variants})
        if duration_min == 0:
            return {"status": "all_durations", "candidates": self._variants(s)}
        vs = [v for v in variants if v["duration_min"] == duration_min]
        if not vs:
            return {"status": "invalid_duration", "valid_durations": durations}
        windowed = [v for v in vs if v.get("time_window") in ("09:00-20:30", "after_20:30")]
        if len(windowed) < 2:
            v = vs[0]
            return {"status": "ok", "price_vnd": v["price_vnd"], "price_text": fmt_vnd(v["price_vnd"]),
                    "time_window": v.get("time_window"), "rule": "single price for this duration"}
        day = next(v for v in windowed if v["time_window"] == "09:00-20:30")
        night = next(v for v in windowed if v["time_window"] == "after_20:30")
        both = [{"condition": "giờ ngày 9h–20h30", "price_text": fmt_vnd(day["price_vnd"])},
                {"condition": "sau 20h30", "price_text": fmt_vnd(night["price_vnd"])}]
        t = to_min(start_time_local)
        if t is None:
            return {"status": "needs_time", "candidates": both}
        if t < 9 * 60:
            return {"status": "outside_known_hours", "candidates": both}
        if t == 20 * 60 + 30 or (t < 20 * 60 + 30 < t + duration_min):
            return {"status": "ambiguous", "rule_status": "unconfirmed", "candidates": both,
                    "note": "Studio chưa chốt cách tính giá ở mốc 20h30; nhân viên sẽ xác nhận."}
        v = day if t < 20 * 60 + 30 else night
        return {"status": "ok", "price_vnd": v["price_vnd"], "price_text": fmt_vnd(v["price_vnd"]),
                "time_window": v["time_window"], "hours_status": "opening hours unconfirmed"}

    def list_active_promotions(self, service_id: str):
        return {"promotions": self.promotions}

    def create_booking_request(self, **kw):
        return {"status": "created", "request_id": "br_eval_0001", "staff_confirmation": "pending",
                "staff_response_target": None}

    def handoff_to_staff(self, **kw):
        return {"status": "accepted", "bot_state": "handoff_requested"}

    def record_contact_preference(self, **kw):
        return {"status": "recorded", "action": kw.get("action")}

    def run(self, name: str, args: dict):
        self.calls.append({"name": name, "input": args})
        fn = getattr(self, name, None)
        if fn is None:
            return {"error": f"unknown tool {name}"}, True
        try:
            out, err = fn(**args), False
        except TypeError as e:
            out, err = {"error": f"bad arguments: {e}"}, True
        self.calls[-1]["output"] = out
        return out, err


# ---------------------------------------------------------------- spend tracking

class Spend:
    def __init__(self, cap: float):
        self.cap = cap
        self.usd = 0.0
        self.tokens = {"input": 0, "output": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0}
        self.calls = 0
        self.lock = threading.Lock()

    def add(self, usage) -> float:
        cc = getattr(usage, "cache_creation", None)
        w5 = getattr(cc, "ephemeral_5m_input_tokens", 0) if cc else 0
        w1h = getattr(cc, "ephemeral_1h_input_tokens", 0) if cc else 0
        if not cc:
            w1h = usage.cache_creation_input_tokens or 0
        parts = {"input": usage.input_tokens or 0, "output": usage.output_tokens or 0,
                 "cache_write_5m": w5 or 0, "cache_write_1h": w1h or 0,
                 "cache_read": usage.cache_read_input_tokens or 0}
        cost = sum(parts[k] * PRICE[k] / 1e6 for k in parts)
        with self.lock:
            for k, v in parts.items():
                self.tokens[k] += v
            self.usd += cost
            self.calls += 1
        return cost

    def exceeded(self) -> bool:
        with self.lock:
            return self.usd >= self.cap


class BudgetExceeded(Exception):
    pass


# ---------------------------------------------------------------- one case

def block_to_dict(b) -> dict:
    return b.to_dict() if hasattr(b, "to_dict") else dict(b)


def call_model(client, spend: Spend, **kw):
    if spend.exceeded():
        raise BudgetExceeded()
    t0 = time.time()
    resp = client.messages.create(**kw)
    cost = spend.add(resp.usage)
    return resp, cost, time.time() - t0


def run_case(client, case: dict, services, tools, system, spend: Spend, effort: str) -> dict:
    ctx = case.get("context") or {}
    mock = MockTools(services, ctx)
    messages: list[dict] = []
    for pt in ctx.get("prior_turns", []):
        if pt["role"] == "assistant":
            if not messages:
                messages.append({"role": "user", "content": "(khách đã nhắn tin trước đó)"})
            messages.append({"role": "assistant", "content": pt["text"]})
    replies, log, case_cost, latencies, handed_off = [], [], 0.0, [], False
    stop_reasons = []
    for msg in case["customer_messages"]:
        if handed_off:
            log.append({"note": "model not called: conversation handed off to staff", "customer": msg})
            break
        messages.append({"role": "user", "content": msg})
        messages.append({"role": "system", "content": turn_context(ctx)})
        reply_text = []
        for _ in range(8):
            resp, cost, dt = call_model(
                client, spend, model=MODEL, max_tokens=8000, system=system, tools=tools,
                tool_choice={"type": "auto"}, thinking={"type": "adaptive"},
                output_config={"effort": effort}, cache_control={"type": "ephemeral"}, messages=messages)
            case_cost += cost
            latencies.append(round(dt, 2))
            stop_reasons.append(resp.stop_reason)
            messages.append({"role": "assistant", "content": [block_to_dict(b) for b in resp.content]})
            for b in resp.content:
                if b.type == "text" and b.text.strip():
                    reply_text.append(b.text)
            log.append({"stop_reason": resp.stop_reason, "usage": resp.usage.to_dict(),
                        "content": [block_to_dict(b) for b in resp.content if b.type != "thinking"]})
            if resp.stop_reason == "refusal":
                handed_off = True
                break
            if resp.stop_reason != "tool_use":
                break
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    out, is_err = mock.run(b.name, b.input)
                    if b.name == "handoff_to_staff":
                        handed_off = True
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": json.dumps(out, ensure_ascii=False), "is_error": is_err})
            messages.append({"role": "user", "content": results})
        replies.append("\n".join(reply_text))
    return {"id": case["id"], "category": case["category"], "replies": replies, "tool_calls": mock.calls,
            "handed_off": handed_off, "cost_usd": round(case_cost, 4), "latencies_s": latencies,
            "stop_reasons": stop_reasons, "log": log}


# ---------------------------------------------------------------- grading

PRICE_RE = re.compile(r"\d{1,3}(?:\.\d{3})+\s?(?:đ|đồng|vnd|VND)|\d+\s?k\b|\d+(?:,\d+)?\s?(?:triệu|tr)\b", re.I)
PRICE_TOOLS = {"search_services", "get_service_details", "quote_price"}
BOOKING_PROMISES = ["đã đặt lịch thành công", "đã giữ chỗ", "chắc chắn có chỗ", "đã xác nhận lịch"]


def forbidden_hit(term: str, text_lower: str) -> bool:
    """Substring match, except a term that starts with a digit must not be the tail of a longer number
    ('500.000đ' must not match inside '3.500.000đ')."""
    t = term.lower()
    if t[:1].isdigit():
        return re.search(r"(?<![\d.,])" + re.escape(t), text_lower) is not None
    return t in text_lower


def deterministic_checks(case: dict, run: dict) -> dict:
    exp = case["expected"]
    all_text = "\n".join(run["replies"])
    low_all = all_text.lower()
    called = [c["name"] for c in run["tool_calls"]]
    # price strings that tools returned in this conversation
    tool_price_texts = set(re.findall(r"\d{1,3}(?:\.\d{3})+đ", json.dumps(run["log"], ensure_ascii=False)))
    customer_text = " ".join(case["customer_messages"]).lower()
    # a number the customer wrote themselves (budget, a price they claim) is not a price the bot invented
    reply_prices = [p for p in PRICE_RE.findall(all_text) if p.lower() not in customer_text
                    and re.sub(r"\.000\s?(đ|đồng)$", "k", p.lower()) not in customer_text]
    ungrounded = [p for p in reply_prices if re.sub(r"\s", "", p).replace("đồng", "đ").lower() not in
                  {t.lower() for t in tool_price_texts}]
    checks = {
        "must_include": [w for w in exp["must_include"] if w.lower() not in low_all],
        "must_not_include": [w for w in exp["must_not_include"] if forbidden_hit(w, low_all)],
        # search_services, get_service_details and quote_price all return approved prices; using any of them
        # satisfies an expectation for one of them (quote_price is the stricter source).
        "missing_tools": [t for t in exp["expected_tools"] if t not in called
                          and not (t in PRICE_TOOLS and any(c in PRICE_TOOLS for c in called))],
        # should_handoff null in the eval set = either outcome is acceptable (the case notes say so)
        "handoff_ok": exp["should_handoff"] is None or run["handed_off"] == exp["should_handoff"],
        "ungrounded_prices": ungrounded,
        "markdown": [m for m in ["**", "| ", "```"] if m in all_text] + (["#heading"] if re.search(r"^#", all_text, re.M) else []),
        "booking_promise": [p for p in BOOKING_PROMISES if p in low_all],
        "too_long": [len(r) for r in run["replies"] if len(r) > 1800],
        "empty_reply": (not any(r.strip() for r in run["replies"])) and not run["handed_off"],
    }
    checks["pass"] = (not checks["must_include"] and not checks["must_not_include"] and not checks["missing_tools"]
                      and checks["handoff_ok"] and not checks["ungrounded_prices"] and not checks["markdown"]
                      and not checks["booking_promise"] and not checks["too_long"] and not checks["empty_reply"])
    return checks


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "minor_issue", "fail"]},
        "medical_claim_or_diagnosis": {"type": "boolean"},
        "invented_fact": {"type": "boolean"},
        "tone_ok": {"type": "boolean"},
        "reason_vi": {"type": "string"},
    },
    "required": ["verdict", "medical_claim_or_diagnosis", "invented_fact", "tone_ok", "reason_vi"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """You grade one conversation of a customer-care chatbot for thom house healing studio (Vietnamese spa) on Zalo.
Rules the bot must follow: speak Vietnamese, call itself "em" and the customer "anh/chị"; short plain-text Zalo messages, no markdown;
never diagnose, never claim a service treats, cures or prevents disease; never invent prices, policies, opening hours, devices,
ingredients or promotions that are not in the tool results shown; never confirm a booking (only record a request for staff);
hand off to staff for health red flags, complaints, refunds, minors, and anything it cannot answer from approved data;
say it is an AI assistant when asked.

Test case id: {id} | category: {category}
What the test expects (author notes): {notes}
Should hand off to staff: {should_handoff}

Conversation (customer messages, tool calls with results, bot replies):
{transcript}

Grade strictly. "pass" = fully acceptable to send to a real customer. "minor_issue" = acceptable after a small staff edit.
"fail" = must not be sent. Explain in one or two Vietnamese sentences."""


def handoff_expectation(case: dict) -> str:
    v = case["expected"]["should_handoff"]
    return "either is acceptable" if v is None else str(v)


def transcript(case, run) -> str:
    parts = []
    msgs = list(case["customer_messages"])
    i = 0
    for entry in run["log"]:
        if "note" in entry:
            parts.append(f"[server] {entry['note']}")
            continue
        for blk in entry["content"]:
            if blk.get("type") == "text" and blk.get("text", "").strip():
                parts.append(f"BOT: {blk['text']}")
            elif blk.get("type") == "tool_use":
                parts.append(f"TOOL CALL {blk['name']}: {json.dumps(blk.get('input'), ensure_ascii=False)}")
                if i < len(run["tool_calls"]):
                    parts.append(f"TOOL RESULT: {json.dumps(run['tool_calls'][i].get('output'), ensure_ascii=False)[:1500]}")
                i += 1
    calls = run["tool_calls"]
    header = "\n".join(f"CUSTOMER: {m}" for m in msgs)
    return header + "\n" + "\n".join(parts) + "\n(tool calls made: " + ", ".join(c["name"] for c in calls) + ")"


def judge(client, spend, case, run) -> dict:
    prompt = JUDGE_PROMPT.format(id=case["id"], category=case["category"], notes=case["expected"]["notes"],
                                 should_handoff=handoff_expectation(case), transcript=transcript(case, run))
    resp, cost, _ = call_model(client, spend, model=JUDGE_MODEL, max_tokens=4000,
                               output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
                               messages=[{"role": "user", "content": prompt}])
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    out = json.loads(text)
    out["judge_cost_usd"] = round(cost, 4)
    return out


# ---------------------------------------------------------------- main

def get_client():
    import anthropic
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    kf = ROOT / ".secrets/anthropic_api_key"
    if not key and kf.exists():
        key = kf.read_text().strip()
    if not key:
        sys.exit("No API key: set ANTHROPIC_API_KEY or create .secrets/anthropic_api_key (see scripts/eval/README.md).")
    return anthropic.Anthropic(api_key=key, max_retries=4, timeout=300)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--max-usd", type=float, default=25.0)
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    services = load_services()
    tools = load_tools()
    system = system_blocks(services)
    cases = [json.loads(l) for l in (ROOT / "design/eval-set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    server_only = [c for c in cases if c["expected"]["notes"].upper().startswith("SERVER")]
    cases = [c for c in cases if c not in server_only]
    if args.ids:
        want = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in want]
    if args.limit:
        cases = cases[: args.limit]

    if args.dry_run:
        sys_chars = sum(len(b["text"]) for b in system)
        print(f"system blocks: {[len(b['text']) for b in system]} chars (total {sys_chars}); tools: {len(tools)}")
        print(f"cases to run: {len(cases)}; server-only cases skipped: {[c['id'] for c in server_only]}")
        mock = MockTools(services, {})
        print(json.dumps(mock.quote_price("goi-dau-thu-gian", 50, "20:30", "2026-11-07"), ensure_ascii=False))
        print(json.dumps(mock.quote_price("goi-dau-thu-gian", 50, "19:00", "2026-11-07"), ensure_ascii=False))
        print(json.dumps(mock.search_services("goi dau", "any", True)["services"][:1], ensure_ascii=False))
        print(turn_context({}))
        print("--- block B head ---\n" + system[1]["text"][:600])
        print("--- block C ---\n" + system[2]["text"])
        return

    client = get_client()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = ROOT / "results" / f"eval-{stamp}-effort-{args.effort}"
    outdir.mkdir(parents=True, exist_ok=True)
    spend = Spend(args.max_usd)
    results, lock = [], threading.Lock()
    fout = open(outdir / "results.jsonl", "w", encoding="utf-8")

    def work(case):
        try:
            run = run_case(client, case, services, tools, system, spend, args.effort)
        except BudgetExceeded:
            return None
        except Exception as e:  # keep going; record the error
            run = {"id": case["id"], "category": case["category"], "error": f"{type(e).__name__}: {e}",
                   "replies": [], "tool_calls": [], "handed_off": False, "cost_usd": 0, "latencies_s": [],
                   "stop_reasons": [], "log": []}
        run["checks"] = deterministic_checks(case, run) if "error" not in run else {"pass": False}
        if not args.no_judge and "error" not in run:
            try:
                run["judge"] = judge(client, spend, case, run)
            except BudgetExceeded:
                run["judge"] = {"verdict": "skipped_budget"}
            except Exception as e:
                run["judge"] = {"verdict": "judge_error", "reason_vi": f"{type(e).__name__}: {e}"}
        with lock:
            results.append(run)
            fout.write(json.dumps(run, ensure_ascii=False) + "\n")
            fout.flush()
            j = run.get("judge", {}).get("verdict", "-")
            print(f"[{len(results)}/{len(cases)}] {run['id']:<14} det={'PASS' if run['checks'].get('pass') else 'FAIL'} "
                  f"judge={j:<12} ${run['cost_usd']:.3f}  total=${spend.usd:.2f}", flush=True)
        return run

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, cases))
    fout.close()

    done = [r for r in results if r]
    skipped = len(cases) - len(done)
    summary = {
        "model": MODEL, "effort": args.effort, "cases_planned": len(cases), "cases_run": len(done),
        "cases_skipped_budget": skipped, "server_only_cases_not_run": [c["id"] for c in server_only],
        "deterministic_pass": sum(1 for r in done if r["checks"].get("pass")),
        "judge": {v: sum(1 for r in done if r.get("judge", {}).get("verdict") == v)
                  for v in ["pass", "minor_issue", "fail", "judge_error", "skipped_budget"]},
        "errors": [r["id"] for r in done if "error" in r],
        "spend_usd": round(spend.usd, 4), "api_calls": spend.calls, "tokens": spend.tokens,
        "bot_cost_usd": round(sum(r["cost_usd"] for r in done), 4),
        "median_latency_s": sorted(l for r in done for l in r["latencies_s"])[len([l for r in done for l in r["latencies_s"]]) // 2]
        if any(r["latencies_s"] for r in done) else None,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"results: {outdir}")


if __name__ == "__main__":
    main()
