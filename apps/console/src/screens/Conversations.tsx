// Conversations: list with status badges, detail with messages, drafts, takeover/release and manual send.
// Every piece of customer or model text is rendered as a React text node (never as HTML).
import { useMemo, useState } from 'react';
import type { Api, ConversationDetail, ConversationMode, ConversationSummary, DraftView } from '../api';
import { ApiError } from '../api';
import { useAction, usePoll } from '../hooks';
import {
  AUTO_REPLY_TEXT,
  BOOKING_STATUS_LABEL,
  BOT_STATE_LABEL,
  CHECKER_RULE_LABEL,
  DRAFT_STATUS_LABEL,
  MODES,
  MODE_LABEL,
  SEND_STATE_LABEL,
  SOURCE_LABEL,
  conversationBadges,
  fmtTime,
  handoffReason,
} from '../labels';
import { Badges, ErrorLine, Notice } from './common';
import { AutoReplySwitch, RoleRow, resolveRole, roomLine } from './ConversationSettings';
import { CustomerSummaryCard } from './CustomerSummaryCard';
import { ProfileCard } from './ProfileCard';
import { DraftImages, SendMenuPanel, useMenuIndex } from './MenuImages';
import type { MenuImagesIndex } from '../api';

type Filter = 'all' | 'attention' | 'pending' | 'staff';

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: 'all', label: 'Tất cả' },
  { id: 'attention', label: 'Cần chú ý' },
  { id: 'pending', label: 'Chờ duyệt' },
  { id: 'staff', label: 'Nhân viên đang xử lý' },
];

function matches(c: ConversationSummary, f: Filter): boolean {
  if (f === 'attention') return c.needs_attention || c.open_handoffs > 0 || c.bot_state === 'handoff_requested';
  if (f === 'pending') return c.pending_drafts > 0;
  if (f === 'staff') return c.bot_state === 'staff_takeover' || c.bot_state === 'staff_only';
  return true;
}

export function customerName(c: ConversationSummary): string {
  return c.customer.display_name?.trim() || `Khách ${c.customer.zalo_user_id.slice(-4)}`;
}

export function ConversationsScreen(props: { api: Api; selectedId: string | null; onSelect: (id: string | null) => void }) {
  const { api, selectedId, onSelect } = props;
  const [filter, setFilter] = useState<Filter>('all');
  const list = usePoll(() => api.listConversations({ limit: 200 }), [api]);
  const items = useMemo(() => (list.data?.items ?? []).filter((c) => matches(c, filter)), [list.data, filter]);

  return (
    <div className="split">
      <section className="list-pane" aria-label="Danh sách hội thoại">
        <div className="filters" role="group" aria-label="Lọc hội thoại">
          {FILTERS.map((f) => (
            <button key={f.id} className={filter === f.id ? 'chip active' : 'chip'} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        <ErrorLine text={list.error} />
        {list.data && items.length === 0 && <p className="muted">Không có hội thoại nào.</p>}
        <ul className="conv-list">
          {items.map((c) => (
            <li key={c.id}>
              <button className={c.id === selectedId ? 'conv-item selected' : 'conv-item'} onClick={() => onSelect(c.id)}>
                <div className="row between">
                  <strong>{customerName(c)}</strong>
                  <span className="muted small">{fmtTime(c.last_message_at)}</span>
                </div>
                <div className="preview">{c.last_message_preview ?? ''}</div>
                <Badges badges={conversationBadges(c)} />
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="detail-pane">
        {selectedId ? (
          <ConversationDetailView key={selectedId} api={api} id={selectedId} />
        ) : (
          <p className="muted">Chọn một hội thoại bên trái để xem tin nhắn và bản nháp.</p>
        )}
      </section>
    </div>
  );
}

function ConversationDetailView({ api, id }: { api: Api; id: string }) {
  const detail = usePoll(() => api.getConversation(id), [api, id]);
  const act = useAction();
  const menu = useMenuIndex(api);
  const d = detail.data;

  if (!d) return detail.error ? <ErrorLine text={detail.error} /> : <p className="muted">Đang tải...</p>;
  const c = d.conversation;
  const open = d.drafts.filter((x) => x.status === 'pending' || x.status === 'blocked');
  const decided = d.drafts.filter((x) => x.status !== 'pending' && x.status !== 'blocked');
  const openHandoffs = d.handoffs.filter((h) => h.status === 'open');
  const takenOver = c.bot_state === 'staff_takeover';
  const staffOnly = c.bot_state === 'staff_only';
  // Contact profiles exist for the personal Zalo channel only ('p:' + threadId).
  const showProfile = Boolean(d.profile) || c.customer.zalo_user_id.startsWith('p:');
  // Section 14: all three are absent on a server before 2026-11-12, and each block below then renders nothing.
  const summary = d.customer_summary && typeof d.customer_summary === 'object' ? d.customer_summary : null;
  const { role, source: roleSource } = resolveRole(summary, c, d.profile);
  // The server keeps the bots away only from a contact with a role row (Zalo label or staff); a role read from the
  // contact profile does not, so it does not lock the switch either.
  const gateRole = roleSource === 'profile' ? null : role;
  const room = d.room && typeof d.room.channel_id === 'string' ? d.room : null;

  const after = async <T,>(fn: () => Promise<T>, ok: string) => {
    const r = await act.run(fn, ok);
    detail.reload();
    return r;
  };

  return (
    <div className="detail">
      <header className="detail-head">
        <div>
          <h2>{customerName(c)}</h2>
          <div className="muted small">
            Zalo id {c.customer.zalo_user_id}
            {c.customer.phone ? ` · SĐT ${c.customer.phone}` : ''} · trạng thái: {BOT_STATE_LABEL[c.bot_state]}
            {takenOver && c.takeover_until ? ` đến ${fmtTime(c.takeover_until)}` : ''}
            {c.takeover_by ? ` (${c.takeover_by})` : ''}
          </div>
          {room && <div className="muted small">{roomLine(room)}</div>}
          <Badges badges={conversationBadges({ ...c, role, role_source: roleSource })} />
        </div>
        <div className="actions">
          {takenOver || staffOnly ? (
            <button disabled={act.busy} onClick={() => after(() => api.release(id), 'Đã trả hội thoại cho bot.')}>
              Trả lại cho bot
            </button>
          ) : (
            <button
              disabled={act.busy || c.bot_state === 'blocked'}
              onClick={() => after(() => api.takeover(id), 'Đã nhận xử lý: bot ngừng soạn nháp trong 12 giờ.')}
            >
              Nhận xử lý (bot ngừng trả lời)
            </button>
          )}
          {!staffOnly && c.bot_state !== 'blocked' && (
            <button
              className="secondary"
              disabled={act.busy}
              title="Dùng cho người nhà, bạn bè hay tài khoản khác nhắn vào: bot không trả lời, không gửi tin xin đồng ý, không tạo yêu cầu chuyển nhân viên."
              onClick={() =>
                after(
                  () => api.markStaffOnly(id),
                  'Đã chuyển sang chỉ nhân viên trả lời: bot không trả lời và không gửi tin xin đồng ý cho người này.',
                )
              }
            >
              Không phải khách (chỉ nhân viên trả lời)
            </button>
          )}
        </div>
      </header>

      <section className="box conv-settings" aria-label="Cài đặt của hội thoại">
        <AutoReplySwitch api={api} conversation={c} role={gateRole} onDone={detail.reload} />
        <ModePicker
          current={c.mode_override}
          effective={c.effective_mode}
          autoReply={c.auto_reply}
          busy={act.busy}
          onChange={(m) => after(() => api.setMode(id, m), 'Đã đổi chế độ của hội thoại.')}
        />
        <RoleRow api={api} zaloUserId={c.customer.zalo_user_id} role={role} source={roleSource} onDone={detail.reload} />
      </section>
      <ErrorLine text={act.error} />
      <Notice text={act.notice} />

      {openHandoffs.length > 0 && (
        <div className="box warn">
          <strong>Bot đã chuyển nhân viên</strong>
          {openHandoffs.map((h) => (
            <p key={h.id}>
              {h.urgency === 'urgent' ? 'GẤP · ' : ''}
              {handoffReason(h)}: {h.summary_for_staff ?? 'không có tóm tắt'}
            </p>
          ))}
        </div>
      )}

      {summary && (
        <CustomerSummaryCard api={api} customerId={c.customer.id} zaloUserId={c.customer.zalo_user_id} summary={summary} onSaved={detail.reload} />
      )}

      {showProfile && (
        <ProfileCard api={api} zaloUserId={d.profile?.zalo_user_id ?? c.customer.zalo_user_id} profile={d.profile ?? null} onSaved={detail.reload} />
      )}

      <Messages detail={d} />

      {open.length > 0 && (
        <div className="drafts">
          <h3>Bản nháp chờ xử lý</h3>
          {open.map((dr) => (
            <DraftCard key={dr.id} api={api} draft={dr} mode={c.effective_mode} menu={menu.index} onDone={detail.reload} />
          ))}
        </div>
      )}

      <ManualSend api={api} conversationId={id} onDone={detail.reload} />

      {/* Menu images go out through the personal Zalo bridge only ('p:' + threadId). */}
      {c.customer.zalo_user_id.startsWith('p:') && c.bot_state !== 'blocked' && (
        <SendMenuPanel api={api} conversationId={id} index={menu.index} indexError={menu.error} onDone={detail.reload} />
      )}

      {d.booking_requests.length > 0 && (
        <div className="box">
          <strong>Yêu cầu đặt lịch của khách này</strong>
          {d.booking_requests.map((b) => (
            <p key={b.id}>
              {b.preferred_date_local} · {b.preferred_time_window} · {b.party_size} người · {BOOKING_STATUS_LABEL[b.status]}
            </p>
          ))}
        </div>
      )}

      {decided.length > 0 && (
        <details>
          <summary>Bản nháp đã xử lý ({decided.length})</summary>
          {decided.map((dr) => (
            <div key={dr.id} className="draft decided">
              <div className="muted small">
                {fmtTime(dr.created_at)} · {DRAFT_STATUS_LABEL[dr.status]}
                {dr.decided_by ? ` · ${dr.decided_by}` : ''}
              </div>
              <div className="text">{dr.final_text ?? dr.text}</div>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

// The setting for what the bots do while the "Tự động trả lời" switch is off (docs/contracts.md section 14.4).
function ModePicker(props: {
  current: ConversationMode | null;
  effective: ConversationMode;
  autoReply?: 'on' | 'off';
  busy: boolean;
  onChange: (m: ConversationMode | null) => void;
}) {
  const note =
    props.autoReply === 'on' && props.effective === 'auto_allowed'
      ? AUTO_REPLY_TEXT.modeWhileOn
      : props.autoReply === 'off'
        ? AUTO_REPLY_TEXT.modeWhileOff
        : 'Chế độ đang áp dụng là mức thấp hơn giữa cài đặt chung và chế độ riêng.';
  return (
    <div className="mode-picker">
      <label>
        Chế độ riêng của hội thoại (bot làm gì khi tự động trả lời đang tắt):{' '}
        <select
          value={props.current ?? ''}
          disabled={props.busy}
          onChange={(e) => props.onChange(e.target.value === '' ? null : (e.target.value as ConversationMode))}
        >
          <option value="">Theo cài đặt chung</option>
          {MODES.map((m) => (
            <option key={m} value={m}>
              {MODE_LABEL[m].label}
            </option>
          ))}
        </select>
      </label>
      <div className="muted small">
        Đang áp dụng: {MODE_LABEL[props.effective].label}. {MODE_LABEL[props.effective].does} {note}
      </div>
    </div>
  );
}

function Messages({ detail }: { detail: ConversationDetail }) {
  if (detail.messages.length === 0) return <p className="muted">Chưa có tin nhắn.</p>;
  return (
    <ol className="messages">
      {detail.messages.map((m) => (
        <li key={m.id} className={`msg ${m.direction} src-${m.source}`}>
          <div className="muted small">
            {SOURCE_LABEL[m.source]}
            {m.staff_id ? ` (${m.staff_id})` : ''} · {fmtTime(m.sent_at ?? m.created_at)}
            {SEND_STATE_LABEL[m.send_state] ? ` · ${SEND_STATE_LABEL[m.send_state]}` : ''}
          </div>
          {m.text && <div className="text">{m.text}</div>}
          {m.attachments.map((a, i) =>
            a.type === 'menu_image' ? (
              <div key={i} className="attachment muted small">
                Ảnh menu{a.name ? `: ${a.name}` : ''}
              </div>
            ) : (
              <div key={i} className="attachment muted small">
                Đính kèm {a.type}
                {a.name ? `: ${a.name}` : ''} (bot không đọc nội dung đính kèm)
              </div>
            ),
          )}
          {!m.text && m.attachments.length === 0 && <div className="muted small">[{m.kind}]</div>}
        </li>
      ))}
    </ol>
  );
}

function CheckerBox({ draft }: { draft: DraftView }) {
  const ch = draft.checker;
  if (ch.passed) return <div className="checker ok">Bước kiểm tra trước khi gửi: không thấy lỗi.</div>;
  return (
    <div className="checker bad">
      <strong>Bước kiểm tra trước khi gửi báo lỗi:</strong>
      <ul>
        {ch.issues.map((i, n) => (
          <li key={n}>
            {CHECKER_RULE_LABEL[i.rule] ?? i.rule}: {i.detail}
            {i.excerpt ? ` ("${i.excerpt}")` : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Checker issues that still apply after staff removed some menu images: an image issue names its key in `excerpt`,
 * and the server re-runs the checker on approve with the kept images only.
 */
export function remainingIssues(draft: DraftView, kept: string[]): DraftView['checker']['issues'] {
  return draft.checker.issues.filter((i) => !(i.rule === 'menu_image' && i.excerpt && (draft.attachments ?? []).includes(i.excerpt) && !kept.includes(i.excerpt)));
}

function DraftCard(props: { api: Api; draft: DraftView; mode: ConversationMode; menu: MenuImagesIndex | null; onDone: () => void }) {
  const { api, draft, mode, menu, onDone } = props;
  const act = useAction();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.text);
  const [override, setOverride] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const images = draft.attachments ?? [];
  const [kept, setKept] = useState<string[]>(images);
  const draftOnly = mode === 'draft_only';
  const needsOverride = !draft.checker.passed && remainingIssues(draft, kept).length > 0;

  const finish = async (fn: () => Promise<unknown>, ok: string) => {
    const r = await act.run(fn, ok);
    if (r !== undefined) {
      setEditing(false);
      onDone();
    }
  };

  const send = (finalText: string | undefined) => {
    if (draftOnly) {
      // draft_only: approve is refused (409 mode_draft_only); staff send by hand from the draft and keep the bot active.
      return finish(
        () => api.manualSend(draft.conversation_id, { text: finalText ?? draft.text, from_draft_id: draft.id, keep_bot_active: true }),
        'Đã gửi tay từ bản nháp.',
      );
    }
    return finish(
      () =>
        api.approveDraft(draft.id, {
          text: finalText,
          override_checker: override || undefined,
          // the images staff kept; omitted for a draft without images (older servers ignore it)
          ...(images.length ? { attachments: kept } : {}),
        }),
      'Đã duyệt và gửi.',
    );
  };

  const failedCheck =
    act.raw instanceof ApiError && act.raw.code === 'checker_failed' ? (act.raw.details?.checker as DraftView['checker'] | undefined) : undefined;

  return (
    <div className={`draft ${draft.status}`}>
      <div className="muted small">
        {fmtTime(draft.created_at)} · {DRAFT_STATUS_LABEL[draft.status]}
        {draft.account_label ? ` · tài khoản ${draft.account_label}` : ''}
      </div>
      {editing ? (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} aria-label="Sửa bản nháp" />
      ) : (
        <div className="text">{draft.text}</div>
      )}
      {images.length > 0 && <DraftImages api={api} keys={images} kept={kept} index={menu} disabled={act.busy} onChange={setKept} />}
      <CheckerBox draft={draft} />
      {!draft.checker.passed && !needsOverride && !draftOnly && (
        <div className="muted small">Lỗi của bước kiểm tra chỉ nằm ở ảnh đã bỏ; máy chủ kiểm lại khi duyệt.</div>
      )}
      {needsOverride && !draftOnly && (
        <label className="small">
          <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} /> Vẫn gửi dù bước kiểm tra báo lỗi
          (thao tác được ghi vào nhật ký)
        </label>
      )}
      {draftOnly && <div className="muted small">Hội thoại ở chế độ chỉ soạn nháp: nút gửi sẽ gửi tay và bot vẫn tiếp tục trả lời.</div>}
      {draftOnly && images.length > 0 && (
        <div className="muted small">Gửi tay chỉ gửi chữ, không gửi ảnh menu của bản nháp. Muốn gửi ảnh, dùng nút Gửi menu bên dưới.</div>
      )}
      <div className="actions">
        {editing ? (
          <>
            <button disabled={act.busy || !text.trim()} onClick={() => send(text.trim())}>
              Gửi bản đã sửa
            </button>
            <button
              className="secondary"
              disabled={act.busy}
              onClick={() => {
                setEditing(false);
                setText(draft.text);
              }}
            >
              Hủy sửa
            </button>
          </>
        ) : (
          <>
            <button disabled={act.busy || (needsOverride && !override && !draftOnly)} onClick={() => send(undefined)}>
              {draftOnly ? 'Gửi tay bản này' : 'Duyệt và gửi'}
            </button>
            <button className="secondary" disabled={act.busy} onClick={() => setEditing(true)}>
              Sửa rồi gửi
            </button>
          </>
        )}
        <input
          className="reason"
          placeholder="Lý do từ chối (không bắt buộc)"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
        <button
          className="danger"
          disabled={act.busy}
          onClick={() => finish(() => api.rejectDraft(draft.id, rejectReason.trim() || undefined), 'Đã từ chối bản nháp.')}
        >
          Từ chối
        </button>
      </div>
      <ErrorLine text={act.error} />
      {failedCheck && <CheckerBox draft={{ ...draft, checker: failedCheck }} />}
    </div>
  );
}

function ManualSend(props: { api: Api; conversationId: string; onDone: () => void }) {
  const act = useAction();
  const [text, setText] = useState('');
  const [keepBot, setKeepBot] = useState(false);
  const submit = async () => {
    const r = await act.run(
      () => props.api.manualSend(props.conversationId, { text: text.trim(), keep_bot_active: keepBot }),
      keepBot ? 'Đã gửi. Bot vẫn tiếp tục trả lời.' : 'Đã gửi. Hội thoại chuyển sang nhân viên đang xử lý trong 12 giờ.',
    );
    if (r !== undefined) {
      setText('');
      props.onDone();
    }
  };
  return (
    <div className="manual-send">
      <h3>Nhân viên gửi tin</h3>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="Nhập tin gửi cho khách" aria-label="Tin gửi tay" />
      <label className="small">
        <input type="checkbox" checked={keepBot} onChange={(e) => setKeepBot(e.target.checked)} /> Giữ bot tiếp tục trả lời sau tin này.
        Nếu không chọn, bot ngừng soạn nháp cho hội thoại này trong 12 giờ.
      </label>
      <div className="actions">
        <button disabled={act.busy || !text.trim()} onClick={submit}>
          Gửi tin
        </button>
      </div>
      <ErrorLine text={act.error} />
      <Notice text={act.notice} />
    </div>
  );
}
