// Contact profiles v2 (docs/contracts.md section 13, migration 0008, analyzer contacts-rules-v3): the relationships
// staff / family / friend, the quiet staff_only rule for them (high confidence, or staff_override = 1 at any
// confidence), model facts never present for them, and last_service: the analyzer's chat signal merged with the
// newest staff-recorded visit (a newer visit wins) in the staff view, in model_facts and in the runner claim.
import { createExecutionContext, env, runDurableObjectAlarm, waitOnExecutionContext } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { profileFactsForModel, quietProfile } from '../src/lib/profiles';
import { localDate } from '../src/lib/time';
import { conversationObjectName, type CustomerProfileImport, type Env, type PersonalWebhookEvent } from '../src/types';
import { seed } from './core-helpers';

const SECRET = 'test-personal-webhook-secret';
const DAY = 86_400_000;
let n = 0;
const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;
const thread = () => `${920000 + n}${Date.now().toString().slice(-6)}${++n}`;

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function call(method: string, path: string, body?: unknown, headers: Record<string, string> = {}, e: Partial<Env> = {}) {
  const ctx = createExecutionContext();
  const raw = body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body);
  const res = await app.fetch(new Request(`https://bot.test${path}`, { method, headers: { 'content-type': 'application/json', ...headers }, ...(raw === undefined ? {} : { body: raw }) }), { ...env, ...e }, ctx);
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

const staff = (method: string, path: string, body?: unknown, staffId = 'tester') =>
  call(method, path, body, { authorization: 'Bearer test-staff-token', 'x-staff-id': staffId });
const runner = (path: string, body: unknown = {}) => call('POST', path, body, { authorization: 'Bearer test-runner-token', 'x-runner-id': 'mac-1' });
const bridge = (path: string, body: unknown = {}) => call('POST', path, body, { authorization: 'Bearer test-runner-token', 'x-bridge-id': 'bridge-1' });

async function postPersonal(ev: PersonalWebhookEvent) {
  const raw = JSON.stringify(ev);
  return call('POST', '/zalo/personal/webhook', raw, { authorization: `Bearer ${SECRET}`, 'x-zalo-signature': `sha256=${await hmacHex(SECRET, raw)}` });
}

function msgEvent(threadId: string, text: string): PersonalWebhookEvent {
  return { event: 'message', accountId: 'acc-test', msgId: uniq('7710'), cliMsgId: uniq('cli'), threadId, type: 0, isSelf: false, uidFrom: threadId, dName: 'Khách', msgType: 'webchat', content: text };
}

async function conv(threadId: string) {
  return env.DB.prepare('SELECT c.* FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?').bind(`p:${threadId}`).first<Record<string, any>>();
}

async function customerId(threadId: string): Promise<string> {
  const r = await env.DB.prepare("SELECT id FROM customers WHERE oa_id = 'personal' AND zalo_user_id = ?").bind(`p:${threadId}`).first<{ id: string }>();
  return r!.id;
}

async function setFlag(name: string, value: unknown) {
  await env.DB.prepare('INSERT INTO flags (name, value_json, updated_at) VALUES (?, ?, 0) ON CONFLICT(name) DO UPDATE SET value_json = excluded.value_json')
    .bind(name, JSON.stringify(value))
    .run();
}

async function sendNext(threadId: string) {
  const c = await bridge('/bridge/outbox/claim');
  expect(c.body.item?.thread_id).toBe(threadId);
  await bridge(`/bridge/outbox/${c.body.item.id}/result`, { status: 'sent', zalo_msg_id: uniq('8810') });
}

async function consentedThread(): Promise<string> {
  const threadId = thread();
  await postPersonal(msgEvent(threadId, 'chào shop'));
  await sendNext(threadId);
  await postPersonal(msgEvent(threadId, 'Đồng ý'));
  await sendNext(threadId);
  expect((await conv(threadId))!.bot_state).toBe('bot_active');
  return threadId;
}

const T_CHAT = Date.now() - 20 * DAY;

function profile(threadId: string, over: Partial<CustomerProfileImport> = {}): CustomerProfileImport {
  return {
    zalo_user_id: `p:${threadId}`,
    display_name: 'Nguyễn Thị Lan',
    relationship: 'customer',
    relationship_confidence: 'medium',
    relationship_reasons: ['service_vocab:3'],
    address_term: 'chị',
    name_to_use: 'Lan',
    address_confidence: 'medium',
    addressing: { owner_calls_contact: { 'chị': 4 }, contact_calls_self: {}, contact_calls_owner: {} },
    services: [
      { key: 'goi-dau-thu-gian', service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', group: 'hair', sensitive: false, status: 'likely_used', mention_count: 2, last_mentioned_at: T_CHAT, used_signal_count: 1, last_used_signal_at: T_CHAT },
    ],
    evidence: [],
    stats: {},
    last_service: { key: 'goi-dau-thu-gian', service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', at: T_CHAT, source: 'chat', confidence: 'medium', sensitive: false },
    ...over,
  };
}

const importProfiles = (profiles: unknown[]) =>
  staff('POST', '/staff/profiles/import', { analyzer_version: 'contacts-rules-v3', generated_at: 1762600000000, profiles }, 'analyzer');
const view = async (threadId: string) => (await staff('GET', `/staff/profiles/p:${threadId}`)).body.profile;

beforeAll(async () => {
  await seed();
});

beforeEach(async () => {
  await setFlag('outbound_enabled', true);
  await setFlag('profile_personal_skip_bot', true);
  await setFlag('ai_calls_enabled', true);
  await setFlag('ai_engine', 'subscription');
  await env.DB.prepare("UPDATE outbox SET status = 'sent' WHERE channel = 'personal' AND status IN ('queued','leased')").run();
  await env.DB.prepare("UPDATE jobs SET status = 'cancelled' WHERE type = 'draft_reply' AND status IN ('queued','leased')").run();
});

// ---------------------------------------------------------------- relationships and validation

describe('relationships staff / family / friend', () => {
  it('imports and lists them; model facts are null for them at any confidence', async () => {
    const ids = { staff: thread(), family: thread(), friend: thread() };
    const r = await importProfiles([
      profile(ids.staff, { relationship: 'staff', relationship_confidence: 'high', address_term: null, address_confidence: 'low', last_service: null }),
      profile(ids.family, { relationship: 'family', relationship_confidence: 'low' }),
      profile(ids.friend, { relationship: 'friend', relationship_confidence: 'medium' }),
    ]);
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ imported: 3, created: 3 });
    for (const [rel, t] of Object.entries(ids)) {
      const p = await view(t);
      expect(p.relationship, rel).toBe(rel);
      expect(p.model_facts, rel).toBeNull();
      expect(await profileFactsForModel(env, `p:${t}`, null), rel).toBeNull();
    }
    const list = await staff('GET', '/staff/profiles?relationship=staff&limit=200');
    expect(list.status).toBe(200);
    expect(list.body.items.map((p: any) => p.zalo_user_id)).toContain(`p:${ids.staff}`);
    expect(list.body.items.every((p: any) => p.relationship === 'staff')).toBe(true);
    expect((await staff('GET', '/staff/profiles?relationship=enemy')).status).toBe(422);
  });

  it('refuses a bad relationship or last_service with 422 and the field', async () => {
    const t = thread();
    const ls = profile(t).last_service!;
    const cases: Array<[unknown, string]> = [
      [{ ...profile(t), relationship: 'enemy' }, 'profiles[0].relationship'],
      [{ ...profile(t), last_service: { ...ls, source: 'visit' } }, 'profiles[0].last_service.source'],
      [{ ...profile(t), last_service: { ...ls, name: 'x'.repeat(121) } }, 'profiles[0].last_service.name'],
      [{ ...profile(t), last_service: { ...ls, at: -1 } }, 'profiles[0].last_service.at'],
      [{ ...profile(t), last_service: { ...ls, confidence: 'sure' } }, 'profiles[0].last_service.confidence'],
      [{ ...profile(t), last_service: { ...ls, key: 'bad key' } }, 'profiles[0].last_service.key'],
      [{ ...profile(t), last_service: 'gội đầu' }, 'profiles[0].last_service'],
    ];
    for (const [p, field] of cases) {
      const r = await importProfiles([p]);
      expect(r.status, field).toBe(422);
      expect(r.body.error.details.field).toBe(field);
    }
    // an analyzer v2 profile without last_service is still accepted
    const { last_service: _drop, ...v2 } = profile(t);
    expect((await importProfiles([v2])).status).toBe(200);
    expect((await view(t)).last_service).toBeNull();
  });

  it('PATCH accepts the new relationships', async () => {
    const t = thread();
    const r = await staff('PATCH', `/staff/profiles/p:${t}`, { relationship: 'friend' });
    expect(r.status).toBe(200);
    expect(r.body.profile).toMatchObject({ relationship: 'friend', relationship_confidence: 'high', staff_override: true, model_facts: null });
  });

  it('quietProfile: family / staff / friend / personal at high, or with staff_override at any confidence', () => {
    for (const rel of ['family', 'staff', 'friend', 'personal']) {
      expect(quietProfile({ relationship: rel, relationship_confidence: 'high', staff_override: 0 }), rel).toBe(true);
      expect(quietProfile({ relationship: rel, relationship_confidence: 'low', staff_override: 1 }), rel).toBe(true);
      expect(quietProfile({ relationship: rel, relationship_confidence: 'medium', staff_override: 0 }), rel).toBe(false);
    }
    expect(quietProfile({ relationship: 'customer', relationship_confidence: 'high', staff_override: 1 })).toBe(false);
    expect(quietProfile({ relationship: 'unknown', relationship_confidence: 'high', staff_override: 1 })).toBe(false);
    expect(quietProfile(null)).toBe(false);
  });
});

// ---------------------------------------------------------------- the quiet rule

describe('the quiet staff_only rule for family, staff and friends', () => {
  it('a high-confidence family, staff or friend profile turns the next message into staff_only, nothing sent', async () => {
    for (const rel of ['family', 'staff', 'friend'] as const) {
      const t = thread();
      await importProfiles([profile(t, { relationship: rel, relationship_confidence: 'high', last_service: null })]);
      expect((await postPersonal(msgEvent(t, 'tối nay về ăn cơm không'))).status).toBe(200);
      const c = await conv(t);
      expect(c, rel).toMatchObject({ bot_state: 'staff_only', needs_attention: 1 });
      const out = await env.DB.prepare("SELECT COUNT(*) AS n FROM outbox WHERE channel = 'personal' AND thread_id = ?").bind(t).first<{ n: number }>();
      expect(out!.n, rel).toBe(0);
    }
  });

  it('a medium-confidence friend gets the consent prompt; with staff_override = 1 the rule applies at any confidence', async () => {
    const t1 = thread();
    await importProfiles([profile(t1, { relationship: 'friend', relationship_confidence: 'medium' })]);
    await postPersonal(msgEvent(t1, 'ê mày'));
    expect((await conv(t1))!.bot_state).toBe('awaiting_consent');

    // staff confirms "friend" but says they are not sure: still staff-owned, so the bot stays away
    const t2 = thread();
    await importProfiles([profile(t2, { relationship: 'customer', relationship_confidence: 'medium' })]);
    const r = await staff('PATCH', `/staff/profiles/p:${t2}`, { relationship: 'friend', relationship_confidence: 'low' });
    expect(r.body.profile).toMatchObject({ relationship: 'friend', relationship_confidence: 'low', staff_override: true });
    await postPersonal(msgEvent(t2, 'ê mày'));
    expect((await conv(t2))!.bot_state).toBe('staff_only');

    // the analyzer said friend/medium and staff fixed only the name: staff_override = 1 and the relationship stands
    const t3 = thread();
    await importProfiles([profile(t3, { relationship: 'friend', relationship_confidence: 'medium' })]);
    await staff('PATCH', `/staff/profiles/p:${t3}`, { name_to_use: 'Hoa' });
    await postPersonal(msgEvent(t3, 'ê mày'));
    expect((await conv(t3))!.bot_state).toBe('staff_only');

    // a customer with staff_override = 1 is not affected
    const t4 = thread();
    await importProfiles([profile(t4)]);
    await staff('PATCH', `/staff/profiles/p:${t4}`, { staff_override: true });
    await postPersonal(msgEvent(t4, 'cho em hỏi giá'));
    expect((await conv(t4))!.bot_state).toBe('awaiting_consent');
  });
});

// ---------------------------------------------------------------- last service

describe('last_service: chat signal merged with recorded visits', () => {
  it('shows the chat signal, then a newer recorded visit wins; an older visit does not', async () => {
    const t = await consentedThread();
    await importProfiles([profile(t)]);
    let p = await view(t);
    expect(p.last_service).toMatchObject({ key: 'goi-dau-thu-gian', source: 'chat', confidence: 'medium', at: T_CHAT, sensitive: false });
    expect(p.model_facts.last_service).toEqual({ name: 'Gội đầu thư giãn', date: localDate(T_CHAT) });

    // an older visit: the chat signal is still the latest
    const cid = await customerId(t);
    const older = await staff('POST', '/staff/visits', { customer_id: cid, service_id: 'massage-body-thu-gian', visited_at: T_CHAT - 5 * DAY });
    expect(older.status).toBe(200);
    p = await view(t);
    expect(p.last_service).toMatchObject({ source: 'chat', key: 'goi-dau-thu-gian' });

    // a newer visit wins in the view, in model_facts and in the facts a draft job carries
    const visitedAt = T_CHAT + 3 * DAY;
    const newer = await staff('POST', '/staff/visits', { customer_id: cid, service_id: 'massage-chan', visited_at: visitedAt });
    expect(newer.status).toBe(200);
    p = await view(t);
    expect(p.last_service).toEqual({ key: 'massage-chan', service_id: 'massage-chan', name: 'Massage chân', at: visitedAt, source: 'visit', confidence: 'high', sensitive: false });
    expect(p.model_facts.last_service).toEqual({ name: 'Massage chân', date: localDate(visitedAt) });
    expect((await profileFactsForModel(env, `p:${t}`, null))!.last_service).toEqual({ name: 'Massage chân', date: localDate(visitedAt) });
    const listed = (await staff('GET', '/staff/profiles?relationship=customer&limit=200')).body.items.find((x: any) => x.zalo_user_id === `p:${t}`);
    expect(listed.last_service).toMatchObject({ source: 'visit', key: 'massage-chan' });
  });

  it('a low-confidence chat signal stays out of the model; a visit with no chat signal reaches it', async () => {
    const t = await consentedThread();
    await importProfiles([profile(t, { last_service: { ...profile(t).last_service!, confidence: 'low' } })]);
    let p = await view(t);
    expect(p.last_service).toMatchObject({ source: 'chat', confidence: 'low' });
    expect(p.model_facts.last_service).toBeUndefined();
    const at = Date.now() - 2 * DAY;
    await staff('POST', '/staff/visits', { customer_id: await customerId(t), service_id: 'detox-da-dau', visited_at: at });
    p = await view(t);
    expect(p.model_facts.last_service).toEqual({ name: 'Detox da đầu', date: localDate(at) });
  });

  it('a sensitive latest service (health / women group) never reaches the model', async () => {
    const t = await consentedThread();
    await importProfiles([profile(t)]);
    const at = Date.now() - DAY;
    expect((await staff('POST', '/staff/visits', { customer_id: await customerId(t), service_id: 'cham-soc-dau-bung-kinh', visited_at: at })).status).toBe(200);
    const p = await view(t);
    expect(p.last_service).toMatchObject({ source: 'visit', service_id: 'cham-soc-dau-bung-kinh', sensitive: true });
    expect(p.model_facts.last_service).toBeUndefined();
    expect(JSON.stringify(p.model_facts)).not.toContain('kinh');
    // a sensitive category from chat is stored as sensitive whatever the import says
    const t2 = thread();
    await importProfiles([profile(t2, {
      services: [{ key: 'cat:yoni', service_id: null, name: 'chăm sóc vùng kín', group: 'women', sensitive: true, status: 'likely_used', mention_count: 1, last_mentioned_at: T_CHAT, used_signal_count: 1, last_used_signal_at: T_CHAT }],
      last_service: { key: 'cat:yoni', service_id: null, name: 'chăm sóc vùng kín', at: T_CHAT, source: 'chat', confidence: 'high', sensitive: false },
    })]);
    const p2 = await view(t2);
    expect(p2.last_service).toMatchObject({ key: 'cat:yoni', sensitive: true });
    expect(p2.model_facts?.last_service).toBeUndefined();
  });

  it('a chat signal whose service is no longer listed as likely used is dropped', async () => {
    const t = thread();
    await importProfiles([profile(t)]);
    await staff('PATCH', `/staff/profiles/p:${t}`, { services: [] });
    const p = await view(t);
    expect(p.last_service).toBeNull();
    expect(p.model_facts.last_service).toBeUndefined();
  });

  it('the runner claim carries last_service as name + date only', async () => {
    const t = await consentedThread();
    await importProfiles([profile(t)]);
    await postPersonal(msgEvent(t, 'gội đầu bao nhiêu tiền ạ'));
    const c = await conv(t);
    await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
    await runDurableObjectAlarm(env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName('personal', `p:${t}`))));
    const r = await runner('/runner/jobs/claim');
    expect(r.status).toBe(200);
    expect(r.body.job?.conversation.conversation_id).toBe(c!.id);
    expect(r.body.job.customer_profile.last_service).toEqual({ name: 'Gội đầu thư giãn', date: localDate(T_CHAT) });
    const raw = JSON.stringify(r.body.job.customer_profile);
    expect(raw).not.toContain('confidence');
    expect(raw).not.toContain('"chat"');
  });
});
