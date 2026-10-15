/* Which build is running, the app's and the server's (R24-009: Admin showed neither). Pure, so the unit tests can read it. */

export type AppBuild = { sha: string | null; ref: string | null; env: string | null; built_at: string | null };
/** The server's, from /version (app/build_info.py): its commit, branch and, when the deploy says, build time; when it started. */
export type ServerBuild = { sha: string | null; short: string | null; branch: string | null; built_at: string | null; started_at: string | null;
  environment?: string | null; deployment?: string | null };

declare const __APP_BUILD__: AppBuild | undefined;
/** This bundle's build, stamped by vite.config.ts (scripts/buildStamp.mjs); empty outside a build (the unit tests, a dev server). */
export const APP_BUILD: AppBuild = typeof __APP_BUILD__ !== "undefined" ? __APP_BUILD__ : { sha: null, ref: null, env: null, built_at: null };

const when = (iso: string | null | undefined, fmt: (iso: string) => string) => (iso ? fmt(iso) : null);

/** One line for a build: "4610d78 on main, built 15 Oct 09:24 IST". `fmt` writes a time. Says plainly what isn't known. */
export function buildLine(b: { sha?: string | null; short?: string | null; branch?: string | null; ref?: string | null; built_at?: string | null;
  started_at?: string | null } | null | undefined, fmt: (iso: string) => string): string {
  if (!b) return "Not reported (an older server).";
  const sha = b.short ?? (b.sha ? b.sha.slice(0, 7) : null);
  const branch = b.branch ?? b.ref ?? null;
  const parts = [sha ? `${sha}${branch ? ` on ${branch}` : ""}` : "Commit not set by the host"];
  const built = when(b.built_at, fmt), started = when(b.started_at, fmt);
  if (built) parts.push(`built ${built}`);
  if (started) parts.push(`running since ${started}`);
  return parts.join(", ") + ".";
}
