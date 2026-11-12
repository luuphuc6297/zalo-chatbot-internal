-- Two-bot rooms, auto reply switch, contact roles and customer summary (docs/contracts.md section 14).
--
-- 1. visits is rebuilt because SQLite cannot change a CHECK constraint in place: source gains 'booking_request' and
--    'import' (POST /staff/visits/import). Every existing row is kept with its values. New columns, all NULL for the
--    rows that exist today:
--      service_name   name of a service outside the catalog (service_id = 'ext:<slug>'), or the name staff typed
--      duration_min   length of the visit in minutes
--      amount_vnd     what the customer paid, in VND. NULL = unknown (never counted as 0 in a sum)
--      technician     first name of the staff member who served the customer
--      benefit_id     customer_benefits.id of the package / voucher this visit used one count of
--    No table references visits by foreign key and the old table has no index.
CREATE TABLE visits_v10 (
  id                 TEXT PRIMARY KEY,
  customer_id        TEXT NOT NULL REFERENCES customers(id),
  service_id         TEXT NOT NULL,
  service_name       TEXT,
  visited_at         INTEGER NOT NULL,
  duration_min       INTEGER CHECK (duration_min IS NULL OR duration_min > 0),
  amount_vnd         INTEGER CHECK (amount_vnd IS NULL OR amount_vnd >= 0),
  technician         TEXT,
  benefit_id         TEXT,
  source             TEXT NOT NULL DEFAULT 'staff' CHECK (source IN ('staff','booking_app','booking_request','import')),
  external_visit_id  TEXT UNIQUE,
  booking_request_id TEXT,
  recorded_by        TEXT,
  created_at         INTEGER NOT NULL
);

INSERT INTO visits_v10 (id, customer_id, service_id, visited_at, source, external_visit_id, booking_request_id, recorded_by, created_at)
  SELECT id, customer_id, service_id, visited_at, source, external_visit_id, booking_request_id, recorded_by, created_at
  FROM visits;

DROP TABLE visits;
ALTER TABLE visits_v10 RENAME TO visits;

CREATE INDEX idx_visits_customer ON visits(customer_id, visited_at DESC);

-- Prepaid packages and vouchers of a customer. remaining = total_count - used_count. A visit recorded with
-- benefit_id adds 1 to used_count in the same batch as the visit row.
CREATE TABLE customer_benefits (
  id           TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL REFERENCES customers(id),
  kind         TEXT NOT NULL CHECK (kind IN ('package','voucher')),
  title        TEXT NOT NULL,
  service_id   TEXT,
  total_count  INTEGER NOT NULL CHECK (total_count > 0),
  used_count   INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0 AND used_count <= total_count),
  expires_at   INTEGER,
  status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','void')),
  recorded_by  TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);
CREATE INDEX idx_benefits_customer ON customer_benefits(customer_id, status);

-- Role of a personal Zalo contact, keyed like customer_profiles ('p:' + threadId). source 'zalo_label' rows come from
-- POST /staff/roles/import (the Zalo labels of the account), source 'staff' rows from PUT /staff/roles/:zalo_user_id.
-- A 'staff' row is never overwritten or removed by an import.
CREATE TABLE contact_roles (
  zalo_user_id TEXT PRIMARY KEY,
  role         TEXT NOT NULL CHECK (role IN ('customer','manager','staff')),
  source       TEXT NOT NULL CHECK (source IN ('zalo_label','staff')),
  updated_at   INTEGER NOT NULL,
  updated_by   TEXT NOT NULL
);

-- conversations.auto_reply: per-conversation switch of the automatic reply. NULL = follow the global setting.
-- room_channel_id / room_synced_at: the staff room this conversation is mirrored into and the time of the last copy.
ALTER TABLE conversations ADD COLUMN auto_reply TEXT CHECK (auto_reply IS NULL OR auto_reply IN ('on','off'));
ALTER TABLE conversations ADD COLUMN room_channel_id TEXT;
ALTER TABLE conversations ADD COLUMN room_synced_at INTEGER;

-- messages.room_mirrored_at: NULL = not yet copied into the room. The history before this migration is never
-- replayed, so every existing row is marked 0.
ALTER TABLE messages ADD COLUMN room_mirrored_at INTEGER;
UPDATE messages SET room_mirrored_at = 0;
CREATE INDEX idx_messages_room_pending ON messages(conversation_id, seq) WHERE room_mirrored_at IS NULL;
