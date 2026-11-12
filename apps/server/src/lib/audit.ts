// Owner: server-core. Append-only audit_log writer. Never log message text or tokens in before/after JSON
// unless the entity itself is a staff-visible record (flags, drafts status, bot_state).
import type { Env } from '../types';

export interface AuditEntry {
  actor_type: 'staff' | 'system' | 'model' | 'runner' | 'zalo';
  actor_id?: string | null;
  action: string;
  entity?: string | null;
  entity_id?: string | null;
  before?: unknown;
  after?: unknown;
  request_id?: string | null;
}

export function auditStatement(env: Env, e: AuditEntry, at: number = Date.now()): D1PreparedStatement {
  return env.DB.prepare(
    'INSERT INTO audit_log (at, actor_type, actor_id, action, entity, entity_id, before_json, after_json, request_id) VALUES (?,?,?,?,?,?,?,?,?)',
  ).bind(
    at,
    e.actor_type,
    e.actor_id ?? null,
    e.action,
    e.entity ?? null,
    e.entity_id ?? null,
    e.before === undefined ? null : JSON.stringify(e.before),
    e.after === undefined ? null : JSON.stringify(e.after),
    e.request_id ?? null,
  );
}
