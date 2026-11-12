// Customer facts guessed from old one-to-one Zalo chats (docs/contracts.md section 15, sections 15.9 to 15.12).
//
// scripts/analyze_visits.py reads the synced chat history with rules and pushes, per contact, guessed visits, upcoming
// bookings, packages or vouchers and a phone number to POST /staff/chat-facts/import. The guesses live in the tables
// of migration 0011 (chat_visits, chat_benefits, chat_contact_facts), keyed by zalo_user_id, never in visits or
// customer_benefits: they never become records by themselves. A staff member confirms a guess (a visits or
// customer_benefits row is created, without any follow-up job) or dismisses it (a tombstone, so the next import does
// not bring it back). The summary of a customer (lib/customer-summary.ts) merges the counted guesses through
// mergeChatVisits.
//
// Privacy: a phone number never goes into a log line or an audit row; audit rows carry ids, counts, enum values and
// field names only, never a title, a technician or a service name typed in a chat.
//
// Before migration 0011 is applied (`wrangler dev` reloads changed code before the owner applies the migration) every
// endpoint answers 409 invalid_state naming the migration file, and the summary ignores chat facts.
import type {
  BenefitKind,
  ChatAmountSource,
  ChatBenefitView,
  ChatConfidence,
  ChatFactSource,
  ChatFactState,
  ChatFactsImportResponse,
  ChatFactsView,
  ChatModelPassReason,
  ChatServiceBasis,
  ChatVisitKind,
  ChatVisitView,
  ContactRole,
  CustomerBenefit,
  CustomerView,
  Env,
  VisitView,
} from '../types';
import { auditStatement, type AuditEntry } from './audit';
import {
  MIGRATION_0011,
  chatFactsRemovalStatements,
  chatTablesPresent,
  isMissingMigration0011,
  migration0011Error,
  orMissing0011,
} from './chat-facts-tables';
import { BENEFIT_COLS, benefitView, normalizePhone, type BenefitRow } from './customer-summary';
import { HttpError } from './http';
import { newId } from './ids';
import { QUIET_RELATIONSHIPS, isMissingProfilesTable, loadModelCatalog, type ModelCatalog } from './profiles';
import { ROLE_ID_RE, getContactRoles, isInternalRole, isMissingMigration0010, migration0010Error } from './roles';
import { hhmmToMin, stripMarks } from './text';
import { DAY_MS, HOUR_MS, isValidLocalDate, localDate, localMidnight, localMinuteOfDay } from './time';
import { PERSONAL_OA_ID } from './zalo-personal';
import { MAX_TECHNICIAN_CHARS, isVisitAmount, parseVisitExtras, visitInsertStatement } from '../jobs/followup-jobs';
import { MAX_BENEFIT_COUNT, MAX_BENEFIT_TITLE_CHARS, parseLocalDateTime, serviceSlug } from '../staff-api/customers';

// ---------------------------------------------------------------- limits (section 15.11)

export const MAX_IMPORT_ENTRIES = 100;
export const MAX_ENTRY_VISITS = 400;
export const MAX_ENTRY_UPCOMING = 50;
export const MAX_ENTRY_BENEFITS = 5;
export const MAX_IMPORT_BYTES = 16_000_000;
const MAX_VISIT_SERVICES = 3;
const MAX_SIGNALS = 20;
const MAX_EVIDENCE = 5;
const MIN_CHAT_AMOUNT = 1_000;
const MAX_CHAT_AMOUNT = 50_000_000;
const MAX_CHAT_TITLE = 120;
const MAX_CHAT_COUNT = 200;
const MAX_COUNT_MESSAGES = 10_000_000;
const ANALYZER_VERSION_RE = /^[A-Za-z0-9._:+-]{1,40}$/;
const SIGNAL_RE = /^[a-z0-9_]{1,40}$/;
const SERVICE_ID_RE = /^[a-z0-9_-]{1,64}$/;
/** The analyzer's normalised mobile number: '0' and 9 digits. */
const PHONE_RE = /^0\d{9}$/;
/** A technician with a run of 3 or more digits (a phone number, an account number) never reaches the model. */
export const TECHNICIAN_DIGITS_RE = /\d{3,}/;
/** Statements per D1 batch of an import. */
const IMPORT_CHUNK = 500;
/** Values per `IN (...)` list (D1 allows 100 bound parameters per statement). */
const IN_CHUNK = 90;

const VISIT_KINDS: ChatVisitKind[] = ['visit', 'upcoming'];
const CONFIDENCES: ChatConfidence[] = ['high', 'medium', 'low'];
const AMOUNT_SOURCES: ChatAmountSource[] = ['paid', 'quoted', 'list_price'];
const FACT_SOURCES: ChatFactSource[] = ['chat_rules', 'chat_model', 'chat_rules+model'];
const BASES: ChatServiceBasis[] = ['booking', 'visit_day', 'window'];
const MODEL_PASS_REASONS: ChatModelPassReason[] = ['disabled', 'not_in_scope', 'no_candidate_window', 'call_cap', 'no_account', 'error', 'ok'];
const BENEFIT_KINDS: BenefitKind[] = ['package', 'voucher'];

// ---------------------------------------------------------------- missing migration 0011

// The detection lives in lib/chat-facts-tables.ts so that the role writes and the phone edit can use it too.
export { MIGRATION_0011, chatFactsRemovalStatements, isMissingMigration0011, migration0011Error, orMissing0011 };

/** Awaits `p`; a missing migration 0011 (or 0010, whose tables the endpoints also read) becomes 409 invalid_state. */
export async function orConflict0011<T>(p: Promise<T>): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingMigration0011(e)) throw migration0011Error();
    if (isMissingMigration0010(e)) throw migration0010Error();
    throw e;
  }
}

/** Throws 409 invalid_state when migration 0011 is not applied. */
async function require0011(env: Env): Promise<void> {
  if (!(await chatTablesPresent(env))) throw migration0011Error();
}

// ---------------------------------------------------------------- small helpers

function fail(field: string, message: string): never {
  throw new HttpError(422, 'validation_failed', message, { field });
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v);
const isMs = (v: unknown): v is number => isInt(v) && v >= 0;
const absent = (v: unknown): boolean => v === undefined || v === null;
const chars = (s: string) => [...s].length;

function oneOf<T extends string>(v: unknown, allowed: T[], field: string): T {
  if (typeof v !== 'string' || !(allowed as string[]).includes(v)) fail(field, `${field} must be one of ${allowed.join(', ')}`);
  return v as T;
}

/** A one-line text of at most `max` characters; null for null / absent / blank. */
function optionalLine(v: unknown, max: number, field: string): string | null {
  if (absent(v)) return null;
  if (typeof v !== 'string' || /[\r\n]/.test(v) || chars(v.trim()) > max) fail(field, `${field} must be one line of at most ${max} characters, or null`);
  return v.normalize('NFC').trim() || null;
}

function inChunks<T>(list: T[], size = IN_CHUNK): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

const marks = (n: number) => Array.from({ length: n }, () => '?').join(',');

const hhmm = (ms: number): string => {
  const m = localMinuteOfDay(ms);
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
};

/** The identity of a benefit across analyzer runs: accent-folded, lower case, spaces collapsed. Pure. */
export function benefitTitleKey(title: string): string {
  return stripMarks(title).replace(/\s+/g, ' ').trim();
}

/** An audit row written only when `EXISTS (guard.sql)` holds when the statement runs (same columns as auditStatement). */
function guardedAuditStatement(env: Env, e: AuditEntry, at: number, guard: { sql: string; binds: unknown[] }): D1PreparedStatement {
  return env.DB.prepare(
    `INSERT INTO audit_log (at, actor_type, actor_id, action, entity, entity_id, before_json, after_json, request_id) SELECT ?,?,?,?,?,?,?,?,? WHERE EXISTS (${guard.sql})`,
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
    ...guard.binds,
  );
}

// ---------------------------------------------------------------- rows

export interface ChatVisitRow {
  id: string;
  zalo_user_id: string;
  local_date: string;
  kind: ChatVisitKind;
  visited_at: number;
  time_known: number;
  services_json: string;
  amount_vnd: number | null;
  amount_source: ChatAmountSource | null;
  technician: string | null;
  confidence: ChatConfidence | null;
  signals_json: string;
  evidence_json: string;
  fact_source: ChatFactSource;
  state: ChatFactState;
  confirmed_visit_id: string | null;
  analyzer_version: string;
  imported_at: number;
  decided_by: string | null;
  decided_at: number | null;
}

export interface ChatBenefitRow {
  id: string;
  zalo_user_id: string;
  kind: BenefitKind;
  title: string;
  title_key: string;
  service_id: string | null;
  total_count: number | null;
  remaining: number | null;
  stated_by: 'owner' | 'contact';
  confidence: 'high' | 'medium';
  stated_at: number;
  state: ChatFactState;
  confirmed_benefit_id: string | null;
  analyzer_version: string;
  imported_at: number;
  decided_by: string | null;
  decided_at: number | null;
}

export interface ChatContactFactsRow {
  zalo_user_id: string;
  analyzer_version: string;
  generated_at: number;
  imported_at: number;
  messages: number;
  first_at: number | null;
  last_at: number | null;
  phone_suggestion: string | null;
  phone_state: 'dismissed' | null;
  phone_dismissed: string | null;
  model_pass_json: string;
}

const CHAT_VISIT_COLS =
  'id, zalo_user_id, local_date, kind, visited_at, time_known, services_json, amount_vnd, amount_source, technician, confidence, signals_json, evidence_json, ' +
  'fact_source, state, confirmed_visit_id, analyzer_version, imported_at, decided_by, decided_at';
const CHAT_BENEFIT_COLS =
  'id, zalo_user_id, kind, title, title_key, service_id, total_count, remaining, stated_by, confidence, stated_at, state, confirmed_benefit_id, analyzer_version, ' +
  'imported_at, decided_by, decided_at';
const CHAT_FACTS_COLS = 'zalo_user_id, analyzer_version, generated_at, imported_at, messages, first_at, last_at, phone_suggestion, phone_state, phone_dismissed, model_pass_json';

function parseJson<T>(s: string | null | undefined, fallback: T): T {
  if (!s) return fallback;
  try {
    return JSON.parse(s) as T;
  } catch {
    return fallback;
  }
}

interface StoredService {
  service_id: string | null;
  service_name: string | null;
  basis: ChatServiceBasis;
}

// ---------------------------------------------------------------- import document (section 15.4)

interface ParsedVisit {
  kind: ChatVisitKind;
  local_date: string;
  visited_at: number;
  time_known: 0 | 1;
  services_json: string;
  amount_vnd: number | null;
  amount_source: ChatAmountSource | null;
  technician: string | null;
  confidence: ChatConfidence | null;
  signals_json: string;
  evidence_json: string;
  fact_source: ChatFactSource;
}

interface ParsedBenefit {
  kind: BenefitKind;
  title: string;
  title_key: string;
  service_id: string | null;
  total_count: number | null;
  remaining: number | null;
  stated_by: 'owner' | 'contact';
  confidence: 'high' | 'medium';
  stated_at: number;
}

interface ParsedEntry {
  zalo_user_id: string;
  messages: number;
  first_at: number | null;
  last_at: number | null;
  visits: ParsedVisit[]; // both kinds
  benefits: ParsedBenefit[];
  phone: { value: string; confidence: 'high' | 'medium' } | null;
  model_pass_json: string;
}

interface ParsedDocument {
  analyzer_version: string;
  generated_at: number;
  dry_run: boolean;
  customers: ParsedEntry[];
}

function parseCandidate(v: unknown, f: string, kind: ChatVisitKind): ParsedVisit {
  if (!isObj(v)) fail(f, `${f} must be an object`);
  if (typeof v.date !== 'string' || !isValidLocalDate(v.date)) fail(`${f}.date`, "date must be a real date 'YYYY-MM-DD'");
  let time: string | null = null;
  if (!absent(v.time)) {
    if (typeof v.time !== 'string' || !/^\d{2}:\d{2}$/.test(v.time) || hhmmToMin(v.time) === null) fail(`${f}.time`, "time must be 'HH:MM' (00:00 to 23:59) or null");
    time = v.time;
  }
  if (typeof v.time_known !== 'boolean') fail(`${f}.time_known`, 'time_known must be true or false');
  if (v.time_known !== (time !== null)) fail(`${f}.time_known`, 'time_known must be true exactly when time is given');
  const local = `${v.date} ${time ?? '12:00'}`;
  const visitedAt = parseLocalDateTime(local);
  if (visitedAt === null) fail(`${f}.date`, 'date and time do not make a local time');
  if (!absent(v.visited_at_local) && (typeof v.visited_at_local !== 'string' || parseLocalDateTime(v.visited_at_local) !== visitedAt)) {
    fail(`${f}.visited_at_local`, 'visited_at_local must be the date with the time (12:00 when the time is unknown)');
  }

  const services = v.services ?? [];
  if (!Array.isArray(services)) fail(`${f}.services`, 'services must be an array');
  if (services.length > MAX_VISIT_SERVICES) fail(`${f}.services`, `at most ${MAX_VISIT_SERVICES} services`);
  const stored: StoredService[] = services.map((s, k) => {
    const sf = `${f}.services[${k}]`;
    if (!isObj(s)) fail(sf, `${sf} must be an object`);
    if (!absent(s.service_id) && (typeof s.service_id !== 'string' || !SERVICE_ID_RE.test(s.service_id))) fail(`${sf}.service_id`, 'service_id must be a catalog id or null');
    const serviceId = absent(s.service_id) ? null : (s.service_id as string);
    const serviceName = optionalLine(s.service_name, MAX_CHAT_TITLE, `${sf}.service_name`);
    if (serviceId === null && serviceName === null) fail(`${sf}.service_id`, 'a service needs a service_id or a service_name');
    return { service_id: serviceId, service_name: serviceName, basis: oneOf(s.basis, BASES, `${sf}.basis`) };
  });

  let amount: number | null = null;
  if (!absent(v.amount_vnd)) {
    if (!isInt(v.amount_vnd) || v.amount_vnd < MIN_CHAT_AMOUNT || v.amount_vnd > MAX_CHAT_AMOUNT) fail(`${f}.amount_vnd`, `amount_vnd must be an integer from ${MIN_CHAT_AMOUNT} to ${MAX_CHAT_AMOUNT}, or null`);
    amount = v.amount_vnd;
  }
  const amountSource = absent(v.amount_source) ? null : oneOf(v.amount_source, AMOUNT_SOURCES, `${f}.amount_source`);
  const technician = optionalLine(v.technician, MAX_TECHNICIAN_CHARS, `${f}.technician`);
  // An upcoming booking has no confidence (the analyzer omits it): a value sent anyway is not stored.
  const confidence = kind === 'visit' ? oneOf(v.confidence, CONFIDENCES, `${f}.confidence`) : null;

  const signals = v.signals ?? [];
  if (!Array.isArray(signals) || signals.length > MAX_SIGNALS || signals.some((x) => typeof x !== 'string' || !SIGNAL_RE.test(x))) {
    fail(`${f}.signals`, `signals must be at most ${MAX_SIGNALS} codes [a-z0-9_]`);
  }
  const evidence = v.evidence_at ?? [];
  if (!Array.isArray(evidence) || evidence.length > MAX_EVIDENCE || evidence.some((x) => !isMs(x))) fail(`${f}.evidence_at`, `evidence_at must be at most ${MAX_EVIDENCE} times in ms`);
  return {
    kind,
    local_date: v.date,
    visited_at: visitedAt,
    time_known: time === null ? 0 : 1,
    services_json: JSON.stringify(stored),
    amount_vnd: amount,
    amount_source: amountSource,
    technician,
    confidence,
    signals_json: JSON.stringify(signals),
    evidence_json: JSON.stringify(evidence),
    fact_source: oneOf(v.source, FACT_SOURCES, `${f}.source`),
  };
}

function parseCandidates(v: unknown, f: string, kind: ChatVisitKind, max: number): ParsedVisit[] {
  const list = v ?? [];
  if (!Array.isArray(list)) fail(f, `${f} must be an array`);
  if (list.length > max) fail(f, `${f} has more than ${max} entries`);
  const seen = new Set<string>();
  return list.map((c, j) => {
    const p = parseCandidate(c, `${f}[${j}]`, kind);
    if (seen.has(p.local_date)) fail(`${f}[${j}].date`, 'two entries on the same date');
    seen.add(p.local_date);
    return p;
  });
}

function parseBenefit(b: unknown, f: string): ParsedBenefit {
  if (!isObj(b)) fail(f, `${f} must be an object`);
  const kind = oneOf(b.kind, BENEFIT_KINDS, `${f}.kind`);
  const title = optionalLine(b.title, MAX_CHAT_TITLE, `${f}.title`);
  if (title === null) fail(`${f}.title`, `title must be one line of 1 to ${MAX_CHAT_TITLE} characters`);
  if (!absent(b.service_id) && (typeof b.service_id !== 'string' || !SERVICE_ID_RE.test(b.service_id))) fail(`${f}.service_id`, 'service_id must be a catalog id or null');
  let total: number | null = null;
  if (!absent(b.total_count)) {
    if (!isInt(b.total_count) || b.total_count < 1 || b.total_count > MAX_CHAT_COUNT) fail(`${f}.total_count`, `total_count must be an integer from 1 to ${MAX_CHAT_COUNT}, or null`);
    total = b.total_count;
  }
  let remaining: number | null = null;
  if (!absent(b.remaining)) {
    if (!isInt(b.remaining) || b.remaining < 0 || b.remaining > MAX_CHAT_COUNT) fail(`${f}.remaining`, `remaining must be an integer from 0 to ${MAX_CHAT_COUNT}, or null`);
    if (total !== null && b.remaining > total) fail(`${f}.remaining`, 'remaining must not be above total_count');
    remaining = b.remaining;
  }
  if (!isMs(b.at)) fail(`${f}.at`, 'at must be a time in ms');
  return {
    kind,
    title,
    title_key: benefitTitleKey(title),
    service_id: absent(b.service_id) ? null : (b.service_id as string),
    total_count: total,
    remaining,
    stated_by: oneOf(b.stated_by, ['owner', 'contact'] as Array<'owner' | 'contact'>, `${f}.stated_by`),
    confidence: oneOf(b.confidence, ['high', 'medium'] as Array<'high' | 'medium'>, `${f}.confidence`),
    stated_at: b.at,
  };
}

function parseEntry(e: unknown, i: number): ParsedEntry {
  const f = `customers[${i}]`;
  if (!isObj(e)) fail(f, `${f} must be an object`);
  if (typeof e.zalo_user_id !== 'string' || !ROLE_ID_RE.test(e.zalo_user_id)) fail(`${f}.zalo_user_id`, "zalo_user_id must be 'p:' + 1 to 32 digits");
  if (!isInt(e.messages) || e.messages < 0 || e.messages > MAX_COUNT_MESSAGES) fail(`${f}.messages`, 'messages must be a count');
  for (const k of ['first_at', 'last_at'] as const) if (!absent(e[k]) && !isMs(e[k])) fail(`${f}.${k}`, `${k} must be a time in ms or null`);

  const visits = parseCandidates(e.visits, `${f}.visits`, 'visit', MAX_ENTRY_VISITS);
  const upcoming = parseCandidates(e.upcoming, `${f}.upcoming`, 'upcoming', MAX_ENTRY_UPCOMING);

  const rawBenefits = e.benefits ?? [];
  if (!Array.isArray(rawBenefits)) fail(`${f}.benefits`, 'benefits must be an array');
  if (rawBenefits.length > MAX_ENTRY_BENEFITS) fail(`${f}.benefits`, `${f}.benefits has more than ${MAX_ENTRY_BENEFITS} entries`);
  // Two titles that fold to the same key are one benefit for the server: the latest statement wins (15.4).
  const byKey = new Map<string, ParsedBenefit>();
  rawBenefits.forEach((b, j) => {
    const p = parseBenefit(b, `${f}.benefits[${j}]`);
    const prev = byKey.get(p.title_key);
    if (!prev || p.stated_at >= prev.stated_at) byKey.set(p.title_key, p);
  });

  let phone: ParsedEntry['phone'] = null;
  if (!absent(e.phone)) {
    const p = e.phone;
    if (!isObj(p)) fail(`${f}.phone`, 'phone must be an object or null');
    const value = normalizePhone(p.value);
    if (!value || !PHONE_RE.test(value)) fail(`${f}.phone.value`, 'value must be a mobile number of 10 digits');
    const confidence = oneOf(p.confidence, ['high', 'medium'] as Array<'high' | 'medium'>, `${f}.phone.confidence`);
    if (!absent(p.source)) oneOf(p.source, ['chat', 'zalo_contact'], `${f}.phone.source`);
    if (!absent(p.at) && !isMs(p.at)) fail(`${f}.phone.at`, 'at must be a time in ms or null');
    phone = { value, confidence };
  }

  const mp = e.model_pass;
  if (!isObj(mp)) fail(`${f}.model_pass`, 'model_pass must be an object {ran, reason}');
  if (typeof mp.ran !== 'boolean') fail(`${f}.model_pass.ran`, 'ran must be true or false');
  const reason = oneOf(mp.reason, MODEL_PASS_REASONS, `${f}.model_pass.reason`);
  return {
    zalo_user_id: e.zalo_user_id,
    messages: e.messages,
    first_at: absent(e.first_at) ? null : (e.first_at as number),
    last_at: absent(e.last_at) ? null : (e.last_at as number),
    visits: [...visits, ...upcoming],
    benefits: [...byKey.values()],
    phone,
    model_pass_json: JSON.stringify({ ran: mp.ran, reason }),
  };
}

/**
 * Validates the whole import document (section 15.4 entries, limits of 15.11). Any problem answers 422
 * validation_failed for the whole body; `details.field` names the path (`customers[3].visits[0].date`). Pure.
 */
export function parseImportDocument(body: unknown): ParsedDocument {
  if (!isObj(body)) fail('customers', 'body must be an object with a customers array');
  if (typeof body.analyzer_version !== 'string' || !ANALYZER_VERSION_RE.test(body.analyzer_version)) fail('analyzer_version', 'analyzer_version must be 1 to 40 characters of [A-Za-z0-9._:+-]');
  if (!isMs(body.generated_at) || body.generated_at === 0) fail('generated_at', 'generated_at must be a time in ms');
  if (body.dry_run !== undefined && typeof body.dry_run !== 'boolean') fail('dry_run', 'dry_run must be true or false');
  const list = body.customers;
  if (!Array.isArray(list)) fail('customers', 'customers must be an array');
  if (list.length < 1 || list.length > MAX_IMPORT_ENTRIES) fail('customers', `customers must have 1 to ${MAX_IMPORT_ENTRIES} entries`);
  const customers = list.map((e, i) => parseEntry(e, i));
  const seen = new Set<string>();
  customers.forEach((c, i) => {
    if (seen.has(c.zalo_user_id)) fail(`customers[${i}].zalo_user_id`, 'duplicate zalo_user_id in this request');
    seen.add(c.zalo_user_id);
  });
  return { analyzer_version: body.analyzer_version, generated_at: body.generated_at, dry_run: body.dry_run === true, customers };
}

// ---------------------------------------------------------------- import (section 15.11 steps 1 to 6)

interface CustomerRef {
  id: string;
  zalo_user_id: string;
  phone: string | null;
  deleted_at: number | null;
}

interface Stored {
  visits: ChatVisitRow[];
  benefits: ChatBenefitRow[];
  facts: ChatContactFactsRow | null;
  /** chat_phone_dismissed: every number staff dismissed as a suggestion or removed from customers.phone */
  dismissedPhones: Set<string>;
}

async function loadStored(env: Env, ids: string[]): Promise<Map<string, Stored>> {
  const out = new Map<string, Stored>(ids.map((id) => [id, { visits: [], benefits: [], facts: null, dismissedPhones: new Set<string>() }]));
  for (const chunk of inChunks(ids)) {
    const [v, b, f, d] = await orConflict0011(
      env.DB.batch([
        env.DB.prepare(`SELECT ${CHAT_VISIT_COLS} FROM chat_visits WHERE zalo_user_id IN (${marks(chunk.length)})`).bind(...chunk),
        env.DB.prepare(`SELECT ${CHAT_BENEFIT_COLS} FROM chat_benefits WHERE zalo_user_id IN (${marks(chunk.length)})`).bind(...chunk),
        env.DB.prepare(`SELECT ${CHAT_FACTS_COLS} FROM chat_contact_facts WHERE zalo_user_id IN (${marks(chunk.length)})`).bind(...chunk),
        env.DB.prepare(`SELECT zalo_user_id, phone FROM chat_phone_dismissed WHERE zalo_user_id IN (${marks(chunk.length)})`).bind(...chunk),
      ]),
    );
    for (const r of v!.results as unknown as ChatVisitRow[]) out.get(r.zalo_user_id)?.visits.push(r);
    for (const r of b!.results as unknown as ChatBenefitRow[]) out.get(r.zalo_user_id)?.benefits.push(r);
    for (const r of f!.results as unknown as ChatContactFactsRow[]) {
      const s = out.get(r.zalo_user_id);
      if (s) s.facts = r;
    }
    for (const r of d!.results as unknown as Array<{ zalo_user_id: string; phone: string }>) out.get(r.zalo_user_id)?.dismissedPhones.add(r.phone);
  }
  return out;
}

/**
 * normalised phone number -> ids of the customers rows (not deleted) that hold it, over every customer. The import and
 * the phone accept never give a contact a number another customer already has (section 15.11 step 5).
 */
async function loadPhoneOwners(env: Env): Promise<Map<string, Set<string>>> {
  const { results } = await env.DB.prepare("SELECT id, phone FROM customers WHERE deleted_at IS NULL AND phone IS NOT NULL AND TRIM(phone) != ''").all<{
    id: string;
    phone: string;
  }>();
  const out = new Map<string, Set<string>>();
  for (const r of results) {
    const p = normalizePhone(r.phone);
    if (!p) continue;
    let s = out.get(p);
    if (!s) out.set(p, (s = new Set()));
    s.add(r.id);
  }
  return out;
}

/** Whether a customer other than `ownId` (null: the contact has no customers row) holds `phone`. */
const heldByOther = (owners: Map<string, Set<string>>, phone: string, ownId: string | null): boolean => [...(owners.get(phone) ?? [])].some((id) => id !== ownId);

/** Profile relationships of several contacts; an empty map before migration 0007. */
async function loadRelationships(env: Env, ids: string[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  for (const chunk of inChunks(ids)) {
    try {
      const { results } = await env.DB.prepare(`SELECT zalo_user_id, relationship FROM customer_profiles WHERE zalo_user_id IN (${marks(chunk.length)})`)
        .bind(...chunk)
        .all<{ zalo_user_id: string; relationship: string }>();
      for (const r of results) out.set(r.zalo_user_id, r.relationship);
    } catch (e) {
      if (isMissingProfilesTable(e)) return new Map();
      throw e;
    }
  }
  return out;
}

async function loadCustomers(env: Env, ids: string[]): Promise<Map<string, CustomerRef>> {
  const out = new Map<string, CustomerRef>();
  for (const chunk of inChunks(ids)) {
    const { results } = await env.DB.prepare(`SELECT id, zalo_user_id, phone, deleted_at FROM customers WHERE oa_id = ? AND zalo_user_id IN (${marks(chunk.length)})`)
      .bind(PERSONAL_OA_ID, ...chunk)
      .all<CustomerRef>();
    for (const r of results) out.set(r.zalo_user_id, r);
  }
  return out;
}

/** customer id -> the local dates of its recorded visits (any source). */
async function loadVisitDays(env: Env, customerIds: string[]): Promise<Map<string, Set<string>>> {
  const out = new Map<string, Set<string>>();
  for (const chunk of inChunks(customerIds)) {
    const { results } = await env.DB.prepare(`SELECT customer_id, visited_at FROM visits WHERE customer_id IN (${marks(chunk.length)})`)
      .bind(...chunk)
      .all<{ customer_id: string; visited_at: number }>();
    for (const r of results) {
      let s = out.get(r.customer_id);
      if (!s) out.set(r.customer_id, (s = new Set()));
      s.add(localDate(r.visited_at));
    }
  }
  return out;
}

/**
 * Whether a contact is internal for the import (section 15.11 step 2): a contact_roles row manager or staff, or, with
 * no role row 'customer', a section 13 relationship family, friend, personal or staff. A role 'customer' overrides the
 * analyzer's relationship, as everywhere else (section 14.3). Pure.
 */
export function internalForChatFacts(role: ContactRole | null | undefined, relationship: string | null | undefined): boolean {
  if (isInternalRole(role)) return true;
  if (role === 'customer') return false;
  return !!relationship && (QUIET_RELATIONSHIPS as string[]).includes(relationship);
}

const VISIT_INSERT =
  'INSERT INTO chat_visits (id, zalo_user_id, local_date, kind, visited_at, time_known, services_json, amount_vnd, amount_source, technician, confidence, ' +
  "signals_json, evidence_json, fact_source, state, analyzer_version, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?) " +
  'ON CONFLICT(zalo_user_id, local_date, kind) DO NOTHING';
const VISIT_UPDATE =
  'UPDATE chat_visits SET visited_at = ?, time_known = ?, services_json = ?, amount_vnd = ?, amount_source = ?, technician = ?, confidence = ?, ' +
  "signals_json = ?, evidence_json = ?, fact_source = ?, analyzer_version = ?, imported_at = ? WHERE id = ? AND state = 'active'";
const BENEFIT_INSERT =
  'INSERT INTO chat_benefits (id, zalo_user_id, kind, title, title_key, service_id, total_count, remaining, stated_by, confidence, stated_at, state, ' +
  "analyzer_version, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?) ON CONFLICT(zalo_user_id, title_key) DO NOTHING";
const BENEFIT_UPDATE =
  'UPDATE chat_benefits SET kind = ?, title = ?, service_id = ?, total_count = ?, remaining = ?, stated_by = ?, confidence = ?, stated_at = ?, ' +
  "analyzer_version = ?, imported_at = ? WHERE id = ? AND state = 'active'";
// phone_state, phone_dismissed and phone_decision_id are kept. The suggestion is written as NULL when, by the time the
// statement runs, staff dismissed that number or the contact's customers row has a phone (a staff accept or phone edit
// between the import's read and this write).
const FACTS_UPSERT =
  'INSERT INTO chat_contact_facts (zalo_user_id, analyzer_version, generated_at, imported_at, messages, first_at, last_at, phone_suggestion, model_pass_json) ' +
  'VALUES (?,?,?,?,?,?,?, CASE WHEN ? IS NULL THEN NULL ' +
  'WHEN EXISTS (SELECT 1 FROM chat_phone_dismissed d WHERE d.zalo_user_id = ? AND d.phone = ?) THEN NULL ' +
  "WHEN EXISTS (SELECT 1 FROM customers cu WHERE cu.oa_id = ? AND cu.zalo_user_id = ? AND cu.deleted_at IS NULL AND cu.phone IS NOT NULL AND TRIM(cu.phone) != '') THEN NULL " +
  'ELSE ? END, ?) ON CONFLICT(zalo_user_id) DO UPDATE SET analyzer_version = excluded.analyzer_version, generated_at = excluded.generated_at, ' +
  'imported_at = excluded.imported_at, messages = excluded.messages, first_at = excluded.first_at, last_at = excluded.last_at, ' +
  'phone_suggestion = excluded.phone_suggestion, model_pass_json = excluded.model_pass_json';
// customers.phone is set only while it is empty and no other customer holds the same number.
const PHONE_SET =
  "UPDATE customers SET phone = ? WHERE id = ? AND (phone IS NULL OR TRIM(phone) = '') " +
  'AND NOT EXISTS (SELECT 1 FROM customers o WHERE o.id != ? AND o.deleted_at IS NULL AND o.phone = ?)';

/** The counters of an import whose value, after a real (not dry) run, is the number of rows the statements changed. */
type WriteCounter = 'visits_imported' | 'visits_updated' | 'visits_removed' | 'benefits_upserted' | 'phones_set';
const WRITE_COUNTERS: WriteCounter[] = ['visits_imported', 'visits_updated', 'visits_removed', 'benefits_upserted', 'phones_set'];

function visitDiffers(r: ChatVisitRow, v: ParsedVisit, version: string): boolean {
  return (
    r.visited_at !== v.visited_at ||
    r.time_known !== v.time_known ||
    r.services_json !== v.services_json ||
    r.amount_vnd !== v.amount_vnd ||
    r.amount_source !== v.amount_source ||
    r.technician !== v.technician ||
    r.confidence !== v.confidence ||
    r.signals_json !== v.signals_json ||
    r.evidence_json !== v.evidence_json ||
    r.fact_source !== v.fact_source ||
    r.analyzer_version !== version
  );
}

function benefitDiffers(r: ChatBenefitRow, b: ParsedBenefit, version: string): boolean {
  return (
    r.kind !== b.kind ||
    r.title !== b.title ||
    r.service_id !== b.service_id ||
    r.total_count !== b.total_count ||
    r.remaining !== b.remaining ||
    r.stated_by !== b.stated_by ||
    r.confidence !== b.confidence ||
    r.stated_at !== b.stated_at ||
    r.analyzer_version !== version
  );
}

/**
 * POST /staff/chat-facts/import (section 15.11). The document is validated first (422 for the whole body). Then, per
 * entry, in order: a contact whose customers row is deleted is skipped and its chat rows are removed
 * (`skipped_deleted`, additive); an internal contact is skipped and loses its active rows (`skipped_internal`); visits
 * and upcoming bookings, benefits and the phone number follow the rules of 15.11; the contact's chat_contact_facts row
 * is written when one of its values changed. Every rule is idempotent: the same document a second time writes nothing
 * and counts nothing but `customers` and `unmatched`.
 *
 * Rules added after review (2026-11-12), beyond the text of 15.11:
 *  - a dismissed upcoming booking is also a tombstone for a visit guess on the same date (`visits_tombstoned`): the
 *    analyzer reads a past booking as a visit, and staff already said that booking is wrong;
 *  - a phone number is neither set nor suggested when staff dismissed it before (every dismissed number is kept in
 *    chat_phone_dismissed), when staff removed or replaced it in customers.phone, or when another customers row holds
 *    it (`phones_taken`, additive).
 *
 * `dry_run: true` computes every counter and writes nothing. Otherwise the statements go in D1 batches of at most 500,
 * then the audit row `chat_facts.import` (the counters and the analyzer version only); a failure leaves earlier batches
 * written and a re-run converges. After a real run, `visits_imported`, `visits_updated`, `visits_removed`,
 * `benefits_upserted` and `phones_set` are the rows the statements changed (a staff decision between the import's read
 * and its write makes them smaller than planned); the other counters are what the import decided. 409 invalid_state
 * when migration 0011 is not applied, also for a dry run.
 */
export async function importChatFacts(env: Env, body: unknown, staffId: string, now = Date.now()): Promise<ChatFactsImportResponse> {
  const doc = parseImportDocument(body);
  const ids = doc.customers.map((c) => c.zalo_user_id);
  // The tables of 0011 are read first, so that a dry run answers 409 too.
  const stored = await loadStored(env, ids);
  const [roles, relationships, customers] = await Promise.all([getContactRoles(env, ids), loadRelationships(env, ids), loadCustomers(env, ids)]);
  const visitDays = await loadVisitDays(env, [...customers.values()].filter((c) => c.deleted_at === null).map((c) => c.id));
  const owners = doc.customers.some((c) => c.phone) ? await loadPhoneOwners(env) : new Map<string, Set<string>>();
  const version = doc.analyzer_version;

  const res: ChatFactsImportResponse = {
    customers: 0,
    unmatched: 0,
    skipped_internal: 0,
    skipped_deleted: 0,
    visits_imported: 0,
    visits_updated: 0,
    visits_removed: 0,
    visits_kept_staff: 0,
    visits_tombstoned: 0,
    phones_set: 0,
    phones_taken: 0,
    phone_suggestions: 0,
    benefits_upserted: 0,
    benefits_kept_staff: 0,
    dry_run: doc.dry_run,
  };
  const stmts: Array<{ s: D1PreparedStatement; counts?: WriteCounter }> = [];
  const add = (s: D1PreparedStatement, counts?: WriteCounter) => stmts.push({ s, counts });

  for (const entry of doc.customers) {
    const id = entry.zalo_user_id;
    const st = stored.get(id)!;
    const cu = customers.get(id) ?? null;

    // A removed customer gets no new guesses, and the old ones go too (section 15.11 "Removal").
    if (cu && cu.deleted_at !== null) {
      res.skipped_deleted += 1;
      if (st.visits.length || st.benefits.length || st.facts || st.dismissedPhones.size) for (const s of chatFactsRemovalStatements(env, id)) add(s);
      continue;
    }
    // Step 2: a contact who is (or became) staff, family or a friend loses the guesses nobody decided on.
    if (internalForChatFacts(roles.get(id)?.role, relationships.get(id))) {
      res.skipped_internal += 1;
      if (st.visits.some((r) => r.state === 'active')) add(env.DB.prepare("DELETE FROM chat_visits WHERE zalo_user_id = ? AND state = 'active'").bind(id));
      if (st.benefits.some((r) => r.state === 'active')) add(env.DB.prepare("DELETE FROM chat_benefits WHERE zalo_user_id = ? AND state = 'active'").bind(id));
      if (st.facts?.phone_suggestion) add(env.DB.prepare('UPDATE chat_contact_facts SET phone_suggestion = NULL WHERE zalo_user_id = ?').bind(id));
      continue;
    }
    res.customers += 1;
    if (!cu) res.unmatched += 1;

    // Step 3: visits and upcoming bookings. The analyzer owns the active rows; staff own confirmed and dismissed ones.
    const days = cu ? visitDays.get(cu.id) : undefined;
    const byKey = new Map(st.visits.map((r) => [`${r.kind}|${r.local_date}`, r]));
    const sent = new Set<string>();
    for (const v of entry.visits) {
      const key = `${v.kind}|${v.local_date}`;
      const row = byKey.get(key);
      // A booking staff dismissed is no visit either once its date has passed.
      const bookingDismissed = v.kind === 'visit' && byKey.get(`upcoming|${v.local_date}`)?.state === 'dismissed';
      if (bookingDismissed && row?.state !== 'confirmed') {
        // an active row of that date (written before the booking was dismissed) is removed below as not sent
        res.visits_tombstoned += 1;
        continue;
      }
      sent.add(key);
      if (row?.state === 'dismissed') {
        res.visits_tombstoned += 1;
        continue;
      }
      if (row?.state === 'confirmed' || days?.has(v.local_date)) {
        res.visits_kept_staff += 1;
        continue;
      }
      if (row) {
        if (visitDiffers(row, v, version)) {
          res.visits_updated += 1;
          add(
            env.DB.prepare(VISIT_UPDATE).bind(
              v.visited_at,
              v.time_known,
              v.services_json,
              v.amount_vnd,
              v.amount_source,
              v.technician,
              v.confidence,
              v.signals_json,
              v.evidence_json,
              v.fact_source,
              version,
              now,
              row.id,
            ),
            'visits_updated',
          );
        }
        continue;
      }
      res.visits_imported += 1;
      add(
        env.DB.prepare(VISIT_INSERT).bind(
          newId('chv', now),
          id,
          v.local_date,
          v.kind,
          v.visited_at,
          v.time_known,
          v.services_json,
          v.amount_vnd,
          v.amount_source,
          v.technician,
          v.confidence,
          v.signals_json,
          v.evidence_json,
          v.fact_source,
          version,
          now,
        ),
        'visits_imported',
      );
    }
    // An upcoming booking whose date has passed goes the same way once the analyzer no longer sends it.
    const staleVisits = st.visits.filter((r) => r.state === 'active' && !sent.has(`${r.kind}|${r.local_date}`)).map((r) => r.id);
    res.visits_removed += staleVisits.length;
    for (const chunk of inChunks(staleVisits)) add(env.DB.prepare(`DELETE FROM chat_visits WHERE state = 'active' AND id IN (${marks(chunk.length)})`).bind(...chunk), 'visits_removed');

    // Step 4: benefits, matched by title_key, same rules.
    const byTitle = new Map(st.benefits.map((r) => [r.title_key, r]));
    const titles = new Set<string>();
    for (const b of entry.benefits) {
      titles.add(b.title_key);
      const row = byTitle.get(b.title_key);
      if (row?.state === 'dismissed') continue;
      if (row?.state === 'confirmed') {
        res.benefits_kept_staff += 1;
        continue;
      }
      if (row) {
        if (benefitDiffers(row, b, version)) {
          res.benefits_upserted += 1;
          add(
            env.DB.prepare(BENEFIT_UPDATE).bind(b.kind, b.title, b.service_id, b.total_count, b.remaining, b.stated_by, b.confidence, b.stated_at, version, now, row.id),
            'benefits_upserted',
          );
        }
        continue;
      }
      res.benefits_upserted += 1;
      add(
        env.DB.prepare(BENEFIT_INSERT).bind(
          newId('chb', now),
          id,
          b.kind,
          b.title,
          b.title_key,
          b.service_id,
          b.total_count,
          b.remaining,
          b.stated_by,
          b.confidence,
          b.stated_at,
          version,
          now,
        ),
        'benefits_upserted',
      );
    }
    const staleBenefits = st.benefits.filter((r) => r.state === 'active' && !titles.has(r.title_key)).map((r) => r.id);
    for (const chunk of inChunks(staleBenefits)) add(env.DB.prepare(`DELETE FROM chat_benefits WHERE state = 'active' AND id IN (${marks(chunk.length)})`).bind(...chunk));

    // Step 5: the phone number. A number already in customers.phone is never overwritten and never suggested; a number
    // staff dismissed, removed or replaced is neither set nor suggested again; nor is a number another customer holds.
    let suggestion = st.facts?.phone_suggestion ?? null;
    if (entry.phone) {
      const num = entry.phone.value;
      const hasPhone = !!cu && typeof cu.phone === 'string' && cu.phone.trim() !== '';
      if (hasPhone) suggestion = null;
      else if (st.dismissedPhones.has(num)) {
        if (suggestion === num) suggestion = null;
      } else if (heldByOther(owners, num, cu?.id ?? null)) {
        res.phones_taken += 1;
        if (suggestion === num) suggestion = null;
      } else if (entry.phone.confidence === 'high' && cu) {
        res.phones_set += 1;
        suggestion = null;
        add(env.DB.prepare(PHONE_SET).bind(num, cu.id, cu.id, num), 'phones_set');
        // a later entry of this request must not get the same number
        owners.set(num, new Set([...(owners.get(num) ?? []), cu.id]));
      } else {
        if (suggestion !== num) res.phone_suggestions += 1;
        suggestion = num;
      }
    }

    // Step 6: the contact's row, written only when a value changed (so a repeated document writes nothing).
    const f = st.facts;
    const changed =
      !f ||
      f.analyzer_version !== version ||
      f.generated_at !== doc.generated_at ||
      f.messages !== entry.messages ||
      f.first_at !== entry.first_at ||
      f.last_at !== entry.last_at ||
      f.phone_suggestion !== suggestion ||
      f.model_pass_json !== entry.model_pass_json;
    if (changed) {
      add(
        env.DB.prepare(FACTS_UPSERT).bind(
          id,
          version,
          doc.generated_at,
          now,
          entry.messages,
          entry.first_at,
          entry.last_at,
          suggestion,
          id,
          suggestion,
          PERSONAL_OA_ID,
          id,
          suggestion,
          entry.model_pass_json,
        ),
      );
    }
  }

  if (doc.dry_run) return res;
  // What the write statements really changed: a confirm, dismiss or phone accept between the read above and the
  // batches below makes their guards skip a row.
  const done: Record<WriteCounter, number> = { visits_imported: 0, visits_updated: 0, visits_removed: 0, benefits_upserted: 0, phones_set: 0 };
  for (let i = 0; i < stmts.length; i += IMPORT_CHUNK) {
    const part = stmts.slice(i, i + IMPORT_CHUNK);
    const results = await orConflict0011(env.DB.batch(part.map((x) => x.s)));
    part.forEach((x, k) => {
      if (x.counts) done[x.counts] += results[k]?.meta?.changes ?? 0;
    });
  }
  for (const k of WRITE_COUNTERS) res[k] = done[k];
  // Counts and the analyzer version only: never an id of a contact, a phone number, a title or a name.
  const { dry_run: _dry, ...counters } = res;
  await orConflict0011(
    auditStatement(env, { actor_type: 'staff', actor_id: staffId, action: 'chat_facts.import', entity: 'chat_facts', after: { ...counters, analyzer_version: version } }, now).run(),
  );
  return res;
}

// ---------------------------------------------------------------- eligible contacts (section 15.11)

/**
 * GET /staff/chat-facts/eligible: every `p:` contact with a customers row that is not deleted and not flagged as a
 * minor, whose latest ai_assistant consent row is granted (the rule of the rooms feed, section 14.7: the last consent
 * row wins), and that is not internal by the rule of import step 2 (internalForChatFacts): no contact_roles row
 * manager or staff, and no section 13 relationship family, friend, personal or staff unless a contact_roles row
 * 'customer' overrides it. The second half goes beyond the text of 15.11 (review of 2026-11-12): the analyzer's model
 * pass must not read a conversation that the import and get_customer_profile treat as private. Sorted. 409
 * invalid_state before migration 0011.
 */
export async function eligibleContacts(env: Env): Promise<string[]> {
  await require0011(env);
  const quiet = QUIET_RELATIONSHIPS.map((r) => `'${r}'`).join(',');
  const { results } = await orConflict0011(
    env.DB.prepare(
      "SELECT cu.zalo_user_id AS zalo_user_id FROM customers cu WHERE cu.oa_id = ? AND cu.zalo_user_id LIKE 'p:%' AND cu.deleted_at IS NULL " +
        'AND (cu.minor_flag IS NULL OR cu.minor_flag != 1) ' +
        "AND (SELECT s.status FROM consents s WHERE s.customer_id = cu.id AND s.purpose = 'ai_assistant' ORDER BY s.recorded_at DESC, s.rowid DESC LIMIT 1) = 'granted' " +
        "AND NOT EXISTS (SELECT 1 FROM contact_roles r WHERE r.zalo_user_id = cu.zalo_user_id AND r.role IN ('manager','staff')) " +
        `AND NOT (EXISTS (SELECT 1 FROM customer_profiles p WHERE p.zalo_user_id = cu.zalo_user_id AND p.relationship IN (${quiet})) ` +
        "AND NOT EXISTS (SELECT 1 FROM contact_roles r WHERE r.zalo_user_id = cu.zalo_user_id AND r.role = 'customer'))",
    )
      .bind(PERSONAL_OA_ID)
      .all<{ zalo_user_id: string }>(),
  );
  return [...new Set(results.map((r) => r.zalo_user_id).filter((id) => ROLE_ID_RE.test(id)))].sort();
}

// ---------------------------------------------------------------- views

function serviceName(catalog: ModelCatalog, s: StoredService): string {
  return (s.service_id ? catalog.byId.get(s.service_id)?.name : undefined) ?? s.service_name ?? s.service_id ?? '';
}

/**
 * The API shape of a chat_visits row: JSON columns parsed, service names resolved from the active catalog. With
 * `recordedDays` (GET /staff/chat-facts/:id) it adds `recorded_day`: the contact's customer has a recorded visit on
 * that local date, so the guess is not counted and cannot be confirmed. Pure.
 */
export function chatVisitView(r: ChatVisitRow, catalog: ModelCatalog, recordedDays?: Set<string>): ChatVisitView {
  const services = parseJson<StoredService[]>(r.services_json, []);
  return {
    ...(recordedDays ? { recorded_day: recordedDays.has(r.local_date) } : {}),
    id: r.id,
    zalo_user_id: r.zalo_user_id,
    local_date: r.local_date,
    kind: r.kind,
    visited_at: r.visited_at,
    time_known: r.time_known === 1,
    time: r.time_known === 1 ? hhmm(r.visited_at) : null,
    services: services.map((s) => ({ service_id: s.service_id ?? null, service_name: s.service_name ?? null, basis: s.basis, name: serviceName(catalog, s) })),
    amount_vnd: r.amount_vnd,
    amount_source: r.amount_source,
    technician: r.technician,
    confidence: r.confidence,
    signals: parseJson<string[]>(r.signals_json, []),
    evidence: parseJson<number[]>(r.evidence_json, []),
    fact_source: r.fact_source,
    state: r.state,
    confirmed_visit_id: r.confirmed_visit_id,
    analyzer_version: r.analyzer_version,
    imported_at: r.imported_at,
    decided_by: r.decided_by,
    decided_at: r.decided_at,
  };
}

/**
 * The API shape of a chat_benefits row. With `recordedTitles` (GET /staff/chat-facts/:id) it adds `recorded_title`:
 * an active benefit of the contact's customer has the same title key, so it is the same package and confirm answers
 * 409. Pure.
 */
export function chatBenefitView(r: ChatBenefitRow, catalog: ModelCatalog, recordedTitles?: Set<string>): ChatBenefitView {
  return {
    ...(recordedTitles ? { recorded_title: recordedTitles.has(r.title_key) } : {}),
    id: r.id,
    zalo_user_id: r.zalo_user_id,
    kind: r.kind,
    title: r.title,
    title_key: r.title_key,
    service_id: r.service_id,
    service_name: r.service_id ? (catalog.byId.get(r.service_id)?.name ?? null) : null,
    total_count: r.total_count,
    remaining: r.remaining,
    stated_by: r.stated_by,
    confidence: r.confidence,
    stated_at: r.stated_at,
    state: r.state,
    confirmed_benefit_id: r.confirmed_benefit_id,
    analyzer_version: r.analyzer_version,
    imported_at: r.imported_at,
    decided_by: r.decided_by,
    decided_at: r.decided_at,
  };
}

/** 404 for an id that is not 'p:' + 1 to 32 digits (section 15.11). */
export function mustChatContactId(id: string): string {
  if (!ROLE_ID_RE.test(id)) throw new HttpError(404, 'not_found', "no chat facts: zalo_user_id must be 'p:' + digits");
  return id;
}

/**
 * GET /staff/chat-facts/:zalo_user_id: every row of every state of one contact (the console shows the state), or null
 * when nothing is stored. Visits newest first, upcoming bookings soonest first, benefits newest statement first.
 *
 * `phone_suggestion` is null while the customer has a phone number, the rule of the summary's `chat.phone_suggestion`
 * (beyond the text of 15.11, review of 2026-11-12). The import never stores a suggestion for a customer with a phone,
 * but a suggestion stored earlier stays when staff later type a number into an empty phone (PATCH /staff/customers/:id)
 * or a booking request fills it; accepting it would answer 409 in that state. The stored suggestion is kept, and shown
 * again if the phone is removed.
 */
export async function getChatFacts(env: Env, zaloUserId: string): Promise<ChatFactsView | null> {
  mustChatContactId(zaloUserId);
  const [v, b, f] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare(`SELECT ${CHAT_VISIT_COLS} FROM chat_visits WHERE zalo_user_id = ?`).bind(zaloUserId),
      env.DB.prepare(`SELECT ${CHAT_BENEFIT_COLS} FROM chat_benefits WHERE zalo_user_id = ? ORDER BY stated_at DESC, id`).bind(zaloUserId),
      env.DB.prepare(`SELECT ${CHAT_FACTS_COLS} FROM chat_contact_facts WHERE zalo_user_id = ?`).bind(zaloUserId),
    ]),
  );
  const visits = v!.results as unknown as ChatVisitRow[];
  const benefits = b!.results as unknown as ChatBenefitRow[];
  const facts = (f!.results as unknown as ChatContactFactsRow[])[0] ?? null;
  if (!facts && !visits.length && !benefits.length) return null;
  const catalog = await loadModelCatalog(env);
  const cu = await personalCustomer(env, zaloUserId);
  const recordedDays = new Set<string>();
  const recordedTitles = new Set<string>();
  if (cu) {
    const [vd, bt] = await orConflict0011(
      env.DB.batch([
        env.DB.prepare('SELECT visited_at FROM visits WHERE customer_id = ?').bind(cu.id),
        env.DB.prepare("SELECT title FROM customer_benefits WHERE customer_id = ? AND status = 'active'").bind(cu.id),
      ]),
    );
    for (const r of vd!.results as Array<{ visited_at: number }>) recordedDays.add(localDate(r.visited_at));
    for (const r of bt!.results as Array<{ title: string }>) recordedTitles.add(benefitTitleKey(r.title));
  }
  const byTime = (a: ChatVisitRow, c: ChatVisitRow) => a.visited_at - c.visited_at || (a.id < c.id ? -1 : a.id > c.id ? 1 : 0);
  const modelPass = facts ? parseJson<{ ran?: unknown; reason?: unknown } | null>(facts.model_pass_json, null) : null;
  return {
    visits: visits.filter((r) => r.kind === 'visit').sort((a, c) => byTime(c, a)).map((r) => chatVisitView(r, catalog, recordedDays)),
    upcoming: visits.filter((r) => r.kind === 'upcoming').sort(byTime).map((r) => chatVisitView(r, catalog, recordedDays)),
    benefits: benefits.map((r) => chatBenefitView(r, catalog, recordedTitles)),
    phone_suggestion: cu && typeof cu.phone === 'string' && cu.phone.trim() !== '' ? null : (facts?.phone_suggestion ?? null),
    analyzer_version: facts?.analyzer_version ?? null,
    generated_at: facts?.generated_at ?? null,
    imported_at: facts?.imported_at ?? null,
    model_pass: modelPass
      ? { ran: modelPass.ran === true, reason: (MODEL_PASS_REASONS as unknown[]).includes(modelPass.reason) ? (modelPass.reason as ChatModelPassReason) : null }
      : null,
  };
}

// ---------------------------------------------------------------- decisions by staff (section 15.11)

const NO_CUSTOMER = 'khách chưa có hồ sơ';
/** 409 of a visit confirm onto a local date that already has a recorded visit (any source). */
const SAME_DAY = 'a visit is already recorded on this date';
/** 409 of a benefit confirm when an active benefit of the customer has the same title key. */
const SAME_BENEFIT = 'the customer already has a benefit with this title';
/** 409 of a phone accept when another customers row holds the suggested number. */
const PHONE_TAKEN = 'another customer already has this phone number';
const NO_SUGGESTION = 'there is no phone number suggestion for this contact';
const HAS_PHONE = 'the customer already has a phone number';
const DECIDED = 'the suggestion was decided in the meantime';

interface PersonalCustomer extends CustomerRef {
  channel: 'oa' | 'personal';
  display_name: string | null;
  minor_flag: number | null;
  last_user_interaction_at: number | null;
}

/** The contact's customers row on the personal channel, not deleted; null otherwise. */
async function personalCustomer(env: Env, zaloUserId: string): Promise<PersonalCustomer | null> {
  return env.DB.prepare(
    'SELECT id, zalo_user_id, phone, deleted_at, channel, display_name, minor_flag, last_user_interaction_at FROM customers WHERE oa_id = ? AND zalo_user_id = ? AND deleted_at IS NULL',
  )
    .bind(PERSONAL_OA_ID, zaloUserId)
    .first<PersonalCustomer>();
}

async function chatVisitRow(env: Env, id: string): Promise<ChatVisitRow | null> {
  return orConflict0011(env.DB.prepare(`SELECT ${CHAT_VISIT_COLS} FROM chat_visits WHERE id = ?`).bind(id).first<ChatVisitRow>());
}

async function chatBenefitRow(env: Env, id: string): Promise<ChatBenefitRow | null> {
  return orConflict0011(env.DB.prepare(`SELECT ${CHAT_BENEFIT_COLS} FROM chat_benefits WHERE id = ?`).bind(id).first<ChatBenefitRow>());
}

/** The body of a decision: absent, null or `{}` is an empty object; another value or an unknown field is 422. */
function decisionBody(body: unknown, allowed: string[]): Record<string, unknown> {
  if (body === undefined || body === null) return {};
  if (!isObj(body)) fail('body', 'body must be an object');
  const unknown = Object.keys(body).find((k) => !allowed.includes(k));
  if (unknown) fail(unknown, `unknown field ${unknown}`);
  return body;
}

const VISIT_CONFIRM_FIELDS = ['service_id', 'amount_vnd', 'technician', 'visited_at_local'];

/**
 * POST /staff/chat-facts/visits/:id/confirm. Only for an active guess of kind 'visit' (409 otherwise, also for a second
 * confirm) of a contact with a customers row that is not deleted (409 "khách chưa có hồ sơ"). Staff may correct
 * `service_id` (a service of the active catalog), `amount_vnd` (an integer of 0 or more, null for unknown),
 * `technician` (one line of at most 60 characters, null for none) and `visited_at_local` ('YYYY-MM-DD HH:MM'); a field
 * left out keeps the guess. The amount is the exception: left out, it is copied only when its amount_source is 'paid'
 * (a quoted or list price is not money the customer paid, section 15.12); staff who know the customer paid it send
 * `amount_vnd`. Without a corrected service the visit takes the first catalog service of the guess, else its first
 * service name (stored as 'ext:' + slug like the visits import).
 *
 * 409 "a visit is already recorded on this date" when the customer has a visits row (any source) on the local date of
 * the final visit time: the summary already counts that day, and a second row would count its spend twice.
 *
 * One batch writes the confirmed state, the visits row (source 'staff', recorded_by the staff id) and the audit row;
 * the visit and the audit row are written only when this request moved the guess from active to confirmed, and the
 * move itself needs the date to be still free of recorded visits. No follow-up job is created (visitInsertStatement).
 */
export async function confirmChatVisit(env: Env, id: string, body: unknown, staffId: string, now = Date.now()): Promise<{ visit: VisitView; chat_visit: ChatVisitView }> {
  const b = decisionBody(body, VISIT_CONFIRM_FIELDS);
  if (!absent(b.service_id) && b.service_id !== '' && typeof b.service_id !== 'string') fail('service_id', 'service_id must be a service id');
  // amount_vnd and technician: the checks of POST /staff/visits (parseVisitExtras); null clears the guessed value.
  const extras = parseVisitExtras({ amount_vnd: b.amount_vnd as number | null | undefined, technician: b.technician as string | null | undefined });
  let correctedAt: number | null = null;
  if (!absent(b.visited_at_local) && b.visited_at_local !== '') {
    correctedAt = typeof b.visited_at_local === 'string' ? parseLocalDateTime(b.visited_at_local) : null;
    if (correctedAt === null) fail('visited_at_local', "visited_at_local must be 'YYYY-MM-DD HH:MM' (Vietnam time)");
  }

  const row = await chatVisitRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'chat visit not found');
  if (row.kind !== 'visit') throw new HttpError(409, 'invalid_state', 'an upcoming booking cannot be confirmed as a visit');
  if (row.state !== 'active') throw new HttpError(409, 'invalid_state', `this guess is already ${row.state}`);
  const cu = await personalCustomer(env, row.zalo_user_id);
  if (!cu) throw new HttpError(409, 'invalid_state', NO_CUSTOMER);

  const catalog = await loadModelCatalog(env);
  let serviceId: string;
  let serviceNameStored: string | null = null;
  if (typeof b.service_id === 'string' && b.service_id) {
    if (!catalog.byId.has(b.service_id)) fail('service_id', 'unknown service_id in the active catalog');
    serviceId = b.service_id;
  } else {
    const services = parseJson<StoredService[]>(row.services_json, []);
    const inCatalog = services.find((s) => s.service_id && catalog.byId.has(s.service_id));
    const named = services.find((s) => s.service_name && serviceSlug(s.service_name));
    if (inCatalog) serviceId = inCatalog.service_id!;
    else if (named) {
      serviceId = `ext:${serviceSlug(named.service_name!)}`;
      serviceNameStored = named.service_name;
    } else fail('service_id', 'the guess names no service: send service_id');
  }
  const amount = b.amount_vnd !== undefined ? extras.amount_vnd : row.amount_source === 'paid' ? row.amount_vnd : null;
  if (amount !== null && !isVisitAmount(amount)) fail('amount_vnd', 'amount_vnd must be an integer of 0 or more (VND)');
  const technician = b.technician !== undefined ? extras.technician : row.technician;
  const visitedAt = correctedAt ?? row.visited_at;
  if (visitedAt > now + HOUR_MS) fail('visited_at_local', 'visited_at_local must not be in the future');
  const dayFrom = localMidnight(visitedAt);
  const dayTaken = 'SELECT 1 FROM visits WHERE customer_id = ? AND visited_at >= ? AND visited_at < ?';
  const dayBinds = [cu.id, dayFrom, dayFrom + DAY_MS];
  if (await env.DB.prepare(dayTaken).bind(...dayBinds).first()) throw new HttpError(409, 'invalid_state', SAME_DAY);

  const visitId = newId('vis', now);
  const corrected = VISIT_CONFIRM_FIELDS.filter((k) => b[k] !== undefined);
  const guard = { sql: 'SELECT 1 FROM chat_visits WHERE id = ? AND confirmed_visit_id = ?', binds: [id, visitId] };
  const [moved] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare(
        "UPDATE chat_visits SET state = 'confirmed', confirmed_visit_id = ?, decided_by = ?, decided_at = ? WHERE id = ? AND state = 'active' AND kind = 'visit' " +
          `AND NOT EXISTS (${dayTaken})`,
      ).bind(visitId, staffId, now, id, ...dayBinds),
      visitInsertStatement(
        env,
        {
          id: visitId,
          customer_id: cu.id,
          service_id: serviceId,
          service_name: serviceNameStored,
          visited_at: visitedAt,
          duration_min: null,
          amount_vnd: amount,
          technician,
          benefit_id: null,
          source: 'staff',
          external_visit_id: null,
          booking_request_id: null,
          recorded_by: staffId,
          created_at: now,
        },
        guard,
      ),
      // ids, enum values and field names only: never the technician, a service name or an amount typed in a chat
      guardedAuditStatement(
        env,
        {
          actor_type: 'staff',
          actor_id: staffId,
          action: 'chat_facts.visit_confirm',
          entity: 'chat_visit',
          entity_id: id,
          before: { state: 'active', confidence: row.confidence },
          after: { state: 'confirmed', visit_id: visitId, customer_id: cu.id, catalog_service: serviceNameStored === null, corrected },
        },
        now,
        guard,
      ),
    ]),
  );
  if (!moved!.meta.changes) {
    // still active: a visit of that date was recorded between the check above and the batch
    if ((await chatVisitRow(env, id))?.state === 'active') throw new HttpError(409, 'invalid_state', SAME_DAY);
    throw new HttpError(409, 'invalid_state', 'this guess was decided in the meantime');
  }
  const visit = await env.DB.prepare(
    'SELECT id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, recorded_by, created_at FROM visits WHERE id = ?',
  )
    .bind(visitId)
    .first<Omit<VisitView, 'name'>>();
  const after = await chatVisitRow(env, id);
  return {
    visit: { ...visit!, name: catalog.byId.get(visit!.service_id)?.name ?? visit!.service_name ?? visit!.service_id },
    chat_visit: chatVisitView(after!, catalog),
  };
}

/** POST /staff/chat-facts/visits/:id/dismiss: an active guess (visit or upcoming booking) becomes a tombstone. */
export async function dismissChatVisit(env: Env, id: string, staffId: string, now = Date.now()): Promise<{ chat_visit: ChatVisitView }> {
  const row = await chatVisitRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'chat visit not found');
  if (row.state !== 'active') throw new HttpError(409, 'invalid_state', `this guess is already ${row.state}`);
  const [moved] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare("UPDATE chat_visits SET state = 'dismissed', decided_by = ?, decided_at = ? WHERE id = ? AND state = 'active'").bind(staffId, now, id),
      guardedAuditStatement(
        env,
        { actor_type: 'staff', actor_id: staffId, action: 'chat_facts.visit_dismiss', entity: 'chat_visit', entity_id: id, before: { state: 'active', kind: row.kind }, after: { state: 'dismissed' } },
        now,
        { sql: "SELECT 1 FROM chat_visits WHERE id = ? AND state = 'dismissed' AND decided_at = ? AND decided_by = ?", binds: [id, now, staffId] },
      ),
    ]),
  );
  if (!moved!.meta.changes) throw new HttpError(409, 'invalid_state', 'this guess was decided in the meantime');
  return { chat_visit: chatVisitView((await chatVisitRow(env, id))!, await loadModelCatalog(env)) };
}

const BENEFIT_CONFIRM_FIELDS = ['title', 'total_count', 'used_count', 'expires_at'];

/**
 * POST /staff/chat-facts/benefits/:id/confirm. Creates a customer_benefits row (recorded_by the staff id) from an active
 * guess of a contact with a customers row (409 otherwise). `title` (one line, 1 to 120 characters) defaults to the
 * guess; `total_count` (1 to 1 000) is required when the guess has none; `used_count` defaults to total_count -
 * remaining when both are known, else 0 (422 when that would be negative); `expires_at` is ms or null. The guess's
 * service is kept only when it is in the active catalog. 409 "the customer already has a benefit with this title" when
 * an active customer_benefits row of the customer has the same title key as the title to record (beyond the text of
 * 15.11, review of 2026-11-12). The benefit and the audit row are written only when this request moved the guess from
 * active to confirmed.
 */
export async function confirmChatBenefit(env: Env, id: string, body: unknown, staffId: string, now = Date.now()): Promise<{ benefit: CustomerBenefit; chat_benefit: ChatBenefitView }> {
  const b = decisionBody(body, BENEFIT_CONFIRM_FIELDS);
  let title: string | null = null;
  if (b.title !== undefined) {
    title = optionalLine(b.title, MAX_BENEFIT_TITLE_CHARS, 'title');
    if (title === null) fail('title', `title must be one line of 1 to ${MAX_BENEFIT_TITLE_CHARS} characters`);
  }
  if (!absent(b.total_count) && (!isInt(b.total_count) || b.total_count < 1 || b.total_count > MAX_BENEFIT_COUNT)) fail('total_count', `total_count must be an integer from 1 to ${MAX_BENEFIT_COUNT}`);
  if (!absent(b.expires_at) && (!isInt(b.expires_at) || b.expires_at <= 0)) fail('expires_at', 'expires_at must be a time in ms or null');

  const row = await chatBenefitRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'chat benefit not found');
  if (row.state !== 'active') throw new HttpError(409, 'invalid_state', `this guess is already ${row.state}`);
  const total = absent(b.total_count) ? row.total_count : (b.total_count as number);
  if (total === null) fail('total_count', 'total_count is required: the guess has no count');
  let used: number;
  if (absent(b.used_count)) {
    // total_count (the guess's, or the one staff gave) and the guessed remaining count
    used = row.remaining !== null ? total - row.remaining : 0;
    if (used < 0) fail('used_count', 'the guessed remaining count is above total_count: send used_count');
  } else {
    if (!isInt(b.used_count) || b.used_count < 0 || b.used_count > total) fail('used_count', `used_count must be an integer from 0 to total_count (${total})`);
    used = b.used_count;
  }
  const cu = await personalCustomer(env, row.zalo_user_id);
  if (!cu) throw new HttpError(409, 'invalid_state', NO_CUSTOMER);
  // The same package typed by staff (or confirmed before): a second row would show the model two packages. Staff who
  // mean a second package of the same kind give it another title.
  const finalKey = benefitTitleKey(title ?? row.title);
  const { results: active } = await orConflict0011(
    env.DB.prepare("SELECT title FROM customer_benefits WHERE customer_id = ? AND status = 'active'").bind(cu.id).all<{ title: string }>(),
  );
  if (active.some((r) => benefitTitleKey(r.title) === finalKey)) throw new HttpError(409, 'invalid_state', SAME_BENEFIT);
  const catalog = await loadModelCatalog(env);

  const benefit: BenefitRow = {
    id: newId('ben', now),
    customer_id: cu.id,
    kind: row.kind,
    title: title ?? row.title,
    service_id: row.service_id && catalog.byId.has(row.service_id) ? row.service_id : null,
    total_count: total,
    used_count: used,
    expires_at: absent(b.expires_at) ? null : (b.expires_at as number),
    status: 'active',
    recorded_by: staffId,
    created_at: now,
    updated_at: now,
  };
  const guard = { sql: 'SELECT 1 FROM chat_benefits WHERE id = ? AND confirmed_benefit_id = ?', binds: [id, benefit.id] };
  const [moved] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare("UPDATE chat_benefits SET state = 'confirmed', confirmed_benefit_id = ?, decided_by = ?, decided_at = ? WHERE id = ? AND state = 'active'").bind(
        benefit.id,
        staffId,
        now,
        id,
      ),
      env.DB.prepare(`INSERT INTO customer_benefits (${BENEFIT_COLS}) SELECT ?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS (${guard.sql})`).bind(
        benefit.id,
        benefit.customer_id,
        benefit.kind,
        benefit.title,
        benefit.service_id,
        benefit.total_count,
        benefit.used_count,
        benefit.expires_at,
        benefit.status,
        benefit.recorded_by,
        benefit.created_at,
        benefit.updated_at,
        ...guard.binds,
      ),
      // never the title
      guardedAuditStatement(
        env,
        {
          actor_type: 'staff',
          actor_id: staffId,
          action: 'chat_facts.benefit_confirm',
          entity: 'chat_benefit',
          entity_id: id,
          before: { state: 'active' },
          after: { state: 'confirmed', benefit_id: benefit.id, customer_id: cu.id, kind: benefit.kind, total_count: total, used_count: used, expires_at: benefit.expires_at, title_changed: benefit.title !== row.title },
        },
        now,
        guard,
      ),
    ]),
  );
  if (!moved!.meta.changes) throw new HttpError(409, 'invalid_state', 'this guess was decided in the meantime');
  return { benefit: benefitView(benefit), chat_benefit: chatBenefitView((await chatBenefitRow(env, id))!, catalog) };
}

/** POST /staff/chat-facts/benefits/:id/dismiss: an active guess becomes a tombstone. */
export async function dismissChatBenefit(env: Env, id: string, staffId: string, now = Date.now()): Promise<{ chat_benefit: ChatBenefitView }> {
  const row = await chatBenefitRow(env, id);
  if (!row) throw new HttpError(404, 'not_found', 'chat benefit not found');
  if (row.state !== 'active') throw new HttpError(409, 'invalid_state', `this guess is already ${row.state}`);
  const [moved] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare("UPDATE chat_benefits SET state = 'dismissed', decided_by = ?, decided_at = ? WHERE id = ? AND state = 'active'").bind(staffId, now, id),
      guardedAuditStatement(
        env,
        { actor_type: 'staff', actor_id: staffId, action: 'chat_facts.benefit_dismiss', entity: 'chat_benefit', entity_id: id, before: { state: 'active', kind: row.kind }, after: { state: 'dismissed' } },
        now,
        { sql: "SELECT 1 FROM chat_benefits WHERE id = ? AND state = 'dismissed' AND decided_at = ? AND decided_by = ?", binds: [id, now, staffId] },
      ),
    ]),
  );
  if (!moved!.meta.changes) throw new HttpError(409, 'invalid_state', 'this guess was decided in the meantime');
  return { chat_benefit: chatBenefitView((await chatBenefitRow(env, id))!, await loadModelCatalog(env)) };
}

async function factsRow(env: Env, zaloUserId: string): Promise<ChatContactFactsRow | null> {
  return orConflict0011(env.DB.prepare(`SELECT ${CHAT_FACTS_COLS} FROM chat_contact_facts WHERE zalo_user_id = ?`).bind(zaloUserId).first<ChatContactFactsRow>());
}

/**
 * POST /staff/chat-facts/:zalo_user_id/phone/accept: copies the suggestion into the empty customers.phone and clears
 * the suggestion. 409 without a suggestion, without a customers row, when the customer already has a phone, or when
 * another customers row (not deleted) holds the same number (beyond the text of 15.11, review of 2026-11-12: the
 * visits import matches a phone only when exactly one customer has it). The audit row says only that a number is now
 * stored; it is written only by the request that made the change (a random decision id that request writes).
 */
export async function acceptPhoneSuggestion(env: Env, zaloUserId: string, staffId: string, now = Date.now()): Promise<{ customer: CustomerView; facts: ChatFactsView | null }> {
  mustChatContactId(zaloUserId);
  const f = await factsRow(env, zaloUserId);
  const num = f?.phone_suggestion ?? null;
  if (!num) throw new HttpError(409, 'invalid_state', NO_SUGGESTION);
  const cu = await personalCustomer(env, zaloUserId);
  if (!cu) throw new HttpError(409, 'invalid_state', NO_CUSTOMER);
  if (typeof cu.phone === 'string' && cu.phone.trim() !== '') throw new HttpError(409, 'invalid_state', HAS_PHONE);
  if (heldByOther(await loadPhoneOwners(env), num, cu.id)) throw new HttpError(409, 'invalid_state', PHONE_TAKEN);
  const decision = crypto.randomUUID();
  const [set] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare(
        "UPDATE customers SET phone = ? WHERE id = ? AND (phone IS NULL OR TRIM(phone) = '') " +
          'AND NOT EXISTS (SELECT 1 FROM customers o WHERE o.id != ? AND o.deleted_at IS NULL AND o.phone = ?) ' +
          'AND EXISTS (SELECT 1 FROM chat_contact_facts WHERE zalo_user_id = ? AND phone_suggestion = ?)',
      ).bind(num, cu.id, cu.id, num, zaloUserId, num),
      env.DB.prepare(
        'UPDATE chat_contact_facts SET phone_suggestion = NULL, phone_decision_id = ? WHERE zalo_user_id = ? AND phone_suggestion = ? AND EXISTS (SELECT 1 FROM customers WHERE id = ? AND phone = ?)',
      ).bind(decision, zaloUserId, num, cu.id, num),
      guardedAuditStatement(
        env,
        { actor_type: 'staff', actor_id: staffId, action: 'chat_facts.phone_accept', entity: 'customer', entity_id: cu.id, before: { has_phone: false }, after: { has_phone: true } },
        now,
        { sql: 'SELECT 1 FROM chat_contact_facts WHERE zalo_user_id = ? AND phone_decision_id = ?', binds: [zaloUserId, decision] },
      ),
    ]),
  );
  if (!set!.meta.changes) {
    // something changed between the checks above and the batch: say what
    if ((await factsRow(env, zaloUserId))?.phone_suggestion !== num) throw new HttpError(409, 'invalid_state', DECIDED);
    const now2 = await personalCustomer(env, zaloUserId);
    if (now2 && typeof now2.phone === 'string' && now2.phone.trim() !== '') throw new HttpError(409, 'invalid_state', HAS_PHONE);
    throw new HttpError(409, 'invalid_state', PHONE_TAKEN);
  }
  return {
    customer: {
      id: cu.id,
      channel: cu.channel,
      zalo_user_id: cu.zalo_user_id,
      display_name: cu.display_name,
      phone: num,
      minor_flag: cu.minor_flag === null ? null : cu.minor_flag === 1,
      last_user_interaction_at: cu.last_user_interaction_at,
    },
    facts: await getChatFacts(env, zaloUserId),
  };
}

/**
 * POST /staff/chat-facts/:zalo_user_id/phone/dismiss: the suggestion moves to phone_dismissed (phone_state
 * 'dismissed') and into chat_phone_dismissed, which keeps every number staff dismissed for the contact, so none of them
 * is suggested or set again. 409 without a suggestion. The audit row has no number; it is written only by the request
 * that made the change.
 */
export async function dismissPhoneSuggestion(env: Env, zaloUserId: string, staffId: string, now = Date.now()): Promise<{ facts: ChatFactsView | null }> {
  mustChatContactId(zaloUserId);
  const f = await factsRow(env, zaloUserId);
  const num = f?.phone_suggestion ?? null;
  if (!num) throw new HttpError(409, 'invalid_state', NO_SUGGESTION);
  const decision = crypto.randomUUID();
  const mine = { sql: 'SELECT 1 FROM chat_contact_facts WHERE zalo_user_id = ? AND phone_decision_id = ?', binds: [zaloUserId, decision] };
  const [moved] = await orConflict0011(
    env.DB.batch([
      env.DB.prepare(
        "UPDATE chat_contact_facts SET phone_dismissed = phone_suggestion, phone_state = 'dismissed', phone_suggestion = NULL, phone_decision_id = ? WHERE zalo_user_id = ? AND phone_suggestion = ?",
      ).bind(decision, zaloUserId, num),
      env.DB.prepare(
        `INSERT INTO chat_phone_dismissed (zalo_user_id, phone, reason, decided_by, decided_at) SELECT ?, ?, 'suggestion_dismissed', ?, ? WHERE EXISTS (${mine.sql}) ` +
          'ON CONFLICT(zalo_user_id, phone) DO NOTHING',
      ).bind(zaloUserId, num, staffId, now, ...mine.binds),
      guardedAuditStatement(
        env,
        { actor_type: 'staff', actor_id: staffId, action: 'chat_facts.phone_dismiss', entity: 'chat_contact_facts', entity_id: zaloUserId, after: { phone_state: 'dismissed' } },
        now,
        mine,
      ),
    ]),
  );
  if (!moved!.meta.changes) throw new HttpError(409, 'invalid_state', DECIDED);
  return { facts: await getChatFacts(env, zaloUserId) };
}

// ---------------------------------------------------------------- summary merge (section 15.12)

/** The service id of a guessed visit day that names no service: counted as a day, never listed as a service. */
export const CHAT_NO_SERVICE = 'chat:none';

/** One visit row as the summary reads it (lib/customer-summary.ts): a recorded visit, or one service of a chat guess. */
export interface SummaryVisitRow {
  id: string;
  service_id: string;
  service_name: string | null;
  visited_at: number;
  amount_vnd: number | null;
  technician: string | null;
  from_chat?: boolean;
  time_known?: boolean;
}

/** What the summary needs from the chat tables of one contact. */
export interface ChatSummaryInput {
  visits: Array<Pick<ChatVisitRow, 'id' | 'local_date' | 'kind' | 'visited_at' | 'time_known' | 'services_json' | 'amount_vnd' | 'amount_source' | 'technician' | 'confidence' | 'state'>>;
  benefits: Array<Pick<ChatBenefitRow, 'kind' | 'remaining' | 'state' | 'title_key'>>;
  facts: Pick<ChatContactFactsRow, 'phone_suggestion' | 'analyzer_version' | 'generated_at'> | null;
}

/**
 * The chat rows of one contact for the summary. null when the contact has none at all (no chat_contact_facts row, no
 * chat visit or benefit of any state), when the id is not a `p:` id, and when migration 0011 is not applied: the
 * summary is then exactly what it was before section 15.
 */
export async function loadChatSummaryInput(env: Env, zaloUserId: string): Promise<ChatSummaryInput | null> {
  if (typeof zaloUserId !== 'string' || !ROLE_ID_RE.test(zaloUserId)) return null;
  const rows = await orMissing0011(
    env.DB.batch([
      env.DB.prepare(
        'SELECT id, local_date, kind, visited_at, time_known, services_json, amount_vnd, amount_source, technician, confidence, state FROM chat_visits WHERE zalo_user_id = ?',
      ).bind(zaloUserId),
      env.DB.prepare('SELECT kind, remaining, state, title_key FROM chat_benefits WHERE zalo_user_id = ?').bind(zaloUserId),
      env.DB.prepare('SELECT phone_suggestion, analyzer_version, generated_at FROM chat_contact_facts WHERE zalo_user_id = ?').bind(zaloUserId),
    ]),
    null,
  );
  if (!rows) return null;
  const visits = rows[0]!.results as unknown as ChatSummaryInput['visits'];
  const benefits = rows[1]!.results as unknown as ChatSummaryInput['benefits'];
  const facts = (rows[2]!.results as unknown as Array<NonNullable<ChatSummaryInput['facts']>>)[0] ?? null;
  if (!facts && !visits.length && !benefits.length) return null;
  return { visits, benefits, facts };
}

export interface ChatMerge {
  /** recorded visits and the counted guesses (one row per service), newest first */
  rows: SummaryVisitRow[];
  /** counted guessed visit days */
  counted: number;
  /** active low-confidence guesses on a date without a recorded visit */
  low: number;
  /** the soonest active upcoming booking, today or later */
  upcomingNext: { date: string; time: string | null } | null;
  /** active chat benefits, less those whose title key is the one of an active customer_benefits row */
  benefitsActive: number;
  /** the same benefits whose remaining count is known: kind and count only */
  benefitsForModel: Array<{ kind: BenefitKind; remaining: number }>;
  phoneSuggestion: boolean;
  analyzerVersion: string | null;
  generatedAt: number | null;
}

/**
 * Merges the chat guesses of one contact into its recorded visits (section 15.12). Pure.
 *
 * Counted: kind 'visit', state 'active', confidence high or medium, on a local date with no recorded visit (a
 * confirmed guess is already a visits row; dismissed, low and upcoming rows never count). A counted guess becomes one
 * row per service (a catalog id, else 'ext:' + slug of the name, else CHAT_NO_SERVICE), all at its visited_at; its
 * amount sits on the first row and only when amount_source is 'paid' (a quoted or list price is not spend).
 *
 * A chat benefit whose title_key is in `recordedBenefitKeys` (the keys of the customer's active customer_benefits
 * titles, benefitTitleKey) is the package staff already recorded: it is neither counted nor shown to the model again
 * (beyond the text of 15.12, review of 2026-11-12).
 */
export function mergeChatVisits(
  recorded: SummaryVisitRow[],
  chat: ChatSummaryInput,
  now: number,
  customerHasPhone: boolean,
  recordedBenefitKeys: Set<string> = new Set(),
): ChatMerge {
  const recordedDays = new Set(recorded.map((v) => localDate(v.visited_at)));
  const open = chat.visits.filter((r) => r.kind === 'visit' && r.state === 'active' && !recordedDays.has(r.local_date));
  const counted = open.filter((r) => r.confidence === 'high' || r.confidence === 'medium');
  const rows: SummaryVisitRow[] = [...recorded];
  for (const r of counted) {
    const services = parseJson<StoredService[]>(r.services_json, []);
    const named = services
      .map((s) => {
        const slug = s.service_name ? serviceSlug(s.service_name) : '';
        return { id: s.service_id ?? (slug ? `ext:${slug}` : null), name: s.service_name ?? null };
      })
      .filter((s): s is { id: string; name: string | null } => !!s.id);
    const list = named.length ? named : [{ id: CHAT_NO_SERVICE, name: null }];
    list.forEach((s, i) => {
      rows.push({
        id: `${r.id}:${i}`,
        service_id: s.id,
        service_name: s.name,
        visited_at: r.visited_at,
        amount_vnd: i === 0 && r.amount_source === 'paid' ? r.amount_vnd : null,
        technician: r.technician,
        from_chat: true,
        time_known: r.time_known === 1,
      });
    });
  }
  rows.sort((a, b) => b.visited_at - a.visited_at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  const today = localDate(now);
  const upcoming = chat.visits
    .filter((r) => r.kind === 'upcoming' && r.state === 'active' && r.local_date >= today)
    .sort((a, b) => (a.local_date < b.local_date ? -1 : a.local_date > b.local_date ? 1 : a.visited_at - b.visited_at))[0];
  const activeBenefits = chat.benefits.filter((b) => b.state === 'active' && !recordedBenefitKeys.has(b.title_key));
  return {
    rows,
    counted: counted.length,
    low: open.filter((r) => r.confidence === 'low').length,
    upcomingNext: upcoming ? { date: upcoming.local_date, time: upcoming.time_known === 1 ? hhmm(upcoming.visited_at) : null } : null,
    benefitsActive: activeBenefits.length,
    benefitsForModel: activeBenefits.filter((b) => b.remaining !== null).map((b) => ({ kind: b.kind, remaining: b.remaining as number })),
    phoneSuggestion: !!chat.facts?.phone_suggestion && !customerHasPhone,
    analyzerVersion: chat.facts?.analyzer_version ?? null,
    generatedAt: chat.facts?.generated_at ?? null,
  };
}
