import { ApiError } from './api';

const CODE_TEXT: Record<string, string> = {
  unauthorized: 'Staff token sai hoặc chưa nhập. Mở Cài đặt để sửa.',
  not_found: 'Không tìm thấy (có thể đã bị xóa hoặc sai địa chỉ máy chủ).',
  invalid_state: 'Trạng thái đã thay đổi, thao tác này không còn hợp lệ. Danh sách sẽ tự tải lại.',
  mode_draft_only: 'Hội thoại đang ở chế độ chỉ soạn nháp: không duyệt gửi được, hãy gửi tay.',
  outbound_disabled: 'Công tắc gửi tin đang chặn mọi tin gửi đi (outbound_enabled = false).',
  outside_cs_window: 'Khách tương tác lần cuối đã quá 7 ngày nên Zalo không cho gửi tin tư vấn.',
  checker_failed: 'Bước kiểm tra trước khi gửi báo lỗi. Sửa tin hoặc chọn vẫn gửi.',
  zalo_send_failed: 'Zalo báo lỗi khi gửi. Tin được lưu với trạng thái gửi lỗi.',
  zalo_send_unknown: 'Gửi bị quá thời gian chờ; chưa rõ tin đã tới khách chưa. Hệ thống sẽ đối soát sau.',
  validation_failed: 'Dữ liệu nhập chưa đúng.',
  not_implemented: 'Máy chủ chưa làm chức năng này (501).',
};

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const base = CODE_TEXT[e.code] ?? e.message;
    const field = typeof e.details?.field === 'string' ? ` (trường ${e.details.field})` : '';
    return `${base}${field}`;
  }
  if (e instanceof TypeError) return 'Không kết nối được máy chủ. Kiểm tra địa chỉ máy chủ và máy chủ có đang chạy không.';
  if (e instanceof Error) return e.message;
  return String(e);
}

/**
 * A staff action of docs/contracts.md section 14 against a server that has not applied migration 0010 (409 naming the
 * file). `what` completes "nên chưa ...", e.g. "lưu được vai trò". Null for any other error.
 */
export function migration0010Text(e: unknown, what: string): string | null {
  if (e instanceof ApiError && e.status === 409 && /0010_rooms_roles_customer/.test(e.message)) {
    return `Máy chủ chưa áp migration 0010_rooms_roles_customer.sql, nên chưa ${what}. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.`;
  }
  return null;
}

function oldServerText(e: unknown, what: string): string | null {
  if (e instanceof ApiError && e.status === 404) {
    return `Máy chủ không có địa chỉ này, nên chưa ${what}. Có thể máy chủ đang chạy bản cũ: cập nhật và khởi động lại máy chủ, rồi làm lại.`;
  }
  return null;
}

/** The same, plus 404 on an endpoint that only exists since 2026-11-12 (an older server). Null for any other error. */
export function serverGapText(e: unknown, what: string): string | null {
  return migration0010Text(e, what) ?? oldServerText(e, what);
}

/** Section 15: a chat-facts endpoint against a server whose local D1 does not have migration 0011 yet (409 naming the file). */
export function migration0011Text(e: unknown, what: string): string | null {
  if (e instanceof ApiError && e.status === 409 && /0011_chat_facts/.test(e.message)) {
    return `Máy chủ chưa áp migration 0011_chat_facts.sql, nên chưa ${what}. Khởi động lại máy chủ bằng scripts/start_local.sh để áp migration, rồi làm lại.`;
  }
  return null;
}

/** Section 15 counterpart of serverGapText: migration 0011 (or 0010) missing, or a server without the endpoint (404). */
export function chatFactsGapText(e: unknown, what: string): string | null {
  return migration0011Text(e, what) ?? migration0010Text(e, what) ?? oldServerText(e, what);
}
