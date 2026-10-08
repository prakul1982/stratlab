import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, inr, price, qty as qtyText, signTone } from "../lib/format";
import { Info } from "../components/ui";
import { Download, Trash } from "../components/Icons";
import { track } from "../lib/analytics";
import { UnitsCard, type Units } from "../components/TaxUnits";
import { UsTaxCard, type UsYear } from "../components/UsTaxCard";
import { useMoreColumns } from "../components/MoreColumns";
import { Card, CardHead, ConfirmDialog, DataTable, Disclosure, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, Meter, Notice, PageHeader, PageNav, PlanNote, Seg, Select, Skeleton, Stat, StatRow, UploadButton, type Column } from "../components/kit";
import { movedYearNote, openFy, rememberFy } from "../lib/fy";

/* /tax-report: capital gains on shares and funds from the tradebooks you upload, matched first in, first out, with the
 * exemption and set-off, F&O and intraday kept apart, and the year's total tax estimate. Estimates, never advice.
 * Built from the kit (components/kit), amounts from lib/format. */

type Bucket = { key: string; label: string; rate: number; gains: number; after_setoff: number; exempt: number; taxable: number; tax: number; slab?: boolean };
type Sale = { key: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number; term: "ST" | "LT"; bonus: boolean; gf: "applied" | "missing" | null; rate: number | null; mf?: boolean };
type Side = { gains: number; losses: number; net: number; sales: number };
type Leg = { pnl: number; turnover: number; trades: number };
type Segment = {
  seg: "fno" | "commodity" | "currency"; label: string; trades: number; pnl: number; charges: number; stt: number; net: number;
  turnover: number; turnover_contract: number; first: string; last: string; options: Leg; futures: Leg; by: ({ u: string } & Leg)[];
};
type Business = { segments: Segment[]; pnl: number; charges: number; net: number; turnover: number; turnover_contract: number; trades: number };
type Age = "below60" | "60to79" | "80plus";
type Inputs = { regime: "new" | "old"; other: number; salary: number | null; deductions: number; age: Age; resident: boolean; saved: boolean };
type Total = {
  available: boolean; reason?: string; regime: "new" | "old"; inputs: Inputs; total: number;
  parts: { capital_gains: number; intraday: number; fno: number; other: number };
  slab_tax: number; special_tax: number; rebate: number; surcharge: number; surcharge_rate: number; cess: number;
  income: { normal: number; special: number; total: number; salary: number; standard_deduction: number; deductions: number };
  carry_forward: { speculative: number; business: number }; steps: string[]; lines: { label: string; amount: number; kind: string }[];
  notes?: string[]; confirmed?: boolean; source?: string | null;
};
type Year = {
  fy: number; label: string; stcg: Side; ltcg: Side; exempt_old: number | null; exemption: { limit: number; used: number; left: number };
  buckets: Bucket[]; steps: string[]; tax: number; tax_with_cess: number; carry_forward: { st: number; lt: number };
  intraday: { count: number; buy: number; sell: number; pnl: number; turnover: number }; gf_missing: number; gf_applied: number; count: number; rows: Sale[];
  business: Business; total: Total; inputs: Inputs; other_regime: { regime: "new" | "old"; total: number } | null; filing: string[]; turnover: number;
  mutual_funds?: MfYear | null;
  units?: Units | null;
  us?: UsYear;
};
/** Mutual fund sales from the Money space, already in the rows and buckets above; this is their summary. */
type MfYear = { count: number; gain: number; equity: number; slab: number; other_lt: number; dividends: number };
type Lot = { key: string; bought: string; qty: number; cost: number; cost_each: number | null; price: number; value: number; loss: number; loss_pct: number | null; days: number; term: "ST" | "LT"; long_from: string | null; bonus: boolean };
type Report = {
  years: Year[]; current_fy: number; names: Record<string, { symbol: string; name: string; isin: string; listed: boolean }>;
  below_cost: { rows: Lot[]; unpriced: number; open: number; st: number; lt: number };
  unmatched_sales: { key: string; qty: number; first: string }[]; holdings_check: { key: string; files: number; holdings: number }[];
  pre_2018: string[]; fmv: Record<string, { value: number | null; source: "yours" | "your file" | "looked up" | null }>;
  kinds?: Record<string, string>; unit_notes?: string[];
  rules: string[]; notes: string[]; disclaimer: string; files: { name: string; broker: string; kind: string; trades: number; at: string }[];
  updated_at: string | null; trades: number; business_lines: number; prices: boolean; prices_at: string | null; max_trades: number;
  mf?: { allowed: boolean; count: number; plan: string };
  us_trades?: number;
};
type Problem = { line: number | null; text: string; reason: string };
type Skipped = { name: string; reason: string };
type Check = { section: string; file: number | null; summary: number | null; ok: boolean; what?: "pnl" | "turnover" };
type BizReply = { lines: number; added: number; replaced: number; same: number; years: number[] };
type ImportReply = {
  broker: string; kind: "trades" | "pnl" | "business"; read: number; added: number; duplicates: number; over_limit: number; problems: Problem[]; problem_count: number;
  not_listed: string[]; skipped: Skipped[]; check: Check[]; files: { name: string; section: string; lines: number }[]; report: Report;
  business: BizReply; picked?: number;
};

const MAX_MB = 10;          // a file, the server's cap too
const FNO_MB = 20;          // an F&O, commodity or currency file on its own (by its name), the server's cap too
const MAX_TOTAL_MB = 25;    // everything picked at once
const isBusiness = (name: string) => !/\.zip$/i.test(name) && /f\s*&\s*o|(^|[^a-z])fno([^a-z]|$)|futures|options|derivative|commodit|currenc/i.test(name);
const capMb = (name: string) => (isBusiness(name) ? FNO_MB : MAX_MB);
const BROKERS = "Zerodha (Console tradebook, or the tax P&L ZIP as it downloads), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities";
const rate = (r: number | null, slab?: boolean) => (r == null || slab ? "Slab" : `${+(r * 100).toFixed(2)}%`);
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

/** Several files' replies as one: counts added up, lists joined. */
function combine(a: ImportReply | null, b: ImportReply): ImportReply {
  if (!a) return b;
  return {
    ...b, picked: (a.picked ?? 1) + 1, read: a.read + b.read, added: a.added + b.added, duplicates: a.duplicates + b.duplicates,
    over_limit: b.over_limit, problems: [...a.problems, ...b.problems].slice(0, 200), problem_count: a.problem_count + b.problem_count,
    not_listed: [...new Set([...a.not_listed, ...b.not_listed])], skipped: [...a.skipped, ...b.skipped], check: [...a.check, ...b.check], files: [...a.files, ...b.files],
    business: {
      lines: a.business.lines + b.business.lines, added: a.business.added + b.business.added, replaced: a.business.replaced + b.business.replaced,
      same: a.business.same + b.business.same, years: [...new Set([...a.business.years, ...b.business.years])].sort(),
    },
  };
}

/** The year to open on: the one already open if it has sales, else the Money pages' shared year (the year being filed,
 * lib/fy), or the latest year with trades when that one has none (`from`: the year it moved from, said in one line). */
const hasTrades = (y: Year) => y.count > 0 || y.intraday.count > 0 || y.business.segments.length > 0 || !!y.units;
function bestYear(r: Report, cur: number | null): { fy: number; from: number | null } {
  const open = r.years.find((y) => y.fy === cur);
  if (open && hasTrades(open)) return { fy: open.fy, from: null };
  return openFy(r.years.map((y) => y.fy), r.current_fy, (fy) => r.years.some((y) => y.fy === fy && hasTrades(y)));
}

export function TaxReportPage() {
  const { fail, notify } = useApp();
  const [rep, setRep] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [movedFrom, setMovedFrom] = useState<number | null>(null);      // the empty year it opened past, if it did
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [allSales, setAllSales] = useState(false);
  const [asking, setAsking] = useState(false);
  // each wide table leads with what the tax works out from; the rest is a click away, so it fits a laptop
  const salesMore = useMoreColumns("tax-sales", 3);
  const lotsMore = useMoreColumns("tax-below", 3);
  const [getting, setGetting] = useState<"csv" | "pdf" | null>(null);

  const open = useCallback((r: Report, cur: number | null) => {
    const b = bestYear(r, cur);
    if (b.fy !== cur) setMovedFrom(b.from);
    return b.fy;
  }, []);
  const show = useCallback((r: Report) => { setRep(r); setFy((cur) => open(r, cur)); }, [open]);
  const load = useCallback(() => {
    setError(null);
    api<Report>("/tax").then(show).catch((e) => { setError(e instanceof Error ? e.message : "Your tax report couldn't be read."); fail(e); });
  }, [show, fail]);
  useEffect(() => { load(); }, [load]);

  const pick = async (files: FileList | null, reset: () => void) => {
    const all = Array.from(files ?? []);
    if (!all.length) return;
    if (all.reduce((n, f) => n + f.size, 0) > MAX_TOTAL_MB * 1024 * 1024) {
      notify(`Those files come to more than ${MAX_TOTAL_MB} MB together. Upload a few at a time.`);
      reset();
      return;
    }
    const list = all.filter((f) => f.size <= capMb(f.name) * 1024 * 1024);
    for (const f of all) if (f.size > capMb(f.name) * 1024 * 1024) notify(`${f.name} is larger than ${capMb(f.name)} MB. Split it by year (or quarter) and upload each one.`);
    if (!list.length) { reset(); return; }
    setBusy(true);
    try {
      let got: ImportReply | null = null;
      for (const [i, f] of list.entries()) {
        // the file itself is the body; with several files, only the first one replaces: the rest are added to it
        const q = new URLSearchParams({ filename: f.name.slice(0, 200), mode: i === 0 ? mode : "add" });
        const one = await api<ImportReply>(`/tax/import?${q}`, { method: "POST", file: f });
        got = combine(got, one);
        track("tax file imported", { rows: one.added, method: mode, zip: /\.zip$/i.test(f.name) });
      }
      if (got) { setResult(got); setRep(got.report); setFy(open(got.report, null)); setMode("add"); }
    } catch (e) { fail(e); } finally {
      setBusy(false);
      reset();
    }
  };

  const download = async (format: "csv" | "pdf") => {
    if (fy == null) return;
    setGetting(format);
    try {
      const r = await api<Response>(`/tax/export?fy=${fy}&format=${format}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-tax-FY-${fy}-${String(fy + 1).slice(2)}.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); } finally { setGetting(null); }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api("/tax", { method: "DELETE" });
      setResult(null);
      show(await api<Report>("/tax"));
      notify("Your tax data is deleted.");
    } catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };

  const setFmv = async (symbol: string, value: number | null) => {
    try { show(await api<Report>("/tax/fmv", { method: "PUT", body: { symbol, fmv: value } })); notify(value ? `${symbol}: 31 Jan 2018 price saved.` : `${symbol}: back to the looked-up price.`); }
    catch (e) { fail(e); }
  };

  const saveInputs = async (year: number, v: Omit<Inputs, "saved">) => {
    try { show(await api<Report>("/tax/inputs", { method: "PUT", body: { fy: year, ...v } })); notify("Saved. The estimate is updated."); track("tax inputs saved", { regime: v.regime, age: v.age, resident: v.resident }); }
    catch (e) { fail(e); }
  };

  const y = useMemo(() => rep?.years.find((x) => x.fy === fy) ?? null, [rep, fy]);
  const name = (k: string) => rep?.names[k]?.symbol ?? k;
  const has = !!rep && (rep.trades > 0 || rep.business_lines > 0 || (rep.mf?.count ?? 0) > 0);

  const bucketCols: Column<Bucket>[] = [
    { key: "kind", header: "Kind", rowHeader: true, cell: (b) => b.label },
    { key: "rate", header: "Rate", numeric: true, cell: (b) => rate(b.rate, b.slab) },
    { key: "gains", header: "Gains", numeric: true, cell: (b) => inr(b.gains) },
    { key: "after", header: "After set-off", numeric: true, cell: (b) => inr(b.after_setoff) },
    { key: "ex", header: "Exempt", numeric: true, cell: (b) => inr(b.exempt) },
    { key: "taxable", header: "Taxable", numeric: true, cell: (b) => inr(b.taxable) },
    { key: "tax", header: "Tax", numeric: true, cell: (b) => inr(b.tax) },
  ];
  const saleCols: Column<Sale & { i: number }>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => (
      <><b>{name(r.key)}</b>{rep?.kinds?.[r.key] && <> <span className="badge kind-etf">{rep.kinds[r.key]}</span></>}{r.bonus && <span className="k-note"> bonus</span>}
        {r.gf === "applied" && <span className="k-note"> grandfathered</span>}{r.gf === "missing" && <span className="k-note k-down"> 31 Jan 2018 price missing</span>}</>) },
    { key: "gain", header: "Gain or loss", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
    { key: "term", header: "Term", cell: (r) => (r.term === "LT" ? "Long" : "Short") },
    { key: "sold", header: "Sold", numeric: true, cell: (r) => dateOnly(r.sold) },
    { key: "cost", header: "Cost", numeric: true, cell: (r) => inr(r.cost) },
    { key: "sale", header: "Sale", numeric: true, cell: (r) => inr(r.sale) },
    ...(salesMore.on ? [
      { key: "bought", header: "Bought", numeric: true, cell: (r: Sale) => dateOnly(r.bought) },
      { key: "qty", header: "Qty", numeric: true, cell: (r: Sale) => qtyText(r.qty) },
      { key: "rate", header: "Rate", numeric: true, cell: (r: Sale) => rate(r.rate) },
    ] : []),
  ];
  const lotCols: Column<Lot & { i: number }>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => <><Link className="link" to={`/research/IN/${encodeURIComponent(r.key)}`}><b>{name(r.key)}</b></Link>{r.bonus && <span className="k-note"> bonus</span>}</> },
    { key: "loss", header: "Below cost by", numeric: true, cell: (r) => <span className="k-down">{inr(r.loss)}{r.loss_pct != null && <span className="k-note"> {r.loss_pct.toFixed(1)}%</span>}</span> },
    { key: "held", header: "Held", numeric: true, cell: (r) => `${r.days} days` },
    { key: "term", header: "Term today", cell: (r) => (r.term === "LT" ? "Long-term" : <>Short-term<span className="k-sub-line">long-term from {dateOnly(r.long_from)}</span></>) },
    { key: "bought", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    ...(lotsMore.on ? [
      { key: "qty", header: "Qty", numeric: true, cell: (r: Lot) => qtyText(r.qty) },
      { key: "each", header: "Cost a share", numeric: true, cell: (r: Lot) => price(r.cost_each, "INR") },
      { key: "now", header: "Price now", numeric: true, cell: (r: Lot) => price(r.price, "INR") },
    ] : []),
  ];
  const problemCols: Column<Problem & { i: number }>[] = [
    { key: "line", header: "Line", rowHeader: true, cell: (u) => u.line ?? "–" },
    { key: "text", header: "What the file says", cell: (u) => u.text || "–" },
    { key: "why", header: "Why", wrap: true, cell: (u) => <span className="k-muted">{u.reason}</span> },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Tax" title="Capital gains on your shares" asOf={rep?.prices_at} asOfLabel="Prices as of"
        lede="Your tradebooks from every broker, matched first in, first out: short- and long-term gains for each financial year, with the exemption and set-off."
        info="Add F&O and your other income for the year's total tax. Only you can see your trades." infoLabel="About the tax report" />
      <Notice label="Estimate only"><b>Estimate only.</b> {rep?.disclaimer ?? "An estimate from the files you uploaded and the income you entered, not tax advice. It covers only the income you enter or import here, for an individual of the age band and residency you choose. Slab tax depends on your full income, and advance tax and TDS already paid aren't included. Check it with a chartered accountant (CA) before you file or pay tax."}</Notice>

      <Card>
        <CardHead title="Upload your trades"
          info={<>Download the equity tradebook (every trade) or the tax P&amp;L as Excel, CSV or ZIP from {BROKERS}, then upload it here. You can pick several files, from several brokers, at once (up to {MAX_MB} MB each, {FNO_MB} MB for an F&amp;O file on its own); trades already uploaded are skipped. Any other CSV works with the columns Date, Symbol (or ISIN), Type (buy or sell), Quantity and Price. F&amp;O, commodity and currency results are read from Zerodha's tax P&amp;L for now (the ZIP, or its "Tradewise Exits" files), or a P&amp;L file with the contract, exit date and profit.</>}
          actions={has ? <Seg label="What the file does" options={[{ value: "add", label: "Add to my trades" }, { value: "replace", label: "Start again with this file" }]} value={mode} onChange={(m) => setMode(m as typeof mode)} /> : undefined} />
        <div className="k-row">
          <UploadButton label="Upload tradebook or tax P&L" busy={busy} multiple accept=".csv,.xlsx,.xls,.txt,.zip,text/csv,application/zip,application/x-zip-compressed,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ariaLabel="Tradebook or tax P&L file" onFiles={pick} />
          <span className="k-note">Excel, CSV or ZIP, from any broker.</span>
        </div>
        {result && (
          <div className="k-stack" role="status">
            <p className="k-small">
              <b>{result.picked ? `Read ${result.picked} files` : result.broker === "CSV" ? "Read as a CSV file" : `Read as a ${result.broker} ${result.kind === "trades" ? "tradebook" : "tax P&L"}`}:</b>{" "}
              {result.added} trade{result.added === 1 ? "" : "s"} added{result.duplicates > 0 && `, ${result.duplicates} already uploaded (skipped)`}.
              {result.business.lines > 0 && ` ${result.business.lines.toLocaleString("en-IN")} F&O, commodity and currency line${result.business.lines === 1 ? "" : "s"} added up as business income${result.business.same && !result.business.added && !result.business.replaced ? " (already uploaded, unchanged)" : result.business.replaced ? " (in place of the figures from an earlier file for the same dates)" : ""}.`}
              {result.problem_count > 0 && ` ${result.problem_count} line${result.problem_count === 1 ? "" : "s"} left out (below).`}
              {result.over_limit > 0 && ` Only the first ${rep?.max_trades.toLocaleString("en-IN")} trades are kept.`}
            </p>
            {result.files.length > 0 && <p className="k-note">From the ZIP: {result.files.map((f) => `${f.section} (${f.lines.toLocaleString("en-IN")} line${f.lines === 1 ? "" : "s"})`).join(", ")}.</p>}
            {result.check.length > 0 && (
              <ul className="k-list" aria-label="Totals checked against your broker's summary">
                {result.check.map((c, i) => (
                  <li key={i}>
                    {c.ok ? <>{c.section}: {inr(c.file)} {c.what === "turnover" ? "netted per contract" : "before charges"}, the same as your broker's summary sheet.</>
                      : c.file == null ? <span className="k-down">{c.section}: your broker's summary shows {inr(c.summary)}, but the ZIP has no tradewise file for it, so it isn't included.</span>
                      : <span className="k-down">{c.section}: {inr(c.file)} read, but your broker's summary sheet shows {inr(c.summary)}. Check the file is complete.</span>}
                  </li>
                ))}
              </ul>
            )}
            {result.skipped.length > 0 && (
              <div className="k-stack">
                <p className="k-note">Left out of the tax report:</p>
                <ul className="k-list muted" aria-label="Files left out">
                  {result.skipped.map((s, i) => <li key={i}><b>{s.name}</b>: {s.reason}</li>)}
                </ul>
              </div>
            )}
            {result.not_listed.length > 0 && <p className="k-note">No listed company matched {result.not_listed.slice(0, 8).join(", ")}{result.not_listed.length > 8 ? "…" : ""}. Their gains still count, without today's prices or bonus and split data.</p>}
            {result.problems.length > 0 && <DataTable label="Lines left out" columns={problemCols} rows={result.problems.map((u, i) => ({ ...u, i }))} rowKey={(u) => String(u.i)} />}
          </div>
        )}
        {has && rep && rep.files.length > 0 && (
          <p className="k-note">
            {rep.trades.toLocaleString("en-IN")} trades{rep.business_lines > 0 && ` and ${rep.business_lines.toLocaleString("en-IN")} F&O lines`} from {rep.files.length} file{rep.files.length === 1 ? "" : "s"}: {rep.files.map((f) => `${f.name} (${f.broker})`).join(", ")}{rep.updated_at ? ` · updated ${ago(rep.updated_at)}` : ""}
          </p>
        )}
      </Card>

      {!rep && (error
        ? <ErrorState title="Your tax report couldn't be read" action={{ label: "Try again", onClick: load }}>{error}</ErrorState>
        : <Card><Skeleton label="Opening your tax report" /></Card>)}
      {rep && !has && <EmptyState title="No trades yet">Upload a tradebook or tax P&amp;L above to see your capital gains by financial year.</EmptyState>}

      {rep && has && y && (
        <>
          <Card compact>
            <CardHead title="Financial year" actions={<>
              <Select small label="Financial year" value={fy ?? ""} onChange={(x) => { setFy(Number(x)); rememberFy(Number(x)); setMovedFrom(null); setAllSales(false); }}
                options={rep.years.map((x) => ({ value: x.fy, label: `${x.label}${x.fy === rep.current_fy ? " (this year)" : ""}` }))} />
              <button type="button" className="btn quiet sm" disabled={!!getting} onClick={() => download("csv")}><Download size={16} />{getting === "csv" ? "Making the CSV…" : "Download CSV"}</button>
              <button type="button" className="btn quiet sm" disabled={!!getting} onClick={() => download("pdf")}><Download size={16} />{getting === "pdf" ? "Making the PDF…" : "Download PDF summary"}</button>
            </>} />
            {movedFrom != null && movedFrom !== y.fy && <p className="k-small k-muted" data-testid="tax-moved-year">{movedYearNote(movedFrom, y.fy, rep.current_fy, "trades")}</p>}
          </Card>

          {!hasTrades(y) && (() => {
            const other = rep.years.filter((x) => x.fy !== y.fy && hasTrades(x)).sort((a, b) => b.fy - a.fy)[0];
            return other ? (
              <Notice label="A year with trades" action={{ label: `Show ${other.label}`, onClick: () => { setFy(other.fy); rememberFy(other.fy); setMovedFrom(null); setAllSales(false); } }}>
                No trades in {y.label}. {other.label} has trades in your files.
              </Notice>
            ) : null;
          })()}

          <PageNav items={[{ id: "tax-total", label: "Total tax" }, { id: "tax-gains", label: "Gains" }, ...(y.count > 0 ? [{ id: "tax-sales", label: "Each sale" }] : []),
            { id: "tax-below", label: "Lots below cost" }, { id: "tax-how", label: "How it works" }]} />

          <TotalCard y={y} onSave={saveInputs} filing={y.filing.length > 0} />

          <Card label="Tax tools">
            <CardHead title="Dividends, advance tax and the long-term exemption" />
            <p className="k-small k-muted">Dividend income with the TDS on it (and whether it goes into the estimate above), the advance tax due by each date with TDS and payments taken off, and how much of this year's long-term exemption is used.</p>
            <Link className="btn quiet sm k-btn-end" to="/money/tax-tools">Open tax tools</Link>
          </Card>

          <Card id="tax-gains">
            <CardHead title={`Gains in ${y.label}`} />
            <StatRow>
              <Stat label="Short-term gains (net)" value={inr(y.stcg.net)} tone={signTone(y.stcg.net)} note={`${inr(y.stcg.gains)} gains · ${inr(y.stcg.losses)} losses`} />
              <Stat label="Long-term gains (net)" value={inr(y.ltcg.net)} tone={signTone(y.ltcg.net)} note={`${inr(y.ltcg.gains)} gains · ${inr(y.ltcg.losses)} losses`} />
              <Stat label="Long-term exemption used" value={inr(y.exemption.used)} note={`of ${inr(y.exemption.limit)}${y.exemption.limit ? ` · ${inr(y.exemption.left)} left` : ""}`} />
              <Stat label={<>Tax on share gains <Info label="How the tax is estimated">Short-term gains on listed shares are taxed at 15% for sales before 23 July 2024 and 20% from that day; long-term gains (held more than 12 months) at 10% and 12.5%, above the yearly exemption. Shown before the 4% cess and any surcharge.</Info></>}
                value={inr(y.tax)} note={`${inr(y.tax_with_cess)} with 4% cess`} />
            </StatRow>
            {y.exemption.limit > 0 && <Meter pct={Math.max(0, Math.min(100, (y.exemption.used / y.exemption.limit) * 100))} />}
          </Card>

          <Card>
            <CardHead title={`How ${y.label} adds up`} />
            {y.buckets.length === 0 ? <EmptyState title={`No gains or losses in ${y.label}`}>No capital gains or losses were realised in {y.label}.</EmptyState>
              : <DataTable label="Gains by rate" columns={bucketCols} rows={y.buckets} rowKey={(b) => b.key} />}
            {y.steps.length > 0 && <ul className="k-list">{y.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
            {y.exempt_old != null && <p className="k-note">Long-term results on sales before 1 April 2018 ({inr(y.exempt_old)}) were exempt under the old section 10(38), so they aren't counted.</p>}
            {y.gf_missing > 0 && <p className="k-small"><b>{y.gf_missing} sale{y.gf_missing === 1 ? "" : "s"}</b> of shares held on 31 Jan 2018 used the actual cost, because their 31 Jan 2018 price isn't known. Grandfathering could lower that gain; enter the price below.</p>}
            {y.gf_applied > 0 && <p className="k-note">{y.gf_applied} sale{y.gf_applied === 1 ? " was" : "s were"} grandfathered: the cost is the higher of the actual cost and the 31 Jan 2018 price (but not above the sale value).</p>}
          </Card>

          <Card>
            <CardHead title="Intraday trades, kept apart" info="Shares bought and sold on the same day are speculative business income, taxed at your slab rate, not capital gains. They aren't in the capital gains above; they are in the total tax estimate." />
            <p className="k-small">{y.intraday.count ? <>{y.intraday.count} same-day round trip{y.intraday.count === 1 ? "" : "s"}: purchases {inr(y.intraday.buy)}, sales {inr(y.intraday.sell)}, result <b className={tone(y.intraday.pnl)}>{inr(y.intraday.pnl)}</b>.</> : `No intraday trades in ${y.label}.`}</p>
          </Card>

          <BusinessCard y={y} />
          <UnitsCard units={y.units} notes={[]} name={name} label={y.label} />

          <MutualFundsCard y={y} mf={rep.mf} />
          <UsTaxCard us={y.us} label={y.label} trades={rep.us_trades} />

          {y.filing.length > 0 && (
            <Card id="tax-filing">
              <CardHead title="Returns and tax audit" />
              <ul className="k-list" aria-label="Returns and tax audit">{y.filing.map((f, i) => <li key={i}>{f}</li>)}</ul>
              <p className="k-note">The Income Tax Department's own page on returns for business income (ITR-3) and audit: <a className="link" href={ITR3_URL} target="_blank" rel="noopener noreferrer">incometax.gov.in</a>.</p>
            </Card>
          )}

          {y.count > 0 && (
            <Card id="tax-sales">
              <CardHead title="Each sale, matched to its purchase" actions={<><span className="k-note">{y.count} line{y.count === 1 ? "" : "s"}</span>{salesMore.toggle}</>} />
              <DataTable label="Realised sales" columns={saleCols} rows={(allSales ? y.rows : y.rows.slice(0, 30)).map((r, i) => ({ ...r, i }))} rowKey={(r) => String(r.i)} />
              {y.rows.length > 30 && !allSales && <button type="button" className="btn quiet sm k-btn-end" onClick={() => setAllSales(true)}>Show all {y.rows.length}</button>}
              {y.count > y.rows.length && <p className="k-note">The CSV download has all {y.count} lines.</p>}
              <p className="k-note">Cost includes brokerage and charges from your files; sale is after them. STT isn't deductible, so it isn't included.</p>
            </Card>
          )}

          <Card id="tax-below">
            <CardHead title="Open lots below cost" info="Tax-loss harvesting is a name for realising a loss on shares that are below their cost, so the loss can be set off against gains in the same financial year. India has no specific wash-sale rule today; shares bought again start a new holding period at the new price. Whether it suits anyone depends on their whole tax position, so check with a CA."
              infoLabel="What is tax-loss harvesting?" actions={rep.below_cost.rows.length > 0 ? lotsMore.toggle : undefined} />
            <p className="k-small k-muted">Lots still open in your files that are worth less than they cost at today's price, and how long each has been held. Facts only: this is not a suggestion to do anything.</p>
            {rep.below_cost.rows.length === 0 ? <EmptyState title="No open lot below its cost">{rep.below_cost.open ? "No open lot is below its cost at today's price." : "Your files leave no shares open."}</EmptyState> : (
              <>
                <p className="k-small">Below cost now: <b className="k-down">{inr(rep.below_cost.st)}</b> on short-term lots and <b className="k-down">{inr(rep.below_cost.lt)}</b> on long-term lots.</p>
                <DataTable label="Open lots below cost" columns={lotCols} rows={rep.below_cost.rows.map((r, i) => ({ ...r, i }))} rowKey={(r) => String(r.i)} />
              </>
            )}
            {rep.below_cost.unpriced > 0 && <p className="k-note">{rep.below_cost.unpriced} open lot{rep.below_cost.unpriced === 1 ? " has" : "s have"} no price today{rep.prices ? " (not a listed company we could match)" : " (live prices are offline right now)"}.</p>}
          </Card>

          {(rep.holdings_check.length > 0 || rep.unmatched_sales.length > 0) && (
            <Card>
              <CardHead title="Worth checking" />
              {rep.unmatched_sales.map((u) => (
                <p key={u.key} className="k-small"><b>{name(u.key)}</b>: {qtyText(u.qty)} shares sold (first on {dateOnly(u.first)}) with no matching purchase in your files. They may have been bought before your earliest file, moved in from another account, or come from a bonus or split older than our data. Their gain isn't counted; upload the older tradebook to include it.</p>
              ))}
              {rep.holdings_check.map((h) => (
                <p key={h.key} className="k-small"><b>{name(h.key)}</b>: your files leave {qtyText(h.files)} shares open; <Link className="link" to="/holdings">My Holdings</Link> has {qtyText(h.holdings)}.</p>
              ))}
            </Card>
          )}

          {rep.pre_2018.length > 0 && (
            <Card>
              <CardHead title="Shares held on 31 Jan 2018" info="For listed shares bought before 1 February 2018, the cost used for long-term gains is the higher of the actual cost and the share's highest price on 31 January 2018, but not more than the sale value. Gains made up to that day stay untaxed." infoLabel="What is grandfathering?" />
              <div className="k-stack">
                {rep.pre_2018.map((k) => <FmvRow key={k} symbol={name(k)} id={k} fmv={rep.fmv[k]} onSave={setFmv} />)}
              </div>
              <p className="k-note">Looked-up prices come from stored price history and are adjusted for later bonuses and splits we know of. Check them against the exchange's 31 Jan 2018 price list, and enter your own if they differ.</p>
            </Card>
          )}

          {/* the method is there for whoever wants it, folded, so the figures come first (R1-015) */}
          <Card id="tax-how" compact label="How this report works">
            <Disclosure summary="The set-off rules, and how this report works">
              <ul className="k-list">{rep.rules.map((r, i) => <li key={i}>{r}</li>)}</ul>
              <h3 className="k-sub">How this report works</h3>
              <ul className="k-list muted">{rep.notes.map((r, i) => <li key={i}>{r}</li>)}</ul>
              {!!rep.unit_notes?.length && <><h3 className="k-sub">ETFs, REITs, InvITs and gold bonds</h3>
                <ul className="k-list muted" aria-label="ETF, REIT, InvIT and gold bond rules">{rep.unit_notes.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
            </Disclosure>
          </Card>
        </>
      )}

      {rep && has && (
        <section className="k-stack">
          <p className="k-note">Your trades are stored with your account only, used for this page, and never shared. Delete them at any time.</p>
          <button type="button" className="btn danger k-btn-end" onClick={() => setAsking(true)}><Trash size={16} />Delete my tax data</button>
        </section>
      )}
      {asking && <ConfirmDialog title="Delete my tax data?" confirmLabel="Delete my tax data" busy={busy} onConfirm={() => void remove()} onClose={() => setAsking(false)}>Every uploaded trade and file is removed from StratLab. Your broker account isn't touched.</ConfirmDialog>}
    </div>
  );
}

const REGIME = { new: "New regime", old: "Old regime" } as const;
const AGES: [Age, string][] = [["below60", "Below 60"], ["60to79", "60–79"], ["80plus", "80+"]];
const AGE_TEXT: Record<Age, string> = { below60: "below 60", "60to79": "60 to 79", "80plus": "80 or more" };
const ITR3_URL = "https://www.incometax.gov.in/iec/foportal/help/individual-business-profession";

/** The year's total tax, where it comes from, the inputs it needs and, below, how it was worked out. */
function TotalCard({ y, onSave, filing }: { y: Year; onSave: (fy: number, v: Omit<Inputs, "saved">) => Promise<void>; filing: boolean }) {
  const t = y.total;
  const chips: [string, number, string][] = [
    ["Tax on capital gains", t.parts?.capital_gains ?? 0, "Tax on short- and long-term gains on listed shares and mutual funds, at the special rates (sections 111A, 112A and 112) or, for debt-fund gains, your slab rate, with its share of surcharge and cess."],
    ["Tax on intraday", t.parts?.intraday ?? 0, "Intraday results are speculative business income, taxed at your slab rate. Slab tax is split between your incomes in proportion to each."],
    ["Tax on F&O", t.parts?.fno ?? 0, "F&O, commodity and currency results, after the charges in your files, are non-speculative business income, taxed at your slab rate."],
    ["Tax on other income", t.parts?.other ?? 0, "Your salary, interest and other income as you entered it, after the standard deduction on salary."],
  ];
  const lineCols: Column<{ i: number; label: string; amount: number; kind: string }>[] = [
    { key: "what", header: "Step", rowHeader: true, wrap: true, cell: (l) => (l.kind === "total" || l.kind === "subtotal" ? <b>{l.label}</b> : <span className={l.kind === "note" ? "k-muted" : undefined}>{l.label}</span>) },
    { key: "amount", header: "Amount", numeric: true, cell: (l) => (l.kind === "total" || l.kind === "subtotal" ? <b>{inr(l.amount)}</b> : <span className={l.kind === "amount" ? tone(l.amount) : undefined}>{inr(l.amount)}</span>) },
  ];
  return (
    <Card id="tax-total" label="Total tax estimate">
      <CardHead title={`Total tax estimate, ${y.label}`} infoLabel="What the total covers"
        info="Slab tax on your other income, intraday and F&O results, plus tax on share gains at the special rates, less the section 87A rebate where it applies, plus surcharge and 4% cess. It is worked out for an individual of the age band and residency you choose below. Advance tax and TDS already paid aren't taken off." />
      <p className="k-small k-muted">Covers only the income you enter or import here: the trades in your files and the other income you type below. House property, foreign income, other capital assets and anything else left out aren't counted.{filing && <> <a className="link" href="#tax-filing">Which return and whether a tax audit applies</a>.</>}</p>
      {t.confirmed === false && <p className="k-small k-down" role="note"><b>Rules for this year not yet confirmed.</b> The figures repeat the year before until they are checked against the Finance Act.</p>}
      {t.available ? (
        <>
          <div className="k-stack">
            <b className="k-big" aria-label="Estimated total tax">{inr(t.total)}</b>
            <span className="k-note">{REGIME[t.regime]} · {y.inputs.resident ? "resident" : "non-resident"}, aged {AGE_TEXT[y.inputs.age ?? "below60"]}{t.rebate > 0 ? ` · 87A rebate ${inr(t.rebate)}` : ""}{t.surcharge > 0 ? ` · surcharge ${inr(t.surcharge)}` : ""} · cess {inr(t.cess)}{!y.inputs.saved ? " · no other income entered yet" : ""}</span>
          </div>
          <StatRow label="Where the tax comes from">
            {chips.map(([label, v, info]) => <Stat key={label} item label={<>{label} <Info label={`About ${label}`}>{info}</Info></>} value={inr(v)} />)}
          </StatRow>
          {y.other_regime && <p className="k-note">With the same figures, the {REGIME[y.other_regime.regime].toLowerCase()} works out to {inr(y.other_regime.total)}{y.other_regime.regime === "old" ? " (with the deductions entered, if any)" : ""}.</p>}
          {(t.notes ?? []).filter((n) => !/not yet confirmed/.test(n)).map((n) => <p key={n} className="k-small" role="note"><b>Note:</b> {n}</p>)}
          {(t.carry_forward.speculative > 0 || t.carry_forward.business > 0) && (
            <p className="k-small">To carry forward:{t.carry_forward.speculative > 0 && <> intraday (speculative) loss <b className="k-down">{inr(t.carry_forward.speculative)}</b> (4 years, against speculative income only)</>}{t.carry_forward.speculative > 0 && t.carry_forward.business > 0 && ";"}{t.carry_forward.business > 0 && <> business loss <b className="k-down">{inr(t.carry_forward.business)}</b> (8 years, against business income)</>}. Only if the return is filed by its due date.</p>
          )}
        </>
      ) : <p className="k-small k-muted">{t.reason}</p>}
      <InputsPanel key={y.fy} y={y} onSave={onSave} />
      {t.available && (
        <Disclosure summary="How we got here" open>
          <ol className="k-list">{t.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {(t.notes ?? []).length > 0 && <ul className="k-list muted" aria-label="Notes on the estimate">{t.notes!.map((n) => <li key={n}>{n}</li>)}</ul>}
          <DataTable label="Total tax breakdown" columns={lineCols} rows={t.lines.map((l, i) => ({ ...l, i }))} rowKey={(l) => String(l.i)} />
        </Disclosure>
      )}
    </Card>
  );
}

const amount = (s: string) => { const n = Number(s.replace(/[,\s₹]/g, "")); return s.trim() === "" ? null : Number.isFinite(n) && n >= 0 ? n : NaN; };

/** Regime, other income (and how much of it is salary), the old regime's deductions, age band and residency, saved per year. */
function InputsPanel({ y, onSave }: { y: Year; onSave: (fy: number, v: Omit<Inputs, "saved">) => Promise<void> }) {
  const v = y.inputs;
  const [regime, setRegime] = useState<"new" | "old">(v.regime);
  const [other, setOther] = useState(v.saved && v.other ? String(v.other) : "");
  const [salary, setSalary] = useState(v.salary != null ? String(v.salary) : "");
  const [ded, setDed] = useState(v.deductions ? String(v.deductions) : "");
  const [age, setAge] = useState<Age>(v.age ?? "below60");
  const [resident, setResident] = useState(v.resident ?? true);
  const [saving, setSaving] = useState(false);
  const o = amount(other), s = amount(salary), d = amount(ded);
  const bad = Number.isNaN(o) || Number.isNaN(s) || Number.isNaN(d) || (s != null && o != null && s > o);
  const save = async () => {
    setSaving(true);
    try { await onSave(y.fy, { regime, other: o ?? 0, salary: s, deductions: regime === "old" ? d ?? 0 : 0, age, resident }); } finally { setSaving(false); }
  };
  return (
    <div className="k-inset">
      <h3 className="k-sub">Your inputs for {y.label}</h3>
      <FormGrid onSubmit={(e) => { e.preventDefault(); if (!bad && !saving) void save(); }}>
        <FieldGroup label="Tax regime" infoLabel="About the tax regime" info="The new regime is the default from FY 2023-24: lower slab rates, a higher standard deduction and almost no deductions. The old regime keeps deductions such as 80C and 80D. Each year's return says which one applies.">
          <Seg label="Tax regime" options={[{ value: "new", label: "New (default)" }, { value: "old", label: "Old" }]} value={regime} onChange={(r) => setRegime(r as typeof regime)} />
        </FieldGroup>
        <FieldGroup label="Age" infoLabel="About age" info="Your age during the year. Under the old regime, the income not taxed is ₹2.5 lakh below 60, ₹3 lakh from 60 to 79 and ₹5 lakh from 80, for residents. The new regime's slabs are the same at every age.">
          <Seg label="Age band" options={AGES.map(([value, label]) => ({ value, label }))} value={age} onChange={(a) => setAge(a as Age)} />
        </FieldGroup>
        <FieldGroup label="Resident in India?" infoLabel="About residency" info="Residency for tax depends mainly on the days spent in India in the year. A non-resident gets no section 87A rebate, can't set the unused basic exemption against share gains (sections 111A and 112A), and has the ₹2.5 lakh old-regime limit at any age. Surcharge and cess apply as usual. TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS.">
          <Seg label="Resident in India" options={[{ value: "yes", label: "Yes" }, { value: "no", label: "No" }]} value={resident ? "yes" : "no"} onChange={(r) => setResident(r === "yes")} />
        </FieldGroup>
        <Field label="Other income" unit="₹" inputMode="decimal" placeholder="e.g. 1200000" value={other} onChange={(e) => setOther(e.target.value)} aria-label="Other income"
          info="Salary, pension, interest, rent and the like for the year, before deductions, as one number. Not the trades in your files: those are added from the files." />
        <Field label="Of which salary" optional unit="₹" inputMode="decimal" placeholder="all of it" value={salary} onChange={(e) => setSalary(e.target.value)} aria-label="Of which salary"
          info="Used for the standard deduction, which is only for salary and pension, and because business losses can't be set off against salary. Leave it blank if all of it is salary." />
        {regime === "old" && (
          <Field label="Deductions" unit="₹" inputMode="decimal" placeholder="e.g. 150000" value={ded} onChange={(e) => setDed(e.target.value)} aria-label="Deductions"
            info="80C, 80D, home-loan interest and the like, as one total. They reduce income taxed at slab rates, not share gains taxed at special rates." />
        )}
        <FormActions>
          <button type="submit" className="btn" disabled={bad || saving}>{saving ? "Saving…" : "Save and update"}</button>
          {bad && <span className="k-small k-down">Enter amounts in rupees, 0 or more; the salary part can't be more than the other income.</span>}
        </FormActions>
      </FormGrid>
    </div>
  );
}

/** Mutual fund gains from the Money space: already counted above, summarised here. */
function MutualFundsCard({ y, mf }: { y: Year; mf?: Report["mf"] }) {
  const m = y.mutual_funds;
  return (
    <Card label="Mutual funds">
      <CardHead title="Mutual funds" />
      {mf && !mf.allowed ? <PlanNote>Mutual fund capital gains are on the {mf.plan} plan.</PlanNote>
        : !m ? <p className="k-small k-muted">No mutual fund redemptions or switches in {y.label}. Upload your CAS on the <Link className="link" to="/money/mutual-funds">Mutual funds</Link> page to include them.</p>
        : (
          <>
            <p className="k-small">{m.count} redemption{m.count === 1 ? "" : "s"} matched to purchase{m.count === 1 ? "" : "s"}, net <b className={tone(m.gain)}>{inr(m.gain)}</b>: equity-oriented funds {inr(m.equity)}, gains at your slab rate {inr(m.slab)}, other long-term {inr(m.other_lt)}. They're in the gains, set-off and total tax estimate above.</p>
            {m.dividends > 0 && <p className="k-note">Dividends paid out by your funds this year: {inr(m.dividends)}. They're income at your slab rate, not capital gains: include them in your other income above.</p>}
            <Link className="link k-small" to="/money/mutual-funds">See each scheme</Link>
          </>
        )}
    </Card>
  );
}

/** F&O, commodity and currency for the year: the result, charges, turnover and the biggest underlyings. */
function BusinessCard({ y }: { y: Year }) {
  const [all, setAll] = useState(false);
  const b = y.business;
  if (!b.segments.length) return (
    <Card>
      <CardHead title="F&O, commodity and currency" />
      <EmptyState title={`None in ${y.label}`}>None in your files for {y.label}. Upload the tax P&amp;L ZIP from Zerodha (or its F&amp;O, commodity and currency files) to include them in the total.</EmptyState>
    </Card>
  );
  const top = b.segments.flatMap((s) => s.by.map((u) => ({ ...u, seg: s.label }))).map((u, i) => ({ ...u, i }));
  const segCols: Column<Segment>[] = [
    { key: "seg", header: "Segment", rowHeader: true, cell: (s) => <><b>{s.label}</b><span className="k-sub-line">{dateOnly(s.first)} to {dateOnly(s.last)}</span></> },
    { key: "trades", header: "Trades", numeric: true, cell: (s) => s.trades.toLocaleString("en-IN") },
    { key: "pnl", header: "Result", numeric: true, cell: (s) => <span className={tone(s.pnl)}>{inr(s.pnl)}</span> },
    { key: "charges", header: "Charges", numeric: true, cell: (s) => inr(s.charges) },
    { key: "net", header: "After charges", numeric: true, cell: (s) => <span className={tone(s.net)}>{inr(s.net)}</span> },
    { key: "turnover", header: "Turnover", numeric: true, cell: (s) => inr(s.turnover) },
  ];
  const underCols: Column<(typeof top)[number]>[] = [
    { key: "u", header: "Underlying", rowHeader: true, cell: (u) => u.u },
    { key: "seg", header: "Segment", cell: (u) => u.seg },
    { key: "trades", header: "Trades", numeric: true, cell: (u) => u.trades.toLocaleString("en-IN") },
    { key: "pnl", header: "Result", numeric: true, cell: (u) => <span className={tone(u.pnl)}>{inr(u.pnl)}</span> },
  ];
  return (
    <Card>
      <CardHead title="F&O, commodity and currency" infoLabel="How F&O is taxed"
        info="Futures and options on shares and indices, and exchange-traded commodity and currency derivatives, are non-speculative business income, taxed at your slab rate. The charges in your files (brokerage, exchange charges, GST, stamp duty, STT and CTT) are business expenses and come off the result." />
      <DataTable label="F&O by segment" columns={segCols} rows={b.segments} rowKey={(s) => s.seg}
        foot={b.segments.length > 1 ? { seg: "Total", trades: b.trades.toLocaleString("en-IN"), pnl: inr(b.pnl), charges: inr(b.charges), net: inr(b.net), turnover: inr(b.turnover) } : undefined} />
      <p className="k-note">Turnover is the total of profits and losses, trade by trade ({inr(b.turnover)}). Netted per contract first, as broker summaries often show it, it is {inr(b.turnover_contract)}. Your files' lines aren't kept, only these totals.</p>
      {top.length > 0 && (
        <>
          <DataTable label="F&O by underlying" columns={underCols} rows={all ? top : top.slice(0, 8)} rowKey={(u) => String(u.i)} />
          {top.length > 8 && !all && <button type="button" className="btn quiet sm k-btn-end" onClick={() => setAll(true)}>Show all {top.length}</button>}
        </>
      )}
    </Card>
  );
}

function FmvRow({ symbol, id, fmv, onSave }: { symbol: string; id: string; fmv?: { value: number | null; source: string | null }; onSave: (symbol: string, value: number | null) => void }) {
  const [v, setV] = useState("");
  const n = Number(v.replace(/,/g, ""));
  const where = fmv?.source === "yours" ? "your price" : fmv?.source === "your file" ? "from your broker's file" : fmv?.source === "looked up" ? "looked up" : "not known";
  return (
    <div className="k-inset">
      <div className="k-stack">
        <b>{symbol}</b>
        <span className="k-note">{fmv?.value ? `${price(fmv.value, "INR")} a share, ${where}` : where === "from your broker's file" ? "from your broker's file" : "31 Jan 2018 price not known"}</span>
      </div>
      <FormGrid onSubmit={(e) => { e.preventDefault(); if (n > 0) { onSave(id, n); setV(""); } }}>
        <Field label="Your 31 Jan 2018 price" unit="₹" inputMode="decimal" placeholder="e.g. 310.50" value={v} onChange={(e) => setV(e.target.value)} />
        <FormActions>
          <button type="submit" className="btn" disabled={!(n > 0)} aria-label={`Save the 31 Jan 2018 price for ${symbol}`}>Save</button>
          {fmv?.source === "yours" && <button type="button" className="btn quiet" onClick={() => onSave(id, null)} aria-label={`Clear my price for ${symbol}`}>Clear</button>}
        </FormActions>
      </FormGrid>
    </div>
  );
}
