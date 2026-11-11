/* One instrument on a list (MW-1; one compact line since MW-2, owner 9 Nov: "very cluttered"): its symbol, the last price, the day's
 * change in price and in percent (green up, red down, with the arrow and sign as well), each in its own right-aligned column under the
 * panel's column heads, and a menu. A wide panel has room for the name and a line of recent closes too. The grip reorders it by
 * pointer or, with the arrow keys, from the keyboard. */
import { forwardRef, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Link } from "react-router-dom";
import { usePopover } from "../kit/Dialog";
import { Spark } from "../kit/Spark";
import { signCls } from "../../lib/format";
import { changeAbsText, changeArrow, changeText, chartPath, currencyOf, labelOf, listName, priceText, subtitleOf, type WatchItem, type WatchList, type WatchQuote } from "../../lib/watch";
import { currencySymbol } from "../../lib/format";

export interface RowProps {
  item: WatchItem; quote: WatchQuote | null | undefined; price: number | null; change: number | null; spark: number[] | undefined;
  /** The day's change in price terms. */
  changeAbs: number | null;
  /** Why the price may not be the market's now: "Delayed" (a source behind it) or "Closed" (the market is shut). */
  note: "Delayed" | "Closed" | null;
  canMove: boolean; dragging: boolean;
  /** Added a moment ago: marked so the eye finds it. */
  fresh?: boolean;
  lists: WatchList[]; listId: string;
  onOpen: () => void; onRemove: () => void; onMoveTo: (listId: string) => void;
  onGrip: (e: PointerEvent<HTMLButtonElement>) => void; onNudge: (by: -1 | 1) => void;
}

export const WatchRow = forwardRef<HTMLLIElement, RowProps>(function WatchRow(p, ref) {
  const { item, quote, price, change } = p;
  const label = labelOf(item);
  const [menu, setMenu] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  usePopover(menu, setMenu, trigger, panel);
  const cur = item.kind === "index" || item.market === "FX" || item.market === "CRYPTO" ? "" : currencySymbol(quote?.currency ?? currencyOf(item));
  const text = changeText(change);
  const key = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); p.onNudge(e.key === "ArrowUp" ? -1 : 1); }
  };
  const others = p.lists.filter((l) => l.id !== p.listId);
  const sub = subtitleOf(item);
  return (
    <li ref={ref} className={`mw-row${p.dragging ? " drag" : ""}${p.fresh ? " fresh" : ""}`} data-key={item.id}>
      {p.canMove
        ? <button type="button" className="mw-grip" aria-label={`Move ${label}. Drag, or press the up or down arrow.`} title="Drag to reorder" onPointerDown={p.onGrip} onKeyDown={key}><i aria-hidden="true" /></button>
        : <span className="mw-grip off" aria-hidden="true" />}
      <button type="button" className="mw-open" onClick={p.onOpen} aria-label={`Open the chart of ${label}`} title={sub === label ? label : `${label}: ${sub}`}>
        <span className="mw-name"><b>{label}</b>{p.note && <em className={p.note === "Delayed" ? "delayed" : undefined} title={p.note === "Delayed" ? "This price can be up to 15 minutes behind the market." : "The market is shut: this is its last price."}>{p.note}</em>}<small className="mw-sub">{sub}</small></span>
        <span className="mw-spark mw-c-spark" aria-hidden="true">{p.spark && p.spark.length > 1 ? <Spark values={p.spark} tone="neutral" label={`${label}, recent closes`} height={20} /> : null}</span>
        <b className="mw-num mw-price">{price == null ? "–" : <>{cur}{priceText(price, quote?.currency ?? null, item.market, item.symbol)}</>}</b>
        <span className={`mw-num mw-abs mw-c-abs ${signCls(change, text)}`}>{changeAbsText(p.changeAbs, price, quote?.currency ?? null, item.market, item.symbol)}</span>
        <span className={`mw-num mw-chg ${signCls(change, text)}`}><i className="mw-arrow">{changeArrow(change)}</i>{text}</span>
      </button>
      <div className="mw-more">
        <button ref={trigger} type="button" className="mw-dots" aria-label={`Actions for ${label}`} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)}><span aria-hidden="true">⋯</span></button>
        {menu && (
          <div ref={panel} className="mw-menu" role="menu" aria-label={`${label}`}>
            <button type="button" role="menuitem" onClick={() => { setMenu(false); p.onOpen(); }}>Open the chart</button>
            <Link role="menuitem" to={chartPath(item)} onClick={() => setMenu(false)}>Open as a full page</Link>
            {others.length > 0 && <div className="mw-menu-sub" role="group" aria-label="Move to another list">
              <small>Move to</small>
              {others.map((l) => <button key={l.id} type="button" role="menuitem" onClick={() => { setMenu(false); p.onMoveTo(l.id); }}>{listName(l.name)}</button>)}
            </div>}
            <button type="button" role="menuitem" className="danger" onClick={() => { setMenu(false); p.onRemove(); }}>Remove from this list</button>
          </div>
        )}
      </div>
    </li>
  );
});
