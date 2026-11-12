"""Static rules over install/** and scripts/release/** (16.10 test_core_static): forbidden strings, no runner API
path, no Vietnamese outside text_vi, Python 3.11 syntax, shell syntax."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.support import FAKE_TREE, INSTALL_DIR, PROJECT_ROOT
from tests.test_core_text import VIET

RELEASE_DIR = PROJECT_ROOT / "scripts" / "release"
FORBIDDEN = (
    "--qr-url", "--tunnel", "--lan", "--relay", "--domain", "--public-url", "--tailscale", "0.0.0.0", "sudo ",
    "ANTHROPIC_API_KEY=", "PROFILE_LLM_ENABLED=true", "PUT /staff/flags", "auto-reply", "openmausbot login",
    ".zshrc", ".zprofile", ".bash_profile", "THOMHOUSE_DRAFT_ENGINE=",
)
SHELL_FILES = ("selfextract.sh.in", "bootstrap.sh", "thomhouse.sh.in")
SKIP_PARTS = ("__pycache__",)


def _files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(f for f in root.rglob("*") if f.is_file() and not any(p in f.parts for p in SKIP_PARTS)
                  and f.suffix != ".pyc")


def _scanned() -> list[Path]:
    tests = INSTALL_DIR / "tests"
    out = []
    for f in _files(INSTALL_DIR) + _files(RELEASE_DIR):
        if f.is_relative_to(tests) or f.name == "safety.py":
            continue
        out.append(f)
    return out


class StaticTest(unittest.TestCase):
    def test_forbidden_strings(self) -> None:
        hits = []
        for f in _scanned():
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for word in FORBIDDEN:
                if word in text:
                    hits.append(f"{f.relative_to(PROJECT_ROOT)}: {word}")
        self.assertEqual(hits, [])

    def test_no_runner_api_literal(self) -> None:
        hits = []
        for f in _scanned():
            text = f.read_text(encoding="utf-8", errors="replace")
            if f.suffix == ".py":
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and \
                            node.value.startswith("/runner/"):
                        hits.append(str(f.relative_to(PROJECT_ROOT)))
            elif re.search(r"[\"']/runner/", text):
                hits.append(str(f.relative_to(PROJECT_ROOT)))
        self.assertEqual(hits, [])

    def test_no_vietnamese_outside_text_catalogs(self) -> None:
        hits = []
        for f in _scanned():
            if f.suffix == ".py" and "text_vi" not in f.parts and VIET.search(f.read_text(encoding="utf-8")):
                hits.append(str(f.relative_to(PROJECT_ROOT)))
        self.assertEqual(hits, [])

    def test_python_3_11_syntax(self) -> None:
        files = [f for f in _files(INSTALL_DIR) + _files(RELEASE_DIR) if f.suffix == ".py"]
        self.assertTrue(files)
        for f in files:
            with self.subTest(file=str(f.relative_to(PROJECT_ROOT))):
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f), feature_version=(3, 11))

    def test_entry_point_adds_its_folder_for_isolated_python(self) -> None:
        text = (INSTALL_DIR / "thomhouse.py").read_text(encoding="utf-8")
        self.assertIn("sys.path.insert(0, str(Path(__file__).resolve().parent))", text)
        tree = ast.parse(text)
        body = tree.body[1:] if ast.get_docstring(tree) is not None else tree.body
        first_code = [n for n in body if not isinstance(n, (ast.Import, ast.ImportFrom))][0]
        self.assertIn("sys.path.insert", ast.unparse(first_code))

    def test_shell_syntax(self) -> None:
        targets = [INSTALL_DIR / n for n in SHELL_FILES if (INSTALL_DIR / n).exists()]
        targets += [FAKE_TREE / "scripts" / "start_local.sh", FAKE_TREE / "scripts" / "stop_local.sh"]
        for f in targets:
            with self.subTest(file=f.name):
                res = subprocess.run(["/bin/bash", "-n", str(f)], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, res.stderr)
                zsh = shutil.which("zsh") or "/bin/zsh"
                if f.name in SHELL_FILES and Path(zsh).exists():
                    res = subprocess.run([zsh, "-n", str(f)], capture_output=True, text=True)
                    self.assertEqual(res.returncode, 0, res.stderr)
