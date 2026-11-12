// Owner: server-zalo. Every outbound Zalo call goes through here.
//
// Endpoints (snapshots in research/snapshots/zalo-2026-11-07/):
//   consultation text/buttons  POST https://openapi.zalo.me/v3.0/oa/message/cs        (OA llms-full :597, :12750)
//   ZBS template via UID       POST https://openapi.zalo.me/v3.0/oa/message/template  (ZBS llms-full :2918)
//   user profile               GET  https://openapi.zalo.me/v3.0/oa/user/detail?data={"user_id":...} (OA :7792)
// All take header access_token (src/lib/zalo-token.ts). ZALO_MODE=real is UNTESTED: no real OA yet.
//
// Idempotency: every send has a dedupe key (SendContext.dedupe_key, default 'msg:' + message_id). The outbox row
// is inserted with that key BEFORE calling Zalo; a repeated call with the same key returns the stored outcome
// and never calls Zalo again. Outcomes:
//   sent     Zalo answered error = 0 (mock: always)            -> { ok: true, zalo_msg_id }
//   failed   Zalo answered an explicit error (message not sent) -> { ok: false, unknown: false }
//   unknown  timeout / network / 5xx / unreadable answer        -> { ok: false, unknown: true }
// 'unknown' is never retried here: the Zalo send APIs have no idempotency key, so a blind retry can deliver twice.
// The caller decides (conversation reply: staff/reconcile; follow-up: needs_staff).
// The only automatic retry is after an explicit token error (-216/-220/-124): Zalo rejected the call, so
// nothing was delivered; we force one refresh and try once more.
//
// Callers must check flags.outbound_enabled BEFORE calling; the client re-checks and refuses when false.
//
// Personal Zalo channel (docs/contracts.md "Personal Zalo channel"): a recipient whose id starts with 'p:' is a
// personal-account thread. Its sends never touch the network here: the client writes an outbox row with
// zalo_mode = 'personal', status = 'queued' and the exact plain text (buttons spelled out as "Nhắn ..." lines,
// follow-up templates as their chat version), and returns { ok: true, queued: true }. apps/zalo-bridge claims the row
// (POST /bridge/outbox/claim) and reports the outcome (src/bridge/outbox.ts). With ZALO_MODE=personal a send to an
// OA user is refused with error_code 'channel_mismatch' (no OA transport is configured in that mode).
import type { Env, ZaloButton, ZaloSendOutcome } from '../types';
import { newId } from './ids';
import { HttpError } from './http';
import { getAccessToken, refreshIfNeeded, type TokenDeps } from './zalo-token';
import { buttonsAsText, isPersonalUserId, threadIdOf } from './zalo-personal';
import { hasChatTemplate, renderChatTemplate } from '../scheduler/templates';

export const CS_URL = 'https://openapi.zalo.me/v3.0/oa/message/cs';
export const TEMPLATE_UID_URL = 'https://openapi.zalo.me/v3.0/oa/message/template';
export const USER_DETAIL_URL = 'https://openapi.zalo.me/v3.0/oa/user/detail';
export const CS_TEXT_MAX = 2000;
const HTTP_TIMEOUT_MS = 10_000;
const TOKEN_ERRORS = new Set([-216, -220, -124]);

export type TemplateKey = 'thank_you' | 'check_in' | 'reconnect' | 'promo' | 'booking_received';

export interface SendContext {
  conversation_id: string | null;
  customer_id: string | null;
  message_id: string | null; // messages.id written with send_state='pending' before the call
  /** One logical send = one key. Default 'msg:' + message_id. Without both, the send is not deduplicated. */
  dedupe_key?: string | null;
}

export interface ClientDeps extends TokenDeps {
  now?: () => number;
}

// ---------------------------------------------------------------- kill switches (read from D1, no cache)

export interface SendFlags {
  outbound_enabled: boolean;
  scheduled_sends_enabled: boolean;
  promotions_enabled: boolean;
}

/** Reads the send-related kill switches straight from D1 (defaults from docs/contracts.md when a row is missing). */
export async function readSendFlags(env: Env): Promise<SendFlags> {
  const rows = await env.DB.prepare(
    "SELECT name, value_json FROM flags WHERE name IN ('outbound_enabled','scheduled_sends_enabled','promotions_enabled')",
  ).all<{ name: string; value_json: string }>();
  const out: SendFlags = { outbound_enabled: true, scheduled_sends_enabled: false, promotions_enabled: false };
  for (const r of rows.results ?? []) {
    let v: unknown;
    try {
      v = JSON.parse(r.value_json);
    } catch {
      continue;
    }
    if (typeof v === 'boolean' && r.name in out) out[r.name as keyof SendFlags] = v;
  }
  return out;
}

// ---------------------------------------------------------------- outbox helpers

interface OutboxRow {
  id: string;
  status: 'pending' | 'queued' | 'leased' | 'sent' | 'failed' | 'unknown';
  zalo_msg_id: string | null;
  error: string | null;
}

function outcomeFromRow(row: OutboxRow): ZaloSendOutcome {
  if (row.status === 'sent' && row.zalo_msg_id) return { ok: true, zalo_msg_id: row.zalo_msg_id, outbox_id: row.id };
  if (row.status === 'sent') return { ok: true, zalo_msg_id: `unknown_id_${row.id}`, outbox_id: row.id };
  // personal channel: still waiting for (or being sent by) the bridge
  if (row.status === 'queued' || row.status === 'leased') return { ok: true, queued: true, zalo_msg_id: null, outbox_id: row.id };
  if (row.status === 'failed') {
    const [code, ...rest] = (row.error ?? 'failed').split(': ');
    return { ok: false, unknown: false, error_code: code ?? 'failed', error_message: rest.join(': ') || 'send failed', outbox_id: row.id };
  }
  // pending (another call is in flight or crashed mid-send) or unknown: never send again automatically
  return {
    ok: false,
    unknown: true,
    error_code: row.status === 'pending' ? 'send_in_progress' : 'send_unknown',
    error_message: 'an earlier send with the same dedupe key has no confirmed outcome',
    outbox_id: row.id,
  };
}

async function findByKey(env: Env, key: string): Promise<OutboxRow | null> {
  return env.DB.prepare('SELECT id, status, zalo_msg_id, error FROM outbox WHERE dedupe_key = ?').bind(key).first<OutboxRow>();
}

async function finish(env: Env, id: string, status: 'sent' | 'failed' | 'unknown', zaloMsgId: string | null, error: string | null, now: number): Promise<void> {
  await env.DB.prepare('UPDATE outbox SET status = ?, zalo_msg_id = ?, error = ?, sent_at = ? WHERE id = ?')
    .bind(status, zaloMsgId, error, status === 'sent' ? now : null, id)
    .run();
}

type ZaloCall = { kind: 'ok'; json: Record<string, unknown> } | { kind: 'unknown'; reason: string };

async function postJson(f: typeof fetch, url: string, token: string, body: unknown): Promise<ZaloCall> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await f(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', access_token: token },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (res.status >= 500) return { kind: 'unknown', reason: `http_${res.status}` };
    try {
      return { kind: 'ok', json: (await res.json()) as Record<string, unknown> };
    } catch {
      return { kind: 'unknown', reason: `unreadable_response_http_${res.status}` };
    }
  } catch (err) {
    return { kind: 'unknown', reason: err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'network_error' };
  } finally {
    clearTimeout(timer);
  }
}

function zaloMsgIdOf(json: Record<string, unknown>): string | null {
  const data = (json.data ?? {}) as Record<string, unknown>;
  const id = data.message_id ?? data.msg_id;
  return typeof id === 'string' && id ? id : typeof id === 'number' ? String(id) : null;
}

type Kind = 'cs_text' | 'cs_buttons' | 'zbs_template';

/** 'personal' when the recipient is a personal-account thread; 'mismatch' when ZALO_MODE=personal but it is an OA user. */
export function transportFor(env: Env, zaloUserId: string): 'personal' | 'mismatch' | 'oa' {
  if (isPersonalUserId(zaloUserId)) return 'personal';
  return env.ZALO_MODE === 'personal' ? 'mismatch' : 'oa';
}

/** Personal channel: one outbox row with status 'queued' and the exact text the bridge will send. No network. */
async function queuePersonal(
  env: Env,
  kind: Kind,
  zaloUserId: string,
  text: string,
  extra: Record<string, unknown>,
  ctx: SendContext,
  templateKey: TemplateKey | null,
  key: string | null,
  now: number,
): Promise<ZaloSendOutcome> {
  const threadId = threadIdOf(zaloUserId)!;
  const id = newId('obx', now);
  const payload = { thread_id: threadId, text, ...extra };
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO outbox (id, kind, zalo_mode, channel, conversation_id, customer_id, zalo_user_id, thread_id, text, message_id, payload_json, status,
       attempts, next_attempt_at, created_at, updated_at, dedupe_key, template_key)
     VALUES (?,?,'personal','personal',?,?,?,?,?,?,?,'queued', 0, ?, ?, ?, ?, ?)`,
  )
    .bind(id, kind, ctx.conversation_id, ctx.customer_id, zaloUserId, threadId, text, ctx.message_id, JSON.stringify(payload), now, now, now, key, templateKey)
    .run();
  if ((ins.meta.changes ?? 0) === 0 && key) {
    const existing = await findByKey(env, key);
    if (existing) return outcomeFromRow(existing);
  }
  return { ok: true, queued: true, zalo_msg_id: null, outbox_id: id };
}

interface PersonalForm {
  text: string; // exact plain text for the personal channel
  extra: Record<string, unknown>; // kept in payload_json for staff (e.g. the original buttons, template params)
}

async function send(
  env: Env,
  kind: Kind,
  zaloUserId: string,
  url: string,
  payload: Record<string, unknown>,
  ctx: SendContext,
  templateKey: TemplateKey | null,
  deps: ClientDeps,
  personal?: PersonalForm,
): Promise<ZaloSendOutcome> {
  const now = deps.now ? deps.now() : Date.now();
  const key = ctx.dedupe_key ?? (ctx.message_id ? `msg:${ctx.message_id}` : null);

  if (key) {
    const existing = await findByKey(env, key);
    if (existing) return outcomeFromRow(existing);
  }

  const flags = await readSendFlags(env);
  if (!flags.outbound_enabled) {
    return { ok: false, unknown: false, error_code: 'outbound_disabled', error_message: 'outbound_enabled is false', outbox_id: '' };
  }

  const transport = transportFor(env, zaloUserId);
  if (transport === 'mismatch') {
    return { ok: false, unknown: false, error_code: 'channel_mismatch', error_message: 'ZALO_MODE=personal has no OA transport for this user', outbox_id: '' };
  }
  if (transport === 'personal') {
    if (!personal) throw new HttpError(409, 'invalid_state', 'this message type cannot be sent on the personal channel');
    return queuePersonal(env, kind, zaloUserId, personal.text, personal.extra, ctx, templateKey, key, now);
  }

  const mode = env.ZALO_MODE === 'real' ? 'real' : 'mock';
  const id = newId('obx', now);
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO outbox (id, kind, zalo_mode, conversation_id, customer_id, zalo_user_id, message_id, payload_json, status, created_at, dedupe_key, template_key)
     VALUES (?,?,?,?,?,?,?,?, 'pending', ?, ?, ?)`,
  )
    .bind(id, kind, mode, ctx.conversation_id, ctx.customer_id, zaloUserId, ctx.message_id, JSON.stringify(payload), now, key, templateKey)
    .run();
  if ((ins.meta.changes ?? 0) === 0 && key) {
    // A concurrent call with the same key won the insert.
    const existing = await findByKey(env, key);
    if (existing) return outcomeFromRow(existing);
  }

  if (mode === 'mock') {
    const zaloMsgId = `mock_${id}`;
    await finish(env, id, 'sent', zaloMsgId, null, now);
    return { ok: true, zalo_msg_id: zaloMsgId, outbox_id: id };
  }

  const f = deps.fetch ?? fetch;
  let token: string;
  try {
    token = await getAccessToken(env, now, deps);
  } catch (err) {
    // Nothing was sent to Zalo: an explicit, safe failure.
    const msg = err instanceof Error ? err.message : 'no access token';
    await finish(env, id, 'failed', null, `no_access_token: ${msg}`, now);
    return { ok: false, unknown: false, error_code: 'no_access_token', error_message: msg, outbox_id: id };
  }

  let call = await postJson(f, url, token, payload);
  if (call.kind === 'ok' && TOKEN_ERRORS.has(Number(call.json.error))) {
    const r = await refreshIfNeeded(env, now, { ...deps, force: true });
    if (r === 'refreshed') {
      try {
        call = await postJson(f, url, await getAccessToken(env, now, deps), payload);
      } catch {
        /* keep the first (explicit) error */
      }
    }
  }

  if (call.kind === 'unknown') {
    await finish(env, id, 'unknown', null, `${call.reason}: outcome unknown`, now);
    console.warn(JSON.stringify({ level: 'warn', at: 'zalo_client', outbox_id: id, result: 'unknown', reason: call.reason }));
    return { ok: false, unknown: true, error_code: call.reason, error_message: 'Zalo did not confirm the send', outbox_id: id };
  }
  const errCode = Number(call.json.error);
  if (errCode === 0) {
    const zaloMsgId = zaloMsgIdOf(call.json) ?? `unknown_id_${id}`;
    await finish(env, id, 'sent', zaloMsgId, null, now);
    return { ok: true, zalo_msg_id: zaloMsgId, outbox_id: id };
  }
  const code = Number.isFinite(errCode) ? `zalo_${errCode}` : 'zalo_error';
  const message = String(call.json.message ?? 'Zalo returned an error').slice(0, 200);
  await finish(env, id, 'failed', null, `${code}: ${message}`, now);
  return { ok: false, unknown: false, error_code: code, error_message: message, outbox_id: id };
}

// ---------------------------------------------------------------- public API

export async function sendText(env: Env, zaloUserId: string, text: string, ctx: SendContext, deps: ClientDeps = {}): Promise<ZaloSendOutcome> {
  if (!text || text.length > CS_TEXT_MAX) {
    throw new HttpError(422, 'validation_failed', `text must be 1..${CS_TEXT_MAX} chars`, { field: 'text' });
  }
  const payload = { recipient: { user_id: zaloUserId }, message: { text } };
  return send(env, 'cs_text', zaloUserId, CS_URL, payload, ctx, null, deps, { text, extra: {} });
}

/** Consultation message with up to 5 buttons (template_type 'request_user_info' is separate). */
export async function sendButtons(
  env: Env,
  zaloUserId: string,
  text: string,
  buttons: ZaloButton[],
  ctx: SendContext,
  deps: ClientDeps = {},
): Promise<ZaloSendOutcome> {
  if (!text || text.length > CS_TEXT_MAX) {
    throw new HttpError(422, 'validation_failed', `text must be 1..${CS_TEXT_MAX} chars`, { field: 'text' });
  }
  if (buttons.length < 1 || buttons.length > 5 || buttons.some((b) => !b.title || b.title.length > 100)) {
    throw new HttpError(422, 'validation_failed', 'buttons: 1..5, each title 1..100 chars', { field: 'buttons' });
  }
  const plainButtons = buttons.map((b) => ({ title: b.title, type: b.type, payload: b.payload }));
  const payload = {
    recipient: { user_id: zaloUserId },
    message: { text, attachment: { type: 'template', payload: { buttons: plainButtons } } },
  };
  const personalText = buttonsAsText(text, buttons);
  if (isPersonalUserId(zaloUserId) && personalText.length > CS_TEXT_MAX) {
    throw new HttpError(422, 'validation_failed', `text with button lines must be 1..${CS_TEXT_MAX} chars`, { field: 'text' });
  }
  return send(env, 'cs_buttons', zaloUserId, CS_URL, payload, ctx, null, deps, { text: personalText, extra: { rendered_from: 'buttons', buttons: plainButtons } });
}

/** Approved ZBS template ids from env ZALO_TEMPLATE_IDS (JSON). Mock mode falls back to 'mock_tpl_<key>'. */
export function templateIdFor(env: Env, key: TemplateKey): string | null {
  let map: Record<string, unknown> = {};
  try {
    map = env.ZALO_TEMPLATE_IDS ? (JSON.parse(env.ZALO_TEMPLATE_IDS) as Record<string, unknown>) : {};
  } catch {
    map = {};
  }
  const id = map[key];
  if (typeof id === 'string' && id) return id;
  if (typeof id === 'number') return String(id);
  return env.ZALO_MODE === 'real' ? null : `mock_tpl_${key}`;
}

/** Whether a template send to this recipient can work: personal channel needs a chat version, OA needs a template id. */
export function templateAvailable(env: Env, key: TemplateKey, zaloUserId: string): boolean {
  const t = transportFor(env, zaloUserId);
  if (t === 'personal') return hasChatTemplate(key);
  if (t === 'mismatch') return false;
  return templateIdFor(env, key) !== null;
}

/** ZBS template message via UID (thank_you / check_in / promo ...). No model involved: params are server data.
 *  Personal channel: the chat version of the template, filled with the same params, sent as plain text. */
export async function sendTemplate(
  env: Env,
  zaloUserId: string,
  templateKey: TemplateKey,
  params: Record<string, string>,
  ctx: SendContext,
  deps: ClientDeps = {},
): Promise<ZaloSendOutcome> {
  if (isPersonalUserId(zaloUserId)) {
    const text = renderChatTemplate(templateKey, params);
    if (!text) throw new HttpError(409, 'invalid_state', `no chat version of template '${templateKey}' for the personal channel`);
    if (text.length > CS_TEXT_MAX) throw new HttpError(422, 'validation_failed', `template text over ${CS_TEXT_MAX} chars`, { field: 'params' });
    const payload = { template_key: templateKey, template_data: params };
    return send(env, 'zbs_template', zaloUserId, TEMPLATE_UID_URL, payload, ctx, templateKey, deps, { text, extra: { rendered_from: 'template', template_key: templateKey, params } });
  }
  const templateId = templateIdFor(env, templateKey);
  if (!templateId) {
    throw new HttpError(409, 'invalid_state', `no approved ZBS template id for '${templateKey}' (ZALO_TEMPLATE_IDS)`);
  }
  const payload = { user_id: zaloUserId, template_id: templateId, template_data: params };
  return send(env, 'zbs_template', zaloUserId, TEMPLATE_UID_URL, payload, ctx, templateKey, deps);
}

export interface ZaloUserProfile {
  user_id: string;
  display_name: string | null;
  is_sensitive: boolean | null; // true = under 18 (minor_flag)
  user_is_follower: boolean | null;
  user_last_interaction_date: string | null; // dd/MM/yyyy as Zalo returns it
  shared_phone: string | null; // only what the customer shared with the OA
}

export type ProfileResult = { ok: true; profile: ZaloUserProfile } | { ok: false; error_code: string; error_message: string };

/** Read-only profile lookup (no outbox row). Mock mode returns a fixed fake profile. A personal thread has no
 *  profile API (the display name comes with each webhook event, the age is never known). */
export async function getUserProfile(env: Env, zaloUserId: string, deps: ClientDeps = {}): Promise<ProfileResult> {
  if (isPersonalUserId(zaloUserId)) return { ok: false, error_code: 'not_supported', error_message: 'personal channel has no profile API' };
  if (env.ZALO_MODE !== 'real') {
    return {
      ok: true,
      profile: {
        user_id: zaloUserId,
        display_name: `Khách ${zaloUserId.slice(-4)}`,
        is_sensitive: false,
        user_is_follower: true,
        user_last_interaction_date: null,
        shared_phone: null,
      },
    };
  }
  const now = deps.now ? deps.now() : Date.now();
  const f = deps.fetch ?? fetch;
  let token: string;
  try {
    token = await getAccessToken(env, now, deps);
  } catch (err) {
    return { ok: false, error_code: 'no_access_token', error_message: err instanceof Error ? err.message : 'no token' };
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);
  try {
    const url = `${USER_DETAIL_URL}?data=${encodeURIComponent(JSON.stringify({ user_id: zaloUserId }))}`;
    const res = await f(url, { method: 'GET', headers: { access_token: token }, signal: ctrl.signal });
    const json = (await res.json()) as Record<string, unknown>;
    if (Number(json.error) !== 0) {
      return { ok: false, error_code: `zalo_${String(json.error)}`, error_message: String(json.message ?? '').slice(0, 200) };
    }
    const d = (json.data ?? {}) as Record<string, unknown>;
    const shared = (d.shared_info ?? {}) as Record<string, unknown>;
    return {
      ok: true,
      profile: {
        user_id: String(d.user_id ?? zaloUserId),
        display_name: typeof d.display_name === 'string' ? d.display_name : null,
        is_sensitive: typeof d.is_sensitive === 'boolean' ? d.is_sensitive : null,
        user_is_follower: typeof d.user_is_follower === 'boolean' ? d.user_is_follower : null,
        user_last_interaction_date: typeof d.user_last_interaction_date === 'string' ? d.user_last_interaction_date : null,
        shared_phone: typeof shared.phone === 'string' && shared.phone ? shared.phone : null,
      },
    };
  } catch (err) {
    return { ok: false, error_code: 'network_error', error_message: err instanceof Error ? err.name : 'error' };
  } finally {
    clearTimeout(timer);
  }
}
