"""Shared implementation of the fake binaries in this folder (16.10). Test support only.

Every fake records one JSON line in `<tmp>/calls.jsonl`: the tool, argv, the working folder, the names (never the
values) of its environment variables, the values of DISABLE_UPDATES, DISABLE_AUTOUPDATER, no_proxy, NO_PROXY,
npm_config_cache and CLAUDE_CONFIG_DIR, and the first PATH entry. Behaviour comes from `<tmp>/behaviour.json`, one
object per tool. `<tmp>` is THOMHOUSE_TEST_DIR, or the parent of HOME when it holds `.installer-test`; without
one a fake refuses to run (exit 99), so a fake can never act on a real home folder.

Written for any Python 3.9 or newer, because `/usr/bin/env python3` may find an older Python in a test that runs
with a minimal PATH.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from urllib.parse import urlsplit

FAKE_BIN = os.path.dirname(os.path.realpath(__file__))
RECORDED_ENV = ("DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "no_proxy", "NO_PROXY", "npm_config_cache",
                "CLAUDE_CONFIG_DIR")
SHIMS = {"@ardennguyen/zalo-agent-cli": ("zalo-agent", "zalo-agent"), "openmausbot": ("openmausbot", "openmausbot"),
         "pnpm": ("pnpm", "pnpm")}


# ---------------------------------------------------------------- common

def test_dir():
    d = os.environ.get("THOMHOUSE_TEST_DIR")
    if d and os.path.isdir(d):
        return d
    home = os.environ.get("HOME")
    if home:
        parent = os.path.dirname(os.path.abspath(home))
        if os.path.exists(os.path.join(parent, ".installer-test")):
            return parent
    return None


def behaviour(tool):
    d = test_dir()
    try:
        with open(os.path.join(d, "behaviour.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    value = data.get(tool, {}) if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def record(tool, argv, **extra):
    d = test_dir()
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    entry = {
        "tool": tool,
        "argv": list(argv),
        "cwd": os.getcwd(),
        "env_names": sorted(os.environ),
        "env": {k: os.environ.get(k) for k in RECORDED_ENV},
        "path0": path_entries[0] if path_entries else "",
        "pid": os.getpid(),
        "at": time.time(),
    }
    entry.update(extra)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(os.path.join(d, "calls.jsonl"), "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(line)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def opt(argv, name, default=None):
    """The value after option `name` (or `name=value`)."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def write_exec(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def shim(path, tool, env_prefix=""):
    write_exec(path, '#!/bin/sh\n%sexec "%s/%s" "$@"\n' % (env_prefix, FAKE_BIN, tool))


def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()


# ---------------------------------------------------------------- tools

def curl(argv):
    record("curl", argv)
    b = behaviour("curl")
    url = next((a for a in reversed(argv) if "://" in a), "")
    output = opt(argv, "-o")
    if not url.startswith("https://"):
        sys.stderr.write("curl: (22) refused: not https\n")
        return 22
    fail = b.get("fail", {})
    if url in fail:
        sys.stderr.write("curl: (%s) failed on demand\n" % fail[url])
        return int(fail[url])
    if "exit" in b:
        return int(b["exit"])
    fixtures = b.get("fixtures") or os.path.join(test_dir(), "fixtures")
    name = b.get("map", {}).get(url) or os.path.basename(urlsplit(url).path)
    src = os.path.join(fixtures, name)
    if not name or not os.path.isfile(src):
        sys.stderr.write("curl: (22) The requested URL returned error: 404\n")
        return 22
    with open(src, "rb") as f:
        data = f.read()
    if url in b.get("truncate", []):
        data = data[: len(data) // 2]
    if url in b.get("corrupt", []) and data:
        data = data[:-1] + bytes([data[-1] ^ 0xFF])
    if output:
        start = 0
        if opt(argv, "-C") == "-" and os.path.exists(output):
            start = os.path.getsize(output)
        with open(output, "ab" if start else "wb") as f:
            f.write(data[start:])
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    return 0


def _system():
    b = behaviour("system")
    return {
        "os": b.get("os", "Darwin"),
        "macos": b.get("macos", "15.1"),
        "cpu": b.get("cpu", "arm64"),
        "uid": int(b.get("uid", os.getuid())),
        "user": b.get("user", "tester"),
    }


def sw_vers(argv):
    record("sw_vers", argv)
    s = _system()
    if "-productVersion" in argv:
        out(s["macos"] + "\n")
    elif "-buildVersion" in argv:
        out("24B83\n")
    else:
        out("ProductName:\t\tmacOS\nProductVersion:\t\t%s\nBuildVersion:\t\t24B83\n" % s["macos"])
    return 0


def sysctl(argv):
    record("sysctl", argv)
    s = _system()
    if "hw.optional.arm64" in argv:
        if s["cpu"] == "arm64":
            out("1\n")
            return 0
        sys.stderr.write("sysctl: unknown oid 'hw.optional.arm64'\n")
        return 1
    out("0\n")
    return 0


def uname(argv):
    record("uname", argv)
    s = _system()
    machine = "arm64" if s["cpu"] == "arm64" else ("x86_64" if s["cpu"] == "x64" else s["cpu"])
    if "-m" in argv:
        out(machine + "\n")
    elif "-r" in argv:
        out("24.1.0\n")
    elif "-a" in argv:
        out("%s fake 24.1.0 %s\n" % (s["os"], machine))
    else:
        out(s["os"] + "\n")
    return 0


def id_(argv):
    record("id", argv)
    s = _system()
    if "-u" in argv and "-n" not in argv and "-un" not in argv:
        out("%d\n" % s["uid"])
    elif "-un" in argv or "-nu" in argv or ("-u" in argv and "-n" in argv):
        out(s["user"] + "\n")
    elif "-g" in argv:
        out("%d\n" % os.getgid())
    else:
        out("uid=%d(%s)\n" % (s["uid"], s["user"]))
    return 0


def node(argv):
    record("node", argv)
    b = behaviour("node")
    if argv and argv[0] in ("--version", "-v"):
        out(os.environ.get("THOMHOUSE_FAKE_NODE_VERSION") or b.get("version", "v24.19.0"))
        out("\n")
        return 0
    if argv and argv[0] in ("-e", "-p"):
        return int(b.get("e_exit", 0))
    return int(b.get("exit", 0))


def _lock_versions(prefix):
    try:
        with open(os.path.join(prefix, "package-lock.json"), encoding="utf-8") as f:
            lock = json.load(f)
    except (OSError, ValueError):
        return {}
    found = {}
    for key, entry in (lock.get("packages") or {}).items():
        if key.startswith("node_modules/") and isinstance(entry, dict) and "version" in entry:
            name = key[len("node_modules/"):]
            if "/node_modules/" not in name:
                found[name] = entry["version"]
    return found


def _install_packages(prefix, packages):
    for name, version in packages.items():
        pkg_dir = os.path.join(prefix, "node_modules", name)
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": name, "version": version}, f)
        if name in SHIMS:
            bin_name, tool = SHIMS[name]
            shim(os.path.join(prefix, "node_modules", ".bin", bin_name), tool)


def npm(argv):
    b = behaviour("npm")
    prefix = os.path.abspath(opt(argv, "--prefix", os.getcwd()))
    cache = opt(argv, "--cache", os.environ.get("npm_config_cache"))
    record("npm", argv, prefix=prefix, cache=cache)
    if argv and argv[0] in ("--version", "-v"):
        out("11.0.0\n")
        return 0
    if not argv:
        return 1
    fail = b.get("fail", [])
    base = os.path.basename(prefix.rstrip("/"))
    if fail is True or "all" in fail or base in fail or argv[0] in fail:
        sys.stderr.write("npm ERR! failed on demand\n")
        return 1
    if argv[0] == "ci":
        packages = _lock_versions(prefix)
        if not packages:
            sys.stderr.write("npm ERR! no package-lock.json\n")
            return 1
        _install_packages(prefix, packages)
        return 0
    if argv[0] == "install":
        if "--package-lock-only" in argv:
            with open(os.path.join(prefix, "package.json"), encoding="utf-8") as f:
                deps = json.load(f).get("dependencies", {})
            lock = {"name": "fake", "lockfileVersion": 3, "requires": True,
                    "packages": {"": {"dependencies": deps}}}
            for name, version in deps.items():
                short = name.rsplit("/", 1)[-1]
                lock["packages"]["node_modules/" + name] = {
                    "version": version,
                    "resolved": "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (name, short, version),
                    "integrity": "sha512-" + hashlib.sha512((name + version).encode()).hexdigest()[:40],
                }
            with open(os.path.join(prefix, "package-lock.json"), "w", encoding="utf-8") as f:
                json.dump(lock, f, indent=1)
            return 0
        specs = [a for a in argv[1:] if not a.startswith("-") and a != opt(argv, "--prefix")]
        packages = {}
        for spec in specs:
            at = spec.rfind("@")
            if at > 0:
                packages[spec[:at]] = spec[at + 1:] or "0.0.0"
            else:
                packages[spec] = "0.0.0"
        if not packages:
            packages = _lock_versions(prefix)
        _install_packages(prefix, packages)
        return 0
    return 0


def pnpm(argv):
    store = None
    try:
        with open(os.path.join(os.getcwd(), ".npmrc"), encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("store-dir="):
                    store = line.strip().split("=", 1)[1]
    except OSError:
        pass
    record("pnpm", argv, store_dir=store)
    b = behaviour("pnpm")
    if argv and argv[0] in ("--version", "-v"):
        out(b.get("version", "10.32.1") + "\n")
        return 0
    if argv and argv[0] == "install":
        if b.get("fail"):
            sys.stderr.write("ERR_PNPM failed on demand\n")
            return 1
        root = os.getcwd()
        shim(os.path.join(root, "apps", "server", "node_modules", ".bin", "wrangler"), "wrangler")
        shim(os.path.join(root, "apps", "console", "node_modules", ".bin", "vite"), "vite")
        os.makedirs(os.path.join(root, "node_modules"), exist_ok=True)
        return 0
    return 0


def _db_name(seed):
    return hashlib.sha256(seed.encode()).hexdigest() + ".sqlite"


def wrangler(argv):
    record("wrangler", argv)
    b = behaviour("wrangler")
    if argv and argv[0] == "--version":
        out("4.0.0\n")
        return 0
    if argv[:3] != ["d1", "migrations", "apply"]:
        return int(b.get("exit", 0))
    persist = opt(argv, "--persist-to")
    if not persist:
        sys.stderr.write("fake wrangler: --persist-to required\n")
        return 1
    folder = os.path.join(persist, "v3", "d1", "miniflare-D1DatabaseObject")
    os.makedirs(folder, exist_ok=True)
    meta = sqlite3.connect(os.path.join(folder, "metadata.sqlite"))
    meta.execute("CREATE TABLE IF NOT EXISTS _mf_metadata (key TEXT PRIMARY KEY, value TEXT)")
    meta.commit()
    meta.close()
    do_dir = os.path.join(persist, "v3", "do", "thomhouse-bot-ConversationDO")
    os.makedirs(do_dir, exist_ok=True)
    do = sqlite3.connect(os.path.join(do_dir, _db_name("conversation-do")))
    do.execute("CREATE TABLE IF NOT EXISTS _cf_KV (key TEXT PRIMARY KEY, value BLOB)")
    do.commit()
    do.close()
    con = sqlite3.connect(os.path.join(folder, _db_name(b.get("db_seed", "thomhouse-main"))))
    con.execute("CREATE TABLE IF NOT EXISTS d1_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")
    con.commit()
    done = {r[0] for r in con.execute("SELECT name FROM d1_migrations")}
    migrations_dir = os.path.join(os.getcwd(), "migrations")
    names = sorted(n for n in os.listdir(migrations_dir) if n.endswith(".sql")) if os.path.isdir(migrations_dir) else []
    fail_at = b.get("fail_at")
    code = 0
    for position, name in enumerate(names, start=1):
        if name in done:
            continue
        if fail_at is not None and (fail_at == position or fail_at == name):
            sys.stderr.write("fake wrangler: migration %s failed\n" % name)
            code = 1
            break
        with open(os.path.join(migrations_dir, name), encoding="utf-8") as f:
            sql = f.read()
        try:
            con.executescript(sql)
        except sqlite3.Error as e:
            sys.stderr.write("fake wrangler: %s: %s\n" % (name, e))
            code = 1
            break
        con.execute("INSERT INTO d1_migrations (name) VALUES (?)", (name,))
        con.commit()
        out("applied %s\n" % name)
    catalog = b.get("catalog")
    if catalog and code == 0:
        con.execute("CREATE TABLE IF NOT EXISTS catalog_versions (id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        con.execute("UPDATE catalog_versions SET status = 'archived' WHERE status = 'active'")
        con.execute("INSERT OR REPLACE INTO catalog_versions (id, status) VALUES (?, 'active')", (catalog,))
        con.commit()
    con.close()
    return code


def _auth_file():
    return os.path.join(test_dir(), "claude-auth.json")


def _auth_load():
    try:
        with open(_auth_file(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _auth_save(data):
    with open(_auth_file(), "w", encoding="utf-8") as f:
        json.dump(data, f)


def claude(argv):
    record("claude", argv)
    b = behaviour("claude")
    key = os.environ.get("CLAUDE_CONFIG_DIR") or "default"
    if argv and argv[0] in ("--version", "-v"):
        version = os.environ.get("THOMHOUSE_FAKE_CLAUDE_VERSION") or b.get("version", "2.1.319")
        out("%s (Claude Code)\n" % version)
        return 0
    if argv[:2] == ["auth", "status"]:
        st = _auth_load().get(key) or {}
        logged = bool(st.get("loggedIn"))
        method = st.get("authMethod") if logged else "none"
        doc = {"loggedIn": logged, "authMethod": method or "none", "apiProvider": "firstParty"}
        if method == "claude.ai":
            doc["email"] = "x@example.invalid"
            doc["subscriptionType"] = st.get("subscriptionType")
        out(json.dumps(doc) + "\n")
        return 0 if logged else 1
    if argv[:2] == ["auth", "login"]:
        mode = (b.get("login_by_dir") or {}).get(key, b.get("login", "max"))
        if mode == "fail":
            return 1
        data = _auth_load()
        if mode == "api_key":
            data[key] = {"loggedIn": True, "authMethod": "api_key", "subscriptionType": None}
        elif mode == "null":
            data[key] = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": None}
        else:
            data[key] = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": mode}
        _auth_save(data)
        out("Login successful.\n")
        return 0
    if argv[:2] == ["auth", "logout"]:
        data = _auth_load()
        data.pop(key, None)
        _auth_save(data)
        return 0
    if argv and argv[0] == "install":
        if os.environ.get("DISABLE_UPDATES"):
            out("Updates are disabled by your administrator. Contact your administrator to install updates.\n")
            return 0
        version = argv[1] if len(argv) > 1 else b.get("version", "2.1.319")
        home = os.environ["HOME"]
        target = os.path.join(home, ".local", "share", "claude", "versions", version)
        marker = b.get("binary_marker")
        text = "#!/bin/sh\n# fake claude %s\n" % version
        if marker:
            text += "# %s\n" % marker
        text += 'THOMHOUSE_FAKE_CLAUDE_VERSION=%s exec "%s/claude" "$@"\n' % (version, FAKE_BIN)
        write_exec(target, text)
        link = os.path.join(home, ".local", "bin", "claude")
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(target, link)
        out("Claude Code %s installed.\n" % version)
        return int(b.get("install_exit", 0))
    if "-p" in argv:
        return 2
    return int(b.get("exit", 0))


def zalo_agent(argv):
    record("zalo-agent", argv)
    b = behaviour("zalo-agent")
    args = [a for a in argv if a != "--json"]
    if args and args[0] == "--version":
        out("2.5.9\n")
        return 0
    if args and args[0] == "login":
        qr_file = os.path.join(test_dir(), "qr.png")
        with open(qr_file, "wb") as f:
            f.write(b"\x89PNG fake")
        out(json.dumps({"event": "qr", "image": "RkFLRVFS", "file": qr_file,
                        "dataUrl": "data:image/png;base64,RkFLRVFS"}) + "\n")
        time.sleep(float(b.get("delay", 0)))
        result = b.get("login", "success")
        if result == "hang":
            time.sleep(600)
            return 1
        if result == "declined":
            out(json.dumps({"event": "qr_declined"}) + "\n")
            return 1
        if result == "error":
            out(json.dumps({"event": "login_error", "message": "fake error"}) + "\n")
            return 1
        out(json.dumps({"event": "qr_scanned", "name": "Ten Gia", "avatar": "https://example.invalid/a.png"}) + "\n")
        out(json.dumps({"event": "login_success", "ownId": "999000111", "name": "Ten Gia"}) + "\n")
        return 0
    if args and args[0] == "sync":
        time.sleep(0.1)
        return int(b.get("sync_exit", 0))
    if args and args[0] == "listen":
        if "--status" in args:
            out(json.dumps({"running": bool(b.get("listening", False))}) + "\n")
        return int(b.get("listen_exit", 0))
    if args and args[0] == "status":
        return int(b.get("status_exit", 0))
    return int(b.get("exit", 0))


def _listen_rows(b, argv):
    rows = b.get("listen", [])
    pids = opt(argv, "-p")
    if pids:
        wanted = {p for p in pids.split(",") if p}
        rows = [r for r in rows if str(r[1]) in wanted]
    for a in argv:
        if a.startswith("-iTCP:"):
            port = a.split(":", 1)[1]
            rows = [r for r in rows if str(r[3]) == port]
    return rows


def lsof(argv):
    record("lsof", argv)
    b = behaviour("lsof")
    if "cwd" in argv and "-Fn" in argv:
        pid = opt(argv, "-p", "")
        cwd = (b.get("cwd") or {}).get(str(pid))
        if cwd:
            out("p%s\nfcwd\nn%s\n" % (pid, cwd))
            return 0
        real = "/usr/sbin/lsof"
        if os.path.exists(real) and not b.get("no_real_cwd"):
            os.execv(real, [real] + list(argv))
        return 1
    rows = _listen_rows(b, argv)
    if not rows:
        return 1
    if "-t" in argv:
        out("".join("%s\n" % p for p in sorted({str(r[1]) for r in rows})))
        return 0
    lines = ["COMMAND     PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME"]
    for command, pid, address, port in rows:
        family = "IPv6" if ":" in str(address).strip("[]") else "IPv4"
        addr = address if family == "IPv4" or str(address).startswith("[") or address == "*" else "[%s]" % address
        lines.append("%-10s %5s tester   20u  %s 0x0      0t0  TCP %s:%s (LISTEN)" % (command, pid, family, addr, port))
    out("\n".join(lines) + "\n")
    return 0


def open_(argv):
    record("open", argv)
    return int(behaviour("open").get("exit", 0))


def pbcopy(argv):
    data = sys.stdin.buffer.read()
    record("pbcopy", argv, bytes=len(data))
    path = os.path.join(test_dir(), "clipboard")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return 0


def pbpaste(argv):
    record("pbpaste", argv)
    try:
        with open(os.path.join(test_dir(), "clipboard"), "rb") as f:
            sys.stdout.buffer.write(f.read())
    except OSError:
        pass
    return 0


def launchctl(argv):
    record("launchctl", argv)
    b = behaviour("launchctl")
    if argv and argv[0] in b.get("fail", []):
        return int(b.get("exit", 5))
    return 0


def hdiutil(argv):
    """The image is a real file (a tar of -srcfolder), so a move image can be hashed and given mode 0600 like a
    .dmg; `attach -mountpoint M FILE` unpacks it into M and `detach M` removes M. Never touches a real disk image."""
    import tarfile

    record("hdiutil", argv)
    b = behaviour("hdiutil")
    if argv and argv[0] in b.get("fail", []):
        sys.stderr.write("hdiutil: %s failed on demand\n" % argv[0])
        return 1
    if argv and argv[0] == "create":
        src = opt(argv, "-srcfolder")
        target = argv[-1]
        if os.path.exists(target):
            sys.stderr.write("hdiutil: create failed - File exists\n")
            return 1
        with tarfile.open(target, "w") as tar:
            for name in sorted(os.listdir(src)):
                tar.add(os.path.join(src, name), arcname=name)
        out("created: %s\n" % target)
        return 0
    if argv and argv[0] == "attach":
        mount = opt(argv, "-mountpoint")
        image = argv[-1]
        os.makedirs(mount, exist_ok=True)
        with tarfile.open(image) as tar:
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name.split("/"):
                    return 1
            try:
                tar.extractall(mount, filter="data")
            except TypeError:  # Python without extraction filters
                tar.extractall(mount)
        out("/dev/disk9\t\t%s\n" % mount)
        return 0
    if argv and argv[0] == "detach":
        target = argv[-1]
        if os.path.isdir(target):
            shutil.rmtree(target)
        return 0
    return 0


def sips(argv):
    record("sips", argv)
    target = opt(argv, "--out")
    src = next((a for a in argv if os.path.isfile(a)), None)
    if target and src:
        shutil.copyfile(src, target)
    return int(behaviour("sips").get("exit", 0))


def vite(argv):
    record("vite", argv)
    return int(behaviour("vite").get("exit", 0))


def openmausbot(argv):
    record("openmausbot", argv)
    if argv and argv[0] == "serve":
        time.sleep(300)
    return int(behaviour("openmausbot").get("exit", 0))


TOOLS = {
    "curl": curl, "sw_vers": sw_vers, "sysctl": sysctl, "uname": uname, "id": id_, "node": node, "npm": npm,
    "pnpm": pnpm, "wrangler": wrangler, "claude": claude, "zalo-agent": zalo_agent, "lsof": lsof, "open": open_,
    "pbcopy": pbcopy, "pbpaste": pbpaste, "launchctl": launchctl, "hdiutil": hdiutil, "sips": sips, "vite": vite,
    "openmausbot": openmausbot,
}


def main(tool):
    if test_dir() is None:
        sys.stderr.write("fake %s: no test folder (THOMHOUSE_TEST_DIR); refusing to run\n" % tool)
        return 99
    try:
        return TOOLS[tool](sys.argv[1:])
    except BrokenPipeError:
        return 0
