// Staff console shell: connection config, navigation, and the five screens.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createApi } from './api';
import { type ConsoleConfig, loadConfig, saveConfig } from './config';
import { usePoll } from './hooks';
import { BookingsScreen } from './screens/Bookings';
import { ConversationsScreen } from './screens/Conversations';
import { HandoffsScreen } from './screens/Handoffs';
import { SettingsScreen } from './screens/Settings';
import { VisitsScreen } from './screens/Visits';
import { ErrorLine } from './screens/common';

type Tab = 'conversations' | 'handoffs' | 'bookings' | 'visits' | 'settings';

export function App() {
  const [config, setConfig] = useState<ConsoleConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('conversations');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    loadConfig()
      .then((c) => {
        setConfig(c);
        if (!c.staffToken) setTab('settings');
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  const api = useMemo(
    () => (config && config.staffToken ? createApi({ baseUrl: config.baseUrl, staffToken: config.staffToken, staffId: config.staffId }) : null),
    [config],
  );

  const onSaveConfig = useCallback(async (c: ConsoleConfig) => {
    await saveConfig(c);
    setConfig(await loadConfig());
  }, []);

  const openConversation = useCallback((id: string) => {
    setSelected(id);
    setTab('conversations');
  }, []);

  if (loadError) return <ErrorLine text={`Không đọc được cấu hình: ${loadError}`} />;
  if (!config) return <p className="muted pad">Đang tải cấu hình...</p>;

  return (
    <div className="app">
      <TopBar api={api} tab={tab} setTab={setTab} />
      <main>
        {!api || tab === 'settings' ? (
          <SettingsScreenWithHealth api={api} config={config} onSaveConfig={onSaveConfig} />
        ) : tab === 'conversations' ? (
          <ConversationsScreen api={api} selectedId={selected} onSelect={setSelected} />
        ) : tab === 'handoffs' ? (
          <HandoffsScreen api={api} onOpenConversation={openConversation} />
        ) : tab === 'bookings' ? (
          <BookingsScreen api={api} onOpenConversation={openConversation} />
        ) : (
          <VisitsScreen api={api} />
        )}
      </main>
    </div>
  );
}

function TopBar(props: { api: ReturnType<typeof createApi> | null; tab: Tab; setTab: (t: Tab) => void }) {
  const { api } = props;
  const handoffs = usePoll(() => (api ? api.listHandoffs({ status: 'open', limit: 200 }) : Promise.resolve(null)), [api]);
  const health = usePoll(() => (api ? api.health() : Promise.resolve(null)), [api], 15_000);
  const openCount = handoffs.data?.items.length ?? 0;
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'conversations', label: 'Hội thoại' },
    { id: 'handoffs', label: openCount ? `Cần nhân viên (${openCount})` : 'Cần nhân viên' },
    { id: 'bookings', label: 'Yêu cầu đặt lịch' },
    { id: 'visits', label: 'Ghi nhận buổi làm' },
    { id: 'settings', label: 'Cài đặt' },
  ];
  return (
    <header className="topbar">
      <strong className="brand">thom house</strong>
      <nav aria-label="Màn hình">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={props.tab === t.id ? 'tab active' : 'tab'}
            aria-current={props.tab === t.id ? 'page' : undefined}
            disabled={!api && t.id !== 'settings'}
            onClick={() => props.setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <span className="conn small">
        {!api
          ? 'chưa nhập staff token'
          : health.error
            ? 'mất kết nối máy chủ'
            : health.data
              ? `máy chủ ${health.data.env} · Zalo ${health.data.zalo_mode === 'mock' ? 'mock (không gửi thật)' : health.data.zalo_mode === 'personal' ? 'cá nhân (qua bridge)' : 'OA thật'}`
              : 'đang kết nối...'}
      </span>
    </header>
  );
}

function SettingsScreenWithHealth(props: {
  api: ReturnType<typeof createApi> | null;
  config: ConsoleConfig;
  onSaveConfig: (c: ConsoleConfig) => Promise<void>;
}) {
  const health = usePoll(() => (props.api ? props.api.health() : Promise.resolve(null)), [props.api], 15_000);
  return <SettingsScreen api={props.api} config={props.config} zaloMode={health.data?.zalo_mode ?? null} onSaveConfig={props.onSaveConfig} />;
}
