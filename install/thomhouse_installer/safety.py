"""Read-only helpers of the safety checks 41 and 42 (invariants 1 and 2, rev F16).

Nothing here changes a process: `ps` and `lsof` are only read. This is the one installer file that may hold the
forbidden OpenMausBot options as text (`test_core_static` skips it), because check 42 must name them to find them.
"""

from __future__ import annotations

import subprocess

FORBIDDEN_PLATFORM_ARGS: tuple[str, ...] = ("--tunnel", "--lan", "--relay", "--domain", "--public-url",
                                            "--tailscale", "login")
TIMEOUT_S = 15


def _read(cmd: list[str]) -> tuple[int, str]:
    """Run a read-only tool and return (exit code, stdout); 127 and "" when it cannot run."""
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return cp.returncode, cp.stdout or ""


def pgid_table() -> dict[int, int]:
    """{pid: pgid} of every process, from `ps -ax -o pid=,pgid=`; {} when ps cannot run."""
    code, out = _read(["ps", "-ax", "-o", "pid=,pgid="])
    table: dict[int, int] = {}
    if code != 0:
        return table
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = int(parts[1])
    return table


def group_pids(pgids: list[int]) -> list[int]:
    """Sorted PIDs of every process whose process group is one of `pgids` (from `ps -ax -o pid=,pgid=`)."""
    wanted = {int(g) for g in pgids if int(g) > 0}
    if not wanted:
        return []
    return sorted(pid for pid, pgid in pgid_table().items() if pgid in wanted)


def _split_name(name: str) -> tuple[str, int] | None:
    """`127.0.0.1:8787`, `*:8787`, `[::1]:8787` -> (address, port)."""
    if ":" not in name:
        return None
    address, _, port = name.rpartition(":")
    if not port.isdigit() or not address:
        return None
    return address, int(port)


def listen_sockets(pids: list[int]) -> list[tuple[int, str, int]]:
    """(pid, address, port) of every TCP LISTEN socket of `pids`, from `lsof -nP -a -p <pids> -iTCP -sTCP:LISTEN`.

    The address is as lsof prints it: `127.0.0.1`, `[::1]`, `*`, `192.168.1.5`. An empty `pids` gives [] without
    calling lsof, because `lsof -p ""` would list every process.
    """
    wanted = sorted({int(p) for p in pids if int(p) > 0})
    if not wanted:
        return []
    code, out = _read(["lsof", "-nP", "-a", "-p", ",".join(str(p) for p in wanted), "-iTCP", "-sTCP:LISTEN"])
    found: list[tuple[int, str, int]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[1].isdigit() or "(LISTEN)" not in parts:
            continue
        at = parts.index("(LISTEN)")
        if at < 1:
            continue
        split = _split_name(parts[at - 1])
        if split is None:
            continue
        entry = (int(parts[1]), split[0], split[1])
        if entry not in found:
            found.append(entry)
    return found


def process_argv(pid: int) -> list[str]:
    """The arguments of process `pid` from `ps -ww -o args= -p PID`, split on whitespace (no installer path holds
    whitespace, 16.2.7); [] when the process is gone."""
    code, out = _read(["ps", "-ww", "-o", "args=", "-p", str(int(pid))])
    if code != 0:
        return []
    return out.split()


def forbidden_platform_args(argv: list[str]) -> list[str]:
    """The forbidden options found in `argv`, each named once without its value (rev F16).

    Whole elements only: an element equal to "login", equal to an option, or starting with "<option>=". A path that
    merely contains those letters (`--data-dir /Users/a/login-x/...`) never matches. Values are not returned, so a
    URL or token given to an option is never shown.
    """
    found: list[str] = []
    for element in argv:
        for option in FORBIDDEN_PLATFORM_ARGS:
            hit = element == option or (option.startswith("--") and element.startswith(option + "="))
            if hit and option not in found:
                found.append(option)
    return found
