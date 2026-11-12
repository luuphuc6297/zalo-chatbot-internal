-- Contact profiles v2 (docs/contracts.md section 13, analyzer contacts-rules-v3, 2026-11-08).
--
-- 1. relationship gains 'staff', 'family' and 'friend'. 'personal' stays valid for rows written by analyzer v2 or set
--    by staff before this migration; analyzer v3 never writes it. SQLite cannot change a CHECK constraint in place, so
--    the table is rebuilt with every row copied as it is (same columns, same values, same indexes).
-- 2. last_service_json: the analyzer's latest likely-used service from chat, as JSON
--    {"key","service_id","name","at","source":"chat","confidence","sensitive"} or NULL. The server merges it with the
--    newest staff-recorded visit (visits table) when it builds the staff view and the model facts; a recorded visit
--    newer than the chat signal wins.
--
-- The quiet staff_only rule (flag profile_personal_skip_bot) now applies to relationship family / staff / friend
-- (and the legacy 'personal') at confidence 'high', and to any of them regardless of confidence when
-- staff_override = 1 (src/lib/profiles.ts personalSkipApplies).
CREATE TABLE customer_profiles_v2 (
  zalo_user_id              TEXT PRIMARY KEY,                -- 'p:' + threadId
  display_name              TEXT,
  relationship              TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (relationship IN ('customer','staff','family','friend','personal','unknown')),
  relationship_confidence   TEXT NOT NULL DEFAULT 'low' CHECK (relationship_confidence IN ('low','medium','high')),
  relationship_reasons_json TEXT NOT NULL DEFAULT '[]',
  address_term              TEXT CHECK (address_term IS NULL OR address_term IN ('chị','anh','cô','chú','bác','anh/chị')),
  name_to_use               TEXT,
  address_confidence        TEXT NOT NULL DEFAULT 'low' CHECK (address_confidence IN ('low','medium','high')),
  addressing_json           TEXT NOT NULL DEFAULT '{}',
  services_json             TEXT NOT NULL DEFAULT '[]',
  evidence_json             TEXT NOT NULL DEFAULT '[]',
  stats_json                TEXT NOT NULL DEFAULT '{}',
  analyzer_json             TEXT,
  analyzer_version          TEXT,
  source                    TEXT NOT NULL DEFAULT 'analyzer' CHECK (source IN ('analyzer','staff')),
  staff_override            INTEGER NOT NULL DEFAULT 0 CHECK (staff_override IN (0,1)),
  staff_fields_json         TEXT NOT NULL DEFAULT '[]',
  staff_note                TEXT,
  analyzed_at               INTEGER,
  created_at                INTEGER NOT NULL,
  updated_at                INTEGER NOT NULL,
  updated_by                TEXT NOT NULL,
  last_service_json         TEXT                              -- analyzer's last service from chat (see above)
);

INSERT INTO customer_profiles_v2 (
  zalo_user_id, display_name, relationship, relationship_confidence, relationship_reasons_json, address_term,
  name_to_use, address_confidence, addressing_json, services_json, evidence_json, stats_json, analyzer_json,
  analyzer_version, source, staff_override, staff_fields_json, staff_note, analyzed_at, created_at, updated_at,
  updated_by, last_service_json)
SELECT
  zalo_user_id, display_name, relationship, relationship_confidence, relationship_reasons_json, address_term,
  name_to_use, address_confidence, addressing_json, services_json, evidence_json, stats_json, analyzer_json,
  analyzer_version, source, staff_override, staff_fields_json, staff_note, analyzed_at, created_at, updated_at,
  updated_by, NULL
FROM customer_profiles;

DROP TABLE customer_profiles;
ALTER TABLE customer_profiles_v2 RENAME TO customer_profiles;
CREATE INDEX idx_customer_profiles_rel ON customer_profiles(relationship, relationship_confidence);
CREATE INDEX idx_customer_profiles_updated ON customer_profiles(updated_at DESC);
