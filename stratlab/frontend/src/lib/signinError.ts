/* Google sends a refused or failed sign-in back to the site with `?error=…` or `#error=…` (and an error_description) in
 * the address. This turns that into one plain sentence for the landing page to show, or null when the address carries no
 * such problem. No imports: unit/signin-error.test.mjs reads it as it is. */

export function signInProblem(search: string, hash: string): string | null {
  const p = new URLSearchParams(`${search.replace(/^\?/, "")}&${hash.replace(/^#/, "")}`);
  const code = (p.get("error") || p.get("error_code") || "").toLowerCase();
  const text = (p.get("error_description") || "").replace(/\s+/g, " ").trim().slice(0, 160);
  if (!code && !text) return null;
  if (code === "access_denied" || /access.denied|cancel/i.test(text))
    return "You're not signed in: Google sign-in was cancelled or wasn't allowed. Choose Continue with Google to try again.";
  if (/exchange external code|server_error|temporarily_unavailable/i.test(`${code} ${text}`))
    return "Google sign-in couldn't finish on our side. Try again in a moment, and write to us from the Contact page if it keeps happening.";
  return text ? `Sign-in didn't finish: ${text.replace(/[.\s]*$/, "")}. Choose Continue with Google to try again.` : "Sign-in didn't finish. Choose Continue with Google to try again.";
}
