import { useState } from 'react';
import type { Badge } from '../labels';

export function Badges({ badges }: { badges: Badge[] }) {
  if (badges.length === 0) return null;
  return (
    <span className="badges">
      {badges.map((b) => (
        <span key={b.text} className={`badge ${b.kind}`}>
          {b.text}
        </span>
      ))}
    </span>
  );
}

export function ErrorLine({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <p className="error" role="alert">
      {text}
    </p>
  );
}

export function Notice({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <p className="notice" role="status">
      {text}
    </p>
  );
}

// Copy a shell command; falls back to selecting the text when the clipboard API is not allowed.
export function CopyField({ value, label }: { value: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'manual'>('idle');
  return (
    <span className="copy-field">
      <input readOnly value={value} aria-label={label} onFocus={(e) => e.currentTarget.select()} />
      <button
        className="secondary"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setState('copied');
          } catch {
            setState('manual');
          }
        }}
      >
        {state === 'copied' ? 'Đã chép' : 'Chép lệnh'}
      </button>
      {state === 'manual' && <span className="muted small">Không chép tự động được; bấm vào ô rồi Cmd+C.</span>}
    </span>
  );
}
