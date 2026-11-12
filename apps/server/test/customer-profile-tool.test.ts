// The read tool get_customer_profile (docs/contracts.md section 14.6) through POST /runner/tools/:name with a leased
// job, the customer summary of the staff detail, and the phone that create_booking_request copies into an empty
// customers.phone (section 14.5). The model view never carries a phone number nor names a sensitive service.
// Every name, phone number, id and text is synthetic.
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { localDate } from '../src/lib/time';
import { claim, draftBody, runner, seed, staff } from './core-helpers';
import { addBenefit, addProfile, addVisit, catalog, CHAN, count, GOI, HEALTH, past, SENS } from './customers-helpers';
import { ask, personalJob, settle } from './personal-helpers';

let names: Record<string, string> = {};

beforeEach(async () => {
  await seed();
  await settle();
  names = (await catalog()).names;
});

const tool = (name: string, jobId: string, input: unknown = {}) => runner(`/runner/tools/${name}`, { job_id: jobId, input });
const PHONE = '0907555123';

const profileService = (serviceId: string, group: string, sensitive: boolean) => ({
  key: serviceId,
  service_id: serviceId,
  name: names[serviceId],
  group,
  sensitive,
  status: 'mentioned',
  mention_count: 2,
  last_mentioned_at: null,
  used_signal_count: 0,
  last_used_signal_at: null,
});

/** A consented personal contact with a profile, a stored phone, visits (two of them sensitive) and two benefits. */
async function regularWithJob() {
  const p = await personalJob('mai chị qua gội đầu được không');
  await addProfile(p.zalo, {
    relationship: 'customer',
    address_term: 'chị',
    name_to_use: 'Lan',
    address_confidence: 'high',
    services: [profileService(SENS, 'women', true), profileService(GOI, 'hair', false)],
  });
  await env.DB.prepare('UPDATE customers SET phone = ? WHERE id = ?').bind(PHONE, p.customerId).run();
  await addVisit(p.customerId, past(60), HEALTH, { amount: 200_000 });
  await addVisit(p.customerId, past(30), GOI, { amount: 450_000, technician: 'Hoa' });
  await addVisit(p.customerId, past(10, 14), CHAN, { amount: 450_000, technician: 'Mai' });
  await addVisit(p.customerId, past(10, 15), SENS, { amount: 300_000 });
  await addBenefit(p.customerId, { title: 'Gói 10 buổi gội đầu', service_id: GOI, total: 10, used: 4 });
  await addBenefit(p.customerId, { title: 'Gói 5 buổi chăm sóc', service_id: SENS, total: 5, used: 1 });
  return p;
}

describe('get_customer_profile', () => {
  it('answers the facts of the job customer: no phone number, no sensitive service, amounts for judgement only', async () => {
    const p = await regularWithJob();
    const r = await tool('get_customer_profile', p.jobId);
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ is_error: false, replayed: false });
    const facts = r.body.result;
    expect(facts).toMatchObject({
      found: true,
      role: 'customer',
      address_term: 'chị',
      name_to_use: 'Lan',
      has_phone: true,
      status: 'returning',
      visits_total: 3,
      last_visit: { date: localDate(past(10)), time: '15:00', services: [names[CHAN]], other_services: 1, technician: 'Mai' },
      days_since_last_visit: 10,
      usual_gap_days: 25,
      gap_basis: 'own',
      absent_after_days: 50,
      window: { visits: 3, spend_vnd: 1_400_000, avg_spend_vnd: 466_667, usual_services: [{ name: names[GOI], count: 1 }, { name: names[CHAN], count: 1 }], other_services: 2 },
      lifetime: { spend_vnd: 1_400_000, spend_visits: 3 },
      services_mentioned: [names[GOI]],
    });
    expect(facts.unused_benefits).toEqual([
      { kind: 'package', title: 'Gói 10 buổi gội đầu', remaining: 6, expires_on: null },
      { kind: 'package', title: 'Gói dịch vụ', remaining: 4, expires_on: null },
    ]);
    const json = JSON.stringify(r.body);
    expect(json).not.toContain(PHONE);
    expect(json).not.toContain('555123');
    for (const sensitive of [SENS, HEALTH]) {
      expect(json).not.toContain(sensitive);
      expect(json).not.toContain(names[sensitive]);
    }
    expect(json).not.toContain('chăm sóc');
    expect(json).not.toContain('Chị Lan'); // the Zalo display name stays on the server

    // a read tool: stored in tool_calls without an idempotency key, and a second call runs again
    const row = await env.DB.prepare('SELECT tool_name, is_error, idempotency_key, conversation_id FROM tool_calls WHERE id = ?').bind(r.body.tool_call_id).first();
    expect(row).toEqual({ tool_name: 'get_customer_profile', is_error: 0, idempotency_key: null, conversation_id: p.cid });
    const again = await tool('get_customer_profile', p.jobId);
    expect(again.body.replayed).toBe(false);
    expect(again.body.tool_call_id).not.toBe(r.body.tool_call_id);
  });

  it('the amounts it returns are not prices: a draft that states the spend is blocked by the checker', async () => {
    const p = await regularWithJob();
    expect((await tool('get_customer_profile', p.jobId)).body.result.window.spend_vnd).toBe(1_400_000);
    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ chị đã chi 1.400.000đ ở tiệm mình rồi ạ.'));
    expect(d.status).toBe(200);
    expect(d.body.status).toBe('blocked');
    expect(d.body.checker.issues.map((i: { rule: string }) => i.rule)).toContain('price');
  });

  it('takes no input: a customer id, or any other field, is refused and nothing else is read', async () => {
    const p = await regularWithJob();
    const other = await personalJob('cho chị hỏi giá massage');
    for (const input of [{ customer_id: other.customerId }, { conversation_id: other.cid }, { ticket: 'tk_00' }]) {
      const r = await tool('get_customer_profile', p.jobId, input);
      expect(r.status).toBe(200);
      expect(r.body.is_error).toBe(true);
      expect(r.body.result).toMatchObject({ error: 'validation_failed', detail: 'unknown field' });
    }
    // the job of the other contact reads the other contact only
    const theirs = await tool('get_customer_profile', other.jobId);
    expect(theirs.body.result).toMatchObject({ found: true, has_phone: false, status: 'first_inquiry', visits_total: 0, last_visit: null, unused_benefits: [] });
  });

  it('a contact without any data is a first inquiry; a deleted customer has no data', async () => {
    const p = await personalJob();
    const r = await tool('get_customer_profile', p.jobId);
    expect(r.body.is_error).toBe(false);
    expect(r.body.result).toEqual({
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

    await env.DB.prepare('UPDATE customers SET deleted_at = ? WHERE id = ?').bind(Date.now(), p.customerId).run();
    expect((await tool('get_customer_profile', p.jobId)).body.result).toEqual({ found: false, reason: 'no_data' });
  });

  it('a family contact without a role has no data for the model, as in section 13', async () => {
    const p = await personalJob();
    await addProfile(p.zalo, { relationship: 'family', address_term: 'chị', name_to_use: 'Lan', address_confidence: 'high' });
    await addVisit(p.customerId, past(5), GOI, { amount: 450_000 });
    expect((await tool('get_customer_profile', p.jobId)).body.result).toEqual({ found: false, reason: 'no_data' });
  });

  it('an internal contact answers found false: the role set while the job runs, and a staff relationship without a role', async () => {
    const a = await regularWithJob();
    expect((await staff('PUT', `/staff/roles/${encodeURIComponent(a.zalo)}`, { role: 'manager' })).status).toBe(200);
    const r = await tool('get_customer_profile', a.jobId);
    expect(r.body).toMatchObject({ is_error: false, result: { found: false, reason: 'internal_contact' } });
    expect(JSON.stringify(r.body)).not.toContain('Lan');

    const b = await personalJob();
    await addProfile(b.zalo, { relationship: 'staff' });
    expect((await tool('get_customer_profile', b.jobId)).body.result).toEqual({ found: false, reason: 'internal_contact' });
  });

  it('needs a job leased by this runner, like every tool', async () => {
    const p = await regularWithJob();
    const foreign = await runner(`/runner/tools/get_customer_profile`, { job_id: p.jobId, input: {} }, 'mac-2');
    expect(foreign.status).toBe(409);
    expect(foreign.body.error.code).toBe('lease_not_owned');
    expect((await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ mai mình qua lúc nào cũng được ạ.'))).status).toBe(200);
    const done = await tool('get_customer_profile', p.jobId);
    expect(done.status).toBe(409);
    expect(done.body.error.code).toBe('job_not_leased');
  });

  it('is the ninth tool of the prompt, with the schema of design/tools-schema.json', async () => {
    const prompt = await runner('/runner/prompt', undefined, 'mac-1', 'GET');
    expect(prompt.status).toBe(200);
    expect(prompt.body.tools).toHaveLength(9);
    expect(prompt.body.tools[8]).toEqual({
      name: 'get_customer_profile',
      description:
        'Đọc hồ sơ của khách trong cuộc trò chuyện hiện tại: cách xưng hô, trạng thái khách, lần đến gần nhất, nhịp quay lại, dịch vụ thường dùng, mức chi và quyền lợi chưa dùng. Không cần tham số. Số tiền chỉ để cân nhắc cách tư vấn, không được nêu với khách.',
      strict: true,
      input_schema: { type: 'object', properties: {}, required: [], additionalProperties: false },
    });
  });
});

describe('customer summary in the staff detail', () => {
  it('carries the phone, the status and the benefits for staff; the list does not carry it', async () => {
    const p = await regularWithJob();
    const d = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(d.status).toBe(200);
    expect(d.body.customer_summary).toMatchObject({
      role: 'customer',
      role_source: 'profile',
      name: 'Lan',
      address_term: 'chị',
      phone: PHONE,
      status: 'returning',
      visits_total: 3,
      lifetime_spend_vnd: 1_400_000,
    });
    expect(d.body.customer_summary.benefits.map((b: { title: string }) => b.title)).toEqual(['Gói 10 buổi gội đầu', 'Gói 5 buổi chăm sóc']);
    expect(d.body).not.toHaveProperty('room');
    const list = await staff('GET', '/staff/conversations');
    const item = list.body.items.find((x: { id: string }) => x.id === p.cid);
    expect(item).toBeDefined();
    expect(item).not.toHaveProperty('customer_summary');
  });
});

describe('create_booking_request copies the phone into an empty customers.phone', () => {
  const booking = (over: Record<string, unknown> = {}) => ({
    service_ids: [GOI],
    duration_min: 50,
    preferred_date_local: localDate(Date.now() + 86_400_000),
    preferred_time_window: '19:00',
    party_size: 1,
    customer_name: 'Lan',
    contact_method: 'phone_shared_with_consent',
    phone: '0901 234 567',
    notes_for_staff: '',
    price_quoted_text: '',
    ...over,
  });
  const phoneOf = async (customerId: string) => (await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(customerId).first<{ phone: string | null }>())!.phone;

  it('stores the number the customer typed, normalised, when the customer has none', async () => {
    const p = await personalJob('mai 7h tối chị gội đầu, sđt chị 0901 234 567 nhé');
    const r = await tool('create_booking_request', p.jobId, booking());
    expect(r.body.result).toMatchObject({ status: 'created' });
    expect(JSON.stringify(r.body)).not.toContain('234');
    expect(await phoneOf(p.customerId)).toBe('0901234567');
    const d = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(d.body.conversation.customer.phone).toBe('0901234567');
  });

  it('never overwrites a stored number, copies nothing for a chat-only booking, and stores a +84 number as 0...', async () => {
    const a = await personalJob('mai 7h tối chị gội đầu, sđt chị 0901 234 567 nhé');
    await env.DB.prepare('UPDATE customers SET phone = ? WHERE id = ?').bind('0907000999', a.customerId).run();
    expect((await tool('create_booking_request', a.jobId, booking())).body.result.status).toBe('created');
    expect(await phoneOf(a.customerId)).toBe('0907000999');

    const b = await personalJob('mai 7h tối chị gội đầu nhé');
    expect((await tool('create_booking_request', b.jobId, booking({ contact_method: 'zalo_chat_only', phone: '' }))).body.result.status).toBe('created');
    expect(await phoneOf(b.customerId)).toBeNull();

    const c = await personalJob('mai 7h tối chị gội đầu, số chị +84 901 234 568');
    expect((await tool('create_booking_request', c.jobId, booking({ phone: '+84 901 234 568' }))).body.result.status).toBe('created');
    expect(await phoneOf(c.customerId)).toBe('0901234568');
    const bookingPhone = await env.DB.prepare('SELECT phone FROM booking_requests WHERE customer_id = ?').bind(c.customerId).first<{ phone: string }>();
    expect(bookingPhone!.phone).toBe('+84 901 234 568'); // the request keeps what the customer typed
    expect(await count('SELECT COUNT(*) AS n FROM booking_requests WHERE customer_id IN (?,?,?)', a.customerId, b.customerId, c.customerId)).toBe(3);
  });
});

describe('a new question after the tool call', () => {
  it('the next job of the same customer reads the same facts', async () => {
    const p = await regularWithJob();
    expect((await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ mai chị qua lúc nào cũng được ạ.'))).body.action).toBe('queued_for_staff');
    await ask(p.threadId, 'à mà chị muốn đổi sang massage chân');
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(p.cid);
    expect((await tool('get_customer_profile', c.job.job_id)).body.result).toMatchObject({ found: true, visits_total: 3, has_phone: true });
  });
});
