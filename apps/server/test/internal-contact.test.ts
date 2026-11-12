// Contact roles in the draft pipeline (docs/contracts.md section 14.3). A manager or a staff member is an internal
// contact: the message is stored and nothing else happens on any path (ingest, enqueue, claim, heartbeat, draft
// acceptance, approve, write tools, the bridge queue, follow-ups). The role customer overrides the quiet rule of
// section 13. Every name, id and text is synthetic.
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { profileFactsForModel } from '../src/lib/profiles';
import { runDueFollowups } from '../src/scheduler/followups';
import { claim, draftBody, jobsOf, runner, seed, setFlags, staff } from './core-helpers';
import { addProfile, auditCount, count, GOI, past } from './customers-helpers';
import {
  ask,
  botOutbox,
  bridge,
  consentedThread,
  convOf,
  fireDebounce,
  ingest,
  messagesOf,
  msgEvent,
  outboxOf,
  personalJob,
  postPersonal,
  sendNext,
  settle,
  thread,
  write,
  zaloOf,
} from './personal-helpers';

let catalogVersion = '';

beforeEach(async () => {
  catalogVersion = (await seed()).catalog_version;
  await settle();
});

const tool = (name: string, jobId: string, input: unknown) => runner(`/runner/tools/${name}`, { job_id: jobId, input });
const quoteGoiDau = (jobId: string) =>
  tool('quote_price', jobId, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '19:00', date_local: 'unknown' });
const GOOD = 'Dạ Gội đầu thư giãn 50 phút lúc 19h là 199.000đ ạ.';

async function setRole(threadId: string, role: 'customer' | 'manager' | 'staff' | null) {
  const r = await staff('PUT', `/staff/roles/${encodeURIComponent(zaloOf(threadId))}`, { role });
  expect(r.status).toBe(200);
  return r.body.role;
}

const jobRow = (id: string) => env.DB.prepare('SELECT status, last_error FROM jobs WHERE id = ?').bind(id).first<{ status: string; last_error: string | null }>();
const openJobs = async (cid: string) => (await jobsOf(cid)).filter((j) => j.status === 'queued' || j.status === 'leased');
const outbound = async (cid: string) => (await messagesOf(cid)).filter((m) => m.direction === 'outbound');
const handoffs = (cid: string) => count('SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ?', cid);
const draftsOf = async (cid: string) => (await env.DB.prepare('SELECT id, status FROM drafts WHERE conversation_id = ?').bind(cid).all<{ id: string; status: string }>()).results;

/** What staff and the customer would notice: outbound messages, bridge rows, the staff flag, handoffs, open jobs. */
async function footprint(threadId: string) {
  const conv = (await convOf(threadId))!;
  return {
    bot_state: conv.bot_state,
    needs_attention: conv.needs_attention,
    outbound: (await outbound(conv.id)).length,
    outbox: (await outboxOf(threadId)).length,
    handoffs: await handoffs(conv.id),
    open_jobs: (await openJobs(conv.id)).length,
  };
}

describe('internal contact (role manager or staff)', () => {
  it('a first message is stored and nothing else happens: no consent prompt, no flag for staff, no job', async () => {
    for (const role of ['manager', 'staff'] as const) {
      const threadId = thread();
      expect(await setRole(threadId, role)).toMatchObject({ zalo_user_id: zaloOf(threadId), role, source: 'staff' });
      const quietBefore = await auditCount('conversation.staff_only_profile');

      const r = await ingest(threadId, 'mai chị nghỉ nhé');
      expect(r.action).toBe('internal_contact');
      const conv = (await convOf(threadId))!;
      const rows = await messagesOf(conv.id);
      expect(rows).toHaveLength(1);
      expect(rows[0]).toMatchObject({ id: r.message_id, direction: 'inbound', source: 'customer', text: 'mai chị nghỉ nhé' });
      expect(await footprint(threadId)).toEqual({ bot_state: 'awaiting_consent', needs_attention: 0, outbound: 0, outbox: 0, handoffs: 0, open_jobs: 0 });
      expect(await jobsOf(conv.id)).toHaveLength(0);
      expect(await auditCount('conversation.staff_only_profile')).toBe(quietBefore);

      // the same through the webhook, and again after the debounce alarm (none is set)
      expect((await write(threadId, 'thứ 7 chị đi làm lại')).status).toBe(200);
      expect(await fireDebounce(threadId)).toBe(false);
      expect(await messagesOf(conv.id)).toHaveLength(2);
      expect(await footprint(threadId)).toEqual({ bot_state: 'awaiting_consent', needs_attention: 0, outbound: 0, outbox: 0, handoffs: 0, open_jobs: 0 });
      expect((await bridge('/bridge/outbox/claim')).body.item).toBeNull();
    }
  });

  it('the quiet rule of section 13 does not fire for an internal contact either', async () => {
    await setFlags({ profile_personal_skip_bot: true });
    const threadId = thread();
    await addProfile(zaloOf(threadId), { relationship: 'family' });
    await setRole(threadId, 'manager');
    expect((await ingest(threadId, 'tối nay ăn gì')).action).toBe('internal_contact');
    expect(await footprint(threadId)).toEqual({ bot_state: 'awaiting_consent', needs_attention: 0, outbound: 0, outbox: 0, handoffs: 0, open_jobs: 0 });
  });

  it('a photo from an internal contact in bot_active opens no handoff and sends no fixed text', async () => {
    const p = await consentedThread();
    await setRole(p.threadId, 'staff');
    const before = await footprint(p.threadId);
    const photo = msgEvent(p.threadId, { title: '', href: 'https://photo.test/a.jpg', thumb: 'https://photo.test/a_t.jpg' }, { msgType: 'chat.photo' });
    expect((await postPersonal(photo)).status).toBe(200);
    expect(await footprint(p.threadId)).toEqual(before);
    expect(before).toMatchObject({ bot_state: 'bot_active', handoffs: 0, open_jobs: 0 });
  });

  it('the role set after a question: the next message cancels the queued draft job and bot_state stays', async () => {
    const p = await consentedThread();
    await ask(p.threadId);
    const [job] = await openJobs(p.cid);
    expect(job).toMatchObject({ status: 'queued' });
    await setRole(p.threadId, 'manager');
    const before = await footprint(p.threadId);

    expect((await ingest(p.threadId, 'à thôi chị hỏi nhầm')).action).toBe('internal_contact');
    expect(await jobRow(job!.id)).toEqual({ status: 'cancelled', last_error: 'internal_contact' });
    expect(await footprint(p.threadId)).toEqual({ ...before, open_jobs: 0 });
    expect(before.bot_state).toBe('bot_active');
    expect((await convOf(p.threadId))!.debounce_until).toBeNull();
    expect((await claim()).job).toBeNull();
  });

  it('the role set during the debounce window: the alarm queues no job and flags nothing', async () => {
    const p = await consentedThread();
    expect((await write(p.threadId, 'gội đầu bao nhiêu tiền ạ')).status).toBe(200);
    await setRole(p.threadId, 'staff');
    const before = await footprint(p.threadId);
    await fireDebounce(p.threadId);
    expect(await jobsOf(p.cid)).toHaveLength(0);
    expect(await footprint(p.threadId)).toEqual(before);
    expect((await claim()).job).toBeNull();
  });

  it('claim does not hand out a queued job of an internal contact: the job is cancelled quietly', async () => {
    const p = await consentedThread();
    await ask(p.threadId);
    const [job] = await openJobs(p.cid);
    await setRole(p.threadId, 'manager');
    const before = await footprint(p.threadId);

    const c = await claim();
    expect(c.job).toBeNull();
    expect(await jobRow(job!.id)).toEqual({ status: 'cancelled', last_error: 'internal_contact' });
    expect(await footprint(p.threadId)).toEqual({ ...before, open_jobs: 0 });
  });

  it('heartbeat cancels a leased job with the reason job_cancelled and records internal_contact', async () => {
    const p = await personalJob();
    expect((await runner(`/runner/jobs/${p.jobId}/heartbeat`)).body.cancel).toBe(false);
    await setRole(p.threadId, 'staff');
    const before = await footprint(p.threadId);

    const hb = await runner(`/runner/jobs/${p.jobId}/heartbeat`);
    expect(hb.status).toBe(200);
    expect(hb.body).toMatchObject({ cancel: true, cancel_reason: 'job_cancelled' });
    expect(await jobRow(p.jobId)).toEqual({ status: 'cancelled', last_error: 'cancel:internal_contact' });
    expect(await footprint(p.threadId)).toEqual({ ...before, open_jobs: 0 });
    // a repeated heartbeat answers the same
    expect((await runner(`/runner/jobs/${p.jobId}/heartbeat`)).body).toMatchObject({ cancel: true, cancel_reason: 'job_cancelled' });
  });

  it('a draft of a leased job is discarded: not sent, not shown as waiting, no handoff', async () => {
    const p = await personalJob();
    await quoteGoiDau(p.jobId);
    await setRole(p.threadId, 'manager');
    const before = await footprint(p.threadId);

    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody(GOOD));
    expect(d.status).toBe(200);
    expect(d.body).toMatchObject({ status: 'discarded', action: 'dropped', message_id: null });
    expect(await botOutbox(p.cid)).toHaveLength(0);
    expect(await footprint(p.threadId)).toEqual({ ...before, open_jobs: 0 });
    expect((await draftsOf(p.cid)).map((x) => x.status)).toEqual(['discarded']);
    expect((await staff('GET', `/staff/conversations/${p.cid}`)).body.conversation.pending_drafts).toBe(0);
  });

  it('nothing is sent under global auto_allowed, with the switch on, or for a draft the checker blocks', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const a = await personalJob();
    await quoteGoiDau(a.jobId);
    await setRole(a.threadId, 'staff');
    const d1 = await runner(`/runner/jobs/${a.jobId}/draft`, draftBody(GOOD));
    expect(d1.body).toMatchObject({ status: 'discarded', action: 'dropped', message_id: null });
    expect(await botOutbox(a.cid)).toHaveLength(0);

    // a blocked draft would open a checker_blocked handoff for a customer; not for an internal contact
    const b = await personalJob();
    await setRole(b.threadId, 'manager');
    const before = await footprint(b.threadId);
    const d2 = await runner(`/runner/jobs/${b.jobId}/draft`, draftBody('Dạ gội đầu giá 150.000đ ạ.'));
    expect(d2.body).toMatchObject({ status: 'discarded', action: 'dropped' });
    expect(await footprint(b.threadId)).toEqual({ ...before, open_jobs: 0 });

    // the switch was turned on before the role was set
    await setFlags({ auto_reply_mode: 'approve_each' });
    const c = await personalJob();
    expect((await staff('PUT', `/staff/conversations/${c.cid}/auto-reply`, { auto_reply: 'on' })).status).toBe(200);
    await quoteGoiDau(c.jobId);
    await setRole(c.threadId, 'manager');
    const d3 = await runner(`/runner/jobs/${c.jobId}/draft`, draftBody(GOOD));
    expect(d3.body).toMatchObject({ status: 'discarded', action: 'dropped', message_id: null });
    expect(await botOutbox(c.cid)).toHaveLength(0);
    expect((await bridge('/bridge/outbox/claim')).body.item).toBeNull();
  });

  it('write tools of a running job are refused and record nothing', async () => {
    const p = await personalJob();
    await setRole(p.threadId, 'manager');
    const before = await footprint(p.threadId);

    const h = await tool('handoff_to_staff', p.jobId, { reason_code: 'customer_request', urgency: 'normal', summary_for_staff: 'Khách muốn gặp nhân viên.' });
    expect(h.status).toBe(200);
    expect(h.body.is_error).toBe(true);
    expect(h.body.result).toMatchObject({ status: 'rejected', error: 'internal_contact' });
    const pref = await tool('record_contact_preference', p.jobId, { preference_type: 'ai_assistant', action: 'opt_out', customer_words: 'đừng để máy trả lời nữa' });
    expect(pref.body.is_error).toBe(true);
    expect(pref.body.result).toMatchObject({ status: 'rejected', error: 'internal_contact' });
    expect(await footprint(p.threadId)).toEqual(before);
    expect(await count('SELECT COUNT(*) AS n FROM contact_preferences WHERE customer_id = ?', p.customerId)).toBe(0);
    expect(await count('SELECT COUNT(*) AS n FROM booking_requests WHERE customer_id = ?', p.customerId)).toBe(0);
  });

  it('a bot reply approved before the role was set is not handed to the bridge, and a waiting draft cannot be approved', async () => {
    const p = await personalJob();
    await quoteGoiDau(p.jobId);
    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {})).status).toBe(200);
    expect((await botOutbox(p.cid)).map((x) => x.status)).toEqual(['queued']);

    // a second question whose draft is still waiting for staff
    await ask(p.threadId, 'massage chân bao nhiêu ạ');
    const c2 = await claim();
    expect(c2.job.conversation.conversation_id).toBe(p.cid);
    const d2 = await runner(`/runner/jobs/${c2.job.job_id}/draft`, draftBody('Dạ để em kiểm tra rồi báo mình ngay ạ.'));
    expect(d2.body.action).toBe('queued_for_staff');

    await setRole(p.threadId, 'manager');
    const flagged = (await convOf(p.threadId))!.needs_attention;

    const claimed = await bridge('/bridge/outbox/claim');
    expect(claimed.status).toBe(200);
    expect(claimed.body.item).toBeNull();
    const rows = await env.DB.prepare("SELECT o.status, o.error FROM outbox o JOIN messages m ON m.id = o.message_id WHERE o.conversation_id = ? AND m.source = 'bot'").bind(p.cid).all<{ status: string; error: string | null }>();
    expect(rows.results).toEqual([{ status: 'failed', error: 'cancelled: internal contact' }]);
    expect((await convOf(p.threadId))!.needs_attention).toBe(flagged);

    const approve = await staff('POST', `/staff/drafts/${d2.body.draft_id}/approve`, {});
    expect(approve.status).toBe(409);
    expect(approve.body.error.code).toBe('invalid_state');
    expect((await botOutbox(p.cid)).filter((x) => x.status === 'queued')).toHaveLength(0);
  });

  it('a consent prompt still in the bridge queue is cancelled when the contact turns out to be internal', async () => {
    const threadId = thread();
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    expect((await outboxOf(threadId)).map((x) => x.status)).toEqual(['queued']);
    await setRole(threadId, 'staff');
    expect((await bridge('/bridge/outbox/claim')).body.item).toBeNull();
    expect((await outboxOf(threadId)).map((x) => x.status)).toEqual(['failed']);
    expect((await convOf(threadId))!.needs_attention).toBe(0);
  });

  it('follow-up jobs of a visit are born skipped, and a job queued earlier is skipped when it runs', async () => {
    const a = await consentedThread();
    await setRole(a.threadId, 'manager');
    const v = await staff('POST', '/staff/visits', { customer_id: a.customerId, service_id: GOI, visited_at: past(1) });
    expect(v.status).toBe(200);
    expect(v.body.jobs.map((j: any) => j.status)).toEqual(['skipped', 'skipped']);
    const born = await env.DB.prepare("SELECT status, last_error FROM jobs WHERE customer_id = ? AND type IN ('thank_you','check_in')").bind(a.customerId).all();
    expect(born.results).toEqual([
      { status: 'skipped', last_error: 'internal_contact' },
      { status: 'skipped', last_error: 'internal_contact' },
    ]);

    const b = await consentedThread();
    const v2 = await staff('POST', '/staff/visits', { customer_id: b.customerId, service_id: GOI, visited_at: past(2) });
    const checkIn = v2.body.jobs.find((j: any) => j.type === 'check_in');
    expect(checkIn.status).toBe('queued');
    await setRole(b.threadId, 'staff');
    await setFlags({ scheduled_sends_enabled: true });
    const sentBefore = (await outboxOf(b.threadId)).length;
    await runDueFollowups(env, checkIn.run_at + 60_000); // 10:01 local, inside the send window
    expect(await jobRow(checkIn.job_id)).toEqual({ status: 'skipped', last_error: 'internal_contact' });
    expect(await outboxOf(b.threadId)).toHaveLength(sentBefore);
  });

  it('bot_state is left unchanged: an expired takeover is not released while the role is set', async () => {
    const p = await consentedThread();
    await env.DB.prepare("UPDATE conversations SET bot_state = 'staff_takeover', takeover_by = 'tester', takeover_until = ? WHERE id = ?").bind(Date.now() - 60_000, p.cid).run();
    await setRole(p.threadId, 'manager');
    expect((await ingest(p.threadId, 'chị gửi lịch tuần sau nhé')).action).toBe('internal_contact');
    expect((await convOf(p.threadId))!.bot_state).toBe('staff_takeover');
    expect(await openJobs(p.cid)).toHaveLength(0);

    // the role removed: the takeover returns to the bot on the next message
    expect(await setRole(p.threadId, null)).toBeNull();
    expect((await ingest(p.threadId, 'gội đầu bao nhiêu tiền ạ')).action).toBe('debounced');
    expect((await convOf(p.threadId))!.bot_state).toBe('bot_active');
  });

  it('the role removed: a new contact gets the consent prompt on the next message', async () => {
    const threadId = thread();
    await setRole(threadId, 'manager');
    expect((await ingest(threadId, 'chào')).action).toBe('internal_contact');
    expect(await outboxOf(threadId)).toHaveLength(0);

    expect(await setRole(threadId, null)).toBeNull();
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    const item = await sendNext(threadId);
    expect(item.thread_id).toBe(threadId);
    expect((await convOf(threadId))!.bot_state).toBe('awaiting_consent');
  });

  it('the role removed: a consented contact gets a draft job on the next message', async () => {
    const p = await consentedThread();
    await setRole(p.threadId, 'staff');
    expect((await ingest(p.threadId, 'gội đầu bao nhiêu tiền ạ')).action).toBe('internal_contact');
    expect(await jobsOf(p.cid)).toHaveLength(0);

    await setRole(p.threadId, null);
    expect((await ingest(p.threadId, 'gội đầu bao nhiêu tiền ạ')).action).toBe('debounced');
    await fireDebounce(p.threadId);
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(p.cid);
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
  });

  it('the staff views show the role while it is set', async () => {
    const p = await consentedThread();
    const plain = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(plain.body.conversation).not.toHaveProperty('role');
    expect(plain.body.conversation).not.toHaveProperty('role_source');

    await setRole(p.threadId, 'manager');
    const detail = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(detail.body.conversation).toMatchObject({ role: 'manager', role_source: 'staff' });
    const list = await staff('GET', '/staff/conversations');
    expect(list.body.items.find((x: any) => x.id === p.cid)).toMatchObject({ role: 'manager', role_source: 'staff' });

    await setRole(p.threadId, null);
    expect((await staff('GET', `/staff/conversations/${p.cid}`)).body.conversation).not.toHaveProperty('role');
  });
});

describe('role customer', () => {
  it('overrides a family relationship: the contact gets the consent prompt instead of the quiet rule', async () => {
    await setFlags({ profile_personal_skip_bot: true });

    // without a role the quiet rule of section 13 fires
    const quiet = thread();
    await addProfile(zaloOf(quiet), { relationship: 'family', address_term: 'chị', name_to_use: 'Lan', address_confidence: 'high' });
    expect((await ingest(quiet, 'tối nay ăn gì')).action).toBe('staff_only_profile');
    expect(await footprint(quiet)).toMatchObject({ bot_state: 'staff_only', needs_attention: 1, outbound: 0, outbox: 0 });
    expect(await profileFactsForModel(env, zaloOf(quiet), catalogVersion)).toBeNull();

    // with the role customer the same profile is read as a customer
    const threadId = thread();
    await addProfile(zaloOf(threadId), { relationship: 'family', address_term: 'chị', name_to_use: 'Lan', address_confidence: 'high' });
    expect(await setRole(threadId, 'customer')).toMatchObject({ role: 'customer', source: 'staff' });
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    expect(await footprint(threadId)).toMatchObject({ bot_state: 'awaiting_consent', needs_attention: 0, outbox: 1 });
    await sendNext(threadId);
    await write(threadId, 'Đồng ý');
    await sendNext(threadId);
    const conv = (await convOf(threadId))!;
    expect(conv.bot_state).toBe('bot_active');

    expect(await profileFactsForModel(env, zaloOf(threadId), catalogVersion)).toMatchObject({ relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    await ask(threadId);
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(conv.id);
    expect(c.job.customer_profile).toMatchObject({ relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    const facts = await tool('get_customer_profile', c.job.job_id, {});
    expect(facts.body.is_error).toBe(false);
    expect(facts.body.result).toMatchObject({ found: true, role: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    expect((await staff('GET', `/staff/conversations/${conv.id}`)).body.conversation).toMatchObject({ role: 'customer', role_source: 'staff' });
  });

  it('the profile view carries the role, and its model facts follow the role', async () => {
    const threadId = thread();
    const id = encodeURIComponent(zaloOf(threadId));
    await addProfile(zaloOf(threadId), { relationship: 'family', address_term: 'chị', name_to_use: 'Lan', address_confidence: 'high' });
    const plain = await staff('GET', `/staff/profiles/${id}`);
    expect(plain.status).toBe(200);
    expect(plain.body.profile).toMatchObject({ relationship: 'family', model_facts: null });
    expect(plain.body.profile).not.toHaveProperty('role');
    expect(plain.body.profile).not.toHaveProperty('role_source');

    await setRole(threadId, 'customer');
    const asCustomer = (await staff('GET', `/staff/profiles/${id}`)).body.profile;
    // the stored relationship is shown as it is; the bot reads the contact as a customer
    expect(asCustomer).toMatchObject({ relationship: 'family', role: 'customer', role_source: 'staff', model_facts: { relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' } });
    const listed = (await staff('GET', '/staff/profiles?relationship=family')).body.items.find((x: any) => x.zalo_user_id === zaloOf(threadId));
    expect(listed).toMatchObject({ role: 'customer', role_source: 'staff' });

    await setRole(threadId, 'staff');
    expect((await staff('GET', `/staff/profiles/${id}`)).body.profile).toMatchObject({ role: 'staff', role_source: 'staff', model_facts: null });
  });

  it('removing the role customer brings the quiet rule back for a contact that has not consented yet', async () => {
    await setFlags({ profile_personal_skip_bot: true });
    const threadId = thread();
    await addProfile(zaloOf(threadId), { relationship: 'friend' });
    await setRole(threadId, 'customer');
    expect((await ingest(threadId, 'chào shop')).action).toBe('consent_prompt_sent');
    await setRole(threadId, null);
    expect((await ingest(threadId, 'đi cà phê không')).action).toBe('staff_only_profile');
    expect((await convOf(threadId))!.bot_state).toBe('staff_only');
  });
});
