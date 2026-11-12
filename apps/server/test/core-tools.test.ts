// server-core: tool endpoints scoped to the job's conversation, quote_price rules, booking + opt-out policies.
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { quotePrice, type QuoteVariant } from '../src/tools/quote';
import { claim, customerWithJob, fireDebounce, jobsOf, runner, say, seed, staff } from './core-helpers';
import { localDate } from '../src/lib/time';

beforeEach(async () => {
  await seed();
});

const tool = (name: string, jobId: string, input: unknown, runnerId = 'mac-1') => runner(`/runner/tools/${name}`, { job_id: jobId, input }, runnerId);

describe('tool scoping', () => {
  it('a job can only act on its own conversation', async () => {
    const a = await customerWithJob('chị muốn gặp nhân viên');
    const b = await customerWithJob('gội đầu bao nhiêu');
    const ca = await claim();
    expect(ca.job.conversation.conversation_id).toBe(a.cid);

    // there is no conversation parameter: smuggling one in is a validation error, nothing is written
    const smuggle = await tool('handoff_to_staff', ca.job.job_id, {
      reason_code: 'customer_requested_human',
      urgency: 'normal',
      summary_for_staff: 'x',
      conversation_id: b.cid,
    });
    expect(smuggle.status).toBe(200);
    expect(smuggle.body.is_error).toBe(false); // handoff always accepted; unknown field ignored for handoff only
    const hb = await env.DB.prepare('SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ?').bind(b.cid).first<{ n: number }>();
    expect(hb!.n).toBe(0);
    const states = await env.DB.prepare('SELECT id, bot_state FROM conversations WHERE id IN (?, ?)').bind(a.cid, b.cid).all<{ id: string; bot_state: string }>();
    expect(Object.fromEntries(states.results.map((r) => [r.id, r.bot_state]))).toEqual({ [a.cid]: 'handoff_requested', [b.cid]: 'bot_active' });

    const bad = await tool('quote_price', ca.job.job_id, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '19:00', date_local: 'unknown', conversation_id: b.cid });
    expect(bad.body).toMatchObject({ is_error: true, result: { error: 'validation_failed', field: 'conversation_id' } });

    // another runner cannot use this job; an unknown tool is 404
    expect((await tool('search_services', ca.job.job_id, { query: '', group: 'hair', include_prices: true }, 'mac-2')).body.error.code).toBe('lease_not_owned');
    expect((await tool('drop_tables', ca.job.job_id, {})).body.error.code).toBe('unknown_tool');

    const calls = await env.DB.prepare('SELECT DISTINCT conversation_id FROM tool_calls').all<{ conversation_id: string }>();
    expect(calls.results.map((r) => r.conversation_id)).toEqual([a.cid]);
  });

  it('write tools are idempotent per job and handoff stops further jobs', async () => {
    const a = await customerWithJob('đang bầu 4 tháng làm gội đầu được không');
    const c = await claim();
    const input = { reason_code: 'pregnancy', urgency: 'normal', summary_for_staff: 'Khách nói "đang bầu 4 tháng".' };
    const h1 = await tool('handoff_to_staff', c.job.job_id, input);
    const h2 = await tool('handoff_to_staff', c.job.job_id, input);
    expect(h1.body.replayed).toBe(false);
    expect(h2.body).toMatchObject({ replayed: true, tool_call_id: h1.body.tool_call_id, result: { status: 'accepted', bot_state: 'handoff_requested' } });
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ?').bind(a.cid).first<{ n: number }>();
    expect(n!.n).toBe(1);
    // the job that called handoff is not cancelled by heartbeat; its draft is kept for staff, never auto-sent
    expect((await runner(`/runner/jobs/${c.job.job_id}/heartbeat`)).body.cancel).toBe(false);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, {
      text: 'Dạ em đã chuyển cho nhân viên ạ.', session_id: 's1', account_label: null, model: 'm', effort: 'low',
      usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
      cost_usd_equiv: 0, duration_ms: 1, num_turns: 1, error_kind: null,
    });
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
    await say(a.userId, 'sao rồi em');
    await fireDebounce(a.userId);
    expect((await jobsOf(a.cid)).filter((j) => j.status === 'queued')).toHaveLength(0);
  });

  it('search_services and get_service_details read the job catalog without unapproved fields', async () => {
    await customerWithJob();
    const c = await claim();
    const s = await tool('search_services', c.job.job_id, { query: '', group: 'hair', include_prices: true });
    expect(s.body.result.services.map((x: { service_id: string }) => x.service_id).sort()).toEqual(['cham-soc-nan-toc', 'detox-da-dau', 'goi-dau-thu-gian']);
    const goi = s.body.result.services.find((x: { service_id: string }) => x.service_id === 'goi-dau-thu-gian');
    expect(goi.variants.map((v: { price_text: string }) => v.price_text)).toEqual(['199.000đ', '229.000đ']);
    const fuzzy = await tool('search_services', c.job.job_id, { query: 'goi dau', group: 'any', include_prices: false });
    expect(fuzzy.body.result.services[0].service_id).toBe('goi-dau-thu-gian');
    expect(fuzzy.body.result.services[0].variants[0].price_text).toBeUndefined();
    const det = await tool('get_service_details', c.job.job_id, { service_id: 'tieu-u-thong-kinh-nguc' });
    expect(JSON.stringify(det.body.result)).not.toContain('flagged_claims');
    expect(det.body.result.who_should_avoid_or_consult).toEqual({ status: 'unapproved' });
  });
});

describe('quote_price rules', () => {
  const body: QuoteVariant[] = [
    { duration_min: 60, time_window: '09:00-20:30', price_vnd: 429000 },
    { duration_min: 75, time_window: '09:00-20:30', price_vnd: 499000 },
    { duration_min: 60, time_window: 'after_20:30', price_vnd: 499000 },
    { duration_min: 75, time_window: 'after_20:30', price_vnd: 569000 },
  ];
  const q = (duration_min: number, start_time_local: string, v = body) =>
    quotePrice({ service_id: 'massage-body-thu-gian', duration_min, start_time_local, date_local: 'unknown' }, v, 'cv_t');

  it('day, night, exactly 20:30 and crossing 20:30', () => {
    expect(q(60, '19:00')).toMatchObject({ status: 'ok', price_text: '429.000đ', time_window: '09:00-20:30' });
    expect(q(60, '19:30')).toMatchObject({ status: 'ok', price_text: '429.000đ' }); // ends exactly 20:30
    expect(q(60, '21:00')).toMatchObject({ status: 'ok', price_text: '499.000đ', hours_status: 'unconfirmed' });
    const at = q(60, '20:30');
    expect(at).toMatchObject({ status: 'ambiguous', rule_status: 'unconfirmed', reason: 'starts_exactly_at_20:30' });
    expect((at.candidates as Array<{ price_text: string }>).map((x) => x.price_text)).toEqual(['429.000đ', '499.000đ']);
    expect(q(60, '20:00')).toMatchObject({ status: 'ambiguous', reason: 'crosses_20:30' });
    expect(q(75, '20:29')).toMatchObject({ status: 'ambiguous', reason: 'crosses_20:30' });
    expect(q(60, '08:30')).toMatchObject({ status: 'outside_known_hours' });
    expect(q(60, 'unknown')).toMatchObject({ status: 'needs_time' });
    expect(q(90, '19:00')).toMatchObject({ status: 'invalid_duration', valid_durations: [60, 75] });
    expect(q(0, '19:00')).toMatchObject({ status: 'all_durations', valid_durations: [60, 75] });
  });

  it('foot massage has one window 09:00-24:00 and single-price services ignore time', () => {
    const foot: QuoteVariant[] = [
      { duration_min: 30, time_window: '09:00-24:00', price_vnd: 199000 },
      { duration_min: 45, time_window: '09:00-24:00', price_vnd: 250000 },
    ];
    expect(q(45, '22:00', foot)).toMatchObject({ status: 'ok', price_text: '250.000đ', time_window: '09:00-24:00' });
    expect(q(30, '20:30', foot)).toMatchObject({ status: 'ok', price_text: '199.000đ' });
    expect(q(45, '23:30', foot)).toMatchObject({ status: 'outside_known_hours' });
    const single: QuoteVariant[] = [{ duration_min: 70, time_window: null, price_vnd: 349000 }];
    expect(q(0, '21:00', single)).toMatchObject({ status: 'ok', duration_min: 70, price_text: '349.000đ', hours_status: 'unconfirmed' });
    expect(q(70, '15:00', single)).toMatchObject({ status: 'ok', price_text: '349.000đ' });
  });

  it('through the endpoint, against the seeded catalog', async () => {
    await customerWithJob();
    const c = await claim();
    const r = await tool('quote_price', c.job.job_id, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '20:30', date_local: '2026-11-08' });
    expect(r.body.result).toMatchObject({ status: 'ambiguous', catalog_version_id: c.job.conversation.catalog_version });
    const badTime = await tool('quote_price', c.job.job_id, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '8h toi', date_local: 'unknown' });
    expect(badTime.body).toMatchObject({ is_error: true, result: { field: 'start_time_local' } });
  });
});

describe('create_booking_request and record_contact_preference', () => {
  const booking = (over: Record<string, unknown> = {}) => ({
    service_ids: ['goi-dau-thu-gian'],
    duration_min: 50,
    preferred_date_local: localDate(Date.now() + 86_400_000),
    preferred_time_window: '19:00',
    party_size: 2,
    customer_name: 'Lan',
    contact_method: 'zalo_chat_only',
    phone: '',
    notes_for_staff: '',
    price_quoted_text: '199.000đ',
    ...over,
  });

  it('validates, rejects phones the customer never typed, stores status new and dedupes', async () => {
    const a = await customerWithJob('đặt gội đầu mai 7h tối 2 người, sđt 0901 234 567');
    const c = await claim();
    const wrongPhone = await tool('create_booking_request', c.job.job_id, booking({ contact_method: 'phone_shared_with_consent', phone: '0912345678' }));
    expect(wrongPhone.body.result).toMatchObject({ error: 'phone_not_from_customer' });
    expect((await tool('create_booking_request', c.job.job_id, booking({ party_size: 7 }))).body.result.error).toBe('large_group');
    expect((await tool('create_booking_request', c.job.job_id, booking({ preferred_date_local: '2020-01-01' }))).body.result.error).toBe('date_in_past');
    expect((await tool('create_booking_request', c.job.job_id, booking({ service_ids: ['khong-co'] }))).body.result.error).toBe('unknown_service');
    const ok = await tool('create_booking_request', c.job.job_id, booking({ contact_method: 'phone_shared_with_consent', phone: '0901 234 567' }));
    expect(ok.body.result).toMatchObject({ status: 'created', staff_confirmation: 'pending' });
    const same = await tool('create_booking_request', c.job.job_id, booking({ contact_method: 'phone_shared_with_consent', phone: '0901 234 567' }));
    expect(same.body.replayed).toBe(true);
    const row = await env.DB.prepare('SELECT status, phone, conversation_id FROM booking_requests').first();
    expect(row).toMatchObject({ status: 'new', phone: '0901 234 567', conversation_id: a.cid });
    const list = await staff('GET', '/staff/booking-requests');
    expect(list.body.items).toHaveLength(1);
  });

  it('opt_out applies immediately and cancels scheduled follow-ups of that type', async () => {
    const a = await customerWithJob('đừng nhắn hỏi thăm nữa nha');
    const cust = await env.DB.prepare('SELECT customer_id FROM conversations WHERE id = ?').bind(a.cid).first<{ customer_id: string }>();
    const visit = await staff('POST', '/staff/visits', { customer_id: cust!.customer_id, service_id: 'goi-dau-thu-gian', visited_at: Date.now() - 3_600_000 });
    expect(visit.status).toBe(200);
    expect(visit.body.jobs.map((j: { status: string }) => j.status)).toEqual(['queued', 'queued']);
    const c = await claim();
    const r = await tool('record_contact_preference', c.job.job_id, { preference_type: 'followup_care', action: 'opt_out', customer_words: 'đừng nhắn hỏi thăm nữa nha' });
    expect(r.body.result).toMatchObject({ status: 'recorded', applied: 'immediately' });
    const jobs = await env.DB.prepare("SELECT status FROM jobs WHERE customer_id = ? AND type IN ('thank_you','check_in')").bind(cust!.customer_id).all<{ status: string }>();
    expect(jobs.results.map((j) => j.status)).toEqual(['cancelled', 'cancelled']);
    const consent = await env.DB.prepare("SELECT status FROM consents WHERE customer_id = ? AND purpose = 'followup_care'").bind(cust!.customer_id).first<{ status: string }>();
    expect(consent!.status).toBe('withdrawn');
  });
});
