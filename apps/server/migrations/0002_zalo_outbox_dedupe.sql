-- server-zalo: idempotent Zalo sends.
-- outbox.dedupe_key: one outbox row per logical send (e.g. 'msg:<messages.id>' or 'job:<jobs.id>').
-- A repeated send with the same key returns the stored outcome and never calls Zalo again.
ALTER TABLE outbox ADD COLUMN dedupe_key TEXT;
ALTER TABLE outbox ADD COLUMN template_key TEXT;
CREATE UNIQUE INDEX idx_outbox_dedupe ON outbox(dedupe_key) WHERE dedupe_key IS NOT NULL;
