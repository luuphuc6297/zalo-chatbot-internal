// GET /staff/chat-facts/:zalo_user_id and the staff decisions on chat guesses (docs/contracts.md section 15.11):
// confirm and dismiss of visits and benefits, accept and dismiss of a phone suggestion. A confirmed visit is a visits
// row without any follow-up job. No audit row and no log line carries the phone number or free text. All data is
// synthetic.
import { env } from 'cloudflare:test';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseLocalDateTime } from '../src/staff-api/customers';
import { localDate } from '../src/lib/time';
import { seed } from './core-helpers';
import { BODY, CHAN, catalog, count, jobCount, newCustomer, nextZaloId, past } from './customers-helpers';
import { benefit, call, cand, chatBenefitsOf, chatVisitsOf, doc, enc, entry, factsOf, phone, push, upcoming } from './chat-facts-helpers';

let NAMES: Record<string, string> = {};

beforeAll(async () => {
  await seed();
  NAMES = (await catalog()).names;
});

/** Local date `days` days before today (real clock: the decision endpoints refuse a visit in the future). */
const ago = (days: number) => localDate(past(days));

interface Contact {
  id: string | null;
  zalo: string;
  visit: Record<string, any>; // high, paid, catalog service, time known
  quoted: Record<string, any>; // medium, quoted amount, category service only, time unknown
  low: Record<string, any>;
  upcoming: Record<string, any>;
  pkg: Record<string, any>; // total 10, remaining 7
  noCount: Record<string, any>; // voucher without a count
}

/** A contact with stored guesses; `withCustomer: false` leaves it without a customers row. */
async function contact(withCustomer = true, phoneNumber = '0912345701'): Promise<Contact> {
  const cu = withCustomer ? await newCustomer() : null;
  const zalo = cu?.zalo ?? nextZaloId();
  const r = await push(
    doc([
      entry(zalo, {
        visits: [
          cand(ago(30), { services: [{ service_id: null, service_name: 'massage', basis: 'window' }, { service_id: CHAN, service_name: null, basis: 'booking' }], technician: 'Hoa' }),
          cand(ago(20), { time: null, amount_vnd: 400000, amount_source: 'quoted', services: [{ service_id: null, service_name: 'gội đầu', basis: 'booking' }], confidence: 'medium' }),
          cand(ago(10), { confidence: 'low' }),
        ],
        upcoming: [upcoming(localDate(Date.now() + 3 * 86_400_000))],
        benefits: [benefit('Gói 10 buổi gội'), benefit('Voucher sinh nhật', { kind: 'voucher', total_count: null, remaining: null })],
        phone: phone(phoneNumber, 'medium'),
      }),
    ]),
  );
  expect(r.status).toBe(200);
  const visits = await chatVisitsOf(zalo);
  const benefits = await chatBenefitsOf(zalo);
  return {
    id: cu?.id ?? null,
    zalo,
    visit: visits.find((v) => v.local_date === ago(30))!,
    quoted: visits.find((v) => v.local_date === ago(20))!,
    low: visits.find((v) => v.local_date === ago(10))!,
    upcoming: visits.find((v) => v.kind === 'upcoming')!,
    pkg: benefits.find((b) => b.kind === 'package')!,
    noCount: benefits.find((b) => b.kind === 'voucher')!,
  };
}

const visitRow = (id: string) => env.DB.prepare('SELECT * FROM visits WHERE id = ?').bind(id).first<Record<string, any>>();
const lastAudit = (action: string) => env.DB.prepare('SELECT * FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT 1').bind(action).first<Record<string, any>>();

describe('GET /staff/chat-facts/:zalo_user_id', () => {
  it('answers every row of every state with JSON parsed and service names resolved', async () => {
    const c = await contact();
    await call('POST', `/staff/chat-facts/visits/${c.low.id}/dismiss`);
    const r = await call('GET', `/staff/chat-facts/${enc(c.zalo)}`);
    expect(r.status).toBe(200);
    const f = r.body.facts;
    expect(f.visits.map((v: any) => [v.local_date, v.state])).toEqual([
      [ago(10), 'dismissed'],
      [ago(20), 'active'],
      [ago(30), 'active'],
    ]);
    expect(f.visits[2]).toEqual({
      recorded_day: false,
      id: c.visit.id,
      zalo_user_id: c.zalo,
      local_date: ago(30),
      kind: 'visit',
      visited_at: parseLocalDateTime(`${ago(30)} 15:00`),
      time_known: true,
      time: '15:00',
      services: [
        { service_id: null, service_name: 'massage', basis: 'window', name: 'massage' },
        { service_id: CHAN, service_name: null, basis: 'booking', name: NAMES[CHAN] },
      ],
      amount_vnd: 350000,
      amount_source: 'paid',
      technician: 'Hoa',
      confidence: 'high',
      signals: ['booking_confirmed', 'arrival', 'payment'],
      evidence: [expect.any(Number)],
      fact_source: 'chat_rules',
      state: 'active',
      confirmed_visit_id: null,
      analyzer_version: 'visits-rules-v1',
      imported_at: expect.any(Number),
      decided_by: null,
      decided_at: null,
    });
    expect(f.visits[1]).toMatchObject({ time_known: false, time: null, amount_source: 'quoted' });
    expect(f.visits[0]).toMatchObject({ state: 'dismissed', decided_by: 'tester' });
    expect(f.upcoming).toEqual([expect.objectContaining({ kind: 'upcoming', confidence: null, state: 'active' })]);
    expect(f.benefits.map((b: any) => b.title).sort()).toEqual(['Gói 10 buổi gội', 'Voucher sinh nhật']);
    expect(f.benefits.find((b: any) => b.kind === 'package')).toMatchObject({ total_count: 10, remaining: 7, service_name: null, state: 'active' });
    expect(f).toMatchObject({ phone_suggestion: '0912345701', analyzer_version: 'visits-rules-v1', generated_at: expect.any(Number), imported_at: expect.any(Number), model_pass: { ran: false, reason: 'disabled' } });
  });

  it('answers null for a contact without chat facts and 404 for an id that is not p: + digits', async () => {
    expect(await call('GET', `/staff/chat-facts/${enc(nextZaloId())}`)).toEqual({ status: 200, body: { facts: null } });
    for (const bad of ['p:abc', '12345', 'p:', `p:${'9'.repeat(33)}`]) {
      const r = await call('GET', `/staff/chat-facts/${enc(bad)}`);
      expect(r.status, bad).toBe(404);
      expect(r.body.error.code).toBe('not_found');
    }
    // the raw colon works too
    const c = await contact();
    expect((await call('GET', `/staff/chat-facts/${c.zalo}`)).body.facts.visits).toHaveLength(3);
  });
});

describe('POST /staff/chat-facts/visits/:id/confirm', () => {
  it('creates one staff visit from the guess, with no follow-up job, and marks the guess confirmed', async () => {
    const c = await contact();
    const jobsBefore = await count("SELECT COUNT(*) AS n FROM jobs WHERE type IN ('thank_you','check_in')");
    const r = await call('POST', `/staff/chat-facts/visits/${c.visit.id}/confirm`);
    expect(r.status).toBe(200);
    const visitId = r.body.visit.id;
    expect(visitId).toMatch(/^vis_/);
    expect(r.body.visit).toEqual({
      id: visitId,
      customer_id: c.id,
      service_id: CHAN, // the first catalog service of the guess
      service_name: null,
      name: NAMES[CHAN],
      visited_at: parseLocalDateTime(`${ago(30)} 15:00`),
      duration_min: null,
      amount_vnd: 350000, // amount_source paid
      technician: 'Hoa',
      benefit_id: null,
      source: 'staff',
      external_visit_id: null,
      recorded_by: 'tester',
      created_at: expect.any(Number),
    });
    expect(r.body.chat_visit).toMatchObject({ id: c.visit.id, state: 'confirmed', confirmed_visit_id: visitId, decided_by: 'tester', decided_at: expect.any(Number) });
    expect(await visitRow(visitId)).toMatchObject({ customer_id: c.id, source: 'staff', booking_request_id: null });

    // no follow-up job of any kind for this customer, none anywhere for this visit
    expect(await jobCount(c.id!)).toBe(0);
    expect(await count('SELECT COUNT(*) AS n FROM jobs WHERE dedupe_key LIKE ?', `${visitId}%`)).toBe(0);
    expect(await count("SELECT COUNT(*) AS n FROM jobs WHERE type IN ('thank_you','check_in')")).toBe(jobsBefore);

    const audit = await lastAudit('chat_facts.visit_confirm');
    expect(audit).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'chat_visit', entity_id: c.visit.id });
    expect(JSON.parse(audit!.after_json)).toEqual({ state: 'confirmed', visit_id: visitId, customer_id: c.id, catalog_service: true, corrected: [] });
    expect(`${audit!.before_json}${audit!.after_json}`).not.toMatch(/Hoa|massage|350000|0912345701/);

    // a second confirm, and a dismiss of the confirmed guess, answer 409 and write nothing
    for (const path of ['confirm', 'dismiss']) {
      const again = await call('POST', `/staff/chat-facts/visits/${c.visit.id}/${path}`);
      expect(again.status, path).toBe(409);
      expect(again.body.error.code).toBe('invalid_state');
    }
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', c.id)).toBe(1);
    // the next import leaves the confirmed date to staff
    const reimport = await push(doc([entry(c.zalo, { visits: [cand(ago(30))] })]));
    expect(reimport.body).toMatchObject({ visits_kept_staff: 1, visits_imported: 0 });
  });

  it('takes the corrections staff send, and keeps every guessed value staff leave out', async () => {
    const c = await contact();
    const r = await call('POST', `/staff/chat-facts/visits/${c.quoted.id}/confirm`, { service_id: BODY, amount_vnd: 380000, technician: ' Mai ', visited_at_local: `${ago(20)} 16:45` });
    expect(r.status).toBe(200);
    expect(r.body.visit).toMatchObject({ service_id: BODY, service_name: null, amount_vnd: 380000, technician: 'Mai', visited_at: parseLocalDateTime(`${ago(20)} 16:45`) });
    expect(JSON.parse((await lastAudit('chat_facts.visit_confirm'))!.after_json).corrected).toEqual(['service_id', 'amount_vnd', 'technician', 'visited_at_local']);

    // without corrections: a quoted amount is not copied (it is not money the customer paid; the console sends
    // amount_vnd when staff type what was paid); a category name becomes an 'ext:' service
    const d = await contact();
    const r2 = await call('POST', `/staff/chat-facts/visits/${d.quoted.id}/confirm`, {});
    expect(r2.status).toBe(200);
    expect(r2.body.visit).toMatchObject({ service_id: 'ext:goi-dau', service_name: 'gội đầu', name: 'gội đầu', amount_vnd: null, visited_at: parseLocalDateTime(`${ago(20)} 12:00`) });
    expect(JSON.parse((await lastAudit('chat_facts.visit_confirm'))!.after_json)).toMatchObject({ catalog_service: false });
    expect((await lastAudit('chat_facts.visit_confirm'))!.after_json).not.toMatch(/gội|goi-dau/);

    // null clears a guessed value
    const e = await contact();
    const r3 = await call('POST', `/staff/chat-facts/visits/${e.visit.id}/confirm`, { amount_vnd: null, technician: null });
    expect(r3.body.visit).toMatchObject({ amount_vnd: null, technician: null });
  });

  it('answers 422 for a bad correction, 409 for a booking, a dismissed guess or a contact without a customers row, 404 for an unknown id', async () => {
    const c = await contact();
    const bad: Array<[unknown, string]> = [
      [{ service_id: 'khong-co-dich-vu' }, 'service_id'],
      [{ service_id: 12 }, 'service_id'],
      [{ amount_vnd: -1 }, 'amount_vnd'],
      [{ amount_vnd: '350000' }, 'amount_vnd'],
      [{ technician: 'Lan\nMai' }, 'technician'],
      [{ technician: 'x'.repeat(61) }, 'technician'],
      [{ visited_at_local: 'hôm qua' }, 'visited_at_local'],
      [{ visited_at_local: `${localDate(Date.now() + 2 * 86_400_000)} 10:00` }, 'visited_at_local'],
      [{ amount: 1 }, 'amount'],
      [[1], 'body'],
    ];
    for (const [body, field] of bad) {
      const r = await call('POST', `/staff/chat-facts/visits/${c.visit.id}/confirm`, body);
      expect(r.status, JSON.stringify(body)).toBe(422);
      expect(r.body.error.details.field, JSON.stringify(body)).toBe(field);
    }
    expect((await call('POST', `/staff/chat-facts/visits/${c.visit.id}/confirm`, undefined, '{oops')).status).toBe(400);

    const booking = await call('POST', `/staff/chat-facts/visits/${c.upcoming.id}/confirm`);
    expect(booking.status).toBe(409);
    expect((await call('POST', `/staff/chat-facts/visits/${c.low.id}/dismiss`)).status).toBe(200);
    expect((await call('POST', `/staff/chat-facts/visits/${c.low.id}/confirm`)).status).toBe(409);
    expect((await call('POST', '/staff/chat-facts/visits/chv_missing/confirm')).status).toBe(404);

    const noRow = await contact(false, '0912345702');
    const r = await call('POST', `/staff/chat-facts/visits/${noRow.visit.id}/confirm`);
    expect(r.status).toBe(409);
    expect(r.body.error).toMatchObject({ code: 'invalid_state', message: 'khách chưa có hồ sơ' });
    // a deleted customers row is no row
    const gone = await contact();
    await env.DB.prepare('UPDATE customers SET deleted_at = 1 WHERE id = ?').bind(gone.id).run();
    expect((await call('POST', `/staff/chat-facts/visits/${gone.visit.id}/confirm`)).status).toBe(409);

    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', c.id)).toBe(0);
    expect((await chatVisitsOf(c.zalo)).find((v) => v.id === c.visit.id)).toMatchObject({ state: 'active' });
  });
});

describe('POST /staff/chat-facts/visits/:id/dismiss', () => {
  it('turns an active visit or upcoming booking into a tombstone, once', async () => {
    const c = await contact();
    for (const row of [c.visit, c.upcoming]) {
      const r = await call('POST', `/staff/chat-facts/visits/${row.id}/dismiss`);
      expect(r.status).toBe(200);
      expect(r.body.chat_visit).toMatchObject({ id: row.id, state: 'dismissed', decided_by: 'tester', confirmed_visit_id: null });
      expect((await call('POST', `/staff/chat-facts/visits/${row.id}/dismiss`)).status).toBe(409);
    }
    expect(JSON.parse((await lastAudit('chat_facts.visit_dismiss'))!.after_json)).toEqual({ state: 'dismissed' });
    expect(await count('SELECT COUNT(*) AS n FROM audit_log WHERE action = ? AND entity_id IN (?, ?)', 'chat_facts.visit_dismiss', c.visit.id, c.upcoming.id)).toBe(2);
    expect((await call('POST', '/staff/chat-facts/visits/chv_missing/dismiss')).status).toBe(404);
    expect(await jobCount(c.id!)).toBe(0);
  });
});

describe('POST /staff/chat-facts/benefits/:id/confirm and dismiss', () => {
  it('creates a customer benefit from the guess, used = total - remaining, and marks the guess confirmed', async () => {
    const c = await contact();
    const r = await call('POST', `/staff/chat-facts/benefits/${c.pkg.id}/confirm`);
    expect(r.status).toBe(200);
    expect(r.body.benefit).toMatchObject({ customer_id: c.id, kind: 'package', title: 'Gói 10 buổi gội', total_count: 10, used_count: 3, remaining: 7, status: 'active', recorded_by: 'tester', expires_at: null });
    expect(r.body.benefit.id).toMatch(/^ben_/);
    expect(r.body.chat_benefit).toMatchObject({ id: c.pkg.id, state: 'confirmed', confirmed_benefit_id: r.body.benefit.id, decided_by: 'tester' });
    expect(await count('SELECT COUNT(*) AS n FROM customer_benefits WHERE customer_id = ?', c.id)).toBe(1);
    const audit = await lastAudit('chat_facts.benefit_confirm');
    expect(JSON.parse(audit!.after_json)).toMatchObject({ benefit_id: r.body.benefit.id, kind: 'package', total_count: 10, used_count: 3, title_changed: false });
    expect(audit!.after_json).not.toMatch(/Gói|buổi/);
    expect((await call('POST', `/staff/chat-facts/benefits/${c.pkg.id}/confirm`)).status).toBe(409);

    // a guess without a count needs total_count; used_count defaults to 0 without a remaining count
    const missing = await call('POST', `/staff/chat-facts/benefits/${c.noCount.id}/confirm`, {});
    expect(missing.status).toBe(422);
    expect(missing.body.error.details.field).toBe('total_count');
    const ok = await call('POST', `/staff/chat-facts/benefits/${c.noCount.id}/confirm`, { total_count: 1, title: 'Voucher 1 buổi', expires_at: Date.UTC(2027, 0, 31, 16, 59) });
    expect(ok.status).toBe(200);
    expect(ok.body.benefit).toMatchObject({ kind: 'voucher', title: 'Voucher 1 buổi', total_count: 1, used_count: 0, expires_on: '2027-01-31' });
    expect(JSON.parse((await lastAudit('chat_facts.benefit_confirm'))!.after_json)).toMatchObject({ title_changed: true });
    expect((await lastAudit('chat_facts.benefit_confirm'))!.after_json).not.toMatch(/Voucher/);
  });

  it('validates the body, needs a customers row, and dismisses once', async () => {
    const c = await contact();
    const bad: Array<[unknown, string]> = [
      [{ title: '' }, 'title'],
      [{ title: 'x'.repeat(121) }, 'title'],
      [{ total_count: 0 }, 'total_count'],
      [{ total_count: 1001 }, 'total_count'],
      [{ used_count: 11 }, 'used_count'],
      [{ total_count: 5 }, 'used_count'], // remaining 7 is above 5: staff must say how many were used
      [{ expires_at: 'mai' }, 'expires_at'],
      [{ remaining: 3 }, 'remaining'],
    ];
    for (const [body, field] of bad) {
      const r = await call('POST', `/staff/chat-facts/benefits/${c.pkg.id}/confirm`, body);
      expect(r.status, JSON.stringify(body)).toBe(422);
      expect(r.body.error.details.field, JSON.stringify(body)).toBe(field);
    }
    expect((await call('POST', `/staff/chat-facts/benefits/${c.pkg.id}/confirm`, { total_count: 5, used_count: 5 })).body.benefit).toMatchObject({ total_count: 5, used_count: 5, remaining: 0 });

    const noRow = await contact(false, '0912345703');
    const r = await call('POST', `/staff/chat-facts/benefits/${noRow.pkg.id}/confirm`);
    expect(r.status).toBe(409);
    expect(r.body.error.message).toBe('khách chưa có hồ sơ');

    const d = await call('POST', `/staff/chat-facts/benefits/${c.noCount.id}/dismiss`);
    expect(d.status).toBe(200);
    expect(d.body.chat_benefit).toMatchObject({ state: 'dismissed', decided_by: 'tester', confirmed_benefit_id: null });
    expect((await call('POST', `/staff/chat-facts/benefits/${c.noCount.id}/dismiss`)).status).toBe(409);
    expect((await call('POST', `/staff/chat-facts/benefits/${c.noCount.id}/confirm`, { total_count: 1 })).status).toBe(409);
    expect((await call('POST', '/staff/chat-facts/benefits/chb_missing/dismiss')).status).toBe(404);
    expect(JSON.parse((await lastAudit('chat_facts.benefit_dismiss'))!.after_json)).toEqual({ state: 'dismissed' });
  });
});

describe('phone suggestion', () => {
  it('accept copies the suggestion into an empty phone and clears it', async () => {
    const c = await contact(true, '0912345711');
    const r = await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/accept`);
    expect(r.status).toBe(200);
    expect(r.body.customer).toMatchObject({ id: c.id, phone: '0912345711', channel: 'personal', zalo_user_id: c.zalo });
    expect(r.body.facts.phone_suggestion).toBeNull();
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(c.id).first<{ phone: string }>())!.phone).toBe('0912345711');
    const audit = await lastAudit('chat_facts.phone_accept');
    expect(audit).toMatchObject({ entity: 'customer', entity_id: c.id });
    expect(JSON.parse(audit!.after_json)).toEqual({ has_phone: true });
    // nothing to accept any more
    expect((await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/accept`)).status).toBe(409);
    expect((await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/dismiss`)).status).toBe(409);
  });

  it('accept answers 409 when the customer already has a phone or has no customers row', async () => {
    const c = await contact(true, '0912345712');
    await env.DB.prepare("UPDATE customers SET phone = '0901234500' WHERE id = ?").bind(c.id).run();
    const r = await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/accept`);
    expect(r.status).toBe(409);
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(c.id).first<{ phone: string }>())!.phone).toBe('0901234500');
    expect((await factsOf(c.zalo))!.phone_suggestion).toBe('0912345712');

    const noRow = await contact(false, '0912345713');
    const r2 = await call('POST', `/staff/chat-facts/${enc(noRow.zalo)}/phone/accept`);
    expect(r2.status).toBe(409);
    expect(r2.body.error.message).toBe('khách chưa có hồ sơ');
    expect((await call('POST', `/staff/chat-facts/${enc('p:abc')}/phone/accept`)).status).toBe(404);
    expect((await call('POST', `/staff/chat-facts/${enc(nextZaloId())}/phone/accept`)).status).toBe(409);
  });

  it('dismiss moves the suggestion aside for good', async () => {
    const c = await contact(true, '0912345714');
    const r = await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/dismiss`);
    expect(r.status).toBe(200);
    expect(r.body.facts.phone_suggestion).toBeNull();
    expect(await factsOf(c.zalo)).toMatchObject({ phone_suggestion: null, phone_state: 'dismissed', phone_dismissed: '0912345714' });
    expect(JSON.parse((await lastAudit('chat_facts.phone_dismiss'))!.after_json)).toEqual({ phone_state: 'dismissed' });
    expect((await push(doc([entry(c.zalo, { phone: phone('0912345714', 'medium') })]))).body).toMatchObject({ phone_suggestions: 0 });
    expect((await factsOf(c.zalo))!.phone_suggestion).toBeNull();
  });
});

describe('privacy of audit rows and log lines', () => {
  const spies: Array<{ mock: { calls: unknown[][] }; mockRestore: () => void }> = [];
  beforeEach(() => {
    for (const m of ['log', 'info', 'warn', 'error', 'debug'] as const) spies.push(vi.spyOn(console, m) as unknown as (typeof spies)[number]);
  });
  afterEach(() => {
    while (spies.length) spies.pop()!.mockRestore();
  });

  it('no audit row and no log line carries a phone number, a title, a technician or a service name from chat', async () => {
    console.info('spy-probe'); // the spies see what this isolate logs, the worker included (app.fetch runs here)
    const auditFrom = (await env.DB.prepare('SELECT COALESCE(MAX(id), 0) AS n FROM audit_log').first<{ n: number }>())!.n;
    const numbers = ['0912345791', '0912345792', '0912345793'];
    const withRow = await newCustomer();
    const another = await newCustomer();
    const noRow = nextZaloId();
    await push(
      doc([
        entry(withRow.zalo, { visits: [cand(ago(40), { technician: 'Thảo Vy', services: [{ service_id: null, service_name: 'xông hơi', basis: 'window' }] })], benefits: [benefit('Gói bí mật 7 buổi')], phone: phone(numbers[0]!, 'medium') }),
        entry(another.zalo, { phone: phone(numbers[1]!, 'high') }),
        entry(noRow, { phone: phone(numbers[2]!, 'high') }),
      ]),
    );
    await push({ ...doc([entry(withRow.zalo, { phone: phone(numbers[0]!, 'medium') })]), dry_run: true });
    // error paths too: a 422 that names the phone field, a 409
    await push(doc([entry(withRow.zalo, { phone: { ...phone(numbers[0]!), confidence: 'certain' } })]));
    await call('POST', `/staff/chat-facts/${enc(noRow)}/phone/accept`);
    const v = (await chatVisitsOf(withRow.zalo))[0]!;
    const b = (await chatBenefitsOf(withRow.zalo))[0]!;
    expect((await call('POST', `/staff/chat-facts/visits/${v.id}/confirm`)).status).toBe(200);
    expect((await call('POST', `/staff/chat-facts/benefits/${b.id}/confirm`, { title: 'Gói riêng tư 7 buổi' })).status).toBe(200);
    expect((await call('POST', `/staff/chat-facts/${enc(withRow.zalo)}/phone/accept`)).status).toBe(200);
    expect((await call('POST', `/staff/chat-facts/${enc(noRow)}/phone/dismiss`)).status).toBe(200);

    const { results } = await env.DB.prepare('SELECT action, entity_id, before_json, after_json FROM audit_log WHERE id > ?').bind(auditFrom).all<Record<string, string | null>>();
    expect(results.map((r) => r.action).sort()).toEqual(
      ['chat_facts.benefit_confirm', 'chat_facts.import', 'chat_facts.phone_accept', 'chat_facts.phone_dismiss', 'chat_facts.visit_confirm'].sort(),
    );
    const text = JSON.stringify(results);
    for (const secret of [...numbers, ...numbers.map((n) => n.slice(1)), 'Thảo Vy', 'xông', 'xong-hoi', 'bí mật', 'riêng tư']) expect(text, secret).not.toContain(secret);

    const logged = spies.flatMap((s) => s.mock.calls.map((args) => args.map((a) => (typeof a === 'string' ? a : JSON.stringify(a))).join(' '))).join('\n');
    expect(logged).toContain('spy-probe');
    for (const secret of [...numbers, ...numbers.map((n) => n.slice(1)), 'Thảo Vy', 'bí mật']) expect(logged, secret).not.toContain(secret);
  });
});

describe('no message, draft or follow-up job comes out of the chat facts endpoints', () => {
  it('leaves outbox, messages and jobs untouched', async () => {
    const tally = async () => [
      await count('SELECT COUNT(*) AS n FROM outbox'),
      await count('SELECT COUNT(*) AS n FROM messages'),
      await count('SELECT COUNT(*) AS n FROM jobs'),
      await count('SELECT COUNT(*) AS n FROM drafts'),
    ];
    const before = await tally();
    const c = await contact(true, '0912345721');
    await call('POST', `/staff/chat-facts/visits/${c.visit.id}/confirm`);
    await call('POST', `/staff/chat-facts/visits/${c.quoted.id}/dismiss`);
    await call('POST', `/staff/chat-facts/benefits/${c.pkg.id}/confirm`);
    await call('POST', `/staff/chat-facts/${enc(c.zalo)}/phone/accept`);
    await call('GET', '/staff/chat-facts/eligible');
    expect(await tally()).toEqual(before);
  });
});
