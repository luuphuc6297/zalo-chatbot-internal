// Typed client for the staff API, written by hand from docs/contracts.md ("Staff API").
// Keep in sync with apps/server/src/types.ts (the server is the source of truth).

export type Ms = number;

export type BotState = 'awaiting_consent' | 'bot_active' | 'handoff_requested' | 'staff_takeover' | 'staff_only' | 'blocked';
export type ConversationMode = 'off' | 'draft_only' | 'approve_each' | 'auto_allowed';
export type AiEngine = 'subscription' | 'api_key' | 'off';
export type MessageSource = 'customer' | 'bot' | 'staff' | 'server';
export type SendState = 'not_applicable' | 'pending' | 'sent' | 'unknown' | 'failed';
export type DraftStatus = 'pending' | 'approved' | 'rejected' | 'sent' | 'blocked' | 'superseded' | 'discarded' | 'send_failed';
export type BookingStatus = 'new' | 'proposed' | 'confirmed' | 'cancelled' | 'expired';
export type JobStatus = 'queued' | 'leased' | 'done' | 'failed' | 'cancelled' | 'expired' | 'skipped' | 'needs_staff';

export interface Flags {
  auto_reply_mode: ConversationMode;
  ai_calls_enabled: boolean;
  ai_engine: AiEngine;
  scheduled_sends_enabled: boolean;
  outbound_enabled: boolean;
  promotions_enabled: boolean;
  runner_desired_account: string;
  // contact profiles: true (default) = family, staff and friends (profile confidence high, or set by staff) who have not
  // agreed to the AI assistant become staff_only on their next message, without a consent prompt
  profile_personal_skip_bot?: boolean; // absent on servers before 2026-11-08
  // two-bot rooms (docs/contracts.md section 14.7): true = the server feeds the rooms; absent on servers before 2026-11-12
  rooms_enabled?: boolean;
}
export type FlagName = keyof Flags;
export interface FlagsResponse {
  flags: Flags;
  updated: Partial<Record<FlagName, { by: string; at: Ms }>>;
}

export interface Attachment {
  type: string;
  url?: string;
  thumbnail?: string;
  name?: string;
}

export interface CustomerView {
  id: string;
  zalo_user_id: string;
  display_name: string | null;
  phone: string | null;
  minor_flag: boolean | null;
  last_user_interaction_at: Ms | null;
}

export interface ConversationSummary {
  id: string;
  customer: CustomerView;
  bot_state: BotState;
  mode_override: ConversationMode | null;
  effective_mode: ConversationMode;
  needs_attention: boolean;
  takeover_by: string | null;
  takeover_until: Ms | null;
  last_message_at: Ms | null;
  last_message_preview: string | null;
  pending_drafts: number;
  open_handoffs: number;
  // section 14 (absent on servers before 2026-11-12, and emitted only when they have a value)
  auto_reply?: 'on' | 'off'; // the per-conversation switch; the console shows it as on when effective_mode is auto_allowed
  role?: ContactRole | null;
  role_source?: RoleSource | null;
}

export interface MessageView {
  id: string;
  direction: 'inbound' | 'outbound';
  source: MessageSource;
  kind: string;
  text: string | null;
  attachments: Attachment[];
  send_state: SendState;
  draft_id: string | null;
  staff_id: string | null;
  created_at: Ms;
  sent_at: Ms | null;
}

export interface CheckerIssue {
  rule: 'price' | 'forbidden_term' | 'format' | 'contact_info' | 'booking_promise' | 'state' | 'length' | 'empty' | 'menu_image';
  detail: string;
  excerpt?: string;
}
export interface CheckerResult {
  passed: boolean;
  issues: CheckerIssue[];
  checked_at: Ms;
}

export interface DraftView {
  id: string;
  job_id: string;
  conversation_id: string;
  text: string;
  final_text: string | null;
  status: DraftStatus;
  checker: CheckerResult;
  account_label: string | null;
  cost_usd_equiv: number | null;
  catalog_version: string | null;
  created_at: Ms;
  decided_by: string | null;
  decided_at: Ms | null;
  attachments?: string[]; // menu image keys the model attached ('<group>/<n>'); sent as one image message after the text
}

export interface HandoffView {
  id: string;
  conversation_id: string;
  customer_display_name: string | null;
  source: 'model_tool' | 'server' | 'runner_failure' | 'staff';
  reason_code: string;
  urgency: 'urgent' | 'normal';
  summary_for_staff: string | null;
  status: 'open' | 'resolved';
  created_at: Ms;
  resolved_by: string | null;
  resolved_at: Ms | null;
}

export interface BookingRequestView {
  id: string;
  conversation_id: string;
  customer_display_name: string | null;
  service_ids: string[];
  duration_min: number;
  preferred_date_local: string;
  preferred_time_window: string;
  party_size: number;
  customer_name: string;
  contact_method: 'zalo_chat_only' | 'phone_shared_with_consent';
  phone: string | null;
  notes_for_staff: string | null;
  price_quoted_text: string | null;
  status: BookingStatus;
  staff_note: string | null;
  created_at: Ms;
  updated_at: Ms;
}

export interface ConsentView {
  purpose: 'ai_assistant' | 'followup_care' | 'promotions' | 'health_data';
  status: 'granted' | 'withdrawn' | 'none';
  recorded_at: Ms | null;
}

export interface ConversationDetail {
  conversation: ConversationSummary & { session_id: string | null; session_turns: number; catalog_version: string | null };
  messages: MessageView[];
  drafts: DraftView[];
  handoffs: HandoffView[];
  booking_requests: BookingRequestView[];
  consents: ConsentView[];
  // contact profiles (docs/contracts.md section 13); absent on servers before 2026-11-08, null when there is none
  profile?: CustomerProfileView | null;
  // section 14.6; absent on servers before 2026-11-12 and when migration 0010 is not applied
  customer_summary?: CustomerSummary | null;
  // section 14.7; present only when the conversation has a two-bot room
  room?: ConversationRoom | null;
}

// ---------------------------------------------------------------- roles, customer summary, visits, benefits (docs/contracts.md section 14)

/** 'manager' and 'staff' are internal contacts: the server stores their messages and does nothing else. */
export type ContactRole = 'customer' | 'manager' | 'staff';
/** Where a role comes from: a Zalo label, a value staff set in the console, or derived from the section 13 profile. */
export type RoleSource = 'zalo_label' | 'staff' | 'profile';

export interface ContactRoleRow {
  zalo_user_id: string;
  role: ContactRole;
  source: 'zalo_label' | 'staff';
  updated_at: Ms;
  updated_by: string;
}

export interface ConversationRoom {
  channel_id: string;
  synced_at?: Ms | null;
  pending?: number;
}

export type CustomerStatus = 'first_inquiry' | 'first_visit_done' | 'returning' | 'long_absent';

export interface SummaryService {
  service_id: string | null;
  name: string;
  count?: number;
}

export interface SummaryLastVisit {
  visited_at: Ms;
  date?: string; // 'YYYY-MM-DD', Vietnam time
  time?: string | null; // 'HH:MM', Vietnam time; null for a day guessed from old chat whose time is unknown (15.12)
  services?: SummaryService[];
  technician?: string | null;
  amount_vnd?: number | null;
  // section 15.12: true when the last visit day is a guess from old chat that staff have not confirmed
  from_chat?: boolean;
}

/**
 * `customer_summary.chat` (section 15.12): what the figures of the summary took from old chat. Absent on servers
 * before section 15; null when the contact has no chat facts.
 */
export interface SummaryChat {
  visits_counted?: number; // guessed visits (high or medium, still active) counted in visits_total and the window
  visits_low?: number; // active guesses with confidence low: never counted
  upcoming_next?: { date: string; time?: string | null } | null;
  benefits_active?: number;
  phone_suggestion?: boolean; // the number itself only comes from GET /staff/chat-facts/:zalo_user_id
  analyzer_version?: string | null;
  generated_at?: Ms | null;
}

export interface SummaryWindow {
  days: number;
  from_date?: string; // 'YYYY-MM-DD'
  visits?: number;
  spend_vnd?: number | null;
  avg_spend_vnd?: number | null;
  services?: SummaryService[];
}

export interface SummaryBenefit {
  id: string;
  kind: BenefitKind;
  title: string;
  remaining: number;
  expires_on?: string | null; // 'YYYY-MM-DD'
}

/** `customer_summary` of a conversation detail. Every field is optional: the console is coded against the contract text. */
export interface CustomerSummary {
  role?: ContactRole | null;
  role_source?: RoleSource | null;
  name?: string | null;
  address_term?: string | null;
  phone?: string | null;
  status?: CustomerStatus;
  visits_total?: number;
  last_visit?: SummaryLastVisit | null;
  days_since_last_visit?: number | null;
  usual_gap_days?: number | null;
  gap_basis?: 'own' | 'service_peers' | 'default' | null;
  absent_after_days?: number | null;
  lifetime_spend_vnd?: number | null;
  lifetime_spend_visits?: number | null; // how many visits have an amount
  window?: SummaryWindow | null;
  benefits?: SummaryBenefit[];
  chat?: SummaryChat | null; // section 15.12
}

export type BenefitKind = 'package' | 'voucher';

export interface CustomerBenefit {
  id: string;
  customer_id: string;
  kind: BenefitKind;
  title: string;
  service_id?: string | null;
  total_count: number;
  used_count: number;
  remaining?: number; // total_count - used_count
  expires_at?: Ms | null;
  status: 'active' | 'void';
  recorded_by?: string | null;
  created_at?: Ms;
  updated_at?: Ms;
}

export interface BenefitCreateRequest {
  customer_id: string;
  kind: BenefitKind;
  title: string;
  service_id?: string;
  total_count: number;
  used_count?: number;
  expires_at?: Ms | null;
}

export interface BenefitPatchRequest {
  title?: string;
  used_count?: number;
  expires_at?: Ms | null;
  status?: 'active' | 'void';
}

/** One recorded visit of GET /staff/visits?customer_id= (column names of migration 0010). */
export interface VisitView {
  id: string;
  customer_id: string;
  service_id: string | null;
  service_name?: string | null;
  name?: string; // the server's name: catalog display name, else the stored service_name, else the service_id
  visited_at: Ms;
  duration_min?: number | null;
  amount_vnd?: number | null;
  technician?: string | null;
  benefit_id?: string | null;
  source?: 'staff' | 'booking_app' | 'booking_request' | 'import';
  recorded_by?: string | null;
  created_at?: Ms;
}

// ---------------------------------------------------------------- facts guessed from old chat (section 15.9 to 15.13)
// Written from the contract text while the server side was being built, then checked against apps/server/src/types.ts
// (ChatVisitView, ChatBenefitView, ChatFactsView) on 2026-11-12: every field the console does not strictly need is
// optional and read leniently (see screens/ChatFacts.tsx).

export type ChatConfidence = 'high' | 'medium' | 'low';
export type ChatAmountSource = 'paid' | 'quoted' | 'list_price';
export type ChatFactState = 'active' | 'confirmed' | 'dismissed';

export interface ChatVisitService {
  service_id: string | null; // a catalog id, or null with a service_name (a catalog category keyword)
  service_name?: string | null;
  name?: string | null; // resolved by the server from the active catalog, like GET /staff/visits
  basis?: string; // 'booking' | 'visit_day' | 'window'
}

/** One row of `chat_visits`: a guessed visit (`kind = 'visit'`) or an upcoming booking (`kind = 'upcoming'`). */
export interface ChatVisitView {
  id: string;
  zalo_user_id?: string;
  local_date?: string; // 'YYYY-MM-DD', Vietnam time
  kind?: 'visit' | 'upcoming';
  visited_at?: Ms; // 12:00 local when the time is not known
  time_known?: boolean | number;
  time?: string | null; // 'HH:MM' when a server sends it; otherwise derived from visited_at and time_known
  services?: ChatVisitService[];
  amount_vnd?: number | null;
  amount_source?: ChatAmountSource | null;
  technician?: string | null;
  confidence?: ChatConfidence | null; // null for an upcoming booking
  signals?: string[];
  evidence?: Ms[]; // times of the messages the guess rests on (the server never sends the texts)
  fact_source?: string; // 'chat_rules' | 'chat_model' | 'chat_rules+model'
  state: ChatFactState;
  confirmed_visit_id?: string | null;
  analyzer_version?: string;
  imported_at?: Ms;
  decided_by?: string | null;
  decided_at?: Ms | null;
  // GET only, after the review of 2026-11-12: the customer has a recorded visit on local_date, so the guess is not
  // counted and the server refuses to confirm it
  recorded_day?: boolean;
}

/** One row of `chat_benefits`: a package or voucher the chat mentions. */
export interface ChatBenefitView {
  id: string;
  zalo_user_id?: string;
  kind: BenefitKind;
  title: string;
  title_key?: string; // the server's identity of the benefit across analyzer runs
  service_id?: string | null;
  service_name?: string | null; // the active catalog's name of service_id
  total_count?: number | null;
  remaining?: number | null;
  stated_by?: 'owner' | 'contact';
  confidence?: 'high' | 'medium';
  stated_at?: Ms;
  state: ChatFactState;
  confirmed_benefit_id?: string | null;
  analyzer_version?: string;
  imported_at?: Ms;
  decided_by?: string | null;
  decided_at?: Ms | null;
  // GET only, after the review of 2026-11-12: an active benefit of the customer has the same title, so the server
  // refuses to confirm this one under that title
  recorded_title?: boolean;
}

/** GET /staff/chat-facts/:zalo_user_id: every row of every state, so the console can show what staff decided. */
export interface ChatFacts {
  visits?: ChatVisitView[];
  upcoming?: ChatVisitView[];
  benefits?: ChatBenefitView[];
  phone_suggestion?: string | null; // staff only; the console masks it until "Hiện số"
  analyzer_version?: string | null;
  generated_at?: Ms | null;
  imported_at?: Ms | null;
  model_pass?: { ran?: boolean; reason?: string | null } | null;
}

/** Corrections staff make before confirming a guessed visit; a field left out keeps the guessed value. */
export interface ChatVisitConfirmRequest {
  service_id?: string;
  amount_vnd?: number | null; // null: staff emptied a guessed amount
  technician?: string | null; // null: staff emptied a guessed technician
  visited_at_local?: string; // 'YYYY-MM-DD HH:MM', Vietnam time
}

export interface ChatBenefitConfirmRequest {
  title?: string;
  total_count: number;
  used_count?: number;
  expires_at?: Ms | null;
}

// ---------------------------------------------------------------- contact profiles (docs/contracts.md section 13)

// 'personal' is the legacy label of profiles imported before 2026-11-08 (analyzer v1/v2)
export type ProfileRelationship = 'customer' | 'staff' | 'family' | 'friend' | 'personal' | 'unknown';
export type ProfileConfidence = 'low' | 'medium' | 'high';
export type ProfileAddressTerm = 'chị' | 'anh' | 'cô' | 'chú' | 'bác' | 'anh/chị';
/** Field groups staff edited; an analyzer import keeps them as staff left them. */
export type ProfileStaffField = 'relationship' | 'address' | 'name' | 'services';

export interface ProfileService {
  key: string; // service id, or 'cat:<category>'
  service_id: string | null;
  name: string;
  group: string | null;
  sensitive: boolean; // health / women group: never shown to the model
  status: 'mentioned' | 'likely_used';
  mention_count: number;
  last_mentioned_at: Ms | null;
  used_signal_count: number;
  last_used_signal_at: Ms | null;
}

export interface ProfileEvidence {
  at: Ms;
  from: 'contact' | 'owner';
  kind: 'service' | 'booking' | 'price';
  text: string; // <= 80 chars, phone numbers masked; staff console only
}

export interface ProfileAddressing {
  owner_calls_contact?: Record<string, number>;
  contact_calls_self?: Record<string, number>;
  contact_calls_owner?: Record<string, number>;
  owner_calls_self?: Record<string, number>;
  name_prefix?: string | null;
  basis?: Record<string, unknown>;
}

/** Analyzer stats (scripts/analyze_contacts.py). Every key may be missing on a profile staff created. */
export interface ProfileStats {
  messages_in?: number;
  messages_out?: number;
  text_in?: number;
  text_out?: number;
  first_at?: Ms | null;
  last_at?: Ms | null;
  first_writer?: 'contact' | 'owner' | null;
  active_days?: number;
  [key: string]: unknown;
}

export interface ProfileAnalyzerValues {
  relationship: ProfileRelationship;
  relationship_confidence: ProfileConfidence;
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  address_confidence: ProfileConfidence;
  services: ProfileService[];
}

/** The newest service the contact likely used: the analyzer's chat signal merged with the newest recorded visit. */
export interface ProfileLastService {
  key: string | null;
  service_id: string | null;
  name: string;
  at: Ms;
  source: 'chat' | 'visit';
  confidence: ProfileConfidence;
  sensitive: boolean; // health / women group: never shown to the model
}

export interface CustomerProfileForModel {
  relationship: 'customer' | 'unknown';
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  services_likely_used: string[];
  services_mentioned: string[];
  last_service?: { name: string; date: string } | null; // date 'YYYY-MM-DD'
}

export interface CustomerProfileView {
  zalo_user_id: string;
  thread_id: string | null;
  customer_id: string | null;
  conversation_id: string | null;
  display_name: string | null;
  relationship: ProfileRelationship;
  relationship_confidence: ProfileConfidence;
  relationship_reasons: string[];
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  address_confidence: ProfileConfidence;
  addressing: ProfileAddressing;
  services: ProfileService[];
  evidence: ProfileEvidence[];
  stats: ProfileStats;
  analyzer: ProfileAnalyzerValues | null;
  analyzer_version: string | null;
  source: 'analyzer' | 'staff';
  staff_override: boolean;
  staff_fields?: ProfileStaffField[]; // absent on servers before 2026-11-08 evening
  staff_note: string | null;
  analyzed_at: Ms | null;
  created_at: Ms;
  updated_at: Ms;
  updated_by: string;
  last_service?: ProfileLastService | null; // absent on servers before 2026-11-08 evening
  model_facts: CustomerProfileForModel | null; // exactly what a draft job for this customer would carry now
  // section 14.3; absent on servers before 2026-11-12
  role?: ContactRole | null;
  role_source?: RoleSource | null;
}

/** PATCH /staff/profiles/:zalo_user_id. An edited field marks its group as staff-owned; `{ staff_override: false }` alone clears all. */
export interface ProfilePatchRequest {
  relationship?: ProfileRelationship;
  relationship_confidence?: ProfileConfidence;
  address_term?: ProfileAddressTerm | null;
  name_to_use?: string | null;
  address_confidence?: ProfileConfidence;
  services?: ProfileService[];
  staff_note?: string | null;
  staff_override?: boolean;
}

export interface ListResponse<T> {
  items: T[];
  next_cursor: string | null;
}

export interface PoolAccountStatus {
  label: string;
  priority: number | null;
  enabled: boolean;
  pinned: boolean;
  pool_status: 'ok' | 'limited' | 'login_expired' | 'blocked' | 'error';
  until: string | null;
  usable_now: boolean;
  login: { loggedIn?: boolean; email?: string | null; subscriptionType?: string | null } | null;
  last_error: string;
  last_ok: string | null;
}

export interface RunnerStatusSnapshot {
  runner_version: string;
  hostname: string;
  active_jobs: number;
  max_concurrency: number;
  accounts: PoolAccountStatus[];
  next_account: string | null;
  applied_desired_account: string;
  reported_at: Ms;
}

export interface StaffRunnerResponse {
  runners: Array<{ runner_id: string; online: boolean; last_seen_at: Ms; last_claim_at: Ms | null; status: RunnerStatusSnapshot | null }>;
  desired_account: string;
  queue: { queued: number; leased: number };
}

export type ZaloMode = 'mock' | 'real' | 'personal';

export interface OutboxItem {
  id: string;
  kind: 'cs_text' | 'cs_buttons' | 'zbs_template' | 'cs_images';
  zalo_mode: ZaloMode;
  conversation_id: string | null;
  zalo_user_id: string;
  message_id: string | null;
  payload: unknown;
  status: 'pending' | 'queued' | 'leased' | 'sent' | 'failed' | 'unknown';
  zalo_msg_id: string | null;
  error: string | null;
  created_at: Ms;
  sent_at: Ms | null;
  // personal Zalo channel (docs/contracts.md section 12); absent on OA rows
  channel?: 'oa' | 'personal';
  thread_id?: string | null;
  text?: string | null;
  attempts?: number;
  next_attempt_at?: Ms | null;
  lease_until?: Ms | null;
}

export type OutboxDecision = 'requeue' | 'mark_sent' | 'mark_failed';

// ---------------------------------------------------------------- menu images (GET /staff/menu-images)

export interface MenuSlideView {
  key: string; // '<group>/<n>'
  group: string;
  group_label: string;
  n: number;
  title: string;
  kind: string;
  has_medical_claim: boolean; // the bot never sends it; staff confirm before sending
  claim_note: string | null;
  service_ids: string[];
  thumb: boolean;
}
export interface MenuGroupView {
  group: string;
  label: string;
  catalog_group: string | null;
  cover: string[];
  price_list: string[];
  review_note: string | null;
}
export interface MenuImagesIndex {
  max_images: number;
  overview: string[];
  groups: MenuGroupView[];
  slides: MenuSlideView[];
}
export interface SendMenuImagesRequest {
  group: string; // 'overview' or a menu group
  keys?: string[];
  include_claim_slides?: boolean;
}

export interface BridgeStatus {
  zalo_mode: ZaloMode;
  outbound_enabled: boolean;
  last_claim_at: Ms | null;
  last_result_at: Ms | null;
  bridges: Array<{ bridge_id: string; last_seen_at: Ms; last_claim_at: Ms | null; last_item_at: Ms | null; last_result_at: Ms | null }>;
  counts: Record<'queued' | 'leased' | 'sent' | 'failed' | 'unknown', number>;
  oldest_queued_at: Ms | null;
}

export interface VisitRequest {
  customer_id: string;
  service_id: string;
  visited_at: Ms;
  external_visit_id?: string;
  booking_request_id?: string;
  // section 14.5 (servers before 2026-11-12 ignore or reject them, so the console sends them only when staff filled them in)
  amount_vnd?: number; // integer, 0 or more
  technician?: string; // one line, at most 60 characters
  duration_min?: number;
  service_name?: string;
  benefit_id?: string; // an active, unexpired benefit of the same customer with a use left
}
export interface VisitResponse {
  visit_id: string;
  jobs: Array<{ job_id: string; type: 'thank_you' | 'check_in'; run_at: Ms; status: JobStatus }>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

export interface ApiConfig {
  baseUrl: string;
  staffToken: string;
  staffId?: string;
}

export function createApi(cfg: ApiConfig) {
  const base = cfg.baseUrl.replace(/\/+$/, '');

  async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { authorization: `Bearer ${cfg.staffToken}` };
    if (cfg.staffId) headers['x-staff-id'] = cfg.staffId;
    if (body !== undefined) headers['content-type'] = 'application/json';
    const res = await fetch(base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await res.text();
    let json: any = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      if (res.ok) throw new ApiError(res.status, 'bad_response', 'Máy chủ trả về dữ liệu không phải JSON');
    }
    if (!res.ok) {
      const e = json?.error ?? {};
      throw new ApiError(res.status, e.code ?? 'unknown', e.message ?? res.statusText, e.details);
    }
    return json as T;
  }

  const q = (params: Record<string, string | number | boolean | undefined>) => {
    const s = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, String(v));
    const str = s.toString();
    return str ? `?${str}` : '';
  };

  return {
    health: () => req<{ ok: true; env: string; zalo_mode: ZaloMode }>('GET', '/health'),

    listConversations: (p: { state?: BotState; needs_attention?: boolean; limit?: number; cursor?: string } = {}) =>
      req<ListResponse<ConversationSummary>>('GET', `/staff/conversations${q(p)}`),
    getConversation: (id: string) => req<ConversationDetail>('GET', `/staff/conversations/${encodeURIComponent(id)}`),
    takeover: (id: string, until?: Ms) =>
      req<{ conversation: ConversationSummary }>('POST', `/staff/conversations/${encodeURIComponent(id)}/takeover`, until ? { until } : {}),
    release: (id: string) => req<{ conversation: ConversationSummary }>('POST', `/staff/conversations/${encodeURIComponent(id)}/release`, {}),
    markStaffOnly: (id: string) =>
      req<{ conversation: ConversationSummary }>('POST', `/staff/conversations/${encodeURIComponent(id)}/staff-only`, {}),
    setMode: (id: string, mode: ConversationMode | null) =>
      req<{ conversation: ConversationSummary }>('PUT', `/staff/conversations/${encodeURIComponent(id)}/mode`, { mode }),
    /** The per-conversation switch of section 14.4; 'on' also clears the conversation's own mode. */
    setAutoReply: (id: string, value: 'on' | 'off') =>
      req<{ conversation: ConversationSummary }>('PUT', `/staff/conversations/${encodeURIComponent(id)}/auto-reply`, { auto_reply: value }),
    manualSend: (id: string, body: { text: string; from_draft_id?: string; keep_bot_active?: boolean }) =>
      req<{ message: MessageView; outbox_id: string }>('POST', `/staff/conversations/${encodeURIComponent(id)}/send`, body),

    approveDraft: (id: string, body: { text?: string; override_checker?: boolean; attachments?: string[] } = {}) =>
      req<{ draft: DraftView; message: MessageView }>('POST', `/staff/drafts/${encodeURIComponent(id)}/approve`, body),
    rejectDraft: (id: string, reason?: string) =>
      req<{ draft: DraftView }>('POST', `/staff/drafts/${encodeURIComponent(id)}/reject`, reason ? { reason } : {}),

    getFlags: () => req<FlagsResponse>('GET', '/staff/flags'),
    putFlags: (patch: Partial<Flags>) => req<FlagsResponse>('PUT', '/staff/flags', patch),

    listHandoffs: (p: { status?: 'open' | 'resolved'; limit?: number; cursor?: string } = {}) =>
      req<ListResponse<HandoffView>>('GET', `/staff/handoffs${q(p)}`),
    resolveHandoff: (id: string) => req<{ handoff: HandoffView }>('POST', `/staff/handoffs/${encodeURIComponent(id)}/resolve`, {}),

    listBookingRequests: (p: { status?: BookingStatus; limit?: number; cursor?: string } = {}) =>
      req<ListResponse<BookingRequestView>>('GET', `/staff/booking-requests${q(p)}`),
    setBookingStatus: (id: string, body: { status: Exclude<BookingStatus, 'new'>; staff_note?: string }) =>
      req<{ booking_request: BookingRequestView }>('POST', `/staff/booking-requests/${encodeURIComponent(id)}/status`, body),

    createVisit: (body: VisitRequest) => req<VisitResponse>('POST', '/staff/visits', body),
    // the contract does not name the wrapper key: `visits` is expected, `items` (the key of the other lists) is accepted
    listVisits: (customerId: string) =>
      req<{ visits?: VisitView[]; items?: VisitView[] }>('GET', `/staff/visits${q({ customer_id: customerId })}`),

    listBenefits: (customerId: string) => req<{ benefits?: CustomerBenefit[] }>('GET', `/staff/benefits${q({ customer_id: customerId })}`),
    createBenefit: (body: BenefitCreateRequest) => req<{ benefit: CustomerBenefit }>('POST', '/staff/benefits', body),
    patchBenefit: (id: string, body: BenefitPatchRequest) =>
      req<{ benefit: CustomerBenefit }>('PATCH', `/staff/benefits/${encodeURIComponent(id)}`, body),

    /** phone: digits (a leading +84 is read as 0), 9 to 11 of them, or null to clear it. */
    patchCustomer: (id: string, body: { phone: string | null }) =>
      req<unknown>('PATCH', `/staff/customers/${encodeURIComponent(id)}`, body),

    // section 15.11: facts guessed from old chat, keyed like the profiles ('p:' + digits, the colon sent %3A-encoded)
    getChatFacts: (zaloUserId: string) =>
      req<{ facts?: ChatFacts | null }>('GET', `/staff/chat-facts/${encodeURIComponent(zaloUserId)}`),
    /** Records the guess as a visit (source 'staff', no follow-up message); the body carries only staff corrections. */
    confirmChatVisit: (id: string, body: ChatVisitConfirmRequest = {}) =>
      req<{ visit?: VisitView; chat_visit?: ChatVisitView }>('POST', `/staff/chat-facts/visits/${encodeURIComponent(id)}/confirm`, body),
    /** A dismissed guess stays as a tombstone, so the next analyzer run does not bring it back. Works for upcoming bookings too. */
    dismissChatVisit: (id: string) =>
      req<{ chat_visit?: ChatVisitView }>('POST', `/staff/chat-facts/visits/${encodeURIComponent(id)}/dismiss`, {}),
    confirmChatBenefit: (id: string, body: ChatBenefitConfirmRequest) =>
      req<{ benefit?: CustomerBenefit; chat_benefit?: ChatBenefitView }>('POST', `/staff/chat-facts/benefits/${encodeURIComponent(id)}/confirm`, body),
    dismissChatBenefit: (id: string) =>
      req<{ chat_benefit?: ChatBenefitView }>('POST', `/staff/chat-facts/benefits/${encodeURIComponent(id)}/dismiss`, {}),
    /** Copies the suggested number into an empty customers.phone (409 when the customer already has one). */
    acceptChatPhone: (zaloUserId: string) =>
      req<unknown>('POST', `/staff/chat-facts/${encodeURIComponent(zaloUserId)}/phone/accept`, {}),
    /** The dismissed number is never suggested again for this contact. */
    dismissChatPhone: (zaloUserId: string) =>
      req<unknown>('POST', `/staff/chat-facts/${encodeURIComponent(zaloUserId)}/phone/dismiss`, {}),

    listRoles: () => req<{ roles?: ContactRoleRow[] }>('GET', '/staff/roles'),
    /** null removes the row, so the next Zalo label import applies again. */
    setRole: (zaloUserId: string, role: ContactRole | null) =>
      req<{ role: ContactRoleRow | null }>('PUT', `/staff/roles/${encodeURIComponent(zaloUserId)}`, { role }),

    getRunner: () => req<StaffRunnerResponse>('GET', '/staff/runner'),
    setRunnerAccount: (label: string) => req<{ desired_account: string }>('PUT', '/staff/runner/account', { label }),

    // zalo_user_id is 'p:' + threadId; the colon is sent %3A-encoded (the server accepts both forms).
    getProfile: (zaloUserId: string) => req<{ profile: CustomerProfileView }>('GET', `/staff/profiles/${encodeURIComponent(zaloUserId)}`),
    patchProfile: (zaloUserId: string, body: ProfilePatchRequest) =>
      req<{ profile: CustomerProfileView }>('PATCH', `/staff/profiles/${encodeURIComponent(zaloUserId)}`, body),

    menuImages: () => req<MenuImagesIndex>('GET', '/staff/menu-images'),
    /** Thumbnail of one menu slide as a data: URL (the staff route needs the bearer token, so <img src> cannot load it). */
    menuThumb: async (key: string): Promise<string> => {
      const [group, n] = key.split('/');
      const headers: Record<string, string> = { authorization: `Bearer ${cfg.staffToken}` };
      const res = await fetch(`${base}/staff/menu-images/${encodeURIComponent(group ?? '')}/${encodeURIComponent(n ?? '')}`, { headers });
      if (!res.ok) throw new ApiError(res.status, 'not_found', 'Không tải được ảnh menu');
      const bytes = new Uint8Array(await res.arrayBuffer());
      let bin = '';
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      return `data:image/jpeg;base64,${btoa(bin)}`;
    },
    sendMenuImages: (conversationId: string, body: SendMenuImagesRequest) =>
      req<{ message: MessageView; outbox_id: string; keys: string[] }>(
        'POST',
        `/staff/conversations/${encodeURIComponent(conversationId)}/menu-images`,
        body,
      ),

    listOutbox: (p: { limit?: number; cursor?: string } = {}) => req<ListResponse<OutboxItem>>('GET', `/staff/outbox${q(p)}`),
    decideOutbox: (id: string, action: OutboxDecision, note?: string) =>
      req<unknown>('POST', `/staff/outbox/${encodeURIComponent(id)}/decide`, note ? { action, note } : { action }),
    bridgeStatus: () => req<BridgeStatus>('GET', '/bridge/status'),
  };
}

export type Api = ReturnType<typeof createApi>;
