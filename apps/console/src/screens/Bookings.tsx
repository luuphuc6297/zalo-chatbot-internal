// Booking requests captured by the bot. Only staff confirm or decline; the bot never promises a slot.
import { useState } from 'react';
import type { Api, BookingRequestView, BookingStatus } from '../api';
import { useAction, usePoll } from '../hooks';
import { BOOKING_STATUS_LABEL, fmtTime } from '../labels';
import { SERVICES } from '../services';
import { ErrorLine, Notice } from './common';

const STATUSES: BookingStatus[] = ['new', 'proposed', 'confirmed', 'cancelled', 'expired'];

function serviceName(id: string): string {
  return SERVICES.find((s) => s.id === id)?.name ?? id;
}

export function BookingsScreen(props: { api: Api; onOpenConversation: (id: string) => void }) {
  const { api } = props;
  const [status, setStatus] = useState<BookingStatus>('new');
  const list = usePoll(() => api.listBookingRequests({ status, limit: 200 }), [api, status]);

  return (
    <div className="page">
      <div className="row between">
        <h2>Yêu cầu đặt lịch</h2>
        <label>
          Trạng thái{' '}
          <select value={status} onChange={(e) => setStatus(e.target.value as BookingStatus)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {BOOKING_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted small">
        Bot chỉ ghi nhận yêu cầu, không giữ chỗ. Nhân viên kiểm tra lịch, nhắn khách trong hội thoại, rồi đánh dấu kết quả ở đây.
      </p>
      <ErrorLine text={list.error} />
      {list.data && list.data.items.length === 0 && <p className="muted">Không có yêu cầu nào.</p>}
      <ul className="cards">
        {(list.data?.items ?? []).map((b) => (
          <BookingCard key={b.id} api={api} b={b} onDone={list.reload} onOpen={() => props.onOpenConversation(b.conversation_id)} />
        ))}
      </ul>
    </div>
  );
}

function BookingCard(props: { api: Api; b: BookingRequestView; onDone: () => void; onOpen: () => void }) {
  const { api, b } = props;
  const act = useAction();
  const [note, setNote] = useState(b.staff_note ?? '');
  const set = async (status: Exclude<BookingStatus, 'new'>, ok: string) => {
    const r = await act.run(() => api.setBookingStatus(b.id, { status, staff_note: note.trim() || undefined }), ok);
    if (r !== undefined) props.onDone();
  };
  return (
    <li className="card">
      <div className="row between">
        <strong>
          {b.customer_name || b.customer_display_name || 'Khách'} · {b.preferred_date_local} · {b.preferred_time_window}
        </strong>
        <span className="muted small">{BOOKING_STATUS_LABEL[b.status]}</span>
      </div>
      <div className="small">
        Dịch vụ: {b.service_ids.map(serviceName).join(', ') || 'chưa rõ'} · {b.duration_min} phút · {b.party_size} người
        {b.price_quoted_text ? ` · giá đã báo ${b.price_quoted_text}` : ''}
      </div>
      <div className="small">
        Liên hệ: {b.contact_method === 'phone_shared_with_consent' ? `điện thoại ${b.phone ?? ''} (khách đồng ý chia sẻ)` : 'chỉ qua Zalo'}
      </div>
      {b.notes_for_staff && <p className="text">Ghi chú của bot: {b.notes_for_staff}</p>}
      <div className="muted small">Tạo lúc {fmtTime(b.created_at)} · cập nhật {fmtTime(b.updated_at)}</div>
      <input className="reason" placeholder="Ghi chú của nhân viên" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="actions">
        <button className="secondary" onClick={props.onOpen}>
          Mở hội thoại
        </button>
        <button disabled={act.busy} onClick={() => set('confirmed', 'Đã đánh dấu đã xác nhận.')}>
          Đã xác nhận với khách
        </button>
        <button className="secondary" disabled={act.busy} onClick={() => set('proposed', 'Đã đánh dấu đã đề xuất giờ khác.')}>
          Đã đề xuất giờ khác
        </button>
        <button className="danger" disabled={act.busy} onClick={() => set('cancelled', 'Đã đánh dấu từ chối hoặc hủy.')}>
          Từ chối hoặc hủy
        </button>
      </div>
      <ErrorLine text={act.error} />
      <Notice text={act.notice} />
    </li>
  );
}
