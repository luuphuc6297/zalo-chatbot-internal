// Rooms feed of the runner API (docs/contracts.md section 14.7): POST /runner/rooms/feed and POST /runner/rooms/ack.
// Which conversations are eligible, which rows wait, what the observation list leaves to the draft turn, and what an
// ack marks. Every name, phone number, id and text is synthetic.
import { env, SELF } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { consentedCustomer, draftBody, runner, say, seed, setFlags, staff, uniq } from './core-helpers';
import { ask, claimOwn, consentedThread, convOf, ingest, messagesOf, personalJob, quietDebounce, sendNext, settle, thread, write, type PersonalContact } from './personal-helpers';

const DAY = 86_400_000;
// Tests that send many messages through the webhook or the conversation object: the default 5 s timed out under
// machine load (2026-11-12).
const MANY_INGESTS_MS = 30_000;
const MESSAGE_KEYS = ['at', 'direction', 'kind', 'message_id', 'seq', 'source', 'text'];
const CONVERSATION_KEYS = ['conversation_id', 'customer_display_name', 'messages'];

beforeEach(async () => {
  await seed(); // rooms_enabled is false after the seed
  await settle();
  // the database is shared by the tests of this file: rows left by an earlier test wait no more
  await env.DB.prepare('UPDATE messages SET room_mirrored_at = 1 WHERE room_mirrored_at IS NULL').run();
});

const feed = (body: unknown = {}) => runner('/runner/rooms/feed', body);
const ack = (body: unknown) => runner('/runner/rooms/ack', body);
const on = () => setFlags({ rooms_enabled: true });

/** The draft-turn feed of one conversation: the list of conversations it answers (one entry or none). */
async function turn(cid: string, extra: Record<string, unknown> = {}): Promise<any[]> {
  const r = await feed({ conversation_id: cid, ...extra });
  expect(r.status).toBe(200);
  expect(r.body.enabled).toBe(true);
  return r.body.conversations;
}

/** The observation list. */
async function observed(limit?: number): Promise<any[]> {
  const r = await feed(limit === undefined ? {} : { limit });
  expect(r.status).toBe(200);
  expect(r.body.enabled).toBe(true);
  return r.body.conversations;
}

const idsOf = (list: any[]) => list.map((c) => c.conversation_id);
const seqsOf = (conv: any) => conv.messages.map((m: any) => m.seq);
const mirroredAt = async (messageId: string) => (await env.DB.prepare('SELECT room_mirrored_at AS at FROM messages WHERE id = ?').bind(messageId).first<{ at: number | null }>())!.at;
const takeover = async (cid: string) => expect((await staff('POST', `/staff/conversations/${cid}/takeover`, {})).status).toBe(200);

/**
 * A consented contact who also asked one question (seq 5); the bot may draft a reply. The debounce alarm is removed,
 * so no draft job is ever queued for this contact: the feed does not depend on one, and a job queued by the alarm
 * 10 s later would be leased by a claim meant for another contact.
 */
async function asking(text = 'gội đầu bao nhiêu tiền ạ'): Promise<PersonalContact> {
  const p = await consentedThread();
  expect((await write(p.threadId, text)).status).toBe(200);
  await quietDebounce(p.threadId);
  return p;
}

describe('POST /runner/rooms/feed', () => {
  it('needs the runner token', async () => {
    await on();
    const call = (headers: Record<string, string>) => SELF.fetch('https://bot.test/runner/rooms/feed', { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: '{}' });
    expect((await call({})).status).toBe(401);
    expect((await call({ authorization: 'Bearer test-staff-token', 'x-runner-id': 'mac-1' })).status).toBe(401);
    expect((await call({ authorization: 'Bearer test-runner-token' })).status).toBe(400);
    const ackCall = await SELF.fetch('https://bot.test/runner/rooms/ack', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
    expect(ackCall.status).toBe(401);
  });

  it('answers enabled false while the flag rooms_enabled is false, whatever the body', async () => {
    const p = await asking();
    await takeover(p.cid);
    for (const body of [{}, { conversation_id: p.cid }, { conversation_id: p.cid, seed: true }, { limit: 'many' }, { seed: true }]) {
      const r = await feed(body);
      expect(r.status).toBe(200);
      expect(r.body).toEqual({ enabled: false, conversations: [] });
    }
    await on();
    expect(idsOf(await observed())).toEqual([p.cid]);
  });

  it('a draft turn gets the rows written after the consent, oldest first, with the documented fields only', async () => {
    await on();
    const p = await asking();
    await env.DB.prepare("UPDATE customers SET phone = '0901234567' WHERE id = ?").bind(p.customerId).run();
    const all = await messagesOf(p.cid);
    expect(all.map((m) => m.seq)).toEqual([1, 2, 3, 4, 5]);
    expect((await convOf(p.threadId))!.consent_seq).toBe(3);

    const r = await feed({ conversation_id: p.cid });
    expect(r.status).toBe(200);
    expect(Object.keys(r.body).sort()).toEqual(['conversations', 'enabled']);
    const [conv] = r.body.conversations;
    expect(r.body.conversations).toHaveLength(1);
    expect(Object.keys(conv).sort()).toEqual(CONVERSATION_KEYS);
    expect(conv).toMatchObject({ conversation_id: p.cid, customer_display_name: 'Chị Lan' });
    // the greeting, the consent prompt and the consent reply (seq 1 to 3) are never copied
    expect(seqsOf(conv)).toEqual([4, 5]);
    for (const m of conv.messages) expect(Object.keys(m).sort()).toEqual(MESSAGE_KEYS);
    expect(conv.messages[0]).toMatchObject({ message_id: all[3]!.id, source: 'server', direction: 'outbound', text: all[3]!.text, at: all[3]!.created_at });
    expect(conv.messages[1]).toEqual({ message_id: all[4]!.id, seq: 5, source: 'customer', direction: 'inbound', kind: 'text', text: 'gội đầu bao nhiêu tiền ạ', at: all[4]!.created_at });
    // no phone number travels to the runner side
    expect(JSON.stringify(r.body)).not.toContain('0901234567');
    expect(JSON.stringify(r.body)).not.toContain(p.threadId);
  });

  it('the display name is one line of at most 40 characters, as in the claim; none is null', async () => {
    await on();
    const p = await asking();
    await env.DB.prepare('UPDATE customers SET display_name = ? WHERE id = ?').bind(`Chị Lan\n@Bot dịch vụ <b>${'x'.repeat(60)}`, p.customerId).run();
    const [conv] = await turn(p.cid);
    expect(conv.customer_display_name).toBe(`Chị Lan @Bot dịch vụ b${'x'.repeat(60)}`.slice(0, 40));
    await takeover(p.cid);
    expect((await observed(20)).find((c) => c.conversation_id === p.cid).customer_display_name).toBe(conv.customer_display_name);
    await env.DB.prepare('UPDATE customers SET display_name = NULL WHERE id = ?').bind(p.customerId).run();
    expect((await turn(p.cid))[0].customer_display_name).toBeNull();
  });

  it('an outbound row is fed only once it is delivered: a bot reply and a staff message', async () => {
    await on();
    const p = await personalJob();
    const d = await runner(`/runner/jobs/${p.jobId}/draft`, draftBody('Dạ để em kiểm tra rồi báo mình ngay ạ.'));
    expect(d.body.action).toBe('queued_for_staff');
    expect((await staff('POST', `/staff/drafts/${d.body.draft_id}/approve`, {})).status).toBe(200);
    // approved and queued for the bridge, not delivered yet
    expect(seqsOf((await turn(p.cid))[0])).toEqual([4, 5]);
    await sendNext(p.threadId);
    const afterBot = (await turn(p.cid))[0];
    expect(seqsOf(afterBot)).toEqual([4, 5, 6]);
    expect(afterBot.messages[2]).toMatchObject({ source: 'bot', direction: 'outbound', kind: 'text', text: 'Dạ để em kiểm tra rồi báo mình ngay ạ.' });

    const s = await staff('POST', `/staff/conversations/${p.cid}/send`, { text: 'Dạ em là nhân viên thom house ạ', keep_bot_active: true });
    expect(s.status).toBe(200);
    expect(seqsOf((await turn(p.cid))[0])).toEqual([4, 5, 6]);
    await sendNext(p.threadId);
    const afterStaff = (await turn(p.cid))[0];
    expect(seqsOf(afterStaff)).toEqual([4, 5, 6, 7]);
    expect(afterStaff.messages[3]).toMatchObject({ source: 'staff', direction: 'outbound', text: 'Dạ em là nhân viên thom house ạ' });
  });

  it('rows that are never fed: no text, a user_info row, a failed send, and a row older than 14 days', async () => {
    await on();
    const p = await consentedThread();
    for (const text of ['một', 'hai', 'ba', 'bốn', 'năm']) expect((await ingest(p.threadId, text)).action).toBe('debounced');
    await quietDebounce(p.threadId);
    const rows = await messagesOf(p.cid);
    const bySeq = (seq: number) => rows.find((m) => m.seq === seq)!.id;
    const now = Date.now();
    await env.DB.batch([
      env.DB.prepare('UPDATE messages SET text = NULL WHERE id = ?').bind(bySeq(5)),
      env.DB.prepare("UPDATE messages SET kind = 'user_info' WHERE id = ?").bind(bySeq(6)),
      env.DB.prepare('UPDATE messages SET created_at = ? WHERE id = ?').bind(now - 14 * DAY - 60_000, bySeq(7)),
      env.DB.prepare('UPDATE messages SET created_at = ? WHERE id = ?').bind(now - 14 * DAY + 600_000, bySeq(8)),
      env.DB.prepare("UPDATE messages SET send_state = 'failed' WHERE id = ?").bind(bySeq(4)),
    ]);
    expect(seqsOf((await turn(p.cid))[0])).toEqual([8, 9]);
    // the same rule decides the context of a new room
    expect(seqsOf((await turn(p.cid, { seed: true }))[0])).toEqual([8, 9]);
    for (const state of ['pending', 'unknown', 'not_applicable']) {
      await env.DB.prepare('UPDATE messages SET send_state = ? WHERE id = ?').bind(state, bySeq(4)).run();
      expect(seqsOf((await turn(p.cid))[0])).toEqual([8, 9]);
    }
    await env.DB.prepare("UPDATE messages SET send_state = 'sent' WHERE id = ?").bind(bySeq(4)).run();
    expect(seqsOf((await turn(p.cid))[0])).toEqual([4, 8, 9]);
  }, MANY_INGESTS_MS);

  it('a conversation that is not eligible answers no conversation and is never observed', async () => {
    await on();
    // the official account channel
    const oa = await consentedCustomer(uniq('u_'));
    await say(oa.userId, 'gội đầu bao nhiêu tiền ạ');
    await takeover(oa.cid);
    // a personal contact who has not consented
    const fresh = thread();
    expect((await ingest(fresh, 'chào shop')).action).toBe('consent_prompt_sent');
    await sendNext(fresh);
    await write(fresh, 'cho mình hỏi giá');
    const freshCid = (await convOf(fresh))!.id;
    // consent withdrawn later
    const withdrawn = await asking();
    await env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, recorded_at) VALUES (?, ?, 'ai_assistant', 'withdrawn', 'staff', ?)")
      .bind(uniq('cns_'), withdrawn.customerId, Date.now() + 1000)
      .run();
    // a minor
    const minor = await asking();
    await env.DB.prepare('UPDATE customers SET minor_flag = 1 WHERE id = ?').bind(minor.customerId).run();
    // a deleted customer
    const deleted = await asking();
    await env.DB.prepare('UPDATE customers SET deleted_at = ? WHERE id = ?').bind(Date.now(), deleted.customerId).run();
    // internal contacts
    const manager = await asking();
    const staffMember = await asking();
    for (const [p, role] of [[manager, 'manager'], [staffMember, 'staff']] as const) {
      expect((await staff('PUT', `/staff/roles/${encodeURIComponent(p.zalo)}`, { role })).status).toBe(200);
    }
    // eligible ones: an ordinary contact and one with the role customer
    const plain = await asking();
    const marked = await asking();
    expect((await staff('PUT', `/staff/roles/${encodeURIComponent(marked.zalo)}`, { role: 'customer' })).status).toBe(200);
    for (const p of [plain, marked]) await takeover(p.cid);

    for (const cid of [oa.cid, freshCid, withdrawn.cid, minor.cid, deleted.cid, manager.cid, staffMember.cid, 'cnv_does_not_exist']) {
      expect(await turn(cid)).toEqual([]);
      expect(await turn(cid, { seed: true })).toEqual([]);
    }
    expect(seqsOf((await turn(plain.cid))[0])).toEqual([4, 5]);
    expect(seqsOf((await turn(marked.cid))[0])).toEqual([4, 5]);
    expect(idsOf(await observed(20)).sort()).toEqual([plain.cid, marked.cid].sort());

    // the role removed: the conversation is fed again
    expect((await staff('PUT', `/staff/roles/${encodeURIComponent(manager.zalo)}`, { role: null })).status).toBe(200);
    expect(seqsOf((await turn(manager.cid))[0])).toEqual([4, 5]);
  }, MANY_INGESTS_MS);

  it('a consent given again starts a new window: the rows before the new consent are not fed', async () => {
    await on();
    const p = await asking();
    await env.DB.prepare('UPDATE conversations SET consent_seq = 5 WHERE id = ?').bind(p.cid).run();
    expect((await turn(p.cid))[0].messages).toEqual([]);
    expect((await ingest(p.threadId, 'massage chân bao nhiêu ạ')).action).toBe('debounced');
    await quietDebounce(p.threadId);
    expect(seqsOf((await turn(p.cid))[0])).toEqual([6]);
    expect(seqsOf((await turn(p.cid, { seed: true }))[0])).toEqual([6]);
  });

  it('the observation list leaves a conversation to its draft turn and takes the ones no draft will deliver', async () => {
    await on();
    const draftable = await asking(); // bot_active, a question waits: the draft turn copies these rows
    const taken = await asking();
    await takeover(taken.cid);
    const modeOff = await asking();
    expect((await staff('PUT', `/staff/conversations/${modeOff.cid}/mode`, { mode: 'off' })).status).toBe(200);
    const quiet = await consentedThread(); // only the consent confirmation waits: no customer row
    const handed = await personalJob('cho em hỏi giá gội đầu');
    const h = await runner('/runner/tools/handoff_to_staff', { job_id: handed.jobId, input: { reason_code: 'customer_request', urgency: 'normal', summary_for_staff: 'Khách hỏi giá.' } });
    expect(h.body.is_error).toBe(false);
    expect((await convOf(handed.threadId))!.bot_state).toBe('handoff_requested');

    const list = await observed(20);
    expect(idsOf(list).sort()).toEqual([taken.cid, modeOff.cid, quiet.cid, handed.cid].sort());
    expect(seqsOf(list.find((c) => c.conversation_id === taken.cid))).toEqual([4, 5]);
    expect(seqsOf(list.find((c) => c.conversation_id === quiet.cid))).toEqual([4]);
    for (const c of list) expect(Object.keys(c).sort()).toEqual(CONVERSATION_KEYS);
    // the draft turn still reads the conversation the list left out
    expect(seqsOf((await turn(draftable.cid))[0])).toEqual([4, 5]);

    // a blocker that covers every conversation: nothing will be drafted, so everything is observed
    await setFlags({ ai_calls_enabled: false });
    expect(idsOf(await observed(20))).toContain(draftable.cid);
    await setFlags({ ai_calls_enabled: true });
    expect(idsOf(await observed(20))).not.toContain(draftable.cid);
    await setFlags({ auto_reply_mode: 'off' });
    expect(idsOf(await observed(20))).toContain(draftable.cid);
    await setFlags({ auto_reply_mode: 'approve_each' });

    // once the question is answered by staff only the outbound rows wait, and the list takes them
    await env.DB.prepare('UPDATE messages SET room_mirrored_at = ? WHERE conversation_id = ? AND seq = 5').bind(Date.now(), draftable.cid).run();
    expect(idsOf(await observed(20))).toContain(draftable.cid);
  }, MANY_INGESTS_MS);

  it('the observation list is ordered by the oldest waiting row and cut at limit', async () => {
    await on();
    const made: PersonalContact[] = [];
    for (let i = 0; i < 6; i++) made.push(await consentedThread());
    // made[5] has the oldest waiting row, made[0] the newest
    const base = Date.now() - 3_600_000;
    await env.DB.batch(made.map((p, i) => env.DB.prepare('UPDATE messages SET created_at = ? WHERE conversation_id = ? AND seq = 4').bind(base - i * 60_000, p.cid)));
    const oldestFirst = made.map((p) => p.cid).reverse();

    expect(idsOf(await observed())).toEqual(oldestFirst.slice(0, 5)); // default 5
    expect(idsOf(await observed(2))).toEqual(oldestFirst.slice(0, 2));
    expect(idsOf(await observed(6))).toEqual(oldestFirst);
    expect(idsOf(await observed(500))).toEqual(oldestFirst);

    for (const limit of [0, -1, 1.5, '3', true]) {
      const r = await feed({ limit });
      expect(r.status).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field: 'limit' } });
    }
    for (const body of [{ conversation_id: 7 }, { conversation_id: '' }]) {
      const r = await feed(body);
      expect(r.status).toBe(422);
      expect(r.body.error.details).toEqual({ field: 'conversation_id' });
    }
    for (const body of [{ seed: true }, { seed: 'yes', conversation_id: made[0]!.cid }]) {
      const r = await feed(body);
      expect(r.status).toBe(422);
      expect(r.body.error.details).toEqual({ field: 'seed' });
    }
    const notObject = await feed([]);
    expect(notObject.status).toBe(422);
  }, MANY_INGESTS_MS);

  it('at most 20 conversations are observed however large limit is', async () => {
    await on();
    for (let i = 0; i < 21; i++) await consentedThread();
    expect(await observed(20)).toHaveLength(20);
    expect(await observed(1000)).toHaveLength(20);
  }, MANY_INGESTS_MS);

  it('row limits: 50 rows for an observed conversation, 100 for a draft turn, the last 20 for a seed', async () => {
    await on();
    const p = await consentedThread();
    for (let i = 1; i <= 101; i++) await ingest(p.threadId, `tin ${i}`);
    await quietDebounce(p.threadId);
    const rows = await messagesOf(p.cid);
    expect(rows).toHaveLength(105);
    const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

    expect(seqsOf((await turn(p.cid))[0])).toEqual(range(4, 103));
    const seedRows = (await turn(p.cid, { seed: true }))[0];
    expect(seqsOf(seedRows)).toEqual(range(86, 105));
    expect(seedRows.messages[19].text).toBe('tin 101');

    await takeover(p.cid);
    const [conv] = await observed();
    expect(conv.conversation_id).toBe(p.cid);
    expect(seqsOf(conv)).toEqual(range(4, 53));

    // the runner acks what it copied and the next call continues after it
    const first = await ack({ conversation_id: p.cid, message_ids: conv.messages.map((m: any) => m.message_id) });
    expect(first.body).toEqual({ ok: true, marked: 50 });
    expect(seqsOf((await observed())[0])).toEqual(range(54, 103));
    // a seed ignores what was copied before
    expect(seqsOf((await turn(p.cid, { seed: true }))[0])).toEqual(range(86, 105));
  }, MANY_INGESTS_MS);
});

describe('POST /runner/rooms/ack', () => {
  it('marks the rows once: a repeated call marks nothing and keeps the first time', async () => {
    await on();
    const p = await asking();
    const other = await asking();
    const [conv] = await turn(p.cid);
    const ids: string[] = conv.messages.map((m: any) => m.message_id);
    const otherIds: string[] = (await turn(other.cid))[0].messages.map((m: any) => m.message_id);

    const a = await ack({ conversation_id: p.cid, message_ids: [ids[0], ids[0], otherIds[0], 'msg_does_not_exist'] });
    expect(a.status).toBe(200);
    expect(a.body).toEqual({ ok: true, marked: 1 });
    const at = await mirroredAt(ids[0]!);
    expect(at).toBeGreaterThan(1);
    // a row of another conversation is not marked through this conversation
    expect(await mirroredAt(otherIds[0]!)).toBeNull();
    expect(seqsOf((await turn(p.cid))[0])).toEqual([5]);
    expect(seqsOf((await turn(other.cid))[0])).toEqual([4, 5]);

    const b = await ack({ conversation_id: p.cid, message_ids: ids });
    expect(b.body).toEqual({ ok: true, marked: 1 });
    const again = await ack({ conversation_id: p.cid, message_ids: ids });
    expect(again.body).toEqual({ ok: true, marked: 0 });
    expect(await mirroredAt(ids[0]!)).toBe(at);
    // an eligible conversation with nothing waiting still answers one entry
    expect(await turn(p.cid)).toEqual([{ conversation_id: p.cid, customer_display_name: 'Chị Lan', messages: [] }]);
    expect(idsOf(await observed(20))).not.toContain(p.cid);
    // nothing was sent to the contact and nothing was flagged by the calls
    expect((await convOf(p.threadId))!.bot_state).toBe('bot_active');
  }, MANY_INGESTS_MS);

  it('stores the room, and the staff detail shows it with the number of rows still waiting', async () => {
    await on();
    const p = await asking();
    const before = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(before.body).not.toHaveProperty('room');

    const ids: string[] = (await turn(p.cid))[0].messages.map((m: any) => m.message_id);
    const t0 = Date.now();
    const a = await ack({ conversation_id: p.cid, message_ids: [ids[0]], room: { channel_id: 'room-chi-lan-01' } });
    expect(a.body).toEqual({ ok: true, marked: 1 });
    const conv = (await convOf(p.threadId))!;
    expect(conv.room_channel_id).toBe('room-chi-lan-01');
    expect(conv.room_synced_at).toBeGreaterThanOrEqual(t0);

    const detail = await staff('GET', `/staff/conversations/${p.cid}`);
    expect(detail.body.room).toEqual({ channel_id: 'room-chi-lan-01', synced_at: conv.room_synced_at, pending: 1 });

    // a call with no ids only refreshes the room
    const b = await ack({ conversation_id: p.cid, message_ids: [], room: { channel_id: 'room-chi-lan-02' } });
    expect(b.body).toEqual({ ok: true, marked: 0 });
    expect((await convOf(p.threadId))!.room_channel_id).toBe('room-chi-lan-02');
    // without `room` the stored room stays
    const c = await ack({ conversation_id: p.cid, message_ids: ids });
    expect(c.body).toEqual({ ok: true, marked: 1 });
    expect((await staff('GET', `/staff/conversations/${p.cid}`)).body.room).toMatchObject({ channel_id: 'room-chi-lan-02', pending: 0 });
  });

  it('refuses a bad body with 422 and an unknown conversation with 404, and changes nothing', async () => {
    await on();
    const p = await asking();
    const ids: string[] = (await turn(p.cid))[0].messages.map((m: any) => m.message_id);
    const bad: Array<[unknown, string]> = [
      [{ message_ids: ids }, 'conversation_id'],
      [{ conversation_id: '', message_ids: ids }, 'conversation_id'],
      [{ conversation_id: p.cid }, 'message_ids'],
      [{ conversation_id: p.cid, message_ids: 'all' }, 'message_ids'],
      [{ conversation_id: p.cid, message_ids: [ids[0], 5] }, 'message_ids'],
      [{ conversation_id: p.cid, message_ids: [''] }, 'message_ids'],
      [{ conversation_id: p.cid, message_ids: Array.from({ length: 201 }, (_, i) => `msg_x${i}`) }, 'message_ids'],
      [{ conversation_id: p.cid, message_ids: ids, room: {} }, 'room.channel_id'],
      [{ conversation_id: p.cid, message_ids: ids, room: { channel_id: '  ' } }, 'room.channel_id'],
      [{ conversation_id: p.cid, message_ids: ids, room: { channel_id: 'x'.repeat(201) } }, 'room.channel_id'],
      [{ conversation_id: p.cid, message_ids: ids, room: 'room-1' }, 'room.channel_id'],
    ];
    for (const [body, field] of bad) {
      const r = await ack(body);
      expect(r.status).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field } });
    }
    const unknown = await ack({ conversation_id: 'cnv_does_not_exist', message_ids: ids });
    expect(unknown.status).toBe(404);
    expect(seqsOf((await turn(p.cid))[0])).toEqual([4, 5]);
    expect((await convOf(p.threadId))!.room_channel_id).toBeNull();

    const full = await ack({ conversation_id: p.cid, message_ids: Array.from({ length: 200 }, (_, i) => `msg_x${i}`) });
    expect(full.body).toEqual({ ok: true, marked: 0 });
  });

  it('is accepted while the flag is false: a row copied before the flag was turned off is still recorded', async () => {
    await on();
    const p = await asking();
    const ids: string[] = (await turn(p.cid))[0].messages.map((m: any) => m.message_id);
    await setFlags({ rooms_enabled: false });
    expect((await feed({ conversation_id: p.cid })).body).toEqual({ enabled: false, conversations: [] });
    expect((await ack({ conversation_id: p.cid, message_ids: ids })).body).toEqual({ ok: true, marked: 2 });
  });
});

describe('rooms feed and the draft pipeline', () => {
  it('reading and acking the feed sends nothing and does not change the draft job of the conversation', async () => {
    await on();
    const p = await consentedThread();
    await ask(p.threadId);
    const outboxBefore = await env.DB.prepare('SELECT COUNT(*) AS n FROM outbox').first<{ n: number }>();
    const ids: string[] = (await turn(p.cid))[0].messages.map((m: any) => m.message_id);
    await ack({ conversation_id: p.cid, message_ids: ids, room: { channel_id: 'room-x' } });
    await observed(20);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM outbox').first<{ n: number }>()).toEqual(outboxBefore);
    // the one queued draft job of the conversation is still there and can be leased
    await claimOwn(p.cid);
    expect((await convOf(p.threadId))!.needs_attention).toBe(0);
  });
});
