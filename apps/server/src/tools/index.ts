// Owner: server-core. Server side of the 9 model tools (design/tools-schema.json + x_server_policy).
// Read tools take the catalog_version of the job; write tools are idempotent per job (tool_calls.idempotency_key)
// and act ONLY on the job's conversation: no tool input names a conversation, customer or job.
import type { Env, HandoffReasonCode, ToolName } from '../types';
import { TOOL_NAMES, WRITE_TOOLS } from '../types';
import { newId } from '../lib/ids';
import { canonicalJson, fmtVnd, sha256Hex, stripMarks } from '../lib/text';
import { isValidLocalDate, localDate, localMidnight } from '../lib/time';
import { cancelQueuedDraftJobs, getConversation, handoffStatements, hasAiConsent, safeJson } from '../lib/db';
import { auditStatement } from '../lib/audit';
import { quotePrice, type QuoteVariant } from './quote';
import { ATTACH_GROUP_VALUES, attachMenuImages } from './menu-images';
import { customerFactsForModel, normalizePhone } from '../lib/customer-summary';
import { conversationIsInternal } from '../lib/roles';

export interface ToolContext {
  job_id: string;
  conversation_id: string;
  customer_id: string;
  catalog_version: string;
  now: number;
}

export interface ToolOutcome {
  result: unknown;
  is_error: boolean;
}

export interface StoredToolOutcome extends ToolOutcome {
  tool_call_id: string;
  replayed: boolean;
}

// ---------------------------------------------------------------- input validation

type FieldSpec =
  | { t: 'string'; enum?: readonly string[]; max?: number }
  | { t: 'integer'; min?: number; max?: number }
  | { t: 'boolean' }
  | { t: 'string[]'; max?: number };

const HANDOFF_REASONS = [
  'customer_requested_human', 'pregnancy', 'postpartum', 'chronic_or_serious_condition', 'medication', 'recent_surgery',
  'skin_lesion_or_wound', 'adverse_reaction_after_visit', 'possible_minor', 'medical_suitability_question', 'complaint',
  'refund_or_payment', 'reschedule_or_cancel', 'harassment_or_inappropriate', 'data_rights_request', 'unknown_answer',
  'price_ambiguity', 'large_group', 'emergency_symptoms', 'other',
] as const;

const SPECS: Record<ToolName, Record<string, FieldSpec>> = {
  search_services: {
    query: { t: 'string', max: 300 },
    group: { t: 'string', enum: ['any', 'relaxation', 'health', 'women', 'skin', 'hair'] },
    include_prices: { t: 'boolean' },
  },
  get_service_details: { service_id: { t: 'string', max: 100 } },
  quote_price: {
    service_id: { t: 'string', max: 100 },
    duration_min: { t: 'integer', min: 0, max: 600 },
    start_time_local: { t: 'string', max: 10 },
    date_local: { t: 'string', max: 10 },
  },
  list_active_promotions: { service_id: { t: 'string', max: 100 } },
  create_booking_request: {
    service_ids: { t: 'string[]', max: 6 },
    duration_min: { t: 'integer', min: 0, max: 600 },
    preferred_date_local: { t: 'string', max: 10 },
    preferred_time_window: { t: 'string', max: 20 },
    party_size: { t: 'integer' },
    customer_name: { t: 'string', max: 100 },
    contact_method: { t: 'string', enum: ['zalo_chat_only', 'phone_shared_with_consent'] },
    phone: { t: 'string', max: 30 },
    notes_for_staff: { t: 'string', max: 500 },
    price_quoted_text: { t: 'string', max: 200 },
  },
  handoff_to_staff: {
    // Always accepted: bad reason/urgency values are coerced, never rejected (policy: handoff never fails closed).
    reason_code: { t: 'string', max: 64 },
    urgency: { t: 'string', max: 16 },
    summary_for_staff: { t: 'string', max: 4000 },
  },
  record_contact_preference: {
    preference_type: { t: 'string', enum: ['promotions', 'followup_care', 'all_proactive_messages', 'ai_assistant'] },
    action: { t: 'string', enum: ['opt_out', 'request_opt_in'] },
    customer_words: { t: 'string', max: 1000 },
  },
  // menu images (task B): src/tools/menu-images.ts checks that exactly one of the two is set
  attach_menu_images: {
    group: { t: 'string', enum: ATTACH_GROUP_VALUES },
    service_id: { t: 'string', max: 100 },
  },
  // read tool of docs/contracts.md section 14.6: no input, the customer is the one of the job
  get_customer_profile: {},
};

export function validateToolInput(name: ToolName, input: unknown): { ok: true } | { ok: false; field: string; detail: string } {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return { ok: false, field: '$', detail: 'input must be an object' };
  // handoff_to_staff never fails closed: its input is coerced in handoffToStaff instead of validated.
  if (name === 'handoff_to_staff') return { ok: true };
  const spec = SPECS[name];
  const obj = input as Record<string, unknown>;
  for (const k of Object.keys(obj)) if (!(k in spec)) return { ok: false, field: k, detail: 'unknown field' };
  for (const [k, f] of Object.entries(spec)) {
    const v = obj[k];
    if (v === undefined) return { ok: false, field: k, detail: 'required' };
    if (f.t === 'string') {
      if (typeof v !== 'string') return { ok: false, field: k, detail: 'must be a string' };
      if (f.enum && !f.enum.includes(v)) return { ok: false, field: k, detail: `must be one of ${f.enum.join(', ')}` };
      if (f.max && v.length > f.max) return { ok: false, field: k, detail: `longer than ${f.max}` };
    } else if (f.t === 'integer') {
      if (typeof v !== 'number' || !Number.isInteger(v)) return { ok: false, field: k, detail: 'must be an integer' };
      if (f.min !== undefined && v < f.min) return { ok: false, field: k, detail: `below ${f.min}` };
      if (f.max !== undefined && v > f.max) return { ok: false, field: k, detail: `above ${f.max}` };
    } else if (f.t === 'boolean') {
      if (typeof v !== 'boolean') return { ok: false, field: k, detail: 'must be a boolean' };
    } else if (f.t === 'string[]') {
      if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) return { ok: false, field: k, detail: 'must be an array of strings' };
      if (f.max && v.length > f.max) return { ok: false, field: k, detail: `more than ${f.max} items` };
    }
  }
  return { ok: true };
}

// ---------------------------------------------------------------- catalog reads

interface ServiceRow {
  service_id: string;
  group_code: string;
  display_name_vi: string;
  name_vi: string;
  short_description_vi: string | null;
  process_steps_json: string;
  is_signature: number;
  approval_status: string;
}

async function loadCatalog(env: Env, cv: string): Promise<{ services: ServiceRow[]; variants: (QuoteVariant & { service_id: string })[] }> {
  const [s, v] = await env.DB.batch([
    env.DB.prepare(
      'SELECT service_id, group_code, display_name_vi, name_vi, short_description_vi, process_steps_json, is_signature, approval_status FROM services WHERE catalog_version = ?',
    ).bind(cv),
    env.DB.prepare('SELECT service_id, duration_min, time_window, price_vnd FROM service_variants WHERE catalog_version = ? ORDER BY id').bind(cv),
  ]);
  return { services: s!.results as unknown as ServiceRow[], variants: v!.results as unknown as (QuoteVariant & { service_id: string })[] };
}

function variantView(vs: QuoteVariant[], includePrices: boolean) {
  return vs.map((v) => ({
    duration_min: v.duration_min,
    time_window: v.time_window,
    ...(includePrices ? { price_vnd: v.price_vnd, price_text: fmtVnd(v.price_vnd) } : {}),
  }));
}

async function searchServices(env: Env, ctx: ToolContext, input: { query: string; group: string; include_prices: boolean }) {
  const { services, variants } = await loadCatalog(env, ctx.catalog_version);
  const q = stripMarks(input.query ?? '').trim();
  const tokens = q.split(/[^\p{L}\p{N}]+/u).filter((t) => t.length > 1);
  const hits: Array<{ score: number; s: ServiceRow }> = [];
  for (const s of services) {
    if (input.group !== 'any' && s.group_code !== input.group) continue;
    const steps = safeJson<string[]>(s.process_steps_json, []);
    const hay = stripMarks([s.service_id.replaceAll('-', ' '), s.display_name_vi, s.name_vi, s.short_description_vi ?? '', steps.join(' ')].join(' '));
    const name = stripMarks(`${s.service_id.replaceAll('-', ' ')} | ${s.display_name_vi} | ${s.name_vi}`);
    const nameWords = name.split(/[^\p{L}\p{N}]+/u);
    let score = tokens.length ? tokens.filter((t) => hay.includes(t)).length : 1;
    score += tokens.filter((t) => nameWords.includes(t)).length * 2;
    if (q && name.includes(q)) score += 10;
    if (score) hits.push({ score, s });
  }
  hits.sort((a, b) => b.score - a.score);
  const limit = tokens.length ? 8 : hits.length;
  return {
    catalog_version_id: ctx.catalog_version,
    services: hits.slice(0, limit).map(({ s }) => ({
      service_id: s.service_id,
      group: s.group_code,
      display_name_vi: s.display_name_vi,
      is_signature: !!s.is_signature,
      variants: variantView(variants.filter((v) => v.service_id === s.service_id), input.include_prices),
    })),
  };
}

async function getServiceDetails(env: Env, ctx: ToolContext, input: { service_id: string }) {
  const { services, variants } = await loadCatalog(env, ctx.catalog_version);
  const s = services.find((x) => x.service_id === input.service_id);
  if (!s) return { result: { status: 'not_found', service_id: input.service_id, catalog_version_id: ctx.catalog_version }, is_error: false };
  const steps = safeJson<string[]>(s.process_steps_json, []);
  return {
    result: {
      status: 'ok',
      catalog_version_id: ctx.catalog_version,
      service_id: s.service_id,
      group: s.group_code,
      display_name_vi: s.display_name_vi,
      is_signature: !!s.is_signature,
      data_status: s.approval_status,
      short_description_vi: s.short_description_vi || { status: 'missing' },
      process_steps_vi: steps.length ? steps : { status: 'missing' },
      variants: variantView(variants.filter((v) => v.service_id === s.service_id), true),
      // Never sent to the model until the owner approves them (flagged_claims, conflicts, derived cautions).
      who_should_avoid_or_consult: { status: 'unapproved' },
      ingredients_or_devices: { status: 'unapproved' },
    },
    is_error: false,
  };
}

async function quote(env: Env, ctx: ToolContext, input: { service_id: string; duration_min: number; start_time_local: string; date_local: string }) {
  if (input.start_time_local !== 'unknown' && !/^\d{1,2}:\d{2}$/.test(input.start_time_local)) {
    return { result: { error: 'validation_failed', field: 'start_time_local', detail: "use HH:MM or 'unknown'" }, is_error: true };
  }
  if (input.date_local !== 'unknown' && !isValidLocalDate(input.date_local)) {
    return { result: { error: 'validation_failed', field: 'date_local', detail: "use YYYY-MM-DD or 'unknown'" }, is_error: true };
  }
  const { variants } = await loadCatalog(env, ctx.catalog_version);
  const vs = variants.filter((v) => v.service_id === input.service_id);
  if (!vs.length) return { result: { status: 'not_found', service_id: input.service_id, catalog_version_id: ctx.catalog_version }, is_error: false };
  return { result: quotePrice(input, vs, ctx.catalog_version), is_error: false };
}

async function listActivePromotions(env: Env, ctx: ToolContext, input: { service_id: string }) {
  const { results } = await env.DB.prepare(
    "SELECT id, title, approved_text_vi, conditions_vi, service_ids_json, valid_from, valid_to FROM promotions WHERE status IN ('approved','scheduled','sending') AND valid_from <= ? AND valid_to >= ? ORDER BY valid_from",
  )
    .bind(ctx.now, ctx.now)
    .all<{ id: string; title: string; approved_text_vi: string; conditions_vi: string | null; service_ids_json: string; valid_from: number; valid_to: number }>();
  const promos = results
    .filter((p) => {
      const ids = safeJson<string[]>(p.service_ids_json, []);
      return input.service_id === 'any' || !ids.length || ids.includes(input.service_id);
    })
    .map((p) => ({
      promotion_id: p.id,
      title: p.title,
      approved_text_vi: p.approved_text_vi,
      conditions_vi: p.conditions_vi,
      service_ids: safeJson<string[]>(p.service_ids_json, []),
      valid_until_local: localDate(p.valid_to),
    }));
  return { catalog_version_id: ctx.catalog_version, promotions: promos };
}

// ---------------------------------------------------------------- writes

const err = (code: string, extra: Record<string, unknown> = {}): ToolOutcome => ({ result: { status: 'rejected', error: code, ...extra }, is_error: true });

async function createBookingRequest(
  env: Env,
  ctx: ToolContext,
  input: {
    service_ids: string[];
    duration_min: number;
    preferred_date_local: string;
    preferred_time_window: string;
    party_size: number;
    customer_name: string;
    contact_method: 'zalo_chat_only' | 'phone_shared_with_consent';
    phone: string;
    notes_for_staff: string;
    price_quoted_text: string;
  },
): Promise<ToolOutcome> {
  const conv = await getConversation(env, ctx.conversation_id);
  if (!conv || conv.bot_state !== 'bot_active') return err('conversation_not_active', { detail: 'the conversation is with staff; do not record bookings, tell the customer staff will reply' });
  if (!(await hasAiConsent(env, ctx.customer_id))) return err('no_ai_consent');

  const { services, variants } = await loadCatalog(env, ctx.catalog_version);
  const ids = input.service_ids.map((s) => s.trim()).filter(Boolean);
  if (!ids.length) return err('validation_failed', { field: 'service_ids' });
  const chuaChon = ids.length === 1 && ids[0] === 'chua_chon';
  if (!chuaChon) {
    const unknown = ids.filter((id) => !services.some((s) => s.service_id === id));
    if (unknown.length) return err('unknown_service', { field: 'service_ids', unknown });
    if (input.duration_min !== 0) {
      const durs = [...new Set(variants.filter((v) => v.service_id === ids[0]).map((v) => v.duration_min))].sort((a, b) => a - b);
      if (!durs.includes(input.duration_min)) return err('invalid_duration', { field: 'duration_min', valid_durations: durs });
    }
  }
  if (!isValidLocalDate(input.preferred_date_local)) return err('validation_failed', { field: 'preferred_date_local', detail: 'use YYYY-MM-DD' });
  if (input.preferred_date_local < localDate(ctx.now)) return err('date_in_past', { field: 'preferred_date_local', today_local: localDate(ctx.now) });
  if (!/^\d{1,2}:\d{2}(\s*-\s*\d{1,2}:\d{2})?$/.test(input.preferred_time_window.trim())) {
    return err('validation_failed', { field: 'preferred_time_window', detail: 'use HH:MM or HH:MM-HH:MM' });
  }
  if (input.party_size < 1) return err('validation_failed', { field: 'party_size', detail: 'at least 1' });
  if (input.party_size > 6) return err('large_group', { field: 'party_size', detail: 'groups above 6 go to staff: call handoff_to_staff with reason large_group' });
  const name = input.customer_name.trim();
  if (!name) return err('validation_failed', { field: 'customer_name' });

  let phone: string | null = null;
  if (input.contact_method === 'phone_shared_with_consent') {
    const typed = input.phone.trim();
    const digits = typed.replace(/\D/g, '');
    if (digits.length < 9 || digits.length > 12) return err('validation_failed', { field: 'phone' });
    const { results } = await env.DB.prepare(
      "SELECT text FROM messages WHERE conversation_id = ? AND direction = 'inbound' AND source = 'customer' AND text IS NOT NULL",
    )
      .bind(ctx.conversation_id)
      .all<{ text: string }>();
    const found = results.some((m) => m.text.includes(typed) || m.text.replace(/[\s.\-()]/g, '').includes(digits));
    if (!found) return err('phone_not_from_customer', { field: 'phone', detail: 'the phone must be typed by the customer in this chat' });
    phone = typed;
  }
  // Section 14.5: a phone the customer gave is copied into an empty customers.phone, normalised as PATCH
  // /staff/customers/:id does. A number staff (or an earlier booking) stored is never overwritten.
  const customerPhone = normalizePhone(phone);

  // Rate limit: at most 3 open requests per customer per local day.
  const open = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM booking_requests WHERE customer_id = ? AND status IN ('new','proposed') AND created_at >= ?",
  )
    .bind(ctx.customer_id, localMidnight(ctx.now))
    .first<{ n: number }>();

  const idem = `brq:${ctx.conversation_id}:${await sha256Hex(
    canonicalJson({ s: [...ids].sort(), d: input.preferred_date_local, w: input.preferred_time_window.replace(/\s+/g, '') }),
  )}`;
  const existing = await env.DB.prepare('SELECT id, status FROM booking_requests WHERE idempotency_key = ?').bind(idem).first<{ id: string; status: string }>();
  if (existing) {
    return { result: { status: 'created', duplicate: true, request_id: existing.id, staff_confirmation: 'pending', staff_response_target: null }, is_error: false };
  }
  if ((open?.n ?? 0) >= 3) return err('rate_limited', { detail: 'this customer already has 3 open booking requests today; hand off to staff' });

  const id = newId('brq', ctx.now);
  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO booking_requests (id, conversation_id, customer_id, job_id, service_ids_json, duration_min, preferred_date_local, preferred_time_window, party_size, customer_name, contact_method, phone, notes_for_staff, price_quoted_text, catalog_version, status, idempotency_key, created_at, updated_at) ' +
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new',?,?,?)",
    ).bind(
      id,
      ctx.conversation_id,
      ctx.customer_id,
      ctx.job_id,
      JSON.stringify(ids),
      input.duration_min,
      input.preferred_date_local,
      input.preferred_time_window.trim(),
      input.party_size,
      name,
      input.contact_method,
      phone,
      input.notes_for_staff.trim() || null,
      input.price_quoted_text.trim() || null,
      ctx.catalog_version,
      idem,
      ctx.now,
      ctx.now,
    ),
    env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(ctx.now, ctx.conversation_id),
    ...(customerPhone
      ? [env.DB.prepare("UPDATE customers SET phone = ? WHERE id = ? AND (phone IS NULL OR TRIM(phone) = '')").bind(customerPhone, ctx.customer_id)]
      : []),
    auditStatement(env, { actor_type: 'model', actor_id: ctx.job_id, action: 'booking_request.create', entity: 'booking_request', entity_id: id }, ctx.now),
  ]);
  return { result: { status: 'created', request_id: id, staff_confirmation: 'pending', staff_response_target: null }, is_error: false };
}

async function handoffToStaff(env: Env, ctx: ToolContext, input: { reason_code?: string; urgency?: string; summary_for_staff?: string }, idem: string): Promise<ToolOutcome> {
  const reason = (HANDOFF_REASONS as readonly string[]).includes(String(input.reason_code ?? '')) ? (input.reason_code as HandoffReasonCode) : 'other';
  const urgency = input.urgency === 'urgent' ? 'urgent' : 'normal';
  const summary = typeof input.summary_for_staff === 'string' ? input.summary_for_staff.slice(0, 2000) || null : null;
  const h = handoffStatements(env, {
    conversation_id: ctx.conversation_id,
    customer_id: ctx.customer_id,
    job_id: ctx.job_id,
    source: 'model_tool',
    reason_code: reason,
    urgency,
    summary_for_staff: summary,
    idempotency_key: `tool:${idem}`,
  }, ctx.now);
  await env.DB.batch([
    ...h.stmts,
    // Staff states win over handoff_requested; awaiting_consent cannot happen (model is only called in bot_active).
    env.DB.prepare(
      "UPDATE conversations SET bot_state = 'handoff_requested', updated_at = ? WHERE id = ? AND bot_state IN ('bot_active','handoff_requested')",
    ).bind(ctx.now, ctx.conversation_id),
    cancelQueuedDraftJobs(env, ctx.conversation_id, 'handoff', ctx.now, ctx.job_id),
    auditStatement(env, { actor_type: 'model', actor_id: ctx.job_id, action: 'handoff.create', entity: 'conversation', entity_id: ctx.conversation_id, after: { reason_code: reason, urgency } }, ctx.now),
  ]);
  const row = await env.DB.prepare('SELECT id FROM handoffs WHERE idempotency_key = ?').bind(`tool:${idem}`).first<{ id: string }>();
  return {
    result: { status: 'accepted', handoff_id: row?.id ?? h.id, bot_state: 'handoff_requested', urgency, staff_response_target: null },
    is_error: false,
  };
}

const PREF_PURPOSES: Record<string, Array<'promotions' | 'followup_care' | 'ai_assistant'>> = {
  promotions: ['promotions'],
  followup_care: ['followup_care'],
  all_proactive_messages: ['promotions', 'followup_care'],
  ai_assistant: ['ai_assistant'],
};
const PREF_JOB_TYPES: Record<string, string[]> = {
  promotions: ['promo_send'],
  followup_care: ['thank_you', 'check_in'],
  all_proactive_messages: ['promo_send', 'thank_you', 'check_in'],
  ai_assistant: [],
};

async function recordContactPreference(
  env: Env,
  ctx: ToolContext,
  input: { preference_type: string; action: 'opt_out' | 'request_opt_in'; customer_words: string },
  idem: string,
): Promise<ToolOutcome> {
  const lastMsg = await env.DB.prepare(
    "SELECT id FROM messages WHERE conversation_id = ? AND direction = 'inbound' ORDER BY seq DESC LIMIT 1",
  )
    .bind(ctx.conversation_id)
    .first<{ id: string }>();
  const stmts: D1PreparedStatement[] = [
    env.DB.prepare(
      "INSERT OR IGNORE INTO contact_preferences (id, customer_id, preference_type, action, customer_words, source, job_id, idempotency_key, created_at) VALUES (?,?,?,?,?,'model_tool',?,?,?)",
    ).bind(newId('cpf', ctx.now), ctx.customer_id, input.preference_type, input.action, input.customer_words.slice(0, 1000), ctx.job_id, `tool:${idem}`, ctx.now),
    env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(ctx.now, ctx.conversation_id),
  ];
  let cancelled_job_types: string[] = [];
  if (input.action === 'opt_out') {
    for (const purpose of PREF_PURPOSES[input.preference_type] ?? []) {
      stmts.push(
        env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, evidence_message_id, recorded_at) VALUES (?,?,?,'withdrawn','chat_keyword',?,?)")
          .bind(newId('cns', ctx.now), ctx.customer_id, purpose, lastMsg?.id ?? null, ctx.now),
      );
    }
    cancelled_job_types = PREF_JOB_TYPES[input.preference_type] ?? [];
    if (cancelled_job_types.length) {
      stmts.push(
        env.DB.prepare(
          `UPDATE jobs SET status = 'cancelled', last_error = 'opt_out', updated_at = ? WHERE customer_id = ? AND status = 'queued' AND type IN (${cancelled_job_types.map(() => '?').join(',')})`,
        ).bind(ctx.now, ctx.customer_id, ...cancelled_job_types),
      );
    }
    if (input.preference_type === 'ai_assistant') {
      stmts.push(
        env.DB.prepare("UPDATE conversations SET bot_state = 'staff_only', session_id = NULL, session_reset_reason = 'released_by_staff', updated_at = ? WHERE id = ? AND bot_state != 'blocked'")
          .bind(ctx.now, ctx.conversation_id),
        cancelQueuedDraftJobs(env, ctx.conversation_id, 'ai_opt_out', ctx.now, ctx.job_id),
        ...handoffStatements(env, {
          conversation_id: ctx.conversation_id,
          customer_id: ctx.customer_id,
          job_id: ctx.job_id,
          source: 'model_tool',
          reason_code: 'customer_declined_ai',
          urgency: 'normal',
          summary_for_staff: `Khách không muốn trò chuyện với trợ lý AI nữa: "${input.customer_words.slice(0, 300)}"`,
          idempotency_key: `optout:${idem}`,
        }, ctx.now).stmts,
      );
    }
  }
  stmts.push(
    auditStatement(env, { actor_type: 'model', actor_id: ctx.job_id, action: `contact_preference.${input.action}`, entity: 'customer', entity_id: ctx.customer_id, after: { preference_type: input.preference_type } }, ctx.now),
  );
  await env.DB.batch(stmts);
  return {
    result:
      input.action === 'opt_out'
        ? { status: 'recorded', action: 'opt_out', preference_type: input.preference_type, applied: 'immediately', cancelled_job_types }
        : {
            status: 'recorded',
            action: 'request_opt_in',
            preference_type: input.preference_type,
            consent_changed: false,
            note: 'staff will send the official consent message; do not say the customer is subscribed',
          },
    is_error: false,
  };
}

// ---------------------------------------------------------------- entry points

export function isToolName(name: string): name is ToolName {
  return (TOOL_NAMES as string[]).includes(name);
}

/** Runs one tool for the job's conversation. Never throws for bad input: returns is_error with a reason. */
export async function runTool(env: Env, ctx: ToolContext, name: ToolName, input: Record<string, unknown>, idemHash = ''): Promise<ToolOutcome> {
  const v = validateToolInput(name, input);
  if (!v.ok) return { result: { error: 'validation_failed', field: v.field, detail: v.detail }, is_error: true };
  const i = input as never;
  // Internal contact (docs/contracts.md section 14.3): the role was set while this job ran. A write tool would flag
  // the conversation for staff, open a handoff or change bot_state, so it is refused; the job is cancelled on its
  // next heartbeat and its draft is discarded.
  if (WRITE_TOOLS.includes(name) && (await conversationIsInternal(env, ctx.conversation_id))) {
    return { result: { status: 'rejected', error: 'internal_contact', detail: 'the contact is a manager or a staff member; nothing is recorded' }, is_error: true };
  }
  switch (name) {
    case 'search_services':
      return { result: await searchServices(env, ctx, i), is_error: false };
    case 'get_service_details':
      return getServiceDetails(env, ctx, i);
    case 'quote_price':
      return quote(env, ctx, i);
    case 'list_active_promotions':
      return { result: await listActivePromotions(env, ctx, i), is_error: false };
    case 'create_booking_request':
      return createBookingRequest(env, ctx, i);
    case 'handoff_to_staff':
      return handoffToStaff(env, ctx, i, idemHash || `${ctx.job_id}:${ctx.now}`);
    case 'record_contact_preference':
      return recordContactPreference(env, ctx, i, idemHash || `${ctx.job_id}:${ctx.now}`);
    case 'attach_menu_images':
      return attachMenuImages(env, ctx, i);
    case 'get_customer_profile':
      return { result: await customerFactsForModel(env, ctx.customer_id, ctx.catalog_version, ctx.now), is_error: false };
  }
}

/** runTool + tool_calls storage + per-job idempotency for write tools. */
export async function runAndStoreTool(env: Env, ctx: ToolContext, name: ToolName, input: Record<string, unknown>): Promise<StoredToolOutcome> {
  const isWrite = WRITE_TOOLS.includes(name);
  const idem = isWrite ? `${ctx.job_id}:${name}:${await sha256Hex(canonicalJson(input))}` : null;
  if (idem) {
    const prev = await env.DB.prepare('SELECT id, result_json, is_error FROM tool_calls WHERE idempotency_key = ?')
      .bind(idem)
      .first<{ id: string; result_json: string; is_error: number }>();
    if (prev) return { result: JSON.parse(prev.result_json), is_error: !!prev.is_error, tool_call_id: prev.id, replayed: true };
  }
  const out = await runTool(env, ctx, name, input, idem ?? '');
  const id = newId('tcl', ctx.now);
  try {
    await env.DB.prepare(
      'INSERT INTO tool_calls (id, job_id, conversation_id, tool_name, input_json, result_json, is_error, idempotency_key, catalog_version, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
    )
      .bind(id, ctx.job_id, ctx.conversation_id, name, JSON.stringify(input), JSON.stringify(out.result), out.is_error ? 1 : 0, idem, ctx.catalog_version, ctx.now)
      .run();
  } catch (e) {
    // Concurrent identical write call: the other one stored first; replay it.
    if (idem) {
      const prev = await env.DB.prepare('SELECT id, result_json, is_error FROM tool_calls WHERE idempotency_key = ?')
        .bind(idem)
        .first<{ id: string; result_json: string; is_error: number }>();
      if (prev) return { result: JSON.parse(prev.result_json), is_error: !!prev.is_error, tool_call_id: prev.id, replayed: true };
    }
    throw e;
  }
  return { ...out, tool_call_id: id, replayed: false };
}
