// Owner: menu images (task B). Read-only access to data/menu-images.json, bundled at build time (the Worker never
// reads the repository at runtime). A menu image key is '<group>/<n>'; the bridge alone turns a key into a local
// JPEG through ~/.thomhouse-bot/menu-images/manifest.json. Keys never come from the model as free text: the
// attach_menu_images tool picks them from this index, and every place that stores or queues keys re-validates them.
import type { Attachment } from '../types';
import MENU_JSON from '../../../../data/menu-images.json';

export type MenuGroup = 'facial' | 'healing' | 'thu-gian-toc' | 'hair-removal';
export type MenuSlideKind = 'cover' | 'price_list' | 'service' | 'process' | 'other';

export interface MenuSlide {
  key: string;
  group: MenuGroup;
  n: number;
  file: string;
  kind: MenuSlideKind;
  title: string;
  service_ids: string[];
  unmatched_names: string[];
  has_medical_claim: boolean;
  claim_note: string | null;
  note: string | null;
}

export interface MenuGroupDef {
  label: string;
  dir: string;
  catalog_group: string | null;
  slide_count: number;
  cover: number[];
  price_list: number[];
  services: Record<string, number[]>;
  unmatched_services: Array<{ name: string; slides: number[] }>;
  review_note?: string;
}

export interface MenuIndex {
  schema_version: number;
  max_images_per_send: number;
  overview_groups: MenuGroup[];
  groups: Record<MenuGroup, MenuGroupDef>;
  slides: MenuSlide[];
}

export const MENU_INDEX = MENU_JSON as unknown as MenuIndex;
/** At most this many images per outbox row (one `zalo-agent msg send-image` call) and per draft. */
export const MAX_MENU_IMAGES = 10;
export const MENU_GROUPS: MenuGroup[] = ['facial', 'healing', 'thu-gian-toc', 'hair-removal'];
export const MENU_IMAGE_KEY_RE = /^(facial|healing|thu-gian-toc|hair-removal)\/([1-9][0-9]?)$/;

const BY_KEY = new Map(MENU_INDEX.slides.map((s) => [s.key, s]));

export function menuSlide(key: string): MenuSlide | null {
  return BY_KEY.get(key) ?? null;
}

export function isMenuImageKey(key: unknown): key is string {
  return typeof key === 'string' && MENU_IMAGE_KEY_RE.test(key) && BY_KEY.has(key);
}

export function slideKey(group: MenuGroup, n: number): string {
  return `${group}/${n}`;
}

/** Order-preserving de-duplication, unknown keys dropped. */
export function uniqueKeys(keys: Iterable<unknown>): string[] {
  const out: string[] = [];
  for (const k of keys) if (isMenuImageKey(k) && !out.includes(k)) out.push(k);
  return out;
}

/** Parses a stored JSON array of keys (drafts.attachments_json, outbox.image_keys); [] when absent or broken. */
export function parseKeys(json: string | null | undefined): string[] {
  if (!json) return [];
  try {
    const v = JSON.parse(json) as unknown;
    return Array.isArray(v) ? uniqueKeys(v) : [];
  } catch {
    return [];
  }
}

/** Slides a service id appears on, in group order (a service sits in one group). */
export function serviceSlides(serviceId: string): MenuSlide[] {
  for (const g of MENU_GROUPS) {
    const ns = MENU_INDEX.groups[g].services[serviceId];
    if (ns) return ns.map((n) => menuSlide(slideKey(g, n))).filter((s): s is MenuSlide => !!s);
  }
  return [];
}

/** Staff-facing label of an image send, stored as the text of its messages / outbox row (never sent to Zalo). */
export function menuImagesLabel(keys: string[]): string {
  const byGroup = new Map<MenuGroup, number[]>();
  for (const k of keys) {
    const s = menuSlide(k);
    if (!s) continue;
    byGroup.set(s.group, [...(byGroup.get(s.group) ?? []), s.n]);
  }
  const parts = [...byGroup].map(([g, ns]) => `${MENU_INDEX.groups[g].label} (ảnh ${ns.join(', ')})`);
  return `[Ảnh menu, ${keys.length} ảnh] ${parts.join('; ')}`;
}

/** messages.attachments_json of an image send: one entry per slide. */
export function menuAttachments(keys: string[]): Attachment[] {
  return keys.map((k) => {
    const s = menuSlide(k);
    return { type: 'menu_image', name: s ? `${MENU_INDEX.groups[s.group].label}, ảnh ${s.n}: ${s.title}`.slice(0, 200) : k };
  });
}
