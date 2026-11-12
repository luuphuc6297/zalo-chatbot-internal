// Owner: server-core. Runner API (docs/contracts.md "Runner API"). Auth by requireRunner (Bearer RUNNER_TOKEN + X-Runner-Id).
import type { Context } from 'hono';
import type { AppEnv, RunnerDraftRequest, RunnerErrorKind, RunnerFailRequest, RunnerStatusRequest, RunnerStatusResponse, RunnerToolResponse } from '../types';
import { HttpError, readJson, rpc } from '../lib/http';
import { getFlags } from '../lib/flags';
import { buildPrompt } from '../lib/prompt';
import { conversationStub } from '../lib/do';
import { claimNext, failDraftJob, heartbeat, loadLeasedJob } from '../jobs/draft-jobs';
import { isToolName, runAndStoreTool } from '../tools';
import { parsePayload } from '../lib/db';

type H = (c: Context<AppEnv>) => Promise<Response>;

const ERROR_KINDS: RunnerErrorKind[] = [
  'login_expired', 'limited', 'blocked', 'no_account', 'timeout', 'session_broken', 'model_error', 'empty_output', 'refusal', 'cancelled', 'internal',
];

const runnerId = (c: Context<AppEnv>) => c.get('runnerId')!;
const bad = (field: string, message = `invalid ${field}`) => new HttpError(422, 'validation_failed', message, { field });
const isNum = (v: unknown) => typeof v === 'number' && Number.isFinite(v) && v >= 0;

/** POST /runner/jobs/claim */
export const claimJob: H = async (c) => {
  await readJson<Record<string, unknown>>(c).catch(() => ({}));
  return c.json(await claimNext(c.env, runnerId(c), Date.now()));
};

/** POST /runner/jobs/:id/heartbeat */
export const heartbeatJob: H = async (c) => {
  return c.json(await heartbeat(c.env, c.req.param('id')!, runnerId(c), Date.now()));
};

function validateDraft(b: unknown): RunnerDraftRequest {
  if (!b || typeof b !== 'object') throw bad('$', 'body must be an object');
  const d = b as Record<string, unknown>;
  if (typeof d.text !== 'string' || !d.text.trim()) throw bad('text', 'text is empty; use /fail with empty_output');
  if (d.text.length > 10_000) throw bad('text', 'text too long');
  if (typeof d.session_id !== 'string' || !/^[A-Za-z0-9._-]{1,128}$/.test(d.session_id)) throw bad('session_id');
  if (d.account_label !== null && d.account_label !== undefined && typeof d.account_label !== 'string') throw bad('account_label');
  if (typeof d.model !== 'string') throw bad('model');
  if (typeof d.effort !== 'string') throw bad('effort');
  const u = d.usage as Record<string, unknown> | undefined;
  if (!u || !['input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'].every((k) => isNum(u[k]))) throw bad('usage');
  if (!isNum(d.cost_usd_equiv)) throw bad('cost_usd_equiv');
  if (!isNum(d.duration_ms)) throw bad('duration_ms');
  if (!isNum(d.num_turns)) throw bad('num_turns');
  if (d.error_kind !== null && d.error_kind !== undefined && d.error_kind !== 'session_restarted') throw bad('error_kind');
  return {
    text: d.text.trim(),
    session_id: d.session_id,
    account_label: (d.account_label as string | null | undefined) ?? null,
    model: d.model,
    effort: d.effort,
    usage: {
      input_tokens: u.input_tokens as number,
      output_tokens: u.output_tokens as number,
      cache_read_input_tokens: u.cache_read_input_tokens as number,
      cache_creation_input_tokens: u.cache_creation_input_tokens as number,
    },
    cost_usd_equiv: d.cost_usd_equiv as number,
    duration_ms: d.duration_ms as number,
    num_turns: d.num_turns as number,
    error_kind: (d.error_kind as 'session_restarted' | null | undefined) ?? null,
  };
}

/** POST /runner/jobs/:id/draft */
export const submitDraft: H = async (c) => {
  const body = validateDraft(await readJson(c));
  const jobId = c.req.param('id')!;
  const job = await c.env.DB.prepare("SELECT conversation_id FROM jobs WHERE id = ? AND type = 'draft_reply'").bind(jobId).first<{ conversation_id: string }>();
  if (!job) throw new HttpError(404, 'not_found', 'job not found');
  const stub = await conversationStub(c.env, job.conversation_id);
  return c.json(await rpc(stub.acceptDraft(jobId, runnerId(c), body)));
};

/** POST /runner/jobs/:id/fail */
export const failJob: H = async (c) => {
  const b = await readJson<Partial<RunnerFailRequest>>(c);
  if (!b || typeof b !== 'object') throw bad('$');
  if (!ERROR_KINDS.includes(b.error_kind as RunnerErrorKind)) throw bad('error_kind');
  const body: RunnerFailRequest = {
    error_kind: b.error_kind as RunnerErrorKind,
    error_message: typeof b.error_message === 'string' ? b.error_message.slice(0, 500) : '',
    account_label: typeof b.account_label === 'string' ? b.account_label.slice(0, 64) : null,
    session_id: typeof b.session_id === 'string' ? b.session_id.slice(0, 128) : null,
    session_broken: b.session_broken === true,
    ...(b.usage ? { usage: b.usage } : {}),
    ...(isNum(b.cost_usd_equiv) ? { cost_usd_equiv: b.cost_usd_equiv } : {}),
  };
  return c.json(await failDraftJob(c.env, c.req.param('id')!, runnerId(c), body, Date.now()));
};

/** POST /runner/tools/:name */
export const callTool: H = async (c) => {
  const name = c.req.param('name')!;
  if (!isToolName(name)) throw new HttpError(404, 'unknown_tool', `unknown tool ${name}`);
  const b = await readJson<{ job_id?: unknown; input?: unknown }>(c);
  if (!b || typeof b.job_id !== 'string') throw new HttpError(400, 'bad_request', 'job_id required');
  const now = Date.now();
  const job = await loadLeasedJob(c.env, b.job_id, runnerId(c), now);
  const payload = parsePayload(job);
  // The conversation is always the job's own; nothing in the input can point elsewhere.
  const out = await runAndStoreTool(
    c.env,
    { job_id: job.id, conversation_id: job.conversation_id!, customer_id: job.customer_id!, catalog_version: payload.catalog_version ?? '', now },
    name,
    (b.input ?? {}) as Record<string, unknown>,
  );
  const res: RunnerToolResponse = { result: out.result, is_error: out.is_error, tool_call_id: out.tool_call_id, replayed: out.replayed };
  return c.json(res);
};

/** GET /runner/prompt */
export const getPrompt: H = async (c) => c.json(await buildPrompt(c.env));

/** POST /runner/status */
export const postStatus: H = async (c) => {
  const b = await readJson<Partial<RunnerStatusRequest>>(c);
  if (!b || typeof b !== 'object' || !Array.isArray(b.accounts)) throw bad('accounts');
  if (typeof b.runner_version !== 'string') throw bad('runner_version');
  const now = Date.now();
  const snapshot = JSON.stringify({ ...b, reported_at: isNum(b.reported_at) ? b.reported_at : now }).slice(0, 64_000);
  await c.env.DB.prepare('UPDATE runner_status SET last_status_at = ?, version = ?, snapshot_json = ? WHERE runner_id = ?')
    .bind(now, b.runner_version.slice(0, 32), snapshot, runnerId(c))
    .run();
  const flags = await getFlags(c.env);
  const res: RunnerStatusResponse = {
    ok: true,
    desired_account: flags.runner_desired_account,
    flags: { ai_calls_enabled: flags.ai_calls_enabled, ai_engine: flags.ai_engine, auto_reply_mode: flags.auto_reply_mode },
  };
  return c.json(res);
};
