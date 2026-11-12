"""scripts/import_visits.py on synthetic CSV files (never a real export).

Each test writes a small CSV into a temp folder and runs the script against a tiny local HTTP server that stands in
for POST /staff/visits/import and answers the way docs/contracts.md 14.5 says. Names, phone numbers, Zalo ids and
invoice ids are made up. No real server, no real data folder."""

from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "import_visits.py"
TOKEN = "tok-test-visits"
CUS_A = "cus_0123456789ab0123456789abcdef"          # a customer the stub knows by id
ZALO_A = "700000000000000001"                        # a Zalo id the stub knows
PHONE_A, PHONE_B = "0900000001", "0900000002"        # phone numbers the stub knows
PHONE_UNKNOWN = "0900000099"
NAME_A, NAME_B = "Nguyễn Thị Thử Một", "Trần Văn Thử Hai"
CATALOG = {"services": [
    {"id": "goi-dau-duong-sinh", "name_vi": "Gội Đầu Dưỡng Sinh (Thư Giãn Sâu)"},
    {"id": "massage-chan", "name_vi": "Massage Chân"},
    {"id": "cham-soc-da-a", "name_vi": "Chăm Sóc Da (Cơ Bản)"},
    {"id": "cham-soc-da-b", "name_vi": "Chăm Sóc Da (Chuyên Sâu)"},
]}
VI_HEADER = ["Họ tên", "Số điện thoại", "Ngày", "Dịch vụ", "Thành tiền"]


def load():
    spec = importlib.util.spec_from_file_location("import_visits", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["import_visits"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


IV = load()


class Stub:
    """What the stand-in server knows and how it answers. `received` holds every request it got."""

    def __init__(self):
        self.received: list[dict] = []
        self.customer_ids = {CUS_A}
        self.zalo_ids = {f"p:{ZALO_A}"}
        self.phones = {PHONE_A, PHONE_B}
        self.stored: set = set()
        self.force: dict[tuple[int, int], str] = {}        # (request number, index) -> reason
        self.fail: dict[int, tuple[int, dict]] = {}        # request number -> (status, body)

    def answer(self, body: dict) -> tuple[int, dict]:
        call = len(self.received)                          # 1 for the first request
        if call in self.fail:
            return self.fail[call]
        imported = duplicates = created = 0
        unmatched, batch, new_zalo = [], set(), set()
        for i, v in enumerate(body["visits"]):
            if (call, i) in self.force:
                unmatched.append({"index": i, "reason": self.force[(call, i)]})
                continue
            if "customer_id" in v:
                who = v["customer_id"] if v["customer_id"] in self.customer_ids else None
            elif "zalo_user_id" in v:
                who = v["zalo_user_id"]
                if who not in self.zalo_ids and who not in new_zalo:
                    new_zalo.add(who)
                    created += 1
            elif "phone" in v:
                who = v["phone"] if v["phone"] in self.phones else None
            else:
                who = None
            if who is None:
                unmatched.append({"index": i, "reason": "no_customer"})
                continue
            key = v.get("external_visit_id") or (who, v["visited_at_local"],
                                                 v.get("service_id") or v.get("service_name"))
            if key in self.stored or key in batch:
                duplicates += 1
                continue
            batch.add(key)
            imported += 1
        if not body["dry_run"]:
            self.stored |= batch
            self.zalo_ids |= new_zalo
        return 200, {"imported": imported, "duplicates": duplicates, "created_customers": created,
                     "unmatched": unmatched}


class ImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thom-visits-"))
        self.catalog = self.tmp / "services.json"
        self.catalog.write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
        self.stub = Stub()
        self.url = self.start_server()
        (self.tmp / "dev.vars").write_text(f"STAFF_TOKEN={TOKEN}\nSERVER_URL={self.url}\n")
        self.env = {"THOMHOUSE_DEV_VARS": str(self.tmp / "dev.vars"), "SERVER_URL": "", "STAFF_TOKEN": ""}
        self._old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_server(self) -> str:
        stub = self.stub

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                stub.received.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                      "staff": self.headers.get("X-Staff-Id"), "body": body})
                status, doc = stub.answer(body)
                raw = json.dumps(doc).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def write_csv(self, header: list[str], rows: list[list[str]], name: str = "visits.csv", delimiter: str = ",",
                  encoding: str = "utf-8", lead: str = "") -> str:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)
        path = self.tmp / name
        path.write_bytes((lead + buf.getvalue()).encode(encoding))
        return str(path)

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = IV.main([*args, "--catalog", str(self.catalog)])
            except SystemExit as e:                        # argparse usage error
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def posted(self, request: int = 0) -> list[dict]:
        return self.stub.received[request]["body"]["visits"]

    def assert_no_leak(self, output: str, *values: str):
        for v in (TOKEN, NAME_A, NAME_B, PHONE_A, PHONE_B, PHONE_UNKNOWN, ZALO_A, CUS_A, *values):
            self.assertNotIn(v, output)


class CellParsingTests(unittest.TestCase):
    def test_amounts_that_are_read(self):
        for cell, want in [("450000", 450000), ("450.000", 450000), ("450,000", 450000), ("450,000đ", 450000),
                           ("450.000 đ", 450000), ("450 000 VND", 450000), ("1.250.000 ₫", 1250000),
                           ("450,000 VNĐ", 450000), ("450.000 đồng", 450000), ("450000.00", 450000),
                           ("450.000,00", 450000), ("450 000", 450000), ("0", 0), ("", None), ("   ", None)]:
            self.assertEqual(IV.parse_amount(cell), want, cell)

    def test_amounts_that_are_not_read(self):
        for cell in ["450k", "450K", "450 nghìn", "1tr2", "1,2tr", "1.5", "450.5", "-450000", "450,00,0",
                     "1.234,567", "450.000.00", "abc", "450000 x 2", "4.5e5"]:
            self.assertIs(IV.parse_amount(cell), IV.BAD, cell)

    def test_dates_and_times(self):
        for date, time, want in [
            ("09/10/2026", "", "2026-10-09 12:00"),                 # no time: noon
            ("9/10/2026 14:30", "", "2026-10-09 14:30"),
            ("09/10/2026 14:30:59", "", "2026-10-09 14:30"),
            ("09-10-2026", "8:05", "2026-10-09 08:05"),
            ("09.10.26", "", "2026-10-09 12:00"),
            ("2026-10-09", "14h30", "2026-10-09 14:30"),
            ("2026-10-09", "14h", "2026-10-09 14:00"),
            ("2026/10/09 2:30 PM", "", "2026-10-09 14:30"),
            ("09/10/2026", "2:30 CH", "2026-10-09 14:30"),
            ("09/10/2026", "9:15 SA", "2026-10-09 09:15"),
            ("09/10/2026", "12:10 AM", "2026-10-09 00:10"),
            ("2026-10-09T14:30:00", "", "2026-10-09 14:30"),
            ("2026-10-09T07:30:00Z", "", "2026-10-09 14:30"),       # an offset is turned into local time
            ("2026-10-09T23:30:00+09:00", "", "2026-10-09 21:30"),
            ("09/10/2026 09:00", "15:45", "2026-10-09 15:45"),      # the time column wins
        ]:
            self.assertEqual(IV.parse_when(date, time)[0], want, (date, time))

    def test_dates_that_are_not_read(self):
        for date, time in [("", ""), ("", "14:30"), ("hôm qua", ""), ("31/02/2026", ""), ("09/10", ""),
                           ("13/13/2026", ""), ("09/10/2026 25:00", ""), ("09/10/2026", "14:75"),
                           ("09/10/2026", "chiều"), ("46304", "")]:
            self.assertIsNone(IV.parse_when(date, time)[0], (date, time))

    def test_date_order_and_the_hint_for_a_month_first_file(self):
        self.assertEqual(IV.parse_when("10/09/2026", order="mdy"), ("2026-10-09 12:00", ""))
        self.assertEqual(IV.parse_when("10/09/2026", order="dmy"), ("2026-09-10 12:00", ""))
        self.assertEqual(IV.parse_when("25/10/2026"), ("2026-10-25 12:00", "only_dmy"))
        self.assertEqual(IV.parse_when("10/25/2026"), (None, "only_mdy"))
        self.assertEqual(IV.parse_when("10/25/2026", order="mdy"), ("2026-10-25 12:00", "only_mdy"))

    def test_phone_numbers(self):
        for cell in ["0900000001", "090 000 0001", "090.000.0001", "(090) 000-0001", "+84900000001", "+84 900 000 001",
                     "84900000001"]:
            self.assertEqual(IV.parse_phone(cell), (PHONE_A, False), cell)
        self.assertEqual(IV.parse_phone("900000001"), (PHONE_A, True))         # the sheet dropped the leading 0
        self.assertEqual(IV.parse_phone("02800000001"), ("02800000001", False))
        self.assertEqual(IV.parse_phone("100000001"), ("100000001", False))    # 9 digits pass as they are: the
        for cell in ["12345", "09000000ab", "090000000123", "không có"]:       # server decides who has the number
            self.assertEqual(IV.parse_phone(cell), (None, False), cell)

    def test_zalo_ids(self):
        self.assertEqual(IV.parse_zalo_id(ZALO_A), f"p:{ZALO_A}")
        self.assertEqual(IV.parse_zalo_id(f"P:{ZALO_A} "), f"p:{ZALO_A}")
        for cell in ["g:123456", "abc", "p:", "12 34", "p:" + "9" * 33]:
            self.assertIsNone(IV.parse_zalo_id(cell), cell)

    def test_durations(self):
        for cell, want in [("60", 60), ("60 phút", 60), ("90p", 90), ("45'", 45), ("60.0", 60), ("75 min", 75),
                           ("1h", 60), ("1h30", 90), ("1 giờ 30 phút", 90), ("2 tiếng", 120), ("1440", 1440),
                           ("", None)]:
            self.assertEqual(IV.parse_duration(cell), want, cell)
        for cell in ["0", "1441", "abc", "1.5h", "-60", "25h"]:
            self.assertIs(IV.parse_duration(cell), IV.BAD, cell)

    def test_sheet_text_markers_are_removed_from_a_cell(self):
        self.assertEqual(IV.clean_cell(f'="{PHONE_A}"'), PHONE_A)
        self.assertEqual(IV.clean_cell(f"'{PHONE_A}"), PHONE_A)
        self.assertEqual(IV.clean_cell(f"  {PHONE_A} "), PHONE_A)

    def test_row_ranges_and_column_letters(self):
        self.assertEqual(IV.row_ranges([9, 2, 3, 4, 4, 12, 13]), "2-4, 9, 12-13")
        self.assertEqual([IV.column_letter(i) for i in (0, 25, 26, 27, 701, 702)], ["A", "Z", "AA", "AB", "ZZ", "AAA"])
        self.assertEqual([IV.column_index(s) for s in ("A", "z", "AA", "AAA", "A1", "")], [0, 25, 26, 702, None, None])


class ColumnMappingTests(unittest.TestCase):
    FIELDS = ["customer_id", "zalo_user_id", "phone", "date", "time", "service_id", "service", "amount", "technician",
              "duration", "external_id"]

    def columns(self, header: list[str], **overrides: str) -> dict[str, int]:
        return IV.map_columns(header, overrides)[0]

    def test_vietnamese_names_match_without_accents_case_and_punctuation(self):
        header = ["Mã khách hàng", "ZALO ID", "Số điện thoại", "Ngày", "Giờ", "Mã dịch vụ", "Dịch vụ", "Thành tiền",
                  "Kỹ thuật viên", "Thời lượng", "Mã hóa đơn"]
        self.assertEqual(self.columns(header), {f: i for i, f in enumerate(self.FIELDS)})
        plain = ["ma khach hang", "zalo_id", "SO DIEN THOAI", "NGÀY ", " giờ", "ma-dich-vu", "DICH VU:",
                 "thanh_tien (VND)", "KTV", "Số phút", "Số hoá đơn"]
        got = self.columns(plain)
        self.assertEqual({f: got.get(f) for f in self.FIELDS if f != "amount"},
                         {f: i for i, f in enumerate(self.FIELDS) if f != "amount"})
        self.assertNotIn("amount", got)                    # "thanh tien vnd" is not a name the script knows

    def test_english_names_and_the_contract_field_names(self):
        english = ["Customer ID", "Zalo User ID", "Phone", "Date", "Time", "Service ID", "Service", "Amount",
                   "Technician", "Duration", "External ID"]
        self.assertEqual(self.columns(english), {f: i for i, f in enumerate(self.FIELDS)})
        contract = ["customer_id", "zalo_user_id", "phone", "visited_at_local", "service_id", "service_name",
                    "amount_vnd", "technician", "duration_min", "external_visit_id"]
        self.assertEqual(self.columns(contract),
                         {"customer_id": 0, "zalo_user_id": 1, "phone": 2, "date": 3, "service_id": 4, "service": 5,
                          "amount": 6, "technician": 7, "duration": 8, "external_id": 9})

    def test_a_name_column_and_a_bare_zalo_column_are_never_mapped(self):
        got = self.columns(["Khách hàng", "Họ tên", "Tên", "Zalo", "Ghi chú", "SĐT", "Ngày", "Dịch vụ"])
        self.assertEqual(got, {"phone": 5, "date": 6, "service": 7})

    def test_the_left_column_wins_and_the_others_are_reported(self):
        columns, extra = IV.map_columns(["SĐT", "Ngày", "Dịch vụ", "Điện thoại", "Ngày tạo"], {})
        self.assertEqual(columns, {"phone": 0, "date": 1, "service": 2})
        self.assertEqual(extra, {"phone": [3], "date": [4]})

    def test_column_option_by_name_or_letter(self):
        header = ["SĐT", "Ngày", "Dịch vụ", "Khách đưa", "Ngày làm thật"]
        got = self.columns(header, amount="khach dua", date="E")
        self.assertEqual(got, {"phone": 0, "date": 4, "service": 2, "amount": 3})
        for bad in ("Không có cột này", "K"):
            with self.assertRaises(IV.ImportFailed):
                self.columns(header, amount=bad)

    def test_catalog_names_with_and_without_the_bracket_part(self):
        ids, names = IV.load_catalog(str(ROOT / "data" / "services.json"))
        self.assertTrue(ids)                               # the project's catalog is readable
        tmp = Path(tempfile.mkdtemp(prefix="thom-visits-cat-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "c.json").write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
        ids, names = IV.load_catalog(str(tmp / "c.json"))
        self.assertEqual(ids, {"goi-dau-duong-sinh", "massage-chan", "cham-soc-da-a", "cham-soc-da-b"})
        self.assertEqual(names["goi dau duong sinh"], "goi-dau-duong-sinh")
        self.assertEqual(names["goi dau duong sinh thu gian sau"], "goi-dau-duong-sinh")
        self.assertIsNone(names["cham soc da"])            # two services share the short name: not mapped
        self.assertEqual(IV.load_catalog(str(tmp / "missing.json")), (set(), {}))
        (tmp / "broken.json").write_text("{not json")
        self.assertEqual(IV.load_catalog(str(tmp / "broken.json")), (set(), {}))


class DryRunAndApplyTests(ImportCase):
    def four_rows(self) -> str:
        return self.write_csv(VI_HEADER, [
            [NAME_A, PHONE_A, "09/10/2026 14:30", "Massage Chân", "470.000"],
            [NAME_B, PHONE_B, "10/10/2026", "Tắm trắng thử nghiệm", "1,250,000đ"],
            ["Lê Thử Ba", PHONE_UNKNOWN, "11/10/2026", "Massage Chân", ""],
            [NAME_A, PHONE_A, "12/10/2026", "Massage Chân", "380k"],
        ])

    def test_dry_run_posts_only_a_dry_run_and_prints_counts_and_row_numbers(self):
        code, out, err = self.run_main(self.four_rows())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(self.stub.received), 1)
        r = self.stub.received[0]
        self.assertEqual((r["path"], r["auth"], r["staff"]),
                         ("/staff/visits/import", f"Bearer {TOKEN}", "visits-import"))
        self.assertIs(r["body"]["dry_run"], True)
        self.assertEqual(r["body"]["visits"], [
            {"phone": PHONE_A, "visited_at_local": "2026-10-09 14:30", "service_id": "massage-chan",
             "service_name": "Massage Chân", "amount_vnd": 470000},
            {"phone": PHONE_B, "visited_at_local": "2026-10-10 12:00", "service_name": "Tắm trắng thử nghiệm",
             "amount_vnd": 1250000},
            {"phone": PHONE_UNKNOWN, "visited_at_local": "2026-10-11 12:00", "service_id": "massage-chan",
             "service_name": "Massage Chân"},
        ])
        self.assertIn("file: 4 rows with data after the column names on row 1", out)
        self.assertIn("columns used: phone B, date C, service D, amount E; not read: A", out)
        self.assertIn("read on this machine: 3 rows ready to send, 1 rows that cannot be sent", out)
        self.assertIn("dry run, nothing written: would import 2, already there (duplicates) 0, new customers 0, "
                      "not imported 2", out)
        self.assertIn("  no_customer (1): row 4\n", out)
        self.assertIn("  bad_amount (1): row 5\n", out)
        self.assertIn("short forms such as 450k or 1tr2 are not", out)     # the fixed explanation, not the cell
        self.assertIn("dry run only: nothing was written", out)
        self.assert_no_leak(out + err, "380k", "Lê Thử Ba", "Massage", "Tắm trắng", "470", "1,250,000",
                            "Họ tên", "Thành tiền")
        self.assertEqual(self.stub.stored, set())

    def test_apply_posts_the_dry_run_first_and_then_writes_the_same_rows(self):
        code, out, err = self.run_main(self.four_rows(), "--apply")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([r["body"]["dry_run"] for r in self.stub.received], [True, False])
        self.assertEqual(self.posted(0), self.posted(1))
        self.assertEqual(len(self.stub.stored), 2)
        self.assertIn("dry run, nothing written: would import 2", out)
        self.assertIn("written: imported 2, already there (duplicates) 0, new customers 0, not imported 2", out)
        self.assertIn("  no_customer (1): row 4\n", out)
        self.assertNotIn("dry run only", out)
        self.assert_no_leak(out + err, "380k", "Lê Thử Ba", "Massage", "Tắm trắng")

    def test_second_apply_of_the_same_file_writes_nothing(self):
        path = self.four_rows()
        self.run_main(path, "--apply")
        del self.stub.received[:]
        code, out, _err = self.run_main(path, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual([r["body"]["dry_run"] for r in self.stub.received], [True])      # no write request at all
        self.assertIn("would import 0, already there (duplicates) 2", out)
        self.assertIn("nothing new to write: nothing was written", out)

    def test_parts_keep_the_sheets_row_numbers(self):
        rows = [[f"Khách Thử {i}", PHONE_A, f"{i:02d}/10/2026", "Massage Chân", "100000"] for i in range(1, 6)]
        self.stub.force[(2, 1)] = "bad_time"               # second request, second visit: sheet row 5
        self.stub.force[(3, 0)] = "bad_service"            # third request, first visit: sheet row 6
        code, out, _err = self.run_main(self.write_csv(VI_HEADER, rows), "--chunk-size", "2")
        self.assertEqual(code, 0)
        self.assertEqual([len(r["body"]["visits"]) for r in self.stub.received], [2, 2, 1])
        self.assertEqual([v["visited_at_local"][:10] for r in self.stub.received for v in r["body"]["visits"]],
                         [f"2026-10-{i:02d}" for i in range(1, 6)])
        self.assertIn("would import 3, already there (duplicates) 0, new customers 0, not imported 2", out)
        self.assertIn("  bad_time (1): row 5\n", out)
        self.assertIn("  bad_service (1): row 6\n", out)
        self.assertIn("the file goes in 3 parts", out)

    def test_apply_in_parts_sends_every_dry_run_before_the_first_write(self):
        rows = [[f"Khách Thử {i}", PHONE_A, f"{i:02d}/10/2026", "Massage Chân", "100000"] for i in range(1, 4)]
        code, out, _err = self.run_main(self.write_csv(VI_HEADER, rows), "--chunk-size", "2", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual([(r["body"]["dry_run"], len(r["body"]["visits"])) for r in self.stub.received],
                         [(True, 2), (True, 1), (False, 2), (False, 1)])
        self.assertIn("written: imported 3", out)

    def test_many_bad_rows_are_listed_as_ranges(self):
        rows = [[NAME_A, PHONE_A, "09/10/2026", "Massage Chân", "100k"] for _ in range(4)]
        rows.insert(2, [NAME_A, PHONE_A, "09/10/2026", "Massage Chân", "100000"])
        rows.append([NAME_A, PHONE_A, "không rõ", "Massage Chân", "100000"])
        code, out, _err = self.run_main(self.write_csv(VI_HEADER, rows))
        self.assertEqual(code, 0)
        self.assertIn("  bad_amount (4): row 2-3, 5-6\n", out)
        self.assertIn("  bad_time (1): row 7\n", out)
        self.assertLess(out.index("bad_amount (4)"), out.index("bad_time (1)"))            # most rows first

    def test_file_without_a_usable_row_sends_nothing(self):
        path = self.write_csv(VI_HEADER, [[NAME_A, "", "09/10/2026", "Massage Chân", ""],
                                          [NAME_B, PHONE_B, "", "Massage Chân", ""]])
        code, out, _err = self.run_main(path, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.stub.received, [])
        self.assertIn("  no_customer (1): row 2\n", out)
        self.assertIn("  bad_time (1): row 3\n", out)
        self.assertIn("nothing to send: nothing was written", out)

    def test_new_customers_are_counted_and_explained(self):
        path = self.write_csv(["Zalo ID", "Ngày", "Dịch vụ"], [["700000000000000777", "09/10/2026", "Massage Chân"],
                                                               [ZALO_A, "09/10/2026", "Massage Chân"]])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual([v["zalo_user_id"] for v in self.posted()], ["p:700000000000000777", f"p:{ZALO_A}"])
        self.assertIn("would import 2, already there (duplicates) 0, new customers 1, not imported 0", out)
        self.assertIn("a new customer is an empty customer made for a Zalo id", out)
        self.assert_no_leak(out, "700000000000000777")


class RowBuildingTests(ImportCase):
    def test_semicolon_file_with_a_bom_and_english_names(self):
        path = self.write_csv(["Phone", "Date", "Time", "Service", "Amount", "Technician", "Duration", "Invoice"],
                              [[PHONE_A, "2026-10-09", "14:30", "massage-chan", "450000", "  Hoa   Thử ", "60 phút",
                                "POS-0001"]], delimiter=";", encoding="utf-8-sig")
        code, _out, err = self.run_main(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.posted(), [{"phone": PHONE_A, "visited_at_local": "2026-10-09 14:30",
                                          "service_id": "massage-chan", "amount_vnd": 450000, "duration_min": 60,
                                          "technician": "Hoa Thử", "external_visit_id": "POS-0001"}])

    def test_tab_and_utf16_files_are_read_and_the_delimiter_can_be_given(self):
        row = [PHONE_A, "09/10/2026", "Massage Chân"]
        code, _out, _err = self.run_main(self.write_csv(["SĐT", "Ngày", "Dịch vụ"], [row], delimiter="\t",
                                                        encoding="utf-16"))
        self.assertEqual(code, 0)
        self.assertEqual(self.posted()[0]["phone"], PHONE_A)
        # One column name holds a comma: the guess would be wrong, the option settles it.
        path = self.write_csv(["SĐT|Ngày|Dịch vụ, liệu trình"], [["|".join(row)]], name="pipe.csv")
        Path(path).write_text("SĐT|Ngày|Dịch vụ\n" + "|".join(row) + "\n", encoding="utf-8")
        code, _out, _err = self.run_main(path, "--delimiter", "|")
        self.assertEqual(code, 0)
        self.assertEqual(self.posted(1)[0]["visited_at_local"], "2026-10-09 12:00")

    def test_customer_comes_from_the_first_readable_identifier(self):
        header = ["Mã khách hàng", "Zalo ID", "SĐT", "Ngày", "Dịch vụ"]
        day, service = "09/10/2026", "Massage Chân"
        path = self.write_csv(header, [
            [CUS_A, ZALO_A, PHONE_A, day, service],         # this system's id wins
            ["KH000123", ZALO_A, PHONE_A, day, service],    # another program's code is left out: the Zalo id
            ["KH000124", "", PHONE_B, day, service],        # ... or the phone
            ["", "g:123456", PHONE_B, day, service],        # a group id cannot be a customer: the phone
            ["", "g:123456", "", day, service],             # nothing else: bad_zalo_id
            ["", "", "12345", day, service],                # bad_phone
            ["KH000125", "", "", day, service],             # no_customer
            ["", "", "900000002", day, service],            # the sheet dropped the leading 0
        ])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        keep = ("customer_id", "zalo_user_id", "phone")
        self.assertEqual([{k: v[k] for k in keep if k in v} for v in self.posted()],
                         [{"customer_id": CUS_A}, {"zalo_user_id": f"p:{ZALO_A}"}, {"phone": PHONE_B},
                          {"phone": PHONE_B}, {"phone": PHONE_B}])
        self.assertIn("  bad_zalo_id (1): row 6\n", out)
        self.assertIn("  bad_phone (1): row 7\n", out)
        self.assertIn("  no_customer (1): row 8\n", out)
        self.assertIn("phone numbers of 9 digits that got their leading 0 back: 1", out)
        self.assertIn("customer codes of another program left out (not a cus_ id): 3", out)
        self.assert_no_leak(out, "KH000123", "g:123456", "12345", "900000002")

    def test_service_goes_by_catalog_id_catalog_name_or_as_written(self):
        header = ["SĐT", "Ngày", "Mã dịch vụ", "Dịch vụ"]
        day = "09/10/2026"
        path = self.write_csv(header, [
            [PHONE_A, day, "", "massage-chan"],                     # a catalog id in the service column
            [PHONE_A, day, "", "  gội đầu   dưỡng sinh "],          # a catalog name without its bracket part
            [PHONE_A, day, "", "GOI DAU DUONG SINH (thu gian sau)"],
            [PHONE_A, day, "", "Chăm sóc da"],                      # two services share this name: as written
            [PHONE_A, day, "", "Combo thử nghiệm 90 phút"],         # not in the catalog: as written
            [PHONE_A, day, "Massage-Chan", "Chân thư giãn"],        # the id column decides, the name goes along
            [PHONE_A, day, "ma-ngoai-danh-muc", ""],                # the server decides (bad_service there)
            [PHONE_A, day, "", ""],                                 # bad_service here
            [PHONE_A, day, "", "x" * 121],                          # too long for the server
        ])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        keep = ("service_id", "service_name")
        self.assertEqual([{k: v[k] for k in keep if k in v} for v in self.posted()], [
            {"service_id": "massage-chan"},
            {"service_id": "goi-dau-duong-sinh", "service_name": "gội đầu dưỡng sinh"},
            {"service_id": "goi-dau-duong-sinh", "service_name": "GOI DAU DUONG SINH (thu gian sau)"},
            {"service_name": "Chăm sóc da"},
            {"service_name": "Combo thử nghiệm 90 phút"},
            {"service_id": "massage-chan", "service_name": "Chân thư giãn"},
            {"service_id": "ma-ngoai-danh-muc"},
        ])
        self.assertIn("  bad_service (2): row 9-10\n", out)
        self.assertIn("service names equal to a catalog name, sent with the catalog id: 2", out)

    def test_without_a_readable_catalog_names_are_sent_as_written(self):
        self.catalog.unlink()
        path = self.write_csv(["SĐT", "Ngày", "Dịch vụ"], [[PHONE_A, "09/10/2026", "Massage Chân"],
                                                           [PHONE_A, "10/10/2026", "massage-chan"]])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual(self.posted()[0]["service_name"], "Massage Chân")
        self.assertNotIn("service_id", self.posted()[0])
        self.assertEqual(self.posted()[1], {"phone": PHONE_A, "visited_at_local": "2026-10-10 12:00",
                                            "service_id": "massage-chan", "service_name": "massage-chan"})
        self.assertIn("the catalog file could not be read", out)

    def test_optional_fields_and_their_limits(self):
        header = ["SĐT", "Ngày", "Dịch vụ", "KTV", "Thời lượng", "Mã hóa đơn"]
        base = [PHONE_A, "09/10/2026", "Massage Chân"]
        path = self.write_csv(header, [
            [*base, "Hoa Thử", "1h30", "HD-0001"],
            [*base, "", "", ""],
            [*base, "T" * 61, "60", "HD-0002"],
            [*base, "Hoa Thử", "cả buổi", "HD-0003"],
            [*base, "Hoa Thử", "60", "H" * 101],
            [*base, "T" * 60, "1440", "H" * 100],
        ])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual(self.posted()[0], {"phone": PHONE_A, "visited_at_local": "2026-10-09 12:00",
                                            "service_id": "massage-chan", "service_name": "Massage Chân",
                                            "technician": "Hoa Thử", "duration_min": 90,
                                            "external_visit_id": "HD-0001"})
        self.assertEqual(self.posted()[1], {"phone": PHONE_A, "visited_at_local": "2026-10-09 12:00",
                                            "service_id": "massage-chan", "service_name": "Massage Chân"})
        self.assertEqual((self.posted()[2]["technician"], self.posted()[2]["duration_min"],
                          self.posted()[2]["external_visit_id"]), ("T" * 60, 1440, "H" * 100))
        self.assertEqual(len(self.posted()), 3)
        self.assertIn("  bad_technician (1): row 4\n", out)
        self.assertIn("  bad_duration (1): row 5\n", out)
        self.assertIn("  bad_external_id (1): row 6\n", out)
        self.assert_no_leak(out, "Hoa Thử", "HD-000", "cả buổi")

    def test_invoice_id_shared_by_several_rows_is_not_sent(self):
        header = ["SĐT", "Ngày", "Dịch vụ", "Mã hóa đơn"]
        path = self.write_csv(header, [
            [PHONE_A, "09/10/2026", "Massage Chân", "HD-0007"],
            [PHONE_A, "09/10/2026", "Gội đầu dưỡng sinh", "HD-0007"],
            [PHONE_B, "09/10/2026", "Massage Chân", "HD-0008"],
        ])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual([v.get("external_visit_id") for v in self.posted()], [None, None, "HD-0008"])
        self.assertIn("would import 3", out)
        self.assertIn("rows that share an external id with another row, sent without it: 2", out)

    def test_empty_rows_are_skipped_and_title_rows_need_header_row(self):
        path = self.tmp / "titled.csv"
        path.write_text("BÁO CÁO THỬ NGHIỆM,,\n,,\nSĐT,Ngày,Dịch vụ\n"
                        f"{PHONE_A},09/10/2026,Massage Chân\n,,\n{PHONE_UNKNOWN},10/10/2026,Massage Chân\n",
                        encoding="utf-8")
        code, out, err = self.run_main(str(path))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("row 1 must hold the column names", err)
        self.assertIn("--column FIELD=NAME", err)
        self.assertEqual(self.stub.received, [])
        self.assert_no_leak(err, "BÁO CÁO")

        code, out, err = self.run_main(str(path), "--header-row", "3")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("file: 2 rows with data after the column names on row 3, 1 empty rows skipped", out)
        self.assertIn("  no_customer (1): row 6\n", out)       # the row number the sheet shows
        code, _out, err = self.run_main(str(path), "--header-row", "9")
        self.assertEqual(code, 1)
        self.assertIn("no such row", err)

    def test_two_columns_for_one_field_are_reported_by_letter(self):
        path = self.write_csv(["SĐT", "Ngày", "Dịch vụ", "Điện thoại"],
                              [[PHONE_A, "09/10/2026", "Massage Chân", PHONE_B]])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual(self.posted()[0]["phone"], PHONE_A)
        self.assertIn("note: column D also looks like the phone; column A is used (--column phone=LETTER", out)
        code, _out, _err = self.run_main(path, "--column", "phone=D")
        self.assertEqual(self.posted(1)[0]["phone"], PHONE_B)

    def test_month_first_file_is_stopped_and_date_order_reads_it(self):
        path = self.write_csv(["Phone", "Date", "Service"], [[PHONE_A, "10/09/2026", "Massage Chân"],
                                                            [PHONE_A, "10/25/2026 14:30", "Massage Chân"]])
        code, _out, err = self.run_main(path, "--apply")
        self.assertEqual(code, 1)
        self.assertIn("--date-order mdy", err)
        self.assertIn("Nothing was sent", err)
        self.assertEqual(self.stub.received, [])

        code, _out, err = self.run_main(path, "--date-order", "mdy")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([v["visited_at_local"] for v in self.posted()], ["2026-10-09 12:00", "2026-10-25 14:30"])

    def test_mixed_date_orders_are_reported_row_by_row(self):
        path = self.write_csv(["Phone", "Date", "Service"], [[PHONE_A, "25/10/2026", "Massage Chân"],
                                                            [PHONE_A, "10/25/2026", "Massage Chân"]])
        code, out, _err = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual([v["visited_at_local"] for v in self.posted()], ["2026-10-25 12:00"])
        self.assertIn("  bad_time (1): row 3\n", out)


class RefusalTests(ImportCase):
    def simple(self) -> str:
        return self.write_csv(VI_HEADER, [[NAME_A, PHONE_A, "09/10/2026", "Massage Chân", "450000"],
                                          [NAME_B, PHONE_B, "10/10/2026", "Massage Chân", "450000"]])

    def test_missing_required_columns_stop_before_any_request(self):
        path = self.write_csv(["Họ tên", "Ghi chú", "Thành tiền"], [[NAME_A, "ghi chú thử", "450000"]])
        code, out, err = self.run_main(path)
        self.assertEqual((code, out), (1, ""))
        for part in ("the customer", "the date", "the service"):
            self.assertIn(part, err)
        self.assertEqual(self.stub.received, [])
        self.assert_no_leak(err, "ghi chú thử")

    def test_files_that_cannot_be_read(self):
        (self.tmp / "empty.csv").write_text("\n\n")
        (self.tmp / "latin.csv").write_bytes("SĐT,Ngày,Dịch vụ\n".encode("cp1258", errors="replace") + b"\xff\xfe\xfa")
        (self.tmp / "book.xlsx").write_bytes(b"PK\x03\x04")
        for name, part in (("empty.csv", "the file is empty"), ("latin.csv", "CSV UTF-8"),
                           ("book.xlsx", "export the sheet as CSV"), ("missing.csv", "cannot read the file")):
            code, out, err = self.run_main(str(self.tmp / name))
            self.assertEqual((code, out), (1, ""), name)
            self.assertIn(part, err, name)
        self.assertEqual(self.stub.received, [])

    def test_missing_token(self):
        (self.tmp / "dev.vars").write_text(f"SERVER_URL={self.url}\n")
        code, _out, err = self.run_main(self.simple())
        self.assertEqual(code, 1)
        self.assertIn("STAFF_TOKEN not found", err)
        self.assertEqual(self.stub.received, [])

    def test_a_remote_server_is_refused(self):
        for url in ("https://bot.example.com", "http://192.168.1.20:8787"):
            code, _out, err = self.run_main(self.simple(), "--server-url", url, "--apply")
            self.assertEqual(code, 1)
            self.assertIn("non-local", err)
        (self.tmp / "dev.vars").write_text(f"STAFF_TOKEN={TOKEN}\nSERVER_URL=https://bot.example.com\n")
        code, _out, err = self.run_main(self.simple())
        self.assertEqual(code, 1)
        self.assertIn("non-local", err)
        self.assertEqual(self.stub.received, [])

    def test_server_error_shows_status_code_and_row_and_never_the_message(self):
        self.stub.fail[1] = (422, {"error": {"code": "validation_failed",
                                             "message": f"technician of {NAME_B} must be one line",
                                             "details": {"field": "visits[1].technician"}}})
        code, out, err = self.run_main(self.simple(), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("dry run failed: HTTP 422 validation_failed, row 3, field technician", err)
        self.assertIn("Nothing was written", err)
        self.assertEqual(len(self.stub.received), 1)       # no write after a failed dry run
        self.assert_no_leak(out + err, "must be one line")

    def test_token_refused_and_missing_migration_get_a_hint(self):
        self.stub.fail[1] = (401, {"error": {"code": "unauthorized", "message": "bad token"}})
        code, _out, err = self.run_main(self.simple())
        self.assertEqual(code, 1)
        self.assertIn("HTTP 401 unauthorized (the server did not accept STAFF_TOKEN)", err)
        self.stub.fail[2] = (409, {"error": {"code": "invalid_state", "message": "visits table missing"}})
        code, _out, err = self.run_main(self.simple())
        self.assertEqual(code, 1)
        self.assertIn("HTTP 409 invalid_state", err)
        self.assertIn("migration", err)
        self.assert_no_leak(err)

    def test_failing_write_part_stops_and_says_a_rerun_is_safe(self):
        rows = [[f"Khách Thử {i}", PHONE_A, f"{i:02d}/10/2026", "Massage Chân", "100000"] for i in range(1, 6)]
        self.stub.fail[5] = (500, {"error": {"code": "internal", "message": "internal error"}})
        code, out, err = self.run_main(self.write_csv(VI_HEADER, rows), "--chunk-size", "2", "--apply")
        self.assertEqual(code, 1)
        # Three dry runs, then the first write went in and the second failed: the third is never sent.
        self.assertEqual([r["body"]["dry_run"] for r in self.stub.received], [True, True, True, False, False])
        self.assertEqual(len(self.stub.stored), 2)
        self.assertIn("writing failed: HTTP 500 internal; part 2 of 3 failed, 2 rows were sent before it", err)
        self.assertIn("sending the file again is safe", err)
        self.assertNotIn("written: imported", out)

    def test_unreachable_server_and_an_answer_that_is_not_json(self):
        with socket.socket() as s:                         # a port that was just free: nothing listens on it now
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code, _out, err = self.run_main(self.simple(), "--server-url", f"http://127.0.0.1:{port}")
        self.assertEqual(code, 1)
        self.assertIn("server not reachable", err)
        self.stub.fail[1] = (200, ["not", "an", "object"])
        code, _out, err = self.run_main(self.simple())
        self.assertEqual(code, 1)
        self.assertIn("did not have the expected shape", err)

    def test_usage_errors_exit_2(self):
        path = self.simple()
        for args in (["--chunk-size", "0"], ["--chunk-size", "2001"], ["--column", "amount"],
                     ["--column", "price=Thành tiền"], ["--delimiter", "::"], ["--date-order", "ymd"]):
            code, _out, _err = self.run_main(path, *args)
            self.assertEqual(code, 2, args)
        self.assertEqual(self.stub.received, [])

    def test_environment_wins_over_the_dev_vars_file(self):
        (self.tmp / "dev.vars").write_text("STAFF_TOKEN=tok-from-file\nSERVER_URL=http://127.0.0.1:9\n")
        os.environ.update({"STAFF_TOKEN": "tok-from-env", "SERVER_URL": self.url})
        code, out, err = self.run_main(self.simple())
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stub.received[0]["auth"], "Bearer tok-from-env")
        self.assertNotIn("tok-from", out + err)


if __name__ == "__main__":
    unittest.main()
