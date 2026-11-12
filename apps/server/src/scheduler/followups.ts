// Owner: server-zalo. Executes thank_you / check_in / promo_send jobs with approved ZBS templates (no model).
// Re-checks scheduled_sends_enabled (and promotions_enabled for promo_send), outbound_enabled, bot_state,
// consent, opt-outs, open handoffs and max_lateness_ms right before sending. Jobs past
// run_at + max_lateness_ms become 'expired'. Outside the local send window a job is moved to the next opening.
//
// Job payload read here (written by server-core's recordVisit / the promo campaign):
//   thank_you / check_in: { visit_id?: string }   (else: the customer's latest visit before the job was created)
//   promo_send:           { promotion_id: string }
//
// Decision order (first match wins):
//   1. scheduled_sends_enabled = false (promo: or promotions_enabled = false)  -> back to 'queued' (deferred)
//   2. now > run_at + max_lateness_ms                                         -> 'expired'
//   3. outside the send window                                                -> 'queued', run_at = next opening
//   4. outbound_enabled = false                                               -> back to 'queued' (deferred)
//   5. customer missing/deleted, minor, conversation staff_takeover / handoff_requested / blocked,
//      open handoff, no consent, opt-out newer than the consent, nothing to send -> 'skipped' (last_error says why)
//   6. no approved template id (real mode)                                    -> 'needs_staff'
//   7. send: sent -> 'done'; explicit Zalo error -> 'failed'; outcome unknown -> 'needs_staff' (never re-sent)
import type { Env } from '../types';
import { auditStatement } from '../lib/audit';
import { newId } from '../lib/ids';
import { readSendFlags, sendTemplate, templateAvailable, type TemplateKey } from '../lib/zalo-client';
import { isPersonalUserId } from '../lib/zalo-personal';
import { getContactRole, isInternalRole } from '../lib/roles';
import { formatLocalDate, isWithinSendWindow, nextWindowStart, sendWindow } from './send-window';
import { TEMPLATES, pickParams, renderChatTemplate, renderTemplate, type TemplateSpec } from './templates';

export interface DueJobRow {
  id: string;
  type: 'thank_you' | 'check_in' | 'promo_send';
  conversation_id: string | null;
  customer_id: string | null;
  run_at: number;
  max_lateness_ms: number | null;
  payload_json: string;
}

export type FollowupResult = 'done' | 'skipped' | 'expired' | 'needs_staff' | 'failed' | 'deferred';

export const FOLLOWUP_TYPES = ['thank_you', 'check_in', 'promo_send'] as const;
export const CRON_LEASE_MS = 5 * 60 * 1000;
const CRON_OWNER = 'cron';
const BLOCKING_STATES = new Set(['staff_takeover', 'handoff_requested', 'blocked']);

export function followupDedupeKey(jobId: string): string {
  return `job:${jobId}`;
}

// ---------------------------------------------------------------- job status writes (job must be leased by cron)

async function finishJob(env: Env, job: DueJobRow, status: Exclude<FollowupResult, 'deferred'>, now: number, lastError: string | null, result?: unknown): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE jobs SET status = ?, last_error = ?, result_json = ?, lease_until = NULL, updated_at = ?
       WHERE id = ? AND status = 'leased' AND lease_owner = ?`,
    ).bind(status, lastError, result === undefined ? null : JSON.stringify(result), now, job.id, CRON_OWNER),
    auditStatement(env, { actor_type: 'system', actor_id: 'cron', action: `followup.${status}`, entity: 'jobs', entity_id: job.id, after: { type: job.type, reason: lastError } }, now),
  ]);
}

async function requeueJob(env: Env, job: DueJobRow, now: number, reason: string, runAt?: number): Promise<void> {
  await env.DB.prepare(
    `UPDATE jobs SET status = 'queued', run_at = ?, lease_until = NULL, lease_owner = NULL, attempts = MAX(attempts - 1, 0),
       last_error = ?, updated_at = ?
     WHERE id = ? AND status = 'leased' AND lease_owner = ?`,
  )
    .bind(runAt ?? job.run_at, reason, now, job.id, CRON_OWNER)
    .run();
}

// ---------------------------------------------------------------- eligibility

interface CustomerRow {
  id: string;
  zalo_user_id: string;
  display_name: string | null;
  minor_flag: number | null;
  deleted_at: number | null;
}

interface ConversationRow {
  id: string;
  bot_state: string;
}

type ConsentPurpose = 'followup_care' | 'promotions';

/** Latest consent for the purpose must be 'granted', and no opt-out may be recorded at or after that grant. */
export async function proactiveConsentState(env: Env, customerId: string, purpose: ConsentPurpose): Promise<'granted' | 'no_consent' | 'opted_out'> {
  const consent = await env.DB.prepare(
    'SELECT status, recorded_at FROM consents WHERE customer_id = ? AND purpose = ? ORDER BY recorded_at DESC, rowid DESC LIMIT 1',
  )
    .bind(customerId, purpose)
    .first<{ status: string; recorded_at: number }>();
  if (!consent || consent.status !== 'granted') return 'no_consent';
  const optOut = await env.DB.prepare(
    `SELECT 1 AS x FROM contact_preferences
     WHERE customer_id = ? AND action = 'opt_out' AND preference_type IN (?, 'all_proactive_messages') AND created_at >= ? LIMIT 1`,
  )
    .bind(customerId, purpose, consent.recorded_at)
    .first<{ x: number }>();
  return optOut ? 'opted_out' : 'granted';
}

async function hasOpenHandoff(env: Env, customerId: string, conversationId: string | null): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT 1 AS x FROM handoffs WHERE status = 'open' AND (customer_id = ? OR conversation_id = ?) LIMIT 1",
  )
    .bind(customerId, conversationId ?? '')
    .first<{ x: number }>();
  return !!row;
}

// ---------------------------------------------------------------- template parameters

function parsePayload(json: string): Record<string, unknown> {
  try {
    const v = JSON.parse(json) as unknown;
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

async function visitParams(env: Env, job: DueJobRow, customer: CustomerRow): Promise<Record<string, string> | null> {
  const payload = parsePayload(job.payload_json);
  type VisitRow = { id: string; service_id: string; visited_at: number; booking_request_id: string | null };
  let visit: VisitRow | null = null;
  if (typeof payload.visit_id === 'string') {
    visit = await env.DB.prepare('SELECT id, service_id, visited_at, booking_request_id FROM visits WHERE id = ? AND customer_id = ?')
      .bind(payload.visit_id, customer.id)
      .first<VisitRow>();
  }
  if (!visit) {
    visit = await env.DB.prepare(
      'SELECT id, service_id, visited_at, booking_request_id FROM visits WHERE customer_id = ? ORDER BY visited_at DESC LIMIT 1',
    )
      .bind(customer.id)
      .first<VisitRow>();
  }
  if (!visit) return null;

  const service = await env.DB.prepare(
    `SELECT s.display_name_vi AS name FROM services s JOIN catalog_versions cv ON cv.id = s.catalog_version
     WHERE cv.status = 'active' AND s.service_id = ? LIMIT 1`,
  )
    .bind(visit.service_id)
    .first<{ name: string }>();
  let bookingName: string | null = null;
  if (visit.booking_request_id) {
    const b = await env.DB.prepare('SELECT customer_name FROM booking_requests WHERE id = ?').bind(visit.booking_request_id).first<{ customer_name: string }>();
    bookingName = b?.customer_name ?? null;
  }
  return {
    customer_name: bookingName ?? customer.display_name ?? 'Quý khách',
    service_name: service?.name ?? visit.service_id,
    visit_date: formatLocalDate(visit.visited_at),
    booking_code: visit.id.slice(-8).toUpperCase(),
    aftercare_note: '', // owner has not approved any aftercare sentence yet (design/followup-templates.md, decision 1)
  };
}

async function promoParams(env: Env, job: DueJobRow, customer: CustomerRow, now: number): Promise<Record<string, string> | null> {
  const payload = parsePayload(job.payload_json);
  if (typeof payload.promotion_id !== 'string') return null;
  const p = await env.DB.prepare(
    `SELECT title, approved_text_vi, conditions_vi, valid_to FROM promotions
     WHERE id = ? AND status IN ('approved','scheduled','sending') AND valid_from <= ? AND valid_to >= ?`,
  )
    .bind(payload.promotion_id, now, now)
    .first<{ title: string; approved_text_vi: string; conditions_vi: string | null; valid_to: number }>();
  if (!p) return null;
  return {
    customer_name: customer.display_name ?? 'Quý khách',
    promo_name: p.title,
    promo_text: p.approved_text_vi,
    valid_until: formatLocalDate(p.valid_to),
    promo_conditions: p.conditions_vi ?? '',
  };
}

// ---------------------------------------------------------------- run one job

/** Runs one follow-up job that the caller has already leased (status 'leased', lease_owner 'cron'). */
export async function runFollowupJob(env: Env, job: DueJobRow, now: number): Promise<FollowupResult> {
  const isPromo = job.type === 'promo_send';

  // 1. kill switches for scheduled sends
  let flags = await readSendFlags(env);
  if (!flags.scheduled_sends_enabled || (isPromo && !flags.promotions_enabled)) {
    await requeueJob(env, job, now, isPromo && flags.scheduled_sends_enabled ? 'promotions_disabled' : 'scheduled_sends_disabled');
    return 'deferred';
  }
  // 2. lateness
  if (job.max_lateness_ms !== null && now > job.run_at + job.max_lateness_ms) {
    await finishJob(env, job, 'expired', now, 'too_late');
    return 'expired';
  }
  // 3. local send window
  const window = sendWindow(env);
  if (!isWithinSendWindow(now, window)) {
    await requeueJob(env, job, now, 'outside_send_window', nextWindowStart(now, window));
    return 'deferred';
  }
  // 4. outbound kill switch
  if (!flags.outbound_enabled) {
    await requeueJob(env, job, now, 'outbound_disabled');
    return 'deferred';
  }

  // 5. recipient checks
  const customer = job.customer_id
    ? await env.DB.prepare('SELECT id, zalo_user_id, display_name, minor_flag, deleted_at FROM customers WHERE id = ?').bind(job.customer_id).first<CustomerRow>()
    : null;
  if (!customer || customer.deleted_at !== null) {
    await finishJob(env, job, 'skipped', now, 'customer_missing');
    return 'skipped';
  }
  if (customer.minor_flag === 1) {
    await finishJob(env, job, 'skipped', now, 'minor');
    return 'skipped';
  }
  // Internal contact (docs/contracts.md section 14.3): a manager or a staff member gets no follow-up message.
  if (isInternalRole((await getContactRole(env, customer.zalo_user_id))?.role)) {
    await finishJob(env, job, 'skipped', now, 'internal_contact');
    return 'skipped';
  }
  const conversation = await env.DB.prepare(
    job.conversation_id ? 'SELECT id, bot_state FROM conversations WHERE id = ?' : 'SELECT id, bot_state FROM conversations WHERE customer_id = ?',
  )
    .bind(job.conversation_id ?? customer.id)
    .first<ConversationRow>();
  if (conversation && BLOCKING_STATES.has(conversation.bot_state)) {
    await finishJob(env, job, 'skipped', now, `conversation_${conversation.bot_state}`);
    return 'skipped';
  }
  if (await hasOpenHandoff(env, customer.id, conversation?.id ?? null)) {
    await finishJob(env, job, 'skipped', now, 'open_handoff');
    return 'skipped';
  }
  const consent = await proactiveConsentState(env, customer.id, isPromo ? 'promotions' : 'followup_care');
  if (consent !== 'granted') {
    await finishJob(env, job, 'skipped', now, consent);
    return 'skipped';
  }

  const spec: TemplateSpec = isPromo ? TEMPLATES.promo : job.type === 'thank_you' ? TEMPLATES.thank_you : TEMPLATES.check_in;
  const values = isPromo ? await promoParams(env, job, customer, now) : await visitParams(env, job, customer);
  if (!values) {
    await finishJob(env, job, 'skipped', now, isPromo ? 'promotion_not_active' : 'visit_missing');
    return 'skipped';
  }
  // 6. approved template id (personal channel: a chat version of the template)
  const templateKey: TemplateKey = spec.key;
  const personal = isPersonalUserId(customer.zalo_user_id);
  if (!templateAvailable(env, templateKey, customer.zalo_user_id)) {
    await finishJob(env, job, 'needs_staff', now, 'template_not_configured');
    return 'needs_staff';
  }
  const params = pickParams(spec, values);

  // Last look at the kill switches immediately before the send (the checks above took several queries).
  flags = await readSendFlags(env);
  if (!flags.scheduled_sends_enabled || !flags.outbound_enabled || (isPromo && !flags.promotions_enabled)) {
    await requeueJob(env, job, now, 'flags_changed');
    return 'deferred';
  }

  // 7. messages row first (send_state 'pending'), then the Zalo client. client_send_id = dedupe key, so a
  //    re-run after a crash finds the same row and the outbox returns the stored outcome instead of resending.
  const dedupeKey = followupDedupeKey(job.id);
  let messageId: string | null = null;
  if (conversation) {
    const candidate = newId('msg', now);
    await env.DB.prepare(
      `INSERT OR IGNORE INTO messages (id, conversation_id, direction, source, kind, text, send_state, client_send_id, created_at)
       VALUES (?, ?, 'outbound', 'server', 'template', ?, 'pending', ?, ?)`,
    )
      .bind(candidate, conversation.id, (personal ? renderChatTemplate(templateKey, params) : null) ?? renderTemplate(spec, params), dedupeKey, now)
      .run();
    const row = await env.DB.prepare('SELECT id FROM messages WHERE client_send_id = ?').bind(dedupeKey).first<{ id: string }>();
    messageId = row?.id ?? null;
  }

  const outcome = await sendTemplate(env, customer.zalo_user_id, templateKey, params, {
    conversation_id: conversation?.id ?? null,
    customer_id: customer.id,
    message_id: messageId,
    dedupe_key: dedupeKey,
  });

  const setMessage = (state: 'sent' | 'failed' | 'unknown', zaloMsgId: string | null, err: string | null) =>
    messageId
      ? env.DB.prepare('UPDATE messages SET send_state = ?, zalo_msg_id = COALESCE(?, zalo_msg_id), send_error = ?, sent_at = ? WHERE id = ?')
          .bind(state, zaloMsgId, err, state === 'sent' ? now : null, messageId)
          .run()
      : Promise.resolve(null);

  if (outcome.ok) {
    // Personal channel: queued for the bridge; the message stays 'pending' until the bridge reports (src/bridge/outbox.ts).
    if (!outcome.queued) await setMessage('sent', outcome.zalo_msg_id, null);
    if (conversation) {
      await env.DB.prepare('UPDATE conversations SET last_message_at = ?, updated_at = ? WHERE id = ?').bind(now, now, conversation.id).run();
    }
    await finishJob(env, job, 'done', now, null, { outbox_id: outcome.outbox_id, zalo_msg_id: outcome.zalo_msg_id, template: templateKey, ...(outcome.queued ? { queued: true } : {}) });
    return 'done';
  }
  if (outcome.error_code === 'outbound_disabled') {
    await requeueJob(env, job, now, 'outbound_disabled');
    return 'deferred';
  }
  if (outcome.unknown) {
    await setMessage('unknown', null, outcome.error_code);
    await finishJob(env, job, 'needs_staff', now, `send_unknown:${outcome.error_code}`, { outbox_id: outcome.outbox_id });
    return 'needs_staff';
  }
  await setMessage('failed', null, `${outcome.error_code}: ${outcome.error_message}`.slice(0, 300));
  await finishJob(env, job, 'failed', now, `send_failed:${outcome.error_code}`, { outbox_id: outcome.outbox_id });
  return 'failed';
}

// ---------------------------------------------------------------- batch entry points used by cron

/** Leases and runs due follow-up jobs. Does nothing (jobs stay 'queued') while scheduled_sends_enabled = false. */
export async function runDueFollowups(env: Env, now: number, limit = 25): Promise<Record<FollowupResult, number>> {
  const counts: Record<FollowupResult, number> = { done: 0, skipped: 0, expired: 0, needs_staff: 0, failed: 0, deferred: 0 };
  const flags = await readSendFlags(env);
  // Kill switches off: leave every job 'queued' untouched (no lease churn). Lateness is judged when they run.
  if (!flags.scheduled_sends_enabled || !flags.outbound_enabled) return counts;

  const due = await env.DB.prepare(
    `SELECT id, type, conversation_id, customer_id, run_at, max_lateness_ms, payload_json FROM jobs
     WHERE status = 'queued' AND type IN ('thank_you','check_in','promo_send') AND run_at <= ?
       AND (type != 'promo_send' OR ? = 1)
     ORDER BY run_at ASC LIMIT ?`,
  )
    .bind(now, flags.promotions_enabled ? 1 : 0, limit)
    .all<DueJobRow>();

  for (const job of due.results ?? []) {
    const lease = await env.DB.prepare(
      `UPDATE jobs SET status = 'leased', lease_owner = ?, lease_until = ?, attempts = attempts + 1, updated_at = ?
       WHERE id = ? AND status = 'queued'`,
    )
      .bind(CRON_OWNER, now + CRON_LEASE_MS, now, job.id)
      .run();
    if ((lease.meta.changes ?? 0) === 0) continue; // another cron tick took it
    try {
      counts[await runFollowupJob(env, job, now)]++;
    } catch (err) {
      // Unexpected error before or around the send. If an outbox row exists the outcome is uncertain: staff.
      const sent = await env.DB.prepare('SELECT status FROM outbox WHERE dedupe_key = ?').bind(followupDedupeKey(job.id)).first<{ status: string }>();
      const msg = (err instanceof Error ? err.message : String(err)).slice(0, 200);
      if (sent) await finishJob(env, job, 'needs_staff', now, `error_after_send_attempt:${msg}`);
      else await finishJob(env, job, 'failed', now, `error:${msg}`);
      counts[sent ? 'needs_staff' : 'failed']++;
      console.error(JSON.stringify({ level: 'error', at: 'scheduler.followup', job_id: job.id, error: msg }));
    }
  }
  return counts;
}

/** Follow-up jobs whose cron lease ran out (worker died mid-run): requeue when nothing was sent, else staff. */
export async function recoverStuckFollowups(env: Env, now: number): Promise<number> {
  const stuck = await env.DB.prepare(
    `SELECT id FROM jobs WHERE status = 'leased' AND lease_owner = ? AND type IN ('thank_you','check_in','promo_send') AND lease_until < ? LIMIT 50`,
  )
    .bind(CRON_OWNER, now)
    .all<{ id: string }>();
  let n = 0;
  for (const { id } of stuck.results ?? []) {
    const out = await env.DB.prepare('SELECT status, id FROM outbox WHERE dedupe_key = ?').bind(followupDedupeKey(id)).first<{ status: string; id: string }>();
    const [status, err] = !out ? ['queued', 'lease_expired_requeued'] : out.status === 'sent' ? ['done', null] : ['needs_staff', `lease_expired_outbox_${out.status}`];
    const r = await env.DB.prepare(
      `UPDATE jobs SET status = ?, last_error = ?, lease_until = NULL, lease_owner = CASE WHEN ? = 'queued' THEN NULL ELSE lease_owner END, updated_at = ?
       WHERE id = ? AND status = 'leased' AND lease_until < ?`,
    )
      .bind(status, err, status, now, id, now)
      .run();
    n += r.meta.changes ?? 0;
  }
  return n;
}
