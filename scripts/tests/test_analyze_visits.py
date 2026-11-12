"""scripts/analyze_visits.py end to end on a synthetic Zalo cache (contract 15.2, 15.4, 15.6, 15.7).

Every test builds a small SQLite file with the engine's tables (threads, messages, contacts) in a temporary folder and
runs the script as `python3 -I -B scripts/analyze_visits.py` in a subprocess. All chat text, names, phone numbers,
amounts and ids below are invented. The real `claude` is never run: PATH holds only scripts/tests/fake_bin_visits, a
folder with a python3 symlink, /usr/bin and /bin, and the tests check that `claude` resolves to the fake. A local
http.server stands in for the server endpoints. THOMHOUSE_BOT_HOME, ZALO_CONFIG_DIR, ZALO_DATA_DIR and
THOMHOUSE_DEV_VARS point at temporary folders.

Run:
  cd /Users/luuphuc/Projects/lulu-thomhouse && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
      -s scripts/tests -t scripts/tests -p 'test_analyze_visits.py'
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "analyze_visits.py"
FAKE_BIN = Path(__file__).resolve().parent / "fake_bin_visits"
FAKE_CLAUDE = FAKE_BIN / "claude"
TZ = timezone(timedelta(hours=7))
NOW = "2026-10-25 12:00"
OWNER = "1000000001"
TOKEN = "tok-test-SECRET-7781"

A = "5550001001"     # customer, with diacritics: two visits, an upcoming booking, a package, a phone in the chat
B = "5550001002"     # customer, without diacritics: a cancelled booking; phone only in the contacts table
FAM = "5550001003"   # family (mother)
STF = "5550001004"   # staff
UNK = "5550001005"   # unknown relationship: analyzed, never in the "customers" model scope
GRP = "5550001006"   # group
SYS = "5550001007"   # system account
MEMBER = "6660001001"

NAME_A = "Vương Ngọc Diệp"
NAME_B = "Phi Thanh Van"
NAME_UNK = "Lò Văn Khiêm"
NAME_STF = "Đinh Thảo Nhi"
NAME_GRP = "Nhóm bạn thân Cầu Giấy"
PHONE_A = "0912 345 678"
PHONE_B = "0987654321"
SENTENCE_A = "Chị mới chuyển nhà sang quận Bảy"
SENTENCE_B = "cam on em, tuan sau chi dat lai nhe"
SENTENCE_FAM = "Mẹ nhận tiền rồi, cảm ơn con"
SENTENCE_STF = "Chị ơi tháng này em chấm công thiếu 1 ngày"
SENTENCE_GRP = "Cuối tuần cả nhóm đi Ba Vì nhé"
HEALTH_A = "Chị bị đau lưng nên muốn massage nhẹ thôi nha em"

CANARIES = (NAME_A, NAME_B, NAME_UNK, NAME_STF, NAME_GRP, PHONE_A, PHONE_A.replace(" ", ""), PHONE_B,
            "0987 654 321", SENTENCE_A, SENTENCE_B, SENTENCE_FAM, SENTENCE_STF, SENTENCE_GRP, HEALTH_A,
            A, B, FAM, STF, UNK, GRP, SYS, MEMBER, OWNER, TOKEN)

SERVICES = {"services": [
    {"id": "goi-dau-thu-gian", "group": "hair", "name_vi": "Gội đầu thư giãn",
     "variants": [{"duration_min": 60, "price_vnd": 199000, "time_window": "09:00-20:30"}]},
    {"id": "massage-body-thu-gian", "group": "relaxation", "name_vi": "Massage body thư giãn",
     "variants": [{"duration_min": 60, "price_vnd": 350000, "time_window": "09:00-20:30"},
                  {"duration_min": 90, "price_vnd": 450000, "time_window": "09:00-20:30"}]},
    {"id": "se-khit-lam-hong", "group": "women", "name_vi": "Se khít làm hồng"},
]}

MOTHER_OWNER = ["Mẹ ơi con về muộn nha", "Con ăn rồi mẹ ơi", "Dạ mẹ, con nhớ rồi", "Mẹ ăn cơm chưa",
                "Con gửi mẹ tiền rồi nha mẹ", "Mai con ghé thăm mẹ", "Con thương mẹ nhiều", "Dạ con biết rồi mẹ",
                "Tiệm con hôm nay đông khách lắm mẹ", "Con làm gội đầu thư giãn cho mẹ nha"]
MOTHER_CONTACT = ["Ừ mẹ biết rồi", "Con ăn cơm chưa", "Mẹ đi chợ rồi con", "Con nhớ mặc ấm nha con",
                  "Mẹ nhớ con lắm", SENTENCE_FAM, "Dạ mẹ khỏe, con đừng lo",
                  "Spa con dạo này đông khách không", "Bữa nào mẹ qua gội đầu nha con", "Mẹ thương con"]
STAFF_CONTACT = ["Dạ chị, em tới tiệm rồi nha chị", "Chị ơi khách đặt lịch gội đầu thư giãn 3h chiều nay",
                 "Khách hủy lịch 5h rồi chị ơi", "Em xin nghỉ ca chiều mai được không chị", SENTENCE_STF,
                 "Có khách hỏi giá massage body nè chị", "Em dọn tiệm xong rồi chị",
                 "Dạ em nhắn khách xác nhận lịch rồi ạ",
                 "Chị ơi giá gội đầu thư giãn bao nhiêu để em báo khách", "Dạ em cảm ơn chị",
                 "Massage chân giá bao nhiêu vậy chị"]
STAFF_OWNER = ["Bé ơi nhắn khách xác nhận lịch giùm chị nha", "Ok em", "Em nhớ dọn phòng nha",
               "Khách tới thì em báo chị nha", "Bé ơi mai em vào ca sáng nha", "Gội đầu thư giãn 199k nha em"]


def at(mo: int, d: int, h: int = 10, mi: int = 0) -> int:
    return int(datetime(2026, mo, d, h, mi, tzinfo=TZ).timestamp() * 1000)


# (timestamp, from the contact, text)
CHAT_A = [
    (at(10, 15, 10, 0), True, "Chào shop, chị muốn đặt lịch gội đầu thư giãn thứ 7 lúc 15h nha em"),
    (at(10, 15, 10, 5), False, "Dạ em giữ lịch thứ 7 15h cho chị nha"),
    (at(10, 17, 14, 55), True, "chị tới rồi nè em"),
    (at(10, 17, 16, 30), False, "Dạ tổng hôm nay 199k ạ, bạn Lan làm cho chị nha"),
    (at(10, 17, 16, 35), True, "chị chuyển khoản rồi nhé em"),
    (at(10, 18, 9, 0), False, "Cảm ơn chị đã ghé thom house hôm qua ạ"),
    (at(10, 18, 9, 30), True, SENTENCE_A + ", sđt chị " + PHONE_A + " nha em"),
    (at(10, 21, 9, 0), True, "mai chị qua massage body lúc 10h được không em"),
    (at(10, 21, 9, 5), True, HEALTH_A),
    (at(10, 21, 9, 10), False, "Dạ được ạ, em giữ lịch 10h mai cho chị nha"),
    (at(10, 22, 9, 55), True, "chị đến nơi rồi"),
    (at(10, 22, 11, 35), True, "chị ck 350k rồi nha"),
    (at(10, 22, 12, 0), False, "Dạ gói 10 buổi gội đầu của chị còn 7 buổi nha chị"),
    (at(10, 24, 20, 0), True, "Thứ 3 tuần sau chị đặt lịch gội đầu lúc 9h nha em"),
    (at(10, 24, 20, 5), False, "Dạ em giữ lịch thứ 3 9h cho chị ạ"),
]
CHAT_B = [
    (at(10, 19, 9, 0), True, "chao shop, mai chi muon dat lich goi dau thu gian luc 3h nhe"),
    (at(10, 19, 9, 5), False, "Dạ em giữ lịch 15h mai cho chị nha"),
    (at(10, 20, 8, 0), True, "em oi chi ban dot xuat, huy lich hom nay giup chi nhe"),
    (at(10, 20, 8, 5), False, "Dạ em hủy lịch rồi nha chị"),
    (at(10, 20, 8, 10), True, SENTENCE_B),
]

EXPECTED_BLOCK = [
    "customer conversations analyzed: 3 (skipped: family 1, staff 1, group 1, system_account 1)",
    "  visits found: 2 (high 2, medium 0, low 0); upcoming bookings: 1; cancelled or no-show: 1",
    "  customers with at least one visit (high or medium): 1",
    "  visits with a service: 2; with a time: 2; with an amount: 2; with a technician: 1",
    "  phone numbers found: 2 (high 2, medium 0)",
    "  packages or vouchers found: 1",
]

SCHEMA = """
CREATE TABLE messages (msgId TEXT PRIMARY KEY, threadId TEXT, senderId TEXT, senderName TEXT, text TEXT,
  timestamp INTEGER, type TEXT, raw_data TEXT, localPath TEXT, has_attachment INTEGER DEFAULT 0, msgStatus INTEGER,
  mediaPrunedAt INTEGER);
CREATE TABLE threads (threadId TEXT PRIMARY KEY, type TEXT, name TEXT, lastUpdate INTEGER,
  sync_timestamp INTEGER DEFAULT 0, respondedByMe INTEGER, lastGlobalId TEXT, lastClientId TEXT, leftAt INTEGER,
  deleteMarkerAt INTEGER);
CREATE TABLE contacts (userId TEXT PRIMARY KEY, name TEXT, phone TEXT);
"""


class Cache:
    """A synthetic zalo.db with the engine's table and column names."""

    def __init__(self, path: Path, contacts_table: bool = True):
        self.con = sqlite3.connect(path)
        schema = SCHEMA if contacts_table else SCHEMA.split("CREATE TABLE contacts")[0]
        self.con.executescript(schema)
        self.n = 0
        self.texts: list[str] = []

    def thread(self, tid: str, name: str | None, ttype: str = "dm") -> None:
        self.con.execute("INSERT INTO threads (threadId, type, name, lastUpdate) VALUES (?,?,?,0)", (tid, ttype, name))

    def msg(self, tid: str, from_contact: bool, text: str, ts: int, mtype: str = "text",
            sender: str | None = None, sender_name: str = "Khách") -> None:
        self.n += 1
        sid = sender or (tid if from_contact else OWNER)
        self.con.execute(
            "INSERT INTO messages (msgId, threadId, senderId, senderName, text, timestamp, type) VALUES (?,?,?,?,?,?,?)",
            (f"m{self.n}", tid, sid, sender_name if from_contact else "Chủ", text, ts, mtype))
        if text:
            self.texts.append(text)

    def contact(self, uid: str, name: str, phone: str | None) -> None:
        self.con.execute("INSERT INTO contacts (userId, name, phone) VALUES (?,?,?)", (uid, name, phone))

    def close(self) -> None:
        self.con.commit()
        self.con.close()


def build_world(cache: Cache, contacts_table: bool = True) -> None:
    cache.thread(A, NAME_A)
    for ts, fc, text in CHAT_A:
        cache.msg(A, fc, text, ts, sender_name=NAME_A)
    cache.msg(A, True, "", at(10, 17, 15, 0), mtype="photo", sender_name=NAME_A)
    cache.thread(B, NAME_B)
    for ts, fc, text in CHAT_B:
        cache.msg(B, fc, text, ts, sender_name=NAME_B)
    cache.thread(FAM, "Mẹ")
    t = at(10, 1, 9, 0)
    for _round in range(3):
        for o, c in zip(MOTHER_OWNER, MOTHER_CONTACT):
            cache.msg(FAM, False, o, t)
            cache.msg(FAM, True, c, t + 60_000)
            t += 12 * 3_600_000
    cache.thread(STF, NAME_STF)
    t = at(10, 1, 9, 0)
    for _round in range(3):
        for c in STAFF_CONTACT:
            cache.msg(STF, True, c, t, sender_name=NAME_STF)
            t += 3 * 3_600_000
        for o in STAFF_OWNER:
            cache.msg(STF, False, o, t)
            t += 3 * 3_600_000
    cache.thread(UNK, NAME_UNK)
    cache.msg(UNK, True, "hello", at(10, 3, 9, 0), sender_name=NAME_UNK)
    cache.msg(UNK, False, "Dạ em chào ạ", at(10, 3, 9, 5))
    cache.thread(GRP, NAME_GRP, ttype="group")
    cache.msg(GRP, True, SENTENCE_GRP, at(10, 5, 9, 0), sender=MEMBER, sender_name="Bạn")
    cache.msg(GRP, False, "mai chị qua gội đầu lúc 3h nha", at(10, 5, 9, 5))
    cache.thread(SYS, "Zalo")
    cache.msg(SYS, True, "Chào mừng bạn đến với Zalo", at(10, 2, 9, 0), sender_name="Zalo")
    if contacts_table:
        cache.contact(B, NAME_B, PHONE_B)
        cache.contact(A, NAME_A, None)
        cache.contact(FAM, "Mẹ", "0933111222")


def index_of(chat: list[tuple[int, bool, str]], text: str, extra_ts: tuple[int, ...] = ()) -> int:
    """1-based transcript index of a message: every message of the conversation in time order (non-text too)."""
    stamps = sorted([ts for ts, _fc, _t in chat] + list(extra_ts))
    ts = next(ts for ts, _fc, t in chat if t == text)
    return stamps.index(ts) + 1


A_PHOTO_TS = (at(10, 17, 15, 0),)


class FakeServer:
    """Stands in for GET /staff/chat-facts/eligible and POST /staff/chat-facts/import."""

    def __init__(self):
        self.received: list[dict] = []
        self.eligible: tuple[int, object] = (200, {"zalo_user_ids": []})
        self.import_answer: tuple[int, object] | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status: int, payload: object) -> None:
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                outer.received.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                self._send(*outer.eligible)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                outer.received.append({"method": "POST", "path": self.path, "headers": dict(self.headers),
                                       "body": body})
                if outer.import_answer is not None:
                    self._send(*outer.import_answer)
                    return
                customers = body.get("customers") or []
                self._send(200, {"customers": len(customers),
                                 "visits_imported": sum(len(c.get("visits") or []) for c in customers),
                                 "visits_updated": 1, "visits_removed": 0, "visits_kept_staff": 2,
                                 "phones_set": sum(1 for c in customers if c.get("phone")),
                                 "benefits_upserted": sum(len(c.get("benefits") or []) for c in customers),
                                 "unmatched": []})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


def closed_port_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class CliCase(unittest.TestCase):
    # "-I" ignores PYTHONDONTWRITEBYTECODE, so the subprocesses also get "-B" (no .pyc next to the scripts).
    contacts_table = True

    def setUp(self):
        self.assertTrue(os.access(FAKE_CLAUDE, os.X_OK), "the fake claude must be executable")
        self.tmp = Path(tempfile.mkdtemp(prefix="test-av-"))
        self.home = self.tmp / "bot"
        self.home.mkdir()
        self.zalo = self.tmp / "zalo"
        acct = self.zalo / "accounts" / OWNER
        acct.mkdir(parents=True)
        (self.zalo / "accounts.json").write_text(json.dumps([{"ownId": OWNER, "name": "x", "active": True}]))
        self.db = acct / "zalo.db"
        self.cache = Cache(self.db, self.contacts_table)
        build_world(self.cache, self.contacts_table)
        self.cache.close()
        self.catalog = self.tmp / "services.json"
        self.catalog.write_text(json.dumps(SERVICES, ensure_ascii=False), encoding="utf-8")
        pybin = self.tmp / "pybin"
        pybin.mkdir()
        (pybin / "python3").symlink_to(sys.executable)
        self.path = os.pathsep.join([str(FAKE_BIN), str(pybin), "/usr/bin", "/bin"])
        found = shutil.which("claude", path=self.path)
        self.assertEqual(Path(found or "").resolve(), FAKE_CLAUDE.resolve(), "only the fake claude may be found")
        self.log = self.tmp / "calls.jsonl"
        self.cfg = self.tmp / "fake.json"
        self.fake(mode="reply", reply={"visits": [], "packages": []})
        accdir = self.home / "accounts" / "acc1"
        accdir.mkdir(parents=True)
        (self.home / "accounts.json").write_text(json.dumps(
            [{"label": "acc1", "config_dir": str(accdir), "priority": 1, "enabled": True}]), encoding="utf-8")
        self.dev_vars = self.tmp / "dev.vars"
        self.server: FakeServer | None = None

    def tearDown(self):
        if self.server is not None:
            self.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers

    def fake(self, **cfg):
        cfg.setdefault("log", str(self.log))
        self.cfg.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def calls(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def start_server(self) -> FakeServer:
        self.server = FakeServer()
        return self.server

    def run_cli(self, *args: str, env: dict | None = None, db: bool = True, now: bool = True,
                catalog: bool = True) -> subprocess.CompletedProcess:
        clean = {k: v for k, v in os.environ.items()
                 if not k.startswith(("ANTHROPIC_", "CLAUDE_", "FAKE_CLAUDE", "PROFILE_LLM", "THOMHOUSE_", "ZALO_",
                                      "SERVER_URL", "STAFF_TOKEN"))}
        clean.update(PATH=self.path, THOMHOUSE_BOT_HOME=str(self.home), ZALO_CONFIG_DIR=str(self.zalo),
                     ZALO_DATA_DIR=str(self.zalo / "accounts"), THOMHOUSE_DEV_VARS=str(self.dev_vars),
                     FAKE_CLAUDE_VISITS_CONFIG=str(self.cfg), PYTHONDONTWRITEBYTECODE="1",
                     ANTHROPIC_API_KEY="sk-test-not-a-real-key", ANTHROPIC_AUTH_TOKEN="test-not-a-real-token")
        clean.update(env or {})
        argv = [sys.executable, "-I", "-B", str(SCRIPT)]
        if catalog:
            argv += ["--catalog", str(self.catalog)]
        if now:
            argv += ["--now", NOW]
        if db:
            argv += ["--db", str(self.db), "--owner-id", OWNER]
        argv += list(args)
        return subprocess.run(argv, capture_output=True, text=True, env=clean, cwd=str(self.tmp), timeout=180)

    def outputs(self) -> list[Path]:
        return sorted((self.home / "profiles").glob("visits-*.json")) if (self.home / "profiles").exists() else []

    def doc(self) -> dict:
        files = self.outputs()
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text(encoding="utf-8"))

    def by_id(self, doc: dict) -> dict[str, dict]:
        return {c["zalo_user_id"]: c for c in doc["customers"]}

    def assert_no_canary(self, p: subprocess.CompletedProcess, *extra: str) -> None:
        text = p.stdout + p.stderr
        for c in CANARIES + extra:
            self.assertNotIn(c, text)
        self.assertNotIn("Traceback", text)

    def model_env(self, scope: str = "customers", **more: str) -> dict:
        env = {"PROFILE_LLM_ENABLED": "1", "PROFILE_LLM_SCOPE": scope, "PROFILE_LLM_MODEL": "claude-test-model",
               "PROFILE_LLM_TIMEOUT_S": "60"}
        env.update(more)
        return env


# ---------------------------------------------------------------- rules pass, output, invariants


class RulesRunTest(CliCase):
    def test_counts_block_file_and_mode(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        lines = p.stdout.splitlines()
        self.assertEqual(lines[:6], EXPECTED_BLOCK)
        self.assertEqual(lines[6], "  model pass: off")
        self.assertEqual(len(lines), 8)
        self.assertTrue(lines[7].startswith("written: ") and lines[7].endswith(" (mode 600)"), lines[7])
        self.assert_no_canary(p)
        files = self.outputs()
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r"^visits-\d{8}-\d{4}\.json$")
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.home / "profiles").stat().st_mode), 0o700)

    def test_document_shape_and_values(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        doc = self.doc()
        self.assertEqual(doc["analyzer_version"], "visits-rules-v1")
        self.assertIsInstance(doc["generated_at"], int)
        self.assertIsNone(doc["since"])
        self.assertEqual(doc["owner_id"], OWNER)
        self.assertEqual(doc["contacts"], 3)
        self.assertEqual(doc["skipped"], {"family": 1, "staff": 1, "group": 1, "system_account": 1})
        self.assertEqual(doc["model"], {"enabled": False, "scope": None, "customers_sent": 0, "calls": 0})
        cust = self.by_id(doc)
        self.assertEqual(sorted(cust), [f"p:{A}", f"p:{B}", f"p:{UNK}"])
        for c in cust.values():
            self.assertEqual(set(c), {"zalo_user_id", "relationship", "relationship_confidence", "messages",
                                      "first_at", "last_at", "visits", "upcoming", "phone", "benefits",
                                      "model_pass"})
            self.assertEqual(c["model_pass"], {"ran": False, "reason": "disabled"})
        a = cust[f"p:{A}"]
        self.assertEqual((a["relationship"], a["relationship_confidence"]), ("customer", "high"))
        self.assertEqual(a["messages"], len(CHAT_A) + 1)               # the photo counts as a message
        self.assertEqual(a["first_at"], CHAT_A[0][0])
        self.assertEqual(a["last_at"], CHAT_A[-1][0])
        self.assertEqual([(v["date"], v["time"], v["confidence"]) for v in a["visits"]],
                         [("2026-10-17", "15:00", "high"), ("2026-10-22", "10:00", "high")])
        v1, v2 = a["visits"]
        self.assertEqual((v1["amount_vnd"], v1["amount_source"], v1["technician"]), (199000, "paid", "Lan"))
        self.assertEqual(v1["services"][0]["service_id"], "goi-dau-thu-gian")
        self.assertEqual((v2["amount_vnd"], v2["amount_source"]), (350000, "paid"))
        self.assertIn("massage-body-thu-gian", [s["service_id"] for s in v2["services"]])
        for v in a["visits"]:
            self.assertEqual(v["source"], "chat_rules")
            self.assertLessEqual(len(v["evidence_at"]), 5)
        self.assertEqual([u["date"] for u in a["upcoming"]], ["2026-10-27"])
        self.assertNotIn("confidence", a["upcoming"][0])
        self.assertEqual(a["phone"], {"value": "0912345678", "confidence": "high", "source": "chat",
                                      "at": CHAT_A[6][0]})
        self.assertEqual(len(a["benefits"]), 1)
        self.assertEqual((a["benefits"][0]["total_count"], a["benefits"][0]["remaining"]), (10, 7))
        b = cust[f"p:{B}"]
        self.assertEqual(b["relationship"], "customer")
        self.assertEqual((b["visits"], b["upcoming"]), ([], []))
        self.assertEqual(b["phone"], {"value": PHONE_B, "confidence": "high", "source": "zalo_contact", "at": None})
        u = cust[f"p:{UNK}"]
        self.assertEqual(u["relationship"], "unknown")
        self.assertIsNone(u["phone"])
        self.assertEqual(doc_problems_15_4(doc), [])

    def test_no_message_text_or_name_in_the_file(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        raw = self.outputs()[0].read_text(encoding="utf-8")
        for text in [t for _ts, _fc, t in CHAT_A + CHAT_B] + MOTHER_CONTACT + STAFF_CONTACT + [SENTENCE_GRP]:
            if len(text) >= 12:
                self.assertNotIn(text, raw)
        for name in (NAME_A, NAME_B, NAME_UNK, NAME_STF, NAME_GRP, PHONE_A):
            self.assertNotIn(name, raw)
        for tid in (FAM, STF, GRP, SYS):
            self.assertNotIn(tid, raw)                                  # skipped conversations leave no trace

    def test_cache_is_left_unchanged(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        listing = sorted(x.name for x in self.db.parent.iterdir())
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertEqual(sorted(x.name for x in self.db.parent.iterdir()), listing)

    def test_default_cache_path_from_the_active_account(self):
        p = self.run_cli(db=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[0], EXPECTED_BLOCK[0])
        self.assertEqual(self.doc()["owner_id"], OWNER)

    def test_dry_run_writes_nothing(self):
        p = self.run_cli("--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        self.assertEqual(lines[:6], EXPECTED_BLOCK)
        self.assertEqual(lines[6:], ["  model pass: off", "dry run: nothing written, nothing pushed"])
        self.assertEqual(self.outputs(), [])
        self.assertFalse((self.home / "profiles").exists())
        self.assert_no_canary(p)

    def test_upcoming_follows_now(self):
        p = self.run_cli("--dry-run", "--now", "2026-10-20 12:00")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("  visits found: 1 (high 1, medium 0, low 0); upcoming bookings: 2; cancelled or no-show: 1",
                      p.stdout.splitlines())

    def test_out_dir_that_others_can_read_gets_a_warning(self):
        out = self.tmp / "shared"
        out.mkdir()
        os.chmod(out, 0o755)
        p = self.run_cli("--out-dir", str(out))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("warning", p.stderr)
        files = list(out.glob("visits-*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o755)
        self.assert_no_canary(p)

    def test_since_filters_messages(self):
        p = self.run_cli("--dry-run", "--since", "2026-10-21")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        self.assertIn("  visits found: 1 (high 1, medium 0, low 0); upcoming bookings: 1; cancelled or no-show: 0",
                      lines)


class NoContactsTableTest(CliCase):
    contacts_table = False

    def test_phone_from_the_chat_only(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("  phone numbers found: 1 (high 1, medium 0)", p.stdout.splitlines())
        cust = self.by_id(self.doc())
        self.assertIsNone(cust[f"p:{B}"]["phone"])
        self.assertEqual(cust[f"p:{A}"]["phone"]["source"], "chat")


# ---------------------------------------------------------------- failure paths (exit codes, no data in output)


class FailureTest(CliCase):
    def test_missing_cache(self):
        p = self.run_cli("--db", str(self.tmp / "nowhere" / OWNER / "zalo.db"), db=False)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")
        self.assertIn("not found", p.stderr)
        self.assert_no_canary(p)
        self.assertEqual(self.outputs(), [])

    def test_no_active_account(self):
        (self.zalo / "accounts.json").unlink()
        p = self.run_cli(db=False)
        self.assertEqual(p.returncode, 1)
        self.assert_no_canary(p)

    def test_corrupt_cache(self):
        bad = self.tmp / "corrupt" / OWNER / "zalo.db"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"SQLite format 3\x00" + (SENTENCE_A + " " + PHONE_A + " " + A).encode("utf-8") * 50)
        p = self.run_cli("--db", str(bad), db=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("cannot read zalo.db", p.stderr)
        self.assert_no_canary(p)
        self.assertEqual(self.outputs(), [])

    def test_not_a_zalo_cache(self):
        other = self.tmp / "other.db"
        con = sqlite3.connect(other)
        con.execute("CREATE TABLE notes (body TEXT)")
        con.execute("INSERT INTO notes VALUES (?)", (SENTENCE_A,))
        con.commit()
        con.close()
        p = self.run_cli("--db", str(other), db=False)
        self.assertEqual(p.returncode, 1)
        self.assert_no_canary(p)

    def test_unreadable_catalog(self):
        bad = self.tmp / "bad-services.json"
        bad.write_text("{not json " + SENTENCE_A + " " + PHONE_A, encoding="utf-8")
        p = self.run_cli("--catalog", str(bad), catalog=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("catalog", p.stderr)
        self.assert_no_canary(p)
        for v in self.by_id(self.doc())[f"p:{A}"]["visits"]:
            self.assertEqual(v["services"], [])

    def test_catalog_of_the_wrong_shape(self):
        bad = self.tmp / "odd-services.json"
        bad.write_text(json.dumps({"services": [1, "x", None, {"id": 5}]}), encoding="utf-8")
        p = self.run_cli("--dry-run", "--catalog", str(bad), catalog=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assert_no_canary(p)

    def test_bad_arguments_exit_2(self):
        for args in (("--now", "25/10/2026"), ("--now", "2026-10-25"), ("--since", "21-10-2026"), ("--bogus",)):
            with self.subTest(args=args):
                p = self.run_cli(*args)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assert_no_canary(p)
        self.assertEqual(self.outputs(), [])

    def test_bad_scope_exit_2_without_a_call(self):
        p = self.run_cli(env=self.model_env(scope="everyone"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("PROFILE_LLM_SCOPE", p.stderr)
        self.assertEqual(self.outputs(), [])
        self.assertEqual(self.calls(), [])
        self.assert_no_canary(p)

    def test_bad_model_settings_exit_2(self):
        for env in ({"PROFILE_LLM_MAX_CALLS": "lots"}, {"PROFILE_LLM_MAX_CALLS": "-1"},
                    {"PROFILE_LLM_TIMEOUT_S": "0"}, {"PROFILE_LLM_MODEL": "--dangerously-skip-permissions"}):
            with self.subTest(env=env):
                p = self.run_cli(env=self.model_env(**env))
                self.assertEqual(p.returncode, 2)
                self.assertEqual(self.calls(), [])
        self.assertEqual(self.outputs(), [])


# ---------------------------------------------------------------- push


class PushTest(CliCase):
    def setUp(self):
        super().setUp()
        self.srv = self.start_server()
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\nSERVER_URL={self.srv.url}\n", encoding="utf-8")

    def test_push_to_the_local_server(self):
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assert_no_canary(p)
        posts = [r for r in self.srv.received if r["method"] == "POST"]
        self.assertEqual(len(posts), 1)
        r = posts[0]
        self.assertEqual(r["path"], "/staff/chat-facts/import")
        h = {k.lower(): v for k, v in r["headers"].items()}
        self.assertEqual(h["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(h["x-staff-id"], "chat-analyzer")
        self.assertEqual(h["content-type"], "application/json")
        body = r["body"]
        self.assertEqual(set(body), {"analyzer_version", "generated_at", "dry_run", "customers"})
        self.assertEqual(body["analyzer_version"], "visits-rules-v1")
        self.assertIs(body["dry_run"], False)
        self.assertEqual(body["customers"], self.doc()["customers"])
        self.assertEqual(p.stdout.splitlines()[-1],
                         "pushed: customers 3, visits_imported 2, visits_updated 1, visits_removed 0, "
                         "visits_kept_staff 2, phones_set 2, benefits_upserted 1, unmatched 0")

    def test_dry_run_never_pushes(self):
        p = self.run_cli("--push", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.srv.received, [])
        self.assertEqual(self.outputs(), [])

    def test_push_refuses_a_remote_server(self):
        for url in ("https://bot.example.com", "http://192.0.2.10:8787", "file://localhost/tmp"):
            with self.subTest(url=url):
                p = self.run_cli("--push", "--server-url", url)
                self.assertEqual(p.returncode, 1)
                self.assertIn("non-local", p.stderr)
                self.assert_no_canary(p)
        self.assertEqual(self.srv.received, [])
        self.assertEqual(self.outputs(), [])

    def test_push_without_a_token(self):
        self.dev_vars.write_text(f"SERVER_URL={self.srv.url}\n", encoding="utf-8")
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assertIn("STAFF_TOKEN", p.stderr)
        self.assertEqual(self.srv.received, [])

    def test_push_404_says_the_endpoint_is_missing(self):
        echo = {"error": {"code": "not_found", "message": SENTENCE_A, "details": {"name": NAME_A, "phone": PHONE_B,
                                                                                 "id": A, "token": TOKEN}}}
        self.srv.import_answer = (404, echo)
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assertIn("404", p.stderr)
        self.assertIn("does not have", p.stderr)
        self.assert_no_canary(p)
        self.assertEqual(len(self.outputs()), 1)                         # the file is written before the push

    def test_push_500_prints_status_and_code_only(self):
        echo = {"error": {"code": "internal_error", "message": SENTENCE_B + " " + NAME_B,
                          "details": {"field": "customers[0].phone", "value": PHONE_A}}}
        self.srv.import_answer = (500, echo)
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assertIn("HTTP 500 internal_error", p.stderr)
        self.assert_no_canary(p)

    def test_push_error_code_with_data_is_not_printed(self):
        self.srv.import_answer = (422, {"error": {"code": NAME_A + " " + PHONE_A}})
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assertIn("HTTP 422", p.stderr)
        self.assert_no_canary(p)

    def test_push_answer_that_is_not_json(self):
        self.srv.import_answer = (200, (SENTENCE_A + " not json").encode("utf-8"))
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assert_no_canary(p)

    def test_server_not_reachable(self):
        p = self.run_cli("--push", "--server-url", closed_port_url())
        self.assertEqual(p.returncode, 1)
        self.assertIn("not reachable", p.stderr)
        self.assert_no_canary(p)

    def test_redirect_is_not_followed(self):
        # urllib follows a 302 after a POST as a GET that keeps the Authorization header; the script must not
        other = FakeServer()
        self.addCleanup(other.stop)
        orig = self.srv.srv.RequestHandlerClass.do_POST

        def redirect(handler):
            handler.rfile.read(int(handler.headers["Content-Length"]))
            handler.send_response(302)
            handler.send_header("Location", other.url + "/staff/chat-facts/eligible")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        self.srv.srv.RequestHandlerClass.do_POST = redirect
        self.addCleanup(setattr, self.srv.srv.RequestHandlerClass, "do_POST", orig)
        p = self.run_cli("--push")
        self.assertEqual(p.returncode, 1)
        self.assertIn("HTTP 302", p.stderr)
        self.assertEqual(other.received, [])                             # the token never reached another server
        self.assert_no_canary(p)

    def test_eligible_redirect_is_not_followed(self):
        other = FakeServer()
        self.addCleanup(other.stop)
        other.eligible = (200, {"zalo_user_ids": [f"p:{A}", f"p:{B}"]})
        orig = self.srv.srv.RequestHandlerClass.do_GET

        def redirect(handler):
            handler.send_response(302)
            handler.send_header("Location", other.url + "/staff/chat-facts/eligible")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        self.srv.srv.RequestHandlerClass.do_GET = redirect
        self.addCleanup(setattr, self.srv.srv.RequestHandlerClass, "do_GET", orig)
        p = self.run_cli("--dry-run", env=self.model_env(scope="consented"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("model pass skipped", p.stderr)
        self.assertIn("HTTP 302", p.stderr)
        self.assertEqual(other.received, [])
        self.assert_no_canary(p)

    def test_token_that_cannot_be_a_header_value(self):
        p = self.run_cli("--push", env={"STAFF_TOKEN": "tok with space " + TOKEN})
        self.assertEqual(p.returncode, 1)
        self.assertIn("STAFF_TOKEN", p.stderr)
        self.assertEqual(self.srv.received, [])
        self.assertEqual(self.outputs(), [])
        self.assert_no_canary(p, "tok with space")

    def test_proxy_variables_are_ignored(self):
        proxy = FakeServer()
        self.addCleanup(proxy.stop)
        env = {"http_proxy": proxy.url, "HTTP_PROXY": proxy.url, "https_proxy": proxy.url, "no_proxy": "",
               "NO_PROXY": ""}
        p = self.run_cli("--push", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(proxy.received, [])
        self.assertEqual(len([r for r in self.srv.received if r["method"] == "POST"]), 1)


class PushBatchTest(unittest.TestCase):
    """push() in-process: batches of 100 customers, counters summed."""

    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import analyze_visits  # noqa: PLC0415
        self.av = analyze_visits
        self.srv = FakeServer()

    def tearDown(self):
        self.srv.stop()

    def test_batches_of_100_and_summed_counters(self):
        customers = [{"zalo_user_id": f"p:9{i:09d}", "visits": [{"date": "2026-10-01"}] * (i % 3),
                      "phone": None, "benefits": []} for i in range(205)]
        totals = self.av.push(customers, 1_700_000_000_000, self.srv.url, TOKEN)
        posts = [r["body"] for r in self.srv.received]
        self.assertEqual([len(b["customers"]) for b in posts], [100, 100, 5])
        self.assertEqual([b["customers"][0]["zalo_user_id"] for b in posts], ["p:9000000000", "p:9000000100",
                                                                              "p:9000000200"])
        self.assertTrue(all(b["generated_at"] == 1_700_000_000_000 and b["dry_run"] is False for b in posts))
        self.assertEqual(totals["customers"], 205)
        self.assertEqual(totals["visits_imported"], sum(i % 3 for i in range(205)))
        self.assertEqual(totals["visits_updated"], 3)
        self.assertEqual(totals["visits_kept_staff"], 6)
        self.assertEqual(totals["unmatched"], 0)

    def test_a_failed_batch_stops_the_push(self):
        self.srv.import_answer = (500, {"error": {"code": "boom"}})
        with self.assertRaises(self.av.PushFailed) as ctx:
            self.av.push([{"zalo_user_id": "p:1"}] * 150, 1, self.srv.url, TOKEN)
        self.assertIn("HTTP 500 boom", str(ctx.exception))
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertEqual(len(self.srv.received), 1)


# ---------------------------------------------------------------- model pass


def answer_a() -> dict:
    """A model answer for customer A: a completed visit on a date without a rules candidate, a completed visit on a
    rules date (fills nothing, raises the source), and the package."""
    return {"visits": [
        {"date": "2026-10-15", "time": None, "status": "completed", "service_id": "goi-dau-thu-gian",
         "amount_vnd": None, "technician": None, "cites": [index_of(CHAT_A, CHAT_A[0][2], A_PHOTO_TS)]},
        {"date": "2026-10-22", "time": "10:00", "status": "completed", "service_id": None, "amount_vnd": 350000,
         "technician": None, "cites": [index_of(CHAT_A, "chị ck 350k rồi nha", A_PHOTO_TS)]},
    ], "packages": [{"title": "Gói 10 buổi", "total_count": 10, "remaining": 7,
                     "cites": [index_of(CHAT_A, CHAT_A[12][2], A_PHOTO_TS)]}]}


EMPTY = {"visits": [], "packages": []}

# The values the server's import accepts (apps/server/src/lib/chat-facts.ts parseImportDocument, contract 15.4):
# one value outside these makes the server answer 422 for the whole batch.
_DOC_ENUMS = {"basis": {"booking", "visit_day", "window"}, "amount_source": {"paid", "quoted", "list_price", None},
              "source": {"chat_rules", "chat_model", "chat_rules+model"}, "confidence": {"high", "medium", "low"},
              "reason": {"disabled", "not_in_scope", "no_candidate_window", "call_cap", "no_account", "error", "ok"}}


def doc_problems_15_4(doc: dict) -> list[str]:
    """Every customer entry of an output document checked against the contract 15.4 values; [] when all pass."""
    out: list[str] = []
    ms_ok = lambda v: type(v) is int and v >= 0  # noqa: E731
    for i, e in enumerate(doc["customers"]):
        w = f"customers[{i}]"
        for kind in ("visits", "upcoming"):
            for j, v in enumerate(e.get(kind) or []):
                vw = f"{w}.{kind}[{j}]"
                t = v.get("time")
                if v.get("time_known") is not (t is not None) or \
                        v.get("visited_at_local") != f"{v.get('date')} {t or '12:00'}":
                    out.append(f"{vw}: time")
                for k, s in enumerate(v.get("services") or []):
                    if s.get("basis") not in _DOC_ENUMS["basis"]:
                        out.append(f"{vw}.services[{k}].basis {s.get('basis')!r}")
                if v.get("amount_source") not in _DOC_ENUMS["amount_source"]:
                    out.append(f"{vw}.amount_source {v.get('amount_source')!r}")
                a = v.get("amount_vnd")
                if a is not None and not (type(a) is int and 1_000 <= a <= 50_000_000):
                    out.append(f"{vw}.amount_vnd")
                if v.get("source") not in _DOC_ENUMS["source"]:
                    out.append(f"{vw}.source {v.get('source')!r}")
                if kind == "visits" and v.get("confidence") not in _DOC_ENUMS["confidence"]:
                    out.append(f"{vw}.confidence {v.get('confidence')!r}")
                ev = v.get("evidence_at") or []
                if len(ev) > 5 or not all(ms_ok(x) for x in ev):
                    out.append(f"{vw}.evidence_at")
        for j, b in enumerate(e.get("benefits") or []):
            bw = f"{w}.benefits[{j}]"
            if b.get("kind") not in ("package", "voucher") or not b.get("title"):
                out.append(f"{bw}: kind or title")
            if b.get("stated_by") not in ("owner", "contact"):
                out.append(f"{bw}.stated_by {b.get('stated_by')!r}")
            if b.get("confidence") not in ("high", "medium"):
                out.append(f"{bw}.confidence {b.get('confidence')!r}")
            if not ms_ok(b.get("at")):
                out.append(f"{bw}.at {b.get('at')!r}")
        if (e.get("model_pass") or {}).get("reason") not in _DOC_ENUMS["reason"]:
            out.append(f"{w}.model_pass.reason")
    return out


class ModelPassTest(CliCase):
    def test_disabled_never_calls_claude(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.log.exists())
        self.assertIn("  model pass: off", p.stdout.splitlines())

    def test_falsy_values_keep_it_off(self):
        for value in ("0", "false", "no", ""):
            with self.subTest(value=value):
                p = self.run_cli("--dry-run", env={"PROFILE_LLM_ENABLED": value, "PROFILE_LLM_SCOPE": "customers"})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("  model pass: off", p.stdout.splitlines())
        self.assertEqual(self.calls(), [])

    def test_scope_customers_through_the_fake_claude(self):
        self.fake(mode="reply", replies=[answer_a(), EMPTY])
        p = self.run_cli(env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        self.assert_no_canary(p)
        calls = self.calls()
        self.assertEqual(len(calls), 2)                                  # A and B; the unknown contact is not sent
        for c in calls:
            flags = c["flags"]
            self.assertEqual(flags[flags.index("--model") + 1], "claude-test-model")
            self.assertEqual(flags[flags.index("--tools") + 1], "")
            self.assertIn("--strict-mcp-config", flags)
            self.assertIn("--no-session-persistence", flags)
            self.assertEqual(flags[flags.index("--output-format") + 1], "json")
            self.assertEqual(c["env"]["ANTHROPIC_API_KEY"], None)
            self.assertEqual(c["env"]["ANTHROPIC_AUTH_TOKEN"], None)
            self.assertEqual(c["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
            self.assertEqual(c["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
            self.assertEqual(c["cwd_files"], [])
            self.assertFalse(Path(c["cwd"]).exists())
            sent = c["user_text"] + c["system_prompt"]
            for secret in (NAME_A, NAME_B, NAME_UNK, PHONE_A, PHONE_A.replace(" ", ""), PHONE_B, HEALTH_A,
                           "Se khít", "se-khit-lam-hong", SENTENCE_FAM, SENTENCE_STF, A, B, OWNER):
                self.assertNotIn(secret, sent)
        self.assertIn(SENTENCE_A, calls[0]["user_text"])                # masked line: the text is sent, the phone not
        self.assertIn("chao shop, mai chi muon dat lich", calls[1]["user_text"])
        doc = self.doc()
        self.assertEqual(doc["model"], {"enabled": True, "scope": "customers", "customers_sent": 2, "calls": 2})
        cust = self.by_id(doc)
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": True, "reason": "ok"})
        self.assertEqual(cust[f"p:{B}"]["model_pass"], {"ran": True, "reason": "ok"})
        self.assertEqual(cust[f"p:{UNK}"]["model_pass"], {"ran": False, "reason": "not_in_scope"})
        visits = {v["date"]: v for v in cust[f"p:{A}"]["visits"]}
        self.assertEqual(sorted(visits), ["2026-10-15", "2026-10-17", "2026-10-22"])
        new = visits["2026-10-15"]
        self.assertEqual((new["confidence"], new["source"], new["signals"]), ("medium", "chat_model",
                                                                              ["model_completed"]))
        self.assertEqual(new["services"], [{"service_id": "goi-dau-thu-gian", "service_name": "Gội đầu thư giãn",
                                            "basis": "visit_day"}])   # the cited line is on that date
        self.assertEqual(doc_problems_15_4(doc), [])                    # what the server's import accepts
        self.assertEqual(visits["2026-10-17"]["source"], "chat_rules")
        same = visits["2026-10-22"]
        self.assertEqual((same["confidence"], same["source"], same["amount_vnd"], same["amount_source"]),
                         ("high", "chat_rules+model", 350000, "paid"))
        self.assertEqual(len(cust[f"p:{A}"]["benefits"]), 1)
        lines = p.stdout.splitlines()
        self.assertIn("  visits found: 3 (high 2, medium 1, low 0); upcoming bookings: 1; cancelled or no-show: 1",
                      lines)
        self.assertEqual(lines[6], "  model pass: on, scope customers: customers sent 2, calls 2 "
                                   "(ok 2, not_in_scope 1); model items dropped 0, fields dropped 0")

    def test_call_cap(self):
        self.fake(mode="reply", reply=EMPTY)
        p = self.run_cli(env=self.model_env(PROFILE_LLM_MAX_CALLS="1"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.calls()), 1)
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": True, "reason": "ok"})
        self.assertEqual(cust[f"p:{B}"]["model_pass"], {"ran": False, "reason": "call_cap"})
        self.assertEqual(self.doc()["model"]["calls"], 1)

    def test_zero_calls_allowed(self):
        p = self.run_cli(env=self.model_env(PROFILE_LLM_MAX_CALLS="0"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [])
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"]["reason"], "call_cap")

    def test_dry_run_makes_no_call(self):
        p = self.run_cli("--dry-run", env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.log.exists())
        self.assertEqual(self.outputs(), [])
        lines = p.stdout.splitlines()
        self.assertEqual(lines[6], "  model pass: dry run, scope customers: customers that would be sent 2, "
                                   "calls that would be made 2 (ok 2, not_in_scope 1); no call made")
        self.assertEqual(lines[7], "dry run: nothing written, nothing pushed")
        self.assert_no_canary(p)

    def test_no_usable_account(self):
        (self.home / "accounts.json").write_text("[]", encoding="utf-8")
        p = self.run_cli(env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [])
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": False, "reason": "no_account"})
        self.assertEqual(cust[f"p:{B}"]["model_pass"], {"ran": False, "reason": "no_account"})
        self.assert_no_canary(p)

    def test_model_error_keeps_the_rules_result(self):
        self.fake(mode="not_json")
        p = self.run_cli(env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.calls()), 2)
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": True, "reason": "error"})
        self.assertEqual([v["source"] for v in cust[f"p:{A}"]["visits"]], ["chat_rules", "chat_rules"])
        self.assertEqual(p.stdout.splitlines()[:6], EXPECTED_BLOCK)
        self.assert_no_canary(p)

    def test_model_visit_after_the_analysis_date_is_ignored(self):
        self.fake(mode="reply", replies=[answer_a(), EMPTY])
        p = self.run_cli("--now", "2026-10-20 12:00", env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        cust = self.by_id(self.doc())
        dates = [v["date"] for v in cust[f"p:{A}"]["visits"]]
        self.assertNotIn("2026-10-22", dates)
        self.assertEqual([u["date"] for u in cust[f"p:{A}"]["upcoming"]], ["2026-10-22", "2026-10-27"])
        self.assertIn("model items dropped 1", p.stdout)

    def test_scope_consented_through_the_eligible_endpoint(self):
        srv = self.start_server()
        srv.eligible = (200, {"zalo_user_ids": [f"p:{B}", "p:9999999999", f"p:{FAM}"]})
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\n", encoding="utf-8")
        self.fake(mode="reply", reply=EMPTY)
        p = self.run_cli("--server-url", srv.url, env=self.model_env(scope="consented"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        self.assert_no_canary(p)
        gets = [r for r in srv.received if r["method"] == "GET"]
        self.assertEqual(len(gets), 1)
        self.assertEqual(gets[0]["path"], "/staff/chat-facts/eligible")
        h = {k.lower(): v for k, v in gets[0]["headers"].items()}
        self.assertEqual(h["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(h["x-staff-id"], "chat-analyzer")
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("chao shop, mai chi muon dat lich", calls[0]["user_text"])
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": False, "reason": "not_in_scope"})
        self.assertEqual(cust[f"p:{B}"]["model_pass"], {"ran": True, "reason": "ok"})
        self.assertEqual(self.doc()["model"], {"enabled": True, "scope": "consented", "customers_sent": 1,
                                               "calls": 1})

    def test_scope_consented_with_the_endpoint_down(self):
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\n", encoding="utf-8")
        p = self.run_cli("--server-url", closed_port_url(), env=self.model_env(scope="consented"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("model pass skipped", p.stderr)
        self.assert_no_canary(p)
        self.assertEqual(self.calls(), [])
        self.assertEqual(p.stdout.splitlines()[:6], EXPECTED_BLOCK)
        cust = self.by_id(self.doc())
        self.assertEqual({c["model_pass"]["reason"] for c in cust.values()}, {"not_in_scope"})

    def test_scope_consented_with_bad_answers(self):
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\n", encoding="utf-8")
        srv = self.start_server()
        for answer in ((404, {"error": {"code": "not_found", "message": SENTENCE_A}}),
                       (200, {"ids": [f"p:{A}"]}), (200, {"zalo_user_ids": f"p:{A}"}),
                       (200, (NAME_A + " not json").encode("utf-8")), (500, {"error": {"code": "x"}})):
            with self.subTest(answer=answer[0]):
                srv.eligible = answer
                p = self.run_cli("--dry-run", "--server-url", srv.url, env=self.model_env(scope="consented"))
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("model pass skipped", p.stderr)
                self.assert_no_canary(p)
        self.assertEqual(self.calls(), [])

    def test_scope_consented_refuses_a_remote_server(self):
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\n", encoding="utf-8")
        p = self.run_cli("--dry-run", "--server-url", "https://bot.example.com",
                         env=self.model_env(scope="consented"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("model pass skipped", p.stderr)
        self.assert_no_canary(p)

    def test_default_scope_is_consented(self):
        env = self.model_env()
        del env["PROFILE_LLM_SCOPE"]
        p = self.run_cli("--dry-run", "--server-url", closed_port_url(), env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scope consented", p.stdout)
        self.assertIn("model pass skipped", p.stderr)


class ReviewFindingsTest(CliCase):
    """Review findings PRIV-1, 2, 7, 8, 10 and 11, end to end."""

    def add_rows(self, rows: list[tuple[str, bool, str, int]]) -> None:
        con = sqlite3.connect(self.db)
        for n, (tid, from_contact, text, ts) in enumerate(rows):
            con.execute("INSERT INTO messages (msgId, threadId, senderId, senderName, text, timestamp, type) "
                        "VALUES (?,?,?,?,?,?,?)", (f"x{n}", tid, tid if from_contact else OWNER,
                                                   NAME_A if from_contact else "Chủ", text, ts, "text"))
        con.commit()
        con.close()

    def test_display_name_in_a_message_is_never_sent(self):
        # PRIV-2: the spa writes the full name, the bank line has it in capitals without diacritics
        self.add_rows([(A, False, "Dạ chị Vương Ngọc Diệp ơi, em giữ lịch cho chị nha", at(10, 15, 10, 6)),
                       (A, True, "STK 0123 456 789 chủ tài khoản VUONG NGOC DIEP", at(10, 15, 10, 8)),
                       (B, False, "Dạ em giữ lịch cho chị Van ơi", at(10, 19, 9, 6))])
        self.fake(mode="reply", reply=EMPTY)
        p = self.run_cli(env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        sent = " ".join(c["user_text"] for c in self.calls())
        self.assertTrue(sent)
        for leak in (NAME_A, "VUONG NGOC DIEP", "Ngọc Diệp", "Vương Ngọc", "chị Van ơi"):
            self.assertNotIn(leak, sent)
        self.assertIn("chủ tài khoản <name>", sent)
        self.assertIn("chị <name> ơi", sent)

    def test_copied_lines_never_reach_the_file_or_the_push(self):
        # PRIV-1: an obedient model copies chat lines into the technician and the package title
        i_sent = index_of(CHAT_A, CHAT_A[6][2], A_PHOTO_TS)
        reply = {"visits": [{"date": "2026-10-17", "status": "completed", "technician": SENTENCE_A[:60],
                             "cites": [i_sent]}],
                 "packages": [{"title": CHAT_A[6][2], "total_count": None, "remaining": None, "cites": [i_sent]},
                              {"title": SENTENCE_A, "total_count": 10, "remaining": 7,
                               "cites": [index_of(CHAT_A, CHAT_A[12][2], A_PHOTO_TS)]}]}
        self.fake(mode="reply", replies=[reply, EMPTY])
        srv = self.start_server()
        self.dev_vars.write_text(f"STAFF_TOKEN={TOKEN}\n", encoding="utf-8")
        p = self.run_cli("--push", "--server-url", srv.url, env=self.model_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        body = json.dumps([r["body"] for r in srv.received if r["method"] == "POST"], ensure_ascii=False)
        stored = json.dumps(self.doc(), ensure_ascii=False)
        for blob in (body, stored):
            self.assertNotIn(SENTENCE_A, blob)
            self.assertNotIn("quận Bảy", blob)
            self.assertNotIn("chuyển nhà", blob)

    def test_staff_token_never_reaches_the_claude_process(self):
        # PRIV-7: STAFF_TOKEN is read for the consent list and the push, never passed to `claude`
        srv = self.start_server()
        srv.eligible = (200, {"zalo_user_ids": [f"p:{A}", f"p:{B}"]})
        self.fake(mode="reply", reply=EMPTY)
        p = self.run_cli("--server-url", srv.url, env=self.model_env(scope="consented", STAFF_TOKEN=TOKEN))
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual([c["env"]["STAFF_TOKEN"] for c in calls], [None, None])
        h = {k.lower(): v for k, v in srv.received[0]["headers"].items()}
        self.assertEqual(h["authorization"], f"Bearer {TOKEN}")

    def test_a_closed_wal_cache_gets_no_side_files(self):
        # PRIV-8: a WAL cache that no process has open is read without creating -wal / -shm files, also from a
        # folder this user cannot write
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA journal_mode=WAL")
        con.close()
        self.assertEqual(sorted(x.name for x in self.db.parent.iterdir()), ["zalo.db"])
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        p = self.run_cli("--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[:6], EXPECTED_BLOCK)
        self.assertEqual(sorted(x.name for x in self.db.parent.iterdir()), ["zalo.db"])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        os.chmod(self.db.parent, 0o500)
        try:
            p = self.run_cli("--dry-run")
        finally:
            os.chmod(self.db.parent, 0o700)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(x.name for x in self.db.parent.iterdir()), ["zalo.db"])

    def test_a_message_the_rules_cannot_read_keeps_the_customer(self):
        # PRIV-10: "²" passes str.isdigit() but int() rejects it
        self.add_rows([(B, False, "Dạ hôm nay ktv số ² làm cho chị ạ", at(10, 19, 9, 7)),
                       (B, True, "buổi thứ 4/² nha em", at(10, 19, 9, 8))])
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[0], EXPECTED_BLOCK[0])
        self.assertIn(f"p:{B}", self.by_id(self.doc()))

    def test_one_very_long_message_does_not_stall_the_run(self):
        # PRIV-11: a 600 000-character message is read up to 4 000 characters by every rules pass. Measured as
        # complexity, in CPU time of the analyzer process (resource RUSAGE_CHILDREN: other processes on a loaded
        # machine do not count), not as wall time. The same run with a message just past the cut (8 680 characters)
        # is the reference: on the build Mac 0.28 s against 0.60 s for 620 000 characters (reading and folding the
        # long text stays linear). Without a cut one rules pass alone adds 1.5 s (relationship rules, linear) to
        # minutes (package rules, quadratic), above the bound below. run_cli's 180 s timeout still stops a stall.
        unit = "chi dat lich goi dau mai 3h nhe, chi toi roi, ck 350k r nha e " * 10
        self.add_rows([(A, True, unit * 14, at(10, 16, 9, 0))])

        def cpu() -> float:
            best = float("inf")
            for _ in range(2):
                before = resource.getrusage(resource.RUSAGE_CHILDREN)
                p = self.run_cli("--dry-run", env=self.model_env())
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                self.assertEqual(p.returncode, 0, p.stderr)
                best = min(best, (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime))
            return best
        just_past = cpu()
        con = sqlite3.connect(self.db)
        con.execute("UPDATE messages SET text = ? WHERE msgId = 'x0'", (unit * 1000,))
        con.commit()
        con.close()
        very_long = cpu()
        self.assertLess(very_long, 2 * just_past + 1.0, (very_long, just_past))
        self.assertLess(very_long, 30.0)         # CPU seconds; about 0.6 s on the build Mac


# ---------------------------------------------------------------- in-process: errors never carry data


class InProcessTest(CliCase):
    """main() called in this process with a pass patched to fail; stdout and stderr are captured."""

    def setUp(self):
        super().setUp()
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import analyze_visits  # noqa: PLC0415
        self.av = analyze_visits
        keep = {k: v for k, v in os.environ.items() if k.startswith(("PROFILE_LLM", "THOMHOUSE_", "ZALO_"))}
        for k in keep:
            os.environ.pop(k)
        os.environ.update(THOMHOUSE_BOT_HOME=str(self.home), THOMHOUSE_DEV_VARS=str(self.dev_vars),
                          ZALO_CONFIG_DIR=str(self.zalo))

        def restore():
            for k in ("THOMHOUSE_BOT_HOME", "THOMHOUSE_DEV_VARS", "ZALO_CONFIG_DIR"):
                os.environ.pop(k, None)
            os.environ.update(keep)
        self.addCleanup(restore)

    def call_main(self, *args: str) -> tuple[int, str, str]:
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.av.main(["--db", str(self.db), "--owner-id", OWNER, "--catalog", str(self.catalog),
                                 "--now", NOW, *args])
        return code, out.getvalue(), err.getvalue()

    def assert_clean(self, text: str) -> None:
        for c in CANARIES:
            self.assertNotIn(c, text)
        self.assertNotIn("Traceback", text)

    def test_unexpected_error_prints_its_type_only(self):
        def boom(*_a, **_k):
            raise RuntimeError(f"{SENTENCE_A} {PHONE_A} {NAME_A} {A}")
        orig = self.av.analyze
        self.av.analyze = boom
        self.addCleanup(setattr, self.av, "analyze", orig)
        code, out, err = self.call_main("--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("unexpected error (RuntimeError)", err)
        self.assert_clean(out + err)

    def test_a_conversation_whose_rules_fail_is_left_out(self):
        orig = self.av.vr.extract_visits

        def flaky(msgs, *a, **k):
            if any(getattr(m, "text", "") == SENTENCE_B for m in msgs):
                raise ValueError(f"{SENTENCE_B} {PHONE_B} {NAME_B}")
            return orig(msgs, *a, **k)
        self.av.vr.extract_visits = flaky
        self.addCleanup(setattr, self.av.vr, "extract_visits", orig)
        code, out, err = self.call_main()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "customer conversations analyzed: 2 (skipped: family 1, staff 1, "
                                              "group 1, system_account 1, analysis_error 1)")
        self.assert_clean(out + err)
        doc = self.doc()
        self.assertNotIn(f"p:{B}", {c["zalo_user_id"] for c in doc["customers"]})
        self.assertEqual(doc["skipped"]["analysis_error"], 1)

    def test_a_failing_model_pass_keeps_the_rules_result(self):
        def boom(*_a, **_k):
            raise RuntimeError(f"{SENTENCE_A} {PHONE_A}")
        orig = self.av.vmp.run_for_customer
        self.av.vmp.run_for_customer = boom
        self.addCleanup(setattr, self.av.vmp, "run_for_customer", orig)
        os.environ.update(PROFILE_LLM_ENABLED="1", PROFILE_LLM_SCOPE="customers")
        self.addCleanup(os.environ.pop, "PROFILE_LLM_ENABLED", None)
        self.addCleanup(os.environ.pop, "PROFILE_LLM_SCOPE", None)
        code, out, err = self.call_main()
        self.assertEqual(code, 0, err)
        self.assert_clean(out + err)
        self.assertEqual(out.splitlines()[:6], EXPECTED_BLOCK)
        cust = self.by_id(self.doc())
        self.assertEqual(cust[f"p:{A}"]["model_pass"], {"ran": False, "reason": "error"})
        self.assertEqual(self.calls(), [])


# ---------------------------------------------------------------- module


class ModuleTest(unittest.TestCase):
    def test_importable_in_isolated_mode_without_side_effects(self):
        tmp = Path(tempfile.mkdtemp(prefix="test-av-imp-"))
        try:
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import analyze_visits as av; "
                    "assert 'claude_pool' not in sys.modules; assert callable(av.main)")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "THOMHOUSE_", "ZALO_"))}
            env.update(PYTHONDONTWRITEBYTECODE="1", THOMHOUSE_BOT_HOME=str(tmp / "bot"),
                       ZALO_CONFIG_DIR=str(tmp / "zalo"))
            p = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(SCRIPTS)], capture_output=True,
                               text=True, env=env, cwd=str(tmp), timeout=60)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
            self.assertEqual(list(tmp.iterdir()), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_help_exits_0(self):
        p = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), "--help"], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertIn("--now", p.stdout)


if __name__ == "__main__":
    unittest.main()
