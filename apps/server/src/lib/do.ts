// Owner: server-core. Finds the Conversation DO of an internal conversation id (cnv_ -> customer -> DO name).
import type { Env } from '../types';
import { conversationObjectName } from '../types';
import { HttpError } from './http';

export async function conversationStub(env: Env, conversationId: string) {
  const r = await env.DB.prepare('SELECT cu.oa_id, cu.zalo_user_id FROM conversations c JOIN customers cu ON cu.id = c.customer_id WHERE c.id = ?')
    .bind(conversationId)
    .first<{ oa_id: string; zalo_user_id: string }>();
  if (!r) throw new HttpError(404, 'not_found', 'conversation not found');
  return env.CONVERSATION.get(env.CONVERSATION.idFromName(conversationObjectName(r.oa_id, r.zalo_user_id)));
}
