import { CFG } from "./config";
import { hasSavedSession } from "./entry";
import { configOn } from "./flags";
import { rememberNext, returnPathFor } from "./returnTo";

/** This browser already has a saved sign-in. A shared page (a library strategy, a verdict) is a visitor's page even then, so
 * it asks this before offering "Sign in" or "Continue with Google" to someone who is signed in. */
export const signedInHere = (): boolean => { try { return hasSavedSession(CFG.SUPABASE_URL, localStorage); } catch { return false; } };

/** Starts downloading the sign-in library when someone reaches for "Sign in" (pointer over it, focus, touch), so the click answers
 * at once (R31-009: it did nothing for ~3 s while that download ran). Never on page load: a visitor who doesn't sign in never
 * downloads it (R5V-020, R8V-013). A failed head start is ignored; signIn() asks again. */
export const warmSignIn = (): void => { void import("./api").catch(() => undefined); };

/** Keep the page to open after sign-in: `next`, else the page the visitor is on. On the sign-in page itself (/login, /signup) the page
 * that sent them there is already kept (startSignIn), so it is left as it is. */
function keepNext(next?: string | null) {
  if (next === undefined && /^\/(login|signup)\/?$/.test(location.pathname)) return;
  rememberNext(next === undefined ? returnPathFor(location.pathname, location.search, location.hash) : next);
}

/** Sign in with Google, then open `next` (left out: the page the visitor is on now, unless that's the landing page).
 * Google comes back to the site's root, which is on Supabase's list of allowed return addresses; the page itself is
 * kept in this browser (lib/returnTo.ts) and opened once the session starts, so no address goes through the URL.
 * The sign-in library loads now, when it is first needed, so a visitor who only reads the page never downloads it. */
export async function signIn(next?: string | null) {
  clearSignInEnded();
  keepNext(next);
  const { supabase } = await import("./api");
  return supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
}

/** Email sign-in is switched on in /config.js (EMAIL_SIGNIN): off, every sign-in is Google's, as before, and no email option is drawn,
 * so the site ships safely before the sign-in service's email provider is set up. */
export const emailSignInOn = (): boolean => configOn(CFG.EMAIL_SIGNIN);

/** A "Sign in" button with no provider in its words: with email sign-in on, the sign-in page with both ways in (Google and email);
 * otherwise straight to Google, as before. The page to come back to is kept the same way either way. */
export function startSignIn(next?: string | null) {
  if (!emailSignInOn()) return signIn(next);
  clearSignInEnded();
  keepNext(next);
  location.assign("/login");
  return Promise.resolve();
}

/** Email the address a one-time sign-in code with a link (the sign-in service sends it; the same account as Google for the same
 * address, made on first use). The page to open afterwards is kept as for Google. Returns the service's error, if any. */
export async function sendEmailCode(email: string, next?: string | null): Promise<{ error: unknown }> {
  clearSignInEnded();
  keepNext(next);
  const { supabase } = await import("./api");
  const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + "/", shouldCreateUser: true } });
  return { error };
}

/** Trade the emailed code for a session (saved in this browser like Google's). Returns the service's error, if any. */
export async function verifyEmailCode(email: string, token: string): Promise<{ error: unknown }> {
  const { supabase } = await import("./api");
  const { data, error } = await supabase.auth.verifyOtp({ email, token, type: "email" });
  return { error: error ?? (data?.session ? null : new Error("no session")) };
}

/* A sign-in the server turned down in the middle of a visit (a 401 on a read: the sign-in ended or was signed out elsewhere) is
 * remembered for this browser tab, so the sign-in page can say "You were signed out" and not look like a first visit (RC7-009). */
const ENDED = "stratlab.signin-ended";
export const noteSignInEnded = (): void => { try { sessionStorage.setItem(ENDED, "1"); } catch { /* storage off: the page just doesn't say it */ } };
export const signInEnded = (): boolean => { try { return sessionStorage.getItem(ENDED) === "1"; } catch { return false; } };
export const clearSignInEnded = (): void => { try { sessionStorage.removeItem(ENDED); sessionStorage.removeItem(UNFINISHED); } catch { /* storage off */ } };

/* A sign-in that came back to the site but couldn't be completed: Google's one-time code the service wouldn't trade (sign-in
 * started in one browser or app and ended in another, or the code was used already), or a spent emailed link. Remembered for
 * this tab so whichever page opens says so, with Continue with Google beside it, instead of a silent sign-in wall
 * (LIVE3-009). Cleared when sign-in starts again or succeeds. */
const UNFINISHED = "stratlab.signin-unfinished";
export const noteSignInUnfinished = (): void => { try { sessionStorage.setItem(UNFINISHED, "1"); } catch { /* storage off */ } };
export const signInUnfinished = (): boolean => { try { return sessionStorage.getItem(UNFINISHED) === "1"; } catch { return false; } };
