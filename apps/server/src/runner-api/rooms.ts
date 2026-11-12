// Owner: server-core. Rooms feed of the runner API (docs/contracts.md section 14.7). Auth by requireRunner
// (Bearer RUNNER_TOKEN + X-Runner-Id). The runner mirrors customer conversations into staff rooms: it reads the rows
// that are waiting with POST /runner/rooms/feed and reports what it copied with POST /runner/rooms/ack.
//
// The feed never carries a phone number: a conversation is { conversation_id, customer_display_name, messages }.
import type { Context } from 'hono';
import type { AppEnv, Env, Flags, Ms, RoomsAckResponse, RoomsFeedConversation, RoomsFeedMessage, RoomsFeedResponse } from '../types';
import { HttpError, readJson } from '../lib/http';
import { getFlags } from '../lib/flags';
import { getConversation, getCustomer, mustConversation } from '../lib/db';
import { isMissingMigration0010, orConflict0010 } from '../lib/roles';
import { ROOM_ELIGIBLE_SQL, ROOM_MESSAGE_COLS, ROOM_PENDING_SQL, ROOM_ROW_SQL, roomOldestAllowed } from '../lib/rooms';
import { draftBlocker } from '../jobs/draft-jobs';
import { oneLine } from '../lib/text';

type H = (c: Context<AppEnv>) => Promise<Response>;

export const ROOM_OBSERVE_DEFAULT = 5; // conversations of the observation list
export const ROOM_OBSERVE_MAX = 20;
export const ROOM_OBSERVE_ROWS = 50; // rows per conversation of the observation list
export const ROOM_TURN_ROWS = 100; // rows of one draft turn
export const ROOM_SEED_ROWS = 20; // rows that open a new room
export const ROOM_ACK_MAX_IDS = 200;
export const ROOM_CHANNEL_ID_MAX_CHARS = 200;

// The observation list looks at the conversations with pending rows oldest first, in pages, and stops after
// SCAN_MAX of them, so one call stays bounded however many conversations wait for their own draft turn.
const SCAN_CHUNK = 40;
const SCAN_MAX = 200;
const IN_CHUNK = 90; // D1 allows 100 bound parameters per statement

const bad = (field: string, message = `invalid ${field}`) => new HttpError(422, 'validation_failed', message, { field });
const OFF: RoomsFeedResponse = { enabled: false, conversations: [] };

const ROWS_FROM = 'FROM messages m JOIN conversations c ON c.id = m.conversation_id';

/** The display name as the claim's turn context carries it: one line, at most 40 characters; null when there is none. */
const displayName = (name: string | null): string | null => oneLine(name, 40) || null;

// ---------------------------------------------------------------- feed

interface FeedInput {
  conversationId: string | null;
  seed: boolean;
  limit: number;
}

/** null and an absent field mean "not given". */
function parseFeed(b: unknown): FeedInput {
  if (b === null || typeof b !== 'object' || Array.isArray(b)) throw bad('$', 'body must be an object');
  const d = b as Record<string, unknown>;
  const id = d.conversation_id ?? null;
  if (id !== null && (typeof id !== 'string' || !id || id.length > 100)) throw bad('conversation_id');
  const seed = d.seed ?? false;
  if (typeof seed !== 'boolean') throw bad('seed');
  if (seed && id === null) throw bad('seed', 'seed needs conversation_id');
  const limit = d.limit ?? ROOM_OBSERVE_DEFAULT;
  if (typeof limit !== 'number' || !Number.isInteger(limit) || limit < 1) throw bad('limit', 'limit must be an integer of 1 or more');
  return { conversationId: id, seed, limit: Math.min(limit, ROOM_OBSERVE_MAX) };
}

/** The pending rows of one conversation, oldest first. */
async function pendingRows(env: Env, conversationId: string, now: Ms, limit: number): Promise<RoomsFeedMessage[]> {
  const { results } = await env.DB.prepare(`SELECT ${ROOM_MESSAGE_COLS} ${ROWS_FROM} WHERE m.conversation_id = ? AND ${ROOM_PENDING_SQL} ORDER BY m.seq ASC LIMIT ?`)
    .bind(conversationId, roomOldestAllowed(now), limit)
    .all<RoomsFeedMessage>();
  return results;
}

/** The last rows of one conversation that meet the row rule, mirrored or not, oldest first (context for a new room). */
async function seedRows(env: Env, conversationId: string, now: Ms): Promise<RoomsFeedMessage[]> {
  const { results } = await env.DB.prepare(`SELECT ${ROOM_MESSAGE_COLS} ${ROWS_FROM} WHERE m.conversation_id = ? AND ${ROOM_ROW_SQL} ORDER BY m.seq DESC LIMIT ?`)
    .bind(conversationId, roomOldestAllowed(now), ROOM_SEED_ROWS)
    .all<RoomsFeedMessage>();
  return results.reverse();
}

/** true when a draft turn can run for this conversation: the turn itself delivers the pending customer rows. */
async function draftWillRun(env: Env, conversationId: string, flags: Flags): Promise<boolean> {
  const conv = await getConversation(env, conversationId);
  const customer = conv ? await getCustomer(env, conv.customer_id) : null;
  if (!conv || !customer) return false;
  return (await draftBlocker(env, conv, customer, flags)) === null;
}

interface Candidate {
  conversation_id: string;
  display_name: string | null;
  oldest: Ms;
  customer_rows: number;
}

/**
 * Observation list: eligible conversations with pending rows that no draft turn will deliver, which means that
 * draftBlocker is non-null or that no pending row is a customer message. Oldest pending row first.
 */
async function observe(env: Env, flags: Flags, limit: number, now: Ms): Promise<RoomsFeedConversation[]> {
  const out: RoomsFeedConversation[] = [];
  for (let offset = 0; offset < SCAN_MAX && out.length < limit; offset += SCAN_CHUNK) {
    const { results } = await env.DB.prepare(
      "SELECT c.id AS conversation_id, cu.display_name AS display_name, MIN(m.created_at) AS oldest, SUM(CASE WHEN m.source = 'customer' THEN 1 ELSE 0 END) AS customer_rows " +
        'FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN customers cu ON cu.id = c.customer_id ' +
        `WHERE ${ROOM_PENDING_SQL} AND ${ROOM_ELIGIBLE_SQL} GROUP BY c.id ORDER BY oldest ASC, c.id ASC LIMIT ? OFFSET ?`,
    )
      .bind(roomOldestAllowed(now), SCAN_CHUNK, offset)
      .all<Candidate>();
    for (const cand of results) {
      if (out.length >= limit) break;
      if (cand.customer_rows > 0 && (await draftWillRun(env, cand.conversation_id, flags))) continue;
      const messages = await pendingRows(env, cand.conversation_id, now, ROOM_OBSERVE_ROWS);
      if (messages.length) out.push({ conversation_id: cand.conversation_id, customer_display_name: displayName(cand.display_name), messages });
    }
    if (results.length < SCAN_CHUNK) break;
  }
  return out;
}

/**
 * Draft turn (and seed): the rows of one conversation whatever its draft blocker. A conversation that does not exist
 * or is not eligible answers no conversation at all; an eligible one answers one entry, whose `messages` is empty
 * when nothing waits.
 */
async function oneConversation(env: Env, input: FeedInput & { conversationId: string }, now: Ms): Promise<RoomsFeedConversation[]> {
  const conv = await env.DB.prepare(
    `SELECT c.id AS conversation_id, cu.display_name AS display_name FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE c.id = ? AND ${ROOM_ELIGIBLE_SQL}`,
  )
    .bind(input.conversationId)
    .first<{ conversation_id: string; display_name: string | null }>();
  if (!conv) return [];
  const messages = input.seed ? await seedRows(env, conv.conversation_id, now) : await pendingRows(env, conv.conversation_id, now, ROOM_TURN_ROWS);
  return [{ conversation_id: conv.conversation_id, customer_display_name: displayName(conv.display_name), messages }];
}

/**
 * POST /runner/rooms/feed. `{ enabled: false, conversations: [] }` when the flag rooms_enabled is false (nothing is
 * read) and when migration 0010 is not applied.
 */
export async function roomsFeed(env: Env, body: unknown, now: Ms): Promise<RoomsFeedResponse> {
  const flags = await getFlags(env);
  if (!flags.rooms_enabled) return OFF;
  const input = parseFeed(body);
  try {
    const conversations =
      input.conversationId !== null ? await oneConversation(env, { ...input, conversationId: input.conversationId }, now) : await observe(env, flags, input.limit, now);
    return { enabled: true, conversations };
  } catch (e) {
    if (isMissingMigration0010(e)) return OFF;
    throw e;
  }
}

// ---------------------------------------------------------------- ack

/**
 * POST /runner/rooms/ack: marks the listed rows of the conversation that are not yet marked, and stores the room
 * when `room` is given. Repeating a call marks nothing more. 404 for an unknown conversation; 409 invalid_state
 * when migration 0010 is not applied.
 */
export async function roomsAck(env: Env, body: unknown, now: Ms): Promise<RoomsAckResponse> {
  if (body === null || typeof body !== 'object' || Array.isArray(body)) throw bad('$', 'body must be an object');
  const d = body as Record<string, unknown>;
  if (typeof d.conversation_id !== 'string' || !d.conversation_id) throw bad('conversation_id');
  if (!Array.isArray(d.message_ids) || d.message_ids.some((x) => typeof x !== 'string' || !x)) throw bad('message_ids', 'message_ids must be a list of message ids');
  if (d.message_ids.length > ROOM_ACK_MAX_IDS) throw bad('message_ids', `at most ${ROOM_ACK_MAX_IDS} message ids per call`);
  let channelId: string | null = null;
  if (d.room !== undefined && d.room !== null) {
    const ch = typeof d.room === 'object' && !Array.isArray(d.room) ? (d.room as Record<string, unknown>).channel_id : undefined;
    if (typeof ch !== 'string' || !ch.trim() || ch.length > ROOM_CHANNEL_ID_MAX_CHARS) throw bad('room.channel_id');
    channelId = ch;
  }
  const conversationId = d.conversation_id;
  await mustConversation(env, conversationId);

  const ids = [...new Set(d.message_ids as string[])];
  const stmts: D1PreparedStatement[] = [];
  for (let i = 0; i < ids.length; i += IN_CHUNK) {
    const chunk = ids.slice(i, i + IN_CHUNK);
    stmts.push(
      env.DB.prepare(`UPDATE messages SET room_mirrored_at = ? WHERE conversation_id = ? AND room_mirrored_at IS NULL AND id IN (${chunk.map(() => '?').join(',')})`).bind(
        now,
        conversationId,
        ...chunk,
      ),
    );
  }
  const marking = stmts.length;
  if (channelId !== null) {
    stmts.push(env.DB.prepare('UPDATE conversations SET room_channel_id = ?, room_synced_at = ? WHERE id = ?').bind(channelId, now, conversationId));
  }
  if (!stmts.length) return { ok: true, marked: 0 };
  const res = await orConflict0010(env.DB.batch(stmts));
  const marked = res.slice(0, marking).reduce((n, r) => n + (r.meta?.changes ?? 0), 0);
  return { ok: true, marked };
}

// ---------------------------------------------------------------- handlers

/** POST /runner/rooms/feed. An absent body counts as `{}`. */
export const feed: H = async (c) => {
  const body = await readJson<unknown>(c).catch(() => ({}));
  return c.json(await roomsFeed(c.env, body, Date.now()));
};

/** POST /runner/rooms/ack */
export const ack: H = async (c) => {
  return c.json(await roomsAck(c.env, await readJson<unknown>(c), Date.now()));
};
