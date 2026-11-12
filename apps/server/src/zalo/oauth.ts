// OA authorization (Zalo OA OAuth v4 with PKCE), research/snapshots/zalo-2026-11-07/zaloplatforms-OA-llms-full.txt:196-360.
// GET /zalo/oauth/start?key=<STAFF_TOKEN>  -> stores a PKCE verifier, redirects the OA admin to Zalo's permission page.
// GET /zalo/oauth/callback?code=&oa_id=&state= -> exchanges the code for the token pair and stores it (oa_tokens row 1).
// The callback URL must be registered on developers.zalo.me as <public origin>/zalo/oauth/callback.
// Token values are never returned or logged.
import type { Context } from 'hono';
import type { AppEnv } from '../types';
import { HttpError } from '../lib/http';
import { safeEqual } from '../lib/auth';
import { storeTokenPair, tokenStatus } from '../lib/zalo-token';

export const PERMISSION_URL = 'https://oauth.zaloapp.com/v4/oa/permission';
export const TOKEN_URL = 'https://oauth.zaloapp.com/v4/oa/access_token';
const STATE_TTL_MS = 15 * 60 * 1000;
const VERIFIER_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';

function randomString(len: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(len));
  let out = '';
  for (const b of bytes) out += VERIFIER_CHARS[b % VERIFIER_CHARS.length];
  return out;
}

/** Zalo: 43 chars with upper, lower and digits. Retries until all three classes are present. */
export function makeVerifier(): string {
  for (;;) {
    const v = randomString(43);
    if (/[A-Z]/.test(v) && /[a-z]/.test(v) && /[0-9]/.test(v)) return v;
  }
}

/** code_challenge = Base64(SHA-256(ASCII(verifier))) without padding. URL-safe alphabet (PKCE S256). */
export async function challengeFor(verifier: string): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  let bin = '';
  for (const b of digest) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function callbackUrl(c: Context<AppEnv>): string {
  const u = new URL(c.req.url);
  return `${u.origin}/zalo/oauth/callback`;
}

function page(title: string, body: string, status = 200): Response {
  const esc = (s: string) => s.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>${esc(title)}</title><body style="font-family:system-ui;max-width:40rem;margin:3rem auto"><h1>${esc(title)}</h1><p>${esc(body)}</p></body>`,
    { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } },
  );
}

export async function oauthStart(c: Context<AppEnv>): Promise<Response> {
  const env = c.env;
  const key = c.req.query('key') ?? '';
  if (!env.STAFF_TOKEN || !safeEqual(key, env.STAFF_TOKEN)) throw new HttpError(401, 'unauthorized', 'staff key required');
  if (!env.ZALO_APP_ID || env.ZALO_APP_ID.startsWith('dev-')) throw new HttpError(409, 'conflict', 'ZALO_APP_ID is not configured');
  const now = Date.now();
  const state = randomString(24);
  const verifier = makeVerifier();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM oauth_pending WHERE created_at < ?').bind(now - STATE_TTL_MS),
    env.DB.prepare('INSERT INTO oauth_pending (state, code_verifier, created_at) VALUES (?, ?, ?)').bind(state, verifier, now),
  ]);
  const url = new URL(PERMISSION_URL);
  url.searchParams.set('app_id', env.ZALO_APP_ID);
  url.searchParams.set('redirect_uri', callbackUrl(c));
  url.searchParams.set('code_challenge', await challengeFor(verifier));
  url.searchParams.set('state', state);
  return c.redirect(url.toString(), 302);
}

export async function oauthCallback(c: Context<AppEnv>, fetchImpl: typeof fetch = fetch): Promise<Response> {
  const env = c.env;
  const code = c.req.query('code') ?? '';
  const state = c.req.query('state') ?? '';
  const oaId = c.req.query('oa_id') ?? '';
  if (!code || !state) return page('Thiếu mã cấp quyền', 'Zalo không trả về code hoặc state. Mở lại đường dẫn cấp quyền từ đầu.', 400);
  const row = await env.DB.prepare('SELECT code_verifier, created_at FROM oauth_pending WHERE state = ?')
    .bind(state).first<{ code_verifier: string; created_at: number }>();
  await env.DB.prepare('DELETE FROM oauth_pending WHERE state = ?').bind(state).run();
  if (!row || row.created_at < Date.now() - STATE_TTL_MS) {
    return page('Phiên cấp quyền đã hết hạn', 'Mở lại đường dẫn cấp quyền từ đầu (hiệu lực 15 phút).', 400);
  }
  if (env.ZALO_OA_ID && !env.ZALO_OA_ID.startsWith('dev-') && oaId && oaId !== env.ZALO_OA_ID) {
    return page('Sai OA', 'Tài khoản OA vừa cấp quyền khác với ZALO_OA_ID đã cấu hình.', 400);
  }
  const body = new URLSearchParams({ code, app_id: env.ZALO_APP_ID, grant_type: 'authorization_code', code_verifier: row.code_verifier });
  let json: Record<string, unknown> = {};
  try {
    const res = await fetchImpl(TOKEN_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded', secret_key: env.ZALO_APP_SECRET_KEY },
      body,
    });
    json = (await res.json()) as Record<string, unknown>;
  } catch {
    return page('Không gọi được Zalo', 'Lỗi mạng khi đổi mã lấy token. Thử lại.', 502);
  }
  const access = typeof json.access_token === 'string' ? json.access_token : '';
  const refresh = typeof json.refresh_token === 'string' ? json.refresh_token : '';
  const expires = Number(json.expires_in ?? 90000);
  if (!access || !refresh) {
    const reason = String(json.error_name ?? json.error_description ?? json.message ?? json.error ?? 'không rõ');
    return page('Zalo từ chối cấp token', `Lý do Zalo trả về: ${reason}`, 502);
  }
  await storeTokenPair(env, access, refresh, Number.isFinite(expires) && expires > 0 ? expires : 90000);
  return page('Đã kết nối OA', 'Server đã lưu token của OA. Có thể đóng trang này.');
}

export async function oauthStatus(c: Context<AppEnv>): Promise<Response> {
  return c.json(await tokenStatus(c.env));
}
