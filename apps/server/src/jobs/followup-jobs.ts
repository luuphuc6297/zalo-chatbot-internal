// Owner: server-core. Creates thank_you / check_in jobs when staff record a visit.
// dedupe_key = visit_id + ':' + type, so a repeated visit report never creates duplicate jobs.
// Timing (design/followup-templates.md): thank_you 20-24 h after visited_at inside 09:00-20:00 local
// (if that falls at night, 09:00 next morning); check_in 2 days after visited_at at 10:00 local.
import type { Env, JobStatus, VisitRequest, VisitResponse } from '../types';
import { HttpError } from '../lib/http';
import { newId } from '../lib/ids';
import { DAY_MS, HOUR_MS, localMidnight, localMinuteOfDay } from '../lib/time';
import { activeCatalogVersion, consentStatus } from '../lib/db';
import { auditStatement } from '../lib/audit';
import { benefitUsable, type BenefitRow } from '../lib/customer-summary';
import { getContactRole, isInternalRole, isMissingMigration0010, migration0010Error, orConflict0010 } from '../lib/roles';

export const FOLLOWUP_MAX_LATENESS_MS = 6 * HOUR_MS;

export function thankYouRunAt(visitedAt: number): number {
  const t = visitedAt + 20 * HOUR_MS;
  const m = localMinuteOfDay(t);
  if (m >= 9 * 60 && m < 20 * 60) return t;
  const midnight = localMidnight(t);
  return m < 9 * 60 ? midnight + 9 * HOUR_MS : midnight + DAY_MS + 9 * HOUR_MS;
}

export function checkInRunAt(visitedAt: number): number {
  return localMidnight(visitedAt) + 2 * DAY_MS + 10 * HOUR_MS;
}

// ---------------------------------------------------------------- visit details (docs/contracts.md section 14.5)

export const MAX_TECHNICIAN_CHARS = 60;
export const MAX_SERVICE_NAME_CHARS = 120;
export const MAX_DURATION_MIN = 24 * 60;

/** The optional details of a visit. null = not given (stored as NULL, an unknown amount is never 0). */
export interface VisitExtras {
  amount_vnd: number | null;
  technician: string | null;
  duration_min: number | null;
  service_name: string | null;
}

/** A known amount in VND: an integer, 0 or more. */
export function isVisitAmount(v: unknown): v is number {
  return typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
}

function oneLine(v: unknown, max: number, field: string): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v !== 'string' || /[\r\n]/.test(v) || v.trim().length > max) {
    throw new HttpError(422, 'validation_failed', `${field} must be one line of at most ${max} characters`, { field });
  }
  return v.trim() || null;
}

/**
 * Validates `amount_vnd`, `technician`, `duration_min` and `service_name` of a visit body (POST /staff/visits and one
 * row of POST /staff/visits/import). Absent, null and an empty text all mean "not given". Throws 422 validation_failed
 * naming `fieldPrefix + <field>`. Pure.
 */
export function parseVisitExtras(req: Pick<VisitRequest, 'amount_vnd' | 'technician' | 'duration_min' | 'service_name'>, fieldPrefix = ''): VisitExtras {
  const amount = req.amount_vnd ?? null;
  if (amount !== null && !isVisitAmount(amount)) {
    throw new HttpError(422, 'validation_failed', 'amount_vnd must be an integer of 0 or more (VND)', { field: `${fieldPrefix}amount_vnd` });
  }
  const duration = req.duration_min ?? null;
  if (duration !== null && (typeof duration !== 'number' || !Number.isInteger(duration) || duration <= 0 || duration > MAX_DURATION_MIN)) {
    throw new HttpError(422, 'validation_failed', `duration_min must be an integer from 1 to ${MAX_DURATION_MIN}`, { field: `${fieldPrefix}duration_min` });
  }
  return {
    amount_vnd: amount,
    technician: oneLine(req.technician, MAX_TECHNICIAN_CHARS, `${fieldPrefix}technician`),
    duration_min: duration,
    service_name: oneLine(req.service_name, MAX_SERVICE_NAME_CHARS, `${fieldPrefix}service_name`),
  };
}

/** The values of one visits row (the columns of migration 0010). */
export interface VisitInsert {
  id: string;
  customer_id: string;
  service_id: string;
  service_name: string | null;
  visited_at: number;
  duration_min: number | null;
  amount_vnd: number | null;
  technician: string | null;
  benefit_id: string | null;
  source: 'staff' | 'booking_app' | 'booking_request' | 'import';
  external_visit_id: string | null;
  booking_request_id: string | null;
  recorded_by: string | null;
  created_at: number;
}

/**
 * The statement that writes one visits row and nothing else: no thank_you or check_in job (docs/contracts.md section
 * 15.11, a visit confirmed from a chat guess, which happened long ago). recordVisit keeps its own statements and still
 * creates the follow-ups. With `guard`, the row is written only when `EXISTS (guard.sql)` holds when the statement
 * runs, so a batch can make the insert depend on an earlier statement of the same batch. Needs migration 0010.
 */
export function visitInsertStatement(env: Env, v: VisitInsert, guard?: { sql: string; binds: unknown[] }): D1PreparedStatement {
  const cols = 'id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, booking_request_id, recorded_by, created_at';
  const values = [v.id, v.customer_id, v.service_id, v.service_name, v.visited_at, v.duration_min, v.amount_vnd, v.technician, v.benefit_id, v.source, v.external_visit_id, v.booking_request_id, v.recorded_by, v.created_at];
  const marks = values.map(() => '?').join(',');
  return guard
    ? env.DB.prepare(`INSERT INTO visits (${cols}) SELECT ${marks} WHERE EXISTS (${guard.sql})`).bind(...values, ...guard.binds)
    : env.DB.prepare(`INSERT INTO visits (${cols}) VALUES (${marks})`).bind(...values);
}

/**
 * POST /staff/visits. Without the section 14.5 fields this is the behaviour from before section 14 and needs no
 * migration 0010. With one of `amount_vnd`, `technician`, `duration_min`, `service_name`, `benefit_id` the visit row
 * carries them, and a `benefit_id` uses one count of that benefit in the same batch as the visit row: the benefit must
 * belong to the same customer, be active, have a use left and not have expired on the local date of the visit, else
 * 409 invalid_state. The thank_you and check_in jobs are created either way. A body with one of the new fields answers
 * 409 invalid_state when migration 0010 is not applied.
 */
export async function recordVisit(env: Env, req: VisitRequest, staffId: string, now = Date.now()): Promise<VisitResponse> {
  if (!req || typeof req !== 'object') throw new HttpError(422, 'validation_failed', 'body must be an object');
  if (typeof req.customer_id !== 'string' || !req.customer_id) throw new HttpError(422, 'validation_failed', 'customer_id required', { field: 'customer_id' });
  if (typeof req.service_id !== 'string' || !req.service_id) throw new HttpError(422, 'validation_failed', 'service_id required', { field: 'service_id' });
  if (typeof req.visited_at !== 'number' || !Number.isFinite(req.visited_at) || req.visited_at > now + HOUR_MS) {
    throw new HttpError(422, 'validation_failed', 'visited_at must be ms and not in the future', { field: 'visited_at' });
  }
  if (req.external_visit_id !== undefined && (typeof req.external_visit_id !== 'string' || req.external_visit_id.length > 100)) {
    throw new HttpError(422, 'validation_failed', 'bad external_visit_id', { field: 'external_visit_id' });
  }
  const extras = parseVisitExtras(req);
  const benefitId = req.benefit_id ?? null;
  if (benefitId !== null && (typeof benefitId !== 'string' || !benefitId || benefitId.length > 100)) {
    throw new HttpError(422, 'validation_failed', 'bad benefit_id', { field: 'benefit_id' });
  }
  const extended = benefitId !== null || Object.values(extras).some((v) => v !== null);
  const customer = await env.DB.prepare('SELECT id, zalo_user_id FROM customers WHERE id = ?').bind(req.customer_id).first<{ id: string; zalo_user_id: string }>();
  if (!customer) throw new HttpError(404, 'not_found', 'customer not found');
  const cv = await activeCatalogVersion(env);
  const svc = cv
    ? await env.DB.prepare('SELECT service_id FROM services WHERE catalog_version = ? AND service_id = ?').bind(cv, req.service_id).first()
    : null;
  if (!svc) throw new HttpError(422, 'validation_failed', 'unknown service_id in the active catalog', { field: 'service_id' });

  if (req.external_visit_id) {
    const prev = await env.DB.prepare('SELECT id FROM visits WHERE external_visit_id = ?').bind(req.external_visit_id).first<{ id: string }>();
    if (prev) return visitResponse(env, prev.id);
  }

  if (benefitId !== null) {
    const benefit = await orConflict0010(
      env.DB.prepare('SELECT customer_id, status, total_count, used_count, expires_at FROM customer_benefits WHERE id = ?')
        .bind(benefitId)
        .first<Pick<BenefitRow, 'customer_id' | 'status' | 'total_count' | 'used_count' | 'expires_at'>>(),
    );
    if (!benefit || benefit.customer_id !== req.customer_id) throw new HttpError(409, 'invalid_state', 'benefit_id is not a benefit of this customer');
    if (!benefitUsable(benefit, req.visited_at)) throw new HttpError(409, 'invalid_state', 'the benefit is void, expired or has no use left');
  }

  const conv = await env.DB.prepare('SELECT id FROM conversations WHERE customer_id = ?').bind(req.customer_id).first<{ id: string }>();
  const consents = await consentStatus(env, req.customer_id);
  const prefs = await env.DB.prepare(
    "SELECT preference_type FROM contact_preferences WHERE customer_id = ? AND action = 'opt_out' AND preference_type IN ('followup_care','all_proactive_messages')",
  )
    .bind(req.customer_id)
    .all();
  // Sending still needs followup_care consent and approved ZBS templates; the scheduler re-checks at run time.
  const optedOut = prefs.results.length > 0 || consents.followup_care?.status === 'withdrawn';
  // Internal contact (docs/contracts.md section 14.3): the visit is recorded, its follow-up jobs are born skipped.
  const internal = isInternalRole((await getContactRole(env, customer.zalo_user_id))?.role);
  const skipReason = internal ? 'internal_contact' : optedOut ? 'opted_out' : null;
  const status: JobStatus = skipReason ? 'skipped' : 'queued';

  const visitId = newId('vis', now);
  const jobs = [
    { type: 'thank_you' as const, run_at: thankYouRunAt(req.visited_at) },
    { type: 'check_in' as const, run_at: checkInRunAt(req.visited_at) },
  ];
  const payload = JSON.stringify({ visit_id: visitId, service_id: req.service_id, catalog_version: cv });
  // The statement from before section 14 is kept for a body without the new fields, so it works without migration 0010.
  const visitInsert = extended
    ? env.DB.prepare(
        'INSERT INTO visits (id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, booking_request_id, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
      ).bind(visitId, req.customer_id, req.service_id, extras.service_name, req.visited_at, extras.duration_min, extras.amount_vnd, extras.technician, benefitId, 'staff', req.external_visit_id ?? null, req.booking_request_id ?? null, staffId, now)
    : env.DB.prepare('INSERT INTO visits (id, customer_id, service_id, visited_at, source, external_visit_id, booking_request_id, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)')
        .bind(visitId, req.customer_id, req.service_id, req.visited_at, 'staff', req.external_visit_id ?? null, req.booking_request_id ?? null, staffId, now);
  const statements = [
    visitInsert,
    // No "used_count < total_count" guard on purpose: when another request took the last use after the check above,
    // the CHECK of customer_benefits fails and D1 rolls the whole batch back, so no visit is written without its count.
    ...(benefitId !== null
      ? [env.DB.prepare('UPDATE customer_benefits SET used_count = used_count + 1, updated_at = ? WHERE id = ? AND customer_id = ?').bind(now, benefitId, req.customer_id)]
      : []),
    ...jobs.map((j) =>
      env.DB.prepare(
        'INSERT OR IGNORE INTO jobs (id, type, conversation_id, customer_id, status, run_at, max_attempts, max_lateness_ms, payload_json, dedupe_key, last_error, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?,?,?,?,?)',
      ).bind(newId('job', now), j.type, conv?.id ?? null, req.customer_id, status, j.run_at, FOLLOWUP_MAX_LATENESS_MS, payload, `${visitId}:${j.type}`, skipReason, now, now),
    ),
    auditStatement(
      env,
      { actor_type: 'staff', actor_id: staffId, action: 'visit.record', entity: 'visit', entity_id: visitId, after: { service_id: req.service_id, ...(benefitId !== null ? { benefit_id: benefitId } : {}) } },
      now,
    ),
  ];
  try {
    await env.DB.batch(statements);
  } catch (e) {
    if (extended && isMissingMigration0010(e)) throw migration0010Error();
    if (benefitId !== null && /CHECK constraint failed/i.test(e instanceof Error ? e.message : String(e))) {
      throw new HttpError(409, 'invalid_state', 'the benefit has no use left');
    }
    throw e;
  }
  return visitResponse(env, visitId);
}

async function visitResponse(env: Env, visitId: string): Promise<VisitResponse> {
  const { results } = await env.DB.prepare("SELECT id, type, run_at, status FROM jobs WHERE dedupe_key IN (?, ?) ORDER BY run_at")
    .bind(`${visitId}:thank_you`, `${visitId}:check_in`)
    .all<{ id: string; type: 'thank_you' | 'check_in'; run_at: number; status: JobStatus }>();
  return { visit_id: visitId, jobs: results.map((j) => ({ job_id: j.id, type: j.type, run_at: j.run_at, status: j.status })) };
}
