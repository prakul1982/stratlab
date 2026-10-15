import { CFG } from "./config";
import { hasSavedSession } from "./entry";
import { rememberNext, returnPathFor } from "./returnTo";

/** This browser already has a saved sign-in. A shared page (a library strategy, a verdict) is a visitor's page even then, so
 * it asks this before offering "Sign in" or "Continue with Google" to someone who is signed in. */
export const signedInHere = (): boolean => { try { return hasSavedSession(CFG.SUPABASE_URL, localStorage); } catch { return false; } };

/** Starts downloading the sign-in library ahead of a click, so "Sign in" answers at once (R31-009: it did nothing for ~3 s while that
 * download ran). A failed head start is ignored; signIn() asks again. */
export const warmSignIn = (): void => { void import("./api").catch(() => undefined); };

/** Sign in with Google, then open `next` (left out: the page the visitor is on now, unless that's the landing page).
 * Google comes back to the site's root, which is on Supabase's list of allowed return addresses; the page itself is
 * kept in this browser (lib/returnTo.ts) and opened once the session starts, so no address goes through the URL.
 * The sign-in library loads now, when it is first needed, so a visitor who only reads the page never downloads it. */
export async function signIn(next?: string | null) {
  rememberNext(next === undefined ? returnPathFor(location.pathname, location.search, location.hash) : next);
  const { supabase } = await import("./api");
  return supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
}
