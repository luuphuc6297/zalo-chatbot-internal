// Staff endpoints of docs/contracts.md section 15.11: customer facts guessed from old chats (src/lib/chat-facts.ts).
//
//   POST /staff/chat-facts/import                          scripts/analyze_visits.py --push (X-Staff-Id: chat-analyzer)
//   GET  /staff/chat-facts/eligible                        contacts the analyzer's model pass may read (consent)
//   GET  /staff/chat-facts/:zalo_user_id                   every stored guess of one contact
//   POST /staff/chat-facts/visits/:id/confirm | dismiss
//   POST /staff/chat-facts/benefits/:id/confirm | dismiss
//   POST /staff/chat-facts/:zalo_user_id/phone/accept | dismiss
//
// Every endpoint answers 409 invalid_state before migration 0011 is applied. No endpoint sends a message or creates a
// draft or follow-up job.
import type { Context } from 'hono';
import type { AppEnv } from '../types';
import { HttpError } from '../lib/http';
import {
  MAX_IMPORT_BYTES,
  acceptPhoneSuggestion,
  confirmChatBenefit,
  confirmChatVisit,
  dismissChatBenefit,
  dismissChatVisit,
  dismissPhoneSuggestion,
  eligibleContacts,
  getChatFacts,
  importChatFacts,
  mustChatContactId,
} from '../lib/chat-facts';
import { readTextCapped } from './profiles';

type H = (c: Context<AppEnv>) => Promise<Response>;
const staffId = (c: Context<AppEnv>) => c.get('staffId') ?? 'staff';

/** The JSON body, or undefined for an empty body (the decision bodies are optional). 400 for text that is not JSON. */
async function optionalJson(c: Context<AppEnv>, max = 100_000): Promise<unknown> {
  const raw = await readTextCapped(c.req.raw, max);
  if (!raw.trim()) return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    throw new HttpError(400, 'bad_request', 'body must be JSON');
  }
}

export const importHandler: H = async (c) => {
  const body = await optionalJson(c, MAX_IMPORT_BYTES);
  if (body === undefined) throw new HttpError(400, 'bad_request', 'body must be JSON');
  return c.json(await importChatFacts(c.env, body, staffId(c)));
};

export const eligibleHandler: H = async (c) => c.json({ zalo_user_ids: await eligibleContacts(c.env) });

const contactId = (c: Context<AppEnv>) => mustChatContactId(c.req.param('zalo_user_id') ?? '');

export const getHandler: H = async (c) => c.json({ facts: await getChatFacts(c.env, contactId(c)) });

export const confirmVisitHandler: H = async (c) => c.json(await confirmChatVisit(c.env, c.req.param('id') ?? '', await optionalJson(c), staffId(c)));

export const dismissVisitHandler: H = async (c) => c.json(await dismissChatVisit(c.env, c.req.param('id') ?? '', staffId(c)));

export const confirmBenefitHandler: H = async (c) => c.json(await confirmChatBenefit(c.env, c.req.param('id') ?? '', await optionalJson(c), staffId(c)));

export const dismissBenefitHandler: H = async (c) => c.json(await dismissChatBenefit(c.env, c.req.param('id') ?? '', staffId(c)));

export const acceptPhoneHandler: H = async (c) => c.json(await acceptPhoneSuggestion(c.env, contactId(c), staffId(c)));

export const dismissPhoneHandler: H = async (c) => c.json(await dismissPhoneSuggestion(c.env, contactId(c), staffId(c)));
