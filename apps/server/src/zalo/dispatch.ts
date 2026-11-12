// Owner: server-zalo. Hand a stored event to its Conversation DO and update events_inbox.status.
// Used by the webhook (waitUntil) and by the inbox_sweep cron (events still 'received' after 2 min).
//
// Status rules:
//   processed  the DO accepted the event (ingestEvent returned)
//   ignored    event kind not used in the MVP, no customer id, or another OA's event
//   received   the DO call threw: kept for inbox_sweep, attempts += 1, error stored (no message text)
//   failed     MAX_DISPATCH_ATTEMPTS reached; staff sees it in events_inbox
// Events with signature_ok = 0 are never dispatched (observe mode stores them for inspection only).
import type { Env, IngestResult, ZaloWebhookEvent } from '../types';
import { conversationObjectName } from '../types';
import { normalizeEvent } from './parse';

export const MAX_DISPATCH_ATTEMPTS = 5;

interface InboxRow {
  event_key: string;
  raw_body: string;
  signature_ok: number;
  status: string;
  attempts: number;
  received_at: number;
}

export type DispatchOutcome = 'processed' | 'ignored' | 'retry' | 'failed' | 'skipped';

function shortError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.slice(0, 300);
}

export async function dispatchEvent(env: Env, eventKey: string, now: number = Date.now()): Promise<DispatchOutcome> {
  const row = await env.DB.prepare(
    'SELECT event_key, raw_body, signature_ok, status, attempts, received_at FROM events_inbox WHERE event_key = ?',
  )
    .bind(eventKey)
    .first<InboxRow>();
  if (!row || row.status !== 'received' || row.signature_ok !== 1) return 'skipped';
  // Personal-channel events have their own parser and dispatcher (src/zalo/personal.ts dispatchPersonalEvent).
  if (eventKey.startsWith('personal:')) return 'skipped';

  const setStatus = (status: string, error: string | null, bumpAttempt: boolean) =>
    env.DB.prepare(
      `UPDATE events_inbox SET status = ?, error = ?, attempts = attempts + ?, processed_at = CASE WHEN ? IN ('processed','ignored','failed') THEN ? ELSE processed_at END
       WHERE event_key = ? AND status = 'received'`,
    )
      .bind(status, error, bumpAttempt ? 1 : 0, status, now, eventKey)
      .run();

  let raw: ZaloWebhookEvent;
  try {
    raw = JSON.parse(row.raw_body) as ZaloWebhookEvent;
  } catch {
    await setStatus('failed', 'raw_body is not JSON', true);
    return 'failed';
  }
  const ev = normalizeEvent(raw, eventKey, true, row.received_at);
  if (!ev) {
    await setStatus('ignored', 'event kind not handled', false);
    return 'ignored';
  }
  if (env.ZALO_OA_ID && ev.oa_id !== env.ZALO_OA_ID) {
    await setStatus('ignored', 'foreign_oa', false);
    return 'ignored';
  }

  try {
    const stub = env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName(ev.oa_id, ev.zalo_user_id)));
    const result = (await stub.ingestEvent(ev)) as IngestResult;
    const status = result.action === 'ignored' ? 'ignored' : 'processed';
    await setStatus(status, null, true);
    return status;
  } catch (err) {
    const attempts = row.attempts + 1;
    const final = attempts >= MAX_DISPATCH_ATTEMPTS;
    await setStatus(final ? 'failed' : 'received', shortError(err), true);
    console.error(JSON.stringify({ level: 'error', at: 'zalo.dispatch', event_key: eventKey, attempts, final, error: shortError(err) }));
    return final ? 'failed' : 'retry';
  }
}
