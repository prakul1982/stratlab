import { useEffect, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import { APP_BUILD } from "../lib/buildInfo";
import { Modal } from "./ui";
import { Seg } from "./kit/Seg";
import { FEEDBACK_MAX, FEEDBACK_TYPES, browserLine, type FeedbackType } from "../lib/feedback";

/* Help & feedback (owner, 4 Nov: "a help button where people can report bugs and also new features or some feature not
 * working"). One dialog for the whole app, opened from the labelled Feedback button (the menu's top on a laptop, the top bar on
 * a phone), the Help page and the public pages' footer, all through openFeedback(). What is sent with the words is only what
 * helps find the problem: the page's path, the app's version, the browser and system in a few words and the screen size; the
 * server adds the plan. Never the page's other fields, a token or anything else about the person. */

const OPEN = "stratlab:feedback";

/** Open the feedback dialog from anywhere (a button, a link in a footer, the Help page). */
export function openFeedback() {
  window.dispatchEvent(new Event(OPEN));
}

/** The labelled button that opens it: the menu's top on a laptop, the top bar on a phone. */
export function FeedbackButton({ className = "btn quiet sm" }: { className?: string }) {
  return <button type="button" className={`${className} feedback-btn`} onClick={openFeedback} title="Report something broken, or suggest a feature">Feedback</button>;
}

export type FeedbackSend = (body: Record<string, unknown>) => Promise<unknown>;

/** Drawn once at each half's root: the dialog, when something asked for it. The signed-in app passes its own request (with the
 * sign-in) and its toast; the public half a plain request, so a visitor's page loads none of the app's account code. */
export function FeedbackHost({ send, signedIn, onSent }: { send: FeedbackSend; signedIn: boolean; onSent?: (msg: string) => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setOpen(true);
    // a link can open it too: any address with #feedback (a reply email, the layout checker)
    const hash = () => { if (location.hash === "#feedback") setOpen(true); };
    hash();
    window.addEventListener(OPEN, on);
    window.addEventListener("hashchange", hash);
    return () => { window.removeEventListener(OPEN, on); window.removeEventListener("hashchange", hash); };
  }, []);
  return open ? <FeedbackDialog onClose={() => setOpen(false)} send={send} me={signedIn} notify={onSent} /> : null;
}

function FeedbackDialog({ onClose, send: post, me, notify }: { onClose: () => void; send: FeedbackSend; me: boolean; notify?: (msg: string) => void }) {
  const loc = useLocation();
  const [type, setType] = useState<FeedbackType>("broken");
  const [text, setText] = useState("");
  const [reply, setReply] = useState(false);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (text.trim().length < 5) { setError("Say a few words about what happened, so it can be found."); return; }
    setBusy(true); setError(null);
    try {
      await post({
        type, text: text.trim(), reply, ...(me ? {} : { email: reply ? email.trim() : null }),
        path: loc.pathname, version: (APP_BUILD.sha ?? "").slice(0, 12), browser: browserLine(navigator.userAgent), screen: `${innerWidth}×${innerHeight}` });
      setDone(true);
      notify?.("Thanks: your report was sent.");
    } catch (x) {
      setError((x as { message?: string })?.message || "It couldn't be sent. Try again in a moment.");
    } finally { setBusy(false); }
  };
  return (
    <Modal title="Help & feedback" onClose={onClose}>
      {done ? (
        <div className="k-stack" data-testid="feedback-done">
          <p>Thanks. Your report is with the person who builds StratLab{reply ? ", who will write back" : ""}.</p>
          <div className="k-row"><button type="button" className="btn" onClick={onClose}>Close</button></div>
        </div>
      ) : (
        <form className="k-stack feedback-form" onSubmit={send} noValidate>
          <Seg label="What is it?" options={FEEDBACK_TYPES.map(([value, label, short]) => ({ value, label, short }))} value={type} onChange={(v) => setType(v as FeedbackType)} />
          <label className="k-stack k-tight">
            <span className="k-label">What happened{type === "idea" ? ", or what would help" : ""}?</span>
            <textarea className="k-textarea" rows={5} maxLength={FEEDBACK_MAX} value={text} onChange={(x) => setText(x.target.value)} required aria-invalid={!!error || undefined}
              placeholder={type === "idea" ? "What would you like StratLab to do?" : "What did you do, what did you expect, and what happened instead?"} />
            <span className="k-note">{text.length.toLocaleString("en-IN")} of {FEEDBACK_MAX.toLocaleString("en-IN")} characters. The page you're on, the app's version, your browser and screen size are sent with it, nothing else.</span>
          </label>
          <label className="k-row k-tight"><input type="checkbox" checked={reply} onChange={(x) => setReply(x.target.checked)} /> <span>Reply to me{me ? " (at your account's email)" : ""}</span></label>
          {reply && !me && (
            <label className="k-stack k-tight">
              <span className="k-label">Your email</span>
              <input className="k-input" type="email" autoComplete="email" maxLength={200} value={email} onChange={(x) => setEmail(x.target.value)} />
            </label>
          )}
          {error && <p className="k-small k-down" role="alert">{error}</p>}
          <div className="k-row">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Sending…" : "Send"}</button>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
