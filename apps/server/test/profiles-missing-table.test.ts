// `wrangler dev` reloads new code before the owner applies migration 0007 to the local D1. Without the
// customer_profiles table the customer path must keep working (no profile), and staff profile writes answer 409.
// This file drops the table in its own D1 (each test file starts from a fresh database).
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { isMissingProfilesTable, personalSkipApplies, profileFactsForModel } from '../src/lib/profiles';
import type { PersonalWebhookEvent } from '../src/types';

const SECRET = 'test-personal-webhook-secret';

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function call(method: string, path: string, body: string | undefined, headers: Record<string, string>) {
  const ctx = createExecutionContext();
  const res = await app.fetch(new Request(`https://bot.test${path}`, { method, headers: { 'content-type': 'application/json', ...headers }, ...(body === undefined ? {} : { body }) }), env, ctx);
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

beforeAll(async () => {
  await env.DB.prepare('DROP TABLE IF EXISTS customer_profiles').run();
});

describe('before migration 0007', () => {
  it('a personal contact still gets the consent prompt, and the detail has profile null', async () => {
    const threadId = '9300001';
    const ev: PersonalWebhookEvent = { event: 'message', accountId: 'acc-test', msgId: '7700991', threadId, type: 0, isSelf: false, uidFrom: threadId, dName: 'Lan', msgType: 'webchat', content: 'chào em' };
    const raw = JSON.stringify(ev);
    const r = await call('POST', '/zalo/personal/webhook', raw, { authorization: `Bearer ${SECRET}`, 'x-zalo-signature': `sha256=${await hmacHex(SECRET, raw)}` });
    expect(r.status).toBe(200);
    const c = await env.DB.prepare("SELECT c.id, c.bot_state FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = 'p:9300001'").first<{ id: string; bot_state: string }>();
    expect(c!.bot_state).toBe('awaiting_consent');
    const d = await call('GET', `/staff/conversations/${c!.id}`, undefined, { authorization: 'Bearer test-staff-token' });
    expect(d.status).toBe(200);
    expect(d.body.profile).toBeNull();
    expect(await personalSkipApplies(env, { id: 'cus_x', zalo_user_id: 'p:9300001' }, c!.id)).toBe(false);
    expect(await profileFactsForModel(env, 'p:9300001', null)).toBeNull();
  });

  it('staff profile writes answer 409 invalid_state', async () => {
    const imp = await call('POST', '/staff/profiles/import', JSON.stringify({ profiles: [] }), { authorization: 'Bearer test-staff-token' });
    expect(imp.status).toBe(200); // nothing to write, nothing touched
    const p = await call('PATCH', '/staff/profiles/p:9300001', JSON.stringify({ address_term: 'chị' }), { authorization: 'Bearer test-staff-token' });
    expect(p.status).toBe(409);
    expect(p.body.error.code).toBe('invalid_state');
    expect((await call('GET', '/staff/profiles', undefined, { authorization: 'Bearer test-staff-token' })).status).toBe(409);
    expect(isMissingProfilesTable(new Error('D1_ERROR: no such table: customer_profiles: SQLITE_ERROR'))).toBe(true);
    expect(isMissingProfilesTable(new Error('no such table: flags'))).toBe(false);
  });
});
