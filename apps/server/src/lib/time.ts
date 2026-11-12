// Owner: server-core. Time helpers. Studio time zone is Asia/Ho_Chi_Minh (UTC+7, no DST).
export const TZ = 'Asia/Ho_Chi_Minh';
export const TZ_OFFSET_MS = 7 * 3600 * 1000;
export const HOUR_MS = 3600 * 1000;
export const DAY_MS = 24 * HOUR_MS;
const WEEKDAYS_VI = ['Chủ nhật', 'thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy'];

export function nowMs(): number {
  return Date.now();
}

const p2 = (n: number) => String(n).padStart(2, '0');

/** "2026-11-07T19:42 Asia/Ho_Chi_Minh (thứ Bảy)" — the now_local format of block D. */
export function formatNowLocal(ms: number): string {
  const d = new Date(ms + TZ_OFFSET_MS);
  const s = `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
  return `${s} ${TZ} (${WEEKDAYS_VI[d.getUTCDay()]})`;
}

/** "2026-11-07T19:40" local, no zone (short stamps inside block D). */
export function formatLocalShort(ms: number): string {
  const d = new Date(ms + TZ_OFFSET_MS);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}

/** Local calendar date "YYYY-MM-DD". */
export function localDate(ms: number): string {
  const d = new Date(ms + TZ_OFFSET_MS);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
}

/** Minutes since local midnight. */
export function localMinuteOfDay(ms: number): number {
  const d = new Date(ms + TZ_OFFSET_MS);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

/** UTC ms of local midnight of the local day containing ms. */
export function localMidnight(ms: number): number {
  const local = ms + TZ_OFFSET_MS;
  return local - (((local % DAY_MS) + DAY_MS) % DAY_MS) - TZ_OFFSET_MS;
}

export function isValidLocalDate(s: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.getUTCFullYear() === Number(m[1]) && d.getUTCMonth() === Number(m[2]) - 1 && d.getUTCDate() === Number(m[3]);
}

export function envInt(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}
