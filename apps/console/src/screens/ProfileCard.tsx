// Contact profile card of a personal Zalo conversation (docs/contracts.md section 13).
// Profiles come from scripts/analyze_contacts.py (rules only, on the Mac) or from staff edits here.
// Display names and evidence snippets come from old chats: rendered as React text nodes only, never as HTML.
import { useState } from 'react';
import type { Api, CustomerProfileView, ProfileAddressTerm, ProfilePatchRequest, ProfileRelationship, ProfileService, ProfileStats } from '../api';
import { ApiError } from '../api';
import { useAction } from '../hooks';
import {
  ADDRESS_TERMS,
  CONFIDENCE_LABEL,
  EVIDENCE_FROM_LABEL,
  EVIDENCE_KIND_LABEL,
  LAST_SERVICE_SOURCE_LABEL,
  QUIET_RELATIONSHIPS,
  RELATIONSHIPS,
  RELATIONSHIP_LABEL,
  SERVICE_STATUS_LABEL,
  STAFF_FIELD_LABEL,
  addressText,
  type Badge,
  fmtDate,
  fmtTime,
  profileReason,
} from '../labels';
import { Badges, ErrorLine, Notice } from './common';

/** Same rule as the server (src/lib/profiles.ts): one word of letters, at most 20 characters. */
export const PROFILE_NAME_RE = /^\p{L}{1,20}$/u;

const RELATIONSHIP_OPTION: Record<ProfileRelationship, string> = {
  customer: 'khách',
  staff: 'nhân viên của studio',
  family: 'gia đình',
  friend: 'bạn bè',
  personal: 'người quen (nhãn cũ; chọn gia đình, bạn bè hoặc nhân viên)',
  unknown: 'chưa rõ',
};

/** Options of the relationship select: the five current kinds, plus the legacy 'personal' only while it is the value. */
export function relationshipOptions(current: ProfileRelationship): ProfileRelationship[] {
  return current === 'personal' ? [...RELATIONSHIPS, 'personal'] : RELATIONSHIPS;
}

/** "Dịch vụ lần trước" line of the card: name, date, where it comes from, and whether the bot may see it. */
export function lastServiceText(p: CustomerProfileView): string | null {
  const l = p.last_service;
  if (!l) return null;
  const parts = [l.name, fmtDate(l.at), l.source === 'chat' ? `${LAST_SERVICE_SOURCE_LABEL.chat}, ${CONFIDENCE_LABEL[l.confidence]}` : LAST_SERVICE_SOURCE_LABEL.visit];
  if (l.sensitive) parts.push('nhóm nhạy cảm, bot không thấy');
  return parts.join(' · ');
}

export interface ProfileForm {
  relationship: ProfileRelationship;
  address: ProfileAddressTerm | '';
  name: string;
}

/**
 * The form as it opens. A low-confidence address guess is not filled in: saving the form would otherwise store the
 * guess as staff-confirmed (confidence 'high') and send it to the bot.
 */
export function profileFormOf(p: CustomerProfileView | null): ProfileForm {
  return {
    relationship: p?.relationship ?? 'unknown',
    address: p && p.address_confidence !== 'low' ? (p.address_term ?? '') : '',
    name: p?.name_to_use ?? '',
  };
}

/**
 * The PATCH body of a saved form: only the fields that differ from how the form opened, so a save marks only those
 * as staff-edited (the server keeps them across analyzer runs and sets a chosen term to confidence 'high').
 * null: the name is invalid. An empty object: nothing changed.
 */
export function profilePatchFromForm(form: ProfileForm, initial: ProfileForm): ProfilePatchRequest | null {
  const name = form.name.normalize('NFC').trim();
  if (name && !PROFILE_NAME_RE.test(name)) return null;
  const out: ProfilePatchRequest = {};
  if (form.relationship !== initial.relationship) out.relationship = form.relationship;
  if (form.address !== initial.address) out.address_term = form.address || null;
  if (name !== initial.name.normalize('NFC').trim()) out.name_to_use = name || null;
  return out;
}

/** "Xác nhận" of what the card shows: the relationship, the address term and the name, as staff-confirmed values. */
export function profileConfirmPatch(p: CustomerProfileView): ProfilePatchRequest {
  const out: ProfilePatchRequest = { relationship: p.relationship };
  if (p.address_term) out.address_term = p.address_term;
  if (p.name_to_use) out.name_to_use = p.name_to_use;
  return out;
}

function staffFieldsText(p: CustomerProfileView): string {
  if (!p.staff_override) return 'Chưa. Lần chạy script sau có thể thay quan hệ, cách gọi, tên và danh sách dịch vụ.';
  const fields = p.staff_fields;
  if (!fields || fields.length === 0) return 'Có. Script phân tích không ghi đè quan hệ, cách gọi, tên và danh sách dịch vụ của người này.';
  const all = fields.length === 4;
  const list = fields.map((f) => STAFF_FIELD_LABEL[f]).join(', ');
  return all
    ? `Có: ${list}. Script phân tích không ghi đè các mục này nữa.`
    : `Có: ${list}. Script phân tích không ghi đè các mục này; các mục khác vẫn theo lần chạy script sau.`;
}

/** 409 from a server whose local D1 does not have migration 0007 (or 0008 for staff, family and friend) yet. */
function missingTableText(raw: unknown): string | null {
  if (raw instanceof ApiError && raw.status === 409 && /0008_profiles_v2/.test(raw.message)) {
    return 'Máy chủ chưa áp migration 0008_profiles_v2.sql, nên chưa lưu được loại nhân viên, gia đình hay bạn bè. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi lưu lại.';
  }
  if (raw instanceof ApiError && raw.status === 409 && /customer_profiles/.test(raw.message)) {
    return 'Máy chủ chưa có bảng hồ sơ liên hệ vì chưa áp migration 0007_customer_profiles.sql. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi lưu lại.';
  }
  return null;
}

function profileBadges(p: CustomerProfileView): Badge[] {
  const kind = p.relationship === 'customer' ? 'bot' : QUIET_RELATIONSHIPS.includes(p.relationship) ? 'staff' : 'muted';
  const out: Badge[] = [{ kind, text: RELATIONSHIP_LABEL[p.relationship] }];
  if (p.staff_override) out.push({ kind: 'pending', text: 'nhân viên đã sửa' });
  return out;
}

function modelFactsText(p: CustomerProfileView): string {
  const f = p.model_facts;
  if (!f) {
    return QUIET_RELATIONSHIPS.includes(p.relationship)
      ? 'Bot không nhận thông tin nào: hồ sơ gia đình, nhân viên và bạn bè không được gửi cho bot.'
      : 'Bot không nhận thông tin nào: hồ sơ chưa có cách gọi đủ chắc chắn hay dịch vụ nào bot được biết.';
  }
  const parts = [`gọi là ${f.address_term ?? 'anh/chị (mặc định)'}`];
  if (f.name_to_use) parts.push(`tên ${f.name_to_use}`);
  if (f.services_likely_used.length) parts.push(`dịch vụ có thể đã dùng: ${f.services_likely_used.join(', ')}`);
  if (f.services_mentioned.length) parts.push(`dịch vụ từng hỏi: ${f.services_mentioned.join(', ')}`);
  if (f.last_service) parts.push(`dịch vụ lần trước: ${f.last_service.name} (${f.last_service.date.split('-').reverse().join('/')})`);
  return `${parts.join('; ')}.`;
}

function statsText(s: ProfileStats): string | null {
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const parts: string[] = [];
  const inn = num(s.messages_in);
  const out = num(s.messages_out);
  if (inn !== null || out !== null) parts.push(`người này gửi ${inn ?? 0} tin, chủ tài khoản gửi ${out ?? 0} tin`);
  const first = num(s.first_at);
  const last = num(s.last_at);
  if (first !== null && last !== null) parts.push(`từ ${fmtDate(first)} đến ${fmtDate(last)}`);
  const days = num(s.active_days);
  if (days !== null) parts.push(`${days} ngày có nhắn`);
  if (s.first_writer === 'contact') parts.push('người này nhắn trước');
  if (s.first_writer === 'owner') parts.push('chủ tài khoản nhắn trước');
  return parts.length ? parts.join(' · ') : null;
}

function serviceLine(s: ProfileService): string {
  const parts = [s.name];
  if (s.status === 'likely_used' && s.used_signal_count > 0) {
    parts.push(`dấu hiệu đã dùng ${s.used_signal_count} lần${s.last_used_signal_at ? `, gần nhất ${fmtDate(s.last_used_signal_at)}` : ''}`);
  }
  parts.push(`nhắc ${s.mention_count} lần${s.last_mentioned_at ? `, gần nhất ${fmtDate(s.last_mentioned_at)}` : ''}`);
  if (s.sensitive) parts.push('nhóm nhạy cảm, bot không thấy');
  return parts.join(' · ');
}

function ServiceGroup({ title, items }: { title: string; items: ProfileService[] }) {
  if (items.length === 0) return null;
  return (
    <div className="profile-services">
      <h4>{title}</h4>
      <ul>
        {items.map((s) => (
          <li key={s.key}>{serviceLine(s)}</li>
        ))}
      </ul>
    </div>
  );
}

export function ProfileCard(props: { api: Api; zaloUserId: string; profile: CustomerProfileView | null; onSaved: () => void }) {
  const { api, zaloUserId, profile: p, onSaved } = props;
  const act = useAction();
  const [form, setForm] = useState<ProfileForm | null>(null);
  const [initial, setInitial] = useState<ProfileForm | null>(null);

  const patch = form && initial ? profilePatchFromForm(form, initial) : null;
  const nameBad = form !== null && patch === null;
  const unchanged = patch !== null && Object.keys(patch).length === 0;

  const startEdit = () => {
    const f = profileFormOf(p);
    setInitial(f);
    setForm(f);
  };

  const save = async () => {
    if (!patch || unchanged) return;
    const r = await act.run(
      () => api.patchProfile(zaloUserId, patch),
      'Đã lưu hồ sơ. Script phân tích không ghi đè các mục vừa sửa nữa.',
    );
    if (r !== undefined) {
      setForm(null);
      onSaved();
    }
  };

  const confirm = async () => {
    if (!p) return;
    const r = await act.run(
      () => api.patchProfile(zaloUserId, profileConfirmPatch(p)),
      'Đã xác nhận quan hệ và cách gọi ở mức chắc chắn cao. Script phân tích không ghi đè các mục này nữa.',
    );
    if (r !== undefined) onSaved();
  };
  const canConfirm = !!p && (p.relationship_confidence !== 'high' || (p.address_term !== null && p.address_confidence !== 'high'));

  const clearOverride = async () => {
    const r = await act.run(
      () => api.patchProfile(zaloUserId, { staff_override: false }),
      p?.analyzer
        ? 'Đã bỏ phần nhân viên sửa: hồ sơ dùng lại kết quả của lần chạy script gần nhất.'
        : 'Đã bỏ dấu nhân viên sửa. Hồ sơ này chưa có kết quả script, nên lần chạy script sau sẽ ghi vào hồ sơ.',
    );
    if (r !== undefined) onSaved();
  };

  const services = p?.services ?? [];
  const used = services.filter((s) => s.status === 'likely_used');
  const mentioned = services.filter((s) => s.status !== 'likely_used');
  const stats = p ? statsText(p.stats ?? {}) : null;
  const a = p?.analyzer;

  return (
    <section className="box profile" aria-label="Hồ sơ liên hệ">
      <div className="row between">
        <h3>Hồ sơ liên hệ</h3>
        {p && <Badges badges={profileBadges(p)} />}
      </div>

      {!p ? (
        <p className="muted small">
          Chưa có hồ sơ liên hệ cho người này. Hồ sơ được lập khi chủ tài khoản chạy scripts/analyze_contacts.py --push trên máy, hoặc khi
          nhân viên tạo hồ sơ ở đây.
        </p>
      ) : (
        <>
          <dl className="facts">
            <dt>Người này là</dt>
            <dd>
              {RELATIONSHIP_LABEL[p.relationship]} ({CONFIDENCE_LABEL[p.relationship_confidence]})
            </dd>
            {p.relationship_reasons.length > 0 && (
              <>
                <dt>Căn cứ của script</dt>
                <dd>{p.relationship_reasons.map(profileReason).join('; ')}</dd>
              </>
            )}
            <dt>Bot gọi người này là</dt>
            <dd>
              {addressText(p.address_term, p.name_to_use)} ({CONFIDENCE_LABEL[p.address_confidence]})
            </dd>
            {lastServiceText(p) && (
              <>
                <dt>Dịch vụ lần trước</dt>
                <dd>{lastServiceText(p)}</dd>
              </>
            )}
            <dt>Bot được biết khi soạn nháp</dt>
            <dd>{modelFactsText(p)}</dd>
            {stats && (
              <>
                <dt>Tin nhắn cũ</dt>
                <dd>{stats}</dd>
              </>
            )}
            <dt>Nguồn</dt>
            <dd>
              {p.source === 'staff' ? 'Nhân viên tạo hồ sơ' : 'Script phân tích tạo hồ sơ'}
              {p.analyzed_at ? `; script chạy gần nhất lúc ${fmtTime(p.analyzed_at)}` : ''}
              {p.analyzer_version ? ` (${p.analyzer_version})` : ''}. Cập nhật gần nhất: {p.updated_by}, {fmtTime(p.updated_at)}.
            </dd>
            <dt>Nhân viên đã sửa</dt>
            <dd>{staffFieldsText(p)}</dd>
            {p.staff_override && a && (
              <>
                <dt>Script đoán</dt>
                <dd>
                  {RELATIONSHIP_LABEL[a.relationship]} ({CONFIDENCE_LABEL[a.relationship_confidence]}), gọi là{' '}
                  {addressText(a.address_term, a.name_to_use)}
                </dd>
              </>
            )}
            {p.staff_note && (
              <>
                <dt>Ghi chú của nhân viên</dt>
                <dd>{p.staff_note}</dd>
              </>
            )}
          </dl>

          {services.length === 0 ? (
            <p className="muted small">Người này chưa nhắc tới dịch vụ nào trong tin nhắn cũ.</p>
          ) : (
            <>
              <ServiceGroup title={`Dịch vụ ${SERVICE_STATUS_LABEL.likely_used}`} items={used} />
              <ServiceGroup title={`Dịch vụ ${SERVICE_STATUS_LABEL.mentioned}`} items={mentioned} />
            </>
          )}

          {p.evidence.length > 0 && (
            <div className="profile-evidence">
              <h4>Đoạn trích làm căn cứ</h4>
              <ul>
                {p.evidence.slice(0, 3).map((e, i) => (
                  <li key={i}>
                    <div className="muted small">
                      {fmtDate(e.at)} · {EVIDENCE_FROM_LABEL[e.from]} · {EVIDENCE_KIND_LABEL[e.kind]}
                    </div>
                    <div className="text">{e.text}</div>
                  </li>
                ))}
              </ul>
              <p className="muted small">Đoạn trích chỉ hiện cho nhân viên và không được gửi cho bot. Số điện thoại đã được che.</p>
            </div>
          )}
        </>
      )}

      {form ? (
        <div className="form profile-form">
          <label>
            Người này là
            <select
              aria-label="Người này là"
              value={form.relationship}
              disabled={act.busy}
              onChange={(e) => setForm({ ...form, relationship: e.target.value as ProfileRelationship })}
            >
              {relationshipOptions(initial?.relationship ?? form.relationship).map((r) => (
                <option key={r} value={r}>
                  {RELATIONSHIP_OPTION[r]}
                </option>
              ))}
            </select>
          </label>
          {QUIET_RELATIONSHIPS.includes(form.relationship) && (
            <p className="muted small">
              Khi cờ profile_personal_skip_bot = true (mặc định) và người này chưa đồng ý trò chuyện với trợ lý AI, tin kế tiếp của họ chuyển
              hội thoại sang chỉ nhân viên trả lời. Bot không gửi tin xin đồng ý và không nhận thông tin nào từ hồ sơ gia đình, nhân viên
              hay bạn bè. Loại người do nhân viên chọn được ghi ở mức chắc chắn cao, nên quy tắc này áp dụng ngay.
            </p>
          )}
          <label>
            Bot gọi người này là
            <select
              aria-label="Bot gọi người này là"
              value={form.address}
              disabled={act.busy}
              onChange={(e) => setForm({ ...form, address: e.target.value as ProfileAddressTerm | '' })}
            >
              <option value="">chưa xác định (bot gọi anh/chị)</option>
              {ADDRESS_TERMS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          {p && p.address_term && p.address_confidence === 'low' && (
            <p className="muted small">
              Script đoán cách gọi {p.address_term} ở mức chắc chắn thấp, nên bot chưa dùng cách gọi này và ô trên để trống. Chỉ chọn khi biết
              chắc.
            </p>
          )}
          <label>
            Tên để gọi
            <input
              aria-label="Tên để gọi"
              value={form.name}
              disabled={act.busy}
              placeholder="Một từ, ví dụ Lan. Để trống nếu không gọi tên."
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          {nameBad && <p className="error">Tên phải là một từ, chỉ gồm chữ cái, tối đa 20 ký tự.</p>}
          <p className="muted small">
            Bot chỉ gọi tên khi cách gọi là chị, anh, cô, chú hoặc bác. Chỉ những ô đã đổi được lưu: quan hệ hoặc cách gọi vừa chọn được ghi ở
            mức chắc chắn cao, và script phân tích không ghi đè các ô đó nữa. Các ô không đổi vẫn theo script.
          </p>
          {unchanged && <p className="muted small">Chưa có ô nào thay đổi.</p>}
          <div className="actions">
            <button disabled={act.busy || !patch || unchanged} onClick={save}>
              Lưu hồ sơ
            </button>
            <button className="secondary" disabled={act.busy} onClick={() => setForm(null)}>
              Hủy sửa
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="secondary" disabled={act.busy} onClick={startEdit}>
            {p ? 'Sửa hồ sơ' : 'Tạo hồ sơ'}
          </button>
          {p && canConfirm && (
            <button
              className="secondary"
              disabled={act.busy}
              title={`Ghi quan hệ ${RELATIONSHIP_LABEL[p.relationship]} và cách gọi ${addressText(p.address_term, p.name_to_use)} ở mức chắc chắn cao; script phân tích không ghi đè các mục này nữa.`}
              onClick={confirm}
            >
              Xác nhận quan hệ và cách gọi đang hiện
            </button>
          )}
          {p?.staff_override && (
            <button
              className="secondary"
              disabled={act.busy}
              title="Bỏ dấu nhân viên sửa. Quan hệ, cách gọi, tên và danh sách dịch vụ lấy lại theo lần chạy script gần nhất; các lần chạy sau được ghi đè."
              onClick={clearOverride}
            >
              Bỏ phần nhân viên sửa, dùng kết quả script
            </button>
          )}
        </div>
      )}
      <ErrorLine text={missingTableText(act.raw) ?? act.error} />
      <Notice text={act.notice} />
    </section>
  );
}
