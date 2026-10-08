// The paths the site's host (vercel.json) forwards to the API, as a dev/preview proxy, so `vite` and `vite preview`
// behave like production: /stocks/in/TCS is the API's public company page, not the app's "Page not found".
// unit/rewrite-proxy.test.mjs checks this list against vercel.json.
import { readFileSync } from "node:fs";

/** The source of every rewrite whose destination is another host ("/stocks/:path*", "/v/:token", "/sitemap.xml"). */
export function forwardedPaths(vercelPath = new URL("../vercel.json", import.meta.url)) {
  const { rewrites = [] } = JSON.parse(readFileSync(vercelPath, "utf8"));
  return rewrites.filter((r) => /^https?:\/\//.test(r.destination)).map((r) => r.source);
}

/** A rewrite source as a pattern that matches whole paths only: "/c/:token" is "/c/abc" but not "/config.js"; "/stocks/:path*"
 * is "/stocks" and anything under it. (A plain prefix key would send /config.js and /verdict/... to the API.) */
export function sourceRegex(source) {
  const body = source
    .replace(/[.+?^${}()|[\]\\]/g, "\\$&")
    .replace(/\/:[A-Za-z_]+\*/g, "(?:/.*)?")
    .replace(/:[A-Za-z_]+/g, "[^/]+");
  return `^${body}/?$`;
}

/** vite's `proxy` option: a key starting with ^ is a pattern. Each forwarded path goes to `target`: the API the app is
 * pointed at (E2E_API in the browser tests, else STRATLAB_API, else a local API on :8000). */
export function rewriteProxy(target = process.env.E2E_API ?? process.env.STRATLAB_API ?? "http://127.0.0.1:8000", sources = forwardedPaths()) {
  return Object.fromEntries(sources.map((s) => [sourceRegex(s), { target, changeOrigin: true }]));
}
