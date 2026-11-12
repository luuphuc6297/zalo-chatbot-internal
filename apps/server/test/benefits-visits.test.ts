// Benefits, POST /staff/visits with the section 14.5 fields, and the phone edit (docs/contracts.md section 14.5).
// All data is synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { DAY_MS, localDate, localMidnight } from '../src/lib/time';
import { createBenefit } from '../src/staff-api/customers';
import { seed, staff } from './core-helpers';
import { CHAN, GOI, NOW, addBenefit, auditCount, benefitRow, count, jobCount, lastAudit, newCustomer, nextPhone, past, visitsOf } from './customers-helpers';

beforeAll(async () => {
  await seed();
});

const field = (r: { body: any }) => r.body.error.details.field;

describe('POST /staff/benefits', () => {
  it('creates a benefit and audits it without the title', async () => {
    const a = await newCustomer();
    const expires = localMidnight(Date.now()) + 30 * DAY_MS;
    const r = await staff('POST', '/staff/benefits', { customer_id: a.id, kind: 'package', title: '  Gói 10 buổi gội đầu ', service_id: GOI, total_count: 10, used_count: 3, expires_at: expires });
    expect(r.status).toBe(200);
    const b = r.body.benefit;
    expect(b).toEqual({
      id: expect.stringMatching(/^ben_/),
      customer_id: a.id,
      kind: 'package',
      title: 'Gói 10 buổi gội đầu',
      service_id: GOI,
      total_count: 10,
      used_count: 3,
      remaining: 7,
      expires_at: expires,
      expires_on: localDate(expires),
      status: 'active',
      recorded_by: 'tester',
      created_at: expect.any(Number),
      updated_at: expect.any(Number),
    });
    expect(await benefitRow(b.id)).toMatchObject({ customer_id: a.id, used_count: 3, status: 'active', recorded_by: 'tester' });
    const audit = await lastAudit('benefit.create');
    expect(audit).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'benefit', entity_id: b.id });
    expect(JSON.parse(audit!.after_json!)).toEqual({ customer_id: a.id, kind: 'package', service_id: GOI, total_count: 10, used_count: 3, expires_at: expires });
    expect(audit!.after_json).not.toMatch(/Gói/);
  });

  it('defaults used_count to 0 and takes a voucher without service and expiry', async () => {
    const a = await newCustomer();
    const r = await staff('POST', '/staff/benefits', { customer_id: a.id, kind: 'voucher', title: 'Voucher sinh nhật', total_count: 1 });
    expect(r.status).toBe(200);
    expect(r.body.benefit).toMatchObject({ kind: 'voucher', service_id: null, total_count: 1, used_count: 0, remaining: 1, expires_at: null, expires_on: null, status: 'active' });
  });

  it('rejects each bad field with 422 naming it, and an unknown customer with 404', async () => {
    const a = await newCustomer();
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    const ok = { customer_id: a.id, kind: 'package', title: 'Gói 5 buổi', total_count: 5 };
    const cases: Array<[unknown, string]> = [
      [[], 'customer_id'],
      [{ ...ok, customer_id: '' }, 'customer_id'],
      [{ ...ok, kind: 'gift' }, 'kind'],
      [{ ...ok, title: '   ' }, 'title'],
      [{ ...ok, title: 'a\nb' }, 'title'],
      [{ ...ok, title: 'x'.repeat(121) }, 'title'],
      [{ ...ok, total_count: 0 }, 'total_count'],
      [{ ...ok, total_count: 1.5 }, 'total_count'],
      [{ ...ok, total_count: 1001 }, 'total_count'],
      [{ ...ok, used_count: 6 }, 'used_count'],
      [{ ...ok, used_count: -1 }, 'used_count'],
      [{ ...ok, expires_at: 'tomorrow' }, 'expires_at'],
      [{ ...ok, expires_at: 0 }, 'expires_at'],
      [{ ...ok, service_id: 'khong-co-dich-vu' }, 'service_id'],
      [{ ...ok, kind: 'gift', title: '' }, 'kind'], // the first bad field is named
    ];
    const before = await count('SELECT COUNT(*) AS n FROM customer_benefits');
    for (const [body, name] of cases) {
      const r = await staff('POST', '/staff/benefits', body);
      expect(r.status, name).toBe(422);
      expect(r.body.error.code).toBe('validation_failed');
      expect(field(r), JSON.stringify(body).slice(0, 80)).toBe(name);
    }
    expect((await staff('POST', '/staff/benefits', { ...ok, customer_id: 'cus_missing' })).status).toBe(404);
    expect((await staff('POST', '/staff/benefits', { ...ok, customer_id: gone.id })).status).toBe(404);
    expect(await count('SELECT COUNT(*) AS n FROM customer_benefits')).toBe(before);
  });
});

describe('GET /staff/benefits', () => {
  it('lists every benefit of the customer, active first and then newest first', async () => {
    const a = await newCustomer();
    const other = await newCustomer();
    const mk = (title: string, now: number) => createBenefit(env, { customer_id: a.id, kind: 'package', title, total_count: 3 }, 'tester', now);
    const b1 = await mk('Gói A', NOW - 3000);
    const b2 = await mk('Gói B', NOW - 2000);
    const b3 = await mk('Gói C', NOW - 1000);
    await createBenefit(env, { customer_id: other.id, kind: 'voucher', title: 'Voucher khác', total_count: 1 }, 'tester', NOW);
    expect((await staff('PATCH', `/staff/benefits/${b3.id}`, { status: 'void' })).status).toBe(200);
    const r = await staff('GET', `/staff/benefits?customer_id=${a.id}`);
    expect(r.status).toBe(200);
    expect(r.body.benefits.map((b: { id: string; status: string }) => [b.id, b.status])).toEqual([
      [b2.id, 'active'],
      [b1.id, 'active'],
      [b3.id, 'void'],
    ]);
    expect(r.body.benefits[0]).toMatchObject({ title: 'Gói B', remaining: 3, expires_on: null });
  });

  it('answers 422 without customer_id and 404 for an unknown or deleted customer', async () => {
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    const none = await staff('GET', '/staff/benefits');
    expect(none.status).toBe(422);
    expect(field(none)).toBe('customer_id');
    expect((await staff('GET', '/staff/benefits?customer_id=cus_missing')).status).toBe(404);
    expect((await staff('GET', `/staff/benefits?customer_id=${gone.id}`)).status).toBe(404);
  });
});

describe('PATCH /staff/benefits/:id', () => {
  it('changes used_count, expires_at, status and title, and audits before and after without the title', async () => {
    const a = await newCustomer();
    const expires = localMidnight(Date.now()) + 10 * DAY_MS;
    const id = await addBenefit(a.id, { title: 'Gói 10 buổi', total: 10, used: 2, expires_at: expires });
    const r = await staff('PATCH', `/staff/benefits/${id}`, { used_count: 5, expires_at: null, title: ' Gói 10 buổi (gia hạn) ' });
    expect(r.status).toBe(200);
    expect(r.body.benefit).toMatchObject({ id, title: 'Gói 10 buổi (gia hạn)', used_count: 5, remaining: 5, expires_at: null, expires_on: null, status: 'active' });
    const audit = await lastAudit('benefit.update');
    expect(audit).toMatchObject({ actor_id: 'tester', entity: 'benefit', entity_id: id });
    expect(JSON.parse(audit!.before_json!)).toEqual({ used_count: 2, expires_at: expires, status: 'active' });
    expect(JSON.parse(audit!.after_json!)).toEqual({ used_count: 5, expires_at: null, status: 'active', title_changed: true });
    expect(`${audit!.before_json}${audit!.after_json}`).not.toMatch(/Gói/);

    const v = await staff('PATCH', `/staff/benefits/${id}`, { status: 'void' });
    expect(v.body.benefit).toMatchObject({ status: 'void', used_count: 5 });
    expect(JSON.parse((await lastAudit('benefit.update'))!.after_json!)).toEqual({ used_count: 5, expires_at: null, status: 'void', title_changed: false });
    expect((await staff('PATCH', `/staff/benefits/${id}`, { status: 'active' })).body.benefit.status).toBe('active');
  });

  it('rejects a bad body with 422 and an unknown benefit with 404', async () => {
    const a = await newCustomer();
    const id = await addBenefit(a.id, { total: 4, used: 1 });
    const audits = await auditCount('benefit.update');
    const cases: Array<[unknown, string]> = [
      [{}, 'body'],
      [[], 'body'],
      [{ total_count: 9 }, 'total_count'],
      [{ used_count: 2, customer_id: 'cus_x' }, 'customer_id'],
      [{ used_count: 5 }, 'used_count'],
      [{ used_count: -1 }, 'used_count'],
      [{ used_count: 1.5 }, 'used_count'],
      [{ status: 'expired' }, 'status'],
      [{ title: '' }, 'title'],
      [{ expires_at: 'x' }, 'expires_at'],
    ];
    for (const [body, name] of cases) {
      const r = await staff('PATCH', `/staff/benefits/${id}`, body);
      expect(r.status, name).toBe(422);
      expect(field(r), JSON.stringify(body)).toBe(name);
    }
    const missing = await staff('PATCH', '/staff/benefits/ben_missing', { used_count: 1 });
    expect(missing.status).toBe(404);
    expect(missing.body.error.code).toBe('not_found');
    expect(await benefitRow(id)).toMatchObject({ used_count: 1, total_count: 4, status: 'active' });
    expect(await auditCount('benefit.update')).toBe(audits);
  });
});

describe('POST /staff/visits with the section 14.5 fields', () => {
  it('keeps the behaviour from before section 14 for a body without the new fields', async () => {
    const a = await newCustomer();
    const r = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(1) });
    expect(r.status).toBe(200);
    expect(r.body.jobs.map((j: { type: string }) => j.type).sort()).toEqual(['check_in', 'thank_you']);
    expect(await visitsOf(a.id)).toEqual([
      expect.objectContaining({ id: r.body.visit_id, service_id: GOI, source: 'staff', service_name: null, duration_min: null, amount_vnd: null, technician: null, benefit_id: null, recorded_by: 'tester' }),
    ]);
    expect(JSON.parse((await lastAudit('visit.record'))!.after_json!)).toEqual({ service_id: GOI });
  });

  it('stores amount, technician, duration and the name of the service, and still creates both jobs', async () => {
    const a = await newCustomer();
    const r = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(1), amount_vnd: 0, technician: ' Mai ', duration_min: 90, service_name: 'Gội thảo dược' });
    expect(r.status).toBe(200);
    expect(r.body.jobs).toHaveLength(2);
    expect(await jobCount(a.id)).toBe(2);
    expect(await visitsOf(a.id)).toEqual([expect.objectContaining({ amount_vnd: 0, technician: 'Mai', duration_min: 90, service_name: 'Gội thảo dược', benefit_id: null, source: 'staff' })]);
  });

  it('rejects bad values of the new fields with 422 naming the field', async () => {
    const a = await newCustomer();
    const ok = { customer_id: a.id, service_id: GOI, visited_at: past(1) };
    const cases: Array<[Record<string, unknown>, string]> = [
      [{ amount_vnd: -1 }, 'amount_vnd'],
      [{ amount_vnd: 1.5 }, 'amount_vnd'],
      [{ amount_vnd: '100000' }, 'amount_vnd'],
      [{ duration_min: 0 }, 'duration_min'],
      [{ duration_min: 1441 }, 'duration_min'],
      [{ technician: 'a\nb' }, 'technician'],
      [{ technician: 'x'.repeat(61) }, 'technician'],
      [{ service_name: 'x'.repeat(121) }, 'service_name'],
      [{ benefit_id: 7 }, 'benefit_id'],
      [{ benefit_id: '' }, 'benefit_id'],
    ];
    for (const [extra, name] of cases) {
      const r = await staff('POST', '/staff/visits', { ...ok, ...extra });
      expect(r.status, name).toBe(422);
      expect(field(r), JSON.stringify(extra)).toBe(name);
    }
    expect(await visitsOf(a.id)).toHaveLength(0);
    expect(await jobCount(a.id)).toBe(0);
  });

  it('uses one count of the benefit per visit and refuses a visit when no use is left', async () => {
    const a = await newCustomer();
    const id = await addBenefit(a.id, { total: 2, used: 0 });
    const first = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(3), benefit_id: id });
    expect(first.status).toBe(200);
    expect((await benefitRow(id))!.used_count).toBe(1);
    expect(JSON.parse((await lastAudit('visit.record'))!.after_json!)).toEqual({ service_id: GOI, benefit_id: id });
    const second = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: CHAN, visited_at: past(2), benefit_id: id, amount_vnd: 0 });
    expect(second.status).toBe(200);
    expect((await benefitRow(id))!.used_count).toBe(2);
    expect((await visitsOf(a.id)).map((v) => v.benefit_id)).toEqual([id, id]);

    const third = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(1), benefit_id: id });
    expect(third.status).toBe(409);
    expect(third.body.error.code).toBe('invalid_state');
    expect((await benefitRow(id))!.used_count).toBe(2);
    expect(await visitsOf(a.id)).toHaveLength(2);
    expect(await jobCount(a.id)).toBe(4);
  });

  it('answers 409 for a benefit of another customer, an unknown benefit and a void benefit', async () => {
    const a = await newCustomer();
    const b = await newCustomer();
    const foreign = await addBenefit(b.id, { total: 5 });
    const voided = await addBenefit(a.id, { total: 5, status: 'void' });
    for (const benefit_id of [foreign, 'ben_missing', voided]) {
      const r = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(1), benefit_id });
      expect(r.status, benefit_id).toBe(409);
      expect(r.body.error.code).toBe('invalid_state');
    }
    expect(await visitsOf(a.id)).toHaveLength(0);
    expect((await benefitRow(foreign))!.used_count).toBe(0);
    expect((await benefitRow(voided))!.used_count).toBe(0);
  });

  it('judges the expiry of a benefit on the local date of the visit', async () => {
    const a = await newCustomer();
    const today = localMidnight(Date.now());
    const id = await addBenefit(a.id, { total: 5, expires_at: today - 2 * DAY_MS + 1000 }); // expired two days ago
    const late = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(1), benefit_id: id });
    expect(late.status).toBe(409);
    const onTheDay = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(2, 20), benefit_id: id });
    expect(onTheDay.status).toBe(200);
    const before = await staff('POST', '/staff/visits', { customer_id: a.id, service_id: GOI, visited_at: past(5), benefit_id: id });
    expect(before.status).toBe(200);
    expect((await benefitRow(id))!.used_count).toBe(2);
  });

  it('a replay with the same external_visit_id returns the first visit and uses no second count', async () => {
    const a = await newCustomer();
    const id = await addBenefit(a.id, { total: 3 });
    const body = { customer_id: a.id, service_id: GOI, visited_at: past(1), benefit_id: id, external_visit_id: 'ext-replay-1' };
    const first = await staff('POST', '/staff/visits', body);
    const again = await staff('POST', '/staff/visits', body);
    expect(first.status).toBe(200);
    expect(again.status).toBe(200);
    expect(again.body).toEqual(first.body);
    expect((await benefitRow(id))!.used_count).toBe(1);
    expect(await visitsOf(a.id)).toHaveLength(1);
  });
});

describe('PATCH /staff/customers/:id', () => {
  it('stores the phone as normalised digits and audits only whether a phone exists', async () => {
    const a = await newCustomer({ display_name: 'Lan' });
    const phone = nextPhone();
    const r = await staff('PATCH', `/staff/customers/${a.id}`, { phone: `+84 ${phone.slice(1, 4)} ${phone.slice(4, 7)} ${phone.slice(7)}` });
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ customer: { id: a.id, channel: 'personal', zalo_user_id: a.zalo, display_name: 'Lan', phone, minor_flag: null, last_user_interaction_at: null } });
    expect(await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first()).toEqual({ phone });
    const audit = await lastAudit('customer.phone_edit');
    expect(audit).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'customer', entity_id: a.id });
    expect(JSON.parse(audit!.before_json!)).toEqual({ has_phone: false });
    expect(JSON.parse(audit!.after_json!)).toEqual({ has_phone: true });
    expect(`${audit!.before_json}${audit!.after_json}`).not.toContain(phone.slice(1));

    const cleared = await staff('PATCH', `/staff/customers/${a.id}`, { phone: null });
    expect(cleared.status).toBe(200);
    expect(cleared.body.customer.phone).toBeNull();
    expect(JSON.parse((await lastAudit('customer.phone_edit'))!.before_json!)).toEqual({ has_phone: true });
    expect(JSON.parse((await lastAudit('customer.phone_edit'))!.after_json!)).toEqual({ has_phone: false });
  });

  it('rejects a bad phone or body with 422 and an unknown or deleted customer with 404', async () => {
    const a = await newCustomer({ phone: '0907999001' });
    const gone = await newCustomer({ deleted_at: 1_700_000_000_001 });
    const cases: Array<[unknown, string]> = [
      [{ phone: 'abc' }, 'phone'],
      [{ phone: '12345' }, 'phone'],
      [{ phone: 907999002 }, 'phone'],
      [{ phone: '' }, 'phone'],
      [{}, 'phone'],
      [[], 'phone'],
      [{ phone: '0907999002', display_name: 'Lan' }, 'display_name'],
    ];
    for (const [body, name] of cases) {
      const r = await staff('PATCH', `/staff/customers/${a.id}`, body);
      expect(r.status, JSON.stringify(body)).toBe(422);
      expect(field(r)).toBe(name);
    }
    expect((await staff('PATCH', '/staff/customers/cus_missing', { phone: '0907999002' })).status).toBe(404);
    expect((await staff('PATCH', `/staff/customers/${gone.id}`, { phone: '0907999002' })).status).toBe(404);
    expect(await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(a.id).first()).toEqual({ phone: '0907999001' });
  });
});
