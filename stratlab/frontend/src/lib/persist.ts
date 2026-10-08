import { useCallback, useEffect, useState } from "react";

/** A small setting kept on this device (localStorage) and shared by every part of the page that reads it: change it in
 * the breadcrumb and the sidebar updates at once. Storage can be off (a private window): the value then lives only until
 * the page is closed, and nothing throws. */
const memory = new Map<string, unknown>();
const listeners = new Map<string, Set<() => void>>();

function read<T>(key: string, fallback: T): T {
  if (memory.has(key)) return memory.get(key) as T;
  try {
    const raw = localStorage.getItem(key);
    if (raw !== null) return JSON.parse(raw) as T;
  } catch { /* storage off or not JSON */ }
  return fallback;
}

export function writePersisted<T>(key: string, value: T) {
  memory.set(key, value);
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage off */ }
  listeners.get(key)?.forEach((f) => f());
}

export function usePersisted<T>(key: string, fallback: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => read(key, fallback));
  useEffect(() => {
    setValue(read(key, fallback));      // a new key (another person signed in) reads its own value
    const set = listeners.get(key) ?? new Set();
    const f = () => setValue(read(key, fallback));
    set.add(f);
    listeners.set(key, set);
    const onStorage = (e: StorageEvent) => { if (e.key === key) { memory.delete(key); f(); } };    // another tab changed it
    window.addEventListener("storage", onStorage);
    return () => { set.delete(f); window.removeEventListener("storage", onStorage); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const update = useCallback((v: T | ((prev: T) => T)) => {
    const next = typeof v === "function" ? (v as (p: T) => T)(read(key, fallback)) : v;
    writePersisted(key, next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return [value, update];
}
