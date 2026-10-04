import { useEffect, useState } from "react";
import { api } from "./api";

/** The exchange's surveillance lists for Indian stocks (ASM, GSM, ESM, trade-to-trade, F&O ban, price-band changes):
 * one answer for every badge in the app, read once and kept for ten minutes. */
export interface SurvLabel { short: string; label: string; text: string }
export interface SurvList { id: string; label: string; as_of: string | null; stale: boolean; failed: boolean; checked: string | null }
export interface SurvView {
  flags: Record<string, string[]>; labels: Record<string, SurvLabel>; lists: SurvList[]; as_of: string | null; note: string; source: string;
}

export const SURV_FAMILIES = [["asm", "ASM (long or short term)"], ["gsm", "GSM"], ["esm", "ESM"], ["t2t", "Trade-to-trade"], ["fo_ban", "F&O ban"]] as const;
const PART: Record<string, string> = { asm_lt: "asm", asm_st: "asm", gsm: "gsm", esm: "esm", fo_ban: "fo_ban", t2t: "bands", band: "bands" };

let cached: { at: number; p: Promise<SurvView | null> } | null = null;

export function loadSurveillance(): Promise<SurvView | null> {
  if (!cached || Date.now() - cached.at > 10 * 60_000) {
    const p = api<SurvView>("/research/surveillance").catch(() => { cached = null; return null; });
    cached = { at: Date.now(), p };
  }
  return cached.p;
}

/** The lists, once loaded (null until then, or when they can't be read). `on` false skips the call (US stocks). */
export function useSurveillance(on = true): SurvView | null {
  const [v, setV] = useState<SurvView | null>(null);
  useEffect(() => {
    if (!on) return;
    let live = true;
    loadSurveillance().then((x) => live && setV(x));
    return () => { live = false; };
  }, [on]);
  return v;
}

/** The words for one flag on one stock (a price-band change carries the stock's own numbers). */
export function survLabel(v: SurvView, symbol: string, code: string): SurvLabel | null {
  return (code === "band" ? v.labels[`band:${symbol}`] : v.labels[code]) ?? null;
}

/** The list a flag comes from, for its date. */
export function survList(v: SurvView, code: string): SurvList | null {
  const id = PART[code.split(":")[0]];
  return v.lists.find((l) => l.id === id) ?? null;
}
