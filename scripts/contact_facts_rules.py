"""Phone number and benefit (package, voucher) rules for one 1:1 Zalo conversation. Pure functions, no I/O.

Chat-facts contract, sections 15.4 ("Phone and benefits") and 15.75. A message is any object with the attributes
ts (epoch ms), from_owner (True: the spa's account wrote it), text and type; only text messages are read
(analyze_contacts.TEXT_TYPES). Nothing is printed or logged. No returned value holds message text: a phone is the
normalised number, a benefit title is a label built here ("Gói 10 buổi", "Voucher 1 buổi", "Voucher 100.000đ",
"Voucher giảm 20%", plus " – " and the catalog name of the service when one is resolved).

Spelling (the analyze_contacts convention): rules read the lowercased NFC text and its diacritic-free copy, aligned
character by character. A plain spelling counts only when the word in the message is itself written without
diacritics (has_marks), so "gội" and "gọi" are never "gói". A few plain spellings that are also other words count
only in a narrow pattern: plain "goi" (gói / gội / gọi) only right before a count ("goi 10 buoi") or "cua <pronoun>",
plain "the" (thẻ / thế / thể) only right before a count, plain "con" (còn / con) only right before a count.

Phone (extract_phone)
  Only the contact's own text messages. Digit groups joined by one or two spaces, or by "." / "-" (with optional
  spaces), form a run; a run must split, at group boundaries, into valid numbers only (normalize_phone), otherwise
  none of it is a phone (an 11- or 12-digit run, an amount, a date). A run glued to letters is skipped, except after
  "sđt" / "đt" / "zalo" / "số". URLs and e-mail addresses are blanked first. Cues in the same message decide:
    - reject cues: a bank account or a payment ("stk", "tài khoản", "chuyển khoản", "ck", bank and wallet names),
      an order or transaction code ("mã đơn", "mã giao dịch", "hóa đơn", "ref"), an identity card ("cccd"), a
      business line ("hotline", "tổng đài"), someone else's number ("số chồng", "sđt của mẹ", "số shipper");
    - phone cues: "sđt", "số điện thoại", "đt", "số chị / em / anh / mình / của ...", "gọi", "liên hệ", "zalo";
    - the nearest cue before the number (within 40 characters) decides, else the nearest after it (within 20);
      otherwise any reject cue in the message rejects, any phone cue makes it high;
    - no cue: high when the message is the number alone (courtesy words such as "dạ", "ạ", "nha", "em" allowed),
      else medium.
  A number the spa wrote before the contact first wrote it (the spa's hotline, echoed back) is not the contact's.
  Another person named with a possessive pronoun ("mẹ chị", "sdt me c", "bạn của c", "em gái chị", "người nhà"), in
  the number's message or in the contact's message up to 30 minutes before it, rejects the number unless it is named
  as the contact's own right before it ("sđt chị 09…", "số của chị là 09…"). Plain spellings count there ("sdt",
  "me c", "ban c"): the pronoun after the noun removes the ambiguity.
  The latest high wins; without one, the latest medium. One number per message: the first one accepted.

Benefits (extract_benefits)
  A benefit comes only from a statement; a bare mention ("bên em có gói 10 buổi"), a question (a clause ending in
  "?" or a question word such as không / chưa / hả / nhỉ / mấy, or containing "bao nhiêu"), an intent ("muốn",
  "định", "nếu", plain "chac" ...), or a negated verb never makes one. Statements:
    - purchase: mua / lấy / chốt / đăng ký / đk / kích hoạt / gia hạn (+ up to 4 words: thêm, 1, cho, a pronoun)
      + a package keyword (gói, liệu trình, combo, thẻ) with a count ("gói 10 buổi", "gói gội đầu 10 buổi") ->
      total_count. From the spa only when it is done: "đã" before the verb, "rồi" after it, or "cho chị" (the spa
      registering it for the contact); "chị lấy gói 10 buổi nha" from the spa is a suggestion;
    - possession: "gói 10 buổi của chị", "chị đang có gói 10 buổi" (spa) -> total_count;
    - remaining: "còn [lại] N buổi" next to a package keyword, after a pronoun of the contact ("chị còn 3 buổi"), or
      with package vocabulary in the conversation in the 24 hours before ("dạ còn 4 buổi ạ" answering "chị còn mấy
      buổi"); not "còn 2 buổi trống"; "không còn buổi nào" and "gói ... đã hết" -> 0;
    - ordinal: "buổi thứ 4/10" -> total 10, remaining 6; "buổi thứ 4 trong gói 10 buổi" likewise. A plain
      "buoi thu 4/10" may be a date ("buổi thử 4/10") and counts only next to a package keyword or when it cannot
      be a date;
    - voucher: "voucher", "phiếu quà tặng", "thẻ quà tặng", "phiếu giảm giá", "coupon" given or held ("em tặng chị
      voucher 1 buổi", "voucher của chị", "chị được tặng voucher"), or "tặng [chị] N buổi" without the word. The
      gift must name the contact ("tặng chị", "cho chị") or, from the contact, be passive ("được tặng"); a contact
      repeating an offer ("bên em tặng voucher cho khách mới") is not a benefit. Count, value ("100k") or percent.
      A clause saying the voucher is spent ("đã dùng") or a package or voucher expired ("hết hạn") is not read as a
      statement; an expiry statement about the contact's package or voucher ("gói của chị hết hạn rồi") removes the
      latest benefit of that kind (a promotion ending in an advertisement does not).
    - another person's benefit: a clause naming another person with a possessive ("cho mẹ chị", "bạn c") or a gift
      passed on ("tặng bạn"; from the spa "để chị tặng ...") is not read, nor a statement within 2 hours after a
      message about another person's package or voucher (the spa answering "mua voucher tặng bạn c").
  The spa's statements are high, the contact's medium. A spa message that advertises (ưu đãi, khuyến mãi, chương
  trình, áp dụng, quý khách, khách hàng, a percent, a price next to a package, or two package sizes) keeps only the
  statements personal to the contact (possession, a pronoun, an ordinal, a completed purchase, a voucher addressed to
  the contact). A catalog service (analyze_contacts.Catalog) within 3 words of the statement, in the same clause,
  names the package; a catalog match whose marked words disagree with the service's own spelling is ignored ("gói
  đầu tiên" is not "gội đầu").
  Same package: same kind, and service, count and value not in conflict (a remaining above the count conflicts); the
  most recently updated match takes the statement, and the latest statement wins field by field (a field the
  statement does not state is kept). A purchase starts a new package when it says "thêm" / "nữa" or the matching
  package is used up. At most 5 benefits: the 5 most recently stated, oldest first.

A message is read up to MAX_TEXT characters (the rules slow down with the square of a message's length).

anchor_timestamps: every text message (both sides) with package or voucher vocabulary: a package keyword, a voucher
keyword, "tặng N buổi", "còn N buổi" (not "trống"), "buổi thứ N", "mấy buổi" / "bao nhiêu buổi". Advertisements and
questions are included: this is vocabulary for the model pass window, not a benefit.
"""

# No "from __future__ import annotations": with real annotations the dataclasses below also work when a caller loads
# this file with importlib without registering it in sys.modules.
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import analyze_contacts as ac  # noqa: E402

DAY_MS = ac.DAY_MS
MAX_BENEFITS = 5
MAX_COUNT = 200
TITLE_MAX = 120

# ---------------------------------------------------------------- rule tables: phone

PHONE_VALID_RE = re.compile(r"^0[35789][0-9]{8}$")
PHONE_INPUT_RE = re.compile(r"^\(?\+?[0-9][0-9 .\-()]*$")
PHONE_SEP_RE = re.compile(r"^(?: {1,2}| ?[.\-] ?)$")          # between digit groups of one number
PAREN_84_RE = re.compile(r"\(\s*(\+?84)\s*\)")
URL_EMAIL_RE = re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+", re.IGNORECASE)
DIGITS_RE = re.compile(r"[0-9]+")
CUE_BEFORE_MAX = 40       # characters between a cue and the number after it
CUE_AFTER_MAX = 20        # characters between the number and a cue after it

# (spelling with diacritics, plain spelling also counts). Plain spellings count only for words written without marks.
PHONE_CUES: tuple[tuple[str, bool], ...] = (
    ("sđt", True), ("số điện thoại", True), ("số đt", True), ("điện thoại", True), ("đt", True), ("liên hệ", True),
    ("lh", True), ("zalo", True), ("zalo số", True), ("phone", True), ("tel", True),
    ("số chị", True), ("số em", True), ("số anh", True), ("số mình", True), ("số của", True), ("số c", True),
    ("số e", True), ("số a", True), ("số tôi", True), ("số tui", True), ("số mk", True), ("số cj", True),
    ("số cô", False), ("số chú", False), ("số bác", False), ("số mới", False),
    ("gọi", False),        # plain "goi" is also gói / gội: only in the phrases below
    ("gọi cho", True), ("gọi lại", True), ("gọi vào", True), ("gọi số", True), ("gọi em", True), ("gọi e", True),
    ("gọi chị", True), ("gọi c", True), ("gọi anh", True), ("gọi a", True), ("gọi mình", True), ("gọi sđt", True),
)
BANKS = ("vcb", "vietcombank", "techcombank", "tcb", "acb", "mb", "mbbank", "mb bank", "bidv", "vietinbank", "vtb",
         "agribank", "sacombank", "scb", "vpbank", "vp bank", "tpbank", "tp bank", "shb", "hdbank", "ocb", "msb",
         "vib", "eximbank", "seabank", "abbank", "lpbank", "lienvietpostbank", "pvcombank", "baovietbank",
         "kienlongbank", "vietbank", "ncb", "oceanbank", "nam a bank", "bac a bank", "timo", "cake", "momo",
         "zalopay", "zalo pay", "viettelpay", "viettel pay", "viettel money", "vnpay", "shopeepay", "napas", "atm")
REJECT_CUES: tuple[tuple[str, bool], ...] = (
    ("stk", True), ("số tk", True), ("số tài khoản", True), ("tài khoản", True), ("tk", True), ("ngân hàng", True),
    ("chuyển khoản", True), ("ck", True), ("chuyển tiền", True), ("chuyển", True), ("mã", False), ("mã đơn", True),
    ("mã đơn hàng", True), ("đơn hàng", True), ("mã đh", True), ("mã vận đơn", True), ("vận đơn", True),
    ("mã gd", True), ("mã giao dịch", True), ("giao dịch", True), ("mgd", True), ("order", True), ("hóa đơn", True),
    ("hoá đơn", True), ("invoice", True), ("bill", True), ("ref", True), ("mã số thuế", True), ("mst", True),
    ("cccd", True), ("cmnd", True), ("cmt", True), ("căn cước", True), ("hotline", True), ("tổng đài", True),
    ("ship", True), ("shipper", True),
) + tuple((b, True) for b in BANKS)
# Someone else's number: "số chồng", "sđt của mẹ", "zalo người nhà".
_THIRD_HEADS = ("số", "sđt", "đt", "zalo", "số điện thoại")
_THIRD_PEOPLE: tuple[tuple[str, bool], ...] = (
    ("chồng", True), ("ck", True), ("vợ", False), ("vk", True), ("mẹ", False), ("má", False), ("bố", False),
    ("bạn", False), ("người nhà", True), ("nhân viên", True), ("shipper", True), ("ship", True), ("con gái", False),
    ("con trai", False), ("em gái", False), ("anh trai", False), ("chị gái", False))
THIRD_PARTY_CUES: tuple[tuple[str, bool], ...] = tuple(
    (f"{h} {mid}{p}", ok) for h in _THIRD_HEADS for mid in ("", "của ") for p, ok in _THIRD_PEOPLE)
# Another person named with a possessive pronoun ("mẹ chị", "bạn của c", "em gái chị", "ck c"): in the message of a
# number, or in the contact's message just before it, the number may be that person's. Plain spellings count here
# because the pronoun after the noun removes the ambiguity ("me c" is "mẹ chị"); plain "ma", "bo", "vo", "di", "co"
# are left out (mà, bò/bỏ, vô, đi, có).
KIN_ONE = {"bạn", "ban", "mẹ", "me", "má", "ba", "bố", "chồng", "chong", "ck", "vợ", "vk", "con", "dì", "bà", "ông",
           "ong", "cháu", "chau", "sếp", "sep", "bồ", "ny", "người", "nguoi"}
KIN_TWO = {("em", "gái"), ("em", "gai"), ("em", "trai"), ("anh", "trai"), ("chị", "gái"), ("chi", "gai"),
           ("con", "gái"), ("con", "gai"), ("con", "trai"), ("người", "nhà"), ("nguoi", "nha"), ("đồng", "nghiệp"),
           ("dong", "nghiep"), ("nhỏ", "bạn"), ("nho", "ban"), ("đứa", "bạn"), ("dua", "ban"), ("bạn", "thân"),
           ("ban", "than"), ("người", "quen"), ("nguoi", "quen")}
POSSESSORS = {"chị", "chi", "c", "em", "e", "anh", "a", "mình", "minh", "tôi", "toi", "tui", "tớ", "mk", "cj", "chj"}
# The contact's own number named as such ("sđt chị", "số của em", "zalo mình"), right before the number.
PHONE_HEADS = {"sđt", "sdt", "số", "so", "đt", "dt", "zalo", "thoại", "thoai"}
SELF_FILLER = {"là", "la", "nè", "ne", "nha", "nhé", "nhe", "đây", "day", "mới", "moi", "của", "cua", "em", "e",
               "ạ", "a"}
CONTEXT_MS = 30 * 60_000          # the contact's previous message counts for 30 minutes
OTHER_CONTEXT_MS = 2 * 60 * 60_000  # benefit statements within 2 hours after one about another person's benefit
# A run glued to letters is a phone only after one of these ("sdt0912345678").
PHONE_GLUE_OK = {"sdt", "dt", "zalo", "so", "sđt", "đt", "số"}
MAX_TEXT = 4_000                  # a message is read up to this length
# Words that may sit around a number that is sent alone ("0912345678 nha em", "dạ 0912 345 678 ạ").
ALONE_OK = {"da", "vang", "a", "ah", "nha", "nhe", "nhen", "nghen", "nhes", "day", "ne", "nek", "em", "e", "ad",
            "shop", "oi", "ok", "oke", "okie", "chi", "c", "anh"}

# ---------------------------------------------------------------- rule tables: benefits

# Package keywords. "gói" and "thẻ" as written; their plain spellings (also gội / gọi, thế / thể) count only
# right before a count ("goi 10 buoi"), plain "goi" also before "cua <pronoun>". "combo" and "liệu trình" always.
PACKAGE_MARKED = ("gói", "thẻ")
PACKAGE_ANY = ("combo",)
PACKAGE_TWO = (("liệu", "trình"),)
VOUCHER_WORDS = {"voucher", "vouchers", "vocher", "voucer", "vourcher", "evoucher", "coupon"}
VOUCHER_PHRASES = (("phiếu", "quà", "tặng"), ("thẻ", "quà", "tặng"), ("phiếu", "giảm", "giá"), ("phiếu", "tặng"),
                   ("phiếu", "quà"))
_VOUCHER_FIRST = {ac.fold(p[0]) for p in VOUCHER_PHRASES}
_PACKAGE_MARKED_FOLDED = {ac.fold(p) for p in PACKAGE_MARKED}
UNITS = ("buổi", "lần")
PURCHASE_VERBS = ("mua", "lấy", "chốt", "đk", "làm")          # "làm" only right before the keyword ("làm gói")
PURCHASE_VERBS2 = (("đăng", "ký"), ("đăng", "kí"), ("kích", "hoạt"), ("gia", "hạn"))
PURCHASE_FILLER = {"them", "mot", "cho", "luon", "giup", "gium", "dum", "cai", "nguyen", "tiep", "1"}
GIFT_VERBS = ("tặng", "gửi", "nhận")                   # plain "nhan" (also nhắn) only in "nhan duoc"
NEGATIONS = ("không", "chưa", "chẳng", "chả", "đừng", "hông", "hổng", "khỏi", "chớ")
NEGATIONS_PLAIN = {"khong", "ko", "k", "kg", "kh", "chua", "hong", "hok", "khoi"}
INTENTS = ("muốn", "định", "tính", "nếu", "sẽ", "nên", "cần", "thử", "hỏi", "chắc")
INTENTS_PLAIN = {"muon", "dinh", "tinh", "neu", "se", "nen", "can", "hoi", "chac"}
GENERIC_SUBJECTS = ("bên", "khách", "người", "ai", "mọi")      # the spa side or anyone: an offer, not a purchase
# Pronouns the spa uses for the contact, and pronouns the contact uses for themselves.
OWNER_SIDE = ("chị", "anh", "cô", "chú", "bác", "bạn", "cj", "chj", "c", "a")
CONTACT_SIDE = ("chị", "anh", "em", "mình", "tôi", "tui", "tớ", "cô", "chú", "bác", "cj", "chj", "c", "a", "e", "mk")
TOTAL_STOP = ("còn", "của", "hết", "đã", "thứ", "là", "và", "hoặc", "hay", "với", "giá", "tặng")
NOT_REMAINING_NEXT = ("trống", "chỗ", "suất", "slot")      # "còn 2 buổi trống": free slots, not a package
USED_UP_STOP = {"han", "cho", "slot", "lich", "gio", "tien", "ca", "ngay", "thang", "tuan", "phong", "nguoi",
                "khach", "suc", "luc", "nuoc", "hang", "mau", "size", "sach"}
NUM_WORDS = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9,
             "mười": 10}
NUM_WORDS_PLAIN = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "chin": 9, "muoi": 10}  # nam / sau / bay / tam are words
# Advertising vocabulary in a spa message (plain spellings count too).
AD_PHRASES: tuple[tuple[str, bool], ...] = tuple((p, True) for p in (
    "ưu đãi", "khuyến mãi", "khuyến mại", "km", "ctkm", "chương trình", "áp dụng", "bảng giá", "menu", "quý khách",
    "khách hàng", "giảm giá", "giá chỉ", "chỉ từ", "sale", "hotline", "tri ân", "khai trương", "số lượng có hạn",
    "đăng ký ngay", "duy nhất", "miễn phí", "giá gốc"))
# A package or voucher statement in a clause with an expiry phrase is not read (an expired benefit is not unused,
# and "used up" would be a guess); a voucher in a clause with a spent phrase is not read either.
EXPIRED: tuple[tuple[str, bool], ...] = tuple((p, True) for p in ("hết hạn", "hết hiệu lực", "quá hạn"))
VOUCHER_SPENT: tuple[tuple[str, bool], ...] = tuple((p, True) for p in (
    "đã dùng", "đã sử dụng", "dùng rồi", "sử dụng rồi", "xài rồi", "đã xài"))
PERCENT_RE = re.compile(r"[0-9]\s?%")
VOUCHER_VALUE_RE = re.compile(
    r"^\s*(?:(?:trị giá|giá trị|mệnh giá|tri gia|gia tri|menh gia)\s*)?(?P<giam>(?:giảm|giam)\s*)?"
    r"(?P<num>[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]{1,4})\s*(?P<unit>k|nghìn|ngàn|nghin|ngan|vnđ|vnd|đ|d|tr|triệu|trieu|%)?"
    r"(?![^\W_])")
VALUE_MIN, VALUE_MAX = 10_000, 50_000_000
QUESTION_MARKED = {"không", "chưa", "hả", "nhỉ", "gì", "nào", "mấy", "hông", "hổng", "hem", "hửm", "sao", "à"}
ADDRESS_END = {"em", "e", "chi", "c", "anh", "a", "co", "chu", "bac", "ad", "shop", "admin", "oi", "minh", "ban", "cj",
               "chj", "ac", "spa", "ah"}
CLAUSE_BREAK_CHARS = set(",.!?;:\n\r…()[]{}")
SERVICE_NEAR = 3          # words between a statement and the catalog service that names it

# ---------------------------------------------------------------- spelling helpers

_FOLD: dict[str, str] = {}


def _f(s: str) -> str:
    v = _FOLD.get(s)
    if v is None:
        v = _FOLD[s] = ac.fold(s)
    return v


@dataclass
class _Tok:
    low: str            # lowercased NFC
    bare: str           # diacritics removed
    plain: bool         # written without diacritics
    start: int
    end: int
    after_digit: bool   # letters glued to a number ("k" of "100k")
    clause: int
    num: int | None     # a small count: digits (up to 3) or a number word


_FOLD_SETS: dict[tuple[str, ...], frozenset[str]] = {}


def _sp(t: _Tok, *forms: str) -> bool:
    """t is one of forms as written, or a plain spelling of one of them written without diacritics."""
    if t.low in forms:
        return True
    if not t.plain:
        return False
    folds = _FOLD_SETS.get(forms)
    if folds is None:
        folds = _FOLD_SETS[forms] = frozenset(_f(f) for f in forms)
    return t.bare in folds


class _Phrases:
    """Phrases matched on the folded text; each word must be the phrase's spelling or (when allowed) a plain one."""

    def __init__(self, entries: Iterable[tuple[str, bool]]):
        self.specs: dict[str, list[tuple[list[str], bool]]] = defaultdict(list)
        for phrase, plain_ok in entries:
            self.specs[_f(phrase)].append((phrase.split(), plain_ok))
        self.regex = ac._phrase_re(self.specs)

    def find(self, low: str, bare: str) -> list[tuple[int, int]]:
        out = []
        for m in self.regex.finditer(bare):
            words = low[m.start():m.end()].split()
            for spec, plain_ok in self.specs[m.group(0)]:
                if len(spec) == len(words) and all(
                        w == s or (plain_ok and not ac.has_marks(w)) for w, s in zip(words, spec)):
                    out.append((m.start(), m.end()))
                    break
        return out


_PHONE_CUES = _Phrases(PHONE_CUES)
_REJECT_CUES = _Phrases(REJECT_CUES + THIRD_PARTY_CUES)
_AD = _Phrases(AD_PHRASES)
_EXPIRED = _Phrases(EXPIRED)
_SPENT = _Phrases(VOUCHER_SPENT)


def _text_msgs(msgs: Iterable[Any]) -> list[tuple[int, int, bool, str]]:
    """(ts, input order, from_owner, text) for text messages, sorted by time."""
    out = []
    for k, m in enumerate(msgs or ()):
        text = getattr(m, "text", None)
        ts = getattr(m, "ts", None)
        if not isinstance(text, str) or not text.strip() or getattr(m, "type", "text") not in ac.TEXT_TYPES:
            continue
        if not isinstance(ts, int) or isinstance(ts, bool):
            continue
        out.append((ts, k, bool(getattr(m, "from_owner", False)), text[:MAX_TEXT]))
    out.sort(key=lambda r: (r[0], r[1]))
    return out


# ---------------------------------------------------------------- phone


def normalize_phone(raw: str) -> str | None:
    """Digits only, +84 / 84 / 0084 prefix -> 0; a Vietnamese mobile number "0[35789]xxxxxxxx" or None."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or not PHONE_INPUT_RE.match(s):
        return None
    plus = s.lstrip("(").startswith("+")
    digits = re.sub(r"[^0-9]", "", s)
    if plus and not digits.startswith("84"):
        return None
    if digits.startswith("0084") and len(digits) == 13:
        digits = digits[2:]
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    elif plus and digits.startswith("840") and len(digits) == 12:
        digits = digits[2:]
    return digits if PHONE_VALID_RE.match(digits) else None


def _prep_phone_text(text: str) -> str:
    low = ac.nfc_lower(text)
    low = URL_EMAIL_RE.sub(lambda m: " " * len(m.group(0)), low)
    return PAREN_84_RE.sub(lambda m: m.group(1).rjust(len(m.group(0))), low)


def _numbers(low: str) -> list[tuple[int, int, str]]:
    """(start, end, normalised number) of every phone-shaped number in low (already prepared)."""
    groups = [(m.start(), m.end(), m.group(0)) for m in DIGITS_RE.finditer(low)]
    runs: list[list[tuple[int, int, str]]] = []
    for g in groups:
        if runs and PHONE_SEP_RE.match(low[runs[-1][-1][1]:g[0]]):
            runs[-1].append(g)
        else:
            runs.append([g])
    out = []
    for run in runs:
        first, last = run[0][0], run[-1][1]
        plus = first > 0 and low[first - 1] == "+"
        lead = low[first - 1 - (1 if plus else 0)] if first - (1 if plus else 0) > 0 else ""
        if lead.isalpha():
            m = re.search(r"[^\W\d_]+$", low[:first - (1 if plus else 0)])
            if not m or m.group(0) not in PHONE_GLUE_OK:
                continue
        if last < len(low) and low[last].isalpha():
            continue
        found: list[tuple[int, int, str]] = []
        i = 0
        while i < len(run):
            acc, hit = "", None
            for j in range(i, len(run)):
                acc += run[j][2]
                if len(acc) > 13:
                    break
                v = normalize_phone(("+" if plus and i == 0 else "") + acc)
                if v:
                    hit = (j, v)
                    break
            if hit is None:
                found = []          # unexplained digits: none of the run is a phone number
                break
            j, v = hit
            found.append((run[i][0] - (1 if plus and i == 0 else 0), run[j][1], v))
            i = j + 1
        out.extend(found)
    return out


def _phone_cues(low: str) -> list[tuple[int, int, str]]:
    bare = ac.fold(low)
    rejects = [(s, e, "reject") for s, e in _REJECT_CUES.find(low, bare)]
    phones = [(s, e, "phone") for s, e in _PHONE_CUES.find(low, bare)
              if not any(s < re_ and rs < e for rs, re_, _k in rejects)]
    return sorted(rejects + phones)


def _alone(low: str, spans: list[tuple[int, int, str]]) -> bool:
    chars = list(low)
    for s, e, _v in spans:
        chars[s:e] = " " * (e - s)
    rest = ac.fold("".join(chars))
    return all(w in ALONE_OK for w in ac.TOKEN_RE.findall(rest))


def _phone_confidence(low: str, num: tuple[int, int, str], cues: list[tuple[int, int, str]],
                      nums: list[tuple[int, int, str]]) -> str | None:
    s, e, _v = num
    if s > 0 and low[s - 1].isalpha():
        return "high"                   # "sdt0912345678": _numbers keeps a glued run only after a phone cue
    before = [c for c in cues if c[1] <= s and s - c[1] <= CUE_BEFORE_MAX]
    after = [c for c in cues if c[0] >= e and c[0] - e <= CUE_AFTER_MAX]
    if before:
        kind = max(before, key=lambda c: c[1])[2]
    elif after:
        kind = min(after, key=lambda c: c[0])[2]
    elif any(c[2] == "reject" for c in cues):
        kind = "reject"
    elif cues:
        kind = "phone"
    else:
        return "high" if _alone(low, nums) else "medium"
    return "high" if kind == "phone" else None


def _kin_spans(low: str) -> list[tuple[int, int]]:
    """Character spans of another person named with a possessive pronoun: "mẹ chị", "bạn của c", "em gái chị",
    "ck c"; a two-word kin phrase ("em gái", "người nhà") also without the pronoun."""
    toks = list(ac.TOKEN_RE.finditer(low))
    words = [t.group(0) for t in toks]
    out = []
    n = len(words)
    for i in range(n):
        end = None
        if i + 1 < n and (words[i], words[i + 1]) in KIN_TWO:
            end = i + 1
            j = i + 2
            if j < n and words[j] in ("của", "cua"):
                j += 1
            if j < n and words[j] in POSSESSORS:
                end = j
        elif words[i] in KIN_ONE:
            j = i + 1
            if j < n and words[j] in ("của", "cua"):
                j += 1
            if j < n and words[j] in POSSESSORS:
                end = j
        if end is not None:
            out.append((toks[i].start(), toks[end].end()))
    return out


def _self_cue(low: str, start: int) -> bool:
    """The number at `start` is named as the contact's own: a phone head, an optional "của" and a pronoun right
    before it ("sđt chị 09…", "số của em là 09…", "số điện thoại chị: 09…")."""
    words = ac.TOKEN_RE.findall(low[:start])[-6:]
    k = len(words) - 1
    while k >= 0 and words[k] in SELF_FILLER and words[k] not in POSSESSORS:
        k -= 1
    if k < 0 or words[k] not in POSSESSORS:
        return False
    k -= 1
    if k >= 0 and words[k] in ("của", "cua"):
        k -= 1
    return k >= 0 and words[k] in PHONE_HEADS


def extract_phone(msgs) -> dict | None:
    """The contact's phone number from their own messages: {"value", "confidence", "source": "chat", "at"}."""
    rows = _text_msgs(msgs)
    first_owner: dict[str, int] = {}
    first_contact: dict[str, int] = {}
    parsed = []
    prev_kin_ts: int | None = None          # the contact's latest message naming another person
    for ts, _k, owner, text in rows:
        low = _prep_phone_text(text)
        nums = _numbers(low)
        seen = first_owner if owner else first_contact
        for _s, _e, v in nums:
            seen.setdefault(v, ts)
        if owner:
            continue
        kin = bool(_kin_spans(low))
        if nums:
            context = prev_kin_ts is not None and ts - prev_kin_ts <= CONTEXT_MS
            parsed.append((ts, low, nums, kin or context))
        if kin:
            prev_kin_ts = ts
    best: dict[str, tuple[int, str]] = {}
    for ts, low, nums, other_person in parsed:
        cues = _phone_cues(low)
        for num in nums:
            v = num[2]
            if v in first_owner and first_owner[v] <= first_contact.get(v, ts):
                continue                    # the spa wrote it first: the spa's own or someone else's number
            if other_person and not _self_cue(low, num[0]):
                continue                    # maybe the number of the person named ("sdt mẹ chị 09…")
            conf = _phone_confidence(low, num, cues, nums)
            if conf is None:
                continue
            prev = best.get(conf)
            if prev is None or ts >= prev[0]:
                best[conf] = (ts, v)
            break                           # one number per message: the first accepted
    for conf in ("high", "medium"):
        if conf in best:
            ts, v = best[conf]
            return {"value": v, "confidence": conf, "source": "chat", "at": ts}
    return None


# ---------------------------------------------------------------- benefits: parsing one message

_WORD_RE = re.compile(r"[0-9]+|[^\W\d_]+")


def _small_int(w: str) -> int | None:
    """An ASCII number of 1-3 digits ("²" passes str.isdigit() but is not one)."""
    return int(w) if w.isascii() and w.isdigit() and len(w) <= 3 else None


def _num_of(w: str, plain: bool) -> int | None:
    if w.isascii() and w.isdigit():
        return int(w) if len(w) <= 3 else None
    if w in NUM_WORDS:
        return NUM_WORDS[w]
    if plain and w in NUM_WORDS_PLAIN:
        return NUM_WORDS_PLAIN[w]
    return None


def _tokens(low: str, bare: str) -> list[_Tok]:
    toks: list[_Tok] = []
    clause = 0
    for m in _WORD_RE.finditer(low):
        s, e = m.span()
        w = low[s:e]
        after_digit = False
        if toks:
            prev = toks[-1]
            gap = low[prev.end:s]
            grouped = prev.low.isdigit() and w.isdigit() and gap in (".", ",")
            if not grouped and any(ch in CLAUSE_BREAK_CHARS or unicodedata.category(ch) == "So" for ch in gap):
                clause += 1
            after_digit = gap == "" and prev.low.isdigit() and not w.isdigit()
        b = bare[s:e]
        plain = b == w          # same as not has_marks(w): w is lowercased and fold only strips marks
        toks.append(_Tok(w, b, plain, s, e, after_digit, clause, _num_of(w, plain)))
    return toks


@dataclass
class _Mention:
    start: int
    kw_end: int
    end: int
    total: int | None
    clause: int
    possessed: bool = False
    purchase: bool = False
    completed: bool = False
    new_hint: bool = False


@dataclass
class _Fact:                  # remaining (value >= 0) stated next to "còn" / "hết"
    start: int
    end: int
    value: int
    clause: int
    pron: bool


@dataclass
class _Ordinal:
    start: int
    end: int
    n: int
    m: int | None
    clause: int
    plain: bool


@dataclass
class _Voucher:
    start: int
    end: int
    clause: int
    total: int | None
    value: int | None
    pct: int | None
    ok: bool


@dataclass
class _Hit:
    start: int
    end: int
    key: str
    service_id: str | None
    name: str


class _Msg:
    """One message parsed for package and voucher vocabulary."""

    def __init__(self, text: str, owner: bool):
        self.owner = owner
        self.low = ac.nfc_lower(text)
        self.bare = ac.fold(self.low)
        self.toks = _tokens(self.low, self.bare)
        self.n = len(self.toks)
        self.question = self._questions()
        self.expired = self._clauses_with(_EXPIRED)
        self.voucher_kw = self._voucher_keywords()
        covered = {k for s, e in self.voucher_kw for k in range(s, e)}
        self.mentions = [m for m in (self._mention(i) for i in range(self.n) if i not in covered) if m]
        self.facts = self._remaining() + self._used_up()
        self.ordinals = self._ordinals()
        self.vouchers = self._vouchers()
        self.asks = self._asks_count()
        self.others = self._other_person_clauses()

    # -- small helpers

    def _other_person_clauses(self) -> set[int]:
        """Clauses about another person's benefit: a person named with a possessive ("cho mẹ chị", "bạn c"), or a
        gift passed on ("tặng bạn", from the contact; "chị tặng ..." in a spa message: the contact gives it on)."""
        out: set[int] = set()
        for s, e in _kin_spans(self.low):
            out |= {t.clause for t in self.toks if t.start >= s and t.end <= e}
        for i, t in enumerate(self.toks):
            if not (t.low == "tặng" or (t.plain and t.bare == "tang")):
                continue
            nxt = self.toks[i + 1] if self.same(i, i + 1) else None
            if not self.owner and nxt is not None and (nxt.low in KIN_ONE or nxt.bare in ("ai", "nguoi")):
                out.add(t.clause)                        # "mua voucher tặng bạn", "để tặng người khác"
            if self.owner and i > 0 and self.same(i - 1, i) and _sp(self.toks[i - 1], *OWNER_SIDE) and \
                    self.toks[i - 1].bare not in ("ban",):
                out.add(t.clause)                        # "để chị tặng bạn": the contact gives it on
        return out

    def same(self, i: int, j: int) -> bool:
        return 0 <= i < self.n and 0 <= j < self.n and self.toks[i].clause == self.toks[j].clause

    def side(self, t: _Tok) -> bool:
        return _sp(t, *(OWNER_SIDE if self.owner else CONTACT_SIDE))

    def any_pron(self, t: _Tok) -> bool:
        return _sp(t, *OWNER_SIDE, *CONTACT_SIDE)

    @staticmethod
    def neg(t: _Tok) -> bool:
        return t.low in NEGATIONS or (t.plain and t.bare in NEGATIONS_PLAIN)

    @staticmethod
    def intent(t: _Tok) -> bool:
        return t.low in INTENTS or (t.plain and t.bare in INTENTS_PLAIN)

    def count_at(self, k: int) -> tuple[int, int] | None:
        """(number, index after the unit) for "N buổi" / "N lần" starting at token k."""
        if not self.same(k, k + 1):
            return None
        a, b = self.toks[k], self.toks[k + 1]
        if a.num is None or not _sp(b, *UNITS) or self.low[a.end:b.start].strip():
            return None
        if k > 0 and self.toks[k - 1].low.isdigit() and self.low[self.toks[k - 1].end:a.start] in (".", ",", "/"):
            return None
        return a.num, k + 2

    def pron_before(self, i: int, span: int = 3) -> bool:
        return any(self.same(k, i) and self.side(self.toks[k]) for k in range(max(0, i - span), i))

    def possessive_after(self, start: int, limit: int) -> bool:
        for k in range(start, min(self.n - 1, start + limit)):
            if not self.same(k, start):
                break
            if _sp(self.toks[k], "của") and self.same(k, k + 1) and self.side(self.toks[k + 1]):
                return True
        return False

    def holder_before(self, i: int, verbs: tuple[str, ...]) -> bool:
        """"chị (đang|vẫn) có <keyword>" with a pronoun of the contact."""
        k = i - 1
        if k < 0 or not self.same(k, i) or not _sp(self.toks[k], *verbs):
            return False
        k -= 1
        if k >= 0 and _sp(self.toks[k], "đang", "vẫn"):
            k -= 1
        return k >= 0 and self.same(k, i) and self.side(self.toks[k])

    def skip(self, clause: int) -> bool:
        """No statement is read from a question, from a clause about an expired benefit, or from a clause about
        another person's benefit."""
        return self.question.get(clause, False) or clause in self.expired or clause in self.others

    def _clauses_with(self, phrases: _Phrases) -> set[int]:
        spans = phrases.find(self.low, self.bare)
        if not spans:
            return set()
        return {t.clause for t in self.toks for a, b in spans if t.start >= a and t.end <= b}

    # -- clause questions

    def _questions(self) -> dict[int, bool]:
        by: dict[int, list[int]] = defaultdict(list)
        for i, t in enumerate(self.toks):
            by[t.clause].append(i)
        out: dict[int, bool] = {}
        for c, idxs in by.items():
            last = self.toks[idxs[-1]]
            nxt = self.toks[idxs[-1] + 1].start if idxs[-1] + 1 < self.n else len(self.low)
            words = [self.toks[i] for i in idxs]
            if "?" in self.low[last.end:nxt] or any(
                    w.bare == "bn" or (w.bare == "bao" and k + 1 < len(words) and words[k + 1].bare == "nhieu")
                    for k, w in enumerate(words)):
                out[c] = True
                continue
            res = False
            for k in range(len(words) - 1, -1, -1):
                w = words[k]
                if w.after_digit:
                    break
                if w.low in QUESTION_MARKED or (w.plain and w.bare in ac.QUESTION_END):
                    # "không còn buổi nào", "không có gì": a negated statement, not a question
                    res = not (w.bare in ("nao", "gi") and any(self.neg(x) for x in words[:k]))
                    break
                if w.bare in ac.END_PARTICLES or w.bare in ADDRESS_END:
                    continue
                break
            out[c] = res
        return out

    # -- keywords

    def _voucher_keywords(self) -> list[tuple[int, int]]:
        out = []
        i = 0
        while i < self.n:
            t = self.toks[i]
            end = i + 1 if t.bare in VOUCHER_WORDS else None
            if end is None and t.bare in _VOUCHER_FIRST:
                for ph in VOUCHER_PHRASES:
                    k = len(ph)
                    if i + k <= self.n and self.same(i, i + k - 1) and all(
                            _sp(self.toks[i + q], ph[q]) for q in range(k)):
                        end = i + k
                        break
            if end is not None:
                out.append((i, end))
                i = end
            else:
                i += 1
        return out

    def keyword_at(self, i: int) -> int | None:
        """Index after a package keyword starting at token i, else None."""
        if i >= self.n:
            return None
        t = self.toks[i]
        if t.low in PACKAGE_MARKED or t.bare in PACKAGE_ANY:
            return i + 1
        if t.plain and t.bare in _PACKAGE_MARKED_FOLDED:
            if self.count_at(i + 1) and self.same(i, i + 1):
                return i + 1
            if t.bare == "goi" and self.same(i, i + 2) and _sp(self.toks[i + 1], "của") and self.side(self.toks[i + 2]):
                return i + 1
            return None
        for a, b in PACKAGE_TWO:
            if self.same(i, i + 1) and _sp(t, a) and _sp(self.toks[i + 1], b):
                return i + 2
        return None

    def _mention(self, i: int) -> _Mention | None:
        kw_end = self.keyword_at(i)
        if kw_end is None:
            return None
        t = self.toks[i]
        immediate = t.plain and t.bare in _PACKAGE_MARKED_FOLDED
        total, end = None, kw_end
        for k in range(kw_end, min(self.n, kw_end + 7)):
            if not self.same(k, i) or (immediate and k > kw_end):
                break
            cnt = self.count_at(k)
            if cnt:
                total, end = (cnt[0] if 2 <= cnt[0] <= MAX_COUNT else None), cnt[1]
                break
            if _sp(self.toks[k], *TOTAL_STOP) or self.keyword_at(k):
                break
        m = _Mention(i, kw_end, end, total, t.clause)
        m.possessed = self.possessive_after(kw_end, 8) or (self.owner and self.holder_before(i, ("có",)))
        self._purchase(m)
        return m

    def _verb_start(self, j: int) -> int | None:
        if j >= 1 and self.same(j - 1, j):
            for a, b in PURCHASE_VERBS2:
                if _sp(self.toks[j - 1], a) and _sp(self.toks[j], b):
                    return j - 1
        if _sp(self.toks[j], *PURCHASE_VERBS):
            return j
        return None

    def _purchase(self, m: _Mention) -> None:
        i, c = m.start, m.clause
        j, skipped, vs = i - 1, [], None
        while j >= 0 and self.toks[j].clause == c and len(skipped) <= 4:
            v = self._verb_start(j)
            if v is not None:
                if _sp(self.toks[v], "làm") and skipped:
                    return
                vs = v
                break
            t = self.toks[j]
            if t.bare in PURCHASE_FILLER or self.any_pron(t):
                skipped.append(j)
                j -= 1
                continue
            return
        if vs is None:
            return
        before = [self.toks[k] for k in range(max(0, vs - 3), vs) if self.toks[k].clause == c]
        if any(self.neg(t) for t in before[-2:]) or any(self.intent(t) for t in before):
            return
        generic = GENERIC_SUBJECTS if not self.owner else tuple(w for w in GENERIC_SUBJECTS if w != "bên")
        if any(_sp(t, *generic) for t in before):
            return              # the contact's "bên em mua gói ... tặng ...", "khách mua gói": an offer
        if any(_sp(self.toks[k], "nếu") for k in range(vs) if self.toks[k].clause == c):
            return
        after = [self.toks[k] for k in range(m.end, min(self.n, m.end + 3)) if self.toks[k].clause == c]
        m.purchase = True
        m.new_hint = any(_sp(self.toks[k], "thêm") for k in skipped) or any(
            t.low in ("nữa", "mới") or (t.plain and t.bare == "nua") for t in after[:1])
        cho_pron = any(_sp(self.toks[k], "cho") and self.same(k, k + 1) and self.toks[k].clause == c
                       and _sp(self.toks[k + 1], *OWNER_SIDE)
                       for k in list(skipped) + list(range(m.end, min(self.n, m.end + 2))))
        m.completed = (any(t.low == "đã" for t in before)
                       or any(_sp(self.toks[k], "rồi") for k in range(vs + 1, self.n) if self.toks[k].clause == c)
                       or cho_pron)

    # -- remaining, used up, ordinal

    def _remaining(self) -> list[_Fact]:
        out = []
        for i, t in enumerate(self.toks):
            if not _sp(t, "còn"):
                continue
            j = i + 1
            if self.same(i, j) and _sp(self.toks[j], "lại", "dư"):
                j += 1
            negated = i > 0 and self.same(i - 1, i) and self.neg(self.toks[i - 1])
            cnt = self.count_at(j)
            if cnt and not negated:
                v, e = cnt
                if v > MAX_COUNT:
                    continue
                if e < self.n and self.same(i, e):
                    nx = self.toks[e]
                    if _sp(nx, *NOT_REMAINING_NEXT):
                        continue
                    if nx.bare == "trong" and nx.plain and self.keyword_at(e + 1) is None:
                        continue    # "còn 3 buổi trong tuần": slots; "còn 3 buổi trong gói" stays
                out.append(_Fact(i, e, v, t.clause, self.pron_before(i)))
            elif (negated and self.same(i, j + 1) and _sp(self.toks[j], "buổi")
                  and _sp(self.toks[j + 1], "nào")):
                out.append(_Fact(i, j + 2, 0, t.clause, self.pron_before(i - 1)))     # "không còn buổi nào"
        return out

    def _used_up(self) -> list[_Fact]:
        out = []
        for i, t in enumerate(self.toks):
            if not _sp(t, "hết"):
                continue
            c = t.clause
            if i > 0 and self.same(i - 1, i) and self.neg(self.toks[i - 1]):
                continue
            nx = self.toks[i + 1] if self.same(i, i + 1) else None
            if nx is not None and (nx.bare in USED_UP_STOP or nx.num is not None or nx.low.isdigit()):
                continue
            kw_before = any(self.keyword_at(k) for k in range(0, i) if self.toks[k].clause == c)
            kw_after = nx is not None and self.keyword_at(i + 1) is not None
            if kw_before or kw_after or (nx is not None and _sp(nx, "buổi")):
                out.append(_Fact(i, i + 1, 0, c, self.pron_before(i, 5)))
        return out

    def _ordinals(self) -> list[_Ordinal]:
        out = []
        for i in range(self.n - 2):
            t, th, nt = self.toks[i], self.toks[i + 1], self.toks[i + 2]
            if not _sp(t, *UNITS) or not self.same(i, i + 2):
                continue
            if th.low == "thứ":
                plain = False
            elif th.plain and th.bare == "thu":
                plain = True
            else:
                continue
            if not (nt.low.isascii() and nt.low.isdigit() and len(nt.low) <= 3):
                continue
            n_, m_, end = int(nt.low), None, i + 3
            if i + 3 < self.n and _small_int(self.toks[i + 3].low) is not None and re.fullmatch(
                    r"\s*/\s*", self.low[nt.end:self.toks[i + 3].start]):
                m_, end = _small_int(self.toks[i + 3].low), i + 4
            elif i + 4 < self.n and self.same(i, i + 4) and _sp(self.toks[i + 3], "trên") and \
                    _small_int(self.toks[i + 4].low) is not None:
                m_, end = _small_int(self.toks[i + 4].low), i + 5
            out.append(_Ordinal(i, end, n_, m_, t.clause, plain))
        return out

    # -- vouchers

    def got_before(self, k: int) -> bool:
        """"được" / "đc" right before token k ("chị được tặng")."""
        return k > 0 and self.same(k - 1, k) and _sp(self.toks[k - 1], "được", "đc", "dc")

    def _gift_at(self, k: int) -> bool:
        t = self.toks[k]
        if t.low in GIFT_VERBS or (t.plain and t.bare in ("tang", "gui")):
            return True
        return t.plain and t.bare == "nhan" and self.same(k, k + 1) and _sp(self.toks[k + 1], "được")

    def _voucher_value(self, end_char: int) -> tuple[int | None, int | None]:
        m = VOUCHER_VALUE_RE.match(self.low[end_char:end_char + 32])
        if not m:
            return None, None
        num, unit = m.group("num"), m.group("unit")
        if unit == "%":
            v = int(num) if num.isdigit() else 0
            return (None, v) if 1 <= v <= 100 else (None, None)
        grouped = not num.isdigit()
        base = int(re.sub(r"[.,]", "", num))
        if unit in ("k", "nghìn", "ngàn", "nghin", "ngan"):
            value = base * 1000 if not grouped else None
        elif unit in ("tr", "triệu", "trieu"):
            value = base * 1_000_000 if not grouped else None
        elif unit in ("vnđ", "vnd", "đ", "d") or grouped:
            value = base
        else:
            value = None
        if value is None or not VALUE_MIN <= value <= VALUE_MAX:
            return None, None
        return value, None

    def _vouchers(self) -> list[_Voucher]:
        out = []
        spent = self._clauses_with(_SPENT)
        for s, e in self.voucher_kw:
            c = self.toks[s].clause
            if c in spent:
                continue
            gift = next((k for k in range(s - 1, max(-1, s - 5), -1) if self.toks[k].clause == c and self._gift_at(k)),
                        None)
            if gift is not None and any(self.neg(self.toks[k]) for k in range(max(0, gift - 2), gift)
                                        if self.toks[k].clause == c):
                gift = None
            pron_between = gift is not None and any(self.side(self.toks[k]) for k in range(gift + 1, s))
            pron_after = any(_sp(self.toks[k], "cho") and self.same(k, k + 1) and self.side(self.toks[k + 1])
                             for k in range(e, min(self.n, e + 4)) if self.toks[k].clause == c)
            held = self.possessive_after(e, 8) or self.holder_before(s, ("có", "còn"))
            # the contact: "chị được tặng voucher", "em tặng chị voucher"; the spa: addressed to the contact
            passive = not self.owner and gift is not None and self.got_before(gift)
            ok = held or (gift is not None and (pron_between or pron_after or passive))
            total, span_end = None, e
            for k in range(e, min(self.n, e + 4)):
                if self.toks[k].clause != c or _sp(self.toks[k], "còn"):
                    break
                cnt = self.count_at(k)
                if cnt:
                    total = cnt[0] if 1 <= cnt[0] <= MAX_COUNT else None
                    span_end = cnt[1]
                    break
            value, pct = self._voucher_value(self.toks[e - 1].end) if total is None else (None, None)
            out.append(_Voucher(gift if gift is not None else s, span_end, c, total, value, pct, ok))
        # "tặng chị 1 buổi" without the word voucher
        for i, t in enumerate(self.toks):
            if not (t.low == "tặng" or (t.plain and t.bare == "tang")) or t.clause in spent:
                continue
            j, skipped = i + 1, []
            while j < self.n and self.same(i, j) and len(skipped) < 3 and self.count_at(j) is None:
                if self.toks[j].bare in ("them", "cho") or self.any_pron(self.toks[j]):
                    skipped.append(j)
                    j += 1
                    continue
                break
            cnt = self.count_at(j) if self.same(i, j) else None
            if not cnt or any(s < cnt[1] and e > i for s, e in self.voucher_kw):
                continue
            if any(self.neg(self.toks[k]) for k in range(max(0, i - 2), i) if self.same(k, i)):
                continue
            ok = any(self.side(self.toks[k]) for k in skipped) or (not self.owner and self.got_before(i))
            total = cnt[0] if 1 <= cnt[0] <= MAX_COUNT else None
            out.append(_Voucher(i, cnt[1], t.clause, total, None, None, ok and total is not None))
        return out

    def _asks_count(self) -> bool:
        for i in range(self.n - 1):
            t = self.toks[i]
            k = i + 1 if t.bare == "bao" and self.same(i, i + 1) and self.toks[i + 1].bare == "nhieu" else i
            if (_sp(t, "mấy") or t.bare in ("bao", "bn")) and self.same(k, k + 1) and _sp(self.toks[k + 1], *UNITS):
                return True
        return False

    # -- summary

    def vocabulary(self) -> bool:
        return bool(self.mentions or self.voucher_kw or self.vouchers or self.facts or self.ordinals or self.asks)

    def advertising(self) -> bool:
        if not self.owner:
            return False
        if _AD.find(self.low, self.bare) or PERCENT_RE.search(self.low):
            return True
        if self.mentions and ac.PRICE_RE.search(self.low):
            return True
        return len({m.total for m in self.mentions if m.total}) >= 2

    def catalog_hits(self, catalog: Any) -> list[_Hit]:
        if catalog is None or not getattr(catalog, "regex", None):
            return []
        out = []
        for pos, key, sid, name, _group in catalog.find(self.bare):
            m = catalog.regex.match(self.bare, pos)
            if not m:
                continue
            idx = [k for k, t in enumerate(self.toks) if t.start >= pos and t.end <= m.end()]
            if not idx:
                continue
            name_words = ac.TOKEN_RE.findall(ac.nfc_lower(name))
            clash = False
            for k in idx:
                t = self.toks[k]
                if t.plain:
                    continue
                same_fold = {w for w in name_words if _f(w) == t.bare}
                if same_fold and t.low not in same_fold:
                    clash = True        # "gói đầu" is not the category "gội đầu"
                    break
            if not clash and len({self.toks[k].clause for k in idx}) == 1:
                out.append(_Hit(idx[0], idx[-1] + 1, key, sid, name))
        return out


# ---------------------------------------------------------------- benefits: statements and merge


@dataclass
class _Stmt:
    kind: str
    total: int | None
    remaining: int | None
    svc: _Hit | None
    value: int | None
    pct: int | None
    owner: bool
    ts: int
    seq: int
    purchase: bool = False
    new_hint: bool = False
    expire: bool = False          # "gói của chị hết hạn rồi": the latest benefit of this kind is no longer unused


@dataclass
class _Benefit:
    kind: str
    total: int | None
    remaining: int | None
    svc: _Hit | None
    value: int | None
    pct: int | None
    owner: bool
    ts: int
    seq: int


def _near(pm: _Msg, hits: list[_Hit], start: int, end: int, clauses: set[int]) -> _Hit | None:
    best, best_key = None, None
    for h in hits:
        if pm.toks[h.start].clause not in clauses:
            continue
        if h.start < end and h.end > start:
            d = 0
        elif h.start >= end:
            d = h.start - end
        else:
            d = start - h.end
        if d > SERVICE_NEAR:
            continue
        key = (d, 0 if h.start >= start else 1)
        if best_key is None or key < best_key:
            best, best_key = h, key
    return best


def _statements(pm: _Msg, catalog: Any, ts: int, seq0: int, context: bool) -> list[_Stmt]:
    hits = pm.catalog_hits(catalog)
    ad = pm.advertising()
    out: list[tuple[int, _Stmt]] = []
    used: set[int] = set()

    def stmt(kind, total, remaining, svc, value=None, pct=None, purchase=False, new_hint=False) -> _Stmt:
        return _Stmt(kind, total, remaining, svc, value, pct, pm.owner, ts, 0, purchase, new_hint)

    has_voucher_word = bool(pm.voucher_kw)
    for f in pm.facts:
        if pm.skip(f.clause):
            continue
        before = [k for k, m in enumerate(pm.mentions) if m.start <= f.start]
        after = [k for k, m in enumerate(pm.mentions) if m.start > f.start and m.clause == f.clause]
        mk = before[-1] if before else (after[0] if after else None)
        if mk is not None:
            m = pm.mentions[mk]
            if pm.skip(m.clause) or (ad and not (m.possessed or f.pron)):
                continue
            used.add(mk)
            svc = _near(pm, hits, min(m.start, f.start), max(m.end, f.end), {m.clause, f.clause})
            out.append((f.start, stmt("package", m.total, f.value, svc, purchase=m.purchase and (
                m.completed or not pm.owner), new_hint=m.new_hint)))
        else:
            if has_voucher_word or (ad and not f.pron) or not (f.pron or context):
                continue
            out.append((f.start, stmt("package", None, f.value, _near(pm, hits, f.start, f.end, {f.clause}))))
    for o in pm.ordinals:
        if pm.skip(o.clause):
            continue
        totals = {m.total for m in pm.mentions if m.total}
        if o.plain and not (pm.mentions or (o.m is not None and (o.m > 12 or o.n > 31))):
            continue
        total = o.m if o.m is not None else (next(iter(totals)) if len(totals) == 1 else None)
        if total is None or not (1 <= o.n <= total and 2 <= total <= MAX_COUNT):
            continue
        for k, m in enumerate(pm.mentions):
            if m.total in (None, total):
                used.add(k)
        out.append((o.start, stmt("package", total, total - o.n, _near(pm, hits, o.start, o.end, {o.clause}))))
    for k, m in enumerate(pm.mentions):
        if k in used or m.total is None or pm.skip(m.clause):
            continue
        bought = m.purchase and (m.completed or not pm.owner)
        if bought or m.possessed:
            svc = _near(pm, hits, m.start, m.end, {m.clause})
            out.append((m.start, stmt("package", m.total, None, svc, purchase=bought, new_hint=m.new_hint)))
    for v in pm.vouchers:
        if not v.ok or pm.skip(v.clause):
            continue
        svc = _near(pm, hits, v.start, v.end, {v.clause})
        out.append((v.start, stmt("voucher", v.total, None, svc, v.value, v.pct)))
    for c in sorted(pm.expired):
        if pm.question.get(c, False) or c in pm.others:
            continue
        kw = [s for s, _e in pm.voucher_kw if pm.toks[s].clause == c]
        mk = [m for m in pm.mentions if m.clause == c]
        if not kw and not mk:
            continue
        personal = not pm.owner or any(m.possessed for m in mk) or any(
            pm.side(t) for t in pm.toks if t.clause == c) or not ad
        if not personal:
            continue
        start = kw[0] if kw else mk[0].start
        st = stmt("voucher" if kw else "package", None, None, None)
        st.expire = True
        out.append((start, st))
    out.sort(key=lambda r: r[0])
    res = []
    for q, (_pos, st) in enumerate(out):
        st.seq = seq0 + q
        res.append(st)
    return res


def _svc_key(x: _Hit | None) -> str | None:
    return x.key if x else None


def _compatible(b: _Benefit, st: _Stmt) -> bool:
    if b.kind != st.kind:
        return False
    if st.svc and b.svc and st.svc.key != b.svc.key:
        return False
    if st.total is not None and b.total is not None and st.total != b.total:
        return False
    if st.remaining is not None and b.total is not None and st.remaining > b.total:
        return False
    if st.total is not None and b.remaining is not None and b.remaining > st.total:
        return False
    for a, c in ((st.value, b.value), (st.pct, b.pct)):
        if a is not None and c is not None and a != c:
            return False
    return True


def _merge(stmts: list[_Stmt]) -> list[_Benefit]:
    benefits: list[_Benefit] = []
    for st in stmts:
        if st.expire:
            same = [b for b in benefits if b.kind == st.kind]
            if same:
                benefits.remove(max(same, key=lambda b: (b.ts, b.seq)))
            continue
        cands = [b for b in benefits if _compatible(b, st)]
        target = None
        if cands:
            exact = [b for b in cands if b.total == st.total and _svc_key(b.svc) == _svc_key(st.svc)]
            target = max(exact or cands, key=lambda b: (b.ts, b.seq))
            if st.purchase and (st.new_hint or target.remaining == 0):
                target = None
        if target is None:
            if st.kind == "package" and st.total is None and not st.remaining:
                continue        # "hết" / "còn 0" with nothing to update, or nothing stated at all
            benefits.append(_Benefit(st.kind, st.total, st.remaining, st.svc, st.value, st.pct, st.owner, st.ts,
                                     st.seq))
            continue
        target.total = st.total if st.total is not None else target.total
        target.remaining = st.remaining if st.remaining is not None else target.remaining
        target.svc = st.svc or target.svc
        target.value = st.value if st.value is not None else target.value
        target.pct = st.pct if st.pct is not None else target.pct
        target.owner, target.ts, target.seq = st.owner, st.ts, st.seq
    return benefits


def _title(b: _Benefit) -> str:
    if b.kind == "package":
        title = "Gói" + (f" {b.total} buổi" if b.total else "")
    elif b.total:
        title = f"Voucher {b.total} buổi"
    elif b.value:
        title = "Voucher " + f"{b.value:,}".replace(",", ".") + "đ"
    elif b.pct:
        title = f"Voucher giảm {b.pct}%"
    else:
        title = "Voucher"
    if b.svc and b.svc.name:
        name = b.svc.name.strip()
        title += " – " + name[:1].upper() + name[1:]
    return title[:TITLE_MAX]


def extract_benefits(msgs, catalog) -> list[dict]:
    """Packages and vouchers the contact holds, from statements in the chat (15.4); at most 5, oldest first."""
    rows = _text_msgs(msgs)
    parsed = [(ts, _Msg(text, owner)) for ts, _k, owner, text in rows]
    stmts: list[_Stmt] = []
    seq = 0
    last_vocab: int | None = None      # time of the latest earlier message with package vocabulary
    last_other: int | None = None      # time of the latest message about a benefit for another person
    for ts, pm in parsed:
        context = last_vocab is not None and last_vocab >= ts - DAY_MS
        new = _statements(pm, catalog, ts, seq, context)
        if last_other is not None and ts - last_other <= OTHER_CONTEXT_MS:
            new = [st for st in new if st.expire]   # the spa answering "mua voucher tặng bạn c": the friend's
        seq += len(new) + 1
        stmts.extend(new)
        if pm.vocabulary():
            last_vocab = ts
            if pm.others & ({m.clause for m in pm.mentions} | {pm.toks[s].clause for s, _e in pm.voucher_kw}):
                last_other = ts
    benefits = sorted(_merge(stmts), key=lambda b: (b.ts, b.seq))[-MAX_BENEFITS:]
    return [{
        "kind": b.kind,
        "title": _title(b),
        "service_id": b.svc.service_id if b.svc else None,
        "total_count": b.total,
        "remaining": b.remaining,
        "stated_by": "owner" if b.owner else "contact",
        "confidence": "high" if b.owner else "medium",
        "at": b.ts,
    } for b in benefits]


def anchor_timestamps(msgs) -> list[int]:
    """Timestamps (ms, ascending, unique) of the text messages with package or voucher vocabulary."""
    return sorted({ts for ts, _k, owner, text in _text_msgs(msgs) if _Msg(text, owner).vocabulary()})
