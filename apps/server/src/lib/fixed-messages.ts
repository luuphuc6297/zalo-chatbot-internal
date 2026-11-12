// Owner: server-core. Server-authored messages (never written by the model). Wording is a DRAFT from
// design/conversation-design.md and needs the owner's/lawyer's approval before real use.

/** Payload strings sent back by oa.query.show buttons. The simulator can send them as plain text. */
export const CONSENT_PAYLOAD_AGREE = '#dong_y_tro_ly_ai';
export const CONSENT_PAYLOAD_STAFF = '#gap_nhan_vien';

export const CONSENT_PROMPT_TEXT =
  'Dạ em chào anh/chị. Em là trợ lý AI của thom house healing studio, hỗ trợ xem menu, giá, quy trình dịch vụ ' +
  'và ghi nhận yêu cầu đặt lịch. Tin nhắn trò chuyện với trợ lý AI được xử lý trên máy chủ của Anthropic tại Mỹ. ' +
  'Thông tin sức khỏe anh/chị chia sẻ là dữ liệu cá nhân nhạy cảm. Anh/chị chọn giúp em:';

export const CONSENT_BUTTON_AGREE = 'Đồng ý trò chuyện với trợ lý AI';
export const CONSENT_BUTTON_STAFF = 'Gặp nhân viên';

/** Sent by the server when the bot cannot answer (runner down, no account, handoff outside working hours). */
export const STAFF_WILL_REPLY_TEXT = 'Dạ em đã chuyển tin của anh/chị cho nhân viên thom house, nhân viên sẽ trả lời anh/chị sớm ạ.';

export const OPT_OUT_KEYWORDS = ['ngừng', 'ngung', 'dừng', 'dung', 'stop', 'đừng nhắn nữa', 'dung nhan nua'];

/** Sent after the customer presses the consent button. Messages sent before consent are never given to the model,
 *  so the customer is asked to send the question again. */
export const CONSENT_GRANTED_TEXT =
  'Dạ em cảm ơn anh/chị đã đồng ý. Anh/chị nhắn giúp em điều anh/chị cần hỏi ạ.';

// ---- personal Zalo channel: no buttons, so the consent prompt tells the customer what to type.
// Replies are matched after lowercasing and removing diacritics (src/lib/zalo-personal.ts consentReplyOf).
export const CONSENT_KEYWORD_AGREE = 'đồng ý';
export const CONSENT_KEYWORD_STAFF = 'gặp nhân viên';
export const CONSENT_REPLY_LINE_AGREE = `Nhắn "${CONSENT_KEYWORD_AGREE}" để trò chuyện với trợ lý AI.`;
export const CONSENT_REPLY_LINE_STAFF = `Nhắn "${CONSENT_KEYWORD_STAFF}" để nói chuyện với nhân viên thom house.`;
