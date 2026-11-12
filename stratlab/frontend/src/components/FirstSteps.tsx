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
  const guiding = useGuideOpen();

  // LIVE7B-012: whether the line showed last time on this device, so its place is kept while the list is read (it came in late at the top of
  // the page and moved everything under it: /trade's layout shift was 0.30 with the full checklist)
  const key = `${SEEN_KEY}.${me?.id ?? session?.user?.id ?? "guest"}`;
  const [wasShown] = useState(() => { try { return localStorage.getItem(key) === "1"; } catch { return false; } });
  useEffect(() => {
    let live = true;
    api<View>("/me/first-steps").then((v) => { if (live && v && Array.isArray(v.steps)) setView(v); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  // one guide at a time: the checklist waits for the welcome question and the tour
  const shown = !!view?.show && !!me && !welcomePending(me) && !guiding;
  const holding = !view && wasShown && !!compact && !guiding;
  useEffect(() => { onShown?.(shown || holding); }, [shown, holding, onShown]);
  useEffect(() => { if (view) try { localStorage.setItem(key, view.show ? "1" : "0"); } catch { /* storage blocked */ } }, [view, key]);

  // while it is read: the same one line, held empty, where it showed last time
  if (holding) return <Card compact className="first-steps fs-compact fs-wait" label="Your first steps"><div className="k-row" aria-hidden="true"><span className="k-small"><b>Your first steps</b></span><span className="btn quiet sm fs-hold">Hide this</span></div></Card>;
  if (!shown || !view) return null;
  const dismiss = async () => {
    setBusy(true);
    try { setView(await api<View>("/me/first-steps", { method: "PUT", body: { dismissed: true } })); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const total = view.steps.length;
  if (compact) {
    const next = view.steps.find((s) => !s.done);
    return (
      <Card compact className="first-steps fs-compact" label="Your first steps">
        <div className="k-row">
          <span className="k-small"><b>Your first steps</b> · {view.done} of {total} done{next && <> · next: <Link className="link" to={next.to}>{next.title}</Link></>}</span>
          <button className="btn quiet sm" disabled={busy} onClick={dismiss}>Hide this</button>
        </div>
      </Card>
    );
  }
  return (
    <Card className="first-steps" label="Your first steps">
      <CardHead title="Your first steps" actions={<button className="btn quiet sm" disabled={busy} onClick={dismiss}>Hide this</button>} />
      <span className="k-small k-muted">{view.done} of {total} done. Each one ticks itself when you've done it.</span>
      <progress className="k-progress" aria-label="First steps done" max={total} value={view.done} />
      <ol className="fs-list">
        {view.steps.map((s) => (
          <li key={s.id} className={s.done ? "done" : ""} data-step={s.id}>
            <span className="fs-tick" aria-hidden="true">{s.done ? "✓" : ""}</span>
            {s.done ? <span className="fs-title">{s.title}<span className="sr-only"> (done)</span></span>
              : <Link className="fs-title fs-go" to={s.to}>{s.title}</Link>}
          </li>
        ))}
      </ol>
    </Card>
  );
}
