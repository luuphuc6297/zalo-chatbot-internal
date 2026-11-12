"""Scan all drive .md files for money amounts; report amounts not in the canonical raw-menu price set.

Usage: python3 -I scripts/scan_prices.py <drive_dir> [--all]
"""
import re, sys
from pathlib import Path
from collections import Counter, defaultdict

drive = Path(sys.argv[1])
show_all = "--all" in sys.argv
CANON = {350000, 389000, 199000, 250000, 399000, 239000, 449000, 429000, 499000, 569000,
         2990000, 599000, 1190000, 1200000, 2500000, 3500000, 500000, 650000,
         329000, 629000, 139000, 159000, 229000, 349000}
pat = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3}){1,2}|\d+(?:[.,]\d+)?\s?(?:k|K|M|tr|triệu|nghìn|ngàn)\b)(\s?(?:VNĐ|VND|đ|₫))?")

def to_vnd(tok):
    t = tok.replace(" ", "")
    m = re.fullmatch(r"(\d{1,3}(?:[.,]\d{3}){1,2})", t)
    if m:
        return int(re.sub(r"[.,]", "", t))
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(k|K|M|tr|triệu|nghìn|ngàn)", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        mult = {"k": 1e3, "K": 1e3, "nghìn": 1e3, "ngàn": 1e3, "M": 1e6, "tr": 1e6, "triệu": 1e6}[m.group(2)]
        return int(round(v * mult))
    return None

files = sorted(p for p in drive.rglob("*.md")) + [drive / "thomhouse-knowledge-bundle.txt"]
noncanon = defaultdict(list)
counts = Counter()
for f in files:
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        for m in pat.finditer(line):
            v = to_vnd(m.group(1))
            if v is None or v < 10000:
                continue
            counts[v] += 1
            if v not in CANON or show_all:
                noncanon[v].append(f"{f.relative_to(drive)}:{n}: {line.strip()[:160]}")
for v in sorted(noncanon):
    print(f"== {v:,} ({len(noncanon[v])} hits)")
    for h in noncanon[v][:8]:
        print("   ", h)
