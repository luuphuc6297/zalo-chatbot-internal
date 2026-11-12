// Record a completed visit. The server schedules the thank-you and check-in follow-ups from it.
import { useMemo, useState } from 'react';
import type { Api, VisitResponse } from '../api';
import { useAction, usePoll } from '../hooks';
import { fmtTime, msToVnLocal, vnLocalToMs } from '../labels';
import { SERVICES } from '../services';
import { customerName } from './Conversations';
import { EMPTY_VISIT_EXTRAS, VisitExtraFields, useUsableBenefits, visitErrorText, visitExtrasPayload, visitExtrasProblem } from './VisitFields';
import type { VisitExtras } from './VisitFields';
import { ErrorLine } from './common';

const JOB_LABEL: Record<string, string> = { thank_you: 'Tin cảm ơn', check_in: 'Tin hỏi thăm' };

export function VisitsScreen({ api }: { api: Api }) {
  const convs = usePoll(() => api.listConversations({ limit: 200 }), [api], 30_000);
  const confirmed = usePoll(() => api.listBookingRequests({ status: 'confirmed', limit: 200 }), [api], 30_000);
  const act = useAction();
  const [customerId, setCustomerId] = useState('');
  const [serviceId, setServiceId] = useState('');
  const [visitedAt, setVisitedAt] = useState(() => msToVnLocal(Date.now()));
  const [bookingId, setBookingId] = useState('');
  const [externalId, setExternalId] = useState('');
  const [extras, setExtras] = useState<VisitExtras>(EMPTY_VISIT_EXTRAS);
  const [result, setResult] = useState<VisitResponse | null>(null);
  const benefits = useUsableBenefits(api, customerId);

  const customers = useMemo(() => {
    const seen = new Map<string, string>();
    for (const c of convs.data?.items ?? []) if (!seen.has(c.customer.id)) seen.set(c.customer.id, customerName(c));
    return [...seen.entries()].map(([id, name]) => ({ id, name }));
  }, [convs.data]);
  const bookings = (confirmed.data?.items ?? []).filter((b) => !customerId || convs.data?.items.some((c) => c.id === b.conversation_id && c.customer.id === customerId));

  const ms = vnLocalToMs(visitedAt);
  const extrasProblem = visitExtrasProblem(extras);
  const valid = customerId && serviceId.trim() && Number.isFinite(ms) && !extrasProblem;

  // A benefit belongs to one customer: choosing another customer clears it.
  const pickCustomer = (id: string) => {
    setCustomerId(id);
    setExtras((x) => ({ ...x, benefitId: '' }));
  };

  const submit = async () => {
    setResult(null);
    const r = await act.run(() =>
      api.createVisit({
        customer_id: customerId,
        service_id: serviceId.trim(),
        visited_at: ms,
        booking_request_id: bookingId || undefined,
        external_visit_id: externalId.trim() || undefined,
        ...visitExtrasPayload(extras),
      }),
    );
    if (r) {
      setResult(r);
      setExtras(EMPTY_VISIT_EXTRAS);
    }
  };

  return (
    <div className="page narrow">
      <h2>Ghi nhận buổi làm</h2>
      <p className="muted small">
        Ghi lại buổi khách đã làm xong. Hệ thống sẽ hẹn tin cảm ơn (20 đến 24 giờ sau, trong 9:00 đến 20:00) và tin hỏi thăm (2 ngày sau,
        10:00). Tin hẹn giờ chỉ được gửi khi công tắc gửi tin hẹn giờ đang cho gửi.
      </p>
      <ErrorLine text={convs.error} />
      <div className="form">
        <label>
          Khách
          <select value={customerId} onChange={(e) => pickCustomer(e.target.value)}>
            <option value="">Chọn khách</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Dịch vụ
          <input list="service-options" value={serviceId} onChange={(e) => setServiceId(e.target.value)} placeholder="Chọn hoặc gõ mã dịch vụ" />
          <datalist id="service-options">
            {SERVICES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </datalist>
          {serviceId && <span className="muted small">{SERVICES.find((s) => s.id === serviceId)?.name ?? 'Mã không có trong danh sách đi kèm'}</span>}
        </label>
        <label>
          Giờ làm (giờ Việt Nam)
          <input type="datetime-local" value={visitedAt} onChange={(e) => setVisitedAt(e.target.value)} />
        </label>
        <VisitExtraFields value={extras} onChange={setExtras} benefits={benefits} />
        <label>
          Yêu cầu đặt lịch đã xác nhận (không bắt buộc)
          <select value={bookingId} onChange={(e) => setBookingId(e.target.value)}>
            <option value="">Không gắn</option>
            {bookings.map((b) => (
              <option key={b.id} value={b.id}>
                {b.customer_name} · {b.preferred_date_local} · {b.preferred_time_window}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mã buổi làm ở hệ thống khác (không bắt buộc)
          <input value={externalId} onChange={(e) => setExternalId(e.target.value)} />
        </label>
        {extrasProblem && <p className="error">{extrasProblem}</p>}
        <div className="actions">
          <button disabled={!valid || act.busy} onClick={submit}>
            Ghi nhận buổi làm
          </button>
        </div>
      </div>
      <ErrorLine text={visitErrorText(act.raw, act.error, extras)} />
      {result && (
        <div className="box">
          <strong>Đã ghi nhận buổi làm {result.visit_id}.</strong>
          {result.jobs.length === 0 ? (
            <p>Không có tin hẹn giờ nào được tạo.</p>
          ) : (
            <ul>
              {result.jobs.map((j) => (
                <li key={j.job_id}>
                  {JOB_LABEL[j.type] ?? j.type}: hẹn gửi lúc {fmtTime(j.run_at)} ({j.status})
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
