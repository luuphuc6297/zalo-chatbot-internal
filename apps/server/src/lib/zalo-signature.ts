// Owner: server-zalo. Webhook signature per research/03-zalo-oa-platform.md:
//   X-ZEvent-Signature: mac=sha256(appId + data + timeStamp + OAsecretKey)
// Interpretation used here (UNVERIFIED on a real OA; WEBHOOK_SIGNATURE_MODE=observe until measured):
//   appId     = body.app_id
//   data      = the raw request body string exactly as received
//   timeStamp = body.timestamp (string of ms)
//   secret    = ZALO_OA_SECRET_KEY
// Header value accepted with or without the "mac=" prefix; hex compared case-insensitively.
// scripts/simulate_zalo.py computes the same formula; keep them in sync.

export async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, '0')).join('');
}

export async function computeSignature(appId: string, rawBody: string, timestamp: string, secret: string): Promise<string> {
  return `mac=${await sha256Hex(appId + rawBody + timestamp + secret)}`;
}

export async function verifySignature(
  header: string | undefined | null,
  appId: string,
  rawBody: string,
  timestamp: string,
  secret: string,
): Promise<boolean> {
  if (!header || !secret) return false;
  const got = header.trim().replace(/^mac=/i, '').toLowerCase();
  const want = (await computeSignature(appId, rawBody, timestamp, secret)).slice(4);
  if (got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}
