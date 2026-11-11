import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { watchSize } from "../../lib/resize";
import { layout, legend, matches, step, stepClass, tileWords, type ColorBy, type GroupBy, type Period, type Placed, type SizeBy, type Tile } from "../../lib/heatmap";
import "./treemap.css";

/* The heatmap's drawing: a treemap of tiles, each a link to its company's page, sized and coloured by the figures the page picks
 * (lib/heatmap.ts does the arithmetic). A tile big enough shows its symbol and its figure, so the colour is never the only signal;
 * every tile says both in its tooltip and to a screen reader, and the page's Table view lists them all. */

const GAP = 2;                    // the surface showing between two tiles, in px
const TIP_W = 250;

// A tile shows its symbol and its figure only at a size they fit at, so no word is ever cut by its tile's edge: each text is
// measured once in the page's own font (at 10px; a width grows with the size), and again once the fonts have loaded.
let pen: CanvasRenderingContext2D | null | undefined;
const measured = new Map<string, number>();
function textWidth(text: string, weight: number): number {
  const key = `${weight}|${text}`;
  const hit = measured.get(key);
  if (hit != null) return hit;
  if (pen === undefined) pen = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
  if (!pen) return text.length * 6.8;
  pen.font = `${weight} 10px ${getComputedStyle(document.body).fontFamily}`;
  const w = pen.measureText(text).width;
  measured.set(key, w);
  return w;
}
export type TreemapProps = {
  tiles: Tile[]; size: SizeBy; color: ColorBy; period: Period; group: GroupBy; index?: (number | null)[] | null;
  /** what was typed in the search box: tiles that don't match fade */
  query?: string;
  /** a tile's address and its figure as text ("+1.2%") */
  href: (t: Tile) => string; figure: (v: number | null) => string;
  /** the tooltip's lines for a tile */
  tip: (p: Placed) => ReactNode;
  label: string;
  /** how many tiles had no size figure, for the page's note */
  onLeftOut?: (n: number) => void;
};

/** The drawing's height for its width: wider than tall on a desktop, taller than wide on a phone; shorter when there are only a few
 * tiles, and taller when there are many, so an average tile keeps room for its symbol (a phone's map of 200 tiles is about three
 * screens long, and scrolls with the page). */
export function mapHeight(width: number, tiles: number): number {
  if (width <= 0) return 0;
  const few = tiles <= 12 ? 0.7 : tiles <= 40 ? 0.85 : 1;
  if (width < 640) return Math.round(Math.min(1500, Math.max(Math.max(360, Math.min(720, width * 1.45)) * few, (tiles * 1850) / width)));
  return Math.round(Math.min(900, Math.max(Math.max(420, Math.min(700, width * 0.56)) * few, (tiles * 1500) / width)));
}

export function Treemap({ tiles, size, color, period, group, index, query = "", href, figure, tip, label, onLeftOut }: TreemapProps) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<{ p: Placed; x: number; y: number } | null>(null);
  const [, setFonts] = useState(0);
  useEffect(() => {
    let live = true;
    document.fonts?.ready.then(() => { if (live) { measured.clear(); setFonts((n) => n + 1); } }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const read = () => setWidth(Math.floor(el.clientWidth));
    read();
    return watchSize(el, read);
  }, []);
  const height = mapHeight(width, tiles.length);
  const laid = useMemo(() => (width > 0 ? layout(tiles, { size, color, period, group, index }, width, height) : null), [tiles, size, color, period, group, index, width, height]);
  const leftOut = laid?.left_out ?? 0;
  useEffect(() => { onLeftOut?.(leftOut); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leftOut]);
  const searching = query.trim() !== "";
  const move = (p: Placed) => (e: MouseEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setHover({ p, x: e.clientX - r.left, y: e.clientY - r.top });
  };
  const tipLeft = hover ? Math.max(0, Math.min(width - TIP_W, hover.x + 14 + TIP_W > width ? hover.x - TIP_W - 10 : hover.x + 14)) : 0;
  const tipUp = !!hover && hover.y > height * 0.55;
  return (
    <div className="hm-map" ref={box} role="group" aria-label={label} style={{ height: width > 0 ? height : undefined }} onMouseLeave={() => setHover(null)}>
      {laid?.groups.map((g) => (
        <div key={g.name || "all"} className="hm-group" role="group" aria-label={g.name ? `${g.name}${g.value != null ? `, ${figure(g.value)}` : ""}` : undefined}>
          {g.head > 0 && (
            <div className="hm-group-head" aria-hidden="true" style={{ left: g.box.x + GAP / 2, top: g.box.y + GAP / 2, width: Math.max(0, g.box.w - GAP), height: g.head - GAP / 2 }}>
              <span className="hm-group-name">{g.name}</span>
              {g.value != null && g.box.w >= 150 && <span className="hm-group-fig">{figure(g.value)}</span>}
            </div>
          )}
          {g.tiles.map((p) => {
            const w = Math.max(0, p.box.w - GAP), h = Math.max(0, p.box.h - GAP);
            if (w < 1 || h < 1) return null;
            const cls = stepClass(step(p.value, color, period), color);
            const text = figure(p.value);
            const { px, fig } = tileWords(p.tile.s, text, w, h, textWidth);
            const scale = px === 15 ? " lg" : px === 10 ? " sm" : "";
            const off = searching && !matches(p.tile, query);
            return (
              <Link key={p.tile.s} to={href(p.tile)} tabIndex={-1} className={`hm-tile ${cls}${scale}${off ? " off" : searching ? " hit" : ""}`}
                style={{ left: p.box.x + GAP / 2, top: p.box.y + GAP / 2, width: w, height: h }}
                aria-label={`${p.tile.n}, ${text}`} onMouseEnter={move(p)} onMouseMove={move(p)}>
                {/* the link's name says both in words; the tile's own letters are the picture */}
                {px > 0 && <span className="hm-sym" aria-hidden="true">{p.tile.s}</span>}
                {fig && <span className="hm-fig" aria-hidden="true">{text}</span>}
              </Link>
            );
          })}
        </div>
      ))}
      {hover && (
        <div className={`hm-tip${tipUp ? " up" : ""}`} aria-hidden="true" style={{ left: tipLeft, top: tipUp ? undefined : hover.y + 16, bottom: tipUp ? height - hover.y + 10 : undefined, width: TIP_W }}>
          {tip(hover.p)}
        </div>
      )}
    </div>
  );
}

/** The legend under the map: each colour step with the figure it starts at. */
export function TreemapLegend({ color, period, title }: { color: ColorBy; period: Period; title: string }) {
  const steps = legend(color, period);
  return (
    <div className="hm-legend" role="group" aria-label={title}>
      <span className="hm-legend-title">{title}</span>
      <span className="hm-legend-steps">
        {steps.map((s) => <span key={s.cls} className={`hm-legend-step ${s.cls}`}>{s.label}</span>)}
        <span className="hm-legend-step hm-na">no figure</span>
      </span>
    </div>
  );
}
