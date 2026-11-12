#!/usr/bin/env python3
"""Import past visits from a CSV file (a sheet or a sales program export) into the LOCAL server.

What it does
  Reads the CSV, turns every row into one visit of POST /staff/visits/import (docs/contracts.md 14.5) and posts the
  rows in parts of at most 2 000. The server finds the customer of each row, skips the visits it already has and
  never creates a follow-up job for an imported visit, so running the same file twice writes nothing twice.

  A dry run always comes first: every part is posted with "dry_run": true, which writes nothing, and the counts and
  the rows that cannot be imported are printed. Only with --apply are the parts posted a second time and written.

Privacy
  The output is counts, row numbers (as the sheet shows them: the first row is row 1), column letters and reason
  codes. No cell of the file is printed: no name, phone number, service, amount or id. Columns the script does not
  know (a customer name, a note) are never read. The rows go to the local server only (SERVER_URL and STAFF_TOKEN
  from the environment or apps/server/.dev.vars, staff id "visits-import"); a non-local server is refused.

Columns
  The first row with text holds the column names. A name is matched without accents, case and punctuation, so
  "Số điện thoại", "so dien thoai" and "SO_DIEN_THOAI" are the same. The field names of the contract work too.
    customer     one of: customer id ("Mã khách hàng", only this system's cus_ ids; a code of another program is
                 left out), Zalo id ("Zalo ID"; digits or p:<digits>), phone ("Số điện thoại", "SĐT", "Phone").
                 The first of the three that the row has in a readable form is used. A Zalo id the server does
                 not know yet gets a new, empty customer (counted as "new customers" in the dry run).
    date         "Ngày", "Date", "Thời gian"...: dd/mm/yyyy, d/m/yy, dd-mm-yyyy, dd.mm.yyyy, yyyy-mm-dd, each
                 alone or followed by a time ("09/10/2026 14:30", "2026-10-09T14:30:00").
    time         "Giờ", "Time" (optional): 14:30, 14:30:00, 14h30, 14h, 2:30 PM, 2:30 CH. Without a time the
                 visit is recorded at 12:00. Times are local (Asia/Ho_Chi_Minh).
    service      "Dịch vụ", "Service": the name the studio uses, or a catalog id. A name equal to a catalog name
                 (data/services.json) is sent with that service's id; any other name is kept as written.
                 "Mã dịch vụ" / "Service ID" is a separate column for catalog ids.
    amount       "Thành tiền", "Số tiền", "Amount" (optional): a whole number of dong. 450000, 450.000, 450,000đ
                 and 450 000 VND are read. Short forms such as 450k are not: the row is reported as bad_amount.
    technician   "KTV", "Kỹ thuật viên", "Nhân viên", "Technician" (optional, at most 60 characters).
    duration     "Thời lượng", "Số phút", "Duration" (optional): minutes (60, 60 phút, 60p) or hours (1h30).
    external id  "Mã hóa đơn", "Invoice", "External ID" (optional): the id of the visit in the other program. An
                 id that several rows share (several lines of one invoice) is not sent; the server then recognises
                 those rows by customer, time and service.
  --column FIELD=NAME tells the script which column holds a field when its name is not in the list above; NAME is
  the column's name in the file or its letter (A, B, ...). --header-row N is for a file that has title rows above
  the column names.

Usage (from the project root)
  python3 -I scripts/import_visits.py visits.csv              # dry run: counts and the rows that would not go in
  python3 -I scripts/import_visits.py visits.csv --apply      # the same dry run, then write
  python3 -I scripts/import_visits.py visits.csv --column amount="Thực thu" --date-order mdy

Exit code: 0 the file was read and the server answered every part; 1 anything else (nothing more is sent after the
first failed part; sending the file again is safe).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAFF_ID = "visits-import"
MAX_ROWS_PER_CALL = 2000                    # the server's limit for one request
HTTP_TIMEOUT_S = 120
LOCAL_TZ = timezone(timedelta(hours=7))     # Asia/Ho_Chi_Minh has no daylight saving
DEFAULT_TIME = (12, 0)                      # a row without a time
MAX_TECHNICIAN_CHARS = 60                   # the server answers 422 for the whole request above these three
MAX_EXTERNAL_ID_CHARS = 100
MAX_DURATION_MIN = 24 * 60
MAX_SERVICE_NAME_CHARS = 120
DELIMITERS = ",;\t|"

# Column names after header_key(): no accents, lower case, words separated by one space.
ALIASES: dict[str, tuple[str, ...]] = {
    "customer_id": ("customer id", "customerid", "ma khach hang", "ma khach", "ma kh", "id khach hang", "id khach"),
    # Not the bare name "Zalo": such a column usually holds a phone number or a display name, and a number sent as
    # a Zalo id would make the server create an empty customer for it.
    "zalo_user_id": ("zalo user id", "zalo id", "zalo uid", "id zalo", "uid zalo"),
    "phone": ("phone", "phone number", "mobile", "tel", "telephone", "so dien thoai", "dien thoai", "sdt", "so dt",
              "dt", "di dong", "so di dong", "sdt khach", "sdt khach hang", "so dien thoai khach hang",
              "dien thoai khach hang"),
    "date": ("date", "visit date", "visited at", "visited at local", "datetime", "date time", "ngay", "ngay den",
             "ngay lam", "ngay su dung", "ngay thuc hien", "ngay ban", "ngay mua", "ngay gio", "thoi gian",
             "ngay hoa don", "ngay giao dich", "ngay tao"),
    "time": ("time", "visit time", "gio", "gio den", "gio lam", "gio vao", "gio bat dau"),
    "service_id": ("service id", "serviceid", "ma dich vu", "ma dv", "id dich vu"),
    "service": ("service", "service name", "dich vu", "ten dich vu", "ten dv", "dv", "goi dich vu", "lieu trinh",
                "ten lieu trinh", "ten hang", "ten hang hoa", "san pham", "ten san pham"),
    "amount": ("amount", "amount vnd", "price", "total", "paid", "so tien", "thanh tien", "tong tien", "tien", "gia",
               "gia tien", "doanh thu", "thanh toan", "khach tra", "khach da tra", "tong cong", "thuc thu"),
    "technician": ("technician", "therapist", "staff", "ktv", "ky thuat vien", "nhan vien", "nhan vien thuc hien",
                   "nguoi thuc hien", "nguoi lam"),
    "duration": ("duration", "duration min", "minutes", "thoi luong", "so phut", "phut", "thoi gian lam"),
    "external_id": ("external id", "external visit id", "visit id", "invoice", "invoice id", "invoice no", "receipt",
                    "order id", "ma hoa don", "so hoa don", "ma hd", "ma don", "ma don hang", "ma giao dich",
                    "ma phieu", "so phieu"),
}
FIELD_LABELS = {"customer_id": "customer id", "zalo_user_id": "Zalo id", "phone": "phone", "date": "date",
                "time": "time", "service_id": "service id", "service": "service", "amount": "amount",
                "technician": "technician", "duration": "duration", "external_id": "external id"}

# Why a row is not imported. The first four also come from the server; the others are found on this machine.
REASONS = {
    "no_customer": "the row has no customer id, Zalo id or phone number, or no customer has it (a phone number "
                   "must be on exactly one customer)",
    "bad_zalo_id": "the Zalo id is not a personal id (digits, or p: and digits)",
    "bad_phone": "the phone number is not 9 to 11 digits",
    "bad_time": "the date or time is missing, is not one of the known forms, is before 2000 or is in the future",
    "bad_service": "the row has no service, a service id outside the catalog without a name, or a name of more "
                   "than 120 characters",
    "bad_amount": "the amount is not a whole number of dong: 450000, 450.000 and 450,000đ are read, short forms "
                  "such as 450k or 1tr2 are not",
    "bad_duration": "the duration is not a whole number of minutes from 1 to 1440",
    "bad_technician": "the technician is longer than 60 characters",
    "bad_external_id": "the external id is longer than 100 characters",
}

BAD = object()      # a cell that has a value the script cannot read


class ImportFailed(Exception):
    """A message for the terminal. It never carries a cell of the file or a body of the server."""


# ---------------------------------------------------------------- text helpers


def fold(text: str) -> str:
    """Lower case without accents (đ becomes d)."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def header_key(text: str) -> str:
    """How a column name (and a service name) is compared: folded, punctuation and extra spaces removed."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split())


def one_line(text: str) -> str:
    return " ".join(text.split())


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA: the letter a sheet shows for that column."""
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def column_index(letter: str) -> int | None:
    if not re.fullmatch(r"[A-Za-z]{1,3}", letter):
        return None
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def row_ranges(numbers: list[int]) -> str:
    """[2, 3, 4, 9] -> '2-4, 9'."""
    parts: list[str] = []
    numbers = sorted(set(numbers))
    i = 0
    while i < len(numbers):
        j = i
        while j + 1 < len(numbers) and numbers[j + 1] == numbers[j] + 1:
            j += 1
        parts.append(str(numbers[i]) if i == j else f"{numbers[i]}-{numbers[j]}")
        i = j + 1
    return ", ".join(parts)


# ---------------------------------------------------------------- cells


def clean_cell(text: str) -> str:
    """A cell as typed: spaces trimmed, and without the ="..." or leading ' that sheets use to keep a text as text."""
    s = text.replace(" ", " ").strip()
    m = re.fullmatch(r'="(.*)"', s)
    if m:
        s = m.group(1).strip()
    return s[1:].strip() if s.startswith("'") else s


def parse_phone(cell: str) -> tuple[str | None, bool]:
    """(digits, a leading 0 was put back). The same rule as the server: spaces, dots, dashes and parentheses are
    removed, +84 (or 84 of an 11-digit number) becomes 0, 9 to 11 digits. A sheet often drops the leading 0 of a
    mobile number; a 9-digit number that starts like a mobile number (3, 5, 7, 8, 9) gets it back."""
    s = re.sub(r"[\s.\-()]", "", cell)
    if s.startswith("+84"):
        s = "0" + s[3:]
    if not re.fullmatch(r"[0-9]+", s):
        return None, False
    if len(s) == 11 and s.startswith("84"):
        s = "0" + s[2:]
    restored = len(s) == 9 and s[0] in "35789"
    if restored:
        s = "0" + s
    return (s, restored) if 9 <= len(s) <= 11 else (None, False)


def parse_zalo_id(cell: str) -> str | None:
    """'p:<digits>' for a personal id written as digits or as p:<digits>; None for a group id or anything else."""
    m = re.fullmatch(r"(?:p:)?([0-9]{1,32})", cell.strip().lower())
    return f"p:{m.group(1)}" if m else None


def parse_amount(cell: str) -> Any:
    """Dong as an integer, None for an empty cell, BAD for anything that is not clearly a whole number of dong.

    Read: 450000, 450.000, 450,000, 450 000, with an optional đ / ₫ / d / VND / VNĐ / đồng, and a zero decimal part
    (450000.00, 450.000,00). Not read: 450k, 1tr2, 1.5, a negative number, mixed separators."""
    s = re.sub(r"\s", "", fold(cell))               # folded: đ, Đ and "đồng" in any Unicode form become d / dong
    if not s:
        return None
    s = re.sub(r"(?:vnd|dong|d|₫)\.?$", "", s).lstrip("₫")
    if re.fullmatch(r"[0-9]+", s):
        return int(s)
    for grouped, decimal in ((r"\.", ","), (",", r"\.")):
        m = re.fullmatch(rf"([0-9]{{1,3}}(?:{grouped}[0-9]{{3}})+)(?:{decimal}0{{1,2}})?", s)
        if m:
            return int(re.sub(r"[^0-9]", "", m.group(1)))
    m = re.fullmatch(r"([0-9]+)[.,]0{1,2}", s)
    return int(m.group(1)) if m else BAD


def parse_duration(cell: str) -> Any:
    """Minutes as an integer from 1 to 1440, None for an empty cell, BAD otherwise. 60, 60 phút, 60p, 60', 1h, 1h30."""
    s = re.sub(r"\s", "", fold(cell))
    if not s:
        return None
    m = re.fullmatch(r"([0-9]{1,4})(?:[.,]0+)?(?:phut|ph|p|'|min|mins|minute|minutes|m)?", s)
    if m:
        minutes = int(m.group(1))
    else:
        m = re.fullmatch(r"([0-9]{1,2})(?:h|g|gio|tieng)(?:([0-9]{1,2})(?:phut|ph|p|'|m)?)?", s)
        if not m:
            return BAD
        minutes = int(m.group(1)) * 60 + int(m.group(2) or 0)
    return minutes if 1 <= minutes <= MAX_DURATION_MIN else BAD


def parse_time(text: str) -> tuple[int, int] | None:
    """(hour, minute) from 14:30, 14:30:05, 14h30, 14h, 14, 2:30 PM, 2 PM, 2:30 CH (SA and CH are AM and PM)."""
    s = re.sub(r"\s", "", fold(text))
    m = re.fullmatch(r"([0-9]{1,2})(?::([0-9]{2})(?::[0-9]{2}(?:[.,][0-9]+)?)?|[hg]([0-9]{2})?)?(am|pm|sa|ch)?", s)
    if not m:
        return None
    hour, minute, half = int(m.group(1)), int(m.group(2) or m.group(3) or 0), m.group(4)
    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half in ("pm", "ch") else 0)
    return (hour, minute) if hour <= 23 and minute <= 59 else None


ISO_WITH_ZONE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?"
                              r"(?:Z|[+-][0-9]{2}:?[0-9]{2})", re.IGNORECASE)
DATE_YMD_RE = re.compile(r"([0-9]{4})[/.\-]([0-9]{1,2})[/.\-]([0-9]{1,2})")
DATE_NUM_RE = re.compile(r"([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4}|[0-9]{2})")
SERVICE_ID_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
ERROR_CODE_RE = re.compile(r"[a-z_]{1,40}")


def real_date(year: int, month: int, day: int) -> tuple[int, int, int] | None:
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return year, month, day


def parse_when(date_cell: str, time_cell: str = "", order: str = "dmy") -> tuple[str | None, str]:
    """('YYYY-MM-DD HH:MM' local time or None, hint).

    hint is 'only_dmy' or 'only_mdy' when a d/m/y date reads as a real date in one order only (what main() uses to
    notice a month-first file), else ''. The time comes from `time_cell`, else from the date cell, else 12:00."""
    s = one_line(date_cell.replace(" ", " "))
    if not s:
        return None, ""
    if ISO_WITH_ZONE_RE.fullmatch(s) and not time_cell.strip():
        try:
            when = datetime.fromisoformat(re.sub(r"[zZ]$", "+00:00", s).replace(" ", "T")).astimezone(LOCAL_TZ)
        except ValueError:
            return None, ""
        return when.strftime("%Y-%m-%d %H:%M"), ""
    tokens = re.sub(r"(?<=[0-9])[tT](?=[0-9])", " ", s).replace(",", " ").split()
    date: tuple[int, int, int] | None = None
    hint = ""
    rest: list[str] = []
    found = False
    for token in tokens:
        if not found:
            m = DATE_YMD_RE.fullmatch(token)
            if m:
                found = True
                date = real_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                continue
            m = DATE_NUM_RE.fullmatch(token)
            if m:
                found = True
                a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                year += 2000 if year < 100 else 0
                dmy, mdy = real_date(year, b, a), real_date(year, a, b)
                hint = "only_dmy" if dmy and not mdy else "only_mdy" if mdy and not dmy else ""
                date = dmy if order == "dmy" else mdy
                continue
        rest.append(token)
    if date is None:
        return None, hint
    time_text = time_cell.strip() or " ".join(rest)
    clock = parse_time(time_text) if time_text else DEFAULT_TIME
    if clock is None:
        return None, hint
    return f"{date[0]:04d}-{date[1]:02d}-{date[2]:02d} {clock[0]:02d}:{clock[1]:02d}", hint


# ---------------------------------------------------------------- file and columns


def read_table(path: Path, delimiter: str | None = None) -> list[list[str]]:
    if path.suffix.lower() in (".xlsx", ".xls", ".ods", ".numbers"):
        raise ImportFailed("this is a spreadsheet file: export the sheet as CSV (UTF-8) and give that file")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ImportFailed(f"cannot read the file ({type(e).__name__})") from None
    try:
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFailed("the file is not UTF-8 text: export it again as CSV UTF-8") from None
    if delimiter is None:
        first = next((line for line in text.splitlines() if line.strip()), "")
        delimiter = max(DELIMITERS, key=first.count)          # a tie goes to the comma
    try:
        return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error:
        raise ImportFailed("the file is not a readable CSV (a broken quote or a stray character)") from None


def map_columns(header: list[str], overrides: dict[str, str]) -> tuple[dict[str, int], dict[str, list[int]]]:
    """({field: column index}, {field: other columns whose name also means that field}). Raises ImportFailed for an
    override that names no column."""
    keys = [header_key(h) for h in header]
    columns: dict[str, int] = {}
    for field, name in overrides.items():
        wanted = header_key(name)
        index = keys.index(wanted) if wanted and wanted in keys else column_index(name.strip())
        if index is None or index >= len(header):
            raise ImportFailed(f"--column {field}: the first row has no column with that name or letter")
        columns[field] = index
    by_alias = {alias: field for field, aliases in ALIASES.items() for alias in aliases}
    extra: dict[str, list[int]] = {}
    taken = set(columns.values())
    for index, key in enumerate(keys):
        field = by_alias.get(key)
        if field is None or index in taken:
            continue
        if field in columns:
            if field not in overrides:
                extra.setdefault(field, []).append(index)
            continue
        columns[field] = index
    return columns, extra


def load_catalog(path: str) -> tuple[set[str], dict[str, str | None]]:
    """(catalog ids, {name key: id, or None when two services share the name}). Empty when the file cannot be read:
    names are then sent as written and the server decides."""
    ids: set[str] = set()
    names: dict[str, str | None] = {}
    if not path:
        return ids, names
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        services = doc["services"] if isinstance(doc, dict) else doc
        services = [s for s in services if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]]
    except (OSError, ValueError, KeyError, TypeError):
        return ids, names
    for s in services:
        ids.add(s["id"])
        name = s.get("name_vi") if isinstance(s.get("name_vi"), str) else ""
        for variant in (name, re.sub(r"\s*\([^()]*\)\s*$", "", name)):
            key = header_key(variant)
            if key:
                names[key] = s["id"] if names.get(key, s["id"]) == s["id"] else None
    return ids, names


def build_visits(rows: list[list[str]], header_at: int, columns: dict[str, int], catalog_ids: set[str],
                 catalog_names: dict[str, str | None], order: str = "dmy",
                 ) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, str]], Counter]:
    """([(row number, visit)], [(row number, reason)], counts). Row numbers are the sheet's: the first row is 1."""
    visits: list[tuple[int, dict[str, Any]]] = []
    problems: list[tuple[int, str]] = []
    stats: Counter = Counter()
    lower_ids = {i.lower(): i for i in catalog_ids}

    for at in range(header_at + 1, len(rows)):
        row, number = rows[at], at + 1

        def cell(field: str) -> str:
            index = columns.get(field)
            return clean_cell(row[index]) if index is not None and index < len(row) else ""

        if not any(c.strip() for c in row):
            stats["empty_rows"] += 1
            continue
        stats["data_rows"] += 1
        visit: dict[str, Any] = {}
        reason = ""

        # Customer: the first id the row has and the script can read.
        code, zalo, phone = cell("customer_id"), cell("zalo_user_id"), cell("phone")
        if code and not code.startswith("cus_"):
            stats["foreign_customer_codes"] += 1        # the other program's own code: not an id of this system
            code = ""
        zalo_id = parse_zalo_id(zalo) if zalo else None
        phone_digits, restored = parse_phone(phone) if phone else (None, False)
        if code:
            visit["customer_id"] = code
        elif zalo_id:
            visit["zalo_user_id"] = zalo_id
        elif phone_digits:
            visit["phone"] = phone_digits
            stats["phones_with_restored_zero"] += 1 if restored else 0
        else:
            reason = "bad_zalo_id" if zalo else "bad_phone" if phone else "no_customer"

        when, hint = parse_when(cell("date"), cell("time"), order)
        if hint:
            stats[hint] += 1
        if when:
            visit["visited_at_local"] = when
        else:
            reason = reason or "bad_time"

        # Service: a catalog id, a name equal to a catalog name, or the name as written.
        service_id, service = cell("service_id"), one_line(cell("service"))
        if service_id:
            visit["service_id"] = lower_ids.get(service_id.lower(), service_id)
        if service and service.lower() in lower_ids:
            visit.setdefault("service_id", lower_ids[service.lower()])
        elif service:
            visit["service_name"] = service
            by_name = catalog_names.get(header_key(service))
            if "service_id" in visit:
                pass                                        # the id column decides; the name goes along
            elif by_name:
                visit["service_id"] = by_name
                stats["services_matched_by_name"] += 1
            elif not catalog_ids and SERVICE_ID_RE.fullmatch(service):
                visit["service_id"] = service               # no local catalog: it may be an id, the server knows
        if not service_id and not service or len(service) > MAX_SERVICE_NAME_CHARS:
            reason = reason or "bad_service"

        amount = parse_amount(cell("amount"))
        if amount is BAD:
            reason = reason or "bad_amount"
        elif amount is not None:
            visit["amount_vnd"] = amount

        duration = parse_duration(cell("duration"))
        if duration is BAD:
            reason = reason or "bad_duration"
        elif duration is not None:
            visit["duration_min"] = duration

        technician = one_line(cell("technician"))
        if len(technician) > MAX_TECHNICIAN_CHARS:
            reason = reason or "bad_technician"
        elif technician:
            visit["technician"] = technician

        external_id = one_line(cell("external_id"))
        if len(external_id) > MAX_EXTERNAL_ID_CHARS:
            reason = reason or "bad_external_id"
        elif external_id:
            visit["external_visit_id"] = external_id

        if reason:
            problems.append((number, reason))
        else:
            visits.append((number, visit))

    # One invoice id on several rows is an invoice with several lines, not one visit: the id cannot tell the rows
    # apart, so they go without it and the server tells repeats by customer, time and service.
    shared = {i for i, n in Counter(v["external_visit_id"] for _, v in visits if "external_visit_id" in v).items()
              if n > 1}
    for _, visit in visits:
        if visit.get("external_visit_id") in shared:
            del visit["external_visit_id"]
            stats["shared_external_ids"] += 1
    return visits, problems, stats


# ---------------------------------------------------------------- server (the same way as analyze_contacts.py)


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


def post_visits(server_url: str, token: str, chunk: list[tuple[int, dict[str, Any]]], dry_run: bool) -> dict[str, Any]:
    """One request. Raises ImportFailed with the HTTP status, the error code and, for a field of a row, the row
    number; never with the server's message or details (they may repeat a value of the request)."""
    body = json.dumps({"dry_run": dry_run, "visits": [v for _, v in chunk]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(server_url.rstrip("/") + "/staff/visits/import", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "X-Staff-Id": STAFF_ID,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            res = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8") or "{}").get("error", {})
        except (ValueError, AttributeError):
            err = {}
        err = err if isinstance(err, dict) else {}
        code = err.get("code") if isinstance(err.get("code"), str) and ERROR_CODE_RE.fullmatch(err["code"]) else ""
        details = err.get("details") if isinstance(err.get("details"), dict) else {}
        field = details.get("field") if isinstance(details.get("field"), str) else ""
        where = ""
        m = re.fullmatch(r"visits\[([0-9]+)\](?:\.([a-z_]{1,40}))?", field)
        if m and int(m.group(1)) < len(chunk):
            where = f", row {chunk[int(m.group(1))][0]}" + (f", field {m.group(2)}" if m.group(2) else "")
        hint = ""
        if e.code in (401, 403):
            hint = " (the server did not accept STAFF_TOKEN)"
        elif e.code == 409:
            hint = " (the server's database may be missing the visit history migration; restart the local stack)"
        raise ImportFailed(f"HTTP {e.code} {code}".rstrip() + where + hint) from None
    except (urllib.error.URLError, OSError) as e:
        raise ImportFailed(f"server not reachable ({type(e).__name__})") from None
    except ValueError:
        raise ImportFailed("the server's answer was not JSON") from None
    if not isinstance(res, dict) or not isinstance(res.get("unmatched", []), list):
        raise ImportFailed("the server's answer did not have the expected shape")
    return res


def send_all(server_url: str, token: str, visits: list[tuple[int, dict[str, Any]]], chunk_size: int, dry_run: bool,
             ) -> tuple[Counter, list[tuple[int, str]]]:
    """Posts every part. Returns (imported / duplicates / created_customers, [(row number, reason)])."""
    totals: Counter = Counter()
    unmatched: list[tuple[int, str]] = []
    parts = (len(visits) + chunk_size - 1) // chunk_size
    for part, start in enumerate(range(0, len(visits), chunk_size), 1):
        chunk = visits[start:start + chunk_size]
        try:
            res = post_visits(server_url, token, chunk, dry_run)
        except ImportFailed as e:
            raise ImportFailed(f"{e}; part {part} of {parts} failed, {start} rows were sent before it") from None
        for key in ("imported", "duplicates", "created_customers"):
            totals[key] += res[key] if isinstance(res.get(key), int) else 0
        for u in res.get("unmatched") or []:
            index = u.get("index") if isinstance(u, dict) else None
            if isinstance(index, int) and 0 <= index < len(chunk):
                reason = u.get("reason")
                known = isinstance(reason, str) and ERROR_CODE_RE.fullmatch(reason)
                unmatched.append((chunk[index][0], reason if known else "other"))
    return totals, unmatched


# ---------------------------------------------------------------- main


def print_problems(problems: list[tuple[int, str]]) -> None:
    by_reason: dict[str, list[int]] = {}
    for number, reason in problems:
        by_reason.setdefault(reason, []).append(number)
    print(f"rows that are not imported: {len(problems)}")
    for reason in sorted(by_reason, key=lambda r: (-len(by_reason[r]), r)):
        rows = by_reason[reason]
        print(f"  {reason} ({len(rows)}): row {row_ranges(rows)}")
        print(f"      {REASONS.get(reason, 'the server gave this reason')}")


def counts_line(totals: Counter, unmatched: int, dry_run: bool) -> str:
    head = "dry run, nothing written: would import" if dry_run else "written: imported"
    return (f"{head} {totals['imported']}, already there (duplicates) {totals['duplicates']}, "
            f"new customers {totals['created_customers']}, not imported {unmatched}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import past visits from a CSV file into the local server. "
                                             "Dry run unless --apply is given.")
    ap.add_argument("csv", help="the CSV file (UTF-8; the first row holds the column names)")
    ap.add_argument("--apply", action="store_true", help="after the dry run, write the visits")
    ap.add_argument("--server-url", help="local server (default SERVER_URL or http://127.0.0.1:8787)")
    ap.add_argument("--delimiter", help="column separator (default: the most frequent of , ; tab | on the first row)")
    ap.add_argument("--date-order", choices=["dmy", "mdy"], default="dmy",
                    help="how 03/04/2026 is read: dmy = 3 April (default), mdy = 4 March")
    ap.add_argument("--column", action="append", default=[], metavar="FIELD=NAME",
                    help="the column of a field, by its name in the file or its letter; fields: "
                         + ", ".join(ALIASES))
    ap.add_argument("--header-row", type=int, metavar="N",
                    help="the row that holds the column names (default: the first row with text)")
    ap.add_argument("--catalog", default=str(ROOT / "data/services.json"),
                    help="catalog JSON used to recognise service ids and names (default data/services.json)")
    ap.add_argument("--chunk-size", type=int, default=MAX_ROWS_PER_CALL,
                    help=f"rows per request, 1 to {MAX_ROWS_PER_CALL} (default {MAX_ROWS_PER_CALL})")
    args = ap.parse_args(argv)
    if not 1 <= args.chunk_size <= MAX_ROWS_PER_CALL:
        ap.error(f"--chunk-size must be from 1 to {MAX_ROWS_PER_CALL}")
    overrides: dict[str, str] = {}
    for item in args.column:
        field, sep, name = item.partition("=")
        if not sep or field.strip() not in ALIASES or not name.strip():
            ap.error("--column takes FIELD=NAME with FIELD one of: " + ", ".join(ALIASES))
        overrides[field.strip()] = name
    delimiter = {"tab": "\t", "\\t": "\t"}.get(args.delimiter, args.delimiter) if args.delimiter else None
    if delimiter is not None and len(delimiter) != 1:
        ap.error("--delimiter takes one character (or the word tab)")

    try:
        rows = read_table(Path(os.path.expanduser(args.csv)), delimiter)
        if args.header_row is not None:
            header_at = args.header_row - 1 if 1 <= args.header_row <= len(rows) else None
        else:
            header_at = next((i for i, row in enumerate(rows) if any(c.strip() for c in row)), None)
        if header_at is None:
            raise ImportFailed("the file is empty" if args.header_row is None else "the file has no such row")
        columns, extra = map_columns(rows[header_at], overrides)
        missing = []
        if not any(f in columns for f in ("customer_id", "zalo_user_id", "phone")):
            missing.append("the customer (a column named Số điện thoại, SĐT, Phone, Zalo ID or Mã khách hàng)")
        if "date" not in columns:
            missing.append("the date (a column named Ngày, Date or Thời gian)")
        if not any(f in columns for f in ("service_id", "service")):
            missing.append("the service (a column named Dịch vụ, Service or Mã dịch vụ)")
        if missing:
            raise ImportFailed(f"row {header_at + 1} must hold the column names, and no column was found for: "
                               + "; ".join(missing) + ". Use --column FIELD=NAME for a column with another name")
    except ImportFailed as e:
        print(f"import_visits: {e}", file=sys.stderr)
        return 1

    catalog_ids, catalog_names = load_catalog(args.catalog)
    visits, problems, stats = build_visits(rows, header_at, columns, catalog_ids, catalog_names, args.date_order)

    used = ", ".join(f"{FIELD_LABELS[f]} {column_letter(columns[f])}" for f in ALIASES if f in columns)
    unused = [column_letter(i) for i in range(len(rows[header_at])) if i not in columns.values()]
    print(f"file: {stats['data_rows']} rows with data after the column names on row {header_at + 1}"
          + (f", {stats['empty_rows']} empty rows skipped" if stats["empty_rows"] else ""))
    print(f"columns used: {used}" + (f"; not read: {', '.join(unused)}" if unused else ""))
    for field, others in extra.items():
        letters = ", ".join(column_letter(i) for i in others)
        print(f"  note: column {letters} also looks like the {FIELD_LABELS[field]}; column "
              f"{column_letter(columns[field])} is used (--column {field}=LETTER picks another)")
    if not catalog_ids and args.catalog:
        print("  note: the catalog file could not be read; service names are sent as written")

    # A file exported with month first reads wrong without a single error on days 1 to 12: stop instead of guessing.
    other = "mdy" if args.date_order == "dmy" else "dmy"
    if stats[f"only_{other}"] and not stats[f"only_{args.date_order}"]:
        how = "month/day/year" if other == "mdy" else "day/month/year"
        fix = "run again with --date-order mdy" if other == "mdy" else "run again without --date-order mdy"
        print(f"import_visits: {stats[f'only_{other}']} rows have a date that is only a real date when read as {how}, "
              f"and no row needs the other reading. If the whole file is {how}, {fix}. Nothing was sent.",
              file=sys.stderr)
        return 1

    for key, text in (("phones_with_restored_zero", "phone numbers of 9 digits that got their leading 0 back"),
                      ("foreign_customer_codes", "customer codes of another program left out (not a cus_ id)"),
                      ("services_matched_by_name", "service names equal to a catalog name, sent with the catalog id"),
                      ("shared_external_ids", "rows that share an external id with another row, sent without it")):
        if stats[key]:
            print(f"  {text}: {stats[key]}")
    print(f"read on this machine: {len(visits)} rows ready to send, {len(problems)} rows that cannot be sent")

    if not visits:
        if problems:
            print_problems(problems)
        print("nothing to send: nothing was written")
        return 0

    server = args.server_url or dev_var("SERVER_URL") or "http://127.0.0.1:8787"
    if not is_local_url(server):
        print("refusing to send visits to a non-local server", file=sys.stderr)
        return 1
    token = dev_var("STAFF_TOKEN")
    if not token:
        print("STAFF_TOKEN not found (environment or apps/server/.dev.vars)", file=sys.stderr)
        return 1

    parts = (len(visits) + args.chunk_size - 1) // args.chunk_size
    try:
        totals, unmatched = send_all(server, token, visits, args.chunk_size, dry_run=True)
    except ImportFailed as e:
        if problems:
            print_problems(problems)
        print(f"import_visits: dry run failed: {e}. Nothing was written.", file=sys.stderr)
        return 1
    print(counts_line(totals, len(problems) + len(unmatched), dry_run=True))
    if totals["created_customers"]:
        print("  note: a new customer is an empty customer made for a Zalo id the server does not know yet; if "
              "that column does not hold Zalo ids, do not apply")
    if parts > 1:
        print(f"  note: the file goes in {parts} parts; a dry run cannot see a repeat between two parts, so the "
              "written count can be lower")

    if not args.apply:
        if problems or unmatched:
            print_problems(problems + unmatched)
        print("dry run only: nothing was written. Run again with --apply to write the visits.")
        return 0
    if totals["imported"] == 0:
        if problems or unmatched:
            print_problems(problems + unmatched)
        print("nothing new to write: nothing was written")
        return 0

    try:
        totals, unmatched = send_all(server, token, visits, args.chunk_size, dry_run=False)
    except ImportFailed as e:
        print(f"import_visits: writing failed: {e}. The parts before it are written; sending the file again is "
              "safe, the server skips the visits it already has.", file=sys.stderr)
        return 1
    print(counts_line(totals, len(problems) + len(unmatched), dry_run=False))
    if problems or unmatched:
        print_problems(problems + unmatched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
