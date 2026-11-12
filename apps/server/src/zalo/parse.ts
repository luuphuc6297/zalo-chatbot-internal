// Owner: server-zalo. Raw Zalo event -> NormalizedEvent + event_key.
// Event shapes: research/snapshots/zalo-2026-11-07/zaloplatforms-OA-llms-full.txt (user_send_* :9294-9410,
// oa_send_* :9570, follow/unfollow :10896, user_submit_info :10844).
//   user_send_*      sender.id = customer, recipient.id = OA
//   oa_send_*        sender.id = OA (sender.admin_id when staff typed in OA Manager), recipient.id = customer
//   follow/unfollow  oa_id = OA, follower.id = customer (no sender/recipient)
//   user_submit_info sender.id = customer, recipient.id = OA, info = form fields
import type { Attachment, NormalizedEvent, ZaloWebhookEvent } from '../types';
import { sha256Hex } from '../lib/zalo-signature';

/** event_name + ':' + message.msg_id when msg_id exists, else 'sha256:' + hex(rawBody). */
export async function eventKey(raw: ZaloWebhookEvent, rawBody: string): Promise<string> {
  const msgId = raw.message?.msg_id;
  if (typeof msgId === 'string' && msgId.length > 0) return `${raw.event_name}:${msgId}`;
  return `sha256:${await sha256Hex(rawBody)}`;
}

type MessageKind = NormalizedEvent['message_kind'];

const USER_SEND_KIND: Record<string, MessageKind> = {
  user_send_text: 'text',
  user_send_image: 'image',
  user_send_gif: 'image',
  user_send_sticker: 'sticker',
  user_send_link: 'link',
  user_send_location: 'location',
  user_send_file: 'file',
  user_send_audio: 'audio',
  user_send_video: 'video',
  user_send_business_card: 'other',
};

function messageKindFor(eventName: string): MessageKind {
  const direct = USER_SEND_KIND[eventName];
  if (direct) return direct;
  // oa_send_text / oa_send_image / ... mirror the user_send_* suffixes
  if (eventName.startsWith('oa_send_')) return USER_SEND_KIND[`user_send_${eventName.slice('oa_send_'.length)}`] ?? 'other';
  return 'other';
}

function str(v: unknown): string | undefined {
  if (typeof v === 'string' && v.length > 0) return v;
  if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  return undefined;
}

/** Zalo attachments -> our Attachment[]. Location coordinates become url 'geo:lat,lng' so nothing is lost. */
export function normalizeAttachments(raw: ZaloWebhookEvent): Attachment[] {
  const list = raw.message?.attachments;
  if (!Array.isArray(list)) return [];
  const out: Attachment[] = [];
  for (const a of list) {
    if (!a || typeof a !== 'object') continue;
    const p = (a.payload ?? {}) as Record<string, unknown>;
    const att: Attachment = { type: str(a.type) ?? 'other' };
    const url = str(p.url);
    if (url) att.url = url;
    const thumb = str(p.thumbnail);
    if (thumb) att.thumbnail = thumb;
    const name = str(p.name) ?? str(p.description);
    if (name) att.name = name;
    const coords = p.coordinates as { latitude?: unknown; longitude?: unknown } | undefined;
    if (coords && str(coords.latitude) && str(coords.longitude)) att.url = `geo:${str(coords.latitude)},${str(coords.longitude)}`;
    out.push(att);
  }
  return out;
}

/** Zalo sends timestamp as a string of ms; fall back to receive time when missing or garbage. */
export function zaloTimestamp(raw: ZaloWebhookEvent, fallback: number): number {
  const n = Number(raw.timestamp);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/** The OA id and the customer's Zalo user id of an event, whatever its direction. */
export function eventParties(raw: ZaloWebhookEvent): { oa_id: string | null; zalo_user_id: string | null } {
  const name = raw.event_name ?? '';
  const anyRaw = raw as ZaloWebhookEvent & { oa_id?: string };
  if (name === 'follow' || name === 'unfollow') {
    return { oa_id: str(anyRaw.oa_id) ?? str(raw.recipient?.id) ?? null, zalo_user_id: str(raw.follower?.id) ?? null };
  }
  if (name.startsWith('oa_send_')) {
    return { oa_id: str(raw.sender?.id) ?? null, zalo_user_id: str(raw.recipient?.id) ?? null };
  }
  return { oa_id: str(raw.recipient?.id) ?? str(anyRaw.oa_id) ?? null, zalo_user_id: str(raw.sender?.id) ?? null };
}

/** Returns null for events the bot ignores (stored with status 'ignored'). */
export function normalizeEvent(raw: ZaloWebhookEvent, eventKeyValue: string, signatureOk: boolean, now: number = Date.now()): NormalizedEvent | null {
  const name = raw.event_name ?? '';
  const { oa_id, zalo_user_id } = eventParties(raw);
  if (!oa_id || !zalo_user_id) return null;

  let kind: NormalizedEvent['kind'];
  if (name.startsWith('user_send_')) kind = 'customer_message';
  else if (name.startsWith('oa_send_')) kind = 'oa_message';
  else if (name === 'follow') kind = 'follow';
  else if (name === 'unfollow') kind = 'unfollow';
  else if (name === 'user_submit_info') kind = 'user_submit_info';
  else return null; // user_received_message, user_seen_message, tag events, ... are not used in the MVP

  const ev: NormalizedEvent = {
    event_key: eventKeyValue,
    event_name: name,
    kind,
    oa_id,
    zalo_user_id,
    zalo_timestamp: zaloTimestamp(raw, now),
    message_kind: kind === 'customer_message' || kind === 'oa_message' ? messageKindFor(name) : 'other',
    attachments: normalizeAttachments(raw),
    signature_ok: signatureOk,
  };
  const uba = str(raw.user_id_by_app);
  if (uba) ev.user_id_by_app = uba;
  const msgId = str(raw.message?.msg_id);
  if (msgId) ev.zalo_msg_id = msgId;
  const text = raw.message?.text;
  if (typeof text === 'string' && text.length > 0) ev.text = text;
  const adminId = str(raw.sender?.admin_id);
  if (kind === 'oa_message' && adminId) ev.zalo_admin_id = adminId;
  const quote = str(raw.message?.quote_msg_id);
  if (quote) ev.quote_msg_id = quote;
  return ev;
}
