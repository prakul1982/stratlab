import { useEffect, useRef, type ReactNode } from "react";
import { useApp } from "../lib/app";
import type { CheckStatus, VerdictKind } from "../lib/types";
import { Close } from "./Icons";

export const VERDICT_NAME: Record<VerdictKind, string> = {
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

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card dashed stack" style={{ alignItems: "center", textAlign: "center", padding: 40 }}>
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
