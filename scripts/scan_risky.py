"""List lines with potentially risky health/efficacy wording in the drive .md files.

Usage: python3 -I scripts/scan_risky.py <drive_dir> [category]
Prints path:line [categories] text. Categories are keyword buckets, not verdicts.
"""
import re, sys
from pathlib import Path

drive = Path(sys.argv[1]); only = sys.argv[2] if len(sys.argv) > 2 else None
CATS = {
 "disease": r"ung thư|u hạch|tuyến giáp|đột quỵ|sa tử cung|khó có thai|sảy thai|vô sinh|tụt huyết áp|huyết áp|tiểu đường|tĩnh mạch|thiếu máu não|viêm nhiễm|khí hư|trầm cảm|mất ngủ|tim mạch|xương khớp|thoát vị|gout|tai biến",
 "cure": r"chữa|dứt điểm|khỏi hẳn|khỏi bệnh|điều trị|trị liệu|đặc trị|tiêu u|bày trừ|giảm ngay|hết (đau|mụn|rụng|thâm)|phục hồi bệnh",
 "efficacy_number": r"\d+\s?(lần|%)|gấp \d+|\d+/\d+ (dịch vụ|khách)",
 "tech_claim": r"collagen|khử khuẩn|plasma|SHR|điện xung|tế bào gốc|whitetox|ion|ánh sáng xanh|kích mọc|mọc tóc|đen tóc|thải độc|độc tố|bạch huyết",
 "aftercare": r"sau (buổi|liệu trình|khi làm)|phản ứng|bình thường|đầy hơi|chướng|ê ẩm|bầm|tím|đỏ da|mệt (hơn|nhẹ)|uống nhiều nước|kiêng|không tắm|tắm",
 "contra": r"mang thai|có thai|bầu|kinh nguyệt đang|đang hành kinh|sau sinh|chống chỉ định|không dành cho|không áp dụng|thận trọng|cấy ghép|máy tạo nhịp|vết thương|ung thư",
}
for f in sorted(drive.rglob("*.md")):
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        cats = [c for c, p in CATS.items() if re.search(p, line, re.I)]
        if only:
            cats = [c for c in cats if c == only]
        if cats:
            print(f"{f.relative_to(drive)}:{n} [{','.join(cats)}] {line.strip()[:200]}")
