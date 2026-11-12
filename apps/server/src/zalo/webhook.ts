// Owner: server-zalo. POST /zalo/webhook (docs/contracts.md "Zalo webhook").
// Must answer within 2 s: verify signature -> INSERT OR IGNORE events_inbox -> 200, then dispatch to the
// Conversation DO with ctx.waitUntil (never call the model or Zalo send APIs here).
//
// Signature (research/03 + snapshot zaloplatforms-OA-llms-full.txt:9301): header X-ZEvent-Signature,
// mac = sha256(appId + data + timeStamp + OAsecretKey). We hash the raw body bytes exactly as received
// (never a re-serialized JSON), body.app_id and body.timestamp. Unverified on a real OA.
import type { Context } from 'hono';
import type { AppEnv, WebhookResponse, ZaloWebhookEvent } from '../types';
import { HttpError } from '../lib/http';
import { verifySignature } from '../lib/zalo-signature';
import { eventKey, eventParties } from './parse';
import { dispatchEvent } from './dispatch';

const MAX_BODY_BYTES = 256 * 1024;

export async function handleWebhook(c: Context<AppEnv>): Promise<Response> {
  const env = c.env;
  const now = Date.now();
  const rawBody = await c.req.text();
  if (rawBody.length > MAX_BODY_BYTES) throw new HttpError(400, 'bad_request', 'body too large');

  let raw: ZaloWebhookEvent;
  try {
    raw = JSON.parse(rawBody) as ZaloWebhookEvent;
  } catch {
    throw new HttpError(400, 'bad_request', 'body must be JSON');
  }
  if (!raw || typeof raw !== 'object' || typeof raw.event_name !== 'string' || raw.event_name.length === 0) {
    throw new HttpError(400, 'bad_request', 'event_name is required');
  }

  const appId = typeof raw.app_id === 'string' ? raw.app_id : String(raw.app_id ?? '');
  const timestamp = typeof raw.timestamp === 'string' ? raw.timestamp : String(raw.timestamp ?? '');
  const signatureOk = await verifySignature(c.req.header('x-zevent-signature'), appId, rawBody, timestamp, env.ZALO_OA_SECRET_KEY);
  const mode = env.WEBHOOK_SIGNATURE_MODE === 'enforce' ? 'enforce' : 'observe';
  if (!signatureOk && mode === 'enforce') {
    throw new HttpError(401, 'signature_invalid', 'webhook signature does not match');
  }

  const key = await eventKey(raw, rawBody);
  const { oa_id, zalo_user_id } = eventParties(raw);
  const numRetryHeader = Number(c.req.header('num_retry') ?? c.req.header('num-retry') ?? '0');
  const numRetry = Number.isFinite(numRetryHeader) && numRetryHeader > 0 ? Math.floor(numRetryHeader) : 0;
  const zaloTs = Number(raw.timestamp);

  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO events_inbox
       (event_key, event_name, zalo_msg_id, oa_id, zalo_user_id, zalo_timestamp, num_retry, signature_ok, signature_mode, raw_body, status, attempts, error, received_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?, 0, ?, ?)`,
  )
    .bind(
      key,
      raw.event_name,
      raw.message?.msg_id ?? null,
      oa_id,
      zalo_user_id,
      Number.isFinite(zaloTs) && zaloTs > 0 ? zaloTs : null,
      numRetry,
      signatureOk ? 1 : 0,
      mode,
      // A body with a wrong signature is not trusted and may carry anyone's text: keep only the metadata.
      signatureOk ? rawBody : '',
      // observe mode: a wrong signature is stored for inspection but never dispatched or swept
      signatureOk ? 'received' : 'ignored',
      signatureOk ? null : 'signature_invalid',
      now,
    )
    .run();
  let duplicate = (ins.meta.changes ?? 0) === 0;

  if (duplicate && signatureOk) {
    // A row stored earlier with a WRONG signature (observe mode) must not shadow the genuine event.
    const upgraded = await env.DB.prepare(
      `UPDATE events_inbox SET signature_ok = 1, signature_mode = ?, raw_body = ?, status = 'received', error = NULL, received_at = ?
       WHERE event_key = ? AND signature_ok = 0`,
    )
      .bind(mode, rawBody, now, key)
      .run();
    if ((upgraded.meta.changes ?? 0) > 0) duplicate = false;
  }

  if (duplicate) {
    if (numRetry > 0) {
      await env.DB.prepare('UPDATE events_inbox SET num_retry = MAX(num_retry, ?) WHERE event_key = ?').bind(numRetry, key).run();
    }
  } else if (signatureOk) {
    // Dispatch after the response. Failures keep the row 'received' for inbox_sweep; never surface as 5xx.
    c.executionCtx.waitUntil(
      dispatchEvent(env, key).catch((err: unknown) => {
        console.error(JSON.stringify({ level: 'error', at: 'zalo.webhook.dispatch', event_key: key, error: String(err).slice(0, 200) }));
      }),
    );
  } else {
    console.warn(JSON.stringify({ level: 'warn', at: 'zalo.webhook', event_key: key, signature_ok: false, mode }));
  }

  const body: WebhookResponse = { ok: true, event_key: key, duplicate, signature_ok: signatureOk };
  return c.json(body, 200);
}
