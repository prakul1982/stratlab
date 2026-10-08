/* The Connection check's wording. A person sees plain words about what works; the server's address and the hosting
 * steps (Railway, environment variables) are for admins only. */

export type CheckLine = { s: "pass" | "fail" | "warn"; d: string };

/** The "StratLab server" row: reachable or not. Only an admin sees the address and what to fix. */
export function serverRow(reachable: boolean, isAdmin: boolean, apiBase: string): CheckLine {
  if (reachable) return { s: "pass", d: isAdmin ? apiBase.replace(/^https?:\/\//, "") : "Online" };
  return { s: "fail", d: isAdmin
    ? "Can't reach the server. Check the Railway service is running and FRONTEND_ORIGIN lists this site."
    : "Can't reach StratLab right now. Check your connection and try again in a minute." };
}

/** The "AI strategy builder" row when the server has no AI key. A person is told what still works (and it is not a
 * "Problem": they can do nothing about it); an admin is told which variable to set. */
export function aiMissingRow(isAdmin: boolean): CheckLine {
  return isAdmin
    ? { s: "fail", d: "No AI key on the server, so the simple converter is used. Add a free GROQ_API_KEY (console.groq.com) in Railway → Variables, then redeploy." }
    : { s: "warn", d: "Using the simple converter right now. Describing ideas still works." };
}
