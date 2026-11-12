// POST /staff/chat-facts/import and GET /staff/chat-facts/eligible (docs/contracts.md section 15.11). All data is
// synthetic: invented ids, phone numbers like 0912345678, dates in 2026.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { parseLocalDateTime } from '../src/staff-api/customers';
import { seed } from './core-helpers';
import { CHAN, GOI, addProfile, addRole, addVisit, count, newCustomer, nextZaloId } from './customers-helpers';
import {
  GENERATED_AT,
  VERSION,
  addConsent,
  benefit,
  call,
  cand,
  chatBenefitsOf,
  chatSnapshot,
  chatVisitsOf,
  doc,
  entry,
  factsOf,
  nonZero,
  phone,
  push,
  setChatState,
  upcoming,
} from './chat-facts-helpers';

beforeAll(async () => {
  await seed();
});

const ZERO = {
  customers: 0,
  unmatched: 0,
  skipped_internal: 0,
  skipped_deleted: 0,
  visits_imported: 0,
  visits_updated: 0,
  visits_removed: 0,
  visits_kept_staff: 0,
  visits_tombstoned: 0,
  phones_set: 0,
  phones_taken: 0,
  phone_suggestions: 0,
  benefits_upserted: 0,
  benefits_kept_staff: 0,
  dry_run: false,
};

const auditCount = () => count("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'chat_facts.import'");

describe('POST /staff/chat-facts/import', () => {
  it('stores visits, upcoming bookings, benefits and the contact row, and counts each of them', async () => {
    const a = await newCustomer();
    const b = nextZaloId(); // no customers row yet
    const r = await push(
      doc([
        entry(a.zalo, {
          visits: [
            cand('2026-10-17', { services: [{ service_id: GOI, service_name: 'Gội đầu', basis: 'booking' }, { service_id: null, service_name: 'massage', basis: 'visit_day' }] }),
            cand('2026-10-30', { time: null, confidence: 'low', amount_vnd: null, amount_source: null, technician: null, services: [] }),
          ],
          upcoming: [upcoming('2026-11-20')],
          benefits: [benefit('Gói 10 buổi gội')],
          phone: phone('0912345601', 'medium'),
        }),
        entry(b, { visits: [cand('2026-09-02', { source: 'chat_rules+model', confidence: 'medium' })], phone: phone('+84 912 345 602', 'high') }),
      ]),
    );
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ ...ZERO, customers: 2, unmatched: 1, visits_imported: 4, phone_suggestions: 2, benefits_upserted: 1 });

    const rows = await chatVisitsOf(a.zalo);
    expect(rows.map((x) => [x.kind, x.local_date, x.state])).toEqual([
      ['upcoming', '2026-11-20', 'active'],
      ['visit', '2026-10-17', 'active'],
      ['visit', '2026-10-30', 'active'],
    ]);
    const [up, v1, v2] = rows;
    expect(v1).toMatchObject({
      visited_at: parseLocalDateTime('2026-10-17 15:00'),
      time_known: 1,
      amount_vnd: 350000,
      amount_source: 'paid',
      technician: 'Lan',
      confidence: 'high',
      fact_source: 'chat_rules',
      analyzer_version: VERSION,
      confirmed_visit_id: null,
      decided_by: null,
    });
    expect(v1!.id).toMatch(/^chv_/);
    expect(JSON.parse(v1!.services_json)).toEqual([
      { service_id: GOI, service_name: 'Gội đầu', basis: 'booking' },
      { service_id: null, service_name: 'massage', basis: 'visit_day' },
    ]);
    expect(JSON.parse(v1!.signals_json)).toEqual(['booking_confirmed', 'arrival', 'payment']);
    expect(JSON.parse(v1!.evidence_json)).toEqual([GENERATED_AT - 86_400_000]);
    // unknown time: 12:00 local, time_known 0
    expect(v2).toMatchObject({ visited_at: parseLocalDateTime('2026-10-30 12:00'), time_known: 0, confidence: 'low', amount_vnd: null, technician: null, services_json: '[]' });
    expect(up).toMatchObject({ kind: 'upcoming', confidence: null });

    const ben = await chatBenefitsOf(a.zalo);
    expect(ben).toEqual([
      expect.objectContaining({ kind: 'package', title: 'Gói 10 buổi gội', title_key: 'goi 10 buoi goi', total_count: 10, remaining: 7, stated_by: 'owner', confidence: 'high', state: 'active' }),
    ]);
    expect(await factsOf(a.zalo)).toMatchObject({
      analyzer_version: VERSION,
      generated_at: GENERATED_AT,
      messages: 120,
      phone_suggestion: '0912345601',
      phone_state: null,
      phone_dismissed: null,
      model_pass_json: JSON.stringify({ ran: false, reason: 'disabled' }),
    });
    // a high number of a contact without a customers row waits as a suggestion (normalised)
    expect(await factsOf(b)).toMatchObject({ phone_suggestion: '0912345602' });
    expect((await chatVisitsOf(b))[0]).toMatchObject({ fact_source: 'chat_rules+model', confidence: 'medium' });

    // one audit row with the counters and the analyzer version only
    const audit = await env.DB.prepare("SELECT actor_id, entity, entity_id, before_json, after_json FROM audit_log WHERE action = 'chat_facts.import' ORDER BY id DESC LIMIT 1").first<Record<string, string | null>>();
    expect(audit).toMatchObject({ actor_id: 'tester', entity: 'chat_facts', entity_id: null, before_json: null });
    const { dry_run: _d, ...counters } = r.body;
    expect(JSON.parse(audit!.after_json!)).toEqual({ ...counters, analyzer_version: VERSION });
    expect(audit!.after_json).not.toMatch(/p:|091234560|Lan|Gội|massage/);
  });

  it('the same document a second time changes nothing', async () => {
    const a = await newCustomer();
    const b = nextZaloId();
    const body = doc([
      entry(a.zalo, { visits: [cand('2026-08-01'), cand('2026-09-01', { confidence: 'medium' })], upcoming: [upcoming('2026-12-01')], benefits: [benefit('Voucher sinh nhật', { kind: 'voucher', total_count: null, remaining: null })], phone: phone('0912345611', 'high') }),
      entry(b, { visits: [cand('2026-07-07')], phone: phone('0912345612', 'medium') }),
    ]);
    const first = await push(body);
    expect(first.body).toEqual({ ...ZERO, customers: 2, unmatched: 1, visits_imported: 4, phones_set: 1, phone_suggestions: 1, benefits_upserted: 1 });
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first<{ phone: string }>())!.phone).toBe('0912345611');
    const snap = await chatSnapshot();
    const phoneBefore = await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first();

    const second = await push(body);
    expect(second.body).toEqual({ ...ZERO, customers: 2, unmatched: 1 });
    expect(await chatSnapshot()).toEqual(snap);
    expect(await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first()).toEqual(phoneBefore);
  });

  it('updates a changed guess in place and removes the dates the document no longer has', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { visits: [cand('2026-06-01'), cand('2026-06-15')], upcoming: [upcoming('2026-06-20')] })]));
    const before = await chatVisitsOf(a.zalo);
    const june1 = before.find((x) => x.local_date === '2026-06-01')!;

    // later run: 1 June has another amount and technician, 15 June is gone, the booking of 20 June is in the past now
    const r = await push(doc([entry(a.zalo, { visits: [cand('2026-06-01', { amount_vnd: 420000, technician: 'số 8' })] })], { analyzer_version: VERSION }));
    expect(r.body).toEqual({ ...ZERO, customers: 1, visits_updated: 1, visits_removed: 2 });
    const after = await chatVisitsOf(a.zalo);
    expect(after).toHaveLength(1);
    expect(after[0]).toMatchObject({ id: june1.id, amount_vnd: 420000, technician: 'số 8', state: 'active' });

    // a new analyzer version is a change of a stored field: the row is updated once, then left alone
    expect((await push(doc([entry(a.zalo, { visits: [cand('2026-06-01', { amount_vnd: 420000, technician: 'số 8' })] })], { analyzer_version: 'visits-rules-v2' }))).body).toMatchObject({ visits_updated: 1 });
    expect((await push(doc([entry(a.zalo, { visits: [cand('2026-06-01', { amount_vnd: 420000, technician: 'số 8' })] })], { analyzer_version: 'visits-rules-v2' }))).body).toMatchObject({ visits_updated: 0, visits_imported: 0 });
    // a document with no visits removes the last active row
    expect((await push(doc([entry(a.zalo)]))).body).toMatchObject({ visits_removed: 1 });
    expect(await chatVisitsOf(a.zalo)).toEqual([]);
  });

  it('keeps a dismissed date as a tombstone and skips a confirmed date', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { visits: [cand('2026-05-01'), cand('2026-05-02'), cand('2026-05-03')], upcoming: [upcoming('2026-12-24')] })]));
    const rows = await chatVisitsOf(a.zalo);
    const byDate = (d: string, kind = 'visit') => rows.find((x) => x.local_date === d && x.kind === kind)!;
    await setChatState('chat_visits', byDate('2026-05-01').id, 'dismissed');
    await setChatState('chat_visits', byDate('2026-05-02').id, 'confirmed');
    await setChatState('chat_visits', byDate('2026-12-24', 'upcoming').id, 'dismissed');

    const changed = { amount_vnd: 990000, technician: 'Mai' };
    const r = await push(
      doc([entry(a.zalo, { visits: [cand('2026-05-01', changed), cand('2026-05-02', changed), cand('2026-05-03', changed)], upcoming: [upcoming('2026-12-24', { time: '10:00' })] })]),
    );
    expect(r.body).toEqual({ ...ZERO, customers: 1, visits_tombstoned: 2, visits_kept_staff: 1, visits_updated: 1 });
    const after = await chatVisitsOf(a.zalo);
    expect(after.find((x) => x.local_date === '2026-05-01')).toMatchObject({ state: 'dismissed', amount_vnd: 350000, technician: 'Lan' });
    expect(after.find((x) => x.local_date === '2026-05-02')).toMatchObject({ state: 'confirmed', amount_vnd: 350000 });
    expect(after.find((x) => x.local_date === '2026-05-03')).toMatchObject({ state: 'active', amount_vnd: 990000 });

    // a document without those dates removes only the active row: the decided ones stay
    const r2 = await push(doc([entry(a.zalo)]));
    expect(r2.body).toEqual({ ...ZERO, customers: 1, visits_removed: 1 });
    expect((await chatVisitsOf(a.zalo)).map((x) => [x.local_date, x.state])).toEqual([
      ['2026-12-24', 'dismissed'],
      ['2026-05-01', 'dismissed'],
      ['2026-05-02', 'confirmed'],
    ]);
    // the tombstone keeps the date out on every later run
    expect((await push(doc([entry(a.zalo, { visits: [cand('2026-05-01')] })]))).body).toEqual({ ...ZERO, customers: 1, visits_tombstoned: 1 });
  });

  it('skips a date on which the customer has a recorded visit of any source', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { visits: [cand('2026-04-10')] })]));
    // staff then record visits on 10 and 11 April (an import row and a staff row)
    await addVisit(a.id, parseLocalDateTime('2026-04-10 09:00')!, CHAN, { source: 'import' });
    await addVisit(a.id, parseLocalDateTime('2026-04-11 23:30')!, GOI, { source: 'staff' });
    const r = await push(doc([entry(a.zalo, { visits: [cand('2026-04-10', { amount_vnd: 500000 }), cand('2026-04-11', { time: '10:00' }), cand('2026-04-12')] })]));
    expect(r.body).toEqual({ ...ZERO, customers: 1, visits_kept_staff: 2, visits_imported: 1 });
    const rows = await chatVisitsOf(a.zalo);
    // the row of 10 April is left as it was (not updated), 11 April is never stored
    expect(rows.map((x) => [x.local_date, x.amount_vnd])).toEqual([
      ['2026-04-10', 350000],
      ['2026-04-12', 350000],
    ]);
  });

  it('skips internal and quiet contacts and deletes only their active rows', async () => {
    const becomesStaff = await newCustomer();
    await push(doc([entry(becomesStaff.zalo, { visits: [cand('2026-03-01'), cand('2026-03-02')], upcoming: [upcoming('2026-12-01')], benefits: [benefit('Gói 5 buổi'), benefit('Gói 3 buổi')], phone: phone('0912345621') })]));
    const v = await chatVisitsOf(becomesStaff.zalo);
    await setChatState('chat_visits', v.find((x) => x.local_date === '2026-03-01')!.id, 'dismissed');
    const bs = await chatBenefitsOf(becomesStaff.zalo);
    await setChatState('chat_benefits', bs[0]!.id, 'confirmed');
    await addRole(becomesStaff.zalo, 'staff', 'staff');

    const manager = nextZaloId();
    await addRole(manager, 'manager');
    const quiet = await Promise.all(['family', 'friend', 'personal', 'staff'].map(async (relationship) => {
      const z = nextZaloId();
      await addProfile(z, { relationship });
      return z;
    }));
    const labelledCustomer = nextZaloId(); // a role 'customer' overrides the analyzer's relationship
    await addProfile(labelledCustomer, { relationship: 'family' });
    await addRole(labelledCustomer, 'customer');
    const unknownProfile = nextZaloId();
    await addProfile(unknownProfile, { relationship: 'unknown' });

    const visit = { visits: [cand('2026-03-05')], phone: phone('0912345622') };
    const r = await push(doc([entry(becomesStaff.zalo, visit), entry(manager, visit), ...quiet.map((z) => entry(z, visit)), entry(labelledCustomer, visit), entry(unknownProfile, visit)]));
    expect(r.body).toEqual({ ...ZERO, skipped_internal: 6, customers: 2, unmatched: 2, visits_imported: 2, phone_suggestions: 2 });

    expect((await chatVisitsOf(becomesStaff.zalo)).map((x) => [x.local_date, x.state])).toEqual([['2026-03-01', 'dismissed']]);
    expect((await chatBenefitsOf(becomesStaff.zalo)).map((x) => x.state)).toEqual(['confirmed']);
    expect(await factsOf(becomesStaff.zalo)).toMatchObject({ phone_suggestion: null });
    for (const z of [manager, ...quiet]) {
      expect(await chatVisitsOf(z), z).toEqual([]);
      expect(await factsOf(z), z).toBeNull();
    }
    expect(await chatVisitsOf(labelledCustomer)).toHaveLength(1);
    expect(await chatVisitsOf(unknownProfile)).toHaveLength(1);
    // a second run deletes nothing more and counts the same
    expect((await push(doc([entry(becomesStaff.zalo, visit), entry(manager, visit)]))).body).toEqual({ ...ZERO, skipped_internal: 2 });
  });

  it('skips a contact whose customers row is deleted and removes its chat rows', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { visits: [cand('2026-02-01')], benefits: [benefit('Gói 4 buổi')], phone: phone('0912345631') })]));
    await env.DB.prepare('UPDATE customers SET deleted_at = 1 WHERE id = ?').bind(a.id).run();
    const r = await push(doc([entry(a.zalo, { visits: [cand('2026-02-01')] })]));
    expect(r.body).toEqual({ ...ZERO, skipped_deleted: 1 });
    expect(await chatVisitsOf(a.zalo)).toEqual([]);
    expect(await chatBenefitsOf(a.zalo)).toEqual([]);
    expect(await factsOf(a.zalo)).toBeNull();
  });

  it('applies the phone rules: set an empty phone, never overwrite, suggest a medium number, never suggest a dismissed one', async () => {
    const empty = await newCustomer();
    const blank = await newCustomer({ phone: '  ' });
    const has = await newCustomer({ phone: '0901111222' });
    const mediumEmpty = await newCustomer();
    const noRow = nextZaloId();
    const r = await push(
      doc([
        entry(empty.zalo, { phone: phone('0912345641', 'high') }),
        entry(blank.zalo, { phone: phone('84912345642', 'high') }),
        entry(has.zalo, { phone: phone('0912345643', 'high') }),
        entry(mediumEmpty.zalo, { phone: phone('0912345644', 'medium') }),
        entry(noRow, { phone: phone('0912345645', 'high') }),
      ]),
    );
    expect(r.body).toEqual({ ...ZERO, customers: 5, unmatched: 1, phones_set: 2, phone_suggestions: 2 });
    const phoneOf = async (id: string) => (await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(id).first<{ phone: string | null }>())!.phone;
    expect(await phoneOf(empty.id)).toBe('0912345641');
    expect(await phoneOf(blank.id)).toBe('0912345642');
    expect(await phoneOf(has.id)).toBe('0901111222');
    expect(await phoneOf(mediumEmpty.id)).toBeNull();
    expect((await factsOf(empty.zalo))!.phone_suggestion).toBeNull();
    expect((await factsOf(has.zalo))!.phone_suggestion).toBeNull();
    expect((await factsOf(mediumEmpty.zalo))!.phone_suggestion).toBe('0912345644');
    expect((await factsOf(noRow))!.phone_suggestion).toBe('0912345645');

    // staff dismiss the suggestion: the same number is never suggested again, at medium or at high
    expect((await call('POST', `/staff/chat-facts/${encodeURIComponent(mediumEmpty.zalo)}/phone/dismiss`)).status).toBe(200);
    const again = await push(doc([entry(mediumEmpty.zalo, { phone: phone('0912345644', 'high') })]));
    expect(again.body).toEqual({ ...ZERO, customers: 1 });
    expect(await phoneOf(mediumEmpty.id)).toBeNull();
    expect(await factsOf(mediumEmpty.zalo)).toMatchObject({ phone_suggestion: null, phone_state: 'dismissed', phone_dismissed: '0912345644' });
    // another number is suggested
    expect((await push(doc([entry(mediumEmpty.zalo, { phone: phone('0912345646') })]))).body).toMatchObject({ phone_suggestions: 1 });
    // an entry without a phone leaves the stored suggestion alone
    expect((await push(doc([entry(mediumEmpty.zalo)]))).body).toMatchObject({ phone_suggestions: 0 });
    expect((await factsOf(mediumEmpty.zalo))!.phone_suggestion).toBe('0912345646');
  });

  it('matches benefits by title key, keeps tombstones and confirmed ones, removes the others', async () => {
    const a = await newCustomer();
    const r1 = await push(doc([entry(a.zalo, { benefits: [benefit('Gói 10 buổi'), benefit('Voucher sinh nhật', { kind: 'voucher', total_count: 1, remaining: 1 }), benefit('Combo 5 buổi', { total_count: 5, remaining: 5 })] })]));
    expect(r1.body).toMatchObject({ benefits_upserted: 3 });
    const before = await chatBenefitsOf(a.zalo);
    const goi = before.find((x) => x.title_key === 'goi 10 buoi')!;
    const combo = before.find((x) => x.title_key === 'combo 5 buoi')!;
    await setChatState('chat_benefits', combo.id, 'dismissed');

    // same key written differently: the same row, updated; the voucher is gone; the dismissed combo stays
    const r2 = await push(doc([entry(a.zalo, { benefits: [benefit('GÓI 10  buổi', { remaining: 6 }), benefit('Combo 5 buổi', { remaining: 2 })] })]));
    expect(r2.body).toEqual({ ...ZERO, customers: 1, benefits_upserted: 1 });
    const after = await chatBenefitsOf(a.zalo);
    expect(after.map((x) => [x.title_key, x.state])).toEqual([
      ['combo 5 buoi', 'dismissed'],
      ['goi 10 buoi', 'active'],
    ]);
    expect(after.find((x) => x.title_key === 'goi 10 buoi')).toMatchObject({ id: goi.id, title: 'GÓI 10  buổi', remaining: 6 });
    expect(after.find((x) => x.title_key === 'combo 5 buoi')).toMatchObject({ remaining: 5 });

    await setChatState('chat_benefits', goi.id, 'confirmed');
    const r3 = await push(doc([entry(a.zalo, { benefits: [benefit('Gói 10 buổi', { remaining: 2 })] })]));
    expect(r3.body).toEqual({ ...ZERO, customers: 1, benefits_kept_staff: 1 });

    // two titles of one entry that fold to the same key are one benefit: the latest statement wins
    const b = await newCustomer();
    await push(doc([entry(b.zalo, { benefits: [benefit('Gói 6 buổi', { remaining: 4, at: GENERATED_AT - 1000 }), benefit('gói 6 buổi', { remaining: 3, at: GENERATED_AT - 2000 })] })]));
    expect(await chatBenefitsOf(b.zalo)).toEqual([expect.objectContaining({ title: 'Gói 6 buổi', remaining: 4 })]);
  });

  it('a dry run computes every counter and writes nothing', async () => {
    const a = await newCustomer();
    const internal = nextZaloId();
    await push(doc([entry(a.zalo, { visits: [cand('2026-01-05'), cand('2026-01-06'), cand('2026-01-07')], benefits: [benefit('Gói 2 buổi')] }), entry(internal, { visits: [cand('2026-01-05')] })]));
    const rows = await chatVisitsOf(a.zalo);
    await setChatState('chat_visits', rows.find((x) => x.local_date === '2026-01-05')!.id, 'dismissed');
    await addVisit(a.id, parseLocalDateTime('2026-01-08 10:00')!, GOI);
    await addRole(internal, 'manager');

    const next = doc([
      entry(a.zalo, { visits: [cand('2026-01-05'), cand('2026-01-07', { amount_vnd: 123000 }), cand('2026-01-08'), cand('2026-01-09')], upcoming: [upcoming('2026-12-12')], benefits: [benefit('Gói 3 buổi')], phone: phone('0912345651', 'high') }),
      entry(internal, { visits: [cand('2026-01-05')] }),
      entry(nextZaloId(), { phone: phone('0912345652') }),
    ]);
    const snap = await chatSnapshot();
    const audits = await auditCount();
    const dry = await push({ ...next, dry_run: true });
    expect(dry.status).toBe(200);
    expect(await chatSnapshot()).toEqual(snap);
    expect(await auditCount()).toBe(audits);
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first<{ phone: string | null }>())!.phone).toBeNull();

    const real = await push(next);
    expect(nonZero(dry.body)).toEqual({ ...nonZero(real.body), dry_run: true });
    expect(real.body).toEqual({
      ...ZERO,
      customers: 2,
      unmatched: 1,
      skipped_internal: 1,
      visits_imported: 2,
      visits_updated: 1,
      visits_removed: 1,
      visits_kept_staff: 1,
      visits_tombstoned: 1,
      phones_set: 1,
      phone_suggestions: 1,
      benefits_upserted: 1,
    });
    expect(await auditCount()).toBe(audits + 1);
  });

  it('answers 422 naming the field for a bad document, and writes nothing', async () => {
    const z = nextZaloId();
    const e = (over: Record<string, unknown>) => doc([entry(z, over)]);
    const v = (over: Record<string, unknown>) => e({ visits: [{ ...cand('2026-03-03'), ...over }] });
    const bad: Array<[unknown, string]> = [
      [[], 'customers'],
      [{ ...doc([entry(z)]), analyzer_version: undefined }, 'analyzer_version'],
      [doc([entry(z)], { analyzer_version: 'x'.repeat(41) }), 'analyzer_version'],
      [doc([entry(z)], { analyzer_version: 'visits rules' }), 'analyzer_version'],
      [doc([entry(z)], { generated_at: 'today' }), 'generated_at'],
      [doc([entry(z)], { dry_run: 'yes' }), 'dry_run'],
      [doc([]), 'customers'],
      [doc(Array.from({ length: 101 }, () => entry(nextZaloId()))), 'customers'],
      [doc([entry('p:abc')]), 'customers[0].zalo_user_id'],
      [doc([entry(`p:${'1'.repeat(33)}`)]), 'customers[0].zalo_user_id'],
      [doc([entry(z), entry(z)]), 'customers[1].zalo_user_id'],
      [e({ messages: -1 }), 'customers[0].messages'],
      [e({ first_at: 'x' }), 'customers[0].first_at'],
      [v({ date: '2026-02-30' }), 'customers[0].visits[0].date'],
      [v({ time: '25:00', time_known: true }), 'customers[0].visits[0].time'],
      [v({ time_known: false }), 'customers[0].visits[0].time_known'],
      [v({ visited_at_local: '2026-03-04 15:00' }), 'customers[0].visits[0].visited_at_local'],
      [v({ services: [1, 2, 3, 4] }), 'customers[0].visits[0].services'],
      [v({ services: [{ service_id: null, service_name: null, basis: 'booking' }] }), 'customers[0].visits[0].services[0].service_id'],
      [v({ services: [{ service_id: 'Goi Dau', service_name: null, basis: 'booking' }] }), 'customers[0].visits[0].services[0].service_id'],
      [v({ services: [{ service_id: GOI, service_name: null, basis: 'later' }] }), 'customers[0].visits[0].services[0].basis'],
      [v({ amount_vnd: 999 }), 'customers[0].visits[0].amount_vnd'],
      [v({ amount_vnd: 50_000_001 }), 'customers[0].visits[0].amount_vnd'],
      [v({ amount_vnd: 350000.5 }), 'customers[0].visits[0].amount_vnd'],
      [v({ amount_source: 'guess' }), 'customers[0].visits[0].amount_source'],
      [v({ technician: 'x'.repeat(61) }), 'customers[0].visits[0].technician'],
      [v({ technician: 'Lan\nMai' }), 'customers[0].visits[0].technician'],
      [v({ confidence: undefined }), 'customers[0].visits[0].confidence'],
      [v({ confidence: 'certain' }), 'customers[0].visits[0].confidence'],
      [v({ signals: Array.from({ length: 21 }, () => 'arrival') }), 'customers[0].visits[0].signals'],
      [v({ signals: ['Arrival'] }), 'customers[0].visits[0].signals'],
      [v({ evidence_at: [1, 2, 3, 4, 5, 6] }), 'customers[0].visits[0].evidence_at'],
      [v({ source: 'chat' }), 'customers[0].visits[0].source'],
      [e({ visits: Array.from({ length: 401 }, (_, i) => cand(`2025-${String((i % 12) + 1).padStart(2, '0')}-01`)) }), 'customers[0].visits'],
      [e({ upcoming: Array.from({ length: 51 }, () => upcoming('2026-12-01')) }), 'customers[0].upcoming'],
      [e({ visits: [cand('2026-03-03'), cand('2026-03-03')] }), 'customers[0].visits[1].date'],
      [e({ upcoming: [{ ...upcoming('2026-12-01'), date: '2026-13-01' }] }), 'customers[0].upcoming[0].date'],
      [e({ benefits: Array.from({ length: 6 }, (_, i) => benefit(`Gói ${i + 1} buổi`)) }), 'customers[0].benefits'],
      [e({ benefits: [benefit('Gói 5 buổi', { total_count: 5, remaining: 8 })] }), 'customers[0].benefits[0].remaining'],
      [e({ benefits: [benefit('Gói 5 buổi', { total_count: 201 })] }), 'customers[0].benefits[0].total_count'],
      [e({ benefits: [benefit('')] }), 'customers[0].benefits[0].title'],
      [e({ benefits: [benefit('x'.repeat(121))] }), 'customers[0].benefits[0].title'],
      [e({ benefits: [benefit('Gói 5 buổi', { kind: 'gift' })] }), 'customers[0].benefits[0].kind'],
      [e({ benefits: [benefit('Gói 5 buổi', { stated_by: 'bot' })] }), 'customers[0].benefits[0].stated_by'],
      [e({ benefits: [benefit('Gói 5 buổi', { confidence: 'low' })] }), 'customers[0].benefits[0].confidence'],
      [e({ benefits: [benefit('Gói 5 buổi', { at: null })] }), 'customers[0].benefits[0].at'],
      [e({ phone: phone('12345') }), 'customers[0].phone.value'],
      [e({ phone: phone('091234566') }), 'customers[0].phone.value'],
      [e({ phone: { ...phone('0912345661'), confidence: 'low' } }), 'customers[0].phone.confidence'],
      [e({ model_pass: undefined }), 'customers[0].model_pass'],
      [e({ model_pass: { ran: 'no', reason: 'disabled' } }), 'customers[0].model_pass.ran'],
      [e({ model_pass: { ran: false, reason: 'tired' } }), 'customers[0].model_pass.reason'],
    ];
    const snap = await chatSnapshot();
    const audits = await auditCount();
    for (const [body, field] of bad) {
      const r = await push(body);
      expect(r.status, field).toBe(422);
      expect(r.body.error.code, field).toBe('validation_failed');
      expect(r.body.error.details.field, JSON.stringify(body).slice(0, 200)).toBe(field);
      expect(JSON.stringify(r.body)).not.toMatch(/091234566|12345/);
    }
    expect(await chatSnapshot()).toEqual(snap);
    expect(await auditCount()).toBe(audits);
    expect((await call('POST', '/staff/chat-facts/import', undefined, 'not json')).status).toBe(400);
  });

  it('accepts a batch of 100 entries', async () => {
    const ids = Array.from({ length: 100 }, () => nextZaloId());
    for (const z of ids.slice(0, 50)) await newCustomer({ zalo_user_id: z });
    const body = doc(ids.map((z, i) => entry(z, { visits: [cand('2026-10-01'), cand(`2026-10-${String((i % 20) + 2).padStart(2, '0')}`)], upcoming: [upcoming('2026-12-05')], benefits: [benefit('Gói 10 buổi')] })));
    const r = await push(body);
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ ...ZERO, customers: 100, unmatched: 50, visits_imported: 300, benefits_upserted: 100 });
    expect(await count(`SELECT COUNT(*) AS n FROM chat_visits WHERE zalo_user_id IN (${ids.map(() => '?').join(',')})`, ...ids)).toBe(300);
    expect(await count(`SELECT COUNT(*) AS n FROM chat_contact_facts WHERE zalo_user_id IN (${ids.map(() => '?').join(',')})`, ...ids)).toBe(100);
    expect((await push(body)).body).toEqual({ ...ZERO, customers: 100, unmatched: 50 });
  }, 60_000);
});

describe('GET /staff/chat-facts/eligible', () => {
  it('lists consented contacts that are not deleted, not minors and not internal, sorted; the last consent row wins', async () => {
    const T = Date.UTC(2026, 9, 1);
    const mk = async (over: Parameters<typeof newCustomer>[0] = {}) => newCustomer(over);
    const granted = await mk();
    await addConsent(granted.id, 'granted', T);
    const withdrawnLater = await mk();
    await addConsent(withdrawnLater.id, 'granted', T);
    await addConsent(withdrawnLater.id, 'withdrawn', T + 1000);
    const grantedAgain = await mk();
    await addConsent(grantedAgain.id, 'withdrawn', T);
    await addConsent(grantedAgain.id, 'granted', T + 1000);
    const sameTimeWithdrawn = await mk(); // same recorded_at: the row written last wins
    await addConsent(sameTimeWithdrawn.id, 'granted', T);
    await addConsent(sameTimeWithdrawn.id, 'withdrawn', T);
    const minor = await mk();
    await addConsent(minor.id, 'granted', T);
    await env.DB.prepare('UPDATE customers SET minor_flag = 1 WHERE id = ?').bind(minor.id).run();
    const notMinor = await mk();
    await addConsent(notMinor.id, 'granted', T);
    await env.DB.prepare('UPDATE customers SET minor_flag = 0 WHERE id = ?').bind(notMinor.id).run();
    const deleted = await mk({ deleted_at: T });
    await addConsent(deleted.id, 'granted', T);
    const staffRole = await mk();
    await addConsent(staffRole.id, 'granted', T);
    await addRole(staffRole.zalo, 'staff');
    const managerRole = await mk();
    await addConsent(managerRole.id, 'granted', T);
    await addRole(managerRole.zalo, 'manager', 'staff');
    const customerRole = await mk();
    await addConsent(customerRole.id, 'granted', T);
    await addRole(customerRole.zalo, 'customer');
    const noConsent = await mk();
    const otherPurpose = await mk();
    await addConsent(otherPurpose.id, 'granted', T, 'followup_care');
    const oa = await mk({ zalo_user_id: '5550001119999', oa_id: 'test-oa-id', channel: 'oa' });
    await addConsent(oa.id, 'granted', T);

    const r = await call('GET', '/staff/chat-facts/eligible');
    expect(r.status).toBe(200);
    expect(Object.keys(r.body)).toEqual(['zalo_user_ids']);
    const list: string[] = r.body.zalo_user_ids;
    expect(list).toEqual([...list].sort());
    const mine = [granted, withdrawnLater, grantedAgain, sameTimeWithdrawn, minor, notMinor, deleted, staffRole, managerRole, customerRole, noConsent, otherPurpose, oa].map((c) => c.zalo);
    expect(list.filter((id) => mine.includes(id))).toEqual([granted.zalo, grantedAgain.zalo, notMinor.zalo, customerRole.zalo].sort());
    expect(list.every((id) => /^p:\d{1,32}$/.test(id))).toBe(true);
  });
});
