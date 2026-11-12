// Shared helpers of the section 14 pipeline tests (auto reply switch, internal contacts, rooms feed, the tool
// get_customer_profile): a personal-channel contact that writes through the webhook, the bridge that delivers the
// queue, and a leased draft job. Every name, phone number, id and text is synthetic.
import { createExecutionContext, env, runDurableObjectAlarm, runInDurableObject, waitOnExecutionContext } from 'cloudflare:test';
import { expect } from 'vitest';
import { app } from '../src/index';
import { conversationObjectName, type IngestResult, type NormalizedEvent, type PersonalWebhookEvent } from '../src/types';
import { PERSONAL_OA_ID } from '../src/lib/zalo-personal';
import { claim } from './core-helpers';

const SECRET = 'test-personal-webhook-secret';
let n = 0;
const seq = () => String(++n).padStart(4, '0');
/** A thread id made of digits only, so 'p:' + thread is a valid id for the roles endpoints. */
export const thread = () => `94${Date.now().toString().slice(-8)}${seq()}`;
export const zaloOf = (threadId: string) => `p:${threadId}`;

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function call(method: string, path: string, raw: string | undefined, headers: Record<string, string>) {
  const ctx = createExecutionContext();
  const res = await app.fetch(new Request(`https://bot.test${path}`, { method, headers: { 'content-type': 'application/json', ...headers }, ...(raw === undefined ? {} : { body: raw }) }), env, ctx);
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

export function msgEvent(threadId: string, content: unknown, extra: Partial<PersonalWebhookEvent> = {}): PersonalWebhookEvent {
  return {
    event: 'message',
    accountId: 'acc-test',
    msgId: `7700${Date.now().toString().slice(-8)}${seq()}`,
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

/** One signed event to POST /zalo/personal/webhook. */
export async function postPersonal(ev: PersonalWebhookEvent) {
  const raw = JSON.stringify(ev);
  return call('POST', '/zalo/personal/webhook', raw, { authorization: `Bearer ${SECRET}`, 'x-zalo-signature': `sha256=${await hmacHex(SECRET, raw)}` });
}

/** The contact writes one text. Returns the webhook response. */
export const write = (threadId: string, text: string, extra: Partial<PersonalWebhookEvent> = {}) => postPersonal(msgEvent(threadId, text, extra));

export const stubOf = (threadId: string) => env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName(PERSONAL_OA_ID, zaloOf(threadId))));

/** The contact writes one text, handed straight to the conversation object: returns what ingest answered. */
export async function ingest(threadId: string, text: string, displayName = 'Chị Lan'): Promise<IngestResult> {
  const msgId = `7700${Date.now().toString().slice(-8)}${seq()}`;
  const ev: NormalizedEvent = {
    event_key: `personal:test:${msgId}`,
    event_name: 'personal_message',
    kind: 'customer_message',
    oa_id: PERSONAL_OA_ID,
    zalo_user_id: zaloOf(threadId),
    zalo_msg_id: msgId,
    zalo_timestamp: Date.now(),
    text,
    message_kind: 'text',
    attachments: [],
    signature_ok: true,
    channel: 'personal',
    display_name: displayName,
  };
  return (await stubOf(threadId).ingestEvent(ev)) as IngestResult;
}

export const bridge = (path: string, body: unknown = {}) =>
  call('POST', path, JSON.stringify(body), { authorization: 'Bearer test-runner-token', 'x-bridge-id': 'bridge-1' });

/** The bridge claims the next row (it must belong to this thread) and reports it sent. Returns the claimed item. */
export async function sendNext(threadId: string): Promise<any> {
  const c = await bridge('/bridge/outbox/claim');
  expect(c.body.item?.thread_id).toBe(threadId);
  await bridge(`/bridge/outbox/${c.body.item.id}/result`, { status: 'sent', zalo_msg_id: `8800${Date.now().toString().slice(-8)}${seq()}` });
  return c.body.item;
}

/** Bridge rows and draft jobs left by earlier tests of the file must not be handed out to the next one. */
export async function settle() {
  await env.DB.batch([
    env.DB.prepare("UPDATE outbox SET status = 'sent' WHERE channel = 'personal' AND status IN ('queued','leased')"),
    env.DB.prepare("UPDATE jobs SET status = 'cancelled', last_error = 'test_cleanup' WHERE type = 'draft_reply' AND status IN ('queued','leased')"),
  ]);
}

export async function convOf(threadId: string) {
  return env.DB.prepare('SELECT c.* FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?').bind(zaloOf(threadId)).first<Record<string, any>>();
}

export async function messagesOf(conversationId: string) {
  return (await env.DB.prepare('SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq').bind(conversationId).all<Record<string, any>>()).results;
}

export async function outboxOf(threadId: string) {
  return (await env.DB.prepare("SELECT * FROM outbox WHERE channel = 'personal' AND thread_id = ? ORDER BY created_at, id").bind(threadId).all<Record<string, any>>()).results;
}

export interface PersonalContact {
  threadId: string;
  zalo: string;
  cid: string;
  customerId: string;
}

/** A new personal contact who typed "Đồng ý" to the delivered consent prompt; the bridge sent both server messages. */
export async function consentedThread(displayName = 'Chị Lan'): Promise<PersonalContact> {
  const threadId = thread();
  await write(threadId, 'chào shop', { dName: displayName });
  await sendNext(threadId);
  await write(threadId, 'Đồng ý', { dName: displayName });
  await sendNext(threadId);
  const c = await convOf(threadId);
  expect(c!.bot_state).toBe('bot_active');
  return { threadId, zalo: zaloOf(threadId), cid: c!.id, customerId: c!.customer_id };
}

/** Ends the debounce window now and fires the conversation alarm (enqueues the draft job when eligible). */
export async function fireDebounce(threadId: string): Promise<boolean> {
  const c = await convOf(threadId);
  await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
  return runDurableObjectAlarm(stubOf(threadId));
}

/**
 * Removes the debounce alarm of the conversation, so it never queues a draft job. The alarm otherwise fires on its own
 * DEBOUNCE_MS (10 s) after the last customer message; a slow run reaches that inside a later step or a later test, and
 * the job it queues is then leased by a claim meant for another conversation. The debounce window in D1 is left as is.
 */
export async function quietDebounce(threadId: string): Promise<void> {
  await runInDurableObject(stubOf(threadId), async (_obj, state) => {
    await state.storage.deleteAlarm();
  });
}

/** The contact asks a question and the debounce window ends: a draft job is queued when the conversation is eligible. */
export async function ask(threadId: string, text = 'gội đầu bao nhiêu tiền ạ') {
  const r = await write(threadId, text);
  expect(r.status).toBe(200);
  await fireDebounce(threadId);
}

/**
 * Leases the one queued draft job of this conversation. The claim endpoint hands out the queued job with the earliest
 * run_at, so the job is first moved before every other queued draft job: a job queued meanwhile for another
 * conversation (by a debounce alarm that fired on its own) stays queued instead of being leased here.
 */
export async function claimOwn(conversationId: string): Promise<any> {
  const own = await env.DB.prepare(
    "UPDATE jobs SET run_at = (SELECT COALESCE(MIN(j.run_at), 1) - 1 FROM jobs j WHERE j.type = 'draft_reply' AND j.status = 'queued') " +
      "WHERE conversation_id = ? AND type = 'draft_reply' AND status = 'queued' RETURNING id",
  )
    .bind(conversationId)
    .all();
  expect(own.results).toHaveLength(1);
  const c = await claim();
  expect(c.job?.conversation.conversation_id).toBe(conversationId);
  return c;
}

/** A consented personal contact with one question asked and its draft job leased by the runner. */
export async function personalJob(question = 'gội đầu bao nhiêu tiền ạ'): Promise<PersonalContact & { jobId: string; job: any }> {
  const p = await consentedThread();
  await ask(p.threadId, question);
  const c = await claimOwn(p.cid);
  return { ...p, jobId: c.job.job_id, job: c.job };
}

/** Bot and staff rows of the bridge queue for one conversation (the consent messages are source 'server'). */
export async function botOutbox(conversationId: string) {
  return (
    await env.DB.prepare("SELECT o.id, o.status, o.kind, o.text FROM outbox o JOIN messages m ON m.id = o.message_id WHERE o.conversation_id = ? AND m.source IN ('bot','staff') ORDER BY o.created_at, o.id")
      .bind(conversationId)
      .all<Record<string, any>>()
  ).results;
}
