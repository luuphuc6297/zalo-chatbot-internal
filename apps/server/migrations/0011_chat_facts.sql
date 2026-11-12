-- Customer facts guessed from old one-to-one Zalo chats (docs/contracts.md section 15, sections 15.9 to 15.12).
--
-- scripts/analyze_visits.py reads the synced chat history with rules and pushes its guesses to
-- POST /staff/chat-facts/import. The guesses live in their own tables, keyed by zalo_user_id ('p:' + digits, the key
-- of customer_profiles and contact_roles), never in visits or customer_benefits: a historical contact often has no
-- customers row yet, a visits row would get thank-you and check-in follow-ups, and each analyzer run replaces its own
-- 'active' rows, which must never touch a record staff typed. Staff turn a guess into a record (confirm: state
-- 'confirmed' and the id of the record created) or remove it (dismiss: state 'dismissed', kept as a tombstone so the
-- next run does not bring it back). Only new tables: no existing row is touched.
--
-- Edited on 2026-11-12 before it was applied anywhere: chat_contact_facts.phone_decision_id and chat_phone_dismissed
-- were added. A database that applied the earlier text needs those two statements by hand (the server answers 409
-- naming this file until then).

-- One guessed visit (kind 'visit') or upcoming booking (kind 'upcoming') per contact per local date.
CREATE TABLE chat_visits (
  id                 TEXT PRIMARY KEY,                    -- chv_...
  zalo_user_id       TEXT NOT NULL,                       -- 'p:' + 1 to 32 digits
  local_date         TEXT NOT NULL,                       -- 'YYYY-MM-DD', Asia/Ho_Chi_Minh
  kind               TEXT NOT NULL CHECK (kind IN ('visit','upcoming')),
  visited_at         INTEGER NOT NULL,                    -- ms of the local date and time (12:00 when the time is unknown)
  time_known         INTEGER NOT NULL CHECK (time_known IN (0,1)),
  services_json      TEXT NOT NULL,                       -- 0 to 3 {service_id, service_name, basis}
  amount_vnd         INTEGER CHECK (amount_vnd IS NULL OR (amount_vnd >= 1000 AND amount_vnd <= 50000000)),
  amount_source      TEXT CHECK (amount_source IS NULL OR amount_source IN ('paid','quoted','list_price')),
  technician         TEXT,                                -- one line, at most 60 characters
  confidence         TEXT CHECK (confidence IS NULL OR confidence IN ('high','medium','low')), -- NULL for 'upcoming'
  signals_json       TEXT NOT NULL,                       -- signal codes, at most 20
  evidence_json      TEXT NOT NULL,                       -- at most 5 message times (ms); never a message text
  fact_source        TEXT NOT NULL CHECK (fact_source IN ('chat_rules','chat_model','chat_rules+model')),
  state              TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','confirmed','dismissed')),
  confirmed_visit_id TEXT,                                -- visits.id created by confirm
  analyzer_version   TEXT NOT NULL,
  imported_at        INTEGER NOT NULL,
  decided_by         TEXT,                                -- staff id of the confirm or dismiss
  decided_at         INTEGER,
  UNIQUE (zalo_user_id, local_date, kind)
);
CREATE INDEX idx_chat_visits_contact ON chat_visits(zalo_user_id, state);

-- Packages and vouchers named in the chat, at most 5 per contact. title_key (accent-folded, lower case, spaces
-- collapsed) is the identity of a benefit across analyzer runs.
CREATE TABLE chat_benefits (
  id                   TEXT PRIMARY KEY,                  -- chb_...
  zalo_user_id         TEXT NOT NULL,
  kind                 TEXT NOT NULL CHECK (kind IN ('package','voucher')),
  title                TEXT NOT NULL,                     -- one line, 1 to 120 characters
  title_key            TEXT NOT NULL,
  service_id           TEXT,
  total_count          INTEGER CHECK (total_count IS NULL OR (total_count >= 1 AND total_count <= 200)),
  remaining            INTEGER CHECK (remaining IS NULL OR (remaining >= 0 AND remaining <= 200 AND (total_count IS NULL OR remaining <= total_count))),
  stated_by            TEXT NOT NULL CHECK (stated_by IN ('owner','contact')),
  confidence           TEXT NOT NULL CHECK (confidence IN ('high','medium')),
  stated_at            INTEGER NOT NULL,
  state                TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','confirmed','dismissed')),
  confirmed_benefit_id TEXT,                              -- customer_benefits.id created by confirm
  analyzer_version     TEXT NOT NULL,
  imported_at          INTEGER NOT NULL,
  decided_by           TEXT,
  decided_at           INTEGER,
  UNIQUE (zalo_user_id, title_key)
);

-- One row per contact seen by an import: counts, the run, and the phone number suggestion. phone_suggestion is shown
-- to staff only; a number staff dismissed moves to phone_dismissed (the latest one) and to chat_phone_dismissed (all
-- of them), and is never suggested again.
CREATE TABLE chat_contact_facts (
  zalo_user_id      TEXT PRIMARY KEY,
  analyzer_version  TEXT NOT NULL,
  generated_at      INTEGER NOT NULL,                     -- generated_at of the analyzer document
  imported_at       INTEGER NOT NULL,
  messages          INTEGER NOT NULL,
  first_at          INTEGER,
  last_at           INTEGER,
  phone_suggestion  TEXT,                                 -- '0' + 9 digits, or NULL
  phone_state       TEXT CHECK (phone_state IS NULL OR phone_state = 'dismissed'),
  phone_dismissed   TEXT,                                 -- the number staff dismissed last
  phone_decision_id TEXT,                                 -- random id of the last staff accept or dismiss (audit guard)
  model_pass_json   TEXT NOT NULL                         -- {ran, reason}
);

-- Every phone number that must not come back for a contact: a suggestion staff dismissed, or a number staff removed
-- from or replaced in customers.phone. The import neither writes such a number into customers.phone nor suggests it.
CREATE TABLE chat_phone_dismissed (
  zalo_user_id TEXT NOT NULL,
  phone        TEXT NOT NULL,                             -- normalised digits
  reason       TEXT NOT NULL CHECK (reason IN ('suggestion_dismissed','staff_removed')),
  decided_by   TEXT,                                      -- staff id
  decided_at   INTEGER NOT NULL,
  PRIMARY KEY (zalo_user_id, phone)
);
