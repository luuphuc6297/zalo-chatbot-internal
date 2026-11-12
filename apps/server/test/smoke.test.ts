import { createExecutionContext, env, SELF, waitOnExecutionContext } from 'cloudflare:test';
import { app } from '../src/index';
import { describe, expect, it } from 'vitest';
import { computeSignature, verifySignature } from '../src/lib/zalo-signature';

describe('scaffold smoke', () => {
  it('serves /health', async () => {
    const res = await SELF.fetch('https://bot.test/health');
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, env: 'dev', zalo_mode: 'mock' });
  });

  it('applies migrations with default flags', async () => {
    const row = await env.DB.prepare("SELECT value_json FROM flags WHERE name = 'auto_reply_mode'").first<{ value_json: string }>();
    expect(JSON.parse(row!.value_json)).toBe('approve_each');
  });

  it('rejects runner calls without token and returns the error envelope', async () => {
    const noAuth = await SELF.fetch('https://bot.test/runner/jobs/claim', { method: 'POST', body: '{}' });
    expect(noAuth.status).toBe(401);
    const stub = await SELF.fetch('https://bot.test/runner/jobs/claim', {
      method: 'POST',
      body: '{}',
      headers: { authorization: 'Bearer test-runner-token', 'x-runner-id': 'mac-1' },
    });
    // no catalog seeded in this file: claim answers 409 invalid_state with the standard envelope
    expect(stub.status).toBe(409);
    expect(((await stub.json()) as { error: { code: string } }).error.code).toBe('invalid_state');
  });

  it('/dev/seed needs ENV=dev and the staff token; body overrides only on a local host', async () => {
    const auth = { authorization: 'Bearer test-staff-token' };
    const noAuth = await SELF.fetch('https://bot.test/dev/seed', { method: 'POST', body: '{}' });
    expect(noAuth.status).toBe(401);
    const wrongAuth = await SELF.fetch('https://bot.test/dev/seed', { method: 'POST', body: '{}', headers: { authorization: 'Bearer test-runner-token' } });
    expect(wrongAuth.status).toBe(401);
    // ENV other than dev (wrangler.toml default is prod): 404 even with the token
    const ctx = createExecutionContext();
    const prod = await app.fetch(new Request('https://bot.test/dev/seed', { method: 'POST', body: '{}', headers: auth }), { ...env, ENV: 'prod' }, ctx);
    await waitOnExecutionContext(ctx);
    expect(prod.status).toBe(404);
    // a non-local host cannot replace the prompt or the catalog
    const remote = await SELF.fetch('https://thomhouse-bot.example.workers.dev/dev/seed', {
      method: 'POST',
      body: JSON.stringify({ block_a: 'x'.repeat(200) }),
      headers: auth,
    });
    expect(remote.status).toBe(403);
    const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM prompt_assets WHERE key = 'block_a'").first<{ n: number }>();
    expect(row!.n).toBe(0);
  });

  it('signature round-trips (same formula as scripts/simulate_zalo.py)', async () => {
    const body = '{"app_id":"a","timestamp":"1"}';
    const sig = await computeSignature('a', body, '1', 's');
    expect(sig).toMatch(/^mac=[0-9a-f]{64}$/);
    expect(await verifySignature(sig, 'a', body, '1', 's')).toBe(true);
    expect(await verifySignature(sig.slice(4), 'a', body, '1', 's')).toBe(true);
    expect(await verifySignature(sig, 'a', body, '1', 'wrong')).toBe(false);
  });
});
