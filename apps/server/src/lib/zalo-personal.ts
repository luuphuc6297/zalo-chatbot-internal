// Owner: server-zalo. Shared helpers of the personal Zalo channel (docs/contracts.md "Personal Zalo channel").
// A personal customer is stored as customers(oa_id = 'personal', zalo_user_id = 'p:' + threadId, channel = 'personal'),
// so an OA user id can never collide with a personal thread id and the Conversation DO name stays unique.
import type { ZaloButton } from '../types';
import {
  CONSENT_PAYLOAD_AGREE,
  CONSENT_PAYLOAD_STAFF,
  CONSENT_REPLY_LINE_AGREE,
  CONSENT_REPLY_LINE_STAFF,
} from './fixed-messages';
import { stripMarks } from './text';

export const PERSONAL_OA_ID = 'personal';
export const PERSONAL_USER_PREFIX = 'p:';

export function personalUserId(threadId: string): string {
  return PERSONAL_USER_PREFIX + threadId;
}

export function isPersonalUserId(zaloUserId: string | null | undefined): boolean {
  return typeof zaloUserId === 'string' && zaloUserId.startsWith(PERSONAL_USER_PREFIX) && zaloUserId.length > PERSONAL_USER_PREFIX.length;
}

/** 'p:123' -> '123'; null when the id is not a personal one. */
export function threadIdOf(zaloUserId: string): string | null {
  return isPersonalUserId(zaloUserId) ? zaloUserId.slice(PERSONAL_USER_PREFIX.length) : null;
}

/**
 * Buttons cannot be sent from a personal account. The text keeps its wording and gets one line per button that
 * says what to type. The two consent buttons have fixed lines; any other button is spelled out generically.
 */
export function buttonsAsText(text: string, buttons: ZaloButton[]): string {
  const lines = buttons.map((b) => {
    const payload = typeof b.payload === 'string' ? b.payload : '';
    if (payload === CONSENT_PAYLOAD_AGREE) return CONSENT_REPLY_LINE_AGREE;
    if (payload === CONSENT_PAYLOAD_STAFF) return CONSENT_REPLY_LINE_STAFF;
    if (b.type === 'oa.open.url' || b.type === 'oa.open.phone') {
      const target = typeof b.payload === 'string' ? b.payload : String((b.payload as Record<string, unknown>).url ?? (b.payload as Record<string, unknown>).phone_code ?? '');
      return target ? `${b.title}: ${target}` : b.title;
    }
    return `Nhắn "${b.title}" để chọn mục này.`;
  });
  return [text, ...lines].join('\n');
}

/** Lowercase, no diacritics, punctuation removed, single spaces. Used for typed keywords. */
export function normalizeKeyword(s: string): string {
  return stripMarks(s)
    .replace(/[.,!?;:~…"'“”‘’()\[\]{}*_\-–—]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const AGREE_REPLIES = new Set([
  'dong y',
  'dong y a',
  'ok dong y',
  'ok dong y a',
  'oke dong y',
  'okay dong y',
  'da dong y',
  'da dong y a',
  'vang dong y',
  'vang dong y a',
  'em dong y',
  'toi dong y',
  'minh dong y',
]);

const STAFF_REPLIES = new Set([
  'gap nhan vien',
  'gap nhan vien a',
  'da gap nhan vien',
  'cho gap nhan vien',
  'cho em gap nhan vien',
  'cho toi gap nhan vien',
  'cho minh gap nhan vien',
  'toi muon gap nhan vien',
  'em muon gap nhan vien',
  'minh muon gap nhan vien',
  'muon gap nhan vien',
]);

/**
 * The customer's answer to the consent prompt. The button payloads count on every channel; typed keywords
 * ("đồng ý", "gặp nhân viên", "ok đồng ý", ...) count only on the personal channel, as whole messages, so
 * "không đồng ý" or a longer sentence is never read as consent.
 */
export function consentReplyOf(text: string, personal: boolean): 'agree' | 'staff' | null {
  if (text === CONSENT_PAYLOAD_AGREE) return 'agree';
  if (text === CONSENT_PAYLOAD_STAFF) return 'staff';
  if (!personal || text.length > 60) return null;
  const k = normalizeKeyword(text);
  if (AGREE_REPLIES.has(k)) return 'agree';
  if (STAFF_REPLIES.has(k)) return 'staff';
  return null;
}

/** Text form used to compare a self-sent webhook message with an outbox row (echo detection). */
export function echoText(s: string | null | undefined): string {
  return (s ?? '').normalize('NFC').replace(/\s+/g, ' ').trim();
}
