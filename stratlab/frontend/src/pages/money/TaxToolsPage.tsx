import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf as asOfText, dateOnly, inr, money, qty as qtyText, signTone } from "../../lib/format";
import { Info } from "../../components/ui";
import { Lock, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Badge, Card, CardHead, type Column, ConfirmDialog, DataTable, DateField, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, Meter, Notice, PageHeader, PlanNote, Seg, Select, Skeleton, Stat, StatRow, UploadButton, UploadProblem, useUploadProblem } from "../../components/kit";
import { fyLink, movedYearNote, openFy } from "../../lib/fy";
import { useAskedFy } from "../../lib/useFy";
import { usSharesNote } from "../../lib/usGains";
import { b234Note } from "../../lib/advanceTax";

/* /money/tax-tools: dividends and the TDS on them, advance tax by date, and the long-term exemption, built on the tax
 * report and My Holdings. Estimates and arithmetic on the user's own figures. Built from the kit (components/kit). */

// ---------- what the server sends ----------
type Company = {
  symbol: string; name: string; country: "IN" | "US"; count: number; amount: number; amount_usd: number | null; tds_file: number | null;
  first: string; last: string; tds_expected?: number; over_threshold?: boolean; withheld_usd?: number; withheld?: number;
};
type DivYear = {
  fy: number; label: string; total: number; india_total: number; us_total: number; count: number; companies_count: number; unpriced: number; taxed: boolean;
  tds: { threshold: number | null; rate: number; section: string; note?: string | null; expected: number; companies_over: number; in_file: number | null };
  us: { gross_usd: number; gross: number; rate: number; withheld_usd: number; withheld: number } | null;
  companies: Company[]; locked: boolean; source: "files" | "estimated" | "none"; include: boolean; include_saved: boolean; estimate_total: number | null; ais_note?: string | null;
};
type Ahead = { symbol: string; ex_date: string; label: string | null; qty: number; per_share: number; currency: string; amount: number };
type Dividends = {
  years: DivYear[]; current_fy: number; files: { name: string; source: string; rows: number; at: string }[]; updated_at: string | null;
  ahead: Ahead[];
  ahead_total: number; usd_inr: number | null; as_of: string; assumptions: string[]; locked: boolean;
  /** Held stocks whose declared dividends are still being read (the estimate leaves them out until then). */
  checking?: number;
};
type DueDate = { n: number; date: string; pct: number; label: string };
type Instalment = DueDate & {
  base: number; required: number; paid: number; short: number; to_pay: number; interest_234c: number; interest_if_missed: number; months: number;
  tolerated: boolean; status: "passed" | "next" | "later";
};
type Schedule = {
  fy: number; label: string; tax: number; tds: number; net: number; due: boolean; threshold: number; instalments: Instalment[]; next: number | null; paid: number;
  interest_234c: number; b234: { applies: boolean; paid: number; ninety_pct: number; short: number; months: number; until: string; interest: number;
    self_assessment?: number; unpaid?: number; fully_paid?: boolean; to_today?: boolean }; steps: string[];
};
type Payment = { d: string; amount: number };
/** A past year's tax with what's paid taken off and the interest added, as one figure (DH-003). */
type Payable = {
  fy: number; label: string; tax: number; tds: number; advance: number; self_assessment: number; balance: number; refund: number;
  interest_234a: number; interest_234b: number; interest_234c: number; fee_234f: number; total: number; due: string; on: string; past_due: boolean;
  return_needed?: boolean; income?: number; exempt?: number;
  lines: { label: string; amount: number }[];
};
type Advance = {
  fy: number; label: string; dates: DueDate[]; remind: boolean; locked: boolean; as_of: string; assumptions: string[]; threshold: number; current_fy: number;
  /** the reminders are the money calendar's, on Basic (DP2-004) */
  remind_locked?: boolean; remind_plan?: string;
  schedule?: Schedule; inputs?: { tds: number; paid: Payment[] }; dividends_in_estimate?: number; dividend_tds?: number; income_saved?: boolean;
  payable?: Payable | null; return_due?: string; audit?: boolean;
  /** a year before the one shown still owes tax (DH-020) */
  owed?: { fy: number; label: string; total: number; balance: number; due: string }; opened_on_owed?: boolean;
  /** every plan: the shares of the tax report's total by each date (DH-021) */
  plain?: { tax: number; due: boolean; rows: (DueDate & { amount: number })[] };
};
type LtLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; gain: number; grandfathered: boolean; bonus: boolean; text: string };
type SoonLot = LtLot & { long_from: string; days_left: number; window: number };
type BelowLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; loss: number; loss_pct: number | null; days: number; term: "ST" | "LT"; long_from: string | null };
type Ltcg = {
  fy: number; label: string; as_of: string; exemption: { limit: number; used: number; left: number; realised_lt_net: number; realised_st_net: number; realised_us_lt_net?: number; realised_us_st_net?: number };
  /** null while locked: a locked figure is no figure, never a false 0 (DP2-003) */
  open_lt: { lots: number; gains: number; losses: number; with_gain: number } | null; soon_counts: Record<string, number> | null; long: LtLot[]; soon: SoonLot[];
  unpriced: number; facts: string[]; locked: boolean; below_cost: { rows: BelowLot[]; unpriced: number; open: number; st: number; lt: number };
  names: Record<string, { symbol: string }>; prices: boolean; trades: number;
};

const usd = (v: number | null | undefined) => money(v, "USD", 2);
// DH-022: on a phone the third tab's short name keeps the three on one line
const TABS = [["dividends", "Dividends", undefined], ["advance", "Advance tax", undefined], ["ltcg", "Long-term exemption", "Exemption"]] as const;
type Tab = (typeof TABS)[number][0];
const DISCLAIMER = "Estimates and arithmetic on your own figures, not tax advice. Check them with a chartered accountant (CA) before you file or pay tax.";
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };
const Dated = ({ label, iso }: { label: string; iso: string | null | undefined }) => (asOfText(iso) ? <p className="k-note">{label} {asOfText(iso)}.</p> : null);

export function TaxToolsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find(([t]) => t === params.get("tab"))?.[0]) ?? "dividends";
  const go = (t: Tab) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", t); return n; }, { replace: true });
  return (
    // each tab says its own lock in the same place, at its top (DP2-012: the page's note showed on two tabs and an inline one on
    // the third); the dividend detail is Basic, the amounts and lots Pro, so one page note can't say both
    <div className="k-page" data-plan-notes="own">
      <PageHeader eyebrow="Money · Tax" title="Dividends, advance tax and the long-term exemption"
        lede={<>Built on your <Link className="link" to="/tax-report">tax report</Link> and <Link className="link" to="/holdings">holdings</Link>: the dividends you received, the advance tax due by each date, and how much of this year's long-term exemption is used.</>}
        info="The dividends you received and the TDS on them, the advance tax due by each date, and how much of this year's long-term gains exemption is used. Only you can see these figures." infoLabel="What these tools cover" />
      <Notice label="Estimate only"><b>Estimate only.</b> {DISCLAIMER}</Notice>
      <Seg label="Tax tools" options={TABS.map(([value, label, short]) => ({ value, label, short }))} value={tab} onChange={(t) => go(t as Tab)} />
      {tab === "dividends" && <DividendsTab />}
      {tab === "advance" && <AdvanceTab />}
      {tab === "ltcg" && <LtcgTab />}
    </div>
  );
}

const yearOptions = (years: { fy: number; label: string }[], current: number) => years.map((x) => ({ value: x.fy, label: `${x.label}${x.fy === current ? " (this year)" : ""}` }));
const loading = (label: string) => <Card><Skeleton label={label} /></Card>;
/** A first load that failed: what happened and a way to try again, not a skeleton for ever. */
const failedLoad = (title: string, message: string, retry: () => void) => <ErrorState title={title} action={{ label: "Try again", onClick: retry }}>{message}</ErrorState>;

// ---------- dividends ----------
const DIVIDEND_INFO = "Upload your broker's dividend statement as CSV or Excel, with columns for the date, the company (symbol, name or ISIN) and the amount (or quantity and dividend a share); TDS and currency are optional (USD for US dividends). A tax P&L ZIP uploaded to the tax report brings its dividend sheet too. Without a file, the year is estimated from your holdings and the dividends the companies declared.";

function DividendsTab() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<Dividends | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [fy, setFy] = useState<number | null>(null);
  const [movedFrom, setMovedFrom] = useState<number | null>(null);      // the empty year it opened past, if it did
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const asked = useAskedFy();             // a link's year ("?fy=2026", from My Holdings) is the year it opens on
  const show = useCallback((d: Dividends) => {
    setV(d);
    // the Money pages' one rule (lib/fy openFy): the year being filed, or the latest year with dividends when that has none
    setFy((cur) => {
      if (cur != null) return cur;
      const o = openFy(d.years.map((y) => y.fy), d.current_fy, (fy) => d.years.some((y) => y.fy === fy && y.count > 0), undefined, asked);
      setMovedFrom(o.from);
      return o.fy;
    });
  }, [asked]);
  useEffect(() => {
    let live = true;
    setError(null);
    api<Dividends>("/money/dividends").then((d) => live && show(d)).catch((e) => { if (!live) return; setError((e as Error).message); fail(e); });
    return () => { live = false; };
  }, [show, fail, tries]);

  const { problem, clear: clearProblem, refused } = useUploadProblem();     // a refused file's reason stays beside the upload (RC6-010)
  const pick = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { notify("That file is larger than 10 MB."); reset(); return; }
    setBusy(true); clearProblem();
    try {
      const r = await api<{ read: number; added: number; duplicates: number; problems: { line: number; text: string; reason: string }[]; date_note?: string | null; dividends: Dividends }>(
        `/money/dividends/import?${new URLSearchParams({ filename: f.name.slice(0, 200) })}`, { method: "POST", file: f });
      setNote(`${r.added} dividend${r.added === 1 ? "" : "s"} added${r.duplicates ? `, ${r.duplicates} already there (skipped)` : ""}${r.problems.length ? `, ${r.problems.length} line${r.problems.length === 1 ? "" : "s"} left out` : ""}.${r.date_note ? ` ${r.date_note}` : ""}`);
      setFy(null);
      show(r.dividends);
      track("dividends imported", { rows: r.added });
    } catch (e) { if (!refused(e)) fail(e); } finally { setBusy(false); reset(); }
  };
  const include = async (year: number, on: boolean) => {
    try { show(await api<Dividends>("/money/dividends/include", { method: "PUT", body: { fy: year, include: on } })); notify(on ? "Included in the total tax estimate." : "Left out of the total tax estimate."); }
    catch (e) { fail(e); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api("/money/dividends", { method: "DELETE" }); setNote(null); setFy(null); show(await api<Dividends>("/money/dividends")); notify("Your uploaded dividends are deleted."); }
    catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };

  if (!v) return error ? failedLoad("Your dividends couldn't be read", error, () => setTries((n) => n + 1)) : loading("Adding up your dividends");
  const y = v.years.find((x) => x.fy === fy) ?? v.years[0];
  const companyCols: Column<Company>[] = [
    { key: "co", header: "Company", rowHeader: true, cell: (c) => <><b>{c.symbol}</b>{c.country === "US" && <span className="k-note"> US</span>}</> },
    { key: "n", header: "Payments", numeric: true, cell: (c) => c.count },
    { key: "amt", header: "Amount", numeric: true, cell: (c) => <>{inr(c.amount)}{c.amount_usd != null && <span className="k-sub-line">{usd(c.amount_usd)}</span>}</> },
    { key: "tds", header: "TDS expected", numeric: true, cell: (c) => (c.country === "IN" ? inr(c.tds_expected) : "–") },
    { key: "us", header: "US tax withheld", numeric: true, cell: (c) => (c.country === "US" ? usd(c.withheld_usd) : "–") },
  ];
  const aheadCols: Column<Ahead>[] = [
    { key: "s", header: "Stock", rowHeader: true, cell: (a) => <><b>{a.symbol}</b><span className="k-sub-line">{a.label ?? "Dividend"}</span></> },
    { key: "ex", header: "Ex-date", numeric: true, cell: (a) => dateOnly(a.ex_date) },
    { key: "q", header: "Shares", numeric: true, cell: (a) => qtyText(a.qty) },
    { key: "ps", header: "A share", numeric: true, cell: (a) => money(a.per_share, a.currency === "USD" ? "USD" : "INR", 2) },
    { key: "amt", header: "Amount", numeric: true, cell: (a) => money(a.amount, a.currency === "USD" ? "USD" : "INR", 0) },
  ];
  const uploadBtn = <UploadButton label="Upload dividends" busy={busy} accept=".csv,.xlsx,.txt,.zip,text/csv" ariaLabel="Dividend file" onFiles={pick} />;
  const deleteBtn = v.files.length > 0 ? <button type="button" className="btn quiet sm" onClick={() => setAsking(true)}><Trash size={16} />Delete uploaded dividends</button> : null;
  return (
    <>
      {v.locked && <PlanNote>Dividends by company, with the TDS expected and the US tax withheld, are on the Basic plan.</PlanNote>}
      {/* VR1-146: with a year to show, the upload button sits in that year's card head (it was a card of its own, a title and one button, above a card
          titled "Dividends, FY …"); with none, the card stays so the file can still be uploaded */}
      {!y && (
        <Card compact={!note && v.files.length === 0}>
          <CardHead title="Your dividends" info={DIVIDEND_INFO} actions={uploadBtn} />
          {note && <p className="k-small" role="status">{note}</p>}
          <UploadProblem problem={problem} />
          {v.files.length > 0 && <p className="k-note">From {v.files.map((f) => f.name).join(", ")}. {deleteBtn}</p>}
        </Card>
      )}

      {y && (
        <>
          {(v.checking ?? 0) > 0 && <p className="k-note" data-testid="dividends-checking">Still reading the dividends of {v.checking} stock{v.checking === 1 ? "" : "s"}; the estimate leaves {v.checking === 1 ? "it" : "them"} out until then. Reload in a minute.</p>}
          <Card label="Dividends for the year">
            <CardHead title={`Dividends, ${y.label}`} info={DIVIDEND_INFO} infoLabel="About your dividends" actions={<>
              {y.source === "files" && <Badge>From your files</Badge>}
              {y.source === "estimated" && <Badge>Estimated</Badge>}
              <Select small label="Financial year" value={y.fy} onChange={(x) => { setFy(Number(x)); setMovedFrom(null); }} options={yearOptions(v.years, v.current_fy)} />
              {uploadBtn}
            </>} />
            {note && <p className="k-small" role="status">{note}</p>}
            <UploadProblem problem={problem} />
            {v.files.length > 0 && <p className="k-note">From {v.files.map((f) => f.name).join(", ")}. {deleteBtn}</p>}
            {movedFrom != null && movedFrom !== y.fy && <p className="k-small k-muted" data-testid="dividends-moved-year">{movedYearNote(movedFrom, y.fy, v.current_fy, "dividends")}</p>}
            {y.source !== "none" && y.taxed && (
              <FieldGroup label="In the total tax estimate" info="Whether this year's dividends are counted as income in the total tax estimate on the tax report.">
                <Seg label="In the total tax estimate" options={[{ value: "in", label: "Include in the tax estimate" }, { value: "out", label: "Leave out" }]} value={y.include ? "in" : "out"} onChange={(x) => include(y.fy, x === "in")} />
              </FieldGroup>
            )}
            {y.source === "none" ? <EmptyState title={`No dividends in ${y.label}`}>No dividends in your files or holdings for the year. Upload a dividend statement above to add them.</EmptyState> : (
              <>
                <StatRow>
                  <Stat label="Dividend income" value={<span aria-label="Dividend income">{inr(y.total)}</span>} note={`${y.count} payment${y.count === 1 ? "" : "s"} from ${y.companies_count} compan${y.companies_count === 1 ? "y" : "ies"}${!y.us ? (y.tds.threshold != null ? ` · TDS above ${inr(y.tds.threshold)} a company` : " · exempt that year") : ""}`} />
                  {/* RC2B-046: with no US dividends the Indian total is the income above, the same figure twice; its note goes under the income */}
                  {y.us && <Stat label="Indian companies" value={inr(y.india_total)} note={y.tds.threshold != null ? `TDS above ${inr(y.tds.threshold)} a company` : "Exempt that year"} />}
                  {!y.locked && y.tds.threshold != null && (
                    <Stat label={<>TDS expected <Info label="About TDS on dividends">A company cuts {+(y.tds.rate * 100).toFixed(2)}% TDS (20% without a PAN) from a resident once its dividends to you in the year are over the threshold, on the whole amount: {inr(y.tds.threshold)} for {y.label} under {y.tds.section}.{y.tds.note ? ` ${y.tds.note}` : ""} Form 26AS or the AIS shows what was actually cut.</Info></>}
                      value={inr(y.tds.expected)} note={`${y.tds.companies_over} compan${y.tds.companies_over === 1 ? "y" : "ies"} over the threshold${y.tds.in_file != null ? ` · ${inr(y.tds.in_file)} in your file` : ""}`} />
                  )}
                  {!y.locked && y.us && (
                    <Stat label={<>US dividends <Info label="About US dividends">The US withholds 25% under the India-US tax treaty (with a W-8BEN). In India the dividend is taxed at your slab rate, and the US tax can be claimed as a foreign tax credit, up to the Indian tax on that income, by filing Form 67 by the end of the assessment year (31 March {y.fy + 2}; Rule 128(9)).</Info></>}
                      value={inr(y.us.gross)} note={`${usd(y.us.gross_usd)} · US tax withheld ${usd(y.us.withheld_usd)} (${inr(y.us.withheld)}), the foreign tax credit figure`} />
                  )}
                </StatRow>
                {/* RC2B-046: the choice is the switch above; this line says only what it does, once */}
                <p className="k-small">{y.taxed ? (y.include
                  ? <>Counted in the <Link className="link" to={fyLink("/tax-report", y.fy)}>total tax estimate</Link> as income from other sources, at your slab rate.</>
                  : <>Not counted in the <Link className="link" to={fyLink("/tax-report", y.fy)}>total tax estimate</Link>{y.source === "estimated" ? " until you include it" : ""}.</>)
                  : "Dividends were exempt in your hands before FY 2020-21 (the company paid dividend distribution tax)."}</p>
                <p className="k-note">Added up by financial year, each payment in the year of its record date. <Link className="link" to="/holdings">My Holdings</Link> shows the last 12 months instead, a different slice of the same dividends.</p>
                {y.source === "files" && y.estimate_total != null && <p className="k-note">From your holdings, the estimate for {y.label} is {inr(y.estimate_total)}.</p>}
                {y.ais_note && <p className="k-note">{y.ais_note}</p>}
                {y.unpriced > 0 && <p className="k-note">{y.unpriced} US payment{y.unpriced === 1 ? " isn't" : "s aren't"} counted: the dollar rate isn't available right now.</p>}
                {!y.locked && y.companies.length > 0 && <DataTable label="Dividends by company" columns={companyCols} rows={y.companies} rowKey={(c) => `${c.country}${c.symbol}`} />}
              </>
            )}
          </Card>
        </>
      )}

      {v.ahead.length > 0 && (
        <Card>
          <CardHead title="Declared, ex-date still ahead" info="Not counted above until paid." />
          <p className="k-small k-muted">{inr(v.ahead_total)} at the shares you hold now.</p>
          <DataTable label="Dividends declared, ex-date ahead" columns={aheadCols} rows={v.ahead} rowKey={(a) => `${a.symbol}${a.ex_date}${a.label}`} />
        </Card>
      )}

      <Card>
        <CardHead title="How these are worked out" />
        <ul className="k-list muted">{v.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <Dated label="Dividends as of" iso={v.as_of} />
      </Card>
      {asking && <ConfirmDialog title="Delete the dividends you uploaded?" confirmLabel="Delete uploaded dividends" busy={busy} onConfirm={() => void remove()} onClose={() => setAsking(false)}>The estimate from your holdings stays, as it is worked out each time.</ConfirmDialog>}
    </>
  );
}

// ---------- advance tax ----------
const num = (s: string) => { const n = Number(s.replace(/[,\s₹]/g, "")); return s.trim() === "" ? 0 : Number.isFinite(n) && n >= 0 ? n : NaN; };

function AdvanceTab() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<Advance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [fy, setFy] = useState<number | null>(null);
  const asked = useAskedFy();
  // Advance tax is paid during the year, so it opens on the year running now; a year asked for by a link carries here when
  // this page has it (this year and the one before); a year picked on another page does not (RC2B-002)
  useEffect(() => {
    let live = true;
    setError(null);
    api<Advance>(`/money/advance-tax${fy ? `?fy=${fy}` : ""}`).then((a) => {
      if (!live) return;
      const want = fy == null ? asked : null;
      if (want != null && want !== a.fy && (want === a.current_fy || want === a.current_fy - 1)) setFy(want);
      else setV(a);
    }).catch((e) => { if (!live) return; setV(null); setError((e as Error).message); fail(e); });     // not the last year's schedule under this year's chip
    return () => { live = false; };
  }, [fy, fail, asked, tries]);
  const remind = async (on: boolean) => {
    try { await api("/money/advance-tax/reminders", { method: "PUT", body: { on } }); setV((x) => (x ? { ...x, remind: on } : x)); notify(on ? "Reminders on: 7 days and 1 day before each date." : "Reminders off."); }
    catch (e) { fail(e); }
  };
  if (!v) return error ? failedLoad("The instalments couldn't be worked out", error, () => setTries((n) => n + 1)) : loading("Working out the instalments");
  const s = v.schedule;
  const cols: Column<Instalment>[] = [
    { key: "by", header: "By", rowHeader: true, cell: (r) => <><b>{r.label}</b>{r.status === "next" && <span className="k-note"> next</span>}</> },
    { key: "share", header: "Share", numeric: true, cell: (r) => `${Math.round(r.pct * 100)}%` },
    { key: "req", header: "Due by then", numeric: true, cell: (r) => inr(r.required) },
    { key: "paid", header: "Paid by then", numeric: true, cell: (r) => inr(r.paid) },
    { key: "short", header: "Short", numeric: true, cell: (r) => <><span className={r.short > 0 ? "k-down" : undefined}>{r.short > 0 ? inr(r.short) : "–"}</span>{r.tolerated && <span className="k-sub-line">within {r.n === 0 ? "12%" : "36%"}</span>}</> },
    { key: "int", header: "234C interest", numeric: true, cell: (r) => (r.status === "passed" ? inr(r.interest_234c) : r.interest_if_missed > 0 ? <span className="k-note">{inr(r.interest_if_missed)} if not paid</span> : "–") },
  ];
  const today = v.as_of.slice(0, 10);
  const nextDue = v.dates.find((d) => d.date >= today)?.n;
  return (
    <>
      {/* DH-021: the shares of the year's tax are shown on every plan (below); what Pro adds is said as itself */}
      {v.locked && <PlanNote>Taking off your TDS and payments, the amount still due by each date and the interest under sections 234A, 234B and 234C are on the Pro plan.</PlanNote>}
      {/* DH-020: a year before still owes tax: said at the top, with a way to it */}
      {v.owed && v.owed.fy !== v.fy && (
        <Notice label="Tax still unpaid" action={{ label: `Show ${v.owed.label}`, onClick: () => setFy(v.owed!.fy) }}>
          <b>{v.owed.label}: {inr(v.owed.total)} still unpaid</b>, with the interest on it. Self-assessment tax is paid before the return is filed (section 140A); the return's due date is {dateOnly(v.owed.due)}.
        </Notice>
      )}
      <FormGrid label="Year and reminders">
        <Field label="Financial year">{(id) => (
          <Select id={id} value={v.fy} onChange={(x) => setFy(Number(x))} options={[v.current_fy, v.current_fy - 1].map((x) => ({ value: x, label: `FY ${x}-${String(x + 1).slice(2)}${x === v.current_fy ? " (this year)" : ""}` }))} />
        )}</Field>
        {/* a short label that fits its column; how they come is behind the (i) (DP2-013: "Reminders by email and ph…") */}
        <FieldGroup label="Reminders" infoLabel="About advance tax reminders" info="By email and phone, 7 days and 1 day before each due date: to your confirmed email address and any phone notifications you set up in Account. Dates only: no amounts are sent.">
          {v.remind_locked
            ? <p className="k-small k-muted" data-testid="advance-remind-locked"><Lock />On the {v.remind_plan ?? "Basic"} plan</p>
            : <Seg label="Advance tax reminders" options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]} value={v.remind ? "on" : "off"} onChange={(x) => remind(x === "on")} />}
        </FieldGroup>
      </FormGrid>
      {v.remind_locked && <PlanNote plan="basic">Advance tax reminders are on the {v.remind_plan ?? "Basic"} plan, with the money calendar's other reminders.</PlanNote>}

      {v.opened_on_owed && <p className="k-small k-muted" data-testid="advance-owed-year">Opened on {v.label}: its tax is still unpaid. Pick {`FY ${v.current_fy}-${String(v.current_fy + 1).slice(2)}`} above for this year's instalments.</p>}
      {s && v.payable && <PayableCard p={v.payable} />}

      <Card label="Advance tax due dates">
        <CardHead title={`Due dates, ${v.label}`} info={`Advance tax is due when the year's tax less TDS is ${inr(v.threshold)} or more (section 208; section 404 of the Income-tax Act, 2025 from FY 2026-27).`} />
        {/* a date already gone is marked, and the next one (DP2-013: 15 Jun and 15 Sep showed as if still ahead) */}
        <ul className="k-list" aria-label="Due dates">
          {v.dates.map((d) => <li key={d.n} className={d.date < today ? "k-muted" : undefined}><b>{d.label}</b>: {d.pct * 100}% of the year's tax (less TDS), counting what was paid before
            {v.plain && v.plain.tax > 0 && <> · {inr(v.plain.rows[d.n]?.amount)} of the {inr(v.plain.tax)} on your tax report, before TDS</>}
            {d.date < today ? <span className="k-note"> · passed</span> : d.n === nextDue ? <span className="k-note"> · next</span> : null}</li>)}
        </ul>
      </Card>

      {s && v.inputs && (
        <>
          <Card label="Advance tax amounts">
            <CardHead title="What is due" />
            <StatRow>
              <Stat label="Tax for the year (estimate)" value={<span aria-label="Tax for the year">{inr(s.tax)}</span>}
                note={<>from the <Link className="link" to={fyLink("/tax-report", v.fy)}>tax report</Link>{v.income_saved ? "" : ", no other income entered"}{v.dividends_in_estimate ? ` · ${inr(v.dividends_in_estimate)} of dividends in it` : ""}</>} />
              <Stat label="Less TDS" value={inr(s.tds)} note="as you entered it" />
              <Stat label="Advance tax for the year" value={<span aria-label="Advance tax for the year">{s.due ? inr(s.net) : "None due"}</span>} note={s.due ? `${inr(s.paid)} paid so far` : `below ${inr(s.threshold)}`} />
              {s.due && <Stat label="Interest so far (234C)" value={inr(s.interest_234c)} tone={s.interest_234c > 0 ? "down" : undefined} note="on instalments already due" />}
              {s.b234.applies && <Stat label="Interest (234B)" value={inr(s.b234.interest)} tone="down" note={b234Note(s.b234, inr)} />}
            </StatRow>
            {s.due && <DataTable label="Instalments" columns={cols} rows={s.instalments} rowKey={(r) => String(r.n)} />}
            <ol className="k-list">{s.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>
          </Card>
          <PaymentsForm key={v.fy} v={v} onSaved={setV} />
        </>
      )}

      <Card>
        <CardHead title="The rules, in plain words" />
        <ul className="k-list">
          <li>15% of the year's tax less TDS by 15 June, 45% by 15 September, 75% by 15 December and all of it by 15 March.</li>
          <li>Capital gains and dividends that arise after a due date go into the instalments still to come (by 31 March when none is left), without interest when paid by then.</li>
          <li>Section 234C: 1% a month on each instalment's shortfall, for 3 months (1 month for March). None for June when 12% was paid by then, none for September when 36% was.</li>
          <li>Section 234B: when advance tax paid by 31 March is under 90% of the tax, 1% a month on the shortfall from 1 April until it is paid. A self-assessment payment (one dated after 31 March) stops it on the amount paid.</li>
          <li>From FY 2026-27 the Income-tax Act, 2025 numbers these sections 404 (who pays), 424 (234B) and 425 (234C).</li>
        </ul>
        {/* the assumptions under their own heading, in the same size as the rules above them (DP2-013: two sizes of bullet) */}
        <h3 className="k-sub">Assumptions</h3>
        <ul className="k-list">{v.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <Dated label="Worked out" iso={v.as_of} />
      </Card>
    </>
  );
}

/** DH-003: what a past year still needs, as one figure, with each line that makes it up. */
function PayableCard({ p }: { p: Payable }) {
  return (
    <Card label="Payable now">
      <CardHead title={`Payable now, ${p.label}`} info="The tax as the return rounds it, less the TDS and the advance and self-assessment tax you entered, plus interest under sections 234A (a late return), 234B and 234C, and the section 234F fee once the due date has passed. The whole is rounded to ₹10 as the return rounds it (section 288B)." />
      <b className="k-big" aria-label="Payable now">{inr(p.total)}</b>
      {p.return_needed === false && <p className="k-note" data-testid="payable-no-return">No return is needed for {p.label}: total income {inr(p.income ?? 0)} is within the {inr(p.exempt ?? 0)} basic exemption limit (section 139(1)), so there is no section 234F late fee.</p>}
      <p className="k-note">{p.past_due ? `The return's due date, ${dateOnly(p.due)}, has passed: worked out as if paid and filed today. Interest under sections 234A and 234B grows by 1% a month of the tax unpaid.`
        : `Worked out as if paid, and the return filed, by its due date, ${dateOnly(p.due)}. Each month after it adds interest under sections 234A and 234B.`}
        {p.refund > 0.5 ? ` TDS and tax paid are more than the tax by ${inr(p.refund)}.` : ""}</p>
      <ul className="k-list" aria-label="How the payable figure adds up">{p.lines.map((l) => <li key={l.label} className="k-spread"><span>{l.label}</span><b>{inr(l.amount)}</b></li>)}</ul>
    </Card>
  );
}

function PaymentsForm({ v, onSaved }: { v: Advance; onSaved: (a: Advance) => void }) {
  const { fail, notify } = useApp();
  const [tds, setTds] = useState(v.inputs?.tds ? String(v.inputs.tds) : "");
  const [rows, setRows] = useState<{ d: string; amount: string }[]>((v.inputs?.paid ?? []).map((p) => ({ d: p.d, amount: String(p.amount) })));
  const [saving, setSaving] = useState(false);
  const t = num(tds);
  const bad = Number.isNaN(t) || rows.some((r) => !r.d || Number.isNaN(num(r.amount)));
  const save = async () => {
    setSaving(true);
    try {
      onSaved(await api<Advance>("/money/advance-tax", { method: "PUT", body: { fy: v.fy, tds: t, paid: rows.filter((r) => num(r.amount) > 0).map((r) => ({ d: r.d, amount: num(r.amount) })) } }));
      notify("Saved. The instalments are updated.");
      track("advance tax saved", { payments: rows.length });
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Card label="TDS and advance tax paid">
      <CardHead title={`TDS and advance tax paid, ${v.label}`} />
      <FormGrid onSubmit={(e) => { e.preventDefault(); if (!bad && !saving) void save(); }}>
        <Field label="TDS for the year" unit="₹" inputMode="decimal" placeholder="e.g. 50000" value={tds} onChange={(e) => setTds(e.target.value)}
          info={<>All tax deducted at source for the year: on salary, interest, dividends and the like. Form 26AS or the AIS lists it.{v.dividend_tds ? ` The TDS expected on your dividends is ${inr(v.dividend_tds)}.` : ""}</>} />
        <div className="k-field wide"><div className="k-label-row"><span className="k-lbl">Advance tax paid</span></div>
          {rows.length === 0 && <p className="k-small k-muted">None entered. Add each payment you made, with its date.</p>}</div>
        {rows.map((r, i) => (
          <PaymentRow key={i} i={i} r={r} onChange={(n) => setRows((x) => x.map((y, j) => (j === i ? n : y)))} onRemove={() => setRows((x) => x.filter((_, j) => j !== i))} />
        ))}
        {bad && <p className="k-small k-down k-field wide">Enter amounts in rupees, 0 or more, and a date for each payment.</p>}
        <FormActions>
          <button type="submit" className="btn" disabled={bad || saving}>{saving ? "Saving…" : "Save and update"}</button>
          {rows.length < 24 && <button type="button" className="btn quiet" onClick={() => setRows((x) => [...x, { d: "", amount: "" }])}>Add a payment</button>}
        </FormActions>
      </FormGrid>
    </Card>
  );
}

function PaymentRow({ i, r, onChange, onRemove }: { i: number; r: { d: string; amount: string }; onChange: (r: { d: string; amount: string }) => void; onRemove: () => void }) {
  return (
    <>
      <DateField label="Date paid" value={r.d} onChange={(d) => onChange({ ...r, d })} ariaLabel={`Payment ${i + 1} date`} />
      <Field label="Amount" unit="₹" inputMode="decimal" value={r.amount} onChange={(e) => onChange({ ...r, amount: e.target.value })} aria-label={`Payment ${i + 1} amount`} />
      <div className="k-field"><button type="button" className="btn quiet" onClick={onRemove} aria-label={`Remove payment ${i + 1}`}>Remove</button></div>
    </>
  );
}

// ---------- the long-term exemption ----------
function LtcgTab() {
  const { fail } = useApp();
  const [v, setV] = useState<Ltcg | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [within, setWithin] = useState(90);
  useEffect(() => {
    let live = true;
    setError(null);
    api<Ltcg>("/money/ltcg").then((x) => live && setV(x)).catch((e) => { if (!live) return; setError((e as Error).message); fail(e); });
    return () => { live = false; };
  }, [fail, tries]);
  if (!v) return error ? failedLoad("Your lots couldn't be read", error, () => setTries((n) => n + 1)) : loading("Checking your lots");
  const lock = v.locked && <PlanNote>Each open lot's long-term gain and the lots turning long-term are on the Pro plan.</PlanNote>;
  if (!v.trades) {
    return <>{lock}<EmptyState title="No trades yet" action={{ label: "Open the tax report", to: "/tax-report" }}>Upload your tradebooks on the tax report to see the exemption used and your open lots.</EmptyState></>;
  }
  const name = (k: string) => v.names[k]?.symbol ?? k;
  const ex = v.exemption;
  const soon = v.soon.filter((r) => r.days_left <= within);
  const longCols: Column<LtLot>[] = [
    { key: "s", header: "Stock", rowHeader: true, cell: (r) => <><b>{name(r.key)}</b>{r.grandfathered && <span className="k-note"> grandfathered</span>}{r.bonus && <span className="k-note"> bonus</span>}</> },
    { key: "b", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "q", header: "Qty", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "c", header: "Cost for tax", numeric: true, cell: (r) => inr(r.cost) },
    { key: "v", header: "Value today", numeric: true, cell: (r) => inr(r.value) },
    { key: "g", header: "Gain if sold today", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
  ];
  const soonCols: Column<SoonLot>[] = [
    { key: "s", header: "Stock", rowHeader: true, cell: (r) => <b>{name(r.key)}</b> },
    { key: "b", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "q", header: "Qty", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "f", header: "Long-term from", numeric: true, cell: (r) => dateOnly(r.long_from) },
    { key: "d", header: "Days left", numeric: true, cell: (r) => r.days_left },
    { key: "g", header: "Gain today", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
  ];
  const belowCols: Column<BelowLot>[] = [
    { key: "s", header: "Stock", rowHeader: true, cell: (r) => <b>{name(r.key)}</b> },
    { key: "b", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "q", header: "Qty", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "l", header: "Below cost by", numeric: true, cell: (r) => <span className="k-down">{inr(r.loss)}</span> },
    { key: "t", header: "Term today", cell: (r) => (r.term === "LT" ? "Long-term" : `Short-term, long-term from ${dateOnly(r.long_from)}`) },
  ];
  // a locked figure is "–" with the lock, never a 0 that reads as a fact (DP2-003)
  const lockedStat = (label: string) => <Stat label={label} value={<span aria-label={`${label}: on the Pro plan`}><Lock />–</span>} note="on the Pro plan" />;
  return (
    <>
      {lock}
      <Card label="Long-term exemption">
        <CardHead title={`Long-term exemption, ${v.label}`} />
        <StatRow>
          <Stat label="Used by gains realised" value={<span aria-label="Exemption used">{inr(ex.used)}</span>} note={`of ${inr(ex.limit)} · ${inr(ex.left)} left`} />
          <Stat label={ex.realised_us_lt_net != null ? "Long-term gains realised, Indian shares and funds (net)" : "Long-term gains realised (net)"} value={inr(ex.realised_lt_net)} tone={signTone(ex.realised_lt_net)} note={`short-term ${inr(ex.realised_st_net)}`} />
          {v.open_lt ? <Stat label="Open long-term lots" value={v.open_lt.lots} note={`unrealised gains ${inr(v.open_lt.gains)}${v.open_lt.losses < 0 ? ` · losses ${inr(v.open_lt.losses)}` : ""}`} />
            : lockedStat("Open long-term lots")}
          {v.soon_counts ? <Stat label="Turning long-term soon" value={v.soon_counts["90"]} note={`${v.soon_counts["30"]} in 30 days · ${v.soon_counts["60"]} in 60 · ${v.soon_counts["90"]} in 90`} />
            : lockedStat("Turning long-term soon")}
        </StatRow>
        {ex.limit > 0 && ex.used > 0 && <Meter pct={(ex.used / ex.limit) * 100} />}
        <p className="k-small">{inr(ex.left)} of this year's {inr(ex.limit)} exemption is unused. It doesn't carry forward to next year.</p>
        {ex.realised_us_lt_net != null && <p className="k-small k-muted" data-testid="ltcg-us-apart">{usSharesNote(ex.realised_us_st_net, ex.realised_us_lt_net, inr)} The exemption is for Indian shares and equity funds only.</p>}
      </Card>

      {!v.locked && (
        <Card>
          <CardHead title="Open long-term lots at today's price" info="Each figure is arithmetic: if a lot were sold today at the latest price, its long-term gain would be the value less the cost for tax (with charges, and the 31 Jan 2018 price for older lots)." />
          {v.long.length === 0 ? <EmptyState title="No open long-term lots">No open lot has been held for more than 12 months{v.unpriced ? " with a price today" : ""}.</EmptyState>
            : <DataTable label="Open long-term lots" columns={longCols} rows={v.long} rowKey={(r, i) => `${r.key}${r.bought}${r.qty}-${i}`} rowAttrs={(r) => ({ title: r.text })} />}
        </Card>
      )}

      {!v.locked && (
        <Card>
          <CardHead title="Turning long-term" info="A sale before the date shown is short-term (20% from 23 July 2024); from that date it is long-term (12.5% above the exemption)."
            actions={<Seg label="Within" options={[30, 60, 90].map((n) => ({ value: String(n), label: `${n} days` }))} value={String(within)} onChange={(n) => setWithin(Number(n))} />} />
          {soon.length === 0 ? <EmptyState title={`Nothing turns long-term in ${within} days`}>No open lot turns long-term in the next {within} days.</EmptyState>
            : <DataTable label="Lots turning long-term" columns={soonCols} rows={soon} rowKey={(r, i) => `${r.key}${r.bought}${r.qty}-${i}`} rowAttrs={(r) => ({ title: r.text })} />}
        </Card>
      )}

      {!v.locked && (
        <Card>
          <CardHead title="Open lots below cost" />
          {v.below_cost.rows.length === 0 ? <EmptyState title="No open lot below its cost">No open lot is below its cost at today's price.</EmptyState>
            : <DataTable label="Open lots below cost" columns={belowCols} rows={v.below_cost.rows} rowKey={(r, i) => `${r.key}${r.bought}${r.qty}-${i}`} />}
        </Card>
      )}

      <Card>
        <CardHead title="The facts behind it" />
        <ul className="k-list">{v.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
        {v.unpriced > 0 && <p className="k-note">{v.unpriced} lot{v.unpriced === 1 ? " has" : "s have"} no price today{v.prices ? "" : " (live prices are offline right now)"}.</p>}
        <Dated label="Prices as of" iso={v.as_of} />
      </Card>
    </>
  );
}
