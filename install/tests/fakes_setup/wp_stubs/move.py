"""Stand-in for thomhouse_installer.move (WP5) in the setup tests.

`place_moved_data(ctx, image)` reads `image` as JSON {"accounts": [...]} (a stand-in for the encrypted disk
image) and writes BOT_HOME/accounts.json the way 16.8.5 does: every account gets BOT_HOME/accounts/<label> (created)
and `enabled: false`, also one with `config_dir: null`; account-state.json becomes {}.
Behaviour "stub_move": {"exit": n} returns n without changing anything.
"""

from __future__ import annotations

import json
from pathlib import Path

from thomhouse_installer import _stubrec


def place_moved_data(ctx, image: Path) -> int:
    _stubrec.record("move", "place_moved_data", image)
    code = int(_stubrec.behaviour("move").get("exit", 0))
    if code != 0:
        return code
    data = json.loads(Path(image).read_text(encoding="utf-8"))
    p = ctx.paths
    out = []
    for account in data.get("accounts", []):
        folder = p.bot_home / "accounts" / account["label"]
        folder.mkdir(parents=True, exist_ok=True)
        out.append({"label": account["label"], "config_dir": str(folder),
                    "priority": account.get("priority", 100), "enabled": False})
    p.bot_home.mkdir(parents=True, exist_ok=True)
    p.accounts_json.write_text(json.dumps(out), encoding="utf-8")
    p.account_state_json.write_text("{}", encoding="utf-8")
    return 0
