// Owner: server-zalo. Local-time window for proactive (scheduled) sends, Asia/Ho_Chi_Minh (UTC+7, no DST).
// Default 09:00 (inclusive) to 19:00 (exclusive), override with env PROACTIVE_SEND_HOURS="9-19".
// This is stricter than Zalo's own limits (ZBS Tag 2/3: 7h-22h from 15/10/2026, research/03) and than the
// 9h-20h window in design/followup-templates.md; the owner can widen it with the env var.
import type { Env } from '../types';
import { TZ_OFFSET_MS } from '../lib/time';

export interface SendWindow {
  startHour: number; // inclusive
  endHour: number; // exclusive
}

export const DEFAULT_SEND_WINDOW: SendWindow = { startHour: 9, endHour: 19 };

export function sendWindow(env: Pick<Env, 'PROACTIVE_SEND_HOURS'>): SendWindow {
  const m = /^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$/.exec(env.PROACTIVE_SEND_HOURS ?? '');
  if (!m) return DEFAULT_SEND_WINDOW;
  const startHour = Number(m[1]);
  const endHour = Number(m[2]);
  if (startHour < 0 || endHour > 24 || startHour >= endHour) return DEFAULT_SEND_WINDOW;
  return { startHour, endHour };
}

/** Local hour + minutes as a fraction, e.g. 18.5 for 18:30 local. */
export function localHour(ms: number): number {
  const d = new Date(ms + TZ_OFFSET_MS);
  return d.getUTCHours() + d.getUTCMinutes() / 60;
}

export function isWithinSendWindow(ms: number, w: SendWindow = DEFAULT_SEND_WINDOW): boolean {
  const h = localHour(ms);
  return h >= w.startHour && h < w.endHour;
}

/** The next moment the window opens (today if before the start, otherwise tomorrow). */
export function nextWindowStart(ms: number, w: SendWindow = DEFAULT_SEND_WINDOW): number {
  const d = new Date(ms + TZ_OFFSET_MS);
  const dayOffset = localHour(ms) < w.startHour ? 0 : 1;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + dayOffset, w.startHour) - TZ_OFFSET_MS;
}

/** dd/MM/yyyy in local time (format used by the ZBS templates in design/followup-templates.md). */
export function formatLocalDate(ms: number): string {
  const d = new Date(ms + TZ_OFFSET_MS);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`;
}
