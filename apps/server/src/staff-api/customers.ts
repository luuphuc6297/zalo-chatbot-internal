// Staff endpoints of docs/contracts.md section 14.3 (contact roles) and 14.5 (visit history, benefits, phone).
//
//   POST  /staff/roles/import          Zalo labels -> contact_roles
//   GET   /staff/roles
//   PUT   /staff/roles/:zalo_user_id   staff override of one contact
//   POST  /staff/visits/import         visit history from the studio's own records (no follow-up jobs)
//   GET   /staff/visits?customer_id=
//   GET   /staff/benefits?customer_id=
//   POST  /staff/benefits
//   PATCH /staff/benefits/:id
//   PATCH /staff/customers/:id         phone only
//
// Every endpoint but the last needs migration 0010 and answers 409 invalid_state before it is applied. Audit entries
// carry ids, counts and flags only: never a name, a phone number or a title typed by staff.
import type { Context } from 'hono';
import type { AppEnv, BenefitKind, BenefitStatus, CustomerBenefit, CustomerView, Env, VisitImportUnmatchedReason, VisitRequest, VisitSource, VisitView, VisitsImportResponse } from '../types';
import { auditStatement } from '../lib/audit';
import { chatTablesPresent, phoneRemovedStatements } from '../lib/chat-facts-tables';
import { BENEFIT_COLS, benefitView, normalizePhone, type BenefitRow } from '../lib/customer-summary';
import { activeCatalogVersion } from '../lib/db';
import { HttpError, readJson } from '../lib/http';
import { newId } from '../lib/ids';
import { ROLE_ID_RE, importContactRoles, listContactRoles, orConflict0010, setContactRole } from '../lib/roles';
import { stripMarks } from '../lib/text';
import { HOUR_MS, TZ_OFFSET_MS, isValidLocalDate } from '../lib/time';
import { PERSONAL_OA_ID } from '../lib/zalo-personal';
import { MAX_SERVICE_NAME_CHARS, isVisitAmount, parseVisitExtras } from '../jobs/followup-jobs';

type H = (c: Context<AppEnv>) => Promise<Response>;
const staffId = (c: Context<AppEnv>) => c.get('staffId') ?? 'staff';

export const MAX_IMPORT_VISITS = 2000;
export const MAX_BENEFIT_TITLE_CHARS = 120;
export const MAX_BENEFIT_COUNT = 1000;
/** Rows of GET /staff/visits. */
const MAX_VISITS_LISTED = 200;
/** Statements per D1 batch of an import. */
const IMPORT_CHUNK = 500;
/** Values per `IN (...)` list (D1 allows 100 bound parameters per statement). */
const IN_CHUNK = 90;
const MAX_EXT_SLUG_CHARS = 60;
/** A visit time before this is a mistake (seconds sent as milliseconds, a spreadsheet serial number). */
const MIN_VISIT_MS = Date.UTC(2000, 0, 1);

function fail(field: string, message: string): never {
  throw new HttpError(422, 'validation_failed', message, { field });
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
/** A body field that was sent: not absent, not null and not an empty text. */
const given = (v: unknown): boolean => v !== undefined && v !== null && v !== '';

// ---------------------------------------------------------------- contact roles (section 14.3)

export const importRoles: H = async (c) => c.json(await importContactRoles(c.env, await readJson(c), staffId(c)));

export const listRoles: H = async (c) => c.json({ roles: await listContactRoles(c.env) });

export const putRole: H = async (c) => c.json({ role: await setContactRole(c.env, c.req.param('zalo_user_id') ?? '', await readJson(c), staffId(c)) });

// ---------------------------------------------------------------- shared lookups

async function mustCustomer(env: Env, id: unknown, opts: { inBody: boolean }): Promise<void> {
  if (typeof id !== 'string' || !id) fail('customer_id', 'customer_id required');
  const row = await env.DB.prepare('SELECT id FROM customers WHERE id = ? AND deleted_at IS NULL').bind(id).first<{ id: string }>();
  if (!row) throw new HttpError(404, 'not_found', opts.inBody ? 'customer_id: customer not found' : 'customer not found');
}

/** service_id -> display name of the active catalog. Empty when no catalog is active. */
async function activeServiceNames(env: Env): Promise<Map<string, string>> {
  const cv = await activeCatalogVersion(env);
  const out = new Map<string, string>();
  if (!cv) return out;
  const { results } = await env.DB.prepare('SELECT service_id, display_name_vi FROM services WHERE catalog_version = ?')
    .bind(cv)
    .all<{ service_id: string; display_name_vi: string }>();
  for (const s of results) out.set(s.service_id, s.display_name_vi);
  return out;
}

// ---------------------------------------------------------------- visits (section 14.5)

interface VisitDbRow {
  id: string;
  customer_id: string;
  service_id: string;
  service_name: string | null;
  visited_at: number;
  duration_min: number | null;
  amount_vnd: number | null;
  technician: string | null;
  benefit_id: string | null;
  source: VisitSource;
  external_visit_id: string | null;
  recorded_by: string | null;
  created_at: number;
}

const VISIT_COLS = 'id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, recorded_by, created_at';

/**
 * GET /staff/visits?customer_id=: the visit rows of one customer, newest first, at most 200. `name` is the display
 * name of the active catalog, else the stored service_name, else the service_id. 422 without customer_id, 404 for an
 * unknown or deleted customer, 409 invalid_state when migration 0010 is not applied.
 */
export async function listVisits(env: Env, customerId: unknown): Promise<VisitView[]> {
  await mustCustomer(env, customerId, { inBody: false });
  const { results } = await orConflict0010(
    env.DB.prepare(`SELECT ${VISIT_COLS} FROM visits WHERE customer_id = ? ORDER BY visited_at DESC, id DESC LIMIT ${MAX_VISITS_LISTED}`)
      .bind(customerId)
      .all<VisitDbRow>(),
  );
  const names = results.length ? await activeServiceNames(env) : new Map<string, string>();
  return results.map((r) => ({
    id: r.id,
    customer_id: r.customer_id,
    service_id: r.service_id,
    service_name: r.service_name,
    name: names.get(r.service_id) ?? r.service_name ?? r.service_id,
    visited_at: r.visited_at,
    duration_min: r.duration_min,
    amount_vnd: r.amount_vnd,
    technician: r.technician,
    benefit_id: r.benefit_id,
    source: r.source,
    external_visit_id: r.external_visit_id,
    recorded_by: r.recorded_by,
    created_at: r.created_at,
  }));
}

export const listVisitsHandler: H = async (c) => c.json({ visits: await listVisits(c.env, c.req.query('customer_id')) });

/** 'YYYY-MM-DD HH:MM' (also 'T' between date and time, and seconds) in Asia/Ho_Chi_Minh -> ms. null when not a real local time. */
export function parseLocalDateTime(s: string): number | null {
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(s.trim());
  if (!m || !isValidLocalDate(m[1]!)) return null;
  const hh = Number(m[2]);
  const mm = Number(m[3]);
  const ss = Number(m[4] ?? 0);
  if (hh > 23 || mm > 59 || ss > 59) return null;
  const [y, mo, d] = m[1]!.split('-').map(Number) as [number, number, number];
  return Date.UTC(y, mo - 1, d, hh, mm, ss) - TZ_OFFSET_MS;
}

/** The part of an 'ext:<slug>' service id: lowercase ASCII letters and digits joined by '-'. '' when nothing is left. */
export function serviceSlug(name: string): string {
  return stripMarks(name)
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_EXT_SLUG_CHARS)
    .replace(/-+$/, '');
}

interface CustomerRef {
  id: string;
  zalo_user_id: string;
  phone: string | null;
  deleted_at: number | null;
}

/** A row that passed every check. `customerId` is null for a `p:<digits>` contact whose customers row is created by this import. */
interface AcceptedVisit {
  customerId: string | null;
  zaloUserId: string | null;
  serviceId: string;
  serviceName: string | null;
  visitedAt: number;
  durationMin: number | null;
  amountVnd: number | null;
  technician: string | null;
  externalVisitId: string | null;
}

function visitTime(r: Record<string, unknown>, now: number): number | null {
  let t: number | null = null;
  if (given(r.visited_at)) t = typeof r.visited_at === 'number' && Number.isFinite(r.visited_at) ? Math.floor(r.visited_at) : null;
  else if (typeof r.visited_at_local === 'string') t = parseLocalDateTime(r.visited_at_local);
  return t !== null && t >= MIN_VISIT_MS && t <= now + HOUR_MS ? t : null;
}

function visitService(r: Record<string, unknown>, catalog: Map<string, string>): { serviceId: string; serviceName: string | null } | null {
  let name: string | null = null;
  if (given(r.service_name)) {
    if (typeof r.service_name !== 'string' || /[\r\n]/.test(r.service_name) || r.service_name.trim().length > MAX_SERVICE_NAME_CHARS) return null;
    name = r.service_name.trim() || null;
  }
  if (typeof r.service_id === 'string' && catalog.has(r.service_id)) return { serviceId: r.service_id, serviceName: name };
  if (!name) return null;
  const slug = serviceSlug(name);
  return slug ? { serviceId: `ext:${slug}`, serviceName: name } : null;
}

/**
 * POST /staff/visits/import. History from the studio's own records: writes visit rows with source 'import' and never
 * creates a thank_you or check_in job.
 *
 * The body shape is checked first (422 names the field: `visits`, `dry_run`, `visits[i]`, `visits[i].technician`,
 * `visits[i].duration_min`, `visits[i].external_visit_id`). Every other problem of a row puts the row into
 * `unmatched` with the first reason that applies, in this order:
 *   no_customer  the first of customer_id / zalo_user_id / phone that is given decides, there is no fall-through.
 *                customer_id: a customers row that is not deleted. zalo_user_id: the customers row with that id, or,
 *                for a `p:<digits>` id without a row, a minimal row created by this import (`created_customers`).
 *                phone: exactly one customer whose stored phone normalises to the same digits (normalizePhone).
 *   bad_time     visited_at (ms) or visited_at_local ('YYYY-MM-DD HH:MM', Asia/Ho_Chi_Minh) is missing, not a real
 *                time, before the year 2000 or more than one hour after now.
 *   bad_service  service_id is not in the active catalog and service_name is missing, not one line of at most 120
 *                characters, or has no letter or digit. A service outside the catalog is stored with
 *                service_id 'ext:' + slug(service_name).
 *   bad_amount   amount_vnd is given and is not an integer of 0 or more.
 * A row whose external_visit_id exists (in the table, or earlier in the request), or, without one, whose customer,
 * visited_at and service_id match an existing visit or an earlier row of the request, is counted in `duplicates`.
 *
 * `dry_run: true` answers the same counts and writes nothing. Otherwise the rows are written in D1 batches of at most
 * 500 statements, with the audit entry `visits.import` (counts only) in the last one. Throws 409 invalid_state when
 * migration 0010 is not applied, also for a dry run.
 */
export async function importVisits(env: Env, body: unknown, staffId: string, now = Date.now()): Promise<VisitsImportResponse> {
  if (!isObj(body)) fail('visits', 'body must be an object with a visits array');
  if (body.dry_run !== undefined && typeof body.dry_run !== 'boolean') fail('dry_run', 'dry_run must be true or false');
  const list = body.visits;
  if (!Array.isArray(list)) fail('visits', 'visits must be an array');
  if (list.length > MAX_IMPORT_VISITS) fail('visits', `at most ${MAX_IMPORT_VISITS} visits per request`);
  const details = list.map((r, i) => {
    if (!isObj(r)) fail(`visits[${i}]`, 'each visit must be an object');
    const ext = r.external_visit_id;
    if (given(ext) && (typeof ext !== 'string' || ext.length > 100)) fail(`visits[${i}].external_visit_id`, 'external_visit_id must be a text of at most 100 characters');
    // technician and duration_min have no `unmatched` reason in the contract, so a bad value is a 422 of the request.
    return parseVisitExtras({ technician: r.technician, duration_min: r.duration_min } as Pick<VisitRequest, 'technician' | 'duration_min'>, `visits[${i}].`);
  });
  const rows = list as Array<Record<string, unknown>>;

  // The columns of migration 0010, asked for before anything else so that a dry run answers 409 too.
  await orConflict0010(env.DB.prepare('SELECT service_name, duration_min, amount_vnd, technician, benefit_id FROM visits LIMIT 1').first());

  const { results: customers } = await env.DB.prepare('SELECT id, zalo_user_id, phone, deleted_at FROM customers').all<CustomerRef>();
  const byId = new Map<string, CustomerRef>();
  const byZalo = new Map<string, CustomerRef[]>();
  const byPhone = new Map<string, CustomerRef[]>();
  const push = (m: Map<string, CustomerRef[]>, k: string, v: CustomerRef) => {
    const l = m.get(k);
    if (l) l.push(v);
    else m.set(k, [v]);
  };
  for (const cu of customers) {
    byId.set(cu.id, cu);
    push(byZalo, cu.zalo_user_id, cu);
    const phone = cu.deleted_at === null ? normalizePhone(cu.phone) : null;
    if (phone) push(byPhone, phone, cu);
  }
  const catalog = await activeServiceNames(env);

  /** The customer of a row: an existing id, a `p:<digits>` id to create, or null (no_customer). */
  const customerOf = (r: Record<string, unknown>): { id: string | null; zaloUserId: string | null } | null => {
    if (given(r.customer_id)) {
      const cu = typeof r.customer_id === 'string' ? byId.get(r.customer_id) : undefined;
      return cu && cu.deleted_at === null ? { id: cu.id, zaloUserId: null } : null;
    }
    if (given(r.zalo_user_id)) {
      if (typeof r.zalo_user_id !== 'string') return null;
      const found = byZalo.get(r.zalo_user_id) ?? [];
      if (found.length === 1) return found[0]!.deleted_at === null ? { id: found[0]!.id, zaloUserId: null } : null;
      if (found.length > 1) return null;
      return ROLE_ID_RE.test(r.zalo_user_id) ? { id: null, zaloUserId: r.zalo_user_id } : null;
    }
    if (given(r.phone)) {
      const phone = normalizePhone(r.phone);
      const found = phone ? (byPhone.get(phone) ?? []) : [];
      return found.length === 1 ? { id: found[0]!.id, zaloUserId: null } : null;
    }
    return null;
  };

  const unmatched: VisitsImportResponse['unmatched'] = [];
  const valid: AcceptedVisit[] = [];
  rows.forEach((r, i) => {
    const miss = (reason: VisitImportUnmatchedReason) => unmatched.push({ index: i, reason });
    const customer = customerOf(r);
    if (!customer) return miss('no_customer');
    const visitedAt = visitTime(r, now);
    if (visitedAt === null) return miss('bad_time');
    const service = visitService(r, catalog);
    if (!service) return miss('bad_service');
    if (given(r.amount_vnd) && !isVisitAmount(r.amount_vnd)) return miss('bad_amount');
    valid.push({
      customerId: customer.id,
      zaloUserId: customer.zaloUserId,
      serviceId: service.serviceId,
      serviceName: service.serviceName,
      visitedAt,
      durationMin: details[i]!.duration_min,
      amountVnd: given(r.amount_vnd) ? (r.amount_vnd as number) : null,
      technician: details[i]!.technician,
      externalVisitId: given(r.external_visit_id) ? (r.external_visit_id as string) : null,
    });
  });

  // What the table already holds: the external ids of the request, and the visits of the customers of the request.
  const seenExternal = new Set<string>();
  const seenVisit = new Set<string>();
  const visitKey = (customer: string, visitedAt: number, serviceId: string) => `${customer}|${visitedAt}|${serviceId}`;
  const externalIds = [...new Set(valid.map((v) => v.externalVisitId).filter((x): x is string => x !== null))];
  for (let i = 0; i < externalIds.length; i += IN_CHUNK) {
    const chunk = externalIds.slice(i, i + IN_CHUNK);
    const { results } = await env.DB.prepare(`SELECT external_visit_id FROM visits WHERE external_visit_id IN (${chunk.map(() => '?').join(',')})`)
      .bind(...chunk)
      .all<{ external_visit_id: string }>();
    for (const x of results) seenExternal.add(x.external_visit_id);
  }
  const customerIds = [...new Set(valid.map((v) => v.customerId).filter((x): x is string => x !== null))];
  for (let i = 0; i < customerIds.length; i += IN_CHUNK) {
    const chunk = customerIds.slice(i, i + IN_CHUNK);
    const { results } = await env.DB.prepare(`SELECT customer_id, visited_at, service_id FROM visits WHERE customer_id IN (${chunk.map(() => '?').join(',')})`)
      .bind(...chunk)
      .all<{ customer_id: string; visited_at: number; service_id: string }>();
    for (const x of results) seenVisit.add(visitKey(x.customer_id, x.visited_at, x.service_id));
  }

  let duplicates = 0;
  const accepted: AcceptedVisit[] = [];
  for (const v of valid) {
    // A contact that gets its customers row from this import is keyed by its Zalo id until the row exists.
    const key = visitKey(v.customerId ?? `new:${v.zaloUserId}`, v.visitedAt, v.serviceId);
    if (v.externalVisitId !== null ? seenExternal.has(v.externalVisitId) : seenVisit.has(key)) {
      duplicates += 1;
      continue;
    }
    if (v.externalVisitId !== null) seenExternal.add(v.externalVisitId);
    seenVisit.add(key);
    accepted.push(v);
  }
  const newContacts = [...new Set(accepted.map((v) => v.zaloUserId).filter((x): x is string => x !== null))];
  const res: VisitsImportResponse = { imported: accepted.length, duplicates, created_customers: newContacts.length, unmatched };
  if (body.dry_run === true) return res;

  const stmts: D1PreparedStatement[] = [];
  // The minimal row the personal webhook writes for a new sender (conversation-do.ts). OR IGNORE: the contact may have
  // written in the meantime, so the visit rows below look the customer up instead of using the id generated here.
  for (const zaloUserId of newContacts) {
    stmts.push(
      env.DB.prepare('INSERT OR IGNORE INTO customers (id, oa_id, zalo_user_id, user_id_by_app, channel, created_at) VALUES (?,?,?,?,?,?)').bind(
        newId('cus', now),
        PERSONAL_OA_ID,
        zaloUserId,
        null,
        'personal',
        now,
      ),
    );
  }
  const VISIT_INSERT = 'INSERT INTO visits (id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, booking_request_id, recorded_by, created_at) VALUES ';
  for (const v of accepted) {
    const tail = [v.serviceId, v.serviceName, v.visitedAt, v.durationMin, v.amountVnd, v.technician, v.externalVisitId, staffId, now];
    stmts.push(
      v.customerId !== null
        ? env.DB.prepare(`${VISIT_INSERT}(?,?,?,?,?,?,?,?,NULL,'import',?,NULL,?,?)`).bind(newId('vis', now), v.customerId, ...tail)
        : env.DB.prepare(`${VISIT_INSERT}(?,(SELECT id FROM customers WHERE oa_id = ? AND zalo_user_id = ?),?,?,?,?,?,?,NULL,'import',?,NULL,?,?)`).bind(
            newId('vis', now),
            PERSONAL_OA_ID,
            v.zaloUserId,
            ...tail,
          ),
    );
  }
  // Counts only: ids, names and phone numbers never go into audit_log.
  stmts.push(
    auditStatement(
      env,
      { actor_type: 'staff', actor_id: staffId, action: 'visits.import', entity: 'visits', after: { imported: res.imported, duplicates: res.duplicates, created_customers: res.created_customers, unmatched: unmatched.length } },
      now,
    ),
  );
  for (let i = 0; i < stmts.length; i += IMPORT_CHUNK) await orConflict0010(env.DB.batch(stmts.slice(i, i + IMPORT_CHUNK)));
  return res;
}

export const importVisitsHandler: H = async (c) => c.json(await importVisits(c.env, await readJson(c), staffId(c)));

// ---------------------------------------------------------------- benefits (section 14.5)

const BENEFIT_KINDS: BenefitKind[] = ['package', 'voucher'];
const BENEFIT_STATUSES: BenefitStatus[] = ['active', 'void'];
const BENEFIT_PATCH_FIELDS = ['title', 'used_count', 'expires_at', 'status'];

function benefitTitle(v: unknown): string {
  if (typeof v !== 'string' || /[\r\n]/.test(v) || !v.trim() || v.trim().length > MAX_BENEFIT_TITLE_CHARS) {
    fail('title', `title must be one line of 1 to ${MAX_BENEFIT_TITLE_CHARS} characters`);
  }
  return v.trim();
}

/** null (no expiry) or a time in ms. A past time is allowed: staff also record benefits that have already expired. */
function benefitExpiry(v: unknown): number | null {
  if (v === undefined || v === null) return null;
  if (typeof v !== 'number' || !Number.isSafeInteger(v) || v <= 0) fail('expires_at', 'expires_at must be a time in ms or null');
  return v;
}

function usedCount(v: unknown, total: number): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < 0 || v > total) fail('used_count', `used_count must be an integer from 0 to total_count (${total})`);
  return v;
}

/**
 * GET /staff/benefits?customer_id=: every benefit of the customer, active ones first, then newest first. 422 without
 * customer_id, 404 for an unknown or deleted customer, 409 invalid_state when migration 0010 is not applied.
 */
export async function listBenefits(env: Env, customerId: unknown): Promise<CustomerBenefit[]> {
  await mustCustomer(env, customerId, { inBody: false });
  const { results } = await orConflict0010(
    env.DB.prepare(`SELECT ${BENEFIT_COLS} FROM customer_benefits WHERE customer_id = ? ORDER BY (status != 'active'), created_at DESC, id DESC`)
      .bind(customerId)
      .all<BenefitRow>(),
  );
  return results.map(benefitView);
}

/**
 * POST /staff/benefits: a prepaid package or a voucher of a customer. 422 names the bad field, 404 for an unknown or
 * deleted customer, 409 invalid_state when migration 0010 is not applied. Audit `benefit.create` without the title.
 */
export async function createBenefit(env: Env, body: unknown, staffId: string, now = Date.now()): Promise<CustomerBenefit> {
  if (!isObj(body)) fail('customer_id', 'body must be an object');
  if (typeof body.customer_id !== 'string' || !body.customer_id) fail('customer_id', 'customer_id required');
  if (typeof body.kind !== 'string' || !(BENEFIT_KINDS as string[]).includes(body.kind)) fail('kind', `kind must be one of ${BENEFIT_KINDS.join(', ')}`);
  const title = benefitTitle(body.title);
  const total = body.total_count;
  if (typeof total !== 'number' || !Number.isInteger(total) || total < 1 || total > MAX_BENEFIT_COUNT) fail('total_count', `total_count must be an integer from 1 to ${MAX_BENEFIT_COUNT}`);
  const used = body.used_count === undefined || body.used_count === null ? 0 : usedCount(body.used_count, total);
  const expiresAt = benefitExpiry(body.expires_at);
  let serviceId: string | null = null;
  if (given(body.service_id)) {
    if (typeof body.service_id !== 'string' || !(await activeServiceNames(env)).has(body.service_id)) fail('service_id', 'unknown service_id in the active catalog');
    serviceId = body.service_id;
  }
  await mustCustomer(env, body.customer_id, { inBody: true });

  const row: BenefitRow = {
    id: newId('ben', now),
    customer_id: body.customer_id,
    kind: body.kind as BenefitKind,
    title,
    service_id: serviceId,
    total_count: total,
    used_count: used,
    expires_at: expiresAt,
    status: 'active',
    recorded_by: staffId,
    created_at: now,
    updated_at: now,
  };
  await orConflict0010(
    env.DB.batch([
      env.DB.prepare(`INSERT INTO customer_benefits (${BENEFIT_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
        row.id,
        row.customer_id,
        row.kind,
        row.title,
        row.service_id,
        row.total_count,
        row.used_count,
        row.expires_at,
        row.status,
        row.recorded_by,
        row.created_at,
        row.updated_at,
      ),
      auditStatement(
        env,
        {
          actor_type: 'staff',
          actor_id: staffId,
          action: 'benefit.create',
          entity: 'benefit',
          entity_id: row.id,
          after: { customer_id: row.customer_id, kind: row.kind, service_id: row.service_id, total_count: row.total_count, used_count: row.used_count, expires_at: row.expires_at },
        },
        now,
      ),
    ]),
  );
  return benefitView(row);
}

/**
 * PATCH /staff/benefits/:id with one or more of title, used_count (0 to total_count), expires_at (ms or null) and
 * status ('active' | 'void'). 422 for an unknown field, an empty body or a bad value, 404 for an unknown benefit, 409
 * invalid_state when migration 0010 is not applied. Audit `benefit.update`: the changed values, a title only as a flag.
 */
export async function patchBenefit(env: Env, id: string, body: unknown, staffId: string, now = Date.now()): Promise<CustomerBenefit> {
  if (!id) throw new HttpError(400, 'bad_request', 'benefit id required');
  if (!isObj(body)) fail('body', 'body must be an object');
  const keys = Object.keys(body).filter((k) => body[k] !== undefined);
  const unknown = keys.find((k) => !BENEFIT_PATCH_FIELDS.includes(k));
  if (unknown) fail(unknown, `unknown field ${unknown}`);
  if (!keys.length) fail('body', `nothing to change: send one of ${BENEFIT_PATCH_FIELDS.join(', ')}`);
  const prev = await orConflict0010(env.DB.prepare(`SELECT ${BENEFIT_COLS} FROM customer_benefits WHERE id = ?`).bind(id).first<BenefitRow>());
  if (!prev) throw new HttpError(404, 'not_found', 'benefit not found');

  const next: BenefitRow = { ...prev, updated_at: now };
  if ('title' in body && body.title !== undefined) next.title = benefitTitle(body.title);
  if ('used_count' in body && body.used_count !== undefined) next.used_count = usedCount(body.used_count, prev.total_count);
  if ('expires_at' in body && body.expires_at !== undefined) next.expires_at = benefitExpiry(body.expires_at);
  if ('status' in body && body.status !== undefined) {
    if (typeof body.status !== 'string' || !(BENEFIT_STATUSES as string[]).includes(body.status)) fail('status', `status must be one of ${BENEFIT_STATUSES.join(', ')}`);
    next.status = body.status as BenefitStatus;
  }
  const facts = (r: BenefitRow) => ({ used_count: r.used_count, expires_at: r.expires_at, status: r.status });
  await orConflict0010(
    env.DB.batch([
      env.DB.prepare('UPDATE customer_benefits SET title = ?, used_count = ?, expires_at = ?, status = ?, updated_at = ? WHERE id = ?').bind(
        next.title,
        next.used_count,
        next.expires_at,
        next.status,
        now,
        id,
      ),
      auditStatement(
        env,
        { actor_type: 'staff', actor_id: staffId, action: 'benefit.update', entity: 'benefit', entity_id: id, before: facts(prev), after: { ...facts(next), title_changed: next.title !== prev.title } },
        now,
      ),
    ]),
  );
  return benefitView(next);
}

export const listBenefitsHandler: H = async (c) => c.json({ benefits: await listBenefits(c.env, c.req.query('customer_id')) });

export const createBenefitHandler: H = async (c) => c.json({ benefit: await createBenefit(c.env, await readJson(c), staffId(c)) });

export const patchBenefitHandler: H = async (c) => c.json({ benefit: await patchBenefit(c.env, c.req.param('id') ?? '', await readJson(c), staffId(c)) });

// ---------------------------------------------------------------- phone (section 14.5)

interface CustomerViewRow {
  id: string;
  channel: 'oa' | 'personal';
  zalo_user_id: string;
  display_name: string | null;
  phone: string | null;
  minor_flag: number | null;
  last_user_interaction_at: number | null;
}

/**
 * PATCH /staff/customers/:id with `{ "phone": "0901234567" | null }`. The number is stored as digits (normalizePhone:
 * '+84' becomes '0', 9 to 11 digits), null clears it. 422 for a bad number or a body without `phone`, 404 for an
 * unknown or deleted customer. Audit `customer.phone_edit` says only whether a number is stored. Reads no table or
 * column of migration 0010, so it works before the migration is applied. When a stored number is removed or replaced
 * and migration 0011 is applied, the old number is added to chat_phone_dismissed of the contact (and a pending chat
 * suggestion of it is cleared) in the same batch; without 0011 nothing else changes.
 */
export async function patchCustomerPhone(env: Env, id: string, body: unknown, staffId: string, now = Date.now()): Promise<CustomerView> {
  if (!id) throw new HttpError(400, 'bad_request', 'customer id required');
  if (!isObj(body) || !('phone' in body)) fail('phone', 'body must be an object with a phone');
  const extra = Object.keys(body).find((k) => k !== 'phone');
  if (extra) fail(extra, `unknown field ${extra}`);
  let phone: string | null = null;
  if (body.phone !== null) {
    phone = normalizePhone(body.phone);
    if (!phone) fail('phone', 'phone must be 9 to 11 digits (a leading +84 is read as 0) or null');
  }
  const row = await env.DB.prepare('SELECT id, channel, zalo_user_id, display_name, phone, minor_flag, last_user_interaction_at FROM customers WHERE id = ? AND deleted_at IS NULL')
    .bind(id)
    .first<CustomerViewRow>();
  if (!row) throw new HttpError(404, 'not_found', 'customer not found');
  // Section 15 (review of 2026-11-12): a number staff remove or replace is remembered for the contact, so that the chat
  // analyzer import never writes it back nor suggests it again. Only with migration 0011; the number goes into
  // chat_phone_dismissed, never into the audit row.
  const old = normalizePhone(row.phone);
  const removed = old !== null && old !== phone && ROLE_ID_RE.test(row.zalo_user_id) ? old : null;
  const chat = removed !== null && (await chatTablesPresent(env)) ? phoneRemovedStatements(env, row.zalo_user_id, removed, staffId, now) : [];
  await env.DB.batch([
    env.DB.prepare('UPDATE customers SET phone = ? WHERE id = ?').bind(phone, id),
    auditStatement(
      env,
      { actor_type: 'staff', actor_id: staffId, action: 'customer.phone_edit', entity: 'customer', entity_id: id, before: { has_phone: !!row.phone }, after: { has_phone: phone !== null } },
      now,
    ),
    ...chat,
  ]);
  return {
    id: row.id,
    channel: row.channel,
    zalo_user_id: row.zalo_user_id,
    display_name: row.display_name,
    phone,
    minor_flag: row.minor_flag === null ? null : row.minor_flag === 1,
    last_user_interaction_at: row.last_user_interaction_at,
  };
}

export const patchCustomerHandler: H = async (c) => c.json({ customer: await patchCustomerPhone(c.env, c.req.param('id') ?? '', await readJson(c), staffId(c)) });
