"""consent.py: c/k and c/s answers, non-interactive answers, --yes, typed words (invariant 10)."""

from __future__ import annotations

import contextlib
import io
from unittest import mock

from tests.support import InstallerTestCase
from thomhouse_installer import consent
from thomhouse_installer.text_vi import t

QUESTION = "core.starting"  # any catalog text works as the question


class ConsentTest(InstallerTestCase):
    def _ask(self, stdin: str, *, interactive: bool = True, yes: bool = False, choices: str = "ck",
             allow_yes: bool = True) -> tuple[str, str]:
        ctx = self.ctx(self.tmp, interactive=interactive, yes=yes)
        ctx.yes = yes
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            answer = consent.ask(ctx, QUESTION, choices, allow_yes=allow_yes)
        return answer, out.getvalue()

    def _typed(self, stdin: str, words=("dong y", "đồng ý"), *, interactive: bool = True,
               yes: bool = False) -> tuple[bool, str]:
        ctx = self.ctx(self.tmp, interactive=interactive, yes=yes)
        ctx.yes = yes
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            result = consent.typed(ctx, QUESTION, words)
        return result, out.getvalue()

    def test_ck_answers(self) -> None:
        for typed_text, expected in (("c\n", "c"), ("C\n", "c"), ("k\n", "k"), ("có\n", "c"), ("Không\n", "k"),
                                     ("  c  \n", "c"), ("\n", "k")):
            answer, out = self._ask(typed_text)
            self.assertEqual(answer, expected, typed_text)
            self.assertIn(t(QUESTION), out)

    def test_cs_answers(self) -> None:
        for typed_text, expected in (("c\n", "c"), ("s\n", "s"), ("\n", "s"), ("để sau\n", "s")):
            answer, _ = self._ask(typed_text, choices="cs")
            self.assertEqual(answer, expected, typed_text)

    def test_asks_again_on_other_answer(self) -> None:
        answer, out = self._ask("x\nyes\nk\n")
        self.assertEqual(answer, "k")
        self.assertEqual(out.count(t("core.ask_again", choices="c, k")), 2)

    def test_end_of_input_answers_like_non_interactive(self) -> None:
        answer, _ = self._ask("x\n")
        self.assertEqual(answer, "k")
        answer, _ = self._ask("", choices="cs")
        self.assertEqual(answer, "s")

    def test_non_interactive_answers_k_or_s(self) -> None:
        answer, out = self._ask("c\n", interactive=False)
        self.assertEqual(answer, "k")
        self.assertIn(t("core.answer_noninteractive", answer="k"), out)
        answer, _ = self._ask("c\n", interactive=False, choices="cs")
        self.assertEqual(answer, "s")

    def test_yes_answers_c_and_prints_question(self) -> None:
        answer, out = self._ask("", yes=True)
        self.assertEqual(answer, "c")
        self.assertIn(t(QUESTION), out)
        self.assertIn(t("core.answer_yes"), out)
        answer, _ = self._ask("", yes=True, interactive=False)
        self.assertEqual(answer, "c")

    def test_yes_never_answers_a_question_without_allow_yes(self) -> None:
        answer, out = self._ask("k\n", yes=True, allow_yes=False)
        self.assertEqual(answer, "k")
        self.assertNotIn(t("core.answer_yes"), out)
        answer, _ = self._ask("", yes=True, allow_yes=False, interactive=False)
        self.assertEqual(answer, "k")

    def test_typed_words(self) -> None:
        for typed_text in ("dong y\n", "Dong Y\n", "đồng ý\n", "ĐỒNG Ý\n", "  dong   y \n"):
            ok, out = self._typed(typed_text)
            self.assertTrue(ok, typed_text)
            self.assertIn(t(QUESTION), out)
        for typed_text in ("\n", "c\n", "dong\n", "y\n"):
            ok, _ = self._typed(typed_text)
            self.assertFalse(ok, typed_text)

    def test_typed_ascii_word_accepts_diacritics(self) -> None:
        ok, _ = self._typed("khôi phục\n", words=("khoi phuc",))
        self.assertTrue(ok)
        ok, _ = self._typed("xóa dữ liệu\n", words=("xoa du lieu",))
        self.assertTrue(ok)

    def test_typed_never_answered_by_yes_or_non_interactive(self) -> None:
        ok, out = self._typed("dong y\n", interactive=False, yes=True)
        self.assertFalse(ok)
        self.assertIn(t("core.typed_needs_person"), out)
        ok, _ = self._typed("", yes=True)
        self.assertFalse(ok)
        ok, _ = self._typed("dong y\n", yes=True)
        self.assertTrue(ok)  # the person typed it; --yes did not
