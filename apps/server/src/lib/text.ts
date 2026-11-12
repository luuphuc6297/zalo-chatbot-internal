// Owner: server-core. Text helpers shared by tools, checker and prompt builders.

/** Lowercase and strip Vietnamese diacritics one character at a time, so the output has the same length
 *  (in UTF-16 code units) as the NFC-lowercased input. Positions in both strings line up. */
export function stripMarksAligned(s: string): string {
  let out = '';
  for (const ch of s.normalize('NFC').toLowerCase()) {
    if (ch === 'đ') {
      out += 'd';
      continue;
    }
    const base = ch.normalize('NFD').replace(/\p{Mn}/gu, '');
    // Keep 1:1 alignment: a precomposed letter becomes exactly one base letter.
    out += base.length === ch.length ? base : ch;
  }
  return out;
}

export function lowerNfc(s: string): string {
  return s.normalize('NFC').toLowerCase();
}

/** Same as stripMarksAligned but not guaranteed aligned; for search only. */
export function stripMarks(s: string): string {
  return stripMarksAligned(s);
}

/** 199000 -> "199.000đ" (format of price_text everywhere). */
export function fmtVnd(n: number): string {
  return `${Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.')}đ`;
}

/** "20:30" -> 1230; anything else -> null. */
export function hhmmToMin(s: string | null | undefined): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s ?? '');
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return null;
  return h * 60 + mi;
}

export function isLetterOrDigit(ch: string | undefined): boolean {
  return ch !== undefined && /[\p{L}\p{N}]/u.test(ch);
}

/** Deterministic JSON: object keys sorted recursively. Used for idempotency keys. */
export function canonicalJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(',')}]`;
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    return `{${Object.keys(o)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${canonicalJson(o[k])}`)
      .join(',')}}`;
  }
  return JSON.stringify(v ?? null);
}

export async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Untrusted short text (e.g. Zalo display name) made safe to embed in a prompt line. */
export function oneLine(s: string | null | undefined, max = 60): string {
  return (s ?? '')
    .replace(/[\r\n\t]+/g, ' ')
    .replace(/[<>"]/g, '')
    .trim()
    .slice(0, max);
}
