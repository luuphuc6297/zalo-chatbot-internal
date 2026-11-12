"""Entry point (run from apps/runner):

  python3 -m runner.main run              poll forever (claim -> claude -p -> draft/fail), Ctrl-C twice to kill
  python3 -m runner.main once             claim and process at most one job, print a JSON summary
  python3 -m runner.main status           print the claude_pool status (with `claude auth status`) and post it
                                          to /runner/status; applies the desired account the server returns
  python3 -m runner.main forget <cnv_id>  delete this conversation's workdir and session files (data deletion)
  python3 -m runner.main rooms-setup      two-bot rooms: write the platform's config.json (one instance per pool
                                          account, the "thom" tools server) and <home>/rooms/credentials.json.
                                          Run it before the rooms platform starts; it contacts nothing.

Output never contains message text or tokens.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .api import ServerUnavailable
from .config import Config, ConfigError
from .contract import ApiError
from .room_setup import SetupError, run_setup
from .sessions import SessionStore, default_account_in_pool


def build_runner(require_token: bool = True):
    from .poller import Runner
    return Runner(Config.load(require_token=require_token))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("once")
    sub.add_parser("status")
    sub.add_parser("rooms-setup")
    f = sub.add_parser("forget")
    f.add_argument("conversation_id")
    ap.add_argument("-v", "--verbose", action="store_true")
    ns = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if ns.verbose else logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if ns.cmd == "forget":
            cfg = Config.load(require_token=False)
            removed = SessionStore(cfg.home).forget_conversation(ns.conversation_id)
            print(json.dumps({"conversation_id": ns.conversation_id, "removed_paths": len(removed)}))
            return 0
        if ns.cmd == "rooms-setup":
            from .claude_runner import load_pool
            cfg = Config.load(require_token=True)
            print(json.dumps(run_setup(cfg, load_pool(cfg.pool_path, cfg.home).accounts()), ensure_ascii=False))
            return 0
        runner = build_runner(require_token=True)
    except (ConfigError, SetupError, ValueError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    if ns.cmd == "run":
        runner.install_signals()
        if default_account_in_pool(runner.claude.pool.accounts()):
            logging.warning("an enabled pool account uses ~/.claude; its session files are not deleted by "
                            "the runner")
        runner.run_forever()
        return 0
    if ns.cmd == "once":
        try:
            out = runner.run_once()
        except ServerUnavailable as e:
            print(json.dumps({"error": "server_unavailable", "detail": str(e)}))
            return 1
        except ApiError as e:
            print(json.dumps({"error": e.code, "status": e.status}))
            return 1
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if ns.cmd == "status":
        body = runner.status_body(with_login=True)
        print(json.dumps(body, ensure_ascii=False, indent=1))
        try:
            resp = runner.report_status(body=body)
        except (ServerUnavailable, ApiError) as e:
            print(json.dumps({"posted": False, "error": getattr(e, "code", str(e))}))
            return 1
        print(json.dumps({"posted": True, "desired_account": resp.get("desired_account"),
                          "applied_desired_account": runner.applied_desired_account,
                          "flags": resp.get("flags")}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
