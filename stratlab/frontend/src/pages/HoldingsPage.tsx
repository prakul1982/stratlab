import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, inr, money, pct, price, qty as qtyText, safeHref, signTone, sourceWords } from "../lib/format";
import { Modal } from "../components/ui";
import { Trash } from "../components/Icons";
import { track } from "../lib/analytics";
import { HoldingsActionsPanel } from "../components/HoldingsActions";
import { SurvBadges } from "../components/Surveillance";
import { EtfGapBadge } from "../components/EtfGap";
import { useMoreColumns } from "../components/MoreColumns";
import { Badge, BarList, Card, CardHead, ConfirmDialog, DataTable, Delta, EmptyState, ErrorState, Field, FormActions, FormGrid, PageHeader, PlanNote, Seg, Skeleton, Stat, StatRow, StockPicker, UploadButton, type Column } from "../components/kit";

/* /holdings: the stocks you hold, valued at today's prices: each one's value, gain or loss, trend and filings, the sector
 * mix, dividends and corporate actions, from a broker file or typed in. Facts, not advice. Built from the kit
 * (components/kit), amounts from lib/format. */

type Row = {
  symbol: string; exchange: string; name: string; sector: string; qty: number; avg: number | null; price: number | null;
  value: number | null; invested: number | null; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null;
  weight: number | null; market?: "IN" | "US"; currency?: string;
  kind?: "stock" | "etf" | "reit" | "invit" | "sgb"; kind_label?: string | null;   // ETFs, REITs, InvITs and gold bonds get a badge
};
type UsTotals = { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number; in_total: boolean };
type View = {
  rows: Row[]; allocation: { sector: string; value: number; pct: number | null; count: number }[];
  totals: { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number; priced: number };
  source: string | null; updated_at: string | null; prices: boolean; prices_at?: string | null; limit: number; facts_max: number;
  us?: UsTotals | null; usd_inr?: number | null; us_prices?: boolean | null;
};
type Mkt = "IN" | "US";
type Facts = {
  stage: number | null; st_up: boolean | null; signal: string | null; red: number | null; amber: number | null; flags: string[];
  recent: { at: string; label: string; severity: string; subject: string; url: string | null }[]; results: { date: string; subject: string; url: string | null } | null;
};
type FactsReply = { rows: Record<string, Facts>; filings: boolean; filings_plan: string; checked: number; count: number };
type Unmatched = { line: number | null; text: string; reason: string };
type ImportReply = { broker: string; imported: number; saved: boolean; unmatched: Unmatched[]; unmatched_count: number; over_limit: string[]; limit: number; holdings: View };

const MAX_MB = 2;
const BROKERS = "Zerodha (Console or Kite), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities";
const usd = (v: number | null | undefined) => money(v, "USD", 0);
const isUS = (r: Row) => r.market === "US";
const cur = (r: Row) => r.currency ?? "INR";
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

const Trend = ({ f }: { f?: Facts }) => (!f || f.stage == null ? <span className="k-muted">–</span> : <>Stage {f.stage} · ST {f.st_up ? "up" : "down"}</>);

function FilingsCell({ f, allowed, plan }: { f?: Facts; allowed: boolean; plan?: string }) {
  if (!allowed) return <span className="k-muted">{plan ?? "Basic"}</span>;
  if (!f || f.red == null) return <span className="k-muted">–</span>;
  if (f.red) return <span>{f.red} red flag{f.red === 1 ? "" : "s"}</span>;
  return <>{f.amber ? `${f.amber} to look at` : "No red flags"}</>;
}

export function HoldingsPage() {
  const { fail, notify } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<FactsReply | null>(null);
  const more = useMoreColumns("holdings", 6);     // price detail, sector, trend and filings: one click away, so the table fits a laptop
  const [mode, setMode] = useState<"replace" | "add">("replace");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [edit, setEdit] = useState<Row | null>(null);
  const editAt = useRef(0);                        // the edited row's place, so focus lands on its neighbour if it's removed
  const [asking, setAsking] = useState(false);
  const [add, setAdd] = useState<{ symbol: string; qty: string; avg: string; market: Mkt }>({ symbol: "", qty: "", avg: "", market: "IN" });
  const [picked, setPicked] = useState("");        // the symbol picked from the suggestions (what the box shows until you type)
  const [boxes, setBoxes] = useState(0);           // a new number empties the stock box

  const loadFacts = useCallback((v: View) => {
    setFacts(null);
    if (v.rows.length) api<FactsReply>("/holdings/facts").then(setFacts).catch(() => setFacts({ rows: {}, filings: true, filings_plan: "Basic", checked: 0, count: 0 }));
  }, []);
  const [actionsAt, setActionsAt] = useState(0);         // reload the corporate actions whenever the holdings change
  // the dividends card arrives a moment after the holdings: the cards below it wait for it (a few seconds at most), so
  // it doesn't push them down the screen as it lands
  const [actionsReady, setActionsReady] = useState(false);
  useEffect(() => {
    if (!view || actionsReady) return;
    if (!view.rows.length) { setActionsReady(true); return; }      // nothing held: no dividends card to wait for, now or after an add
    const t = window.setTimeout(() => setActionsReady(true), 3000);
    return () => window.clearTimeout(t);
  }, [view, actionsReady]);
  const show = useCallback((v: View) => { setView(v); loadFacts(v); setActionsAt((n) => n + 1); }, [loadFacts]);
  const load = useCallback(() => {
    setError(null);
    api<View>("/holdings").then(show).catch((e) => { setError(e instanceof Error ? e.message : "Your holdings couldn't be read."); fail(e); });
  }, [show, fail]);
  useEffect(() => { load(); }, [load]);

  const pick = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB. A holdings export is much smaller; check it's the right file.`); reset(); return; }
    setBusy(true);
    try {
      const data = await dataUrl(f);
      const r = await api<ImportReply>("/holdings/import", { method: "POST", body: { filename: f.name, data, mode } });
      track("holdings imported", { rows: r.imported, method: mode });
      setResult(r);
      show(r.holdings);
    } catch (e) { fail(e); } finally {
      setBusy(false);
      reset();
    }
  };

  const save = async (items: { symbol: string; qty: number; avg: number | null; market: Mkt }[], done?: string) => {
    setBusy(true);
    try {
      const r = await api<{ unmatched: Unmatched[]; holdings: View }>("/holdings", { method: "PUT", body: { items } });
      show(r.holdings);
      if (r.unmatched.length) notify(`${r.unmatched.map((u) => u.text).join(", ")}: ${r.unmatched[0].reason.startsWith("No US") ? "no US-listed company has that ticker" : "no listed company on NSE or BSE has that symbol"}.`);
      else if (done) notify(done);
      return !r.unmatched.length;
    } catch (e) { fail(e); return false; } finally { setBusy(false); }
  };
  const current = () => (view?.rows ?? []).map((r) => ({ symbol: r.symbol, qty: r.qty, avg: r.avg, market: (r.market ?? "IN") as Mkt }));
  const same = (x: { symbol: string; market: Mkt }, r: Row) => x.symbol === r.symbol && x.market === (r.market ?? "IN");

  const addOne = async () => {
    const q = Number(add.qty), a = add.avg.trim() ? Number(add.avg) : null;
    if (!add.symbol.trim() || !(q > 0) || (a != null && !(a >= 0))) { notify("Enter the symbol, a quantity above 0 and, if you like, the average price."); return; }
    if (await save([...current(), { symbol: add.symbol.trim(), qty: q, avg: a, market: add.market }], `${add.symbol.trim().toUpperCase()} added.`)) {
      setAdd({ symbol: "", qty: "", avg: "", market: add.market }); setPicked(""); setBoxes((n) => n + 1);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api("/holdings", { method: "DELETE" });
      setResult(null); setFacts(null);
      setView(await api<View>("/holdings"));
      notify("Your holdings are deleted.");
    } catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };

  const rows = view?.rows ?? [];
  const t = view?.totals;
  const withFilings = facts ? rows.filter((r) => (facts.rows[r.symbol]?.recent.length ?? 0) > 0) : [];

  const cols: Column<Row>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => (
      <>
        {r.kind && r.kind !== "stock" ? <b>{r.symbol}</b> : <Link className="link" to={`/research/${isUS(r) ? "US" : "IN"}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>}
        {r.exchange === "BSE" && <span className="k-note"> BSE</span>}{isUS(r) && <span className="k-note"> US</span>}
        {r.kind_label && <> <span className={`badge kind-${r.kind}`} title="Instrument type">{r.kind_label}</span></>}
        <div className="k-note k-clip">{r.name}</div>
        {!isUS(r) && (!r.kind || r.kind === "stock") && <SurvBadges region="IN" symbol={r.symbol} />}{!isUS(r) && r.kind === "etf" && <EtfGapBadge symbol={r.symbol} />}
      </>) },
    { key: "value", header: "Value", numeric: true, cell: (r) => money(r.value ?? r.invested, cur(r), 0) },
    { key: "pnl", header: "Unrealised P&L", numeric: true, cell: (r) => (r.pnl == null ? "–" : <span className={tone(r.pnl)}>{money(r.pnl, cur(r), 0)}<span className="k-sub-line">{pct(r.pnl_pct)}</span></span>) },
    { key: "day", header: "Today", numeric: true, cell: (r) => (r.day == null ? "–" : <span className={tone(r.day)}>{money(r.day, cur(r), 0)}<span className="k-sub-line">{pct(r.day_pct, 2)}</span></span>) },
    { key: "weight", header: "Weight", numeric: true, cell: (r) => (r.weight == null ? "–" : `${r.weight.toFixed(1)}%`) },
    { key: "qty", header: "Qty", numeric: true, cell: (r) => qtyText(r.qty) },
    ...(more.on ? [
      { key: "avg", header: "Avg. price", numeric: true, cell: (r: Row) => price(r.avg, cur(r)) },
      { key: "price", header: "Price", numeric: true, cell: (r: Row) => price(r.price, cur(r)) },
      { key: "sector", header: "Sector", cell: (r: Row) => r.sector },
      { key: "trend", header: "Trend", cell: (r: Row) => <Trend f={facts?.rows[r.symbol]} /> },
      { key: "filings", header: "Filings, 3 months", cell: (r: Row) => <FilingsCell f={facts?.rows[r.symbol]} allowed={facts?.filings !== false} plan={facts?.filings_plan} /> },
      { key: "results", header: "Results meeting", cell: (r: Row) => { const f = facts?.rows[r.symbol]; return f?.results ? <a className="link" href={safeHref(f.results.url)} target="_blank" rel="noreferrer">{dateOnly(f.results.date)}</a> : <span className="k-muted">–</span>; } },
    ] : []),
    { key: "edit", header: "", action: true, cell: (r) => <button type="button" className="btn quiet sm" data-row-edit onClick={() => { editAt.current = rows.indexOf(r); setEdit(r); }} aria-label={`Edit ${r.symbol}`}>Edit</button> },
  ];
  const unmatchedCols: Column<Unmatched & { i: number }>[] = [
    { key: "line", header: "Line", rowHeader: true, cell: (u) => u.line ?? "–" },
    { key: "text", header: "What the file says", cell: (u) => u.text || "–" },
    { key: "why", header: "Why", wrap: true, cell: (u) => <span className="k-muted">{u.reason}</span> },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · What you own" title="Your stocks, at today's prices" asOf={view?.prices_at} asOfLabel="Prices as of"
        lede="Your broker's holdings file, valued at today's prices: each stock's value, gain or loss, and your sector mix."
        info="Facts, not advice. Only you can see your holdings." infoLabel="About your holdings" />

      <Card>
        <CardHead title="Import from your broker" info={<>Download your holdings as Excel or CSV from {BROKERS} (usually Portfolio › Holdings › Download), then upload it here. Any other CSV works too with columns for Symbol (or ISIN), Quantity and Average price.</>}
          actions={rows.length > 0 ? <Seg label="What the file does" options={[{ value: "replace", label: "Replace my holdings" }, { value: "add", label: "Add to them" }]} value={mode} onChange={(m) => setMode(m as typeof mode)} /> : undefined} />
        <div className="k-row">
          <UploadButton label="Upload holdings file" busy={busy} accept=".csv,.xlsx,.xls,.txt,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ariaLabel="Holdings file" onFiles={pick} />
          <span className="k-note">Excel or CSV, up to {MAX_MB} MB.</span>
        </div>
        <p className="k-note">Prefer not to upload each time? <Link to="/settings#accounts">Connect Zerodha or your statement inbox once</Link> and this stays up to date by itself.</p>
        {result && (
          <div className="k-stack" role="status">
            <p className="k-small">
              <b>{result.broker === "CSV" ? "Read as a CSV file" : `Read as a ${result.broker} file`}:</b>{" "}
              {result.saved ? `${result.imported} stock${result.imported === 1 ? "" : "s"} saved.` : "nothing matched, so your saved holdings are unchanged."}
              {result.unmatched_count > 0 && ` ${result.unmatched_count} line${result.unmatched_count === 1 ? "" : "s"} couldn't be matched (below).`}
            </p>
            {result.over_limit.length > 0 && (
              <p className="k-small">Your plan keeps {result.limit} stocks, so {result.over_limit.length} were left out: {result.over_limit.slice(0, 12).join(", ")}{result.over_limit.length > 12 ? "…" : ""}. <Link className="link" to="/plans">See plans</Link></p>
            )}
            {result.unmatched.length > 0 && <DataTable label="Lines that couldn't be matched" columns={unmatchedCols} rows={result.unmatched.map((u, i) => ({ ...u, i }))} rowKey={(u) => String(u.i)} />}
            {result.unmatched.length > 0 && <p className="k-note">Add any of these by hand below with its NSE symbol or BSE code.</p>}
          </div>
        )}
      </Card>

      {!view && (error
        ? <ErrorState title="Your holdings couldn't be read" action={{ label: "Try again", onClick: load }}>{error}</ErrorState>
        : <Card><Skeleton label="Opening your holdings" /></Card>)}
      {view && rows.length === 0 && (
        <EmptyState title="No holdings yet">Upload your broker's holdings file above, or add stocks one at a time below.</EmptyState>
      )}

      {view && t && rows.length > 0 && (
        <>
          <Card>
            <CardHead title="Where your stocks stand" />
            <StatRow>
              <Stat label="Current value" value={inr(t.value)} />
              <Stat label="Invested" value={inr(t.invested)} />
              <Stat label="Unrealised P&L" value={t.pnl == null ? "–" : inr(t.pnl)} tone={signTone(t.pnl)} delta={t.pnl == null ? undefined : <Delta value={t.pnl}>{pct(t.pnl_pct)}</Delta>} />
              <Stat label="Today" value={t.day == null ? "–" : inr(t.day)} tone={signTone(t.day)} delta={t.day == null ? undefined : <Delta value={t.day}>{pct(t.day_pct, 2)}</Delta>} />
            </StatRow>
            <p className="k-note">
              {t.count} stock{t.count === 1 ? "" : "s"}{view.source ? ` · from ${sourceWords(view.source)}` : ""}{view.updated_at ? ` · updated ${ago(view.updated_at)}` : ""}
              {!view.prices && " · Live prices are offline right now, so values are shown at cost."}
            </p>
            {view.us && (
              <p className="k-small" aria-label="US stocks">
                <b>US stocks</b> ({view.us.count}): {usd(view.us.value)} · invested {usd(view.us.invested)}
                {view.us.pnl != null && <> · <span className={tone(view.us.pnl)}>{usd(view.us.pnl)} ({pct(view.us.pnl_pct)})</span></>}
                <span className="k-note"> · {view.us.in_total && view.usd_inr ? `in the rupee totals above at ₹${view.usd_inr.toFixed(2)} a dollar` : "not in the rupee totals above: the exchange rate isn't available right now"}
                  {view.us_prices === false && " · US prices are offline right now, so these are at cost"}. US stocks aren't part of the tax report, which works out Indian capital gains.</span>
              </p>
            )}
          </Card>
          <HoldingsActionsPanel<View> version={actionsAt} onHoldings={setView} onLoaded={() => setActionsReady(true)} />
          {!actionsReady && <Card><Skeleton label="Opening your sectors and positions" /></Card>}
        </>
      )}

      {view && t && rows.length > 0 && actionsReady && (
        <>
          <Card>
            <CardHead title="By sector" />
            <BarList label="Holdings by sector" footnote="Share of the current value, by the exchange's sector for each company."
              rows={view.allocation.map((a) => ({ key: a.sector, name: a.sector, note: `${a.count} stock${a.count === 1 ? "" : "s"}`, value: a.pct == null ? "–" : `${a.pct.toFixed(1)}%`, pct: a.pct }))} />
          </Card>

          <Card label="Positions">
            <CardHead title="Positions" actions={<>
              {!facts && <span className="k-note">Checking each stock's trend and filings…</span>}
              {more.toggle}
            </>} />
            <DataTable label="Positions" columns={cols} rows={rows} rowKey={(r) => `${r.exchange}:${r.symbol}`} />
            {facts && facts.count > facts.checked && <p className="k-note">Trend and filings are shown for the {facts.checked} largest positions.</p>}
            {facts && !facts.filings && <PlanNote>Red flags, recent filings and results dates come from the filings feature on the {facts.filings_plan} plan.</PlanNote>}
          </Card>

          {withFilings.length > 0 && (
            <Card>
              <CardHead title="Recent filings" info={<>From the companies' own exchange filings, sorted by fixed rules you can read on the <Link className="link" to="/research/filings">Red flags</Link> page.</>} />
              <div className="k-stack">
                {withFilings.map((r) => {
                  const f = facts!.rows[r.symbol];
                  return (
                    <div key={r.symbol} className="k-stack">
                      <div className="k-row"><b>{r.symbol}</b>{f.flags.length > 0 && <span className="k-note">Last 3 months: {f.flags.join(" · ")}</span>}</div>
                      {f.recent.map((x, i) => (
                        <div key={i} className="k-row top k-small">
                          <span className="k-note">{dateOnly(x.at)}</span>
                          <Badge dot={false}>{x.label}</Badge>
                          {x.url ? <a className="link k-any" href={safeHref(x.url)} target="_blank" rel="noreferrer">{x.subject || "Filing"}</a> : <span className="k-any">{x.subject}</span>}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}

      {view && actionsReady && (
        <Card>
          <CardHead title="Add a stock by hand" actions={
            <Seg label="Where it's listed" options={[{ value: "IN", label: "India (NSE/BSE)" }, { value: "US", label: "United States" }]} value={add.market}
              onChange={(m) => { setAdd({ ...add, market: m as Mkt, symbol: add.market === m ? add.symbol : "" }); if (add.market !== m) { setPicked(""); setBoxes((n) => n + 1); } }} />} />
          <FormGrid onSubmit={(e) => { e.preventDefault(); void addOne(); }}>
            <Field label={add.market === "IN" ? "NSE symbol or BSE code" : "US ticker"} info="Type a name or a symbol and pick from the suggestions, or type an exact symbol.">
              {(id) => <StockPicker key={`${add.market}-${boxes}`} id={id} market={add.market} value={picked} placeholder={add.market === "IN" ? "Name or symbol, e.g. Reliance" : "Name or ticker, e.g. Apple"}
                onText={(text) => setAdd((x) => ({ ...x, symbol: text }))} onPick={(s, region) => { setPicked(s); setAdd((x) => ({ ...x, symbol: s, market: region })); }} />}
            </Field>
            <Field label="Quantity" inputMode="decimal" placeholder="10" value={add.qty} onChange={(e) => setAdd({ ...add, qty: e.target.value })} />
            <Field label="Average price" optional unit={add.market === "US" ? "$" : "₹"} inputMode="decimal" placeholder={add.market === "US" ? "180" : "2,450"} value={add.avg}
              onChange={(e) => setAdd({ ...add, avg: e.target.value.replace(/,/g, "") })} />
            <FormActions><button type="submit" className="btn" disabled={busy}>Add</button></FormActions>
          </FormGrid>
          {add.market === "US" && <p className="k-note">US stocks are valued in dollars, and added to your totals in rupees at the day's exchange rate. They aren't part of the tax report.</p>}
        </Card>
      )}

      {view && rows.length > 0 && actionsReady && (
        <section className="k-stack">
          <p className="k-note">Your holdings are stored with your account only, used for this page and your My Stocks newsletter, and never shared. Values use the latest prices; P&amp;L is before charges and taxes. Nothing here is investment advice.</p>
          <button type="button" className="btn danger k-btn-end" onClick={() => setAsking(true)}><Trash size={16} />Delete my holdings</button>
        </section>
      )}

      {edit && (
        <EditHolding row={edit} busy={busy} onClose={() => setEdit(null)} fallback={() => afterRemove(editAt.current)}
          onSave={async (q, a) => { if (await save(current().map((x) => (same(x, edit) ? { ...x, qty: q, avg: a } : x)), `${edit.symbol} updated.`)) setEdit(null); }}
          onRemove={async () => { if (await save(current().filter((x) => !same(x, edit)), `${edit.symbol} removed.`)) setEdit(null); }} />
      )}
      {asking && <ConfirmDialog title="Delete my holdings?" confirmLabel="Delete my holdings" busy={busy} onConfirm={() => void remove()} onClose={() => setAsking(false)}>Every saved position is removed from StratLab. Your broker account isn't touched.</ConfirmDialog>}
    </div>
  );
}

/** Where focus goes once a removed row's dialog closes: the next row's Edit button (the last one if it was last), else the
 * Positions heading, else the page's heading. */
function afterRemove(at: number): HTMLElement | null {
  const edits = document.querySelectorAll<HTMLElement>("[data-row-edit]");
  if (edits.length) return edits[Math.min(at, edits.length - 1)];
  const h = document.querySelector<HTMLElement>('section[aria-label="Positions"] h2') ?? document.querySelector<HTMLElement>("main h1");
  h?.setAttribute("tabindex", "-1");
  return h;
}

function EditHolding({ row, busy, onClose, onSave, onRemove, fallback }: {
  row: Row; busy: boolean; onClose: () => void; onSave: (qty: number, avg: number | null) => void; onRemove: () => void; fallback: () => HTMLElement | null;
}) {
  const [q, setQ] = useState(String(row.qty));
  const [a, setA] = useState(row.avg == null ? "" : String(row.avg));
  const qn = Number(q), an = a.trim() ? Number(a) : null;
  const ok = qn > 0 && (an == null || an >= 0);
  return (
    <Modal title={`Edit ${row.symbol}`} onClose={onClose} fallback={fallback}>
      <FormGrid onSubmit={(e) => { e.preventDefault(); if (ok && !busy) onSave(qn, an); }}>
        <Field label="Quantity" inputMode="decimal" value={q} onChange={(e) => setQ(e.target.value)} />
        <Field label="Average price" optional unit={row.market === "US" ? "$" : "₹"} inputMode="decimal" value={a} onChange={(e) => setA(e.target.value.replace(/,/g, ""))} />
        <FormActions>
          <button type="submit" className="btn" disabled={busy || !ok}>Save</button>
          <button type="button" className="btn danger" disabled={busy} onClick={onRemove}><Trash size={16} />Remove from holdings</button>
        </FormActions>
      </FormGrid>
    </Modal>
  );
}
