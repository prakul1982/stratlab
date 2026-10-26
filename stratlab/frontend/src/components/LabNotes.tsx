import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Card, CardHead } from "./kit";
import { HELP } from "../lib/help";

/* The notebook's Lab notes as a floating panel (MO-4a): a small button at the bottom-right that opens a card above it (a bottom
 * sheet on a phone), so the notebook keeps the one centred column every page has instead of sharing its row with a notes card.
 * What the notes store is unchanged: the parent still saves `value` through the notebook's own autosave. */

const KEY = "stratlab.labnotes.open";
const PANEL = "lab-notes-panel";

function remembered(): boolean {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}
function remember(open: boolean) {
  try { localStorage.setItem(KEY, open ? "1" : "0"); } catch { /* private window or blocked storage: the panel just starts closed next time */ }
}

export type LabNotesHandle = { /** open the panel and put the cursor in the notes (a suggestion that says "write a note") */ focus: () => void };

export const LabNotes = forwardRef<LabNotesHandle, { value: string; onChange: (v: string) => void }>(function LabNotes({ value, onChange }, ref) {
  const [open, setOpen] = useState(remembered);
  const button = useRef<HTMLButtonElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const focusIn = useRef(false);        // set when a person opened it (button or suggestion), not when it came back open from storage

  const set = useCallback((next: boolean, focus = false) => {
    focusIn.current = next && focus;
    setOpen(next);
    remember(next);
  }, []);
  useImperativeHandle(ref, () => ({ focus: () => { set(true, true); if (open) area.current?.focus(); } }), [set, open]);

  // focus goes into the notes when it opens, and back to the button when it closes
  const was = useRef(open);
  useEffect(() => {
    if (open && focusIn.current) area.current?.focus();
    else if (!open && was.current) button.current?.focus();
    was.current = open;
    focusIn.current = false;
  }, [open]);

  const has = value.trim().length > 0;
  return (
    <div className="ln-dock"
      // Escape closes it, unless it was meant for the (i) tip inside, which has already taken it
      onKeyDown={(e) => { if (open && e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); set(false); } }}>
      <div className="ln-dock-in">
      <div id={PANEL} className="ln-panel" hidden={!open}>
        <Card label="Lab notes">
          <CardHead title="Lab notes" level={3} info={HELP.labNotes} infoLabel="About lab notes"
            actions={<button type="button" className="btn sm quiet" onClick={() => set(false)} aria-label="Close lab notes">Close</button>} />
          <label className="sr-only" htmlFor="notes">Lab notes</label>
          <textarea id="notes" ref={area} className="lab-note" value={value} maxLength={4000}
            placeholder="What did you notice? What do you want to try next?" onChange={(e) => onChange(e.target.value)} />
        </Card>
      </div>
      <button ref={button} type="button" className="ln-btn" aria-expanded={open} aria-controls={PANEL} data-testid="lab-notes-btn"
        onClick={() => set(!open, true)}>
        Lab notes{has && <><span className="ln-dot" aria-hidden="true" /><span className="sr-only"> (this notebook has notes)</span></>}
      </button>
      </div>
    </div>
  );
});
