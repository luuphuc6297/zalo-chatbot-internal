// Contact profile card in the conversation view (docs/contracts.md section 13). Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationDetail, ConversationSummary, CustomerProfileView } from './api';
import { App } from './App';
import { addressText, fmtDate, profileReason } from './labels';
import { profileConfirmPatch, profileFormOf, profilePatchFromForm } from './screens/ProfileCard';

const T_FIRST = Date.UTC(2026, 8, 1, 3, 0); // 01/09/2026 Vietnam time
const T_USED = Date.UTC(2026, 9, 20, 3, 0); // 20/10/2026
const T_LAST = Date.UTC(2026, 10, 1, 3, 0); // 01/11/2026

const summary: ConversationSummary = {
  id: 'cnv_9',
  customer: {
    id: 'cus_9',
    zalo_user_id: 'p:9100123',
    display_name: 'Lan Nguyễn',
    phone: null,
    minor_flag: null,
    last_user_interaction_at: T_LAST,
  },
  bot_state: 'awaiting_consent',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: false,
  takeover_by: null,
  takeover_until: null,
  last_message_at: T_LAST,
  last_message_preview: 'chào shop',
  pending_drafts: 0,
  open_handoffs: 0,
};

function makeProfile(over: Partial<CustomerProfileView> = {}): CustomerProfileView {
  return {
    zalo_user_id: 'p:9100123',
    thread_id: '9100123',
    customer_id: 'cus_9',
    conversation_id: 'cnv_9',
    display_name: 'Lan Nguyễn',
    relationship: 'customer',
    relationship_confidence: 'medium',
    relationship_reasons: ['service_vocab:3', 'price_vocab:1'],
    address_term: 'chị',
    name_to_use: 'Lan',
    address_confidence: 'medium',
    addressing: { owner_calls_contact: { chị: 4 }, contact_calls_self: { chị: 2 }, contact_calls_owner: { em: 3 } },
    services: [
      {
        key: 'goi-dau-thu-gian',
        service_id: 'goi-dau-thu-gian',
        name: 'Gội đầu thư giãn',
        group: 'hair',
        sensitive: false,
        status: 'likely_used',
        mention_count: 3,
        last_mentioned_at: T_LAST,
        used_signal_count: 1,
        last_used_signal_at: T_USED,
      },
      {
        key: 'cat:massage',
        service_id: null,
        name: 'massage',
        group: 'relaxation',
        sensitive: false,
        status: 'mentioned',
        mention_count: 2,
        last_mentioned_at: T_USED,
        used_signal_count: 0,
        last_used_signal_at: null,
      },
    ],
    evidence: [{ at: T_USED, from: 'contact', kind: 'booking', text: 'Chị muốn đặt lịch gội đầu <b>thứ 7</b> nha' }],
    stats: { messages_in: 10, messages_out: 8, text_in: 9, text_out: 8, first_at: T_FIRST, last_at: T_LAST, first_writer: 'contact', active_days: 4 },
    analyzer: {
      relationship: 'customer',
      relationship_confidence: 'medium',
      address_term: 'chị',
      name_to_use: 'Lan',
      address_confidence: 'medium',
      services: [],
    },
    analyzer_version: 'contacts-rules-v1',
    source: 'analyzer',
    staff_override: false,
    staff_note: null,
    analyzed_at: T_LAST,
    created_at: T_LAST,
    updated_at: T_LAST,
    updated_by: 'analyzer',
    model_facts: {
      relationship: 'customer',
      address_term: 'chị',
      name_to_use: 'Lan',
      services_likely_used: ['Gội đầu thư giãn'],
      services_mentioned: ['massage'],
    },
    ...over,
  };
}

function makeDetail(profile: CustomerProfileView | null | undefined, conv: ConversationSummary = summary): ConversationDetail {
  const d: ConversationDetail = {
    conversation: { ...conv, session_id: null, session_turns: 0, catalog_version: 'cv_seed_20261107' },
    messages: [],
    drafts: [],
    handoffs: [],
    booking_requests: [],
    consents: [],
  };
  if (profile !== undefined) d.profile = profile;
  return d;
}

type Call = { method: string; url: string; body: unknown };
let calls: Call[] = [];
let conv: ConversationSummary = summary;
let profile: CustomerProfileView | null | undefined = makeProfile();
let patchStatus = 200;
let patchError: { code: string; message: string } | null = null;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

beforeEach(() => {
  calls = [];
  conv = summary;
  profile = makeProfile();
  patchStatus = 200;
  patchError = null;
  localStorage.setItem('thomhouse.console.config', JSON.stringify({ baseUrl: '', staffToken: 'test-token', staffId: 'lan' }));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === '/health') return json({ ok: true, env: 'dev', zalo_mode: 'personal' });
      if (url.startsWith('/staff/handoffs')) return json({ items: [], next_cursor: null });
      if (url.startsWith('/staff/conversations?')) return json({ items: [conv], next_cursor: null });
      if (url === `/staff/conversations/${conv.id}`) return json(makeDetail(profile, conv));
      if (url === '/staff/roles/p%3A9100123' && method === 'PUT') {
        // section 14.3: a staff role wins over the profile; null clears it and the role falls back to the profile
        const role = (JSON.parse(String(init?.body)) as { role: 'customer' | 'manager' | 'staff' | null }).role;
        conv = role ? { ...conv, role, role_source: 'staff' } : { ...conv, role: null, role_source: null };
        return json({ role: role ? { zalo_user_id: 'p:9100123', role, source: 'staff', updated_at: T_LAST, updated_by: 'lan' } : null });
      }
      if (url === '/staff/profiles/p%3A9100123' && method === 'PATCH') {
        if (patchError) return json({ error: patchError }, patchStatus);
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        const base = profile ?? makeProfile({ source: 'staff', analyzer: null, analyzed_at: null, evidence: [], services: [], stats: {}, relationship_reasons: [] });
        profile =
          body.staff_override === false
            ? { ...base, ...(base.analyzer ?? {}), staff_override: false, updated_by: 'lan' }
            : { ...base, ...body, staff_override: true, relationship_confidence: 'high', updated_by: 'lan' };
        return json({ profile });
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

async function openCard(name = 'Lan Nguyễn'): Promise<HTMLElement> {
  render(<App />);
  fireEvent.click(await screen.findByText(name));
  return screen.findByRole('region', { name: 'Hồ sơ liên hệ' });
}

describe('profile card', () => {
  it('shows relationship, addressing, services, stats, evidence and source of a personal contact', async () => {
    const card = await openCard();
    const w = within(card);
    expect(w.getByText('khách (chắc chắn vừa)')).toBeTruthy();
    expect(w.getByText('nhắc tới dịch vụ (3 lần); hỏi giá (1 lần)')).toBeTruthy();
    expect(w.getByText('chị Lan (chắc chắn vừa)')).toBeTruthy();
    expect(w.getByText('gọi là chị; tên Lan; dịch vụ có thể đã dùng: Gội đầu thư giãn; dịch vụ từng hỏi: massage.')).toBeTruthy();

    expect(w.getByText('Dịch vụ có dấu hiệu đã dùng (chưa chắc chắn)')).toBeTruthy();
    expect(
      w.getByText(`Gội đầu thư giãn · dấu hiệu đã dùng 1 lần, gần nhất ${fmtDate(T_USED)} · nhắc 3 lần, gần nhất ${fmtDate(T_LAST)}`),
    ).toBeTruthy();
    expect(w.getByText('Dịch vụ từng hỏi hoặc nhắc tới')).toBeTruthy();
    expect(w.getByText(`massage · nhắc 2 lần, gần nhất ${fmtDate(T_USED)}`)).toBeTruthy();

    expect(
      w.getByText(
        `người này gửi 10 tin, chủ tài khoản gửi 8 tin · từ ${fmtDate(T_FIRST)} đến ${fmtDate(T_LAST)} · 4 ngày có nhắn · người này nhắn trước`,
      ),
    ).toBeTruthy();

    // evidence is plain text, never parsed as HTML
    const snippet = w.getByText('Chị muốn đặt lịch gội đầu <b>thứ 7</b> nha');
    expect(snippet.querySelector('b')).toBeNull();
    expect(w.getByText(`${fmtDate(T_USED)} · người này nhắn · về đặt lịch`)).toBeTruthy();

    expect(w.getByText(/Script phân tích tạo hồ sơ; script chạy gần nhất lúc .* \(contacts-rules-v1\)/)).toBeTruthy();
    expect(w.getByText(/^Chưa\. Lần chạy script sau/)).toBeTruthy();
    expect(w.queryByRole('button', { name: 'Bỏ phần nhân viên sửa, dùng kết quả script' })).toBeNull();
  });

  it('saves relationship, address term and name with PATCH and reloads the conversation', async () => {
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    fireEvent.change(w.getByLabelText('Người này là'), { target: { value: 'family' } });
    expect(w.getByText(/tin kế tiếp của họ chuyển hội thoại sang chỉ nhân viên trả lời/)).toBeTruthy();
    fireEvent.change(w.getByLabelText('Bot gọi người này là'), { target: { value: 'cô' } });
    fireEvent.change(w.getByLabelText('Tên để gọi'), { target: { value: ' Hoa ' } });
    const loadsBefore = calls.filter((c) => c.url === '/staff/conversations/cnv_9').length;
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));

    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    const call = calls.find((c) => c.method === 'PATCH')!;
    expect(call.url).toBe('/staff/profiles/p%3A9100123');
    expect(call.body).toEqual({ relationship: 'family', address_term: 'cô', name_to_use: 'Hoa' });

    expect(await w.findByText(/^Đã lưu hồ sơ\./)).toBeTruthy();
    await waitFor(() => expect(calls.filter((c) => c.url === '/staff/conversations/cnv_9').length).toBeGreaterThan(loadsBefore));
    expect(await w.findByText('gia đình (chắc chắn cao)')).toBeTruthy();
    expect(w.getByText('nhân viên đã sửa')).toBeTruthy();
  });

  it('refuses a name that is not one word of letters', async () => {
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    fireEvent.change(w.getByLabelText('Tên để gọi'), { target: { value: 'Lan Anh' } });
    expect(w.getByText('Tên phải là một từ, chỉ gồm chữ cái, tối đa 20 ký tự.')).toBeTruthy();
    expect((w.getByRole('button', { name: 'Lưu hồ sơ' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(w.getByLabelText('Tên để gọi'), { target: { value: '' } });
    expect((w.getByRole('button', { name: 'Lưu hồ sơ' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(w.getByRole('button', { name: 'Hủy sửa' }));
    expect(w.queryByLabelText('Tên để gọi')).toBeNull();
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
  });

  it('clears the staff override and shows what the analyzer guessed', async () => {
    profile = makeProfile({
      relationship: 'personal',
      relationship_confidence: 'high',
      address_term: 'cô',
      name_to_use: 'Hoa',
      address_confidence: 'high',
      staff_override: true,
      staff_note: 'khách quen <i>lâu năm</i>',
      updated_by: 'lan',
      model_facts: null,
    });
    const card = await openCard();
    const w = within(card);
    expect(w.getByText('người quen (nhãn cũ) (chắc chắn cao)')).toBeTruthy();
    expect(w.getByText('Bot không nhận thông tin nào: hồ sơ gia đình, nhân viên và bạn bè không được gửi cho bot.')).toBeTruthy();
    expect(w.getByText(/^Có\. Script phân tích không ghi đè/)).toBeTruthy();
    expect(w.getByText('khách (chắc chắn vừa), gọi là chị Lan')).toBeTruthy();
    expect(w.getByText('khách quen <i>lâu năm</i>').querySelector('i')).toBeNull();

    fireEvent.click(w.getByRole('button', { name: 'Bỏ phần nhân viên sửa, dùng kết quả script' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    const call = calls.find((c) => c.method === 'PATCH')!;
    expect(call.url).toBe('/staff/profiles/p%3A9100123');
    expect(call.body).toEqual({ staff_override: false });
    expect(await w.findByText(/^Đã bỏ phần nhân viên sửa/)).toBeTruthy();
    expect(await w.findByText('khách (chắc chắn vừa)')).toBeTruthy();
  });

  it('explains a missing migration instead of a generic state error', async () => {
    patchStatus = 409;
    patchError = { code: 'invalid_state', message: 'customer_profiles table missing: apply migration 0007_customer_profiles.sql' };
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    fireEvent.change(w.getByLabelText('Tên để gọi'), { target: { value: 'Hoa' } });
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));
    expect((await w.findByRole('alert')).textContent).toMatch(/chưa áp migration 0007_customer_profiles\.sql/);
    expect(w.getByLabelText('Người này là')).toBeTruthy();
  });

  it('lets staff create a profile for a personal contact that has none', async () => {
    profile = null;
    const card = await openCard();
    const w = within(card);
    expect(w.getByText(/^Chưa có hồ sơ liên hệ cho người này/)).toBeTruthy();
    fireEvent.click(w.getByRole('button', { name: 'Tạo hồ sơ' }));
    expect((w.getByLabelText('Người này là') as HTMLSelectElement).value).toBe('unknown');
    expect((w.getByLabelText('Bot gọi người này là') as HTMLSelectElement).value).toBe('');
    fireEvent.change(w.getByLabelText('Người này là'), { target: { value: 'customer' } });
    fireEvent.change(w.getByLabelText('Bot gọi người này là'), { target: { value: 'anh' } });
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ relationship: 'customer', address_term: 'anh' });
  });

  it('leaves a low-confidence address guess out of the form and saves only the field that changed', async () => {
    profile = makeProfile({ address_term: 'anh', address_confidence: 'low', model_facts: null });
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    expect((w.getByLabelText('Bot gọi người này là') as HTMLSelectElement).value).toBe('');
    expect(w.getByText(/Script đoán cách gọi anh ở mức chắc chắn thấp/)).toBeTruthy();
    // nothing changed yet: nothing to save
    expect((w.getByRole('button', { name: 'Lưu hồ sơ' }) as HTMLButtonElement).disabled).toBe(true);
    expect(w.getByText('Chưa có ô nào thay đổi.')).toBeTruthy();
    fireEvent.change(w.getByLabelText('Tên để gọi'), { target: { value: 'Mai' } });
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ name_to_use: 'Mai' });
  });

  it('confirms what the card shows with a separate button', async () => {
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Xác nhận quan hệ và cách gọi đang hiện' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ relationship: 'customer', address_term: 'chị', name_to_use: 'Lan' });
    expect(await w.findByText(/^Đã xác nhận quan hệ và cách gọi/)).toBeTruthy();
  });

  it('names the fields staff edited', async () => {
    profile = makeProfile({ staff_override: true, staff_fields: ['address', 'name'], address_confidence: 'high', relationship_confidence: 'high' });
    const card = await openCard();
    const w = within(card);
    expect(w.getByText('Có: cách gọi, tên. Script phân tích không ghi đè các mục này; các mục khác vẫn theo lần chạy script sau.')).toBeTruthy();
    // both confidences are high: nothing left to confirm
    expect(w.queryByRole('button', { name: 'Xác nhận quan hệ và cách gọi đang hiện' })).toBeNull();
  });

  it('offers the five relationship kinds and saves staff, family or friend as a staff choice', async () => {
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    const select = w.getByLabelText('Người này là') as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(['khách', 'nhân viên của studio', 'gia đình', 'bạn bè', 'chưa rõ']);
    fireEvent.change(select, { target: { value: 'staff' } });
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ relationship: 'staff' });
    expect(await w.findByText('nhân viên (chắc chắn cao)')).toBeTruthy();
  });

  it('keeps the legacy personal label selectable only while a profile still has it', async () => {
    profile = makeProfile({ relationship: 'personal', relationship_confidence: 'high', model_facts: null });
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    const options = [...(w.getByLabelText('Người này là') as HTMLSelectElement).options].map((o) => o.value);
    expect(options).toEqual(['customer', 'staff', 'family', 'friend', 'unknown', 'personal']);
    fireEvent.change(w.getByLabelText('Người này là'), { target: { value: 'friend' } });
    expect((w.getByLabelText('Người này là') as HTMLSelectElement).value).toBe('friend');
    expect([...(w.getByLabelText('Người này là') as HTMLSelectElement).options].map((o) => o.value)).toContain('personal');
  });

  it('shows the last service with its source, and what the bot gets of it', async () => {
    profile = makeProfile({
      last_service: { key: 'goi-dau-thu-gian', service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', at: T_USED, source: 'chat', confidence: 'medium', sensitive: false },
      model_facts: { ...makeProfile().model_facts!, last_service: { name: 'Gội đầu thư giãn', date: '2026-10-20' } },
    });
    let w = within(await openCard());
    expect(w.getByText(`Gội đầu thư giãn · ${fmtDate(T_USED)} · đoán từ tin nhắn cũ, chắc chắn vừa`)).toBeTruthy();
    expect(w.getByText(/dịch vụ lần trước: Gội đầu thư giãn \(20\/10\/2026\)\.$/)).toBeTruthy();
    cleanup();
    profile = makeProfile({
      last_service: { key: 'cham-soc-dau-bung-kinh', service_id: 'cham-soc-dau-bung-kinh', name: 'Chăm sóc đau bụng kinh', at: T_USED, source: 'visit', confidence: 'high', sensitive: true },
    });
    w = within(await openCard());
    expect(w.getByText(`Chăm sóc đau bụng kinh · ${fmtDate(T_USED)} · nhân viên ghi buổi làm · nhóm nhạy cảm, bot không thấy`)).toBeTruthy();
  });

  it('explains that saving staff, family or friend needs migration 0008', async () => {
    patchStatus = 409;
    patchError = { code: 'invalid_state', message: 'customer_profiles is older than profiles v2: apply migration 0008_profiles_v2.sql' };
    const card = await openCard();
    const w = within(card);
    fireEvent.click(w.getByRole('button', { name: 'Sửa hồ sơ' }));
    fireEvent.change(w.getByLabelText('Người này là'), { target: { value: 'friend' } });
    fireEvent.click(w.getByRole('button', { name: 'Lưu hồ sơ' }));
    expect((await w.findByRole('alert')).textContent).toMatch(/chưa áp migration 0008_profiles_v2\.sql/);
  });

  it('shows the role derived from the profile and lets staff set and clear their own', async () => {
    profile = makeProfile({ role: 'customer', role_source: 'profile' });
    await openCard();
    const box = screen.getByRole('region', { name: 'Cài đặt của hội thoại' });
    const row = box.querySelector('.role-row') as HTMLElement;
    const select = () => within(row).getByRole('combobox', { name: 'Vai trò' }) as HTMLSelectElement;
    const autoReply = () => within(box).getByRole('switch', { name: 'Tự động trả lời' }) as HTMLInputElement;
    expect(row.textContent).toContain('Vai trò: khách (nguồn: suy từ hồ sơ)');
    // the select holds only what staff set here
    expect(select().value).toBe('');
    expect(autoReply().disabled).toBe(false);

    fireEvent.change(select(), { target: { value: 'staff' } });
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
    const call = calls.find((c) => c.method === 'PUT')!;
    expect(call.url).toBe('/staff/roles/p%3A9100123');
    expect(call.body).toEqual({ role: 'staff' });
    expect(await within(row).findByText('Đã đặt vai trò nhân viên: bot không trả lời người này nữa.')).toBeTruthy();
    await waitFor(() => expect(row.textContent).toContain('Vai trò: nhân viên (nguồn: lễ tân đặt)'));
    expect(select().value).toBe('staff');
    expect(autoReply().disabled).toBe(true);

    fireEvent.change(select(), { target: { value: '' } });
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').length).toBe(2));
    expect(calls.filter((c) => c.method === 'PUT')[1]!.body).toEqual({ role: null });
    await waitFor(() => expect(row.textContent).toContain('Vai trò: khách (nguồn: suy từ hồ sơ)'));
    expect(autoReply().disabled).toBe(false);
    // the profile itself was not touched
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
  });

  it('shows no role and no customer summary when the server sends neither', async () => {
    await openCard();
    const box = screen.getByRole('region', { name: 'Cài đặt của hội thoại' });
    expect((box.querySelector('.role-row') as HTMLElement).textContent).toContain('Vai trò: chưa có');
    expect((within(box).getByRole('combobox', { name: 'Vai trò' }) as HTMLSelectElement).value).toBe('');
    expect(screen.queryByRole('region', { name: 'Tóm tắt khách hàng' })).toBeNull();
    expect(calls.some((c) => c.url.startsWith('/staff/roles'))).toBe(false);
  });

  it('shows no profile card for an OA customer without a profile', async () => {
    conv = { ...summary, id: 'cnv_1', customer: { ...summary.customer, id: 'cus_1', zalo_user_id: '2468458835291979', display_name: 'Chị Mai' } };
    profile = undefined; // older server: no profile key at all
    render(<App />);
    fireEvent.click(await screen.findByText('Chị Mai'));
    expect(await screen.findByText('Chưa có tin nhắn.')).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Hồ sơ liên hệ' })).toBeNull();
  });
});

describe('profile helpers', () => {
  it('labels reason codes with their counts', () => {
    expect(profileReason('price_vocab:2')).toBe('hỏi giá (2 lần)');
    expect(profileReason('family_role:contact_parent')).toBe('vai trong gia đình: cha hoặc mẹ của chủ tài khoản');
    expect(profileReason('purchase_ratio:0.03')).toBe('tỉ lệ tin về mua dịch vụ: 3%');
    expect(profileReason('insider_contact:6')).toBe('người này nói về việc của studio như người làm (ca làm, lương, khách của studio) (6 lần)');
    expect(profileReason('long_chat_no_service')).toBe('nhắn từ 30 tin trở lên mà gần như không nhắc dịch vụ');
    expect(profileReason('new_code:4')).toBe('new_code (4 lần)');
  });

  it('describes how the bot addresses the contact', () => {
    expect(addressText('chị', 'Lan')).toBe('chị Lan');
    expect(addressText('anh/chị', 'Lan')).toBe('anh/chị');
    expect(addressText(null, null)).toBe('chưa xác định (bot gọi anh/chị)');
  });

  it('builds the PATCH body from the changed fields only and rejects a bad name', () => {
    const init = profileFormOf(makeProfile());
    expect(init).toEqual({ relationship: 'customer', address: 'chị', name: 'Lan' });
    expect(profilePatchFromForm({ relationship: 'customer', address: '', name: '  ' }, init)).toEqual({
      address_term: null,
      name_to_use: null,
    });
    expect(profilePatchFromForm({ relationship: 'unknown', address: 'bác', name: 'Thủy' }, init)).toEqual({
      relationship: 'unknown',
      address_term: 'bác',
      name_to_use: 'Thủy',
    });
    expect(profilePatchFromForm({ ...init, name: ' Lan ' }, init)).toEqual({});
    expect(profilePatchFromForm({ relationship: 'customer', address: 'chị', name: 'Lan2' }, init)).toBeNull();
    expect(profilePatchFromForm({ relationship: 'customer', address: 'chị', name: 'Abcdefghijklmnopqrstu' }, init)).toBeNull();
    // a low-confidence guess is not prefilled; no profile at all starts from unknown and empty fields
    expect(profileFormOf(makeProfile({ address_term: 'anh', address_confidence: 'low' })).address).toBe('');
    expect(profileFormOf(null)).toEqual({ relationship: 'unknown', address: '', name: '' });
    expect(profileConfirmPatch(makeProfile({ address_term: null, name_to_use: null }))).toEqual({ relationship: 'customer' });
  });

  it('formats dates in Vietnam time', () => {
    expect(fmtDate(Date.UTC(2026, 10, 7, 18, 0))).toBe('08/11/2026');
    expect(fmtDate(null)).toBe('');
  });
});
