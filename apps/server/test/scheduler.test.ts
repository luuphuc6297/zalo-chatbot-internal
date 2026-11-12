// server-zalo: cron scheduler (follow-up ZBS sends, kill switches, consent/opt-out, send window, lateness,
// inbox sweep, draft lease fallback).
import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { runCron } from '../src/scheduler/cron';
import { runDueFollowups } from '../src/scheduler/followups';
import { isWithinSendWindow, nextWindowStart } from '../src/scheduler/send-window';
import { expireDraftLeasesFallback, sweepInbox } from '../src/scheduler/sweeps';

const H = 3600 * 1000;
// 2026-11-07 10:00 Asia/Ho_Chi_Minh = 03:00 UTC
const T10_LOCAL = Date.UTC(2026, 10, 7, 3, 0);

let seq = 0;
const uid = (p: string) => `${p}_${Date.now().toString(36)}${++seq}`;

async function setFlag(name: string, value: unknown) {
  await env.DB.prepare('UPDATE flags SET value_json = ? WHERE name = ?').bind(JSON.stringify(value), name).run();
}

interface Seed {
  customerId: string;
  conversationId: string;
  zaloUserId: string;
  visitId: string;
  jobId: string;
}

async function seedFollowup(opts: { consent?: boolean; botState?: string; runAt?: number; type?: 'thank_you' | 'check_in' } = {}): Promise<Seed> {
  const now = T10_LOCAL - 30 * H;
  const s: Seed = { customerId: uid('cus'), conversationId: uid('cnv'), zaloUserId: uid('zu'), visitId: uid('vis'), jobId: uid('job') };
  const stmts = [
    env.DB.prepare('INSERT INTO customers (id, oa_id, zalo_user_id, display_name, created_at) VALUES (?,?,?,?,?)').bind(s.customerId, 'test-oa-id', s.zaloUserId, 'Lan', now),
    env.DB.prepare('INSERT INTO conversations (id, customer_id, oa_id, bot_state, created_at, updated_at) VALUES (?,?,?,?,?,?)').bind(
      s.conversationId, s.customerId, 'test-oa-id', opts.botState ?? 'bot_active', now, now),
    env.DB.prepare("INSERT INTO visits (id, customer_id, service_id, visited_at, created_at) VALUES (?,?, 'goi-dau-thu-gian', ?, ?)").bind(s.visitId, s.customerId, now, now),
    env.DB.prepare(
      "INSERT INTO jobs (id, type, conversation_id, customer_id, status, run_at, max_lateness_ms, payload_json, dedupe_key, created_at, updated_at) VALUES (?,?,?,?, 'queued', ?, ?, ?, ?, ?, ?)",
    ).bind(s.jobId, opts.type ?? 'thank_you', s.conversationId, s.customerId, opts.runAt ?? T10_LOCAL - 10 * 60 * 1000, 6 * H, JSON.stringify({ visit_id: s.visitId }), `${s.visitId}:${opts.type ?? 'thank_you'}`, now, now),
  ];
  if (opts.consent !== false) {
    stmts.push(
      env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, recorded_at) VALUES (?, ?, 'followup_care', 'granted', 'button', ?)").bind(uid('cns'), s.customerId, now),
    );
  }
  await env.DB.batch(stmts);
  return s;
}

async function job(id: string) {
  return env.DB.prepare('SELECT status, run_at, last_error, lease_owner FROM jobs WHERE id = ?').bind(id).first<{ status: string; run_at: number; last_error: string | null; lease_owner: string | null }>();
}

async function outboxFor(zaloUserId: string) {
  return (await env.DB.prepare('SELECT * FROM outbox WHERE zalo_user_id = ?').bind(zaloUserId).all<Record<string, string | number | null>>()).results;
}

beforeEach(async () => {
  await setFlag('scheduled_sends_enabled', false);
  await setFlag('outbound_enabled', true);
  await setFlag('promotions_enabled', false);
});

describe('send window (Asia/Ho_Chi_Minh, default 09:00-19:00)', () => {
  it('knows local hours and the next opening', () => {
    expect(isWithinSendWindow(T10_LOCAL)).toBe(true);
    expect(isWithinSendWindow(Date.UTC(2026, 10, 7, 12, 0))).toBe(false); // 19:00 local
    expect(isWithinSendWindow(Date.UTC(2026, 10, 7, 1, 59))).toBe(false); // 08:59 local
    expect(nextWindowStart(Date.UTC(2026, 10, 7, 14, 0))).toBe(Date.UTC(2026, 10, 8, 2, 0)); // 21:00 -> 09:00 next day
    expect(nextWindowStart(Date.UTC(2026, 10, 6, 20, 0))).toBe(Date.UTC(2026, 10, 7, 2, 0)); // 03:00 -> 09:00 same day
  });
});

describe('follow-up jobs', () => {
  it('scheduled_sends_enabled = false keeps due jobs queued and sends nothing', async () => {
    const s = await seedFollowup();
    await runCron(env, T10_LOCAL);
    expect((await job(s.jobId))!.status).toBe('queued');
    expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('sends the ZBS thank_you template once when enabled, consented and eligible', async () => {
    const s = await seedFollowup();
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, T10_LOCAL);
    await runCron(env, T10_LOCAL + 60_000); // a second tick must not resend
    const j = await job(s.jobId);
    expect(j!.status).toBe('done');
    const rows = await outboxFor(s.zaloUserId);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: 'zbs_template', status: 'sent', template_key: 'thank_you', dedupe_key: `job:${s.jobId}` });
    const payload = JSON.parse(String(rows[0]!.payload_json));
    expect(payload).toMatchObject({ user_id: s.zaloUserId, template_id: 'mock_tpl_thank_you' });
    expect(payload.template_data).toEqual({
      customer_name: 'Lan',
      service_name: 'goi-dau-thu-gian', // no active catalog seeded in this test
      visit_date: '06/11/2026',
      booking_code: s.visitId.slice(-8).toUpperCase(),
      aftercare_note: '',
    });
    const msg = await env.DB.prepare('SELECT direction, source, kind, send_state, zalo_msg_id, text FROM messages WHERE conversation_id = ?').bind(s.conversationId).first<Record<string, string>>();
    expect(msg).toMatchObject({ direction: 'outbound', source: 'server', kind: 'template', send_state: 'sent', zalo_msg_id: `mock_${rows[0]!.id}` });
    expect(msg!.text).toContain('thom house cảm ơn bạn Lan');
    expect(msg!.text).not.toContain('<aftercare_note>');
  });

  it('skips a customer who opted out after consenting', async () => {
    const s = await seedFollowup();
    await env.DB.prepare(
      "INSERT INTO contact_preferences (id, customer_id, preference_type, action, source, created_at) VALUES (?, ?, 'followup_care', 'opt_out', 'keyword', ?)",
    ).bind(uid('cpf'), s.customerId, T10_LOCAL - H).run();
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, T10_LOCAL);
    expect(await job(s.jobId)).toMatchObject({ status: 'skipped', last_error: 'opted_out' });
    expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('an all_proactive_messages opt-out also blocks follow-ups', async () => {
    const s = await seedFollowup();
    await env.DB.prepare(
      "INSERT INTO contact_preferences (id, customer_id, preference_type, action, source, created_at) VALUES (?, ?, 'all_proactive_messages', 'opt_out', 'staff', ?)",
    ).bind(uid('cpf'), s.customerId, T10_LOCAL - H).run();
    await setFlag('scheduled_sends_enabled', true);
    await runDueFollowups(env, T10_LOCAL);
    expect(await job(s.jobId)).toMatchObject({ status: 'skipped', last_error: 'opted_out' });
  });

  it('skips without consent, with an open handoff, or while staff took over', async () => {
    const noConsent = await seedFollowup({ consent: false });
    const handoff = await seedFollowup();
    await env.DB.prepare(
      "INSERT INTO handoffs (id, conversation_id, customer_id, source, reason_code, urgency, status, created_at) VALUES (?,?,?, 'model_tool', 'complaint', 'urgent', 'open', ?)",
    ).bind(uid('hof'), handoff.conversationId, handoff.customerId, T10_LOCAL - H).run();
    const takeover = await seedFollowup({ botState: 'staff_takeover' });
    await setFlag('scheduled_sends_enabled', true);
    await runDueFollowups(env, T10_LOCAL);
    expect(await job(noConsent.jobId)).toMatchObject({ status: 'skipped', last_error: 'no_consent' });
    expect(await job(handoff.jobId)).toMatchObject({ status: 'skipped', last_error: 'open_handoff' });
    expect(await job(takeover.jobId)).toMatchObject({ status: 'skipped', last_error: 'conversation_staff_takeover' });
    for (const s of [noConsent, handoff, takeover]) expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('outbound_enabled = false leaves jobs queued', async () => {
    const s = await seedFollowup();
    await setFlag('scheduled_sends_enabled', true);
    await setFlag('outbound_enabled', false);
    await runCron(env, T10_LOCAL);
    expect((await job(s.jobId))!.status).toBe('queued');
    expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('outside 09:00-19:00 local a due job moves to the next 09:00 instead of sending', async () => {
    const at21 = Date.UTC(2026, 10, 7, 14, 0); // 21:00 local
    const s = await seedFollowup({ runAt: at21 - 5 * 60 * 1000 });
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, at21);
    const j = await job(s.jobId);
    expect(j).toMatchObject({ status: 'queued', last_error: 'outside_send_window', lease_owner: null });
    expect(j!.run_at).toBe(Date.UTC(2026, 10, 8, 2, 0));
    expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('a job past run_at + max_lateness_ms expires instead of sending late', async () => {
    const s = await seedFollowup({ runAt: T10_LOCAL - 7 * H });
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, T10_LOCAL);
    expect(await job(s.jobId)).toMatchObject({ status: 'expired', last_error: 'too_late' });
    expect(await outboxFor(s.zaloUserId)).toHaveLength(0);
  });

  it('promo_send stays queued while promotions_enabled = false', async () => {
    const s = await seedFollowup();
    await env.DB.prepare("UPDATE jobs SET type = 'promo_send', payload_json = '{\"promotion_id\":\"prm_x\"}' WHERE id = ?").bind(s.jobId).run();
    await setFlag('scheduled_sends_enabled', true);
    await runCron(env, T10_LOCAL);
    expect((await job(s.jobId))!.status).toBe('queued');
  });
});

describe('inbox sweep and draft lease fallback', () => {
  it('re-dispatches signed events still received after 2 minutes', async () => {
    const key = `user_send_text:${uid('m')}`;
    const raw = JSON.stringify({ app_id: 'test-app-id', sender: { id: 'c-sweep' }, recipient: { id: 'test-oa-id' }, event_name: 'user_send_text', message: { text: 'hi', msg_id: key.split(':')[1] }, timestamp: '1' });
    await env.DB.prepare(
      "INSERT INTO events_inbox (event_key, event_name, signature_ok, signature_mode, raw_body, status, attempts, received_at) VALUES (?, 'user_send_text', 1, 'observe', ?, 'received', 0, ?)",
    ).bind(key, raw, T10_LOCAL - 3 * 60 * 1000).run();
    const fresh = `user_send_text:${uid('m')}`;
    await env.DB.prepare(
      "INSERT INTO events_inbox (event_key, event_name, signature_ok, signature_mode, raw_body, status, attempts, received_at) VALUES (?, 'user_send_text', 1, 'observe', ?, 'received', 0, ?)",
    ).bind(fresh, raw, T10_LOCAL - 30 * 1000).run();
    await sweepInbox(env, T10_LOCAL);
    const old = await env.DB.prepare('SELECT attempts FROM events_inbox WHERE event_key = ?').bind(key).first<{ attempts: number }>();
    const young = await env.DB.prepare('SELECT attempts FROM events_inbox WHERE event_key = ?').bind(fresh).first<{ attempts: number }>();
    expect(old!.attempts).toBe(1);
    expect(young!.attempts).toBe(0);
  });

  it('expired draft_reply leases go to staff exactly once', async () => {
    const s = await seedFollowup();
    const draftJob = uid('job');
    await env.DB.prepare(
      "INSERT INTO jobs (id, type, conversation_id, customer_id, status, run_at, lease_until, lease_owner, created_at, updated_at) VALUES (?, 'draft_reply', ?, ?, 'leased', ?, ?, 'mac-1', ?, ?)",
    ).bind(draftJob, s.conversationId, s.customerId, T10_LOCAL - 5 * 60 * 1000, T10_LOCAL - 1000, T10_LOCAL, T10_LOCAL).run();
    expect(await expireDraftLeasesFallback(env, T10_LOCAL)).toBeGreaterThanOrEqual(1);
    expect(await expireDraftLeasesFallback(env, T10_LOCAL + 1000)).toBe(0);
    expect((await job(draftJob))!.status).toBe('failed');
    const h = await env.DB.prepare('SELECT reason_code, source, status FROM handoffs WHERE job_id = ?').bind(draftJob).all<Record<string, string>>();
    expect(h.results).toEqual([{ reason_code: 'ai_unavailable', source: 'runner_failure', status: 'open' }]);
    const c = await env.DB.prepare('SELECT needs_attention FROM conversations WHERE id = ?').bind(s.conversationId).first<{ needs_attention: number }>();
    expect(c!.needs_attention).toBe(1);
  });
});
