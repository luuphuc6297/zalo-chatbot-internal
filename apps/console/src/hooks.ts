import { useCallback, useEffect, useRef, useState } from 'react';
import { errorText } from './errors';

export const POLL_MS = 3000;

// Polls fn every `ms`; never overlaps calls; resets data when deps change.
export function usePoll<T>(fn: () => Promise<T>, deps: unknown[], ms = POLL_MS) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      try {
        const d = await fnRef.current();
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(errorText(e));
      } finally {
        if (alive) timer = setTimeout(run, ms);
      }
    };
    void run();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, ms]);

  useEffect(() => {
    setData(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, reload };
}

// Runs one staff action at a time and keeps its error/result text.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [raw, setRaw] = useState<unknown>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    setNotice(null);
    setRaw(null);
    try {
      const r = await fn();
      if (ok) setNotice(ok);
      return r;
    } catch (e) {
      setError(errorText(e));
      setRaw(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, notice, raw, run, setError };
}
