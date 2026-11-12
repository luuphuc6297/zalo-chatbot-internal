// Owner: server-core. Builds CheckerInput from D1 for one conversation (the checker itself stays pure).
import type { CheckerInput, CheckerResult, Env } from '../types';
import { FACT_USABLE_STATUSES } from '../lib/prompt';
import { checkDraft } from './index';

function collectPriceTexts(v: unknown, out: Set<string>): void {
  if (Array.isArray(v)) v.forEach((x) => collectPriceTexts(x, out));
  else if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      if (k === 'price_text' && typeof x === 'string') out.add(x);
      else collectPriceTexts(x, out);
    }
  }
}

function collectStrings(v: unknown, out: string[]): void {
  if (typeof v === 'string') out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => collectStrings(x, out));
  else if (v && typeof v === 'object') Object.values(v as Record<string, unknown>).forEach((x) => collectStrings(x, out));
}

export async function buildCheckerInput(env: Env, conversationId: string, catalogVersion: string, text: string, attachmentKeys: string[] = []): Promise<CheckerInput> {
  const [calls, facts, names] = await env.DB.batch([
    env.DB.prepare('SELECT result_json FROM tool_calls WHERE conversation_id = ? AND catalog_version = ? AND is_error = 0').bind(conversationId, catalogVersion),
    env.DB.prepare('SELECT value_json, status FROM facts WHERE catalog_version = ?').bind(catalogVersion),
    env.DB.prepare('SELECT display_name_vi FROM services WHERE catalog_version = ?').bind(catalogVersion),
  ]);
  const prices = new Set<string>();
  for (const r of calls!.results as Array<{ result_json: string }>) {
    try {
      collectPriceTexts(JSON.parse(r.result_json), prices);
    } catch {
      /* ignore malformed rows */
    }
  }
  const contacts: string[] = [];
  for (const f of facts!.results as Array<{ value_json: string | null; status: string }>) {
    if (!FACT_USABLE_STATUSES.includes(f.status) || !f.value_json) continue;
    try {
      collectStrings(JSON.parse(f.value_json), contacts);
    } catch {
      /* ignore */
    }
  }
  return {
    text,
    conversation_id: conversationId,
    catalog_version: catalogVersion,
    allowed_price_texts: [...prices],
    approved_contact_values: contacts,
    display_names: (names!.results as Array<{ display_name_vi: string }>).map((r) => r.display_name_vi),
    ...(attachmentKeys.length ? { attachment_keys: attachmentKeys } : {}),
  };
}

/** attachmentKeys: menu image keys the draft would send after its text (menu images, src/checker/attachments.ts). */
export async function checkConversationDraft(
  env: Env,
  conversationId: string,
  catalogVersion: string,
  text: string,
  now: number,
  attachmentKeys: string[] = [],
): Promise<CheckerResult> {
  return checkDraft(await buildCheckerInput(env, conversationId, catalogVersion, text, attachmentKeys), now);
}
