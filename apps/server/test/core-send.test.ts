// server-core: draft acceptance by mode, last-moment flag/state checks, staff approve / send / reject, prompt.
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { claim, customerWithJob, draftBody, runner, say, seed, setFlags, staff } from './core-helpers';

beforeEach(async () => {
  await seed();
});

const tool = (name: string, jobId: string, input: unknown) => runner(`/runner/tools/${name}`, { job_id: jobId, input });
const quoteGoiDau = (jobId: string) =>
  tool('quote_price', jobId, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '19:00', date_local: 'unknown' });
const botOutbox = async (cid: string) =>
  (await env.DB.prepare("SELECT o.payload_json FROM outbox o JOIN messages m ON m.id = o.message_id WHERE o.conversation_id = ? AND m.source IN ('bot','staff')").bind(cid).all()).results;

const GOOD = 'Dạ Gội đầu thư giãn 50 phút lúc 19h là 199.000đ ạ.';

describe('auto_allowed', () => {
  it('auto-sends a draft that passes the checker', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const { cid } = await customerWithJob();
    const c = await claim();
    expect(c.job.turn_context.conversation_mode).toBe('auto_allowed');
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'sent', action: 'auto_sent' });
    expect(d.body.message_id).toMatch(/^msg_/);
    const out = await botOutbox(cid);
    expect(out).toHaveLength(1);
    expect(String(out[0]!.payload_json)).toContain('199.000đ');
  });

  it('flags and state are re-read at the last moment: outbound off or takeover keeps the draft for staff', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const a = await customerWithJob();
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    await setFlags({ outbound_enabled: false }); // flipped while the model was drafting
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(await botOutbox(a.cid)).toHaveLength(0);
    // approving while outbound is off is refused too
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {})).body.error.code).toBe('outbound_disabled');

    await setFlags({ outbound_enabled: true });
    const b = await customerWithJob();
    const c2 = await claim();
    await quoteGoiDau(c2.job.job_id);
    await env.DB.prepare("UPDATE conversations SET bot_state = 'staff_takeover' WHERE id = ?").bind(b.cid).run();
    const d2 = await runner(`/runner/jobs/${c2.job.job_id}/draft`, draftBody(GOOD));
    expect(d2.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
    expect(await botOutbox(b.cid)).toHaveLength(0);
  });

  it('a draft with an ungrounded price is blocked and handed off, never sent', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const { cid } = await customerWithJob();
    const c = await claim();
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ gội đầu giá 150.000đ ạ.'));
    expect(d.body).toMatchObject({ status: 'blocked', action: 'queued_for_staff' });
    expect(d.body.checker.issues[0].rule).toBe('price');
    expect(await botOutbox(cid)).toHaveLength(0);
    const h = await env.DB.prepare("SELECT reason_code FROM handoffs WHERE conversation_id = ? AND reason_code = 'checker_blocked'").bind(cid).first();
    expect(h).not.toBeNull();
  });
});

describe('staff review', () => {
  it('approve_each: draft waits; approve sends it, approving twice is invalid_state', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
    expect(await botOutbox(cid)).toHaveLength(0);
    const detail = await staff('GET', `/staff/conversations/${cid}`);
    expect(detail.body.drafts[0]).toMatchObject({ id: d.body.draft_id, status: 'pending' });
    expect(detail.body.conversation).toMatchObject({ pending_drafts: 1, effective_mode: 'approve_each' });
    expect(detail.body.conversation.needs_attention).toBe(true);

    const bad = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, { text: '**Dạ** 199.000đ ạ' });
    expect(bad.status).toBe(422);
    expect(bad.body.error.code).toBe('checker_failed');

    const ok = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
    expect(ok.status).toBe(200);
    expect(ok.body.draft.status).toBe('sent');
    // needs_attention is recomputed after the staff action, not left at 1 until release.
    expect((await staff('GET', `/staff/conversations/${cid}`)).body.conversation.needs_attention).toBe(false);
    expect(ok.body.message).toMatchObject({ direction: 'outbound', source: 'bot', send_state: 'sent', draft_id: d.body.draft_id });
    expect(await botOutbox(cid)).toHaveLength(1);
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {})).body.error.code).toBe('invalid_state');
    const conv = await env.DB.prepare('SELECT bot_state FROM conversations WHERE id = ?').bind(cid).first<{ bot_state: string }>();
    expect(conv!.bot_state).toBe('bot_active');
  });

  it('a draft is sent once when approve and a manual send from the same draft race', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    const [a, m] = await Promise.all([
      staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {}),
      staff('POST', `/staff/conversations/${cid}/send`, { text: GOOD, from_draft_id: d.body.draft_id }),
    ]);
    expect([a.status, m.status].sort()).toEqual([200, 409]);
    expect(await botOutbox(cid)).toHaveLength(1);
  });

  it('manual send from a draft that an approve is already sending answers 409 and sends nothing', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    // state an in-flight approve leaves between its UPDATE and the Zalo call
    await env.DB.prepare("UPDATE drafts SET status = 'approved' WHERE id = ?").bind(d.body.draft_id).run();
    const m = await staff('POST', `/staff/conversations/${cid}/send`, { text: GOOD, from_draft_id: d.body.draft_id });
    expect(m.status).toBe(409);
    expect(m.body.error.code).toBe('invalid_state');
    expect(await botOutbox(cid)).toHaveLength(0);
    const conv = await env.DB.prepare('SELECT bot_state FROM conversations WHERE id = ?').bind(cid).first<{ bot_state: string }>();
    expect(conv!.bot_state).toBe('bot_active'); // the refused send did not take the conversation over
  });

  it('release keeps needs_attention while a pending draft is still waiting', async () => {
    const { cid } = await customerWithJob();
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body.status).toBe('pending');
    expect((await staff('POST', `/staff/conversations/${cid}/takeover`, {})).status).toBe(200);
    expect((await staff('POST', `/staff/conversations/${cid}/release`, {})).status).toBe(200);
    const conv = await env.DB.prepare('SELECT bot_state, needs_attention FROM conversations WHERE id = ?').bind(cid).first();
    expect(conv).toMatchObject({ bot_state: 'bot_active', needs_attention: 1 });
  });

  it('draft_only: approve is refused; manual send works and takes the conversation over', async () => {
    await setFlags({ auto_reply_mode: 'draft_only' });
    const { cid } = await customerWithJob();
    const c = await claim();
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em chào anh/chị ạ.'));
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {})).body.error.code).toBe('mode_draft_only');
    const s = await staff('POST', `/staff/conversations/${cid}/send`, { text: 'Dạ chị cần hỗ trợ gì ạ?', from_draft_id: d.body.draft_id });
    expect(s.status).toBe(200);
    expect(s.body.message).toMatchObject({ source: 'staff', send_state: 'sent' });
    const conv = await env.DB.prepare('SELECT bot_state, takeover_by FROM conversations WHERE id = ?').bind(cid).first();
    expect(conv).toMatchObject({ bot_state: 'staff_takeover', takeover_by: 'tester' });
    const dr = await env.DB.prepare('SELECT status, final_text FROM drafts WHERE id = ?').bind(d.body.draft_id).first();
    expect(dr).toMatchObject({ status: 'sent', final_text: 'Dạ chị cần hỗ trợ gì ạ?' });
  });

  it('reject, flags, handoffs, runner, outbox and list endpoints', async () => {
    const { userId, cid } = await customerWithJob();
    const c = await claim();
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em chào anh/chị ạ.'));
    const rj = await staff('POST', `/staff/drafts/${d.body.draft_id}/reject`, { reason: 'sai giọng' });
    expect(rj.body.draft.status).toBe('rejected');
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/reject`, {})).status).toBe(409);

    const flags = await staff('PUT', '/staff/flags', { promotions_enabled: true });
    expect(flags.body.flags.promotions_enabled).toBe(true);
    expect(flags.body.updated.promotions_enabled.by).toBe('tester');
    expect((await staff('PUT', '/staff/flags', { nope: 1 })).status).toBe(422);
    expect((await staff('PUT', '/staff/flags', { auto_reply_mode: 'yolo' })).status).toBe(422);

    await say(userId, '#gap_nhan_vien');
    const hs = await staff('GET', '/staff/handoffs');
    const mine = hs.body.items.find((h: { conversation_id: string }) => h.conversation_id === cid);
    expect(mine.reason_code).toBe('customer_requested_human');
    const open = await staff('GET', '/staff/conversations?needs_attention=true');
    expect(open.body.items.some((x: { id: string }) => x.id === cid)).toBe(true);
    expect((await staff('POST', `/staff/handoffs/${mine.id}/resolve`, {})).body.handoff.status).toBe('resolved');

    expect((await staff('PUT', '/staff/runner/account', { label: 'ultra-anlnt' })).body.desired_account).toBe('ultra-anlnt');
    const st = await runner('/runner/status', {
      runner_version: '0.1.0', hostname: 'h', active_jobs: 0, max_concurrency: 3, accounts: [], next_account: null, applied_desired_account: 'auto', reported_at: Date.now(),
    });
    expect(st.body).toMatchObject({ ok: true, desired_account: 'ultra-anlnt', flags: { ai_engine: 'subscription' } });
    const rr = await staff('GET', '/staff/runner');
    expect(rr.body.runners.find((r: { runner_id: string }) => r.runner_id === 'mac-1')).toMatchObject({ online: true });

    const ob = await staff('GET', '/staff/outbox?limit=1');
    expect(ob.body.items).toHaveLength(1);
    expect(ob.body.next_cursor).not.toBeNull();
    // still needs attention after the handoff is resolved: the customer's request for a human has no reply yet
    const list = await staff('GET', '/staff/conversations?needs_attention=true');
    expect(list.body.items.some((x: { id: string }) => x.id === cid)).toBe(true);
    expect((await staff('GET', '/staff/conversations/cnv_nope')).status).toBe(404);
  });
});

describe('prompt', () => {
  it('GET /runner/prompt builds blocks A/B/C from D1 and matches the claimed job hash', async () => {
    const p = await runner('/runner/prompt', undefined, 'mac-1', 'GET');
    expect(p.status).toBe(200);
    expect(p.body.blocks.a).toContain('<hard_rules>');
    expect(p.body.blocks.b).toContain('[service_id: goi-dau-thu-gian] group: hair | display_name_vi: Gội đầu thư giãn');
    expect(p.body.blocks.b).toContain('Total 23 services.');
    expect(p.body.blocks.b).not.toMatch(/\d{3}\.000đ/);
    expect(p.body.blocks.c).toContain('opening_hours: [chưa có]');
    expect(p.body.blocks.c).toContain('address: [chưa có]'); // status conflict is not given
    expect(p.body.tools.map((t: { name: string }) => t.name)).toEqual([
      'search_services', 'get_service_details', 'quote_price', 'list_active_promotions', 'create_booking_request', 'handoff_to_staff', 'record_contact_preference',
      'attach_menu_images', 'get_customer_profile',
    ]);
    expect(JSON.stringify(p.body.tools)).not.toContain('x_server_policy');
    expect(p.body.cli_system_prompt).toContain('mcp__thom__');
    await customerWithJob();
    const c = await claim();
    expect(c.job.prompt_hash).toBe(p.body.prompt_hash);
    expect(c.job.turn_context_text).toMatch(/^<turn_context>\nnow_local: \d{4}-\d{2}-\d{2}T\d{2}:\d{2} Asia\/Ho_Chi_Minh/);
  });
});
