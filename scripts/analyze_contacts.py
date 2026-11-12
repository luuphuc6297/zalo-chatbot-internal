"""Profile the personal Zalo account's 1:1 contacts from the engine's local message cache. Rules only, no network.

What it does
  Opens the zalo-agent-cli cache (~/.zalo-agent-cli/accounts/<ownId>/zalo.db) READ-ONLY (sqlite URI mode=ro) and,
  for every 1:1 thread (groups, the account's chat with itself, and Zalo system / official accounts are skipped),
  derives:
    - identity: display name, message counts in/out, first/last message time, who wrote first, active days;
    - addressing: which pronouns (kinship terms included) the owner uses for the contact and the contact uses for
      themselves and for the owner, and a recommendation for the bot (the bot speaks for the studio and always calls
      itself "em"); only a customer or an unknown contact gets an address_term;
    - relationship: customer | staff | family | friend | unknown, with a confidence and reason codes;
    - services: catalog services (data/services.json) and catalog service categories the contact mentioned, and
      those with a past-use signal ("likely_used"; never certain); services the studio does not offer are ignored;
    - last_service: the most recent likely_used service with a confidence (customers and unknown contacts only);
    - evidence: at most 3 short snippets (<= 80 chars) from service/booking/price messages, phone numbers and long
      digit runs masked, never from a message with health vocabulary or about a sensitive service, never from the
      chat of a family member, a staff member or a friend.
  Output: JSON at $THOMHOUSE_BOT_HOME/profiles/contacts-<YYYYMMDD-HHMM>.json (file 0600, dir 0700; a folder given
  with --out-dir keeps its mode, with a warning when other users can read it) and a stdout summary of counts only.
  Message texts and names are never printed or logged.

  Nothing leaves the machine unless --push is given; --push posts the profiles to the LOCAL server only
  (POST /staff/profiles/import, staff id "analyzer"; SERVER_URL and STAFF_TOKEN from the environment or
  apps/server/.dev.vars). Contacts never consented to sending their past chats to a model provider, so there is no
  model call here. PROFILE_LLM_ENABLED (env, default false) is reserved for a future, consented model pass; it is
  not implemented and setting it to true makes the script stop.

Usage (from the project root):
  python3 -I scripts/analyze_contacts.py                 # analyze, write the JSON, print counts
  python3 -I scripts/analyze_contacts.py --dry-run       # analyze and print counts, write nothing
  python3 -I scripts/analyze_contacts.py --push          # also import into the local server
  python3 -I scripts/analyze_contacts.py --since 2026-01-01 --db /path/zalo.db --owner-id 123

Heuristics (all on lowercased NFC text and on a diacritic-free copy aligned character by character)
  Direction: in a 1:1 thread the thread id is the contact's uid, so a row whose senderId equals the thread id is the
  contact's; any other sender (the own uid, "0", or a noised id the mobile sync could not decode) is the owner's.
  System rows (deleted, event, group_event, poll_event, profile/OA cards, "ge:" ids) are not counted.
  System accounts are skipped (counted as skipped.system_account): a display name containing "Zalo", "Official
  Account" or the word "OA", or a contact whose rows are only cards, events and links (at least one card or event).

  Pronouns: tokens are split into clauses at . , ! ? ; : / newline and emoji. A pronoun token is
    - strong when written with its diacritics (chị, cô, chú, bác, cháu, mình, tôi, tớ, bạn, cậu, mày) or when it has
      no other common meaning (em, anh, tao, tui, cj, chj);
    - ambiguous for short forms and diacritic-free spellings that are also other words: e (em), a (anh; never
      "ạ/à/á"), c (chị), b (bạn), con, chi, minh, toi, ban, cau, chau. Plain "co/chu/bac" (có, chữ, bạc...) count only
      in the vocative "co oi". Diacritic-free spellings count only when the whole message has no diacritics.
    shop / ad / admin / spa (plain spelling) are read like a pronoun for the studio; any hit counts as a customer
    signal and never as an address term.
    Kinship terms are pronouns too: family-only terms (mẹ, má, bố, cha, ba, bô, plain "me" in a diacritic-free
    message, nội, ngoại, dì, dượng, mợ, thím, vợ, chồng, vk, and "ck" only as a vocative or after a greeting, since it
    is also chuyển khoản), elder-or-peer terms (ông, bà: an elder, or "you" between friends in the South), child terms
    (con, cháu), endearments (bé, cưng); cô, chú, bác, cậu stay senior terms. ba, cha, bô, bé, nội, ngoại, vk are
    ambiguous (three, small, "nội dung" ...). A kin term followed by a pronoun or a relative word is a third person
    ("mẹ em", "con chị", "vợ anh", "ba mẹ", "mẹ bầu", "bà con", "ông xã"), and so is one inside a noun phrase ("em bé",
    "vợ chồng", "ông bà").
  Not pronouns of the two people: gender-neutral pairs ("anh/chị", "anh chị", "anh, chị", "chị/anh", "anh hoặc chị",
  "a/c", "anh chị em", "cô/chú"; the clause is not split inside the pair), kin and third persons ("anh trai", "chị
  gái", "em bé", "anh ấy", "chị ta", "cô kia"), "chú ý", "bác sĩ", "cô đơn", and a capitalized given name right
  after a term ("chị Anh").
  The start of a clause skips leading particles (dạ, vâng, ok, thì, mà, hôm nay, sáng, tối ...) and vocatives
  ("chị Lan ơi"), so in "chị ơi cho em hỏi" the clause starts at "cho".
  Roles (who the pronoun points at), in this order:
    1. vocative: the next token is "ơi/oi" (a name between them is skipped) -> the person addressed;
    2. greeting / thanks: the previous tokens are chào, hi, hello, alo, cảm ơn, cám ơn, thanks, tks -> addressed; a
       plain "a" there ("cam on a") is skipped, it is as likely "ạ";
    3. "dạ/vâng/ok + PRON" closing the clause (only particles after it) -> addressed; a plain "a" there is skipped;
       "nhé/nha/đi/ạ ... + PRON" closing the clause ("ngủ ngon nha con") -> addressed (weight 1);
    4. "bên + PRON" ("bên em"): the studio side -> the owner's term, whoever writes (owner: owner_calls_self;
       contact: contact_calls_owner);
    5. right after cho/giúp/giùm/hộ/để/xin/chờ opening the clause ("cho em hỏi", "để em xem") -> the writer;
    6. a clause whose first pronoun PRON1 is followed later by a pronoun PRON2 of another term (not in a position of
       rules 1-4), unless PRON1 is followed by a first-person verb (muốn, cần, sẽ, đang, cảm ơn, đến, ...):
       a. "PRON1 ... giúp/giùm/hộ/cho PRON2" ("anh xem giúp em", "chị cho em hỏi"): the favour is for PRON2. In the
          contact's messages PRON1 is the owner (addressed) and PRON2 the writer. In the owner's messages a junior
          PRON1 is the owner offering ("em xem giúp chị nhé": em the writer, chị addressed); a senior PRON1 ("chị gửi
          giúp em ảnh") may be an offer or a request and is not counted;
       b. a senior PRON1 and a junior PRON2 without a favour word, not a question ("anh báo giá em ...", "chị gửi em
          địa chỉ"): in the contact's messages PRON1 addressed, PRON2 the writer; in the owner's messages not counted.
          A wrong reading of the contact's clause gives the contact a junior self-term, so the result falls back to
          the neutral "anh/chị"; the owner's clause is skipped because reading it either way could give the contact
          the owner's own (gendered) term;
    7. first pronoun of a statement clause (not a question: no "?" and no question word such as không/chưa/sao/gì/
       nào at the end; not ending in nhé/nha/với/đi), followed by something other than a particle -> the writer.
       Ambiguous tokens need a verb from a fixed list right after them (a name may sit in between). A senior term
       followed by a service action the studio does (xem, gửi, báo, tư vấn, check, nhắn, gọi, ...) is skipped: "anh
       xem lịch thứ 7" is "you check" as often as "I check". A senior self-term counts as clear ("self") after a
       first-person verb or one of đặt/book/làm/hỏi/có/không ..., else as word-order only ("self_weak");
    8. a later pronoun with a different term in the same clause, after a writer pronoun -> addressed (strong only).
       A kin term counts there only as the answer to a kin self-term ("con nhớ mẹ", "mẹ thương con"; an ambiguous
       con/bé then needs a verb, a particle or the clause end after it): after another self-term it is a third person
       ("chị đặt lịch cho mẹ"). Rule 6 reads only chị/anh/em-style terms, never kin terms; rule 7 skips ông/bà.
    Anything else is not counted (a question like "chị muốn đặt lịch không ạ?" is skipped: its subject can be
    either person). Vocative, greeting and "dạ + PRON" hits weigh 2, the others 1.
    Uses: separately from the roles, every term in a pronoun position is counted per side ("uses_owner",
    "uses_contact"; an ambiguous token needs a verb, a particle, "ơi" or the clause end after it). Uses measure
    whether kinship dominates a chat, whoever the term points at.
  Recommendation (bot calls itself "em"): senior terms chị, anh, cô, chú, bác; junior terms em, con, cháu, bé, cưng.
    A contact self-term that the same contact also uses for the owner is a misreading: the weaker of the two counts
    is dropped (a tie drops the self-term). Score each senior term by owner_calls_contact + contact_calls_self (a
    self-term from word order only weighs half; +1 when the owner's name for the thread starts with that term, e.g.
    "Chị Lan"). The best senior term wins when it
    is at least the junior evidence. When the owner calls the contact em/con/cháu or the contact calls the owner
    anh/chị (the contact is younger than the owner), the bot uses the contact's own anh or chị only from clear
    patterns (rules 5, 6a, 7 with a first-person verb), else "anh/chị". An elder (the owner calls themselves con/cháu,
    or the contact calls the owner con/cháu, >= 2 times and more than the junior evidence) without a direct cô/chú/bác
    gets "bác" when the owner calls them ông/bà, else "cô" for a middle name "Thị", "chú" for "Văn", else "anh/chị".
    Without evidence the answer is "anh/chị" with low confidence. Confidence: high when the winner has weight >= 4 and
    >= 80 % of the direct evidence, medium at >= 2 and >= 60 %. Family, staff and friends get address_term null
    (address_confidence low): the bot never drafts for them; addressing.bot_term_if_customer keeps the recommendation
    for staff.
  name_to_use: decoration is removed first: emoji, digits, punctuation and the words girl, boy, phố, xinh, cute, mr,
    mrs, ms, miss, baby, official, shop, spa, store, nail, beauty, salon, studio, khách quen, vip, quận, a district
    ... A business or service word (cty, shop online names, cafe, zalo, bank, admin, house ...) gives no name. Then
    the last word is the name only when what is left looks like a Vietnamese personal name: exactly one word after a
    kinship prefix ("Chị", "C.", "Cj", "A.", "Em", "Cô", "Chú"; the full words "Anh" and "Chi" are given names, not
    prefixes), one common given name alone ("Vy girl phố" -> Vy, "Lan Spa" -> Lan; "Bống" is a nickname), or 2-5
    words with at least one diacritic or a common family name first, not "Given Family" order; never a nickname of
    someone else ("Mẹ Bống", "Bé Su", "Vợ iu"), and the last word not a family name that is rarely a given name
    ("Chị Nguyễn").
  Relationship: customer | staff | family | friend | unknown. Kinship and insider evidence outweigh service words:
    people around a spa owner talk about the spa all the time.
    Customer vocabulary: strong customer words name the studio's trade (dịch vụ, liệu trình, bảng giá, spa, thom
    house, đặt lịch, lịch hẹn, a catalog service or category); weak words are everyday ones (giá, cọc, bao nhiêu tiền,
    combo, voucher, khuyến mãi, tư vấn, thanh toán, book, slot, giữ chỗ, an amount like 50k, "mai chị qua" / "3h em
    ghé"). A message about the shop's operations (insider, below) or naming only a service the studio does not offer
    (làm móng, nail, nối mi, cắt tóc, triệt lông, xông hơi, ngâm chân ...) is not customer vocabulary, gives no service
    and no evidence.
    Customer points = contact messages with strong words + 0.5 x contact messages with weak words only + 2 x the
    contact's catalog matches + 3 x the contact's shop/ad/admin/spa + 0.5 x owner messages with strong words + 1 x the
    owner's "shop" + 0.5 x owner messages that open with "dạ/vâng" and call the contact chị/anh (at most 3). Words
    friends use as much as customers ("bao nhiêu" alone, "hẹn", "mấy giờ", "chuyển khoản", "gói", "mở cửa") are not
    customer vocabulary; the owner's service talk (a promotion sent to every contact) is never a strong sign.
    Purchase ratio = (contact messages with strong words + 0.5 x weak only + shop/ad from the contact) / contact text
    messages.
    Personal points = 2 x intimate signals (tao, mày; tui with ông/bà; tớ with cậu; at most 6 points) + personal
    chit-chat markers (at most 3; "về nhà", "nhậu", "nhớ quá" only with diacritics) + 3 for a long chat (>= 30 text
    messages, strong service messages <= 2 % of them) + 2 for >= 8 active days without any.
    Family points = uses of family-only terms (both sides) + child-term uses up to that number + 3 x couple signals
    ("anh yêu", "vợ iu", "yêu em", "ông xã ơi", vk/ox/bx not followed by a pronoun) + 2 x family endearments ("con
    yêu", "mẹ yêu") + 4 when the thread name is only a family word ("Mẹ", "Vợ iu") + half the ông/bà uses next to child
    terms. With >= 2 couple signals the couple's anh/em uses count as kinship. family when family-only uses >= 3 (or
    such a name, or a couple), >= 6 points and >= 1.5 x the uses of non-kin terms (chị, anh, em, mình, bạn, tôi, tớ,
    tui, tao, mày); high at >= 12 points, >= 3 x non-kin uses and family terms from both sides (or >= 10 of them, the
    name, or >= 3 couple signals). An elder pattern (owner con/cháu with cô/chú/bác/ông/bà/cậu/dì >= 2, personal
    points >= 3, customer points <= 1, no insider talk) is family/medium. Reason family_role: contact_parent,
    contact_child, spouse, elder or relative.
    Insider talk (staff): shifts, pay and shop chores (ca làm, nghỉ ca, chấm công, ứng lương, dọn tiệm, KTV, chia
    tour, mở/đóng tiệm, xin nghỉ ...) and the shop's customers as a third person (khách đặt/tới/hủy/hỏi, có khách,
    lịch của khách, báo/nhắn/chuyển khoản cho khách; not "khách quen/cũ/vip", which customers say of themselves);
    weak: đi làm, tới/ở tiệm, mở cửa, dọn phòng, lương, xếp lịch. An owner message with insider words and an
    instruction (giùm, nhớ, đừng, a closing nha/nhé/đi) is an instruction. Staff points = 2 x contact insider
    messages + 0.5 x weak ones + instructions + 0.5 x owner insider messages + 2 when the owner calls the contact
    "bé" twice or more. staff when >= 2 contact insider messages, >= 6 points, >= half the customer points, and the
    contact is the junior (owner calls them em/bé or they call the owner chị/anh, more than the reverse) or the
    contact talks shop a lot (>= 5 messages, >= 15 points); high at >= 5 contact insider messages, >= 15 points,
    junior evidence >= 6 and >= 2 x senior, and staff points >= customer points.
    friend/high: no shop/ad from the contact, < 2 contact insider messages, and a very long chat (>= 1000 text
    messages, or >= 400 over >= 30 days) with purchase ratio < 3 %, or a long chat (>= 200 over >= 10 days) with
    purchase ratio < 3 % and intimacy or chit-chat, or >= 2 intimate signals with >= 6 personal points, >= 30 text
    messages, no strong word or catalog match from the contact and personal points >= 3 x customer points.
    friend/medium: a long chat with purchase ratio < 8 %, or personal points >= 3 and >= 2 x customer points.
    Order: family, staff, elder family, friend high, friend medium, customer high (>= 6 points, personal <= 1),
    customer medium (>= 3 and >= 2 x personal), staff low, customer low, friend low, family low, unknown. The server
    keeps family, staff and friends at high confidence away from the bot. None of them keeps an evidence snippet or a
    last_service.
  Services: aliases from each catalog name (main name, the part in brackets, dash-separated parts of >= 2 words,
    the id with dashes as spaces) plus a few common spellings; an alias shared by two services becomes a category hit.
    Category keywords (gội đầu, massage, chăm sóc da, nặn mụn, xóa thâm, diện chẩn, vùng kín ...) give category
    entries, only for a group the catalog has services in. Longest match wins. Past-use signals: time phrases (lần trước, hôm trước, tuần trước ...) mark the services of their own
    message; visit phrases (đã làm, đã ghé, làm xong, dùng rồi, quay lại from the contact, feedback, "cảm ơn ... đã
    ghé/đến/sử dụng/trải nghiệm" from the owner) mark those of their message, or else those mentioned in the
    previous 72 hours of the thread. A phrase with an inquiry verb (hỏi, xem, nhắn, báo ...) within 4 words after or
    3 before it does not count ("tuần trước em có hỏi giá ..."). Services of the health and women groups are flagged
    sensitive; the server never shows them to the model.
  last_service: the likely_used service with the latest signal (a catalog service wins a tie with a category):
    {key, service_id, name, at, source "chat", confidence, sensitive}. Confidence high after >= 2 signals in messages
    that name the service, medium when the latest signal named it (or an earlier one did), low when it comes only
    from the 72-hour window. The server merges it with recorded visits and gives the model name + date only when it
    is not sensitive and its confidence is medium or high (a recorded visit always qualifies).
  Evidence: only messages with strong customer words; never a message with health vocabulary, checked with
    diacritics and, for every word written without them, also in the plain spelling (also inside a message with
    diacritics elsewhere).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import stat
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
ANALYZER_VERSION = "contacts-rules-v3"
TZ_VN = timezone(timedelta(hours=7))
DAY_MS = 86_400_000
IMPORT_BATCH = 200
SNIPPET_MAX = 80
MAX_SNIPPETS = 3
SENSITIVE_GROUPS = {"health", "women"}

THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")   # server: zalo_user_id must match ^p:[A-Za-z0-9_-]{1,64}$
SYSTEM_TYPES = {"deleted", "event", "group_event", "poll_event", "card", "profile_card", "reaction"}
TEXT_TYPES = {"text", "", None}

# ---------------------------------------------------------------- text helpers


def _strip_char(c: str) -> str:
    if c == "đ":
        return "d"
    if c == "Đ":
        return "D"
    d = unicodedata.normalize("NFD", c)
    return d[0] if d else c


def nfc_lower(text: str) -> str:
    """NFC, lowercased per character so every index stays aligned with the original string."""
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        lo = ch.lower()
        out.append(lo if len(lo) == 1 else ch)
    return "".join(out)


def fold(text: str) -> str:
    """Diacritics removed character by character (same length as the input)."""
    return "".join(_strip_char(c) for c in text)


def has_marks(text: str) -> bool:
    return any(_strip_char(c) != c for c in text if c.isalpha())


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
BOUNDARY_CHARS = set(".,!?;:\n\r…()[]{}\"“”|/")


@dataclass
class Tok:
    orig: str      # lowercased NFC
    bare: str      # diacritics removed
    cased: str     # original case (NFC)
    start: int
    end: int
    neutral: bool = False   # part of a gender-neutral pair ("anh/chị", "anh chị", "a/c"): a pronoun of neither person


@dataclass
class Clause:
    toks: list[Tok]
    question: bool


# Gender-neutral address pairs: "anh/chị", "anh chị", "anh, chị", "chị/anh", "anh hoặc chị", "a/c", "anh chị em",
# "cô/chú". Shops send "xin chào anh/chị" to every new contact, so neither word says anything about the contact.
PAIR_TERMS = {"anh": "anh", "chị": "chị", "cô": "cô", "chú": "chú", "bác": "bác", "cj": "chị", "chj": "chị"}
PAIR_SHORT = {"a": "anh", "c": "chị"}        # only with a slash ("a/c")
PAIR_PLAIN = {"chi": "chị"}                  # with a slash, or in a diacritic-free message
PAIR_JOIN = {"hoặc", "hay", "và", "hoac"}
PAIR_GAP_CHARS = set(" \t/,&+-\\|")


def _pair_term(t: Tok, slash: bool, plain_ok: bool) -> str | None:
    if t.orig in PAIR_TERMS:
        return PAIR_TERMS[t.orig]
    if slash and t.orig in PAIR_SHORT:
        return PAIR_SHORT[t.orig]
    if (slash or plain_ok) and t.orig in PAIR_PLAIN:
        return PAIR_PLAIN[t.orig]
    return None


def _mark_neutral(toks: list[Tok], low: str, plain_ok: bool) -> None:
    n = len(toks)
    i = 0
    while i < n - 1:
        a = toks[i]
        j = i + 1
        if toks[j].orig in PAIR_JOIN and j + 1 < n:
            j += 1
        b = toks[j]
        if j == i + 1:
            gap = low[a.end:b.start]
            ok_gap = all(ch in PAIR_GAP_CHARS for ch in gap)
        else:
            gap = low[a.end:toks[i + 1].start] + low[toks[i + 1].end:b.start]
            ok_gap = all(ch.isspace() for ch in gap)
        slash = "/" in gap
        ta, tb = _pair_term(a, slash, plain_ok), _pair_term(b, slash, plain_ok)
        # "chị Anh" (lowercase term, capitalized word, space only) is a term and a given name, not a pair
        name_like = not gap.strip() and a.cased[:1].islower() and b.cased[:1].isupper()
        if ok_gap and ta and tb and ta != tb and not name_like:
            for k in range(i, j + 1):
                toks[k].neutral = True
            if j + 1 < n and toks[j + 1].bare in ("em", "e") and not low[b.end:toks[j + 1].start].strip(" /,"):
                toks[j + 1].neutral = True     # "anh chị em"
            i = j                              # a chain: "anh/chị/cô/chú"
            continue
        i += 1


def clauses_of(text: str) -> tuple[list[Clause], bool]:
    """Splits a message into clauses; returns (clauses, message_has_diacritics)."""
    cased = unicodedata.normalize("NFC", text or "")
    low = nfc_lower(cased)
    bare = fold(low)
    marked = has_marks(low)
    toks = [Tok(low[m.start():m.end()], bare[m.start():m.end()], cased[m.start():m.end()], m.start(), m.end())
            for m in TOKEN_RE.finditer(low)]
    _mark_neutral(toks, low, not marked)
    out: list[Clause] = []
    cur: list[Tok] = []
    for i, t in enumerate(toks):
        cur.append(t)
        gap_end = toks[i + 1].start if i + 1 < len(toks) else len(low)
        gap = low[t.end:gap_end]
        boundary = i + 1 == len(toks) or any(ch in BOUNDARY_CHARS or unicodedata.category(ch) == "So" for ch in gap)
        if boundary and i + 1 < len(toks) and t.neutral and toks[i + 1].neutral and \
                all(ch in PAIR_GAP_CHARS or ch.isspace() for ch in gap):
            boundary = False                   # "anh/chị", "anh, chị" stay in one clause
        if boundary:
            out.append(Clause(cur, "?" in gap))
            cur = []
    return out, marked


# ---------------------------------------------------------------- vocabulary

SENIOR = ("chị", "anh", "cô", "chú", "bác")
JUNIOR = ("em", "con", "cháu", "bé", "cưng")
# Kinship address terms. Family-only terms say the two people are relatives or a couple. ông/bà are elders, or "you"
# between friends in the South ("bà đi đâu đó"); cô/chú/bác/cậu are relatives as often as older customers, so they
# stay senior address terms and count as family only next to other family evidence.
PARENT_TERMS = {"mẹ", "má", "ba", "bố", "bô", "cha"}
SPOUSE_TERMS = {"vợ", "chồng", "vk", "ck"}
FAMILY_TERMS = PARENT_TERMS | SPOUSE_TERMS | {"nội", "ngoại", "dì", "dượng", "mợ", "thím"}
ELDER_PEER_TERMS = {"ông", "bà"}
CHILD_TERMS = {"con", "cháu"}
# Terms checked for a third person right after them ("mẹ em", "con chị", "vợ anh", "ba mẹ"): kin words name a relative
# of someone as often as they address the reader.
KIN_LIKE = FAMILY_TERMS | ELDER_PEER_TERMS | CHILD_TERMS | {"bé", "cưng"}
# Terms rule 6 (two pronouns in one clause) reads; kin terms there are mostly a third person ("đặt cho mẹ").
RULE6_TERMS = set(SENIOR) | {"em", "con", "cháu", "mình", "tôi", "tớ", "bạn", "cậu", "tao", "mày", "tui"}
# Terms that address an elder relative, and the junior terms that answer them ("con nhớ mẹ", "mẹ thương con").
KIN_ELDER = FAMILY_TERMS | ELDER_PEER_TERMS | {"cô", "chú", "bác", "cậu"}
KIN_JUNIOR = {"con", "cháu", "bé", "cưng"}
# Address terms that are neither kin nor elders: their share measures whether kinship dominates a chat.
NONKIN_TERMS = ("chị", "anh", "em", "mình", "bạn", "tôi", "tớ", "tui", "tao", "mày")
# orig (diacritics) -> term; strong forms
STRONG = {"chị": "chị", "anh": "anh", "cô": "cô", "chú": "chú", "bác": "bác", "cháu": "cháu", "em": "em",
          "mình": "mình", "tôi": "tôi", "tớ": "tớ", "bạn": "bạn", "cậu": "cậu", "tao": "tao", "mày": "mày",
          "tui": "tui", "cj": "chị", "chj": "chị",
          "mẹ": "mẹ", "má": "má", "bố": "bố", "dì": "dì", "dượng": "dượng", "mợ": "mợ", "thím": "thím",
          "vợ": "vợ", "chồng": "chồng", "ông": "ông", "bà": "bà", "cưng": "cưng"}
# short forms with other common meanings ("ba" is also three, "bé" small, "con" a classifier, "nội" in "nội dung");
# they need a verb, a vocative or a closing position
AMBIG_SHORT = {"e": "em", "a": "anh", "c": "chị", "b": "bạn", "con": "con", "ba": "ba", "cha": "cha", "bô": "bô",
               "bé": "bé", "nội": "nội", "ngoại": "ngoại", "vk": "vk", "ck": "ck"}
# "ck" is also chuyển khoản: a husband only in a vocative or greeting position ("ck ơi", "chào ck")
VOCATIVE_ONLY_TERMS = {"ck"}
# diacritic-free spellings, only in a message without any diacritics
AMBIG_PLAIN = {"chi": "chị", "minh": "mình", "toi": "tôi", "ban": "bạn", "cau": "cậu", "chau": "cháu", "me": "mẹ"}
# plain spellings that count only in the vocative "<x> oi"
VOCATIVE_ONLY_PLAIN = {"co": "cô", "chu": "chú", "bac": "bác"}
BUSINESS_ADDRESS = {"shop", "ad", "admin", "spa", "sop"}  # bare forms; the contact addressing the studio as a business

VOCATIVE_NEXT = {"oi"}
GREET_PREV = {"chao", "hi", "hello", "helo", "alo", "thanks", "thank", "tks", "thx", "camon", "cmon"}
LEADS_ORIG = {"dạ", "vâng", "ừ", "ừm", "uh", "uhm", "ok", "oke", "okie", "okay", "vậy", "thế", "nhưng", "mà", "thì",
              "rồi", "nếu", "khi", "còn", "hi", "hello", "alo", "à", "ờ", "hôm", "nay", "mai", "mốt", "sáng", "chiều",
              "trưa", "tối", "bây", "giờ", "lúc", "tuần", "sau", "chắc", "thôi", "vì", "nên"}
LEADS_PLAIN = {"da", "vang", "u", "uh", "um", "ok", "oke", "okie", "okay", "vay", "the", "nhung", "ma", "thi",
               "roi", "neu", "khi", "hom", "nay", "mai", "sang", "chieu", "trua", "bay", "gio", "luc", "tuan", "sau",
               "chac", "thoi", "vi", "nen"}
YES_ORIG = {"dạ", "vâng", "ừ", "ok", "oke", "okie", "okay"}
YES_PLAIN = {"da", "vang", "ok", "oke", "okie", "okay"}
DEFER_ORIG = {"dạ", "vâng"}
DEFER_PLAIN = {"da", "vang"}
REQUEST_ORIG = {"cho", "giúp", "giùm", "hộ", "để", "xin", "chờ"}
SIDE_ORIG = {"bên"}   # "bên em" / "bên chị": the studio side; the pronoun is the owner's term
SIDE_PLAIN = {"ben"}
REQUEST_PLAIN = {"cho", "giup", "gium", "de", "xin"}
# "PRON1 ... giúp/giùm/hộ/cho PRON2": PRON2 is the one the favour is for
FAVOR_ORIG = {"cho", "giúp", "giùm", "hộ"}
FAVOR_PLAIN = {"cho", "giup", "gium"}
# Verbs after a subject that mark the writer ("chị muốn", "anh cảm ơn", "chị sẽ"): "PRON1 + one of these ... PRON2"
# keeps PRON1 as the writer even before "giúp/cho PRON2" ("anh muốn đặt cho em").
SELF_VERBS_STRONG = {"muon", "can", "dinh", "tinh", "dang", "se", "vua", "moi", "sap", "thay", "nghi", "cam", "xin",
                     "bi", "o", "la", "cung", "van", "rat", "phai", "mong", "nho", "quen", "thuong", "yeu", "thich",
                     "biet", "hieu", "chao", "an", "ngu", "den", "toi", "qua", "ghe", "ve", "di"}
# A senior subject followed by one of these (and no second pronoun) counts as a clear self-term ("chị đặt lịch").
SELF_VERBS = SELF_VERBS_STRONG | {"hoi", "co", "khong", "ko", "k", "chua", "hong", "hok", "kg", "vao", "ra", "len",
                                  "xuong", "duoc", "dc", "doi", "ok", "dat", "book", "lam"}
# Service actions the studio does for a customer: "anh xem lịch thứ 7" may be "you check" as well as "I check", so a
# senior subject followed by one of these and no second pronoun is not counted.
ASK_VERBS_ORIG = {"xem", "coi", "gửi", "báo", "tư", "check", "kiểm", "nhắn", "gọi", "chuyển", "lấy", "đưa", "giữ",
                  "tìm", "ib", "inbox"}
ASK_VERBS_PLAIN = {"xem", "coi", "gui", "bao", "tu", "check", "kiem", "nhan", "goi", "chuyen", "lay", "dua", "giu",
                   "tim", "ib", "inbox"}
# "chú ý" (pay attention), "bác sĩ" (doctor), "cô đơn", "anh hùng", "nội dung", "bà bầu", "ông xã": not pronouns
NOT_PRONOUN_NEXT = {
    "chú": {"ý", "trọng"}, "bác": {"sĩ"}, "cô": {"đơn", "giáo", "nhi"}, "anh": {"hùng", "ngữ"},
    "nội": {"dung", "thất", "bộ", "trợ", "tiết", "soi", "khoa", "địa", "vụ", "quy", "công", "tâm", "các", "thành",
            "trú", "tiết", "lực", "tạng"},
    "ngoại": {"hình", "trừ", "tỉnh", "ngữ", "giao", "khoa", "lệ", "tuyến", "ô", "thành", "quốc", "cảnh", "trời",
              "lai", "vi", "hạng", "khóa", "khoá"},
    "bà": {"con", "xã", "bầu", "đẻ", "chủ", "nội", "ngoại", "già", "cô", "bô"},
    "ông": {"xã", "chủ", "bà", "nội", "ngoại", "trời", "già", "bô"},
    "mẹ": {"bầu", "bỉm", "đẻ", "chồng", "vợ", "kế", "ghẻ", "nuôi", "ruột"},
    "bé": {"xíu", "tí", "tẹo", "nhỏ", "hơn", "nhất", "lắm", "quá", "bỏng"},
    "con": {"nít", "cái", "số", "đầu", "út", "gái", "trai", "mèo", "chó", "gà", "người", "đường", "dấu", "mắt",
            "ngươi", "tim", "heo", "cháu", "nhỏ", "lắc"},
    "chồng": {"chất", "lên", "sắp"}, "vợ": {"sắp"}, "cha": {"chả", "chà", "xứ"},
}
# A kin term right after one of these is part of a noun phrase ("em bé", "con bé", "thằng bé", "ông bà", "vợ chồng")
KIN_NOUN_PREV = {
    "bé": {"em", "con", "thằng", "đứa", "cô", "cậu", "nhỏ", "cháu", "bé", "e"},
    "con": {"mẹ", "má", "ba", "bố", "cha", "đứa", "thằng", "hai", "một", "những", "mấy", "vài", "các", "sinh"},
    "bà": {"ông"}, "ông": {"bà"}, "chồng": {"vợ", "lấy", "có"}, "vợ": {"lấy", "có", "chồng"},
    "mẹ": {"ba", "bố", "cha", "má"}, "má": {"ba", "bố"},
}
# A kin term followed by one of these names a third person: "mẹ em" (my/your mother), "con chị", "vợ anh", "ba mẹ".
KIN_POSSESSOR_ORIG = {"em", "anh", "chị", "tôi", "mình", "tui", "tao", "mày", "bạn", "nó", "họ", "con", "cháu", "cô",
                      "chú", "bác", "ông", "bà", "mẹ", "má", "ba", "bố", "cha", "của", "nhà", "chồng", "vợ", "ck", "vk",
                      "kế", "ghẻ", "đẻ", "ruột", "nuôi", "bầu", "bỉm", "chủ", "xã", "e", "c", "cj", "chj", "mk"}
KIN_POSSESSOR_PLAIN = {"chi", "toi", "minh", "may", "ban", "no", "ho", "chau", "bac", "ong", "me", "bo", "cua",
                       "chong", "vo", "ruot", "nuoi"}
# "... nhé con", "ngủ ngon nha mẹ": a term after a closing particle at the end of a clause addresses the reader
CLOSING_PARTICLE_ORIG = {"nhé", "nha", "nhen", "nghen", "đi", "ạ", "à", "hen", "nè", "nhe", "nhaa", "nhee", "hả",
                         "nhỉ"}
CLOSING_PARTICLE_PLAIN = {"nhe", "nha", "nhen", "nghen", "di", "a", "hen", "ne", "ha", "nhi"}
END_PARTICLES = {"a", "nhe", "nha", "nhen", "nghen", "ha", "hen", "nhi", "day", "do", "ne", "ak", "ah", "luon",
                 "voi", "nhoa", "nhaa", "nhee", "oi", "nhes", "ha"}
IMPERATIVE_END = {"nhe", "nha", "nhen", "nghen", "voi", "di", "nhaa", "nhee", "nhes", "nhoa"}
QUESTION_END = {"khong", "ko", "k", "hong", "hok", "kg", "chua", "ha", "nhi", "sao", "gi", "j", "nao", "nhieu", "may",
                "ak", "hem"}
# "anh trai", "chị gái", "em bé" (kin), "anh ấy", "chị ta", "cô kia", "em này" (a third person)
FAMILY_FOLLOW = {"trai", "gai", "re", "dau", "ho", "ruot", "ca", "ut", "be", "nho", "lon", "nuoi", "xa",
                 "ay", "ta", "kia", "nay"}
VERBS = {
    "muon", "can", "hoi", "dat", "book", "xin", "co", "khong", "ko", "k", "da", "dang", "se", "vua", "moi", "thay",
    "nghi", "den", "toi", "qua", "di", "ve", "lam", "gui", "nhan", "o", "bi", "duoc", "dc", "thich", "chao", "cam",
    "cung", "van", "chua", "hen", "goi", "check", "xem", "biet", "hieu", "nho", "quen", "thuong", "yeu", "an", "ngu",
    "tinh", "dinh", "vao", "ra", "len", "xuong", "mua", "chuyen", "ck", "tra", "huy", "doi", "ghe", "sap", "phai",
    "mong", "rat", "hay", "chi", "nhan", "bao", "ung", "ok", "dong", "the", "lai", "tu", "con", "cu", "mat", "dung",
    "thu", "noi", "nhac", "hoi", "kiem", "dua", "lay", "mo", "nghe", "doc", "viet", "hong", "hok", "kg",
}
INTIMATE_ALWAYS = {"mày"}
INTIMATE_MARKED_ONLY = {"tao", "tau", "mi"}   # plain spellings of tạo / tàu / mì in a diacritic-free message
# Matched without diacritics: these spellings have no common other meaning.
PERSONAL_CHITCHAT = ("ngu ngon", "an com chua", "an gi chua", "an trua chua", "di choi", "ca phe", "cafe", "hop lop",
                     "don con", "don be", "chuc mung sinh nhat", "tet nay", "an tet")
# Matched only as written with diacritics: "ve nha" is also "về nha" (bye, I am off), "nhau" is "gặp nhau".
PERSONAL_CHITCHAT_ORIG = ("về nhà", "về quê", "nhậu", "nhớ quá", "thương quá", "bố mẹ", "ba mẹ", "cả nhà", "ông bà",
                          "hun")
# Customer vocabulary. Strong words name the studio's trade; weak words are everyday words (a price, "book", "slot",
# "combo", an amount) that count as half a point and only fully next to a service or a strong word. Words a friend or
# relative uses all the time ("bao nhiêu" alone, "hẹn", "mấy giờ", "chuyển khoản", "gói", "mở cửa") are left out.
SERVICE_PHRASES = ("dich vu", "lieu trinh", "bang gia", "spa", "studio", "thom house", "thomhouse")
SERVICE_WEAK_PHRASES = (
    "bao nhieu tien", "bao nhieu a", "bnhieu", "bn tien", "nhieu tien", "menu", "combo", "voucher", "uu dai",
    "khuyen mai", "tu van", "gia bn", "gia bao", "gia sao", "gia the nao", "het bao", "mat bao", "dat coc",
    "thanh toan",
)
# Shop operations seen from the inside (docstring "Relationship"): shifts, pay, opening the shop, technicians, and the
# shop's customers as a third person. Written with diacritics; the plain spellings count in a diacritic-free message.
INSIDER_ORIG = (
    "ca làm", "ca sáng", "ca chiều", "ca tối", "ca trực", "nghỉ ca", "đổi ca", "lên ca", "vào ca", "hết ca", "tan ca",
    "giao ca", "trực ca", "chia ca", "lịch ca", "xếp ca", "chấm công", "bảng lương", "ứng lương", "tính lương",
    "chuyển lương", "trả lương", "phát lương", "tăng lương", "dọn tiệm", "kỹ thuật viên", "kĩ thuật viên", "ktv",
    "chia tour", "tiền tour", "tính tour", "lên tour", "hoa hồng", "doanh thu", "chốt sổ", "chốt ca", "kết ca",
    "trực tiệm", "coi tiệm", "giữ tiệm", "mở tiệm", "đóng tiệm", "mở cửa tiệm", "đóng cửa tiệm", "xin nghỉ",
    "nghỉ phép", "có người đặt", "có người book", "người ta đặt",
)
# Everyday words a customer or a friend also writes ("em tới tiệm rồi", "đi làm về"): half a point, never alone.
INSIDER_WEAK_ORIG = ("đi làm", "nghỉ làm", "tới tiệm", "đến tiệm", "ở tiệm", "lên tiệm", "ra tiệm", "về tiệm",
                     "tại tiệm", "mở cửa", "đóng cửa", "dọn phòng", "lương", "xếp lịch", "lịch làm")
# The shop's customers as a third person: "khách đặt", "có khách", "lịch của khách", "chuyển khoản cho khách".
# "khách quen / khách cũ / khách vip" are left out: customers describe themselves that way.
KHACH_RE = re.compile(
    r"(?<![^\W_])(?:co khach|khach (?:dat|book|bo|toi|den|qua|huy|hoi|hen|nhan|goi|ib|inbox|chuyen|ck|tra|coc|doi|ve|"
    r"vo|vao|muon|can|lam|di|nay|do|kia|nam|nu|le|om|bung|tre|gui|keu|review|danh gia|cua (?:chi|em|minh|tiem|anh|mk))|"
    r"(?:bao|nhan tin|nhan|goi|tra loi|rep|xep|chot|giu|don|tiep|lam cho|hen|dat cho|book cho|cho|doi|xac nhan|nhac|"
    r"chuyen khoan cho|hoan tien cho|tra tien cho) (?:lich )?(?:cho )?khach|lich (?:cua )?khach|"
    r"(?:dong|vang|it|nhieu|het|hut) khach)(?![^\W_])")
# Words of an instruction in the owner's message ("nhắn khách giùm chị nha", "em nhớ dọn phòng")
INSTRUCTION_ORIG = {"giùm", "giúp", "dùm", "nhớ", "phải", "đừng", "kêu", "nhắc", "lo"}
# Services the studio does not offer (nail, hair salon, lashes, waxing, steam, foot soak): never a service of the
# profile, never customer vocabulary, never evidence ("đi làm móng không" is not a visit to thom house).
NON_CATALOG_PHRASES = ("lam mong", "nail", "nails", "son gel", "son mong", "ve mong", "noi mi", "uon mi", "lam mi",
                       "phun may", "phun moi", "xam may", "cat toc", "nhuom toc", "uon toc", "duoi toc", "lam toc",
                       "triet long", "waxing", "wax long", "xong hoi", "ngam chan", "tam trang")
# A couple: "anh yêu", "vợ iu", "yêu em", "ông xã ơi" (not "ông xã em", the contact's husband).
COUPLE_RE = re.compile(
    r"(?<![^\W_])(?:(?:anh|em|vo|chong|ck|vk) (?:yeu|iu)(?! cau)(?! thich)|(?<!dang )(?:yeu|iu|hun) (?:anh|em|vo|chong|ck|vk)"
    r"|(?:ong xa|ba xa)(?! (?:em|chi|anh|toi|minh|tui|cua|e|c|a|mk)(?![^\W_])))(?![^\W_])")
SERVICE_WEAK_ORIG = ("giá", "cọc")
BOOKING_PHRASES = ("dat lich", "lich hen", "hen lich", "dat hen", "huy lich", "doi lich", "con lich", "khung gio")
BOOKING_WEAK_PHRASES = ("book", "booking", "dat cho", "giu cho", "hen gio", "con slot", "slot", "gio mo cua",
                        "mo cua may gio", "qua lam", "ghe lam", "den lam")
BOOKING_WEAK_ORIG = ("còn chỗ",)
PRICE_RE = re.compile(r"\b\d{2,4}\s?k\b|\b\d{1,3}(?:[.,]\d{3})+\s?(?:đ|d|vnd|vnđ|dong|đồng)?\b|\b\d+\s?(?:tr|triệu|trieu)\b")
# "mai chị qua", "chiều em ghé", "3h chị đến": a visit with a time (weak booking vocabulary)
VISIT_VERB_ORIG = {"qua", "ghé", "đến", "tới"}
VISIT_VERB_PLAIN = {"qua", "ghe", "den"}
VISIT_TIME_ORIG_RE = re.compile(
    r"(?<![^\W_])(?:mai|chiều|sáng|tối|trưa|thứ\s?\d|chủ nhật|cn|\d{1,2}\s?h(?:\d{2})?|\d{1,2}\s?giờ|\d{1,2}:\d{2})(?![^\W_])")
VISIT_TIME_PLAIN_RE = re.compile(
    r"(?<![^\W_])(?:mai|chieu|sang|trua|thu\s?\d|chu nhat|cn|\d{1,2}\s?h(?:\d{2})?|\d{1,2}\s?gio|\d{1,2}:\d{2})(?![^\W_])")
# Past-use signals. A time phrase ("lần trước") marks only the services of its own message; a visit phrase also those
# of the previous 72 hours. Neither counts when an inquiry verb sits next to it ("tuần trước em có hỏi giá ...").
PAST_TIME_PHRASES = ("lan truoc", "hom truoc", "bua truoc", "buoi truoc", "dot truoc", "thang truoc", "tuan truoc")
PAST_VISIT_PHRASES = ("lam roi", "lam xong", "dung roi", "thu roi", "den roi", "ghe roi", "quay lai", "hom qua lam",
                      "sau khi lam", "sau buoi", "feedback", "feeback")
CONTACT_ONLY_PAST = {"quay lai"}   # the owner's "em quay lại báo chị" is not a revisit
# "đã X" only with its diacritics: the diacritic-free "da lam" is also "dạ làm" (yes, can do).
PAST_USE_ORIG = ("đã làm", "đã dùng", "đã thử", "đã đến", "đã ghé", "đã qua", "đã sử dụng")
# The owner thanking for a visit. Thanks for "tin tưởng / lựa chọn / ủng hộ" follow an inquiry or a booking too.
OWNER_VISIT_RE = re.compile(r"\bcam on\b.{0,40}\bda (?:ghe|den|qua|su dung|trai nghiem)\b")
INQUIRY_ORIG = {"hỏi", "xem", "coi", "nhắn", "inbox", "ib", "tham", "báo"}
INQUIRY_PLAIN = {"hoi", "xem", "coi", "nhan", "inbox", "ib", "tham", "bao"}
HEALTH_ORIG = ("bệnh", "đau", "sinh", "kinh", "thai", "ung thư", "viêm", "thuốc", "bác sĩ", "khám", "xét nghiệm",
               "mổ", "phẫu thuật", "tiểu đường", "huyết áp", "tim mạch", "gan", "thận", "dị ứng", "nhiễm", "nấm",
               "ngứa", "sốt", "mất ngủ", "trầm cảm", "tê", "tĩnh mạch", "đột quỵ", "thiếu máu", "rối loạn",
               "nguyệt", "phụ khoa", "tuyến giáp", "xương khớp", "thoát vị", "bầu", "vùng kín", "sàn chậu", "u",
               "hạch", "khối u", "ho", "cảm cúm", "bị cảm", "yoni", "ngực", "bướu", "xuất huyết", "chảy máu",
               "thoái hóa", "thoái hoá", "cột sống", "dạ dày", "bao tử", "tử cung", "buồng trứng", "trĩ", "gút",
               "gout", "hen suyễn", "suyễn", "tiền đình", "tai biến", "liệt", "động kinh", "xoang", "phổi",
               "chấn thương", "bong gân", "gãy", "mỡ máu", "tháo đường", "chàm", "vảy nến", "á sừng", "zona",
               "sảy thai", "hiếm muộn", "hóa trị", "hoá trị", "xạ trị", "nội soi", "siêu âm", "tiêm", "cho con bú",
               "hậu sản", "cholesterol", "covid", "hiv", "tự kỷ", "lo âu", "hoảng loạn", "migraine", "nửa đầu")
# Diacritic-free spellings. They are checked on every word written without diacritics, also inside a message that
# has diacritics elsewhere ("em bi dau lung lắm"). Over-matching is on purpose: a skipped snippet costs nothing.
HEALTH_PLAIN = ("benh", "dau", "sinh", "kinh", "thai", "ung thu", "viem", "thuoc", "bac si", "kham", "xet nghiem",
                "phau thuat", "tieu duong", "huyet ap", "tim mach", "di ung", "nhiem", "ngua", "sot", "mat ngu",
                "tram cam", "tinh mach", "dot quy", "thieu mau", "roi loan", "nguyet", "phu khoa", "tuyen giap",
                "xuong khop", "thoat vi", "bau", "vung kin", "san chau", "u", "hach", "cam cum", "bi cam", "yoni",
                "nguc", "buou", "xuat huyet", "chay mau", "thoai hoa", "cot song", "da day", "bao tu", "tu cung",
                "buong trung", "benh tri", "bi tri", "gut", "gout", "hen suyen", "suyen", "tien dinh", "tai bien",
                "dong kinh", "xoang", "phoi", "chan thuong", "bong gan", "gay xuong", "mo mau", "thao duong",
                "vay nen", "a sung", "zona", "say thai", "hiem muon", "hoa tri", "xa tri", "noi soi", "sieu am",
                "tiem chung", "mui tiem", "cho con bu", "hau san", "cholesterol", "covid", "hiv", "tu ky", "lo au",
                "hoang loan", "migraine", "nua dau", "bi u", "khoi u", "u xo", "u nang")
# Diacritic-free "dau" is also đầu / đâu / dầu: these phrases are not about pain and are removed before the check.
NOT_PAIN_PLAIN = ("goi dau", "da dau", "dau tien", "bat dau", "o dau", "dau a", "dau vay", "dau the", "dau roi",
                  "dau goi", "dau nhe", "tinh dau", "dau tu", "cai dau", "dau oc")

CATEGORY_KEYWORDS: dict[str, tuple[str, str, str]] = {
    "goi dau": ("cat:goi_dau", "gội đầu", "hair"),
    "goi thao duoc": ("cat:goi_dau", "gội đầu", "hair"),
    "goi duoc lieu": ("cat:goi_dau", "gội đầu", "hair"),
    "goi dau duong sinh": ("cat:goi_dau", "gội đầu", "hair"),
    "massage": ("cat:massage", "massage", "relaxation"),
    "masage": ("cat:massage", "massage", "relaxation"),
    "mat xa": ("cat:massage", "massage", "relaxation"),
    "matxa": ("cat:massage", "massage", "relaxation"),
    "xoa bop": ("cat:massage", "massage", "relaxation"),
    "facial": ("cat:cham_soc_da", "chăm sóc da", "skin"),
    "cham soc da": ("cat:cham_soc_da", "chăm sóc da", "skin"),
    "cham soc da mat": ("cat:cham_soc_da", "chăm sóc da", "skin"),
    "skincare": ("cat:cham_soc_da", "chăm sóc da", "skin"),
    "nan mun": ("cat:da_mun", "chăm sóc da mụn", "skin"),
    "lay mun": ("cat:da_mun", "chăm sóc da mụn", "skin"),
    "tri mun": ("cat:da_mun", "chăm sóc da mụn", "skin"),
    "da mun": ("cat:da_mun", "chăm sóc da mụn", "skin"),
    "xoa tham": ("cat:quang_mat", "xóa thâm quầng mắt", "skin"),
    "quang mat": ("cat:quang_mat", "xóa thâm quầng mắt", "skin"),
    "tham mat": ("cat:quang_mat", "xóa thâm quầng mắt", "skin"),
    "dien chan": ("cat:dien_chan", "diện chẩn, ấn huyệt", "health"),
    "an huyet": ("cat:dien_chan", "diện chẩn, ấn huyệt", "health"),
    "giac hoi": ("cat:dien_chan", "diện chẩn, ấn huyệt", "health"),
    "ho ngai": ("cat:dien_chan", "diện chẩn, ấn huyệt", "health"),
    "yoni": ("cat:yoni", "chăm sóc vùng kín", "women"),
    "vung kin": ("cat:yoni", "chăm sóc vùng kín", "women"),
}
EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "massage-chan": ("massage chan", "mat xa chan", "masage chan", "xoa bop chan"),
    "massage-co-vai-gay": ("massage co vai gay", "massage vai gay", "massage co vai", "mat xa vai gay",
                           "massage vai co gay", "massage co gay"),
    "massage-body-thu-gian": ("massage body", "massage toan than", "mat xa body", "body thu gian",
                              "mat xa toan than"),
    "goi-dau-thu-gian": ("goi dau thu gian",),
    "detox-da-dau": ("detox da dau",),
    "cham-soc-nan-toc": ("cham soc nan toc", "cham soc toc"),
    "goi-mun-5-in-1": ("mun 5 in 1", "5 in 1"),
    "se-khit-lam-hong-yoni": ("se khit",),
    "yoni-retreat": ("yoni retreat",),
}
GENERIC_PARTS = {"goi co ban", "goi cong nghe dien xung truong", "cham soc", "goi"}

FAMILY_NAMES = {"nguyen", "tran", "le", "pham", "hoang", "huynh", "phan", "vu", "vo", "dang", "bui", "do", "ho",
                "ngo", "duong", "ly", "truong", "dinh", "lam", "mai", "trinh", "dao", "cao", "luu", "ha", "ta", "kieu",
                "quach", "luong", "to", "thai", "chu", "lai", "van", "tang", "la", "doan", "khuc", "giang", "han"}
# Family names that are rarely given names (as written; "Ly", "Mai", "Hà", "Giang" are common given names).
FAMILY_ONLY_ORIG = {"nguyễn", "trần", "lê", "phạm", "huỳnh", "phan", "võ", "đặng", "bùi", "đỗ", "ngô", "lý", "lưu",
                    "tạ", "kiều", "quách", "lại", "đoàn", "khúc", "nguyen", "pham", "huynh", "quach", "bui"}
# Kinship prefixes of a display name, as written (lowercased, dot removed). The full words "Anh" and "Chi" are left out:
# they are common given names ("Anh Thư", "Chi Nguyễn"); "Chị", "C", "Cj", "A" are not.
NAME_PREFIX = {"chị": "chị", "c": "chị", "cj": "chị", "chj": "chị", "a": "anh", "cô": "cô", "chú": "chú",
               "bác": "bác", "em": "em", "e": "em"}
# A display name that starts with one of these is a nickname or an alias for someone else ("Mẹ Bống" is the mother of
# Bống, "Bé Su", "Vợ iu"): no name to use.
NICKNAME_FIRST = {"mẹ", "má", "ba", "bố", "mama", "papa", "bé", "vợ", "chồng", "ck", "vk", "ox", "bx", "ny", "con",
                  "me", "bo", "be", "mommy", "daddy"}
NAME_STOP = {"oi", "a", "nhe", "em", "anh", "chi", "co", "chu", "bac", "con", "chau", "minh", "ban", "toi", "be",
             "me", "ba", "bo", "vo", "chong", "ck", "vk"}
# Decoration of a display name, removed before the name is read ("Vy girl phố", "Lan Spa", "Lan 0909", "🌸 Lan 🌸");
# emoji, digits and punctuation are removed too. Compared lowercased as written; the ASCII words also in a plain name.
NAME_DECOR = {"girl", "boy", "phố", "xinh", "cute", "kute", "cutie", "mr", "mrs", "ms", "miss", "baby", "bae", "iu",
              "real", "đẹp", "official", "shop", "spa", "store", "nail", "nails", "oa", "beauty", "salon", "studio",
              "online", "khách", "quen", "vip", "ctv", "kh", "sđt", "sdt", "mới", "quận", "huyện", "phường", "tp", "hcm",
              "tphcm", "sg", "hn", "q", "vấp", "pro"}
NAME_DECOR_PLAIN = {"girl", "boy", "pho", "xinh", "cute", "kute", "cutie", "mr", "mrs", "ms", "miss", "baby", "bae",
                    "iu", "real", "official", "shop", "spa", "store", "nail", "nails", "oa", "beauty", "salon", "studio",
                    "online", "khach", "quen", "vip", "ctv", "kh", "sdt", "tp", "hcm", "tphcm", "sg", "hn", "q", "vap",
                    "pro"}
# A display name with one of these is a business or a service account, not a person: no name.
NAME_BUSINESS = {"cty", "company", "shopee", "lazada", "tiki", "mart", "kho", "order", "sale", "fashion", "boutique",
                 "cafe", "coffee", "quán", "tiệm", "dịch", "zalo", "bank", "admin", "page", "media", "agency", "food",
                 "tea", "milk", "group", "clinic", "care", "hair", "house", "bot"}
NAME_BUSINESS_PLAIN = {"cty", "company", "shopee", "lazada", "tiki", "mart", "order", "sale", "fashion", "boutique",
                       "cafe", "coffee", "zalo", "bank", "admin", "page", "media", "agency", "food", "tea", "milk",
                       "group", "clinic", "care", "hair", "house", "bot"}
# Common Vietnamese given names (as written). A display name reduced to one word is used only when it is one of these
# ("Vy", "Lan"); "Bống", "Su", "Bin" are nicknames.
GIVEN_NAMES = set("""
an anh ánh ái bích châu chi cúc dung duyên diệp diễm đào gấm giang hà hạ hải hạnh hằng hân hậu hiền hiên hoa hòa hoà
hồng huệ hương hường huyền khanh khánh khuê kiều kim lam lan liên lệ linh loan ly lý mai my mỹ mơ nga ngà ngân ngọc
nguyệt nhàn nhã nhi nhung như nhiên oanh phương phượng quyên quỳnh quế sương sen tâm thảo thanh thắm thơ thu thư thủy
thuỷ thùy thuỳ thy tiên trang trâm trân trinh trúc tuyết tuyền uyên vân vi vy xuân yến thoa trà tú hoài thục thương
bảo bình cường công chiến chính danh dũng duy dương đạt đức định đông hào hiếu hiệp hoàng hùng huy hưng khang khải
khoa khôi kiên lâm lộc long luân lực mạnh minh nam nghĩa nguyên nhân nhật phát phong phú phúc phước quang quân quốc
quý sang sơn tài tân thái thắng thành thiện thịnh thông tiến toàn trí trọng trung trường tuấn tùng việt vinh vũ vương
đăng khoa lợi nhựt tín thuận triều uy vĩ vỹ hiển hòa thạch tường thắng hậu nhung ngân
""".split())
GIVEN_NAMES_PLAIN = {fold(n) for n in GIVEN_NAMES}


def _phrase_re(phrases: Iterable[str]) -> re.Pattern:
    alts = sorted({p for p in phrases if p}, key=len, reverse=True)
    return re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(p) for p in alts) + r")(?![^\W_])")


SERVICE_RE = _phrase_re(SERVICE_PHRASES)
SERVICE_WEAK_RE = _phrase_re(SERVICE_WEAK_PHRASES)
SERVICE_WEAK_ORIG_RE = _phrase_re(SERVICE_WEAK_ORIG)
BOOKING_RE = _phrase_re(BOOKING_PHRASES)
BOOKING_WEAK_RE = _phrase_re(BOOKING_WEAK_PHRASES)
BOOKING_WEAK_ORIG_RE = _phrase_re(BOOKING_WEAK_ORIG)
PAST_TIME_RE = _phrase_re(PAST_TIME_PHRASES)
PAST_VISIT_RE = _phrase_re(PAST_VISIT_PHRASES)
PAST_ORIG_RE = _phrase_re(PAST_USE_ORIG)
NOT_PAIN_RE = _phrase_re(NOT_PAIN_PLAIN)
CHITCHAT_RE = _phrase_re(PERSONAL_CHITCHAT)
CHITCHAT_ORIG_RE = _phrase_re(PERSONAL_CHITCHAT_ORIG)
HEALTH_PLAIN_RE = _phrase_re(HEALTH_PLAIN)
HEALTH_ORIG_RE = _phrase_re(HEALTH_ORIG)
INSIDER_ORIG_RE = _phrase_re(INSIDER_ORIG)
INSIDER_PLAIN_RE = _phrase_re(fold(p) for p in INSIDER_ORIG)
INSIDER_WEAK_ORIG_RE = _phrase_re(INSIDER_WEAK_ORIG)
INSIDER_WEAK_PLAIN_RE = _phrase_re(fold(p) for p in INSIDER_WEAK_ORIG if fold(p) != "luong")  # "lượng" is not pay
NON_CATALOG_RE = _phrase_re(NON_CATALOG_PHRASES)


# ---------------------------------------------------------------- catalog


@dataclass
class Catalog:
    regex: re.Pattern | None
    targets: dict[str, tuple[str, str | None, str, str]]   # alias -> (key, service_id, name, group)

    def find(self, bare: str) -> list[tuple[int, str, str | None, str, str]]:
        if not self.regex:
            return []
        out = []
        for m in self.regex.finditer(bare):
            key, sid, name, group = self.targets[m.group(0)]
            out.append((m.start(), key, sid, name, group))
        return out


def _norm_phrase(s: str) -> str:
    return " ".join(TOKEN_RE.findall(fold(nfc_lower(s))))


def load_catalog(path: Path) -> Catalog:
    try:
        services = json.loads(path.read_text(encoding="utf-8")).get("services") or []
    except (OSError, ValueError):
        services = []
    alias_to: dict[str, set[str]] = defaultdict(set)
    info: dict[str, tuple[str, str]] = {}
    for s in services:
        sid = str(s.get("id") or s.get("service_id") or "")
        name = str(s.get("display_name_vi") or s.get("name_vi") or "")
        group = str(s.get("group") or s.get("group_code") or "")
        if not sid or not name:
            continue
        info[sid] = (name, group)
        main, _, rest = name.partition("(")
        cands = {main, rest.rstrip(")"), sid.replace("-", " ")}
        parts = re.split(r"\s[–—-]\s|[–—]", main)
        if len(parts) > 1:
            cands.update(parts)
        cands.update(EXTRA_ALIASES.get(sid, ()))
        for c in cands:
            p = _norm_phrase(c)
            if len(p.split()) >= 2 and p not in GENERIC_PARTS:
                alias_to[p].add(sid)
    targets: dict[str, tuple[str, str | None, str, str]] = {}
    for alias, sids in alias_to.items():
        if len(sids) == 1:
            sid = next(iter(sids))
            targets[alias] = (sid, sid, info[sid][0], info[sid][1])
    # A category counts only when the catalog has services of its group (no catalog, no categories).
    groups = {g for _n, g in info.values()}
    for kw, (key, label, group) in CATEGORY_KEYWORDS.items():
        if group in groups:
            targets.setdefault(kw, (key, None, label, group))
    regex = _phrase_re(targets) if targets else None
    return Catalog(regex, targets)


# ---------------------------------------------------------------- pronoun roles


def _term_of(t: Tok, plain_ok: bool) -> tuple[str | None, bool]:
    """(term, ambiguous) for a pronoun-like token, else (None, False). 'shop' stands for shop/ad/admin/spa."""
    if t.orig in STRONG:
        return STRONG[t.orig], False
    if t.orig in AMBIG_SHORT:
        return AMBIG_SHORT[t.orig], True
    if plain_ok and t.orig in AMBIG_PLAIN:
        return AMBIG_PLAIN[t.orig], True
    if t.bare in BUSINESS_ADDRESS and t.orig == t.bare:
        return "shop", True
    return None, False


def _is_name(t: Tok) -> bool:
    return len(t.cased) >= 2 and t.cased[0].isupper() and t.cased[1:].islower() and t.bare not in VERBS


def _next_index(toks: list[Tok], i: int) -> int:
    """Index of the token after position i, skipping one capitalized name ("chị Lan ơi")."""
    j = i + 1
    if j < len(toks) and _is_name(toks[j]) and j + 1 < len(toks):
        return j + 1
    return j


def _is_particle(t: Tok, plain_ok: bool) -> bool:
    if t.bare not in END_PARTICLES:
        return False
    if t.bare == "a":
        return t.orig in ("ạ", "à", "á", "ả") or plain_ok
    return True


def _in(t: Tok, orig_set: set[str], plain_set: set[str], plain_ok: bool) -> bool:
    return t.orig in orig_set or (plain_ok and t.orig in plain_set)


def _lead_end(toks: list[Tok], plain_ok: bool) -> int:
    """Index of the first token after leading particles (dạ, vâng, ok, hôm nay ...) and vocatives ("chị Lan ơi")."""
    lead, n = 0, len(toks)
    while lead < n:
        t = toks[lead]
        if _in(t, LEADS_ORIG, LEADS_PLAIN, plain_ok) or t.bare in VOCATIVE_NEXT:
            lead += 1
            continue
        j = _next_index(toks, lead)
        if j < n and toks[j].bare in VOCATIVE_NEXT:
            lead = j + 1
            continue
        break
    return lead


def _pron_at(toks: list[Tok], i: int, plain_ok: bool) -> tuple[str, bool] | None:
    """(term, ambiguous) when toks[i] is a pronoun of one of the two people, else None."""
    t = toks[i]
    if t.neutral:
        return None                                    # "anh/chị": neutral, neither person
    term, ambiguous = _term_of(t, plain_ok)
    if term is None:
        return None
    if i > 0 and t.cased[:1].isupper() and toks[i - 1].cased[:1].islower() and _term_of(toks[i - 1], plain_ok)[0]:
        return None                                    # "chị Anh ơi": Anh is the given name after a term
    if i + 1 < len(toks) and toks[i + 1].orig in NOT_PRONOUN_NEXT.get(t.orig, ()):
        return None                                    # "chú ý", "bác sĩ", "nội dung", "bà bầu"
    nxt_i = _next_index(toks, i)
    if nxt_i < len(toks) and toks[nxt_i].bare in FAMILY_FOLLOW:
        return None                                    # "anh trai", "em bé", "anh ấy": a third person
    if term in KIN_LIKE:
        if i + 1 < len(toks):
            n1 = toks[i + 1]
            if n1.orig in KIN_POSSESSOR_ORIG or (plain_ok and n1.orig in KIN_POSSESSOR_PLAIN):
                return None                            # "mẹ em", "con chị", "vợ anh", "ba mẹ": a relative of someone
        if i > 0 and toks[i - 1].orig in KIN_NOUN_PREV.get(term, ()):
            return None                                # "em bé", "con bé", "ông bà", "vợ chồng"
    return term, ambiguous


def _closing_particle(t: Tok, plain_ok: bool) -> bool:
    if t.bare == "a" and t.orig == "a":
        return plain_ok
    return _in(t, CLOSING_PARTICLE_ORIG, CLOSING_PARTICLE_PLAIN, plain_ok)


def _fixed_role(toks: list[Tok], i: int, ambiguous: bool, plain_ok: bool) -> tuple[str, int] | str | None:
    """Roles fixed by position: vocative, greeting/thanks, "dạ + PRON" closing, "nhé + PRON" closing, "bên + PRON".
    'skip' for a plain "a" in a greeting or closing position (as likely "ạ" as "anh")."""
    t = toks[i]
    n = len(toks)
    nxt_i = _next_index(toks, i)
    nxt = toks[nxt_i] if nxt_i < n else None
    prev = toks[i - 1] if i > 0 else None
    prev2 = toks[i - 2] if i > 1 else None
    if nxt is not None and nxt.bare in VOCATIVE_NEXT:
        return ("vocative", 2)
    if prev is not None and (prev.bare in GREET_PREV or (prev.bare == "on" and prev2 is not None and prev2.bare == "cam")):
        return "skip" if ambiguous and _is_particle(t, plain_ok) else ("addressee", 2)
    closing = all(_is_particle(x, plain_ok) for x in toks[i + 1:])
    if prev is not None and _in(prev, YES_ORIG, YES_PLAIN, plain_ok) and closing:
        return "skip" if ambiguous and _is_particle(t, plain_ok) else ("addressee", 2)
    if prev is not None and closing and i >= 2 and _closing_particle(prev, plain_ok):
        # "ngủ ngon nha con", "tối về sớm nhé mẹ": the reader, named after the closing particle
        return "skip" if ambiguous and _is_particle(t, plain_ok) else ("addressee", 1)
    if t.orig in VOCATIVE_ONLY_TERMS:
        return "skip"                                  # "ck" outside a vocative or greeting: chuyển khoản
    if prev is not None and _in(prev, SIDE_ORIG, SIDE_PLAIN, plain_ok) and not ambiguous:
        return ("side", 1)
    return None


SENIOR_SET = set(SENIOR)
JUNIOR_SET = set(JUNIOR)


def pronoun_hits(clause: Clause, plain_ok: bool, from_contact: bool | None = None) -> list[tuple[str, str, int]]:
    """(role, term, weight) per pronoun occurrence. role: 'self' (the writer, from a clear pattern), 'self_weak' (the
    writer, from word order only), 'addressee' (the other person) or 'side' ("bên em": the studio side, i.e. the
    owner's term whoever writes). from_contact: who wrote the clause (None: unknown, read like the contact)."""
    toks = clause.toks
    n = len(toks)
    hits: list[tuple[str, str, int]] = []
    if not n:
        return hits
    last_real = n - 1
    while last_real > 0 and _is_particle(toks[last_real], plain_ok):
        last_real -= 1
    imperative = toks[-1].bare in IMPERATIVE_END
    question = clause.question or toks[last_real].bare in QUESTION_END
    lead = _lead_end(toks, plain_ok)
    prons = [_pron_at(toks, i, plain_ok) for i in range(n)]
    fixed = [(_fixed_role(toks, i, p[1], plain_ok) if p else None) for i, p in enumerate(prons)]
    seen_self: str | None = None
    first_pron_done = False
    consumed: set[int] = set()
    for i, t in enumerate(toks):
        if i in consumed:
            continue
        nxt_i = _next_index(toks, i)
        nxt = toks[nxt_i] if nxt_i < n else None
        if prons[i] is None:
            if not t.neutral and t.orig in VOCATIVE_ONLY_PLAIN and nxt is not None and nxt.bare in VOCATIVE_NEXT:
                hits.append(("addressee", VOCATIVE_ONLY_PLAIN[t.orig], 2))
            continue
        term, ambiguous = prons[i]
        prev = toks[i - 1] if i > 0 else None
        # 1-4: roles fixed by position (vocative, greeting, "dạ + PRON", "bên + PRON")
        f = fixed[i]
        if f == "skip":
            first_pron_done = True
            continue
        if f is not None:
            role, w = f
            hits.append(("addressee" if role == "vocative" else role, term, w))
            if role != "vocative":
                first_pron_done = True
            continue
        # 5. right after a request word that opens the clause ("cho em hỏi", "để em xem")
        if prev is not None and i - 1 == lead and _in(prev, REQUEST_ORIG, REQUEST_PLAIN, plain_ok):
            if not seen_self and term != "shop":
                hits.append(("self", term, 1))
                seen_self = term
            first_pron_done = True
            continue
        if not first_pron_done and i == lead:
            first_pron_done = True
            verb_ok = nxt is not None and not _is_particle(nxt, plain_ok) and \
                (not ambiguous or nxt.bare in VERBS or _in(nxt, FAVOR_ORIG, FAVOR_PLAIN, plain_ok))
            self_verb = nxt is not None and nxt.bare in SELF_VERBS
            # a second pronoun of the other person later in the clause (kin terms there are mostly a third person:
            # "chị muốn đặt cho mẹ")
            partner = None
            if term in RULE6_TERMS:
                for j in range(i + 2, n):
                    if prons[j] and fixed[j] is None and prons[j][0] != term and prons[j][0] in RULE6_TERMS:
                        partner = j
                        break
            if partner is not None and verb_ok and nxt.bare not in SELF_VERBS_STRONG:
                term2 = prons[partner][0]
                favor = _in(toks[partner - 1], FAVOR_ORIG, FAVOR_PLAIN, plain_ok)
                # Reading PRON1 as the owner (addressed) in the contact's messages can only give the contact a junior
                # self-term, which ends in the neutral "anh/chị". In the owner's messages the same reading would give
                # the contact the owner's own term (a man writing "anh gửi em ..." would make the contact "anh"), so
                # the owner's ambiguous clauses are not counted.
                if favor:
                    # 6a. "anh xem giúp em", "chị cho em hỏi": PRON2 is who the favour is for. A contact asks the
                    # studio; the owner offers with a junior PRON1 ("em xem giúp chị nhé"), while a senior PRON1 from
                    # the owner ("chị gửi giúp em ảnh") may be an offer or a request.
                    if from_contact is not False:
                        hits += [("addressee", term, 1), ("self", term2, 1)]
                        seen_self = term2
                    elif term not in SENIOR_SET:
                        hits += [("self", term, 1), ("addressee", term2, 1)]
                        seen_self = term
                    consumed.add(partner)
                    continue
                if not question and term in SENIOR_SET and term2 in JUNIOR_SET:
                    # 6b. "anh báo giá em ...", "chị gửi em địa chỉ": from the contact, a request to the owner.
                    if from_contact is not False:
                        hits += [("addressee", term, 1), ("self_weak", term2, 1)]
                        seen_self = term2
                    consumed.add(partner)
                    continue
            # 7. subject of a statement
            if question or imperative or not verb_ok:
                continue
            if term in SENIOR_SET and _in(nxt, ASK_VERBS_ORIG, ASK_VERBS_PLAIN, plain_ok):
                continue   # "anh xem lịch thứ 7": "you check" as likely as "I check"
            if term in ELDER_PEER_TERMS:
                continue   # "bà nói đúng": "you" between friends, "I" from a grandmother
            role = "self" if (term not in SENIOR_SET or self_verb) else "self_weak"
            hits.append((role, term, 1))
            seen_self = term
            continue
        first_pron_done = True
        # 8. later pronoun of another term in the same clause. A kin term counts only as the answer to a kin self-term
        # ("con nhớ mẹ", "mẹ thương con"): after any other self-term it is a third person ("chị đặt lịch cho mẹ").
        if not seen_self or term == seen_self or term == "shop":
            continue
        kin_pair = (seen_self in KIN_ELDER and term in KIN_JUNIOR) or (seen_self in KIN_JUNIOR and term in KIN_ELDER)
        if term in KIN_LIKE - CHILD_TERMS or (term in CHILD_TERMS and seen_self in KIN_ELDER):
            if not kin_pair:
                continue
            if ambiguous and not (nxt is None or nxt.bare in VERBS or _is_particle(nxt, plain_ok)):
                continue   # "mẹ mua con cá": a classifier
            hits.append(("addressee", term, 1))
        elif not ambiguous:
            hits.append(("addressee", term, 1))
    return hits


def pronoun_uses(clause: Clause, plain_ok: bool) -> Counter:
    """Every occurrence of an address term in a pronoun position, whatever its role (the measure behind "kinship
    dominates"). An ambiguous token needs a verb, a particle, "ơi" or the clause end after it ("ba đi làm", "con ơi"),
    or a greeting / "dạ" / request word before it; "ck" only as a vocative or after a greeting."""
    toks = clause.toks
    n = len(toks)
    out: Counter = Counter()
    for i in range(n):
        p = _pron_at(toks, i, plain_ok)
        if p is None or p[0] == "shop":
            continue
        term, ambiguous = p
        nxt_i = _next_index(toks, i)
        nxt = toks[nxt_i] if nxt_i < n else None
        prev = toks[i - 1] if i > 0 else None
        vocative = nxt is not None and nxt.bare in VOCATIVE_NEXT
        greeted = prev is not None and (prev.bare in GREET_PREV or _in(prev, YES_ORIG, YES_PLAIN, plain_ok))
        if term in VOCATIVE_ONLY_TERMS and not (vocative or greeted):
            continue
        if ambiguous:
            if _is_particle(toks[i], plain_ok):
                ok = vocative or (nxt is not None and nxt.bare in VERBS)   # "a" is as often "ạ"
            else:
                ok = (nxt is None or vocative or nxt.bare in VERBS or _is_particle(nxt, plain_ok) or greeted or
                      (prev is not None and _in(prev, REQUEST_ORIG, REQUEST_PLAIN, plain_ok)))
            if not ok:
                continue
        out[term] += 1
    return out


# ---------------------------------------------------------------- per-thread analysis


@dataclass
class Msg:
    sender: str
    name: str
    text: str
    ts: int
    type: str


@dataclass
class ServiceAcc:
    key: str
    service_id: str | None
    name: str
    group: str
    mention_count: int = 0
    last_mentioned_at: int | None = None
    used_signal_count: int = 0
    last_used_signal_at: int | None = None
    direct_used_count: int = 0          # past-use signals in the message that names the service ("lần trước chị làm X")
    last_signal_direct: bool = False    # the latest signal named the service itself (not the 72-hour window)


@dataclass
class ThreadResult:
    profile: dict[str, Any]
    counts: dict[str, int] = field(default_factory=dict)


def mask_digits(s: str) -> str:
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "•••", s)
    return re.sub(r"\+?\d[\d .\-]{4,}\d", lambda m: "•••" if sum(ch.isdigit() for ch in m.group(0)) >= 7 else m.group(0), s)


def snippet(text: str, pos: int) -> str:
    flat = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()
    pos = min(max(0, pos), len(flat))
    flat = mask_digits(flat)
    if len(flat) <= SNIPPET_MAX:
        return flat
    start = max(0, min(pos - 30, len(flat) - (SNIPPET_MAX - 1)))
    body = flat[start:start + SNIPPET_MAX - 2]
    out = ("…" if start > 0 else "") + body.strip()
    if start + len(body) < len(flat):
        out = out[:SNIPPET_MAX - 1].rstrip() + "…"
    return out[:SNIPPET_MAX]


def has_health(low: str, bare: str) -> bool:
    """Health vocabulary as written with diacritics, and the plain spellings wherever at least one word of the match
    is written without diacritics, also in a message that has diacritics elsewhere ("em bi dau lung lắm"). Words
    written with diacritics are left to the first check ("đầu" is not "đau"). Over-matching on purpose: a skipped
    snippet costs nothing. low and bare must be aligned character by character (bare = fold(low))."""
    if HEALTH_ORIG_RE.search(low):
        return True
    cleaned = NOT_PAIN_RE.sub(lambda m: " " * len(m.group(0)), bare)
    for m in HEALTH_PLAIN_RE.finditer(cleaned):
        if any(not has_marks(w) for w in TOKEN_RE.findall(low[m.start():m.end()])):
            return True
    return False


def _inquiry_near(low: str, start: int, end: int, plain_ok: bool) -> bool:
    """An inquiry verb (hỏi, xem, nhắn, báo ...) within 4 words after or 3 words before low[start:end]."""
    def hit(w: str) -> bool:
        return w in INQUIRY_ORIG or (plain_ok and fold(w) in INQUIRY_PLAIN)
    after = TOKEN_RE.findall(low[end:])[:4]
    before = TOKEN_RE.findall(low[:start])[-3:]
    return any(hit(w) for w in after + before)


def has_visit_time(low: str, bare: str, plain_ok: bool) -> bool:
    """"mai chị qua", "3h em ghé": a visit verb and a time in the same message ("hôm qua" is not a visit)."""
    words = TOKEN_RE.findall(low)
    verb = False
    for k, w in enumerate(words):
        if w in VISIT_VERB_ORIG or (plain_ok and fold(w) in VISIT_VERB_PLAIN):
            if not (k > 0 and fold(words[k - 1]) in ("hom", "bua") and fold(w) == "qua"):
                verb = True
                break
    if not verb:
        return False
    return bool(VISIT_TIME_ORIG_RE.search(low)) or (plain_ok and bool(VISIT_TIME_PLAIN_RE.search(bare)))


def local_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, TZ_VN).strftime("%Y-%m-%d")


def recommend(owner_calls: Counter, self_terms: Counter, calls_owner: Counter, owner_self: Counter,
              name_prefix: str | None, self_sure: Counter | None = None,
              gender: str | None = None) -> tuple[str, str, dict[str, Any]]:
    """(address_term, confidence, basis). self_sure: the part of self_terms that comes from clear patterns ("cho chị
    hỏi", "chị muốn ...", "anh cảm ơn ..."), not from word order alone. gender: 'female' / 'male' from the display name
    ("Thị" / "Văn"), used only for an elder without a gendered term."""
    self_terms = Counter(self_terms)
    self_sure = Counter(self_sure if self_sure is not None else self_terms)
    calls_owner = Counter(calls_owner)
    # The contact cannot be X and call the owner X too: the weaker side of such a pair is dropped (a tie drops the
    # self-term, the side more often misread from word order).
    dropped = []
    for t in set(self_terms) & set(calls_owner):
        if self_terms[t] > 0 and calls_owner[t] > 0:
            if self_terms[t] <= calls_owner[t]:
                self_terms[t] = 0
                self_sure[t] = 0
            else:
                calls_owner[t] = 0
            dropped.append(t)
    direct = Counter()
    for t in SENIOR:
        # a senior self-term from word order alone ("chị đau lưng") weighs half
        own = self_sure[t] + 0.5 * max(0, self_terms[t] - self_sure[t])
        direct[t] = owner_calls[t] + own + (1 if name_prefix == t else 0)
    junior_direct = sum(owner_calls[t] + self_terms[t] for t in JUNIOR) + (1 if name_prefix in JUNIOR else 0)
    junior_inferred = sum(owner_self[t] + calls_owner[t] for t in SENIOR)
    senior_inferred = owner_self["em"] + calls_owner["em"]
    total = sum(direct.values()) + junior_direct
    best, best_w = (direct.most_common(1)[0] if total else (None, 0))
    basis = {"senior_direct": dict(+direct), "junior_direct": junior_direct, "junior_inferred": junior_inferred,
             "senior_inferred": senior_inferred}
    if dropped:
        basis["conflicting_terms"] = sorted(dropped)
    # The owner calls themselves con/cháu, or the contact calls the owner con/cháu: the contact is an elder.
    elder_inferred = sum(owner_self[t] + calls_owner[t] for t in CHILD_TERMS)
    if elder_inferred:
        basis["elder_inferred"] = elder_inferred
    if best and best_w > 0 and best_w >= junior_direct:
        share = best_w / total if total else 0
        conf = "high" if best_w >= 4 and share >= 0.8 else "medium" if best_w >= 2 and share >= 0.6 else "low"
        return best, conf, basis
    if elder_inferred >= 2 and elder_inferred > junior_direct + junior_inferred:
        # cô/chú/bác: "bác" when the owner calls them ông/bà, else the display name's gender ("Thị" cô, "Văn" chú);
        # without a cue the neutral "anh/chị" (staff picks cô or chú in the console)
        if owner_calls["ông"] + owner_calls["bà"] > 0:
            term = "bác"
        else:
            term = {"female": "cô", "male": "chú"}.get(gender or "")
        if term:
            basis["elder_term_from"] = "ong_ba" if term == "bác" else "display_name"
            return term, ("medium" if elder_inferred >= 3 else "low"), basis
        basis["elder_without_gender"] = True
        return "anh/chị", "low", basis
    if junior_direct > 0 or junior_inferred > senior_inferred:
        # The owner calls the contact em/con/cháu: only a self-term from a clear pattern says anh or chị.
        own = Counter({t: self_sure[t] for t in ("anh", "chị")})
        term, w = (own.most_common(1)[0] if sum(own.values()) else (None, 0))
        if term and w > 0 and own[("chị" if term == "anh" else "anh")] == 0:
            return term, ("medium" if w >= 2 else "low"), basis
        weight = junior_direct + junior_inferred
        return "anh/chị", ("medium" if weight >= 3 else "low"), basis
    return "anh/chị", "low", basis


def name_words(display: str | None) -> list[str]:
    """The display name's words with emoji, digits and punctuation removed (letters only, original case)."""
    if not display:
        return []
    out = []
    for w in unicodedata.normalize("NFC", display).split():
        letters = "".join(ch for ch in w if ch.isalpha())
        if letters:
            out.append(letters)
    return out


def given_name(display: str | None) -> tuple[str | None, str | None]:
    """(name_to_use, name_prefix_term) from the display name. Decoration (girl, phố, xinh, spa, shop, emoji, digits,
    "khách quen", a district) is removed first; a kinship prefix ("Chị", "C.", "A.", "Em", "Cô", "Chú") gives the term.
    The given name is the last word, used only when what is left looks like a Vietnamese personal name: one word after
    a prefix, one common given name alone ("Vy", "Lan"), or 2-5 words in family-first order."""
    words = name_words(display)
    if not words:
        return None, None
    plain_name = not has_marks(" ".join(words))
    low = [nfc_lower(w) for w in words]
    if any(w in NAME_BUSINESS or (plain_name and w in NAME_BUSINESS_PLAIN) for w in low) or \
            any(w in NAME_BUSINESS_PLAIN and w.isascii() and len(w) > 3 for w in low):
        return None, None                      # "Kho Sỉ Mỹ Phẩm", "Lan Cafe": a business
    if low[0] in NICKNAME_FIRST:
        return None, None                      # "Mẹ Bống", "Bé Su": an alias, and the name is someone else's
    prefix = NAME_PREFIX.get(low[0])
    rest = words[1:] if prefix else words
    rest = [w for w in rest if not (nfc_lower(w) in NAME_DECOR or (plain_name and nfc_lower(w) in NAME_DECOR_PLAIN))]
    if not rest or len(rest) > 5:
        return None, prefix
    if prefix and len(rest) != 1:
        return None, prefix                    # "Chị Lan Gò Vấp": more than a given name after the prefix
    folded = [fold(nfc_lower(w)) for w in rest]
    if not prefix and len(rest) == 1:
        w = nfc_lower(rest[0])
        if not (w in GIVEN_NAMES or (plain_name and w in GIVEN_NAMES_PLAIN)):
            return None, prefix                # "Bống": a nickname
    elif not prefix:
        if not (has_marks(" ".join(rest)) or folded[0] in FAMILY_NAMES):
            return None, prefix
        if folded[-1] in FAMILY_NAMES and folded[0] not in FAMILY_NAMES:
            return None, prefix                # "Minh Hoàng", "Lan Nguyen": given name first, or unclear
    last = rest[-1]
    lf = folded[-1]
    if nfc_lower(last) in FAMILY_ONLY_ORIG:
        return None, prefix                    # "Chị Nguyễn", "Hoa Lê": a family name, not a given name
    if lf in NAME_STOP or not (2 <= len(last) <= 7) or not re.search(r"[aeiouy]", lf):
        return None, prefix
    return last[0].upper() + last[1:].lower(), prefix


def name_gender(display: str | None) -> str | None:
    """'female' for a middle "Thị", 'male' for a middle "Văn" (plain "Thi"/"Van" only in a diacritic-free name)."""
    words = [nfc_lower(w) for w in name_words(display)]
    if len(words) < 3:
        middle = words[:-1] if len(words) == 2 else []
    else:
        middle = words[1:-1]
    plain = not has_marks(" ".join(words))
    if "thị" in middle or (plain and "thi" in middle):
        return "female"
    if "văn" in middle or (plain and "van" in middle):
        return "male"
    return None


# A thread name that is only a family word ("Mẹ", "Ba", "Vợ iu", "Chồng yêu", "Bà ngoại"): the owner saved a relative.
FAMILY_NAME_CORE = {"mẹ", "má", "ba", "bố", "cha", "vợ", "chồng", "ck", "vk", "ox", "bx", "nội", "ngoại", "dì",
                    "dượng", "mợ", "thím", "mommy", "daddy", "mama", "papa"}
FAMILY_NAME_EXTRA = {"yêu", "iu", "của", "con", "em", "anh", "tôi", "mình", "ơi", "ông", "bà", "hai", "ba", "tư", "út"}


def family_display_name(display: str | None) -> bool:
    words = [nfc_lower(w) for w in name_words(display)]
    return bool(words) and len(words) <= 4 and any(w in FAMILY_NAME_CORE for w in words) and \
        all(w in FAMILY_NAME_CORE or w in FAMILY_NAME_EXTRA for w in words)


def insider_of(low: str, bare: str, plain_ok: bool) -> tuple[bool, bool]:
    """(strong, weak): shop operations seen from the inside ("ca làm", "chấm công", "khách đặt", "có khách"), and
    everyday words that also fit an insider ("đi làm", "tới tiệm", "mở cửa")."""
    strong = bool(INSIDER_ORIG_RE.search(low)) or bool(KHACH_RE.search(bare)) or \
        (plain_ok and bool(INSIDER_PLAIN_RE.search(bare)))
    weak = not strong and (bool(INSIDER_WEAK_ORIG_RE.search(low)) or
                           (plain_ok and bool(INSIDER_WEAK_PLAIN_RE.search(bare))))
    return strong, weak


def is_instruction(low: str) -> bool:
    """The owner telling someone what to do: "giùm", "nhớ", "đừng" ..., or a closing "nha/nhé/đi"."""
    words = TOKEN_RE.findall(low)
    if not words:
        return False
    return any(w in INSTRUCTION_ORIG for w in words) or fold(words[-1]) in IMPERATIVE_END


FAMILY_ENDEAR_RE = re.compile(r"(?<![^\W_])(?:con|me|ba|bo) (?:yeu|iu)(?! cau)(?! thich)(?![^\W_])")
COUPLE_TOKENS = {"vk", "ox", "bx", "ny"}
KIN_POSSESSOR_BARE = {"em", "e", "anh", "chi", "c", "toi", "minh", "mk", "tui", "tao", "may", "ban", "cua"}


def last_service_of(services: dict[str, ServiceAcc]) -> dict[str, Any] | None:
    """The most recent likely_used service: {key, service_id, name, at, source 'chat', confidence, sensitive}.
    Confidence: high after two or more signals naming the service in the same message, medium when the latest signal
    named it (or an earlier one did), low when it comes only from the 72-hour window around a visit phrase."""
    best: tuple[tuple[int, int], ServiceAcc] | None = None
    for acc in services.values():
        if not acc.last_used_signal_at:
            continue
        rank = (acc.last_used_signal_at, 1 if acc.service_id else 0)
        if best is None or rank > best[0]:
            best = (rank, acc)
    if best is None:
        return None
    acc = best[1]
    if acc.last_signal_direct:
        conf = "high" if acc.direct_used_count >= 2 else "medium"
    else:
        conf = "medium" if acc.direct_used_count >= 1 else "low"
    return {"key": acc.key, "service_id": acc.service_id, "name": acc.name, "at": acc.last_used_signal_at,
            "source": "chat", "confidence": conf, "sensitive": acc.group in SENSITIVE_GROUPS}


def analyze_thread(thread_id: str, thread_name: str | None, msgs: list[Msg], catalog: Catalog) -> ThreadResult:
    contact_msgs = [m for m in msgs if m.sender == thread_id]
    owner_msgs = [m for m in msgs if m.sender != thread_id]
    latest_in_name = next((m.name for m in reversed(contact_msgs) if m.name), None)
    display = (thread_name or "").strip() or latest_in_name or None
    name_to_use, name_prefix = given_name(display)
    gender = name_gender(display)
    kin_name = family_display_name(display)

    owner_calls, self_terms, calls_owner, owner_self, self_sure = Counter(), Counter(), Counter(), Counter(), Counter()
    use_owner, use_contact = Counter(), Counter()     # every address term in a pronoun position, per side
    services: dict[str, ServiceAcc] = {}
    mention_log: list[tuple[int, str]] = []
    cust = {"service": 0, "weak": 0, "booking": 0, "price": 0, "catalog": 0, "business": 0, "visit": 0,
            "owner_service": 0, "owner_business": 0, "deference": 0}
    pers = {"endearment": 0, "intimate": 0, "chitchat": 0, "couple": 0}
    ins = {"contact": 0, "contact_weak": 0, "owner": 0, "instruction": 0}
    evidence_cands: list[tuple[int, int, dict[str, Any]]] = []
    text_in = text_out = 0
    service_msgs = weak_msgs = booking_msgs = price_msgs = visit_msgs = personal_msgs = 0
    work_msgs = non_catalog_msgs = 0

    for m in msgs:
        if m.type not in TEXT_TYPES or not m.text or not m.text.strip():
            continue
        from_contact = m.sender == thread_id
        if from_contact:
            text_in += 1
        else:
            text_out += 1
        low = nfc_lower(unicodedata.normalize("NFC", m.text))
        bare = fold(low)
        clauses, marked = clauses_of(m.text)
        plain_ok = not marked
        senior_address = False
        for cl in clauses:
            for role, term, w in pronoun_hits(cl, plain_ok, from_contact):
                if term == "shop":
                    # the chat treats the owner as a business; from the owner's side ("shop em có ...") it is also
                    # what a promotion sent to every contact says, so only the contact's own use is a strong sign
                    cust["business" if from_contact else "owner_business"] += 1
                    continue
                if role == "side":          # "bên em": the owner's term, whoever writes
                    (calls_owner if from_contact else owner_self)[term] += w
                elif role in ("self", "self_weak"):
                    if from_contact:
                        self_terms[term] += w
                        if role == "self":
                            self_sure[term] += w
                    else:
                        owner_self[term] += w
                else:
                    (calls_owner if from_contact else owner_calls)[term] += w
                    if not from_contact and term in ("chị", "anh"):
                        senior_address = True
            (use_contact if from_contact else use_owner).update(pronoun_uses(cl, plain_ok))
        # the owner answering "dạ ..." and calling the contact chị/anh: the way a shop talks to a customer
        first_tok = next(iter(TOKEN_RE.findall(low)), "")
        if not from_contact and senior_address and (first_tok in DEFER_ORIG or (plain_ok and first_tok in DEFER_PLAIN)):
            cust["deference"] += 1
        # shop operations from the inside: the contact working there, or the owner instructing them
        ins_strong, ins_weak = insider_of(low, bare, plain_ok)
        if from_contact:
            if ins_strong:
                ins["contact"] += 1
            elif ins_weak:
                ins["contact_weak"] += 1
        elif ins_strong or ins_weak:
            ins["owner"] += 1 if ins_strong else 0
            if is_instruction(low):
                ins["instruction"] += 1
        # A message about the shop's own customers, shifts or pay is work talk: its services are not the contact's,
        # and its prices or bookings are not a purchase. A message naming only a service the studio does not offer
        # ("làm móng") is not customer vocabulary either.
        work = ins_strong
        hits = [] if work else catalog.find(bare)
        non_catalog = not work and not hits and bool(NON_CATALOG_RE.search(bare))
        work_msgs += work
        non_catalog_msgs += non_catalog
        strong = bkg = prc = weak_bkg = False
        if not work and not non_catalog:
            svc = bool(SERVICE_RE.search(bare)) or bool(hits)
            bkg = bool(BOOKING_RE.search(bare))
            prc = bool(PRICE_RE.search(low))
            weak = (bool(SERVICE_WEAK_RE.search(bare)) or bool(SERVICE_WEAK_ORIG_RE.search(low)) or
                    bool(BOOKING_WEAK_RE.search(bare)) or bool(BOOKING_WEAK_ORIG_RE.search(low)) or prc or
                    has_visit_time(low, bare, plain_ok))
            strong = svc or bkg
            weak_bkg = bool(BOOKING_WEAK_RE.search(bare)) or bool(BOOKING_WEAK_ORIG_RE.search(low))
            if strong:
                service_msgs += 1
                cust["service" if from_contact else "owner_service"] += 1
            elif weak:
                weak_msgs += 1
                if from_contact:
                    cust["weak"] += 1
            if from_contact and (bkg or (strong and weak_bkg)):
                cust["booking"] += 1
            if bkg or (strong and weak_bkg):
                booking_msgs += 1
            if prc:
                price_msgs += 1
                if from_contact:
                    cust["price"] += 1
        # personal signals: endearments of family ("con yêu"), a couple ("anh yêu", "vk ơi"), tao/mày, chit-chat
        toks = TOKEN_RE.findall(bare)
        endear = len(FAMILY_ENDEAR_RE.findall(bare))
        couple = len(COUPLE_RE.findall(bare)) + sum(
            1 for i, tk in enumerate(toks) if tk in COUPLE_TOKENS and not (i + 1 < len(toks) and toks[i + 1] in KIN_POSSESSOR_BARE))
        intimate = sum(1 for tk in TOKEN_RE.findall(low)
                       if tk in INTIMATE_ALWAYS or (tk in INTIMATE_MARKED_ONLY and not plain_ok))
        chit = len(CHITCHAT_RE.findall(bare)) + len(CHITCHAT_ORIG_RE.findall(low))
        if endear or couple or intimate or chit:
            personal_msgs += 1
        pers["endearment"] += endear
        pers["couple"] += couple
        pers["intimate"] += intimate
        pers["chitchat"] += chit
        if work or non_catalog:
            continue
        # services
        msg_keys: list[str] = []
        sensitive_here = False
        for _pos, key, sid, name, group in hits:
            acc = services.setdefault(key, ServiceAcc(key, sid, name, group))
            acc.mention_count += 1
            acc.last_mentioned_at = max(acc.last_mentioned_at or 0, m.ts)
            if sid and from_contact:
                cust["catalog"] += 1        # the owner naming services (a promotion) is owner_service
            if group in SENSITIVE_GROUPS:
                sensitive_here = True
            if key not in msg_keys:
                msg_keys.append(key)
        for key in msg_keys:
            mention_log.append((m.ts, key))
        # past use: a time phrase marks the services of this message only; a visit phrase (or the owner's thanks
        # for coming) also those of the previous 72 hours. Next to an inquiry verb neither counts.
        past_time = any(not _inquiry_near(low, x.start(), x.end(), plain_ok) for x in PAST_TIME_RE.finditer(bare))
        past_visit = any(not _inquiry_near(low, x.start(), x.end(), plain_ok)
                         for x in PAST_VISIT_RE.finditer(bare) if from_contact or x.group(0) not in CONTACT_ONLY_PAST)
        past_visit = past_visit or any(not _inquiry_near(low, x.start(), x.end(), plain_ok) for x in PAST_ORIG_RE.finditer(low))
        past_visit = past_visit or (not from_contact and bool(OWNER_VISIT_RE.search(bare)))
        if past_time or past_visit:
            visit_msgs += 1
            cust["visit"] += 1
            direct = bool(msg_keys)
            if msg_keys:
                targets = msg_keys
            elif past_visit:
                targets = sorted({k for ts, k in mention_log if m.ts - 3 * DAY_MS <= ts <= m.ts})
            else:
                targets = []
            for key in targets:
                acc = services[key]
                acc.used_signal_count += 1
                acc.direct_used_count += 1 if direct else 0
                if m.ts >= (acc.last_used_signal_at or 0):
                    acc.last_used_signal_at = m.ts
                    acc.last_signal_direct = direct
        # evidence candidates: messages with strong vocabulary or a service name only
        if strong and not sensitive_here and not has_health(low, bare):
            kind = "service" if hits else "booking" if (bkg or weak_bkg) else "price" if prc else "service"
            match_pos = hits[0][0] if hits else next(
                (r.search(bare).start() for r in (BOOKING_RE, SERVICE_RE) if r.search(bare)), 0)
            rank = (0 if from_contact else 2) + (0 if hits else 1)
            evidence_cands.append((rank, -m.ts, {"at": m.ts, "from": "contact" if from_contact else "owner",
                                                 "kind": kind, "text": snippet(m.text, match_pos)}))

    # ---- relationship (docstring "Relationship")
    total_text = text_in + text_out
    active_days = len({local_date(m.ts) for m in msgs})
    long_chat = total_text >= 30 and service_msgs <= max(1, total_text // 50)
    many_days = active_days >= 8 and service_msgs == 0
    purchase = cust["service"] + 0.5 * cust["weak"] + cust["business"]
    purchase_ratio = purchase / text_in if text_in else 0.0
    both = use_owner + use_contact
    peer_slang = min(both["tui"], both["ông"] + both["bà"]) + min(both["tớ"], both["cậu"])
    intimate = pers["intimate"] + peer_slang
    cust_score = (cust["service"] + 0.5 * cust["weak"] + 2 * cust["catalog"] + 3 * cust["business"] +
                  0.5 * cust["owner_service"] + cust["owner_business"] + min(3.0, 0.5 * cust["deference"]))
    pers_score = (min(6, 2 * intimate) + min(3, pers["chitchat"]) + (3 if long_chat else 0) + (2 if many_days else 0))

    # family: kinship address terms dominate the chat (both sides, any role); child terms count next to them
    kin_o = sum(use_owner[t] for t in FAMILY_TERMS)
    kin_c = sum(use_contact[t] for t in FAMILY_TERMS)
    child_use = sum(both[t] for t in CHILD_TERMS)
    nonkin = sum(both[t] for t in NONKIN_TERMS)
    couple_mode = pers["couple"] >= 2
    anh_em = both["anh"] + both["em"]
    kin_use = kin_o + kin_c + (anh_em if couple_mode else 0)
    if couple_mode:
        nonkin -= anh_em                    # a couple's anh/em is kinship, not a customer's
    grand = 0.5 * (both["ông"] + both["bà"]) if child_use >= 2 and peer_slang == 0 else 0
    family_points = (kin_use + min(child_use, kin_o + kin_c) + 3 * pers["couple"] + 2 * pers["endearment"] +
                     (4 if kin_name else 0) + grand)
    fam_ok = ((kin_o + kin_c >= 3 or kin_name or couple_mode) and family_points >= 6 and
              family_points >= 1.5 * nonkin)
    fam_high = fam_ok and family_points >= 12 and family_points >= 3 * nonkin and \
        ((kin_o > 0 and kin_c > 0) or kin_o + kin_c >= 10 or kin_name or pers["couple"] >= 3)
    elder_inferred = sum(owner_self[t] + calls_owner[t] for t in CHILD_TERMS)
    elder_terms = sum(owner_calls[t] + self_terms[t] for t in ("cô", "chú", "bác", "cậu", "ông", "bà", "dì"))
    elder_kin = elder_inferred >= 3 and elder_terms >= 2 and pers_score >= 3 and cust_score <= 1 and ins["contact"] == 0

    # staff: the contact talks about the shop as an insider and is the junior of the two (calls the owner chị/anh,
    # is called em/bé), or talks shop a lot whatever the pronouns
    junior = (owner_calls["em"] + owner_calls["bé"] + self_terms["em"] + self_terms["bé"] + calls_owner["chị"] +
              calls_owner["anh"] + owner_self["chị"] + owner_self["anh"])
    senior = sum(owner_calls[t] + self_terms[t] for t in SENIOR) + calls_owner["em"] + owner_self["em"]
    be_use = use_owner["bé"]
    staff_points = (2 * ins["contact"] + 0.5 * ins["contact_weak"] + ins["instruction"] + 0.5 * ins["owner"] +
                    (2 if be_use >= 2 else 0))
    staff_ok = (ins["contact"] >= 2 and staff_points >= 6 and staff_points >= 0.5 * cust_score and
                (junior > senior or (ins["contact"] >= 5 and staff_points >= 15)))
    staff_high = staff_ok and ins["contact"] >= 5 and staff_points >= 15 and junior >= 6 and junior >= 2 * senior \
        and staff_points >= cust_score
    staff_low = ins["contact"] >= 1 and staff_points >= 4 and junior > senior and staff_points >= cust_score

    # friend: a long personal chat, or tao/mày and chit-chat, with little buying and no insider talk
    long_personal = total_text >= 200 and active_days >= 10
    very_long = total_text >= 1000 or (total_text >= 400 and active_days >= 30)
    no_buy = cust["business"] == 0 and ins["contact"] < 2
    friend_high = no_buy and (
        (very_long and purchase_ratio < 0.03) or
        (long_personal and purchase_ratio < 0.03 and (intimate >= 2 or pers["chitchat"] >= 3)) or
        (intimate >= 2 and pers_score >= 6 and total_text >= 30 and cust["service"] == 0 and cust["catalog"] == 0
         and pers_score >= 3 * cust_score))
    friend_med = (long_personal and purchase_ratio < 0.08) or (pers_score >= 3 and pers_score >= 2 * cust_score)

    if cust_score == 0 and pers_score == 0 and family_points == 0 and staff_points == 0:
        rel, rel_conf = "unknown", "low"
    elif fam_ok:
        rel, rel_conf = "family", "high" if fam_high else "medium"
    elif staff_ok:
        rel, rel_conf = "staff", "high" if staff_high else "medium"
    elif elder_kin:
        rel, rel_conf = "family", "medium"
    elif friend_high:
        rel, rel_conf = "friend", "high"
    elif friend_med:
        rel, rel_conf = "friend", "medium"
    elif cust_score >= 6 and pers_score <= 1:
        rel, rel_conf = "customer", "high"
    elif cust_score >= 3 and cust_score >= 2 * pers_score:
        rel, rel_conf = "customer", "medium"
    elif staff_low:
        rel, rel_conf = "staff", "low"
    elif cust_score >= 1 and cust_score > pers_score:
        rel, rel_conf = "customer", "low"
    elif pers_score >= 1 and pers_score > cust_score:
        rel, rel_conf = "friend", "low"
    elif family_points >= 3 and family_points > cust_score:
        rel, rel_conf = "family", "low"
    else:
        rel, rel_conf = "unknown", "low"

    reasons: list[str] = []
    if rel == "family":
        parent = (sum(owner_calls[t] + self_terms[t] for t in PARENT_TERMS) + elder_inferred)
        child = (sum(calls_owner[t] + owner_self[t] for t in PARENT_TERMS) +
                 sum(owner_calls[t] + self_terms[t] for t in CHILD_TERMS))
        spouse = sum(both[t] for t in SPOUSE_TERMS) + pers["couple"]
        role = ("spouse" if spouse > max(parent, child) else "contact_parent" if parent > child and parent > 0
                else "contact_child" if child > 0 else "elder" if elder_kin else "relative")
        reasons.append(f"family_role:{role}")
        if elder_kin and not fam_ok:
            reasons.append("elder_kin_pattern")
    if kin_name:
        reasons.append("kin_display_name")
    for code, v in (("kin_address", kin_o + kin_c), ("kin_child_terms", child_use if kin_o + kin_c else 0),
                    ("couple_signal", pers["couple"]), ("kin_endearment", pers["endearment"]),
                    ("insider_contact", ins["contact"]), ("insider_contact_weak", ins["contact_weak"]),
                    ("insider_owner", ins["owner"]), ("owner_instruction", ins["instruction"]),
                    ("owner_calls_be", be_use), ("contact_elder", elder_inferred),
                    ("service_vocab", cust["service"]), ("catalog_match", cust["catalog"]),
                    ("booking_vocab", cust["booking"]), ("price_vocab", cust["price"]),
                    ("weak_service_vocab", cust["weak"]), ("calls_owner_business", cust["business"]),
                    ("owner_business", cust["owner_business"]), ("visit_signal", cust["visit"]),
                    ("owner_service_vocab", cust["owner_service"]), ("owner_deference", cust["deference"]),
                    ("intimate_pronoun", intimate), ("personal_chitchat", pers["chitchat"]),
                    ("non_catalog_service", non_catalog_msgs)):
        if v:
            reasons.append(f"{code}:{v}")
    if rel == "staff" or ins["contact"]:
        reasons.append(f"junior_pattern:{junior}")
        reasons.append(f"senior_pattern:{senior}")
    if very_long:
        reasons.append("very_long_chat")
    elif long_personal:
        reasons.append("long_personal_chat")
    if long_chat:
        reasons.append("long_chat_no_service")
    if many_days:
        reasons.append("many_days_no_service")
    if text_in >= 30:
        reasons.append(f"purchase_ratio:{purchase_ratio:.2f}")

    # ---- addressing: only a customer (or an unknown contact) is addressed by the bot
    term, addr_conf, basis = recommend(owner_calls, self_terms, calls_owner, owner_self, name_prefix, self_sure, gender)
    addressing: dict[str, Any] = {
        "owner_calls_contact": dict(+owner_calls), "contact_calls_self": dict(+self_terms),
        "contact_calls_owner": dict(+calls_owner), "owner_calls_self": dict(+owner_self),
        "uses_owner": dict(+use_owner), "uses_contact": dict(+use_contact),
        "name_prefix": name_prefix, "name_gender": gender, "basis": basis,
    }
    last_service = last_service_of(services)
    if rel in ("family", "staff", "friend"):
        # the bot never drafts for them; the recommendation stays visible to staff in case they relabel the contact
        addressing["bot_term_if_customer"] = term
        addressing["bot_term_confidence"] = addr_conf
        term, addr_conf = None, "low"
        evidence_cands = []                 # nothing from a family, staff or friend chat is kept as a snippet
        last_service = None

    # ---- output
    svc_out = []
    for acc in sorted(services.values(), key=lambda a: (-(a.used_signal_count > 0), -a.mention_count, a.key)):
        svc_out.append({
            "key": acc.key, "service_id": acc.service_id, "name": acc.name, "group": acc.group or None,
            "sensitive": acc.group in SENSITIVE_GROUPS,
            "status": "likely_used" if acc.used_signal_count > 0 else "mentioned",
            "mention_count": acc.mention_count, "last_mentioned_at": acc.last_mentioned_at,
            "used_signal_count": acc.used_signal_count, "last_used_signal_at": acc.last_used_signal_at,
        })
    evidence_cands.sort(key=lambda x: (x[0], x[1]))
    evidence, seen = [], set()
    for _r, _t, ev in evidence_cands:
        if ev["text"] in seen:
            continue
        seen.add(ev["text"])
        evidence.append(ev)
        if len(evidence) >= MAX_SNIPPETS:
            break
    first = msgs[0] if msgs else None
    stats = {
        "messages_in": len(contact_msgs), "messages_out": len(owner_msgs), "text_in": text_in, "text_out": text_out,
        "first_at": first.ts if first else None, "last_at": msgs[-1].ts if msgs else None,
        "first_writer": None if not first else ("contact" if first.sender == thread_id else "owner"),
        "active_days": active_days, "service_messages": service_msgs, "weak_service_messages": weak_msgs,
        "booking_messages": booking_msgs,
        "price_messages": price_msgs, "visit_signal_messages": visit_msgs, "personal_signal_messages": personal_msgs,
        "work_messages": work_msgs, "non_catalog_messages": non_catalog_msgs,
        "insider_messages_contact": ins["contact"], "insider_messages_owner": ins["owner"],
        "owner_instructions": ins["instruction"], "kin_terms_owner": kin_o, "kin_terms_contact": kin_c,
        "child_terms": child_use, "nonkin_terms": nonkin,
        "customer_score": round(cust_score, 1), "personal_score": pers_score,
        "family_score": round(family_points, 1), "staff_score": round(staff_points, 1),
        "purchase_ratio": round(purchase_ratio, 3),
    }
    profile = {
        "zalo_user_id": f"p:{thread_id}",
        "display_name": display[:100] if display else None,
        "relationship": rel, "relationship_confidence": rel_conf, "relationship_reasons": reasons[:20],
        "address_term": term, "name_to_use": name_to_use, "address_confidence": addr_conf,
        "addressing": addressing, "services": svc_out[:40], "evidence": evidence, "last_service": last_service,
        "stats": stats,
    }
    return ThreadResult(profile, {"services": len(svc_out), "likely_used": sum(1 for s in svc_out if s["status"] == "likely_used"),
                                  "evidence": len(evidence), "last_service": 1 if last_service else 0})


# ---------------------------------------------------------------- database


def zalo_config_dir() -> Path:
    return Path(os.path.expanduser(os.environ.get("ZALO_CONFIG_DIR") or "~/.zalo-agent-cli"))


def active_account() -> str | None:
    p = zalo_config_dir() / "accounts.json"
    try:
        accounts = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(accounts, list):
        return None
    for a in accounts:
        if isinstance(a, dict) and a.get("active") and a.get("ownId"):
            return str(a["ownId"])
    if len(accounts) == 1 and isinstance(accounts[0], dict) and accounts[0].get("ownId"):
        return str(accounts[0]["ownId"])
    return None


def default_db(owner_id: str | None) -> Path | None:
    if not owner_id:
        return None
    data = os.environ.get("ZALO_DATA_DIR") or os.environ.get("ZALO_DB_DIR")
    base = Path(os.path.expanduser(data)) if data else zalo_config_dir() / "accounts"
    return base / owner_id / "zalo.db"


def open_ro(path: Path) -> sqlite3.Connection:
    uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.execute("PRAGMA query_only = ON")
    return con


SYSTEM_NAME_RE = re.compile(r"zalo|official account|(?<![^\W_])oa(?![^\W_])", re.IGNORECASE)
CARD_TYPES = {"card", "profile_card", "event"}
CARD_LIKE_TYPES = CARD_TYPES | {"link", "deleted", "group_event", "poll_event", "reaction"}


def is_system_account(display: str | None, contact_types: Counter | None) -> bool:
    """Zalo's own accounts and official accounts ("Zalo", "Zalo Official Account", "ZaloPay", "Thom OA"), or a contact
    whose rows are only cards, events and links (with at least one card or event)."""
    if display and SYSTEM_NAME_RE.search(unicodedata.normalize("NFC", display)):
        return True
    if contact_types:
        kinds = set(contact_types)
        return kinds <= CARD_LIKE_TYPES and bool(kinds & CARD_TYPES)
    return False


def read_threads(con: sqlite3.Connection, owner_id: str | None, since_ms: int | None) -> tuple[dict[str, str | None], dict[str, list[Msg]], dict[str, int]]:
    skipped = Counter()
    threads: dict[str, tuple[str | None, str | None]] = {}
    for tid, ttype, name in con.execute("SELECT threadId, type, name FROM threads"):
        threads[str(tid)] = (ttype, name)
    where = " WHERE timestamp >= ?" if since_ms else ""
    args: tuple = (since_ms,) if since_ms else ()
    rows = con.execute(
        "SELECT threadId, senderId, senderName, text, timestamp, type, msgId FROM messages" + where +
        " ORDER BY threadId, timestamp, msgId", args)
    by_thread: dict[str, list[Msg]] = defaultdict(list)
    contact_types: dict[str, Counter] = defaultdict(Counter)   # every row type the contact sent, system rows included
    contact_name: dict[str, str] = {}
    for tid, sender, sname, text, ts, mtype, msg_id in rows:
        tid = str(tid or "")
        if not tid:
            continue
        if str(sender or "") == tid:
            contact_types[tid][str(mtype or "")] += 1
            if sname:
                contact_name[tid] = str(sname)
        if str(msg_id or "").startswith("ge:") or (mtype or "") in SYSTEM_TYPES:
            continue
        by_thread[tid].append(Msg(str(sender or ""), str(sname or ""), text if isinstance(text, str) else "",
                                  int(ts or 0), str(mtype or "")))
    # Zalo's own accounts and official accounts: by name, or a contact that only ever sent cards, events and links
    for tid, types in contact_types.items():
        if tid in by_thread:
            continue
        ttype, name = threads.get(tid, (None, None))
        if ttype != "group" and (types.keys() & CARD_TYPES):
            skipped["system_account"] += 1
    if not owner_id:
        others = Counter(m.sender for tid, ms in by_thread.items() for m in ms if m.sender != tid and m.sender.isdigit())
        owner_id = others.most_common(1)[0][0] if others else None
    names: dict[str, str | None] = {}
    msgs: dict[str, list[Msg]] = {}
    for tid, ms in by_thread.items():
        ttype, name = threads.get(tid, (None, None))
        if ttype == "group":
            skipped["group"] += 1
            continue
        if owner_id and tid == owner_id:
            skipped["own_thread"] += 1
            continue
        if not THREAD_ID_RE.match(tid):
            skipped["bad_thread_id"] += 1   # the server would refuse the whole import batch
            continue
        if is_system_account((name or "").strip() or contact_name.get(tid), contact_types.get(tid)):
            skipped["system_account"] += 1
            continue
        if ttype != "dm" and not any(m.sender == tid for m in ms):
            skipped["not_dm"] += 1
            continue
        names[tid] = name
        msgs[tid] = ms
    return names, msgs, dict(skipped)


# ---------------------------------------------------------------- output / push


def bot_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("THOMHOUSE_BOT_HOME") or "~/.thomhouse-bot"))


def write_output(doc: dict[str, Any], out_dir: Path, now: datetime, private_dir: bool = False) -> Path:
    """Writes the JSON (mode 0600). The folder is set to 0700 only when this call creates it or it is the default
    profiles folder (private_dir); a folder the user named (--out-dir) keeps its mode, with a warning on stderr when
    other users of the Mac can read it."""
    created = not out_dir.exists()
    out_dir.mkdir(parents=True, exist_ok=True)
    if created or private_dir:
        try:
            os.chmod(out_dir, 0o700)
        except OSError as e:
            print(f"warning: cannot set the output folder to mode 700 ({type(e).__name__})", file=sys.stderr)
    else:
        try:
            if stat.S_IMODE(out_dir.stat().st_mode) & 0o077:
                print("warning: other users of this Mac can list the output folder; the file itself is written with "
                      "mode 600", file=sys.stderr)
        except OSError:
            pass
    path = out_dir / f"contacts-{now.strftime('%Y%m%d-%H%M')}.json"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.chmod(path, 0o600)
    return path


def dev_var(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    path = Path(os.environ.get("THOMHOUSE_DEV_VARS") or (ROOT / "apps/server/.dev.vars"))
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip() == name:
                return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def is_local_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost") or host.endswith(".test")


def push(profiles: list[dict[str, Any]], generated_at: int, server_url: str, token: str) -> dict[str, int]:
    totals = Counter()
    for i in range(0, len(profiles), IMPORT_BATCH):
        body = json.dumps({"analyzer_version": ANALYZER_VERSION, "generated_at": generated_at,
                           "profiles": profiles[i:i + IMPORT_BATCH]}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(server_url.rstrip("/") + "/staff/profiles/import", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {token}", "X-Staff-Id": "analyzer",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8") or "{}").get("error", {})
            except ValueError:
                err = {}
            raise RuntimeError(f"import failed: HTTP {e.code} {err.get('code', '')} {json.dumps(err.get('details') or {})}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"import failed: server not reachable ({type(e).__name__})") from None
        for k in ("imported", "created", "updated", "kept_staff_fields"):
            totals[k] += int(res.get(k) or 0)
    return dict(totals)


# ---------------------------------------------------------------- main


def parse_since(s: str | None) -> int | None:
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=TZ_VN)
    except ValueError:
        raise SystemExit("--since must be YYYY-MM-DD") from None
    return int(d.timestamp() * 1000)


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Profile 1:1 Zalo contacts from the local zalo.db (rules only).")
    ap.add_argument("--db", help="path to zalo.db (default: the active account under ~/.zalo-agent-cli)")
    ap.add_argument("--owner-id", help="the account's ownId (default: from accounts.json or the db folder)")
    ap.add_argument("--since", help="only messages from this local date on (YYYY-MM-DD)")
    ap.add_argument("--catalog", default=str(ROOT / "data/services.json"), help="catalog JSON (default data/services.json)")
    ap.add_argument("--out-dir", help="output folder (default $THOMHOUSE_BOT_HOME/profiles)")
    ap.add_argument("--push", action="store_true", help="import the profiles into the local server")
    ap.add_argument("--server-url", help="local server (default SERVER_URL or http://127.0.0.1:8787)")
    ap.add_argument("--dry-run", action="store_true", help="analyze and print counts; write and push nothing")
    args = ap.parse_args(argv)

    if truthy(os.environ.get("PROFILE_LLM_ENABLED")):
        print("PROFILE_LLM_ENABLED is set, but a model pass over contact history is not implemented "
              "(contacts did not consent to it). Unset it to run the rules-only analysis.", file=sys.stderr)
        return 2

    owner_id = args.owner_id or None
    if args.db:
        db = Path(os.path.expanduser(args.db))
        if not owner_id and db.parent.name.isdigit():
            owner_id = db.parent.name
    else:
        owner_id = owner_id or active_account()
        db = default_db(owner_id)
        if db is None:
            print("no active zalo-agent account found; pass --db and --owner-id", file=sys.stderr)
            return 1
    if not db.exists():
        print("zalo.db not found at the given or default path", file=sys.stderr)
        return 1
    try:
        con = open_ro(db)
        names, msgs, skipped = read_threads(con, owner_id, parse_since(args.since))
        con.close()
    except sqlite3.Error as e:
        print(f"cannot read zalo.db read-only ({type(e).__name__}); is it a zalo-agent-cli cache?", file=sys.stderr)
        return 1

    catalog = load_catalog(Path(args.catalog))
    profiles = []
    totals = Counter()
    for tid in sorted(msgs):
        r = analyze_thread(tid, names.get(tid), msgs[tid], catalog)
        profiles.append(r.profile)
        totals.update(r.counts)
    rel = Counter((p["relationship"], p["relationship_confidence"]) for p in profiles)
    addr = Counter(p["address_term"] for p in profiles)
    now = datetime.now(TZ_VN)
    generated_at = int(time.time() * 1000)
    doc = {"analyzer_version": ANALYZER_VERSION, "generated_at": generated_at, "since": args.since,
           "owner_id": owner_id, "contacts": len(profiles), "skipped": skipped, "profiles": profiles}

    skipped_txt = ", ".join(f"{k} {v}" for k, v in sorted(skipped.items()))
    print(f"contacts analyzed: {len(profiles)}" + (f" (skipped threads: {skipped_txt})" if skipped_txt else ""))
    for (r, c), n in sorted(rel.items()):
        print(f"  relationship {r}/{c}: {n}")
    for t, n in sorted(addr.items(), key=lambda x: str(x[0])):
        print(f"  address_term {t}: {n}")
    print(f"  with a name to use: {sum(1 for p in profiles if p['name_to_use'])}")
    print(f"  services found: {totals['services']} (likely used: {totals['likely_used']}); evidence snippets: {totals['evidence']}")
    print(f"  with a last service from chat: {totals['last_service']}")

    if args.dry_run:
        print("dry run: nothing written, nothing pushed")
        return 0
    if args.out_dir:
        out = write_output(doc, Path(os.path.expanduser(args.out_dir)), now)
    else:
        out = write_output(doc, bot_home() / "profiles", now, private_dir=True)
    print(f"written: {out} (mode 600)")
    if args.push:
        server = args.server_url or dev_var("SERVER_URL") or "http://127.0.0.1:8787"
        if not is_local_url(server):
            print("refusing to push profiles to a non-local server", file=sys.stderr)
            return 1
        token = dev_var("STAFF_TOKEN")
        if not token:
            print("STAFF_TOKEN not found (environment or apps/server/.dev.vars)", file=sys.stderr)
            return 1
        try:
            res = push(profiles, generated_at, server, token)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        print("pushed: " + ", ".join(f"{k} {res.get(k, 0)}" for k in ("imported", "created", "updated", "kept_staff_fields")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
