"""The only place that asks the person something (invariant 10).

`ask()` takes one letter answers (`c` yes, `k` no, `s` later, ...). A non-interactive stdin answers `k` when the
question offers it, else `s`. `--yes` answers `c`, but only for a question asked with `allow_yes=True`. `typed()`
needs typed words (`dong y`, `khoi phuc`, `xoa du lieu`) and is never answered by `--yes` or a non-interactive stdin.
"""

from __future__ import annotations

import sys
import unicodedata

from .text_vi import say

_WORDS = {  # whole-word answers, compared without diacritics
    "co": "c",
    "khong": "k",
    "sau": "s",
    "de sau": "s",
    "thu lai": "c",
}


def _fold(text: str) -> str:
    """Lower case, without Vietnamese diacritics (d with stroke becomes d), single spaces."""
    text = unicodedata.normalize("NFD", text.strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace(chr(0x111), "d")
    return " ".join(text.split())


def _read_line() -> str | None:
    """One line from stdin without its newline; None at end of input."""
    try:
        line = sys.stdin.readline()
    except (OSError, ValueError):
        return None
    if line == "":
        return None
    return line.rstrip("\r\n")


def _auto(choices: str) -> str:
    return "k" if "k" in choices else "s"


def ask(ctx, key: str, choices: str = "ck", *, allow_yes: bool = True, **fmt: object) -> str:
    """Print `t(key, **fmt)` and return one letter of `choices`.

    Case and diacritics are ignored, and the whole words for yes, no and later count as `c`, `k` and `s`. A bare
    Enter counts as `k` (or `s` when `k` is not offered); any other answer asks again. `--yes` with `allow_yes` prints the question and answers `c`; a non-interactive stdin
    (or end of input) answers `k` when offered, else `s`.
    """
    choices = choices.lower()
    say(key, **fmt)
    if ctx.yes and allow_yes and "c" in choices:
        say("core.answer_yes")
        return "c"
    if not ctx.interactive:
        answer = _auto(choices)
        say("core.answer_noninteractive", answer=answer)
        return answer
    while True:
        line = _read_line()
        if line is None:
            answer = _auto(choices)
            say("core.answer_noninteractive", answer=answer)
            return answer
        folded = _fold(line)
        if folded == "":
            if "k" in choices or "s" in choices:
                return _auto(choices)
        elif len(folded) == 1 and folded in choices:
            return folded
        elif folded in _WORDS and _WORDS[folded] in choices:
            return _WORDS[folded]
        say("core.ask_again", choices=", ".join(choices))


def typed(ctx, key: str, words: tuple[str, ...], **fmt: object) -> bool:
    """Print `t(key, **fmt)` and return True when the person types one of `words`.

    Compared after NFC normalisation and lower case; a word without diacritics also matches the same word typed
    with diacritics ("dong y" accepts it written the Vietnamese way). One attempt; a bare Enter is False. Never
    answered by `--yes`; a non-interactive stdin gives False.
    """
    say(key, **fmt)
    if not ctx.interactive:
        say("core.typed_needs_person")
        return False
    line = _read_line()
    if line is None:
        say("core.typed_needs_person")
        return False
    answer = " ".join(unicodedata.normalize("NFC", line).strip().lower().split())
    if not answer:
        return False
    exact = {" ".join(unicodedata.normalize("NFC", w).strip().lower().split()) for w in words}
    if answer in exact:
        return True
    return _fold(answer) in {_fold(w) for w in words}
