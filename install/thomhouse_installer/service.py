"""The commands `start`, `stop` and `restart` (16.3.1 WP5 `service.py`, 16.3.3, 16.8.8).

`start` runs `stack.start` (exit 3 while the data moved out or an update is unfinished), then `stack.health_gate`
and the doctor checks `listen_local_only` and `openmausbot_options`. With `--quiet` (the LaunchAgent) only errors
are printed.
"""

from __future__ import annotations

from . import stack
from .backup import print_failed_checks, tb, tilde
from .context import EXIT_FAILED, EXIT_OK
from .text_vi import say

SAFETY_CHECKS = ("listen_local_only", "openmausbot_options")


def cmd_start(ctx, args) -> int:
    """0 running and healthy, 1 failed, 3 refused (raised by stack.start)."""
    from . import doctor

    paths = ctx.paths
    quiet = bool(getattr(args, "quiet", False)) or ctx.quiet
    code = stack.start(ctx, quiet=quiet)
    if code != 0:
        say("ops.start_failed", log=tilde(paths.logs / "start.log", paths), tb=tb(paths))
        return EXIT_FAILED
    failed = list(stack.health_gate(ctx))
    bad = [r for r in doctor.run_checks(ctx, only=set(SAFETY_CHECKS)) if getattr(r, "status", None) == "fail"]
    for check_id in failed:
        say(f"ops.health_{check_id}")
    print_failed_checks(bad)
    if failed or bad:
        say("ops.start_unhealthy", tb=tb(paths))
        return EXIT_FAILED
    if not quiet:
        say("ops.start_done")
    return EXIT_OK


def cmd_stop(ctx, args) -> int:
    """0 stopped, 1 when a process survives."""
    if stack.stop(ctx):
        say("ops.stop_done")
        return EXIT_OK
    say("ops.stop_survivor", tb=tb(ctx.paths))
    return EXIT_FAILED


def cmd_restart(ctx, args) -> int:
    """`stop`, then `start`."""
    if not stack.stop(ctx):
        say("ops.stop_survivor", tb=tb(ctx.paths))
        return EXIT_FAILED
    return cmd_start(ctx, args)
