"""Synthetic zalo.db behind the two analyzer documents of test/chat-facts-analyzer-document.test.ts.

Same tables and columns as scripts/tests/test_analyze_visits.py. Every name, phone number, id and message below is
invented. Python 3.11 or later (scripts/analyze_visits.py needs it). The folders are throwaway, never
~/.zalo-agent-cli or ~/.thomhouse-bot. Both recipes run from the repository root.

test/fixtures/analyzer-visits-document.json, the rules pass only (contacts A, B, C, D and the family contact):

  T=$(mktemp -d) && mkdir -p $T/accounts/1000000009 $T/out $T/home $T/zalo && chmod 700 $T/out
  python3 -I -B apps/server/test/fixtures/analyzer-cache.py $T/accounts/1000000009/zalo.db
  env -u PROFILE_LLM_ENABLED THOMHOUSE_BOT_HOME=$T/home ZALO_CONFIG_DIR=$T/zalo ZALO_DATA_DIR=$T/zalo/accounts \
      THOMHOUSE_DEV_VARS=$T/none python3 -I -B scripts/analyze_visits.py --db $T/accounts/1000000009/zalo.db \
      --owner-id 1000000009 --out-dir $T/out --now '2026-11-12 10:00'
  cp $T/out/visits-*.json apps/server/test/fixtures/analyzer-visits-document.json

test/fixtures/analyzer-model-document.json, the model pass on (contact E added), answered by the fake claude of
scripts/tests/fake_bin_visits. "--model-pass FILE" adds E and writes the fake's configuration to FILE: the answers of
MODEL_ANSWERS in the analyzer's call order (A, B, C, D, E) and a call log next to FILE. PATH holds only the fake, a
python3 link and /usr/bin:/bin, so no real `claude` can be found; the account pool is a throwaway accounts.json.

  T=$(mktemp -d) && mkdir -p $T/accounts/1000000009 $T/out $T/home/accounts/acc1 $T/zalo $T/bin && chmod 700 $T/out
  ln -s "$(command -v python3)" $T/bin/python3
  printf '[{"label": "acc1", "config_dir": "%s", "priority": 1, "enabled": true}]' $T/home/accounts/acc1 \
      > $T/home/accounts.json
  python3 -I -B apps/server/test/fixtures/analyzer-cache.py $T/accounts/1000000009/zalo.db --model-pass $T/fake.json
  env -i HOME=$T/home PATH=$PWD/scripts/tests/fake_bin_visits:$T/bin:/usr/bin:/bin THOMHOUSE_BOT_HOME=$T/home \
      ZALO_CONFIG_DIR=$T/zalo ZALO_DATA_DIR=$T/zalo/accounts THOMHOUSE_DEV_VARS=$T/none \
      FAKE_CLAUDE_VISITS_CONFIG=$T/fake.json PROFILE_LLM_ENABLED=true PROFILE_LLM_SCOPE=customers \
      python3 -I -B scripts/analyze_visits.py --db $T/accounts/1000000009/zalo.db --owner-id 1000000009 \
      --out-dir $T/out --now '2026-11-12 10:00'
  cp $T/out/visits-*.json apps/server/test/fixtures/analyzer-model-document.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=7))
OWNER = "1000000009"
A = "5550002001"    # customer, diacritics: two visits, an upcoming booking, a package, a phone in the chat
B = "5550002002"    # customer, no diacritics: a cancelled booking, then a visit; phone only in the contacts table
C = "5550002003"    # customer: a booking request the spa never confirmed (low)
D = "5550002004"    # customer for the analyzer; the server test gives it the role staff
FAM = "5550002005"  # family (mother): the analyzer skips it
E = "5550002006"    # --model-pass only: a walk-in and a package the rules miss, a visit without a service

SCHEMA = """
CREATE TABLE messages (msgId TEXT PRIMARY KEY, threadId TEXT, senderId TEXT, senderName TEXT, text TEXT,
  timestamp INTEGER, type TEXT, raw_data TEXT, localPath TEXT, has_attachment INTEGER DEFAULT 0, msgStatus INTEGER,
  mediaPrunedAt INTEGER);
CREATE TABLE threads (threadId TEXT PRIMARY KEY, type TEXT, name TEXT, lastUpdate INTEGER,
  sync_timestamp INTEGER DEFAULT 0, respondedByMe INTEGER, lastGlobalId TEXT, lastClientId TEXT, leftAt INTEGER,
  deleteMarkerAt INTEGER);
CREATE TABLE contacts (userId TEXT PRIMARY KEY, name TEXT, phone TEXT);
"""


def at(mo: int, d: int, h: int = 10, mi: int = 0) -> int:
    return int(datetime(2026, mo, d, h, mi, tzinfo=TZ).timestamp() * 1000)


# (timestamp, from the contact, text)
CHAT_A = [
    (at(10, 29, 10, 0), True, "Chào shop, chị muốn đặt lịch gội đầu thư giãn thứ 7 lúc 15h nha em"),
    (at(10, 29, 10, 5), False, "Dạ em giữ lịch thứ 7 15h cho chị nha"),
    (at(10, 31, 14, 55), True, "chị tới rồi nè em"),
    (at(10, 31, 16, 30), False, "Dạ tổng hôm nay 199k ạ, bạn Lan làm cho chị nha"),
    (at(10, 31, 16, 35), True, "chị chuyển khoản rồi nhé em"),
    (at(11, 1, 9, 0), False, "Cảm ơn chị đã ghé thom house hôm qua ạ"),
    (at(11, 1, 9, 30), True, "Chị mới đổi số, sđt chị 0912 345 678 nha em"),
    (at(11, 4, 9, 0), True, "mai chị qua massage body lúc 10h được không em"),
    (at(11, 4, 9, 10), False, "Dạ được ạ, em giữ lịch 10h mai cho chị nha"),
    (at(11, 5, 9, 55), True, "chị đến nơi rồi"),
    (at(11, 5, 11, 35), True, "chị ck 350k rồi nha"),
    (at(11, 5, 12, 0), False, "Dạ gói 10 buổi gội đầu của chị còn 7 buổi nha chị"),
    (at(11, 11, 20, 0), True, "Thứ 3 tuần sau chị đặt lịch gội đầu lúc 9h nha em"),
    (at(11, 11, 20, 5), False, "Dạ em giữ lịch thứ 3 9h cho chị ạ"),
]
CHAT_B = [
    (at(11, 2, 9, 0), True, "chao shop, mai chi muon dat lich goi dau thu gian luc 3h nhe"),
    (at(11, 2, 9, 5), False, "Dạ em giữ lịch 15h mai cho chị nha"),
    (at(11, 3, 8, 0), True, "em oi chi ban dot xuat, huy lich hom nay giup chi nhe"),
    (at(11, 3, 8, 5), False, "Dạ em hủy lịch rồi nha chị"),
    (at(11, 3, 8, 10), True, "cam on em, tuan sau chi dat lai nhe"),
    (at(11, 8, 9, 0), True, "chieu nay chi qua massage chan luc 4h nhe em"),
    (at(11, 8, 9, 5), False, "Dạ em giữ lịch 16h chiều nay cho chị nha"),
    (at(11, 8, 15, 58), True, "chi toi roi em"),
    (at(11, 9, 9, 0), False, "Cảm ơn chị hôm qua đã ghé ạ"),
]
CHAT_C = [
    (at(11, 6, 9, 0), True, "Cho chị hỏi giá massage body 60 phút bao nhiêu vậy em"),
    (at(11, 6, 9, 5), False, "Dạ massage body 60 phút giá 350k ạ"),
    (at(11, 6, 9, 30), True, "Chủ nhật chị đặt lịch massage body lúc 2h chiều nha em"),
]
CHAT_D = [
    (at(11, 3, 10, 0), True, "Chào shop, mai chị muốn đặt lịch gội đầu thư giãn lúc 11h nha"),
    (at(11, 3, 10, 5), False, "Dạ em giữ lịch 11h mai cho chị nha"),
    (at(11, 4, 10, 55), True, "chị tới rồi em ơi"),
    (at(11, 4, 12, 30), False, "Dạ tổng hôm nay 199k ạ, cảm ơn chị đã ghé"),
]
MOTHER_OWNER = ["Mẹ ơi con về muộn nha", "Con ăn rồi mẹ ơi", "Dạ mẹ, con nhớ rồi", "Mẹ ăn cơm chưa",
                "Con gửi mẹ tiền rồi nha mẹ", "Mai con ghé thăm mẹ", "Con thương mẹ nhiều", "Dạ con biết rồi mẹ"]
MOTHER_CONTACT = ["Ừ mẹ biết rồi", "Con ăn cơm chưa", "Mẹ đi chợ rồi con", "Con nhớ mặc ấm nha con",
                  "Mẹ nhớ con lắm", "Mẹ nhận tiền rồi, cảm ơn con", "Dạ mẹ khỏe, con đừng lo", "Mẹ thương con"]
# The rules find only the 10/11 visit (booked, arrival, thanks), without a service. They miss the 07/11 walk-in (a
# payment with no arrival or thanks around it) and the package ("đóng tiền" is not a purchase verb of the rules).
# The price question makes the analyzer read E as a customer at confidence high (scope "customers" sends it).
E_PAID = "Bạn Mai bấm cổ vai gáy cho chị nhẹ người hẳn, chị ck 300k rồi nha em"
E_PACKAGE = "Chị đóng tiền liệu trình 5 lần cổ vai gáy rồi đó em"
E_BOOKED = "Dạ em giữ lịch 17h mai cho chị nha"
E_THANKS = "Cảm ơn chị hôm qua đã ghé ạ"
CHAT_E = [
    (at(11, 7, 9, 0), True, "Chào shop, massage cổ vai gáy bên mình giá bao nhiêu vậy em"),
    (at(11, 7, 9, 5), False, "Dạ massage cổ vai gáy 60 phút giá 300k ạ"),
    (at(11, 7, 16, 40), True, E_PAID),
    (at(11, 8, 10, 0), True, E_PACKAGE),
    (at(11, 8, 10, 5), False, "Dạ em ghi nhận rồi ạ"),
    (at(11, 9, 9, 0), True, "Chiều mai 5h chị qua làm tiếp nha em"),
    (at(11, 9, 9, 5), False, E_BOOKED),
    (at(11, 10, 16, 58), True, "chị tới rồi nè"),
    (at(11, 11, 9, 0), False, E_THANKS),
]


def cite(chat: list[tuple[int, bool, str]], *texts: str) -> list[int]:
    """Transcript indexes of messages: 1-based position among all messages of the conversation in time order."""
    stamps = sorted(ts for ts, _fc, _t in chat)
    return [stamps.index(next(ts for ts, _fc, t in chat if t == text)) + 1 for text in texts]


def _visit(date: str, time: str | None, status: str, service_id: str | None, amount: int | None,
           technician: str | None, cites: list[int]) -> dict:
    return {"date": date, "time": time, "status": status, "service_id": service_id, "amount_vnd": amount,
            "technician": technician, "cites": cites}


def model_answers() -> list[dict]:
    """What a careful model answers for each transcript, in the analyzer's call order (A, B, C, D, E)."""
    a = [
        _visit("2026-10-31", "15:00", "completed", "goi-dau-thu-gian", 199000, "Lan", cite(CHAT_A, *(
            t for _ts, _fc, t in CHAT_A[0:6]))),
        _visit("2026-11-05", "10:00", "completed", "massage-body-thu-gian", 350000, None, cite(CHAT_A, *(
            t for _ts, _fc, t in CHAT_A[7:11]))),
        # dated after --now: the analyzer drops it ("model items dropped 1")
        _visit("2026-11-17", "09:00", "booked", "goi-dau-thu-gian", None, None, cite(CHAT_A, CHAT_A[12][2],
                                                                                    CHAT_A[13][2])),
    ]
    a_packages = [{"title": "Gói 10 buổi gội đầu", "total_count": 10, "remaining": 7,
                   "cites": cite(CHAT_A, CHAT_A[11][2])}]          # the rules package: nothing new
    b = [
        _visit("2026-11-03", "15:00", "cancelled", "goi-dau-thu-gian", None, None, cite(CHAT_B, *(
            t for _ts, _fc, t in CHAT_B[0:4]))),                     # no candidate on that date: nothing
        _visit("2026-11-08", "16:00", "completed", "massage-chan", None, None, cite(CHAT_B, *(
            t for _ts, _fc, t in CHAT_B[5:9]))),
    ]
    c = [_visit("2026-11-08", "14:00", "booked", "massage-body-thu-gian", None, None, cite(CHAT_C, CHAT_C[2][2]))]
    d = [_visit("2026-11-04", "11:00", "completed", "goi-dau-thu-gian", 199000, None, cite(CHAT_D, *(
        t for _ts, _fc, t in CHAT_D)))]
    e = [
        # a new medium visit: service on the cited line's date (basis visit_day), amount with "ck" (paid)
        _visit("2026-11-07", None, "completed", "massage-co-vai-gay", 300000, "Mai", cite(CHAT_E, E_PAID)),
        # fills the empty service of the rules visit; no cited line is on 10/11 (basis window)
        _visit("2026-11-10", "17:00", "completed", "massage-co-vai-gay", None, None, cite(
            CHAT_E, E_PACKAGE, E_BOOKED, E_THANKS)),
    ]
    e_packages = [{"title": "Liệu trình cổ vai gáy", "total_count": 5, "remaining": None,
                   "cites": cite(CHAT_E, E_PACKAGE)}]              # stated by the contact
    return [{"visits": a, "packages": a_packages}, {"visits": b, "packages": []}, {"visits": c, "packages": []},
            {"visits": d, "packages": []}, {"visits": e, "packages": e_packages}]


def main(out: Path, model_config: Path | None = None) -> None:
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    n = 0

    def thread(tid: str, name: str) -> None:
        con.execute("INSERT INTO threads (threadId, type, name, lastUpdate) VALUES (?,?,?,0)", (tid, "dm", name))

    def msg(tid: str, from_contact: bool, text: str, ts: int, name: str) -> None:
        nonlocal n
        n += 1
        con.execute(
            "INSERT INTO messages (msgId, threadId, senderId, senderName, text, timestamp, type) VALUES (?,?,?,?,?,?,?)",
            (f"m{n}", tid, tid if from_contact else OWNER, name if from_contact else "Chủ", text, ts, "text"))

    chats = [(A, "Trần Thị Mơ", CHAT_A), (B, "Le Thi Hien", CHAT_B), (C, "Đỗ Thu Trang", CHAT_C),
             (D, "Phạm Ngọc Hà", CHAT_D)]
    if model_config is not None:
        chats.append((E, "Vũ Hồng Nhung", CHAT_E))
    for tid, name, chat in chats:
        thread(tid, name)
        for ts, fc, text in chat:
            msg(tid, fc, text, ts, name)
    thread(FAM, "Mẹ")
    t = at(10, 1, 9, 0)
    for _round in range(3):
        for o, c in zip(MOTHER_OWNER, MOTHER_CONTACT):
            msg(FAM, False, o, t, "Mẹ")
            msg(FAM, True, c, t + 60_000, "Mẹ")
            t += 12 * 3_600_000
    con.execute("INSERT INTO contacts (userId, name, phone) VALUES (?,?,?)", (B, "Le Thi Hien", "0987654321"))
    con.execute("INSERT INTO contacts (userId, name, phone) VALUES (?,?,?)", (FAM, "Mẹ", "0933111222"))
    con.commit()
    con.close()
    if model_config is not None:
        log = model_config.parent / "calls.jsonl"
        model_config.write_text(json.dumps({"mode": "reply", "replies": model_answers(), "log": str(log)},
                                           ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(Path(sys.argv[1]))
    elif len(sys.argv) == 4 and sys.argv[2] == "--model-pass":
        main(Path(sys.argv[1]), Path(sys.argv[3]))
    else:
        sys.exit("usage: analyzer-cache.py ZALO_DB [--model-pass FAKE_CLAUDE_CONFIG]")
