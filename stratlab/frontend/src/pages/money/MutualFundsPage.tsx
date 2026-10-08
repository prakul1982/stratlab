import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataUrl } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, inr, pct, price, qty as qtyText, signTone } from "../../lib/format";
import { Info } from "../../components/ui";
import { Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { BarList, Card, CardHead, ConfirmDialog, DataTable, Delta, Disclosure, EmptyState, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, PlanNote, Seg, Select, Signed, Skeleton, Stat, StatRow, UploadButton, type Column } from "../../components/kit";
import { FundCosts } from "./FundCosts";
import { FundBehaviour } from "./FundBehaviour";
import { pickFy, rememberFy } from "../../lib/fy";
import { PlanInline } from "../../components/PlanInterest";

/* /money/mutual-funds: the Consolidated Account Statement read into every scheme's value at the latest NAV, what went in,
 * the gain and XIRR, the mix by category, and capital gains for each financial year. Built from the kit (components/kit). */

type Kind = "equity" | "debt" | "hybrid" | "other";
type Scheme = {
  key: string; name: string; amc: string; folio: string; isin: string; amfi: string; category: string; broad: string; sub: string;
  kind: Kind; kind_auto: Kind; kind_set: boolean; units: number; nav: number | null; nav_date: string | null; nav_source: "daily" | "statement" | null;
  invested: number | null; value: number | null; gain: number | null; gain_pct: number | null; xirr: number | null; realised: number | null;
  cost_unknown: boolean; short_units: number | null; elss: { locked_units: number; next_free: string; all_free: string } | null; txns: number;
  fmv_2018: number | null; fmv_yours: boolean;
};
type Bucket = { key: string; label: string; rate: number; gains: number; after_setoff: number; exempt: number; taxable: number; tax: number; slab?: boolean };
type Sale = { key: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number; term: "ST" | "LT"; gf: "applied" | "missing" | null; rate: number | null; kind?: Kind };
type Side = { gains: number; losses: number; net: number; sales: number };
type Year = {
  fy: number; label: string; stcg: Side; ltcg: Side; exemption: { limit: number; used: number; left: number }; buckets: Bucket[]; steps: string[];
  tax: number; tax_with_cess: number; carry_forward: { st: number; lt: number }; count: number; rows: Sale[]; dividends: number; stt: number;
  exempt_old: number | null;
};
type Gains = { years: Year[]; current_fy: number; notes: string[]; gf_missing: string[]; unknown_units: Record<string, number>; flags: string[] };
type View = {
  schemes: Scheme[]; allocation: { broad: string; value: number; pct: number | null; schemes: number; subs: { sub: string; value: number; pct: number | null }[] }[];
  total: { value: number; invested: number; gain: number; xirr: number | null; held: number; schemes: number; unknown_cost: number; nav_dates: [string, string] | null };
  gains: Gains | null; gains_allowed: boolean; gains_plan: string; limit: number | null; files: { name: string; kind: string; txns: number; at: string }[];
  updated_at: string | null; txns: number; kinds: Record<Kind, string>; nav_read_at: string | null; assumptions: string[]; disclaimer: string; as_of: string;
};
type Problem = { line?: number; text: string; reason: string };
type ImportReply = { kind: "cas" | "csv"; added: number; duplicates: number; over_limit: string[]; schemes: number; problems: Problem[]; limit: number | null; upgrade: string | null; view: View };

const MAX_MB = 5;
const rate = (r: number | null, slab?: boolean) => (r == null || slab ? "Slab" : `${+(r * 100).toFixed(2)}%`);
const xirrText = (x: number | null) => (x == null ? "–" : pct(x * 100));
const KIND_SHORT: Record<Kind, string> = { equity: "Equity-oriented", debt: "Debt", hybrid: "Other (35–65% equity)", other: "Other (under 35% equity)" };
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

export function MutualFundsPage() {
  const { fail, notify } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [allSales, setAllSales] = useState(false);
  const [asking, setAsking] = useState(false);
  const resetFile = useRef<() => void>(() => undefined);

  const show = useCallback((v: View) => {
    setView(v);
    setFy((cur) => (cur != null && v.gains?.years.some((y) => y.fy === cur) ? cur
      : v.gains?.years.length ? pickFy(v.gains.years.map((y) => y.fy), v.gains.current_fy) : null));     // the Money pages' shared year
  }, []);
  const load = useCallback(() => {
    setError(null);
    api<View>("/money/mutual-funds").then(show).catch((e) => { setError(e instanceof Error ? e.message : "Your funds couldn't be read."); fail(e); });
  }, [show, fail]);
  useEffect(() => { load(); }, [load]);

  const isPdf = !!picked && (/\.pdf$/i.test(picked.name) || picked.type === "application/pdf");
  const send = async () => {
    if (!picked) { notify("Pick your CAS PDF or a CSV first."); return; }
    if (picked.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB. A CAS is usually much smaller.`); return; }
    setBusy(true);
    try {
      const data = await dataUrl(picked);
      const r = await api<ImportReply>("/money/mutual-funds/import", { method: "POST", body: { filename: picked.name, data, password: isPdf ? password : "", mode } });
      track("mutual funds imported", { kind: r.kind, added: r.added });
      setResult(r);
      show(r.view);
      setPicked(null);
      resetFile.current();
    } catch (e) { fail(e); } finally {
      setPassword("");          // used once to open the file, then forgotten
      setBusy(false);
    }
  };

  const setKind = async (key: string, kind: Kind | null) => {
    try { show(await api<View>("/money/mutual-funds/kind", { method: "PUT", body: { key, kind } })); notify("Saved. The gains are worked out again."); }
    catch (e) { fail(e); }
  };
  const setFmv = async (key: string, nav: number | null) => {
    try { show(await api<View>("/money/mutual-funds/fmv", { method: "PUT", body: { key, nav } })); notify(nav ? "Saved. Units held on 31 Jan 2018 now use it." : "Cleared."); }
    catch (e) { fail(e); }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await api("/money/mutual-funds", { method: "DELETE" });
      setResult(null);
      show(await api<View>("/money/mutual-funds"));
      notify("Your mutual fund data is deleted.");
    } catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };

  const schemes = view?.schemes ?? [];
  const held = schemes.filter((s) => s.units > 0);
  const name = useCallback((k: string) => schemes.find((s) => s.key === k)?.name ?? k, [schemes]);
  const y = useMemo(() => view?.gains?.years.find((x) => x.fy === fy) ?? null, [view, fy]);
  const t = view?.total;
  const navWhen = t?.nav_dates ? (t.nav_dates[0] === t.nav_dates[1] ? dateOnly(t.nav_dates[0]) : `${dateOnly(t.nav_dates[0])} to ${dateOnly(t.nav_dates[1])}`) : null;

  const schemeCols: Column<Scheme>[] = [
    { key: "scheme", header: "Scheme", rowHeader: true, wrap: true, cell: (s) => (
      <>
        <b>{s.name}</b>
        <span className="k-sub-line">Folio {s.folio}{s.category ? ` · ${s.category}` : ""}</span>
        {s.elss && <span className="k-sub-line">ELSS lock-in: {qtyText(s.elss.locked_units)} units locked; the next free on {dateOnly(s.elss.next_free)}, all by {dateOnly(s.elss.all_free)}.</span>}
        {s.cost_unknown && <span className="k-sub-line k-down">Some units have no purchase in the statement, so their cost isn't known. A statement from your first investment fixes this.</span>}
      </>) },
    { key: "units", header: "Units", numeric: true, cell: (s) => qtyText(s.units) },
    { key: "nav", header: "NAV", numeric: true, cell: (s) => <>{price(s.nav, "INR")}<span className="k-sub-line">{s.nav_date ? dateOnly(s.nav_date) : "–"}{s.nav_source === "statement" ? " · statement" : ""}</span></> },
    { key: "inv", header: "Invested", numeric: true, cell: (s) => inr(s.invested) },
    { key: "val", header: "Value", numeric: true, cell: (s) => inr(s.value) },
    { key: "gain", header: "Gain", numeric: true, cell: (s) => (s.gain == null ? "–" : <><span className={tone(s.gain)}>{inr(s.gain)}</span><span className="k-sub-line"><Signed value={s.gain}>{pct(s.gain_pct)}</Signed></span></>) },
    { key: "xirr", header: "XIRR", numeric: true, cell: (s) => <span className={tone(s.xirr)}>{xirrText(s.xirr)}</span> },
    { key: "kind", header: "Taxed as", cell: (s) => (
      <>
        <Select small label={`How ${s.name} is taxed`} value={s.kind} onChange={(k) => setKind(s.key, k === s.kind_auto ? null : k as Kind)} options={(Object.keys(KIND_SHORT) as Kind[]).map((k) => ({ value: k, label: KIND_SHORT[k] }))} />
        <span className="k-sub-line">{s.kind_set ? "Set by you" : "From the category"}</span>
      </>) },
  ];
  const bucketCols: Column<Bucket>[] = [
    { key: "kind", header: "Kind", rowHeader: true, cell: (b) => b.label },
    { key: "rate", header: "Rate", numeric: true, cell: (b) => rate(b.rate, b.slab) },
    { key: "gains", header: "Gains", numeric: true, cell: (b) => inr(b.gains) },
    { key: "after", header: "After set-off", numeric: true, cell: (b) => inr(b.after_setoff) },
    { key: "ex", header: "Exempt", numeric: true, cell: (b) => inr(b.exempt) },
    { key: "taxable", header: "Taxable", numeric: true, cell: (b) => inr(b.taxable) },
    { key: "tax", header: "Tax", numeric: true, cell: (b) => (b.slab ? <span className="k-small k-muted">At your slab rate</span> : inr(b.tax)) },
  ];
  const saleCols: Column<Sale & { i: number }>[] = [
    { key: "scheme", header: "Scheme", rowHeader: true, wrap: true, cell: (r) => <>{name(r.key)}{r.gf === "applied" && <span className="k-note"> grandfathered</span>}{r.gf === "missing" && <span className="k-note k-down"> 31 Jan 2018 NAV missing</span>}</> },
    { key: "bought", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "sold", header: "Sold", numeric: true, cell: (r) => dateOnly(r.sold) },
    { key: "units", header: "Units", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "cost", header: "Cost", numeric: true, cell: (r) => inr(r.cost) },
    { key: "sale", header: "Sale", numeric: true, cell: (r) => inr(r.sale) },
    { key: "gain", header: "Gain or loss", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
    { key: "term", header: "Term", cell: (r) => (r.term === "LT" ? "Long" : "Short") },
    { key: "rate", header: "Rate", numeric: true, cell: (r) => rate(r.rate) },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · What you own" title="Your mutual funds, in one place"
        lede="Upload your Consolidated Account Statement to see every scheme's value at the latest NAV, the gain, XIRR and capital gains for each financial year."
        asOf={t?.nav_dates?.[1] ?? view?.nav_read_at} asOfLabel="NAVs up to"
        info="Your value, what you put in, the gain, XIRR, your mix by category, and capital gains for each financial year. Only you can see your funds, and you can delete them at any time." infoLabel="What this page shows" />
      <Notice label="Facts and arithmetic">{view?.disclaimer ?? "Facts and arithmetic from your own statement, valued at the latest published NAV. Not investment or tax advice."}</Notice>

      <Card>
        <CardHead title="Upload your statement"
          info={<>Ask CAMS or KFintech for the <b>detailed</b> Consolidated Account Statement (with transactions), from the date of your first investment, and upload the PDF as it was emailed to you, with its password. The PDF is opened in memory to read your transactions; neither the file nor the password is kept. Or upload a CSV with the columns Date, Scheme, ISIN or AMFI code, Units, Amount and Type (purchase, SIP, redemption, switch in or out, dividend, stamp duty or STT).</>}
          actions={schemes.length > 0 ? <Seg label="What the file does" options={[{ value: "add", label: "Add to my funds" }, { value: "replace", label: "Start again with this file" }]} value={mode} onChange={(m) => setMode(m as typeof mode)} /> : undefined} />
        <div className="k-row">
          <UploadButton quiet label={picked ? "Pick another file" : "Pick CAS PDF or CSV"} busy={busy} accept=".pdf,.csv,application/pdf,text/csv" ariaLabel="CAS PDF or CSV file"
            onFiles={(files, reset) => { resetFile.current = reset; setPicked(files?.[0] ?? null); }} />
          {picked && <span className="k-small k-any">{picked.name}</span>}
        </div>
        <FormGrid onSubmit={(e) => { e.preventDefault(); void send(); }}>
          {isPdf && <Field label="PDF password" type="password" value={password} autoComplete="off" spellCheck={false} placeholder="As set when you asked for it, often your PAN"
            onChange={(e) => setPassword(e.target.value)} aria-label="PDF password" />}
          <FormActions>
            <button type="submit" className="btn" disabled={busy || !picked}>{busy ? "Reading…" : "Read my funds"}</button>
            {/* a greyed-out button says what it is waiting for (R1-057) */}
            {!picked && <span className="k-note">Pick your statement first. A PDF asks for its password here once picked.</span>}
          </FormActions>
        </FormGrid>
        {result && (
          <div className="k-stack" role="status">
            <p className="k-small">
              <b>{result.kind === "cas" ? "Read your statement" : "Read as a CSV file"}:</b> {result.added} transaction{result.added === 1 ? "" : "s"} added
              {result.duplicates > 0 && `, ${result.duplicates} already saved (skipped)`}, from {result.schemes} scheme{result.schemes === 1 ? "" : "s"}.
            </p>
            {result.over_limit.length > 0 && (
              <p className="k-small">Your plan keeps {result.limit} schemes, so {result.over_limit.length} {result.over_limit.length === 1 ? "was" : "were"} left out: {result.over_limit.slice(0, 8).join(", ")}{result.over_limit.length > 8 ? "…" : ""}. {result.upgrade} <PlanInline /></p>
            )}
            {result.problems.length > 0 && (
              <ul className="k-list muted" aria-label="Lines left out">
                {result.problems.slice(0, 20).map((p, i) => <li key={i}>{p.line ? `Line ${p.line}: ` : ""}{p.text ? `${p.text} · ` : ""}{p.reason}</li>)}
              </ul>
            )}
          </div>
        )}
        {view && view.files.length > 0 && (
          <p className="k-note">{view.txns.toLocaleString("en-IN")} transactions from {view.files.length} file{view.files.length === 1 ? "" : "s"}{view.updated_at ? ` · updated ${ago(view.updated_at)}` : ""}</p>
        )}
      </Card>

      {!view && (error
        ? <ErrorState title="Your funds couldn't be read" action={{ label: "Try again", onClick: load }}>{error}</ErrorState>
        : <Card><Skeleton label="Opening your mutual funds" /></Card>)}
      {view && schemes.length === 0 && (
        <EmptyState title="No funds yet">Upload your CAS above to see your schemes, their value and your gains.</EmptyState>
      )}

      {view && t && schemes.length > 0 && (
        <>
          <Card>
            <CardHead title="Where your funds stand" info={navWhen ? `Valued at the NAV of ${navWhen}.` : "No NAV is available yet."} />
            <StatRow>
              <Stat label="Current value" value={inr(t.value)} note={`${t.held} scheme${t.held === 1 ? "" : "s"} held`} />
              <Stat label={<>Invested <Info label="What invested means">The cost of the units you still hold, matched first in, first out, including stamp duty. Units sold or switched out are not in it.</Info></>}
                value={inr(t.invested)} note={t.unknown_cost > 0 ? `${t.unknown_cost} scheme${t.unknown_cost === 1 ? "" : "s"} without a known cost left out` : undefined} />
              <Stat label="Unrealised gain" value={inr(t.gain)} tone={signTone(t.gain)} delta={t.invested > 0 ? <Delta value={t.gain}>{pct((t.gain / t.invested) * 100)}</Delta> : undefined} />
              <Stat label={<>XIRR, all schemes <Info label="What XIRR is">The yearly rate of return that accounts for when each rupee went in and came out: every purchase, redemption and dividend paid out, with today's value as the last amount.</Info></>}
                value={xirrText(t.xirr)} tone={signTone(t.xirr)} />
            </StatRow>
          </Card>

          <Card>
            <CardHead title="By category" />
            <BarList label="Funds by category" footnote="Share of the current value, by each scheme's official category."
              rows={view.allocation.map((a) => ({ key: a.broad, name: a.broad, note: `${a.schemes} scheme${a.schemes === 1 ? "" : "s"}${a.subs.length > 0 ? ` · ${a.subs.map((s) => s.sub).join(", ")}` : ""}`, value: a.pct == null ? "–" : `${a.pct.toFixed(1)}%`, pct: a.pct }))} />
          </Card>

          <Card>
            <CardHead title="Schemes" info={'Gain is the current value less the cost of the units held. XIRR counts every purchase, redemption and dividend paid out in the scheme; it isn\'t shown for less than 30 days, or when the cost of some units isn\'t known. "Taxed as" is read from the category; change it where your fund\'s documents say otherwise.'} />
            <DataTable label="Schemes" columns={schemeCols} rows={schemes} rowKey={(s) => s.key} />
            <Disclosure summary="What each tax kind means">
              <ul className="k-list muted">{(Object.keys(view.kinds) as Kind[]).map((k) => <li key={k}>{view.kinds[k]}</li>)}</ul>
            </Disclosure>
          </Card>

          {held.length > 0 && <FundCosts version={`${view.updated_at}|${view.txns}`} />}
          <FundBehaviour version={`${view.updated_at}|${view.txns}`} />

          {!view.gains_allowed && <PlanNote>Capital gains for each financial year, and every scheme you hold, are on the {view.gains_plan} plan.</PlanNote>}
          {view.gains && (
            <Card label="Capital gains">
              <CardHead title="Capital gains by financial year" actions={view.gains.years.length > 0 ? (
                <Select small label="Financial year" value={fy ?? ""} onChange={(x) => { setFy(Number(x)); rememberFy(Number(x)); setAllSales(false); }}
                  options={view.gains.years.map((x) => ({ value: x.fy, label: `${x.label}${x.fy === view.gains!.current_fy ? " (this year)" : ""}` }))} />
              ) : undefined} />
              {view.gains.years.length === 0 && <EmptyState title="No gains realised yet">No redemptions or switches out yet, so no gains have been realised.</EmptyState>}
              {y && (
                <>
                  <StatRow>
                    <Stat label="Short-term (net)" value={inr(y.stcg.net)} tone={signTone(y.stcg.net)} />
                    <Stat label="Long-term (net)" value={inr(y.ltcg.net)} tone={signTone(y.ltcg.net)} />
                    <Stat label="Tax at special rates" value={inr(y.tax)} note="before cess; slab-rate gains are taxed with your income" />
                    <Stat label="Dividends paid out" value={inr(y.dividends)} note="income at your slab rate" />
                  </StatRow>
                  {y.buckets.length > 0 && <DataTable label="Gains by rate" columns={bucketCols} rows={y.buckets} rowKey={(b) => b.key} />}
                  {y.steps.length > 0 && <ul className="k-list">{y.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
                  <p className="k-note">The long-term exemption here counts your funds alone. The <Link className="link" to="/tax-report">tax report</Link> adds these gains to your shares', shares the exemption and set-off between them, and includes them in the year's total tax estimate.</p>
                  {y.count > 0 && <DataTable label="Redemptions matched to purchases" columns={saleCols} rows={(allSales ? y.rows : y.rows.slice(0, 30)).map((r, i) => ({ ...r, i }))} rowKey={(r) => String(r.i)} />}
                  {y.rows.length > 30 && !allSales && <button type="button" className="btn quiet sm k-btn-end" onClick={() => setAllSales(true)}>Show all {y.rows.length}</button>}
                </>
              )}
              {view.gains.gf_missing.length > 0 && (
                <div className="k-stack">
                  <p className="k-small">Units held on 31 Jan 2018 cost at least that day's NAV. It isn't known for these schemes; enter it to use it:</p>
                  {view.gains.gf_missing.map((k) => <FmvRow key={k} label={name(k)} onSave={(v) => setFmv(k, v)} />)}
                </div>
              )}
              {schemes.filter((s) => s.fmv_yours).map((s) => (
                <p key={s.key} className="k-note">{s.name}: your 31 Jan 2018 NAV of {price(s.fmv_2018, "INR")} is used. <button type="button" className="btn quiet sm" onClick={() => setFmv(s.key, null)}>Clear it</button></p>
              ))}
              <Disclosure summary="How gains are worked out">
                <ul className="k-list muted">{view.gains.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </Disclosure>
            </Card>
          )}

          <section className="k-stack">
            <ul className="k-list muted" aria-label="Assumptions">{view.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            <p className="k-note">Your transactions are stored with your account only, used for this page, the tax report and your net worth, and never shared. As of {dateOnly(view.as_of)}.</p>
            <button type="button" className="btn danger k-btn-end" onClick={() => setAsking(true)}><Trash size={16} />Delete my mutual fund data</button>
          </section>
        </>
      )}
      {view && held.length === 0 && schemes.length > 0 && <p className="k-note">Every scheme in your files has been fully redeemed.</p>}
      {asking && <ConfirmDialog title="Delete my mutual fund data?" confirmLabel="Delete my mutual fund data" busy={busy} onConfirm={() => void remove()} onClose={() => setAsking(false)}>Every scheme and transaction is removed from StratLab. Your folios aren't touched.</ConfirmDialog>}
    </div>
  );
}

function FmvRow({ label, onSave }: { label: string; onSave: (v: number | null) => void }) {
  const [v, setV] = useState("");
  return (
    <div className="k-inset">
      <b>{label}</b>
      <FormGrid onSubmit={(e) => { e.preventDefault(); if (Number(v) > 0) onSave(Number(v)); }}>
        <Field label="NAV on 31 Jan 2018" unit="₹" inputMode="decimal" placeholder="e.g. 42.15" value={v} onChange={(e) => setV(e.target.value)} />
        <FormActions><button type="submit" className="btn" disabled={!(Number(v) > 0)}>Save</button></FormActions>
      </FormGrid>
    </div>
  );
}
