"""Command context, exit codes and the error classes every package raises (16.3.3).

Every error meant for the person subclasses `InstallerError`. The dispatcher of `install/thomhouse.py` prints
`t(err.key, **err.fmt)` and returns `err.code`, so it never imports another package's exception classes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:  # imported lazily at run time: paths imports this module for Exit
    from .paths import Paths
    from .pins import Pins
    from .platforms import Platform

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED, EXIT_DECLINED, EXIT_HUMAN_PENDING = 0, 1, 2, 3, 4, 10


class InstallerError(Exception):
    """An error shown to the person as one catalog text.

    `code` is the exit code of the command, `key` the text key (16.4.7 or a package catalog) and `fmt` the format
    values of that text. `fmt` never holds a secret, an email, a Zalo id or message text.
    """

    code: int = 1
    key: str = "core.failed"

    def __init__(self, key: str | None = None, code: int | None = None, **fmt: object) -> None:
        if key is not None:
            self.key = key
        if code is not None:
            self.code = code
        self.fmt: dict[str, object] = dict(fmt)
        super().__init__(self.key)


class Exit(InstallerError):
    """Stop the command with `code`; with `key` None the dispatcher prints nothing."""

    def __init__(self, code: int, key: str | None = None, **fmt: object) -> None:
        super().__init__(None, code, **fmt)
        self.key = key  # type: ignore[assignment]  # None means: print nothing
        self.args = (key,)


@dataclass
class Ctx:
    """Everything a command needs: paths, a copy of the environment, the parsed arguments and common flags.

    `platform` and `pins` are computed on first use (`platforms.detect()`, `pins.load()`); `pins` raises
    `PinError`. `log()` writes one JSON line to `logs/install.log` through `proc.redact` and never prints.
    """

    paths: "Paths"
    env: Mapping[str, str]
    args: argparse.Namespace
    yes: bool = False
    dry_run: bool = False
    quiet: bool = False
    offline: bool = False
    interactive: bool = False
    _platform: "Platform | None" = field(default=None, repr=False)
    _pins: "Pins | None" = field(default=None, repr=False)

    @property
    def platform(self) -> "Platform":
        """`platforms.detect()` on first use, then cached."""
        if self._platform is None:
            from . import platforms

            self._platform = platforms.detect()
        return self._platform

    @platform.setter
    def platform(self, value: "Platform") -> None:
        self._platform = value

    @property
    def pins(self) -> "Pins":
        """`pins.load(paths.code_root, platform.key)` on first use, then cached; raises `PinError`."""
        if self._pins is None:
            from . import pins

            self._pins = pins.load(self.paths.code_root, self.platform.key)
        return self._pins

    @pins.setter
    def pins(self, value: "Pins") -> None:
        self._pins = value

    def log(self, event: str, **fields: object) -> None:
        """Append `{"at", "event", ...}` as one JSON line to `logs/install.log`, secrets replaced by `***`.

        Never prints and never raises: a log that cannot be written is skipped. With `dry_run` nothing is written,
        because --dry-run changes nothing on the device (16.4.5).
        """
        from . import proc

        if self.dry_run:
            return
        try:
            record: dict[str, object] = {
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "event": event,
            }
            record.update(fields)
            line = json.dumps(record, ensure_ascii=False, default=str)
            line = proc.redact(line, proc.secret_values(self.paths))
            logs = self.paths.logs
            logs.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(logs, 0o700)
            except OSError:
                pass
            target = logs / "install.log"
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:  # noqa: BLE001 - logging must never stop a command
            pass


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except (ValueError, OSError):
        return False


def make_ctx(
    args: argparse.Namespace, env: Mapping[str, str] | None = None, *, paths: "Paths | None" = None
) -> Ctx:
    """Build the context of one command.

    `env` defaults to a copy of `os.environ`. `paths` defaults to `paths.resolve(env)`; the dispatcher passes the
    paths it resolved from the logical location of `thomhouse.py`, because the package itself is imported from the
    real (symlink-resolved) folder. Raises `Exit(3, "core.whitespace_path")` like `paths.resolve`.
    """
    from . import paths as paths_mod

    env_copy = dict(os.environ if env is None else env)
    p = paths if paths is not None else paths_mod.resolve(env_copy)
    return Ctx(
        paths=p,
        env=env_copy,
        args=args,
        yes=bool(getattr(args, "yes", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        quiet=bool(getattr(args, "quiet", False)),
        offline=bool(getattr(args, "offline", False)),
        interactive=_stdin_is_tty(),
    )
