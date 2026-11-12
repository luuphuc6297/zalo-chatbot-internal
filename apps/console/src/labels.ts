// Vietnamese labels for staff. Each value label says what the system does, not just on/off.
import type {
  BenefitKind,
  BookingStatus,
  BotState,
  ChatAmountSource,
  ChatBenefitView,
  ChatConfidence,
  ChatFactState,
  CheckerIssue,
  ContactRole,
  ConversationMode,
  ConversationSummary,
  CustomerStatus,
  CustomerSummary,
  DraftStatus,
  HandoffView,
  MessageSource,
  ProfileAddressTerm,
  ProfileConfidence,
  ProfileEvidence,
  ProfileRelationship,
  ProfileService,
  ProfileStaffField,
  RoleSource,
  SendState,
  VisitView,
} from './api';

export const BOT_STATE_LABEL: Record<BotState, string> = {
  awaiting_consent: 'chờ khách đồng ý dùng trợ lý AI',
  bot_active: 'bot đang trả lời',
  handoff_requested: 'bot đã chuyển nhân viên',
  staff_takeover: 'nhân viên đang xử lý',
  staff_only: 'chỉ nhân viên trả lời (khách chọn gặp nhân viên, hoặc không phải khách)',
  blocked: 'đã chặn bot',
};

export const MODES: ConversationMode[] = ['off', 'draft_only', 'approve_each', 'auto_allowed'];

export const MODE_LABEL: Record<ConversationMode, { label: string; does: string }> = {
  off: {
    label: 'Tắt bot',
    does: 'Không soạn nháp. Tin của khách vẫn được lưu và hội thoại được đánh dấu cần chú ý.',
  },
  draft_only: {
    label: 'Chỉ soạn nháp',
    does: 'Bot soạn nháp để tham khảo nhưng không duyệt gửi được; nhân viên tự gửi tay, có thể chép từ bản nháp.',
  },
  approve_each: {
    label: 'Duyệt từng tin (mặc định)',
    does: 'Bot soạn nháp; tin chỉ được gửi khi nhân viên bấm duyệt.',
  },
  auto_allowed: {
    label: 'Cho bot tự gửi',
    does:
      'Bot tự gửi khi bước kiểm tra trước khi gửi không báo lỗi, hội thoại vẫn ở trạng thái bot đang trả lời và bot không chuyển nhân viên. Các trường hợp khác chờ duyệt.',
  },
};

export const DRAFT_STATUS_LABEL: Record<DraftStatus, string> = {
  pending: 'chờ duyệt',
  blocked: 'bị chặn bởi bước kiểm tra',
  approved: 'đã duyệt',
  rejected: 'đã từ chối',
  sent: 'đã gửi',
  superseded: 'bị thay bằng bản mới',
  discarded: 'đã bỏ',
  send_failed: 'gửi lỗi',
};

export const CHECKER_RULE_LABEL: Record<CheckerIssue['rule'], string> = {
  price: 'Giá không khớp giá do hệ thống báo',
  forbidden_term: 'Có từ không được dùng',
  format: 'Sai định dạng (markdown, ký tự lạ)',
  contact_info: 'Có thông tin liên hệ chưa được duyệt',
  booking_promise: 'Hứa giữ chỗ hoặc xác nhận lịch',
  state: 'Trạng thái hội thoại không cho gửi',
  length: 'Tin quá dài',
  empty: 'Tin rỗng',
  menu_image: 'Ảnh menu không gửi được tự động (ảnh in câu về sức khỏe hoặc ảnh lạ)',
};

export const SOURCE_LABEL: Record<MessageSource, string> = {
  customer: 'Khách',
  bot: 'Bot',
  staff: 'Nhân viên',
  server: 'Hệ thống',
};

export const SEND_STATE_LABEL: Record<SendState, string> = {
  not_applicable: '',
  pending: 'đang gửi',
  sent: 'đã gửi',
  unknown: 'chưa rõ đã tới Zalo chưa',
  failed: 'gửi lỗi',
};

export const BOOKING_STATUS_LABEL: Record<BookingStatus, string> = {
  new: 'mới, chưa xử lý',
  proposed: 'đã đề xuất giờ khác',
  confirmed: 'đã xác nhận',
  cancelled: 'đã từ chối hoặc hủy',
  expired: 'hết hạn',
};

export const HANDOFF_REASON_LABEL: Record<string, string> = {
  customer_requested_human: 'Khách muốn gặp nhân viên',
  pregnancy: 'Khách đang mang thai',
  postpartum: 'Khách sau sinh',
  chronic_or_serious_condition: 'Bệnh mãn tính hoặc bệnh nặng',
  medication: 'Đang dùng thuốc',
  recent_surgery: 'Mới phẫu thuật',
  skin_lesion_or_wound: 'Da tổn thương hoặc vết thương',
  adverse_reaction_after_visit: 'Phản ứng xấu sau buổi làm',
  possible_minor: 'Có thể là người chưa đủ tuổi',
  medical_suitability_question: 'Hỏi dịch vụ có hợp sức khỏe không',
  complaint: 'Khiếu nại',
  refund_or_payment: 'Hoàn tiền hoặc thanh toán',
  reschedule_or_cancel: 'Đổi hoặc hủy lịch',
  harassment_or_inappropriate: 'Quấy rối hoặc nội dung không phù hợp',
  data_rights_request: 'Yêu cầu về dữ liệu cá nhân',
  unknown_answer: 'Khách hỏi điều studio chưa công bố',
  price_ambiguity: 'Giá chưa rõ',
  large_group: 'Nhóm đông',
  emergency_symptoms: 'Dấu hiệu cấp cứu',
  other: 'Lý do khác',
  ai_unavailable: 'Model không chạy được (máy chạy model lỗi hoặc tắt)',
  checker_blocked: 'Bản nháp tự gửi bị bước kiểm tra chặn',
  customer_declined_ai: 'Khách không đồng ý dùng trợ lý AI',
  unsupported_message: 'Khách gửi ảnh, sticker hoặc file bot không đọc được',
  minor_flag: 'Khách bị đánh dấu chưa đủ tuổi',
};

export function handoffReason(h: Pick<HandoffView, 'reason_code'>): string {
  return HANDOFF_REASON_LABEL[h.reason_code] ?? h.reason_code;
}

// ---- contact profiles (docs/contracts.md section 13)

/** Relationships staff can choose; 'personal' (legacy, before 2026-11-08) is shown but no longer offered. */
export const RELATIONSHIPS: ProfileRelationship[] = ['customer', 'staff', 'family', 'friend', 'unknown'];

export const RELATIONSHIP_LABEL: Record<ProfileRelationship, string> = {
  customer: 'khách',
  staff: 'nhân viên',
  family: 'gia đình',
  friend: 'bạn bè',
  personal: 'người quen (nhãn cũ)',
  unknown: 'chưa rõ',
};

/** Family, staff, friends and the legacy 'personal': the bot never gets their profile and may stay quiet for them. */
export const QUIET_RELATIONSHIPS: ProfileRelationship[] = ['staff', 'family', 'friend', 'personal'];

export const LAST_SERVICE_SOURCE_LABEL: Record<'chat' | 'visit', string> = {
  chat: 'đoán từ tin nhắn cũ',
  visit: 'nhân viên ghi buổi làm',
};

export const CONFIDENCE_LABEL: Record<ProfileConfidence, string> = {
  low: 'chắc chắn thấp',
  medium: 'chắc chắn vừa',
  high: 'chắc chắn cao',
};

export const ADDRESS_TERMS: ProfileAddressTerm[] = ['chị', 'anh', 'cô', 'chú', 'bác', 'anh/chị'];

// Reason codes of scripts/analyze_contacts.py; "code:n" carries a count.
export const PROFILE_REASON_LABEL: Record<string, string> = {
  service_vocab: 'nhắc tới dịch vụ',
  catalog_match: 'nhắc đúng tên dịch vụ trong bảng giá',
  booking_vocab: 'hỏi đặt lịch',
  price_vocab: 'hỏi giá',
  weak_service_vocab: 'nhắc giá, số tiền hoặc chuyện đặt chỗ nhưng không nêu dịch vụ',
  calls_owner_business: 'gọi chủ tài khoản là shop, ad, admin hoặc spa',
  owner_business: 'chủ tài khoản tự xưng là shop',
  visit_signal: 'có dấu hiệu đã đến làm',
  owner_service_vocab: 'chủ tài khoản nhắn về dịch vụ',
  owner_deference: 'chủ tài khoản trả lời bằng dạ và gọi người này là anh hoặc chị',
  kinship_vocative: 'xưng hô kiểu người nhà (ví dụ mẹ ơi)',
  intimate_pronoun: 'xưng hô thân mật (tao, mày)',
  personal_chitchat: 'chuyện riêng không liên quan dịch vụ',
  long_chat_no_service: 'nhắn từ 30 tin trở lên mà gần như không nhắc dịch vụ',
  many_days_no_service: 'nhắn trong 8 ngày trở lên mà không nhắc dịch vụ',
  // analyzer v3 (2026-11-08)
  family_role: 'vai trong gia đình',
  elder_kin_pattern: 'xưng hô kiểu người lớn tuổi trong nhà',
  kin_display_name: 'tên Zalo có từ chỉ người nhà',
  kin_address: 'gọi nhau bằng từ chỉ người nhà (mẹ, con, vợ, chồng)',
  kin_child_terms: 'dùng từ gọi con cháu (con, bé, cưng)',
  couple_signal: 'dấu hiệu là vợ chồng hoặc người yêu',
  kin_endearment: 'lời âu yếm kiểu người nhà',
  insider_contact: 'người này nói về việc của studio như người làm (ca làm, lương, khách của studio)',
  insider_contact_weak: 'người này có vài tin nói về việc của studio như người làm',
  insider_owner: 'chủ tài khoản nói về việc của studio như với người làm',
  owner_instruction: 'chủ tài khoản giao việc cho người này',
  owner_calls_be: 'chủ tài khoản gọi người này là bé',
  contact_elder: 'người này lớn tuổi hơn chủ tài khoản',
  non_catalog_service: 'nhắc dịch vụ không có trong bảng giá',
  junior_pattern: 'người này xưng hô như người nhỏ tuổi hơn',
  senior_pattern: 'người này xưng hô như người lớn tuổi hơn',
  very_long_chat: 'trò chuyện rất dài',
  long_personal_chat: 'trò chuyện dài, phần lớn là chuyện riêng',
  purchase_ratio: 'tỉ lệ tin về mua dịch vụ',
};

const FAMILY_ROLE_LABEL: Record<string, string> = {
  spouse: 'vợ hoặc chồng',
  contact_parent: 'cha hoặc mẹ của chủ tài khoản',
  contact_child: 'con của chủ tài khoản',
  elder: 'người lớn tuổi trong nhà',
  relative: 'họ hàng',
};

export function profileReason(code: string): string {
  const i = code.indexOf(':');
  const key = i === -1 ? code : code.slice(0, i);
  const n = i === -1 ? '' : code.slice(i + 1);
  const label = PROFILE_REASON_LABEL[key] ?? key;
  if (key === 'family_role') return `${label}: ${FAMILY_ROLE_LABEL[n] ?? n}`;
  if (key === 'purchase_ratio') {
    const r = Number(n);
    return Number.isFinite(r) ? `${label}: ${Math.round(r * 100)}%` : label;
  }
  return n ? `${label} (${n} lần)` : label;
}

/** Field groups staff edited (CustomerProfileView.staff_fields). */
export const STAFF_FIELD_LABEL: Record<ProfileStaffField, string> = {
  relationship: 'quan hệ',
  address: 'cách gọi',
  name: 'tên',
  services: 'danh sách dịch vụ',
};

export const SERVICE_STATUS_LABEL: Record<ProfileService['status'], string> = {
  likely_used: 'có dấu hiệu đã dùng (chưa chắc chắn)',
  mentioned: 'từng hỏi hoặc nhắc tới',
};

export const EVIDENCE_KIND_LABEL: Record<ProfileEvidence['kind'], string> = {
  service: 'về dịch vụ',
  booking: 'về đặt lịch',
  price: 'về giá',
};

export const EVIDENCE_FROM_LABEL: Record<ProfileEvidence['from'], string> = {
  contact: 'người này nhắn',
  owner: 'chủ tài khoản nhắn',
};

/** How the bot addresses the contact, e.g. "chị Lan"; null term means the default "anh/chị". */
export function addressText(term: ProfileAddressTerm | null, name: string | null): string {
  if (!term) return 'chưa xác định (bot gọi anh/chị)';
  if (term === 'anh/chị') return 'anh/chị';
  return name ? `${term} ${name}` : term;
}

export type BadgeKind = 'attention' | 'pending' | 'staff' | 'bot' | 'muted';
export interface Badge {
  kind: BadgeKind;
  text: string;
}

// ---- roles, auto reply switch and customer summary (docs/contracts.md section 14)

export const ROLES: ContactRole[] = ['customer', 'manager', 'staff'];

export const ROLE_LABEL: Record<ContactRole, string> = {
  customer: 'khách',
  manager: 'quản lý',
  staff: 'nhân viên',
};

export const ROLE_SOURCE_LABEL: Record<RoleSource, string> = {
  zalo_label: 'nhãn Zalo',
  staff: 'lễ tân đặt',
  profile: 'suy từ hồ sơ',
};

/** What the server does for a contact with this role. */
export const ROLE_DOES: Record<ContactRole, string> = {
  customer: 'Bot coi người này là khách, kể cả khi hồ sơ liên hệ đoán khác.',
  manager: 'Người của studio: máy chủ chỉ lưu tin của người này. Bot không soạn nháp, không gửi tin và hội thoại không bị đánh dấu cần chú ý.',
  staff: 'Người của studio: máy chủ chỉ lưu tin của người này. Bot không soạn nháp, không gửi tin và hội thoại không bị đánh dấu cần chú ý.',
};

/** Managers and staff are internal contacts: the bots never answer them. */
export function isInternalRole(role: ContactRole | null | undefined): boolean {
  return role === 'manager' || role === 'staff';
}

export const AUTO_REPLY_TEXT = {
  title: 'Tự động trả lời',
  meaning: 'Bật: bot gửi câu trả lời cho khách ngay, không ai đọc trước. Tắt: tin của bot chỉ tới khách sau khi nhân viên duyệt.',
  onDetail: 'Khi đang bật, tin kèm ảnh menu và tin bị bước kiểm tra báo lỗi vẫn chờ nhân viên duyệt.',
  confirm:
    'Bật tự động trả lời cho hội thoại này? Câu trả lời của bot sẽ tới khách ngay, không ai đọc trước. Chế độ riêng của hội thoại sẽ được bỏ.',
  confirmYes: 'Bật tự động trả lời',
  confirmNo: 'Không bật',
  turnedOn: 'Đã bật tự động trả lời cho hội thoại này.',
  turnedOff: 'Đã tắt tự động trả lời cho hội thoại này.',
  internal: 'Người này là người của studio (quản lý hoặc nhân viên) nên bot không trả lời. Muốn bật thì đổi vai trò trước.',
  serverSaysInternal: 'Máy chủ không cho bật vì người này đang có vai trò quản lý hoặc nhân viên. Đổi vai trò trước rồi bật lại.',
  globalOff:
    'Chế độ trả lời chung đang là Tắt bot (auto_reply_mode = off) nên công tắc này chưa có tác dụng. Đổi chế độ trả lời chung ở tab Cài đặt trước.',
  storedWhileGlobalOff: 'Hội thoại này đã được bật tự động trả lời từ trước. Khi chế độ trả lời chung khác Tắt bot, bot sẽ tự gửi tin ở đây.',
  clearStored: 'Bỏ tự động trả lời của hội thoại này',
  modeWhileOn:
    'Công tắc tự động trả lời đang bật cho hội thoại này. Chọn Tắt bot, Chỉ soạn nháp hoặc Duyệt từng tin ở đây thì công tắc tự tắt.',
  modeWhileOff: 'Công tắc tự động trả lời đã được tắt riêng cho hội thoại này, nên chế độ đang áp dụng không vượt quá Duyệt từng tin.',
};

export const CUSTOMER_STATUS_LABEL: Record<CustomerStatus, string> = {
  first_inquiry: 'mới hỏi, chưa đến lần nào',
  first_visit_done: 'đã đến lần đầu',
  returning: 'khách quay lại',
  long_absent: 'lâu chưa quay lại',
};

export const GAP_BASIS_LABEL: Record<NonNullable<CustomerSummary['gap_basis']>, string> = {
  own: 'tính từ các lần đến của chính khách',
  service_peers: 'khách mới đến một lần nên lấy theo các khách dùng cùng dịch vụ',
  default: 'khách mới đến một lần nên lấy mức mặc định',
};

export const BENEFIT_KINDS: BenefitKind[] = ['package', 'voucher'];

export const BENEFIT_KIND_LABEL: Record<BenefitKind, string> = {
  package: 'gói nhiều buổi',
  voucher: 'voucher',
};

export const VISIT_SOURCE_LABEL: Record<NonNullable<VisitView['source']>, string> = {
  staff: 'nhân viên ghi',
  booking_app: 'phần mềm đặt lịch',
  booking_request: 'từ yêu cầu đặt lịch',
  import: 'nhập từ file',
};

// ---- facts guessed from old chat (section 15.13)

export const CHAT_SECTION_TITLE = 'Suy ra từ tin nhắn cũ';

/** Marker on a figure of the summary that counts guesses from old chat. */
export const FROM_CHAT_TEXT = 'suy ra từ tin nhắn';

export function chatMarkerText(n: number, atMost = false): string {
  return `gồm ${atMost ? 'tối đa ' : ''}${n} lần ${FROM_CHAT_TEXT}`;
}

export const CHAT_CONFIDENCE_LABEL: Record<ChatConfidence, string> = {
  high: 'chắc',
  medium: 'khá chắc',
  low: 'chưa chắc',
};

export const CHAT_AMOUNT_SOURCE_LABEL: Record<ChatAmountSource, string> = {
  paid: 'đã trả',
  quoted: 'báo giá',
  list_price: 'giá niêm yết',
};

export const CHAT_STATE_LABEL: Record<ChatFactState, string> = {
  active: 'chờ xử lý',
  confirmed: 'đã xác nhận',
  dismissed: 'đã bỏ',
};

export const CHAT_STATED_BY_LABEL: Record<NonNullable<ChatBenefitView['stated_by']>, string> = {
  owner: 'theo tin studio nhắn',
  contact: 'theo tin khách nhắn',
};

/** "0912345678" -> "*******678": only the last 3 digits stay readable until staff click "Hiện số". */
export function maskPhone(phone: string): string {
  const p = phone.trim();
  if (p.length <= 3) return '*'.repeat(p.length);
  return `${'*'.repeat(p.length - 3)}${p.slice(-3)}`;
}

/**
 * The sentence of a customer summary without visit data. The console ships with a server of section 15, where guesses
 * from old chat (high or medium) count as visits, so the sentence names the chat analyzer whether or not the summary
 * carries `chat` (the server leaves `chat` out for a contact without chat facts).
 */
export const NO_VISIT_DATA_CHAT_TEXT =
  'Chưa có buổi làm nào được ghi cho khách này. Số lần đến, số tiền và kỹ thuật viên có khi nhân viên ghi nhận buổi làm, nhập từ file, hoặc khi công cụ phân tích tin nhắn cũ tìm thấy lần đến chắc hoặc khá chắc.';

/** One line that explains the status with the numbers behind it. */
export function customerStatusReason(s: CustomerSummary): string {
  const days = s.days_since_last_visit;
  const gap = s.usual_gap_days;
  const limit = s.absent_after_days;
  const has = (n: number | null | undefined): n is number => typeof n === 'number' && Number.isFinite(n);
  if (!s.status) return '';
  if (s.status === 'first_inquiry') return 'Chưa có buổi làm nào được ghi.';
  const since = has(days) ? `Lần đến gần nhất cách đây ${days} ngày` : 'Chưa rõ lần đến gần nhất';
  const usual = has(gap) ? `thường ${gap} ngày quay lại một lần` : '';
  if (s.status === 'long_absent') {
    const over = has(limit) ? `, quá mốc ${limit} ngày` : '';
    return `${since}${over}${usual ? ` (${usual})` : ''}.`;
  }
  const count = s.status === 'first_visit_done' ? 'Khách mới đến một lần. ' : has(s.visits_total) ? `Khách đã đến ${s.visits_total} lần. ` : '';
  const under = has(limit) ? `, chưa quá mốc ${limit} ngày` : '';
  return `${count}${since}${under}${usual ? ` (${usual})` : ''}.`;
}

/** 450000 -> "450.000đ", the price format used everywhere in the project. */
export function fmtVnd(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '';
  const whole = Math.round(n);
  const digits = String(Math.abs(whole)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${whole < 0 ? '-' : ''}${digits}đ`;
}

/** Text of a money field while staff type: digits only, grouped in thousands ("1250000" -> "1.250.000"). */
export function vndInputText(raw: string): string {
  const digits = raw.replace(/\D/g, '').replace(/^0+(?=\d)/, '');
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

/** Whole amount in VND of a money field; null when the field is empty or the number is too large to be exact. */
export function parseVnd(text: string): number | null {
  const digits = text.replace(/\D/g, '');
  if (!digits) return null;
  const n = Number(digits);
  return Number.isSafeInteger(n) ? n : null;
}

/** "2026-10-30" -> "30/10/2026"; anything else is returned unchanged. */
export function fmtYmd(ymd: string | null | undefined): string {
  if (!ymd) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ymd;
}

/** Vietnamese phone as the server stores it: "+84 90 123 4567" -> "0901234567"; null when it is not 9 to 11 digits. */
export function normalizePhone(text: string): string | null {
  const compact = text.replace(/[\s.\-()]/g, '');
  const local = compact.startsWith('+84') ? `0${compact.slice(3)}` : compact;
  return /^\d{9,11}$/.test(local) ? local : null;
}

// The four list badges staff asked for, plus the consent and blocked states, the auto reply switch and the role.
export function conversationBadges(c: ConversationSummary): Badge[] {
  const out: Badge[] = [];
  if (c.needs_attention || c.open_handoffs > 0 || c.bot_state === 'handoff_requested') {
    out.push({ kind: 'attention', text: 'cần chú ý' });
  }
  if (c.pending_drafts > 0) out.push({ kind: 'pending', text: `chờ duyệt (${c.pending_drafts})` });
  if (c.bot_state === 'staff_takeover' || c.bot_state === 'staff_only') {
    out.push({ kind: 'staff', text: 'nhân viên đang xử lý' });
  }
  if (c.bot_state === 'bot_active') out.push({ kind: 'bot', text: 'bot đang trả lời' });
  if (c.bot_state === 'awaiting_consent') out.push({ kind: 'muted', text: 'chờ khách đồng ý' });
  if (c.bot_state === 'blocked') out.push({ kind: 'muted', text: 'đã chặn bot' });
  // an internal contact (a role row from a Zalo label or set by staff) never gets a bot reply, whatever the mode
  // says; a role read from the contact profile does not stop the bots
  const internal = isInternalRole(c.role) && c.role_source !== 'profile';
  if (c.effective_mode === 'auto_allowed' && !internal) out.push({ kind: 'bot', text: 'tự động trả lời' });
  if (c.role) out.push({ kind: isInternalRole(c.role) ? 'staff' : 'muted', text: `vai trò: ${ROLE_LABEL[c.role]}` });
  return out;
}

const TZ = 'Asia/Ho_Chi_Minh';
const dtf = new Intl.DateTimeFormat('vi-VN', {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export function fmtTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '';
  return dtf.format(new Date(ms));
}

const dateFmt = new Intl.DateTimeFormat('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' });

/** Date only, Vietnam time, e.g. "07/11/2026". */
export function fmtDate(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '';
  return dateFmt.format(new Date(ms));
}

// "2026-11-07T19:30" typed in a datetime-local field, read as Vietnam time (UTC+7, no DST).
export function vnLocalToMs(local: string): number {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return Number.NaN;
  return Date.parse(`${local}:00+07:00`);
}

export function msToVnLocal(ms: number): string {
  return new Date(ms + 7 * 3600_000).toISOString().slice(0, 16);
}

/** Last second of a Vietnam day typed in a date field: "2027-01-31" -> 2027-01-31 23:59:59 (UTC+7). NaN when not a date. */
export function vnDateEndMs(ymd: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return Number.NaN;
  return Date.parse(`${ymd}T23:59:59+07:00`);
}
