"""The local D1 database: where miniflare keeps it, which migrations are applied or pending, applying them, and the
active catalog id (rev F7, F13).

Miniflare keeps local D1 at `<persist>/v3/d1/miniflare-D1DatabaseObject/<hash>.sqlite`, beside a `metadata.sqlite`
and possibly other `<hash>.sqlite` files. Every open here is read-only (`mode=ro`), so reading never changes the
file; whether `wrangler dev` holding the file makes such a read fail was not tested (16.13 item 7).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

D1_SUBDIR = ("v3", "d1", "miniflare-D1DatabaseObject")
DATABASE = "thomhouse-main"


def _folder(bot_home: Path) -> Path:
    return bot_home.joinpath("d1", *D1_SUBDIR)


def _candidates(bot_home: Path) -> list[Path]:
    try:
        return sorted(p for p in _folder(bot_home).glob("*.sqlite") if p.is_file() and p.name != "metadata.sqlite")
    except OSError:
        return []


def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=2.0)


def _has_table(path: Path, table: str) -> bool:
    try:
        con = _connect_ro(path)
    except sqlite3.Error:
        return False
    try:
        row = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()


def find_db(bot_home: Path) -> Path | None:
    """The newest (mtime) `*.sqlite` in `bot_home/d1/v3/d1/miniflare-D1DatabaseObject/` that has a table
    `d1_migrations`; `metadata.sqlite` and files without that table are ignored (rev F13)."""
    found = [p for p in _candidates(bot_home) if _has_table(p, "d1_migrations")]
    if not found:
        return None
    return max(found, key=lambda p: (p.stat().st_mtime, p.name))


def applied(bot_home: Path) -> list[str] | None:
    """Names of the applied migrations in order; [] when the folder holds no `*.sqlite` other than
    `metadata.sqlite`; None when such files exist but none has `d1_migrations`, or the file cannot be read."""
    if not _candidates(bot_home):
        return []
    db = find_db(bot_home)
    if db is None:
        return None
    try:
        con = _connect_ro(db)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute("SELECT name FROM d1_migrations ORDER BY id").fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return [str(r[0]) for r in rows]


def pending(code_root: Path, bot_home: Path) -> list[str] | None:
    """Sorted names of `code_root/apps/server/migrations/*.sql` that are not applied; None when `applied()` is
    None."""
    done = applied(bot_home)
    if done is None:
        return None
    folder = code_root / "apps" / "server" / "migrations"
    try:
        names = sorted(p.name for p in folder.glob("*.sql") if p.is_file())
    except OSError:
        names = []
    have = set(done)
    return [n for n in names if n not in have]


def apply(ctx, code_root: Path) -> int:
    """`wrangler d1 migrations apply thomhouse-main --local --persist-to <bot_home>/d1 </dev/null` in
    `code_root/apps/server` with the child environment; output in `logs/migrations.log`; wrangler's exit code
    (127 when wrangler is not installed)."""
    from . import proc

    server = code_root / "apps" / "server"
    wrangler = server / "node_modules" / ".bin" / "wrangler"
    persist = ctx.paths.bot_home / "d1"
    persist.mkdir(parents=True, exist_ok=True)
    res = proc.run(
        ctx,
        [str(wrangler), "d1", "migrations", "apply", DATABASE, "--local", "--persist-to", str(persist)],
        cwd=server,
        log=ctx.paths.logs / "migrations.log",
    )
    ctx.log("migrations_apply", exit=res.returncode)
    return res.returncode


def active_catalog(bot_home: Path) -> str | None:
    """`SELECT id FROM catalog_versions WHERE status = 'active'` on the D1 file (read-only); None when there is no
    database, no such table, no active row or the file cannot be read (rev F7)."""
    db = find_db(bot_home)
    if db is None:
        return None
    try:
        con = _connect_ro(db)
    except sqlite3.Error:
        return None
    try:
        row = con.execute("SELECT id FROM catalog_versions WHERE status = 'active' LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return str(row[0]) if row and row[0] is not None else None
