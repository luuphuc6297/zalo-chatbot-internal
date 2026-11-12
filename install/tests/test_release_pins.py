"""Pins on the real project files (16.2.2 step 3, 16.2.5): the pnpm lock package equals packageManager, the engine
and OpenMausBot pins agree, versions.json has the schema of 16.2.5; the real allowlist expands and its files pass the
id scan with placeholders.txt; refresh_pins.py with its network functions replaced (never run against the network);
and the shell files' copies of catalog texts equal the catalog."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests.fakes_release.kit import ReleaseTestCase
from tests.support import INSTALL_DIR, PROJECT_ROOT
from thomhouse_installer import pins, release
from thomhouse_installer.text_vi import t


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class RealProjectPinsTest(ReleaseTestCase):
    def test_pnpm_lock_package_equals_package_manager(self) -> None:
        pm = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))["packageManager"]
        version = pm.split("@", 1)[1].split("+", 1)[0]
        lock_dir = INSTALL_DIR / "lock" / "pnpm"
        pkg = json.loads((lock_dir / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["dependencies"], {"pnpm": version})
        lock = lock_dir / "package-lock.json"
        if lock.exists():  # written by refresh_pins.py on the build Mac
            data = json.loads(lock.read_text(encoding="utf-8"))
            self.assertEqual(data["packages"][""]["dependencies"]["pnpm"], version)

    def test_engine_and_openmausbot_pins_agree(self) -> None:
        self.assertEqual(pins.agreement(PROJECT_ROOT), [])

    def test_versions_json_schema(self) -> None:
        data = json.loads((INSTALL_DIR / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"schema", "macos_min", "disk_min_gb", "python", "node", "pnpm", "claude_code",
                                     "hash_source"})
        self.assertNotIn("features", data)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(set(data["python"]), {"version", "min", "platforms"})
        self.assertEqual(set(data["node"]), {"version", "min_stack", "min_rooms_major", "platforms"})
        self.assertEqual(set(data["claude_code"]), {"version", "min", "installer_url", "approx_installed_mb",
                                                    "platforms"})
        for section in ("python", "node", "claude_code"):
            self.assertEqual(set(data[section]["platforms"]), {"darwin-arm64", "darwin-x64"})
        self.assertIsNone(data["claude_code"]["platforms"]["darwin-x64"]["sha256"])
        p = pins.load(PROJECT_ROOT)
        self.assertEqual(p.pnpm_version, "10.32.1")

    def test_real_allowlist_expands_and_passes_the_id_scan(self) -> None:
        make_release = _load("make_release_real", PROJECT_ROOT / "scripts" / "release" / "make_release.py")
        entries = make_release.parse_allowlist(
            (PROJECT_ROOT / "scripts" / "release" / "allowlist.txt").read_text(encoding="utf-8"))
        self.assertTrue(any(e["glob"] == "install/**" and e["except"] == ["install/tests/**"] for e in entries))
        files = make_release.collect(entries, release.denylist(PROJECT_ROOT))
        self.assertIn("install/thomhouse.py", files)
        self.assertFalse(any(p.startswith("install/tests/") for p in files))
        contents = {p: f.read_bytes() for p, f in files.items()}
        # Only the id rules: no secret values are read here (the live-secret scan runs in make_release itself).
        problems = make_release.scan(contents, set(), make_release.placeholders(), [])
        self.assertEqual(problems, [])

    def test_placeholders_file_format(self) -> None:
        lines = [x for x in (PROJECT_ROOT / "scripts" / "release" / "placeholders.txt").read_text().splitlines()
                 if x.strip() and not x.startswith("#")]
        self.assertEqual(len(lines), 2)
        for line in lines:
            digest, comment = line.split(None, 1)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertTrue(comment)
            self.assertNotRegex(comment, r"\d{9,}")


class RefreshPinsTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.tmp / "project"
        (self.project / "install" / "lock" / "pnpm").mkdir(parents=True)
        shutil.copy2(PROJECT_ROOT / "package.json", self.project / "package.json")
        shutil.copy2(INSTALL_DIR / "versions.json", self.project / "install" / "versions.json")
        shutil.copy2(INSTALL_DIR / "lock" / "pnpm" / "package.json",
                     self.project / "install" / "lock" / "pnpm" / "package.json")
        (self.project / "tools" / "zalo-agent").mkdir(parents=True)
        shutil.copy2(PROJECT_ROOT / "tools" / "zalo-agent" / "package.json",
                     self.project / "tools" / "zalo-agent" / "package.json")
        quiet = io.StringIO()
        for redirect in (redirect_stdout(quiet), redirect_stderr(quiet)):
            redirect.__enter__()
            self.addCleanup(redirect.__exit__, None, None, None)
        self.mod =_load("refresh_pins_test", PROJECT_ROOT / "scripts" / "release" / "refresh_pins.py")
        self.mod.PROJECT = self.project
        self.mod.VERSIONS = self.project / "install" / "versions.json"
        self.mod.LOCK_DIR = self.project / "install" / "lock" / "pnpm"
        self.urls: list[str] = []
        tag = "20260115"
        arm = f"cpython-3.14.6+{tag}-aarch64-apple-darwin-install_only.tar.gz"
        self.py_sha, self.node_sha = "a" * 64, "b" * 64
        base = "https://github.com/astral-sh/python-build-standalone/releases/download/" + tag
        releases = [
            {"tag_name": "20260201", "assets": [{"name": "SHA256SUMS", "browser_download_url": "https://x/none"}]},
            {"tag_name": tag, "assets": [
                {"name": arm, "size": 41000000, "browser_download_url": f"{base}/{arm}"},
                {"name": "SHA256SUMS", "browser_download_url": f"{base}/SHA256SUMS"}]},
        ]
        self.pages = {
            self.mod.PBS_API + "?per_page=30": json.dumps(releases).encode(),
            f"{base}/SHA256SUMS": f"{self.py_sha}  {arm}\n{'c' * 64}  other.tar.gz\n".encode(),
            "https://nodejs.org/dist/v24.19.0/SHASUMS256.txt":
                f"{self.node_sha}  node-v24.19.0-darwin-arm64.tar.gz\n{'d' * 64}  node-v24.19.0-linux-x64.tar.gz\n"
                .encode(),
        }
        self.sizes = {"https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz": 49000000,
                      "https://registry.npmjs.org/pnpm/-/pnpm-10.32.1.tgz": 4500000}

        def fetch_bytes(url: str) -> bytes:
            self.urls.append(url)
            if url not in self.pages:
                raise self.mod.RefreshError(f"download failed: {url}")
            return self.pages[url]

        def fetch_size(url: str) -> int:
            self.urls.append("HEAD " + url)
            if url not in self.sizes:
                raise self.mod.RefreshError(f"no size for {url}")
            return self.sizes[url]

        self.mod.fetch_bytes = fetch_bytes
        self.mod.fetch_size = fetch_size
        self.binary = self.home / ".local" / "share" / "claude" / "versions" / "2.1.319"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"claude binary bytes")

    def test_refresh_writes_versions_and_lock(self) -> None:
        self.assertEqual(self.mod.main([]), 0)
        data = json.loads(self.mod.VERSIONS.read_text(encoding="utf-8"))
        self.assertEqual(data["hash_source"], "https")
        self.assertEqual(data["python"]["platforms"]["darwin-arm64"]["sha256"], self.py_sha)
        self.assertEqual(data["python"]["platforms"]["darwin-arm64"]["bytes"], 41000000)
        self.assertTrue(data["python"]["platforms"]["darwin-arm64"]["url"].endswith("install_only.tar.gz"))
        self.assertEqual(data["node"]["platforms"]["darwin-arm64"],
                         {"url": "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz",
                          "sha256": self.node_sha, "bytes": 49000000})
        self.assertIsNone(data["node"]["platforms"]["darwin-x64"]["sha256"])
        self.assertEqual(data["pnpm"]["bytes"], 4500000)
        self.assertEqual(data["claude_code"]["platforms"]["darwin-arm64"],
                         {"sha256": hashlib.sha256(b"claude binary bytes").hexdigest(), "bytes": 19})
        self.assertEqual(data["claude_code"]["platforms"]["darwin-x64"], {"sha256": None, "bytes": None})
        lock = json.loads((self.mod.LOCK_DIR / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"][""]["dependencies"], {"pnpm": "10.32.1"})
        npm = [c for c in self.calls("npm") if c["argv"][:1] == ["install"]]
        self.assertEqual(npm[0]["argv"], ["install", "--package-lock-only", "--ignore-scripts", "--no-audit",
                                          "--no-fund"])
        self.assertTrue(all(u.startswith(("https://", "HEAD https://")) for u in self.urls))
        p = pins.load(self.project)
        self.assertEqual((p.python.sha256, p.node.bytes), (self.py_sha, 49000000))

    def test_nothing_written_when_something_is_missing(self) -> None:
        before = self.mod.VERSIONS.read_bytes()
        self.binary.unlink()
        self.assertEqual(self.mod.main([]), 1)
        self.assertEqual(self.mod.VERSIONS.read_bytes(), before)
        self.assertFalse((self.mod.LOCK_DIR / "package-lock.json").exists())
        self.binary.write_bytes(b"x")
        del self.pages["https://nodejs.org/dist/v24.19.0/SHASUMS256.txt"]
        self.assertEqual(self.mod.main([]), 1)
        self.assertEqual(self.mod.VERSIONS.read_bytes(), before)

    def test_bad_arguments(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            self.mod.main(["--node", "24"])
        self.assertEqual(cm.exception.code, 2)
        with self.assertRaises(SystemExit) as cm:
            self.mod.main(["--platforms", "linux-x64"])
        self.assertEqual(cm.exception.code, 2)

    def test_only_https(self) -> None:
        mod = _load("refresh_pins_https", PROJECT_ROOT / "scripts" / "release" / "refresh_pins.py")
        with self.assertRaises(mod.RefreshError):
            mod.fetch_bytes("http://nodejs.org/dist/x")
        self.assertEqual(sys.modules.get("refresh_pins_https"), None)


class ShellTextCopiesTest(ReleaseTestCase):
    """The shell files print copies of catalog texts before Python exists; keep them equal."""

    COPIES = [
        ("release.damaged", {}, ("selfextract.sh.in", "bootstrap.sh")),
        ("release.signature", {}, ("selfextract.sh.in",)),
        ("release.already_installed", {"file": "$SELF"}, ("selfextract.sh.in",)),
        ("release.plan_head", {}, ("bootstrap.sh",)),
        ("release.plan_ask", {}, ("bootstrap.sh",)),
        ("release.plan_claude_other", {}, ("bootstrap.sh",)),
        ("release.decline_head", {"folder": "$AH"}, ("bootstrap.sh",)),
        ("release.decline_pnpm", {"v": "$PNPM_VERSION"}, ("bootstrap.sh",)),
        ("release.decline_claude", {"v": "$CLAUDE_VERSION"}, ("bootstrap.sh",)),
        ("release.decline_tail", {"folder": "$AH/cache/downloads/"}, ("bootstrap.sh",)),
        ("release.plan_python", {"v": "$PY_VERSION", "host": '$(host_of "$PY_URL")', "n": '$(mb "$PY_BYTES")',
                                 "folder": "$AH/runtime"}, ("bootstrap.sh",)),
        ("release.plan_node", {"v": "$NODE_VERSION", "host": '$(host_of "$NODE_URL")', "n": '$(mb "$NODE_BYTES")',
                               "folder": "$AH/runtime"}, ("bootstrap.sh",)),
        ("release.plan_pnpm", {"v": "$PNPM_VERSION", "host": "registry.npmjs.org", "n": '$(mb "$PNPM_BYTES")',
                               "folder": "$AH/runtime"}, ("bootstrap.sh",)),
        ("core.locked", {}, ("selfextract.sh.in",)),
        ("core.answer_yes", {}, ("selfextract.sh.in", "bootstrap.sh")),
        ("core.answer_noninteractive", {"answer": "k"}, ("selfextract.sh.in", "bootstrap.sh")),
        ("core.ask_again", {"choices": "c, k"}, ("selfextract.sh.in", "bootstrap.sh")),
        ("core.whitespace_path", {"folder": "$folder"}, ("selfextract.sh.in", "bootstrap.sh")),
    ]

    def test_copies_equal_the_catalog(self) -> None:
        for key, fmt, files in self.COPIES:
            for name in files:
                text = (INSTALL_DIR / name).read_text(encoding="utf-8")
                for line in t(key, **fmt).splitlines():
                    with self.subTest(key=key, file=name, line=line):
                        self.assertIn(line, text)

    def test_claude_plan_line_is_split_but_equal(self) -> None:
        text = (INSTALL_DIR / "bootstrap.sh").read_text(encoding="utf-8")
        head = '  - Claude Code $CLAUDE_VERSION: chương trình cài của Anthropic (claude.ai),'
        self.assertIn(head, text)
        self.assertIn('say "$LINE khoảng $CLAUDE_MB MB, vào ~/.local"', text)
        self.assertEqual(t("release.plan_claude", v="X", n="N"),
                         head.replace("$CLAUDE_VERSION", "X") + " khoảng N MB, vào ~/.local")
