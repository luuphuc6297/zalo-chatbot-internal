// Customer summary block of a conversation (docs/contracts.md section 14.6) with the forms of section 14.5:
// edit the phone, record a visit, add / use / void a benefit, and the list of recorded visits.
// The block is mounted only when the detail carries `customer_summary`, so an older server shows nothing here.
// Section 15.13: figures that include guesses from old chat carry a short marker, and the section "Suy ra từ tin nhắn
// cũ" (screens/ChatFacts.tsx) closes the card; both appear only when the summary has the `chat` field.
// Names, titles and technician names are typed by staff or imported: rendered as React text nodes only, never as HTML.
import { useEffect, useRef, useState } from 'react';
import type { Api, BenefitCreateRequest, BenefitKind, CustomerBenefit, CustomerStatus, CustomerSummary, SummaryLastVisit, VisitView } from '../api';
import { errorText, serverGapText } from '../errors';
import { useAction } from '../hooks';
import {
  BENEFIT_KINDS,
  BENEFIT_KIND_LABEL,
  CUSTOMER_STATUS_LABEL,
  FROM_CHAT_TEXT,
  GAP_BASIS_LABEL,
  NO_VISIT_DATA_CHAT_TEXT,
  VISIT_SOURCE_LABEL,
  type BadgeKind,
  chatMarkerText,
  customerStatusReason,
  fmtDate,
  fmtTime,
  fmtVnd,
  fmtYmd,
  msToVnLocal,
  normalizePhone,
  vnDateEndMs,
  vnLocalToMs,
} from '../labels';
import { SERVICES } from '../services';
import { CHAT_FACTS_ID_RE, ChatFactsSection, type ChatFigureMarker, chatMarkers, useChatFacts } from './ChatFacts';
import {
  EMPTY_VISIT_EXTRAS,
  VisitExtraFields,
  benefitExpired,
  benefitRemaining,
  summaryBenefitText,
  visitErrorText,
  visitExtrasPayload,
  visitExtrasProblem,
} from './VisitFields';
import type { BenefitChoice, VisitExtras } from './VisitFields';
import { ErrorLine, Notice } from './common';

const STATUS_BADGE: Record<CustomerStatus, BadgeKind> = {
  first_inquiry: 'muted',
  first_visit_done: 'bot',
  returning: 'bot',
  long_absent: 'pending',
};

const isNum = (n: number | null | undefined): n is number => typeof n === 'number' && Number.isFinite(n);

/** True when at least one visit day is recorded for the customer. */
export function hasVisitData(s: CustomerSummary): boolean {
  return (isNum(s.visits_total) && s.visits_total > 0) || !!s.last_visit;
}

/** "Dịch vụ cuối cùng" line: services, day and time, technician, amount. */
export function lastVisitText(v: SummaryLastVisit): string {
  const names = (v.services ?? []).map((s) => s.name).filter(Boolean);
  const when = v.date ? `${fmtYmd(v.date)}${v.time ? ` lúc ${v.time}` : ''}` : fmtTime(v.visited_at);
  return [
    names.length > 0 ? names.join(', ') : 'chưa ghi tên dịch vụ',
    when,
    v.technician ? `kỹ thuật viên ${v.technician}` : 'chưa ghi kỹ thuật viên',
    isNum(v.amount_vnd) ? fmtVnd(v.amount_vnd) : 'chưa ghi số tiền',
  ].join(' · ');
}

/** "183 ngày gần nhất, từ 13/05/2026 đến hôm nay: 3 buổi". */
export function windowText(w: NonNullable<CustomerSummary['window']>): string {
  const from = w.from_date ? `, từ ${fmtYmd(w.from_date)} đến hôm nay` : '';
  const visits = isNum(w.visits) ? `: ${w.visits} buổi` : '';
  return `${w.days} ngày gần nhất${from}${visits}`;
}

/**
 * Loads once when mounted, again on reload() and again when `refresh` changes (a decision in the section "Suy ra từ tin
 * nhắn cũ" changed the list); a 404 or a "migration 0010" 409 becomes one calm sentence.
 */
function useLoad<T>(fn: () => Promise<T>, what: string, refresh = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    fnRef
      .current()
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (alive) setError(serverGapText(e, what) ?? errorText(e));
      });
    return () => {
      alive = false;
    };
  }, [tick, what, refresh]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

function ServiceOptions({ id }: { id: string }) {
  return (
    <datalist id={id}>
      {SERVICES.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </datalist>
  );
}

// ---------------------------------------------------------------- phone

function PhoneFact(props: { api: Api; customerId: string; phone: string | null; onSaved: () => void }) {
  const { api, customerId, phone, onSaved } = props;
  const act = useAction();
  const [text, setText] = useState<string | null>(null); // null = not editing

  const typed = (text ?? '').trim();
  const next = typed === '' ? null : normalizePhone(typed);
  const bad = text !== null && typed !== '' && next === null;
  const unchanged = text !== null && !bad && next === (phone ?? null);

  const save = async () => {
    if (text === null || bad || unchanged) return;
    const r = await act.run(() => api.patchCustomer(customerId, { phone: next }), next ? 'Đã lưu số điện thoại.' : 'Đã xóa số điện thoại.');
    if (r !== undefined) {
      setText(null);
      onSaved();
    }
  };

  return (
    <>
      {text === null ? (
        <span className="row wrap">
          <span>{phone || 'chưa có'}</span>
          <button className="secondary small" disabled={act.busy} onClick={() => setText(phone ?? '')}>
            Sửa số điện thoại
          </button>
        </span>
      ) : (
        <span className="row wrap">
          <input
            aria-label="Số điện thoại"
            inputMode="tel"
            autoComplete="off"
            placeholder="0901234567"
            value={text}
            disabled={act.busy}
            onChange={(e) => setText(e.target.value)}
          />
          <button disabled={act.busy || bad || unchanged} onClick={save}>
            Lưu số điện thoại
          </button>
          <button className="secondary" disabled={act.busy} onClick={() => setText(null)}>
            Hủy sửa số điện thoại
          </button>
        </span>
      )}
      {bad && <p className="error">Số điện thoại gồm 9 đến 11 chữ số, ví dụ 0901234567. Để trống nếu muốn xóa số.</p>}
      <ErrorLine text={serverGapText(act.raw, 'lưu được số điện thoại') ?? act.error} />
      <Notice text={act.notice} />
    </>
  );
}

// ---------------------------------------------------------------- record a visit

function VisitPanel(props: { api: Api; customerId: string; benefits: BenefitChoice[]; onSaved: () => void }) {
  const { api, customerId, benefits, onSaved } = props;
  const act = useAction();
  const [serviceId, setServiceId] = useState('');
  const [visitedAt, setVisitedAt] = useState(() => msToVnLocal(Date.now()));
  const [extras, setExtras] = useState<VisitExtras>(EMPTY_VISIT_EXTRAS);
  const [notice, setNotice] = useState<string | null>(null);

  const ms = vnLocalToMs(visitedAt);
  const extrasProblem = visitExtrasProblem(extras);
  const valid = serviceId.trim() !== '' && Number.isFinite(ms) && !extrasProblem;

  const submit = async () => {
    if (!valid) return;
    setNotice(null);
    const r = await act.run(() =>
      api.createVisit({ customer_id: customerId, service_id: serviceId.trim(), visited_at: ms, ...visitExtrasPayload(extras) }),
    );
    if (r !== undefined) {
      const jobs = r.jobs?.length ?? 0;
      setNotice(jobs > 0 ? `Đã ghi buổi làm. Đã hẹn ${jobs} tin gửi sau buổi làm.` : 'Đã ghi buổi làm. Không có tin hẹn giờ nào được tạo.');
      setServiceId('');
      setExtras(EMPTY_VISIT_EXTRAS);
      onSaved();
    }
  };

  return (
    <div className="form summary-panel" role="group" aria-label="Ghi buổi làm cho khách này">
      <h4>Ghi buổi làm cho khách này</h4>
      <p className="muted small">
        Ghi buổi khách đã làm xong. Máy chủ hẹn tin cảm ơn và tin hỏi thăm như khi ghi ở tab Ghi nhận buổi làm.
      </p>
      <label>
        Dịch vụ
        <input
          list="summary-service-options"
          value={serviceId}
          disabled={act.busy}
          onChange={(e) => setServiceId(e.target.value)}
          placeholder="Chọn hoặc gõ mã dịch vụ"
        />
        <ServiceOptions id="summary-service-options" />
        {serviceId && <span className="muted small">{SERVICES.find((s) => s.id === serviceId)?.name ?? 'Mã không có trong danh sách đi kèm'}</span>}
      </label>
      <label>
        Giờ làm (giờ Việt Nam)
        <input type="datetime-local" value={visitedAt} disabled={act.busy} onChange={(e) => setVisitedAt(e.target.value)} />
      </label>
      <VisitExtraFields value={extras} onChange={setExtras} benefits={benefits} />
      {extrasProblem && <p className="error">{extrasProblem}</p>}
      <div className="actions">
        <button disabled={!valid || act.busy} onClick={submit}>
          Lưu buổi làm
        </button>
      </div>
      <ErrorLine text={visitErrorText(act.raw, act.error, extras)} />
      <Notice text={notice} />
    </div>
  );
}

// ---------------------------------------------------------------- benefits

export interface BenefitForm {
  kind: BenefitKind;
  title: string;
  serviceId: string;
  total: string;
  used: string;
  expires: string; // 'YYYY-MM-DD' of a date field, or ''
}

export const EMPTY_BENEFIT_FORM: BenefitForm = { kind: 'package', title: '', serviceId: '', total: '', used: '', expires: '' };

export const BENEFIT_TITLE_MAX = 120;
/** The server refuses a total above this (MAX_BENEFIT_COUNT of apps/server/src/staff-api/customers.ts). */
export const BENEFIT_TOTAL_MAX = 1000;

/** The first problem of the "add a benefit" form as a sentence for staff; null when it can be sent. */
export function benefitFormProblem(f: BenefitForm): string | null {
  const title = f.title.trim();
  if (!title) return 'Nhập tên quyền lợi, ví dụ Gói 10 buổi gội dưỡng sinh.';
  if (title.length > BENEFIT_TITLE_MAX || /[\r\n]/.test(title)) return `Tên quyền lợi viết trên một dòng, tối đa ${BENEFIT_TITLE_MAX} ký tự.`;
  const total = f.total.trim();
  if (!/^\d+$/.test(total) || Number(total) <= 0 || !Number.isSafeInteger(Number(total))) return 'Tổng số lần là số nguyên lớn hơn 0.';
  if (Number(total) > BENEFIT_TOTAL_MAX) return `Tổng số lần tối đa ${BENEFIT_TOTAL_MAX}.`;
  const used = f.used.trim();
  if (used !== '' && (!/^\d+$/.test(used) || Number(used) > Number(total))) return 'Số lần đã dùng là số nguyên từ 0 đến tổng số lần.';
  if (f.expires !== '' && !Number.isFinite(vnDateEndMs(f.expires))) return 'Hạn dùng không phải ngày hợp lệ.';
  return null;
}

/** Body of POST /staff/benefits; optional fields are sent only when staff filled them in. */
export function benefitCreateBody(customerId: string, f: BenefitForm): BenefitCreateRequest {
  const body: BenefitCreateRequest = { customer_id: customerId, kind: f.kind, title: f.title.trim(), total_count: Number(f.total.trim()) };
  if (f.serviceId.trim()) body.service_id = f.serviceId.trim();
  if (f.used.trim() !== '' && Number(f.used.trim()) > 0) body.used_count = Number(f.used.trim());
  if (f.expires !== '') body.expires_at = vnDateEndMs(f.expires);
  return body;
}

/** State of one benefit in words: void, expired, used up, or usable. */
export function benefitStateText(b: CustomerBenefit, now = Date.now()): string {
  if (b.status === 'void') return 'đã hủy';
  if (benefitExpired(b, now)) return 'đã hết hạn';
  if (benefitRemaining(b) <= 0) return 'đã dùng hết';
  return 'đang dùng được';
}

function BenefitsPanel(props: { api: Api; customerId: string; onSaved: () => void; refresh: number }) {
  const { api, customerId, onSaved, refresh } = props;
  const list = useLoad(() => api.listBenefits(customerId), 'tải được danh sách quyền lợi', refresh);
  const act = useAction();
  const [form, setForm] = useState<BenefitForm>(EMPTY_BENEFIT_FORM);
  const [voiding, setVoiding] = useState<string | null>(null);

  const problem = benefitFormProblem(form);
  const untouched = form.title === '' && form.total === '';
  const rows = list.data?.benefits ?? [];

  const done = () => {
    list.reload();
    onSaved();
  };

  const add = async () => {
    if (problem) return;
    const r = await act.run(() => api.createBenefit(benefitCreateBody(customerId, form)), 'Đã thêm quyền lợi.');
    if (r !== undefined) {
      setForm(EMPTY_BENEFIT_FORM);
      done();
    }
  };

  const useOnce = async (b: CustomerBenefit) => {
    const r = await act.run(() => api.patchBenefit(b.id, { used_count: b.used_count + 1 }), `Đã ghi một lần dùng cho quyền lợi ${b.title}.`);
    if (r !== undefined) done();
  };

  const setStatus = async (b: CustomerBenefit, status: 'active' | 'void') => {
    setVoiding(null);
    const r = await act.run(
      () => api.patchBenefit(b.id, { status }),
      status === 'void' ? `Đã hủy quyền lợi ${b.title}.` : `Đã khôi phục quyền lợi ${b.title}.`,
    );
    if (r !== undefined) done();
  };

  return (
    <div className="summary-panel" role="group" aria-label="Quyền lợi của khách">
      <h4>Quyền lợi của khách</h4>
      <p className="muted small">
        Quyền lợi là gói nhiều buổi hoặc voucher khách đã mua hay được tặng. Bot chỉ nhắc tới quyền lợi còn hạn và còn lượt dùng.
      </p>
      <ErrorLine text={list.error} />
      {!list.error && list.data === null && <p className="muted small">Đang tải danh sách quyền lợi.</p>}
      {list.data !== null && rows.length === 0 && <p className="muted small">Khách này chưa có quyền lợi nào được ghi.</p>}
      {rows.length > 0 && (
        <ul className="benefit-list">
          {rows.map((b) => {
            const usable = b.status === 'active' && benefitRemaining(b) > 0 && !benefitExpired(b);
            return (
              <li key={b.id} className={b.status === 'void' ? 'benefit void' : 'benefit'}>
                <div>
                  <strong>{b.title}</strong> <span className="muted small">({BENEFIT_KIND_LABEL[b.kind] ?? b.kind})</span>
                </div>
                <div className="muted small">
                  đã dùng {b.used_count}/{b.total_count} lần, còn {benefitRemaining(b)} lần ·{' '}
                  {isNum(b.expires_at) ? `hạn ${fmtDate(b.expires_at)}` : 'không có hạn'} · {benefitStateText(b)}
                </div>
                <div className="actions">
                  {usable && (
                    <button className="secondary" aria-label={`Dùng 1 lần: ${b.title}`} disabled={act.busy} onClick={() => void useOnce(b)}>
                      Dùng 1 lần
                    </button>
                  )}
                  {b.status === 'active' && voiding !== b.id && (
                    <button className="secondary" aria-label={`Hủy quyền lợi: ${b.title}`} disabled={act.busy} onClick={() => setVoiding(b.id)}>
                      Hủy quyền lợi
                    </button>
                  )}
                  {b.status === 'void' && (
                    <button
                      className="secondary"
                      aria-label={`Khôi phục quyền lợi: ${b.title}`}
                      disabled={act.busy}
                      onClick={() => void setStatus(b, 'active')}
                    >
                      Khôi phục quyền lợi
                    </button>
                  )}
                </div>
                {voiding === b.id && (
                  <div className="confirm-box" role="group" aria-label={`Xác nhận hủy quyền lợi ${b.title}`}>
                    <p>Hủy quyền lợi {b.title}? Bot sẽ không nhắc tới quyền lợi này nữa. Có thể khôi phục lại sau.</p>
                    <div className="actions">
                      <button className="danger" disabled={act.busy} onClick={() => void setStatus(b, 'void')}>
                        Hủy quyền lợi này
                      </button>
                      <button className="secondary" disabled={act.busy} onClick={() => setVoiding(null)}>
                        Giữ quyền lợi
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="form benefit-form">
        <h4>Thêm quyền lợi</h4>
        <label>
          Loại quyền lợi
          <select value={form.kind} disabled={act.busy} onChange={(e) => setForm({ ...form, kind: e.target.value as BenefitKind })}>
            {BENEFIT_KINDS.map((k) => (
              <option key={k} value={k}>
                {BENEFIT_KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tên quyền lợi
          <input
            maxLength={BENEFIT_TITLE_MAX}
            autoComplete="off"
            placeholder="Gói 10 buổi gội dưỡng sinh"
            value={form.title}
            disabled={act.busy}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
        </label>
        <label>
          Dịch vụ áp dụng (không bắt buộc)
          <input
            list="benefit-service-options"
            autoComplete="off"
            placeholder="Chọn hoặc gõ mã dịch vụ"
            value={form.serviceId}
            disabled={act.busy}
            onChange={(e) => setForm({ ...form, serviceId: e.target.value })}
          />
          <ServiceOptions id="benefit-service-options" />
        </label>
        <label>
          Tổng số lần
          <input
            inputMode="numeric"
            autoComplete="off"
            placeholder="10"
            value={form.total}
            disabled={act.busy}
            onChange={(e) => setForm({ ...form, total: e.target.value })}
          />
        </label>
        <label>
          Số lần đã dùng (không bắt buộc)
          <input
            inputMode="numeric"
            autoComplete="off"
            placeholder="0"
            value={form.used}
            disabled={act.busy}
            onChange={(e) => setForm({ ...form, used: e.target.value })}
          />
        </label>
        <label>
          Hạn dùng (không bắt buộc)
          <input type="date" value={form.expires} disabled={act.busy} onChange={(e) => setForm({ ...form, expires: e.target.value })} />
          <span className="muted small">Quyền lợi dùng được đến hết ngày này, giờ Việt Nam. Để trống nếu không có hạn.</span>
        </label>
        {problem && !untouched && <p className="error">{problem}</p>}
        <div className="actions">
          <button disabled={act.busy || problem !== null} onClick={add}>
            Thêm quyền lợi
          </button>
        </div>
      </div>
      <ErrorLine text={serverGapText(act.raw, 'lưu được quyền lợi') ?? act.error} />
      <Notice text={act.notice} />
    </div>
  );
}

// ---------------------------------------------------------------- recorded visits

function visitServiceText(v: VisitView): string {
  // The server's name falls back to the bare service id; the list shipped with the console may know a better one.
  const serverName = v.name && v.name !== v.service_id ? v.name : '';
  return serverName || v.service_name || SERVICES.find((s) => s.id === v.service_id)?.name || v.service_id || 'chưa ghi';
}

// Only one panel is open at a time, so this list is loaded afresh each time staff open it, and again after a decision
// in the section "Suy ra từ tin nhắn cũ" while it is open.
function VisitsPanel(props: { api: Api; customerId: string; refresh: number }) {
  const { api, customerId, refresh } = props;
  const list = useLoad(() => api.listVisits(customerId), 'tải được danh sách buổi làm', refresh);
  const rows = list.data ? (list.data.visits ?? list.data.items ?? []) : [];

  return (
    <div className="summary-panel" role="group" aria-label="Các buổi làm đã ghi">
      <h4>Các buổi làm đã ghi</h4>
      <ErrorLine text={list.error} />
      {!list.error && list.data === null && <p className="muted small">Đang tải danh sách buổi làm.</p>}
      {list.data !== null && rows.length === 0 && <p className="muted small">Chưa có buổi làm nào được ghi cho khách này.</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Giờ làm</th>
                <th>Dịch vụ</th>
                <th>Kỹ thuật viên</th>
                <th>Thời lượng</th>
                <th>Số tiền</th>
                <th>Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id}>
                  <td>{fmtTime(v.visited_at)}</td>
                  <td>
                    {visitServiceText(v)}
                    {v.benefit_id ? ' (dùng quyền lợi)' : ''}
                  </td>
                  <td>{v.technician || 'chưa ghi'}</td>
                  <td>{isNum(v.duration_min) ? `${v.duration_min} phút` : 'chưa ghi'}</td>
                  <td>{isNum(v.amount_vnd) ? fmtVnd(v.amount_vnd) : 'chưa ghi'}</td>
                  <td>{v.source ? (VISIT_SOURCE_LABEL[v.source] ?? v.source) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the block

/** " · gồm 2 lần suy ra từ tin nhắn" after a figure; nothing at all when the figure includes no guess. */
function ChatMarker({ text }: { text: string | null }) {
  if (!text) return null;
  return <span className="chat-marker"> · {text}</span>;
}

const figureMarker = (m: ChatFigureMarker | null) => (m ? chatMarkerText(m.n, m.atMost) : null);

type Panel = 'visit' | 'benefits' | 'visits';

const PANEL_BUTTON: Record<Panel, { open: string; close: string }> = {
  visit: { open: 'Ghi buổi làm cho khách này', close: 'Đóng phần ghi buổi làm' },
  benefits: { open: 'Thêm hoặc dùng quyền lợi', close: 'Đóng phần quyền lợi' },
  visits: { open: 'Xem các buổi làm đã ghi', close: 'Đóng danh sách buổi làm' },
};

export function CustomerSummaryCard(props: { api: Api; customerId: string; summary: CustomerSummary; onSaved: () => void; zaloUserId?: string }) {
  const { api, customerId, summary: s, onSaved, zaloUserId } = props;
  const [panel, setPanel] = useState<Panel | null>(null);
  // counts the decisions taken in the chat section, so that an open list of benefits or visits loads again
  const [chatDecisions, setChatDecisions] = useState(0);

  // Section 15: the server leaves `chat` out when GET /staff/chat-facts would answer null (no chat facts for the
  // contact, or migration 0011 not applied), so nothing is loaded then.
  const chatId = s.chat !== undefined && zaloUserId && CHAT_FACTS_ID_RE.test(zaloUserId) ? zaloUserId : null;
  const chatGeneratedAt = s.chat && typeof s.chat === 'object' ? (s.chat.generated_at ?? null) : null;
  const chatLoad = useChatFacts(api, chatId, chatGeneratedAt);
  const marks = chatMarkers(s, chatLoad.facts);
  const visitsMarker = marks.visits > 0 ? chatMarkerText(marks.visits) : null;
  const anyMarker = visitsMarker !== null || marks.lastVisit;

  const visited = hasVisitData(s);
  const benefits = s.benefits ?? [];
  const choices: BenefitChoice[] = benefits.filter((b) => b.remaining > 0).map((b) => ({ id: b.id, label: summaryBenefitText(b) }));
  const w = s.window ?? null;
  const usual = w?.services ?? [];
  const reason = customerStatusReason(s);

  return (
    <section className="box customer-summary" aria-label="Tóm tắt khách hàng">
      <h3>Tóm tắt khách hàng</h3>

      <dl className="facts">
        <dt>Tên</dt>
        <dd>{s.name || 'chưa có tên để gọi'}</dd>
        <dt>Cách xưng hô</dt>
        <dd>{s.address_term || 'chưa xác định (bot gọi anh/chị)'}</dd>
        <dt>Số điện thoại</dt>
        <dd>
          <PhoneFact api={api} customerId={customerId} phone={s.phone ?? null} onSaved={onSaved} />
        </dd>
        {s.status && (
          <>
            <dt>Trạng thái</dt>
            <dd>
              <span className={`badge ${STATUS_BADGE[s.status] ?? 'muted'}`}>{CUSTOMER_STATUS_LABEL[s.status] ?? s.status}</span>
              {reason ? ` ${reason}` : ''}
              <ChatMarker text={s.status !== 'first_inquiry' ? visitsMarker : null} />
            </dd>
          </>
        )}
        <dt>Tổng số lần đã đến</dt>
        <dd>
          {isNum(s.visits_total) ? `${s.visits_total} lần` : 'chưa có số liệu'}
          <ChatMarker text={isNum(s.visits_total) ? visitsMarker : null} />
        </dd>
        {visited && (
          <>
            <dt>Dịch vụ cuối cùng</dt>
            <dd>
              {s.last_visit ? lastVisitText(s.last_visit) : 'chưa có số liệu'}
              <ChatMarker text={s.last_visit && marks.lastVisit ? FROM_CHAT_TEXT : null} />
            </dd>
            <dt>Tổng số tiền đã dùng</dt>
            <dd>
              {isNum(s.lifetime_spend_vnd) && (s.lifetime_spend_visits ?? 1) > 0 ? (
                <>
                  {`${fmtVnd(s.lifetime_spend_vnd)}${isNum(s.lifetime_spend_visits) ? ` (tính trên ${s.lifetime_spend_visits} buổi có ghi số tiền)` : ''}`}
                  <ChatMarker text={figureMarker(marks.spend)} />
                </>
              ) : (
                'chưa có buổi nào ghi số tiền'
              )}
            </dd>
            <dt>Đã bao lâu chưa đến</dt>
            <dd>
              {isNum(s.days_since_last_visit) ? `${s.days_since_last_visit} ngày` : 'chưa có số liệu'}
              <ChatMarker text={isNum(s.days_since_last_visit) && marks.lastVisit ? `tính từ lần đến ${FROM_CHAT_TEXT}` : null} />
            </dd>
            <dt>Thường cách bao lâu quay lại</dt>
            <dd>
              {isNum(s.usual_gap_days)
                ? `${s.usual_gap_days} ngày${s.gap_basis && GAP_BASIS_LABEL[s.gap_basis] ? ` (${GAP_BASIS_LABEL[s.gap_basis]})` : ''}`
                : 'chưa có số liệu'}
              <ChatMarker text={isNum(s.usual_gap_days) && s.gap_basis === 'own' ? visitsMarker : null} />
            </dd>
            {w && (
              <>
                <dt>Khoảng thời gian tính</dt>
                <dd>
                  {windowText(w)}
                  <ChatMarker text={figureMarker(marks.window)} />
                </dd>
                <dt>Dịch vụ thường dùng</dt>
                <dd>
                  {usual.length > 0
                    ? usual.map((x) => `${x.name}${isNum(x.count) ? ` (${x.count} lần)` : ''}`).join('; ')
                    : 'chưa có buổi nào trong khoảng thời gian tính'}
                  <ChatMarker text={usual.length > 0 ? figureMarker(marks.window) : null} />
                </dd>
                <dt>Mức chi mỗi lần</dt>
                <dd>
                  {isNum(w.avg_spend_vnd) ? `trung bình ${fmtVnd(w.avg_spend_vnd)}` : 'chưa có buổi nào ghi số tiền trong khoảng thời gian tính'}
                  <ChatMarker text={isNum(w.avg_spend_vnd) ? figureMarker(marks.windowSpend) : null} />
                </dd>
                <dt>Tổng chi trong khoảng</dt>
                <dd>
                  {isNum(w.spend_vnd) ? fmtVnd(w.spend_vnd) : 'chưa có buổi nào ghi số tiền trong khoảng thời gian tính'}
                  <ChatMarker text={isNum(w.spend_vnd) ? figureMarker(marks.windowSpend) : null} />
                </dd>
              </>
            )}
          </>
        )}
        <dt>Quyền lợi chưa dùng</dt>
        <dd>
          {benefits.length === 0 ? (
            'không có'
          ) : (
            <ul className="plain-list">
              {benefits.map((b) => (
                <li key={b.id}>{summaryBenefitText(b)}</li>
              ))}
            </ul>
          )}
        </dd>
      </dl>

      {/* the server leaves `chat` out for a contact without chat facts, so its absence says nothing about the server */}
      {!visited && <p className="muted small">{NO_VISIT_DATA_CHAT_TEXT}</p>}
      {visited && w && (
        <p className="muted small">Dịch vụ thường dùng, mức chi mỗi lần và tổng chi trong khoảng chỉ tính các buổi nằm trong khoảng thời gian tính.</p>
      )}
      {visited && anyMarker && (
        <p className="muted small">
          Ghi chú {FROM_CHAT_TEXT} bên cạnh một số liệu nghĩa là số liệu đó tính cả lần đến mà công cụ phân tích suy ra từ tin nhắn Zalo cũ (mức
          chắc hoặc khá chắc) và nhân viên chưa xác nhận.
        </p>
      )}

      <div className="actions">
        {(Object.keys(PANEL_BUTTON) as Panel[]).map((p) => (
          <button key={p} className="secondary" aria-expanded={panel === p} onClick={() => setPanel(panel === p ? null : p)}>
            {panel === p ? PANEL_BUTTON[p].close : PANEL_BUTTON[p].open}
          </button>
        ))}
      </div>

      {panel === 'visit' && <VisitPanel api={api} customerId={customerId} benefits={choices} onSaved={onSaved} />}
      {panel === 'benefits' && <BenefitsPanel api={api} customerId={customerId} onSaved={onSaved} refresh={chatDecisions} />}
      {panel === 'visits' && <VisitsPanel api={api} customerId={customerId} refresh={chatDecisions} />}

      {chatId && (
        <ChatFactsSection
          api={api}
          zaloUserId={chatId}
          load={chatLoad}
          onSaved={() => {
            setChatDecisions((n) => n + 1);
            onSaved();
          }}
        />
      )}
    </section>
  );
}
