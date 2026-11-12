"""Stand-in for thomhouse_installer.autostart (WP5) in the setup tests: records the calls only.
Behaviour "stub_autostart": {"fail": "enable" or "shortcuts"} raises an InstallerError."""

from __future__ import annotations

from thomhouse_installer import _stubrec
from thomhouse_installer.context import InstallerError


def _maybe_fail(name: str) -> None:
    if _stubrec.fails("autostart", name):
        raise InstallerError("core.failed")


def enable(ctx) -> None:
    _stubrec.record("autostart", "enable")
    _maybe_fail("enable")


def disable(ctx) -> None:
    _stubrec.record("autostart", "disable")


SHORTCUTS_MARK = "[stub] desktop files written"


def shortcuts(ctx, on: bool) -> None:
    _stubrec.record("autostart", "shortcuts", on)
    _maybe_fail("shortcuts")
    print(SHORTCUTS_MARK, flush=True)  # lets a test see what was printed before the files were written


def remove_all(ctx) -> list[str]:
    _stubrec.record("autostart", "remove_all")
    return []
