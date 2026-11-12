// The rules added to section 15 after the review of 2026-11-12 (privacy and data integrity of chat guesses):
//  - a number staff removed, replaced or dismissed never comes back through the import (every number is remembered);
//  - a number another customer holds is neither set, suggested nor accepted;
//  - the analyzer's model pass is not offered a contact the import treats as private;
//  - a contact who becomes manager or staff loses its undecided guesses at once;
//  - a sensitive category in a benefit title never reaches the model;
//  - a confirm never writes a second visit on a day that has a recorded one;
//  - a dismissed booking is a tombstone for a visit guess on the same date;
//  - an import that races a staff decision does not undo it and counts only what it wrote;
//  - one audit row per phone decision;
//  - a quoted or list price is not recorded as paid by a one-click confirm;
//  - a chat package with the title of a recorded one is not shown twice nor confirmed twice.
// Every name, phone number and id is synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { confirmChatVisit, importChatFacts } from '../src/lib/chat-facts';
import { benefitTitleForModel, buildCustomerSummary, customerFactsForModel } from '../src/lib/customer-summary';
import { loadModelCatalog } from '../src/lib/profiles';
import { parseLocalDateTime } from '../src/staff-api/customers';
import { DAY_MS, localDate } from '../src/lib/time';
import type { CustomerFacts, Env } from '../src/types';
import { seed } from './core-helpers';
import { GOI, NOW, addBenefit, addProfile, addRole, addVisit, count, newCustomer, nextZaloId, past } from './customers-helpers';
import { addConsent, benefit, call, cand, chatBenefitsOf, chatVisitsOf, doc, enc, entry, factsOf, phone, push, upcoming } from './chat-facts-helpers';

let CV = '';

beforeAll(async () => {
  CV = (await seed()).catalog_version;
});

const ago = (days: number) => localDate(past(days));
const phoneOf = async (id: string) => (await env.DB.prepare('SELECT phone FROM customers WHERE id = ?').bind(id).first<{ phone: string | null }>())!.phone;
const dismissedOf = async (zalo: string) =>
  (await env.DB.prepare('SELECT phone, reason, decided_by FROM chat_phone_dismissed WHERE zalo_user_id = ? ORDER BY phone').bind(zalo).all<Record<string, string>>()).results;
const auditCount = (action: string, entityId?: string) =>
  entityId === undefined
    ? count('SELECT COUNT(*) AS n FROM audit_log WHERE action = ?', action)
    : count('SELECT COUNT(*) AS n FROM audit_log WHERE action = ? AND entity_id = ?', action, entityId);

/** env whose DB.batch runs `before` once, just before its `nth` call (1-based), to put a staff decision in a race. */
function racingEnv(nth: number, before: () => Promise<void>): { env: Env; fired: () => boolean } {
  let calls = 0;
  let fired = false;
  const db = new Proxy(env.DB, {
    get(t, p) {
      if (p === 'batch') {
        return async (s: D1PreparedStatement[]) => {
          calls += 1;
          if (calls === nth && !fired) {
            fired = true;
            await before();
          }
          return t.batch(s);
        };
      }
      const v = (t as unknown as Record<string | symbol, unknown>)[p];
      return typeof v === 'function' ? (v as (...a: unknown[]) => unknown).bind(t) : v;
    },
  });
  return { env: { ...env, DB: db } as Env, fired: () => fired };
}

describe('a phone number staff removed, replaced or dismissed never comes back', () => {
  it('a high number the import set, then staff cleared, is not written back; nor is a replaced number', async () => {
    const a = await newCustomer();
    const first = await push(doc([entry(a.zalo, { phone: phone('0912345801', 'high') })]));
    expect(first.body).toMatchObject({ phones_set: 1, phone_suggestions: 0 });
    expect(await phoneOf(a.id)).toBe('0912345801');

    const cleared = await call('PATCH', `/staff/customers/${a.id}`, { phone: null });
    expect(cleared.status).toBe(200);
    expect(await dismissedOf(a.zalo)).toEqual([{ phone: '0912345801', reason: 'staff_removed', decided_by: 'tester' }]);
    // the audit row of the edit still carries flags only
    const audit = await env.DB.prepare("SELECT before_json, after_json FROM audit_log WHERE action = 'customer.phone_edit' ORDER BY id DESC LIMIT 1").first<Record<string, string>>();
    expect(`${audit!.before_json}${audit!.after_json}`).not.toContain('912345801');

    // the next analyzer run sends the same number at high, then at medium: neither set nor suggested
    for (const conf of ['high', 'medium'] as const) {
      const again = await push(doc([entry(a.zalo, { phone: phone('0912345801', conf) })], { generated_at: Date.UTC(2026, 10, 12, conf === 'high' ? 2 : 3, 0) }));
      expect(again.body, conf).toMatchObject({ phones_set: 0, phone_suggestions: 0 });
      expect(await phoneOf(a.id)).toBeNull();
      expect((await factsOf(a.zalo))!.phone_suggestion).toBeNull();
    }
    // a different number is still set
    expect((await push(doc([entry(a.zalo, { phone: phone('0912345802', 'high') })]))).body).toMatchObject({ phones_set: 1 });
    expect(await phoneOf(a.id)).toBe('0912345802');

    // staff replace it: the replaced number is remembered too, and comes back neither after the new one is cleared
    expect((await call('PATCH', `/staff/customers/${a.id}`, { phone: '0901 234 803' })).status).toBe(200);
    expect((await call('PATCH', `/staff/customers/${a.id}`, { phone: null })).status).toBe(200);
    expect((await dismissedOf(a.zalo)).map((r) => r.phone)).toEqual(['0901234803', '0912345801', '0912345802']);
    expect((await push(doc([entry(a.zalo, { phone: phone('0912345802', 'high') })], { generated_at: Date.UTC(2026, 10, 12, 4, 0) }))).body).toMatchObject({ phones_set: 0 });
    expect(await phoneOf(a.id)).toBeNull();
    // saving the same number again, or another format of it, remembers nothing new
    const b = await newCustomer({ phone: '0912345804' });
    expect((await call('PATCH', `/staff/customers/${b.id}`, { phone: '+84 912 345 804' })).status).toBe(200);
    expect(await dismissedOf(b.zalo)).toEqual([]);
  });

  it('removing a number also clears a pending suggestion of it', async () => {
    const a = await newCustomer({ phone: '0912345811' });
    // a suggestion that waited while the customer had no phone (set here directly)
    await push(doc([entry(a.zalo)]));
    await env.DB.prepare("UPDATE chat_contact_facts SET phone_suggestion = '0912345811' WHERE zalo_user_id = ?").bind(a.zalo).run();
    expect((await call('PATCH', `/staff/customers/${a.id}`, { phone: null })).status).toBe(200);
    expect((await factsOf(a.zalo))!.phone_suggestion).toBeNull();
  });

  it('every dismissed suggestion stays dismissed, not only the latest one', async () => {
    const a = await newCustomer();
    const run = (n: string, conf: 'high' | 'medium', h: number) => push(doc([entry(a.zalo, { phone: phone(n, conf) })], { generated_at: Date.UTC(2026, 10, 12, h, 0) }));
    // suggestions only come from medium numbers while the customer has no phone
    expect((await run('0912345821', 'medium', 1)).body).toMatchObject({ phone_suggestions: 1 });
    expect((await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/dismiss`)).status).toBe(200);
    expect((await run('0912345822', 'medium', 2)).body).toMatchObject({ phone_suggestions: 1 });
    expect((await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/dismiss`)).status).toBe(200);
    expect(await factsOf(a.zalo)).toMatchObject({ phone_state: 'dismissed', phone_dismissed: '0912345822', phone_suggestion: null });
    expect((await dismissedOf(a.zalo)).map((r) => [r.phone, r.reason])).toEqual([
      ['0912345821', 'suggestion_dismissed'],
      ['0912345822', 'suggestion_dismissed'],
    ]);
    // the first number comes back at medium, then at high: neither suggested nor set
    expect((await run('0912345821', 'medium', 3)).body).toMatchObject({ phone_suggestions: 0, phones_set: 0 });
    expect((await run('0912345821', 'high', 4)).body).toMatchObject({ phone_suggestions: 0, phones_set: 0 });
    expect(await phoneOf(a.id)).toBeNull();
    expect((await factsOf(a.zalo))!.phone_suggestion).toBeNull();
  });
});

describe('a suggestion stored before the customer got a phone', () => {
  it('GET /staff/chat-facts leaves it out while the customer has a phone, and offers it again once the phone is removed', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345891', 'medium') })]));
    const shown = async () => (await call('GET', `/staff/chat-facts/${enc(a.zalo)}`)).body.facts.phone_suggestion;
    expect(await shown()).toBe('0912345891');

    // staff type another number into the empty phone: the suggestion stays stored but is not offered
    expect((await call('PATCH', `/staff/customers/${a.id}`, { phone: '0912345892' })).status).toBe(200);
    expect((await factsOf(a.zalo))!.phone_suggestion).toBe('0912345891');
    expect(await shown()).toBeNull();
    // the summary follows the same rule
    expect((await buildCustomerSummary(env, a.id, Date.now()))!.chat).toMatchObject({ phone_suggestion: false });
    // an accept sent anyway still answers 409 and changes nothing
    const r = await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/accept`);
    expect(r.status).toBe(409);
    expect(r.body.error).toMatchObject({ code: 'invalid_state', message: 'the customer already has a phone number' });
    expect(await phoneOf(a.id)).toBe('0912345892');

    // the phone removed: the stored suggestion is offered again (the removed number is the one remembered as dismissed)
    expect((await call('PATCH', `/staff/customers/${a.id}`, { phone: null })).status).toBe(200);
    expect(await shown()).toBe('0912345891');
    expect((await buildCustomerSummary(env, a.id, Date.now()))!.chat).toMatchObject({ phone_suggestion: true });
    expect(await dismissedOf(a.zalo)).toEqual([{ phone: '0912345892', reason: 'staff_removed', decided_by: 'tester' }]);
  });
});

describe('a phone number another customer holds', () => {
  it('is neither set nor suggested by the import, so the visits import still finds its owner', async () => {
    const owner = await newCustomer({ phone: '0912345831' });
    const otherFormat = await newCustomer({ phone: '+84 912 345 832' });
    const a = await newCustomer();
    const noRow = nextZaloId();
    const r = await push(
      doc([
        entry(a.zalo, { phone: phone('0912345831', 'high') }),
        entry(noRow, { phone: phone('0912345832', 'medium') }),
      ]),
    );
    expect(r.body).toMatchObject({ phones_set: 0, phones_taken: 2, phone_suggestions: 0 });
    expect(await phoneOf(a.id)).toBeNull();
    expect((await factsOf(a.zalo))!.phone_suggestion).toBeNull();
    expect((await factsOf(noRow))!.phone_suggestion).toBeNull();
    const byPhone = await call('POST', '/staff/visits/import', { visits: [{ phone: '0912345831', service_id: GOI, visited_at_local: `${ago(3)} 10:00` }] });
    expect(byPhone.body).toMatchObject({ imported: 1, unmatched: [] });
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', owner.id)).toBe(1);
    expect(otherFormat.id).toBeTruthy();
  });

  it('two entries of one request with the same high number: the first gets it, the second does not', async () => {
    const a = await newCustomer();
    const b = await newCustomer();
    const r = await push(doc([entry(a.zalo, { phone: phone('0912345841', 'high') }), entry(b.zalo, { phone: phone('0912345841', 'high') })]));
    expect(r.body).toMatchObject({ phones_set: 1, phones_taken: 1 });
    expect([await phoneOf(a.id), await phoneOf(b.id)]).toEqual(['0912345841', null]);
  });

  it('an accept answers 409 when another customer got the number in the meantime', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345851', 'medium') })]));
    expect((await factsOf(a.zalo))!.phone_suggestion).toBe('0912345851');
    const b = await newCustomer();
    expect((await call('PATCH', `/staff/customers/${b.id}`, { phone: '0912345851' })).status).toBe(200);
    const r = await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/accept`);
    expect(r.status).toBe(409);
    expect(r.body.error).toMatchObject({ code: 'invalid_state', message: 'another customer already has this phone number' });
    expect(await phoneOf(a.id)).toBeNull();
    expect(await auditCount('chat_facts.phone_accept', a.id)).toBe(0);
  });
});

describe('GET /staff/chat-facts/eligible and private relationships', () => {
  it('leaves out a consented contact whose profile is family, friend, personal or staff, unless its role is customer', async () => {
    const T = Date.UTC(2026, 9, 1);
    const mk = async (relationship: string | null, role: 'customer' | null = null) => {
      const c = await newCustomer();
      await addConsent(c.id, 'granted', T);
      if (relationship) await addProfile(c.zalo, { relationship });
      if (role) await addRole(c.zalo, role);
      return c.zalo;
    };
    const quiet = await Promise.all(['family', 'friend', 'personal', 'staff'].map((r) => mk(r)));
    const customer = await mk('customer');
    const unknown = await mk('unknown');
    const none = await mk(null);
    const overridden = await mk('family', 'customer');
    const r = await call('GET', '/staff/chat-facts/eligible');
    expect(r.status).toBe(200);
    const list: string[] = r.body.zalo_user_ids;
    for (const z of quiet) expect(list, z).not.toContain(z);
    for (const z of [customer, unknown, none, overridden]) expect(list, z).toContain(z);
  });
});

describe('a contact who becomes manager or staff', () => {
  async function withGuesses(phoneNumber: string) {
    const c = await newCustomer();
    await push(
      doc([
        entry(c.zalo, {
          visits: [cand(ago(30)), cand(ago(20)), cand(ago(10))],
          upcoming: [upcoming(localDate(Date.now() + 3 * DAY_MS))],
          benefits: [benefit('Gói 5 buổi'), benefit('Gói 3 buổi')],
          phone: phone(phoneNumber, 'medium'),
        }),
      ]),
    );
    const v = await chatVisitsOf(c.zalo);
    await call('POST', `/staff/chat-facts/visits/${v.find((x) => x.local_date === ago(30))!.id}/dismiss`);
    expect((await call('POST', `/staff/chat-facts/visits/${v.find((x) => x.local_date === ago(20))!.id}/confirm`)).status).toBe(200);
    const b = await chatBenefitsOf(c.zalo);
    expect((await call('POST', `/staff/chat-facts/benefits/${b[0]!.id}/confirm`)).status).toBe(200);
    return c;
  }
  const states = async (zalo: string) => ({
    visits: (await chatVisitsOf(zalo)).map((x) => x.state).sort(),
    benefits: (await chatBenefitsOf(zalo)).map((x) => x.state).sort(),
    suggestion: (await factsOf(zalo))!.phone_suggestion,
  });

  it('PUT /staff/roles: the undecided guesses and the phone suggestion go at once; decided rows stay', async () => {
    const c = await withGuesses('0912345861');
    expect(await states(c.zalo)).toEqual({ visits: ['active', 'active', 'confirmed', 'dismissed'], benefits: ['active', 'confirmed'], suggestion: '0912345861' });
    const r = await call('PUT', `/staff/roles/${enc(c.zalo)}`, { role: 'staff' });
    expect(r.status).toBe(200);
    expect(await states(c.zalo)).toEqual({ visits: ['confirmed', 'dismissed'], benefits: ['confirmed'], suggestion: null });
    const facts = (await call('GET', `/staff/chat-facts/${enc(c.zalo)}`)).body.facts;
    expect(facts.visits.every((v: { state: string }) => v.state !== 'active')).toBe(true);
    expect(facts.phone_suggestion).toBeNull();
    // the staff summary of that contact no longer counts a guess either
    expect((await buildCustomerSummary(env, c.id, Date.now()))!.chat).toMatchObject({ visits_counted: 0, phone_suggestion: false, benefits_active: 0 });
  });

  it('role customer removes nothing', async () => {
    const c = await withGuesses('0912345862');
    expect((await call('PUT', `/staff/roles/${enc(c.zalo)}`, { role: 'customer' })).status).toBe(200);
    expect((await states(c.zalo)).suggestion).toBe('0912345862');
    expect((await states(c.zalo)).visits).toContain('active');
  });

  it('POST /staff/roles/import: a label manager or staff cleans up; a staff row that says customer wins over the label', async () => {
    const m = await withGuesses('0912345863');
    const kept = await withGuesses('0912345864');
    await addRole(kept.zalo, 'customer', 'staff');
    const r = await call('POST', '/staff/roles/import', {
      source: 'zalo_label',
      roles: [
        { zalo_user_id: m.zalo, role: 'manager' },
        { zalo_user_id: kept.zalo, role: 'staff' },
      ],
    });
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ imported: 1, kept_staff: 1 });
    expect(await states(m.zalo)).toEqual({ visits: ['confirmed', 'dismissed'], benefits: ['confirmed'], suggestion: null });
    expect((await states(kept.zalo)).visits).toContain('active');
    expect((await states(kept.zalo)).suggestion).toBe('0912345864');
  });
});

describe('a sensitive category in a benefit title', () => {
  it('is replaced by a generic title for the model after a confirm; staff still see the title', async () => {
    const c = await newCustomer();
    await push(
      doc([
        entry(c.zalo, {
          benefits: [
            benefit('Gói 10 buổi – Chăm sóc vùng kín'),
            benefit('Gói 10 buổi – Diện chẩn, ấn huyệt'),
            benefit('goi 5 buoi giac hoi', { total_count: 5, remaining: 5 }),
            benefit('Gói 10 buổi gội', { total_count: 10, remaining: 4 }),
          ],
        }),
      ]),
    );
    for (const b of await chatBenefitsOf(c.zalo)) expect((await call('POST', `/staff/chat-facts/benefits/${b.id}/confirm`)).status, b.title).toBe(200);
    const f = (await customerFactsForModel(env, c.id, CV, NOW)) as Extract<CustomerFacts, { found: true }>;
    expect(f.found).toBe(true);
    expect(f.unused_benefits.map((b) => b.title).sort()).toEqual(['Gói 10 buổi gội', 'Gói dịch vụ', 'Gói dịch vụ', 'Gói dịch vụ']);
    const json = JSON.stringify(f);
    for (const hidden of ['vùng kín', 'Diện chẩn', 'ấn huyệt', 'giac hoi']) expect(json, hidden).not.toContain(hidden);
    // the staff summary keeps the real titles
    const s = await buildCustomerSummary(env, c.id, NOW);
    expect(s!.benefits.map((b) => b.title)).toContain('Gói 10 buổi – Chăm sóc vùng kín');
  });

  it('benefitTitleForModel matches the category words as whole words, with or without accents', async () => {
    const catalog = await loadModelCatalog(env);
    const t = (title: string, kind: 'package' | 'voucher' = 'package') => benefitTitleForModel({ kind, title, service_id: null }, catalog);
    for (const title of ['Liệu trình HƠ NGẢI 6 buổi', 'Voucher yoni', 'combo dien chan', 'Gói giác-hơi 3 buổi']) expect(t(title), title).toBe('Gói dịch vụ');
    expect(t('Voucher Vùng Kín', 'voucher')).toBe('Voucher');
    for (const title of ['Gói 10 buổi gội đầu', 'Voucher sinh nhật', 'Gói thanh huyết 3 buổi', 'Combo yonix']) expect(t(title), title).toBe(title);
  });
});

describe('confirm and a recorded visit on the same day', () => {
  it('answers 409 and writes nothing when the date already has a recorded visit', async () => {
    const c = await newCustomer();
    await push(doc([entry(c.zalo, { visits: [cand(ago(12)), cand(ago(14), { time: '10:00', amount_vnd: 300000 })] })]));
    const rows = await chatVisitsOf(c.zalo);
    const g12 = rows.find((x) => x.local_date === ago(12))!;
    const g14 = rows.find((x) => x.local_date === ago(14))!;
    // staff record the real visits of 12 days ago and of 13 days ago
    await addVisit(c.id, past(12, 18), GOI, { amount: 400000 });
    await addVisit(c.id, past(13, 11), GOI, { amount: 300000 });

    const facts = (await call('GET', `/staff/chat-facts/${enc(c.zalo)}`)).body.facts;
    expect(facts.visits.map((v: { local_date: string; recorded_day: boolean }) => [v.local_date, v.recorded_day])).toEqual([
      [ago(12), true],
      [ago(14), false],
    ]);

    const same = await call('POST', `/staff/chat-facts/visits/${g12.id}/confirm`, {});
    expect(same.status).toBe(409);
    expect(same.body.error).toMatchObject({ code: 'invalid_state', message: 'a visit is already recorded on this date' });
    // a corrected date onto a recorded day is refused too
    const moved = await call('POST', `/staff/chat-facts/visits/${g14.id}/confirm`, { visited_at_local: `${ago(13)} 11:30` });
    expect(moved.status).toBe(409);
    expect(moved.body.error.message).toBe('a visit is already recorded on this date');
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', c.id)).toBe(2);
    expect((await chatVisitsOf(c.zalo)).map((x) => x.state)).toEqual(['active', 'active']);
    expect(await auditCount('chat_facts.visit_confirm', g12.id)).toBe(0);
    // the summary still counts the day once, with the recorded amount
    expect(await buildCustomerSummary(env, c.id, Date.now())).toMatchObject({ visits_total: 3, chat: { visits_counted: 1 } });
    // the other guess on its own date is fine
    expect((await call('POST', `/staff/chat-facts/visits/${g14.id}/confirm`, {})).status).toBe(200);
  });

  it('a visit recorded between the check and the write stops the confirm too', async () => {
    const c = await newCustomer();
    await push(doc([entry(c.zalo, { visits: [cand(ago(16))] })]));
    const g = (await chatVisitsOf(c.zalo))[0]!;
    const race = racingEnv(1, async () => {
      await addVisit(c.id, past(16, 9), GOI, { amount: 200000 });
    });
    await expect(confirmChatVisit(race.env, g.id, {}, 'tester')).rejects.toMatchObject({ status: 409, message: 'a visit is already recorded on this date' });
    expect(race.fired()).toBe(true);
    expect(await count('SELECT COUNT(*) AS n FROM visits WHERE customer_id = ?', c.id)).toBe(1);
    expect((await chatVisitsOf(c.zalo))[0]).toMatchObject({ state: 'active', confirmed_visit_id: null });
    expect(await auditCount('chat_facts.visit_confirm', g.id)).toBe(0);
  });
});

describe('a dismissed upcoming booking', () => {
  it('is also a tombstone for a visit guess on the same date', async () => {
    const c = await newCustomer();
    await push(doc([entry(c.zalo, { upcoming: [upcoming('2026-11-20')] })]));
    const booking = (await chatVisitsOf(c.zalo))[0]!;
    expect((await call('POST', `/staff/chat-facts/visits/${booking.id}/dismiss`)).status).toBe(200);
    // a later run reads the same booking as a past visit
    const later = Date.UTC(2026, 10, 22, 3, 0);
    const r = await push(doc([entry(c.zalo, { visits: [cand('2026-11-20', { confidence: 'medium', amount_vnd: null, amount_source: null })] })], { generated_at: later }));
    expect(r.body).toMatchObject({ visits_imported: 0, visits_tombstoned: 1 });
    expect((await chatVisitsOf(c.zalo)).map((x) => [x.kind, x.local_date, x.state])).toEqual([['upcoming', '2026-11-20', 'dismissed']]);
    const s = await buildCustomerSummary(env, c.id, Date.UTC(2026, 10, 23, 3, 0));
    expect(s).toMatchObject({ visits_total: 0, last_visit: null });
    // an active booking on another date does not stop that date's visit
    await push(doc([entry(c.zalo, { upcoming: [upcoming('2026-11-25')] })]));
    expect((await push(doc([entry(c.zalo, { visits: [cand('2026-11-25')] })], { generated_at: later + DAY_MS }))).body).toMatchObject({ visits_imported: 1 });
  });
});

describe('an import that races a staff decision', () => {
  it('counts only the rows it changed: a confirm and a dismiss in between are kept and not counted', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { visits: [cand('2026-10-20'), cand('2026-10-21'), cand('2026-10-22')] })]));
    const rows = await chatVisitsOf(a.zalo);
    const r20 = rows.find((x) => x.local_date === '2026-10-20')!; // the next document drops it: a planned DELETE
    const r21 = rows.find((x) => x.local_date === '2026-10-21')!; // the next document changes it: a planned UPDATE
    // batch 1 is the import's read of the chat tables, batch 2 its write
    const race = racingEnv(2, async () => {
      expect((await call('POST', `/staff/chat-facts/visits/${r20.id}/confirm`, {})).status).toBe(200);
      expect((await call('POST', `/staff/chat-facts/visits/${r21.id}/dismiss`)).status).toBe(200);
    });
    const at = Date.UTC(2026, 10, 12, 4, 0);
    const res = await importChatFacts(race.env, doc([entry(a.zalo, { visits: [cand('2026-10-21', { amount_vnd: 999000 }), cand('2026-10-22')] })], { generated_at: at }), 'tester', at);
    expect(race.fired()).toBe(true);
    expect(res).toMatchObject({ visits_updated: 0, visits_removed: 0, visits_imported: 0 });
    const audit = await env.DB.prepare("SELECT after_json FROM audit_log WHERE action = 'chat_facts.import' ORDER BY id DESC LIMIT 1").first<{ after_json: string }>();
    expect(JSON.parse(audit!.after_json)).toMatchObject({ visits_updated: 0, visits_removed: 0 });
    const after = await chatVisitsOf(a.zalo);
    expect(after.find((x) => x.local_date === '2026-10-20')).toMatchObject({ state: 'confirmed' });
    expect(after.find((x) => x.local_date === '2026-10-21')).toMatchObject({ state: 'dismissed', amount_vnd: 350000 });
  });

  it('a phone accept in between: the suggestion does not come back', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345871', 'medium') })]));
    const race = racingEnv(2, async () => {
      expect((await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/accept`)).status).toBe(200);
    });
    const at = Date.UTC(2026, 10, 12, 5, 0);
    const res = await importChatFacts(race.env, doc([entry(a.zalo, { phone: phone('0912345871', 'medium') })], { generated_at: at }), 'tester', at);
    expect(race.fired()).toBe(true);
    expect(res.phones_set).toBe(0);
    expect(await phoneOf(a.id)).toBe('0912345871');
    expect((await factsOf(a.zalo))!.phone_suggestion).toBeNull();
    expect((await call('GET', `/staff/chat-facts/${enc(a.zalo)}`)).body.facts.phone_suggestion).toBeNull();
  });
});

describe('two phone decisions at the same time', () => {
  it('two accepts: one 200, one 409, one audit row', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345881', 'medium') })]));
    const rs = await Promise.all([call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/accept`), call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/accept`)]);
    expect(rs.map((r) => r.status).sort()).toEqual([200, 409]);
    expect(await auditCount('chat_facts.phone_accept', a.id)).toBe(1);
  });

  it('two dismisses: one 200, one 409, one audit row', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345882', 'medium') })]));
    const rs = await Promise.all([call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/dismiss`), call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/dismiss`)]);
    expect(rs.map((r) => r.status).sort()).toEqual([200, 409]);
    expect(await auditCount('chat_facts.phone_dismiss', a.zalo)).toBe(1);
    expect(await dismissedOf(a.zalo)).toHaveLength(1);
  });

  it('an accept that loses the race to a dismiss says the suggestion was decided', async () => {
    const a = await newCustomer();
    await push(doc([entry(a.zalo, { phone: phone('0912345883', 'medium') })]));
    const { acceptPhoneSuggestion } = await import('../src/lib/chat-facts');
    const race = racingEnv(1, async () => {
      expect((await call('POST', `/staff/chat-facts/${enc(a.zalo)}/phone/dismiss`)).status).toBe(200);
    });
    await expect(acceptPhoneSuggestion(race.env, a.zalo, 'tester')).rejects.toMatchObject({ status: 409, message: 'the suggestion was decided in the meantime' });
    expect(await phoneOf(a.id)).toBeNull();
    expect(await auditCount('chat_facts.phone_accept', a.id)).toBe(0);
  });
});

describe('the amount of a one-click confirm', () => {
  it('copies a paid amount, not a quoted or list price; staff can still send what was paid', async () => {
    const c = await newCustomer();
    await push(
      doc([
        entry(c.zalo, {
          visits: [
            cand(ago(40), { amount_vnd: 350000, amount_source: 'paid' }),
            cand(ago(41), { amount_vnd: 300000, amount_source: 'quoted' }),
            cand(ago(42), { amount_vnd: 250000, amount_source: 'list_price' }),
            cand(ago(43), { amount_vnd: 300000, amount_source: 'quoted' }),
          ],
        }),
      ]),
    );
    const rows = await chatVisitsOf(c.zalo);
    const byDate = (d: string) => rows.find((x) => x.local_date === d)!.id;
    const confirm = async (d: string, body: unknown) => (await call('POST', `/staff/chat-facts/visits/${byDate(d)}/confirm`, body)).body.visit.amount_vnd;
    const before = (await buildCustomerSummary(env, c.id, Date.now()))!.lifetime_spend_vnd;
    expect(before).toBe(350000); // only the paid guess is spend
    expect(await confirm(ago(40), {})).toBe(350000);
    expect(await confirm(ago(41), {})).toBeNull();
    expect(await confirm(ago(42), {})).toBeNull();
    expect(await confirm(ago(43), { amount_vnd: 300000 })).toBe(300000);
    expect((await buildCustomerSummary(env, c.id, Date.now()))!.lifetime_spend_vnd).toBe(650000);
  });
});

describe('a chat package with the title of a recorded one', () => {
  it('is not shown to the model twice, is not counted, and cannot be confirmed as a second package', async () => {
    const c = await newCustomer();
    await addBenefit(c.id, { title: 'Gói 10 buổi gội', total: 10, used: 3 });
    await push(doc([entry(c.zalo, { benefits: [benefit('GÓI 10  buổi gội'), benefit('Voucher sinh nhật', { kind: 'voucher', total_count: 1, remaining: 1 })] })]));
    const f = (await customerFactsForModel(env, c.id, CV, NOW)) as Extract<CustomerFacts, { found: true }>;
    expect(f.unused_benefits).toEqual([expect.objectContaining({ title: 'Gói 10 buổi gội', remaining: 7 })]);
    expect(f.benefits_from_chat).toEqual([{ kind: 'voucher', remaining: 1 }]);
    expect((await buildCustomerSummary(env, c.id, NOW))!.chat).toMatchObject({ benefits_active: 1 });

    const facts = (await call('GET', `/staff/chat-facts/${enc(c.zalo)}`)).body.facts;
    const pkg = facts.benefits.find((b: { kind: string }) => b.kind === 'package');
    const voucher = facts.benefits.find((b: { kind: string }) => b.kind === 'voucher');
    expect([pkg.recorded_title, voucher.recorded_title]).toEqual([true, false]);

    const twice = await call('POST', `/staff/chat-facts/benefits/${pkg.id}/confirm`, {});
    expect(twice.status).toBe(409);
    expect(twice.body.error).toMatchObject({ code: 'invalid_state', message: 'the customer already has a benefit with this title' });
    expect(await count("SELECT COUNT(*) AS n FROM customer_benefits WHERE customer_id = ? AND status = 'active'", c.id)).toBe(1);
    // a second package of the same kind gets another title
    const renamed = await call('POST', `/staff/chat-facts/benefits/${pkg.id}/confirm`, { title: 'Gói 10 buổi gội (lần 2)' });
    expect(renamed.status).toBe(200);
    expect(await count("SELECT COUNT(*) AS n FROM customer_benefits WHERE customer_id = ? AND status = 'active'", c.id)).toBe(2);
    // a void package does not block the title
    const d = await newCustomer();
    await addBenefit(d.id, { title: 'Gói 5 buổi', status: 'void' });
    await push(doc([entry(d.zalo, { benefits: [benefit('Gói 5 buổi', { total_count: 5, remaining: 5 })] })]));
    const dPkg = (await chatBenefitsOf(d.zalo))[0]!;
    expect((await call('POST', `/staff/chat-facts/benefits/${dPkg.id}/confirm`)).status).toBe(200);
  });
});

describe('the confirmed date stays in the past', () => {
  it('a guess confirmed with an old time is still refused in the future', async () => {
    const c = await newCustomer();
    await push(doc([entry(c.zalo, { visits: [cand(ago(5))] })]));
    const g = (await chatVisitsOf(c.zalo))[0]!;
    const r = await call('POST', `/staff/chat-facts/visits/${g.id}/confirm`, { visited_at_local: `${localDate(Date.now() + 3 * DAY_MS)} 10:00` });
    expect(r.status).toBe(422);
    expect(r.body.error.details.field).toBe('visited_at_local');
    expect(parseLocalDateTime(`${ago(5)} 15:00`)).toBe(g.visited_at);
  });
});
