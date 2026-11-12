// Staff menu images (task C): the slide index and thumbnails for the console, a draft's attachments in the staff view
// and approve with a subset, and "Gửi menu" (staff queue covers or a group's price slides; claim slides only with
// include_claim_slides). Synthetic customers only.
import { createExecutionContext, env, runDurableObjectAlarm, waitOnExecutionContext } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { MENU_INDEX } from '../src/lib/menu-images';
import { MENU_THUMBS } from '../src/menu-thumbs';
import { conversationObjectName, type PersonalWebhookEvent } from '../src/types';
import { claim as claimJob, consentedCustomer, draftBody, runner, seed, setFlags, staff } from './core-helpers';

const SECRET = 'test-personal-webhook-secret';
let n = 0;
const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function call(method: string, path: string, headers: Record<string, string>, body?: unknown) {
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, { method, headers: { 'content-type': 'application/json', ...headers }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return res;
}

async function postPersonal(ev: PersonalWebhookEvent) {
  const raw = JSON.stringify(ev);
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request('https://bot.test/zalo/personal/webhook', {
      method: 'POST',
      body: raw,
      headers: { 'content-type': 'application/json', authorization: `Bearer ${SECRET}`, 'x-zalo-signature': `sha256=${await hmacHex(SECRET, raw)}` },
    }),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  expect(res.status).toBe(200);
}

const msg = (threadId: string, content: string): PersonalWebhookEvent => ({
  event: 'message',
  accountId: 'acc-test',
  msgId: uniq('7710'),
  threadId,
  type: 0,
  isSelf: false,
  uidFrom: threadId,
  dName: 'Chị Lan',
  msgType: 'webchat',
  content,
});

const bridgeHeaders = { authorization: 'Bearer test-runner-token', 'x-bridge-id': 'bridge-staff-menu' };
async function claimImages() {
  return (await (await call('POST', '/bridge/outbox/claim', bridgeHeaders, { capabilities: ['images'] })).json()) as any;
}
async function sendNext(threadId: string) {
  const c = await claimImages();
  expect(c.item?.thread_id).toBe(threadId);
  await call('POST', `/bridge/outbox/${c.item.id}/result`, bridgeHeaders, { status: 'sent', zalo_msg_id: uniq('8810') });
}

async function convOf(threadId: string) {
  return (await env.DB.prepare('SELECT c.* FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?')
    .bind(`p:${threadId}`)
    .first<Record<string, any>>())!;
}
async function outboxOf(threadId: string) {
  return (await env.DB.prepare("SELECT * FROM outbox WHERE channel = 'personal' AND thread_id = ? ORDER BY created_at, id").bind(threadId).all<Record<string, any>>()).results;
}

/** A personal customer past the consent gate (bot_active); the two server messages are already sent. */
async function personalCustomer(): Promise<{ threadId: string; cid: string }> {
  const threadId = uniq('9400');
  await postPersonal(msg(threadId, 'chào shop'));
  await sendNext(threadId);
  await postPersonal(msg(threadId, 'Đồng ý'));
  await sendNext(threadId);
  const c = await convOf(threadId);
  expect(c.bot_state).toBe('bot_active');
  return { threadId, cid: c.id };
}

/** personalCustomer + a question, its draft job claimed, menu slides attached and a draft submitted. */
async function draftWithImages(input: { group: string; service_id: string }) {
  const p = await personalCustomer();
  await postPersonal(msg(p.threadId, 'cho chị xem menu tóc'));
  await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, p.cid).run();
  await runDurableObjectAlarm(env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName('personal', `p:${p.threadId}`))));
  const job = await claimJob();
  expect(job.job?.conversation.conversation_id).toBe(p.cid);
  const t = await runner('/runner/tools/attach_menu_images', { job_id: job.job.job_id, input });
  expect(t.body.result.status).toBe('attached');
  const d = await runner(`/runner/jobs/${job.job.job_id}/draft`, draftBody('Dạ em gửi chị menu chăm sóc tóc ạ.'));
  expect(d.status).toBe(200);
  return { ...p, draftId: d.body.draft_id as string, keys: (t.body.result.attached as Array<{ key: string }>).map((a) => a.key) };
}

beforeEach(async () => {
  await seed();
  await env.DB.prepare("UPDATE outbox SET status = 'sent' WHERE channel = 'personal' AND status IN ('queued','leased')").run();
});

describe('GET /staff/menu-images and thumbnails', () => {
  it('lists the sendable slides with claim flags, the overview covers and the groups', async () => {
    const r = await staff('GET', '/staff/menu-images');
    expect(r.status).toBe(200);
    expect(r.body.max_images).toBe(10);
    expect(r.body.overview).toEqual(['facial/1', 'healing/1', 'thu-gian-toc/1', 'hair-removal/1']);
    expect(r.body.groups.map((g: { group: string }) => g.group)).toEqual(['facial', 'healing', 'thu-gian-toc', 'hair-removal']);
    const healing = r.body.groups.find((g: { group: string }) => g.group === 'healing');
    expect(healing.price_list).toEqual(['healing/2', 'healing/5', 'healing/8', 'healing/11', 'healing/14', 'healing/17']);
    const keys = r.body.slides.map((s: { key: string }) => s.key);
    expect(keys).not.toContain('hair-removal/3'); // the internal customer form is never offered
    expect(r.body.slides).toHaveLength(MENU_INDEX.slides.length - 1);
    expect(r.body.slides.every((s: { thumb: boolean }) => s.thumb)).toBe(true);
    expect(r.body.slides.find((s: { key: string }) => s.key === 'healing/17')).toMatchObject({ has_medical_claim: true, group_label: 'Giúp bạn khỏe' });
  });

  it('serves a JPEG thumbnail for an index key only, to staff only', async () => {
    const ok = await call('GET', '/staff/menu-images/facial/2', { authorization: 'Bearer test-staff-token' });
    expect(ok.status).toBe(200);
    expect(ok.headers.get('content-type')).toBe('image/jpeg');
    const bytes = new Uint8Array(await ok.arrayBuffer());
    expect([bytes[0], bytes[1]]).toEqual([0xff, 0xd8]);
    expect(bytes.length).toBe(atob(MENU_THUMBS['facial/2']!).length);
    for (const bad of ['/staff/menu-images/facial/99', '/staff/menu-images/hair-removal/3', '/staff/menu-images/x/1', '/staff/menu-images/..%2F..%2Fetc/passwd']) {
      expect((await call('GET', bad, { authorization: 'Bearer test-staff-token' })).status, bad).toBe(404);
    }
    expect((await call('GET', '/staff/menu-images/facial/2', {})).status).toBe(401);
  });
});

describe('draft attachments in the staff view', () => {
  it('lists the attached keys and approves only the images staff kept', async () => {
    const d = await draftWithImages({ group: 'thu-gian-toc', service_id: 'none' });
    expect(d.keys).toEqual(['thu-gian-toc/2', 'thu-gian-toc/5', 'thu-gian-toc/8', 'thu-gian-toc/10']);
    const view = await staff('GET', `/staff/conversations/${d.cid}`);
    const draft = view.body.drafts.find((x: { id: string }) => x.id === d.draftId);
    expect(draft.attachments).toEqual(d.keys);
    expect((await staff('POST', `/staff/drafts/${d.draftId}/approve`, { attachments: 'thu-gian-toc/5' })).status).toBe(422);
    const a = await staff('POST', `/staff/drafts/${d.draftId}/approve`, { attachments: ['thu-gian-toc/5', 'thu-gian-toc/10'] });
    expect(a.status).toBe(200);
    const image = (await outboxOf(d.threadId)).find((r) => r.kind === 'cs_images')!;
    expect(JSON.parse(image.image_keys)).toEqual(['thu-gian-toc/5', 'thu-gian-toc/10']);
  });

  it('sends the text only when staff remove every image', async () => {
    const d = await draftWithImages({ group: 'none', service_id: 'goi-dau-thu-gian' });
    const a = await staff('POST', `/staff/drafts/${d.draftId}/approve`, { attachments: [] });
    expect(a.status).toBe(200);
    const rows = await outboxOf(d.threadId);
    expect(rows.some((r) => r.kind === 'cs_images')).toBe(false);
    expect(rows.filter((r) => r.kind === 'cs_text' && r.status === 'queued')).toHaveLength(1);
  });
});

describe('POST /staff/conversations/:id/menu-images ("Gửi menu")', () => {
  it('queues the overview covers as one staff image row the bridge can claim at once', async () => {
    const p = await personalCustomer();
    const r = await staff('POST', `/staff/conversations/${p.cid}/menu-images`, { group: 'overview' });
    expect(r.status).toBe(200);
    expect(r.body.keys).toEqual(['facial/1', 'healing/1', 'thu-gian-toc/1', 'hair-removal/1']);
    expect(r.body.message).toMatchObject({ kind: 'image', source: 'staff', staff_id: 'tester', send_state: 'pending' });
    expect(r.body.message.text).toBe('[Ảnh menu, 4 ảnh] Chăm sóc da cơ bản (ảnh 1); Giúp bạn khỏe (ảnh 1); Thư giãn và chăm sóc tóc (ảnh 1); Triệt lông (ảnh 1)');
    const row = (await outboxOf(p.threadId)).find((x) => x.id === r.body.outbox_id)!;
    expect(row).toMatchObject({ kind: 'cs_images', status: 'queued', depends_on: null });
    expect((await convOf(p.threadId)).bot_state).toBe('bot_active'); // the bot keeps answering
    const c = await claimImages();
    expect(c.item).toMatchObject({ id: r.body.outbox_id, kind: 'cs_images', images: r.body.keys });
    const audit = await env.DB.prepare("SELECT after_json FROM audit_log WHERE action = 'message.menu_images' AND entity_id = ?").bind(p.cid).first<{ after_json: string }>();
    expect(JSON.parse(audit!.after_json)).toMatchObject({ group: 'overview', images: 4, claim_slides: 0 });
  });

  it('sends a group without its claim slides unless staff confirm them', async () => {
    const p = await personalCustomer();
    const plain = await staff('POST', `/staff/conversations/${p.cid}/menu-images`, { group: 'healing' });
    expect(plain.status).toBe(200);
    expect(plain.body.keys).toEqual(['healing/5', 'healing/8']);
    const refused = await staff('POST', `/staff/conversations/${p.cid}/menu-images`, { group: 'healing', keys: ['healing/2', 'healing/5'] });
    expect(refused.status).toBe(422);
    expect(refused.body.error.details).toMatchObject({ field: 'include_claim_slides', claim_keys: ['healing/2'] });
    const confirmed = await staff('POST', `/staff/conversations/${p.cid}/menu-images`, { group: 'healing', keys: ['healing/5', 'healing/2'], include_claim_slides: true });
    expect(confirmed.status).toBe(200);
    expect(confirmed.body.keys).toEqual(['healing/2', 'healing/5']);
  });

  it('refuses keys outside the choice, unknown groups, a disabled outbound flag and OA customers', async () => {
    const p = await personalCustomer();
    const path = `/staff/conversations/${p.cid}/menu-images`;
    expect((await staff('POST', path, { group: 'facial', keys: ['healing/5'] })).body.error.details.field).toBe('keys');
    expect((await staff('POST', path, { group: 'spa' })).body.error.details.field).toBe('group');
    expect((await staff('POST', path, { group: 'facial', keys: [] })).status).toBe(422);
    expect((await staff('POST', path, { group: 'facial', include_claim_slides: 'yes' })).status).toBe(422);
    expect((await staff('POST', '/staff/conversations/cnv_nope/menu-images', { group: 'overview' })).status).toBe(404);
    await setFlags({ outbound_enabled: false });
    expect((await staff('POST', path, { group: 'overview' })).body.error.code).toBe('outbound_disabled');
    await setFlags({ outbound_enabled: true });
    const oa = await consentedCustomer();
    const r = await staff('POST', `/staff/conversations/${oa.cid}/menu-images`, { group: 'overview' });
    expect(r.status).toBe(409);
    expect(r.body.error.code).toBe('invalid_state');
  });
});
