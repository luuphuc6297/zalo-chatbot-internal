"""Unit tests for scripts/visit_rules.py (contract 15.4, 15.5, 15.75).

Synthetic chats only: invented names, invented numbers, invented amounts. The catalog is a small synthetic JSON written
to a temporary folder. Run:

  cd /Users/luuphuc/Projects/lulu-thomhouse && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
      -s scripts/tests -t scripts/tests -p 'test_visit_rules.py'
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "visit_rules.py"
TZ = timezone(timedelta(hours=7))


def load():
    spec = importlib.util.spec_from_file_location("visit_rules", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["visit_rules"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


VR = load()
AC = sys.modules["analyze_contacts"]

CATALOG = {"services": [
    {"id": "goi-dau-duong-sinh", "group": "hair", "name_vi": "Gội đầu dưỡng sinh",
     "variants": [{"duration_min": 60, "price_vnd": 150000, "time_window": None}]},
    {"id": "massage-body-thu-gian", "group": "relaxation", "name_vi": "Massage body thư giãn",
     "variants": [{"duration_min": 60, "price_vnd": 429000, "time_window": "09:00-20:30"},
                  {"duration_min": 90, "price_vnd": 599000, "time_window": "09:00-20:30"},
                  {"duration_min": 60, "price_vnd": 499000, "time_window": "after_20:30"}]},
    {"id": "massage-chan", "group": "relaxation", "name_vi": "Massage chân",
     "variants": [{"duration_min": 30, "price_vnd": 199000, "time_window": "09:00-24:00"},
                  {"duration_min": 45, "price_vnd": 250000, "time_window": "09:00-24:00"}]},
    {"id": "massage-co-vai-gay", "group": "relaxation", "name_vi": "Massage cổ, vai, gáy",
     "variants": [{"duration_min": 30, "price_vnd": 199000, "time_window": None}]},
    {"id": "cham-soc-da-co-ban", "group": "skin", "name_vi": "Chăm sóc da cơ bản",
     "variants": [{"duration_min": 60, "price_vnd": 300000, "time_window": None}]},
]}

_TMP = tempfile.TemporaryDirectory(prefix="test_visit_rules_")
CATALOG_PATH = Path(_TMP.name) / "services.json"
CATALOG_PATH.write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
CAT = AC.load_catalog(CATALOG_PATH)
PRICES = VR.load_prices(CATALOG_PATH)


def ms(when: str) -> int:
    """Local (UTC+7) 'YYYY-MM-DD HH:MM' -> epoch milliseconds."""
    return int(datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=TZ).timestamp() * 1000)


def C(when: str, text: str, mtype: str = "text"):
    """A message the contact wrote."""
    return VR.ChatMsg(ms(when), False, text, mtype)


def S(when: str, text: str, mtype: str = "text"):
    """A message the spa (owner account) wrote."""
    return VR.ChatMsg(ms(when), True, text, mtype)


NOW = ms("2026-11-12 18:00")           # a Thursday


def run(msgs, prices=None, now=NOW):
    return VR.extract_visits(msgs, CAT, now, prices)


def day(text: str, when: str, past: bool = False):
    return VR.resolve_day(text, ms(when), past=past)


# ---------------------------------------------------------------- 15.5 date resolution


class ResolveDayTest(unittest.TestCase):
    T = "2026-11-12 10:00"     # Thursday morning

    def test_relative_days_with_and_without_diacritics(self):
        cases = {
            "mai 3h chị qua nha": "2026-11-13",
            "mai 3h chi qua nhe": "2026-11-13",
            "ngày mai chị ghé": "2026-11-13",
            "chiều mai": "2026-11-13",
            "chieu mai chi qua": "2026-11-13",
            "sáng mai 9h": "2026-11-13",
            "tối mai": "2026-11-13",
            "mốt chị qua": "2026-11-14",
            "ngày mốt": "2026-11-14",
            "ngày kia chị qua": "2026-11-14",
            "ngay kia chi qua": "2026-11-14",
            "hôm nay chị qua": "2026-11-12",
            "hom nay chi qua": "2026-11-12",
            "nay chị qua được không": "2026-11-12",
            "nay chi qua dc ko em": "2026-11-12",
            "chiều nay": "2026-11-12",
            "tối nay 7h": "2026-11-12",
            "toi nay 7h chi qua": "2026-11-12",
            "lát nữa chị qua": "2026-11-12",
            "lát chị ghé": "2026-11-12",
            "tí nữa chị qua": "2026-11-12",
            "chút nữa chị tới": "2026-11-12",
            "bây giờ chị qua được không": "2026-11-12",
            "giờ chị qua nha": "2026-11-12",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(day(text, self.T), want)

    def test_ambiguous_or_vague_words_give_no_date(self):
        for text in ("mot chi qua", "mai mốt chị ghé", "hôm nào rảnh chị qua", "cuối tuần chị qua",
                     "lần trước chị làm", "tuần sau chị qua", "3 giờ chị qua", "chị Mai ơi", "cho chị gặp Mai",
                     "thêm chút nữa nha em", "mấy giờ mở cửa", "chi thay thoai mai lam em"):
            with self.subTest(text=text):
                self.assertIsNone(day(text, self.T))

    def test_weekdays_roll_forward(self):
        cases = {
            "thứ 7 chị qua": "2026-11-14", "thứ bảy": "2026-11-14", "t7 chị qua": "2026-11-14",
            "thu 7 chi qua": "2026-11-14", "thu bay": "2026-11-14", "chủ nhật": "2026-11-15",
            "cn chị qua": "2026-11-15",
            "chu nhat": "2026-11-15", "thứ 2": "2026-11-16", "thứ hai": "2026-11-16", "t2": "2026-11-16",
            "thứ 3": "2026-11-17", "thứ tư": "2026-11-18", "thứ 6": "2026-11-13", "thứ sáu": "2026-11-13",
            "thứ7 chị qua": "2026-11-14",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(day(text, self.T), want)

    def test_plain_weekday_spellings_that_are_other_words(self):
        # "thu tu" is also "thứ tự" (order), "thu sau" also "thử sau" (try later)
        self.assertIsNone(day("thu tu chi qua", self.T))
        self.assertIsNone(day("de chi thu sau", self.T))

    def test_ordinal_is_not_a_weekday(self):
        self.assertIsNone(day("buổi thứ 4 của chị", self.T))
        self.assertIsNone(day("lần thứ 2 chị làm", self.T))
        self.assertIsNone(day("lan thu 2 chi lam", self.T))
        # a capitalized name before the weekday is not the plain "lan" (lần)
        self.assertEqual(day("cho chị bạn Lan thứ 7 nha", self.T), "2026-11-14")

    def test_same_weekday_depends_on_stated_time(self):
        self.assertEqual(day("thứ 5 3h chị qua", self.T), "2026-11-12")       # 15:00 is still ahead
        self.assertEqual(day("thứ 5 9h chị qua", self.T), "2026-11-19")       # 09:00 has passed
        self.assertEqual(day("thứ 5 chị qua", self.T), "2026-11-19")          # no time: next week

    def test_next_week(self):
        self.assertEqual(day("thứ 7 tuần sau chị qua", self.T), "2026-11-21")
        self.assertEqual(day("tuần sau thứ 2 nha", self.T), "2026-11-16")
        self.assertEqual(day("thứ 7 tuần tới", self.T), "2026-11-21")
        self.assertEqual(day("thu 7 tuan sau", self.T), "2026-11-21")
        # sent on a Sunday: next calendar week starts the next day
        self.assertEqual(day("thứ 2 tuần sau", "2026-11-15 10:00"), "2026-11-16")
        self.assertEqual(day("thứ 3 tuần sau", "2026-11-15 10:00"), "2026-11-17")

    def test_explicit_dates(self):
        cases = {
            "15/11 chị qua": "2026-11-15", "15-11": "2026-11-15", "15.11": "2026-11-15",
            "15/11/2026": "2026-11-15", "ngày 15": "2026-11-15", "ngay 15 chi qua": "2026-11-15",
            "ngày 15 tháng 11": "2026-11-15", "ngay 15 thang 11": "2026-11-15", "15 tây": "2026-11-15",
            "ngày 15/11": "2026-11-15", "12/11": "2026-11-12",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(day(text, self.T), want)

    def test_month_and_year_rollover(self):
        self.assertEqual(day("ngày 5 chị qua", "2026-11-12 10:00"), "2026-12-05")
        self.assertEqual(day("5/1 chị qua", "2026-12-20 10:00"), "2027-01-05")
        self.assertEqual(day("mai chị qua", "2026-12-31 20:00"), "2027-01-01")
        self.assertEqual(day("thứ 2 chị qua", "2026-12-31 20:00"), "2027-01-04")
        self.assertEqual(day("10/11 chị qua", self.T), "2027-11-10")      # booking: first such date on or after

    def test_impossible_dates_and_numbers_that_are_not_dates(self):
        for text in ("31/2 chị qua", "30/2", "ngày 32", "15/13", "giá 1.150.000đ nha", "số chị 0915/11/2345 nha",
                     "3-4 người", "giảm 1/2 giá", "hẻm 15/11 Lê Lợi", "còn 3/10 buổi"):
            with self.subTest(text=text):
                self.assertIsNone(day(text, self.T))

    def test_midnight_boundary_utc_plus_7(self):
        # 2026-11-12 16:50 UTC is 23:50 local on the 12th; 17:10 UTC is 00:10 local on the 13th
        before = int(datetime(2026, 11, 12, 16, 50, tzinfo=timezone.utc).timestamp() * 1000)
        after = int(datetime(2026, 11, 12, 17, 10, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(VR.resolve_day("mai chị qua", before), "2026-11-13")
        self.assertEqual(VR.resolve_day("mai chị qua", after), "2026-11-14")
        self.assertEqual(VR.resolve_day("hôm nay", after), "2026-11-13")
        self.assertEqual(VR.resolve_day("hôm qua chị làm", after, past=True), "2026-11-12")

    def test_past_direction(self):
        cases = {
            "hôm qua chị làm gội đầu": "2026-11-11", "hom qua chi lam": "2026-11-11", "tối qua": "2026-11-11",
            "chiều qua chị ghé": "2026-11-11", "sáng qua": "2026-11-11", "hôm kia": "2026-11-10",
            "hom kia": "2026-11-10", "ngày 15": "2026-10-15", "15/11": "2025-11-15", "10/11": "2026-11-10",
            "sáng nay chị làm rồi": "2026-11-12", "thứ 7 chị làm rồi": "2026-11-07",
            "thứ 7 tuần trước": "2026-11-07",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(day(text, self.T, past=True), want)
        for text in ("lần trước chị làm", "hôm bữa chị qua", "tuần trước chị qua", "hôm trước chị làm",
                     "chiều chị qua", "toi qua", "sang qua"):
            with self.subTest(text=text):
                self.assertIsNone(day(text, self.T, past=True))

    def test_booking_direction_ignores_past_words(self):
        self.assertIsNone(day("hôm qua chị làm", self.T))
        self.assertIsNone(day("mai chị qua", self.T, past=True))

    def test_busy_clause_is_skipped(self):
        self.assertEqual(day("mai chị bận, mốt chị qua nha", self.T), "2026-11-14")
        self.assertEqual(day("thứ 6 chị kẹt rồi, thứ 7 nha em", self.T), "2026-11-14")


# ---------------------------------------------------------------- 15.5 time resolution


class ResolveTimeTest(unittest.TestCase):
    def test_forms(self):
        cases = {
            "15h": "15:00", "15h30": "15:30", "15:30": "15:30", "15g": "15:00", "15g30": "15:30",
            "3 giờ": "15:00", "3 gio": "15:00", "3 giờ rưỡi": "15:30", "3h rưỡi": "15:30", "3h kém 15": "14:45",
            "3h kem 15": "14:45", "mai 3 rưỡi chị qua": "15:30", "chị qua lúc 3 rưỡi nha": "15:30",
            "3h30p": "15:30", "lúc 4h": "16:00",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(VR.resolve_time(text), want)

    def test_day_parts(self):
        cases = {
            "sáng mai 10h": "10:00", "9h sáng": "09:00", "sáng 8h": "08:00", "trưa 12h": "12:00",
            "trưa 1h": "13:00", "11h trưa": "11:00", "chiều 5h": "17:00", "chieu 5h": "17:00", "tối 7h": "19:00",
            "7h tối": "19:00", "toi nay 7h": "19:00", "7h toi": "19:00", "9h sang": "09:00", "chiều mai 3h": "15:00",
            "chieu mai 3h": "15:00", "10h": "10:00", "12h": "12:00", "8h": "20:00", "1h": "13:00", "9h": "09:00",
            "20h30": "20:30", "sáng mai chị bận, 3h chiều qua nha": "15:00",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(VR.resolve_time(text), want)

    def test_not_a_time(self):
        for text in ("25h", "15h75", "15:61", "3 rưỡi", "giá 3 trăm rưỡi", "massage body 1h", "massage chân 45 phút",
                     "1 tiếng", "350k", "15/11", "mấy giờ", "chị trễ 10p", "liệu trình 1h30 nha"):
            with self.subTest(text=text):
                self.assertIsNone(VR.resolve_time(text))

    def test_busy_clause_time_is_skipped(self):
        self.assertEqual(VR.resolve_time("3h kín rồi chị ơi, 4h được không ạ"), "16:00")

    def test_marked_word_is_not_its_plain_twin(self):
        # "trống" (free) folds to "trong" (within), which would mark a duration
        self.assertEqual(VR.resolve_time("mai bên em còn trống 3h"), "15:00")
        # "sang" (move to) is not "sáng" (morning)
        self.assertEqual(VR.resolve_time("Em ơi chị dời sang 5h nha"), "17:00")
        self.assertEqual(VR.resolve_time("em oi chi doi sang 5h nha"), "17:00")


# ---------------------------------------------------------------- prices


class LoadPricesTest(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(PRICES["goi-dau-duong-sinh"], [{"duration_min": 60, "price_vnd": 150000, "time_window": None}])
        self.assertEqual(len(PRICES["massage-body-thu-gian"]), 3)
        self.assertEqual(PRICES["massage-chan"][1], {"duration_min": 45, "price_vnd": 250000,
                                                     "time_window": "09:00-24:00"})

    def test_missing_or_bad_file(self):
        self.assertEqual(VR.load_prices(Path(_TMP.name) / "nope.json"), {})
        bad = Path(_TMP.name) / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        self.assertEqual(VR.load_prices(bad), {})

    def test_real_catalog_loads(self):
        real = ROOT / "data" / "services.json"
        if real.exists():
            prices = VR.load_prices(real)
            self.assertTrue(prices)
            for rows in prices.values():
                for r in rows:
                    self.assertEqual(set(r), {"duration_min", "price_vnd", "time_window"})
                    self.assertIsInstance(r["price_vnd"], int)


# ---------------------------------------------------------------- 15.4 visit candidates


KEYS = {"date", "time", "time_known", "visited_at_local", "services", "amount_vnd", "amount_source", "technician",
        "confidence", "signals", "evidence_at", "source"}


class ExtractShapeTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(run([]), {"visits": [], "upcoming": [], "dropped": {"cancelled": 0, "no_show": 0},
                                   "anchor_ts": []})

    def test_duck_typed_messages(self):
        class M:
            def __init__(self, ts, from_owner, text, type):
                self.ts, self.from_owner, self.text, self.type = ts, from_owner, text, type
        msgs = [M(ms("2026-11-05 09:00"), False, "Mai 3h chị qua nha em", "text"),
                M(ms("2026-11-05 09:05"), True, "Dạ em giữ lịch cho chị ạ", "text"),
                M(ms("2026-11-06 15:00"), False, "Chị tới rồi", "text")]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-06"])

    def test_unsorted_input_is_sorted(self):
        msgs = [C("2026-11-06 15:00", "Chị tới rồi"), S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-05 09:00", "Mai 3h chị qua nha em")]
        out = run(msgs)
        self.assertEqual(out["visits"][0]["signals"], ["booking_request", "booking_confirmed", "arrival"])


class FullVisitTest(unittest.TestCase):
    MSGS = [
        C("2026-11-05 09:00", "Em ơi mai chị đặt lịch gội đầu dưỡng sinh lúc 3h chiều nha"),
        S("2026-11-05 09:10", "Dạ em đã giữ lịch 15h ngày mai cho chị ạ"),
        C("2026-11-06 14:55", "Chị tới rồi nha em"),
        S("2026-11-06 16:30", "Dạ em cảm ơn chị đã ghé ạ"),
    ]
    PLAIN = [
        C("2026-11-05 09:00", "em oi mai chi dat lich goi dau duong sinh luc 3h chieu nha"),
        S("2026-11-05 09:10", "da em da giu lich 15h ngay mai cho chi a"),
        C("2026-11-06 14:55", "chi den roi nha em"),
        S("2026-11-06 16:30", "da em cam on chi da ghe a"),
    ]

    def check(self, msgs):
        out = run(msgs)
        self.assertEqual(out["upcoming"], [])
        self.assertEqual(len(out["visits"]), 1)
        v = out["visits"][0]
        self.assertEqual(set(v), KEYS)
        self.assertEqual(v["date"], "2026-11-06")
        self.assertEqual(v["time"], "15:00")
        self.assertTrue(v["time_known"])
        self.assertEqual(v["visited_at_local"], "2026-11-06 15:00")
        self.assertEqual(v["confidence"], "high")
        self.assertEqual(v["signals"], ["booking_request", "booking_confirmed", "arrival", "after_visit"])
        self.assertEqual(v["source"], "chat_rules")
        self.assertEqual(v["services"][0], {"service_id": "goi-dau-duong-sinh", "service_name": "Gội đầu dưỡng sinh",
                                            "basis": "booking"})
        self.assertIsNone(v["technician"])
        self.assertIsNone(v["amount_vnd"])
        self.assertIsNone(v["amount_source"])
        self.assertTrue(set(v["evidence_at"]) <= {m.ts for m in msgs})
        self.assertLessEqual(len(v["evidence_at"]), 5)
        self.assertEqual(v["evidence_at"], sorted(v["evidence_at"]))
        self.assertEqual(out["anchor_ts"], sorted(m.ts for m in msgs))
        return v

    def test_with_diacritics(self):
        self.check(self.MSGS)

    def test_without_diacritics(self):
        self.check(self.PLAIN)

    def test_list_price_when_catalog_has_one_price(self):
        v = run(self.MSGS, prices=PRICES)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (150000, "list_price"))


class ConfidenceTest(unittest.TestCase):
    BOOK = [
        C("2026-11-09 10:00", "Mai 5h chiều chị qua massage body nha em"),
        S("2026-11-09 10:05", "Dạ vâng ạ, em giữ chỗ cho chị nha"),
    ]

    def test_confirmation_then_nothing_after_is_low(self):
        out = run(self.BOOK)
        v = out["visits"][0]
        self.assertEqual((v["date"], v["time"], v["confidence"]), ("2026-11-10", "17:00", "low"))
        self.assertEqual(v["signals"], ["booking_request", "booking_confirmed"])

    def test_confirmation_then_unrelated_chat_is_medium(self):
        out = run(self.BOOK + [C("2026-11-11 20:00", "Chị gửi em cái ảnh nha")])
        self.assertEqual(out["visits"][0]["confidence"], "medium")

    def test_non_text_message_after_slot_counts_as_later_message(self):
        out = run(self.BOOK + [C("2026-11-11 09:00", "", "sticker")])
        self.assertEqual(out["visits"][0]["confidence"], "medium")

    def test_message_before_slot_is_not_after_slot(self):
        out = run(self.BOOK + [C("2026-11-10 12:00", "Em ơi gửi chị địa chỉ nha")])
        self.assertEqual(out["visits"][0]["confidence"], "low")

    def test_booking_today_stays_low_even_with_later_message(self):
        msgs = [C("2026-11-12 08:00", "Sáng nay 10h chị qua massage chân nha"), S("2026-11-12 08:05", "Dạ vâng chị"),
                C("2026-11-12 12:00", "Chị gửi em cái ảnh")]
        out = run(msgs)
        self.assertEqual(out["visits"][0]["date"], "2026-11-12")
        self.assertEqual(out["visits"][0]["confidence"], "low")

    def test_unconfirmed_request_is_low(self):
        out = run([C("2026-11-03 10:00", "Mai chị đặt lịch 10h nha em"), C("2026-11-05 10:00", "Em ơi")])
        v = out["visits"][0]
        self.assertEqual((v["date"], v["confidence"], v["signals"]), ("2026-11-04", "low", ["booking_request"]))

    def test_request_plus_arrival_is_high(self):
        out = run([C("2026-11-03 10:00", "Mai 10h chị qua nha em"), C("2026-11-04 10:02", "Chị đến rồi em")])
        self.assertEqual(out["visits"][0]["confidence"], "high")

    def test_arrival_alone_is_medium(self):
        out = run([C("2026-11-04 10:02", "Chị đến rồi em ơi")])
        v = out["visits"][0]
        self.assertEqual((v["date"], v["confidence"], v["signals"]), ("2026-11-04", "medium", ["arrival"]))
        self.assertIsNone(v["time"])
        self.assertFalse(v["time_known"])
        self.assertEqual(v["visited_at_local"], "2026-11-04 12:00")

    def test_owner_thanks_alone_is_medium(self):
        out = run([S("2026-11-04 18:00", "Em cảm ơn chị đã ghé spa hôm nay ạ")])
        self.assertEqual(out["visits"][0]["confidence"], "medium")
        self.assertEqual(out["visits"][0]["signals"], ["after_visit"])

    def test_payment_with_arrival_is_high(self):
        out = run([C("2026-11-04 10:02", "Chị tới rồi"), C("2026-11-04 11:30", "ck 350k nha em")])
        v = out["visits"][0]
        self.assertEqual((v["confidence"], v["amount_vnd"], v["amount_source"]), ("high", 350000, "paid"))

    def test_spa_reminder_counts_as_confirmed(self):
        msgs = [S("2026-11-05 09:00", "Dạ em nhắc lịch hẹn của chị 3h chiều mai ạ"),
                C("2026-11-07 09:00", "Chị gửi em hình")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["date"], v["time"], v["signals"], v["confidence"]),
                         ("2026-11-06", "15:00", ["reminder"], "medium"))

    def test_spa_thanks_naming_yesterday(self):
        msgs = [C("2026-11-05 10:00", "Chiều nay 3h chị qua nha"), S("2026-11-05 10:01", "Dạ vâng ạ"),
                S("2026-11-06 09:00", "Dạ em cảm ơn chị hôm qua đã ghé ạ")]
        out = run(msgs)
        self.assertEqual([(v["date"], v["confidence"]) for v in out["visits"]], [("2026-11-05", "high")])

    def test_minutes_away_is_en_route(self):
        msgs = [C("2026-11-05 10:00", "Chiều nay 3h chị qua nha"), S("2026-11-05 10:01", "Dạ vâng ạ"),
                C("2026-11-05 14:50", "5 phút nữa chị tới nha em")]
        self.assertIn("en_route", run(msgs)["visits"][0]["signals"])

    def test_en_route_alone_makes_no_candidate(self):
        out = run([C("2026-11-04 10:02", "Chị đang qua nha em, kẹt xe xíu")])
        self.assertEqual(out["visits"], [])

    def test_en_route_with_booking_is_high(self):
        msgs = [C("2026-11-04 08:00", "Chiều nay 3h chị qua nha em"), S("2026-11-04 08:05", "Dạ vâng ạ"),
                C("2026-11-04 14:50", "Chị đang qua nha em, kẹt xe xíu")]
        v = run(msgs)["visits"][0]
        self.assertEqual(v["confidence"], "high")
        self.assertEqual(v["signals"], ["booking_request", "booking_confirmed", "en_route"])


class CancelRescheduleTest(unittest.TestCase):
    BOOK = [
        C("2026-11-03 09:00", "Thứ 7 chị đặt lịch massage chân 10h nha em"),
        S("2026-11-03 09:05", "Dạ em giữ lịch cho chị ạ"),
    ]

    def test_cancellation_with_date(self):
        out = run(self.BOOK + [C("2026-11-06 20:00", "Em ơi chị hủy lịch thứ 7 nha, chị bận")])
        self.assertEqual(out["visits"], [])
        self.assertEqual(out["upcoming"], [])
        self.assertEqual(out["dropped"], {"cancelled": 1, "no_show": 0})

    def test_cancellation_without_date_or_diacritics(self):
        out = run(self.BOOK + [C("2026-11-06 20:00", "em oi chi huy lich nha")])
        self.assertEqual(out["visits"], [])
        self.assertEqual(out["dropped"]["cancelled"], 1)

    def test_cannot_come_is_a_cancellation(self):
        out = run(self.BOOK + [C("2026-11-06 20:00", "Em ơi mai chị không qua được rồi, để hôm khác nha")])
        self.assertEqual(out["visits"], [])
        self.assertEqual(out["dropped"]["cancelled"], 1)

    def test_future_booking_cancelled_is_not_upcoming(self):
        msgs = [C("2026-11-12 09:00", "Thứ 7 chị đặt lịch 2h chiều nha em"), S("2026-11-12 09:05", "Dạ vâng chị"),
                C("2026-11-12 12:00", "Em ơi chị hủy lịch nha")]
        out = run(msgs)
        self.assertEqual((out["visits"], out["upcoming"]), ([], []))
        self.assertEqual(out["dropped"]["cancelled"], 1)

    def test_reschedule_to_another_day(self):
        msgs = [
            C("2026-11-02 09:00", "Thứ 5 chị qua gội đầu 3h nha em"),
            S("2026-11-02 09:05", "Dạ vâng chị"),
            C("2026-11-04 10:00", "Em ơi cho chị dời lịch sang thứ 6 nha, vẫn 3h"),
            S("2026-11-04 10:05", "Dạ ok chị"),
            C("2026-11-06 15:00", "Chị đến rồi"),
        ]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-06"])
        v = out["visits"][0]
        self.assertEqual((v["time"], v["confidence"]), ("15:00", "high"))
        self.assertIn("rescheduled", v["signals"])
        self.assertIn("booking_confirmed", v["signals"])
        self.assertEqual(out["dropped"]["cancelled"], 1)

    def test_reschedule_without_diacritics_by_the_spa(self):
        msgs = [
            C("2026-11-02 09:00", "thu 5 chi qua goi dau 3h nha em"),
            S("2026-11-02 09:05", "da vang chi"),
            S("2026-11-04 10:00", "chi oi em doi lich chi sang thu 6 3h nha"),
            C("2026-11-06 15:00", "chi den roi"),
        ]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-06"])
        self.assertEqual(out["visits"][0]["confidence"], "high")
        self.assertEqual(out["dropped"]["cancelled"], 1)

    def test_no_show(self):
        msgs = [
            C("2026-11-07 10:00", "Mai 10h chị qua nha"),
            S("2026-11-07 10:05", "Dạ em giữ lịch cho chị ạ"),
            S("2026-11-08 11:00", "Chị ơi em đợi chị mà không thấy chị qua ạ"),
            C("2026-11-08 12:00", "Chị xin lỗi, chị quên mất"),
        ]
        out = run(msgs)
        self.assertEqual(out["visits"], [])
        self.assertEqual(out["dropped"], {"cancelled": 0, "no_show": 1})

    def test_late_arrival_after_spa_nudge_is_not_no_show(self):
        msgs = [
            C("2026-11-07 10:00", "Mai 10h chị qua nha"),
            S("2026-11-07 10:05", "Dạ em giữ lịch cho chị ạ"),
            S("2026-11-08 10:20", "Chị ơi chị chưa qua ạ?"),
            C("2026-11-08 10:30", "Chị tới rồi nè"),
        ]
        out = run(msgs)
        self.assertEqual(out["visits"][0]["confidence"], "high")
        self.assertEqual(out["dropped"]["no_show"], 0)


class UpcomingTest(unittest.TestCase):
    def test_booking_after_analysis_date(self):
        msgs = [C("2026-11-12 09:00", "Thứ 7 chị đặt lịch 2h chiều nha em"),
                S("2026-11-12 09:05", "Dạ em giữ lịch thứ 7 lúc 14h cho chị ạ")]
        out = run(msgs)
        self.assertEqual(out["visits"], [])
        self.assertEqual(len(out["upcoming"]), 1)
        u = out["upcoming"][0]
        self.assertNotIn("confidence", u)
        self.assertEqual(set(u), KEYS - {"confidence"})
        self.assertEqual((u["date"], u["time"]), ("2026-11-14", "14:00"))

    def test_midnight_message_tomorrow(self):
        out = run([C("2026-11-12 00:10", "Mai chị qua 10h nha em"), S("2026-11-12 07:00", "Dạ vâng chị")])
        self.assertEqual(out["upcoming"][0]["date"], "2026-11-13")


class PaymentTest(unittest.TestCase):
    def test_ck_amount(self):
        msgs = [C("2026-11-10 10:00", "Chiều nay 4h chị qua massage chân nha"), S("2026-11-10 10:05", "Dạ vâng ạ"),
                C("2026-11-10 16:00", "Chị tới rồi"), C("2026-11-10 17:30", "ck 350k nha em")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["date"], v["confidence"]), ("2026-11-10", "high"))
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (350000, "paid"))
        self.assertEqual(v["signals"], ["booking_request", "booking_confirmed", "arrival", "payment"])

    def test_transfer_alone_makes_no_candidate(self):
        # deviation from the 15.4 text (R2, F3): a payment alone does not show a session (a package, a product, a
        # debt, a deposit); it only joins a booking, an arrival or a thanks of its day or the day before
        out = run([C("2026-11-11 19:00", "chị chuyển khoản 700.000 rồi nha")])
        self.assertEqual(out["visits"], [])
        out = run([C("2026-11-11 15:00", "Chị tới rồi"), C("2026-11-11 19:00", "chị chuyển khoản 700.000 rồi nha")])
        v = out["visits"][0]
        self.assertEqual((v["date"], v["confidence"], v["signals"]), ("2026-11-11", "high", ["arrival", "payment"]))
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (700000, "paid"))

    def test_payment_next_day_attaches_to_visit(self):
        msgs = [C("2026-11-08 10:00", "Mai 2h chị qua nha em"), S("2026-11-08 10:05", "Dạ vâng ạ"),
                C("2026-11-09 14:05", "Chị tới rồi"), C("2026-11-10 08:00", "chị ck 400k rồi nha em")]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-09"])
        self.assertEqual(out["visits"][0]["amount_vnd"], 400000)

    def test_spa_total_wins_and_formats(self):
        msgs = [C("2026-11-09 15:00", "Chị tới rồi"),
                S("2026-11-09 16:30", "Dạ gội 150k + massage chân 200k, tổng của chị là 350k ạ"),
                C("2026-11-09 16:40", "ok em chị ck rồi nha")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (350000, "paid"))

    def test_million_forms(self):
        for text, want in (("chị ck 1tr2 rồi nha", 1200000), ("chị chuyển khoản 1 triệu 2 rồi", 1200000),
                           ("ck 1.500.000đ nha em", 1500000), ("ck 350,000đ nha", 350000)):
            with self.subTest(text=text):
                v = run([C("2026-11-09 15:00", "Chị tới rồi"), C("2026-11-09 16:40", text)])["visits"][0]
                self.assertEqual(v["amount_vnd"], want)

    def test_payment_question_is_not_payment(self):
        out = run([C("2026-11-09 09:00", "Bên em có nhận chuyển khoản không?")])
        self.assertEqual(out["visits"], [])

    def test_not_payments(self):
        # "ck" is also the husband; a promise or a method is not a payment
        for text in ("ck chị đi công tác rồi", "chị muốn thanh toán bằng thẻ", "ck nha em"):
            with self.subTest(text=text):
                self.assertEqual(run([C("2026-11-09 09:00", text)])["visits"], [])

    def test_bill_at_the_session(self):
        out = run([C("2026-11-05 15:00", "Chị tới rồi"), C("2026-11-05 16:30", "em ơi tính tiền cho chị")])
        self.assertEqual(out["visits"][0]["signals"], ["arrival", "payment"])

    def test_spa_payment_request_with_account_number(self):
        msgs = [C("2026-11-05 15:00", "Chị tới rồi"),
                S("2026-11-05 16:30", "Dạ chị chuyển khoản 450k vào stk 0123456789 giúp em ạ")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (450000, "paid"))

    def test_same_day_deposit_is_not_a_payment(self):
        msgs = [C("2026-11-05 09:00", "Chiều nay 3h chị qua massage body nha em"),
                S("2026-11-05 09:05", "Dạ chị cọc giúp em 100k ạ"), C("2026-11-05 09:10", "chị ck cọc 100k rồi nha"),
                S("2026-11-05 09:12", "Dạ em giữ lịch cho chị ạ")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["confidence"], v["amount_vnd"]), ("low", None))
        self.assertNotIn("payment", v["signals"])

    def test_deposit_is_not_the_amount(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị đặt lịch nha"), S("2026-11-05 09:05", "Dạ chị cọc giúp em 100k ạ"),
                C("2026-11-05 09:10", "chị ck cọc 100k rồi nha"), C("2026-11-06 15:00", "Chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertEqual(v["date"], "2026-11-06")
        self.assertIsNone(v["amount_vnd"])
        self.assertNotIn("payment", v["signals"])


def paid(out):
    return [(v["date"], v["confidence"], v["signals"], v["amount_vnd"], v["amount_source"]) for v in out["visits"]]


class EarlyPaymentTest(unittest.TestCase):
    """S2: a walk-in's payment that comes before the arrival or the thanks of its day is kept: payment plus
    after_visit (or arrival) on D is high with the amount (15.4), whatever the order of the messages."""

    def test_payment_then_thanks_or_feedback_of_the_same_day(self):
        cases = {
            "spa total, transfer, named thanks": [
                S("2026-11-05 16:30", "Dạ tổng hôm nay 199k ạ"), C("2026-11-05 16:35", "chị chuyển khoản rồi nhé em"),
                S("2026-11-05 16:40", "Dạ em nhận rồi, cảm ơn chị đã ghé tiệm hôm nay ạ")],
            "transfer with amount, feedback": [
                C("2026-11-05 16:35", "chị ck 199k rồi nha em"), C("2026-11-05 18:00", "Hôm nay gội đầu thích lắm em")],
            "plain transfer, plain feedback": [
                C("2026-11-05 16:35", "c ck 199k r nha e"), C("2026-11-05 18:00", "hom nay goi dau thich lam e")],
            "transfer, thanks without a day word": [
                C("2026-11-05 16:35", "chị ck 199k rồi nha em"),
                S("2026-11-05 16:40", "Dạ chị về cẩn thận, cảm ơn chị đã ghé ạ")],
        }
        for name, msgs in cases.items():
            with self.subTest(case=name):
                out = paid(run(msgs))
                self.assertEqual(len(out), 1, out)
                d, conf, signals, amount, source = out[0]
                self.assertEqual((d, conf, amount, source), ("2026-11-05", "high", 199000, "paid"))
                self.assertEqual(signals[0], "payment")        # chronological: the payment came first
                self.assertIn("after_visit", signals)

    def test_payment_then_arrival_of_the_same_day(self):
        out = run([C("2026-11-05 13:00", "chị ck 199k rồi nha em"), C("2026-11-05 14:58", "chị tới rồi")])
        self.assertEqual(paid(out), [("2026-11-05", "high", ["payment", "arrival"], 199000, "paid")])

    def test_payment_then_thanks_of_the_next_day_for_that_day(self):
        out = run([C("2026-11-05 16:35", "chị ck 199k rồi nha em"),
                   S("2026-11-06 09:00", "Cảm ơn chị đã ghé tiệm hôm qua ạ")])
        self.assertEqual(paid(out), [("2026-11-05", "high", ["payment", "after_visit"], 199000, "paid")])

    def test_payment_of_the_next_day_joins_the_day_before(self):
        # 15.4: a payment on D+1 belongs to D; here the visit of D is stated after the payment
        out = run([C("2026-11-06 09:00", "chị ck 199k rồi nha em"),
                   C("2026-11-06 10:00", "hôm qua chị gội đầu thích lắm em")])
        self.assertEqual(paid(out), [("2026-11-05", "high", ["payment", "past_reference", "after_visit"], 199000,
                                      "paid")])
        out = run([C("2026-11-06 09:00", "hôm qua chị quên ck, giờ chị ck 199k rồi nha"),
                   C("2026-11-06 10:00", "hôm qua chị gội đầu thích lắm em")])
        self.assertEqual(paid(out)[0][:2] + paid(out)[0][3:], ("2026-11-05", "high", 199000, "paid"))

    def test_spa_receipt_and_thanks_in_one_message(self):
        out = run([S("2026-11-05 17:00", "Dạ em nhận được chuyển khoản 199k rồi ạ, cảm ơn chị đã ghé ạ")])
        self.assertEqual(paid(out), [("2026-11-05", "high", ["after_visit", "payment"], 199000, "paid")])

    def test_a_waiting_payment_never_makes_a_visit_alone(self):
        cases = {
            "alone": [C("2026-11-05 16:35", "chị ck 199k rồi nha em")],
            "booking only": [C("2026-11-05 09:00", "chị ck 199k rồi nha em"),
                             C("2026-11-05 10:00", "chiều nay 3h chị qua gội đầu nha"),
                             S("2026-11-05 10:05", "Dạ em giữ lịch cho chị ạ")],
            "price answer with thanks": [C("2026-11-05 09:00", "Gội đầu bao nhiêu em?"),
                                         S("2026-11-05 09:01", "Dạ 150k ạ, cảm ơn chị đã ghé ạ")],
            "total answering the price with thanks": [
                C("2026-11-05 09:00", "Gội đầu với massage chân bao nhiêu em?"),
                S("2026-11-05 09:01", "Dạ tổng 349k ạ, cảm ơn chị đã ghé ạ")],
            "account number request": [S("2026-11-05 09:00", "Dạ chị ck 360k vào stk 19033344455 giúp em nha")],
        }
        for name, msgs in cases.items():
            with self.subTest(case=name):
                out = run(msgs)
                self.assertFalse([v for v in out["visits"] if "payment" in v["signals"]], paid(out))
                self.assertFalse([v for v in out["visits"] if v["confidence"] == "high"], paid(out))

    def test_a_waiting_payment_joins_only_its_day_or_the_day_before(self):
        # a payment the evening before the visit (a prepayment) is not this visit's payment (F3)
        out = run([C("2026-11-05 21:00", "Chị ck trước 429k rồi nha em"), C("2026-11-06 15:00", "Chị tới rồi")])
        self.assertEqual(paid(out), [("2026-11-06", "medium", ["arrival"], None, None)])
        # the visit stated two days after the payment ("hôm kia"): too late to take it
        out = run([C("2026-11-05 16:00", "chị ck 199k rồi nha em"),
                   C("2026-11-07 10:00", "hôm kia chị gội đầu thích lắm em")])
        self.assertEqual(paid(out), [("2026-11-05", "medium", ["past_reference", "after_visit"], None, None)])

    def test_a_spa_total_without_a_receipt_word_stays_a_quote(self):
        out = run([S("2026-11-05 16:30", "Dạ tổng 199k ạ"),
                   S("2026-11-05 16:40", "Dạ em cảm ơn chị đã ghé tiệm hôm nay ạ")])
        self.assertEqual(paid(out), [("2026-11-05", "medium", ["after_visit"], None, None)])

    def test_a_cancelled_slot_is_not_reopened_by_a_waiting_payment(self):
        out = run([C("2026-11-04 09:00", "mai 3h chị qua gội nha"), S("2026-11-04 09:01", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-04 20:00", "hủy lịch mai nha em, chị bận"),
                   C("2026-11-05 16:00", "chị ck 199k rồi nha em"), S("2026-11-05 17:00", "Dạ cảm ơn chị đã ghé ạ")])
        self.assertEqual((out["visits"], out["dropped"]), ([], {"cancelled": 1, "no_show": 0}))


class PriceTest(unittest.TestCase):
    def test_price_inquiry_is_not_a_visit_or_amount(self):
        msgs = [C("2026-11-01 10:00", "Gội đầu dưỡng sinh giá bao nhiêu vậy em?"),
                S("2026-11-01 10:05", "Dạ gội đầu dưỡng sinh 60 phút bên em 150k ạ"),
                C("2026-11-01 10:10", "ok em, để chị sắp xếp")]
        out = run(msgs, prices=PRICES)
        self.assertEqual((out["visits"], out["upcoming"]), ([], []))
        self.assertIn(msgs[0].ts, out["anchor_ts"])
        self.assertIn(msgs[1].ts, out["anchor_ts"])

    def test_quote_in_the_booking_exchange_is_quoted(self):
        msgs = [C("2026-11-01 10:00", "Gội đầu dưỡng sinh giá bao nhiêu vậy em?"),
                S("2026-11-01 10:05", "Dạ 160k ạ"),
                C("2026-11-01 10:10", "Vậy mai 3h chị qua gội nha"),
                S("2026-11-01 10:12", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-02 15:00", "Chị tới rồi")]
        v = run(msgs, prices=PRICES)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (160000, "quoted"))

    def test_old_quote_is_not_tied_to_a_later_visit(self):
        msgs = [C("2026-10-01 10:00", "Gội đầu dưỡng sinh giá bao nhiêu vậy em?"),
                S("2026-10-01 10:05", "Dạ 160k ạ"),
                C("2026-11-01 10:10", "Mai 3h chị qua nha"),
                S("2026-11-01 10:12", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-02 15:00", "Chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertIsNone(v["amount_vnd"])

    def test_spa_price_list_is_not_an_amount_or_a_service(self):
        msgs = [S("2026-11-01 09:00",
                  "Bảng giá bên em ạ:\nGội đầu dưỡng sinh 150k\nMassage body 429k\nMassage chân 199k"),
                C("2026-11-01 09:30", "Mai chị qua gội đầu 3h nha"),
                S("2026-11-01 09:35", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-02 15:00", "Chị đến rồi")]
        v = run(msgs, prices=PRICES)["visits"][0]
        self.assertEqual(v["confidence"], "high")
        self.assertIsNone(v["amount_vnd"])
        self.assertIsNone(v["amount_source"])
        self.assertEqual(v["services"], [{"service_id": None, "service_name": "gội đầu", "basis": "booking"}])
        self.assertIn(msgs[0].ts, run(msgs)["anchor_ts"])

    def test_list_price_needs_one_price_for_the_named_duration(self):
        base = [S("2026-11-08 10:05", "Dạ vâng ạ"), C("2026-11-09 15:00", "Chị đến rồi")]
        v = run([C("2026-11-08 10:00", "Mai 3h chị qua massage chân 45 phút nha")] + base, prices=PRICES)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (250000, "list_price"))
        v = run([C("2026-11-08 10:00", "Mai 3h chị qua massage chân nha")] + base, prices=PRICES)["visits"][0]
        self.assertIsNone(v["amount_vnd"])
        # the time picks the time window: 60 minutes before 20:30 has one price
        v = run([C("2026-11-08 10:00", "Mai 3h chị qua massage body 60 phút nha")] + base, prices=PRICES)["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (429000, "list_price"))


class PastReferenceTest(unittest.TestCase):
    def test_yesterday_with_feedback(self):
        for text in ("hôm qua chị làm gội đầu thấy dễ chịu lắm", "hom qua chi lam goi dau thay de chiu lam"):
            with self.subTest(text=text):
                out = run([C("2026-11-12 10:00", text)])
                v = out["visits"][0]
                self.assertEqual((v["date"], v["confidence"]), ("2026-11-11", "medium"))
                self.assertIn("past_reference", v["signals"])
                self.assertEqual(v["services"][0]["service_name"], "gội đầu")
                self.assertIsNone(v["services"][0]["service_id"])

    def test_past_reference_joins_the_booking(self):
        msgs = [C("2026-11-09 10:00", "Mai 3h chị qua gội đầu nha"), S("2026-11-09 10:05", "Dạ vâng ạ"),
                C("2026-11-11 09:00", "Hôm qua chị làm gội đầu thích lắm em")]
        out = run(msgs)
        self.assertEqual(len(out["visits"]), 1)
        v = out["visits"][0]
        self.assertEqual((v["date"], v["confidence"]), ("2026-11-10", "high"))
        self.assertIn("past_reference", v["signals"])

    def test_vague_past_gives_nothing(self):
        out = run([C("2026-11-12 10:00", "lần trước chị làm gội đầu thấy dễ chịu lắm")])
        self.assertEqual(out["visits"], [])

    def test_inquiry_or_negation_or_third_person_is_not_a_visit(self):
        for text in ("hôm qua chị có hỏi giá gội đầu", "hôm qua chị bận không qua được",
                     "hôm qua bạn chị làm gội đầu bên em khen lắm"):
            with self.subTest(text=text):
                self.assertEqual(run([C("2026-11-12 10:00", text)])["visits"], [])


class TechnicianTest(unittest.TestCase):
    def test_named_with_cue(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị qua massage body, cho chị bạn Lan làm như lần trước nha"),
                S("2026-11-05 09:05", "Dạ em xếp bạn Lan cho chị ạ"),
                C("2026-11-06 15:00", "Chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertEqual(v["technician"], "Lan")
        self.assertEqual(v["services"][0]["service_id"], "massage-body-thu-gian")

    def test_numbered_technician(self):
        for text in ("Mai 3h chị qua, cho chị kỹ thuật viên số 8 nha", "mai 3h chi qua, cho chi ktv so 8 nhe"):
            with self.subTest(text=text):
                msgs = [C("2026-11-05 09:00", text), S("2026-11-05 09:05", "Dạ vâng chị"),
                        C("2026-11-06 15:00", "Chị tới rồi")]
                self.assertEqual(run(msgs)["visits"][0]["technician"], "số 8")

    def test_plain_spelling_with_cue(self):
        msgs = [C("2026-11-05 09:00", "mai 3h chi qua, cho chi ban Lan lam nhu lan truoc nha"),
                S("2026-11-05 09:05", "da vang chi"), C("2026-11-06 15:00", "chi den roi")]
        self.assertEqual(run(msgs)["visits"][0]["technician"], "Lan")

    def test_bare_name_is_not_a_technician(self):
        for text in ("Mai 3h chị qua với Lan nha", "Mai 3h chị qua nha, Lan cũng đi", "Mai 3h chị đi với bạn Lan nha"):
            with self.subTest(text=text):
                msgs = [C("2026-11-05 09:00", text), S("2026-11-05 09:05", "Dạ vâng chị"),
                        C("2026-11-06 15:00", "Chị tới rồi")]
                self.assertIsNone(run(msgs)["visits"][0]["technician"])


class MultiVisitTest(unittest.TestCase):
    def test_two_visits_weeks_apart(self):
        msgs = [C("2026-10-10 09:00", "Mai 10h chị qua gội đầu nha em"),
                S("2026-10-10 09:05", "Dạ em giữ lịch cho chị ạ"),
                C("2026-10-11 10:00", "Chị tới rồi"),
                C("2026-11-06 09:00", "Mai 4h chiều chị qua massage body nha"), S("2026-11-06 09:05", "Dạ vâng ạ"),
                C("2026-11-07 16:00", "Chị đến rồi")]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-10-11", "2026-11-07"])
        self.assertEqual([v["confidence"] for v in out["visits"]], ["high", "high"])
        self.assertEqual(out["visits"][0]["services"][0]["service_name"], "gội đầu")
        self.assertEqual(out["visits"][1]["services"][0]["service_id"], "massage-body-thu-gian")

    def test_one_candidate_per_date(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"), S("2026-11-05 09:05", "Dạ vâng ạ"),
                C("2026-11-05 20:00", "Mai chị đặt thêm massage chân 4h nha"), S("2026-11-05 20:05", "Dạ vâng chị"),
                C("2026-11-06 15:00", "Chị tới rồi")]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-06"])
        sig = out["visits"][0]["signals"]
        self.assertEqual(len(sig), len(set(sig)))


class SlotProposalTest(unittest.TestCase):
    def test_spa_proposes_contact_accepts(self):
        msgs = [C("2026-11-08 09:00", "Em ơi mai còn chỗ không?"),
                S("2026-11-08 09:05", "Dạ mai 3h còn trống chị nha"),
                C("2026-11-08 09:10", "ok em"),
                C("2026-11-09 15:00", "chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["date"], v["time"], v["confidence"]), ("2026-11-09", "15:00", "high"))
        self.assertEqual(v["signals"], ["booking_request", "booking_confirmed", "arrival"])

    def test_spa_proposes_without_answer_is_not_confirmed(self):
        msgs = [C("2026-11-08 09:00", "Em ơi mai còn chỗ không?"),
                S("2026-11-08 09:05", "Dạ mai 3h còn trống chị nha"),
                C("2026-11-11 10:00", "Em ơi")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["signals"], v["confidence"]), (["booking_request"], "low"))

    def test_counter_time_from_the_spa(self):
        msgs = [C("2026-11-08 09:00", "Mai 3h chị qua nha em"),
                S("2026-11-08 09:05", "Dạ 3h kín rồi chị ơi, 4h được không ạ"),
                C("2026-11-08 09:10", "dạ được em"),
                C("2026-11-09 16:00", "chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["time"], v["confidence"]), ("16:00", "high"))

    def test_contact_gives_the_day_in_a_second_message(self):
        msgs = [C("2026-11-08 09:00", "Em ơi chị muốn đặt lịch gội đầu"),
                C("2026-11-08 09:01", "Thứ 7 2h chiều nha em"),
                S("2026-11-08 09:30", "Dạ vâng chị"),
                C("2026-11-14 14:00", "Chị tới rồi")]
        v = run(msgs, now=ms("2026-11-15 10:00"))["visits"][0]
        self.assertEqual((v["date"], v["confidence"]), ("2026-11-14", "high"))
        self.assertEqual(v["services"][0]["basis"], "booking")

    def test_day_word_after_a_finished_booking_is_not_a_request(self):
        msgs = [C("2026-11-08 09:00", "Mai 3h chị đặt lịch nha"), S("2026-11-08 09:01", "Dạ vâng chị"),
                C("2026-11-08 09:30", "Mai chị đi làm sớm nên chiều mới rảnh")]
        out = run(msgs)
        self.assertEqual([v["date"] for v in out["visits"]], ["2026-11-09"])

    def test_explicit_date_wins_in_the_same_clause(self):
        self.assertEqual(day("thứ 7 15/11 chị qua", "2026-11-12 10:00"), "2026-11-15")
        self.assertEqual(day("mai chị qua, 20/11 chị qua lần nữa", "2026-11-12 10:00"), "2026-11-13")

    def test_spa_outreach_proposal_accepted(self):
        msgs = [S("2026-11-05 09:00", "Chị ơi mai bên em còn trống 3h, chị qua không ạ?"),
                C("2026-11-05 09:10", "ok em"),
                C("2026-11-06 15:00", "chị tới rồi")]
        v = run(msgs)["visits"][0]
        self.assertEqual((v["time"], v["confidence"]), ("15:00", "high"))
        self.assertEqual(v["signals"], ["booking_confirmed", "arrival"])

    def test_price_answer_or_greeting_does_not_confirm(self):
        for reply in ("Dạ 150k ạ", "Dạ em chào chị ạ"):
            with self.subTest(reply=reply):
                msgs = [C("2026-11-05 09:00", "Mai 3h chị qua gội đầu được không em?"), S("2026-11-05 09:05", reply)]
                self.assertEqual(run(msgs)["visits"][0]["signals"], ["booking_request"])

    def test_same_day_time_change(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị qua nha"), S("2026-11-05 09:01", "Dạ vâng ạ"),
                C("2026-11-05 20:00", "Em ơi chị dời sang 5h nha"), S("2026-11-05 20:01", "Dạ ok chị"),
                C("2026-11-06 17:00", "Chị tới rồi")]
        out = run(msgs)
        self.assertEqual([(v["date"], v["time"]) for v in out["visits"]], [("2026-11-06", "17:00")])
        self.assertEqual(out["dropped"]["cancelled"], 0)

    def test_date_given_after_the_spa_asks(self):
        msgs = [C("2026-11-08 09:00", "Chị muốn đặt lịch gội đầu"),
                S("2026-11-08 09:05", "Dạ chị muốn qua ngày nào ạ?"),
                C("2026-11-08 09:10", "Thứ 7 2h chiều nha em"),
                S("2026-11-08 09:12", "Dạ vâng chị"),
                C("2026-11-14 14:00", "Chị tới rồi")]
        v = run(msgs, now=ms("2026-11-15 10:00"))["visits"][0]
        self.assertEqual((v["date"], v["time"], v["confidence"]), ("2026-11-14", "14:00", "high"))


class FilterTest(unittest.TestCase):
    def test_spa_mentions_another_customers_appointment(self):
        msgs = [S("2026-11-10 10:00", "Dạ mai 3h bên em có khách đặt lịch rồi chị ạ"),
                S("2026-11-10 10:01", "Lịch hẹn của khách: 15h thứ 7, massage body"),
                C("2026-11-10 10:05", "ok em")]
        out = run(msgs)
        self.assertEqual((out["visits"], out["upcoming"]), ([], []))

    def test_health_vocabulary_is_still_used(self):
        msgs = [C("2026-11-09 10:00", "Mai 3h chị qua massage cổ vai gáy nha em, dạo này chị bị đau lưng quá"),
                S("2026-11-09 10:05", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-10 15:05", "Chị tới rồi")]
        self.assertTrue(AC.has_health(AC.nfc_lower(msgs[0].text), AC.fold(AC.nfc_lower(msgs[0].text))))
        v = run(msgs)["visits"][0]
        self.assertEqual((v["date"], v["confidence"]), ("2026-11-10", "high"))
        self.assertEqual(v["services"][0]["service_id"], "massage-co-vai-gay")

    def test_service_the_spa_does_not_offer(self):
        out = run([C("2026-11-09 10:00", "Mai 3h chị qua làm nail nha em"), S("2026-11-09 10:05", "Dạ vâng chị")])
        self.assertEqual(out["visits"], [])

    def test_output_holds_no_text(self):
        msgs = FullVisitTest.MSGS
        blob = json.dumps(run(msgs), ensure_ascii=False)
        for m in msgs:
            self.assertNotIn(m.text, blob)
        self.assertNotIn("Chị tới", blob)

    def test_chitchat_is_not_an_anchor(self):
        msgs = [C("2026-11-09 10:00", "Chị ăn cơm chưa"), C("2026-11-09 10:05", "Hôm nay trời đẹp ghê")]
        out = run(msgs)
        self.assertEqual(out, {"visits": [], "upcoming": [], "dropped": {"cancelled": 0, "no_show": 0},
                               "anchor_ts": []})


# ---------------------------------------------------------------- review findings (dates lens F1-F13)


def vis(out):
    return [(v["date"], v["confidence"], v["signals"]) for v in out["visits"]]


class DateFindingTest(unittest.TestCase):
    def test_f1_number_ranges_are_not_dates(self):
        for text, want in (("tầm 3-4 chiều mai chị qua", "2026-11-13"), ("tam 3-4 chieu mai chi qua", "2026-11-13"),
                           ("chắc 2-3 hôm nữa chị qua", None), ("khoảng 1-2 tuần nữa chị qua", None),
                           ("mai 9-10h chị qua", "2026-11-13"), ("từ 5-6 chị qua", None)):
            with self.subTest(text=text):
                self.assertEqual(day(text, "2026-11-12 10:00"), want)
        out = run([C("2026-11-05 09:00", "Em ơi tầm 3-4 chiều mai chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ vâng chị, em giữ lịch cho chị ạ"),
                   C("2026-11-06 15:02", "Chị tới rồi nha em")])
        self.assertEqual((vis(out), out["upcoming"]),
                         ([("2026-11-06", "high", ["booking_request", "booking_confirmed", "arrival"])], []))
        out = run([C("2026-11-05 09:00", "Chắc 2-3 hôm nữa chị qua làm gội đầu nha em"),
                   S("2026-11-05 09:05", "Dạ vâng chị ạ")])
        self.assertEqual((out["visits"], out["upcoming"]), ([], []))

    def test_f1_dash_and_dot_dates_that_stay_dates(self):
        for text, want in (("15-11", "2026-11-15"), ("15.11", "2026-11-15"), ("ngày 5-12 chị qua", "2026-12-05"),
                           ("5.12.2026 chị qua", "2026-12-05"), ("20/11 chị qua", "2026-11-20")):
            with self.subTest(text=text):
                self.assertEqual(day(text, "2026-11-12 10:00"), want)

    def test_f2_spa_total_answering_a_price_question_is_a_quote(self):
        for reply in ("Dạ gội đầu 150k, massage chân 199k, tổng là 349k ạ", "Dạ tổng 349k ạ",
                      "Dạ làm cả hai thì hết 349k chị nha", "da goi dau 150k, massage chan 199k, tong la 349k a"):
            with self.subTest(reply=reply):
                out = run([C("2026-11-05 20:00", "Gội đầu với massage chân bao nhiêu em?"),
                           S("2026-11-05 20:05", reply)])
                self.assertEqual(out["visits"], [])
        # the same total after the session is the bill
        out = run([C("2026-11-05 15:00", "Chị tới rồi"), S("2026-11-05 16:30", "Dạ tổng 349k ạ")])
        v = out["visits"][0]
        self.assertEqual((v["signals"], v["amount_vnd"], v["amount_source"]), (["arrival", "payment"], 349000, "paid"))
        # a quote before the session, answering the price question, is not a payment for the booked visit
        out = run([C("2026-11-05 09:00", "Chiều nay 3h chị qua gội đầu với massage chân nha, hết bao nhiêu em?"),
                   S("2026-11-05 09:05", "Dạ tổng 349k ạ, em giữ lịch cho chị nha")])
        self.assertNotIn("payment", out["visits"][0]["signals"])

    def test_f3_payment_that_is_not_for_a_session_makes_no_candidate(self):
        cases = {
            "prepay": [C("2026-11-05 09:00", "Mai 3h chị qua massage body nha em"),
                       S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                       C("2026-11-05 21:00", "Chị ck trước 429k rồi nha em"), C("2026-11-06 15:00", "Chị tới rồi")],
            "late": [C("2026-11-05 09:00", "Chiều nay 3h chị qua gội đầu nha"), S("2026-11-05 09:05", "Dạ vâng ạ"),
                     C("2026-11-05 15:00", "Chị tới rồi"),
                     C("2026-11-08 20:00", "Em ơi chị ck 150k rồi nha, hôm bữa chị quên")],
            "package": [C("2026-11-05 20:00", "Chị ck 3 triệu mua gói 10 buổi rồi nha em")],
            "product": [C("2026-11-05 20:00", "Chị ck 250k tiền chai dầu gội rồi nha em")],
            "husband": [C("2026-11-05 20:00", "Ck chị về rồi em, nói chuyện sau nha")],
        }
        for name, msgs in cases.items():
            with self.subTest(case=name):
                out = run(msgs)
                self.assertFalse([v for v in out["visits"] if v["signals"] == ["payment"]], vis(out))
                self.assertLessEqual(len(out["visits"]), 1)

    def test_f4_yesterday_without_the_spa_is_not_a_visit(self):
        for msg in (C("2026-11-05 20:00", "Hôm qua chị đi làm về mệt quá em"),
                    C("2026-11-05 20:00", "Hôm qua chị qua nhà bạn chơi"),
                    S("2026-11-05 09:00", "Dạ hôm qua em nghỉ làm nên không trả lời chị được ạ")):
            with self.subTest(text=msg.text):
                self.assertEqual(run([msg])["visits"], [])

    def test_f5_spa_broadcasts_are_not_visits(self):
        for msgs in ([S("2026-11-05 09:00", "Thom House cảm ơn chị đã sử dụng dịch vụ bên em trong thời gian qua ạ")],
                     [S("2026-11-05 09:00", "Nhân dịp 20/11, Thom House cảm ơn chị đã ghé thăm và ủng hộ bên em ạ")],
                     [S("2026-11-01 09:00", "Chị đừng quên chương trình tri ân ngày 5/11 bên em nha"),
                      C("2026-11-08 09:00", "Dạ")]):
            with self.subTest(text=msgs[0].text):
                self.assertEqual(run(msgs)["visits"], [])

    BOOK = [C("2026-11-03 09:00", "Thứ 7 chị đặt lịch 10h nha"), S("2026-11-03 09:05", "Dạ em giữ lịch cho chị ạ")]

    def test_f6_cancellations_are_not_lost(self):
        out = run(self.BOOK + [C("2026-11-05 09:00", "Em ơi chị hủy lịch nha, mai chị bận rồi"),
                               S("2026-11-05 09:05", "Dạ vâng chị"), C("2026-11-09 09:00", "Chị gửi em hình nha")])
        self.assertEqual((out["visits"], out["dropped"]["cancelled"]), ([], 1))
        out = run([C("2026-11-06 20:00", "Thứ 7 10h chị qua nha"), S("2026-11-06 20:05", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-07 08:00", "Em ơi hủy lịch thứ 7 giúp chị nha"), S("2026-11-07 08:05", "Dạ vâng chị"),
                   C("2026-11-09 09:00", "Chị gửi em hình nha")])
        self.assertEqual((out["visits"], out["dropped"]["cancelled"]), ([], 1))
        # a spa reminder sent after the contact cancelled does not reopen the booking
        out = run(self.BOOK + [C("2026-11-05 09:00", "Em ơi chị hủy lịch thứ 7 nha"),
                               S("2026-11-05 09:05", "Dạ vâng chị"),
                               S("2026-11-06 20:00", "Dạ em nhắc lịch hẹn của chị 10h sáng mai ạ"),
                               C("2026-11-09 09:00", "Chị gửi em hình nha")])
        self.assertEqual((out["visits"], out["dropped"]["cancelled"]), ([], 1))

    def test_f7_a_service_change_or_next_time_is_not_a_cancellation(self):
        base = [C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha em"),
                S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ")]
        for extra in ([C("2026-11-05 20:00", "Em ơi mai chị đổi sang massage body nha"),
                       S("2026-11-05 20:05", "Dạ vâng chị")],
                      [C("2026-11-05 09:30", "Mà massage body bao nhiêu em, để lần sau chị làm"),
                       S("2026-11-05 09:31", "Dạ 429k ạ")],
                      [C("2026-11-05 20:00", "chi moi doi sang khu Vinhomes nha e")]):
            with self.subTest(text=extra[0].text):
                out = run(base + extra + [C("2026-11-08 09:00", "Chị gửi em hình nha")])
                self.assertEqual(vis(out), [("2026-11-06", "medium", ["booking_request", "booking_confirmed"])])
                self.assertEqual(out["dropped"]["cancelled"], 0)
        # a reschedule that names the new time still moves the slot
        out = run(base + [C("2026-11-05 20:00", "Em ơi chị dời sang 5h nha"), S("2026-11-05 20:01", "Dạ ok chị"),
                          C("2026-11-06 17:00", "Chị tới rồi")])
        self.assertEqual([(v["date"], v["time"]) for v in out["visits"]], [("2026-11-06", "17:00")])

    def test_f8_a_price_for_another_service_is_not_the_quote(self):
        out = run([C("2026-11-05 09:00", "Gội đầu dưỡng sinh bao nhiêu em"), S("2026-11-05 09:01", "Dạ 150k ạ"),
                   C("2026-11-05 09:02", "Còn massage body thư giãn bao nhiêu"), S("2026-11-05 09:03", "Dạ 429k ạ"),
                   C("2026-11-05 09:10", "Ok mai 3h chị qua gội đầu thôi nha"),
                   S("2026-11-05 09:12", "Dạ em giữ lịch cho chị ạ"), C("2026-11-06 15:00", "Chị tới rồi")])
        v = out["visits"][0]
        self.assertEqual((v["amount_vnd"], v["amount_source"]), (150000, "quoted"))
        self.assertNotIn("massage-body-thu-gian", [s["service_id"] for s in v["services"]])
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-05 09:30", "Mà massage body bao nhiêu em, để lần sau chị làm"),
                   S("2026-11-05 09:31", "Dạ 429k ạ"), C("2026-11-06 15:00", "Chị tới rồi")])
        v = out["visits"][0]
        self.assertEqual((v["amount_vnd"], v["signals"]), (None, ["booking_request", "booking_confirmed", "arrival"]))

    def test_f9_a_booking_for_someone_else_is_not_the_contacts_visit(self):
        cases = ([C("2026-11-05 09:00", "Em ơi đặt cho mẹ chị 3h chiều mai gội đầu nha"),
                  S("2026-11-05 09:05", "Dạ em giữ lịch cho bác ạ"), C("2026-11-06 15:00", "Mẹ chị tới rồi đó em")],
                 [C("2026-11-05 20:00", "Em ơi đặt giúp bạn chị 3h chiều mai gội đầu nha"),
                  S("2026-11-05 20:05", "Dạ em giữ lịch cho bạn chị ạ"),
                  C("2026-11-07 09:00", "Bạn chị khen bên em lắm")],
                 [C("2026-11-05 20:00", "Mai ck chị qua massage body nha em"),
                  S("2026-11-05 20:05", "Dạ em giữ lịch cho anh ạ"), C("2026-11-06 15:00", "Ck chị tới rồi em")])
        for msgs in cases:
            with self.subTest(text=msgs[0].text):
                out = run(msgs)
                self.assertFalse([v for v in out["visits"] if v["confidence"] in ("high", "medium")], vis(out))
        # the contact comes too: still the contact's visit
        out = run([C("2026-11-05 09:00", "Mai 3h chị với bạn chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"), C("2026-11-06 15:00", "Chị tới rồi")])
        self.assertEqual(vis(out)[0][1], "high")
        # another person named in another clause does not hide the contact's cancellation
        out = run([C("2026-11-01 10:00", "mai 9h c qua goi dau nha e"),
                   S("2026-11-01 10:01", "Dạ em giữ lịch 9h mai cho chị ạ"),
                   C("2026-11-01 22:00", "e oi mai c ko qua dc r, con c bi om")])
        self.assertEqual((out["visits"], out["dropped"]["cancelled"]), ([], 1))

    def test_f10_technician_number_and_next_time(self):
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ, có gì chị gọi nhân viên số 0912345678 nha"),
                   C("2026-11-06 15:00", "Chị tới rồi")])
        self.assertIsNone(out["visits"][0]["technician"])
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-06 15:00", "Chị tới rồi"), C("2026-11-07 09:00", "Lần sau cho chị bạn Hoa làm nha em")])
        self.assertIsNone(out["visits"][0]["technician"])
        for text in ("ktv số ² làm cho chị nha", "Dạ hôm nay nhân viên số 0938271645 làm cho chị ạ"):
            with self.subTest(text=text):
                out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"), S("2026-11-05 09:05", "Dạ vâng chị"),
                           C("2026-11-06 15:00", "Chị tới rồi"), S("2026-11-06 16:00", text)])
                self.assertEqual((out["visits"][0]["confidence"], out["visits"][0]["technician"]), ("high", None))

    def test_f11_night_and_hour_ranges(self):
        for text, want in (("12h đêm", "00:00"), ("11h đêm", "23:00"), ("tầm 3-4h chiều", "15:00"),
                           ("mai 9-10h chị qua", "09:00"), ("1h đêm", "01:00"), ("3h - 4h chiều", "15:00")):
            with self.subTest(text=text):
                self.assertEqual(VR.resolve_time(text), want)

    def test_f12_tokens_that_look_like_dates(self):
        out = run([C("2026-11-05 09:00", "Mai 8.12 chị qua gội đầu nha em"),
                   S("2026-11-05 09:05", "Dạ vâng chị, em giữ lịch cho chị ạ")])
        self.assertEqual((out["upcoming"], [v["date"] for v in out["visits"]]), ([], ["2026-11-06"]))
        for text in ("mai 10.10 chị qua", "Em ơi chị muốn đặt mã T7 nha", "mã T7 còn không em",
                     "15/11 âm lịch chị qua", "chị ở 15/11 Lê Lợi", "size t5 nha"):
            with self.subTest(text=text):
                want = "2026-11-13" if text.startswith("mai") else None
                self.assertEqual(day(text, "2026-11-12 10:00"), want)


class MutationGuardTest(unittest.TestCase):
    """F13: one test for every rule a surviving mutant showed untested."""

    def test_evidence_keeps_at_most_five_of_the_highest_priority(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha em"),
                S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                C("2026-11-06 14:50", "Chị đang qua nha"), C("2026-11-06 15:00", "Chị tới rồi"),
                C("2026-11-06 16:30", "Chị ck 150k rồi nha"), S("2026-11-06 17:00", "Dạ em cảm ơn chị đã ghé ạ"),
                C("2026-11-06 20:00", "Gội thích lắm em")]
        v = run(msgs)["visits"][0]
        self.assertEqual(len(v["evidence_at"]), 5)
        self.assertEqual(v["evidence_at"], sorted(m.ts for m in msgs[2:]))

    def test_services_keeps_at_most_three(self):
        msgs = [C("2026-11-05 09:00", "Mai 3h chị qua gội đầu dưỡng sinh, massage body thư giãn, massage chân và "
                                      "chăm sóc da cơ bản nha"),
                S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"), C("2026-11-06 15:00", "Chị tới rồi")]
        self.assertEqual(len(run(msgs)["visits"][0]["services"]), 3)

    def test_past_reference_alone_is_medium(self):
        v = run([C("2026-11-12 10:00", "hôm qua chị qua làm gội đầu rồi")])["visits"][0]
        self.assertEqual((v["date"], v["confidence"], v["signals"]), ("2026-11-11", "medium", ["past_reference"]))

    def test_day_part_boundaries(self):
        for text, want in (("chiều 6h", "18:00"), ("tối 5h", "17:00"), ("tối 11h", "23:00"), ("trưa 2h", "14:00"),
                           ("24h", None), ("sáng 11h", "11:00")):
            with self.subTest(text=text):
                self.assertEqual(VR.resolve_time(text), want)

    def test_same_weekday_at_the_same_time_is_next_week(self):
        self.assertEqual(day("thứ 5 3h chị qua", "2026-11-12 15:00"), "2026-11-19")
        self.assertEqual(day("thứ 5 3h chị qua", "2026-11-12 14:59"), "2026-11-12")

    def test_explicit_dates_on_the_message_day(self):
        self.assertEqual(day("12/11 chị làm rồi", "2026-11-12 10:00", past=True), "2026-11-12")
        self.assertEqual(day("ngày 12 chị qua", "2026-11-12 10:00"), "2026-11-12")
        self.assertEqual(day("ngày 12 chị làm rồi", "2026-11-12 10:00", past=True), "2026-11-12")

    def test_a_date_inside_a_phone_number_is_not_a_date(self):
        self.assertIsNone(day("sdt 0912 15-11 678 nha", "2026-11-12 10:00"))
        self.assertIsNone(day("sdt 0912 15/11 678 nha", "2026-11-12 10:00"))

    def test_spa_side_cancellation(self):
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                   S("2026-11-05 20:00", "Dạ em hủy lịch cho chị rồi nha"), C("2026-11-08 09:00", "Chị gửi em hình")])
        self.assertEqual((out["visits"], out["dropped"]), ([], {"cancelled": 1, "no_show": 0}))

    def test_cancel_after_the_slot_is_a_no_show(self):
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-06 18:00", "Em ơi chị hủy lịch nha, chị quên")])
        self.assertEqual((out["visits"], out["dropped"]), ([], {"cancelled": 0, "no_show": 1}))

    def test_total_wins_over_a_later_smaller_transfer(self):
        out = run([C("2026-11-05 15:00", "Chị tới rồi"), S("2026-11-05 16:30", "Dạ tổng của chị 350k ạ"),
                   C("2026-11-05 16:40", "chị ck 300k rồi nha")])
        self.assertEqual(out["visits"][0]["amount_vnd"], 350000)

    def test_a_promotion_in_the_exchange_is_not_a_quote(self):
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"),
                   S("2026-11-05 09:01", "Dạ bên em đang khuyến mãi gội đầu 99k ạ"),
                   S("2026-11-05 09:05", "Dạ em giữ lịch cho chị ạ"), C("2026-11-06 15:00", "Chị tới rồi")])
        self.assertIsNone(out["visits"][0]["amount_vnd"])

    def test_a_name_without_a_performer_is_not_a_technician(self):
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha, em Lan nhớ nha"),
                   S("2026-11-05 09:05", "Dạ vâng chị"), C("2026-11-06 15:00", "Chị tới rồi")])
        self.assertIsNone(out["visits"][0]["technician"])

    def test_come_over_is_not_yesterday(self):
        self.assertIsNone(day("tối qua nha em", "2026-11-12 10:00", past=True))
        self.assertEqual(day("tối qua chị làm rồi", "2026-11-12 10:00", past=True), "2026-11-11")

    def test_a_booking_more_than_180_days_ahead_is_ignored(self):
        out = run([C("2026-11-05 09:00", "Ngày 15/7/2027 chị đặt lịch gội đầu nha"),
                   S("2026-11-05 09:05", "Dạ vâng chị")])
        self.assertEqual((out["visits"], out["upcoming"]), ([], []))

    def test_later_message_must_come_within_72_hours_and_not_ask_the_address(self):
        book = [C("2026-11-01 10:00", "Mai 5h chiều chị qua massage body nha em"),
                S("2026-11-01 10:05", "Dạ vâng ạ, em giữ chỗ cho chị nha")]
        self.assertEqual(run(book + [C("2026-11-05 16:00", "Chị gửi em hình nha")])["visits"][0]["confidence"],
                         "medium")
        self.assertEqual(run(book + [C("2026-11-05 18:00", "Chị gửi em hình nha")])["visits"][0]["confidence"], "low")
        self.assertEqual(run(book + [C("2026-11-03 09:00", "Em ơi địa chỉ bên em ở đâu vậy")])["visits"][0]
                         ["confidence"], "low")
        self.assertEqual(run(book + [S("2026-11-03 09:00", "Chị ơi bên em có ưu đãi mới ạ")])["visits"][0]
                         ["confidence"], "low")              # a spa message is not the contact's

    def test_a_spa_confirmation_after_the_contact_cancelled_does_not_reopen(self):
        out = run([C("2026-11-03 09:00", "Thứ 7 chị đặt lịch 10h nha"),
                   S("2026-11-03 09:05", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-05 09:00", "Em ơi chị hủy lịch thứ 7 nha"),
                   S("2026-11-05 12:00", "Dạ em giữ lịch thứ 7 10h cho chị nha"),
                   C("2026-11-09 09:00", "Chị gửi em hình nha")])
        self.assertEqual((out["visits"], out["dropped"]["cancelled"]), ([], 1))

    def test_yesterday_needs_the_spa_or_a_service(self):
        self.assertEqual(run([C("2026-11-12 10:00", "Hôm qua chị qua chơi với bạn vui lắm em")])["visits"], [])
        self.assertEqual(run([C("2026-11-12 10:00", "Hôm qua chị ghé rồi")])["visits"], [])
        v = run([C("2026-11-12 10:00", "Hôm qua chị ghé tiệm rồi")])["visits"][0]
        self.assertEqual((v["date"], v["confidence"]), ("2026-11-11", "medium"))

    def test_a_contact_message_exactly_at_the_slot_is_not_after_it(self):
        book = [C("2026-11-09 10:00", "Mai 5h chiều chị qua massage body nha em"),
                S("2026-11-09 10:05", "Dạ vâng ạ, em giữ chỗ cho chị nha")]
        self.assertEqual(run(book + [C("2026-11-10 17:00", "", "sticker")])["visits"][0]["confidence"], "low")
        self.assertEqual(run(book + [C("2026-11-10 17:01", "", "sticker")])["visits"][0]["confidence"], "medium")


# ---------------------------------------------------------------- review findings (recall lens R1-R15)


class RecallFindingTest(unittest.TestCase):
    TS = "2026-11-11 20:00"

    def test_r1_past_reference_needs_the_spa(self):
        for text in ("hom qua c qua nha me nen ko rep e duoc", "hôm qua chị qua nhà mẹ nên không rep em được",
                     "hom qua c di dam cuoi ve muon qua", "hom qua c dinh qua ma ket viec",
                     "hôm qua chị ghé mà tiệm đóng cửa", "hôm qua chị đi massage chỗ khác rồi",
                     "hôm nay chị đi gội đầu ở tiệm gần nhà rồi", "hôm qua chị qua ngang tiệm thấy đông quá nên về",
                     "hom qua c den cong ty tre nen met", "hôm qua chị đến bệnh viện khám",
                     "chiều qua chị qua chỗ em mà không có ai"):
            with self.subTest(text=text):
                self.assertEqual(run([C(self.TS, text)])["visits"], [])
        for text in ("hôm qua chị làm gội đầu thích lắm em", "hom qua c qua goi dau thich lam",
                     "hôm qua chị massage xong ngủ ngon ghê", "hôm qua chị qua làm mặt, giờ da mịn lắm"):
            with self.subTest(text=text):
                self.assertEqual(vis(run([C(self.TS, text)]))[0][:2], ("2026-11-10", "medium"))

    def test_r2_payment_alone_is_no_visit(self):
        for msg in (C("2026-10-20 09:00", "c ck coc r nha e"), S("2026-10-20 09:00", "Dạ em chuyển rồi ạ"),
                    S("2026-10-20 09:00", "Dạ chị ck 360k vào stk 19033344455 giúp em nha"),
                    S("2026-10-20 09:00", "Chị ck giúp em 360k nha chị"), C("2026-10-20 09:00", "ck c ve r"),
                    C("2026-10-20 09:00", "ck c di lam r e"),
                    C("2026-10-20 09:00", "e oi c mua 2 hop tra 200k, c ck r nha")):
            with self.subTest(text=msg.text):
                self.assertEqual(run([msg])["visits"], [])
        # a spa refund on the visit day is not a payment either
        out = run([C("2026-10-20 15:00", "Chị tới rồi"), S("2026-10-20 18:00", "Dạ em chuyển lại tiền cọc rồi ạ")])
        self.assertEqual(vis(out), [("2026-10-20", "medium", ["arrival"])])

    def test_r3_bookings_for_a_friend_or_the_husband(self):
        for msgs in ([C("2026-11-06 09:00", "e oi mai 2h dat lich cho ban c 1 suat goi dau nhe"),
                      S("2026-11-06 09:01", "Dạ em giữ lịch 2h mai cho bạn chị ạ"),
                      S("2026-11-07 14:05", "Dạ bạn chị tới rồi ạ"),
                      C("2026-11-07 16:00", "c ck cho ban c 199k nha e")],
                     [C("2026-11-02 09:00", "e oi ck c mai qua massage body luc 5h chieu nha"),
                      S("2026-11-02 09:01", "Dạ em giữ lịch 5h chiều mai cho anh ạ"),
                      C("2026-11-03 20:00", "ck c ve r, cam on e nhe")]):
            with self.subTest(text=msgs[0].text):
                self.assertEqual(run(msgs)["visits"], [])

    def test_r4_arrival_words_in_other_senses(self):
        for msg in (C("2026-10-20 09:00", "Hàng đến rồi nha em, chị nhận được rồi"),
                    C("2026-10-20 09:00", "hang den r nha e"),
                    C("2026-10-20 09:00", "Chị đang ở cửa hàng quần áo, tí chị nhắn lại"),
                    C("2026-10-20 09:00", "c o duoi que nen song yeu"), C("2026-10-20 09:00", "chị ở dưới quê mới lên"),
                    C("2026-10-20 09:00", "Mùa mưa tới rồi em"),
                    C("2026-10-20 09:00", "c dang o truoc cong truong don con"),
                    S("2026-10-20 09:00", "Dạ mời chị vào nhóm Zalo của tiệm ạ"),
                    S("2026-10-20 09:00", "Chị vào luôn link này để xem bảng giá ạ"),
                    C("2026-10-20 09:00", "Giá lên rồi hả em")):
            with self.subTest(text=msg.text):
                self.assertEqual(run([msg])["visits"], [])

    def test_r5_picking_up_an_item_is_not_a_visit(self):
        out = run([C("2026-10-14 20:00", "Em ơi mai chị qua lấy khăn chị để quên nha"),
                   S("2026-10-14 20:01", "Dạ vâng chị"),
                   C("2026-10-15 10:00", "Chị tới rồi em, ra lấy khăn giúp chị")])
        self.assertEqual(out["visits"], [])

    def test_r6_thanks_for_visiting_the_page(self):
        out = run([C("2026-10-28 10:00", "Bên em có massage cổ vai gáy không?"),
                   S("2026-10-28 10:01", "Dạ có chị ạ, 199k/30 phút. Cảm ơn chị đã ghé thăm Thơm House ạ")])
        self.assertEqual(out["visits"], [])
        out = run([S("2026-10-28 18:00", "Cảm ơn chị đã ghé thăm tiệm hôm nay ạ")])
        self.assertEqual(vis(out), [("2026-10-28", "medium", ["after_visit"])])

    def test_r7_bill_amount_is_the_total(self):
        base = [C("2026-10-20 09:00", "Mai 3h chị qua gội đầu với massage chân nha"),
                S("2026-10-20 09:01", "Dạ em giữ lịch 3h mai cho chị ạ"), C("2026-10-21 14:58", "Chị tới rồi")]
        for bill, want in (("Dạ em gửi bill hôm nay ạ: gội đầu 199k + massage chân 199k, tổng 398k ạ", 398000),
                           ("Dạ tổng hôm nay: gội đầu 199k + massage chân 199k = 398k ạ", 398000),
                           ("Dạ hóa đơn: gội đầu 199k, massage chân 250k, tổng cộng 449k ạ", 449000),
                           ("da bill hom nay: goi dau 199k, massage chan 199k, tong 398k a", 398000)):
            with self.subTest(bill=bill):
                v = run(base + [S("2026-10-21 17:00", bill)])["visits"][0]
                self.assertEqual((v["confidence"], v["amount_vnd"], v["amount_source"]), ("high", want, "paid"))

    def test_r8_quote_for_another_service(self):
        v = run([C("2026-10-20 09:00", "massage body bn vay e"),
                 S("2026-10-20 09:01", "Dạ massage body 60 phút 429k ạ"),
                 C("2026-10-20 09:03", "thoi mai 3h c goi dau thoi nha"),
                 S("2026-10-20 09:04", "Dạ em giữ lịch 3h chiều mai cho chị ạ"),
                 C("2026-10-21 14:58", "c den r")])["visits"][0]
        self.assertEqual((v["confidence"], v["amount_vnd"]), ("high", None))

    def test_r9_later_message_rule(self):
        out = run([C("2026-09-30 09:00", "thu 7 2h c qua goi dau nha e"),
                   S("2026-09-30 09:01", "Dạ em giữ lịch cho chị ạ"),
                   C("2026-11-10 10:00", "e oi cho c xin dia chi spa voi")])
        self.assertEqual(vis(out)[0][:2], ("2026-10-03", "low"))
        out = run([S("2026-10-19 09:00", "Thứ 7 này bên em còn trống lịch buổi chiều, chị qua thư giãn nha"),
                   C("2026-10-19 12:00", "ok e"), C("2026-11-02 20:00", "goi dau bn vay e")])
        self.assertEqual(out["visits"], [])

    def test_r11_phrase_families(self):
        def with_booking(phrase, h="14:55", plain=True):
            req = "mai 3h c qua goi dau nha e" if plain else "Mai 3h chị qua gội đầu nha em"
            out = run([C("2026-10-20 09:00", req), S("2026-10-20 09:01", "Dạ em giữ lịch 3h chiều mai cho chị ạ"),
                       C(f"2026-10-21 {h}", phrase)])
            return vis(out)[0]
        for phrase in ("c toi r", "c toi roi e", "c toi noi r", "e oi c toi r nha", "c toi spa r", "c toi sanh r",
                       "c dang o sanh", "e mo cua cho c", "c o ngoai cua nha e", "c len r nha", "chị đang dưới sảnh",
                       "chị ở sảnh rồi", "chị đang ở ngoài cửa", "chị lên rồi nha", "chị gửi xe xong rồi",
                       "chị tới chỗ rồi nè"):
            with self.subTest(arrival=phrase):
                self.assertEqual(with_booking(phrase)[1:], ("high", ["booking_request", "booking_confirmed",
                                                                     "arrival"]))
                self.assertEqual(vis(run([C("2026-10-21 14:55", phrase)])), [("2026-10-21", "medium", ["arrival"])])
        for phrase in ("c dang toi", "c toi lien", "c tre 10p nha e", "c sap toi", "c di r nha", "c muon xiu nha",
                       "chị sắp tới", "chị đi rồi nha", "c dang len", "chị đang lên nha em"):
            with self.subTest(en_route=phrase):
                self.assertIn("en_route", with_booking(phrase)[2])
                self.assertEqual(run([C("2026-10-21 14:55", phrase)])["visits"], [])
        for phrase in ("c chuyen r nha e", "c chuyen khoan r nha", "c da ck nha", "c gui tien r nha",
                       "c thanh toan r nha e", "c chuyen 199k nha"):
            with self.subTest(payment=phrase):
                self.assertIn("payment", with_booking(phrase, "16:30")[2])
        for phrase in ("e goi ky ghe", "c ve toi nha r nha e", "massage đã quá em ơi"):
            with self.subTest(thanks=phrase):
                self.assertIn("after_visit", with_booking(phrase, "16:30")[2])

    def test_r15_spa_feedback_question_answered(self):
        out = run([S("2026-10-19 19:00", "Dạ hôm nay chị thấy buổi massage thế nào ạ?"),
                   C("2026-10-19 19:30", "Thích lắm em, nhẹ người hẳn")])
        self.assertEqual(vis(out), [("2026-10-19", "medium", ["past_reference", "after_visit"])])
        out = run([S("2026-10-19 19:00", "Dạ hôm nay chị thấy buổi massage thế nào ạ?"),
                   C("2026-10-19 19:30", "Chị chưa đi em ơi, hôm nay chị bận")])
        self.assertEqual(out["visits"], [])


class RobustnessTest(unittest.TestCase):
    def test_a_message_that_cannot_be_read_is_skipped_not_the_conversation(self):
        # PRIV-10
        out = run([C("2026-11-05 09:00", "Mai 3h chị qua gội đầu nha"), S("2026-11-05 09:05", "Dạ vâng chị"),
                   C("2026-11-06 15:00", "Chị tới rồi"), S("2026-11-06 16:00", "Dạ hôm nay ktv số ² làm cho chị ạ")])
        self.assertEqual(vis(out)[0][1], "high")

    def test_one_very_long_message_is_read_quickly(self):
        # PRIV-11: about 600 000 characters in one message. Measured as complexity, in CPU time of this process
        # (time.process_time: other processes on a loaded machine do not count), not as wall time: the rules read a
        # message up to MAX_TEXT characters, so a message 70 times longer than one just past the cut costs about the
        # same. Without the cut the cost grows at least 70-fold (the rules are linear to quadratic in the length:
        # about 0.03 s at 8 000 characters, 2.6 s at 600 000 on the build Mac), far above the bound below.
        import time  # noqa: PLC0415

        def cpu(text: str) -> float:
            best = float("inf")
            for _ in range(3):
                start = time.process_time()
                run([C("2026-11-05 09:00", text), S("2026-11-05 09:05", "Dạ vâng chị")])
                best = min(best, time.process_time() - start)
            return best
        unit = "chi dat lich goi dau mai 3h nhe, chi toi roi, ck 350k r nha e, ktv Lan lam "
        just_past = cpu(unit * 107)              # 8 000 characters, twice the cut of 4 000
        very_long = cpu(unit * 8000)
        self.assertLess(very_long, 3 * just_past + 0.05, (very_long, just_past))
        self.assertLess(very_long, 5.0)          # CPU seconds; about 0.02 s on the build Mac


class ImportTest(unittest.TestCase):
    def test_importable_in_isolated_mode_and_silent(self):
        # the way scripts/analyze_visits.py imports it: its own folder on sys.path, then a plain import
        code = ("import sys; sys.path.insert(0, %r); import visit_rules as m; "
                "r = m.extract_visits([m.ChatMsg(0, False, 'mai chi qua', 'text')], None, 0); "
                "assert set(r) == {'visits', 'upcoming', 'dropped', 'anchor_ts'}") % str(SCRIPT.parent)
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        # -I ignores PYTHON* variables, so -B keeps the run from writing bytecode
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, env=env,
                              cwd=_TMP.name, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")

    def test_chatmsg_is_frozen(self):
        m = VR.ChatMsg(1, True, "x", "text")
        with self.assertRaises(Exception):
            m.ts = 2  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
