// Connection settings for the staff console.
// Desktop (Electron): the preload exposes window.thomhouse.getConfig/setConfig; the main process keeps the
// staff token encrypted with safeStorage. Plain web dev: localStorage fallback (token stored in clear text,
// acceptable only on a developer machine).

export interface ConsoleConfig {
  baseUrl: string; // '' = same origin (Vite dev proxy)
  staffToken: string;
  staffId: string;
}

export interface DesktopBridge {
  getConfig(): Promise<Partial<ConsoleConfig> | null>;
  setConfig(cfg: ConsoleConfig): Promise<{ ok: boolean; error?: string }>;
}

declare global {
  interface Window {
    thomhouse?: DesktopBridge;
  }
}

const LS_KEY = 'thomhouse.console.config';

export function storageKind(): 'safeStorage' | 'localStorage' {
  return typeof window !== 'undefined' && window.thomhouse ? 'safeStorage' : 'localStorage';
}

export function defaultBaseUrl(): string {
  // A file:// page has no dev proxy, so it must call the Worker directly.
  if (typeof location !== 'undefined' && location.protocol === 'file:') return 'http://127.0.0.1:8787';
  return '';
}

function normalize(p: Partial<ConsoleConfig> | null | undefined): ConsoleConfig {
  return {
    baseUrl: typeof p?.baseUrl === 'string' ? p.baseUrl.trim() : defaultBaseUrl(),
    staffToken: typeof p?.staffToken === 'string' ? p.staffToken : '',
    staffId: typeof p?.staffId === 'string' && p.staffId.trim() ? p.staffId.trim() : 'staff',
  };
}

export async function loadConfig(): Promise<ConsoleConfig> {
  if (window.thomhouse) return normalize(await window.thomhouse.getConfig());
  try {
    const raw = localStorage.getItem(LS_KEY);
    return normalize(raw ? (JSON.parse(raw) as Partial<ConsoleConfig>) : null);
  } catch {
    return normalize(null);
  }
}

export async function saveConfig(cfg: ConsoleConfig): Promise<void> {
  const clean = normalize(cfg);
  if (window.thomhouse) {
    const r = await window.thomhouse.setConfig(clean);
    if (!r.ok) throw new Error(r.error ?? 'Không lưu được cấu hình');
    return;
  }
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(clean));
  } catch {
    throw new Error('Trình duyệt không cho lưu cấu hình (localStorage bị chặn)');
  }
}
