"""Send one text through `zalo-agent --json [--account X] msg send -t 0 -- <threadId> <text>` and classify it.

What the engine prints (src/commands/msg.js, src/utils/output.js, v2.5.9):
- success: the zca-js answer, e.g. {"message": {"msgId": 7100000000900, "cliMsgId": "..."}, "attachment": [],
  "cliMsgId": "..."}; a text over 3000 bytes is split and also carries "splitInto" and "parts".
- failure: {"error": "<message>"}, usually with exit code 0 (the send action catches and prints).
- not logged in: {"error": "Not logged in. Run: zalo-agent login"} (stderr may also say "AutoLogin failed").
- a part after the first failing: "... (part 2 of 3 failed; the 1 earlier part(s) were already delivered)".
- commander usage errors: "error: ..." on stderr, exit 1, no JSON (nothing was sent).
A text send does its own HTTP login and send; it does not open a second WebSocket, so it runs fine beside the
`listen` daemon (only uploads are routed through the daemon channel).

Classification (the outcome posted to /bridge/outbox/:id/result):
- sent:    JSON with message.msgId
- failed:  an explicit refusal, nothing went out: not logged in, invalid thread id, a Zalo error answer, a usage
           error, the executable missing
- unknown: timeout, cancelled mid-send, transport errors after the request may have left, a partial split send,
           output that is not the expected JSON, and two zca-js errors raised only after Zalo answered: "Failed to
           parse response data" (HTTP 200 whose body could not be decoded: the message may be delivered) and
           "Request failed with status code 5xx". The server never retries "unknown"; staff decides.
A split send (text over ~3000 bytes) also reports every part's msgId (`parts[].msgId`) as part_msg_ids, so the
server matches each part's echo by id.

Menu images (outbox kind cs_images): `zalo-agent --json [--account X] msg send-image -t 0 --upload-timeout <ms> --
<threadId> <jpg...>` (src/commands/msg.js v2.5.9). JPEGs take zca-js's inline-image path: HTTP upload and send, no
WebSocket, so it runs beside the listen daemon. zca-js uploads every file first, then sends one message per image in
parallel; success prints the zca-js answer plus `sent: [{msgId, cliMsgId}]` (one per image, from `attachment`),
failure prints {"error": ...} with exit code 1. Classification:
- sent:    `sent` (or `attachment`) carries msgIds; zalo_msg_id = the first, part_msg_ids = all of them
- failed:  keys that do not resolve to verified files (nothing runs), not logged in, the engine's own refusals before
           any upload (too many files, file too large, file missing, missing arguments), a usage error, and a Zalo
           error answer for a single image
- unknown: timeout, cancel, transport errors, garbled output, JSON without msgIds, and a Zalo error answer when more
           than one image was sent (earlier images of the same call may already be delivered)
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from .config import Config
from .engine import EngineResult, run_engine
from .menu_images import MenuImageError, resolve as resolve_menu_images

THREAD_ID_RE = re.compile(r"^[0-9]{1,40}$")
NOT_LOGGED_IN_RE = re.compile(r"not logged in|no active account|no saved credentials|please login|"
                              r"autologin failed|session was revoked|đăng nhập thất bại", re.I)
PARTIAL_RE = re.compile(r"part \d+ of \d+ failed", re.I)
# Errors after which the request may already have reached Zalo.
AMBIGUOUS_RE = re.compile(r"timed? ?out|etimedout|econnreset|socket hang up|other side closed|aborted|epipe|"
                          r"und_err_socket|network error|fetch failed|terminated|"
                          # zca-js handleZaloResponse: errors after Zalo already received the request
                          r"failed to parse response|status code 5\d\d", re.I)
MAX_ERROR_LEN = 300
MSG_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
# send-image refusals raised before any file is uploaded (zca-js sendMessage / uploadAttachment, fs): nothing went out.
IMAGE_PRESEND_RE = re.compile(r"exceed maximum file|size exceed maximum|enoent|no such file|missing attachments|"
                              r"missing threadid|missing message content|could not open the upload channel", re.I)


def _part_ids(data: dict) -> list[str] | None:
    """parts[].msgId of a split send (src/commands/msg.js); None when the text went out in one message."""
    parts = data.get("parts")
    if not isinstance(parts, list) or len(parts) < 2:
        return None
    ids = [str(p.get("msgId")) for p in parts if isinstance(p, dict) and p.get("msgId") not in (None, "")]
    ids = [i for i in ids if MSG_ID_RE.match(i)][:50]
    return ids or None


@dataclass
class SendOutcome:
    status: str                         # sent | failed | unknown
    zalo_msg_id: str | None = None
    error: str | None = None
    login_required: bool = False
    part_msg_ids: list[str] | None = None   # split send: msgId of every part, first part included

    def result_body(self) -> dict:
        body: dict = {"status": self.status}
        if self.zalo_msg_id:
            body["zalo_msg_id"] = self.zalo_msg_id
        if self.part_msg_ids:
            body["part_msg_ids"] = list(self.part_msg_ids)
        if self.error:
            body["error"] = self.error
        return body


def _short(kind: str, detail: str | None = None) -> str:
    text = kind if not detail else f"{kind}: {' '.join(detail.split())}"
    return text[:MAX_ERROR_LEN]


def classify(res: EngineResult) -> SendOutcome:
    if res.missing:
        return SendOutcome("failed", error=_short("engine_missing", res.stderr))
    if res.cancelled:
        return SendOutcome("unknown", error=_short("cancelled", "bridge stopped while zalo-agent was sending"))
    if res.timed_out:
        return SendOutcome("unknown", error=_short("timeout", "zalo-agent did not finish in time"))
    data = res.data
    if isinstance(data, dict):
        err = res.error_text
        if err is not None:
            if PARTIAL_RE.search(err):
                return SendOutcome("unknown", error=_short("partial_send", err))
            if NOT_LOGGED_IN_RE.search(err) or NOT_LOGGED_IN_RE.search(res.stderr or ""):
                return SendOutcome("failed", error=_short("not_logged_in", err), login_required=True)
            if AMBIGUOUS_RE.search(err):
                return SendOutcome("unknown", error=_short("transport_error", err))
            return SendOutcome("failed", error=_short("zalo_error", err))
        msg = data.get("message")
        msg_id = msg.get("msgId") if isinstance(msg, dict) else None
        if msg_id not in (None, ""):
            return SendOutcome("sent", zalo_msg_id=str(msg_id), part_msg_ids=_part_ids(data))
        return SendOutcome("unknown", error=_short("no_msg_id", f"exit {res.returncode}, JSON without message.msgId"))
    stderr = (res.stderr or "").strip()
    if res.returncode not in (0, None) and stderr.lower().startswith("error:"):
        # Commander refused the arguments before any action ran. Keep only its first line.
        return SendOutcome("failed", error=_short("cli_usage", stderr.splitlines()[0]))
    if res.returncode not in (0, None) and NOT_LOGGED_IN_RE.search(stderr):
        return SendOutcome("failed", error=_short("not_logged_in", stderr.splitlines()[-1]), login_required=True)
    return SendOutcome("unknown", error=_short("garbled_output", f"exit {res.returncode}, stdout is not the expected JSON"))


def _image_ids(data: dict) -> list[str]:
    """msgId of every image: `sent` (zalo-agent's own list), else zca-js's `attachment` answers."""
    rows = data.get("sent")
    if not isinstance(rows, list) or not rows:
        rows = data.get("attachment")
        rows = rows if isinstance(rows, list) else [rows]
    ids = [str(r.get("msgId")) for r in rows if isinstance(r, dict) and r.get("msgId") not in (None, "")]
    return [i for i in ids if MSG_ID_RE.match(i)][:50]


def classify_images(res: EngineResult, count: int) -> SendOutcome:
    """Outcome of one `msg send-image` with `count` files (see the module docstring)."""
    if res.missing:
        return SendOutcome("failed", error=_short("engine_missing", res.stderr))
    if res.cancelled:
        return SendOutcome("unknown", error=_short("cancelled", "bridge stopped while zalo-agent was sending images"))
    if res.timed_out:
        return SendOutcome("unknown", error=_short("timeout", "zalo-agent did not finish the image send in time"))
    data = res.data
    if isinstance(data, dict):
        err = res.error_text
        if err is not None:
            if NOT_LOGGED_IN_RE.search(err) or NOT_LOGGED_IN_RE.search(res.stderr or ""):
                return SendOutcome("failed", error=_short("not_logged_in", err), login_required=True)
            if IMAGE_PRESEND_RE.search(err):
                return SendOutcome("failed", error=_short("image_refused", err))
            if AMBIGUOUS_RE.search(err):
                return SendOutcome("unknown", error=_short("transport_error", err))
            if count > 1:
                return SendOutcome("unknown", error=_short("partial_possible", err))
            return SendOutcome("failed", error=_short("zalo_error", err))
        ids = _image_ids(data)
        if ids:
            return SendOutcome("sent", zalo_msg_id=ids[0], part_msg_ids=ids)
        return SendOutcome("unknown", error=_short("no_msg_id", f"exit {res.returncode}, JSON without image msgIds"))
    stderr = (res.stderr or "").strip()
    if res.returncode not in (0, None) and stderr.lower().startswith("error:"):
        return SendOutcome("failed", error=_short("cli_usage", stderr.splitlines()[0]))
    if res.returncode not in (0, None) and NOT_LOGGED_IN_RE.search(stderr):
        return SendOutcome("failed", error=_short("not_logged_in", stderr.splitlines()[-1]), login_required=True)
    return SendOutcome("unknown", error=_short("garbled_output", f"exit {res.returncode}, stdout is not the expected JSON"))


class Sender:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def send(self, thread_id: str, text: str, cancel: threading.Event | None = None) -> SendOutcome:
        if not isinstance(thread_id, str) or not THREAD_ID_RE.match(thread_id):
            return SendOutcome("failed", error="invalid_item: thread_id must be a numeric Zalo user id")
        if not isinstance(text, str) or not text.strip():
            return SendOutcome("failed", error="invalid_item: text is empty")
        # -t 0: personal 1-1 thread (the webhook ignores groups). `--` so a text starting with "-" stays text.
        res = run_engine(self.cfg, ["msg", "send", "-t", "0", "--", thread_id, text],
                         timeout=self.cfg.send_timeout_s, cancel=cancel)
        return classify(res)

    def send_images(self, thread_id: str, keys, cancel: threading.Event | None = None) -> SendOutcome:
        """Send the menu images of a cs_images row (keys resolved through the manifest) in one `msg send-image`."""
        if not isinstance(thread_id, str) or not THREAD_ID_RE.match(thread_id):
            return SendOutcome("failed", error="invalid_item: thread_id must be a numeric Zalo user id")
        menu_dir = self.cfg.menu_images_dir or (self.cfg.state_dir.parent / "menu-images")
        try:
            images = resolve_menu_images(menu_dir, keys)
        except MenuImageError as e:
            return SendOutcome("failed", error=_short(str(e)))
        timeout = self.cfg.image_timeout_s(len(images))
        upload_ms = int(max(5.0, timeout - 5.0) * 1000)   # the engine gives up (and says so) before we kill it
        res = run_engine(self.cfg, ["msg", "send-image", "-t", "0", "--upload-timeout", str(upload_ms), "--", thread_id,
                                    *[str(i.path) for i in images]], timeout=timeout, cancel=cancel)
        return classify_images(res, len(images))
