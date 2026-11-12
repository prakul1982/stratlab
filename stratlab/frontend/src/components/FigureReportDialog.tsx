import { useMemo, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { APP_BUILD } from "../lib/buildInfo";
import { browserLine, FEEDBACK_MAX } from "../lib/feedback";
import { figureChoice, pageName } from "../lib/figureReport";
import { Dialog } from "./kit/Dialog";
import { Select } from "./kit/Form";
import type { FigureDetail } from "./kit/ReportFigure";
import "./figureReport.css";

/* The "Report an error" dialog (owner, 12 Nov), opened from the flag beside a figure: the page, the figure, its value, period and source
 * filled in, the person adds what looks wrong and sends. It goes to Admin → Feedback as a data error; when it is marked fixed the person
 * gets a note in the app. Downloaded only when opened (FigureReportHost). */
export default function FigureReportDialog({ detail, signedIn, onClose, notify }: { detail: FigureDetail; signedIn: boolean; onClose: () => void; notify?: (m: string) => void }) {
  const loc = useLocation();
  const page = useMemo(() => pageName(document), []);
  const choices = detail.choices ?? [];
  const [pick, setPick] = useState(() => figureChoice(choices).index);
  const fig = figureChoice(choices, pick);
  const label = fig.column && !fig.period ? `${detail.label} · ${fig.column}` : detail.label;
  const value = fig.value ?? detail.value ?? "";
  const period = fig.period ?? detail.period ?? "";
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const where = [page, detail.section].filter(Boolean).join(" · ");
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (text.trim().length < 3) { setError("Say what looks wrong, in a few words."); return; }
    setBusy(true); setError(null);
    try {
      await api("/feedback/figure", { method: "POST", body: {
        text: text.trim(), path: loc.pathname, section: where.slice(0, 120), label: label.slice(0, 160), value: value.slice(0, 80), period: period.slice(0, 60),
        source: (detail.source ?? "").slice(0, 160), version: (APP_BUILD.sha ?? "").slice(0, 12), browser: browserLine(navigator.userAgent), screen: `${innerWidth}×${innerHeight}` } });
      setDone(true);
      notify?.("Thanks: the figure was reported.");
    } catch (x) {
      setError((x as { message?: string })?.message || "It couldn't be sent. Try again in a moment.");
    } finally { setBusy(false); }
  };
  if (!signedIn) {
    return (
      <Dialog title="Report an error" onClose={onClose}>
        <div className="k-stack" data-testid="figure-report-signin">
          <p>Sign in to report an error in a figure. We reply in the app when it's checked.</p>
          <div className="k-row"><Link className="btn" to={`/login?next=${encodeURIComponent(loc.pathname)}`}>Sign in to report</Link>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button></div>
        </div>
      </Dialog>
    );
  }
  return (
    <Dialog title="Report an error" onClose={onClose}>
      {done ? (
        <div className="k-stack" data-testid="figure-report-done">
          <p>Thanks. The figure is on the list to check, and you'll get a note here in the app when it's fixed.</p>
          <div className="k-row"><button type="button" className="btn" onClick={onClose}>Close</button></div>
        </div>
      ) : (
        <form className="k-stack figure-report" onSubmit={send} noValidate>
          {where && <p className="k-small k-muted" data-testid="figure-report-where">{where}</p>}
          <dl className="figure-report-facts">
            <div><dt className="k-label">Figure</dt><dd data-testid="figure-report-figure"><b>{label}</b>{period ? `, ${period}` : ""}{value ? `: ${value}` : ""}</dd></div>
            {detail.source && <div><dt className="k-label">Source</dt><dd>{detail.source}</dd></div>}
          </dl>
          {choices.length > 1 && (
            <div className="k-stack k-tight">
              <span className="k-label" aria-hidden="true">Which figure?</span>
              <Select value={pick} onChange={(v) => setPick(Number(v))} label="Which figure?" options={choices.map(([c, v], i) => ({ value: i, label: `${c}: ${v}` }))} />
            </div>
          )}
          <label className="k-stack k-tight">
            <span className="k-label">What looks wrong?</span>
            <textarea className="k-textarea" rows={4} maxLength={FEEDBACK_MAX} value={text} onChange={(x) => setText(x.target.value)} required aria-invalid={!!error || undefined}
              placeholder="For example: the annual report says 17.9%." />
            <span className="k-note">The page, the figure and its source are sent with your note, nothing else. We reply here in the app when it's checked.</span>
          </label>
          {error && <p className="k-small k-down" role="alert">{error}</p>}
          <div className="k-row">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Sending…" : "Send"}</button>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
