// Optional fields of a recorded visit (docs/contracts.md section 14.5): amount, technician, duration and a benefit to use.
// Shared by the "Ghi nhận buổi làm" tab and the customer summary block of a conversation.
import { useEffect, useState } from 'react';
import type { Api, CustomerBenefit, SummaryBenefit, VisitRequest } from '../api';
import { ApiError } from '../api';
import { migration0010Text } from '../errors';
import { BENEFIT_KIND_LABEL, fmtDate, fmtYmd, parseVnd, vndInputText } from '../labels';

export const TECHNICIAN_MAX = 60;
const DURATION_MAX_MIN = 24 * 60;

export interface VisitExtras {
  amount: string; // as shown in the field, e.g. "450.000"
  technician: string;
  duration: string;
  benefitId: string;
}

export const EMPTY_VISIT_EXTRAS: VisitExtras = { amount: '', technician: '', duration: '', benefitId: '' };

export interface BenefitChoice {
  id: string;
  label: string;
}

/** The first problem in the optional fields, as a sentence for staff; null when they can be sent. */
export function visitExtrasProblem(x: VisitExtras): string | null {
  if (x.amount.trim() !== '' && parseVnd(x.amount) === null) return 'Số tiền quá lớn hoặc không phải số.';
  const technician = x.technician.trim();
  if (technician.length > TECHNICIAN_MAX || /[\r\n]/.test(technician)) {
    return `Tên kỹ thuật viên viết trên một dòng, tối đa ${TECHNICIAN_MAX} ký tự.`;
  }
  const duration = x.duration.trim();
  if (duration !== '') {
    const n = Number(duration);
    if (!/^\d+$/.test(duration) || n <= 0 || n > DURATION_MAX_MIN) return 'Thời lượng là số phút, lớn hơn 0.';
  }
  return null;
}

/** Only the fields staff filled in, so a server before 2026-11-12 gets the same body as before. */
export function visitExtrasPayload(x: VisitExtras): Pick<VisitRequest, 'amount_vnd' | 'technician' | 'duration_min' | 'benefit_id'> {
  const out: Pick<VisitRequest, 'amount_vnd' | 'technician' | 'duration_min' | 'benefit_id'> = {};
  const amount = x.amount.trim() === '' ? null : parseVnd(x.amount);
  if (amount !== null) out.amount_vnd = amount;
  const technician = x.technician.trim();
  if (technician) out.technician = technician;
  if (x.duration.trim() !== '') out.duration_min = Number(x.duration.trim());
  if (x.benefitId) out.benefit_id = x.benefitId;
  return out;
}

/** Error line of a failed POST /staff/visits: the migration and the benefit cases get their own sentence. */
export function visitErrorText(raw: unknown, fallback: string | null, x: VisitExtras): string | null {
  const migration = migration0010Text(raw, 'lưu được buổi làm');
  if (migration) return migration;
  if (raw instanceof ApiError && raw.status === 409 && raw.code === 'invalid_state' && x.benefitId) {
    return 'Quyền lợi đã chọn không dùng được nữa: đã hủy, hết hạn hoặc hết lượt. Bỏ chọn quyền lợi rồi ghi lại.';
  }
  return fallback;
}

export function summaryBenefitText(b: Pick<SummaryBenefit, 'title' | 'remaining' | 'expires_on'>): string {
  return `${b.title}: còn ${b.remaining} lần${b.expires_on ? `, hạn ${fmtYmd(b.expires_on)}` : ', không có hạn'}`;
}

export function benefitRemaining(b: CustomerBenefit): number {
  return typeof b.remaining === 'number' ? b.remaining : b.total_count - b.used_count;
}

export function benefitExpired(b: CustomerBenefit, now = Date.now()): boolean {
  return typeof b.expires_at === 'number' && b.expires_at < now;
}

/** Benefits a visit can use now: active, not expired, with a use left. */
export function usableBenefitChoices(list: CustomerBenefit[], now = Date.now()): BenefitChoice[] {
  return list
    .filter((b) => b.status === 'active' && benefitRemaining(b) > 0 && !benefitExpired(b, now))
    .map((b) => ({
      id: b.id,
      label: `${b.title} (${BENEFIT_KIND_LABEL[b.kind] ?? b.kind}): còn ${benefitRemaining(b)} lần${b.expires_at ? `, hạn ${fmtDate(b.expires_at)}` : ''}`,
    }));
}

/**
 * Benefits of one customer that a visit can use. Empty while loading, without a customer, on a server before 2026-11-12
 * (404) and before migration 0010 (409): the benefit field then simply does not show.
 */
export function useUsableBenefits(api: Api, customerId: string): BenefitChoice[] {
  const [choices, setChoices] = useState<BenefitChoice[]>([]);
  useEffect(() => {
    let alive = true;
    setChoices([]);
    if (!customerId) return;
    api
      .listBenefits(customerId)
      .then((r) => {
        if (alive) setChoices(usableBenefitChoices(r.benefits ?? []));
      })
      .catch(() => {
        // an older server has no benefits: the visit form works without them
      });
    return () => {
      alive = false;
    };
  }, [api, customerId]);
  return choices;
}

export function VisitExtraFields(props: { value: VisitExtras; onChange: (next: VisitExtras) => void; benefits: BenefitChoice[] }) {
  const { value: x, onChange, benefits } = props;
  return (
    <>
      <label>
        Số tiền khách trả (đồng, không bắt buộc)
        <input
          inputMode="numeric"
          autoComplete="off"
          placeholder="450.000"
          value={x.amount}
          onChange={(e) => onChange({ ...x, amount: vndInputText(e.target.value) })}
        />
      </label>
      <label>
        Kỹ thuật viên (không bắt buộc)
        <input
          maxLength={TECHNICIAN_MAX}
          autoComplete="off"
          value={x.technician}
          onChange={(e) => onChange({ ...x, technician: e.target.value })}
        />
      </label>
      <label>
        Thời lượng (phút, không bắt buộc)
        <input inputMode="numeric" autoComplete="off" placeholder="60" value={x.duration} onChange={(e) => onChange({ ...x, duration: e.target.value })} />
      </label>
      {benefits.length > 0 && (
        <label>
          Dùng quyền lợi (không bắt buộc)
          <select value={x.benefitId} onChange={(e) => onChange({ ...x, benefitId: e.target.value })}>
            <option value="">Không dùng quyền lợi</option>
            {benefits.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>
          <span className="muted small">Chọn một quyền lợi thì buổi làm này dùng một lần của quyền lợi đó.</span>
        </label>
      )}
    </>
  );
}
