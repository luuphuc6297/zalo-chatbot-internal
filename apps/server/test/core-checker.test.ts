// server-core: pre-send checker rules 1-5 (pure function).
import { describe, expect, it } from 'vitest';
import { checkDraft, findTerm } from '../src/checker';
import type { CheckerInput } from '../src/types';

const base: Omit<CheckerInput, 'text'> = {
  conversation_id: 'cnv_t',
  catalog_version: 'cv_t',
  allowed_price_texts: ['199.000đ', '229.000đ'],
  approved_contact_values: ['https://maps.app.goo.gl/Xo43VT6JYEtxxCNf9', 'beacons.ai/thomhouseq7'],
  display_names: ['Gội đầu thư giãn', 'Diện chẩn ngừa đột quỵ', 'Bài thuốc gội đầu (tên giả để thử)'],
};
const check = (text: string, over: Partial<CheckerInput> = {}) => checkDraft({ ...base, ...over, text }, 1);
const rules = (text: string, over: Partial<CheckerInput> = {}) => check(text, over).issues.map((i) => i.rule);

describe('checkDraft', () => {
  it('passes a clean reply with grounded prices', () => {
    const r = check(
      'Dạ Gội đầu thư giãn 50 phút giá 199.000đ (9h – 20h30), 229.000đ (sau 20h30) ạ.\n- Anh/chị chưa chọn giờ thì em ghi yêu cầu để nhân viên xác nhận nha.',
    );
    expect(r).toEqual({ passed: true, issues: [], checked_at: 1 });
  });

  it('catches ungrounded prices and k / triệu amounts', () => {
    expect(check('Dạ giá 250.000đ ạ.').issues).toEqual([expect.objectContaining({ rule: 'price', excerpt: '250.000đ' })]);
    expect(rules('Dạ giá 199k ạ.')).toEqual(['price']);
    expect(rules('Dạ khoảng 2,5 triệu ạ.')).toEqual(['price']);
    expect(rules('Dạ giá 199.000 đồng ạ.')).toEqual([]); // same amount as a tool price_text
    expect(rules('Dạ giá 3.199.000đ ạ.')).toEqual(['price']); // not the tail of a longer number
  });

  it('catches amounts without dot separators or without a unit', () => {
    expect(check('Dạ gội đầu giá 150000đ ạ.').issues).toEqual([expect.objectContaining({ rule: 'price', excerpt: '150000đ' })]);
    expect(rules('Dạ gội đầu giá 150,000đ ạ.')).toEqual(['price']);
    expect(rules('Dạ gội đầu giá 150.000 ạ.')).toEqual(['price']);
    expect(rules('Dạ gội đầu giá 150 000 đồng ạ.')).toEqual(['price']);
    expect(rules('Dạ gội đầu giá 150000 ạ.')).toEqual(['price']);
    // grounded amounts pass in any of these spellings
    expect(rules('Dạ giá 199000đ ạ.')).toEqual([]);
    expect(rules('Dạ giá 199,000 ạ.')).toEqual([]);
    expect(rules('Dạ giá 199.000 ạ.')).toEqual([]);
    // not money: durations, times, a year, an approved link, a date
    expect(rules('Dạ gói 90 phút, mở 9h-20h30 năm 2026, ngày 07/11/2026 ạ.')).toEqual([]);
    expect(rules('Dạ chỉ đường: https://maps.app.goo.gl/Xo43VT6JYEtxxCNf9 ạ.')).toEqual([]);
    // a phone number is judged by the contact rule, not the price rule
    expect(rules('Dạ gọi 0912345678 ạ.')).toEqual(['contact_info']);
  });

  it('catches markdown and over-long replies', () => {
    expect(rules('**Gội đầu thư giãn**')).toContain('format');
    expect(rules('# Menu')).toContain('format');
    expect(rules('| dịch vụ | giá |')).toContain('format');
    expect(rules('a'.repeat(1801))).toEqual(['length']);
    expect(rules('   ')).toEqual(['empty']);
  });

  it('catches forbidden terms with and without diacritics, but not look-alike words', () => {
    expect(rules('Dịch vụ này giúp điều trị mất ngủ ạ.')).toContain('forbidden_term');
    expect(rules('dich vu nay chua khoi han dau lung')).toContain('forbidden_term');
    expect(rules('Bên em đảm bảo hiệu quả 100% ạ.').length).toBeGreaterThanOrEqual(2);
    expect(rules('Dạ bên em chưa có thông tin này ạ.')).toEqual([]); // chưa is not chữa
    expect(rules('Dạ em gửi vị trí trên bản đồ ạ.')).toEqual([]); // trí is not trị
    expect(rules('Phiếu có giá trị 30 ngày ạ.')).toEqual([]);
    expect(findTerm('Đây là cách TRỊ mụn', 'trị')).toBe('TRỊ');
  });

  it('allows a forbidden word only inside an exact catalog display name', () => {
    expect(rules('Dạ Bài thuốc gội đầu (tên giả để thử) 50 phút ạ.')).toEqual([]);
    expect(rules('Dạ bên em có bài thuốc gội đầu ạ.')).toContain('forbidden_term');
  });

  it('allows only approved contact values', () => {
    expect(rules('Dạ bản đồ: https://maps.app.goo.gl/Xo43VT6JYEtxxCNf9 ạ.')).toEqual([]);
    expect(rules('Dạ anh/chị xem beacons.ai/thomhouseq7 ạ.')).toEqual([]);
    expect(rules('Dạ anh/chị gọi 0901 234 567 nha.')).toEqual(['contact_info']);
    expect(rules('Dạ xem thêm tại thomhouse.vn ạ.')).toEqual(['contact_info']);
    expect(rules('Dạ email thom@gmail.com ạ.')).toEqual(['contact_info']);
    expect(rules('Dạ bên em ở TP.HCM, mở 09:00 ạ.')).toEqual([]);
  });

  it('catches booking confirmation promises', () => {
    expect(rules('Dạ em đã đặt lịch thành công cho chị ạ.')).toEqual(['booking_promise']);
    expect(rules('Dạ em đã giữ chỗ 19h cho anh ạ.')).toEqual(['booking_promise']);
    expect(rules('Dạ em đã ghi yêu cầu đặt lịch, nhân viên sẽ xác nhận giờ với chị ạ.')).toEqual([]);
  });
});
