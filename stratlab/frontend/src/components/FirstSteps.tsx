import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { Card, CardHead } from "./kit";
import { useGuideOpen, welcomePending } from "../lib/onboarding";

const SEEN_KEY = "stratlab.firstSteps.shown";

type Step = { id: string; title: string; to: string; done: boolean };
type View = { show: boolean; dismissed: boolean; done: number; steps: Step[] };

/** Home's first-steps checklist for a new account. Each step ticks itself from what the user has really done; the
 *  list hides for good when dismissed, and by itself once every step is done. `compact`: one line with the next step,
 *  for a page whose own content comes first (DF-023: on Invest home the whole checklist, the same as on Trade home,
 *  took the top of the page). */
export function FirstSteps({ onShown, compact }: { onShown?: (shown: boolean) => void; compact?: boolean }) {
  const { fail, me, session } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const guiding = useGuideOpen();

  // LIVE7B-012: whether the line showed last time on this device, so its place is kept while the list is read (it came in late at the top of
  // the page and moved everything under it: /trade's layout shift was 0.30 with the full checklist)
  const key = `${SEEN_KEY}.${session?.user?.id ?? me?.id ?? "guest"}`;
  // LIVE12B-022: the row as it showed last time, so the held place is the row's own height (a phone wraps its words over two or three lines)
  const [last] = useState<View | null | false>(() => {
    try { const v = localStorage.getItem(key); return v === "1" ? null : v && v !== "0" ? (JSON.parse(v) as View) : false; } catch { return false; }
  });
  const wasShown = last !== false;
  useEffect(() => {
    let live = true;
    api<View>("/me/first-steps").then((v) => { if (live && v && Array.isArray(v.steps)) setView(v); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  // one guide at a time: the checklist waits for the welcome question and the tour
  const shown = !!view?.show && !!me && !welcomePending(me) && !guiding;
  // held while either answer is still on its way: the list (when it showed last time) or the account (when the list says it shows)
  const holding = !!compact && !guiding && (view ? !!view.show && !me : wasShown);
  useEffect(() => { onShown?.(shown || holding); }, [shown, holding, onShown]);
  useEffect(() => { if (view) try { localStorage.setItem(key, view.show ? JSON.stringify(view) : "0"); } catch { /* storage blocked */ } }, [view, key]);

  const dismiss = async () => {
    setBusy(true);
    try { setView(await api<View>("/me/first-steps", { method: "PUT", body: { dismissed: true } })); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const list = (v: View) => (
    <ol className="fs-list" id="fs-steps">
      {v.steps.map((s) => (
        <li key={s.id} className={s.done ? "done" : ""} data-step={s.id}>
          <span className="fs-tick" aria-hidden="true">{s.done ? "✓" : ""}</span>
          {s.done ? <span className="fs-title">{s.title}<span className="sr-only"> (done)</span></span>
            : <Link className="fs-title fs-go" to={s.to}>{s.title}</Link>}
        </li>
      ))}
    </ol>
  );
  // LIVE11B-009: one slim row across the page (the steps done as a bar, the next one, the whole list on a click), not a short card
  // with the rest of its row empty. `hold`: the row as it was last time, unseen and inert, keeping its place while the answers come
  function line(v: View, hold: boolean) {
    const total = v.steps.length;
    const next = v.steps.find((s) => !s.done);
    return (
      <Card compact className={`first-steps fs-compact${hold ? " fs-wait" : ""}`} label="Your first steps">
        <div className="fs-line" aria-hidden={hold || undefined} inert={hold || undefined}>
          <span className="k-small"><b>Your first steps</b> · {v.done} of {total} done{next && <> · next: <Link className="link" to={next.to}>{next.title}</Link></>}</span>
          <progress className="k-progress fs-bar" aria-label="First steps done" max={total} value={v.done} />
          <button type="button" className="btn quiet sm" aria-expanded={open} aria-controls="fs-steps" onClick={() => setOpen((o) => !o)}>{open ? "Fewer" : `All ${total} steps`}</button>
          <button type="button" className="btn quiet sm" disabled={busy} onClick={() => void dismiss()}>Hide this</button>
        </div>
        {!hold && open && list(v)}
      </Card>
    );
  }

  // while it is read: the same one line, held empty, where it showed last time
  const held = view ?? last;
  if (holding && held && Array.isArray(held.steps)) return line(held, true);
  if (holding) return <Card compact className="first-steps fs-compact fs-wait" label="Your first steps"><div className="fs-line" aria-hidden="true"><span className="k-small"><b>Your first steps</b></span><span className="fs-bar" /><span className="btn quiet sm fs-hold">Hide this</span></div></Card>;
  if (!shown || !view) return null;
  const total = view.steps.length;
  if (compact) return line(view, false);
  return (
    <Card className="first-steps" label="Your first steps">
      <CardHead title="Your first steps" actions={<button className="btn quiet sm" disabled={busy} onClick={dismiss}>Hide this</button>} />
      <span className="k-small k-muted">{view.done} of {total} done. Each one ticks itself when you've done it.</span>
      <progress className="k-progress" aria-label="First steps done" max={total} value={view.done} />
      {list(view)}
    </Card>
  );
}
