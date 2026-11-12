"""The stand-ins that the setup and operations tests load in place of other packages' modules
(tests/fakes_setup/wp_stubs, tests/fakes_ops/stub_modules) keep the real modules' interfaces: every public function
of a stand-in exists in the real module with the same parameter names and kinds, and every dataclass of a stand-in
has the real dataclass's fields in the same order (the real one may add trailing fields with defaults). A stand-in
that drifts from the real module would let a cross-package mismatch pass those tests unseen."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

import thomhouse_installer as pkg

TESTS = Path(__file__).resolve().parent
STAND_IN_DIRS = {
    "setup": (TESTS / "fakes_setup" / "wp_stubs", "_stubrec"),
    "ops": (TESTS / "fakes_ops" / "stub_modules", "_stubio"),
}
# Helpers that exist only in a stand-in and that no code under test calls.
STAND_IN_ONLY = {("ops", "runtimes", "current")}


def _load(full: str, path: Path):
    spec = importlib.util.spec_from_file_location(full, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


class StandInParityTest(unittest.TestCase):
    def test_stand_ins_match_the_real_modules(self) -> None:
        for kind, (folder, helper) in STAND_IN_DIRS.items():
            names = sorted(f.stem for f in folder.glob("*.py") if not f.name.startswith("_"))
            self.assertTrue(names, folder)
            for name in names:
                real = importlib.import_module(f"thomhouse_installer.{name}")
                full = f"thomhouse_installer.{name}"
                helper_full = f"thomhouse_installer.{helper}"
                with mock.patch.dict(sys.modules), mock.patch.object(pkg, helper, None, create=True):
                    setattr(pkg, helper, _load(helper_full, folder / f"{helper}.py"))
                    stand_in = _load(full, folder / f"{name}.py")
                for attr, obj in vars(stand_in).items():
                    if attr.startswith("_") or getattr(obj, "__module__", None) != full:
                        continue
                    if (kind, name, attr) in STAND_IN_ONLY:
                        continue
                    with self.subTest(stand_in=f"{kind}/{name}.{attr}"):
                        self.assertTrue(hasattr(real, attr), "missing in the real module")
                        target = getattr(real, attr)
                        if inspect.isfunction(obj):
                            mine = [(p.name, p.kind) for p in inspect.signature(obj).parameters.values()]
                            theirs = [(p.name, p.kind) for p in inspect.signature(target).parameters.values()]
                            self.assertEqual(mine, theirs)
                        elif dataclasses.is_dataclass(obj):
                            mine = [f.name for f in dataclasses.fields(obj)]
                            theirs = dataclasses.fields(target)
                            self.assertEqual(mine, [f.name for f in theirs][:len(mine)])
                            for extra in theirs[len(mine):]:
                                self.assertFalse(extra.default is dataclasses.MISSING
                                                 and extra.default_factory is dataclasses.MISSING, extra.name)

    def test_doctor_test_stand_ins_match_the_real_modules(self) -> None:
        """The WP2 stand-ins that test_doctor_checks builds in `stub_wp2` take the real functions' parameters."""
        from tests.test_doctor_checks import DoctorFixture

        class Holder(DoctorFixture):
            def __init__(self) -> None:
                self.cleanups: list = []

            def addCleanup(self, fn, *args) -> None:  # noqa: N802 - the unittest name
                self.cleanups.append((fn, args))

        holder = Holder()
        modules = holder.stub_wp2()
        for fn, args in reversed(holder.cleanups):
            fn(*args)
        for full, stand_in in modules.items():
            real = importlib.import_module(full)
            for attr, obj in vars(stand_in).items():
                if attr.startswith("_") or not callable(obj):
                    continue
                with self.subTest(stand_in=f"{full}.{attr}"):
                    self.assertTrue(hasattr(real, attr), "missing in the real module")
                    mine = [p.name for p in inspect.signature(obj).parameters.values()]
                    theirs = [p.name for p in inspect.signature(getattr(real, attr)).parameters.values()
                              if p.default is inspect.Parameter.empty and p.kind is not p.VAR_KEYWORD]
                    self.assertEqual(mine, theirs)


if __name__ == "__main__":
    unittest.main()
