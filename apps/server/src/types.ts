/**
 * Shared types for the thom house chatbot backend.
 * Source of truth for wire shapes: docs/contracts.md. Keep this file and that doc in sync.
 * SHARED FILE: builders may only make ADDITIVE edits (new types / new optional fields). Re-read before editing.
 */

// ---------------------------------------------------------------- env

export interface Env {
  DB: D1Database;
  CONVERSATION: DurableObjectNamespace<import('./conversation-do').ConversationDO>;
  ENV: 'dev' | 'staging' | 'prod';
  // 'personal' (docs/contracts.md "Personal Zalo channel"): sends to personal customers go to the bridge outbox and
  // sends to OA users are refused. Personal customers ('p:' ids) always use the bridge outbox, whatever the mode.
  ZALO_MODE: 'mock' | 'real' | 'personal';
  WEBHOOK_SIGNATURE_MODE: 'observe' | 'enforce';
  DEBOUNCE_MS: string; // default "10000"
  LEASE_MS: string; // default "90000"
  RUNNER_OFFLINE_MS: string; // default "120000"
  TAKEOVER_DEFAULT_MS: string; // default "43200000" (12 h)
  // secrets (.dev.vars locally, `wrangler secret put` in Cloudflare)
  RUNNER_TOKEN: string;
  STAFF_TOKEN: string;
  ZALO_APP_ID: string;
  ZALO_OA_ID: string;
  ZALO_OA_SECRET_KEY: string; // used for the webhook signature
  ZALO_APP_SECRET_KEY: string; // used for OAuth token refresh
  // optional (server-zalo): JSON map of approved ZBS template ids, e.g. {"thank_you":"433555","check_in":"433556"}.
  // ZALO_MODE=real refuses a template send whose key has no id here; mock mode uses 'mock_tpl_<key>'.
  ZALO_TEMPLATE_IDS?: string;
  // optional (server-zalo): local hours [start, end) for proactive (scheduled) sends, default "9-19".
  PROACTIVE_SEND_HOURS?: string;
  // personal channel: shared secret of `zalo-agent listen --webhook` (the engine reads it from ZALO_WEBHOOK_SECRET).
  // POST /zalo/personal/webhook answers 401 to everything while it is unset.
  ZALO_PERSONAL_WEBHOOK_SECRET?: string;
  // personal channel, optional: the personal account's ownId; events with another accountId are ignored, and a
  // message from (or to) this id is the owner's own (self) message.
  ZALO_PERSONAL_ACCOUNT_ID?: string;
  // personal channel, optional: comma-separated threadIds that are not customers (family, friends, other OAs,
  // system accounts). Their events are logged as ignored ('ignored_thread') and never stored or answered.
  ZALO_PERSONAL_IGNORE_THREADS?: string;
  // personal channel, optional bridge pacing (docs/contracts.md "Personal Zalo channel", "Send limits"):
  PERSONAL_QUEUE_MAX_AGE_MS?: string; // default "1800000": an automatic row queued longer is not sent (failed, expired_in_queue)
  PERSONAL_SEND_MAX_PER_HOUR?: string; // default "30": automatic rows claimed per rolling hour (staff rows bypass it)
  PERSONAL_THREAD_MIN_GAP_MS?: string; // default "5000": minimum gap between two claims to the same thread
  // customer status, optional integers (docs/contracts.md section 14.6, src/lib/customer-summary.ts statusConfigFromEnv):
  CUSTOMER_ABSENT_FACTOR_PCT?: string; // default "200": absent after 200 % of the customer's usual gap between visits
  CUSTOMER_MIN_ABSENT_DAYS?: string; // default "14": never "long absent" before this many days
  CUSTOMER_DEFAULT_GAP_DAYS?: string; // default "45": usual gap of a customer with one visit day and no service peers
  CUSTOMER_WINDOW_DAYS?: string; // default "183": the recent window of visits and spend
}

export type Ms = number; // milliseconds since epoch, UTC

// ---------------------------------------------------------------- errors

export type ErrorCode =
  | 'bad_request'
  | 'validation_failed'
  | 'unauthorized'
  | 'signature_invalid'
  | 'forbidden'
  | 'not_found'
  | 'unknown_tool'
  | 'conflict'
  | 'lease_expired'
  | 'lease_not_owned'
  | 'job_not_leased'
  | 'invalid_state'
  | 'checker_failed'
  | 'mode_draft_only'
  | 'outbound_disabled'
  | 'outside_cs_window'
  | 'zalo_send_failed'
  | 'zalo_send_unknown'
  | 'dev_only'
  | 'not_implemented'
  | 'internal';

export interface ErrorBody {
  error: { code: ErrorCode; message: string; details?: Record<string, unknown> };
}

// ---------------------------------------------------------------- enums

export type BotState =
  | 'awaiting_consent'
  | 'bot_active'
  | 'handoff_requested'
  | 'staff_takeover'
  | 'staff_only'
  | 'blocked';

export type ConversationMode = 'off' | 'draft_only' | 'approve_each' | 'auto_allowed';
export const MODE_ORDER: ConversationMode[] = ['off', 'draft_only', 'approve_each', 'auto_allowed'];

export type AiEngine = 'subscription' | 'api_key' | 'off';

export type MessageDirection = 'inbound' | 'outbound';
export type MessageSource = 'customer' | 'bot' | 'staff' | 'server';
export type SendState = 'not_applicable' | 'pending' | 'sent' | 'unknown' | 'failed';

export type JobType = 'draft_reply' | 'thank_you' | 'check_in' | 'promo_send' | 'token_watch' | 'inbox_sweep';
export type JobStatus =
  | 'queued'
  | 'leased'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'skipped'
  | 'needs_staff';

export type DraftStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'sent'
  | 'blocked'
  | 'superseded'
  | 'discarded'
  | 'send_failed';

export type HandoffReasonCode =
  // from design/tools-schema.json handoff_to_staff.reason_code
  | 'customer_requested_human'
  | 'pregnancy'
  | 'postpartum'
  | 'chronic_or_serious_condition'
  | 'medication'
  | 'recent_surgery'
  | 'skin_lesion_or_wound'
  | 'adverse_reaction_after_visit'
  | 'possible_minor'
  | 'medical_suitability_question'
  | 'complaint'
  | 'refund_or_payment'
  | 'reschedule_or_cancel'
  | 'harassment_or_inappropriate'
  | 'data_rights_request'
  | 'unknown_answer'
  | 'price_ambiguity'
  | 'large_group'
  | 'emergency_symptoms'
  | 'other'
  // server-side codes
  | 'ai_unavailable' // runner failed / offline / no account
  | 'checker_blocked' // auto_allowed draft failed the pre-send checker
  | 'customer_declined_ai' // pressed "Gặp nhân viên" or opted out of the AI assistant
  | 'unsupported_message' // image / sticker / file the bot cannot read
  | 'minor_flag';

export type HandoffSource = 'model_tool' | 'server' | 'runner_failure' | 'staff';
export type BookingStatus = 'new' | 'proposed' | 'confirmed' | 'cancelled' | 'expired';

export type RunnerErrorKind =
  | 'login_expired'
  | 'limited'
  | 'blocked'
  | 'no_account'
  | 'timeout'
  | 'session_broken'
  | 'model_error'
  | 'empty_output'
  | 'refusal'
  | 'cancelled'
  | 'internal';

export type ToolName =
  | 'search_services'
  | 'get_service_details'
  | 'quote_price'
  | 'list_active_promotions'
  | 'create_booking_request'
  | 'handoff_to_staff'
  | 'record_contact_preference'
  | 'attach_menu_images' // menu images (task B): attaches menu slide keys to the job's draft
  | 'get_customer_profile'; // section 14.6: read tool, the customer facts of the job's customer (customerFactsForModel)

export const TOOL_NAMES: ToolName[] = [
  'search_services',
  'get_service_details',
  'quote_price',
  'list_active_promotions',
  'create_booking_request',
  'handoff_to_staff',
  'record_contact_preference',
  'attach_menu_images',
  'get_customer_profile',
];
export const WRITE_TOOLS: ToolName[] = ['create_booking_request', 'handoff_to_staff', 'record_contact_preference'];

// ---------------------------------------------------------------- flags

export interface Flags {
  auto_reply_mode: ConversationMode;
  ai_calls_enabled: boolean;
  ai_engine: AiEngine;
  scheduled_sends_enabled: boolean;
  outbound_enabled: boolean;
  promotions_enabled: boolean;
  runner_desired_account: string; // 'auto' or an account label from claude_pool
  // contact profiles: true (default) = a contact whose profile says family / staff / friend (or legacy 'personal') with
  // confidence 'high', or with staff_override = 1 at any confidence, and who has no ai_assistant consent, becomes
  // staff_only on their next message, without a consent prompt (needs_attention = 1).
  profile_personal_skip_bot: boolean;
  // rooms (section 14.7): false (default) = POST /runner/rooms/feed answers { enabled: false, conversations: [] }.
  rooms_enabled: boolean;
}
export type FlagName = keyof Flags;

export interface FlagsResponse {
  flags: Flags;
  updated: Partial<Record<FlagName, { by: string; at: Ms }>>;
}
export type PutFlagsRequest = Partial<Flags>;

// ---------------------------------------------------------------- Zalo webhook

/** Raw Zalo event body (subset we read). All ids are strings. timestamp is a string of ms. */
export interface ZaloWebhookEvent {
  app_id: string;
  event_name: string;
  timestamp: string;
  user_id_by_app?: string;
  sender?: { id: string; admin_id?: string };
  recipient?: { id: string };
  follower?: { id: string };
  source?: string;
  message?: {
    msg_id?: string;
    text?: string;
    quote_msg_id?: string;
    attachments?: Array<{ type: string; payload: Record<string, unknown> }>;
  };
  info?: Record<string, unknown>;
}

export interface WebhookResponse {
  ok: true;
  event_key: string;
  duplicate: boolean;
  signature_ok: boolean;
}

/** What src/zalo hands to the Conversation DO after verify + store. Produced by src/zalo/parse.ts. */
export interface NormalizedEvent {
  event_key: string;
  event_name: string;
  kind:
    | 'customer_message' // user_send_*
    | 'oa_message' // oa_send_* (echo of our own send, or staff via OA Manager when admin_id is set)
    | 'follow'
    | 'unfollow'
    | 'user_submit_info'
    | 'other';
  oa_id: string;
  zalo_user_id: string; // the customer side, for both user_* and oa_* events
  user_id_by_app?: string;
  zalo_msg_id?: string;
  zalo_timestamp: Ms;
  text?: string;
  message_kind: 'text' | 'image' | 'sticker' | 'file' | 'link' | 'audio' | 'video' | 'location' | 'other';
  attachments: Attachment[];
  zalo_admin_id?: string;
  quote_msg_id?: string;
  signature_ok: boolean;
  // personal channel (src/zalo/personal-parse.ts); absent on OA events
  channel?: 'oa' | 'personal';
  display_name?: string; // customer display name (dName) of an incoming personal message
  text_is_placeholder?: boolean; // text is a stand-in such as "[hình ảnh]"; the bot treats the message as non-text
}

export interface Attachment {
  type: string;
  url?: string;
  thumbnail?: string;
  name?: string;
}

/** Name of the Conversation DO instance for one customer of one OA. */
export function conversationObjectName(oaId: string, zaloUserId: string): string {
  return `oa:${oaId}:user:${zaloUserId}`;
}

// ---------------------------------------------------------------- Conversation DO RPC surface

export interface IngestResult {
  conversation_id: string;
  message_id: string | null;
  action:
    | 'stored'
    | 'debounced'
    | 'consent_prompt_sent'
    | 'consent_recorded'
    | 'takeover_detected'
    | 'ignored'
    | 'echo_matched'
    | 'staff_only_profile' // contact profiles: personal contact set to staff_only quietly (flag profile_personal_skip_bot)
    | 'internal_contact'; // section 14.3: message of a manager / staff contact, stored and nothing else
}

export interface DraftAcceptResult {
  draft_id: string | null;
  status: DraftStatus | 'late';
  checker: CheckerResult | null;
  action: 'queued_for_staff' | 'auto_sent' | 'dropped' | 'rejected_late';
  message_id?: string | null;
  attachments?: string[]; // menu images (task B): menu image keys attached with attach_menu_images in this job
}

// ---------------------------------------------------------------- runner API

export interface RunnerClaimRequest {
  max_jobs?: 1; // only 1 is supported
}

export interface CustomerMessageForRunner {
  message_id: string;
  text: string; // '' for non-text messages; see attachments
  kind: string;
  attachments: Attachment[];
  sent_at: Ms;
}

export interface SentMessageForRunner {
  message_id: string;
  source: 'bot' | 'staff' | 'server';
  text: string;
  sent_at: Ms;
  from_draft_id: string | null;
  edited_by_staff: boolean; // true when final_text != model text
}

export interface UnsentDraftForRunner {
  draft_id: string;
  status: 'rejected' | 'blocked' | 'superseded' | 'discarded' | 'send_failed';
  text: string;
}

export interface HistoryMessageForRunner {
  source: MessageSource;
  text: string;
  at: Ms;
}

export interface TurnContext {
  now_local: string; // e.g. "2026-11-07T19:42 Asia/Ho_Chi_Minh (thứ Bảy)"
  conversation_mode: ConversationMode;
  customer_display_name: string;
  customer_gender_hint: string;
  minor_flag: 'true' | 'false' | 'unknown';
  consent: { ai_assistant: string; followup_care: string; promotions: string };
  open_booking_requests: Array<{ request_id: string; summary: string; status: BookingStatus }>;
  last_followup_sent: string;
  notes: string[];
}

export type SessionResetReason =
  | 'new_conversation'
  | 'turn_limit'
  | 'idle'
  | 'catalog_changed'
  | 'released_by_staff'
  | 'session_broken'
  | 'runner_requested';

export interface ClaimedJob {
  job_id: string;
  type: 'draft_reply';
  lease_until: Ms;
  attempt: number;
  conversation: {
    conversation_id: string; // internal cnv_ id; never the Zalo id
    session_id: string | null; // null => runner must start a new Claude Code session
    session_turns: number;
    session_started_at: Ms | null;
    session_reset_reason: SessionResetReason | null;
    catalog_version: string; // active catalog version this job must use (matches GET /runner/prompt)
  };
  turn_context: TurnContext;
  turn_context_text: string; // server-rendered <turn_context>...</turn_context> block (block D)
  new_customer_messages: CustomerMessageForRunner[];
  sent_since_last_draft: SentMessageForRunner[];
  unsent_drafts_since_last: UnsentDraftForRunner[];
  history: HistoryMessageForRunner[]; // non-empty only when session_id is null (seed for the new session)
  prompt_hash: string; // must equal GET /runner/prompt prompt_hash; refetch when different
  // contact profiles (additive 2026-11-08): derived facts only, null when there is no usable profile. Never evidence,
  // stats or history; present only for a profile with relationship 'customer' or 'unknown'.
  customer_profile?: CustomerProfileForModel | null;
}

export interface RunnerClaimResponse {
  job: ClaimedJob | null;
  poll_after_ms: number;
  reason?: 'no_work' | 'ai_calls_disabled' | 'ai_engine_not_subscription';
}

export interface RunnerHeartbeatResponse {
  lease_until: Ms;
  stale: boolean; // newer customer messages arrived; finish anyway, the draft will be superseded
  cancel: boolean; // stop now: takeover / handoff / flags changed / lease lost
  cancel_reason?: 'takeover' | 'handoff' | 'flags_changed' | 'lease_lost' | 'job_cancelled';
}

export interface RunnerUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
}

export interface RunnerDraftRequest {
  text: string;
  session_id: string;
  account_label: string | null;
  model: string;
  effort: string;
  usage: RunnerUsage;
  cost_usd_equiv: number; // this turn only (delta of total_cost_usd within the session)
  duration_ms: number;
  num_turns: number;
  error_kind: null | 'session_restarted'; // runner discarded the given session and started a new one
}
export type RunnerDraftResponse = DraftAcceptResult;

export interface RunnerFailRequest {
  error_kind: RunnerErrorKind;
  error_message: string; // truncated to 500 chars, no secrets
  account_label: string | null;
  session_id: string | null;
  session_broken: boolean;
  usage?: RunnerUsage;
  cost_usd_equiv?: number;
}
export interface RunnerFailResponse {
  job_status: JobStatus;
  handoff_id: string | null;
}

export interface RunnerToolRequest {
  job_id: string;
  input: Record<string, unknown>;
}
export interface RunnerToolResponse {
  result: unknown; // tool result JSON passed to the model unchanged
  is_error: boolean;
  tool_call_id: string;
  replayed: boolean; // true when a write tool call was deduplicated
}

export interface ToolDefinition {
  name: ToolName;
  description: string;
  input_schema: Record<string, unknown>;
  strict?: boolean;
}

export interface RunnerPromptResponse {
  catalog_version: string;
  prompt_hash: string; // sha256 hex of cli_system_prompt + JSON(tools)
  blocks: { a: string; b: string; c: string; t?: string }; // t = <reply_templates> from data/reply-templates.json (2026-11-08)
  cli_system_prompt: string; // a + "\n\n" + t + "\n\n" + b + "\n\n" + c + cli_tool_note; pass to --system-prompt
  tools: ToolDefinition[]; // 7 tools, fixed order, without x_ fields
}

export interface PoolAccountStatus {
  label: string;
  priority: number | null;
  enabled: boolean;
  pinned: boolean;
  pool_status: 'ok' | 'limited' | 'login_expired' | 'blocked' | 'error';
  until: string | null; // ISO time from account-state.json
  usable_now: boolean;
  login: { loggedIn?: boolean; email?: string | null; subscriptionType?: string | null } | null;
  last_error: string;
  last_ok: string | null;
}

export interface RunnerStatusRequest {
  runner_version: string;
  hostname: string;
  active_jobs: number;
  max_concurrency: number;
  accounts: PoolAccountStatus[];
  next_account: string | null;
  applied_desired_account: string; // what the runner applied last ('auto' or a label)
  reported_at: Ms;
}
export interface RunnerStatusResponse {
  ok: true;
  desired_account: string; // 'auto' or label; runner applies it with claude_pool use
  flags: Pick<Flags, 'ai_calls_enabled' | 'ai_engine' | 'auto_reply_mode'>;
}

// ---------------------------------------------------------------- checker

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
export interface CheckerInput {
  text: string;
  conversation_id: string;
  catalog_version: string;
  allowed_price_texts: string[]; // every price_text seen in tool results of this conversation
  approved_contact_values: string[]; // phones / urls / emails from approved facts
  display_names: string[]; // display_name_vi of the active catalog (exempt from forbidden terms)
  attachment_keys?: string[]; // menu images (task B): menu image keys the draft would send after its text
}

// ---------------------------------------------------------------- staff API

export interface CustomerView {
  id: string;
  channel?: 'oa' | 'personal';
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
  // contact roles (section 14.3, additive): emitted only when the contact has a role
  role?: ContactRole | null;
  role_source?: RoleSource | null;
  // auto reply switch (section 14.4, additive): emitted only when conversations.auto_reply is set
  auto_reply?: 'on' | 'off';
}

export interface MessageView {
  id: string;
  direction: MessageDirection;
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
  attachments?: string[]; // menu images (task B): drafts.attachments_json, sent as one image row after the text
}

export interface HandoffView {
  id: string;
  conversation_id: string;
  customer_display_name: string | null;
  source: HandoffSource;
  reason_code: HandoffReasonCode;
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
  conversation: ConversationSummary & {
    session_id: string | null;
    session_turns: number;
    catalog_version: string | null;
  };
  messages: MessageView[]; // oldest first, last 200
  drafts: DraftView[]; // pending + blocked + last 20 decided
  handoffs: HandoffView[];
  booking_requests: BookingRequestView[];
  consents: ConsentView[];
  profile?: CustomerProfileView | null; // contact profiles (additive 2026-11-08); null when the customer has none
  customer_summary?: CustomerSummary | null; // section 14.6 (additive): src/lib/customer-summary.ts buildCustomerSummary
  // rooms (section 14.7, additive): emitted only when conversations.room_channel_id is set
  room?: { channel_id: string; synced_at: Ms | null; pending: number };
}

export interface ListResponse<T> {
  items: T[];
  next_cursor: string | null;
}

export interface TakeoverRequest {
  until?: Ms; // default now + TAKEOVER_DEFAULT_MS
}
export interface SetModeRequest {
  mode: ConversationMode | null; // null = inherit flag auto_reply_mode
}
/** PUT /staff/conversations/:id/auto-reply (section 14.4). 'on' also clears the per-conversation mode. */
export interface SetAutoReplyRequest {
  auto_reply: 'on' | 'off';
}
export interface ApproveDraftRequest {
  text?: string; // edited text; omitted = send the model text
  override_checker?: boolean; // send even if the checker fails (audited)
  attachments?: string[]; // menu images to keep (a subset of DraftView.attachments); omitted = all, [] = none (2026-11-08)
}
export interface RejectDraftRequest {
  reason?: string;
}
export interface ManualSendRequest {
  text: string;
  from_draft_id?: string;
  keep_bot_active?: boolean; // default false: a manual send puts the conversation in staff_takeover
}

// ---- staff menu images (task C, 2026-11-08; src/staff-api/menu.ts)
export interface StaffMenuSlide {
  key: string; // '<group>/<n>' of data/menu-images.json
  group: string;
  group_label: string;
  n: number;
  title: string;
  kind: string;
  has_medical_claim: boolean; // staff only: the bot never sends it; staff confirm before sending
  claim_note: string | null;
  service_ids: string[];
  thumb: boolean; // GET /staff/menu-images/:group/:n serves a thumbnail for this key
}
export interface StaffMenuGroup {
  group: string; // menu image group: facial | healing | thu-gian-toc | hair-removal
  label: string;
  catalog_group: string | null;
  cover: string[]; // keys
  price_list: string[]; // keys: what "Gửi menu" of this group sends
  review_note: string | null;
}
export interface StaffMenuImagesResponse {
  max_images: number;
  overview: string[]; // keys of the covers ("Gửi menu" > overview)
  groups: StaffMenuGroup[];
  slides: StaffMenuSlide[];
}
/** POST /staff/conversations/:id/menu-images. keys: a subset of the choice's slides (default: its non-claim slides). */
export interface SendMenuImagesRequest {
  group: string; // 'overview' or a menu image group
  keys?: string[];
  include_claim_slides?: boolean; // must be true when keys contain a slide with has_medical_claim (the console confirms first)
}
export interface SendMenuImagesResponse {
  message: MessageView; // kind 'image', source 'staff', text = staff-facing label (never sent)
  outbox_id: string; // cs_images row
  keys: string[];
}
export interface SendResult {
  message: MessageView;
  outbox_id: string;
}
export interface ApproveDraftResponse {
  draft: DraftView;
  message: MessageView;
}

export interface VisitRequest {
  customer_id: string;
  service_id: string;
  visited_at: Ms;
  external_visit_id?: string;
  booking_request_id?: string;
  // section 14.5 (additive, need migration 0010 when given):
  amount_vnd?: number | null; // integer VND, 0 or more; absent or null = unknown
  technician?: string | null; // one line, at most 60 characters
  duration_min?: number | null; // integer minutes, more than 0
  service_name?: string | null; // one line, at most 120 characters
  benefit_id?: string | null; // an active, unexpired benefit of the same customer with a use left; uses one count
}
export interface VisitResponse {
  visit_id: string;
  jobs: Array<{ job_id: string; type: 'thank_you' | 'check_in'; run_at: Ms; status: JobStatus }>;
}

export interface BookingStatusRequest {
  status: Exclude<BookingStatus, 'new'>;
  staff_note?: string;
}

export interface StaffRunnerResponse {
  runners: Array<{
    runner_id: string;
    online: boolean;
    last_seen_at: Ms;
    last_claim_at: Ms | null;
    status: RunnerStatusRequest | null;
    last_error?: { kind: RunnerErrorKind; at: Ms; account_label: string | null } | null; // server-core phase 2
  }>;
  desired_account: string;
  queue: { queued: number; leased: number };
}

export interface OutboxItem {
  id: string;
  kind: 'cs_text' | 'cs_buttons' | 'zbs_template' | 'cs_images';
  zalo_mode: 'mock' | 'real' | 'personal';
  conversation_id: string | null;
  zalo_user_id: string;
  message_id: string | null;
  payload: unknown;
  status: OutboxStatus;
  zalo_msg_id: string | null;
  error: string | null;
  created_at: Ms;
  sent_at: Ms | null;
  // personal channel (absent / null on OA rows)
  channel?: 'oa' | 'personal';
  thread_id?: string | null;
  text?: string | null;
  attempts?: number;
  next_attempt_at?: Ms | null;
  lease_until?: Ms | null;
}

export type OutboxStatus = 'pending' | 'queued' | 'leased' | 'sent' | 'failed' | 'unknown';

// ---------------------------------------------------------------- dev

export interface DevSeedRequest {
  services_json: unknown; // contents of data/services.json
  business_facts_json: unknown; // contents of data/business-facts.json
  block_a: string; // text of the ```text fence under "## Khối A" in design/system-prompt-draft.md
  tools_schema_json: unknown; // contents of design/tools-schema.json
  cli_tool_note?: string; // appended to the CLI system prompt; default in src/lib/prompt.ts
  catalog_version?: string; // default 'cv_seed_' + yyyymmdd
  activate?: boolean; // default true
}
export interface DevSeedResponse {
  catalog_version: string;
  services: number;
  variants: number;
  facts: number;
  prompt_hash: string;
}

// ---------------------------------------------------------------- Zalo client (src/lib/zalo-client.ts)

export type ZaloSendOutcome =
  | { ok: true; zalo_msg_id: string; outbox_id: string; queued?: false }
  // personal channel: stored as an outbox row with status 'queued'; the bridge reports the real outcome later
  | { ok: true; queued: true; zalo_msg_id: null; outbox_id: string }
  | { ok: false; unknown: boolean; error_code: string; error_message: string; outbox_id: string };

export interface ZaloButton {
  title: string; // <= 100 chars
  type: 'oa.query.show' | 'oa.query.hide' | 'oa.open.url' | 'oa.open.phone';
  payload: string | Record<string, unknown>;
}

// ---------------------------------------------------------------- Hono app typing

export interface AppVariables {
  requestId: string;
  runnerId?: string; // set by requireRunner from X-Runner-Id
  staffId?: string; // set by requireStaff from X-Staff-Id (default 'staff')
  bridgeId?: string; // set by requireBridge from X-Bridge-Id
}
export interface AppEnv {
  Bindings: Env;
  Variables: AppVariables;
}

// ---------------------------------------------------------------- personal Zalo channel (docs/contracts.md "Personal Zalo channel")

/** One event as `zalo-agent listen --webhook` posts it (src/commands/listen.js messageEvent()). Fields we read. */
export interface PersonalWebhookEvent {
  event: string; // 'message' | 'friend' | 'group' | 'reaction' | 'read' | 'undo' | 'deleted_for_me' | ...
  accountId?: string;
  msgId?: string;
  cliMsgId?: string;
  threadId?: string;
  type?: number; // 0 = user (DM), 1 = group
  isSelf?: boolean;
  uidFrom?: string | null;
  dName?: string | null;
  msgType?: string | null;
  content?: unknown; // string for text, object for attachments
  catchUp?: boolean; // recovered after a dropped socket
}

/** Webhook body: one event, or a batch when the engine's batch size is above 1. */
export interface PersonalWebhookBatch {
  event: 'batch';
  accountId?: string;
  count?: number;
  events: PersonalWebhookEvent[];
}

export interface PersonalWebhookResult {
  index: number;
  event_key: string | null;
  status: 'accepted' | 'duplicate' | 'ignored';
  reason?: 'not_message' | 'group_thread' | 'no_thread' | 'foreign_account' | 'malformed' | 'own_thread' | 'ignored_thread';
}

export interface PersonalWebhookResponse {
  ok: true;
  count: number;
  results: PersonalWebhookResult[];
}

/**
 * POST /bridge/outbox/claim response item. `text` is always plain text; send it as is. A 'cs_images' item (handed
 * out only to a bridge that claims with capabilities ['images']) sends `images` with `msg send-image` instead, and
 * its `text` is a staff-facing label that is never sent.
 */
export interface BridgeOutboxItem {
  id: string; // obx_...
  thread_id: string;
  thread_type: 0; // always a user (DM) thread
  text: string;
  kind: 'cs_text' | 'cs_buttons' | 'zbs_template' | 'cs_images'; // cs_images: send `images`, not `text`
  images?: string[]; // cs_images only: 1..10 menu image keys ('<group>/<n>'), resolved by the bridge's manifest
  attempt: number; // 1 on the first claim
  lease_until: Ms;
  conversation_id: string | null;
  message_id: string | null;
  // set when staff requeued this row (POST /staff/outbox/:id/decide requeue): the bridge sends it again even if
  // its journal already holds an outcome for this id from before that time
  requeued_at: Ms | null;
}

export interface BridgeClaimResponse {
  item: BridgeOutboxItem | null;
  poll_after_ms: number;
  reason?: 'no_work' | 'outbound_disabled' | 'rate_limited';
}

export interface BridgeResultRequest {
  status: 'sent' | 'failed' | 'unknown';
  zalo_msg_id?: string; // msgId printed by `zalo-agent --json msg send` (message.msgId)
  error?: string; // short, no message text, no secrets
  attempt?: number; // the claim's attempt number; lets the server spot a result from an older claim
  part_msg_ids?: string[]; // split send: msgId of every part (parts[].msgId), so each part's echo is matched by id
}

export interface BridgeResultResponse {
  id: string;
  status: OutboxStatus; // row status after this result
  attempts: number;
  next_attempt_at: Ms | null; // set when a 'failed' result was re-queued for a retry
  ignored: boolean; // true when the row already had a final outcome that this result does not change
}

export interface BridgeStatusResponse {
  zalo_mode: Env['ZALO_MODE'];
  outbound_enabled: boolean;
  last_claim_at: Ms | null;
  last_result_at: Ms | null;
  bridges: Array<{ bridge_id: string; last_seen_at: Ms; last_claim_at: Ms | null; last_item_at: Ms | null; last_result_at: Ms | null }>;
  counts: Record<'queued' | 'leased' | 'sent' | 'failed' | 'unknown', number>;
  oldest_queued_at: Ms | null;
  claims_last_hour?: number; // personal rows claimed in the last hour (send limit, docs/contracts.md "Send limits")
  send_max_per_hour?: number; // PERSONAL_SEND_MAX_PER_HOUR (0 = no limit)
}

export interface OutboxDecisionRequest {
  action: 'requeue' | 'mark_sent' | 'mark_failed';
  note?: string;
}

// ---------------------------------------------------------------- contact profiles (docs/contracts.md section 13)

// 'personal': legacy value of analyzer v2 (migration 0007); analyzer v3 writes family / staff / friend instead.
export type ProfileRelationship = 'customer' | 'staff' | 'family' | 'friend' | 'personal' | 'unknown';

/**
 * The latest service the contact likely used (migration 0008). The analyzer sends source 'chat' (a past-use signal,
 * never certain); the server merges it with the newest staff-recorded visit (source 'visit', confidence 'high'), and a
 * visit newer than the chat signal wins.
 */
export interface ProfileLastService {
  key: string | null; // service_id or 'cat:<category>'; null for a visit of a service no longer in the catalog
  service_id: string | null;
  name: string; // catalog name or category label (staff view)
  at: Ms;
  source: 'chat' | 'visit';
  confidence: ProfileConfidence;
  sensitive: boolean; // health / women group: never shown to the model
}
export type ProfileConfidence = 'low' | 'medium' | 'high';
export type ProfileAddressTerm = 'chị' | 'anh' | 'cô' | 'chú' | 'bác' | 'anh/chị';

/** One service (catalog id) or service category ('cat:...') the contact mentioned. */
export interface ProfileService {
  key: string; // service_id, or 'cat:<category>' for a category keyword (e.g. 'cat:massage')
  service_id: string | null; // catalog id from data/services.json; null for a category
  name: string; // catalog name or category label (staff view; the model gets names from the active catalog)
  group: string | null; // catalog group: relaxation | health | women | skin | hair | other
  sensitive: boolean; // health / women group: never shown to the model
  status: 'mentioned' | 'likely_used'; // likely_used = a past-use signal; never certain
  mention_count: number;
  last_mentioned_at: Ms | null;
  used_signal_count: number;
  last_used_signal_at: Ms | null;
}

/** A short local snippet behind a service / booking / price match. Staff console only; never sent to the model. */
export interface ProfileEvidence {
  at: Ms;
  from: 'contact' | 'owner';
  kind: 'service' | 'booking' | 'price';
  text: string; // <= 80 chars, phone numbers and long digit runs masked
}

export interface ProfileAddressing {
  owner_calls_contact: Record<string, number>;
  contact_calls_self: Record<string, number>;
  contact_calls_owner: Record<string, number>;
  owner_calls_self?: Record<string, number>;
  name_prefix?: string | null;
  basis?: Record<string, unknown>;
}

/** One profile in POST /staff/profiles/import (scripts/analyze_contacts.py output). */
export interface CustomerProfileImport {
  zalo_user_id: string; // 'p:' + threadId
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
  stats: Record<string, unknown>;
  last_service?: ProfileLastService | null; // analyzer v3: source 'chat' only; absent or null from analyzer v2
}

export interface ProfileImportRequest {
  analyzer_version?: string;
  generated_at?: Ms;
  profiles: CustomerProfileImport[];
}

export interface ProfileImportResponse {
  imported: number;
  created: number;
  updated: number;
  kept_staff_fields: number; // existing rows with staff_override = 1 whose staff-edited fields were kept
}

/** Field groups staff can own: relationship (+ confidence), address (address_term + address_confidence), name, services. */
export type ProfileStaffField = 'relationship' | 'address' | 'name' | 'services';

/** PATCH /staff/profiles/:zalo_user_id. An edited field marks its group as staff-owned (staff_override = 1). */
export interface ProfilePatchRequest {
  relationship?: ProfileRelationship;
  relationship_confidence?: ProfileConfidence; // default 'high' when relationship is given
  address_term?: ProfileAddressTerm | null;
  name_to_use?: string | null;
  address_confidence?: ProfileConfidence; // default 'high' when address_term is given
  services?: ProfileService[];
  staff_note?: string | null; // does not set staff_override by itself
  staff_override?: boolean; // true alone: mark all four groups; false (alone or with staff_note only): clear them and restore the analyzer values
}

/** The staff-editable fields as the analyzer last wrote them (restored when the override is cleared). */
export interface ProfileAnalyzerValues {
  relationship: ProfileRelationship;
  relationship_confidence: ProfileConfidence;
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  address_confidence: ProfileConfidence;
  services: ProfileService[];
}

export interface CustomerProfileView {
  zalo_user_id: string;
  thread_id: string | null;
  customer_id: string | null; // customers row, when the contact has written since the bot runs
  conversation_id: string | null;
  display_name: string | null;
  relationship: ProfileRelationship;
  relationship_confidence: ProfileConfidence;
  relationship_reasons: string[];
  address_term: ProfileAddressTerm | null;
  name_to_use: string | null;
  address_confidence: ProfileConfidence;
  addressing: ProfileAddressing | Record<string, never>;
  services: ProfileService[];
  evidence: ProfileEvidence[];
  stats: Record<string, unknown>;
  analyzer: ProfileAnalyzerValues | null;
  analyzer_version: string | null;
  source: 'analyzer' | 'staff';
  staff_override: boolean; // true when staff_fields is not empty
  staff_fields: ProfileStaffField[]; // groups an import keeps as staff left them
  staff_note: string | null;
  analyzed_at: Ms | null;
  created_at: Ms;
  updated_at: Ms;
  updated_by: string;
  last_service: ProfileLastService | null; // chat signal merged with the newest recorded visit (newer wins)
  model_facts: CustomerProfileForModel | null; // exactly what a draft job for this customer would carry now
  // contact roles (section 14.3, additive): emitted only when the contact has a role
  role?: ContactRole | null;
  role_source?: RoleSource | null;
}

/** What reaches the model (ClaimedJob.customer_profile). Built by src/lib/profiles.ts profileFactsForModel. */
export interface CustomerProfileForModel {
  relationship: 'customer' | 'unknown';
  address_term: ProfileAddressTerm | null; // null: keep the default "anh/chị"
  name_to_use: string | null; // only with a specific address_term (not "anh/chị")
  services_likely_used: string[]; // catalog display names / category labels, at most 5
  services_mentioned: string[]; // asked about, not necessarily used, at most 5
  // name + local date only; non-sensitive; a recorded visit, or a chat signal with confidence medium/high (additive)
  last_service?: { name: string; date: string } | null; // date 'YYYY-MM-DD' (Asia/Ho_Chi_Minh)
}

// ---------------------------------------------------------------- contact roles (docs/contracts.md section 14.3)

/** Role of a personal Zalo contact (table contact_roles, migration 0010). 'manager' and 'staff' are internal contacts. */
export type ContactRole = 'customer' | 'manager' | 'staff';
/** Who wrote a contact_roles row: the Zalo label import, or a staff member in the console. */
export type ContactRoleSource = 'zalo_label' | 'staff';
/** Where a role shown to staff comes from. 'profile': no contact_roles row, derived from the section 13 relationship. */
export type RoleSource = ContactRoleSource | 'profile';

export interface ContactRoleRow {
  zalo_user_id: string; // 'p:' + threadId
  role: ContactRole;
  source: ContactRoleSource;
  updated_at: Ms;
  updated_by: string;
}

/** POST /staff/roles/import. */
export interface RolesImportRequest {
  source: 'zalo_label';
  complete?: boolean; // true: the zalo_label rows that are not in `roles` are deleted
  roles: Array<{ zalo_user_id: string; role: ContactRole }>; // at most 5 000
}

export interface RolesImportResponse {
  imported: number; // new rows
  updated: number; // zalo_label rows whose role changed
  unchanged: number;
  removed: number; // complete: zalo_label rows deleted because the list does not name them
  kept_staff: number; // list entries skipped because a staff row exists
}

/** PUT /staff/roles/:zalo_user_id. null deletes the row, so the next label import applies again. */
export interface RolePutRequest {
  role: ContactRole | null;
}

// ---------------------------------------------------------------- visits, benefits, phone (section 14.5)

export type VisitSource = 'staff' | 'booking_app' | 'booking_request' | 'import';

/** One row of GET /staff/visits?customer_id= (answer `{ visits: VisitView[] }`, newest first, at most 200). */
export interface VisitView {
  id: string;
  customer_id: string;
  service_id: string; // catalog id, or 'ext:<slug>' for a service outside the catalog
  service_name: string | null; // as stored
  name: string; // catalog display_name_vi, else the stored service_name, else the service_id
  visited_at: Ms;
  duration_min: number | null;
  amount_vnd: number | null; // null = unknown
  technician: string | null;
  benefit_id: string | null;
  source: VisitSource;
  external_visit_id: string | null;
  recorded_by: string | null;
  created_at: Ms;
}

/** One row of POST /staff/visits/import: one of customer_id / zalo_user_id / phone, one of visited_at / visited_at_local. */
export interface VisitImportRow {
  customer_id?: string;
  zalo_user_id?: string; // 'p:<digits>'
  phone?: string;
  service_id?: string; // kept when it is in the active catalog
  service_name?: string; // needed otherwise: stored with service_id 'ext:' + slug(service_name)
  visited_at?: Ms;
  visited_at_local?: string; // 'YYYY-MM-DD HH:MM' in Asia/Ho_Chi_Minh
  amount_vnd?: number | null;
  technician?: string | null;
  duration_min?: number | null;
  external_visit_id?: string;
}

export interface VisitsImportRequest {
  dry_run?: boolean; // true: counts only, nothing is written
  visits: VisitImportRow[]; // at most 2 000
}

export type VisitImportUnmatchedReason = 'no_customer' | 'bad_time' | 'bad_service' | 'bad_amount';

export interface VisitsImportResponse {
  imported: number;
  duplicates: number;
  created_customers: number;
  unmatched: Array<{ index: number; reason: VisitImportUnmatchedReason }>;
}

export type BenefitKind = 'package' | 'voucher';
export type BenefitStatus = 'active' | 'void';

/** A prepaid package or a voucher of a customer (table customer_benefits, migration 0010). */
export interface CustomerBenefit {
  id: string; // 'ben_…'
  customer_id: string;
  kind: BenefitKind;
  title: string;
  service_id: string | null;
  total_count: number;
  used_count: number;
  remaining: number; // total_count - used_count
  expires_at: Ms | null;
  expires_on: string | null; // local date of expires_at; the benefit can be used through that date
  status: BenefitStatus;
  recorded_by: string;
  created_at: Ms;
  updated_at: Ms;
}

/** POST /staff/benefits. */
export interface BenefitCreateRequest {
  customer_id: string;
  kind: BenefitKind;
  title: string; // one line, at most 120 characters
  service_id?: string | null; // a service of the active catalog
  total_count: number; // 1 or more
  used_count?: number; // default 0, at most total_count
  expires_at?: Ms | null;
}

/** PATCH /staff/benefits/:id. */
export interface BenefitPatchRequest {
  title?: string;
  used_count?: number;
  expires_at?: Ms | null;
  status?: BenefitStatus;
}

/** PATCH /staff/customers/:id (answer `{ customer: CustomerView }`). */
export interface CustomerPhonePatchRequest {
  phone: string | null; // stored as digits: '+84' becomes '0', 9 to 11 digits
}

// ---------------------------------------------------------------- customer status and summary (section 14.6)

type CustomerStatusName = import('./lib/customer-status').CustomerStatus;
type CustomerGapBasis = 'own' | 'service_peers' | 'default';

/** Staff view of a customer (ConversationDetail.customer_summary). Built by src/lib/customer-summary.ts buildCustomerSummary. */
export interface CustomerSummary {
  role: ContactRole | null;
  role_source: RoleSource | null;
  name: string | null;
  address_term: string | null;
  phone: string | null;
  status: CustomerStatusName;
  visits_total: number; // visit days
  last_visit: {
    visited_at: Ms;
    date: string; // 'YYYY-MM-DD' (Asia/Ho_Chi_Minh)
    time: string | null; // 'HH:MM'; null only for a day guessed from chat whose time is unknown (section 15.12)
    services: Array<{ service_id: string; name: string }>;
    technician: string | null;
    amount_vnd: number | null; // sum of the known amounts of that day; null = unknown
    // section 15.12 (additive): emitted only when the contact has chat facts; true when the day is a guess from chat
    from_chat?: boolean;
  } | null;
  days_since_last_visit: number | null;
  usual_gap_days: number | null;
  gap_basis: CustomerGapBasis | null;
  absent_after_days: number | null;
  lifetime_spend_vnd: number;
  lifetime_spend_visits: number;
  window: {
    days: number;
    from_date: string;
    visits: number;
    spend_vnd: number;
    avg_spend_vnd: number | null;
    services: Array<{ service_id: string; name: string; count: number }>;
  };
  benefits: Array<{ id: string; kind: BenefitKind; title: string; remaining: number; expires_on: string | null }>;
  // section 15.12 (additive): emitted only when the contact has chat facts (migration 0011). visits_total, window and
  // the spend figures then include the counted chat visits (spend only from amounts with amount_source 'paid').
  chat?: CustomerSummaryChat | null;
}

/** What the staff summary says about the guesses from old chats (section 15.12). */
export interface CustomerSummaryChat {
  visits_counted: number; // active chat visits of confidence high / medium on a date without a recorded visit
  visits_low: number; // active chat visits of confidence low on a date without a recorded visit (never counted)
  upcoming_next: { date: string; time: string | null } | null; // the soonest active upcoming booking, today or later
  benefits_active: number; // active chat benefits
  phone_suggestion: boolean; // a phone number waits for staff (the number itself is in GET /staff/chat-facts/:id)
  analyzer_version: string | null;
  generated_at: Ms | null;
}

/** Model view of the same data: the result of the read tool get_customer_profile (customerFactsForModel). */
export type CustomerFacts =
  | { found: false; reason: 'internal_contact' | 'no_data' }
  | {
      found: true;
      role: ContactRole | null;
      address_term: ProfileAddressTerm | null; // section 13 rule 2
      name_to_use: string | null; // section 13 rule 3
      has_phone: boolean; // the number itself never reaches the model
      status: CustomerStatusName;
      visits_total: number;
      last_visit: {
        date: string;
        time: string | null; // null only for a day guessed from chat whose time is unknown (section 15.12)
        services: string[]; // names section 13 rule 4 allows
        other_services: number; // services of that day that are not named
        technician: string | null; // a chat technician only without a run of 3 or more digits
        from_chat?: boolean; // section 15.12 (additive): emitted only when the contact has chat facts
      } | null;
      days_since_last_visit: number | null;
      usual_gap_days: number | null;
      gap_basis: CustomerGapBasis | null;
      absent_after_days: number | null;
      window: {
        days: number;
        visits: number;
        spend_vnd: number;
        avg_spend_vnd: number | null;
        usual_services: Array<{ name: string; count: number }>; // at most 5
        other_services: number; // services of the window that are not named
      };
      lifetime: { spend_vnd: number; spend_visits: number };
      unused_benefits: Array<{ kind: BenefitKind; title: string; remaining: number; expires_on: string | null }>;
      services_mentioned: string[]; // section 13 rule 4, at most 5
      // section 15.12 (additive): the four fields below are emitted only when the contact has chat facts
      visits_from_chat?: number; // how many of visits_total are guesses from old chats
      next_booking_from_chat?: { date: string; time: string | null } | null; // an active upcoming booking, today or later
      benefits_from_chat?: Array<{ kind: BenefitKind; remaining: number }>; // active, remaining known; never the title
    };

// ---------------------------------------------------------------- rooms feed (docs/contracts.md section 14.7)

/** POST /runner/rooms/feed. Without conversation_id: the observation list. With it: the rows of one draft turn. */
export interface RoomsFeedRequest {
  conversation_id?: string;
  seed?: boolean; // with conversation_id: the last 20 rows that meet the row rule, ignoring room_mirrored_at
  limit?: number; // observation list: conversations to return (default 5, at most 20)
}
export interface RoomsFeedMessage {
  message_id: string;
  seq: number;
  source: 'customer' | 'bot' | 'staff' | 'server';
  direction: MessageDirection;
  kind: string;
  text: string;
  at: Ms;
}
export interface RoomsFeedConversation {
  conversation_id: string;
  customer_display_name: string | null;
  messages: RoomsFeedMessage[]; // oldest first
}
export interface RoomsFeedResponse {
  enabled: boolean; // false: flag rooms_enabled is false or migration 0010 is not applied
  conversations: RoomsFeedConversation[];
}
/** POST /runner/rooms/ack: the runner mirrored these rows into the room. */
export interface RoomsAckRequest {
  conversation_id: string;
  message_ids: string[]; // at most 200
  room?: { channel_id: string };
}
export interface RoomsAckResponse {
  ok: true;
  marked: number;
}

// ---------------------------------------------------------------- chat-derived customer facts (docs/contracts.md section 15)

export type ChatVisitKind = 'visit' | 'upcoming';
export type ChatFactState = 'active' | 'confirmed' | 'dismissed';
export type ChatConfidence = 'high' | 'medium' | 'low';
export type ChatAmountSource = 'paid' | 'quoted' | 'list_price';
export type ChatFactSource = 'chat_rules' | 'chat_model' | 'chat_rules+model';
export type ChatServiceBasis = 'booking' | 'visit_day' | 'window';
export type ChatModelPassReason = 'disabled' | 'not_in_scope' | 'no_candidate_window' | 'call_cap' | 'no_account' | 'error' | 'ok';

/** One visit candidate of the analyzer (section 15.4), also the shape of an upcoming booking (no confidence). */
export interface ChatVisitCandidate {
  date: string; // 'YYYY-MM-DD', Asia/Ho_Chi_Minh
  time: string | null; // 'HH:MM'
  time_known: boolean;
  visited_at_local?: string; // 'YYYY-MM-DD HH:MM' (12:00 when the time is unknown)
  services: Array<{ service_id: string | null; service_name: string | null; basis: ChatServiceBasis }>; // 0 to 3
  amount_vnd: number | null; // 1 000 to 50 000 000
  amount_source: ChatAmountSource | null;
  technician: string | null; // one line, at most 60 characters
  confidence?: ChatConfidence | null; // required for a visit, omitted for an upcoming booking
  signals: string[]; // at most 20 codes
  evidence_at: Ms[]; // at most 5
  source: ChatFactSource;
}

/** One customer entry of the analyzer document (section 15.4). */
export interface ChatFactsEntry {
  zalo_user_id: string; // 'p:' + 1 to 32 digits
  relationship?: string; // the analyzer's; not used by the server
  relationship_confidence?: string;
  messages: number;
  first_at: Ms | null;
  last_at: Ms | null;
  visits: ChatVisitCandidate[]; // at most 400
  upcoming: ChatVisitCandidate[]; // at most 50
  phone: { value: string; confidence: 'high' | 'medium'; source: 'chat' | 'zalo_contact'; at?: Ms | null } | null;
  benefits: Array<{
    kind: BenefitKind;
    title: string; // one line, 1 to 120 characters
    service_id: string | null;
    total_count: number | null; // 1 to 200
    remaining: number | null; // 0 to 200, not above total_count
    stated_by: 'owner' | 'contact';
    confidence: 'high' | 'medium';
    at: Ms;
  }>; // at most 5
  model_pass: { ran: boolean; reason: ChatModelPassReason };
}

/** POST /staff/chat-facts/import (section 15.11). */
export interface ChatFactsImportRequest {
  analyzer_version: string; // 1 to 40 characters of [A-Za-z0-9._:+-]
  generated_at: Ms;
  dry_run?: boolean;
  customers: ChatFactsEntry[]; // 1 to 100
}

export interface ChatFactsImportResponse {
  customers: number; // entries processed (not skipped)
  unmatched: number; // processed entries without a customers row (stored all the same)
  skipped_internal: number; // manager / staff role, or a family / friend / personal / staff profile without a customer role
  skipped_deleted: number; // additive: the contact's customers row is deleted; its chat rows are removed
  visits_imported: number;
  visits_updated: number;
  visits_removed: number;
  visits_kept_staff: number;
  visits_tombstoned: number;
  phones_set: number;
  phones_taken: number; // additive: a number another customers row holds, neither set nor suggested
  phone_suggestions: number;
  benefits_upserted: number;
  benefits_kept_staff: number;
  dry_run: boolean;
}

/** One chat_visits row as staff read it (GET /staff/chat-facts/:zalo_user_id, decisions). */
export interface ChatVisitView {
  recorded_day?: boolean; // GET /staff/chat-facts/:id only: the customer has a recorded visit on local_date (not counted, no confirm)
  id: string; // 'chv_…'
  zalo_user_id: string;
  local_date: string;
  kind: ChatVisitKind;
  visited_at: Ms;
  time_known: boolean;
  time: string | null; // 'HH:MM' when time_known
  services: Array<{ service_id: string | null; service_name: string | null; basis: ChatServiceBasis; name: string }>; // name: catalog, else service_name, else service_id
  amount_vnd: number | null;
  amount_source: ChatAmountSource | null;
  technician: string | null;
  confidence: ChatConfidence | null;
  signals: string[];
  evidence: Ms[];
  fact_source: ChatFactSource;
  state: ChatFactState;
  confirmed_visit_id: string | null;
  analyzer_version: string;
  imported_at: Ms;
  decided_by: string | null;
  decided_at: Ms | null;
}

/** One chat_benefits row as staff read it. */
export interface ChatBenefitView {
  recorded_title?: boolean; // GET /staff/chat-facts/:id only: an active benefit of the customer has the same title key (no confirm)
  id: string; // 'chb_…'
  zalo_user_id: string;
  kind: BenefitKind;
  title: string;
  title_key: string;
  service_id: string | null;
  service_name: string | null; // the active catalog's name of service_id
  total_count: number | null;
  remaining: number | null;
  stated_by: 'owner' | 'contact';
  confidence: 'high' | 'medium';
  stated_at: Ms;
  state: ChatFactState;
  confirmed_benefit_id: string | null;
  analyzer_version: string;
  imported_at: Ms;
  decided_by: string | null;
  decided_at: Ms | null;
}

/** GET /staff/chat-facts/:zalo_user_id answers `{ facts: ChatFactsView | null }` (null: nothing stored). */
export interface ChatFactsView {
  visits: ChatVisitView[]; // kind 'visit', every state, newest first
  upcoming: ChatVisitView[]; // kind 'upcoming', every state, soonest first
  benefits: ChatBenefitView[]; // every state, newest statement first
  phone_suggestion: string | null; // shown to staff only
  analyzer_version: string | null;
  generated_at: Ms | null;
  imported_at: Ms | null;
  model_pass: { ran: boolean; reason: ChatModelPassReason | null } | null;
}

/** POST /staff/chat-facts/visits/:id/confirm (optional body; same validation as POST /staff/visits). */
export interface ChatVisitConfirmRequest {
  service_id?: string; // a service of the active catalog
  amount_vnd?: number | null;
  technician?: string | null;
  visited_at_local?: string; // 'YYYY-MM-DD HH:MM'
}

/** POST /staff/chat-facts/benefits/:id/confirm (optional body). */
export interface ChatBenefitConfirmRequest {
  title?: string;
  total_count?: number; // required when the guess has none
  used_count?: number; // default total_count - remaining when both are known, else 0
  expires_at?: Ms | null;
}
