// Menu images (task B): the attach_menu_images tool (slide picking, claim-slide refusal, the 10-image cap), draft
// attachments and the checker rule, approve -> text row then cs_images row, bridge claims with the 'images'
// capability, lease scaling, cancellation of images whose text was not sent, and echo matching of self-sent photos
// (by msgId, by time when msgIds are missing, and owner photos that still mean a staff takeover).
import { createExecutionContext, env, runDurableObjectAlarm, waitOnExecutionContext } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { app } from '../src/index';
import { checkDraft } from '../src/checker';
import { IMAGE_ECHO_WINDOW_MS, leaseMsFor } from '../src/bridge/outbox';
import { MENU_INDEX, isMenuImageKey, menuImagesLabel } from '../src/lib/menu-images';
import { conversationObjectName, type Env, type PersonalWebhookEvent } from '../src/types';
import { claim as claimJob, customerWithJob, draftBody, runner, seed, setFlags, staff } from './core-helpers';

const SECRET = 'test-personal-webhook-secret';
let n = 0;
const uniq = (p: string) => `${p}${Date.now().toString(36)}${++n}`;
const thread = () => uniq('9300');
const tool = (jobId: string, input: unknown) => runner('/runner/tools/attach_menu_images', { job_id: jobId, input });
const keysOf = (r: any): string[] => (r.body.result.attached ?? []).map((a: any) => a.key);

async function hmacHex(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function postPersonal(body: unknown) {
  const raw = JSON.stringify(body);
  const headers = { 'content-type': 'application/json', authorization: `Bearer ${SECRET}`, 'x-zalo-signature': `sha256=${await hmacHex(SECRET, raw)}` };
  const ctx = createExecutionContext();
  const res = await app.fetch(new Request('https://bot.test/zalo/personal/webhook', { method: 'POST', body: raw, headers }), env, ctx);
  await waitOnExecutionContext(ctx);
  return { res, json: (await res.json()) as any };
}

function msgEvent(threadId: string, content: unknown, extra: Partial<PersonalWebhookEvent> = {}): PersonalWebhookEvent {
  return {
    event: 'message',
    accountId: 'acc-test',
    msgId: uniq('7700'),
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

/** A photo the account itself sent (the bridge's send-image, or the owner on the phone). */
function selfPhoto(threadId: string, msgId: string | null): PersonalWebhookEvent {
  const ev = msgEvent(threadId, { href: 'https://photo.example/x.jpg', thumb: 'https://photo.example/t.jpg' }, { isSelf: true, uidFrom: '0', dName: 'Owner' });
  if (msgId === null) delete ev.msgId;
  else ev.msgId = msgId;
  return ev;
}

async function bridge(method: string, path: string, body?: unknown, e?: Partial<Env>) {
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, {
      method,
      headers: { authorization: 'Bearer test-runner-token', 'x-bridge-id': 'bridge-img', 'content-type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    { ...env, ...e },
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}
const claimImages = () => bridge('POST', '/bridge/outbox/claim', { capabilities: ['images'] });
const claimTextOnly = () => bridge('POST', '/bridge/outbox/claim', {});
const report = (id: string, body: unknown) => bridge('POST', `/bridge/outbox/${id}/result`, body);

async function convOf(threadId: string) {
  return env.DB.prepare('SELECT c.* FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE cu.zalo_user_id = ?')
    .bind(`p:${threadId}`)
    .first<Record<string, any>>();
}

async function outboxOf(threadId: string) {
  return (await env.DB.prepare("SELECT * FROM outbox WHERE channel = 'personal' AND thread_id = ? ORDER BY created_at, id").bind(threadId).all<Record<string, any>>()).results;
}

async function inboxError(msgId: string) {
  return (await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(`personal:${msgId}`).first<{ status: string; error: string | null }>())!;
}

/** The bridge claims the next row of this thread (text capability is enough) and reports it sent. */
async function sendNextText(threadId: string) {
  const c = await claimImages();
  expect(c.body.item?.thread_id).toBe(threadId);
  await report(c.body.item.id, { status: 'sent', zalo_msg_id: uniq('8800') });
  return c.body.item;
}

/** Personal customer past the consent gate, a question asked and its draft job leased by the runner. */
async function personalJob(question = 'cho em xem menu tóc với ạ'): Promise<{ threadId: string; cid: string; jobId: string }> {
  const threadId = thread();
  await postPersonal(msgEvent(threadId, 'chào shop'));
  await sendNextText(threadId);
  await postPersonal(msgEvent(threadId, 'Đồng ý'));
  await sendNextText(threadId);
  const c = await convOf(threadId);
  expect(c!.bot_state).toBe('bot_active');
  await postPersonal(msgEvent(threadId, question));
  await env.DB.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(Date.now() - 1, c!.id).run();
  await runDurableObjectAlarm(env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName('personal', `p:${threadId}`))));
  const job = await claimJob();
  expect(job.job?.conversation.conversation_id).toBe(c!.id);
  return { threadId, cid: c!.id, jobId: job.job.job_id };
}

/** personalJob + attach_menu_images + draft + staff approve. Returns the text and image outbox rows. */
async function approvedImageDraft(input: { group: string; service_id: string }) {
  const p = await personalJob();
  const t = await tool(p.jobId, input);
  expect(t.body.result.status).toBe('attached');
  const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ em gửi anh/chị ảnh menu ạ.'));
  expect(d.status).toBe(200);
  expect(d.body.status).toBe('pending');
  const a = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
  expect(a.status).toBe(200);
  const rows = await outboxOf(p.threadId);
  const text = rows.find((r) => r.kind === 'cs_text' && r.status === 'queued')!;
  const image = rows.find((r) => r.kind === 'cs_images')!;
  return { ...p, draftId: d.body.draft_id as string, keys: keysOf(t), text, image };
}

beforeEach(async () => {
  await seed();
  // Rows left by earlier tests must not be handed out to this one.
  await env.DB.prepare("UPDATE outbox SET status = 'sent' WHERE channel = 'personal' AND status IN ('queued','leased')").run();
});

// ---------------------------------------------------------------- index and tool

describe('menu index bundled in the server', () => {
  it('has the 57 slides and only catalog service ids', async () => {
    expect(MENU_INDEX.slides).toHaveLength(57);
    const cv = (await env.DB.prepare("SELECT id FROM catalog_versions WHERE status = 'active'").first<{ id: string }>())!.id;
    const ids = new Set((await env.DB.prepare('SELECT service_id FROM services WHERE catalog_version = ?').bind(cv).all<{ service_id: string }>()).results.map((r) => r.service_id));
    for (const g of Object.values(MENU_INDEX.groups)) for (const sid of Object.keys(g.services)) expect(ids.has(sid)).toBe(true);
    expect(isMenuImageKey('facial/1')).toBe(true);
    expect(isMenuImageKey('../../etc/passwd')).toBe(false);
    expect(isMenuImageKey('facial/99')).toBe(false);
    expect(menuImagesLabel(['facial/2', 'facial/4'])).toBe('[Ảnh menu, 2 ảnh] Chăm sóc da cơ bản (ảnh 2, 4)');
  });
});

describe('attach_menu_images', () => {
  it('attaches the overview covers and a group price list, skipping claim slides', async () => {
    await customerWithJob('cho xem menu');
    const job = await claimJob();
    const o = await tool(job.job.job_id, { group: 'overview', service_id: 'none' });
    expect(o.body.is_error).toBe(false);
    expect(keysOf(o)).toEqual(['facial/1', 'healing/1', 'thu-gian-toc/1', 'hair-removal/1']);
    const g = await tool(job.job.job_id, { group: 'thu-gian-toc', service_id: 'none' });
    expect(keysOf(g)).toEqual(['thu-gian-toc/2', 'thu-gian-toc/5', 'thu-gian-toc/8', 'thu-gian-toc/10']);
    expect(g.body.result).toMatchObject({ status: 'attached', skipped_claim_slides: ['thu-gian-toc/13', 'thu-gian-toc/14'], total_attached: 8 });
    // a repeated call adds nothing new
    const again = await tool(job.job.job_id, { group: 'overview', service_id: 'none' });
    expect(again.body.result).toMatchObject({ attached: [], total_attached: 8 });
    // no price_text in the result: the checker's price allow-list stays tool-quote only
    expect(JSON.stringify(g.body.result)).not.toContain('price_text');
  });

  it('refuses claim slides: a service whose price slide prints a claim is staff only', async () => {
    await customerWithJob('ngừa đột quỵ có hình không');
    const job = await claimJob();
    const r = await tool(job.job.job_id, { group: 'none', service_id: 'dien-chan-ngua-dot-quy' });
    expect(r.body).toMatchObject({ is_error: false, result: { status: 'refused', reason: 'medical_claim_slides_staff_only', attached: [] } });
    expect(r.body.result.refused).toEqual(['healing/17', 'healing/18', 'healing/19']);
    // giai-moi-dung-lau: only the process slide 16 is claim-free, so the whole service is refused too
    const g = await tool(job.job.job_id, { group: 'none', service_id: 'giai-moi-dung-lau' });
    expect(g.body.result.status).toBe('refused');
    // a claim-free service attaches its non-claim slides only
    const ok = await tool(job.job.job_id, { group: 'none', service_id: 'goi-dau-thu-gian' });
    expect(keysOf(ok)).toEqual(['thu-gian-toc/5', 'thu-gian-toc/7']);
  });

  it('validates input: exactly one of group / service_id, known service ids', async () => {
    await customerWithJob('menu');
    const job = await claimJob();
    expect((await tool(job.job.job_id, { group: 'none', service_id: 'none' })).body).toMatchObject({ is_error: true, result: { error: 'validation_failed' } });
    expect((await tool(job.job.job_id, { group: 'facial', service_id: 'goi-dau-thu-gian' })).body).toMatchObject({ is_error: true });
    expect((await tool(job.job.job_id, { group: 'none', service_id: 'khong-co' })).body).toMatchObject({ is_error: true, result: { field: 'service_id' } });
    expect((await tool(job.job.job_id, { group: 'spa', service_id: 'none' })).body).toMatchObject({ is_error: true, result: { field: 'group' } });
    expect((await tool(job.job.job_id, { group: 'overview' })).body).toMatchObject({ is_error: true, result: { field: 'service_id' } });
    expect((await tool(job.job.job_id, { group: 'overview', service_id: 'none', path: '/etc/passwd' })).body).toMatchObject({ is_error: true, result: { field: 'path' } });
    // a catalog service without any slide: nothing to attach, not an error
    expect((await tool(job.job.job_id, { group: 'none', service_id: 'massage-chan' })).body.result).toMatchObject({ status: 'no_images' });
  });

  it('caps a draft at 10 images across calls', async () => {
    await customerWithJob('menu da và tóc');
    const job = await claimJob();
    const a = await tool(job.job.job_id, { group: 'facial', service_id: 'none' });
    expect(keysOf(a)).toHaveLength(7);
    const b = await tool(job.job.job_id, { group: 'thu-gian-toc', service_id: 'none' });
    expect(keysOf(b)).toHaveLength(3);
    expect(b.body.result).toMatchObject({ total_attached: 10, dropped_over_limit: ['thu-gian-toc/10'] });
    const c = await tool(job.job.job_id, { group: 'overview', service_id: 'none' });
    expect(c.body.result).toMatchObject({ status: 'limit_reached', attached: [] });
    const d = await runner(`/runner/jobs/${job.job.job_id}/draft`, draftBody('Dạ em gửi menu ạ.'));
    expect(d.body.attachments).toHaveLength(10);
  });
});

describe('draft attachments and the checker', () => {
  it('stores the attachments, never auto-sends a draft with images, and passes the checker', async () => {
    await setFlags({ auto_reply_mode: 'auto_allowed' });
    const c = await customerWithJob('cho xem menu tóc');
    const job = await claimJob();
    await tool(job.job.job_id, { group: 'thu-gian-toc', service_id: 'none' });
    const d = await runner(`/runner/jobs/${job.job.job_id}/draft`, draftBody('Dạ em gửi anh/chị menu chăm sóc tóc ạ.'));
    expect(d.body).toMatchObject({ status: 'pending', action: 'queued_for_staff', attachments: ['thu-gian-toc/2', 'thu-gian-toc/5', 'thu-gian-toc/8', 'thu-gian-toc/10'] });
    expect(d.body.checker.passed).toBe(true);
    const row = await env.DB.prepare('SELECT attachments_json FROM drafts WHERE id = ?').bind(d.body.draft_id).first<{ attachments_json: string }>();
    expect(JSON.parse(row!.attachments_json)).toEqual(d.body.attachments);
    expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM outbox WHERE conversation_id = ? AND kind = 'cs_images'").bind(c.cid).first<{ n: number }>())!.n).toBe(0);
  });

  it('blocks a draft whose attachments include a claim slide (checker rule menu_image)', async () => {
    const unit = checkDraft({ text: 'Dạ em gửi ảnh ạ.', conversation_id: 'c', catalog_version: 'v', allowed_price_texts: [], approved_contact_values: [], display_names: [], attachment_keys: ['healing/17', 'facial/1'] });
    expect(unit.passed).toBe(false);
    expect(unit.issues).toEqual([expect.objectContaining({ rule: 'menu_image', excerpt: 'healing/17' })]);
    expect(checkDraft({ text: 'x', conversation_id: 'c', catalog_version: 'v', allowed_price_texts: [], approved_contact_values: [], display_names: [], attachment_keys: ['bogus/1'] }).issues[0]!.rule).toBe('menu_image');

    // A tool_calls row that carries a claim slide (the tool itself never returns one) still cannot reach a customer.
    const c = await customerWithJob('ngừa đột quỵ');
    const job = await claimJob();
    await env.DB.prepare(
      "INSERT INTO tool_calls (id, job_id, conversation_id, tool_name, input_json, result_json, is_error, idempotency_key, catalog_version, created_at) VALUES (?,?,?,'attach_menu_images','{}',?,0,NULL,'',?)",
    )
      .bind(uniq('tcl_'), job.job.job_id, c.cid, JSON.stringify({ status: 'attached', attached: [{ key: 'healing/17' }] }), Date.now())
      .run();
    const d = await runner(`/runner/jobs/${job.job.job_id}/draft`, draftBody('Dạ em gửi ảnh ạ.'));
    expect(d.body.status).toBe('blocked');
    expect(d.body.checker.issues.map((i: any) => i.rule)).toContain('menu_image');
    const a = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
    expect(a.body.error.code).toBe('checker_failed');
  });

  it('an approved draft of an OA customer sends the text only (images are personal-channel only)', async () => {
    const c = await customerWithJob('menu tóc');
    const job = await claimJob();
    await tool(job.job.job_id, { group: 'thu-gian-toc', service_id: 'none' });
    const d = await runner(`/runner/jobs/${job.job.job_id}/draft`, draftBody('Dạ em gửi menu ạ.'));
    const a = await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {});
    expect(a.status).toBe(200);
    expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM outbox WHERE conversation_id = ? AND kind = 'cs_images'").bind(c.cid).first<{ n: number }>())!.n).toBe(0);
    expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND kind = 'image'").bind(c.cid).first<{ n: number }>())!.n).toBe(0);
  });
});

// ---------------------------------------------------------------- approve -> outbox -> bridge (personal channel)

describe('approve queues text first, then one image row', () => {
  it('orders text before images, hands images only to an images-capable bridge, scales the lease', async () => {
    const f = await approvedImageDraft({ group: 'thu-gian-toc', service_id: 'none' });
    expect(f.keys).toEqual(['thu-gian-toc/2', 'thu-gian-toc/5', 'thu-gian-toc/8', 'thu-gian-toc/10']);
    expect(f.image).toMatchObject({ status: 'queued', depends_on: f.text.id, text: menuImagesLabel(f.keys) });
    expect(JSON.parse(f.image.image_keys)).toEqual(f.keys);
    expect(f.image.created_at).toBeGreaterThan(f.text.created_at - 1);
    const msg = await env.DB.prepare('SELECT kind, source, staff_id, send_state, draft_id, attachments_json FROM messages WHERE id = ?').bind(f.image.message_id).first<Record<string, any>>();
    expect(msg).toMatchObject({ kind: 'image', source: 'bot', staff_id: 'tester', send_state: 'pending', draft_id: null });
    expect(JSON.parse(msg!.attachments_json)).toHaveLength(4);

    const first = await claimImages();
    expect(first.body.item).toMatchObject({ id: f.text.id, kind: 'cs_text' });
    expect(first.body.item.images).toBeUndefined();
    // the image row waits while its text row is leased
    expect((await claimImages()).body.item).toBeNull();
    await report(f.text.id, { status: 'sent', zalo_msg_id: uniq('8800') });
    // a bridge without the images capability never gets the image row
    expect((await claimTextOnly()).body.item).toBeNull();
    const before = Date.now();
    const img = await claimImages();
    expect(img.body.item).toMatchObject({ id: f.image.id, kind: 'cs_images', images: f.keys, thread_id: f.threadId, attempt: 1 });
    expect(img.body.item.lease_until).toBeGreaterThanOrEqual(before + leaseMsFor('cs_images', JSON.stringify(f.keys)));
    expect(leaseMsFor('cs_images', JSON.stringify(f.keys))).toBe(60_000 + 4 * 20_000);
    expect(leaseMsFor('cs_text', null)).toBe(60_000);

    const ids = ['91001', '91002', '91003', '91004'];
    const r = await report(f.image.id, { status: 'sent', zalo_msg_id: ids[0], part_msg_ids: ids, attempt: 1 });
    expect(r.body).toMatchObject({ status: 'sent', ignored: false });
    const row = (await outboxOf(f.threadId)).find((x) => x.id === f.image.id)!;
    expect(JSON.parse(row.part_msg_ids)).toEqual(ids);
    expect((await env.DB.prepare('SELECT send_state FROM messages WHERE id = ?').bind(f.image.message_id).first<{ send_state: string }>())!.send_state).toBe('sent');

    // echoes of each image, matched by msgId: ignored, no takeover
    for (const id of ids) {
      await postPersonal(selfPhoto(f.threadId, id));
      expect(await inboxError(id)).toMatchObject({ status: 'ignored', error: `echo:${f.image.id}` });
    }
    expect((await convOf(f.threadId))!.bot_state).toBe('bot_active');
    // an owner photo with another msgId is staff on the phone
    const owner = uniq('9200');
    await postPersonal(selfPhoto(f.threadId, owner));
    expect((await inboxError(owner)).status).toBe('processed');
    expect((await convOf(f.threadId))!.bot_state).toBe('staff_takeover');
  });

  it('matches photo echoes by time while the image row has no msgIds, one per image, within 3 minutes', async () => {
    const f = await approvedImageDraft({ group: 'none', service_id: 'goi-dau-thu-gian' });
    expect(f.keys).toEqual(['thu-gian-toc/5', 'thu-gian-toc/7']);
    await sendNextText(f.threadId);
    const img = await claimImages();
    expect(img.body.item.id).toBe(f.image.id);
    // the bridge has not reported yet: two photos (one with a msgId, one without) are the two echoes
    const e1 = uniq('9400');
    await postPersonal(selfPhoto(f.threadId, e1));
    expect(await inboxError(e1)).toMatchObject({ status: 'ignored', error: `echo:${f.image.id}` });
    const row1 = (await outboxOf(f.threadId)).find((x) => x.id === f.image.id)!;
    expect(row1).toMatchObject({ status: 'sent', echo_count: 1 });
    expect((await env.DB.prepare('SELECT send_state FROM messages WHERE id = ?').bind(f.image.message_id).first<{ send_state: string }>())!.send_state).toBe('sent');
    const noId = selfPhoto(f.threadId, null);
    const res = await postPersonal(noId);
    const key = res.json.results[0].event_key as string;
    const ev = await env.DB.prepare('SELECT status, error FROM events_inbox WHERE event_key = ?').bind(key).first<{ status: string; error: string }>();
    expect(ev).toMatchObject({ status: 'ignored', error: `echo:${f.image.id}` });
    // a third photo is more than the row's 2 images: the owner sent it
    const third = uniq('9400');
    await postPersonal(selfPhoto(f.threadId, third));
    expect((await inboxError(third)).status).toBe('processed');
    expect((await convOf(f.threadId))!.bot_state).toBe('staff_takeover');
    // the bridge's late report still fills the msgIds of the row confirmed by echo
    const late = await report(f.image.id, { status: 'sent', zalo_msg_id: '95001', part_msg_ids: ['95001', '95002'] });
    expect(late.body).toMatchObject({ status: 'sent', ignored: true });
  });

  it('a photo after the 3-minute window, or with an unknown msgId once msgIds are known, is a staff takeover', async () => {
    const f = await approvedImageDraft({ group: 'none', service_id: 'goi-dau-thu-gian' });
    await sendNextText(f.threadId);
    await claimImages();
    await env.DB.prepare('UPDATE outbox SET last_claimed_at = ? WHERE id = ?').bind(Date.now() - IMAGE_ECHO_WINDOW_MS - 5_000, f.image.id).run();
    const late = uniq('9500');
    await postPersonal(selfPhoto(f.threadId, late));
    expect((await inboxError(late)).status).toBe('processed');
    expect((await convOf(f.threadId))!.bot_state).toBe('staff_takeover');

    const g = await approvedImageDraft({ group: 'none', service_id: 'goi-dau-thu-gian' });
    await sendNextText(g.threadId);
    await claimImages();
    await report(g.image.id, { status: 'sent', zalo_msg_id: '96001', part_msg_ids: ['96001', '96002'] });
    const other = uniq('9600');
    await postPersonal(selfPhoto(g.threadId, other));
    expect((await inboxError(other)).status).toBe('processed');
    expect((await convOf(g.threadId))!.bot_state).toBe('staff_takeover');
  });

  it('cancels the image row when its text row ends unknown; staff requeue sends it anyway', async () => {
    const f = await approvedImageDraft({ group: 'none', service_id: 'goi-dau-thu-gian' });
    const t = await claimImages();
    expect(t.body.item.id).toBe(f.text.id);
    await report(f.text.id, { status: 'unknown', error: 'timeout', attempt: 1 });
    expect((await claimImages()).body.item).toBeNull();
    const row = (await outboxOf(f.threadId)).find((x) => x.id === f.image.id)!;
    expect(row.status).toBe('failed');
    expect(row.error).toMatch(/^cancelled: text row not sent \(unknown\)/);
    expect((await env.DB.prepare('SELECT send_state FROM messages WHERE id = ?').bind(f.image.message_id).first<{ send_state: string }>())!.send_state).toBe('failed');

    const d = await staff('POST', `/staff/outbox/${f.image.id}/decide`, { action: 'requeue' });
    expect(d.status).toBe(200);
    const again = await claimImages();
    expect(again.body.item).toMatchObject({ id: f.image.id, kind: 'cs_images', images: f.keys });
    expect((await outboxOf(f.threadId)).find((x) => x.id === f.image.id)!.depends_on).toBeNull();
  });

  it('counts an image row as one send toward the hourly limit', async () => {
    const f = await approvedImageDraft({ group: 'none', service_id: 'goi-dau-thu-gian' });
    await sendNextText(f.threadId);
    await claimImages();
    const s = await bridge('GET', '/bridge/status');
    const claimed = await env.DB.prepare("SELECT COUNT(*) AS n FROM outbox WHERE channel = 'personal' AND last_claimed_at >= ?").bind(Date.now() - 3600_000).first<{ n: number }>();
    expect(s.body.claims_last_hour).toBe(claimed!.n);
    const imageClaims = await env.DB.prepare("SELECT COUNT(*) AS n FROM outbox WHERE id = ? AND last_claimed_at IS NOT NULL").bind(f.image.id).first<{ n: number }>();
    expect(imageClaims!.n).toBe(1);
  });
});
