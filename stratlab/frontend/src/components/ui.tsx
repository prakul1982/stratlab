import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { CheckStatus, VerdictKind } from "../lib/types";
import { usePopover } from "./kit/Dialog";
import { asOf } from "../lib/format";

const VERDICT_NAME: Record<VerdictKind, string> = {
  // facts about the checks, never a claim about the strategy (R11C-009: the badge said "Likely a real edge" beside a return far behind buy and hold)
  edge: "Passed the checks", mixed: "Mixed check results", luck: "Failed a robustness check", not_enough: "Too few trades", no_edge: "Lost money after costs",
};
export const STATUS_NAME: Record<CheckStatus, string> = { pass: "Passed", warn: "Warning", fail: "Failed", skip: "Skipped" };

/** The same verdicts as facts about the checks, with no judgement of the strategy: the library lists other people's
 * rules side by side, where "Likely a real edge" beside a return far behind buy and hold reads as a recommendation (R5O-014). */
export const VERDICT_FACT: Record<VerdictKind, string> = {
  edge: "Passed the checks", mixed: "Mixed check results", luck: "Failed a robustness check", not_enough: "Too few trades", no_edge: "Lost money after costs",
};

/** `label`: the server's own words for this verdict (a library entry's "Passed all 3 checks run"), shown instead. */
/** `tone`: the colour class when it isn't the verdict's own (a pass beside a big shortfall to buy and hold is plain grey,
 *  R43A-007). */
export const VerdictBadge = ({ v, facts, label, tone }: { v: VerdictKind | null | undefined; facts?: boolean; label?: string | null; tone?: string }) =>
  v ? <span className={`badge ${tone ?? v}`}>{label || (facts ? VERDICT_FACT : VERDICT_NAME)[v]}</span> : <span className="badge skip">No experiments yet</span>;

/** The kit's modal dialog (components/kit/Dialog), under its old name. */
export { Dialog as Modal } from "./kit/Dialog";

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="k-loading"><span className="spinner" />{label}…</div>;
}

/** A panel's placeholder while it loads, about the height of what replaces it: a row of figures (`figs`), or `lines`
 * of text. Screen readers hear `label`. */
export function PanelSkel({ label, figs, lines = 2 }: { label: string; figs?: boolean; lines?: number }) {
  return (
    <div className="panel-skel" role="status" aria-label={label} aria-busy="true">
      {figs ? (
        <div className="panel-skel-figs">{[0, 1, 2].map((i) => <span key={i}><span className="skel" /><span className="skel big" /></span>)}</div>
      ) : Array.from({ length: lines }, (_, i) => <span key={i} className="skel line" />)}
      <span className="skel line last" />
    </div>
  );
}

/** Auto-growing textarea for the notebook question. */
export function AutoGrow(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  });
  return <textarea ref={ref} rows={1} {...props} />;
}

/** A small (i) button that explains the thing next to it. Click or tap to open; Escape or a click outside closes, and
 * focus stays on the button. Name it after what it explains ("About Markets"); beside a heading it sits after the
 * heading element, never inside it. The box is drawn on the page's top layer (a portal to the body, fixed to the button),
 * so a table's scroll box or a card's edge never cuts it (owner, 5 Nov: the box in a table was cut off at the card's edge);
 * it opens under the button, or above when there is no room below, and stays inside the screen's sides. */
export function Info({ children, label = "What does this mean?" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<{ left: number; top: number; up: boolean } | null>(null);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const id = useId();
  usePopover(open, setOpen, btn, pop, { focusInto: false });
  useLayoutEffect(() => {
    if (!open) { setAt(null); return; }
    const place = () => {
      const b = btn.current?.getBoundingClientRect(), p = pop.current;
      if (!b || !p) return;
      const vw = document.documentElement.clientWidth, vh = window.innerHeight, gap = 8, edge = 12;
      const w = p.offsetWidth, h = p.offsetHeight;
      // the circle is drawn inside a larger tap box: measure from the box's middle, where the circle is
      const mid = b.left + b.width / 2;
      const left = Math.max(edge, Math.min(mid - 22, vw - w - edge));
      const below = b.bottom + gap, room = vh - below - edge;
      const up = h > room && b.top - gap - h >= edge;
      setAt({ left, top: up ? b.top - gap - h : below, up });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => { window.removeEventListener("scroll", place, true); window.removeEventListener("resize", place); };
  }, [open]);
  return (
    <span className="info">
      <button ref={btn} type="button" className="info-btn" aria-label={label} aria-expanded={open} aria-controls={open ? id : undefined}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (!open) setHost(layerOf(btn.current)); setOpen(!open); }}>i</button>
      {open && host && createPortal(
        // a click inside the box is not a click on whatever holds the button (a row, a card that opens)
        <span ref={pop} id={id} role="note" className={`info-pop${at?.up ? " up" : ""}`} onClick={(e) => e.stopPropagation()}
          style={at ? { left: at.left, top: at.top } : { left: 0, top: 0, visibility: "hidden" }}>{children}</span>,
        host)}
    </span>
  );
}

/** Where an (i) box is drawn: inside the floating layer the button is in (a dialog, the Market Watch panel, a full-screen chart), so it
 * is over that layer and under whatever is over it; else on the body, over the page and under every floating layer. */
function layerOf(el: HTMLElement | null): HTMLElement {
  for (let p = el?.parentElement; p && p !== document.body; p = p.parentElement) if (getComputedStyle(p).position === "fixed") return p;
  return document.body;
}

/** One labelled figure in a row of them (`.k-stats`): the label, the number, and a note under it. The row is one grid,
 * so the numbers sit on one line however the labels wrap. A missing number says why in words (`missing`), never a
 * bare dash. */
export function Fig({ label, value, note, tone = "", missing = "Not available yet", missingId, noteTone = "" }:
  { label: ReactNode; value: ReactNode; note?: ReactNode; noteTone?: string; tone?: string; missing?: string; missingId?: string }) {
  const none = value == null || value === false || (typeof value === "string" && /^\s*[-–—]?\s*$/.test(value));
  const dirOf = (t: string) => (/\bup\b|\bpos\b|\bk-up\b/.test(t) ? " k-up" : /\bdown\b|\bneg\b|\bk-down\b/.test(t) ? " k-down" : "");
  const dir = dirOf(tone);
  return (
    <div className="k-stat">
      <span className="k-stat-k">{label}</span>
      {none ? <span className="k-stat-d" data-testid={missingId}>{missing}</span> : <span className={`k-stat-v${dir}`}>{value}</span>}
      {note ? <span className="k-stat-d"><span className={dirOf(noteTone).trim() || undefined}>{note}</span></span> : null}
    </div>
  );
}

/** A small "as of" line, so people know how fresh the numbers next to it are. Each part shows only when known. Times
 * are in the market's zone with its name (India's unless `tz` says otherwise). */
export function AsOf({ parts, tz }: { parts: [string, string | null | undefined][]; tz?: string }) {
  const shown = parts.map(([label, iso]) => [label, asOf(iso, { tz })] as const).filter(([, t]) => t);
  if (!shown.length) return null;
  return <p className="tiny muted as-of">{shown.map(([label, t]) => `${label} as of ${t}`).join(" · ")}</p>;
}
