"""data/menu-images.json (the menu slide index) and scripts/build_menu_images.py.

The index tests read the real repository files. The build tests use a temp home and a fake `sips` that copies the
source file, so they run anywhere and never touch ~/.thomhouse-bot."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "menu-images.json"
CATALOG = ROOT / "data" / "services.json"
SCRIPT = ROOT / "scripts" / "build_menu_images.py"
GROUPS = {"facial", "healing", "thu-gian-toc", "hair-removal"}
KINDS = {"cover", "price_list", "service", "process", "other"}


def load_script():
    spec = importlib.util.spec_from_file_location("build_menu_images", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MenuIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads(INDEX.read_text(encoding="utf-8"))
        cls.catalog_ids = {s["id"] for s in json.loads(CATALOG.read_text(encoding="utf-8"))["services"]}
        cls.slides = {s["key"]: s for s in cls.index["slides"]}

    def test_every_slide_of_the_four_folders_is_indexed_once(self):
        self.assertEqual(len(self.index["slides"]), 57)
        self.assertEqual(len(self.slides), 57, "duplicate keys")
        on_disk = set()
        for g, meta in self.index["groups"].items():
            folder = ROOT / self.index["source_root"] / meta["dir"]
            pngs = sorted(folder.glob("*.png"))
            self.assertEqual(len(pngs), meta["slide_count"], g)
            on_disk |= {f"{g}/{p.stem}" for p in pngs}
        self.assertEqual(on_disk, set(self.slides))

    def test_slide_fields(self):
        for key, s in self.slides.items():
            with self.subTest(key=key):
                self.assertIn(s["group"], GROUPS)
                self.assertEqual(key, f"{s['group']}/{s['n']}")
                self.assertTrue((ROOT / s["file"]).is_file(), s["file"])
                self.assertTrue(s["file"].endswith(f"/{self.index['groups'][s['group']]['dir']}/{s['n']}.png"))
                self.assertIn(s["kind"], KINDS)
                self.assertIsInstance(s["title"], str)
                self.assertTrue(s["title"].strip())
                self.assertIsInstance(s["has_medical_claim"], bool)
                if s["has_medical_claim"]:
                    self.assertTrue(isinstance(s["claim_note"], str) and s["claim_note"].strip(), "claim needs a note")
                else:
                    self.assertIsNone(s["claim_note"])
                self.assertIsInstance(s["unmatched_names"], list)
                for sid in s["service_ids"]:
                    self.assertIn(sid, self.catalog_ids)

    def test_group_definitions_point_at_slides_of_the_group(self):
        for g, meta in self.index["groups"].items():
            with self.subTest(group=g):
                self.assertTrue(meta["label"].strip())
                self.assertTrue(meta["cover"])
                self.assertTrue(meta["price_list"])
                for n in meta["cover"]:
                    self.assertEqual(self.slides[f"{g}/{n}"]["kind"], "cover")
                for n in meta["price_list"]:
                    self.assertIn(self.slides[f"{g}/{n}"]["kind"], ("price_list", "service"))
                for sid, ns in meta["services"].items():
                    self.assertIn(sid, self.catalog_ids)
                    for n in ns:
                        self.assertIn(sid, self.slides[f"{g}/{n}"]["service_ids"], f"{g}/{n}")
                    self.assertTrue(any(self.slides[f"{g}/{n}"]["kind"] == "service" for n in ns), sid)
                for u in meta["unmatched_services"]:
                    for n in u["slides"]:
                        self.assertIn(u["name"], self.slides[f"{g}/{n}"]["unmatched_names"])
        self.assertEqual(set(self.index["overview_groups"]), GROUPS)

    def test_service_ids_on_slides_are_listed_in_their_group(self):
        for key, s in self.slides.items():
            for sid in s["service_ids"]:
                self.assertIn(s["n"], self.index["groups"][s["group"]]["services"][sid], key)

    def test_known_claim_slides_are_flagged(self):
        # Spot checks from research/menu-audit: "gấp 10 lần", "điều trị", disease and prevention names.
        for key in ("facial/9", "facial/18", "facial/20", "healing/11", "healing/14", "healing/17", "healing/19",
                    "thu-gian-toc/3", "thu-gian-toc/9"):
            self.assertTrue(self.slides[key]["has_medical_claim"], key)
        for key in ("facial/1", "healing/1", "thu-gian-toc/1", "hair-removal/1", "thu-gian-toc/5", "hair-removal/2"):
            self.assertFalse(self.slides[key]["has_medical_claim"], key)

    def test_internal_form_is_never_offered(self):
        form = self.slides["hair-removal/3"]
        self.assertEqual(form["kind"], "other")
        meta = self.index["groups"]["hair-removal"]
        used = set(meta["cover"]) | set(meta["price_list"]) | {n for ns in meta["services"].values() for n in ns}
        self.assertNotIn(3, used)


class BuildMenuImagesTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_script()
        self.tmp = Path(tempfile.mkdtemp(prefix="menu-images-test-"))
        self.root = self.tmp / "root"
        (self.root / "data").mkdir(parents=True)
        src_dir = self.root / "sources" / "m" / "g"
        src_dir.mkdir(parents=True)
        for n in (1, 2):
            (src_dir / f"{n}.png").write_bytes(f"png-{n}".encode() * 100)
        self.index = {"slides": [
            {"key": "facial/1", "group": "facial", "n": 1, "file": "sources/m/g/1.png", "kind": "cover", "has_medical_claim": False},
            {"key": "facial/2", "group": "facial", "n": 2, "file": "sources/m/g/2.png", "kind": "process", "has_medical_claim": True},
        ]}
        (self.root / "data" / "menu-images.json").write_text(json.dumps(self.index))
        self.calls = self.tmp / "sips-calls.log"
        self.sips = self.tmp / "sips"
        # Fake sips: "-g" prints a size; a conversion copies the source to --out and logs the call.
        self.sips.write_text(
            "#!/usr/bin/env python3\n"
            "import shutil, sys\n"
            "a = sys.argv[1:]\n"
            "if '-g' in a:\n"
            "    print(a[-1]); print('  pixelWidth: 1200'); print('  pixelHeight: 1600'); sys.exit(0)\n"
            f"open({str(self.calls)!r}, 'a').write(' '.join(a[:8]) + '\\n')\n"
            "shutil.copy(a[a.index('--out') - 1], a[a.index('--out') + 1])\n")
        self.sips.chmod(self.sips.stat().st_mode | stat.S_IEXEC)
        self.home = self.tmp / "home"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_build(self, **kw) -> tuple[int, list[str]]:
        lines: list[str] = []
        code = self.mod.build(self.home, sips=str(self.sips), root=self.root, log=lines.append, **kw)
        return code, lines

    def conversions(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_builds_jpegs_and_manifest_with_sha256(self):
        code, _ = self.run_build()
        self.assertEqual(code, 0)
        out = self.home / "menu-images"
        m = json.loads((out / "manifest.json").read_text())
        self.assertEqual(sorted(m["images"]), ["facial/1", "facial/2"])
        e = m["images"]["facial/2"]
        self.assertEqual(e["path"], "facial/2.jpg")
        self.assertEqual(e["sha256"], self.mod.sha256_file(out / "facial" / "2.jpg"))
        self.assertEqual((e["width"], e["height"]), (1200, 1600))
        self.assertTrue(e["has_medical_claim"])
        self.assertIn("-s format jpeg -s formatOptions 85 -Z 1600", self.conversions()[0])

    def test_second_run_is_a_no_op_and_check_passes(self):
        self.run_build()
        self.assertEqual(len(self.conversions()), 2)
        code, _ = self.run_build()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.conversions()), 2)
        self.assertEqual(self.run_build(check=True)[0], 0)

    def test_changed_source_or_damaged_copy_is_rebuilt_only(self):
        self.run_build()
        src = self.root / "sources" / "m" / "g" / "1.png"
        src.write_bytes(b"changed" * 50)
        self.assertEqual(self.run_build(check=True)[0], 1)
        self.run_build()
        self.assertEqual(len(self.conversions()), 3)
        (self.home / "menu-images" / "facial" / "2.jpg").write_bytes(b"tampered")
        self.run_build()
        self.assertEqual(len(self.conversions()), 4)

    def test_slides_removed_from_the_index_are_deleted(self):
        self.run_build()
        self.index["slides"] = self.index["slides"][:1]
        (self.root / "data" / "menu-images.json").write_text(json.dumps(self.index))
        self.assertEqual(self.run_build(check=True)[0], 1)
        self.run_build()
        self.assertFalse((self.home / "menu-images" / "facial" / "2.jpg").exists())
        m = json.loads((self.home / "menu-images" / "manifest.json").read_text())
        self.assertEqual(list(m["images"]), ["facial/1"])

    def test_missing_sips_or_source_is_exit_2(self):
        lines: list[str] = []
        self.assertEqual(self.mod.build(self.home, sips=str(self.tmp / "nope"), root=self.root, log=lines.append), 2)
        (self.root / "sources" / "m" / "g" / "2.png").unlink()
        code, lines = self.run_build()
        self.assertEqual(code, 2)
        self.assertTrue(any("facial/2" in x for x in lines))

    def test_cli_quiet_prints_nothing_when_up_to_date(self):
        self.run_build()
        buf = io.StringIO()
        old = self.mod.ROOT
        try:
            self.mod.ROOT = self.root
            with contextlib.redirect_stdout(buf):
                code = self.mod.main(["--home", str(self.home), "--quiet", "--sips", str(self.sips)])
        finally:
            self.mod.ROOT = old
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue(), "")


class Migration0009Tests(unittest.TestCase):
    """apps/server/migrations/0009_outbox_images.sql rebuilds outbox: every row and column must survive."""

    def test_rebuild_keeps_rows_and_columns_and_accepts_image_rows(self):
        import sqlite3
        db = sqlite3.connect(":memory:")
        migrations = sorted((ROOT / "apps" / "server" / "migrations").glob("*.sql"))
        target = ROOT / "apps" / "server" / "migrations" / "0009_outbox_images.sql"
        for m in migrations:
            if m == target:
                break
            db.executescript(m.read_text(encoding="utf-8"))
        before = {r[1] for r in db.execute("PRAGMA table_info(outbox)")}
        db.execute("INSERT INTO outbox (id, kind, zalo_mode, zalo_user_id, payload_json, status, created_at, channel, thread_id, text, "
                   "attempts, echo_msg_id, requeued_at, part_msg_ids, dedupe_key) VALUES "
                   "('obx_a','cs_text','personal','p:1','{}','sent',1,'personal','1','x',1,'e1',5,'[\"m\"]','msg:1')")
        db.execute("INSERT INTO outbox (id, kind, zalo_mode, zalo_user_id, payload_json, status, created_at) "
                   "VALUES ('obx_b','zbs_template','mock','u','{}','pending',2)")
        db.executescript(target.read_text(encoding="utf-8"))
        after = {r[1] for r in db.execute("PRAGMA table_info(outbox)")}
        self.assertEqual(after - before, {"image_keys", "depends_on", "echo_count"})
        self.assertEqual(before - after, set())
        rows = db.execute("SELECT id, kind, status, thread_id, attempts, echo_msg_id, requeued_at, part_msg_ids, dedupe_key, echo_count "
                          "FROM outbox ORDER BY id").fetchall()
        self.assertEqual(rows, [("obx_a", "cs_text", "sent", "1", 1, "e1", 5, '["m"]', "msg:1", 1),
                                ("obx_b", "zbs_template", "pending", None, 0, None, None, None, None, 0)])
        db.execute("INSERT INTO outbox (id, kind, zalo_mode, zalo_user_id, payload_json, status, created_at, image_keys) "
                   "VALUES ('obx_c','cs_images','personal','p:1','{}','queued',3,'[\"facial/1\"]')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO outbox (id, kind, zalo_mode, zalo_user_id, payload_json, status, created_at) "
                       "VALUES ('obx_d','cs_video','personal','p:1','{}','queued',4)")
        with self.assertRaises(sqlite3.IntegrityError):   # the dedupe index is back
            db.execute("INSERT INTO outbox (id, kind, zalo_mode, zalo_user_id, payload_json, status, created_at, dedupe_key) "
                       "VALUES ('obx_e','cs_text','personal','p:1','{}','queued',5,'msg:1')")
        self.assertIn("attachments_json", {r[1] for r in db.execute("PRAGMA table_info(drafts)")})


if __name__ == "__main__":
    unittest.main()
