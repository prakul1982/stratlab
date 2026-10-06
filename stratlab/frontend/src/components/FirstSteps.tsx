import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { Card, CardHead } from "./kit";

type Step = { id: string; title: string; to: string; done: boolean };
type View = { show: boolean; dismissed: boolean; done: number; steps: Step[] };

/** Home's first-steps checklist for a new account. Each step ticks itself from what the user has really done; the
 *  list hides for good when dismissed, and by itself once every step is done. */
export function FirstSteps() {
  const { fail } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api<View>("/me/first-steps").then((v) => { if (live && v && Array.isArray(v.steps)) setView(v); }).catch(() => undefined);
    return () => { live = false; };
  }, []);

  if (!view?.show) return null;
  const dismiss = async () => {
    setBusy(true);
    try { setView(await api<View>("/me/first-steps", { method: "PUT", body: { dismissed: true } })); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const total = view.steps.length;
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
