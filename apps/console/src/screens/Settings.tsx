// Settings: connection, kill switches with explicit values, runner + Claude account pool, outbox (mock or personal Zalo).
import { useState } from 'react';
import type { Api, Flags, OutboxDecision, OutboxItem, PoolAccountStatus, ZaloMode } from '../api';
import { type ConsoleConfig, storageKind } from '../config';
import { useAction, usePoll } from '../hooks';
import { MODES, MODE_LABEL, fmtTime } from '../labels';
import { CopyField, ErrorLine, Notice } from './common';

type FlagKey = Exclude<keyof Flags, 'runner_desired_account'>;
interface FlagOption {
  value: Flags[FlagKey];
  label: string;
  does: string;
}

export const FLAG_SPECS: Array<{ key: FlagKey; title: string; options: FlagOption[] }> = [
  {
    key: 'outbound_enabled',
    title: 'Gửi tin qua Zalo (outbound_enabled)',
    options: [
      { value: true, label: 'true: cho gửi tin', does: 'Duyệt, gửi tay, tự gửi và tin hẹn giờ đều được gửi qua Zalo.' },
      { value: false, label: 'false: chặn mọi tin gửi đi', does: 'Không gửi tin nào qua Zalo, kể cả khi nhân viên duyệt hoặc gửi tay.' },
    ],
  },
  {
    key: 'auto_reply_mode',
    title: 'Chế độ trả lời chung (auto_reply_mode)',
    options: MODES.map((m) => ({ value: m, label: `${m}: ${MODE_LABEL[m].label}`, does: MODE_LABEL[m].does })),
  },
  {
    key: 'ai_calls_enabled',
    title: 'Gọi model (ai_calls_enabled)',
    options: [
      { value: true, label: 'true: cho gọi model', does: 'Máy chạy model nhận việc soạn nháp cho hội thoại đang để bot trả lời.' },
      { value: false, label: 'false: không gọi model', does: 'Không tạo việc soạn nháp nào. Giá trị này thắng mọi cài đặt khác.' },
    ],
  },
  {
    key: 'ai_engine',
    title: 'Cách gọi model (ai_engine)',
    options: [
      {
        value: 'subscription',
        label: 'subscription: gói Claude của chủ studio',
        does: 'Máy chạy model trên Mac soạn nháp bằng claude -p qua các tài khoản trong danh sách bên dưới.',
      },
      {
        value: 'api_key',
        label: 'api_key: API key (chưa cấu hình)',
        does: 'Chưa làm. Mọi lần soạn nháp chuyển ngay cho nhân viên với lý do model không chạy được.',
      },
      { value: 'off', label: 'off: tắt', does: 'Giống ai_calls_enabled = false: không soạn nháp.' },
    ],
  },
  {
    key: 'scheduled_sends_enabled',
    title: 'Tin hẹn giờ sau buổi làm (scheduled_sends_enabled)',
    options: [
      { value: false, label: 'false: giữ tin hẹn giờ', does: 'Tin cảm ơn và tin hỏi thăm đến hạn vẫn nằm chờ, không gửi.' },
      {
        value: true,
        label: 'true: gửi tin hẹn giờ',
        does: 'Gửi tin đến hạn bằng mẫu ZBS; tin trễ quá 6 giờ bị bỏ. Mẫu ZBS chưa được Zalo duyệt nên chưa nên chọn.',
      },
    ],
  },
  {
    key: 'promotions_enabled',
    title: 'Tin khuyến mãi (promotions_enabled)',
    options: [
      { value: false, label: 'false: không gửi khuyến mãi', does: 'Việc gửi khuyến mãi nằm chờ, không gửi.' },
      { value: true, label: 'true: cho gửi khuyến mãi', does: 'Tin khuyến mãi gửi theo cùng điều kiện với tin hẹn giờ.' },
    ],
  },
  {
    key: 'profile_personal_skip_bot',
    title: 'Bot im lặng với gia đình, nhân viên và bạn bè (profile_personal_skip_bot)',
    options: [
      {
        value: true,
        label: 'true: bot không nhắn người quen (mặc định)',
        does:
          'Người có hồ sơ là gia đình, nhân viên, bạn bè hoặc người quen (nhãn cũ) ở mức chắc chắn cao, hoặc do nhân viên chọn, và chưa đồng ý trò chuyện với trợ lý AI: tin kế tiếp của họ chuyển hội thoại sang chỉ nhân viên trả lời. Server không gửi tin xin đồng ý cho họ.',
      },
      {
        value: false,
        label: 'false: xử lý như mọi người nhắn tới',
        does: 'Người quen cũng nhận tin xin đồng ý trò chuyện với trợ lý AI như khách. Bot vẫn không nhận thông tin nào từ hồ sơ của họ.',
      },
    ],
  },
  {
    // docs/contracts.md section 14.7; absent on servers before 2026-11-12, and the entry then does not show
    key: 'rooms_enabled',
    title: 'Phòng hai bot (rooms_enabled)',
    options: [
      {
        value: false,
        label: 'false: máy chủ không đưa tin vào phòng hai bot (mặc định)',
        does: 'Máy chủ không giao tin nhắn nào cho phòng hai bot. Bản nháp vẫn được soạn như trước.',
      },
      {
        value: true,
        label: 'true: máy chủ đưa tin vào phòng hai bot',
        does:
          'Mỗi hội thoại một-một của khách đã đồng ý trò chuyện với trợ lý AI có một phòng riêng trên máy Mac, nơi Bot dịch vụ và Bot khách hàng cùng soạn câu trả lời. Máy chủ giao tin của hội thoại cho runner để đưa vào phòng; quản lý và nhân viên của studio không có phòng. Phòng chỉ chạy khi runner được đặt THOMHOUSE_DRAFT_ENGINE=rooms. Câu trả lời vẫn là bản nháp chờ nhân viên duyệt, trừ khi công tắc Tự động trả lời của hội thoại đó đang bật.',
      },
    ],
  },
];

export function SettingsScreen(props: {
  api: Api | null;
  config: ConsoleConfig;
  zaloMode: ZaloMode | null;
  onSaveConfig: (cfg: ConsoleConfig) => Promise<void>;
}) {
  return (
    <div className="page">
      <h2>Cài đặt</h2>
      <ConnectionForm config={props.config} onSave={props.onSaveConfig} />
      {props.api && (
        <>
          <FlagsSection api={props.api} />
          <RunnerSection api={props.api} />
          {(props.zaloMode === 'mock' || props.zaloMode === 'personal') && <OutboxSection api={props.api} mode={props.zaloMode} />}
        </>
      )}
    </div>
  );
}

function ConnectionForm(props: { config: ConsoleConfig; onSave: (cfg: ConsoleConfig) => Promise<void> }) {
  const [baseUrl, setBaseUrl] = useState(props.config.baseUrl);
  const [token, setToken] = useState(props.config.staffToken);
  const [staffId, setStaffId] = useState(props.config.staffId);
  const act = useAction();
  const kind = storageKind();
  return (
    <section className="box">
      <h3>Kết nối máy chủ</h3>
      <div className="form">
        <label>
          Địa chỉ máy chủ
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="để trống khi chạy pnpm dev:console (qua proxy)" />
        </label>
        <label>
          Staff token
          <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        <label>
          Tên nhân viên (ghi vào nhật ký)
          <input value={staffId} onChange={(e) => setStaffId(e.target.value)} />
        </label>
        <p className="muted small">
          {kind === 'safeStorage'
            ? 'Token được mã hóa bằng safeStorage của ứng dụng desktop và lưu trên máy này.'
            : 'Đang chạy trên trình duyệt: token lưu dạng chữ thường trong localStorage. Chỉ dùng trên máy phát triển.'}
        </p>
        <div className="actions">
          <button
            disabled={act.busy || !token.trim()}
            onClick={() => act.run(() => props.onSave({ baseUrl: baseUrl.trim(), staffToken: token.trim(), staffId: staffId.trim() }), 'Đã lưu.')}
          >
            Lưu và kết nối
          </button>
        </div>
      </div>
      <ErrorLine text={act.error} />
      <Notice text={act.notice} />
    </section>
  );
}

function FlagsSection({ api }: { api: Api }) {
  const flags = usePoll(() => api.getFlags(), [api], 10_000);
  const act = useAction();
  const data = flags.data;

  const apply = async (key: FlagKey, value: Flags[FlagKey]) => {
    const r = await act.run(() => api.putFlags({ [key]: value } as Partial<Flags>), `Đã đặt ${key} = ${String(value)}.`);
    if (r) flags.reload();
  };

  return (
    <section className="box">
      <h3>Công tắc an toàn</h3>
      <p className="muted small">Mỗi công tắc có hiệu lực ngay ở lần gửi hoặc lần soạn nháp kế tiếp. Chọn giá trị rồi bấm Áp dụng.</p>
      <ErrorLine text={flags.error ?? act.error} />
      <Notice text={act.notice} />
      {data &&
        // a flag the server does not report (older server) is not shown
        FLAG_SPECS.filter((spec) => data.flags[spec.key] !== undefined).map((spec) => (
          <FlagEditor
            key={spec.key}
            spec={spec}
            current={data.flags[spec.key]}
            updated={data.updated[spec.key]}
            busy={act.busy}
            onApply={(v) => apply(spec.key, v)}
          />
        ))}
    </section>
  );
}

function FlagEditor(props: {
  spec: (typeof FLAG_SPECS)[number];
  current: Flags[FlagKey];
  updated?: { by: string; at: number };
  busy: boolean;
  onApply: (v: Flags[FlagKey]) => void;
}) {
  const { spec, current } = props;
  const [picked, setPicked] = useState<Flags[FlagKey] | undefined>(undefined);
  const choice = picked === undefined ? current : picked;
  const changed = picked !== undefined && picked !== current;
  return (
    <fieldset className="flag">
      <legend>{spec.title}</legend>
      <div className="small">
        Giá trị hiện tại: <code>{String(current)}</code>
        {props.updated ? ` · đổi lần cuối bởi ${props.updated.by} lúc ${fmtTime(props.updated.at)}` : ''}
      </div>
      {spec.options.map((o) => (
        <label key={String(o.value)} className="option">
          <input type="radio" name={spec.key} checked={choice === o.value} onChange={() => setPicked(o.value)} />
          <span>
            <strong>{o.label}</strong>
            <span className="muted small"> {o.does}</span>
          </span>
        </label>
      ))}
      {changed && (
        <div className="actions">
          <button
            disabled={props.busy}
            onClick={() => {
              props.onApply(picked as Flags[FlagKey]);
              setPicked(undefined);
            }}
          >
            Áp dụng {spec.key} = {String(picked)}
          </button>
          <button className="secondary" onClick={() => setPicked(undefined)}>
            Bỏ chọn
          </button>
        </div>
      )}
    </fieldset>
  );
}

function shellQuote(s: string): string {
  return /^[A-Za-z0-9._\/-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;
}

// Matches `claude_pool.py add <label>`: each pool account has its own config dir under ~/.thomhouse-bot/accounts/.
// An account registered with `add-default` uses the machine's normal login; run plain `claude auth login` for it.
export function loginCommand(a: PoolAccountStatus & { config_dir?: string | null }): string {
  const dir = a.config_dir ? shellQuote(a.config_dir) : `"$HOME/.thomhouse-bot/accounts/"${shellQuote(a.label)}`;
  return `CLAUDE_CONFIG_DIR=${dir} claude auth login`;
}

const POOL_STATUS_TEXT: Record<PoolAccountStatus['pool_status'], string> = {
  ok: 'bình thường',
  limited: 'hết lượt dùng',
  login_expired: 'phiên đăng nhập hết hạn',
  blocked: 'bị chặn',
  error: 'lỗi',
};

function RunnerSection({ api }: { api: Api }) {
  const runner = usePoll(() => api.getRunner(), [api], 5000);
  const act = useAction();
  const r = runner.data;
  const accounts = r?.runners.flatMap((x) => x.status?.accounts ?? []) ?? [];
  const labels = [...new Set(accounts.map((a) => a.label))];

  return (
    <section className="box">
      <h3>Máy chạy model và tài khoản Claude</h3>
      <ErrorLine text={runner.error ?? act.error} />
      <Notice text={act.notice} />
      {r && (
        <>
          <p className="small">
            Hàng đợi soạn nháp: {r.queue.queued} việc đang chờ, {r.queue.leased} việc đang chạy.
          </p>
          {r.runners.length === 0 && <p className="error">Chưa có máy chạy model nào kết nối. Bot sẽ không soạn được nháp.</p>}
          {r.runners.map((x) => (
            <div key={x.runner_id} className="small">
              <strong>{x.runner_id}</strong>: {x.online ? 'đang kết nối' : 'mất kết nối'} · lần cuối {fmtTime(x.last_seen_at)}
              {x.status ? ` · ${x.status.hostname} · phiên bản ${x.status.runner_version} · ${x.status.active_jobs}/${x.status.max_concurrency} việc` : ''}
              {x.status ? ` · tài khoản kế tiếp: ${x.status.next_account ?? 'không có tài khoản dùng được'}` : ''}
            </div>
          ))}
          <div className="form inline">
            <label>
              Chọn tài khoản cho máy chạy model
              <select
                value={r.desired_account}
                disabled={act.busy}
                onChange={(e) =>
                  act
                    .run(() => api.setRunnerAccount(e.target.value), `Đã yêu cầu dùng ${e.target.value}; máy chạy model áp dụng ở lần báo trạng thái kế tiếp.`)
                    .then(() => runner.reload())
                }
              >
                <option value="auto">auto: tự chọn tài khoản còn dùng được</option>
                {labels.map((l) => (
                  <option key={l} value={l}>
                    {l}: chỉ dùng tài khoản này
                  </option>
                ))}
              </select>
            </label>
          </div>
          {accounts.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tài khoản</th>
                    <th>Email</th>
                    <th>Gói</th>
                    <th>Dùng được ngay</th>
                    <th>Trạng thái</th>
                    <th>Bị giới hạn đến</th>
                    <th>Lỗi gần nhất</th>
                    <th>Lệnh đăng nhập</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.label}>
                      <td>
                        {a.label}
                        {a.pinned ? ' (đang ghim)' : ''}
                        {a.enabled ? '' : ' (đã tắt)'}
                      </td>
                      <td>{a.login?.email ?? (a.login?.loggedIn === false ? 'chưa đăng nhập' : '')}</td>
                      <td>{a.login?.subscriptionType ?? ''}</td>
                      <td>{a.usable_now ? 'có' : 'không'}</td>
                      <td>{POOL_STATUS_TEXT[a.pool_status] ?? a.pool_status}</td>
                      <td>{a.until ?? ''}</td>
                      <td className="small">{a.last_error}</td>
                      <td>
                        <CopyField value={loginCommand(a)} label={`Lệnh đăng nhập cho ${a.label}`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">
                Chạy lệnh đăng nhập trong Terminal của máy chạy model. Tài khoản đăng ký bằng add-default dùng lệnh claude auth login.
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function outboxText(o: OutboxItem): string {
  if (typeof o.text === 'string') return o.text;
  const p = o.payload as { message?: { text?: unknown } } | null;
  if (p && typeof p.message?.text === 'string') return p.message.text;
  try {
    return JSON.stringify(o.payload, null, 1);
  } catch {
    return String(o.payload);
  }
}

const DECISIONS: Array<{ action: OutboxDecision; label: string; done: string }> = [
  { action: 'requeue', label: 'Gửi lại', done: 'Đã đưa tin vào hàng chờ gửi lại.' },
  { action: 'mark_sent', label: 'Khách đã nhận', done: 'Đã ghi nhận tin đã tới khách.' },
  { action: 'mark_failed', label: 'Ghi là lỗi', done: 'Đã ghi tin là gửi lỗi.' },
];

function OutboxSection({ api, mode }: { api: Api; mode: 'mock' | 'personal' }) {
  const outbox = usePoll(() => api.listOutbox({ limit: 50 }), [api]);
  const bridge = usePoll(() => (mode === 'personal' ? api.bridgeStatus() : Promise.resolve(null)), [api, mode]);
  const act = useAction();
  const decide = async (o: OutboxItem, action: OutboxDecision, done: string) => {
    const r = await act.run(() => api.decideOutbox(o.id, action), done);
    if (r !== undefined) outbox.reload();
  };
  const b = bridge.data;
  return (
    <section className="box">
      <h3>{mode === 'personal' ? 'Hộp thư gửi đi (Zalo cá nhân)' : 'Hộp thư gửi đi (chế độ mock)'}</h3>
      {mode === 'personal' ? (
        <p className="muted small">
          ZALO_MODE = personal: bridge lấy tin trong hàng chờ và gửi bằng zalo-agent. Tin ở trạng thái unknown không được gửi lại tự động;
          anh xem trên điện thoại rồi chọn Gửi lại hoặc Khách đã nhận. 50 tin mới nhất.
        </p>
      ) : (
        <p className="muted small">ZALO_MODE = mock: mọi tin gửi được ghi vào đây thay vì gửi qua Zalo. 50 tin mới nhất.</p>
      )}
      {mode === 'personal' && b && (
        <p className="small">
          Bridge lấy tin lần cuối: {b.last_claim_at ? fmtTime(b.last_claim_at) : 'chưa lần nào'} · chờ gửi {b.counts.queued} · đang gửi{' '}
          {b.counts.leased} · đã gửi {b.counts.sent} · lỗi {b.counts.failed} · unknown {b.counts.unknown}
        </p>
      )}
      <ErrorLine text={outbox.error ?? bridge.error ?? act.error} />
      <Notice text={act.notice} />
      <ul className="cards">
        {(outbox.data?.items ?? []).map((o) => (
          <li key={o.id} className="card">
            <div className="muted small">
              {fmtTime(o.created_at)} · {o.kind} · tới {o.zalo_user_id} · {o.status}
              {o.attempts ? ` · lần thử ${o.attempts}` : ''}
              {o.error ? ` · lỗi: ${o.error}` : ''}
            </div>
            <pre className="text">{outboxText(o)}</pre>
            {o.channel === 'personal' && (o.status === 'failed' || o.status === 'unknown') && (
              <div className="actions">
                {DECISIONS.filter((d) => d.action !== 'mark_failed' || o.status === 'unknown').map((d) => (
                  <button key={d.action} className="secondary" disabled={act.busy} onClick={() => void decide(o, d.action, d.done)}>
                    {d.label}
                  </button>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
