// The paths the site's host (vercel.json) forwards to the API, as a dev/preview proxy, so `vite` and `vite preview`
// behave like production: /stocks/in/TCS is the API's public company page, not the app's "Page not found".
// unit/rewrite-proxy.test.mjs checks this list against vercel.json.
import { readFileSync } from "node:fs";

/** The leading path of every rewrite whose destination is another host ("/stocks/:path*" -> "/stocks"). */
export function forwardedPaths(vercelPath = new URL("../vercel.json", import.meta.url)) {
  const { rewrites = [] } = JSON.parse(readFileSync(vercelPath, "utf8"));
  return rewrites.filter((r) => /^https?:\/\//.test(r.destination)).map((r) => r.source.replace(/\/:.*$/, ""));
}

/** vite's `proxy` option: each forwarded path (and what's under it) goes to `target`: the API the app is pointed at
 * (E2E_API in the browser tests, else STRATLAB_API, else a local API on :8000). */
export function rewriteProxy(target = process.env.E2E_API ?? process.env.STRATLAB_API ?? "http://127.0.0.1:8000", paths = forwardedPaths()) {
  return Object.fromEntries(paths.map((p) => [p, { target, changeOrigin: true }]));
}
