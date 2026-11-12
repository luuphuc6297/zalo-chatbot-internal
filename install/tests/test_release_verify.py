"""release.py on a device (16.2.6, 16.2.7, 16.8.1 U1): the header is read as data and never executed, payload hash
and signature, trust on first use versus the stored trust, the denylist of the installed release, unpack, the cached
copy, the app link, prune and the menu slides (rev F5, F10)."""

from __future__ import annotations

import json
import os
import re
import tarfile
from pathlib import Path

from tests.fakes_release import kit
from tests.fakes_release.kit import ReleaseTestCase
from thomhouse_installer import release, state
from thomhouse_installer.context import InstallerError
from thomhouse_installer.release import ReleaseError


class VerifyTest(ReleaseTestCase):
    def assert_refused(self, kind: str, fn, *args, **kwargs) -> None:
        with self.assertRaises(ReleaseError) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.kind, kind)
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(cm.exception.key, f"release.{kind}")

    def test_read_header(self) -> None:
        command = self.release_file()
        info = release.read_header(command)
        data = command.read_bytes()
        self.assertEqual(info.version, "1.4.0")
        self.assertEqual(data[info.payload_offset - 12:info.payload_offset], b"\n__PAYLOAD__\n"[1:])
        self.assertEqual(len(data) - info.payload_offset, info.payload_bytes)
        self.assertEqual(info.release_id, release.group_id(kit.sha256_bytes(data)[:16]))
        self.assertRegex(info.release_id, r"^[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$")
        self.assertTrue(info.signature.startswith(b"-----BEGIN SSH SIGNATURE-----"))
        self.assertEqual(data[:info.payload_offset].count(b"__PAYLOAD__"), 1)

    def test_not_a_release(self) -> None:
        f = self.tmp / "x.command"
        f.write_text("#!/bin/bash\necho hello\n")
        self.assert_refused("not_release", release.read_header, f)
        f.write_bytes(b'#!/bin/bash\nRELEASE_VERSION="1.4.0"\n__PAYLOAD__\nxx')
        self.assert_refused("not_release", release.read_header, f)
        self.assert_refused("not_release", release.read_header, self.tmp / "missing.command")

    def test_header_never_executed(self) -> None:
        command = self.release_file()
        marker = self.tmp / "header-ran"
        lines = command.read_bytes().split(b"\n", 1)
        command.write_bytes(lines[0] + b"\n" + f'touch "{marker}"\n'.encode() + lines[1])
        ctx = self.ctx()
        info = release.verify_file(ctx, command, first_install=True)
        self.assertEqual(info.version, "1.4.0")
        self.install_built()
        info = release.verify_file(self.ctx(), command, first_install=False)
        self.assertEqual(info.version, "1.4.0")
        self.assertFalse(marker.exists())

    def test_changed_payload_is_refused(self) -> None:
        command = self.release_file()
        data = bytearray(command.read_bytes())
        data[-50] ^= 0x01
        command.write_bytes(bytes(data))
        self.assert_refused("damaged", release.verify_file, self.ctx(), command, first_install=True)
        # A forged payload with a header that carries its new hash still fails on the signature.
        info = release.read_header(command)
        new_sha = kit.sha256_bytes(bytes(data[info.payload_offset:])).encode()
        fixed = re.sub(rb'PAYLOAD_SHA256="[0-9a-f]{64}"', b'PAYLOAD_SHA256="' + new_sha + b'"', bytes(data), count=1)
        command.write_bytes(fixed)
        with self.assertRaises(ReleaseError) as cm:
            release.verify_file(self.ctx(), command, first_install=True)
        self.assertIn(cm.exception.kind, ("damaged", "signature"))

    def test_update_signed_with_another_key_is_refused(self) -> None:
        self.install_built("1.4.0")
        other = self.release_file("1.5.0", key="other")
        self.assert_refused("signature", release.verify_file, self.ctx(), other, first_install=False)
        # On a device with no trust yet, the file's own key is trusted (trust on first use, 16.2.6).
        self.assertEqual(release.verify_file(self.ctx(), other, first_install=True).version, "1.5.0")

    def test_missing_trust_is_a_signature_failure(self) -> None:
        self.assert_refused("signature", release.verify_file, self.ctx(), self.release_file(), first_install=False)

    def test_older_and_same(self) -> None:
        self.assert_refused("older", release.compare_versions, "1.4.0", "1.3.9")
        self.assert_refused("same", release.compare_versions, "1.4.0", "1.4.0")
        release.compare_versions("1.4.0", "1.10.0")
        from thomhouse_installer.text_vi import t

        self.assertIn("~/ThomHouse/bin/thomhouse rollback", t("release.older", tb="~/ThomHouse/bin/thomhouse"))

    def test_denylisted_manifest_path_is_refused(self) -> None:
        folder = self.install_built("1.4.0")
        with open(folder / "install" / "denylist.txt", "a", encoding="utf-8") as f:
            f.write("scripts/stop_local.sh\n")
        update = self.release_file("1.5.0")
        self.assert_refused("denylisted", release.verify_file, self.ctx(), update, first_install=False)

    def test_payload_menu_id_wins_over_the_header(self) -> None:
        command = self.release_file()
        data = command.read_bytes()
        fixed = re.sub(rb'MENU_ID="[0-9a-f]{16}"', b'MENU_ID="0123456789abcdef"', data, count=1)
        command.write_bytes(fixed)
        info = release.verify_file(self.ctx(), command, first_install=True)
        self.assertEqual(info.menu_id, "e3b0c44298fc1c14")  # the sha of no slides, from the payload's VERSION.json


class UnpackTest(ReleaseTestCase):
    def test_unpack_cache_switch(self) -> None:
        command = self.release_file()
        ctx = self.ctx()
        info = release.verify_file(ctx, command, first_install=True)
        folder = release.unpack(ctx, info)
        self.assertEqual(folder, self.app_home / "releases" / "1.4.0")
        self.assertEqual(release.verify_manifest(folder), [])
        self.assertFalse((self.app_home / "releases" / ".staging-1.4.0").exists())
        self.assertEqual(self.app_home.stat().st_mode & 0o777, 0o700)
        self.assertTrue(os.access(folder / "scripts" / "start_local.sh", os.X_OK))
        self.assertEqual((folder / "package.json").stat().st_mode & 0o777, 0o644)
        marker = folder / "node_modules"
        marker.mkdir()
        self.assertEqual(release.unpack(ctx, info), folder)
        self.assertTrue(marker.exists(), "a verified folder is returned as is")
        cached = release.copy_to_cache(ctx, info)
        self.assertEqual(cached, self.app_home / "cache" / "releases" / "thomhouse-1.4.0.command")
        self.assertEqual(cached.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cached.read_bytes(), command.read_bytes())
        release.switch_app(ctx, "1.4.0")
        self.assertEqual(os.readlink(self.app_home / "app"), "releases/1.4.0")
        with self.assertRaises(FileNotFoundError):
            release.switch_app(ctx, "9.9.9")

    def test_broken_release_folder_is_replaced_but_never_the_live_one(self) -> None:
        command = self.release_file()
        ctx = self.ctx()
        info = release.verify_file(ctx, command, first_install=True)
        folder = release.unpack(ctx, info)
        (folder / "package.json").write_text("changed", encoding="utf-8")
        folder = release.unpack(ctx, info)
        self.assertEqual(release.verify_manifest(folder), [])
        release.switch_app(ctx, "1.4.0")
        (folder / "package.json").write_text("changed", encoding="utf-8")
        with self.assertRaises(ReleaseError):
            release.unpack(self.ctx(), info)
        self.assertEqual((folder / "package.json").read_text(), "changed")

    def test_verify_manifest_reports_changes_and_skips_runtime_written(self) -> None:
        folder = self.install_built()
        self.assertEqual(release.verify_manifest(folder), [])
        (folder / "apps" / "server" / "src" / "seed-data.ts").write_text("regenerated", encoding="utf-8")
        (folder / "scripts" / "stop_local.sh").unlink()
        (folder / "package.json").write_text("{}", encoding="utf-8")
        self.assertEqual(release.verify_manifest(folder), ["package.json", "scripts/stop_local.sh"])
        (folder / "MANIFEST.json").unlink()
        self.assertEqual(release.verify_manifest(folder), ["MANIFEST.json"])

    def test_prune_keeps_live_and_previous(self) -> None:
        live = self.install_built("1.4.0")
        rel = self.app_home / "releases"
        for v in ("1.2.0", "1.3.0", ".staging-1.5.0"):
            (rel / v).mkdir()
            (rel / v / "VERSION.json").write_text(json.dumps({"version": v, "menu_id": "1" * 16}))
        cache = self.app_home / "cache" / "releases"
        for v in ("1.2.0", "1.3.0"):
            (cache / f"thomhouse-{v}.command").write_text("x")
        ctx = self.ctx()
        data = state.load_installed(ctx.paths)
        data["previous_version"] = "1.2.0"
        state.save_installed(ctx.paths, data)
        release.prune(ctx, keep_previous=1)
        self.assertEqual(sorted(p.name for p in rel.iterdir()), ["1.2.0", "1.4.0"])
        self.assertEqual(sorted(p.name for p in cache.iterdir()),
                         ["thomhouse-1.2.0.command", "thomhouse-1.4.0.command"])
        release.prune(ctx, keep_previous=0)
        self.assertEqual([p.name for p in rel.iterdir()], ["1.4.0"])
        self.assertEqual(release.verify_manifest(live), [])

    def test_prune_runtime_folders(self) -> None:
        self.install_built("1.4.0")
        rt = self.app_home / "runtime"
        for name in ("python-3.13.0-aarch64-apple-darwin", "python-3.14.6-aarch64-apple-darwin",
                     "python-3.15.0-aarch64-apple-darwin", "node-v22.0.0-darwin-arm64", "node-v24.19.0-darwin-arm64",
                     "pnpm-10.0.0", "pnpm-10.32.1", ".tmp-node-1"):
            (rt / name).mkdir(parents=True)
        (rt / "python").symlink_to("python-3.15.0-aarch64-apple-darwin")
        ctx = self.ctx()
        data = state.load_installed(ctx.paths)
        data["runtimes"] = {"python": "3.14.6", "node": "24.19.0", "pnpm": "10.32.1"}
        data["previous_runtimes"] = {"python": "3.13.0", "node": "24.19.0", "pnpm": "10.32.1"}
        state.save_installed(ctx.paths, data)
        release.prune(ctx)
        self.assertEqual(sorted(p.name for p in rt.iterdir()),
                         ["node-v24.19.0-darwin-arm64", "pnpm-10.32.1", "python", "python-3.13.0-aarch64-apple-darwin",
                          "python-3.14.6-aarch64-apple-darwin", "python-3.15.0-aarch64-apple-darwin"])


class GlobTest(ReleaseTestCase):
    def test_denylist_patterns(self) -> None:
        patterns = release.denylist(kit.INSTALL_DIR.parent)
        self.assertIn("!**/.env.example", patterns)
        deny = [".secrets/x", "apps/server/.dev.vars", "apps/runner/.env", ".env", "apps/console/.env.local",
                "results/r.json", "sources/repos/x", "node_modules/x", "apps/server/node_modules/a/b.js",
                "scripts/tests/wip_x.py", "design/eval-set.jsonl", "apps/server/.wrangler/state/x", "a/b.sqlite-wal",
                "x.db", "apps/runner/tests/t.py", "install/tests/x.py", "scripts/release/make_release.py",
                "data/services-corrections.json", "apps/console/dist/index.js", "scripts/wip_notes.md",
                "apps/x/wip_dir/inner.py"]
        allow = ["apps/runner/.env.example", "apps/console/.env.example", "apps/server/.dev.vars.example",
                 "install/denylist.txt", "scripts/start_local.sh", "data/services.json", "install/tests.md"]
        for p in deny:
            self.assertTrue(release.denylisted(p, patterns), p)
        for p in allow:
            self.assertFalse(release.denylisted(p, patterns), p)

    def test_glob(self) -> None:
        self.assertTrue(release.glob_match("apps/server/src/a/b.ts", "apps/server/src/**"))
        self.assertFalse(release.glob_match("apps/server/src", "apps/server/src/**"))
        self.assertTrue(release.glob_match("apps/server/migrations/0001.sql", "apps/server/migrations/*.sql"))
        self.assertFalse(release.glob_match("apps/server/migrations/x/0001.sql", "apps/server/migrations/*.sql"))
        self.assertTrue(release.glob_match(".env", "**/.env"))
        self.assertTrue(release.glob_match("a/b/.env", "**/.env"))


class MenuTest(ReleaseTestCase):
    def test_menu_install_link_and_check(self) -> None:
        command = self.release_file(menu=True)
        tars = list(command.parent.glob("thomhouse-menu-*.tar"))
        self.assertEqual(len(tars), 1)
        ctx = self.ctx()
        info = release.verify_file(ctx, command, first_install=True)
        folder = release.unpack(ctx, info)
        release.switch_app(ctx, info.version)
        ctx = self.ctx()
        self.assertFalse(release.menu_slides_ok(ctx, folder))
        self.assertFalse(release.link_menu(ctx, folder, info.menu_id), "nothing to link before the slides exist")
        menu_id = release.install_menu(ctx, tars[0])
        self.assertEqual(menu_id, info.menu_id)
        self.assertEqual(tars[0].name, f"thomhouse-menu-{menu_id}.tar")
        dest = self.app_home / "shared" / "menu-slides" / menu_id
        self.assertEqual(sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()),
                         ["MENU.json", "facial/1.png", "facial/2.png"])
        self.assertTrue(release.link_menu(ctx, self.app_home / "app", menu_id))
        link = folder / "sources" / "drive-resources" / "thomhouse-menu"
        self.assertTrue(link.is_symlink())
        self.assertFalse(os.readlink(link).startswith("/"))
        self.assertEqual((link / "facial" / "1.png").read_bytes(), b"\x89PNG slide one")
        self.assertTrue(release.menu_slides_ok(ctx, self.app_home / "app"))
        self.assertEqual(release.install_menu(ctx, tars[0]), menu_id)  # kept as it is
        (dest / "facial" / "2.png").write_bytes(b"changed")
        self.assertFalse(release.menu_slides_ok(ctx, folder))
        release.install_menu(ctx, tars[0])
        self.assertTrue(release.menu_slides_ok(ctx, folder))

    def test_damaged_menu_archive(self) -> None:
        command = self.release_file(menu=True)
        tar_path = next(command.parent.glob("thomhouse-menu-*.tar"))
        bad = self.tmp / "bad.tar"
        with tarfile.open(tar_path) as src, tarfile.open(bad, "w") as dst:
            for m in src.getmembers():
                data = src.extractfile(m).read()
                if m.name.endswith("2.png"):
                    data = b"other bytes!!!!"
                    m.size = len(data)
                import io

                dst.addfile(m, io.BytesIO(data))
        with self.assertRaises(InstallerError) as cm:
            release.install_menu(self.ctx(), bad)
        self.assertEqual(cm.exception.key, "release.menu_damaged")
        self.assertFalse((self.app_home / "shared" / "menu-slides").exists()
                         and any(p.name[:1] != "." for p in (self.app_home / "shared" / "menu-slides").iterdir()))

    def test_real_folder_is_never_replaced(self) -> None:
        checkout = self.make_checkout()
        real = checkout / "sources" / "drive-resources" / "thomhouse-menu"
        real.mkdir(parents=True)
        slides: Path = self.app_home / "shared" / "menu-slides" / ("a" * 16)
        slides.mkdir(parents=True)
        (slides / "MENU.json").write_text("{}", encoding="utf-8")
        self.assertFalse(release.link_menu(self.ctx(), checkout, "a" * 16))
        self.assertTrue(real.is_dir() and not real.is_symlink())
