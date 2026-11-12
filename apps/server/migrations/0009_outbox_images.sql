-- Menu images on the personal Zalo channel (docs/contracts.md section 12, "Menu images").
--
-- outbox is rebuilt because SQLite cannot change a CHECK constraint in place: kind gets the value 'cs_images' (a row
-- that sends menu slides with `zalo-agent msg send-image`). Every existing row and column is kept. New columns:
--   image_keys   cs_images: JSON array of 1..10 menu image keys ('<group>/<n>' from data/menu-images.json). Never a
--                file path: the bridge resolves keys to local JPEGs through ~/.thomhouse-bot/menu-images/manifest.json
--   depends_on   cs_images: outbox id of the text row of the same draft. The image row is handed out only after that
--                row is 'sent'; when it ends 'failed' or 'unknown' the image row is cancelled (staff can requeue both)
--   echo_count   number of self-sent webhook events matched to this row (one per image of a cs_images row); limits
--                the time-window echo match of photos without a matching msgId
CREATE TABLE outbox_v9 (
  id               TEXT PRIMARY KEY,
  kind             TEXT NOT NULL CHECK (kind IN ('cs_text','cs_buttons','zbs_template','cs_images')),
  zalo_mode        TEXT NOT NULL CHECK (zalo_mode IN ('mock','real','personal')),
  conversation_id  TEXT,
  customer_id      TEXT,
  zalo_user_id     TEXT NOT NULL,
  message_id       TEXT,
  payload_json     TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('pending','queued','leased','sent','failed','unknown')),
  zalo_msg_id      TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  sent_at          INTEGER,
  dedupe_key       TEXT,
  template_key     TEXT,
  channel          TEXT NOT NULL DEFAULT 'oa' CHECK (channel IN ('oa','personal')),
  thread_id        TEXT,
  text             TEXT,
  attempts         INTEGER NOT NULL DEFAULT 0,
  next_attempt_at  INTEGER,
  lease_owner      TEXT,
  lease_until      INTEGER,
  last_claimed_at  INTEGER,
  echo_msg_id      TEXT,
  updated_at       INTEGER,
  requeued_at      INTEGER,
  part_msg_ids     TEXT,
  image_keys       TEXT,
  depends_on       TEXT,
  echo_count       INTEGER NOT NULL DEFAULT 0
);

INSERT INTO outbox_v9 (id, kind, zalo_mode, conversation_id, customer_id, zalo_user_id, message_id, payload_json, status, zalo_msg_id,
                       error, created_at, sent_at, dedupe_key, template_key, channel, thread_id, text, attempts, next_attempt_at,
                       lease_owner, lease_until, last_claimed_at, echo_msg_id, updated_at, requeued_at, part_msg_ids, echo_count)
  SELECT id, kind, zalo_mode, conversation_id, customer_id, zalo_user_id, message_id, payload_json, status, zalo_msg_id,
         error, created_at, sent_at, dedupe_key, template_key, channel, thread_id, text, attempts, next_attempt_at,
         lease_owner, lease_until, last_claimed_at, echo_msg_id, updated_at, requeued_at, part_msg_ids,
         CASE WHEN echo_msg_id IS NULL THEN 0 ELSE 1 END
  FROM outbox;

DROP TABLE outbox;
ALTER TABLE outbox_v9 RENAME TO outbox;

CREATE INDEX idx_outbox_created ON outbox(created_at DESC);
CREATE UNIQUE INDEX idx_outbox_dedupe ON outbox(dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX idx_outbox_bridge ON outbox(channel, status, created_at);
CREATE INDEX idx_outbox_thread ON outbox(thread_id, created_at);
CREATE INDEX idx_outbox_zalo_msg ON outbox(zalo_msg_id) WHERE zalo_msg_id IS NOT NULL;
CREATE INDEX idx_outbox_depends ON outbox(depends_on) WHERE depends_on IS NOT NULL;

-- drafts.attachments_json: JSON array of the menu image keys the model attached with the attach_menu_images tool in
-- the draft's job (NULL = none). Approving the draft queues the text row, then one cs_images row with these keys.
ALTER TABLE drafts ADD COLUMN attachments_json TEXT;
