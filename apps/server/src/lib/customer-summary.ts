// Customer summary (docs/contracts.md section 14.6): one customer's role, visits, rhythm, spend and benefits, as a
// staff view (ConversationDetail.customer_summary) and as a model view (read tool get_customer_profile).
//
// The numbers come from src/lib/customer-status.ts (pure). This file loads the rows, adds the peer gap of a customer
// with a single visit day, resolves names, and applies the privacy rules of section 13 to the model view through the
// helpers of src/lib/profiles.ts.
import type { BenefitKind, BenefitStatus, ContactRole, ContactRoleRow, CustomerBenefit, CustomerFacts, CustomerSummary, Env, RoleSource } from '../types';
import { CHAT_NO_SERVICE, TECHNICIAN_DIGITS_RE, benefitTitleKey, loadChatSummaryInput, mergeChatVisits, type ChatMerge, type SummaryVisitRow } from './chat-facts';
import { computeCustomerStatus, localDayNumber, median, medianGapDays, type CustomerStatusResult, type StatusConfig, type VisitFact } from './customer-status';
import { getCustomer, type CustomerRow } from './db';
import {
  MAX_MODEL_SERVICES,
  QUIET_RELATIONSHIPS,
  SENSITIVE_CATEGORY_WORDS,
  SENSITIVE_GROUPS,
  getProfileRow,
  loadModelCatalog,
  modelFactsFromRow,
  type ModelCatalog,
  type ProfileRow,
} from './profiles';
import { getContactRole, isInternalRole, isMissingMigration0010 } from './roles';
import { stripMarks } from './text';
import { DAY_MS, TZ_OFFSET_MS, envInt, localDate, localMidnight, localMinuteOfDay } from './time';

/** A peer gap needs at least this many other customers. */
export const MIN_PEER_CUSTOMERS = 3;

// ---------------------------------------------------------------- config

/**
 * Status thresholds from the optional env integers CUSTOMER_ABSENT_FACTOR_PCT (200), CUSTOMER_MIN_ABSENT_DAYS (14),
 * CUSTOMER_DEFAULT_GAP_DAYS (45) and CUSTOMER_WINDOW_DAYS (183). A missing, non-numeric or non-positive value gives
 * the default. Reads no table, so a missing migration 0010 does not concern it.
 */
export function statusConfigFromEnv(env: Pick<Env, 'CUSTOMER_ABSENT_FACTOR_PCT' | 'CUSTOMER_MIN_ABSENT_DAYS' | 'CUSTOMER_DEFAULT_GAP_DAYS' | 'CUSTOMER_WINDOW_DAYS'>): StatusConfig {
  const int = (v: string | undefined, fallback: number) => Math.max(1, Math.floor(envInt(v, fallback)));
  return {
    absentFactor: int(env.CUSTOMER_ABSENT_FACTOR_PCT, 200) / 100,
    minAbsentDays: int(env.CUSTOMER_MIN_ABSENT_DAYS, 14),
    defaultGapDays: int(env.CUSTOMER_DEFAULT_GAP_DAYS, 45),
    windowDays: int(env.CUSTOMER_WINDOW_DAYS, 183),
  };
}

// ---------------------------------------------------------------- phone

/**
 * A phone number as stored in customers.phone: digits only, 9 to 11 of them. Spaces, dots, dashes and parentheses are
 * removed, a leading '+84' becomes '0', and so does a leading '84' of an 11-digit number (the country code written
 * without '+'). null for anything else. Pure.
 */
export function normalizePhone(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  let s = v.replace(/[\s.\-()]/g, '');
  if (s.startsWith('+84')) s = `0${s.slice(3)}`;
  if (!/^\d+$/.test(s)) return null;
  if (s.length === 11 && s.startsWith('84')) s = `0${s.slice(2)}`;
  return s.length >= 9 && s.length <= 11 ? s : null;
}

// ---------------------------------------------------------------- benefits

/** A row of customer_benefits (migration 0010). */
export interface BenefitRow {
  id: string;
  customer_id: string;
  kind: BenefitKind;
  title: string;
  service_id: string | null;
  total_count: number;
  used_count: number;
  expires_at: number | null;
  status: BenefitStatus;
  recorded_by: string;
  created_at: number;
  updated_at: number;
}

export const BENEFIT_COLS = 'id, customer_id, kind, title, service_id, total_count, used_count, expires_at, status, recorded_by, created_at, updated_at';

/** The API shape of a benefit row: adds `remaining` and `expires_on` (local date of expires_at). Pure. */
export function benefitView(r: BenefitRow): CustomerBenefit {
  return {
    id: r.id,
    customer_id: r.customer_id,
    kind: r.kind,
    title: r.title,
    service_id: r.service_id,
    total_count: r.total_count,
    used_count: r.used_count,
    remaining: r.total_count - r.used_count,
    expires_at: r.expires_at,
    expires_on: r.expires_at === null ? null : localDate(r.expires_at),
    status: r.status,
    recorded_by: r.recorded_by,
    created_at: r.created_at,
    updated_at: r.updated_at,
  };
}

/**
 * Whether a benefit can pay for a visit at `now`: status 'active', a use left, and not expired. A benefit can be used
 * through the whole local date of expires_at. Pure.
 */
export function benefitUsable(r: Pick<BenefitRow, 'status' | 'total_count' | 'used_count' | 'expires_at'>, now: number): boolean {
  return r.status === 'active' && r.used_count < r.total_count && (r.expires_at === null || r.expires_at >= localMidnight(now));
}

// ---------------------------------------------------------------- role

/**
 * The role shown for a contact: the contact_roles row when there is one, otherwise derived from the section 13
 * relationship of the profile ('customer' and 'staff' only, role_source 'profile'), otherwise null. Pure: pass null
 * for a missing row, profile or table.
 */
export function resolveRole(
  roleRow: Pick<ContactRoleRow, 'role' | 'source'> | null | undefined,
  profile: Pick<ProfileRow, 'relationship'> | null | undefined,
): { role: ContactRole | null; role_source: RoleSource | null } {
  if (roleRow) return { role: roleRow.role, role_source: roleRow.source };
  if (profile?.relationship === 'customer') return { role: 'customer', role_source: 'profile' };
  if (profile?.relationship === 'staff') return { role: 'staff', role_source: 'profile' };
  return { role: null, role_source: null };
}

// ---------------------------------------------------------------- peer gap

/**
 * The usual gap of the customers who use the same service: over the OTHER customers who used one of `serviceIds` and
 * have two or more visit days, the median of their own median gaps (all their visits count, on local dates). null
 * with fewer than MIN_PEER_CUSTOMERS such customers or an empty service list. Throws the D1 error when the visits
 * table is missing; the columns it reads exist before migration 0010.
 */
export async function peerGapDays(env: Env, customerId: string, serviceIds: string[]): Promise<number | null> {
  const ids = [...new Set(serviceIds.filter((s) => typeof s === 'string' && s))].slice(0, 80);
  if (!ids.length) return null;
  // The day number is the one of localDayNumber (customer-status.ts). The two constants are numbers of lib/time.ts,
  // written into the SQL text so that SQLite divides integers.
  const { results } = await env.DB.prepare(
    `SELECT customer_id, CAST((visited_at + ${TZ_OFFSET_MS}) / ${DAY_MS} AS INTEGER) AS day FROM visits ` +
      `WHERE customer_id IN (SELECT customer_id FROM visits WHERE service_id IN (${ids.map(() => '?').join(',')}) AND customer_id != ?) ` +
      'GROUP BY customer_id, day',
  )
    .bind(...ids, customerId)
    .all<{ customer_id: string; day: number }>();
  const days = new Map<string, number[]>();
  for (const r of results) {
    const list = days.get(r.customer_id);
    if (list) list.push(r.day);
    else days.set(r.customer_id, [r.day]);
  }
  const gaps: number[] = [];
  for (const list of days.values()) {
    const g = medianGapDays(list);
    if (g !== null) gaps.push(g);
  }
  return gaps.length >= MIN_PEER_CUSTOMERS ? median(gaps) : null;
}

// ---------------------------------------------------------------- load

/** A recorded visit, or one service of a counted chat guess (from_chat, section 15.12). */
type VisitRow = SummaryVisitRow;

interface CustomerData {
  customer: CustomerRow;
  roleRow: ContactRoleRow | null;
  profile: ProfileRow | null;
  /** newest first; with chat facts, the recorded visits and the counted guesses (mergeChatVisits) */
  visits: VisitRow[];
  /** usable now, soonest expiry first */
  benefits: BenefitRow[];
  status: CustomerStatusResult;
  /** the rows of the last visit day, oldest first */
  lastDayRows: VisitRow[];
  /** null when the contact has no chat facts or migration 0011 is not applied: everything is as before section 15 */
  chat: ChatMerge | null;
}

/** null when the customer does not exist or is deleted. Throws the D1 error when migration 0010 is missing. */
async function loadCustomerData(env: Env, customerId: string, now: number): Promise<CustomerData | null> {
  if (typeof customerId !== 'string' || !customerId) return null;
  const customer = await getCustomer(env, customerId);
  if (!customer || customer.deleted_at) return null;
  const [roleRow, profile, visitRes, benefitRes, chatInput] = await Promise.all([
    getContactRole(env, customer.zalo_user_id),
    getProfileRow(env, customer.zalo_user_id),
    env.DB.prepare('SELECT id, service_id, service_name, visited_at, amount_vnd, technician FROM visits WHERE customer_id = ? ORDER BY visited_at DESC, id')
      .bind(customerId)
      .all<VisitRow>(),
    env.DB.prepare(`SELECT ${BENEFIT_COLS} FROM customer_benefits WHERE customer_id = ? AND status = 'active' ORDER BY (expires_at IS NULL), expires_at, created_at, id`)
      .bind(customerId)
      .all<BenefitRow>(),
    loadChatSummaryInput(env, customer.zalo_user_id),
  ]);
  const hasPhone = typeof customer.phone === 'string' && customer.phone.trim() !== '';
  // a chat benefit with the title of an active recorded benefit is that benefit (benefitRes holds status 'active' only)
  const recordedBenefitKeys = new Set(benefitRes.results.map((b) => benefitTitleKey(b.title)));
  const chat = chatInput ? mergeChatVisits(visitRes.results, chatInput, now, hasPhone, recordedBenefitKeys) : null;
  const visits = chat ? chat.rows : visitRes.results;
  const facts: VisitFact[] = visits.map((v) => ({ visited_at: v.visited_at, service_id: v.service_id, amount_vnd: v.amount_vnd }));
  const config = statusConfigFromEnv(env);
  let status = computeCustomerStatus(facts, now, { config });
  if (status.visits_total === 1) {
    // one visit day: the customer has no rhythm of their own yet, so use the rhythm of the customers of that service
    const serviceIds = visits.map((v) => v.service_id);
    const peer = await peerGapDays(env, customerId, chat ? serviceIds.filter((s) => s !== CHAT_NO_SERVICE) : serviceIds);
    if (peer !== null) status = computeCustomerStatus(facts, now, { config, peerGapDays: peer });
  }
  const lastDay = status.last_visit_at === null ? null : localDayNumber(status.last_visit_at);
  const lastDayRows =
    lastDay === null
      ? []
      : visits.filter((v) => localDayNumber(v.visited_at) === lastDay).sort((a, b) => a.visited_at - b.visited_at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return { customer, roleRow, profile, visits, benefits: benefitRes.results.filter((b) => benefitUsable(b, now)), status, lastDayRows, chat };
}

/**
 * The last visit day is a guess from chat (a day holds either recorded visits or one chat guess, never both). With an
 * unknown time the guess sits at 12:00, which is not a time to show: null.
 */
function lastDayTime(d: CustomerData, lastVisitAt: number): string | null {
  const fromChat = d.lastDayRows.some((r) => r.from_chat);
  return fromChat && d.lastDayRows.every((r) => r.time_known === false) ? null : hhmm(lastVisitAt);
}

/** Service ids of a list, without the marker of a guessed day that names no service (only when chat facts exist). */
const realServices = <T extends { service_id: string }>(d: CustomerData, list: T[]): T[] => (d.chat ? list.filter((s) => s.service_id !== CHAT_NO_SERVICE) : list);

const hhmm = (ms: number): string => {
  const m = localMinuteOfDay(ms);
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
};

const distinct = <T>(list: T[]): T[] => [...new Set(list)];

/** Technicians of a visit day, in time order, joined with ', '. null when none was recorded. */
function technicianOf(rows: VisitRow[]): string | null {
  const names = distinct(rows.map((r) => (r.technician ?? '').trim()).filter(Boolean));
  return names.length ? names.join(', ') : null;
}

// ---------------------------------------------------------------- staff view

/**
 * Staff view of one customer. null when the customer does not exist or is deleted, and null when migration 0010 is
 * not applied (visits has no amount / technician columns, customer_benefits is missing), so a conversation detail
 * built before the migration simply has no summary.
 *
 * `last_visit` describes the last visit DAY: `visited_at` is the newest row of that day, `services` the day's
 * services in time order, `amount_vnd` the sum of the day's known amounts (null when none is known). Service names
 * are the active catalog's display_name_vi, else the name stored with the visit, else the service id.
 */
export async function buildCustomerSummary(env: Env, customerId: string, now: number): Promise<CustomerSummary | null> {
  let d: CustomerData | null;
  let catalog: ModelCatalog;
  try {
    d = await loadCustomerData(env, customerId, now);
    if (!d) return null;
    catalog = await loadModelCatalog(env);
  } catch (e) {
    if (isMissingMigration0010(e)) return null;
    throw e;
  }
  const { customer, profile, status } = d;
  const stored = new Map<string, string>();
  for (const v of d.visits) {
    const n = (v.service_name ?? '').trim();
    if (n && !stored.has(v.service_id)) stored.set(v.service_id, n);
  }
  const nameOf = (id: string): string => catalog.byId.get(id)?.name ?? stored.get(id) ?? id;

  let lastVisit: CustomerSummary['last_visit'] = null;
  if (status.last_visit_at !== null) {
    // same rules as the status: duplicate rows count once, unknown amounts are not 0
    const day = computeCustomerStatus(d.lastDayRows, now).lifetime;
    lastVisit = {
      visited_at: status.last_visit_at,
      date: localDate(status.last_visit_at),
      time: lastDayTime(d, status.last_visit_at),
      services: realServices(d, distinct(d.lastDayRows.map((r) => r.service_id)).map((id) => ({ service_id: id, name: nameOf(id) }))),
      technician: technicianOf(d.lastDayRows),
      amount_vnd: day.spend_visits ? day.spend_vnd : null,
      // section 15.12: only for a contact with chat facts, so the summary of everyone else is unchanged
      ...(d.chat ? { from_chat: d.lastDayRows.some((r) => r.from_chat) } : {}),
    };
  }
  const chat = d.chat;
  return {
    ...resolveRole(d.roleRow, profile),
    name: profile?.name_to_use || customer.display_name || profile?.display_name || null,
    address_term: profile?.address_term ?? null,
    phone: customer.phone || null,
    status: status.status,
    visits_total: status.visits_total,
    last_visit: lastVisit,
    days_since_last_visit: status.days_since_last_visit,
    usual_gap_days: status.usual_gap_days,
    gap_basis: status.gap_basis,
    absent_after_days: status.absent_after_days,
    lifetime_spend_vnd: status.lifetime.spend_vnd,
    lifetime_spend_visits: status.lifetime.spend_visits,
    window: {
      days: status.window.days,
      from_date: localDate(status.window.from),
      visits: status.window.visits,
      spend_vnd: status.window.spend_vnd,
      avg_spend_vnd: status.window.avg_spend_vnd,
      services: realServices(d, status.window.services).map((s) => ({ service_id: s.service_id, name: nameOf(s.service_id), count: s.count })),
    },
    benefits: d.benefits.map((b) => ({
      id: b.id,
      kind: b.kind,
      title: b.title,
      remaining: b.total_count - b.used_count,
      expires_on: b.expires_at === null ? null : localDate(b.expires_at),
    })),
    ...(chat
      ? {
          chat: {
            visits_counted: chat.counted,
            visits_low: chat.low,
            upcoming_next: chat.upcomingNext,
            benefits_active: chat.benefitsActive,
            phone_suggestion: chat.phoneSuggestion,
            analyzer_version: chat.analyzerVersion,
            generated_at: chat.generatedAt,
          },
        }
      : {}),
  };
}

// ---------------------------------------------------------------- model view

const GENERIC_BENEFIT_TITLE: Record<BenefitKind, string> = { package: 'Gói dịch vụ', voucher: 'Voucher' };

/** Folded title with every run of non-letters as one space, padded, so a keyword is matched as whole words. */
const foldedWords = (s: string): string => ` ${stripMarks(s).replace(/[^a-z0-9]+/g, ' ').trim()} `;
const SENSITIVE_WORDS_PADDED = SENSITIVE_CATEGORY_WORDS.map((w) => ` ${w} `);

/**
 * The title of a benefit as the model may see it. The title is free text typed by staff or copied from a chat guess,
 * so it is replaced by a generic one when it could name a sensitive service: the benefit's service is in a health /
 * women group or is not in the catalog (its group cannot be checked), the title contains the name of a service of
 * those groups, or it contains a keyword of their analyzer categories (SENSITIVE_CATEGORY_WORDS, matched as whole words
 * after folding accents). Exported for tests.
 */
export function benefitTitleForModel(b: Pick<BenefitRow, 'kind' | 'title' | 'service_id'>, catalog: ModelCatalog): string {
  const generic = GENERIC_BENEFIT_TITLE[b.kind] ?? GENERIC_BENEFIT_TITLE.package;
  if (b.service_id) {
    const c = catalog.byId.get(b.service_id);
    if (!c || SENSITIVE_GROUPS.includes(c.group)) return generic;
  }
  const title = stripMarks(b.title);
  for (const c of catalog.byId.values()) {
    if (SENSITIVE_GROUPS.includes(c.group) && c.name && title.includes(stripMarks(c.name))) return generic;
  }
  const words = foldedWords(b.title);
  if (SENSITIVE_WORDS_PADDED.some((w) => words.includes(w))) return generic;
  return b.title;
}

/**
 * Model view of the same data (the result of the read tool get_customer_profile). Never throws for missing data:
 *  - `{ found: false, reason: 'no_data' }` when the customer does not exist or is deleted, when migration 0010 is not
 *    applied, and when the contact has no contact_roles row and a section 13 relationship of family, friend or
 *    personal (rule 1 of section 13: nothing about such a contact reaches a model).
 *  - `{ found: false, reason: 'internal_contact' }` for a manager or staff contact (contact_roles row, or no row and
 *    the profile relationship 'staff').
 *  - otherwise `found: true`. A customer without visits and without a profile answers `status: 'first_inquiry'`.
 *
 * Privacy (section 13, through lib/profiles.ts): no phone number, only `has_phone`. `address_term`, `name_to_use`
 * and `services_mentioned` are the ones of modelFactsFromRow (rules 2 to 4); a contact_roles row 'customer' overrides
 * a quiet relationship. A visited service is named only when it is in the catalog `catalogVersion` (the active one
 * when empty) and its group is not health / women; every other service, including 'ext:' ids, is only counted in
 * `other_services`. The last visit has no age cap. Benefit titles: see benefitTitleForModel.
 */
export async function customerFactsForModel(env: Env, customerId: string, catalogVersion: string, now: number): Promise<CustomerFacts> {
  let d: CustomerData | null;
  let catalog: ModelCatalog;
  try {
    d = await loadCustomerData(env, customerId, now);
    if (!d) return { found: false, reason: 'no_data' };
    catalog = await loadModelCatalog(env, catalogVersion || null);
  } catch (e) {
    if (isMissingMigration0010(e)) return { found: false, reason: 'no_data' };
    throw e;
  }
  const { customer, profile, roleRow, status } = d;
  const { role } = resolveRole(roleRow, profile);
  if (isInternalRole(role)) return { found: false, reason: 'internal_contact' };
  if (!roleRow && profile && QUIET_RELATIONSHIPS.includes(profile.relationship)) return { found: false, reason: 'no_data' };

  // Rules 2 to 4 of section 13 live in modelFactsFromRow. A 'customer' role overrides the stored relationship (14.3).
  const facts = profile ? modelFactsFromRow(roleRow?.role === 'customer' ? { ...profile, relationship: 'customer' } : profile, catalog) : null;
  // Rule 4 for a visited service. Mirrors labelOf inside modelFactsFromRow (lib/profiles.ts), which is not exported.
  const modelName = (id: string): string | null => {
    const c = catalog.byId.get(id);
    return c && !SENSITIVE_GROUPS.includes(c.group) ? c.name : null;
  };

  let lastVisit: Extract<CustomerFacts, { found: true }>['last_visit'] = null;
  if (status.last_visit_at !== null) {
    const ids = distinct(d.lastDayRows.map((r) => r.service_id)).filter((id) => !d.chat || id !== CHAT_NO_SERVICE);
    const names = distinct(ids.map(modelName).filter((n): n is string => !!n));
    const fromChat = d.lastDayRows.some((r) => r.from_chat);
    const technician = technicianOf(d.lastDayRows);
    lastVisit = {
      date: localDate(status.last_visit_at),
      time: lastDayTime(d, status.last_visit_at),
      services: names,
      other_services: ids.filter((id) => !modelName(id)).length,
      // a technician read from a chat reaches the model only without a run of 3 or more digits (section 15.12)
      technician: fromChat && technician && TECHNICIAN_DIGITS_RE.test(technician) ? null : technician,
      ...(d.chat ? { from_chat: fromChat } : {}),
    };
  }
  const usual: Array<{ name: string; count: number }> = [];
  let other = 0;
  for (const s of realServices(d, status.window.services)) {
    const name = modelName(s.service_id);
    if (name && usual.length < MAX_MODEL_SERVICES) usual.push({ name, count: s.count });
    else other += 1;
  }
  const chat = d.chat;
  return {
    found: true,
    role,
    address_term: facts?.address_term ?? null,
    name_to_use: facts?.name_to_use ?? null,
    has_phone: typeof customer.phone === 'string' && customer.phone.trim() !== '',
    status: status.status,
    visits_total: status.visits_total,
    last_visit: lastVisit,
    days_since_last_visit: status.days_since_last_visit,
    usual_gap_days: status.usual_gap_days,
    gap_basis: status.gap_basis,
    absent_after_days: status.absent_after_days,
    window: {
      days: status.window.days,
      visits: status.window.visits,
      spend_vnd: status.window.spend_vnd,
      avg_spend_vnd: status.window.avg_spend_vnd,
      usual_services: usual,
      other_services: other,
    },
    lifetime: { spend_vnd: status.lifetime.spend_vnd, spend_visits: status.lifetime.spend_visits },
    unused_benefits: d.benefits.map((b) => ({
      kind: b.kind,
      title: benefitTitleForModel(b, catalog),
      remaining: b.total_count - b.used_count,
      expires_on: b.expires_at === null ? null : localDate(b.expires_at),
    })),
    services_mentioned: facts?.services_mentioned ?? [],
    // section 15.12: only for a contact with chat facts. Chat benefits as kind and count, never the title; no phone.
    ...(chat
      ? {
          visits_from_chat: chat.counted,
          next_booking_from_chat: chat.upcomingNext,
          benefits_from_chat: chat.benefitsForModel,
        }
      : {}),
  };
}
