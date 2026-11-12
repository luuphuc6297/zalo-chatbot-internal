// Owner: server-core. Row types and small D1 helpers shared by jobs, tools, DO, runner and staff APIs.
import type { BotState, ConversationMode, Env, HandoffReasonCode, HandoffSource, Ms } from '../types';
import { newId } from './ids';
import { HttpError } from './http';
import { conversationIsInternal } from './roles';

export interface CustomerRow {
  id: string;
  oa_id: string;
  zalo_user_id: string;
  user_id_by_app: string | null;
  display_name: string | null;
  phone: string | null;
  preferred_address_form: string | null;
  gender_hint: string;
  minor_flag: number | null;
  created_at: Ms;
  last_user_interaction_at: Ms | null;
  deleted_at: Ms | null;
}

export interface ConversationRow {
  id: string;
  customer_id: string;
  oa_id: string;
  bot_state: BotState;
  mode: ConversationMode | null;
  takeover_by: string | null;
  takeover_until: Ms | null;
  needs_attention: number;
  session_id: string | null;
  session_turns: number;
  session_started_at: Ms | null;
  session_last_turn_at: Ms | null;
  catalog_version: string | null;
  session_reset_reason: string | null;
  last_message_at: Ms | null;
  last_customer_message_at: Ms | null;
  debounce_until: Ms | null;
  created_at: Ms;
  updated_at: Ms;
  answered_seq: number;
  consent_seq: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_write_tokens: number;
  total_cost_usd_equiv: number;
  // Migration 0010 (docs/contracts.md section 14). undefined while the migration is not applied.
  auto_reply?: 'on' | 'off' | null;
  room_channel_id?: string | null;
  room_synced_at?: Ms | null;
}

export interface JobRow {
  id: string;
  type: string;
  conversation_id: string | null;
  customer_id: string | null;
  status: string;
  run_at: Ms;
  lease_until: Ms | null;
  lease_owner: string | null;
  attempts: number;
  max_attempts: number;
  max_lateness_ms: number | null;
  stale: number;
  payload_json: string;
  result_json: string | null;
  dedupe_key: string | null;
  last_error: string | null;
  created_at: Ms;
  updated_at: Ms;
}

/** payload_json of a draft_reply job; filled at claim time. */
export interface DraftJobPayload {
  last_customer_message_id?: string;
  up_to_seq?: number; // highest customer message seq handed to the runner
  catalog_version?: string;
  session_id_given?: string | null;
  session_reset_reason?: string | null;
  cancel_reason?: string;
}

export interface MessageRow {
  id: string;
  conversation_id: string;
  direction: 'inbound' | 'outbound';
  source: 'customer' | 'bot' | 'staff' | 'server';
  kind: string;
  text: string | null;
  attachments_json: string | null;
  zalo_msg_id: string | null;
  draft_id: string | null;
  staff_id: string | null;
  send_state: string;
  created_at: Ms;
  sent_at: Ms | null;
  seq: number;
}

export interface DraftRow {
  id: string;
  job_id: string;
  conversation_id: string;
  text: string;
  final_text: string | null;
  status: string;
  checker_passed: number;
  checker_result_json: string;
  account_label: string | null;
  session_id: string | null;
  model: string | null;
  effort: string | null;
  usage_json: string | null;
  cost_usd_equiv: number | null;
  duration_ms: number | null;
  catalog_version: string | null;
  decided_by: string | null;
  decided_at: Ms | null;
  reject_reason: string | null;
  sent_message_id: string | null;
  created_at: Ms;
}

export async function getConversation(env: Env, id: string): Promise<ConversationRow | null> {
  return env.DB.prepare('SELECT * FROM conversations WHERE id = ?').bind(id).first<ConversationRow>();
}

export async function mustConversation(env: Env, id: string): Promise<ConversationRow> {
  const c = await getConversation(env, id);
  if (!c) throw new HttpError(404, 'not_found', 'conversation not found');
  return c;
}

export async function getCustomer(env: Env, id: string): Promise<CustomerRow | null> {
  return env.DB.prepare('SELECT * FROM customers WHERE id = ?').bind(id).first<CustomerRow>();
}

export async function getJob(env: Env, id: string): Promise<JobRow | null> {
  return env.DB.prepare('SELECT * FROM jobs WHERE id = ?').bind(id).first<JobRow>();
}

export function parsePayload(job: Pick<JobRow, 'payload_json'>): DraftJobPayload {
  try {
    return JSON.parse(job.payload_json || '{}') as DraftJobPayload;
  } catch {
    return {};
  }
}

export async function activeCatalogVersion(env: Env): Promise<string | null> {
  const r = await env.DB.prepare("SELECT id FROM catalog_versions WHERE status = 'active'").first<{ id: string }>();
  return r?.id ?? null;
}

/** Latest consent status per purpose for a customer. */
export async function consentStatus(
  env: Env,
  customerId: string,
): Promise<Record<string, { status: 'granted' | 'withdrawn'; recorded_at: Ms } | undefined>> {
  const { results } = await env.DB.prepare(
    'SELECT purpose, status, recorded_at FROM consents WHERE customer_id = ? ORDER BY recorded_at ASC, rowid ASC',
  )
    .bind(customerId)
    .all<{ purpose: string; status: 'granted' | 'withdrawn'; recorded_at: Ms }>();
  const out: Record<string, { status: 'granted' | 'withdrawn'; recorded_at: Ms } | undefined> = {};
  for (const r of results) out[r.purpose] = { status: r.status, recorded_at: r.recorded_at };
  return out;
}

export async function hasAiConsent(env: Env, customerId: string): Promise<boolean> {
  return (await consentStatus(env, customerId)).ai_assistant?.status === 'granted';
}

export interface HandoffInput {
  conversation_id: string;
  customer_id: string;
  job_id?: string | null;
  source: HandoffSource;
  reason_code: HandoffReasonCode;
  urgency: 'urgent' | 'normal';
  summary_for_staff?: string | null;
  idempotency_key?: string | null;
}

/** INSERT OR IGNORE so a repeated idempotency_key is a no-op. Also flags the conversation for staff. */
export function handoffStatements(env: Env, h: HandoffInput, now: Ms): { id: string; stmts: D1PreparedStatement[] } {
  const id = newId('hof', now);
  return {
    id,
    stmts: [
      env.DB.prepare(
        'INSERT OR IGNORE INTO handoffs (id, conversation_id, customer_id, job_id, source, reason_code, urgency, summary_for_staff, status, idempotency_key, created_at) ' +
          "VALUES (?,?,?,?,?,?,?,?,'open',?,?)",
      ).bind(
        id,
        h.conversation_id,
        h.customer_id,
        h.job_id ?? null,
        h.source,
        h.reason_code,
        h.urgency,
        h.summary_for_staff ?? null,
        h.idempotency_key ?? null,
        now,
      ),
      env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, h.conversation_id),
    ],
  };
}

/** Creates a handoff (idempotent on idempotency_key) and returns the id of the stored row. */
export async function createHandoff(env: Env, h: HandoffInput, now: Ms): Promise<string> {
  const { id, stmts } = handoffStatements(env, h, now);
  await env.DB.batch(stmts);
  if (h.idempotency_key) {
    const r = await env.DB.prepare('SELECT id FROM handoffs WHERE idempotency_key = ?').bind(h.idempotency_key).first<{ id: string }>();
    return r?.id ?? id;
  }
  return id;
}

/** Cancels queued draft_reply jobs of a conversation (takeover, handoff, mode off). Leased jobs see cancel on heartbeat. */
export function cancelQueuedDraftJobs(env: Env, conversationId: string, reason: string, now: Ms, exceptJobId = ''): D1PreparedStatement {
  return env.DB.prepare(
    "UPDATE jobs SET status = 'cancelled', last_error = ?, updated_at = ? WHERE conversation_id = ? AND type = 'draft_reply' AND status = 'queued' AND id != ?",
  ).bind(reason, now, conversationId, exceptJobId);
}

export function safeJson<T>(s: string | null | undefined, fallback: T): T {
  if (!s) return fallback;
  try {
    return JSON.parse(s) as T;
  } catch {
    return fallback;
  }
}

/**
 * Recomputes conversations.needs_attention after a staff action (approve, reject, manual send, resolve handoff).
 * Stays 1 while bot_state is handoff_requested, a draft waits for staff, a handoff is open, or a customer message is unanswered with no draft job
 * on the way; otherwise 0. Integration fix: the flag was set in many places but only cleared on release.
 */
export async function refreshNeedsAttention(env: Env, conversationId: string, now: Ms): Promise<void> {
  // An internal contact (role manager or staff, section 14.3) never needs attention because of an unanswered message:
  // the server stores what they write and does nothing else. The other reasons (a handoff, a waiting draft) stay.
  const unanswered = (await conversationIsInternal(env, conversationId))
    ? ''
    : "OR (EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = conversations.id AND m.source = 'customer' AND m.seq > conversations.answered_seq) " +
      "AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.conversation_id = conversations.id AND j.type = 'draft_reply' AND j.status IN ('queued','leased'))) ";
  await env.DB.prepare(
    'UPDATE conversations SET needs_attention = CASE WHEN ' +
      "conversations.bot_state = 'handoff_requested' OR " +
      "EXISTS (SELECT 1 FROM drafts d WHERE d.conversation_id = conversations.id AND d.status IN ('pending','blocked')) " +
      "OR EXISTS (SELECT 1 FROM handoffs h WHERE h.conversation_id = conversations.id AND h.status = 'open') " +
      unanswered +
      'THEN 1 ELSE 0 END, updated_at = ? WHERE id = ?',
  )
    .bind(now, conversationId)
    .run();
}
