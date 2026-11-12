// Handoffs: conversations the bot (or the server) passed to staff, urgent first, with the model's summary.
import { useMemo, useState } from 'react';
import type { Api, HandoffView } from '../api';
import { useAction, usePoll } from '../hooks';
import { fmtTime, handoffReason } from '../labels';
import { ErrorLine, Notice } from './common';

const SOURCE_TEXT: Record<HandoffView['source'], string> = {
  model_tool: 'bot chuyển',
  server: 'hệ thống chuyển',
  runner_failure: 'máy chạy model lỗi',
  staff: 'nhân viên tạo',
};

export function sortHandoffs(items: HandoffView[]): HandoffView[] {
  return [...items].sort((a, b) => {
    if (a.urgency !== b.urgency) return a.urgency === 'urgent' ? -1 : 1;
    return a.created_at - b.created_at;
  });
}

export function HandoffsScreen(props: { api: Api; onOpenConversation: (id: string) => void }) {
  const { api } = props;
  const [status, setStatus] = useState<'open' | 'resolved'>('open');
  const list = usePoll(() => api.listHandoffs({ status, limit: 200 }), [api, status]);
  const act = useAction();
  const items = useMemo(() => sortHandoffs(list.data?.items ?? []), [list.data]);

  return (
    <div className="page">
      <div className="row between">
        <h2>Cần nhân viên</h2>
        <div className="filters" role="group" aria-label="Lọc theo trạng thái">
          <button className={status === 'open' ? 'chip active' : 'chip'} onClick={() => setStatus('open')}>
            Đang chờ
          </button>
          <button className={status === 'resolved' ? 'chip active' : 'chip'} onClick={() => setStatus('resolved')}>
            Đã xử lý
          </button>
        </div>
      </div>
      <p className="muted small">Việc gấp đứng đầu, sau đó là việc chờ lâu nhất.</p>
      <ErrorLine text={list.error ?? act.error} />
      <Notice text={act.notice} />
      {list.data && items.length === 0 && <p className="muted">Không có việc nào.</p>}
      <ul className="cards">
        {items.map((h) => (
          <li key={h.id} className={h.urgency === 'urgent' ? 'card urgent' : 'card'}>
            <div className="row between">
              <strong>
                {h.urgency === 'urgent' ? 'GẤP · ' : ''}
                {handoffReason(h)}
              </strong>
              <span className="muted small">{fmtTime(h.created_at)}</span>
            </div>
            <div className="muted small">
              {h.customer_display_name ?? 'Khách chưa có tên'} · {SOURCE_TEXT[h.source]}
              {h.resolved_at ? ` · xử lý lúc ${fmtTime(h.resolved_at)}${h.resolved_by ? ` bởi ${h.resolved_by}` : ''}` : ''}
            </div>
            <p className="text">{h.summary_for_staff ?? 'Không có tóm tắt.'}</p>
            <div className="actions">
              <button className="secondary" onClick={() => props.onOpenConversation(h.conversation_id)}>
                Mở hội thoại
              </button>
              {h.status === 'open' && (
                <button
                  disabled={act.busy}
                  onClick={async () => {
                    await act.run(() => api.resolveHandoff(h.id), 'Đã đánh dấu đã xử lý.');
                    list.reload();
                  }}
                >
                  Đánh dấu đã xử lý
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
