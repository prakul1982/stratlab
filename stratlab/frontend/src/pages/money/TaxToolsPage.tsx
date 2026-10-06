import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf as asOfText, dateOnly, inr, money, qty as qtyText, signTone } from "../../lib/format";
import { Info } from "../../components/ui";
import { Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, EmptyState, Field, FieldGroup, FormActions, FormGrid, Meter, Notice, PageHeader, PlanNote, Seg, Select, Skeleton, Stat, StatRow, UploadButton, type Column } from "../../components/kit";

/* /money/tax-tools: dividends and the TDS on them, advance tax by date, and the long-term exemption, built on the tax
 * report and My Holdings. Estimates and arithmetic on the user's own figures. Built from the kit (components/kit). */

// ---------- what the server sends ----------
type Company = {
  symbol: string; name: string; country: "IN" | "US"; count: number; amount: number; amount_usd: number | null; tds_file: number | null;
  first: string; last: string; tds_expected?: number; over_threshold?: boolean; withheld_usd?: number; withheld?: number;
};
type DivYear = {
  fy: number; label: string; total: number; india_total: number; us_total: number; count: number; companies_count: number; unpriced: number; taxed: boolean;
  tds: { threshold: number | null; rate: number; section: string; expected: number; companies_over: number; in_file: number | null };
  us: { gross_usd: number; gross: number; rate: number; withheld_usd: number; withheld: number } | null;
  companies: Company[]; locked: boolean; source: "files" | "estimated" | "none"; include: boolean; include_saved: boolean; estimate_total: number | null;
};
type Ahead = { symbol: string; ex_date: string; label: string | null; qty: number; per_share: number; currency: string; amount: number };
type Dividends = {
  years: DivYear[]; current_fy: number; files: { name: string; source: string; rows: number; at: string }[]; updated_at: string | null;
  ahead: Ahead[];
  ahead_total: number; usd_inr: number | null; as_of: string; assumptions: string[]; locked: boolean;
};
type DueDate = { n: number; date: string; pct: number; label: string };
type Instalment = DueDate & {
  base: number; required: number; paid: number; short: number; to_pay: number; interest_234c: number; interest_if_missed: number; months: number;
  tolerated: boolean; status: "passed" | "next" | "later";
};
type Schedule = {
  fy: number; label: string; tax: number; tds: number; net: number; due: boolean; threshold: number; instalments: Instalment[]; next: number | null; paid: number;
  interest_234c: number; b234: { applies: boolean; paid: number; ninety_pct: number; short: number; months: number; until: string; interest: number }; steps: string[];
};
type Payment = { d: string; amount: number };
type Advance = {
  fy: number; label: string; dates: DueDate[]; remind: boolean; locked: boolean; as_of: string; assumptions: string[]; threshold: number; current_fy: number;
  schedule?: Schedule; inputs?: { tds: number; paid: Payment[] }; dividends_in_estimate?: number; dividend_tds?: number; income_saved?: boolean;
};
type LtLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; gain: number; grandfathered: boolean; bonus: boolean; text: string };
type SoonLot = LtLot & { long_from: string; days_left: number; window: number };
type BelowLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; loss: number; loss_pct: number | null; days: number; term: "ST" | "LT"; long_from: string | null };
type Ltcg = {
  fy: number; label: string; as_of: string; exemption: { limit: number; used: number; left: number; realised_lt_net: number; realised_st_net: number };
  open_lt: { lots: number; gains: number; losses: number; with_gain: number }; soon_counts: Record<string, number>; long: LtLot[]; soon: SoonLot[];
  unpriced: number; facts: string[]; locked: boolean; below_cost: { rows: BelowLot[]; unpriced: number; open: number; st: number; lt: number };
  names: Record<string, { symbol: string }>; prices: boolean; trades: number;
};

const usd = (v: number | null | undefined) => money(v, "USD", 2);
const TABS = [["dividends", "Dividends"], ["advance", "Advance tax"], ["ltcg", "Long-term exemption"]] as const;
type Tab = (typeof TABS)[number][0];
const DISCLAIMER = "Estimates and arithmetic on your own figures, not tax advice. Check them with a chartered accountant (CA) before you file or pay tax.";
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };
const Dated = ({ label, iso }: { label: string; iso: string | null | undefined }) => (asOfText(iso) ? <p className="k-note">{label} {asOfText(iso)}.</p> : null);

export function TaxToolsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find(([t]) => t === params.get("tab"))?.[0]) ?? "dividends";
  const go = (t: Tab) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", t); return n; }, { replace: true });
  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Tax" title="Dividends, advance tax and the long-term exemption"
        lede={<>Built on your <Link className="link" to="/tax-report">tax report</Link> and <Link className="link" to="/holdings">holdings</Link>: the dividends you received, the advance tax due by each date, and how much of this year's long-term exemption is used.</>}
        info="The dividends you received and the TDS on them, the advance tax due by each date, and how much of this year's long-term gains exemption is used. Only you can see these figures." infoLabel="What these tools cover" />
      <Notice label="Estimate only"><b>Estimate only.</b> {DISCLAIMER}</Notice>
      <Seg label="Tax tools" options={TABS.map(([value, label]) => ({ value, label }))} value={tab} onChange={(t) => go(t as Tab)} />
      {tab === "dividends" && <DividendsTab />}
      {tab === "advance" && <AdvanceTab />}
      {tab === "ltcg" && <LtcgTab />}
    </div>
  );
}

const yearOptions = (years: { fy: number; label: string }[], current: number) => years.map((x) => ({ value: x.fy, label: `${x.label}${x.fy === current ? " (this year)" : ""}` }));
const loading = (label: string) => <Card><Skeleton label={label} /></Card>;

// ---------- dividends ----------
function DividendsTab() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<Dividends | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const show = useCallback((d: Dividends) => {
    setV(d);
    setFy((cur) => cur ?? (d.years.find((y) => y.fy === d.current_fy && y.total > 0) ?? d.years.find((y) => y.total > 0) ?? d.years[0])?.fy ?? d.current_fy);
  }, []);
  useEffect(() => { api<Dividends>("/money/dividends").then(show).catch(fail); }, [show, fail]);

  const pick = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { notify("That file is larger than 10 MB."); reset(); return; }
    setBusy(true);
    try {
      const r = await api<{ read: number; added: number; duplicates: number; problems: { line: number; text: string; reason: string }[]; dividends: Dividends }>(
        `/money/dividends/import?${new URLSearchParams({ filename: f.name.slice(0, 200) })}`, { method: "POST", file: f });
      setNote(`${r.added} dividend${r.added === 1 ? "" : "s"} added${r.duplicates ? `, ${r.duplicates} already there (skipped)` : ""}${r.problems.length ? `, ${r.problems.length} line${r.problems.length === 1 ? "" : "s"} left out` : ""}.`);
      setFy(null);
      show(r.dividends);
      track("dividends imported", { rows: r.added });
    } catch (e) { fail(e); } finally { setBusy(false); reset(); }
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

  if (!v) return loading("Adding up your dividends");
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
  return (
    <>
      <Card>
        <CardHead title="Your dividends" info="Upload your broker's dividend statement as CSV or Excel, with columns for the date, the company (symbol, name or ISIN) and the amount (or quantity and dividend a share); TDS and currency are optional (USD for US dividends). A tax P&L ZIP uploaded to the tax report brings its dividend sheet too. Without a file, the year is estimated from your holdings and the dividends the companies declared."
          actions={<>
            <UploadButton label="Upload dividends" busy={busy} accept=".csv,.xlsx,.txt,.zip,text/csv" ariaLabel="Dividend file" onFiles={pick} />
            {v.files.length > 0 && <button type="button" className="btn quiet sm" onClick={() => setAsking(true)}><Trash size={16} />Delete uploaded dividends</button>}
          </>} />
        {note && <p className="k-small" role="status">{note}</p>}
        {v.files.length > 0 && <p className="k-note">From {v.files.map((f) => f.name).join(", ")}.</p>}
      </Card>

      {y && (
        <>
          <FormGrid label="Year">
            <Field label="Financial year">{(id) => <Select id={id} value={y.fy} onChange={(x) => setFy(Number(x))} options={yearOptions(v.years, v.current_fy)} />}</Field>
            {y.source !== "none" && y.taxed && (
              <FieldGroup label="In the total tax estimate" info="Whether this year's dividends are counted as income in the total tax estimate on the tax report.">
                <Seg label="In the total tax estimate" options={[{ value: "in", label: "Include in the tax estimate" }, { value: "out", label: "Leave out" }]} value={y.include ? "in" : "out"} onChange={(x) => include(y.fy, x === "in")} />
              </FieldGroup>
            )}
          </FormGrid>
          <Card label="Dividends for the year">
            <CardHead title={`Dividends, ${y.label}`} actions={<>
              {y.source === "files" && <Badge>From your files</Badge>}
              {y.source === "estimated" && <Badge>Estimated</Badge>}
            </>} />
            {y.source === "none" ? <EmptyState title={`No dividends in ${y.label}`}>No dividends in your files or holdings for the year. Upload a dividend statement above to add them.</EmptyState> : (
              <>
                <StatRow>
                  <Stat label="Dividend income" value={<span aria-label="Dividend income">{inr(y.total)}</span>} note={`${y.count} payment${y.count === 1 ? "" : "s"} from ${y.companies_count} compan${y.companies_count === 1 ? "y" : "ies"}`} />
                  <Stat label="Indian companies" value={inr(y.india_total)} note={y.tds.threshold != null ? `TDS above ${inr(y.tds.threshold)} a company` : "Exempt that year"} />
                  {!y.locked && y.tds.threshold != null && (
                    <Stat label={<>TDS expected <Info label="About TDS on dividends">A company cuts 10% TDS (20% without a PAN) from a resident once its dividends to you in the year are over the threshold, on the whole amount: {inr(y.tds.threshold)} for {y.label} under {y.tds.section}. Form 26AS or the AIS shows what was actually cut.</Info></>}
                      value={inr(y.tds.expected)} note={`${y.tds.companies_over} compan${y.tds.companies_over === 1 ? "y" : "ies"} over the threshold${y.tds.in_file != null ? ` · ${inr(y.tds.in_file)} in your file` : ""}`} />
                  )}
                  {!y.locked && y.us && (
                    <Stat label={<>US dividends <Info label="About US dividends">The US withholds 25% under the India-US tax treaty (with a W-8BEN). In India the dividend is taxed at your slab rate, and the US tax can be claimed as a foreign tax credit, up to the Indian tax on that income, by filing Form 67 before the return.</Info></>}
                      value={inr(y.us.gross)} note={`${usd(y.us.gross_usd)} · US tax withheld ${usd(y.us.withheld_usd)} (${inr(y.us.withheld)}), the foreign tax credit figure`} />
                  )}
                </StatRow>
                <p className="k-small">{y.taxed ? (y.include
                  ? <>Included in the <Link className="link" to="/tax-report">total tax estimate</Link> as income from other sources, taxed at your slab rate.</>
                  : <>Not in the <Link className="link" to="/tax-report">total tax estimate</Link>{y.source === "estimated" ? " (an estimate is left out until you include it)" : ""}.</>)
                  : "Dividends were exempt in your hands before FY 2020-21 (the company paid dividend distribution tax)."}</p>
                {y.source === "files" && y.estimate_total != null && <p className="k-note">From your holdings, the estimate for {y.label} is {inr(y.estimate_total)}.</p>}
                {y.unpriced > 0 && <p className="k-note">{y.unpriced} US payment{y.unpriced === 1 ? " isn't" : "s aren't"} counted: the dollar rate isn't available right now.</p>}
                {y.locked ? <PlanNote>Dividends by company, with the TDS expected and the US tax withheld, are on the Basic plan.</PlanNote>
                  : y.companies.length > 0 && <DataTable label="Dividends by company" columns={companyCols} rows={y.companies} rowKey={(c) => `${c.country}${c.symbol}`} />}
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
  const [fy, setFy] = useState<number | null>(null);
  useEffect(() => { api<Advance>(`/money/advance-tax${fy ? `?fy=${fy}` : ""}`).then(setV).catch(fail); }, [fy, fail]);
  const remind = async (on: boolean) => {
    try { await api("/money/advance-tax/reminders", { method: "PUT", body: { on } }); setV((x) => (x ? { ...x, remind: on } : x)); notify(on ? "Reminders on: 7 days and 1 day before each date." : "Reminders off."); }
    catch (e) { fail(e); }
  };
  if (!v) return loading("Working out the instalments");
  const s = v.schedule;
  const cols: Column<Instalment>[] = [
    { key: "by", header: "By", rowHeader: true, cell: (r) => <><b>{r.label}</b>{r.status === "next" && <span className="k-note"> next</span>}</> },
    { key: "share", header: "Share", numeric: true, cell: (r) => `${Math.round(r.pct * 100)}%` },
    { key: "req", header: "Due by then", numeric: true, cell: (r) => inr(r.required) },
    { key: "paid", header: "Paid by then", numeric: true, cell: (r) => inr(r.paid) },
    { key: "short", header: "Short", numeric: true, cell: (r) => <><span className={r.short > 0 ? "k-down" : undefined}>{r.short > 0 ? inr(r.short) : "–"}</span>{r.tolerated && <span className="k-sub-line">within {r.n === 0 ? "12%" : "36%"}</span>}</> },
    { key: "int", header: "234C interest", numeric: true, cell: (r) => (r.status === "passed" ? inr(r.interest_234c) : r.interest_if_missed > 0 ? <span className="k-note">{inr(r.interest_if_missed)} if not paid</span> : "–") },
  ];
  return (
    <>
      <FormGrid label="Year and reminders">
        <Field label="Financial year">{(id) => (
          <Select id={id} value={v.fy} onChange={(x) => setFy(Number(x))} options={[v.current_fy, v.current_fy - 1].map((x) => ({ value: x, label: `FY ${x}-${String(x + 1).slice(2)}${x === v.current_fy ? " (this year)" : ""}` }))} />
        )}</Field>
        <FieldGroup label="Reminders by email and phone" info="7 days and 1 day before each due date, to your confirmed email address and any phone notifications you set up in Account. Dates only: no amounts are sent.">
          <Seg label="Advance tax reminders" options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]} value={v.remind ? "on" : "off"} onChange={(x) => remind(x === "on")} />
        </FieldGroup>
      </FormGrid>

      <Card label="Advance tax due dates">
        <CardHead title={`Due dates, ${v.label}`} info={`Advance tax is due when the year's tax less TDS is ${inr(v.threshold)} or more (section 208; section 404 of the Income-tax Act, 2025 from FY 2026-27).`} />
        <ul className="k-list" aria-label="Due dates">
          {v.dates.map((d) => <li key={d.n}><b>{d.label}</b>: {d.pct * 100}% of the year's tax (less TDS), counting what was paid before</li>)}
        </ul>
        {v.locked && <PlanNote>The amounts due by each date, and the interest on a short instalment, are on the Pro plan.</PlanNote>}
      </Card>

      {s && v.inputs && (
        <>
          <Card label="Advance tax amounts">
            <CardHead title="What is due" />
            <StatRow>
              <Stat label="Tax for the year (estimate)" value={<span aria-label="Tax for the year">{inr(s.tax)}</span>}
                note={<>from the <Link className="link" to="/tax-report">tax report</Link>{v.income_saved ? "" : ", no other income entered"}{v.dividends_in_estimate ? ` · ${inr(v.dividends_in_estimate)} of dividends in it` : ""}</>} />
              <Stat label="Less TDS" value={inr(s.tds)} note="as you entered it" />
              <Stat label="Advance tax for the year" value={<span aria-label="Advance tax for the year">{s.due ? inr(s.net) : "None due"}</span>} note={s.due ? `${inr(s.paid)} paid so far` : `below ${inr(s.threshold)}`} />
              {s.due && <Stat label="Interest so far (234C)" value={inr(s.interest_234c)} tone={s.interest_234c > 0 ? "down" : undefined} note="on instalments already due" />}
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
          <li>Capital gains and dividends that arise after a due date go into the instalments still to come (by 31 March when none is left), without interest.</li>
          <li>Section 234C: 1% a month on each instalment's shortfall, for 3 months (1 month for March). None for June when 12% was paid by then, none for September when 36% was.</li>
          <li>Section 234B: when advance tax paid by 31 March is under 90% of the tax, 1% a month on the shortfall from 1 April until it is paid.</li>
          <li>From FY 2026-27 the Income-tax Act, 2025 numbers these sections 404 (who pays), 424 (234B) and 425 (234C).</li>
        </ul>
        <ul className="k-list muted">{v.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <Dated label="Worked out" iso={v.as_of} />
      </Card>
    </>
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
      <Field label="Date paid" type="date" value={r.d} onChange={(e) => onChange({ ...r, d: e.target.value })} aria-label={`Payment ${i + 1} date`} />
      <Field label="Amount" unit="₹" inputMode="decimal" value={r.amount} onChange={(e) => onChange({ ...r, amount: e.target.value })} aria-label={`Payment ${i + 1} amount`} />
      <div className="k-field"><button type="button" className="btn quiet" onClick={onRemove} aria-label={`Remove payment ${i + 1}`}>Remove</button></div>
    </>
  );
}

// ---------- the long-term exemption ----------
function LtcgTab() {
  const { fail } = useApp();
  const [v, setV] = useState<Ltcg | null>(null);
  const [within, setWithin] = useState(90);
  useEffect(() => { api<Ltcg>("/money/ltcg").then(setV).catch(fail); }, [fail]);
  if (!v) return loading("Checking your lots");
  if (!v.trades) {
    return <EmptyState title="No trades yet" action={{ label: "Open the tax report", to: "/tax-report" }}>Upload your tradebooks on the tax report to see the exemption used and your open lots.</EmptyState>;
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
  return (
    <>
      <Card label="Long-term exemption">
        <CardHead title={`Long-term exemption, ${v.label}`} />
        <StatRow>
          <Stat label="Used by gains realised" value={<span aria-label="Exemption used">{inr(ex.used)}</span>} note={`of ${inr(ex.limit)} · ${inr(ex.left)} left`} />
          <Stat label="Long-term gains realised (net)" value={inr(ex.realised_lt_net)} tone={signTone(ex.realised_lt_net)} note={`short-term ${inr(ex.realised_st_net)}`} />
          <Stat label="Open long-term lots" value={v.open_lt.lots} note={`unrealised gains ${inr(v.open_lt.gains)}${v.open_lt.losses < 0 ? ` · losses ${inr(v.open_lt.losses)}` : ""}`} />
          <Stat label="Turning long-term soon" value={v.soon_counts["90"]} note={`${v.soon_counts["30"]} in 30 days · ${v.soon_counts["60"]} in 60 · ${v.soon_counts["90"]} in 90`} />
        </StatRow>
        {ex.limit > 0 && <Meter pct={(ex.used / ex.limit) * 100} />}
        <p className="k-small">{inr(ex.left)} of this year's {inr(ex.limit)} exemption is unused. It doesn't carry forward to next year.</p>
        {v.locked && <PlanNote>Each open lot's long-term gain and the lots turning long-term are on the Pro plan.</PlanNote>}
      </Card>

      {!v.locked && (
        <Card>
          <CardHead title="Open long-term lots at today's price" info="Each figure is arithmetic: if a lot were sold today at the latest price, its long-term gain would be the value less the cost for tax (with charges, and the 31 Jan 2018 price for older lots)." />
          {v.long.length === 0 ? <EmptyState title="No open long-term lots">No open lot has been held for more than 12 months{v.unpriced ? " with a price today" : ""}.</EmptyState>
            : <DataTable label="Open long-term lots" columns={longCols} rows={v.long} rowKey={(r) => `${r.key}${r.bought}${r.qty}`} rowAttrs={(r) => ({ title: r.text })} />}
        </Card>
      )}

      {!v.locked && (
        <Card>
          <CardHead title="Turning long-term" info="A sale before the date shown is short-term (20% from 23 July 2024); from that date it is long-term (12.5% above the exemption)."
            actions={<Seg label="Within" options={[30, 60, 90].map((n) => ({ value: String(n), label: `${n} days` }))} value={String(within)} onChange={(n) => setWithin(Number(n))} />} />
          {soon.length === 0 ? <EmptyState title={`Nothing turns long-term in ${within} days`}>No open lot turns long-term in the next {within} days.</EmptyState>
            : <DataTable label="Lots turning long-term" columns={soonCols} rows={soon} rowKey={(r) => `${r.key}${r.bought}${r.qty}`} rowAttrs={(r) => ({ title: r.text })} />}
        </Card>
      )}

      {!v.locked && (
        <Card>
          <CardHead title="Open lots below cost" />
          {v.below_cost.rows.length === 0 ? <EmptyState title="No open lot below its cost">No open lot is below its cost at today's price.</EmptyState>
            : <DataTable label="Open lots below cost" columns={belowCols} rows={v.below_cost.rows} rowKey={(r) => `${r.key}${r.bought}${r.qty}`} />}
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
