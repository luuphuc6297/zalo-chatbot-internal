// Owner: server-core. Deterministic pre-send checker (design/system-prompt-draft.md "Server kiểm gì trước khi
// gửi bản nháp?" rules 1-5; rule 6 state check happens at send time). Ports deterministic_checks from
// scripts/eval/run_eval.py. Pure function: no D1 access here, the caller builds CheckerInput (see ./input.ts).
import type { CheckerInput, CheckerIssue, CheckerResult } from '../types';
import { isLetterOrDigit, lowerNfc, stripMarksAligned } from '../lib/text';
import { menuImageIssues } from './attachments';

export const MAX_DRAFT_CHARS = 1800;

/** H4 of block A plus the "trị" ban; matched without diacritics (see findTerm for the collision rule). */
export const FORBIDDEN_TERMS = [
  'điều trị', 'trị bệnh', 'trị liệu', 'chữa', 'chữa khỏi', 'đặc trị', 'bài thuốc', 'châm cứu', 'kê toa', 'thay thế thuốc',
  'đảm bảo', 'cam kết hiệu quả', '100%', 'khỏi hẳn', 'dứt điểm', 'thải độc', 'độc tố', 'gấp 20 lần', 'tốt nhất', 'duy nhất',
  'số một', 'trị',
];

/** Ordinary phrases that contain a forbidden word ("giá trị" = value). Removed before the forbidden-term scan. */
const ALLOWED_PHRASES = ['giá trị', 'trị giá'];

export const BOOKING_PROMISES = [
  'đã đặt lịch thành công', 'đặt lịch thành công', 'đã giữ chỗ', 'chắc chắn có chỗ', 'đã xác nhận lịch', 'lịch đã được xác nhận',
  'đã chốt lịch',
];

/**
 * Money amounts written with digits: any number with 4+ digits or with thousands separators (. , or space),
 * unit optional ("150000đ", "150,000đ", "150.000", "150 000 đồng"). Compared by digits with tool price_texts.
 * Group 1 = the number, group 2 = the unit (if any).
 */
const AMOUNT_RE = /(?<![\p{L}\p{N}.,/:])(\d{1,3}(?:[.,]\d{3})+|\d{1,3}(?: \d{3})+(?=\s?(?:đồng|đ|vnđ|vnd)(?![\p{L}\p{N}]))|\d{4,})(?:\s?(đồng|đ|vnđ|vnd))?(?![\p{L}\p{N}/:]|[.,]\d)/giu;
/** k / nghìn / triệu forms: always fail (the model must copy price_text). */
const K_PRICE_RE = /\d+(?:[.,]\d+)?\s?(k|nghìn|ngàn|triệu|tr)(?![\p{L}\p{N}])/giu;

const PHONE_RE = /(?<![\p{N}])(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?![\p{N}])/gu;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const URL_RE =
  /\b(?:https?:\/\/[^\s<>"]+|www\.[^\s<>"]+|(?:[a-z0-9-]+\.)+(?:com|vn|net|org|ai|gl|me|io|info|biz|co|app|link|ly|page|site|online|store|shop)(?:\/[^\s<>"]*)?)/gi;

function priceDigits(s: string): string {
  return s.replace(/\D/g, '');
}

function normUrl(s: string): string {
  return s.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/[).,;!?]+$/, '').replace(/\/+$/, '');
}

function digits(s: string): string {
  return s.replace(/\D/g, '').replace(/^84/, '0');
}

/**
 * Finds a forbidden term after removing diacritics and case, with word boundaries. A match whose original span
 * carries diacritics different from the term is not a hit ("chưa" is not "chữa", "vị trí" is not "trị"); a
 * span written without any diacritics is a hit ("chua khoi"), as the rule asks.
 */
export function findTerm(text: string, term: string): string | null {
  const orig = lowerNfc(text);
  const flat = stripMarksAligned(orig);
  const t = lowerNfc(term);
  const tFlat = stripMarksAligned(t);
  let from = 0;
  for (;;) {
    const i = flat.indexOf(tFlat, from);
    if (i < 0) return null;
    from = i + 1;
    const before = orig[i - 1];
    const after = orig[i + tFlat.length];
    const startsWithDigit = /\d/.test(tFlat[0] ?? '');
    if (startsWithDigit ? before !== undefined && /[\d.,]/.test(before) : isLetterOrDigit(before)) continue;
    if (/[\p{L}\p{N}]/u.test(tFlat.at(-1) ?? '') && isLetterOrDigit(after)) continue;
    const span = orig.slice(i, i + tFlat.length);
    if (span === t || span === tFlat) return text.normalize('NFC').slice(i, i + tFlat.length);
  }
}

export function checkDraft(input: CheckerInput, now: number = Date.now()): CheckerResult {
  const issues: CheckerIssue[] = [];
  const text = (input.text ?? '').normalize('NFC');

  if (!text.trim()) {
    issues.push({ rule: 'empty', detail: 'draft is empty' });
    return { passed: false, issues, checked_at: now };
  }
  if (text.length > MAX_DRAFT_CHARS) {
    issues.push({ rule: 'length', detail: `draft has ${text.length} characters (max ${MAX_DRAFT_CHARS})` });
  }

  // Rule 3: plain text only.
  for (const [mark, detail] of [
    ['**', 'bold markdown'],
    ['__', 'underline markdown'],
    ['```', 'code fence'],
    ['`', 'backtick'],
    ['|', 'table pipe'],
  ] as const) {
    if (text.includes(mark)) {
      issues.push({ rule: 'format', detail, excerpt: mark });
      if (mark === '```') break;
    }
  }
  if (/^\s*#/m.test(text)) issues.push({ rule: 'format', detail: 'heading (# at line start)', excerpt: '#' });
  if (/\[[^\]]+\]\([^)]+\)/.test(text)) issues.push({ rule: 'format', detail: 'markdown link' });

  // Rule 1: every money amount must equal a price_text returned by a tool in this conversation.
  // Phone numbers, URLs and emails are judged by rule 4; a bare 4-digit year (19xx/20xx, no unit) is not money.
  const allowed = new Set(input.allowed_price_texts.map(priceDigits).filter(Boolean));
  const skipSpans = [...text.matchAll(PHONE_RE), ...text.matchAll(EMAIL_RE), ...text.matchAll(URL_RE)].map((m) => [m.index!, m.index! + m[0].length] as const);
  const inSkip = (a: number, b: number) => skipSpans.some(([s, e]) => a < e && b > s);
  for (const m of text.matchAll(AMOUNT_RE)) {
    const raw = m[0];
    if (inSkip(m.index!, m.index! + raw.length)) continue;
    if (!m[2] && /^(19|20)\d{2}$/.test(m[1]!)) continue;
    if (!allowed.has(priceDigits(m[1]!))) issues.push({ rule: 'price', detail: 'price not returned by a tool in this conversation', excerpt: raw });
  }
  for (const m of text.matchAll(K_PRICE_RE)) {
    issues.push({ rule: 'price', detail: 'k / nghìn / triệu amounts are not allowed; copy price_text', excerpt: m[0] });
  }

  // Rule 2: forbidden terms, except inside an exact display_name_vi of the active catalog.
  let scrubbed = text;
  for (const name of [...input.display_names].sort((a, b) => b.length - a.length)) {
    if (name) scrubbed = scrubbed.split(name.normalize('NFC')).join(' '.repeat(name.normalize('NFC').length));
  }
  for (const ok of ALLOWED_PHRASES) scrubbed = scrubbed.replace(new RegExp(ok, 'giu'), (m) => ' '.repeat(m.length));
  for (const term of FORBIDDEN_TERMS) {
    const hit = findTerm(scrubbed, term);
    if (hit) issues.push({ rule: 'forbidden_term', detail: `forbidden term "${term}"`, excerpt: hit });
  }

  // Rule 4: contact info only from approved facts.
  const approvedDigits = new Set(input.approved_contact_values.map(digits).filter((d) => d.length >= 9));
  const approvedUrls = new Set(input.approved_contact_values.map(normUrl));
  for (const m of text.matchAll(PHONE_RE)) {
    if (!approvedDigits.has(digits(m[0]))) issues.push({ rule: 'contact_info', detail: 'phone number not in approved facts', excerpt: m[0] });
  }
  const emails = [...text.matchAll(EMAIL_RE)].map((m) => m[0]);
  for (const e of emails) {
    if (!approvedUrls.has(normUrl(e))) issues.push({ rule: 'contact_info', detail: 'email not in approved facts', excerpt: e });
  }
  for (const m of text.matchAll(URL_RE)) {
    if (emails.some((e) => e.includes(m[0]))) continue;
    if (!approvedUrls.has(normUrl(m[0]))) issues.push({ rule: 'contact_info', detail: 'URL not in approved facts', excerpt: m[0] });
  }

  // Rule 5: no booking confirmation promises.
  for (const p of BOOKING_PROMISES) {
    const hit = findTerm(text, p);
    if (hit) {
      issues.push({ rule: 'booking_promise', detail: 'bookings are requests; staff confirm', excerpt: hit });
      break;
    }
  }

  // Menu images attached to the draft: known slides only, at most 10, none that prints a health claim.
  if (input.attachment_keys?.length) issues.push(...menuImageIssues(input.attachment_keys));

  return { passed: issues.length === 0, issues, checked_at: now };
}
