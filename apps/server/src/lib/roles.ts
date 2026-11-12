// Contact roles of the personal Zalo channel (docs/contracts.md section 14.3): the Zalo labels `Khách hàng`,
// `Quản lý`, `Nhân viên` imported into contact_roles, and the staff override of one contact.
//
// Precedence: a row with source 'staff' is never overwritten or removed by an import. A staff member who clears the
// role (PUT with null) deletes the row, so the next label import applies again.
//
// This file also holds the helpers for a D1 that does not have migration 0010 yet (`wrangler dev` reloads changed
// code before the owner applies the migration): reads on the customer path behave as "no role"; the staff endpoints
// of section 14 answer 409.
import type { ContactRole, ContactRoleRow, ContactRoleSource, Env, RolesImportResponse } from '../types';
import { auditStatement } from './audit';
import { chatTablesPresent, internalChatCleanupStatements } from './chat-facts-tables';
import { HttpError } from './http';

export type { ContactRole, ContactRoleRow } from '../types';

export const CONTACT_ROLES: ContactRole[] = ['customer', 'manager', 'staff'];
/** Roles of the people who work at the studio. The bot does not treat them as customers. */
export const INTERNAL_ROLES: ContactRole[] = ['manager', 'staff'];
/** A contact_roles key: 'p:' + the Zalo threadId, which is a string of digits on the personal channel. */
export const ROLE_ID_RE = /^p:\d{1,32}$/;
export const MAX_IMPORT_ROLES = 5000;
/** Statements per D1 batch of an import. */
const IMPORT_CHUNK = 500;
/** Ids per `IN (...)` list (D1 allows 100 bound parameters per statement). */
const IN_CHUNK = 90;

// ---------------------------------------------------------------- missing migration 0010

export const MIGRATION_0010 = '0010_rooms_roles_customer.sql';

const NEW_TABLES_0010 = 'contact_roles|customer_benefits';
const NEW_COLUMNS_0010 = 'service_name|duration_min|amount_vnd|technician|benefit_id|auto_reply|room_channel_id|room_synced_at|room_mirrored_at';

/**
 * True when a D1 error says that migration 0010 is not applied: one of its tables (contact_roles,
 * customer_benefits) or one of its columns (visits.service_name / duration_min / amount_vnd / technician /
 * benefit_id, conversations.auto_reply / room_channel_id / room_synced_at, messages.room_mirrored_at) is missing.
 */
export function isMissingMigration0010(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return (
    new RegExp(`no such table:?\\s*(?:main\\.)?(?:${NEW_TABLES_0010})\\b`, 'i').test(msg) ||
    new RegExp(`no such column:?\\s*(?:\\w+\\.)?(?:${NEW_COLUMNS_0010})\\b`, 'i').test(msg) ||
    new RegExp(`has no column named\\s*(?:${NEW_COLUMNS_0010})\\b`, 'i').test(msg)
  );
}

/** The 409 the staff and runner endpoints of section 14 answer before migration 0010. */
export function migration0010Error(): HttpError {
  return new HttpError(409, 'invalid_state', `the database is older than section 14: apply migration ${MIGRATION_0010}`);
}

/** Awaits `p`; a "migration 0010 is missing" error becomes `fallback` (read paths), any other error is rethrown. */
export async function orMissing0010<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingMigration0010(e)) return fallback;
    throw e;
  }
}

/** Awaits `p`; a "migration 0010 is missing" error becomes 409 invalid_state (staff writes and lists). */
export async function orConflict0010<T>(p: Promise<T>): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingMigration0010(e)) throw migration0010Error();
    throw e;
  }
}

// ---------------------------------------------------------------- read

const ROLE_COLS = 'zalo_user_id, role, source, updated_at, updated_by';

/** null when there is no row or the table is missing (migration 0010 not applied). */
export async function getContactRole(env: Env, zaloUserId: string): Promise<ContactRoleRow | null> {
  if (typeof zaloUserId !== 'string' || !zaloUserId) return null;
  return orMissing0010(env.DB.prepare(`SELECT ${ROLE_COLS} FROM contact_roles WHERE zalo_user_id = ?`).bind(zaloUserId).first<ContactRoleRow>(), null);
}

/**
 * The rows of several contacts in one call (conversation lists), keyed by zalo_user_id. Ids without a row are not in
 * the map. An empty map when the table is missing (migration 0010 not applied).
 */
export async function getContactRoles(env: Env, zaloUserIds: string[]): Promise<Map<string, ContactRoleRow>> {
  const out = new Map<string, ContactRoleRow>();
  const ids = [...new Set(zaloUserIds.filter((x) => typeof x === 'string' && x))];
  for (let i = 0; i < ids.length; i += IN_CHUNK) {
    const chunk = ids.slice(i, i + IN_CHUNK);
    const rows = await orMissing0010(
      env.DB.prepare(`SELECT ${ROLE_COLS} FROM contact_roles WHERE zalo_user_id IN (${chunk.map(() => '?').join(',')})`)
        .bind(...chunk)
        .all<ContactRoleRow>()
        .then((r) => r.results),
      null,
    );
    if (rows === null) return new Map();
    for (const r of rows) out.set(r.zalo_user_id, r);
  }
  return out;
}

/** manager or staff. Pure: false for 'customer', null and undefined (no role, or migration 0010 not applied). */
export function isInternalRole(role: ContactRole | null | undefined): boolean {
  return !!role && INTERNAL_ROLES.includes(role);
}

/**
 * true when the contact of this conversation has the role manager or staff (docs/contracts.md section 14.3). false
 * when there is no role, the conversation does not exist or migration 0010 is not applied.
 */
export async function conversationIsInternal(env: Env, conversationId: string): Promise<boolean> {
  const r = await orMissing0010(
    env.DB.prepare(
      'SELECT r.role AS role FROM conversations c JOIN customers cu ON cu.id = c.customer_id JOIN contact_roles r ON r.zalo_user_id = cu.zalo_user_id WHERE c.id = ?',
    )
      .bind(conversationId)
      .first<{ role: ContactRole }>(),
    null,
  );
  return isInternalRole(r?.role);
}

/** Every row, newest change first (GET /staff/roles). Throws 409 invalid_state when the table is missing. */
export async function listContactRoles(env: Env): Promise<ContactRoleRow[]> {
  const { results } = await orConflict0010(env.DB.prepare(`SELECT ${ROLE_COLS} FROM contact_roles ORDER BY updated_at DESC, zalo_user_id`).all<ContactRoleRow>());
  return results;
}

// ---------------------------------------------------------------- write

function fail(field: string, message: string): never {
  throw new HttpError(422, 'validation_failed', message, { field });
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/**
 * POST /staff/roles/import. Validates the whole list first (422 names the first bad field), then writes it in D1
 * batches of at most 500 statements. A list entry whose contact has a 'staff' row is skipped (`kept_staff`).
 * `complete: true` deletes the 'zalo_label' rows the list does not name; 'staff' rows stay. The audit entry
 * `roles.import` carries counts only. Throws 409 invalid_state when the table is missing (migration 0010 not applied).
 *
 * A contact that ends up manager or staff loses its undecided chat guesses in the same batches (section 15.11 step 2,
 * applied when the role changes rather than at the next analyzer run): internalChatCleanupStatements, only when
 * migration 0011 is applied.
 */
export async function importContactRoles(env: Env, body: unknown, staffId: string, now = Date.now()): Promise<RolesImportResponse> {
  if (!isObj(body)) fail('roles', 'body must be an object with a roles array');
  if (body.source !== 'zalo_label') fail('source', "source must be 'zalo_label'");
  if (body.complete !== undefined && typeof body.complete !== 'boolean') fail('complete', 'complete must be true or false');
  const list = body.roles;
  if (!Array.isArray(list)) fail('roles', 'roles must be an array');
  if (list.length > MAX_IMPORT_ROLES) fail('roles', `at most ${MAX_IMPORT_ROLES} roles per request`);
  const wanted = new Map<string, ContactRole>();
  list.forEach((r, i) => {
    if (!isObj(r)) fail(`roles[${i}]`, 'each role must be an object');
    const id = r.zalo_user_id;
    if (typeof id !== 'string' || !ROLE_ID_RE.test(id)) fail(`roles[${i}].zalo_user_id`, "zalo_user_id must be 'p:' + digits");
    if (typeof r.role !== 'string' || !(CONTACT_ROLES as string[]).includes(r.role)) fail(`roles[${i}].role`, `role must be one of ${CONTACT_ROLES.join(', ')}`);
    if (wanted.has(id)) fail(`roles[${i}].zalo_user_id`, 'duplicate zalo_user_id in this request');
    wanted.set(id, r.role as ContactRole);
  });

  const { results: rows } = await orConflict0010(
    env.DB.prepare('SELECT zalo_user_id, role, source FROM contact_roles').all<{ zalo_user_id: string; role: ContactRole; source: ContactRoleSource }>(),
  );
  const existing = new Map(rows.map((r) => [r.zalo_user_id, r]));

  const res: RolesImportResponse = { imported: 0, updated: 0, unchanged: 0, removed: 0, kept_staff: 0 };
  const stmts: D1PreparedStatement[] = [];
  // The WHERE of the upsert keeps a staff row that was written between the read above and this batch.
  const upsert =
    "INSERT INTO contact_roles (zalo_user_id, role, source, updated_at, updated_by) VALUES (?,?,'zalo_label',?,?) " +
    'ON CONFLICT(zalo_user_id) DO UPDATE SET role = excluded.role, updated_at = excluded.updated_at, updated_by = excluded.updated_by ' +
    "WHERE contact_roles.source = 'zalo_label'";
  for (const [id, role] of wanted) {
    const prev = existing.get(id);
    if (prev?.source === 'staff') {
      res.kept_staff += 1;
      continue;
    }
    if (prev && prev.role === role) {
      res.unchanged += 1;
      continue;
    }
    if (prev) res.updated += 1;
    else res.imported += 1;
    stmts.push(env.DB.prepare(upsert).bind(id, role, now, staffId));
  }
  // Section 15: undecided chat guesses of a contact that is now manager or staff (each statement checks the final role).
  const internalIds = [...wanted].filter(([id, role]) => existing.get(id)?.source !== 'staff' && isInternalRole(role)).map(([id]) => id);
  if (internalIds.length && (await chatTablesPresent(env))) stmts.push(...internalChatCleanupStatements(env, internalIds));
  if (body.complete === true) {
    const stale = rows.filter((r) => r.source === 'zalo_label' && !wanted.has(r.zalo_user_id)).map((r) => r.zalo_user_id);
    res.removed = stale.length;
    for (let i = 0; i < stale.length; i += IN_CHUNK) {
      const chunk = stale.slice(i, i + IN_CHUNK);
      stmts.push(env.DB.prepare(`DELETE FROM contact_roles WHERE source = 'zalo_label' AND zalo_user_id IN (${chunk.map(() => '?').join(',')})`).bind(...chunk));
    }
  }
  // Counts only: ids and names never go into audit_log.
  stmts.push(auditStatement(env, { actor_type: 'staff', actor_id: staffId, action: 'roles.import', entity: 'contact_roles', after: { ...res, complete: body.complete === true } }, now));
  for (let i = 0; i < stmts.length; i += IMPORT_CHUNK) await orConflict0010(env.DB.batch(stmts.slice(i, i + IMPORT_CHUNK)));
  return res;
}

/**
 * PUT /staff/roles/:zalo_user_id. A role writes the row with source 'staff'; null deletes the row whatever its source.
 * Returns the row after the change (null after a delete). The audit entry `role.staff_edit` carries role values only.
 * Throws 409 invalid_state when the table is missing (migration 0010 not applied). Setting manager or staff also
 * deletes the contact's undecided chat guesses and its phone suggestion in the same batch when migration 0011 is applied
 * (internalChatCleanupStatements, section 15.11 step 2).
 */
export async function setContactRole(env: Env, zaloUserId: string, body: unknown, staffId: string, now = Date.now()): Promise<ContactRoleRow | null> {
  if (!ROLE_ID_RE.test(zaloUserId)) throw new HttpError(400, 'bad_request', "zalo_user_id must be 'p:' + digits");
  if (!isObj(body) || !('role' in body)) fail('role', 'body must be an object with a role');
  const role = body.role;
  if (role !== null && (typeof role !== 'string' || !(CONTACT_ROLES as string[]).includes(role))) fail('role', `role must be one of ${CONTACT_ROLES.join(', ')} or null`);
  const prev = await orConflict0010(env.DB.prepare(`SELECT ${ROLE_COLS} FROM contact_roles WHERE zalo_user_id = ?`).bind(zaloUserId).first<ContactRoleRow>());
  const audit = auditStatement(
    env,
    {
      actor_type: 'staff',
      actor_id: staffId,
      action: 'role.staff_edit',
      entity: 'contact_role',
      entity_id: zaloUserId,
      before: prev ? { role: prev.role, source: prev.source } : null,
      after: role === null ? null : { role, source: 'staff' },
    },
    now,
  );
  if (role === null) {
    if (!prev) return null;
    await orConflict0010(env.DB.batch([env.DB.prepare('DELETE FROM contact_roles WHERE zalo_user_id = ?').bind(zaloUserId), audit]));
    return null;
  }
  const cleanup = isInternalRole(role as ContactRole) && (await chatTablesPresent(env)) ? internalChatCleanupStatements(env, [zaloUserId]) : [];
  await orConflict0010(
    env.DB.batch([
      env.DB.prepare(
        "INSERT INTO contact_roles (zalo_user_id, role, source, updated_at, updated_by) VALUES (?,?,'staff',?,?) " +
          "ON CONFLICT(zalo_user_id) DO UPDATE SET role = excluded.role, source = 'staff', updated_at = excluded.updated_at, updated_by = excluded.updated_by",
      ).bind(zaloUserId, role, now, staffId),
      audit,
      ...cleanup,
    ]),
  );
  return { zalo_user_id: zaloUserId, role: role as ContactRole, source: 'staff', updated_at: now, updated_by: staffId };
}
