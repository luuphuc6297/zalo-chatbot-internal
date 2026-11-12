// Personal Zalo channel: webhook auth (Bearer + HMAC), batch bodies, dedupe, group/non-message filtering, media
// placeholder + handoff, echo of bridge sends, staff takeover from the phone, typed consent, bridge outbox
// claim/lease/result semantics, and follow-up templates rendered as chat text.
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { sendButtons, sendText } from '../src/lib/zalo-client';
import { CONSENT_PROMPT_TEXT, CONSENT_REPLY_LINE_AGREE, CONSENT_REPLY_LINE_STAFF } from '../src/lib/fixed-messages';
import { consentReplyOf } from '../src/lib/zalo-personal';
import { MAX_SEND_ATTEMPTS } from '../src/bridge/outbox';
import { runCron } from '../src/scheduler/cron';
import type { Env, PersonalWebhookEvent } from '../src/types';

const SECRET = 'test-personal-webhook-secret';
const H = 3600 * 1000;
const T10_LOCAL = Date.UTC(2026, 10, 7, 3, 0); // 2026-11-07 10:00 Asia/Ho_Chi_Minh

let n = 0;
const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;
const thread = () => uniq('9100');

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

interface PostOpts {
  secret?: string;
  bearer?: string | null;
  signature?: string | null;
  env?: Partial<Env>;
  raw?: string;
}

async function postPersonal(body: unknown, opts: PostOpts = {}) {
  const raw = opts.raw ?? JSON.stringify(body);
  const secret = opts.secret ?? SECRET;
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (opts.bearer !== null) headers.authorization = `Bearer ${opts.bearer ?? secret}`;
  if (opts.signature !== null) headers['x-zalo-signature'] = opts.signature ?? `sha256=${await hmacHex(secret, raw)}`;
  const ctx = createExecutionContext();
  const res = await app.fetch(new Request('https://bot.test/zalo/personal/webhook', { method: 'POST', body: raw, headers }), { ...env, ...opts.env }, ctx);
  await waitOnExecutionContext(ctx);
  return { res, json: (await res.json()) as any };
}

function msgEvent(threadId: string, content: unknown, extra: Partial<PersonalWebhookEvent> = {}): PersonalWebhookEvent {
  return {
    event: 'message',
    accountId: 'acc-test',
    msgId: uniq('7700'),
    cliMsgId: uniq('cli'),
    threadId,
    type: 0,
    isSelf: false,
    uidFrom: threadId,
    dName: 'Chị Lan',
    msgType: typeof content === 'string' ? 'webchat' : 'chat.photo',
    content,
    ...extra,
  };
}

async function bridge(method: string, path: string, body?: unknown, opts: { bridgeId?: string | null; token?: string; env?: Partial<Env> } = {}) {
  const headers: Record<string, string> = { authorization: `Bearer ${opts.token ?? 'test-runner-token'}`, 'content-type': 'application/json' };
  if (opts.bridgeId !== null) headers['x-bridge-id'] = opts.bridgeId ?? 'bridge-1';
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, { method, headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }),
    { ...env, ...opts.env },
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

const claim = (e?: Partial<Env>) => bridge('POST', '/bridge/outbox/claim', {}, e ? { env: e } : {});
const report = (id: string, body: unknown, bridgeId = 'bridge-1') => bridge('POST', `/bridge/outbox/${id}/result`, body, { bridgeId });

async function conv(threadId: string) {
  return env.DB.prepare(
    "SELECT c.*, cu.display_name, cu.channel, cu.oa_id AS cu_oa FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?",
  )
    .bind(`p:${threadId}`)
    .first<Record<string, any>>();
}

async function messages(conversationId: string) {
  return (await env.DB.prepare('SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq').bind(conversationId).all<Record<string, any>>()).results;
}

async function outboxOf(threadId: string) {
  return (await env.DB.prepare("SELECT * FROM outbox WHERE channel = 'personal' AND thread_id = ? ORDER BY created_at, id").bind(threadId).all<Record<string, any>>()).results;
}

async function setFlag(name: string, value: unknown) {
  await env.DB.prepare('UPDATE flags SET value_json = ? WHERE name = ?').bind(JSON.stringify(value), name).run();
}

/** The bridge claims the next row (it must belong to this thread) and reports it sent. Returns the claim item. */
async function sendNext(threadId: string): Promise<any> {
  const c = await claim();
  expect(c.body.item?.thread_id).toBe(threadId);
  await report(c.body.item.id, { status: 'sent', zalo_msg_id: uniq('8800') });
  return c.body.item;
}

/** A new personal customer who typed "đồng ý" to the delivered consent prompt; the bridge sent both server messages. */
async function consentedThread(): Promise<{ threadId: string; cid: string }> {
  const threadId = thread();
  await postPersonal(msgEvent(threadId, 'chào shop'));
  await sendNext(threadId);
  await postPersonal(msgEvent(threadId, 'Đồng ý'));
  await sendNext(threadId);
  const c = await conv(threadId);
  expect(c!.bot_state).toBe('bot_active');
  return { threadId, cid: c!.id };
}

async function staffPost(path: string, body: unknown = {}) {
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, {
      method: 'POST',
      headers: { authorization: 'Bearer test-staff-token', 'x-staff-id': 'tester', 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

/** A bot reply waiting in the bridge queue, as an auto-sent draft leaves it (messages.source 'bot', no staff_id). */
async function queuedBotReply(threadId: string, cid: string, text = 'Dạ gội đầu thư giãn là 350.000đ ạ'): Promise<{ messageId: string; outboxId: string }> {
  const c = await conv(threadId);
  const messageId = uniq('msg_bot');
  const now = Date.now();
  await env.DB.prepare(
    "INSERT INTO messages (id, conversation_id, direction, source, kind, text, send_state, created_at, seq) VALUES (?, ?, 'outbound', 'bot', 'text', ?, 'pending', ?, (SELECT COALESCE(MAX(seq),0)+1 FROM messages WHERE conversation_id = ?))",
  )
    .bind(messageId, cid, text, now, cid)
    .run();
  const out = await sendText(env, `p:${threadId}`, text, { conversation_id: cid, customer_id: c!.customer_id, message_id: messageId, dedupe_key: uniq('k') });
  expect(out).toMatchObject({ ok: true, queued: true });
  return { messageId, outboxId: out.outbox_id };
}

beforeEach(async () => {
  await setFlag('outbound_enabled', true);
  await setFlag('scheduled_sends_enabled', false);
  // Rows left by earlier tests must not be handed out to this one.
  await env.DB.prepare("UPDATE outbox SET status = 'sent' WHERE channel = 'personal' AND status IN ('queued','leased')").run();
});

// ---------------------------------------------------------------- webhook auth

describe('POST /zalo/personal/webhook auth', () => {
  it('accepts a body with the right bearer and HMAC, and stores it under personal:<msgId>', async () => {
    const ev = msgEvent(thread(), 'gội đầu bao nhiêu tiền ạ');
    const { res, json } = await postPersonal(ev);
    expect(res.status).toBe(200);
    expect(json).toMatchObject({ ok: true, count: 1, results: [{ index: 0, event_key: `personal:${ev.msgId}`, status: 'accepted' }] });
    const row = await env.DB.prepare('SELECT * FROM events_inbox WHERE event_key = ?').bind(`personal:${ev.msgId}`).first<Record<string, any>>();
    expect(row).toMatchObject({ oa_id: 'personal', zalo_user_id: `p:${ev.threadId}`, signature_ok: 1, event_name: 'personal_message', status: 'processed' });
  });

  it('refuses a wrong bearer, a wrong signature, a missing header, or a server without a secret (401, nothing stored)', async () => {
    const ev = msgEvent(thread(), 'hi');
    const raw = JSON.stringify(ev);
    const badBearer = await postPersonal(ev, { bearer: 'not-the-secret' });
    expect(badBearer.res.status).toBe(401);
    expect(badBearer.json.error.code).toBe('unauthorized');
    const badSig = await postPersonal(ev, { signature: `sha256=${await hmacHex('other-secret', raw)}` });
    expect(badSig.res.status).toBe(401);
    expect(badSig.json.error.code).toBe('signature_invalid');
    // signature of a different body (one byte changed)
    const tampered = await postPersonal(ev, { signature: `sha256=${await hmacHex(SECRET, raw.replace('hi', 'ho'))}` });
    expect(tampered.json.error.code).toBe('signature_invalid');
    expect((await postPersonal(ev, { bearer: null })).res.status).toBe(401);
    expect((await postPersonal(ev, { signature: null })).res.status).toBe(401);
    expect((await postPersonal(ev, { env: { ZALO_PERSONAL_WEBHOOK_SECRET: '' } })).res.status).toBe(401);
    const stored = await env.DB.prepare('SELECT COUNT(*) AS n FROM events_inbox WHERE event_key = ?').bind(`personal:${ev.msgId}`).first<{ n: number }>();
    expect(stored!.n).toBe(0);
  });

  it('answers 400 to a body that is not JSON (the engine dead-letters it instead of retrying forever)', async () => {
    const r = await postPersonal(null, { raw: 'not json' });
    expect(r.res.status).toBe(400);
  });
});

// ---------------------------------------------------------------- body shapes, dedupe, filtering

describe('personal webhook bodies', () => {
  it('handles a batch: messages in order, group threads and non-message events ignored and not stored', async () => {
    const threadId = thread();
    const group = msgEvent(uniq('9200'), 'tin trong nhóm', { type: 1 });
    const batch = {
      event: 'batch',
      accountId: 'acc-test',
      count: 4,
      events: [msgEvent(threadId, 'chào shop'), group, { event: 'reaction', threadId, isSelf: false }, msgEvent(threadId, 'cho em hỏi giá')],
    };
    const { res, json } = await postPersonal(batch);
    expect(res.status).toBe(200);
    expect(json.results.map((r: any) => r.status)).toEqual(['accepted', 'ignored', 'ignored', 'accepted']);
    expect(json.results[1].reason).toBe('group_thread');
    expect(json.results[2].reason).toBe('not_message');
    const groupRow = await env.DB.prepare('SELECT COUNT(*) AS n FROM events_inbox WHERE event_key = ?').bind(`personal:${group.msgId}`).first<{ n: number }>();
    expect(groupRow!.n).toBe(0);
    const c = await conv(threadId);
    const msgs = await messages(c!.id);
    const inbound = msgs.filter((m) => m.direction === 'inbound').map((m) => m.text);
    expect(inbound).toEqual(['chào shop', 'cho em hỏi giá']);
    expect(c!.channel).toBe('personal');
    expect(c!.cu_oa).toBe('personal');
    expect(c!.display_name).toBe('Chị Lan');
  });

  it('ZALO_PERSONAL_ACCOUNT_ID set: events of another account are ignored', async () => {
    const ev = msgEvent(thread(), 'hi', { accountId: 'someone-else' });
    const { json } = await postPersonal({ event: 'batch', accountId: 'someone-else', count: 1, events: [{ ...ev, accountId: undefined }] }, { env: { ZALO_PERSONAL_ACCOUNT_ID: 'acc-test' } });
    expect(json.results[0]).toMatchObject({ status: 'ignored', reason: 'foreign_account' });
    const ok = await postPersonal(msgEvent(thread(), 'hi'), { env: { ZALO_PERSONAL_ACCOUNT_ID: 'acc-test' } });
    expect(ok.json.results[0].status).toBe('accepted');
  });

  it('a redelivered event (engine retry) is answered 200 as a duplicate and stored once', async () => {
    const ev = msgEvent(thread(), 'gội đầu bao nhiêu tiền ạ');
    const first = await postPersonal(ev);
    const again = await postPersonal(ev);
    expect(first.json.results[0].status).toBe('accepted');
    expect(again.res.status).toBe(200);
    expect(again.json.results[0].status).toBe('duplicate');
    const c = await conv(ev.threadId!);
    const inbound = (await messages(c!.id)).filter((m) => m.direction === 'inbound');
    expect(inbound).toHaveLength(1);
    // the consent prompt was queued once, not once per delivery
    expect(await outboxOf(ev.threadId!)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------- consent

describe('consent on the personal channel', () => {
  it('sends the consent prompt as text with reply instructions, and accepts a typed "đồng ý"', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const rows = await outboxOf(threadId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ zalo_mode: 'personal', status: 'queued', kind: 'cs_buttons', attempts: 0 });
    expect(rows[0]!.text).toBe(`${CONSENT_PROMPT_TEXT}\n${CONSENT_REPLY_LINE_AGREE}\n${CONSENT_REPLY_LINE_STAFF}`);
    const c0 = await conv(threadId);
    const prompt = (await messages(c0!.id)).find((m) => m.kind === 'buttons');
    expect(prompt).toMatchObject({ send_state: 'pending', text: rows[0]!.text });

    await sendNext(threadId); // the customer can answer only once the prompt reached the phone
    await postPersonal(msgEvent(threadId, 'Đồng ý ạ!'));
    const c = await conv(threadId);
    expect(c!.bot_state).toBe('bot_active');
    const consent = await env.DB.prepare("SELECT status, source FROM consents WHERE customer_id = ? AND purpose = 'ai_assistant'").bind(c!.customer_id).first<Record<string, string>>();
    expect(consent).toEqual({ status: 'granted', source: 'chat_keyword' });
    expect(await outboxOf(threadId)).toHaveLength(2); // prompt + "cảm ơn anh/chị đã đồng ý"
  });

  it('a typed "gặp nhân viên" means staff only; "ok" or "không đồng ý" is not consent', async () => {
    expect(consentReplyOf('ok', true)).toBeNull();
    expect(consentReplyOf('không đồng ý', true)).toBeNull();
    expect(consentReplyOf('dong y', true)).toBe('agree');
    expect(consentReplyOf('OK đồng ý', true)).toBe('agree');
    expect(consentReplyOf('đồng ý', false)).toBeNull(); // OA keeps buttons only
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    await postPersonal(msgEvent(threadId, 'ok'));
    expect((await conv(threadId))!.bot_state).toBe('awaiting_consent');
    await postPersonal(msgEvent(threadId, 'Gặp nhân viên'));
    const c = await conv(threadId);
    expect(c!.bot_state).toBe('staff_only');
    const h = await env.DB.prepare('SELECT reason_code FROM handoffs WHERE conversation_id = ?').bind(c!.id).first<{ reason_code: string }>();
    expect(h!.reason_code).toBe('customer_declined_ai');
  });
});

// ---------------------------------------------------------------- media

describe('attachments', () => {
  it('a photo is stored with a placeholder text and hands the conversation to staff (unsupported_message)', async () => {
    const { threadId, cid } = await consentedThread();
    const photo = msgEvent(threadId, { title: '', href: 'https://photo.test/a.jpg', thumb: 'https://photo.test/a_t.jpg' }, { msgType: 'chat.photo' });
    await postPersonal(photo);
    const msg = (await messages(cid)).find((m) => m.zalo_msg_id === photo.msgId);
    expect(msg).toMatchObject({ direction: 'inbound', kind: 'image', text: '[hình ảnh]' });
    expect(JSON.parse(msg!.attachments_json)).toEqual([{ type: 'image', url: 'https://photo.test/a.jpg', thumbnail: 'https://photo.test/a_t.jpg' }]);
    const h = await env.DB.prepare("SELECT reason_code, status FROM handoffs WHERE conversation_id = ? AND reason_code = 'unsupported_message'").bind(cid).first<Record<string, string>>();
    expect(h).toEqual({ reason_code: 'unsupported_message', status: 'open' });
    // the bot does not answer a placeholder: no debounce was armed for it
    expect((await conv(threadId))!.needs_attention).toBe(1);
  });
});

// ---------------------------------------------------------------- self-sent messages

describe('self-sent messages (isSelf)', () => {
  it('the echo of a message the bridge sent is ignored and confirms the send', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const c1 = await claim();
    const item = c1.body.item;
    expect(item).toMatchObject({ thread_id: threadId, thread_type: 0, attempt: 1, kind: 'cs_buttons' });
    // the echo arrives before the bridge reports its result
    const echo = msgEvent(threadId, item.text, { isSelf: true, dName: 'thom house', uidFrom: '0' });
    await postPersonal(echo);
    const inbox = await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(`personal:${echo.msgId}`).first<Record<string, string>>();
    expect(inbox).toEqual({ status: 'ignored', error: `echo:${item.id}` });
    const row = (await outboxOf(threadId))[0]!;
    expect(row).toMatchObject({ status: 'sent', echo_msg_id: echo.msgId });
    const c = await conv(threadId);
    expect(c!.bot_state).toBe('awaiting_consent'); // not a staff takeover
    expect((await messages(c!.id)).find((m) => m.kind === 'buttons')!.send_state).toBe('sent');
    // the bridge's late result does not change anything
    const late = await report(item.id, { status: 'failed', error: 'timeout' });
    expect(late.status).toBe(200);
    expect(late.body).toMatchObject({ status: 'sent', ignored: true });
  });

  it('a recovered echo (catch-up) is matched by msgId after the bridge reported it', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    const zid = uniq('8800');
    await report(item.id, { status: 'sent', zalo_msg_id: zid });
    // older than both text windows: only the msgId can match
    await env.DB.prepare('UPDATE outbox SET last_claimed_at = ? WHERE id = ?').bind(Date.now() - 30 * H, item.id).run();
    await postPersonal(msgEvent(threadId, item.text, { isSelf: true, msgId: zid, catchUp: true }));
    const inbox = await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(`personal:${zid}`).first<Record<string, string>>();
    expect(inbox).toEqual({ status: 'ignored', error: `echo:${item.id}` });
    expect((await conv(threadId))!.bot_state).toBe('awaiting_consent');
  });

  it('the same text typed again later by staff is not taken for an echo (each send matches one echo)', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    await postPersonal(msgEvent(threadId, item.text, { isSelf: true }));
    expect((await conv(threadId))!.bot_state).toBe('awaiting_consent');
    await postPersonal(msgEvent(threadId, item.text, { isSelf: true }));
    expect((await conv(threadId))!.bot_state).toBe('staff_takeover');
  });

  it('a self-sent message that matches no bridge send is staff typing on the phone: staff message + takeover', async () => {
    const { threadId, cid } = await consentedThread();
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    const staffMsg = msgEvent(threadId, 'Dạ chị đợi em kiểm tra lịch nhé', { isSelf: true, dName: 'thom house', uidFrom: '0' });
    await postPersonal(staffMsg);
    const c = await conv(threadId);
    expect(c!.bot_state).toBe('staff_takeover');
    expect(c!.takeover_by).toBe('zalo_phone');
    expect(c!.display_name).toBe('Chị Lan'); // the owner's dName on a self message is not the customer's name
    const m = (await messages(cid)).find((x) => x.zalo_msg_id === staffMsg.msgId);
    expect(m).toMatchObject({ direction: 'outbound', source: 'staff', staff_id: 'zalo_phone', text: 'Dạ chị đợi em kiểm tra lịch nhé', send_state: 'sent' });
  });
});

// ---------------------------------------------------------------- bridge API

describe('bridge outbox API', () => {
  it('needs the runner token and an X-Bridge-Id', async () => {
    expect((await bridge('POST', '/bridge/outbox/claim', {}, { token: 'wrong' })).status).toBe(401);
    expect((await bridge('POST', '/bridge/outbox/claim', {}, { bridgeId: null })).status).toBe(400);
    const st = await bridge('GET', '/bridge/status', undefined, { token: 'test-staff-token', bridgeId: null });
    expect(st.status).toBe(200);
    expect(st.body).toHaveProperty('counts.queued');
  });

  it('claim leases the oldest row for 60 s; result sent marks the outbox row and the message', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const before = Date.now();
    const c = await claim();
    expect(c.status).toBe(200);
    const item = c.body.item;
    expect(item.thread_id).toBe(threadId);
    expect(item.text.startsWith(CONSENT_PROMPT_TEXT)).toBe(true);
    expect(item.lease_until).toBeGreaterThanOrEqual(before + 60_000);
    expect(item.lease_until).toBeLessThanOrEqual(Date.now() + 60_000);
    // leased: nothing else to claim
    expect((await claim()).body).toMatchObject({ item: null, reason: 'no_work' });
    // another bridge cannot report a failure on this lease
    expect((await report(item.id, { status: 'failed', error: 'x' }, 'bridge-2')).body.error.code).toBe('lease_not_owned');
    const zid = uniq('8800');
    const r = await report(item.id, { status: 'sent', zalo_msg_id: zid, attempt: 1 });
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ id: item.id, status: 'sent', attempts: 1, ignored: false });
    const msg = (await messages((await conv(threadId))!.id)).find((m) => m.kind === 'buttons');
    expect(msg).toMatchObject({ send_state: 'sent', zalo_msg_id: zid });
    const st = await bridge('GET', '/bridge/status');
    expect(st.body.last_claim_at).toBeGreaterThanOrEqual(before);
    expect(st.body.bridges.find((b: any) => b.bridge_id === 'bridge-1')).toBeTruthy();
  });

  it('keeps per-thread order: a later row waits while an earlier one of the same thread is queued or leased', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    await postPersonal(msgEvent(threadId, 'gặp nhân viên')); // queues the "staff will reply" text after the prompt
    const rows = await outboxOf(threadId);
    expect(rows).toHaveLength(2);
    const first = (await claim()).body.item;
    expect(first.id).toBe(rows[0]!.id);
    expect((await claim()).body.item).toBeNull();
    await report(first.id, { status: 'sent', zalo_msg_id: uniq('8800') });
    expect((await claim()).body.item.id).toBe(rows[1]!.id);
  });

  it('failed is retried with backoff up to the attempt limit, then final; the message becomes failed', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    let item = (await claim()).body.item;
    const r1 = await report(item.id, { status: 'failed', error: 'zalo error 114' });
    expect(r1.body).toMatchObject({ status: 'queued', attempts: 1 });
    expect(r1.body.next_attempt_at).toBeGreaterThan(Date.now());
    expect((await claim()).body.item).toBeNull(); // backoff not over
    for (let attempt = 2; attempt <= MAX_SEND_ATTEMPTS; attempt++) {
      await env.DB.prepare('UPDATE outbox SET next_attempt_at = ? WHERE id = ?').bind(Date.now() - 1, item.id).run();
      item = (await claim()).body.item;
      expect(item.attempt).toBe(attempt);
      const r = await report(item.id, { status: 'failed', error: 'zalo error 114' });
      expect(r.body.status).toBe(attempt < MAX_SEND_ATTEMPTS ? 'queued' : 'failed');
    }
    expect((await claim()).body.item).toBeNull();
    const c = await conv(threadId);
    const msg = (await messages(c!.id)).find((m) => m.kind === 'buttons');
    expect(msg!.send_state).toBe('failed');
    expect(c!.needs_attention).toBe(1);
  });

  it('unknown is final and never handed out again; staff can requeue it', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    expect(item.requeued_at).toBeNull();
    const r = await report(item.id, { status: 'unknown', error: 'msg send timed out' });
    expect(r.body).toMatchObject({ status: 'unknown', ignored: false });
    expect((await claim()).body.item).toBeNull();
    expect((await report(item.id, { status: 'unknown' })).body.ignored).toBe(true); // repeated report
    expect((await report(item.id, { status: 'failed' })).status).toBe(409);
    const msg = (await messages((await conv(threadId))!.id)).find((m) => m.kind === 'buttons');
    expect(msg!.send_state).toBe('unknown');
    // staff decides
    const ctx = createExecutionContext();
    const res = await app.fetch(
      new Request(`https://bot.test/staff/outbox/${item.id}/decide`, {
        method: 'POST',
        headers: { authorization: 'Bearer test-staff-token', 'content-type': 'application/json' },
        body: JSON.stringify({ action: 'requeue' }),
      }),
      env,
      ctx,
    );
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(200);
    const again = (await claim()).body.item;
    expect(again.id).toBe(item.id);
    expect(again.attempt).toBe(1);
    // the bridge journal already holds "unknown" for this id; requeued_at tells it this is a staff resend
    expect(again.requeued_at).toBeGreaterThan(0);
  });

  it('an expired lease can be claimed again (next attempt)', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const first = (await claim()).body.item;
    await env.DB.prepare('UPDATE outbox SET lease_until = ? WHERE id = ?').bind(Date.now() - 1, first.id).run();
    const second = (await claim()).body.item;
    expect(second.id).toBe(first.id);
    expect(second.attempt).toBe(2);
    expect(second.lease_until).toBeGreaterThan(Date.now());
    // the old attempt's failure no longer applies
    expect((await report(first.id, { status: 'failed', attempt: 1 })).body.error.code).toBe('lease_expired');
  });

  it('outbound_enabled=false: claim hands out nothing', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    await setFlag('outbound_enabled', false);
    expect((await claim()).body).toMatchObject({ item: null, reason: 'outbound_disabled' });
  });
});

// ---------------------------------------------------------------- client + scheduler

describe('zalo client and follow-ups on the personal channel', () => {
  it('ZALO_MODE=personal refuses an OA user; a personal user gets a queued row with button lines', async () => {
    const personalEnv = { ...env, ZALO_MODE: 'personal' as const };
    const oa = await sendText(personalEnv, uniq('oa'), 'hello', { conversation_id: null, customer_id: null, message_id: null, dedupe_key: uniq('k') });
    expect(oa).toMatchObject({ ok: false, unknown: false, error_code: 'channel_mismatch' });
    const threadId = thread();
    const out = await sendButtons(personalEnv, `p:${threadId}`, 'Chọn giúp em:', [
      { title: 'Đồng ý', type: 'oa.query.show', payload: '#dong_y_tro_ly_ai' },
      { title: 'Gặp nhân viên', type: 'oa.query.show', payload: '#gap_nhan_vien' },
    ], { conversation_id: null, customer_id: null, message_id: null, dedupe_key: uniq('k') });
    expect(out).toMatchObject({ ok: true, queued: true, zalo_msg_id: null });
    const row = (await outboxOf(threadId))[0]!;
    expect(row.text).toBe(`Chọn giúp em:\n${CONSENT_REPLY_LINE_AGREE}\n${CONSENT_REPLY_LINE_STAFF}`);
  });

  it('a thank_you follow-up is queued as the chat version of the template', async () => {
    const threadId = thread();
    const now = T10_LOCAL - 30 * H;
    const ids = { cus: uniq('cus_'), cnv: uniq('cnv_'), vis: uniq('vis_'), job: uniq('job_') };
    await env.DB.batch([
      env.DB.prepare("INSERT INTO customers (id, oa_id, zalo_user_id, display_name, channel, created_at) VALUES (?, 'personal', ?, 'Lan', 'personal', ?)").bind(ids.cus, `p:${threadId}`, now),
      env.DB.prepare("INSERT INTO conversations (id, customer_id, oa_id, bot_state, created_at, updated_at) VALUES (?, ?, 'personal', 'bot_active', ?, ?)").bind(ids.cnv, ids.cus, now, now),
      env.DB.prepare("INSERT INTO visits (id, customer_id, service_id, visited_at, created_at) VALUES (?, ?, 'goi-dau-thu-gian', ?, ?)").bind(ids.vis, ids.cus, now, now),
      env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, recorded_at) VALUES (?, ?, 'followup_care', 'granted', 'button', ?)").bind(uniq('cns_'), ids.cus, now),
      env.DB.prepare(
        "INSERT INTO jobs (id, type, conversation_id, customer_id, status, run_at, max_lateness_ms, payload_json, dedupe_key, created_at, updated_at) VALUES (?, 'thank_you', ?, ?, 'queued', ?, ?, ?, ?, ?, ?)",
      ).bind(ids.job, ids.cnv, ids.cus, T10_LOCAL - 60_000, 6 * H, JSON.stringify({ visit_id: ids.vis }), `${ids.vis}:thank_you`, now, now),
    ]);
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, T10_LOCAL);
    const job = await env.DB.prepare('SELECT status FROM jobs WHERE id = ?').bind(ids.job).first<{ status: string }>();
    expect(job!.status).toBe('done');
    const rows = await outboxOf(threadId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: 'zbs_template', status: 'queued', template_key: 'thank_you', dedupe_key: `job:${ids.job}` });
    const text = String(rows[0]!.text);
    expect(text.startsWith('Dạ em chào Lan, em là trợ lý AI của thom house. Cảm ơn anh/chị đã ghé làm goi-dau-thu-gian hôm 06/11/2026 ạ.')).toBe(true);
    expect(text).toContain('nhắn "Ngừng" giúp em ạ.');
    expect(text).not.toContain('{');
    expect(text).not.toContain('<');
    expect(text.split('\n')).toHaveLength(4); // the empty aftercare line is dropped
    const msg = (await messages(ids.cnv))[0]!;
    expect(msg).toMatchObject({ kind: 'template', send_state: 'pending', text });
    // the bridge sends it; the message follows
    const item = (await claim()).body.item;
    expect(item.id).toBe(rows[0]!.id);
    await report(item.id, { status: 'sent', zalo_msg_id: uniq('8800') });
    expect((await messages(ids.cnv))[0]!.send_state).toBe('sent');
  });
});

// ---------------------------------------------------------------- contacts that are not customers

async function consentCount(threadId: string): Promise<number> {
  const c = await conv(threadId);
  const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM consents WHERE customer_id = ? AND purpose = 'ai_assistant'").bind(c!.customer_id).first<{ n: number }>();
  return r!.n;
}

const phoneMsg = (threadId: string, text: string, extra: Partial<PersonalWebhookEvent> = {}) =>
  msgEvent(threadId, text, { isSelf: true, uidFrom: '0', dName: 'thom house', ...extra });

describe('contacts that are not customers', () => {
  it('ZALO_PERSONAL_IGNORE_THREADS: a listed thread is ignored, never stored, never prompted', async () => {
    const threadId = thread();
    const ignore = { ZALO_PERSONAL_IGNORE_THREADS: `5550001, ${threadId}` };
    const { json } = await postPersonal(msgEvent(threadId, 'Con ơi tối nay về ăn cơm nhé'), { env: ignore });
    expect(json.results[0]).toMatchObject({ status: 'ignored', reason: 'ignored_thread' });
    const self = await postPersonal(phoneMsg(threadId, 'Dạ con về ạ'), { env: ignore });
    expect(self.json.results[0]).toMatchObject({ status: 'ignored', reason: 'ignored_thread' });
    expect(await conv(threadId)).toBeNull();
    expect(await outboxOf(threadId)).toHaveLength(0);
  });

  it("the account's chat with itself is ignored; a message from the account's own id is self-sent", async () => {
    const own = await postPersonal(msgEvent('acc-test', 'ghi chú cho mình', { uidFrom: 'acc-test' }));
    expect(own.json.results[0]).toMatchObject({ status: 'ignored', reason: 'own_thread' });
    expect(await conv('acc-test')).toBeNull();
    const { threadId, cid } = await consentedThread();
    // isSelf false but uidFrom is the account itself (a row restored from the offline queue): not a customer message
    const ev = msgEvent(threadId, 'Dạ em gửi chị lịch hẹn nhé', { isSelf: false, uidFrom: 'acc-test', dName: 'thom house' });
    await postPersonal(ev);
    const c = await conv(threadId);
    expect(c!.bot_state).toBe('staff_takeover');
    expect(c!.display_name).toBe('Chị Lan');
    expect((await messages(cid)).find((x) => x.zalo_msg_id === ev.msgId)).toMatchObject({ direction: 'outbound', source: 'staff' });
  });

  it('staff marks a conversation staff_only: no handoff, the queued consent prompt is cancelled, "đồng ý" is not consent', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào con'));
    const cid = (await conv(threadId))!.id;
    const r = await staffPost(`/staff/conversations/${cid}/staff-only`);
    expect(r.status).toBe(200);
    expect(r.body.conversation.bot_state).toBe('staff_only');
    const h = await env.DB.prepare('SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ?').bind(cid).first<{ n: number }>();
    expect(h!.n).toBe(0);
    expect((await outboxOf(threadId))[0]).toMatchObject({ status: 'failed', error: 'cancelled: marked staff_only by staff' });
    expect((await messages(cid)).find((m) => m.kind === 'buttons')!.send_state).toBe('failed');
    expect((await claim()).body.item).toBeNull();
    await postPersonal(msgEvent(threadId, 'Đồng ý'));
    expect((await conv(threadId))!.bot_state).toBe('staff_only');
    expect(await consentCount(threadId)).toBe(0);
    expect(await outboxOf(threadId)).toHaveLength(1);
    // marked by mistake: release undoes it (no consent yet, so back to awaiting_consent)
    const back = await staffPost(`/staff/conversations/${cid}/release`);
    expect(back.status).toBe(200);
    expect(back.body.conversation.bot_state).toBe('awaiting_consent');
  });
});

// ---------------------------------------------------------------- consent prompt repetition and typed consent

describe('consent prompt on the personal channel', () => {
  it('is not queued again a few days later, only after 30 days', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    await sendNext(threadId);
    const cid = (await conv(threadId))!.id;
    const age = (ms: number) =>
      env.DB.prepare("UPDATE messages SET created_at = created_at - ?, sent_at = sent_at - ? WHERE conversation_id = ? AND kind = 'buttons'").bind(ms, ms, cid).run();
    await age(2 * 24 * H);
    await postPersonal(msgEvent(threadId, 'shop ơi'));
    expect(await outboxOf(threadId)).toHaveLength(1);
    expect((await conv(threadId))!.needs_attention).toBe(1);
    await age(29 * 24 * H);
    await postPersonal(msgEvent(threadId, 'alo shop'));
    expect(await outboxOf(threadId)).toHaveLength(2);
  });

  it('a prompt whose send ended unknown counts as asked', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    await report(item.id, { status: 'unknown', error: 'timeout' });
    await postPersonal(msgEvent(threadId, 'shop ơi'));
    await postPersonal(msgEvent(threadId, 'alo'));
    expect(await outboxOf(threadId)).toHaveLength(1);
  });

  it('three messages of a new customer arriving together queue one prompt (ingest runs one at a time)', async () => {
    const threadId = thread();
    await Promise.all([
      postPersonal(msgEvent(threadId, 'chào shop')),
      postPersonal(msgEvent(threadId, 'cho em hỏi')),
      postPersonal(msgEvent(threadId, 'giá gội đầu bao nhiêu ạ')),
    ]);
    const c = await conv(threadId);
    expect((await messages(c!.id)).filter((m) => m.direction === 'inbound')).toHaveLength(3);
    expect(await outboxOf(threadId)).toHaveLength(1);
  });

  it('no prompt to a contact the owner wrote to first; the expired takeover returns to awaiting_consent, not bot_active', async () => {
    const threadId = thread();
    await postPersonal(phoneMsg(threadId, 'Chào chị, em bên thom house xác nhận lịch hẹn chiều mai ạ'));
    let c = await conv(threadId);
    expect(c!.bot_state).toBe('staff_takeover');
    await env.DB.prepare('UPDATE conversations SET takeover_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    c = await conv(threadId);
    expect(c!.bot_state).toBe('awaiting_consent');
    expect(c!.needs_attention).toBe(1);
    expect(await outboxOf(threadId)).toHaveLength(0);
  });

  it('after staff releases a conversation the owner started, the next customer message gets the consent prompt', async () => {
    const threadId = thread();
    await postPersonal(phoneMsg(threadId, 'Chào chị, em bên thom house ạ'));
    await postPersonal(msgEvent(threadId, 'dạ chào em'));
    let c = await conv(threadId);
    expect(c!.bot_state).toBe('staff_takeover');
    expect(await outboxOf(threadId)).toHaveLength(0);
    const res = await staffPost(`/staff/conversations/${c!.id}/release`);
    expect(res.status).toBe(200);
    c = await conv(threadId);
    expect(c!.bot_state).toBe('awaiting_consent');
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    const rows = await outboxOf(threadId);
    expect(rows).toHaveLength(1);
  });

  it('an expired takeover of a consented customer returns to bot_active', async () => {
    const { threadId, cid } = await consentedThread();
    await postPersonal(phoneMsg(threadId, 'Dạ chị đợi em chút ạ'));
    expect((await conv(threadId))!.bot_state).toBe('staff_takeover');
    await env.DB.prepare('UPDATE conversations SET takeover_until = ? WHERE id = ?').bind(Date.now() - 1, cid).run();
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    expect((await conv(threadId))!.bot_state).toBe('bot_active');
  });

  it('a typed "đồng ý" counts only as the answer to a delivered prompt that is the latest message, within 24 h', async () => {
    const t1 = thread();
    await postPersonal(msgEvent(t1, 'chào shop'));
    await postPersonal(msgEvent(t1, 'đồng ý')); // the prompt is still waiting for the bridge
    expect((await conv(t1))!.bot_state).toBe('awaiting_consent');
    await sendNext(t1);
    const cid1 = (await conv(t1))!.id;
    await env.DB.prepare("UPDATE messages SET sent_at = sent_at - ? WHERE conversation_id = ? AND kind = 'buttons'").bind(25 * H, cid1).run();
    await postPersonal(msgEvent(t1, 'đồng ý')); // delivered more than 24 h ago
    expect((await conv(t1))!.bot_state).toBe('awaiting_consent');
    expect(await consentCount(t1)).toBe(0);

    const t2 = thread();
    await postPersonal(msgEvent(t2, 'chào shop'));
    await sendNext(t2);
    await postPersonal(msgEvent(t2, 'gặp nhân viên'));
    await sendNext(t2);
    await postPersonal(msgEvent(t2, 'Đồng ý')); // the latest message sent is "nhân viên sẽ trả lời", not the prompt
    expect((await conv(t2))!.bot_state).toBe('staff_only');
    expect(await consentCount(t2)).toBe(0);
  });
});

// ---------------------------------------------------------------- queued bot replies after staff steps in

describe('queued bot replies after staff steps in', () => {
  it('staff typing on the phone cancels the bot reply waiting in the bridge queue', async () => {
    const { threadId, cid } = await consentedThread();
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    const bot = await queuedBotReply(threadId, cid);
    await postPersonal(phoneMsg(threadId, 'Dạ chị ơi giá 350k ạ'));
    expect((await conv(threadId))!.bot_state).toBe('staff_takeover');
    const row = (await outboxOf(threadId)).find((r) => r.id === bot.outboxId)!;
    expect(row).toMatchObject({ status: 'failed', error: 'cancelled: conversation is staff_takeover' });
    expect((await messages(cid)).find((m) => m.id === bot.messageId)!.send_state).toBe('failed');
    expect((await claim()).body.item).toBeNull();
  });

  it('claim cancels a queued bot reply of a conversation that left bot_active by any path, and keeps staff rows', async () => {
    const { threadId, cid } = await consentedThread();
    const bot = await queuedBotReply(threadId, cid);
    await env.DB.prepare("UPDATE conversations SET bot_state = 'handoff_requested' WHERE id = ?").bind(cid).run();
    const staffSend = await staffPost(`/staff/conversations/${cid}/send`, { text: 'Dạ em là nhân viên thom house ạ', keep_bot_active: true });
    expect(staffSend.status).toBe(200);
    const item = (await claim()).body.item;
    expect(item.id).toBe(staffSend.body.outbox_id);
    expect((await outboxOf(threadId)).find((r) => r.id === bot.outboxId)).toMatchObject({ status: 'failed', error: 'cancelled: conversation is handoff_requested' });
  });
});

// ---------------------------------------------------------------- send limits

describe('send limits of the personal account', () => {
  it('an automatic row queued longer than 30 min is not sent (failed, expired_in_queue); a staff requeue sends it', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const row0 = (await outboxOf(threadId))[0]!;
    await env.DB.prepare('UPDATE outbox SET created_at = ? WHERE id = ?').bind(Date.now() - 31 * 60_000, row0.id).run();
    expect((await claim()).body.item).toBeNull();
    const row = (await outboxOf(threadId))[0]!;
    expect(row.status).toBe('failed');
    expect(String(row.error)).toMatch(/^expired_in_queue/);
    const c = await conv(threadId);
    expect((await messages(c!.id)).find((m) => m.kind === 'buttons')!.send_state).toBe('failed');
    expect(c!.needs_attention).toBe(1);
    expect((await staffPost(`/staff/outbox/${row0.id}/decide`, { action: 'requeue' })).status).toBe(200);
    expect((await claim()).body.item.id).toBe(row0.id);
  });

  it('hourly limit: automatic rows wait (rate_limited); a staff message still goes out', async () => {
    await env.DB.prepare("UPDATE outbox SET last_claimed_at = last_claimed_at - ? WHERE channel = 'personal' AND last_claimed_at IS NOT NULL").bind(2 * H).run();
    const limits = { PERSONAL_SEND_MAX_PER_HOUR: '2' };
    const [a, b, d] = [thread(), thread(), thread()];
    for (const t of [a, b, d]) await postPersonal(msgEvent(t, 'chào shop'));
    for (const t of [a, b]) {
      const c = await claim(limits);
      expect(c.body.item.thread_id).toBe(t);
      await report(c.body.item.id, { status: 'sent', zalo_msg_id: uniq('8800') });
    }
    const held = await claim(limits);
    expect(held.body).toMatchObject({ item: null, reason: 'rate_limited' });
    expect(held.body.poll_after_ms).toBeGreaterThanOrEqual(5000);
    expect(held.body.poll_after_ms).toBeLessThanOrEqual(60_000);
    const s = await staffPost(`/staff/conversations/${(await conv(a))!.id}/send`, { text: 'Dạ em chào chị ạ' });
    expect(s.status).toBe(200);
    expect((await claim(limits)).body.item.id).toBe(s.body.outbox_id);
    expect((await outboxOf(d))[0]!.status).toBe('queued');
  });

  it('per-thread gap: a second row to the same thread waits PERSONAL_THREAD_MIN_GAP_MS after the previous claim', async () => {
    const limits = { PERSONAL_THREAD_MIN_GAP_MS: '60000' };
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    await postPersonal(msgEvent(threadId, 'gặp nhân viên'));
    const first = (await claim(limits)).body.item;
    await report(first.id, { status: 'sent', zalo_msg_id: uniq('8800') });
    expect((await claim(limits)).body.item).toBeNull();
    await env.DB.prepare('UPDATE outbox SET last_claimed_at = ? WHERE id = ?').bind(Date.now() - 61_000, first.id).run();
    expect((await claim(limits)).body.item.thread_id).toBe(threadId);
  });
});

// ---------------------------------------------------------------- echo matching

describe('echo matching (late and split sends)', () => {
  it('an echo delivered hours late (Mac asleep) still matches the unreported send instead of a takeover', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    await env.DB.prepare('UPDATE outbox SET last_claimed_at = ? WHERE id = ?').bind(Date.now() - 3 * H, item.id).run();
    const echo = phoneMsg(threadId, item.text);
    await postPersonal(echo);
    const inbox = await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(`personal:${echo.msgId}`).first<Record<string, string>>();
    expect(inbox).toEqual({ status: 'ignored', error: `echo:${item.id}` });
    expect((await conv(threadId))!.bot_state).toBe('awaiting_consent');
  });

  it('a split send reports every part id; the echo of a short last part is matched by id', async () => {
    const threadId = thread();
    await postPersonal(msgEvent(threadId, 'chào shop'));
    const item = (await claim()).body.item;
    const [p1, p2] = [uniq('8800'), uniq('8800')];
    expect((await report(item.id, { status: 'sent', zalo_msg_id: p1, part_msg_ids: [p1, p2] })).status).toBe(200);
    const echo = phoneMsg(threadId, 'ạ.', { msgId: p2 });
    await postPersonal(echo);
    const inbox = await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(`personal:${p2}`).first<Record<string, string>>();
    expect(inbox).toEqual({ status: 'ignored', error: `echo:${item.id}` });
    expect((await conv(threadId))!.bot_state).toBe('awaiting_consent');
    expect((await report(item.id, { status: 'sent', part_msg_ids: ['not an id!'] })).status).toBe(422);
  });
});
