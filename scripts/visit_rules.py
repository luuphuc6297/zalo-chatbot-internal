"""Visit candidates from one 1:1 Zalo chat between the spa ("owner") and a customer. Rules only: no network, no
model, no file writes, nothing printed.

Contract: "Chat-derived customer facts" (draft of docs/contracts.md section 15): 15.4 (candidate shape, signal codes,
confidence, amount sources, services basis), 15.5 (date and time resolution) and 15.75 (this module's API). The
result holds dates, times, catalog ids and names, amounts, a technician's given name or number, signal codes and
message timestamps; never message text.

Text convention (same as scripts/analyze_contacts.py)
  Every phrase in the tables below is matched on the lowercased NFC text. A word matches as written with its
  diacritics, or in its plain spelling only when that word in the message is itself written without diacritics
  (has_marks). A word written "=x" in a table matches only as written, because its plain spelling is another common
  word: "=mốt" (mot is một), "=tới" (toi is tôi), "=bận" (ban is bạn), "=hủy" (huy is the name Huy), "=tối qua" (toi
  qua is "tôi qua", I come over), "=sáng qua" (sang qua, to cross over).

Dates and times (15.5)
  resolve_day(text, ts, past=False) reads the day words of one message relative to the local (UTC+7) date and time
  of that message. past=False is the booking direction (same day, +1, +2, the next weekday, the first explicit date
  on or after the message date); past=True is the past direction (same day, -1, -2, the last weekday before the
  message date, the last explicit date on or before it). A day word in a clause that says the person is busy or
  cannot come ("mai chị bận, mốt chị qua") is skipped while another day word is available. Vague words give no date
  and hide the day word inside them: "mai mốt", "mai sau", "hôm bữa", "lần trước", "tuần trước" (alone), "cuối tuần",
  "hôm khác", "thoải mái" (plain "thoai mai" is not "mai"). "Mai" with a capital M after another word, or followed by
  "ơi", is the given name. "nay", "giờ" (now) and plain "lat" count only at the start of a clause; "giờ" also needs a
  pronoun or a visit verb after it ("giờ chị qua"). "tí/chút/xíu nữa" after thêm/giảm/bớt is "a bit more". A weekday
  after an ordinal word ("buổi thứ 4", "lần thứ 2") or a code word ("mã T7", "size t5") is not a weekday. "X qua"
  (tối/chiều/sáng/trưa/bữa) followed by nha/nhé/đi/được/liền ... is "come over", not yesterday. A number pair "15/11"
  is not a date inside a price, a phone number, an address (số, hẻm, ngõ, ở, tại ...), a fraction (giảm 1/2, 3/10
  buổi), before a unit (người, tiếng, k, % ...) or before "âm lịch". A pair written with "-" or "." ("3-4", "8.12")
  is a date only with a year, after "ngày", or when the first number is above the second ("15-11", "20.11"), and
  never after tầm/khoảng/từ/chắc/cỡ or before a day part or a time unit ("tầm 3-4 chiều", "2-3 hôm nữa"): such a pair
  is a range or a clock time as often as a date (15.5 lists "15-11" and "15.11"; the narrower reading is a choice).
  resolve_time(text) reads "15h", "15h30", "15:30", "15g", "3 giờ", "3 giờ rưỡi", "3h kém 15", "3 rưỡi" (only within
  two words of a day word, a visit verb, "lúc" or "tầm"), a range "3-4h" as its first hour, maps the hour with the
  day part in the same clause ("đêm" beyond 15.5: 6-11 are 18-23, 12 is 00:00, 1-5 stay), and skips a duration: a
  number of hours right after trong/mất/gói/liệu trình/massage/body/mặt/chân/vai/gáy/combo/suất, unless a day part
  follows it ("massage body 1h" is a duration, "1h chiều" a time).

Signals (15.4), by who writes
  contact: booking_request (booking words such as "đặt lịch", "còn chỗ", "book", or a visit verb qua/ghé/đến/tới, or
    a reply to the spa's booking question, and a day that resolves in the booking direction; not a trip to pick
    something up: "qua lấy khăn", "để quên"); booking_confirmed when accepting ("ok em", "dạ được") a slot the spa
    proposed within 12 hours; en_route ("đang qua", "kẹt xe", "trễ", "5 phút nữa", "giờ chị qua", "chị sắp tới",
    "c dang toi", "c di r", plain "tre 10p" / "muon xiu"); arrival ("tới rồi", "đến nơi", "ở dưới", "ở sảnh", "lên
    rồi", "gửi xe xong", plain "c toi r"), only with the contact as the subject (nothing, lead words or the contact's
    pronoun before it: not "hàng đến rồi", "mùa mưa tới rồi") and, for "ở dưới / ở trước / ở cửa / ngoài cửa", no
    other place after it ("ở cửa hàng", "ở dưới quê"); after_visit (feedback words such as "dễ chịu", "thích lắm",
    "ngủ ngon" on the visit day or the next); payment; past_reference; cancelled; rescheduled; no_show ("quên mất",
    "quên lịch", "lỡ hẹn" after the slot).
  spa: booking_confirmed (confirm words such as "giữ lịch", "giữ chỗ", "đã đặt lịch cho", "xác nhận", or a short "dạ
    vâng / ok chị / dạ được" reply within 12 hours of the contact's request); a slot proposal ("mai 3h còn trống chị
    nha", "4h được không ạ") that the contact may accept, only after the contact asked in the last 12 hours or as a
    question naming a time ("mai bên em còn trống 3h, chị qua không ạ?"); reminder ("nhắc lịch", "chị có lịch",
    "đừng quên lịch"); arrival ("em ra mở cửa"; not "mời chị vào nhóm Zalo / link"); after_visit ("cảm ơn chị đã
    ghé/đến/sử dụng/trải nghiệm", not "đã ghé thăm" without a day word; a feedback request such as "chị thấy thế
    nào" only joins an existing visit, or, naming a day and a session, is completed by the contact's feedback words
    within 12 hours into a past_reference); payment (a total "tổng ... 350k", a bill, a transfer received);
    cancelled; rescheduled; no_show ("em đợi chị mà không thấy chị qua" after the slot). A spa message sent to many
    customers (trong thời gian qua, tri ân, chương trình, nhân dịp, ưu đãi ...) is never a thanks, a reminder or a
    slot proposal.
  Someone else's visit gives no signal: a relative or a friend named with a pronoun ("mẹ chị", "bạn c", "ck chị") in
  the clause that books, arrives, pays or cancels, from either side, unless the contact comes too ("chị với bạn
  chị"); the spa's answer within 12 hours to such a booking is not the contact's booking either.
  Not a payment for a session: a deposit (cọc, plain "coc" next to ck/rồi), a refund ("hoàn tiền"; the spa's "em
  chuyển rồi"), a package, voucher or product (gói, voucher, chai, hộp, mua ...), "ck" followed by other words than
  "rồi" ("ck chị về rồi": the husband). A spa total alone ("Dạ tổng 349k ạ") is a payment only after the session
  (an arrival, a thanks, the slot passed) or with a receipt word; within 3 hours after the contact's price question
  it is a quote.
  A past_reference names the spa: a catalog service, a service verb (gội, massage, xông ...), the spa as a place
  (tiệm, bên em, chỗ em), "qua làm", or the contact's feedback words; and none of: work (đi làm, nghỉ làm), another
  place (qua nhà, công ty, bệnh viện, chỗ khác, tiệm khác, gần nhà), an intent (định qua), a failed trip (đóng cửa,
  không có ai, mà kẹt). From the spa only as a feedback request or naming a service, never with "em" as the subject.
  A spa message about another customer (analyze_contacts.KHACH_RE: "có khách", "khách đặt", "lịch của khách"; or
  "khách khác", "người ta", "chị ấy") gives no signal. A message naming only a service the studio does not offer
  ("làm nail") gives no signal. A spa message with two or more different amounts and no total word, or with
  price-list words (bảng giá, menu, khuyến mãi, combo ...) and an amount, is a price list: no signal, service or
  amount comes from it. Health vocabulary does not stop anything here (no text is stored).

How a signal finds its date (one candidate per local date)
  A booking message uses its own day. A confirmation or acceptance without a day goes to the pending request or
  proposal (12 hours). A cancellation uses a day named in its own clause ("hủy lịch nha, mai chị bận": "mai" is the
  reason), else, or when that day has no booking, the nearest open booking on or after the message date; "hủy lịch
  thứ 7" sent on that Saturday before the slot is today's. "để lần sau / để hôm khác" cancels only when the message
  names no service and asks no price. A reminder without a day goes to the nearest open booking. en_route joins a
  booking on the message date and never makes a candidate alone (it has no confidence rule in 15.4). arrival joins
  or makes the candidate of the message date. after_visit and payment without a day of their own join the booking
  on the message date when its slot is not more than one hour ahead, else the candidate of the day before. Unlike
  the 15.4 text, a payment never makes a candidate on its own date, and a spa thanks does so only when it names the
  session (a service, a day word, "đã ghé làm"): a payment alone was mostly a package, a product, a debt or a
  deposit, and "cảm ơn chị đã ghé" also closes a price answer. A payment that finds no candidate waits instead of
  being lost: an arrival, a thanks, a feedback or a past reference written later on the payment's day or the next,
  for the payment's date or the day before (the D+1 rule of 15.4), takes it (a payment naming a past day only that
  day, a spa total with a receipt word only its own date), so a walk-in who pays before the thanks keeps the payment
  and its amount. A spa thanks that follows such a waiting payment of the same day, or carries a transfer itself,
  makes the candidate of its date. A feedback request or the contact's feedback words only join. A cancellation
  after the slot is a no_show. Only the contact's own signals, an arrival or a payment
  reopen a cancelled slot (not a spa reminder or confirmation). A reschedule cancels the old date (the date before
  "sang/qua", else the nearest open booking) and books the new date (the day after the phrase; a time alone moves
  the slot on the same date); "đổi/dời/chuyển sang" counts only with a day or a time after it and no catalog service
  ("đổi sang massage body" changes the service, "chuyển sang khu khác" the address).

Confidence, services, amount, technician
  high, medium, low and the drops follow 15.4. Choices beyond its text: a spa reminder counts as a confirmed
  booking; two or more of arrival / after_visit / payment without a booking count as medium ("at least one"); the
  "later message" of the medium rule is a message from the contact within 72 hours after the slot that is not an
  address, opening-hours or price question (a booking followed by months of silence and "cho chị xin địa chỉ" is a
  visit that did not happen).
  Services: booking (named in the booking exchange: from 6 hours before the first booking message to the last one),
  visit_day (named on the visit date or in a message that gave this candidate a signal), window (named within 72
  hours before the visit); at most 3, most certain first. When the booking messages (or the contact's request the
  spa confirmed) name a service, a service of another kind named in the exchange or the window ("massage body bao
  nhiêu?") is not this visit's. Amount: paid (latest total statement, else latest payment amount, on the visit date
  or the day after; a deposit "cọc" is never the amount; a bill that lists items is read at its last total word
  "tổng / tổng cộng / thành tiền / =", else the amount that is the sum of the others), quoted (the latest spa
  message with exactly one amount within the booking exchange, up to one hour after it, before the visit date ends,
  whose service, or the service of the contact's message it answers, is the booked one; with no service named, only
  when the exchange names one kind of service; never an answer to "... để lần sau"), list_price (exactly one catalog
  service named, every category named belongs to its group, and the catalog variants left after the named duration
  and the slot's time window have one price). Technician: a given name from analyze_contacts.GIVEN_NAMES or "số N"
  (N of 1-3 ASCII digits) after kỹ thuật viên / ktv / nhân viên, or after bạn / bé / em when the clause also says who
  performs the service (làm, massage, gội, xếp, chọn, cho chị ...) and the name is not a vocative ("Em Hoa ơi");
  never a bare name, never from a request for the next visit ("lần sau cho chị bạn Hoa làm").

Robustness
  A message is read up to MAX_TEXT characters (the rules slow down with the square of a message's length). A message
  the rules cannot read is skipped; the rest of the conversation is still read.
"""

from __future__ import annotations

import bisect
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import analyze_contacts as ac  # noqa: E402  (sibling module; python3 -I does not put this folder on sys.path)

nfc_lower = ac.nfc_lower
fold = ac.fold
has_marks = ac.has_marks
TOKEN_RE = ac.TOKEN_RE
TZ_VN = ac.TZ_VN

# ---------------------------------------------------------------- limits

HOUR_MS = 3_600_000
DAY_MS = ac.DAY_MS
PENDING_MS = 12 * HOUR_MS          # a reply confirms a request or accepts a proposal within 12 hours
EXCHANGE_LEAD_MS = 6 * HOUR_MS     # the booking exchange starts up to 6 hours before its first booking message
QUOTE_TAIL_MS = HOUR_MS            # a quote may follow the last booking message by up to one hour
WINDOW_MS = 72 * HOUR_MS           # services named within 72 hours before the visit
AHEAD_SLACK_MS = HOUR_MS           # a same-day slot up to one hour ahead still takes a payment / thanks
NO_SHOW_DAYS = 3
MAX_AHEAD_DAYS = 180               # a booking further ahead than this is not read as one
MAX_SERVICES = 3
MAX_EVIDENCE = 5
AMOUNT_MIN, AMOUNT_MAX = 10_000, 50_000_000
TECH_MAX = 60
SHORT_REPLY_TOKENS = 10
MAX_TEXT = 4_000                   # a message is read up to this length (rules time grows with the length)
LATER_MSG_MS = 72 * HOUR_MS        # medium for a confirmed booking: a contact message within 72 hours after the slot
QUOTE_INQUIRY_MS = 3 * HOUR_MS     # a spa total within 3 hours after the contact's price question is a quote

# ---------------------------------------------------------------- phrase tables (15.5 day and time words)

SAME_DAY_WORDS = ("hôm nay", "bữa nay", "sáng nay", "trưa nay", "chiều nay", "tối nay", "lát nữa", "=lát", "tí nữa",
                  "chút nữa", "xíu nữa", "bây giờ")
NEXT_DAY_WORDS = ("ngày mai", "sáng mai", "trưa mai", "chiều mai", "tối mai", "mai")
DAY_AFTER_NEXT_WORDS = ("ngày =mốt", "=mốt", "ngày kia")
YESTERDAY_WORDS = ("hôm qua", "=tối qua", "chiều qua", "=sáng qua", "trưa qua", "bữa qua")
TWO_DAYS_AGO_WORDS = ("hôm kia",)
# Phrases that hide the day word inside them and give no date.
VAGUE_DAY_WORDS = ("mai mốt", "mai sau", "mai kia", "hôm bữa", "bữa trước", "hôm trước", "lần trước", "tuần trước",
                   "hôm khác", "bữa khác", "dịp khác", "ngày khác", "hôm nào", "bữa nào", "ngày nào", "khi nào",
                   "lúc nào", "cuối tuần", "đầu tuần", "giữa tuần", "thoải mái", "mãi mãi", "mái tóc", "hoa mai",
                   "tuần =tới nữa")
NEXT_WEEK_WORDS = ("tuần sau", "tuần tới")
PREV_WEEK_WORDS = ("tuần trước",)
THIS_WEEK_WORDS = ("tuần này",)
WEEKDAY_WORDS = {
    0: ("thứ 2", "thứ hai", "t2"),
    1: ("thứ 3", "thứ ba", "t3"),
    2: ("thứ 4", "thứ =tư", "t4"),           # plain "thu tu" is also "thứ tự" (order)
    3: ("thứ 5", "thứ năm", "t5"),
    4: ("thứ 6", "thứ =sáu", "t6"),          # plain "thu sau" is also "thử sau" (try later)
    5: ("thứ 7", "thứ bảy", "thứ bẩy", "t7"),
    6: ("chủ nhật", "cn"),
}
# Token rules: single words, same convention as the phrases (as written, or the plain spelling of an unmarked token;
# "=x" only as written). Checked with _tok_is().
CLAUSE_LEAD = ("dạ", "vâng", "ok", "oke", "okie", "okay", "uh", "ừm", "ừ", "vậy", "thế", "thì", "mà", "thôi", "nhưng",
               "còn", "rồi", "ơi", "=à", "=ạ", "hi", "hello", "alo", "nếu", "khi")
NOW_NEXT = ("chị", "em", "anh", "mình", "c", "e", "a", "tôi", "tui", "qua", "ghé", "đến", "đi", "=sang", "có", "làm",
            "book", "đặt")
SOON_NOT_AFTER = ("thêm", "giảm", "bớt", "nhiều", "ít")         # "thêm chút nữa": a bit more, not "later today"
QUA_NOT_YESTERDAY_NEXT = ("nha", "nhé", "nhe", "nhen", "nghen", "đi", "được", "dc", "đc", "liền", "luôn", "ngay",
                          "không", "ko", "hông", "nhá", "với", "lấy", "chơi", "thăm", "bên", "spa", "tiệm")
ORDINAL_PREV = ("lần", "buổi", "người", "đứa", "cái", "tuần", "tháng", "hạng", "số", "con", "bé", "đợt", "lượt",
                "chương", "bài", "phần", "lớp", "năm", "gói", "bản", "mã", "code", "size", "sz", "loại", "mẫu", "màu",
                "dòng", "model")                 # "mã T7", "size t5": a code, not a weekday
DATE_UNIT_NEXT = ("người", "tiếng", "giờ", "h", "phút", "p", "buổi", "lần", "k", "tr", "triệu", "nghìn", "ngàn", "đ",
                  "d", "vnd", "đồng", "cái", "chai", "hộp", "lọ", "gói", "suất", "vé", "ly", "kg", "g", "cm", "m",
                  "km", "tuổi", "giá", "sp", "sản", "điểm", "sao", "liệu")
DATE_ADDRESS_PREV = ("số", "hẻm", "ngõ", "ngách", "kiệt", "lô", "phòng", "lầu", "tầng", "căn", "block", "đường",
                     "giảm", "thứ", "buổi", "còn", "sđt", "stk", "tk", "ở", "tại")
# A number pair written with "-" or "." ("3-4", "8.12") is a range or a clock time as often as a date: it is a date
# only with a year, after "ngày", or when the first number is above the second ("15-11", "20.11"), and never after a
# range word or before a day part or a time unit ("tầm 3-4 chiều", "2-3 hôm nữa", "1-2 tuần").
RANGE_PREV = ("tầm", "khoảng", "từ", "chắc", "cỡ", "độ", "trong", "mất")
RANGE_NEXT = ("=sáng", "trưa", "chiều", "=tối", "=đêm", "hôm", "ngày", "bữa", "tuần", "tháng", "=nữa", "năm", "lát")
DATE_LEAD_PREV = ("ngày", "hôm", "bữa", "mùng", "mồng")
LUNAR_NEXT = ("=âm", "âm lịch", "al")            # "15/11 âm lịch": a lunar date, not this calendar's 15/11
DAY_PART_WORDS = ("=sáng", "trưa", "chiều", "=tối", "=đêm")
DAY_PART_OF = {"sang": "morning", "trua": "noon", "chieu": "afternoon", "toi": "evening", "dem": "night"}
# Plain "sang" / "toi" are also "sang" (to move over: "dời sang 5h") and "tôi" / "tới". Like the analyzer's ambiguous
# plain spellings they count only in a message without any diacritics, and only right next to the time or before
# nay / mai ("9h sang", "toi nay 7h"), never after a move verb ("doi sang 5h").
PLAIN_DAY_PART_RE = re.compile(r"(?<![^\W_])(sang|toi)(?![^\W_])")
MOVE_VERBS = ("dời", "đổi", "chuyển", "lùi", "để", "qua", "đi")
DURATION_PREV = ("trong", "mất", "kéo", "dài", "gói", "combo", "suất", "liệu", "trình", "massage", "masage", "body",
                 "mặt", "chân", "vai", "gáy", "tổng")
HALF_HOUR_NEAR = ("mai", "nay", "=sáng", "trưa", "chiều", "=tối", "qua", "ghé", "đến", "đặt", "book", "=hẹn", "lúc",
                  "tầm", "khoảng", "vào", "kia", "=mốt")

# ---------------------------------------------------------------- phrase tables (15.4 signals)

# The contact asks for a slot (with a day that resolves).
BOOKING_ASK_WORDS = ("đặt lịch", "lịch hẹn", "hẹn lịch", "đặt hẹn", "đặt chỗ", "giữ chỗ", "giữ lịch", "còn lịch",
                     "còn chỗ", "còn slot", "còn =trống", "=trống lịch", "khung giờ", "book", "booking", "book lịch",
                     "đặt slot", "hẹn giờ", "qua làm", "ghé làm", "đến làm", "=tới làm", "lấy lịch", "xếp lịch",
                     "đặt trước", "=hẹn", "=đặt")
# "qua" after these is a preposition ("chuyển qua", "gửi qua"), "đến" after these is "about" ("liên quan đến").
QUA_PREP_PREV = ("chuyển", "đổi", "dời", "gửi", "nhắn", "ck", "đi", "lướt", "xem", "coi", "gọi", "đưa", "giới",
                 "lùi", "vượt", "bỏ", "để", "sống")
DEN_PREP_PREV = ("quan", "nghĩ", "nói", "nhắc", "tính", "nhìn", "chú", "=tới", "từ")
# The spa confirms a slot.
CONFIRM_WORDS = ("giữ lịch", "giữ chỗ", "giữ slot", "đặt lịch cho", "đã đặt lịch", "em đặt lịch", "lên lịch",
                 "xếp lịch", "ghi lịch", "note lịch", "chốt lịch", "nhận lịch", "book cho", "em book", "đã book",
                 "xác nhận", "=hẹn chị", "=hẹn anh", "=hẹn gặp", "=đợi chị", "=đợi anh", "=chờ chị", "=chờ anh",
                 "em =đợi", "em =chờ", "lịch của chị", "lịch của anh", "ghi nhận", "em note")
# The spa offers a slot; the contact's acceptance makes it booking_confirmed.
AVAILABILITY_WORDS = ("còn =trống", "còn chỗ", "còn slot", "còn lịch", "=trống lịch", "có slot", "có chỗ", "=trống",
                      "được không", "đc không", "dc không", "được ko", "đc ko", "dc ko", "được hông", "được k",
                      "đc k", "qua lúc", "ghé lúc", "=tới lúc", "đến lúc")
# A short reply that accepts ("ok em", "dạ được", "dạ vâng chị") and has none of the blocking words.
ACCEPT_TOKENS = ("dạ", "vâng", "ok", "oke", "okie", "okay", "okela", "oki", "uki", "ừ", "ừm", "được", "đc", "dc",
                 "chốt", "yes")
ACCEPT_BLOCK = ("không", "ko", "k", "hông", "chưa", "hết", "kín", "full", "tiếc", "thôi", "xem", "coi", "tính", "nghĩ",
                "sắp", "xếp", "hỏi", "hủy", "huỷ", "sao", "gì", "j", "nào", "mấy", "bao", "đổi", "dời", "ck", "cọc",
                "quên", "lỗi", "chào", "hello", "hi", "alo", "=bận", "=kẹt")
REMINDER_WORDS = ("nhắc lịch", "nhắc chị", "nhắc anh", "nhắc hẹn", "có lịch hẹn", "chị có lịch", "anh có lịch",
                  "lịch hẹn của chị", "lịch hẹn của anh", "nhớ lịch", "đừng quên lịch", "đừng quên hẹn")
# A message the spa sends to many customers: thanks "in the past time", a promotion, an anniversary. It is never a
# thanks for one visit or a reminder of one appointment.
BROADCAST_WORDS = ("trong thời gian qua", "thời gian qua", "tri ân", "chương trình", "nhân dịp", "ủng hộ",
                   "đồng hành", "quan tâm", "tin tưởng", "quý khách", "khách hàng", "khuyến mãi", "ưu đãi",
                   "luôn ủng hộ", "thân thiết", "chúc mừng")
_NEG = ("không", "ko", "k", "hông", "hổng", "=chưa")
_COME = ("qua", "đi", "=tới", "đến", "ghé")
_ABLE = ("được", "đc", "dc", "kịp")
CANCEL_WORDS = tuple(f"{n} {v} {a}" for n in _NEG for v in _COME for a in _ABLE) + (
    "hủy lịch", "huỷ lịch", "hủy hẹn", "huỷ hẹn", "=hủy", "=huỷ", "hủy giúp", "huỷ giúp", "hủy giùm", "hủy dùm",
    "hủy nha", "huỷ nha", "hủy nhé", "huỷ nhé", "hủy đi", "hủy rồi", "huỷ rồi", "cancel", "bận đột xuất",
    "thôi không qua", "không qua nữa", "ko qua nữa", "không đi nữa", "không kịp", "ko kịp", "thôi để lần sau",
    "thôi hẹn lần sau")
# "để hôm khác", "để lần sau": a cancellation, unless the message is about another service or a price ("Mà massage
# body bao nhiêu em, để lần sau chị làm").
CANCEL_WEAK_WORDS = ("để hôm khác", "để bữa khác", "hẹn hôm khác", "hẹn bữa khác", "hẹn dịp khác", "hẹn lại sau",
                     "thôi để sau", "để lần sau", "hẹn lần sau")
# A reschedule that names the moving itself ("dời lịch", "đổi giờ"), and one that is only a verb plus "sang/qua"
# ("đổi sang", "dời qua"), which also changes a service ("đổi sang massage body") or a place ("chuyển sang khu
# khác"): the second kind counts only when a day or a time follows it and no catalog service does.
RESCHEDULE_WORDS = ("dời lịch", "đổi lịch", "lùi lịch", "dời hẹn", "đổi hẹn", "chuyển lịch", "=hoãn", "hoãn lịch",
                    "đổi ngày", "dời ngày", "đổi giờ", "dời giờ", "lùi giờ", "chuyển ngày", "chuyển giờ")
RESCHEDULE_WEAK_WORDS = ("dời sang", "đổi sang", "chuyển sang", "lùi sang", "để sang", "dời qua", "đổi qua",
                         "chuyển qua", "lùi qua", "=dời", "=đổi", "=lùi")
NO_SHOW_CONTACT_WORDS = ("quên lịch", "quên mất", "quên hẹn", "quên béng", "lỡ hẹn", "ngủ quên")
NO_SHOW_OWNER_WORDS = ("không thấy chị", "không thấy anh", "ko thấy chị", "ko thấy anh", "k thấy chị",
                       "chị không qua", "anh không qua", "chị ko qua", "chị không đến", "chị không =tới",
                       "em =đợi chị mà", "em =chờ chị mà", "=đợi chị mãi", "=chờ chị mãi", "=bùng", "chị quên lịch")
EN_ROUTE_WORDS = ("đang qua", "đang =tới", "đang đến", "đang chạy qua", "đang chạy =tới", "đang trên đường qua",
                  "đang trên đường =tới", "đang trên đường đến", "sắp =tới nơi", "sắp đến nơi", "gần =tới",
                  "gần đến", "qua liền", "=tới liền", "đến liền", "qua ngay", "=tới ngay", "đến ngay", "đi liền",
                  "kẹt xe", "=trễ", "trễ chút", "trễ xíu", "trễ tí", "=muộn", "xuất phát", "ra khỏi nhà", "đi đây",
                  "đang lên", "đang =tới nơi", "sắp đến")
EN_ROUTE_MIN_RE = re.compile(r"(?<![\w.,/:])\d{1,2}\s?(?:phút|phut|ph|p|')\s*(?:nữa|nua)(?![^\W_])")
# plain "tre" (trễ / trẻ) and "muon" (muộn / muốn) only before a number of minutes or "xíu / tí / chút"
EN_ROUTE_PLAIN_RE = re.compile(
    r"(?<![^\W_])(?:tre|muon)\s+(?:\d{1,2}\s?(?:p|ph|phut)|1?\s?(?:xiu|ti|chut))(?![^\W_])")
ARRIVAL_WORDS = ("=tới rồi", "đến rồi", "=tới nơi", "đến nơi", "ở dưới", "ở trước", "ở cửa", "đứng dưới",
                 "đứng trước", "đang ở dưới", "=tới cửa", "đến cửa", "mở cửa cho chị", "mở cửa cho anh",
                 "mở cửa cho em", "mở cửa giúp", "mở cửa cho c", "mở cửa cho a", "=tới r", "đến r", "=tới spa",
                 "đến spa", "=tới tiệm", "đến tiệm", "ở sảnh", "dưới sảnh", "=tới sảnh", "đến sảnh", "ngoài cửa",
                 "lên rồi", "lên =r", "=tới chỗ rồi", "đến chỗ rồi", "gửi xe xong", "gửi xe rồi", "gửi xe =r")
# "ở dưới", "ở trước", "ở cửa", "ngoài cửa", "đứng ...": a place right after them must be the spa's ("ở dưới nhà
# em", "ở cửa rồi"), not another place ("ở cửa hàng", "ở dưới quê", "ở trước cổng trường").
ARRIVAL_PLACE_WORDS = ("ở dưới", "ở trước", "ở cửa", "đứng dưới", "đứng trước", "đang ở dưới", "ngoài cửa")
ARRIVAL_PLACE_NEXT = ("rồi", "=r", "nè", "nha", "nhé", "nhe", "em", "e", "tiệm", "spa", "cửa", "sảnh", "nhà", "này",
                      "đây", "đó", "=ạ", "=á", "chờ", "=đợi", "mở", "luôn", "thôi", "nek", "ròi", "ơi", "chị", "c",
                      "anh", "a", "rùi", "ah", "tòa", "toà", "building", "chung", "lầu", "tầng")
ARRIVAL_NOT_AFTER = ("sắp", "gần", "chưa", "chắc", "tuần", "tháng", "năm", "lần")
# Before an arrival phrase only the contact (a pronoun, nothing, or lead words) may stand: "hàng đến rồi", "mùa mưa
# tới rồi", "giá lên rồi" have another subject.
ADVERB_TOKENS = ("đã", "mới", "vừa", "cũng", "đang", "thì", "là", "ở", "đứng", "ngồi", "chờ", "=đợi", "=sắp")
CONTACT_PRONOUNS = ("chị", "c", "anh", "a", "em", "e", "mình", "tôi", "tui", "tớ", "mk", "cj", "chj", "minh", "chi")
OWNER_ARRIVAL_WORDS = ("em ra mở cửa", "em xuống mở cửa", "em ra đón", "em xuống đón", "em thấy chị rồi",
                       "em thấy anh rồi", "mời chị vào", "mời anh vào", "mời chị lên", "mời anh lên", "chị vào luôn",
                       "anh vào luôn", "chị lên luôn", "anh lên luôn")
# "mời chị vào nhóm Zalo", "chị vào luôn link này": an invitation to a page, not an arrival.
NOT_ARRIVAL_OBJECT_WORDS = ("nhóm", "group", "link", "zalo", "page", "fanpage", "trang", "web", "website", "app",
                            "xem", "đọc", "coi", "bảng", "form", "khảo", "đăng ký", "theo dõi", "kênh")
# A trip to the spa that is not a session: picking up or bringing back something.
PICKUP_WORDS = ("qua lấy", "ghé lấy", "đến lấy", "=tới lấy", "ra lấy", "lấy đồ", "lấy khăn", "lấy áo", "lấy túi",
                "lấy lại", "qua gửi", "ghé gửi", "qua trả", "ghé trả", "để quên", "bỏ quên", "quên đồ", "quên khăn",
                "quên áo", "quên túi", "quên ví", "quên điện thoại", "quên dù", "quên ô", "quên kính")
# The spa thanking for a visit ("cảm ơn chị đã ghé"); not "đã ghé thăm page" or "đã tin tưởng" (also after inquiries).
THANKS_VISIT_RE = re.compile(
    r"(?<![^\W_])(?:cảm|cám|cam)\s+(?:ơn|on)(?![^\W_]).{0,40}?(?<![^\W_])(?:đã|da)\s+"
    r"(?:ghé|ghe|đến|den|qua|sử\s+dụng|su\s+dung|trải\s+nghiệm|trai\s+nghiem|tới|làm)(?![^\W_])", re.S)
NOT_VISIT_WORDS = ("ghé thăm page", "ghé thăm fanpage", "ghé thăm trang", "ghé thăm zalo", "ghé thăm kênh",
                   "ghé thăm shop", "ghé thăm website", "ghé page", "ghé fanpage", "ghé trang")
# "ghé thăm" is a visit of the page unless the thanks names a day ("cảm ơn chị đã ghé thăm tiệm hôm nay").
GHE_THAM_WORDS = ("ghé thăm",)
OWNER_FEEDBACK_WORDS = ("về =tới nhà chưa", "về đến nhà chưa", "về nhà chưa", "thấy dịch vụ", "thấy buổi",
                        "thấy thế nào", "thấy sao", "thấy ổn không", "thấy có ổn", "đánh giá", "feedback", "review",
                        "có hài lòng", "góp ý", "cảm nhận")
CONTACT_FEEDBACK_WORDS = ("dễ chịu", "thoải mái", "nhẹ người", "nhẹ nhõm", "đỡ mỏi", "đỡ đau", "ngủ ngon",
                          "thích lắm", "thích quá", "ưng lắm", "ưng quá", "hài lòng", "tay nghề", "làm kỹ", "làm kĩ",
                          "có tâm", "=sướng", "=phê", "thơm lắm", "mượt lắm", "da mịn", "tóc thơm", "làm xong",
                          "vừa làm", "mới làm", "vừa về", "mới về", "về tới nhà", "về đến nhà", "khen", "kỹ ghê",
                          "kĩ ghê", "=đã quá", "=đã lắm", "=đã ghê", "thích ghê", "êm lắm", "êm ghê")
PAST_DONE_WORDS = ("rồi", "=r", "xong", "=đã", "vừa", "=mới", "lúc =nãy", "hồi =nãy", "khi =nãy", "ban =nãy",
                   "=hồi sáng", "=hồi chiều")
PAST_VISIT_WORDS = ("=làm", "=gội", "massage", "mát xa", "qua", "ghé", "đến", "=tới", "trải nghiệm", "=dùng",
                    "sử dụng", "xông", "nặn", "spa", "đi spa")
# A past visit names the spa: a service verb, the spa as a place, or a session ("qua làm", "ghé làm"). The motion
# verbs alone (qua, ghé, đến, tới, đi) and "làm" alone also describe going elsewhere or going to work.
SPA_EVIDENCE_WORDS = ("=gội", "massage", "mát xa", "xông", "nặn", "spa", "tiệm", "bên em", "chỗ em", "bên mình",
                      "thơm house", "thom house", "qua làm", "ghé làm", "đến làm", "=tới làm", "làm mặt", "làm da",
                      "chăm sóc da")
# Not a visit to the spa: work, another place, another spa, an intent, a failed trip.
NOT_PAST_VISIT_WORDS = ("đi làm", "nghỉ làm", "làm việc", "đi học", "đi chơi", "qua nhà", "về quê", "đến nhà",
                        "=tới nhà", "ghé nhà", "đến công ty", "=tới công ty", "qua công ty", "bệnh viện", "đám cưới",
                        "đám giỗ", "chỗ khác", "tiệm khác", "spa khác", "nơi khác", "bên khác", "gần nhà",
                        "qua ngang", "đi ngang", "chạy ngang", "định qua", "định ghé", "định đến", "định =tới",
                        "định đi", "định làm", "tính qua", "tính ghé", "muốn qua", "muốn ghé", "đóng cửa",
                        "không có ai", "ko có ai", "mà =kẹt", "nhưng =kẹt", "=kẹt việc", "nên về", "thấy đông",
                        "hết chỗ", "chưa qua", "chưa ghé", "không qua", "ko qua")
PAY_WORDS = ("chuyển khoản", "đã chuyển", "chuyển rồi", "chuyển =r", "chuyển xong", "chuyển tiền", "thanh toán",
             "trả tiền", "gửi tiền", "nhận được tiền", "nhận được ck", "nhận được chuyển khoản", "nhận ck",
             "nhận tiền", "bill", "hóa đơn", "hoá đơn", "tính tiền")
# Money paid back ("hoàn tiền"; from the spa "em chuyển rồi ạ"): not a payment for a session.
REFUND_WORDS = ("hoàn tiền", "hoàn lại", "trả lại tiền", "hoàn cọc", "trả cọc", "trả lại cọc")
OWNER_REFUND_WORDS = ("em chuyển", "em ck", "em gửi lại", "em chuyển lại", "em hoàn", "em đã chuyển", "em trả")
# A payment for a package, a voucher or a product is not a payment for a session.
PRODUCT_WORDS = ("=gói", "liệu trình", "voucher", "=chai", "=hũ", "=hộp", "=lọ", "tuýp", "sản phẩm", "=sp", "mua",
                 "dầu gội", "dầu xả", "mỹ phẩm", "serum", "đơn hàng")
# A spa total is a payment (not a quote) with a receipt word, or when the session took place.
RECEIPT_WORDS = ("nhận", "đã chuyển", "chuyển rồi", "bill", "hóa đơn", "hoá đơn", "tính tiền", "thanh toán",
                 "hôm nay", "buổi này", "lần này")
# The total of a bill: the amount after the last of these is the total.
TOTAL_LAST_WORDS = ("tổng", "tổng cộng", "tổng bill", "tất cả là", "tất cả hết", "thành tiền", "tổng là")
PAY_TOTAL_WORDS = ("tổng", "tổng cộng", "tổng bill", "tất cả là", "tất cả hết", "=hết", "tính tiền", "bill",
                   "hóa đơn", "hoá đơn", "thành tiền")
STK_WORDS = ("stk", "số tài khoản", "số tk")
DEPOSIT_WORDS = ("=cọc", "đặt cọc", "cọc trước", "tiền cọc", "ck cọc", "chuyển cọc", "cọc rồi", "cọc =r",
                 "cọc giữ", "cọc nha", "cọc nhé")
# "ck" is chuyển khoản next to an amount, or done ("ck rồi", "đã ck", "nhận được ck"); otherwise it may be the
# husband ("ck chị") or a promise ("ck nha"), and a payment without an amount needs a done word.
CK_DONE_NEXT = {"rồi", "roi", "r", "xong"}
CK_DONE_PREV = {"đã", "da", "vừa", "vua", "mới", "nhận", "nhan", "được", "duoc", "dc", "đc"}
# words that may sit between "ck" and "rồi" in a payment ("ck cho em rồi"); any other word ("ck chị về rồi": the
# husband came home) ends the search
CK_FILLER = {"cho", "em", "e", "shop", "spa", "bên", "ben", "luôn", "luon", "tiền", "tien", "ạ", "a", "nha", "nhe",
             "nhé", "trước", "truoc", "đủ", "du"}
# Payment words that only come up at the session itself, so they count without an amount or a done word.
PAY_AT_SESSION_WORDS = ("tính tiền", "bill", "hóa đơn", "hoá đơn")
PRICE_INQUIRY_WORDS = ("bao nhiêu", "bn tiền", "bnhieu", "nhiêu tiền", "=giá", "báo giá", "bảng giá", "menu",
                       "giá bn", "bao tiền", "giá sao", "giá thế nào", "bn vậy", "bn vay", "bn ạ", "=bn")
# A message after a confirmed slot that shows the contact never came: an address, opening hours, a price.
FIRST_CONTACT_WORDS = ("địa chỉ", "ở đâu", "chỉ đường", "đường nào", "mấy giờ mở", "giờ mở cửa", "mở cửa mấy giờ",
                       "mở cửa tới mấy", "mở cửa đến mấy", "bao nhiêu", "bn tiền", "=giá", "bảng giá", "menu")
# A request for the next visit ("lần sau cho chị bạn Hoa làm").
NEXT_TIME_WORDS = ("lần sau", "hôm sau", "bữa sau", "lần =tới", "buổi sau", "lần sau nữa")
PRICE_LIST_WORDS = ("bảng giá", "menu", "giá dịch vụ", "khuyến mãi", "ưu đãi", "combo", "chương trình", "giảm giá",
                    "sale", "voucher", "giá lẻ", "giá gói", "liệu trình", "=gói")
# The spa talking about someone else's appointment (with analyze_contacts.KHACH_RE).
OWNER_THIRD_WORDS = ("khách khác", "người khác", "chị ấy", "anh ấy", "bạn ấy", "người ta", "khách hàng khác",
                     "bạn kia", "chị kia", "anh kia", "khách hàng", "khách bên em", "khách của em")
# The contact talking about a relative's or a friend's visit ("bạn chị", "mẹ em").
THIRD_SUBJECT_RE = re.compile(
    r"(?<![^\W_])(?:bạn|ban|mẹ|me|má|bố|chồng|chong|ck|vợ|vk|con|cô|dì|bà|ông|em gái|em gai|em trai|chị gái|chi gai|"
    r"anh trai|nhỏ bạn|đứa bạn|dua ban|bạn thân|ban than|người nhà|nguoi nha)\s+(?:của\s+|cua\s+)?"
    r"(?:chị|chi|em|anh|mình|minh|tôi|toi|tui|tớ|c|e|mk)(?![^\W_])")
# ... unless the contact comes too ("chị với bạn chị", "cả hai", "2 người").
SELF_TOO_WORDS = ("chị với", "chị và", "chị cùng", "chị dẫn", "chị đưa", "chị rủ", "c với", "c và", "em với", "em và",
                  "anh với", "anh và", "mình với", "mình và", "cả hai", "cả 2", "2 người", "hai người", "2 chị em",
                  "hai chị em", "cả nhà", "chị =dắt", "c =dắt")
NEGATIVE_WORDS = ("=bận", "=kẹt", "không được", "ko được", "k được", "không đc", "ko đc", "k đc", "không dc", "ko dc",
                  "k dc", "không rảnh", "ko rảnh", "k rảnh", "hết chỗ", "hết slot", "hết lịch", "kín lịch", "=kín",
                  "full", "không còn", "ko còn", "k còn", "không qua", "ko qua", "k qua", "không đi", "ko đi",
                  "không =tới", "ko =tới", "không đến", "ko đến", "=hủy", "=huỷ", "hủy lịch", "huỷ lịch",
                  "không kịp", "ko kịp", "kín rồi")
# Technician cues
TECH_STRONG_WORDS = ("kỹ thuật viên", "kĩ thuật viên", "ktv", "nhân viên", "nv")
# bạn / bé before a capitalized given name: the plain "ban" / "be" are accepted there, the name is the evidence.
TECH_WEAK_TOKENS = ("bạn", "bé", "em", "e")
PERFORMER_WORDS = ("làm", "massage", "gội", "phục", "xếp", "chọn", "book", "đặt", "cho", "nghề", "mát", "nặn", "chăm")

SIGNAL_PRIORITY = ("payment", "arrival", "after_visit", "en_route", "booking_confirmed", "booking_request", "reminder",
                   "past_reference", "rescheduled", "cancelled", "no_show")
BOOKING_CODES = {"booking_request", "booking_confirmed", "reminder"}
POSITIVE_CODES = BOOKING_CODES | {"en_route", "arrival", "after_visit", "payment", "past_reference"}
VISIT_EVIDENCE_CODES = {"arrival", "after_visit", "past_reference"}   # a payment waiting for its visit joins these
BASIS = ("booking", "visit_day", "window")

# ---------------------------------------------------------------- regex building


def _word_src(word: str) -> str:
    exact = word.startswith("=")
    w = nfc_lower(word[1:] if exact else word)
    plain = fold(w)
    if exact or plain == w:
        return re.escape(w)
    return "(?:" + re.escape(w) + "|" + re.escape(plain) + ")"


def _phrase_src(phrase: str) -> str:
    words = phrase.split()
    src = _word_src(words[0])
    for w in words[1:]:
        src += (r"\s*" if w.isdigit() else r"\s+") + _word_src(w)
    return src


@dataclass(frozen=True)
class TokenSet:
    """Single words: as written, or (unless marked "=") the plain spelling of a token written without marks."""
    orig: frozenset
    plain: frozenset


def tset(words: Iterable[str]) -> TokenSet:
    orig, plain = set(), set()
    for word in words:
        exact = word.startswith("=")
        w = nfc_lower(word[1:] if exact else word)
        orig.add(w)
        if not exact:
            plain.add(fold(w))
    return TokenSet(frozenset(orig), frozenset(plain))


def _word_is(w: str, ts: TokenSet) -> bool:
    return w in ts.orig or (not has_marks(w) and w in ts.plain)


def _tok_is(toks: list[re.Match], k: int, ts: TokenSet) -> bool:
    return 0 <= k < len(toks) and _word_is(toks[k].group(0), ts)


def vre(phrases: Iterable[str]) -> re.Pattern:
    """One regex for a phrase table (whole words, longest phrase first), matched on nfc_lower(text). A word matches
    as written, or in its plain spelling when the message writes that word without diacritics; "=word" only as
    written."""
    alts = sorted({p.strip() for p in phrases if p and p.strip()}, key=lambda p: (-len(p.replace("=", "")), p))
    return re.compile(r"(?<![^\W_])(?:" + "|".join(_phrase_src(p) for p in alts) + r")(?![^\W_])")


SAME_DAY_RE = vre(SAME_DAY_WORDS)
NEXT_DAY_RE = vre(NEXT_DAY_WORDS)
DAY_AFTER_NEXT_RE = vre(DAY_AFTER_NEXT_WORDS)
YESTERDAY_RE = vre(YESTERDAY_WORDS)
TWO_DAYS_AGO_RE = vre(TWO_DAYS_AGO_WORDS)
VAGUE_DAY_RE = vre(VAGUE_DAY_WORDS)
NEXT_WEEK_RE = vre(NEXT_WEEK_WORDS)
PREV_WEEK_RE = vre(PREV_WEEK_WORDS)
THIS_WEEK_RE = vre(THIS_WEEK_WORDS)
WEEKDAY_RES = [(wd, vre(words)) for wd, words in WEEKDAY_WORDS.items()]
DAY_PART_RE = vre(DAY_PART_WORDS)
BOOKING_ASK_RE = vre(BOOKING_ASK_WORDS)
CONFIRM_RE = vre(CONFIRM_WORDS)
AVAILABILITY_RE = vre(AVAILABILITY_WORDS)
REMINDER_RE = vre(REMINDER_WORDS)
CANCEL_RE = vre(CANCEL_WORDS)
CANCEL_WEAK_RE = vre(CANCEL_WEAK_WORDS)
RESCHEDULE_RE = vre(RESCHEDULE_WORDS)
RESCHEDULE_WEAK_RE = vre(RESCHEDULE_WEAK_WORDS)
RESCHEDULE_ANY_RE = vre(RESCHEDULE_WORDS + RESCHEDULE_WEAK_WORDS)
BROADCAST_RE = vre(BROADCAST_WORDS)
GHE_THAM_RE = vre(GHE_THAM_WORDS)
ARRIVAL_PLACE_RE = vre(ARRIVAL_PLACE_WORDS)
NOT_ARRIVAL_OBJECT_RE = vre(NOT_ARRIVAL_OBJECT_WORDS)
PICKUP_RE = vre(PICKUP_WORDS)
SPA_EVIDENCE_RE = vre(SPA_EVIDENCE_WORDS)
NOT_PAST_VISIT_RE = vre(NOT_PAST_VISIT_WORDS)
REFUND_RE = vre(REFUND_WORDS)
OWNER_REFUND_RE = vre(OWNER_REFUND_WORDS)
PRODUCT_RE = vre(PRODUCT_WORDS)
RECEIPT_RE = vre(RECEIPT_WORDS)
TOTAL_LAST_RE = vre(TOTAL_LAST_WORDS)
FIRST_CONTACT_RE = vre(FIRST_CONTACT_WORDS)
NEXT_TIME_RE = vre(NEXT_TIME_WORDS)
SELF_TOO_RE = vre(SELF_TOO_WORDS)
LUNAR_NEXT_RE = vre(LUNAR_NEXT)
NO_SHOW_CONTACT_RE = vre(NO_SHOW_CONTACT_WORDS)
NO_SHOW_OWNER_RE = vre(NO_SHOW_OWNER_WORDS)
EN_ROUTE_RE = vre(EN_ROUTE_WORDS)
ARRIVAL_RE = vre(ARRIVAL_WORDS)
OWNER_ARRIVAL_RE = vre(OWNER_ARRIVAL_WORDS)
NOT_VISIT_RE = vre(NOT_VISIT_WORDS)
OWNER_FEEDBACK_RE = vre(OWNER_FEEDBACK_WORDS)
CONTACT_FEEDBACK_RE = vre(CONTACT_FEEDBACK_WORDS)
PAST_DONE_RE = vre(PAST_DONE_WORDS)
PAST_VISIT_RE = vre(PAST_VISIT_WORDS)
PAY_RE = vre(PAY_WORDS)
PAY_TOTAL_RE = vre(PAY_TOTAL_WORDS)
STK_RE = vre(STK_WORDS)
PAY_AT_SESSION_RE = vre(PAY_AT_SESSION_WORDS)
DEPOSIT_RE = vre(DEPOSIT_WORDS)
PRICE_INQUIRY_RE = vre(PRICE_INQUIRY_WORDS)
PRICE_LIST_RE = vre(PRICE_LIST_WORDS)
OWNER_THIRD_RE = vre(OWNER_THIRD_WORDS)
NEGATIVE_RE = vre(NEGATIVE_WORDS)
TECH_STRONG_RE = vre(TECH_STRONG_WORDS)
LEAD_T = tset(CLAUSE_LEAD)
NOW_NEXT_T = tset(NOW_NEXT)
SOON_NOT_AFTER_T = tset(SOON_NOT_AFTER)
QUA_NOT_YESTERDAY_NEXT_T = tset(QUA_NOT_YESTERDAY_NEXT)
ORDINAL_PREV_T = tset(ORDINAL_PREV)
DATE_UNIT_NEXT_T = tset(DATE_UNIT_NEXT)
DATE_ADDRESS_PREV_T = tset(DATE_ADDRESS_PREV)
MOVE_VERBS_T = tset(MOVE_VERBS)
DURATION_PREV_T = tset(DURATION_PREV)
HALF_HOUR_NEAR_T = tset(HALF_HOUR_NEAR)
QUA_PREP_PREV_T = tset(QUA_PREP_PREV)
DEN_PREP_PREV_T = tset(DEN_PREP_PREV)
ACCEPT_T = tset(ACCEPT_TOKENS)
ACCEPT_BLOCK_T = tset(ACCEPT_BLOCK)
ARRIVAL_NOT_AFTER_T = tset(ARRIVAL_NOT_AFTER)
TECH_WEAK_T = tset(TECH_WEAK_TOKENS)
PERFORMER_T = tset(PERFORMER_WORDS)
VOCATIVE_T = tset(("ơi",))
RANGE_PREV_T = tset(RANGE_PREV)
RANGE_NEXT_T = tset(RANGE_NEXT)
DATE_LEAD_PREV_T = tset(DATE_LEAD_PREV)
ARRIVAL_PLACE_NEXT_T = tset(ARRIVAL_PLACE_NEXT)
ADVERB_T = tset(ADVERB_TOKENS)
CONTACT_PRONOUN_T = tset(CONTACT_PRONOUNS)

# Numbers. A number glued to a letter, a dot, a comma or a slash is part of something else (a code, a price, a date).
_NUM_LB = r"(?<![\w.,/:])"
TIME_H_RE = re.compile(
    _NUM_LB + r"(\d{1,2})\s?(?:giờ|gio|h|g)"
    r"(?:(\d{1,2})(?!\d)|\s(\d{2})(?!\d))?\s?(?:phút|phut|ph|p|')?"
    r"(?:\s?(?:kém|kem)\s?(\d{1,2})(?!\d)\s?(?:phút|phut|ph|p|')?)?"
    r"(\s?(?:rưỡi|ruoi))?"
    r"(?![^\W\d_])")
TIME_COLON_RE = re.compile(_NUM_LB + r"(\d{1,2}):(\d{2})(?!\d)")
# "3-4h", "9 - 10 giờ": a range of hours starts at the first one
TIME_RANGE_RE = re.compile(_NUM_LB + r"(\d{1,2})\s?[-–~]\s?\d{1,2}\s?(?:giờ|gio|h|g)(?![^\W\d_])")
TIME_HALF_RE = re.compile(_NUM_LB + r"(\d{1,2})\s+(?:rưỡi|ruoi)(?![^\W_])")
DATE_DM_RE = re.compile(r"(?<![\w.,/:-])(\d{1,2})([/.-])(\d{1,2})(?:\2(\d{4}|\d{2}))?(?![\w]|[.,/:-]\d)")
DATE_NGAY_RE = re.compile(
    r"(?<![^\W_])(?:ngày|ngay)\s+(\d{1,2})(?![\w]|[/.-]\d)"
    r"(?:\s+(?:tháng|thang)\s+(\d{1,2})(?![\w])(?:\s+(?:năm|nam)\s+(\d{4})(?![\w]))?)?")
DATE_TAY_RE = re.compile(r"(?<![\w.,/:-])(\d{1,2})\s+(?:tây|tay)(?![^\W_])")
PHONE_RUN_RE = re.compile(r"\+?\d[\d .\-/]{5,}\d")
AMT_SEP_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+)(?:\s?(?:đồng|dong|vnđ|vnd|đ|d))?(?![\w])")
AMT_MIL_RE = re.compile(
    r"(?<![\w.,])(\d{1,3})(?:[.,](\d{1,2}))?\s?(?:triệu|trieu|tr)"
    r"(?:\s?(\d{1,3})(?!\d)(?:\s?(nghìn|ngàn|nghin|ngan|k|trăm|tram))?|\s?(rưỡi|ruoi))?(?![^\W\d_])")
AMT_K_RE = re.compile(r"(?<![\w.,])(\d{1,4})\s?(?:k|nghìn|ngàn|nghin|ngan|ngìn)(?![^\W_])")
AMT_RAW_RE = re.compile(r"(?<![\w.,])(\d{5,8})\s?(?:đồng|dong|vnđ|vnd|đ)(?![\w])")
DUR_MIN_RE = re.compile(_NUM_LB + r"(\d{2,3})\s?(?:phút|phut|ph|p|')(?![^\W_])")
DUR_HOUR_RE = re.compile(_NUM_LB + r"(\d)\s?(?:tiếng|tieng)(\s+(?:rưỡi|ruoi))?(?![^\W_])")
CLAUSE_CUT = set(",;!?\n\r…")

# ---------------------------------------------------------------- public: message type and prices


@dataclass(frozen=True)
class ChatMsg:
    ts: int          # epoch milliseconds
    from_owner: bool  # True: the spa's account wrote it. False: the contact wrote it.
    text: str        # "" for a non-text message
    type: str        # "text", "photo", "sticker", ...


def load_prices(path: Path) -> dict[str, list[dict]]:
    """service_id -> [{"duration_min": int|None, "price_vnd": int, "time_window": str|None}] from data/services.json.
    A missing or unreadable file gives {}."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        services = doc.get("services") or []
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
    out: dict[str, list[dict]] = {}
    for s in services if isinstance(services, list) else []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or s.get("service_id") or "")
        if not sid:
            continue
        rows = []
        for v in s.get("variants") or []:
            if not isinstance(v, dict):
                continue
            price = v.get("price_vnd")
            if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
                continue
            dur = v.get("duration_min")
            dur = dur if isinstance(dur, int) and not isinstance(dur, bool) and dur > 0 else None
            tw = v.get("time_window")
            tw = tw if isinstance(tw, str) and tw else None
            rows.append({"duration_min": dur, "price_vnd": price, "time_window": tw})
        if rows:
            out[sid] = rows
    return out


# ---------------------------------------------------------------- text helpers


def _norm(text: str) -> tuple[str, str]:
    """(cased NFC, lowercased NFC), aligned character by character."""
    cased = unicodedata.normalize("NFC", text or "")
    return cased, nfc_lower(cased)


def _local(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, TZ_VN)


def _local_ms(d: date, minutes: int) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=TZ_VN) + timedelta(minutes=minutes)
    return int(dt.timestamp() * 1000)


def _clauses(low: str) -> list[int]:
    """Start offsets of the clauses of a message: cut at , ; ! ? newline … and at . or : not between two digits."""
    starts = [0]
    n = len(low)
    for i, ch in enumerate(low):
        if ch in CLAUSE_CUT or (ch in ".:" and not (0 < i < n - 1 and low[i - 1].isdigit() and low[i + 1].isdigit())):
            starts.append(i + 1)
    return starts


def _clause_of(starts: list[int], pos: int) -> int:
    return bisect.bisect_right(starts, pos) - 1


def _neg_clauses(low: str, starts: list[int]) -> set[int]:
    return {_clause_of(starts, m.start()) for m in NEGATIVE_RE.finditer(low)}


class _Toks(list):
    """The word tokens of a text (re.Match objects) with their start offsets, for a binary search."""

    def __init__(self, matches: Iterable[re.Match]):
        super().__init__(matches)
        self.starts = [t.start() for t in self]


def _toks(low: str) -> _Toks:
    return _Toks(TOKEN_RE.finditer(low))


def _tok_index(toks: list[re.Match], pos: int) -> int:
    """Index of the token that starts at or after pos."""
    starts = getattr(toks, "starts", None)
    if starts is None:
        starts = [t.start() for t in toks]
    return bisect.bisect_left(starts, pos)


def _folded(toks: list[re.Match], k: int) -> str:
    return fold(toks[k].group(0)) if 0 <= k < len(toks) else ""


def _starts_clause(toks: list[re.Match], k: int, starts: list[int]) -> bool:
    """True when every token before toks[k] in its clause is a lead particle or a vocative ("em ơi", "dạ", "ok")."""
    ci = _clause_of(starts, toks[k].start())
    j = k - 1
    while j >= 0 and _clause_of(starts, toks[j].start()) == ci:
        if _tok_is(toks, j, LEAD_T) or _tok_is(toks, j + 1, VOCATIVE_T):
            j -= 1
            continue
        return False
    return True


def _mk_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


# ---------------------------------------------------------------- 15.5 times


def _map_hour(h: int, part: str | None) -> int:
    def default(x: int) -> int:
        return x + 12 if 1 <= x <= 8 else x       # 9-11 stay, 12 is noon, 1-8 are 13-20 (the spa opens 09:00)
    if h >= 13 or h == 0:
        return h
    if part == "morning":
        return h
    if part == "noon":
        return h + 12 if 1 <= h <= 2 else h if h in (11, 12) else default(h)
    if part == "afternoon":
        return h + 12 if 1 <= h <= 6 else default(h)
    if part == "evening":
        return h + 12 if 5 <= h <= 11 else default(h)
    if part == "night":                            # "11h đêm" 23:00, "12h đêm" 00:00, "1h đêm" 01:00
        return h + 12 if 6 <= h <= 11 else 0 if h == 12 else h
    return default(h)


def _day_parts(low: str, toks: list[re.Match]) -> list[tuple[int, int, str, bool]]:
    """(start, end, part, adjacent_only) of sáng / trưa / chiều / tối. Plain "sang"/"toi" only in a message without
    diacritics and not after a move verb; before nay/mai they count anywhere in the clause, else only next to the
    time (adjacent_only=True)."""
    out = [(m.start(), m.end(), DAY_PART_OF[fold(m.group(0))], False) for m in DAY_PART_RE.finditer(low)]
    if has_marks(low):
        return out
    for m in PLAIN_DAY_PART_RE.finditer(low):
        k = _tok_index(toks, m.start())
        if _tok_is(toks, k - 1, MOVE_VERBS_T):
            continue                                    # "doi sang 5h": move to 5h
        before_day = _folded(toks, k + 1) in ("nay", "mai")
        out.append((m.start(), m.end(), DAY_PART_OF[m.group(1)], not before_day))
    return out


def _time_hits(low: str) -> list[tuple[int, int, int, bool]]:
    """(start, end, minutes of the day, in_negative_clause) for every time expression, in text order."""
    toks = _toks(low)
    starts = _clauses(low)
    neg = _neg_clauses(low, starts)
    parts = _day_parts(low, toks)
    raw: list[tuple[int, int, int, int, int]] = []          # start, end, hour, minute, minus
    for m in TIME_H_RE.finditer(low):
        h = int(m.group(1))
        minute = int(m.group(2) or m.group(3) or 0)
        minus = int(m.group(4)) if m.group(4) else 0
        if m.group(5) and minute == 0:
            minute = 30
        raw.append((m.start(), m.end(), h, minute, minus))
    for m in TIME_COLON_RE.finditer(low):
        raw.append((m.start(), m.end(), int(m.group(1)), int(m.group(2)), 0))
    for m in TIME_RANGE_RE.finditer(low):
        raw.append((m.start(), m.end(), int(m.group(1)), 0, 0))
    for m in TIME_HALF_RE.finditer(low):
        k0 = _tok_index(toks, m.start())
        k1 = _tok_index(toks, m.end())
        if any(_tok_is(toks, j, HALF_HOUR_NEAR_T) for j in (k0 - 2, k0 - 1, k1, k1 + 1)):
            raw.append((m.start(), m.end(), int(m.group(1)), 30, 0))
    raw.sort()
    out: list[tuple[int, int, int, bool]] = []
    last_end = -1
    for s, e, h, minute, minus in raw:
        if s < last_end:
            continue
        if h > 23 or minute > 59 or minus > 59:
            continue
        ci = _clause_of(starts, s)
        # the day part nearest to the time in the same clause; a plain sang/toi only right next to it
        best, best_gap = None, None
        for ps, pe, part, plain in parts:
            if _clause_of(starts, ps) != ci:
                continue
            gap_text = low[e:ps] if ps >= e else low[pe:s]
            if plain and gap_text.strip():
                continue
            gap = len(gap_text)
            if best_gap is None or gap < best_gap:
                best, best_gap = part, gap
        adjacent_part = best is not None and best_gap is not None and best_gap <= 1
        k = _tok_index(toks, s)
        k_next = _tok_index(toks, e)
        if not adjacent_part and (_tok_is(toks, k - 1, DURATION_PREV_T) or
                                  (_folded(toks, k_next) == "dong" and _folded(toks, k_next + 1) == "ho")):
            continue                                    # "massage body 1h", "2 giờ đồng hồ": a duration
        hh = _map_hour(h, best)
        total = (hh * 60 + minute - minus) % (24 * 60)
        out.append((s, e, total, ci in neg))
        last_end = e
    return out


def _first_time(hits: list[tuple[int, int, int, bool]]) -> int | None:
    for _s, _e, t, neg in hits:
        if not neg:
            return t
    return hits[0][2] if hits else None


def resolve_time(text: str) -> str | None:
    """'HH:MM' of the first time expression of the text (one in a busy clause only when there is no other), or None.
    15.5: day parts decide the half of the day; without one 9-11 stay, 12 is noon and 1-8 mean 13-20."""
    _cased, low = _norm(text)
    t = _first_time(_time_hits(low))
    return None if t is None else f"{t // 60:02d}:{t % 60:02d}"


# ---------------------------------------------------------------- 15.5 days


@dataclass
class _Hit:
    start: int
    end: int
    kind: str          # same | next | past | weekday | explicit
    arg: Any           # day offset, weekday (Mon=0), or (day, month|None, year|None)
    now: bool = False  # "giờ" / "bây giờ": now


@dataclass
class _Row:
    hit: _Hit
    fdate: date | None   # booking direction
    pdate: date | None   # past direction
    neg: bool            # in a busy / cannot-come clause
    clause: int = 0


def _day_hits(low: str, cased: str) -> list[_Hit]:
    toks = _toks(low)
    starts = _clauses(low)
    hits: list[_Hit] = []
    for rx, kind, off in ((SAME_DAY_RE, "same", 0), (NEXT_DAY_RE, "next", 1), (DAY_AFTER_NEXT_RE, "next", 2),
                          (YESTERDAY_RE, "past", 1), (TWO_DAYS_AGO_RE, "past", 2)):
        for m in rx.finditer(low):
            k = _tok_index(toks, m.start())
            f = fold(m.group(0))
            words = f.split()
            if kind == "next" and f == "mai":
                if cased[m.start():m.end()] == "Mai" and not _starts_clause(toks, k, starts):
                    continue                            # "chị Mai", "gặp Mai": the given name
                if _tok_is(toks, k + 1, VOCATIVE_T):
                    continue                            # "Mai ơi"
            if f in ("lat", "ti nua", "chut nua", "xiu nua") and _tok_is(toks, k - 1, SOON_NOT_AFTER_T):
                continue
            if kind == "past" and words[0] in ("toi", "chieu", "sang", "trua") and \
                    _tok_is(toks, k + len(words), QUA_NOT_YESTERDAY_NEXT_T):
                continue                                # "chiều qua nha": come over this afternoon
            hits.append(_Hit(m.start(), m.end(), kind, off if kind != "same" else 0,
                             now=(f == "bay gio")))
    # standalone "nay" (today), plain "lat" (later today), "giờ" (now) at the start of a clause
    for k, t in enumerate(toks):
        w = t.group(0)
        if w not in ("nay", "lat", "giờ", "gio") or not _starts_clause(toks, k, starts):
            continue
        if w in ("giờ", "gio"):
            if not _tok_is(toks, k + 1, NOW_NEXT_T):
                continue
            hits.append(_Hit(t.start(), t.end(), "same", 0, now=True))
        else:
            hits.append(_Hit(t.start(), t.end(), "same", 0))
    # weekdays
    for wd, rx in WEEKDAY_RES:
        for m in rx.finditer(low):
            k = _tok_index(toks, m.start())
            if _tok_is(toks, k - 1, ORDINAL_PREV_T):
                prev_cased = cased[toks[k - 1].start():toks[k - 1].end()]
                name_like = k - 1 > 0 and prev_cased[:1].isupper() and not has_marks(prev_cased)
                if not name_like:
                    continue                            # "buổi thứ 4", "lần thứ 2" (not "bạn Lan thứ 7 qua")
            if re.match(r"[/.]\d", low[m.end():m.end() + 2]):
                continue                                # "thứ 4/10"
            hits.append(_Hit(m.start(), m.end(), "weekday", wd))
    # explicit dates
    phone_runs = [(m.start(), m.end()) for m in PHONE_RUN_RE.finditer(low)
                  if sum(ch.isdigit() for ch in m.group(0)) >= 9]
    for m in DATE_DM_RE.finditer(low):
        if any(s <= m.start() and m.end() <= e and (e - s) > (m.end() - m.start()) for s, e in phone_runs):
            continue
        k0 = _tok_index(toks, m.start())
        k1 = _tok_index(toks, m.end())
        if _tok_is(toks, k0 - 1, DATE_ADDRESS_PREV_T) or _tok_is(toks, k1, DATE_UNIT_NEXT_T):
            continue
        rest = low[m.end():].lstrip()
        if rest.startswith("%") or LUNAR_NEXT_RE.match(low, len(low) - len(rest)):
            continue                                    # "15/11 âm lịch": a lunar date
        d_, mo_ = int(m.group(1)), int(m.group(3))
        y = int(m.group(4)) if m.group(4) else None
        if m.group(2) in "-." and y is None and not _tok_is(toks, k0 - 1, DATE_LEAD_PREV_T):
            if d_ <= mo_ or _tok_is(toks, k0 - 1, RANGE_PREV_T) or _tok_is(toks, k1, RANGE_NEXT_T):
                continue                                # "3-4 chiều", "2-3 hôm nữa", "8.12" (a clock time)
        hits.append(_Hit(m.start(), m.end(), "explicit", (d_, mo_, y)))
    for m in DATE_NGAY_RE.finditer(low):
        k1 = _tok_index(toks, m.end())
        if _tok_is(toks, k1, DATE_UNIT_NEXT_T):
            continue                                    # "ngay 15 phut nua": in 15 minutes
        mo = int(m.group(2)) if m.group(2) else None
        y = int(m.group(3)) if m.group(3) else None
        hits.append(_Hit(m.start(), m.end(), "explicit", (int(m.group(1)), mo, y)))
    for m in DATE_TAY_RE.finditer(low):
        hits.append(_Hit(m.start(), m.end(), "explicit", (int(m.group(1)), None, None)))
    # vague phrases hide the day words inside them; overlapping hits keep the longest
    vague = [(m.start(), m.end()) for m in VAGUE_DAY_RE.finditer(low)]
    hits = [h for h in hits if not any(h.start < e and s < h.end for s, e in vague)]
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    kept: list[_Hit] = []
    for h in hits:
        if kept and h.start < kept[-1].end:
            continue
        kept.append(h)
    return kept


def _weekday_dates(wd: int, msg_d: date, tmin: int | None, msg_min: int,
                   nxt: bool, prv: bool, this: bool) -> tuple[date | None, date | None]:
    monday = msg_d - timedelta(days=msg_d.weekday())
    if nxt:
        f: date | None = monday + timedelta(days=7 + wd)
    elif prv:
        f = None
    elif this:
        d = monday + timedelta(days=wd)
        f = d if d >= msg_d else None
    else:
        delta = (wd - msg_d.weekday()) % 7
        if delta == 0 and not (tmin is not None and tmin > msg_min):
            delta = 7                                   # same weekday: today only when the stated time is ahead
        f = msg_d + timedelta(days=delta)
    if prv:
        p: date | None = monday - timedelta(days=7) + timedelta(days=wd)
    elif nxt:
        p = None
    elif this:
        d = monday + timedelta(days=wd)
        p = d if d <= msg_d else None
    else:
        delta = (msg_d.weekday() - wd) % 7
        if delta == 0 and not (tmin is not None and tmin <= msg_min):
            delta = 7
        p = msg_d - timedelta(days=delta)
    return f, p


def _explicit_dates(d: int, m: int | None, y: int | None, msg_d: date) -> tuple[date | None, date | None]:
    if not 1 <= d <= 31 or (m is not None and not 1 <= m <= 12):
        return None, None
    if y is not None:
        exact = _mk_date(y + 2000 if y < 100 else y, m or 0, d) if m else None
        return exact, exact
    if m is not None:
        f = next((x for yy in range(msg_d.year, msg_d.year + 5) if (x := _mk_date(yy, m, d)) and x >= msg_d), None)
        p = next((x for yy in range(msg_d.year, msg_d.year - 5, -1) if (x := _mk_date(yy, m, d)) and x <= msg_d), None)
        return f, p
    f = p = None
    for k in range(13):
        idx = msg_d.month - 1 + k
        x = _mk_date(msg_d.year + idx // 12, idx % 12 + 1, d)
        if x and x >= msg_d:
            f = x
            break
    for k in range(13):
        idx = msg_d.month - 1 - k
        x = _mk_date(msg_d.year + idx // 12, idx % 12 + 1, d)
        if x and x <= msg_d:
            p = x
            break
    return f, p


def _day_rows(low: str, cased: str, msg_dt: datetime, tmin: int | None) -> list[_Row]:
    msg_d = msg_dt.date()
    msg_min = msg_dt.hour * 60 + msg_dt.minute
    starts = _clauses(low)
    neg = _neg_clauses(low, starts)
    nxt, prv, this = bool(NEXT_WEEK_RE.search(low)), bool(PREV_WEEK_RE.search(low)), bool(THIS_WEEK_RE.search(low))
    rows = []
    for h in _day_hits(low, cased):
        if h.kind == "same":
            f, p = msg_d, msg_d
        elif h.kind == "next":
            f, p = msg_d + timedelta(days=h.arg), None
        elif h.kind == "past":
            f, p = None, msg_d - timedelta(days=h.arg)
        elif h.kind == "weekday":
            f, p = _weekday_dates(h.arg, msg_d, tmin, msg_min, nxt, prv, this)
        else:
            f, p = _explicit_dates(*h.arg, msg_d)
        ci = _clause_of(starts, h.start)
        rows.append(_Row(h, f, p, ci in neg, ci))
    return rows


def _pick(rows: list[_Row], attr: str) -> _Row | None:
    """First row with a date in that direction outside a busy clause; an explicit date in the same clause as that
    row wins over a relative word or a weekday ("thứ 7 15/11"); a row in a busy clause only when there is no other."""
    pos = [r for r in rows if getattr(r, attr) and not r.neg]
    if pos:
        first = pos[0]
        if first.hit.kind != "explicit":
            same = next((r for r in pos if r.hit.kind == "explicit" and r.clause == first.clause), None)
            if same is not None:
                return same
        return first
    return next((r for r in rows if getattr(r, attr)), None)


def resolve_day(text: str, msg_ts: int, *, past: bool = False) -> str | None:
    """'YYYY-MM-DD' of the day the text names, relative to the local date and time of its message (15.5), or None.
    past=False reads it as a booking (today or later); past=True as a past reference (today or earlier)."""
    cased, low = _norm(text)
    dt = _local(msg_ts)
    rows = _day_rows(low, cased, dt, _first_time(_time_hits(low)))
    row = _pick(rows, "pdate" if past else "fdate")
    if row is None:
        return None
    d = row.pdate if past else row.fdate
    return d.isoformat() if d else None


# ---------------------------------------------------------------- amounts


def _amounts(low: str) -> list[tuple[int, int, int]]:
    """(start, end, đồng) of every amount: 350k, 350.000(đ), 350,000đ, 1tr2, 1 triệu 2, 1,5tr, 350 nghìn, 350000đ."""
    found: list[tuple[int, int, int]] = []
    for m in AMT_SEP_RE.finditer(low):
        found.append((m.start(), m.end(), int(re.sub(r"[.,]", "", m.group(1)))))
    for m in AMT_MIL_RE.finditer(low):
        v = int(m.group(1)) * 1_000_000
        if m.group(2):
            v += int(m.group(2).ljust(2, "0")) * 10_000
        if m.group(3):
            unit = fold(m.group(4) or "")
            t = m.group(3)
            if unit in ("nghin", "ngan", "k"):
                v += int(t) * 1_000
            elif unit == "tram":
                v += int(t) * 100_000
            else:
                v += int(t.ljust(3, "0")) * 1_000
        elif m.group(5):
            v += 500_000
        found.append((m.start(), m.end(), v))
    for m in AMT_K_RE.finditer(low):
        found.append((m.start(), m.end(), int(m.group(1)) * 1_000))
    for m in AMT_RAW_RE.finditer(low):
        found.append((m.start(), m.end(), int(m.group(1))))
    phone_runs = [(m.start(), m.end()) for m in PHONE_RUN_RE.finditer(low)
                  if sum(ch.isdigit() for ch in m.group(0)) >= 9]
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out: list[tuple[int, int, int]] = []
    for s, e, v in found:
        if out and s < out[-1][1]:
            continue
        if any(ps <= s and e <= pe for ps, pe in phone_runs):
            continue
        if AMOUNT_MIN <= v <= AMOUNT_MAX:
            out.append((s, e, v))
    return out


# ---------------------------------------------------------------- message scan


@dataclass
class _Msg:
    idx: int
    ts: int
    owner: bool
    is_text: bool
    day: date
    mins: int
    low: str = ""
    cased: str = ""
    bare: str = ""
    rows: list = field(default_factory=list)
    fday: date | None = None          # booking-direction day outside a busy clause
    pday: date | None = None          # past-direction day outside a busy clause
    past_row: _Row | None = None
    now: bool = False                 # "giờ" / "bây giờ" outside a busy clause
    tmin: int | None = None
    times: list = field(default_factory=list)
    amounts: list = field(default_factory=list)
    services: list = field(default_factory=list)   # (key, service_id|None, name, group)
    durations: set = field(default_factory=set)
    question: bool = False
    third: bool = False               # the spa talking about another customer
    third_subject: bool = False       # the contact talking about a relative's or a friend's visit
    price_list: bool = False
    non_catalog: bool = False
    tech: str | None = None
    f: set = field(default_factory=set)
    anchor: bool = False
    broadcast: bool = False           # a spa message sent to many customers (thanks for the past time, a promotion)
    resched_span: tuple[int, int] | None = None
    pickup: bool = False              # a trip to pick something up, not a session
    next_time: bool = False           # "lần sau", "bữa sau": about the next visit
    total_only: bool = False          # the spa states a total and nothing else about paying
    receipt: bool = False             # a receipt word next to the payment ("nhận", "bill", "hôm nay")
    thanks_named: bool = False        # the spa's thanks names the session (a service, a day word, "đã ghé làm")
    first_contact: bool = False       # an address, opening-hours or price question


def _is_question(text: str, toks: list[re.Match]) -> bool:
    if "?" in text:
        return True
    return bool(toks) and fold(toks[-1].group(0)) in ac.QUESTION_END


def _is_accept(toks: list[re.Match]) -> bool:
    words = [t.group(0) for t in toks]
    if not words or len(words) > SHORT_REPLY_TOKENS:
        return False
    if not any(_word_is(w, ACCEPT_T) for w in words):
        return False
    return not any(_word_is(w, ACCEPT_BLOCK_T) for w in words)


def _visit_verb(toks: list[re.Match], spans: list[tuple[int, int]]) -> bool:
    for k, t in enumerate(toks):
        w = t.group(0)
        if w not in ac.VISIT_VERB_ORIG and w not in ac.VISIT_VERB_PLAIN:
            continue
        if any(s <= t.start() < e for s, e in spans):
            continue                                    # the "qua" of "hôm qua"
        fw = fold(w)
        if fw == "qua" and _tok_is(toks, k - 1, QUA_PREP_PREV_T):
            continue                                    # "chuyển qua", "gửi qua": a preposition
        if fw == "den" and _tok_is(toks, k - 1, DEN_PREP_PREV_T):
            continue                                    # "liên quan đến": about
        return True
    return False


def _ck_payment(toks: list[re.Match], has_amount: bool) -> bool:
    """"ck" as a transfer: next to an amount, after đã / vừa / nhận ..., or followed by rồi / r / xong with only
    filler words between ("ck cho em rồi"). "ck chị về rồi" (the husband came home) is not one."""
    for k, t in enumerate(toks):
        if t.group(0) != "ck":
            continue
        if has_amount:
            return True
        prv = toks[k - 1].group(0) if k > 0 else ""
        if prv in CK_DONE_PREV:
            return True
        for x in toks[k + 1:k + 5]:
            w = x.group(0)
            if w in CK_DONE_NEXT:
                return True
            if w not in CK_FILLER and not _word_is(w, CONTACT_PRONOUN_T):
                break
    return False


def _transfer_amount(low: str, toks: list[re.Match], amounts: list[tuple[int, int, int]]) -> bool:
    """"chuyển 199k", "chuyen 350.000": the verb right before an amount."""
    for t in toks:
        if fold(t.group(0)) != "chuyen" or (has_marks(t.group(0)) and t.group(0) != "chuyển"):
            continue
        if any(t.end() <= s_ <= t.end() + 12 for s_, _e, _v in amounts):
            return True
    return False


def _technician(low: str, cased: str, toks: list[re.Match]) -> str | None:
    """A technician named with a cue (15.4): "kỹ thuật viên số 8", "ktv Hoa", "cho chị bạn Lan làm"."""
    starts = _clauses(low)
    clause_of = [_clause_of(starts, t.start()) for t in toks]
    performers: dict[int, list[int]] = {}
    for j in range(len(toks)):
        if _tok_is(toks, j, PERFORMER_T):
            performers.setdefault(clause_of[j], []).append(j)

    def name_at(k: int, need_capital: bool) -> str | None:
        if k >= len(toks):
            return None
        w, c = toks[k].group(0), cased[toks[k].start():toks[k].end()]
        if fold(w) == "so" and k + 1 < len(toks):
            nxt = toks[k + 1].group(0)
            # a staff number has 1-3 ASCII digits ("số 8"); "số 0938…" is a phone number, "²" is not a digit
            if nxt.isascii() and nxt.isdigit() and len(nxt) <= 3:
                return f"số {int(nxt)}"
            return None
        capital = c[:1].isupper()
        known = w in ac.GIVEN_NAMES or (not has_marks(w) and w in ac.GIVEN_NAMES_PLAIN)
        if not known or (need_capital and not capital) or (not capital and not has_marks(w)):
            return None
        parts = [c[:1].upper() + c[1:].lower()]
        if k + 1 < len(toks):
            w2, c2 = toks[k + 1].group(0), cased[toks[k + 1].start():toks[k + 1].end()]
            if c2[:1].isupper() and (w2 in ac.GIVEN_NAMES or w2 in ac.GIVEN_NAMES_PLAIN) and \
                    clause_of[k + 1] == clause_of[k]:
                parts.append(c2[:1].upper() + c2[1:].lower())
        return " ".join(parts)[:TECH_MAX]

    for m in TECH_STRONG_RE.finditer(low):
        got = name_at(_tok_index(toks, m.end()), need_capital=False)
        if got:
            return got
    for k, t in enumerate(toks):
        if not _word_is(t.group(0), TECH_WEAK_T):
            continue
        got = name_at(k + 1, need_capital=True)
        if not got or _tok_is(toks, k + 1 + len(got.split()), VOCATIVE_T):
            continue                                    # "Em Hoa ơi": the person the contact writes to
        skip = {k, k + 1, k + 2}
        if any(j not in skip for j in performers.get(clause_of[k], ())):
            return got                                  # the clause says who performs the service
    return None


def _contact_subject(toks: list[re.Match], k: int, starts: list[int], low: str) -> bool:
    """The words before toks[k] in its clause leave the contact as the subject: nothing, lead words or a vocative
    ("dạ", "em ơi"), or the contact's pronoun ("chị", "c") that is not part of "mẹ chị", "bạn c" ...; adverbs such
    as "đang", "đã", "ở" are skipped. "Hàng đến rồi", "mùa mưa tới rồi", "giá lên rồi" have another subject."""
    ci = _clause_of(starts, toks[k].start())
    j = k - 1
    while j >= 0 and _clause_of(starts, toks[j].start()) == ci and _tok_is(toks, j, ADVERB_T):
        j -= 1
    if j < 0 or _clause_of(starts, toks[j].start()) != ci:
        return True
    if _tok_is(toks, j, CONTACT_PRONOUN_T):
        seg = low[toks[max(0, j - 2)].start():toks[j].end()]
        return not THIRD_SUBJECT_RE.search(seg)
    return _tok_is(toks, j, LEAD_T) or _tok_is(toks, j, VOCATIVE_T)


_ARRIVE_VERBS = ("toi", "tới", "đến", "den")
_ARRIVE_DONE_NEXT = ("r", "roi", "rồi", "noi", "nơi", "spa", "sanh", "sảnh", "cua", "cửa", "tiem", "tiệm")
_ARRIVE_SOON_NEXT = ("lien", "liền", "ngay")
_SOON_ADVERBS = ("đang", "dang", "sắp", "sap")


def _contact_motion(toks: list[re.Match], starts: list[int]) -> str | None:
    """"c toi r" (plain "toi" is also "tôi") and "chị sắp tới": "arrival" or "en_route" when a pronoun of the
    contact is the subject; "c di r" / "chị đi rồi": en_route."""
    for k, t in enumerate(toks):
        w = t.group(0)
        if w not in _ARRIVE_VERBS and w not in ("đi", "di"):
            continue
        ci = _clause_of(starts, t.start())
        j, soon = k - 1, False
        while j >= 0 and _clause_of(starts, toks[j].start()) == ci and toks[j].group(0) in \
                _SOON_ADVERBS + ("đã", "da", "vừa", "vua", "mới", "moi", "cũng", "cung"):
            soon = soon or toks[j].group(0) in _SOON_ADVERBS
            j -= 1
        if j < 0 or _clause_of(starts, toks[j].start()) != ci or not _tok_is(toks, j, CONTACT_PRONOUN_T):
            continue
        if j >= 1 and THIRD_SUBJECT_RE.search(" ".join(x.group(0) for x in toks[max(0, j - 2):j + 1])):
            continue                                    # "mẹ chị tới rồi"
        nxt = toks[k + 1].group(0) if k + 1 < len(toks) and _clause_of(starts, toks[k + 1].start()) == ci else ""
        if w in ("đi", "di"):
            if nxt in ("r", "roi", "rồi"):
                return "en_route"
            continue
        if soon or nxt in _ARRIVE_SOON_NEXT:
            return "en_route"
        if nxt in _ARRIVE_DONE_NEXT and w == "toi":
            return "arrival"                            # the marked forms are in ARRIVAL_WORDS
    return None


def _weak_reschedule(low: str, rows: list, times: list, service_pos: list[int]) -> tuple[int, int] | None:
    """The span of a "dời sang / đổi qua / đổi" phrase followed by a day or a time and not by a catalog service."""
    for x in RESCHEDULE_WEAK_RE.finditer(low):
        if any(x.end() <= p_ <= x.end() + 3 for p_ in service_pos):
            continue                                    # "đổi sang massage body": another service
        if any(r.hit.start >= x.end() for r in rows) or any(s_ >= x.end() for s_, _e, _t, _n in times):
            return x.start(), x.end()
    return None


_SIGNAL_RES = (BOOKING_ASK_RE, ARRIVAL_RE, EN_ROUTE_RE, CANCEL_RE, CANCEL_WEAK_RE, RESCHEDULE_ANY_RE, PAY_RE,
               CONTACT_FEEDBACK_RE, PAST_VISIT_RE, CONFIRM_RE, NO_SHOW_CONTACT_RE, OWNER_ARRIVAL_RE)


def _third_party(low: str, starts: list[int]) -> bool:
    """A relative or a friend ("mẹ chị", "ck c", "bạn chị") in a clause that also books, arrives, pays, cancels or
    gives feedback: the message is about that person's visit, unless the contact comes too ("chị với bạn chị").
    "mai c ko qua dc r, con c bi om" names the child in another clause: the cancellation is the contact's."""
    if SELF_TOO_RE.search(low):
        return False
    bounds = starts + [len(low) + 1]
    for x in THIRD_SUBJECT_RE.finditer(low):
        head = x.group(0).split()[0]
        before = TOKEN_RE.findall(low[max(0, x.start() - 12):x.start()])
        if head in ("ban", "con", "me") and before and _word_is(before[-1], CONTACT_PRONOUN_T):
            continue                                    # "c ban e oi" (bận), "c con 2 buoi" (còn): a verb
        ci = _clause_of(starts, x.start())
        clause = low[bounds[ci]:bounds[ci + 1]]
        if any(rx.search(clause) for rx in _SIGNAL_RES) or re.search(r"(?<![^\W_])ck(?![^\W_])",
                                                                       clause.replace(x.group(0), " ")):
            return True
    return False


def _scan(idx: int, raw: Any, catalog: Any) -> _Msg:
    ts = int(getattr(raw, "ts", 0) or 0)
    owner = bool(getattr(raw, "from_owner", False))
    text = getattr(raw, "text", "")
    text = text[:MAX_TEXT] if isinstance(text, str) else ""
    mtype = getattr(raw, "type", "text")
    dt = _local(ts)
    is_text = mtype in ac.TEXT_TYPES and bool(text.strip())
    m = _Msg(idx, ts, owner, is_text, dt.date(), dt.hour * 60 + dt.minute)
    if not is_text:
        return m
    cased, low = _norm(text)
    bare = fold(low)
    m.low, m.cased, m.bare = low, cased, bare
    toks = _toks(low)
    starts = _clauses(low)
    m.times = _time_hits(low)
    m.tmin = _first_time(m.times)
    m.rows = _day_rows(low, cased, dt, m.tmin)
    frow = _pick(m.rows, "fdate")
    m.fday = frow.fdate if frow and not frow.neg else None
    prow = _pick(m.rows, "pdate")
    if prow is not None and not prow.neg:
        m.pday, m.past_row = prow.pdate, prow
    m.now = any(r.hit.now and not r.neg for r in m.rows)
    m.amounts = _amounts(low)
    m.question = _is_question(text, toks)
    service_pos: list[int] = []
    if catalog is not None:
        seen = set()
        for pos, key, sid, name, group in catalog.find(bare):
            service_pos.append(pos)
            if key not in seen:
                seen.add(key)
                m.services.append((key, sid, name, group))
    for x in DUR_MIN_RE.finditer(low):
        if 10 <= int(x.group(1)) <= 240:
            m.durations.add(int(x.group(1)))
    for x in DUR_HOUR_RE.finditer(low):
        m.durations.add(60 * int(x.group(1)) + (30 if x.group(2) else 0))
    m.non_catalog = not m.services and bool(ac.NON_CATALOG_RE.search(bare))
    day_spans = [(r.hit.start, r.hit.end) for r in m.rows]
    f = m.f
    has_amount = bool(m.amounts)

    def hit(rx: re.Pattern, name: str) -> None:
        if rx.search(low):
            f.add(name)

    m.broadcast = owner and bool(BROADCAST_RE.search(low))
    hit(BOOKING_ASK_RE, "ask")
    if _visit_verb(toks, day_spans):
        f.add("visit")
    hit(CONFIRM_RE, "confirm")
    if not m.broadcast:
        hit(AVAILABILITY_RE, "avail")
    if _is_accept(toks) and not m.question and not has_amount:
        f.add("accept")                                 # "dạ 150k ạ" answers a price, it accepts nothing
    if REMINDER_RE.search(low) and not m.question and not m.broadcast:
        f.add("reminder")
    hit(CANCEL_RE, "cancel")
    if "cancel" not in f and CANCEL_WEAK_RE.search(low) and not m.services and not PRICE_INQUIRY_RE.search(low):
        f.add("cancel")                                 # "để lần sau" about the booking, not about another service
    strong = RESCHEDULE_RE.search(low)
    m.resched_span = (strong.start(), strong.end()) if strong else _weak_reschedule(low, m.rows, m.times,
                                                                                     service_pos)
    if m.resched_span is not None:
        f.add("resched")
    hit(PAST_DONE_RE, "done")
    hit(PRICE_INQUIRY_RE, "inquiry")
    if any(all(not (s <= x.start() < e) for s, e in day_spans) for x in PAST_VISIT_RE.finditer(low)):
        f.add("past_visit")                             # a visit word outside the day words ("qua" of "hôm qua")
    m.pickup = bool(PICKUP_RE.search(low)) and not m.services and not re.search(r"(?<![^\W_])(?:làm|lam)(?![^\W_])",
                                                                                 low)
    m.next_time = bool(NEXT_TIME_RE.search(low))
    deposit = bool(DEPOSIT_RE.search(low))
    if deposit:
        f.add("deposit")
    refund = bool(REFUND_RE.search(low)) or (owner and bool(OWNER_REFUND_RE.search(low)))
    product = bool(PRODUCT_RE.search(low))
    total = bool(PAY_TOTAL_RE.search(low)) and has_amount
    pay_words = bool(PAY_RE.search(low))
    ck = _ck_payment(toks, has_amount)
    stk = owner and has_amount and bool(STK_RE.search(low))
    transfer = _transfer_amount(low, toks, m.amounts)
    at_session = bool(PAY_AT_SESSION_RE.search(low))
    # a payment states an amount, says it is done, or is the bill at the session; "chị muốn thanh toán bằng thẻ"
    # and "có nhận chuyển khoản không?" are not payments, nor a deposit, a refund, or a package or product bought
    paying = ck or total or stk or transfer or (pay_words and (has_amount or "done" in f)) or at_session
    if paying and not deposit and not refund and not product and not (m.question and not has_amount):
        f.add("pay")
        if total or (owner and re.search(r"(?<![^\W_])bill(?![^\W_])", low)):
            f.add("pay_total")
        # the spa only states a total ("Dạ tổng 349k ạ"): a payment only after the session or with a receipt word
        m.total_only = owner and total and not (ck or stk or transfer or pay_words or at_session)
        m.receipt = bool(RECEIPT_RE.search(low))
    if owner:
        m.third = bool(OWNER_THIRD_RE.search(low)) or bool(ac.KHACH_RE.search(bare))
        m.third_subject = _third_party(low, starts)     # "em giữ lịch cho bạn chị": someone else's booking
        distinct = {v for _s, _e, v in m.amounts}
        m.price_list = (len(distinct) >= 2 and "pay_total" not in f) or \
            (has_amount and bool(PRICE_LIST_RE.search(low)) and "pay" not in f)
        hit(NO_SHOW_OWNER_RE, "no_show")
        if "no_show" in f and re.search(r"(?<![^\W_])(?:lâu|lau)(?![^\W_])", low):
            f.discard("no_show")                         # "lâu rồi không thấy chị": long time no see
        for x in OWNER_ARRIVAL_RE.finditer(low):
            ci = _clause_of(starts, x.start())
            tail = low[x.end():starts[ci + 1] if ci + 1 < len(starts) else len(low)]
            if not NOT_ARRIVAL_OBJECT_RE.search(tail):  # not "mời chị vào nhóm Zalo"
                f.add("arrival")
                break
        ghe_tham = bool(GHE_THAM_RE.search(low)) and not any(r.hit.kind in ("same", "past") for r in m.rows)
        if THANKS_VISIT_RE.search(low) and not NOT_VISIT_RE.search(low) and not m.broadcast and not ghe_tham:
            f.add("thanks")
            m.thanks_named = bool(m.services) or any(r.hit.kind in ("same", "past") for r in m.rows) or bool(
                re.search(r"(?<![^\W_])(?:đã|da)\s+(?:ghé|ghe|qua|đến|den|tới)\s+(?:làm|lam|gội|goi)(?![^\W_])", low))
        hit(OWNER_FEEDBACK_RE, "feedback")
    else:
        m.third_subject = _third_party(low, starts)
        m.first_contact = bool(FIRST_CONTACT_RE.search(low))
        hit(NO_SHOW_CONTACT_RE, "no_show")
        motion = _contact_motion(toks, starts)
        if EN_ROUTE_RE.search(low) or EN_ROUTE_MIN_RE.search(low) or EN_ROUTE_PLAIN_RE.search(low) or \
                motion == "en_route" or (m.now and "visit" in f and not m.question):
            f.add("en_route")
        place_starts = {x.start() for x in ARRIVAL_PLACE_RE.finditer(low)}
        for x in ARRIVAL_RE.finditer(low):
            k = _tok_index(toks, x.start())
            if _tok_is(toks, k - 1, ARRIVAL_NOT_AFTER_T) or not _contact_subject(toks, k, starts, low):
                continue
            if x.start() in place_starts:
                k_end = _tok_index(toks, x.end())
                same_clause = k_end < len(toks) and _clause_of(starts, toks[k_end].start()) == \
                    _clause_of(starts, x.start())
                if same_clause and not _tok_is(toks, k_end, ARRIVAL_PLACE_NEXT_T):
                    continue                            # "ở cửa hàng", "ở dưới quê"
            f.add("arrival")
            break
        if motion == "arrival":
            f.add("arrival")
        hit(CONTACT_FEEDBACK_RE, "feedback")
    m.tech = _technician(low, cased, toks)
    m.anchor = bool(
        f & {"ask", "confirm", "avail", "reminder", "cancel", "resched", "no_show", "en_route", "arrival", "thanks",
             "pay", "deposit", "inquiry"}
        or has_amount or ac.PRICE_RE.search(low) or ac.BOOKING_RE.search(bare) or ac.BOOKING_WEAK_RE.search(bare)
        or ac.BOOKING_WEAK_ORIG_RE.search(low) or ac.has_visit_time(low, bare, not has_marks(low))
        or ac.PAST_VISIT_RE.search(bare) or ac.PAST_ORIG_RE.search(low))
    return m


# ---------------------------------------------------------------- per-conversation state


class _Cand:
    def __init__(self, d: date):
        self.date = d
        self.time: int | None = None
        self.rank = -1
        self.sigs: list[tuple[int, str]] = []
        self.cancelled = False
        self.no_show = False
        self.booking_ts: list[int] = []
        self.pays: list[tuple[int, int, bool]] = []
        self.techs: list[tuple[int, str]] = []
        self.msg_idx: set[int] = set()

    def codes(self) -> set[str]:
        return {c for _t, c in self.sigs}

    @property
    def booked(self) -> bool:
        return bool(self.codes() & BOOKING_CODES)

    @property
    def dropped(self) -> bool:
        return self.cancelled or self.no_show

    def slot_ms(self) -> int:
        """The slot start; without a time, the end of the day."""
        return _local_ms(self.date, self.time if self.time is not None else 24 * 60 - 1)

    def visit_ms(self) -> int:
        return _local_ms(self.date, self.time if self.time is not None else 12 * 60)

    def exchange(self) -> tuple[int, int] | None:
        if not self.booking_ts:
            return None
        return min(self.booking_ts) - EXCHANGE_LEAD_MS, max(self.booking_ts)


class _Run:
    def __init__(self, msgs: list[_Msg]):
        self.msgs = msgs
        self.cands: dict[date, _Cand] = {}
        self.pend_req: tuple[date, int] | None = None              # contact request: (date, ts)
        self.pend_prop: tuple[date, int | None, int] | None = None  # spa proposal: (date, minutes, ts)
        # A booking question still without a day ("chị muốn đặt lịch", the spa's "chị qua ngày nào ạ?"): the
        # contact's next message that names a day answers it.
        self.open_ask: int | None = None
        self.touched: list[_Cand] = []
        self.anchors: set[int] = set()
        self.interest_ts: int | None = None     # the contact's latest booking question or visit wish
        self.inquiry_ts: int | None = None      # the contact's latest price question
        self.third_req: tuple[date | None, int] | None = None   # a booking the contact made for someone else
        self.pend_feedback: tuple[date, int] | None = None     # the spa's feedback question about a past day
        # Payments that found no candidate yet (a walk-in pays before the arrival or the thanks): (message, the
        # candidate dates it may join). A later arrival / after_visit / past_reference on one of them takes it.
        self.pend_pays: list[tuple[_Msg, frozenset[date]]] = []

    # -- helpers

    def add(self, m: _Msg, d: date, code: str, *, time: int | None = None, rank: int = -1,
            booking: bool = False) -> _Cand:
        c = self.cands.setdefault(d, _Cand(d))
        c.sigs.append((m.ts, code))
        c.msg_idx.add(m.idx)
        if code in POSITIVE_CODES and (not m.owner or code in ("arrival", "payment")):
            c.cancelled = c.no_show = False             # a spa reminder or thanks does not reopen a dropped slot
        if booking:
            c.booking_ts.append(m.ts)
        if time is not None and rank >= c.rank:
            c.time, c.rank = time, rank
        if c not in self.touched:
            self.touched.append(c)
        self.anchors.add(m.ts)
        if code in VISIT_EVIDENCE_CODES and self.pend_pays:
            self._attach_pending(c, m)
        return c

    def _attach_pending(self, c: _Cand, m: _Msg) -> None:
        """A payment that came before the visit evidence of its day joins it (the order of a walk-in's messages does
        not matter): a payment of day P without a candidate joins the candidate of P or P-1 (15.4: a payment on D+1
        belongs to D) when an arrival, a thanks, a feedback or a past reference for that date comes later, on day P
        or P+1. A payment that names a past day joins only that day; a spa total with a receipt word only P."""
        keep: list[tuple[_Msg, frozenset[date]]] = []
        for p, days in self.pend_pays:
            age = (m.day - p.day).days
            if age > 1:
                continue                                # too old to join anything later
            if c.dropped or p.idx > m.idx or c.date not in days or c.date < m.day - timedelta(days=1):
                keep.append((p, days))
                continue
            self.add(p, c.date, "payment")
            amount = _payment_amount(p)
            if amount is not None:
                c.pays.append((p.ts, amount, "pay_total" in p.f))
                c.pays.sort(key=lambda x: x[0])
        self.pend_pays = keep

    def _pending_pay_on(self, day: date, m: _Msg) -> bool:
        """A payment of `day`, up to and including message m, is still waiting for its visit."""
        return any(p.day == day and p.idx <= m.idx for p, _days in self.pend_pays)

    def _req(self, m: _Msg) -> tuple[date, int] | None:
        return self.pend_req if self.pend_req and m.ts - self.pend_req[1] <= PENDING_MS else None

    def _prop(self, m: _Msg) -> tuple[date, int | None, int] | None:
        return self.pend_prop if self.pend_prop and m.ts - self.pend_prop[2] <= PENDING_MS else None

    def _open_future(self, day: date, exclude: date | None = None) -> _Cand | None:
        opts = [c for c in self.cands.values() if c.booked and not c.dropped and c.date >= day and c.date != exclude]
        return min(opts, key=lambda c: c.date) if opts else None

    def _recent_open(self, m: _Msg) -> date | None:
        opts = [c for c in self.cands.values() if c.booked and not c.dropped and c.date >= m.day and c.booking_ts
                and m.ts - max(c.booking_ts) <= 2 * PENDING_MS]
        return max(opts, key=lambda c: max(c.booking_ts)).date if opts else None

    def _passed(self, c: _Cand, m: _Msg) -> bool:
        return m.ts > c.slot_ms() if c.time is not None else m.day > c.date

    def _clear_pending(self, d: date) -> None:
        if self.pend_req and self.pend_req[0] == d:
            self.pend_req = None
        if self.pend_prop and self.pend_prop[0] == d:
            self.pend_prop = None

    def _after_target(self, m: _Msg, need_passed: bool) -> date | None:
        """The candidate an after_visit or payment message without a day of its own joins (15.4): the booking on
        the message date when its slot is not more than one hour ahead, else the candidate of the day before, else
        (need_passed False) the booking later that day. Never a new candidate: a payment or a thanks alone does not
        show a visit (see the module docstring)."""
        same = self.cands.get(m.day)
        prev = self.cands.get(m.day - timedelta(days=1))
        slack = 0 if need_passed else AHEAD_SLACK_MS
        if same and not same.dropped and (same.time is None or same.slot_ms() <= m.ts + slack):
            return m.day
        if prev and not prev.dropped:
            return prev.date
        if same and not same.dropped and not need_passed:
            return m.day
        return None

    def _named_past_day(self, m: _Msg) -> date | None:
        """A past day the message names for itself ("hôm qua chị quên ck")."""
        if m.past_row is not None and m.pday is not None and m.pday < m.day and m.past_row.hit.kind == "past":
            return m.pday
        return None

    def _third_reply(self, m: _Msg) -> bool:
        """The spa answering the contact's booking for someone else ("đặt cho mẹ chị 3h mai" / "Dạ em giữ lịch
        cho bác ạ") within 12 hours, while the contact has no booking request of their own pending."""
        if self.third_req is None or m.ts - self.third_req[1] > PENDING_MS:
            return False
        if self.pend_req is not None and self.pend_req[1] > self.third_req[1]:
            return False
        day = self.third_req[0]
        return bool(m.f & {"confirm", "accept", "avail", "reminder"}) and (m.fday is None or day is None
                                                                          or m.fday == day)

    # -- signal handlers

    def _cancel(self, m: _Msg) -> date | None:
        cm = CANCEL_RE.search(m.low) or CANCEL_WEAK_RE.search(m.low)
        ci = _clause_of(_clauses(m.low), cm.start()) if cm else None
        # only a day in the clause of the cancel words names the slot ("hủy lịch nha, mai chị bận": "mai" is the
        # reason, not the slot)
        named = next((r for r in m.rows if r.fdate and (ci is None or r.clause == ci)), None)
        c: _Cand | None = None
        if named is not None:
            c = self.cands.get(named.fdate)
            if named.hit.kind == "weekday" and named.fdate == m.day + timedelta(days=7):
                today = self.cands.get(m.day)
                if today and today.booked and not today.dropped and not self._passed(today, m):
                    c = today                           # "hủy lịch thứ 7" sent on that Saturday before the slot
            if c is not None and (not c.booked or c.dropped):
                c = None
        if c is None and m.pday is not None and m.pday in self.cands and m.past_row \
                and m.past_row.hit.kind == "past" and (ci is None or m.past_row.clause == ci):
            c = self.cands[m.pday]
        if c is None:
            c = self._open_future(m.day)               # no day, or a day nobody booked: the next open booking
        if c is None or c.dropped:
            return None
        if self._passed(c, m):
            self.add(m, c.date, "no_show")
            c.no_show = True
        else:
            self.add(m, c.date, "cancelled")
            c.cancelled = True
        self._clear_pending(c.date)
        return c.date

    def _no_show(self, m: _Msg) -> None:
        lo = m.day - timedelta(days=NO_SHOW_DAYS)
        opts = [c for c in self.cands.values() if c.booked and not c.dropped and lo <= c.date <= m.day
                and (m.ts > c.slot_ms() if c.time is not None else m.day >= c.date)]
        if m.pday is not None:
            named = [c for c in opts if c.date == m.pday]
            opts = named or opts
        if not opts:
            return
        c = max(opts, key=lambda x: x.date)
        self.add(m, c.date, "no_show")
        c.no_show = True
        self._clear_pending(c.date)

    def _reschedule(self, m: _Msg) -> bool:
        if m.resched_span is None:
            return False
        rs, re_ = m.resched_span
        after = [r for r in m.rows if r.hit.start >= re_ and r.fdate and r.fdate >= m.day]
        before = [r for r in m.rows if r.hit.end <= rs and r.fdate]
        new = after[0].fdate if after else None
        new_t = next((t for s, _e, t, _n in m.times if s >= re_), None)
        old = None
        if before and before[0].fdate in self.cands and self.cands[before[0].fdate].booked:
            old = before[0].fdate
        if old is None:
            oc = self._open_future(m.day, exclude=new)
            old = oc.date if oc else None
        if new is None and new_t is None:
            if old is None:
                return False
            self.add(m, old, "rescheduled")
            self.cands[old].cancelled = True              # moved to a day not named yet
            self._clear_pending(old)
            return True
        if new is None:
            if old is None:
                return False
            new = old                                     # same day, another time
        if old is not None and old != new:
            self.add(m, old, "rescheduled")
            self.cands[old].cancelled = True
            self._clear_pending(old)
        self.add(m, new, "rescheduled")
        code = "booking_confirmed" if m.owner else "booking_request"
        self.add(m, new, code, time=new_t if new_t is not None else m.tmin, rank=3, booking=True)
        self.pend_prop = None
        self.pend_req = None if m.owner else (new, m.ts)
        return True

    def _payment(self, m: _Msg) -> None:
        """A payment joins the candidate of its day or the day before (15.4); it never makes a candidate alone. A
        spa total that answers the contact's price question, or that comes before the session without a receipt
        word, is a quote and not a payment."""
        d = self._named_past_day(m)
        if d is not None and (d not in self.cands or self.cands[d].dropped):
            d = None
        if d is None:
            d = self._after_target(m, need_passed=False)
        if m.total_only:
            answers = self.inquiry_ts is not None and 0 <= m.ts - self.inquiry_ts <= QUOTE_INQUIRY_MS
            c = self.cands.get(d) if d is not None else None
            held = c is not None and (bool(c.codes() & {"arrival", "after_visit", "payment"}) or m.ts >= c.slot_ms()
                                      or d < m.day)
            if answers or not (held or m.receipt):
                m.f.discard("pay")                      # a quote ("Dạ tổng 349k ạ"): the quote rules may use it
                m.f.discard("pay_total")
                return
        if d is None:
            # no candidate yet: a walk-in may pay before the arrival or the thanks of the same day; the payment
            # waits for that visit evidence (_attach_pending) and never makes a candidate alone
            named = self._named_past_day(m)
            days = {named} if named is not None else (
                {m.day} if m.total_only else {m.day, m.day - timedelta(days=1)})
            self.pend_pays = [(p, ds) for p, ds in self.pend_pays if (m.day - p.day).days <= 1]
            self.pend_pays.append((m, frozenset(days)))
            return
        c = self.add(m, d, "payment")
        amount = _payment_amount(m)
        if amount is not None:
            c.pays.append((m.ts, amount, "pay_total" in m.f))

    def _past_reference(self, m: _Msg) -> date | None:
        if m.pday is None or m.past_row is None or m.pday > m.day:
            return None
        if m.question and not (m.owner and "feedback" in m.f):
            return None
        if "past_visit" not in m.f and not m.services:
            return None
        if NOT_PAST_VISIT_RE.search(m.low):
            return None                                 # work, another place, another spa, an intent, a failed trip
        if not (m.services or SPA_EVIDENCE_RE.search(m.low) or ("feedback" in m.f and not m.owner)):
            return None                                 # "hôm qua chị qua ..." without the spa or a service
        if m.owner:
            if "feedback" not in m.f and not m.services:
                return None
            first = next((t.group(0) for t in TOKEN_RE.finditer(m.low)
                          if t.group(0) in ("em", "e", "chị", "chi", "c", "anh", "a", "cô", "chú", "bác")), None)
            if first in ("em", "e"):
                return None                             # the spa about itself ("hôm qua em nghỉ làm")
        kind = m.past_row.hit.kind
        done = "done" in m.f or ("feedback" in m.f and not m.owner)
        if kind == "past":
            pass
        elif kind == "same":
            if not done:
                return None
        elif kind in ("weekday", "explicit"):
            if not done or m.fday is not None or m.pday >= m.day:
                return None
        else:
            return None
        if ac._inquiry_near(m.low, m.past_row.hit.start, m.past_row.hit.end, not has_marks(m.low)):
            return None
        return m.pday

    def _feedback(self, m: _Msg) -> None:
        if m.third_subject or m.third:
            return
        pref = self._past_reference(m)
        if pref is not None:
            self.add(m, pref, "past_reference")
            if "feedback" in m.f:
                self.add(m, pref, "after_visit")
            return
        if "feedback" not in m.f:
            return
        d = self._after_target(m, need_passed=True)
        if d is not None and (self.cands[d].booked or self.cands[d].codes() & {"arrival", "payment"}):
            self.add(m, d, "after_visit")
            return
        if m.owner:
            # the spa asks how a session of a named day went ("hôm nay chị thấy buổi massage thế nào ạ?"); the
            # contact's feedback words in reply state that visit (a past_reference made of the two messages)
            if m.past_row is not None and m.pday is not None and m.past_row.hit.kind in ("same", "past") and \
                    (m.services or re.search(r"(?<![^\W_])(?:buổi|buoi)(?![^\W_])", m.low)):
                self.pend_feedback = (m.pday, m.ts)
        elif self.pend_feedback is not None and m.ts - self.pend_feedback[1] <= PENDING_MS and not m.question \
                and not NEGATIVE_RE.search(m.low):
            day = self.pend_feedback[0]
            self.pend_feedback = None
            self.add(m, day, "past_reference")
            self.add(m, day, "after_visit")

    def _technician(self, m: _Msg) -> None:
        if m.next_time and m.fday is None:
            return                                      # "lần sau cho chị bạn Hoa làm": the next visit
        live = [x for x in self.touched if not x.dropped]
        c: _Cand | None = live[0] if live else None     # not the old date of a reschedule
        if c is None:
            req = self._req(m)
            d = m.fday or (req[0] if req else None)
            c = self.cands.get(d) if d else None
        if c is None:
            c = self._open_future(m.day)
        if c is None:
            for d in (m.day, m.day - timedelta(days=1)):
                if d in self.cands and not self.cands[d].dropped:
                    c = self.cands[d]
                    break
        if c is not None and m.tech:
            c.techs.append((m.ts, m.tech))

    # -- per side

    def _contact(self, m: _Msg) -> None:
        f = m.f
        if m.third_subject:
            # a booking, arrival or payment for a relative or a friend ("đặt cho mẹ chị", "ck chị tới rồi"): no
            # signal for the contact; the spa's answer to that booking is not the contact's booking either
            if f & {"ask", "visit"}:
                self.third_req = (m.fday, m.ts)
            return
        if "resched" in f and self._reschedule(m):
            return
        cancelled = self._cancel(m) if "cancel" in f else None
        if "no_show" in f:
            self._no_show(m)
        future = m.fday is not None and m.fday > m.day
        past_only = m.past_row is not None and m.past_row.hit.kind == "past"
        if "en_route" in f and not future and not past_only and not m.pickup:
            if m.day in self.cands:
                self.add(m, m.day, "en_route")
            return
        if "arrival" in f and not future and not past_only and not m.question and not m.pickup:
            self.add(m, m.day, "arrival")
            if "pay" in f:
                self._payment(m)
            return
        self._contact_booking(m, cancelled)
        if "pay" in f:
            self._payment(m)
        self._feedback(m)

    def _contact_booking(self, m: _Msg, skip: date | None) -> None:
        f = m.f
        prop, req = self._prop(m), self._req(m)
        if prop and "accept" in f and m.fday in (None, prop[0]):
            t = prop[1] if prop[1] is not None else m.tmin
            c = self.add(m, prop[0], "booking_confirmed", time=t, rank=2, booking=True)
            c.booking_ts.append(prop[2])
            self.pend_prop = self.pend_req = None
            return
        if m.pickup:
            return                                      # "mai chị qua lấy khăn": not a session
        answers = self.open_ask is not None and m.ts - self.open_ask <= PENDING_MS
        if not ("ask" in f or "visit" in f or answers):
            return
        if m.fday is not None and m.fday != skip and m.day <= m.fday <= m.day + timedelta(days=MAX_AHEAD_DAYS):
            same_day_done = m.fday == m.day and "done" in f and not m.question
            if same_day_done:
                return                                   # "hôm nay chị qua rồi": a statement, not a request
            self.add(m, m.fday, "booking_request", time=m.tmin, rank=0, booking=True)
            self.pend_req = (m.fday, m.ts)
            return
        if m.fday is None and m.tmin is not None:
            target = prop[0] if prop else (req[0] if req else None)
            if target is not None and not m.rows:
                self.add(m, target, "booking_request", time=m.tmin, rank=1 if prop else 0, booking=True)
                self.pend_req = (target, m.ts)

    def _owner(self, m: _Msg) -> None:
        f = m.f
        if m.third_subject or self._third_reply(m):
            if self._third_reply(m):
                self.third_req = None
            return                                      # the spa about a relative's or a friend's booking
        if "resched" in f and self._reschedule(m):
            return
        if "cancel" in f:
            self._cancel(m)
        if "no_show" in f:
            self._no_show(m)
        if "reminder" in f:
            d = m.fday
            if d is None:
                oc = self._open_future(m.day)
                d = oc.date if oc else None
            if d is not None and not (d in self.cands and self.cands[d].dropped):
                self.add(m, d, "reminder", time=m.tmin, rank=1)
        if not f & {"cancel", "no_show"}:
            self._owner_booking(m)
        future = m.fday is not None and m.fday > m.day
        if "arrival" in f and not future and not m.question:
            self.add(m, m.day, "arrival")
        thanks_open = False
        if "thanks" in f:
            # a thanks joins the visit it follows; alone it makes a candidate only when it names the session (a
            # service, a day word, "đã ghé làm") or follows a payment of the same day that is waiting for its visit
            # (a walk-in: "chị ck 199k rồi nha" then "cảm ơn chị đã ghé ạ"): "cảm ơn chị đã ghé thăm" also answers a
            # price question
            d = self._named_past_day(m)
            if d is not None and d not in self.cands and not m.thanks_named:
                d = None
            if d is None:
                d = self._after_target(m, need_passed=False)
            if d is None and (m.thanks_named or self._pending_pay_on(m.day, m)):
                d = m.day
            if d is not None:
                self.add(m, d, "after_visit")
            else:
                thanks_open = True
        if "pay" in f:
            self._payment(m)
        if thanks_open and not m.total_only and self._pending_pay_on(m.day, m):
            self.add(m, m.day, "after_visit")           # "Dạ em nhận 199k rồi, cảm ơn chị đã ghé ạ": one message
        if "thanks" not in f:
            self._feedback(m)

    def _owner_booking(self, m: _Msg) -> None:
        f = m.f
        req = self._req(m)
        if "confirm" in f and not m.question:
            d = m.fday or (req[0] if req else None) or self._recent_open(m)
            if d is not None and d >= m.day:
                self.add(m, d, "booking_confirmed", time=m.tmin, rank=2, booking=True)
                self.pend_req = self.pend_prop = None
                return
        if "avail" in f and (m.tmin is not None or m.fday is not None):
            d = m.fday or (req[0] if req else None)
            asked = req is not None or (self.interest_ts is not None and m.ts - self.interest_ts <= PENDING_MS)
            # a slot offered to the contact: after the contact asked, or a question naming a time ("mai bên em còn
            # trống 3h, chị qua không ạ?"); not an announcement ("thứ 7 này bên em còn trống lịch, chị qua nha")
            if d is not None and d >= m.day and (asked or (m.tmin is not None and m.question)) and \
                    (m.tmin is not None or not m.question):
                self.pend_prop = (d, m.tmin, m.ts)
                self.anchors.add(m.ts)
            return
        if req and "accept" in f and m.fday in (None, req[0]):
            self.add(m, req[0], "booking_confirmed", time=m.tmin, rank=2, booking=True)
            self.pend_req = None
            return
        if req and (m.tmin is not None or (m.fday is not None and not m.question)):
            d = m.fday or req[0]
            if d >= m.day:
                self.pend_prop = (d, m.tmin, m.ts)       # "dạ chị qua 4h nha": the contact may accept

    # -- run

    def run(self) -> None:
        for m in self.msgs:
            if not m.is_text:
                continue
            self.touched = []
            if m.anchor:
                self.anchors.add(m.ts)
            if (m.owner and (m.third or m.price_list)) or m.non_catalog:
                continue
            n_booking = sum(len(c.booking_ts) for c in self.cands.values())
            try:
                (self._owner if m.owner else self._contact)(m)
                if m.tech:
                    self._technician(m)
            except Exception:  # noqa: BLE001 - one message the rules cannot read is skipped, not the conversation
                continue
            if sum(len(c.booking_ts) for c in self.cands.values()) > n_booking:
                self.open_ask = None                    # the question got its booking
            elif (not m.owner and "ask" in m.f) or (m.owner and m.question and m.f & {"ask", "visit", "avail"}):
                self.open_ask = m.ts
            if not m.owner and not m.third_subject:
                if m.f & {"ask", "visit"}:
                    self.interest_ts = m.ts
                if "inquiry" in m.f:
                    self.inquiry_ts = m.ts

    # -- output

    def candidate(self, c: _Cand, prices: dict | None) -> dict[str, Any]:
        services = self._services(c)
        amount, source = self._amount(c, services, prices)
        seen: list[str] = []
        for _ts, code in sorted(c.sigs, key=lambda s: s[0]):    # chronological: a waiting payment joins late
            if code not in seen:
                seen.append(code)
        best: dict[int, int] = {}
        for ts, code in c.sigs:
            r = SIGNAL_PRIORITY.index(code) if code in SIGNAL_PRIORITY else len(SIGNAL_PRIORITY)
            best[ts] = min(best.get(ts, r), r)
        evidence = sorted(sorted(best, key=lambda t: (best[t], t))[:MAX_EVIDENCE])
        t = None if c.time is None else f"{c.time // 60:02d}:{c.time % 60:02d}"
        return {
            "date": c.date.isoformat(), "time": t, "time_known": t is not None,
            "visited_at_local": f"{c.date.isoformat()} {t or '12:00'}",
            "services": services, "amount_vnd": amount, "amount_source": source,
            "technician": c.techs[-1][1] if c.techs else None,
            "confidence": None, "signals": seen, "evidence_at": evidence, "source": "chat_rules",
        }

    def _related(self, c: _Cand) -> list[tuple[_Msg, int]]:
        """(message, basis index) of every message whose services count for this candidate."""
        ex = c.exchange()
        day_end = _local_ms(c.date + timedelta(days=1), 0)
        visit = c.visit_ms()
        out = []
        for m in self.msgs:
            if not m.is_text or m.price_list or (m.owner and m.third) or m.non_catalog:
                continue
            if ex and ex[0] <= m.ts <= ex[1] and m.ts < day_end:
                out.append((m, 0))
            elif m.day == c.date or m.idx in c.msg_idx:
                out.append((m, 1))
            elif visit - WINDOW_MS <= m.ts < visit:
                out.append((m, 2))
        return out

    def _booking_services(self, c: _Cand) -> tuple[set[str], set[str]]:
        """Keys and groups of the services named in the messages that made this candidate's booking."""
        stamps = set(c.booking_ts)
        keys: set[str] = set()
        groups: set[str] = set()
        for m in self.msgs:
            if m.is_text and m.ts in stamps:
                for key, _sid, _name, group in m.services:
                    keys.add(key)
                    groups.add(group)
        if not keys and stamps:
            # the spa confirmed without naming a service: the contact's last message before it names it
            first = min(stamps)
            asked = next((m for m in reversed(self.msgs) if m.is_text and not m.owner and m.services
                          and first - PENDING_MS <= m.ts <= first), None)
            if asked is not None:
                keys = {k for k, _s, _n, _g in asked.services}
                groups = {g for _k, _s, _n, g in asked.services}
        return keys, groups

    def _services(self, c: _Cand) -> list[dict[str, Any]]:
        keys, groups = self._booking_services(c)
        acc: dict[str, list] = {}
        for m, basis in self._related(c):
            for key, sid, name, group in m.services:
                if keys and basis != 1 and key not in keys and group not in groups:
                    continue        # asked about in the exchange ("massage body bao nhiêu?") but not what was booked
                a = acc.setdefault(key, [basis, 0, 0, sid, name, group, key])
                a[0] = min(a[0], basis)
                a[1] += 1
                a[2] = max(a[2], m.ts)
        ranked = sorted(acc.values(), key=lambda a: (a[0], -a[1], -a[2]))[:MAX_SERVICES]
        return [{"service_id": a[3], "service_name": a[4], "basis": BASIS[a[0]], "_group": a[5], "_key": a[6]}
                for a in ranked]

    def _quote_fits(self, q: _Msg, c: _Cand, services: list[dict], ex_groups: set[str]) -> bool:
        """A quote counts for this visit when the service it prices (named in the quote, or in the contact's
        message it answers) is the booked one; with no service named, only when the exchange is about one kind
        of service. An answer to "... để lần sau" is about another visit."""
        answered = next((x for x in reversed(self.msgs[:q.idx]) if x.is_text and not x.owner
                         and q.ts - x.ts <= 2 * HOUR_MS), None)
        if answered is not None and (NEXT_TIME_RE.search(answered.low) or CANCEL_WEAK_RE.search(answered.low)):
            return False
        named = q.services or (answered.services if answered is not None else [])
        if not named:
            return len(ex_groups) <= 1
        keys, groups = self._booking_services(c)
        if not keys and services:
            keys, groups = {services[0]["_key"]}, {services[0]["_group"]}
        return any(k in keys or g in groups for k, _s, _n, g in named)

    def _amount(self, c: _Cand, services: list[dict], prices: dict | None) -> tuple[int | None, str | None]:
        if c.pays:
            totals = [p for p in c.pays if p[2]]
            return (totals or c.pays)[-1][1], "paid"
        ex = c.exchange()
        if ex:
            day_end = _local_ms(c.date + timedelta(days=1), 0)
            ex_msgs = [m for m in self.msgs if m.is_text and ex[0] <= m.ts <= ex[1] + QUOTE_TAIL_MS
                       and m.ts < day_end and not m.price_list and not (m.owner and m.third)]
            ex_groups = {g for m in ex_msgs for _k, _s, _n, g in m.services}
            quotes = [m for m in ex_msgs if m.owner and not m.f & {"deposit", "pay"}
                      and len({v for _s, _e, v in m.amounts}) == 1]
            for q in reversed(quotes):
                if self._quote_fits(q, c, services, ex_groups):
                    return q.amounts[0][2], "quoted"
        if prices:
            price = self._list_price(c, services, prices)
            if price is not None:
                return price, "list_price"
        return None, None

    def _list_price(self, c: _Cand, services: list[dict], prices: dict) -> int | None:
        named = [s for s in services if s["service_id"]]
        if len(named) != 1:
            return None
        sid, group = named[0]["service_id"], named[0]["_group"]
        if any(s["service_id"] is None and s["_group"] != group for s in services):
            return None                                   # another kind of service was named too
        variants = list(prices.get(sid) or [])
        durations: set[int] = set()
        for m, _basis in self._related(c):
            durations |= m.durations
        if durations:
            variants = [v for v in variants if v.get("duration_min") in durations]
        if c.time is not None:
            variants = [v for v in variants if _in_window(v.get("time_window"), c.time)]
        found = {v["price_vnd"] for v in variants}
        return found.pop() if len(found) == 1 else None


def _in_window(window: str | None, minutes: int) -> bool:
    """09:00-20:30 (inclusive), after_20:30, before_10:00; an unknown format does not exclude."""
    if not window:
        return True

    def mins(s: str) -> int | None:
        x = re.fullmatch(r"(\d{1,2}):(\d{2})", s.strip())
        return int(x.group(1)) * 60 + int(x.group(2)) if x else None
    w = window.strip().lower()
    if w.startswith("after_"):
        x = mins(w[6:])
        return True if x is None else minutes > x
    if w.startswith("before_"):
        x = mins(w[7:])
        return True if x is None else minutes < x
    if "-" in w:
        a, b = w.split("-", 1)
        x, y = mins(a), mins(b)
        if x is not None and y is not None:
            return x <= minutes <= y
    return True


def _payment_amount(m: _Msg) -> int | None:
    """The amount of a payment message: its only amount; else the amount right after the last total word ("tổng",
    "tổng cộng", "thành tiền", "="), so a bill that lists items first gives the total; else the amount that is the
    sum of the others; else none."""
    vals = [v for _s, _e, v in m.amounts]
    if not vals:
        return None
    if len(set(vals)) == 1:
        return vals[0]
    marks = [x.end() for x in TOTAL_LAST_RE.finditer(m.low)] + [x.end() for x in re.finditer(r"=", m.low)]
    if marks:
        after = [v for s, _e, v in m.amounts if s >= max(marks)]
        if after:
            return after[0]
    for v in vals:
        rest = list(vals)
        rest.remove(v)
        if rest and sum(rest) == v:
            return v
    return None


def _confidence(c: _Cand, today: date, later: bool) -> str:
    """15.4. later: the contact wrote within 72 hours after the slot, and not an address, opening-hours or price
    question (see the module docstring)."""
    codes = c.codes()
    booking = codes & {"booking_request", "booking_confirmed", "reminder"}
    visit = codes & {"en_route", "arrival", "after_visit", "payment"}
    if booking and visit:
        return "high"
    if "payment" in codes and codes & {"arrival", "after_visit"}:
        return "high"
    if codes & {"booking_confirmed", "reminder"} and c.date < today and later:
        return "medium"
    if codes & {"arrival", "after_visit", "payment"}:
        return "medium"
    if "past_reference" in codes:
        return "medium"
    return "low"


def _later_message(c: _Cand, msgs: list[_Msg]) -> bool:
    slot = c.slot_ms()
    return any(not m.owner and slot < m.ts <= slot + LATER_MSG_MS and not m.first_contact for m in msgs)


# ---------------------------------------------------------------- public: extraction


def _safe_scan(idx: int, raw: Any, catalog: Any) -> _Msg:
    """_scan, or the message as a non-text one when the rules cannot read it (the conversation is kept)."""
    try:
        return _scan(idx, raw, catalog)
    except Exception:  # noqa: BLE001 - no text of the message is kept or raised
        ts = int(getattr(raw, "ts", 0) or 0)
        dt = _local(ts)
        return _Msg(idx, ts, bool(getattr(raw, "from_owner", False)), False, dt.date(), dt.hour * 60 + dt.minute)


def extract_visits(msgs, catalog, now_ms: int, prices: dict | None = None) -> dict:
    """Visit candidates of one conversation (15.4). msgs: objects with ts, from_owner, text, type (any order).
    catalog: an analyze_contacts.Catalog or None. now_ms: the analysis time; bookings after its local date go to
    "upcoming" without a confidence. prices: load_prices() output, for list_price; None skips list_price."""
    raw = sorted(list(msgs or []), key=lambda x: int(getattr(x, "ts", 0) or 0))
    scanned = [_safe_scan(i, x, catalog) for i, x in enumerate(raw)]
    run = _Run(scanned)
    run.run()
    today = _local(int(now_ms)).date()
    visits: list[dict] = []
    upcoming: list[dict] = []
    dropped = {"cancelled": 0, "no_show": 0}
    for d in sorted(run.cands):
        c = run.cands[d]
        if not c.sigs:
            continue
        if c.no_show:
            dropped["no_show"] += 1
            continue
        if c.cancelled:
            dropped["cancelled"] += 1
            continue
        if not (c.codes() & POSITIVE_CODES):
            continue
        out = run.candidate(c, prices)
        for s in out["services"]:
            s.pop("_group", None)
            s.pop("_key", None)
        if d > today:
            out.pop("confidence")
            upcoming.append(out)
        else:
            out["confidence"] = _confidence(c, today, _later_message(c, scanned))
            visits.append(out)
    return {"visits": visits, "upcoming": upcoming, "dropped": dropped, "anchor_ts": sorted(run.anchors)}
