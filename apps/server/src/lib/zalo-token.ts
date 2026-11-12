// Owner: server-zalo. Single holder of the OA refresh token (table oa_tokens, one row id = 1).
// Refresh is serialized by a conditional UPDATE on refresh_lock_until (no second Durable Object class in MVP).
// Refresh token is single-use (snapshot zaloplatforms-OA-llms-full.txt:184-187): the new access+refresh pair is
// written in ONE statement, guarded by the refresh token we used, before anything else happens.
// Tokens are never logged, never returned by any API, never written to audit_log.
//
// Endpoint (snapshot :339-353): POST https://oauth.zaloapp.com/v4/oa/access_token,
//   header secret_key = ZALO_APP_SECRET_KEY, form body refresh_token, app_id, grant_type=refresh_token.
//   Response { access_token, refresh_token, expires_in: "90000" } (seconds; access token lives 25 h).
// UNTESTED against a real OA. The initial pair comes from the OAuth v4 PKCE flow, which is not built yet:
// insert it with storeTokenPair() (or `wrangler d1 execute`) after authorizing the app by hand.
import type { Env } from '../types';
import { auditStatement } from './audit';
import { HttpError } from './http';

export const OAUTH_URL = 'https://oauth.zaloapp.com/v4/oa/access_token';
export const REFRESH_BEFORE_MS = 2 * 3600 * 1000; // refresh when the access token has < 2 h left
export const REFRESH_TOKEN_WARN_AGE_MS = 80 * 24 * 3600 * 1000; // refresh token lives ~3 months
const LOCK_MS = 30_000;
const HTTP_TIMEOUT_MS = 10_000;

export type RefreshResult = 'ok' | 'refreshed' | 'reauth_required' | 'missing' | 'locked' | 'error';

export interface TokenDeps {
  fetch?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
}

interface TokenRow {
  access_token: string | null;
  refresh_token: string | null;
  access_expires_at: number | null;
  refresh_issued_at: number | null;
  auth_state: 'ok' | 'reauth_required' | 'missing';
  refresh_lock_until: number | null;
}

async function readRow(env: Env): Promise<TokenRow | null> {
  return env.DB.prepare(
    'SELECT access_token, refresh_token, access_expires_at, refresh_issued_at, auth_state, refresh_lock_until FROM oa_tokens WHERE id = 1',
  ).first<TokenRow>();
}

/** Stores a fresh pair (first authorization or manual re-auth). Overwrites whatever is there. */
export async function storeTokenPair(env: Env, accessToken: string, refreshToken: string, expiresInSec: number, now: number = Date.now()): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO oa_tokens (id, access_token, refresh_token, access_expires_at, refresh_issued_at, auth_state, refresh_lock_until, updated_at)
       VALUES (1, ?, ?, ?, ?, 'ok', NULL, ?)
       ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token, refresh_token = excluded.refresh_token,
         access_expires_at = excluded.access_expires_at, refresh_issued_at = excluded.refresh_issued_at,
         auth_state = 'ok', refresh_lock_until = NULL, updated_at = excluded.updated_at`,
    ).bind(accessToken, refreshToken, now + expiresInSec * 1000, now, now),
    auditStatement(env, { actor_type: 'system', action: 'zalo_token.stored', entity: 'oa_tokens', entity_id: '1', after: { auth_state: 'ok' } }, now),
  ]);
}

/** Token status for staff/health views. Never includes token values. */
export async function tokenStatus(env: Env, now: number = Date.now()) {
  const row = await readRow(env);
  if (!row) return { auth_state: 'missing' as const, access_expires_in_ms: null, refresh_token_age_ms: null };
  return {
    auth_state: row.auth_state,
    access_expires_in_ms: row.access_expires_at === null ? null : row.access_expires_at - now,
    refresh_token_age_ms: row.refresh_issued_at === null ? null : now - row.refresh_issued_at,
  };
}

/** Access token for an API call. Refreshes first when < 2 h left. Throws when no usable token exists. */
export async function getAccessToken(env: Env, now: number = Date.now(), deps: TokenDeps = {}): Promise<string> {
  let row = await readRow(env);
  if (row?.auth_state === 'ok' && row.access_token && (row.access_expires_at ?? 0) - now > REFRESH_BEFORE_MS) {
    return row.access_token;
  }
  const r = await refreshIfNeeded(env, now, deps);
  row = await readRow(env);
  if (row?.auth_state === 'ok' && row.access_token && (row.access_expires_at ?? 0) > now) return row.access_token;
  throw new HttpError(503, 'internal', `zalo access token unavailable (${r})`);
}

/**
 * true only when Zalo says the refresh token itself is invalid / expired / revoked. The snapshot of the Zalo docs
 * (research/snapshots/zalo-2026-11-07) lists no numeric error codes for the refresh endpoint, so this matches the
 * error name / description wording. Anything else (rate limit, temporary JSON error) is retried by cron.
 */
export function isRefreshTokenInvalid(json: Record<string, unknown>): boolean {
  const words = [json.error_name, json.error_description, json.message, json.error_reason].filter((x) => typeof x === 'string').join(' ');
  if (/invalid_grant/i.test(words)) return true;
  return /refresh[_ ]?token/i.test(words) && /invalid|expired|revoked|not[_ ]?exist|already[_ ]?used/i.test(words);
}

async function callRefresh(env: Env, refreshToken: string, f: typeof fetch): Promise<
  | { kind: 'ok'; access_token: string; refresh_token: string; expires_in: number }
  | { kind: 'rejected'; code: string }
  | { kind: 'transient'; code: string }
  | { kind: 'network'; reason: string }
> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await f(OAUTH_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded', secret_key: env.ZALO_APP_SECRET_KEY },
      body: new URLSearchParams({ refresh_token: refreshToken, app_id: env.ZALO_APP_ID, grant_type: 'refresh_token' }).toString(),
      signal: ctrl.signal,
    });
    if (res.status >= 500 || res.status === 429 || res.status === 408) return { kind: 'network', reason: `http_${res.status}` };
    let json: Record<string, unknown>;
    try {
      json = (await res.json()) as Record<string, unknown>;
    } catch {
      return { kind: 'network', reason: 'bad_json' };
    }
    const at = json.access_token;
    const rt = json.refresh_token;
    if (typeof at === 'string' && at && typeof rt === 'string' && rt) {
      const exp = Number(json.expires_in ?? json.expire_in ?? 90000);
      return { kind: 'ok', access_token: at, refresh_token: rt, expires_in: Number.isFinite(exp) && exp > 0 ? exp : 90000 };
    }
    const code = String(json.error ?? json.error_name ?? `http_${res.status}`).slice(0, 40);
    return isRefreshTokenInvalid(json) ? { kind: 'rejected', code } : { kind: 'transient', code };
  } catch (err) {
    return { kind: 'network', reason: err instanceof Error && err.name === 'AbortError' ? 'timeout' : 'network_error' };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Refreshes the access token when it has < 2 h left (or when force is set, e.g. after a Zalo token error).
 * Single writer: only the caller whose conditional UPDATE took refresh_lock_until may call Zalo.
 *  - success: new pair stored in one UPDATE guarded by the old refresh token -> 'refreshed'
 *  - Zalo says the refresh token is invalid (isRefreshTokenInvalid): auth_state = 'reauth_required' (all real
 *    sends stop) -> 'reauth_required'. Other Zalo errors and HTTP 429 -> 'error', lock released, cron retries.
 *  - timeout / network: the old refresh token may or may not be spent. Retry once with the same token
 *    (research/06); if Zalo then rejects it -> 'reauth_required'; if the network fails again -> 'error'.
 */
export async function refreshIfNeeded(
  env: Env,
  now: number = Date.now(),
  deps: TokenDeps & { force?: boolean } = {},
): Promise<RefreshResult> {
  const f = deps.fetch ?? fetch;
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const row = await readRow(env);
  if (!row || !row.refresh_token) return 'missing';
  if (row.auth_state === 'reauth_required') return 'reauth_required';
  if (!deps.force && row.access_token && (row.access_expires_at ?? 0) - now > REFRESH_BEFORE_MS) return 'ok';

  const oldRefresh = row.refresh_token;
  const lock = await env.DB.prepare(
    `UPDATE oa_tokens SET refresh_lock_until = ?, updated_at = ?
     WHERE id = 1 AND refresh_token = ? AND (refresh_lock_until IS NULL OR refresh_lock_until < ?)`,
  )
    .bind(now + LOCK_MS, now, oldRefresh, now)
    .run();
  if ((lock.meta.changes ?? 0) === 0) {
    // Someone else is refreshing (or just did). Wait briefly for their result; never call Zalo ourselves.
    for (let i = 0; i < 6; i++) {
      await sleep(500);
      const cur = await readRow(env);
      if (!cur) return 'missing';
      if (cur.auth_state === 'reauth_required') return 'reauth_required';
      if (cur.refresh_token !== oldRefresh) return 'refreshed';
    }
    return 'locked';
  }

  let attempt = await callRefresh(env, oldRefresh, f);
  if (attempt.kind === 'network') attempt = await callRefresh(env, oldRefresh, f);

  if (attempt.kind === 'ok') {
    const upd = await env.DB.prepare(
      `UPDATE oa_tokens SET access_token = ?, refresh_token = ?, access_expires_at = ?, refresh_issued_at = ?,
         auth_state = 'ok', refresh_lock_until = NULL, updated_at = ?
       WHERE id = 1 AND refresh_token = ?`,
    )
      .bind(attempt.access_token, attempt.refresh_token, now + attempt.expires_in * 1000, now, now, oldRefresh)
      .run();
    if ((upd.meta.changes ?? 0) === 0) {
      // Cannot happen while we hold the lock unless the lock expired mid-call; the pair Zalo gave us is the
      // only valid one now, so store it anyway rather than lose it.
      await env.DB.prepare(
        `UPDATE oa_tokens SET access_token = ?, refresh_token = ?, access_expires_at = ?, refresh_issued_at = ?,
           auth_state = 'ok', refresh_lock_until = NULL, updated_at = ? WHERE id = 1`,
      )
        .bind(attempt.access_token, attempt.refresh_token, now + attempt.expires_in * 1000, now, now)
        .run();
    }
    await auditStatement(env, { actor_type: 'system', action: 'zalo_token.refreshed', entity: 'oa_tokens', entity_id: '1' }, now).run();
    console.log(JSON.stringify({ level: 'info', at: 'zalo_token', result: 'refreshed' }));
    return 'refreshed';
  }

  if (attempt.kind === 'rejected') {
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE oa_tokens SET auth_state = 'reauth_required', refresh_lock_until = NULL, updated_at = ? WHERE id = 1 AND refresh_token = ?",
      ).bind(now, oldRefresh),
      auditStatement(env, { actor_type: 'system', action: 'zalo_token.reauth_required', entity: 'oa_tokens', entity_id: '1', after: { zalo_error: attempt.code } }, now),
    ]);
    console.error(JSON.stringify({ level: 'error', at: 'zalo_token', result: 'reauth_required', zalo_error: attempt.code }));
    return 'reauth_required';
  }

  // network failure, rate limit or a temporary Zalo error: release the lock; the next cron run retries.
  await env.DB.prepare('UPDATE oa_tokens SET refresh_lock_until = NULL, updated_at = ? WHERE id = 1 AND refresh_token = ?')
    .bind(now, oldRefresh)
    .run();
  const reason = attempt.kind === 'network' ? attempt.reason : `zalo_${attempt.code}`;
  console.error(JSON.stringify({ level: 'error', at: 'zalo_token', result: 'error', reason }));
  return 'error';
}
