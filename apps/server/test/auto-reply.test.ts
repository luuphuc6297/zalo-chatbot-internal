// Auto reply switch of one conversation (docs/contracts.md section 14.4): conversationMode, the endpoint
// PUT /staff/conversations/:id/auto-reply with its interplay with PUT .../mode, and what the switch does to a draft.
// Every name, id and text is synthetic.
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { conversationMode, effectiveMode } from '../src/lib/flags';
import { MODE_ORDER, type ConversationMode } from '../src/types';
import { claim, consentedCustomer, customerWithJob, draftBody, fireDebounce, jobsOf, runner, say, seed, setFlags, staff } from './core-helpers';
import { auditCount, lastAudit } from './customers-helpers';
import { convOf, ingest, settle, thread, zaloOf } from './personal-helpers';

beforeEach(async () => {
  await seed();
  await settle();
});

const tool = (name: string, jobId: string, input: unknown) => runner(`/runner/tools/${name}`, { job_id: jobId, input });
const quoteGoiDau = (jobId: string) =>
  tool('quote_price', jobId, { service_id: 'goi-dau-thu-gian', duration_min: 50, start_time_local: '19:00', date_local: 'unknown' });
const botOutbox = async (cid: string) =>
  (await env.DB.prepare("SELECT o.payload_json FROM outbox o JOIN messages m ON m.id = o.message_id WHERE o.conversation_id = ? AND m.source IN ('bot','staff')").bind(cid).all()).results;
const botMessages = async (cid: string) =>
  (await env.DB.prepare("SELECT id FROM messages WHERE conversation_id = ? AND source = 'bot'").bind(cid).all()).results;
const setSwitch = (cid: string, value: unknown) => staff('PUT', `/staff/conversations/${cid}/auto-reply`, { auto_reply: value });
const setMode = (cid: string, mode: unknown) => staff('PUT', `/staff/conversations/${cid}/mode`, { mode });
const switchOf = async (cid: string) =>
  (await env.DB.prepare('SELECT auto_reply, mode FROM conversations WHERE id = ?').bind(cid).first<{ auto_reply: string | null; mode: string | null }>())!;

const GOOD = 'Dạ Gội đầu thư giãn 50 phút lúc 19h là 199.000đ ạ.';

describe('conversationMode', () => {
  const GLOBALS: ConversationMode[] = ['off', 'draft_only', 'approve_each', 'auto_allowed'];
  const MODES: (ConversationMode | null)[] = [null, 'off', 'draft_only', 'approve_each', 'auto_allowed'];
  const SWITCHES: ('on' | 'off' | null | undefined)[] = [undefined, null, 'on', 'off'];
  const rank = (m: ConversationMode) => MODE_ORDER.indexOf(m);
  const lower = (a: ConversationMode, b: ConversationMode) => (rank(a) <= rank(b) ? a : b);

  /** The rule of section 14.4 written a second time, from the contract text. */
  function expected(global: ConversationMode, mode: ConversationMode | null, sw: 'on' | 'off' | null | undefined): ConversationMode {
    if (global === 'off') return 'off'; // the global flag off always wins
    if (sw === 'on') return 'auto_allowed'; // the switch on beats the global mode and the per-conversation mode
    const base = mode === null ? global : lower(global, mode);
    return sw === 'off' ? lower(base, 'approve_each') : base; // the switch off never sends without approval
  }

  it('answers the rule of section 14.4 for every combination of global flag, conversation mode and switch', () => {
    let checked = 0;
    for (const global of GLOBALS) {
      for (const mode of MODES) {
        for (const sw of SWITCHES) {
          const conv = sw === undefined ? { mode } : { mode, auto_reply: sw };
          expect(conversationMode({ auto_reply_mode: global }, conv), `global=${global} mode=${mode} switch=${sw}`).toBe(expected(global, mode, sw));
          checked++;
        }
      }
    }
    expect(checked).toBe(80);
  });

  it('a conversation without the switch (column absent or NULL) keeps the mode from before section 14', () => {
    for (const global of GLOBALS) {
      for (const mode of MODES) {
        expect(conversationMode({ auto_reply_mode: global }, { mode })).toBe(effectiveMode(global, mode));
        expect(conversationMode({ auto_reply_mode: global }, { mode, auto_reply: null })).toBe(effectiveMode(global, mode));
      }
    }
  });

  it('the cases the contract names', () => {
    const m = (global: ConversationMode, mode: ConversationMode | null, auto_reply: 'on' | 'off' | null) => conversationMode({ auto_reply_mode: global }, { mode, auto_reply });
    // switch on: auto under the default global approve_each, and under draft_only
    expect(m('approve_each', null, 'on')).toBe('auto_allowed');
    expect(m('draft_only', null, 'on')).toBe('auto_allowed');
    // switch on beats a lower per-conversation mode (the endpoint clears that mode anyway)
    expect(m('approve_each', 'off', 'on')).toBe('auto_allowed');
    expect(m('approve_each', 'draft_only', 'on')).toBe('auto_allowed');
    // the global flag off stops everything, switch or not
    expect(m('off', null, 'on')).toBe('off');
    expect(m('off', 'auto_allowed', 'on')).toBe('off');
    // switch off: never more than approve_each, and a lower mode stays
    expect(m('auto_allowed', null, 'off')).toBe('approve_each');
    expect(m('auto_allowed', 'auto_allowed', 'off')).toBe('approve_each');
    expect(m('auto_allowed', 'draft_only', 'off')).toBe('draft_only');
    expect(m('auto_allowed', 'off', 'off')).toBe('off');
    expect(m('draft_only', null, 'off')).toBe('draft_only');
    // no switch
    expect(m('auto_allowed', null, null)).toBe('auto_allowed');
    expect(m('approve_each', null, null)).toBe('approve_each');
    expect(m('auto_allowed', 'approve_each', null)).toBe('approve_each');
  });
});

describe('PUT /staff/conversations/:id/auto-reply', () => {
  it('rejects a value other than on or off and an unknown conversation', async () => {
    const { cid } = await consentedCustomer();
    for (const body of [{}, { auto_reply: null }, { auto_reply: true }, { auto_reply: 'ON' }, { auto_reply: 'auto' }]) {
      const r = await staff('PUT', `/staff/conversations/${cid}/auto-reply`, body);
      expect(r.status).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field: 'auto_reply' } });
    }
    expect((await switchOf(cid)).auto_reply).toBeNull();
    const missing = await setSwitch('conv_does_not_exist', 'on');
    expect(missing.status).toBe(404);
    expect(missing.body.error.code).toBe('not_found');
  });

  it('a conversation that never had the switch set shows no auto_reply field', async () => {
    const { cid } = await consentedCustomer();
    const detail = await staff('GET', `/staff/conversations/${cid}`);
    expect(detail.status).toBe(200);
    expect(detail.body.conversation).not.toHaveProperty('auto_reply');
    expect(detail.body.conversation.effective_mode).toBe('approve_each');
    const list = await staff('GET', '/staff/conversations');
    const row = list.body.items.find((x: any) => x.id === cid);
    expect(row).toBeDefined();
    expect(row).not.toHaveProperty('auto_reply');
  });

  it('on: stores the switch, clears the per-conversation mode, answers the summary and writes one audit row', async () => {
    const { cid } = await consentedCustomer();
    expect((await setMode(cid, 'draft_only')).status).toBe(200);
    const before = await auditCount('conversation.auto_reply');

    const r = await setSwitch(cid, 'on');
    expect(r.status).toBe(200);
    expect(r.body.conversation).toMatchObject({ id: cid, auto_reply: 'on', mode_override: null, effective_mode: 'auto_allowed' });
    expect(await switchOf(cid)).toEqual({ auto_reply: 'on', mode: null });
    expect(await auditCount('conversation.auto_reply')).toBe(before + 1);
    const audit = await lastAudit('conversation.auto_reply');
    expect(audit).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'conversation', entity_id: cid });
    expect(JSON.parse(audit!.before_json!)).toEqual({ auto_reply: null, mode: 'draft_only' });
    expect(JSON.parse(audit!.after_json!)).toEqual({ auto_reply: 'on', mode: null });

    // the list and the detail show the switch
    const detail = await staff('GET', `/staff/conversations/${cid}`);
    expect(detail.body.conversation).toMatchObject({ auto_reply: 'on', effective_mode: 'auto_allowed' });
    const list = await staff('GET', '/staff/conversations');
    expect(list.body.items.find((x: any) => x.id === cid)).toMatchObject({ auto_reply: 'on', effective_mode: 'auto_allowed' });
  });

  it('off: keeps the per-conversation mode and caps the conversation at approve_each under global auto_allowed', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const a = await consentedCustomer();
    const r = await setSwitch(a.cid, 'off');
    expect(r.status).toBe(200);
    expect(r.body.conversation).toMatchObject({ auto_reply: 'off', mode_override: null, effective_mode: 'approve_each' });
    expect(await switchOf(a.cid)).toEqual({ auto_reply: 'off', mode: null });
    expect(JSON.parse((await lastAudit('conversation.auto_reply'))!.after_json!)).toEqual({ auto_reply: 'off', mode: null });

    const b = await consentedCustomer();
    await setMode(b.cid, 'draft_only');
    const r2 = await setSwitch(b.cid, 'off');
    expect(r2.body.conversation).toMatchObject({ auto_reply: 'off', mode_override: 'draft_only', effective_mode: 'draft_only' });
    expect(await switchOf(b.cid)).toEqual({ auto_reply: 'off', mode: 'draft_only' });

    // a conversation without the switch still follows the global flag
    const c = await consentedCustomer();
    expect((await staff('GET', `/staff/conversations/${c.cid}`)).body.conversation.effective_mode).toBe('auto_allowed');
  });

  it('the global flag off wins over a switch that is on', async () => {
    const { cid } = await consentedCustomer();
    await setSwitch(cid, 'on');
    await setFlags({ auto_reply_mode: 'off' });
    expect((await staff('GET', `/staff/conversations/${cid}`)).body.conversation).toMatchObject({ auto_reply: 'on', effective_mode: 'off' });
    await setFlags({ auto_reply_mode: 'draft_only' });
    expect((await staff('GET', `/staff/conversations/${cid}`)).body.conversation).toMatchObject({ auto_reply: 'on', effective_mode: 'auto_allowed' });
  });

  it('PUT .../mode with a mode below auto_allowed turns a switch that is on to off, with its own audit row', async () => {
    for (const mode of ['approve_each', 'draft_only', 'off'] as const) {
      const { cid } = await consentedCustomer();
      await setSwitch(cid, 'on');
      const before = await auditCount('conversation.auto_reply');
      const r = await setMode(cid, mode);
      expect(r.status).toBe(200);
      expect(r.body.conversation).toMatchObject({ auto_reply: 'off', mode_override: mode, effective_mode: mode });
      expect(await switchOf(cid)).toEqual({ auto_reply: 'off', mode });
      expect(await auditCount('conversation.auto_reply')).toBe(before + 1);
      const audit = await lastAudit('conversation.auto_reply');
      expect(audit).toMatchObject({ actor_type: 'staff', entity_id: cid });
      expect(JSON.parse(audit!.before_json!)).toEqual({ auto_reply: 'on' });
      expect(JSON.parse(audit!.after_json!)).toEqual({ auto_reply: 'off', by: 'mode' });
    }
  });

  it('PUT .../mode with null or auto_allowed keeps a switch that is on, and never touches a switch that is off or unset', async () => {
    const a = await consentedCustomer();
    await setSwitch(a.cid, 'on');
    const before = await auditCount('conversation.auto_reply');
    expect((await setMode(a.cid, 'auto_allowed')).body.conversation).toMatchObject({ auto_reply: 'on', mode_override: 'auto_allowed', effective_mode: 'auto_allowed' });
    expect((await setMode(a.cid, null)).body.conversation).toMatchObject({ auto_reply: 'on', mode_override: null, effective_mode: 'auto_allowed' });
    expect(await auditCount('conversation.auto_reply')).toBe(before);

    const b = await consentedCustomer();
    await setSwitch(b.cid, 'off');
    expect((await setMode(b.cid, 'draft_only')).body.conversation).toMatchObject({ auto_reply: 'off', mode_override: 'draft_only' });
    expect(await auditCount('conversation.auto_reply')).toBe(before + 1); // only the row of setSwitch(b, 'off')

    const c = await consentedCustomer();
    const r = await setMode(c.cid, 'draft_only');
    expect(r.body.conversation).not.toHaveProperty('auto_reply');
    expect((await switchOf(c.cid)).auto_reply).toBeNull();
  });

  it('on is refused with 409 invalid_state for a manager or a staff member; off is still accepted', async () => {
    for (const role of ['manager', 'staff'] as const) {
      const threadId = thread();
      const put = await staff('PUT', `/staff/roles/${encodeURIComponent(zaloOf(threadId))}`, { role });
      expect(put.status).toBe(200);
      expect((await ingest(threadId, 'mai chị nghỉ nhé')).action).toBe('internal_contact');
      const conv = await convOf(threadId);
      const before = await auditCount('conversation.auto_reply');

      const on = await setSwitch(conv!.id, 'on');
      expect(on.status).toBe(409);
      expect(on.body.error.code).toBe('invalid_state');
      expect((await switchOf(conv!.id)).auto_reply).toBeNull();
      expect(await auditCount('conversation.auto_reply')).toBe(before);

      const off = await setSwitch(conv!.id, 'off');
      expect(off.status).toBe(200);
      expect(off.body.conversation).toMatchObject({ auto_reply: 'off', role, role_source: 'staff' });
    }
  });
});

describe('a conversation with the switch on', () => {
  it('auto-sends under the default global approve_each when every condition holds', async () => {
    const { cid } = await customerWithJob();
    expect((await setSwitch(cid, 'on')).status).toBe(200);
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(cid);
    expect(c.job.turn_context.conversation_mode).toBe('auto_allowed');
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.status).toBe(200);
    expect(d.body).toMatchObject({ status: 'sent', action: 'auto_sent' });
    expect(d.body.message_id).toMatch(/^msg_/);
    const out = await botOutbox(cid);
    expect(out).toHaveLength(1);
    expect(String(out[0]!.payload_json)).toContain('199.000đ');
  });

  it('a neighbour without the switch still waits for staff under the same global flag', async () => {
    const on = await customerWithJob();
    await setSwitch(on.cid, 'on');
    const first = await claim();
    expect(first.job.conversation.conversation_id).toBe(on.cid);
    await quoteGoiDau(first.job.job_id);
    expect((await runner(`/runner/jobs/${first.job.job_id}/draft`, draftBody(GOOD))).body.action).toBe('auto_sent');

    const plain = await customerWithJob();
    const second = await claim();
    expect(second.job.conversation.conversation_id).toBe(plain.cid);
    expect(second.job.turn_context.conversation_mode).toBe('approve_each');
    await quoteGoiDau(second.job.job_id);
    const d = await runner(`/runner/jobs/${second.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(await botOutbox(plain.cid)).toHaveLength(0);
  });

  it('waits as pending when the draft carries a menu image', async () => {
    const { cid } = await customerWithJob('cho xem menu tóc');
    await setSwitch(cid, 'on');
    const c = await claim();
    expect(c.job.turn_context.conversation_mode).toBe('auto_allowed');
    const img = await tool('attach_menu_images', c.job.job_id, { group: 'thu-gian-toc', service_id: 'none' });
    expect(img.body.is_error).toBe(false);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ em gửi anh/chị menu chăm sóc tóc ạ.'));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(d.body.checker.passed).toBe(true);
    expect(d.body.attachments.length).toBeGreaterThan(0);
    expect(await botOutbox(cid)).toHaveLength(0);
    expect(await botMessages(cid)).toHaveLength(0);
  });

  it('a draft the checker blocks is never sent', async () => {
    const { cid } = await customerWithJob();
    await setSwitch(cid, 'on');
    const c = await claim();
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody('Dạ gội đầu giá 150.000đ ạ.'));
    expect(d.body).toMatchObject({ status: 'blocked', action: 'queued_for_staff' });
    expect(d.body.checker.issues[0].rule).toBe('price');
    expect(await botOutbox(cid)).toHaveLength(0);
    expect(await botMessages(cid)).toHaveLength(0);
  });

  it('waits as pending when outbound_enabled is false, when staff took over and when the job handed off', async () => {
    const a = await customerWithJob();
    await setSwitch(a.cid, 'on');
    const c1 = await claim();
    await quoteGoiDau(c1.job.job_id);
    await setFlags({ outbound_enabled: false });
    const d1 = await runner(`/runner/jobs/${c1.job.job_id}/draft`, draftBody(GOOD));
    expect(d1.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(await botOutbox(a.cid)).toHaveLength(0);
    expect((await staff('POST', `/staff/drafts/${d1.body.draft_id}/approve`, {})).body.error.code).toBe('outbound_disabled');
    expect(await botOutbox(a.cid)).toHaveLength(0);
    await setFlags({ outbound_enabled: true });

    const b = await customerWithJob();
    await setSwitch(b.cid, 'on');
    const c2 = await claim();
    await quoteGoiDau(c2.job.job_id);
    await env.DB.prepare("UPDATE conversations SET bot_state = 'staff_takeover' WHERE id = ?").bind(b.cid).run();
    const d2 = await runner(`/runner/jobs/${c2.job.job_id}/draft`, draftBody(GOOD));
    expect(d2.body).toMatchObject({ status: 'pending', action: 'queued_for_staff' });
    expect(await botOutbox(b.cid)).toHaveLength(0);

    const h = await customerWithJob('cho mình gặp nhân viên');
    await setSwitch(h.cid, 'on');
    const c3 = await claim();
    const handoff = await tool('handoff_to_staff', c3.job.job_id, { reason_code: 'customer_request', urgency: 'normal', summary_for_staff: 'Khách muốn gặp nhân viên.' });
    expect(handoff.body.is_error).toBe(false);
    const d3 = await runner(`/runner/jobs/${c3.job.job_id}/draft`, draftBody('Dạ em báo nhân viên hỗ trợ mình ngay ạ.'));
    expect(d3.body.action).toBe('queued_for_staff');
    expect(await botOutbox(h.cid)).toHaveLength(0);
  });

  it('the switch turned off while the model was drafting keeps the draft for staff', async () => {
    const { cid } = await customerWithJob();
    await setSwitch(cid, 'on');
    const c = await claim();
    expect(c.job.turn_context.conversation_mode).toBe('auto_allowed');
    await quoteGoiDau(c.job.job_id);
    await setSwitch(cid, 'off');
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(await botOutbox(cid)).toHaveLength(0);
  });

  it('sends nothing when the global flag auto_reply_mode is off', async () => {
    // a job leased before the global flag went off: its draft is dropped and the heartbeat cancels the run
    const a = await customerWithJob();
    await setSwitch(a.cid, 'on');
    const c = await claim();
    expect(c.job.conversation.conversation_id).toBe(a.cid);
    await quoteGoiDau(c.job.job_id);
    await setFlags({ auto_reply_mode: 'off' });
    const hb = await runner(`/runner/jobs/${c.job.job_id}/heartbeat`);
    expect(hb.body).toMatchObject({ cancel: true, cancel_reason: 'flags_changed' });
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body.status).not.toBe('sent');
    expect(d.body.action).not.toBe('auto_sent');
    expect(await botOutbox(a.cid)).toHaveLength(0);
    expect(await botMessages(a.cid)).toHaveLength(0);

    // a new message under global off: no draft job at all
    const b = await consentedCustomer();
    await setSwitch(b.cid, 'on');
    await say(b.userId, 'gội đầu bao nhiêu tiền ạ');
    await fireDebounce(b.userId);
    expect((await jobsOf(b.cid)).filter((j) => j.status === 'queued' || j.status === 'leased')).toHaveLength(0);
    expect((await claim()).job).toBeNull();
    expect(await botOutbox(b.cid)).toHaveLength(0);
  });

  it('a draft of a still leased job is dropped when the global flag went off, whatever the switch says', async () => {
    const { cid } = await customerWithJob();
    await setSwitch(cid, 'on');
    const c = await claim();
    await quoteGoiDau(c.job.job_id);
    await setFlags({ auto_reply_mode: 'off' });
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.status).toBe(200);
    expect(d.body).toMatchObject({ status: 'discarded', action: 'dropped' });
    expect(await botOutbox(cid)).toHaveLength(0);
    expect(await botMessages(cid)).toHaveLength(0);
  });
});

describe('a conversation with the switch off', () => {
  it('waits for staff under global auto_allowed, and the approved draft is sent', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const { cid } = await customerWithJob();
    await setSwitch(cid, 'off');
    const c = await claim();
    expect(c.job.turn_context.conversation_mode).toBe('approve_each');
    await quoteGoiDau(c.job.job_id);
    const d = await runner(`/runner/jobs/${c.job.job_id}/draft`, draftBody(GOOD));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', message_id: null });
    expect(await botOutbox(cid)).toHaveLength(0);
    const ok = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
    expect(ok.status).toBe(200);
    expect(await botOutbox(cid)).toHaveLength(1);
  });
});
