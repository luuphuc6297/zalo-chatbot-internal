"""Menu images: `zalo-agent msg send-image` for cs_images outbox rows, with the fake engine and a temp manifest.

Keys resolve only through <menu_images_dir>/manifest.json (sha256 checked, no path outside the folder). The result
carries every image's msgId (part_msg_ids). Errors are classified like text sends, with one difference: a Zalo error
answer for more than one image is "unknown" (earlier images of the same call may have been delivered)."""

from __future__ import annotations

import hashlib
import json
import os

from bridge.config import Config
from bridge.engine import EngineResult
from bridge.journal import Journal
from bridge.menu_images import MenuImageError, resolve
from bridge.poller import Bridge
from bridge.sender import Sender, classify_images
from tests.helpers import THREAD, BridgeTestCase

KEYS = ["thu-gian-toc/2", "thu-gian-toc/5", "thu-gian-toc/8"]


class ImagesTestCase(BridgeTestCase):
    def setUp(self):
        super().setUp()
        self.menu = self.tmp / "menu-images"
        self.manifest: dict = {"version": 1, "images": {}}
        for k in KEYS + ["facial/1"]:
            self.add_image(k)
        self.write_manifest()

    def add_image(self, key: str, data: bytes | None = None) -> None:
        group, n = key.split("/")
        path = self.menu / group / f"{n}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data or f"jpeg-{key}".encode() * 50)
        self.manifest["images"][key] = {"path": f"{group}/{n}.jpg", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                        "bytes": path.stat().st_size}

    def write_manifest(self) -> None:
        self.menu.mkdir(parents=True, exist_ok=True)
        (self.menu / "manifest.json").write_text(json.dumps(self.manifest))

    def icfg(self, **kw) -> Config:
        return self.cfg(menu_images_dir=self.menu, **kw)

    def image_calls(self) -> list[dict]:
        return [c for c in self.calls() if "send-image" in c["argv"]]


class SendImagesTests(ImagesTestCase):
    def test_sends_all_images_in_one_call_with_safe_argv_and_reports_every_msg_id(self):
        os.environ["RUNNER_TOKEN"] = "must-not-reach-engine"
        os.environ["ZALO_PERSONAL_WEBHOOK_SECRET"] = "must-not-reach-engine"
        out = Sender(self.icfg()).send_images(THREAD, KEYS)
        self.assertEqual(out.status, "sent")
        sent = self.sent()[0]
        self.assertEqual(sent["images"], [f"{k.split('/')[0]}/{k.split('/')[1]}.jpg" for k in KEYS])
        self.assertEqual(out.zalo_msg_id, sent["msgIds"][0])
        self.assertEqual(out.part_msg_ids, sent["msgIds"])
        self.assertEqual(out.result_body(), {"status": "sent", "zalo_msg_id": sent["msgIds"][0], "part_msg_ids": sent["msgIds"]})
        call = self.image_calls()[0]
        timeout = self.icfg().image_timeout_s(3)
        self.assertEqual(call["argv"][:8], ["--json", "msg", "send-image", "-t", "0", "--upload-timeout",
                                            str(int((timeout - 5) * 1000)), "--"])
        self.assertEqual(call["argv"][8], THREAD)
        self.assertEqual(call["argv"][9:], [str((self.menu / k.split("/")[0] / f"{k.split('/')[1]}.jpg").resolve()) for k in KEYS])
        self.assertTrue(call["stdin_devnull"])
        self.assertTrue(call["own_process_group"])
        self.assertFalse(call["env"]["runner_token"])
        self.assertFalse(call["env"]["personal_secret"])

    def test_timeout_grows_with_the_image_count_and_is_capped(self):
        cfg = self.icfg(send_timeout_s=30.0)
        self.assertEqual(cfg.image_timeout_s(1), 45.0)
        self.assertEqual(cfg.image_timeout_s(10), 180.0)
        self.assertEqual(self.icfg(send_timeout_s=30.0, image_timeout_max_s=60.0).image_timeout_s(10), 60.0)
        # a hanging upload is killed and reported unknown
        self.write_fake(send_image="timeout", sleep_s=10)
        out = Sender(self.icfg(send_timeout_s=1.0, image_timeout_per_image_s=0.5)).send_images(THREAD, KEYS[:1])
        self.assertEqual(out.status, "unknown")
        self.assertTrue(out.error.startswith("timeout"))

    def test_account_is_pinned_when_configured(self):
        Sender(self.icfg(zalo_account="1000000000000001")).send_images(THREAD, KEYS[:1])
        self.assertEqual(self.image_calls()[0]["argv"][:3], ["--json", "--account", "1000000000000001"])

    def test_keys_that_do_not_resolve_are_refused_before_the_engine_runs(self):
        s = Sender(self.icfg())
        cases = {
            "unknown key": (["facial/9"], "not in manifest"),
            "bad key": (["../../etc/passwd"], "bad image key"),
            "empty": ([], "images is empty"),
            "not a list": ("facial/1", "images is empty"),
            "too many": ([f"facial/{i}" for i in range(1, 12)], "more than 10"),
            "duplicate": (["facial/1", "facial/1"], "duplicate"),
        }
        for name, (keys, want) in cases.items():
            with self.subTest(name):
                out = s.send_images(THREAD, keys)
                self.assertEqual(out.status, "failed")
                self.assertIn(want, out.error)
        # damaged file, file outside the folder, missing file, missing manifest
        (self.menu / "facial" / "1.jpg").write_bytes(b"tampered")
        self.assertIn("sha256 mismatch", s.send_images(THREAD, ["facial/1"]).error)
        self.manifest["images"]["thu-gian-toc/2"]["path"] = "../outside.jpg"
        (self.tmp / "outside.jpg").write_bytes(b"x")
        self.write_manifest()
        self.assertIn("outside the menu folder", s.send_images(THREAD, ["thu-gian-toc/2"]).error)
        (self.menu / "thu-gian-toc" / "5.jpg").unlink()
        self.assertIn("file missing", s.send_images(THREAD, ["thu-gian-toc/5"]).error)
        (self.menu / "manifest.json").unlink()
        self.assertIn("manifest_missing", s.send_images(THREAD, ["thu-gian-toc/8"]).error)
        self.assertEqual(self.image_calls(), [])
        self.assertEqual(s.send_images("not-a-thread", KEYS).status, "failed")

    def test_resolve_never_follows_a_symlink_out_of_the_folder(self):
        target = self.tmp / "secret.jpg"
        target.write_bytes(b"secret")
        link = self.menu / "facial" / "2.jpg"
        link.symlink_to(target)
        self.manifest["images"]["facial/2"] = {"path": "facial/2.jpg", "sha256": hashlib.sha256(b"secret").hexdigest()}
        self.write_manifest()
        with self.assertRaises(MenuImageError):
            resolve(self.menu, ["facial/2"])

    def test_engine_errors_are_classified(self):
        s = Sender(self.icfg())
        expect = {
            "not_logged_in": ("failed", "not_logged_in", True),
            "too_many": ("failed", "image_refused", False),
            "transport": ("unknown", "transport_error", False),
            "no_ids": ("unknown", "no_msg_id", False),
            "garbled": ("unknown", "garbled_output", False),
        }
        for mode, (status, kind, login) in expect.items():
            with self.subTest(mode):
                self.write_fake(send_image=mode)
                out = s.send_images(THREAD, KEYS)
                self.assertEqual((out.status, out.error.split(":")[0], out.login_required), (status, kind, login))
        # a Zalo error answer: nothing delivered for one image; maybe some images delivered for several
        self.write_fake(send_image="zalo_error")
        self.assertEqual(s.send_images(THREAD, KEYS[:1]).status, "failed")
        multi = s.send_images(THREAD, KEYS)
        self.assertEqual((multi.status, multi.error.split(":")[0]), ("unknown", "partial_possible"))

    def test_classify_reads_attachment_ids_when_sent_is_absent(self):
        res = EngineResult(argv_tail=[], returncode=0, data={"message": None, "attachment": [{"msgId": 11}, {"msgId": 12}]})
        out = classify_images(res, 2)
        self.assertEqual((out.status, out.zalo_msg_id, out.part_msg_ids), ("sent", "11", ["11", "12"]))
        self.assertEqual(classify_images(EngineResult(argv_tail=[], missing=True, stderr="nope"), 1).status, "failed")
        self.assertEqual(classify_images(EngineResult(argv_tail=[], cancelled=True), 1).status, "unknown")


class PollerImagesTests(ImagesTestCase):
    def test_claims_with_the_images_capability_and_sends_text_then_images(self):
        srv = self.start_server()
        t = srv.enqueue("Dạ em gửi anh/chị menu tóc ạ.")
        i = srv.enqueue_images(KEYS)
        b = Bridge(self.icfg())
        self.assertEqual(b.run_once()["id"], t)
        r = b.run_once()
        self.assertEqual((r["id"], r["status"], r["sent_now"]), (i, "sent", True))
        claims = [q for q in srv.requests if q["path"] == "/bridge/outbox/claim"]
        self.assertTrue(all(q["body"] == {"capabilities": ["images"]} for q in claims))
        self.assertEqual([c["argv"][1:3] for c in self.calls() if "msg" in c["argv"]], [["msg", "send"], ["msg", "send-image"]])
        body = srv.results(i)[0]["body"]
        ids = self.sent()[1]["msgIds"]
        self.assertEqual(body, {"status": "sent", "zalo_msg_id": ids[0], "part_msg_ids": ids, "attempt": 1})
        self.assertEqual(srv.row(i)["part_msg_ids"], ids)
        # the label text of the image row never went out as a message
        self.assertEqual([x.get("text") for x in self.sent() if "text" in x], ["Dạ em gửi anh/chị menu tóc ạ."])

    def test_image_row_is_sent_at_most_once(self):
        srv = self.start_server()
        i = srv.enqueue_images(KEYS[:2])
        b = Bridge(self.icfg())
        b.run_once()
        srv.requeue(i)                         # the same row comes back (e.g. a lost lease): replay, do not resend
        r = b.run_once()
        self.assertEqual((r["status"], r["replayed"]), ("sent", True))
        self.assertEqual(len(self.image_calls()), 1)
        self.assertEqual(srv.results(i)[-1]["body"]["part_msg_ids"], self.sent()[0]["msgIds"])
        # a crash mid-send leaves "sending": reported unknown, never sent again
        j = srv.enqueue_images(KEYS[:1])
        Journal(self.icfg().state_dir).record(j, status="sending", attempt=1, reported=False)
        b2 = Bridge(self.icfg())
        b2.flush_unreported()
        self.assertEqual(srv.results(j)[-1]["body"]["status"], "unknown")
        self.assertEqual(len(self.image_calls()), 1)

    def test_unresolvable_keys_are_reported_failed_without_sending(self):
        srv = self.start_server()
        i = srv.enqueue_images(["healing/17"])
        r = Bridge(self.icfg()).run_once()
        self.assertEqual(r["status"], "failed")
        self.assertIn("not in manifest", srv.results(i)[0]["body"]["error"])
        self.assertEqual(self.image_calls(), [])
