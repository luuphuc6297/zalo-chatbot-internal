// Shared helpers of the section 14.5 / 14.6 tests (visits, benefits, phone, customer summary).
// Every name, phone number and id in these tests is synthetic.
import { env } from 'cloudflare:test';
import { DAY_MS, HOUR_MS, localMidnight } from '../src/lib/time';

export const GOI = 'goi-dau-thu-gian'; // hair
export const CHAN = 'massage-chan'; // relaxation
export const BODY = 'massage-body-thu-gian'; // relaxation
export const SENS = 'cham-soc-dau-bung-kinh'; // women (sensitive)
export const HEALTH = 'thai-han-giai-cam'; // health (sensitive)

/** A fixed clock for library calls: 15:00 local on 2026-11-12. */
export const NOW = Date.UTC(2026, 10, 12, 8, 0);
export const T0 = localMidnight(NOW);
/** `daysAgo` local days before NOW at hh:mm local. */
export const at = (daysAgo: number, hh = 10, mm = 0) => T0 - daysAgo * DAY_MS + hh * HOUR_MS + mm * 60_000;
/** For HTTP calls (real clock): `days` (1 or more) local days before today at `hh`:00 local. */
export const past = (days: number, hh = 10) => localMidnight(Date.now()) - days * DAY_MS + hh * HOUR_MS;

let counter = 0;
const pad = (n: number, w: number) => String(n).padStart(w, '0');
export const nextZaloId = () => `p:9300000000${pad(++counter, 5)}`;
export const nextPhone = () => `0907${pad(++counter, 6)}`;

/** Active catalog: service_id -> display name and group. Call after seed(). */
export async function catalog(): Promise<{ names: Record<string, string>; groups: Record<string, string> }> {
  const { results } = await env.DB.prepare(
    "SELECT s.service_id, s.group_code, s.display_name_vi FROM services s JOIN catalog_versions v ON v.id = s.catalog_version WHERE v.status = 'active'",
  ).all<{ service_id: string; group_code: string; display_name_vi: string }>();
  const names: Record<string, string> = {};
  const groups: Record<string, string> = {};
  for (const r of results) {
    names[r.service_id] = r.display_name_vi;
    groups[r.service_id] = r.group_code;
  }
  return { names, groups };
}

export interface NewCustomer {
  zalo_user_id?: string;
  oa_id?: string;
  channel?: string;
  phone?: string | null;
  display_name?: string | null;
  deleted_at?: number | null;
}

export async function newCustomer(over: NewCustomer = {}): Promise<{ id: string; zalo: string }> {
  const zalo = over.zalo_user_id ?? nextZaloId();
  const id = `cus_t${pad(++counter, 5)}`;
  await env.DB.prepare('INSERT INTO customers (id, oa_id, zalo_user_id, display_name, phone, channel, created_at, deleted_at) VALUES (?,?,?,?,?,?,?,?)')
    .bind(id, over.oa_id ?? 'personal', zalo, over.display_name ?? null, over.phone ?? null, over.channel ?? 'personal', 1_700_000_000_000, over.deleted_at ?? null)
    .run();
  return { id, zalo };
}

export interface VisitOver {
  amount?: number | null;
  technician?: string | null;
  service_name?: string | null;
  source?: string;
  external_visit_id?: string | null;
}

export async function addVisit(customerId: string, visitedAt: number, serviceId: string, over: VisitOver = {}): Promise<string> {
  const id = `vis_t${pad(++counter, 5)}`;
  await env.DB.prepare(
    'INSERT INTO visits (id, customer_id, service_id, service_name, visited_at, amount_vnd, technician, source, external_visit_id, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
  )
    .bind(id, customerId, serviceId, over.service_name ?? null, visitedAt, over.amount ?? null, over.technician ?? null, over.source ?? 'staff', over.external_visit_id ?? null, 'tester', visitedAt)
    .run();
  return id;
}

export interface VisitRow {
  id: string;
  customer_id: string;
  service_id: string;
  service_name: string | null;
  visited_at: number;
  duration_min: number | null;
  amount_vnd: number | null;
  technician: string | null;
  benefit_id: string | null;
  source: string;
  external_visit_id: string | null;
  booking_request_id: string | null;
  recorded_by: string | null;
}

export async function visitsOf(customerId: string): Promise<VisitRow[]> {
  const { results } = await env.DB.prepare(
    'SELECT id, customer_id, service_id, service_name, visited_at, duration_min, amount_vnd, technician, benefit_id, source, external_visit_id, booking_request_id, recorded_by FROM visits WHERE customer_id = ? ORDER BY visited_at, id',
  )
    .bind(customerId)
    .all<VisitRow>();
  return results;
}

export const count = async (sql: string, ...binds: unknown[]) => (await env.DB.prepare(sql).bind(...binds).first<{ n: number }>())!.n;
export const jobCount = (customerId: string) => count('SELECT COUNT(*) AS n FROM jobs WHERE customer_id = ?', customerId);
export const auditCount = (action: string) => count('SELECT COUNT(*) AS n FROM audit_log WHERE action = ?', action);

export interface AuditRow {
  actor_type: string;
  actor_id: string | null;
  entity: string | null;
  entity_id: string | null;
  before_json: string | null;
  after_json: string | null;
}

export const lastAudit = (action: string) =>
  env.DB.prepare('SELECT actor_type, actor_id, entity, entity_id, before_json, after_json FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT 1').bind(action).first<AuditRow>();

export async function addRole(zaloId: string, role: 'customer' | 'manager' | 'staff', source: 'zalo_label' | 'staff' = 'zalo_label'): Promise<void> {
  await env.DB.prepare('INSERT INTO contact_roles (zalo_user_id, role, source, updated_at, updated_by) VALUES (?,?,?,?,?)').bind(zaloId, role, source, 1_700_000_000_000, 'tester').run();
}

export interface ProfileOver {
  relationship?: string;
  address_term?: string | null;
  name_to_use?: string | null;
  address_confidence?: string;
  display_name?: string | null;
  services?: unknown[];
}

export async function addProfile(zaloId: string, over: ProfileOver = {}): Promise<void> {
  await env.DB.prepare(
    'INSERT INTO customer_profiles (zalo_user_id, display_name, relationship, relationship_confidence, address_term, name_to_use, address_confidence, services_json, source, created_at, updated_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
  )
    .bind(zaloId, over.display_name ?? null, over.relationship ?? 'customer', 'high', over.address_term ?? null, over.name_to_use ?? null, over.address_confidence ?? 'medium', JSON.stringify(over.services ?? []), 'analyzer', 1_700_000_000_000, 1_700_000_000_000, 'tester')
    .run();
}

export interface BenefitOver {
  kind?: 'package' | 'voucher';
  title?: string;
  service_id?: string | null;
  total?: number;
  used?: number;
  expires_at?: number | null;
  status?: 'active' | 'void';
  created_at?: number;
}

export async function addBenefit(customerId: string, over: BenefitOver = {}): Promise<string> {
  const id = `ben_t${pad(++counter, 5)}`;
  const created = over.created_at ?? 1_700_000_000_000;
  await env.DB.prepare(
    'INSERT INTO customer_benefits (id, customer_id, kind, title, service_id, total_count, used_count, expires_at, status, recorded_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
  )
    .bind(id, customerId, over.kind ?? 'package', over.title ?? 'Gói 10 buổi', over.service_id ?? null, over.total ?? 10, over.used ?? 0, over.expires_at ?? null, over.status ?? 'active', 'tester', created, created)
    .run();
  return id;
}

export const benefitRow = (id: string) =>
  env.DB.prepare('SELECT id, customer_id, kind, title, service_id, total_count, used_count, expires_at, status, recorded_by FROM customer_benefits WHERE id = ?').bind(id).first<{
    id: string;
    customer_id: string;
    kind: string;
    title: string;
    service_id: string | null;
    total_count: number;
    used_count: number;
    expires_at: number | null;
    status: string;
    recorded_by: string;
  }>();
