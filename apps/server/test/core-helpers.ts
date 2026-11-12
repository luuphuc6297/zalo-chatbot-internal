// server-core test helpers: seed, runner/staff calls, and a conversation that already gave AI consent.
import { env, runDurableObjectAlarm, SELF } from 'cloudflare:test';
import { expect } from 'vitest';
import { conversationObjectName, type NormalizedEvent } from '../src/types';

export const OA = 'test-oa-id';
let n = 0;
export const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;

export async function seed(): Promise<{ catalog_version: string; prompt_hash: string }> {
  const res = await SELF.fetch('https://bot.test/dev/seed', { method: 'POST', body: '{}', headers: { authorization: 'Bearer test-staff-token' } });
  expect(res.status).toBe(200);
  // D1 is shared by the tests of one file: close draft jobs left by earlier tests so claim() takes this test's job.
  await env.DB.prepare("UPDATE jobs SET status = 'cancelled' WHERE type = 'draft_reply' AND status IN ('queued','leased')").run();
  await env.DB.prepare("UPDATE flags SET value_json = CASE name WHEN 'auto_reply_mode' THEN '\"approve_each\"' WHEN 'ai_engine' THEN '\"subscription\"' WHEN 'runner_desired_account' THEN '\"auto\"' WHEN 'ai_calls_enabled' THEN 'true' WHEN 'outbound_enabled' THEN 'true' ELSE 'false' END").run();
  return res.json();
}

export async function runner<T = any>(path: string, body: unknown = {}, runnerId = 'mac-1', method = 'POST'): Promise<{ status: number; body: T }> {
  const res = await SELF.fetch(`https://bot.test${path}`, {
    method,
    headers: { authorization: 'Bearer test-runner-token', 'x-runner-id': runnerId, 'content-type': 'application/json' },
    ...(method === 'GET' ? {} : { body: JSON.stringify(body) }),
  });
  return { status: res.status, body: (await res.json()) as T };
}

export async function staff<T = any>(method: string, path: string, body?: unknown): Promise<{ status: number; body: T }> {
  const res = await SELF.fetch(`https://bot.test${path}`, {
    method,
    headers: { authorization: 'Bearer test-staff-token', 'x-staff-id': 'tester', 'content-type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return { status: res.status, body: (await res.json()) as T };
}

export function stubFor(userId: string) {
  return env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName(OA, userId)));
}

export function textEvent(userId: string, text: string): NormalizedEvent {
  const msgId = uniq('m');
  return {
    event_key: `user_send_text:${msgId}`,
    event_name: 'user_send_text',
    kind: 'customer_message',
    oa_id: OA,
    zalo_user_id: userId,
    user_id_by_app: `app_${userId}`,
    zalo_msg_id: msgId,
    zalo_timestamp: Date.now(),
    text,
    message_kind: 'text',
    attachments: [],
    signature_ok: true,
  };
}

export async function say(userId: string, text: string) {
  return stubFor(userId).ingestEvent(textEvent(userId, text));
}

export async function conversationIdOf(userId: string): Promise<string> {
  const r = await env.DB.prepare('SELECT c.id FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?')
    .bind(userId)
    .first<{ id: string }>();
  return r!.id;
}

/** Ends the debounce window now and fires the DO alarm (enqueues the draft job when eligible). */
export async function fireDebounce(userId: string): Promise<boolean> {
  const cid = await conversationIdOf(userId);
  await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, cid).run();
  return runDurableObjectAlarm(stubFor(userId));
}

/** New customer who passed the consent gate. Returns the conversation id. */
export async function consentedCustomer(userId = uniq('u')): Promise<{ userId: string; cid: string }> {
  const first = await say(userId, 'chào shop');
  expect(first.action).toBe('consent_prompt_sent');
  const agree = await say(userId, '#dong_y_tro_ly_ai');
  expect(agree.action).toBe('consent_recorded');
  return { userId, cid: await conversationIdOf(userId) };
}

/** Consented customer with one question asked and a draft job queued. */
export async function customerWithJob(text = 'gội đầu bao nhiêu tiền ạ', userId = uniq('u')) {
  const c = await consentedCustomer(userId);
  const r = await say(c.userId, text);
  expect(r.action).toBe('debounced');
  await fireDebounce(c.userId);
  return c;
}

export async function claim(runnerId = 'mac-1') {
  const r = await runner('/runner/jobs/claim', {}, runnerId);
  expect(r.status).toBe(200);
  return r.body;
}

export function draftBody(text: string, sessionId = 'sess-1') {
  return {
    text,
    session_id: sessionId,
    account_label: 'acct-a',
    model: 'claude-opus-5-5',
    effort: 'low',
    usage: { input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 1000, cache_creation_input_tokens: 0 },
    cost_usd_equiv: 0.01,
    duration_ms: 3000,
    num_turns: 2,
    error_kind: null,
  };
}

export async function setFlags(patch: Record<string, unknown>) {
  const r = await staff('PUT', '/staff/flags', patch);
  expect(r.status).toBe(200);
}

export async function jobsOf(cid: string) {
  const { results } = await env.DB.prepare("SELECT * FROM jobs WHERE conversation_id = ? AND type = 'draft_reply' ORDER BY created_at")
    .bind(cid)
    .all<{ id: string; status: string; stale: number; lease_owner: string | null }>();
  return results;
}
