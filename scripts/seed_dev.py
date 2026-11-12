"""Load the catalog, facts, block A and tool definitions into the local backend (POST /dev/seed, ENV=dev only).

Auth: /dev/* needs the staff bearer token. The script reads STAFF_TOKEN from the environment, else from
apps/server/.dev.vars (never printed).

Reads the read-only sources and posts them as one DevSeedRequest (docs/contracts.md section 5):
  data/services.json, data/business-facts.json,
  block A = the ```text fence under "## Khối A" in design/system-prompt-draft.md,
  design/tools-schema.json.
The Worker never reads repo files at runtime. With --embedded the script posts {} and the server uses the copy
generated at build time in apps/server/src/seed-data.ts (scripts/gen-seed-data.mjs).

Examples (from the project root, with `pnpm dev:server` running):
  python3 -I scripts/seed_dev.py
  python3 -I scripts/seed_dev.py --catalog-version cv_seed_test --no-activate
  python3 -I scripts/seed_dev.py --url http://127.0.0.1:8787 --embedded
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block_a() -> str:
    text = (ROOT / "design/system-prompt-draft.md").read_text(encoding="utf-8")
    start = text.index("## Khối A")
    fence = text.index("```text\n", start) + len("```text\n")
    end = text.index("\n```", fence)
    return text[fence:end].strip()


def staff_token() -> str:
    tok = os.environ.get("STAFF_TOKEN", "").strip()
    if tok:
        return tok
    path = ROOT / "apps/server/.dev.vars"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip() == "STAFF_TOKEN":
                return val.strip().strip('"').strip("'")
    return ""


def build_body(args: argparse.Namespace) -> dict:
    if args.embedded:
        body: dict = {}
    else:
        body = {
            "services_json": json.loads((ROOT / "data/services.json").read_text(encoding="utf-8")),
            "business_facts_json": json.loads((ROOT / "data/business-facts.json").read_text(encoding="utf-8")),
            "block_a": block_a(),
            "tools_schema_json": json.loads((ROOT / "design/tools-schema.json").read_text(encoding="utf-8")),
        }
    if args.catalog_version:
        body["catalog_version"] = args.catalog_version
    if args.no_activate:
        body["activate"] = False
    return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8787", help="backend base URL")
    ap.add_argument("--catalog-version", default="", help="default: cv_seed_<yyyymmdd> (server side)")
    ap.add_argument("--no-activate", action="store_true", help="store the version without activating it")
    ap.add_argument("--embedded", action="store_true", help="post {} and use the server's build-time copy")
    args = ap.parse_args()

    token = staff_token()
    if not token:
        print("STAFF_TOKEN not set (environment or apps/server/.dev.vars)", file=sys.stderr)
        return 1
    data = json.dumps(build_body(args), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        args.url.rstrip("/") + "/dev/seed", data=data, method="POST", headers={"content-type": "application/json", "authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            print(res.read().decode("utf-8"))
            return 0
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"cannot reach {args.url}: {e.reason} (is `pnpm dev:server` running?)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
