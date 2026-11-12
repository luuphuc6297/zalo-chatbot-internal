"""Post a signed fake Zalo OA webhook event to the local backend (no real Zalo account needed).

Signature = "mac=" + sha256(app_id + raw_body + timestamp + OA secret), the formula documented by Zalo
(research/03-zalo-oa-platform.md); apps/server/src/lib/zalo-signature.ts verifies the same formula.
The formula is unverified on a real OA, so this only proves the two sides of THIS codebase agree.

Secret lookup order: --secret, env ZALO_OA_SECRET_KEY, apps/server/.dev.vars, apps/server/.dev.vars.example.
The secret is never printed.

Examples (run from the project root, with `pnpm dev:server` running):
  python3 -I scripts/simulate_zalo.py --text "gội đầu bao nhiêu tiền ạ"
  python3 -I scripts/simulate_zalo.py --user 1001 --text "#dong_y_tro_ly_ai"        # consent button payload
  python3 -I scripts/simulate_zalo.py --image https://example.com/a.jpg --text "da em thế này"
  python3 -I scripts/simulate_zalo.py --event oa_send_text --admin-id 42 --text "chị ơi em là nhân viên"
  python3 -I scripts/simulate_zalo.py --text "hi" --repeat 2                          # same body twice: dedup test
  python3 -I scripts/simulate_zalo.py --text "hi" --bad-signature                     # observe vs enforce
  python3 -I scripts/simulate_zalo.py --event user_send_sticker                       # sticker (no text)
  python3 -I scripts/simulate_zalo.py --event user_send_location                      # location attachment
  python3 -I scripts/simulate_zalo.py --event follow --user 1001                      # follow / unfollow
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "apps" / "server"


def read_dev_vars(name: str) -> str | None:
    for f in (SERVER_DIR / ".dev.vars", SERVER_DIR / ".dev.vars.example"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return None


def signature(app_id: str, raw_body: str, timestamp: str, secret: str) -> str:
    return "mac=" + hashlib.sha256((app_id + raw_body + timestamp + secret).encode("utf-8")).hexdigest()


def build_event(args: argparse.Namespace, ts: str) -> dict:
    if args.event in ("follow", "unfollow"):
        # follow/unfollow carry oa_id + follower.id and no msg_id (server dedupes on sha256 of the body).
        return {"oa_id": args.oa, "follower": {"id": args.user}, "user_id_by_app": f"app_{args.user}",
                "event_name": args.event, "source": "oa_profile", "app_id": args.app_id, "timestamp": ts}
    msg_id = args.msg_id or secrets.token_hex(10)
    message: dict = {"msg_id": msg_id}
    if args.event == "user_send_sticker":
        message["attachments"] = [{"type": "sticker", "payload": {"id": "sticker1", "url": "https://example.com/s.png"}}]
    elif args.event == "user_send_location":
        message["attachments"] = [{"type": "location",
                                   "payload": {"coordinates": {"latitude": "10.7642473", "longitude": "106.6564314"}}}]
    elif args.event == "user_send_link":
        message["text"] = args.text or ""
        message["attachments"] = [{"type": "link", "payload": {"url": args.link or "https://example.com",
                                                               "description": "link", "thumbnail": ""}}]
    elif args.event == "user_send_image":
        message["text"] = args.text or ""
        message["attachments"] = [{"type": "image", "payload": {"url": args.image, "thumbnail": args.image}}]
    else:
        message["text"] = args.text
    if args.event.startswith("oa_send_"):
        # OA -> user: sender is the OA, recipient is the customer.
        sender = {"id": args.oa}
        if args.admin_id:
            sender["admin_id"] = args.admin_id
        return {"app_id": args.app_id, "sender": sender, "recipient": {"id": args.user},
                "event_name": args.event, "message": message, "timestamp": ts}
    return {"app_id": args.app_id, "sender": {"id": args.user}, "user_id_by_app": f"app_{args.user}",
            "recipient": {"id": args.oa}, "event_name": args.event, "message": message, "timestamp": ts}


def post(url: str, raw: str, sig: str, num_retry: int | None) -> tuple[int, str]:
    headers = {"Content-Type": "application/json", "X-ZEvent-Signature": sig, "User-Agent": "thomhouse-simulator/1.0"}
    if num_retry is not None:
        headers["num_retry"] = str(num_retry)
    req = urllib.request.Request(url, data=raw.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8787/zalo/webhook")
    ap.add_argument("--user", default="2468458835291979", help="customer Zalo user id (sender.id)")
    ap.add_argument("--text", default="", help="message text")
    ap.add_argument("--image", help="image URL; switches the event to user_send_image")
    ap.add_argument("--event", default="user_send_text",
                    choices=["user_send_text", "user_send_image", "user_send_sticker", "user_send_link",
                             "user_send_location", "oa_send_text", "follow", "unfollow"])
    ap.add_argument("--link", help="URL for --event user_send_link")
    ap.add_argument("--admin-id", help="sender.admin_id for oa_send_text (staff replying from OA Manager)")
    ap.add_argument("--msg-id", help="fixed message.msg_id (default random)")
    ap.add_argument("--oa", default=None, help="OA id (default ZALO_OA_ID from .dev.vars)")
    ap.add_argument("--app-id", default=None, help="app id (default ZALO_APP_ID from .dev.vars)")
    ap.add_argument("--secret", default=None, help="OA secret key (default ZALO_OA_SECRET_KEY from env/.dev.vars)")
    ap.add_argument("--repeat", type=int, default=1, help="post the identical body N times (dedup test)")
    ap.add_argument("--num-retry", type=int, default=None, help="add Zalo's num_retry header")
    ap.add_argument("--bad-signature", action="store_true", help="send a wrong signature")
    args = ap.parse_args()

    if args.image:
        args.event = "user_send_image"
    if args.event in ("user_send_text", "oa_send_text") and not args.text:
        ap.error("--text is required for text events (or use --image / another --event)")
    args.oa = args.oa or read_dev_vars("ZALO_OA_ID") or "dev-oa-id"
    args.app_id = args.app_id or read_dev_vars("ZALO_APP_ID") or "dev-app-id"
    secret = args.secret or os.environ.get("ZALO_OA_SECRET_KEY") or read_dev_vars("ZALO_OA_SECRET_KEY")
    if not secret:
        ap.error("no OA secret found; pass --secret or create apps/server/.dev.vars")

    ts = str(int(time.time() * 1000))
    event = build_event(args, ts)
    raw = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    sig = signature(args.app_id, raw, ts, secret + ("x" if args.bad_signature else ""))

    rc = 0
    for i in range(args.repeat):
        status, body = post(args.url, raw, sig, args.num_retry)
        print(json.dumps({"attempt": i + 1, "status": status, "event_name": event["event_name"],
                          "msg_id": event.get("message", {}).get("msg_id"), "response": body[:500]},
                         ensure_ascii=False))
        if status >= 400:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
