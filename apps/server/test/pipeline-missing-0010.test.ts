// The draft pipeline on a D1 without migration 0010 (`wrangler dev` reloads the new code before the owner applies
// 0010_rooms_roles_customer.sql). Every hot path keeps working as before section 14: message ingest and the consent
// gate, debounce and enqueue, claim, heartbeat, tools, draft acceptance and auto-send, approve, the bridge queue, the
// staff views, failures and expired leases. A missing table or column means no role, no auto reply switch, no
// summary and rooms off. This file removes what 0010 added in its own D1. Every name, id and text is synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { expireLeases } from '../src/jobs/draft-jobs';
import { runDueFollowups } from '../src/scheduler/followups';
import { claim, draftBody, jobsOf, runner, seed, setFlags, staff } from './core-helpers';
import { GOI, past } from './customers-helpers';
import {
  ask,
  botOutbox,
  bridge,
  consentedThread,
  convOf,
  fireDebounce,
  ingest,
  msgEvent,
  outboxOf,
  personalJob,
  postPersonal,
  sendNext,
  settle,
  thread,
  write,
} from './personal-helpers';

function queriesOf(prefix: string): string[] {
  const m = env.TEST_MIGRATIONS.find((x) => x.name.startsWith(prefix));
  expect(m, prefix).toBeDefined();
  return m!.queries;
}

beforeAll(async () => {
  await seed();
  const oldVisitsDdl = queriesOf('0001_').find((q) => /CREATE TABLE visits\b/.test(q));
  expect(oldVisitsDdl).toBeDefined();
  // back to the shape of 0001-0009
  await env.DB.batch(
    [
      'DROP INDEX IF EXISTS idx_messages_room_pending',
      'ALTER TABLE messages DROP COLUMN room_mirrored_at',
      'ALTER TABLE conversations DROP COLUMN auto_reply',
      'ALTER TABLE conversations DROP COLUMN room_channel_id',
      'ALTER TABLE conversations DROP COLUMN room_synced_at',
      'DROP TABLE contact_roles',
      'DROP TABLE customer_benefits',
      'DROP TABLE visits',
      oldVisitsDdl!,
    ].map((q) => env.DB.prepare(q)),
  );
});

beforeEach(async () => {
  await settle();
  await setFlags({ auto_reply_mode: 'approve_each', rooms_enabled: false, outbound_enabled: true, ai_calls_enabled: true });
});

const tool = (name: string, jobId: string, input: unknown) => runner(`/runner/tools/${name}`, { job_id: jobId, input });
const quoteGoiDau = (jobId: string) =>
  tool('quote_price', jobId, { service_id: GOI, duration_min: 50, start_time_local: '19:00', date_local: 'unknown' });
const GOOD = 'Dạ Gội đầu thư giãn 50 phút lúc 19h là 199.000đ ạ.';
const NEW_SUMMARY_FIELDS = ['auto_reply', 'role', 'role_source'];

describe('without migration 0010', () => {
  it('the schema really lacks what 0010 adds', async () => {
    await expect(env.DB.prepare('SELECT 1 FROM contact_roles').run()).rejects.toThrow(/no such table/);
    await expect(env.DB.prepare('SELECT auto_reply FROM conversations').run()).rejects.toThrow(/no such column/);
    await expect(env.DB.prepare('SELECT room_mirrored_at FROM messages').run()).rejects.toThrow(/no such column/);
  });

  it('a personal contact goes from the consent prompt to a draft that staff approve and the bridge sends', async () => {
    const threadId = thread();
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    await sendNext(threadId);
    expect((await write(threadId, 'Đồng ý')).status).toBe(200);
    await sendNext(threadId);
    const conv = (await convOf(threadId))!;
    expect(conv.bot_state).toBe('bot_active');
    expect(conv).not.toHaveProperty('auto_reply');

    expect((await ingest(threadId, 'gội đầu bao nhiêu tiền ạ')).action).toBe('debounced');
    expect(await fireDebounce(threadId)).toBe(true);
    expect((await jobsOf(conv.id)).map((j) => j.status)).toEqual(['queued']);
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(conv.id);
    expect(c.job.turn_context.conversation_mode).toBe('approve_each');
    expect(c.job.customer_profile).toBeNull();

    const hb = await runner(`/runner/jobs/${c.job.job_id}/heartbeat`);
    expect(hb.status).toBe(200);
    expect(hb.body.cancel).toBe(false);
    const facts = await tool('get_customer_profile', c.job.job_id, {});
    expect(facts.status).toBe(200);
    expect(facts.body).toMatchObject({ is_error: false, result: { found: false, reason: 'no_data' } });
    expect((await quoteGoiDau(c.job.job_id)).body.is_error).toBe(false);

    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.status).toBe(200);
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });

    const list = await staff('GET', '/staff/conversations');
    expect(list.status).toBe(200);
    const item = list.body.items.find((x: { id: string }) => x.id === conv.id);
    expect(item).toMatchObject({ effective_mode: 'approve_each', pending_drafts: 1, needs_attention: true });
    for (const k of NEW_SUMMARY_FIELDS) expect(item).not.toHaveProperty(k);
    const detail = await staff('GET', `/staff/conversations/${conv.id}`);
    expect(detail.status).toBe(200);
    for (const k of NEW_SUMMARY_FIELDS) expect(detail.body.conversation).not.toHaveProperty(k);
    expect(detail.body).not.toHaveProperty('customer_summary');
    expect(detail.body).not.toHaveProperty('room');

    const ok = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
    expect(ok.status).toBe(200);
    const item2 = await sendNext(threadId);
    expect(item2.text).toBe(GOOD);
    expect((await botOutbox(conv.id)).map((x) => x.status)).toEqual(['sent']);
  });

  it('auto-sends under the global auto_allowed as before; the mode endpoint works and the switch answers 409', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const p = await personalJob();
    await quoteGoiDau(p.jobId);
    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'sent', action: 'auto_sent' });
    expect((await sendNext(p.threadId)).text).toBe(GOOD);

    const m = await staff('PUT', `/staff/conversations/${p.cid}/mode`, { mode: 'approve_each' });
    expect(m.status).toBe(200);
    expect(m.body.conversation).toMatchObject({ mode_override: 'approve_each', effective_mode: 'approve_each' });
    expect(m.body.conversation).not.toHaveProperty('auto_reply');

    for (const value of ['on', 'off']) {
      const s = await staff('PUT', `/staff/conversations/${p.cid}/auto-reply`, { auto_reply: value });
      expect(s.status, value).toBe(409);
      expect(s.body.error.code).toBe('invalid_state');
      expect(s.body.error.message).toContain('0010_rooms_roles_customer.sql');
    }
    expect((await convOf(p.threadId))!.mode).toBe('approve_each');
  });

  it('heartbeat, the mode off, a takeover, a failed job and an expired lease behave as before', async () => {
    const a = await personalJob();
    expect((await staff('PUT', `/staff/conversations/${a.cid}/mode`, { mode: 'off' })).status).toBe(200);
    expect((await runner(`/runner/jobs/${a.jobId}/heartbeat`)).body).toMatchObject({ cancel: true, cancel_reason: 'flags_changed' });

    const b = await personalJob();
    const f = await runner(`/runner/jobs/${b.jobId}/fail`, { error_kind: 'timeout', error_message: 'slow' });
    expect(f.status).toBe(200);
    expect(f.body.handoff_id).toMatch(/^hof_/);

    const c = await personalJob();
    await env.DB.prepare('UPDATE jobs SET lease_until = ? WHERE id = ?').bind(Date.now() - 1, c.jobId).run();
    expect(await expireLeases(env, Date.now())).toBe(1);
    expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM handoffs WHERE job_id = ?').bind(c.jobId).first<{ n: number }>())!.n).toBe(1);

    // an expired takeover returns to the bot on the next message
    const t = await consentedThread();
    await env.DB.prepare("UPDATE conversations SET bot_state = 'staff_takeover', takeover_by = 'tester', takeover_until = ? WHERE id = ?").bind(Date.now() - 60_000, t.cid).run();
    expect((await ingest(t.threadId, 'gội đầu bao nhiêu tiền ạ')).action).toBe('debounced');
    expect((await convOf(t.threadId))!.bot_state).toBe('bot_active');
  });

  it('a photo opens the usual handoff, and a staff reject recomputes the staff flag', async () => {
    const p = await personalJob();
    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ để em kiểm tra rồi báo mình ngay ạ.'));
    expect(d.body.action).toBe('queued_for_staff');
    const r = await staff('POST', `/staff/drafts/${d.body.draft_id}/reject`, { reason: 'sai' });
    expect(r.status).toBe(200);
    // the question was answered by the (rejected) draft and nothing else waits: the flag is cleared
    expect((await convOf(p.threadId))!.needs_attention).toBe(0);

    const handoffs = () => env.DB.prepare("SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ? AND reason_code = 'unsupported_message'").bind(p.cid).first<{ n: number }>();
    const photo = msgEvent(p.threadId, { title: '', href: 'https://photo.test/b.jpg', thumb: 'https://photo.test/b_t.jpg' }, { msgType: 'chat.photo' });
    expect((await postPersonal(photo)).status).toBe(200);
    expect((await handoffs())!.n).toBe(1);
    expect((await convOf(p.threadId))!.needs_attention).toBe(1);

    await ask(p.threadId, 'à cho chị hỏi thêm');
    expect((await jobsOf(p.cid)).some((j) => j.status === 'queued')).toBe(true);
  });

  it('rooms are off whatever the flag says: the feed answers enabled false, ack answers 409', async () => {
    const p = await consentedThread();
    await setFlags({ rooms_enabled: true });
    for (const body of [{}, { conversation_id: p.cid }, { conversation_id: p.cid, seed: true }]) {
      const r = await runner('/runner/rooms/feed', body);
      expect(r.status).toBe(200);
      expect(r.body).toEqual({ enabled: false, conversations: [] });
    }
    const msg = await env.DB.prepare('SELECT id FROM messages WHERE conversation_id = ? LIMIT 1').bind(p.cid).first<{ id: string }>();
    const ack = await runner('/runner/rooms/ack', { conversation_id: p.cid, message_ids: [msg!.id], room: { channel_id: 'ch-1' } });
    expect(ack.status).toBe(409);
    expect(ack.body.error.code).toBe('invalid_state');
  });

  it('a visit recorded with the old body schedules its follow-ups, and the scheduler runs them', async () => {
    const p = await consentedThread();
    const v = await staff('POST', '/staff/visits', { customer_id: p.customerId, service_id: GOI, visited_at: past(2) });
    expect(v.status).toBe(200);
    expect(v.body.jobs.map((j: { status: string }) => j.status)).toEqual(['queued', 'queued']);
    const checkIn = v.body.jobs.find((j: { type: string }) => j.type === 'check_in');
    await setFlags({ scheduled_sends_enabled: true });
    const res = await runDueFollowups(env, checkIn.run_at + 60_000);
    expect(Object.values(res).reduce((n, x) => n + x, 0)).toBeGreaterThan(0);
    const job = await env.DB.prepare('SELECT status, last_error FROM jobs WHERE id = ?').bind(checkIn.job_id).first<{ status: string; last_error: string | null }>();
    expect(job!.last_error ?? '').not.toContain('internal_contact');
    expect(job!.status).not.toBe('queued');
    expect((await outboxOf(p.threadId)).length).toBeGreaterThanOrEqual(2);
    await setFlags({ scheduled_sends_enabled: false });
  });

  it('the bridge queue is served as before', async () => {
    const threadId = thread();
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    const c = await bridge('/bridge/outbox/claim');
    expect(c.status).toBe(200);
    expect(c.body.item?.thread_id).toBe(threadId);
  });
});
