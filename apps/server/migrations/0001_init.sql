-- thom house chatbot: initial schema (Cloudflare D1 / SQLite).
-- Conventions: every *_at column is INTEGER milliseconds since epoch (UTC); *_json columns hold JSON text;
-- ids are TEXT with a type prefix (see apps/server/src/lib/ids.ts); booleans are INTEGER 0/1.
-- Builders may only ADD new migrations (0002_*.sql, ...); never edit this file after phase 1.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- customers and consent

CREATE TABLE customers (
  id                        TEXT PRIMARY KEY,              -- cus_...
  oa_id                     TEXT NOT NULL,
  zalo_user_id              TEXT NOT NULL,                 -- sender.id of user_* events
  user_id_by_app            TEXT,
  display_name              TEXT,
  phone                     TEXT,                          -- only when shared with consent
  preferred_address_form    TEXT,                          -- 'anh' | 'chi' | NULL (unknown -> 'anh/chị')
  gender_hint               TEXT NOT NULL DEFAULT 'unknown',
  minor_flag                INTEGER,                       -- NULL unknown, 1 = Zalo is_sensitive
  created_at                INTEGER NOT NULL,
  last_user_interaction_at  INTEGER,                       -- for the 7-day consultation-message window
  deleted_at                INTEGER,
  UNIQUE (oa_id, zalo_user_id)
);

CREATE TABLE consents (
  id                   TEXT PRIMARY KEY,                   -- cns_...
  customer_id          TEXT NOT NULL REFERENCES customers(id),
  purpose              TEXT NOT NULL CHECK (purpose IN ('ai_assistant','followup_care','promotions','health_data')),
  status               TEXT NOT NULL CHECK (status IN ('granted','withdrawn')),
  source               TEXT NOT NULL CHECK (source IN ('button','chat_keyword','form','staff')),
  evidence_message_id  TEXT,
  recorded_at          INTEGER NOT NULL
);
CREATE INDEX idx_consents_customer ON consents(customer_id, purpose, recorded_at);

CREATE TABLE contact_preferences (
  id               TEXT PRIMARY KEY,                       -- cpf_...
  customer_id      TEXT NOT NULL REFERENCES customers(id),
  preference_type  TEXT NOT NULL CHECK (preference_type IN ('promotions','followup_care','all_proactive_messages','ai_assistant')),
  action           TEXT NOT NULL CHECK (action IN ('opt_out','request_opt_in')),
  customer_words   TEXT,
  source           TEXT NOT NULL CHECK (source IN ('model_tool','keyword','staff','button')),
  job_id           TEXT,
  idempotency_key  TEXT UNIQUE,
  created_at       INTEGER NOT NULL
);
CREATE INDEX idx_contact_prefs_customer ON contact_preferences(customer_id, created_at);

-- ---------------------------------------------------------------- conversations and messages

CREATE TABLE conversations (
  id                        TEXT PRIMARY KEY,              -- cnv_... (internal id; never the Zalo id)
  customer_id               TEXT NOT NULL UNIQUE REFERENCES customers(id),
  oa_id                     TEXT NOT NULL,
  bot_state                 TEXT NOT NULL DEFAULT 'awaiting_consent'
                            CHECK (bot_state IN ('awaiting_consent','bot_active','handoff_requested','staff_takeover','staff_only','blocked')),
  mode                      TEXT CHECK (mode IS NULL OR mode IN ('off','draft_only','approve_each','auto_allowed')), -- NULL = inherit flag auto_reply_mode
  takeover_by               TEXT,
  takeover_until            INTEGER,
  needs_attention           INTEGER NOT NULL DEFAULT 0,
  session_id                TEXT,                          -- Claude Code session id used with --resume
  session_turns             INTEGER NOT NULL DEFAULT 0,    -- customer turns drafted in this session
  session_started_at        INTEGER,
  session_last_turn_at      INTEGER,
  catalog_version           TEXT,                          -- catalog version the current session was started with
  session_reset_reason      TEXT,                          -- set when the server decides the next job starts a new session
  last_message_at           INTEGER,
  last_customer_message_at  INTEGER,
  debounce_until            INTEGER,
  created_at                INTEGER NOT NULL,
  updated_at                INTEGER NOT NULL
);
CREATE INDEX idx_conversations_last ON conversations(last_message_at DESC);
CREATE INDEX idx_conversations_state ON conversations(bot_state, needs_attention);

CREATE TABLE messages (
  id                 TEXT PRIMARY KEY,                     -- msg_...
  conversation_id    TEXT NOT NULL REFERENCES conversations(id),
  direction          TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
  source             TEXT NOT NULL CHECK (source IN ('customer','bot','staff','server')),
  kind               TEXT NOT NULL DEFAULT 'text',         -- text | image | sticker | file | link | buttons | template | other
  text               TEXT,
  attachments_json   TEXT,
  zalo_msg_id        TEXT UNIQUE,
  zalo_timestamp     INTEGER,
  event_key          TEXT,
  draft_id           TEXT,
  staff_id           TEXT,
  zalo_admin_id      TEXT,                                 -- sender.admin_id of oa_send_* sent from OA Manager
  catalog_version    TEXT,
  send_state         TEXT NOT NULL DEFAULT 'not_applicable'
                     CHECK (send_state IN ('not_applicable','pending','sent','unknown','failed')),
  send_error         TEXT,
  client_send_id     TEXT UNIQUE,
  model              TEXT,
  account_label      TEXT,
  input_tokens       INTEGER,
  output_tokens      INTEGER,
  cache_read_tokens  INTEGER,
  cache_write_tokens INTEGER,
  cost_usd_equiv     REAL,
  created_at         INTEGER NOT NULL,
  sent_at            INTEGER
);
CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE events_inbox (
  event_key        TEXT PRIMARY KEY,                       -- event_name + ':' + msg_id, else 'sha256:' + hex(body)
  event_name       TEXT NOT NULL,
  zalo_msg_id      TEXT,
  oa_id            TEXT,
  zalo_user_id     TEXT,
  zalo_timestamp   INTEGER,
  num_retry        INTEGER NOT NULL DEFAULT 0,
  signature_ok     INTEGER NOT NULL,
  signature_mode   TEXT NOT NULL,                          -- observe | enforce
  raw_body         TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'received'
                   CHECK (status IN ('received','dispatched','processed','ignored','failed')),
  attempts         INTEGER NOT NULL DEFAULT 0,
  error            TEXT,
  received_at      INTEGER NOT NULL,
  processed_at     INTEGER
);
CREATE INDEX idx_events_status ON events_inbox(status, received_at);

-- ---------------------------------------------------------------- jobs, drafts, tool calls

CREATE TABLE jobs (
  id               TEXT PRIMARY KEY,                       -- job_...
  type             TEXT NOT NULL CHECK (type IN ('draft_reply','thank_you','check_in','promo_send','token_watch','inbox_sweep')),
  conversation_id  TEXT REFERENCES conversations(id),
  customer_id      TEXT REFERENCES customers(id),
  status           TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued','leased','done','failed','cancelled','expired','skipped','needs_staff')),
  run_at           INTEGER NOT NULL,
  lease_until      INTEGER,
  lease_owner      TEXT,                                   -- runner_id for draft_reply, 'cron' for scheduled jobs
  attempts         INTEGER NOT NULL DEFAULT 0,
  max_attempts     INTEGER NOT NULL DEFAULT 1,
  max_lateness_ms  INTEGER,
  stale            INTEGER NOT NULL DEFAULT 0,             -- draft_reply: a newer customer message arrived after claim
  payload_json     TEXT NOT NULL DEFAULT '{}',
  result_json      TEXT,
  dedupe_key       TEXT UNIQUE,
  last_error       TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX idx_jobs_due ON jobs(status, run_at);
CREATE INDEX idx_jobs_conv ON jobs(conversation_id, type, status);

CREATE TABLE drafts (
  id                   TEXT PRIMARY KEY,                   -- drf_...
  job_id               TEXT NOT NULL UNIQUE REFERENCES jobs(id),
  conversation_id      TEXT NOT NULL REFERENCES conversations(id),
  text                 TEXT NOT NULL,                      -- as written by the model
  final_text           TEXT,                               -- as sent (after staff edits)
  status               TEXT NOT NULL
                       CHECK (status IN ('pending','approved','rejected','sent','blocked','superseded','discarded','send_failed')),
  checker_passed       INTEGER NOT NULL,
  checker_result_json  TEXT NOT NULL,
  account_label        TEXT,
  session_id           TEXT,
  model                TEXT,
  effort               TEXT,
  usage_json           TEXT,
  cost_usd_equiv       REAL,
  duration_ms          INTEGER,
  catalog_version      TEXT,
  decided_by           TEXT,
  decided_at           INTEGER,
  reject_reason        TEXT,
  sent_message_id      TEXT,
  created_at           INTEGER NOT NULL
);
CREATE INDEX idx_drafts_conv ON drafts(conversation_id, status, created_at);

CREATE TABLE tool_calls (
  id               TEXT PRIMARY KEY,                       -- tcl_...
  job_id           TEXT NOT NULL REFERENCES jobs(id),
  conversation_id  TEXT NOT NULL REFERENCES conversations(id),
  tool_name        TEXT NOT NULL,
  input_json       TEXT NOT NULL,
  result_json      TEXT NOT NULL,
  is_error         INTEGER NOT NULL DEFAULT 0,
  idempotency_key  TEXT UNIQUE,                            -- write tools only: job_id + ':' + tool + ':' + sha256(canonical input)
  catalog_version  TEXT,
  created_at       INTEGER NOT NULL
);
CREATE INDEX idx_tool_calls_conv ON tool_calls(conversation_id, created_at);

-- ---------------------------------------------------------------- staff work items

CREATE TABLE handoffs (
  id                 TEXT PRIMARY KEY,                     -- hof_...
  conversation_id    TEXT NOT NULL REFERENCES conversations(id),
  customer_id        TEXT NOT NULL REFERENCES customers(id),
  job_id             TEXT,
  source             TEXT NOT NULL CHECK (source IN ('model_tool','server','runner_failure','staff')),
  reason_code        TEXT NOT NULL,                        -- tools-schema reason codes + server codes (see docs/contracts.md)
  urgency            TEXT NOT NULL CHECK (urgency IN ('urgent','normal')),
  summary_for_staff  TEXT,
  status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
  idempotency_key    TEXT UNIQUE,
  created_at         INTEGER NOT NULL,
  resolved_by        TEXT,
  resolved_at        INTEGER
);
CREATE INDEX idx_handoffs_status ON handoffs(status, created_at);

CREATE TABLE booking_requests (
  id                     TEXT PRIMARY KEY,                 -- brq_...
  conversation_id        TEXT NOT NULL REFERENCES conversations(id),
  customer_id            TEXT NOT NULL REFERENCES customers(id),
  job_id                 TEXT,
  service_ids_json       TEXT NOT NULL,
  duration_min           INTEGER NOT NULL DEFAULT 0,
  preferred_date_local   TEXT NOT NULL,
  preferred_time_window  TEXT NOT NULL,
  party_size             INTEGER NOT NULL,
  customer_name          TEXT NOT NULL,
  contact_method         TEXT NOT NULL CHECK (contact_method IN ('zalo_chat_only','phone_shared_with_consent')),
  phone                  TEXT,
  notes_for_staff        TEXT,
  price_quoted_text      TEXT,
  catalog_version        TEXT,
  status                 TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','proposed','confirmed','cancelled','expired')),
  staff_note             TEXT,
  handled_by             TEXT,
  external_booking_id    TEXT,
  idempotency_key        TEXT UNIQUE,
  created_at             INTEGER NOT NULL,
  updated_at             INTEGER NOT NULL
);
CREATE INDEX idx_booking_status ON booking_requests(status, created_at);

CREATE TABLE visits (
  id                 TEXT PRIMARY KEY,                     -- vis_...
  customer_id        TEXT NOT NULL REFERENCES customers(id),
  service_id         TEXT NOT NULL,
  visited_at         INTEGER NOT NULL,
  source             TEXT NOT NULL DEFAULT 'staff' CHECK (source IN ('staff','booking_app')),
  external_visit_id  TEXT UNIQUE,
  booking_request_id TEXT,
  recorded_by        TEXT,
  created_at         INTEGER NOT NULL
);

-- ---------------------------------------------------------------- catalog, facts, prompt assets

CREATE TABLE catalog_versions (
  id            TEXT PRIMARY KEY,                          -- e.g. cv_2026_11_07_seed
  status        TEXT NOT NULL CHECK (status IN ('draft','approved','active','retired')),
  source_ref    TEXT,
  notes         TEXT,
  created_by    TEXT,
  created_at    INTEGER NOT NULL,
  approved_by   TEXT,
  approved_at   INTEGER,
  activated_at  INTEGER
);
CREATE UNIQUE INDEX idx_one_active_catalog ON catalog_versions(status) WHERE status = 'active';

CREATE TABLE services (
  catalog_version       TEXT NOT NULL REFERENCES catalog_versions(id),
  service_id            TEXT NOT NULL,                     -- slug from data/services.json, e.g. goi-dau-thu-gian
  group_code            TEXT NOT NULL CHECK (group_code IN ('relaxation','health','women','skin','hair')),
  display_name_vi       TEXT NOT NULL,
  name_vi               TEXT NOT NULL,
  short_description_vi  TEXT,
  process_steps_json    TEXT NOT NULL DEFAULT '[]',
  notes_vi              TEXT,
  is_signature          INTEGER NOT NULL DEFAULT 0,
  approval_status       TEXT NOT NULL DEFAULT 'draft_unapproved',
  raw_json              TEXT NOT NULL,                     -- full source object (flagged_claims etc. never reach the model)
  PRIMARY KEY (catalog_version, service_id)
);

CREATE TABLE service_variants (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog_version  TEXT NOT NULL,
  service_id       TEXT NOT NULL,
  duration_min     INTEGER NOT NULL,
  time_window      TEXT,                                   -- '09:00-20:30' | 'after_20:30' | '09:00-24:00' | NULL
  price_vnd        INTEGER NOT NULL,
  condition_note   TEXT,
  FOREIGN KEY (catalog_version, service_id) REFERENCES services(catalog_version, service_id)
);
CREATE INDEX idx_variants_service ON service_variants(catalog_version, service_id);

CREATE TABLE facts (
  catalog_version  TEXT NOT NULL REFERENCES catalog_versions(id),
  key              TEXT NOT NULL,
  value_json       TEXT,
  status           TEXT NOT NULL,                          -- documented | conflict | derived_unapproved | missing | approved
  note             TEXT,
  PRIMARY KEY (catalog_version, key)
);

CREATE TABLE promotions (
  id                TEXT PRIMARY KEY,                      -- prm_...
  title             TEXT NOT NULL,
  approved_text_vi  TEXT NOT NULL,
  conditions_vi     TEXT,
  service_ids_json  TEXT NOT NULL DEFAULT '[]',
  valid_from        INTEGER NOT NULL,
  valid_to          INTEGER NOT NULL,
  status            TEXT NOT NULL CHECK (status IN ('draft','approved','scheduled','sending','done','cancelled')),
  created_by        TEXT,
  approved_by       TEXT,
  approved_at       INTEGER,
  created_at        INTEGER NOT NULL
);

CREATE TABLE prompt_assets (
  key         TEXT PRIMARY KEY,                            -- 'block_a' | 'tools_schema' | 'cli_tool_note'
  body        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- ---------------------------------------------------------------- flags, tokens, outbox, audit, runner

CREATE TABLE flags (
  name        TEXT PRIMARY KEY,
  value_json  TEXT NOT NULL,
  updated_by  TEXT NOT NULL DEFAULT 'migration',
  updated_at  INTEGER NOT NULL
);
INSERT INTO flags (name, value_json, updated_at) VALUES
  ('auto_reply_mode',         '"approve_each"', 0),
  ('ai_calls_enabled',        'true',           0),
  ('ai_engine',               '"subscription"', 0),
  ('scheduled_sends_enabled', 'false',          0),
  ('outbound_enabled',        'true',           0),
  ('promotions_enabled',      'false',          0),
  ('runner_desired_account',  '"auto"',         0);

CREATE TABLE oa_tokens (
  id                 INTEGER PRIMARY KEY CHECK (id = 1),   -- single row; refresh is serialized with a conditional UPDATE on refresh_lock_until
  access_token       TEXT,
  refresh_token      TEXT,
  access_expires_at  INTEGER,
  refresh_issued_at  INTEGER,
  auth_state         TEXT NOT NULL DEFAULT 'missing' CHECK (auth_state IN ('ok','reauth_required','missing')),
  refresh_lock_until INTEGER,
  updated_at         INTEGER NOT NULL
);

CREATE TABLE outbox (
  id               TEXT PRIMARY KEY,                       -- obx_...
  kind             TEXT NOT NULL CHECK (kind IN ('cs_text','cs_buttons','zbs_template')),
  zalo_mode        TEXT NOT NULL CHECK (zalo_mode IN ('mock','real')),
  conversation_id  TEXT,
  customer_id      TEXT,
  zalo_user_id     TEXT NOT NULL,
  message_id       TEXT,                                   -- messages.id this send belongs to
  payload_json     TEXT NOT NULL,                          -- exact request body that is (or would be) sent to Zalo
  status           TEXT NOT NULL CHECK (status IN ('pending','sent','failed','unknown')),
  zalo_msg_id      TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  sent_at          INTEGER
);
CREATE INDEX idx_outbox_created ON outbox(created_at DESC);

CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          INTEGER NOT NULL,
  actor_type  TEXT NOT NULL CHECK (actor_type IN ('staff','system','model','runner','zalo')),
  actor_id    TEXT,
  action      TEXT NOT NULL,
  entity      TEXT,
  entity_id   TEXT,
  before_json TEXT,
  after_json  TEXT,
  request_id  TEXT
);
CREATE INDEX idx_audit_entity ON audit_log(entity, entity_id, at);

CREATE TABLE runner_status (
  runner_id      TEXT PRIMARY KEY,
  last_seen_at   INTEGER NOT NULL,                         -- any authenticated runner call
  last_claim_at  INTEGER,
  last_status_at INTEGER,
  version        TEXT,
  snapshot_json  TEXT                                      -- last RunnerStatusRequest body
);
