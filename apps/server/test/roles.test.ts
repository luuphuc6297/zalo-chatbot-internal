// Contact roles (docs/contracts.md section 14.3): the roles library and the three staff endpoints. Ids are synthetic.
import { env, SELF } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { MAX_IMPORT_ROLES, ROLE_ID_RE, getContactRole, getContactRoles, importContactRoles, isInternalRole, listContactRoles, setContactRole } from '../src/lib/roles';
import { staff } from './core-helpers';

const A = 'p:900000000000001';
const B = 'p:900000000000002';
const C = 'p:900000000000003';
const D = 'p:900000000000004';

const importRoles = (roles: unknown, extra: Record<string, unknown> = {}) => staff('POST', '/staff/roles/import', { source: 'zalo_label', roles, ...extra });
const putRole = (id: string, role: unknown) => staff('PUT', `/staff/roles/${encodeURIComponent(id)}`, { role });
const rowOf = (id: string) => env.DB.prepare('SELECT zalo_user_id, role, source, updated_by FROM contact_roles WHERE zalo_user_id = ?').bind(id).first<{ zalo_user_id: string; role: string; source: string; updated_by: string | null }>();
const countRows = async () => (await env.DB.prepare('SELECT COUNT(*) AS n FROM contact_roles').first<{ n: number }>())!.n;
async function audits(action: string) {
  const { results } = await env.DB.prepare('SELECT actor_type, actor_id, entity, entity_id, before_json, after_json FROM audit_log WHERE action = ? ORDER BY id').bind(action).all<{
    actor_type: string;
    actor_id: string | null;
    entity: string | null;
    entity_id: string | null;
    before_json: string | null;
    after_json: string | null;
  }>();
  return results;
}

beforeEach(async () => {
  await env.DB.batch([env.DB.prepare('DELETE FROM contact_roles'), env.DB.prepare("DELETE FROM audit_log WHERE action IN ('roles.import', 'role.staff_edit')")]);
});

describe('POST /staff/roles/import', () => {
  it('imports new rows with source zalo_label and counts them', async () => {
    const r = await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'manager' },
      { zalo_user_id: C, role: 'staff' },
    ]);
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ imported: 3, updated: 0, unchanged: 0, removed: 0, kept_staff: 0 });
    expect(await rowOf(A)).toEqual({ zalo_user_id: A, role: 'customer', source: 'zalo_label', updated_by: 'tester' });
    expect(await rowOf(B)).toMatchObject({ role: 'manager', source: 'zalo_label' });
    expect(await rowOf(C)).toMatchObject({ role: 'staff', source: 'zalo_label' });
  });

  it('a second import counts unchanged and updated rows and leaves the others alone', async () => {
    await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'manager' },
    ]);
    const before = await env.DB.prepare('SELECT updated_at FROM contact_roles WHERE zalo_user_id = ?').bind(A).first<{ updated_at: number }>();
    const r = await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'staff' },
      { zalo_user_id: C, role: 'customer' },
    ]);
    expect(r.body).toEqual({ imported: 1, updated: 1, unchanged: 1, removed: 0, kept_staff: 0 });
    expect(await rowOf(B)).toMatchObject({ role: 'staff', source: 'zalo_label' });
    // an unchanged row is not rewritten
    expect(await env.DB.prepare('SELECT updated_at FROM contact_roles WHERE zalo_user_id = ?').bind(A).first()).toEqual(before);
  });

  it('never overwrites a row a staff member set', async () => {
    expect((await putRole(A, 'manager')).status).toBe(200);
    const r = await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'customer' },
    ]);
    expect(r.body).toEqual({ imported: 1, updated: 0, unchanged: 0, removed: 0, kept_staff: 1 });
    expect(await rowOf(A)).toMatchObject({ role: 'manager', source: 'staff' });
    // also when the label says the same role: the row stays a staff row
    const same = await importRoles([{ zalo_user_id: A, role: 'manager' }]);
    expect(same.body).toMatchObject({ kept_staff: 1, unchanged: 0, updated: 0 });
    expect(await rowOf(A)).toMatchObject({ role: 'manager', source: 'staff' });
  });

  it('complete: true removes the label rows the list does not name, and never a staff row', async () => {
    await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'customer' },
      { zalo_user_id: C, role: 'staff' },
    ]);
    await putRole(D, 'manager');
    const r = await importRoles([{ zalo_user_id: A, role: 'customer' }], { complete: true });
    expect(r.body).toEqual({ imported: 0, updated: 0, unchanged: 1, removed: 2, kept_staff: 0 });
    expect(await rowOf(A)).toMatchObject({ role: 'customer' });
    expect(await rowOf(B)).toBeNull();
    expect(await rowOf(C)).toBeNull();
    expect(await rowOf(D)).toMatchObject({ role: 'manager', source: 'staff' });
  });

  it('without complete (or with complete: false) nothing is removed', async () => {
    await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'customer' },
    ]);
    expect((await importRoles([{ zalo_user_id: A, role: 'customer' }])).body).toMatchObject({ removed: 0, unchanged: 1 });
    expect((await importRoles([{ zalo_user_id: A, role: 'customer' }], { complete: false })).body).toMatchObject({ removed: 0, unchanged: 1 });
    expect(await rowOf(B)).not.toBeNull();
  });

  it('an empty complete list clears every label row and keeps the staff rows', async () => {
    await importRoles([
      { zalo_user_id: A, role: 'customer' },
      { zalo_user_id: B, role: 'staff' },
    ]);
    await putRole(C, 'staff');
    const r = await importRoles([], { complete: true });
    expect(r.body).toEqual({ imported: 0, updated: 0, unchanged: 0, removed: 2, kept_staff: 0 });
    expect(await countRows()).toBe(1);
    expect(await rowOf(C)).toMatchObject({ source: 'staff' });
  });

  it('rejects the whole request when one entry is bad, naming the field, and writes nothing', async () => {
    const bad = async (roles: unknown, field: string, extra: Record<string, unknown> = {}) => {
      const r = await importRoles(roles, extra);
      expect(r.status, field).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field } });
    };
    await bad([{ zalo_user_id: A, role: 'customer' }, { zalo_user_id: 'u123', role: 'customer' }], 'roles[1].zalo_user_id');
    await bad([{ zalo_user_id: 'p:12ab', role: 'customer' }], 'roles[0].zalo_user_id');
    await bad([{ zalo_user_id: 'p:', role: 'customer' }], 'roles[0].zalo_user_id');
    await bad([{ zalo_user_id: 12345, role: 'customer' }], 'roles[0].zalo_user_id');
    await bad([{ zalo_user_id: A, role: 'owner' }], 'roles[0].role');
    await bad([{ zalo_user_id: A, role: null }], 'roles[0].role');
    await bad([{ zalo_user_id: A }], 'roles[0].role');
    await bad([{ zalo_user_id: A, role: 'customer' }, 'x'], 'roles[1]');
    await bad([{ zalo_user_id: A, role: 'customer' }, { zalo_user_id: A, role: 'staff' }], 'roles[1].zalo_user_id');
    await bad('nope', 'roles');
    await bad(undefined, 'roles');
    await bad([{ zalo_user_id: A, role: 'customer' }], 'complete', { complete: 'yes' });
    await bad([{ zalo_user_id: A, role: 'customer' }], 'source', { source: 'staff' });
    await bad([{ zalo_user_id: A, role: 'customer' }], 'source', { source: undefined });
    expect(await countRows()).toBe(0);
    expect(await audits('roles.import')).toHaveLength(0);
    const notObject = await staff('POST', '/staff/roles/import', [1, 2]);
    expect(notObject.status).toBe(422);
    expect(notObject.body.error.details.field).toBe('roles');
  });

  it(`rejects more than ${MAX_IMPORT_ROLES} entries`, async () => {
    const roles = Array.from({ length: MAX_IMPORT_ROLES + 1 }, (_, i) => ({ zalo_user_id: `p:8${String(i).padStart(9, '0')}`, role: 'customer' }));
    const r = await importRoles(roles);
    expect(r.status).toBe(422);
    expect(r.body.error.details.field).toBe('roles');
    expect(await countRows()).toBe(0);
  });

  it('writes a list longer than one D1 batch, and removes it again in chunks', async () => {
    const roles = Array.from({ length: 1203 }, (_, i) => ({ zalo_user_id: `p:7${String(i).padStart(9, '0')}`, role: i % 50 === 0 ? 'staff' : 'customer' }));
    const first = await importContactRoles(env, { source: 'zalo_label', roles }, 'tester');
    expect(first).toEqual({ imported: 1203, updated: 0, unchanged: 0, removed: 0, kept_staff: 0 });
    expect(await countRows()).toBe(1203);
    expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM contact_roles WHERE role = 'staff'").first<{ n: number }>())!.n).toBe(25);
    const again = await importContactRoles(env, { source: 'zalo_label', roles }, 'tester');
    expect(again).toEqual({ imported: 0, updated: 0, unchanged: 1203, removed: 0, kept_staff: 0 });
    const keep = roles.slice(0, 3);
    const cleared = await importContactRoles(env, { source: 'zalo_label', roles: keep, complete: true }, 'tester');
    expect(cleared).toEqual({ imported: 0, updated: 0, unchanged: 3, removed: 1200, kept_staff: 0 });
    expect(await countRows()).toBe(3);
  });

  it('audits counts only: no id and no name', async () => {
    await putRole(D, 'manager');
    await importRoles(
      [
        { zalo_user_id: A, role: 'customer' },
        { zalo_user_id: D, role: 'customer' },
      ],
      { complete: true },
    );
    const rows = await audits('roles.import');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ actor_type: 'staff', actor_id: 'tester', entity: 'contact_roles', entity_id: null, before_json: null });
    expect(JSON.parse(rows[0]!.after_json!)).toEqual({ imported: 1, updated: 0, unchanged: 0, removed: 0, kept_staff: 1, complete: true });
    expect(rows[0]!.after_json).not.toContain('p:');
  });

  it('needs the staff token', async () => {
    const res = await SELF.fetch('https://bot.test/staff/roles/import', { method: 'POST', body: JSON.stringify({ source: 'zalo_label', roles: [{ zalo_user_id: A, role: 'customer' }] }) });
    expect(res.status).toBe(401);
    const wrong = await SELF.fetch('https://bot.test/staff/roles', { headers: { authorization: 'Bearer test-runner-token' } });
    expect(wrong.status).toBe(401);
    expect(await countRows()).toBe(0);
  });
});

describe('PUT /staff/roles/:zalo_user_id', () => {
  it('sets the role with source staff, over a label row too', async () => {
    await importRoles([{ zalo_user_id: A, role: 'customer' }]);
    const r = await putRole(A, 'staff');
    expect(r.status).toBe(200);
    expect(r.body.role).toMatchObject({ zalo_user_id: A, role: 'staff', source: 'staff', updated_by: 'tester' });
    expect(typeof r.body.role.updated_at).toBe('number');
    expect(await rowOf(A)).toEqual({ zalo_user_id: A, role: 'staff', source: 'staff', updated_by: 'tester' });
    // a contact without any row
    expect((await putRole(B, 'customer')).body.role).toMatchObject({ zalo_user_id: B, role: 'customer', source: 'staff' });
    const edits = await audits('role.staff_edit');
    expect(edits).toHaveLength(2);
    expect(edits[0]).toMatchObject({ actor_id: 'tester', entity: 'contact_role', entity_id: A });
    expect(JSON.parse(edits[0]!.before_json!)).toEqual({ role: 'customer', source: 'zalo_label' });
    expect(JSON.parse(edits[0]!.after_json!)).toEqual({ role: 'staff', source: 'staff' });
    expect(JSON.parse(edits[1]!.before_json!)).toBeNull();
  });

  it('null deletes the row, and the next import applies again', async () => {
    await putRole(A, 'manager');
    const del = await putRole(A, null);
    expect(del.status).toBe(200);
    expect(del.body).toEqual({ role: null });
    expect(await rowOf(A)).toBeNull();
    const r = await importRoles([{ zalo_user_id: A, role: 'customer' }]);
    expect(r.body).toMatchObject({ imported: 1, kept_staff: 0 });
    expect(await rowOf(A)).toMatchObject({ role: 'customer', source: 'zalo_label' });
    // null also removes a label row
    expect((await putRole(A, null)).body).toEqual({ role: null });
    expect(await rowOf(A)).toBeNull();
  });

  it('null for a contact without a row answers null and writes nothing', async () => {
    const r = await putRole(C, null);
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ role: null });
    expect(await audits('role.staff_edit')).toHaveLength(0);
  });

  it('400 for an id that is not p:<digits>, 422 for a bad role', async () => {
    for (const id of ['u123', 'p:abc', 'p:12 34']) {
      const r = await putRole(id, 'customer');
      expect(r.status, id).toBe(400);
      expect(r.body.error.code).toBe('bad_request');
    }
    for (const role of ['owner', '', 3, undefined]) {
      const r = await staff('PUT', `/staff/roles/${A}`, role === undefined ? {} : { role });
      expect(r.status, String(role)).toBe(422);
      expect(r.body.error).toMatchObject({ code: 'validation_failed', details: { field: 'role' } });
    }
    expect((await staff('PUT', `/staff/roles/${A}`, 'customer')).status).toBe(422);
    expect(await countRows()).toBe(0);
  });
});

describe('GET /staff/roles and the read helpers', () => {
  it('lists every row, newest change first', async () => {
    await importContactRoles(env, { source: 'zalo_label', roles: [{ zalo_user_id: A, role: 'customer' }, { zalo_user_id: B, role: 'staff' }] }, 'tester', 1000);
    await setContactRole(env, C, { role: 'manager' }, 'tester', 3000);
    await setContactRole(env, A, { role: 'manager' }, 'tester', 2000);
    const r = await staff('GET', '/staff/roles');
    expect(r.status).toBe(200);
    expect(r.body).toEqual({
      roles: [
        { zalo_user_id: C, role: 'manager', source: 'staff', updated_at: 3000, updated_by: 'tester' },
        { zalo_user_id: A, role: 'manager', source: 'staff', updated_at: 2000, updated_by: 'tester' },
        { zalo_user_id: B, role: 'staff', source: 'zalo_label', updated_at: 1000, updated_by: 'tester' },
      ],
    });
    expect(await listContactRoles(env)).toEqual(r.body.roles);
  });

  it('an empty table lists nothing', async () => {
    expect((await staff('GET', '/staff/roles')).body).toEqual({ roles: [] });
  });

  it('getContactRole: the row, or null', async () => {
    await importRoles([{ zalo_user_id: A, role: 'staff' }]);
    expect(await getContactRole(env, A)).toMatchObject({ zalo_user_id: A, role: 'staff', source: 'zalo_label', updated_by: 'tester' });
    expect(await getContactRole(env, B)).toBeNull();
    expect(await getContactRole(env, '')).toBeNull();
    expect(await getContactRole(env, undefined as unknown as string)).toBeNull();
  });

  it('getContactRoles: one map for many ids, more than one IN list', async () => {
    const roles = Array.from({ length: 205 }, (_, i) => ({ zalo_user_id: `p:6${String(i).padStart(9, '0')}`, role: i % 2 ? 'customer' : 'staff' }));
    await importContactRoles(env, { source: 'zalo_label', roles }, 'tester');
    const ids = roles.map((r) => r.zalo_user_id);
    const map = await getContactRoles(env, [...ids, ...ids, 'p:5000000000', '', 'someone-on-oa']);
    expect(map.size).toBe(205);
    expect(map.get(ids[0]!)).toMatchObject({ role: 'staff', source: 'zalo_label' });
    expect(map.get(ids[203]!)).toMatchObject({ role: 'customer' });
    expect(map.has('p:5000000000')).toBe(false);
    expect((await getContactRoles(env, [])).size).toBe(0);
  });

  it('isInternalRole: manager and staff only', () => {
    expect(isInternalRole('manager')).toBe(true);
    expect(isInternalRole('staff')).toBe(true);
    expect(isInternalRole('customer')).toBe(false);
    expect(isInternalRole(null)).toBe(false);
    expect(isInternalRole(undefined)).toBe(false);
  });

  it('ROLE_ID_RE: p: followed by digits only', () => {
    for (const ok of ['p:1', A, 'p:' + '9'.repeat(32)]) expect(ROLE_ID_RE.test(ok), ok).toBe(true);
    for (const no of ['p:', 'p:12a', 'P:123', ' p:123', 'p:123 ', '123', 'p:' + '9'.repeat(33), 'p:1\np:2']) expect(ROLE_ID_RE.test(no), JSON.stringify(no)).toBe(false);
  });
});
