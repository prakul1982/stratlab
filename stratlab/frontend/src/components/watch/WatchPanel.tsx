/* Market Watch (MW-1): the panel that floats over every page. Several named lists of instruments from every market (the first is
 * the Research watchlist), with the last price and the day's change; a tap opens the chart without leaving the page. Docked to the
 * right edge, floating, or a full-height sheet on a phone. Prices are read every 5 seconds for the rows in view only, and tick by
 * tick where the broker's feed carries them. Facts only: names, prices, counts.
 * MW-2 (owner, 9 Nov: "only extendable from one top corner ... very cluttered, we need to redesign it"): a floating panel is sized
 * from every edge and corner and dragged by its header; one search field adds a symbol; a row is one line under column heads
 * (Symbol, Last, Change, Change %) that also sort the list; the tabs say their lists' names in words. */
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { Link } from "react-router-dom";
import { ChartWorkspace } from "./ChartWorkspace";
import { AddField, AddResults, AddSaid, useAddSearch } from "./AddSymbol";
import { WatchRow } from "./WatchRow";
import { useWatch } from "./useWatch";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { useDialogFocus, usePopover } from "../kit/Dialog";
import { EmptyState, ErrorState, Skeleton } from "../kit/States";
import { Chevron, Close, Download, Plus } from "../Icons";
import { downloadCsv } from "../../lib/csvDownload";
import { csvName } from "../../lib/csv";
import { istToday } from "../../lib/format";
import { useApp } from "../../lib/app";
import { lastTradingDay, marketState } from "../../lib/marketHours";
import { signCls, currencySymbol } from "../../lib/format";
import { getSparks, live } from "../../lib/watchApi";
import type { LiveSub } from "../../lib/watchLive";
import {
  addOutcome, asOfLine, changeAbsOf, changeArrow, changeOf, changeText, countSaid, currencyOf, DEFAULT_ID, itemFromPath, labelOf, listName, listsSaid, moveItem, newestDay,
  nextSort, POPULAR, priceText, SORTS, sortItems, subtitleOf, symbolsSaid, tabTitle, type SortMode, type WatchItem, type WatchQuote,
} from "../../lib/watch";
import { dragged, DOCK_FROM, drawnHeight, EDGES, isSheet, MAX_W, MIN_H, MIN_W, resized, shapeOf, type Edge, type PanelLayout } from "../../lib/watchLayout";
import "./watch.css";

export default function WatchPanel({ layout, patch, vw, vh, onClose }: { layout: PanelLayout; patch: (p: Partial<PanelLayout>) => void; vw: number; vh: number; onClose: () => void }) {
  const { markets, me, notify } = useApp();
  const w = useWatch();
  const sheet = isSheet(vw);
  const shape = shapeOf(layout, vw);
  // the layout as drawn: a "docked" panel on a window too narrow to dock in floats in the corner (watchLayout.DOCK_FROM)
  const drawn: PanelLayout = shape === "dock" ? layout : { ...layout, mode: "float", h: drawnHeight(layout, vw, vh) };
  const box = useRef<HTMLDivElement>(null);
  const plan = me?.plan_info.name ?? "Free";
  const listId = w.lists?.some((l) => l.id === layout.list) ? layout.list! : DEFAULT_ID;
  const list = w.lists?.find((l) => l.id === listId) ?? null;
  const sort: SortMode = layout.sort;

  useDialogFocus(box, sheet, { onEscape: onClose, initial: () => box.current?.querySelector<HTMLElement>(".mw-tab[aria-selected=true], .mw-close") });
  // Esc inside a docked or floating panel closes it too, unless something inside (a menu, the search) took the key
  useEffect(() => {
    if (sheet) return;
    const el = box.current;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented && el?.contains(document.activeElement) && !(document.activeElement as HTMLElement)?.closest?.(".pc")) onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [sheet, onClose]);

  // ---------- prices: the rows in view, and the chart open ----------
  const [visible, setVisible] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Record<string, WatchQuote | null>>({});
  const [ticks, setTicks] = useState<Record<string, number>>({});
  const [sparks, setSparks] = useState<Record<string, number[]>>({});
  const [tickAt, setTickAt] = useState<number | null>(null);          // when the last live tick came in: the foot's "as of" (LIVE4-009)
  const pending = useRef<Record<string, number>>({});
  const timer = useRef<number>(0);
  const sub = useRef<LiveSub | null>(null);
  const chartKey = layout.chart;
  useEffect(() => {
    const s = live().subscribe({
      quote: (k, q) => setQuotes((o) => (o[k] === q ? o : { ...o, [k]: q })),
      tick: (k, t) => {                                                // ticks are folded into one update a quarter second
        pending.current[k] = t.p;
        if (!timer.current) timer.current = window.setTimeout(() => { timer.current = 0; const got = pending.current; pending.current = {}; setTicks((o) => ({ ...o, ...got })); setTickAt(Date.now()); }, 250);
      },
    });
    sub.current = s;
    return () => { s.close(); sub.current = null; window.clearTimeout(timer.current); timer.current = 0; };
  }, []);
  const wanted = useMemo(() => [...new Set([...visible, ...(chartKey ? [chartKey] : [])])].join(","), [visible, chartKey]);
  useEffect(() => { sub.current?.set(wanted ? wanted.split(",") : []); }, [wanted]);
  useEffect(() => {
    const need = visible.filter((k) => !sparks[k]);
    if (!need.length) return;
    let on = true;
    getSparks(need.slice(0, 24)).then((got) => { if (on) setSparks((o) => ({ ...o, ...got })); }).catch(() => undefined);
    return () => { on = false; };
  }, [visible]);       // eslint-disable-line react-hooks/exhaustive-deps

  // which rows are on screen: only those are read
  const scroller = useRef<HTMLDivElement>(null);
  const seen = useRef(new Set<string>());
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const io = useRef<IntersectionObserver | null>(null);
  const listKey = list?.items.map((i) => i.id).join(",") ?? "";
  useEffect(() => {
    seen.current = new Set();
    if (chartKey) { setVisible([]); return; }                          // a chart open: only its own price is read
    if (!scroller.current || typeof IntersectionObserver === "undefined") { setVisible(list?.items.slice(0, 24).map((i) => i.id) ?? []); return; }
    io.current = new IntersectionObserver((entries) => {
      for (const e of entries) {
        const k = (e.target as HTMLElement).dataset.key!;
        if (e.isIntersecting) seen.current.add(k); else seen.current.delete(k);
      }
      setVisible([...seen.current].slice(0, 24));
    }, { root: scroller.current, rootMargin: "60px 0px" });
    rowRefs.current.forEach((el) => io.current!.observe(el));
    return () => { io.current?.disconnect(); io.current = null; };
  }, [listKey, listId, chartKey]);        // eslint-disable-line react-hooks/exhaustive-deps
  const setRow = (id: string) => (el: HTMLLIElement | null) => {
    if (el) { rowRefs.current.set(id, el); io.current?.observe(el); }
    else { const old = rowRefs.current.get(id); if (old) io.current?.unobserve(old); rowRefs.current.delete(id); seen.current.delete(id); }
  };

  const priceOf = (it: WatchItem) => ticks[it.id] ?? quotes[it.id]?.price ?? null;
  const changeFor = (it: WatchItem) => changeOf(quotes[it.id] ?? undefined, ticks[it.id]);
  const open = useMemo(() => Object.fromEntries(markets.map((m) => [m.id, marketState(m).open])), [markets]);
  const allShut = !!list?.items.length && list.items.every((it) => open[it.market] === false);
  // a list of only US stocks says its day in New York's time (the US close is past midnight in India)
  const tzOf = list?.items.length && list.items.every((it) => it.market === "US") ? "America/New_York" : "Asia/Kolkata";
  // shut: the day said is the last day the list's markets traded (the newest of them), from each exchange's own days, never the
  // day the prices were read (owner, 9 Nov: "last close Sun")
  const lastDay = allShut ? newestDay([...new Set(list!.items.map((it) => it.market))].map((id) => { const m = markets.find((x) => x.id === id); return m ? lastTradingDay(m) : null; })) : null;
  const asOf = asOfLine([...Object.values(quotes).map((q) => q?.at), allShut ? null : tickAt], allShut ? tzOf : undefined, allShut, lastDay);
  // "Closed" is said on a row only while another market on the list is trading: with all of them shut the foot says it once
  const noteOf = (it: WatchItem): "Delayed" | "Closed" | null => (quotes[it.id]?.delayed ? "Delayed" : open[it.market] === false && !allShut ? "Closed" : null);
  const notes = new Set(list?.items.map(noteOf));
  const changeAbsFor = (it: WatchItem) => changeAbsOf(quotes[it.id] ?? undefined, ticks[it.id]);

  // ---------- the rows in order, and dragging them ----------
  const [drag, setDrag] = useState<{ id: string; order: string[] } | null>(null);
  const sorted = useMemo(() => (list ? sortItems(list.items, sort, changeFor) : []), [list, sort, quotes, ticks]);   // eslint-disable-line react-hooks/exhaustive-deps
  const shown = drag ? drag.order.map((i) => sorted.find((x) => x.id === i)!).filter(Boolean) : sorted;
  const canMove = sort === "custom";
  const startDrag = (id: string) => (e: RPointerEvent<HTMLButtonElement>) => {
    if (!list || !canMove) return;
    e.preventDefault();
    const ids = sorted.map((x) => x.id);
    const scroll = scroller.current?.scrollTop ?? 0;
    // the rows' middles as they stand now, without the one dragged: where it lands is counted against these, so it can't flicker
    const mids = ids.filter((k) => k !== id).map((k) => { const r = rowRefs.current.get(k)!.getBoundingClientRect(); return r.top + scroll + r.height / 2; });
    let last = ids;
    setDrag({ id, order: ids });
    const move = (ev: PointerEvent) => {
      const y = ev.clientY + (scroller.current?.scrollTop ?? 0);
      const to = mids.filter((m) => m < y).length;
      const rest = ids.filter((k) => k !== id);
      last = [...rest.slice(0, to), id, ...rest.slice(to)];
      setDrag((d) => (d && d.order.join() === last.join() ? d : { id, order: last }));
    };
    const end = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end);
      setDrag(null);
      if (last.join() !== ids.join()) void w.set(listId, last.map((k) => list.items.find((x) => x.id === k)!));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };
  const nudge = (it: WatchItem, by: -1 | 1) => {
    if (!list || !canMove) return;
    const i = list.items.findIndex((x) => x.id === it.id), j = i + by;
    if (j < 0 || j >= list.items.length) return;
    void w.set(listId, moveItem(list.items, i, j));
    window.setTimeout(() => rowRefs.current.get(it.id)?.querySelector<HTMLElement>(".mw-grip")?.focus(), 0);
  };

  // ---------- adding, lists ----------
  const capSymbols = w.limits?.symbols ?? null;
  const full = capSymbols != null && !!list && list.items.length >= capSymbols;
  const onList = list?.items.map((x) => x.id).join(",") ?? "";
  const has = useCallback((id: string) => onList.split(",").includes(id), [onList]);
  /** Add to the open list, and what came of it in a sentence (added, there already, or the list is full). */
  const add = (it: WatchItem): { ok: boolean; text: string } => {
    if (!list) return { ok: false, text: "Your lists are still loading." };
    const out = addOutcome(list, it, capSymbols, symbolsSaid(w.limits, list.items.length, plan));
    if (out.ok) { void w.add(listId, it); setFresh(it.id); }
    return out;
  };
  // the row just added is brought into view and marked for a moment: the list itself shows what was added
  const [fresh, setFresh] = useState<string | null>(null);
  useEffect(() => {
    if (!fresh) return;
    const show = window.setTimeout(() => rowRefs.current.get(fresh)?.scrollIntoView({ block: "nearest" }), 60);
    const done = window.setTimeout(() => setFresh(null), 2400);
    return () => { window.clearTimeout(show); window.clearTimeout(done); };
  }, [fresh]);
  const search = useAddSearch(has, add, listId);
  const [naming, setNaming] = useState<null | "new" | "rename">(null);
  const [name, setName] = useState("");
  const [askDelete, setAskDelete] = useState(false);
  const submitName = async () => {
    const n = name.trim();
    if (!n) { setNaming(null); return; }
    if (naming === "new") { const id = await w.create(n); if (id) patch({ list: id }); }
    else if (naming === "rename") await w.rename(listId, n);
    setNaming(null); setName("");
  };
  // the tabs are one stop in the tab order (the open list's); the arrow keys, Home and End move along them (MWR1-008)
  const tabKey = (e: React.KeyboardEvent) => {
    const ids = w.lists?.map((l) => l.id) ?? [];
    const i = ids.indexOf(listId);
    const to = e.key === "ArrowRight" ? ids[(i + 1) % ids.length] : e.key === "ArrowLeft" ? ids[(i - 1 + ids.length) % ids.length] : e.key === "Home" ? ids[0] : e.key === "End" ? ids[ids.length - 1] : null;
    if (!to || to === listId) return;
    e.preventDefault();
    patch({ list: to });
    window.setTimeout(() => document.getElementById(`mw-tab-${to}`)?.focus(), 0);
  };
  const tabsFull = w.lists && w.limits?.lists != null && w.lists.length >= w.limits.lists;
  const menuTrigger = useRef<HTMLButtonElement>(null), menuBox = useRef<HTMLDivElement>(null);
  const [listMenu, setListMenu] = useState(false);
  usePopover(listMenu, setListMenu, menuTrigger, menuBox);

  // ---------- the chart open in the panel ----------
  const chartItem = useMemo(() => {
    if (!chartKey) return null;
    const found = w.lists?.flatMap((l) => l.items).find((i) => i.id === chartKey) ?? POPULAR.find((i) => i.id === chartKey);
    if (found) return found;
    const [m, ...s] = chartKey.split(":");
    return itemFromPath(m, s.join(":"));
  }, [chartKey, w.lists]);

  // ---------- the panel's place: a floating one is dragged by its header and sized from any edge or corner, a docked one from its
  // left edge; the pointer is a mouse, a pen or a finger alike, and the size and place are kept on this device for this person ----------
  const grab = (kind: "move" | "size", edge: Edge = "w") => (e: RPointerEvent<HTMLElement>) => {
    if (sheet || e.button > 0 || (kind === "move" && (shape !== "float" || (e.target as HTMLElement).closest("button, a, input")))) return;
    e.preventDefault();
    const el = e.currentTarget, id = e.pointerId, x0 = e.clientX, y0 = e.clientY, from = drawn;
    try { el.setPointerCapture(id); } catch { /* the pointer is already gone */ }
    document.body.classList.add("mw-moving");
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      const l = kind === "move" ? dragged(from, ev.clientX - x0, ev.clientY - y0, vw, vh) : resized(from, ev.clientX - x0, ev.clientY - y0, vw, vh, edge);
      // a panel sized or moved while it floats is the person's own floating panel from then on: its height is theirs, not half the window
      patch(shape === "dock" ? { w: l.w } : { w: l.w, h: l.h, x: l.x, y: l.y, mode: "float" });
    };
    const end = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end);
      document.body.classList.remove("mw-moving");
      try { el.releasePointerCapture(id); } catch { /* released with the pointer */ }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };
  // from the keyboard: left and right change the width, and on a floating panel up and down change the height
  const sizeKey = (e: React.KeyboardEvent) => {
    const dx = e.key === "ArrowLeft" ? 24 : e.key === "ArrowRight" ? -24 : 0;
    const dy = shape !== "float" ? 0 : e.key === "ArrowUp" ? -24 : e.key === "ArrowDown" ? 24 : 0;
    if (!dx && !dy) return;
    e.preventDefault();
    const r = resized(drawn, dx, dy, vw, vh, "nw");
    patch(shape === "dock" ? { w: r.w } : { w: r.w, h: r.h, x: r.x, y: r.y, mode: "float" });
  };

  const chartH = Math.max(260, Math.min(640, (shape === "float" ? drawn.h : vh) - 300));          // the header, the chart's toolbar and its range row take about 300px
  const style = { ["--mw-w" as string]: `${layout.w}px`, ["--mw-h" as string]: `${Math.max(MIN_H, drawn.h)}px`, ["--mw-x" as string]: layout.x == null ? "auto" : `${layout.x}px`, ["--mw-y" as string]: layout.y == null ? "auto" : `${layout.y}px` };
  const used = list?.items.length ?? 0;
  const said = list ? symbolsSaid(w.limits, used, plan) : null;
  const named = list ? (list.default ? list.name : listName(list.name)) : "";
  const listsLine = listsSaid(w.limits, w.lists?.length ?? 0, plan);

  return (
    // a sheet is a dialog, which an aside element may not be; and the panel's top and bottom bars are not the page's banner and footer (MWR1-016)
    <div ref={box} className={`mw mw-${shape}`} style={style} data-testid="market-watch" aria-label="Market Watch"
      {...(sheet ? { role: "dialog", "aria-modal": true } : { role: "complementary" })}>
      {/* the grips: the left edge is the one a keyboard reaches (a separator with its value); a floating panel has the other seven too */}
      {!sheet && <div className="mw-size w" role="separator" aria-orientation="vertical" aria-valuemin={MIN_W} aria-valuemax={MAX_W} aria-valuenow={layout.w} aria-valuetext={`${layout.w} pixels wide`}
        aria-label={shape === "float" ? "Resize the panel. Left and right arrow keys change its width, up and down its height." : "Resize the panel. Use the left and right arrow keys."}
        tabIndex={0} onPointerDown={grab("size", "w")} onKeyDown={sizeKey} />}
      {shape === "float" && EDGES.filter((edge) => edge !== "w").map((edge) => <div key={edge} className={`mw-size ${edge}`} data-edge={edge} aria-hidden="true" onPointerDown={grab("size", edge)} />)}
      <div className="mw-head" onPointerDown={grab("move")}>
        {chartItem
          ? <button type="button" className="mw-back" onClick={() => patch({ chart: null })} aria-label="Back to the list"><span className="mw-back-ic" aria-hidden="true"><Chevron size={16} /></span>Lists</button>
          : <h2 className="mw-title">Markets</h2>}
        <span className="mw-head-btns">
          {chartItem && <Link className="mw-ic" to={`/chart/${chartItem.market}/${encodeURIComponent(chartItem.symbol)}`} aria-label="Open as a full page" title="Open as a full page" onClick={() => { if (sheet) onClose(); }}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-8 8M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
          </Link>}
          {!sheet && vw >= DOCK_FROM && <button type="button" className="mw-ic" aria-label={shape === "dock" ? "Float the panel over the page" : "Dock the panel to the right"} title={shape === "dock" ? "Float over the page" : "Dock to the right"}
            onClick={() => patch(shape === "dock" ? { mode: "float", x: Math.max(0, vw - layout.w - 24), y: Math.max(0, vh - layout.h - 24) } : { mode: "dock", x: null, y: null })}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d={shape === "dock" ? "M8 4.5v15" : "M14 4.5v15"} /></svg>
          </button>}
          <button type="button" className="mw-ic mw-close" aria-label="Close Market Watch" onClick={onClose}><Close size={18} /></button>
        </span>
      </div>

      {chartItem ? (
        <div className="mw-chartview">
          <div className="mw-chead">
            <div className="mw-ctitle"><b>{labelOf(chartItem)}</b><small>{subtitleOf(chartItem)}</small></div>
            <div className="mw-cprice">
              <b>{(() => { const p = priceOf(chartItem); return p == null ? "–" : `${chartItem.kind === "index" || chartItem.market === "FX" || chartItem.market === "CRYPTO" ? "" : currencySymbol(quotes[chartItem.id]?.currency ?? currencyOf(chartItem))}${priceText(p, quotes[chartItem.id]?.currency ?? null, chartItem.market, chartItem.symbol)}`; })()}</b>
              {(() => { const c = changeFor(chartItem); const t = changeText(c); return <span className={signCls(c, t)}>{changeArrow(c)}{t}</span>; })()}
            </div>
          </div>
          <div className="mw-chartbox"><ChartWorkspace item={chartItem} height={chartH} /></div>
        </div>
      ) : (
        <>
          <div className="mw-tabs">
            <div className="mw-tablist" role="tablist" aria-label="Your lists" onKeyDown={tabKey}>
              {w.lists?.map((l) => (
                <button key={l.id} type="button" role="tab" id={`mw-tab-${l.id}`} className="mw-tab" aria-selected={l.id === listId} tabIndex={l.id === listId ? 0 : -1}
                  onClick={() => patch({ list: l.id })} title={tabTitle(l)}>{l.default ? l.name : listName(l.name)}</button>
              ))}
            </div>
            {naming ? null : tabsFull
              ? <span className="mw-tab-full">{listsLine}</span>
              : <button type="button" className="mw-tab add" onClick={() => { setName(""); setNaming("new"); }} aria-label="New list" title="New list"><Plus size={14} /></button>}
          </div>
          {naming && (
            <form className="mw-name-form" onSubmit={(e) => { e.preventDefault(); void submitName(); }}>
              <input className="k-input sm" aria-label={naming === "new" ? "Name of the new list" : "New name of this list"} value={name} maxLength={40} autoFocus placeholder="List name"
                onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setNaming(null); } }} />
              <button type="submit" className="btn sm">{naming === "new" ? "Create" : "Save"}</button>
              <button type="button" className="btn quiet sm" onClick={() => setNaming(null)}>Cancel</button>
            </form>
          )}
          <div className="mw-bar">
            <AddField s={search} disabled={!list} />
            {/* EXPORT: the list as a CSV, in its order, with the prices it shows now */}
            {list && list.items.length > 0 && (
              <button type="button" className="mw-ic" data-csv={`watchlist ${list.name}`} aria-label={`Download CSV: the list ${named}`} title="Download this list as a CSV file"
                onClick={() => downloadCsv(csvName(`watchlist ${list.name}`, istToday()), ["Symbol", "Name", "Market", "Kind", "Currency", "Price", "Change today", "Change today (%)"],
                  shown.map((it) => { const c = changeFor(it), a = changeAbsFor(it); return [it.symbol, it.name || null, it.market, it.kind, currencyOf(it), priceOf(it), a == null ? null : Math.round(a * 10000) / 10000, c == null ? null : Math.round(c * 100) / 100]; }))}>
                <Download size={16} />
              </button>
            )}
            {list && !list.default && (
              <span className="mw-listmenu">
                <button ref={menuTrigger} type="button" className="mw-ic" aria-label={`Actions for the list ${named}`} aria-haspopup="menu" aria-expanded={listMenu} onClick={() => setListMenu(!listMenu)}><span aria-hidden="true">⋯</span></button>
                {listMenu && (
                  <div ref={menuBox} className="mw-menu right" role="menu" aria-label="This list">
                    <button type="button" role="menuitem" onClick={() => { setListMenu(false); setName(list.name); setNaming("rename"); }}>Rename the list</button>
                    <button type="button" role="menuitem" className="danger" onClick={() => { setListMenu(false); setAskDelete(true); }}>Delete the list</button>
                  </div>
                )}
              </span>
            )}
          </div>
          {full && list && <p className="mw-limit" role="status">{said} <Link to="/plans">See plans</Link></p>}

          <div className="mw-scroll" ref={scroller} role="tabpanel" aria-labelledby={`mw-tab-${listId}`}>
            {w.failed && <ErrorState title="Your lists couldn't be read" action={{ label: "Try again", onClick: () => void w.reload() }}>Check your connection. Nothing was lost.</ErrorState>}
            {!w.lists && !w.failed && <div className="mw-skel"><Skeleton label="Loading your lists" lines={5} /></div>}
            <AddSaid s={search} />
            {search.active && <AddResults s={search} />}
            {!search.active && list && list.items.length === 0 && (
              <EmptyState title={list.default ? "Your watchlist is empty" : `${named} is empty`} action={{ label: "Add a symbol", onClick: search.focus }}>
                Search above for anything the app covers: stocks, indices, crypto, currencies, commodities. {list.default ? "Stocks you star on a company page are here too." : ""}
              </EmptyState>
            )}
            {!search.active && list && list.items.length === 0 && (
              <div className="mw-pop mw-quick" role="group" aria-label="Quick add">
                <span className="k-small k-muted">Quick add</span>
                {POPULAR.slice(0, 8).map((p) => <button key={p.id} type="button" className="btn quiet sm" onClick={() => notify(add(p).text)}>{labelOf(p)}</button>)}
              </div>
            )}
            {!search.active && list && list.items.length > 0 && (
              <div className={`mw-table${canMove ? "" : " fixed"}`}>
                {/* the column heads: Symbol and Change % sort the list too (a press again turns it round, a third gives your own order back) */}
                <div className="mw-cols" role="group" aria-label={`Columns. The list is in this order: ${SORTS.find((x) => x.value === sort)!.label}`}>
                  <span aria-hidden="true" />
                  <button type="button" className="mw-col" aria-pressed={sort === "name"} aria-label="Sort by name" title={sort === "name" ? "In order of name. Press for your own order." : "Sort by name"}
                    onClick={() => patch({ sort: nextSort(sort, "name") })}>Symbol{sort === "name" && <i aria-hidden="true">▲</i>}</button>
                  <span className="mw-c-spark" aria-hidden="true" />
                  <span className="mw-col num">Last</span>
                  <span className="mw-col num mw-c-abs">Change</span>
                  <button type="button" className="mw-col num" aria-pressed={sort === "change_desc" || sort === "change_asc"} aria-label="Sort by the day's change"
                    title={sort === "change_desc" ? "Biggest rise first. Press for the biggest fall first." : sort === "change_asc" ? "Biggest fall first. Press for your own order." : "Sort by the day's change"}
                    onClick={() => patch({ sort: nextSort(sort, "change") })}>Change %{sort === "change_desc" ? <i aria-hidden="true">▼</i> : sort === "change_asc" ? <i aria-hidden="true">▲</i> : null}</button>
                  <span aria-hidden="true" />
                </div>
                <ul className="mw-rows" aria-label={named}>
                  {shown.map((it) => (
                    <WatchRow key={it.id} ref={setRow(it.id)} item={it} quote={quotes[it.id]} price={priceOf(it)} change={changeFor(it)} changeAbs={changeAbsFor(it)} spark={sparks[it.id]} note={noteOf(it)}
                      canMove={canMove} dragging={drag?.id === it.id} fresh={fresh === it.id} lists={w.lists ?? []} listId={listId}
                      onOpen={() => { patch({ chart: it.id }); }} onRemove={() => void w.remove(listId, it.id)} onMoveTo={(to) => void w.moveTo(listId, to, it)}
                      onGrip={startDrag(it.id)} onNudge={(by) => nudge(it, by)} />
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div className="mw-foot">
            {list && w.limits?.symbols != null && !full && said ? <span role="status">{said} <Link to="/plans">See plans</Link></span>
              : <span className="mw-foot-note">{list ? countSaid(used) : ""}
                {list && asOf && <span data-testid="mw-as-of"> · {asOf}</span>}</span>}
            {/* a narrow panel marks a delayed or shut row with a dot beside its symbol: what the dots are */}
            {!search.active && (notes.has("Delayed") || notes.has("Closed")) && (
              <span className="mw-legend">
                {notes.has("Delayed") && <span><i className="mw-dot delayed" aria-hidden="true" />Delayed, up to 15 minutes</span>}
                {notes.has("Closed") && <span><i className="mw-dot" aria-hidden="true" />Market closed</span>}
              </span>
            )}
          </div>
        </>
      )}
      {askDelete && list && (
        <ConfirmDialog title={`Delete the list ${named}?`} confirmLabel="Delete the list" onClose={() => setAskDelete(false)}
          onConfirm={() => { setAskDelete(false); patch({ list: null }); void w.delete(list.id); }}>
          The list and its {countSaid(list.items.length)} are removed. Your charts and drawings are not.
        </ConfirmDialog>
      )}
    </div>
  );
}

