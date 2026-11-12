// Owner: server-core. Bearer-token middlewares for the runner and staff APIs.
import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from '../types';
import { HttpError } from './http';

/** Constant-time string comparison (length leak only). */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function bearer(header: string | undefined): string | null {
  if (!header) return null;
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  return m ? m[1]!.trim() : null;
}

const RUNNER_ID_RE = /^[A-Za-z0-9._-]{1,64}$/;

export const requireRunner: MiddlewareHandler<AppEnv> = async (c, next) => {
  const token = bearer(c.req.header('authorization'));
  if (!token || !c.env.RUNNER_TOKEN || !safeEqual(token, c.env.RUNNER_TOKEN)) {
    throw new HttpError(401, 'unauthorized', 'invalid runner token');
  }
  const runnerId = c.req.header('x-runner-id') ?? '';
  if (!RUNNER_ID_RE.test(runnerId)) {
    throw new HttpError(400, 'bad_request', 'X-Runner-Id header required ([A-Za-z0-9._-]{1,64})');
  }
  c.set('runnerId', runnerId);
  // Every authenticated runner call counts as a sign of life (GET /staff/runner, sweepRunnerHealth).
  await c.env.DB.prepare(
    'INSERT INTO runner_status (runner_id, last_seen_at) VALUES (?, ?) ON CONFLICT(runner_id) DO UPDATE SET last_seen_at = excluded.last_seen_at',
  )
    .bind(runnerId, Date.now())
    .run();
  await next();
};

export const requireStaff: MiddlewareHandler<AppEnv> = async (c, next) => {
  const token = bearer(c.req.header('authorization'));
  if (!token || !c.env.STAFF_TOKEN || !safeEqual(token, c.env.STAFF_TOKEN)) {
    throw new HttpError(401, 'unauthorized', 'invalid staff token');
  }
  const staffId = (c.req.header('x-staff-id') ?? 'staff').slice(0, 64);
  c.set('staffId', staffId);
  await next();
};

/** Hostnames treated as local development (wrangler dev, tests). */
export function isLocalHost(url: string): boolean {
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return false;
  }
  return host === 'localhost' || host === '127.0.0.1' || host === '[::1]' || host.endsWith('.localhost') || host.endsWith('.test');
}

/** /dev/* needs ENV=dev (set only in .dev.vars; wrangler.toml defaults to prod) AND the staff bearer token. */
export const requireDev: MiddlewareHandler<AppEnv> = async (c, next) => {
  if (c.env.ENV !== 'dev') throw new HttpError(404, 'dev_only', 'dev endpoints are disabled');
  const token = bearer(c.req.header('authorization'));
  if (!token || !c.env.STAFF_TOKEN || !safeEqual(token, c.env.STAFF_TOKEN)) {
    throw new HttpError(401, 'unauthorized', 'dev endpoints need the staff token');
  }
  await next();
};
