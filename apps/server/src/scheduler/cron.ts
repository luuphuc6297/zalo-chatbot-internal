// Owner: server-zalo. Cron trigger, every minute (wrangler.toml [triggers]).
// Each tick, in order (one failing step never stops the others):
//   1. recoverStuckFollowups  follow-up jobs whose cron lease ran out
//   2. runDueFollowups        thank_you / check_in / promo_send via ZBS templates (scheduler/followups.ts)
//   3. sweepInbox             re-dispatch webhook events stuck in 'received' > 2 min
//   4. tokenWatch             OA token refresh / age warning (real mode only)
//   5. expireLeases           jobs/draft-jobs.ts (server-core); falls back to expireDraftLeasesFallback while
//                             that function is still a phase 1 stub
//   6. sweepRunnerHealth      jobs/draft-jobs.ts (server-core); skipped while it is a stub
import type { Env } from '../types';
import { NotImplementedError } from '../lib/http';
import { expireLeases, sweepRunnerHealth } from '../jobs/draft-jobs';
import { recoverStuckFollowups, runDueFollowups } from './followups';
import { expireDraftLeasesFallback, sweepInbox, tokenWatch } from './sweeps';

export interface CronReport {
  steps: Record<string, unknown>;
  errors: Record<string, string>;
}

export async function runCron(env: Env, scheduledTime: number): Promise<CronReport> {
  const now = scheduledTime || Date.now();
  const report: CronReport = { steps: {}, errors: {} };

  const step = async (name: string, fn: () => Promise<unknown>) => {
    try {
      report.steps[name] = await fn();
    } catch (err) {
      report.errors[name] = (err instanceof Error ? err.message : String(err)).slice(0, 200);
    }
  };

  await step('recover_followups', () => recoverStuckFollowups(env, now));
  await step('followups', () => runDueFollowups(env, now));
  await step('inbox_sweep', () => sweepInbox(env, now));
  await step('token_watch', () => tokenWatch(env, now));
  await step('expire_leases', async () => {
    try {
      return await expireLeases(env, now);
    } catch (err) {
      if (err instanceof NotImplementedError) return { fallback: await expireDraftLeasesFallback(env, now) };
      throw err;
    }
  });
  await step('runner_health', async () => {
    try {
      return await sweepRunnerHealth(env, now);
    } catch (err) {
      if (err instanceof NotImplementedError) return 'not_implemented';
      throw err;
    }
  });

  if (Object.keys(report.errors).length > 0) {
    console.error(JSON.stringify({ level: 'error', at: 'scheduler.cron', errors: report.errors }));
  }
  return report;
}
