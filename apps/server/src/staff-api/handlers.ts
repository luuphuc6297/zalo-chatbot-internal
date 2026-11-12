// Owner: server-core. Staff API (docs/contracts.md "Staff API"). Auth by requireStaff (Bearer STAFF_TOKEN).
import type { Context } from 'hono';
import type {
  AppEnv,
  BookingRequestView,
  BookingStatusRequest,
  BotState,
  CheckerResult,
  ConsentView,
  ContactRoleRow,
  ConversationDetail,
  ConversationMode,
  ConversationSummary,
  DraftView,
  Env,
  Flags,
  HandoffView,
  ListResponse,
  MessageView,
  OutboxItem,
  RunnerErrorKind,
  StaffRunnerResponse,
} from '../types';
import { MODE_ORDER } from '../types';
import { HttpError, readJson, rpc } from '../lib/http';
import { conversationMode, getFlags, getFlagsWithMeta, putFlags, validateFlag } from '../lib/flags';
import { conversationStub } from '../lib/do';
import { consentStatus, mustConversation, refreshNeedsAttention, safeJson } from '../lib/db';
import { auditStatement } from '../lib/audit';
import { envInt } from '../lib/time';
import { recordVisit } from '../jobs/followup-jobs';
import { runnerOfflineMs } from '../jobs/draft-jobs';
import { getProfileView } from '../lib/profiles';
import { conversationIsInternal, getContactRole, getContactRoles, isMissingMigration0010, orConflict0010 } from '../lib/roles';
import { buildCustomerSummary } from '../lib/customer-summary';
import { roomPendingCount } from '../lib/rooms';
import { parseKeys } from '../lib/menu-images';

type H = (c: Context<AppEnv>) => Promise<Response>;

const staffId = (c: Context<AppEnv>) => c.get('staffId') ?? 'staff';

// ---------------------------------------------------------------- pagination

function page(c: Context<AppEnv>): { limit: number; offset: number } {
  const limit = Math.min(Math.max(Number(c.req.query('limit') ?? 50) || 50, 1), 200);
  const cur = c.req.query('cursor');
  let offset = 0;
  if (cur) {
    try {
      offset = Math.max(0, Number(JSON.parse(atob(cur)).o) || 0);
    } catch {
      throw new HttpError(400, 'bad_request', 'bad cursor');
    }
  }
  return { limit, offset };
}

function listOf<T>(rows: T[], limit: number, offset: number): ListResponse<T> {
  const more = rows.length > limit;
  return { items: rows.slice(0, limit), next_cursor: more ? btoa(JSON.stringify({ o: offset + limit })) : null };
}

// ---------------------------------------------------------------- views

interface ConvJoinRow {
  id: string;
  customer_id: string;
  bot_state: BotState;
  mode: ConversationMode | null;
  needs_attention: number;
  takeover_by: string | null;
  takeover_until: number | null;
  last_message_at: number | null;
  session_id: string | null;
  session_turns: number;
  catalog_version: string | null;
  zalo_user_id: string;
  channel: 'oa' | 'personal';
  display_name: string | null;
  phone: string | null;
  minor_flag: number | null;
  last_user_interaction_at: number | null;
  pending_drafts: number;
  open_handoffs: number;
  last_preview: string | null;
  // migration 0010 (docs/contracts.md section 14); undefined on a database without it
  auto_reply?: 'on' | 'off' | null;
  room_channel_id?: string | null;
  room_synced_at?: number | null;
}

const CONV_SELECT =
  'SELECT c.id, c.customer_id, c.bot_state, c.mode, c.needs_attention, c.takeover_by, c.takeover_until, c.last_message_at, c.session_id, c.session_turns, c.catalog_version, ' +
  'cu.zalo_user_id, cu.channel, cu.display_name, cu.phone, cu.minor_flag, cu.last_user_interaction_at, ' +
  "(SELECT COUNT(*) FROM drafts d WHERE d.conversation_id = c.id AND d.status IN ('pending','blocked')) AS pending_drafts, " +
  "(SELECT COUNT(*) FROM handoffs h WHERE h.conversation_id = c.id AND h.status = 'open') AS open_handoffs, " +
  '(SELECT m.text FROM messages m WHERE m.conversation_id = c.id AND m.text IS NOT NULL ORDER BY m.seq DESC LIMIT 1) AS last_preview ' +
  'FROM conversations c JOIN customers cu ON cu.id = c.customer_id';
/** CONV_SELECT plus the conversation columns of migration 0010. */
const CONV_SELECT_0010 = CONV_SELECT.replace('SELECT c.id, ', 'SELECT c.auto_reply, c.room_channel_id, c.room_synced_at, c.id, ');

/**
 * Runs a conversation query with the columns of migration 0010 (auto reply switch, room), and again without them
 * when the database does not have them yet, so the staff views keep working before the migration.
 */
async function withConvSelect<T>(run: (select: string) => Promise<T>): Promise<T> {
  try {
    return await run(CONV_SELECT_0010);
  } catch (e) {
    if (!isMissingMigration0010(e)) throw e;
    return run(CONV_SELECT);
  }
}

/** `role` is the contact_roles row of the contact (null or undefined: no role); role, role_source and auto_reply are emitted only when set. */
function summary(r: ConvJoinRow, flags: Flags, role?: ContactRoleRow | null): ConversationSummary {
  return {
    id: r.id,
    customer: {
      id: r.customer_id,
      channel: r.channel,
      zalo_user_id: r.zalo_user_id,
      display_name: r.display_name,
      phone: r.phone,
      minor_flag: r.minor_flag === null ? null : r.minor_flag === 1,
      last_user_interaction_at: r.last_user_interaction_at,
    },
    bot_state: r.bot_state,
    mode_override: r.mode,
    effective_mode: conversationMode(flags, r),
    needs_attention: !!r.needs_attention,
    takeover_by: r.takeover_by,
    takeover_until: r.takeover_until,
    last_message_at: r.last_message_at,
    last_message_preview: r.last_preview ? r.last_preview.slice(0, 120) : null,
    pending_drafts: r.pending_drafts,
    open_handoffs: r.open_handoffs,
    ...(role ? { role: role.role, role_source: role.source } : {}),
    ...(r.auto_reply === 'on' || r.auto_reply === 'off' ? { auto_reply: r.auto_reply } : {}),
  };
}

async function convSummary(env: Env, id: string): Promise<ConversationSummary> {
  const r = await withConvSelect((select) => env.DB.prepare(`${select} WHERE c.id = ?`).bind(id).first<ConvJoinRow>());
  if (!r) throw new HttpError(404, 'not_found', 'conversation not found');
  return summary(r, await getFlags(env), await getContactRole(env, r.zalo_user_id));
}

interface MessageRowV {
  id: string;
  direction: 'inbound' | 'outbound';
  source: 'customer' | 'bot' | 'staff' | 'server';
  kind: string;
  text: string | null;
  attachments_json: string | null;
  send_state: MessageView['send_state'];
  draft_id: string | null;
  staff_id: string | null;
  created_at: number;
  sent_at: number | null;
}
const messageView = (m: MessageRowV): MessageView => ({
  id: m.id,
  direction: m.direction,
  source: m.source,
  kind: m.kind,
  text: m.text,
  attachments: safeJson(m.attachments_json, []),
  send_state: m.send_state,
  draft_id: m.draft_id,
  staff_id: m.staff_id,
  created_at: m.created_at,
  sent_at: m.sent_at,
});

async function messageById(env: Env, id: string): Promise<MessageView> {
  const m = await env.DB.prepare('SELECT * FROM messages WHERE id = ?').bind(id).first<MessageRowV>();
  if (!m) throw new HttpError(404, 'not_found', 'message not found');
  return messageView(m);
}

interface DraftRowV {
  id: string;
  job_id: string;
  conversation_id: string;
  text: string;
  final_text: string | null;
  status: DraftView['status'];
  checker_result_json: string;
  account_label: string | null;
  cost_usd_equiv: number | null;
  catalog_version: string | null;
  created_at: number;
  decided_by: string | null;
  decided_at: number | null;
  attachments_json?: string | null; // migration 0009; undefined before it
}
const draftView = (d: DraftRowV): DraftView => ({
  id: d.id,
  job_id: d.job_id,
  conversation_id: d.conversation_id,
  text: d.text,
  final_text: d.final_text,
  status: d.status,
  checker: safeJson<CheckerResult>(d.checker_result_json, { passed: false, issues: [], checked_at: 0 }),
  account_label: d.account_label,
  cost_usd_equiv: d.cost_usd_equiv,
  catalog_version: d.catalog_version,
  created_at: d.created_at,
  decided_by: d.decided_by,
  decided_at: d.decided_at,
  // menu images the model attached (known keys only); the console lists them and staff may drop some before approving
  attachments: parseKeys(d.attachments_json),
});

async function draftById(env: Env, id: string): Promise<DraftView> {
  const d = await env.DB.prepare('SELECT * FROM drafts WHERE id = ?').bind(id).first<DraftRowV>();
  if (!d) throw new HttpError(404, 'not_found', 'draft not found');
  return draftView(d);
}

const HANDOFF_SELECT =
  'SELECT h.*, cu.display_name AS customer_display_name FROM handoffs h JOIN customers cu ON cu.id = h.customer_id';
const handoffView = (h: Record<string, unknown>): HandoffView => ({
  id: h.id as string,
  conversation_id: h.conversation_id as string,
  customer_display_name: (h.customer_display_name as string | null) ?? null,
  source: h.source as HandoffView['source'],
  reason_code: h.reason_code as HandoffView['reason_code'],
  urgency: h.urgency as HandoffView['urgency'],
  summary_for_staff: (h.summary_for_staff as string | null) ?? null,
  status: h.status as HandoffView['status'],
  created_at: h.created_at as number,
  resolved_by: (h.resolved_by as string | null) ?? null,
  resolved_at: (h.resolved_at as number | null) ?? null,
});

const BOOKING_SELECT =
  'SELECT b.*, cu.display_name AS customer_display_name FROM booking_requests b JOIN customers cu ON cu.id = b.customer_id';
const bookingView = (b: Record<string, unknown>): BookingRequestView => ({
  id: b.id as string,
  conversation_id: b.conversation_id as string,
  customer_display_name: (b.customer_display_name as string | null) ?? null,
  service_ids: safeJson<string[]>(b.service_ids_json as string, []),
  duration_min: b.duration_min as number,
  preferred_date_local: b.preferred_date_local as string,
  preferred_time_window: b.preferred_time_window as string,
  party_size: b.party_size as number,
  customer_name: b.customer_name as string,
  contact_method: b.contact_method as BookingRequestView['contact_method'],
  phone: (b.phone as string | null) ?? null,
  notes_for_staff: (b.notes_for_staff as string | null) ?? null,
  price_quoted_text: (b.price_quoted_text as string | null) ?? null,
  status: b.status as BookingRequestView['status'],
  staff_note: (b.staff_note as string | null) ?? null,
  created_at: b.created_at as number,
  updated_at: b.updated_at as number,
});

// ---------------------------------------------------------------- conversations

export const listConversations: H = async (c) => {
  const { limit, offset } = page(c);
  const where: string[] = [];
  const binds: unknown[] = [];
  const state = c.req.query('state');
  if (state) {
    where.push('c.bot_state = ?');
    binds.push(state);
  }
  const na = c.req.query('needs_attention');
  if (na === 'true' || na === 'false') {
    where.push('c.needs_attention = ?');
    binds.push(na === 'true' ? 1 : 0);
  }
  const tail = `${where.length ? ` WHERE ${where.join(' AND ')}` : ''} ORDER BY c.last_message_at DESC, c.id DESC LIMIT ? OFFSET ?`;
  const { results } = await withConvSelect((select) => c.env.DB.prepare(`${select}${tail}`).bind(...binds, limit + 1, offset).all<ConvJoinRow>());
  const flags = await getFlags(c.env);
  const roles = await getContactRoles(c.env, results.map((r) => r.zalo_user_id));
  return c.json(listOf(results.map((r) => summary(r, flags, roles.get(r.zalo_user_id))), limit, offset));
};

export const getConversation: H = async (c) => {
  const id = c.req.param('id')!;
  const db = c.env.DB;
  const r = await withConvSelect((select) => db.prepare(`${select} WHERE c.id = ?`).bind(id).first<ConvJoinRow>());
  if (!r) throw new HttpError(404, 'not_found', 'conversation not found');
  const flags = await getFlags(c.env);
  const now = Date.now();
  const [msgs, open, decided, hofs, brqs] = await db.batch([
    db.prepare('SELECT * FROM (SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq DESC LIMIT 200) ORDER BY seq ASC').bind(id),
    db.prepare("SELECT * FROM drafts WHERE conversation_id = ? AND status IN ('pending','blocked') ORDER BY created_at").bind(id),
    db.prepare("SELECT * FROM drafts WHERE conversation_id = ? AND status NOT IN ('pending','blocked') ORDER BY created_at DESC LIMIT 20").bind(id),
    db.prepare(`${HANDOFF_SELECT} WHERE h.conversation_id = ? ORDER BY h.created_at DESC LIMIT 50`).bind(id),
    db.prepare(`${BOOKING_SELECT} WHERE b.conversation_id = ? ORDER BY b.created_at DESC LIMIT 50`).bind(id),
  ]);
  const cs = await consentStatus(c.env, r.customer_id);
  const consents: ConsentView[] = (['ai_assistant', 'followup_care', 'promotions', 'health_data'] as const).map((p) => ({
    purpose: p,
    status: cs[p]?.status ?? 'none',
    recorded_at: cs[p]?.recorded_at ?? null,
  }));
  // null before migration 0010 and for a deleted customer: the field is then left out
  const customerSummary = await buildCustomerSummary(c.env, r.customer_id, now);
  const detail: ConversationDetail = {
    conversation: {
      ...summary(r, flags, await getContactRole(c.env, r.zalo_user_id)),
      session_id: r.session_id,
      session_turns: r.session_turns,
      catalog_version: r.catalog_version,
    },
    messages: (msgs!.results as unknown as MessageRowV[]).map(messageView),
    drafts: [...(open!.results as unknown as DraftRowV[]), ...(decided!.results as unknown as DraftRowV[])].map(draftView),
    handoffs: (hofs!.results as Record<string, unknown>[]).map(handoffView),
    booking_requests: (brqs!.results as Record<string, unknown>[]).map(bookingView),
    consents,
    profile: await getProfileView(c.env, r.zalo_user_id),
    ...(customerSummary ? { customer_summary: customerSummary } : {}),
    ...(r.room_channel_id
      ? { room: { channel_id: r.room_channel_id, synced_at: r.room_synced_at ?? null, pending: await roomPendingCount(c.env, id, now) } }
      : {}),
  };
  return c.json(detail);
};

export const takeover: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ until?: unknown }>(c).catch(() => ({}) as { until?: unknown });
  const now = Date.now();
  let until = now + envInt(c.env.TAKEOVER_DEFAULT_MS, 43_200_000);
  if (b.until !== undefined) {
    if (typeof b.until !== 'number' || b.until <= now) throw new HttpError(422, 'validation_failed', 'until must be a future ms timestamp', { field: 'until' });
    until = b.until;
  }
  await mustConversation(c.env, id);
  await rpc((await conversationStub(c.env, id)).takeover(staffId(c), until, id));
  return c.json({ conversation: await convSummary(c.env, id) });
};

export const release: H = async (c) => {
  const id = c.req.param('id')!;
  await mustConversation(c.env, id);
  await rpc((await conversationStub(c.env, id)).release(staffId(c), id));
  return c.json({ conversation: await convSummary(c.env, id) });
};

/** POST /staff/conversations/:id/staff-only: not a customer / staff handles it; bot_state staff_only, no handoff. */
export const markStaffOnly: H = async (c) => {
  const id = c.req.param('id')!;
  await mustConversation(c.env, id);
  await rpc((await conversationStub(c.env, id)).markStaffOnly(staffId(c), id));
  return c.json({ conversation: await convSummary(c.env, id) });
};

export const setMode: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ mode?: unknown }>(c);
  if (!b || !('mode' in b) || (b.mode !== null && !(MODE_ORDER as unknown[]).includes(b.mode))) {
    throw new HttpError(422, 'validation_failed', 'mode must be null or one of off, draft_only, approve_each, auto_allowed', { field: 'mode' });
  }
  const conv = await mustConversation(c.env, id);
  const now = Date.now();
  const stmts = [
    c.env.DB.prepare('UPDATE conversations SET mode = ?, updated_at = ? WHERE id = ?').bind(b.mode, now, id),
    auditStatement(c.env, { actor_type: 'staff', actor_id: staffId(c), action: 'conversation.mode', entity: 'conversation', entity_id: id, before: conv.mode, after: b.mode }, now),
  ];
  // Section 14.4: a mode below auto_allowed on a conversation whose auto reply switch is on turns the switch off,
  // otherwise the switch would keep sending without approval. conv.auto_reply is 'on' only after migration 0010.
  if (conv.auto_reply === 'on' && b.mode !== null && b.mode !== 'auto_allowed') {
    stmts.push(
      c.env.DB.prepare("UPDATE conversations SET auto_reply = 'off' WHERE id = ?").bind(id),
      auditStatement(
        c.env,
        { actor_type: 'staff', actor_id: staffId(c), action: 'conversation.auto_reply', entity: 'conversation', entity_id: id, before: { auto_reply: 'on' }, after: { auto_reply: 'off', by: 'mode' } },
        now,
      ),
    );
  }
  if (b.mode === 'off') {
    stmts.push(
      c.env.DB.prepare("UPDATE jobs SET status = 'cancelled', last_error = 'mode_off', updated_at = ? WHERE conversation_id = ? AND type = 'draft_reply' AND status = 'queued'").bind(now, id),
    );
  }
  await c.env.DB.batch(stmts);
  return c.json({ conversation: await convSummary(c.env, id) });
};

/**
 * PUT /staff/conversations/:id/auto-reply (docs/contracts.md section 14.4): the per-conversation switch of the
 * automatic reply. `on` also clears the mode override, so the conversation is auto_allowed unless the global flag
 * auto_reply_mode is off; `off` keeps the mode override and caps the conversation at approve_each. 422 for another
 * value, 409 invalid_state for `on` on an internal contact (the bot never replies to it) and before migration 0010.
 */
export const setAutoReply: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ auto_reply?: unknown }>(c);
  if (!b || (b.auto_reply !== 'on' && b.auto_reply !== 'off')) {
    throw new HttpError(422, 'validation_failed', "auto_reply must be 'on' or 'off'", { field: 'auto_reply' });
  }
  const conv = await mustConversation(c.env, id);
  if (b.auto_reply === 'on' && (await conversationIsInternal(c.env, id))) {
    throw new HttpError(409, 'invalid_state', 'the contact is a manager or a staff member: the bot does not reply to it');
  }
  const now = Date.now();
  const mode = b.auto_reply === 'on' ? null : conv.mode;
  await orConflict0010(
    c.env.DB.batch([
      b.auto_reply === 'on'
        ? c.env.DB.prepare("UPDATE conversations SET auto_reply = 'on', mode = NULL, updated_at = ? WHERE id = ?").bind(now, id)
        : c.env.DB.prepare("UPDATE conversations SET auto_reply = 'off', updated_at = ? WHERE id = ?").bind(now, id),
      auditStatement(
        c.env,
        {
          actor_type: 'staff',
          actor_id: staffId(c),
          action: 'conversation.auto_reply',
          entity: 'conversation',
          entity_id: id,
          before: { auto_reply: conv.auto_reply ?? null, mode: conv.mode },
          after: { auto_reply: b.auto_reply, mode },
        },
        now,
      ),
    ]),
  );
  return c.json({ conversation: await convSummary(c.env, id) });
};

export const manualSend: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ text?: unknown; from_draft_id?: unknown; keep_bot_active?: unknown }>(c);
  if (typeof b?.text !== 'string') throw new HttpError(422, 'validation_failed', 'text required', { field: 'text' });
  if (b.from_draft_id !== undefined && typeof b.from_draft_id !== 'string') throw new HttpError(422, 'validation_failed', 'bad from_draft_id', { field: 'from_draft_id' });
  await mustConversation(c.env, id);
  const stub = await conversationStub(c.env, id);
  const r = await rpc(
    stub.sendStaffText({
      text: b.text,
      staffId: staffId(c),
      ...(typeof b.from_draft_id === 'string' ? { draftId: b.from_draft_id } : {}),
      keepBotActive: b.keep_bot_active === true,
      conversationId: id,
    }),
  );
  await refreshNeedsAttention(c.env, id, Date.now());
  return c.json({ message: await messageById(c.env, r.message_id), outbox_id: r.outbox_id });
};

// ---------------------------------------------------------------- drafts

export const approveDraft: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ text?: unknown; override_checker?: unknown; attachments?: unknown }>(c).catch(
    () => ({}) as { text?: unknown; override_checker?: unknown; attachments?: unknown },
  );
  if (b.text !== undefined && typeof b.text !== 'string') throw new HttpError(422, 'validation_failed', 'bad text', { field: 'text' });
  // attachments: the menu images staff keep (a subset of the draft's keys; [] sends the text only)
  if (b.attachments !== undefined && (!Array.isArray(b.attachments) || b.attachments.some((k) => typeof k !== 'string') || b.attachments.length > 20)) {
    throw new HttpError(422, 'validation_failed', 'attachments must be an array of menu image keys', { field: 'attachments' });
  }
  const d = await c.env.DB.prepare('SELECT conversation_id FROM drafts WHERE id = ?').bind(id).first<{ conversation_id: string }>();
  if (!d) throw new HttpError(404, 'not_found', 'draft not found');
  const stub = await conversationStub(c.env, d.conversation_id);
  const r = await rpc(
    stub.approveDraft(id, staffId(c), {
      ...(typeof b.text === 'string' ? { text: b.text } : {}),
      override_checker: b.override_checker === true,
      ...(Array.isArray(b.attachments) ? { attachments: b.attachments as string[] } : {}),
    }),
  );
  await refreshNeedsAttention(c.env, d.conversation_id, Date.now());
  return c.json({ draft: await draftById(c.env, id), message: await messageById(c.env, r.message_id) });
};

export const rejectDraft: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<{ reason?: unknown }>(c).catch(() => ({}) as { reason?: unknown });
  const now = Date.now();
  const r = await c.env.DB.prepare(
    "UPDATE drafts SET status = 'rejected', reject_reason = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status IN ('pending','blocked')",
  )
    .bind(typeof b.reason === 'string' ? b.reason.slice(0, 500) : null, staffId(c), now, id)
    .run();
  if (!r.meta.changes) {
    await draftById(c.env, id); // 404 when missing
    throw new HttpError(409, 'invalid_state', 'draft is not pending or blocked');
  }
  await auditStatement(c.env, { actor_type: 'staff', actor_id: staffId(c), action: 'draft.reject', entity: 'draft', entity_id: id }, now).run();
  const rd = await c.env.DB.prepare('SELECT conversation_id FROM drafts WHERE id = ?').bind(id).first<{ conversation_id: string }>();
  if (rd) await refreshNeedsAttention(c.env, rd.conversation_id, now);
  return c.json({ draft: await draftById(c.env, id) });
};

// ---------------------------------------------------------------- flags

export const getFlagsHandler: H = async (c) => c.json(await getFlagsWithMeta(c.env));

export const putFlagsHandler: H = async (c) => c.json(await putFlags(c.env, await readJson(c), staffId(c)));

// ---------------------------------------------------------------- handoffs and booking requests

export const listHandoffs: H = async (c) => {
  const { limit, offset } = page(c);
  const status = c.req.query('status') ?? 'open';
  if (status !== 'open' && status !== 'resolved') throw new HttpError(422, 'validation_failed', 'status must be open or resolved', { field: 'status' });
  const order = status === 'open' ? "CASE h.urgency WHEN 'urgent' THEN 0 ELSE 1 END, h.created_at ASC" : 'h.resolved_at DESC';
  const { results } = await c.env.DB.prepare(`${HANDOFF_SELECT} WHERE h.status = ? ORDER BY ${order} LIMIT ? OFFSET ?`)
    .bind(status, limit + 1, offset)
    .all<Record<string, unknown>>();
  return c.json(listOf(results.map(handoffView), limit, offset));
};

export const resolveHandoff: H = async (c) => {
  const id = c.req.param('id')!;
  const now = Date.now();
  const r = await c.env.DB.prepare("UPDATE handoffs SET status = 'resolved', resolved_by = ?, resolved_at = ? WHERE id = ? AND status = 'open'")
    .bind(staffId(c), now, id)
    .run();
  const row = await c.env.DB.prepare(`${HANDOFF_SELECT} WHERE h.id = ?`).bind(id).first<Record<string, unknown>>();
  if (!row) throw new HttpError(404, 'not_found', 'handoff not found');
  if (!r.meta.changes) throw new HttpError(409, 'invalid_state', 'handoff already resolved');
  await auditStatement(c.env, { actor_type: 'staff', actor_id: staffId(c), action: 'handoff.resolve', entity: 'handoff', entity_id: id }, now).run();
  await refreshNeedsAttention(c.env, row.conversation_id as string, now);
  return c.json({ handoff: handoffView(row) });
};

const BOOKING_STATUSES = ['new', 'proposed', 'confirmed', 'cancelled', 'expired'];

export const listBookingRequests: H = async (c) => {
  const { limit, offset } = page(c);
  const status = c.req.query('status') ?? 'new';
  if (!BOOKING_STATUSES.includes(status)) throw new HttpError(422, 'validation_failed', 'bad status', { field: 'status' });
  const { results } = await c.env.DB.prepare(`${BOOKING_SELECT} WHERE b.status = ? ORDER BY b.created_at ASC LIMIT ? OFFSET ?`)
    .bind(status, limit + 1, offset)
    .all<Record<string, unknown>>();
  return c.json(listOf(results.map(bookingView), limit, offset));
};

export const setBookingStatus: H = async (c) => {
  const id = c.req.param('id')!;
  const b = await readJson<Partial<BookingStatusRequest>>(c);
  if (!b || !['proposed', 'confirmed', 'cancelled', 'expired'].includes(b.status as string)) {
    throw new HttpError(422, 'validation_failed', 'status must be proposed, confirmed, cancelled or expired', { field: 'status' });
  }
  if (b.staff_note !== undefined && typeof b.staff_note !== 'string') throw new HttpError(422, 'validation_failed', 'bad staff_note', { field: 'staff_note' });
  const now = Date.now();
  const prev = await c.env.DB.prepare('SELECT status FROM booking_requests WHERE id = ?').bind(id).first<{ status: string }>();
  if (!prev) throw new HttpError(404, 'not_found', 'booking request not found');
  await c.env.DB.batch([
    c.env.DB.prepare('UPDATE booking_requests SET status = ?, staff_note = COALESCE(?, staff_note), handled_by = ?, updated_at = ? WHERE id = ?')
      .bind(b.status, b.staff_note?.slice(0, 1000) ?? null, staffId(c), now, id),
    auditStatement(c.env, { actor_type: 'staff', actor_id: staffId(c), action: 'booking_request.status', entity: 'booking_request', entity_id: id, before: prev.status, after: b.status }, now),
  ]);
  const row = await c.env.DB.prepare(`${BOOKING_SELECT} WHERE b.id = ?`).bind(id).first<Record<string, unknown>>();
  return c.json({ booking_request: bookingView(row!) });
};

export const createVisit: H = async (c) => c.json(await recordVisit(c.env, await readJson(c), staffId(c)));

// ---------------------------------------------------------------- runner and outbox

export const getRunner: H = async (c) => {
  const now = Date.now();
  const offline = runnerOfflineMs(c.env);
  const [runners, queue] = await c.env.DB.batch([
    c.env.DB.prepare('SELECT * FROM runner_status ORDER BY last_seen_at DESC'),
    c.env.DB.prepare("SELECT status, COUNT(*) AS n FROM jobs WHERE type = 'draft_reply' AND status IN ('queued','leased') GROUP BY status"),
  ]);
  const flags = await getFlags(c.env);
  const counts = Object.fromEntries((queue!.results as Array<{ status: string; n: number }>).map((r) => [r.status, r.n]));
  const res: StaffRunnerResponse = {
    runners: (runners!.results as Array<Record<string, unknown>>).map((r) => ({
      runner_id: r.runner_id as string,
      online: now - (r.last_seen_at as number) <= offline,
      last_seen_at: r.last_seen_at as number,
      last_claim_at: (r.last_claim_at as number | null) ?? null,
      status: safeJson(r.snapshot_json as string | null, null),
      last_error: r.last_error_kind
        ? { kind: r.last_error_kind as RunnerErrorKind, at: r.last_error_at as number, account_label: (r.last_error_account as string | null) ?? null }
        : null,
    })),
    desired_account: flags.runner_desired_account,
    queue: { queued: counts.queued ?? 0, leased: counts.leased ?? 0 },
  };
  return c.json(res);
};

export const putRunnerAccount: H = async (c) => {
  const b = await readJson<{ label?: unknown }>(c);
  if (validateFlag('runner_desired_account', b?.label) === undefined) {
    throw new HttpError(422, 'validation_failed', "label must be 'auto' or an account label", { field: 'label' });
  }
  const r = await putFlags(c.env, { runner_desired_account: b.label as string }, staffId(c));
  return c.json({ desired_account: r.flags.runner_desired_account });
};

export const listOutbox: H = async (c) => {
  const { limit, offset } = page(c);
  const { results } = await c.env.DB.prepare('SELECT * FROM outbox ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?')
    .bind(limit + 1, offset)
    .all<Record<string, unknown>>();
  const items: OutboxItem[] = results.map((o) => ({
    id: o.id as string,
    kind: o.kind as OutboxItem['kind'],
    zalo_mode: o.zalo_mode as OutboxItem['zalo_mode'],
    conversation_id: (o.conversation_id as string | null) ?? null,
    zalo_user_id: o.zalo_user_id as string,
    message_id: (o.message_id as string | null) ?? null,
    payload: safeJson(o.payload_json as string, null),
    status: o.status as OutboxItem['status'],
    zalo_msg_id: (o.zalo_msg_id as string | null) ?? null,
    error: (o.error as string | null) ?? null,
    created_at: o.created_at as number,
    sent_at: (o.sent_at as number | null) ?? null,
    ...(o.channel === 'personal'
      ? {
          channel: 'personal' as const,
          thread_id: (o.thread_id as string | null) ?? null,
          text: (o.text as string | null) ?? null,
          attempts: (o.attempts as number) ?? 0,
          next_attempt_at: (o.next_attempt_at as number | null) ?? null,
          lease_until: (o.lease_until as number | null) ?? null,
        }
      : {}),
  }));
  return c.json(listOf(items, limit, offset));
};
