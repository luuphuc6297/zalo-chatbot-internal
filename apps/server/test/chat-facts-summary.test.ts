// The merge of chat guesses into buildCustomerSummary and customerFactsForModel (docs/contracts.md section 15.12), and
// the JSON of the read tool get_customer_profile. Library calls use the fixed clock NOW of customers-helpers.ts. All data
// is synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { buildCustomerSummary, customerFactsForModel } from '../src/lib/customer-summary';
import { DAY_MS, localDate, localMidnight } from '../src/lib/time';
import type { CustomerFacts } from '../src/types';
import { runner, seed } from './core-helpers';
import { BODY, CHAN, GOI, HEALTH, NOW, SENS, addProfile, addRole, addVisit, at, catalog, newCustomer, nextZaloId } from './customers-helpers';
import { GENERATED_AT, VERSION, benefit, call, cand, chatBenefitsOf, chatVisitsOf, doc, entry, phone, push, setChatState, upcoming } from './chat-facts-helpers';
import { personalJob, settle } from './personal-helpers';

let NAMES: Record<string, string> = {};
let CV = '';

beforeAll(async () => {
  CV = (await seed()).catalog_version;
  NAMES = (await catalog()).names;
});

type Found = Extract<CustomerFacts, { found: true }>;
async function facts(customerId: string): Promise<Found> {
  const f = await customerFactsForModel(env, customerId, CV, NOW);
  if (!f.found) throw new Error(`expected found: true, got ${f.reason}`);
  return f;
}

const d = (daysAgo: number) => localDate(at(daysAgo));
const svc = (service_id: string | null, service_name: string | null = null) => ({ service_id, service_name, basis: 'visit_day' });
const WINDOW_FROM = localDate(localMidnight(NOW - 183 * DAY_MS));

describe('buildCustomerSummary with chat guesses', () => {
  it('counts active high and medium guesses on dates without a recorded visit; spend only from paid amounts', async () => {
    const a = await newCustomer();
    await addVisit(a.id, at(100), GOI, { amount: 200000 });
    await addVisit(a.id, at(40), GOI, { amount: 300000 });
    await push(
      doc([
        entry(a.zalo, {
          visits: [
            cand(d(70), { time: '10:00', services: [svc(CHAN)], amount_vnd: 500000, amount_source: 'paid', technician: 'Hoa' }),
            cand(d(55), { services: [svc(GOI)], amount_vnd: 600000, amount_source: 'list_price', confidence: 'medium' }),
            cand(d(40), { services: [svc(BODY)], amount_vnd: 999000 }), // a recorded visit that day: not counted
            cand(d(20), { time: '14:30', services: [svc(BODY)], amount_vnd: 400000, amount_source: 'quoted', technician: 'Lan', confidence: 'medium' }),
            cand(d(10), { confidence: 'low' }),
            cand(d(8)), // confirmed below: it is already a visits row, never counted twice
            cand(d(5)), // dismissed below
          ],
          upcoming: [upcoming(d(-3), { time: null }), upcoming(d(2))],
          benefits: [benefit('Gói 10 buổi'), benefit('Voucher sinh nhật', { kind: 'voucher', total_count: null, remaining: null }), benefit('Gói 3 buổi', { total_count: 3, remaining: 1 })],
          phone: phone('0912345801'),
        }),
      ]),
    );
    const rows = await chatVisitsOf(a.zalo);
    await setChatState('chat_visits', rows.find((r) => r.local_date === d(8))!.id, 'confirmed');
    await setChatState('chat_visits', rows.find((r) => r.local_date === d(5))!.id, 'dismissed');
    await setChatState('chat_benefits', (await chatBenefitsOf(a.zalo)).find((b) => b.title === 'Gói 3 buổi')!.id, 'dismissed');

    // visit days 100 (recorded), 70, 55, 40 (recorded), 20: gaps 30, 15, 15, 20, median 17.5
    expect(await buildCustomerSummary(env, a.id, NOW)).toEqual({
      role: null,
      role_source: null,
      name: null,
      address_term: null,
      phone: null,
      status: 'returning',
      visits_total: 5,
      last_visit: { visited_at: at(20, 14, 30), date: d(20), time: '14:30', services: [{ service_id: BODY, name: NAMES[BODY] }], technician: 'Lan', amount_vnd: null, from_chat: true },
      days_since_last_visit: 20,
      usual_gap_days: 17.5,
      gap_basis: 'own',
      absent_after_days: 35,
      lifetime_spend_vnd: 1_000_000,
      lifetime_spend_visits: 3,
      window: {
        days: 183,
        from_date: WINDOW_FROM,
        visits: 5,
        spend_vnd: 1_000_000,
        avg_spend_vnd: 333333,
        services: [
          { service_id: GOI, name: NAMES[GOI], count: 3 },
          { service_id: BODY, name: NAMES[BODY], count: 1 },
          { service_id: CHAN, name: NAMES[CHAN], count: 1 },
        ],
      },
      benefits: [],
      chat: {
        visits_counted: 3,
        visits_low: 1,
        upcoming_next: { date: d(-3), time: null },
        benefits_active: 2,
        phone_suggestion: true,
        analyzer_version: VERSION,
        generated_at: GENERATED_AT,
      },
    });

    // the model view of the same contact: no phone, no benefit title, guesses counted and marked
    const f = await facts(a.id);
    expect(f).toMatchObject({
      has_phone: false,
      status: 'returning',
      visits_total: 5,
      last_visit: { date: d(20), time: '14:30', services: [NAMES[BODY]], other_services: 0, technician: 'Lan', from_chat: true },
      window: { days: 183, visits: 5, spend_vnd: 1_000_000, avg_spend_vnd: 333333, usual_services: [{ name: NAMES[GOI], count: 3 }, { name: NAMES[BODY], count: 1 }, { name: NAMES[CHAN], count: 1 }], other_services: 0 },
      lifetime: { spend_vnd: 1_000_000, spend_visits: 3 },
      unused_benefits: [],
      visits_from_chat: 3,
      next_booking_from_chat: { date: d(-3), time: null },
      benefits_from_chat: [{ kind: 'package', remaining: 7 }],
    });
    const json = JSON.stringify(f);
    for (const hidden of ['0912345801', '912345801', 'Gói 10', 'sinh nhật', 'phone_suggestion', a.zalo, 'chv_']) expect(json, hidden).not.toContain(hidden);

    // once the customer has a phone, the suggestion no longer waits for staff
    await env.DB.prepare("UPDATE customers SET phone = '0901234511' WHERE id = ?").bind(a.id).run();
    expect((await buildCustomerSummary(env, a.id, NOW))!.chat!.phone_suggestion).toBe(false);
  });

  it('a guessed last day: unknown time is null, a day without a service is counted but lists none', async () => {
    const b = await newCustomer();
    await push(doc([entry(b.zalo, { visits: [cand(d(15), { time: null, services: [], technician: 'KTV 0912', amount_vnd: 250000 })] })]));
    expect(await buildCustomerSummary(env, b.id, NOW)).toMatchObject({
      status: 'first_visit_done',
      visits_total: 1,
      last_visit: { visited_at: at(15, 12, 0), date: d(15), time: null, services: [], technician: 'KTV 0912', amount_vnd: 250000, from_chat: true },
      days_since_last_visit: 15,
      gap_basis: 'default',
      usual_gap_days: 45,
      lifetime_spend_vnd: 250000,
      window: { visits: 1, spend_vnd: 250000, services: [] },
      chat: { visits_counted: 1, visits_low: 0, upcoming_next: null, benefits_active: 0, phone_suggestion: false },
    });
    // the model gets no chat technician with a run of 3 or more digits
    const f = await facts(b.id);
    expect(f.last_visit).toEqual({ date: d(15), time: null, services: [], other_services: 0, technician: null, from_chat: true });
    expect(f.window).toMatchObject({ usual_services: [], other_services: 0 });
    expect(JSON.stringify(f)).not.toContain('0912');
    expect(JSON.stringify(f)).not.toContain('chat:none');

    for (const [technician, model] of [['số 8', 'số 8'], ['Lan', 'Lan'], ['KTV 12', 'KTV 12'], ['123', null], ['Mai 2025', null]] as const) {
      const c = await newCustomer();
      await push(doc([entry(c.zalo, { visits: [cand(d(3), { technician })] })]));
      expect((await facts(c.id)).last_visit!.technician, technician).toBe(model);
      expect((await buildCustomerSummary(env, c.id, NOW))!.last_visit!.technician).toBe(technician);
    }
  });

  it('sensitive and non-catalog services from chat are named to staff and only counted for the model', async () => {
    const c = await newCustomer();
    await push(doc([entry(c.zalo, { visits: [cand(d(12), { services: [svc(SENS), svc(HEALTH), svc(null, 'tắm trắng')], technician: 'Mai' })] })]));
    const s = await buildCustomerSummary(env, c.id, NOW);
    expect(s!.last_visit!.services).toEqual([
      { service_id: SENS, name: NAMES[SENS] },
      { service_id: HEALTH, name: NAMES[HEALTH] },
      { service_id: 'ext:tam-trang', name: 'tắm trắng' },
    ]);
    const f = await facts(c.id);
    expect(f.last_visit).toMatchObject({ services: [], other_services: 3, from_chat: true });
    expect(f.window).toMatchObject({ usual_services: [], other_services: 3 });
    const json = JSON.stringify(f);
    for (const hidden of [NAMES[SENS]!, NAMES[HEALTH]!, 'tắm trắng', 'ext:', SENS, HEALTH]) expect(json, hidden).not.toContain(hidden);
  });

  it('with chat facts but no counted guess, the figures are the recorded ones and from_chat is false', async () => {
    const e = await newCustomer();
    await addVisit(e.id, at(5), GOI, { amount: 150000, technician: 'Hoa 0912' });
    await push(doc([entry(e.zalo, { visits: [cand(d(30), { confidence: 'low' })], upcoming: [upcoming(d(1))] })]));
    const s = await buildCustomerSummary(env, e.id, NOW);
    expect(s).toMatchObject({
      visits_total: 1,
      last_visit: { from_chat: false, technician: 'Hoa 0912', time: '10:00' },
      chat: { visits_counted: 0, visits_low: 1, upcoming_next: null, benefits_active: 0, phone_suggestion: false, analyzer_version: VERSION },
    });
    const f = await facts(e.id);
    // a technician staff typed keeps the section 14 behaviour
    expect(f).toMatchObject({ visits_total: 1, visits_from_chat: 0, next_booking_from_chat: null, benefits_from_chat: [], last_visit: { from_chat: false, technician: 'Hoa 0912' } });
  });

  it('a confirmed guess counts once, as the recorded visit', async () => {
    const g = await newCustomer();
    await push(doc([entry(g.zalo, { visits: [cand(d(25), { services: [svc(CHAN)] })] })]));
    const before = await buildCustomerSummary(env, g.id, NOW);
    expect(before).toMatchObject({ visits_total: 1, last_visit: { from_chat: true }, chat: { visits_counted: 1 } });
    const id = (await chatVisitsOf(g.zalo))[0]!.id;
    expect((await call('POST', `/staff/chat-facts/visits/${id}/confirm`)).status).toBe(200);
    const after = await buildCustomerSummary(env, g.id, NOW);
    expect(after).toMatchObject({ visits_total: 1, lifetime_spend_vnd: 350000, last_visit: { from_chat: false, amount_vnd: 350000 }, chat: { visits_counted: 0 } });
  });

  it('a contact without chat facts gets exactly the section 14 summary and model facts', async () => {
    const h = await newCustomer();
    await addVisit(h.id, at(9), GOI, { amount: 100000, technician: 'Hoa' });
    // guesses of another contact, and a contact profile, do not count
    await push(doc([entry(nextZaloId(), { visits: [cand(d(9))] })]));
    await addProfile(h.zalo, { relationship: 'customer' });
    const s = await buildCustomerSummary(env, h.id, NOW);
    expect(s).not.toHaveProperty('chat');
    expect(s!.last_visit).toEqual({ visited_at: at(9), date: d(9), time: '10:00', services: [{ service_id: GOI, name: NAMES[GOI] }], technician: 'Hoa', amount_vnd: 100000 });
    const f = await facts(h.id);
    for (const k of ['visits_from_chat', 'next_booking_from_chat', 'benefits_from_chat']) expect(f).not.toHaveProperty(k);
    expect(f.last_visit).not.toHaveProperty('from_chat');
    // an OA customer is never looked up in the chat tables
    const oa = await newCustomer({ zalo_user_id: '5550002223334', oa_id: 'test-oa-id', channel: 'oa' });
    expect(await buildCustomerSummary(env, oa.id, NOW)).not.toHaveProperty('chat');
  });

  it('chat facts of an internal or private contact never reach the model', async () => {
    const staffContact = await newCustomer();
    await push(doc([entry(staffContact.zalo, { visits: [cand(d(4))] })]));
    await addRole(staffContact.zalo, 'staff');
    expect(await customerFactsForModel(env, staffContact.id, CV, NOW)).toEqual({ found: false, reason: 'internal_contact' });
    const family = await newCustomer();
    await push(doc([entry(family.zalo, { visits: [cand(d(4))] })]));
    await addProfile(family.zalo, { relationship: 'family' });
    expect(await customerFactsForModel(env, family.id, CV, NOW)).toEqual({ found: false, reason: 'no_data' });
  });
});

describe('get_customer_profile', () => {
  it('returns the merged facts to the running job, without the phone suggestion or a title', async () => {
    await settle();
    const p = await personalJob('mai chị qua gội đầu được không');
    await push(
      doc([
        entry(p.zalo, {
          visits: [cand(localDate(Date.now() - 20 * DAY_MS), { services: [svc(GOI)], technician: 'Vy' })],
          upcoming: [upcoming(localDate(Date.now() + 2 * DAY_MS))],
          benefits: [benefit('Gói 8 buổi gội', { total_count: 8, remaining: 5 })],
          phone: phone('0912345899'),
        }),
      ]),
    );
    const r = await runner('/runner/tools/get_customer_profile', { job_id: p.jobId, input: {} });
    expect(r.status).toBe(200);
    expect(r.body.is_error).toBe(false);
    expect(r.body.result).toMatchObject({
      found: true,
      has_phone: false,
      visits_total: 1,
      last_visit: { services: [NAMES[GOI]], technician: 'Vy', from_chat: true },
      visits_from_chat: 1,
      next_booking_from_chat: { date: localDate(Date.now() + 2 * DAY_MS), time: '15:00' },
      benefits_from_chat: [{ kind: 'package', remaining: 5 }],
    });
    const json = JSON.stringify(r.body);
    for (const hidden of ['0912345899', 'Gói 8', 'phone_suggestion']) expect(json, hidden).not.toContain(hidden);
  });
});
