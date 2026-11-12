// Migration 0011_chat_facts.sql on a D1 that has 0001-0010 only (`wrangler dev` reloads the new code before the owner
// applies the migration). Before 0011: every endpoint of section 15.11 answers 409 invalid_state naming the migration,
// and the customer summary and the model facts are exactly what section 14 gives; the role writes and the phone edit,
// which also touch the chat tables once 0011 is there, work as in section 14. Applying 0011 keeps every row of the
// existing tables. This file removes the four tables of 0011 in its own D1. Every name, phone number and id is
// synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { isMissingMigration0011, loadChatSummaryInput } from '../src/lib/chat-facts';
import { buildCustomerSummary, customerFactsForModel } from '../src/lib/customer-summary';
import { isMissingMigration0010 } from '../src/lib/roles';
import { seed } from './core-helpers';
import { GOI, NOW, addBenefit, addProfile, addRole, addVisit, at } from './customers-helpers';
import { addConsent, benefit, call, cand, doc, enc, entry, phone, upcoming } from './chat-facts-helpers';
import { chatTablesPresent } from '../src/lib/chat-facts-tables';

function queriesOf(prefix: string): string[] {
  const m = env.TEST_MIGRATIONS.find((x) => x.name.startsWith(prefix));
  expect(m, prefix).toBeDefined();
  return m!.queries;
}

async function run(queries: string[]) {
  await env.DB.batch(queries.map((q) => env.DB.prepare(q)));
}

const CUS = 'cus_m11a';
const ZALO = 'p:930000000088001';
const CNV = 'cnv_m11a';
const T = at(40);
const CHAT_TABLES = ['chat_visits', 'chat_benefits', 'chat_contact_facts', 'chat_phone_dismissed'];
const TABLES = ['customers', 'conversations', 'messages', 'visits', 'customer_benefits', 'contact_roles', 'customer_profiles', 'consents', 'jobs', 'audit_log'];
let CV = '';
let summaryBefore: unknown;
let factsBefore: unknown;

async function snapshot(): Promise<Record<string, unknown[]>> {
  const out: Record<string, unknown[]> = {};
  for (const t of TABLES) out[t] = (await env.DB.prepare(`SELECT * FROM ${t} ORDER BY rowid`).all()).results;
  return out;
}

const count = async (sql: string) => (await env.DB.prepare(sql).first<{ n: number }>())!.n;

beforeAll(async () => {
  CV = (await seed()).catalog_version;
  await env.DB.prepare("INSERT INTO customers (id, oa_id, zalo_user_id, display_name, phone, channel, created_at) VALUES (?, 'personal', ?, 'Lan Thử', '0907880001', 'personal', ?)")
    .bind(CUS, ZALO, T)
    .run();
  await env.DB.prepare("INSERT INTO conversations (id, customer_id, oa_id, bot_state, created_at, updated_at) VALUES (?, ?, 'personal', 'bot_active', ?, ?)").bind(CNV, CUS, T, T).run();
  await env.DB.prepare("INSERT INTO messages (id, conversation_id, direction, source, text, seq, created_at) VALUES ('msg_m11a', ?, 'inbound', 'customer', 'tin nhắn thử', 1, ?)").bind(CNV, T).run();
  await addVisit(CUS, at(40), GOI, { amount: 300000, technician: 'Hoa' });
  await addVisit(CUS, at(10), GOI, { amount: 250000, source: 'import' });
  await addBenefit(CUS, { title: 'Gói 10 buổi gội', total: 10, used: 2 });
  await addRole(ZALO, 'customer');
  await addProfile(ZALO, { relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
  await addConsent(CUS, 'granted', T);
  // the section 14 answers, while 0011 is present and no chat row exists
  summaryBefore = await buildCustomerSummary(env, CUS, NOW);
  factsBefore = await customerFactsForModel(env, CUS, CV, NOW);
  expect(summaryBefore).not.toBeNull();

  // back to the shape of 0001-0010
  await run(CHAT_TABLES.map((t) => `DROP TABLE ${t}`));
});

describe('before migration 0011', () => {
  it('the schema really lacks what 0011 adds', async () => {
    for (const t of CHAT_TABLES) await expect(env.DB.prepare(`SELECT 1 FROM ${t}`).run()).rejects.toThrow(/no such table/);
    expect(await chatTablesPresent(env)).toBe(false);
  });

  it('the summary and the model facts are exactly those of section 14', async () => {
    expect(await loadChatSummaryInput(env, ZALO)).toBeNull();
    expect(await buildCustomerSummary(env, CUS, NOW)).toEqual(summaryBefore);
    expect(await customerFactsForModel(env, CUS, CV, NOW)).toEqual(factsBefore);
    expect(summaryBefore).not.toHaveProperty('chat');
    expect(factsBefore).not.toHaveProperty('visits_from_chat');
  });

  it('every endpoint of section 15.11 answers 409 invalid_state naming the migration, and writes nothing', async () => {
    const body = doc([entry(ZALO, { visits: [cand('2026-10-01')], upcoming: [upcoming('2026-12-01')], benefits: [benefit('Gói 5 buổi')], phone: phone('0912345901') })]);
    const calls: Array<[string, string, unknown?]> = [
      ['POST', '/staff/chat-facts/import', body],
      ['POST', '/staff/chat-facts/import', { ...body, dry_run: true }],
      ['GET', '/staff/chat-facts/eligible'],
      ['GET', `/staff/chat-facts/${enc(ZALO)}`],
      ['POST', '/staff/chat-facts/visits/chv_x/confirm', { amount_vnd: 300000 }],
      ['POST', '/staff/chat-facts/visits/chv_x/dismiss'],
      ['POST', '/staff/chat-facts/benefits/chb_x/confirm', { total_count: 5 }],
      ['POST', '/staff/chat-facts/benefits/chb_x/dismiss'],
      ['POST', `/staff/chat-facts/${enc(ZALO)}/phone/accept`],
      ['POST', `/staff/chat-facts/${enc(ZALO)}/phone/dismiss`],
    ];
    const before = await snapshot();
    for (const [method, path, b] of calls) {
      const r = await call(method, path, b);
      expect(r.status, `${method} ${path}`).toBe(409);
      expect(r.body.error.code, `${method} ${path}`).toBe('invalid_state');
      expect(r.body.error.message, `${method} ${path}`).toContain('0011_chat_facts.sql');
    }
    expect(await snapshot()).toEqual(before);
    expect(await count("SELECT COUNT(*) AS n FROM audit_log WHERE action LIKE 'chat_facts.%'")).toBe(0);
  });

  it('a role write and a phone edit work as in section 14 and touch no chat table', async () => {
    const other = 'p:930000000088002';
    await env.DB.prepare("INSERT INTO customers (id, oa_id, zalo_user_id, phone, channel, created_at) VALUES ('cus_m11b', 'personal', ?, '0907880002', 'personal', ?)").bind(other, T).run();
    const put = await call('PUT', `/staff/roles/${enc(other)}`, { role: 'staff' });
    expect(put.status).toBe(200);
    expect(put.body.role).toMatchObject({ role: 'staff', source: 'staff' });
    const imp = await call('POST', '/staff/roles/import', { source: 'zalo_label', roles: [{ zalo_user_id: 'p:930000000088003', role: 'manager' }] });
    expect(imp.status).toBe(200);
    expect(imp.body).toMatchObject({ imported: 1 });
    const cleared = await call('PATCH', '/staff/customers/cus_m11b', { phone: null });
    expect(cleared.status).toBe(200);
    expect(cleared.body.customer.phone).toBeNull();
    const replaced = await call('PATCH', `/staff/customers/${CUS}`, { phone: '0907880009' });
    expect(replaced.status).toBe(200);
    await call('PATCH', `/staff/customers/${CUS}`, { phone: '0907880001' });
    for (const t of CHAT_TABLES) await expect(env.DB.prepare(`SELECT 1 FROM ${t}`).run()).rejects.toThrow(/no such table/);
    await run(["DELETE FROM contact_roles WHERE zalo_user_id IN ('p:930000000088002', 'p:930000000088003')"]);
  });

  it('the conversation detail still carries the section 14 summary', async () => {
    const r = await call('GET', `/staff/conversations/${CNV}`);
    expect(r.status).toBe(200);
    expect(r.body.customer_summary).toEqual(JSON.parse(JSON.stringify(await buildCustomerSummary(env, CUS, Date.now()))));
    expect(r.body.customer_summary).not.toHaveProperty('chat');
  });

  it('recognises only the errors that mean "0011 is missing"', () => {
    for (const msg of [
      'D1_ERROR: no such table: chat_visits: SQLITE_ERROR',
      'D1_ERROR: no such table: main.chat_benefits: SQLITE_ERROR',
      'D1_ERROR: no such table: chat_contact_facts: SQLITE_ERROR',
      'D1_ERROR: no such table: chat_phone_dismissed: SQLITE_ERROR',
      'D1_ERROR: no such column: phone_decision_id: SQLITE_ERROR',
    ]) {
      expect(isMissingMigration0011(new Error(msg)), msg).toBe(true);
      expect(isMissingMigration0010(new Error(msg)), msg).toBe(false);
    }
    for (const msg of [
      'D1_ERROR: no such table: contact_roles: SQLITE_ERROR',
      'D1_ERROR: no such table: customer_profiles: SQLITE_ERROR',
      'D1_ERROR: no such column: chat_visits_x: SQLITE_ERROR',
      'D1_ERROR: UNIQUE constraint failed: chat_visits.zalo_user_id, chat_visits.local_date, chat_visits.kind: SQLITE_CONSTRAINT',
    ]) {
      expect(isMissingMigration0011(new Error(msg)), msg).toBe(false);
    }
    expect(isMissingMigration0011('no such table: chat_visits')).toBe(true);
  });
});

describe('applying migration 0011 on a database at 0010 with rows', () => {
  let before: Record<string, unknown[]> = {};
  beforeAll(async () => {
    before = await snapshot();
    await run(queriesOf('0011_'));
  });

  it('keeps every row of the existing tables', async () => {
    expect(before.visits).toHaveLength(2);
    expect(before.customer_benefits).toHaveLength(1);
    expect(await snapshot()).toEqual(before);
  });

  it('creates the four tables empty, with the index and the checks', async () => {
    expect(await chatTablesPresent(env)).toBe(true);
    for (const t of CHAT_TABLES) expect(await count(`SELECT COUNT(*) AS n FROM ${t}`), t).toBe(0);
    const idx = await env.DB.prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_chat_visits_contact'").first();
    expect(idx).toEqual({ name: 'idx_chat_visits_contact' });
    const ins = (id: string, date: string, kind: string, over: Record<string, unknown> = {}) =>
      env.DB.prepare(
        'INSERT INTO chat_visits (id, zalo_user_id, local_date, kind, visited_at, time_known, services_json, amount_vnd, amount_source, confidence, signals_json, evidence_json, fact_source, analyzer_version, imported_at) ' +
          "VALUES (?,?,?,?,1,0,'[]',?,?,?,'[]','[]',?,'v1',1)",
      )
        .bind(id, ZALO, date, kind, over.amount ?? null, over.source ?? null, over.confidence ?? 'high', over.fact ?? 'chat_rules')
        .run();
    await ins('chv_m11a', '2026-10-01', 'visit');
    await ins('chv_m11b', '2026-10-01', 'upcoming', { confidence: null });
    await expect(ins('chv_m11c', '2026-10-01', 'visit')).rejects.toThrow(/UNIQUE/);
    await expect(ins('chv_m11d', '2026-10-02', 'walk_in')).rejects.toThrow(/CHECK/);
    await expect(ins('chv_m11e', '2026-10-03', 'visit', { amount: 999 })).rejects.toThrow(/CHECK/);
    await expect(ins('chv_m11f', '2026-10-04', 'visit', { source: 'guess' })).rejects.toThrow(/CHECK/);
    await expect(ins('chv_m11g', '2026-10-05', 'visit', { fact: 'chat' })).rejects.toThrow(/CHECK/);
    const ben = (id: string, key: string, total: number | null, remaining: number | null) =>
      env.DB.prepare(
        "INSERT INTO chat_benefits (id, zalo_user_id, kind, title, title_key, total_count, remaining, stated_by, confidence, stated_at, analyzer_version, imported_at) VALUES (?,?,'package','Gói',?,?,?,'owner','high',1,'v1',1)",
      )
        .bind(id, ZALO, key, total, remaining)
        .run();
    await ben('chb_m11a', 'goi a', 10, 7);
    await expect(ben('chb_m11b', 'goi a', 10, 7)).rejects.toThrow(/UNIQUE/);
    await expect(ben('chb_m11c', 'goi c', 5, 6)).rejects.toThrow(/CHECK/);
    await expect(ben('chb_m11d', 'goi d', 201, null)).rejects.toThrow(/CHECK/);
    await expect(env.DB.prepare("INSERT INTO chat_contact_facts (zalo_user_id, analyzer_version, generated_at, imported_at, messages, phone_state, model_pass_json) VALUES (?, 'v1', 1, 1, 0, 'maybe', '{}')").bind(ZALO).run()).rejects.toThrow(/CHECK/);
    const dis = (phoneNumber: string, reason: string) =>
      env.DB.prepare('INSERT INTO chat_phone_dismissed (zalo_user_id, phone, reason, decided_by, decided_at) VALUES (?,?,?,\'tester\',1)').bind(ZALO, phoneNumber, reason).run();
    await dis('0912345903', 'suggestion_dismissed');
    await dis('0912345904', 'staff_removed');
    await expect(dis('0912345903', 'staff_removed')).rejects.toThrow(/UNIQUE|PRIMARY/);
    await expect(dis('0912345905', 'forgotten')).rejects.toThrow(/CHECK/);
    await run(['DELETE FROM chat_phone_dismissed']);
    await run(['DELETE FROM chat_visits', 'DELETE FROM chat_benefits']);
  });

  it('makes the endpoints and the summary work', async () => {
    const r = await call('POST', '/staff/chat-facts/import', doc([entry(ZALO, { visits: [cand('2026-09-01')], phone: phone('0912345902') })]));
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ customers: 1, unmatched: 0, visits_imported: 1 });
    expect((await call('GET', `/staff/chat-facts/${enc(ZALO)}`)).body.facts.visits).toHaveLength(1);
    expect((await call('GET', '/staff/chat-facts/eligible')).body.zalo_user_ids).toContain(ZALO);
    const s = await buildCustomerSummary(env, CUS, NOW);
    expect(s).toMatchObject({ visits_total: 3, chat: { visits_counted: 1, phone_suggestion: false } });
  });
});
