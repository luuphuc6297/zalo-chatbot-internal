// server-core: consent gate, debounce + per-conversation lock, lease expiry, superseded drafts, fail, heartbeat.
import { env, runDurableObjectAlarm, runInDurableObject } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { expireLeases, sweepRunnerHealth } from '../src/jobs/draft-jobs';
import {
  claim,
  consentedCustomer,
  conversationIdOf,
  customerWithJob,
  draftBody,
  fireDebounce,
  jobsOf,
  runner,
  say,
  seed,
  setFlags,
  staff,
  stubFor,
  textEvent,
  uniq,
} from './core-helpers';

beforeEach(async () => {
  await seed();
});

describe('consent gate', () => {
  it('first contact gets the fixed consent prompt with buttons; the model is not called before consent', async () => {
    const userId = uniq('u');
    const r = await say(userId, 'gội đầu bao nhiêu tiền ạ');
    expect(r.action).toBe('consent_prompt_sent');
    const cid = await conversationIdOf(userId);
    const conv = await env.DB.prepare('SELECT bot_state FROM conversations WHERE id = ?').bind(cid).first<{ bot_state: string }>();
    expect(conv!.bot_state).toBe('awaiting_consent');
    const box = await env.DB.prepare("SELECT kind, payload_json FROM outbox WHERE conversation_id = ? AND kind = 'cs_buttons'").bind(cid).first<{ payload_json: string }>();
    expect(box!.payload_json).toContain('#dong_y_tro_ly_ai');
    expect(box!.payload_json).toContain('#gap_nhan_vien');
    // "ok" typed by hand is not consent; no job either way
    expect((await say(userId, 'ok')).action).toBe('stored');
    expect(await jobsOf(cid)).toHaveLength(0);
  });

  it('agree button activates the bot; messages before consent never reach the runner', async () => {
    const { userId, cid } = await consentedCustomer();
    await say(userId, 'massage chân 45 phút giá sao');
    await fireDebounce(userId);
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(cid);
    expect(c.job.new_customer_messages.map((m: { text: string }) => m.text)).toEqual(['massage chân 45 phút giá sao']);
    expect(c.job.history).toEqual([]);
    expect(c.job.turn_context_text).toContain('consent: ai_assistant=granted(');
  });

  it('"Gặp nhân viên" button puts the conversation in staff_only with a handoff', async () => {
    const userId = uniq('u');
    await say(userId, 'alo');
    expect((await say(userId, '#gap_nhan_vien')).action).toBe('consent_recorded');
    const cid = await conversationIdOf(userId);
    const conv = await env.DB.prepare('SELECT bot_state FROM conversations WHERE id = ?').bind(cid).first<{ bot_state: string }>();
    expect(conv!.bot_state).toBe('staff_only');
    const h = await env.DB.prepare('SELECT reason_code FROM handoffs WHERE conversation_id = ?').bind(cid).first<{ reason_code: string }>();
    expect(h!.reason_code).toBe('customer_declined_ai');
    await say(userId, 'cho hỏi giá');
    expect(await fireDebounce(userId)).toBe(false); // no alarm: never debounced for the model
    expect(await jobsOf(cid)).toHaveLength(0);
  });
});

describe('debounce and per-conversation lock', () => {
  it('messages inside the debounce window produce one job; the alarm before the window ends does nothing', async () => {
    const { userId, cid } = await consentedCustomer();
    await say(userId, 'cho em hỏi');
    await say(userId, 'gội đầu bao nhiêu');
    // alarm fired early (debounce_until still in the future) re-arms instead of enqueueing
    await runDurableObjectAlarm(stubFor(userId));
    expect(await jobsOf(cid)).toHaveLength(0);
    await fireDebounce(userId);
    const jobs = await jobsOf(cid);
    expect(jobs).toHaveLength(1);
    expect(jobs[0]!.status).toBe('queued');
    const c = await claim();
    expect(c.job.new_customer_messages).toHaveLength(2);
  });

  it('only one draft job per conversation: a message during a leased job marks it stale instead of adding a job', async () => {
    const { userId, cid } = await customerWithJob();
    const c = await claim();
    expect(c.job).not.toBeNull();
    await say(userId, 'à mà 9h tối nha');
    await fireDebounce(userId);
    const jobs = await jobsOf(cid);
    expect(jobs).toHaveLength(1);
    expect(jobs[0]!.stale).toBe(1);
    // another runner cannot take a second job for the same conversation
    const other = await runner('/runner/jobs/claim', {}, 'mac-2');
    expect(other.body.job).toBeNull();
    const hb = await runner(`/runner/jobs/${c.job.job_id}/heartbeat`);
    expect(hb.body).toMatchObject({ stale: true, cancel: false });
  });

  it('flags and states skip the job and route the conversation to staff', async () => {
    await setFlags({ ai_calls_enabled: false });
    const { userId, cid } = await consentedCustomer();
    await say(userId, 'gội đầu bao nhiêu');
    await fireDebounce(userId);
    expect(await jobsOf(cid)).toHaveLength(0);
    const conv = await env.DB.prepare('SELECT needs_attention FROM conversations WHERE id = ?').bind(cid).first<{ needs_attention: number }>();
    expect(conv!.needs_attention).toBe(1);
    expect((await runner('/runner/jobs/claim')).body).toMatchObject({ job: null, reason: 'ai_calls_disabled' });

    await setFlags({ ai_calls_enabled: true, ai_engine: 'api_key' });
    await say(userId, 'alo');
    await fireDebounce(userId);
    expect(await jobsOf(cid)).toHaveLength(0);
    const h = await env.DB.prepare("SELECT summary_for_staff FROM handoffs WHERE conversation_id = ? AND reason_code = 'ai_unavailable'").bind(cid).first<{ summary_for_staff: string }>();
    expect(h!.summary_for_staff).toBe('api_key engine not configured');

    await setFlags({ ai_engine: 'subscription' });
    await staff('PUT', `/staff/conversations/${cid}/mode`, { mode: 'off' });
    await say(userId, 'alo 2');
    await fireDebounce(userId);
    expect(await jobsOf(cid)).toHaveLength(0);
  });

  it('minor flag blocks the conversation and never calls the model', async () => {
    const { userId, cid } = await consentedCustomer();
    await env.DB.prepare('UPDATE customers SET minor_flag = 1 WHERE zalo_user_id = ?').bind(userId).run();
    await say(userId, 'gội đầu bao nhiêu');
    await fireDebounce(userId);
    expect(await jobsOf(cid)).toHaveLength(0);
    const conv = await env.DB.prepare('SELECT bot_state FROM conversations WHERE id = ?').bind(cid).first<{ bot_state: string }>();
    expect(conv!.bot_state).toBe('blocked');
  });
});

describe('lease, supersede, fail', () => {
  it('a draft after lease expiry is rejected (409) but its session and usage are recorded; cron fails the job with a handoff', async () => {
    const { userId, cid } = await customerWithJob();
    const c = await claim();
    await env.DB.prepare('UPDATE jobs SET lease_until = ? WHERE id = ?').bind(Date.now() - 1, c.job.job_id).run();
    const late = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em chào anh/chị ạ.', 'sess-late'));
    expect(late.status).toBe(409);
    expect(late.body.error.code).toBe('lease_expired');
    const conv = await env.DB.prepare('SELECT session_id, total_output_tokens FROM conversations WHERE id = ?').bind(cid).first<{ session_id: string; total_output_tokens: number }>();
    expect(conv).toMatchObject({ session_id: 'sess-late', total_output_tokens: 20 });
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM drafts WHERE job_id = ?').bind(c.job.job_id).first<{ n: number }>()).toEqual({ n: 0 });

    expect(await expireLeases(env, Date.now())).toBe(1);
    const job = await env.DB.prepare('SELECT status FROM jobs WHERE id = ?').bind(c.job.job_id).first<{ status: string }>();
    expect(job!.status).toBe('failed');
    const h = await env.DB.prepare("SELECT source FROM handoffs WHERE job_id = ? AND reason_code = 'ai_unavailable'").bind(c.job.job_id).first<{ source: string }>();
    expect(h!.source).toBe('runner_failure');
    // the next customer message gets a fresh job (requeue on the next turn, never an automatic retry)
    await say(userId, 'alo shop');
    await fireDebounce(userId);
    const next = await claim();
    expect(next.job.job_id).not.toBe(c.job.job_id);
    expect(next.job.new_customer_messages.map((m: { text: string }) => m.text)).toEqual(['gội đầu bao nhiêu tiền ạ', 'alo shop']);
  });

  it('a draft superseded by newer customer messages is dropped and a new job covers all unanswered messages', async () => {
    const { userId, cid } = await customerWithJob('gội đầu bao nhiêu');
    const c = await claim();
    await say(userId, 'mà 9h tối thì sao');
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ gội đầu thư giãn 50 phút ạ.'));
    expect(d.status).toBe(200);
    expect(d.body).toMatchObject({ status: 'superseded', action: 'dropped' });
    await fireDebounce(userId);
    const jobs = await jobsOf(cid);
    expect(jobs.filter((j) => j.status === 'queued')).toHaveLength(1);
    const c2 = await claim();
    expect(c2.job.new_customer_messages.map((m: { text: string }) => m.text)).toEqual(['gội đầu bao nhiêu', 'mà 9h tối thì sao']);
    expect(c2.job.unsent_drafts_since_last).toEqual([{ draft_id: d.body.draft_id, status: 'superseded', text: 'Dạ gội đầu thư giãn 50 phút ạ.' }]);
    expect(c2.job.conversation.session_id).toBe('sess-1');
  });

  it('runner wrong id, unknown job and double submit get the contract errors', async () => {
    await customerWithJob();
    const c = await claim();
    expect((await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ.'), 'mac-9')).body.error.code).toBe('lease_not_owned');
    expect((await runner('/runner/jobs/job_nope/heartbeat')).status).toBe(404);
    expect((await runner(`/runner/jobs/${c.job.job_id}/draft`, { ...draftBody('x'), text: '' })).status).toBe(422);
    expect((await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em chào anh/chị ạ.'))).status).toBe(200);
    expect((await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ.'))).body.error.code).toBe('job_not_leased');
  });

  it('fail routes the conversation to staff, records the runner error and resets a broken session', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    const f = await runner(`/runner/jobs/${c.job.job_id}/fail`, {
      error_kind: 'session_broken',
      error_message: 'resume failed twice',
      account_label: 'acct-a',
      session_id: 'sess-x',
      session_broken: true,
    });
    expect(f.status).toBe(200);
    expect(f.body.job_status).toBe('failed');
    expect(f.body.handoff_id).toMatch(/^hof_/);
    const conv = await env.DB.prepare('SELECT bot_state, needs_attention, session_reset_reason FROM conversations WHERE id = ?').bind(cid).first();
    expect(conv).toMatchObject({ bot_state: 'bot_active', needs_attention: 1, session_reset_reason: 'session_broken' });
    const rs = await env.DB.prepare("SELECT last_error_kind FROM runner_status WHERE runner_id = 'mac-1'").first<{ last_error_kind: string }>();
    expect(rs!.last_error_kind).toBe('session_broken');
    const bad = await runner(`/runner/jobs/${c.job.job_id}/fail`, { error_kind: 'weird' });
    expect(bad.status).toBe(422);
  });

  it('a retried event whose first ingest stopped after storing the message re-arms the debounce', async () => {
    const { userId, cid } = await consentedCustomer();
    const ev = textEvent(userId, 'gội đầu bao nhiêu tiền ạ');
    expect((await stubFor(userId).ingestEvent(ev)).action).toBe('debounced');
    // while the alarm is pending, a repeat changes nothing
    expect((await stubFor(userId).ingestEvent(ev)).action).toBe('stored');
    // simulate a D1 failure after the message INSERT: no alarm was set
    await runInDurableObject(stubFor(userId), async (_obj, state) => {
      await state.storage.deleteAlarm();
    });
    const retry = await stubFor(userId).ingestEvent(ev);
    expect(retry.action).toBe('debounced');
    expect(await fireDebounce(userId)).toBe(true);
    expect(await jobsOf(cid)).toHaveLength(1);
    // once a job covers the message, a further repeat is a no-op
    expect((await stubFor(userId).ingestEvent(ev)).action).toBe('stored');
    expect(await jobsOf(cid)).toHaveLength(1);
  });

  it('a retried event for a conversation the bot does not answer flags it for staff', async () => {
    const userId = uniq('u');
    const ev = textEvent(userId, 'alo');
    await stubFor(userId).ingestEvent(ev);
    const cid = await conversationIdOf(userId);
    await env.DB.prepare('UPDATE conversations SET needs_attention = 0 WHERE id = ?').bind(cid).run();
    expect((await stubFor(userId).ingestEvent(ev)).action).toBe('stored');
    const conv = await env.DB.prepare('SELECT needs_attention FROM conversations WHERE id = ?').bind(cid).first<{ needs_attention: number }>();
    expect(conv!.needs_attention).toBe(1);
  });

  it('fail with error_kind cancelled (runner shutdown) still routes the question to staff', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    const f = await runner(`/runner/jobs/${c.job.job_id}/fail`, { error_kind: 'cancelled', error_message: 'runner shutting down' });
    expect(f.status).toBe(200);
    expect(f.body.job_status).toBe('failed');
    expect(f.body.handoff_id).toMatch(/^hof_/);
    const job = await env.DB.prepare('SELECT status FROM jobs WHERE id = ?').bind(c.job.job_id).first<{ status: string }>();
    expect(job!.status).toBe('failed');
    const h = await env.DB.prepare('SELECT reason_code FROM handoffs WHERE id = ?').bind(f.body.handoff_id).first<{ reason_code: string }>();
    expect(h!.reason_code).toBe('ai_unavailable');
    const conv = await env.DB.prepare('SELECT needs_attention FROM conversations WHERE id = ?').bind(cid).first<{ needs_attention: number }>();
    expect(conv!.needs_attention).toBe(1);
  });

  it('heartbeat cancels the job when staff take over', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    expect((await staff('POST', `/staff/conversations/${cid}/takeover`, {})).status).toBe(200);
    const hb = await runner(`/runner/jobs/${c.job.job_id}/heartbeat`);
    expect(hb.body).toMatchObject({ cancel: true, cancel_reason: 'takeover' });
    const again = await runner(`/runner/jobs/${c.job.job_id}/heartbeat`);
    expect(again.body).toMatchObject({ cancel: true, cancel_reason: 'job_cancelled' });
  });

  it('runner offline: old queued jobs go to staff', async () => {
    const { cid } = await customerWithJob();
    await env.DB.prepare("UPDATE jobs SET created_at = ? WHERE conversation_id = ?").bind(Date.now() - 600_000, cid).run();
    await env.DB.prepare('DELETE FROM runner_status').run();
    expect(await sweepRunnerHealth(env, Date.now())).toBe(1);
    expect((await jobsOf(cid))[0]!.status).toBe('needs_staff');
  });

  it('runner alive but without a usable Claude account: old queued jobs go to staff', async () => {
    const { cid } = await customerWithJob();
    await env.DB.prepare("UPDATE jobs SET created_at = ? WHERE conversation_id = ?").bind(Date.now() - 600_000, cid).run();
    const limited = { label: 'a', usable_now: false, pool_status: 'limited', until: '2026-11-13T09:00:00+07:00' };
    await env.DB.prepare(
      "INSERT OR REPLACE INTO runner_status (runner_id, last_seen_at, last_status_at, snapshot_json) VALUES ('mac-1', ?, ?, ?)",
    )
      .bind(Date.now(), Date.now(), JSON.stringify({ runner_version: 't', accounts: [limited] }))
      .run();
    expect(await sweepRunnerHealth(env, Date.now())).toBe(1);
    expect((await jobsOf(cid))[0]!.status).toBe('needs_staff');
    const h = await env.DB.prepare('SELECT reason_code, summary_for_staff FROM handoffs WHERE conversation_id = ?').bind(cid).first<{ reason_code: string; summary_for_staff: string }>();
    expect(h!.reason_code).toBe('ai_unavailable');
    expect(h!.summary_for_staff).toMatch(/tài khoản Claude/);
  });

  it('runner alive with a usable account: queued jobs stay queued', async () => {
    const { cid } = await customerWithJob();
    await env.DB.prepare("UPDATE jobs SET created_at = ? WHERE conversation_id = ?").bind(Date.now() - 600_000, cid).run();
    await env.DB.prepare(
      "INSERT OR REPLACE INTO runner_status (runner_id, last_seen_at, last_status_at, snapshot_json) VALUES ('mac-1', ?, ?, ?)",
    )
      .bind(Date.now(), Date.now(), JSON.stringify({ runner_version: 't', accounts: [{ label: 'a', usable_now: false }, { label: 'b', usable_now: true }] }))
      .run();
    expect(await sweepRunnerHealth(env, Date.now())).toBe(0);
    expect((await jobsOf(cid))[0]!.status).toBe('queued');
  });

  it('session rules: resumed session after a draft, reset after staff release', async () => {
    const { userId, cid } = await customerWithJob();
    const c = await claim();
    expect(c.job.conversation).toMatchObject({ session_id: null, session_reset_reason: 'new_conversation' });
    await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em chào anh/chị ạ.', 'sess-A'));
    await say(userId, 'thêm câu nữa');
    await fireDebounce(userId);
    const c2 = await claim();
    expect(c2.job.conversation).toMatchObject({ session_id: 'sess-A', session_turns: 1, session_reset_reason: null });
    expect(c2.job.history).toEqual([]);
    await runner(`/runner/jobs/${c2.job.job_id}/draft`, draftBody('Dạ vâng ạ.', 'sess-A'));
    await staff('POST', `/staff/conversations/${cid}/takeover`, {});
    expect((await staff('POST', `/staff/conversations/${cid}/release`, {})).status).toBe(200);
    await say(userId, 'quay lại hỏi tiếp');
    await fireDebounce(userId);
    const c3 = await claim();
    expect(c3.job.conversation).toMatchObject({ session_id: null, session_reset_reason: 'released_by_staff' });
    expect(c3.job.history.length).toBeGreaterThan(0);
  });
});
