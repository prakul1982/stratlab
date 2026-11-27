/* The sign-in page's email form's code (components/EmailSignIn.tsx), kept apart so the pages that open the sign-in page (a plan card's
 * "Sign in with email" button, components/EmailWay.tsx) can ask for it before they go there: LIVE17B-002, the sign-in page opened from a
 * plan card was drawn for 0.3-0.45 s with an empty band where the form goes, while its code downloaded. Once here it is drawn straight
 * away (pages/Login.tsx reads emailFormNow). */
import { importWithRetry } from "./lazyRetry";

type Mod = typeof import("../components/EmailSignIn");
let mod: Mod | null = null;
let asked: Promise<Mod> | null = null;
let settled: Promise<unknown> = Promise.resolve();

/** The form's code if it has arrived, else null. */
export const emailFormNow = (): Mod | null => mod;

/** Ask for the form's code (once); resolves with it. */
export function loadEmailForm(): Promise<Mod> {
  if (!asked) {
    asked = importWithRetry(() => import("../components/EmailSignIn")).then((m) => { mod = m; return m; });
    settled = asked.catch(() => { asked = null; });
  }
  return asked;
}

/** Wait for the form's code at most `ms` (a slow network still opens the page, the form then filling its slot as before). */
export const emailFormWithin = (ms: number): Promise<unknown> =>
  Promise.race([loadEmailForm().catch(() => undefined), new Promise((ok) => setTimeout(ok, ms))]);

/** One promise per download, settled once the form's code has arrived or its download failed (it never rejects): what the sign-in page waits
 * on when it is opened for its email form before the code is here (fix98), so a failed download still draws the page. */
export const emailFormSettled = (): Promise<unknown> => (loadEmailForm(), settled);
