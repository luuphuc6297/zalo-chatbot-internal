"""Post signed webhook events to the local server exactly as `zalo-agent listen --webhook` would (no Zalo account).

Wire format copied from @ardennguyen/zalo-agent-cli v2.5.9 (sources/repos/arden-zalo-agent-cli):
- Event body: src/commands/listen.js messageEvent() plus postWebhook(), i.e.
  JSON.stringify({accountId, event: "message", msgId, cliMsgId, threadId, type, isSelf, uidFrom, dName, msgType,
  content, catchUp?}). content is a string for text and an object for attachments (photo: msgType "chat.photo").
  For a self-sent DM, threadId is the customer and uidFrom/dName are the account owner (zca-js).
- Batch body (src/core/webhook-outbox.js post()): JSON.stringify({event: "batch", accountId, count, events}).
- Headers (webhookHeaders()): Content-Type: application/json, Authorization: Bearer <secret>,
  X-Zalo-Signature: sha256=<hex HMAC-SHA256 of the exact body bytes>, plus X-Zalo-Delivery and X-Zalo-Attempt.
- A redelivery re-posts the stored body bytes unchanged (--save-body / --replay, or --repeat).

Secret lookup order: --secret, env ZALO_PERSONAL_WEBHOOK_SECRET, apps/server/.dev.vars. The secret is never printed.

Real Zalo users are never messaged by default. The server queues its replies for the bridge, and with
scripts/start_local.sh running a real bridge would run `zalo-agent msg send` to the simulated thread id. So:
- the default thread id is "sim-9100123": not numeric, so the bridge refuses it ("invalid_item: thread_id must be a
  numeric Zalo user id"), reports "failed", and nothing is sent; the server retries a few times, then the row stays
  "failed" in the console;
- a numeric --thread (or a numeric threadId inside --replay) is refused while GET /bridge/status shows a bridge that
  claimed in the last 2 minutes, or when the status cannot be read; --allow-real-bridge overrides this.
The events are still written to the D1 database of the running server (~/.thomhouse-bot/d1): simulated customers
show up in the console with their "p:sim-..." id.

Examples (from the project root, with scripts/start_local.sh running):
  python3 -I scripts/simulate_personal_zalo.py --name "Chị Lan" --text "Chào em"
  python3 -I scripts/simulate_personal_zalo.py --thread sim-9100124 --text "đồng ý"
  python3 -I scripts/simulate_personal_zalo.py --image https://example.com/a.jpg
  python3 -I scripts/simulate_personal_zalo.py --self --msg-id 7100000000900 --text "Dạ ..."
  python3 -I scripts/simulate_personal_zalo.py --text "a" --text "b" --group-event          # one batch
  python3 -I scripts/simulate_personal_zalo.py --text "hi" --save-body /tmp/ev.json
  python3 -I scripts/simulate_personal_zalo.py --replay /tmp/ev.json --attempt 2           # redelivery
  python3 -I scripts/simulate_personal_zalo.py --text "hi" --bad-signature
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "apps" / "server"
FAKE_OWN_ID = "1000000000000001"      # fake account id; the server accepts any unless ZALO_PERSONAL_ACCOUNT_ID is set
OWNER_NAME = "thom house"
DEFAULT_THREAD = "sim-9100123"
NUMERIC_RE = re.compile(r"^[0-9]+$")
BRIDGE_ACTIVE_MS = 2 * 60 * 1000
_seq = itertools.count(int(time.time()) % 100000)


def read_dev_vars(name: str) -> str | None:
    f = SERVER_DIR / ".dev.vars"
    if not f.exists():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    return None


def js_stringify(obj: object) -> str:
    """JSON.stringify(obj): no spaces, non-ASCII kept as UTF-8, key order preserved."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def headers_for(body: bytes, secret: str, attempt: int, delivery: str, bad_signature: bool) -> dict[str, str]:
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if bad_signature:
        sig = "0" * len(sig)
    return {"Content-Type": "application/json", "Authorization": f"Bearer {secret}",
            "X-Zalo-Signature": f"sha256={sig}", "X-Zalo-Delivery": delivery, "X-Zalo-Attempt": str(attempt)}


def new_msg_id() -> str:
    # zca-js msgIds are numeric strings; time-based so repeated runs do not collide.
    return str(int(time.time() * 1000) * 1000 + next(_seq) % 1000)


def message_event(args: argparse.Namespace, *, text: str | None = None, image: str | None = None,
                  sticker: bool = False, msg_id: str | None = None, thread: str | None = None,
                  group: bool = False) -> dict:
    thread_id = thread or args.thread
    self_sent = bool(args.self_sent) and not group
    if image:
        msg_type = "chat.photo"
        content: object = {"title": "", "description": "", "href": image, "thumb": image, "childnumber": 0,
                           "action": "", "params": json.dumps({"width": 1280, "height": 960}), "type": ""}
    elif sticker:
        msg_type = "chat.sticker"
        content = {"id": 21979, "catId": 10425, "type": 7}
    else:
        msg_type = "webchat"
        content = text if text is not None else ""
    ev: dict = {"accountId": args.account_id, "event": "message", "msgId": msg_id or new_msg_id(),
                "cliMsgId": args.cli_msg_id or str(int(time.time() * 1000)), "threadId": thread_id,
                "type": 1 if group else 0, "isSelf": self_sent,
                "uidFrom": args.account_id if self_sent else (args.group_sender if group else thread_id),
                "dName": OWNER_NAME if self_sent else (args.name or "Khách thử"), "msgType": msg_type,
                "content": content}
    if args.catch_up:
        ev["catchUp"] = True
    return ev


def build_body(args: argparse.Namespace) -> bytes:
    events: list[dict] = []
    texts = args.text or []
    for i, t in enumerate(texts):
        events.append(message_event(args, text=t, msg_id=args.msg_id if (args.msg_id and i == 0) else None))
    if args.image:
        events.append(message_event(args, image=args.image, msg_id=args.msg_id if not texts else None))
    if args.sticker:
        events.append(message_event(args, sticker=True))
    if args.group_event:
        events.insert(0, message_event(args, text="tin trong nhóm (phải bị bỏ qua)", thread=args.group_thread,
                                       group=True))
    if args.reaction:
        events.append({"accountId": args.account_id, "event": "reaction", "threadId": args.thread,
                       "isSelf": False, "icon": "/-heart"})
    if not events:
        raise SystemExit("nothing to send: pass --text, --image, --sticker or --replay")
    if len(events) == 1 and not args.batch:
        return js_stringify(events[0]).encode("utf-8")
    # Engine batch: events are the stored single-event bodies, each already carrying accountId.
    return js_stringify({"event": "batch", "accountId": args.account_id, "count": len(events),
                         "events": events}).encode("utf-8")


def dm_thread_ids(body: bytes) -> list[str]:
    """threadIds of the 1-1 message events in a body (single event or batch)."""
    try:
        top = json.loads(body)
    except ValueError:
        return []
    events = top.get("events") if isinstance(top, dict) and top.get("event") == "batch" else [top]
    out = []
    for ev in events if isinstance(events, list) else []:
        if isinstance(ev, dict) and ev.get("event") == "message" and int(ev.get("type") or 0) == 0 and ev.get("threadId"):
            out.append(str(ev["threadId"]))
    return out


def bridge_activity(webhook_url: str) -> tuple[bool | None, str]:
    """(True if a bridge claimed within 2 minutes, False if not, None if unknown; detail). Reads GET /bridge/status
    of the same server with STAFF_TOKEN (env, then apps/server/.dev.vars). The token is never printed."""
    token = (os.environ.get("STAFF_TOKEN") or read_dev_vars("STAFF_TOKEN") or "").strip()
    if not token:
        return None, "STAFF_TOKEN not found, so /bridge/status cannot be read"
    u = urllib.parse.urlsplit(webhook_url)
    url = urllib.parse.urlunsplit((u.scheme, u.netloc, "/bridge/status", "", ""))
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "thomhouse-sim/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            st = json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"/bridge/status unreadable ({type(e).__name__})"
    last = st.get("last_claim_at") if isinstance(st, dict) else None
    if isinstance(last, (int, float)) and time.time() * 1000 - last < BRIDGE_ACTIVE_MS:
        return True, "a bridge claimed from the outbox in the last 2 minutes"
    return False, "no bridge claimed in the last 2 minutes"


def guard_real_sends(webhook_url: str, body: bytes, allow: bool) -> str | None:
    """Error text when posting this body could make a running bridge message a real Zalo user, else None."""
    numeric = [t for t in dm_thread_ids(body) if NUMERIC_RE.match(t)]
    if not numeric or allow:
        return None
    active, detail = bridge_activity(webhook_url)
    if active is False:
        return None
    return (f"refused: numeric thread id ...{numeric[0][-4:]} could be a real Zalo user, and {detail}. The server "
            f"would queue replies that the bridge sends for real. Use a non-numeric id such as {DEFAULT_THREAD}, stop "
            "the bridge, or pass --allow-real-bridge if this id is yours.")


def post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Simulate zalo-agent listen webhook deliveries (personal Zalo).")
    p.add_argument("--url", default="http://127.0.0.1:8787/zalo/personal/webhook")
    p.add_argument("--secret", default=None, help="default: env ZALO_PERSONAL_WEBHOOK_SECRET, then .dev.vars")
    p.add_argument("--thread", default=DEFAULT_THREAD,
                   help=f"customer threadId (default {DEFAULT_THREAD}: not numeric, so a running bridge never sends to it)")
    p.add_argument("--name", default=None, help="customer display name (dName)")
    p.add_argument("--text", action="append", help="text message; repeat for several events in one batch")
    p.add_argument("--image", default=None, help="photo URL: a chat.photo event")
    p.add_argument("--sticker", action="store_true", help="a chat.sticker event")
    p.add_argument("--self", dest="self_sent", action="store_true",
                   help="self-sent message (an echo of the bridge, or staff typing on the phone)")
    p.add_argument("--msg-id", default=None, help="msgId of the (first) event; default: new time-based id")
    p.add_argument("--cli-msg-id", default=None)
    p.add_argument("--catch-up", action="store_true", help="mark as a catch-up event (catchUp: true)")
    p.add_argument("--group-event", action="store_true", help="add a group-thread event (type 1) to the body")
    p.add_argument("--group-thread", default="5550001")
    p.add_argument("--group-sender", default="9100999")
    p.add_argument("--reaction", action="store_true", help="add a non-message event (reaction)")
    p.add_argument("--batch", action="store_true", help="send as a batch even with one event")
    p.add_argument("--account-id", default=FAKE_OWN_ID)
    p.add_argument("--attempt", type=int, default=1, help="X-Zalo-Attempt header")
    p.add_argument("--repeat", type=int, default=1, help="post the same bytes N times (redelivery)")
    p.add_argument("--save-body", default=None, help="write the exact body bytes to this file")
    p.add_argument("--replay", default=None, help="post the body bytes saved with --save-body")
    p.add_argument("--bad-signature", action="store_true")
    p.add_argument("--allow-real-bridge", action="store_true",
                   help="post a numeric thread id even while a bridge is claiming (it may message that Zalo user)")
    args = p.parse_args(argv)

    secret = (args.secret or os.environ.get("ZALO_PERSONAL_WEBHOOK_SECRET")
              or read_dev_vars("ZALO_PERSONAL_WEBHOOK_SECRET") or "").strip()
    if not secret:
        print("ZALO_PERSONAL_WEBHOOK_SECRET not found (env or apps/server/.dev.vars)", file=sys.stderr)
        return 2
    body = Path(args.replay).read_bytes() if args.replay else build_body(args)
    refusal = guard_real_sends(args.url, body, args.allow_real_bridge)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3
    if args.save_body:
        Path(args.save_body).write_bytes(body)
    seq = next(_seq)
    status = 0
    for i in range(max(1, args.repeat)):
        h = headers_for(body, secret, args.attempt + i, f"{seq}-{seq}", args.bad_signature)
        status, text = post(args.url, body, h)
        try:
            shown = json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError:
            shown = text[:500]
        print(f"HTTP {status} {shown}")
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
