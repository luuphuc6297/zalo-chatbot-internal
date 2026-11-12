// The documents scripts/analyze_visits.py really writes, posted to POST /staff/chat-facts/import the way its --push does
// (docs/contracts.md sections 15.7 and 15.11). Both fixtures are the analyzer's output for the synthetic cache of
// test/fixtures/analyzer-cache.py with --now '2026-11-12 10:00' (how to regenerate them is in that file). Every name,
// phone number and id is synthetic.
//
// test/fixtures/analyzer-visits-document.json, rules pass only. Its four contacts: A has two paid high visits, an
// upcoming booking, a package and a high phone number from the chat; B has one high visit and a phone from the cache's
// contacts table; C has one low booking request with a quoted price; D looks like a customer to the analyzer, and
// these tests give it the role staff.
//
// test/fixtures/analyzer-model-document.json, the model pass on (scope customers) with the fake claude of
// scripts/tests/fake_bin_visits: the same four contacts plus E. The model confirms visits of A, B and D (source
// chat_rules+model, no rules value changed), adds E's walk-in the rules missed (chat_model, medium, paid amount, basis
// visit_day), fills the empty service of E's rules visit (basis window) and adds E's package stated by the contact.
//
// The contact ids are renamed per test (nothing else in the document changes), so the tests do not share rows.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { buildCustomerSummary, customerFactsForModel } from '../src/lib/customer-summary';
import { parseLocalDateTime } from '../src/staff-api/customers';
import type { CustomerFacts } from '../src/types';
import { seed } from './core-helpers';
import { BODY, GOI, NOW, addRole, addVisit, catalog, count, jobCount, newCustomer } from './customers-helpers';
import { call, chatBenefitsOf, chatSnapshot, chatVisitsOf, enc, factsOf, push, type ChatVisitDb } from './chat-facts-helpers';
import modelFixture from './fixtures/analyzer-model-document.json';
import fixture from './fixtures/analyzer-visits-document.json';

interface Candidate {
  date: string;
  time: string | null;
  time_known: boolean;
  visited_at_local: string;
  services: Array<{ service_id: string | null; service_name: string | null; basis: string }>;
  amount_vnd: number | null;
  amount_source: string | null;
  technician: string | null;
  confidence?: string;
  signals: string[];
  evidence_at: number[];
  source: string;
}
interface Entry {
  zalo_user_id: string;
  messages: number;
  first_at: number | null;
  last_at: number | null;
  visits: Candidate[];
  upcoming: Candidate[];
  phone: { value: string; confidence: string; source: string; at: number | null } | null;
  benefits: Array<{ kind: string; title: string; service_id: string | null; total_count: number | null; remaining: number | null; stated_by: string; confidence: string; at: number; source?: string }>;
  model_pass: { ran: boolean; reason: string };
}
interface Doc {
  analyzer_version: string;
  generated_at: number;
  contacts: number;
  skipped: Record<string, number>;
  model: { enabled: boolean; scope: string | null; customers_sent: number; calls: number };
  customers: Entry[];
}
const DOC = fixture as unknown as Doc;
const [A, B, C, D] = DOC.customers as [Entry, Entry, Entry, Entry];
const MDOC = modelFixture as unknown as Doc;
const [MA, MB, MC, MD, ME] = MDOC.customers as [Entry, Entry, Entry, Entry, Entry];
const VAI = 'massage-co-vai-gay';

let NAMES: Record<string, string> = {};
let CV = '';

beforeAll(async () => {
  CV = (await seed()).catalog_version;
  NAMES = (await catalog()).names;
});

/** A document with its contact ids renamed, and the body analyze_visits.push sends for it. */
let worlds = 0;
function world(doc: Doc = DOC) {
  worlds += 1;
  const rename = new Map(doc.customers.map((c, i) => [c.zalo_user_id, `p:94${String(worlds).padStart(3, '0')}${String(i + 1).padStart(5, '0')}`]));
  const customers = doc.customers.map((c) => ({ ...structuredClone(c), zalo_user_id: rename.get(c.zalo_user_id)! }));
  const id = (c: Entry) => rename.get(c.zalo_user_id)!;
  return {
    a: id(A),
    b: id(B),
    c: id(C),
    d: id(D),
    id,
    customers,
    // scripts/analyze_visits.py push(): {analyzer_version, generated_at, dry_run: false, customers} in parts of 100
    body: (dryRun = false) => ({ analyzer_version: doc.analyzer_version, generated_at: doc.generated_at, dry_run: dryRun, customers }),
  };
}

/**
 * The server side of the fixture: A, C and D have customers rows (A without a phone, with a recorded visit on the day
 * of its first guess), B has none, D has the role staff.
 */
async function setUp(w: ReturnType<typeof world>) {
  // The tests share one D1 and the fixture's phone numbers: a number the customer of an earlier world holds would count
  // as another customer's number (phones_taken) in this world, so the earlier worlds give their numbers back.
  await env.DB.prepare("UPDATE customers SET phone = NULL WHERE zalo_user_id LIKE 'p:94%'").run();
  const a = await newCustomer({ zalo_user_id: w.a });
  const c = await newCustomer({ zalo_user_id: w.c });
  const d = await newCustomer({ zalo_user_id: w.d });
  await addRole(w.d, 'staff');
  const recorded = await addVisit(a.id, parseLocalDateTime('2026-10-31 15:00')!, GOI, { amount: 199000, technician: 'Lan' });
  return { a: a.id, c: c.id, d: d.id, recorded };
}

/** A stored chat_visits row is the candidate as the analyzer wrote it. */
function expectStored(row: ChatVisitDb | undefined, cand: Candidate, kind: 'visit' | 'upcoming') {
  expect(row, `${kind} ${cand.date}`).toMatchObject({
    kind,
    local_date: cand.date,
    visited_at: parseLocalDateTime(cand.visited_at_local),
    time_known: cand.time_known ? 1 : 0,
    amount_vnd: cand.amount_vnd,
    amount_source: cand.amount_source,
    technician: cand.technician,
    confidence: kind === 'visit' ? cand.confidence : null,
    fact_source: cand.source,
    state: 'active',
    confirmed_visit_id: null,
    analyzer_version: DOC.analyzer_version,
    decided_by: null,
    decided_at: null,
  });
  expect(JSON.parse(row!.services_json)).toEqual(cand.services);
  expect(JSON.parse(row!.signals_json)).toEqual(cand.signals);
  expect(JSON.parse(row!.evidence_json)).toEqual(cand.evidence_at);
}

type Found = Extract<CustomerFacts, { found: true }>;

describe('the document scripts/analyze_visits.py writes', () => {
  it('is the analyzer output this test expects (premises of the checks below)', () => {
    expect(DOC).toMatchObject({ analyzer_version: 'visits-rules-v1', contacts: 4, skipped: { family: 1 } });
    expect(DOC.model).toEqual({ enabled: false, scope: null, customers_sent: 0, calls: 0 });
    expect(DOC.customers.map((c) => c.zalo_user_id)).toEqual(['p:5550002001', 'p:5550002002', 'p:5550002003', 'p:5550002004']);
    for (const c of DOC.customers) {
      expect(c.model_pass, c.zalo_user_id).toEqual({ ran: false, reason: 'disabled' });
      for (const v of [...c.visits, ...c.upcoming]) expect(v.source, `${c.zalo_user_id} ${v.date}`).toBe('chat_rules');
    }
    // B's arrival message without diacritics ("chi toi roi em" at 15:58) is one of the visit's signals
    expect(B.visits[0]!.signals).toEqual(['booking_request', 'booking_confirmed', 'arrival', 'after_visit']);
    const brief = (c: Entry) => ({
      visits: c.visits.map((v) => [v.date, v.time, v.confidence, v.amount_vnd, v.amount_source]),
      upcoming: c.upcoming.map((v) => [v.date, v.time, 'confidence' in v]),
      phone: c.phone && [c.phone.value, c.phone.confidence, c.phone.source],
      benefits: c.benefits.map((b) => [b.kind, b.title, b.total_count, b.remaining]),
    });
    expect(brief(A)).toEqual({
      visits: [
        ['2026-10-31', '15:00', 'high', 199000, 'paid'],
        ['2026-11-05', '10:00', 'high', 350000, 'paid'],
      ],
      upcoming: [['2026-11-17', '09:00', false]],
      phone: ['0912345678', 'high', 'chat'],
      benefits: [['package', 'Gói 10 buổi – Gội đầu', 10, 7]],
    });
    expect(brief(B)).toEqual({ visits: [['2026-11-08', '16:00', 'high', null, null]], upcoming: [], phone: ['0987654321', 'high', 'zalo_contact'], benefits: [] });
    expect(brief(C)).toEqual({ visits: [['2026-11-08', '14:00', 'low', 350000, 'quoted']], upcoming: [], phone: null, benefits: [] });
    expect(brief(D)).toEqual({ visits: [['2026-11-04', '11:00', 'high', 199000, 'paid']], upcoming: [], phone: null, benefits: [] });
    expect(A.visits[1]!.services).toEqual([
      { service_id: BODY, service_name: 'Massage body thư giãn', basis: 'booking' },
      { service_id: null, service_name: 'gội đầu', basis: 'visit_day' },
    ]);
  });

  it('is imported as sent: counters, stored rows, an idempotent re-run, the summary and the model facts', async () => {
    const w = world();
    const ids = await setUp(w);
    const auditsBefore = await count("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'chat_facts.import'");

    // a dry run counts everything and writes nothing
    const expected = {
      customers: 3, // A, B, C; D is staff
      unmatched: 1, // B has no customers row; its facts are stored all the same
      skipped_internal: 1,
      skipped_deleted: 0,
      visits_imported: 4, // A 05/11 and the 17/11 booking, B 08/11, C 08/11
      visits_updated: 0,
      visits_removed: 0,
      visits_kept_staff: 1, // A 31/10 has a recorded visit
      visits_tombstoned: 0,
      phones_set: 1, // A: high, from the chat, the customers row has no phone
      phones_taken: 0,
      phone_suggestions: 1, // B: high, but no customers row
      benefits_upserted: 1,
      benefits_kept_staff: 0,
    };
    const before = await chatSnapshot();
    const dry = await push(w.body(true));
    expect(dry).toEqual({ status: 200, body: { ...expected, dry_run: true } });
    expect(await chatSnapshot()).toEqual(before);
    expect(await count("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'chat_facts.import'")).toBe(auditsBefore);

    const r = await push(w.body());
    expect(r).toEqual({ status: 200, body: { ...expected, dry_run: false } });

    // A: the guess on the recorded day is not stored; the other guess and the booking are, field by field
    const aRows = await chatVisitsOf(w.a);
    expect(aRows.map((x) => [x.kind, x.local_date])).toEqual([
      ['upcoming', '2026-11-17'],
      ['visit', '2026-11-05'],
    ]);
    expectStored(aRows[1], A.visits[1]!, 'visit');
    expectStored(aRows[0], A.upcoming[0]!, 'upcoming');
    expect(await chatBenefitsOf(w.a)).toEqual([
      expect.objectContaining({
        kind: 'package',
        title: 'Gói 10 buổi – Gội đầu',
        title_key: 'goi 10 buoi – goi dau',
        service_id: null,
        total_count: 10,
        remaining: 7,
        stated_by: 'owner',
        confidence: 'high',
        stated_at: A.benefits[0]!.at,
        state: 'active',
        confirmed_benefit_id: null,
      }),
    ]);
    expect(await factsOf(w.a)).toMatchObject({
      analyzer_version: DOC.analyzer_version,
      generated_at: DOC.generated_at,
      messages: A.messages,
      first_at: A.first_at,
      last_at: A.last_at,
      phone_suggestion: null, // the number went into customers.phone
      phone_state: null,
      phone_dismissed: null,
      model_pass_json: JSON.stringify(A.model_pass),
    });
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(ids.a).first<{ phone: string }>())!.phone).toBe('0912345678');

    // B: stored under its zalo_user_id until the contact writes; the number waits for staff
    const bRows = await chatVisitsOf(w.b);
    expect(bRows).toHaveLength(1);
    expectStored(bRows[0], B.visits[0]!, 'visit');
    expect(await factsOf(w.b)).toMatchObject({ messages: B.messages, phone_suggestion: '0987654321', phone_state: null });
    // C: the low guess is stored (staff may confirm it) with its quoted price
    const cRows = await chatVisitsOf(w.c);
    expect(cRows).toHaveLength(1);
    expectStored(cRows[0], C.visits[0]!, 'visit');
    expect(await factsOf(w.c)).toMatchObject({ messages: C.messages, phone_suggestion: null });
    // D: a staff contact gets nothing at all
    expect(await chatVisitsOf(w.d)).toEqual([]);
    expect(await chatBenefitsOf(w.d)).toEqual([]);
    expect(await factsOf(w.d)).toBeNull();

    // one audit row with the counters and the version; no audit row holds a number, a title or a contact id
    const audit = await env.DB.prepare("SELECT * FROM audit_log WHERE action = 'chat_facts.import' ORDER BY id DESC LIMIT 1").first<Record<string, any>>();
    expect(JSON.parse(audit!.after_json)).toEqual({ ...expected, analyzer_version: DOC.analyzer_version });
    const allAudit = JSON.stringify((await env.DB.prepare('SELECT * FROM audit_log').all()).results);
    for (const hidden of ['0912345678', '0987654321', 'Gói 10', 'gội đầu', w.a, w.b, w.c]) expect(allAudit, hidden).not.toContain(hidden);

    // the same document again (the analyzer run twice): nothing written, nothing counted but the entries
    const snap = await chatSnapshot();
    const again = await push(w.body());
    expect(again.body).toEqual({ ...expected, visits_imported: 0, phones_set: 0, phone_suggestions: 0, benefits_upserted: 0, dry_run: false });
    expect(await chatSnapshot()).toEqual(snap);

    // the summary of A merges the counted guess with the recorded visit (fixed clock: 15:00 on 12/11/2026)
    expect(await buildCustomerSummary(env, ids.a, NOW)).toMatchObject({
      phone: '0912345678',
      status: 'returning',
      visits_total: 2,
      last_visit: {
        visited_at: parseLocalDateTime('2026-11-05 10:00'),
        date: '2026-11-05',
        time: '10:00',
        services: [
          { service_id: BODY, name: NAMES[BODY] },
          { service_id: 'ext:goi-dau', name: 'gội đầu' },
        ],
        technician: null,
        amount_vnd: 350000,
        from_chat: true,
      },
      days_since_last_visit: 7,
      usual_gap_days: 5,
      gap_basis: 'own',
      lifetime_spend_vnd: 549000,
      lifetime_spend_visits: 2,
      window: { visits: 2, spend_vnd: 549000, avg_spend_vnd: 274500 },
      benefits: [],
      chat: {
        visits_counted: 1,
        visits_low: 0,
        upcoming_next: { date: '2026-11-17', time: '09:00' },
        benefits_active: 1,
        phone_suggestion: false,
        analyzer_version: DOC.analyzer_version,
        generated_at: DOC.generated_at,
      },
    });
    const f = (await customerFactsForModel(env, ids.a, CV, NOW)) as Found;
    expect(f).toMatchObject({
      found: true,
      has_phone: true,
      visits_total: 2,
      visits_from_chat: 1,
      last_visit: { date: '2026-11-05', time: '10:00', services: [NAMES[BODY]], other_services: 1, technician: null, from_chat: true },
      next_booking_from_chat: { date: '2026-11-17', time: '09:00' },
      benefits_from_chat: [{ kind: 'package', remaining: 7 }],
    });
    for (const hidden of ['0912345678', 'Gói 10', 'ext:', w.a, 'chv_']) expect(JSON.stringify(f), hidden).not.toContain(hidden);

    // C: a low guess is never counted
    expect(await buildCustomerSummary(env, ids.c, NOW)).toMatchObject({
      status: 'first_inquiry',
      visits_total: 0,
      last_visit: null,
      chat: { visits_counted: 0, visits_low: 1, upcoming_next: null, benefits_active: 0, phone_suggestion: false },
    });
  }, 30_000);

  it('takes the decisions the console sends, and the next analyzer run leaves them alone', async () => {
    const w = world();
    const ids = await setUp(w);
    expect((await push(w.body())).status).toBe(200);

    // GET with the colon %3A-encoded, as the console sends it
    const g = await call('GET', `/staff/chat-facts/${enc(w.a)}`);
    expect(g.status).toBe(200);
    const facts = g.body.facts;
    expect(facts.visits).toHaveLength(1);
    expect(facts.visits[0]).toMatchObject({
      local_date: '2026-11-05',
      kind: 'visit',
      time_known: true,
      time: '10:00',
      services: [
        { service_id: BODY, service_name: 'Massage body thư giãn', basis: 'booking', name: NAMES[BODY] },
        { service_id: null, service_name: 'gội đầu', basis: 'visit_day', name: 'gội đầu' },
      ],
      amount_vnd: 350000,
      amount_source: 'paid',
      technician: null,
      confidence: 'high',
      signals: A.visits[1]!.signals,
      evidence: A.visits[1]!.evidence_at,
      state: 'active',
    });
    expect(facts.upcoming).toEqual([expect.objectContaining({ local_date: '2026-11-17', time: '09:00', confidence: null, state: 'active' })]);
    expect(facts.benefits).toEqual([expect.objectContaining({ title: 'Gói 10 buổi – Gội đầu', total_count: 10, remaining: 7, state: 'active' })]);
    expect(facts).toMatchObject({ phone_suggestion: null, analyzer_version: DOC.analyzer_version, generated_at: DOC.generated_at, model_pass: { ran: false, reason: 'disabled' } });

    // "Xác nhận" with nothing changed sends {}: the visit takes the guess's first catalog service, time and amount
    const aVisit = await call('POST', `/staff/chat-facts/visits/${facts.visits[0].id}/confirm`, {});
    expect(aVisit.status).toBe(200);
    expect(aVisit.body.visit).toMatchObject({
      customer_id: ids.a,
      service_id: BODY,
      service_name: null,
      visited_at: parseLocalDateTime('2026-11-05 10:00'),
      amount_vnd: 350000,
      technician: null,
      source: 'staff',
      recorded_by: 'tester',
    });
    expect(await jobCount(ids.a)).toBe(0); // no thank-you or check-in for an old visit
    // the low guess of C with its quoted price: an empty body records no amount (a quoted price is not spend); the
    // console sends amount_vnd only when staff type what the customer paid
    const cRow = (await chatVisitsOf(w.c))[0]!;
    const cVisit = await call('POST', `/staff/chat-facts/visits/${cRow.id}/confirm`, {});
    expect(cVisit.body.visit).toMatchObject({ customer_id: ids.c, service_id: BODY, amount_vnd: null, visited_at: parseLocalDateTime('2026-11-08 14:00') });
    // the console always sends total_count and used_count for a benefit
    const aBenefit = (await chatBenefitsOf(w.a))[0]!;
    const ben = await call('POST', `/staff/chat-facts/benefits/${aBenefit.id}/confirm`, { total_count: 10, used_count: 3 });
    expect(ben.status).toBe(200);
    expect(ben.body.benefit).toMatchObject({ customer_id: ids.a, kind: 'package', title: 'Gói 10 buổi – Gội đầu', total_count: 10, used_count: 3, remaining: 7, status: 'active' });
    // "Bỏ" on the booking, with an empty object as body
    expect((await call('POST', `/staff/chat-facts/visits/${facts.upcoming[0].id}/dismiss`, {})).status).toBe(200);

    // B has no customers row: a confirm and "Dùng số này" answer 409; "Bỏ" on the number works
    const bRow = (await chatVisitsOf(w.b))[0]!;
    const bConfirm = await call('POST', `/staff/chat-facts/visits/${bRow.id}/confirm`, {});
    expect(bConfirm.status).toBe(409);
    expect(bConfirm.body.error).toMatchObject({ code: 'invalid_state', message: 'khách chưa có hồ sơ' });
    expect((await call('POST', `/staff/chat-facts/${enc(w.b)}/phone/accept`, {})).status).toBe(409);
    expect((await call('POST', `/staff/chat-facts/${enc(w.b)}/phone/dismiss`, {})).status).toBe(200);
    expect(await factsOf(w.b)).toMatchObject({ phone_suggestion: null, phone_state: 'dismissed', phone_dismissed: '0987654321' });

    // the analyzer runs again on the same cache: every decision stays, nothing comes back
    const snap = await chatSnapshot();
    const again = await push(w.body());
    expect(again.body).toEqual({
      customers: 3,
      unmatched: 1,
      skipped_internal: 1,
      skipped_deleted: 0,
      visits_imported: 0,
      visits_updated: 0,
      visits_removed: 0,
      visits_kept_staff: 3, // A 31/10 recorded, A 05/11 and C 08/11 confirmed
      visits_tombstoned: 1, // A's booking on 17/11
      phones_set: 0,
      phones_taken: 0,
      phone_suggestions: 0, // B's dismissed number is not suggested again
      benefits_upserted: 0,
      benefits_kept_staff: 1,
      dry_run: false,
    });
    expect(await chatSnapshot()).toEqual(snap);

    // A's summary now reads the recorded visits only
    expect(await buildCustomerSummary(env, ids.a, NOW)).toMatchObject({
      visits_total: 2,
      last_visit: { date: '2026-11-05', time: '10:00', from_chat: false, amount_vnd: 350000 },
      lifetime_spend_vnd: 549000,
      benefits: [{ kind: 'package', title: 'Gói 10 buổi – Gội đầu', remaining: 7 }],
      chat: { visits_counted: 0, visits_low: 0, upcoming_next: null, benefits_active: 0, phone_suggestion: false },
    });
  }, 30_000);
});

/** An entry without what the model pass may change on it: its model_pass and the source of its candidates. */
const withoutModel = (e: Entry) => ({
  ...e,
  model_pass: undefined,
  visits: e.visits.map((v) => ({ ...v, source: undefined })),
  upcoming: e.upcoming.map((v) => ({ ...v, source: undefined })),
});

describe('the document scripts/analyze_visits.py writes with the model pass on (fake claude)', () => {
  it('is the analyzer output this test expects (premises of the checks below)', () => {
    expect(MDOC).toMatchObject({ analyzer_version: 'visits-rules-v1', contacts: 5, skipped: { family: 1 } });
    expect(MDOC.model).toEqual({ enabled: true, scope: 'customers', customers_sent: 5, calls: 5 });
    expect(MDOC.customers.map((c) => c.zalo_user_id)).toEqual(['p:5550002001', 'p:5550002002', 'p:5550002003', 'p:5550002004', 'p:5550002006']);
    for (const c of MDOC.customers) expect(c.model_pass, c.zalo_user_id).toEqual({ ran: true, reason: 'ok' });

    // A, B, C and D: the rules result with only the source raised where the model confirmed a visit
    [MA, MB, MC, MD].forEach((m, i) => expect(withoutModel(m), m.zalo_user_id).toEqual(withoutModel(DOC.customers[i]!)));
    const sources = (c: Entry) => [...c.visits, ...c.upcoming].map((v) => [v.date, v.source]);
    expect(sources(MA)).toEqual([
      ['2026-10-31', 'chat_rules+model'],
      ['2026-11-05', 'chat_rules+model'],
      ['2026-11-17', 'chat_rules'], // the model's "booked" is after --now: dropped
    ]);
    expect(sources(MB)).toEqual([['2026-11-08', 'chat_rules+model']]);
    expect(sources(MC)).toEqual([['2026-11-08', 'chat_rules']]); // "booked" changes nothing
    expect(sources(MD)).toEqual([['2026-11-04', 'chat_rules+model']]);

    // E: every value below comes from scripts/visit_model_pass.py (contract 15.4 values, item S1 of the review)
    expect(ME.visits).toEqual([
      {
        date: '2026-11-07',
        time: null,
        time_known: false,
        visited_at_local: '2026-11-07 12:00',
        services: [{ service_id: VAI, service_name: 'Massage cổ, vai, gáy', basis: 'visit_day' }], // the cited line is on 07/11
        amount_vnd: 300000,
        amount_source: 'paid', // the cited line says "ck 300k"
        technician: 'Mai',
        confidence: 'medium',
        signals: ['model_completed'],
        evidence_at: [Date.UTC(2026, 10, 7, 9, 40)], // 16:40 local
        source: 'chat_model',
      },
      {
        date: '2026-11-10',
        time: '17:00',
        time_known: true,
        visited_at_local: '2026-11-10 17:00',
        services: [{ service_id: VAI, service_name: 'Massage cổ, vai, gáy', basis: 'window' }], // no cited line on 10/11
        amount_vnd: null,
        amount_source: null,
        technician: null,
        confidence: 'high',
        signals: ['booking_request', 'booking_confirmed', 'arrival', 'after_visit'],
        evidence_at: ME.visits[1]!.evidence_at, // the rules evidence, kept
        source: 'chat_rules+model',
      },
    ]);
    expect(ME.visits[1]!.evidence_at).toHaveLength(4);
    expect(ME.upcoming).toEqual([]);
    expect(ME.phone).toBeNull();
    expect(ME.benefits).toEqual([
      {
        kind: 'package',
        title: 'Gói 5 buổi',
        service_id: null,
        total_count: 5,
        remaining: null,
        stated_by: 'contact', // the newest cited line is the contact's
        confidence: 'medium',
        at: Date.UTC(2026, 10, 8, 3, 0), // that line: 10:00 local on 08/11
        source: 'chat_model',
      },
    ]);
  });

  it('is imported with 200 and the model fields stored as sent; staff can confirm the model visit', async () => {
    const w = world(MDOC);
    await setUp(w); // A, C and D have customers rows (A with a recorded visit on 31/10), D is staff, B has none
    const e = await newCustomer({ zalo_user_id: w.id(ME) });
    const expected = {
      customers: 4, // A, B, C, E; D is staff
      unmatched: 1, // B
      skipped_internal: 1,
      skipped_deleted: 0,
      visits_imported: 6, // A 05/11 and the 17/11 booking, B 08/11, C 08/11, E 07/11 and 10/11
      visits_updated: 0,
      visits_removed: 0,
      visits_kept_staff: 1, // A 31/10 has a recorded visit
      visits_tombstoned: 0,
      phones_set: 1,
      phones_taken: 0,
      phone_suggestions: 1,
      benefits_upserted: 2, // A's package (rules), E's package (model)
      benefits_kept_staff: 0,
    };
    const before = await chatSnapshot();
    expect(await push(w.body(true))).toEqual({ status: 200, body: { ...expected, dry_run: true } });
    expect(await chatSnapshot()).toEqual(before);
    expect(await push(w.body())).toEqual({ status: 200, body: { ...expected, dry_run: false } });

    // every stored candidate is the analyzer's, whichever pass wrote it
    const aRows = await chatVisitsOf(w.a);
    expect(aRows.map((x) => [x.kind, x.local_date, x.fact_source])).toEqual([
      ['upcoming', '2026-11-17', 'chat_rules'],
      ['visit', '2026-11-05', 'chat_rules+model'],
    ]);
    expectStored(aRows[1], MA.visits[1]!, 'visit');
    expectStored(aRows[0], MA.upcoming[0]!, 'upcoming');
    const bRows = await chatVisitsOf(w.b);
    expect(bRows).toHaveLength(1);
    expectStored(bRows[0], MB.visits[0]!, 'visit');
    const cRows = await chatVisitsOf(w.c);
    expect(cRows).toHaveLength(1);
    expectStored(cRows[0], MC.visits[0]!, 'visit');
    expect(await chatVisitsOf(w.d)).toEqual([]);
    expect(await factsOf(w.d)).toBeNull();

    // E: the model's values reach the rows unchanged
    const eRows = await chatVisitsOf(w.id(ME));
    expect(eRows).toHaveLength(2);
    expectStored(eRows[0], ME.visits[0]!, 'visit');
    expectStored(eRows[1], ME.visits[1]!, 'visit');
    expect(eRows.map((r) => [r.local_date, r.fact_source, r.confidence, r.amount_source, r.technician, JSON.parse(r.services_json).map((s: { basis: string }) => s.basis)])).toEqual([
      ['2026-11-07', 'chat_model', 'medium', 'paid', 'Mai', ['visit_day']],
      ['2026-11-10', 'chat_rules+model', 'high', null, null, ['window']],
    ]);
    expect(eRows[0]!.time_known).toBe(0);
    expect(await chatBenefitsOf(w.id(ME))).toEqual([
      expect.objectContaining({
        kind: 'package',
        title: 'Gói 5 buổi',
        title_key: 'goi 5 buoi',
        service_id: null,
        total_count: 5,
        remaining: null,
        stated_by: 'contact',
        confidence: 'medium',
        stated_at: ME.benefits[0]!.at,
        state: 'active',
        confirmed_benefit_id: null,
        analyzer_version: MDOC.analyzer_version,
      }),
    ]);
    for (const z of [w.a, w.b, w.c, w.id(ME)]) expect(await factsOf(z), z).toMatchObject({ model_pass_json: JSON.stringify({ ran: true, reason: 'ok' }) });

    // the same document again: nothing written, so every model field was stored exactly as sent
    const snap = await chatSnapshot();
    const again = await push(w.body());
    expect(again.body).toEqual({ ...expected, visits_imported: 0, phones_set: 0, phone_suggestions: 0, benefits_upserted: 0, dry_run: false });
    expect(await chatSnapshot()).toEqual(snap);

    // what the console reads
    const g = await call('GET', `/staff/chat-facts/${enc(w.id(ME))}`);
    expect(g.status).toBe(200);
    expect(g.body.facts.model_pass).toEqual({ ran: true, reason: 'ok' });
    expect(g.body.facts.visits.map((v: any) => [v.local_date, v.fact_source, v.confidence, v.time, v.amount_vnd, v.amount_source, v.technician, v.services])).toEqual([
      ['2026-11-10', 'chat_rules+model', 'high', '17:00', null, null, null, [{ service_id: VAI, service_name: 'Massage cổ, vai, gáy', basis: 'window', name: NAMES[VAI] }]],
      ['2026-11-07', 'chat_model', 'medium', null, 300000, 'paid', 'Mai', [{ service_id: VAI, service_name: 'Massage cổ, vai, gáy', basis: 'visit_day', name: NAMES[VAI] }]],
    ]);
    expect(g.body.facts.benefits).toEqual([expect.objectContaining({ title: 'Gói 5 buổi', total_count: 5, remaining: null, stated_by: 'contact', confidence: 'medium', stated_at: ME.benefits[0]!.at })]);

    // the summary counts the medium model visit with its paid amount, and the high one the model completed
    expect(await buildCustomerSummary(env, e.id, NOW)).toMatchObject({
      visits_total: 2,
      last_visit: { date: '2026-11-10', time: '17:00', services: [{ service_id: VAI, name: NAMES[VAI] }], amount_vnd: null, from_chat: true },
      lifetime_spend_vnd: 300000,
      chat: { visits_counted: 2, visits_low: 0, upcoming_next: null, benefits_active: 1, phone_suggestion: false },
    });

    // "Xác nhận" on the model's walk-in with nothing changed: its service, technician and paid amount become the visit
    const modelVisit = g.body.facts.visits[1];
    const confirmed = await call('POST', `/staff/chat-facts/visits/${modelVisit.id}/confirm`, {});
    expect(confirmed.status).toBe(200);
    expect(confirmed.body.visit).toMatchObject({
      customer_id: e.id,
      service_id: VAI,
      service_name: null,
      visited_at: parseLocalDateTime('2026-11-07 12:00'),
      amount_vnd: 300000,
      technician: 'Mai',
      source: 'staff',
      recorded_by: 'tester',
    });
    expect((await chatVisitsOf(w.id(ME)))[0]).toMatchObject({ local_date: '2026-11-07', state: 'confirmed', confirmed_visit_id: confirmed.body.visit.id });
  }, 30_000);

  it("refuses the values the model pass wrote before the fix ('model' basis and amount source, no stated_by or at)", async () => {
    const w = world(MDOC);
    const k = MDOC.customers.indexOf(ME);
    const old: Array<[(e: any) => void, string]> = [
      [(e) => (e.visits[0].services[0].basis = 'model'), `customers[${k}].visits[0].services[0].basis`],
      [(e) => (e.visits[0].amount_source = 'model'), `customers[${k}].visits[0].amount_source`],
      [(e) => (e.benefits[0].stated_by = null), `customers[${k}].benefits[0].stated_by`],
      [(e) => (e.benefits[0].at = null), `customers[${k}].benefits[0].at`],
    ];
    const snap = await chatSnapshot();
    for (const [change, field] of old) {
      const body = structuredClone(w.body());
      change(body.customers[k]);
      const r = await push(body);
      expect(r.status, field).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field } });
    }
    expect(await chatSnapshot()).toEqual(snap);
    expect((await push(w.body(true))).status).toBe(200); // the document as written is accepted
  });
});
