// Migration 0008_profiles_v2.sql on a D1 that has 0007 only (`wrangler dev` reloads the new code before the owner
// applies the migration). Before 0008: reads and the customer path work, imports answer 409 (they write
// last_service_json), a PATCH to family / staff / friend answers 409 (CHECK), a PATCH to customer works. Applying 0008
// keeps every row as it was and accepts the new relationships. This file rebuilds customer_profiles in its own D1.
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { isMissingProfilesV2, personalSkipApplies, profileFactsForModel } from '../src/lib/profiles';
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

const ROW_COLS =
  'zalo_user_id, display_name, relationship, relationship_confidence, relationship_reasons_json, address_term, name_to_use, address_confidence, ' +
  'addressing_json, services_json, evidence_json, stats_json, analyzer_json, analyzer_version, source, staff_override, staff_fields_json, staff_note, ' +
  'analyzed_at, created_at, updated_at, updated_by';

beforeAll(async () => {
  await seed();
  await env.DB.prepare('DROP TABLE IF EXISTS customer_profiles').run();
  await run(queriesOf('0007_'));
  await env.DB.prepare(
    `INSERT INTO customer_profiles (${ROW_COLS}) VALUES ('p:9400001','Mẹ','personal','high','["kinship_vocative:4"]',NULL,NULL,'low','{}','[]','[]','{"messages_in":12}',` +
      `'{"relationship":"personal"}','contacts-rules-v2','analyzer',1,'["relationship"]','người nhà',1762600000000,1762600000000,1762600000001,'tester')`,
  ).run();
  await env.DB.prepare(
    `INSERT INTO customer_profiles (${ROW_COLS}) VALUES ('p:9400002','Nguyễn Thị Lan','customer','medium','[]','chị','Lan','medium','{}',` +
      `'[{"key":"massage-chan","service_id":"massage-chan","name":"Massage chân","group":"relaxation","sensitive":false,"status":"likely_used","mention_count":1,"last_mentioned_at":1,"used_signal_count":1,"last_used_signal_at":1}]',` +
      `'[]','{}',NULL,'contacts-rules-v2','analyzer',0,'[]',NULL,1762600000000,1762600000000,1762600000000,'analyzer')`,
  ).run();
});

describe('before migration 0008', () => {
  it('reads and the customer path work; writes that need 0008 answer 409', async () => {
    const g = await call('GET', '/staff/profiles/p:9400002');
    expect(g.status).toBe(200);
    expect(g.body.profile).toMatchObject({ relationship: 'customer', address_term: 'chị', last_service: null });
    expect(await profileFactsForModel(env, 'p:9400002', null)).toMatchObject({ address_term: 'chị', services_likely_used: ['Massage chân'] });
    expect(await personalSkipApplies(env, { id: 'cus_none', zalo_user_id: 'p:9400002' }, 'cnv_none')).toBe(false);

    const imp = await call('POST', '/staff/profiles/import', {
      profiles: [{ zalo_user_id: 'p:9400003', display_name: null, relationship: 'customer', relationship_confidence: 'low', relationship_reasons: [],
        address_term: null, name_to_use: null, address_confidence: 'low', addressing: {}, services: [], evidence: [], stats: {} }],
    });
    expect(imp.status).toBe(409);
    expect(imp.body.error.message).toContain('0008_profiles_v2');
    const fam = await call('PATCH', '/staff/profiles/p:9400002', { relationship: 'family' });
    expect(fam.status).toBe(409);
    const ok = await call('PATCH', '/staff/profiles/p:9400002', { name_to_use: 'Hoa' });
    expect(ok.status).toBe(200);
    expect(isMissingProfilesV2(new Error('D1_ERROR: table customer_profiles has no column named last_service_json'))).toBe(true);
    expect(isMissingProfilesV2(new Error('no such column: other'))).toBe(false);
  });
});

describe('migration 0008', () => {
  it('keeps every row and column value, adds last_service_json, and accepts staff / family / friend', async () => {
    const before = await env.DB.prepare(`SELECT ${ROW_COLS} FROM customer_profiles ORDER BY zalo_user_id`).all();
    await run(queriesOf('0008_'));
    const after = await env.DB.prepare(`SELECT ${ROW_COLS}, last_service_json FROM customer_profiles ORDER BY zalo_user_id`).all<Record<string, unknown>>();
    expect(after.results.map(({ last_service_json: _l, ...rest }) => rest)).toEqual(before.results);
    expect(after.results.every((r) => r.last_service_json === null)).toBe(true);
    const idx = await env.DB.prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'customer_profiles' AND name LIKE 'idx_%' ORDER BY name").all<{ name: string }>();
    expect(idx.results.map((r) => r.name)).toEqual(['idx_customer_profiles_rel', 'idx_customer_profiles_updated']);

    // the legacy 'personal' row keeps its staff fields and gives no model facts
    const legacy = await call('GET', '/staff/profiles/p:9400001');
    expect(legacy.body.profile).toMatchObject({ relationship: 'personal', staff_override: true, staff_note: 'người nhà', model_facts: null });
    expect((await call('PATCH', '/staff/profiles/p:9400002', { relationship: 'family' })).status).toBe(200);
    await expect(env.DB.prepare("UPDATE customer_profiles SET relationship = 'enemy' WHERE zalo_user_id = 'p:9400002'").run()).rejects.toThrow(/CHECK/);
  });
});
