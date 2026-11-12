// Menu images in the console (task C): a draft's images with thumbnails, removing an image before approving, the
// "Gửi menu" action with the claim-slide confirm, menu image messages, and the profile_personal_skip_bot flag.
// Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationDetail, ConversationSummary, DraftView, MenuImagesIndex } from './api';
import { App } from './App';
import { remainingIssues } from './screens/Conversations';
import { claimConfirmText } from './screens/MenuImages';

const T = Date.UTC(2026, 10, 8, 3, 0);

const summary: ConversationSummary = {
  id: 'cnv_m',
  customer: { id: 'cus_m', zalo_user_id: 'p:9100777', display_name: 'Hoa Trần', phone: null, minor_flag: null, last_user_interaction_at: T },
  bot_state: 'bot_active',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: true,
  takeover_by: null,
  takeover_until: null,
  last_message_at: T,
  last_message_preview: 'cho chị xem menu tóc',
  pending_drafts: 1,
  open_handoffs: 0,
};

const slide = (key: string, title: string, claim = false) => {
  const [group, n] = key.split('/');
  const labels: Record<string, string> = { 'thu-gian-toc': 'Thư giãn và chăm sóc tóc', healing: 'Giúp bạn khỏe', facial: 'Chăm sóc da cơ bản', 'hair-removal': 'Triệt lông' };
  return {
    key,
    group: group!,
    group_label: labels[group!]!,
    n: Number(n),
    title,
    kind: 'service',
    has_medical_claim: claim,
    claim_note: claim ? 'in tên bệnh' : null,
    service_ids: [],
    thumb: true,
  };
};

const index: MenuImagesIndex = {
  max_images: 10,
  overview: ['facial/1', 'healing/1', 'thu-gian-toc/1', 'hair-removal/1'],
  groups: [
    { group: 'facial', label: 'Chăm sóc da cơ bản', catalog_group: 'skin', cover: ['facial/1'], price_list: ['facial/2'], review_note: null },
    { group: 'healing', label: 'Giúp bạn khỏe', catalog_group: 'health', cover: ['healing/1'], price_list: ['healing/2', 'healing/5', 'healing/8'], review_note: null },
    { group: 'thu-gian-toc', label: 'Thư giãn và chăm sóc tóc', catalog_group: 'hair', cover: ['thu-gian-toc/1'], price_list: ['thu-gian-toc/2', 'thu-gian-toc/5'], review_note: null },
    { group: 'hair-removal', label: 'Triệt lông', catalog_group: null, cover: ['hair-removal/1'], price_list: ['hair-removal/2'], review_note: null },
  ],
  slides: [
    slide('facial/1', 'Menu chăm sóc da'),
    slide('facial/2', 'Detox da'),
    slide('healing/1', 'Menu khỏe'),
    slide('healing/2', 'Thải hàn giải cảm', true),
    slide('healing/5', 'Detox cơ thể'),
    slide('healing/8', 'Đau thắt lưng mỏi gối'),
    slide('thu-gian-toc/1', 'Menu chăm sóc tóc'),
    slide('thu-gian-toc/2', 'Detox da đầu'),
    slide('thu-gian-toc/5', 'Gội đầu thư giãn'),
    slide('hair-removal/1', 'Triệt lông'),
    slide('hair-removal/2', 'Bảng giá triệt lông'),
  ],
};

const draft: DraftView = {
  id: 'drf_m',
  job_id: 'job_m',
  conversation_id: 'cnv_m',
  text: 'Dạ em gửi chị Hoa menu chăm sóc tóc ạ.',
  final_text: null,
  status: 'pending',
  checker: { passed: true, issues: [], checked_at: T },
  account_label: 'acct-a',
  cost_usd_equiv: 0.01,
  catalog_version: 'cv_seed_20261108',
  created_at: T,
  decided_by: null,
  decided_at: null,
  attachments: ['thu-gian-toc/2', 'thu-gian-toc/5'],
};

let detailDraft: DraftView = draft;
let conv: ConversationSummary = summary;
type Call = { method: string; url: string; body: unknown };
let calls: Call[] = [];
// Flags a newer server adds to GET /staff/flags (section 14.7); empty = a server before 2026-11-12.
let flagsExtra: Record<string, unknown> = {};

function detail(): ConversationDetail {
  return {
    conversation: { ...conv, session_id: null, session_turns: 0, catalog_version: 'cv_seed_20261108' },
    messages: [
      {
        id: 'msg_img',
        direction: 'outbound',
        source: 'staff',
        kind: 'image',
        text: '[Ảnh menu, 1 ảnh] Triệt lông (ảnh 1)',
        attachments: [{ type: 'menu_image', name: 'Triệt lông, ảnh 1: Triệt lông' }],
        send_state: 'pending',
        draft_id: null,
        staff_id: 'lan',
        created_at: T,
        sent_at: null,
      },
    ],
    drafts: [detailDraft],
    handoffs: [],
    booking_requests: [],
    consents: [],
    profile: null,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);

let confirmAnswers: boolean[] = [];

beforeEach(() => {
  calls = [];
  detailDraft = draft;
  conv = summary;
  confirmAnswers = [];
  flagsExtra = {};
  localStorage.setItem('thomhouse.console.config', JSON.stringify({ baseUrl: '', staffToken: 'test-token', staffId: 'lan' }));
  vi.stubGlobal('confirm', vi.fn(() => confirmAnswers.shift() ?? false));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const headers = new Headers(init?.headers);
      if (url !== '/health' && headers.get('authorization') !== 'Bearer test-token') return json({ error: { code: 'unauthorized', message: 'no' } }, 401);
      if (url === '/health') return json({ ok: true, env: 'dev', zalo_mode: 'personal' });
      if (url.startsWith('/staff/handoffs')) return json({ items: [], next_cursor: null });
      if (url.startsWith('/staff/conversations?')) return json({ items: [conv], next_cursor: null });
      if (url === `/staff/conversations/${conv.id}`) return json(detail());
      if (url === '/staff/menu-images') return json(index);
      if (/^\/staff\/menu-images\/[a-z-]+\/\d+$/.test(url)) return new Response(JPEG, { status: 200, headers: { 'content-type': 'image/jpeg' } });
      if (url === '/staff/drafts/drf_m/approve') return json({ draft: { ...draft, status: 'sent' }, message: detail().messages[0] });
      if (url === `/staff/conversations/${conv.id}/menu-images` && method === 'POST') {
        const b = JSON.parse(String(init!.body)) as { keys: string[] };
        return json({ message: detail().messages[0], outbox_id: 'obx_img', keys: b.keys });
      }
      if (url === '/staff/flags' && method === 'GET') {
        return json({
          flags: { auto_reply_mode: 'approve_each', ai_calls_enabled: true, ai_engine: 'subscription', scheduled_sends_enabled: false, outbound_enabled: true, promotions_enabled: false, runner_desired_account: 'auto', profile_personal_skip_bot: true, ...flagsExtra },
          updated: {},
        });
      }
      if (url === '/staff/flags' && method === 'PUT') return json({ flags: {}, updated: {} });
      if (url === '/staff/runner') return json({ runners: [], desired_account: 'auto', queue: { queued: 0, leased: 0 } });
      if (url.startsWith('/staff/outbox?')) return json({ items: [], next_cursor: null });
      if (url === '/bridge/status') {
        return json({ zalo_mode: 'personal', outbound_enabled: true, last_claim_at: null, last_result_at: null, bridges: [], counts: { queued: 0, leased: 0, sent: 0, failed: 0, unknown: 0 }, oldest_queued_at: null });
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

async function openDraft(): Promise<HTMLElement> {
  render(<App />);
  fireEvent.click(await screen.findByText('Hoa Trần'));
  return (await screen.findByText('Dạ em gửi chị Hoa menu chăm sóc tóc ạ.')).closest('.draft') as HTMLElement;
}

describe('draft images', () => {
  it('shows the thumbnails of the attached images and approves only the ones staff kept', async () => {
    const card = await openDraft();
    const w = within(card);
    expect(w.getByText('Ảnh menu gửi sau câu trả lời: 2/2 ảnh.')).toBeTruthy();
    const img = (await w.findByAltText('Thư giãn và chăm sóc tóc, ảnh 2: Detox da đầu')) as HTMLImageElement;
    expect(img.src.startsWith('data:image/jpeg;base64,')).toBe(true);
    // the thumbnail request carries the staff token and names the key only
    const thumbCall = calls.find((c) => c.url === '/staff/menu-images/thu-gian-toc/2');
    expect(thumbCall?.method).toBe('GET');

    fireEvent.click(w.getByRole('button', { name: 'Bỏ Thư giãn và chăm sóc tóc, ảnh 2: Detox da đầu' }));
    expect(w.getByText('Ảnh menu gửi sau câu trả lời: 1/2 ảnh.')).toBeTruthy();
    fireEvent.click(w.getByRole('button', { name: 'Duyệt và gửi' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/drafts/drf_m/approve')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/drafts/drf_m/approve')!.body).toEqual({ attachments: ['thu-gian-toc/5'] });
  });

  it('sends the text only when every image is removed, and restores an image in its order', async () => {
    const card = await openDraft();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Bỏ Thư giãn và chăm sóc tóc, ảnh 2: Detox da đầu' }));
    fireEvent.click(w.getByRole('button', { name: 'Bỏ Thư giãn và chăm sóc tóc, ảnh 5: Gội đầu thư giãn' }));
    expect(w.getByText(/Đã bỏ hết ảnh/)).toBeTruthy();
    fireEvent.click(w.getByRole('button', { name: 'Giữ lại Thư giãn và chăm sóc tóc, ảnh 5: Gội đầu thư giãn' }));
    fireEvent.click(w.getByRole('button', { name: 'Giữ lại Thư giãn và chăm sóc tóc, ảnh 2: Detox da đầu' }));
    fireEvent.click(w.getByRole('button', { name: 'Bỏ Thư giãn và chăm sóc tóc, ảnh 5: Gội đầu thư giãn' }));
    fireEvent.click(w.getByRole('button', { name: 'Bỏ Thư giãn và chăm sóc tóc, ảnh 2: Detox da đầu' }));
    fireEvent.click(w.getByRole('button', { name: 'Duyệt và gửi' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/drafts/drf_m/approve')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/drafts/drf_m/approve')!.body).toEqual({ attachments: [] });
  });

  it('lets staff approve without the override once the only blocked image is removed', async () => {
    detailDraft = {
      ...draft,
      status: 'blocked',
      attachments: ['healing/5', 'healing/2'],
      checker: { passed: false, issues: [{ rule: 'menu_image', detail: 'menu image prints a health claim; staff only', excerpt: 'healing/2' }], checked_at: T },
    };
    const card = await openDraft();
    const w = within(card);
    expect(w.getByText(/Ảnh menu không gửi được tự động/)).toBeTruthy();
    const approve = w.getByRole('button', { name: 'Duyệt và gửi' }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    fireEvent.click(w.getByRole('button', { name: 'Bỏ Giúp bạn khỏe, ảnh 2: Thải hàn giải cảm' }));
    expect(approve.disabled).toBe(false);
    expect(w.getByText(/Lỗi của bước kiểm tra chỉ nằm ở ảnh đã bỏ/)).toBeTruthy();
    fireEvent.click(approve);
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/drafts/drf_m/approve')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/drafts/drf_m/approve')!.body).toEqual({ attachments: ['healing/5'] });
  });

  it('labels a menu image message as a menu image, not as an unread customer attachment', async () => {
    await openDraft();
    expect(screen.getByText('Ảnh menu: Triệt lông, ảnh 1: Triệt lông')).toBeTruthy();
    expect(screen.queryByText(/bot không đọc nội dung đính kèm/)).toBeNull();
  });
});

describe('Gửi menu', () => {
  async function openPanel(): Promise<HTMLElement> {
    render(<App />);
    fireEvent.click(await screen.findByText('Hoa Trần'));
    const panel = await screen.findByRole('region', { name: 'Gửi menu' });
    fireEvent.click(within(panel).getByRole('button', { name: 'Gửi menu' }));
    await waitFor(() => expect((within(panel).getByLabelText('Chọn menu') as HTMLSelectElement).disabled).toBe(false));
    return panel;
  }

  it('sends the overview covers', async () => {
    const panel = await openPanel();
    const w = within(panel);
    fireEvent.change(w.getByLabelText('Chọn menu'), { target: { value: 'overview' } });
    fireEvent.click(w.getByRole('button', { name: 'Gửi 4 ảnh menu' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/conversations/cnv_m/menu-images')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/conversations/cnv_m/menu-images')!.body).toEqual({
      group: 'overview',
      keys: ['facial/1', 'healing/1', 'thu-gian-toc/1', 'hair-removal/1'],
    });
    expect(await w.findByText('Đã xếp 4 ảnh menu vào hàng chờ gửi. Bot vẫn tiếp tục trả lời hội thoại này.')).toBeTruthy();
  });

  it('leaves claim slides out until staff confirm them', async () => {
    const panel = await openPanel();
    const w = within(panel);
    fireEvent.change(w.getByLabelText('Chọn menu'), { target: { value: 'healing' } });
    const claimBox = w.getByLabelText('Chọn Giúp bạn khỏe, ảnh 2: Thải hàn giải cảm') as HTMLInputElement;
    expect(claimBox.checked).toBe(false);
    expect((w.getByLabelText('Chọn Giúp bạn khỏe, ảnh 5: Detox cơ thể') as HTMLInputElement).checked).toBe(true);
    // first answer "no": the slide stays out
    confirmAnswers = [false];
    fireEvent.click(claimBox);
    expect(window.confirm).toHaveBeenCalledWith(claimConfirmText(index.slides.find((s) => s.key === 'healing/2')!));
    expect(claimBox.checked).toBe(false);
    // then "yes"
    confirmAnswers = [true];
    fireEvent.click(claimBox);
    expect(claimBox.checked).toBe(true);
    fireEvent.click(w.getByRole('button', { name: 'Gửi 3 ảnh menu (có 1 ảnh in câu về sức khỏe)' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/conversations/cnv_m/menu-images')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/conversations/cnv_m/menu-images')!.body).toEqual({
      group: 'healing',
      keys: ['healing/2', 'healing/5', 'healing/8'],
      include_claim_slides: true,
    });
  });

  it('is not offered on an OA conversation', async () => {
    conv = { ...summary, customer: { ...summary.customer, zalo_user_id: '2468458835291979' } };
    render(<App />);
    fireEvent.click(await screen.findByText('Hoa Trần'));
    await screen.findByText('Dạ em gửi chị Hoa menu chăm sóc tóc ạ.');
    expect(screen.queryByRole('region', { name: 'Gửi menu' })).toBeNull();
  });
});

describe('settings', () => {
  it('lists profile_personal_skip_bot with what each value does', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cài đặt' }));
    const legend = await screen.findByText('Bot im lặng với gia đình, nhân viên và bạn bè (profile_personal_skip_bot)');
    const box = legend.closest('fieldset') as HTMLElement;
    expect(within(box).getByText('true: bot không nhắn người quen (mặc định)')).toBeTruthy();
    fireEvent.click(within(box).getByRole('radio', { name: /false: xử lý như mọi người nhắn tới/ }));
    fireEvent.click(within(box).getByRole('button', { name: 'Áp dụng profile_personal_skip_bot = false' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/flags' && c.method === 'PUT')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/flags' && c.method === 'PUT')!.body).toEqual({ profile_personal_skip_bot: false });
  });

  it('lists rooms_enabled with what each value does and applies it', async () => {
    flagsExtra = { rooms_enabled: false };
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cài đặt' }));
    const legend = await screen.findByText('Phòng hai bot (rooms_enabled)');
    const box = legend.closest('fieldset') as HTMLElement;
    const off = within(box).getByRole('radio', { name: /false: máy chủ không đưa tin vào phòng hai bot \(mặc định\)/ }) as HTMLInputElement;
    const on = within(box).getByRole('radio', { name: /true: máy chủ đưa tin vào phòng hai bot/ }) as HTMLInputElement;
    expect(off.checked).toBe(true);
    // the description says who gets a room, what else must be set, and that replies stay drafts
    expect(box.textContent).toContain('quản lý và nhân viên của studio không có phòng');
    expect(box.textContent).toContain('THOMHOUSE_DRAFT_ENGINE=rooms');
    expect(box.textContent).toContain('Câu trả lời vẫn là bản nháp chờ nhân viên duyệt');
    fireEvent.click(on);
    fireEvent.click(within(box).getByRole('button', { name: 'Áp dụng rooms_enabled = true' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/staff/flags' && c.method === 'PUT')).toBe(true));
    expect(calls.find((c) => c.url === '/staff/flags' && c.method === 'PUT')!.body).toEqual({ rooms_enabled: true });
  });

  it('hides rooms_enabled when the server does not send the flag', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cài đặt' }));
    await screen.findByText('Bot im lặng với gia đình, nhân viên và bạn bè (profile_personal_skip_bot)');
    expect(screen.queryByText('Phòng hai bot (rooms_enabled)')).toBeNull();
  });
});

describe('helpers', () => {
  it('keeps checker issues unless they name an image staff removed', () => {
    const d: DraftView = {
      ...draft,
      attachments: ['healing/2', 'healing/5'],
      checker: {
        passed: false,
        issues: [
          { rule: 'menu_image', detail: 'claim', excerpt: 'healing/2' },
          { rule: 'price', detail: 'k price', excerpt: '199k' },
        ],
        checked_at: T,
      },
    };
    expect(remainingIssues(d, ['healing/5']).map((i) => i.rule)).toEqual(['price']);
    expect(remainingIssues(d, ['healing/2', 'healing/5']).map((i) => i.rule)).toEqual(['menu_image', 'price']);
  });
});
