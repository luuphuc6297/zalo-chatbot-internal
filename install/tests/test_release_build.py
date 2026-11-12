"""scripts/release/make_release.py (16.2.2 to 16.2.5): the allowlist and the denylist, the scans for secrets, ids,
phone numbers and the home path, the pins, determinism, the header, the release id, the note beside the file, the
menu archive and the test-only pins (rev F5, F19, F25, rev facts)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

from tests.fakes_release import kit
from tests.fakes_release.kit import ReleaseTestCase, build_env, make_project, run_make_release
from thomhouse_installer import release

TOKEN = "runner-" + "9f" * 24


class BuildTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(self.tmp / "project")
        self.out = self.tmp / "out"
        self.bhome = self.tmp / "buildhome"

    def build(self, *args: str, extra: dict | None = None, version: str = "1.4.0", env: dict | None = None):
        env = env if env is not None else build_env(self.bhome, extra=extra)
        return run_make_release(self.project, "--version", version, "--sign-key", str(self.kit.key()), "--out",
                                str(self.out), *args, home=self.bhome, env=env)

    def check_fails(self, *needles: str, args: tuple = ("--check-only",), **kw) -> str:
        res = self.build(*args, **kw)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        for n in needles:
            self.assertIn(n, res.stderr)
        return res.stdout + res.stderr

    def payload_names(self, command: Path) -> list[str]:
        info = release.read_header(command)
        payload = command.read_bytes()[info.payload_offset:]
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            return [m.name for m in tar.getmembers()]

    def append(self, rel: str, text: str) -> None:
        with open(self.project / rel, "a", encoding="utf-8") as f:
            f.write(text)

    # ------------------------------------------------------------ what ships
    def test_only_allowlisted_files_ship(self) -> None:
        planted = {".secrets/x": "TOKEN=" + "e" * 40 + "\n", "apps/server/.dev.vars": f"RUNNER_TOKEN={TOKEN}\n",
                   "results/r.json": "{}", "sources/repos/x": "x", "node_modules/x": "x",
                   "scripts/tests/wip_x.py": "", "design/eval-set.jsonl": "{}\n", "apps/runner/.env": "A=1\n",
                   "install/tests/test_x.py": "", "apps/server/src/a.test.ts": "", "apps/server/src/.DS_Store": "x",
                   "apps/zalo-bridge/bridge/__pycache__/x.cpython-314.pyc": "x"}
        for rel, text in planted.items():
            (self.project / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.project / rel).write_text(text, encoding="utf-8")
        res = self.build()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        names = {n.split("/", 1)[1] for n in self.payload_names(self.out / "thomhouse-1.4.0.command")}
        for rel in planted:
            self.assertNotIn(rel, names)
        for rel in ("VERSION.json", "MANIFEST.json", "MANIFEST.sha256", "install/versions.env",
                    "install/versions.json", "install/thomhouse.py", "install/denylist.txt", "install/bootstrap.sh",
                    "install/selfextract.sh.in", "install/thomhouse.sh.in", "install/trust/allowed_signers",
                    "install/lock/pnpm/package-lock.json", "scripts/start_local.sh", "apps/server/src/seed-data.ts",
                    "docs/cai-dat-may-moi.md", "tools/zalo-agent/package-lock.json"):
            self.assertIn(rel, names)
        self.assertFalse(any(n.startswith("scripts/release/") for n in names))
        self.assertNotIn(TOKEN, res.stdout + res.stderr)

    def test_payload_layout(self) -> None:
        res = self.build()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        command = self.out / "thomhouse-1.4.0.command"
        info = release.read_header(command)
        payload = command.read_bytes()[info.payload_offset:]
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            self.assertEqual(names, sorted(names))
            self.assertTrue(all(n.startswith("thomhouse-1.4.0/") for n in names))
            for m in members:
                self.assertEqual((m.mtime, m.uid, m.gid, m.uname, m.gname), (0, 0, 0, "", ""))
                self.assertIn(m.mode, (0o644, 0o755))
            files = {m.name.split("/", 1)[1]: tar.extractfile(m).read() for m in members}
        manifest = json.loads(files["MANIFEST.json"])
        by_path = {e["path"]: e for e in manifest["files"]}
        self.assertTrue(by_path["apps/server/src/seed-data.ts"]["runtime_written"])
        self.assertFalse(by_path["package.json"]["runtime_written"])
        self.assertEqual(by_path["scripts/start_local.sh"]["mode"], "0755")
        self.assertNotIn("MANIFEST.json", by_path)
        self.assertNotIn("MANIFEST.sha256", by_path)
        for path, entry in by_path.items():
            self.assertEqual(hashlib.sha256(files[path]).hexdigest(), entry["sha256"], path)
        self.assertEqual(files["MANIFEST.sha256"].decode().splitlines()[0],
                         f"{manifest['files'][0]['sha256']}  {manifest['files'][0]['path']}")
        version = json.loads(files["VERSION.json"])
        self.assertEqual(version, {"schema": 1, "version": "1.4.0", "menu_id": info.menu_id})
        env = dict(line.split("=", 1) for line in files["install/versions.env"].decode().splitlines())
        self.assertEqual(env["PY_VERSION"], "3.14.6")
        self.assertEqual(env["PY_URL_darwin_arm64"], kit.PY_URL)
        self.assertEqual(env["PNPM_VERSION"], "10.32.1")
        self.assertEqual(env["CLAUDE_SHA256_darwin_x64"], "")
        self.assertEqual(env["CLAUDE_INSTALLER_URL"], "https://claude.ai/install.sh")
        self.assertEqual(set(env), {
            "MACOS_MIN", "DISK_MIN_GB", "PY_VERSION", "PY_URL_darwin_arm64", "PY_SHA256_darwin_arm64",
            "PY_BYTES_darwin_arm64", "PY_URL_darwin_x64", "PY_SHA256_darwin_x64", "PY_BYTES_darwin_x64",
            "NODE_VERSION", "NODE_URL_darwin_arm64", "NODE_SHA256_darwin_arm64", "NODE_BYTES_darwin_arm64",
            "NODE_URL_darwin_x64", "NODE_SHA256_darwin_x64", "NODE_BYTES_darwin_x64", "PNPM_VERSION", "PNPM_BYTES",
            "CLAUDE_VERSION", "CLAUDE_MIN", "CLAUDE_INSTALLER_URL", "CLAUDE_APPROX_MB", "CLAUDE_SHA256_darwin_arm64",
            "CLAUDE_SHA256_darwin_x64"})
        self.assertEqual(json.loads(files["install/versions.json"])["hash_source"], "test")

    def test_same_tree_gives_the_same_payload(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        first = release.read_header(self.out / "thomhouse-1.4.0.command")
        self.out = self.tmp / "out2"
        self.assertEqual(self.build().returncode, 0)
        second = release.read_header(self.out / "thomhouse-1.4.0.command")
        self.assertEqual(first.payload_sha256, second.payload_sha256)
        self.assertEqual(first.payload_bytes, second.payload_bytes)

    def test_header_marker_release_id_and_note(self) -> None:
        res = self.build()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        command = self.out / "thomhouse-1.4.0.command"
        data = command.read_bytes()
        info = release.read_header(command)
        self.assertEqual(data[:info.payload_offset].count(b"__PAYLOAD__"), 1)
        self.assertTrue(data[:info.payload_offset].endswith(b"\n__PAYLOAD__\n"))
        self.assertEqual(command.stat().st_mode & 0o777, 0o755)
        shasum = subprocess.run(["shasum", "-a", "256", str(command)], capture_output=True, text=True).stdout.split()[0]
        printed = re.search(r"^release id: (\S+)$", res.stdout, re.M).group(1)
        self.assertEqual(printed, "-".join(shasum[:16].upper()[i:i + 4] for i in range(0, 16, 4)))
        self.assertEqual(printed, info.release_id)
        sha_line = (self.out / "thomhouse-1.4.0.sha256").read_text(encoding="utf-8")
        self.assertEqual(sha_line, f"{shasum}  thomhouse-1.4.0.command\n")
        note = (self.out / "thomhouse-1.4.0-DOC-TRUOC.txt").read_text(encoding="utf-8")
        self.assertIn("bash /Volumes/USB/thomhouse-1.4.0.command", note)
        self.assertNotIn("{version}", note)
        self.assertNotIn(printed, note)
        self.assertNotIn(shasum[:16], note.lower())
        self.assertIn("files: ", res.stdout)
        self.assertIn(f"menu_id: {info.menu_id}", res.stdout)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)

    def test_menu_archive_holds_exactly_the_indexed_slides(self) -> None:
        kit.add_menu(self.project)
        res = self.build("--menu")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        tars = list(self.out.glob("thomhouse-menu-*.tar"))
        self.assertEqual(len(tars), 1)
        with tarfile.open(tars[0]) as tar:
            self.assertEqual(tar.getnames(), ["MENU.json", "slides/facial/1.png", "slides/facial/2.png"])
            menu = json.loads(tar.extractfile("MENU.json").read())
        self.assertEqual(tars[0].name, f"thomhouse-menu-{menu['menu_id']}.tar")
        self.assertEqual(menu["menu_id"], release.menu_id_of([(f["path"], f["sha256"]) for f in menu["files"]]))
        self.assertEqual(release.read_header(self.out / "thomhouse-1.4.0.command").menu_id, menu["menu_id"])

    def test_slide_outside_the_menu_folder_fails(self) -> None:
        (self.project / "data" / "menu-images.json").write_text(json.dumps({"slides": [{"file": "data/x.png"}]}))
        self.check_fails("data/menu-images.json")

    # ------------------------------------------------------------ refusals
    def test_installed_copy_is_refused(self) -> None:
        (self.project / "VERSION.json").write_text('{"version": "1.4.0"}', encoding="utf-8")
        res = self.build("--check-only")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)

    def test_bad_arguments(self) -> None:
        res = run_make_release(self.project, "--version", "1.4", home=self.bhome)
        self.assertEqual(res.returncode, 2)
        res = run_make_release(self.project, home=self.bhome)
        self.assertEqual(res.returncode, 2)

    def test_check_only_writes_nothing(self) -> None:
        res = self.build("--check-only")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("every check passed", res.stdout)
        self.assertFalse(self.out.exists())

    def test_denylisted_path_in_the_allowlist_fails(self) -> None:
        (self.project / "results").mkdir()
        (self.project / "results" / "r.json").write_text("{}", encoding="utf-8")
        self.append("scripts/release/allowlist.txt", "results/r.json\n")
        self.check_fails("results/r.json: denylisted")

    def test_private_mode_fails(self) -> None:
        (self.project / "data" / "services.json").chmod(0o600)
        self.check_fails("data/services.json: private file mode")

    def test_symlink_and_large_file_fail(self) -> None:
        link = self.project / "apps" / "server" / "src" / "link.ts"
        link.symlink_to(self.project / "apps" / "server" / "src" / "index.ts")
        self.check_fails("apps/server/src/link.ts: a symlink")
        link.unlink()
        (self.project / "apps" / "server" / "src" / "big.ts").write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        self.check_fails("apps/server/src/big.ts: larger than 5 MB")

    def test_unmatched_allowlist_line(self) -> None:
        self.append("scripts/release/allowlist.txt", "docs/missing.md\n")
        self.check_fails("matches no file: docs/missing.md")
        text = (self.project / "scripts" / "release" / "allowlist.txt").read_text(encoding="utf-8")
        (self.project / "scripts" / "release" / "allowlist.txt").write_text(
            text.replace("docs/missing.md\n", "docs/missing.md   (optional)\n"), encoding="utf-8")
        self.assertEqual(self.build("--check-only").returncode, 0)

    def test_live_token_planted_fails_and_is_never_printed(self) -> None:
        dev = self.project / "apps" / "server" / ".dev.vars"
        dev.write_text(f"RUNNER_TOKEN={TOKEN}\nSERVER_URL=http://127.0.0.1:8787\n", encoding="utf-8")
        self.append("design/system-prompt-draft.md", f"\nleak {TOKEN}\n")
        out = self.check_fails("design/system-prompt-draft.md:", "live secret")
        self.assertNotIn(TOKEN, out)

    def test_loopback_url_and_names_in_env_files_are_not_secrets(self) -> None:
        dev = self.project / "apps" / "runner" / ".env"
        dev.write_text("SERVER_URL=http://127.0.0.1:8787\nZALO_PERSONAL_WEBHOOK_SECRET_NAME=x\n", encoding="utf-8")
        self.assertEqual(self.build("--check-only").returncode, 0)

    def test_secrets_url_file(self) -> None:
        secrets = self.project / ".secrets"
        secrets.mkdir()
        (secrets / "oauth-start-url.txt").write_text(
            "https://hooks.example-host.workers.dev/start?state=Zx81kQ0pL2mN4bV7cT9w&mode=1\n", encoding="utf-8")
        (secrets / "zalo.env.example").write_text("ZALO_APP_SECRET_KEY=placeholderplaceholder\n", encoding="utf-8")
        self.append("design/system-prompt-draft.md", "\nhost hooks.example-host.workers.dev is fine\n")
        self.append("design/system-prompt-draft.md", "placeholderplaceholder from an example file is fine\n")
        self.assertEqual(self.build("--check-only").returncode, 0)
        self.append("design/system-prompt-draft.md", "token Zx81kQ0pL2mN4bV7cT9w\n")
        out = self.check_fails("live secret")
        self.assertNotIn("Zx81kQ0pL2mN4bV7cT9w", out)

    def test_phone_number_and_long_id_fail_unless_listed(self) -> None:
        self.append("design/system-prompt-draft.md", "\nGọi 0389123456 nhé\n")
        self.check_fails("design/system-prompt-draft.md:", "phone number")
        digest = hashlib.sha256(b"0389123456").hexdigest()
        self.append("scripts/release/placeholders.txt", f"{digest}  test placeholder\n")
        self.assertEqual(self.build("--check-only").returncode, 0)
        self.append("data/business-facts.json", "")
        self.append("design/tools-schema.json", "")
        self.append("design/system-prompt-draft.md", "id 123456789012345678\n")
        self.check_fails("run of 15 to 20 digits")

    def test_hex_digests_are_not_ids(self) -> None:
        self.append("design/system-prompt-draft.md", "\nsha a0389123456b and 1234567890123456789abc\n")
        self.assertEqual(self.build("--check-only").returncode, 0)

    def test_home_path_fails(self) -> None:
        self.append("design/system-prompt-draft.md", f"\nsee {self.bhome}/Projects/x\n")
        self.check_fails("home folder path")

    def test_private_key_block_fails(self) -> None:
        self.append("design/system-prompt-draft.md", "\n-----BEGIN OPENSSH " + "PRIVATE KEY-----\nabc\n")
        self.check_fails("private key block")

    def test_syntax_checks(self) -> None:
        bad = {"apps/runner/runner/bad.py": "def x(:\n", "data/reply-templates.json": "{nope",
               "scripts/stop_local.sh": "if then fi\n"}
        for rel, text in bad.items():
            with self.subTest(rel=rel):
                original = (self.project / rel).read_text(encoding="utf-8") if (self.project / rel).exists() else None
                (self.project / rel).write_text(text, encoding="utf-8")
                self.check_fails(rel)
                if original is None:
                    (self.project / rel).unlink()
                else:
                    (self.project / rel).write_text(original, encoding="utf-8")

    def test_pin_disagreement_fails(self) -> None:
        pkg = self.project / "tools" / "zalo-agent" / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"@ardennguyen/zalo-agent-cli": "2.6.0"}}), encoding="utf-8")
        self.check_fails("pins disagree: zalo-agent-cli")

    # ------------------------------------------------------------ pins and trust
    def test_placeholder_pins_are_refused(self) -> None:
        env = build_env(self.bhome)
        del env["THOMHOUSE_RELEASE_TEST_PINS"]
        # install/versions.json as it is shipped today: "https" with null placeholders.
        out = self.check_fails("pin python.platforms.darwin-arm64.url", env=env)
        self.assertIn("refresh_pins.py", out)
        data = json.loads((self.project / "install" / "versions.json").read_text(encoding="utf-8"))
        self.assertIsNone(data["python"]["platforms"]["darwin-arm64"]["sha256"])
        data["python"]["platforms"]["darwin-arm64"]["url"] = kit.PY_URL
        (self.project / "install" / "versions.json").write_text(json.dumps(data), encoding="utf-8")
        self.check_fails("pin python.platforms.darwin-arm64.sha256", env=env)
        data["hash_source"] = None
        (self.project / "install" / "versions.json").write_text(json.dumps(data), encoding="utf-8")
        self.check_fails("hash_source", env=env)

    def test_test_pins_need_the_test_marker(self) -> None:
        pins = json.loads(self.kit.pins_file.read_text(encoding="utf-8"))
        pins["hash_source"] = "https"
        f = self.tmp / "pins.json"
        f.write_text(json.dumps(pins), encoding="utf-8")
        self.check_fails('"hash_source": "test"', extra={"THOMHOUSE_RELEASE_TEST_PINS": str(f)})
        env = build_env(self.bhome)
        del env["THOMHOUSE_RELEASE_TEST_PINS"]
        (self.project / "install" / "versions.json").write_text(self.kit.pins_file.read_text(), encoding="utf-8")
        self.check_fails("hash_source", env=env)

    def test_test_build_warns(self) -> None:
        res = self.build("--check-only")
        self.assertIn("TEST BUILD", res.stderr)

    def test_pnpm_lock_and_trust_checks(self) -> None:
        lock = self.project / "install" / "lock" / "pnpm" / "package-lock.json"
        lock.write_text(kit.pnpm_lock("10.0.0"), encoding="utf-8")
        self.check_fails("package-lock.json: root dependency pnpm")
        lock.unlink()
        self.check_fails("install/lock/pnpm/package-lock.json")
        lock.write_text(kit.pnpm_lock(), encoding="utf-8")
        (self.project / "install" / "trust" / "allowed_signers").write_text(self.kit.signers_line("other"))
        self.check_fails("does not hold the public key")
        (self.project / "install" / "trust" / "allowed_signers").unlink()
        self.check_fails("install/trust/allowed_signers is missing")

    def test_init_key(self) -> None:
        key = self.tmp / "keys" / "release"
        (self.project / "install" / "trust" / "allowed_signers").unlink()
        res = run_make_release(self.project, "--init-key", "--sign-key", str(key), home=self.bhome)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        pub = Path(str(key) + ".pub").read_text().split()
        signers = (self.project / "install" / "trust" / "allowed_signers").read_text()
        self.assertEqual(signers, f'thomhouse-release namespaces="thomhouse-release" {pub[0]} {pub[1]}\n')
        res = run_make_release(self.project, "--init-key", "--sign-key", str(key), home=self.bhome)
        self.assertEqual(res.returncode, 1)
        self.assertIn("exists", res.stderr)
        res = run_make_release(self.project, "--version", "1.4.0", "--sign-key", str(key), "--out", str(self.out),
                               home=self.bhome)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(os.stat(self.out / "thomhouse-1.4.0.command").st_mode & 0o777, 0o755)
