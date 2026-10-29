import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, fmtDate, money } from "../../lib/format";
import { useMoreColumns } from "../../components/MoreColumns";
import { Badge, Card, CardHead, DataTable, ErrorState, Field, FormGrid, Select, Skeleton, type Column } from "../../components/kit";
import { aboutRupees, parsePrice, priceLabel, rateNote, ratesRead } from "./prices";

type Row = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number; charged_in: string;
  auto: boolean; rate: number | null; no_rate?: boolean;
  /** how the price is set (DJ-015): the fixed price of `fixed_on`, one typed here, or (older rows) following the rupee price */
  price_set?: "default" | "owner" | "follows";
  plan_basic: string | null; plan_pro: string | null; plan_basic_year: string | null; plan_pro_year: string | null };
type View = { currencies: Record<string, Row>; fixed_on?: string; rates_at: string | null; rates_read_at?: Record<string, string>; rate_errors: string[] };
const PRICE = ["basic", "pro", "basic_year", "pro_year"] as const;
const PLAN = ["plan_basic", "plan_pro", "plan_basic_year", "plan_pro_year"] as const;
const LABEL: Record<string, string> = { basic: "Basic / month", pro: "Pro / month", basic_year: "Basic / year", pro_year: "Pro / year" };

/** Prices outside India, per currency, and the Razorpay plan that charges each one (blank: charged in rupees). */
export function PricesPanel() {
  const { fail, notify } = useApp();
  const [rows, setRows] = useState<Record<string, Row> | null>(null);
  const [fixedOn, setFixedOn] = useState<string | null>(null);
  const [fx, setFx] = useState<{ readAt: Record<string, string>; errors: string[] }>({ readAt: {}, errors: [] });
  const show = (x: View) => { setRows(x.currencies); setFixedOn(x.fixed_on ?? null); setFx({ readAt: x.rates_read_at ?? (x.rates_at ? { all: x.rates_at } : {}), errors: x.rate_errors }); };
  const [edit, setEdit] = useState<Record<string, Partial<Record<string, string>>>>({});
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const more = useMoreColumns("admin-prices", 2);     // the yearly prices: one click away, so the table fits a laptop
  const shown = more.on ? PRICE : PRICE.slice(0, 2);
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => { setFailed(false); api<View>("/admin/prices").then(show).catch((e) => { setFailed(true); fail(e); }); }, [fail, tries]);
  const readRates = async () => {
    setBusy(true);
    try { show(await api<View>("/admin/prices/rates", { method: "POST" })); notify("Exchange rates read."); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const automatic = async (c: string) => {
    setBusy(true);
    try {
      show(await api<View>("/admin/prices", { method: "PUT", body: { currencies: { [c]: { basic: null, pro: null, basic_year: null, pro_year: null } } } }));
      setEdit((e) => { const n = { ...e }; delete n[c]; return n; });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const val = (c: string, f: string) => edit[c]?.[f] ?? String((rows?.[c] as unknown as Record<string, unknown>)?.[f] ?? "");
  const set = (c: string, f: string, v: string) => { setErrs((x) => { const n = { ...x }; delete n[`${c}.${f}`]; return n; }); setEdit((e) => ({ ...e, [c]: { ...e[c], [f]: v } })); };
  const save = async () => {
    const body: Record<string, Record<string, number | string | null>> = {};
    const bad: Record<string, string> = {};
    for (const [c, ch] of Object.entries(edit)) {
      body[c] = {};
      for (const [f, v] of Object.entries(ch)) {
        if (!(PRICE as readonly string[]).includes(f)) { body[c][f] = (v ?? "").trim(); continue; }
        const n = parsePrice(v);
        if (n === undefined) bad[`${c}.${f}`] = `Type a number, like 8 or 1,999.50. Leave it empty for the price set ${fixedOn ? fmtDate(fixedOn, { year: false }) : "by StratLab"}.`;
        else body[c][f] = n;
      }
    }
    setErrs(bad);
    if (Object.keys(bad).length) return;
    setBusy(true);
    try { show(await api<View>("/admin/prices", { method: "PUT", body: { currencies: body } })); setEdit({}); notify("Prices saved."); } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const list = Object.entries(rows ?? {}).filter(([c]) => c !== "INR").map(([c, r]) => ({ c, r }));
  /** a row that departs from the rule (the set price, charged in rupees) */
  const odd = (r: Row) => !!r.no_rate || r.price_set === "owner" || r.price_set === "follows" || !r.price_set;
  const cols: Column<{ c: string; r: Row }>[] = [
    { key: "cur", header: "Currency", rowHeader: true, wrap: true, cell: ({ c, r }) => (
      <span><b>{c}</b> <span className="k-small k-muted">{r.name}{r.rate ? ` · ${money(r.rate, "INR", r.rate < 1 ? 4 : 2)}` : ""}</span></span>) },
    ...shown.map((f): Column<{ c: string; r: Row }> => ({ key: f, header: LABEL[f], numeric: true, cell: ({ c, r }) => (
      <span className="k-stack"><input className="k-input adm-num-input" value={val(c, f)} onChange={(e) => set(c, f, e.target.value)} inputMode="decimal" aria-label={`${c} ${LABEL[f]}`}
        aria-invalid={errs[`${c}.${f}`] ? true : undefined} aria-describedby={errs[`${c}.${f}`] ? `price-err-${c}-${f}` : undefined} />
        {/* what the price is in rupees today, so the spread between currencies shows (DJ-019) */}
        {aboutRupees(Number(val(c, f)), r.rate) && <span className="k-note k-muted">{aboutRupees(Number(val(c, f)), r.rate)}</span>}
        {errs[`${c}.${f}`] && <span id={`price-err-${c}-${f}`} className="k-note" role="alert">{errs[`${c}.${f}`]}</span>}</span>) })),
    // the chips say only what differs from the rule: the set price and rupee charging are said once under the table, not on all 18 rows (LIVE1C-009)
    ...(list.some(({ r }) => odd(r)) ? [{ key: "mode", header: "Price", cell: ({ c, r }) => r.no_rate ? <Badge tone="warn" dot={false}>No rate: not shown to visitors</Badge>
      : r.price_set === "owner" ? <button type="button" className="btn quiet sm" disabled={busy} onClick={() => automatic(c)}
        title={`Go back to the price set ${fixedOn ? fmtDate(fixedOn, { year: false }) : "by StratLab"}`}>{priceLabel(r.price_set, fixedOn)} · undo</button>
      : r.price_set === "follows" || !r.price_set ? <Badge tone="ok" dot={false}>{priceLabel(r.price_set ?? (r.auto ? "follows" : "owner"), fixedOn)}</Badge> : null } as Column<{ c: string; r: Row }>] : []),
    ...(list.some(({ c, r }) => r.charged_in === c) ? [{ key: "in", header: "Charged in", cell: ({ c, r }) => (r.charged_in === c ? <Badge tone="ok" dot={false}>{c}</Badge> : null) } as Column<{ c: string; r: Row }>] : []),
  ];

  return (
    <Card label="Prices outside India">
      <CardHead title="Prices outside India"
        info={<>Visitors see prices in their own currency (picked from their country; they can switch). Every price here is <b>fixed</b>: set {fixedOn ? fmtDate(fixedOn) : "by StratLab"} from the rupee price and rounded, it doesn't move with the exchange rate, and changing the rupee price doesn't change it. Type a price to change one; empty the box to go back to the set price. <b>Read today's rates</b> only updates the "about ₹…" notes and what a card charged in rupees pays. No Razorpay plan is needed: without one, visitors pay the rupee price and their card converts it. Only to charge in a currency itself, create a plan in Razorpay in that currency for the same amount and paste the plan ID.</>}
        actions={<>
          {more.toggle}
          <button type="button" className="btn quiet sm" disabled={busy} onClick={readRates}>Read today's rates</button>
          <button type="button" className="btn sm" disabled={busy || !Object.keys(edit).length} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
        </>} />
      <p className="k-note k-muted">{ratesRead(fx.readAt, ago)}
        {rows ? ` ${rateNote(fx.errors, rows)}` : ""}</p>
      {!rows ? (failed ? <ErrorState title="The prices couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }} /> : <Skeleton label="Loading prices" />) : (
        <>
          <DataTable label="Prices outside India" rows={list} rowKey={(x) => x.c} columns={cols} />
          <p className="k-note k-muted">{list.some(({ r }) => odd(r)) ? "Rows without a mark are the set price" : "Every price is the set price"}{fixedOn ? ` of ${fmtDate(fixedOn, { year: false })}` : ""}, and a card is charged in rupees unless a row says it has a plan in its own currency.</p>
          <div className="k-row">
            <label htmlFor="price-plan-currency" className="k-small">Razorpay plan IDs for</label>
            <Select id="price-plan-currency" small value={open ?? ""} onChange={(v) => setOpen(v || null)} label="Currency for the Razorpay plan IDs"
              options={[{ value: "", label: "Choose a currency" }, ...list.map(({ c }) => ({ value: c, label: c }))]} />
          </div>
        </>
      )}
      {open && rows?.[open] && (
        <FormGrid label={`${open} Razorpay plans`}>
          {PLAN.map((f) => (
            <Field key={f} label={`${LABEL[f.replace("plan_", "")]} plan ID`} value={val(open, f)} onChange={(e) => set(open, f, e.target.value)} placeholder="plan_…" />
          ))}
        </FormGrid>
      )}
    </Card>
  );
}
