// Owner: server-zalo. ZBS template parameter maps for proactive sends (design/followup-templates.md, DRAFT:
// not approved by the owner, not submitted to Zalo). The server fills the parameters; the model never writes
// proactive messages. `body` is the ZBS text as drafted, kept here only to show staff what was sent (the real
// wording lives in the template Zalo approves; its id comes from env ZALO_TEMPLATE_IDS).
import type { TemplateKey } from '../lib/zalo-client';

export interface TemplateSpec {
  key: TemplateKey;
  zbs_tag: 1 | 2 | 3;
  params: string[];
  body: string;
}

export const TEMPLATES: Record<'thank_you' | 'check_in' | 'promo', TemplateSpec> = {
  thank_you: {
    key: 'thank_you',
    zbs_tag: 1,
    params: ['customer_name', 'service_name', 'visit_date', 'booking_code', 'aftercare_note'],
    body:
      'thom house cảm ơn bạn <customer_name> đã sử dụng dịch vụ <service_name> ngày <visit_date>, mã buổi làm <booking_code>.\n' +
      '<aftercare_note>\n' +
      'Nếu bạn thấy khó chịu, đau tăng hoặc có biểu hiện lạ sau buổi làm, bạn hãy nhắn cho thom house qua Zalo này, và đi khám nếu thấy nặng.\n' +
      'Nếu không muốn nhận tin chăm sóc sau buổi làm, bạn nhắn "Ngừng" cho thom house.',
  },
  check_in: {
    key: 'check_in',
    zbs_tag: 2,
    params: ['customer_name', 'service_name', 'visit_date', 'booking_code'],
    body:
      'Chào bạn <customer_name>, thom house xin hỏi thăm sau buổi <service_name> ngày <visit_date>, mã buổi làm <booking_code>.\n' +
      'Sau vài ngày, bạn cảm thấy thế nào? thom house mong nhận được góp ý của bạn về buổi làm.\n' +
      'Nếu có điều gì khó chịu, bạn hãy nhắn cho thom house qua Zalo này để nhân viên liên hệ.\n' +
      'Nếu không muốn nhận tin chăm sóc sau buổi làm, bạn nhắn "Ngừng" cho thom house.',
  },
  promo: {
    key: 'promo',
    zbs_tag: 3,
    params: ['customer_name', 'promo_name', 'promo_text', 'valid_until', 'promo_conditions'],
    body:
      'Chào bạn <customer_name>, thom house gửi bạn thông tin chương trình <promo_name>.\n' +
      'Nội dung: <promo_text>\n' +
      'Thời hạn: đến hết ngày <valid_until>.\n' +
      'Điều kiện áp dụng: <promo_conditions>\n' +
      'Nếu không muốn nhận tin ưu đãi từ thom house, bạn nhắn "Ngừng" cho thom house.',
  },
};

/** Fills <param> placeholders for the staff-visible copy; an empty param drops its line when it is alone on it. */
export function renderTemplate(spec: TemplateSpec, params: Record<string, string>): string {
  const out: string[] = [];
  for (const line of spec.body.split('\n')) {
    const filled = line.replace(/<([a-z_]+)>/g, (_m, name: string) => params[name] ?? '');
    const onlyParam = /^<[a-z_]+>$/.test(line.trim());
    if (onlyParam && filled.trim().length === 0) continue;
    out.push(filled);
  }
  return out.join('\n');
}

/** Every declared param present (empty string allowed) and nothing else. */
export function pickParams(spec: TemplateSpec, values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of spec.params) out[p] = values[p] ?? '';
  return out;
}

// ---------------------------------------------------------------- personal channel: chat versions

/**
 * Chat versions ("Bản chat") of design/followup-templates.md, used on the personal Zalo channel where ZBS templates
 * do not exist. Same DRAFT status as the ZBS text: not approved by the owner. Variables use {name}. Only the two
 * care messages have a proactive chat version; promo and the others need staff on the personal channel.
 */
export const CHAT_TEMPLATES: Partial<Record<TemplateKey, string>> = {
  thank_you:
    'Dạ em chào {customer_name}, em là trợ lý AI của thom house. Cảm ơn anh/chị đã ghé làm {service_name} hôm {visit_date} ạ.\n' +
    'Sau buổi làm anh/chị thấy trong người thế nào ạ?\n' +
    '{aftercare_note}\n' +
    'Nếu anh/chị thấy khó chịu, đau tăng hoặc có biểu hiện lạ, anh/chị nhắn bên em ngay, và đi khám nếu thấy nặng ạ.\n' +
    'Anh/chị không muốn nhận tin hỏi thăm nữa thì nhắn "Ngừng" giúp em ạ.',
  check_in:
    'Dạ em chào {customer_name}, em là trợ lý AI của thom house. Đã vài ngày từ buổi {service_name} hôm {visit_date}, em hỏi thăm anh/chị đã thấy ổn chưa ạ?\n' +
    'Anh/chị có góp ý gì về buổi làm, bên em rất muốn được nghe ạ.\n' +
    'Nếu có điều gì khó chịu, anh/chị nhắn em để nhân viên liên hệ ạ.\n' +
    'Anh/chị không muốn nhận tin hỏi thăm nữa thì nhắn "Ngừng" giúp em ạ.',
};

export function hasChatTemplate(key: TemplateKey): boolean {
  return typeof CHAT_TEMPLATES[key] === 'string';
}

/** Fills {param} placeholders of the chat version; an empty param alone on its line drops the line. Null if no chat version. */
export function renderChatTemplate(key: TemplateKey, params: Record<string, string>): string | null {
  const body = CHAT_TEMPLATES[key];
  if (!body) return null;
  const out: string[] = [];
  for (const line of body.split('\n')) {
    const filled = line.replace(/\{([a-z_]+)\}/g, (_m, name: string) => params[name] ?? '');
    if (/^\{[a-z_]+\}$/.test(line.trim()) && filled.trim().length === 0) continue;
    out.push(filled);
  }
  return out.join('\n');
}
