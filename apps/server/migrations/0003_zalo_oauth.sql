-- PKCE state for the OA authorization flow (GET /zalo/oauth/start -> Zalo -> GET /zalo/oauth/callback).
CREATE TABLE IF NOT EXISTS oauth_pending (
  state TEXT PRIMARY KEY,
  code_verifier TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
