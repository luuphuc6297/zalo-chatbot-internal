import { env, SELF } from 'cloudflare:test';
import { describe, expect, it } from 'vitest';
import { challengeFor, makeVerifier, oauthCallback } from '../src/zalo/oauth';

describe('zalo oauth', () => {
  it('computes the PKCE S256 challenge (RFC 7636 appendix B vector)', async () => {
    expect(await challengeFor('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk')).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
  });

  it('makes 43-char verifiers with upper, lower and digits', () => {
    const v = makeVerifier();
    expect(v).toHaveLength(43);
    expect(/[A-Z]/.test(v) && /[a-z]/.test(v) && /[0-9]/.test(v)).toBe(true);
  });

  it('start requires the staff key and redirects to Zalo with a stored state', async () => {
    expect((await SELF.fetch('https://bot.test/zalo/oauth/start?key=wrong', { redirect: 'manual' })).status).toBe(401);
    const res = await SELF.fetch('https://bot.test/zalo/oauth/start?key=test-staff-token', { redirect: 'manual' });
    expect(res.status).toBe(302);
    const loc = new URL(res.headers.get('location')!);
    expect(loc.origin + loc.pathname).toBe('https://oauth.zaloapp.com/v4/oa/permission');
    expect(loc.searchParams.get('app_id')).toBe('test-app-id');
    expect(loc.searchParams.get('redirect_uri')).toBe('https://bot.test/zalo/oauth/callback');
    const state = loc.searchParams.get('state')!;
    const row = await env.DB.prepare('SELECT code_verifier FROM oauth_pending WHERE state = ?').bind(state).first<{ code_verifier: string }>();
    expect(loc.searchParams.get('code_challenge')).toBe(await challengeFor(row!.code_verifier));
  });

  it('callback exchanges the code with the verifier and stores the token pair', async () => {
    const start = await SELF.fetch('https://bot.test/zalo/oauth/start?key=test-staff-token', { redirect: 'manual' });
    const state = new URL(start.headers.get('location')!).searchParams.get('state')!;
    const { code_verifier } = (await env.DB.prepare('SELECT code_verifier FROM oauth_pending WHERE state = ?').bind(state).first<{ code_verifier: string }>())!;
    let sent: { url: string; headers: Headers; body: URLSearchParams } | null = null;
    const fakeFetch = (async (url: string, init: RequestInit) => {
      sent = { url, headers: new Headers(init.headers), body: new URLSearchParams(String(init.body)) };
      return new Response(JSON.stringify({ access_token: 'AT', refresh_token: 'RT', expires_in: '90000' }));
    }) as unknown as typeof fetch;
    const c = {
      env,
      req: { query: (k: string) => ({ code: 'CODE1', state, oa_id: '' } as Record<string, string>)[k] },
    } as never;
    const res = await oauthCallback(c, fakeFetch);
    expect(res.status).toBe(200);
    expect(sent!.url).toBe('https://oauth.zaloapp.com/v4/oa/access_token');
    expect(sent!.body.get('code')).toBe('CODE1');
    expect(sent!.body.get('code_verifier')).toBe(code_verifier);
    expect(sent!.body.get('grant_type')).toBe('authorization_code');
    const tok = await env.DB.prepare('SELECT access_token, refresh_token, auth_state FROM oa_tokens WHERE id = 1').first<Record<string, string>>();
    expect(tok).toMatchObject({ access_token: 'AT', refresh_token: 'RT', auth_state: 'ok' });
    // state is single-use
    const again = await oauthCallback(c, fakeFetch);
    expect(again.status).toBe(400);
  });
});

describe('staff catalog load', () => {
  it('loads the embedded catalog with the staff token and rejects without it', async () => {
    expect((await SELF.fetch('https://bot.example.com/staff/catalog/load-embedded', { method: 'POST' })).status).toBe(401);
    const res = await SELF.fetch('https://bot.example.com/staff/catalog/load-embedded', {
      method: 'POST', headers: { authorization: 'Bearer test-staff-token', 'x-staff-id': 't' },
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { services: number };
    expect(body.services).toBe(23);
  });
});
