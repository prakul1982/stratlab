import { lazy, Suspense, useEffect, useState } from "react";
import type { FeedbackSend } from "./Feedback";

/* Help & feedback's opener, the labelled button and the host (owner, 4 Nov). Small, and in the shared "common" file every page
 * already downloads (vite.config.ts), so the button and the footer link cost a page nothing; the dialog (Feedback.tsx) is
 * downloaded only when someone opens it. */

const OPEN = "stratlab:feedback";
const Dialog = lazy(() => import("./Feedback"));

/** Open the feedback dialog from anywhere (a button, a link in a footer, the Help page). */
export function openFeedback() {
  window.dispatchEvent(new Event(OPEN));
}

/** The labelled button that opens it: the menu's top on a laptop, the top bar on a phone. */
export function FeedbackButton({ className = "btn quiet sm" }: { className?: string }) {
  return <button type="button" className={`${className} feedback-btn`} onClick={openFeedback} title="Report something broken, or suggest a feature">Feedback</button>;
}

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
  return open ? <Suspense fallback={null}><Dialog onClose={() => setOpen(false)} send={send} me={signedIn} notify={onSent} /></Suspense> : null;
}
