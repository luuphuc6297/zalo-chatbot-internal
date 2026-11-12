"""Operating system, macOS version, CPU and free disk (16.5).

The OS comes from `uname -s` (and `/proc/version` for WSL), the macOS version from `sw_vers -productVersion`, the
CPU from `sysctl -n hw.optional.arm64` (macOS) or `uname -m`. Every tool is looked up on PATH, so tests can put fakes
first. Nothing here installs or changes anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROC_VERSION = Path("/proc/version")  # tests patch this module attribute


@dataclass(frozen=True)
class Platform:
    """What `detect()` found."""

    os: str  # "darwin" | "linux" | "wsl" | "windows" | "other"
    uname: str  # raw `uname -s`
    macos: tuple[int, ...] | None
    cpu: str  # "arm64" | "x64" | "other"
    key: str | None  # "darwin-arm64" | "darwin-x64" | None


def _out(run: Callable[..., subprocess.CompletedProcess], cmd: list[str]) -> tuple[int, str]:
    try:
        cp = run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return cp.returncode, (cp.stdout or "").strip()


def _parse_version(text: str) -> tuple[int, ...] | None:
    parts = []
    for piece in text.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or None


def _os_of(uname_s: str) -> str:
    name = uname_s.strip()
    upper = name.upper()
    if name == "Darwin":
        return "darwin"
    if name == "Linux":
        try:
            text = PROC_VERSION.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            text = ""
        return "wsl" if "microsoft" in text else "linux"
    if upper.startswith(("MINGW", "MSYS", "CYGWIN")):
        return "windows"
    return "other"


def _cpu_of_machine(machine: str) -> str:
    m = machine.strip().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64", "x64"):
        return "x64"
    return "other"


def detect(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Platform:
    """Detect the platform with `run` (default `subprocess.run`); a missing tool counts as an empty answer."""
    _, uname_s = _out(run, ["uname", "-s"])
    os_name = _os_of(uname_s)
    macos = None
    cpu = "other"
    if os_name == "darwin":
        _, ver = _out(run, ["sw_vers", "-productVersion"])
        macos = _parse_version(ver)
        rc, arm = _out(run, ["sysctl", "-n", "hw.optional.arm64"])
        if rc == 0 and arm == "1":
            cpu = "arm64"
        elif rc == 0 and arm == "0":
            cpu = "x64"
        else:  # Intel Macs may not know the key at all
            _, machine = _out(run, ["uname", "-m"])
            cpu = _cpu_of_machine(machine)
    else:
        _, machine = _out(run, ["uname", "-m"])
        cpu = _cpu_of_machine(machine)
    key = None
    if os_name == "darwin" and cpu in ("arm64", "x64"):
        key = f"darwin-{cpu}"
    return Platform(os=os_name, uname=uname_s, macos=macos, cpu=cpu, key=key)


def free_gb(path: Path) -> float:
    """Free space in GB (10**9 bytes) on the disk of `path`, or of its nearest existing parent."""
    p = Path(os.path.abspath(str(path)))
    while not p.exists() and p != p.parent:
        p = p.parent
    usage = shutil.disk_usage(p)
    return usage.free / 1e9
