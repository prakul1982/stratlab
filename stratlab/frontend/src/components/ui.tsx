import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useApp } from "../lib/app";
import type { CheckStatus, VerdictKind } from "../lib/types";
import { Close } from "./Icons";
import { asOf } from "../lib/format";

const VERDICT_NAME: Record<VerdictKind, string> = {
  edge: "Likely real edge", mixed: "Mixed evidence", luck: "Probably luck", not_enough: "Not enough evidence", no_edge: "No edge",
};
export const STATUS_NAME: Record<CheckStatus, string> = { pass: "Passed", warn: "Warning", fail: "Failed", skip: "Skipped" };

export const VerdictBadge = ({ v }: { v: VerdictKind | null | undefined }) =>
  v ? <span className={`badge ${v}`}>{VERDICT_NAME[v]}</span> : <span className="badge skip">No experiments yet</span>;

export function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div className="toast" role="status">
      <span>{toast.msg}</span>
      {toast.action && <button onClick={toast.action.run}>{toast.action.label}</button>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>("input, textarea, button:not([data-close])")?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("keydown", esc); prev?.focus(); };
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={box} style={wide ? { width: "min(920px, 100%)" } : undefined}>
        <div className="spread" style={{ marginBottom: 16 }}>
          <h2 className="h2">{title}</h2>
          <button className="icon-btn" data-close aria-label="Close" onClick={onClose}><Close /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="row muted" style={{ padding: 40, justifyContent: "center" }}><span className="spinner" />{label}…</div>;
}

/** A panel's placeholder while it loads, about the height of what replaces it: a row of figures (`figs`), or `lines`
 * of text. Screen readers hear `label`. */
export function PanelSkel({ label, figs, lines = 2 }: { label: string; figs?: boolean; lines?: number }) {
  return (
    <div className="panel-skel" role="status" aria-label={label} aria-busy="true">
      {figs ? (
        <div className="panel-skel-figs">{[0, 1, 2].map((i) => <span key={i}><span className="skel" /><span className="skel big" /></span>)}</div>
      ) : Array.from({ length: lines }, (_, i) => <span key={i} className="skel line" style={{ width: `${92 - i * 17}%` }} />)}
      <span className="skel line" style={{ width: "40%" }} />
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card dashed stack empty">
      <h2 className="h2">{title}</h2>
      {children}
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

/** A small (i) button that explains the thing next to it. Click or tap to open; Escape or a click outside closes. */
export function Info({ children, label = "What does this mean?" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const [side, setSide] = useState<"left" | "right">("left");
  const wrap = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const r = wrap.current?.getBoundingClientRect();
    if (r) setSide(r.left + 300 > window.innerWidth - 12 ? "right" : "left");
    const out = (e: MouseEvent | TouchEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", out);
    document.addEventListener("touchstart", out);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", out);
      document.removeEventListener("touchstart", out);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <span ref={wrap} className="info">
      <button type="button" className="info-btn" aria-label={label} aria-expanded={open} aria-controls={id}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); }}>i</button>
      {open && <span id={id} role="note" className={`info-pop ${side}`}>{children}</span>}
    </span>
  );
}

/** One labelled figure in a row of them (`.space-figs`): the label, the number, and a note under it. The row is one grid,
 * so the numbers sit on one line however the labels wrap. A missing number says why in words (`missing`), never a
 * bare dash. */
export function Fig({ label, value, note, noteTone = "muted", tone = "", missing = "Not available yet", missingId }:
  { label: ReactNode; value: ReactNode; note?: ReactNode; noteTone?: string; tone?: string; missing?: string; missingId?: string }) {
  const none = value == null || value === false || (typeof value === "string" && /^\s*[-–—]?\s*$/.test(value));
  return (
    <div className="space-fig">
      <span className="tiny muted">{label}</span>
      {none ? <span className="small muted fig-missing" data-testid={missingId}>{missing}</span> : <b className={`num ${tone}`.trim()}>{value}</b>}
      {note ? <span className={`tiny ${noteTone}`}>{note}</span> : null}
    </div>
  );
}

/** A small "as of" line, so people know how fresh the numbers next to it are. Each part shows only when known. */
export function AsOf({ parts }: { parts: [string, string | null | undefined][] }) {
  const shown = parts.map(([label, iso]) => [label, asOf(iso)] as const).filter(([, t]) => t);
  if (!shown.length) return null;
  return <p className="tiny muted as-of">{shown.map(([label, t]) => `${label} as of ${t}`).join(" · ")}</p>;
}
