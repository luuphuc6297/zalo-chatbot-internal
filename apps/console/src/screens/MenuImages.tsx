// Menu images in the conversation view: thumbnails of the printed menu slides (GET /staff/menu-images/:group/:n),
// the images a draft will send (staff may drop some before approving), and "Gửi menu" (staff queue the covers or one
// menu's price slides; slides that print health claims need a confirm). Titles come from data/menu-images.json
// through the server and are rendered as text nodes only.
import { useEffect, useMemo, useState } from 'react';
import type { Api, MenuImagesIndex, MenuSlideView } from '../api';
import { useAction } from '../hooks';
import { ErrorLine, Notice } from './common';

/** Loads the slide index once per API client. null while loading or when the server has no menu routes. */
export function useMenuIndex(api: Api): { index: MenuImagesIndex | null; error: string | null } {
  const [index, setIndex] = useState<MenuImagesIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.menuImages().then(
      (r) => alive && setIndex(r),
      () => alive && setError('Không tải được danh sách ảnh menu từ máy chủ.'),
    );
    return () => {
      alive = false;
    };
  }, [api]);
  return { index, error };
}

const thumbCache = new WeakMap<Api, Map<string, Promise<string>>>();

function loadThumb(api: Api, key: string): Promise<string> {
  let m = thumbCache.get(api);
  if (!m) {
    m = new Map();
    thumbCache.set(api, m);
  }
  let p = m.get(key);
  if (!p) {
    p = api.menuThumb(key);
    p.catch(() => m!.delete(key));
    m.set(key, p);
  }
  return p;
}

export function slideCaption(s: MenuSlideView | undefined, key: string): string {
  return s ? `${s.group_label}, ảnh ${s.n}: ${s.title}` : `Ảnh ${key}`;
}

export function MenuThumb({ api, slideKey, slide }: { api: Api; slideKey: string; slide?: MenuSlideView }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setSrc(null);
    setFailed(false);
    loadThumb(api, slideKey).then(
      (s) => alive && setSrc(s),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [api, slideKey]);
  const caption = slideCaption(slide, slideKey);
  return (
    <figure className="menu-thumb">
      {src ? <img src={src} alt={caption} /> : <div className="menu-thumb-empty muted small">{failed ? 'Không tải được ảnh' : 'Đang tải ảnh...'}</div>}
      <figcaption className="small">
        {caption}
        {slide?.has_medical_claim ? ' · in câu về sức khỏe' : ''}
      </figcaption>
    </figure>
  );
}

/** The images a draft carries; staff remove or restore each one before approving. */
export function DraftImages(props: {
  api: Api;
  keys: string[];
  kept: string[];
  index: MenuImagesIndex | null;
  disabled: boolean;
  onChange: (kept: string[]) => void;
}) {
  const { api, keys, kept, index, disabled, onChange } = props;
  const bySlide = useMemo(() => new Map((index?.slides ?? []).map((s) => [s.key, s])), [index]);
  return (
    <div className="draft-images" aria-label="Ảnh menu của bản nháp">
      <div className="small">
        <strong>Ảnh menu gửi sau câu trả lời: {kept.length}/{keys.length} ảnh.</strong> Bỏ ảnh nào không muốn gửi trước khi duyệt.
      </div>
      <ul className="thumb-grid">
        {keys.map((k) => {
          const on = kept.includes(k);
          const s = bySlide.get(k);
          return (
            <li key={k} className={on ? 'thumb-item' : 'thumb-item removed'}>
              <MenuThumb api={api} slideKey={k} slide={s} />
              <button
                className="secondary"
                disabled={disabled}
                aria-label={`${on ? 'Bỏ' : 'Giữ lại'} ${slideCaption(s, k)}`}
                onClick={() => onChange(on ? kept.filter((x) => x !== k) : keys.filter((x) => x === k || kept.includes(x)))}
              >
                {on ? 'Bỏ ảnh này' : 'Giữ lại ảnh này'}
              </button>
            </li>
          );
        })}
      </ul>
      {kept.length === 0 && <p className="muted small">Đã bỏ hết ảnh: khi duyệt, khách chỉ nhận câu trả lời bằng chữ.</p>}
    </div>
  );
}

export function claimConfirmText(s: MenuSlideView): string {
  return (
    `Ảnh "${s.title}" in câu về sức khỏe${s.claim_note ? ` (${s.claim_note})` : ''}. ` +
    'Bot không được gửi loại ảnh này; nếu nhân viên gửi, khách sẽ đọc được câu đó. Vẫn chọn gửi ảnh này?'
  );
}

/** "Gửi menu": choose the covers of every menu or one menu, keep or drop slides, then queue them as one image message. */
export function SendMenuPanel(props: { api: Api; conversationId: string; index: MenuImagesIndex | null; indexError: string | null; onDone: () => void }) {
  const { api, conversationId, index, indexError, onDone } = props;
  const act = useAction();
  const [open, setOpen] = useState(false);
  const [group, setGroup] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const bySlide = useMemo(() => new Map((index?.slides ?? []).map((s) => [s.key, s])), [index]);
  const offered = !index || !group ? [] : group === 'overview' ? index.overview : (index.groups.find((g) => g.group === group)?.price_list ?? []);
  const max = index?.max_images ?? 10;

  const choose = (g: string) => {
    setGroup(g);
    const keys = !index || !g ? [] : g === 'overview' ? index.overview : (index.groups.find((x) => x.group === g)?.price_list ?? []);
    setPicked(keys.filter((k) => !bySlide.get(k)?.has_medical_claim));
  };

  const toggle = (k: string) => {
    if (picked.includes(k)) return setPicked(picked.filter((x) => x !== k));
    const s = bySlide.get(k);
    if (s?.has_medical_claim && !window.confirm(claimConfirmText(s))) return;
    setPicked(offered.filter((x) => x === k || picked.includes(x)));
  };

  const claimCount = picked.filter((k) => bySlide.get(k)?.has_medical_claim).length;
  const send = async () => {
    const r = await act.run(
      () => api.sendMenuImages(conversationId, { group, keys: picked, ...(claimCount ? { include_claim_slides: true } : {}) }),
      `Đã xếp ${picked.length} ảnh menu vào hàng chờ gửi. Bot vẫn tiếp tục trả lời hội thoại này.`,
    );
    if (r !== undefined) {
      setGroup('');
      setPicked([]);
      onDone();
    }
  };

  return (
    <section className="send-menu" aria-label="Gửi menu">
      <div className="row between">
        <h3>Gửi ảnh menu</h3>
        {!open && (
          <button className="secondary" onClick={() => setOpen(true)}>
            Gửi menu
          </button>
        )}
      </div>
      {open && (
        <div className="form">
          <ErrorLine text={indexError} />
          <label>
            Chọn menu
            <select aria-label="Chọn menu" value={group} disabled={act.busy || !index} onChange={(e) => choose(e.target.value)}>
              <option value="">chọn menu cần gửi</option>
              <option value="overview">Ảnh bìa của tất cả menu</option>
              {(index?.groups ?? []).map((g) => (
                <option key={g.group} value={g.group}>
                  Bảng giá: {g.label}
                </option>
              ))}
            </select>
          </label>
          {group && (
            <>
              <p className="muted small">
                Ảnh được chọn sẵn là ảnh bot cũng được gửi. Ảnh in câu về sức khỏe để trống; chọn ảnh đó thì console hỏi lại trước. Mỗi lần gửi
                tối đa {max} ảnh.
              </p>
              <ul className="thumb-grid">
                {offered.map((k) => {
                  const s = bySlide.get(k);
                  return (
                    <li key={k} className={picked.includes(k) ? 'thumb-item' : 'thumb-item removed'}>
                      <label className="small">
                        <input type="checkbox" checked={picked.includes(k)} disabled={act.busy} onChange={() => toggle(k)} aria-label={`Chọn ${slideCaption(s, k)}`} />{' '}
                        {s?.has_medical_claim ? 'Ảnh in câu về sức khỏe, bot không được gửi' : 'Chọn ảnh này'}
                      </label>
                      <MenuThumb api={api} slideKey={k} slide={s} />
                    </li>
                  );
                })}
              </ul>
              {picked.length > max && <p className="error">Đã chọn {picked.length} ảnh; mỗi lần gửi tối đa {max} ảnh.</p>}
            </>
          )}
          <div className="actions">
            <button disabled={act.busy || !group || picked.length === 0 || picked.length > max} onClick={send}>
              {picked.length ? `Gửi ${picked.length} ảnh menu` : 'Gửi ảnh menu'}
              {claimCount ? ` (có ${claimCount} ảnh in câu về sức khỏe)` : ''}
            </button>
            <button
              className="secondary"
              disabled={act.busy}
              onClick={() => {
                setOpen(false);
                setGroup('');
                setPicked([]);
              }}
            >
              Đóng
            </button>
          </div>
        </div>
      )}
      <ErrorLine text={act.error} />
      <Notice text={act.notice} />
    </section>
  );
}
