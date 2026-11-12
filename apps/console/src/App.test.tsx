import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationDetail, ConversationSummary, HandoffView, OutboxItem } from './api';
import { App } from './App';
import { conversationBadges, vnLocalToMs } from './labels';
import { sortHandoffs } from './screens/Handoffs';
import { loginCommand, outboxText } from './screens/Settings';

const summary: ConversationSummary = {
  id: 'cnv_1',
  customer: {
    id: 'cus_1',
    zalo_user_id: '2468458835291979',
    display_name: 'Chị Lan',
    phone: null,
    minor_flag: null,
    last_user_interaction_at: 1762500000000,
  },
  bot_state: 'bot_active',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: true,
  takeover_by: null,
  takeover_until: null,
  last_message_at: 1762500000000,
  last_message_preview: 'gội đầu bao nhiêu tiền ạ',
  pending_drafts: 1,
  open_handoffs: 0,
};

const detail: ConversationDetail = {
  conversation: { ...summary, session_id: null, session_turns: 0, catalog_version: 'cv_seed_20261107' },
  messages: [
    {
      id: 'msg_1',
      direction: 'inbound',
      source: 'customer',
      kind: 'text',
      text: '<b>xin chào</b><img src=x onerror=alert(1)>',
      attachments: [],
      send_state: 'not_applicable',
      draft_id: null,
      staff_id: null,
      created_at: 1762500000000,
      sent_at: null,
    },
  ],
  drafts: [
    {
      id: 'drf_1',
      job_id: 'job_1',
      conversation_id: 'cnv_1',
      text: 'Dạ gội đầu thư giãn 50 phút giá 199k ạ.',
      final_text: null,
      status: 'blocked',
      checker: { passed: false, issues: [{ rule: 'price', detail: 'số tiền viết tắt k', excerpt: '199k' }], checked_at: 1762500008000 },
      account_label: 'ultra-anlnt',
      cost_usd_equiv: 0.02,
      catalog_version: 'cv_seed_20261107',
      created_at: 1762500008000,
      decided_by: null,
      decided_at: null,
    },
  ],
  handoffs: [],
  booking_requests: [],
  consents: [],
};

type Call = { method: string; url: string; body: unknown };
let calls: Call[] = [];
let zaloMode: 'mock' | 'personal' = 'mock';
// Section 14 fields the server adds to the conversation; empty = a server before 2026-11-12.
let convExtra: Partial<ConversationSummary> = {};

const unknownPersonalRow: OutboxItem = {
  id: 'obx_9',
  kind: 'cs_buttons',
  zalo_mode: 'personal',
  conversation_id: 'cnv_9',
  zalo_user_id: 'p:9100123',
  message_id: 'msg_9',
  payload: {},
  status: 'unknown',
  zalo_msg_id: null,
  error: 'timeout: zalo-agent did not finish in time',
  created_at: 1762500000000,
  sent_at: null,
  channel: 'personal',
  thread_id: '9100123',
  text: 'Nhắn "đồng ý" để trò chuyện với trợ lý AI.',
  attempts: 1,
  next_attempt_at: null,
  lease_until: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

beforeEach(() => {
  calls = [];
  zaloMode = 'mock';
  convExtra = {};
  localStorage.setItem('thomhouse.console.config', JSON.stringify({ baseUrl: '', staffToken: 'test-token', staffId: 'lan' }));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const headers = new Headers(init?.headers);
      if (url !== '/health' && headers.get('authorization') !== 'Bearer test-token') return json({ error: { code: 'unauthorized', message: 'no' } }, 401);
      if (url === '/health') return json({ ok: true, env: 'dev', zalo_mode: zaloMode });
      if (url.startsWith('/staff/outbox?')) return json({ items: [unknownPersonalRow], next_cursor: null });
      if (url === '/staff/outbox/obx_9/decide') return json({ id: 'obx_9', status: 'sent', attempts: 1, next_attempt_at: null, ignored: false });
      if (url === '/bridge/status') {
        return json({ zalo_mode: 'personal', outbound_enabled: true, last_claim_at: 1762500000000, last_result_at: null, bridges: [],
          counts: { queued: 0, leased: 0, sent: 3, failed: 0, unknown: 1 }, oldest_queued_at: null });
      }
      if (url.startsWith('/staff/conversations?')) return json({ items: [{ ...summary, ...convExtra }], next_cursor: null });
      if (url === '/staff/conversations/cnv_1') return json({ ...detail, conversation: { ...detail.conversation, ...convExtra } });
      if (url === '/staff/conversations/cnv_1/auto-reply' && method === 'PUT') {
        const value = (JSON.parse(String(init?.body)) as { auto_reply: 'on' | 'off' }).auto_reply;
        convExtra = { auto_reply: value, mode_override: null, effective_mode: value === 'on' ? 'auto_allowed' : 'approve_each' };
        return json({ conversation: { ...summary, ...convExtra } });
      }
      if (url.startsWith('/staff/handoffs')) return json({ items: [], next_cursor: null });
      if (url === '/staff/conversations/cnv_1/staff-only') return json({ conversation: { ...summary, bot_state: 'staff_only' } });
      if (url === '/staff/drafts/drf_1/approve') {
        return json({ draft: { ...detail.drafts[0], status: 'sent' }, message: { ...detail.messages[0], id: 'msg_2' } });
      }
      return json({ error: { code: 'not_found', message: 'nope' } }, 404);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('App', () => {
  it('lists conversations with badges and renders customer text as plain text', async () => {
    render(<App />);
    expect(await screen.findByText('Chị Lan')).toBeTruthy();
    for (const label of ['Hội thoại', 'Cần nhân viên', 'Yêu cầu đặt lịch', 'Ghi nhận buổi làm', 'Cài đặt']) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy();
    }
    expect(screen.getByText('chờ duyệt (1)')).toBeTruthy();
    expect(screen.getAllByText('cần chú ý').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText('Chị Lan'));
    const raw = await screen.findByText('<b>xin chào</b><img src=x onerror=alert(1)>');
    const messages = raw.closest('ol')!;
    expect(messages.querySelector('b')).toBeNull();
    expect(messages.querySelector('img')).toBeNull();
  });

  it('requires an explicit override before approving a draft that failed the checker', async () => {
    render(<App />);
    fireEvent.click(await screen.findByText('Chị Lan'));
    await screen.findByText('Dạ gội đầu thư giãn 50 phút giá 199k ạ.');
    const draft = screen.getByText('Dạ gội đầu thư giãn 50 phút giá 199k ạ.').closest('.draft') as HTMLElement;
    expect(within(draft).getByText(/số tiền viết tắt k/)).toBeTruthy();

    const approve = within(draft).getByRole('button', { name: 'Duyệt và gửi' }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    fireEvent.click(within(draft).getByRole('checkbox'));
    expect(approve.disabled).toBe(false);
    fireEvent.click(approve);

    await waitFor(() => expect(calls.some((c) => c.url === '/staff/drafts/drf_1/approve')).toBe(true));
    const call = calls.find((c) => c.url === '/staff/drafts/drf_1/approve')!;
    expect(call.method).toBe('POST');
    expect(call.body).toEqual({ override_checker: true });
  });

  it('shows the personal Zalo outbox and lets staff settle an unknown send', async () => {
    zaloMode = 'personal';
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cài đặt' }));
    expect(await screen.findByText('Hộp thư gửi đi (Zalo cá nhân)')).toBeTruthy();
    const card = (await screen.findByText('Nhắn "đồng ý" để trò chuyện với trợ lý AI.')).closest('li') as HTMLElement;
    expect(within(card).getByRole('button', { name: 'Gửi lại' })).toBeTruthy();
    expect(within(card).getByRole('button', { name: 'Ghi là lỗi' })).toBeTruthy();
    fireEvent.click(within(card).getByRole('button', { name: 'Khách đã nhận' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/outbox/obx_9/decide')).toBe(true));
    const call = calls.find((c) => c.url === '/staff/outbox/obx_9/decide')!;
    expect(call.method).toBe('POST');
    expect(call.body).toEqual({ action: 'mark_sent' });
  });

  it('marks a contact as not a customer (staff_only) from the conversation detail', async () => {
    render(<App />);
    fireEvent.click(await screen.findByText('Chị Lan'));
    fireEvent.click(await screen.findByRole('button', { name: 'Không phải khách (chỉ nhân viên trả lời)' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/conversations/cnv_1/staff-only')).toBe(true));
    const call = calls.find((c) => c.url === '/staff/conversations/cnv_1/staff-only')!;
    expect(call.method).toBe('POST');
    expect(call.body).toEqual({});
  });

  it('opens Settings when no staff token is stored', async () => {
    localStorage.clear();
    render(<App />);
    expect(await screen.findByText('Kết nối máy chủ')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Hội thoại' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('keeps the section 14 blocks quiet against a server that does not send them', async () => {
    render(<App />);
    const item = (await screen.findByText('Chị Lan', { selector: 'strong' })).closest('button') as HTMLElement;
    expect(within(item).queryByText('tự động trả lời')).toBeNull();
    expect(within(item).queryByText(/^vai trò:/)).toBeNull();

    fireEvent.click(item);
    const box = await screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
    const sw = within(box).getByRole('switch', { name: 'Tự động trả lời' }) as HTMLInputElement;
    expect(sw.checked).toBe(false);
    expect(sw.disabled).toBe(false);
    // an OA contact without a role has no role row, and nothing else of section 14 shows
    expect(within(box).queryByRole('combobox', { name: 'Vai trò' })).toBeNull();
    expect(within(box).queryByText(/^Vai trò:/)).toBeNull();
    expect(screen.queryByRole('region', { name: 'Tóm tắt khách hàng' })).toBeNull();
    expect(screen.queryByText(/^Phòng hai bot/)).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(calls.some((c) => /^\/staff\/(roles|benefits|visits|customers)/.test(c.url))).toBe(false);
  });

  it('switches auto reply on only after the confirmation, then marks the conversation in the list', async () => {
    render(<App />);
    fireEvent.click(await screen.findByText('Chị Lan'));
    const box = await screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
    fireEvent.click(within(box).getByRole('switch', { name: 'Tự động trả lời' }));
    expect(calls.some((c) => c.url === '/staff/conversations/cnv_1/auto-reply')).toBe(false);
    const confirm = within(box).getByRole('group', { name: 'Xác nhận bật tự động trả lời' });
    fireEvent.click(within(confirm).getByRole('button', { name: 'Bật tự động trả lời' }));

    await waitFor(() => expect(calls.some((c) => c.url === '/staff/conversations/cnv_1/auto-reply')).toBe(true));
    const call = calls.find((c) => c.url === '/staff/conversations/cnv_1/auto-reply')!;
    expect(call.method).toBe('PUT');
    expect(call.body).toEqual({ auto_reply: 'on' });
    await waitFor(() => expect((within(box).getByRole('switch', { name: 'Tự động trả lời' }) as HTMLInputElement).checked).toBe(true));
    expect(within(box).getByText('Đã bật tự động trả lời cho hội thoại này.')).toBeTruthy();
  });

  it('shows the auto reply badge in the list for a conversation whose switch is on', async () => {
    convExtra = { auto_reply: 'on', effective_mode: 'auto_allowed' };
    render(<App />);
    const item = (await screen.findByText('Chị Lan', { selector: 'strong' })).closest('button') as HTMLElement;
    expect(within(item).getByText('tự động trả lời')).toBeTruthy();
    // the older badges are still there
    expect(within(item).getByText('chờ duyệt (1)')).toBeTruthy();
  });
});

describe('helpers', () => {
  it('reads datetime-local input as Vietnam time', () => {
    expect(vnLocalToMs('2026-11-07T19:30')).toBe(Date.UTC(2026, 10, 7, 12, 30));
    expect(Number.isNaN(vnLocalToMs('bad'))).toBe(true);
  });

  it('builds the claude_pool login command per account', () => {
    const base = {
      priority: 1,
      enabled: true,
      pinned: false,
      pool_status: 'ok' as const,
      until: null,
      usable_now: true,
      login: null,
      last_error: '',
      last_ok: null,
    };
    expect(loginCommand({ ...base, label: 'ultra-anlnt' })).toBe('CLAUDE_CONFIG_DIR="$HOME/.thomhouse-bot/accounts/"ultra-anlnt claude auth login');
    expect(loginCommand({ ...base, label: "x'y; rm" })).toBe(`CLAUDE_CONFIG_DIR="$HOME/.thomhouse-bot/accounts/"'x'\\''y; rm' claude auth login`);
  });

  it('sorts handoffs urgent first, then oldest first', () => {
    const h = (id: string, urgency: 'urgent' | 'normal', created_at: number) => ({ id, urgency, created_at }) as HandoffView;
    expect(sortHandoffs([h('a', 'normal', 1), h('b', 'urgent', 5), h('c', 'urgent', 2)]).map((x) => x.id)).toEqual(['c', 'b', 'a']);
  });

  it('shows the exact text of a personal Zalo outbox row, and the OA payload text otherwise', () => {
    const base = {
      id: 'obx_1',
      kind: 'cs_buttons' as const,
      conversation_id: 'cnv_1',
      message_id: 'msg_1',
      zalo_msg_id: null,
      error: null,
      created_at: 1762500000000,
      sent_at: null,
    };
    const personal: OutboxItem = {
      ...base,
      zalo_mode: 'personal',
      zalo_user_id: 'p:9100123',
      payload: { recipient: { user_id: 'p:9100123' } },
      status: 'unknown',
      channel: 'personal',
      thread_id: '9100123',
      text: 'Nhắn "đồng ý" để trò chuyện với trợ lý AI.',
    };
    expect(outboxText(personal)).toBe('Nhắn "đồng ý" để trò chuyện với trợ lý AI.');
    const oa: OutboxItem = { ...base, zalo_mode: 'mock', zalo_user_id: '2468458835291979', payload: { message: { text: 'Dạ em chào ạ' } }, status: 'sent' };
    expect(outboxText(oa)).toBe('Dạ em chào ạ');
  });

  it('marks staff takeover conversations', () => {
    const b = conversationBadges({ ...summary, bot_state: 'staff_takeover', needs_attention: false, pending_drafts: 0 });
    expect(b.map((x) => x.text)).toEqual(['nhân viên đang xử lý']);
  });

  it('adds the auto reply and role badges after the older ones', () => {
    const quiet = { ...summary, needs_attention: false, pending_drafts: 0 };
    expect(conversationBadges(quiet).map((x) => x.text)).toEqual(['bot đang trả lời']);
    expect(conversationBadges({ ...quiet, effective_mode: 'auto_allowed', role: 'customer' }).map((x) => x.text)).toEqual([
      'bot đang trả lời',
      'tự động trả lời',
      'vai trò: khách',
    ]);
    // a manager or staff member never gets a bot reply, whatever the mode says
    expect(conversationBadges({ ...quiet, effective_mode: 'auto_allowed', role: 'manager' }).map((x) => x.text)).toEqual(['bot đang trả lời', 'vai trò: quản lý']);
    expect(conversationBadges({ ...quiet, role: 'staff', role_source: 'staff' }).map((x) => x.text)).toEqual(['bot đang trả lời', 'vai trò: nhân viên']);
  });
});
