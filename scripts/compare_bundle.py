"""Compare each section of thomhouse-knowledge-bundle.txt with its source .md file.

Usage: python3 -I scripts/compare_bundle.py <drive_dir> [--detail]
Normalizes markdown/plain-text formatting, then diffs normalized line lists.
"""
import difflib, re, sys, unicodedata
from pathlib import Path

drive = Path(sys.argv[1])
detail = "--detail" in sys.argv
bundle = (drive / "thomhouse-knowledge-bundle.txt").read_text(encoding="utf-8").splitlines()

def norm(line):
    s = unicodedata.normalize("NFC", line).lower()
    s = s.replace("\\", "")
    s = re.sub(r"[*_`#>|]", " ", s)
    s = re.sub(r"^\s*[-•]\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if re.fullmatch(r"[-=:\s]*", s):
        return ""
    return s

# locate sections
heads = [(i, bundle[i + 1]) for i, l in enumerate(bundle) if re.match(r"^### \d{2}\. ", l) and i + 1 < len(bundle) and bundle[i + 1].startswith("### Nguồn:")]
sections = []
for k, (i, src) in enumerate(heads):
    end = heads[k + 1][0] if k + 1 < len(heads) else len(bundle)
    rel = src.split("Nguồn:")[1].strip().replace(".txt", ".md")
    sections.append((bundle[i], rel, i + 1, end))

total_b = total_m = 0
for title, rel, start, end in sections:
    md_path = drive / rel
    b_lines = [(n, norm(l)) for n, l in enumerate(bundle[start + 1:end], start=start + 2)]
    b_lines = [(n, s) for n, s in b_lines if s]
    if not md_path.exists():
        print(f"{title} | {rel} | MISSING md")
        continue
    m_raw = md_path.read_text(encoding="utf-8").splitlines()
    m_lines = [(n, norm(l)) for n, l in enumerate(m_raw, start=1)]
    m_lines = [(n, s) for n, s in m_lines if s]
    sm = difflib.SequenceMatcher(None, [s for _, s in b_lines], [s for _, s in m_lines], autojunk=False)
    only_b = only_m = 0
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        bseg = b_lines[i1:i2]; mseg = m_lines[j1:j2]
        # treat whitespace/punct-insensitive equality as equal
        bj = re.sub(r"\W", "", "".join(s for _, s in bseg)); mj = re.sub(r"\W", "", "".join(s for _, s in mseg))
        if bj == mj:
            continue
        only_b += len(bseg); only_m += len(mseg)
        out.append((tag, bseg, mseg))
    print(f"{title[4:60]:<58} | {rel:<52} | bundle {start+1}-{end} | b={len(b_lines)} md={len(m_lines)} | ratio={sm.ratio():.3f} | diff_b={only_b} diff_md={only_m}")
    if detail:
        for tag, bseg, mseg in out:
            print(f"   [{tag}]")
            for n, s in bseg[:6]: print(f"     B{n}: {s[:150]}")
            for n, s in mseg[:6]: print(f"     M{n}: {s[:150]}")
