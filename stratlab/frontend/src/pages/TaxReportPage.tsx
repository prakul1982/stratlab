import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, money, price, qty as qtyText, signClass } from "../lib/format";
import { AsOf, Empty, Info, Loading } from "../components/ui";
import { Download, Trash, Upload } from "../components/Icons";
import { track } from "../lib/analytics";
import { UnitsCard, type Units } from "../components/TaxUnits";
import { UsTaxCard, type UsYear } from "../components/UsTaxCard";
import { useMoreColumns } from "../components/MoreColumns";

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
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const rate = (r: number | null, slab?: boolean) => (r == null || slab ? "Slab" : `${+(r * 100).toFixed(2)}%`);

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

/** The year to open on: the one already open if it has sales, else the latest with any. */
function bestYear(r: Report, cur: number | null): number {
  const busy = (y: Year) => y.count > 0 || y.intraday.count > 0 || y.business.segments.length > 0 || !!y.units;
  const open = r.years.find((y) => y.fy === cur);
  if (open && busy(open)) return open.fy;
  return r.years.find(busy)?.fy ?? (open ? open.fy : r.current_fy);
}

function Disclaimer({ text }: { text: string }) {
  return <div className="banner tax-note" role="note"><span><b>Estimate only.</b> {text}</span></div>;
}

export function TaxReportPage() {
  const { fail, notify } = useApp();
  const [rep, setRep] = useState<Report | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [allSales, setAllSales] = useState(false);
  // each wide table leads with what the tax works out from; the rest is a click away, so it fits a laptop
  const salesMore = useMoreColumns("tax-sales", 3);
  const lotsMore = useMoreColumns("tax-below", 3);
  const [getting, setGetting] = useState<"csv" | "pdf" | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const show = useCallback((r: Report) => { setRep(r); setFy((cur) => bestYear(r, cur)); }, []);
  useEffect(() => { api<Report>("/tax").then(show).catch(fail); }, [show, fail]);

  const pick = async (files: FileList | null) => {
    const all = Array.from(files ?? []);
    if (!all.length) return;
    if (all.reduce((n, f) => n + f.size, 0) > MAX_TOTAL_MB * 1024 * 1024) {
      notify(`Those files come to more than ${MAX_TOTAL_MB} MB together. Upload a few at a time.`);
      if (file.current) file.current.value = "";
      return;
    }
    const list = all.filter((f) => f.size <= capMb(f.name) * 1024 * 1024);
    for (const f of all) if (f.size > capMb(f.name) * 1024 * 1024) notify(`${f.name} is larger than ${capMb(f.name)} MB. Split it by year (or quarter) and upload each one.`);
    if (!list.length) { if (file.current) file.current.value = ""; return; }
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
      if (got) { setResult(got); setRep(got.report); setFy(bestYear(got.report, null)); setMode("add"); }
    } catch (e) { fail(e); } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
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

  const remove = () => {
    if (!confirm("Delete my tax data? Every uploaded trade and file is removed from StratLab. Your broker account isn't touched.")) return;
    api("/tax", { method: "DELETE" }).then(() => { setResult(null); return api<Report>("/tax").then(show); })
      .then(() => notify("Your tax data is deleted.")).catch(fail);
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

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Tax report</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Capital gains on your shares</h1>
        <p className="page-sub">Your tradebooks from every broker, matched first in, first out: short- and long-term gains for each financial year, with the exemption and set-off. Add F&amp;O and your other income for the year's total tax. Only you can see your trades.</p>
      </div>
      <Disclaimer text={rep?.disclaimer ?? "An estimate from the files you uploaded and the income you entered, not tax advice. It covers only the income you enter or import here, for an individual of the age band and residency you choose. Slab tax depends on your full income, and advance tax and TDS already paid aren't included. Check it with a chartered accountant (CA) before you file or pay tax."} />

      <section className="card stack" style={{ gap: 14 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Upload your trades</h2>
          <p className="small muted" style={{ margin: 0 }}>Download the equity tradebook (every trade) or the tax P&amp;L as Excel, CSV or ZIP from {BROKERS}, then upload it here. You can pick several files, from several brokers, at once (up to {MAX_MB} MB each, {FNO_MB} MB for an F&amp;O file on its own); trades already uploaded are skipped. Any other CSV works with the columns Date, Symbol (or ISIN), Type (buy or sell), Quantity and Price. F&amp;O, commodity and currency results are read from Zerodha's tax P&amp;L for now (the ZIP, or its "Tradewise Exits" files), or a P&amp;L file with the contract, exit date and profit.</p>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className={`btn${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{busy ? "Reading…" : "Upload tradebook or tax P&L"}
            <input ref={file} type="file" multiple accept=".csv,.xlsx,.xls,.txt,.zip,text/csv,application/zip,application/x-zip-compressed,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden disabled={busy}
              onChange={(e) => pick(e.target.files)} aria-label="Tradebook or tax P&L file" />
          </label>
          {has && (
            <div className="seg" role="radiogroup" aria-label="What the file does">
              <button role="radio" aria-checked={mode === "add"} aria-pressed={mode === "add"} onClick={() => setMode("add")}>Add to my trades</button>
              <button role="radio" aria-checked={mode === "replace"} aria-pressed={mode === "replace"} onClick={() => setMode("replace")}>Start again with this file</button>
            </div>
          )}
        </div>
        {result && (
          <div className="stack" style={{ gap: 8 }} role="status">
            <p className="small" style={{ margin: 0 }}>
              <b>{result.picked ? `Read ${result.picked} files` : result.broker === "CSV" ? "Read as a CSV file" : `Read as a ${result.broker} ${result.kind === "trades" ? "tradebook" : "tax P&L"}`}:</b>{" "}
              {result.added} trade{result.added === 1 ? "" : "s"} added{result.duplicates > 0 && `, ${result.duplicates} already uploaded (skipped)`}.
              {result.business.lines > 0 && ` ${result.business.lines.toLocaleString()} F&O, commodity and currency line${result.business.lines === 1 ? "" : "s"} added up as business income${result.business.same && !result.business.added && !result.business.replaced ? " (already uploaded, unchanged)" : result.business.replaced ? " (in place of the figures from an earlier file for the same dates)" : ""}.`}
              {result.problem_count > 0 && ` ${result.problem_count} line${result.problem_count === 1 ? "" : "s"} left out (below).`}
              {result.over_limit > 0 && ` Only the first ${rep?.max_trades.toLocaleString()} trades are kept.`}
            </p>
            {result.files.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>From the ZIP: {result.files.map((f) => `${f.section} (${f.lines.toLocaleString()} line${f.lines === 1 ? "" : "s"})`).join(", ")}.</p>}
            {result.check.length > 0 && (
              <ul className="tiny" style={{ margin: 0, paddingLeft: 18 }} aria-label="Totals checked against your broker's summary">
                {result.check.map((c, i) => (
                  <li key={i}>
                    {c.ok ? <>{c.section}: {inr(c.file)} {c.what === "turnover" ? "netted per contract" : "before charges"}, the same as your broker's summary sheet.</>
                      : c.file == null ? <span className="neg">{c.section}: your broker's summary shows {inr(c.summary)}, but the ZIP has no tradewise file for it, so it isn't included.</span>
                      : <span className="neg">{c.section}: {inr(c.file)} read, but your broker's summary sheet shows {inr(c.summary)}. Check the file is complete.</span>}
                  </li>
                ))}
              </ul>
            )}
            {result.skipped.length > 0 && (
              <div className="stack" style={{ gap: 2 }}>
                <p className="tiny muted" style={{ margin: 0 }}>Left out of the tax report:</p>
                <ul className="tiny muted" style={{ margin: 0, paddingLeft: 18 }} aria-label="Files left out">
                  {result.skipped.map((s, i) => <li key={i}><b>{s.name}</b>: {s.reason}</li>)}
                </ul>
              </div>
            )}
            {result.not_listed.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>No listed company matched {result.not_listed.slice(0, 8).join(", ")}{result.not_listed.length > 8 ? "…" : ""}. Their gains still count, without today's prices or bonus and split data.</p>}
            {result.problems.length > 0 && (
              <div className="table-wrap" style={{ margin: 0 }}>
                <table aria-label="Lines left out">
                  <thead><tr><th>Line</th><th>What the file says</th><th style={{ textAlign: "left" }}>Why</th></tr></thead>
                  <tbody>{result.problems.map((u, i) => <tr key={i}><td className="num">{u.line ?? "–"}</td><td>{u.text || "–"}</td><td style={{ textAlign: "left", whiteSpace: "normal" }} className="small muted">{u.reason}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
        {has && rep && rep.files.length > 0 && (
          <p className="tiny muted" style={{ margin: 0 }}>
            {rep.trades.toLocaleString()} trades{rep.business_lines > 0 && ` and ${rep.business_lines.toLocaleString()} F&O lines`} from {rep.files.length} file{rep.files.length === 1 ? "" : "s"}: {rep.files.map((f) => `${f.name} (${f.broker})`).join(", ")}{rep.updated_at ? ` · updated ${ago(rep.updated_at)}` : ""}
          </p>
        )}
      </section>

      {!rep && <Loading label="Opening your tax report" />}
      {rep && !has && (
        <Empty title="No trades yet">
          <p className="muted">Upload a tradebook or tax P&amp;L above to see your capital gains by financial year.</p>
        </Empty>
      )}

      {rep && has && y && (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between" }}>
            <label className="field" style={{ minWidth: 200 }}>Financial year
              <select value={fy ?? ""} onChange={(e) => { setFy(Number(e.target.value)); setAllSales(false); }} aria-label="Financial year">
                {rep.years.map((x) => <option key={x.fy} value={x.fy}>{x.label}{x.fy === rep.current_fy ? " (this year)" : ""}</option>)}
              </select>
            </label>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn quiet sm" disabled={!!getting} onClick={() => download("csv")}><Download size={16} />{getting === "csv" ? "Making the CSV…" : "Download CSV"}</button>
              <button className="btn quiet sm" disabled={!!getting} onClick={() => download("pdf")}><Download size={16} />{getting === "pdf" ? "Making the PDF…" : "Download PDF summary"}</button>
            </div>
          </div>

          <TotalCard y={y} onSave={saveInputs} filing={y.filing.length > 0} />
          <TaxToolsLink />

          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Short-term gains (net)</span><b className={`num ${signClass(y.stcg.net)}`}>{inr(y.stcg.net)}</b><span className="tiny muted">{inr(y.stcg.gains)} gains · {inr(y.stcg.losses)} losses</span></div>
            <div className="stat"><span className="tiny muted">Long-term gains (net)</span><b className={`num ${signClass(y.ltcg.net)}`}>{inr(y.ltcg.net)}</b><span className="tiny muted">{inr(y.ltcg.gains)} gains · {inr(y.ltcg.losses)} losses</span></div>
            <div className="stat"><span className="tiny muted">Long-term exemption used</span><b className="num">{inr(y.exemption.used)}</b>
              <span className="tiny muted">of {inr(y.exemption.limit)}{y.exemption.limit ? ` · ${inr(y.exemption.left)} left` : ""}</span>
              {y.exemption.limit > 0 && <div className="seg-bar" aria-hidden><i style={{ width: `${Math.max(0, Math.min(100, (y.exemption.used / y.exemption.limit) * 100))}%` }} /></div>}
            </div>
            <div className="stat"><span className="tiny muted">Tax on share gains <Info label="How the tax is estimated">Short-term gains on listed shares are taxed at 15% for sales before 23 July 2024 and 20% from that day; long-term gains (held more than 12 months) at 10% and 12.5%, above the yearly exemption. Shown before the 4% cess and any surcharge.</Info></span>
              <b className="num">{inr(y.tax)}</b><span className="tiny muted">{inr(y.tax_with_cess)} with 4% cess</span></div>
          </div>

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">How {y.label} adds up</h2>
            {y.buckets.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No capital gains or losses were realised in {y.label}.</p> : (
              <div className="table-wrap">
                <table aria-label="Gains by rate">
                  <thead><tr><th style={{ textAlign: "left" }}>Kind</th><th>Rate</th><th>Gains</th><th>After set-off</th><th>Exempt</th><th>Taxable</th><th>Tax</th></tr></thead>
                  <tbody>{y.buckets.map((b) => (
                    <tr key={b.key}><td style={{ textAlign: "left" }}>{b.label}</td><td className="num">{rate(b.rate, b.slab)}</td><td className="num">{inr(b.gains)}</td><td className="num">{inr(b.after_setoff)}</td>
                      <td className="num">{inr(b.exempt)}</td><td className="num">{inr(b.taxable)}</td><td className="num">{inr(b.tax)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {y.steps.length > 0 && <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{y.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
            {y.exempt_old != null && <p className="small muted" style={{ margin: 0 }}>Long-term results on sales before 1 April 2018 ({inr(y.exempt_old)}) were exempt under the old section 10(38), so they aren't counted.</p>}
            {y.gf_missing > 0 && <p className="small" style={{ margin: 0 }}><b>{y.gf_missing} sale{y.gf_missing === 1 ? "" : "s"}</b> of shares held on 31 Jan 2018 used the actual cost, because their 31 Jan 2018 price isn't known. Grandfathering could lower that gain; enter the price below.</p>}
            {y.gf_applied > 0 && <p className="small muted" style={{ margin: 0 }}>{y.gf_applied} sale{y.gf_applied === 1 ? " was" : "s were"} grandfathered: the cost is the higher of the actual cost and the 31 Jan 2018 price (but not above the sale value).</p>}
          </section>

          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h2">Intraday trades, kept apart</h2>
            <p className="small" style={{ margin: 0 }}>{y.intraday.count ? <>{y.intraday.count} same-day round trip{y.intraday.count === 1 ? "" : "s"}: purchases {inr(y.intraday.buy)}, sales {inr(y.intraday.sell)}, result <b className={signClass(y.intraday.pnl)}>{inr(y.intraday.pnl)}</b>.</> : `No intraday trades in ${y.label}.`}</p>
            <p className="tiny muted" style={{ margin: 0 }}>Shares bought and sold on the same day are speculative business income, taxed at your slab rate, not capital gains. They aren't in the capital gains above; they are in the total tax estimate.</p>
          </section>

          <BusinessCard y={y} />
          <UnitsCard units={y.units} notes={[]} name={name} label={y.label} />

          <MutualFundsCard y={y} mf={rep.mf} />
          <UsTaxCard us={y.us} label={y.label} trades={rep.us_trades} />

          {y.filing.length > 0 && (
            <section className="card stack" style={{ gap: 10 }} id="tax-filing">
              <h2 className="h2">Returns and tax audit</h2>
              <ul className="small" style={{ margin: 0, paddingLeft: 20 }} aria-label="Returns and tax audit">{y.filing.map((f, i) => <li key={i}>{f}</li>)}</ul>
              <p className="tiny muted" style={{ margin: 0 }}>The Income Tax Department's own page on returns for business income (ITR-3) and audit: <a className="link" href={ITR3_URL} target="_blank" rel="noopener noreferrer">incometax.gov.in</a>.</p>
            </section>
          )}

          {y.count > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}><h2 className="h2">Each sale, matched to its purchase</h2>
                <span className="row" style={{ gap: 10, flexWrap: "wrap" }}><span className="tiny muted">{y.count} line{y.count === 1 ? "" : "s"}</span>{salesMore.toggle}</span></div>
              <div className="table-wrap">
                <table aria-label="Realised sales">
                  <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Gain or loss</th><th>Term</th><th>Sold</th><th>Cost</th><th>Sale</th>
                    {salesMore.on && <><th>Bought</th><th>Qty</th><th>Rate</th></>}</tr></thead>
                  <tbody>{(allSales ? y.rows : y.rows.slice(0, 30)).map((r, i) => (
                    <tr key={i}>
                      <td style={{ textAlign: "left" }}><b>{name(r.key)}</b>{rep.kinds?.[r.key] && <> <span className="badge kind-etf">{rep.kinds[r.key]}</span></>}{r.bonus && <span className="tiny muted"> bonus</span>}{r.gf === "applied" && <span className="tiny muted"> grandfathered</span>}{r.gf === "missing" && <span className="tiny neg"> 31 Jan 2018 price missing</span>}</td>
                      <td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td><td>{r.term === "LT" ? "Long" : "Short"}</td>
                      <td className="num">{dateOnly(r.sold)}</td><td className="num">{inr(r.cost)}</td><td className="num">{inr(r.sale)}</td>
                      {salesMore.on && <><td className="num">{dateOnly(r.bought)}</td><td className="num">{qtyText(r.qty)}</td><td className="num">{rate(r.rate)}</td></>}
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              {y.rows.length > 30 && !allSales && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAllSales(true)}>Show all {y.rows.length}</button>}
              {y.count > y.rows.length && <p className="tiny muted" style={{ margin: 0 }}>The CSV download has all {y.count} lines.</p>}
              <p className="tiny muted" style={{ margin: 0 }}>Cost includes brokerage and charges from your files; sale is after them. STT isn't deductible, so it isn't included.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <h2 className="h2">Open lots below cost</h2>
              <Info label="What is tax-loss harvesting?">Tax-loss harvesting is a name for realising a loss on shares that are below their cost, so the loss can be set off against gains in the same financial year. India has no specific wash-sale rule today; shares bought again start a new holding period at the new price. Whether it suits anyone depends on their whole tax position, so check with a CA.</Info>
            </div>
            <p className="small muted" style={{ margin: 0 }}>Lots still open in your files that are worth less than they cost at today's price, and how long each has been held. Facts only: this is not a suggestion to do anything.</p>
            {rep.below_cost.rows.length === 0 ? <p className="small" style={{ margin: 0 }}>{rep.below_cost.open ? "No open lot is below its cost at today's price." : "Your files leave no shares open."}</p> : (
              <>
                <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
                  <p className="small" style={{ margin: 0 }}>Below cost now: <b className="neg">{inr(rep.below_cost.st)}</b> on short-term lots and <b className="neg">{inr(rep.below_cost.lt)}</b> on long-term lots.</p>
                  {lotsMore.toggle}
                </div>
                <div className="table-wrap">
                  <table aria-label="Open lots below cost">
                    <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Below cost by</th><th>Held</th><th style={{ textAlign: "left" }}>Term today</th><th>Bought</th>
                      {lotsMore.on && <><th>Qty</th><th>Cost a share</th><th>Price now</th></>}</tr></thead>
                    <tbody>{rep.below_cost.rows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ textAlign: "left" }}><Link className="link" to={`/research/IN/${encodeURIComponent(r.key)}`}><b>{name(r.key)}</b></Link>{r.bonus && <span className="tiny muted"> bonus</span>}</td>
                        <td className="num neg">{inr(r.loss)}{r.loss_pct != null && <span className="tiny"> {r.loss_pct.toFixed(1)}%</span>}</td>
                        <td className="num">{r.days} days</td>
                        <td className="small" style={{ textAlign: "left" }}>{r.term === "LT" ? "Long-term" : <>Short-term<div className="tiny muted">long-term from {dateOnly(r.long_from)}</div></>}</td>
                        <td className="num">{dateOnly(r.bought)}</td>
                        {lotsMore.on && <><td className="num">{qtyText(r.qty)}</td><td className="num">{price(r.cost_each, "INR")}</td><td className="num">{price(r.price, "INR")}</td></>}
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </>
            )}
            {rep.below_cost.unpriced > 0 && <p className="tiny muted" style={{ margin: 0 }}>{rep.below_cost.unpriced} open lot{rep.below_cost.unpriced === 1 ? " has" : "s have"} no price today{rep.prices ? " (not a listed company we could match)" : " (live prices are offline right now)"}.</p>}
            <AsOf parts={[["Prices", rep.prices_at]]} />
          </section>

          {(rep.holdings_check.length > 0 || rep.unmatched_sales.length > 0) && (
            <section className="card stack" style={{ gap: 10 }}>
              <h2 className="h2">Worth checking</h2>
              {rep.unmatched_sales.map((u) => (
                <p key={u.key} className="small" style={{ margin: 0 }}><b>{name(u.key)}</b>: {qtyText(u.qty)} shares sold (first on {dateOnly(u.first)}) with no matching purchase in your files. They may have been bought before your earliest file, moved in from another account, or come from a bonus or split older than our data. Their gain isn't counted; upload the older tradebook to include it.</p>
              ))}
              {rep.holdings_check.map((h) => (
                <p key={h.key} className="small" style={{ margin: 0 }}><b>{name(h.key)}</b>: your files leave {qtyText(h.files)} shares open; <Link className="link" to="/holdings">My Holdings</Link> has {qtyText(h.holdings)}.</p>
              ))}
            </section>
          )}

          {rep.pre_2018.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <h2 className="h2">Shares held on 31 Jan 2018</h2>
                <Info label="What is grandfathering?">For listed shares bought before 1 February 2018, the cost used for long-term gains is the higher of the actual cost and the share's highest price on 31 January 2018, but not more than the sale value. Gains made up to that day stay untaxed.</Info>
              </div>
              <div className="stack" style={{ gap: 10 }}>
                {rep.pre_2018.map((k) => <FmvRow key={k} symbol={name(k)} id={k} fmv={rep.fmv[k]} onSave={setFmv} />)}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>Looked-up prices come from stored price history and are adjusted for later bonuses and splits we know of. Check them against the exchange's 31 Jan 2018 price list, and enter your own if they differ.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h2">The set-off rules, in plain words</h2>
            <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{rep.rules.map((r, i) => <li key={i}>{r}</li>)}</ul>
            <h3 className="small" style={{ margin: "6px 0 0" }}>How this report works</h3>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{rep.notes.map((r, i) => <li key={i}>{r}</li>)}</ul>
            {!!rep.unit_notes?.length && <><h3 className="small" style={{ margin: "6px 0 0" }}>ETFs, REITs, InvITs and gold bonds</h3>
              <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }} aria-label="ETF, REIT, InvIT and gold bond rules">{rep.unit_notes.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
          </section>
        </>
      )}

      {rep && has && (
        <section className="stack" style={{ gap: 8 }}>
          <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Your trades are stored with your account only, used for this page, and never shared. Delete them at any time.</p>
          <button className="btn danger" style={{ alignSelf: "flex-start" }} onClick={remove}><Trash size={16} />Delete my tax data</button>
        </section>
      )}
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
    ["Capital gains", t.parts?.capital_gains ?? 0, "Tax on short- and long-term gains on listed shares and mutual funds, at the special rates (sections 111A, 112A and 112) or, for debt-fund gains, your slab rate, with its share of surcharge and cess."],
    ["Intraday", t.parts?.intraday ?? 0, "Intraday results are speculative business income, taxed at your slab rate. Slab tax is split between your incomes in proportion to each."],
    ["F&O", t.parts?.fno ?? 0, "F&O, commodity and currency results, after the charges in your files, are non-speculative business income, taxed at your slab rate."],
    ["Other income", t.parts?.other ?? 0, "Your salary, interest and other income as you entered it, after the standard deduction on salary."],
  ];
  return (
    <section className="card stack tax-total" style={{ gap: 14 }} aria-label="Total tax estimate">
      <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <h2 className="h2">Total tax estimate, {y.label}</h2>
        <Info label="What the total covers">Slab tax on your other income, intraday and F&amp;O results, plus tax on share gains at the special rates, less the section 87A rebate where it applies, plus surcharge and 4% cess. It is worked out for an individual of the age band and residency you choose below. Advance tax and TDS already paid aren't taken off.</Info>
      </div>
      <p className="small muted" style={{ margin: 0 }}>Covers only the income you enter or import here: the trades in your files and the other income you type below. House property, foreign income, other capital assets and anything else left out aren't counted.{filing && <> <a className="link" href="#tax-filing">Which return and whether a tax audit applies</a>.</>}</p>
      {t.confirmed === false && <p className="small neg" style={{ margin: 0 }} role="note"><b>Rules for this year not yet confirmed.</b> The figures repeat the year before until they are checked against the Finance Act.</p>}
      {t.available ? (
        <>
          <div className="stack" style={{ gap: 2 }}>
            <b className="num tax-big" aria-label="Estimated total tax">{inr(t.total)}</b>
            <span className="tiny muted">{REGIME[t.regime]} · {y.inputs.resident ? "resident" : "non-resident"}, aged {AGE_TEXT[y.inputs.age ?? "below60"]}{t.rebate > 0 ? ` · 87A rebate ${inr(t.rebate)}` : ""}{t.surcharge > 0 ? ` · surcharge ${inr(t.surcharge)}` : ""} · cess {inr(t.cess)}{!y.inputs.saved ? " · no other income entered yet" : ""}</span>
          </div>
          <div className="tax-chips" role="list" aria-label="Where the tax comes from">
            {chips.map(([label, v, info]) => (
              <div key={label} role="listitem" className="tax-chip"><span className="tiny muted">{label} <Info label={`About ${label}`}>{info}</Info></span><b className="num">{inr(v)}</b></div>
            ))}
          </div>
          {y.other_regime && <p className="tiny muted" style={{ margin: 0 }}>With the same figures, the {REGIME[y.other_regime.regime].toLowerCase()} works out to {inr(y.other_regime.total)}{y.other_regime.regime === "old" ? " (with the deductions entered, if any)" : ""}.</p>}
          {(t.notes ?? []).filter((n) => !/not yet confirmed/.test(n)).map((n) => <p key={n} className="small" style={{ margin: 0 }} role="note"><b>Note:</b> {n}</p>)}
          {(t.carry_forward.speculative > 0 || t.carry_forward.business > 0) && (
            <p className="small" style={{ margin: 0 }}>To carry forward:{t.carry_forward.speculative > 0 && <> intraday (speculative) loss <b className="neg">{inr(t.carry_forward.speculative)}</b> (4 years, against speculative income only)</>}{t.carry_forward.speculative > 0 && t.carry_forward.business > 0 && ";"}{t.carry_forward.business > 0 && <> business loss <b className="neg">{inr(t.carry_forward.business)}</b> (8 years, against business income)</>}. Only if the return is filed by its due date.</p>
          )}
        </>
      ) : <p className="small muted" style={{ margin: 0 }}>{t.reason}</p>}
      <InputsPanel key={y.fy} y={y} onSave={onSave} />
      {t.available && (
        <details className="tax-how" open>
          <summary>How we got here</summary>
          <ol className="small" style={{ margin: "8px 0 0", paddingLeft: 20 }}>{t.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {(t.notes ?? []).length > 0 && <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 20 }} aria-label="Notes on the estimate">{t.notes!.map((n) => <li key={n}>{n}</li>)}</ul>}
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table aria-label="Total tax breakdown">
              <tbody>{t.lines.map((l, i) => (
                <tr key={i} className={l.kind === "total" ? "tax-line-total" : l.kind === "subtotal" ? "tax-line-sub" : undefined}>
                  <td style={{ textAlign: "left", whiteSpace: "normal" }} className={l.kind === "note" ? "muted" : undefined}>{l.label}</td>
                  <td className={`num ${l.kind === "amount" ? signClass(l.amount) : ""}`}>{inr(l.amount)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
    </section>
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
    <div className="tax-inputs stack" style={{ gap: 10 }}>
      <b className="small">Your inputs for {y.label}</b>
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="small muted" style={{ fontWeight: 600 }}>Tax regime <Info label="About the tax regime">The new regime is the default from FY 2023-24: lower slab rates, a higher standard deduction and almost no deductions. The old regime keeps deductions such as 80C and 80D. Each year's return says which one applies.</Info></span>
          <div className="seg" role="radiogroup" aria-label="Tax regime">
            {(["new", "old"] as const).map((r) => <button key={r} role="radio" aria-checked={regime === r} aria-pressed={regime === r} onClick={() => setRegime(r)}>{r === "new" ? "New (default)" : "Old"}</button>)}
          </div>
        </div>
        <div className="stack" style={{ gap: 6 }}>
          <span className="small muted" style={{ fontWeight: 600 }}>Age <Info label="About age">Your age during the year. Under the old regime, the income not taxed is ₹2.5 lakh below 60, ₹3 lakh from 60 to 79 and ₹5 lakh from 80, for residents. The new regime's slabs are the same at every age.</Info></span>
          <div className="seg" role="radiogroup" aria-label="Age band">
            {AGES.map(([k, label]) => <button key={k} role="radio" aria-checked={age === k} aria-pressed={age === k} onClick={() => setAge(k)}>{label}</button>)}
          </div>
        </div>
        <div className="stack" style={{ gap: 6 }}>
          <span className="small muted" style={{ fontWeight: 600 }}>Resident in India? <Info label="About residency">Residency for tax depends mainly on the days spent in India in the year. A non-resident gets no section 87A rebate, can't set the unused basic exemption against share gains (sections 111A and 112A), and has the ₹2.5 lakh old-regime limit at any age. Surcharge and cess apply as usual. TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS.</Info></span>
          <div className="seg" role="radiogroup" aria-label="Resident in India">
            {([true, false] as const).map((r) => <button key={String(r)} role="radio" aria-checked={resident === r} aria-pressed={resident === r} onClick={() => setResident(r)}>{r ? "Yes" : "No"}</button>)}
          </div>
        </div>
        <label className="field" style={{ width: 200 }}>
          <span>Other income (₹) <Info label="About other income">Salary, pension, interest, rent and the like for the year, before deductions, as one number. Not the trades in your files: those are added from the files.</Info></span>
          <input value={other} inputMode="decimal" placeholder="e.g. 1200000" onChange={(e) => setOther(e.target.value)} aria-label="Other income" />
        </label>
        <label className="field" style={{ width: 200 }}>
          <span>Of which salary (₹) <Info label="About salary">Used for the standard deduction, which is only for salary and pension, and because business losses can't be set off against salary. Leave it blank if all of it is salary.</Info></span>
          <input value={salary} inputMode="decimal" placeholder="all of it" onChange={(e) => setSalary(e.target.value)} aria-label="Of which salary" />
        </label>
        {regime === "old" && (
          <label className="field" style={{ width: 200 }}>
            <span>Deductions (₹) <Info label="About deductions">80C, 80D, home-loan interest and the like, as one total. They reduce income taxed at slab rates, not share gains taxed at special rates.</Info></span>
            <input value={ded} inputMode="decimal" placeholder="e.g. 150000" onChange={(e) => setDed(e.target.value)} aria-label="Deductions" />
          </label>
        )}
        <button className="btn sm" disabled={bad || saving} onClick={save}>{saving ? "Saving…" : "Save and update"}</button>
      </div>
      {bad && <p className="tiny neg" style={{ margin: 0 }}>Enter amounts in rupees, 0 or more; the salary part can't be more than the other income.</p>}
    </div>
  );
}

/** F&O, commodity and currency for the year: the result, charges, turnover and the biggest underlyings. */
/** Mutual fund gains from the Money space: already counted above, summarised here. */
function MutualFundsCard({ y, mf }: { y: Year; mf?: Report["mf"] }) {
  const m = y.mutual_funds;
  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="Mutual funds">
      <h2 className="h2">Mutual funds</h2>
      {mf && !mf.allowed ? <p className="small" style={{ margin: 0 }}>Mutual fund capital gains are on the {mf.plan} plan. <Link className="link" to="/plans">See plans</Link></p>
        : !m ? <p className="small muted" style={{ margin: 0 }}>No mutual fund redemptions or switches in {y.label}. Upload your CAS on the <Link className="link" to="/money/mutual-funds">Mutual funds</Link> page to include them.</p>
        : (
          <>
            <p className="small" style={{ margin: 0 }}>{m.count} redemption{m.count === 1 ? "" : "s"} matched to purchase{m.count === 1 ? "" : "s"}, net <b className={signClass(m.gain)}>{inr(m.gain)}</b>: equity-oriented funds {inr(m.equity)}, gains at your slab rate {inr(m.slab)}, other long-term {inr(m.other_lt)}. They're in the gains, set-off and total tax estimate above.</p>
            {m.dividends > 0 && <p className="small muted" style={{ margin: 0 }}>Dividends paid out by your funds this year: {inr(m.dividends)}. They're income at your slab rate, not capital gains: include them in your other income above.</p>}
            <Link className="link small" to="/money/mutual-funds">See each scheme</Link>
          </>
        )}
    </section>
  );
}

function BusinessCard({ y }: { y: Year }) {
  const [all, setAll] = useState(false);
  const b = y.business;
  if (!b.segments.length) return (
    <section className="card stack" style={{ gap: 8 }}>
      <h2 className="h2">F&amp;O, commodity and currency</h2>
      <p className="small muted" style={{ margin: 0 }}>None in your files for {y.label}. Upload the tax P&amp;L ZIP from Zerodha (or its F&amp;O, commodity and currency files) to include them in the total.</p>
    </section>
  );
  const top = b.segments.flatMap((s) => s.by.map((u) => ({ ...u, seg: s.label })));
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <h2 className="h2">F&amp;O, commodity and currency</h2>
        <Info label="How F&O is taxed">Futures and options on shares and indices, and exchange-traded commodity and currency derivatives, are non-speculative business income, taxed at your slab rate. The charges in your files (brokerage, exchange charges, GST, stamp duty, STT and CTT) are business expenses and come off the result.</Info>
      </div>
      <div className="table-wrap">
        <table aria-label="F&O by segment">
          <thead><tr><th style={{ textAlign: "left" }}>Segment</th><th>Trades</th><th>Result</th><th>Charges</th><th>After charges</th><th>Turnover</th></tr></thead>
          <tbody>{b.segments.map((s) => (
            <tr key={s.seg}><td style={{ textAlign: "left" }}><b>{s.label}</b><div className="tiny muted">{dateOnly(s.first)} to {dateOnly(s.last)}</div></td>
              <td className="num">{s.trades.toLocaleString()}</td><td className={`num ${signClass(s.pnl)}`}>{inr(s.pnl)}</td><td className="num">{inr(s.charges)}</td>
              <td className={`num ${signClass(s.net)}`}>{inr(s.net)}</td><td className="num">{inr(s.turnover)}</td></tr>
          ))}</tbody>
          {b.segments.length > 1 && <tfoot><tr><td style={{ textAlign: "left" }}><b>Total</b></td><td className="num">{b.trades.toLocaleString()}</td><td className={`num ${signClass(b.pnl)}`}>{inr(b.pnl)}</td><td className="num">{inr(b.charges)}</td><td className={`num ${signClass(b.net)}`}><b>{inr(b.net)}</b></td><td className="num">{inr(b.turnover)}</td></tr></tfoot>}
        </table>
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>Turnover is the total of profits and losses, trade by trade ({inr(b.turnover)}). Netted per contract first, as broker summaries often show it, it is {inr(b.turnover_contract)}. Your files' lines aren't kept, only these totals.</p>
      {top.length > 0 && (
        <>
          <div className="table-wrap">
            <table aria-label="F&O by underlying">
              <thead><tr><th style={{ textAlign: "left" }}>Underlying</th><th>Segment</th><th>Trades</th><th>Result</th></tr></thead>
              <tbody>{(all ? top : top.slice(0, 8)).map((u, i) => (
                <tr key={i}><td style={{ textAlign: "left" }}>{u.u}</td><td className="small">{u.seg}</td><td className="num">{u.trades.toLocaleString()}</td><td className={`num ${signClass(u.pnl)}`}>{inr(u.pnl)}</td></tr>
              ))}</tbody>
            </table>
          </div>
          {top.length > 8 && !all && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAll(true)}>Show all {top.length}</button>}
        </>
      )}
    </section>
  );
}

function FmvRow({ symbol, id, fmv, onSave }: { symbol: string; id: string; fmv?: { value: number | null; source: string | null }; onSave: (symbol: string, value: number | null) => void }) {
  const [v, setV] = useState("");
  const n = Number(v.replace(/,/g, ""));
  const where = fmv?.source === "yours" ? "your price" : fmv?.source === "your file" ? "from your broker's file" : fmv?.source === "looked up" ? "looked up" : "not known";
  return (
    <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
      <div className="stack" style={{ gap: 2, minWidth: 160 }}>
        <b>{symbol}</b>
        <span className="tiny muted">{fmv?.value ? `${price(fmv.value, "INR")} a share, ${where}` : where === "from your broker's file" ? "from your broker's file" : "31 Jan 2018 price not known"}</span>
      </div>
      <label className="field" style={{ width: 170 }}>Your 31 Jan 2018 price (₹)<input value={v} inputMode="decimal" placeholder="e.g. 310.50" onChange={(e) => setV(e.target.value)} /></label>
      <button className="btn quiet sm" disabled={!(n > 0)} onClick={() => { onSave(id, n); setV(""); }} aria-label={`Save the 31 Jan 2018 price for ${symbol}`}>Save</button>
      {fmv?.source === "yours" && <button className="btn quiet sm" onClick={() => onSave(id, null)} aria-label={`Clear my price for ${symbol}`}>Clear</button>}
    </div>
  );
}

/** Where the dividends, advance tax and long-term exemption tools are. */
function TaxToolsLink() {
  return (
    <section className="card stack" style={{ gap: 6 }} aria-label="Tax tools">
      <h2 className="h2">Dividends, advance tax and the long-term exemption</h2>
      <p className="small muted" style={{ margin: 0 }}>Dividend income with the TDS on it (and whether it goes into the estimate above), the advance tax due by each date with TDS and payments taken off, and how much of this year's long-term exemption is used.</p>
      <Link className="btn quiet sm" style={{ alignSelf: "flex-start" }} to="/money/tax-tools">Open tax tools</Link>
    </section>
  );
}
