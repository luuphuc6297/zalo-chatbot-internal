"""scripts/contact_facts_rules.py: phone number and benefit (package, voucher) rules on synthetic chats.

Every text, name and number below is invented. Messages are a small stand-in with the attributes the rules read
(ts, from_owner, text, type); the catalog is a small synthetic services.json written to a temporary folder."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "contact_facts_rules.py"
TZ = timezone(timedelta(hours=7))
T0 = int(datetime(2026, 10, 1, 10, 0, tzinfo=TZ).timestamp() * 1000)
MIN = 60_000
H = 60 * MIN
DAY = 24 * H


def load():
    spec = importlib.util.spec_from_file_location("contact_facts_rules", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["contact_facts_rules"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


CF = load()
AC = sys.modules["analyze_contacts"]


@dataclass(frozen=True)
class Msg:
    ts: int
    from_owner: bool
    text: str
    type: str = "text"


def conv(*rows) -> list[Msg]:
    """rows: (minutes after T0, "S" for the spa or "K" for the contact, text[, type])."""
    out = []
    for row in rows:
        minutes, who, text = row[0], row[1], row[2]
        mtype = row[3] if len(row) > 3 else "text"
        out.append(Msg(T0 + minutes * MIN, who == "S", text, mtype))
    return out


def one(who: str, text: str) -> list[Msg]:
    return conv((0, who, text))


CATALOG_JSON = {
    "services": [
        {"id": "goi-dau-thu-gian", "group": "hair", "name_vi": "Gội đầu thư giãn"},
        {"id": "detox-da-dau", "group": "hair", "name_vi": "Detox da đầu"},
        {"id": "massage-chan", "group": "relaxation", "name_vi": "Massage chân"},
        {"id": "goi-mun-chuyen-sau", "group": "skin", "name_vi": "Gói Mụn Chuyên Sâu"},
    ]
}
_TMP = tempfile.TemporaryDirectory()
_CAT_PATH = Path(_TMP.name) / "services.json"
_CAT_PATH.write_text(json.dumps(CATALOG_JSON, ensure_ascii=False), encoding="utf-8")
CAT = AC.load_catalog(_CAT_PATH)

SERVICE_LABELS = {"Gội đầu thư giãn", "Detox da đầu", "Massage chân", "Gói Mụn Chuyên Sâu", "Gội đầu", "Massage",
                  "Chăm sóc da", "Chăm sóc da mụn", "Xóa thâm quầng mắt"}
TITLE_RE = re.compile(r"^(Gói|Voucher)(?: \d{1,3} buổi| \d{1,3}(?:\.\d{3})+đ| giảm \d{1,3}%)?(?: – (?P<svc>.+))?$")
BENEFIT_KEYS = {"kind", "title", "service_id", "total_count", "remaining", "stated_by", "confidence", "at"}


def tearDownModule():
    _TMP.cleanup()


# ---------------------------------------------------------------- phone


class NormalizePhoneTests(unittest.TestCase):
    def test_valid_forms(self):
        for raw in ("0912345678", "0912 345 678", "0912.345.678", "0912-345-678", "+84 912 345 678", "84912345678",
                    "+84912345678", "0084912345678", "(+84) 912 345 678", "+84 0912 345 678"):
            with self.subTest(raw=raw):
                self.assertEqual(CF.normalize_phone(raw), "0912345678")
        self.assertEqual(CF.normalize_phone("0387654321"), "0387654321")
        self.assertEqual(CF.normalize_phone("0567654321"), "0567654321")
        self.assertEqual(CF.normalize_phone("0787654321"), "0787654321")
        self.assertEqual(CF.normalize_phone("0887654321"), "0887654321")

    def test_invalid_forms(self):
        for raw in ("", "abc", "0123456789", "02838123456", "028 3812 3456", "091234567890", "09123456789",
                    "091234567", "840912345678", "1900 1234", "0912345678a", "sdt 0912345678", "0412345678",
                    "0612345678", "+85 912 345 678"):
            with self.subTest(raw=raw):
                self.assertIsNone(CF.normalize_phone(raw))
        self.assertIsNone(CF.normalize_phone(None))  # type: ignore[arg-type]


class ExtractPhoneTests(unittest.TestCase):
    def phone(self, msgs):
        return CF.extract_phone(msgs)

    def assertPhone(self, msgs, value, confidence, at=None):
        got = self.phone(msgs)
        self.assertIsNotNone(got)
        self.assertEqual(set(got), {"value", "confidence", "source", "at"})
        self.assertEqual(got["value"], value)
        self.assertEqual(got["confidence"], confidence)
        self.assertEqual(got["source"], "chat")
        self.assertEqual(got["at"], msgs[-1].ts if at is None else at)

    def test_cue_with_spaces(self):
        self.assertPhone(one("K", "sđt chị 0912 345 678"), "0912345678", "high")

    def test_cue_with_dots(self):
        self.assertPhone(one("K", "số của chị là 0912.345.678"), "0912345678", "high")

    def test_plus84_alone(self):
        self.assertPhone(one("K", "+84 912 345 678"), "0912345678", "high")

    def test_84_prefix_alone(self):
        self.assertPhone(one("K", "84912345678"), "0912345678", "high")

    def test_number_alone(self):
        self.assertPhone(one("K", "0987654321"), "0987654321", "high")
        self.assertPhone(one("K", "0987654321 nha em"), "0987654321", "high")
        self.assertPhone(one("K", "Dạ 0987.654.321 ạ"), "0987654321", "high")

    def test_number_in_sentence_without_cue_is_medium(self):
        self.assertPhone(one("K", "có gì em nhắn chị qua 0912345678 nhé, chiều chị bận"), "0912345678", "medium")
        self.assertPhone(one("K", "co gi e nhan c qua 0912345678 nhe"), "0912345678", "medium")

    def test_other_cues(self):
        self.assertPhone(one("K", "em gọi chị 0912345678 nha"), "0912345678", "high")
        self.assertPhone(one("K", "liên hệ 0912345678"), "0912345678", "high")
        self.assertPhone(one("K", "zalo số 0912345678 em kết bạn nha"), "0912345678", "high")
        self.assertPhone(one("K", "số điện thoại của chị: 0912345678"), "0912345678", "high")
        self.assertPhone(one("K", "goi cho c so 0912345678 nhe"), "0912345678", "high")

    def test_unaccented(self):
        self.assertPhone(one("K", "sdt c la 0912345678"), "0912345678", "high")
        self.assertPhone(one("K", "so cua chi 0912 345 678 nha"), "0912345678", "high")

    def test_cue_glued_to_number(self):
        self.assertPhone(one("K", "sdt0912345678"), "0912345678", "high")

    def test_split_across_separators(self):
        for text in ("sđt chị 0912-345-678", "sđt chị 091 234 5678", "sđt chị 0912 . 345 . 678",
                     "sđt chị 0912  345  678"):
            with self.subTest(text=text):
                self.assertPhone(one("K", text), "0912345678", "high")

    def test_bank_account_is_not_a_phone(self):
        for text in ("stk 0912345678 vcb", "stk 0123456789 vcb", "Vietcombank 0912345678 Nguyen Thi Hoa",
                     "chị chuyển khoản từ số 0912345678 rồi nha", "so tai khoan 0912345678 techcombank",
                     "momo 0912345678"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_amounts_are_not_phones(self):
        for text in ("chị ck 1.500.000đ rồi nha", "chị chuyển 3500000 rồi em", "tổng 12 500 000 đ nha em",
                     "chi chuyen 1 500 000 roi"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_order_codes_are_not_phones(self):
        for text in ("mã đơn 0912345678", "ma don hang 0987654321", "mã giao dịch 0912345678 nha em"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_dates_are_not_phones(self):
        for text in ("chị đặt ngày 15/11/2026 lúc 15:30 nha", "2026-11-15", "15.11.2026 09:30"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_long_digit_runs_are_not_phones(self):
        for text in ("091234567890", "cccd 001234567890", "sđt 0912 345 6789", "sđt 0912345678 9"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_landline_is_not_a_mobile(self):
        self.assertIsNone(self.phone(one("K", "sđt nhà chị 028 3812 3456")))

    def test_number_glued_to_letters_is_not_read(self):
        self.assertIsNone(self.phone(one("K", "0912345678k")))
        self.assertIsNone(self.phone(one("K", "ref0912345678")))

    def test_third_party_number_is_not_the_contact(self):
        self.assertIsNone(self.phone(one("K", "số chồng chị 0912345678")))
        self.assertIsNone(self.phone(one("K", "hotline 0912345678")))

    def test_third_party_number_in_every_spelling(self):
        # PRIV-3 / R10: a relative's or a friend's number, with "sdt" typed without đ, plain spellings, the person
        # named before the number or in the clause before it
        for text in ("sdt mẹ chị 0912000111", "sdt me chi 0912000111", "sdt ban chi 0912000111",
                     "em gọi giúp chị cho mẹ chị số 0912000111 nha", "so ban chi 0912000111 nha e",
                     "sdt cua ban c 0912000111 nhe", "so cua me c 0912000111", "so em gai c 0912000111",
                     "e goi cho ban c nha 0912000111", "lien he ban c 0912000111 nha", "zalo ban c 0912000111",
                     "ban c sdt 0912000111", "dat lich cho ban c, sdt 0912000111",
                     "Em gọi cho bạn chị nha, 0912000111", "Liên hệ bạn chị qua số 0912000111 nha",
                     "Đặt lịch cho bạn chị nha, sđt 0912000111", "Chị đặt cho em gái chị, sđt 0912000111",
                     "sdt nguoi nha c 0912000111", "sđt con gái chị 0912000111"):
            with self.subTest(text=text):
                self.assertIsNone(self.phone(one("K", text)))

    def test_relatives_number_does_not_replace_the_contacts_own(self):
        msgs = conv((0, "K", "sđt chị 0938271645 nha em"), (1, "K", "sdt mẹ chị 0912000111"))
        self.assertPhone(msgs, "0938271645", "high", at=T0)

    def test_own_number_named_next_to_another_person(self):
        # the contact names the number as their own: it counts even with a friend in the message
        self.assertPhone(one("K", "đặt cho chị với bạn chị nha, sđt chị 0938271645"), "0938271645", "high")
        self.assertPhone(one("K", "sdt mẹ chị 0912000111, còn số của chị là 0938271645"), "0938271645", "high")

    def test_number_after_a_message_about_another_person(self):
        # the friend is named in the message just before; a bare number then may be the friend's
        msgs = conv((0, "K", "Em đặt lịch giúp bạn chị nha"), (1, "K", "0912000111"))
        self.assertIsNone(self.phone(msgs))
        msgs = conv((0, "K", "Em đặt lịch giúp bạn chị nha"), (90, "K", "0912000111"))   # 90 minutes later
        self.assertPhone(msgs, "0912000111", "high")

    def test_spa_hotline_is_ignored(self):
        msgs = conv((0, "S", "Dạ hotline bên em 0909 111 222 ạ"),
                    (5, "K", "chị gọi 0909111222 mà không ai nghe máy"))
        self.assertIsNone(self.phone(msgs))

    def test_owner_messages_never_count(self):
        self.assertIsNone(self.phone(one("S", "Dạ sđt của chị là 0912345678 đúng không ạ")))
        self.assertIsNone(self.phone(one("S", "0912345678")))

    def test_contact_number_first_then_owner_echo_still_counts(self):
        msgs = conv((0, "K", "sđt chị 0912345678"), (3, "S", "Dạ em lưu số 0912345678 rồi ạ"))
        self.assertPhone(msgs, "0912345678", "high", at=T0)

    def test_latest_high_wins(self):
        msgs = conv((0, "K", "sđt chị 0912345678"), (2 * 24 * 60, "K", "số mới của chị 0987654321 nha"))
        self.assertPhone(msgs, "0987654321", "high", at=T0 + 2 * DAY)

    def test_high_beats_later_medium(self):
        msgs = conv((0, "K", "sdt chi 0912345678"), (60, "K", "co gi nhan chi qua 0987654321 nhe"))
        self.assertPhone(msgs, "0912345678", "high", at=T0)

    def test_latest_medium_without_high(self):
        msgs = conv((0, "K", "có gì nhắn chị qua 0912345678 nhé"), (60, "K", "có gì nhắn chị qua 0987654321 nhé"))
        self.assertPhone(msgs, "0987654321", "medium", at=T0 + H)

    def test_unsorted_input(self):
        msgs = conv((60, "K", "số mới của chị 0987654321 nha"), (0, "K", "sđt chị 0912345678"))
        self.assertPhone(msgs, "0987654321", "high", at=T0 + H)

    def test_two_numbers_in_one_message_takes_the_first(self):
        self.assertPhone(one("K", "sdt 0912345678 - 0987654321"), "0912345678", "high")

    def test_non_text_messages_and_links_are_ignored(self):
        msgs = conv((0, "K", "https://example.vn/p/0912345678", "link"), (1, "K", "", "photo"),
                    (2, "K", "xem https://example.vn/p/0912345678 nha"), (3, "K", "mail chị là hoa0912345678@example.vn"))
        self.assertIsNone(self.phone(msgs))

    def test_no_messages(self):
        self.assertIsNone(self.phone([]))


# ---------------------------------------------------------------- benefits


class BenefitTests(unittest.TestCase):
    def benefits(self, msgs):
        out = CF.extract_benefits(msgs, CAT)
        for b in out:
            self.assertEqual(set(b), BENEFIT_KEYS)
            m = TITLE_RE.match(b["title"])
            self.assertIsNotNone(m, b["title"])
            if m.group("svc"):
                self.assertIn(m.group("svc"), SERVICE_LABELS)
        return out

    def assertOne(self, msgs, **expected):
        got = self.benefits(msgs)
        self.assertEqual(len(got), 1, got)
        for k, v in expected.items():
            self.assertEqual(got[0][k], v, (k, got[0]))
        return got[0]

    def assertNone(self, msgs):
        self.assertEqual(self.benefits(msgs), [])

    def test_purchase_with_count_by_contact(self):
        b = self.assertOne(one("K", "chị lấy gói 10 buổi gội dưỡng sinh nha"), kind="package", title="Gói 10 buổi",
                           service_id=None, total_count=10, remaining=None, stated_by="contact",
                           confidence="medium")
        self.assertEqual(b["at"], T0)

    def test_purchase_unaccented(self):
        self.assertOne(one("K", "chi lay goi 10 buoi nha e"), title="Gói 10 buổi", total_count=10,
                       remaining=None, confidence="medium")
        self.assertOne(one("K", "c dang ky lieu trinh 5 buoi nhe"), title="Gói 5 buổi", total_count=5)

    def test_remaining_stated_by_spa_is_high(self):
        self.assertOne(one("S", "gói của chị còn 3 buổi ạ"), kind="package", title="Gói", total_count=None,
                       remaining=3, stated_by="owner", confidence="high")

    def test_remaining_stated_by_spa_unaccented(self):
        self.assertOne(one("S", "goi cua chi con 3 buoi a"), remaining=3, stated_by="owner", confidence="high")

    def test_remaining_stated_by_contact_is_medium(self):
        self.assertOne(one("K", "gói của chị còn 3 buổi nha em"), remaining=3, stated_by="contact",
                       confidence="medium")
        self.assertOne(one("K", "chi con 3 buoi nua thoi"), remaining=3, stated_by="contact", confidence="medium")

    def test_ordinal_session(self):
        self.assertOne(one("S", "Hôm nay là buổi thứ 4/10 của chị ạ"), title="Gói 10 buổi", total_count=10,
                       remaining=6, stated_by="owner", confidence="high")
        self.assertOne(one("S", "hom nay la buoi thu 4/10 trong goi cua chi a"), total_count=10, remaining=6)
        self.assertOne(one("K", "hôm nay chị làm buổi thứ 4 trong gói 10 buổi nha"), total_count=10, remaining=6,
                       confidence="medium")

    def test_unaccented_ordinal_without_package_word_may_be_a_date(self):
        self.assertNone(one("S", "hom nay buoi thu 4/10 nha chi"))

    def test_voucher_gift(self):
        self.assertOne(one("S", "em tặng chị voucher 1 buổi nha"), kind="voucher", title="Voucher 1 buổi",
                       total_count=1, remaining=None, stated_by="owner", confidence="high")
        self.assertOne(one("S", "em tang chi voucher 1 buoi nhe"), kind="voucher", title="Voucher 1 buổi")

    def test_voucher_value_and_percent(self):
        self.assertOne(one("S", "em gửi chị voucher 100k cho lần sau nha"), kind="voucher",
                       title="Voucher 100.000đ", total_count=None)
        self.assertOne(one("S", "em tặng chị voucher giảm 20% nha"), kind="voucher", title="Voucher giảm 20%")

    def test_voucher_by_contact_is_medium(self):
        self.assertOne(one("K", "chị được tặng voucher 1 buổi massage chân nè em"), kind="voucher",
                       title="Voucher 1 buổi – Massage chân", service_id="massage-chan", stated_by="contact",
                       confidence="medium")

    def test_gift_sessions_without_the_word_voucher(self):
        self.assertOne(one("S", "dạ lần này em tặng chị 1 buổi massage chân nha"), kind="voucher",
                       title="Voucher 1 buổi – Massage chân", service_id="massage-chan", total_count=1)

    def test_spa_advertising_is_not_a_benefit(self):
        for text in ("Thom House ưu đãi tháng 11: gói 5 buổi gội đầu 900k, gói 10 buổi 1.700.000đ",
                     "Dạ bên em có gói 5 buổi và gói 10 buổi ạ",
                     "Dạ chị lấy gói 10 buổi giá 1.500.000đ nha",
                     "Tặng voucher 100k cho khách hàng đặt lịch trong tháng 11",
                     "Mua gói 10 buổi tặng thêm 1 buổi gội đầu, áp dụng đến hết 30/11",
                     "uu dai thang 11 goi 10 buoi chi con 1tr5"):
            with self.subTest(text=text):
                self.assertNone(one("S", text))

    def test_contact_questions_are_not_benefits(self):
        for text in ("bên em có gói 10 buổi không em?", "gói 10 buổi giá bao nhiêu vậy em",
                     "chị lấy gói 10 buổi được không", "chi con may buoi vay e", "chị còn 3 buổi đúng không em",
                     "voucher 1 buổi dùng được cho massage chân không em"):
            with self.subTest(text=text):
                self.assertNone(one("K", text))

    def test_intent_and_negation_are_not_purchases(self):
        for text in ("chị muốn lấy gói 10 buổi", "chị chưa mua gói đâu em", "chi khong lay goi 10 buoi dau",
                     "nếu chị lấy gói 10 buổi thì sao"):
            with self.subTest(text=text):
                self.assertNone(one("K", text))

    def test_owner_suggestion_is_not_a_purchase(self):
        self.assertNone(one("S", "chị lấy gói 10 buổi nha, tiết kiệm hơn ạ"))

    def test_owner_confirmed_purchase_with_price_counts(self):
        self.assertOne(one("S", "Dạ em xác nhận chị đã mua gói 10 buổi, tổng 1.500.000đ ạ"), total_count=10,
                       stated_by="owner", confidence="high")

    def test_shampoo_and_calls_are_not_packages(self):
        for who, text in (("K", "mai chị qua gội đầu nha"), ("K", "mai chi qua goi dau nha"),
                          ("K", "chị gọi lại sau nha"), ("K", "chi goi lai sau nhe"),
                          ("K", "chị muốn làm gói mụn chuyên sâu"), ("S", "gói đầu tiên của chị nha")):
            with self.subTest(text=text):
                self.assertNone(one(who, text))

    def test_free_slots_are_not_remaining_sessions(self):
        self.assertNone(one("S", "tối nay bên em còn 2 buổi trống ạ"))

    def test_bare_remaining_needs_context(self):
        self.assertNone(one("S", "dạ còn 4 buổi ạ"))
        msgs = conv((0, "K", "chị còn mấy buổi vậy em?"), (5, "S", "dạ còn 4 buổi ạ"))
        b = self.assertOne(msgs, title="Gói", remaining=4, stated_by="owner", confidence="high")
        self.assertEqual(b["at"], T0 + 5 * MIN)

    def test_same_package_latest_statement_wins(self):
        msgs = conv((0, "S", "gói 10 buổi của chị còn 7 buổi ạ"), (7 * 24 * 60, "S", "dạ gói của chị còn 3 buổi ạ"))
        b = self.assertOne(msgs, title="Gói 10 buổi", total_count=10, remaining=3, confidence="high")
        self.assertEqual(b["at"], T0 + 7 * DAY)
        msgs = msgs + conv((8 * 24 * 60, "K", "chị còn 2 buổi nha em"))
        b = self.assertOne(msgs, total_count=10, remaining=2, stated_by="contact", confidence="medium")
        self.assertEqual(b["at"], T0 + 8 * DAY)

    def test_purchase_then_spa_confirms(self):
        msgs = conv((0, "K", "chị lấy gói 10 buổi nha"), (3, "S", "dạ em đã đăng ký gói 10 buổi cho chị rồi ạ"))
        b = self.assertOne(msgs, total_count=10, stated_by="owner", confidence="high")
        self.assertEqual(b["at"], T0 + 3 * MIN)
        self.assertOne(one("S", "dạ bên em đã đăng ký gói 10 buổi cho chị rồi ạ"), total_count=10, confidence="high")

    def test_used_up_then_new_package(self):
        msgs = conv((0, "S", "gói 10 buổi của chị còn 1 buổi ạ"), (60, "S", "dạ gói của chị đã hết rồi ạ"),
                    (120, "K", "chị mua thêm gói 10 buổi nha"))
        got = self.benefits(msgs)
        self.assertEqual(len(got), 2, got)
        self.assertEqual((got[0]["total_count"], got[0]["remaining"], got[0]["at"]), (10, 0, T0 + H))
        self.assertEqual((got[1]["total_count"], got[1]["remaining"], got[1]["at"]), (10, None, T0 + 2 * H))

    def test_at_most_five(self):
        msgs = conv(*[(k * 60, "K", f"chị mua gói {n} buổi nha") for k, n in enumerate(range(3, 9))])
        got = self.benefits(msgs)
        self.assertEqual(len(got), 5)
        self.assertEqual([b["total_count"] for b in got], [4, 5, 6, 7, 8])

    def test_catalog_service_next_to_the_package(self):
        self.assertOne(one("K", "chị mua gói 10 buổi gội đầu thư giãn nha"), service_id="goi-dau-thu-gian",
                       title="Gói 10 buổi – Gội đầu thư giãn", total_count=10)
        self.assertOne(one("K", "chi mua goi 10 buoi goi dau thu gian nha"), service_id="goi-dau-thu-gian",
                       title="Gói 10 buổi – Gội đầu thư giãn")

    def test_catalog_service_whose_name_starts_with_goi(self):
        self.assertOne(one("K", "chị lấy gói mụn chuyên sâu 5 buổi nha"), service_id="goi-mun-chuyen-sau",
                       title="Gói 5 buổi – Gói Mụn Chuyên Sâu", total_count=5)

    def test_catalog_category_gives_a_label_without_id(self):
        self.assertOne(one("K", "chị mua gói 5 buổi massage nha"), service_id=None, title="Gói 5 buổi – Massage")

    def test_service_in_another_clause_is_not_attached(self):
        self.assertOne(one("K", "chị mua gói 10 buổi nha. hôm qua chị gội đầu thư giãn thích lắm"),
                       service_id=None, title="Gói 10 buổi")

    def test_question_in_another_clause_does_not_hide_a_statement(self):
        for text in ("dạ gói của chị còn 3 buổi, chị đặt lịch buổi tiếp theo không ạ",
                     "dạ gói của chị còn 3 buổi, chị đặt lịch buổi tiếp theo không ạ?"):
            with self.subTest(text=text):
                self.assertOne(one("S", text), remaining=3, confidence="high")

    def test_none_left(self):
        self.assertOne(one("S", "gói 10 buổi của chị không còn buổi nào ạ"), total_count=10, remaining=0)
        self.assertNone(one("S", "dạ chị không còn buổi nào ạ"))          # nothing known to update
        self.assertNone(one("K", "chị không còn buổi nào hả em"))         # a question

    def test_expired_or_spent_is_not_read(self):
        for who, text in (("S", "dạ liệu trình 10 buổi của chị đã hết hạn ạ"), ("K", "voucher của chị hết hạn rồi"),
                          ("K", "voucher 1 buổi của chị dùng rồi nha em"),
                          ("S", "goi 10 buoi cua chi het han roi a")):
            with self.subTest(text=text):
                self.assertNone(one(who, text))

    def test_voucher_held(self):
        self.assertOne(one("S", "voucher 1 buổi gội đầu thư giãn của chị nha"), kind="voucher",
                       title="Voucher 1 buổi – Gội đầu thư giãn", service_id="goi-dau-thu-gian")
        self.assertOne(one("K", "voucher của chị còn hạn tới 30/11 nha"), kind="voucher", title="Voucher",
                       confidence="medium")

    def test_contact_repeating_an_offer_is_not_a_benefit(self):
        for text in ("bên em tặng voucher 100k cho khách mới nè", "thấy bên em mua gói 10 buổi tặng 1 buổi"):
            with self.subTest(text=text):
                self.assertNone(one("K", text))

    def test_other_package_words(self):
        self.assertOne(one("K", "the 10 buoi cua chi con 4 buoi a"), total_count=10, remaining=4)
        self.assertOne(one("K", "combo 3 buổi của mình còn 1 buổi nha"), total_count=3, remaining=1)
        self.assertOne(one("S", "dạ em kích hoạt gói 10 buổi cho chị rồi nha"), total_count=10, confidence="high")
        self.assertNone(one("S", "thẻ ngân hàng của chị bị lỗi rồi ạ"))
        self.assertOne(one("S", "Dạ hôm nay là lần thứ 3/5 của chị"), total_count=5, remaining=2)

    def test_ordinal_beyond_the_count_is_not_read(self):
        self.assertNone(one("S", "hôm nay chị làm buổi thứ 11/10 ạ"))

    def test_non_text_messages_are_ignored(self):
        self.assertNone(conv((0, "K", "chị lấy gói 10 buổi nha", "photo"), (1, "K", "", "sticker")))

    def test_empty(self):
        self.assertEqual(CF.extract_benefits([], CAT), [])

    # -- review findings R12, R13, R14, PRIV-10

    def test_package_or_voucher_for_another_person_is_not_the_contacts(self):
        # R12: bought for the mother, a voucher given on to a friend
        self.assertNone(conv((0, "K", "c mua goi 10 buoi goi dau cho me c nha e"),
                             (1, "S", "Dạ em đã đăng ký gói 10 buổi gội đầu cho mẹ chị rồi ạ")))
        self.assertNone(one("S", "Em gửi chị voucher 1 buổi gội đầu để chị tặng bạn nha"))
        self.assertNone(one("K", "c mua 1 voucher 500k tang ban c"))
        self.assertNone(one("K", "gói 10 buổi của mẹ chị còn 3 buổi nha em"))
        # the contact's own package still counts
        self.assertOne(one("S", "Dạ em đã đăng ký gói 10 buổi gội đầu cho chị rồi ạ"), total_count=10)
        self.assertOne(one("S", "em tặng chị voucher 1 buổi nha"), kind="voucher", total_count=1)

    def test_plain_chac_is_an_intent(self):
        # R13: "chắc chị lấy gói 10 buổi quá em" is a thought, not a purchase
        self.assertNone(one("K", "chac c lay goi 10 buoi quá e"))
        self.assertNone(one("K", "chắc chị lấy gói 10 buổi quá em"))
        self.assertOne(one("K", "c lay goi 10 buoi nha e"), total_count=10)

    def test_expiry_after_a_benefit_removes_it(self):
        # R14: the spa says the package has expired: the old remaining count is not an unused benefit any more
        self.assertNone(conv((0, "S", "Dạ gói của chị còn 3 buổi ạ"),
                             (31 * 24 * 60, "S", "Dạ gói của chị hết hạn rồi ạ")))
        self.assertNone(conv((0, "S", "da goi 10 buoi cua chi con 3 buoi a"),
                             (60, "K", "goi cua c het han r ha e"),      # a question: nothing changes yet
                             (120, "S", "da goi cua chi het han roi a")))
        # a voucher expiry does not remove a package
        self.assertOne(conv((0, "S", "Dạ gói 10 buổi của chị còn 3 buổi ạ"),
                            (60, "S", "Dạ voucher của chị hết hạn rồi ạ")), kind="package", remaining=3)
        # a promotion ending is not the contact's package expiring
        self.assertOne(conv((0, "S", "Dạ gói 10 buổi của chị còn 3 buổi ạ"),
                            (60, "S", "Chương trình ưu đãi gói 5 buổi hết hạn ngày 30/11")), remaining=3)

    def test_superscript_digit_does_not_crash(self):
        # PRIV-10: "²" passes str.isdigit() but int() rejects it
        for text in ("buổi thứ 4/² nha", "buoi thu 4 tren ² nha"):
            with self.subTest(text=text):
                self.assertEqual(CF.extract_benefits(one("S", text), CAT), [])
                CF.anchor_timestamps(one("S", text))
        # "²" is not the package size: the size comes from "gói 10 buổi"
        self.assertOne(one("S", "gói 10 buổi, hôm nay buổi thứ 4/² ạ"), total_count=10, remaining=6)

    def test_very_long_message_is_read_quickly(self):
        # PRIV-11: one message of ~200 000 characters is cut before the rules read it. Measured as complexity, in
        # CPU time of this process (time.process_time: other processes on a loaded machine do not count), not as
        # wall time: a message 25 times longer than one just past the cut must cost about the same. Without the cut
        # these rules are quadratic in the length (about 0.06 s at 8 000 characters, 0.66 s at 32 000 on the build
        # Mac), far above the bound below.
        import time  # noqa: PLC0415

        def cpu(text: str) -> float:
            best = float("inf")
            for _ in range(3):
                start = time.process_time()
                CF.extract_benefits(one("K", text), CAT)
                CF.extract_phone(one("K", text + " sđt chị 0912345678"))
                CF.anchor_timestamps(one("K", text))
                best = min(best, time.process_time() - start)
            return best
        unit = "chị lấy gói 10 buổi nha em, còn 3 buổi hết hạn "
        just_past = cpu(unit * 170)              # 8 000 characters, twice the cut of 4 000
        very_long = cpu(unit * 4000)
        self.assertLess(very_long, 3 * just_past + 0.05, (very_long, just_past))
        self.assertLess(very_long, 5.0)          # CPU seconds; about 0.02 s on the build Mac


class AnchorTests(unittest.TestCase):
    def test_anchor_timestamps(self):
        msgs = conv((50, "K", "chị còn 3 buổi nha em"),
                    (0, "K", "bên em có gói 10 buổi không?"),
                    (10, "S", "Thom House ưu đãi gói 5 buổi 900k"),
                    (20, "K", "mai chị qua gội đầu nha"),
                    (30, "S", "em tặng chị voucher 1 buổi nha"),
                    (40, "K", "ok em"),
                    (45, "K", "chị lấy gói 10 buổi nha", "photo"),
                    (55, "S", "tối nay bên em còn 2 buổi trống ạ"))
        self.assertEqual(CF.anchor_timestamps(msgs), [T0, T0 + 10 * MIN, T0 + 30 * MIN, T0 + 50 * MIN])

    def test_anchor_empty(self):
        self.assertEqual(CF.anchor_timestamps([]), [])


# ---------------------------------------------------------------- hygiene


class HygieneTests(unittest.TestCase):
    def test_nothing_printed(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            mod = load()
            mod.extract_phone(one("K", "sđt chị 0912345678"))
            mod.extract_benefits(one("K", "chị lấy gói 10 buổi nha"), CAT)
            mod.anchor_timestamps(one("K", "chị lấy gói 10 buổi nha"))
            mod.normalize_phone("0912345678")
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_importable_in_isolated_mode(self):
        code = ("import importlib.util as u\n"
                f"s = u.spec_from_file_location('cfr', {str(SCRIPT)!r})\n"
                "m = u.module_from_spec(s)\n"
                "s.loader.exec_module(m)\n"
                "print(m.normalize_phone('0912 345 678'))\n")
        with tempfile.TemporaryDirectory() as cwd:
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
            run = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=cwd, env=env, capture_output=True,
                                 text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr[-400:])
        self.assertEqual(run.stdout, "0912345678\n")
        self.assertEqual(run.stderr, "")

    def test_running_the_file_prints_nothing(self):
        with tempfile.TemporaryDirectory() as cwd:
            run = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT)], cwd=cwd, capture_output=True, text=True,
                                 timeout=60)
        self.assertEqual((run.returncode, run.stdout, run.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
