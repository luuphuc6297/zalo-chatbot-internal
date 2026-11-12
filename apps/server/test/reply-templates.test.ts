// Reply templates (task C): data/reply-templates.json is consistent (placeholders, intents, tools), every example
// reply follows the voice rules and passes the pre-send checker, and GET /runner/prompt carries the templates as the
// <reply_templates> block right after block A.
import { describe, expect, it } from 'vitest';
import { checkDraft } from '../src/checker';
import { GROUP_ORDER } from '../src/lib/prompt';
import { MENU_GROUPS } from '../src/lib/menu-images';
import { INTENT_IDS, REPLY_TEMPLATES, blockTemplates, placeholdersIn, templateIssues, type ReplyTemplatesFile } from '../src/lib/reply-templates';
import { validateToolInput } from '../src/tools';
import { SEED_DATA } from '../src/seed-data';
import type { ToolName } from '../src/types';
import { runner, seed } from './core-helpers';

const examples = REPLY_TEMPLATES.intents.flatMap((it) => it.examples.map((ex, i) => ({ intent: it.id, n: i + 1, ...ex })));
const displayNames = (SEED_DATA.services_json as { services: Array<{ name_vi: string; display_name_vi?: string }> }).services.map(
  (s) => s.display_name_vi ?? s.name_vi,
);
const words = (text: string) => text.toLowerCase().split(/[^\p{L}\p{N}/]+/u);

describe('reply templates file', () => {
  it('is consistent: the seven intents, declared and used placeholders, known tools', () => {
    expect(templateIssues()).toEqual([]);
    expect(REPLY_TEMPLATES.intents.map((i) => i.id)).toEqual([...INTENT_IDS]);
    for (const it of REPLY_TEMPLATES.intents) expect(it.examples).toHaveLength(2);
  });

  it('reports a placeholder that is used but not declared, and an unfilled example', () => {
    const broken = JSON.parse(JSON.stringify(REPLY_TEMPLATES)) as ReplyTemplatesFile;
    broken.intents[0]!.template += ' {gio}';
    broken.intents[1]!.examples[0]!.reply += ' {xung_ho}';
    broken.intents[2]!.fallback_no_profile = broken.intents[2]!.fallback_no_profile.replace('anh/chị', '{xung_ho}');
    const issues = templateIssues(broken);
    expect(issues.some((i) => i.includes('chao_khach_moi: {gio} is used but not listed'))).toBe(true);
    expect(issues.some((i) => i.includes('chao_khach_quen example 1: {xung_ho} is not filled'))).toBe(true);
    expect(issues.some((i) => i.includes('xem_menu_tong: the no-profile fallback must say anh/chị'))).toBe(true);
  });

  it('maps every catalog group to one menu line and only known menu image groups', () => {
    expect(REPLY_TEMPLATES.menu_groups.map((g) => g.catalog_group)).toEqual([...GROUP_ORDER]);
    for (const g of REPLY_TEMPLATES.menu_groups) {
      if (g.image_group !== null) expect(MENU_GROUPS as string[]).toContain(g.image_group);
      expect(g.line.length).toBeLessThan(100);
    }
  });

  it('lists tool calls in examples with inputs the server accepts', () => {
    for (const ex of examples) {
      for (const t of ex.tool_calls) {
        expect(validateToolInput(t.name as ToolName, t.input), `${ex.intent} ${ex.n} ${t.name}`).toEqual({ ok: true });
      }
    }
  });
});

describe('example replies follow the voice rules', () => {
  it.each(examples.map((e) => [`${e.intent} #${e.n}`, e] as const))('%s', (_label, ex) => {
    const r = ex.reply;
    expect(r.startsWith('Dạ ')).toBe(true);
    // never "mình" / "bạn" / "quý khách" for the customer, never "ngay" / "liền" / "sớm"
    for (const w of ['mình', 'bạn', 'ngay', 'liền', 'sớm']) expect(words(r), w).not.toContain(w);
    expect(r.toLowerCase()).not.toContain('quý khách');
    // at most two questions (question marks; each template question asks one or two pieces of information)
    expect((r.match(/\?/g) ?? []).length).toBeLessThanOrEqual(2);
    // only {price_text} may stay unfilled
    expect(placeholdersIn(r).every((p) => p === 'price_text')).toBe(true);
    // the first sentence addresses the customer from the profile (term + name), or "anh/chị" without one
    const first = r.split(/[.?!]\s/)[0]!;
    const p = ex.profile;
    const call = p?.name ? `${p.address} ${p.name}` : (p?.address ?? 'anh/chị');
    expect(first, `${ex.intent} first sentence`).toContain(call);
    // the pre-send checker passes: no forbidden term, no markdown, no k-prices, within the length limit
    const res = checkDraft({ text: r, conversation_id: 'c', catalog_version: 'v', allowed_price_texts: [], approved_contact_values: [], display_names: displayNames }, 1);
    expect(res.issues).toEqual([]);
  });

  it('mentions a last service only when the example profile has one', () => {
    for (const ex of examples) {
      if (ex.reply.includes('Lần trước')) expect(ex.profile?.last_service, `${ex.intent} ${ex.n}`).toBeTruthy();
    }
    const quen = REPLY_TEMPLATES.intents.find((i) => i.id === 'chao_khach_quen')!;
    expect(quen.template).toContain('Lần trước {xung_ho} làm {dich_vu} bên em hôm {ngay}');
    expect(quen.fallback_no_profile).not.toContain('Lần trước');
  });
});

describe('<reply_templates> in the prompt', () => {
  it('renders every intent, its template, fallback and examples', () => {
    const t = blockTemplates();
    expect(t.startsWith('<reply_templates version="rt1_')).toBe(true);
    expect(t.trimEnd().endsWith('</reply_templates>')).toBe(true);
    for (const it of REPLY_TEMPLATES.intents) {
      expect(t).toContain(`[intent: ${it.id}]`);
      expect(t).toContain(it.template.split('\n')[0]);
      expect(t).toContain(it.fallback_no_profile.split('\n')[0]);
    }
    expect(t).toContain('never copy a price from an example');
    expect(t).toContain('- relaxation | menu thư giãn |');
  });

  it('GET /runner/prompt places the templates between block A and the catalog', async () => {
    await seed();
    const p = await runner('/runner/prompt', undefined, 'mac-1', 'GET');
    expect(p.status).toBe(200);
    const cli: string = p.body.cli_system_prompt;
    expect(p.body.blocks.t).toBe(blockTemplates());
    // block A itself names both tags, so locate the blocks by their whole text
    const a = cli.indexOf(p.body.blocks.a);
    const t = cli.indexOf(p.body.blocks.t);
    const b = cli.indexOf(p.body.blocks.b);
    expect(a).toBeGreaterThanOrEqual(0);
    expect(t).toBeGreaterThan(a);
    expect(b).toBeGreaterThan(t);
    // block A tells the model to use the templates and the profile's address in the first sentence
    expect(p.body.blocks.a).toContain('Reply templates: the <reply_templates> block');
    expect(p.body.blocks.a).toContain('in the first sentence of every reply');
  });
});
