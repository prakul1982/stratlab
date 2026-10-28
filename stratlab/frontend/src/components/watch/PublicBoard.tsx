/* The visitor's Market Watch (MW-1): one fixed board of indices, bitcoin, forex and commodities with price, the day's change and a
 * line of recent closes, read every ten seconds while it is open and showing. Nothing to save, nothing to search: signing in
 * brings your own lists, every market and the chart. This file may not import the account code (unit/seo.test.mjs). */
import { useEffect, useRef, useState } from "react";
import { publicGet } from "../../lib/http";
import { Spark } from "../kit/Spark";
import { Close } from "../Icons";
import { changeText, labelOf, MARKET_NAME, priceText, type WatchItem } from "../../lib/watch";
import { signCls } from "../../lib/format";
import { useDialogFocus } from "../kit/Dialog";
import { isSheet, type PanelLayout } from "../../lib/watchLayout";
import "./watch.css";

interface Row { id: string; name: string; market: string; price?: number | null; change_pct?: number | null; currency?: string | null; stale?: boolean; spark?: number[] }
const EVERY = 10_000;

const asItem = (r: Row): WatchItem => {
  const [market, ...rest] = r.id.split(":");
  const symbol = rest.join(":");
  return { id: r.id, market, symbol, name: r.name, kind: symbol.startsWith("^") ? "index" : market === "CRYPTO" ? "crypto" : market === "FX" ? "fx" : "commodity" };
};

export default function PublicBoard({ layout, vw, onClose }: { layout: PanelLayout; patch: (p: Partial<PanelLayout>) => void; vw: number; vh: number; onClose: () => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [failed, setFailed] = useState(false);
  const box = useRef<HTMLElement>(null);
  const sheet = isSheet(vw);
  useDialogFocus(box, sheet, { onEscape: onClose, initial: () => box.current?.querySelector<HTMLElement>(".mw-close") });
  useEffect(() => {
    let alive = true, timer = 0;
    const read = async () => {
      if (document.visibilityState !== "hidden") {
        try { const r = await publicGet<{ rows: Row[] }>("/public/markets/watch"); if (alive) { setRows(r.rows); setFailed(false); } } catch { if (alive) setFailed(true); }
      }
      if (alive) timer = window.setTimeout(read, EVERY);
    };
    void read();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);
  const style = { ["--mw-w" as string]: `${layout.w}px`, ["--mw-h" as string]: `${layout.h}px`, ["--mw-x" as string]: "auto", ["--mw-y" as string]: "auto" };
  return (
    <aside ref={box} className={`mw mw-${sheet ? "sheet" : "dock"} mw-public`} style={style} aria-label="Market Watch" data-testid="market-watch"
      {...(sheet ? { role: "dialog", "aria-modal": true } : { role: "complementary" })}>
      <header className="mw-head">
        <h2 className="mw-title">Markets</h2>
        <span className="mw-head-btns"><button type="button" className="mw-ic mw-close" aria-label="Close Market Watch" onClick={onClose}><Close size={18} /></button></span>
      </header>
      <div className="mw-scroll">
        {failed && !rows && <p className="mw-limit" role="status">The prices couldn't be read just now. Trying again in a few seconds.</p>}
        {!rows && !failed && <p className="k-small k-muted mw-pad" role="status">Loading the markets…</p>}
        {rows && (
          <ul className="mw-rows" aria-label="Main markets">
            {rows.map((r) => {
              const it = asItem(r), cur = it.kind === "index" || it.market === "FX" || it.market === "CRYPTO" ? "" : r.currency === "USD" ? "$" : r.currency === "INR" ? "₹" : "";
              const t = changeText(r.change_pct);
              return (
                <li key={r.id} className="mw-row static">
                  <span className="mw-grip off" aria-hidden="true" />
                  <div className="mw-open static">
                    <span className="mw-name"><b>{labelOf(it)}</b><small>{MARKET_NAME[it.market] ?? it.market}</small></span>
                    <span className="mw-spark" aria-hidden="true">{r.spark && r.spark.length > 1 ? <Spark values={r.spark} tone="neutral" label={`${labelOf(it)}, recent closes`} height={24} /> : null}</span>
                    <span className="mw-px">
                      <b className="mw-price">{r.price == null ? "–" : <>{cur}{priceText(r.price, r.currency ?? null, it.market, it.symbol)}</>}</b>
                      <span className={`mw-chg ${signCls(r.change_pct, t)}`}>{r.change_pct != null && r.change_pct > 0 ? "▲ " : r.change_pct != null && r.change_pct < 0 ? "▼ " : ""}{t}</span>
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <footer className="mw-foot mw-signin">
        <span>Prices can be delayed. Sign in to keep your own lists, add any market and chart them with drawings and indicators.</span>
        <a className="btn sm" href="/login">Sign in</a>
      </footer>
    </aside>
  );
}
