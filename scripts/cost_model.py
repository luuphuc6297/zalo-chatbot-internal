#!/usr/bin/env python3
"""Monthly Claude API cost model for the thom house Zalo OA chatbot.

Pure Python, no dependencies, no network. Run:
    python3 scripts/cost_model.py            # human-readable tables
    python3 scripts/cost_model.py --json     # machine-readable results

All prices are USD per million tokens, copied from
https://platform.claude.com/docs/en/about-claude/pricing (accessed 2026-11-07).
FX rate: Vietcombank USD sell rate 25,780 VND, table dated 2026-11-07
(https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx).

Token sizes below are ESTIMATES, not measurements. Vietnamese token counts for
the current Claude tokenizer were not measured (that requires the
/v1/messages/count_tokens endpoint, which this research did not call).
"""

import json
import math
import os
import sys

# ---------------------------------------------------------------------------
# Prices (USD / MTok), Claude API first-party, global inference_geo.
# ---------------------------------------------------------------------------
PRICES = {
    # model: base input, 5m cache write, 1h cache write, cache read, output
    "claude-opus-5-5": {"in": 4.00, "w5m": 5.00, "w1h": 8.00, "read": 0.20, "out": 20.00},
    "claude-sonnet-5-5": {"in": 2.00, "w5m": 2.50, "w1h": 4.00, "read": 0.10, "out": 10.00},
    # Haiku 5.5 prices for prompts up to 100,000 tokens (our Haiku prompts are tiny).
    "claude-haiku-5-5": {"in": 0.10, "w5m": 0.125, "w1h": 0.20, "read": 0.01, "out": 0.50},
}
BATCH_DISCOUNT = 0.5          # Message Batches API: 50% off input and output
US_GEO_MULTIPLIER = 1.1       # only if inference_geo="us"; model uses global (1.0)

FX_VND_PER_USD = 25_780       # Vietcombank sell rate, 2026-11-07
VAT_RATE = 0.10               # inference from indirect evidence; see report section on VAT
MONTHLY_API_CREDIT_USD = {"Max": 100, "Ultra": 200}

# ---------------------------------------------------------------------------
# Knowledge-block size estimate from the Drive mirror (characters measured,
# tokens estimated with a chars-per-token range for Vietnamese text).
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MENU_FILES = [
    "sources/drive/knowledge-base/02-services/README.md",
    "sources/drive/knowledge-base/02-services/relaxation-menu.md",
    "sources/drive/knowledge-base/02-services/health-menu.md",
    "sources/drive/knowledge-base/02-services/women-health-menu.md",
    "sources/drive/knowledge-base/02-services/skincare-menu.md",
    "sources/drive/knowledge-base/02-services/hair-care-menu.md",
    "sources/drive/knowledge-base/03-pricing-structure.md",
]
SERVICES_JSON = "data/services.json"
CHARS_PER_TOKEN_RANGE = (2.5, 3.5)   # assumption for Vietnamese with diacritics


def measure_knowledge_block():
    """Return measured characters and an estimated token range."""
    path = os.path.join(ROOT, SERVICES_JSON)
    files = [SERVICES_JSON] if os.path.exists(path) else MENU_FILES
    chars = 0
    found = []
    for rel in files:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                chars += len(fh.read())
            found.append(rel)
    lo = int(chars / CHARS_PER_TOKEN_RANGE[1])
    hi = int(chars / CHARS_PER_TOKEN_RANGE[0])
    return {"source_files": found, "chars": chars, "tokens_low": lo, "tokens_high": hi}


# ---------------------------------------------------------------------------
# Workload assumptions (per conversation). Each customer turn = 2 model calls:
#   1) guard / intent call (on Opus in "opus_only", on Haiku in "routed")
#   2) answer call on Opus (may include one tool round trip folded in)
# So N calls per conversation = 2 * turns.
# ---------------------------------------------------------------------------
TOOLS_TOKENS = 1_500          # tool definitions, part of the cached prefix
RULES_TOKENS = 5_000          # persona, safety rules, response format (system prompt)
FIRST_MSG_TOKENS = 80         # first customer message
USER_MSG_TOKENS = 60          # each later customer message (Zalo messages are short)
TOOL_ROUNDTRIP_TOKENS = 380   # tool_use block + tool_result (e.g. availability lookup)

OUTPUT_PROFILES = {
    # visible answer, thinking (billed as output; Opus 5.5 thinking cannot be disabled)
    "base": {"answer_visible": 350, "answer_thinking": 400, "guard_visible": 60, "guard_thinking": 150},
    "high": {"answer_visible": 600, "answer_thinking": 1_200, "guard_visible": 80, "guard_thinking": 300},
}

HAIKU_GUARD_PROMPT = 2_000    # small guard prompt (below Haiku cache minimum; billed as base input)
HAIKU_GUARD_HISTORY = 1_000   # last few messages passed to the guard

OPEN_HOURS_PER_DAY = 15       # 9h-24h per bundle header (hours still to be confirmed, claim K8)
DAYS_PER_MONTH = 30
HIST_CACHE_HIT = 0.7          # share of turns where the customer replies within the 5-minute TTL

FOLLOWUP_INPUT = 2_500        # per follow-up draft: customer summary + promo rules, no full menu
FOLLOWUP_OUTPUT = 250 + 300   # visible + thinking
FOLLOWUPS_PER_CONV = 1


def p_static_write(conv_per_month, ttl_hours):
    """Probability that a conversation start finds the shared prefix cache cold.

    Conversation starts are modelled as a Poisson process spread evenly over
    open hours. A cache hit refreshes the TTL at no extra cost, so the prefix
    is cold only if no conversation started within the previous TTL window.
    """
    lam = conv_per_month / DAYS_PER_MONTH / OPEN_HOURS_PER_DAY  # starts per hour
    return math.exp(-lam * ttl_hours)


def cost_tokens(model, base_in=0, w5m=0, w1h=0, read=0, out=0, batch=False):
    p = PRICES[model]
    usd = (base_in * p["in"] + w5m * p["w5m"] + w1h * p["w1h"] + read * p["read"] + out * p["out"]) / 1e6
    return usd * (BATCH_DISCOUNT if batch else 1.0)


def conversation_cost(n_calls, static_tokens, mode, profile, conv_per_month, static_ttl="1h"):
    """USD cost of one average conversation (chat part only)."""
    o = OUTPUT_PROFILES[profile]
    turns = n_calls // 2
    prefix = TOOLS_TOKENS + RULES_TOKENS + static_tokens
    cached = not mode.endswith("nocache")
    routed = mode.startswith("routed")
    ttl_h = 1.0 if static_ttl == "1h" else 5 / 60
    p_cold = p_static_write(conv_per_month, ttl_h) if cached else 1.0
    wkey = "w1h" if static_ttl == "1h" else "w5m"

    usd = 0.0
    history = FIRST_MSG_TOKENS
    prev_history_cached = 0  # history tokens already in cache from the previous Opus call
    tokens = {"opus_in_total": 0, "opus_out_total": 0, "haiku_in_total": 0, "haiku_out_total": 0}

    for t in range(turns):
        opus_calls = [("answer", o["answer_visible"] + o["answer_thinking"])]
        if not routed:
            opus_calls.insert(0, ("guard", o["guard_visible"] + o["guard_thinking"]))
        for kind, out_tokens in opus_calls:
            hist_in = history + (TOOL_ROUNDTRIP_TOKENS if kind == "answer" else 0)
            tokens["opus_in_total"] += prefix + hist_in
            tokens["opus_out_total"] += out_tokens
            if not cached:
                usd += cost_tokens("claude-opus-5-5", base_in=prefix + hist_in, out=out_tokens)
                continue
            # Shared prefix: cold only for the first call of a conversation.
            first_call = (t == 0 and kind == opus_calls[0][0])
            if first_call:
                static_part = {wkey: prefix * p_cold, "read": prefix * (1 - p_cold)}
            else:
                static_part = {"read": prefix}
            # History: tokens seen in an earlier call are read if the 5m cache is still warm.
            if kind == "guard" or (routed and kind == "answer"):
                hit = HIST_CACHE_HIT if t > 0 else 1.0
            else:  # answer call right after the Opus guard call: seconds apart
                hit = 1.0
            reread = prev_history_cached * hit
            rewrite = prev_history_cached * (1 - hit)
            new = hist_in - prev_history_cached
            w5 = rewrite + new + static_part.get("w5m", 0)
            w1 = static_part.get("w1h", 0)
            usd += cost_tokens("claude-opus-5-5", w5m=w5, w1h=w1,
                               read=static_part["read"] + reread, out=out_tokens)
            prev_history_cached = hist_in
        if routed:
            hin = HAIKU_GUARD_PROMPT + min(history, HAIKU_GUARD_HISTORY)
            hout = o["guard_visible"] + o["guard_thinking"]
            tokens["haiku_in_total"] += hin
            tokens["haiku_out_total"] += hout
            usd += cost_tokens("claude-haiku-5-5", base_in=hin, out=hout)
        # History grows with the answer (visible + thinking kept by Opus 5.5),
        # the tool round trip and the next customer message.
        history += o["answer_visible"] + o["answer_thinking"] + TOOL_ROUNDTRIP_TOKENS + USER_MSG_TOKENS
    return usd, tokens


def followup_cost():
    return FOLLOWUPS_PER_CONV * cost_tokens("claude-opus-5-5", base_in=FOLLOWUP_INPUT,
                                            out=FOLLOWUP_OUTPUT, batch=True)


def prior_report_check():
    """Reproduce claim C2: 1,000 conv x 6 calls, flat tokens, no caching."""
    calls = 1_000 * 6
    a = calls * cost_tokens("claude-opus-5-5", base_in=2_000, out=400)
    b = calls * cost_tokens("claude-opus-5-5", base_in=6_000, out=800)
    return round(a, 2), round(b, 2)


MODES = ["opus_nocache", "opus_cache", "routed_nocache", "routed_cache"]


def run():
    kb = measure_knowledge_block()
    results = []
    static_options = {"15k (compact services.json)": 15_000,
                      f"{kb['tokens_high']//1000}k (full menu markdown, high estimate)": kb["tokens_high"]}
    for conv in (300, 1_000, 3_000):
        for n in (4, 6, 8):
            for s_label, s_tokens in static_options.items():
                for profile in OUTPUT_PROFILES:
                    for mode in MODES:
                        per_conv, tok = conversation_cost(n, s_tokens, mode, profile, conv)
                        chat = per_conv * conv
                        fu = followup_cost() * conv
                        total = chat + fu
                        results.append({
                            "conversations": conv, "calls_per_conv": n, "static_block": s_label,
                            "static_tokens": s_tokens, "output_profile": profile, "mode": mode,
                            "usd_chat": round(chat, 2), "usd_followup_batch": round(fu, 2),
                            "usd_total": round(total, 2),
                            "vnd_total": round(total * FX_VND_PER_USD),
                            "vnd_total_with_vat": round(total * FX_VND_PER_USD * (1 + VAT_RATE)),
                            "ultra_credit_share": round(total / MONTHLY_API_CREDIT_USD["Ultra"], 2),
                            "opus_input_tokens_per_conv": tok["opus_in_total"],
                            "opus_output_tokens_per_conv": tok["opus_out_total"],
                        })
    ttl_compare = []
    for conv in (300, 1_000, 3_000):
        for ttl in ("5m", "1h"):
            per_conv, _ = conversation_cost(6, 15_000, "routed_cache", "base", conv, static_ttl=ttl)
            ttl_compare.append({"conversations": conv, "static_ttl": ttl,
                                "p_cold_start": round(p_static_write(conv, 1.0 if ttl == "1h" else 5 / 60), 3),
                                "usd_chat": round(per_conv * conv, 2)})
    return {"knowledge_block": kb, "fx_vnd_per_usd": FX_VND_PER_USD, "vat_rate": VAT_RATE,
            "prior_report_C2": prior_report_check(), "results": results, "ttl_compare": ttl_compare}


def fmt_usd(x):
    return f"{x:>8.2f}"


def main():
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    kb = out["knowledge_block"]
    print("Knowledge block measured:", kb["chars"], "chars from", len(kb["source_files"]), "files;",
          f"estimated {kb['tokens_low']:,}-{kb['tokens_high']:,} tokens (chars/token {CHARS_PER_TOKEN_RANGE})")
    print("FX:", FX_VND_PER_USD, "VND/USD (Vietcombank sell, 2026-11-07); VAT shown separately at", VAT_RATE)
    a, b = out["prior_report_C2"]
    print(f"Prior report C2 reproduced: {a} USD and {b} USD\n")

    for s_label in sorted({r["static_block"] for r in out["results"]}, key=lambda x: int(x.split('k')[0])):
        for profile in OUTPUT_PROFILES:
            print(f"== static block {s_label}, output profile '{profile}' -- USD/month incl. batch follow-ups ==")
            print(f"{'conv':>6} {'N':>3} " + " ".join(f"{m:>15}" for m in MODES) + f" {'best VND':>14} {'best/Ultra$200':>15}")
            for conv in (300, 1_000, 3_000):
                for n in (4, 6, 8):
                    row = {r["mode"]: r for r in out["results"]
                           if r["conversations"] == conv and r["calls_per_conv"] == n
                           and r["static_block"] == s_label and r["output_profile"] == profile}
                    best = row["routed_cache"]
                    print(f"{conv:>6} {n:>3} " + " ".join(f"{row[m]['usd_total']:>15.2f}" for m in MODES)
                          + f" {best['vnd_total']:>14,} {best['ultra_credit_share']:>15.2f}")
            print()
    print("== static-prefix TTL comparison (routed_cache, N=6, 15k block, base) ==")
    for r in out["ttl_compare"]:
        print(f"conv={r['conversations']:>5} ttl={r['static_ttl']:>3} p_cold_start={r['p_cold_start']:<6} chat_usd={r['usd_chat']}")


if __name__ == "__main__":
    main()
