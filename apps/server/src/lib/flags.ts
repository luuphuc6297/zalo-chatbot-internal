// Owner: server-core. Kill switches live in table `flags` (value_json). Read from D1 on every decision, no cache.
import type { ConversationMode, Env, FlagName, Flags, FlagsResponse, PutFlagsRequest } from '../types';
import { MODE_ORDER } from '../types';
import { HttpError } from './http';
import { auditStatement } from './audit';

export const DEFAULT_FLAGS: Flags = {
  auto_reply_mode: 'approve_each',
  ai_calls_enabled: true,
  ai_engine: 'subscription',
  scheduled_sends_enabled: false,
  outbound_enabled: true,
  promotions_enabled: false,
  runner_desired_account: 'auto',
  profile_personal_skip_bot: true,
  rooms_enabled: false,
};

const FLAG_NAMES = Object.keys(DEFAULT_FLAGS) as FlagName[];
const ACCOUNT_LABEL_RE = /^[A-Za-z0-9._@+-]{1,64}$/;

/** Returns the parsed value when valid for that flag, else undefined. */
export function validateFlag(name: string, value: unknown): Flags[FlagName] | undefined {
  switch (name) {
    case 'auto_reply_mode':
      return typeof value === 'string' && (MODE_ORDER as string[]).includes(value) ? (value as ConversationMode) : undefined;
    case 'ai_engine':
      return value === 'subscription' || value === 'api_key' || value === 'off' ? value : undefined;
    case 'ai_calls_enabled':
    case 'scheduled_sends_enabled':
    case 'outbound_enabled':
    case 'promotions_enabled':
    case 'profile_personal_skip_bot':
    case 'rooms_enabled':
      return typeof value === 'boolean' ? value : undefined;
    case 'runner_desired_account':
      return typeof value === 'string' && (value === 'auto' || ACCOUNT_LABEL_RE.test(value)) ? value : undefined;
    default:
      return undefined;
  }
}

interface FlagRow {
  name: string;
  value_json: string;
  updated_by: string;
  updated_at: number;
}

async function readRows(env: Env): Promise<FlagRow[]> {
  const { results } = await env.DB.prepare('SELECT name, value_json, updated_by, updated_at FROM flags').all<FlagRow>();
  return results;
}

function rowsToFlags(rows: FlagRow[]): Flags {
  const flags: Flags = { ...DEFAULT_FLAGS };
  for (const r of rows) {
    let v: unknown;
    try {
      v = JSON.parse(r.value_json);
    } catch {
      continue;
    }
    const ok = validateFlag(r.name, v);
    if (ok !== undefined) (flags as unknown as Record<string, unknown>)[r.name] = ok;
  }
  return flags;
}

export async function getFlags(env: Env): Promise<Flags> {
  return rowsToFlags(await readRows(env));
}

export async function getFlagsWithMeta(env: Env): Promise<FlagsResponse> {
  const rows = await readRows(env);
  const updated: FlagsResponse['updated'] = {};
  for (const r of rows) {
    if ((FLAG_NAMES as string[]).includes(r.name) && r.updated_at > 0) {
      updated[r.name as FlagName] = { by: r.updated_by, at: r.updated_at };
    }
  }
  return { flags: rowsToFlags(rows), updated };
}

/** Validates every key, writes changed values, one audit_log row per changed flag. */
export async function putFlags(env: Env, patch: PutFlagsRequest, staffId: string, now = Date.now()): Promise<FlagsResponse> {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    throw new HttpError(422, 'validation_failed', 'body must be an object of flags');
  }
  const before = await getFlags(env);
  const stmts: D1PreparedStatement[] = [];
  for (const [name, value] of Object.entries(patch)) {
    if (!(FLAG_NAMES as string[]).includes(name)) {
      throw new HttpError(422, 'validation_failed', `unknown flag ${name}`, { field: name });
    }
    const v = validateFlag(name, value);
    if (v === undefined) throw new HttpError(422, 'validation_failed', `bad value for ${name}`, { field: name });
    if (before[name as FlagName] === v) continue;
    stmts.push(
      env.DB.prepare(
        'INSERT INTO flags (name, value_json, updated_by, updated_at) VALUES (?,?,?,?) ' +
          'ON CONFLICT(name) DO UPDATE SET value_json = excluded.value_json, updated_by = excluded.updated_by, updated_at = excluded.updated_at',
      ).bind(name, JSON.stringify(v), staffId, now),
      auditStatement(env, {
        actor_type: 'staff',
        actor_id: staffId,
        action: 'flag.set',
        entity: 'flag',
        entity_id: name,
        before: before[name as FlagName],
        after: v,
      }, now),
    );
  }
  if (stmts.length) await env.DB.batch(stmts);
  return getFlagsWithMeta(env);
}

/** Effective mode = the lower of the global flag and the per-conversation override (off < draft_only < approve_each < auto_allowed). */
export function effectiveMode(global: ConversationMode, override: ConversationMode | null): ConversationMode {
  if (!override) return global;
  return MODE_ORDER[Math.min(MODE_ORDER.indexOf(global), MODE_ORDER.indexOf(override))]!;
}

/**
 * The mode of one conversation (docs/contracts.md section 14.4). Replaces every direct
 * `effectiveMode(flags.auto_reply_mode, conv.mode)` call:
 *   1. global flag auto_reply_mode = 'off': 'off' (the global stop always wins);
 *   2. conversations.auto_reply = 'on': 'auto_allowed', whatever the global flag (other than off) and conv.mode say;
 *   3. auto_reply = 'off': the lower of effectiveMode(global, conv.mode) and 'approve_each';
 *   4. auto_reply NULL: effectiveMode(global, conv.mode), unchanged.
 * A row read before migration 0010 has no auto_reply column (undefined) and counts as NULL.
 */
export function conversationMode(
  flags: Pick<Flags, 'auto_reply_mode'>,
  conv: { mode: ConversationMode | null; auto_reply?: 'on' | 'off' | null },
): ConversationMode {
  if (flags.auto_reply_mode === 'off') return 'off';
  if (conv.auto_reply === 'on') return 'auto_allowed';
  const base = effectiveMode(flags.auto_reply_mode, conv.mode);
  if (conv.auto_reply === 'off') return effectiveMode(base, 'approve_each');
  return base;
}

/** true when the model may be called at all (ai_calls_enabled and ai_engine=subscription). */
export function aiCallsAllowed(flags: Flags): boolean {
  return flags.ai_calls_enabled && flags.ai_engine === 'subscription';
}
