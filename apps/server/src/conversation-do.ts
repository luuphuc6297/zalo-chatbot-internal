// Owner: server-core. One Durable Object per customer (name = conversationObjectName(oa_id, zalo_user_id)).
// Serializes everything for that customer: inbound events, debounce alarm, draft acceptance and sending,
// takeover/release. D1 is the source of truth; DO storage only keeps the conversation id for the alarm.
// HttpErrors thrown here cross the RPC boundary encoded (lib/http toRpcError); handlers decode them with rpc().
import { DurableObject } from 'cloudflare:workers';
import type {
  CheckerResult,
  DraftAcceptResult,
  DraftStatus,
  Env,
  IngestResult,
  NormalizedEvent,
  RunnerDraftRequest,
  ZaloButton,
  ZaloSendOutcome,
} from './types';
import { HttpError, type RpcFailure, toRpcError, toRpcFailure } from './lib/http';
import { newId } from './lib/ids';
import { conversationMode, getFlags } from './lib/flags';
import { DAY_MS, envInt } from './lib/time';
import { auditStatement } from './lib/audit';
import {
  CONSENT_BUTTON_AGREE,
  CONSENT_BUTTON_STAFF,
  CONSENT_GRANTED_TEXT,
  CONSENT_PAYLOAD_AGREE,
  CONSENT_PAYLOAD_STAFF,
  CONSENT_PROMPT_TEXT,
  STAFF_WILL_REPLY_TEXT,
} from './lib/fixed-messages';
import {
  type ConversationRow,
  type CustomerRow,
  type DraftRow,
  cancelQueuedDraftJobs,
  consentStatus,
  createHandoff,
  getConversation,
  getCustomer,
  getJob,
  handoffStatements,
  parsePayload,
  refreshNeedsAttention,
} from './lib/db';
import { checkConversationDraft } from './checker/input';
import { cutoffSeq, debounceMs, enqueueDraftJob, jobHandedOff, releaseExpiredTakeover } from './jobs/draft-jobs';
import { getUserProfile, sendButtons, sendText } from './lib/zalo-client';
import { buttonsAsText, consentReplyOf, isPersonalUserId } from './lib/zalo-personal';
import { cancelQueuedBotRows, cancelQueuedInternalRows, queuePersonalImages } from './bridge/outbox';
import { attachmentsForJob } from './tools/menu-images';
import { menuAttachments, menuImagesLabel, parseKeys } from './lib/menu-images';
import { personalSkipApplies } from './lib/profiles';
import { conversationIsInternal, getContactRole, isInternalRole } from './lib/roles';

export const CS_WINDOW_MS = 7 * DAY_MS;
export const MAX_SEND_CHARS = 2000;
/** OA: the consent prompt is sent again at most once per day while the customer has not answered. */
const CONSENT_PROMPT_REPEAT_MS = DAY_MS;
/**
 * Personal channel: anyone who writes to the account gets the prompt (friends, family, other accounts), and a
 * personal account repeating one text to many people risks a Zalo ban, so the prompt is repeated after 30 days only.
 */
export const PERSONAL_CONSENT_PROMPT_REPEAT_MS = 30 * DAY_MS;
/** Personal channel: a typed "đồng ý" counts only this long after a delivered consent prompt. */
export const PERSONAL_CONSENT_REPLY_WINDOW_MS = DAY_MS;

type SendSource = 'bot' | 'staff' | 'server';
interface DeliverArgs {
  text: string;
  source: SendSource;
  kind?: 'text' | 'buttons';
  buttons?: ZaloButton[];
  draftId?: string | null;
  staffId?: string | null;
  meta?: { model?: string | null; account_label?: string | null; usage?: RunnerDraftRequest['usage']; cost_usd_equiv?: number; catalog_version?: string | null };
}
interface DeliverResult {
  message_id: string;
  outbox_id: string;
  outcome: ZaloSendOutcome;
}

export interface ApproveResult {
  draft_id: string;
  message_id: string;
  outbox_id: string;
  // menu images: the cs_images row queued after the text (personal channel), or why the attachments were not queued
  images?: { outbox_id: string; message_id: string; keys: string[] } | { queued: false; reason: string };
}

export class ConversationDO extends DurableObject<Env> {
  // ---------------------------------------------------------------- serialization

  /**
   * A Durable Object keeps taking RPCs while one awaits D1 (D1 is outgoing I/O, not DO storage, so the input gate
   * stays open). Two messages of one customer could then be ingested side by side and both queue a consent prompt.
   * Every state-changing entry point runs through this chain, one at a time, in arrival order.
   */
  private tail: Promise<void> = Promise.resolve();

  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.tail.then(fn, fn);
    this.tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  // ---------------------------------------------------------------- helpers

  private async rememberConversation(id: string): Promise<void> {
    if ((await this.ctx.storage.get<string>('conversation_id')) !== id) await this.ctx.storage.put('conversation_id', id);
  }

  private async resolveConversationId(given?: string): Promise<string> {
    const id = given ?? (await this.ctx.storage.get<string>('conversation_id'));
    if (!id) throw new HttpError(404, 'not_found', 'conversation not found');
    await this.rememberConversation(id);
    return id;
  }

  private async load(conversationId: string): Promise<{ conv: ConversationRow; customer: CustomerRow }> {
    const conv = await getConversation(this.env, conversationId);
    if (!conv) throw new HttpError(404, 'not_found', 'conversation not found');
    const customer = await getCustomer(this.env, conv.customer_id);
    if (!customer) throw new HttpError(404, 'not_found', 'customer not found');
    return { conv, customer };
  }

  private async maxCustomerSeq(conversationId: string): Promise<number> {
    const r = await this.env.DB.prepare("SELECT COALESCE(MAX(seq), 0) AS s FROM messages WHERE conversation_id = ? AND direction = 'inbound'")
      .bind(conversationId)
      .first<{ s: number }>();
    return r?.s ?? 0;
  }

  /** Rule 6 of the checker: state re-read right before any consultation-message send. */
  private async assertCanSend(conv: ConversationRow, customer: CustomerRow, now: number): Promise<void> {
    const flags = await getFlags(this.env);
    if (!flags.outbound_enabled) throw new HttpError(409, 'outbound_disabled', 'outbound_enabled is false');
    if (conv.bot_state === 'blocked') throw new HttpError(409, 'invalid_state', 'conversation is blocked');
    // The 7-day consultation window is a Zalo OA rule; a personal account has no such limit.
    if (isPersonalUserId(customer.zalo_user_id)) return;
    if (!customer.last_user_interaction_at || now - customer.last_user_interaction_at > CS_WINDOW_MS) {
      throw new HttpError(409, 'outside_cs_window', 'customer last interaction is older than 7 days');
    }
  }

  /** Writes messages(send_state='pending') before calling the Zalo client, then records the outcome. */
  private async deliver(conv: ConversationRow, customer: CustomerRow, a: DeliverArgs, now: number): Promise<DeliverResult> {
    const id = newId('msg', now);
    const u = a.meta?.usage;
    // Personal channel: buttons go out as text with "Nhắn ..." lines; store what the customer actually sees.
    const storedText = a.kind === 'buttons' && isPersonalUserId(customer.zalo_user_id) ? buttonsAsText(a.text, a.buttons ?? []) : a.text;
    await this.env.DB.prepare(
      'INSERT INTO messages (id, conversation_id, direction, source, kind, text, draft_id, staff_id, catalog_version, send_state, client_send_id, model, account_label, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd_equiv, created_at, seq) ' +
        "VALUES (?,?,'outbound',?,?,?,?,?,?,'pending',?,?,?,?,?,?,?,?,?,(SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?))",
    )
      .bind(
        id,
        conv.id,
        a.source,
        a.kind === 'buttons' ? 'buttons' : 'text',
        storedText,
        a.draftId ?? null,
        a.staffId ?? null,
        a.meta?.catalog_version ?? null,
        `cs_${id}`,
        a.meta?.model ?? null,
        a.meta?.account_label ?? null,
        u?.input_tokens ?? null,
        u?.output_tokens ?? null,
        u?.cache_read_input_tokens ?? null,
        u?.cache_creation_input_tokens ?? null,
        a.meta?.cost_usd_equiv ?? null,
        now,
        conv.id,
      )
      .run();
    const ctx = { conversation_id: conv.id, customer_id: customer.id, message_id: id };
    let outcome: ZaloSendOutcome;
    try {
      outcome =
        a.kind === 'buttons'
          ? await sendButtons(this.env, customer.zalo_user_id, a.text, a.buttons ?? [], ctx)
          : await sendText(this.env, customer.zalo_user_id, a.text, ctx);
    } catch (e) {
      outcome = { ok: false, unknown: false, error_code: 'client_error', error_message: (e as Error).message?.slice(0, 300) ?? 'error', outbox_id: '' };
    }
    const at = Date.now();
    if (outcome.ok && outcome.queued) {
      // Personal channel: queued for the bridge. send_state stays 'pending' until POST /bridge/outbox/:id/result
      // (or the echo of the send) settles it (src/bridge/outbox.ts).
      await this.env.DB.prepare('UPDATE conversations SET last_message_at = ?, updated_at = ? WHERE id = ?').bind(at, at, conv.id).run();
    } else if (outcome.ok) {
      await this.env.DB.batch([
        this.env.DB.prepare("UPDATE messages SET send_state = 'sent', zalo_msg_id = ?, sent_at = ? WHERE id = ?").bind(outcome.zalo_msg_id, at, id),
        this.env.DB.prepare('UPDATE conversations SET last_message_at = ?, updated_at = ? WHERE id = ?').bind(at, at, conv.id),
      ]);
    } else {
      await this.env.DB.prepare('UPDATE messages SET send_state = ?, send_error = ? WHERE id = ?')
        .bind(outcome.unknown ? 'unknown' : 'failed', `${outcome.error_code}: ${outcome.error_message}`.slice(0, 500), id)
        .run();
    }
    return { message_id: id, outbox_id: outcome.outbox_id, outcome };
  }

  private throwSendError(r: DeliverResult): void {
    if (r.outcome.ok) return;
    const details = { message_id: r.message_id, outbox_id: r.outbox_id, error_code: r.outcome.error_code };
    if (r.outcome.unknown) throw new HttpError(504, 'zalo_send_unknown', 'Zalo did not answer in time; send state unknown', details);
    throw new HttpError(502, 'zalo_send_failed', r.outcome.error_message || 'Zalo send failed', details);
  }

  /** Server-authored fixed message; skipped silently when outbound is disabled. */
  private async sendFixed(conv: ConversationRow, customer: CustomerRow, text: string, now: number, buttons?: ZaloButton[]): Promise<boolean> {
    const flags = await getFlags(this.env);
    if (!flags.outbound_enabled) {
      await this.env.DB.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, conv.id).run();
      return false;
    }
    const r = await this.deliver(conv, customer, { text, source: 'server', kind: buttons ? 'buttons' : 'text', ...(buttons ? { buttons } : {}) }, now);
    return r.outcome.ok;
  }

  private async grantAiConsent(conv: ConversationRow, customer: CustomerRow, messageId: string, seq: number, now: number, source: 'button' | 'chat_keyword' = 'button'): Promise<void> {
    await this.env.DB.batch([
      this.env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, evidence_message_id, recorded_at) VALUES (?,?,'ai_assistant','granted',?,?,?)")
        .bind(newId('cns', now), customer.id, source, messageId, now),
      this.env.DB.prepare(
        "UPDATE conversations SET bot_state = 'bot_active', consent_seq = ?, answered_seq = MAX(answered_seq, ?), session_id = NULL, session_reset_reason = NULL, updated_at = ? WHERE id = ?",
      ).bind(seq, seq, now, conv.id),
      auditStatement(this.env, { actor_type: 'zalo', actor_id: customer.id, action: 'consent.ai_assistant.granted', entity: 'conversation', entity_id: conv.id }, now),
    ]);
  }

  // ---------------------------------------------------------------- ingest

  /** Called by src/zalo/dispatch.ts for every stored event of this customer. Idempotent on event_key. */
  private async _ingestEvent(event: NormalizedEvent): Promise<IngestResult> {
    const env = this.env;
    const now = Date.now();
    const db = env.DB;
    const personal = event.channel === 'personal' || isPersonalUserId(event.zalo_user_id);
    await db.prepare('INSERT OR IGNORE INTO customers (id, oa_id, zalo_user_id, user_id_by_app, channel, created_at) VALUES (?,?,?,?,?,?)')
      .bind(newId('cus', now), event.oa_id, event.zalo_user_id, event.user_id_by_app ?? null, personal ? 'personal' : 'oa', now)
      .run();
    const customer = (await db.prepare('SELECT * FROM customers WHERE oa_id = ? AND zalo_user_id = ?').bind(event.oa_id, event.zalo_user_id).first<CustomerRow>())!;
    if (personal) {
      // Personal channel: the display name comes with each incoming message (dName); there is no profile API and
      // no age signal, so minor_flag stays unknown.
      if (event.kind === 'customer_message' && event.display_name && event.display_name !== customer.display_name) {
        customer.display_name = event.display_name;
        await db.prepare('UPDATE customers SET display_name = ? WHERE id = ?').bind(customer.display_name, customer.id).run();
      }
    } else if (customer.display_name === null && customer.minor_flag === null && event.kind === 'customer_message') {
      // First contact: Zalo profile gives the display name and is_sensitive (under 18 -> minor_flag = 1).
      try {
        const p = await getUserProfile(env, event.zalo_user_id);
        if (p.ok) {
          customer.display_name = p.profile.display_name;
          customer.minor_flag = p.profile.is_sensitive === null ? null : p.profile.is_sensitive ? 1 : 0;
          await db.prepare('UPDATE customers SET display_name = ?, minor_flag = ? WHERE id = ?').bind(customer.display_name, customer.minor_flag, customer.id).run();
        }
      } catch {
        /* profile is optional; minor_flag stays unknown */
      }
    }
    await db.prepare("INSERT OR IGNORE INTO conversations (id, customer_id, oa_id, bot_state, created_at, updated_at) VALUES (?,?,?,'awaiting_consent',?,?)")
      .bind(newId('cnv', now), customer.id, event.oa_id, now, now)
      .run();
    let conv = (await db.prepare('SELECT * FROM conversations WHERE customer_id = ?').bind(customer.id).first<ConversationRow>())!;
    await this.rememberConversation(conv.id);

    const dup = await db.prepare('SELECT id FROM messages WHERE event_key = ? OR (zalo_msg_id IS NOT NULL AND zalo_msg_id = ?)')
      .bind(event.event_key, event.zalo_msg_id ?? null)
      .first<{ id: string }>();

    if (event.kind === 'oa_message') {
      if (dup) return { conversation_id: conv.id, message_id: dup.id, action: 'echo_matched' };
      if (!event.zalo_admin_id) return { conversation_id: conv.id, message_id: null, action: 'ignored' };
      // Staff replied from Zalo OA Manager (OA) or typed on the phone of the personal account: record it and take
      // the conversation over.
      const staffLabel = personal ? 'zalo_phone' : `oa_admin:${event.zalo_admin_id}`;
      const id = newId('msg', now);
      const until = now + envInt(env.TAKEOVER_DEFAULT_MS, 43_200_000);
      const keepState = conv.bot_state === 'blocked' || conv.bot_state === 'staff_only';
      await db.batch([
        db.prepare(
          "INSERT INTO messages (id, conversation_id, direction, source, kind, text, attachments_json, zalo_msg_id, zalo_timestamp, event_key, staff_id, zalo_admin_id, send_state, created_at, sent_at, seq) VALUES (?,?,'outbound','staff',?,?,?,?,?,?,?,?,'sent',?,?,(SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?))",
        ).bind(id, conv.id, event.message_kind, event.text ?? null, JSON.stringify(event.attachments ?? []), event.zalo_msg_id ?? null, event.zalo_timestamp, event.event_key, staffLabel, event.zalo_admin_id, now, now, conv.id),
        keepState
          ? db.prepare('UPDATE conversations SET last_message_at = ?, updated_at = ? WHERE id = ?').bind(now, now, conv.id)
          : db.prepare(
              "UPDATE conversations SET bot_state = 'staff_takeover', takeover_by = ?, takeover_until = ?, last_message_at = ?, updated_at = ? WHERE id = ?",
            ).bind(staffLabel, until, now, now, conv.id),
        db.prepare('UPDATE conversations SET answered_seq = (SELECT COALESCE(MAX(seq),0) FROM messages WHERE conversation_id = ? AND direction = \'inbound\') WHERE id = ?').bind(conv.id, conv.id),
        cancelQueuedDraftJobs(env, conv.id, 'takeover', now),
        auditStatement(env, { actor_type: 'zalo', actor_id: event.zalo_admin_id, action: personal ? 'conversation.takeover_zalo_phone' : 'conversation.takeover_oa_manager', entity: 'conversation', entity_id: conv.id }, now),
      ]);
      // A bot reply still waiting in the bridge queue must not reach the customer after staff answered.
      await cancelQueuedBotRows(env, conv.id, now);
      return { conversation_id: conv.id, message_id: id, action: keepState ? 'stored' : 'takeover_detected' };
    }

    if (event.kind !== 'customer_message' && event.kind !== 'user_submit_info') {
      if (event.kind === 'follow' || event.kind === 'unfollow') {
        await auditStatement(env, { actor_type: 'zalo', actor_id: customer.id, action: `customer.${event.kind}`, entity: 'conversation', entity_id: conv.id }, now).run();
      }
      return { conversation_id: conv.id, message_id: null, action: 'ignored' };
    }
    if (dup) return this.recoverDuplicate(conv, dup.id, now, personal);

    // ---- store the customer message
    const msgId = newId('msg', now);
    await db.batch([
      db.prepare(
        "INSERT INTO messages (id, conversation_id, direction, source, kind, text, attachments_json, zalo_msg_id, zalo_timestamp, event_key, created_at, seq) VALUES (?,?,'inbound','customer',?,?,?,?,?,?,?,(SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?))",
      ).bind(
        msgId,
        conv.id,
        event.kind === 'user_submit_info' ? 'user_info' : event.message_kind,
        event.text ?? null,
        JSON.stringify(event.attachments ?? []),
        event.zalo_msg_id ?? null,
        event.zalo_timestamp,
        event.event_key,
        now,
        conv.id,
      ),
      db.prepare('UPDATE customers SET last_user_interaction_at = ?, user_id_by_app = COALESCE(user_id_by_app, ?) WHERE id = ?').bind(now, event.user_id_by_app ?? null, customer.id),
      db.prepare('UPDATE conversations SET last_message_at = ?, last_customer_message_at = ?, updated_at = ? WHERE id = ?').bind(now, now, now, conv.id),
    ]);
    customer.last_user_interaction_at = now;
    // seq is assigned inside the INSERT (atomic in D1) because other RPCs can interleave at await points.
    const seq = (await db.prepare('SELECT seq FROM messages WHERE id = ?').bind(msgId).first<{ seq: number }>())!.seq;

    // ---- internal contact (docs/contracts.md section 14.3): a manager or a staff member of the spa. The message is
    // stored above and nothing else happens: no needs_attention, no consent prompt, no fixed text, no handoff, no
    // draft job, no debounce alarm. bot_state is left as it is, so removing the role restores the normal flow on the
    // next message. A text that starts with "/" from a staff contact is reserved for staff commands (not built yet).
    if (isInternalRole((await getContactRole(env, customer.zalo_user_id))?.role)) {
      await db.batch([
        cancelQueuedDraftJobs(env, conv.id, 'internal_contact', now),
        db.prepare('UPDATE conversations SET debounce_until = NULL WHERE id = ?').bind(conv.id),
      ]);
      // An automatic message still waiting in the bridge queue (bot reply, consent prompt, follow-up) must not go out.
      await cancelQueuedInternalRows(env, conv.id, now);
      await this.ctx.storage.deleteAlarm();
      return { conversation_id: conv.id, message_id: msgId, action: 'internal_contact' };
    }
    // A placeholder ("[hình ảnh]" for a personal-channel photo) is stored for staff, but the bot treats the
    // message as non-text: no consent keyword, and in bot_active the unsupported_message handoff below.
    const text = event.text_is_placeholder ? '' : (event.text ?? '').trim();
    let reply = consentReplyOf(text, personal);

    if (event.kind === 'user_submit_info') {
      // Form fields are not in NormalizedEvent; keep them on the message for staff (never sent to the model).
      const raw = await db.prepare('SELECT raw_body FROM events_inbox WHERE event_key = ?').bind(event.event_key).first<{ raw_body: string }>();
      let info: Record<string, unknown> = {};
      try {
        info = ((JSON.parse(raw?.raw_body ?? '{}') as { info?: Record<string, unknown> }).info ?? {}) as Record<string, unknown>;
      } catch {
        info = {};
      }
      await db.batch([
        db.prepare('UPDATE messages SET text = COALESCE(text, ?), attachments_json = ? WHERE id = ?').bind(
          `Khách gửi thông tin: ${Object.keys(info).join(', ') || 'trống'}`,
          JSON.stringify([{ type: 'user_info', ...info }]),
          msgId,
        ),
        db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id),
      ]);
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }

    conv = await releaseExpiredTakeover(env, conv, now);

    // ---- consent gate (server only, model never called)
    if (conv.bot_state === 'awaiting_consent' || conv.bot_state === 'staff_only') {
      // Personal channel: "đồng ý" is an everyday word. It is consent only as the answer to a consent prompt that was
      // delivered within the last 24 h and is still the latest message sent to this customer.
      if (reply === 'agree' && personal && !(await this.consentPromptAnswerable(conv.id, now))) reply = null;
      if (reply === 'agree') {
        if (customer.minor_flag === 1) {
          await db.prepare("UPDATE conversations SET bot_state = 'blocked', needs_attention = 1 WHERE id = ?").bind(conv.id).run();
          await createHandoff(env, { conversation_id: conv.id, customer_id: customer.id, source: 'server', reason_code: 'minor_flag', urgency: 'normal', idempotency_key: `minor:${conv.id}` }, now);
          return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
        }
        await this.grantAiConsent(conv, customer, msgId, seq, now, text === CONSENT_PAYLOAD_AGREE ? 'button' : 'chat_keyword');
        await this.sendFixed(conv, customer, CONSENT_GRANTED_TEXT, now);
        return { conversation_id: conv.id, message_id: msgId, action: 'consent_recorded' };
      }
      // Contact profiles (docs/contracts.md section 13): a contact the analyzer (or staff) classified as personal with
      // high confidence is kept away from the bot. staff_only, quietly: no consent prompt, nothing sent, a waiting
      // prompt cancelled, needs_attention = 1 so the owner sees the message. Flag profile_personal_skip_bot.
      if (personal && conv.bot_state === 'awaiting_consent' && (await personalSkipApplies(env, customer, conv.id))) {
        await db.batch([
          db.prepare(
            "UPDATE conversations SET bot_state = 'staff_only', needs_attention = 1, takeover_by = NULL, takeover_until = NULL, debounce_until = NULL, updated_at = ? WHERE id = ?",
          ).bind(now, conv.id),
          cancelQueuedDraftJobs(env, conv.id, 'staff_only', now),
          auditStatement(env, {
            actor_type: 'system',
            actor_id: 'profile',
            action: 'conversation.staff_only_profile',
            entity: 'conversation',
            entity_id: conv.id,
            before: { bot_state: conv.bot_state },
            after: { bot_state: 'staff_only', reason: 'profile_personal_high' },
          }, now),
        ]);
        await cancelQueuedBotRows(env, conv.id, now, { alsoServer: true, reason: 'cancelled: personal contact (profile)' });
        return { conversation_id: conv.id, message_id: msgId, action: 'staff_only_profile' };
      }
      // A personal contact already in staff_only (the quiet rule above, or staff) gets nothing on "gặp nhân viên"
      // either: no fixed reply, no handoff; the message is stored and flagged for staff.
      if (personal && conv.bot_state === 'staff_only' && reply === 'staff' && (await personalSkipApplies(env, customer, conv.id))) {
        await db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id).run();
        return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
      }
      if (reply === 'staff') {
        await db.batch([
          db.prepare("UPDATE conversations SET bot_state = 'staff_only', updated_at = ? WHERE id = ?").bind(now, conv.id),
          ...handoffStatements(env, {
            conversation_id: conv.id,
            customer_id: customer.id,
            source: 'server',
            reason_code: 'customer_declined_ai',
            urgency: 'normal',
            summary_for_staff: 'Khách chọn gặp nhân viên thay vì trợ lý AI.',
            idempotency_key: `declined:${msgId}`,
          }, now).stmts,
          auditStatement(env, { actor_type: 'zalo', actor_id: customer.id, action: 'consent.ai_assistant.declined', entity: 'conversation', entity_id: conv.id }, now),
        ]);
        await this.sendFixed(conv, customer, STAFF_WILL_REPLY_TEXT, now);
        return { conversation_id: conv.id, message_id: msgId, action: 'consent_recorded' };
      }
      if (conv.bot_state === 'staff_only') {
        await db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id).run();
        return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
      }
      if (customer.minor_flag === 1) {
        await db.prepare("UPDATE conversations SET bot_state = 'blocked', needs_attention = 1 WHERE id = ?").bind(conv.id).run();
        await createHandoff(env, { conversation_id: conv.id, customer_id: customer.id, source: 'server', reason_code: 'minor_flag', urgency: 'normal', idempotency_key: `minor:${conv.id}` }, now);
        return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
      }
      // Personal channel: no prompt to someone the account owner wrote to first from the phone (a personal contact,
      // or a customer staff already handles); staff sees the message instead.
      if (personal && (await this.ownerStartedConversation(conv.id))) {
        await db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id).run();
        return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
      }
      // Personal channel: the prompt stays 'pending' until the bridge reports, and 'unknown' when the send timed out
      // (it most likely arrived); neither may be queued again. Staff resends an unknown prompt with requeue.
      const lastPrompt = await db.prepare(
        "SELECT MAX(created_at) AS t FROM messages WHERE conversation_id = ? AND direction = 'outbound' AND source = 'server' AND kind = 'buttons' AND " +
          (personal ? "send_state IN ('sent','pending','unknown')" : "send_state = 'sent'"),
      )
        .bind(conv.id)
        .first<{ t: number | null }>();
      const repeatMs = personal ? PERSONAL_CONSENT_PROMPT_REPEAT_MS : CONSENT_PROMPT_REPEAT_MS;
      if (!lastPrompt?.t || now - lastPrompt.t > repeatMs) {
        const buttons: ZaloButton[] = [
          { title: CONSENT_BUTTON_AGREE, type: 'oa.query.show', payload: CONSENT_PAYLOAD_AGREE },
          { title: CONSENT_BUTTON_STAFF, type: 'oa.query.show', payload: CONSENT_PAYLOAD_STAFF },
        ];
        const ok = await this.sendFixed(conv, customer, CONSENT_PROMPT_TEXT, now, buttons);
        if (ok) return { conversation_id: conv.id, message_id: msgId, action: 'consent_prompt_sent' };
      }
      await db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id).run();
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }

    if (conv.bot_state !== 'bot_active') {
      await db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id).run();
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }

    // ---- bot_active
    if (text === CONSENT_PAYLOAD_AGREE) {
      await db.prepare('UPDATE conversations SET answered_seq = MAX(answered_seq, ?) WHERE id = ?').bind(seq, conv.id).run();
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }
    if (reply === 'staff') {
      await db.batch([
        db.prepare("UPDATE conversations SET bot_state = 'handoff_requested', answered_seq = MAX(answered_seq, ?), updated_at = ? WHERE id = ?").bind(seq, now, conv.id),
        cancelQueuedDraftJobs(env, conv.id, 'handoff', now),
        ...handoffStatements(env, {
          conversation_id: conv.id,
          customer_id: customer.id,
          source: 'server',
          reason_code: 'customer_requested_human',
          urgency: 'normal',
          summary_for_staff: text === CONSENT_PAYLOAD_STAFF ? 'Khách bấm nút gặp nhân viên.' : 'Khách nhắn "gặp nhân viên".',
          idempotency_key: `button_staff:${msgId}`,
        }, now).stmts,
      ]);
      await cancelQueuedBotRows(env, conv.id, now);
      await this.sendFixed(conv, customer, STAFF_WILL_REPLY_TEXT, now);
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }
    if (!text) {
      // Image / sticker / file without text: the bot cannot read it.
      await createHandoff(env, {
        conversation_id: conv.id,
        customer_id: customer.id,
        source: 'server',
        reason_code: 'unsupported_message',
        urgency: 'normal',
        summary_for_staff: `Khách gửi ${event.message_kind}; trợ lý AI không xem được.`,
        idempotency_key: `unsupported:${msgId}`,
      }, now);
      return { conversation_id: conv.id, message_id: msgId, action: 'stored' };
    }
    const until = now + debounceMs(env);
    await db.batch([
      db.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(until, conv.id),
      db.prepare("UPDATE jobs SET stale = 1, updated_at = ? WHERE conversation_id = ? AND type = 'draft_reply' AND status = 'leased'").bind(now, conv.id),
    ]);
    await this.ctx.storage.setAlarm(until);
    return { conversation_id: conv.id, message_id: msgId, action: 'debounced' };
  }

  /**
   * A customer message that is already stored came in again (inbox_sweep retry after a failure part-way through
   * the first ingest, or a Zalo resend). If nothing covers it yet (no debounce alarm, no draft job created after
   * it, not answered), re-arm the debounce for an active bot and flag the conversation for staff, so a D1 error
   * between storing the message and setting the alarm cannot leave the question unseen.
   */
  private async recoverDuplicate(conv: ConversationRow, messageId: string, now: number, personal = false): Promise<IngestResult> {
    const db = this.env.DB;
    const done: IngestResult = { conversation_id: conv.id, message_id: messageId, action: 'stored' };
    // Internal contact (section 14.3): a stored message needs no recovery; nothing is flagged and no debounce starts.
    if (await conversationIsInternal(this.env, conv.id)) return { ...done, action: 'internal_contact' };
    const msg = await db.prepare('SELECT seq, created_at, text, kind FROM messages WHERE id = ?').bind(messageId).first<{ seq: number; created_at: number; text: string | null; kind: string }>();
    if (!msg || msg.seq <= cutoffSeq(conv)) return done;
    if ((await this.ctx.storage.getAlarm()) !== null) return done;
    const job = await db.prepare("SELECT id FROM jobs WHERE conversation_id = ? AND type = 'draft_reply' AND created_at >= ? LIMIT 1")
      .bind(conv.id, msg.created_at)
      .first<{ id: string }>();
    if (job) return done;
    const text = (msg.text ?? '').trim();
    // Personal channel: a non-text message carries a placeholder text ("[hình ảnh]"), which the bot does not answer.
    const botCanAnswer =
      conv.bot_state === 'bot_active' && msg.kind !== 'user_info' && !(personal && msg.kind !== 'text') && text && text !== CONSENT_PAYLOAD_AGREE && consentReplyOf(text, personal) !== 'staff';
    if (!botCanAnswer) {
      await db.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, conv.id).run();
      return done;
    }
    const until = now + debounceMs(this.env);
    await db.prepare('UPDATE conversations SET debounce_until = ? WHERE id = ?').bind(until, conv.id).run();
    await this.ctx.storage.setAlarm(until);
    return { ...done, action: 'debounced' };
  }

  /** Personal channel: the latest outbound message is a consent prompt, delivered (or unknown) within the last 24 h. */
  private async consentPromptAnswerable(conversationId: string, now: number): Promise<boolean> {
    const last = await this.env.DB.prepare(
      "SELECT source, kind, send_state, COALESCE(sent_at, created_at) AS t FROM messages WHERE conversation_id = ? AND direction = 'outbound' ORDER BY seq DESC LIMIT 1",
    )
      .bind(conversationId)
      .first<{ source: string; kind: string; send_state: string | null; t: number }>();
    return (
      !!last &&
      last.source === 'server' &&
      last.kind === 'buttons' &&
      (last.send_state === 'sent' || last.send_state === 'unknown') &&
      now - last.t <= PERSONAL_CONSENT_REPLY_WINDOW_MS
    );
  }

  /**
   * The first message of the conversation was written by staff (on the phone of the personal account), and staff has
   * not handed the conversation back to the bot since. A staff release (POST /staff/conversations/:id/release) is the
   * explicit "let the bot handle this contact" signal, so the consent prompt is allowed again after it.
   */
  private async ownerStartedConversation(conversationId: string): Promise<boolean> {
    const first = await this.env.DB.prepare('SELECT direction, source FROM messages WHERE conversation_id = ? ORDER BY seq ASC LIMIT 1')
      .bind(conversationId)
      .first<{ direction: string; source: string }>();
    if (!first || first.direction !== 'outbound' || first.source !== 'staff') return false;
    const released = await this.env.DB.prepare(
      "SELECT 1 AS x FROM audit_log WHERE entity = 'conversation' AND entity_id = ? AND action = 'conversation.release' LIMIT 1",
    )
      .bind(conversationId)
      .first<{ x: number }>();
    return !released;
  }

  /** Debounce alarm: when DEBOUNCE_MS passed since the last customer message, enqueue a draft_reply job. */
  override async alarm(): Promise<void> {
    return this.serial(() => this._alarm());
  }

  private async _alarm(): Promise<void> {
    const id = await this.ctx.storage.get<string>('conversation_id');
    if (!id) return;
    const conv = await getConversation(this.env, id);
    if (!conv) return;
    const now = Date.now();
    if (conv.debounce_until && conv.debounce_until > now) {
      await this.ctx.storage.setAlarm(conv.debounce_until);
      return;
    }
    await enqueueDraftJob(this.env, id, now);
  }

  // ---------------------------------------------------------------- drafts

  /** Called by POST /runner/jobs/:id/draft: re-reads flags + bot_state, runs the checker, then queues for
   *  staff or auto-sends (effective mode auto_allowed + checker passed + no handoff in this job). */
  private async _acceptDraft(jobId: string, runnerId: string, draft: RunnerDraftRequest): Promise<DraftAcceptResult> {
    const env = this.env;
    const db = env.DB;
    const now = Date.now();
    const job = await getJob(env, jobId);
    if (!job || job.type !== 'draft_reply' || !job.conversation_id) throw new HttpError(404, 'not_found', 'job not found');
    if (job.lease_owner !== runnerId) {
      throw job.status === 'leased' ? new HttpError(409, 'lease_not_owned', 'job is leased by another runner') : new HttpError(409, 'job_not_leased', `job is ${job.status}`);
    }
    await this.rememberConversation(job.conversation_id);
    const payload = parsePayload(job);

    // Session + usage are recorded even for a late draft (accounting, and the runner's session really advanced).
    const given = payload.session_id_given ?? null;
    const newSession = draft.error_kind === 'session_restarted' || !given || given !== draft.session_id;
    const u = draft.usage;
    await db.prepare(
      'UPDATE conversations SET session_id = ?, ' +
        (newSession ? 'session_turns = 1, session_started_at = ?, catalog_version = ?, ' : 'session_turns = session_turns + 1, ') +
        'session_last_turn_at = ?, session_reset_reason = CASE WHEN session_reset_reason IS ? THEN NULL ELSE session_reset_reason END, ' +
        'total_input_tokens = total_input_tokens + ?, total_output_tokens = total_output_tokens + ?, total_cache_read_tokens = total_cache_read_tokens + ?, ' +
        'total_cache_write_tokens = total_cache_write_tokens + ?, total_cost_usd_equiv = total_cost_usd_equiv + ?, updated_at = ? WHERE id = ?',
    )
      .bind(
        draft.session_id,
        ...(newSession ? [now, payload.catalog_version ?? null] : []),
        now,
        payload.session_reset_reason ?? null,
        u.input_tokens,
        u.output_tokens,
        u.cache_read_input_tokens,
        u.cache_creation_input_tokens,
        draft.cost_usd_equiv,
        now,
        job.conversation_id,
      )
      .run();

    if (job.status !== 'leased') {
      if (job.last_error === 'lease_expired') throw new HttpError(409, 'lease_expired', 'lease expired; draft not stored');
      throw new HttpError(409, 'job_not_leased', `job is ${job.status}`, { status: job.status });
    }
    if ((job.lease_until ?? 0) <= now) throw new HttpError(409, 'lease_expired', 'lease expired; draft not stored');

    const { conv, customer } = await this.load(job.conversation_id);
    const cv = payload.catalog_version ?? conv.catalog_version ?? '';
    const newer = await db.prepare(
      "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND direction = 'inbound' AND source = 'customer' AND kind != 'user_info' AND seq > ?",
    )
      .bind(conv.id, payload.up_to_seq ?? 0)
      .first<{ n: number }>();
    const superseded = !!job.stale || (newer?.n ?? 0) > 0;
    // Menu images the model attached in this job (attach_menu_images); checked with the text.
    const attachments = await attachmentsForJob(env, job.id);
    const checker: CheckerResult = await checkConversationDraft(env, conv.id, cv, draft.text, now, attachments);
    const flags = await getFlags(env);
    const mode = conversationMode(flags, conv);
    // A draft with menu images always waits for staff, whatever the mode.
    const handedOff = (await jobHandedOff(env, job.id)) || attachments.length > 0;
    // Internal contact (section 14.3): the role was set while this job ran. The draft is discarded: it is never sent,
    // never shown to staff as waiting, and opens no handoff.
    const internal = isInternalRole((await getContactRole(env, customer.zalo_user_id))?.role);

    let status: DraftStatus;
    let action: DraftAcceptResult['action'];
    let autoSend = false;
    if (internal) {
      status = 'discarded';
      action = 'dropped';
    } else if (superseded) {
      status = 'superseded';
      action = 'dropped';
    } else if (mode === 'off') {
      status = 'discarded';
      action = 'dropped';
    } else if (!checker.passed) {
      status = 'blocked';
      action = 'queued_for_staff';
    } else if (
      mode === 'auto_allowed' &&
      conv.bot_state === 'bot_active' &&
      !handedOff &&
      flags.outbound_enabled &&
      !!customer.last_user_interaction_at &&
      now - customer.last_user_interaction_at <= CS_WINDOW_MS
    ) {
      status = 'approved';
      action = 'auto_sent';
      autoSend = true;
    } else {
      status = 'pending';
      action = 'queued_for_staff';
    }

    const draftId = newId('drf', now);
    const stmts: D1PreparedStatement[] = [
      db.prepare(
        'INSERT INTO drafts (id, job_id, conversation_id, text, final_text, status, checker_passed, checker_result_json, account_label, session_id, model, effort, usage_json, cost_usd_equiv, duration_ms, catalog_version, decided_by, decided_at, created_at) ' +
          'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
      ).bind(
        draftId,
        job.id,
        conv.id,
        draft.text,
        autoSend ? draft.text : null,
        status,
        checker.passed ? 1 : 0,
        JSON.stringify(checker),
        draft.account_label ?? null,
        draft.session_id,
        draft.model,
        draft.effort,
        JSON.stringify({ ...u, num_turns: draft.num_turns }),
        draft.cost_usd_equiv,
        draft.duration_ms,
        cv,
        autoSend ? 'auto' : null,
        autoSend ? now : null,
        now,
      ),
      db.prepare("UPDATE jobs SET status = 'done', result_json = ?, updated_at = ? WHERE id = ?").bind(JSON.stringify({ draft_id: draftId, status, action }), now, job.id),
    ];
    if (!superseded) stmts.push(db.prepare('UPDATE conversations SET answered_seq = MAX(answered_seq, ?) WHERE id = ?').bind(payload.up_to_seq ?? 0, conv.id));
    if (action === 'queued_for_staff') stmts.push(db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id));
    if (status === 'blocked' && mode === 'auto_allowed' && conv.bot_state === 'bot_active') {
      stmts.push(
        ...handoffStatements(env, {
          conversation_id: conv.id,
          customer_id: customer.id,
          job_id: job.id,
          source: 'server',
          reason_code: 'checker_blocked',
          urgency: 'normal',
          summary_for_staff: `Bản nháp không qua bước kiểm trước khi gửi: ${checker.issues.map((i) => i.rule).join(', ')}`,
          idempotency_key: `checker:${job.id}`,
        }, now).stmts,
      );
    }
    if (attachments.length) stmts.push(db.prepare('UPDATE drafts SET attachments_json = ? WHERE id = ?').bind(JSON.stringify(attachments), draftId));
    stmts.push(auditStatement(env, { actor_type: 'runner', actor_id: runnerId, action: 'draft.accept', entity: 'draft', entity_id: draftId, after: { status, action } }, now));
    await db.batch(stmts);

    if (superseded && !internal) await enqueueDraftJob(env, conv.id, now, Math.max(now, conv.debounce_until ?? 0));

    let messageId: string | null = null;
    if (autoSend) {
      // bot_state / outbound may have changed (takeover, kill switch) while this call awaited D1 above.
      const fresh = await getConversation(env, conv.id);
      const freshFlags = await getFlags(env);
      if (await conversationIsInternal(env, conv.id)) {
        // The role manager / staff was set while this call awaited D1: nothing is sent and nothing waits for staff.
        autoSend = false;
        status = 'discarded';
        action = 'dropped';
        await db.prepare("UPDATE drafts SET status = 'discarded', final_text = NULL, decided_by = NULL, decided_at = NULL WHERE id = ? AND status = 'approved'").bind(draftId).run();
      } else if (!fresh || fresh.bot_state !== 'bot_active' || !freshFlags.outbound_enabled || conversationMode(freshFlags, fresh) !== 'auto_allowed') {
        autoSend = false;
        status = 'pending';
        action = 'queued_for_staff';
        await db.batch([
          db.prepare("UPDATE drafts SET status = 'pending', final_text = NULL, decided_by = NULL, decided_at = NULL WHERE id = ? AND status = 'approved'").bind(draftId),
          db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id),
        ]);
      }
    }
    if (autoSend) {
      const r = await this.deliver(
        conv,
        customer,
        { text: draft.text, source: 'bot', draftId, meta: { model: draft.model, account_label: draft.account_label, usage: u, cost_usd_equiv: draft.cost_usd_equiv, catalog_version: cv } },
        now,
      );
      messageId = r.message_id;
      if (r.outcome.ok) {
        status = 'sent';
        await db.prepare("UPDATE drafts SET status = 'sent', sent_message_id = ? WHERE id = ?").bind(r.message_id, draftId).run();
      } else if (!r.outcome.unknown) {
        status = 'send_failed';
        action = 'queued_for_staff';
        await db.batch([
          db.prepare("UPDATE drafts SET status = 'send_failed', sent_message_id = ? WHERE id = ?").bind(r.message_id, draftId),
          db.prepare('UPDATE conversations SET needs_attention = 1 WHERE id = ?').bind(conv.id),
        ]);
      } else {
        await db.prepare('UPDATE drafts SET sent_message_id = ? WHERE id = ?').bind(r.message_id, draftId).run();
      }
    }
    return { draft_id: draftId, status, checker, action, message_id: messageId, ...(attachments.length ? { attachments } : {}) };
  }

  /** Staff approves a pending/blocked draft (optionally edited). Re-runs the checker on the final text. */
  private async _approveDraft(draftId: string, staffId: string, opts: { text?: string; override_checker?: boolean; attachments?: string[] }): Promise<ApproveResult> {
    const env = this.env;
    const db = env.DB;
    const now = Date.now();
    const draft = await db.prepare('SELECT * FROM drafts WHERE id = ?').bind(draftId).first<DraftRow>();
    if (!draft) throw new HttpError(404, 'not_found', 'draft not found');
    await this.rememberConversation(draft.conversation_id);
    if (draft.status !== 'pending' && draft.status !== 'blocked') throw new HttpError(409, 'invalid_state', `draft is ${draft.status}`);
    const { conv, customer } = await this.load(draft.conversation_id);
    // Internal contact (section 14.3): a draft the bot wrote is never sent to a manager or a staff member. Staff can
    // still write to the contact themselves (POST /staff/conversations/:id/send).
    if (await conversationIsInternal(env, conv.id)) {
      throw new HttpError(409, 'invalid_state', 'the contact is internal (manager or staff); a bot draft is not sent to it');
    }
    const flags = await getFlags(env);
    if (conversationMode(flags, conv) === 'draft_only') {
      throw new HttpError(409, 'mode_draft_only', 'draft_only mode: send it yourself with POST /staff/conversations/:id/send');
    }
    const finalText = (opts.text ?? draft.text).trim();
    if (!finalText || finalText.length > MAX_SEND_CHARS) throw new HttpError(422, 'validation_failed', `text must be 1-${MAX_SEND_CHARS} characters`, { field: 'text' });
    // Menu images of the draft (opts.attachments: staff keeps only these; [] drops them all).
    const draftKeys = parseKeys((draft as DraftRow & { attachments_json?: string | null }).attachments_json);
    const imageKeys = opts.attachments ? draftKeys.filter((k) => opts.attachments!.includes(k)) : draftKeys;
    const checker = await checkConversationDraft(env, conv.id, draft.catalog_version ?? conv.catalog_version ?? '', finalText, now, imageKeys);
    if (!checker.passed && !opts.override_checker) {
      throw new HttpError(422, 'checker_failed', 'final text fails the pre-send checker', { checker });
    }
    await this.assertCanSend(conv, customer, now);
    const claimed = await db.batch([
      db.prepare("UPDATE drafts SET status = 'approved', final_text = ?, decided_by = ?, decided_at = ?, checker_passed = ?, checker_result_json = ? WHERE id = ? AND status IN ('pending','blocked')")
        .bind(finalText, staffId, now, checker.passed ? 1 : 0, JSON.stringify(checker), draftId),
      auditStatement(env, {
        actor_type: 'staff',
        actor_id: staffId,
        action: 'draft.approve',
        entity: 'draft',
        entity_id: draftId,
        after: { edited: finalText !== draft.text, override_checker: !checker.passed && !!opts.override_checker, ...(draftKeys.length ? { images: imageKeys.length } : {}) },
      }, now),
    ]);
    // Another approve / manual send of this draft won the conditional UPDATE while this call awaited D1.
    if (!(claimed[0]?.meta.changes ?? 0)) throw new HttpError(409, 'invalid_state', 'draft was already decided by another request');
    const r = await this.deliver(conv, customer, { text: finalText, source: finalText === draft.text ? 'bot' : 'staff', draftId, staffId, meta: { model: draft.model, account_label: draft.account_label, catalog_version: draft.catalog_version } }, now);
    if (r.outcome.ok) {
      await db.prepare("UPDATE drafts SET status = 'sent', sent_message_id = ? WHERE id = ?").bind(r.message_id, draftId).run();
    } else {
      await db.prepare('UPDATE drafts SET status = ?, sent_message_id = ? WHERE id = ?').bind(r.outcome.unknown ? 'approved' : 'send_failed', r.message_id, draftId).run();
    }
    // Menu images go after the text, in their own outbox row that waits for the text row (personal channel only).
    const images = imageKeys.length && r.outcome.ok ? await this.queueDraftImages(conv, customer, imageKeys, draftId, staffId, r.outbox_id, now) : undefined;
    this.throwSendError(r);
    return { draft_id: draftId, message_id: r.message_id, outbox_id: r.outbox_id, ...(images ? { images } : {}) };
  }

  /**
   * Menu images of an approved draft: a messages row (kind 'image', the staff-facing label as text, send_state
   * 'pending') and one cs_images outbox row that the bridge sends with `msg send-image` once the text row is sent.
   * Never throws: the text is already queued, so a refusal only flags the conversation for staff.
   */
  private async queueDraftImages(
    conv: ConversationRow,
    customer: CustomerRow,
    keys: string[],
    draftId: string,
    staffId: string,
    textOutboxId: string,
    now: number,
  ): Promise<NonNullable<ApproveResult['images']>> {
    const db = this.env.DB;
    if (!isPersonalUserId(customer.zalo_user_id)) {
      await db.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, conv.id).run();
      return { queued: false, reason: 'channel_not_supported' };
    }
    const id = newId('msg', now);
    try {
      await db.prepare(
        "INSERT INTO messages (id, conversation_id, direction, source, kind, text, attachments_json, staff_id, send_state, client_send_id, created_at, seq) VALUES (?,?,'outbound','bot','image',?,?,?,'pending',?,?,(SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?))",
      )
        .bind(id, conv.id, menuImagesLabel(keys), JSON.stringify(menuAttachments(keys)), staffId, `img_${id}`, now, conv.id)
        .run();
      const q = await queuePersonalImages(
        this.env,
        { conversation_id: conv.id, customer_id: customer.id, zalo_user_id: customer.zalo_user_id, message_id: id, keys, depends_on: textOutboxId || null, dedupe_key: `img:${draftId}`, draft_id: draftId },
        now,
      );
      return { outbox_id: q.outbox_id, message_id: id, keys: q.keys };
    } catch (e) {
      await db.batch([
        db.prepare("UPDATE messages SET send_state = 'failed', send_error = ? WHERE id = ? AND send_state = 'pending'").bind(`not queued: ${(e as Error).message ?? 'error'}`.slice(0, 300), id),
        db.prepare('UPDATE conversations SET needs_attention = 1, updated_at = ? WHERE id = ?').bind(now, conv.id),
      ]);
      return { queued: false, reason: (e as Error).message?.slice(0, 120) ?? 'error' };
    }
  }

  /** Staff manual send. Writes messages(send_state='pending') before calling the Zalo client. */
  private async _sendStaffText(args: { text: string; staffId: string; draftId?: string; keepBotActive?: boolean; conversationId?: string }): Promise<{ message_id: string; outbox_id: string }> {
    const env = this.env;
    const db = env.DB;
    const now = Date.now();
    const cid = await this.resolveConversationId(args.conversationId);
    const { conv, customer } = await this.load(cid);
    const text = (args.text ?? '').trim();
    if (!text || text.length > MAX_SEND_CHARS) throw new HttpError(422, 'validation_failed', `text must be 1-${MAX_SEND_CHARS} characters`, { field: 'text' });
    let draft: DraftRow | null = null;
    if (args.draftId) {
      draft = await db.prepare('SELECT * FROM drafts WHERE id = ? AND conversation_id = ?').bind(args.draftId, cid).first<DraftRow>();
      if (!draft) throw new HttpError(404, 'not_found', 'draft not found in this conversation');
      if (draft.status === 'sent') throw new HttpError(409, 'invalid_state', 'draft already sent');
    }
    await this.assertCanSend(conv, customer, now);
    if (draft) {
      // Atomic claim: an approve (or another manual send) of the same draft in flight holds status 'approved'.
      const r = await db.prepare("UPDATE drafts SET status = 'approved', final_text = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status NOT IN ('sent','approved')")
        .bind(text, args.staffId, now, draft.id)
        .run();
      if (!(r.meta.changes ?? 0)) throw new HttpError(409, 'invalid_state', 'draft is already being sent or was sent');
    }
    const stmts: D1PreparedStatement[] = [
      db.prepare('UPDATE conversations SET answered_seq = MAX(answered_seq, ?), updated_at = ? WHERE id = ?').bind(await this.maxCustomerSeq(cid), now, cid),
      auditStatement(env, { actor_type: 'staff', actor_id: args.staffId, action: 'message.manual_send', entity: 'conversation', entity_id: cid, after: { from_draft_id: args.draftId ?? null, keep_bot_active: !!args.keepBotActive } }, now),
    ];
    if (!args.keepBotActive && conv.bot_state !== 'staff_only') {
      stmts.push(
        db.prepare("UPDATE conversations SET bot_state = 'staff_takeover', takeover_by = ?, takeover_until = ?, updated_at = ? WHERE id = ?")
          .bind(args.staffId, now + envInt(env.TAKEOVER_DEFAULT_MS, 43_200_000), now, cid),
        cancelQueuedDraftJobs(env, cid, 'takeover', now),
      );
    }
    await db.batch(stmts);
    if (!args.keepBotActive && conv.bot_state !== 'staff_only') await cancelQueuedBotRows(env, cid, now);
    const r = await this.deliver(conv, customer, { text, source: 'staff', draftId: args.draftId ?? null, staffId: args.staffId }, now);
    if (draft) {
      await db.prepare('UPDATE drafts SET status = ?, sent_message_id = ? WHERE id = ?')
        .bind(r.outcome.ok ? 'sent' : r.outcome.unknown ? 'approved' : 'send_failed', r.message_id, draft.id)
        .run();
    }
    this.throwSendError(r);
    return { message_id: r.message_id, outbox_id: r.outbox_id };
  }

  private async _takeover(staffId: string, until: number, conversationId?: string): Promise<void> {
    const now = Date.now();
    const cid = await this.resolveConversationId(conversationId);
    const { conv } = await this.load(cid);
    if (conv.bot_state === 'blocked') throw new HttpError(409, 'invalid_state', 'conversation is blocked');
    await this.env.DB.batch([
      this.env.DB.prepare("UPDATE conversations SET bot_state = 'staff_takeover', takeover_by = ?, takeover_until = ?, updated_at = ? WHERE id = ?").bind(staffId, until, now, cid),
      cancelQueuedDraftJobs(this.env, cid, 'takeover', now),
      auditStatement(this.env, { actor_type: 'staff', actor_id: staffId, action: 'conversation.takeover', entity: 'conversation', entity_id: cid, before: { bot_state: conv.bot_state }, after: { bot_state: 'staff_takeover', until } }, now),
    ]);
    await cancelQueuedBotRows(this.env, cid, now);
  }

  /**
   * Staff marks a contact as not a customer (family, friend, another account) or as handled by staff only:
   * bot_state = 'staff_only' without a handoff. The bot never drafts for it, no consent prompt is sent, and queued
   * automatic messages of the conversation (bot replies, a waiting consent prompt) are cancelled.
   */
  private async _markStaffOnly(staffId: string, conversationId?: string): Promise<void> {
    const now = Date.now();
    const cid = await this.resolveConversationId(conversationId);
    const { conv } = await this.load(cid);
    if (conv.bot_state === 'blocked') throw new HttpError(409, 'invalid_state', 'conversation is blocked');
    await this.env.DB.batch([
      this.env.DB.prepare(
        "UPDATE conversations SET bot_state = 'staff_only', takeover_by = NULL, takeover_until = NULL, session_id = NULL, session_reset_reason = 'released_by_staff', debounce_until = NULL, updated_at = ? WHERE id = ?",
      ).bind(now, cid),
      cancelQueuedDraftJobs(this.env, cid, 'staff_only', now),
      auditStatement(this.env, { actor_type: 'staff', actor_id: staffId, action: 'conversation.staff_only', entity: 'conversation', entity_id: cid, before: { bot_state: conv.bot_state }, after: { bot_state: 'staff_only' } }, now),
    ]);
    await cancelQueuedBotRows(this.env, cid, now, { alsoServer: true, reason: 'cancelled: marked staff_only by staff' });
    await this.ctx.storage.deleteAlarm();
    await refreshNeedsAttention(this.env, cid, now);
  }

  private async _release(staffId: string, conversationId?: string): Promise<void> {
    const now = Date.now();
    const cid = await this.resolveConversationId(conversationId);
    const { conv, customer } = await this.load(cid);
    // staff_only can be released too: it undoes "mark staff_only" (POST /staff/conversations/:id/staff-only).
    if (conv.bot_state !== 'staff_takeover' && conv.bot_state !== 'handoff_requested' && conv.bot_state !== 'staff_only') {
      throw new HttpError(409, 'invalid_state', `conversation is ${conv.bot_state}, not taken over`);
    }
    const consent = (await consentStatus(this.env, customer.id)).ai_assistant?.status === 'granted';
    const next = consent ? 'bot_active' : 'awaiting_consent';
    await this.env.DB.batch([
      this.env.DB.prepare(
        "UPDATE conversations SET bot_state = ?, takeover_by = NULL, takeover_until = NULL, session_id = NULL, session_reset_reason = 'released_by_staff', answered_seq = MAX(answered_seq, ?), updated_at = ? WHERE id = ?",
      ).bind(next, await this.maxCustomerSeq(cid), now, cid),
      this.env.DB.prepare("UPDATE handoffs SET status = 'resolved', resolved_by = ?, resolved_at = ? WHERE conversation_id = ? AND status = 'open'").bind(staffId, now, cid),
      auditStatement(this.env, { actor_type: 'staff', actor_id: staffId, action: 'conversation.release', entity: 'conversation', entity_id: cid, before: { bot_state: conv.bot_state }, after: { bot_state: next } }, now),
    ]);
    // Pending / blocked drafts still need staff after the bot takes over again.
    await refreshNeedsAttention(this.env, cid, now);
  }

  // ---------------------------------------------------------------- RPC surface (prototype methods; errors encoded for the caller)

  async ingestEvent(event: NormalizedEvent): Promise<IngestResult> {
    try {
      return await this.serial(() => this._ingestEvent(event));
    } catch (e) {
      throw toRpcError(e);
    }
  }

  async acceptDraft(jobId: string, runnerId: string, draft: RunnerDraftRequest): Promise<DraftAcceptResult | RpcFailure> {
    try {
      return await this.serial(() => this._acceptDraft(jobId, runnerId, draft));
    } catch (e) {
      return toRpcFailure(e);
    }
  }

  async approveDraft(draftId: string, staffId: string, opts: { text?: string; override_checker?: boolean; attachments?: string[] }): Promise<ApproveResult | RpcFailure> {
    try {
      return await this.serial(() => this._approveDraft(draftId, staffId, opts));
    } catch (e) {
      return toRpcFailure(e);
    }
  }

  async sendStaffText(args: { text: string; staffId: string; draftId?: string; keepBotActive?: boolean; conversationId?: string }): Promise<{ message_id: string; outbox_id: string } | RpcFailure> {
    try {
      return await this.serial(() => this._sendStaffText(args));
    } catch (e) {
      return toRpcFailure(e);
    }
  }

  async takeover(staffId: string, until: number, conversationId?: string): Promise<void | RpcFailure> {
    try {
      return await this.serial(() => this._takeover(staffId, until, conversationId));
    } catch (e) {
      return toRpcFailure(e);
    }
  }

  async release(staffId: string, conversationId?: string): Promise<void | RpcFailure> {
    try {
      return await this.serial(() => this._release(staffId, conversationId));
    } catch (e) {
      return toRpcFailure(e);
    }
  }

  async markStaffOnly(staffId: string, conversationId?: string): Promise<void | RpcFailure> {
    try {
      return await this.serial(() => this._markStaffOnly(staffId, conversationId));
    } catch (e) {
      return toRpcFailure(e);
    }
  }
}
