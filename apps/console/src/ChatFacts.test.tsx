// Facts guessed from old chat in the customer summary (chat-facts contract, section 15.13): the markers on the figures,
// the section "Suy ra từ tin nhắn cũ", confirm and dismiss, the masked phone suggestion, the 404 and 409 sentences, and
// a summary without the `chat` field rendering as before apart from the no-visit sentence. Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatBenefitView, ChatFacts, ChatVisitView, ConversationDetail, ConversationSummary, CustomerSummary } from './api';
import { App } from './App';
import { NO_VISIT_DATA_CHAT_TEXT, fmtDate, fmtTime, maskPhone } from './labels';
import {
  CHAT_VISIBLE_VISITS,
  RECORDED_DAY_TEXT,
  RECORDED_TITLE_TEXT,
  benefitConfirmBody,
  benefitConfirmInitial,
  benefitConfirmProblem,
  benefitConfirmUsed,
  chatBenefitText,
  chatDecisionErrorText,
  chatMarkers,
  chatVisitText,
  visitConfirmBody,
  visitConfirmInitial,
  visitConfirmProblem,
} from './screens/ChatFacts';
import { ApiError } from './api';
import { benefitFormProblem, EMPTY_BENEFIT_FORM } from './screens/CustomerSummaryCard';

const T = Date.UTC(2026, 10, 12, 3, 0);
const vn = (ymd: string, hm: string) => Date.parse(`${ymd}T${hm}:00+07:00`);
const ZID = 'p:9100666';
const FACTS_URL = `/staff/chat-facts/${encodeURIComponent(ZID)}`;
const DECIDED_AT = vn('2026-11-10', '10:00');
const GENERATED_AT = vn('2026-11-11', '09:00');
const STATED_AT = vn('2026-10-17', '16:00');

const conv: ConversationSummary = {
  id: 'cnv_f',
  customer: { id: 'cus_f', zalo_user_id: ZID, display_name: 'Hạnh Võ', phone: null, minor_flag: null, last_user_interaction_at: T },
  bot_state: 'bot_active',
  mode_override: null,
  effective_mode: 'approve_each',
  needs_attention: false,
  takeover_by: null,
  takeover_until: null,
  last_message_at: T,
  last_message_preview: 'em hỏi lịch',
  pending_drafts: 0,
  open_handoffs: 0,
};

// The summary used to capture the card before section 15 (same values, no `chat` field).
const plainSummary: CustomerSummary = {
  role: 'customer',
  role_source: 'zalo_label',
  name: 'Hạnh',
  address_term: 'chị',
  phone: '0912345678',
  status: 'returning',
  visits_total: 5,
  last_visit: {
    visited_at: vn('2026-10-30', '14:30'),
    date: '2026-10-30',
    time: '14:30',
    services: [{ service_id: 'massage-chan', name: 'Massage chân' }],
    technician: 'Lan',
    amount_vnd: 350000,
  },
  days_since_last_visit: 13,
  usual_gap_days: 20,
  gap_basis: 'own',
  absent_after_days: 40,
  lifetime_spend_vnd: 1400000,
  lifetime_spend_visits: 4,
  window: { days: 183, from_date: '2026-05-13', visits: 3, spend_vnd: 1050000, avg_spend_vnd: 350000, services: [{ service_id: 'massage-chan', name: 'Massage chân', count: 3 }] },
  benefits: [{ id: 'ben_g', kind: 'package', title: 'Gói 10 buổi massage chân', remaining: 3, expires_on: '2099-01-31' }],
};
const plainEmpty: CustomerSummary = { role: null, role_source: null, name: null, address_term: null, phone: null, status: 'first_inquiry', visits_total: 0, benefits: [] };

// Text of the card captured from the component before section 15 (2026-11-12), for the two summaries above. The one
// change since: the sentence of a summary without visits names the chat analyzer (NO_VISIT_DATA_CHAT_TEXT), because the
// server leaves `chat` out for a contact without chat facts and the console ships with that server.
const BEFORE_FULL =
  'Tóm tắt khách hàngTênHạnhCách xưng hôchịSố điện thoại0912345678Sửa số điện thoạiTrạng tháikhách quay lại Khách đã đến 5 lần. Lần đến gần nhất cách đây 13 ngày, chưa quá mốc 40 ngày (thường 20 ngày quay lại một lần).Tổng số lần đã đến5 lầnDịch vụ cuối cùngMassage chân · 30/10/2026 lúc 14:30 · kỹ thuật viên Lan · 350.000đTổng số tiền đã dùng1.400.000đ (tính trên 4 buổi có ghi số tiền)Đã bao lâu chưa đến13 ngàyThường cách bao lâu quay lại20 ngày (tính từ các lần đến của chính khách)Khoảng thời gian tính183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 3 buổiDịch vụ thường dùngMassage chân (3 lần)Mức chi mỗi lầntrung bình 350.000đTổng chi trong khoảng1.050.000đQuyền lợi chưa dùngGói 10 buổi massage chân: còn 3 lần, hạn 31/01/2099Dịch vụ thường dùng, mức chi mỗi lần và tổng chi trong khoảng chỉ tính các buổi nằm trong khoảng thời gian tính.Ghi buổi làm cho khách nàyThêm hoặc dùng quyền lợiXem các buổi làm đã ghi';
const BEFORE_EMPTY =
  'Tóm tắt khách hàngTênchưa có tên để gọiCách xưng hôchưa xác định (bot gọi anh/chị)Số điện thoạichưa cóSửa số điện thoạiTrạng tháimới hỏi, chưa đến lần nào Chưa có buổi làm nào được ghi.Tổng số lần đã đến0 lầnQuyền lợi chưa dùngkhông có' +
  'Chưa có buổi làm nào được ghi cho khách này. Số lần đến, số tiền và kỹ thuật viên có khi nhân viên ghi nhận buổi làm, nhập từ file, hoặc khi công cụ phân tích tin nhắn cũ tìm thấy lần đến chắc hoặc khá chắc.' +
  'Ghi buổi làm cho khách nàyThêm hoặc dùng quyền lợiXem các buổi làm đã ghi';

// A summary of section 15.12: two guesses counted (17/10 high with a paid amount, 05/09 medium with a quote).
const chatSummary: CustomerSummary = {
  ...plainSummary,
  phone: null,
  visits_total: 5,
  last_visit: {
    visited_at: vn('2026-10-17', '15:00'),
    date: '2026-10-17',
    time: '15:00',
    services: [{ service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn' }],
    technician: 'Lan',
    amount_vnd: 350000,
    from_chat: true,
  },
  days_since_last_visit: 26,
  window: { days: 183, from_date: '2026-05-13', visits: 4, spend_vnd: 1050000, avg_spend_vnd: 350000, services: [{ service_id: 'massage-chan', name: 'Massage chân', count: 3 }] },
  chat: {
    visits_counted: 2,
    visits_low: 1,
    upcoming_next: { date: '2026-11-20', time: '15:30' },
    benefits_active: 2,
    phone_suggestion: true,
    analyzer_version: 'visits-rules-v1',
    generated_at: GENERATED_AT,
  },
};

const visit = (v: Partial<ChatVisitView> & Pick<ChatVisitView, 'id' | 'local_date'>): ChatVisitView => ({
  kind: 'visit',
  visited_at: vn(v.local_date!, '12:00'),
  time_known: false,
  services: [],
  amount_vnd: null,
  amount_source: null,
  technician: null,
  confidence: 'high',
  fact_source: 'chat_rules',
  state: 'active',
  ...v,
});

function baseFacts(): ChatFacts {
  return {
    analyzer_version: 'visits-rules-v1',
    generated_at: GENERATED_AT,
    imported_at: GENERATED_AT + 60_000,
    model_pass: { ran: false, reason: 'disabled' },
    phone_suggestion: '0987654321',
    visits: [
      visit({ id: 'chv_3', local_date: '2026-08-20', visited_at: vn('2026-08-20', '10:00'), time_known: true, confidence: 'low' }),
      visit({
        id: 'chv_1',
        local_date: '2026-10-17',
        visited_at: vn('2026-10-17', '15:00'),
        time_known: true,
        services: [{ service_id: 'goi-dau-thu-gian', service_name: 'gội đầu', name: 'Gội đầu thư giãn', basis: 'booking' }],
        amount_vnd: 350000,
        amount_source: 'paid',
        technician: 'Lan',
        confidence: 'high',
      }),
      visit({
        id: 'chv_2',
        local_date: '2026-09-05',
        services: [{ service_id: null, service_name: 'massage', basis: 'visit_day' }],
        amount_vnd: 250000,
        amount_source: 'quoted',
        confidence: 'medium',
      }),
      visit({ id: 'chv_4', local_date: '2026-07-01', confidence: 'high', state: 'dismissed', decided_by: 'lan', decided_at: DECIDED_AT }),
      visit({ id: 'chv_5', local_date: '2026-06-10', confidence: 'medium', state: 'confirmed', confirmed_visit_id: 'vis_9', decided_by: 'lan', decided_at: DECIDED_AT }),
    ],
    upcoming: [
      visit({
        id: 'chv_6',
        kind: 'upcoming',
        local_date: '2026-11-20',
        visited_at: vn('2026-11-20', '15:30'),
        time_known: true,
        services: [{ service_id: 'massage-chan', name: 'Massage chân', basis: 'booking' }],
        confidence: null,
      }),
    ],
    benefits: [
      { id: 'chb_1', kind: 'package', title: 'Gói 10 buổi gội đầu', service_id: 'goi-dau-thu-gian', total_count: 10, remaining: 7, stated_by: 'owner', confidence: 'high', stated_at: STATED_AT, state: 'active' },
      { id: 'chb_2', kind: 'voucher', title: 'Voucher sinh nhật', service_id: null, total_count: null, remaining: 1, stated_by: 'contact', confidence: 'medium', stated_at: STATED_AT, state: 'active' },
    ],
  };
}

type Call = { method: string; url: string; body: unknown };
type StubError = { status: number; code: string; message: string; details?: Record<string, unknown> };
let calls: Call[] = [];
let customer = conv.customer;
let summary: CustomerSummary | undefined = chatSummary;
let facts: ChatFacts | null = baseFacts();
let factsError: StubError | null = null;
let decisionError: StubError | null = null;

const MIGRATION_0011: StubError = { status: 409, code: 'invalid_state', message: 'apply migration 0011_chat_facts.sql' };
const OLD_SERVER_404: StubError = { status: 404, code: 'not_found', message: 'nope' };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}
function fail(e: StubError) {
  return json({ error: { code: e.code, message: e.message, ...(e.details ? { details: e.details } : {}) } }, e.status);
}

/** Marks one row decided in the stored facts, like the server; null when the id is unknown. */
function decide(list: 'visits' | 'benefits', id: string, state: 'confirmed' | 'dismissed'): ChatVisitView | ChatBenefitView | null {
  if (!facts) return null;
  const stamp = { state, decided_by: 'lan', decided_at: T };
  if (list === 'visits') {
    const row = [...(facts.visits ?? []), ...(facts.upcoming ?? [])].find((v) => v.id === id);
    if (!row) return null;
    const mark = (rows: ChatVisitView[] | undefined) => (rows ?? []).map((v) => (v.id === id ? { ...v, ...stamp } : v));
    facts = { ...facts, visits: mark(facts.visits), upcoming: mark(facts.upcoming) };
    return { ...row, ...stamp };
  }
  const row = (facts.benefits ?? []).find((b) => b.id === id);
  if (!row) return null;
  facts = { ...facts, benefits: (facts.benefits ?? []).map((b) => (b.id === id ? { ...b, ...stamp } : b)) };
  return { ...row, ...stamp };
}

beforeEach(() => {
  calls = [];
  customer = conv.customer;
  summary = chatSummary;
  facts = baseFacts();
  factsError = null;
  decisionError = null;
  localStorage.setItem('thomhouse.console.config', JSON.stringify({ baseUrl: '', staffToken: 'test-token', staffId: 'lan' }));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined;
      calls.push({ method, url, body });
      if (url === '/health') return json({ ok: true, env: 'dev', zalo_mode: 'personal' });
      if (url.startsWith('/staff/handoffs') || url.startsWith('/staff/booking-requests')) return json({ items: [], next_cursor: null });
      const c = { ...conv, customer };
      if (url.startsWith('/staff/conversations?')) return json({ items: [c], next_cursor: null });
      if (url === `/staff/conversations/${conv.id}`) {
        const d: ConversationDetail = {
          conversation: { ...c, session_id: null, session_turns: 0, catalog_version: 'cv_seed' },
          messages: [],
          drafts: [],
          handoffs: [],
          booking_requests: [],
          consents: [],
          ...(summary === undefined ? {} : { customer_summary: summary }),
        };
        return json(d);
      }
      if (url.startsWith('/staff/chat-facts/') && method === 'GET') {
        if (url !== FACTS_URL) return fail(OLD_SERVER_404);
        return factsError ? fail(factsError) : json({ facts });
      }
      let m = /^\/staff\/chat-facts\/(visits|benefits)\/([^/]+)\/(confirm|dismiss)$/.exec(url);
      if (m && method === 'POST') {
        if (decisionError) return fail(decisionError);
        const [, list, id, action] = m as unknown as [string, 'visits' | 'benefits', string, 'confirm' | 'dismiss'];
        const row = decide(list, id!, action === 'confirm' ? 'confirmed' : 'dismissed');
        if (!row) return fail(OLD_SERVER_404);
        if (list === 'visits') return json(action === 'confirm' ? { visit: { id: 'vis_new', customer_id: 'cus_f', visited_at: T }, chat_visit: row } : { chat_visit: row });
        return json(action === 'confirm' ? { benefit: { id: 'ben_new' }, chat_benefit: row } : { chat_benefit: row });
      }
      m = /^\/staff\/chat-facts\/([^/]+)\/phone\/(accept|dismiss)$/.exec(url);
      if (m && method === 'POST') {
        if (decisionError) return fail(decisionError);
        if (m[1] !== encodeURIComponent(ZID)) return fail(OLD_SERVER_404);
        if (m[2] === 'accept' && facts?.phone_suggestion) customer = { ...customer, phone: facts.phone_suggestion };
        if (facts) facts = { ...facts, phone_suggestion: null };
        return json({ ok: true });
      }
      return fail(OLD_SERVER_404);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function openCard(): Promise<HTMLElement> {
  render(<App />);
  fireEvent.click(await screen.findByText('Hạnh Võ'));
  return screen.findByRole('region', { name: 'Tóm tắt khách hàng' });
}

async function openSection(): Promise<HTMLElement> {
  const card = await openCard();
  const section = await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
  await within(section).findByRole('group', { name: 'Lần đến suy ra từ tin nhắn' });
  return section;
}

function fact(card: HTMLElement, term: string): string | null {
  const dt = [...card.querySelectorAll('dt')].find((el) => el.textContent === term);
  return dt ? (dt.nextElementSibling?.textContent ?? '') : null;
}

const sent = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url);
const factsLoads = () => sent('GET', FACTS_URL).length;
const type = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });
const rowOf = (section: HTMLElement, text: string) => within(section).getByText(text).closest('li') as HTMLElement;
const VISIT_1 = '17/10/2026 lúc 15:00 · Gội đầu thư giãn · 350.000đ (đã trả) · kỹ thuật viên Lan · chắc';
const VISIT_2 = '05/09/2026, chưa rõ giờ · massage · 250.000đ (báo giá) · chưa rõ kỹ thuật viên · khá chắc';
const VISIT_3 = '20/08/2026 lúc 10:00 · chưa rõ dịch vụ · chưa rõ số tiền · chưa rõ kỹ thuật viên · chưa chắc, không tính vào số lần đến';
const UPCOMING = '20/11/2026 lúc 15:30 · Massage chân · chưa rõ số tiền · chưa rõ kỹ thuật viên';
const BENEFIT_1 = `Gói 10 buổi gội đầu (gói nhiều buổi) · tổng 10 lần, còn 7 lần · theo tin studio nhắn ngày ${fmtDate(STATED_AT)} · chắc`;
const BENEFIT_2 = `Voucher sinh nhật (voucher) · còn 1 lần, chưa rõ tổng số lần · theo tin khách nhắn ngày ${fmtDate(STATED_AT)} · khá chắc`;

describe('a summary without the chat field', () => {
  it('renders as before, with the no-visit sentence that names the chat analyzer, and asks nothing about old chat', async () => {
    summary = plainSummary;
    let card = await openCard();
    expect(card.textContent).toBe(BEFORE_FULL);
    expect(card.querySelector('.chat-marker, .chat-facts')).toBeNull();
    cleanup();

    summary = plainEmpty;
    card = await openCard();
    expect(card.textContent).toBe(BEFORE_EMPTY);
    // the server leaves `chat` out for a contact without chat facts: the sentence must not say old chat never counts
    expect(within(card).getByText(NO_VISIT_DATA_CHAT_TEXT)).toBeTruthy();
    expect(card.textContent).not.toContain('tin nhắn cũ không được tính là buổi làm');
    // a few polls later there is still no call for chat facts
    await waitFor(() => expect(sent('GET', `/staff/conversations/${conv.id}`).length).toBeGreaterThan(1), { timeout: 4000 });
    expect(calls.some((c) => c.url.startsWith('/staff/chat-facts'))).toBe(false);
  }, 15_000);

  it('does not ask for a contact whose id is not p: and digits', async () => {
    customer = { ...conv.customer, zalo_user_id: 'p:ab_12' };
    await openCard();
    await waitFor(() => expect(sent('GET', `/staff/conversations/${conv.id}`).length).toBeGreaterThan(0));
    expect(calls.some((c) => c.url.startsWith('/staff/chat-facts'))).toBe(false);
  });

  it('stays unchanged when the server has no facts for this contact', async () => {
    summary = { ...plainSummary, chat: null };
    facts = null;
    const card = await openCard();
    await waitFor(() => expect(factsLoads()).toBe(1));
    expect(card.textContent).toBe(BEFORE_FULL);
    expect(within(card).queryByRole('region', { name: 'Suy ra từ tin nhắn cũ' })).toBeNull();
  });

  it('words "no visit" for a server that counts guesses', async () => {
    summary = { ...plainEmpty, chat: null };
    facts = null;
    const card = await openCard();
    expect(within(card).getByText(NO_VISIT_DATA_CHAT_TEXT)).toBeTruthy();
    expect(card.textContent).not.toContain('tin nhắn cũ không được tính là buổi làm');
  });
});

describe('markers on the figures of the summary', () => {
  it('marks every figure that includes guesses, and the last visit', async () => {
    const card = await openCard();
    await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    expect(fact(card, 'Tổng số lần đã đến')).toBe('5 lần · gồm 2 lần suy ra từ tin nhắn');
    expect(fact(card, 'Dịch vụ cuối cùng')).toBe('Gội đầu thư giãn · 17/10/2026 lúc 15:00 · kỹ thuật viên Lan · 350.000đ · suy ra từ tin nhắn');
    expect(fact(card, 'Đã bao lâu chưa đến')).toBe('26 ngày · tính từ lần đến suy ra từ tin nhắn');
    expect(fact(card, 'Thường cách bao lâu quay lại')).toBe('20 ngày (tính từ các lần đến của chính khách) · gồm 2 lần suy ra từ tin nhắn');
    // these three need the list of guesses, so they appear once it is loaded
    expect(fact(card, 'Khoảng thời gian tính')).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 4 buổi · gồm 2 lần suy ra từ tin nhắn');
    // only the 17/10 guess has a paid amount; the 05/09 amount is a quote and is not spend
    expect(fact(card, 'Tổng số tiền đã dùng')).toBe('1.400.000đ (tính trên 4 buổi có ghi số tiền) · gồm 1 lần suy ra từ tin nhắn');
    expect(fact(card, 'Mức chi mỗi lần')).toBe('trung bình 350.000đ · gồm 1 lần suy ra từ tin nhắn');
    expect(fact(card, 'Tổng chi trong khoảng')).toBe('1.050.000đ · gồm 1 lần suy ra từ tin nhắn');
    // the usual services and the status line count the guesses too, so they say so
    expect(fact(card, 'Dịch vụ thường dùng')).toBe('Massage chân (3 lần) · gồm 2 lần suy ra từ tin nhắn');
    expect(fact(card, 'Trạng thái')).toMatch(/ · gồm 2 lần suy ra từ tin nhắn$/);
    expect(within(card).getByText(/^Ghi chú suy ra từ tin nhắn bên cạnh một số liệu/)).toBeTruthy();
  });

  it('shows only the markers the summary itself gives while the list cannot be loaded', async () => {
    factsError = MIGRATION_0011;
    const card = await openCard();
    await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    expect(fact(card, 'Tổng số lần đã đến')).toBe('5 lần · gồm 2 lần suy ra từ tin nhắn');
    expect(fact(card, 'Dịch vụ cuối cùng')).toContain('· suy ra từ tin nhắn');
    expect(fact(card, 'Khoảng thời gian tính')).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 4 buổi');
    expect(fact(card, 'Tổng chi trong khoảng')).toBe('1.050.000đ');
  });

  it('counts the guesses of the window exactly, or says "tối đa" when a recorded day hides one', () => {
    const f = baseFacts();
    expect(chatMarkers(chatSummary, f)).toEqual({
      visits: 2,
      lastVisit: true,
      window: { n: 2, atMost: false },
      spend: { n: 1, atMost: false },
      windowSpend: { n: 1, atMost: false },
    });
    // a third guess, before the window, on a day staff also recorded: the server counts two of the three and the console
    // cannot tell which, so the window holds one or two of them
    const withHidden: ChatFacts = { ...f, visits: [...(f.visits ?? []), visit({ id: 'chv_7', local_date: '2026-03-01', amount_vnd: 400000, amount_source: 'paid' })] };
    expect(chatMarkers(chatSummary, withHidden)).toEqual({
      visits: 2,
      lastVisit: true,
      window: { n: 2, atMost: true },
      spend: { n: 2, atMost: true },
      windowSpend: { n: 1, atMost: true },
    });
    // the same extra guess inside the window: all three are in it, so exactly two of them count there
    const inside: ChatFacts = { ...f, visits: [...(f.visits ?? []), visit({ id: 'chv_7', local_date: '2026-10-01' })] };
    expect(chatMarkers(chatSummary, inside).window).toEqual({ n: 2, atMost: false });
    // a guess on the day of the recorded last visit is known not to count
    const recorded: CustomerSummary = { ...chatSummary, last_visit: { visited_at: vn('2026-03-01', '10:00'), date: '2026-03-01', from_chat: false } };
    expect(chatMarkers(recorded, withHidden)).toEqual({
      visits: 2,
      lastVisit: false,
      window: { n: 2, atMost: false },
      spend: { n: 1, atMost: false },
      windowSpend: { n: 1, atMost: false },
    });
    // a guess before the window is in visits_total but not in the window
    const early: ChatFacts = { ...f, visits: (f.visits ?? []).map((v) => (v.id === 'chv_2' ? { ...v, local_date: '2026-03-01' } : v)) };
    expect(chatMarkers(chatSummary, early).window).toEqual({ n: 1, atMost: false });
    // no list, or a list older than the summary: only what the summary says
    const summaryOnly = { visits: 2, lastVisit: true, window: null, spend: null, windowSpend: null };
    expect(chatMarkers(chatSummary, null)).toEqual(summaryOnly);
    expect(chatMarkers({ ...chatSummary, chat: { ...chatSummary.chat!, visits_counted: 3 } }, f)).toEqual({ ...summaryOnly, visits: 3 });
    // nothing counted: no marker at all
    expect(chatMarkers({ ...chatSummary, chat: { visits_counted: 0 }, last_visit: null }, f)).toEqual({
      visits: 0,
      lastVisit: false,
      window: null,
      spend: null,
      windowSpend: null,
    });
  });

  it('writes "tối đa" in the marker when the number is a ceiling', async () => {
    const f = baseFacts();
    facts = { ...f, visits: [...(f.visits ?? []), visit({ id: 'chv_7', local_date: '2026-03-01', amount_vnd: 400000, amount_source: 'paid' })] };
    const card = await openCard();
    await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    await waitFor(() => expect(fact(card, 'Khoảng thời gian tính')).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 4 buổi · gồm tối đa 2 lần suy ra từ tin nhắn'));
    expect(fact(card, 'Tổng số tiền đã dùng')).toBe('1.400.000đ (tính trên 4 buổi có ghi số tiền) · gồm tối đa 2 lần suy ra từ tin nhắn');
    expect(fact(card, 'Tổng số lần đã đến')).toBe('5 lần · gồm 2 lần suy ra từ tin nhắn');
  });
});

describe('the section "Suy ra từ tin nhắn cũ"', () => {
  it('lists each guess with its time, amount source and confidence in words', async () => {
    const section = await openSection();
    // the analyzer version is only a tooltip for whoever maintains the tool
    const run = within(section).getByText(`Phân tích lúc ${fmtTime(GENERATED_AT)}.`);
    expect(run.getAttribute('title')).toBe('Bản công cụ phân tích: visits-rules-v1');
    expect(section.textContent).not.toContain('visits-rules-v1');
    const visits = within(section).getByRole('group', { name: 'Lần đến suy ra từ tin nhắn' });
    // newest first
    expect([...visits.querySelectorAll('li > div:first-child')].map((d) => d.textContent)).toEqual([VISIT_1, VISIT_2, VISIT_3]);
    for (const day of ['17/10/2026', '05/09/2026', '20/08/2026']) {
      expect(within(visits).getByRole('button', { name: `Xác nhận lần đến ngày ${day}` })).toBeTruthy();
      expect(within(visits).getByRole('button', { name: `Bỏ lần đến ngày ${day}` })).toBeTruthy();
    }

    const upcoming = within(section).getByRole('group', { name: 'Lịch hẹn suy ra từ tin nhắn' });
    expect(rowOf(upcoming, UPCOMING)).toBeTruthy();
    // an upcoming booking can only be dismissed
    expect(within(upcoming).queryByRole('button', { name: /^Xác nhận/ })).toBeNull();
    expect(within(upcoming).getByRole('button', { name: 'Bỏ lịch hẹn ngày 20/11/2026' })).toBeTruthy();

    const benefits = within(section).getByRole('group', { name: 'Quyền lợi suy ra từ tin nhắn' });
    expect([...benefits.querySelectorAll('li > div:first-child')].map((d) => d.textContent)).toEqual([BENEFIT_1, BENEFIT_2]);

    // decided rows: dimmed, with their state, collapsed by default
    const decided = section.querySelector('details.chat-decided') as HTMLDetailsElement;
    expect(decided.open).toBe(false);
    expect(decided.querySelector('summary')?.textContent).toBe('Đã xử lý (2)');
    const rows = [...decided.querySelectorAll('li')];
    expect(rows.every((li) => li.classList.contains('decided'))).toBe(true);
    expect(rows.map((li) => li.textContent)).toEqual([
      `Lần đến: 01/07/2026, chưa rõ giờ · chưa rõ dịch vụ · chưa rõ số tiền · chưa rõ kỹ thuật viên · chắc · đã bỏ ngày ${fmtDate(DECIDED_AT)}`,
      `Lần đến: 10/06/2026, chưa rõ giờ · chưa rõ dịch vụ · chưa rõ số tiền · chưa rõ kỹ thuật viên · khá chắc · đã xác nhận ngày ${fmtDate(DECIDED_AT)}`,
    ]);
    expect(within(decided).queryByRole('button')).toBeNull();
  });

  it('shows ten guessed visits and the rest on request', async () => {
    facts = {
      ...baseFacts(),
      visits: Array.from({ length: CHAT_VISIBLE_VISITS + 2 }, (_, i) => visit({ id: `chv_m${i}`, local_date: `2026-06-${String(i + 1).padStart(2, '0')}` })),
    };
    const section = await openSection();
    const visits = within(section).getByRole('group', { name: 'Lần đến suy ra từ tin nhắn' });
    expect(visits.querySelectorAll('li').length).toBe(CHAT_VISIBLE_VISITS);
    fireEvent.click(within(visits).getByRole('button', { name: 'Hiện thêm 2 lần đến' }));
    expect(visits.querySelectorAll('li').length).toBe(CHAT_VISIBLE_VISITS + 2);
    fireEvent.click(within(visits).getByRole('button', { name: 'Thu gọn danh sách lần đến' }));
    expect(visits.querySelectorAll('li').length).toBe(CHAT_VISIBLE_VISITS);
  });

  it('says so when nothing is left to decide', async () => {
    const f = baseFacts();
    facts = { ...f, visits: (f.visits ?? []).filter((v) => v.state !== 'active'), upcoming: [], benefits: [], phone_suggestion: null };
    const card = await openCard();
    const section = await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    expect(await within(section).findByText('Không còn dòng nào chờ xử lý.')).toBeTruthy();
    expect(section.querySelector('details.chat-decided summary')?.textContent).toBe('Đã xử lý (2)');
  });
});

describe('confirm a guessed visit', () => {
  const confirmForm = async (section: HTMLElement, day: string) => {
    fireEvent.click(within(section).getByRole('button', { name: `Xác nhận lần đến ngày ${day}` }));
    return within(section).getByRole('group', { name: `Xác nhận lần đến ngày ${day}` });
  };
  const field = (form: HTMLElement, label: string | RegExp) => within(form).getByLabelText(label) as HTMLInputElement;
  const save = (form: HTMLElement) => within(form).getByRole('button', { name: 'Ghi thành buổi làm' }) as HTMLButtonElement;

  it('opens the form with the guess and confirms it as it is', async () => {
    const section = await openSection();
    const form = await confirmForm(section, '17/10/2026');
    expect(field(form, /^Dịch vụ/).value).toBe('goi-dau-thu-gian');
    // the catalog name of the chosen id, under the field
    expect(within(form).getAllByText('Gội đầu thư giãn').some((el) => el.tagName === 'SPAN')).toBe(true);
    expect(field(form, 'Ngày đến').value).toBe('2026-10-17');
    expect(field(form, /^Giờ đến/).value).toBe('15:00');
    expect(field(form, /^Số tiền khách trả/).value).toBe('350.000');
    expect(field(form, /^Kỹ thuật viên/).value).toBe('Lan');
    // the service field offers the catalog list the console ships
    expect(form.querySelectorAll('datalist option').length).toBeGreaterThan(10);

    const detailLoads = sent('GET', `/staff/conversations/${conv.id}`).length;
    fireEvent.click(save(form));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/visits/chv_1/confirm').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/visits/chv_1/confirm')[0]!.body).toEqual({});
    expect(await within(section).findByText('Đã ghi lần đến ngày 17/10/2026 thành buổi làm. Không có tin hẹn giờ nào được tạo.')).toBeTruthy();
    // the list and the summary are loaded again; the row moves to the decided rows
    await waitFor(() => expect(within(section).queryByText(VISIT_1)).toBeNull());
    expect(factsLoads()).toBeGreaterThanOrEqual(2);
    expect(sent('GET', `/staff/conversations/${conv.id}`).length).toBeGreaterThan(detailLoads);
    expect(section.querySelector('details.chat-decided summary')?.textContent).toBe('Đã xử lý (3)');
    expect(within(section).queryByRole('group', { name: 'Xác nhận lần đến ngày 17/10/2026' })).toBeNull();
  });

  it('sends only the corrections staff make', async () => {
    const section = await openSection();
    const form = await confirmForm(section, '05/09/2026');
    // the guess names only a category and gives no time; its amount is a quote, so the field starts empty with a hint
    expect(field(form, /^Dịch vụ/).value).toBe('');
    expect(within(form).getByText('Để trống thì máy chủ ghi dịch vụ suy ra từ tin nhắn: massage.')).toBeTruthy();
    expect(field(form, /^Giờ đến/).value).toBe('');
    expect(within(form).getByText('Chưa rõ giờ thì buổi làm được ghi lúc 12:00.')).toBeTruthy();
    expect(field(form, /^Số tiền khách trả/).value).toBe('');
    expect(within(form).getByText('Tin nhắn có báo giá 250.000đ, chưa chắc là số khách đã trả. Nhập số tiền nếu khách đã trả.')).toBeTruthy();

    type(field(form, /^Dịch vụ/), 'massage-chan');
    type(field(form, /^Giờ đến/), '16:30');
    type(field(form, /^Số tiền khách trả/), '300000');
    expect(field(form, /^Số tiền khách trả/).value).toBe('300.000');
    type(field(form, /^Kỹ thuật viên/), ' Hoa ');
    fireEvent.click(save(form));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/visits/chv_2/confirm').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/visits/chv_2/confirm')[0]!.body).toEqual({
      service_id: 'massage-chan',
      visited_at_local: '2026-09-05 16:30',
      amount_vnd: 300000,
      technician: 'Hoa',
    });
  });

  it('needs a service when the guess names none, and checks the fields', async () => {
    const section = await openSection();
    const form = await confirmForm(section, '20/08/2026');
    expect(within(form).getByText('Chọn dịch vụ khách đã làm.')).toBeTruthy();
    expect(save(form).disabled).toBe(true);
    type(field(form, /^Dịch vụ/), 'massage-chan');
    expect(save(form).disabled).toBe(false);
    type(field(form, /^Kỹ thuật viên/), 'H'.repeat(61));
    expect(within(form).getByText('Tên kỹ thuật viên viết trên một dòng, tối đa 60 ký tự.')).toBeTruthy();
    expect(save(form).disabled).toBe(true);
    type(field(form, /^Kỹ thuật viên/), '');
    type(field(form, 'Ngày đến'), '');
    expect(within(form).getByText('Chọn ngày khách đến.')).toBeTruthy();
    // closing the form sends nothing
    fireEvent.click(within(form).getByRole('button', { name: 'Đóng' }));
    expect(within(section).queryByRole('group', { name: 'Xác nhận lần đến ngày 20/08/2026' })).toBeNull();
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });

  it('explains a row someone already decided, a missing customer row and migration 0011', async () => {
    decisionError = { status: 409, code: 'invalid_state', message: 'chat visit is not active' };
    const section = await openSection();
    let form = await confirmForm(section, '17/10/2026');
    fireEvent.click(save(form));
    const first = await within(section).findByText('Dòng này đã được xử lý trước đó, nên chưa ghi được buổi làm. Danh sách đã được tải lại.');
    // the sentence sits in the row of the open form, not at the end of a long list
    expect(first.closest('li')).toBe(rowOf(section, VISIT_1));
    await waitFor(() => expect(factsLoads()).toBe(2));

    decisionError = { status: 409, code: 'invalid_state', message: 'khách chưa có hồ sơ' };
    form = within(section).getByRole('group', { name: 'Xác nhận lần đến ngày 17/10/2026' });
    fireEvent.click(save(form));
    expect(await within(section).findByText('Khách chưa có hồ sơ khách hàng trên máy chủ, nên chưa ghi được buổi làm.')).toBeTruthy();

    decisionError = MIGRATION_0011;
    fireEvent.click(save(form));
    expect(
      await within(section).findByText(
        'Máy chủ chưa áp migration 0011_chat_facts.sql, nên chưa ghi được buổi làm. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.',
      ),
    ).toBeTruthy();
    // the form stays open with what staff typed, for another try
    expect(field(form, /^Số tiền khách trả/).value).toBe('350.000');
  });

  it('builds the body from the changed fields only', () => {
    const v = baseFacts().visits!.find((x) => x.id === 'chv_1')!;
    const init = visitConfirmInitial(v);
    expect(init).toEqual({ serviceId: 'goi-dau-thu-gian', date: '2026-10-17', time: '15:00', amount: '350.000', technician: 'Lan' });
    expect(visitConfirmBody(init, v)).toEqual({});
    // emptied amount and technician are sent as null; an emptied time records 12:00
    expect(visitConfirmBody({ ...init, amount: '', technician: '  ', time: '' }, v)).toEqual({ amount_vnd: null, technician: null, visited_at_local: '2026-10-17 12:00' });
    expect(visitConfirmBody({ ...init, date: '2026-10-18' }, v)).toEqual({ visited_at_local: '2026-10-18 15:00' });
    expect(visitConfirmProblem({ ...init, time: '25:00' }, v)).toBe('Giờ đến viết theo dạng 15:30, hoặc để trống nếu chưa rõ.');
    expect(visitConfirmProblem({ ...init, amount: '99.999.999.999.999.999.999' }, v)).toBe('Số tiền quá lớn hoặc không phải số.');
  });
});

describe('dismiss a guess', () => {
  it('asks first in one line, then dismisses', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Bỏ lần đến ngày 17/10/2026' }));
    let box = within(section).getByRole('group', { name: 'Xác nhận bỏ lần đến ngày 17/10/2026' });
    expect(box.querySelector('p')?.textContent).toBe('Bỏ lần đến ngày 17/10/2026? Lần phân tích sau không đưa lại dòng này.');
    fireEvent.click(within(box).getByRole('button', { name: 'Giữ lại' }));
    expect(within(section).queryByRole('group', { name: 'Xác nhận bỏ lần đến ngày 17/10/2026' })).toBeNull();
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);

    fireEvent.click(within(section).getByRole('button', { name: 'Bỏ lần đến ngày 17/10/2026' }));
    box = within(section).getByRole('group', { name: 'Xác nhận bỏ lần đến ngày 17/10/2026' });
    fireEvent.click(within(box).getByRole('button', { name: 'Bỏ dòng này' }));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/visits/chv_1/dismiss').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/visits/chv_1/dismiss')[0]!.body).toEqual({});
    expect(await within(section).findByText('Đã bỏ lần đến ngày 17/10/2026.')).toBeTruthy();
    await waitFor(() => expect(section.querySelector('details.chat-decided summary')?.textContent).toBe('Đã xử lý (3)'));
  });

  it('dismisses an upcoming booking and a benefit the same way', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Bỏ lịch hẹn ngày 20/11/2026' }));
    fireEvent.click(within(within(section).getByRole('group', { name: 'Xác nhận bỏ lịch hẹn ngày 20/11/2026' })).getByRole('button', { name: 'Bỏ dòng này' }));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/visits/chv_6/dismiss').length).toBe(1));
    expect(await within(section).findByText('Đã bỏ lịch hẹn ngày 20/11/2026.')).toBeTruthy();

    fireEvent.click(within(section).getByRole('button', { name: 'Bỏ quyền lợi Gói 10 buổi gội đầu' }));
    const box = within(section).getByRole('group', { name: 'Xác nhận bỏ quyền lợi Gói 10 buổi gội đầu' });
    expect(box.querySelector('p')?.textContent).toBe('Bỏ quyền lợi Gói 10 buổi gội đầu? Lần phân tích sau không đưa lại dòng này.');
    fireEvent.click(within(box).getByRole('button', { name: 'Bỏ dòng này' }));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/benefits/chb_1/dismiss').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/benefits/chb_1/dismiss')[0]!.body).toEqual({});
  });

  it('explains a row the server no longer has and reloads the list', async () => {
    decisionError = OLD_SERVER_404;
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Bỏ lần đến ngày 05/09/2026' }));
    fireEvent.click(within(within(section).getByRole('group', { name: 'Xác nhận bỏ lần đến ngày 05/09/2026' })).getByRole('button', { name: 'Bỏ dòng này' }));
    expect(
      await within(section).findByText('Máy chủ không còn dòng này, nên chưa bỏ được dòng này. Có thể lần phân tích mới đã thay danh sách; danh sách đã được tải lại.'),
    ).toBeTruthy();
    await waitFor(() => expect(factsLoads()).toBe(2));
  });
});

describe('confirm a guessed benefit', () => {
  const field = (form: HTMLElement, label: string | RegExp) => within(form).getByLabelText(label) as HTMLInputElement;
  const save = (form: HTMLElement) => within(form).getByRole('button', { name: 'Ghi thành quyền lợi' }) as HTMLButtonElement;

  it('prefills the counts the chat states and sends them', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' });
    expect(field(form, 'Tên quyền lợi').value).toBe('Gói 10 buổi gội đầu');
    expect(field(form, /^Tổng số lần/).value).toBe('10');
    expect(field(form, /^Số lần đã dùng/).value).toBe('3');
    expect(within(form).getByText('Tính từ 7 lần còn lại mà tin nhắn nêu.')).toBeTruthy();
    fireEvent.click(save(form));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/benefits/chb_1/confirm').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/benefits/chb_1/confirm')[0]!.body).toEqual({ total_count: 10, used_count: 3 });
    expect(await within(section).findByText('Đã ghi quyền lợi Gói 10 buổi gội đầu.')).toBeTruthy();
  });

  it('asks for the total when the chat does not state it', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận quyền lợi Voucher sinh nhật' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận quyền lợi Voucher sinh nhật' });
    expect(field(form, /^Tổng số lần/).value).toBe('');
    expect(within(form).getByText('Tin nhắn không nói tổng số lần, cần nhập.')).toBeTruthy();
    expect(within(form).getByText('Tổng số lần là số nguyên lớn hơn 0.')).toBeTruthy();
    expect(save(form).disabled).toBe(true);
    type(field(form, /^Tổng số lần/), '2');
    expect(field(form, /^Số lần đã dùng/).value).toBe('1');
    type(field(form, /^Số lần đã dùng/), '3');
    expect(within(form).getByText('Số lần đã dùng là số nguyên từ 0 đến tổng số lần.')).toBeTruthy();
    type(field(form, /^Số lần đã dùng/), '0');
    type(field(form, 'Tên quyền lợi'), ' Voucher sinh nhật 2026 ');
    type(field(form, /^Hạn dùng/), '2099-06-30');
    fireEvent.click(save(form));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/benefits/chb_2/confirm').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/benefits/chb_2/confirm')[0]!.body).toEqual({
      title: 'Voucher sinh nhật 2026',
      total_count: 2,
      used_count: 0,
      expires_at: Date.parse('2099-06-30T23:59:59+07:00'),
    });
  });

  it('builds the body with the default uses', () => {
    const b = baseFacts().benefits![0]!;
    expect(benefitConfirmBody(benefitConfirmInitial(b), b)).toEqual({ total_count: 10, used_count: 3 });
    // remaining unknown: 0 uses taken
    expect(benefitConfirmBody(benefitConfirmInitial({ ...b, remaining: null }), { ...b, remaining: null })).toEqual({ total_count: 10, used_count: 0 });
  });
});

describe('phone suggestion', () => {
  it('stays masked except the last 3 digits until "Hiện số"', async () => {
    const section = await openSection();
    const group = within(section).getByRole('group', { name: 'Số điện thoại gợi ý' });
    expect(within(group).getByText('*******321')).toBeTruthy();
    expect(document.body.innerHTML).not.toContain('0987654321');
    fireEvent.click(within(group).getByRole('button', { name: 'Hiện số' }));
    expect(within(group).getByText('0987654321')).toBeTruthy();
    fireEvent.click(within(group).getByRole('button', { name: 'Ẩn số' }));
    expect(document.body.innerHTML).not.toContain('0987654321');
  });

  it('uses the number for the customer', async () => {
    const section = await openSection();
    const group = within(section).getByRole('group', { name: 'Số điện thoại gợi ý' });
    expect(within(group).getByText('Số này có trong tin nhắn cũ của khách nhưng chưa chắc là số điện thoại của khách.')).toBeTruthy();
    fireEvent.click(within(group).getByRole('button', { name: 'Dùng số này' }));
    await waitFor(() => expect(sent('POST', `/staff/chat-facts/${encodeURIComponent(ZID)}/phone/accept`).length).toBe(1));
    expect(sent('POST', `/staff/chat-facts/${encodeURIComponent(ZID)}/phone/accept`)[0]!.body).toEqual({});
    expect(await within(section).findByText('Đã lưu số gợi ý làm số điện thoại của khách.')).toBeTruthy();
    await waitFor(() => expect(within(section).queryByRole('group', { name: 'Số điện thoại gợi ý' })).toBeNull());
  });

  it('dismisses the number after a one-line confirmation', async () => {
    const section = await openSection();
    const group = within(section).getByRole('group', { name: 'Số điện thoại gợi ý' });
    fireEvent.click(within(group).getByRole('button', { name: 'Bỏ số gợi ý' }));
    const box = within(group).getByRole('group', { name: 'Xác nhận bỏ số gợi ý' });
    expect(box.querySelector('p')?.textContent).toBe('Bỏ số gợi ý? Số này sẽ không được gợi ý lại cho khách này.');
    fireEvent.click(within(box).getByRole('button', { name: 'Bỏ số này' }));
    await waitFor(() => expect(sent('POST', `/staff/chat-facts/${encodeURIComponent(ZID)}/phone/dismiss`).length).toBe(1));
    expect(await within(section).findByText('Đã bỏ số gợi ý. Số này sẽ không được gợi ý lại.')).toBeTruthy();
  });

  it('has no wording of its own for a customer who has a phone; a 409 for a phone saved meanwhile is explained', async () => {
    // The server sends no suggestion while the customer has a phone. Should one arrive anyway (a phone typed between
    // two loads), the row reads as usual and the server's 409 explains why the number was not used.
    summary = { ...chatSummary, phone: '0901234567' };
    decisionError = { status: 409, code: 'invalid_state', message: 'the customer already has a phone number' };
    const section = await openSection();
    const group = within(section).getByRole('group', { name: 'Số điện thoại gợi ý' });
    expect(within(group).getByText('Số này có trong tin nhắn cũ của khách nhưng chưa chắc là số điện thoại của khách.')).toBeTruthy();
    expect(within(group).queryByText(/không thay bằng số gợi ý/)).toBeNull();
    const use = within(group).getByRole('button', { name: 'Dùng số này' }) as HTMLButtonElement;
    expect(use.disabled).toBe(false);
    fireEvent.click(use);
    await waitFor(() => expect(sent('POST', `/staff/chat-facts/${encodeURIComponent(ZID)}/phone/accept`).length).toBe(1));
    expect(
      await within(section).findByText('Khách đã có số điện thoại nên máy chủ không dùng số gợi ý. Nếu số gợi ý đúng hơn, sửa ở dòng Số điện thoại phía trên.'),
    ).toBeTruthy();
  });

  it('masks a number down to its last 3 digits', () => {
    expect(maskPhone('0912345678')).toBe('*******678');
    expect(maskPhone(' 0912345678 ')).toBe('*******678');
    expect(maskPhone('12')).toBe('**');
  });
});

describe('older servers and migration 0011', () => {
  it('says calmly that the server is too old (404)', async () => {
    factsError = OLD_SERVER_404;
    const card = await openCard();
    const section = await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    expect(
      await within(section).findByText(
        'Máy chủ không có địa chỉ này, nên chưa tải được dữ liệu suy ra từ tin nhắn cũ. Có thể máy chủ đang chạy bản cũ: cập nhật và khởi động lại máy chủ, rồi làm lại.',
      ),
    ).toBeTruthy();
    expect(within(section).queryByRole('button')).toBeNull();
    expect(within(section).queryByRole('alert')).toBeNull();
  });

  it('says calmly that migration 0011 is not applied (409)', async () => {
    factsError = MIGRATION_0011;
    const card = await openCard();
    const section = await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    expect(
      await within(section).findByText(
        'Máy chủ chưa áp migration 0011_chat_facts.sql, nên chưa tải được dữ liệu suy ra từ tin nhắn cũ. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.',
      ),
    ).toBeTruthy();
    expect(within(section).queryByRole('button')).toBeNull();
  });
});

// Contact A of the analyzer fixture of the server (apps/server/test/fixtures/analyzer-visits-document.json): the summary
// and the GET answer exactly as apps/server/test/chat-facts-analyzer-document.test.ts reads them from the server, with
// every field the server sends (ids and import times aside).
describe('answers shaped exactly like the server sends them', () => {
  const VISIT_AT = vn('2026-11-05', '10:00');
  const BOOKING_AT = vn('2026-11-17', '09:00');
  const STATED = 1793854800000;
  const IMPORTED = vn('2026-11-12', '15:11');
  const ROW = { zalo_user_id: ZID, analyzer_version: 'visits-rules-v1', imported_at: IMPORTED, confirmed_visit_id: null, decided_by: null, decided_at: null };

  const serverSummary: CustomerSummary = {
    role: null,
    role_source: null,
    name: null,
    address_term: null,
    phone: '0912345678',
    status: 'returning',
    visits_total: 2,
    last_visit: {
      visited_at: VISIT_AT,
      date: '2026-11-05',
      time: '10:00',
      services: [
        { service_id: 'massage-body-thu-gian', name: 'Massage body thư giãn' },
        { service_id: 'ext:goi-dau', name: 'gội đầu' },
      ],
      technician: null,
      amount_vnd: 350000,
      from_chat: true,
    },
    days_since_last_visit: 7,
    usual_gap_days: 5,
    gap_basis: 'own',
    absent_after_days: 14,
    lifetime_spend_vnd: 549000,
    lifetime_spend_visits: 2,
    window: {
      days: 183,
      from_date: '2026-05-13',
      visits: 2,
      spend_vnd: 549000,
      avg_spend_vnd: 274500,
      services: [
        { service_id: 'ext:goi-dau', name: 'gội đầu', count: 1 },
        { service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', count: 1 },
        { service_id: 'massage-body-thu-gian', name: 'Massage body thư giãn', count: 1 },
      ],
    },
    benefits: [],
    chat: { visits_counted: 1, visits_low: 0, upcoming_next: { date: '2026-11-17', time: '09:00' }, benefits_active: 1, phone_suggestion: false, analyzer_version: 'visits-rules-v1', generated_at: GENERATED_AT },
  };

  const serverFacts = (): ChatFacts => ({
    visits: [
      {
        ...ROW,
        id: 'chv_a1',
        local_date: '2026-11-05',
        kind: 'visit',
        visited_at: VISIT_AT,
        time_known: true,
        time: '10:00',
        services: [
          { service_id: 'massage-body-thu-gian', service_name: 'Massage body thư giãn', basis: 'booking', name: 'Massage body thư giãn' },
          { service_id: null, service_name: 'gội đầu', basis: 'visit_day', name: 'gội đầu' },
        ],
        amount_vnd: 350000,
        amount_source: 'paid',
        technician: null,
        confidence: 'high',
        signals: ['booking_request', 'booking_confirmed', 'arrival', 'payment'],
        evidence: [1793757600000, 1793758200000, 1793847300000, 1793853300000],
        fact_source: 'chat_rules',
        state: 'active',
      },
    ],
    upcoming: [
      {
        ...ROW,
        id: 'chv_a2',
        local_date: '2026-11-17',
        kind: 'upcoming',
        visited_at: BOOKING_AT,
        time_known: true,
        time: '09:00',
        services: [{ service_id: null, service_name: 'gội đầu', basis: 'booking', name: 'gội đầu' }],
        amount_vnd: null,
        amount_source: null,
        technician: null,
        confidence: null,
        signals: ['booking_request', 'booking_confirmed'],
        evidence: [1794402000000, 1794402300000],
        fact_source: 'chat_rules',
        state: 'active',
      },
    ],
    benefits: [
      {
        id: 'chb_a1',
        zalo_user_id: ZID,
        kind: 'package',
        title: 'Gói 10 buổi – Gội đầu',
        title_key: 'goi 10 buoi – goi dau',
        service_id: null,
        service_name: null,
        total_count: 10,
        remaining: 7,
        stated_by: 'owner',
        confidence: 'high',
        stated_at: STATED,
        state: 'active',
        confirmed_benefit_id: null,
        analyzer_version: 'visits-rules-v1',
        imported_at: IMPORTED,
        decided_by: null,
        decided_at: null,
      },
    ],
    phone_suggestion: null,
    analyzer_version: 'visits-rules-v1',
    generated_at: GENERATED_AT,
    imported_at: IMPORTED,
    model_pass: { ran: false, reason: 'disabled' },
  });

  beforeEach(() => {
    summary = serverSummary;
    facts = serverFacts();
  });

  it('renders the rows, the markers and no phone group', async () => {
    const card = await openCard();
    const section = await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    const visits = await within(section).findByRole('group', { name: 'Lần đến suy ra từ tin nhắn' });
    expect([...visits.querySelectorAll('li > div:first-child')].map((d) => d.textContent)).toEqual([
      '05/11/2026 lúc 10:00 · Massage body thư giãn, gội đầu · 350.000đ (đã trả) · chưa rõ kỹ thuật viên · chắc',
    ]);
    const upcoming = within(section).getByRole('group', { name: 'Lịch hẹn suy ra từ tin nhắn' });
    expect(upcoming.querySelector('li > div:first-child')?.textContent).toBe('17/11/2026 lúc 09:00 · gội đầu · chưa rõ số tiền · chưa rõ kỹ thuật viên');
    const benefits = within(section).getByRole('group', { name: 'Quyền lợi suy ra từ tin nhắn' });
    expect(benefits.querySelector('li > div:first-child')?.textContent).toBe(
      `Gói 10 buổi – Gội đầu (gói nhiều buổi) · tổng 10 lần, còn 7 lần · theo tin studio nhắn ngày ${fmtDate(STATED)} · chắc`,
    );
    expect(within(section).queryByRole('group', { name: 'Số điện thoại gợi ý' })).toBeNull();
    expect(section.querySelector('details.chat-decided')).toBeNull();

    expect(fact(card, 'Tổng số lần đã đến')).toBe('2 lần · gồm 1 lần suy ra từ tin nhắn');
    expect(fact(card, 'Dịch vụ cuối cùng')).toBe('Massage body thư giãn, gội đầu · 05/11/2026 lúc 10:00 · chưa ghi kỹ thuật viên · 350.000đ · suy ra từ tin nhắn');
    await waitFor(() => expect(fact(card, 'Tổng số tiền đã dùng')).toBe('549.000đ (tính trên 2 buổi có ghi số tiền) · gồm 1 lần suy ra từ tin nhắn'));
    expect(fact(card, 'Khoảng thời gian tính')).toBe('183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 2 buổi · gồm 1 lần suy ra từ tin nhắn');
    expect(sent('GET', FACTS_URL)).toHaveLength(1);
  });

  it('confirms the visit and the benefit with the bodies the server reads', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận lần đến ngày 05/11/2026' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận lần đến ngày 05/11/2026' });
    const field = (label: string | RegExp) => (within(form).getByLabelText(label) as HTMLInputElement).value;
    // the server records the first catalog service of the guess, its time and its amount when nothing is changed
    expect([field(/^Dịch vụ/), field('Ngày đến'), field(/^Giờ đến/), field(/^Số tiền khách trả/), field(/^Kỹ thuật viên/)]).toEqual([
      'massage-body-thu-gian',
      '2026-11-05',
      '10:00',
      '350.000',
      '',
    ]);
    fireEvent.click(within(form).getByRole('button', { name: 'Ghi thành buổi làm' }));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/visits/chv_a1/confirm')).toHaveLength(1));
    expect(sent('POST', '/staff/chat-facts/visits/chv_a1/confirm')[0]!.body).toEqual({});

    fireEvent.click(await within(section).findByRole('button', { name: 'Xác nhận quyền lợi Gói 10 buổi – Gội đầu' }));
    const bform = within(section).getByRole('group', { name: 'Xác nhận quyền lợi Gói 10 buổi – Gội đầu' });
    fireEvent.click(within(bform).getByRole('button', { name: 'Ghi thành quyền lợi' }));
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/benefits/chb_a1/confirm')).toHaveLength(1));
    expect(sent('POST', '/staff/chat-facts/benefits/chb_a1/confirm')[0]!.body).toEqual({ total_count: 10, used_count: 3 });
  });
});

describe('row texts', () => {
  it('reads a row leniently', () => {
    // services sent as JSON text, the date taken from visited_at, the time from a `time` field
    const loose = { id: 'chv_x', state: 'active', visited_at: vn('2026-10-02', '12:00'), services_json: '[{"service_id":"massage-chan","service_name":null}]', time: '09:15' } as unknown as ChatVisitView;
    expect(chatVisitText(loose)).toBe('02/10/2026 lúc 09:15 · Massage chân · chưa rõ số tiền · chưa rõ kỹ thuật viên');
    expect(chatVisitText({ id: 'chv_y', state: 'active', amount_vnd: 450000, amount_source: 'list_price', confidence: 'medium' })).toBe(
      'chưa rõ ngày, chưa rõ giờ · chưa rõ dịch vụ · 450.000đ (giá niêm yết) · chưa rõ kỹ thuật viên · khá chắc',
    );
    expect(chatBenefitText({ id: 'chb_x', kind: 'package', title: 'Liệu trình da', state: 'active' })).toBe('Liệu trình da (gói nhiều buổi) · chưa rõ số lần');
    expect(chatBenefitText({ id: 'chb_y', kind: 'package', title: 'Gói 5 buổi', total_count: 5, state: 'active' })).toBe(
      'Gói 5 buổi (gói nhiều buổi) · tổng 5 lần, chưa rõ còn bao nhiêu',
    );
  });
});

// ---------------------------------------------------------------- review of 2026-11-12

describe('review: the phone suggestion decided elsewhere', () => {
  const phoneUrl = (action: string) => `/staff/chat-facts/${encodeURIComponent(ZID)}/phone/${action}`;
  async function dismissPhone(section: HTMLElement) {
    const group = within(section).getByRole('group', { name: 'Số điện thoại gợi ý' });
    fireEvent.click(within(group).getByRole('button', { name: 'Bỏ số gợi ý' }));
    fireEvent.click(within(within(group).getByRole('group', { name: 'Xác nhận bỏ số gợi ý' })).getByRole('button', { name: 'Bỏ số này' }));
    await waitFor(() => expect(sent('POST', phoneUrl('dismiss')).length).toBe(1));
  }

  it('a dismiss answered "no suggestion" says the number was already used or dismissed', async () => {
    decisionError = { status: 409, code: 'invalid_state', message: 'there is no phone number suggestion for this contact' };
    const section = await openSection();
    await dismissPhone(section);
    expect(await within(section).findByText('Số gợi ý đã được xử lý trước đó (đã dùng hoặc đã bỏ). Danh sách đã được tải lại.')).toBeTruthy();
    expect(within(section).queryByText(/khách đã có số điện thoại/i)).toBeNull();
  });

  it('each 409 of the phone endpoints gets its own sentence', () => {
    const e = (message: string) => new ApiError(409, 'invalid_state', message);
    const what = 'lưu được số điện thoại';
    expect(chatDecisionErrorText(e('the suggestion was decided in the meantime'), null, what, 'accept')).toBe(
      'Số gợi ý đã được xử lý trước đó (đã dùng hoặc đã bỏ). Danh sách đã được tải lại.',
    );
    expect(chatDecisionErrorText(e('khách chưa có hồ sơ'), null, what, 'accept')).toBe('Khách chưa có hồ sơ khách hàng trên máy chủ, nên chưa lưu được số điện thoại.');
    expect(chatDecisionErrorText(e('another customer already has this phone number'), null, what, 'accept')).toBe(
      'Số này đang là số điện thoại của một khách khác, nên máy chủ không dùng số này cho khách này.',
    );
    expect(chatDecisionErrorText(e('the customer already has a phone number'), null, what, 'accept')).toMatch(/^Khách đã có số điện thoại/);
  });
});

describe('review: values the server refuses', () => {
  it('a confirm date in the future is refused by the form, with a sentence', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận lần đến ngày 17/10/2026' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận lần đến ngày 17/10/2026' });
    type(within(form).getByLabelText('Ngày đến') as HTMLInputElement, '2099-12-24');
    expect(within(form).getByText('Ngày đến chưa tới. Chỉ ghi buổi khách đã làm.')).toBeTruthy();
    expect((within(form).getByRole('button', { name: 'Ghi thành buổi làm' }) as HTMLButtonElement).disabled).toBe(true);
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });

  it('checks the time of today against the clock, an unknown time being 12:00', () => {
    const v = baseFacts().visits!.find((x) => x.id === 'chv_1')!;
    const init = visitConfirmInitial(v);
    const nineAm = vn('2026-11-12', '09:00');
    expect(visitConfirmProblem({ ...init, date: '2026-11-12', time: '' }, v, nineAm)).toBe(
      'Chưa rõ giờ thì buổi làm được ghi lúc 12:00, mà hôm nay chưa tới giờ đó. Nhập giờ khách đã đến.',
    );
    expect(visitConfirmProblem({ ...init, date: '2026-11-12', time: '11:30' }, v, nineAm)).toBe('Giờ đến chưa tới. Chỉ ghi buổi khách đã làm.');
    // up to one hour ahead is allowed, like the server
    expect(visitConfirmProblem({ ...init, date: '2026-11-12', time: '09:45' }, v, nineAm)).toBeNull();
    expect(visitConfirmProblem({ ...init, date: '2026-11-12', time: '' }, v, vn('2026-11-12', '11:30'))).toBeNull();
  });

  it('a benefit total above 1000 is refused by both benefit forms', async () => {
    const b = baseFacts().benefits![0]!;
    expect(benefitConfirmProblem({ ...benefitConfirmInitial(b), total: '1500', used: '0' }, b)).toBe('Tổng số lần tối đa 1000.');
    expect(benefitConfirmProblem({ ...benefitConfirmInitial(b), total: '1000', used: '0' }, b)).toBeNull();
    expect(benefitFormProblem({ ...EMPTY_BENEFIT_FORM, title: 'Gói lớn', total: '1001' })).toBe('Tổng số lần tối đa 1000.');
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' });
    type(within(form).getByLabelText(/^Tổng số lần/) as HTMLInputElement, '1500');
    expect(within(form).getByText('Tổng số lần tối đa 1000.')).toBeTruthy();
    expect((within(form).getByRole('button', { name: 'Ghi thành quyền lợi' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a 422 names the form field as staff read it, never the API field', async () => {
    decisionError = { status: 422, code: 'validation_failed', message: 'technician must be one line', details: { field: 'technician' } };
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận lần đến ngày 17/10/2026' }));
    fireEvent.click(within(within(section).getByRole('group', { name: 'Xác nhận lần đến ngày 17/10/2026' })).getByRole('button', { name: 'Ghi thành buổi làm' }));
    expect(await within(section).findByText('Máy chủ không nhận giá trị ở ô Kỹ thuật viên, nên chưa ghi được buổi làm. Sửa ô đó rồi làm lại.')).toBeTruthy();
    expect(section.textContent).not.toContain('trường technician');
    const e = (field: string) => new ApiError(422, 'validation_failed', 'x', { field });
    expect(chatDecisionErrorText(e('visited_at_local'), null, 'ghi được buổi làm', null)).toContain('ô Ngày đến hoặc Giờ đến');
    expect(chatDecisionErrorText(e('total_count'), null, 'ghi được quyền lợi', null)).toContain('ô Tổng số lần');
    expect(chatDecisionErrorText(e('used_count'), null, 'ghi được quyền lợi', null)).toContain('ô Số lần đã dùng');
    expect(chatDecisionErrorText(e('nope'), null, 'ghi được quyền lợi', null)).toBe('Máy chủ không nhận dữ liệu của biểu mẫu, nên chưa ghi được quyền lợi.');
  });
});

describe('review: a booking whose date has passed', () => {
  it('is not listed under "Lịch hẹn sắp tới" and offers no button', async () => {
    const f = baseFacts();
    facts = { ...f, upcoming: [...f.upcoming!, { ...f.upcoming![0]!, id: 'chv_past', local_date: '2001-11-01', visited_at: vn('2001-11-01', '15:30') }] };
    const section = await openSection();
    const soon = within(section).getByRole('group', { name: 'Lịch hẹn suy ra từ tin nhắn' });
    expect(soon.textContent).not.toContain('01/11/2001');
    expect(rowOf(soon, UPCOMING)).toBeTruthy();
    const past = within(section).getByRole('group', { name: 'Lịch hẹn đã qua ngày' });
    expect(past.textContent).toContain('01/11/2001 lúc 15:30 · Massage chân');
    expect(within(past).queryByRole('button')).toBeNull();
    // a dismiss of an upcoming booking says it also keeps a visit of that date out
    fireEvent.click(within(soon).getByRole('button', { name: 'Bỏ lịch hẹn ngày 20/11/2026' }));
    expect(within(section).getByRole('group', { name: 'Xác nhận bỏ lịch hẹn ngày 20/11/2026' }).querySelector('p')?.textContent).toBe(
      'Bỏ lịch hẹn ngày 20/11/2026? Lần phân tích sau không đưa lại lịch hẹn này, và không tính lần đến nào vào ngày đó.',
    );
  });

  it('with only past bookings left, the "sắp tới" group is gone', async () => {
    const f = baseFacts();
    facts = { ...f, upcoming: [{ ...f.upcoming![0]!, id: 'chv_past', local_date: '2001-11-01', visited_at: vn('2001-11-01', '15:30') }] };
    const section = await openSection();
    expect(within(section).queryByRole('group', { name: 'Lịch hẹn suy ra từ tin nhắn' })).toBeNull();
    expect(within(section).getByRole('group', { name: 'Lịch hẹn đã qua ngày' })).toBeTruthy();
  });
});

describe('review: markers on the status line and the usual services', () => {
  it('a customer whose only visit is a guess sees the marker on both', async () => {
    summary = {
      ...chatSummary,
      status: 'first_visit_done',
      visits_total: 1,
      lifetime_spend_vnd: 350000,
      lifetime_spend_visits: 1,
      usual_gap_days: 30,
      gap_basis: 'default',
      window: { days: 183, from_date: '2026-05-13', visits: 1, spend_vnd: 350000, avg_spend_vnd: 350000, services: [{ service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', count: 1 }] },
      chat: { ...chatSummary.chat!, visits_counted: 1 },
    };
    const f = baseFacts();
    facts = { ...f, visits: (f.visits ?? []).filter((v) => v.id !== 'chv_2') };
    const card = await openCard();
    await within(card).findByRole('region', { name: 'Suy ra từ tin nhắn cũ' });
    await waitFor(() => expect(fact(card, 'Dịch vụ thường dùng')).toBe('Gội đầu thư giãn (1 lần) · gồm 1 lần suy ra từ tin nhắn'));
    expect(fact(card, 'Trạng thái')).toMatch(/^đã đến lần đầu Khách mới đến một lần\. .* · gồm 1 lần suy ra từ tin nhắn$/);
  });
});

describe('review: the uses of a confirmed benefit', () => {
  it('a total below the remaining count the chat states leaves the uses empty and asks for them', async () => {
    const section = await openSection();
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' }));
    const form = within(section).getByRole('group', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' });
    type(within(form).getByLabelText(/^Tổng số lần/) as HTMLInputElement, '5');
    expect((within(form).getByLabelText(/^Số lần đã dùng/) as HTMLInputElement).value).toBe('');
    expect(within(form).queryByText(/^Tính từ/)).toBeNull();
    expect(within(form).getByText('Tin nhắn nói còn 7 lần, nhiều hơn tổng số lần: nhập số lần đã dùng.')).toBeTruthy();
    const save = within(form).getByRole('button', { name: 'Ghi thành quyền lợi' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    type(within(form).getByLabelText(/^Số lần đã dùng/) as HTMLInputElement, '0');
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(sent('POST', '/staff/chat-facts/benefits/chb_1/confirm').length).toBe(1));
    expect(sent('POST', '/staff/chat-facts/benefits/chb_1/confirm')[0]!.body).toEqual({ total_count: 5, used_count: 0 });
    const b = baseFacts().benefits![0]!;
    expect(benefitConfirmUsed({ ...benefitConfirmInitial(b), total: '' }, b)).toBe('');
    expect(benefitConfirmUsed({ ...benefitConfirmInitial(b), total: '12' }, b)).toBe('5');
  });
});

describe('review: the amount of a guess that is not known to be paid', () => {
  it('starts empty, so a one-click confirm records no amount; a typed amount is sent', () => {
    const quoted = baseFacts().visits!.find((x) => x.id === 'chv_2')!;
    const init = visitConfirmInitial(quoted);
    expect(init.amount).toBe('');
    expect(visitConfirmBody(init, quoted)).toEqual({});
    expect(visitConfirmBody({ ...init, amount: '250.000' }, quoted)).toEqual({ amount_vnd: 250000 });
    const listed = { ...quoted, amount_source: 'list_price' as const };
    expect(visitConfirmInitial(listed).amount).toBe('');
    // a paid amount is prefilled and left out of the body while unchanged
    const paid = baseFacts().visits!.find((x) => x.id === 'chv_1')!;
    expect(visitConfirmInitial(paid).amount).toBe('350.000');
    expect(visitConfirmBody(visitConfirmInitial(paid), paid)).toEqual({});
  });
});

describe('review: guesses the server says are already recorded', () => {
  it('a guess on a day with a recorded visit has no confirm button; a benefit with a recorded title says so', async () => {
    const f = baseFacts();
    facts = {
      ...f,
      visits: (f.visits ?? []).map((v) => (v.id === 'chv_1' ? { ...v, recorded_day: true } : { ...v, recorded_day: false })),
      benefits: (f.benefits ?? []).map((b) => (b.id === 'chb_1' ? { ...b, recorded_title: true } : b)),
    };
    const section = await openSection();
    const row = rowOf(section, VISIT_1);
    expect(within(row).getByText(RECORDED_DAY_TEXT)).toBeTruthy();
    expect(within(row).queryByRole('button', { name: 'Xác nhận lần đến ngày 17/10/2026' })).toBeNull();
    expect(within(row).getByRole('button', { name: 'Bỏ lần đến ngày 17/10/2026' })).toBeTruthy();
    expect(within(rowOf(section, VISIT_2)).getByRole('button', { name: 'Xác nhận lần đến ngày 05/09/2026' })).toBeTruthy();
    expect(within(rowOf(section, BENEFIT_1)).getByText(RECORDED_TITLE_TEXT)).toBeTruthy();
    expect(within(rowOf(section, BENEFIT_2)).queryByText(RECORDED_TITLE_TEXT)).toBeNull();
  });

  it('the 409 of a confirm onto a recorded day or a recorded title gets its own sentence', () => {
    const e = (message: string) => new ApiError(409, 'invalid_state', message);
    expect(chatDecisionErrorText(e('a visit is already recorded on this date'), null, 'ghi được buổi làm', null)).toBe(
      'Ngày này đã có buổi làm được ghi cho khách, nên chưa ghi được buổi làm. Nếu đó là cùng một lần đến, bỏ dòng này.',
    );
    expect(chatDecisionErrorText(e('the customer already has a benefit with this title'), null, 'ghi được quyền lợi', null)).toBe(
      'Khách đã có quyền lợi cùng tên, nên chưa ghi được quyền lợi. Nếu đây là một gói khác, đổi tên quyền lợi rồi xác nhận lại.',
    );
  });
});

describe('review: the model pass in words staff use', () => {
  it('says "trợ lý AI", never "model"', async () => {
    facts = { ...baseFacts(), model_pass: { ran: true, reason: 'ok' } };
    const section = await openSection();
    expect(within(section).getByText(`Phân tích lúc ${fmtTime(GENERATED_AT)}, có dùng trợ lý AI đọc lại tin nhắn.`)).toBeTruthy();
    expect(section.textContent).not.toMatch(/\bmodel\b/);
  });
});

describe('review: open lists of the card after a chat decision', () => {
  it('the open benefits list and the open visits list load again after a confirm in the chat section', async () => {
    const orig = globalThis.fetch;
    let benefitConfirmed = false;
    let visitConfirmed = false;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.startsWith('/staff/benefits?')) {
          calls.push({ method: 'GET', url, body: undefined });
          return json({
            benefits: benefitConfirmed
              ? [{ id: 'ben_new', customer_id: 'cus_f', kind: 'package', title: 'Gói 10 buổi gội đầu', service_id: null, total_count: 10, used_count: 3, remaining: 7, expires_at: null, status: 'active', recorded_by: 'lan', created_at: T, updated_at: T }]
              : [],
          });
        }
        if (url.startsWith('/staff/visits?')) {
          calls.push({ method: 'GET', url, body: undefined });
          return json({ visits: visitConfirmed ? [{ id: 'vis_new', customer_id: 'cus_f', service_id: 'goi-dau-thu-gian', name: 'Gội đầu thư giãn', visited_at: vn('2026-10-17', '15:00'), source: 'staff' }] : [] });
        }
        if (/\/benefits\/[^/]+\/confirm$/.test(url)) benefitConfirmed = true;
        if (/\/visits\/[^/]+\/confirm$/.test(url)) visitConfirmed = true;
        return orig(input, init);
      }),
    );
    const section = await openSection();
    const card = screen.getByRole('region', { name: 'Tóm tắt khách hàng' });
    const loads = (prefix: string) => calls.filter((c) => c.url.startsWith(prefix)).length;

    fireEvent.click(within(card).getByRole('button', { name: 'Thêm hoặc dùng quyền lợi' }));
    const panel = within(card).getByRole('group', { name: 'Quyền lợi của khách' });
    await within(panel).findByText('Khách này chưa có quyền lợi nào được ghi.');
    // what staff typed in the add form stays while the list loads again
    type(within(panel).getByLabelText('Tên quyền lợi') as HTMLInputElement, 'Gói đang gõ');
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' }));
    fireEvent.click(within(within(section).getByRole('group', { name: 'Xác nhận quyền lợi Gói 10 buổi gội đầu' })).getByRole('button', { name: 'Ghi thành quyền lợi' }));
    await within(section).findByText('Đã ghi quyền lợi Gói 10 buổi gội đầu.');
    expect(await within(panel).findByText('Gói 10 buổi gội đầu')).toBeTruthy();
    expect(loads('/staff/benefits?')).toBe(2);
    expect((within(panel).getByLabelText('Tên quyền lợi') as HTMLInputElement).value).toBe('Gói đang gõ');

    fireEvent.click(within(card).getByRole('button', { name: 'Xem các buổi làm đã ghi' }));
    const vpanel = within(card).getByRole('group', { name: 'Các buổi làm đã ghi' });
    await within(vpanel).findByText('Chưa có buổi làm nào được ghi cho khách này.');
    fireEvent.click(within(section).getByRole('button', { name: 'Xác nhận lần đến ngày 17/10/2026' }));
    fireEvent.click(within(within(section).getByRole('group', { name: 'Xác nhận lần đến ngày 17/10/2026' })).getByRole('button', { name: 'Ghi thành buổi làm' }));
    await within(section).findByText(/^Đã ghi lần đến ngày 17\/10\/2026/);
    expect(await within(vpanel).findByText('Gội đầu thư giãn')).toBeTruthy();
    expect(within(vpanel).queryByText('Chưa có buổi làm nào được ghi cho khách này.')).toBeNull();
  });
});
