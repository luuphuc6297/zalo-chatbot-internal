// buildCustomerSummary, customerFactsForModel, peerGapDays and the env config (docs/contracts.md section 14.6).
// All data is synthetic. Library calls use the fixed clock NOW of customers-helpers.ts.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { buildCustomerSummary, customerFactsForModel, peerGapDays, resolveRole, statusConfigFromEnv } from '../src/lib/customer-summary';
import { DAY_MS, localDate, localMidnight } from '../src/lib/time';
import type { CustomerFacts, Env } from '../src/types';
import { seed, uniq } from './core-helpers';
import { BODY, CHAN, GOI, HEALTH, NOW, SENS, T0, addBenefit, addProfile, addRole, addVisit, at, catalog, newCustomer, nextPhone } from './customers-helpers';

let NAMES: Record<string, string> = {};
let CV = '';

beforeAll(async () => {
  CV = (await seed()).catalog_version;
  const c = await catalog();
  NAMES = c.names;
  expect(c.groups).toMatchObject({ [GOI]: 'hair', [CHAN]: 'relaxation', [BODY]: 'relaxation', [SENS]: 'women', [HEALTH]: 'health' });
});

type Found = Extract<CustomerFacts, { found: true }>;
async function facts(customerId: string, cv = CV): Promise<Found> {
  const f = await customerFactsForModel(env, customerId, cv, NOW);
  if (!f.found) throw new Error(`expected found: true, got ${f.reason}`);
  return f;
}

describe('buildCustomerSummary', () => {
  it('returns null for an unknown, deleted or empty customer id', async () => {
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    expect(await buildCustomerSummary(env, 'cus_missing', NOW)).toBeNull();
    expect(await buildCustomerSummary(env, gone.id, NOW)).toBeNull();
    expect(await buildCustomerSummary(env, '', NOW)).toBeNull();
  });

  it('describes a contact without visits, profile and role as a first inquiry', async () => {
    const a = await newCustomer();
    expect(await buildCustomerSummary(env, a.id, NOW)).toEqual({
      role: null,
      role_source: null,
      name: null,
      address_term: null,
      phone: null,
      status: 'first_inquiry',
      visits_total: 0,
      last_visit: null,
      days_since_last_visit: null,
      usual_gap_days: null,
      gap_basis: null,
      absent_after_days: null,
      lifetime_spend_vnd: 0,
      lifetime_spend_visits: 0,
      window: { days: 183, from_date: localDate(localMidnight(NOW - 183 * DAY_MS)), visits: 0, spend_vnd: 0, avg_spend_vnd: null, services: [] },
      benefits: [],
    });
  });

  it('builds the whole view from the visit history, the role, the profile and the benefits', async () => {
    const phone = nextPhone();
    const a = await newCustomer({ display_name: 'Lan Nguyen', phone });
    await addRole(a.zalo, 'customer', 'zalo_label');
    await addProfile(a.zalo, { address_term: 'chị', name_to_use: 'Lan', display_name: 'Lan N' });
    await addVisit(a.id, at(100), GOI, { amount: 200000 });
    await addVisit(a.id, at(70), GOI, { amount: 250000 });
    await addVisit(a.id, at(40), GOI);
    await addVisit(a.id, at(10, 10, 0), GOI, { amount: 300000, technician: 'Hoa' });
    await addVisit(a.id, at(10, 11, 30), CHAN, { technician: 'Mai' });
    await addVisit(a.id, at(10, 12, 0), 'ext:xong-hoi', { amount: 100000, technician: 'Hoa', service_name: 'Xông hơi', source: 'import' });

    const in30 = await addBenefit(a.id, { title: 'Gói 10 buổi gội', total: 10, used: 3, expires_at: T0 + 30 * DAY_MS });
    const noExpiry = await addBenefit(a.id, { kind: 'voucher', title: 'Voucher 1 buổi', total: 1 });
    await addBenefit(a.id, { title: 'Gói đã hủy', status: 'void' });
    await addBenefit(a.id, { title: 'Gói đã dùng hết', total: 2, used: 2 });
    await addBenefit(a.id, { title: 'Gói hết hạn hôm qua', expires_at: T0 - 1 });
    const today = await addBenefit(a.id, { title: 'Gói hết hạn hôm nay', total: 5, used: 4, expires_at: T0 + 30 * 60_000 });

    const s = await buildCustomerSummary(env, a.id, NOW);
    expect(s).toEqual({
      role: 'customer',
      role_source: 'zalo_label',
      name: 'Lan',
      address_term: 'chị',
      phone,
      status: 'returning',
      visits_total: 4,
      last_visit: {
        visited_at: at(10, 12, 0),
        date: localDate(at(10)),
        time: '12:00',
        services: [
          { service_id: GOI, name: NAMES[GOI] },
          { service_id: CHAN, name: NAMES[CHAN] },
          { service_id: 'ext:xong-hoi', name: 'Xông hơi' },
        ],
        technician: 'Hoa, Mai',
        amount_vnd: 400000,
      },
      days_since_last_visit: 10,
      usual_gap_days: 30,
      gap_basis: 'own',
      absent_after_days: 60,
      lifetime_spend_vnd: 850000,
      lifetime_spend_visits: 3,
      window: {
        days: 183,
        from_date: localDate(localMidnight(NOW - 183 * DAY_MS)),
        visits: 4,
        spend_vnd: 850000,
        avg_spend_vnd: 283333,
        services: [
          { service_id: GOI, name: NAMES[GOI], count: 4 },
          { service_id: 'ext:xong-hoi', name: 'Xông hơi', count: 1 },
          { service_id: CHAN, name: NAMES[CHAN], count: 1 },
        ],
      },
      benefits: [
        { id: today, kind: 'package', title: 'Gói hết hạn hôm nay', remaining: 1, expires_on: localDate(T0) },
        { id: in30, kind: 'package', title: 'Gói 10 buổi gội', remaining: 7, expires_on: localDate(T0 + 30 * DAY_MS) },
        { id: noExpiry, kind: 'voucher', title: 'Voucher 1 buổi', remaining: 1, expires_on: null },
      ],
    });
  });

  it('marks a customer long absent by their own rhythm, not by a fixed number of days', async () => {
    const weekly = await newCustomer();
    for (const d of [51, 44, 37, 30]) await addVisit(weekly.id, at(d), GOI); // every 7 days, away for 30
    const quarterly = await newCustomer();
    for (const d of [300, 210, 120, 30]) await addVisit(quarterly.id, at(d), GOI); // every 90 days, away for 30
    expect(await buildCustomerSummary(env, weekly.id, NOW)).toMatchObject({ status: 'long_absent', usual_gap_days: 7, absent_after_days: 14, days_since_last_visit: 30, gap_basis: 'own' });
    expect(await buildCustomerSummary(env, quarterly.id, NOW)).toMatchObject({ status: 'returning', usual_gap_days: 90, absent_after_days: 180, days_since_last_visit: 30, gap_basis: 'own' });
  });

  it('falls back to the display name, and derives the role from the profile when there is no role row', async () => {
    const a = await newCustomer({ display_name: 'Thu Tran' });
    await addProfile(a.zalo, { relationship: 'customer', display_name: 'Thu T' });
    expect(await buildCustomerSummary(env, a.id, NOW)).toMatchObject({ role: 'customer', role_source: 'profile', name: 'Thu Tran', address_term: null });
    const b = await newCustomer();
    await addProfile(b.zalo, { relationship: 'staff', display_name: 'Nhan vien A' });
    expect(await buildCustomerSummary(env, b.id, NOW)).toMatchObject({ role: 'staff', role_source: 'profile', name: 'Nhan vien A' });
    const c = await newCustomer();
    await addProfile(c.zalo, { relationship: 'family' });
    await addRole(c.zalo, 'manager', 'staff');
    expect(await buildCustomerSummary(env, c.id, NOW)).toMatchObject({ role: 'manager', role_source: 'staff' });
    expect(resolveRole(null, { relationship: 'family' })).toEqual({ role: null, role_source: null });
    expect(resolveRole(null, null)).toEqual({ role: null, role_source: null });
  });
});

describe('peer gap of a customer with one visit', () => {
  it('uses the default gap with fewer than three peers and the peers median from three on', async () => {
    const svc = `ext:${uniq('peer')}`;
    const subject = await newCustomer();
    await addVisit(subject.id, at(20), svc);
    const p1 = await newCustomer(); // 23:50 and 00:10 of the next local day: a gap of 1 day
    await addVisit(p1.id, at(60, 23, 50), svc);
    await addVisit(p1.id, at(59, 0, 10), GOI);
    const p2 = await newCustomer(); // gap 20
    await addVisit(p2.id, at(50), svc);
    await addVisit(p2.id, at(30), svc);
    const single = await newCustomer(); // one visit day: no rhythm, ignored
    await addVisit(single.id, at(40, 9), svc);
    await addVisit(single.id, at(40, 15), svc);

    expect(await peerGapDays(env, subject.id, [svc])).toBeNull();
    expect(await buildCustomerSummary(env, subject.id, NOW)).toMatchObject({ status: 'first_visit_done', visits_total: 1, gap_basis: 'default', usual_gap_days: 45, absent_after_days: 90, days_since_last_visit: 20 });

    const p3 = await newCustomer(); // gaps 30 and 50: median 40
    for (const d of [100, 70, 20]) await addVisit(p3.id, at(d), svc);
    expect(await peerGapDays(env, subject.id, [svc])).toBe(20); // median of 1, 20, 40
    expect(await buildCustomerSummary(env, subject.id, NOW)).toMatchObject({ status: 'first_visit_done', gap_basis: 'service_peers', usual_gap_days: 20, absent_after_days: 40 });
    expect(await customerFactsForModel(env, subject.id, CV, NOW)).toMatchObject({ found: true, gap_basis: 'service_peers', usual_gap_days: 20, absent_after_days: 40 });
    // the subject's own visits never count as a peer
    expect(await peerGapDays(env, p3.id, [svc])).toBeNull();
    expect(await peerGapDays(env, subject.id, [])).toBeNull();
    expect(await peerGapDays(env, subject.id, [`ext:${uniq('nobody')}`])).toBeNull();
  });

  it('a single visit long ago is long absent by the peers rhythm', async () => {
    const svc = `ext:${uniq('peer')}`;
    const subject = await newCustomer();
    await addVisit(subject.id, at(50), svc);
    for (let i = 0; i < 3; i++) {
      const p = await newCustomer();
      await addVisit(p.id, at(40), svc);
      await addVisit(p.id, at(30), svc);
    }
    expect(await buildCustomerSummary(env, subject.id, NOW)).toMatchObject({ status: 'long_absent', gap_basis: 'service_peers', usual_gap_days: 10, absent_after_days: 20, days_since_last_visit: 50 });
  });
});

describe('customerFactsForModel', () => {
  it('answers no_data for an unknown or deleted customer', async () => {
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    expect(await customerFactsForModel(env, 'cus_missing', CV, NOW)).toEqual({ found: false, reason: 'no_data' });
    expect(await customerFactsForModel(env, gone.id, CV, NOW)).toEqual({ found: false, reason: 'no_data' });
  });

  it('answers the full object for a new contact without visits and profile', async () => {
    const a = await newCustomer();
    expect(await customerFactsForModel(env, a.id, CV, NOW)).toEqual({
      found: true,
      role: null,
      address_term: null,
      name_to_use: null,
      has_phone: false,
      status: 'first_inquiry',
      visits_total: 0,
      last_visit: null,
      days_since_last_visit: null,
      usual_gap_days: null,
      gap_basis: null,
      absent_after_days: null,
      window: { days: 183, visits: 0, spend_vnd: 0, avg_spend_vnd: null, usual_services: [], other_services: 0 },
      lifetime: { spend_vnd: 0, spend_visits: 0 },
      unused_benefits: [],
      services_mentioned: [],
    });
  });

  it('never carries the phone number, sensitive service names or names from outside the catalog', async () => {
    const phone = nextPhone();
    const a = await newCustomer({ phone, display_name: 'Lan Nguyen' });
    await addVisit(a.id, at(50, 9), GOI, { amount: 200000 });
    await addVisit(a.id, at(50, 10), SENS, { amount: 500000 });
    await addVisit(a.id, at(20, 9), GOI, { amount: 200000, technician: 'Hoa' });
    await addVisit(a.id, at(20, 10), CHAN, { technician: 'Hoa' });
    await addVisit(a.id, at(20, 11), 'ext:tam-trang', { service_name: 'Tắm trắng bí mật' });
    await addVisit(a.id, at(20, 12), HEALTH, { service_name: 'Giải cảm riêng' });
    const f = await facts(a.id);
    expect(f).toMatchObject({
      has_phone: true,
      status: 'returning',
      visits_total: 2,
      days_since_last_visit: 20,
      usual_gap_days: 30,
      gap_basis: 'own',
      absent_after_days: 60,
      last_visit: { date: localDate(at(20)), time: '12:00', services: [NAMES[GOI], NAMES[CHAN]], other_services: 2, technician: 'Hoa' },
      window: { days: 183, visits: 2, spend_vnd: 900000, avg_spend_vnd: 450000, usual_services: [{ name: NAMES[GOI], count: 2 }, { name: NAMES[CHAN], count: 1 }], other_services: 3 },
      lifetime: { spend_vnd: 900000, spend_visits: 2 },
    });
    const json = JSON.stringify(f);
    expect(json).not.toContain(phone);
    expect(json).not.toContain(phone.slice(1));
    expect(json).not.toContain('"phone"');
    expect(json).not.toContain(NAMES[SENS]);
    expect(json).not.toContain(NAMES[HEALTH]);
    for (const hidden of ['Tắm trắng', 'Giải cảm riêng', 'ext:', SENS, HEALTH, 'Lan Nguyen', a.id, a.zalo]) expect(json, hidden).not.toContain(hidden);
  });

  it('hides a benefit title that could name a sensitive service, and never gives benefit ids', async () => {
    const a = await newCustomer();
    const expires = T0 + 5 * DAY_MS;
    await addBenefit(a.id, { title: 'Gói 10 buổi gội đầu', service_id: GOI, total: 10, used: 4, expires_at: expires, created_at: 1 });
    await addBenefit(a.id, { title: 'Gói chăm sóc riêng', service_id: SENS, total: 5, created_at: 2 });
    await addBenefit(a.id, { kind: 'voucher', title: `TẶNG 1 BUỔI ${NAMES[SENS]!.toUpperCase()}`, total: 1, created_at: 3 });
    await addBenefit(a.id, { title: 'Gói tắm trắng', service_id: 'ext:tam-trang', total: 3, created_at: 4 });
    await addBenefit(a.id, { kind: 'voucher', title: 'Voucher sinh nhật', total: 1, created_at: 5 });
    await addBenefit(a.id, { title: 'Gói đã hủy', status: 'void', created_at: 6 });
    const f = await facts(a.id);
    expect(f.unused_benefits).toEqual([
      { kind: 'package', title: 'Gói 10 buổi gội đầu', remaining: 6, expires_on: localDate(expires) },
      { kind: 'package', title: 'Gói dịch vụ', remaining: 5, expires_on: null },
      { kind: 'voucher', title: 'Voucher', remaining: 1, expires_on: null },
      { kind: 'package', title: 'Gói dịch vụ', remaining: 3, expires_on: null },
      { kind: 'voucher', title: 'Voucher sinh nhật', remaining: 1, expires_on: null },
    ]);
    expect(JSON.stringify(f)).not.toMatch(/ben_|riêng|tắm trắng/i);
  });

  it('answers internal_contact for a manager or staff contact and no_data for a private contact', async () => {
    const mk = async (role: 'customer' | 'manager' | 'staff' | null, relationship: string | null) => {
      const c = await newCustomer({ phone: nextPhone() });
      if (role) await addRole(c.zalo, role);
      if (relationship) await addProfile(c.zalo, { relationship, address_term: 'chị', name_to_use: 'Lan' });
      await addVisit(c.id, at(5), GOI, { amount: 100000 });
      return customerFactsForModel(env, c.id, CV, NOW);
    };
    expect(await mk('manager', null)).toEqual({ found: false, reason: 'internal_contact' });
    expect(await mk('staff', 'customer')).toEqual({ found: false, reason: 'internal_contact' });
    expect(await mk(null, 'staff')).toEqual({ found: false, reason: 'internal_contact' });
    for (const rel of ['family', 'friend', 'personal']) expect(await mk(null, rel), rel).toEqual({ found: false, reason: 'no_data' });
    // a role row 'customer' wins over the stored relationship
    expect(await mk('customer', 'family')).toMatchObject({ found: true, role: 'customer', address_term: 'chị', name_to_use: 'Lan', visits_total: 1 });
    expect(await mk('customer', 'staff')).toMatchObject({ found: true, role: 'customer' });
    expect(await mk(null, 'unknown')).toMatchObject({ found: true, role: null, address_term: 'chị', name_to_use: 'Lan' });
    expect(await mk(null, 'customer')).toMatchObject({ found: true, role: 'customer' });
  });

  it('gives the address term and name only by the section 13 rules', async () => {
    const mk = async (over: Parameters<typeof addProfile>[1]) => {
      const c = await newCustomer();
      await addProfile(c.zalo, over);
      return facts(c.id);
    };
    expect(await mk({ address_term: 'chị', name_to_use: 'Lan', address_confidence: 'medium' })).toMatchObject({ address_term: 'chị', name_to_use: 'Lan' });
    expect(await mk({ address_term: 'chị', name_to_use: 'Lan', address_confidence: 'low' })).toMatchObject({ address_term: null, name_to_use: null });
    expect(await mk({ address_term: 'anh/chị', name_to_use: 'Lan', address_confidence: 'high' })).toMatchObject({ address_term: 'anh/chị', name_to_use: null });
    expect(await mk({ address_term: 'anh', name_to_use: 'Minh Anh 0907', address_confidence: 'high' })).toMatchObject({ address_term: 'anh', name_to_use: null });
  });

  it('lists the services the profile says were mentioned, without sensitive ones', async () => {
    const a = await newCustomer();
    const svc = (service_id: string, status: string) => ({ key: service_id, service_id, name: 'x', group: 'x', sensitive: false, status });
    await addProfile(a.zalo, { services: [svc(BODY, 'mentioned'), svc(SENS, 'mentioned'), svc(GOI, 'likely_used'), { ...svc(CHAN, 'mentioned'), sensitive: true }] });
    const f = await facts(a.id);
    expect(f.services_mentioned).toEqual([NAMES[BODY]]);
    expect(JSON.stringify(f)).not.toContain(NAMES[SENS]);
  });

  it('names services only from the given catalog version, the active one when it is empty', async () => {
    const a = await newCustomer();
    await addVisit(a.id, at(5), GOI);
    await addVisit(a.id, at(5, 11), CHAN);
    const none = await facts(a.id, 'cv_none');
    expect(none.last_visit).toMatchObject({ services: [], other_services: 2 });
    expect(none.window).toMatchObject({ usual_services: [], other_services: 2 });
    const active = await facts(a.id, '');
    expect(active.last_visit!.services).toEqual([NAMES[GOI], NAMES[CHAN]]);
    expect(active.window.other_services).toBe(0);
  });

  it('names at most five usual services and counts the rest', async () => {
    const a = await newCustomer();
    const ids = Object.keys(NAMES).filter((id) => !['cham', 'se-khit', 'yoni', 'nan-chinh', 'tieu-u', 'dien-chan', 'giai-moi', 'thieu-mau', 'dau-that', 'detox-mui', 'thai-han'].some((p) => id.startsWith(p)));
    const six = ids.filter((id) => id === GOI || id === CHAN || id === BODY || id.startsWith('mo-vai') || id.startsWith('massage-co') || id.startsWith('detox-da'));
    expect(six).toHaveLength(6);
    let minute = 0;
    for (const id of six) await addVisit(a.id, at(3, 9, minute++), id);
    const f = await facts(a.id);
    expect(f.window.usual_services).toHaveLength(5);
    expect(f.window.other_services).toBe(1);
    expect(f.last_visit!.services).toHaveLength(6);
  });
});

describe('statusConfigFromEnv', () => {
  const cfg = (over: Partial<Env>) => statusConfigFromEnv({ ...env, CUSTOMER_ABSENT_FACTOR_PCT: undefined, CUSTOMER_MIN_ABSENT_DAYS: undefined, CUSTOMER_DEFAULT_GAP_DAYS: undefined, CUSTOMER_WINDOW_DAYS: undefined, ...over } as Env);
  it('reads the four integers and falls back to the defaults', () => {
    expect(cfg({})).toEqual({ absentFactor: 2, minAbsentDays: 14, defaultGapDays: 45, windowDays: 183 });
    expect(cfg({ CUSTOMER_ABSENT_FACTOR_PCT: '150', CUSTOMER_MIN_ABSENT_DAYS: '7', CUSTOMER_DEFAULT_GAP_DAYS: '30', CUSTOMER_WINDOW_DAYS: '90' } as Partial<Env>)).toEqual({ absentFactor: 1.5, minAbsentDays: 7, defaultGapDays: 30, windowDays: 90 });
    expect(cfg({ CUSTOMER_ABSENT_FACTOR_PCT: 'abc', CUSTOMER_MIN_ABSENT_DAYS: '0', CUSTOMER_DEFAULT_GAP_DAYS: '-5', CUSTOMER_WINDOW_DAYS: '' } as Partial<Env>)).toEqual({ absentFactor: 2, minAbsentDays: 14, defaultGapDays: 45, windowDays: 183 });
  });

  it('the summary follows the configured numbers', async () => {
    const a = await newCustomer();
    for (const d of [40, 30, 20]) await addVisit(a.id, at(d), GOI);
    const tuned = { ...env, CUSTOMER_ABSENT_FACTOR_PCT: '150', CUSTOMER_MIN_ABSENT_DAYS: '7', CUSTOMER_WINDOW_DAYS: '25' } as Env;
    expect(await buildCustomerSummary(tuned, a.id, NOW)).toMatchObject({ status: 'long_absent', usual_gap_days: 10, absent_after_days: 15, window: { days: 25, visits: 1 } });
    expect(await buildCustomerSummary(env, a.id, NOW)).toMatchObject({ status: 'returning', absent_after_days: 20, window: { days: 183, visits: 3 } });
  });
});
