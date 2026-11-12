// Owner: server-core. Contact profile routes of the staff API (docs/contracts.md section 13). Auth: requireStaff.
import type { Context } from 'hono';
import type { AppEnv } from '../types';
import { HttpError, readJson } from '../lib/http';
import {
  CONFIDENCES,
  MAX_IMPORT_BYTES,
  PROFILE_ID_RE,
  RELATIONSHIPS,
  getProfileView,
  importProfiles,
  listProfiles,
  patchProfile,
} from '../lib/profiles';

type H = (c: Context<AppEnv>) => Promise<Response>;

const staffId = (c: Context<AppEnv>) => c.get('staffId') ?? 'staff';

function profileId(c: Context<AppEnv>): string {
  const id = c.req.param('zalo_user_id') ?? '';
  if (!PROFILE_ID_RE.test(id)) throw new HttpError(400, 'bad_request', "zalo_user_id must be 'p:' + threadId");
  return id;
}

const tooLarge = () => new HttpError(413, 'bad_request', `body is larger than ${MAX_IMPORT_BYTES} bytes`);

/** The request body as text, reading at most `max` bytes (a chunked body without Content-Length included). */
export async function readTextCapped(req: Request, max: number): Promise<string> {
  const len = Number(req.headers.get('content-length') ?? 0);
  if (len > max) throw tooLarge();
  if (!req.body) return '';
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      await reader.cancel().catch(() => undefined);
      throw tooLarge();
    }
    chunks.push(value);
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const ch of chunks) {
    buf.set(ch, off);
    off += ch.byteLength;
  }
  return new TextDecoder().decode(buf);
}

/** POST /staff/profiles/import: batch upsert from scripts/analyze_contacts.py (X-Staff-Id: analyzer). */
export const importHandler: H = async (c) => {
  const raw = await readTextCapped(c.req.raw, MAX_IMPORT_BYTES);
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    throw new HttpError(400, 'bad_request', 'body must be JSON');
  }
  return c.json(await importProfiles(c.env, body, staffId(c)));
};

/** GET /staff/profiles?relationship=&confidence=&staff_override=&limit=&cursor= (newest change first). */
export const listHandler: H = async (c) => {
  const limit = Math.min(Math.max(Number(c.req.query('limit') ?? 50) || 50, 1), 200);
  let offset = 0;
  const cur = c.req.query('cursor');
  if (cur) {
    try {
      offset = Math.max(0, Number(JSON.parse(atob(cur)).o) || 0);
    } catch {
      throw new HttpError(400, 'bad_request', 'bad cursor');
    }
  }
  const relationship = c.req.query('relationship');
  if (relationship && !(RELATIONSHIPS as string[]).includes(relationship)) throw new HttpError(422, 'validation_failed', 'bad relationship', { field: 'relationship' });
  const confidence = c.req.query('confidence');
  if (confidence && !(CONFIDENCES as string[]).includes(confidence)) throw new HttpError(422, 'validation_failed', 'bad confidence', { field: 'confidence' });
  const so = c.req.query('staff_override');
  if (so !== undefined && so !== 'true' && so !== 'false') throw new HttpError(422, 'validation_failed', 'staff_override must be true or false', { field: 'staff_override' });
  const rows = await listProfiles(
    c.env,
    { ...(relationship ? { relationship } : {}), ...(confidence ? { confidence } : {}), ...(so !== undefined ? { staff_override: so === 'true' } : {}) },
    limit + 1,
    offset,
  );
  const more = rows.length > limit;
  return c.json({ items: rows.slice(0, limit), next_cursor: more ? btoa(JSON.stringify({ o: offset + limit })) : null });
};

/** GET /staff/profiles/:zalo_user_id */
export const getHandler: H = async (c) => {
  const profile = await getProfileView(c.env, profileId(c));
  if (!profile) throw new HttpError(404, 'not_found', 'profile not found');
  return c.json({ profile });
};

/** PATCH /staff/profiles/:zalo_user_id: staff correction (sets staff_override) or `{ "staff_override": false }`. */
export const patchHandler: H = async (c) => {
  const id = profileId(c);
  await patchProfile(c.env, id, await readJson(c), staffId(c));
  return c.json({ profile: await getProfileView(c.env, id) });
};
