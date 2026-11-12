// Per-conversation settings of docs/contracts.md section 14: the auto reply switch (14.4) and the contact role (14.3).
// Both keep working against an older server: a 404 or a 409 "apply migration 0010" becomes one calm sentence.
import { useState } from 'react';
import type { Api, ContactRole, ConversationRoom, ConversationSummary, RoleSource } from '../api';
import { ApiError } from '../api';
import { serverGapText } from '../errors';
import { useAction } from '../hooks';
import { AUTO_REPLY_TEXT, ROLES, ROLE_DOES, ROLE_LABEL, ROLE_SOURCE_LABEL, fmtTime, isInternalRole } from '../labels';
import { ErrorLine, Notice } from './common';

/**
 * The role the console shows for a conversation and where it comes from. The customer summary is the server's own
 * resolution (label or staff row first, then the profile); the conversation and the profile carry the same pair.
 */
export function resolveRole(
  ...sources: Array<{ role?: ContactRole | null; role_source?: RoleSource | null } | null | undefined>
): { role: ContactRole | null; source: RoleSource | null } {
  for (const s of sources) {
    if (s?.role) return { role: s.role, source: s.role_source ?? null };
  }
  return { role: null, source: null };
}

/**
 * True when the global auto_reply_mode is off: the conversation resolves to 'off' although its own mode is not 'off'
 * (resolution rule 1 of section 14.4). With the own mode 'off' the console cannot tell, and the switch stays usable:
 * switching on clears the own mode.
 */
export function globalModeOff(c: Pick<ConversationSummary, 'effective_mode' | 'mode_override'>): boolean {
  return c.effective_mode === 'off' && c.mode_override !== 'off';
}

export function AutoReplySwitch(props: { api: Api; conversation: ConversationSummary; role: ContactRole | null; onDone: () => void }) {
  const { api, conversation: c, role, onDone } = props;
  const act = useAction();
  const [confirming, setConfirming] = useState(false);
  const [attempt, setAttempt] = useState<'on' | 'off' | null>(null);

  const internal = isInternalRole(role);
  // An internal contact never gets a bot reply, so the switch reads off whatever the mode says.
  const on = !internal && c.effective_mode === 'auto_allowed';
  const globalOff = !internal && globalModeOff(c);
  const disabled = act.busy || internal || globalOff;

  const put = async (value: 'on' | 'off') => {
    setConfirming(false);
    setAttempt(value);
    const r = await act.run(() => api.setAutoReply(c.id, value), value === 'on' ? AUTO_REPLY_TEXT.turnedOn : AUTO_REPLY_TEXT.turnedOff);
    if (r !== undefined) onDone();
  };

  const raw = act.raw;
  const refusedInternal = attempt === 'on' && raw instanceof ApiError && raw.status === 409 && raw.code === 'invalid_state';
  const error = serverGapText(raw, 'đổi được công tắc tự động trả lời') ?? (refusedInternal ? AUTO_REPLY_TEXT.serverSaysInternal : act.error);

  return (
    <div className="auto-reply">
      <label className="switch-row">
        <input
          type="checkbox"
          role="switch"
          className="switch"
          aria-label={AUTO_REPLY_TEXT.title}
          checked={on}
          disabled={disabled}
          onChange={() => {
            if (on) void put('off');
            else setConfirming(true);
          }}
        />
        <strong>{AUTO_REPLY_TEXT.title}</strong>
        <span className={on ? 'badge bot' : 'badge muted'}>{on ? 'đang bật' : 'đang tắt'}</span>
      </label>
      <div className="muted small">
        {AUTO_REPLY_TEXT.meaning}
        {on ? ` ${AUTO_REPLY_TEXT.onDetail}` : ''}
      </div>
      {internal && <p className="muted small">{AUTO_REPLY_TEXT.internal}</p>}
      {globalOff && <p className="muted small">{AUTO_REPLY_TEXT.globalOff}</p>}
      {globalOff && c.auto_reply === 'on' && (
        <div className="row wrap">
          <span className="muted small">{AUTO_REPLY_TEXT.storedWhileGlobalOff}</span>
          <button className="secondary" disabled={act.busy} onClick={() => void put('off')}>
            {AUTO_REPLY_TEXT.clearStored}
          </button>
        </div>
      )}
      {confirming && !disabled && !on && (
        <div className="confirm-box" role="group" aria-label="Xác nhận bật tự động trả lời">
          <p>{AUTO_REPLY_TEXT.confirm}</p>
          <div className="actions">
            <button disabled={act.busy} onClick={() => void put('on')}>
              {AUTO_REPLY_TEXT.confirmYes}
            </button>
            <button className="secondary" disabled={act.busy} onClick={() => setConfirming(false)}>
              {AUTO_REPLY_TEXT.confirmNo}
            </button>
          </div>
        </div>
      )}
      <ErrorLine text={error} />
      <Notice text={act.notice} />
    </div>
  );
}

const ROLE_NOTICE: Record<ContactRole, string> = {
  customer: 'Đã đặt vai trò khách cho người này.',
  manager: 'Đã đặt vai trò quản lý: bot không trả lời người này nữa.',
  staff: 'Đã đặt vai trò nhân viên: bot không trả lời người này nữa.',
};

/**
 * "Vai trò" row of the detail: the role, where it comes from, and a select to set or clear the staff value.
 * Roles are keyed like contact profiles ('p:' + threadId), so the select shows for the personal Zalo channel only.
 * Renders nothing for another channel without a role.
 */
export function RoleRow(props: { api: Api; zaloUserId: string; role: ContactRole | null; source: RoleSource | null; onDone: () => void }) {
  const { api, zaloUserId, role, source, onDone } = props;
  const act = useAction();
  const canSet = zaloUserId.startsWith('p:');
  if (!canSet && !role) return null;
  // The select holds the value staff set here; a role from a Zalo label or from the profile is shown as text only.
  const staffValue = role && source === 'staff' ? role : '';

  const change = async (value: string) => {
    const next = value === '' ? null : (value as ContactRole);
    const r = await act.run(
      () => api.setRole(zaloUserId, next),
      next ? ROLE_NOTICE[next] : 'Đã bỏ vai trò lễ tân đặt. Vai trò lấy lại theo nhãn Zalo hoặc hồ sơ liên hệ, nếu có.',
    );
    if (r !== undefined) onDone();
  };

  return (
    <div className="role-row">
      <div className="row wrap">
        <span>
          Vai trò: <strong>{role ? ROLE_LABEL[role] : 'chưa có'}</strong>
          {role && source ? ` (nguồn: ${ROLE_SOURCE_LABEL[source]})` : ''}
        </span>
        {canSet && (
          <label className="row">
            <span className="muted small">Lễ tân đặt:</span>
            <select aria-label="Vai trò" value={staffValue} disabled={act.busy} onChange={(e) => void change(e.target.value)}>
              <option value="">Không đặt (theo nhãn Zalo hoặc hồ sơ)</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {role && <div className="muted small">{ROLE_DOES[role]}</div>}
      <ErrorLine text={serverGapText(act.raw, 'lưu được vai trò') ?? act.error} />
      <Notice text={act.notice} />
    </div>
  );
}

/** One line of the detail header for a conversation that has a two-bot room (section 14.7). */
export function roomLine(room: ConversationRoom): string {
  const parts = [`Phòng hai bot: mã phòng ${room.channel_id}`];
  parts.push(typeof room.synced_at === 'number' ? `đồng bộ gần nhất lúc ${fmtTime(room.synced_at)}` : 'chưa đồng bộ lần nào');
  if (typeof room.pending === 'number') parts.push(room.pending > 0 ? `${room.pending} tin chưa đưa vào phòng` : 'không còn tin nào chờ đưa vào phòng');
  return parts.join(' · ');
}
