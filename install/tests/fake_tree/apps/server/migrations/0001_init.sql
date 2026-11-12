-- Fake migration for the installer tests.
CREATE TABLE IF NOT EXISTS catalog_versions (id TEXT PRIMARY KEY, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL);
