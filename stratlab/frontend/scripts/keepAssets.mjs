// Old builds' page code kept beside the new one (owner, 5 Nov: "I have to click a button 10 times and reload 10 times"). Every
// build names its files by their content, and the host serves only the newest build: a tab opened before a deploy asks for
// /assets/<old name>.js when a page or dialog is first opened, gets a 404, and fails until it is reloaded. Five deploys in a day
// made that a constant. So a production build on the host downloads the files the live site lists in /asset-list.json and that
// this build doesn't have, and serves them too, for KEEP_DAYS after they stopped being current. Nothing here can fail a build:
// a file that can't be fetched is left out, and the page's own retry and reload still cover it.
//
//   node scripts/keepAssets.mjs            (after `vite build`; does nothing unless VERCEL_ENV=production or KEEP_ASSETS_FROM is set)
import { readdir, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

export const KEEP_DAYS = 7;
export const MAX_FILES = 1500;             // a bound on what is carried: a few builds' worth (one build is ~300 files)
export const MAX_BYTES = 60 * 1024 * 1024; // and on its size
const NAME = /^[\w.-]{1,120}\.(?:js|css|mjs|woff2?|svg|png|webp|json|map)$/;

/** What this build should carry from the last one: {fetch: [names to download], kept: {name: ISO day it stopped being current}}.
 * `prev` is the live /asset-list.json ({files, kept}); `current` the names this build made. A name current in the last build
 * and not in this one starts its KEEP_DAYS today; one already kept keeps its date; one older than KEEP_DAYS is dropped. */
export function plan(prev, current, now = new Date()) {
  const have = new Set(current);
  const cutoff = now.getTime() - KEEP_DAYS * 86400_000;
  const today = now.toISOString();
  const kept = {};
  const add = (name, since) => {
    if (typeof name !== "string" || !NAME.test(name) || have.has(name) || name in kept) return;
    const t = Date.parse(since);
    if (!Number.isFinite(t) || t < cutoff || t > now.getTime() + 86400_000) return;
    kept[name] = new Date(t).toISOString();
  };
  for (const name of Array.isArray(prev?.files) ? prev.files : []) add(name, today);
  const old = prev && typeof prev.kept === "object" && prev.kept ? prev.kept : {};
  for (const [name, since] of Object.entries(old)) add(name, since);
  const names = Object.keys(kept).sort((a, b) => kept[b].localeCompare(kept[a]) || a.localeCompare(b)).slice(0, MAX_FILES);
  return { fetch: names, kept: Object.fromEntries(names.map((n) => [n, kept[n]])) };
}

async function get(url, ms = 15000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { "user-agent": "StratLab build" } });
    return r.ok ? r : null;
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

/** A live site from before this script (no /asset-list.json yet): the files its page names, and every file those scripts
 * name in turn (each page's chunk is named by the script that opens it). */
export function namesIn(text) {
  // "/assets/x.js" in the page; "./x.js" between the scripts themselves (they sit side by side in /assets)
  return [...new Set([...String(text).matchAll(/(?:(?:^|[/"'`(])assets\/|["'`(]\.\/)([\w.-]{1,120}\.(?:js|css))/g)].map((m) => m[1]))];
}

async function listed(from) {
  const page = await get(`${from}/`);
  if (!page) return null;
  const names = new Set(namesIn(await page.text()));
  const queue = [...names].filter((x) => x.endsWith(".js"));
  const seen = new Set();
  while (queue.length && seen.size < MAX_FILES) {           // every script the page can reach, a few at a time
    const batch = queue.splice(0, 8).filter((n) => !seen.has(n));
    batch.forEach((n) => seen.add(n));
    await Promise.all(batch.map(async (n) => {
      const r = await get(`${from}/assets/${n}`);
      if (!r || (r.headers.get("content-type") || "").includes("text/html")) return;
      for (const m of namesIn(await r.text())) {
        if (!names.has(m)) { names.add(m); if (m.endsWith(".js")) queue.push(m); }
      }
    }));
  }
  return names.size ? { files: [...names], kept: {} } : null;
}

export async function main(env = process.env, dist = path.resolve("dist")) {
  const assets = path.join(dist, "assets");
  const current = (await readdir(assets).catch(() => [])).filter((n) => NAME.test(n));
  const from = String(env.KEEP_ASSETS_FROM || (env.VERCEL_ENV === "production" ? "https://stratlab.studio" : "")).replace(/\/+$/, "");
  let carried = {};
  if (from) {
    const res = await get(`${from}/asset-list.json`);
    const prev = (res ? await res.json().catch(() => null) : null) ?? await listed(from);
    const { fetch: names, kept } = plan(prev, current);
    let bytes = 0;
    await mkdir(assets, { recursive: true });
    for (let i = 0; i < names.length; i += 8) {
      await Promise.all(names.slice(i, i + 8).map(async (name) => {
        if (bytes > MAX_BYTES) return;
        const r = await get(`${from}/assets/${name}`);
        const type = r?.headers.get("content-type") || "";
        if (!r || type.includes("text/html")) return;          // a 404 page is never kept as a script
        const buf = Buffer.from(await r.arrayBuffer());
        bytes += buf.length;
        if (bytes > MAX_BYTES) return;
        await writeFile(path.join(assets, name), buf);
        carried[name] = kept[name];
      }));
    }
    console.log(`keepAssets: ${Object.keys(carried).length} of ${names.length} files from earlier builds kept (${Math.round(bytes / 1024)} KB)`);
  }
  await writeFile(path.join(dist, "asset-list.json"), JSON.stringify({ files: current.sort(), kept: carried }));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.log("keepAssets: skipped,", String(e?.message || e).slice(0, 200)); });
}
