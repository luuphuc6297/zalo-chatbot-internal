// Shared helpers of the section 15 tests (customer facts guessed from old chats): analyzer documents, calls that run
// in the test's own isolate (so console spies see the worker's log lines), and readers of the three chat tables.
// Every name, phone number, id and date is synthetic.
import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { app } from '../src/index';
import { localDate } from '../src/lib/time';

export const VERSION = 'visits-rules-v1';
export const GENERATED_AT = Date.UTC(2026, 10, 12, 1, 0);

/** A staff call through app.fetch with X-Staff-Id 'tester'. `raw` sends a body as it is. */
export async function call(method: string, path: string, body?: unknown, raw?: string): Promise<{ status: number; body: any }> {
  const ctx = createExecutionContext();
  const res = await app.fetch(
    new Request(`https://bot.test${path}`, {
      method,
      headers: { 'content-type': 'application/json', authorization: 'Bearer test-staff-token', 'x-staff-id': 'tester' },
      ...(raw !== undefined ? { body: raw } : body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return { status: res.status, body: (await res.json()) as any };
}

export const enc = (zalo: string) => encodeURIComponent(zalo);

export interface CandOver {
  time?: string | null;
  services?: unknown[];
  amount_vnd?: number | null;
  amount_source?: string | null;
  technician?: string | null;
  confidence?: string | null;
  signals?: string[];
  evidence_at?: number[];
  source?: string;
  visited_at_local?: string;
}

/** A visit candidate of the analyzer (section 15.4) on `date`. */
export function cand(date: string, over: CandOver = {}): Record<string, unknown> {
  const time = over.time === undefined ? '15:00' : over.time;
  const c: Record<string, unknown> = {
    date,
    time,
    time_known: time !== null,
    visited_at_local: over.visited_at_local ?? `${date} ${time ?? '12:00'}`,
    services: over.services ?? [{ service_id: 'goi-dau-thu-gian', service_name: null, basis: 'booking' }],
    amount_vnd: over.amount_vnd === undefined ? 350000 : over.amount_vnd,
    amount_source: over.amount_source === undefined ? 'paid' : over.amount_source,
    technician: over.technician === undefined ? 'Lan' : over.technician,
    confidence: over.confidence === undefined ? 'high' : over.confidence,
    signals: over.signals ?? ['booking_confirmed', 'arrival', 'payment'],
    evidence_at: over.evidence_at ?? [GENERATED_AT - 86_400_000],
    source: over.source ?? 'chat_rules',
  };
  if (c.confidence === null) delete c.confidence;
  return c;
}

/** An upcoming booking: same shape, no confidence. */
export function upcoming(date: string, over: CandOver = {}): Record<string, unknown> {
  return cand(date, { amount_vnd: null, amount_source: null, technician: null, signals: ['booking_confirmed'], ...over, confidence: null });
}

export function benefit(title: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return { kind: 'package', title, service_id: null, total_count: 10, remaining: 7, stated_by: 'owner', confidence: 'high', at: GENERATED_AT - 5 * 86_400_000, ...over };
}

export const phone = (value: string, confidence: 'high' | 'medium' = 'medium') => ({ value, confidence, source: 'chat', at: GENERATED_AT - 86_400_000 });

/** One customer entry of the analyzer document (section 15.4). */
export function entry(zalo: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    zalo_user_id: zalo,
    relationship: 'customer',
    relationship_confidence: 'high',
    messages: 120,
    first_at: GENERATED_AT - 200 * 86_400_000,
    last_at: GENERATED_AT - 86_400_000,
    visits: [],
    upcoming: [],
    phone: null,
    benefits: [],
    model_pass: { ran: false, reason: 'disabled' },
    ...over,
  };
}

export function doc(customers: unknown[], over: Record<string, unknown> = {}): Record<string, unknown> {
  return { analyzer_version: VERSION, generated_at: GENERATED_AT, dry_run: false, customers, ...over };
}

export const push = (body: unknown) => call('POST', '/staff/chat-facts/import', body);

/** The counters of a response that are not 0 or false (plus customers, so an empty answer is visible). */
export function nonZero(r: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(r).filter(([k, v]) => k === 'customers' || (v !== 0 && v !== false)));
}

export interface ChatVisitDb {
  id: string;
  zalo_user_id: string;
  local_date: string;
  kind: string;
  visited_at: number;
  time_known: number;
  services_json: string;
  amount_vnd: number | null;
  amount_source: string | null;
  technician: string | null;
  confidence: string | null;
  signals_json: string;
  evidence_json: string;
  fact_source: string;
  state: string;
  confirmed_visit_id: string | null;
  analyzer_version: string;
  imported_at: number;
  decided_by: string | null;
  decided_at: number | null;
}

export async function chatVisitsOf(zalo: string): Promise<ChatVisitDb[]> {
  return (await env.DB.prepare('SELECT * FROM chat_visits WHERE zalo_user_id = ? ORDER BY kind, local_date').bind(zalo).all<ChatVisitDb>()).results;
}

export async function chatBenefitsOf(zalo: string): Promise<Array<Record<string, any>>> {
  return (await env.DB.prepare('SELECT * FROM chat_benefits WHERE zalo_user_id = ? ORDER BY title_key').bind(zalo).all<Record<string, any>>()).results;
}

export async function factsOf(zalo: string): Promise<Record<string, any> | null> {
  return env.DB.prepare('SELECT * FROM chat_contact_facts WHERE zalo_user_id = ?').bind(zalo).first<Record<string, any>>();
}

/** Every row of the three chat tables, for "nothing changed" checks. */
export async function chatSnapshot(): Promise<unknown[]> {
  const out: unknown[] = [];
  for (const t of ['chat_visits ORDER BY id', 'chat_benefits ORDER BY id', 'chat_contact_facts ORDER BY zalo_user_id']) {
    out.push((await env.DB.prepare(`SELECT * FROM ${t}`).all()).results);
  }
  return out;
}

export async function setChatState(table: 'chat_visits' | 'chat_benefits', id: string, state: string): Promise<void> {
  await env.DB.prepare(`UPDATE ${table} SET state = ?, decided_by = 'tester', decided_at = 1 WHERE id = ?`).bind(state, id).run();
}

export async function addConsent(customerId: string, status: 'granted' | 'withdrawn', recordedAt: number, purpose = 'ai_assistant'): Promise<void> {
  await env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, recorded_at) VALUES (?,?,?,?,'staff',?)")
    .bind(`cns_${crypto.randomUUID().replace(/-/g, '')}`, customerId, purpose, status, recordedAt)
    .run();
}

/** Local date `days` days before (negative: after) the local date of `ms`. */
export const dayOf = (ms: number, days = 0) => localDate(ms - days * 86_400_000);
