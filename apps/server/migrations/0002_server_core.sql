-- server-core (phase 2): ordering and accounting columns. Additive only.

-- Per-conversation message sequence, assigned by the Conversation DO at insert (rowid is not stable across VACUUM).
ALTER TABLE messages ADD COLUMN seq INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_messages_conv_seq ON messages(conversation_id, seq);

-- answered_seq: last customer message seq covered by an accepted draft or a staff/bot send.
-- consent_seq: seq of the message that granted ai_assistant consent; the model never sees messages at or before it.
ALTER TABLE conversations ADD COLUMN answered_seq INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN consent_seq INTEGER NOT NULL DEFAULT 0;

-- Running totals of model usage for this conversation (subscription accounting, cost is API-equivalent USD).
ALTER TABLE conversations ADD COLUMN total_input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN total_output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN total_cache_read_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN total_cache_write_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN total_cost_usd_equiv REAL NOT NULL DEFAULT 0;

-- Last runner failure, shown to staff in GET /staff/runner.
ALTER TABLE runner_status ADD COLUMN last_error_kind TEXT;
ALTER TABLE runner_status ADD COLUMN last_error_at INTEGER;
ALTER TABLE runner_status ADD COLUMN last_error_account TEXT;

CREATE INDEX idx_jobs_customer ON jobs(customer_id, type, status);
CREATE INDEX idx_booking_conv ON booking_requests(conversation_id, created_at);
CREATE INDEX idx_handoffs_conv ON handoffs(conversation_id, status);
