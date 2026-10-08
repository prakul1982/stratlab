import { rememberNext, returnPathFor } from "./returnTo";

/** Sign in with Google, then open `next` (left out: the page the visitor is on now, unless that's the landing page).
 * Google comes back to the site's root, which is on Supabase's list of allowed return addresses; the page itself is
 * kept in this browser (lib/returnTo.ts) and opened once the session starts, so no address goes through the URL.
 * The sign-in library loads now, when it is first needed, so a visitor who only reads the page never downloads it. */
export async function signIn(next?: string | null) {
  rememberNext(next === undefined ? returnPathFor(location.pathname, location.search, location.hash) : next);
  const { supabase } = await import("./api");
  return supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
}
