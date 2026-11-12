// Owner: personal channel. Bridge API used by apps/zalo-bridge (docs/contracts.md "Personal Zalo channel").
//   POST /bridge/outbox/claim        Bearer RUNNER_TOKEN + X-Bridge-Id
//   POST /bridge/outbox/:id/result   Bearer RUNNER_TOKEN + X-Bridge-Id
//   GET  /bridge/status              Bearer RUNNER_TOKEN (bridge) or STAFF_TOKEN (console)
//   POST /staff/outbox/:id/decide    staff: requeue / mark_sent / mark_failed a failed or unknown personal row
import type { Context, MiddlewareHandler } from 'hono';
import type {
  AppEnv,
  BridgeClaimResponse,
  BridgeResultRequest,
  BridgeStatusResponse,
  OutboxDecisionRequest,
} from '../types';
import { HttpError, readJson } from '../lib/http';
import { safeEqual } from '../lib/auth';
import { readSendFlags } from '../lib/zalo-client';
import { applyResult, claimNext, decideOutbox, sendMaxPerHour } from './outbox';

type H = (c: Context<AppEnv>) => Promise<Response>;

const BRIDGE_ID_RE = /^[A-Za-z0-9._-]{1,64}$/;
const POLL_IDLE_MS = 2000;
const POLL_DISABLED_MS = 5000;

function bearer(header: string | undefined): string | null {
  if (!header) return null;
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  return m ? m[1]!.trim() : null;
}

async function touch(c: Context<AppEnv>, bridgeId: string, now: number, what: { claim?: boolean; item?: boolean; result?: boolean } = {}): Promise<void> {
  await c.env.DB.prepare(
    `INSERT INTO bridge_status (bridge_id, last_seen_at, last_claim_at, last_item_at, last_result_at) VALUES (?1, ?2, ?3, ?4, ?5)
     ON CONFLICT(bridge_id) DO UPDATE SET last_seen_at = ?2, last_claim_at = COALESCE(?3, last_claim_at),
       last_item_at = COALESCE(?4, last_item_at), last_result_at = COALESCE(?5, last_result_at)`,
  )
    .bind(bridgeId, now, what.claim ? now : null, what.item ? now : null, what.result ? now : null)
    .run();
}

/** Bearer RUNNER_TOKEN and X-Bridge-Id ([A-Za-z0-9._-]{1,64}). Every authenticated call updates last_seen_at. */
export const requireBridge: MiddlewareHandler<AppEnv> = async (c, next) => {
  const token = bearer(c.req.header('authorization'));
  if (!token || !c.env.RUNNER_TOKEN || !safeEqual(token, c.env.RUNNER_TOKEN)) {
    throw new HttpError(401, 'unauthorized', 'invalid bridge token');
  }
  const bridgeId = c.req.header('x-bridge-id') ?? '';
  if (!BRIDGE_ID_RE.test(bridgeId)) throw new HttpError(400, 'bad_request', 'X-Bridge-Id header required ([A-Za-z0-9._-]{1,64})');
  c.set('bridgeId', bridgeId);
  await touch(c, bridgeId, Date.now());
  await next();
};

/** GET /bridge/status: the bridge (RUNNER_TOKEN) or the console (STAFF_TOKEN). */
export const requireBridgeOrStaff: MiddlewareHandler<AppEnv> = async (c, next) => {
  const token = bearer(c.req.header('authorization'));
  const ok = !!token && ((!!c.env.RUNNER_TOKEN && safeEqual(token, c.env.RUNNER_TOKEN)) || (!!c.env.STAFF_TOKEN && safeEqual(token, c.env.STAFF_TOKEN)));
  if (!ok) throw new HttpError(401, 'unauthorized', 'invalid token');
  await next();
};

export const claim: H = async (c) => {
  const now = Date.now();
  const bridgeId = c.get('bridgeId')!;
  // Optional body {"capabilities": ["images"]}: only such a bridge is handed menu image rows (kind 'cs_images').
  const req = await readJson<{ capabilities?: unknown }>(c).catch(() => null);
  const images = !!req && Array.isArray(req.capabilities) && req.capabilities.includes('images');
  const flags = await readSendFlags(c.env);
  if (!flags.outbound_enabled) {
    await touch(c, bridgeId, now, { claim: true });
    const body: BridgeClaimResponse = { item: null, poll_after_ms: POLL_DISABLED_MS, reason: 'outbound_disabled' };
    return c.json(body);
  }
  const { item, rate_limited_until } = await claimNext(c.env, bridgeId, now, { images });
  await touch(c, bridgeId, now, { claim: true, item: !!item });
  let body: BridgeClaimResponse;
  if (item) body = { item, poll_after_ms: 0 };
  else if (rate_limited_until) {
    // Hourly send limit reached: wait until a slot frees up (at least 5 s, at most 60 s between polls).
    body = { item: null, poll_after_ms: Math.min(Math.max(rate_limited_until - now, POLL_DISABLED_MS), 60_000), reason: 'rate_limited' };
  } else body = { item: null, poll_after_ms: POLL_IDLE_MS, reason: 'no_work' };
  return c.json(body);
};

export const result: H = async (c) => {
  const now = Date.now();
  const bridgeId = c.get('bridgeId')!;
  const id = c.req.param('id') ?? '';
  if (!/^obx_[0-9a-f]{28}$/.test(id)) throw new HttpError(400, 'bad_request', 'malformed outbox id');
  const body = await readJson<Partial<BridgeResultRequest>>(c);
  if (!body || typeof body !== 'object') throw new HttpError(400, 'bad_request', 'body must be a JSON object');
  if (body.status !== 'sent' && body.status !== 'failed' && body.status !== 'unknown') {
    throw new HttpError(422, 'validation_failed', "status must be 'sent', 'failed' or 'unknown'", { field: 'status' });
  }
  if (body.zalo_msg_id !== undefined && body.zalo_msg_id !== null && (typeof body.zalo_msg_id !== 'string' || !/^[A-Za-z0-9_.:-]{1,64}$/.test(body.zalo_msg_id))) {
    throw new HttpError(422, 'validation_failed', 'zalo_msg_id must be a short id string', { field: 'zalo_msg_id' });
  }
  if (body.error !== undefined && body.error !== null && typeof body.error !== 'string') {
    throw new HttpError(422, 'validation_failed', 'error must be a string', { field: 'error' });
  }
  if (body.attempt !== undefined && body.attempt !== null && (!Number.isInteger(body.attempt) || body.attempt < 1)) {
    throw new HttpError(422, 'validation_failed', 'attempt must be a positive integer', { field: 'attempt' });
  }
  if (
    body.part_msg_ids !== undefined &&
    body.part_msg_ids !== null &&
    (!Array.isArray(body.part_msg_ids) || body.part_msg_ids.length > 50 || !body.part_msg_ids.every((x) => typeof x === 'string' && /^[A-Za-z0-9_.:-]{1,64}$/.test(x)))
  ) {
    throw new HttpError(422, 'validation_failed', 'part_msg_ids must be at most 50 short id strings', { field: 'part_msg_ids' });
  }
  const req: BridgeResultRequest = {
    status: body.status,
    ...(Array.isArray(body.part_msg_ids) && body.part_msg_ids.length ? { part_msg_ids: body.part_msg_ids } : {}),
    ...(body.zalo_msg_id ? { zalo_msg_id: body.zalo_msg_id } : {}),
    ...(body.error ? { error: body.error } : {}),
    ...(typeof body.attempt === 'number' ? { attempt: body.attempt } : {}),
  };
  const out = await applyResult(c.env, id, bridgeId, req, now);
  await touch(c, bridgeId, now, { result: true });
  return c.json(out);
};

export const status: H = async (c) => {
  const db = c.env.DB;
  const flags = await readSendFlags(c.env);
  const [bridges, counts, oldest, recent] = await Promise.all([
    db.prepare('SELECT bridge_id, last_seen_at, last_claim_at, last_item_at, last_result_at FROM bridge_status ORDER BY last_seen_at DESC LIMIT 20').all<{
      bridge_id: string;
      last_seen_at: number;
      last_claim_at: number | null;
      last_item_at: number | null;
      last_result_at: number | null;
    }>(),
    db.prepare("SELECT status, COUNT(*) AS n FROM outbox WHERE channel = 'personal' GROUP BY status").all<{ status: string; n: number }>(),
    db.prepare("SELECT MIN(created_at) AS t FROM outbox WHERE channel = 'personal' AND status = 'queued'").first<{ t: number | null }>(),
    db.prepare("SELECT COUNT(*) AS n FROM outbox WHERE channel = 'personal' AND last_claimed_at >= ?").bind(Date.now() - 3600_000).first<{ n: number }>(),
  ]);
  const byStatus: BridgeStatusResponse['counts'] = { queued: 0, leased: 0, sent: 0, failed: 0, unknown: 0 };
  for (const r of counts.results ?? []) if (r.status in byStatus) byStatus[r.status as keyof typeof byStatus] = r.n;
  const rows = bridges.results ?? [];
  const maxOf = (k: 'last_claim_at' | 'last_result_at') => rows.reduce<number | null>((m, r) => (r[k] !== null && (m === null || r[k]! > m) ? r[k] : m), null);
  const body: BridgeStatusResponse = {
    zalo_mode: c.env.ZALO_MODE,
    outbound_enabled: flags.outbound_enabled,
    last_claim_at: maxOf('last_claim_at'),
    last_result_at: maxOf('last_result_at'),
    bridges: rows,
    counts: byStatus,
    oldest_queued_at: oldest?.t ?? null,
    claims_last_hour: recent?.n ?? 0,
    send_max_per_hour: sendMaxPerHour(c.env),
  };
  return c.json(body);
};

/** POST /staff/outbox/:id/decide (staff auth from /staff/*). */
export const decide: H = async (c) => {
  const id = c.req.param('id') ?? '';
  const body = await readJson<Partial<OutboxDecisionRequest>>(c);
  if (!body || (body.action !== 'requeue' && body.action !== 'mark_sent' && body.action !== 'mark_failed')) {
    throw new HttpError(422, 'validation_failed', "action must be 'requeue', 'mark_sent' or 'mark_failed'", { field: 'action' });
  }
  const note = typeof body.note === 'string' ? body.note.slice(0, 200) : null;
  return c.json(await decideOutbox(c.env, id, c.get('staffId') ?? 'staff', body.action, note, Date.now()));
};
