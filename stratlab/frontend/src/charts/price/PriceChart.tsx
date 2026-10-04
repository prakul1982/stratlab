/* The price chart every page with OHLC prices uses: company pages, backtests and paper trading. Chart types,
 * timeframes and ranges, volume, indicators (the engine's own maths), drawings saved per symbol, compare, log and %
 * scales, fullscreen and a PNG download. Loaded as its own chunk (see lazy.tsx). Facts only: no signals. */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../../lib/api";
import { CHART_TYPES, PriceChartEngine, type ChartMarker, type ChartType, type Hover, type PriceLevel, type Theme } from "./engine";
import { DRAW_TOOLS, type Drawing, type DrawingKind } from "./drawings";
import type { ScaleMode } from "./scales";
import { clampParam, newStudy, STAGE_NAMES, STUDIES, STUDY, studyLabel, type StudyConfig, type StudyType } from "./studies";
import { aggregate, indexAtOrBefore, merge, parseTime, toBars, type Bar, type RawCandle } from "./transforms";
import "./priceChart.css";

export type Tf = "5m" | "15m" | "1h" | "1d" | "1w" | "1mo";
export type BaseTf = "5m" | "15m" | "1h" | "1d";
export type RangeKey = "1D" | "5D" | "1M" | "6M" | "YTD" | "1Y" | "5Y" | "All";
export interface Loaded { candles: RawCandle[]; more?: boolean }
export type Loader = (tf: BaseTf, opts: { range?: string; before?: string }) => Promise<Loaded>;

export interface PriceChartProps {
  /** What the chart shows, in the legend and the PNG's title. */
  symbol: string;
  /** Where drawings are saved, e.g. "IN:RELIANCE" (letters, digits and : . - _ ^ & =). */
  storageKey: string;
  currency?: string | null;
  /** Reads candles for a timeframe: the first window covering `range`, or the page older than `before`. */
  load?: Loader;
  /** Or a fixed or live list of candles (paper trading), redrawn in place as it grows. */
  bars?: RawCandle[];
  /** The timeframe of `bars`, or the first one `load` shows. */
  tf?: Tf;
  timeframes?: Tf[];
  range?: RangeKey | null;
  markers?: { t: string; side: "buy" | "sell" }[];
  levels?: PriceLevel[];
  /** Indicators that come with the page (a strategy's own), shown on top of the person's saved ones. */
  pageStudies?: StudyConfig[];
  /** Candles of another symbol, to compare on a % scale. */
  compareLoad?: (symbol: string) => Promise<RawCandle[]>;
  compareHint?: string;
  height?: number;
  note?: ReactNode;
  /** How far back the first read of daily candles goes when no range is picked ("1y", "3y", "5y", "max"). */
  history?: string;
  /** Only closes are known (an uploaded file): drawn as a line, area or baseline. */
  closesOnly?: boolean;
}

const TF_LABEL: Record<Tf, string> = { "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1D", "1w": "1W", "1mo": "1M" };
const TF_LONG: Record<Tf, string> = { "5m": "5-minute", "15m": "15-minute", "1h": "1-hour", "1d": "Daily", "1w": "Weekly", "1mo": "Monthly" };
const ALL_TFS: Tf[] = ["5m", "15m", "1h", "1d", "1w", "1mo"];
const RANGES: { key: RangeKey; tf: Tf; fetch: string }[] = [
  { key: "1D", tf: "5m", fetch: "1d" }, { key: "5D", tf: "15m", fetch: "5d" }, { key: "1M", tf: "1h", fetch: "1m" },
  { key: "6M", tf: "1d", fetch: "6m" }, { key: "YTD", tf: "1d", fetch: "ytd" }, { key: "1Y", tf: "1d", fetch: "1y" },
  { key: "5Y", tf: "1w", fetch: "5y" }, { key: "All", tf: "1mo", fetch: "max" },
];
const LS = { type: "stratlab.pc.type", studies: "stratlab.pc.studies", volume: "stratlab.pc.volume", draw: "stratlab.pc.draw." };

function lsGet<T>(k: string, fallback: T): T {
  try { const v = localStorage.getItem(k); return v == null ? fallback : (JSON.parse(v) as T); } catch { return fallback; }
}
function lsSet(k: string, v: unknown): void {
  try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: not remembered */ }
}

function readTheme(el: HTMLElement): Theme {
  const cs = getComputedStyle(el);
  const v = (k: string, d: string) => cs.getPropertyValue(k).trim() || d;
  const mono = v("--mono", "ui-monospace, monospace");
  return {
    bg: v("--card", "#FFFDF8"), text: v("--ink", "#1D1B17"), muted: v("--muted", "#5C574D"), grid: v("--rule", "#EAE3D3"),
    border: v("--line", "#E2DAC8"), ink: v("--ink", "#1D1B17"), accent: v("--blue", "#1F4FB5"),
    up: v("--pc-up", "#1F4FB5"), down: v("--pc-down", "#B4500F"), onUp: v("--pc-on-up", "#fff"), onDown: v("--pc-on-down", "#fff"),
    slots: [v("--pc-s0", "#138A62"), v("--pc-s1", "#A8327A"), v("--pc-s2", "#6F695C")],
    font: `11.5px ${mono}`,
  };
}

const formatters = new Map<string, Intl.NumberFormat>();
function numberFormat(locale: string, d: number): Intl.NumberFormat {
  const k = `${locale}|${d}`;
  let f = formatters.get(k);
  if (!f) { f = new Intl.NumberFormat(locale, { minimumFractionDigits: d, maximumFractionDigits: d }); formatters.set(k, f); }
  return f;
}

function validStudies(v: unknown): StudyConfig[] {
  if (!Array.isArray(v)) return [];
  return v.filter((s): s is StudyConfig => !!s && typeof s === "object" && (s as StudyConfig).type in STUDY && Array.isArray((s as StudyConfig).params))
    .map((s) => ({ ...s, params: STUDY[s.type].params.map((p, i) => clampParam(p, Number(s.params[i]))), slot: Number.isInteger(s.slot) ? s.slot : 0 }))
    .slice(0, 12);
}

const isoOf = (t: number) => new Date(t).toISOString();

/* small line icons, drawn like the app's own */
const I = (d: ReactNode) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
const ICON: Record<string, ReactNode> = {
  trend: I(<><path d="M4 19 20 5" /><circle cx="4" cy="19" r="1.6" /><circle cx="20" cy="5" r="1.6" /></>),
  hline: I(<><path d="M3 12h18" /><circle cx="12" cy="12" r="1.6" /></>),
  ray: I(<><path d="M4 18 21 6" /><circle cx="4" cy="18" r="1.6" /></>),
  rect: I(<rect x="4" y="6" width="16" height="12" rx="1" />),
  fib: I(<><path d="M3 5h18M3 10h18M3 14h18M3 19h18" /></>),
  text: I(<><path d="M5 6h14M12 6v13" /></>),
  zoomIn: I(<><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4M8 11h6M11 8v6" /></>),
  zoomOut: I(<><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4M8 11h6" /></>),
  reset: I(<><path d="M4 12a8 8 0 1 0 2.4-5.7" /><path d="M4 4v4h4" /></>),
  camera: I(<><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>),
  full: I(<><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" /></>),
  exit: I(<><path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5" /></>),
  trash: I(<><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></>),
  gear: I(<><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>),
};

export default function PriceChart(props: PriceChartProps) {
  const { symbol, storageKey, currency, load, markers, levels, pageStudies, compareLoad, height = 420 } = props;
  const offered = (props.timeframes ?? (load ? ALL_TFS : [props.tf ?? "1d"])).filter((t) => ALL_TFS.includes(t));
  const rootRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<PriceChartEngine | null>(null);
  const baseRef = useRef<Bar[]>([]);               // candles as loaded (before weekly/monthly grouping)
  const moreRef = useRef(false);
  const loadingMore = useRef(false);
  const reqRef = useRef(0);
  const maybeMoreRef = useRef<() => void>(() => {});

  const [tf, setTf] = useState<Tf>(props.tf && offered.includes(props.tf) ? props.tf : offered.includes("1d") ? "1d" : offered[0]);
  const [range, setRange] = useState<RangeKey | null>(load ? (props.range === undefined ? "1Y" : props.range) : null);
  const [type, setType] = useState<ChartType>(() => { const t = lsGet<string>(LS.type, "candles"); return CHART_TYPES.some((c) => c.type === t) ? t as ChartType : "candles"; });
  const [volume, setVolume] = useState(() => lsGet<unknown>(LS.volume, true) !== false);
  const [mine, setMine] = useState<StudyConfig[]>(() => validStudies(lsGet(LS.studies, [])));
  const [pageList, setPageList] = useState<StudyConfig[]>(pageStudies ?? []);
  const [mode, setMode] = useState<ScaleMode>("normal");
  const [auto, setAuto] = useState(true);
  const [tool, setTool] = useState<DrawingKind | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawCount, setDrawCount] = useState(0);
  const [full, setFull] = useState(false);
  const [menu, setMenu] = useState<"studies" | "draw" | "compare" | null>(null);
  const [edit, setEdit] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [error, setError] = useState("");
  const setMore = (v: boolean) => { if (rootRef.current) rootRef.current.dataset.more = String(v); };
  const [fetchingMore, setFetchingMore] = useState(false);
  const [table, setTable] = useState(false);
  const [cmp, setCmp] = useState<{ symbol: string; bars: Bar[] } | null>(null);
  const [cmpText, setCmpText] = useState("");
  const [cmpBusy, setCmpBusy] = useState(false);
  const [, setTick] = useState(0);

  const studies = useMemo(() => [...pageList, ...mine.map((s) => ({ ...s, slot: s.slot + pageList.length }))], [pageList, mine]);
  const intraday = tf === "5m" || tf === "15m" || tf === "1h";
  const locale = currency === "INR" ? "en-IN" : "en-US";

  const syncData = useCallback(() => {
    const e = engineRef.current, el = rootRef.current;
    if (!e || !el) return;
    const s = e.state();
    Object.assign(el.dataset, { bars: String(s.bars), from: String(s.from), to: String(s.to), spacing: s.spacing.toFixed(3), mode: s.mode,
      auto: String(s.auto), drawings: String(s.drawings), tool: s.tool ?? "", selected: s.selected ?? "" });
  }, []);

  // ---------- the engine ----------
  useEffect(() => {
    const host = canvasRef.current!;
    const e = new PriceChartEngine(host, readTheme(rootRef.current!), (v, d) => numberFormat(locale, d).format(v));
    engineRef.current = e;
    let raf = 0;
    e.listen("crosshair", (h) => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => setHover(h)); });
    e.listen("select", (id) => { setSelected(id); syncData(); });
    e.listen("tool", (t) => { setTool(t); syncData(); });
    e.listen("drawings", (d) => { setDrawCount(d.length); saveDrawings(d); syncData(); });
    e.listen("view", () => { syncData(); setAuto(e.auto); maybeMoreRef.current(); });
    const retheme = () => e.setTheme(readTheme(rootRef.current!));
    const mo = new MutationObserver(retheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    mq?.addEventListener?.("change", retheme);
    return () => { cancelAnimationFrame(raf); mo.disconnect(); mq?.removeEventListener?.("change", retheme); e.destroy(); engineRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const lineish = type === "line" || type === "area" || type === "baseline";
  const shownType: ChartType = props.closesOnly && !lineish ? "line" : type;
  useEffect(() => { engineRef.current?.setType(shownType); rootRef.current!.dataset.type = shownType; }, [shownType]);
  useEffect(() => { lsSet(LS.type, type); }, [type]);
  useEffect(() => { engineRef.current?.setVolume(volume); lsSet(LS.volume, volume); }, [volume]);
  useEffect(() => { engineRef.current?.setStudies(studies); rootRef.current!.dataset.studies = String(studies.length); setTick((x) => x + 1); }, [studies]);
  useEffect(() => { lsSet(LS.studies, mine); }, [mine]);
  useEffect(() => {
    const list = (markers ?? []).map((m) => ({ t: parseTime(m.t)?.[0] ?? NaN, side: m.side })).filter((m) => Number.isFinite(m.t)) as ChartMarker[];
    engineRef.current?.setMarkers(list);
    rootRef.current!.dataset.markers = String(list.length);
  }, [markers]);
  useEffect(() => { engineRef.current?.setLevels(levels ?? []); }, [levels]);
  useEffect(() => { engineRef.current?.setScaleMode(mode); syncData(); }, [mode, syncData]);
  useEffect(() => { engineRef.current?.setIntraday(intraday); rootRef.current!.dataset.tf = tf; }, [intraday, tf]);
  useEffect(() => {
    engineRef.current?.setCompare(cmp ? { label: cmp.symbol, bars: cmp.bars } : null);
    if (cmp) setMode("percent");
  }, [cmp]);

  // ---------- drawings, per symbol: the account first, this browser as the fallback ----------
  const saveTimer = useRef(0);
  const saveDrawings = useCallback((d: Drawing[]) => {
    lsSet(LS.draw + storageKey, d);
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      api("/chart/drawings", { method: "PUT", body: { symbol: storageKey, items: d } }).catch(() => { /* kept in this browser */ });
    }, 500);
  }, [storageKey]);

  useEffect(() => {
    const e = engineRef.current;
    if (!e) return;
    let live = true;
    const local = lsGet<Drawing[]>(LS.draw + storageKey, []);
    e.setDrawings(Array.isArray(local) ? local : []);
    setDrawCount(e.drawings.length);
    api<{ items: Drawing[] }>(`/chart/drawings?symbol=${encodeURIComponent(storageKey)}`)
      .then((r) => {
        if (!live || !Array.isArray(r?.items)) return;
        if (!r.items.length && local.length) { saveDrawings(local); return; }      // drawn while signed out: keep them
        e.setDrawings(r.items); setDrawCount(r.items.length); lsSet(LS.draw + storageKey, r.items); syncData();
      })
      .catch(() => { /* signed out or offline: this browser's copy */ });
    syncData();
    return () => { live = false; };
  }, [storageKey, saveDrawings, syncData]);

  // ---------- candles ----------
  const shownFrom = useCallback((base: Bar[], t: Tf) => (t === "1w" ? aggregate(base, "week") : t === "1mo" ? aggregate(base, "month") : base), []);

  const applyRange = useCallback((r: RangeKey | null) => {
    const e = engineRef.current, bars = e?.bars;
    if (!e || !bars?.length || !r) return;
    const last = bars[bars.length - 1];
    const d = new Date(last.w);
    let from: number;
    if (r === "1D" || r === "5D") {
      const days = [...new Set(bars.map((b) => b.day))];
      const keep = days.slice(-(r === "1D" ? 1 : 5))[0];
      from = bars.find((b) => b.day === keep)!.t;
    } else if (r === "All") from = bars[0].t;
    else if (r === "YTD") from = last.t - (last.w - Date.UTC(d.getUTCFullYear(), 0, 1));
    else {
      const months = { "1M": 1, "6M": 6, "1Y": 12, "5Y": 60 }[r];
      from = last.t - (last.w - Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - months, d.getUTCDate()));
    }
    e.showFrom(from);
  }, []);

  useEffect(() => {
    if (!load) return;
    const e = engineRef.current!;
    const req = ++reqRef.current;
    const base: BaseTf = tf === "1w" || tf === "1mo" ? "1d" : tf;
    const fetchRange = range ? RANGES.find((x) => x.key === range)!.fetch : tf === "1w" ? "5y" : tf === "1mo" ? "max" : props.history ?? "1y";
    setStatus("loading"); setError("");
    load(base, { range: fetchRange })
      .then((r) => {
        if (req !== reqRef.current) return;
        const bars = toBars(r.candles ?? []);
        baseRef.current = bars;
        moreRef.current = !!r.more; setMore(!!r.more);
        rootRef.current!.dataset.loaded = tf;
        e.setData(shownFrom(bars, tf));
        setStatus(bars.length ? "ready" : "empty");
        if (range) applyRange(range);
        syncData();
      })
      .catch((err) => { if (req === reqRef.current) { setStatus("error"); setError((err as Error).message || "Couldn't load prices."); } });
  }, [load, tf, range, shownFrom, applyRange, syncData]);

  // older candles when the chart is scrolled back to its first ones
  const maybeMore = useCallback(() => {
    const e = engineRef.current;
    if (!e || !load || !moreRef.current || loadingMore.current || !baseRef.current.length) return;
    if (e.visibleRange()[0] > 30) return;
    loadingMore.current = true; setFetchingMore(true);
    const req = reqRef.current;
    const base: BaseTf = tf === "1w" || tf === "1mo" ? "1d" : tf;
    load(base, { before: isoOf(baseRef.current[0].t) })
      .then((r) => {
        if (req !== reqRef.current) return;
        const older = toBars(r.candles ?? []).filter((b) => b.t < baseRef.current[0].t);
        moreRef.current = !!r.more && older.length > 0; setMore(moreRef.current);
        if (!older.length) return;
        baseRef.current = [...older, ...baseRef.current];
        e.replaceOlder(shownFrom(baseRef.current, tf));
        syncData();
      })
      .catch(() => { moreRef.current = false; setMore(false); })
      .finally(() => { loadingMore.current = false; setFetchingMore(false); });
  }, [load, tf, shownFrom, syncData]);
  maybeMoreRef.current = maybeMore;

  // fixed or live candles (paper trading): patched in place as they grow
  useEffect(() => {
    if (load || !props.bars) return;
    const e = engineRef.current!;
    const next = toBars(props.bars);
    const was = baseRef.current;
    const m = merge(was, next);
    if (m.kind === "same" && was.length) return;
    baseRef.current = m.bars;
    if (m.kind === "reset" || !was.length) e.setData(m.bars, was.length > 0);
    else for (const b of m.bars.slice(Math.max(0, was.length - 1))) e.update(b);
    setStatus(m.bars.length ? "ready" : "empty");
    syncData();
  }, [load, props.bars, syncData]);

  // ---------- actions ----------
  const pickTf = (t: Tf) => { setRange(null); setTf(t); setMenu(null); };
  const pickRange = (r: RangeKey) => {
    const want = RANGES.find((x) => x.key === r)!.tf;
    const t = offered.includes(want) ? want : offered.includes("1d") ? "1d" : offered[0];
    setTf(t); setRange(r);
    if (t === tf && r === range) applyRange(r);
  };
  const addStudy = (t: StudyType) => { setMine((s) => [...s, newStudy(t, s)]); setMenu(null); };
  const removeStudy = (id: string) => {
    setMine((s) => s.filter((x) => x.id !== id));
    setPageList((s) => s.filter((x) => x.id !== id));
    if (edit === id) setEdit(null);
  };
  const setParam = (id: string, i: number, v: number) => {
    const fix = (s: StudyConfig) => (s.id !== id ? s : { ...s, params: s.params.map((p, k) => (k === i ? clampParam(STUDY[s.type].params[k], v) : p)) });
    setMine((s) => s.map(fix)); setPageList((s) => s.map(fix));
  };
  const pickTool = (t: DrawingKind | null) => { engineRef.current?.setTool(t === tool ? null : t); setMenu(null); };
  const shot = () => {
    const e = engineRef.current;
    if (!e) return;
    const canvas = e.snapshot(`${symbol} · ${TF_LONG[tf]}${cmp ? ` vs ${cmp.symbol}` : ""}`);
    canvas.toBlob((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `${symbol.replace(/[^A-Za-z0-9_-]+/g, "-")}-${TF_LABEL[tf]}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }, "image/png");
  };
  const toggleFull = () => {
    const next = !full;
    setFull(next);
    const el = rootRef.current!;
    if (next) el.requestFullscreen?.().catch(() => { /* the CSS version is enough */ });
    else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  };
  useEffect(() => {
    const off = () => { if (!document.fullscreenElement) setFull(false); };
    document.addEventListener("fullscreenchange", off);
    return () => document.removeEventListener("fullscreenchange", off);
  }, []);
  useEffect(() => {
    rootRef.current!.dataset.full = String(full);
    if (!full) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && !engineRef.current?.tool) setFull(false); };
    window.addEventListener("keydown", esc);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", esc); };
  }, [full]);
  const doCompare = async (sym: string) => {
    if (!compareLoad || !sym.trim()) return;
    setCmpBusy(true);
    try {
      const bars = toBars(await compareLoad(sym.trim().toUpperCase()));
      if (!bars.length) throw new Error("No prices for that symbol.");
      setCmp({ symbol: sym.trim().toUpperCase(), bars });
      setMenu(null);
    } catch (err) { setError((err as Error).message); setTimeout(() => setError(""), 4000); } finally { setCmpBusy(false); }
  };

  // close a menu on a click outside it or Esc
  useEffect(() => {
    if (!menu && !edit) return;
    const close = (e: Event) => { if (!(e.target as HTMLElement).closest?.(".pc-wrap, .pc-pop")) { setMenu(null); setEdit(null); } };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(null); setEdit(null); } };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [menu, edit]);

  // ---------- the legend ----------
  const e = engineRef.current;
  const h = hover ?? (e && e.bars.length ? e.hoverAt(e.bars.length - 1) : null);
  const fmt = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "–" : (e ? e.priceText(v) : String(v)));
  const chg = h && h.prev ? h.bar.c - h.prev.c : null;
  const chgPct = h && h.prev && h.prev.c ? ((h.bar.c / h.prev.c) - 1) * 100 : null;
  const sw = (color: string, dash = false) => <span className={`sw${dash ? " dash" : ""}`} style={dash ? { color } : { background: color }} aria-hidden="true" />;
  const th = e ? readThemeCached(rootRef.current) : null;
  const slotColor = (slot: number) => (th ? th.slots[slot % th.slots.length] : "currentColor");
  const cmpPct = (() => {
    if (!e || !cmp || !h) return null;
    const [a] = e.visibleRange();
    const first = indexAtOrBefore(cmp.bars, e.bars[a]?.t ?? 0);
    const now = indexAtOrBefore(cmp.bars, h.bar.t);
    return first >= 0 && now >= 0 ? (cmp.bars[now].c / cmp.bars[first].c - 1) * 100 : null;
  })();

  const lastBars = table && e ? e.bars.slice(-60).reverse() : [];
  const first = e?.bars[0], last = e?.bars[e.bars.length - 1];
  const summary = first && last
    ? `${symbol}, ${TF_LONG[tf].toLowerCase()} candles from ${new Date(first.t).toLocaleDateString("en-GB")} to ${new Date(last.t).toLocaleDateString("en-GB")}. Last close ${fmt(last.c)}.`
    : `${symbol} price chart.`;
  const tfSelect = offered.length > 1;

  return (
    <div ref={rootRef} className={`pc${full ? " pc-full" : ""}`} data-testid="price-chart" style={{ ["--pc-h" as string]: `${height}px` }}>
      <div className="pc-bar" role="toolbar" aria-label="Chart tools">
        <select className="pc-sel" aria-label="Chart type" value={shownType} onChange={(ev) => setType(ev.target.value as ChartType)}>
          {CHART_TYPES.filter((c) => !props.closesOnly || ["line", "area", "baseline"].includes(c.type)).map((c) => <option key={c.type} value={c.type}>{c.name}</option>)}
        </select>
        {tfSelect && <>
          <div className="pc-seg pc-hide-phone" role="radiogroup" aria-label="Timeframe">
            {offered.map((t) => <button key={t} type="button" className="pc-btn" role="radio" aria-checked={t === tf} aria-pressed={t === tf} title={TF_LONG[t]} onClick={() => pickTf(t)}>{TF_LABEL[t]}</button>)}
          </div>
          <select className="pc-sel pc-only-phone" aria-label="Timeframe (phone)" value={tf} onChange={(ev) => pickTf(ev.target.value as Tf)}>
            {offered.map((t) => <option key={t} value={t}>{TF_LONG[t]}</option>)}
          </select>
        </>}
        <div className="pc-wrap">
          <button type="button" className="pc-btn" aria-haspopup="menu" aria-expanded={menu === "studies"} onClick={() => setMenu(menu === "studies" ? null : "studies")}>Indicators</button>
          {menu === "studies" && (
            <div className="pc-pop" role="menu" aria-label="Add an indicator">
              {STUDIES.map((d) => <button key={d.type} type="button" role="menuitem" className="item" onClick={() => addStudy(d.type)}>{d.name}<small>{d.about}</small></button>)}
            </div>
          )}
        </div>
        <div className="pc-seg pc-hide-phone" role="group" aria-label="Drawing tools">
          {DRAW_TOOLS.map((d) => <button key={d.kind} type="button" className="pc-btn icon" aria-label={d.name} title={d.name} aria-pressed={tool === d.kind} onClick={() => pickTool(d.kind)}>{ICON[d.kind]}</button>)}
        </div>
        <div className="pc-wrap pc-only-phone">
          <button type="button" className="pc-btn" aria-haspopup="menu" aria-expanded={menu === "draw"} aria-pressed={!!tool} onClick={() => setMenu(menu === "draw" ? null : "draw")}>{tool ? DRAW_TOOLS.find((d) => d.kind === tool)!.name : "Draw"}</button>
          {menu === "draw" && (
            <div className="pc-pop" role="menu" aria-label="Drawing tools">
              {DRAW_TOOLS.map((d) => <button key={d.kind} type="button" role="menuitem" className="item" onClick={() => pickTool(d.kind)}>{d.name}</button>)}
              {tool && <button type="button" role="menuitem" className="item" onClick={() => pickTool(null)}>Stop drawing</button>}
            </div>
          )}
        </div>
        <button type="button" className="pc-btn icon" disabled={!drawCount} aria-label={selected ? "Delete drawing" : "Clear drawings"}
          title={selected ? "Delete the selected drawing (Delete key)" : "Remove every drawing on this chart"}
          onClick={() => { const e = engineRef.current; if (!e) return; if (selected) e.deleteSelected(); else if (confirm("Remove every drawing on this chart?")) e.clearDrawings(); }}>{ICON.trash}</button>
        {compareLoad && (
          <div className="pc-wrap">
            {cmp ? <button type="button" className="pc-btn" aria-pressed="true" onClick={() => { setCmp(null); setMode("normal"); }} title="Stop comparing">vs {cmp.symbol} ✕</button>
              : <button type="button" className="pc-btn" aria-haspopup="dialog" aria-expanded={menu === "compare"} onClick={() => setMenu(menu === "compare" ? null : "compare")}>Compare</button>}
            {menu === "compare" && (
              <form className="pc-pop" onSubmit={(ev) => { ev.preventDefault(); doCompare(cmpText); }} aria-label="Compare with another symbol">
                <label>Symbol<input autoFocus value={cmpText} onChange={(ev) => setCmpText(ev.target.value)} placeholder={props.compareHint ?? "e.g. TCS"} maxLength={20} aria-label="Symbol to compare" /></label>
                <button type="submit" className="pc-btn" disabled={cmpBusy || !cmpText.trim()}>{cmpBusy ? "Loading…" : "Compare on a % scale"}</button>
              </form>
            )}
          </div>
        )}
        <span className="pc-gap" />
        <button type="button" className="pc-btn icon pc-hide-phone" aria-label="Zoom out" title="Zoom out" onClick={() => engineRef.current?.zoomBy(0.8)}>{ICON.zoomOut}</button>
        <button type="button" className="pc-btn icon pc-hide-phone" aria-label="Zoom in" title="Zoom in" onClick={() => engineRef.current?.zoomBy(1.25)}>{ICON.zoomIn}</button>
        <button type="button" className="pc-btn icon" aria-label="Reset the view" title="Reset the view (double-click the chart)" onClick={() => { engineRef.current?.resetView(); if (range) applyRange(range); }}>{ICON.reset}</button>
        <button type="button" className="pc-btn icon" aria-label="Download as PNG" title="Download as PNG" onClick={shot}>{ICON.camera}</button>
        <button type="button" className="pc-btn icon" aria-label={full ? "Exit full screen" : "Full screen"} title={full ? "Exit full screen" : "Full screen"} aria-pressed={full} onClick={toggleFull}>{full ? ICON.exit : ICON.full}</button>
      </div>

      <div ref={stageRef} className="pc-stage" tabIndex={0} role="group" aria-label={`${symbol} price chart. Arrow keys move it, plus and minus zoom, Delete removes the selected drawing.`}
        onKeyDown={(ev) => { if (engineRef.current?.key(ev.nativeEvent)) { ev.preventDefault(); syncData(); } }}>
        <div ref={canvasRef} className="pc-canvas" role="img" aria-label={summary} />
        <div className="pc-legend" aria-label="Legend">
          <div aria-hidden="true">
            <span className="title">{symbol}</span><span className="k">{TF_LONG[tf]}</span>
            {h && <>
              {shownType !== "line" && shownType !== "area" && shownType !== "baseline" && <>
                <span><span className="k">O</span>{fmt(h.bar.o)}</span><span><span className="k">H</span>{fmt(h.bar.h)}</span><span><span className="k">L</span>{fmt(h.bar.l)}</span>
              </>}
              <span><span className="k">C</span>{fmt(h.bar.c)}</span>
              {chg != null && <span>{chg >= 0 ? "▲" : "▼"} {e ? e.priceText(Math.abs(chg), h!.bar.c) : ""} ({signedPct(chgPct)})</span>}
            </>}
          </div>
          {h && volume && h.bar.v > 0 && <div><span><span className="k">Vol</span>{compact(h.bar.v)}</span></div>}
          {cmp && <div>{sw(th?.ink ?? "currentColor")}<span>{cmp.symbol}</span><span>{signedPct(cmpPct)}</span></div>}
          {e?.studies.map((s) => {
            const i = h?.index ?? -1;
            const own = STUDY[s.config.type].params.length > 0;
            return (
              <div key={s.config.id} className="study" data-study={s.config.type}>
                {sw(typeof s.lines[0].color === "number" ? slotColor(s.lines[0].color) : s.lines[0].color === "up" ? th?.up ?? "" : s.lines[0].color === "down" ? th?.down ?? "" : th?.muted ?? "",
                  !!s.lines[0].dash || (typeof s.lines[0].color === "number" && s.lines[0].color >= 3))}
                <span>{s.label}</span>
                {s.lines.map((l) => <span key={l.name} className="num">{s.lines.length > 1 && <span className="k">{l.name}</span>}{i >= 0 ? fmt(l.values[i]) : "–"}</span>)}
                {s.stage && i >= 0 && Number.isFinite(s.stage[i]) && <span>{STAGE_NAMES[s.stage[i]]}</span>}
                {s.hist && i >= 0 && <span><span className="k">Gap</span>{fmt(s.hist[i])}</span>}
                {own && <button type="button" aria-label={`Settings for ${s.label}`} title="Settings" onClick={() => setEdit(edit === s.config.id ? null : s.config.id)}>⚙</button>}
                <button type="button" aria-label={`Remove ${s.label}`} title="Remove" onClick={() => removeStudy(s.config.id)}>✕</button>
              </div>
            );
          })}
        </div>
        {edit && (() => {
          const s = studies.find((x) => x.id === edit);
          if (!s) return null;
          return (
            <div className="pc-pop" style={{ top: 40, left: 8 }} role="dialog" aria-label={`${studyLabel(s)} settings`}>
              <b style={{ padding: "4px 6px" }}>{STUDY[s.type].name}</b>
              {STUDY[s.type].params.map((p, i) => (
                <label key={p.label}>{p.label}
                  <input type="number" inputMode="decimal" min={p.min} max={p.max} step={p.step} defaultValue={s.params[i]}
                    onChange={(ev) => { const v = Number(ev.target.value); if (Number.isFinite(v) && ev.target.value !== "") setParam(s.id, i, v); }} />
                </label>
              ))}
              {!STUDY[s.type].params.length && <span className="pc-note" style={{ padding: "4px 6px" }}>No settings.</span>}
              <button type="button" className="pc-btn" onClick={() => setEdit(null)}>Done</button>
            </div>
          );
        })()}
        {status === "loading" && <div className="pc-status">Loading prices…</div>}
        {status === "empty" && <div className="pc-status">No candles for this timeframe yet.</div>}
        {status === "error" && <div className="pc-status">Couldn't load prices: {error}</div>}
        {fetchingMore && <div className="pc-loading-more">Loading older candles…</div>}
      </div>

      <div className="pc-foot">
        {load ? (
          <div className="pc-seg" role="radiogroup" aria-label="Range">
            {RANGES.filter((r) => offered.includes(r.tf) || offered.includes("1d")).map((r) => (
              <button key={r.key} type="button" className="pc-btn" role="radio" aria-checked={range === r.key} aria-pressed={range === r.key} onClick={() => pickRange(r.key)}>{r.key}</button>
            ))}
          </div>
        ) : <span className="pc-note">{TF_LONG[tf]} candles</span>}
        <div className="pc-seg" role="group" aria-label="Scale">
          <button type="button" className="pc-btn" aria-pressed={volume} onClick={() => setVolume(!volume)} title="Volume bars">Vol</button>
          <button type="button" className="pc-btn" aria-pressed={mode === "percent"} onClick={() => setMode(mode === "percent" ? "normal" : "percent")} title="Percent scale, from the first candle on screen">%</button>
          <button type="button" className="pc-btn" aria-pressed={mode === "log"} onClick={() => setMode(mode === "log" ? "normal" : "log")} title="Log scale">Log</button>
          <button type="button" className="pc-btn" aria-pressed={auto} onClick={() => { engineRef.current?.setAuto(!auto); setAuto(!auto); }} title="Fit prices to the candles on screen">Auto</button>
          <button type="button" className="pc-btn" aria-pressed={table} onClick={() => { setTable(!table); setTick((x) => x + 1); }} title="The candles as a table">Table</button>
        </div>
      </div>
      {error && status === "ready" && <p className="pc-note" role="status">{error}</p>}
      {props.note && <p className="pc-note">{props.note}</p>}
      {tool && <p className="pc-note" role="status">{DRAW_TOOLS.find((d) => d.kind === tool)!.points === 2 ? "Click or drag on the chart to place both ends. Esc stops." : "Click on the chart to place it. Esc stops."}</p>}
      {table && (
        <div className="pc-table">
          <table>
            <caption className="sr-only">{symbol} {TF_LONG[tf].toLowerCase()} candles, newest first</caption>
            <thead><tr><th scope="col">{intraday ? "Time" : "Date"}</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th></tr></thead>
            <tbody>{lastBars.map((b) => (
              <tr key={b.t}><td>{wallText(b.w, intraday)}</td><td>{fmt(b.o)}</td><td>{fmt(b.h)}</td><td>{fmt(b.l)}</td><td>{fmt(b.c)}</td><td>{b.v ? compact(b.v) : "–"}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

let themeCache: { el: HTMLElement | null; at: number; th: Theme } | null = null;
/** The theme for legend swatches, read at most every half second. */
function readThemeCached(el: HTMLElement | null): Theme | null {
  if (!el) return null;
  const now = performance.now();
  if (!themeCache || themeCache.el !== el || now - themeCache.at > 500) themeCache = { el, at: now, th: readTheme(el) };
  return themeCache.th;
}

/** +1.23%, −0.40%, or 0.00% when it rounds to nothing. */
function signedPct(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const t = Math.abs(v).toFixed(2);
  return t === "0.00" ? "0.00%" : `${v > 0 ? "+" : "−"}${t}%`;
}

function compact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v));
}

function wallText(w: number, intraday: boolean): string {
  const d = new Date(w);
  const date = `${String(d.getUTCDate()).padStart(2, "0")} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  return intraday ? `${date} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}` : date;
}
