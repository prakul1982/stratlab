/* Google sends a refused or failed sign-in back to the site with `?error=…` or `#error=…` (and an error_description) in
 * the address. This turns that into one plain sentence for the landing page to show, or null when the address carries no
 * such problem. No imports: unit/signin-error.test.mjs reads it as it is. */

/** A sign-in that came back but couldn't be completed (lib/signin.ts signInUnfinished: a one-time code the service wouldn't
 * trade, a spent emailed link). The address no longer carries anything by then, so this is the sentence (LIVE3-009). */
export const UNFINISHED_SIGNIN = "That sign-in didn't finish, so you're not signed in. This happens when sign-in starts in one browser or app and ends in another, or the link was used already. Choose Continue with Google to try again.";

export function signInProblem(search: string, hash: string, unfinished = false): string | null {
  const p = new URLSearchParams(`${search.replace(/^\?/, "")}&${hash.replace(/^#/, "")}`);
  const code = (p.get("error") || p.get("error_code") || "").toLowerCase();
  const text = (p.get("error_description") || "").replace(/\s+/g, " ").trim().slice(0, 160);
  if (!code && !text) return unfinished ? UNFINISHED_SIGNIN : null;
  if (code === "access_denied" || /access.denied|cancel/i.test(text))
    return "You're not signed in: Google sign-in was cancelled or wasn't allowed. Choose Continue with Google to try again.";
  if (/exchange external code|server_error|temporarily_unavailable/i.test(`${code} ${text}`))
    return "Google sign-in couldn't finish on our side. Try again in a moment, and write to us from the Contact page if it keeps happening.";
  return text ? `Sign-in didn't finish: ${text.replace(/[.\s]*$/, "")}. Choose Continue with Google to try again.` : "Sign-in didn't finish. Choose Continue with Google to try again.";
}
