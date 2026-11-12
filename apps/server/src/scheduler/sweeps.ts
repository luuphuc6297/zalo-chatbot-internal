// Owner: server-zalo. inbox_sweep (re-dispatch events_inbox rows stuck in 'received' > 2 min),
// token_watch (refresh when the access token has < 2 h left; warn when the refresh token is > 80 days old),
// and a fallback for draft_reply lease expiry used only while server-core's expireLeases() is not implemented.
import type { Env } from '../types';
import { auditStatement } from '../lib/audit';
import { newId } from '../lib/ids';
import { REFRESH_TOKEN_WARN_AGE_MS, refreshIfNeeded, tokenStatus, type TokenDeps } from '../lib/zalo-token';
import { dispatchEvent, MAX_DISPATCH_ATTEMPTS } from '../zalo/dispatch';
import { dispatchPersonalEvent } from '../zalo/personal';

export const INBOX_SWEEP_AFTER_MS = 2 * 60 * 1000;

/** Re-dispatches signed events still 'received' 2 min after arrival. Returns how many were tried. */
export async function sweepInbox(env: Env, now: number): Promise<number> {
  const rows = await env.DB.prepare(
    `SELECT event_key FROM events_inbox
     WHERE status = 'received' AND signature_ok = 1 AND received_at < ? AND attempts < ?
     ORDER BY received_at ASC LIMIT 50`,
  )
    .bind(now - INBOX_SWEEP_AFTER_MS, MAX_DISPATCH_ATTEMPTS)
    .all<{ event_key: string }>();
  let n = 0;
  for (const { event_key } of rows.results ?? []) {
    if (event_key.startsWith('personal:')) await dispatchPersonalEvent(env, event_key, now);
    else await dispatchEvent(env, event_key, now);
    n++;
  }
  return n;
}

/**
 * Real mode only (mock mode has no tokens). Runs every cron tick; it is one SELECT unless a refresh is due.
 * The > 80-day warning is written to audit_log at most once per 24 h.
 */
export async function tokenWatch(env: Env, now: number, deps: TokenDeps = {}): Promise<void> {
  if (env.ZALO_MODE !== 'real') return;
  const before = await tokenStatus(env, now);
  if (before.auth_state === 'missing') return;
  if (before.auth_state === 'ok') await refreshIfNeeded(env, now, deps);
  const after = await tokenStatus(env, now);
  if (after.refresh_token_age_ms !== null && after.refresh_token_age_ms > REFRESH_TOKEN_WARN_AGE_MS) {
    const recent = await env.DB.prepare(
      "SELECT 1 AS x FROM audit_log WHERE action = 'zalo_token.refresh_token_old' AND at > ? LIMIT 1",
    )
      .bind(now - 24 * 3600 * 1000)
      .first<{ x: number }>();
    if (!recent) {
      await auditStatement(env, {
        actor_type: 'system',
        action: 'zalo_token.refresh_token_old',
        entity: 'oa_tokens',
        entity_id: '1',
        after: { age_days: Math.floor(after.refresh_token_age_ms / 86_400_000) },
      }, now).run();
      console.warn(JSON.stringify({ level: 'warn', at: 'zalo_token', result: 'refresh_token_old' }));
    }
  }
}

/**
 * Fallback for jobs/draft-jobs.ts expireLeases() (owned by server-core) while that is still a stub:
 * leased draft_reply jobs past lease_until -> 'failed' + handoff ai_unavailable (source runner_failure)
 * + conversation needs_attention = 1. Conditional UPDATE first, so a job is expired exactly once.
 */
export async function expireDraftLeasesFallback(env: Env, now: number): Promise<number> {
  const rows = await env.DB.prepare(
    "SELECT id, conversation_id FROM jobs WHERE type = 'draft_reply' AND status = 'leased' AND lease_until < ? LIMIT 50",
  )
    .bind(now)
    .all<{ id: string; conversation_id: string | null }>();
  let n = 0;
  for (const job of rows.results ?? []) {
    const upd = await env.DB.prepare(
      "UPDATE jobs SET status = 'failed', last_error = 'lease_expired', updated_at = ? WHERE id = ? AND status = 'leased' AND lease_until < ?",
    )
      .bind(now, job.id, now)
      .run();
    if ((upd.meta.changes ?? 0) === 0) continue;
    n++;
    if (!job.conversation_id) continue;
    const conv = await env.DB.prepare('SELECT customer_id FROM conversations WHERE id = ?').bind(job.conversation_id).first<{ customer_id: string }>();
    if (!conv) continue;
    await env.DB.batch([
      env.DB.prepare(
        `INSERT OR IGNORE INTO handoffs (id, conversation_id, customer_id, job_id, source, reason_code, urgency, summary_for_staff, status, idempotency_key, created_at)
         VALUES (?, ?, ?, ?, 'runner_failure', 'ai_unavailable', 'normal', ?, 'open', ?, ?)`,
      ).bind(
        newId('hof', now),
        job.conversation_id,
        conv.customer_id,
        job.id,
        'Máy chạy model không trả bản nháp trước khi hết hạn lease; nhân viên trả lời khách.',
        `lease_expired:${job.id}`,
        now,
      ),
      env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, job.conversation_id),
      auditStatement(env, { actor_type: 'system', actor_id: 'cron', action: 'job.lease_expired', entity: 'jobs', entity_id: job.id }, now),
    ]);
  }
  return n;
}
