// server-zalo: webhook signature, dedupe, parsing, Zalo client idempotency, token refresh lock.
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { computeSignature } from '../src/lib/zalo-signature';
import { sendButtons, sendTemplate, sendText } from '../src/lib/zalo-client';
import { refreshIfNeeded, storeTokenPair } from '../src/lib/zalo-token';
import { eventKey, normalizeEvent } from '../src/zalo/parse';
import type { Env, ZaloWebhookEvent } from '../src/types';

const OA = 'test-oa-id';
const APP = 'test-app-id';
const SECRET = 'test-oa-secret';

let seq = 0;
function uid(prefix: string): string {
  seq += 1;
  return `${prefix}${Date.now().toString(36)}${seq}`;
}

function textEvent(userId: string, text: string, msgId: string): ZaloWebhookEvent {
  return {
    app_id: APP,
    sender: { id: userId },
    user_id_by_app: `app_${userId}`,
    recipient: { id: OA },
    event_name: 'user_send_text',
    message: { text, msg_id: msgId },
    timestamp: String(Date.now()),
  };
}

async function postWebhook(
  body: ZaloWebhookEvent | string,
  opts: { badSignature?: boolean; noSignature?: boolean; env?: Partial<Env>; numRetry?: number } = {},
) {
  const raw = typeof body === 'string' ? body : JSON.stringify(body);
  const parsed = typeof body === 'string' ? ({ app_id: APP, timestamp: '0' } as ZaloWebhookEvent) : body;
  const sig = await computeSignature(parsed.app_id, raw, parsed.timestamp, opts.badSignature ? 'wrong-secret' : SECRET);
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (!opts.noSignature) headers['x-zevent-signature'] = sig;
  if (opts.numRetry) headers['num_retry'] = String(opts.numRetry);
  const ctx = createExecutionContext();
  const res = await app.fetch(new Request('https://bot.test/zalo/webhook', { method: 'POST', body: raw, headers }), { ...env, ...opts.env }, ctx);
  await waitOnExecutionContext(ctx);
  return { res, json: (await res.json()) as Record<string, unknown> };
}

async function inboxRow(key: string) {
  return env.DB.prepare('SELECT * FROM events_inbox WHERE event_key = ?').bind(key).first<Record<string, unknown>>();
}

async function setFlag(name: string, value: unknown) {
  await env.DB.prepare('UPDATE flags SET value_json = ? WHERE name = ?').bind(JSON.stringify(value), name).run();
}

beforeEach(async () => {
  await setFlag('outbound_enabled', true);
});

describe('POST /zalo/webhook signature', () => {
  it('accepts a correctly signed event and stores the raw body before answering', async () => {
    const ev = textEvent(uid('u'), 'gội đầu bao nhiêu tiền ạ', uid('m'));
    const raw = JSON.stringify(ev);
    const { res, json } = await postWebhook(ev);
    expect(res.status).toBe(200);
    expect(json).toMatchObject({ ok: true, duplicate: false, signature_ok: true, event_key: `user_send_text:${ev.message!.msg_id}` });
    const row = await inboxRow(json.event_key as string);
    expect(row).not.toBeNull();
    expect(row!.signature_ok).toBe(1);
    expect(row!.raw_body).toBe(raw);
    expect(row!.zalo_user_id).toBe(ev.sender!.id);
    expect(row!.oa_id).toBe(OA);
    // dispatched once (the Conversation DO may still be a stub: then the row stays 'received' for inbox_sweep)
    expect(row!.attempts).toBe(1);
    expect(['received', 'processed', 'ignored']).toContain(row!.status);
  });

  it('observe mode: wrong signature is stored as ignored, answered 200, never dispatched', async () => {
    const ev = textEvent(uid('u'), 'hi', uid('m'));
    const { res, json } = await postWebhook(ev, { badSignature: true });
    expect(res.status).toBe(200);
    expect(json.signature_ok).toBe(false);
    const row = await inboxRow(json.event_key as string);
    expect(row!.signature_ok).toBe(0);
    expect(row!.status).toBe('ignored');
    expect(row!.attempts).toBe(0);
    // the untrusted body is not kept
    expect(row!.raw_body).toBe('');
  });

  it('observe mode: the genuine event after a forged one is stored with its body and dispatched', async () => {
    const ev = textEvent(uid('u'), 'hi', uid('m'));
    await postWebhook(ev, { badSignature: true });
    const { json } = await postWebhook(ev);
    expect(json).toMatchObject({ duplicate: false, signature_ok: true });
    const row = await inboxRow(json.event_key as string);
    expect(row!.raw_body).toBe(JSON.stringify(ev));
  });

  it('enforce mode: wrong or missing signature answers 401 signature_invalid and stores nothing', async () => {
    const ev = textEvent(uid('u'), 'hi', uid('m'));
    const bad = await postWebhook(ev, { badSignature: true, env: { WEBHOOK_SIGNATURE_MODE: 'enforce' } });
    expect(bad.res.status).toBe(401);
    expect((bad.json.error as { code: string }).code).toBe('signature_invalid');
    const none = await postWebhook(ev, { noSignature: true, env: { WEBHOOK_SIGNATURE_MODE: 'enforce' } });
    expect(none.res.status).toBe(401);
    expect(await inboxRow(`user_send_text:${ev.message!.msg_id}`)).toBeNull();
    const good = await postWebhook(ev, { env: { WEBHOOK_SIGNATURE_MODE: 'enforce' } });
    expect(good.res.status).toBe(200);
    expect(good.json.signature_ok).toBe(true);
  });

  it('a genuine event replaces an earlier forged copy with the same msg_id (observe mode)', async () => {
    const ev = textEvent(uid('u'), 'hi', uid('m'));
    await postWebhook(ev, { badSignature: true });
    const { json } = await postWebhook(ev);
    expect(json).toMatchObject({ duplicate: false, signature_ok: true });
    const row = await inboxRow(json.event_key as string);
    expect(row!.signature_ok).toBe(1);
    expect(row!.attempts).toBe(1);
  });

  it('rejects a body that is not JSON or has no event_name with 400', async () => {
    const notJson = await postWebhook('not json');
    expect(notJson.res.status).toBe(400);
    const noName = await postWebhook(JSON.stringify({ app_id: APP, timestamp: '0' }));
    expect(noName.res.status).toBe(400);
  });
});

describe('POST /zalo/webhook dedupe', () => {
  it('a replayed event (Zalo retry) is stored and dispatched once', async () => {
    const ev = textEvent(uid('u'), 'cho em hỏi giá', uid('m'));
    const first = await postWebhook(ev);
    const second = await postWebhook(ev, { numRetry: 2 });
    expect(first.json.duplicate).toBe(false);
    expect(second.res.status).toBe(200);
    expect(second.json).toMatchObject({ duplicate: true, event_key: first.json.event_key });
    const count = await env.DB.prepare('SELECT COUNT(*) AS n FROM events_inbox WHERE event_key = ?').bind(first.json.event_key).first<{ n: number }>();
    expect(count!.n).toBe(1);
    const row = await inboxRow(first.json.event_key as string);
    expect(row!.attempts).toBe(1); // the replay did not dispatch again
    expect(row!.num_retry).toBe(2);
  });

  it('events without msg_id (follow) dedupe on sha256 of the raw body', async () => {
    const follow = { app_id: APP, oa_id: OA, follower: { id: uid('u') }, event_name: 'follow', source: 'oa_profile', timestamp: String(Date.now()) } as unknown as ZaloWebhookEvent;
    const a = await postWebhook(follow);
    const b = await postWebhook(follow);
    expect(String(a.json.event_key)).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(b.json).toMatchObject({ duplicate: true, event_key: a.json.event_key });
  });
});

describe('zalo/parse', () => {
  it('maps customer events, OA echoes, follow and attachments', async () => {
    const sticker = { app_id: APP, sender: { id: 'c1' }, recipient: { id: OA }, event_name: 'user_send_sticker', timestamp: '1762500000000',
      message: { msg_id: 's1', attachments: [{ type: 'sticker', payload: { url: 'https://x/s.png', id: 'e1' } }] } } as ZaloWebhookEvent;
    const n1 = normalizeEvent(sticker, await eventKey(sticker, JSON.stringify(sticker)), true)!;
    expect(n1).toMatchObject({ kind: 'customer_message', message_kind: 'sticker', oa_id: OA, zalo_user_id: 'c1', zalo_msg_id: 's1', zalo_timestamp: 1762500000000 });
    expect(n1.attachments).toEqual([{ type: 'sticker', url: 'https://x/s.png' }]);

    const loc = { ...sticker, event_name: 'user_send_location', message: { msg_id: 'l1', attachments: [{ type: 'location', payload: { coordinates: { latitude: '10.76', longitude: '106.65' } } }] } } as ZaloWebhookEvent;
    expect(normalizeEvent(loc, 'k', true)!.attachments[0]).toEqual({ type: 'location', url: 'geo:10.76,106.65' });

    const link = { ...sticker, event_name: 'user_send_link', message: { msg_id: 'k1', text: 'xem', attachments: [{ type: 'link', payload: { url: 'https://a', description: 'A' } }] } } as ZaloWebhookEvent;
    expect(normalizeEvent(link, 'k', true)).toMatchObject({ message_kind: 'link', text: 'xem' });

    const echo = { app_id: APP, sender: { id: OA, admin_id: 'adm1' }, recipient: { id: 'c1' }, event_name: 'oa_send_text', message: { msg_id: 'o1', text: 'dạ' }, timestamp: '1' } as ZaloWebhookEvent;
    expect(normalizeEvent(echo, 'k', true)).toMatchObject({ kind: 'oa_message', oa_id: OA, zalo_user_id: 'c1', zalo_admin_id: 'adm1', message_kind: 'text' });

    const unfollow = { app_id: APP, oa_id: OA, follower: { id: 'c2' }, event_name: 'unfollow', timestamp: '1' } as unknown as ZaloWebhookEvent;
    expect(normalizeEvent(unfollow, 'k', true)).toMatchObject({ kind: 'unfollow', oa_id: OA, zalo_user_id: 'c2' });

    const seen = { app_id: APP, sender: { id: 'c1' }, recipient: { id: OA }, event_name: 'user_seen_message', timestamp: '1' } as ZaloWebhookEvent;
    expect(normalizeEvent(seen, 'k', true)).toBeNull();
  });
});

describe('zalo-client mock mode', () => {
  it('writes the outbox exactly once under duplicate and concurrent calls with the same dedupe key', async () => {
    const user = uid('u');
    const ctx = { conversation_id: null, customer_id: null, message_id: uid('msg_') };
    const results = await Promise.all([sendText(env, user, 'Dạ em chào anh/chị', ctx), sendText(env, user, 'Dạ em chào anh/chị', ctx), sendText(env, user, 'Dạ em chào anh/chị', ctx)]);
    const again = await sendText(env, user, 'Dạ em chào anh/chị', ctx);
    const rows = await env.DB.prepare('SELECT id, status, zalo_msg_id, kind, zalo_mode, payload_json FROM outbox WHERE zalo_user_id = ?').bind(user).all<Record<string, string>>();
    expect(rows.results).toHaveLength(1);
    const row = rows.results[0]!;
    expect(row).toMatchObject({ status: 'sent', kind: 'cs_text', zalo_mode: 'mock', zalo_msg_id: `mock_${row.id}` });
    expect(JSON.parse(row.payload_json!)).toEqual({ recipient: { user_id: user }, message: { text: 'Dạ em chào anh/chị' } });
    for (const r of [...results, again]) expect(r).toEqual({ ok: true, zalo_msg_id: `mock_${row.id}`, outbox_id: row.id });
  });

  it('refuses every send while outbound_enabled = false and writes nothing', async () => {
    await setFlag('outbound_enabled', false);
    const user = uid('u');
    const r = await sendText(env, user, 'x', { conversation_id: null, customer_id: null, message_id: uid('msg_') });
    expect(r).toMatchObject({ ok: false, unknown: false, error_code: 'outbound_disabled' });
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM outbox WHERE zalo_user_id = ?').bind(user).first<{ n: number }>();
    expect(n!.n).toBe(0);
  });

  it('builds the documented button and ZBS template payloads', async () => {
    const user = uid('u');
    const b = await sendButtons(env, user, 'Chọn giúp em', [{ title: 'Gặp nhân viên', type: 'oa.query.show', payload: '#gap_nhan_vien' }], { conversation_id: null, customer_id: null, message_id: uid('msg_') });
    const t = await sendTemplate(env, user, 'thank_you', { customer_name: 'Lan' }, { conversation_id: null, customer_id: null, message_id: null, dedupe_key: uid('job:') });
    expect(b.ok && t.ok).toBe(true);
    const rows = await env.DB.prepare('SELECT kind, payload_json, template_key FROM outbox WHERE zalo_user_id = ? ORDER BY kind').bind(user).all<Record<string, string>>();
    expect(JSON.parse(rows.results[0]!.payload_json!).message.attachment.payload.buttons[0]).toEqual({ title: 'Gặp nhân viên', type: 'oa.query.show', payload: '#gap_nhan_vien' });
    expect(JSON.parse(rows.results[1]!.payload_json!)).toEqual({ user_id: user, template_id: 'mock_tpl_thank_you', template_data: { customer_name: 'Lan' } });
    expect(rows.results[1]!.template_key).toBe('thank_you');
  });
});

describe('zalo-client real mode (fake fetch, no network)', () => {
  const realEnv = () => ({ ...env, ZALO_MODE: 'real' as const, ZALO_TEMPLATE_IDS: '{"thank_you":"433555"}' });

  async function freshTokens() {
    await storeTokenPair(env, 'access-1', 'refresh-1', 90000);
  }

  it('records an unknown outcome on timeout and never calls Zalo again for the same key', async () => {
    await freshTokens();
    let calls = 0;
    const fetchFail = (async () => {
      calls++;
      throw new Error('socket hang up');
    }) as unknown as typeof fetch;
    const ctx = { conversation_id: null, customer_id: null, message_id: uid('msg_') };
    const first = await sendText(realEnv(), 'u-real-1', 'xin chào', ctx, { fetch: fetchFail });
    expect(first).toMatchObject({ ok: false, unknown: true });
    const second = await sendText(realEnv(), 'u-real-1', 'xin chào', ctx, { fetch: fetchFail });
    expect(second).toMatchObject({ ok: false, unknown: true, error_code: 'send_unknown', outbox_id: (first as { outbox_id: string }).outbox_id });
    expect(calls).toBe(1);
    const row = await env.DB.prepare('SELECT status FROM outbox WHERE id = ?').bind((first as { outbox_id: string }).outbox_id).first<{ status: string }>();
    expect(row!.status).toBe('unknown');
  });

  it('marks explicit Zalo errors failed and successes sent with the Zalo message id', async () => {
    await freshTokens();
    const seen: Array<{ url: string; token: string | null }> = [];
    const fetchOk = (async (url: string, init: RequestInit) => {
      seen.push({ url, token: new Headers(init.headers).get('access_token') });
      return Response.json({ error: 0, message: 'Success', data: { message_id: 'zmsg-1', user_id: 'u' } });
    }) as unknown as typeof fetch;
    const ok = await sendText(realEnv(), 'u-real-2', 'xin chào', { conversation_id: null, customer_id: null, message_id: uid('msg_') }, { fetch: fetchOk });
    expect(ok).toMatchObject({ ok: true, zalo_msg_id: 'zmsg-1' });
    expect(seen[0]).toEqual({ url: 'https://openapi.zalo.me/v3.0/oa/message/cs', token: 'access-1' });

    const fetchErr = (async () => Response.json({ error: -230, message: 'User has not interacted with the OA in the past 7 days' })) as unknown as typeof fetch;
    const failed = await sendText(realEnv(), 'u-real-2', 'xin chào', { conversation_id: null, customer_id: null, message_id: uid('msg_') }, { fetch: fetchErr });
    expect(failed).toMatchObject({ ok: false, unknown: false, error_code: 'zalo_-230' });
  });
});

describe('zalo-token refresh', () => {
  it('refreshes once under concurrent callers and stores the new pair atomically', async () => {
    const now = Date.now();
    await storeTokenPair(env, 'access-old', 'refresh-old', 3600, now); // < 2 h left
    let calls = 0;
    let sentBody = '';
    let sentSecret: string | null = null;
    const fakeFetch = (async (_url: string, init: RequestInit) => {
      calls++;
      sentBody = String(init.body);
      sentSecret = new Headers(init.headers).get('secret_key');
      await new Promise((r) => setTimeout(r, 20));
      return Response.json({ access_token: 'access-new', refresh_token: 'refresh-new', expires_in: '90000' });
    }) as unknown as typeof fetch;
    const sleep = () => new Promise<void>((r) => setTimeout(r, 10));
    const results = await Promise.all([refreshIfNeeded(env, now, { fetch: fakeFetch, sleep }), refreshIfNeeded(env, now, { fetch: fakeFetch, sleep })]);
    expect(calls).toBe(1);
    expect(results.sort()).toEqual(['refreshed', 'refreshed']);
    expect(new URLSearchParams(sentBody).get('grant_type')).toBe('refresh_token');
    expect(new URLSearchParams(sentBody).get('refresh_token')).toBe('refresh-old');
    expect(sentSecret).toBe('test-app-secret');
    const row = await env.DB.prepare('SELECT access_token, refresh_token, auth_state, refresh_lock_until, access_expires_at FROM oa_tokens WHERE id = 1').first<Record<string, unknown>>();
    expect(row).toMatchObject({ access_token: 'access-new', refresh_token: 'refresh-new', auth_state: 'ok', refresh_lock_until: null, access_expires_at: now + 90000 * 1000 });
    expect(await refreshIfNeeded(env, now, { fetch: fakeFetch })).toBe('ok');
    expect(calls).toBe(1);
    const audit = await env.DB.prepare("SELECT after_json FROM audit_log WHERE action LIKE 'zalo_token.%'").all<{ after_json: string | null }>();
    expect(JSON.stringify(audit.results)).not.toContain('refresh-new');
  });

  it('a rejected refresh token puts the OA in reauth_required', async () => {
    await storeTokenPair(env, 'a', 'r', 60);
    const rejected = (async () => Response.json({ error: -14014, error_name: 'invalid_refresh_token' })) as unknown as typeof fetch;
    expect(await refreshIfNeeded(env, Date.now(), { fetch: rejected })).toBe('reauth_required');
    const row = await env.DB.prepare('SELECT auth_state FROM oa_tokens WHERE id = 1').first<{ auth_state: string }>();
    expect(row!.auth_state).toBe('reauth_required');
  });

  it('rate limit or a temporary Zalo error does not require re-auth; the lock is released for the next cron run', async () => {
    for (const reply of [
      () => new Response('slow down', { status: 429 }),
      () => Response.json({ error: -32, message: 'Exceed rate limit' }),
      () => Response.json({ error: -500, error_name: 'internal_error' }, { status: 400 }),
    ]) {
      await storeTokenPair(env, 'a', 'r', 60);
      const f = (async () => reply()) as unknown as typeof fetch;
      expect(await refreshIfNeeded(env, Date.now(), { fetch: f })).toBe('error');
      const row = await env.DB.prepare('SELECT auth_state, refresh_lock_until, refresh_token FROM oa_tokens WHERE id = 1').first<Record<string, unknown>>();
      expect(row).toMatchObject({ auth_state: 'ok', refresh_lock_until: null, refresh_token: 'r' });
    }
  });
});
