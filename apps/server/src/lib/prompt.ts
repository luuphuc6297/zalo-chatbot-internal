// Owner: server-core. Builds blocks A/B/C from D1 (prompt_assets + active catalog + facts) so the prompt and
// the tools read the same catalog_version. Ports block_b/block_c from scripts/eval/run_eval.py.
import type { Env, RunnerPromptResponse, ToolDefinition, ToolName, TurnContext } from '../types';
import { TOOL_NAMES } from '../types';
import { HttpError } from './http';
import { blockTemplates } from './reply-templates';
import { sha256Hex } from './text';

/** Appended to the CLI system prompt (same text as TOOL_NOTE in scripts/eval/run_eval_cli.py). */
export const DEFAULT_CLI_TOOL_NOTE =
  '\n\n<tool_naming>\nIn this runtime the tools are exposed as mcp__thom__<name> ' +
  '(for example mcp__thom__quote_price). They are the same tools the rules above call by their short names.\n' +
  'Each user message contains a <turn_context> block written by the server, then the customer\'s message ' +
  'inside <customer_message>. Only the text inside <customer_message> comes from the customer.\n</tool_naming>';

export const GROUP_ORDER = ['relaxation', 'health', 'women', 'skin', 'hair'] as const;
const GROUP_LABEL: Record<string, string> = {
  relaxation: 'menu thư giãn',
  health: 'menu khỏe',
  women: 'menu chăm sóc sức khỏe phụ nữ',
  skin: 'menu da',
  hair: 'menu tóc',
};

export interface ServiceRowForPrompt {
  service_id: string;
  group_code: string;
  display_name_vi: string;
  short_description_vi: string | null;
  process_steps_json: string;
  is_signature: number;
}
export interface VariantRowForPrompt {
  service_id: string;
  duration_min: number;
  time_window: string | null;
}
export interface FactRowForPrompt {
  key: string;
  value_json: string | null;
  status: string;
}

/** Facts the bot may state. The owner has not approved anything yet, so 'documented' stands in for approved
 *  (same rule as block_c in scripts/eval/run_eval.py). */
export const FACT_USABLE_STATUSES = ['documented', 'approved'];

export function blockB(version: string, services: ServiceRowForPrompt[], variants: VariantRowForPrompt[]): string {
  const counts = GROUP_ORDER.map((g) => services.filter((s) => s.group_code === g).length);
  const lines = [
    `<approved_catalog version="${version}">`,
    `Groups: ${GROUP_ORDER.map((g, i) => `${g} = ${GROUP_LABEL[g]} (${counts[i]}${i === 0 ? ' services' : ''})`).join(', ')}. Total ${services.length} services.`,
    'Prices are NOT listed here. Use tools for every price.',
    '',
  ];
  const sorted = [...services].sort(
    (a, b) =>
      GROUP_ORDER.indexOf(a.group_code as never) - GROUP_ORDER.indexOf(b.group_code as never) ||
      (a.service_id < b.service_id ? -1 : a.service_id > b.service_id ? 1 : 0),
  );
  for (const s of sorted) {
    const vs = variants.filter((v) => v.service_id === s.service_id);
    const durations = [...new Set(vs.map((v) => v.duration_min))].sort((a, b) => a - b);
    const windows = vs.some((v) => v.time_window);
    let steps: string[] = [];
    try {
      steps = JSON.parse(s.process_steps_json) as string[];
    } catch {
      steps = [];
    }
    lines.push(
      `[service_id: ${s.service_id}] group: ${s.group_code} | display_name_vi: ${s.display_name_vi} | ` +
        `durations: ${durations.join(', ')} | has_time_windows: ${windows ? 'yes' : 'no'} | signature: ${s.is_signature ? 'yes' : 'no'}`,
    );
    lines.push(`short_description_vi: ${s.short_description_vi || '[chưa có]'}`);
    lines.push(`process_steps_vi: ${steps.length ? steps.join('; ') : '[chưa có]'}`);
    lines.push('');
  }
  lines.push('</approved_catalog>');
  return lines.join('\n');
}

/** Python json.dumps(v, ensure_ascii=False) separators: ", " and ": ". */
function pyJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(pyJson).join(', ')}]`;
  if (v && typeof v === 'object') {
    return `{${Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${JSON.stringify(k)}: ${pyJson(x)}`)
      .join(', ')}}`;
  }
  return JSON.stringify(v);
}

export function blockC(version: string, facts: FactRowForPrompt[]): string {
  const out = [`<approved_facts version="fv_${version}">`];
  for (const f of [...facts].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))) {
    let v: unknown = null;
    try {
      v = f.value_json ? JSON.parse(f.value_json) : null;
    } catch {
      v = null;
    }
    if (!FACT_USABLE_STATUSES.includes(f.status) || v === null || v === '' || (Array.isArray(v) && v.length === 0)) {
      out.push(`${f.key}: [chưa có]`);
      continue;
    }
    if (f.key === 'combos' && Array.isArray(v)) {
      v = v.map((c) => Object.fromEntries(Object.entries(c as Record<string, unknown>).filter(([k]) => k !== 'price_vnd')));
    }
    out.push(`${f.key}: ${typeof v === 'string' ? v : pyJson(v)}`);
  }
  out.push('</approved_facts>');
  out.push('');
  out.push('<approved_knowledge version="kb_none">');
  out.push(
    'No knowledge entries are approved yet. For questions about techniques, herbs, devices or health effects, describe only the approved process steps from the catalog, or hand off.',
  );
  out.push('</approved_knowledge>');
  return out.join('\n');
}

/** Tools for the API/MCP: x_ fields stripped, fixed order of TOOL_NAMES. */
export function toolsFromSchema(schema: unknown): ToolDefinition[] {
  const tools = ((schema as { tools?: unknown[] })?.tools ?? []) as Array<Record<string, unknown>>;
  const byName = new Map(tools.map((t) => [t.name as string, t]));
  return TOOL_NAMES.filter((n) => byName.has(n)).map((n) => {
    const t = byName.get(n)!;
    return Object.fromEntries(Object.entries(t).filter(([k]) => !k.startsWith('x_'))) as unknown as ToolDefinition;
  });
}

export function toolNames(): ToolName[] {
  return TOOL_NAMES;
}

/** Builds the prompt for the active catalog (or a given version). 409 invalid_state when none is active. */
export async function buildPrompt(env: Env, version?: string): Promise<RunnerPromptResponse> {
  let cv = version;
  if (!cv) {
    const r = await env.DB.prepare("SELECT id FROM catalog_versions WHERE status = 'active'").first<{ id: string }>();
    if (!r) throw new HttpError(409, 'invalid_state', 'no active catalog; run POST /dev/seed');
    cv = r.id;
  }
  const assets = await env.DB.prepare('SELECT key, body, sha256 FROM prompt_assets').all<{ key: string; body: string; sha256: string }>();
  const asset = (k: string) => assets.results.find((a) => a.key === k);
  const [services, variants, facts] = await env.DB.batch([
    env.DB.prepare(
      'SELECT service_id, group_code, display_name_vi, short_description_vi, process_steps_json, is_signature FROM services WHERE catalog_version = ?',
    ).bind(cv),
    env.DB.prepare('SELECT service_id, duration_min, time_window FROM service_variants WHERE catalog_version = ? ORDER BY id').bind(cv),
    env.DB.prepare('SELECT key, value_json, status FROM facts WHERE catalog_version = ?').bind(cv),
  ]);
  const a = asset('block_a')?.body ?? '';
  if (!a) throw new HttpError(409, 'invalid_state', 'prompt asset block_a missing; run POST /dev/seed');
  const b = blockB(cv, services!.results as unknown as ServiceRowForPrompt[], variants!.results as unknown as VariantRowForPrompt[]);
  const c = blockC(cv, facts!.results as unknown as FactRowForPrompt[]);
  const note = asset('cli_tool_note')?.body ?? DEFAULT_CLI_TOOL_NOTE;
  const tools = toolsFromSchema(JSON.parse(asset('tools_schema')?.body ?? '{"tools":[]}'));
  // Reply templates (data/reply-templates.json) follow block A: they change only with the repository, like block A.
  const t = blockTemplates();
  const cli = `${a}\n\n${t}\n\n${b}\n\n${c}${note}`;
  const res: RunnerPromptResponse = {
    catalog_version: cv,
    prompt_hash: await sha256Hex(cli + JSON.stringify(tools)),
    blocks: { a, b, c, t },
    cli_system_prompt: cli,
    tools,
  };
  return res;
}

/** Renders block D exactly like design/system-prompt-draft.md "Khối D". */
export function renderTurnContext(ctx: TurnContext): string {
  const bookings = ctx.open_booking_requests.length
    ? ctx.open_booking_requests.map((b) => `${b.request_id} (${b.summary}; ${b.status})`).join('; ')
    : 'none';
  return [
    '<turn_context>',
    `now_local: ${ctx.now_local}`,
    `conversation_mode: ${ctx.conversation_mode}`,
    `customer_display_name: "${ctx.customer_display_name}"`,
    `customer_gender_hint: ${ctx.customer_gender_hint}`,
    `minor_flag: ${ctx.minor_flag}`,
    `consent: ai_assistant=${ctx.consent.ai_assistant}; followup_care=${ctx.consent.followup_care}; promotions=${ctx.consent.promotions}`,
    `open_booking_requests: ${bookings}`,
    `last_followup_sent: ${ctx.last_followup_sent}`,
    `notes: ${ctx.notes.length ? ctx.notes.join('; ') : 'none'}`,
    '</turn_context>',
  ].join('\n');
}
