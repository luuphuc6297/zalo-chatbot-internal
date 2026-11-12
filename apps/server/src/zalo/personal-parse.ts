// Owner: personal channel. Engine webhook event -> NormalizedEvent (docs/contracts.md "Personal Zalo channel").
// Event shape: @ardennguyen/zalo-agent-cli v2.5.9 src/commands/listen.js messageEvent():
//   { event: "message", msgId, cliMsgId, threadId, type (0 user, 1 group), isSelf, uidFrom, dName, msgType, content, catchUp? }
// content is a string for text and an object for attachments (photo, sticker, file, link, ...). For isSelf events
// dName is the account owner, not the customer, so it is never used as the customer's name.
import type { Attachment, NormalizedEvent, PersonalWebhookEvent } from '../types';
import { PERSONAL_OA_ID, personalUserId } from '../lib/zalo-personal';
import { sha256Hex } from '../lib/text';

type MessageKind = NormalizedEvent['message_kind'];

/** Shown to staff (and stored as the message text) for a message that is not text. */
export const PLACEHOLDER_TEXT: Record<Exclude<MessageKind, 'text'>, string> = {
  image: '[hình ảnh]',
  sticker: '[sticker]',
  file: '[tệp đính kèm]',
  link: '[liên kết]',
  audio: '[tin nhắn thoại]',
  video: '[video]',
  location: '[vị trí]',
  other: '[tin nhắn không phải chữ]',
};

function str(v: unknown): string | undefined {
  if (typeof v === 'string' && v.length > 0) return v;
  if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  return undefined;
}

/** zca-js msgType ('webchat', 'chat.photo', 'chat.sticker', 'share.file', 'chat.recommended', ...) -> our kind. */
export function personalMessageKind(msgType: string | null | undefined, content: unknown): MessageKind {
  if (typeof content === 'string') return 'text';
  const t = (msgType ?? '').toLowerCase();
  if (/photo|image|gif|doodle/.test(t)) return 'image';
  if (/sticker/.test(t)) return 'sticker';
  if (/video/.test(t)) return 'video';
  if (/voice|audio/.test(t)) return 'audio';
  if (/location/.test(t)) return 'location';
  if (/file/.test(t)) return 'file';
  if (/link|recommend/.test(t)) return 'link';
  return 'other';
}

function attachmentsOf(kind: MessageKind, content: unknown): Attachment[] {
  if (kind === 'text' || !content || typeof content !== 'object') return [];
  const c = content as Record<string, unknown>;
  const att: Attachment = { type: kind };
  const url = str(c.href) ?? str(c.url);
  if (url) att.url = url;
  const thumb = str(c.thumb) ?? str(c.thumbnail);
  if (thumb) att.thumbnail = thumb;
  const name = str(c.title) ?? str(c.description);
  if (name) att.name = name.slice(0, 200);
  return [att];
}

/** events_inbox key: 'personal:' + msgId; without a msgId (never seen) the hash of the event JSON. */
export async function personalEventKey(ev: PersonalWebhookEvent): Promise<string> {
  const msgId = str(ev.msgId);
  if (msgId) return `personal:${msgId}`;
  return `personal:sha256:${await sha256Hex(JSON.stringify(ev))}`;
}

/** ZALO_PERSONAL_IGNORE_THREADS ("123, 456") -> set of threadIds that are not customers. */
export function ignoredThreads(raw: string | undefined): Set<string> {
  return new Set((raw ?? '').split(/[\s,;]+/).map((x) => x.trim()).filter((x) => x.length > 0));
}

/** The personal account's own id: ZALO_PERSONAL_ACCOUNT_ID when set, else the event's accountId. */
function ownIdOf(e: PersonalWebhookEvent, accountId: string | undefined): string | undefined {
  return accountId || str(e.accountId);
}

/**
 * A message the account owner sent: the engine's isSelf, or a sender id equal to the account's own id (zca-js sets
 * isSelf only when uidFrom is "0"; a row restored from an offline queue can carry the real ownId instead).
 */
export function isSelfEvent(ev: PersonalWebhookEvent, accountId: string | undefined): boolean {
  if (ev.isSelf === true) return true;
  const own = ownIdOf(ev, accountId);
  return !!own && str(ev.uidFrom) === own;
}

export type PersonalIgnoreReason = 'not_message' | 'group_thread' | 'no_thread' | 'foreign_account' | 'malformed' | 'own_thread' | 'ignored_thread';

/**
 * Why an event is not a customer DM we handle, or null when it is one. 'own_thread': the account's chat with itself
 * (My Documents / Cloud của tôi), never a customer. 'ignored_thread': listed in ZALO_PERSONAL_IGNORE_THREADS.
 */
export function personalIgnoreReason(ev: unknown, accountId: string | undefined, ignore: Set<string> = new Set()): PersonalIgnoreReason | null {
  if (!ev || typeof ev !== 'object' || Array.isArray(ev)) return 'malformed';
  const e = ev as PersonalWebhookEvent;
  if (e.event !== 'message') return 'not_message';
  if (Number(e.type ?? 0) !== 0) return 'group_thread';
  const threadId = str(e.threadId);
  if (!threadId) return 'no_thread';
  if (accountId && str(e.accountId) && str(e.accountId) !== accountId) return 'foreign_account';
  if (threadId === ownIdOf(e, accountId)) return 'own_thread';
  if (ignore.has(threadId)) return 'ignored_thread';
  return null;
}

/** Text of the message as stored and shown: the text itself, or a placeholder for attachments. */
export function personalText(ev: PersonalWebhookEvent): { text: string; kind: MessageKind; placeholder: boolean } {
  const kind = personalMessageKind(ev.msgType, ev.content);
  if (kind === 'text') return { text: typeof ev.content === 'string' ? ev.content : '', kind, placeholder: false };
  return { text: PLACEHOLDER_TEXT[kind], kind, placeholder: true };
}

/**
 * Normalized form handed to the Conversation DO.
 *   incoming (isSelf false): kind 'customer_message', display_name = dName
 *   self-sent, not an echo of the bridge (isSelfEvent): kind 'oa_message' with zalo_admin_id 'phone', which the DO
 *   records as a staff message and turns into a staff takeover (same as an OA Manager reply).
 */
export function normalizePersonalEvent(ev: PersonalWebhookEvent, eventKey: string, receivedAt: number, accountId?: string): NormalizedEvent {
  const threadId = str(ev.threadId)!;
  const { text, kind, placeholder } = personalText(ev);
  const self = isSelfEvent(ev, accountId);
  const out: NormalizedEvent = {
    event_key: eventKey,
    event_name: self ? 'personal_self_message' : 'personal_message',
    kind: self ? 'oa_message' : 'customer_message',
    oa_id: PERSONAL_OA_ID,
    zalo_user_id: personalUserId(threadId),
    zalo_timestamp: receivedAt,
    message_kind: kind,
    attachments: attachmentsOf(kind, ev.content),
    signature_ok: true,
    channel: 'personal',
  };
  const msgId = str(ev.msgId);
  if (msgId) out.zalo_msg_id = msgId;
  if (text.length > 0) out.text = text.slice(0, 4000);
  if (placeholder) out.text_is_placeholder = true;
  if (self) out.zalo_admin_id = 'phone';
  else {
    const name = str(ev.dName);
    if (name) out.display_name = name.slice(0, 100);
  }
  return out;
}
