// Customer status from the visit history (docs/contracts.md section 14.6, src/lib/customer-status.ts). Pure: no D1.
// Every time is written as a local time of the studio (Asia/Ho_Chi_Minh) and turned into ms by `at`.
import { describe, expect, it } from 'vitest';
import { DEFAULT_STATUS_CONFIG, computeCustomerStatus, localDayNumber, median, medianGapDays, type VisitFact } from '../src/lib/customer-status';
import { DAY_MS, TZ_OFFSET_MS, localDate, localMidnight } from '../src/lib/time';

/** 'YYYY-MM-DD', hour and minute in Asia/Ho_Chi_Minh -> ms. */
function at(date: string, hh = 10, mm = 0): number {
  const [y, m, d] = date.split('-').map(Number) as [number, number, number];
  return Date.UTC(y, m - 1, d, hh, mm) - TZ_OFFSET_MS;
}

const NOW = at('2026-11-12', 15, 0);
/** A visit `n` local days before NOW, at 10:00. */
const daysAgo = (n: number, service_id = 'goi-dau-thu-gian', amount_vnd: number | null = null): VisitFact => ({ visited_at: at('2026-11-12', 10, 0) - n * DAY_MS, service_id, amount_vnd });

describe('helpers', () => {
  it('localDayNumber counts local dates, not UTC dates', () => {
    // 23:50 local is 16:50 UTC of the same date, 00:10 local is 17:10 UTC of the date before
    expect(localDayNumber(at('2026-10-10', 0, 10)) - localDayNumber(at('2026-10-09', 23, 50))).toBe(1);
    expect(localDayNumber(at('2026-10-10', 0, 10))).toBe(localDayNumber(at('2026-10-10', 23, 50)));
    expect(new Date(at('2026-10-10', 0, 10)).toISOString().slice(0, 10)).toBe('2026-10-09');
    expect(localDayNumber(at('2026-03-01')) - localDayNumber(at('2026-02-28'))).toBe(1);
    expect(localDayNumber(at('2028-03-01')) - localDayNumber(at('2028-02-28'))).toBe(2); // leap year
  });

  it('median: the middle value, or the mean of the two middle values', () => {
    expect(median([])).toBeNull();
    expect(median([7])).toBe(7);
    expect(median([30, 10, 20])).toBe(20);
    expect(median([10, 20])).toBe(15);
    expect(median([8, 7])).toBe(7.5);
    expect(median([40, 10, 30, 20])).toBe(25);
    const input = [3, 1, 2];
    median(input);
    expect(input).toEqual([3, 1, 2]); // the input is not sorted in place
  });

  it('medianGapDays: gaps between different days, in any order', () => {
    expect(medianGapDays([])).toBeNull();
    expect(medianGapDays([100])).toBeNull();
    expect(medianGapDays([100, 100, 100])).toBeNull();
    expect(medianGapDays([100, 110])).toBe(10);
    expect(medianGapDays([160, 100, 130, 110])).toBe(20); // gaps 10, 20, 30
    expect(medianGapDays([130, 100, 110, 110])).toBe(15); // gaps 10, 20
  });
});

describe('computeCustomerStatus: status', () => {
  it('no visit: first_inquiry, every gap field null, empty sums', () => {
    const r = computeCustomerStatus([], NOW);
    expect(r).toEqual({
      status: 'first_inquiry',
      visits_total: 0,
      last_visit_at: null,
      days_since_last_visit: null,
      usual_gap_days: null,
      gap_basis: null,
      absent_after_days: null,
      window: { days: 183, from: localMidnight(NOW - 183 * DAY_MS), visits: 0, spend_vnd: 0, spend_visits: 0, avg_spend_vnd: null, services: [] },
      lifetime: { spend_vnd: 0, spend_visits: 0, services: [] },
    });
    expect(localDate(r.window.from)).toBe('2026-05-13');
  });

  it('one visit inside the threshold: first_visit_done on the default gap', () => {
    const r = computeCustomerStatus([daysAgo(10)], NOW);
    expect(r).toMatchObject({ status: 'first_visit_done', visits_total: 1, days_since_last_visit: 10, usual_gap_days: 45, gap_basis: 'default', absent_after_days: 90 });
    expect(r.last_visit_at).toBe(daysAgo(10).visited_at);
  });

  it('one visit: long_absent only when strictly more days than absent_after_days have passed', () => {
    expect(computeCustomerStatus([daysAgo(90)], NOW)).toMatchObject({ status: 'first_visit_done', days_since_last_visit: 90, absent_after_days: 90 });
    expect(computeCustomerStatus([daysAgo(91)], NOW)).toMatchObject({ status: 'long_absent', days_since_last_visit: 91, absent_after_days: 90, visits_total: 1 });
  });

  it('a visit today counts 0 days, whatever the hour', () => {
    const r = computeCustomerStatus([{ visited_at: at('2026-11-12', 0, 5), service_id: 'massage-chan', amount_vnd: null }], at('2026-11-12', 23, 55));
    expect(r).toMatchObject({ status: 'first_visit_done', days_since_last_visit: 0 });
    // yesterday 23:55 and today 00:05 are ten minutes apart and one day apart
    expect(computeCustomerStatus([{ visited_at: at('2026-11-11', 23, 55), service_id: 'massage-chan', amount_vnd: null }], at('2026-11-12', 0, 5)).days_since_last_visit).toBe(1);
  });

  it('several services on one local day are one visit', () => {
    const r = computeCustomerStatus(
      [
        { visited_at: at('2026-11-02', 9, 0), service_id: 'goi-dau-thu-gian', amount_vnd: 150000 },
        { visited_at: at('2026-11-02', 10, 30), service_id: 'massage-chan', amount_vnd: 250000 },
        { visited_at: at('2026-11-02', 21, 0), service_id: 'massage-body-thu-gian', amount_vnd: null },
      ],
      NOW,
    );
    expect(r).toMatchObject({ status: 'first_visit_done', visits_total: 1, usual_gap_days: 45, gap_basis: 'default', days_since_last_visit: 10 });
    expect(r.last_visit_at).toBe(at('2026-11-02', 21, 0));
    expect(r.window).toMatchObject({ visits: 1, spend_vnd: 400000, spend_visits: 1, avg_spend_vnd: 400000 });
    expect(r.window.services).toEqual([
      { service_id: 'goi-dau-thu-gian', count: 1 },
      { service_id: 'massage-body-thu-gian', count: 1 },
      { service_id: 'massage-chan', count: 1 },
    ]);
  });

  it('visits either side of local midnight are two visit days, one day apart', () => {
    const r = computeCustomerStatus(
      [
        { visited_at: at('2026-11-01', 23, 50), service_id: 'massage-chan', amount_vnd: 200000 },
        { visited_at: at('2026-11-02', 0, 10), service_id: 'massage-chan', amount_vnd: 200000 },
      ],
      NOW,
    );
    expect(r).toMatchObject({ visits_total: 2, usual_gap_days: 1, gap_basis: 'own', absent_after_days: 14, days_since_last_visit: 10, status: 'returning' });
    expect(r.window).toMatchObject({ visits: 2, spend_visits: 2, spend_vnd: 400000, avg_spend_vnd: 200000 });
    expect(r.window.services).toEqual([{ service_id: 'massage-chan', count: 2 }]);
  });

  it('the same local day stays one visit although the two rows fall on different UTC dates', () => {
    const r = computeCustomerStatus(
      [
        { visited_at: at('2026-11-02', 0, 10), service_id: 'massage-chan', amount_vnd: null },
        { visited_at: at('2026-11-02', 23, 50), service_id: 'goi-dau-thu-gian', amount_vnd: null },
      ],
      NOW,
    );
    expect(r).toMatchObject({ visits_total: 1, gap_basis: 'default', status: 'first_visit_done' });
  });

  it('usual gap: the median of an odd number of gaps', () => {
    // visit days 70, 60, 40, 10 days ago: gaps 10, 20, 30
    const r = computeCustomerStatus([daysAgo(70), daysAgo(60), daysAgo(40), daysAgo(10)], NOW);
    expect(r).toMatchObject({ visits_total: 4, usual_gap_days: 20, gap_basis: 'own', absent_after_days: 40, days_since_last_visit: 10, status: 'returning' });
  });

  it('usual gap: the mean of the two middle gaps for an even number of gaps', () => {
    // gaps 10, 20 -> 15
    expect(computeCustomerStatus([daysAgo(40), daysAgo(30), daysAgo(10)], NOW)).toMatchObject({ usual_gap_days: 15, absent_after_days: 30, status: 'returning' });
    // gaps 7, 8 -> 7.5, round(2 x 7.5) = 15
    expect(computeCustomerStatus([daysAgo(20), daysAgo(13), daysAgo(5)], NOW)).toMatchObject({ usual_gap_days: 7.5, absent_after_days: 15, status: 'returning' });
    // gaps 5, 10, 30, 100 -> 20: one very long break does not move the rhythm
    expect(computeCustomerStatus([daysAgo(150), daysAgo(145), daysAgo(135), daysAgo(105), daysAgo(5)], NOW)).toMatchObject({ usual_gap_days: 20, absent_after_days: 40 });
  });

  it('long absent follows the own rhythm, not a fixed number of days', () => {
    const monthly = (last: number) => computeCustomerStatus([daysAgo(last + 60), daysAgo(last + 30), daysAgo(last)], NOW);
    expect(monthly(45)).toMatchObject({ status: 'returning', usual_gap_days: 30, absent_after_days: 60, days_since_last_visit: 45 });
    expect(monthly(60)).toMatchObject({ status: 'returning' });
    expect(monthly(61)).toMatchObject({ status: 'long_absent', visits_total: 3 });
    // a customer who comes every 90 days is still on rhythm after 5 months
    expect(computeCustomerStatus([daysAgo(330), daysAgo(240), daysAgo(150)], NOW)).toMatchObject({ status: 'returning', usual_gap_days: 90, absent_after_days: 180 });
    // a weekly customer is absent after three weeks
    expect(computeCustomerStatus([daysAgo(35), daysAgo(28), daysAgo(21)], NOW)).toMatchObject({ status: 'long_absent', usual_gap_days: 7, absent_after_days: 14 });
  });

  it('minAbsentDays is the floor of absent_after_days', () => {
    // every 3 days: 2 x 3 = 6, raised to 14
    const everyThreeDays = (last: number) => computeCustomerStatus([daysAgo(last + 6), daysAgo(last + 3), daysAgo(last)], NOW);
    expect(everyThreeDays(14)).toMatchObject({ usual_gap_days: 3, absent_after_days: 14, status: 'returning' });
    expect(everyThreeDays(15)).toMatchObject({ absent_after_days: 14, status: 'long_absent' });
    expect(computeCustomerStatus([daysAgo(13), daysAgo(10), daysAgo(7)], NOW, { config: { minAbsentDays: 0 } })).toMatchObject({ absent_after_days: 6, status: 'long_absent' });
    expect(computeCustomerStatus([daysAgo(13), daysAgo(10), daysAgo(7)], NOW, { config: { minAbsentDays: 30 } })).toMatchObject({ absent_after_days: 30, status: 'returning' });
  });

  it('a single visit uses the peer gap when given, else the default gap', () => {
    expect(computeCustomerStatus([daysAgo(41)], NOW, { peerGapDays: 20 })).toMatchObject({ usual_gap_days: 20, gap_basis: 'service_peers', absent_after_days: 40, status: 'long_absent' });
    expect(computeCustomerStatus([daysAgo(40)], NOW, { peerGapDays: 20 })).toMatchObject({ gap_basis: 'service_peers', status: 'first_visit_done' });
    expect(computeCustomerStatus([daysAgo(41)], NOW, { peerGapDays: 22.5 })).toMatchObject({ usual_gap_days: 22.5, absent_after_days: 45, status: 'first_visit_done' });
    for (const peer of [null, undefined, 0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(computeCustomerStatus([daysAgo(41)], NOW, { peerGapDays: peer }), String(peer)).toMatchObject({ usual_gap_days: 45, gap_basis: 'default', absent_after_days: 90 });
    }
  });

  it('the peer gap is ignored once the customer has an own gap', () => {
    expect(computeCustomerStatus([daysAgo(40), daysAgo(10)], NOW, { peerGapDays: 5 })).toMatchObject({ usual_gap_days: 30, gap_basis: 'own', absent_after_days: 60 });
    expect(computeCustomerStatus([], NOW, { peerGapDays: 5 })).toMatchObject({ status: 'first_inquiry', usual_gap_days: null, gap_basis: null });
  });
});

describe('computeCustomerStatus: window and lifetime sums', () => {
  it('an unknown amount is never counted as 0', () => {
    const r = computeCustomerStatus(
      [
        // day A: one known amount and one unknown
        { visited_at: at('2026-10-01', 9), service_id: 'goi-dau-thu-gian', amount_vnd: 100000 },
        { visited_at: at('2026-10-01', 10), service_id: 'massage-chan', amount_vnd: null },
        // day B: unknown only
        { visited_at: at('2026-10-15', 9), service_id: 'goi-dau-thu-gian', amount_vnd: null },
        // day C: known
        { visited_at: at('2026-11-01', 9), service_id: 'goi-dau-thu-gian', amount_vnd: 300000 },
        // day D: a free visit, 0 is a known amount
        { visited_at: at('2026-11-05', 9), service_id: 'massage-chan', amount_vnd: 0 },
        // long before the window
        { visited_at: at('2025-01-10', 9), service_id: 'massage-body-thu-gian', amount_vnd: 900000 },
      ],
      NOW,
    );
    expect(r.visits_total).toBe(5);
    expect(r.window).toMatchObject({ days: 183, visits: 4, spend_vnd: 400000, spend_visits: 3, avg_spend_vnd: 133333 });
    expect(r.lifetime).toMatchObject({ spend_vnd: 1300000, spend_visits: 4 });
    expect(r.window.services).toEqual([
      { service_id: 'goi-dau-thu-gian', count: 3 },
      { service_id: 'massage-chan', count: 2 },
    ]);
    expect(r.lifetime.services).toEqual([
      { service_id: 'goi-dau-thu-gian', count: 3 },
      { service_id: 'massage-chan', count: 2 },
      { service_id: 'massage-body-thu-gian', count: 1 },
    ]);
  });

  it('no known amount at all: sums 0, average null', () => {
    const r = computeCustomerStatus([daysAgo(20), daysAgo(5)], NOW);
    expect(r.window).toMatchObject({ visits: 2, spend_vnd: 0, spend_visits: 0, avg_spend_vnd: null });
    expect(r.lifetime).toMatchObject({ spend_vnd: 0, spend_visits: 0 });
  });

  it('amounts that are not a number of 0 or more are unknown', () => {
    const odd = [-1, Number.NaN, '250000', undefined].map((a, i) => ({ visited_at: at('2026-11-01', 9 + i), service_id: `s${i}`, amount_vnd: a as unknown as number | null }));
    expect(computeCustomerStatus(odd, NOW).window).toMatchObject({ visits: 1, spend_vnd: 0, spend_visits: 0, avg_spend_vnd: null });
  });

  it('the window runs from the local date of now - windowDays through the local date of now', () => {
    const first = '2026-05-13'; // 183 days before 2026-11-12
    const visits = (date: string, hh: number): VisitFact[] => [{ visited_at: at(date, hh), service_id: 'massage-chan', amount_vnd: 100000 }];
    // 00:05 on the first date is inside, although it is more than 183 x 24 h before now (15:00)
    expect(computeCustomerStatus(visits(first, 0), NOW).window).toMatchObject({ visits: 1, spend_vnd: 100000 });
    expect(computeCustomerStatus(visits('2026-05-12', 23), NOW).window).toMatchObject({ visits: 0, spend_vnd: 0 });
    expect(computeCustomerStatus(visits('2026-05-12', 23), NOW).lifetime).toMatchObject({ spend_vnd: 100000, spend_visits: 1 });
    // later today is inside
    expect(computeCustomerStatus(visits('2026-11-12', 23), NOW).window).toMatchObject({ visits: 1 });
    // a row dated tomorrow (a typing mistake) is outside the window and never gives a negative day count
    const tomorrow = computeCustomerStatus(visits('2026-11-13', 9), NOW);
    expect(tomorrow.window).toMatchObject({ visits: 0 });
    expect(tomorrow).toMatchObject({ visits_total: 1, days_since_last_visit: 0, status: 'first_visit_done' });
  });

  it('services are ordered by count, then by service_id; a service counts once per visit day', () => {
    const r = computeCustomerStatus(
      [
        { visited_at: at('2026-10-01', 9), service_id: 'massage-chan', amount_vnd: null },
        { visited_at: at('2026-10-01', 14), service_id: 'massage-chan', amount_vnd: null }, // same day again: still 1
        { visited_at: at('2026-10-08', 9), service_id: 'massage-chan', amount_vnd: null },
        { visited_at: at('2026-10-08', 9), service_id: 'goi-dau-thu-gian', amount_vnd: null },
        { visited_at: at('2026-10-15', 9), service_id: 'goi-dau-thu-gian', amount_vnd: null },
        { visited_at: at('2026-10-15', 9), service_id: 'detox-da-dau', amount_vnd: null },
        { visited_at: at('2026-10-22', 9), service_id: 'detox-da-dau', amount_vnd: null },
        { visited_at: at('2026-10-22', 9), service_id: 'cham-soc-da', amount_vnd: null },
        { visited_at: at('2026-10-29', 9), service_id: 'massage-chan', amount_vnd: null },
      ],
      NOW,
    );
    expect(r.window.services).toEqual([
      { service_id: 'massage-chan', count: 3 },
      { service_id: 'detox-da-dau', count: 2 },
      { service_id: 'goi-dau-thu-gian', count: 2 },
      { service_id: 'cham-soc-da', count: 1 },
    ]);
    expect(r.lifetime.services).toEqual(r.window.services);
  });
});

describe('computeCustomerStatus: config', () => {
  it('defaults', () => {
    expect(DEFAULT_STATUS_CONFIG).toEqual({ absentFactor: 2, minAbsentDays: 14, defaultGapDays: 45, windowDays: 183 });
  });

  it('overrides change the thresholds and the window', () => {
    const r = computeCustomerStatus([daysAgo(100, 'massage-chan', 200000), daysAgo(40, 'massage-chan', 300000), daysAgo(10, 'massage-chan', 400000)], NOW, {
      config: { absentFactor: 1.5, minAbsentDays: 7, defaultGapDays: 30, windowDays: 30 },
    });
    // gaps 60, 30 -> 45; round(1.5 x 45) = 68
    expect(r).toMatchObject({ usual_gap_days: 45, absent_after_days: 68, status: 'returning' });
    expect(r.window).toMatchObject({ days: 30, from: localMidnight(NOW - 30 * DAY_MS), visits: 1, spend_vnd: 400000, avg_spend_vnd: 400000 });
    expect(r.lifetime).toMatchObject({ spend_vnd: 900000, spend_visits: 3 });
    // the default gap override applies to a single visit
    expect(computeCustomerStatus([daysAgo(61)], NOW, { config: { defaultGapDays: 30 } })).toMatchObject({ usual_gap_days: 30, absent_after_days: 60, status: 'long_absent' });
    expect(computeCustomerStatus([daysAgo(61)], NOW, { config: { absentFactor: 3 } })).toMatchObject({ absent_after_days: 135, status: 'first_visit_done' });
  });

  it('a partial override keeps the other defaults, an invalid value falls back to the default', () => {
    expect(computeCustomerStatus([daysAgo(10)], NOW, { config: { windowDays: 7 } })).toMatchObject({ usual_gap_days: 45, absent_after_days: 90, window: { days: 7, visits: 0 } });
    const bad = { absentFactor: 0, minAbsentDays: -3, defaultGapDays: Number.NaN, windowDays: -1 };
    expect(computeCustomerStatus([daysAgo(10)], NOW, { config: bad })).toMatchObject({ usual_gap_days: 45, absent_after_days: 90, window: { days: 183 } });
    expect(computeCustomerStatus([daysAgo(10)], NOW, { config: { windowDays: 30.9 } }).window.days).toBe(30);
  });
});

describe('computeCustomerStatus: input', () => {
  const rows: VisitFact[] = [
    { visited_at: at('2026-08-01', 9), service_id: 'goi-dau-thu-gian', amount_vnd: 150000 },
    { visited_at: at('2026-08-21', 15), service_id: 'massage-chan', amount_vnd: 250000 },
    { visited_at: at('2026-08-21', 16), service_id: 'goi-dau-thu-gian', amount_vnd: null },
    { visited_at: at('2026-09-30', 9), service_id: 'goi-dau-thu-gian', amount_vnd: 150000 },
    { visited_at: at('2026-10-30', 19), service_id: 'massage-body-thu-gian', amount_vnd: 450000 },
  ];

  it('the order of the rows does not matter', () => {
    const sorted = computeCustomerStatus(rows, NOW);
    expect(sorted).toMatchObject({ visits_total: 4, usual_gap_days: 30, gap_basis: 'own', days_since_last_visit: 13, status: 'returning' }); // gaps 20, 40, 30
    expect(sorted.last_visit_at).toBe(at('2026-10-30', 19));
    expect(computeCustomerStatus([...rows].reverse(), NOW)).toEqual(sorted);
    expect(computeCustomerStatus([rows[3]!, rows[0]!, rows[4]!, rows[2]!, rows[1]!], NOW)).toEqual(sorted);
    const copy = [...rows].reverse();
    computeCustomerStatus(copy, NOW);
    expect(copy).toEqual([...rows].reverse()); // the input is left as it was
  });

  it('a duplicate row (same time and service) counts once', () => {
    const once = computeCustomerStatus(rows, NOW);
    expect(computeCustomerStatus([...rows, ...rows], NOW)).toEqual(once);
    expect(computeCustomerStatus([rows[4]!, ...rows, rows[0]!, rows[0]!], NOW)).toEqual(once);
  });

  it('of two duplicate rows the known amount is kept, the larger one when both are known', () => {
    const t = at('2026-11-01', 9);
    const dup = (a: number | null, b: number | null) =>
      computeCustomerStatus(
        [
          { visited_at: t, service_id: 'massage-chan', amount_vnd: a },
          { visited_at: t, service_id: 'massage-chan', amount_vnd: b },
        ],
        NOW,
      ).window;
    expect(dup(null, 200000)).toMatchObject({ visits: 1, spend_vnd: 200000, spend_visits: 1 });
    expect(dup(200000, null)).toMatchObject({ visits: 1, spend_vnd: 200000, spend_visits: 1 });
    expect(dup(200000, 250000)).toMatchObject({ spend_vnd: 250000 });
    expect(dup(250000, 200000)).toMatchObject({ spend_vnd: 250000 });
    expect(dup(null, null)).toMatchObject({ visits: 1, spend_vnd: 0, spend_visits: 0, avg_spend_vnd: null });
    // the same time with another service is another row of the same visit
    const two = computeCustomerStatus(
      [
        { visited_at: t, service_id: 'massage-chan', amount_vnd: 200000 },
        { visited_at: t, service_id: 'goi-dau-thu-gian', amount_vnd: 150000 },
      ],
      NOW,
    );
    expect(two.window).toMatchObject({ visits: 1, spend_vnd: 350000, spend_visits: 1 });
  });

  it('rows without a usable time are ignored, and a missing list is an empty history', () => {
    const junk = [{ visited_at: Number.NaN, service_id: 'x', amount_vnd: 1 }, { visited_at: '2026-11-01' as unknown as number, service_id: 'x', amount_vnd: 1 }, null as unknown as VisitFact];
    expect(computeCustomerStatus(junk, NOW)).toMatchObject({ status: 'first_inquiry', visits_total: 0 });
    expect(computeCustomerStatus([...junk, daysAgo(3)], NOW)).toMatchObject({ status: 'first_visit_done', visits_total: 1, days_since_last_visit: 3 });
    expect(computeCustomerStatus(undefined as unknown as VisitFact[], NOW)).toMatchObject({ status: 'first_inquiry' });
  });
});
