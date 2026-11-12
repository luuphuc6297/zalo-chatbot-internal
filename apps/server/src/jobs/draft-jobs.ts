// Owner: server-core. draft_reply job lifecycle (docs/contracts.md "Job and draft lifecycle").
import type {
  ClaimedJob,
  ConversationMode,
  Env,
  Flags,
  RunnerClaimResponse,
  RunnerFailRequest,
  RunnerFailResponse,
  RunnerHeartbeatResponse,
  SessionResetReason,
  TurnContext,
} from '../types';
import { HttpError } from '../lib/http';
import { newId } from '../lib/ids';
import { aiCallsAllowed, conversationMode, getFlags } from '../lib/flags';
import { conversationIsInternal, getContactRole, isInternalRole } from '../lib/roles';
import { buildPrompt, renderTurnContext } from '../lib/prompt';
import { profileFactsForModel } from '../lib/profiles';
import { DAY_MS, envInt, formatLocalShort, formatNowLocal, localDate } from '../lib/time';
import { oneLine } from '../lib/text';
import { auditStatement } from '../lib/audit';
import {
  type ConversationRow,
  type CustomerRow,
  type DraftJobPayload,
  type JobRow,
  activeCatalogVersion,
  cancelQueuedDraftJobs,
  consentStatus,
  createHandoff,
  getConversation,
  getCustomer,
  getJob,
  handoffStatements,
  parsePayload,
  safeJson,
} from '../lib/db';

export const SESSION_TURN_LIMIT = 20;
export const SESSION_IDLE_MS = DAY_MS;
export const HISTORY_LIMIT = 20;

export const leaseMs = (env: Env) => envInt(env.LEASE_MS, 90_000);
export const debounceMs = (env: Env) => envInt(env.DEBOUNCE_MS, 10_000);
export const runnerOfflineMs = (env: Env) => envInt(env.RUNNER_OFFLINE_MS, 120_000);

// ---------------------------------------------------------------- eligibility

export type DraftBlocker =
  | 'ai_calls_disabled'
  | 'ai_engine_off'
  | 'api_key_not_configured'
  | 'minor_flag'
  | 'not_bot_active'
  | 'mode_off'
  | 'no_ai_consent'
  | 'internal_contact';

/**
 * Why the model must not be called for this conversation right now (null = eligible). An internal contact (role
 * manager or staff, docs/contracts.md section 14.3) is checked first: that blocker is quiet (see applyBlocker), so it
 * must win over the ones that route the conversation to staff.
 */
export async function draftBlocker(env: Env, conv: ConversationRow, customer: CustomerRow, flags: Flags): Promise<DraftBlocker | null> {
  if (isInternalRole((await getContactRole(env, customer.zalo_user_id))?.role)) return 'internal_contact';
  if (!flags.ai_calls_enabled) return 'ai_calls_disabled';
  if (flags.ai_engine === 'off') return 'ai_engine_off';
  if (flags.ai_engine === 'api_key') return 'api_key_not_configured';
  if (customer.minor_flag === 1) return 'minor_flag';
  if (conv.bot_state !== 'bot_active') return 'not_bot_active';
  if (conversationMode(flags, conv) === 'off') return 'mode_off';
  if ((await consentStatus(env, customer.id)).ai_assistant?.status !== 'granted') return 'no_ai_consent';
  return null;
}

/**
 * Side effects of a blocked draft: route the conversation to staff. The blocker 'internal_contact' is the exception:
 * nothing reaches staff (no needs_attention, no handoff); the queued draft jobs of the conversation are cancelled.
 */
export async function applyBlocker(env: Env, conv: ConversationRow, blocker: DraftBlocker, now: number, jobId: string | null = null): Promise<void> {
  if (blocker === 'internal_contact') {
    await cancelQueuedDraftJobs(env, conv.id, 'internal_contact', now, jobId ?? '').run();
    return;
  }
  const stmts: D1PreparedStatement[] = [
    env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, conv.id),
  ];
  if (blocker === 'api_key_not_configured') {
    // One open handoff per conversation for this cause (idempotent per last customer message).
    stmts.push(
      ...handoffStatements(env, {
        conversation_id: conv.id,
        customer_id: conv.customer_id,
        job_id: jobId,
        source: 'server',
        reason_code: 'ai_unavailable',
        urgency: 'normal',
        summary_for_staff: 'api_key engine not configured',
        idempotency_key: `apikey:${conv.id}:${conv.last_customer_message_at ?? now}`,
      }, now).stmts,
    );
  }
  if (blocker === 'minor_flag' && conv.bot_state !== 'blocked') {
    stmts.push(
      env.DB.prepare("UPDATE conversations SET bot_state = 'blocked', updated_at = ? WHERE id = ?").bind(now, conv.id),
      ...handoffStatements(env, {
        conversation_id: conv.id,
        customer_id: conv.customer_id,
        job_id: jobId,
        source: 'server',
        reason_code: 'minor_flag',
        urgency: 'normal',
        summary_for_staff: 'Zalo đánh dấu tài khoản dưới 18 tuổi; trợ lý AI không trả lời.',
        idempotency_key: `minor:${conv.id}`,
      }, now).stmts,
      auditStatement(env, { actor_type: 'system', action: 'conversation.blocked_minor', entity: 'conversation', entity_id: conv.id }, now),
    );
  }
  await env.DB.batch(stmts);
}

/**
 * A takeover whose takeover_until passed returns to the bot with a fresh session: bot_active when the customer gave
 * AI consent, awaiting_consent otherwise (same rule as a staff release). A takeover can start before any consent,
 * e.g. staff writing first from the phone of the personal account.
 */
export async function releaseExpiredTakeover(env: Env, conv: ConversationRow, now: number): Promise<ConversationRow> {
  if (conv.bot_state !== 'staff_takeover' || !conv.takeover_until || conv.takeover_until > now) return conv;
  // Internal contact (section 14.3): bot_state is left unchanged, so the takeover does not return to the bot.
  if (await conversationIsInternal(env, conv.id)) return conv;
  const next = (await consentStatus(env, conv.customer_id)).ai_assistant?.status === 'granted' ? 'bot_active' : 'awaiting_consent';
  await env.DB.batch([
    env.DB.prepare(
      "UPDATE conversations SET bot_state = ?, takeover_by = NULL, takeover_until = NULL, session_id = NULL, session_reset_reason = 'released_by_staff', updated_at = ? WHERE id = ? AND bot_state = 'staff_takeover'",
    ).bind(next, now, conv.id),
    auditStatement(env, { actor_type: 'system', action: 'conversation.takeover_expired', entity: 'conversation', entity_id: conv.id, after: { bot_state: next } }, now),
  ]);
  return (await getConversation(env, conv.id))!;
}

// ---------------------------------------------------------------- enqueue

export function cutoffSeq(conv: Pick<ConversationRow, 'answered_seq' | 'consent_seq'>): number {
  return Math.max(conv.answered_seq ?? 0, conv.consent_seq ?? 0);
}

/** Called by the Conversation DO alarm after the debounce window. Idempotent per conversation:
 *  dedupe_key = 'draft:' + conversation_id + ':' + last customer message id. Returns null when not eligible. */
export async function enqueueDraftJob(env: Env, conversationId: string, now: number, runAt = now): Promise<string | null> {
  let conv = await getConversation(env, conversationId);
  if (!conv) return null;
  const customer = await getCustomer(env, conv.customer_id);
  if (!customer) return null;
  conv = await releaseExpiredTakeover(env, conv, now);

  const last = await env.DB.prepare(
    "SELECT id, seq FROM messages WHERE conversation_id = ? AND direction = 'inbound' AND source = 'customer' AND kind != 'user_info' AND seq > ? ORDER BY seq DESC LIMIT 1",
  )
    .bind(conv.id, cutoffSeq(conv))
    .first<{ id: string; seq: number }>();
  if (!last) return null;

  const flags = await getFlags(env);
  const blocker = await draftBlocker(env, conv, customer, flags);
  if (blocker) {
    await applyBlocker(env, conv, blocker, now);
    return null;
  }

  const open = await env.DB.prepare(
    "SELECT id, status FROM jobs WHERE conversation_id = ? AND type = 'draft_reply' AND status IN ('queued','leased') ORDER BY created_at DESC",
  )
    .bind(conv.id)
    .all<{ id: string; status: string }>();
  const leased = open.results.find((j) => j.status === 'leased');
  if (leased) {
    await env.DB.prepare('UPDATE jobs SET stale = 1, updated_at = ? WHERE id = ?').bind(now, leased.id).run();
    return null;
  }
  const queued = open.results.find((j) => j.status === 'queued');
  if (queued) {
    // claim reads messages at claim time, so the queued job covers the new ones
    await env.DB.prepare('UPDATE jobs SET run_at = MIN(run_at, ?), updated_at = ? WHERE id = ?').bind(runAt, now, queued.id).run();
    return queued.id;
  }

  const id = newId('job', now);
  const dedupe = `draft:${conv.id}:${last.id}`;
  const r = await env.DB.prepare(
    "INSERT OR IGNORE INTO jobs (id, type, conversation_id, customer_id, status, run_at, max_attempts, payload_json, dedupe_key, created_at, updated_at) VALUES (?, 'draft_reply', ?, ?, 'queued', ?, 1, ?, ?, ?, ?)",
  )
    .bind(id, conv.id, conv.customer_id, runAt, JSON.stringify({ last_customer_message_id: last.id } satisfies DraftJobPayload), dedupe, now, now)
    .run();
  return r.meta.changes ? id : null;
}

// ---------------------------------------------------------------- claim

export function decideSession(conv: ConversationRow, activeCv: string, now: number): { session_id: string | null; reason: SessionResetReason | null } {
  if (conv.session_reset_reason) return { session_id: null, reason: conv.session_reset_reason as SessionResetReason };
  if (!conv.session_id) return { session_id: null, reason: 'new_conversation' };
  if (conv.session_turns >= SESSION_TURN_LIMIT) return { session_id: null, reason: 'turn_limit' };
  if (conv.session_last_turn_at && now - conv.session_last_turn_at > SESSION_IDLE_MS) return { session_id: null, reason: 'idle' };
  if (conv.catalog_version !== activeCv) return { session_id: null, reason: 'catalog_changed' };
  return { session_id: conv.session_id, reason: null };
}

function consentText(c: { status: string; recorded_at: number } | undefined): string {
  return c ? `${c.status}(${formatLocalShort(c.recorded_at)})` : 'none';
}

async function buildClaimedJob(env: Env, job: JobRow, conv: ConversationRow, customer: CustomerRow, flags: Flags, cv: string, promptHash: string, now: number): Promise<ClaimedJob | null> {
  const cutoff = cutoffSeq(conv);
  const db = env.DB;
  const newMsgs = await db.prepare(
    // user_info rows (Zalo form submissions) hold personal data for staff only and never reach the model.
    "SELECT id, text, kind, attachments_json, created_at, seq FROM messages WHERE conversation_id = ? AND direction = 'inbound' AND source = 'customer' AND kind != 'user_info' AND seq > ? ORDER BY seq",
  )
    .bind(conv.id, cutoff)
    .all<{ id: string; text: string | null; kind: string; attachments_json: string | null; created_at: number; seq: number }>();
  if (!newMsgs.results.length) return null;
  const upTo = newMsgs.results[newMsgs.results.length - 1]!;

  const session = decideSession(conv, cv, now);
  let history: ClaimedJob['history'] = [];
  if (!session.session_id) {
    const h = await db.prepare(
      "SELECT source, text, created_at FROM messages WHERE conversation_id = ? AND seq > ? AND seq <= ? AND text IS NOT NULL AND kind != 'user_info' AND (direction = 'inbound' OR send_state = 'sent') ORDER BY seq DESC LIMIT ?",
    )
      .bind(conv.id, conv.consent_seq, cutoff, HISTORY_LIMIT)
      .all<{ source: 'customer' | 'bot' | 'staff' | 'server'; text: string; created_at: number }>();
    history = h.results.reverse().map((m) => ({ source: m.source, text: m.text, at: m.created_at }));
  }

  const prevDraft = await db.prepare('SELECT id, text, created_at FROM drafts WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1')
    .bind(conv.id)
    .first<{ id: string; text: string; created_at: number }>();
  const sentRows = await db.prepare(
    "SELECT m.id, m.source, m.text, m.sent_at, m.created_at, m.draft_id, d.text AS draft_text FROM messages m LEFT JOIN drafts d ON d.id = m.draft_id " +
      "WHERE m.conversation_id = ? AND m.direction = 'outbound' AND m.send_state = 'sent' AND m.text IS NOT NULL AND m.seq > ? AND m.created_at > ? ORDER BY m.seq",
  )
    .bind(conv.id, conv.consent_seq, prevDraft?.created_at ?? 0)
    .all<{ id: string; source: 'bot' | 'staff' | 'server'; text: string; sent_at: number | null; created_at: number; draft_id: string | null; draft_text: string | null }>();
  const sent = sentRows.results
    .filter((m) => !(m.draft_id && m.draft_id === prevDraft?.id && m.draft_text === m.text))
    .map((m) => ({
      message_id: m.id,
      source: m.source,
      text: m.text,
      sent_at: m.sent_at ?? m.created_at,
      from_draft_id: m.draft_id,
      edited_by_staff: !!m.draft_id && m.draft_text !== null && m.draft_text !== m.text,
    }));

  const lastSentDraft = await db.prepare("SELECT created_at FROM drafts WHERE conversation_id = ? AND status IN ('sent','approved') ORDER BY created_at DESC LIMIT 1")
    .bind(conv.id)
    .first<{ created_at: number }>();
  const unsent = await db.prepare(
    "SELECT id, status, text FROM drafts WHERE conversation_id = ? AND status IN ('rejected','blocked','superseded','discarded','send_failed') AND created_at > ? ORDER BY created_at DESC LIMIT 5",
  )
    .bind(conv.id, lastSentDraft?.created_at ?? 0)
    .all<{ id: string; status: 'rejected' | 'blocked' | 'superseded' | 'discarded' | 'send_failed'; text: string }>();

  const consents = await consentStatus(env, customer.id);
  const bookings = await db.prepare(
    "SELECT id, service_ids_json, preferred_date_local, preferred_time_window, party_size, status FROM booking_requests WHERE conversation_id = ? AND status IN ('new','proposed') ORDER BY created_at",
  )
    .bind(conv.id)
    .all<{ id: string; service_ids_json: string; preferred_date_local: string; preferred_time_window: string; party_size: number; status: 'new' | 'proposed' }>();
  const followup = await db.prepare(
    "SELECT type, updated_at FROM jobs WHERE customer_id = ? AND type IN ('thank_you','check_in') AND status = 'done' ORDER BY updated_at DESC LIMIT 1",
  )
    .bind(customer.id)
    .first<{ type: string; updated_at: number }>();

  const notes: string[] = [];
  const nonText = newMsgs.results.filter((m) => m.kind !== 'text');
  if (nonText.length) notes.push(`customer sent ${nonText.map((m) => m.kind).join(', ')}; the assistant cannot view attachments`);
  if (job.stale) notes.push('newer customer messages may arrive while you answer');

  const mode: ConversationMode = conversationMode(flags, conv);
  const turn: TurnContext = {
    now_local: formatNowLocal(now),
    conversation_mode: mode,
    customer_display_name: oneLine(customer.display_name, 40) || 'Khách',
    customer_gender_hint: customer.gender_hint || 'unknown',
    minor_flag: customer.minor_flag === 1 ? 'true' : customer.minor_flag === 0 ? 'false' : 'unknown',
    consent: {
      ai_assistant: consentText(consents.ai_assistant),
      followup_care: consentText(consents.followup_care),
      promotions: consentText(consents.promotions),
    },
    open_booking_requests: bookings.results.map((b) => ({
      request_id: b.id,
      summary: `${safeJson<string[]>(b.service_ids_json, []).join('+')} ${b.preferred_date_local} ${b.preferred_time_window}, ${b.party_size} người`,
      status: b.status,
    })),
    last_followup_sent: followup ? `${followup.type} ${localDate(followup.updated_at)}` : 'none',
    notes,
  };

  const payload: DraftJobPayload = {
    ...parsePayload(job),
    last_customer_message_id: upTo.id,
    up_to_seq: upTo.seq,
    catalog_version: cv,
    session_id_given: session.session_id,
    session_reset_reason: session.reason,
  };
  await db.prepare('UPDATE jobs SET payload_json = ?, updated_at = ? WHERE id = ?').bind(JSON.stringify(payload), now, job.id).run();

  return {
    job_id: job.id,
    type: 'draft_reply',
    lease_until: job.lease_until!,
    attempt: job.attempts,
    conversation: {
      conversation_id: conv.id,
      session_id: session.session_id,
      session_turns: session.session_id ? conv.session_turns : 0,
      session_started_at: session.session_id ? conv.session_started_at : null,
      session_reset_reason: session.reason,
      catalog_version: cv,
    },
    turn_context: turn,
    turn_context_text: renderTurnContext(turn),
    new_customer_messages: newMsgs.results.map((m) => ({
      message_id: m.id,
      text: m.text ?? '',
      kind: m.kind,
      attachments: safeJson(m.attachments_json, []),
      sent_at: m.created_at,
    })),
    sent_since_last_draft: sent,
    unsent_drafts_since_last: unsent.results.map((d) => ({ draft_id: d.id, status: d.status, text: d.text })),
    history,
    prompt_hash: promptHash,
    // Derived facts only (address term, name, catalog service names, last service as name + date); only for a
    // customer or unknown profile, never for family, staff or friends.
    customer_profile: await profileFactsForModel(env, customer.zalo_user_id, cv),
  };
}

/** Atomically leases the oldest queued draft_reply job whose conversation has no other leased job. */
export async function claimNext(env: Env, runnerId: string, now: number): Promise<RunnerClaimResponse> {
  const flags = await getFlags(env);
  if (!flags.ai_calls_enabled || flags.ai_engine === 'off') return { job: null, poll_after_ms: 5000, reason: 'ai_calls_disabled' };
  if (flags.ai_engine !== 'subscription') return { job: null, poll_after_ms: 5000, reason: 'ai_engine_not_subscription' };
  const cv = await activeCatalogVersion(env);
  if (!cv) throw new HttpError(409, 'invalid_state', 'no active catalog; run POST /dev/seed');
  let promptHash: string | null = null; // built only once a job is leased (claim is polled every 2 s)

  for (let attempt = 0; attempt < 5; attempt++) {
    const job = await env.DB.prepare(
      "UPDATE jobs SET status = 'leased', lease_owner = ?, lease_until = ?, attempts = attempts + 1, updated_at = ? " +
        "WHERE id = (SELECT j.id FROM jobs j WHERE j.type = 'draft_reply' AND j.status = 'queued' AND j.run_at <= ? " +
        "AND NOT EXISTS (SELECT 1 FROM jobs l WHERE l.conversation_id = j.conversation_id AND l.type = 'draft_reply' AND l.status = 'leased') " +
        'ORDER BY j.run_at, j.created_at LIMIT 1) ' +
        "AND status = 'queued' RETURNING *",
    )
      .bind(runnerId, now + leaseMs(env), now, now)
      .first<JobRow>();
    if (!job) break;
    let conv = await getConversation(env, job.conversation_id!);
    const customer = conv ? await getCustomer(env, conv.customer_id) : null;
    if (!conv || !customer) {
      await cancelJob(env, job.id, 'conversation_missing', now);
      continue;
    }
    conv = await releaseExpiredTakeover(env, conv, now);
    const blocker = await draftBlocker(env, conv, customer, flags);
    if (blocker) {
      await cancelJob(env, job.id, blocker, now);
      await applyBlocker(env, conv, blocker, now, job.id);
      continue;
    }
    promptHash ??= (await buildPrompt(env, cv)).prompt_hash;
    const claimed = await buildClaimedJob(env, job, conv, customer, flags, cv, promptHash, now);
    if (!claimed) {
      await cancelJob(env, job.id, 'nothing_to_answer', now);
      continue;
    }
    await env.DB.prepare('UPDATE runner_status SET last_claim_at = ? WHERE runner_id = ?').bind(now, runnerId).run();
    return { job: claimed, poll_after_ms: 0 };
  }
  return { job: null, poll_after_ms: 2000, reason: 'no_work' };
}

export async function claimDraftJob(env: Env, runnerId: string, now: number): Promise<ClaimedJob | null> {
  return (await claimNext(env, runnerId, now)).job;
}

async function cancelJob(env: Env, jobId: string, reason: string, now: number): Promise<void> {
  await env.DB.prepare("UPDATE jobs SET status = 'cancelled', last_error = ?, updated_at = ? WHERE id = ?").bind(reason, now, jobId).run();
}

// ---------------------------------------------------------------- lease checks, heartbeat, fail

/** Order of checks from the contract: 404, job_not_leased, lease_not_owned, lease_expired. */
export async function loadLeasedJob(env: Env, jobId: string, runnerId: string, now: number, opts: { allowExpired?: boolean } = {}): Promise<JobRow> {
  const job = await getJob(env, jobId);
  if (!job || job.type !== 'draft_reply') throw new HttpError(404, 'not_found', 'job not found');
  if (job.status !== 'leased') throw new HttpError(409, 'job_not_leased', `job is ${job.status}`, { status: job.status });
  if (job.lease_owner !== runnerId) throw new HttpError(409, 'lease_not_owned', 'job is leased by another runner');
  if (!opts.allowExpired && (job.lease_until ?? 0) <= now) throw new HttpError(409, 'lease_expired', 'lease expired');
  return job;
}

/** true when this job itself called handoff_to_staff or opted the customer out of the AI. */
export async function jobHandedOff(env: Env, jobId: string): Promise<boolean> {
  const r = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM tool_calls WHERE job_id = ? AND is_error = 0 AND (tool_name = 'handoff_to_staff' OR (tool_name = 'record_contact_preference' AND input_json LIKE '%\"ai_assistant\"%' AND input_json LIKE '%\"opt_out\"%'))",
  )
    .bind(jobId)
    .first<{ n: number }>();
  return (r?.n ?? 0) > 0;
}

export async function heartbeat(env: Env, jobId: string, runnerId: string, now: number): Promise<RunnerHeartbeatResponse> {
  const pre = await getJob(env, jobId);
  if (pre && pre.type === 'draft_reply' && pre.status === 'cancelled' && pre.lease_owner === runnerId) {
    return { lease_until: pre.lease_until ?? now, stale: !!pre.stale, cancel: true, cancel_reason: 'job_cancelled' };
  }
  const job = await loadLeasedJob(env, jobId, runnerId, now);
  const flags = await getFlags(env);
  const conv = await getConversation(env, job.conversation_id!);
  let cancel: RunnerHeartbeatResponse['cancel_reason'] | undefined;
  // The contact got the role manager or staff while the job was running (section 14.3): the runner gets `cancel` with
  // the existing reason 'job_cancelled'; the job row records 'internal_contact'.
  let internal = false;
  if (!aiCallsAllowed(flags)) cancel = 'flags_changed';
  else if (!conv) cancel = 'job_cancelled';
  else if (await conversationIsInternal(env, conv.id)) {
    cancel = 'job_cancelled';
    internal = true;
  } else if (conversationMode(flags, conv) === 'off') cancel = 'flags_changed';
  else if (conv.bot_state === 'staff_takeover') cancel = 'takeover';
  else if (conv.bot_state !== 'bot_active' && !(await jobHandedOff(env, job.id))) cancel = 'handoff';
  if (cancel) {
    const recorded = internal ? 'internal_contact' : cancel;
    const payload = { ...parsePayload(job), cancel_reason: recorded };
    await env.DB.prepare("UPDATE jobs SET status = 'cancelled', last_error = ?, payload_json = ?, updated_at = ? WHERE id = ? AND status = 'leased'")
      .bind(`cancel:${recorded}`, JSON.stringify(payload), now, job.id)
      .run();
    return { lease_until: job.lease_until!, stale: !!job.stale, cancel: true, cancel_reason: cancel };
  }
  const until = now + leaseMs(env);
  await env.DB.prepare("UPDATE jobs SET lease_until = ?, updated_at = ? WHERE id = ? AND status = 'leased'").bind(until, now, job.id).run();
  return { lease_until: until, stale: !!job.stale, cancel: false };
}

export async function failDraftJob(env: Env, jobId: string, runnerId: string, body: RunnerFailRequest, now: number): Promise<RunnerFailResponse> {
  // Record the runner error even when the job can no longer be failed (useful for the staff runner view).
  await env.DB.prepare('UPDATE runner_status SET last_error_kind = ?, last_error_at = ?, last_error_account = ? WHERE runner_id = ?')
    .bind(body.error_kind, now, body.account_label ?? null, runnerId)
    .run();
  const job = await loadLeasedJob(env, jobId, runnerId, now, { allowExpired: true });
  const conv = (await getConversation(env, job.conversation_id!))!;
  const msg = `${body.error_kind}: ${(body.error_message ?? '').slice(0, 500)}`;
  const stmts: D1PreparedStatement[] = [];
  const usage = body.usage;
  if (usage || body.cost_usd_equiv) {
    stmts.push(
      env.DB.prepare(
        'UPDATE conversations SET total_input_tokens = total_input_tokens + ?, total_output_tokens = total_output_tokens + ?, total_cache_read_tokens = total_cache_read_tokens + ?, total_cache_write_tokens = total_cache_write_tokens + ?, total_cost_usd_equiv = total_cost_usd_equiv + ? WHERE id = ?',
      ).bind(usage?.input_tokens ?? 0, usage?.output_tokens ?? 0, usage?.cache_read_input_tokens ?? 0, usage?.cache_creation_input_tokens ?? 0, body.cost_usd_equiv ?? 0, conv.id),
    );
  }
  if (body.session_broken || body.error_kind === 'session_broken') {
    stmts.push(
      env.DB.prepare("UPDATE conversations SET session_id = NULL, session_reset_reason = 'session_broken', updated_at = ? WHERE id = ?").bind(now, conv.id),
    );
  }
  // 'cancelled' from the runner (shutdown mid-job) is handled like every other error kind: the customer's
  // question must reach staff. Cancels decided by the server go through heartbeat and never call /fail.
  stmts.push(
    env.DB.prepare("UPDATE jobs SET status = 'failed', last_error = ?, result_json = ?, updated_at = ? WHERE id = ?")
      .bind(msg, JSON.stringify({ error_kind: body.error_kind, account_label: body.account_label }), now, job.id),
    auditStatement(env, { actor_type: 'runner', actor_id: runnerId, action: 'job.fail', entity: 'job', entity_id: job.id, after: { error_kind: body.error_kind } }, now),
  );
  await env.DB.batch(stmts);
  // An internal contact (section 14.3) raises nothing for staff: the job is failed, no handoff is opened.
  if (await conversationIsInternal(env, conv.id)) return { job_status: 'failed', handoff_id: null };
  const handoffId = await createHandoff(env, {
    conversation_id: conv.id,
    customer_id: conv.customer_id,
    job_id: job.id,
    source: 'runner_failure',
    reason_code: 'ai_unavailable',
    urgency: 'normal',
    summary_for_staff: `Trợ lý AI không soạn được trả lời (${body.error_kind}). Nhân viên trả lời khách giúp.`,
    idempotency_key: `fail:${job.id}`,
  }, now);
  return { job_status: 'failed', handoff_id: handoffId };
}

// ---------------------------------------------------------------- cron sweeps

/** Cron: leased draft_reply jobs past lease_until -> 'failed' + handoff reason 'ai_unavailable'. */
export async function expireLeases(env: Env, now: number): Promise<number> {
  const { results } = await env.DB.prepare(
    "SELECT id, conversation_id, customer_id FROM jobs WHERE type = 'draft_reply' AND status = 'leased' AND lease_until <= ?",
  )
    .bind(now)
    .all<{ id: string; conversation_id: string; customer_id: string }>();
  let n = 0;
  for (const j of results) {
    const r = await env.DB.prepare("UPDATE jobs SET status = 'failed', last_error = 'lease_expired', updated_at = ? WHERE id = ? AND status = 'leased' AND lease_until <= ?")
      .bind(now, j.id, now)
      .run();
    if (!r.meta.changes) continue;
    n++;
    if (await conversationIsInternal(env, j.conversation_id)) continue; // section 14.3: nothing reaches staff
    await createHandoff(env, {
      conversation_id: j.conversation_id,
      customer_id: j.customer_id,
      job_id: j.id,
      source: 'runner_failure',
      reason_code: 'ai_unavailable',
      urgency: 'normal',
      summary_for_staff: 'Máy chạy model không gửi bản nháp kịp (hết hạn lease). Nhân viên trả lời khách giúp.',
      idempotency_key: `expire:${j.id}`,
    }, now);
  }
  return n;
}

/**
 * Whether a runner status snapshot (last POST /runner/status body) says the runner can draft: at least one account
 * with usable_now !== false. A snapshot without an accounts array (older runner, none reported yet) counts as able.
 */
export function runnerCanDraft(snapshotJson: string | null): boolean {
  if (!snapshotJson) return true;
  try {
    const accounts = (JSON.parse(snapshotJson) as { accounts?: unknown }).accounts;
    if (!Array.isArray(accounts)) return true;
    return accounts.some((a) => a && typeof a === 'object' && (a as { usable_now?: unknown }).usable_now !== false);
  } catch {
    return true;
  }
}

/**
 * Cron: when no runner that can draft was seen for RUNNER_OFFLINE_MS, queued draft_reply jobs older than that go to
 * staff. "Can draft" also needs a usable Claude account in the runner's last status: a runner whose only account hit
 * its weekly limit keeps reporting status but stops claiming, and its jobs would otherwise wait in the queue forever.
 */
export async function sweepRunnerHealth(env: Env, now: number): Promise<number> {
  const offlineMs = runnerOfflineMs(env);
  const { results: runners } = await env.DB.prepare('SELECT last_seen_at, snapshot_json FROM runner_status').all<{
    last_seen_at: number;
    snapshot_json: string | null;
  }>();
  const alive = runners.filter((r) => now - r.last_seen_at <= offlineMs);
  if (alive.some((r) => runnerCanDraft(r.snapshot_json))) return 0;
  const noAccount = alive.length > 0;
  const { results } = await env.DB.prepare(
    "SELECT id, conversation_id, customer_id FROM jobs WHERE type = 'draft_reply' AND status = 'queued' AND created_at < ?",
  )
    .bind(now - offlineMs)
    .all<{ id: string; conversation_id: string; customer_id: string }>();
  let n = 0;
  for (const j of results) {
    if (await conversationIsInternal(env, j.conversation_id)) {
      // Section 14.3: a job queued before the contact became internal is dropped, nothing reaches staff.
      await env.DB.prepare("UPDATE jobs SET status = 'cancelled', last_error = 'internal_contact', updated_at = ? WHERE id = ? AND status = 'queued'").bind(now, j.id).run();
      continue;
    }
    const r = await env.DB.prepare("UPDATE jobs SET status = 'needs_staff', last_error = ?, updated_at = ? WHERE id = ? AND status = 'queued'")
      .bind(noAccount ? 'runner_no_account' : 'runner_offline', now, j.id)
      .run();
    if (!r.meta.changes) continue;
    n++;
    await createHandoff(env, {
      conversation_id: j.conversation_id,
      customer_id: j.customer_id,
      job_id: j.id,
      source: 'server',
      reason_code: 'ai_unavailable',
      urgency: 'normal',
      summary_for_staff: noAccount
        ? 'Runner không còn tài khoản Claude dùng được (hết hạn mức hoặc hết đăng nhập). Nhân viên trả lời khách giúp.'
        : 'Máy chạy model đang offline. Nhân viên trả lời khách giúp.',
      idempotency_key: `offline:${j.id}`,
    }, now);
  }
  return n;
}
