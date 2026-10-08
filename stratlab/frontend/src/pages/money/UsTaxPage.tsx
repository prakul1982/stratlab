import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, inr, money, qty as qtyText, signTone } from "../../lib/format";
import { Download, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { fyLink, movedYearNote, rememberFy, savedFy } from "../../lib/fy";
import { useAskedFy } from "../../lib/useFy";
import { Card, CardHead, type Column, ConfirmDialog, DataTable, DateField, Disclosure, EmptyState, Field, FormActions, FormGrid, Notice, PageHeader, PlanNote, Select, Skeleton, Stat, StatRow, UploadButton } from "../../components/kit";

/* /money/us-tax: US share sales in rupees the way the Income-tax Rules convert them, long or short term under the
 * 24-month rule, US dividends with the tax withheld and the foreign tax credit, and the calendar-year Schedule FA table.
 * Built from the kit (components/kit), amounts from lib/format. */

type Rate = { rate: number; on: string; fallback: boolean } | null;
type Sale = {
  symbol: string; bought: string; sold: string; qty: number; cost_usd: number; sale_usd: number; rate_buy: Rate; rate_sell: Rate;
  cost: number | null; indexed_cost: number | null; sale: number | null; gain: number | null; term: "ST" | "LT"; rate: number | null; bucket: string;
};
type Ftc = { income: number; foreign_tax: number; indian_tax: number; credit: number; not_credited: number };
type DivStock = { symbol: string; count: number; usd: number; tax_usd: number; inr: number; tax_inr: number; fallback: boolean; ftc: Ftc };
type Dividends = { fy: number; stocks: DivStock[]; usd: number; inr: number; tax_inr: number; ftc: Ftc; indian_rate: number; unpriced: number; estimated: boolean };
type Year = { fy: number; label: string; count: number; unpriced: number; st: number; lt: number; sale: number; fallback: boolean; rows?: Sale[]; dividends?: Dividends };
type FaRow = {
  symbol: string; name: string; lot: number; acquired: string; country: string; nature: string; initial: number | null; initial_usd: number;
  peak: number | null; peak_day: string | null; closing: number | null; closing_qty: number; income: number; proceeds: number | null;
};
type Fa = { cy: number; label: string; rows: FaRow[]; totals: Record<string, number>; missing_prices: string[]; missing_rates: number; fallback: boolean };
type Trade = { id: string; d: string; side: "B" | "S"; sym: string; qty: number; price: number; fees?: number; src?: string };
type OpenLot = { symbol: string; bought: string; qty: number; cost_usd: number; term: "ST" | "LT"; long_from: string | null };
type View = {
  as_of: string; fy: number; cy: number; cys: number[]; locked: boolean; plan: string; trades: Trade[]; files: { name: string; rows: number; at: string }[];
  gaps: { symbol: string; name: string; held: number; in_trades: number; missing: number; avg: number | null }[]; short: Record<string, number>;
  open_lots: OpenLot[];
  years: Year[]; fa: Fa | null; facts: string[]; assumptions: string[]; missing_history: string[];
  rates: { available: boolean; sbi_from: string | null; sbi_to: string | null; source: string; fallback: string }; names: Record<string, string>;
};
type ImportReply = { read: number; added: number; duplicates: number; problems: { line: number; text: string; reason: string }[]; month_first: boolean; us: View };

const usd = (v: number | null | undefined, dp = 2) => money(v, "USD", dp);
const rateText = (r: Rate) => (r ? `₹${r.rate.toFixed(2)} (${dateOnly(r.on)}${r.fallback ? ", RBI" : ""})` : "not known");
const today = () => new Date().toISOString().slice(0, 10);
const blank = { d: "", side: "B" as "B" | "S", sym: "", qty: "", price: "", fees: "" };
const tone = (v: number | null | undefined) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

export function UsTaxPage() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<View | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [getting, setGetting] = useState(false);
  const [asking, setAsking] = useState(false);

  const load = useCallback((fy?: number, cy?: number) => {
    const q = new URLSearchParams();
    if (fy) q.set("fy", String(fy));
    if (cy) q.set("cy", String(cy));
    return api<View>(`/money/us-tax${q.size ? `?${q}` : ""}`).then(setV).catch(fail);
  }, [fail]);
  const [movedFrom, setMovedFrom] = useState<number | null>(null);      // the empty year it opened past, if it did
  const asked = useAskedFy();             // a link's year ("?fy=2025") is the year it opens on
  // The Money pages' one rule (lib/fy openFy): the year a link asked for, else the year last picked, else the year being
  // filed; when that year has no sales and another has, the latest year with sales, said in one line.
  useEffect(() => {
    let live = true;
    (async () => {
      const want = asked ?? savedFy();
      const first = await api<View>(`/money/us-tax${want ? `?fy=${want}` : ""}`);
      if (!live) return;
      const here = first.years.find((x) => x.fy === first.fy);
      const busy = asked == null && !here?.count ? [...first.years].sort((a, b) => b.fy - a.fy).find((x) => x.count > 0) : undefined;
      if (!busy) { setV(first); return; }
      const v = await api<View>(`/money/us-tax?fy=${busy.fy}`);
      if (!live) return;
      setMovedFrom(first.fy);
      setV(v);
    })().catch((e) => live && fail(e));
    return () => { live = false; };
  }, [asked, fail]);

  const add = async () => {
    const body = { d: form.d, side: form.side, sym: form.sym.trim().toUpperCase(), qty: Number(form.qty), price: Number(form.price), fees: Number(form.fees || 0) };
    if (!body.d || !body.sym || !(body.qty > 0) || !(body.price >= 0) || form.price === "") { notify("Fill in the date, ticker, shares and price."); return; }
    setBusy(true);
    try {
      setV(await api<View>("/money/us-tax/trades", { method: "POST", body }));
      setForm(blank);
      notify(`${body.side === "B" ? "Purchase" : "Sale"} of ${body.sym} added.`);
      track("us trade added", { side: body.side });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const pick = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { notify("That file is larger than 5 MB."); reset(); return; }
    setBusy(true);
    try {
      const r = await api<ImportReply>(`/money/us-tax/import?${new URLSearchParams({ filename: f.name.slice(0, 200) })}`, { method: "POST", file: f });
      setV(r.us);
      setNote(`${r.added} trade${r.added === 1 ? "" : "s"} added${r.duplicates ? `, ${r.duplicates} already there (skipped)` : ""}${r.problems.length ? `, ${r.problems.length} line${r.problems.length === 1 ? "" : "s"} left out` : ""}.${r.month_first ? " Dates like 03/04/2025 were read month first, the US way." : ""}`);
      track("us trades imported", { rows: r.added });
    } catch (e) { fail(e); } finally { setBusy(false); reset(); }
  };
  const removeOne = async (id: string) => {
    try { setV(await api<View>(`/money/us-tax/trades/${encodeURIComponent(id)}`, { method: "DELETE" })); } catch (e) { fail(e); }
  };
  const removeAll = async () => {
    setBusy(true);
    try { await api("/money/us-tax", { method: "DELETE" }); setNote(null); await load(); notify("Your US trades are deleted."); } catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };
  const faCsv = async () => {
    if (!v?.fa) return;
    setGetting(true);
    try {
      const r = await api<Response>(`/money/us-tax/schedule-fa.csv?cy=${v.fa.cy}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-schedule-FA-CY${v.fa.cy}.csv`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); } finally { setGetting(false); }
  };

  const y = v?.years.find((x) => x.fy === v.fy) ?? v?.years[0];
  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const tradeCols: Column<Trade>[] = [
    { key: "d", header: "Date", rowHeader: true, cell: (t) => dateOnly(t.d) },
    { key: "side", header: "Trade", cell: (t) => (t.side === "B" ? "Purchase" : "Sale") },
    { key: "sym", header: "Ticker", cell: (t) => <b>{t.sym}</b> },
    { key: "qty", header: "Shares", numeric: true, cell: (t) => qtyText(t.qty) },
    { key: "price", header: "Price", numeric: true, cell: (t) => usd(t.price) },
    { key: "fees", header: "Fees", numeric: true, cell: (t) => usd(t.fees ?? 0) },
    { key: "x", header: "", action: true, cell: (t) => (t.id ? <button type="button" className="btn quiet sm" aria-label={`Delete the ${t.sym} trade of ${t.d}`} onClick={() => removeOne(t.id)}><Trash size={14} /></button> : null) },
  ];
  const saleCols: Column<Sale>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => <b>{r.symbol}</b> },
    { key: "bought", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "sold", header: "Sold", numeric: true, cell: (r) => dateOnly(r.sold) },
    { key: "qty", header: "Shares", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "cost", header: "Cost", numeric: true, cell: (r) => usd(r.cost_usd) },
    { key: "rb", header: "Rate used", cell: (r) => rateText(r.rate_buy) },
    { key: "costinr", header: "Cost (₹)", numeric: true, cell: (r) => <>{inr(r.indexed_cost ?? r.cost)}{r.indexed_cost != null && <span className="k-sub-line">indexed</span>}</> },
    { key: "sale", header: "Sale", numeric: true, cell: (r) => usd(r.sale_usd) },
    { key: "rs", header: "Rate used", cell: (r) => rateText(r.rate_sell) },
    { key: "saleinr", header: "Sale (₹)", numeric: true, cell: (r) => inr(r.sale) },
    { key: "gain", header: "Gain (₹)", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
    { key: "term", header: "Term", cell: (r) => (r.term === "LT" ? `Long, ${r.rate === 0.2 ? "20%" : "12.5%"}` : "Short, slab") },
  ];
  const divCols: Column<DivStock>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (s) => <b>{s.symbol}</b> },
    { key: "usd", header: "Dividends", numeric: true, cell: (s) => usd(s.usd) },
    { key: "tax", header: "US tax", numeric: true, cell: (s) => usd(s.tax_usd) },
    { key: "inr", header: "Dividends (₹)", numeric: true, cell: (s) => inr(s.inr) },
    { key: "taxinr", header: "US tax (₹)", numeric: true, cell: (s) => inr(s.tax_inr) },
    { key: "ind", header: "Indian tax on it (₹)", numeric: true, cell: (s) => inr(s.ftc.indian_tax) },
    { key: "credit", header: "Credit (₹)", numeric: true, cell: (s) => inr(s.ftc.credit) },
  ];
  const lotCols: Column<OpenLot>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (l) => <b>{l.symbol}</b> },
    { key: "bought", header: "Bought", numeric: true, cell: (l) => dateOnly(l.bought) },
    { key: "qty", header: "Shares", numeric: true, cell: (l) => qtyText(l.qty) },
    { key: "cost", header: "Cost", numeric: true, cell: (l) => usd(l.cost_usd) },
    { key: "term", header: "Term today", cell: (l) => (l.term === "LT" ? "Long-term" : <>Short-term<span className="k-sub-line">long-term from {dateOnly(l.long_from)}</span></>) },
  ];
  const faCols: Column<FaRow>[] = [
    { key: "entity", header: "Entity", rowHeader: true, wrap: true, cell: (r) => <><b>{r.name}</b><span className="k-sub-line">{r.symbol} · lot {r.lot}</span></> },
    { key: "acq", header: "Acquired", numeric: true, cell: (r) => dateOnly(r.acquired) },
    { key: "init", header: "Initial value", numeric: true, cell: (r) => inr(r.initial) },
    { key: "peak", header: "Peak value", numeric: true, cell: (r) => <>{inr(r.peak)}{r.peak_day && <span className="k-sub-line">{dateOnly(r.peak_day)}</span>}</> },
    { key: "close", header: "Closing balance", numeric: true, cell: (r) => inr(r.closing) },
    { key: "inc", header: "Income credited", numeric: true, cell: (r) => inr(r.income) },
    { key: "proc", header: "Sale proceeds", numeric: true, cell: (r) => (r.proceeds == null ? "–" : inr(r.proceeds)) },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Tax" title="US stocks in Indian tax" asOf={v?.as_of} asOfLabel="Rates up to"
        lede="Your US share sales in rupees, long or short term under the 24-month rule, US dividends with the foreign tax credit, and the Schedule FA table."
        info="Sales are converted the way the Income-tax Rules say; the calendar-year Schedule FA table is for the return. Only you can see these figures." infoLabel="What this page covers" />
      <Notice label="Estimate only"><b>Estimate only.</b> Arithmetic on your own trades, not tax advice, for a resident individual. Check it with a chartered accountant (CA) before you file.</Notice>

      <Card>
        <CardHead title="Your US trades" info="Upload your US broker's trade history as CSV or Excel (columns for the date, purchase or sale, the ticker, shares and the price in dollars; fees optional), or add each purchase and sale below. Dates are best as YYYY-MM-DD."
          actions={<>
            <UploadButton quiet label="Upload US trades" busy={busy} accept=".csv,.xlsx,.txt,text/csv" ariaLabel="US trades file" onFiles={pick} />
            {!!v?.trades.length && <button type="button" className="btn quiet sm" onClick={() => setAsking(true)}><Trash size={16} />Delete all US trades</button>}
          </>} />
        {note && <p className="k-small" role="status">{note}</p>}
        <div role="group" aria-label="Add a trade">
          <FormGrid onSubmit={(e) => { e.preventDefault(); void add(); }}>
            <DateField label="Date" value={form.d} max={today()} onChange={(d) => set("d")({ target: { value: d } })} ariaLabel="Trade date" />
            <Field label="Trade">{(id) => <Select id={id} value={form.side} label="Purchase or sale" onChange={(x) => setForm((f) => ({ ...f, side: x as "B" | "S" }))} options={[{ value: "B", label: "Purchase" }, { value: "S", label: "Sale" }]} />}</Field>
            <Field label="Ticker" value={form.sym} onChange={set("sym")} placeholder="AAPL" maxLength={10} aria-label="Ticker" />
            <Field label="Shares" type="number" inputMode="decimal" min={0} step="any" value={form.qty} onChange={set("qty")} aria-label="Shares" />
            <Field label="Price" unit="$" type="number" inputMode="decimal" min={0} step="any" value={form.price} onChange={set("price")} aria-label="Price in dollars" />
            <Field label="Fees" optional unit="$" type="number" inputMode="decimal" min={0} step="any" value={form.fees} onChange={set("fees")} aria-label="Fees in dollars" />
            <FormActions><button type="submit" className="btn" disabled={busy}>Add trade</button></FormActions>
          </FormGrid>
        </div>
        {v && v.gaps.length > 0 && (
          <div className="k-stack" aria-label="Holdings without purchases">
            {v.gaps.map((g) => (
              <p key={g.symbol} className="k-small">
                <b>{g.symbol}</b>: <Link className="link" to="/holdings">My Holdings</Link> has {qtyText(g.held)} shares; your trades cover {qtyText(g.in_trades)}.{" "}
                <button type="button" className="btn quiet sm" onClick={() => setForm({ ...blank, sym: g.symbol, qty: String(g.missing), price: g.avg ? String(g.avg) : "" })}>Add its purchase</button>
              </p>
            ))}
          </div>
        )}
        {v && Object.keys(v.short).length > 0 && (
          <p className="k-small">Sold with no purchase in your trades: {Object.entries(v.short).map(([s, q]) => `${s} (${qtyText(q)} shares)`).join(", ")}. Their gain isn't counted; add the purchases.</p>
        )}
        {v && v.trades.length > 0 && (
          <Disclosure summary={<>{v.trades.length} trade{v.trades.length === 1 ? "" : "s"}{v.files.length ? ` · last file ${ago(v.files[v.files.length - 1].at)}` : ""}</>}>
            <DataTable label="US trades" columns={tradeCols} rows={v.trades.slice(0, 200)} rowKey={(t) => t.id || `${t.d}${t.sym}${t.qty}${t.price}`} />
          </Disclosure>
        )}
      </Card>

      {!v && <Card><Skeleton label="Opening your US stocks" /></Card>}
      {v && v.trades.length === 0 && (
        <EmptyState title="No US trades yet">Add your US purchases and sales above to see each sale's gain in rupees, which lots are long term, and the Schedule FA table.</EmptyState>
      )}

      {v && v.trades.length > 0 && y && (
        <>
          {!v.rates.available && <Notice tone="warn">The rupee rates couldn't be loaded just now, so the rupee figures are missing. Try again in a while.</Notice>}
          <FormGrid label="Choose the year">
            <Field label="Financial year">{(id) => <Select id={id} value={y.fy} onChange={(x) => { rememberFy(Number(x)); setMovedFrom(null); load(Number(x), v.cy); }} options={v.years.map((x) => ({ value: x.fy, label: x.label }))} />}</Field>
          </FormGrid>
          {movedFrom != null && movedFrom !== y.fy && <p className="k-small k-muted" data-testid="us-moved-year">{movedYearNote(movedFrom, y.fy, Math.max(...v.years.map((x) => x.fy)), "sales")}</p>}
          <Card>
            <CardHead title={`Sales in ${y.label}`} />
            <StatRow>
              <Stat label="Short-term gain (held 24 months or less)" value={inr(y.st)} tone={signTone(y.st)} note="at your slab rate" />
              <Stat label={<>Long-term gain</>} value={inr(y.lt)} tone={signTone(y.lt)} note="12.5% (section 112)" />
              <Stat label={`Sales in ${y.label}`} value={y.count} note={`${inr(y.sale)} sale value`} />
            </StatRow>
            <p className="k-note">Shares listed abroad are taxed like unlisted shares in India: long term when held more than 24 months, at 12.5% without indexation for sales from 23 July 2024 (20% with indexation before), with no ₹1.25 lakh exemption. Short-term gains are added to your income at your slab rate.</p>
            {y.unpriced > 0 && <p className="k-small">{y.unpriced} sale{y.unpriced === 1 ? " has" : "s have"} no rupee rate for its dates yet, so {y.unpriced === 1 ? "it isn't" : "they aren't"} counted.</p>}
            <p className="k-note">These sales are in your <Link className="link" to={fyLink("/tax-report", y.fy)}>tax report</Link> too, where losses are set off against your other gains, and in the <Link className="link" to={fyLink("/money/itr", y.fy)}>ITR-ready export</Link>.</p>
          </Card>

          {v.locked ? <PlanNote>Each sale's rupee workings, US dividends with the foreign tax credit, and Schedule FA are on the {v.plan} plan.</PlanNote> : (
            <>
              <Card>
                <CardHead title="Each sale in rupees" />
                {!y.rows?.length ? <EmptyState title={`No US sales in ${y.label}`}>Sales you add or upload show here with the rate used for each.</EmptyState>
                  : <DataTable label="US sales in rupees" columns={saleCols} rows={y.rows} rowKey={(r) => `${r.symbol}${r.bought}${r.sold}${r.qty}${r.cost_usd}`} />}
                <p className="k-note">Rule 115: the sale at SBI's TT buying rate on the last day of the month before the sale, the cost at the rate on the last day of the month before the purchase; the last rate SBI published when it has none that day. "RBI" marks the RBI reference rate, used where SBI's rate isn't known.</p>
              </Card>

              <Card>
                <CardHead title="US dividends and the foreign tax credit" info="The US withholds 25% of dividends paid to an Indian resident who gave the broker a W-8BEN (India-US treaty, Article 10). India taxes the dividend at your slab rate and gives credit for the US tax, but never more than the Indian tax on that dividend. You claim it by filing Form 67 by the end of the assessment year." infoLabel="How the credit works" />
                {!y.dividends || !y.dividends.stocks.length ? <EmptyState title={`No US dividends in ${y.label}`}>Dividends from your US holdings show here with the US tax withheld.</EmptyState> : (
                  <>
                    <DataTable label="US dividends and credit" columns={divCols} rows={y.dividends.stocks} rowKey={(s) => s.symbol} />
                    <p className="k-small">Credit for {y.label}: <b>{inr(y.dividends.ftc.credit)}</b> of the {inr(y.dividends.tax_inr)} US tax{y.dividends.ftc.not_credited > 0.5 ? `; ${inr(y.dividends.ftc.not_credited)} can't be credited (more than the Indian tax on the dividends)` : ""}. Indian tax on the dividends at your average rate of {(y.dividends.indian_rate * 100).toFixed(2)}% from the <Link className="link" to={fyLink("/tax-report", y.fy)}>total tax estimate</Link>.</p>
                    {y.dividends.estimated && <p className="k-note">Estimated: each dividend the company paid × the shares your trades held on its ex-date, dated by the ex-date. Upload your broker's dividend statement in <Link className="link" to={fyLink("/money/tax-tools", y.fy)}>Tax tools</Link> for the actual figures.</p>}
                  </>
                )}
              </Card>
            </>
          )}

          <Card>
            <CardHead title="Shares you still hold" />
            {!v.open_lots.length ? <EmptyState title="No US shares open">Your trades leave no US shares open.</EmptyState>
              : <DataTable label="Open US lots" columns={lotCols} rows={v.open_lots} rowKey={(l) => `${l.symbol}${l.bought}${l.qty}`} />}
            <p className="k-note">Facts only: when each lot turns long term under the 24-month rule.</p>
          </Card>

          {!v.locked && v.fa && (
            <Card label="Schedule FA">
              <CardHead title="Schedule FA, Table A3" info="Residents list every foreign asset held at any time in the calendar year (1 January to 31 December) in Schedule FA of ITR-2 or ITR-3. Table A3 takes one line per purchase lot of foreign shares, with the initial, peak and closing value and the income, each at SBI's TT buying rate on its own date." infoLabel="What Schedule FA is"
                actions={<>
                  <Select small label="Calendar year" value={v.fa.cy} onChange={(c) => load(v.fy, Number(c))} options={v.cys.map((c) => ({ value: c, label: String(c) }))} />
                  <button type="button" className="btn quiet sm" disabled={getting} onClick={faCsv}><Download size={16} />{getting ? "Making the CSV…" : "Download CSV"}</button>
                </>} />
              <p className="k-small k-muted">{v.fa.label}.</p>
              {!v.fa.rows.length ? <EmptyState title={`No US shares were held in ${v.fa.cy}`}>Pick another calendar year above.</EmptyState>
                : <DataTable label="Schedule FA" columns={faCols} rows={v.fa.rows} rowKey={(r) => `${r.symbol}-${r.lot}`} />}
              {v.fa.missing_prices.length > 0 && <p className="k-small">No daily prices for {v.fa.missing_prices.join(", ")}, so their peak and closing values are blank. Use your broker's year statement for them.</p>}
              <p className="k-note">Country: 2-UNITED STATES OF AMERICA; nature of entity: company. Fill each company's address and ZIP code from its annual report. The broker account's cash goes in Table A2, from your broker's statement.</p>
            </Card>
          )}
        </>
      )}

      <Card>
        <CardHead title="Deadlines and rules" />
        <ul className="k-list" aria-label="Deadlines and rules">{(v?.facts ?? []).map((f, i) => <li key={i}>{f}</li>)}</ul>
        <h3 className="k-sub">How these figures are worked out</h3>
        <ul className="k-list muted">{(v?.assumptions ?? []).map((f, i) => <li key={i}>{f}</li>)}</ul>
        {v?.rates.sbi_to && <p className="k-note">Rupees a dollar: {v.rates.source}, from SBI's daily rate sheets ({dateOnly(v.rates.sbi_from)} to {dateOnly(v.rates.sbi_to)}); the RBI reference rate where SBI's isn't known, marked "RBI".</p>}
      </Card>

      {asking && <ConfirmDialog title="Delete all your US trades?" confirmLabel="Delete all US trades" busy={busy} onConfirm={() => void removeAll()} onClose={() => setAsking(false)}>Every US trade is removed from StratLab. Your broker account isn't touched.</ConfirmDialog>}
    </div>
  );
}
