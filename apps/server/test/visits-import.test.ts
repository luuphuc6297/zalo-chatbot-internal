// POST /staff/visits/import and GET /staff/visits (docs/contracts.md section 14.5). All data is synthetic.
import { env, SELF } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { normalizePhone } from '../src/lib/customer-summary';
import { HOUR_MS, TZ_OFFSET_MS } from '../src/lib/time';
import { MAX_IMPORT_VISITS, importVisits, parseLocalDateTime, serviceSlug } from '../src/staff-api/customers';
import { seed, staff } from './core-helpers';
import { BODY, CHAN, GOI, NOW, addVisit, auditCount, catalog, count, jobCount, lastAudit, newCustomer, nextPhone, nextZaloId, past, visitsOf } from './customers-helpers';

let NAMES: Record<string, string> = {};
const imp = (visits: unknown, extra: Record<string, unknown> = {}) => staff('POST', '/staff/visits/import', { visits, ...extra });
const LOCAL = '2024-03-05 14:30';
const LOCAL_MS = Date.UTC(2024, 2, 5, 14, 30) - TZ_OFFSET_MS;

beforeAll(async () => {
  await seed();
  NAMES = (await catalog()).names;
  expect(NAMES[GOI]).toBeTruthy();
});

describe('POST /staff/visits/import', () => {
  it('imports rows matched by customer_id, zalo_user_id and phone, without follow-up jobs', async () => {
    const a = await newCustomer();
    const b = await newCustomer();
    const phone = nextPhone();
    const c = await newCustomer({ phone });
    const r = await imp([
      { customer_id: a.id, service_id: GOI, visited_at: past(3), amount_vnd: 250000, technician: ' Hoa ', duration_min: 60 },
      { zalo_user_id: b.zalo, service_id: CHAN, visited_at_local: LOCAL, external_visit_id: 'ext-imp-1' },
      { phone: `+84 ${phone.slice(1, 4)}.${phone.slice(4, 7)}-${phone.slice(7)}`, service_name: 'Xông hơi thảo dược', visited_at: past(2), amount_vnd: 0 },
    ]);
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ imported: 3, duplicates: 0, created_customers: 0, unmatched: [] });

    expect(await visitsOf(a.id)).toEqual([
      expect.objectContaining({ service_id: GOI, service_name: null, visited_at: past(3), amount_vnd: 250000, technician: 'Hoa', duration_min: 60, source: 'import', benefit_id: null, booking_request_id: null, external_visit_id: null, recorded_by: 'tester' }),
    ]);
    expect(await visitsOf(b.id)).toEqual([expect.objectContaining({ service_id: CHAN, visited_at: LOCAL_MS, external_visit_id: 'ext-imp-1', amount_vnd: null, technician: null, duration_min: null })]);
    expect(await visitsOf(c.id)).toEqual([expect.objectContaining({ service_id: 'ext:xong-hoi-thao-duoc', service_name: 'Xông hơi thảo dược', amount_vnd: 0, source: 'import' })]);
    for (const cu of [a, b, c]) expect(await jobCount(cu.id)).toBe(0);

    const audit = await lastAudit('visits.import');
    expect(audit).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'visits', entity_id: null });
    expect(JSON.parse(audit!.after_json!)).toEqual({ imported: 3, duplicates: 0, created_customers: 0, unmatched: 0 });
    expect(`${audit!.before_json}${audit!.after_json}`).not.toMatch(/p:|0907|Hoa|Xông/);
  });

  it('creates one minimal customers row for a new p: contact and detects a re-import', async () => {
    const z1 = nextZaloId();
    const z2 = nextZaloId();
    const rows = [
      { zalo_user_id: z1, service_id: GOI, visited_at: past(9), display_name: 'Lan', phone: nextPhone() },
      { zalo_user_id: z1, service_id: GOI, visited_at: past(5) },
      { zalo_user_id: z2, service_id: CHAN, visited_at: past(4) },
    ];
    const r = await imp(rows);
    expect(r.body).toEqual({ imported: 3, duplicates: 0, created_customers: 2, unmatched: [] });
    const { results } = await env.DB.prepare('SELECT id, oa_id, channel, display_name, phone, user_id_by_app, deleted_at FROM customers WHERE zalo_user_id = ?').bind(z1).all<Record<string, unknown>>();
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ oa_id: 'personal', channel: 'personal', display_name: null, phone: null, user_id_by_app: null, deleted_at: null });
    expect(String(results[0]!.id)).toMatch(/^cus_/);
    expect(await visitsOf(String(results[0]!.id))).toHaveLength(2);
    expect(await count('SELECT COUNT(*) AS n FROM conversations WHERE customer_id = ?', results[0]!.id)).toBe(0);

    const again = await imp(rows);
    expect(again.body).toEqual({ imported: 0, duplicates: 3, created_customers: 0, unmatched: [] });
    expect(await count('SELECT COUNT(*) AS n FROM customers WHERE zalo_user_id IN (?, ?)', z1, z2)).toBe(2);
  });

  it('answers no_customer for ids it cannot resolve and matches an existing OA user id', async () => {
    const oa = await newCustomer({ zalo_user_id: '5550001112223', oa_id: 'test-oa-id', channel: 'oa' });
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    const twice = nextZaloId();
    await newCustomer({ zalo_user_id: twice });
    await newCustomer({ zalo_user_id: twice, oa_id: 'test-oa-id', channel: 'oa' });
    const r = await imp([
      { zalo_user_id: oa.zalo, service_id: GOI, visited_at: past(3) },
      { zalo_user_id: '5550009998887', service_id: GOI, visited_at: past(3) },
      { zalo_user_id: 'p:abc', service_id: GOI, visited_at: past(3) },
      { zalo_user_id: gone.zalo, service_id: GOI, visited_at: past(3) },
      { zalo_user_id: twice, service_id: GOI, visited_at: past(3) },
      { zalo_user_id: 12345, service_id: GOI, visited_at: past(3) },
      { customer_id: gone.id, service_id: GOI, visited_at: past(3) },
      { customer_id: 'cus_missing', service_id: GOI, visited_at: past(3) },
      { service_id: GOI, visited_at: past(3) },
    ]);
    expect(r.body).toEqual({ imported: 1, duplicates: 0, created_customers: 0, unmatched: [1, 2, 3, 4, 5, 6, 7, 8].map((index) => ({ index, reason: 'no_customer' })) });
    expect(await visitsOf(oa.id)).toHaveLength(1);
    expect(await visitsOf(gone.id)).toHaveLength(0);
    expect(await count("SELECT COUNT(*) AS n FROM customers WHERE zalo_user_id IN ('5550009998887', 'p:abc')")).toBe(0);
  });

  it('matches a phone on its normalised digits and only when exactly one customer has it', async () => {
    const phone = nextPhone();
    const a = await newCustomer({ phone: `+84 ${phone.slice(1, 4)} ${phone.slice(4)}` }); // stored in another spelling
    const shared = nextPhone();
    await newCustomer({ phone: shared });
    await newCustomer({ phone: shared });
    const deletedPhone = nextPhone();
    await newCustomer({ phone: deletedPhone, deleted_at: 1_700_000_000_001 });
    const r = await imp([
      { phone: `${phone.slice(0, 4)} ${phone.slice(4, 7)} ${phone.slice(7)}`, service_id: GOI, visited_at: past(8) },
      { phone: `+84${phone.slice(1)}`, service_id: GOI, visited_at: past(7) },
      { phone: `84${phone.slice(1)}`, service_id: GOI, visited_at: past(6) },
      { phone: shared, service_id: GOI, visited_at: past(5) },
      { phone: nextPhone(), service_id: GOI, visited_at: past(5) },
      { phone: 'abc', service_id: GOI, visited_at: past(5) },
      { phone: deletedPhone, service_id: GOI, visited_at: past(5) },
      { phone: Number(phone), service_id: GOI, visited_at: past(5) },
    ]);
    expect(r.body).toEqual({ imported: 3, duplicates: 0, created_customers: 0, unmatched: [3, 4, 5, 6, 7].map((index) => ({ index, reason: 'no_customer' })) });
    expect(await visitsOf(a.id)).toHaveLength(3);
  });

  it('lets the first customer key that is given decide, without falling through', async () => {
    const phone = nextPhone();
    const a = await newCustomer({ phone });
    const r = await imp([
      { customer_id: 'cus_missing', phone, service_id: GOI, visited_at: past(3) },
      { customer_id: '', zalo_user_id: null, phone, service_id: GOI, visited_at: past(3) },
      { zalo_user_id: 'p:abc', phone, service_id: GOI, visited_at: past(2) },
    ]);
    expect(r.body).toEqual({ imported: 1, duplicates: 0, created_customers: 0, unmatched: [{ index: 0, reason: 'no_customer' }, { index: 2, reason: 'no_customer' }] });
    expect(await visitsOf(a.id)).toHaveLength(1);
  });

  it('reports bad_time, bad_service and bad_amount in that order and writes nothing for those rows', async () => {
    const a = await newCustomer();
    const base = { customer_id: a.id, service_id: GOI };
    const ok = { customer_id: a.id, visited_at: past(3) };
    const r = await imp([
      { ...base }, // 0 no time
      { ...base, visited_at_local: '2024-02-30 10:00' },
      { ...base, visited_at_local: '2024-03-05' },
      { ...base, visited_at_local: '2024-03-05 24:00' },
      { ...base, visited_at: Date.now() + 2 * HOUR_MS },
      { ...base, visited_at: Math.floor(past(3) / 1000) }, // 5 seconds, not ms
      { ...base, visited_at_local: 20240305 },
      { ...base, visited_at: 'yesterday' },
      { ...ok, service_name: '!!!' }, // 8
      { ...ok, service_name: 'Gội\nđầu' },
      { ...ok, service_name: 'x'.repeat(121) },
      { ...ok, service_name: 42 },
      { ...ok, service_id: GOI, service_name: 'a\nb' }, // 12 a bad name even with a catalog id
      { ...ok, service_id: 'khong-co-dich-vu' },
      { ...ok },
      { ...ok, service_id: GOI, amount_vnd: -1 }, // 15
      { ...ok, service_id: GOI, amount_vnd: 1.5 },
      { ...ok, service_id: GOI, amount_vnd: '250000' },
      { customer_id: a.id, service_name: '!!!', amount_vnd: -1 }, // 18 bad_time wins
      { ...ok, service_name: '!!!', amount_vnd: -1 }, // 19 bad_service wins
    ]);
    const reason = (from: number, to: number, r2: string) => Array.from({ length: to - from + 1 }, (_, k) => ({ index: from + k, reason: r2 }));
    expect(r.body).toEqual({
      imported: 0,
      duplicates: 0,
      created_customers: 0,
      unmatched: [...reason(0, 7, 'bad_time'), ...reason(8, 14, 'bad_service'), ...reason(15, 17, 'bad_amount'), { index: 18, reason: 'bad_time' }, { index: 19, reason: 'bad_service' }],
    });
    expect(await visitsOf(a.id)).toHaveLength(0);
    expect(JSON.parse((await lastAudit('visits.import'))!.after_json!)).toEqual({ imported: 0, duplicates: 0, created_customers: 0, unmatched: 20 });
  });

  it('counts duplicates by external_visit_id and by customer, time and service', async () => {
    const a = await newCustomer();
    await addVisit(a.id, past(10), GOI, { external_visit_id: 'ext-dup-1' });
    const viaStaff = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: CHAN, visited_at: past(9) });
    expect(viaStaff.status).toBe(200);
    const r = await imp([
      { customer_id: a.id, service_id: BODY, visited_at: past(2), external_visit_id: 'ext-dup-1' }, // id in the table
      { customer_id: a.id, service_id: GOI, visited_at: past(8), external_visit_id: 'ext-dup-2' },
      { customer_id: a.id, service_id: CHAN, visited_at: past(7), external_visit_id: 'ext-dup-2' }, // id earlier in the request
      { customer_id: a.id, service_id: CHAN, visited_at: past(9) }, // key of the visit recorded by staff
      { customer_id: a.id, service_id: GOI, visited_at: past(6) },
      { customer_id: a.id, service_id: GOI, visited_at: past(6) }, // key earlier in the request
      { customer_id: a.id, service_id: CHAN, visited_at: past(6) }, // same time, another service
    ]);
    expect(r.body).toEqual({ imported: 3, duplicates: 4, created_customers: 0, unmatched: [] });
    expect((await visitsOf(a.id)).map((v) => `${v.source}:${v.service_id}`).sort()).toEqual([`import:${CHAN}`, `import:${GOI}`, `import:${GOI}`, `staff:${CHAN}`, `staff:${GOI}`].sort());
  });

  it('dry_run answers the counts of the real run and writes nothing', async () => {
    const a = await newCustomer();
    const z = nextZaloId();
    const rows = [
      { customer_id: a.id, service_id: GOI, visited_at: past(3) },
      { zalo_user_id: z, service_name: 'Tắm trắng', visited_at: past(3) },
      { customer_id: a.id, service_id: GOI, visited_at: past(3) },
      { customer_id: a.id, service_id: GOI },
    ];
    const audits = await auditCount('visits.import');
    const expected = { imported: 2, duplicates: 1, created_customers: 1, unmatched: [{ index: 3, reason: 'bad_time' }] };
    const dry = await imp(rows, { dry_run: true });
    expect(dry.status).toBe(200);
    expect(dry.body).toEqual(expected);
    expect(await visitsOf(a.id)).toHaveLength(0);
    expect(await count('SELECT COUNT(*) AS n FROM customers WHERE zalo_user_id = ?', z)).toBe(0);
    expect(await auditCount('visits.import')).toBe(audits);

    expect((await imp(rows, { dry_run: false })).body).toEqual(expected);
    expect(await visitsOf(a.id)).toHaveLength(1);
    expect(await auditCount('visits.import')).toBe(audits + 1);
  });

  it('rejects a malformed body with 422 naming the field', async () => {
    const a = await newCustomer();
    const row = { customer_id: a.id, service_id: GOI, visited_at: past(3) };
    const cases: Array<[unknown, string]> = [
      [[], 'visits'],
      [{ visits: 'x' }, 'visits'],
      [{}, 'visits'],
      [{ visits: [], dry_run: 'yes' }, 'dry_run'],
      [{ visits: [row, 5] }, 'visits[1]'],
      [{ visits: [row, { ...row, external_visit_id: 7 }] }, 'visits[1].external_visit_id'],
      [{ visits: [{ ...row, external_visit_id: 'x'.repeat(101) }] }, 'visits[0].external_visit_id'],
      [{ visits: [{ ...row, technician: 'a\nb' }] }, 'visits[0].technician'],
      [{ visits: [{ ...row, duration_min: 0 }] }, 'visits[0].duration_min'],
      [{ visits: Array.from({ length: MAX_IMPORT_VISITS + 1 }, () => ({})) }, 'visits'],
    ];
    for (const [body, field] of cases) {
      const r = await staff('POST', '/staff/visits/import', body);
      expect(r.status, field).toBe(422);
      expect(r.body.error.code).toBe('validation_failed');
      expect(r.body.error.details.field).toBe(field);
    }
    expect(await visitsOf(a.id)).toHaveLength(0);

    const headers = { authorization: 'Bearer test-staff-token', 'content-type': 'application/json' };
    const notJson = await SELF.fetch('https://bot.test/staff/visits/import', { method: 'POST', headers, body: '{not json' });
    expect(notJson.status).toBe(400);
    const noToken = await SELF.fetch('https://bot.test/staff/visits/import', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ visits: [] }) });
    expect(noToken.status).toBe(401);
  });

  it('stores a service outside the catalog as ext:<slug> and keeps the given name of a catalog service', async () => {
    const a = await newCustomer();
    const r = await imp([
      { customer_id: a.id, service_name: '  Tắm trắng (đặc biệt) #2 ', visited_at: past(4) },
      { customer_id: a.id, service_id: GOI, service_name: 'Gội thảo dược 60 phút', visited_at: past(3) },
      { customer_id: a.id, service_id: 'khong-co-dich-vu', service_name: 'Đắp mặt nạ', visited_at: past(2) },
    ]);
    expect(r.body).toMatchObject({ imported: 3, unmatched: [] });
    expect((await visitsOf(a.id)).map((v) => [v.service_id, v.service_name])).toEqual([
      ['ext:tam-trang-dac-biet-2', 'Tắm trắng (đặc biệt) #2'],
      [GOI, 'Gội thảo dược 60 phút'],
      ['ext:dap-mat-na', 'Đắp mặt nạ'],
    ]);
  });

  it('imports more rows than one batch holds for one new contact', async () => {
    const z = nextZaloId();
    const first = Date.UTC(2023, 0, 1, 3, 0);
    const rows = Array.from({ length: 620 }, (_, i) => ({ zalo_user_id: z, service_id: GOI, visited_at: first + i * 24 * HOUR_MS }));
    const r = await imp(rows);
    expect(r.body).toEqual({ imported: 620, duplicates: 0, created_customers: 1, unmatched: [] });
    const cu = await env.DB.prepare('SELECT id FROM customers WHERE zalo_user_id = ?').bind(z).all<{ id: string }>();
    expect(cu.results).toHaveLength(1);
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', cu.results[0]!.id)).toBe(620);
    expect(await count('SELECT COUNT(DISTINCT id) AS n FROM visits WHERE customer_id = ?', cu.results[0]!.id)).toBe(620);
  });

  it('accepts a time up to one hour after now and no later (library call with a fixed clock)', async () => {
    const a = await newCustomer();
    const r = await importVisits(
      env,
      { dry_run: true, visits: [
        { customer_id: a.id, service_id: GOI, visited_at: NOW + HOUR_MS / 2 },
        { customer_id: a.id, service_id: GOI, visited_at: NOW + 2 * HOUR_MS },
        { customer_id: a.id, service_id: GOI, visited_at: Date.UTC(1999, 11, 31) },
        { customer_id: a.id, service_id: GOI, visited_at: NOW - 0.5 },
      ] },
      'tester',
      NOW,
    );
    expect(r).toEqual({ imported: 2, duplicates: 0, created_customers: 0, unmatched: [{ index: 1, reason: 'bad_time' }, { index: 2, reason: 'bad_time' }] });
  });
});

describe('import helpers', () => {
  it('parseLocalDateTime reads a local date and time of Asia/Ho_Chi_Minh', () => {
    expect(parseLocalDateTime('2024-03-05 14:30')).toBe(LOCAL_MS);
    expect(parseLocalDateTime(' 2024-03-05T14:30:15 ')).toBe(LOCAL_MS + 15_000);
    expect(parseLocalDateTime('2024-03-05 9:05')).toBe(Date.UTC(2024, 2, 5, 9, 5) - TZ_OFFSET_MS);
    expect(parseLocalDateTime('2024-03-05 00:00')).toBe(Date.UTC(2024, 2, 4, 17, 0));
    for (const bad of ['2024-03-05', '2024-02-30 10:00', '2024-13-01 10:00', '2024-03-05 24:00', '2024-03-05 10:60', '05/03/2024 10:00', '']) expect(parseLocalDateTime(bad), bad).toBeNull();
  });

  it('serviceSlug strips marks and keeps at most 60 characters without a trailing dash', () => {
    expect(serviceSlug('Xông hơi thảo dược')).toBe('xong-hoi-thao-duoc');
    expect(serviceSlug('  Đắp   mặt nạ!! ')).toBe('dap-mat-na');
    expect(serviceSlug('!!!')).toBe('');
    const long = serviceSlug(`${'a'.repeat(59)} bcd`);
    expect(long).toBe('a'.repeat(59));
    expect(serviceSlug('b'.repeat(80))).toHaveLength(60);
  });

  it('normalizePhone keeps Vietnamese numbers as 0xxxxxxxxx digits', () => {
    expect(normalizePhone('0907 000 111')).toBe('0907000111');
    expect(normalizePhone('+84 (907) 000-111')).toBe('0907000111');
    expect(normalizePhone('84907000111')).toBe('0907000111');
    expect(normalizePhone('0907.000.111')).toBe('0907000111');
    for (const bad of ['abc', '12345', '0907 000 11a', '', null, undefined, 907000111, '090700011122']) expect(normalizePhone(bad), String(bad)).toBeNull();
  });
});

describe('GET /staff/visits', () => {
  it('lists the visits of a customer newest first with the name of each service', async () => {
    const a = await newCustomer();
    await addVisit(a.id, past(30), GOI, { amount: 200000, technician: 'Hoa' });
    await addVisit(a.id, past(20), 'ext:xong-hoi', { service_name: 'Xông hơi', source: 'import' });
    await addVisit(a.id, past(10), 'ext:khong-ten', { source: 'import' });
    const r = await staff('GET', `/staff/visits?customer_id=${a.id}`);
    expect(r.status).toBe(200);
    expect(r.body.visits.map((v: { service_id: string; name: string }) => [v.service_id, v.name])).toEqual([
      ['ext:khong-ten', 'ext:khong-ten'],
      ['ext:xong-hoi', 'Xông hơi'],
      [GOI, NAMES[GOI]],
    ]);
    expect(r.body.visits[2]).toEqual({
      id: expect.stringMatching(/^vis_/),
      customer_id: a.id,
      service_id: GOI,
      service_name: null,
      name: NAMES[GOI],
      visited_at: past(30),
      duration_min: null,
      amount_vnd: 200000,
      technician: 'Hoa',
      benefit_id: null,
      source: 'staff',
      external_visit_id: null,
      recorded_by: 'tester',
      created_at: past(30),
    });
  });

  it('answers 422 without customer_id and 404 for an unknown or deleted customer', async () => {
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    const none = await staff('GET', '/staff/visits');
    expect(none.status).toBe(422);
    expect(none.body.error.details.field).toBe('customer_id');
    expect((await staff('GET', '/staff/visits?customer_id=cus_missing')).status).toBe(404);
    expect((await staff('GET', `/staff/visits?customer_id=${gone.id}`)).status).toBe(404);
  });
});
