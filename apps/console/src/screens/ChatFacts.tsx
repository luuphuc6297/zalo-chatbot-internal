// Facts guessed from old chat (chat-facts contract, section 15.13): the markers on the figures of the customer summary
// and the section "Suy ra từ tin nhắn cũ" of the same card, where staff confirm a guess (it becomes a recorded visit or
// benefit) or dismiss it (the next analyzer run does not bring it back).
// The section is loaded only when the summary carries the `chat` field (a server that knows section 15), so a summary
// without it renders exactly as before. Service names, technicians and benefit titles come from old chat: they are
// rendered as React text only. The suggested phone number stays masked until staff click "Hiện số".
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  Api,
  ChatBenefitConfirmRequest,
  ChatBenefitView,
  ChatConfidence,
  ChatFacts,
  ChatVisitConfirmRequest,
  ChatVisitService,
  ChatVisitView,
  CustomerSummary,
} from '../api';
import { ApiError } from '../api';
import { chatFactsGapText, errorText, migration0010Text, migration0011Text } from '../errors';
import { useAction } from '../hooks';
import {
  BENEFIT_KIND_LABEL,
  CHAT_AMOUNT_SOURCE_LABEL,
  CHAT_CONFIDENCE_LABEL,
  CHAT_SECTION_TITLE,
  CHAT_STATED_BY_LABEL,
  CHAT_STATE_LABEL,
  fmtDate,
  fmtTime,
  fmtVnd,
  fmtYmd,
  maskPhone,
  msToVnLocal,
  parseVnd,
  vnDateEndMs,
  vnLocalToMs,
  vndInputText,
} from '../labels';
import { SERVICES } from '../services';
import { TECHNICIAN_MAX } from './VisitFields';
import { ErrorLine, Notice } from './common';

/** Chat facts are keyed by 'p:' + 1 to 32 digits; the server answers 404 for any other id, so the console does not ask. */
export const CHAT_FACTS_ID_RE = /^p:\d{1,32}$/;

const YMD_RE = /^\d{4}-\d{2}-\d{2}$/;
const HM_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const BENEFIT_TITLE_MAX = 120;
/** The server refuses a benefit total above this (MAX_BENEFIT_COUNT of apps/server/src/staff-api/customers.ts). */
export const BENEFIT_COUNT_MAX = 1000;
/** The server refuses a visit time more than this after now. */
const FUTURE_SLACK_MS = 3_600_000;
/** Active guessed visits shown before "Hiện thêm". */
export const CHAT_VISIBLE_VISITS = 10;

const isNum = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

// ---------------------------------------------------------------- loading

export interface ChatFactsLoad {
  facts: ChatFacts | null;
  loaded: boolean;
  /** One calm sentence for a 404 (older server) or a 409 naming migration 0011; null otherwise. */
  gap: string | null;
  /** Any other failure (network, 401, 500). */
  error: string | null;
  reload: () => void;
}

type LoadState = Omit<ChatFactsLoad, 'reload'>;
const NOT_LOADED: LoadState = { facts: null, loaded: false, gap: null, error: null };

/**
 * GET /staff/chat-facts/:zalo_user_id once when mounted, again when `key` changes (a new analyzer run) and on reload().
 * A null id loads nothing. The card re-renders on every poll of the conversation; this hook does not refetch then.
 */
export function useChatFacts(api: Api, zaloUserId: string | null, key: string | number | null): ChatFactsLoad {
  const [state, setState] = useState<LoadState>(NOT_LOADED);
  const [tick, setTick] = useState(0);
  const apiRef = useRef(api);
  apiRef.current = api;

  useEffect(() => {
    if (!zaloUserId) {
      setState((s) => (s === NOT_LOADED ? s : NOT_LOADED));
      return;
    }
    let alive = true;
    apiRef.current
      .getChatFacts(zaloUserId)
      .then((r) => {
        if (!alive) return;
        const facts = r && typeof r === 'object' && r.facts && typeof r.facts === 'object' ? r.facts : null;
        setState({ facts, loaded: true, gap: null, error: null });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        const gap = chatFactsGapText(e, 'tải được dữ liệu suy ra từ tin nhắn cũ');
        // a 404 or 409 means the server has no chat facts to give: drop what was shown before
        setState((s) => (gap ? { facts: null, loaded: true, gap, error: null } : { ...s, loaded: true, error: errorText(e) }));
      });
    return () => {
      alive = false;
    };
  }, [zaloUserId, key, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

// ---------------------------------------------------------------- reading a row (leniently: the server was built in parallel)

/** 'YYYY-MM-DD' of a guessed visit or booking, Vietnam time; '' when the row carries no usable date. */
export function chatRowDate(v: ChatVisitView): string {
  if (typeof v.local_date === 'string' && YMD_RE.test(v.local_date)) return v.local_date;
  const loose = (v as { date?: unknown }).date;
  if (typeof loose === 'string' && YMD_RE.test(loose)) return loose;
  return isNum(v.visited_at) ? msToVnLocal(v.visited_at).slice(0, 10) : '';
}

/** 'HH:MM' when the chat gave a time; null when it did not (the stored 12:00 is not a real time). */
export function chatRowTime(v: ChatVisitView): string | null {
  if (typeof v.time === 'string' && HM_RE.test(v.time)) return v.time;
  if (v.time_known && isNum(v.visited_at)) return msToVnLocal(v.visited_at).slice(11, 16);
  return null;
}

export function chatRowServices(v: ChatVisitView): ChatVisitService[] {
  let list: unknown = v.services ?? (v as { services_json?: unknown }).services_json;
  if (typeof list === 'string') {
    try {
      list = JSON.parse(list);
    } catch {
      list = [];
    }
  }
  return Array.isArray(list) ? list.filter((s): s is ChatVisitService => !!s && typeof s === 'object') : [];
}

/** The server's catalog name, else the name of the list shipped with the console, else the keyword the chat used. */
export function chatServiceName(s: ChatVisitService): string {
  const server = typeof s.name === 'string' && s.name && s.name !== s.service_id ? s.name : '';
  const bundled = s.service_id ? SERVICES.find((x) => x.id === s.service_id)?.name : undefined;
  return server || bundled || s.service_name || s.service_id || '';
}

function confidenceText(c: ChatVisitView['confidence']): string | null {
  if (!c) return null;
  const label = CHAT_CONFIDENCE_LABEL[c as ChatConfidence] ?? String(c);
  return c === 'low' ? `${label}, không tính vào số lần đến` : label;
}

/** "17/10/2026 lúc 15:00 · Massage chân · 350.000đ (đã trả) · kỹ thuật viên Lan · chắc". */
export function chatVisitText(v: ChatVisitView): string {
  const date = chatRowDate(v);
  const time = chatRowTime(v);
  const day = date ? fmtYmd(date) : 'chưa rõ ngày';
  const names = chatRowServices(v).map(chatServiceName).filter(Boolean);
  const source = v.amount_source ? (CHAT_AMOUNT_SOURCE_LABEL[v.amount_source] ?? v.amount_source) : '';
  const parts = [
    time ? `${day} lúc ${time}` : `${day}, chưa rõ giờ`,
    names.length > 0 ? names.join(', ') : 'chưa rõ dịch vụ',
    isNum(v.amount_vnd) ? `${fmtVnd(v.amount_vnd)}${source ? ` (${source})` : ''}` : 'chưa rõ số tiền',
    v.technician ? `kỹ thuật viên ${v.technician}` : 'chưa rõ kỹ thuật viên',
  ];
  const confidence = confidenceText(v.confidence);
  if (confidence) parts.push(confidence);
  return parts.join(' · ');
}

/** "Gói 10 buổi (gói nhiều buổi) · tổng 10 lần, còn 7 lần · theo tin studio nhắn ngày 17/10/2026 · chắc". */
export function chatBenefitText(b: ChatBenefitView): string {
  const total = isNum(b.total_count) ? b.total_count : null;
  const left = isNum(b.remaining) ? b.remaining : null;
  let counts: string;
  if (total !== null && left !== null) counts = `tổng ${total} lần, còn ${left} lần`;
  else if (total !== null) counts = `tổng ${total} lần, chưa rõ còn bao nhiêu`;
  else if (left !== null) counts = `còn ${left} lần, chưa rõ tổng số lần`;
  else counts = 'chưa rõ số lần';
  const parts = [`${b.title} (${BENEFIT_KIND_LABEL[b.kind] ?? b.kind})`, counts];
  if (b.stated_by && CHAT_STATED_BY_LABEL[b.stated_by]) {
    parts.push(`${CHAT_STATED_BY_LABEL[b.stated_by]}${isNum(b.stated_at) ? ` ngày ${fmtDate(b.stated_at)}` : ''}`);
  }
  if (b.confidence) parts.push(CHAT_CONFIDENCE_LABEL[b.confidence] ?? b.confidence);
  return parts.join(' · ');
}

/** "đã xác nhận ngày 12/11/2026" or "đã bỏ". */
export function chatDecisionText(row: { state: ChatVisitView['state']; decided_at?: number | null }): string {
  const label = CHAT_STATE_LABEL[row.state] ?? row.state;
  return isNum(row.decided_at) ? `${label} ngày ${fmtDate(row.decided_at)}` : label;
}

/** Under a guessed visit whose date already has a recorded visit (`recorded_day` of the server). */
export const RECORDED_DAY_TEXT = 'Ngày này đã có buổi làm được ghi, nên lần đến suy ra này không được tính và không cần xác nhận. Bỏ dòng này nếu đó là cùng một lần đến.';
/** Under a guessed benefit whose title an active benefit of the customer already has (`recorded_title`). */
export const RECORDED_TITLE_TEXT = 'Khách đã có quyền lợi cùng tên. Nếu đây là một gói khác, đổi tên khi xác nhận; nếu là cùng gói, bỏ dòng này.';

const visitNoun = (v: ChatVisitView) => `${v.kind === 'upcoming' ? 'lịch hẹn' : 'lần đến'} ngày ${fmtYmd(chatRowDate(v)) || 'chưa rõ'}`;

// ---------------------------------------------------------------- markers on the summary figures

/** How many guesses a figure includes; `atMost` when the console cannot tell the exact number (see chatMarkers). */
export interface ChatFigureMarker {
  n: number;
  atMost: boolean;
}

export interface ChatMarkers {
  /** Guesses counted in visits_total: `chat.visits_counted` of the summary, exact. */
  visits: number;
  /** The last visit day is a guess. */
  lastVisit: boolean;
  window: ChatFigureMarker | null;
  spend: ChatFigureMarker | null;
  windowSpend: ChatFigureMarker | null;
}

/**
 * Which figures of the summary include guesses. `visits` and `lastVisit` come from the summary itself. The summary does
 * not say how many guesses fall in the window or carry a paid amount, so the console counts them in the loaded facts:
 * active rows of kind visit with confidence high or medium (the rows 15.12 counts), less the day of a recorded last
 * visit. The server also skips a guess on any other day that has a recorded visit, which the console cannot see; when
 * the list holds more such rows than `visits_counted`, a figure gets the largest possible number with `atMost`.
 * Without facts (still loading, or the load failed) only `visits` and `lastVisit` are given.
 */
export function chatMarkers(s: CustomerSummary, facts: ChatFacts | null): ChatMarkers {
  const raw = s.chat?.visits_counted;
  const counted = isNum(raw) && raw > 0 ? Math.floor(raw) : 0;
  const out: ChatMarkers = { visits: counted, lastVisit: s.last_visit?.from_chat === true, window: null, spend: null, windowSpend: null };
  if (counted === 0 || !facts) return out;

  const recordedDay = s.last_visit && s.last_visit.from_chat !== true && s.last_visit.date ? s.last_visit.date : null;
  const guesses = (facts.visits ?? []).filter(
    (v) => v.state === 'active' && v.kind !== 'upcoming' && (v.confidence === 'high' || v.confidence === 'medium') && chatRowDate(v) !== recordedDay,
  );
  const extra = guesses.length - counted; // guesses on a day with a recorded visit the console cannot see
  if (extra < 0) return out; // the list is older than the summary: no number rather than a wrong one

  const bound = (x: number, cap: number): ChatFigureMarker | null => {
    const hi = Math.min(x, counted, cap);
    if (hi <= 0) return null;
    const lo = Math.min(Math.max(0, x - extra), hi);
    return { n: hi, atMost: lo < hi };
  };
  const from = s.window?.from_date;
  const inWindow = (v: ChatVisitView) => !!from && chatRowDate(v) >= from;
  const paid = (v: ChatVisitView) => v.amount_source === 'paid' && isNum(v.amount_vnd);
  const windowVisits = s.window?.visits;
  out.window = from ? bound(guesses.filter(inWindow).length, isNum(windowVisits) ? windowVisits : Infinity) : null;
  out.spend = bound(guesses.filter(paid).length, isNum(s.lifetime_spend_visits) ? s.lifetime_spend_visits : Infinity);
  out.windowSpend = from && out.window ? bound(guesses.filter((v) => inWindow(v) && paid(v)).length, out.window.n) : null;
  return out;
}

// ---------------------------------------------------------------- confirm a guessed visit

export interface VisitConfirmForm {
  serviceId: string;
  date: string; // 'YYYY-MM-DD'
  time: string; // 'HH:MM' or '' (not known)
  amount: string; // as shown in the field, e.g. "350.000"
  technician: string;
}

/** The guessed amount the customer paid: only an amount whose source is 'paid' (a quote or a list price is not one). */
const paidAmount = (v: ChatVisitView): number | null => (v.amount_source === 'paid' && isNum(v.amount_vnd) ? Math.round(v.amount_vnd) : null);

/**
 * The form opens with the guess: its first catalog service, its day and time, technician, and the amount only when the
 * chat shows the customer paid it. A quoted or list price is shown as a hint next to an empty field: the server records
 * it only when staff type it (section 15.11 after the review of 2026-11-12).
 */
export function visitConfirmInitial(v: ChatVisitView): VisitConfirmForm {
  const first = chatRowServices(v).find((s) => typeof s.service_id === 'string' && s.service_id);
  const paid = paidAmount(v);
  return {
    serviceId: first?.service_id ?? '',
    date: chatRowDate(v),
    time: chatRowTime(v) ?? '',
    amount: paid !== null ? vndInputText(String(paid)) : '',
    technician: v.technician ?? '',
  };
}

export function visitConfirmProblem(f: VisitConfirmForm, v: ChatVisitView, now = Date.now()): string | null {
  if (!f.serviceId.trim() && chatRowServices(v).length === 0) return 'Chọn dịch vụ khách đã làm.';
  if (!YMD_RE.test(f.date) || !Number.isFinite(vnLocalToMs(`${f.date}T12:00`))) return 'Chọn ngày khách đến.';
  if (f.time.trim() !== '' && !HM_RE.test(f.time.trim())) return 'Giờ đến viết theo dạng 15:30, hoặc để trống nếu chưa rõ.';
  // the server refuses a visit more than one hour ahead; an unknown time is recorded at 12:00
  if (vnLocalToMs(`${f.date}T${f.time.trim() || '12:00'}`) > now + FUTURE_SLACK_MS) {
    if (f.date > msToVnLocal(now).slice(0, 10)) return 'Ngày đến chưa tới. Chỉ ghi buổi khách đã làm.';
    return f.time.trim() ? 'Giờ đến chưa tới. Chỉ ghi buổi khách đã làm.' : 'Chưa rõ giờ thì buổi làm được ghi lúc 12:00, mà hôm nay chưa tới giờ đó. Nhập giờ khách đã đến.';
  }
  if (f.amount.trim() !== '' && parseVnd(f.amount) === null) return 'Số tiền quá lớn hoặc không phải số.';
  const technician = f.technician.trim();
  if (technician.length > TECHNICIAN_MAX || /[\r\n]/.test(technician)) return `Tên kỹ thuật viên viết trên một dòng, tối đa ${TECHNICIAN_MAX} ký tự.`;
  return null;
}

/**
 * Body of the confirm call: only what staff changed, since the server records the guessed value of every field left out
 * (the amount only when it was paid). An emptied amount or technician is sent as null; an amount typed next to a quoted
 * or list price is sent. An emptied time records 12:00, like a guess without a time.
 */
export function visitConfirmBody(f: VisitConfirmForm, v: ChatVisitView): ChatVisitConfirmRequest {
  const initial = visitConfirmInitial(v);
  const body: ChatVisitConfirmRequest = {};
  const serviceId = f.serviceId.trim();
  if (serviceId && serviceId !== initial.serviceId) body.service_id = serviceId;
  const time = f.time.trim();
  if (f.date !== initial.date || time !== initial.time) body.visited_at_local = `${f.date} ${time || '12:00'}`;
  // left out, the server records the guessed amount only when it was paid; typed, it records what staff typed
  const amount = f.amount.trim() === '' ? null : parseVnd(f.amount);
  if (amount !== paidAmount(v)) body.amount_vnd = amount;
  const technician = f.technician.trim() || null;
  if (technician !== (v.technician?.trim() || null)) body.technician = technician;
  return body;
}

/** The sentence next to the amount field when the chat names an amount that is not known to be paid; null otherwise. */
export function unpaidAmountHint(v: ChatVisitView): string | null {
  if (!isNum(v.amount_vnd) || v.amount_source === 'paid') return null;
  const amount = fmtVnd(v.amount_vnd);
  const ask = 'Nhập số tiền nếu khách đã trả.';
  if (v.amount_source === 'quoted') return `Tin nhắn có báo giá ${amount}, chưa chắc là số khách đã trả. ${ask}`;
  if (v.amount_source === 'list_price') return `Giá niêm yết của dịch vụ là ${amount}, chưa chắc là số khách đã trả. ${ask}`;
  return `Tin nhắn có số tiền ${amount}, chưa rõ khách đã trả hay chưa. ${ask}`;
}

function VisitConfirmPanel(props: { v: ChatVisitView; busy: boolean; onSubmit: (body: ChatVisitConfirmRequest) => void; onClose: () => void }) {
  const { v, busy, onSubmit, onClose } = props;
  const [form, setForm] = useState<VisitConfirmForm>(() => visitConfirmInitial(v));
  const problem = visitConfirmProblem(form, v);
  const services = chatRowServices(v);
  const guessed = services.find((s) => s.service_id) ?? services[0];
  const listId = `chat-service-options-${v.id}`;
  const amountHint = unpaidAmountHint(v);
  const set = (patch: Partial<VisitConfirmForm>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <div className="form chat-confirm" role="group" aria-label={`Xác nhận ${visitNoun(v)}`}>
      <p className="muted small">
        Sửa nếu cần, rồi ghi thành buổi làm của khách. Máy chủ không hẹn tin cảm ơn hay tin hỏi thăm cho buổi làm này.
      </p>
      <label>
        Dịch vụ
        <input
          list={listId}
          autoComplete="off"
          placeholder="Chọn hoặc gõ mã dịch vụ"
          value={form.serviceId}
          disabled={busy}
          onChange={(e) => set({ serviceId: e.target.value })}
        />
        <datalist id={listId}>
          {SERVICES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </datalist>
        {form.serviceId.trim() ? (
          <span className="muted small">{SERVICES.find((s) => s.id === form.serviceId.trim())?.name ?? 'Mã không có trong danh sách đi kèm'}</span>
        ) : guessed ? (
          <span className="muted small">Để trống thì máy chủ ghi dịch vụ suy ra từ tin nhắn: {chatServiceName(guessed)}.</span>
        ) : null}
      </label>
      <label>
        Ngày đến
        <input type="date" value={form.date} disabled={busy} onChange={(e) => set({ date: e.target.value })} />
      </label>
      <label>
        Giờ đến (để trống nếu chưa rõ)
        <input type="time" value={form.time} disabled={busy} onChange={(e) => set({ time: e.target.value })} />
        {!form.time.trim() && <span className="muted small">Chưa rõ giờ thì buổi làm được ghi lúc 12:00.</span>}
      </label>
      <label>
        Số tiền khách trả (đồng, không bắt buộc)
        <input
          inputMode="numeric"
          autoComplete="off"
          placeholder="350.000"
          value={form.amount}
          disabled={busy}
          onChange={(e) => set({ amount: vndInputText(e.target.value) })}
        />
        {amountHint && <span className="muted small">{amountHint}</span>}
      </label>
      <label>
        Kỹ thuật viên (không bắt buộc)
        <input
          maxLength={TECHNICIAN_MAX}
          autoComplete="off"
          value={form.technician}
          disabled={busy}
          onChange={(e) => set({ technician: e.target.value })}
        />
      </label>
      {problem && <p className="error">{problem}</p>}
      <div className="actions">
        <button disabled={busy || problem !== null} onClick={() => onSubmit(visitConfirmBody(form, v))}>
          Ghi thành buổi làm
        </button>
        <button className="secondary" disabled={busy} onClick={onClose}>
          Đóng
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- confirm a guessed benefit

export interface BenefitConfirmForm {
  title: string;
  total: string;
  used: string | null; // null: not touched, the field shows the default
  expires: string; // 'YYYY-MM-DD' or ''
}

export function benefitConfirmInitial(b: ChatBenefitView): BenefitConfirmForm {
  return { title: b.title, total: isNum(b.total_count) ? String(b.total_count) : '', used: null, expires: '' };
}

/**
 * Uses already taken: what staff typed; else total minus the remaining count the chat stated; else 0 when the chat
 * states no remaining count. Empty when the chat states more uses left than the total: staff must say how many were used.
 */
export function benefitConfirmUsed(f: BenefitConfirmForm, b: ChatBenefitView): string {
  if (f.used !== null) return f.used;
  if (!isNum(b.remaining)) return '0';
  const total = f.total.trim();
  if (/^\d+$/.test(total) && b.remaining <= Number(total)) return String(Number(total) - b.remaining);
  return '';
}

/** The default uses come from the remaining count the chat states (the note under the field says so). */
const usedFromChat = (f: BenefitConfirmForm, b: ChatBenefitView) => f.used === null && isNum(b.remaining) && benefitConfirmUsed(f, b) !== '';

export function benefitConfirmProblem(f: BenefitConfirmForm, b: ChatBenefitView): string | null {
  const title = f.title.trim();
  if (!title) return 'Nhập tên quyền lợi.';
  if (title.length > BENEFIT_TITLE_MAX || /[\r\n]/.test(title)) return `Tên quyền lợi viết trên một dòng, tối đa ${BENEFIT_TITLE_MAX} ký tự.`;
  const total = f.total.trim();
  if (!/^\d+$/.test(total) || Number(total) <= 0 || !Number.isSafeInteger(Number(total))) return 'Tổng số lần là số nguyên lớn hơn 0.';
  if (Number(total) > BENEFIT_COUNT_MAX) return `Tổng số lần tối đa ${BENEFIT_COUNT_MAX}.`;
  if (f.used === null && isNum(b.remaining) && b.remaining > Number(total)) {
    return `Tin nhắn nói còn ${b.remaining} lần, nhiều hơn tổng số lần: nhập số lần đã dùng.`;
  }
  const used = benefitConfirmUsed(f, b).trim();
  if (!/^\d+$/.test(used) || Number(used) > Number(total)) return 'Số lần đã dùng là số nguyên từ 0 đến tổng số lần.';
  if (f.expires !== '' && !Number.isFinite(vnDateEndMs(f.expires))) return 'Hạn dùng không phải ngày hợp lệ.';
  return null;
}

/** total_count and used_count are always sent; the title only when staff changed it; the expiry only when set. */
export function benefitConfirmBody(f: BenefitConfirmForm, b: ChatBenefitView): ChatBenefitConfirmRequest {
  const body: ChatBenefitConfirmRequest = { total_count: Number(f.total.trim()), used_count: Number(benefitConfirmUsed(f, b).trim()) };
  const title = f.title.trim();
  if (title !== b.title.trim()) body.title = title;
  if (f.expires !== '') body.expires_at = vnDateEndMs(f.expires);
  return body;
}

function BenefitConfirmPanel(props: { b: ChatBenefitView; busy: boolean; onSubmit: (body: ChatBenefitConfirmRequest) => void; onClose: () => void }) {
  const { b, busy, onSubmit, onClose } = props;
  const [form, setForm] = useState<BenefitConfirmForm>(() => benefitConfirmInitial(b));
  const problem = benefitConfirmProblem(form, b);
  const set = (patch: Partial<BenefitConfirmForm>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <div className="form chat-confirm" role="group" aria-label={`Xác nhận quyền lợi ${b.title}`}>
      <p className="muted small">Sửa nếu cần, rồi ghi thành quyền lợi của khách.</p>
      <label>
        Tên quyền lợi
        <input maxLength={BENEFIT_TITLE_MAX} autoComplete="off" value={form.title} disabled={busy} onChange={(e) => set({ title: e.target.value })} />
      </label>
      <label>
        Tổng số lần
        <input inputMode="numeric" autoComplete="off" value={form.total} disabled={busy} onChange={(e) => set({ total: e.target.value })} />
        {!isNum(b.total_count) && <span className="muted small">Tin nhắn không nói tổng số lần, cần nhập.</span>}
      </label>
      <label>
        Số lần đã dùng
        <input
          inputMode="numeric"
          autoComplete="off"
          value={benefitConfirmUsed(form, b)}
          disabled={busy}
          onChange={(e) => set({ used: e.target.value })}
        />
        {usedFromChat(form, b) && <span className="muted small">Tính từ {b.remaining} lần còn lại mà tin nhắn nêu.</span>}
      </label>
      <label>
        Hạn dùng (không bắt buộc)
        <input type="date" value={form.expires} disabled={busy} onChange={(e) => set({ expires: e.target.value })} />
      </label>
      {problem && <p className="error">{problem}</p>}
      <div className="actions">
        <button disabled={busy || problem !== null} onClick={() => onSubmit(benefitConfirmBody(form, b))}>
          Ghi thành quyền lợi
        </button>
        <button className="secondary" disabled={busy} onClick={onClose}>
          Đóng
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the section

function DismissBox(props: { label: string; question: string; yes: string; busy: boolean; onYes: () => void; onNo: () => void }) {
  const { label, question, yes, busy, onYes, onNo } = props;
  return (
    <div className="confirm-box" role="group" aria-label={label}>
      <p>{question}</p>
      <div className="actions">
        <button className="danger" disabled={busy} onClick={onYes}>
          {yes}
        </button>
        <button className="secondary" disabled={busy} onClick={onNo}>
          Giữ lại
        </button>
      </div>
    </div>
  );
}

/** The label of the form field a 422 of a decision names (`details.field` of the server), as staff read it. */
export const CHAT_FIELD_LABEL: Record<string, string> = {
  visited_at_local: 'Ngày đến hoặc Giờ đến',
  service_id: 'Dịch vụ',
  amount_vnd: 'Số tiền khách trả',
  technician: 'Kỹ thuật viên',
  total_count: 'Tổng số lần',
  used_count: 'Số lần đã dùng',
  title: 'Tên quyền lợi',
  expires_at: 'Hạn dùng',
};

/** Which phone decision failed: "Dùng số này" or "Bỏ"; null for a visit or a benefit. */
export type PhoneAction = 'accept' | 'dismiss' | null;

/**
 * Error line of a failed decision: a missing migration, a row the server no longer has, a value the server refuses
 * (422, named by the field label), and each 409 the server answers, told apart by its message: a row already decided,
 * a missing customer row, a day that already has a recorded visit, a benefit title the customer already has, and for
 * the phone suggestion a phone the customer already has, a number another customer holds, or a suggestion already
 * used or dismissed elsewhere.
 */
export function chatDecisionErrorText(raw: unknown, fallback: string | null, what: string, phone: PhoneAction): string | null {
  const migration = migration0011Text(raw, what) ?? migration0010Text(raw, what);
  if (migration) return migration;
  if (!(raw instanceof ApiError)) return fallback;
  if (raw.status === 404) return `Máy chủ không còn dòng này, nên chưa ${what}. Có thể lần phân tích mới đã thay danh sách; danh sách đã được tải lại.`;
  if (raw.status === 422) {
    const field = typeof raw.details?.field === 'string' ? CHAT_FIELD_LABEL[raw.details.field] : undefined;
    return field ? `Máy chủ không nhận giá trị ở ô ${field}, nên chưa ${what}. Sửa ô đó rồi làm lại.` : `Máy chủ không nhận dữ liệu của biểu mẫu, nên chưa ${what}.`;
  }
  if (raw.status === 409) {
    const m = raw.message;
    if (/chưa có hồ sơ|no customer/i.test(m)) return `Khách chưa có hồ sơ khách hàng trên máy chủ, nên chưa ${what}.`;
    if (phone) {
      if (/already has a phone/i.test(m)) return 'Khách đã có số điện thoại nên máy chủ không dùng số gợi ý. Nếu số gợi ý đúng hơn, sửa ở dòng Số điện thoại phía trên.';
      if (/another customer/i.test(m)) return 'Số này đang là số điện thoại của một khách khác, nên máy chủ không dùng số này cho khách này.';
      return 'Số gợi ý đã được xử lý trước đó (đã dùng hoặc đã bỏ). Danh sách đã được tải lại.';
    }
    if (/already recorded on this date/i.test(m)) return `Ngày này đã có buổi làm được ghi cho khách, nên chưa ${what}. Nếu đó là cùng một lần đến, bỏ dòng này.`;
    if (/already has a benefit with this title/i.test(m)) return `Khách đã có quyền lợi cùng tên, nên chưa ${what}. Nếu đây là một gói khác, đổi tên quyền lợi rồi xác nhận lại.`;
    return `Dòng này đã được xử lý trước đó, nên chưa ${what}. Danh sách đã được tải lại.`;
  }
  return fallback;
}

type Open =
  | { what: 'confirm-visit' | 'dismiss-visit' | 'confirm-benefit' | 'dismiss-benefit'; id: string }
  | { what: 'dismiss-phone' };

const byDateDesc = (a: ChatVisitView, b: ChatVisitView) => chatRowDate(b).localeCompare(chatRowDate(a));
const byDateAsc = (a: ChatVisitView, b: ChatVisitView) => chatRowDate(a).localeCompare(chatRowDate(b));

export function ChatFactsSection(props: { api: Api; zaloUserId: string; load: ChatFactsLoad; onSaved: () => void }) {
  const { api, zaloUserId, load, onSaved } = props;
  const act = useAction();
  const [open, setOpen] = useState<Open | null>(null);
  const [allVisits, setAllVisits] = useState(false);
  const [phoneShown, setPhoneShown] = useState(false);
  // the last decision: what it would have done (for the error sentence) and the row it was about ('phone' for the number)
  const [last, setLast] = useState<{ what: string; phone: PhoneAction; key: string }>({ what: 'lưu được', phone: null, key: '' });

  if (!load.facts && !load.gap && !load.error) return null;

  const f = load.facts;
  const visits = [...(f?.visits ?? [])].sort(byDateDesc);
  const upcoming = [...(f?.upcoming ?? [])].sort(byDateAsc);
  const today = msToVnLocal(Date.now()).slice(0, 10);
  const benefits = f?.benefits ?? [];
  const activeVisits = visits.filter((v) => v.state === 'active');
  const shownVisits = allVisits ? activeVisits : activeVisits.slice(0, CHAT_VISIBLE_VISITS);
  // An active booking whose date has passed waits for the next analyzer run (it becomes a guessed visit or goes away),
  // like the summary's upcoming_next, which keeps only today and later.
  const activeUpcoming = upcoming.filter((v) => v.state === 'active' && chatRowDate(v) >= today);
  const pastUpcoming = upcoming.filter((v) => v.state === 'active' && chatRowDate(v) < today);
  const activeBenefits = benefits.filter((b) => b.state === 'active');
  const decidedRows = [...visits, ...upcoming].filter((v) => v.state !== 'active');
  const decidedBenefits = benefits.filter((b) => b.state !== 'active');
  const decidedCount = decidedRows.length + decidedBenefits.length;
  const phone = typeof f?.phone_suggestion === 'string' && f.phone_suggestion.trim() ? f.phone_suggestion.trim() : null;
  const nothingActive = activeVisits.length === 0 && activeUpcoming.length === 0 && activeBenefits.length === 0 && !phone;
  const isOpen = (what: Open['what'], id?: string) => open?.what === what && (id === undefined || ('id' in open && open.id === id));

  // One decision at a time. A 404, or a 409 other than a missing migration, means the list on screen is out of date,
  // so it is loaded again.
  const decide = async <T,>(fn: () => Promise<T>, ok: string, what: string, key: string, phone: PhoneAction = null) => {
    setLast({ what, phone, key });
    const r = await act.run(async () => {
      try {
        return await fn();
      } catch (e) {
        const migration = migration0011Text(e, what) ?? migration0010Text(e, what);
        if (e instanceof ApiError && (e.status === 404 || (e.status === 409 && !migration))) load.reload();
        throw e;
      }
    }, ok);
    if (r !== undefined) {
      setOpen(null);
      load.reload();
      onSaved();
    }
  };

  const generated = isNum(f?.generated_at) ? fmtTime(f.generated_at) : '';
  // the analyzer version is for whoever maintains the tool: a tooltip, not text for reception staff
  const version = f?.analyzer_version ? `Bản công cụ phân tích: ${f.analyzer_version}` : undefined;
  const model = f?.model_pass?.ran === true ? ', có dùng trợ lý AI đọc lại tin nhắn' : '';

  // A failed decision is explained in its own row, next to the open form; at the top when that row is gone.
  const decisionError = chatDecisionErrorText(act.raw, act.error, last.what, last.phone);
  const shownKeys = new Set<string>([...shownVisits, ...activeUpcoming, ...activeBenefits].map((x) => x.id));
  if (phone) shownKeys.add('phone');
  const rowError = (key: string) => (decisionError && last.key === key ? <ErrorLine text={decisionError} /> : null);

  return (
    <section className="chat-facts" aria-label={CHAT_SECTION_TITLE}>
      <h4>{CHAT_SECTION_TITLE}</h4>
      {load.gap && <p className="muted small">{load.gap}</p>}
      <ErrorLine text={load.error} />
      {decisionError && !shownKeys.has(last.key) && <ErrorLine text={decisionError} />}
      <Notice text={act.notice} />
      {f && (
        <>
          <p className="muted small">
            Công cụ phân tích đọc tin nhắn Zalo cũ và suy ra các dòng dưới đây bằng quy tắc, nên có thể sai. Xác nhận để ghi thành buổi làm
            hoặc quyền lợi; bỏ để lần phân tích sau không đưa lại dòng đó.
          </p>
          <p className="muted small">
            Lần đến chắc và khá chắc đang được tính vào số liệu phía trên, trừ ngày đã có buổi làm được ghi; số tiền chỉ được tính khi tin nhắn cho
            thấy khách đã trả. Lần đến chưa chắc và lịch hẹn không được tính.
          </p>
          {generated && (
            <p className="muted small" title={version}>
              Phân tích lúc {generated}
              {model}.
            </p>
          )}
          {nothingActive && <p className="muted small">Không còn dòng nào chờ xử lý.</p>}

          {activeVisits.length > 0 && (
            <div className="chat-group" role="group" aria-label="Lần đến suy ra từ tin nhắn">
              <h5>Lần đến</h5>
              <ul className="chat-list">
                {shownVisits.map((v) => (
                  <li key={v.id} className="chat-row">
                    <div>{chatVisitText(v)}</div>
                    {v.recorded_day === true && <p className="muted small">{RECORDED_DAY_TEXT}</p>}
                    <div className="actions">
                      {v.recorded_day !== true && (
                        <button
                          className="secondary"
                          aria-label={`Xác nhận ${visitNoun(v)}`}
                          aria-expanded={isOpen('confirm-visit', v.id)}
                          disabled={act.busy}
                          onClick={() => setOpen(isOpen('confirm-visit', v.id) ? null : { what: 'confirm-visit', id: v.id })}
                        >
                          Xác nhận
                        </button>
                      )}
                      <button className="secondary" aria-label={`Bỏ ${visitNoun(v)}`} disabled={act.busy} onClick={() => setOpen({ what: 'dismiss-visit', id: v.id })}>
                        Bỏ
                      </button>
                    </div>
                    {isOpen('confirm-visit', v.id) && v.recorded_day !== true && (
                      <VisitConfirmPanel
                        v={v}
                        busy={act.busy}
                        onClose={() => setOpen(null)}
                        onSubmit={(body) =>
                          void decide(
                            () => api.confirmChatVisit(v.id, body),
                            `Đã ghi ${visitNoun(v)} thành buổi làm. Không có tin hẹn giờ nào được tạo.`,
                            'ghi được buổi làm',
                            v.id,
                          )
                        }
                      />
                    )}
                    {isOpen('dismiss-visit', v.id) && (
                      <DismissBox
                        label={`Xác nhận bỏ ${visitNoun(v)}`}
                        question={`Bỏ ${visitNoun(v)}? Lần phân tích sau không đưa lại dòng này.`}
                        yes="Bỏ dòng này"
                        busy={act.busy}
                        onNo={() => setOpen(null)}
                        onYes={() => void decide(() => api.dismissChatVisit(v.id), `Đã bỏ ${visitNoun(v)}.`, 'bỏ được dòng này', v.id)}
                      />
                    )}
                    {rowError(v.id)}
                  </li>
                ))}
              </ul>
              {activeVisits.length > CHAT_VISIBLE_VISITS && (
                <div className="actions">
                  <button className="secondary small" onClick={() => setAllVisits(!allVisits)}>
                    {allVisits ? 'Thu gọn danh sách lần đến' : `Hiện thêm ${activeVisits.length - CHAT_VISIBLE_VISITS} lần đến`}
                  </button>
                </div>
              )}
            </div>
          )}

          {activeUpcoming.length > 0 && (
            <div className="chat-group" role="group" aria-label="Lịch hẹn suy ra từ tin nhắn">
              <h5>Lịch hẹn sắp tới</h5>
              <ul className="chat-list">
                {activeUpcoming.map((v) => (
                  <li key={v.id} className="chat-row">
                    <div>{chatVisitText(v)}</div>
                    <div className="actions">
                      <button className="secondary" aria-label={`Bỏ ${visitNoun(v)}`} disabled={act.busy} onClick={() => setOpen({ what: 'dismiss-visit', id: v.id })}>
                        Bỏ
                      </button>
                    </div>
                    {isOpen('dismiss-visit', v.id) && (
                      <DismissBox
                        label={`Xác nhận bỏ ${visitNoun(v)}`}
                        question={`Bỏ ${visitNoun(v)}? Lần phân tích sau không đưa lại lịch hẹn này, và không tính lần đến nào vào ngày đó.`}
                        yes="Bỏ dòng này"
                        busy={act.busy}
                        onNo={() => setOpen(null)}
                        onYes={() => void decide(() => api.dismissChatVisit(v.id), `Đã bỏ ${visitNoun(v)}.`, 'bỏ được dòng này', v.id)}
                      />
                    )}
                    {rowError(v.id)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {pastUpcoming.length > 0 && (
            <div className="chat-group" role="group" aria-label="Lịch hẹn đã qua ngày">
              <h5>Lịch hẹn đã qua ngày</h5>
              <p className="muted small">
                Lần phân tích sau sẽ đổi các lịch hẹn này thành lần đến suy ra từ tin nhắn, hoặc xóa đi nếu tin nhắn cho thấy lịch đã hủy hay khách không đến.
              </p>
              <ul className="chat-list">
                {pastUpcoming.map((v) => (
                  <li key={v.id} className="chat-row decided">
                    {chatVisitText(v)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {activeBenefits.length > 0 && (
            <div className="chat-group" role="group" aria-label="Quyền lợi suy ra từ tin nhắn">
              <h5>Quyền lợi (gói nhiều buổi, voucher)</h5>
              <ul className="chat-list">
                {activeBenefits.map((b) => (
                  <li key={b.id} className="chat-row">
                    <div>{chatBenefitText(b)}</div>
                    {b.recorded_title === true && <p className="muted small">{RECORDED_TITLE_TEXT}</p>}
                    <div className="actions">
                      <button
                        className="secondary"
                        aria-label={`Xác nhận quyền lợi ${b.title}`}
                        aria-expanded={isOpen('confirm-benefit', b.id)}
                        disabled={act.busy}
                        onClick={() => setOpen(isOpen('confirm-benefit', b.id) ? null : { what: 'confirm-benefit', id: b.id })}
                      >
                        Xác nhận
                      </button>
                      <button
                        className="secondary"
                        aria-label={`Bỏ quyền lợi ${b.title}`}
                        disabled={act.busy}
                        onClick={() => setOpen({ what: 'dismiss-benefit', id: b.id })}
                      >
                        Bỏ
                      </button>
                    </div>
                    {isOpen('confirm-benefit', b.id) && (
                      <BenefitConfirmPanel
                        b={b}
                        busy={act.busy}
                        onClose={() => setOpen(null)}
                        onSubmit={(body) =>
                          void decide(() => api.confirmChatBenefit(b.id, body), `Đã ghi quyền lợi ${body.title ?? b.title}.`, 'ghi được quyền lợi', b.id)
                        }
                      />
                    )}
                    {isOpen('dismiss-benefit', b.id) && (
                      <DismissBox
                        label={`Xác nhận bỏ quyền lợi ${b.title}`}
                        question={`Bỏ quyền lợi ${b.title}? Lần phân tích sau không đưa lại dòng này.`}
                        yes="Bỏ dòng này"
                        busy={act.busy}
                        onNo={() => setOpen(null)}
                        onYes={() => void decide(() => api.dismissChatBenefit(b.id), `Đã bỏ quyền lợi ${b.title}.`, 'bỏ được dòng này', b.id)}
                      />
                    )}
                    {rowError(b.id)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {phone && (
            <div className="chat-group" role="group" aria-label="Số điện thoại gợi ý">
              <h5>Số điện thoại gợi ý</h5>
              <div className="row wrap">
                <span className="chat-phone">{phoneShown ? phone : maskPhone(phone)}</span>
                <button className="secondary small" onClick={() => setPhoneShown(!phoneShown)}>
                  {phoneShown ? 'Ẩn số' : 'Hiện số'}
                </button>
              </div>
              {/* the server sends a suggestion only while the customer has no phone (GET /staff/chat-facts) */}
              <p className="muted small">Số này có trong tin nhắn cũ của khách nhưng chưa chắc là số điện thoại của khách.</p>
              <div className="actions">
                <button
                  disabled={act.busy}
                  onClick={() =>
                    void decide(() => api.acceptChatPhone(zaloUserId), 'Đã lưu số gợi ý làm số điện thoại của khách.', 'lưu được số điện thoại', 'phone', 'accept')
                  }
                >
                  Dùng số này
                </button>
                <button className="secondary" aria-label="Bỏ số gợi ý" disabled={act.busy} onClick={() => setOpen({ what: 'dismiss-phone' })}>
                  Bỏ
                </button>
              </div>
              {isOpen('dismiss-phone') && (
                <DismissBox
                  label="Xác nhận bỏ số gợi ý"
                  question="Bỏ số gợi ý? Số này sẽ không được gợi ý lại cho khách này."
                  yes="Bỏ số này"
                  busy={act.busy}
                  onNo={() => setOpen(null)}
                  onYes={() =>
                    void decide(() => api.dismissChatPhone(zaloUserId), 'Đã bỏ số gợi ý. Số này sẽ không được gợi ý lại.', 'bỏ được số gợi ý', 'phone', 'dismiss')
                  }
                />
              )}
              {rowError('phone')}
            </div>
          )}

          {decidedCount > 0 && (
            <details className="chat-decided">
              <summary>Đã xử lý ({decidedCount})</summary>
              <ul className="chat-list">
                {decidedRows.map((v) => (
                  <li key={v.id} className="chat-row decided">
                    {v.kind === 'upcoming' ? 'Lịch hẹn' : 'Lần đến'}: {chatVisitText(v)} · {chatDecisionText(v)}
                  </li>
                ))}
                {decidedBenefits.map((b) => (
                  <li key={b.id} className="chat-row decided">
                    Quyền lợi: {chatBenefitText(b)} · {chatDecisionText(b)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
