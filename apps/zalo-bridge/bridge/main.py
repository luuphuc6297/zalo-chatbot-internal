"""Entry point (run from apps/zalo-bridge):

  python3 -m bridge.main run                      poll forever: claim -> zalo-agent msg send -> result
  python3 -m bridge.main once                     claim and process at most one outbox row, print a JSON summary
  python3 -m bridge.main status                   GET /bridge/status (what the console shows)
  python3 -m bridge.main doctor [--json]          check engine, Zalo login, listener, server, token, and report
                                                  the optional room platform
  python3 -m bridge.main listener start|status|stop [--only-ours] [--no-login-check]
  python3 -m bridge.main init-env [--mode personal|mock] [--engine-bin PATH]   used by scripts/start_local.sh
  python3 -m bridge.main sync-labels [--dry-run]  copy the Zalo labels Khách hàng / Quản lý / Nhân viên to the
                                                  server's contact roles (labels.py); prints counts only
  python3 -m bridge.main rooms-node               print the directory of the node (24 or newer) that runs the
                                                  optional room platform; exit 1 and print nothing when this
                                                  machine has none (used by scripts/start_local.sh)

Exit codes of `listener start`: 0 started or already running, 2 config (engine missing, no secret),
3 Zalo account not logged in, 4 another daemon holds the account's WebSocket, 1 other error.
`run` and `once` exit 5 when another bridge process holds the state directory (flock on <state_dir>/bridge.lock).
Exit codes of `sync-labels`: 0 synced (or dry run read the labels), 1 the engine failed, its output was not the
expected document, or the server refused the import (nothing is posted after an engine failure), 2 no staff token.
Output never contains message text, tokens, secrets or full Zalo ids.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import listener
from .api import ApiError, ServerUnavailable
from .config import REPO_ROOT, Config, ConfigError


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bridge")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("once")
    sub.add_parser("status")
    d = sub.add_parser("doctor")
    d.add_argument("--json", action="store_true")
    li = sub.add_parser("listener")
    li.add_argument("action", choices=["start", "status", "stop"])
    li.add_argument("--only-ours", action="store_true", help="stop: leave a daemon the bridge did not start")
    li.add_argument("--no-login-check", action="store_true", help="start: skip `zalo-agent status`")
    ie = sub.add_parser("init-env")
    ie.add_argument("--mode", choices=["personal", "mock"], default="personal")
    ie.add_argument("--engine-bin", default=None)
    ie.add_argument("--repo-root", default=str(REPO_ROOT))
    sl = sub.add_parser("sync-labels")
    sl.add_argument("--dry-run", action="store_true", help="read and count the labels, post nothing")
    rn = sub.add_parser("rooms-node")
    rn.add_argument("--repo-root", default=str(REPO_ROOT))
    ns = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if ns.verbose else logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if ns.cmd == "init-env":
        from .envfiles import init_env
        _print(init_env(ns.repo_root, mode=ns.mode, engine_bin=ns.engine_bin))
        return 0

    if ns.cmd == "rooms-node":
        from .rooms import platform_node_dir
        node_dir = platform_node_dir(ns.repo_root)
        if not node_dir:
            return 1
        print(node_dir)
        return 0

    try:
        cfg = Config.load(require_token=ns.cmd not in ("listener", "sync-labels"))
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    if ns.cmd == "listener":
        if ns.action == "start":
            code, out = listener.start(cfg, check_login=not ns.no_login_check)
        elif ns.action == "stop":
            code, out = listener.stop(cfg, only_ours=ns.only_ours)
        else:
            out = listener.status(cfg)
            code = 0 if out.get("running") is not None else 1
        _print(out)
        return code

    if ns.cmd == "doctor":
        from .doctor import run_checks, summary_exit
        checks = run_checks(cfg)
        if ns.json:
            _print({"checks": checks})
        else:
            for c in checks:
                print(f"[{c['status']:>4}] {c['name']}: {c['detail']}")
        return summary_exit(checks)

    if ns.cmd == "sync-labels":
        from .labels import sync_labels
        code, out = sync_labels(cfg, dry_run=ns.dry_run)
        _print(out)
        return code

    from .poller import Bridge
    if ns.cmd in ("run", "once"):
        from .journal import StateLocked, acquire_state_lock
        try:
            _lock_fd = acquire_state_lock(cfg.state_dir)   # held until the process exits
        except StateLocked as e:
            print(f"bridge already running: {e}. Stop it first (scripts/stop_local.sh).", file=sys.stderr)
            return 5
    bridge = Bridge(cfg)
    if ns.cmd == "run":
        bridge.install_signals()
        bridge.run_forever()
        return 0
    try:
        if ns.cmd == "once":
            _print(bridge.run_once())
        else:
            _print(bridge.api.status())
    except ServerUnavailable as e:
        _print({"error": "server_unavailable", "detail": str(e)})
        return 1
    except ApiError as e:
        _print({"error": e.code, "status": e.status})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
