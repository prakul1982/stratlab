// rev11d: the service worker's 5xx fallback, the browser bar colour in dark mode, and the legal pages' wording.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// runs sw.js with a fake network and cache; returns what a page load at `path` is answered with
async function load(path, { status, body = "<html>x</html>", throws = false, shell = true }) {
  const handlers = {};
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: {} };
  class Res {
    constructor(b, init = {}) { this.body = b; this.status = init.status ?? 200; this.ok = this.status < 400; this.headers = { get: (k) => (init.headers || {})[k.toLowerCase()] ?? null }; }
    clone() { return this; }
    static error() { return new Res("error", { status: 0 }); }
  }
  const server = new Res(body, { status, headers: { "content-type": "text/html" } });
  const caches = { match: async () => (shell ? new Res("APP SHELL") : undefined), open: async () => ({ put: async () => {} }) };
  vm.runInNewContext(read("public/sw.js"), { self, caches, fetch: async () => { if (throws) throw new Error("offline"); return server; }, URL, Response: Res, Promise, String });
  let answer;
  handlers.fetch({ request: { method: "GET", mode: "navigate", url: "https://stratlab.studio" + path }, respondWith: (p) => { answer = p; } });
  return { res: await answer, server };
}

test("a server 5xx on a server page is shown as it is, not replaced by the app shell", async () => {
  for (const p of ["/stocks/in/TCS", "/stocks/us/AAPL", "/c/abc"]) {
    const { res, server } = await load(p, { status: 503 });
    assert.equal(res, server, p);
  }
});

test("a server 5xx on an app address still starts the app from the shell", async () => {
  for (const p of ["/", "/mine", "/account"]) assert.equal((await load(p, { status: 503 })).res.body, "APP SHELL", p);
  assert.match((await load("/mine", { status: 503, shell: false })).res.body, /StratLab can't be reached/);
});

test("the offline page shows when the fetch itself failed and no shell stands in", async () => {
  assert.match((await load("/stocks/in/TCS", { status: 200, throws: true })).res.body, /StratLab can't be reached/);
  assert.equal((await load("/mine", { status: 200, throws: true })).res.body, "APP SHELL");
});

test("the browser bar colour follows the app's dark paper colour", () => {
  const html = read("index.html");
  assert.match(html, /name="theme-color" content="#141311" media="\(prefers-color-scheme: dark\)"/);
  assert.match(html, /name="theme-color" content="#F5F1E8" media="\(prefers-color-scheme: light\)"/);
  assert.match(read("src/styles.css"), /:root\[data-theme="dark"\] \{\s*--paper: #141311;/);
  assert.match(read("src/lib/app.tsx"), /applyThemeColor\(t\)/);
  assert.match(read("public/theme.js"), /theme-color/);
});

test("the privacy page names the Account page controls, and the terms don't promise billing that isn't open", () => {
  const legal = read("src/pages/LegalPage.tsx");
  assert.match(legal, /"Download everything" to get a copy[^]*"Delete all my data"[^]*PrivacyMail/);
  assert.match(legal, /Paid plans are billed only once they are on sale; the Plans page shows whether they are\./);
});

test("the legal pages' last-updated dates agree across the page, seo.ts and the sitemap", () => {
  const legal = read("src/pages/LegalPage.tsx"), seo = read("src/content/seo.ts"), py = readFileSync(new URL("../../backend/app/site_pages.py", import.meta.url), "utf8");
  const months = { January: "01", February: "02", March: "03", April: "04", May: "05", June: "06", July: "07", August: "08", September: "09", October: "10", November: "11", December: "12" };
  for (const [path, d, m, y] of [...legal.matchAll(/"(\/\w+)": "(\d+) (\w+) (\d+)"/g)].map((x) => [x[1], x[2], x[3], x[4]])) {
    const iso = `${y}-${months[m]}-${d.padStart(2, "0")}`;
    assert.match(seo, new RegExp(`path: "${path}"[^]*?updated: "${iso}"`), path);
    assert.match(py, new RegExp(`\\("${path}", "${iso}"\\)`), path);
  }
});
