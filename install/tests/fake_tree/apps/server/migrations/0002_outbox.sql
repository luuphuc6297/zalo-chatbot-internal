-- Fake migration for the installer tests.
CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, status TEXT NOT NULL);
