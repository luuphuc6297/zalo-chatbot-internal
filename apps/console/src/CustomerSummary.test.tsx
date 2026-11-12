// Customer summary block of a conversation (docs/contracts.md section 14.6) and the forms of section 14.5:
// phone, record a visit, add / use / void a benefit, the list of recorded visits, and money formatting.
// Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationDetail, ConversationSummary, CustomerBenefit, CustomerSummary, VisitView } from './api';
import { App } from './App';
import { NO_VISIT_DATA_CHAT_TEXT, customerStatusReason, fmtDate, fmtTime, fmtVnd, fmtYmd, normalizePhone, parseVnd, vnDateEndMs, vndInputText } from './labels';
import {
  EMPTY_BENEFIT_FORM,
  benefitCreateBody,
  benefitFormProblem,
  benefitStateText,
  hasVisitData,
  lastVisitText,
  windowText,
} from './screens/CustomerSummaryCard';
import { EMPTY_VISIT_EXTRAS, summaryBenefitText, usableBenefitChoices, visitExtrasPayload, visitExtrasProblem } from './screens/VisitFields';

const T = Date.UTC(2026, 10, 12, 3, 0);
const T_VISIT = Date.UTC(2026, 9, 30, 7, 30); // 30/10/2026 14:30, Vietnam time
const T_OLD = Date.UTC(2026, 8, 2, 3, 0);
const FAR = Date.parse('2099-01-31T23:59:59+07:00');
const PAST = Date.parse('2020-01-31T23:59:59+07:00');

const conv: ConversationSummary = {
  id: 'cnv_c',
  customer: { id: 'cus_c', zalo_user_id: 'p:9100888', display_name: 'Thu Lê', phone: null, minor_flag: null, last_user_interaction_at: T },
  bot_state: 'bot_active',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: false,
  takeover_by: null,
  takeover_until: null,
  last_message_at: T,
  last_message_preview: 'em muốn đặt lịch cuối tuần',
  pending_drafts: 0,
  open_handoffs: 0,
};

// modelled on the example of section 14.6
const fullSummary: CustomerSummary = {
  role: 'customer',
  role_source: 'zalo_label',
  name: 'Thu',
  address_term: 'chị',
  phone: '0901234567',
  status: 'returning',
  visits_total: 7,
  last_visit: {
    visited_at: T_VISIT,
    date: '2026-10-30',
    time: '14:30',
    services: [{ service_id: 'massage-chan', name: 'Massage chân 60 phút' }],
    technician: 'Hoa',
    amount_vnd: 450000,
  },
  days_since_last_visit: 13,
  usual_gap_days: 21,
  gap_basis: 'own',
  absent_after_days: 42,
  lifetime_spend_vnd: 2950000,
  lifetime_spend_visits: 6,
  window: {
    days: 183,
    from_date: '2026-05-13',
    visits: 3,
    spend_vnd: 1350000,
    avg_spend_vnd: 450000,
    services: [{ service_id: 'massage-chan', name: 'Massage chân 60 phút', count: 3 }],
  },
  benefits: [{ id: 'ben_1', kind: 'package', title: 'Gói 10 buổi gội dưỡng sinh', remaining: 4, expires_on: '2099-01-31' }],
};

const emptySummary: CustomerSummary = { role: null, role_source: null, name: null, address_term: null, phone: null, status: 'first_inquiry', visits_total: 0, benefits: [] };

const benPackage: CustomerBenefit = {
  id: 'ben_1',
  customer_id: 'cus_c',
  kind: 'package',
  title: 'Gói 10 buổi gội dưỡng sinh',
  total_count: 10,
  used_count: 6,
  remaining: 4,
  expires_at: FAR,
  status: 'active',
};
const benVoid: CustomerBenefit = { id: 'ben_2', customer_id: 'cus_c', kind: 'voucher', title: 'Voucher tặng 1 buổi massage chân', total_count: 1, used_count: 0, expires_at: null, status: 'void' };
const benExpired: CustomerBenefit = { id: 'ben_3', customer_id: 'cus_c', kind: 'voucher', title: 'Voucher sinh nhật', total_count: 1, used_count: 0, expires_at: PAST, status: 'active' };

const visitRows: VisitView[] = [
  { id: 'vis_2', customer_id: 'cus_c', service_id: 'massage-chan', service_name: 'Massage chân 60 phút', visited_at: T_VISIT, duration_min: 60, amount_vnd: 450000, technician: 'Hoa', source: 'staff' },
  { id: 'vis_1', customer_id: 'cus_c', service_id: null, visited_at: T_OLD, benefit_id: 'ben_1', source: 'import' },
];

const MIGRATION_409: StubError = { status: 409, code: 'invalid_state', message: 'apply migration 0010_rooms_roles_customer.sql' };
const OLD_SERVER_404: StubError = { status: 404, code: 'not_found', message: 'nope' };
const migrationText = (what: string) =>
  `Máy chủ chưa áp migration 0010_rooms_roles_customer.sql, nên chưa ${what}. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.`;
const oldServerText = (what: string) =>
  `Máy chủ không có địa chỉ này, nên chưa ${what}. Có thể máy chủ đang chạy bản cũ: cập nhật và khởi động lại máy chủ, rồi làm lại.`;

type Call = { method: string; url: string; body: unknown };
type StubError = { status: number; code: string; message: string };
let calls: Call[] = [];
let summary: CustomerSummary | null | undefined = fullSummary;
let benefits: CustomerBenefit[] = [];
let visitsBody: { visits?: VisitView[]; items?: VisitView[] } = { visits: visitRows };
let benefitsListError: StubError | null = null;
let benefitWriteError: StubError | null = null;
let visitsListError: StubError | null = null;
let visitWriteError: StubError | null = null;
let customerError: StubError | null = null;

function detail(): ConversationDetail {
  return {
    conversation: { ...conv, session_id: null, session_turns: 0, catalog_version: 'cv_seed_20261108' },
    messages: [],
    drafts: [],
    handoffs: [],
    booking_requests: [],
    consents: [],
    ...(summary === undefined ? {} : { customer_summary: summary }),
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
  summary = fullSummary;
  benefits = [benPackage, benVoid, benExpired];
  visitsBody = { visits: visitRows };
  benefitsListError = null;
  benefitWriteError = null;
  visitsListError = null;
  visitWriteError = null;
  customerError = null;
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
      if (url.startsWith('/staff/booking-requests')) return json({ items: [], next_cursor: null });

      if (url === '/staff/benefits?customer_id=cus_c' && method === 'GET') {
        return benefitsListError ? fail(benefitsListError) : json({ benefits });
      }
      if (url === '/staff/benefits' && method === 'POST') {
        if (benefitWriteError) return fail(benefitWriteError);
        const total = Number(body?.total_count);
        const used = Number(body?.used_count ?? 0);
        const created = { ...body, id: 'ben_new', used_count: used, remaining: total - used, status: 'active' } as unknown as CustomerBenefit;
        benefits = [created, ...benefits];
        return json({ benefit: created }, 201);
      }
      if (url.startsWith('/staff/benefits/') && method === 'PATCH') {
        if (benefitWriteError) return fail(benefitWriteError);
        const id = url.slice('/staff/benefits/'.length);
        const before = benefits.find((b) => b.id === id);
        if (!before) return fail(OLD_SERVER_404);
        const after = { ...before, ...body } as CustomerBenefit;
        after.remaining = after.total_count - after.used_count;
        benefits = benefits.map((b) => (b.id === id ? after : b));
        return json({ benefit: after });
      }

      if (url === '/staff/visits?customer_id=cus_c' && method === 'GET') {
        return visitsListError ? fail(visitsListError) : json(visitsBody);
      }
      if (url === '/staff/visits' && method === 'POST') {
        if (visitWriteError) return fail(visitWriteError);
        return json(
          {
            visit_id: 'vis_new',
            jobs: [
              { job_id: 'job_1', type: 'thank_you', run_at: T + 86_400_000, status: 'scheduled' },
              { job_id: 'job_2', type: 'check_in', run_at: T + 2 * 86_400_000, status: 'scheduled' },
            ],
          },
          201,
        );
      }

      if (url === '/staff/customers/cus_c' && method === 'PATCH') {
        if (customerError) return fail(customerError);
        const phone = (body?.phone ?? null) as string | null;
        if (summary) summary = { ...summary, phone };
        return json({ customer: { ...conv.customer, phone } });
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

async function openDetail(): Promise<HTMLElement> {
  render(<App />);
  fireEvent.click(await screen.findByText('Thu Lê'));
  return screen.findByRole('region', { name: 'Cài đặt của hội thoại' });
}

async function openCard(): Promise<HTMLElement> {
  await openDetail();
  return screen.findByRole('region', { name: 'Tóm tắt khách hàng' });
}

/** Text of the value next to one term of the summary; null when the term is not shown. */
function fact(card: HTMLElement, term: string): string | null {
  const dt = [...card.querySelectorAll('dt')].find((el) => el.textContent === term);
  return dt ? (dt.nextElementSibling?.textContent ?? '') : null;
}

async function openPanel(card: HTMLElement, button: string, group: string): Promise<HTMLElement> {
  fireEvent.click(within(card).getByRole('button', { name: button }));
  return within(card).findByRole('group', { name: group });
}

const openVisitPanel = (card: HTMLElement) => openPanel(card, 'Ghi buổi làm cho khách này', 'Ghi buổi làm cho khách này');
const openBenefitsPanel = (card: HTMLElement) => openPanel(card, 'Thêm hoặc dùng quyền lợi', 'Quyền lợi của khách');
const openVisitsPanel = (card: HTMLElement) => openPanel(card, 'Xem các buổi làm đã ghi', 'Các buổi làm đã ghi');
const sent = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url);
const type = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

describe('customer summary block', () => {
  it('shows every field the owner asked for when visits are recorded', async () => {
    const card = await openCard();
    expect(fact(card, 'Tên')).toBe('Thu');
    expect(fact(card, 'Cách xưng hô')).toBe('chị');
    expect(fact(card, 'Số điện thoại')).toContain('0901234567');
    expect(fact(card, 'Trạng thái')).toBe(
      'khách quay lại Khách đã đến 7 lần. Lần đến gần nhất cách đây 13 ngày, chưa quá mốc 42 ngày (thường 21 ngày quay lại một lần).',
    );
    expect(fact(card, 'Tổng số lần đã đến')).toBe('7 lần');
    expect(fact(card, 'Dịch vụ cuối cùng')).toBe('Massage chân 60 phút · 30/10/2026 lúc 14:30 · kỹ thuật viên Hoa · 450.000đ');
    expect(fact(card, 'Tổng số tiền đã dùng')).toBe('2.950.000đ (tính trên 6 buổi có ghi số tiền)');
    expect(fact(card, 'Đã bao lâu chưa đến')).toBe('13 ngày');
    expect(fact(card, 'Thường cách bao lâu quay lại')).toBe('21 ngày (tính từ các lần đến của chính khách)');
    expect(fact(card, 'Khoảng thời gian tính')).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 3 buổi');
    expect(fact(card, 'Dịch vụ thường dùng')).toBe('Massage chân 60 phút (3 lần)');
    expect(fact(card, 'Mức chi mỗi lần')).toBe('trung bình 450.000đ');
    expect(fact(card, 'Tổng chi trong khoảng')).toBe('1.350.000đ');
    expect(fact(card, 'Quyền lợi chưa dùng')).toBe('Gói 10 buổi gội dưỡng sinh: còn 4 lần, hạn 31/01/2099');
    expect(within(card).queryByText(NO_VISIT_DATA_CHAT_TEXT)).toBeNull();
  });

  it('says clearly that there is no visit data yet and hides the rows that need visits', async () => {
    summary = emptySummary;
    const card = await openCard();
    // no `chat` field (a contact without chat facts): the sentence still names the chat analyzer, which the server
    // shipped with this console has
    expect(emptySummary).not.toHaveProperty('chat');
    expect(within(card).getByText(NO_VISIT_DATA_CHAT_TEXT)).toBeTruthy();
    expect(card.textContent).not.toContain('tin nhắn cũ không được tính là buổi làm');
    expect(fact(card, 'Tên')).toBe('chưa có tên để gọi');
    expect(fact(card, 'Cách xưng hô')).toBe('chưa xác định (bot gọi anh/chị)');
    expect(fact(card, 'Số điện thoại')).toContain('chưa có');
    expect(fact(card, 'Trạng thái')).toBe('mới hỏi, chưa đến lần nào Chưa có buổi làm nào được ghi.');
    expect(fact(card, 'Tổng số lần đã đến')).toBe('0 lần');
    expect(fact(card, 'Quyền lợi chưa dùng')).toBe('không có');
    for (const term of ['Dịch vụ cuối cùng', 'Tổng số tiền đã dùng', 'Đã bao lâu chưa đến', 'Thường cách bao lâu quay lại', 'Dịch vụ thường dùng', 'Mức chi mỗi lần']) {
      expect(fact(card, term)).toBeNull();
    }
    // the forms stay reachable: the first visit is recorded from here
    expect(within(card).getByRole('button', { name: 'Ghi buổi làm cho khách này' })).toBeTruthy();
  });

  it('copes with a summary that carries no field at all', async () => {
    summary = {};
    const card = await openCard();
    expect(fact(card, 'Tổng số lần đã đến')).toBe('chưa có số liệu');
    expect(fact(card, 'Trạng thái')).toBeNull();
    expect(within(card).getByText(NO_VISIT_DATA_CHAT_TEXT)).toBeTruthy();
  });

  it('explains a long absence with the numbers behind it', async () => {
    summary = { ...fullSummary, status: 'long_absent', days_since_last_visit: 60 };
    const card = await openCard();
    expect(fact(card, 'Trạng thái')).toBe('lâu chưa quay lại Lần đến gần nhất cách đây 60 ngày, quá mốc 42 ngày (thường 21 ngày quay lại một lần).');
    expect(fact(card, 'Đã bao lâu chưa đến')).toBe('60 ngày');
  });

  it('words visits without amounts, and a window without visits', async () => {
    summary = {
      ...fullSummary,
      status: 'first_visit_done',
      visits_total: 1,
      gap_basis: 'default',
      last_visit: { visited_at: T_VISIT },
      lifetime_spend_vnd: 0,
      lifetime_spend_visits: 0,
      window: { days: 183, from_date: '2026-05-13', visits: 0, spend_vnd: null, avg_spend_vnd: null, services: [] },
    };
    const card = await openCard();
    expect(fact(card, 'Dịch vụ cuối cùng')).toBe(`chưa ghi tên dịch vụ · ${fmtTime(T_VISIT)} · chưa ghi kỹ thuật viên · chưa ghi số tiền`);
    expect(fact(card, 'Tổng số tiền đã dùng')).toBe('chưa có buổi nào ghi số tiền');
    expect(fact(card, 'Thường cách bao lâu quay lại')).toBe('21 ngày (khách mới đến một lần nên lấy mức mặc định)');
    expect(fact(card, 'Dịch vụ thường dùng')).toBe('chưa có buổi nào trong khoảng thời gian tính');
    expect(fact(card, 'Mức chi mỗi lần')).toBe('chưa có buổi nào ghi số tiền trong khoảng thời gian tính');
    expect(fact(card, 'Tổng chi trong khoảng')).toBe('chưa có buổi nào ghi số tiền trong khoảng thời gian tính');
  });

  it('renders nothing when an older server sends no customer summary', async () => {
    summary = undefined;
    await openDetail();
    expect(screen.queryByRole('region', { name: 'Tóm tắt khách hàng' })).toBeNull();
    cleanup();

    summary = null;
    await openDetail();
    expect(screen.queryByRole('region', { name: 'Tóm tắt khách hàng' })).toBeNull();
    expect(calls.some((c) => c.url.startsWith('/staff/benefits') || c.url.startsWith('/staff/visits'))).toBe(false);
  });
});

describe('phone of the customer', () => {
  const PHONE_RULE = 'Số điện thoại gồm 9 đến 11 chữ số, ví dụ 0901234567. Để trống nếu muốn xóa số.';
  const startEdit = (card: HTMLElement) => {
    fireEvent.click(within(card).getByRole('button', { name: 'Sửa số điện thoại' }));
    return within(card).getByLabelText('Số điện thoại') as HTMLInputElement;
  };
  const saveButton = (card: HTMLElement) => within(card).getByRole('button', { name: 'Lưu số điện thoại' }) as HTMLButtonElement;

  it('validates the number and saves it the way the server stores it', async () => {
    const card = await openCard();
    const input = startEdit(card);
    expect(input.value).toBe('0901234567');
    expect(saveButton(card).disabled).toBe(true); // nothing changed yet

    type(input, '12345');
    expect(within(card).getByText(PHONE_RULE)).toBeTruthy();
    expect(saveButton(card).disabled).toBe(true);

    type(input, '+84 90 765 4321');
    expect(within(card).queryByText(PHONE_RULE)).toBeNull();
    fireEvent.click(saveButton(card));
    await waitFor(() => expect(sent('PATCH', '/staff/customers/cus_c').length).toBe(1));
    expect(sent('PATCH', '/staff/customers/cus_c')[0]!.body).toEqual({ phone: '0907654321' });
    expect(await within(card).findByText('Đã lưu số điện thoại.')).toBeTruthy();
    await waitFor(() => expect(fact(card, 'Số điện thoại')).toContain('0907654321'));
    expect(within(card).queryByLabelText('Số điện thoại')).toBeNull();
  });

  it('clears the number with null when the field is emptied', async () => {
    const card = await openCard();
    type(startEdit(card), '  ');
    fireEvent.click(saveButton(card));
    await waitFor(() => expect(sent('PATCH', '/staff/customers/cus_c').length).toBe(1));
    expect(sent('PATCH', '/staff/customers/cus_c')[0]!.body).toEqual({ phone: null });
    expect(await within(card).findByText('Đã xóa số điện thoại.')).toBeTruthy();
    await waitFor(() => expect(fact(card, 'Số điện thoại')).toContain('chưa có'));
  });

  it('sends nothing when staff cancel the edit', async () => {
    const card = await openCard();
    type(startEdit(card), '0907654321');
    fireEvent.click(within(card).getByRole('button', { name: 'Hủy sửa số điện thoại' }));
    expect(within(card).queryByLabelText('Số điện thoại')).toBeNull();
    expect(sent('PATCH', '/staff/customers/cus_c')).toEqual([]);
    expect(fact(card, 'Số điện thoại')).toContain('0901234567');
  });

  it('explains a 409 before migration 0010 and a 404 from an older server', async () => {
    customerError = MIGRATION_409;
    const card = await openCard();
    type(startEdit(card), '0907654321');
    fireEvent.click(saveButton(card));
    expect(await within(card).findByText(migrationText('lưu được số điện thoại'))).toBeTruthy();
    // the typed number is still there for another try
    expect((within(card).getByLabelText('Số điện thoại') as HTMLInputElement).value).toBe('0907654321');

    customerError = OLD_SERVER_404;
    fireEvent.click(saveButton(card));
    expect(await within(card).findByText(oldServerText('lưu được số điện thoại'))).toBeTruthy();
  });
});

describe('record a visit from the summary block', () => {
  const service = (panel: HTMLElement) => within(panel).getByPlaceholderText('Chọn hoặc gõ mã dịch vụ') as HTMLInputElement;
  const saveButton = (panel: HTMLElement) => within(panel).getByRole('button', { name: 'Lưu buổi làm' }) as HTMLButtonElement;
  const amount = (panel: HTMLElement) => within(panel).getByLabelText('Số tiền khách trả (đồng, không bắt buộc)') as HTMLInputElement;
  const duration = (panel: HTMLElement) => within(panel).getByLabelText('Thời lượng (phút, không bắt buộc)') as HTMLInputElement;
  const benefit = (panel: HTMLElement) => within(panel).getByLabelText(/^Dùng quyền lợi/) as HTMLSelectElement;

  it('needs a service, shows the amount with thousands separators and rejects a bad duration', async () => {
    const panel = await openVisitPanel(await openCard());
    expect(saveButton(panel).disabled).toBe(true);
    type(service(panel), 'massage-chan');
    expect(saveButton(panel).disabled).toBe(false);

    type(amount(panel), '1250000');
    expect(amount(panel).value).toBe('1.250.000');
    type(amount(panel), '1.250.0005');
    expect(amount(panel).value).toBe('12.500.005');
    type(amount(panel), '45abc');
    expect(amount(panel).value).toBe('45');

    type(duration(panel), 'một tiếng');
    expect(within(panel).getByText('Thời lượng là số phút, lớn hơn 0.')).toBeTruthy();
    expect(saveButton(panel).disabled).toBe(true);
    type(duration(panel), '0');
    expect(saveButton(panel).disabled).toBe(true);
    type(duration(panel), '90');
    expect(within(panel).queryByText('Thời lượng là số phút, lớn hơn 0.')).toBeNull();
    expect(saveButton(panel).disabled).toBe(false);

    type(within(panel).getByLabelText('Giờ làm (giờ Việt Nam)'), '');
    expect(saveButton(panel).disabled).toBe(true);
    expect(sent('POST', '/staff/visits')).toEqual([]);
  });

  it('sends the amount, technician, duration and the benefit to use', async () => {
    const panel = await openVisitPanel(await openCard());
    type(service(panel), ' massage-chan ');
    type(within(panel).getByLabelText('Giờ làm (giờ Việt Nam)'), '2026-11-07T19:30');
    type(amount(panel), '450000');
    type(within(panel).getByLabelText('Kỹ thuật viên (không bắt buộc)'), ' Hoa ');
    type(duration(panel), '60');
    expect([...benefit(panel).options].map((o) => o.textContent)).toEqual(['Không dùng quyền lợi', 'Gói 10 buổi gội dưỡng sinh: còn 4 lần, hạn 31/01/2099']);
    type(benefit(panel), 'ben_1');
    fireEvent.click(saveButton(panel));

    await waitFor(() => expect(sent('POST', '/staff/visits').length).toBe(1));
    expect(sent('POST', '/staff/visits')[0]!.body).toEqual({
      customer_id: 'cus_c',
      service_id: 'massage-chan',
      visited_at: Date.UTC(2026, 10, 7, 12, 30),
      amount_vnd: 450000,
      technician: 'Hoa',
      duration_min: 60,
      benefit_id: 'ben_1',
    });
    expect(await within(panel).findByText('Đã ghi buổi làm. Đã hẹn 2 tin gửi sau buổi làm.')).toBeTruthy();
    // the form is ready for the next visit
    expect(service(panel).value).toBe('');
    expect(amount(panel).value).toBe('');
    expect(benefit(panel).value).toBe('');
  });

  it('sends the same body as before when the optional fields are empty', async () => {
    summary = emptySummary;
    const panel = await openVisitPanel(await openCard());
    // no usable benefit: the field is not shown
    expect(within(panel).queryByLabelText(/^Dùng quyền lợi/)).toBeNull();
    type(service(panel), 'massage-chan');
    type(within(panel).getByLabelText('Giờ làm (giờ Việt Nam)'), '2026-11-07T19:30');
    fireEvent.click(saveButton(panel));
    await waitFor(() => expect(sent('POST', '/staff/visits').length).toBe(1));
    expect(sent('POST', '/staff/visits')[0]!.body).toEqual({ customer_id: 'cus_c', service_id: 'massage-chan', visited_at: Date.UTC(2026, 10, 7, 12, 30) });
  });

  it('leaves out a benefit with nothing left', async () => {
    summary = { ...fullSummary, benefits: [{ id: 'ben_9', kind: 'voucher', title: 'Voucher đã dùng hết', remaining: 0, expires_on: null }] };
    const panel = await openVisitPanel(await openCard());
    expect(within(panel).queryByLabelText(/^Dùng quyền lợi/)).toBeNull();
  });

  it('explains a benefit the server no longer accepts', async () => {
    visitWriteError = { status: 409, code: 'invalid_state', message: 'benefit not usable' };
    const panel = await openVisitPanel(await openCard());
    type(service(panel), 'massage-chan');
    type(benefit(panel), 'ben_1');
    fireEvent.click(saveButton(panel));
    expect(await within(panel).findByText('Quyền lợi đã chọn không dùng được nữa: đã hủy, hết hạn hoặc hết lượt. Bỏ chọn quyền lợi rồi ghi lại.')).toBeTruthy();
    // nothing was cleared: staff change one field and try again
    expect(service(panel).value).toBe('massage-chan');
    expect(benefit(panel).value).toBe('ben_1');
  });

  it('explains a 409 before migration 0010', async () => {
    visitWriteError = MIGRATION_409;
    const panel = await openVisitPanel(await openCard());
    type(service(panel), 'massage-chan');
    type(amount(panel), '450000');
    fireEvent.click(saveButton(panel));
    expect(await within(panel).findByText(migrationText('lưu được buổi làm'))).toBeTruthy();
    expect(amount(panel).value).toBe('450.000');
  });
});

describe('benefits of the customer', () => {
  const row = (panel: HTMLElement, title: string) => within(panel).getByText(title).closest('li') as HTMLElement;
  const addButton = (panel: HTMLElement) => within(panel).getByRole('button', { name: 'Thêm quyền lợi' }) as HTMLButtonElement;
  const patches = (id: string) => sent('PATCH', `/staff/benefits/${id}`);

  it('lists each benefit with what is left, the expiry and its state', async () => {
    const panel = await openBenefitsPanel(await openCard());
    await within(panel).findByText('Gói 10 buổi gội dưỡng sinh');
    expect(sent('GET', '/staff/benefits?customer_id=cus_c').length).toBe(1);

    const active = row(panel, 'Gói 10 buổi gội dưỡng sinh');
    expect(active.textContent).toContain('(gói nhiều buổi)');
    expect(active.textContent).toContain(`đã dùng 6/10 lần, còn 4 lần · hạn ${fmtDate(FAR)} · đang dùng được`);
    expect(within(active).getByRole('button', { name: 'Dùng 1 lần: Gói 10 buổi gội dưỡng sinh' })).toBeTruthy();
    expect(within(active).getByRole('button', { name: 'Hủy quyền lợi: Gói 10 buổi gội dưỡng sinh' })).toBeTruthy();

    const voided = row(panel, 'Voucher tặng 1 buổi massage chân');
    expect(voided.textContent).toContain('(voucher)');
    expect(voided.textContent).toContain('đã dùng 0/1 lần, còn 1 lần · không có hạn · đã hủy');
    expect(within(voided).queryByRole('button', { name: /^Dùng 1 lần/ })).toBeNull();
    expect(within(voided).getByRole('button', { name: 'Khôi phục quyền lợi: Voucher tặng 1 buổi massage chân' })).toBeTruthy();

    const expired = row(panel, 'Voucher sinh nhật');
    expect(expired.textContent).toContain(`hạn ${fmtDate(PAST)} · đã hết hạn`);
    expect(within(expired).queryByRole('button', { name: /^Dùng 1 lần/ })).toBeNull();
    expect(within(expired).getByRole('button', { name: 'Hủy quyền lợi: Voucher sinh nhật' })).toBeTruthy();
  });

  it('uses one turn of a benefit', async () => {
    const panel = await openBenefitsPanel(await openCard());
    fireEvent.click(await within(panel).findByRole('button', { name: 'Dùng 1 lần: Gói 10 buổi gội dưỡng sinh' }));
    await waitFor(() => expect(patches('ben_1').length).toBe(1));
    expect(patches('ben_1')[0]!.body).toEqual({ used_count: 7 });
    expect(await within(panel).findByText('Đã ghi một lần dùng cho quyền lợi Gói 10 buổi gội dưỡng sinh.')).toBeTruthy();
    await waitFor(() => expect(row(panel, 'Gói 10 buổi gội dưỡng sinh').textContent).toContain('đã dùng 7/10 lần, còn 3 lần'));
  });

  it('voids a benefit only after a confirmation and can restore it', async () => {
    const panel = await openBenefitsPanel(await openCard());
    const title = 'Gói 10 buổi gội dưỡng sinh';
    fireEvent.click(await within(panel).findByRole('button', { name: `Hủy quyền lợi: ${title}` }));
    let confirm = within(panel).getByRole('group', { name: `Xác nhận hủy quyền lợi ${title}` });
    expect(within(confirm).getByText(`Hủy quyền lợi ${title}? Bot sẽ không nhắc tới quyền lợi này nữa. Có thể khôi phục lại sau.`)).toBeTruthy();
    fireEvent.click(within(confirm).getByRole('button', { name: 'Giữ quyền lợi' }));
    expect(within(panel).queryByRole('group', { name: `Xác nhận hủy quyền lợi ${title}` })).toBeNull();
    expect(patches('ben_1')).toEqual([]);

    fireEvent.click(within(panel).getByRole('button', { name: `Hủy quyền lợi: ${title}` }));
    confirm = within(panel).getByRole('group', { name: `Xác nhận hủy quyền lợi ${title}` });
    fireEvent.click(within(confirm).getByRole('button', { name: 'Hủy quyền lợi này' }));
    await waitFor(() => expect(patches('ben_1').length).toBe(1));
    expect(patches('ben_1')[0]!.body).toEqual({ status: 'void' });
    expect(await within(panel).findByText(`Đã hủy quyền lợi ${title}.`)).toBeTruthy();

    fireEvent.click(await within(panel).findByRole('button', { name: `Khôi phục quyền lợi: ${title}` }));
    await waitFor(() => expect(patches('ben_1').length).toBe(2));
    expect(patches('ben_1')[1]!.body).toEqual({ status: 'active' });
    expect(await within(panel).findByText(`Đã khôi phục quyền lợi ${title}.`)).toBeTruthy();
  });

  it('validates the new benefit before it can be added', async () => {
    const panel = await openBenefitsPanel(await openCard());
    await within(panel).findByText('Gói 10 buổi gội dưỡng sinh');
    // an untouched form shows no error, and cannot be sent
    expect(panel.querySelector('.benefit-form .error')).toBeNull();
    expect(addButton(panel).disabled).toBe(true);

    type(within(panel).getByLabelText('Tổng số lần'), '5');
    expect(within(panel).getByText('Nhập tên quyền lợi, ví dụ Gói 10 buổi gội dưỡng sinh.')).toBeTruthy();
    type(within(panel).getByLabelText('Tên quyền lợi'), 'Gói 5 buổi massage chân');
    type(within(panel).getByLabelText('Tổng số lần'), 'năm');
    expect(within(panel).getByText('Tổng số lần là số nguyên lớn hơn 0.')).toBeTruthy();
    type(within(panel).getByLabelText('Tổng số lần'), '5');
    type(within(panel).getByLabelText('Số lần đã dùng (không bắt buộc)'), '6');
    expect(within(panel).getByText('Số lần đã dùng là số nguyên từ 0 đến tổng số lần.')).toBeTruthy();
    expect(addButton(panel).disabled).toBe(true);
    type(within(panel).getByLabelText('Số lần đã dùng (không bắt buộc)'), '2');
    expect(panel.querySelector('.benefit-form .error')).toBeNull();
    expect(addButton(panel).disabled).toBe(false);
    expect(sent('POST', '/staff/benefits')).toEqual([]);
  });

  it('adds a package with the uses already taken', async () => {
    const panel = await openBenefitsPanel(await openCard());
    await within(panel).findByText('Gói 10 buổi gội dưỡng sinh');
    type(within(panel).getByLabelText('Tên quyền lợi'), '  Gói 5 buổi massage chân ');
    type(within(panel).getByLabelText('Tổng số lần'), '5');
    type(within(panel).getByLabelText('Số lần đã dùng (không bắt buộc)'), '2');
    fireEvent.click(addButton(panel));
    await waitFor(() => expect(sent('POST', '/staff/benefits').length).toBe(1));
    expect(sent('POST', '/staff/benefits')[0]!.body).toEqual({ customer_id: 'cus_c', kind: 'package', title: 'Gói 5 buổi massage chân', total_count: 5, used_count: 2 });
    expect(await within(panel).findByText('Đã thêm quyền lợi.')).toBeTruthy();
    // the new row is listed and the form is empty again
    await waitFor(() => expect(row(panel, 'Gói 5 buổi massage chân').textContent).toContain('đã dùng 2/5 lần, còn 3 lần'));
    expect((within(panel).getByLabelText('Tên quyền lợi') as HTMLInputElement).value).toBe('');
  });

  it('adds a voucher for one service with an expiry at the end of the Vietnam day', async () => {
    benefits = [];
    const panel = await openBenefitsPanel(await openCard());
    expect(await within(panel).findByText('Khách này chưa có quyền lợi nào được ghi.')).toBeTruthy();
    type(within(panel).getByLabelText('Loại quyền lợi'), 'voucher');
    type(within(panel).getByLabelText('Tên quyền lợi'), 'Voucher tặng 1 buổi massage chân');
    type(within(panel).getByLabelText(/^Dịch vụ áp dụng/), 'massage-chan');
    type(within(panel).getByLabelText('Tổng số lần'), '1');
    type(within(panel).getByLabelText('Số lần đã dùng (không bắt buộc)'), '0');
    type(within(panel).getByLabelText(/^Hạn dùng/), '2099-06-30');
    fireEvent.click(addButton(panel));
    await waitFor(() => expect(sent('POST', '/staff/benefits').length).toBe(1));
    expect(sent('POST', '/staff/benefits')[0]!.body).toEqual({
      customer_id: 'cus_c',
      kind: 'voucher',
      title: 'Voucher tặng 1 buổi massage chân',
      service_id: 'massage-chan',
      total_count: 1,
      expires_at: Date.parse('2099-06-30T23:59:59+07:00'),
    });
  });

  it('explains a 409 before migration 0010 and a 404 from an older server when the list cannot load', async () => {
    benefitsListError = MIGRATION_409;
    const card = await openCard();
    let panel = await openBenefitsPanel(card);
    expect(await within(panel).findByText(migrationText('tải được danh sách quyền lợi'))).toBeTruthy();
    expect(within(panel).queryByText('Khách này chưa có quyền lợi nào được ghi.')).toBeNull();
    fireEvent.click(within(card).getByRole('button', { name: 'Đóng phần quyền lợi' }));
    expect(within(card).queryByRole('group', { name: 'Quyền lợi của khách' })).toBeNull();

    benefitsListError = OLD_SERVER_404;
    panel = await openBenefitsPanel(card);
    expect(await within(panel).findByText(oldServerText('tải được danh sách quyền lợi'))).toBeTruthy();
  });

  it('explains a 409 before migration 0010 when a benefit cannot be saved', async () => {
    benefitWriteError = MIGRATION_409;
    const panel = await openBenefitsPanel(await openCard());
    fireEvent.click(await within(panel).findByRole('button', { name: 'Dùng 1 lần: Gói 10 buổi gội dưỡng sinh' }));
    expect(await within(panel).findByText(migrationText('lưu được quyền lợi'))).toBeTruthy();
  });
});

describe('recorded visits of the customer', () => {
  const cells = (panel: HTMLElement) =>
    within(panel)
      .getAllByRole('row')
      .map((r) => [...r.querySelectorAll('th,td')].map((c) => c.textContent));

  it('lists the visits with technician, duration, amount and source', async () => {
    const panel = await openVisitsPanel(await openCard());
    await within(panel).findByRole('table');
    expect(cells(panel)).toEqual([
      ['Giờ làm', 'Dịch vụ', 'Kỹ thuật viên', 'Thời lượng', 'Số tiền', 'Nguồn'],
      [fmtTime(T_VISIT), 'Massage chân 60 phút', 'Hoa', '60 phút', '450.000đ', 'nhân viên ghi'],
      [fmtTime(T_OLD), 'chưa ghi (dùng quyền lợi)', 'chưa ghi', 'chưa ghi', 'chưa ghi', 'nhập từ file'],
    ]);
  });

  it('names a visit by the server name, unless that name is only the service id', async () => {
    visitsBody = {
      visits: [
        { id: 'vis_4', customer_id: 'cus_c', service_id: 'ext:goi-dau-thao-duoc', service_name: 'gội thảo dược', name: 'Gội thảo dược (bảng giá cũ)', visited_at: T_VISIT, source: 'import' },
        { id: 'vis_3', customer_id: 'cus_c', service_id: 'ext:x', name: 'ext:x', visited_at: T_OLD, source: 'import' },
      ],
    };
    const panel = await openVisitsPanel(await openCard());
    await within(panel).findByRole('table');
    expect(cells(panel).map((row) => row[1])).toEqual(['Dịch vụ', 'Gội thảo dược (bảng giá cũ)', 'ext:x']);
  });

  it('reads the rows from an items wrapper too, and has a calm empty state', async () => {
    visitsBody = { items: [visitRows[0]!] };
    const card = await openCard();
    let panel = await openVisitsPanel(card);
    await within(panel).findByRole('table');
    expect(cells(panel).length).toBe(2);
    fireEvent.click(within(card).getByRole('button', { name: 'Đóng danh sách buổi làm' }));

    visitsBody = {};
    panel = await openVisitsPanel(card);
    expect(await within(panel).findByText('Chưa có buổi làm nào được ghi cho khách này.')).toBeTruthy();
    expect(within(panel).queryByRole('table')).toBeNull();
  });

  it('explains a 404 from an older server and a 409 before migration 0010', async () => {
    visitsListError = OLD_SERVER_404;
    const card = await openCard();
    let panel = await openVisitsPanel(card);
    expect(await within(panel).findByText(oldServerText('tải được danh sách buổi làm'))).toBeTruthy();
    fireEvent.click(within(card).getByRole('button', { name: 'Đóng danh sách buổi làm' }));

    visitsListError = MIGRATION_409;
    panel = await openVisitsPanel(card);
    expect(await within(panel).findByText(migrationText('tải được danh sách buổi làm'))).toBeTruthy();
  });

  it('keeps one panel open at a time', async () => {
    const card = await openCard();
    await openVisitsPanel(card);
    await openBenefitsPanel(card);
    expect(within(card).queryByRole('group', { name: 'Các buổi làm đã ghi' })).toBeNull();
    expect(within(card).getByRole('button', { name: 'Đóng phần quyền lợi' }).getAttribute('aria-expanded')).toBe('true');
    expect(within(card).getByRole('button', { name: 'Xem các buổi làm đã ghi' }).getAttribute('aria-expanded')).toBe('false');
  });
});

describe('visit tab', () => {
  async function openTab(): Promise<HTMLElement> {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ghi nhận buổi làm' }));
    const page = (await screen.findByRole('heading', { name: 'Ghi nhận buổi làm' })).closest('.page') as HTMLElement;
    await within(page).findByRole('option', { name: 'Thu Lê' });
    type(within(page).getByLabelText('Khách'), 'cus_c');
    return page;
  }
  const fill = (page: HTMLElement) => {
    type(within(page).getByPlaceholderText('Chọn hoặc gõ mã dịch vụ'), 'massage-chan');
    type(within(page).getByLabelText('Giờ làm (giờ Việt Nam)'), '2026-11-07T19:30');
  };
  const submit = (page: HTMLElement) => within(page).getByRole('button', { name: 'Ghi nhận buổi làm' }) as HTMLButtonElement;

  it('offers the usable benefits of the chosen customer and sends the optional fields', async () => {
    const page = await openTab();
    const benefit = (await within(page).findByLabelText(/^Dùng quyền lợi/)) as HTMLSelectElement;
    // the void and the expired benefit are not offered
    expect([...benefit.options].map((o) => o.textContent)).toEqual([
      'Không dùng quyền lợi',
      `Gói 10 buổi gội dưỡng sinh (gói nhiều buổi): còn 4 lần, hạn ${fmtDate(FAR)}`,
    ]);
    fill(page);
    const amount = within(page).getByLabelText('Số tiền khách trả (đồng, không bắt buộc)') as HTMLInputElement;
    type(amount, '1250000');
    expect(amount.value).toBe('1.250.000');
    type(within(page).getByLabelText('Kỹ thuật viên (không bắt buộc)'), 'Hoa');
    type(within(page).getByLabelText('Thời lượng (phút, không bắt buộc)'), '90');
    type(benefit, 'ben_1');
    fireEvent.click(submit(page));

    await waitFor(() => expect(sent('POST', '/staff/visits').length).toBe(1));
    expect(sent('POST', '/staff/visits')[0]!.body).toEqual({
      customer_id: 'cus_c',
      service_id: 'massage-chan',
      visited_at: Date.UTC(2026, 10, 7, 12, 30),
      amount_vnd: 1250000,
      technician: 'Hoa',
      duration_min: 90,
      benefit_id: 'ben_1',
    });
    expect(await within(page).findByText('Đã ghi nhận buổi làm vis_new.')).toBeTruthy();
    expect(amount.value).toBe('');
  });

  it('works as before against an older server without benefits', async () => {
    benefitsListError = OLD_SERVER_404;
    const page = await openTab();
    await waitFor(() => expect(sent('GET', '/staff/benefits?customer_id=cus_c').length).toBe(1));
    fill(page);
    expect(within(page).queryByLabelText(/^Dùng quyền lợi/)).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.click(submit(page));
    await waitFor(() => expect(sent('POST', '/staff/visits').length).toBe(1));
    expect(sent('POST', '/staff/visits')[0]!.body).toEqual({ customer_id: 'cus_c', service_id: 'massage-chan', visited_at: Date.UTC(2026, 10, 7, 12, 30) });
  });

  it('blocks a technician name that is too long', async () => {
    const page = await openTab();
    fill(page);
    type(within(page).getByLabelText('Kỹ thuật viên (không bắt buộc)'), 'H'.repeat(61));
    expect(within(page).getByText('Tên kỹ thuật viên viết trên một dòng, tối đa 60 ký tự.')).toBeTruthy();
    expect(submit(page).disabled).toBe(true);
  });
});

describe('money and date helpers', () => {
  it('formats an amount in VND with thousands separators', () => {
    expect(fmtVnd(450000)).toBe('450.000đ');
    expect(fmtVnd(2950000)).toBe('2.950.000đ');
    expect(fmtVnd(999)).toBe('999đ');
    expect(fmtVnd(1000)).toBe('1.000đ');
    expect(fmtVnd(0)).toBe('0đ');
    expect(fmtVnd(1234.6)).toBe('1.235đ');
    expect(fmtVnd(-450000)).toBe('-450.000đ');
    expect(fmtVnd(null)).toBe('');
    expect(fmtVnd(undefined)).toBe('');
    expect(fmtVnd(Number.NaN)).toBe('');
  });

  it('groups the digits of a money field while staff type', () => {
    expect(vndInputText('1250000')).toBe('1.250.000');
    expect(vndInputText('450.000')).toBe('450.000');
    expect(vndInputText('450.0001')).toBe('4.500.001');
    expect(vndInputText('450 000 đ')).toBe('450.000');
    expect(vndInputText('0450000')).toBe('450.000');
    expect(vndInputText('000')).toBe('0');
    expect(vndInputText('999')).toBe('999');
    expect(vndInputText('abc')).toBe('');
    expect(vndInputText('')).toBe('');
  });

  it('reads a money field back as a whole number of VND', () => {
    expect(parseVnd('450.000')).toBe(450000);
    expect(parseVnd('1.250.000')).toBe(1250000);
    expect(parseVnd('0')).toBe(0);
    expect(parseVnd('')).toBeNull();
    expect(parseVnd('abc')).toBeNull();
    expect(parseVnd('99.999.999.999.999.999.999')).toBeNull();
    // what the field shows is what is sent
    expect(parseVnd(vndInputText('2950000'))).toBe(2950000);
  });

  it('formats a calendar day and the end of a Vietnam day', () => {
    expect(fmtYmd('2026-10-30')).toBe('30/10/2026');
    expect(fmtYmd('30/10/2026')).toBe('30/10/2026');
    expect(fmtYmd(null)).toBe('');
    expect(fmtYmd(undefined)).toBe('');
    expect(vnDateEndMs('2027-01-31')).toBe(Date.UTC(2027, 0, 31, 16, 59, 59));
    expect(Number.isNaN(vnDateEndMs('31/01/2027'))).toBe(true);
    expect(Number.isNaN(vnDateEndMs(''))).toBe(true);
  });

  it('normalizes a phone number to the digits the server stores', () => {
    expect(normalizePhone('0901234567')).toBe('0901234567');
    expect(normalizePhone('+84 90 123 4567')).toBe('0901234567');
    expect(normalizePhone('090.123.4567')).toBe('0901234567');
    expect(normalizePhone('(090) 123-4567')).toBe('0901234567');
    expect(normalizePhone('12345')).toBeNull();
    expect(normalizePhone('090123456789')).toBeNull();
    expect(normalizePhone('số của chị')).toBeNull();
  });
});

describe('summary helpers', () => {
  it('builds the status reason from the numbers', () => {
    expect(customerStatusReason({})).toBe('');
    expect(customerStatusReason({ status: 'first_inquiry' })).toBe('Chưa có buổi làm nào được ghi.');
    expect(customerStatusReason({ status: 'first_visit_done', days_since_last_visit: 5, usual_gap_days: 30, absent_after_days: 60 })).toBe(
      'Khách mới đến một lần. Lần đến gần nhất cách đây 5 ngày, chưa quá mốc 60 ngày (thường 30 ngày quay lại một lần).',
    );
    expect(customerStatusReason({ status: 'returning', visits_total: 7, days_since_last_visit: 13, usual_gap_days: 21, absent_after_days: 42 })).toBe(
      'Khách đã đến 7 lần. Lần đến gần nhất cách đây 13 ngày, chưa quá mốc 42 ngày (thường 21 ngày quay lại một lần).',
    );
    expect(customerStatusReason({ status: 'long_absent', days_since_last_visit: 60, usual_gap_days: 21, absent_after_days: 42 })).toBe(
      'Lần đến gần nhất cách đây 60 ngày, quá mốc 42 ngày (thường 21 ngày quay lại một lần).',
    );
    // missing numbers leave their part out instead of printing "undefined"
    expect(customerStatusReason({ status: 'long_absent' })).toBe('Chưa rõ lần đến gần nhất.');
    expect(customerStatusReason({ status: 'returning', days_since_last_visit: 3 })).toBe('Lần đến gần nhất cách đây 3 ngày.');
  });

  it('knows whether a visit is recorded', () => {
    expect(hasVisitData({})).toBe(false);
    expect(hasVisitData({ visits_total: 0, last_visit: null })).toBe(false);
    expect(hasVisitData({ visits_total: 1 })).toBe(true);
    expect(hasVisitData({ last_visit: { visited_at: T_VISIT } })).toBe(true);
  });

  it('words the last visit and the window', () => {
    expect(lastVisitText(fullSummary.last_visit!)).toBe('Massage chân 60 phút · 30/10/2026 lúc 14:30 · kỹ thuật viên Hoa · 450.000đ');
    expect(
      lastVisitText({
        visited_at: T_VISIT,
        date: '2026-10-30',
        services: [
          { service_id: 'massage-chan', name: 'Massage chân 60 phút' },
          { service_id: null, name: 'Gội đầu thư giãn' },
        ],
        amount_vnd: 0,
      }),
    ).toBe('Massage chân 60 phút, Gội đầu thư giãn · 30/10/2026 · chưa ghi kỹ thuật viên · 0đ');
    expect(windowText({ days: 183, from_date: '2026-05-13', visits: 3 })).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 3 buổi');
    expect(windowText({ days: 90 })).toBe('90 ngày gần nhất');
  });

  it('words a benefit of the summary and the state of a stored benefit', () => {
    expect(summaryBenefitText({ title: 'Gói 10 buổi gội dưỡng sinh', remaining: 4, expires_on: '2027-01-31' })).toBe('Gói 10 buổi gội dưỡng sinh: còn 4 lần, hạn 31/01/2027');
    expect(summaryBenefitText({ title: 'Voucher sinh nhật', remaining: 1, expires_on: null })).toBe('Voucher sinh nhật: còn 1 lần, không có hạn');
    expect(benefitStateText(benPackage, T)).toBe('đang dùng được');
    expect(benefitStateText(benVoid, T)).toBe('đã hủy');
    expect(benefitStateText(benExpired, T)).toBe('đã hết hạn');
    expect(benefitStateText({ ...benPackage, used_count: 10, remaining: 0 }, T)).toBe('đã dùng hết');
    // the expiry is the last second of the day: still usable one second before it
    expect(benefitStateText({ ...benPackage, expires_at: T }, T - 1000)).toBe('đang dùng được');
    expect(benefitStateText({ ...benPackage, expires_at: T }, T + 1000)).toBe('đã hết hạn');
  });

  it('offers a visit only the benefits that can be used now', () => {
    const usedUp: CustomerBenefit = { ...benPackage, id: 'ben_4', used_count: 10, remaining: 0 };
    const noExpiry: CustomerBenefit = { id: 'ben_5', customer_id: 'cus_c', kind: 'voucher', title: 'Voucher sinh nhật', total_count: 2, used_count: 1, status: 'active' };
    expect(usableBenefitChoices([benPackage, benVoid, benExpired, usedUp, noExpiry], T)).toEqual([
      { id: 'ben_1', label: `Gói 10 buổi gội dưỡng sinh (gói nhiều buổi): còn 4 lần, hạn ${fmtDate(FAR)}` },
      { id: 'ben_5', label: 'Voucher sinh nhật (voucher): còn 1 lần' },
    ]);
    expect(usableBenefitChoices([], T)).toEqual([]);
  });
});

describe('form helpers', () => {
  it('checks the optional fields of a visit', () => {
    expect(visitExtrasProblem(EMPTY_VISIT_EXTRAS)).toBeNull();
    expect(visitExtrasProblem({ amount: '450.000', technician: 'Hoa', duration: '60', benefitId: 'ben_1' })).toBeNull();
    expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, amount: '99.999.999.999.999.999.999' })).toBe('Số tiền quá lớn hoặc không phải số.');
    expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, technician: 'H'.repeat(60) })).toBeNull();
    expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, technician: 'H'.repeat(61) })).toBe('Tên kỹ thuật viên viết trên một dòng, tối đa 60 ký tự.');
    expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, technician: 'Hoa\nLan' })).toBe('Tên kỹ thuật viên viết trên một dòng, tối đa 60 ký tự.');
    for (const duration of ['0', '1441', '1.5', '-30', 'một tiếng']) {
      expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, duration })).toBe('Thời lượng là số phút, lớn hơn 0.');
    }
    expect(visitExtrasProblem({ ...EMPTY_VISIT_EXTRAS, duration: '1440' })).toBeNull();
  });

  it('sends only the optional fields staff filled in', () => {
    expect(visitExtrasPayload(EMPTY_VISIT_EXTRAS)).toEqual({});
    expect(visitExtrasPayload({ amount: '450.000', technician: '  Hoa ', duration: ' 90 ', benefitId: 'ben_1' })).toEqual({
      amount_vnd: 450000,
      technician: 'Hoa',
      duration_min: 90,
      benefit_id: 'ben_1',
    });
    expect(visitExtrasPayload({ ...EMPTY_VISIT_EXTRAS, amount: '0' })).toEqual({ amount_vnd: 0 });
    expect(visitExtrasPayload({ ...EMPTY_VISIT_EXTRAS, technician: '   ' })).toEqual({});
  });

  it('checks the new benefit in the order staff fill it in', () => {
    const ok = { ...EMPTY_BENEFIT_FORM, title: 'Gói 10 buổi gội dưỡng sinh', total: '10' };
    expect(benefitFormProblem(EMPTY_BENEFIT_FORM)).toBe('Nhập tên quyền lợi, ví dụ Gói 10 buổi gội dưỡng sinh.');
    expect(benefitFormProblem(ok)).toBeNull();
    expect(benefitFormProblem({ ...ok, title: 'G'.repeat(121) })).toBe('Tên quyền lợi viết trên một dòng, tối đa 120 ký tự.');
    expect(benefitFormProblem({ ...ok, title: 'Gói 10 buổi\ngội dưỡng sinh' })).toBe('Tên quyền lợi viết trên một dòng, tối đa 120 ký tự.');
    for (const total of ['', '0', '2.5', '-1', 'mười']) {
      expect(benefitFormProblem({ ...ok, total })).toBe('Tổng số lần là số nguyên lớn hơn 0.');
    }
    expect(benefitFormProblem({ ...ok, used: '10' })).toBeNull();
    expect(benefitFormProblem({ ...ok, used: '11' })).toBe('Số lần đã dùng là số nguyên từ 0 đến tổng số lần.');
    expect(benefitFormProblem({ ...ok, used: 'hai' })).toBe('Số lần đã dùng là số nguyên từ 0 đến tổng số lần.');
    expect(benefitFormProblem({ ...ok, expires: '2099-01-31' })).toBeNull();
    expect(benefitFormProblem({ ...ok, expires: '31/01/2099' })).toBe('Hạn dùng không phải ngày hợp lệ.');
  });

  it('builds the body of a new benefit from the filled fields only', () => {
    expect(benefitCreateBody('cus_c', { ...EMPTY_BENEFIT_FORM, title: ' Gói 10 buổi gội dưỡng sinh ', total: ' 10 ' })).toEqual({
      customer_id: 'cus_c',
      kind: 'package',
      title: 'Gói 10 buổi gội dưỡng sinh',
      total_count: 10,
    });
    expect(benefitCreateBody('cus_c', { kind: 'voucher', title: 'Voucher sinh nhật', serviceId: ' massage-chan ', total: '2', used: '1', expires: '2099-01-31' })).toEqual({
      customer_id: 'cus_c',
      kind: 'voucher',
      title: 'Voucher sinh nhật',
      service_id: 'massage-chan',
      total_count: 2,
      used_count: 1,
      expires_at: FAR,
    });
    // a typed 0 is the server default and is left out
    expect(benefitCreateBody('cus_c', { ...EMPTY_BENEFIT_FORM, title: 'Voucher sinh nhật', total: '1', used: '0' })).toEqual({
      customer_id: 'cus_c',
      kind: 'package',
      title: 'Voucher sinh nhật',
      total_count: 1,
    });
  });
});
