import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { APIRequestContext } from "@playwright/test";

// UI-LINT: what the pages are filled with and which pages there are. The fake world (backend/tests/visual_server.py) already
// holds the owner's holdings, a tradebook and tax P&L, IPOs, breadth, positioning and so on; this adds what a real Pro user has
// that the world does not: a mutual fund statement, net worth entries, other income, US trades, notebooks with experiments, a
// paper session, alerts, a watchlist and Money calendar dates. Everything goes through the app's own API, as the Pro (admin)
// test user, so the pages are drawn full, not as empty states.
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
export const WEB = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? 5599}`;
const admin = { Authorization: "Bearer admin-token" };
export const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

const EMA = { name: "Trend follower", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
  risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
const RSI = { name: "RSI dip", tf: "1d", entry: [{ l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 30 } }],
  exit: [{ l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 60 } }],
  risk: { capital: 10000, riskPct: 2, sl: 5, tgt: 10, brokerage: 0, slippage: 0.05 } };

export interface Route { path: string; label: string; signedIn: boolean; space?: string }
export interface World { routes: Route[]; notes: string[] }

/** Seeds the Pro user's data and returns the routes to visit. A seed that fails is noted in the report, never fatal. */
export async function seedWorld(request: APIRequestContext): Promise<World> {
  const notes: string[] = [];
  const call = async (what: string, method: "post" | "put" | "delete", path: string, data?: object): Promise<any> => {
    try {
      const r = await request[method](API + path, { headers: admin, data, timeout: 120_000 });
      const said = r.ok() ? "" : await r.text();
      if (!r.ok() && (r.status() === 409 || /already/.test(said))) return null;               // a re-run on the same world: it is there already
      if (!r.ok()) { notes.push(`seed "${what}" failed: ${r.status()} ${said.slice(0, 120)}`); return null; }
      return await r.json().catch(() => ({}));
    } catch (e) { notes.push(`seed "${what}" failed: ${String(e).slice(0, 120)}`); return null; }
  };
  await call("prefs", "put", "/me/prefs", { level: "some", focus: "both" });             // no welcome questions

  // notebooks with experiments, a paper session (the run's own: earlier runs' are cleared, so the menu's list stays the same)
  try {
    const old = await (await request.get(`${API}/notebooks`, { headers: admin })).json();
    for (const n of Array.isArray(old) ? old : []) await request.delete(`${API}/notebooks/${n.id}`, { headers: admin });
  } catch { /* nothing to clear */ }
  const nb = await call("notebook", "post", "/notebooks", { name: "Trend follower on Bitcoin", question: "Does the 10/30 EMA cross work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" });
  const nb2 = await call("notebook 2", "post", "/notebooks", { name: "RSI dip on Reliance", question: "Does buying an oversold dip pay?", strategy: RSI, instrument: "IN:1206" });
  for (const [id, days] of [[nb?.id, 1500], [nb?.id, 800], [nb2?.id, 900]] as const) if (id) await call("experiment", "post", `/notebooks/${id}/experiments`, { days });
  try {            // earlier runs' sessions would fill the plan's limit of running sessions
    const live = await (await request.get(`${API}/live/sessions`, { headers: admin })).json();
    for (const x of Array.isArray(live) ? live : live?.sessions ?? []) if (x?.id) await request.post(`${API}/live/sessions/${x.id}/stop`, { headers: admin });
  } catch { /* none to stop */ }
  const paper = await call("paper session", "post", "/live/sessions", { strategy: EMA, instrument: "CRYPTO:BTC-USD" });

  // alerts, watchlist
  await call("alert 1", "post", "/alerts", { region: "IN", symbol: "RELIANCE", kind: "price", op: "above", value: 3500 });
  await call("alert 2", "post", "/alerts", { region: "IN", symbol: "TCS", kind: "move", op: "down", value: 3 });
  await call("alert 3", "post", "/alerts", { region: "US", symbol: "AAPL", kind: "price", op: "below", value: 150, repeat: true });
  await call("watchlist", "put", "/research/watchlist", { items: ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC"].map((symbol) => ({ region: "IN", symbol })).concat([{ region: "US", symbol: "AAPL" }, { region: "US", symbol: "MSFT" }]) });

  // mutual funds (the synthetic statement), net worth entries of each kind, a loan
  try {
    const cas = readFileSync(resolve(ROOT, "backend/tests/fixtures/mf/synthetic_cas.pdf")).toString("base64");
    await call("mutual fund statement", "post", "/money/mutual-funds/import", { filename: "cas.pdf", data: cas, password: "ABCDE1234F", mode: "replace" });
  } catch (e) { notes.push(`seed "mutual fund statement" failed: ${String(e).slice(0, 100)}`); }
  await call("net worth reset", "delete", "/money/net-worth");
  const items: object[] = [
    { kind: "epf", name: "EPF", balance: 850000, monthly: 12000, rate: 8.25 }, { kind: "ppf", name: "PPF", balance: 400000, yearly: 150000, rate: 7.1 },
    { kind: "nps", name: "NPS", tier1: 300000, tier2: 50000 }, { kind: "fd", name: "Bank FD", principal: 500000, rate: 7, compounding: "quarterly", start: "2026-01-01", maturity: "2027-06-01" },
    { kind: "gold", name: "Gold coins", grams: 50, purity: 24 }, { kind: "property", name: "Flat", value: 7500000 }, { kind: "cash", name: "Savings account", value: 243481.78 },
    { kind: "crypto", name: "Bitcoin", value: 120000 },
    { kind: "loan", loan_type: "home", lender: "Example Bank", principal: 5000000, rate: 8.5, tenure_months: 240, start: "2024-04-01", benchmark: "repo", reset_months: 3, last_reset: "2026-07-01", current_rate: 7.65 },
    { kind: "policy", name: "Term cover", policy_type: "term", insurer: "Example Life", sum_assured: 10000000, premium: 18000, frequency: "yearly" },
  ];
  for (const it of items) await call(`net worth ${(it as any).kind}`, "post", "/money/net-worth/items", it);

  // tax: other income for each year, TDS and advance tax, US trades; money calendar
  for (const fy of [2024, 2025, 2026]) await call(`tax inputs ${fy}`, "put", "/tax/inputs", { fy, regime: "new", other: 1200000, salary: 900000, deductions: 0, age: "below60", resident: true });
  await call("advance tax", "put", "/money/advance-tax", { fy: 2025, tds: 2000, paid: [{ d: "2025-12-12", amount: 4000 }] });
  await call("us trade buy", "post", "/money/us-tax/trades", { d: "2023-03-01", side: "B", sym: "AAPL", qty: 3, price: 150, fees: 1 });
  await call("us trade buy 2", "post", "/money/us-tax/trades", { d: "2024-02-01", side: "B", sym: "MSFT", qty: 2, price: 400, fees: 1 });
  await call("us trade sell", "post", "/money/us-tax/trades", { d: "2025-05-02", side: "S", sym: "AAPL", qty: 2, price: 190, fees: 1 });
  const day = (n: number) => { const d = new Date(Date.now() + n * 864e5); return d.toISOString().slice(0, 10); };
  await call("calendar 1", "post", "/money/calendar/events", { date: day(3), title: "Rent goes up", amount: 52000, repeat: "none" });
  await call("calendar 2", "post", "/money/calendar/events", { date: day(9), title: "Insurance premium", amount: 18000, repeat: "yearly" });
  await call("calendar 3", "post", "/money/calendar/events", { date: day(20), title: "School fees", amount: 40000, repeat: "none" });

  // ---- the routes ------------------------------------------------------------------------------------------------------------------------------
  const nav = readFileSync(resolve(ROOT, "frontend/src/lib/nav.ts"), "utf8");
  const navPaths = Array.from(new Set(Array.from(nav.matchAll(/\bpage\("([^"]+)"/g)).map((m) => m[1])));
  const groups: string[] = [];
  const spaceOf = new Map<string, string>();                 // the menu a page shows: its own space's (the menu follows the page)
  for (const [space, rx] of [["trade", /trade: \{[\s\S]*?(?=\n  invest: \{)/], ["invest", /invest: \{[\s\S]*?(?=\n  money: \{)/], ["money", /money: \{[\s\S]*$/]] as const) {
    const block = (nav.match(rx) || [""])[0];
    for (const m of block.matchAll(/\{ id: "([a-z-]+)", label:/g)) { groups.push(`/${space}/g/${m[1]}`); spaceOf.set(`/${space}/g/${m[1]}`, space); }
    for (const m of block.matchAll(/\bpage\("([^"]+)"/g)) spaceOf.set(m[1], space);
    spaceOf.set(`/${space}`, space);
  }
  const app: string[] = ["/", "/trade", "/invest", "/money", "/mine", "/features", ...groups, ...navPaths,
    "/new", "/trade/positioning/stocks", "/research/scan?scan=high52", "/research/filings?view=all", "/research/filings?region=US&view=all",
    "/invest/holders?region=US", "/research/corporate-actions?scope=all", "/research/corporate-actions?region=US&scope=all",
    "/research/themes?region=IN&q=India%20steel%20and%20mining", "/research/IN/RELIANCE", "/research/IN/TCS", "/research/US/AAPL", "/research/IN/RELIANCE/deep", "/research/US/AAPL/deep",
    "/invest/ipos/in-bonfig", "/invest/ipos/in-sfctech", "/invest/ipos/us-1273626-119431",
    "/plans", "/account", "/settings", "/settings#experience", "/settings#accounts", "/settings#check", "/assistant", "/invite",
    "/admin", "/admin/users", "/admin/money", "/admin/data", "/admin/quality", "/admin/system", "/admin/emails"];
  if (nb?.id) app.push(`/n/${nb.id}`, `/n/${nb.id}/market`, `/n/${nb.id}/compare`, `/n/${nb.id}/e/1`);
  if (nb2?.id) app.push(`/n/${nb2.id}`);
  if (paper?.id) app.push(`/paper/${paper.id}`);
  const spaceFor = (p: string): string | undefined => {
    const bare = p.split(/[?#]/)[0];
    if (spaceOf.has(bare)) return spaceOf.get(bare);
    if (p === "/mine" || p === "/features") return "mine";
    if (/^\/(n\/|paper\/|options\/)/.test(bare)) return "trade";
    if (/^\/research\//.test(bare) || /^\/invest\//.test(bare)) return "invest";
    return undefined;
  };
  const open = ["/", "/plans", "/library", "/help"];
  const routes: Route[] = [
    ...Array.from(new Set(app)).map((p) => ({ path: p, label: p, signedIn: true, space: spaceFor(p) })),
    ...open.map((p) => ({ path: p, label: `${p} (signed out)`, signedIn: false })),
  ];
  return { routes, notes };
}
