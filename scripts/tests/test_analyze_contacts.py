"""scripts/analyze_contacts.py on synthetic zalo.db fixtures (never the real cache).

Each test builds a small SQLite file with the engine's tables (messages, threads, contacts) in a temp folder,
runs the analyzer with a temp THOMHOUSE_BOT_HOME / ZALO_CONFIG_DIR, and checks the profile JSON. A tiny local HTTP
server stands in for POST /staff/profiles/import."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "analyze_contacts.py"
OWNER = "1000000001"
TZ = timezone(timedelta(hours=7))
T0 = int(datetime(2026, 9, 1, 10, 0, tzinfo=TZ).timestamp() * 1000)
H = 3_600_000
DAY = 24 * H


def load():
    spec = importlib.util.spec_from_file_location("analyze_contacts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyze_contacts"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


AC = load()

SCHEMA = """
CREATE TABLE messages (msgId TEXT PRIMARY KEY, threadId TEXT, senderId TEXT, senderName TEXT, text TEXT,
  timestamp INTEGER, type TEXT, raw_data TEXT, localPath TEXT, has_attachment INTEGER DEFAULT 0, msgStatus INTEGER,
  mediaPrunedAt INTEGER);
CREATE TABLE threads (threadId TEXT PRIMARY KEY, type TEXT, name TEXT, lastUpdate INTEGER,
  sync_timestamp INTEGER DEFAULT 0, respondedByMe INTEGER, lastGlobalId TEXT, lastClientId TEXT, leftAt INTEGER,
  deleteMarkerAt INTEGER);
CREATE TABLE contacts (userId TEXT PRIMARY KEY, name TEXT, phone TEXT);
"""


class Fixture:
    def __init__(self, path: Path):
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)
        self.n = 0
        self.texts: list[str] = []
        self.names: list[str] = []

    def thread(self, tid: str, name: str | None, ttype: str = "dm"):
        self.con.execute("INSERT INTO threads (threadId, type, name, lastUpdate) VALUES (?,?,?,0)", (tid, ttype, name))
        if name:
            self.names.append(name)

    def msg(self, tid: str, from_contact: bool, text: str, at: int, mtype: str = "text", sender: str | None = None,
            sender_name: str = "Khách"):
        self.n += 1
        sid = sender or (tid if from_contact else OWNER)
        self.con.execute(
            "INSERT INTO messages (msgId, threadId, senderId, senderName, text, timestamp, type) VALUES (?,?,?,?,?,?,?)",
            (f"m{self.n}", tid, sid, sender_name if from_contact else "Chủ", text, at, mtype))
        if text:
            self.texts.append(text)

    def close(self):
        if self.con is not None:
            self.con.commit()
            self.con.close()
            self.con = None


class AnalyzerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thom-analyzer-"))
        self.home = self.tmp / "bot"
        self.zalo = self.tmp / "zalo"
        acct = self.zalo / "accounts" / OWNER
        acct.mkdir(parents=True)
        (self.zalo / "accounts.json").write_text(json.dumps([{"ownId": OWNER, "name": "x", "proxy": None, "active": True}]))
        self.db = acct / "zalo.db"
        self.fx = Fixture(self.db)
        self.env = {"THOMHOUSE_BOT_HOME": str(self.home), "ZALO_CONFIG_DIR": str(self.zalo),
                    "THOMHOUSE_DEV_VARS": str(self.tmp / "dev.vars"), "PROFILE_LLM_ENABLED": "",
                    "ZALO_DATA_DIR": "", "ZALO_DB_DIR": "", "SERVER_URL": "", "STAFF_TOKEN": ""}
        self._old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self, *args: str) -> tuple[int, str, str]:
        self.fx.close()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = AC.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def profiles(self, *args: str) -> dict[str, dict]:
        code, out, _err = self.run_main(*args)
        self.assertEqual(code, 0, out)
        files = sorted((self.home / "profiles").glob("contacts-*.json"))
        self.assertEqual(len(files), 1)
        doc = json.loads(files[0].read_text(encoding="utf-8"))
        return {p["zalo_user_id"]: p for p in doc["profiles"]}

    def assert_no_text_leak(self, output: str):
        for t in self.fx.texts:
            if len(t) >= 6:
                self.assertNotIn(t, output)
        for n in self.fx.names:
            self.assertNotIn(n, output)


class Fixture_:  # namespace for builders shared by several tests
    @staticmethod
    def customer(fx: Fixture, tid: str = "2001"):
        fx.thread(tid, "Nguyễn Thị Lan")
        fx.msg(tid, True, "Chào shop, chị muốn đặt lịch gội đầu thư giãn thứ 7 này", T0)
        fx.msg(tid, False, "Dạ em chào chị ạ. Chị Lan ơi bên em còn slot 3h chiều ạ", T0 + 60_000)
        fx.msg(tid, True, "Giá gói đó bao nhiêu tiền em, sđt chị 0909 123 456 nhé", T0 + 120_000)
        fx.msg(tid, False, "Dạ gội đầu thư giãn 50 phút giá 199.000đ ạ", T0 + 180_000)
        fx.msg(tid, False, "Cảm ơn chị đã ghé thom house hôm nay ạ", T0 + 2 * DAY)
        fx.msg(tid, True, "Ok em, chị đau lưng quá nên lần sau muốn massage body nữa", T0 + 6 * DAY)
        fx.msg(tid, True, "Lần trước chị làm gội đầu thư giãn thích lắm, cảm ơn em", T0 + 10 * DAY)


class CustomerTest(AnalyzerCase):
    def test_customer_profile_address_services_evidence(self):
        Fixture_.customer(self.fx)
        p = self.profiles()["p:2001"]
        self.assertEqual(p["display_name"], "Nguyễn Thị Lan")
        self.assertEqual(p["relationship"], "customer")
        self.assertIn(p["relationship_confidence"], ("medium", "high"))
        self.assertEqual(p["address_term"], "chị")
        self.assertIn(p["address_confidence"], ("medium", "high"))
        self.assertEqual(p["name_to_use"], "Lan")
        self.assertGreater(p["addressing"]["owner_calls_contact"].get("chị", 0), 0)
        self.assertGreater(p["addressing"]["contact_calls_self"].get("chị", 0), 0)
        svc = {s["key"]: s for s in p["services"]}
        self.assertEqual(svc["goi-dau-thu-gian"]["status"], "likely_used")
        self.assertGreaterEqual(svc["goi-dau-thu-gian"]["mention_count"], 2)
        self.assertEqual(svc["massage-body-thu-gian"]["status"], "mentioned")
        self.assertFalse(svc["goi-dau-thu-gian"]["sensitive"])
        self.assertEqual(p["stats"]["first_writer"], "contact")
        self.assertEqual(p["stats"]["messages_in"], 4)
        self.assertEqual(p["stats"]["messages_out"], 3)
        ev = p["evidence"]
        self.assertTrue(1 <= len(ev) <= 3)
        for e in ev:
            self.assertLessEqual(len(e["text"]), 80)
            self.assertNotIn("0909", e["text"])
            self.assertNotIn("123 456", e["text"])
            self.assertNotIn("đau", e["text"])   # the message with health vocabulary is never a snippet
            self.assertIn(e["kind"], ("service", "booking", "price"))

    def test_output_file_mode_and_stdout_has_counts_only(self):
        Fixture_.customer(self.fx)
        code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("contacts analyzed: 1", out)
        self.assert_no_text_leak(out + err)
        files = list((self.home / "profiles").glob("contacts-*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.home / "profiles").stat().st_mode), 0o700)

    def test_db_is_opened_read_only_and_left_unchanged(self):
        Fixture_.customer(self.fx)
        self.fx.close()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        con = AC.open_ro(self.db)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("INSERT INTO contacts (userId, name) VALUES ('x','y')")
        con.close()
        code, _out, _err = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_diacritic_free_abbreviations(self):
        self.fx.thread("2002", "Tran Thi Mai")
        self.fx.msg("2002", True, "c muon dat lich massage chan chieu nay", T0)
        self.fx.msg("2002", False, "e chao c a, c oi e con slot 4h nhe", T0 + 60_000)
        self.fx.msg("2002", True, "ok e, c cam on e", T0 + 120_000)
        p = self.profiles()["p:2002"]
        self.assertEqual(p["address_term"], "chị")
        self.assertEqual(p["name_to_use"], "Mai")
        self.assertEqual(p["relationship"], "customer")
        self.assertIn("massage-chan", {s["key"] for s in p["services"]})

    def test_c_and_a_outside_pronoun_positions_do_not_count(self):
        self.fx.thread("2003", "Bống")
        self.fx.msg("2003", True, "Dạ ạ, uống vitamin c mỗi ngày", T0)
        self.fx.msg("2003", True, "à vâng ạ", T0 + 1000)
        p = self.profiles()["p:2003"]
        a = p["addressing"]
        self.assertEqual(a["contact_calls_self"], {})
        self.assertEqual(a["contact_calls_owner"], {})
        self.assertEqual(p["address_term"], "anh/chị")
        self.assertEqual(p["address_confidence"], "low")
        self.assertIsNone(p["name_to_use"])   # one-word nickname

    def test_owner_calls_contact_em_uses_contact_self_term(self):
        self.fx.thread("2004", "Lê Văn Hùng")
        self.fx.msg("2004", False, "Em ơi chị gửi bảng giá nhé", T0)
        self.fx.msg("2004", True, "Dạ anh muốn đặt lịch massage cổ vai gáy", T0 + 1000)
        self.fx.msg("2004", False, "Ok em, cảm ơn em", T0 + 2000)
        self.fx.msg("2004", True, "anh cảm ơn chị", T0 + 3000)
        p = self.profiles()["p:2004"]
        self.assertGreater(p["addressing"]["owner_calls_contact"].get("em", 0), 0)
        self.assertEqual(p["address_term"], "anh")

    def test_owner_calls_contact_em_without_self_term_gives_anh_chi(self):
        self.fx.thread("2005", "Phạm Thu Hà")
        self.fx.msg("2005", False, "Em ơi, chị gửi bảng giá gội đầu nhé", T0)
        self.fx.msg("2005", True, "dạ vâng ạ, cho em đặt lịch nha", T0 + 1000)
        self.fx.msg("2005", False, "Cảm ơn em nhiều", T0 + 2000)
        p = self.profiles()["p:2005"]
        self.assertEqual(p["address_term"], "anh/chị")


class RelationshipTest(AnalyzerCase):
    def test_family_chat_is_family_high(self):
        self.fx.thread("3001", "Mẹ")
        lines = [(False, "Mẹ ơi con về muộn nha"), (True, "Ừ con ăn cơm chưa"), (False, "Con ăn rồi mẹ ơi"),
                 (True, "Tối về nhà sớm nhé con"), (False, "Dạ mẹ, tuần sau con về quê"),
                 (True, "Con ơi nhớ mua thuốc cho ba"), (False, "Dạ con nhớ rồi mẹ ơi"), (True, "Ngủ ngon nha con"),
                 (False, "Mẹ ngủ ngon"), (True, "Con ơi tết này về không"), (False, "Dạ có mẹ ơi")]
        for i, (fc, t) in enumerate(lines):
            self.fx.msg("3001", fc, t, T0 + i * DAY)
        p = self.profiles()["p:3001"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("family", "high"))
        self.assertTrue(any(r.startswith("kin_address") for r in p["relationship_reasons"]))
        self.assertEqual(p["evidence"], [])
        self.assertEqual(p["services"], [])
        self.assertIsNone(p["address_term"])

    def test_friend_with_one_service_question_is_friend_medium(self):
        self.fx.thread("3002", "Hoa")
        for i in range(12):
            self.fx.msg("3002", i % 2 == 0, "tao với mày đi cà phê không", T0 + i * DAY)
        self.fx.msg("3002", True, "mà bên mày gội đầu giá bao nhiêu tiền", T0 + 13 * DAY)
        p = self.profiles()["p:3002"]
        # the friend named a service once: still a friend, but not kept away from the bot
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("friend", "medium"))
        self.assertIn("cat:goi_dau", {s["key"] for s in p["services"]})

    def test_empty_thread_is_unknown(self):
        self.fx.thread("3003", None)
        self.fx.msg("3003", True, "", T0, mtype="photo")
        p = self.profiles()["p:3003"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("unknown", "low"))
        self.assertEqual(p["stats"]["messages_in"], 1)


FAMILY_LINES = [(False, "Mẹ ơi con về muộn nha"), (True, "Ừ con ăn cơm chưa"), (False, "Con ăn rồi mẹ ơi"),
                (True, "Tối về nhà sớm nhé con"), (False, "Dạ mẹ, tuần sau con về quê"),
                (True, "Con ơi nhớ mua thuốc cho ba"), (False, "Dạ con nhớ rồi mẹ ơi"), (True, "Ngủ ngon nha con"),
                (False, "Mẹ ngủ ngon"), (True, "Con ơi tết này về không"), (False, "Dạ có mẹ ơi")]


class AddressingRegressionTest(AnalyzerCase):
    """Patterns where word order alone gives the wrong person (review of 2026-11-08)."""

    def test_requests_that_name_the_owner_first_are_not_the_contact_self_term(self):
        # a woman who calls the account owner "anh" and herself "em"
        self.fx.thread("4001", "Trần Thị Mai")
        self.fx.msg("4001", True, "anh xem giúp em lịch thứ 7", T0)
        self.fx.msg("4001", True, "anh báo giá em gói gội đầu thư giãn", T0 + 60_000)
        self.fx.msg("4001", True, "anh tư vấn em gói nào hợp", T0 + 120_000)
        p = self.profiles()["p:4001"]
        a = p["addressing"]
        self.assertEqual(a["contact_calls_self"], {"em": 3})
        self.assertEqual(a["contact_calls_owner"], {"anh": 3})
        self.assertEqual((p["address_term"], p["address_confidence"]), ("anh/chị", "medium"))

    def test_chi_gui_em_dia_chi_is_a_request_to_the_owner(self):
        self.fx.thread("4002", "Lê Văn Nam")
        self.fx.msg("4002", True, "chị gửi em địa chỉ", T0)
        p = self.profiles()["p:4002"]
        self.assertEqual(p["addressing"]["contact_calls_self"], {"em": 1})
        self.assertEqual(p["addressing"]["contact_calls_owner"], {"chị": 1})
        self.assertEqual(p["address_term"], "anh/chị")

    def test_favour_words_owner_offer_owner_request_and_contact_request(self):
        self.fx.thread("4003", "Đỗ Thị Hằng")
        self.fx.msg("4003", True, "em xem giúp chị lịch thứ 7 với", T0)               # contact chị asks staff em
        self.fx.msg("4003", False, "Dạ em xem giúp chị nhé", T0 + 60_000)            # staff offers
        self.fx.msg("4003", False, "Dạ chị gửi giúp em ảnh chuyển khoản nhé", T0 + 120_000)  # offer or request: skipped
        p = self.profiles()["p:4003"]
        a = p["addressing"]
        self.assertEqual(a["contact_calls_self"], {"chị": 1})
        self.assertEqual(a["contact_calls_owner"], {"em": 1})
        self.assertEqual(a["owner_calls_contact"], {"chị": 1})
        self.assertEqual(a["owner_calls_self"], {"em": 1})
        self.assertEqual((p["address_term"], p["address_confidence"]), ("chị", "medium"))

    def test_a_male_owner_writing_anh_gui_em_does_not_make_the_contact_anh(self):
        self.fx.thread("4009", "Đỗ Thị Hằng")
        self.fx.msg("4009", False, "anh gửi em bảng giá gội đầu nhé", T0)
        self.fx.msg("4009", False, "anh gửi giúp em địa chỉ nhé", T0 + 60_000)
        p = self.profiles()["p:4009"]
        self.assertEqual(p["addressing"]["owner_calls_contact"], {})
        self.assertEqual(p["address_term"], "anh/chị")

    def test_owner_greeting_template_alone_stays_neutral_and_low(self):
        self.fx.thread("4004", "Phạm Thị Lan")
        self.fx.msg("4004", False, "Dạ thom house xin chào anh/chị ạ", T0)
        self.fx.msg("4004", False, "Dạ gội đầu thư giãn giá 199k ạ", T0 + 60_000)
        self.fx.msg("4004", True, "ok", T0 + 120_000)
        p = self.profiles()["p:4004"]
        self.assertEqual(p["addressing"]["owner_calls_contact"], {})
        self.assertEqual((p["address_term"], p["address_confidence"]), ("anh/chị", "low"))

    def test_neutral_pair_spellings_count_for_neither_person(self):
        self.fx.thread("4005", "Phạm Thị Lan")
        for i, t in enumerate(["Chào anh chị ạ", "Kính chào anh, chị", "chào a/c nhé", "Chị/Anh ơi bên em có ưu đãi",
                               "anh chị em ghé chơi nha", "cảm ơn anh hoặc chị đã nhắn"]):
            self.fx.msg("4005", False, t, T0 + i * 60_000)
        p = self.profiles()["p:4005"]
        self.assertEqual(p["addressing"]["owner_calls_contact"], {})
        self.assertEqual(p["address_term"], "anh/chị")

    def test_third_person_chu_y_and_plain_cam_on_a(self):
        self.fx.thread("4006", "Võ Thị Thu")
        self.fx.msg("4006", True, "anh ấy muốn đặt lịch massage body", T0)
        self.fx.msg("4006", True, "cam on a", T0 + 60_000)
        self.fx.msg("4006", True, "ok cam on a nhieu", T0 + 120_000)
        self.fx.msg("4006", False, "Dạ em sẽ chú ý ạ", T0 + 180_000)
        self.fx.msg("4006", False, "Chú ý: bên em nghỉ lễ 2/9", T0 + 240_000)
        p = self.profiles()["p:4006"]
        a = p["addressing"]
        self.assertNotIn("anh", a["contact_calls_self"])
        self.assertNotIn("anh", a["contact_calls_owner"])
        self.assertNotIn("chú", a["owner_calls_contact"])
        self.assertNotIn("chú", a["owner_calls_self"])
        self.assertEqual(p["address_term"], "anh/chị")

    def test_given_name_after_a_term_is_not_a_second_pronoun(self):
        self.fx.thread("4007", "Ngô Thị Anh")
        self.fx.msg("4007", False, "chị Anh ơi em gửi lịch", T0)
        p = self.profiles()["p:4007"]
        self.assertEqual(p["addressing"]["owner_calls_contact"], {"chị": 2})

    def test_unclear_self_term_is_not_used_when_the_owner_calls_the_contact_em(self):
        # "anh xem lịch thứ 7" may be "you check"; it gives no self-term, so the younger contact stays "anh/chị"
        self.fx.thread("4008", "Hà Thị Vy")
        self.fx.msg("4008", False, "Em ơi chị gửi bảng giá nhé", T0)
        self.fx.msg("4008", True, "anh xem lịch thứ 7", T0 + 60_000)
        self.fx.msg("4008", False, "Ok em, cảm ơn em", T0 + 120_000)
        p = self.profiles()["p:4008"]
        self.assertEqual(p["addressing"]["contact_calls_self"], {})
        self.assertEqual(p["address_term"], "anh/chị")


class RelationshipRegressionTest(AnalyzerCase):
    def family(self, tid: str):
        self.fx.thread(tid, "Mẹ")
        for i, (fc, t) in enumerate(FAMILY_LINES):
            self.fx.msg(tid, fc, t, T0 + i * DAY)

    def test_family_chat_with_one_everyday_money_or_booking_word_stays_family_high(self):
        extras = {"3101": "con book vé xe chưa", "3102": "giá vàng hôm nay lên rồi con", "3103": "mẹ mua rau hết 50k",
                  "3104": "mai con qua nhà mẹ lúc 3h nha"}
        for tid, extra in extras.items():
            self.family(tid)
            self.fx.msg(tid, True, extra, T0 + 12 * DAY)
        profiles = self.profiles()
        for tid in extras:
            p = profiles[f"p:{tid}"]
            self.assertEqual((p["relationship"], p["relationship_confidence"]), ("family", "high"), tid)
            self.assertEqual(p["evidence"], [], tid)

    def test_owner_promotion_sent_to_family_keeps_family_high(self):
        self.family("3105")
        self.fx.msg("3105", False, "Thom house ưu đãi gội đầu thư giãn 99k, shop em mời cả nhà ghé", T0 + 12 * DAY)
        p = self.profiles()["p:3105"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("family", "high"))
        self.assertEqual(p["evidence"], [])

    def test_regular_customer_who_writes_casually_is_a_customer(self):
        self.fx.thread("3106", "Hoa")
        for d in range(32):
            self.fx.msg("3106", True, "mai chị qua nha em", T0 + d * DAY)
            self.fx.msg("3106", False, "dạ em đợi chị", T0 + d * DAY + 1000)
            self.fx.msg("3106", True, "chị về nha", T0 + d * DAY + 2000)
            self.fx.msg("3106", True, "ok em", T0 + d * DAY + 3000)
        p = self.profiles()["p:3106"]
        self.assertEqual(p["relationship"], "customer")
        self.assertNotIn("personal_chitchat", " ".join(p["relationship_reasons"]))
        self.assertTrue(any(r.startswith("owner_deference") for r in p["relationship_reasons"]))
        self.assertEqual(p["address_term"], "chị")

    def test_long_chat_and_many_days_without_kinship_is_friend_medium(self):
        self.fx.thread("3107", "Hoa")
        for d in range(32):
            self.fx.msg("3107", d % 2 == 0, "đi chơi không, ăn cơm chưa", T0 + d * DAY)
        p = self.profiles()["p:3107"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("friend", "medium"))


class HealthEvidenceTest(AnalyzerCase):
    def test_health_words_in_mixed_diacritic_messages_never_become_snippets(self):
        self.fx.thread("5001", "Trần Thị Mai")
        self.fx.msg("5001", True, "em bi dau lung lắm, massage body được không ạ", T0)
        self.fx.msg("5001", True, "em bị thoái hoá cột sống, muốn massage cổ vai gáy ạ", T0 + 60_000)
        self.fx.msg("5001", True, "dạ dày em yếu, đặt lịch massage chân được không", T0 + 120_000)
        self.fx.msg("5001", True, "em muốn đặt lịch gội đầu thư giãn thứ 7", T0 + 180_000)
        p = self.profiles()["p:5001"]
        texts = [e["text"] for e in p["evidence"]]
        self.assertEqual(len(texts), 1)
        joined = " ".join(texts).lower()
        for word in ("dau lung", "thoái", "cột sống", "dạ dày"):
            self.assertNotIn(word, joined)

    def test_has_health_checks_plain_words_only(self):
        def h(t):
            low = AC.nfc_lower(t)
            return AC.has_health(low, AC.fold(low))
        self.assertTrue(h("em bi dau lung lắm"))
        self.assertTrue(h("em bị trĩ"))
        self.assertTrue(h("chị bị tiền đình"))
        self.assertTrue(h("dau dau qua"))
        self.assertFalse(h("chị muốn massage đầu"))      # "đầu" written with its marks is not pain
        self.assertFalse(h("gội đầu thư giãn"))
        self.assertFalse(h("goi dau thu gian"))
        self.assertFalse(h("ừ em đặt lịch nha"))         # "ừ" is not the plain "u"


class PastUseRegressionTest(AnalyzerCase):
    def statuses(self, tid: str) -> dict[str, str]:
        return {s["key"]: s["status"] for s in self.profiles()[f"p:{tid}"]["services"]}

    def test_an_earlier_question_is_not_a_visit(self):
        self.fx.thread("6001", "Trần Thị Mai")
        self.fx.msg("6001", True, "tuần trước em có hỏi giá massage body, giờ còn ưu đãi không ạ", T0)
        self.assertEqual(self.statuses("6001"), {"massage-body-thu-gian": "mentioned"})

    def test_owner_thanks_for_trust_is_not_a_visit(self):
        self.fx.thread("6002", "Trần Thị Mai")
        self.fx.msg("6002", True, "cho em hỏi triệt lông và gội đầu bao nhiêu", T0)
        self.fx.msg("6002", False, "Dạ em cảm ơn chị đã tin tưởng thom house ạ", T0 + 60_000)
        # triệt lông is not a thom house service: never a profile service (analyzer v3)
        self.assertEqual(self.statuses("6002"), {"cat:goi_dau": "mentioned"})

    def test_owner_quay_lai_is_not_a_revisit(self):
        self.fx.thread("6003", "Trần Thị Mai")
        self.fx.msg("6003", True, "massage chân giá sao ạ", T0)
        self.fx.msg("6003", False, "Dạ em quay lại báo chị sau nhé", T0 + 60_000)
        self.assertEqual(self.statuses("6003"), {"massage-chan": "mentioned"})

    def test_a_time_phrase_without_a_service_does_not_spread(self):
        self.fx.thread("6004", "Trần Thị Mai")
        self.fx.msg("6004", True, "gội đầu thư giãn giá sao em", T0)
        self.fx.msg("6004", True, "lần trước chị nói rồi mà", T0 + 60_000)
        self.assertEqual(self.statuses("6004"), {"goi-dau-thu-gian": "mentioned"})

    def test_visits_still_count(self):
        self.fx.thread("6005", "Trần Thị Mai")
        self.fx.msg("6005", True, "massage chân giá sao ạ", T0)
        self.fx.msg("6005", False, "Cảm ơn chị đã ghé thom house hôm nay ạ", T0 + DAY)
        self.fx.msg("6005", True, "hôm trước chị làm massage cổ vai gáy thích lắm", T0 + 5 * DAY)
        self.assertEqual(self.statuses("6005"), {"massage-chan": "likely_used", "massage-co-vai-gay": "likely_used"})


class ScopeTest(AnalyzerCase):
    def test_groups_own_thread_and_system_rows_are_skipped(self):
        Fixture_.customer(self.fx, "2001")
        self.fx.thread("g1", "Nhóm", ttype="group")
        self.fx.msg("g1", False, "chào cả nhà", T0, sender="777")
        self.fx.thread(OWNER, "My Documents")
        self.fx.msg(OWNER, False, "ghi chú", T0)
        self.fx.msg("2001", True, "", T0 + 5, mtype="deleted")
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("contacts analyzed: 1", out)
        doc = json.loads(next((self.home / "profiles").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual([p["zalo_user_id"] for p in doc["profiles"]], ["p:2001"])
        self.assertEqual(doc["skipped"], {"group": 1, "own_thread": 1})
        self.assertEqual(doc["profiles"][0]["stats"]["messages_in"], 4)

    def test_since_filters_old_messages(self):
        Fixture_.customer(self.fx)
        since = datetime.fromtimestamp((T0 + 5 * DAY) / 1000, TZ).strftime("%Y-%m-%d")
        p = self.profiles("--since", since)["p:2001"]
        self.assertEqual(p["stats"]["messages_in"], 2)    # the messages of day 6 and day 10
        self.assertEqual(p["stats"]["messages_out"], 0)

    def test_out_dir_keeps_the_mode_of_an_existing_folder(self):
        Fixture_.customer(self.fx)
        shared = self.tmp / "shared"
        shared.mkdir()
        os.chmod(shared, 0o755)
        code, out, err = self.run_main("--out-dir", str(shared))
        self.assertEqual(code, 0, err)
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), 0o755)
        self.assertIn("warning", err)
        files = list(shared.glob("contacts-*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assert_no_text_leak(out + err)

    def test_out_dir_created_by_the_script_is_private(self):
        Fixture_.customer(self.fx)
        new_dir = self.tmp / "new" / "profiles"
        code, _out, err = self.run_main("--out-dir", str(new_dir))
        self.assertEqual(code, 0, err)
        self.assertEqual(stat.S_IMODE(new_dir.stat().st_mode), 0o700)
        self.assertNotIn("warning", err)

    def test_dry_run_writes_nothing(self):
        Fixture_.customer(self.fx)
        code, out, _ = self.run_main("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertFalse((self.home / "profiles").exists())

    def test_explicit_db_and_missing_db(self):
        Fixture_.customer(self.fx)
        code, _out, _err = self.run_main("--db", str(self.db), "--dry-run")
        self.assertEqual(code, 0)
        code, _out, err = self.run_main("--db", str(self.tmp / "nope.db"), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_llm_flag_is_not_implemented(self):
        Fixture_.customer(self.fx)
        os.environ["PROFILE_LLM_ENABLED"] = "true"
        code, _out, err = self.run_main("--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("not implemented", err)


class ImportShapeTest(AnalyzerCase):
    """The analyzer output must pass POST /staff/profiles/import validation (docs/contracts.md section 13)."""

    def test_profiles_follow_the_server_import_rules(self):
        import re
        Fixture_.customer(self.fx)
        self.fx.thread("3001", "Mẹ")
        for i in range(12):
            self.fx.msg("3001", i % 2 == 0, "Mẹ ơi con về muộn, ăn cơm chưa", T0 + i * DAY)
        self.fx.thread("bad id!", "x")
        self.fx.msg("bad id!", True, "chào", T0)
        code, _out, _err = self.run_main()
        self.assertEqual(code, 0)
        doc = json.loads(next((self.home / "profiles").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(doc["skipped"].get("bad_thread_id"), 1)
        terms = {"chị", "anh", "cô", "chú", "bác", "anh/chị", None}
        services_by_id = {s["id"]: s for s in json.loads((ROOT / "data/services.json").read_text(encoding="utf-8"))["services"]}
        for p in doc["profiles"]:
            self.assertRegex(p["zalo_user_id"], r"^p:[A-Za-z0-9_-]{1,64}$")
            self.assertTrue(p["display_name"] is None or len(p["display_name"]) <= 100)
            self.assertIn(p["relationship"], ("customer", "staff", "family", "friend", "unknown"))
            if p["relationship"] in ("staff", "family", "friend"):
                self.assertIsNone(p["address_term"])
                self.assertIsNone(p["last_service"])
            ls = p["last_service"]
            if ls is not None:
                self.assertEqual(ls["source"], "chat")
                self.assertIn(ls["confidence"], ("low", "medium", "high"))
                self.assertIsInstance(ls["at"], int)
                self.assertTrue(0 < len(ls["name"]) <= 120)
                self.assertIsInstance(ls["sensitive"], bool)
                self.assertTrue(ls["service_id"] is None or ls["service_id"] in services_by_id)
            self.assertIn(p["relationship_confidence"], ("low", "medium", "high"))
            self.assertIn(p["address_confidence"], ("low", "medium", "high"))
            self.assertIn(p["address_term"], terms)
            self.assertTrue(p["name_to_use"] is None or re.fullmatch(r"[^\W\d_]{1,20}", p["name_to_use"]))
            self.assertLessEqual(len(p["relationship_reasons"]), 20)
            for r in p["relationship_reasons"]:
                self.assertRegex(r, r"^[a-z0-9_:.-]{1,64}$")
            self.assertLessEqual(len(json.dumps(p["addressing"], ensure_ascii=False)), 4000)
            self.assertLessEqual(len(json.dumps(p["stats"], ensure_ascii=False)), 4000)
            self.assertLessEqual(len(p["services"]), 40)
            for sv in p["services"]:
                self.assertRegex(sv["key"], r"^(cat:)?[a-z0-9_-]{1,64}$")
                self.assertTrue(sv["service_id"] is None or re.fullmatch(r"[a-z0-9-]{1,64}", sv["service_id"]))
                self.assertTrue(0 < len(sv["name"]) <= 120)
                self.assertIsInstance(sv["sensitive"], bool)
                self.assertIn(sv["status"], ("mentioned", "likely_used"))
            self.assertLessEqual(len(p["evidence"]), 3)
            for ev in p["evidence"]:
                self.assertTrue(0 < len(ev["text"]) <= 80)
                self.assertIn(ev["from"], ("contact", "owner"))
                self.assertIn(ev["kind"], ("service", "booking", "price"))


MOTHER_OWNER = ["Mẹ ơi con về muộn nha", "Con ăn rồi mẹ ơi", "Dạ mẹ, con nhớ rồi", "Mẹ ăn cơm chưa",
                "Con gửi mẹ tiền rồi nha mẹ", "Mai con ghé thăm mẹ", "Con thương mẹ nhiều", "Dạ con biết rồi mẹ",
                "Tiệm con hôm nay đông khách lắm mẹ", "Con làm gội đầu thư giãn cho mẹ nha"]
MOTHER_CONTACT = ["Ừ mẹ biết rồi", "Con ăn cơm chưa", "Mẹ đi chợ rồi con", "Con nhớ mặc ấm nha con",
                  "Mẹ nhớ con lắm", "Mẹ nhận tiền rồi, cảm ơn con", "Dạ mẹ khỏe, con đừng lo",
                  "Spa con dạo này đông khách không", "Bữa nào mẹ qua gội đầu nha con", "Mẹ thương con"]
STAFF_CONTACT = ["Dạ chị, em tới tiệm rồi nha chị", "Chị ơi khách đặt lịch gội đầu thư giãn 3h chiều nay",
                 "Khách hủy lịch 5h rồi chị ơi", "Em xin nghỉ ca chiều mai được không chị",
                 "Chị ơi tháng này em chấm công thiếu 1 ngày", "Có khách hỏi giá massage body nè chị",
                 "Em dọn tiệm xong rồi chị", "Dạ em nhắn khách xác nhận lịch rồi ạ",
                 "Chị ơi giá gội đầu thư giãn bao nhiêu để em báo khách", "Dạ em cảm ơn chị",
                 "Massage chân giá bao nhiêu vậy chị"]
STAFF_OWNER = ["Bé ơi nhắn khách xác nhận lịch giùm chị nha", "Ok em", "Em nhớ dọn phòng nha",
               "Khách tới thì em báo chị nha", "Bé ơi mai em vào ca sáng nha", "Gội đầu thư giãn 199k nha em"]
FRIEND_LINES = ["tao với mày đi cà phê không", "mày ăn cơm chưa", "tối nay đi chơi không mày", "tao mệt quá trời",
                "hôm qua tao gặp con Lan", "mày coi phim đó chưa", "ngủ ngon nha mày", "tao đang ở nhà nè"]


class RealFailureRegressionTest(AnalyzerCase):
    """Synthetic chats that reproduce the misclassifications the owner measured on real data (2026-11-08)."""

    def test_mother_via_me_con_is_family_and_never_addressed(self):
        # the owner writes "mẹ" and "con" all the time, the mother too; three stray "anh" won before (v2: "anh Xuân")
        self.fx.thread("7001", "Lê Xuân")
        at = T0
        for _round in range(3):
            for o, c in zip(MOTHER_OWNER, MOTHER_CONTACT):
                self.fx.msg("7001", False, o, at)
                self.fx.msg("7001", True, c, at + 60_000)
                at += DAY // 2
        for t in ("Chào anh ạ", "cảm ơn anh nha", "Dạ anh"):
            self.fx.msg("7001", False, t, at)
            at += 60_000
        p = self.profiles()["p:7001"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("family", "high"))
        self.assertIn("family_role:contact_parent", p["relationship_reasons"])
        self.assertIsNone(p["address_term"])
        self.assertEqual(p["address_confidence"], "low")
        self.assertEqual(p["evidence"], [])
        self.assertIsNone(p["last_service"])
        a = p["addressing"]
        self.assertGreater(a["uses_owner"].get("mẹ", 0), 10)
        self.assertGreater(a["uses_contact"].get("mẹ", 0), 10)
        self.assertGreater(a["owner_calls_contact"].get("mẹ", 0), 0)
        self.assertGreater(a["owner_calls_self"].get("con", 0), 0)
        self.assertIn("bot_term_if_customer", a)

    def test_staff_via_chi_em_be_and_insider_work_talk(self):
        # a young staff member: calls the owner "chị", herself "em"; the owner calls her "bé"; the chat is full of
        # services, prices and bookings, but of the shop's customers (v2: "customer, gọi chị Thư")
        self.fx.thread("7002", "Anh Thư")
        at = T0
        for _round in range(3):
            for t in STAFF_CONTACT:
                self.fx.msg("7002", True, t, at)
                at += 3 * H
            for t in STAFF_OWNER:
                self.fx.msg("7002", False, t, at)
                at += 3 * H
        p = self.profiles()["p:7002"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("staff", "high"))
        self.assertIsNone(p["address_term"])
        self.assertEqual(p["name_to_use"], "Thư")
        self.assertEqual(p["evidence"], [])
        self.assertIsNone(p["last_service"])
        reasons = " ".join(p["relationship_reasons"])
        self.assertIn("insider_contact:", reasons)
        self.assertIn("owner_calls_be:", reasons)
        self.assertGreater(p["stats"]["work_messages"], 10)
        # work talk about the shop's customers never marks a service as used by the staff member
        self.assertFalse(any(s["status"] == "likely_used" for s in p["services"]))

    def test_young_customer_who_calls_the_owner_chi_is_still_a_customer(self):
        self.fx.thread("7010", "Ngô Thị Hà")
        self.fx.msg("7010", True, "Chị ơi em muốn đặt lịch gội đầu thư giãn", T0)
        self.fx.msg("7010", False, "Dạ em ơi, chị xếp lịch 3h cho em nha", T0 + 60_000)
        self.fx.msg("7010", True, "Giá massage body bao nhiêu chị", T0 + 120_000)
        self.fx.msg("7010", True, "em tới tiệm rồi chị ơi", T0 + DAY)
        self.fx.msg("7010", True, "Dạ em cảm ơn chị", T0 + DAY + 60_000)
        p = self.profiles()["p:7010"]
        self.assertEqual(p["relationship"], "customer")
        self.assertEqual(p["address_term"], "anh/chị")

    def test_customer_booking_for_her_mother_is_not_family(self):
        self.fx.thread("7009", "Phạm Thị Thu")
        self.fx.msg("7009", True, "Chị muốn đặt lịch massage body cho mẹ chị thứ 7", T0)
        self.fx.msg("7009", False, "Dạ em chào chị ạ, bên em còn lịch thứ 7 ạ", T0 + 60_000)
        self.fx.msg("7009", True, "Mẹ chị 60 tuổi rồi, đặt massage chân được không em", T0 + 120_000)
        self.fx.msg("7009", False, "Dạ được ạ chị", T0 + 180_000)
        self.fx.msg("7009", True, "Cho chị đặt 2 người, chị với mẹ", T0 + 240_000)
        self.fx.msg("7009", True, "cảm ơn em nha", T0 + 300_000)
        p = self.profiles()["p:7009"]
        self.assertEqual(p["relationship"], "customer")
        self.assertEqual(p["address_term"], "chị")
        self.assertEqual(p["name_to_use"], "Thu")

    def test_nickname_display_name_keeps_the_given_name(self):
        self.fx.thread("7003", "Vy girl phố")
        self.fx.msg("7003", True, "Chị muốn đặt lịch gội đầu thư giãn", T0)
        self.fx.msg("7003", False, "Dạ em chào chị ạ", T0 + 60_000)
        p = self.profiles()["p:7003"]
        self.assertEqual(p["name_to_use"], "Vy")     # v2: "Phố"

    def test_zalo_system_and_official_accounts_are_skipped(self):
        Fixture_.customer(self.fx, "2001")
        self.fx.thread("7004", "Zalo Official Account")
        self.fx.msg("7004", True, "Chào mừng bạn đến với Zalo, cập nhật phiên bản mới", T0)
        self.fx.thread("7005", None)                      # only cards and events (dropped as system rows)
        self.fx.msg("7005", True, "", T0, mtype="card")
        self.fx.msg("7005", True, "", T0 + 1000, mtype="event")
        self.fx.thread("7006", None)                      # a card and links
        self.fx.msg("7006", True, "", T0, mtype="card")
        self.fx.msg("7006", True, "https://example.test/x", T0 + 1000, mtype="link")
        self.fx.thread("7012", "ZaloPay")
        self.fx.msg("7012", True, "Giao dịch thành công 50.000đ", T0)
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        doc = json.loads(next((self.home / "profiles").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual([p["zalo_user_id"] for p in doc["profiles"]], ["p:2001"])
        self.assertEqual(doc["skipped"].get("system_account"), 4)
        self.assert_no_text_leak(out)

    def test_nail_is_not_a_service_and_never_evidence(self):
        self.fx.thread("7007", "Trần Thị Mai")
        self.fx.msg("7007", True, "Chị muốn đặt lịch làm móng thứ 7", T0)
        self.fx.msg("7007", True, "Cho chị hỏi gội đầu thư giãn giá bao nhiêu", T0 + 60_000)
        self.fx.msg("7007", True, "Lần trước chị làm móng xong rồi, đẹp lắm", T0 + 120_000)
        self.fx.msg("7007", False, "Dạ bên em không có làm nail ạ, bên em có gội đầu thư giãn", T0 + 180_000)
        p = self.profiles()["p:7007"]
        self.assertEqual({s["key"]: s["status"] for s in p["services"]}, {"goi-dau-thu-gian": "mentioned"})
        self.assertIsNone(p["last_service"])
        for e in p["evidence"]:
            self.assertNotIn("móng", e["text"])
        self.assertTrue(any(r.startswith("non_catalog_service:") for r in p["relationship_reasons"]))

    def test_close_friend_with_a_long_chat_about_the_spa_is_friend_high(self):
        self.fx.thread("7008", "Trần Bảo Ngọc")
        at = T0
        for d in range(60):
            for k in range(10):
                self.fx.msg("7008", k % 2 == 0, FRIEND_LINES[(d + k) % len(FRIEND_LINES)], at + k * 60_000)
            at += DAY
        for k, t in enumerate(["spa mày dạo này sao rồi", "bữa nào tao qua gội đầu nha", "đi làm móng không mày",
                               "thom house có combo gì mới không mày"]):
            self.fx.msg("7008", True, t, at + k * 60_000)
        p = self.profiles()["p:7008"]
        self.assertEqual((p["relationship"], p["relationship_confidence"]), ("friend", "high"))
        self.assertIsNone(p["address_term"])
        self.assertEqual(p["evidence"], [])
        self.assertIn("very_long_chat", p["relationship_reasons"])

    def test_elder_customer_is_addressed_co(self):
        self.fx.thread("7011", "Trần Thị Hoa")
        self.fx.msg("7011", False, "Dạ con chào cô ạ", T0)
        self.fx.msg("7011", True, "Cô muốn đặt lịch massage chân", T0 + 60_000)
        self.fx.msg("7011", False, "Dạ con xếp lịch cho cô 9h sáng nha cô", T0 + 120_000)
        self.fx.msg("7011", True, "Ừ cảm ơn con", T0 + 180_000)
        p = self.profiles()["p:7011"]
        self.assertEqual(p["relationship"], "customer")
        self.assertEqual(p["address_term"], "cô")

    def test_last_service_is_the_latest_likely_used_catalog_service(self):
        Fixture_.customer(self.fx)
        p = self.profiles()["p:2001"]
        ls = p["last_service"]
        self.assertEqual({k: ls[k] for k in ("key", "service_id", "source", "confidence", "sensitive")},
                         {"key": "goi-dau-thu-gian", "service_id": "goi-dau-thu-gian", "source": "chat",
                          "confidence": "medium", "sensitive": False})
        self.assertEqual(ls["at"], T0 + 10 * DAY)
        self.assertEqual(ls["name"], "Gội đầu thư giãn")

    def test_last_service_from_the_visit_window_only_is_low(self):
        self.fx.thread("6010", "Trần Thị Mai")
        self.fx.msg("6010", True, "massage chân giá sao ạ", T0)
        self.fx.msg("6010", False, "Cảm ơn chị đã ghé thom house hôm nay ạ", T0 + DAY)
        ls = self.profiles()["p:6010"]["last_service"]
        self.assertEqual((ls["key"], ls["confidence"], ls["at"]), ("massage-chan", "low", T0 + DAY))


class NameTest(unittest.TestCase):
    def test_given_name_rules(self):
        g = AC.given_name
        self.assertEqual(g("Nguyễn Thị Lan"), ("Lan", None))
        self.assertEqual(g("Chị Lan"), ("Lan", "chị"))
        self.assertEqual(g("C Hoa"), ("Hoa", "chị"))
        self.assertEqual(g("Nguyen Van Nam"), ("Nam", None))
        self.assertEqual(g("Lan Nguyen")[0], None)        # no diacritics, western order
        self.assertEqual(g("Minh Hoàng")[0], None)        # last word is a family name: ambiguous order
        # decoration, emoji and digits are removed first; one common given name is then used (analyzer v3)
        self.assertEqual(g("Lan Spa")[0], "Lan")
        self.assertEqual(g("Bống")[0], None)
        self.assertEqual(g("Lan 0909")[0], "Lan")
        self.assertEqual(g("🌸 Lan 🌸")[0], "Lan")
        self.assertEqual(g(None), (None, None))
        # nicknames, aliases and given names that look like a prefix (review of 2026-11-08)
        self.assertEqual(g("Mẹ Bống"), (None, None))       # the child's name
        self.assertEqual(g("Mẹ Su Su"), (None, None))
        self.assertEqual(g("Bé Na"), (None, None))
        self.assertEqual(g("Chị Lan Gò Vấp"), (None, "chị"))
        self.assertEqual(g("Lan Khách Quen"), ("Lan", None))
        self.assertEqual(g("Chi Nguyễn"), (None, None))   # "Chi" is the given name, Nguyễn the family name
        self.assertEqual(g("Chị Nguyễn"), (None, "chị"))
        self.assertEqual(g("Anh Thư"), ("Thư", None))     # a female given name, not "anh" + Thư
        self.assertEqual(g("A. Tuấn"), ("Tuấn", "anh"))
        self.assertEqual(g("Cj Hoa"), ("Hoa", "chị"))
        self.assertEqual(g("Tran Thi Mai"), ("Mai", None))

    def test_recommend_drops_conflicting_self_terms_and_needs_clear_ones_for_a_younger_contact(self):
        from collections import Counter as C
        r = AC.recommend
        # the contact "calls herself anh" once (misread) but calls the owner anh three times: the self-term goes
        term, _conf, basis = r(C(), C({"anh": 1}), C({"anh": 3}), C(), None, C({"anh": 1}))
        self.assertEqual(term, "anh/chị")
        self.assertEqual(basis["conflicting_terms"], ["anh"])
        # the owner calls the contact em: only a self-term from a clear pattern says anh
        self.assertEqual(r(C({"em": 2}), C({"anh": 2}), C(), C(), None, C())[0], "anh/chị")
        self.assertEqual(r(C({"em": 2}), C({"anh": 2}), C(), C(), None, C({"anh": 2}))[0], "anh")
        # both anh and chị from clear patterns: no gendered guess
        self.assertEqual(r(C({"em": 2}), C({"anh": 1, "chị": 1}), C(), C(), None, C({"anh": 1, "chị": 1}))[0], "anh/chị")

    def test_snippet_masks_and_limits(self):
        s = AC.snippet("x" * 50 + " gọi 0909123456 hoặc +84 909 123 456 để đặt lịch gội đầu " + "y" * 60, 60)
        self.assertLessEqual(len(s), 80)
        self.assertNotIn("0909123456", s)
        self.assertNotIn("909 123 456", s)
        self.assertEqual(AC.mask_digits("giá 199.000đ"), "giá 199.000đ")


class PushTest(AnalyzerCase):
    def start_server(self):
        received: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                received.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                 "staff": self.headers.get("X-Staff-Id"), "body": body})
                n = len(body["profiles"])
                raw = json.dumps({"imported": n, "created": n, "updated": 0, "kept_staff_fields": 0}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}", received

    def test_push_posts_to_local_import_with_staff_token(self):
        Fixture_.customer(self.fx)
        url, received = self.start_server()
        (self.tmp / "dev.vars").write_text(f"STAFF_TOKEN=tok-test\nSERVER_URL={url}\n")
        code, out, err = self.run_main("--push")
        self.assertEqual(code, 0, err)
        self.assertIn("pushed: imported 1, created 1", out)
        self.assertEqual(len(received), 1)
        r = received[0]
        self.assertEqual(r["path"], "/staff/profiles/import")
        self.assertEqual(r["auth"], "Bearer tok-test")
        self.assertEqual(r["staff"], "analyzer")
        self.assertEqual(r["body"]["profiles"][0]["zalo_user_id"], "p:2001")
        self.assertNotIn("tok-test", out + err)
        self.assert_no_text_leak(out + err)

    def test_push_refuses_a_remote_server(self):
        Fixture_.customer(self.fx)
        (self.tmp / "dev.vars").write_text("STAFF_TOKEN=tok-test\n")
        code, _out, err = self.run_main("--push", "--server-url", "https://bot.example.com")
        self.assertEqual(code, 1)
        self.assertIn("non-local", err)


if __name__ == "__main__":
    unittest.main()
