"""deps.py (step 7 of 16.4.3): the exact commands, the release's .npmrc and its store (rev F21), the stamp and what
makes it stale, an OpenMausBot failure as a warning, and the two errors."""

from __future__ import annotations

import io
import json
import os
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from tests.fakes_release import kit
from tests.fakes_release.kit import ReleaseTestCase
from thomhouse_installer import deps, proc
from thomhouse_installer.deps import DepsError
from thomhouse_installer.text_vi import t


class DepsTest(ReleaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.install_release("1.4.0")
        self.real_root = Path(os.path.realpath(self.root))
        rt = self.app_home / "runtime"
        self.node_bin = rt / "node" / "bin"
        self.node_bin.mkdir(parents=True)
        (self.node_bin / "node").write_bytes(kit.node_wrapper())
        (self.node_bin / "npm").write_bytes(kit.npm_wrapper())
        for f in self.node_bin.iterdir():
            f.chmod(0o755)
        (rt / "bin").mkdir()
        (rt / "bin" / "pnpm").symlink_to(Path(self.env["THOMHOUSE_FAKE_BIN"]) / "pnpm")
        self.ctx_ = self.ctx()
        self.app = self.app_home / "app"

    def install(self) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            result = deps.install(self.ctx_, self.app, self.node_bin)
        self.out = out.getvalue()
        return result

    def test_exact_commands_and_options(self) -> None:
        self.assertEqual(self.install(), {"rooms": True})
        pnpm = [c for c in self.calls("pnpm") if c["argv"][:1] == ["install"]]
        npm = [c for c in self.calls("npm") if c["argv"][:1] == ["ci"]]
        self.assertEqual([c["argv"] for c in pnpm], [["install", "--frozen-lockfile"]])
        self.assertEqual(pnpm[0]["cwd"], str(self.real_root))
        self.assertEqual([c["argv"] for c in npm], [
            ["ci", "--prefix", "tools/zalo-agent", "--no-fund", "--no-audit"],
            ["ci", "--prefix", "tools/openmausbot", "--no-fund", "--no-audit"],
        ])
        for c in pnpm + npm:
            self.assertEqual(c["path0"], str(self.node_bin))
            self.assertEqual(c["env"]["npm_config_cache"], str(self.app_home / "cache" / "npm"))
            self.assertEqual(c["env"]["DISABLE_UPDATES"], "1")
        order = [c["tool"] for c in self.calls() if c["tool"] in ("pnpm", "npm") and c["argv"][:1] in (["install"],
                                                                                                       ["ci"])]
        self.assertEqual(order, ["pnpm", "npm", "npm"])
        self.assertTrue((self.root / "tools" / "zalo-agent" / "node_modules" / ".bin" / "zalo-agent").exists())

    def test_npmrc_store_is_the_one_start_local_uses(self) -> None:
        self.install()
        store = str(self.app_home / "cache" / "pnpm-store")
        self.assertEqual((self.root / ".npmrc").read_text(encoding="utf-8"), f"store-dir={store}\n")
        self.assertEqual(self.calls("pnpm")[-1]["store_dir"], store)
        # start_local.sh runs its own `pnpm install` in the release folder later; it reads the same store.
        later = self.tmp / "later_start.sh"
        later.write_text('#!/bin/bash\nset -e\ncd "$1"\npnpm install --frozen-lockfile\n', encoding="utf-8")
        env = proc.child_env(self.ctx_.paths)
        res = subprocess.run(["/bin/bash", str(later), str(self.app)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls("pnpm")[-1]["store_dir"], store)

    def test_stamp_and_what_makes_it_stale(self) -> None:
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": False, "engine": False, "rooms": False})
        self.install()
        stamp = json.loads((self.root / ".thomhouse-deps.json").read_text(encoding="utf-8"))
        self.assertEqual(stamp["platform"], "Darwin arm64")
        self.assertEqual(stamp["node_major"], 24)
        self.assertEqual(set(stamp["locks"]), {"pnpm-lock.yaml", "tools/zalo-agent/package-lock.json",
                                               "tools/openmausbot/package-lock.json"})
        self.assertEqual(stamp["ok"], {"workspace": True, "engine": True, "rooms": True})
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": True, "engine": True, "rooms": True})

        self.behave(system={"cpu": "x64"})  # the release folder carried to an Intel Mac
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": False, "engine": False, "rooms": False})
        self.behave(system={"cpu": "arm64"})

        lock = self.root / "pnpm-lock.yaml"
        lock.write_text(lock.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": False, "engine": True, "rooms": True})

        engine = self.root / "tools" / "zalo-agent" / "node_modules" / "@ardennguyen" / "zalo-agent-cli"
        (engine / "package.json").write_text(json.dumps({"version": "2.5.8"}), encoding="utf-8")
        self.assertFalse(deps.stamp_ok(self.ctx_, self.app)["engine"])

        self.install()  # a reinstall makes the stamp current again
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": True, "engine": True, "rooms": True})

    def test_node_major_change_makes_the_stamp_stale(self) -> None:
        self.install()
        (self.node_bin / "node").write_bytes(kit.node_wrapper("25.0.0"))
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": False, "engine": False, "rooms": False})

    def test_openmausbot_failure_is_a_warning(self) -> None:
        self.behave(npm={"fail": ["openmausbot"]})
        self.assertEqual(self.install(), {"rooms": False})
        self.assertIn(t("release.deps_rooms_warn"), self.out)
        self.assertEqual(deps.stamp_ok(self.ctx_, self.app), {"workspace": True, "engine": True, "rooms": False})

    def test_workspace_and_engine_failures(self) -> None:
        for behaviour, which in (({"pnpm": {"fail": True}}, "workspace"), ({"npm": {"fail": ["zalo-agent"]}}, "engine")):
            with self.subTest(which=which):
                (self.tmp / "behaviour.json").write_text("{}", encoding="utf-8")
                self.behave(**behaviour)
                with self.assertRaises(DepsError) as cm:
                    self.install()
                self.assertEqual((cm.exception.which, cm.exception.code, cm.exception.key),
                                 (which, 1, f"release.deps_{which}"))
                self.assertFalse(deps.stamp_ok(self.ctx_, self.app)[which])
                text = t(cm.exception.key, cmd="~/ThomHouse/bin/thomhouse continue")
                self.assertIn("~/ThomHouse/logs/deps.log", text)

    def test_pnpm_bin_of_an_update(self) -> None:
        other = self.tmp / "newpnpm"
        other.mkdir()
        (other / "pnpm").symlink_to(Path(self.env["THOMHOUSE_FAKE_BIN"]) / "pnpm")
        out = io.StringIO()
        with redirect_stdout(out):
            deps.install(self.ctx_, self.app, self.node_bin, pnpm_bin=other / "pnpm")
        pnpm = [c for c in self.calls("pnpm") if c["argv"][:1] == ["install"]]
        self.assertEqual(len(pnpm), 1)
        self.assertTrue(deps.stamp_ok(self.ctx_, self.app)["workspace"])

    def test_without_openmausbot_no_rooms_install(self) -> None:
        import shutil

        shutil.rmtree(self.root / "tools" / "openmausbot")
        self.assertEqual(self.install(), {"rooms": False})
        self.assertEqual(len([c for c in self.calls("npm") if c["argv"][:1] == ["ci"]]), 1)
        self.assertNotIn(t("release.deps_rooms_warn"), self.out)
