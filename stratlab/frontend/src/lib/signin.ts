import { CFG } from "./config";
import { hasSavedSession } from "./entry";
import { rememberNext, returnPathFor } from "./returnTo";

/** This browser already has a saved sign-in. A shared page (a library strategy, a verdict) is a visitor's page even then, so
 * it asks this before offering "Sign in" or "Continue with Google" to someone who is signed in. */
export const signedInHere = (): boolean => { try { return hasSavedSession(CFG.SUPABASE_URL, localStorage); } catch { return false; } };

/** Starts downloading the sign-in library when someone reaches for "Sign in" (pointer over it, focus, touch), so the click answers
 * at once (R31-009: it did nothing for ~3 s while that download ran). Never on page load: a visitor who doesn't sign in never
 * downloads it (R5V-020, R8V-013). A failed head start is ignored; signIn() asks again. */
export const warmSignIn = (): void => { void import("./api").catch(() => undefined); };

/** Sign in with Google, then open `next` (left out: the page the visitor is on now, unless that's the landing page).
 * Google comes back to the site's root, which is on Supabase's list of allowed return addresses; the page itself is
 * kept in this browser (lib/returnTo.ts) and opened once the session starts, so no address goes through the URL.
 * The sign-in library loads now, when it is first needed, so a visitor who only reads the page never downloads it. */
export async function signIn(next?: string | null) {
  clearSignInEnded();
  rememberNext(next === undefined ? returnPathFor(location.pathname, location.search, location.hash) : next);
  const { supabase } = await import("./api");
  return supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
}

/* A sign-in the server turned down in the middle of a visit (a 401 on a read: the sign-in ended or was signed out elsewhere) is
 * remembered for this browser tab, so the sign-in page can say "You were signed out" and not look like a first visit (RC7-009). */
const ENDED = "stratlab.signin-ended";
export const noteSignInEnded = (): void => { try { sessionStorage.setItem(ENDED, "1"); } catch { /* storage off: the page just doesn't say it */ } };
export const signInEnded = (): boolean => { try { return sessionStorage.getItem(ENDED) === "1"; } catch { return false; } };
export const clearSignInEnded = (): void => { try { sessionStorage.removeItem(ENDED); } catch { /* storage off */ } };
