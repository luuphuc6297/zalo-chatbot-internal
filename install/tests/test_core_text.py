"""Text catalog rules (16.4.7): Vietnamese with diacritics, "anh" only, no emoji, at most 100 characters per line,
unique keys, every key used in code exists, and the texts the contract fixes equal the catalogs."""

from __future__ import annotations

import ast
import importlib
import re
import unittest
from pathlib import Path

from tests.support import INSTALL_DIR, PROJECT_ROOT
from thomhouse_installer import download, text_vi

VIET = re.compile("[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
                  "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]")
FORBIDDEN_WORDS = re.compile(r"(?<![\w])(bạn|mình)(?![\w])", re.IGNORECASE)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍⭐⬆↔-↪]")
KEY_LITERAL = re.compile(r"^(core|release|setup|doctor|ops)\.[a-z0-9_]+$")
FILE_SUFFIXES = (".py", ".json", ".log", ".sh", ".txt", ".md", ".in")
SHELL_TEMPLATES = ("selfextract.sh.in", "bootstrap.sh", "thomhouse.sh.in")

# Texts with a key in 16.4.7 and 16.8.1, copied from the contract. " / " separates two screen lines there.
KEYED = {
    "release.already_installed": "Máy này đã cài chatbot thom house, nên file cài không chạy lại từ đầu. / "
    "Cập nhật bằng file này: ~/ThomHouse/bin/thomhouse update {file} / "
    "Các bước còn lại: ~/ThomHouse/bin/thomhouse continue",
    "core.download_network": "Chưa tải được {tên} từ {máy chủ} vì máy không kết nối được mạng. / "
    "Anh kiểm tra mạng rồi chạy lại: {lệnh}",
    "core.download_http": "Máy chủ {máy chủ} chưa trả file {tên}. Anh chờ một lúc rồi chạy lại: {lệnh}",
    "core.download_size": "File {tên} tải về không đúng mã kiểm tra nên chương trình đã xóa file đó. "
    "Anh chạy lại: {lệnh}",
    "core.download_checksum": "File {tên} tải về không đúng mã kiểm tra nên chương trình đã xóa file đó. "
    "Anh chạy lại: {lệnh}",
    "core.download_not_https": "Địa chỉ tải {tên} không dùng https nên chương trình không tải. "
    "Anh báo người gửi file.",
    "release.deps_workspace": "Chưa cài được thư viện từ registry.npmjs.org; chi tiết ở ~/ThomHouse/logs/deps.log. / "
    "Anh kiểm tra mạng rồi chạy lại: {lệnh}",
    "release.deps_engine": "Chưa cài được thư viện từ registry.npmjs.org; chi tiết ở ~/ThomHouse/logs/deps.log. / "
    "Anh kiểm tra mạng rồi chạy lại: {lệnh}",
    "release.runtime_installer": "Chưa cài được Claude Code; chi tiết ở ~/ThomHouse/logs/runtimes.log.",
    "release.runtime_checksum": "Bản Claude Code vừa tải không khớp bản đã thử trên máy tạo file cài, / "
    "nên chương trình đã gỡ bản đó. Anh báo người gửi file.",
    "core.locked": "Một lệnh cài hoặc cập nhật khác đang chạy trên máy này. Anh chờ lệnh đó xong rồi chạy lại.",
    "core.update_open": "Lần cập nhật trước chưa xong, nên chương trình chưa làm lệnh này. / "
    "Anh chạy lại: ~/ThomHouse/bin/thomhouse update {file}",
    "core.moved_out": "Dữ liệu chatbot của máy này đã chuyển sang máy khác, nên chương trình không bật chatbot ở đây. / "
    "Muốn chạy lại ở máy này: {tb} move-back",
    "setup.shared_data": "Máy này đã có dữ liệu chatbot ở {thư mục}, của một bản cài khác hoặc của bản đã gỡ. / "
    "Bản cài mới sẽ dùng dữ liệu đó; nếu bản kia vẫn còn trên máy, anh không chạy bản kia nữa. / "
    "Dùng dữ liệu đó? [c = có / k = không]",
    "ops.desktop_prompt": "macOS có thể hỏi bằng tiếng Anh cho Terminal ghi vào Desktop; anh bấm Allow.",
    "ops.hdiutil_create": "Ngay sau đây hdiutil hỏi mật khẩu bằng tiếng Anh. Anh đặt mật khẩu và ghi lại để mở ở máy "
    "mới.",
    "ops.hdiutil_attach": "Ngay sau đây macOS hỏi mật khẩu của file chuyển máy; anh nhập mật khẩu đã đặt ở máy cũ.",
    "setup.visits_server_404": "Máy chủ chưa nhận được kết quả phân tích buổi làm; lần chạy thomhouse continue sau sẽ "
    "thử lại.",
    "ops.update_same": "Máy đã chạy bản {v}, nên không cần cập nhật. / "
    "Các bước còn lại: ~/ThomHouse/bin/thomhouse continue",
}

STEP_TITLES = {
    1: "Kiểm tra file cài đặt", 2: "Kiểm tra máy", 3: "Giải nén chương trình", 4: "Cài Python",
    5: "Cài Node.js, pnpm và Claude Code", 6: "Điều khoản bộ công cụ Zalo", 7: "Cài thư viện của chương trình",
    8: "Kích hoạt bản cài", 9: "Tạo file cấu hình và mã bí mật", 10: "Chuyển dữ liệu từ máy cũ",
    11: "Chép ảnh menu gốc", 12: "Cập nhật cơ sở dữ liệu", 13: "Đăng ký tài khoản Claude cho chatbot",
    14: "Đăng nhập Claude", 15: "Bật chatbot", 16: "Đăng nhập Zalo", 17: "Lấy tin nhắn cũ từ điện thoại",
    18: "Phân tích danh bạ khách", 19: "Phân tích các buổi làm trong tin nhắn", 20: "Gắn nhãn khách trong Zalo",
    21: "Đưa mã nhân viên vào console", 22: "Tự bật chatbot khi đăng nhập máy", 23: "Tạo nút bấm trên màn hình",
    24: "Kiểm tra ảnh menu", 25: "Kiểm tra lần cuối",
}

DOCTOR_LABELS = (
    "Hệ điều hành", "Chip", "Dung lượng trống", "Công cụ của macOS", "Python", "Lệnh cài khác", "Máy đã chuyển đi",
    "Bản chatbot khác", "Bản cài", "Tệp chương trình", "Tệp không được mang theo", "Node.js", "pnpm", "Claude Code",
    "Phiên bản ghi trong mã", "Thư viện JavaScript", "Bộ công cụ Zalo", "OpenMausBot", "Ảnh menu gốc",
    "File cấu hình", "Mã bí mật khớp nhau", "Đường dẫn trong file cấu hình", "Quyền thư mục", "Khóa API Anthropic",
    "Phân tích bằng model", "Cơ sở dữ liệu", "Bản cập nhật cơ sở dữ liệu", "Sao lưu", "Tài khoản Claude của chatbot",
    "Đăng nhập Claude", "Các phần của chatbot", "Máy chủ local", "Runner", "Danh mục dịch vụ", "Console",
    "Đăng nhập Zalo", "Nhận tin Zalo", "Bridge", "Phòng chat hai bot", "Ảnh menu cho Zalo", "Chỉ mở trên máy này",
    "Tùy chọn của OpenMausBot", "Chế độ trả lời", "Tin nhắn cũ", "Phân tích danh bạ", "Phân tích buổi làm",
    "Nhãn khách trong Zalo", "Mã nhân viên trong console",
)
DOCTOR_STATUS_WORDS = ("[ĐẠT]", "[LỖI]", "[CHÚ Ý]", "[CHƯA LÀM]", "[BỎ QUA]")

OS_SENTENCES = (  # 16.5, sentences without placeholders
    "Anh báo người gửi file; chương trình chưa thay đổi gì trên máy này.",
    "Máy Intel chưa được chạy thử. Anh vẫn cài? [c = có / k = không]",
    "File cài này chưa có bản cho máy Intel.",
    "Anh chạy lại lệnh cài bằng tài khoản thường của máy, không dùng sudo.",
    "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; máy Linux chưa được hỗ trợ.",
    "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; Windows và WSL chưa được hỗ trợ.",
    "Bản cài này chỉ chạy trên máy Mac có macOS 13.5 trở lên; máy Windows chưa được hỗ trợ.",
)


def normalize(text: str) -> str:
    """Placeholders as {}, the contract's " / " line separator and every line break as one space."""
    text = re.sub(r"\{[^{}]*\}", "{}", text)
    text = text.replace(" / ", " ").replace("\n", " ")
    return " ".join(text.split())


def text_problems(text: str, *, fixed_label: bool = False) -> list[str]:
    """`fixed_label`: a doctor label that 16.7 fixes as a product or part name (Chip, Python, Node.js, ...); such a
    label has no Vietnamese word to carry diacritics, so only the other rules apply to it."""
    problems = []
    if not fixed_label and not VIET.search(text):
        problems.append("no Vietnamese diacritics")
    if FORBIDDEN_WORDS.search(text):
        problems.append("uses bạn or mình")
    if EMOJI.search(text):
        problems.append("emoji")
    for line in text.split("\n"):
        if len(line) > 100:
            problems.append(f"line longer than 100 characters ({len(line)})")
    return problems


def catalog_modules() -> dict[str, object]:
    found = {}
    for name in text_vi.CATALOGS:
        try:
            found[name] = importlib.import_module(f"thomhouse_installer.text_vi.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"thomhouse_installer.text_vi.{name}":
                raise
    return found


class CatalogRulesTest(unittest.TestCase):
    def test_every_catalog_string_follows_the_rules(self) -> None:
        for key, value in text_vi.TEXTS.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, str)
                fixed = key.startswith("doctor.label_") and value in DOCTOR_LABELS
                self.assertEqual(text_problems(value, fixed_label=fixed), [])

    def test_keys_unique_and_prefixed(self) -> None:
        modules = catalog_modules()
        self.assertIn("core", modules)
        total = 0
        for name, module in modules.items():
            for key in module.TEXTS:
                self.assertTrue(key.startswith(f"{name}."), key)
            total += len(module.TEXTS)
        self.assertEqual(total, len(text_vi.TEXTS))
        self.assertEqual(text_vi.KEYS, frozenset(text_vi.TEXTS))

    def test_t_and_say(self) -> None:
        self.assertEqual(text_vi.t("core.not_built", part="doctor", command="doctor").count("doctor"), 2)
        with self.assertRaises(KeyError):
            text_vi.t("core.no_such_key")
        with self.assertRaises(KeyError):
            text_vi.t("core.not_built")  # placeholder values missing

    def test_every_key_used_in_code_exists(self) -> None:
        files = [INSTALL_DIR / "thomhouse.py"] + [
            f for f in (INSTALL_DIR / "thomhouse_installer").rglob("*.py") if "text_vi" not in f.parts]
        missing = []
        for f in files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    value = node.value
                    if KEY_LITERAL.match(value) and not value.endswith("_") and not value.endswith(FILE_SUFFIXES):
                        if value not in text_vi.KEYS:
                            missing.append(f"{f.relative_to(INSTALL_DIR)}: {value}")
        self.assertEqual(missing, [])
        for kind in download.KINDS:
            self.assertIn(f"core.download_{kind}", text_vi.KEYS)

    def test_every_catalog_is_built(self) -> None:
        self.assertEqual(sorted(catalog_modules()), sorted(text_vi.CATALOGS))

    def test_keyed_texts_equal_the_contract(self) -> None:
        for key, expected in KEYED.items():
            with self.subTest(key=key):
                self.assertIn(key, text_vi.TEXTS)
                self.assertEqual(normalize(text_vi.TEXTS[key]), normalize(expected))

    def test_step_titles(self) -> None:
        steps = importlib.import_module("thomhouse_installer.steps")
        self.assertEqual([s.n for s in steps.STEPS], list(range(1, 26)))
        for step in steps.STEPS:
            self.assertEqual(normalize(text_vi.t(step.title_key)), normalize(STEP_TITLES[step.n]), step.id)

    def test_doctor_labels(self) -> None:
        values = {normalize(v) for k, v in text_vi.TEXTS.items() if k.startswith("doctor.")}
        joined = "\n".join(text_vi.TEXTS[k] for k in text_vi.TEXTS if k.startswith("doctor."))
        for label in DOCTOR_LABELS:
            self.assertIn(normalize(label), values, label)
        for word in DOCTOR_STATUS_WORDS:
            self.assertIn(word, joined)

    def test_os_sentences(self) -> None:
        corpus = "\n".join(text_vi.TEXTS.values())
        for name in SHELL_TEMPLATES:
            corpus += "\n" + (INSTALL_DIR / name).read_text(encoding="utf-8")
        for sentence in OS_SENTENCES:
            self.assertIn(sentence, corpus)


class ShellTextTest(unittest.TestCase):
    def _check_file(self, path: Path, quoted_only: bool) -> None:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not VIET.search(line):
                continue
            pieces = re.findall(r'"([^"]*)"|\'([^\']*)\'', line) if quoted_only else [(line, "")]
            for a, b in pieces:
                piece = a or b
                if not VIET.search(piece):
                    continue
                with self.subTest(file=path.name, line=n):
                    self.assertFalse(FORBIDDEN_WORDS.search(piece), piece)
                    self.assertFalse(EMOJI.search(piece), piece)
                    self.assertLessEqual(len(piece), 100, piece)

    def test_shell_templates(self) -> None:
        found = [INSTALL_DIR / n for n in SHELL_TEMPLATES]
        for f in found:
            self._check_file(f, quoted_only=True)

    def test_note_beside_the_file(self) -> None:
        note = PROJECT_ROOT / "scripts" / "release" / "DOC-TRUOC.txt.in"
        self._check_file(note, quoted_only=False)
        self.assertIn("{version}", note.read_text(encoding="utf-8"))
