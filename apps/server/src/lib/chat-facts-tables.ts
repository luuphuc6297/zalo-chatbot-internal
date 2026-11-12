// The tables of migration 0011 (docs/contracts.md section 15) as seen from code that also runs before 0011 is applied:
// the role writes (lib/roles.ts), the phone edit (PATCH /staff/customers/:id) and lib/chat-facts.ts itself.
//
// This module imports nothing from lib/chat-facts.ts, lib/roles.ts or staff-api/customers.ts, so those can use it
// without an import cycle. Every statement here touches only the chat tables; the callers put them in the same D1
// batch as their own write, after checking chatTablesPresent (a batch that names a missing table fails as a whole).
import type { Env } from '../types';
import { HttpError } from './http';

export const MIGRATION_0011 = '0011_chat_facts.sql';
const NEW_TABLES_0011 = 'chat_visits|chat_benefits|chat_contact_facts|chat_phone_dismissed';
const NEW_COLUMNS_0011 = 'phone_decision_id';

/**
 * True when a D1 error says that migration 0011 is not applied: one of its four tables is missing, or the column
 * chat_contact_facts.phone_decision_id is (a database that applied an earlier draft of 0011).
 */
export function isMissingMigration0011(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return (
    new RegExp(`no such table:?\\s*(?:main\\.)?(?:${NEW_TABLES_0011})\\b`, 'i').test(msg) ||
    new RegExp(`no such column:?\\s*(?:\\w+\\.)?(?:${NEW_COLUMNS_0011})\\b`, 'i').test(msg) ||
    new RegExp(`has no column named\\s*(?:${NEW_COLUMNS_0011})\\b`, 'i').test(msg)
  );
}

/** The 409 every endpoint of section 15.11 answers before migration 0011. */
export function migration0011Error(): HttpError {
  return new HttpError(409, 'invalid_state', `the database is older than section 15: apply migration ${MIGRATION_0011}`);
}

/** Awaits `p`; a "migration 0011 is missing" error becomes `fallback` (the summary), any other error is rethrown. */
export async function orMissing0011<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingMigration0011(e)) return fallback;
    throw e;
  }
}

/** Whether every table and column of migration 0011 is there. Any other D1 error is rethrown. */
export async function chatTablesPresent(env: Env): Promise<boolean> {
  return orMissing0011(
    env.DB.batch([
      env.DB.prepare('SELECT 1 FROM chat_visits LIMIT 0'),
      env.DB.prepare('SELECT 1 FROM chat_benefits LIMIT 0'),
      env.DB.prepare('SELECT phone_decision_id FROM chat_contact_facts LIMIT 0'),
      env.DB.prepare('SELECT 1 FROM chat_phone_dismissed LIMIT 0'),
    ]).then(() => true),
    false,
  );
}

const IN_CHUNK = 90;
const marks = (n: number) => Array.from({ length: n }, () => '?').join(',');

/** Every chat row of one contact (removal of a customer or a contact profile, section 15.11 "Removal"). */
export function chatFactsRemovalStatements(env: Env, zaloUserId: string): D1PreparedStatement[] {
  return [
    env.DB.prepare('DELETE FROM chat_visits WHERE zalo_user_id = ?').bind(zaloUserId),
    env.DB.prepare('DELETE FROM chat_benefits WHERE zalo_user_id = ?').bind(zaloUserId),
    env.DB.prepare('DELETE FROM chat_contact_facts WHERE zalo_user_id = ?').bind(zaloUserId),
    env.DB.prepare('DELETE FROM chat_phone_dismissed WHERE zalo_user_id = ?').bind(zaloUserId),
  ];
}

/**
 * A contact who becomes manager or staff loses the guesses nobody decided on, as import step 2 does (section 15.11):
 * its active chat_visits and chat_benefits rows are deleted and its phone suggestion is cleared. Confirmed and dismissed
 * rows stay. Each statement checks the contact_roles row itself, so it runs after the role write in the same batch and
 * does nothing for a contact whose role is not manager or staff by then.
 */
export function internalChatCleanupStatements(env: Env, zaloUserIds: string[]): D1PreparedStatement[] {
  const out: D1PreparedStatement[] = [];
  const internal = "SELECT r.zalo_user_id FROM contact_roles r WHERE r.role IN ('manager','staff')";
  const ids = [...new Set(zaloUserIds)];
  for (let i = 0; i < ids.length; i += IN_CHUNK) {
    const chunk = ids.slice(i, i + IN_CHUNK);
    const where = `zalo_user_id IN (${marks(chunk.length)}) AND zalo_user_id IN (${internal})`;
    out.push(
      env.DB.prepare(`DELETE FROM chat_visits WHERE state = 'active' AND ${where}`).bind(...chunk),
      env.DB.prepare(`DELETE FROM chat_benefits WHERE state = 'active' AND ${where}`).bind(...chunk),
      env.DB.prepare(`UPDATE chat_contact_facts SET phone_suggestion = NULL WHERE phone_suggestion IS NOT NULL AND ${where}`).bind(...chunk),
    );
  }
  return out;
}

/**
 * Staff removed or replaced a phone number of a customer (PATCH /staff/customers/:id): the number is remembered for the
 * contact so that the import neither writes it back into customers.phone nor suggests it again, and a pending
 * suggestion of that same number is cleared. `phone` is the normalised number that was stored.
 */
export function phoneRemovedStatements(env: Env, zaloUserId: string, phone: string, staffId: string, now: number): D1PreparedStatement[] {
  return [
    env.DB.prepare(
      "INSERT INTO chat_phone_dismissed (zalo_user_id, phone, reason, decided_by, decided_at) VALUES (?,?,'staff_removed',?,?) ON CONFLICT(zalo_user_id, phone) DO NOTHING",
    ).bind(zaloUserId, phone, staffId, now),
    env.DB.prepare('UPDATE chat_contact_facts SET phone_suggestion = NULL WHERE zalo_user_id = ? AND phone_suggestion = ?').bind(zaloUserId, phone),
  ];
}
