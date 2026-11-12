"""Vietnamese text catalog of the installer (16.4.7).

Each catalog module `text_vi/{core,release,setup,doctor,ops}.py` defines `TEXTS: dict[str, str]` whose keys start
with "<module>.". This package merges the modules that exist; a duplicate key raises ValueError at import. A text
may hold several screen lines separated by "\\n" and `{name}` placeholders filled by `t()`.
"""

from __future__ import annotations

import importlib

CATALOGS = ("core", "release", "setup", "doctor", "ops")


def _merge() -> dict[str, str]:
    merged: dict[str, str] = {}
    for name in CATALOGS:
        full = f"{__name__}.{name}"
        try:
            module = importlib.import_module(full)
        except ModuleNotFoundError as e:
            if e.name == full:
                continue  # that package is not built yet
            raise
        texts = getattr(module, "TEXTS", {})
        for key, value in texts.items():
            if key in merged:
                raise ValueError(f"duplicate text key {key!r} in text_vi.{name}")
            merged[key] = value
    return merged


TEXTS: dict[str, str] = _merge()
KEYS: frozenset[str] = frozenset(TEXTS)


def t(key: str, **fmt: object) -> str:
    """The text of `key` with `fmt` filled in; KeyError for an unknown key or a missing placeholder value."""
    return TEXTS[key].format(**fmt)


def say(key: str, **fmt: object) -> None:
    """Print `t(key, **fmt)` on standard output."""
    print(t(key, **fmt), flush=True)
