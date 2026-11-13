import { ago } from "../../lib/format";

export type RebuildMarket = { region: string; counted: boolean; current?: number; of?: number; pages?: number | null; at?: string | null };
export type PagesRebuild = { version: number; markets: RebuildMarket[] };

export const MARKET: Record<string, string> = { IN: "India", US: "US" };
const n = (x: number) => x.toLocaleString("en-IN");

/** One market's line: the stored pages at the current facts version, N of M, with the share and when they were counted. */
export function rebuildLine(m: RebuildMarket, version: number): { value: string; note: string } {
  if (!m.counted || m.of == null) {
    return { value: "Not counted yet", note: `Counted the next time the stored pages are gathered (every half hour) at facts version ${version}` };
  }
  const cur = m.current ?? 0;
  const share = m.of ? Math.floor((cur / m.of) * 100) : 100;
  const left = m.of - cur;
  return {
    value: `${n(cur)} of ${n(m.of)}`,
    note: `${share}% at facts version ${version}${left ? `; ${n(left)} still at an earlier one, rebuilt a few at a time, the largest first` : "; every page is rebuilt"}`
      + (m.at ? ` (counted ${ago(m.at)})` : ""),
  };
}

