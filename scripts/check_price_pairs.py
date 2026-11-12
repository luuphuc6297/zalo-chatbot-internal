"""Check that every line mentioning a service name together with a price/duration uses a value
documented for that service in raw-content (canonical). Reports mismatches.

Usage: python3 -I scripts/check_price_pairs.py <drive_dir>
"""
import re, sys, unicodedata
from pathlib import Path

drive = Path(sys.argv[1])
# id -> (aliases regex, allowed prices, allowed durations)
S = {
 "mo-vai-nang-mat": (r"mở vai|vai cổ thông|nâng mặt", {350000, 389000}, {60}),
 "massage-chan": (r"massage chân(?! cơ bản)(?! thải)", {199000, 250000}, {30, 45}),
 "massage-co-vai-gay": (r"massage (cổ,? vai,? gáy|cổ vai gáy|vai cổ gáy)", {199000, 399000, 239000, 449000}, {30, 60}),
 "massage-body": (r"massage body", {429000, 499000, 569000}, {60, 75}),
 "dien-chan-ngua-dot-quy": (r"ngừa đột quỵ", {2990000}, {180}),
 "giai-moi-dung-lau": (r"giải mỏi đứng lâu|giãn tĩnh mạch", {599000}, {60}),
 "thieu-mau-nao": (r"thiếu máu não", {599000}, {60}),
 "dau-that-lung-moi-goi": (r"thắt lưng,? mỏi gối", {599000}, {60}),
 "detox-mui-co-the": (r"detox mùi", {1190000}, {90}),
 "thai-han-giai-cam": (r"thải hàn", {1200000}, {90}),
 "dau-bung-kinh": (r"đau bụng kinh", {599000}, {60}),
 "se-khit-yoni": (r"se khít", {2500000}, {45}),
 "yoni-retreat": (r"yoni retreat", {3500000}, {100}),
 "nan-chinh-san-chau": (r"sàn chậu", {500000}, {10}),
 "tieu-u-thong-kinh-nguc": (r"tiêu u|kinh ngực", {650000}, {60}),
 "goi-mun-chuyen-sau": (r"mụn chuyên sâu", {389000}, {75}),
 "goi-mun-5-in-1": (r"5 in 1", {599000}, {90}),
 "da-kich-ung": (r"da kích ứng", {599000}, {90}),
 "quang-mat-co-ban": (r"quầng mắt.*cơ bản|cơ bản.*quầng mắt", {329000}, {60}),
 "quang-mat-dien-xung": (r"điện xung trường", {629000}, {90}),
 "detox-da-dau": (r"detox da đầu", {139000, 159000}, {40}),
 "goi-dau-thu-gian": (r"gội đầu thư giãn", {199000, 229000}, {50}),
 "cham-soc-nan-toc": (r"nan tóc", {349000}, {70}),
}
money = re.compile(r"(?<![\w.,/])(\d{1,3}(?:[.,]\d{3}){1,2}|\d+(?:[.,]\d+)?(?:k|M|tr)\b)")
dur = re.compile(r"(\d{1,3})\s?(?:phút|p\b|')")

def vnd(t):
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3}){1,2}", t):
        return int(re.sub(r"[.,]", "", t))
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(k|M|tr)", t)
    v = float(m.group(1).replace(",", ".")); return int(round(v * (1e3 if m.group(2) == "k" else 1e6)))

files = sorted(drive.rglob("*.md")) + [drive / "thomhouse-knowledge-bundle.txt"]
issues = 0; checked = 0
for f in files:
    for n, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        line = unicodedata.normalize("NFC", raw).lower()
        hits = [sid for sid, (a, _, _) in S.items() if re.search(a, line)]
        if len(hits) != 1:
            continue  # skip lines naming 0 or several services (ambiguous)
        sid = hits[0]; _, prices, durs = S[sid]
        ps = [vnd(t) for t in money.findall(line)]
        ps = [p for p in ps if p >= 100000]
        ds = [int(d) for d in dur.findall(line)]
        if not ps and not ds:
            continue
        checked += 1
        badp = [p for p in ps if p not in prices]
        badd = [d for d in ds if d not in durs]
        if badp or badd:
            issues += 1
            print(f"{f.relative_to(drive)}:{n} [{sid}] badprice={badp} baddur={badd} :: {raw.strip()[:170]}")
print(f"checked lines: {checked}, flagged: {issues}")
