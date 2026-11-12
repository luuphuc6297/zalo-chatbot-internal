// Contact profiles (docs/contracts.md section 13): import with validation, staff override kept across imports,
// PATCH and clearing the override, the profile in the conversation detail, the quiet staff_only rule for personal
// contacts (flag on / off, medium confidence, consented customer, staff release), and the derived facts in the
// runner claim payload (never evidence, never health services, never a personal profile).
import { createExecutionContext, env, runDurableObjectAlarm, waitOnExecutionContext } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { conversationObjectName, type CustomerProfileImport, type Env, type PersonalWebhookEvent } from '../src/types';
import { seed } from './core-helpers';

const SECRET = 'test-personal-webhook-secret';
let n = 0;
const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;
const thread = () => `${910000 + n}${Date.now().toString().slice(-6)}${++n}`;

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

function msgEvent(threadId: string, text: string, extra: Partial<PersonalWebhookEvent> = {}): PersonalWebhookEvent {
  return { event: 'message', accountId: 'acc-test', msgId: uniq('7700'), cliMsgId: uniq('cli'), threadId, type: 0, isSelf: false, uidFrom: threadId, dName: 'Nguyễn Thị Lan', msgType: 'webchat', content: text, ...extra };
}

async function conv(threadId: string) {
  return env.DB.prepare('SELECT c.* FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?').bind(`p:${threadId}`).first<Record<string, any>>();
}

async function outboxOf(threadId: string) {
  return (await env.DB.prepare("SELECT * FROM outbox WHERE channel = 'personal' AND thread_id = ? ORDER BY created_at, id").bind(threadId).all<Record<string, any>>()).results;
}

async function setFlag(name: string, value: unknown) {
  await env.DB.prepare('INSERT INTO flags (name, value_json, updated_at) VALUES (?, ?, 0) ON CONFLICT(name) DO UPDATE SET value_json = excluded.value_json')
    .bind(name, JSON.stringify(value))
    .run();
}

/** The bridge claims the next row of this thread and reports it sent. */
async function sendNext(threadId: string) {
  const c = await bridge('/bridge/outbox/claim');
  expect(c.body.item?.thread_id).toBe(threadId);
  await bridge(`/bridge/outbox/${c.body.item.id}/result`, { status: 'sent', zalo_msg_id: uniq('8800') });
  return c.body.item;
}

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

const SNIPPET = 'Chị muốn đặt lịch gội đầu thư giãn thứ 7';

function profile(threadId: string, over: Partial<CustomerProfileImport> = {}): CustomerProfileImport {
  return {
    zalo_user_id: `p:${threadId}`,
    display_name: 'Nguyễn Thị Lan',
    relationship: 'customer',
    relationship_confidence: 'medium',
    relationship_reasons: ['service_vocab:3', 'catalog_match:2'],
    address_term: 'chị',
    name_to_use: 'Lan',
    address_confidence: 'medium',
    addressing: { owner_calls_contact: { 'chị': 4 }, contact_calls_self: { 'chị': 2 }, contact_calls_owner: { em: 3 } },
    services: [
      { key: 'goi-dau-thu-gian', service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', group: 'hair', sensitive: false, status: 'likely_used', mention_count: 3, last_mentioned_at: 1762000000000, used_signal_count: 1, last_used_signal_at: 1762000000000 },
      { key: 'massage-chan', service_id: 'massage-chan', name: 'Massage chân', group: 'relaxation', sensitive: false, status: 'mentioned', mention_count: 1, last_mentioned_at: 1762000000000, used_signal_count: 0, last_used_signal_at: null },
      { key: 'cham-soc-dau-bung-kinh', service_id: 'cham-soc-dau-bung-kinh', name: 'Chăm sóc đau bụng kinh, rối loạn kinh nguyệt', group: 'women', sensitive: true, status: 'likely_used', mention_count: 1, last_mentioned_at: 1762000000000, used_signal_count: 1, last_used_signal_at: 1762000000000 },
      { key: 'cat:massage', service_id: null, name: 'massage', group: 'relaxation', sensitive: false, status: 'mentioned', mention_count: 2, last_mentioned_at: 1762000000000, used_signal_count: 0, last_used_signal_at: null },
      { key: 'cat:triet_long', service_id: null, name: 'triệt lông', group: 'other', sensitive: false, status: 'mentioned', mention_count: 1, last_mentioned_at: 1762000000000, used_signal_count: 0, last_used_signal_at: null },
    ],
    evidence: [{ at: 1762000000000, from: 'contact', kind: 'service', text: SNIPPET }],
    stats: { messages_in: 10, messages_out: 8 },
    ...over,
  };
}

const importProfiles = (profiles: unknown[], staffId = 'analyzer') => staff('POST', '/staff/profiles/import', { analyzer_version: 'contacts-rules-v1', generated_at: 1762600000000, profiles }, staffId);

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

// ---------------------------------------------------------------- import

describe('POST /staff/profiles/import', () => {
  it('creates, then updates, and answers counts; GET returns the view with evidence and model facts', async () => {
    const t1 = thread();
    const t2 = thread();
    const r = await importProfiles([profile(t1), profile(t2, { relationship: 'unknown', relationship_confidence: 'low', address_term: 'anh/chị', address_confidence: 'low', name_to_use: null, services: [], evidence: [] })]);
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ imported: 2, created: 2, updated: 0, kept_staff_fields: 0 });
    const again = await importProfiles([profile(t1)]);
    expect(again.body).toEqual({ imported: 1, created: 0, updated: 1, kept_staff_fields: 0 });

    const g = await staff('GET', `/staff/profiles/${encodeURIComponent(`p:${t1}`)}`);
    expect(g.status).toBe(200);
    const p = g.body.profile;
    expect(p).toMatchObject({ zalo_user_id: `p:${t1}`, thread_id: t1, customer_id: null, conversation_id: null, relationship: 'customer', address_term: 'chị', name_to_use: 'Lan', staff_override: false, source: 'analyzer', updated_by: 'analyzer', analyzer_version: 'contacts-rules-v1', analyzed_at: 1762600000000 });
    expect(p.evidence).toEqual([{ at: 1762000000000, from: 'contact', kind: 'service', text: SNIPPET }]);
    expect(p.analyzer).toMatchObject({ relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    expect(p.model_facts).toEqual({
      relationship: 'customer',
      address_term: 'chị',
      name_to_use: 'Lan',
      services_likely_used: ['Gội đầu thư giãn'],
      services_mentioned: ['Massage chân', 'massage'],
    });
    // the unencoded colon works too
    expect((await staff('GET', `/staff/profiles/p:${t1}`)).status).toBe(200);
    const audit = await env.DB.prepare("SELECT after_json FROM audit_log WHERE action = 'profile.import' ORDER BY id DESC LIMIT 1").first<{ after_json: string }>();
    expect(audit!.after_json).not.toContain('Lan');
    expect(audit!.after_json).not.toContain(SNIPPET);
  });

  it('refuses invalid input with 422 and the field, and stores nothing from that batch', async () => {
    const t = thread();
    const cases: Array<[unknown, string]> = [
      [{ ...profile(t), address_term: 'mình' }, 'profiles[0].address_term'],
      [{ ...profile(t), name_to_use: 'Lan Anh' }, 'profiles[0].name_to_use'],
      [{ ...profile(t), zalo_user_id: '12345' }, 'profiles[0].zalo_user_id'],
      [{ ...profile(t), evidence: [{ at: 1, from: 'contact', kind: 'service', text: 'x'.repeat(81) }] }, 'profiles[0].evidence[0].text'],
      [{ ...profile(t), evidence: [1, 2, 3, 4] }, 'profiles[0].evidence'],
      [{ ...profile(t), relationship: 'enemy' }, 'profiles[0].relationship'],
      [{ ...profile(t), stats: { blob: 'x'.repeat(5000) } }, 'profiles[0].stats'],
    ];
    for (const [p, field] of cases) {
      const r = await importProfiles([p]);
      expect(r.status, field).toBe(422);
      expect(r.body.error.details.field).toBe(field);
    }
    const dup = await importProfiles([profile(t), profile(t)]);
    expect(dup.body.error.details.field).toBe('profiles[1].zalo_user_id');
    expect((await staff('GET', `/staff/profiles/p:${t}`)).status).toBe(404);
    expect((await staff('POST', '/staff/profiles/import', 'not json')).status).toBe(400);
    expect((await call('POST', '/staff/profiles/import', { profiles: [] })).status).toBe(401);
  });

  it('counts the 2 MB import limit in bytes, also for a body sent without Content-Length', async () => {
    // about 1.5 million characters but over 2 MB in UTF-8 (each "ạ" is 3 bytes)
    const big = JSON.stringify({ profiles: [], pad: 'ạ'.repeat(700_000) });
    expect(big.length).toBeLessThan(2_000_000);
    expect(new TextEncoder().encode(big).length).toBeGreaterThan(2_000_000);
    const enc = new TextEncoder().encode(big);
    const stream = new ReadableStream<Uint8Array>({
      start(ctl) {
        for (let i = 0; i < enc.length; i += 65_536) ctl.enqueue(enc.slice(i, i + 65_536));
        ctl.close();
      },
    });
    const ctx = createExecutionContext();
    const res = await app.fetch(
      new Request('https://bot.test/staff/profiles/import', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: 'Bearer test-staff-token', 'x-staff-id': 'analyzer' },
        body: stream,
        // @ts-expect-error undici needs duplex for a streamed body
        duplex: 'half',
      }),
      env,
      ctx,
    );
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(413);
    const small = await staff('POST', '/staff/profiles/import', { profiles: [], pad: 'ạ'.repeat(1000) }, 'analyzer');
    expect(small.status).toBe(200);
  });

  it('lists profiles filtered by relationship', async () => {
    const t = thread();
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'medium' })]);
    const r = await staff('GET', '/staff/profiles?relationship=personal&confidence=medium&limit=200');
    expect(r.status).toBe(200);
    expect(r.body.items.map((p: any) => p.zalo_user_id)).toContain(`p:${t}`);
    expect(r.body.items.every((p: any) => p.relationship === 'personal')).toBe(true);
    expect((await staff('GET', '/staff/profiles?relationship=enemy')).status).toBe(422);
  });
});

// ---------------------------------------------------------------- staff edits

describe('PATCH /staff/profiles/:zalo_user_id', () => {
  it('sets staff_override; a later import keeps the staff fields and refreshes the analyzer ones; clearing restores', async () => {
    const t = thread();
    await importProfiles([profile(t)]);
    const p1 = await staff('PATCH', `/staff/profiles/${encodeURIComponent(`p:${t}`)}`, { address_term: 'cô', name_to_use: 'Hoa', staff_note: 'khách quen' });
    expect(p1.status).toBe(200);
    expect(p1.body.profile).toMatchObject({ address_term: 'cô', address_confidence: 'high', name_to_use: 'Hoa', staff_override: true, staff_fields: ['address', 'name'], staff_note: 'khách quen', updated_by: 'tester' });
    expect(p1.body.profile.model_facts).toMatchObject({ address_term: 'cô', name_to_use: 'Hoa' });

    // the analyzer changes its mind on everything; only the groups staff edited are kept
    const newer = profile(t, {
      relationship: 'unknown',
      relationship_confidence: 'low',
      address_term: 'anh',
      name_to_use: 'Tuấn',
      services: [],
      evidence: [{ at: 1762100000000, from: 'owner', kind: 'booking', text: 'Dạ bên em còn slot 3h' }],
      stats: { messages_in: 20 },
    });
    const imp = await importProfiles([newer]);
    expect(imp.body).toEqual({ imported: 1, created: 0, updated: 1, kept_staff_fields: 1 });
    const kept = (await staff('GET', `/staff/profiles/p:${t}`)).body.profile;
    expect(kept).toMatchObject({ address_term: 'cô', address_confidence: 'high', name_to_use: 'Hoa', staff_override: true, staff_note: 'khách quen' });
    expect(kept).toMatchObject({ relationship: 'unknown', relationship_confidence: 'low', services: [] });
    expect(kept.analyzer).toMatchObject({ address_term: 'anh', name_to_use: 'Tuấn' });
    expect(kept.evidence[0].text).toBe('Dạ bên em còn slot 3h');
    expect(kept.stats).toEqual({ messages_in: 20 });

    const cleared = await staff('PATCH', `/staff/profiles/p:${t}`, { staff_override: false });
    expect(cleared.body.profile).toMatchObject({ address_term: 'anh', name_to_use: 'Tuấn', staff_override: false, staff_fields: [] });
    const audit = await env.DB.prepare("SELECT action, after_json FROM audit_log WHERE entity = 'customer_profile' AND entity_id = ? ORDER BY id").bind(`p:${t}`).all<{ action: string; after_json: string }>();
    expect(audit.results.map((a) => a.action)).toEqual(['profile.staff_edit', 'profile.override_cleared']);
    expect(audit.results.map((a) => a.after_json).join()).not.toMatch(/Hoa|Tuấn|khách quen/);
  });

  it('creates a staff profile when none exists, and validates the body and the id', async () => {
    const t = thread();
    const r = await staff('PATCH', `/staff/profiles/p:${t}`, { relationship: 'personal' });
    expect(r.status).toBe(200);
    expect(r.body.profile).toMatchObject({ relationship: 'personal', relationship_confidence: 'high', source: 'staff', staff_override: true, staff_fields: ['relationship'], analyzer: null, model_facts: null });
    expect((await staff('PATCH', `/staff/profiles/p:${t}`, { staff_override: false, address_term: 'chị' })).body.error.details.field).toBe('staff_override');
    expect((await staff('PATCH', `/staff/profiles/p:${t}`, { nickname: 'x' })).body.error.details.field).toBe('nickname');
    expect((await staff('PATCH', `/staff/profiles/p:${t}`, { name_to_use: 'Lan 2' })).body.error.details.field).toBe('name_to_use');
    expect((await staff('PATCH', `/staff/profiles/p:${t}`, {})).status).toBe(422);
    expect((await staff('PATCH', '/staff/profiles/not-a-profile', { relationship: 'customer' })).status).toBe(400);
    expect((await staff('GET', `/staff/profiles/p:${thread()}`)).status).toBe(404);
  });

  it('editing only the name does not raise a low-confidence address guess, and a later import still changes the relationship', async () => {
    const t = thread();
    await importProfiles([profile(t, { address_term: 'anh', address_confidence: 'low', name_to_use: 'Lan' })]);
    const before = (await staff('GET', `/staff/profiles/p:${t}`)).body.profile;
    expect(before.model_facts.address_term).toBeNull();
    const r = await staff('PATCH', `/staff/profiles/p:${t}`, { name_to_use: 'Mai' });
    expect(r.body.profile).toMatchObject({ name_to_use: 'Mai', address_term: 'anh', address_confidence: 'low', staff_override: true, staff_fields: ['name'] });
    // the low guess stays out of the model, and so does the name (no specific term)
    expect(r.body.profile.model_facts).toMatchObject({ address_term: null, name_to_use: null });
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high', address_term: 'chị', address_confidence: 'medium', name_to_use: 'Lan' })]);
    const after = (await staff('GET', `/staff/profiles/p:${t}`)).body.profile;
    expect(after).toMatchObject({ relationship: 'personal', relationship_confidence: 'high', address_term: 'chị', address_confidence: 'medium', name_to_use: 'Mai' });
  });

  it('staff_override true alone pins all four groups', async () => {
    const t = thread();
    await importProfiles([profile(t)]);
    const r = await staff('PATCH', `/staff/profiles/p:${t}`, { staff_override: true });
    expect(r.body.profile).toMatchObject({ staff_override: true, staff_fields: ['relationship', 'address', 'name', 'services'] });
    await importProfiles([profile(t, { relationship: 'unknown', address_term: 'anh', name_to_use: 'Tuấn', services: [] })]);
    const kept = (await staff('GET', `/staff/profiles/p:${t}`)).body.profile;
    expect(kept).toMatchObject({ relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    expect(kept.services).toHaveLength(5);
  });
});

// ---------------------------------------------------------------- conversation detail + the quiet rule

describe('personal contacts and the bot', () => {
  it('a high-confidence personal contact becomes staff_only on the next message: no prompt, nothing sent, flagged for staff', async () => {
    const t = thread();
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high', services: [], evidence: [] })]);
    const r = await postPersonal(msgEvent(t, 'Mẹ ơi con về muộn nha'));
    expect(r.status).toBe(200);
    const c = await conv(t);
    expect(c).toMatchObject({ bot_state: 'staff_only', needs_attention: 1 });
    expect(await outboxOf(t)).toHaveLength(0);
    const audit = await env.DB.prepare("SELECT actor_type, after_json FROM audit_log WHERE action = 'conversation.staff_only_profile' AND entity_id = ?").bind(c!.id).first<{ actor_type: string; after_json: string }>();
    expect(audit).toMatchObject({ actor_type: 'system' });
    // later messages stay with staff and never get a prompt either
    await postPersonal(msgEvent(t, 'con ăn cơm chưa'));
    expect((await conv(t))!.bot_state).toBe('staff_only');
    expect(await outboxOf(t)).toHaveLength(0);
    // the conversation detail carries the profile for the console
    const d = await staff('GET', `/staff/conversations/${c!.id}`);
    expect(d.status).toBe(200);
    expect(d.body.profile).toMatchObject({ zalo_user_id: `p:${t}`, relationship: 'personal', conversation_id: c!.id, model_facts: null });
  });

  it('writes exactly one audit row, and "gặp nhân viên" from that contact sends nothing and opens no handoff', async () => {
    const t = thread();
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high', services: [], evidence: [] })]);
    await postPersonal(msgEvent(t, 'Mẹ ơi con về muộn nha'));
    const c = await conv(t);
    expect(c!.bot_state).toBe('staff_only');
    await env.DB.prepare('UPDATE conversations SET needs_attention = 0 WHERE id = ?').bind(c!.id).run();
    const r = await postPersonal(msgEvent(t, 'gặp nhân viên'));
    expect(r.status).toBe(200);
    const c2 = await conv(t);
    expect(c2).toMatchObject({ bot_state: 'staff_only', needs_attention: 1 });
    expect(await outboxOf(t)).toHaveLength(0);
    const handoffs = await env.DB.prepare('SELECT COUNT(*) AS n FROM handoffs WHERE conversation_id = ?').bind(c!.id).first<{ n: number }>();
    expect(handoffs!.n).toBe(0);
    const audits = await env.DB.prepare("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'conversation.staff_only_profile' AND entity_id = ?").bind(c!.id).first<{ n: number }>();
    expect(audits!.n).toBe(1);
  });

  it('applies after a staff takeover expires: no prompt, one audit row', async () => {
    const t = thread();
    await postPersonal(msgEvent(t, 'chào em'));
    await sendNext(t);                                   // the consent prompt went out before the import
    const c = await conv(t);
    expect((await staff('POST', `/staff/conversations/${c!.id}/takeover`, { until: Date.now() + 60_000 })).status).toBe(200);
    expect((await conv(t))!.bot_state).toBe('staff_takeover');
    await env.DB.prepare('UPDATE conversations SET takeover_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high' })]);
    await postPersonal(msgEvent(t, 'tối nay về ăn cơm không con'));
    const c2 = await conv(t);
    expect(c2).toMatchObject({ bot_state: 'staff_only', needs_attention: 1, takeover_by: null, takeover_until: null });
    expect((await outboxOf(t)).map((o) => o.status)).toEqual(['sent']);   // only the old prompt, nothing new
    const audits = await env.DB.prepare("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'conversation.staff_only_profile' AND entity_id = ?").bind(c!.id).first<{ n: number }>();
    expect(audits!.n).toBe(1);
  });

  it('with profile_personal_skip_bot=false the contact gets the consent prompt as before', async () => {
    await setFlag('profile_personal_skip_bot', false);
    const t = thread();
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high' })]);
    await postPersonal(msgEvent(t, 'chào em'));
    expect((await conv(t))!.bot_state).toBe('awaiting_consent');
    expect((await outboxOf(t)).map((o) => o.kind)).toEqual(['cs_buttons']);
  });

  it('a medium-confidence personal profile, or staff saying customer, does not trigger the rule', async () => {
    const t1 = thread();
    await importProfiles([profile(t1, { relationship: 'personal', relationship_confidence: 'medium' })]);
    await postPersonal(msgEvent(t1, 'chào em'));
    expect((await conv(t1))!.bot_state).toBe('awaiting_consent');
    const t2 = thread();
    await importProfiles([profile(t2, { relationship: 'personal', relationship_confidence: 'high' })]);
    await staff('PATCH', `/staff/profiles/p:${t2}`, { relationship: 'customer' });
    await postPersonal(msgEvent(t2, 'chào em'));
    expect((await conv(t2))!.bot_state).toBe('awaiting_consent');
  });

  it('a waiting consent prompt from before the import is cancelled, and a staff release is not undone', async () => {
    const t = thread();
    await postPersonal(msgEvent(t, 'chào em'));   // prompt queued, not sent yet
    expect((await outboxOf(t)).map((o) => o.status)).toEqual(['queued']);
    await importProfiles([profile(t, { relationship: 'personal', relationship_confidence: 'high' })]);
    await postPersonal(msgEvent(t, 'tối nay về ăn cơm không'));
    const c = await conv(t);
    expect(c!.bot_state).toBe('staff_only');
    expect((await outboxOf(t)).map((o) => o.status)).toEqual(['failed']);
    // staff hands the contact back to the bot: the rule does not apply again
    expect((await staff('POST', `/staff/conversations/${c!.id}/release`, {})).status).toBe(200);
    await postPersonal(msgEvent(t, 'cho em hỏi giá gội đầu'));
    expect((await conv(t))!.bot_state).toBe('awaiting_consent');
  });

  it('a customer who already granted consent is not affected', async () => {
    const { threadId } = await consentedThread();
    await importProfiles([profile(threadId, { relationship: 'personal', relationship_confidence: 'high' })]);
    await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
    expect((await conv(threadId))!.bot_state).toBe('bot_active');
  });
});

// ---------------------------------------------------------------- runner claim payload

async function claimFor(threadId: string) {
  await postPersonal(msgEvent(threadId, 'gội đầu bao nhiêu tiền ạ'));
  const c = await conv(threadId);
  await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
  const stub = env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName('personal', `p:${threadId}`)));
  await runDurableObjectAlarm(stub);
  const r = await runner('/runner/jobs/claim');
  expect(r.status).toBe(200);
  expect(r.body.job?.conversation.conversation_id).toBe(c!.id);
  return r.body.job;
}

describe('runner claim payload', () => {
  it('carries the derived facts only: address, name, catalog names; no snippets, no health services', async () => {
    const { threadId } = await consentedThread();
    await importProfiles([profile(threadId)]);
    const job = await claimFor(threadId);
    expect(job.customer_profile).toEqual({
      relationship: 'customer',
      address_term: 'chị',
      name_to_use: 'Lan',
      services_likely_used: ['Gội đầu thư giãn'],
      services_mentioned: ['Massage chân', 'massage'],
    });
    const raw = JSON.stringify(job);
    expect(raw).not.toContain(SNIPPET);
    expect(raw).not.toContain('kinh nguyệt');
    expect(raw).not.toContain('triệt lông');
    expect(raw).not.toContain('service_vocab');
  });

  it('a low-confidence address is left out; a personal profile gives null', async () => {
    const a = await consentedThread();
    await importProfiles([profile(a.threadId, { address_confidence: 'low', services: [] })]);
    expect((await claimFor(a.threadId)).customer_profile).toBeNull();
    const b = await consentedThread();
    await importProfiles([profile(b.threadId, { relationship: 'personal', relationship_confidence: 'medium' })]);
    expect((await claimFor(b.threadId)).customer_profile).toBeNull();
    const c = await consentedThread();
    expect((await claimFor(c.threadId)).customer_profile).toBeNull();   // no profile at all
  });
});
