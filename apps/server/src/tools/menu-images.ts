// Owner: menu images (task B). Server side of the attach_menu_images model tool.
//
// The model asks for menu slides by group ({group: 'overview' | <group>, service_id: 'none'}) or by catalog service
// ({group: 'none', service_id}). The tool picks the slide keys from data/menu-images.json, never from the model's
// words. Slides with has_medical_claim = true are refused: only staff send them. A successful call attaches its keys
// to the job's draft: acceptDraft reads them back from tool_calls (attachmentsForJob), so a draft carries exactly the
// keys this tool returned, at most MAX_MENU_IMAGES, in call order. Approving the draft queues the text first, then
// one cs_images outbox row with these keys (src/conversation-do.ts, src/bridge/outbox.ts).
import type { Env } from '../types';
import { MAX_MENU_IMAGES, MENU_GROUPS, MENU_INDEX, type MenuGroup, type MenuSlide, menuSlide, serviceSlides, slideKey, uniqueKeys } from '../lib/menu-images';
import type { ToolContext, ToolOutcome } from './index';

export const ATTACH_GROUP_VALUES = ['none', 'overview', ...MENU_GROUPS] as const;

const NOTE_ATTACHED =
  'These images go out right after your text, once staff approve the draft. Say in one short sentence that you are ' +
  'sending the menu image(s). Do not read prices off the images: prices come only from quote_price. Do not describe ' +
  'health effects printed on any image.';
const NOTE_REFUSED =
  'These slides print health or treatment claims, so only staff can send them. Do not promise an image. Answer in ' +
  'text from the catalog tools, or offer that staff will send the menu.';

function view(s: MenuSlide) {
  return { key: s.key, group_label: MENU_INDEX.groups[s.group].label, slide: s.n, title: s.title };
}

/** Keys this job already attached (successful attach_menu_images calls, in call order), at most MAX_MENU_IMAGES. */
export async function attachmentsForJob(env: Env, jobId: string): Promise<string[]> {
  const { results } = await env.DB.prepare(
    "SELECT result_json FROM tool_calls WHERE job_id = ? AND tool_name = 'attach_menu_images' AND is_error = 0 ORDER BY created_at, id",
  )
    .bind(jobId)
    .all<{ result_json: string }>();
  const keys: string[] = [];
  for (const r of results ?? []) {
    try {
      const res = JSON.parse(r.result_json) as { status?: string; attached?: Array<{ key?: unknown }> };
      if (res.status === 'attached' && Array.isArray(res.attached)) keys.push(...res.attached.map((a) => a?.key as string));
    } catch {
      /* ignore malformed rows */
    }
  }
  return uniqueKeys(keys).slice(0, MAX_MENU_IMAGES);
}

/** Candidate slides for the request, before the medical-claim filter. */
function candidates(group: string, serviceId: string): { slides: MenuSlide[]; scope: string } | { error: string; field: string; detail: string } {
  const wantsGroup = group !== 'none';
  const wantsService = serviceId !== 'none' && serviceId !== '';
  if (wantsGroup === wantsService) {
    return { error: 'validation_failed', field: wantsGroup ? 'service_id' : 'group', detail: "give either a group (service_id 'none') or a service_id (group 'none')" };
  }
  if (group === 'overview') {
    const slides = MENU_INDEX.overview_groups.flatMap((g) => MENU_INDEX.groups[g].cover.map((n) => menuSlide(slideKey(g, n))).filter((s): s is MenuSlide => !!s));
    return { slides, scope: 'overview' };
  }
  if (wantsGroup) {
    const g = group as MenuGroup;
    const slides = MENU_INDEX.groups[g].price_list.map((n) => menuSlide(slideKey(g, n))).filter((s): s is MenuSlide => !!s);
    return { slides, scope: `group:${g}` };
  }
  return { slides: serviceSlides(serviceId), scope: `service:${serviceId}` };
}

export async function attachMenuImages(env: Env, ctx: ToolContext, input: { group: string; service_id: string }): Promise<ToolOutcome> {
  const picked = candidates(input.group, input.service_id);
  if ('error' in picked) return { result: picked, is_error: true };
  if (picked.scope.startsWith('service:')) {
    const known = await env.DB.prepare('SELECT 1 AS x FROM services WHERE catalog_version = ? AND service_id = ?').bind(ctx.catalog_version, input.service_id).first<{ x: number }>();
    if (!known) return { result: { error: 'validation_failed', field: 'service_id', detail: 'unknown service_id; use an id from search_services' }, is_error: true };
  }
  if (!picked.slides.length) {
    return {
      result: { status: 'no_images', reason: 'service_not_on_menu_slides', attached: [], note: 'There is no menu image for this service. Answer in text.' },
      is_error: false,
    };
  }
  const allowed = picked.slides.filter((s) => !s.has_medical_claim);
  const refused = picked.slides.filter((s) => s.has_medical_claim);
  // A service whose name-and-price slide prints a claim is not sent as loose process slides: staff send all of it.
  const serviceBlocked = picked.scope.startsWith('service:') && !allowed.some((s) => s.kind === 'service');
  if (!allowed.length || serviceBlocked) {
    return {
      result: { status: 'refused', reason: 'medical_claim_slides_staff_only', attached: [], refused: picked.slides.map((s) => s.key), note: NOTE_REFUSED },
      is_error: false,
    };
  }
  const before = await attachmentsForJob(env, ctx.job_id);
  const fresh = allowed.filter((s) => !before.includes(s.key));
  const room = Math.max(0, MAX_MENU_IMAGES - before.length);
  const take = fresh.slice(0, room);
  const dropped = fresh.slice(room).map((s) => s.key);
  if (!take.length && fresh.length) {
    return {
      result: { status: 'limit_reached', attached: [], total_attached: before.length, max_images: MAX_MENU_IMAGES, note: `This reply already carries ${MAX_MENU_IMAGES} images; no more can be attached.` },
      is_error: false,
    };
  }
  return {
    result: {
      status: 'attached',
      scope: picked.scope,
      attached: take.map(view),
      already_attached: allowed.filter((s) => before.includes(s.key)).map((s) => s.key),
      skipped_claim_slides: refused.map((s) => s.key),
      ...(dropped.length ? { dropped_over_limit: dropped } : {}),
      total_attached: before.length + take.length,
      max_images: MAX_MENU_IMAGES,
      note: NOTE_ATTACHED,
    },
    is_error: false,
  };
}
