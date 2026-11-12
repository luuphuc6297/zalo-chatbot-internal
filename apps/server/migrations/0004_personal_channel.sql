-- Personal Zalo channel (docs/contracts.md "Personal Zalo channel"). The local app talks to customers through a
-- personal Zalo account driven by the unofficial engine @ardennguyen/zalo-agent-cli; apps/zalo-bridge claims
-- queued outbox rows over the bridge API and sends them with `zalo-agent msg send`.

-- customers.channel: 'oa' (Zalo OA webhook) or 'personal' (personal account). Personal customers are stored with
-- oa_id = 'personal' and zalo_user_id = 'p:' + threadId, so an OA user id can never collide with a personal one.
ALTER TABLE customers ADD COLUMN channel TEXT NOT NULL DEFAULT 'oa';

-- outbox is rebuilt because SQLite cannot change a CHECK constraint in place. New values:
--   zalo_mode 'personal'; status 'queued' (waiting for the bridge) and 'leased' (claimed, lease_until running).
-- New columns (NULL / default for every OA row):
--   channel          'oa' | 'personal'
--   thread_id        personal: the Zalo threadId the bridge sends to (zalo_user_id without the 'p:' prefix)
--   text             personal: the exact plain text the bridge sends (buttons and templates already rendered)
--   attempts         personal: number of claims so far
--   next_attempt_at  personal: earliest claim time (retry backoff after a 'failed' result)
--   lease_owner      personal: X-Bridge-Id of the current claim
--   lease_until      personal: end of the 60 s claim lease
--   last_claimed_at  personal: time of the latest claim (echo matching window starts here)
--   echo_msg_id      personal: msgId of the self-sent webhook event that matched this row
--   updated_at       last change of the row
CREATE TABLE outbox_v4 (
  id               TEXT PRIMARY KEY,
  kind             TEXT NOT NULL CHECK (kind IN ('cs_text','cs_buttons','zbs_template')),
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
  updated_at       INTEGER
);

INSERT INTO outbox_v4 (id, kind, zalo_mode, conversation_id, customer_id, zalo_user_id, message_id, payload_json, status, zalo_msg_id, error, created_at, sent_at, dedupe_key, template_key, updated_at)
  SELECT id, kind, zalo_mode, conversation_id, customer_id, zalo_user_id, message_id, payload_json, status, zalo_msg_id, error, created_at, sent_at, dedupe_key, template_key, COALESCE(sent_at, created_at)
  FROM outbox;

DROP TABLE outbox;
ALTER TABLE outbox_v4 RENAME TO outbox;

CREATE INDEX idx_outbox_created ON outbox(created_at DESC);
CREATE UNIQUE INDEX idx_outbox_dedupe ON outbox(dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX idx_outbox_bridge ON outbox(channel, status, created_at);
CREATE INDEX idx_outbox_thread ON outbox(thread_id, created_at);
CREATE INDEX idx_outbox_zalo_msg ON outbox(zalo_msg_id) WHERE zalo_msg_id IS NOT NULL;

-- One row per bridge process (X-Bridge-Id), for GET /bridge/status.
CREATE TABLE bridge_status (
  bridge_id       TEXT PRIMARY KEY,
  last_seen_at    INTEGER NOT NULL,
  last_claim_at   INTEGER,
  last_item_at    INTEGER,
  last_result_at  INTEGER
);
