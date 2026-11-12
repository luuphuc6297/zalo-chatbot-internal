// Customer status from the real visit history (docs/contracts.md section 14.6). Pure: no Env, no clock, no I/O.
//
// Everything is counted on local dates of the studio (Asia/Ho_Chi_Minh, lib/time.ts): a customer who had three services
// on one day made one visit, and a visit at 23:50 and one at 00:10 the next morning are two visit days one day apart.
// "Long absent" is measured against the customer's own rhythm (the median gap between visit days), never a fixed number
// of days: a monthly customer is absent after about two months, a weekly customer after about two weeks.
import { DAY_MS, TZ_OFFSET_MS, localMidnight } from './time';

export interface VisitFact {
  visited_at: number;
  service_id: string;
  amount_vnd: number | null;
}

export interface StatusConfig {
  /** absent_after_days = round(absentFactor x usual_gap_days), never below minAbsentDays. */
  absentFactor: number;
  minAbsentDays: number;
  /** usual gap of a customer with a single visit day when no peer gap is given. */
  defaultGapDays: number;
  /** length of the "recent" window in days. */
  windowDays: number;
}

export const DEFAULT_STATUS_CONFIG: StatusConfig = { absentFactor: 2, minAbsentDays: 14, defaultGapDays: 45, windowDays: 183 };

export type CustomerStatus = 'first_inquiry' | 'first_visit_done' | 'returning' | 'long_absent';

export interface ServiceCount {
  service_id: string;
  count: number;
}

export interface CustomerStatusResult {
  status: CustomerStatus;
  /** number of visit days (local dates with at least one visit row). */
  visits_total: number;
  last_visit_at: number | null;
  days_since_last_visit: number | null;
  usual_gap_days: number | null;
  gap_basis: 'own' | 'service_peers' | 'default' | null;
  absent_after_days: number | null;
  window: {
    days: number;
    /** UTC ms of local midnight of the first local date of the window. */
    from: number;
    visits: number;
    spend_vnd: number;
    spend_visits: number;
    avg_spend_vnd: number | null;
    services: ServiceCount[];
  };
  lifetime: { spend_vnd: number; spend_visits: number; services: ServiceCount[] };
}

/** Number of the local date that contains `ms` (days since 1970-01-01 local). Consecutive dates differ by 1. */
export function localDayNumber(ms: number): number {
  return Math.round((localMidnight(ms) + TZ_OFFSET_MS) / DAY_MS);
}

/** Median of a list of numbers: the middle value, or the mean of the two middle values. null for an empty list. */
export function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 1 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

/**
 * Median gap, in days, between consecutive visit days. `dayNumbers` are local day numbers (localDayNumber) in any
 * order, duplicates allowed. null with fewer than two different days.
 */
export function medianGapDays(dayNumbers: number[]): number | null {
  const days = [...new Set(dayNumbers)].sort((a, b) => a - b);
  if (days.length < 2) return null;
  const gaps: number[] = [];
  for (let i = 1; i < days.length; i++) gaps.push(days[i]! - days[i - 1]!);
  return median(gaps);
}

const knownAmount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;

interface DayFacts {
  day: number;
  services: Set<string>;
  spend: number;
  hasAmount: boolean;
}

/**
 * Visit rows grouped into visit days, oldest first. Rows with the same visited_at and service_id are one row (a
 * double import, or a visit recorded twice): the known amount is kept, the larger one when both are known, so the
 * result does not depend on the order of the input. Rows without a usable time are ignored.
 */
function groupByDay(visits: VisitFact[]): DayFacts[] {
  const rows = new Map<string, VisitFact>();
  for (const v of visits) {
    if (!v || typeof v.visited_at !== 'number' || !Number.isFinite(v.visited_at)) continue;
    const serviceId = String(v.service_id ?? '');
    const key = `${v.visited_at}|${serviceId}`;
    const amount = knownAmount(v.amount_vnd) ? v.amount_vnd : null;
    const prev = rows.get(key);
    if (!prev) rows.set(key, { visited_at: v.visited_at, service_id: serviceId, amount_vnd: amount });
    else if (amount !== null && (prev.amount_vnd === null || amount > prev.amount_vnd)) prev.amount_vnd = amount;
  }
  const days = new Map<number, DayFacts>();
  for (const r of rows.values()) {
    const day = localDayNumber(r.visited_at);
    let d = days.get(day);
    if (!d) {
      d = { day, services: new Set(), spend: 0, hasAmount: false };
      days.set(day, d);
    }
    d.services.add(r.service_id);
    if (r.amount_vnd !== null) {
      d.spend += r.amount_vnd;
      d.hasAmount = true;
    }
  }
  return [...days.values()].sort((a, b) => a.day - b.day);
}

function totals(days: DayFacts[]): { visits: number; spend_vnd: number; spend_visits: number; avg_spend_vnd: number | null; services: ServiceCount[] } {
  let spend = 0;
  let spendVisits = 0;
  const counts = new Map<string, number>();
  for (const d of days) {
    if (d.hasAmount) {
      spend += d.spend;
      spendVisits += 1;
    }
    for (const s of d.services) counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  const services = [...counts.entries()]
    .map(([service_id, count]) => ({ service_id, count }))
    .sort((a, b) => b.count - a.count || (a.service_id < b.service_id ? -1 : a.service_id > b.service_id ? 1 : 0));
  return { visits: days.length, spend_vnd: spend, spend_visits: spendVisits, avg_spend_vnd: spendVisits ? Math.round(spend / spendVisits) : null, services };
}

function resolveConfig(over?: Partial<StatusConfig>): StatusConfig {
  const pos = (v: unknown, fallback: number) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : fallback);
  const d = DEFAULT_STATUS_CONFIG;
  const minAbsent = over?.minAbsentDays;
  return {
    absentFactor: pos(over?.absentFactor, d.absentFactor),
    // 0 is allowed: no floor
    minAbsentDays: typeof minAbsent === 'number' && Number.isFinite(minAbsent) && minAbsent >= 0 ? minAbsent : d.minAbsentDays,
    defaultGapDays: pos(over?.defaultGapDays, d.defaultGapDays),
    windowDays: Math.max(1, Math.floor(pos(over?.windowDays, d.windowDays))),
  };
}

/**
 * Status of one customer from the visit rows. `visits` may be unsorted and may hold duplicate rows. `now` is ms.
 *
 * Rules (all on local dates):
 *  1. A visit day is a local date with at least one visit row. Several services on one day are one visit.
 *     `visits_total` counts visit days.
 *  2. No visit day: `first_inquiry`, every gap field is null.
 *  3. A gap is the number of days between two consecutive visit days. `usual_gap_days` is the median of the
 *     customer's own gaps (`own`, the mean of the two middle gaps when their number is even). With a single visit day
 *     it is `opts.peerGapDays` when given (`service_peers`), else `defaultGapDays` (`default`).
 *  4. `absent_after_days = max(minAbsentDays, round(absentFactor x usual_gap_days))`.
 *  5. `days_since_last_visit > absent_after_days`: `long_absent`. Otherwise one visit day is `first_visit_done`, two
 *     or more are `returning`.
 *  6. Window: the visit days from the local date of `now - windowDays` to the local date of `now`, both included (a
 *     window of 183 days covers 184 local dates). `spend_vnd` sums the known amounts (null =
 *     unknown, never counted as 0), `spend_visits` counts the visit days with a known amount,
 *     `avg_spend_vnd = round(spend_vnd / spend_visits)` or null. A service counts once per visit day it was used on,
 *     `services` is sorted by count (highest first), then by service_id. `lifetime` is the same over all visits.
 *
 * Invalid config values (not a positive number) fall back to DEFAULT_STATUS_CONFIG, an invalid peer gap to the default
 * gap. Never throws and never reads the database, so a missing migration 0010 does not concern it.
 */
export function computeCustomerStatus(
  visits: VisitFact[],
  now: number,
  opts?: { config?: Partial<StatusConfig>; peerGapDays?: number | null },
): CustomerStatusResult {
  const cfg = resolveConfig(opts?.config);
  const days = groupByDay(Array.isArray(visits) ? visits : []);
  const from = localMidnight(now - cfg.windowDays * DAY_MS);
  const fromDay = localDayNumber(from);
  const nowDay = localDayNumber(now);
  const w = totals(days.filter((d) => d.day >= fromDay && d.day <= nowDay));
  const all = totals(days);
  const window = { days: cfg.windowDays, from, visits: w.visits, spend_vnd: w.spend_vnd, spend_visits: w.spend_visits, avg_spend_vnd: w.avg_spend_vnd, services: w.services };
  const lifetime = { spend_vnd: all.spend_vnd, spend_visits: all.spend_visits, services: all.services };

  if (!days.length) {
    return {
      status: 'first_inquiry',
      visits_total: 0,
      last_visit_at: null,
      days_since_last_visit: null,
      usual_gap_days: null,
      gap_basis: null,
      absent_after_days: null,
      window,
      lifetime,
    };
  }

  let lastVisitAt = -Infinity;
  for (const v of visits) if (v && typeof v.visited_at === 'number' && Number.isFinite(v.visited_at) && v.visited_at > lastVisitAt) lastVisitAt = v.visited_at;
  const lastDay = days[days.length - 1]!.day;
  const daysSince = Math.max(0, nowDay - lastDay);

  let usualGap: number;
  let basis: 'own' | 'service_peers' | 'default';
  const own = medianGapDays(days.map((d) => d.day));
  const peer = opts?.peerGapDays;
  if (own !== null) {
    usualGap = own;
    basis = 'own';
  } else if (typeof peer === 'number' && Number.isFinite(peer) && peer > 0) {
    usualGap = peer;
    basis = 'service_peers';
  } else {
    usualGap = cfg.defaultGapDays;
    basis = 'default';
  }
  const absentAfter = Math.max(cfg.minAbsentDays, Math.round(cfg.absentFactor * usualGap));
  const status: CustomerStatus = daysSince > absentAfter ? 'long_absent' : days.length === 1 ? 'first_visit_done' : 'returning';

  return {
    status,
    visits_total: days.length,
    last_visit_at: lastVisitAt,
    days_since_last_visit: daysSince,
    usual_gap_days: usualGap,
    gap_basis: basis,
    absent_after_days: absentAfter,
    window,
    lifetime,
  };
}
