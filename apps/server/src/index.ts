// SHARED FILE: builders may only make ADDITIVE edits (new routes / middleware). Re-read before editing.
// Route table mirrors docs/contracts.md. Handlers live in module files owned by one builder each.
import { Hono } from 'hono';
import type { AppEnv, Env } from './types';
import { onError, errorJson } from './lib/http';
import { newId } from './lib/ids';
import { requireDev, requireRunner, requireStaff } from './lib/auth';
import { handleWebhook } from './zalo/webhook';
import { handlePersonalWebhook } from './zalo/personal';
import * as bridge from './bridge/handlers';
import { oauthCallback, oauthStart, oauthStatus } from './zalo/oauth';
import { runCron } from './scheduler/cron';
import * as runner from './runner-api/handlers';
import * as rooms from './runner-api/rooms';
import * as staff from './staff-api/handlers';
import * as profiles from './staff-api/profiles';
import * as menu from './staff-api/menu';
import * as customers from './staff-api/customers';
import * as chatFacts from './staff-api/chat-facts';
import { loadEmbeddedCatalog, seed } from './dev/seed';

export { ConversationDO } from './conversation-do';

export const app = new Hono<AppEnv>();

app.use('*', async (c, next) => {
  c.set('requestId', c.req.header('cf-ray') ?? newId('req'));
  await next();
});
app.onError(onError);
app.notFound((c) => errorJson(c, 404, 'not_found', 'route not found'));

app.get('/health', (c) => c.json({ ok: true, env: c.env.ENV, zalo_mode: c.env.ZALO_MODE }));

// ---- Zalo webhook (no bearer auth; signature checked inside per WEBHOOK_SIGNATURE_MODE)
app.post('/zalo/webhook', handleWebhook);
app.get('/zalo/oauth/start', oauthStart);
app.get('/zalo/oauth/callback', (c) => oauthCallback(c));
// ---- Personal Zalo channel (docs/contracts.md "Personal Zalo channel"): Bearer + HMAC of ZALO_PERSONAL_WEBHOOK_SECRET
app.post('/zalo/personal/webhook', handlePersonalWebhook);

// ---- Bridge API (apps/zalo-bridge): Bearer RUNNER_TOKEN + X-Bridge-Id; status also accepts the staff token
app.use('/bridge/outbox/*', bridge.requireBridge);
app.post('/bridge/outbox/claim', bridge.claim);
app.post('/bridge/outbox/:id/result', bridge.result);
app.get('/bridge/status', bridge.requireBridgeOrStaff, bridge.status);

// ---- Runner API
app.use('/runner/*', requireRunner);
app.post('/runner/jobs/claim', runner.claimJob);
app.post('/runner/jobs/:id/heartbeat', runner.heartbeatJob);
app.post('/runner/jobs/:id/draft', runner.submitDraft);
app.post('/runner/jobs/:id/fail', runner.failJob);
app.post('/runner/tools/:name', runner.callTool);
app.get('/runner/prompt', runner.getPrompt);
app.post('/runner/status', runner.postStatus);
// ---- Rooms feed (docs/contracts.md section 14.7, src/runner-api/rooms.ts)
app.post('/runner/rooms/feed', rooms.feed);
app.post('/runner/rooms/ack', rooms.ack);

// ---- Staff API
app.use('/staff/*', requireStaff);
app.get('/staff/conversations', staff.listConversations);
app.get('/staff/conversations/:id', staff.getConversation);
app.post('/staff/conversations/:id/takeover', staff.takeover);
app.post('/staff/conversations/:id/release', staff.release);
app.post('/staff/conversations/:id/staff-only', staff.markStaffOnly);
app.put('/staff/conversations/:id/mode', staff.setMode);
app.put('/staff/conversations/:id/auto-reply', staff.setAutoReply);
app.post('/staff/conversations/:id/send', staff.manualSend);
app.post('/staff/drafts/:id/approve', staff.approveDraft);
app.post('/staff/drafts/:id/reject', staff.rejectDraft);
app.get('/staff/flags', staff.getFlagsHandler);
app.put('/staff/flags', staff.putFlagsHandler);
app.get('/staff/handoffs', staff.listHandoffs);
app.post('/staff/handoffs/:id/resolve', staff.resolveHandoff);
app.get('/staff/booking-requests', staff.listBookingRequests);
app.post('/staff/booking-requests/:id/status', staff.setBookingStatus);
app.post('/staff/visits', staff.createVisit);
app.get('/staff/runner', staff.getRunner);
app.put('/staff/runner/account', staff.putRunnerAccount);
app.get('/staff/outbox', staff.listOutbox);
app.post('/staff/outbox/:id/decide', bridge.decide);
app.get('/staff/zalo/token', oauthStatus);
app.post('/staff/catalog/load-embedded', loadEmbeddedCatalog);
// ---- Contact profiles of the personal channel (docs/contracts.md section 13)
app.post('/staff/profiles/import', profiles.importHandler);
app.get('/staff/profiles', profiles.listHandler);
app.get('/staff/profiles/:zalo_user_id', profiles.getHandler);
app.patch('/staff/profiles/:zalo_user_id', profiles.patchHandler);
// ---- Menu images for staff: slide index, thumbnails, "Gửi menu" (task C, src/staff-api/menu.ts)
app.get('/staff/menu-images', menu.listMenuImages);
app.get('/staff/menu-images/:group/:n', menu.menuThumb);
app.post('/staff/conversations/:id/menu-images', menu.sendMenuImages);
// ---- Contact roles, visit history, benefits and phone (docs/contracts.md sections 14.3 and 14.5, src/staff-api/customers.ts)
app.post('/staff/roles/import', customers.importRoles);
app.get('/staff/roles', customers.listRoles);
app.put('/staff/roles/:zalo_user_id', customers.putRole);
app.post('/staff/visits/import', customers.importVisitsHandler);
app.get('/staff/visits', customers.listVisitsHandler);
app.get('/staff/benefits', customers.listBenefitsHandler);
app.post('/staff/benefits', customers.createBenefitHandler);
app.patch('/staff/benefits/:id', customers.patchBenefitHandler);
app.patch('/staff/customers/:id', customers.patchCustomerHandler);
// ---- Customer facts guessed from old chats (docs/contracts.md section 15.11, src/staff-api/chat-facts.ts). The fixed
// paths come before the ones with :zalo_user_id.
app.post('/staff/chat-facts/import', chatFacts.importHandler);
app.get('/staff/chat-facts/eligible', chatFacts.eligibleHandler);
app.post('/staff/chat-facts/visits/:id/confirm', chatFacts.confirmVisitHandler);
app.post('/staff/chat-facts/visits/:id/dismiss', chatFacts.dismissVisitHandler);
app.post('/staff/chat-facts/benefits/:id/confirm', chatFacts.confirmBenefitHandler);
app.post('/staff/chat-facts/benefits/:id/dismiss', chatFacts.dismissBenefitHandler);
app.get('/staff/chat-facts/:zalo_user_id', chatFacts.getHandler);
app.post('/staff/chat-facts/:zalo_user_id/phone/accept', chatFacts.acceptPhoneHandler);
app.post('/staff/chat-facts/:zalo_user_id/phone/dismiss', chatFacts.dismissPhoneHandler);

// ---- Dev (ENV=dev only)
app.use('/dev/*', requireDev);
app.post('/dev/seed', seed);

export default {
  fetch: app.fetch,
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCron(env, controller.scheduledTime));
  },
} satisfies ExportedHandler<Env>;
