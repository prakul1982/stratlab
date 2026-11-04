import { useEffect, useState } from "react";

/* Help & feedback's opener and the open/closed state (the labelled button is the app shell's own, Shell.tsx) (owner, 4 Nov). Tiny, and in the shared "common" file
 * every page already downloads (vite.config.ts), so the button and the footer link cost a page nothing. Each half's root draws
 * the dialog (Feedback.tsx) with React.lazy only once it is asked for, so no page downloads it before that. */

const OPEN = "stratlab:feedback";

/** Open the feedback dialog from anywhere (a button, a link in a footer, the Help page). */
export function openFeedback() {
  window.dispatchEvent(new Event(OPEN));
}

/** Whether the dialog is asked for: openFeedback() anywhere, or an address with #feedback (a reply email, the layout checker). */
export function useFeedbackOpen(): [boolean, (v: boolean) => void] {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setOpen(true);
    const hash = () => { if (location.hash === "#feedback") setOpen(true); };
    hash();
    window.addEventListener(OPEN, on);
    window.addEventListener("hashchange", hash);
    return () => { window.removeEventListener(OPEN, on); window.removeEventListener("hashchange", hash); };
  }, []);
  return [open, setOpen];
}
