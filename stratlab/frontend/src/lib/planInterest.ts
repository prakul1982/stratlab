/* "Tell me when plans open": while Basic and Pro can't be bought, a lock or a plan limit offers this instead of a dead-end
 * "See plans". The server keeps one record per person (/me/plan-interest). The answer is shared by every button on the
 * page, so pressing one turns the others over too. */
import { useEffect, useSyncExternalStore } from "react";
import { api } from "./api";

export type InterestSource = "lock" | "plans" | "limit" | "inline";
export interface Interest { registered: boolean; at: string | null }

let state: Interest | null = null;
let loading: Promise<void> | null = null;
const subs = new Set<() => void>();
const set = (s: Interest | null) => { state = s; subs.forEach((f) => f()); };

/** Read it once (a second call waits for the first). */
export function loadInterest(): Promise<void> {
  if (state) return Promise.resolve();
  loading ??= api<Interest>("/me/plan-interest").then(set).catch(() => undefined).finally(() => { loading = null; });
  return loading;
}

/** Put the person on the list. */
export async function joinInterest(source: InterestSource): Promise<Interest> {
  const r = await api<Interest>("/me/plan-interest", { method: "PUT", body: { source } });
  set(r);
  return r;
}

/** Take them off again. */
export async function leaveInterest(): Promise<Interest> {
  const r = await api<Interest>("/me/plan-interest", { method: "DELETE" });
  set(r);
  return r;
}

/** Forget what was read (a different person signed in). */
export function resetInterest() { loading = null; set(null); }

/** Whether this person is on the list: null until it is read. `on` false reads nothing. */
export function useInterest(on = true): Interest | null {
  const v = useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f); }; }, () => state, () => null);
  useEffect(() => { if (on) void loadInterest(); }, [on]);
  return v;
}

export const JOINED = "Done. We'll tell you when plans open.";
export const JOIN_LABEL = "Tell me when plans open";
