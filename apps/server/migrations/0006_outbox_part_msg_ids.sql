-- Personal Zalo channel: `zalo-agent msg send` splits a text above ~3000 UTF-8 bytes into parts, and each part comes
-- back as its own self-sent webhook event. The bridge reports every part's msgId (result field part_msg_ids); the
-- server keeps them here as a JSON array of strings so each part's echo is matched by id, not only by text.
ALTER TABLE outbox ADD COLUMN part_msg_ids TEXT;
