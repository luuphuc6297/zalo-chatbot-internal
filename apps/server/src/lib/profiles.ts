// Owner: server-core. Contact profiles of the personal channel (docs/contracts.md section 13).
// Profiles come from scripts/analyze_contacts.py (rules only, local) through POST /staff/profiles/import and from staff
// edits (PATCH /staff/profiles/:zalo_user_id). Only derived facts ever reach the model (profileFactsForModel):
// address term, name, catalog service names, the last service (name + date), relationship. Evidence snippets, stats
// and pronoun counts stay with staff. Relationships family / staff / friend never reach the model and are kept away
// from the bot by the quiet rule (personalSkipApplies).
import type {
  ContactRole,
  ContactRoleRow,
  CustomerProfileForModel,
  CustomerProfileImport,
  CustomerProfileView,
  Env,
  ProfileAddressTerm,
  ProfileAnalyzerValues,
  ProfileConfidence,
  ProfileEvidence,
  ProfileImportResponse,
  ProfileLastService,
  ProfilePatchRequest,
  ProfileRelationship,
  ProfileService,
  ProfileStaffField,
} from '../types';
import { HttpError } from './http';
import { auditStatement } from './audit';
import { consentStatus, safeJson } from './db';
import { getFlags } from './flags';
import { localDate } from './time';
import { getContactRole, getContactRoles, isInternalRole } from './roles';

export const PROFILE_ID_RE = /^p:[A-Za-z0-9_-]{1,64}$/;
/** 'personal' is the legacy value of analyzer v2; analyzer v3 writes family / staff / friend. */
export const RELATIONSHIPS: ProfileRelationship[] = ['customer', 'staff', 'family', 'friend', 'unknown', 'personal'];
/** Relationships the bot may draft for (and the only ones whose facts reach the model). */
export const BOT_RELATIONSHIPS: ProfileRelationship[] = ['customer', 'unknown'];
/** Relationships the quiet rule keeps away from the bot (at confidence high, or with staff_override = 1). */
export const QUIET_RELATIONSHIPS: ProfileRelationship[] = ['family', 'staff', 'friend', 'personal'];
export const CONFIDENCES: ProfileConfidence[] = ['low', 'medium', 'high'];
export const ADDRESS_TERMS: ProfileAddressTerm[] = ['chị', 'anh', 'cô', 'chú', 'bác', 'anh/chị'];
/** Field groups staff can own (staff_fields_json); each group is kept across imports on its own. */
export const STAFF_FIELDS: ProfileStaffField[] = ['relationship', 'address', 'name', 'services'];
/** One word, letters only (Vietnamese letters included), at most 20 characters. */
const NAME_RE = /^\p{L}{1,20}$/u;
const SERVICE_KEY_RE = /^(cat:)?[a-z0-9_-]{1,64}$/;
const SERVICE_ID_RE = /^[a-z0-9-]{1,64}$/;
const REASON_RE = /^[a-z0-9_:.-]{1,64}$/;
export const MAX_IMPORT_PROFILES = 500;
export const MAX_IMPORT_BYTES = 2_000_000;
const MAX_SERVICES = 40;
const MAX_EVIDENCE = 3;
export const EVIDENCE_MAX_CHARS = 80;
const MAX_OBJECT_JSON = 4000;
/** Services named to the model per list (section 13 rule 4); also the cap of the customer summary's model view. */
export const MAX_MODEL_SERVICES = 5;
/** The model gets the last service only this long after it (reply template chao_khach_quen, data/reply-templates.json). */
export const LAST_SERVICE_MODEL_MAX_AGE_MS = 180 * 86_400_000;

/** Catalog groups whose services are health data; never named to the model. */
export const SENSITIVE_GROUPS = ['health', 'women'];
/** Category keys of those groups (scripts/analyze_contacts.py CATEGORY_KEYWORDS). */
const SENSITIVE_CATEGORY_KEYS = ['cat:dien_chan', 'cat:yoni'];
/**
 * The folded keywords of those two categories in scripts/analyze_contacts.py CATEGORY_KEYWORDS ('diện chẩn', 'ấn
 * huyệt', 'giác hơi', 'hơ ngải' for cat:dien_chan, health; 'yoni', 'vùng kín' for cat:yoni, women). The analyzer builds
 * a benefit title from a category name ('Gói 10 buổi – Chăm sóc vùng kín'), which then names no catalog service.
 */
export const SENSITIVE_CATEGORY_WORDS = ['dien chan', 'an huyet', 'giac hoi', 'ho ngai', 'yoni', 'vung kin'];
/** Category keys the model may see, with fixed labels (catalog groups relaxation, skin, hair). Other keys are dropped. */
export const MODEL_CATEGORY_LABELS: Record<string, string> = {
  'cat:goi_dau': 'gội đầu',
  'cat:massage': 'massage',
  'cat:cham_soc_da': 'chăm sóc da',
  'cat:da_mun': 'chăm sóc da mụn',
  'cat:quang_mat': 'xóa thâm quầng mắt',
};

export interface ProfileRow {
  zalo_user_id: string;
  display_name: string | null;
  relationship: ProfileRelationship;
  relationship_confidence: ProfileConfidence;
  relationship_reasons_json: string;
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  address_confidence: ProfileConfidence;
  addressing_json: string;
  services_json: string;
  evidence_json: string;
  stats_json: string;
  analyzer_json: string | null;
  analyzer_version: string | null;
  source: 'analyzer' | 'staff';
  staff_override: number;
  staff_fields_json?: string;
  staff_note: string | null;
  analyzed_at: number | null;
  created_at: number;
  updated_at: number;
  updated_by: string;
  customer_id?: string | null;
  conversation_id?: string | null;
  last_service_json?: string | null; // migration 0008; undefined before it
}

/** The newest staff-recorded visit of the profile's customer (visits joined through customers.zalo_user_id). */
export interface VisitRef {
  service_id: string;
  visited_at: number;
}

// ---------------------------------------------------------------- missing table (before migration 0007)

/**
 * `wrangler dev` reloads changed code while the local D1 may not have migration 0007 yet. Reads that sit on the
 * customer path (claim, ingest, conversation detail) then behave as "no profile"; staff writes answer 409.
 */
export function isMissingProfilesTable(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return /no such table:?\s*customer_profiles/i.test(msg);
}

async function orNoTable<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingProfilesTable(e)) return fallback;
    throw e;
  }
}

/**
 * The local D1 has migration 0007 but not 0008: no last_service_json column, and the CHECK constraint refuses the
 * relationships family / staff / friend. Reads ignore the missing column; writes that need it answer 409.
 */
export function isMissingProfilesV2(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return /last_service_json/i.test(msg) || /CHECK constraint failed:?.*relationship/i.test(msg);
}

async function orConflict<T>(p: Promise<T>): Promise<T> {
  try {
    return await p;
  } catch (e) {
    if (isMissingProfilesTable(e)) throw new HttpError(409, 'invalid_state', 'customer_profiles table missing: apply migration 0007_customer_profiles.sql');
    if (isMissingProfilesV2(e)) throw new HttpError(409, 'invalid_state', 'customer_profiles is older than profiles v2: apply migration 0008_profiles_v2.sql');
    throw e;
  }
}

// ---------------------------------------------------------------- validation

function fail(field: string, message: string): never {
  throw new HttpError(422, 'validation_failed', message, { field });
}

const chars = (s: string) => [...s].length;
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isMs = (v: unknown) => v === null || (Number.isInteger(v) && (v as number) >= 0);
const isCount = (v: unknown) => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= 10_000_000;

function oneOf<T extends string>(v: unknown, allowed: T[], field: string): T {
  if (typeof v !== 'string' || !(allowed as string[]).includes(v)) fail(field, `${field} must be one of ${allowed.join(', ')}`);
  return v as T;
}

export function validName(v: unknown, field: string): string | null {
  if (v === null) return null;
  if (typeof v !== 'string') fail(field, `${field} must be a string or null`);
  const s = v.normalize('NFC').trim();
  if (!NAME_RE.test(s)) fail(field, `${field} must be one word of letters, at most 20 characters`);
  return s;
}

function validAddressTerm(v: unknown, field: string): ProfileAddressTerm | null {
  if (v === null) return null;
  return oneOf(typeof v === 'string' ? v.normalize('NFC') : v, ADDRESS_TERMS, field);
}

function validSmallObject(v: unknown, field: string): Record<string, unknown> {
  if (!isObj(v)) fail(field, `${field} must be an object`);
  if (JSON.stringify(v).length > MAX_OBJECT_JSON) fail(field, `${field} is larger than ${MAX_OBJECT_JSON} characters`);
  return v;
}

export function validServices(v: unknown, field: string): ProfileService[] {
  if (!Array.isArray(v)) fail(field, `${field} must be an array`);
  if (v.length > MAX_SERVICES) fail(field, `${field} has more than ${MAX_SERVICES} entries`);
  return v.map((s, i): ProfileService => {
    const f = `${field}[${i}]`;
    if (!isObj(s)) fail(f, `${f} must be an object`);
    if (typeof s.key !== 'string' || !SERVICE_KEY_RE.test(s.key)) fail(`${f}.key`, 'key must be a service id or cat:<name>');
    if (s.service_id !== null && (typeof s.service_id !== 'string' || !SERVICE_ID_RE.test(s.service_id))) fail(`${f}.service_id`, 'bad service_id');
    if (typeof s.name !== 'string' || !s.name.trim() || chars(s.name) > 120) fail(`${f}.name`, 'name must be 1-120 characters');
    if (s.group !== null && s.group !== undefined && (typeof s.group !== 'string' || s.group.length > 32)) fail(`${f}.group`, 'bad group');
    if (typeof s.sensitive !== 'boolean') fail(`${f}.sensitive`, 'sensitive must be a boolean');
    const status = oneOf(s.status, ['mentioned', 'likely_used'], `${f}.status`);
    for (const k of ['mention_count', 'used_signal_count'] as const) if (!isCount(s[k])) fail(`${f}.${k}`, `${k} must be a non-negative integer`);
    for (const k of ['last_mentioned_at', 'last_used_signal_at'] as const) if (!isMs(s[k] ?? null)) fail(`${f}.${k}`, `${k} must be ms or null`);
    const group = (s.group as string | null | undefined) ?? null;
    return {
      key: s.key,
      service_id: (s.service_id as string | null) ?? null,
      name: s.name.normalize('NFC').trim(),
      group,
      // a health / women service stays sensitive whatever the sender says
      sensitive: s.sensitive || (group !== null && SENSITIVE_GROUPS.includes(group)),
      status,
      mention_count: s.mention_count as number,
      last_mentioned_at: (s.last_mentioned_at as number | null | undefined) ?? null,
      used_signal_count: s.used_signal_count as number,
      last_used_signal_at: (s.last_used_signal_at as number | null | undefined) ?? null,
    };
  });
}

function validEvidence(v: unknown, field: string): ProfileEvidence[] {
  if (!Array.isArray(v)) fail(field, `${field} must be an array`);
  if (v.length > MAX_EVIDENCE) fail(field, `${field} has more than ${MAX_EVIDENCE} entries`);
  return v.map((e, i): ProfileEvidence => {
    const f = `${field}[${i}]`;
    if (!isObj(e)) fail(f, `${f} must be an object`);
    if (!Number.isInteger(e.at) || (e.at as number) < 0) fail(`${f}.at`, 'at must be ms');
    const from = oneOf(e.from, ['contact', 'owner'], `${f}.from`);
    const kind = oneOf(e.kind, ['service', 'booking', 'price'], `${f}.kind`);
    if (typeof e.text !== 'string' || !e.text.trim() || chars(e.text) > EVIDENCE_MAX_CHARS) fail(`${f}.text`, `text must be 1-${EVIDENCE_MAX_CHARS} characters`);
    return { at: e.at as number, from, kind, text: e.text.normalize('NFC') };
  });
}

/** last_service of an import: the analyzer's chat signal, or null. A sensitive key or catalog group stays sensitive. */
export function validLastService(v: unknown, field: string): ProfileLastService | null {
  if (v === null || v === undefined) return null;
  if (!isObj(v)) fail(field, `${field} must be an object or null`);
  const key = v.key ?? null;
  const sid = v.service_id ?? null;
  if (key !== null && (typeof key !== 'string' || !SERVICE_KEY_RE.test(key))) fail(`${field}.key`, 'key must be a service id or cat:<name>');
  if (sid !== null && (typeof sid !== 'string' || !SERVICE_ID_RE.test(sid))) fail(`${field}.service_id`, 'bad service_id');
  if (key === null && sid === null) fail(`${field}.key`, 'key or service_id is required');
  if (typeof v.name !== 'string' || !v.name.trim() || chars(v.name) > 120) fail(`${field}.name`, 'name must be 1-120 characters');
  if (!Number.isInteger(v.at) || (v.at as number) < 0) fail(`${field}.at`, 'at must be ms');
  oneOf(v.source, ['chat'], `${field}.source`);
  const confidence = oneOf(v.confidence, CONFIDENCES, `${field}.confidence`);
  if (v.sensitive !== undefined && typeof v.sensitive !== 'boolean') fail(`${field}.sensitive`, 'sensitive must be a boolean');
  const k = (key as string | null) ?? (sid as string);
  return {
    key: k,
    service_id: sid as string | null,
    name: v.name.normalize('NFC').trim(),
    at: v.at as number,
    source: 'chat',
    confidence,
    sensitive: v.sensitive === true || SENSITIVE_CATEGORY_KEYS.includes(k),
  };
}

export function validateImportProfile(p: unknown, i: number): CustomerProfileImport {
  const f = `profiles[${i}]`;
  if (!isObj(p)) fail(f, `${f} must be an object`);
  if (typeof p.zalo_user_id !== 'string' || !PROFILE_ID_RE.test(p.zalo_user_id)) fail(`${f}.zalo_user_id`, "zalo_user_id must be 'p:' + threadId");
  let display: string | null = null;
  if (p.display_name !== null && p.display_name !== undefined) {
    if (typeof p.display_name !== 'string' || chars(p.display_name) > 100) fail(`${f}.display_name`, 'display_name must be at most 100 characters');
    display = p.display_name.normalize('NFC').trim() || null;
  }
  const reasons = p.relationship_reasons ?? [];
  if (!Array.isArray(reasons) || reasons.length > 20 || reasons.some((r) => typeof r !== 'string' || !REASON_RE.test(r))) {
    fail(`${f}.relationship_reasons`, 'relationship_reasons must be at most 20 reason codes');
  }
  return {
    zalo_user_id: p.zalo_user_id,
    display_name: display,
    relationship: oneOf(p.relationship, RELATIONSHIPS, `${f}.relationship`),
    relationship_confidence: oneOf(p.relationship_confidence, CONFIDENCES, `${f}.relationship_confidence`),
    relationship_reasons: reasons as string[],
    address_term: validAddressTerm(p.address_term ?? null, `${f}.address_term`),
    name_to_use: validName(p.name_to_use ?? null, `${f}.name_to_use`),
    address_confidence: oneOf(p.address_confidence, CONFIDENCES, `${f}.address_confidence`),
    addressing: validSmallObject(p.addressing ?? {}, `${f}.addressing`) as unknown as CustomerProfileImport['addressing'],
    services: validServices(p.services ?? [], `${f}.services`),
    evidence: validEvidence(p.evidence ?? [], `${f}.evidence`),
    stats: validSmallObject(p.stats ?? {}, `${f}.stats`),
    last_service: validLastService(p.last_service, `${f}.last_service`),
  };
}

// ---------------------------------------------------------------- import

/** Columns of each staff field group. */
const STAFF_FIELD_COLUMNS: Record<ProfileStaffField, string[]> = {
  relationship: ['relationship', 'relationship_confidence'],
  address: ['address_term', 'address_confidence'],
  name: ['name_to_use'],
  services: ['services_json'],
};

const IMPORT_SQL =
  'INSERT INTO customer_profiles (zalo_user_id, display_name, relationship, relationship_confidence, relationship_reasons_json, address_term, name_to_use, ' +
  'address_confidence, addressing_json, services_json, evidence_json, stats_json, analyzer_json, analyzer_version, source, staff_override, analyzed_at, ' +
  "created_at, updated_at, updated_by, last_service_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'analyzer',0,?,?,?,?,?) " +
  'ON CONFLICT(zalo_user_id) DO UPDATE SET ' +
  'display_name = COALESCE(excluded.display_name, customer_profiles.display_name), ' +
  'relationship_reasons_json = excluded.relationship_reasons_json, addressing_json = excluded.addressing_json, ' +
  'evidence_json = excluded.evidence_json, stats_json = excluded.stats_json, analyzer_json = excluded.analyzer_json, ' +
  // the analyzer's chat signal is always the latest run's (null clears it); visits are merged at read time
  'last_service_json = excluded.last_service_json, ' +
  'analyzer_version = excluded.analyzer_version, analyzed_at = excluded.analyzed_at, ' +
  // Per group: a group staff edited keeps its values; the other groups take the analyzer's.
  STAFF_FIELDS.flatMap((g) =>
    STAFF_FIELD_COLUMNS[g].map(
      (c) => `${c} = CASE WHEN instr(customer_profiles.staff_fields_json, '"${g}"') > 0 THEN customer_profiles.${c} ELSE excluded.${c} END`,
    ),
  ).join(', ') +
  ', updated_at = excluded.updated_at, updated_by = excluded.updated_by';

function staffFieldsOf(row: { staff_fields_json?: string | null; staff_override?: number } | null | undefined): ProfileStaffField[] {
  if (!row) return [];
  const v = safeJson<unknown>(row.staff_fields_json ?? '[]', []);
  return Array.isArray(v) ? STAFF_FIELDS.filter((f) => v.includes(f)) : [];
}

function analyzerValues(p: CustomerProfileImport): ProfileAnalyzerValues {
  return {
    relationship: p.relationship,
    relationship_confidence: p.relationship_confidence,
    address_term: p.address_term,
    name_to_use: p.name_to_use,
    address_confidence: p.address_confidence,
    services: p.services,
  };
}

/** Validates the whole batch first (422 names the first bad field), then upserts it in one D1 batch. */
export async function importProfiles(env: Env, body: unknown, staffId: string, now = Date.now()): Promise<ProfileImportResponse> {
  if (!isObj(body)) fail('profiles', 'body must be an object with a profiles array');
  const list = body.profiles;
  if (!Array.isArray(list)) fail('profiles', 'profiles must be an array');
  if (list.length > MAX_IMPORT_PROFILES) fail('profiles', `at most ${MAX_IMPORT_PROFILES} profiles per request`);
  const version = body.analyzer_version === undefined ? null : body.analyzer_version;
  if (version !== null && (typeof version !== 'string' || !/^[A-Za-z0-9._-]{1,64}$/.test(version))) fail('analyzer_version', 'bad analyzer_version');
  if (body.generated_at !== undefined && !(Number.isInteger(body.generated_at) && (body.generated_at as number) > 0)) fail('generated_at', 'generated_at must be ms');
  const analyzedAt = (body.generated_at as number | undefined) ?? now;
  const profiles = list.map((p, i) => validateImportProfile(p, i));
  const seen = new Set<string>();
  profiles.forEach((p, i) => {
    if (seen.has(p.zalo_user_id)) fail(`profiles[${i}].zalo_user_id`, 'duplicate zalo_user_id in this request');
    seen.add(p.zalo_user_id);
  });
  if (!profiles.length) return { imported: 0, created: 0, updated: 0, kept_staff_fields: 0 };

  const existing = new Map<string, number>();
  const ids = profiles.map((p) => p.zalo_user_id);
  for (let i = 0; i < ids.length; i += 90) {
    const chunk = ids.slice(i, i + 90);
    const { results } = await orConflict(
      env.DB.prepare(`SELECT zalo_user_id, staff_override FROM customer_profiles WHERE zalo_user_id IN (${chunk.map(() => '?').join(',')})`)
        .bind(...chunk)
        .all<{ zalo_user_id: string; staff_override: number }>(),
    );
    for (const r of results) existing.set(r.zalo_user_id, r.staff_override);
  }
  const stmts = profiles.map((p) =>
    env.DB.prepare(IMPORT_SQL).bind(
      p.zalo_user_id,
      p.display_name,
      p.relationship,
      p.relationship_confidence,
      JSON.stringify(p.relationship_reasons),
      p.address_term,
      p.name_to_use,
      p.address_confidence,
      JSON.stringify(p.addressing),
      JSON.stringify(p.services),
      JSON.stringify(p.evidence),
      JSON.stringify(p.stats),
      JSON.stringify(analyzerValues(p)),
      version,
      analyzedAt,
      now,
      now,
      staffId,
      p.last_service ? JSON.stringify(p.last_service) : null,
    ),
  );
  const res: ProfileImportResponse = {
    imported: profiles.length,
    created: profiles.filter((p) => !existing.has(p.zalo_user_id)).length,
    updated: profiles.filter((p) => existing.has(p.zalo_user_id)).length,
    kept_staff_fields: profiles.filter((p) => existing.get(p.zalo_user_id) === 1).length,
  };
  // Counts only: names, texts and snippets never go into audit_log.
  stmts.push(auditStatement(env, { actor_type: 'staff', actor_id: staffId, action: 'profile.import', entity: 'customer_profile', after: { ...res, analyzer_version: version } }, now));
  await orConflict(env.DB.batch(stmts));
  return res;
}

// ---------------------------------------------------------------- read

const ROW_SELECT =
  'SELECT p.*, cu.id AS customer_id, c.id AS conversation_id FROM customer_profiles p ' +
  "LEFT JOIN customers cu ON cu.zalo_user_id = p.zalo_user_id AND cu.oa_id = 'personal' LEFT JOIN conversations c ON c.customer_id = cu.id";

export async function getProfileRow(env: Env, zaloUserId: string): Promise<ProfileRow | null> {
  return orNoTable(env.DB.prepare(`${ROW_SELECT} WHERE p.zalo_user_id = ?`).bind(zaloUserId).first<ProfileRow>(), null);
}

export interface ModelCatalog {
  catalog_version: string | null;
  byId: Map<string, { group: string; name: string }>;
}

/** Service names and groups of the given (or the active) catalog version. */
export async function loadModelCatalog(env: Env, cv?: string | null): Promise<ModelCatalog> {
  let version = cv ?? null;
  if (!version) {
    const r = await env.DB.prepare("SELECT id FROM catalog_versions WHERE status = 'active'").first<{ id: string }>();
    version = r?.id ?? null;
  }
  const byId = new Map<string, { group: string; name: string }>();
  if (version) {
    const { results } = await env.DB.prepare('SELECT service_id, group_code, display_name_vi FROM services WHERE catalog_version = ?')
      .bind(version)
      .all<{ service_id: string; group_code: string; display_name_vi: string }>();
    for (const s of results) byId.set(s.service_id, { group: s.group_code, name: s.display_name_vi });
  }
  return { catalog_version: version, byId };
}

// ---------------------------------------------------------------- last service (chat signal + recorded visits)

const VISIT_SQL =
  'SELECT cu.zalo_user_id AS zalo_user_id, v.service_id AS service_id, MAX(v.visited_at) AS visited_at FROM visits v ' +
  "JOIN customers cu ON cu.id = v.customer_id WHERE cu.oa_id = 'personal' AND cu.zalo_user_id IN ";

/** The newest staff-recorded visit per profile id (POST /staff/visits writes them; keyed by customer). */
export async function latestVisits(env: Env, zaloUserIds: string[]): Promise<Map<string, VisitRef>> {
  const out = new Map<string, VisitRef>();
  for (let i = 0; i < zaloUserIds.length; i += 90) {
    const chunk = zaloUserIds.slice(i, i + 90);
    // SQLite returns the bare service_id of the row that holds MAX(visited_at)
    const { results } = await env.DB.prepare(`${VISIT_SQL}(${chunk.map(() => '?').join(',')}) GROUP BY cu.zalo_user_id`)
      .bind(...chunk)
      .all<{ zalo_user_id: string; service_id: string; visited_at: number }>();
    for (const r of results) out.set(r.zalo_user_id, { service_id: r.service_id, visited_at: r.visited_at });
  }
  return out;
}

function chatLastService(row: ProfileRow): ProfileLastService | null {
  const ls = safeJson<ProfileLastService | null>(row.last_service_json, null);
  if (!ls || typeof ls !== 'object' || typeof ls.name !== 'string' || !Number.isInteger(ls.at)) return null;
  // Consistent with the services list: a signal whose service is no longer listed as likely used (staff edited the
  // list, or an older import) is dropped.
  const services = safeJson<ProfileService[]>(row.services_json, []);
  const key = ls.key ?? ls.service_id;
  if (!services.some((s) => s && s.status === 'likely_used' && (s.key === key || (!!ls.service_id && s.service_id === ls.service_id)))) return null;
  return { ...ls, key, source: 'chat' };
}

function visitLastService(visit: VisitRef | null | undefined, catalog: ModelCatalog): ProfileLastService | null {
  if (!visit) return null;
  const c = catalog.byId.get(visit.service_id);
  return {
    key: visit.service_id,
    service_id: visit.service_id,
    name: c?.name ?? visit.service_id,
    at: visit.visited_at,
    source: 'visit',
    confidence: 'high',
    // a service unknown to the active catalog is treated as sensitive: its group cannot be checked
    sensitive: !c || SENSITIVE_GROUPS.includes(c.group),
  };
}

/** Staff view: the newer of the chat signal and the newest recorded visit (a visit wins a tie). */
export function mergedLastService(row: ProfileRow, catalog: ModelCatalog, visit?: VisitRef | null): ProfileLastService | null {
  const chat = chatLastService(row);
  const v = visitLastService(visit, catalog);
  if (!chat) return v;
  if (!v) return chat;
  return v.at >= chat.at ? v : chat;
}

/**
 * Model view of the last service: the newer of a recorded visit and a chat signal of confidence medium/high; nothing
 * when that one is sensitive (health / women group, a sensitive category, or a service the catalog does not name), or
 * older than LAST_SERVICE_MODEL_MAX_AGE_MS (180 days). Name and local date only.
 */
function modelLastService(row: ProfileRow, catalog: ModelCatalog, visit?: VisitRef | null, now = Date.now()): { name: string; date: string } | null {
  const chat = chatLastService(row);
  const candidates = [visitLastService(visit, catalog), chat && chat.confidence !== 'low' ? chat : null].filter(
    (x): x is ProfileLastService => !!x,
  );
  if (!candidates.length) return null;
  const pick = candidates.reduce((a, b) => (b.at > a.at || (b.at === a.at && b.source === 'visit') ? b : a));
  if (pick.sensitive || now - pick.at > LAST_SERVICE_MODEL_MAX_AGE_MS) return null;
  let name: string | null;
  if (pick.service_id) {
    const c = catalog.byId.get(pick.service_id);
    name = c && !SENSITIVE_GROUPS.includes(c.group) ? c.name : null;
  } else {
    name = pick.key ? (MODEL_CATEGORY_LABELS[pick.key] ?? null) : null;
  }
  return name ? { name, date: localDate(pick.at) } : null;
}

/**
 * The facts a draft job may carry. Rules: nothing unless relationship is 'customer' or 'unknown' (family, staff,
 * friend and the legacy 'personal' get null); the address term only when its confidence is medium/high (a staff
 * choice of term is stored as 'high'; editing another field does not raise it); the name only with a specific term
 * (not "anh/chị"); service names only from the catalog (health and women groups dropped) or the fixed category
 * labels; at most 5 per list; the last service as name + date (modelLastService). Free text from an import (display
 * name, snippets, reasons) is never passed on.
 */
export function modelFactsFromRow(row: ProfileRow, catalog: ModelCatalog, visit?: VisitRef | null): CustomerProfileForModel | null {
  if (!BOT_RELATIONSHIPS.includes(row.relationship)) return null;
  const term =
    row.address_term && (ADDRESS_TERMS as string[]).includes(row.address_term) && row.address_confidence !== 'low' ? row.address_term : null;
  const name = term && term !== 'anh/chị' && row.name_to_use && NAME_RE.test(row.name_to_use) ? row.name_to_use : null;
  const used: string[] = [];
  const mentioned: string[] = [];
  const services = safeJson<ProfileService[]>(row.services_json, []);
  const labelOf = (s: ProfileService): string | null => {
    if (!s || typeof s !== 'object' || s.sensitive) return null;
    if (s.service_id) {
      const c = catalog.byId.get(s.service_id);
      return c && !SENSITIVE_GROUPS.includes(c.group) ? c.name : null;
    }
    return typeof s.key === 'string' ? (MODEL_CATEGORY_LABELS[s.key] ?? null) : null;
  };
  for (const pass of ['likely_used', 'mentioned'] as const) {
    for (const s of services) {
      if ((s?.status === 'likely_used') !== (pass === 'likely_used')) continue;
      const label = labelOf(s);
      if (!label || used.includes(label) || mentioned.includes(label)) continue;
      const list = pass === 'likely_used' ? used : mentioned;
      if (list.length < MAX_MODEL_SERVICES) list.push(label);
    }
  }
  const last = modelLastService(row, catalog, visit);
  if (!term && !used.length && !mentioned.length && !last) return null;
  return {
    relationship: row.relationship === 'customer' ? 'customer' : 'unknown',
    address_term: term,
    name_to_use: name,
    services_likely_used: used,
    services_mentioned: mentioned,
    ...(last ? { last_service: last } : {}),
  };
}

/**
 * The profile row as the bot reads it under a contact role (docs/contracts.md section 14.3): null for an internal
 * contact (manager, staff), the relationship 'customer' for the role customer (it overrides the analyzer's family /
 * staff / friend / personal), the row itself without a role. Pure.
 */
export function profileRowForBot(row: ProfileRow, role: ContactRole | null | undefined): ProfileRow | null {
  if (isInternalRole(role)) return null;
  return role === 'customer' && row.relationship !== 'customer' ? { ...row, relationship: 'customer' } : row;
}

/**
 * ClaimedJob.customer_profile for a customer (null when there is no usable profile). The contact role is applied
 * first: an internal contact gets null, the role customer is read as relationship 'customer'.
 */
export async function profileFactsForModel(env: Env, zaloUserId: string, cv: string | null): Promise<CustomerProfileForModel | null> {
  const stored = await orNoTable(env.DB.prepare('SELECT * FROM customer_profiles WHERE zalo_user_id = ?').bind(zaloUserId).first<ProfileRow>(), null);
  if (!stored) return null;
  const row = profileRowForBot(stored, (await getContactRole(env, zaloUserId))?.role);
  if (!row || !BOT_RELATIONSHIPS.includes(row.relationship)) return null;
  const visits = await latestVisits(env, [zaloUserId]);
  return modelFactsFromRow(row, await loadModelCatalog(env, cv), visits.get(zaloUserId));
}

/** `roleRow` is the contact_roles row of the contact (null or absent = no role): the view then carries role and role_source. */
export function profileView(
  row: ProfileRow,
  catalog: ModelCatalog,
  visit?: VisitRef | null,
  roleRow?: Pick<ContactRoleRow, 'role' | 'source'> | null,
): CustomerProfileView {
  const botRow = profileRowForBot(row, roleRow?.role);
  return {
    zalo_user_id: row.zalo_user_id,
    thread_id: row.zalo_user_id.startsWith('p:') ? row.zalo_user_id.slice(2) : null,
    customer_id: row.customer_id ?? null,
    conversation_id: row.conversation_id ?? null,
    display_name: row.display_name,
    relationship: row.relationship,
    relationship_confidence: row.relationship_confidence,
    relationship_reasons: safeJson<string[]>(row.relationship_reasons_json, []),
    address_term: row.address_term,
    name_to_use: row.name_to_use,
    address_confidence: row.address_confidence,
    addressing: safeJson(row.addressing_json, {}),
    services: safeJson<ProfileService[]>(row.services_json, []),
    evidence: safeJson<ProfileEvidence[]>(row.evidence_json, []),
    stats: safeJson<Record<string, unknown>>(row.stats_json, {}),
    analyzer: safeJson<ProfileAnalyzerValues | null>(row.analyzer_json, null),
    analyzer_version: row.analyzer_version,
    source: row.source,
    staff_override: row.staff_override === 1,
    staff_fields: staffFieldsOf(row),
    staff_note: row.staff_note,
    analyzed_at: row.analyzed_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
    updated_by: row.updated_by,
    last_service: mergedLastService(row, catalog, visit),
    model_facts: botRow ? modelFactsFromRow(botRow, catalog, visit) : null,
    ...(roleRow ? { role: roleRow.role, role_source: roleRow.source } : {}),
  };
}

export async function getProfileView(env: Env, zaloUserId: string): Promise<CustomerProfileView | null> {
  const row = await getProfileRow(env, zaloUserId);
  if (!row) return null;
  const visits = await latestVisits(env, [zaloUserId]);
  return profileView(row, await loadModelCatalog(env), visits.get(zaloUserId), await getContactRole(env, zaloUserId));
}

export async function listProfiles(
  env: Env,
  q: { relationship?: string; confidence?: string; staff_override?: boolean },
  limit: number,
  offset: number,
): Promise<CustomerProfileView[]> {
  const where: string[] = [];
  const binds: unknown[] = [];
  if (q.relationship) {
    where.push('p.relationship = ?');
    binds.push(q.relationship);
  }
  if (q.confidence) {
    where.push('p.relationship_confidence = ?');
    binds.push(q.confidence);
  }
  if (q.staff_override !== undefined) {
    where.push('p.staff_override = ?');
    binds.push(q.staff_override ? 1 : 0);
  }
  const { results } = await orConflict(
    env.DB.prepare(`${ROW_SELECT}${where.length ? ` WHERE ${where.join(' AND ')}` : ''} ORDER BY p.updated_at DESC, p.zalo_user_id LIMIT ? OFFSET ?`)
      .bind(...binds, limit, offset)
      .all<ProfileRow>(),
  );
  const catalog = await loadModelCatalog(env);
  const visits = await latestVisits(env, results.map((r) => r.zalo_user_id));
  const roles = await getContactRoles(env, results.map((r) => r.zalo_user_id));
  return results.map((r) => profileView(r, catalog, visits.get(r.zalo_user_id), roles.get(r.zalo_user_id)));
}

// ---------------------------------------------------------------- staff edit

const PATCH_KEYS = ['relationship', 'relationship_confidence', 'address_term', 'name_to_use', 'address_confidence', 'services', 'staff_note', 'staff_override'];
const EDIT_KEYS = ['relationship', 'relationship_confidence', 'address_term', 'name_to_use', 'address_confidence', 'services'];

/**
 * Staff correction. Editing a field marks its group (relationship, address, name, services) as staff-owned: later
 * imports keep that group and still refresh the others. `staff_override: true` alone marks all four groups;
 * `staff_override: false` alone clears them and restores the analyzer's latest values. staff_override = 1 exactly when
 * some group is staff-owned. Creates the profile when absent.
 */
export async function patchProfile(env: Env, zaloUserId: string, body: unknown, staffId: string, now = Date.now()): Promise<void> {
  if (!isObj(body)) fail('body', 'body must be an object');
  const b = body as ProfilePatchRequest & Record<string, unknown>;
  for (const k of Object.keys(b)) if (!PATCH_KEYS.includes(k)) fail(k, `unknown field ${k}`);
  const edited = EDIT_KEYS.filter((k) => k in b);
  if (b.staff_override !== undefined && typeof b.staff_override !== 'boolean') fail('staff_override', 'staff_override must be a boolean');
  if (b.staff_override === false && edited.length) fail('staff_override', 'clearing the override cannot be combined with field edits');
  if (!edited.length && b.staff_override === undefined && !('staff_note' in b)) fail('body', 'nothing to change');

  const cur = await orConflict(env.DB.prepare('SELECT * FROM customer_profiles WHERE zalo_user_id = ?').bind(zaloUserId).first<ProfileRow>());
  const next = {
    relationship: cur?.relationship ?? ('unknown' as ProfileRelationship),
    relationship_confidence: cur?.relationship_confidence ?? ('low' as ProfileConfidence),
    address_term: cur?.address_term ?? null,
    name_to_use: cur?.name_to_use ?? null,
    address_confidence: cur?.address_confidence ?? ('low' as ProfileConfidence),
    services_json: cur?.services_json ?? '[]',
    staff_fields: staffFieldsOf(cur),
    staff_note: cur?.staff_note ?? null,
  };
  if ('relationship' in b) {
    next.relationship = oneOf(b.relationship, RELATIONSHIPS, 'relationship');
    next.relationship_confidence = 'high';
  }
  if ('relationship_confidence' in b) next.relationship_confidence = oneOf(b.relationship_confidence, CONFIDENCES, 'relationship_confidence');
  if ('address_term' in b) {
    next.address_term = validAddressTerm(b.address_term, 'address_term');
    next.address_confidence = next.address_term ? 'high' : 'low';
  }
  if ('address_confidence' in b) next.address_confidence = oneOf(b.address_confidence, CONFIDENCES, 'address_confidence');
  if ('name_to_use' in b) next.name_to_use = validName(b.name_to_use, 'name_to_use');
  if ('services' in b) next.services_json = JSON.stringify(validServices(b.services, 'services'));
  if ('staff_note' in b) {
    if (b.staff_note !== null && (typeof b.staff_note !== 'string' || chars(b.staff_note) > 500)) fail('staff_note', 'staff_note must be at most 500 characters');
    next.staff_note = b.staff_note ? b.staff_note.normalize('NFC').trim() || null : null;
  }
  const groups = new Set<ProfileStaffField>(next.staff_fields);
  if ('relationship' in b || 'relationship_confidence' in b) groups.add('relationship');
  if ('address_term' in b || 'address_confidence' in b) groups.add('address');
  if ('name_to_use' in b) groups.add('name');
  if ('services' in b) groups.add('services');
  if (b.staff_override === true) for (const g of STAFF_FIELDS) groups.add(g);
  next.staff_fields = STAFF_FIELDS.filter((g) => groups.has(g));
  if (b.staff_override === false) {
    next.staff_fields = [];
    const a = safeJson<ProfileAnalyzerValues | null>(cur?.analyzer_json, null);
    if (a) {
      next.relationship = a.relationship;
      next.relationship_confidence = a.relationship_confidence;
      next.address_term = a.address_term;
      next.name_to_use = a.name_to_use;
      next.address_confidence = a.address_confidence;
      next.services_json = JSON.stringify(a.services ?? []);
    }
  }
  await orConflict(env.DB.batch([
    env.DB.prepare(
      'INSERT INTO customer_profiles (zalo_user_id, relationship, relationship_confidence, address_term, name_to_use, address_confidence, services_json, ' +
        "staff_override, staff_fields_json, staff_note, source, created_at, updated_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,'staff',?,?,?) " +
        'ON CONFLICT(zalo_user_id) DO UPDATE SET relationship = excluded.relationship, relationship_confidence = excluded.relationship_confidence, ' +
        'address_term = excluded.address_term, name_to_use = excluded.name_to_use, address_confidence = excluded.address_confidence, ' +
        'services_json = excluded.services_json, staff_override = excluded.staff_override, staff_fields_json = excluded.staff_fields_json, ' +
        'staff_note = excluded.staff_note, updated_at = excluded.updated_at, updated_by = excluded.updated_by',
    ).bind(
      zaloUserId,
      next.relationship,
      next.relationship_confidence,
      next.address_term,
      next.name_to_use,
      next.address_confidence,
      next.services_json,
      next.staff_fields.length ? 1 : 0,
      JSON.stringify(next.staff_fields),
      next.staff_note,
      now,
      now,
      staffId,
    ),
    // Field names and enum values only; never the name or the note.
    auditStatement(env, {
      actor_type: 'staff',
      actor_id: staffId,
      action: b.staff_override === false ? 'profile.override_cleared' : 'profile.staff_edit',
      entity: 'customer_profile',
      entity_id: zaloUserId,
      before: cur ? { relationship: cur.relationship, address_term: cur.address_term, staff_override: cur.staff_override, staff_fields: staffFieldsOf(cur) } : null,
      after: { fields: edited, relationship: next.relationship, address_term: next.address_term, staff_override: next.staff_fields.length ? 1 : 0, staff_fields: next.staff_fields },
    }, now),
  ]));
}

// ---------------------------------------------------------------- personal contacts and the bot

/** Whether a profile keeps the contact away from the bot (before consent, flag and release checks). */
export function quietProfile(p: { relationship: string; relationship_confidence: string; staff_override: number } | null | undefined): boolean {
  if (!p || !(QUIET_RELATIONSHIPS as string[]).includes(p.relationship)) return false;
  return p.relationship_confidence === 'high' || p.staff_override === 1;
}

/**
 * The quiet rule of the personal channel: flag profile_personal_skip_bot is true; the profile says family, staff,
 * friend (or the legacy 'personal') with confidence 'high', or with any confidence while staff_override = 1 (staff
 * owns some field of the profile and left that relationship in place); the customer has not granted ai_assistant
 * consent; and staff has not released this conversation out of staff_only before (an explicit "let the bot handle
 * this contact").
 */
export async function personalSkipApplies(env: Env, customer: { id: string; zalo_user_id: string }, conversationId: string): Promise<boolean> {
  const flags = await getFlags(env);
  if (!flags.profile_personal_skip_bot) return false;
  const p = await orNoTable(
    env.DB.prepare('SELECT relationship, relationship_confidence, staff_override FROM customer_profiles WHERE zalo_user_id = ?')
      .bind(customer.zalo_user_id)
      .first<{ relationship: string; relationship_confidence: string; staff_override: number }>(),
    null,
  );
  if (!quietProfile(p)) return false;
  // The role customer (docs/contracts.md section 14.3) overrides the analyzer's relationship: the quiet rule does not fire.
  if ((await getContactRole(env, customer.zalo_user_id))?.role === 'customer') return false;
  if ((await consentStatus(env, customer.id)).ai_assistant?.status === 'granted') return false;
  const released = await env.DB.prepare(
    "SELECT 1 AS x FROM audit_log WHERE entity = 'conversation' AND entity_id = ? AND action = 'conversation.release' AND before_json LIKE '%\"staff_only\"%' LIMIT 1",
  )
    .bind(conversationId)
    .first<{ x: number }>();
  return !released;
}
