"""Stand-in for WP4 `doctor.py` in the operations tests (16.3.3 signatures only).

`run_checks` returns one CheckResult per requested id ("pass" unless behaviour "stubs": {"checks": {id: status}}
says otherwise) and records which ids were asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import _stubio

DEFAULT_IDS = ("release", "processes", "listen_local_only", "openmausbot_options")


@dataclass
class CheckResult:
    n: int
    id: str
    group: str
    status: str
    label: str
    detail: str
    fix: str | None

    def as_dict(self) -> dict:
        return {"n": self.n, "id": self.id, "group": self.group, "status": self.status, "label": self.label,
                "detail": self.detail, "fix": self.fix}


def run_checks(ctx, *, only: set[str] | None = None) -> list[CheckResult]:
    ids = sorted(only) if only else list(DEFAULT_IDS)
    _stubio.record("doctor.run_checks", only=sorted(only) if only else None)
    statuses = _stubio.behaviour().get("checks") or {}
    return [CheckResult(n=i + 1, id=c, group="stub", status=statuses.get(c, "pass"), label=f"stub {c}",
                        detail="stub detail.", fix=None) for i, c in enumerate(ids)]


def passes(ctx, ids: set[str]) -> bool:
    return all(r.status not in ("fail", "todo") for r in run_checks(ctx, only=ids))


def exit_code(results, strict: bool) -> int:
    return 1 if any(r.status == "fail" for r in results) else 0


def cmd_doctor(ctx, args) -> int:
    return exit_code(run_checks(ctx), False)
