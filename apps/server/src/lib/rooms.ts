// Owner: server-core. Rules of the rooms feed (docs/contracts.md section 14.7): which conversations may be mirrored
// into a staff room and which message rows are still waiting to be copied. The endpoints are in
// src/runner-api/rooms.ts; the staff conversation view uses roomPendingCount.
//
// Every statement built from these fragments reads messages.room_mirrored_at and contact_roles, so it fails with a
// "migration 0010 is missing" error on an older database; the callers turn that error into "rooms off".
import type { Env, Ms, RoomsFeedMessage } from '../types';
import { DAY_MS } from './time';
import { orMissing0010 } from './roles';

/** A row older than this is never copied into a room. */
export const ROOM_ROW_MAX_AGE_MS = 14 * DAY_MS;

/**
 * An eligible conversation, over the aliases `c` (conversations) and `cu` (customers): a one-to-one personal
 * conversation (group threads never reach the server, src/zalo/personal.ts), whose customer is not deleted, is not
 * flagged as a minor, has `ai_assistant` consent granted (the last consent row wins) and is not an internal contact.
 * No bound parameter.
 */
export const ROOM_ELIGIBLE_SQL =
  "cu.channel = 'personal' AND cu.deleted_at IS NULL AND (cu.minor_flag IS NULL OR cu.minor_flag != 1) " +
  "AND (SELECT s.status FROM consents s WHERE s.customer_id = cu.id AND s.purpose = 'ai_assistant' ORDER BY s.recorded_at DESC, s.rowid DESC LIMIT 1) = 'granted' " +
  "AND NOT EXISTS (SELECT 1 FROM contact_roles r WHERE r.zalo_user_id = cu.zalo_user_id AND r.role IN ('manager','staff'))";

/**
 * The row rule, over the aliases `m` (messages) and `c` (conversations): written after the consent, with a text, not
 * a user_info row, inbound or a delivered outbound row, at most 14 days old. One bound parameter: the oldest
 * `created_at` allowed (roomOldestAllowed).
 */
export const ROOM_ROW_SQL =
  "m.seq > c.consent_seq AND m.text IS NOT NULL AND m.kind != 'user_info' AND (m.direction = 'inbound' OR m.send_state = 'sent') AND m.created_at >= ?";

/** A pending row: the row rule and not yet mirrored. One bound parameter, as ROOM_ROW_SQL. */
export const ROOM_PENDING_SQL = `m.room_mirrored_at IS NULL AND ${ROOM_ROW_SQL}`;

/** The columns of one feed message, over the alias `m`. */
export const ROOM_MESSAGE_COLS = 'm.id AS message_id, m.seq AS seq, m.source AS source, m.direction AS direction, m.kind AS kind, m.text AS text, m.created_at AS at';

export type RoomMessageRow = RoomsFeedMessage;

export function roomOldestAllowed(now: Ms): Ms {
  return now - ROOM_ROW_MAX_AGE_MS;
}

/**
 * How many rows of this conversation still wait to be copied into its room. 0 for a conversation that is not
 * eligible (its rows are never fed) and when migration 0010 is not applied.
 */
export async function roomPendingCount(env: Env, conversationId: string, now: Ms): Promise<number> {
  const r = await orMissing0010(
    env.DB.prepare(
      `SELECT COUNT(*) AS n FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN customers cu ON cu.id = c.customer_id WHERE c.id = ? AND ${ROOM_PENDING_SQL} AND ${ROOM_ELIGIBLE_SQL}`,
    )
      .bind(conversationId, roomOldestAllowed(now))
      .first<{ n: number }>(),
    null,
  );
  return r?.n ?? 0;
}
