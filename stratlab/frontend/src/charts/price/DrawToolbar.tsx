/* The drawing tools' own controls: a vertical rail on desktop, a bottom sheet on a phone, the bar for the selected
 * drawing (colour, line style, lock, duplicate, delete, text, risk amount), the list of drawings with show/hide, and
 * the shortcut list behind an (i). Plain props in, events out: the chart owns the state. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Modal } from "../../components/ui";
import { COLOR_KEYS, DASH_KEYS, DRAW_TOOLS, drawingTitle, SHORTCUTS, TOOL, TOOL_GROUPS, TOOL_HINT, type ColorKey, type DashStyle, type Drawing, type DrawingKind } from "./drawings";

const I = (d: ReactNode) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
export const DRAW_ICON: Record<string, ReactNode> = {
  select: I(<path d="M6 4l12 8-5 1.4L10.5 19z" />),
  trend: I(<><path d="M4 19 20 5" /><circle cx="4" cy="19" r="1.6" /><circle cx="20" cy="5" r="1.6" /></>),
  ray: I(<><path d="M4 18 21 6" /><circle cx="4" cy="18" r="1.6" /></>),
  hline: I(<><path d="M3 12h18" /><circle cx="12" cy="12" r="1.6" /></>),
  hray: I(<><path d="M5 12h16" /><circle cx="5" cy="12" r="1.6" /></>),
  vline: I(<><path d="M12 3v18" /><circle cx="12" cy="12" r="1.6" /></>),
  rect: I(<rect x="4" y="6" width="16" height="12" rx="1" />),
  channel: I(<><path d="M4 15 20 6M4 20 20 11" /></>),
  fib: I(<path d="M3 5h18M3 10h18M3 14h18M3 19h18" />),
  long: I(<><rect x="5" y="4" width="14" height="8" rx="1" /><rect x="5" y="12" width="14" height="7" rx="1" strokeDasharray="2 2" /></>),
  short: I(<><rect x="5" y="5" width="14" height="7" rx="1" strokeDasharray="2 2" /><rect x="5" y="12" width="14" height="8" rx="1" /></>),
  measure: I(<><path d="M5 19 19 5" /><path d="M5 19v-4M5 19h4M19 5v4M19 5h-4" /></>),
  prange: I(<><path d="M12 4v16M9 7l3-3 3 3M9 17l3 3 3-3" /><path d="M5 4h14M5 20h14" strokeDasharray="2 2" /></>),
  drange: I(<><path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3" /><path d="M4 5v14M20 5v14" strokeDasharray="2 2" /></>),
  text: I(<path d="M5 6h14M12 6v13" />),
  arrow: I(<><path d="M5 19 19 5" /><path d="M10 5h9v9" /></>),
  brush: I(<path d="M4 17c3-7 5 3 8-3s4-6 8-9" />),
  magnet: I(<path d="M6 4v8a6 6 0 0 0 12 0V4h-4v8a2 2 0 0 1-4 0V4zM6 8h4M14 8h4" />),
  eye: I(<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>),
  eyeOff: I(<><path d="M3 3l18 18M10 6a9 9 0 0 1 2-.2c6 0 10 6.2 10 6.2a15 15 0 0 1-3 3.5M6.6 7.6A15 15 0 0 0 2 12s4 7 10 7a9 9 0 0 0 4-1" /></>),
  list: I(<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />),
  undo: I(<path d="M9 7 4 12l5 5M4 12h10a6 6 0 0 1 6 6" />),
  redo: I(<path d="m15 7 5 5-5 5M20 12H10a6 6 0 0 0-6 6" />),
  lock: I(<><rect x="5" y="11" width="14" height="9" rx="1.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>),
  unlock: I(<><rect x="5" y="11" width="14" height="9" rx="1.5" /><path d="M8 11V8a4 4 0 0 1 7.5-2" /></>),
  copy: I(<><rect x="8" y="8" width="12" height="12" rx="1.5" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>),
  trash: I(<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />),
  pencil: I(<path d="M4 20l1-4L16 5l3 3L8 19zM14 7l3 3" />),
};

const Btn = ({ label, icon, pressed, disabled, onClick, children, title }: {
  label: string; icon: string; pressed?: boolean; disabled?: boolean; onClick: () => void; children?: ReactNode; title?: string;
}) => (
  <button type="button" className="pc-btn icon" aria-label={label} title={title ?? label} aria-pressed={pressed} disabled={disabled} onClick={onClick}>
    {DRAW_ICON[icon]}{children}
  </button>
);

export interface ToolState {
  tool: DrawingKind | null; onTool: (k: DrawingKind | null) => void;
  magnet: boolean; onMagnet: () => void;
  hideAll: boolean; onHide: () => void;
  canUndo: boolean; canRedo: boolean; onUndo: () => void; onRedo: () => void;
  drawings: Drawing[]; selected: string | null; onSelect: (id: string | null) => void;
  onUpdate: (id: string, patch: Partial<Drawing>) => void; onDelete: (id: string) => void; onClearAll: () => void;
}

/** Undo and redo, in the chart's top bar. */
export function HistoryButtons(p: Pick<ToolState, "canUndo" | "canRedo" | "onUndo" | "onRedo">) {
  return (
    <span className="pc-seg" role="group" aria-label="Undo and redo">
      <Btn label="Undo" title="Undo (Ctrl/Cmd+Z)" icon="undo" disabled={!p.canUndo} onClick={p.onUndo} />
      <Btn label="Redo" title="Redo (Ctrl/Cmd+Shift+Z)" icon="redo" disabled={!p.canRedo} onClick={p.onRedo} />
    </span>
  );
}

/** The (i) with every shortcut. */
export function ShortcutsButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="info-btn pc-info" aria-label="Drawing tools and shortcuts" title="Drawing tools and shortcuts" onClick={() => setOpen(true)}>i</button>
      {open && (
        <Modal title="Drawing shortcuts" onClose={() => setOpen(false)}>
          <p className="k-small k-muted">Click the chart first so the keys go to it. Drawings are saved to your account for this symbol.</p>
          <dl className="pc-keys">
            {SHORTCUTS.map((s) => <div key={s.what}><dt><kbd>{s.keys}</kbd></dt><dd>{s.what}</dd></div>)}
          </dl>
          <p className="k-small k-muted">On a phone: tap Draw, pick a tool, then tap the first point and the second. Drag a handle to adjust.</p>
        </Modal>
      )}
    </>
  );
}

/** The list of drawings: show or hide each, lock, delete, and pick one to edit. */
function DrawList(p: ToolState) {
  return (
    <div className="pc-list" role="list" aria-label="Drawings">
      {!p.drawings.length && <p className="pc-note">Nothing drawn on this chart yet.</p>}
      {p.drawings.map((d) => (
        <div key={d.id} role="listitem" className={`pc-row${d.id === p.selected ? " on" : ""}${d.hidden ? " off" : ""}`}>
          <button type="button" className="pc-row-name" onClick={() => p.onSelect(d.id === p.selected ? null : d.id)}>
            <span className="pc-ico">{DRAW_ICON[TOOL[d.kind].icon]}</span><span>{drawingTitle(d)}</span>
          </button>
          <Btn label={d.hidden ? `Show ${TOOL[d.kind].name}` : `Hide ${TOOL[d.kind].name}`} icon={d.hidden ? "eyeOff" : "eye"} pressed={!d.hidden} onClick={() => p.onUpdate(d.id, { hidden: !d.hidden })} />
          <Btn label={d.locked ? `Unlock ${TOOL[d.kind].name}` : `Lock ${TOOL[d.kind].name}`} icon={d.locked ? "lock" : "unlock"} pressed={!!d.locked} onClick={() => p.onUpdate(d.id, { locked: !d.locked })} />
          <Btn label={`Delete ${TOOL[d.kind].name}`} icon="trash" disabled={!!d.locked} onClick={() => p.onDelete(d.id)} />
        </div>
      ))}
      {p.drawings.length > 0 && <button type="button" className="btn quiet sm" onClick={p.onClearAll}>Remove all drawings</button>}
    </div>
  );
}

/** The vertical rail on a desktop chart. */
export function DrawRail(p: ToolState) {
  const [open, setOpen] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const out = (e: Event) => { if (!ref.current?.contains(e.target as Node)) setOpen(null); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("pointerdown", out);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", out); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="pc-rail" ref={ref} role="toolbar" aria-orientation="vertical" aria-label="Drawing tools">
      <Btn label="Select" title="Select and edit drawings (V)" icon="select" pressed={!p.tool} onClick={() => { p.onTool(null); setOpen(null); }} />
      {TOOL_GROUPS.map((g) => {
        const current = g.kinds.includes(p.tool as DrawingKind) ? (p.tool as DrawingKind) : g.kinds[0];
        return (
          <div className="pc-wrap" key={g.id}>
            <Btn label={g.name} title={`${g.name}: ${g.kinds.map((k) => TOOL[k].name).join(", ")}`} icon={TOOL[current].icon}
              pressed={g.kinds.includes(p.tool as DrawingKind)} onClick={() => setOpen(open === g.id ? null : g.id)}>
              <span className="pc-caret" aria-hidden="true" />
            </Btn>
            {open === g.id && (
              <div className="pc-pop pc-fly" role="menu" aria-label={g.name}>
                {g.kinds.map((k) => (
                  <button key={k} type="button" role="menuitem" aria-label={TOOL[k].name} aria-keyshortcuts={TOOL[k].key} className="item row" onClick={() => { p.onTool(k); setOpen(null); }}>
                    <span className="pc-ico">{DRAW_ICON[TOOL[k].icon]}</span><span>{TOOL[k].name}</span><kbd>{TOOL[k].key}</kbd>
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <span className="pc-rule" />
      <Btn label="Magnet" title="Magnet: snap to open, high, low and close (G)" icon="magnet" pressed={p.magnet} onClick={p.onMagnet} />
      <Btn label={p.hideAll ? "Show all drawings" : "Hide all drawings"} title="Hide or show all drawings (O)" icon={p.hideAll ? "eyeOff" : "eye"} pressed={p.hideAll} onClick={p.onHide} />
      <div className="pc-wrap">
        <Btn label={`Drawings (${p.drawings.length})`} icon="list" pressed={open === "list"} onClick={() => setOpen(open === "list" ? null : "list")} />
        {open === "list" && <div className="pc-pop pc-fly pc-listpop" role="dialog" aria-label="Drawings"><DrawList {...p} /></div>}
      </div>
    </div>
  );
}

/** The same controls as a bottom sheet, for a phone. */
export function DrawSheet(p: ToolState & { onClose: () => void }) {
  const pick = (k: DrawingKind | null) => { p.onTool(k); p.onClose(); };
  return (
    <div className="pc-sheet" role="dialog" aria-label="Drawing tools">
      <div className="pc-sheet-head">
        <b>Draw</b>
        <span className="pc-sheet-acts">
          <Btn label="Select" icon="select" pressed={!p.tool} onClick={() => pick(null)} />
          <Btn label="Magnet" icon="magnet" pressed={p.magnet} onClick={p.onMagnet} />
          <Btn label={p.hideAll ? "Show all drawings" : "Hide all drawings"} icon={p.hideAll ? "eyeOff" : "eye"} pressed={p.hideAll} onClick={p.onHide} />
          <button type="button" className="pc-btn" onClick={p.onClose}>Done</button>
        </span>
      </div>
      <div className="pc-sheet-body">
        {TOOL_GROUPS.map((g) => (
          <section key={g.id} aria-label={g.name}>
            <h4>{g.name}</h4>
            <div className="pc-tiles">
              {g.kinds.map((k) => (
                <button key={k} type="button" className="pc-tile" aria-pressed={p.tool === k} onClick={() => pick(k)}>{DRAW_ICON[TOOL[k].icon]}<span>{TOOL[k].name}</span></button>
              ))}
            </div>
          </section>
        ))}
        <section aria-label="Drawings on this chart">
          <h4>Drawings ({p.drawings.length})</h4>
          <DrawList {...p} />
        </section>
      </div>
    </div>
  );
}

const SWATCH: Record<ColorKey, string> = { ink: "Black", blue: "Blue", orange: "Orange", green: "Green", magenta: "Magenta", grey: "Grey" };
const DASH_NAME: Record<DashStyle, string> = { solid: "Solid line", dashed: "Dashed line", dotted: "Dotted line" };

/** Colour, line style, text, risk amount, lock, duplicate and delete for the selected drawing. */
export function SelectionBar({ d, symbol, onUpdate, onDelete, onDuplicate, focusText }: {
  d: Drawing; symbol: string; onUpdate: (patch: Partial<Drawing>) => void; onDelete: () => void; onDuplicate: () => void; focusText: number;
}) {
  const textRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (d.kind === "text" && focusText) { textRef.current?.focus(); textRef.current?.select(); } }, [focusText, d.kind, d.id]);
  const locked = !!d.locked;
  const pos = d.kind === "long" || d.kind === "short";
  return (
    <div className="pc-selbar" role="toolbar" aria-label={`${TOOL[d.kind].name} settings`} onKeyDown={(e) => e.stopPropagation()}>
      <span className="pc-selbar-name">{TOOL[d.kind].name}</span>
      <span className="pc-colors" role="group" aria-label="Colour">
        {COLOR_KEYS.map((c) => (
          <button key={c} type="button" className={`pc-dot sw-${c}`} aria-label={SWATCH[c]} aria-pressed={(d.color ?? "ink") === c} disabled={locked} onClick={() => onUpdate({ color: c })} />
        ))}
      </span>
      {d.kind !== "text" && d.kind !== "brush" && (
        <span className="pc-seg" role="group" aria-label="Line style">
          {DASH_KEYS.map((s) => (
            <button key={s} type="button" className="pc-btn icon" aria-label={DASH_NAME[s]} title={DASH_NAME[s]} aria-pressed={(d.dash ?? "solid") === s} disabled={locked} onClick={() => onUpdate({ dash: s })}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h18" stroke="currentColor" strokeWidth="2" strokeDasharray={s === "solid" ? undefined : s === "dashed" ? "5 3" : "1 3"} strokeLinecap="round" /></svg>
            </button>
          ))}
        </span>
      )}
      {d.kind === "text" && (
        <input ref={textRef} className="pc-text" aria-label="Note text" maxLength={200} value={d.text ?? ""} disabled={locked}
          onChange={(e) => onUpdate({ text: e.target.value })} />
      )}
      {pos && (
        <label className="pc-risk">Risk amount
          <span className="pc-unit">{symbol}</span>
          <input type="number" inputMode="decimal" min={0} step="any" aria-label="Risk amount" value={d.risk ?? ""} disabled={locked}
            onChange={(e) => { const v = Number(e.target.value); onUpdate({ risk: e.target.value === "" || !Number.isFinite(v) || v < 0 ? undefined : v }); }} />
        </label>
      )}
      <Btn label={locked ? "Unlock" : "Lock"} title={locked ? "Unlock (Shift+L)" : "Lock in place (Shift+L)"} icon={locked ? "lock" : "unlock"} pressed={locked} onClick={() => onUpdate({ locked: !locked })} />
      <Btn label="Duplicate" title="Duplicate (Ctrl/Cmd+D)" icon="copy" onClick={onDuplicate} />
      <Btn label="Delete drawing" title="Delete (Delete key)" icon="trash" disabled={locked} onClick={onDelete} />
    </div>
  );
}

export { DRAW_TOOLS, TOOL_HINT };
