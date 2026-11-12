// Owner: reply templates (task C). data/reply-templates.json (Vietnamese, owner has not approved it yet) rendered as
// the <reply_templates> block of the system prompt. buildPrompt (./prompt.ts) places it right after block A, so the
// templates change the prompt_hash like any prompt edit, and the runner gets them through GET /runner/prompt without
// a re-seed. The JSON is bundled at build time (the Worker never reads the repository at runtime).
import TEMPLATES_JSON from '../../../../data/reply-templates.json';
import { TOOL_NAMES } from '../types';

export interface ReplyTemplateTool {
  name: string;
  input: Record<string, unknown>;
  purpose: string;
}

export interface ReplyTemplateExample {
  situation: string;
  profile: Record<string, string> | null;
  customer: string;
  tool_calls: Array<{ name: string; input: Record<string, unknown>; result: string }>;
  reply: string;
}

export interface ReplyTemplateIntent {
  id: string;
  label: string;
  when: string[];
  not_when: string[];
  tools: ReplyTemplateTool[];
  source?: string;
  template: string;
  placeholders: string[];
  fallback_no_profile: string;
  rules: string[];
  examples: ReplyTemplateExample[];
}

export interface ReplyTemplatesFile {
  schema_version: number;
  status: string;
  written_on: string;
  note: string;
  voice: {
    self: string;
    address_default: string;
    address_terms: string[];
    never_address: string[];
    never_words: string[];
    max_questions: number;
    rules: string[];
  };
  selection_rules: string[];
  placeholders: Record<string, { meaning: string; source: string }>;
  menu_groups: Array<{ catalog_group: string; label: string; line: string; image_group: string | null }>;
  intents: ReplyTemplateIntent[];
}

export const REPLY_TEMPLATES = TEMPLATES_JSON as unknown as ReplyTemplatesFile;

/** The intents the prompt and the tests know; data/reply-templates.json must define exactly these, in this order. */
export const INTENT_IDS = [
  'chao_khach_moi',
  'chao_khach_quen',
  'xem_menu_tong',
  'xem_menu_nhom',
  'hoi_dich_vu',
  'dat_lich',
  'cam_on_sau_khi_lam',
] as const;

/** Placeholders an example reply may still show: prices are copied from a tool result, never from an example. */
export const EXAMPLE_PLACEHOLDERS = ['price_text'];

const PLACEHOLDER_RE = /\{([a-z_]+)\}/g;

export function placeholdersIn(text: string): string[] {
  return [...new Set([...text.matchAll(PLACEHOLDER_RE)].map((m) => m[1]!))];
}

/**
 * Consistency problems of a templates file (empty = fine): the fixed intent list, placeholders declared globally and
 * per intent and used by the template, examples with only {price_text} left, tool names the server knows.
 */
export function templateIssues(file: ReplyTemplatesFile = REPLY_TEMPLATES): string[] {
  const out: string[] = [];
  const ids = file.intents.map((i) => i.id);
  if (JSON.stringify(ids) !== JSON.stringify(INTENT_IDS)) out.push(`intents must be ${INTENT_IDS.join(', ')} (got ${ids.join(', ')})`);
  const declared = Object.keys(file.placeholders);
  for (const it of file.intents) {
    const used = new Set([...placeholdersIn(it.template), ...placeholdersIn(it.fallback_no_profile)]);
    for (const p of used) {
      if (!it.placeholders.includes(p)) out.push(`${it.id}: {${p}} is used but not listed in placeholders`);
      if (!declared.includes(p)) out.push(`${it.id}: {${p}} has no entry in the global placeholders`);
    }
    for (const p of it.placeholders) if (!placeholdersIn(it.template).includes(p)) out.push(`${it.id}: placeholder ${p} is not used by the template`);
    for (const p of placeholdersIn(it.fallback_no_profile)) {
      if (p === 'xung_ho' || p === 'ten') out.push(`${it.id}: the no-profile fallback must say anh/chị, not {${p}}`);
    }
    if (it.examples.length < 2) out.push(`${it.id}: needs 2 examples`);
    it.examples.forEach((ex, n) => {
      for (const p of placeholdersIn(ex.reply)) if (!EXAMPLE_PLACEHOLDERS.includes(p)) out.push(`${it.id} example ${n + 1}: {${p}} is not filled`);
      for (const t of ex.tool_calls) if (!(TOOL_NAMES as string[]).includes(t.name)) out.push(`${it.id} example ${n + 1}: unknown tool ${t.name}`);
    });
    for (const t of it.tools) if (!(TOOL_NAMES as string[]).includes(t.name)) out.push(`${it.id}: unknown tool ${t.name}`);
  }
  return out;
}

function indent(text: string): string {
  return text
    .split('\n')
    .map((l) => `  ${l}`)
    .join('\n');
}

function profileText(p: Record<string, string> | null): string {
  if (!p) return 'no <customer_profile>';
  return Object.entries(p)
    .map(([k, v]) => `${k}: ${v}`)
    .join('; ');
}

/** The <reply_templates> block: instructions in English, template text and rules in Vietnamese as written. */
export function blockTemplates(file: ReplyTemplatesFile = REPLY_TEMPLATES): string {
  const L: string[] = [];
  L.push(`<reply_templates version="rt${file.schema_version}_${file.written_on}" status="${file.status}">`);
  L.push(
    'Reply templates, one per customer intent. Before writing, pick the one intent that matches the latest customer ' +
      'message, call the tools it lists, and write the reply in the shape of its template. The hard rules of block A win ' +
      'over every template. Template text, rules and examples below are in Vietnamese as the owner will review them.',
  );
  L.push(
    'Placeholders such as {xung_ho} are filled only from <customer_profile>, tool results in this conversation, ' +
      '<approved_catalog> or the menu groups below; without a profile use the "without profile" version. In the examples ' +
      '{price_text} stands for a price_text you copy from a tool result: never copy a price from an example.',
  );
  L.push('');
  L.push('Voice:');
  for (const r of file.voice.rules) L.push(`- ${r}`);
  L.push('');
  L.push('How to choose:');
  for (const r of file.selection_rules) L.push(`- ${r}`);
  L.push('');
  L.push('Placeholders:');
  for (const [k, v] of Object.entries(file.placeholders)) L.push(`- {${k}}: ${v.meaning}`);
  L.push('');
  L.push('menu_groups (catalog group | label | line for the overview | menu image group for attach_menu_images):');
  for (const g of file.menu_groups) L.push(`- ${g.catalog_group} | ${g.label} | ${g.line} | ${g.image_group ?? 'none: no menu images'}`);
  for (const it of file.intents) {
    L.push('');
    L.push(`[intent: ${it.id}] ${it.label}`);
    L.push(`When: ${it.when.join(' ')}`);
    if (it.not_when.length) L.push(`Not when: ${it.not_when.join(' ')}`);
    if (it.tools.length) {
      L.push('Tools:');
      for (const t of it.tools) L.push(`- ${t.name} ${JSON.stringify(t.input)}: ${t.purpose}`);
    } else {
      L.push('Tools: none.');
    }
    if (it.source) L.push(`Source: ${it.source}`);
    L.push('Template:');
    L.push(indent(it.template));
    L.push('Without profile:');
    L.push(indent(it.fallback_no_profile));
    L.push('Rules:');
    for (const r of it.rules) L.push(`- ${r}`);
    it.examples.forEach((ex, n) => {
      L.push(`Example ${n + 1} (${ex.situation} Profile: ${profileText(ex.profile)}.)`);
      L.push(`Customer: "${ex.customer}"`);
      if (ex.tool_calls.length) {
        L.push(`(You call ${ex.tool_calls.map((t) => `${t.name} ${JSON.stringify(t.input)} -> ${t.result}`).join('; ')}.)`);
      }
      L.push('Reply:');
      L.push(indent(ex.reply));
    });
  }
  L.push('</reply_templates>');
  return L.join('\n');
}
