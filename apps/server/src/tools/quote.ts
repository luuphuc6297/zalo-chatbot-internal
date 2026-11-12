// Owner: server-core. Pure quote_price rules (port of MockTools.quote_price in scripts/eval/run_eval.py plus
// x_server_policy.quote_price in design/tools-schema.json). No D1 access; the caller passes the variants.
import { fmtVnd, hhmmToMin } from '../lib/text';

export interface QuoteVariant {
  duration_min: number;
  time_window: string | null; // '09:00-20:30' | 'after_20:30' | '09:00-24:00' | null
  price_vnd: number;
}

export interface QuoteInput {
  service_id: string;
  duration_min: number;
  start_time_local: string; // 'HH:MM' | 'unknown'
  date_local: string; // 'YYYY-MM-DD' | 'unknown'
}

const DAY = '09:00-20:30';
const NIGHT = 'after_20:30';
const FOOT = '09:00-24:00';
const OPEN_MIN = 9 * 60;
const BOUNDARY_MIN = 20 * 60 + 30;
const FOOT_CLOSE_MIN = 24 * 60;

const cand = (condition_vi: string, v: QuoteVariant, extra: Record<string, unknown> = {}) => ({
  condition_vi,
  duration_min: v.duration_min,
  time_window: v.time_window,
  price_vnd: v.price_vnd,
  price_text: fmtVnd(v.price_vnd),
  ...extra,
});

/** Returns the tool result object (status ok | ambiguous | needs_time | outside_known_hours | invalid_duration | all_durations). */
export function quotePrice(input: QuoteInput, variants: QuoteVariant[], catalogVersion: string): Record<string, unknown> {
  const base = {
    service_id: input.service_id,
    start_time_local: input.start_time_local,
    date_local: input.date_local,
    catalog_version_id: catalogVersion,
  };
  const durations = [...new Set(variants.map((v) => v.duration_min))].sort((a, b) => a - b);
  let duration = input.duration_min;
  if (duration === 0) {
    if (durations.length !== 1) {
      return {
        ...base,
        status: 'all_durations',
        duration_min: 0,
        valid_durations: durations,
        candidates: variants.map((v) =>
          cand(
            v.time_window === DAY ? `${v.duration_min} phút, khung 9h – 20h30` : v.time_window === NIGHT ? `${v.duration_min} phút, khung sau 20h30` : `${v.duration_min} phút`,
            v,
          ),
        ),
      };
    }
    duration = durations[0]!;
  }
  const vs = variants.filter((v) => v.duration_min === duration);
  if (!vs.length) {
    return { ...base, status: 'invalid_duration', duration_min: duration, valid_durations: durations };
  }
  const t = hhmmToMin(input.start_time_local);
  const day = vs.find((v) => v.time_window === DAY);
  const night = vs.find((v) => v.time_window === NIGHT);

  // Single-price services (no day/night pair): foot massage window, or no time window at all.
  if (!day || !night) {
    const v = vs[0]!;
    if (v.time_window === FOOT) {
      const res = { ...base, duration_min: duration, price_vnd: v.price_vnd, price_text: fmtVnd(v.price_vnd), time_window: FOOT, rule: 'single price, window 09:00-24:00' };
      if (t !== null && (t < OPEN_MIN || t + duration > FOOT_CLOSE_MIN)) {
        return { ...res, status: 'outside_known_hours', candidates: [cand('khung 9h – 24h', v)] };
      }
      return { ...res, status: 'ok' };
    }
    const res: Record<string, unknown> = {
      ...base,
      status: 'ok',
      duration_min: duration,
      price_vnd: v.price_vnd,
      price_text: fmtVnd(v.price_vnd),
      time_window: v.time_window,
      rule: 'single price for this duration',
    };
    if (t !== null && t < OPEN_MIN) return { ...res, status: 'outside_known_hours', candidates: [cand('một giá', v)] };
    if (t !== null && t > BOUNDARY_MIN) res.hours_status = 'unconfirmed';
    return res;
  }

  const both = [cand('nếu tính theo khung 9h – 20h30', day), cand('nếu tính theo khung sau 20h30', night)];
  if (t === null) return { ...base, status: 'needs_time', duration_min: duration, candidates: both };
  if (t < OPEN_MIN) return { ...base, status: 'outside_known_hours', duration_min: duration, candidates: both };
  if (t === BOUNDARY_MIN || (t < BOUNDARY_MIN && t + duration > BOUNDARY_MIN)) {
    return {
      ...base,
      status: 'ambiguous',
      duration_min: duration,
      candidates: both,
      rule_status: 'unconfirmed',
      hours_status: 'unconfirmed',
      reason: t === BOUNDARY_MIN ? 'starts_exactly_at_20:30' : 'crosses_20:30',
      note: 'Studio chưa chốt cách tính giá ở mốc 20h30; nhân viên sẽ xác nhận.',
    };
  }
  if (t < BOUNDARY_MIN) {
    return { ...base, status: 'ok', duration_min: duration, price_vnd: day.price_vnd, price_text: fmtVnd(day.price_vnd), time_window: DAY };
  }
  return {
    ...base,
    status: 'ok',
    duration_min: duration,
    price_vnd: night.price_vnd,
    price_text: fmtVnd(night.price_vnd),
    time_window: NIGHT,
    hours_status: 'unconfirmed',
  };
}
