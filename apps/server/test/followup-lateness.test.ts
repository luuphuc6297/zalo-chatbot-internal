// A visit recorded long after it happened (live run-through of 2026-11-12, finding D2): POST /staff/visits creates its
// thank_you and check_in jobs with status 'queued' and a run_at already in the past. The scheduler never sends them
// late: recordVisit gives every follow-up job max_lateness_ms = 6 h, and the scheduler checks run_at + max_lateness_ms
// before the send window, consent and the template, so once followup_care consent, scheduled_sends_enabled and
// outbound_enabled allow a send the jobs become 'expired' (last_error too_late) and nothing is sent. A visit recorded in
// time is still thanked. Every name, phone number and id is synthetic.
import { env } from 'cloudflare:test';
import { beforeAll, describe, expect, it } from 'vitest';
import { FOLLOWUP_MAX_LATENESS_MS } from '../src/jobs/followup-jobs';
import { runDueFollowups } from '../src/scheduler/followups';
import { HOUR_MS } from '../src/lib/time';
import { seed, setFlags, staff, uniq } from './core-helpers';
import { GOI, past } from './customers-helpers';
import { consentedThread, outboxOf, type PersonalContact } from './personal-helpers';

beforeAll(async () => {
  await seed();
});

/** A consented personal contact who also agreed to follow-up care messages. */
async function caredFor(): Promise<PersonalContact> {
  const p = await consentedThread();
  await env.DB.prepare("INSERT INTO consents (id, customer_id, purpose, status, source, recorded_at) VALUES (?, ?, 'followup_care', 'granted', 'staff', ?)")
    .bind(uniq('cns_'), p.customerId, Date.now() - 60 * 24 * HOUR_MS)
    .run();
  return p;
}

const jobRow = (id: string) =>
  env.DB.prepare('SELECT status, last_error, run_at, max_lateness_ms FROM jobs WHERE id = ?').bind(id).first<{ status: string; last_error: string | null; run_at: number; max_lateness_ms: number | null }>();

const templateMessages = async (cid: string) =>
  (await env.DB.prepare("SELECT id FROM messages WHERE conversation_id = ? AND kind = 'template'").bind(cid).all()).results.length;

describe('follow-up jobs of a visit recorded late', () => {
  it('a visit recorded 23 days late: both jobs are queued in the past, then expire instead of being sent', async () => {
    const p = await caredFor();
    const v = await staff('POST', '/staff/visits', { customer_id: p.customerId, service_id: GOI, visited_at: past(23, 14) });
    expect(v.status).toBe(200);
    // the response shape and the stored status are unchanged: the scheduler decides at run time
    expect(Object.keys(v.body).sort()).toEqual(['jobs', 'visit_id']);
    expect(v.body.jobs.map((j: any) => [j.type, j.status])).toEqual([
      ['thank_you', 'queued'],
      ['check_in', 'queued'],
    ]);
    const now = Date.now();
    for (const j of v.body.jobs) {
      expect(Object.keys(j).sort()).toEqual(['job_id', 'run_at', 'status', 'type']);
      expect((await jobRow(j.job_id))!.max_lateness_ms).toBe(FOLLOWUP_MAX_LATENESS_MS);
      expect(j.run_at + FOLLOWUP_MAX_LATENESS_MS).toBeLessThan(now);
    }

    // while scheduled_sends_enabled is false nothing runs and the jobs stay queued
    const outboxBefore = (await outboxOf(p.threadId)).length;
    await runDueFollowups(env, now);
    for (const j of v.body.jobs) expect((await jobRow(j.job_id))!.status).toBe('queued');

    // consent granted and both send flags true: the jobs expire, nothing reaches the outbox or the conversation
    await setFlags({ scheduled_sends_enabled: true, outbound_enabled: true });
    const counts = await runDueFollowups(env, now);
    expect(counts).toMatchObject({ expired: 2, done: 0, needs_staff: 0, failed: 0 });
    for (const j of v.body.jobs) expect(await jobRow(j.job_id)).toMatchObject({ status: 'expired', last_error: 'too_late' });
    expect(await outboxOf(p.threadId)).toHaveLength(outboxBefore);
    expect(await templateMessages(p.cid)).toBe(0);
    // a later tick changes nothing
    await runDueFollowups(env, now + 60_000);
    for (const j of v.body.jobs) expect((await jobRow(j.job_id))!.status).toBe('expired');
    await setFlags({ scheduled_sends_enabled: false });
  });

  it('a visit recorded in time: the thank-you is still sent within the lateness bound', async () => {
    const p = await caredFor();
    // yesterday 10:00 local: thank_you at 06:00 today is moved to 09:00 today; check_in is tomorrow 10:00
    const v = await staff('POST', '/staff/visits', { customer_id: p.customerId, service_id: GOI, visited_at: past(1, 10) });
    expect(v.status).toBe(200);
    const thanks = v.body.jobs.find((j: any) => j.type === 'thank_you');
    const checkIn = v.body.jobs.find((j: any) => j.type === 'check_in');
    expect([thanks.status, checkIn.status]).toEqual(['queued', 'queued']);

    await setFlags({ scheduled_sends_enabled: true, outbound_enabled: true });
    const outboxBefore = (await outboxOf(p.threadId)).length;
    // the cron runs 2 h after the planned time (11:00 local): late, but inside max_lateness_ms and the send window
    const counts = await runDueFollowups(env, thanks.run_at + 2 * HOUR_MS);
    expect(counts).toMatchObject({ done: 1, expired: 0 });
    expect(await jobRow(thanks.job_id)).toMatchObject({ status: 'done', last_error: null });
    expect(await jobRow(checkIn.job_id)).toMatchObject({ status: 'queued' });
    expect(await outboxOf(p.threadId)).toHaveLength(outboxBefore + 1);
    expect(await templateMessages(p.cid)).toBe(1);
    await setFlags({ scheduled_sends_enabled: false });
  });
});
