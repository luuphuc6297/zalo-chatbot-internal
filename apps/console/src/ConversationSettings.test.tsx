// Per-conversation settings of docs/contracts.md section 14: the "Tự động trả lời" switch (14.4), the contact role
// (14.3), the room line (14.7) and the list badges. Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ContactRole, ConversationDetail, ConversationMode, ConversationSummary } from './api';
import { App } from './App';
import { AUTO_REPLY_TEXT, conversationBadges, fmtTime } from './labels';
import { globalModeOff, resolveRole, roomLine } from './screens/ConversationSettings';

const T = Date.UTC(2026, 10, 10, 3, 0);

const base: ConversationSummary = {
  id: 'cnv_s',
  customer: { id: 'cus_s', zalo_user_id: 'p:9100555', display_name: 'Mai Phạm', phone: null, minor_flag: null, last_user_interaction_at: T },
  bot_state: 'bot_active',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: false,
  takeover_by: null,
  takeover_until: null,
  last_message_at: T,
  last_message_preview: 'cho em hỏi giờ mở cửa',
  pending_drafts: 0,
  open_handoffs: 0,
};

type Call = { method: string; url: string; body: unknown };
type StubError = { status: number; code: string; message: string };
let calls: Call[] = [];
let conv: ConversationSummary = base;
let extra: Partial<ConversationDetail> = {};
let autoReplyError: StubError | null = null;
let roleError: StubError | null = null;

function detail(): ConversationDetail {
  return {
    conversation: { ...conv, session_id: null, session_turns: 0, catalog_version: 'cv_seed_20261108' },
    messages: [],
    drafts: [],
    handoffs: [],
    booking_requests: [],
    consents: [],
    ...extra,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function fail(e: StubError) {
  return json({ error: { code: e.code, message: e.message } }, e.status);
}

beforeEach(() => {
  calls = [];
  conv = base;
  extra = {};
  autoReplyError = null;
  roleError = null;
  localStorage.setItem('thomhouse.console.config', JSON.stringify({ baseUrl: '', staffToken: 'test-token', staffId: 'lan' }));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined;
      calls.push({ method, url, body });
      const headers = new Headers(init?.headers);
      if (url !== '/health' && headers.get('authorization') !== 'Bearer test-token') return json({ error: { code: 'unauthorized', message: 'no' } }, 401);
      if (url === '/health') return json({ ok: true, env: 'dev', zalo_mode: 'personal' });
      if (url.startsWith('/staff/handoffs')) return json({ items: [], next_cursor: null });
      if (url.startsWith('/staff/conversations?')) return json({ items: [conv], next_cursor: null });
      if (url === `/staff/conversations/${conv.id}`) return json(detail());
      // section 14.4: `on` also clears the conversation's own mode; `off` caps the effective mode at approve_each
      if (url === `/staff/conversations/${conv.id}/auto-reply` && method === 'PUT') {
        if (autoReplyError) return fail(autoReplyError);
        conv =
          body?.auto_reply === 'on'
            ? { ...conv, auto_reply: 'on', mode_override: null, effective_mode: 'auto_allowed' }
            : { ...conv, auto_reply: 'off', effective_mode: 'approve_each' };
        return json({ conversation: conv });
      }
      // section 14.4: a mode other than auto_allowed (or null) on a switched-on conversation switches it off
      if (url === `/staff/conversations/${conv.id}/mode` && method === 'PUT') {
        const mode = (body?.mode ?? null) as ConversationMode | null;
        conv = { ...conv, mode_override: mode };
        if (mode !== null && mode !== 'auto_allowed') conv = { ...conv, effective_mode: mode, ...(conv.auto_reply === 'on' ? { auto_reply: 'off' as const } : {}) };
        return json({ conversation: conv });
      }
      if (url === '/staff/roles/p%3A9100555' && method === 'PUT') {
        if (roleError) return fail(roleError);
        const role = (body?.role ?? null) as ContactRole | null;
        const { role: _role, role_source: _source, ...rest } = conv;
        conv = role ? { ...rest, role, role_source: 'staff' } : rest;
        return json({ role: role ? { zalo_user_id: 'p:9100555', role, source: 'staff', updated_at: T, updated_by: 'lan' } : null });
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

async function openSettings(name = 'Mai Phạm'): Promise<HTMLElement> {
  render(<App />);
  fireEvent.click(await screen.findByText(name));
  return screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
}

/** The row of the conversation list (the detail header repeats the name in a heading). */
async function listItem(name = 'Mai Phạm'): Promise<HTMLElement> {
  return (await screen.findByText(name, { selector: 'strong' })).closest('button') as HTMLElement;
}

const getSwitch = (box: HTMLElement) => within(box).getByRole('switch', { name: 'Tự động trả lời' }) as HTMLInputElement;
const confirmBox = () => screen.queryByRole('group', { name: 'Xác nhận bật tự động trả lời' });
const putsTo = (suffix: string) => calls.filter((c) => c.method === 'PUT' && c.url.endsWith(suffix));

describe('auto reply switch', () => {
  it('is off with an explanation of both positions while replies wait for approval', async () => {
    const box = await openSettings();
    const sw = getSwitch(box);
    expect(sw.checked).toBe(false);
    expect(sw.disabled).toBe(false);
    expect(within(box).getByText('đang tắt')).toBeTruthy();
    expect(within(box).getByText(AUTO_REPLY_TEXT.meaning)).toBeTruthy();
    expect(confirmBox()).toBeNull();
    expect(within(await listItem()).queryByText('tự động trả lời')).toBeNull();
  });

  it('asks for confirmation before switching on and sends nothing when staff decline', async () => {
    const box = await openSettings();
    fireEvent.click(getSwitch(box));
    const group = confirmBox() as HTMLElement;
    expect(group).toBeTruthy();
    expect(within(group).getByText(AUTO_REPLY_TEXT.confirm)).toBeTruthy();
    expect(putsTo('/auto-reply')).toEqual([]);

    fireEvent.click(within(group).getByRole('button', { name: 'Không bật' }));
    expect(confirmBox()).toBeNull();
    expect(putsTo('/auto-reply')).toEqual([]);
    expect(getSwitch(box).checked).toBe(false);
  });

  it('switches on after the confirmation and then shows the switch on', async () => {
    const box = await openSettings();
    fireEvent.click(getSwitch(box));
    fireEvent.click(within(confirmBox() as HTMLElement).getByRole('button', { name: 'Bật tự động trả lời' }));

    await waitFor(() => expect(putsTo('/auto-reply').length).toBe(1));
    expect(putsTo('/auto-reply')[0]).toEqual({ method: 'PUT', url: '/staff/conversations/cnv_s/auto-reply', body: { auto_reply: 'on' } });
    expect(await within(box).findByText('Đã bật tự động trả lời cho hội thoại này.')).toBeTruthy();
    await waitFor(() => expect(getSwitch(box).checked).toBe(true));
    expect(within(box).getByText('đang bật')).toBeTruthy();
    expect(within(box).getByText(`${AUTO_REPLY_TEXT.meaning} ${AUTO_REPLY_TEXT.onDetail}`)).toBeTruthy();
    expect(confirmBox()).toBeNull();
    // the detail header carries the same badge as the list
    expect(screen.getAllByText('tự động trả lời').length).toBeGreaterThan(0);
  });

  it('switches off at once, without a confirmation step', async () => {
    conv = { ...base, auto_reply: 'on', effective_mode: 'auto_allowed' };
    const box = await openSettings();
    expect(getSwitch(box).checked).toBe(true);
    fireEvent.click(getSwitch(box));
    expect(confirmBox()).toBeNull();

    await waitFor(() => expect(putsTo('/auto-reply').length).toBe(1));
    expect(putsTo('/auto-reply')[0]!.body).toEqual({ auto_reply: 'off' });
    expect(await within(box).findByText('Đã tắt tự động trả lời cho hội thoại này.')).toBeTruthy();
    await waitFor(() => expect(getSwitch(box).checked).toBe(false));
  });

  it('is on, with a list badge, when the effective mode is auto_allowed from the global setting', async () => {
    conv = { ...base, effective_mode: 'auto_allowed' };
    render(<App />);
    const item = await listItem();
    expect(within(item).getByText('tự động trả lời')).toBeTruthy();
    fireEvent.click(item);
    const box = await screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
    expect(getSwitch(box).checked).toBe(true);
    expect(getSwitch(box).disabled).toBe(false);
  });

  it('is disabled with the reason for a manager or staff contact, and the list shows the role instead', async () => {
    conv = { ...base, effective_mode: 'auto_allowed', role: 'staff', role_source: 'zalo_label' };
    render(<App />);
    const item = await listItem();
    expect(within(item).getByText('vai trò: nhân viên')).toBeTruthy();
    expect(within(item).queryByText('tự động trả lời')).toBeNull();
    fireEvent.click(item);
    const box = await screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
    const sw = getSwitch(box);
    expect(sw.checked).toBe(false);
    expect(sw.disabled).toBe(true);
    expect(within(box).getByText(AUTO_REPLY_TEXT.internal)).toBeTruthy();
    fireEvent.click(sw);
    expect(confirmBox()).toBeNull();
    expect(putsTo('/auto-reply')).toEqual([]);
  });

  it('is disabled with a note while the global mode is off', async () => {
    conv = { ...base, effective_mode: 'off' };
    const box = await openSettings();
    expect(getSwitch(box).disabled).toBe(true);
    expect(getSwitch(box).checked).toBe(false);
    expect(within(box).getByText(AUTO_REPLY_TEXT.globalOff)).toBeTruthy();
    expect(within(box).queryByRole('button', { name: AUTO_REPLY_TEXT.clearStored })).toBeNull();
  });

  it('lets staff clear a stored on while the global mode is off', async () => {
    conv = { ...base, effective_mode: 'off', auto_reply: 'on' };
    const box = await openSettings();
    expect(getSwitch(box).disabled).toBe(true);
    expect(within(box).getByText(AUTO_REPLY_TEXT.storedWhileGlobalOff)).toBeTruthy();
    fireEvent.click(within(box).getByRole('button', { name: 'Bỏ tự động trả lời của hội thoại này' }));
    await waitFor(() => expect(putsTo('/auto-reply').length).toBe(1));
    expect(putsTo('/auto-reply')[0]!.body).toEqual({ auto_reply: 'off' });
  });

  it('stays usable when the conversation itself is set to off', async () => {
    conv = { ...base, effective_mode: 'off', mode_override: 'off' };
    const box = await openSettings();
    expect(getSwitch(box).disabled).toBe(false);
    expect(within(box).queryByText(AUTO_REPLY_TEXT.globalOff)).toBeNull();
  });

  it('explains a 404 from an older server and leaves the switch off', async () => {
    autoReplyError = { status: 404, code: 'not_found', message: 'nope' };
    const box = await openSettings();
    fireEvent.click(getSwitch(box));
    fireEvent.click(within(confirmBox() as HTMLElement).getByRole('button', { name: 'Bật tự động trả lời' }));
    expect(
      await within(box).findByText(
        'Máy chủ không có địa chỉ này, nên chưa đổi được công tắc tự động trả lời. Có thể máy chủ đang chạy bản cũ: cập nhật và khởi động lại máy chủ, rồi làm lại.',
      ),
    ).toBeTruthy();
    expect(getSwitch(box).checked).toBe(false);
    expect(getSwitch(box).disabled).toBe(false);
  });

  it('explains a 409 that names migration 0010', async () => {
    autoReplyError = { status: 409, code: 'invalid_state', message: 'apply migration 0010_rooms_roles_customer.sql' };
    const box = await openSettings();
    fireEvent.click(getSwitch(box));
    fireEvent.click(within(confirmBox() as HTMLElement).getByRole('button', { name: 'Bật tự động trả lời' }));
    expect(
      await within(box).findByText(
        'Máy chủ chưa áp migration 0010_rooms_roles_customer.sql, nên chưa đổi được công tắc tự động trả lời. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.',
      ),
    ).toBeTruthy();
  });

  it('explains a 409 for an internal contact the console did not know about', async () => {
    autoReplyError = { status: 409, code: 'invalid_state', message: 'internal contact' };
    const box = await openSettings();
    fireEvent.click(getSwitch(box));
    fireEvent.click(within(confirmBox() as HTMLElement).getByRole('button', { name: 'Bật tự động trả lời' }));
    expect(await within(box).findByText(AUTO_REPLY_TEXT.serverSaysInternal)).toBeTruthy();
    expect(getSwitch(box).checked).toBe(false);
  });
});

describe('conversation mode next to the switch', () => {
  const modeSelect = (box: HTMLElement) => within(box).getByLabelText(/^Chế độ riêng của hội thoại/) as HTMLSelectElement;

  it('keeps the mode select as the setting for when the switch is off', async () => {
    const box = await openSettings();
    const select = modeSelect(box);
    expect(select.value).toBe('');
    expect([...select.options].map((o) => o.textContent)).toEqual([
      'Theo cài đặt chung',
      'Tắt bot',
      'Chỉ soạn nháp',
      'Duyệt từng tin (mặc định)',
      'Cho bot tự gửi',
    ]);
    fireEvent.change(select, { target: { value: 'draft_only' } });
    await waitFor(() => expect(putsTo('/mode').length).toBe(1));
    expect(putsTo('/mode')[0]).toEqual({ method: 'PUT', url: '/staff/conversations/cnv_s/mode', body: { mode: 'draft_only' } });
    await waitFor(() => expect(modeSelect(box).value).toBe('draft_only'));
  });

  it('says that choosing a lower mode switches the switch off, and shows it off afterwards', async () => {
    conv = { ...base, auto_reply: 'on', effective_mode: 'auto_allowed' };
    const box = await openSettings();
    expect(box.textContent).toContain(AUTO_REPLY_TEXT.modeWhileOn);
    fireEvent.change(modeSelect(box), { target: { value: 'approve_each' } });
    await waitFor(() => expect(putsTo('/mode').length).toBe(1));
    expect(putsTo('/mode')[0]!.body).toEqual({ mode: 'approve_each' });
    await waitFor(() => expect(getSwitch(box).checked).toBe(false));
    expect(box.textContent).toContain(AUTO_REPLY_TEXT.modeWhileOff);
    expect(box.textContent).not.toContain(AUTO_REPLY_TEXT.modeWhileOn);
  });
});

describe('role row', () => {
  const roleSelect = (box: HTMLElement) => within(box).getByRole('combobox', { name: 'Vai trò' }) as HTMLSelectElement;
  const rowText = (box: HTMLElement) => roleSelect(box).closest('.role-row')!.textContent ?? '';

  it('shows a role derived from the profile with its source and offers the three roles', async () => {
    conv = { ...base, role: 'customer', role_source: 'profile' };
    render(<App />);
    const item = await listItem();
    expect(within(item).getByText('vai trò: khách')).toBeTruthy();
    fireEvent.click(item);
    const box = await screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
    expect(rowText(box)).toContain('Vai trò: khách (nguồn: suy từ hồ sơ)');
    const select = roleSelect(box);
    // the select holds only what staff set here
    expect(select.value).toBe('');
    expect([...select.options].map((o) => o.textContent)).toEqual(['Không đặt (theo nhãn Zalo hoặc hồ sơ)', 'khách', 'quản lý', 'nhân viên']);
    expect(getSwitch(box).disabled).toBe(false);
  });

  it('shows a Zalo label as the source without putting it in the select', async () => {
    conv = { ...base, role: 'manager', role_source: 'zalo_label' };
    const box = await openSettings();
    expect(rowText(box)).toContain('Vai trò: quản lý (nguồn: nhãn Zalo)');
    expect(roleSelect(box).value).toBe('');
  });

  it('says when there is no role yet', async () => {
    const box = await openSettings();
    expect(rowText(box)).toContain('Vai trò: chưa có');
    expect(rowText(box)).not.toContain('nguồn');
  });

  it('sets a staff role and then disables the auto reply switch', async () => {
    const box = await openSettings();
    fireEvent.change(roleSelect(box), { target: { value: 'manager' } });
    await waitFor(() => expect(putsTo('/staff/roles/p%3A9100555').length).toBe(1));
    expect(putsTo('/staff/roles/p%3A9100555')[0]!.body).toEqual({ role: 'manager' });
    expect(await within(box).findByText('Đã đặt vai trò quản lý: bot không trả lời người này nữa.')).toBeTruthy();
    await waitFor(() => expect(roleSelect(box).value).toBe('manager'));
    expect(rowText(box)).toContain('Vai trò: quản lý (nguồn: lễ tân đặt)');
    expect(getSwitch(box).disabled).toBe(true);
    expect(within(box).getByText(AUTO_REPLY_TEXT.internal)).toBeTruthy();
  });

  it('clears the staff role with null', async () => {
    conv = { ...base, role: 'staff', role_source: 'staff' };
    const box = await openSettings();
    expect(roleSelect(box).value).toBe('staff');
    fireEvent.change(roleSelect(box), { target: { value: '' } });
    await waitFor(() => expect(putsTo('/staff/roles/p%3A9100555').length).toBe(1));
    expect(putsTo('/staff/roles/p%3A9100555')[0]!.body).toEqual({ role: null });
    expect(await within(box).findByText('Đã bỏ vai trò lễ tân đặt. Vai trò lấy lại theo nhãn Zalo hoặc hồ sơ liên hệ, nếu có.')).toBeTruthy();
    await waitFor(() => expect(rowText(box)).toContain('Vai trò: chưa có'));
    expect(getSwitch(box).disabled).toBe(false);
  });

  it('takes the role from the customer summary before the conversation', async () => {
    conv = { ...base, role: 'customer', role_source: 'profile' };
    extra = { customer_summary: { role: 'manager', role_source: 'staff' } };
    const box = await openSettings();
    expect(rowText(box)).toContain('Vai trò: quản lý (nguồn: lễ tân đặt)');
    expect(roleSelect(box).value).toBe('manager');
    expect(getSwitch(box).disabled).toBe(true);
    expect(screen.getAllByText('vai trò: quản lý').length).toBeGreaterThan(0);
  });

  it('leaves the switch usable for a staff role read from the contact profile', async () => {
    // The server keeps the bots away only from a contact with a role row (Zalo label or staff), so a role the
    // summary derives from the profile does not lock the switch nor hide the auto reply badge.
    conv = { ...base, effective_mode: 'auto_allowed' };
    extra = { customer_summary: { role: 'staff', role_source: 'profile' } };
    const box = await openSettings();
    expect(rowText(box)).toContain('Vai trò: nhân viên (nguồn: suy từ hồ sơ)');
    expect(getSwitch(box).disabled).toBe(false);
    expect(getSwitch(box).checked).toBe(true);
    expect(within(box).queryByText(AUTO_REPLY_TEXT.internal)).toBeNull();
    const head = box.closest('.detail')!.querySelector('.detail-head')!;
    expect(within(head as HTMLElement).getByText('tự động trả lời')).toBeTruthy();
  });

  it('has no role row on an OA conversation without a role, and no select with one', async () => {
    conv = { ...base, customer: { ...base.customer, zalo_user_id: '2468458835291979' } };
    const box = await openSettings();
    expect(box.querySelector('.role-row')).toBeNull();
    cleanup();

    conv = { ...conv, role: 'customer', role_source: 'profile' };
    const again = await openSettings();
    expect(again.querySelector('.role-row')!.textContent).toContain('Vai trò: khách (nguồn: suy từ hồ sơ)');
    expect(within(again).queryByRole('combobox', { name: 'Vai trò' })).toBeNull();
  });

  it('explains a 404 from an older server when saving a role', async () => {
    roleError = { status: 404, code: 'not_found', message: 'nope' };
    const box = await openSettings();
    fireEvent.change(roleSelect(box), { target: { value: 'staff' } });
    expect(
      await within(box).findByText(
        'Máy chủ không có địa chỉ này, nên chưa lưu được vai trò. Có thể máy chủ đang chạy bản cũ: cập nhật và khởi động lại máy chủ, rồi làm lại.',
      ),
    ).toBeTruthy();
    expect(roleSelect(box).value).toBe('');
  });

  it('explains a 409 that names migration 0010 when saving a role', async () => {
    roleError = { status: 409, code: 'invalid_state', message: 'apply migration 0010_rooms_roles_customer.sql' };
    const box = await openSettings();
    fireEvent.change(roleSelect(box), { target: { value: 'customer' } });
    expect(
      await within(box).findByText(
        'Máy chủ chưa áp migration 0010_rooms_roles_customer.sql, nên chưa lưu được vai trò. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.',
      ),
    ).toBeTruthy();
  });
});

describe('room line', () => {
  it('shows the room of the conversation in the detail header', async () => {
    extra = { room: { channel_id: 'room_cnv_s', synced_at: T, pending: 2 } };
    await openSettings();
    const line = screen.getByText(`Phòng hai bot: mã phòng room_cnv_s · đồng bộ gần nhất lúc ${fmtTime(T)} · 2 tin chưa đưa vào phòng`);
    expect(line.closest('header')).toBeTruthy();
  });

  it('shows nothing when the detail has no room', async () => {
    await openSettings();
    expect(screen.queryByText(/^Phòng hai bot/)).toBeNull();
    cleanup();

    extra = { room: null };
    await openSettings();
    expect(screen.queryByText(/^Phòng hai bot/)).toBeNull();
  });

  it('words a room that was never synced and a room with nothing waiting', () => {
    expect(roomLine({ channel_id: 'room_a' })).toBe('Phòng hai bot: mã phòng room_a · chưa đồng bộ lần nào');
    expect(roomLine({ channel_id: 'room_a', synced_at: null, pending: 0 })).toBe(
      'Phòng hai bot: mã phòng room_a · chưa đồng bộ lần nào · không còn tin nào chờ đưa vào phòng',
    );
  });
});

describe('helpers', () => {
  it('resolves the role from the first source that has one', () => {
    expect(resolveRole(null, undefined, {})).toEqual({ role: null, source: null });
    expect(resolveRole({ role: null }, { role: 'staff', role_source: 'zalo_label' }, { role: 'customer', role_source: 'profile' })).toEqual({
      role: 'staff',
      source: 'zalo_label',
    });
    expect(resolveRole({ role: 'customer' })).toEqual({ role: 'customer', source: null });
  });

  it('reads a global off from the effective mode unless the conversation itself is off', () => {
    expect(globalModeOff({ effective_mode: 'off', mode_override: null })).toBe(true);
    expect(globalModeOff({ effective_mode: 'off', mode_override: 'approve_each' })).toBe(true);
    expect(globalModeOff({ effective_mode: 'off', mode_override: 'off' })).toBe(false);
    expect(globalModeOff({ effective_mode: 'approve_each', mode_override: null })).toBe(false);
  });

  it('adds the auto reply and role badges after the existing ones', () => {
    const quiet = { ...base, bot_state: 'staff_only' as const };
    expect(conversationBadges({ ...base, effective_mode: 'auto_allowed' }).map((b) => b.text)).toEqual(['bot đang trả lời', 'tự động trả lời']);
    expect(conversationBadges({ ...base, effective_mode: 'auto_allowed', role: 'customer' })).toEqual([
      { kind: 'bot', text: 'bot đang trả lời' },
      { kind: 'bot', text: 'tự động trả lời' },
      { kind: 'muted', text: 'vai trò: khách' },
    ]);
    expect(conversationBadges({ ...quiet, effective_mode: 'auto_allowed', role: 'manager' })).toEqual([
      { kind: 'staff', text: 'nhân viên đang xử lý' },
      { kind: 'staff', text: 'vai trò: quản lý' },
    ]);
    // without the new fields the badges are the ones of before
    expect(conversationBadges(base).map((b) => b.text)).toEqual(['bot đang trả lời']);
  });
});
