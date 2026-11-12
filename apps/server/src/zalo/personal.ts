// Owner: personal channel. POST /zalo/personal/webhook (docs/contracts.md "Personal Zalo channel").
//
// `zalo-agent listen --filter user --webhook <url>` POSTs one event, or {event:"batch", accountId, count, events:[...]},
// with `Authorization: Bearer <secret>` and `X-Zalo-Signature: sha256=<hex HMAC-SHA256 of the exact body bytes>`
// (engine src/core/webhook-outbox.js webhookHeaders). Both must match ZALO_PERSONAL_WEBHOOK_SECRET (constant time).
// Delivery is durable with retries on the engine side: any non-2xx except 400/413/422 is retried, 400/413/422 is
// dead-lettered there. So: wrong auth -> 401 (kept and retried once fixed), malformed body -> 400.
//
// Order per event: verify -> INSERT OR IGNORE events_inbox ('personal:' + msgId) -> 200 -> ctx.waitUntil(dispatch).
// Group threads (type 1), non-message events, the account's chat with itself and threads listed in
// ZALO_PERSONAL_IGNORE_THREADS are logged (metadata only) and not stored.
// Dispatch (also used by inbox_sweep for 'personal:' keys):
//   self-sent + matches an outbox row the bridge sent (msgId or a part's msgId, or same thread + text of a row not
//     matched yet, claimed within 24 h; a photo: a menu image row claimed within 3 minutes that has no msgIds yet,
//     or the photo has no msgId) -> echo: ignored,
//     and the row is confirmed 'sent' if the bridge had not reported yet;
//   isSelf otherwise -> staff typed on the phone: DO records a staff message and takes the conversation over;
//   incoming -> DO ingests a customer message (consent gate, debounce, media handoff ...).
import type { Context } from 'hono';
import type { AppEnv, Env, IngestResult, PersonalWebhookEvent, PersonalWebhookResponse, PersonalWebhookResult } from '../types';
import { conversationObjectName } from '../types';
import { HttpError } from '../lib/http';
import { safeEqual } from '../lib/auth';
import { PERSONAL_OA_ID, personalUserId } from '../lib/zalo-personal';
import { confirmByEcho, findEchoRow } from '../bridge/outbox';
import { MAX_DISPATCH_ATTEMPTS, type DispatchOutcome } from './dispatch';
import { ignoredThreads, isSelfEvent, normalizePersonalEvent, personalEventKey, personalIgnoreReason, personalText } from './personal-parse';

const MAX_BODY_BYTES = 1024 * 1024;
const MAX_BATCH_EVENTS = 500;

async function hmacSha256Hex(secret: string, body: Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, body);
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Both headers must carry the shared secret: the bearer token, and the HMAC of the exact bytes received. */
export async function verifyPersonalWebhook(
  secretRaw: string | undefined,
  authorization: string | undefined,
  signature: string | undefined,
  body: Uint8Array,
): Promise<'ok' | 'not_configured' | 'unauthorized' | 'signature_invalid'> {
  // The engine trims the secret before using it (webhookHeaders), so the server does too.
  const secret = (secretRaw ?? '').trim();
  if (!secret) return 'not_configured';
  const m = /^Bearer\s+(.+)$/i.exec((authorization ?? '').trim());
  const token = m ? m[1]!.trim() : '';
  // Compute the HMAC even when the bearer is wrong, so both failures take about the same time.
  const want = await hmacSha256Hex(secret, body);
  const got = (signature ?? '').trim().replace(/^sha256=/i, '').toLowerCase();
  const tokenOk = token.length > 0 && safeEqual(token, secret);
  const sigOk = got.length === want.length && safeEqual(got, want);
  if (!tokenOk) return 'unauthorized';
  if (!sigOk) return 'signature_invalid';
  return 'ok';
}

function logIgnored(reason: string, ev: unknown): void {
  const e = (ev && typeof ev === 'object' ? ev : {}) as PersonalWebhookEvent;
  // Metadata only: never the content, the name or the ids.
  console.log(JSON.stringify({ level: 'info', at: 'zalo.personal.webhook', ignored: reason, event: typeof e.event === 'string' ? e.event.slice(0, 32) : null, type: e.type ?? null }));
}

export async function handlePersonalWebhook(c: Context<AppEnv>): Promise<Response> {
  const env = c.env;
  const now = Date.now();
  const bytes = new Uint8Array(await c.req.arrayBuffer());
  if (bytes.byteLength > MAX_BODY_BYTES) throw new HttpError(413, 'bad_request', 'body too large');

  const verdict = await verifyPersonalWebhook(env.ZALO_PERSONAL_WEBHOOK_SECRET, c.req.header('authorization'), c.req.header('x-zalo-signature'), bytes);
  if (verdict === 'not_configured') throw new HttpError(401, 'unauthorized', 'ZALO_PERSONAL_WEBHOOK_SECRET is not set');
  if (verdict === 'unauthorized') throw new HttpError(401, 'unauthorized', 'invalid webhook bearer token');
  if (verdict === 'signature_invalid') throw new HttpError(401, 'signature_invalid', 'X-Zalo-Signature does not match the body');

  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new HttpError(400, 'bad_request', 'body must be JSON');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new HttpError(400, 'bad_request', 'body must be a JSON object');
  const top = parsed as Record<string, unknown>;
  const isBatch = top.event === 'batch';
  if (isBatch && !Array.isArray(top.events)) throw new HttpError(400, 'bad_request', 'batch body needs an events array');
  const events: unknown[] = isBatch ? (top.events as unknown[]) : [parsed];
  if (events.length > MAX_BATCH_EVENTS) throw new HttpError(413, 'bad_request', `at most ${MAX_BATCH_EVENTS} events per batch`);
  const batchAccount = typeof top.accountId === 'string' ? top.accountId : undefined;
  const attemptHeader = Number(c.req.header('x-zalo-attempt') ?? '1');
  const numRetry = Number.isFinite(attemptHeader) && attemptHeader > 1 ? Math.floor(attemptHeader) - 1 : 0;

  const results: PersonalWebhookResult[] = [];
  const toDispatch: string[] = [];
  const ignore = ignoredThreads(env.ZALO_PERSONAL_IGNORE_THREADS);
  for (let index = 0; index < events.length; index++) {
    const raw = events[index];
    // A batch carries accountId at the top; single events carry it themselves.
    const candidate =
      raw && typeof raw === 'object' && !Array.isArray(raw)
        ? { ...(raw as PersonalWebhookEvent), ...(!(raw as PersonalWebhookEvent).accountId && batchAccount ? { accountId: batchAccount } : {}) }
        : raw;
    const reason = personalIgnoreReason(candidate, env.ZALO_PERSONAL_ACCOUNT_ID, ignore);
    if (reason) {
      logIgnored(reason, candidate);
      results.push({ index, event_key: null, status: 'ignored', reason });
      continue;
    }
    const ev = candidate as PersonalWebhookEvent;
    const key = await personalEventKey(ev);
    const threadId = String(ev.threadId);
    const ins = await env.DB.prepare(
      `INSERT OR IGNORE INTO events_inbox
         (event_key, event_name, zalo_msg_id, oa_id, zalo_user_id, zalo_timestamp, num_retry, signature_ok, signature_mode, raw_body, status, attempts, error, received_at)
       VALUES (?,?,?,?,?, NULL, ?, 1, 'enforce', ?, 'received', 0, NULL, ?)`,
    )
      .bind(
        key,
        isSelfEvent(ev, env.ZALO_PERSONAL_ACCOUNT_ID) ? 'personal_self_message' : 'personal_message',
        typeof ev.msgId === 'string' ? ev.msgId : null,
        PERSONAL_OA_ID,
        personalUserId(threadId),
        numRetry,
        JSON.stringify(ev),
        now,
      )
      .run();
    if ((ins.meta.changes ?? 0) === 0) {
      if (numRetry > 0) await env.DB.prepare('UPDATE events_inbox SET num_retry = MAX(num_retry, ?) WHERE event_key = ?').bind(numRetry, key).run();
      results.push({ index, event_key: key, status: 'duplicate' });
      continue;
    }
    results.push({ index, event_key: key, status: 'accepted' });
    toDispatch.push(key);
  }

  if (toDispatch.length > 0) {
    // In order, after the response: a batch keeps the thread's message order. Failures stay 'received' for inbox_sweep.
    c.executionCtx.waitUntil(
      (async () => {
        for (const key of toDispatch) {
          try {
            await dispatchPersonalEvent(env, key);
          } catch (err) {
            console.error(JSON.stringify({ level: 'error', at: 'zalo.personal.dispatch', event_key: key, error: String(err).slice(0, 200) }));
          }
        }
      })(),
    );
  }

  const body: PersonalWebhookResponse = { ok: true, count: events.length, results };
  return c.json(body, 200);
}

interface InboxRow {
  event_key: string;
  raw_body: string;
  status: string;
  attempts: number;
  received_at: number;
}

/** Hands one stored personal event to its Conversation DO (or drops it as the bridge's own echo). */
export async function dispatchPersonalEvent(env: Env, eventKey: string, now: number = Date.now()): Promise<DispatchOutcome> {
  const row = await env.DB.prepare('SELECT event_key, raw_body, status, attempts, received_at FROM events_inbox WHERE event_key = ?')
    .bind(eventKey)
    .first<InboxRow>();
  if (!row || row.status !== 'received') return 'skipped';

  const setStatus = (status: string, error: string | null, bumpAttempt: boolean) =>
    env.DB.prepare(
      `UPDATE events_inbox SET status = ?, error = ?, attempts = attempts + ?, processed_at = CASE WHEN ? IN ('processed','ignored','failed') THEN ? ELSE processed_at END
       WHERE event_key = ? AND status = 'received'`,
    )
      .bind(status, error, bumpAttempt ? 1 : 0, status, now, eventKey)
      .run();

  let ev: PersonalWebhookEvent;
  try {
    ev = JSON.parse(row.raw_body) as PersonalWebhookEvent;
  } catch {
    await setStatus('failed', 'raw_body is not JSON', true);
    return 'failed';
  }
  // Re-checked at dispatch: ZALO_PERSONAL_IGNORE_THREADS may have changed since the event was stored.
  const ignoredBecause = personalIgnoreReason(ev, env.ZALO_PERSONAL_ACCOUNT_ID, ignoredThreads(env.ZALO_PERSONAL_IGNORE_THREADS));
  if (ignoredBecause) {
    await setStatus('ignored', `not a customer DM: ${ignoredBecause}`, false);
    return 'ignored';
  }
  const threadId = String(ev.threadId);
  const self = isSelfEvent(ev, env.ZALO_PERSONAL_ACCOUNT_ID);

  try {
    if (self) {
      const { text, placeholder, kind } = personalText(ev);
      // A self-sent photo may be the echo of a menu image row (matched by msgId, else by time; src/bridge/outbox.ts).
      const echo = await findEchoRow(env, threadId, typeof ev.msgId === 'string' ? ev.msgId : null, placeholder ? null : text, ev.catchUp === true, now, {
        photo: kind === 'image',
      });
      if (echo) {
        await confirmByEcho(env, echo, typeof ev.msgId === 'string' ? ev.msgId : null, now);
        await setStatus('ignored', `echo:${echo.id}`, true);
        return 'ignored';
      }
    }
    const normalized = normalizePersonalEvent(ev, eventKey, row.received_at, env.ZALO_PERSONAL_ACCOUNT_ID);
    const stub = env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName(normalized.oa_id, normalized.zalo_user_id)));
    const result = (await stub.ingestEvent(normalized)) as IngestResult;
    const status = result.action === 'ignored' ? 'ignored' : 'processed';
    await setStatus(status, result.action === 'echo_matched' ? 'echo_matched' : null, true);
    return status;
  } catch (err) {
    const attempts = row.attempts + 1;
    const final = attempts >= MAX_DISPATCH_ATTEMPTS;
    const msg = (err instanceof Error ? err.message : String(err)).slice(0, 300);
    await setStatus(final ? 'failed' : 'received', msg, true);
    console.error(JSON.stringify({ level: 'error', at: 'zalo.personal.dispatch', event_key: eventKey, attempts, final, error: msg }));
    return final ? 'failed' : 'retry';
  }
}
