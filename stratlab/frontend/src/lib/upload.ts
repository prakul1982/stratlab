/* Candles from a CSV file, for markets StratLab has no live data for. Kept in memory
   (and in this browser's storage when it fits), keyed by notebook. */

export interface Candle { t: string; o: number; h: number; l: number; c: number; v: number }
export interface Upload { name: string; currency: string; step: number; bars: Candle[] }

const mem = new Map<string, Upload>();
const key = (nid: string) => `stratlab-upload-${nid}`;

export function saveUpload(nid: string, u: Upload) {
  mem.set(nid, u);
  try { localStorage.setItem(key(nid), JSON.stringify(u)); } catch { /* too big for storage: memory only */ }
}
export function getUpload(nid: string): Upload | null {
  if (mem.has(nid)) return mem.get(nid)!;
  try {
    const raw = localStorage.getItem(key(nid));
    if (raw) { const u = JSON.parse(raw) as Upload; mem.set(nid, u); return u; }
  } catch { /* unavailable */ }
  return null;
}

const pad = (n: number) => String(n).padStart(2, "0");

function toIso(date: string, time?: string): string | null {
  let d = date.trim().replace(/^"|"$/g, "");
  if (time) d = `${d} ${time.trim()}`;
  if (/^\d{10}(\.\d+)?$/.test(d)) return new Date(+d * 1000).toISOString();
  if (/^\d{13}$/.test(d)) return new Date(+d).toISOString();
  let m = d.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?(.*)$/);
  if (m) {
    const [, y, mo, da, h = "0", mi = "0", s = "0", rest] = m;
    const tz = (rest || "").trim().match(/^(Z|[+-]\d{2}:?\d{2})$/)?.[1] ?? "";
    return `${y}-${pad(+mo)}-${pad(+da)}T${pad(+h)}:${pad(+mi)}:${pad(+s)}${tz ? (tz === "Z" ? "+00:00" : tz.length === 5 ? tz.slice(0, 3) + ":" + tz.slice(3) : tz) : ""}`;
  }
  m = d.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
  if (m) {
    let [, a, b, y, h = "0", mi = "0", s = "0"] = m;
    // 31/01/2024 is day-first; 01/31/2024 month-first; ambiguous dates are read day-first
    if (+b > 12) [a, b] = [b, a];
    return `${y}-${pad(+b)}-${pad(+a)}T${pad(+h)}:${pad(+mi)}:${pad(+s)}`;
  }
  const parsed = Date.parse(d);
  return Number.isNaN(parsed) ? null : new Date(parsed).toISOString();
}

export function parseCsv(text: string): { bars: Candle[]; skipped: number } {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) throw new Error("The file looks empty.");
  const delim = [",", ";", "\t", "|"].sort((a, b) => lines[0].split(b).length - lines[0].split(a).length)[0];
  const head = lines[0].split(delim).map((h) => h.trim().replace(/^"|"$/g, "").toLowerCase());
  const find = (...names: string[]) => head.findIndex((h) => names.some((n) => h === n || h.startsWith(n + " ") || h.endsWith(" " + n)));
  const iDate = find("date", "datetime", "timestamp", "time", "open time", "day");
  const iTime = head.findIndex((h, i) => i !== iDate && (h === "time" || h === "hour"));
  const [iO, iH, iL, iC] = [find("open", "o"), find("high", "h"), find("low", "l"), find("close", "adj close", "c", "price", "last")];
  const iV = find("volume", "vol", "v");
  if (iDate < 0 || iC < 0) throw new Error("Couldn't find the date and close columns. The first row should be headings like: date, open, high, low, close, volume.");
  const bars: Candle[] = [];
  let skipped = 0;
  for (const line of lines.slice(1)) {
    const f = line.split(delim).map((x) => x.trim().replace(/^"|"$/g, ""));
    const num = (i: number) => (i < 0 ? NaN : parseFloat((f[i] || "").replace(/,/g, "")));
    const c = num(iC);
    const t = toIso(f[iDate] || "", iTime >= 0 ? f[iTime] : undefined);
    if (!t || !Number.isFinite(c) || c <= 0) { skipped++; continue; }
    const o = Number.isFinite(num(iO)) ? num(iO) : c, h = Number.isFinite(num(iH)) ? num(iH) : Math.max(o, c);
    const l = Number.isFinite(num(iL)) ? num(iL) : Math.min(o, c), v = Number.isFinite(num(iV)) ? num(iV) : 0;
    bars.push({ t, o, h: Math.max(h, o, c), l: Math.min(l, o, c), c, v });
  }
  bars.sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
  if (bars.length < 30) throw new Error(`Only ${bars.length} usable rows were found; at least 30 candles are needed.`);
  if (bars.length > 50000) throw new Error("That's more than 50,000 candles. Trim the file and try again.");
  return { bars, skipped };
}
