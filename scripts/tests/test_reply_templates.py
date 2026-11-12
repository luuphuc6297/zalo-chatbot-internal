"""Reply templates (data/reply-templates.json) and the bundled menu thumbnails (scripts/build_menu_thumbs.py).

The template tests read the real repository files: every placeholder is declared and used, the no-profile versions say
"anh/chị", and every example reply follows the bot voice (xưng "em", never "mình"/"bạn"/"quý khách", no "ngay",
at most two questions, the profile's address term and name in the first sentence, no forbidden health words).
The thumbnail tests use a fake `sips` and temp files; one test checks the generated module against the slide index.
"""

from __future__ import annotations

import importlib.util
import json
import re
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = json.loads((ROOT / "data" / "reply-templates.json").read_text(encoding="utf-8"))
SERVICES = json.loads((ROOT / "data" / "services.json").read_text(encoding="utf-8"))["services"]
MENU = json.loads((ROOT / "data" / "menu-images.json").read_text(encoding="utf-8"))
TOOLS = {t["name"] for t in json.loads((ROOT / "design" / "tools-schema.json").read_text(encoding="utf-8"))["tools"]}

INTENTS = ["chao_khach_moi", "chao_khach_quen", "xem_menu_tong", "xem_menu_nhom", "hoi_dich_vu", "dat_lich",
           "cam_on_sau_khi_lam"]
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
# H4 of block A (design/system-prompt-draft.md); "trị" alone is matched as a word.
FORBIDDEN = ["điều trị", "trị bệnh", "trị liệu", "chữa", "đặc trị", "bài thuốc", "châm cứu", "kê toa", "đảm bảo",
             "cam kết hiệu quả", "100%", "khỏi hẳn", "dứt điểm", "thải độc", "độc tố", "tốt nhất", "duy nhất", "số một"]


def words(text: str) -> list[str]:
    return re.split(r"[^\w/]+", text.lower())


def examples():
    for it in TEMPLATES["intents"]:
        for n, ex in enumerate(it["examples"], 1):
            yield it["id"], n, ex


class TemplateFileTest(unittest.TestCase):
    def test_seven_intents_with_two_examples_each(self):
        self.assertEqual([i["id"] for i in TEMPLATES["intents"]], INTENTS)
        self.assertEqual(TEMPLATES["status"], "draft_unapproved")
        for it in TEMPLATES["intents"]:
            self.assertEqual(len(it["examples"]), 2, it["id"])
            for key in ("label", "when", "template", "placeholders", "fallback_no_profile", "rules"):
                self.assertTrue(it[key], f"{it['id']}.{key}")

    def test_placeholders_are_declared_and_used(self):
        declared = set(TEMPLATES["placeholders"])
        for it in TEMPLATES["intents"]:
            in_template = set(PLACEHOLDER_RE.findall(it["template"]))
            in_fallback = set(PLACEHOLDER_RE.findall(it["fallback_no_profile"]))
            self.assertEqual(set(it["placeholders"]), in_template, it["id"])
            self.assertLessEqual(in_fallback, in_template, it["id"])
            self.assertLessEqual(in_template, declared, it["id"])
            # without a profile the customer is "anh/chị", never a placeholder
            self.assertFalse(in_fallback & {"xung_ho", "ten"}, it["id"])
            self.assertIn("anh/chị", it["fallback_no_profile"], it["id"])

    def test_returning_customer_template_mentions_the_last_service(self):
        quen = next(i for i in TEMPLATES["intents"] if i["id"] == "chao_khach_quen")
        self.assertIn("Lần trước {xung_ho} làm {dich_vu} bên em hôm {ngay}", quen["template"])
        self.assertNotIn("Lần trước", quen["fallback_no_profile"])
        self.assertTrue(any("180 ngày" in r for r in quen["rules"]))

    def test_menu_groups_match_the_catalog_and_the_menu_images(self):
        groups = [g["catalog_group"] for g in TEMPLATES["menu_groups"]]
        self.assertEqual(set(groups), {s["group"] for s in SERVICES})
        self.assertEqual(len(groups), len(set(groups)))
        for g in TEMPLATES["menu_groups"]:
            if g["image_group"] is not None:
                self.assertIn(g["image_group"], MENU["groups"])
                self.assertEqual(MENU["groups"][g["image_group"]]["catalog_group"], g["catalog_group"])

    def test_tools_and_example_inputs_are_real(self):
        ids = {s["id"] for s in SERVICES}
        for it in TEMPLATES["intents"]:
            for t in it["tools"]:
                self.assertIn(t["name"], TOOLS, it["id"])
        for intent, n, ex in examples():
            for t in ex["tool_calls"]:
                self.assertIn(t["name"], TOOLS, f"{intent} {n}")
                sid = t["input"].get("service_id")
                if sid not in (None, "none"):
                    self.assertIn(sid, ids, f"{intent} {n}")
                g = t["input"].get("group")
                if t["name"] == "attach_menu_images" and g != "none":
                    self.assertIn(g, ["overview", *MENU["groups"]], f"{intent} {n}")

    def test_cam_on_template_reuses_the_followup_wording_without_ngay(self):
        it = next(i for i in TEMPLATES["intents"] if i["id"] == "cam_on_sau_khi_lam")
        followup = (ROOT / "design" / "followup-templates.md").read_text(encoding="utf-8")
        self.assertIn("đi khám nếu thấy nặng", followup)
        self.assertIn("đi khám nếu thấy nặng", it["template"])
        self.assertIn("design/followup-templates.md", it["source"])


class ExampleVoiceTest(unittest.TestCase):
    def test_every_example_follows_the_voice_rules(self):
        for intent, n, ex in examples():
            with self.subTest(intent=intent, example=n):
                r = ex["reply"]
                self.assertTrue(r.startswith("Dạ "))
                w = words(r)
                for bad in ("mình", "bạn", "ngay", "liền", "sớm", "trị"):
                    self.assertNotIn(bad, w)
                self.assertNotIn("quý khách", r.lower())
                self.assertLessEqual(r.count("?"), 2)
                self.assertLessEqual(len(r), 600)
                self.assertEqual(set(PLACEHOLDER_RE.findall(r)) - {"price_text"}, set())
                for term in FORBIDDEN:
                    self.assertNotIn(term, r.lower())
                self.assertNotRegex(r, r"\d+\s?k\b|\*\*|^#|\|")
                profile = ex["profile"]
                call = (f"{profile['address']} {profile['name']}" if profile and profile.get("name")
                        else profile["address"] if profile else "anh/chị")
                first = re.split(r"[.?!]\s", r)[0]
                self.assertIn(call, first)

    def test_last_service_is_mentioned_only_with_a_last_service_profile(self):
        for intent, n, ex in examples():
            if "Lần trước" in ex["reply"]:
                self.assertTrue(ex["profile"] and ex["profile"].get("last_service"), f"{intent} {n}")
                name, day = re.match(r"(.+) \((\d{2}/\d{2})\)$", ex["profile"]["last_service"]).groups()
                self.assertIn(f"làm {name} bên em hôm {day}", ex["reply"])


def _load_thumbs():
    spec = importlib.util.spec_from_file_location("build_menu_thumbs", ROOT / "scripts" / "build_menu_thumbs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MenuThumbsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_thumbs()

    def test_sendable_keys_skip_the_internal_form(self):
        keys = self.mod.sendable_keys(MENU)
        self.assertNotIn("hair-removal/3", keys)
        self.assertEqual(len(keys), len(MENU["slides"]) - 1)

    def test_generated_module_has_exactly_the_sendable_keys(self):
        text = (ROOT / "apps" / "server" / "src" / "menu-thumbs.ts").read_text(encoding="utf-8")
        found = re.findall(r'^  "([a-z-]+/\d+)": "', text, re.M)
        self.assertEqual(sorted(found), sorted(self.mod.sendable_keys(MENU)))
        self.assertIn("export const MENU_THUMBS: Record<string, string>", text)

    def test_build_with_a_fake_sips_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "data").mkdir()
            (tmp / "src").mkdir()
            png = tmp / "src" / "a.png"
            png.write_bytes(b"\x89PNG fake")
            index = {"groups": {"facial": {"cover": [1], "price_list": [], "services": {}, "unmatched_services": []}},
                     "slides": [{"key": "facial/1", "file": "src/a.png"}, {"key": "facial/2", "file": "src/a.png"}]}
            (tmp / "data" / "menu-images.json").write_text(json.dumps(index), encoding="utf-8")
            sips = tmp / "sips"
            # Fake sips: writes a tiny JPEG to the path after --out.
            sips.write_text("#!/usr/bin/env python3\nimport sys\nout = sys.argv[sys.argv.index('--out') + 1]\n"
                            "open(out, 'wb').write(b'\\xff\\xd8fakejpeg')\n", encoding="utf-8")
            sips.chmod(sips.stat().st_mode | stat.S_IEXEC)
            out = tmp / "thumbs.ts"
            idx = tmp / "data" / "menu-images.json"
            self.assertEqual(self.mod.build(idx, out, check=True, sips=str(sips)), 1)
            self.assertEqual(self.mod.build(idx, out, sips=str(sips)), 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn('"facial/1": "/9hmYWtlanBlZw=="', text)
            self.assertNotIn("facial/2", text)  # not a cover, price list or service slide
            self.assertEqual(self.mod.build(idx, out, check=True, sips=str(sips)), 0)
            self.assertEqual(self.mod.build(idx, out, sips=str(tmp / "nope")), 2)


if __name__ == "__main__":
    unittest.main()
