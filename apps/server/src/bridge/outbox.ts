// Owner: personal channel. State machine of personal-channel outbox rows (docs/contracts.md "Personal Zalo channel").
//
//   queued --claim--> leased --result sent-------------------------------------> sent
//                       |    --result failed, attempts < MAX_SEND_ATTEMPTS -----> queued (next_attempt_at = backoff)
//                       |    --result failed, attempts = MAX_SEND_ATTEMPTS -----> failed  (final)
//                       |    --result unknown ----------------------------------> unknown (final, never retried)
//                       '-- lease_until passed: claimable again while attempts < MAX_SEND_ATTEMPTS, else unknown
//
// A delivery is a fact: a 'sent' result, or a self-sent webhook event that matches the row (echo), moves the row
// to 'sent' from any state. A late 'failed'/'unknown' never downgrades a 'sent' row.
// Claims keep per-thread order: a row is not handed out while an older row of the same thread is queued or leased.
// The linked messages row (outbox.message_id) follows the final state: sent / failed / unknown.
//
// Before handing out a row, claim also settles queued rows that must not go out any more (both become 'failed', so
// the console shows them and staff can requeue one):
//   - an automatic bot reply of a conversation that is no longer bot_active (takeover, handoff, staff_only, blocked):
//     error 'cancelled: conversation is <state>';
//   - an automatic row (bot reply or server fixed message) queued longer than PERSONAL_QUEUE_MAX_AGE_MS (Mac asleep,
//     bridge stopped, outbound_enabled off for a while): error 'expired_in_queue';
//   - a bot or server row for a contact whose role is manager or staff (docs/contracts.md section 14.3): error
//     'cancelled: internal contact'. This one raises nothing for staff (no needs_attention).
// Send limits for the personal account: at most PERSONAL_SEND_MAX_PER_HOUR automatic rows per rolling hour (rows typed
// or approved by staff are not held back, but they count), and PERSONAL_THREAD_MIN_GAP_MS between two claims to the
// same thread.
//
// Menu images (kind 'cs_images', migration 0009): one row carries 1..MAX_MENU_IMAGES menu image keys (image_keys), sent
// by the bridge with `zalo-agent msg send-image`. Only a bridge that claims with capabilities ['images'] gets such a
// row. The row of an approved draft depends on the draft's text row (depends_on): it is handed out only once the text
// is 'sent', and it is cancelled ('failed', staff can requeue) when the text row ends 'failed' or 'unknown'. Its lease
// grows with the number of images. One image row counts as one send for the hourly limit. Its echo is one self-sent
// photo event per image: matched by msgId (zalo_msg_id / part_msg_ids), or, while the row has no msgIds yet or the
// event has none, by time (claimed within IMAGE_ECHO_WINDOW_MS, at most one event per image: echo_count).
import type { BridgeOutboxItem, BridgeResultRequest, BridgeResultResponse, Env, OutboxStatus } from '../types';
import { auditStatement } from '../lib/audit';
import { HttpError } from '../lib/http';
import { newId } from '../lib/ids';
import { echoText, threadIdOf } from '../lib/zalo-personal';
import { MAX_MENU_IMAGES, menuImagesLabel, parseKeys, uniqueKeys } from '../lib/menu-images';
import { INTERNAL_ROLES, orMissing0010 } from '../lib/roles';

/** A non-negative integer env value; "0" is allowed (disables the limit), anything unreadable is the default. */
function envNonNeg(value: string | undefined, fallback: number): number {
  if (value === undefined || value.trim() === '') return fallback;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback;
}

/** An automatic row (bot reply or server fixed message) queued longer than this is not sent. 0 = no limit. */
export const queueMaxAgeMs = (env: Env) => envNonNeg(env.PERSONAL_QUEUE_MAX_AGE_MS, 30 * 60_000);
/** Automatic rows claimed per rolling hour. 0 = no limit. */
export const sendMaxPerHour = (env: Env) => envNonNeg(env.PERSONAL_SEND_MAX_PER_HOUR, 30);
/** Minimum time between two claims to the same thread. 0 = no gap. */
export const threadMinGapMs = (env: Env) => envNonNeg(env.PERSONAL_THREAD_MIN_GAP_MS, 5_000);
const HOUR_MS = 3600_000;

/** SQL (outbox aliased o): the row's message was typed or approved by staff, so send limits do not hold it back. */
const STAFF_ROW_SQL = "EXISTS (SELECT 1 FROM messages m WHERE m.id = o.message_id AND (m.source = 'staff' OR m.staff_id IS NOT NULL))";

export const BRIDGE_LEASE_MS = 60_000;
/** First try plus at most 3 retries after explicit failures. */
export const MAX_SEND_ATTEMPTS = 4;
/** Wait before retry n (n = attempts already made, 1-based). */
export const RETRY_BACKOFF_MS = [15_000, 60_000, 240_000];
/** A split row already matched by one echo still matches further parts by text for this long after its claim. */
export const ECHO_WINDOW_MS = 10 * 60_000;
/**
 * A self-sent message whose text equals a row not matched by any echo yet, claimed within this window, is the
 * bridge's own send coming back. The engine can hold an echo in its webhook outbox (Mac asleep, server down) and
 * deliver it much later, with or without catchUp, so the window is not 10 minutes.
 */
export const UNMATCHED_ECHO_WINDOW_MS = 24 * 3600_000;
/** `zalo-agent msg send` splits a text above ~3000 UTF-8 bytes into parts; each part comes back as its own echo. */
const SPLIT_BYTES = 2900;
/** A self-sent photo without a usable msgId is the bridge's own image send when it comes this soon after the claim. */
export const IMAGE_ECHO_WINDOW_MS = 3 * 60_000;
/** Lease of a cs_images row: the text lease plus this much per image (uploads take longer), at most IMAGE_LEASE_MAX_MS. */
export const IMAGE_LEASE_PER_IMAGE_MS = 20_000;
export const IMAGE_LEASE_MAX_MS = 300_000;

export interface PersonalOutboxRow {
  id: string;
  kind: 'cs_text' | 'cs_buttons' | 'zbs_template' | 'cs_images';
  conversation_id: string | null;
  customer_id: string | null;
  zalo_user_id: string;
  thread_id: string;
  text: string;
  message_id: string | null;
  status: OutboxStatus;
  zalo_msg_id: string | null;
  error: string | null;
  attempts: number;
  next_attempt_at: number | null;
  lease_owner: string | null;
  lease_until: number | null;
  last_claimed_at: number | null;
  echo_msg_id: string | null;
  dedupe_key: string | null;
  created_at: number;
  requeued_at: number | null;
  part_msg_ids: string | null; // JSON array of the parts' msgIds (split send), migration 0006
  image_keys: string | null; // cs_images: JSON array of menu image keys, migration 0009
  depends_on: string | null; // cs_images: outbox id of the draft's text row, migration 0009
  echo_count: number; // self-sent webhook events matched to this row, migration 0009
}

const ROW_COLS =
  'id, kind, conversation_id, customer_id, zalo_user_id, thread_id, text, message_id, status, zalo_msg_id, error, attempts, next_attempt_at, lease_owner, lease_until, last_claimed_at, echo_msg_id, dedupe_key, created_at, requeued_at, part_msg_ids, image_keys, depends_on, echo_count';

export async function getPersonalRow(env: Env, id: string): Promise<PersonalOutboxRow | null> {
  return env.DB.prepare(`SELECT ${ROW_COLS} FROM outbox WHERE id = ? AND channel = 'personal'`).bind(id).first<PersonalOutboxRow>();
}

function backoffFor(attempts: number): number {
  return RETRY_BACKOFF_MS[Math.min(Math.max(attempts, 1), RETRY_BACKOFF_MS.length) - 1]!;
}

function toItem(r: PersonalOutboxRow): BridgeOutboxItem {
  return {
    id: r.id,
    thread_id: r.thread_id,
    thread_type: 0,
    text: r.text,
    kind: r.kind,
    ...(r.kind === 'cs_images' ? { images: parseKeys(r.image_keys) } : {}),
    attempt: r.attempts,
    lease_until: r.lease_until ?? 0,
    conversation_id: r.conversation_id,
    message_id: r.message_id,
    requeued_at: r.requeued_at ?? null,
  };
}

/** Claim lease of a row: 60 s for text; for menu images 60 s + 20 s per image, at most 5 minutes. */
export function leaseMsFor(kind: string, imageKeys: string | null): number {
  if (kind !== 'cs_images') return BRIDGE_LEASE_MS;
  return Math.min(BRIDGE_LEASE_MS + IMAGE_LEASE_PER_IMAGE_MS * Math.max(1, parseKeys(imageKeys).length), IMAGE_LEASE_MAX_MS);
}

// ---------------------------------------------------------------- final state of the linked message / draft / job

type FinalState = 'sent' | 'failed' | 'unknown';

/**
 * Mirrors a final outbox state onto the messages row it belongs to (and the draft / follow-up job behind it).
 * messages.zalo_msg_id is UNIQUE: the id is only written when no other message holds it.
 */
async function applyToMessage(env: Env, row: PersonalOutboxRow, state: FinalState, zaloMsgId: string | null, error: string | null, now: number, quiet = false): Promise<void> {
  const db = env.DB;
  const stmts: D1PreparedStatement[] = [];
  if (row.message_id) {
    if (state === 'sent') {
      stmts.push(
        db.prepare(
          `UPDATE messages SET send_state = 'sent', send_error = NULL, sent_at = COALESCE(sent_at, ?),
             zalo_msg_id = CASE WHEN ? IS NOT NULL AND zalo_msg_id IS NULL AND NOT EXISTS (SELECT 1 FROM messages m2 WHERE m2.zalo_msg_id = ?) THEN ? ELSE zalo_msg_id END
           WHERE id = ?`,
        ).bind(now, zaloMsgId, zaloMsgId, zaloMsgId, row.message_id),
        db.prepare("UPDATE drafts SET status = 'sent' WHERE sent_message_id = ? AND status IN ('send_failed','approved')").bind(row.message_id),
      );
    } else {
      stmts.push(
        db.prepare('UPDATE messages SET send_state = ?, send_error = ? WHERE id = ? AND send_state != \'sent\'').bind(state, (error ?? state).slice(0, 500), row.message_id),
        db.prepare('UPDATE drafts SET status = ? WHERE sent_message_id = ? AND status = \'sent\'').bind(state === 'failed' ? 'send_failed' : 'approved', row.message_id),
      );
    }
  }
  // quiet: the row was cancelled for an internal contact (section 14.3), which never raises needs_attention.
  if (row.conversation_id && state !== 'sent' && !quiet) {
    stmts.push(db.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, row.conversation_id));
  }
  // Follow-up jobs (dedupe_key 'job:<id>') were marked 'done' when the row was queued.
  if (row.dedupe_key?.startsWith('job:')) {
    const jobId = row.dedupe_key.slice(4);
    if (state === 'sent') {
      stmts.push(db.prepare("UPDATE jobs SET status = 'done', last_error = NULL, updated_at = ? WHERE id = ? AND status IN ('failed','needs_staff')").bind(now, jobId));
    } else {
      stmts.push(
        db.prepare("UPDATE jobs SET status = ?, last_error = ?, updated_at = ? WHERE id = ? AND status = 'done'").bind(
          state === 'failed' ? 'failed' : 'needs_staff',
          `bridge_${state}:${(error ?? '').slice(0, 150)}`,
          now,
          jobId,
        ),
      );
    }
  }
  if (stmts.length) await db.batch(stmts);
}

// ---------------------------------------------------------------- claim

/** Expired leases that used every attempt: the outcome of the last claim is unknown, so staff decides. */
async function expireExhaustedLeases(env: Env, now: number): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT ${ROW_COLS} FROM outbox WHERE channel = 'personal' AND status = 'leased' AND lease_until < ? AND attempts >= ? LIMIT 20`,
  )
    .bind(now, MAX_SEND_ATTEMPTS)
    .all<PersonalOutboxRow>();
  for (const row of results ?? []) {
    const upd = await env.DB.prepare(
      "UPDATE outbox SET status = 'unknown', error = 'lease_expired_without_result', lease_until = NULL, updated_at = ? WHERE id = ? AND status = 'leased' AND lease_until < ?",
    )
      .bind(now, row.id, now)
      .run();
    if ((upd.meta.changes ?? 0) > 0) await applyToMessage(env, row, 'unknown', null, 'lease_expired_without_result', now);
  }
}

/**
 * Moves queued rows to 'failed' with this error, and mirrors that onto their message / draft / conversation.
 * quiet = true leaves needs_attention of the conversation alone.
 */
async function failQueuedRows(env: Env, rows: PersonalOutboxRow[], error: string, now: number, quiet = false): Promise<number> {
  let n = 0;
  for (const row of rows) {
    const upd = await env.DB.prepare(
      "UPDATE outbox SET status = 'failed', error = ?, next_attempt_at = NULL, lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ? AND status = 'queued'",
    )
      .bind(error.slice(0, 300), now, row.id)
      .run();
    if ((upd.meta.changes ?? 0) === 0) continue;
    n++;
    await applyToMessage(env, row, 'failed', null, error, now, quiet);
    await auditStatement(env, { actor_type: 'system', actor_id: 'bridge_claim', action: 'outbox.cancelled', entity: 'outbox', entity_id: row.id, after: { error: error.slice(0, 80) } }, now).run();
  }
  return n;
}

/**
 * Queued automatic bot replies of conversations that are no longer bot_active (staff took over on the console or on
 * the phone, the customer asked for staff, a handoff, staff_only, blocked) are not sent: the row becomes 'failed'
 * with error 'cancelled: conversation is <state>'. Staff messages, staff-approved drafts and server fixed messages
 * stay queued. conversationId = null checks every conversation (claim); a value checks that one (DO state changes).
 */
export async function cancelQueuedBotRows(
  env: Env,
  conversationId: string | null,
  now: number,
  opts: { alsoServer?: boolean; reason?: string } = {},
): Promise<number> {
  // alsoServer (staff marked the contact staff_only): a waiting consent prompt or other server message goes too.
  const which = opts.alsoServer ? "((m.source = 'bot' AND m.staff_id IS NULL) OR m.source = 'server')" : "m.source = 'bot' AND m.staff_id IS NULL";
  const { results } = await env.DB.prepare(
    `SELECT ${ROW_COLS.split(', ').map((c) => `o.${c}`).join(', ')}, c.bot_state AS bot_state FROM outbox o
       JOIN messages m ON m.id = o.message_id
       JOIN conversations c ON c.id = o.conversation_id
     WHERE o.channel = 'personal' AND o.status = 'queued' AND ${which}
       AND c.bot_state != 'bot_active' ${conversationId ? 'AND o.conversation_id = ?' : ''}
     LIMIT 50`,
  )
    .bind(...(conversationId ? [conversationId] : []))
    .all<PersonalOutboxRow & { bot_state: string }>();
  let n = 0;
  for (const r of results ?? []) n += await failQueuedRows(env, [r], opts.reason ?? `cancelled: conversation is ${r.bot_state}`, now);
  return n;
}

export const INTERNAL_CONTACT_CANCEL_ERROR = 'cancelled: internal contact';

/**
 * Queued rows for a contact whose role is manager or staff (docs/contracts.md section 14.3) are not sent, whatever the
 * bot_state: a bot reply, a draft approved before the role was set and a server message (consent prompt, fixed text,
 * follow-up) become 'failed' with error 'cancelled: internal contact'. Unlike the other cancels this raises nothing for
 * staff (needs_attention is left alone). A message typed by staff stays queued, and so does a row that staff requeued
 * on the console. conversationId = null checks every conversation (claim); a value checks that one (message ingest).
 * Returns 0 when migration 0010 is not applied.
 */
export async function cancelQueuedInternalRows(env: Env, conversationId: string | null, now: number): Promise<number> {
  const rows = await orMissing0010(
    env.DB.prepare(
      `SELECT ${ROW_COLS.split(', ').map((c) => `o.${c}`).join(', ')} FROM outbox o
         JOIN contact_roles r ON r.zalo_user_id = o.zalo_user_id
         LEFT JOIN messages m ON m.id = o.message_id
       WHERE o.channel = 'personal' AND o.status = 'queued' AND o.requeued_at IS NULL
         AND r.role IN (${INTERNAL_ROLES.map((x) => `'${x}'`).join(',')})
         AND (m.id IS NULL OR m.source IN ('bot','server')) ${conversationId ? 'AND o.conversation_id = ?' : ''}
       LIMIT 50`,
    )
      .bind(...(conversationId ? [conversationId] : []))
      .all<PersonalOutboxRow>()
      .then((r) => r.results ?? []),
    [] as PersonalOutboxRow[],
  );
  return rows.length ? failQueuedRows(env, rows, INTERNAL_CONTACT_CANCEL_ERROR, now, true) : 0;
}

/** Automatic rows (bot reply or server fixed message) queued longer than PERSONAL_QUEUE_MAX_AGE_MS: staff decides. */
async function expireStaleQueued(env: Env, now: number): Promise<void> {
  const maxAge = queueMaxAgeMs(env);
  if (maxAge <= 0) return;
  const { results } = await env.DB.prepare(
    `SELECT ${ROW_COLS.split(', ').map((c) => `o.${c}`).join(', ')} FROM outbox o JOIN messages m ON m.id = o.message_id
     WHERE o.channel = 'personal' AND o.status = 'queued' AND o.kind IN ('cs_text','cs_buttons')
       AND m.source IN ('bot','server') AND m.staff_id IS NULL AND COALESCE(o.requeued_at, o.created_at) < ?
     LIMIT 50`,
  )
    .bind(now - maxAge)
    .all<PersonalOutboxRow>();
  if (results?.length) {
    await failQueuedRows(env, results, `expired_in_queue: queued more than ${Math.round(maxAge / 60_000)} min; not sent, staff decides`, now);
  }
}

/**
 * Image rows of a draft whose text row ended 'failed' or 'unknown' are not sent: the pictures would arrive without the
 * reply they belong to. The row becomes 'failed' ('cancelled: text row not sent'), so staff can requeue it.
 */
async function cancelOrphanImageRows(env: Env, now: number): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT ${ROW_COLS.split(', ').map((c) => `o.${c}`).join(', ')}, d.status AS dep_status FROM outbox o JOIN outbox d ON d.id = o.depends_on
     WHERE o.channel = 'personal' AND o.status = 'queued' AND o.depends_on IS NOT NULL AND d.status IN ('failed','unknown') LIMIT 50`,
  ).all<PersonalOutboxRow & { dep_status: string }>();
  for (const r of results ?? []) await failQueuedRows(env, [r], `cancelled: text row not sent (${r.dep_status}); staff decides`, now);
}

export interface ClaimOutcome {
  item: BridgeOutboxItem | null;
  /** Set when due rows wait only because of the hourly limit: the time a claim slot frees up. */
  rate_limited_until?: number;
}

export interface ClaimOptions {
  /** The bridge sends menu images (claim body capabilities includes 'images'); otherwise cs_images rows are not offered. */
  images?: boolean;
}

/**
 * Leases the oldest claimable row for this bridge. Claimable: 'queued' and due, or 'leased' with an expired lease and
 * attempts left; no older row of the same thread still queued or leased; no claim to the same thread within
 * PERSONAL_THREAD_MIN_GAP_MS; and, for automatic rows, fewer than PERSONAL_SEND_MAX_PER_HOUR claims in the last hour.
 */
export async function claimNext(env: Env, bridgeId: string, now: number, opts: ClaimOptions = {}): Promise<ClaimOutcome> {
  await expireExhaustedLeases(env, now);
  await cancelQueuedBotRows(env, null, now);
  await cancelQueuedInternalRows(env, null, now);
  await expireStaleQueued(env, now);
  await cancelOrphanImageRows(env, now);
  const claimable = `channel = 'personal' AND (
      (status = 'queued' AND COALESCE(next_attempt_at, 0) <= ?1)
      OR (status = 'leased' AND lease_until < ?1 AND attempts < ?2))`;
  const cap = sendMaxPerHour(env);
  const gap = threadMinGapMs(env);
  let capReached = false;
  let oldestInWindow: number | null = null;
  if (cap > 0) {
    const w = await env.DB.prepare("SELECT COUNT(*) AS n, MIN(last_claimed_at) AS t FROM outbox WHERE channel = 'personal' AND last_claimed_at >= ?")
      .bind(now - HOUR_MS)
      .first<{ n: number; t: number | null }>();
    capReached = (w?.n ?? 0) >= cap;
    oldestInWindow = w?.t ?? null;
  }
  const { results } = await env.DB.prepare(
    `SELECT id, kind, image_keys FROM outbox o WHERE ${claimable}
       AND NOT EXISTS (SELECT 1 FROM outbox p WHERE p.channel = 'personal' AND p.thread_id = o.thread_id AND p.status IN ('queued','leased')
                       AND (p.created_at < o.created_at OR (p.created_at = o.created_at AND p.id < o.id)))
       AND (?3 = 0 OR NOT EXISTS (SELECT 1 FROM outbox g WHERE g.channel = 'personal' AND g.thread_id = o.thread_id AND g.id != o.id AND g.last_claimed_at > ?4))
       AND (?5 = 0 OR ${STAFF_ROW_SQL})
       AND (o.kind != 'cs_images' OR ?6 = 1)
       AND (o.depends_on IS NULL OR EXISTS (SELECT 1 FROM outbox d WHERE d.id = o.depends_on AND d.status = 'sent'))
     ORDER BY created_at ASC, id ASC LIMIT 5`,
  )
    .bind(now, MAX_SEND_ATTEMPTS, gap, now - gap, capReached ? 1 : 0, opts.images ? 1 : 0)
    .all<{ id: string; kind: string; image_keys: string | null }>();
  for (const { id, kind, image_keys } of results ?? []) {
    const upd = await env.DB.prepare(
      `UPDATE outbox SET status = 'leased', lease_owner = ?3, lease_until = ?4, attempts = attempts + 1, last_claimed_at = ?1, updated_at = ?1
       WHERE id = ?5 AND ${claimable}`,
    )
      .bind(now, MAX_SEND_ATTEMPTS, bridgeId, now + leaseMsFor(kind, image_keys), id)
      .run();
    if ((upd.meta.changes ?? 0) === 0) continue; // another claim won
    const row = await getPersonalRow(env, id);
    if (row) return { item: toItem(row) };
  }
  if (capReached) {
    const due = await env.DB.prepare(`SELECT 1 AS x FROM outbox WHERE ${claimable} LIMIT 1`).bind(now, MAX_SEND_ATTEMPTS).first<{ x: number }>();
    if (due) return { item: null, rate_limited_until: (oldestInWindow ?? now) + HOUR_MS };
  }
  return { item: null };
}

// ---------------------------------------------------------------- result

async function markSent(env: Env, row: PersonalOutboxRow, zaloMsgId: string | null, now: number, echoMsgId: string | null = null, partIds: string[] | null = null): Promise<boolean> {
  const upd = await env.DB.prepare(
    `UPDATE outbox SET status = 'sent', zalo_msg_id = COALESCE(zalo_msg_id, ?), echo_msg_id = COALESCE(echo_msg_id, ?), error = NULL,
       part_msg_ids = COALESCE(part_msg_ids, ?), sent_at = COALESCE(sent_at, ?), lease_until = NULL, next_attempt_at = NULL, updated_at = ?
     WHERE id = ? AND status != 'sent'`,
  )
    .bind(zaloMsgId, echoMsgId, partIds && partIds.length ? JSON.stringify(partIds) : null, now, now, row.id)
    .run();
  const changed = (upd.meta.changes ?? 0) > 0;
  if (changed) await applyToMessage(env, row, 'sent', zaloMsgId ?? echoMsgId, null, now);
  return changed;
}

function response(row: PersonalOutboxRow, ignored: boolean): BridgeResultResponse {
  return { id: row.id, status: row.status, attempts: row.attempts, next_attempt_at: row.status === 'queued' ? row.next_attempt_at : null, ignored };
}

/** POST /bridge/outbox/:id/result. Throws HttpError 404 / 409 (see docs/contracts.md). */
export async function applyResult(env: Env, id: string, bridgeId: string, body: BridgeResultRequest, now: number): Promise<BridgeResultResponse> {
  const row = await getPersonalRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'outbox item not found');
  const zaloMsgId = body.zalo_msg_id ?? null;
  const partIds = body.part_msg_ids && body.part_msg_ids.length ? body.part_msg_ids : null;
  const error = body.error ? body.error.slice(0, 300) : null;

  if (body.status === 'sent') {
    if (row.status === 'sent') {
      if (zaloMsgId && !row.zalo_msg_id) {
        await env.DB.prepare('UPDATE outbox SET zalo_msg_id = ?, updated_at = ? WHERE id = ? AND zalo_msg_id IS NULL').bind(zaloMsgId, now, row.id).run();
        await applyToMessage(env, row, 'sent', zaloMsgId, null, now);
      }
      if (partIds && !row.part_msg_ids) {
        await env.DB.prepare('UPDATE outbox SET part_msg_ids = ?, updated_at = ? WHERE id = ? AND part_msg_ids IS NULL').bind(JSON.stringify(partIds), now, row.id).run();
      }
      return response((await getPersonalRow(env, id))!, true);
    }
    await markSent(env, row, zaloMsgId, now, null, partIds);
    if (row.status === 'failed' || row.status === 'unknown') {
      await auditStatement(env, { actor_type: 'system', actor_id: `bridge:${bridgeId}`, action: 'outbox.late_sent', entity: 'outbox', entity_id: row.id, before: { status: row.status } }, now).run();
    }
    return response((await getPersonalRow(env, id))!, false);
  }

  // failed / unknown
  if (row.status === 'sent') return response(row, true); // delivery already proven (earlier result or echo)
  if (row.status === 'failed' || row.status === 'unknown') {
    if (row.status === body.status) return response(row, true); // repeated report
    throw new HttpError(409, 'invalid_state', `outbox item is already ${row.status}`);
  }
  if (row.status !== 'leased') throw new HttpError(409, 'lease_expired', `outbox item is ${row.status}; claim it again`);
  if (row.lease_owner !== bridgeId) throw new HttpError(409, 'lease_not_owned', 'outbox item is leased by another bridge');
  if (body.attempt !== undefined && body.attempt !== row.attempts) {
    throw new HttpError(409, 'lease_expired', `result for attempt ${body.attempt}, item is on attempt ${row.attempts}`);
  }

  if (body.status === 'unknown') {
    const upd = await env.DB.prepare(
      "UPDATE outbox SET status = 'unknown', error = ?, lease_until = NULL, updated_at = ? WHERE id = ? AND status = 'leased' AND attempts = ?",
    )
      .bind(error ?? 'bridge_unknown', now, row.id, row.attempts)
      .run();
    if ((upd.meta.changes ?? 0) > 0) {
      await applyToMessage(env, row, 'unknown', null, `bridge_unknown: ${error ?? ''}`, now);
      await auditStatement(env, { actor_type: 'system', actor_id: `bridge:${bridgeId}`, action: 'outbox.unknown', entity: 'outbox', entity_id: row.id, after: { attempts: row.attempts } }, now).run();
    }
    return response((await getPersonalRow(env, id))!, false);
  }

  // failed: retry with backoff while attempts are left, else final
  if (row.attempts < MAX_SEND_ATTEMPTS) {
    const next = now + backoffFor(row.attempts);
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE outbox SET status = 'queued', error = ?, next_attempt_at = ?, lease_until = NULL, lease_owner = NULL, updated_at = ? WHERE id = ? AND status = 'leased' AND attempts = ?",
      ).bind(error ?? 'bridge_failed', next, now, row.id, row.attempts),
      ...(row.message_id
        ? [env.DB.prepare("UPDATE messages SET send_error = ? WHERE id = ? AND send_state = 'pending'").bind(`retrying after: ${error ?? 'failed'}`.slice(0, 500), row.message_id)]
        : []),
    ]);
    return response((await getPersonalRow(env, id))!, false);
  }
  const upd = await env.DB.prepare(
    "UPDATE outbox SET status = 'failed', error = ?, lease_until = NULL, updated_at = ? WHERE id = ? AND status = 'leased' AND attempts = ?",
  )
    .bind(error ?? 'bridge_failed', now, row.id, row.attempts)
    .run();
  if ((upd.meta.changes ?? 0) > 0) {
    await applyToMessage(env, row, 'failed', null, `bridge_failed: ${error ?? ''}`, now);
    await auditStatement(env, { actor_type: 'system', actor_id: `bridge:${bridgeId}`, action: 'outbox.failed', entity: 'outbox', entity_id: row.id, after: { attempts: row.attempts } }, now).run();
  }
  return response((await getPersonalRow(env, id))!, false);
}

// ---------------------------------------------------------------- echo of the bridge's own sends

function utf8Bytes(s: string): number {
  return new TextEncoder().encode(s).length;
}

/**
 * Finds the outbox row a self-sent message came from: the same msgId as the row's send, echo or one of its parts (any
 * age); or the same thread and the same text as a row not matched by an echo yet, claimed within
 * UNMATCHED_ECHO_WINDOW_MS. A long row (split by `msg send`) also matches an echo that is one part of its text.
 * A self-sent photo (opts.photo) that matches no msgId is the echo of a menu image row of the same thread claimed
 * within IMAGE_ECHO_WINDOW_MS, when that row has no msgIds yet (the bridge has not reported) or the event carries no
 * msgId, and the row has had fewer photo echoes than images. Returns null when the message was typed (or the photo
 * sent) by a person on the phone. `catchUp` no longer changes the window.
 */
export async function findEchoRow(
  env: Env,
  threadId: string,
  msgId: string | null,
  text: string | null,
  _catchUp: boolean,
  now: number,
  opts: { photo?: boolean } = {},
): Promise<PersonalOutboxRow | null> {
  if (msgId) {
    const byId = await env.DB.prepare(
      `SELECT ${ROW_COLS} FROM outbox WHERE channel = 'personal' AND thread_id = ?1 AND (zalo_msg_id = ?2 OR echo_msg_id = ?2
         OR (part_msg_ids IS NOT NULL AND EXISTS (SELECT 1 FROM json_each(outbox.part_msg_ids) j WHERE j.value = ?2))) LIMIT 1`,
    )
      .bind(threadId, msgId)
      .first<PersonalOutboxRow>();
    if (byId) return byId;
  }
  if (opts.photo) {
    const byTime = await env.DB.prepare(
      `SELECT ${ROW_COLS} FROM outbox WHERE channel = 'personal' AND thread_id = ?1 AND kind = 'cs_images' AND last_claimed_at >= ?2
         AND echo_count < json_array_length(COALESCE(image_keys, '[]'))
         AND (?3 IS NULL OR (zalo_msg_id IS NULL AND part_msg_ids IS NULL))
       ORDER BY last_claimed_at DESC LIMIT 1`,
    )
      .bind(threadId, now - IMAGE_ECHO_WINDOW_MS, msgId)
      .first<PersonalOutboxRow>();
    return byTime ?? null;
  }
  const want = echoText(text);
  if (!want) return null;
  const { results } = await env.DB.prepare(
    `SELECT ${ROW_COLS} FROM outbox WHERE channel = 'personal' AND thread_id = ? AND kind != 'cs_images' AND last_claimed_at >= ? ORDER BY last_claimed_at ASC LIMIT 50`,
  )
    .bind(threadId, now - UNMATCHED_ECHO_WINDOW_MS)
    .all<PersonalOutboxRow>();
  const rows = results ?? [];
  const exact = rows.find((r) => r.echo_msg_id === null && echoText(r.text) === want);
  if (exact) return exact;
  return (
    rows.find(
      (r) =>
        utf8Bytes(r.text) > SPLIT_BYTES &&
        (r.echo_msg_id === null || (r.last_claimed_at ?? 0) >= now - ECHO_WINDOW_MS) &&
        want.length >= 20 &&
        echoText(r.text).includes(want),
    ) ?? null
  );
}

/** The echo proves delivery: the row becomes 'sent' (if it was not) and remembers the echo's msgId; echo_count + 1. */
export async function confirmByEcho(env: Env, row: PersonalOutboxRow, msgId: string | null, now: number): Promise<void> {
  await env.DB.prepare('UPDATE outbox SET echo_count = echo_count + 1, echo_msg_id = COALESCE(echo_msg_id, ?), updated_at = ? WHERE id = ?')
    .bind(row.status === 'sent' ? msgId : null, now, row.id)
    .run();
  if (row.status === 'sent') return;
  await markSent(env, row, null, now, msgId);
}

// ---------------------------------------------------------------- staff decision on failed / unknown rows

export async function decideOutbox(env: Env, id: string, staffId: string, action: 'requeue' | 'mark_sent' | 'mark_failed', note: string | null, now: number): Promise<BridgeResultResponse> {
  const row = await getPersonalRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'personal outbox item not found');
  if (row.status !== 'failed' && row.status !== 'unknown') {
    throw new HttpError(409, 'invalid_state', `only failed or unknown items need a decision; this one is ${row.status}`);
  }
  if (action === 'requeue') {
    await env.DB.batch([
      // depends_on is cleared: staff decided to send these images even though the draft's text row was not sent.
      env.DB.prepare(
        "UPDATE outbox SET status = 'queued', attempts = 0, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, error = NULL, requeued_at = ?, depends_on = NULL, updated_at = ? WHERE id = ? AND status IN ('failed','unknown')",
      ).bind(now, now, now, row.id),
      ...(row.message_id ? [env.DB.prepare("UPDATE messages SET send_state = 'pending', send_error = NULL WHERE id = ? AND send_state IN ('failed','unknown')").bind(row.message_id)] : []),
    ]);
  } else if (action === 'mark_sent') {
    await markSent(env, row, null, now);
  } else {
    const upd = await env.DB.prepare("UPDATE outbox SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND status = 'unknown'")
      .bind(`staff: ${note ?? 'marked failed'}`.slice(0, 300), now, row.id)
      .run();
    if ((upd.meta.changes ?? 0) > 0) await applyToMessage(env, row, 'failed', null, 'marked failed by staff', now);
  }
  await auditStatement(env, { actor_type: 'staff', actor_id: staffId, action: `outbox.${action}`, entity: 'outbox', entity_id: row.id, before: { status: row.status }, after: { note } }, now).run();
  return response((await getPersonalRow(env, id))!, false);
}

// ---------------------------------------------------------------- menu images (kind 'cs_images')

export interface QueueImagesArgs {
  conversation_id: string;
  customer_id: string;
  zalo_user_id: string; // 'p:' + threadId
  message_id: string; // messages row (kind 'image') written by the caller with send_state 'pending'
  keys: string[];
  depends_on: string | null; // outbox id of the draft's text row
  dedupe_key: string; // 'img:' + draft id
  draft_id: string | null;
}

/**
 * Queues one cs_images row for a personal customer. Keys are re-validated against data/menu-images.json (unknown keys
 * are dropped; none left, or more than MAX_MENU_IMAGES, is refused). created_at is after the text row's, so the
 * per-thread order sends the text first even when both are queued in the same millisecond.
 */
export async function queuePersonalImages(env: Env, a: QueueImagesArgs, now: number): Promise<{ outbox_id: string; keys: string[] }> {
  const threadId = threadIdOf(a.zalo_user_id);
  if (!threadId) throw new HttpError(409, 'invalid_state', 'menu images are sent on the personal channel only');
  const keys = uniqueKeys(a.keys);
  if (!keys.length || keys.length > MAX_MENU_IMAGES) throw new HttpError(422, 'validation_failed', `1..${MAX_MENU_IMAGES} known menu image keys required`, { field: 'attachments' });
  const dep = a.depends_on ? await env.DB.prepare('SELECT created_at FROM outbox WHERE id = ?').bind(a.depends_on).first<{ created_at: number }>() : null;
  const createdAt = Math.max(now, (dep?.created_at ?? 0) + 1);
  const id = newId('obx', createdAt);
  const label = menuImagesLabel(keys);
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO outbox (id, kind, zalo_mode, channel, conversation_id, customer_id, zalo_user_id, thread_id, text, message_id, payload_json, status,
       attempts, next_attempt_at, created_at, updated_at, dedupe_key, image_keys, depends_on)
     VALUES (?, 'cs_images', 'personal', 'personal', ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      id,
      a.conversation_id,
      a.customer_id,
      a.zalo_user_id,
      threadId,
      label,
      a.message_id,
      JSON.stringify({ thread_id: threadId, images: keys, draft_id: a.draft_id }),
      createdAt,
      createdAt,
      now,
      a.dedupe_key,
      JSON.stringify(keys),
      a.depends_on,
    )
    .run();
  if ((ins.meta.changes ?? 0) === 0) {
    const existing = await env.DB.prepare('SELECT id, image_keys FROM outbox WHERE dedupe_key = ?').bind(a.dedupe_key).first<{ id: string; image_keys: string | null }>();
    if (existing) return { outbox_id: existing.id, keys: parseKeys(existing.image_keys) };
  }
  return { outbox_id: id, keys };
}
