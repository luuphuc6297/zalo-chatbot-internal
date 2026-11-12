"""pins.py and install/versions.json: loading, placeholders, agreement of the engine pins (16.2.2 step 3, 16.2.5)."""

from __future__ import annotations

import json

from tests.support import INSTALL_DIR, PROJECT_ROOT, InstallerTestCase
from thomhouse_installer import pins


class PinsTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release()

    def test_load_from_release(self) -> None:
        loaded = pins.load(self.root, "darwin-arm64")
        self.assertEqual(loaded.macos_min, (13, 5))
        self.assertEqual(loaded.disk_min_gb, 3)
        self.assertEqual(loaded.python.version, "3.14.6")
        self.assertEqual(loaded.python_min, "3.11")
        self.assertEqual(loaded.node.version, "24.19.0")
        self.assertEqual(loaded.node.url, "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz")
        self.assertEqual(loaded.node_min_stack, "22.19.0")
        self.assertEqual(loaded.node_min_rooms_major, 24)
        self.assertEqual(loaded.pnpm_version, "10.32.1")
        self.assertEqual(loaded.claude.version, "2.1.319")
        self.assertEqual(loaded.claude.url, "https://claude.ai/install.sh")
        self.assertEqual(loaded.claude_min, "2.1.319")
        self.assertEqual(loaded.claude_approx_mb, 310)
        self.assertEqual(loaded.engine_version, "2.5.9")
        self.assertEqual(loaded.openmausbot_version, "0.1.154")

    def test_placeholders_are_none(self) -> None:
        loaded = pins.load(self.root, "darwin-arm64")
        for pin in (loaded.python, loaded.node, loaded.claude):
            self.assertIsNone(pin.sha256)
            self.assertIsNone(pin.bytes)
        self.assertIsNone(loaded.python.url)
        self.assertIsNone(loaded.pnpm_bytes)
        x64 = pins.load(self.root, "darwin-x64")
        self.assertIsNone(x64.claude.sha256)
        none = pins.load(self.root, None)
        self.assertIsNone(none.node.url)

    def test_filled_pins(self) -> None:
        f = self.root / "install" / "versions.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        data["python"]["platforms"]["darwin-arm64"] = {"url": "https://example.invalid/py.tar.gz",
                                                       "sha256": "AB" * 32, "bytes": 41_000_000}
        data["claude_code"]["platforms"]["darwin-arm64"] = {"sha256": "cd" * 32, "bytes": 200}
        data["pnpm"]["bytes"] = 5000
        f.write_text(json.dumps(data), encoding="utf-8")
        loaded = pins.load(self.root)
        self.assertEqual(loaded.python.sha256, "ab" * 32)
        self.assertEqual(loaded.python.bytes, 41_000_000)
        self.assertEqual(loaded.claude.sha256, "cd" * 32)
        self.assertEqual(loaded.pnpm_bytes, 5000)

    def test_missing_pins_raise(self) -> None:
        (self.root / "install" / "versions.json").write_text("{", encoding="utf-8")
        with self.assertRaises(pins.PinError) as cm:
            pins.load(self.root)
        self.assertEqual((cm.exception.code, cm.exception.key, cm.exception.fmt["name"]),
                         (2, "core.pin_missing", "versions.json"))
        (self.root / "install" / "versions.json").write_text(json.dumps({"schema": 1}), encoding="utf-8")
        with self.assertRaises(pins.PinError):
            pins.load(self.root)
        (self.root / "install" / "versions.json").write_text(
            (INSTALL_DIR / "versions.json").read_text(encoding="utf-8"), encoding="utf-8")
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(pins.PinError) as cm:
            pins.load(self.root)
        self.assertEqual(cm.exception.fmt["name"], "packageManager")

    def test_agreement(self) -> None:
        self.assertEqual(pins.agreement(self.root), [])
        start = self.root / "scripts" / "start_local.sh"
        start.write_text(start.read_text(encoding="utf-8").replace('ENGINE_VERSION="2.5.9"', 'ENGINE_VERSION="2.6.0"'),
                         encoding="utf-8")
        self.assertEqual(pins.agreement(self.root), ["zalo-agent-cli"])
        start.write_text(start.read_text(encoding="utf-8").replace('ENGINE_VERSION="2.6.0"', 'ENGINE_VERSION="2.5.9"'),
                         encoding="utf-8")
        lock = self.root / "tools" / "openmausbot" / "package-lock.json"
        data = json.loads(lock.read_text(encoding="utf-8"))
        data["packages"][""]["dependencies"]["openmausbot"] = "0.1.155"
        lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(pins.agreement(self.root), ["openmausbot"])
        (self.root / "tools" / "openmausbot" / "package.json").unlink()
        self.assertEqual(pins.agreement(self.root), [])  # rooms are optional
        (self.root / "apps" / "zalo-bridge" / "bridge" / "config.py").unlink()
        self.assertEqual(pins.agreement(self.root), ["zalo-agent-cli"])

    def test_project_versions_json(self) -> None:
        data = json.loads((INSTALL_DIR / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertNotIn("features", data)
        self.assertEqual(data["hash_source"], "https")
        for name in ("python", "node", "claude_code"):
            for plat in ("darwin-arm64", "darwin-x64"):
                entry = data[name]["platforms"][plat]
                self.assertIsNone(entry["sha256"], f"{name} {plat}: only refresh_pins.py fills hashes")
                self.assertIsNone(entry["bytes"])
        self.assertIsNone(data["pnpm"]["bytes"])

    def test_real_project_pins_load_and_agree(self) -> None:
        loaded = pins.load(PROJECT_ROOT)
        self.assertEqual(loaded.pnpm_version, "10.32.1")
        self.assertEqual(pins.agreement(PROJECT_ROOT), [])
