// Owner: menu images (task B). Pre-send checker rule for menu images attached to a draft: every key must be a known
// slide of data/menu-images.json, at most MAX_MENU_IMAGES, and no slide may print a medical claim
// (has_medical_claim = true). attach_menu_images already refuses claim slides; this rule is the second line, so a
// draft that would send one is 'blocked' and only staff can send it (approve with override_checker).
import type { CheckerIssue } from '../types';
import { MAX_MENU_IMAGES, isMenuImageKey, menuSlide } from '../lib/menu-images';

export function menuImageIssues(keys: readonly string[]): CheckerIssue[] {
  const issues: CheckerIssue[] = [];
  if (keys.length > MAX_MENU_IMAGES) {
    issues.push({ rule: 'menu_image', detail: `${keys.length} menu images attached (max ${MAX_MENU_IMAGES})` });
  }
  for (const k of keys) {
    if (!isMenuImageKey(k)) {
      issues.push({ rule: 'menu_image', detail: 'unknown menu image key', excerpt: String(k).slice(0, 40) });
      continue;
    }
    const s = menuSlide(k)!;
    if (s.has_medical_claim) {
      issues.push({ rule: 'menu_image', detail: `menu image prints a health claim; staff only: ${s.claim_note ?? ''}`.slice(0, 300), excerpt: k });
    }
  }
  return issues;
}
