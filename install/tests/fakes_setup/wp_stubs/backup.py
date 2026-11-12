"""Stand-in for thomhouse_installer.backup (WP5) in the setup tests: `make` copies BOT_HOME/d1 into
BOT_HOME/backups/<stamp>-<reason>/d1 with a backup.json and returns state.BackupInfo.
Behaviour "stub_backup": {"fail": "make"} raises BackupError."""

from __future__ import annotations

import json
import os
import shutil
import time

from thomhouse_installer import _stubrec, migrations, state
from thomhouse_installer.context import InstallerError


class BackupError(InstallerError):
    code = 1

    def __init__(self, kind: str) -> None:
        super().__init__("core.failed", 3 if kind in ("refused", "locked") else 1)
        self.kind = kind


def make(ctx, *, mode: str, reason: str) -> state.BackupInfo:
    _stubrec.record("backup", "make", mode, reason)
    if _stubrec.fails("backup", "make"):
        raise BackupError("verify")
    p = ctx.paths
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = p.backups / f"{stamp}-{reason}"
    n = 1
    while folder.exists():
        n += 1
        folder = p.backups / f"{stamp}-{reason}-{n}"
    folder.mkdir(parents=True)
    os.chmod(folder, 0o700)
    if p.d1_dir.exists():
        shutil.copytree(p.d1_dir, folder / "d1", symlinks=True)
    applied = migrations.applied(p.bot_home) or []
    meta = {"schema": 1, "id": folder.name, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": reason,
            "mode": mode, "app_version": "1.4.0", "device_id": None, "migrations_applied": applied, "files": []}
    (folder / "backup.json").write_text(json.dumps(meta), encoding="utf-8")
    return state.BackupInfo(id=folder.name, path=folder, created_at=meta["created_at"], reason=reason, mode=mode,
                            app_version="1.4.0", device_id=None, migrations_applied=applied, bytes=0)
