"""`thomhouse doctor`: the 48 checks of 16.7, `passes()` for the install steps, and the doctor command.

Each check is a function `fn(ctx, cache) -> CheckResult`; `run_checks()` calls them in order and shares one cache
dict per call, so the bridge doctor, the Claude pool and the login statuses are read at most once per call. Before
a check runs, `run_checks()` applies the rules of 16.7 that do not depend on the check itself:

- checkout mode: checks 9 to 11, 16 to 19, 22, 44 to 46 and 48 are "skip" (the build Mac has no install);
- installed mode without `installed.json`, full run only: checks 10 to 48 are "todo" (before install). A run with
  `only` (the step checks of `passes()`, or `--only`) always inspects the machine, so an install step whose check
  names a doctor check sees the real state before step 8 too;
- `--offline`: the checks marked net, and the other checks that need the bridge doctor, are "skip";
- stack stopped (no service of `start_local.sh` alive): the checks marked run are "skip", except `processes`.

No check calls `/runner/*` or sends RUNNER_TOKEN (rev F7). Staff calls send STAFF_TOKEN to the loopback server only.
No detail holds a token, an email, a Zalo id, a name or a message: the bridge doctor and the pool are read through
`bridgecli.doctor()` and `accounts`, which keep statuses only.

Calls into WP2 (`release`, `deps`, `runtimes`) go through `_part()`: when that module is not installed the check
fails with `doctor.part_missing` instead of crashing.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import accounts, bridgecli, envs, migrations, platforms, proc, safety, stack, state
from . import pins as pins_mod
from .context import EXIT_FAILED, EXIT_OK, EXIT_USAGE
from .text_vi import t

STATUSES = ("pass", "fail", "warn", "todo", "skip")
STATUS_KEYS = {
    "pass": "doctor.status_pass",
    "fail": "doctor.status_fail",
    "warn": "doctor.status_warn",
    "todo": "doctor.status_todo",
    "skip": "doctor.status_skip",
}
MACOS_MIN_DEFAULT = (13, 5)
DISK_MIN_DEFAULT = 3
PYTHON_MIN_DEFAULT = "3.11"
# 16.5 names /usr/bin and /usr/sbin; macOS keeps launchctl in /bin, so /bin and /sbin are looked at too.
SYSTEM_TOOLS = ("curl", "shasum", "tar", "lsof", "ssh-keygen", "pbcopy", "pbpaste", "open", "sips", "hdiutil",
                "launchctl", "sw_vers", "sysctl")
SYSTEM_TOOL_DIRS = ("/usr/bin", "/usr/sbin", "/bin", "/sbin")
OS_NAMES = {"linux": "Linux", "wsl": "Windows (WSL)", "windows": "Windows"}
CHECKOUT_SKIP = frozenset({"release", "release_files", "release_clean", "deps_workspace", "deps_engine",
                           "deps_rooms", "menu_slides", "paths_current", "history_sync", "contacts_analyzed",
                           "visits_analyzed", "staff_token_step"})
BRIDGE_CHECKS = frozenset({"zalo_login", "listener", "bridge_token", "room_platform"})
# Commands that checkout mode runs (16.4.1); start, stop and restart become the scripts of the checkout (16.7).
CHECKOUT_COMMANDS = frozenset({"doctor", "backup", "backups", "restore", "move-out", "move-back"})
CHECKOUT_SCRIPTS = {"start": "scripts/start_local.sh", "stop": "scripts/stop_local.sh",
                    "restart": "scripts/stop_local.sh; scripts/start_local.sh"}
REQUIRED_KEYS = {
    "server": ("RUNNER_TOKEN", "STAFF_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET"),
    "runner": ("SERVER_URL", "RUNNER_TOKEN"),
    "bridge": ("SERVER_URL", "RUNNER_TOKEN", "ZALO_PERSONAL_WEBHOOK_SECRET"),
}
ENV_NAMES = ("server", "runner", "bridge", "console_local")
API_KEY_NAMES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
TRUTHY = ("1", "true", "yes", "on")
CATALOG_FILES = ("data/services.json", "data/business-facts.json", "design/system-prompt-draft.md",
                 "design/tools-schema.json")
LOOPBACK_ADDRESSES = ("127.0.0.1", "[::1]", "::1")
STACK_NAMES = ("server", "cron", "runner", "bridge", "console")
DEFAULT_RUNNER_ID = "mac-runner-1"  # apps/runner/runner/config.py when RUNNER_ID is missing (rev check)
BACKUP_MAX_AGE = timedelta(days=7)
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass
class CheckResult:
    """One doctor line. `status` is one of pass, fail, warn, todo, skip; `crashed` marks a check that raised (the
    command then exits 2) and is not part of `as_dict()`."""

    n: int
    id: str
    group: str
    status: str
    label: str
    detail: str
    fix: str | None
    crashed: bool = field(default=False, repr=False, compare=False)

    def as_dict(self) -> dict:
        """{"n", "id", "group", "status", "label", "detail", "fix"} for `--json`."""
        return {"n": self.n, "id": self.id, "group": self.group, "status": self.status, "label": self.label,
                "detail": self.detail, "fix": self.fix}


@dataclass
class CheckDef:
    """One check of 16.7: `net` checks are skipped with --offline, `run` checks while the stack is stopped."""

    n: int
    id: str
    group: str
    net: bool
    run: bool
    fn: Callable[..., CheckResult]


# ---------------------------------------------------------------- small helpers

def _tilde(path: Path | str, home: Path) -> str:
    text = str(path)
    h = str(home).rstrip("/")
    if h and (text == h or text.startswith(h + "/")):
        return "~" + text[len(h):]
    return text


def _tb(ctx) -> str:
    """How the person types this program: the launcher, or the checkout form (16.7)."""
    if ctx.paths.mode != "installed":
        return "python3 -I install/thomhouse.py"
    return _tilde(ctx.paths.launcher, ctx.paths.home)


def _cmd(ctx, command: str, *args: str) -> str | None:
    """`{tb} <command> <args>`; in checkout mode the script form of start, stop and restart, and None for a command
    that checkout mode refuses (16.4.1)."""
    if ctx.paths.mode != "installed":
        if command in CHECKOUT_SCRIPTS and not args:
            return CHECKOUT_SCRIPTS[command]
        if command not in CHECKOUT_COMMANDS:
            return None
    return " ".join([_tb(ctx), command, *args])


def _fix(ctx, key: str | None, command: str, *args: str, **fmt: object) -> str:
    """A fix that names a command: the command alone (key None) or the text `key` with it as {cmd}. A command that
    checkout mode refuses becomes the pointer to docs/run-local.md (16.7, rev check)."""
    cmd = _cmd(ctx, command, *args)
    if cmd is None:
        return t("doctor.see_docs")
    if key is None:
        return cmd
    return t(key, cmd=cmd, **fmt)


def _version_tuple(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    m = _VERSION.search(text)
    if m:
        return tuple(int(x) for x in m.groups())
    parts = []
    for piece in str(text).split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) or None


def _first_version(text: str) -> str | None:
    m = _VERSION.search(text or "")
    return ".".join(m.groups()) if m else None


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _release_version(code_root: Path) -> str | None:
    data = _read_json(code_root / "VERSION.json")
    if isinstance(data, dict) and isinstance(data.get("version"), str):
        return data["version"]
    return None


def _version(ctx) -> str:
    """The version of the release this code belongs to, for `thomhouse-<version>.command`."""
    return _release_version(ctx.paths.code_root) or "checkout"


def _parse_time(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value


def _date(text: object) -> str | None:
    value = _parse_time(text)
    return value.strftime("%d/%m/%Y") if value else None


def _rel(ctx, path: Path) -> str:
    try:
        return str(path.relative_to(ctx.paths.app))
    except ValueError:
        return _tilde(path, ctx.paths.home)


def _part(name: str):
    """The WP2 module `name`, or None when it is not part of this copy of the program."""
    full = f"{__package__}.{name}"
    try:
        return importlib.import_module(full)
    except ModuleNotFoundError as e:
        if e.name == full:
            return None
        raise


def _res(check_id: str, status: str, detail: str, fix: str | None = None) -> CheckResult:
    d = BY_ID[check_id]
    return CheckResult(d.n, d.id, d.group, status, t(f"doctor.label_{d.id}"), detail, fix)


def _part_missing(check_id: str, part: str) -> CheckResult:
    return _res(check_id, "fail", t("doctor.part_missing", name=part), t("doctor.report_to_maker"))


def _pins(ctx, c: dict):
    if "pins" not in c:
        try:
            c["pins"], c["pins_error"] = ctx.pins, None
        except pins_mod.PinError as e:
            c["pins"], c["pins_error"] = None, e.name
    return c["pins"]


def _pins_fail(check_id: str, c: dict) -> CheckResult:
    return _res(check_id, "fail", t("doctor.pins_unreadable", name=c.get("pins_error") or "versions.json"),
                t("doctor.report_to_maker"))


def _installed(ctx, c: dict) -> dict | None:
    if "installed" not in c:
        c["installed"] = state.load_installed(ctx.paths)
    return c["installed"]


def _services(ctx, c: dict) -> dict[str, stack.Service]:
    if "services" not in c:
        c["services"] = {s.name: s for s in stack.services(ctx.paths)}
    return c["services"]


def _stopped(ctx, c: dict) -> bool:
    return not any(s.alive for s in _services(ctx, c).values())


def _bridge(ctx, c: dict) -> dict[str, str] | None:
    if "bridge" not in c:
        c["bridge"] = bridgecli.doctor(ctx)
    return c["bridge"]


def _pool(ctx, c: dict) -> list:
    if "pool" not in c:
        c["pool"] = accounts.load(ctx)
    return c["pool"]


def _auth(ctx, c: dict) -> dict:
    if "auth" not in c:
        c["auth"] = {a.label: accounts.auth_status(ctx, a) for a in _pool(ctx, c)}
    return c["auth"]


def _journal(ctx, c: dict) -> dict[str, dict]:
    if "journal" not in c:
        c["journal"] = state.steps_all(ctx.paths)
    return c["journal"]


def _staff_token(ctx) -> str | None:
    return envs.value(ctx.paths, "server", "STAFF_TOKEN")


def _path_version(ctx, cmd: list[str]) -> str | None:
    """The first x.y.z of `cmd` (a tool on the caller's PATH, checkout mode only)."""
    res = proc.run(ctx, cmd, capture=True, timeout=30)
    if res.returncode != 0:
        return None
    return _first_version(res.stdout + " " + res.stderr)


def _found(ctx, c: dict, name: str) -> tuple[bool, str | None]:
    """(module present, `runtimes.found(ctx, name)`), cached per call."""
    key = f"found:{name}"
    if key not in c:
        rt = _part("runtimes")
        c[key] = (False, None) if rt is None else (True, rt.found(ctx, name))
    return c[key]


def _node_version(ctx, c: dict) -> str | None:
    if "node_version" not in c:
        if ctx.paths.mode == "installed":
            c["node_version"] = _found(ctx, c, "node")[1]
        else:
            c["node_version"] = _path_version(ctx, ["node", "--version"])
    return c["node_version"]


def _dep(ctx, c: dict, check_id: str) -> CheckResult:
    """The result of another check in this call, run now when it was not run yet."""
    return _evaluate(ctx, BY_ID[check_id], c)


# ---------------------------------------------------------------- 1 to 8: the machine

def _check_macos(ctx, c: dict) -> CheckResult:
    p = ctx.platform
    if p.os != "darwin":
        name = OS_NAMES.get(p.os) or t("doctor.os_other", name=p.uname or "?")
        return _res("macos", "fail", t("doctor.os_unsupported", name=name), t("doctor.os_unsupported_fix"))
    if not p.macos:
        return _res("macos", "fail", t("doctor.macos_unknown"), t("doctor.macos_old_fix"))
    version = ".".join(str(x) for x in p.macos)
    pins = _pins(ctx, c)
    need = pins.macos_min if pins else MACOS_MIN_DEFAULT
    if tuple(p.macos) < tuple(need):
        return _res("macos", "fail", t("doctor.macos_old", v=version, min=".".join(str(x) for x in need)),
                    t("doctor.macos_old_fix"))
    return _res("macos", "pass", f"macOS {version}")


def _check_cpu(ctx, c: dict) -> CheckResult:
    p = ctx.platform
    if p.os != "darwin":
        return _res("cpu", "skip", t("doctor.not_mac"))
    if p.cpu == "arm64":
        return _res("cpu", "pass", "Apple Silicon")
    return _res("cpu", "warn", t("doctor.cpu_intel"), t("doctor.cpu_intel_fix"))


def _check_disk(ctx, c: dict) -> CheckResult:
    free = platforms.free_gb(ctx.paths.home)
    pins = _pins(ctx, c)
    need = pins.disk_min_gb if pins else DISK_MIN_DEFAULT
    n = int(free)
    if free < need:
        return _res("disk", "fail", t("doctor.disk_low", n=n, m=need), t("doctor.disk_low_fix"))
    return _res("disk", "pass", f"{n} GB")


def _check_system_tools(ctx, c: dict) -> CheckResult:
    missing = [tool for tool in SYSTEM_TOOLS
               if not any(os.access(os.path.join(folder, tool), os.X_OK) for folder in SYSTEM_TOOL_DIRS)]
    if missing:
        return _res("system_tools", "fail", t("doctor.system_tools_missing", names=", ".join(missing)),
                    t("doctor.system_tools_fix"))
    return _res("system_tools", "pass", t("doctor.enough"))


def _checkout_python(ctx, minimum: str) -> str | None:
    """16.5 checkout rule: the first of python3.14 ... python3.11, python3 on PATH that is >= minimum. The macOS
    shim /usr/bin/python3 is never run (its first run can open the developer-tools dialog)."""
    path = ctx.env.get("PATH") or os.environ.get("PATH", "")
    shim = os.path.realpath("/usr/bin/python3")
    need = _version_tuple(minimum) or (3, 11)
    for name in [f"python3.{m}" for m in range(14, 10, -1)] + ["python3"]:
        exe = shutil.which(name, path=path)
        if not exe or os.path.abspath(exe) == "/usr/bin/python3" or os.path.realpath(exe) == shim:
            continue
        version = _path_version(ctx, [exe, "--version"])
        if version and (_version_tuple(version) or ()) >= need:
            return version
    return None


def _check_python(ctx, c: dict) -> CheckResult:
    pins = _pins(ctx, c)
    if ctx.paths.mode != "installed":
        minimum = pins.python_min if pins else PYTHON_MIN_DEFAULT
        found = _checkout_python(ctx, minimum)
        if found:
            return _res("python", "pass", found)
        return _res("python", "fail", t("doctor.python_checkout_missing", v=minimum), t("doctor.see_docs"))
    if pins is None:
        return _pins_fail("python", c)
    present, found = _found(ctx, c, "python")
    if not present:
        return _part_missing("python", "runtimes")
    if found == pins.python.version:
        return _res("python", "pass", found)
    if _installed(ctx, c) is not None:
        fix = "bash " + _tilde(ctx.paths.app_home / "app" / "install" / "bootstrap.sh", ctx.paths.home) \
            + " --python-only"
    else:
        fix = t("doctor.python_fix_first", version=_version(ctx))
    return _res("python", "fail", t("doctor.python_missing", v=pins.python.version), fix)


def _check_install_lock(ctx, c: dict) -> CheckResult:
    holder = state.lock_holder(ctx.paths)
    if holder is None or state.held_by_us(ctx.paths):
        return _res("install_lock", "pass", t("doctor.none"))
    return _res("install_lock", "fail", t("doctor.install_lock_held"), t("doctor.install_lock_fix"))


def _check_moved_out(ctx, c: dict) -> CheckResult:
    mark = state.moved_out(ctx.paths)
    if mark is None:
        return _res("moved_out", "pass", t("doctor.moved_out_pass"))
    date = _date(mark.get("at"))
    detail = t("doctor.moved_out_at", date=date) if date else t("doctor.moved_out_plain")
    return _res("moved_out", "fail", detail, _fix(ctx, "doctor.moved_out_fix", "move-back"))


def _other_root(svc: stack.Service) -> str | None:
    """The project or release folder of another installation's service, from its working folder or command line."""
    markers = ("/apps/", "/tools/openmausbot/")
    candidates = [str(svc.cwd)] if svc.cwd is not None else []
    if svc.pid:
        candidates += [a for a in safety.process_argv(svc.pid) if a.startswith("/")]
    for text in candidates:
        for marker in markers:
            if marker in text:
                return text.split(marker, 1)[0]
    return None


def _check_other_stack(ctx, c: dict) -> CheckResult:
    others = stack.other_stacks(ctx.paths)
    if not others:
        return _res("other_stack", "pass", t("doctor.none"))
    folder = next((f for f in (_other_root(s) for s in others) if f), None)
    detail = (t("doctor.other_stack_at", folder=_tilde(folder, ctx.paths.home)) if folder
              else t("doctor.other_stack_plain"))
    return _res("other_stack", "fail", detail, t("doctor.other_stack_fix"))


# ---------------------------------------------------------------- 9 to 19: the program

def _check_release(ctx, c: dict) -> CheckResult:
    paths = ctx.paths
    installed = _installed(ctx, c)
    if installed is None:
        return _res("release", "fail", t("doctor.release_missing"),
                    t("doctor.release_missing_fix", version=_version(ctx)))
    journal = state.update_open(paths)
    if journal is not None:
        return _res("release", "fail", t("doctor.release_update_open"),
                    _fix(ctx, None, "update", str(journal.get("file") or "FILE")))
    version = installed.get("version")
    ok = False
    if isinstance(version, str) and version:
        target = paths.release_dir(version)
        app = paths.app_home / "app"
        ok = (app.is_symlink() and os.path.realpath(app) == os.path.realpath(target)
              and _release_version(target) == version)
    if ok:
        when = _date(installed.get("installed_at")) or "?"
        return _res("release", "pass", t("doctor.release_pass", v=version, date=when))
    return _res("release", "fail", t("doctor.release_mismatch"), _fix(ctx, None, "repair"))


def _manifest_files(root: Path) -> list[dict]:
    data = _read_json(root / "MANIFEST.json")
    files = data.get("files") if isinstance(data, dict) else None
    return [f for f in files if isinstance(f, dict)] if isinstance(files, list) else []


def _check_release_files(ctx, c: dict) -> CheckResult:
    release = _part("release")
    if release is None:
        return _part_missing("release_files", "release")
    bad = release.verify_manifest(ctx.paths.code_root)
    if not bad:
        return _res("release_files", "pass",
                    t("doctor.release_files_pass", n=len(_manifest_files(ctx.paths.code_root))))
    return _res("release_files", "fail", t("doctor.release_files_bad", n=len(bad)), _fix(ctx, None, "repair"))


def _check_release_clean(ctx, c: dict) -> CheckResult:
    release = _part("release")
    if release is None:
        return _part_missing("release_clean", "release")
    patterns = release.denylist(ctx.paths.code_root)
    hits: list[str] = []
    try:
        folders = sorted(p for p in ctx.paths.releases.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        folders = []
    for folder in folders:
        for entry in _manifest_files(folder):
            rel = entry.get("path")
            if isinstance(rel, str) and release.denylisted(rel, patterns):
                hits.append(f"{folder.name}/{rel}")
    if not hits:
        return _res("release_clean", "pass", t("doctor.none"))
    return _res("release_clean", "fail", t("doctor.release_clean_bad", path=hits[0]), t("doctor.release_clean_fix"))


def _check_node(ctx, c: dict) -> CheckResult:
    pins = _pins(ctx, c)
    if pins is None:
        return _pins_fail("node", c)
    if ctx.paths.mode == "installed":
        present, found = _found(ctx, c, "node")
        if not present:
            return _part_missing("node", "runtimes")
        if found == pins.node.version:
            return _res("node", "pass", found)
        return _res("node", "fail", t("doctor.version_missing", v=pins.node.version),
                    _fix(ctx, None, "install", "--only", "runtimes"))
    found = _node_version(ctx, c)
    minimum = pins.node_min_stack
    need = _version_tuple(minimum) or (22,)
    if not found:
        return _res("node", "fail", t("doctor.node_checkout_missing", min=minimum), t("doctor.see_docs"))
    have = _version_tuple(found) or (0,)
    if have[0] < need[0]:
        return _res("node", "fail", t("doctor.node_checkout_old", v=found, min=minimum), t("doctor.see_docs"))
    if have < need:
        return _res("node", "warn", t("doctor.node_checkout_untested", v=found, min=minimum))
    if have[0] < pins.node_min_rooms_major:
        return _res("node", "warn", t("doctor.node_checkout_no_rooms", v=found, major=pins.node_min_rooms_major))
    return _res("node", "pass", found)


def _check_pnpm(ctx, c: dict) -> CheckResult:
    pins = _pins(ctx, c)
    if pins is None:
        return _pins_fail("pnpm", c)
    want = pins.pnpm_version
    if ctx.paths.mode == "installed":
        present, found = _found(ctx, c, "pnpm")
        if not present:
            return _part_missing("pnpm", "runtimes")
        if found == want:
            return _res("pnpm", "pass", found)
        return _res("pnpm", "fail", t("doctor.version_missing", v=want),
                    _fix(ctx, None, "install", "--only", "runtimes"))
    found = _path_version(ctx, ["pnpm", "--version"])
    if found == want:
        return _res("pnpm", "pass", found)
    if found and (_version_tuple(found) or (0,))[0] == (_version_tuple(want) or (-1,))[0]:
        return _res("pnpm", "warn", t("doctor.pnpm_checkout_other", v=found, min=want))
    return _res("pnpm", "fail", t("doctor.version_missing", v=want), t("doctor.see_docs"))


def _check_claude_cli(ctx, c: dict) -> CheckResult:
    pins = _pins(ctx, c)
    if pins is None:
        return _pins_fail("claude_cli", c)
    paths = ctx.paths
    installed_mode = paths.mode == "installed"
    if installed_mode:
        present, found = _found(ctx, c, "claude_code")
        if not present:
            return _part_missing("claude_cli", "runtimes")
        fix = _fix(ctx, None, "install", "--only", "runtimes")
    else:
        found = _path_version(ctx, ["claude", "--version"])
        fix = t("doctor.see_docs")
    have = _version_tuple(found)
    if have is None or have < (_version_tuple(pins.claude_min) or (0,)):
        return _res("claude_cli", "fail", t("doctor.claude_cli_missing", min=pins.claude_min), fix)
    if installed_mode:
        link = paths.runtime_bin / "claude"
        target = paths.home / ".local" / "bin" / "claude"
        try:
            linked = link.is_symlink() and os.path.normpath(os.readlink(link)) == os.path.normpath(str(target))
        except OSError:
            linked = False
        if not linked:
            return _res("claude_cli", "fail", t("doctor.claude_cli_link"), fix)
    if have > (_version_tuple(pins.claude.version) or (0,)):
        return _res("claude_cli", "warn", t("doctor.claude_cli_newer", v=found, min=pins.claude.version))
    return _res("claude_cli", "pass", str(found))


def _check_pins(ctx, c: dict) -> CheckResult:
    bad = pins_mod.agreement(ctx.paths.code_root)
    if not bad:
        return _res("pins", "pass", t("doctor.agree"))
    return _res("pins", "fail", t("doctor.pins_disagree", names=", ".join(bad)), t("doctor.report_to_maker"))


def _stamp(ctx, c: dict) -> dict | None:
    if "stamp" not in c:
        deps = _part("deps")
        c["stamp"] = None if deps is None else dict(deps.stamp_ok(ctx, ctx.paths.code_root))
    return c["stamp"]


def _package_version(path: Path) -> str | None:
    data = _read_json(path)
    value = data.get("version") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def _check_deps_workspace(ctx, c: dict) -> CheckResult:
    stamp = _stamp(ctx, c)
    if stamp is None:
        return _part_missing("deps_workspace", "deps")
    if stamp.get("workspace"):
        return _res("deps_workspace", "pass", t("doctor.deps_workspace_pass"))
    return _res("deps_workspace", "fail", t("doctor.deps_workspace_bad"), _fix(ctx, None, "install", "--only", "deps"))


def _check_deps_engine(ctx, c: dict) -> CheckResult:
    stamp = _stamp(ctx, c)
    if stamp is None:
        return _part_missing("deps_engine", "deps")
    pins = _pins(ctx, c)
    if pins is None:
        return _pins_fail("deps_engine", c)
    pkg = ctx.paths.code_root / "tools" / "zalo-agent" / "node_modules" / pins_mod.ENGINE_PACKAGE / "package.json"
    if stamp.get("engine") and _package_version(pkg) == pins.engine_version:
        return _res("deps_engine", "pass", pins.engine_version)
    return _res("deps_engine", "fail", t("doctor.deps_engine_bad", v=pins.engine_version),
                _fix(ctx, None, "install", "--only", "deps"))


def _check_deps_rooms(ctx, c: dict) -> CheckResult:
    stamp = _stamp(ctx, c)
    if stamp is None:
        return _part_missing("deps_rooms", "deps")
    if stamp.get("rooms"):
        pkg = ctx.paths.code_root / "tools" / "openmausbot" / "node_modules" / pins_mod.ROOMS_PACKAGE / "package.json"
        pins = _pins(ctx, c)
        version = _package_version(pkg) or (pins.openmausbot_version if pins else None) or "?"
        return _res("deps_rooms", "pass", version)
    return _res("deps_rooms", "warn", t("doctor.deps_rooms_bad"), _fix(ctx, None, "install", "--only", "deps"))


def _check_menu_slides(ctx, c: dict) -> CheckResult:
    release = _part("release")
    if release is None:
        return _part_missing("menu_slides", "release")
    data = _read_json(ctx.paths.code_root / "VERSION.json")
    menu_id = str(data.get("menu_id") or "?") if isinstance(data, dict) else "?"
    if release.menu_slides_ok(ctx, ctx.paths.code_root):
        return _res("menu_slides", "pass", t("doctor.menu_slides_pass", menu_id=menu_id))
    fix = _fix(ctx, "doctor.menu_slides_fix", "install", "--only", "menu_slides", "--menu", "<file>", menu_id=menu_id)
    return _res("menu_slides", "warn", t("doctor.menu_slides_bad", menu_id=menu_id), fix)


# ---------------------------------------------------------------- 20 to 25: configuration

def _check_env_files(ctx, c: dict) -> CheckResult:
    for name, keys in REQUIRED_KEYS.items():
        path = ctx.paths.env_file(name)
        rel = _rel(ctx, path)
        bad_keys: tuple[str, ...] | list[str] = ()
        try:
            mode = path.stat().st_mode
        except OSError:
            mode = None
        if mode is None or not path.is_file() or mode & 0o077:
            bad_keys = keys
        else:
            data = envs.read(path)
            bad_keys = [k for k in keys if not data.get(k)]
        if bad_keys:
            return _res("env_files", "fail", t("doctor.env_files_bad", file=rel, names=", ".join(bad_keys)),
                        _fix(ctx, None, "install", "--only", "config"))
    return _res("env_files", "pass", t("doctor.env_files_pass"))


def _digest(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _check_tokens_agree(ctx, c: dict) -> CheckResult:
    paths = ctx.paths
    runner = [_digest(envs.value(paths, n, "RUNNER_TOKEN")) for n in ("server", "runner", "bridge")]
    secret = [_digest(envs.value(paths, n, "ZALO_PERSONAL_WEBHOOK_SECRET")) for n in ("server", "bridge")]
    ok = all(runner) and len(set(runner)) == 1 and all(secret) and len(set(secret)) == 1
    if ok:
        return _res("tokens_agree", "pass", t("doctor.agree"))
    return _res("tokens_agree", "fail", t("doctor.tokens_disagree"), _fix(ctx, None, "repair", "--env"))


def _under(value: str, folder: Path) -> bool:
    text = os.path.abspath(os.path.expanduser(value))
    prefix = str(folder).rstrip("/") + "/"
    return text.startswith(prefix)


def _check_paths_current(ctx, c: dict) -> CheckResult:
    paths = ctx.paths
    fix = _fix(ctx, None, "repair", "--paths")
    engine = envs.value(paths, "bridge", "ZALO_AGENT_BIN")
    if not engine or not _under(engine, paths.app_home / "app") or not os.path.exists(os.path.expanduser(engine)):
        return _res("paths_current", "fail", t("doctor.paths_stale", name="ZALO_AGENT_BIN"), fix)
    node_dir = envs.value(paths, "runner", "OPENMAUSBOT_NODE_DIR")
    if node_dir and (not _under(node_dir, paths.runtime) or not os.path.isdir(os.path.expanduser(node_dir))):
        return _res("paths_current", "fail", t("doctor.paths_stale", name="OPENMAUSBOT_NODE_DIR"), fix)
    return _res("paths_current", "pass", t("doctor.correct"))


def _check_permissions(ctx, c: dict) -> CheckResult:
    paths = ctx.paths
    folders = [paths.app_home] if paths.mode == "installed" else []
    folders.append(paths.bot_home)
    for sub in ("backups", "profiles"):
        if (paths.bot_home / sub).is_dir():
            folders.append(paths.bot_home / sub)
    for folder in folders:
        try:
            mode = os.stat(folder).st_mode
        except OSError:
            continue
        if mode & 0o077:
            return _res("permissions", "fail", t("doctor.permissions_bad", folder=_tilde(folder, paths.home)),
                        _fix(ctx, None, "repair"))
    return _res("permissions", "pass", t("doctor.correct"))


def _settings_sources(ctx) -> list[tuple[str, dict[str, str]]]:
    """(where, values) of the environment and of every env file under `app`; values never leave this module."""
    out: list[tuple[str, dict[str, str]]] = [(t("doctor.where_environment"), dict(ctx.env))]
    for name in ENV_NAMES:
        path = ctx.paths.env_file(name)
        out.append((_rel(ctx, path), envs.read(path)))
    return out


def _check_no_api_key(ctx, c: dict) -> CheckResult:
    sources = _settings_sources(ctx)
    fix = _fix(ctx, "doctor.remove_line_fix", "restart")
    for where, values in sources:
        for name in API_KEY_NAMES:
            if (values.get(name) or "").strip():
                return _res("no_api_key", "fail", t("doctor.api_key_set", where=where, name=name), fix)
    for where, values in sources:
        if (values.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip():
            return _res("no_api_key", "warn", t("doctor.oauth_token_set", where=where), fix)
    return _res("no_api_key", "pass", t("doctor.none"))


def _check_profile_llm_off(ctx, c: dict) -> CheckResult:
    for where, values in _settings_sources(ctx):
        if (values.get("PROFILE_LLM_ENABLED") or "").strip().lower() in TRUTHY:
            return _res("profile_llm_off", "fail", t("doctor.profile_llm_on", where=where),
                        _fix(ctx, "doctor.remove_line_fix", "restart"))
    return _res("profile_llm_off", "pass", t("doctor.profile_llm_pass"))


# ---------------------------------------------------------------- 26 to 28: data

def _check_database(ctx, c: dict) -> CheckResult:
    if migrations.find_db(ctx.paths.bot_home) is not None:
        return _res("database", "pass", t("doctor.database_pass"))
    return _res("database", "todo", t("doctor.database_missing"), _fix(ctx, None, "install", "--only", "migrations"))


def _check_migrations(ctx, c: dict) -> CheckResult:
    bot = ctx.paths.bot_home
    done = migrations.applied(bot)
    if done == [] and migrations.find_db(bot) is None:
        return _res("migrations", "todo", t("doctor.migrations_no_db"),
                    _fix(ctx, None, "install", "--only", "migrations"))
    pending = migrations.pending(ctx.paths.code_root, bot)
    if pending is None:
        return _res("migrations", "warn", t("doctor.migrations_unknown"))
    if pending:
        return _res("migrations", "fail", t("doctor.migrations_pending", n=len(pending)),
                    _fix(ctx, "doctor.migrations_fix", "restart"))
    return _res("migrations", "pass", t("doctor.migrations_pass", n=len(done or [])))


def _check_last_backup(ctx, c: dict) -> CheckResult:
    fix = _fix(ctx, None, "backup")
    found = state.list_backups(ctx.paths)
    if not found:
        return _res("last_backup", "warn", t("doctor.backup_none"), fix)
    newest = found[0]
    when = _parse_time(newest.created_at)
    if when is None:
        try:
            when = datetime.fromtimestamp(newest.path.stat().st_mtime).astimezone()
        except OSError:
            return _res("last_backup", "warn", t("doctor.backup_none"), fix)
    age = datetime.now().astimezone() - when
    if age <= BACKUP_MAX_AGE:
        return _res("last_backup", "pass", when.strftime("%d/%m/%Y"))
    return _res("last_backup", "warn", t("doctor.backup_old", n=age.days), fix)


# ---------------------------------------------------------------- 29, 30: Claude

def _check_claude_pool(ctx, c: dict) -> CheckResult:
    pool = _pool(ctx, c)
    fix = _fix(ctx, None, "login-claude")
    usable = [a for a in pool if a.enabled and a.usable_now]
    if usable:
        paused = [a.label for a in pool if a.enabled and not a.usable_now]
        if paused:
            return _res("claude_pool", "warn", t("doctor.pool_paused", labels=", ".join(paused)))
        return _res("claude_pool", "pass", t("doctor.pool_pass", n=len(usable)))
    if all(not a.enabled for a in pool):
        return _res("claude_pool", "todo", t("doctor.pool_all_disabled"), fix)
    return _res("claude_pool", "fail", t("doctor.pool_none_usable"), fix)


def _check_claude_login(ctx, c: dict) -> CheckResult:
    pool = _pool(ctx, c)
    if not pool:
        return _res("claude_login", "todo", t("doctor.login_no_account"), _fix(ctx, None, "login-claude"))
    statuses = _auth(ctx, c)
    api_key, missing, no_plan = [], [], []
    for account in pool:
        st = statuses.get(account.label)
        if st is None or not st.logged_in:
            missing.append(account.label)
        elif st.auth_method != "claude.ai":
            api_key.append(account.label)
        elif not st.subscription:
            no_plan.append(account.label)
    if api_key:
        return _res("claude_login", "fail", t("doctor.login_api_key", label=api_key[0]),
                    _fix(ctx, None, "login-claude", api_key[0]))
    if missing:
        return _res("claude_login", "todo", t("doctor.login_missing", label=missing[0]),
                    _fix(ctx, None, "login-claude", missing[0]))
    if no_plan:
        return _res("claude_login", "warn", t("doctor.login_no_plan", label=no_plan[0]))
    return _res("claude_login", "pass", t("doctor.login_pass"))


# ---------------------------------------------------------------- 31 to 35: the running stack

def _zalo_mode(ctx) -> str:
    return ctx.env.get("THOMHOUSE_ZALO_MODE", "personal")


def _rooms_installed(ctx, c: dict) -> bool:
    binary = ctx.paths.code_root / "tools" / "openmausbot" / "node_modules" / ".bin" / "openmausbot"
    if not binary.exists():
        return False
    pins = _pins(ctx, c)
    major = pins.node_min_rooms_major if pins else 24
    have = _version_tuple(_node_version(ctx, c))
    return have is not None and have[0] >= major


def _check_processes(ctx, c: dict) -> CheckResult:
    services = _services(ctx, c)
    needed = [n for n in STACK_NAMES if n != "bridge" or _zalo_mode(ctx) == "personal"]
    down = [n for n in needed if not (n in services and services[n].alive)]
    if down:
        return _res("processes", "fail", t("doctor.processes_down", names=", ".join(down)), _fix(ctx, None, "start"))
    rooms = services.get("openmausbot")
    if (rooms is None or not rooms.alive) and _rooms_installed(ctx, c):
        return _res("processes", "warn", t("doctor.processes_rooms_down"), _fix(ctx, None, "restart"))
    return _res("processes", "pass", t("doctor.running"))


def _check_server_health(ctx, c: dict) -> CheckResult:
    fix = _fix(ctx, "doctor.server_down_fix", "restart",
               log=_tilde(ctx.paths.bot_logs / "server.log", ctx.paths.home))
    code, body = stack.http_json(ctx, "GET", "/health")
    want = _zalo_mode(ctx)
    if code == 200 and isinstance(body, dict):
        if body.get("zalo_mode") == want:
            return _res("server_health", "pass", t("doctor.running"))
        return _res("server_health", "fail", t("doctor.server_mode", mode=str(body.get("zalo_mode")), want=want), fix)
    return _res("server_health", "fail", t("doctor.server_down"), fix)


def _staff_get(ctx, check_id: str, path: str) -> tuple[CheckResult | None, object | None]:
    """GET a /staff path with STAFF_TOKEN; (failure result, None) when that is not possible."""
    token = _staff_token(ctx)
    if not token:
        return _res(check_id, "fail", t("doctor.staff_token_missing", file=_rel(ctx, ctx.paths.env_file("server"))),
                    _fix(ctx, None, "install", "--only", "config")), None
    code, body = stack.http_json(ctx, "GET", path, token=token)
    if code != 200 or body is None:
        return _res(check_id, "fail", t("doctor.staff_api_down", path=path), _fix(ctx, None, "restart")), None
    return None, body


def _check_runner_online(ctx, c: dict) -> CheckResult:
    failed, body = _staff_get(ctx, "runner_online", "/staff/runner")
    if failed is not None:
        return failed
    runner_id = envs.value(ctx.paths, "runner", "RUNNER_ID") or DEFAULT_RUNNER_ID
    rows = body.get("runners") if isinstance(body, dict) else None
    row = next((r for r in rows if isinstance(r, dict) and r.get("runner_id") == runner_id), None) \
        if isinstance(rows, list) else None
    if row is not None and row.get("online") is True:
        return _res("runner_online", "pass", t("doctor.runner_pass"))
    fix = _fix(ctx, "doctor.runner_down_fix", "restart",
               log=_tilde(ctx.paths.bot_logs / "runner.log", ctx.paths.home))
    return _res("runner_online", "fail", t("doctor.runner_down"), fix)


def _expected_catalog(code_root: Path) -> str | None:
    """`cv_local_` + the first 12 hex of the SHA-256 of the four catalog files concatenated (start_local.sh)."""
    h = hashlib.sha256()
    for rel in CATALOG_FILES:
        try:
            h.update((code_root / rel).read_bytes())
        except OSError:
            return None
    return "cv_local_" + h.hexdigest()[:12]


def _check_catalog(ctx, c: dict) -> CheckResult:
    active = migrations.active_catalog(ctx.paths.bot_home)
    expected = _expected_catalog(ctx.paths.code_root)
    if active is None or expected is None:
        return _res("catalog", "warn", t("doctor.catalog_unknown"))
    if active == expected:
        return _res("catalog", "pass", active)
    return _res("catalog", "fail", t("doctor.catalog_old"), _fix(ctx, None, "restart"))


def _check_console(ctx, c: dict) -> CheckResult:
    url = (ctx.env.get("THOMHOUSE_CONSOLE_URL") or stack.DEFAULT_CONSOLE_URL).rstrip("/") + "/"
    try:
        code, _ = stack.http_json(ctx, "GET", url)
    except ValueError:
        code = 0
    if code != 0:
        return _res("console", "pass", t("doctor.console_pass"))
    return _res("console", "fail", t("doctor.console_down"), _fix(ctx, None, "start"))


# ---------------------------------------------------------------- 36 to 40: Zalo and the bridge

def _bridge_missing(ctx, check_id: str, status: str, key: str, fix: str) -> CheckResult:
    """Result when the bridge doctor gave nothing: `key` when the bridge has no env file yet, else unreadable."""
    if not ctx.paths.env_file("bridge").exists():
        return _res(check_id, status, t(key), fix)
    return _res(check_id, "fail", t("doctor.bridge_unreadable"), _fix(ctx, None, "restart"))


def _check_zalo_login(ctx, c: dict) -> CheckResult:
    fix = _fix(ctx, None, "login-zalo")
    bridge = _bridge(ctx, c)
    if bridge is None:
        return _bridge_missing(ctx, "zalo_login", "todo", "doctor.zalo_login_missing", fix)
    if bridge.get("zalo_login") == "ok":
        return _res("zalo_login", "pass", t("doctor.zalo_login_pass"))
    return _res("zalo_login", "todo", t("doctor.zalo_login_missing"), fix)


def _check_listener(ctx, c: dict) -> CheckResult:
    login_fix = _fix(ctx, None, "login-zalo")
    bridge = _bridge(ctx, c)
    if bridge is None:
        return _bridge_missing(ctx, "listener", "todo", "doctor.listener_no_login", login_fix)
    status = bridge.get("listener")
    if status == "ok":
        return _res("listener", "pass", t("doctor.listener_pass"))
    if _dep(ctx, c, "zalo_login").status == "todo":
        return _res("listener", "todo", t("doctor.listener_no_login"), login_fix)
    if status == "warn":
        return _res("listener", "warn", t("doctor.listener_warn"), _fix(ctx, None, "restart"))
    return _res("listener", "fail", t("doctor.listener_down"), _fix(ctx, None, "restart"))


def _check_bridge_token(ctx, c: dict) -> CheckResult:
    bridge = _bridge(ctx, c)
    if bridge is None:
        return _bridge_missing(ctx, "bridge_token", "fail", "doctor.bridge_token_bad",
                               _fix(ctx, None, "install", "--only", "config"))
    status = bridge.get("bridge_token")
    if status == "ok":
        return _res("bridge_token", "pass", t("doctor.bridge_token_pass"))
    if status == "warn":  # the token is accepted; some sends have an unknown outcome (bridge doctor)
        return _res("bridge_token", "warn", t("doctor.bridge_token_unknown"))
    return _res("bridge_token", "fail", t("doctor.bridge_token_bad"), _fix(ctx, None, "restart"))


def _check_room_platform(ctx, c: dict) -> CheckResult:
    bridge = _bridge(ctx, c)
    if bridge is not None and bridge.get("room_platform") == "ok":
        return _res("room_platform", "pass", t("doctor.room_platform_pass"))
    return _res("room_platform", "warn", t("doctor.room_platform_bad"))


def _check_menu_images(ctx, c: dict) -> CheckResult:
    script = ctx.paths.code_root / "scripts" / "build_menu_images.py"
    res = proc.run(ctx, [sys.executable, "-I", str(script), "--home", str(ctx.paths.bot_home), "--check"],
                   cwd=ctx.paths.code_root, timeout=300)
    if res.returncode == 0:
        return _res("menu_images", "pass", t("doctor.enough"))
    return _res("menu_images", "warn", t("doctor.menu_images_bad"), _fix(ctx, None, "restart"))


# ---------------------------------------------------------------- 41 to 43: safety and reply mode

def _listener_pid(ctx) -> int | None:
    if not ctx.paths.env_file("bridge").exists():
        return None
    _, data = bridgecli.listener(ctx, "status")
    pid = data.get("pid") if isinstance(data, dict) else None
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and data.get("running") is not False:
        return pid
    return None


def _check_listen_local_only(ctx, c: dict) -> CheckResult:
    groups: dict[int, str] = {}
    for svc in _services(ctx, c).values():
        if svc.alive and svc.pid:
            groups.setdefault(svc.pid, svc.name)
    daemon = _listener_pid(ctx)
    if daemon is not None:
        groups.setdefault(daemon, "listener")
    owners: dict[int, str] = {}
    for pgid, name in groups.items():
        owners.setdefault(pgid, name)
        for pid in safety.group_pids([pgid]):
            owners.setdefault(pid, name)
    for pid, address, port in safety.listen_sockets(sorted(owners)):
        if address not in LOOPBACK_ADDRESSES:
            return _res("listen_local_only", "fail",
                        t("doctor.listen_open", name=owners.get(pid, str(pid)), port=port),
                        _fix(ctx, "doctor.stop_now_fix", "stop"))
    return _res("listen_local_only", "pass", t("doctor.correct"))


def _check_openmausbot_options(ctx, c: dict) -> CheckResult:
    rooms = _services(ctx, c).get("openmausbot")
    if rooms is None or not rooms.alive or not rooms.pid:
        return _res("openmausbot_options", "pass", t("doctor.openmausbot_not_running"))
    bad = safety.forbidden_platform_args(safety.process_argv(rooms.pid))
    if bad:
        return _res("openmausbot_options", "fail", t("doctor.openmausbot_bad", options=", ".join(bad)),
                    _fix(ctx, "doctor.stop_now_fix", "stop"))
    return _res("openmausbot_options", "pass", t("doctor.correct"))


def _check_reply_flags(ctx, c: dict) -> CheckResult:
    failed, body = _staff_get(ctx, "reply_flags", "/staff/flags")
    if failed is not None:
        return failed
    flags = body.get("flags") if isinstance(body, dict) and isinstance(body.get("flags"), dict) else body
    if not isinstance(flags, dict):
        return _res("reply_flags", "fail", t("doctor.staff_api_down", path="/staff/flags"), _fix(ctx, None, "restart"))
    engine = flags.get("ai_engine")
    if engine != "subscription":
        return _res("reply_flags", "fail", t("doctor.flags_engine", value=str(engine)), t("doctor.flags_engine_fix"))
    mode = flags.get("auto_reply_mode")
    if mode == "auto_allowed":
        return _res("reply_flags", "warn", t("doctor.flags_auto"), t("doctor.flags_auto_fix"))
    if flags.get("outbound_enabled") is False:
        return _res("reply_flags", "warn", t("doctor.flags_outbound_off"), t("doctor.flags_outbound_fix"))
    detail = t("doctor.flags_approve_each") if mode == "approve_each" else str(mode)
    return _res("reply_flags", "pass", detail)


# ---------------------------------------------------------------- 44 to 48: steps only the journal knows

def _step(ctx, c: dict, step_id: str) -> dict:
    entry = _journal(ctx, c).get(step_id)
    return entry if isinstance(entry, dict) else {}


def _check_history_sync(ctx, c: dict) -> CheckResult:
    if _step(ctx, c, "history_sync").get("status") == "done":
        return _res("history_sync", "pass", t("doctor.history_pass"))
    return _res("history_sync", "todo", t("doctor.history_missing"), _fix(ctx, None, "sync-history"))


def _analyzed(ctx, c: dict, check_id: str, step_id: str, missing_key: str, flag: str) -> CheckResult:
    entry = _step(ctx, c, step_id)
    if entry.get("status") == "done":
        return _res(check_id, "pass", t("doctor.analyzed_on", date=_date(entry.get("at")) or "?"))
    if entry.get("status") == "skipped" and entry.get("reason") == "no_cache":
        return _res(check_id, "skip", t("doctor.no_zalo_cache"))
    if step_id == "analyze_visits" and entry.get("reason") == "server_404":
        return _res(check_id, "todo", t("doctor.visits_server_404"), _fix(ctx, None, "continue"))
    return _res(check_id, "todo", t(missing_key), _fix(ctx, None, "analyze", flag))


def _check_contacts_analyzed(ctx, c: dict) -> CheckResult:
    return _analyzed(ctx, c, "contacts_analyzed", "analyze_contacts", "doctor.contacts_missing", "--contacts")


def _check_visits_analyzed(ctx, c: dict) -> CheckResult:
    return _analyzed(ctx, c, "visits_analyzed", "analyze_visits", "doctor.visits_missing", "--visits")


def _check_labels(ctx, c: dict) -> CheckResult:
    failed, body = _staff_get(ctx, "labels", "/staff/roles")
    if failed is not None:
        return failed
    roles = body.get("roles") if isinstance(body, dict) else body
    count = len(roles) if isinstance(roles, list) else 0
    if count:
        return _res("labels", "pass", t("doctor.labels_pass", n=count))
    return _res("labels", "todo", t("doctor.labels_missing"), _fix(ctx, "doctor.labels_fix", "labels"))


def _check_staff_token_step(ctx, c: dict) -> CheckResult:
    if _step(ctx, c, "staff_token").get("status") == "done":
        return _res("staff_token_step", "pass", t("doctor.staff_token_pass"))
    return _res("staff_token_step", "todo", t("doctor.staff_token_missing_step"), _fix(ctx, None, "staff-token"))


# ---------------------------------------------------------------- the table of 16.7

CHECKS: list[CheckDef] = [
    CheckDef(1, "macos", "machine", False, False, _check_macos),
    CheckDef(2, "cpu", "machine", False, False, _check_cpu),
    CheckDef(3, "disk", "machine", False, False, _check_disk),
    CheckDef(4, "system_tools", "machine", False, False, _check_system_tools),
    CheckDef(5, "python", "machine", False, False, _check_python),
    CheckDef(6, "install_lock", "machine", False, False, _check_install_lock),
    CheckDef(7, "moved_out", "machine", False, False, _check_moved_out),
    CheckDef(8, "other_stack", "machine", False, False, _check_other_stack),
    CheckDef(9, "release", "program", False, False, _check_release),
    CheckDef(10, "release_files", "program", False, False, _check_release_files),
    CheckDef(11, "release_clean", "program", False, False, _check_release_clean),
    CheckDef(12, "node", "program", False, False, _check_node),
    CheckDef(13, "pnpm", "program", False, False, _check_pnpm),
    CheckDef(14, "claude_cli", "program", False, False, _check_claude_cli),
    CheckDef(15, "pins", "program", False, False, _check_pins),
    CheckDef(16, "deps_workspace", "program", False, False, _check_deps_workspace),
    CheckDef(17, "deps_engine", "program", False, False, _check_deps_engine),
    CheckDef(18, "deps_rooms", "program", False, False, _check_deps_rooms),
    CheckDef(19, "menu_slides", "program", False, False, _check_menu_slides),
    CheckDef(20, "env_files", "config", False, False, _check_env_files),
    CheckDef(21, "tokens_agree", "config", False, False, _check_tokens_agree),
    CheckDef(22, "paths_current", "config", False, False, _check_paths_current),
    CheckDef(23, "permissions", "config", False, False, _check_permissions),
    CheckDef(24, "no_api_key", "config", False, False, _check_no_api_key),
    CheckDef(25, "profile_llm_off", "config", False, False, _check_profile_llm_off),
    CheckDef(26, "database", "data", False, False, _check_database),
    CheckDef(27, "migrations", "data", False, False, _check_migrations),
    CheckDef(28, "last_backup", "data", False, False, _check_last_backup),
    CheckDef(29, "claude_pool", "claude", False, False, _check_claude_pool),
    CheckDef(30, "claude_login", "claude", True, False, _check_claude_login),
    CheckDef(31, "processes", "stack", False, True, _check_processes),
    CheckDef(32, "server_health", "stack", False, True, _check_server_health),
    CheckDef(33, "runner_online", "stack", False, True, _check_runner_online),
    CheckDef(34, "catalog", "stack", False, True, _check_catalog),
    CheckDef(35, "console", "stack", False, True, _check_console),
    CheckDef(36, "zalo_login", "zalo", True, False, _check_zalo_login),
    CheckDef(37, "listener", "zalo", True, True, _check_listener),
    CheckDef(38, "bridge_token", "zalo", False, True, _check_bridge_token),
    CheckDef(39, "room_platform", "zalo", True, True, _check_room_platform),
    CheckDef(40, "menu_images", "zalo", False, False, _check_menu_images),
    CheckDef(41, "listen_local_only", "safety", False, True, _check_listen_local_only),
    CheckDef(42, "openmausbot_options", "safety", False, True, _check_openmausbot_options),
    CheckDef(43, "reply_flags", "safety", False, True, _check_reply_flags),
    CheckDef(44, "history_sync", "steps", False, False, _check_history_sync),
    CheckDef(45, "contacts_analyzed", "steps", False, False, _check_contacts_analyzed),
    CheckDef(46, "visits_analyzed", "steps", False, False, _check_visits_analyzed),
    CheckDef(47, "labels", "steps", False, True, _check_labels),
    CheckDef(48, "staff_token_step", "steps", False, False, _check_staff_token_step),
]
BY_ID: dict[str, CheckDef] = {d.id: d for d in CHECKS}
BY_N: dict[str, CheckDef] = {str(d.n): d for d in CHECKS}


# ---------------------------------------------------------------- running the checks

def _gate(ctx, d: CheckDef, c: dict) -> CheckResult | None:
    """The result the rules of 16.7 give before the check itself runs, or None to run it."""
    paths = ctx.paths
    if paths.mode != "installed":
        if d.id in CHECKOUT_SKIP:
            return _res(d.id, "skip", t("doctor.skip_checkout"))
    elif c["full"] and d.n >= 10 and _installed(ctx, c) is None:
        return _res(d.id, "todo", t("doctor.before_install"), t("doctor.before_install_fix", version=_version(ctx)))
    if ctx.offline and (d.net or d.id in BRIDGE_CHECKS):
        return _res(d.id, "skip", t("doctor.skip_offline"))
    if d.run and d.id != "processes" and _stopped(ctx, c):
        return _res(d.id, "skip", t("doctor.skip_stopped"))
    return None


def _evaluate(ctx, d: CheckDef, c: dict) -> CheckResult:
    done = c["results"].get(d.id)
    if done is not None:
        return done
    try:
        result = _gate(ctx, d, c) or d.fn(ctx, c)
    except Exception as exc:  # noqa: BLE001 - one broken check must not hide the other lines
        ctx.log("doctor_check_crashed", check=d.id, type=type(exc).__name__,
                traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        result = CheckResult(d.n, d.id, d.group, "fail", t(f"doctor.label_{d.id}"),
                             t("doctor.crashed", name=type(exc).__name__), t("doctor.crashed_fix"), crashed=True)
    c["results"][d.id] = result
    return result


def run_checks(ctx, *, only: set[str] | None = None) -> list[CheckResult]:
    """The results of the checks of CHECKS in order (only those named in `only`, by id, when given).

    The bridge doctor, the pool and the login statuses are read at most once per call. ValueError for an id in
    `only` that is not a check.
    """
    if only is not None:
        unknown = sorted(set(only) - set(BY_ID))
        if unknown:
            raise ValueError(f"unknown doctor checks: {', '.join(unknown)}")
    c: dict = {"results": {}, "full": only is None}
    return [_evaluate(ctx, d, c) for d in CHECKS if only is None or d.id in only]


def passes(ctx, ids: set[str]) -> bool:
    """True when none of the checks `ids` is "fail" or "todo" (the check() of an install step); "warn" and "skip"
    pass (16.3.3, rev check)."""
    return all(r.status not in ("fail", "todo") for r in run_checks(ctx, only=set(ids)))


def exit_code(results: list[CheckResult], strict: bool) -> int:
    """2 when a check crashed; 1 when a check is "fail" (with `strict` also "warn" or "todo"); else 0."""
    if any(r.crashed for r in results):
        return EXIT_USAGE
    if any(r.status == "fail" for r in results):
        return EXIT_FAILED
    if strict and any(r.status in ("warn", "todo") for r in results):
        return EXIT_FAILED
    return EXIT_OK


def line(result: CheckResult) -> str:
    """`<status> <label>: <detail>`, plus the fix word (`doctor.fix_word`) and the fix when the status is not pass
    and a fix exists."""
    text = f"{t(STATUS_KEYS[result.status])} {result.label}: {result.detail}"
    if result.status != "pass" and result.fix:
        word = t("doctor.fix_word")
        text += f" {word} {result.fix}"
    return text


def _wanted(only: object) -> tuple[set[str] | None, str | None]:
    """(check ids, None) from `--only` (ids or numbers), or (None, the first unknown name)."""
    if not only:
        return None, None
    ids: set[str] = set()
    for item in sorted(str(x) for x in only):
        d = BY_ID.get(item) or BY_N.get(item)
        if d is None:
            return None, item
        ids.add(d.id)
    return ids, None


def cmd_doctor(ctx, args) -> int:
    """`thomhouse doctor [--json] [--offline] [--strict] [--only CHECK[,CHECK...]]`: 0, 1 or 2 (16.7)."""
    ids, unknown = _wanted(getattr(args, "only", None))
    if unknown is not None:
        print(t("doctor.unknown_check", name=unknown), flush=True)
        return EXIT_USAGE
    results = run_checks(ctx, only=ids)
    code = exit_code(results, bool(getattr(args, "strict", False)))
    if getattr(args, "json", False):
        doc = {"schema": 1, "checks": [r.as_dict() for r in results], "exit": code}
        print(json.dumps(doc, ensure_ascii=False, indent=1), flush=True)
    else:
        for result in results:
            print(line(result), flush=True)
    counts = {s: sum(1 for r in results if r.status == s) for s in STATUSES}
    ctx.log("doctor", exit=code, offline=ctx.offline, counts=counts)
    return code
