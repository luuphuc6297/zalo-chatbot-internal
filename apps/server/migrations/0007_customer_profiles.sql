-- Contact profiles of the personal Zalo channel (docs/contracts.md "Contact profiles"). Written by
-- scripts/analyze_contacts.py (rules only, run locally over the engine's zalo.db) through POST /staff/profiles/import,
-- and corrected by staff through PATCH /staff/profiles/:zalo_user_id. Keyed by the customer's zalo_user_id
-- ('p:' + threadId) so a profile can exist before the contact writes again and the customers row is created.
--
-- Columns the model may see, after server-side filtering (src/lib/profiles.ts profileFactsForModel):
--   address_term, name_to_use, the catalog names of services in services_json, relationship (never 'personal').
-- Never sent to the model: evidence_json (local snippets for staff), stats_json, addressing_json, reasons, staff_note.
--
-- staff_fields_json: the field groups staff edited, a subset of ["relationship","address","name","services"]
-- (relationship = relationship + relationship_confidence, address = address_term + address_confidence,
-- name = name_to_use, services = services_json). An import keeps the fields of those groups as staff left them and
-- refreshes the others; it always refreshes display_name, addressing_json, relationship_reasons_json, evidence_json,
-- stats_json, analyzer_json and analyzed_at. staff_override = 1 exactly when staff_fields_json is not empty.
-- analyzer_json holds the latest analyzer values of the six editable fields, so clearing the override restores them.
CREATE TABLE customer_profiles (
  zalo_user_id              TEXT PRIMARY KEY,                -- 'p:' + threadId
  display_name              TEXT,
  relationship              TEXT NOT NULL DEFAULT 'unknown' CHECK (relationship IN ('customer','personal','unknown')),
  relationship_confidence   TEXT NOT NULL DEFAULT 'low' CHECK (relationship_confidence IN ('low','medium','high')),
  relationship_reasons_json TEXT NOT NULL DEFAULT '[]',       -- reason codes, e.g. ["service_vocab:4","catalog_match:2"]
  address_term              TEXT CHECK (address_term IS NULL OR address_term IN ('chị','anh','cô','chú','bác','anh/chị')),
  name_to_use               TEXT,
  address_confidence        TEXT NOT NULL DEFAULT 'low' CHECK (address_confidence IN ('low','medium','high')),
  addressing_json           TEXT NOT NULL DEFAULT '{}',       -- pronoun counts behind the recommendation
  services_json             TEXT NOT NULL DEFAULT '[]',
  evidence_json             TEXT NOT NULL DEFAULT '[]',       -- at most 3 snippets of <= 80 chars; staff console only
  stats_json                TEXT NOT NULL DEFAULT '{}',
  analyzer_json             TEXT,                             -- latest analyzer values of the staff-editable fields
  analyzer_version          TEXT,
  source                    TEXT NOT NULL DEFAULT 'analyzer' CHECK (source IN ('analyzer','staff')),  -- who created the row
  staff_override            INTEGER NOT NULL DEFAULT 0 CHECK (staff_override IN (0,1)),
  staff_fields_json         TEXT NOT NULL DEFAULT '[]',       -- field groups staff edited (see above)
  staff_note                TEXT,
  analyzed_at               INTEGER,
  created_at                INTEGER NOT NULL,
  updated_at                INTEGER NOT NULL,
  updated_by                TEXT NOT NULL
);
CREATE INDEX idx_customer_profiles_rel ON customer_profiles(relationship, relationship_confidence);
CREATE INDEX idx_customer_profiles_updated ON customer_profiles(updated_at DESC);

-- true: a contact whose profile says relationship 'personal' with confidence 'high' (and who has not granted
-- ai_assistant consent) is set to staff_only on their next message, quietly: no consent prompt, needs_attention = 1.
INSERT OR IGNORE INTO flags (name, value_json, updated_at) VALUES ('profile_personal_skip_bot', 'true', 0);
