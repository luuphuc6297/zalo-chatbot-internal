// Migration 0010_rooms_roles_customer.sql on a D1 that has 0001-0009 only (`wrangler dev` reloads the new code before
// the owner applies the migration). Before 0010: the role and summary lookups answer "nothing known", the section 14
// endpoints answer 409 invalid_state naming the migration, and what worked before section 14 still works. Applying
// 0010 keeps every visits, conversations and messages row. This file rebuilds the old shape in its own D1.
// Every name, phone number and id is synthetic.
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { customerFactsForModel, buildCustomerSummary } from '../src/lib/customer-summary';
import { getContactRole, getContactRoles, isMissingMigration0010 } from '../src/lib/roles';
import { DAY_MS } from '../src/lib/time';
import { seed } from './core-helpers';

async function call(method: string, path: string, body?: unknown) {
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, {
      method,
      headers: { 'content-type': 'application/json', authorization: 'Bearer test-staff-token', 'x-staff-id': 'tester' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

function queriesOf(prefix: string): string[] {
  const m = env.TEST_MIGRATIONS.find((x) => x.name.startsWith(prefix));
  expect(m, prefix).toBeDefined();
  return m!.queries;
}

async function run(queries: string[]) {
  await env.DB.batch(queries.map((q) => env.DB.prepare(q)));
}

const GOI = 'goi-dau-thu-gian';
const CHAN = 'massage-chan';
const CUS = 'cus_m10a';
const ZALO = 'p:930000000077001';
const CNV = 'cnv_m10a';
const T = Date.now() - 40 * DAY_MS;
const OLD_VISIT_COLS = 'id, customer_id, service_id, visited_at, source, external_visit_id, booking_request_id, recorded_by, created_at';
const OLD_VISITS = [
  { id: 'vis_m10a', customer_id: CUS, service_id: GOI, visited_at: T, source: 'staff', external_visit_id: null, booking_request_id: null, recorded_by: 'tester', created_at: T + 1 },
  { id: 'vis_m10b', customer_id: CUS, service_id: CHAN, visited_at: T + 5 * DAY_MS, source: 'booking_app', external_visit_id: 'app-m10-1', booking_request_id: 'bkr_m10', recorded_by: null, created_at: T + 5 * DAY_MS },
];
let catalogVersion = '';

const count = async (sql: string, ...binds: unknown[]) => (await env.DB.prepare(sql).bind(...binds).first<{ n: number }>())!.n;
const insertMessage = (id: string, seq: number) =>
  env.DB.prepare("INSERT INTO messages (id, conversation_id, direction, source, text, seq, created_at) VALUES (?,?,'inbound','customer',?,?,?)").bind(id, CNV, 'tin nhắn thử', seq, T + seq).run();

beforeAll(async () => {
  catalogVersion = (await seed()).catalog_version;
  await env.DB.prepare("INSERT INTO customers (id, oa_id, zalo_user_id, channel, created_at) VALUES (?, 'personal', ?, 'personal', ?)").bind(CUS, ZALO, T).run();
  await env.DB.prepare("INSERT INTO conversations (id, customer_id, oa_id, bot_state, created_at, updated_at) VALUES (?, ?, 'personal', 'bot_active', ?, ?)").bind(CNV, CUS, T, T).run();
  await insertMessage('msg_m10a', 1);
  await insertMessage('msg_m10b', 2);

  // back to the shape of 0001-0009
  const oldVisitsDdl = queriesOf('0001_').find((q) => /CREATE TABLE visits\b/.test(q));
  expect(oldVisitsDdl).toBeDefined();
  await run([
    'DROP INDEX IF EXISTS idx_messages_room_pending',
    'ALTER TABLE messages DROP COLUMN room_mirrored_at',
    'ALTER TABLE conversations DROP COLUMN auto_reply',
    'ALTER TABLE conversations DROP COLUMN room_channel_id',
    'ALTER TABLE conversations DROP COLUMN room_synced_at',
    'DROP TABLE contact_roles',
    'DROP TABLE customer_benefits',
    'DROP TABLE visits',
    oldVisitsDdl!,
  ]);
  for (const v of OLD_VISITS) {
    await env.DB.prepare(`INSERT INTO visits (${OLD_VISIT_COLS}) VALUES (?,?,?,?,?,?,?,?,?)`)
      .bind(v.id, v.customer_id, v.service_id, v.visited_at, v.source, v.external_visit_id, v.booking_request_id, v.recorded_by, v.created_at)
      .run();
  }
});

describe('before migration 0010', () => {
  it('answers "nothing known" from the role and summary lookups instead of failing', async () => {
    expect(await getContactRole(env, ZALO)).toBeNull();
    expect((await getContactRoles(env, [ZALO, 'p:930000000077002'])).size).toBe(0);
    expect(await buildCustomerSummary(env, CUS, Date.now())).toBeNull();
    expect(await customerFactsForModel(env, CUS, catalogVersion, Date.now())).toEqual({ found: false, reason: 'no_data' });
  });

  it('answers 409 invalid_state naming the migration on every endpoint that needs it', async () => {
    const row = { customer_id: CUS, visited_at_local: '2026-10-01 10:00', service_id: GOI };
    const calls: Array<[string, string, unknown?]> = [
      ['POST', '/staff/roles/import', { source: 'zalo_label', roles: [{ zalo_user_id: ZALO, role: 'customer' }] }],
      ['GET', '/staff/roles'],
      ['PUT', `/staff/roles/${encodeURIComponent(ZALO)}`, { role: 'staff' }],
      ['POST', '/staff/visits/import', { visits: [row] }],
      ['POST', '/staff/visits/import', { visits: [row], dry_run: true }],
      ['GET', `/staff/visits?customer_id=${CUS}`],
      ['GET', `/staff/benefits?customer_id=${CUS}`],
      ['POST', '/staff/benefits', { customer_id: CUS, kind: 'package', title: 'Gói 5 buổi', total_count: 5 }],
      ['PATCH', '/staff/benefits/ben_missing', { status: 'void' }],
    ];
    for (const [method, path, body] of calls) {
      const r = await call(method, path, body);
      expect(r.status, `${method} ${path}`).toBe(409);
      expect(r.body.error.code, `${method} ${path}`).toBe('invalid_state');
      expect(r.body.error.message, `${method} ${path}`).toContain('0010_rooms_roles_customer.sql');
    }
    expect(await count('SELECT COUNT(*) AS n FROM visits')).toBe(OLD_VISITS.length);
    expect(await count("SELECT COUNT(*) AS n FROM audit_log WHERE action LIKE 'roles.%' OR action LIKE 'benefit.%' OR action = 'visits.import'")).toBe(0);
  });

  it('still records a visit sent with the body from before section 14, with both jobs', async () => {
    const r = await call('POST', '/staff/visits', { customer_id: CUS, service_id: GOI, visited_at: Date.now() - DAY_MS });
    expect(r.status).toBe(200);
    expect(r.body.jobs).toHaveLength(2);
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE id = ?', r.body.visit_id)).toBe(1);
    await env.DB.prepare('DELETE FROM jobs WHERE customer_id = ?').bind(CUS).run();
    await env.DB.prepare('DELETE FROM visits WHERE id = ?').bind(r.body.visit_id).run();
  });

  it('answers 409 for a visit that carries one of the new fields, and writes nothing', async () => {
    const base = { customer_id: CUS, service_id: GOI, visited_at: Date.now() - DAY_MS };
    for (const extra of [{ amount_vnd: 250_000 }, { technician: 'Mai' }, { benefit_id: 'ben_missing' }]) {
      const r = await call('POST', '/staff/visits', { ...base, ...extra });
      expect(r.status, JSON.stringify(extra)).toBe(409);
      expect(r.body.error.code).toBe('invalid_state');
      expect(r.body.error.message).toContain('0010_rooms_roles_customer.sql');
    }
    expect(await count('SELECT COUNT(*) AS n FROM visits')).toBe(OLD_VISITS.length);
    expect(await count('SELECT COUNT(*) AS n FROM jobs WHERE customer_id = ?', CUS)).toBe(0);
  });

  it('still saves a phone number, which needs no new table', async () => {
    const r = await call('PATCH', `/staff/customers/${CUS}`, { phone: '0907 770 001' });
    expect(r.status).toBe(200);
    expect((await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(CUS).first<{ phone: string }>())!.phone).toBe('0907770001');
  });

  it('recognises only the errors that mean "0010 is missing"', () => {
    for (const msg of [
      'D1_ERROR: no such table: contact_roles: SQLITE_ERROR',
      'D1_ERROR: no such table: main.customer_benefits: SQLITE_ERROR',
      'D1_ERROR: table visits has no column named service_name: SQLITE_ERROR',
      'D1_ERROR: no such column: amount_vnd at offset 12: SQLITE_ERROR',
      'D1_ERROR: no such column: c.auto_reply: SQLITE_ERROR',
    ]) {
      expect(isMissingMigration0010(new Error(msg)), msg).toBe(true);
    }
    for (const msg of [
      'D1_ERROR: no such table: customer_profiles: SQLITE_ERROR',
      'D1_ERROR: no such column: last_service_json: SQLITE_ERROR',
      'D1_ERROR: UNIQUE constraint failed: visits.external_visit_id: SQLITE_CONSTRAINT',
      'D1_ERROR: CHECK constraint failed: used_count >= 0 AND used_count <= total_count: SQLITE_CONSTRAINT',
    ]) {
      expect(isMissingMigration0010(new Error(msg)), msg).toBe(false);
    }
    expect(isMissingMigration0010('no such table: contact_roles')).toBe(true);
  });
});

describe('applying migration 0010 on a database with rows', () => {
  beforeAll(async () => {
    await run(queriesOf('0010_'));
  });

  it('keeps every visit with its values and leaves the new columns empty', async () => {
    const { results } = await env.DB.prepare(`SELECT ${OLD_VISIT_COLS} FROM visits ORDER BY id`).all();
    expect(results).toEqual(OLD_VISITS);
    const extra = await env.DB.prepare('SELECT service_name, duration_min, amount_vnd, technician, benefit_id FROM visits ORDER BY id').all();
    expect(extra.results).toEqual(OLD_VISITS.map(() => ({ service_name: null, duration_min: null, amount_vnd: null, technician: null, benefit_id: null })));
  });

  it('marks the messages that existed as never to be mirrored, and leaves a new message pending', async () => {
    const before = await env.DB.prepare('SELECT id, room_mirrored_at FROM messages WHERE conversation_id = ? ORDER BY seq').bind(CNV).all();
    expect(before.results).toEqual([
      { id: 'msg_m10a', room_mirrored_at: 0 },
      { id: 'msg_m10b', room_mirrored_at: 0 },
    ]);
    await insertMessage('msg_m10c', 3);
    expect(await env.DB.prepare("SELECT room_mirrored_at FROM messages WHERE id = 'msg_m10c'").first()).toEqual({ room_mirrored_at: null });
  });

  it('keeps the conversation and leaves its new columns NULL', async () => {
    const c = await env.DB.prepare('SELECT id, customer_id, bot_state, auto_reply, room_channel_id, room_synced_at FROM conversations WHERE id = ?').bind(CNV).first();
    expect(c).toEqual({ id: CNV, customer_id: CUS, bot_state: 'bot_active', auto_reply: null, room_channel_id: null, room_synced_at: null });
  });

  it('accepts the new visit sources and enforces the new checks', async () => {
    const ins = (id: string, source: string, amount: number | null, duration: number | null, ext: string | null) =>
      env.DB.prepare('INSERT INTO visits (id, customer_id, service_id, visited_at, source, amount_vnd, duration_min, external_visit_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)')
        .bind(id, CUS, GOI, T, source, amount, duration, ext, T)
        .run();
    await ins('vis_m10c', 'import', 0, 60, 'imp-m10-1');
    await ins('vis_m10d', 'booking_request', null, null, null);
    await expect(ins('vis_m10e', 'walk_in', null, null, null)).rejects.toThrow(/CHECK/);
    await expect(ins('vis_m10f', 'staff', -1, null, null)).rejects.toThrow(/CHECK/);
    await expect(ins('vis_m10g', 'staff', null, 0, null)).rejects.toThrow(/CHECK/);
    await expect(ins('vis_m10h', 'import', null, null, 'app-m10-1')).rejects.toThrow(/UNIQUE/);
    await expect(env.DB.prepare("UPDATE conversations SET auto_reply = 'maybe' WHERE id = ?").bind(CNV).run()).rejects.toThrow(/CHECK/);
    await env.DB.prepare("UPDATE conversations SET auto_reply = 'off' WHERE id = ?").bind(CNV).run();
    expect(await count('SELECT COUNT(*) AS n FROM visits')).toBe(OLD_VISITS.length + 2);
  });

  it('creates the three indexes', async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type = 'index' AND name IN ('idx_visits_customer','idx_benefits_customer','idx_messages_room_pending') ORDER BY name",
    ).all<{ name: string }>();
    expect(results.map((r) => r.name)).toEqual(['idx_benefits_customer', 'idx_messages_room_pending', 'idx_visits_customer']);
  });

  it('makes the roles, benefits and summary work', async () => {
    const put = await call('PUT', `/staff/roles/${encodeURIComponent(ZALO)}`, { role: 'customer' });
    expect(put.status).toBe(200);
    expect(await getContactRole(env, ZALO)).toMatchObject({ zalo_user_id: ZALO, role: 'customer', source: 'staff' });
    expect((await call('GET', '/staff/roles')).status).toBe(200);

    const ben = await call('POST', '/staff/benefits', { customer_id: CUS, kind: 'package', title: 'Gói 5 buổi', total_count: 5 });
    expect(ben.status).toBe(200);
    const visit = await call('POST', '/staff/visits', { customer_id: CUS, service_id: GOI, visited_at: Date.now() - DAY_MS, amount_vnd: 0, benefit_id: ben.body.benefit.id });
    expect(visit.status).toBe(200);
    expect(await env.DB.prepare('SELECT used_count FROM customer_benefits WHERE id = ?').bind(ben.body.benefit.id).first()).toEqual({ used_count: 1 });

    const summary = await buildCustomerSummary(env, CUS, Date.now());
    expect(summary).not.toBeNull();
    expect(summary!.role).toBe('customer');
    expect(summary!.phone).toBe('0907770001');
    const facts = await customerFactsForModel(env, CUS, catalogVersion, Date.now());
    expect(facts.found).toBe(true);
    expect(JSON.stringify(facts)).not.toContain('0907770001');
  });
});
