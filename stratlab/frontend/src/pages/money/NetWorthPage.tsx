import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type ApiError } from "../../lib/api";
import { numberProblem, type Limits } from "../../lib/validate";
import { useApp } from "../../lib/app";
import { useMarketRefresh } from "../../lib/marketLive";
import { LoanCheck } from "./LoanCheck";
import { asOf, axisInr, dateOnly, inr, inrCompact, istToday, signedInrCompact } from "../../lib/format";
import { mergeLiveNetWorth, netWorthDelta, pricedMarkets, restatedNote, sinceNote } from "../../lib/networth";
import { Modal } from "../../components/ui";
import { XYChart } from "../../components/Charts";
import { Download, Plus, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Card, CardHead, ChartFrame, ConfirmDialog, DateField, DataTable, Delta, EmptyState, ErrorState, FactTable, Field, FormActions, FormGrid, Notice, Notes, PageHeader, PlanNote, Select, ShareTable, Skeleton, TilePicker, useRange, type Column, type TileGroup } from "../../components/kit";

/* /money/net-worth: what you own minus what you owe: stocks from My Holdings, plus the deposits, provident funds, gold,
 * property and loans added here, each with how it is worked out and its date. Built from the kit (components/kit). */

type Kind = "epf" | "ppf" | "nps" | "fd" | "rd" | "gold" | "sgb" | "cash" | "property" | "crypto" | "other" | "loan" | "policy";
type Entry = Record<string, string | number | null | undefined> & { kind: Kind; id: string; name?: string };
type Row = {
  id: string; kind: string; label: string; name: string; class?: string; value: number | null; as_of: string | null; basis: string; rule: string;
  facts: Record<string, any>; entry?: Entry; linked?: string | null;
};
type Policy = {
  id: string; label: string; name: string; insurer: string; sum_assured: number | null; premium: number; frequency: string; yearly_premium: number | null;
  next_due: string | null; due_in: number | null; nominee: string | null; entry: Entry;
};
type Snapshot = { d: string; net: number; assets: number; liabilities: number; why: string; partial?: string[]; added?: number; m?: number };
type View = {
  as_of: string; computed_at: string; totals: { assets: number; liabilities: number; net: number; oldest_as_of: string | null; partial?: string[] | null; partial_lasting?: boolean; notes?: string[] | null };
  allocation: { class: string; label: string; value: number; pct: number | null }[]; assets: Row[]; liabilities: Row[];
  insurance: { policies: Policy[]; yearly_premium: number; cover: Record<string, number>; next: string | null };
  gold_price: { per_g: number; as_of: string } | null; rates: { epf: number; epf_note: string; ppf: number; ppf_note: string; sgb: number };
  history: Snapshot[] | null; history_allowed: boolean; history_count: number; valuation?: number;
  limit: number | null; count: number; deposit_tax?: DepositTax | null;
};
type DepositTax = { tax_rate: number; basis: "estimate" | "slab"; items: Record<string, { interest: number; interest_after_tax: number }> };
type Prepay = {
  outstanding: number; amount: number; closes: boolean; emi: number; months_left: number; interest_left?: number; interest_saved?: number; note: string;
  tenure: { months_left: number; months_saved: number; interest_saved: number; ends: string } | null;
  lower_emi: { emi: number; emi_change: number; interest_saved: number; months_left: number } | null;
};
type Ask = { title: string; body: string; label: string; run: () => Promise<void> };

const day = (iso: string | null | undefined) => asOf(iso) ?? "–";
const today = () => istToday();      // India's day, not UTC's: between 00:00 and 05:30 IST UTC is still yesterday

type Ftype = "money" | "rate" | "date" | "int" | "num" | "text" | "select";
type F = {
  k: string; label: string; type: Ftype; options?: [string, string][]; optional?: boolean; hint?: string; unit?: string; info?: ReactNode;
  /** asked only for a floating-rate loan */ floating?: boolean;
};
const isFloating = (form: Record<string, string>) => !!form.benchmark && form.benchmark !== "fixed";
const NAME: F = { k: "name", label: "Name", type: "text", optional: true, hint: "e.g. HDFC savings" };
const AS_OF: F = { k: "as_of", label: "Value as of", type: "date", optional: true };
const RATE: F = { k: "rate", label: "Interest rate", type: "rate" };
/** What each kind of entry asks for. */
const FORM: Record<Kind, { title: string; fields: F[]; note?: string }> = {
  epf: { title: "EPF", fields: [NAME, { k: "balance", label: "Balance", type: "money" }, { k: "as_of", label: "Balance as of", type: "date", optional: true },
    { k: "monthly", label: "Monthly contribution", type: "money", optional: true, info: "Yours and your employer's together." },
    { ...RATE, optional: true, hint: "8.25", info: "Leave it empty to use the declared rate." }],
    note: "Interest is worked out monthly on the running balance and credited on 31 March, at the declared rate unless you enter another." },
  ppf: { title: "PPF", fields: [NAME, { k: "balance", label: "Balance", type: "money" }, { k: "as_of", label: "Balance as of", type: "date", optional: true },
    { k: "paid_since", label: "Deposited since that date", type: "money", optional: true, info: "This year's deposit, when the balance above is from before it (the 1 April balance, say)." },
    { k: "yearly", label: "Yearly deposit (up to ₹1,50,000)", type: "money", optional: true }, { k: "opened", label: "Account opened on", type: "date", optional: true },
    { ...RATE, optional: true, hint: "7.1", info: "Leave it empty to use the declared rate." }],
    note: "Matures after 15 whole financial years from the end of the year it was opened in." },
  nps: { title: "NPS", fields: [NAME, { k: "tier1", label: "Tier I value", type: "money" }, { k: "tier2", label: "Tier II value", type: "money", optional: true }, AS_OF] },
  fd: { title: "Fixed deposit", fields: [NAME, { k: "principal", label: "Amount deposited", type: "money" }, RATE,
    { k: "compounding", label: "Interest compounds", type: "select", options: [["quarterly", "Every quarter"], ["monthly", "Every month"], ["half-yearly", "Every six months"], ["yearly", "Every year"], ["simple", "Simple interest"]] },
    { k: "start", label: "Start date", type: "date" }, { k: "maturity", label: "Maturity date", type: "date" }] },
  rd: { title: "Recurring deposit", fields: [NAME, { k: "monthly", label: "Monthly instalment", type: "money" }, RATE,
    { k: "start", label: "First instalment on", type: "date" }, { k: "maturity", label: "Maturity date", type: "date" }], note: "Each instalment compounds every quarter." },
  gold: { title: "Gold", fields: [NAME, { k: "grams", label: "Grams", type: "num", optional: true, unit: "g" },
    { k: "purity", label: "Purity", type: "select", options: [["24", "24 carat"], ["22", "22 carat"], ["18", "18 carat"], ["14", "14 carat"]] },
    { k: "price_per_g", label: "Your own price a gram", type: "money", optional: true },
    { k: "value", label: "Or its value", type: "money", optional: true, info: "Used when there's no price." }, AS_OF] },
  sgb: { title: "Sovereign gold bond", fields: [NAME, { k: "units", label: "Units", type: "num", unit: "grams" }, { k: "issue_price", label: "Issue price a gram", type: "money", optional: true },
    { k: "start", label: "Issue date", type: "date", optional: true }, { k: "maturity", label: "Maturity date", type: "date", optional: true, info: "8 years after the issue date when empty." }],
    note: "Interest of 2.5% a year on the issue price is paid every six months to your bank, so it isn't added to the value." },
  cash: { title: "Savings and cash", fields: [NAME, { k: "value", label: "Amount", type: "money" }, AS_OF] },
  property: { title: "Property", fields: [NAME, { k: "value", label: "Value", type: "money", info: "Your own estimate." }, AS_OF] },
  crypto: { title: "Crypto", fields: [NAME, { k: "coin", label: "Coin", type: "text", optional: true, hint: "BTC" }, { k: "qty", label: "Quantity", type: "num", optional: true },
    { k: "value", label: "Or its value", type: "money", optional: true, info: "Used when there's no price." }, AS_OF] },
  other: { title: "Other asset", fields: [NAME, { k: "value", label: "Value", type: "money" }, AS_OF] },
  loan: { title: "Loan or card", fields: [NAME, { k: "loan_type", label: "Kind", type: "select", options: [["home", "Home loan"], ["car", "Car loan"], ["personal", "Personal loan"], ["education", "Education loan"], ["credit_card", "Credit card"], ["other", "Other loan"]] },
    { k: "lender", label: "Lender", type: "text", optional: true }, { k: "principal", label: "Amount borrowed", type: "money", info: "For a card, the amount owed." },
    RATE, { k: "tenure_months", label: "Tenure", type: "int", optional: true, unit: "months", info: "Leave it empty for a card." },
    { k: "start", label: "Loan start date", type: "date", optional: true },
    { k: "benchmark", label: "Rate type", type: "select", options: [["fixed", "Fixed"], ["repo", "Floating: repo-linked"], ["tbill", "Floating: T-bill-linked"], ["mclr", "Floating: MCLR"], ["other", "Floating: other internal rate"]] },
    { k: "spread", label: "Spread over the benchmark", type: "rate", optional: true, hint: "2.75", floating: true, unit: "points" },
    { k: "reset_months", label: "Rate resets every", type: "select", options: [["3", "3 months"], ["1", "Month"], ["6", "6 months"], ["12", "12 months"]], floating: true },
    { k: "last_reset", label: "Last reset date", type: "date", optional: true, floating: true },
    { k: "current_rate", label: "Rate on your latest statement", type: "rate", optional: true, floating: true }],
    note: "With a tenure, the EMI, the balance owed today and this year's interest are worked out on reducing balance, the first EMI a month after the start. For a floating rate, the loan check below compares your statement's rate with the benchmark." },
  policy: { title: "Insurance policy", fields: [NAME, { k: "policy_type", label: "Kind", type: "select", options: [["term", "Term"], ["health", "Health"], ["life", "Life"], ["vehicle", "Vehicle"], ["other", "Other"]] },
    { k: "insurer", label: "Insurer", type: "text" }, { k: "sum_assured", label: "Sum assured", type: "money", optional: true }, { k: "premium", label: "Premium", type: "money" },
    { k: "frequency", label: "Paid", type: "select", options: [["yearly", "Every year"], ["half-yearly", "Every six months"], ["quarterly", "Every quarter"], ["monthly", "Every month"], ["single", "Once"]] },
    { k: "due", label: "Next premium due", type: "date", optional: true }, { k: "nominee", label: "Nominee", type: "text", optional: true }],
    note: "Policies are listed for their dates and premiums; they aren't counted in net worth." },
};

/** The entry types as tiles, grouped by what the person is adding. */
const ic = {
  cash: <path d="M3 7h18v10H3z M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" />, fd: <path d="M4 20V9l8-5 8 5v11M9 20v-6h6v6" />,
  ret: <path d="M12 3v18M5 10l7-7 7 7" />, gold: <path d="M4 18h16l-3-6H7zM8 12l2-5h4l2 5" />, home: <path d="M3 11l9-7 9 7M5 10v10h14V10" />,
  loan: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18" /></>, shield: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />,
  coin: <path d="M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM9 9h4.5a2 2 0 010 4H9h5a2 2 0 010 4H9M11 7v12" />,
  // one picture per kind, so no two tiles look the same
  rd: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4M8 14h2M12 14h2M16 14h0" /></>,
  ppf: <path d="M5 20V10l7-6 7 6v10zM9 20v-5h6v5M12 8v3" />,
  nps: <path d="M4 19l5-6 4 3 7-9M15 7h5v5" />,
  bond: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
  other: <path d="M6 12h.01M12 12h.01M18 12h.01M4 6h16v12H4z" />,
};
const TILES: TileGroup[] = [
  { title: "Cash and deposits", tiles: [
    { value: "cash", title: "Savings and cash", sub: "Bank balances", icon: ic.cash }, { value: "fd", title: "Fixed deposit", sub: "Works out today's value", icon: ic.fd },
    { value: "rd", title: "Recurring deposit", sub: "Monthly instalments", icon: ic.rd }] },
  { title: "Retirement", tiles: [
    { value: "epf", title: "EPF", sub: "From your passbook", icon: ic.ret }, { value: "ppf", title: "PPF", sub: "Yearly deposits", icon: ic.ppf }, { value: "nps", title: "NPS", sub: "Tier I and II", icon: ic.nps }] },
  { title: "Gold, property and other", tiles: [
    { value: "gold", title: "Gold", sub: "Grams or value", icon: ic.gold }, { value: "sgb", title: "Sovereign gold bond", sub: "Units in grams", icon: ic.bond },
    { value: "property", title: "Property", sub: "Your estimate", icon: ic.home }, { value: "crypto", title: "Crypto", sub: "Coins held", icon: ic.coin }, { value: "other", title: "Other asset", sub: "Anything else", icon: ic.other }] },
  { title: "What you owe and cover", tiles: [
    { value: "loan", title: "Loan or card", sub: "Balance left", icon: ic.loan }, { value: "policy", title: "Insurance policy", sub: "Cover and premium", icon: ic.shield }] },
];

/** The kinds most people add, as one-tap chips under the totals (MO-2); every other kind is behind "Something else". */
const QUICK: Kind[] = ["cash", "fd", "epf", "ppf", "gold", "property", "loan"];

function blank(kind: Kind): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of FORM[kind].fields) out[f.k] = f.type === "select" ? f.options![0][0] : "";
  return out;
}
/** What a new entry starts with: the first option of each list, and today as the start of a deposit. */
function fresh(kind: Kind): Record<string, string> {
  const out = blank(kind);
  if (kind === "fd" || kind === "rd") out.start = today();
  return out;
}

/** The form as the server takes it: numbers as numbers, empty fields left out. */
function body(kind: Kind, form: Record<string, string>) {
  const out: Record<string, string | number> = { kind };
  for (const f of FORM[kind].fields) {
    const v = (form[f.k] ?? "").trim();
    if (!v || (f.floating && !isFloating(form))) continue;
    const whole = f.k === "purity" || f.k === "reset_months";
    if (f.type === "money" || f.type === "rate" || f.type === "num" || f.type === "int" || (f.type === "select" && whole)) {
      const n = Number(v.replace(/,/g, ""));
      if (!Number.isFinite(n)) throw new Error(`${f.label}: enter a number.`);
      out[f.k] = f.type === "int" || whole ? Math.round(n) : n;
    } else out[f.k] = v;
  }
  return out;
}

/** The limits the server keeps for each kind of box (ItemReq in money_networth.py), checked here first so a problem is
 * said under its box with the limit named. */
const SMALL_MONEY = ["monthly", "yearly", "premium", "paid_since"];
const SMALL_NUM = ["grams", "price_per_g", "units", "issue_price"];
function limitsFor(f: F): Limits | null {
  const optional = !!f.optional;
  if (f.k === "purity") return { min: 1, max: 24, whole: true, optional };
  if (f.k === "tenure_months") return { min: 0, max: 600, whole: true, optional };
  if (f.k === "spread") return { min: -10, max: 30, optional, unit: "%" };
  // DP2-005: a required amount of 0 is no entry (a "0" took one of Free's five places)
  if (f.type === "money") return { min: 0, above: !optional, max: SMALL_MONEY.includes(f.k) ? 1e10 : SMALL_NUM.includes(f.k) ? 1e7 : 1e12, optional, unit: "₹" };
  if (f.type === "rate") return { min: 0, max: 60, optional, unit: "%" };
  if (f.type === "int") return { min: 0, whole: true, optional };
  if (f.type === "num") return { min: 0, max: SMALL_NUM.includes(f.k) ? 1e7 : 1e12, optional };
  return null;
}

/** Each box's problem, or none: numbers against their limits, and the boxes a kind needs filled in. */
function formProblems(kind: Kind, form: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of FORM[kind].fields) {
    if (f.floating && !isFloating(form)) continue;
    const v = form[f.k] ?? "";
    const lim = limitsFor(f);
    const p = lim ? numberProblem(v, lim) : !f.optional && f.type !== "select" && !v.trim() ? "Fill this in." : null;
    if (p) out[f.k] = p;
  }
  // DG-014: dates in the wrong order are said under the maturity date, not in a toast that goes in seconds
  if (form.start && form.maturity && (kind === "fd" || kind === "rd" || kind === "sgb") && form.maturity <= form.start && !out.maturity) {
    out.maturity = "The maturity date has to be after the start date.";
  }
  return out;
}

function EntryForm({ kind, start, busy, onSave, onCancel, onRemove, saveLabel, serverErrors }: { kind: Kind; start: Record<string, string>; busy: boolean; saveLabel: string;
  onSave: (b: Record<string, string | number>) => void; onCancel?: () => void; onRemove?: () => void; serverErrors?: Record<string, string> | null }) {
  const { notify } = useApp();
  const [form, setForm] = useState(start);
  const [errs, setErrs] = useState<Record<string, string>>({});
  useEffect(() => { setForm(start); setErrs({}); }, [start]);
  useEffect(() => { if (serverErrors) setErrs(serverErrors); }, [serverErrors]);     // the server's own checks, under their boxes
  const spec = FORM[kind];
  const submit = () => {
    const p = formProblems(kind, form);
    setErrs(p);
    if (Object.keys(p).length) return;
    try { onSave(body(kind, form)); } catch (e) { notify((e as Error).message); }
  };
  const set = (k: string) => (v: string) => {
    setForm((x) => ({ ...x, [k]: v }));
    const f = spec.fields.find((x) => x.k === k);
    const lim = f && limitsFor(f);
    // a number is checked as it's typed (an empty box only on Add, so the form doesn't start out red)
    setErrs((e) => { const n = { ...e }; const p = lim && v.trim() ? numberProblem(v, lim) : null; if (p) n[k] = p; else delete n[k]; return n; });
  };
  return (
    <FormGrid label={spec.title} onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {spec.fields.filter((f) => !f.floating || isFloating(form)).map((f) => {
        const unit = f.unit ?? (f.type === "money" ? "₹" : f.type === "rate" ? "% / yr" : undefined);
        if (f.type === "select") {
          return <Field key={f.k} label={f.label} info={f.info}>{(id) => <Select id={id} value={form[f.k] ?? ""} onChange={set(f.k)} options={f.options!.map(([value, label]) => ({ value, label }))} />}</Field>;
        }
        if (f.type === "date") return <DateField key={f.k} label={f.label} optional={f.optional} info={f.info} value={form[f.k] ?? ""} onChange={set(f.k)} error={errs[f.k]} />;
        return <Field key={f.k} label={f.label} optional={f.optional} unit={f.type === "text" ? undefined : unit} info={f.info}
          value={form[f.k] ?? ""} type="text" inputMode={f.type === "text" ? undefined : "decimal"} error={errs[f.k]}
          placeholder={f.hint ?? (f.type === "money" ? "1,00,000" : f.type === "rate" ? "7" : "")} maxLength={f.type === "text" ? 60 : undefined}
          onChange={(e) => set(f.k)(e.target.value)} />;
      })}
      {spec.note && <p className="k-note k-field wide">{spec.note}</p>}
      <FormActions>
        <button type="submit" className="btn" disabled={busy}>{saveLabel}</button>
        {onCancel && <button type="button" className="btn quiet" onClick={onCancel}>Cancel</button>}
        {onRemove && <button type="button" className="btn danger" disabled={busy} onClick={onRemove}><Trash size={16} />Remove this entry</button>}
      </FormActions>
    </FormGrid>
  );
}

/** One line of figures under an entry: maturity, interest, EMIs, as the server worked them out. */
function Facts({ r, tax }: { r: Row; tax?: DepositTax | null }) {
  const f = r.facts || {};
  const bits: string[] = [];
  if (f.maturity) bits.push(`${f.matured ? "Matured" : "Matures"} ${day(f.maturity)}${f.maturity_value != null ? `: ${inr(f.maturity_value)}` : ""}`);
  if (f.interest_so_far != null && r.kind !== "loan") bits.push(`interest so far ${inr(f.interest_so_far)}`);
  if (f.year_end != null) bits.push(`${f.year_end_label}: ${inr(f.year_end)} projected`);
  if (f.paid_in != null) bits.push(`paid in ${inr(f.paid_in)}`);
  if (f.yearly_interest != null) bits.push(`interest ${inr(f.yearly_interest)} a year`);
  if (f.next_interest) bits.push(`next interest ${day(f.next_interest)}`);
  const d = tax?.items?.[r.id];
  if (d) bits.push(`interest to maturity ${inr(d.interest)}, ${inr(d.interest_after_tax)} after tax at ${tax!.tax_rate}%${tax!.basis === "estimate" ? " (your estimate)" : ""}`);
  if (!bits.length) return null;
  return <span className="k-sub-line">{bits.join(" · ")}</span>;
}

/** A loan's rate: the sanctioned one, and today's after a floating rate's resets when it differs (DG-011). */
function loanRate(r: Row): string {
  const sanctioned = Number(r.entry?.rate), now = r.facts?.rate_now;
  return now != null && Number.isFinite(sanctioned) && Math.abs(now - sanctioned) > 1e-9 ? `${now}% a year now (${sanctioned}% at the start)` : `${r.entry?.rate}% a year`;
}

function PrepayBox({ loan, onClose }: { loan: Row; onClose: () => void }) {
  const { fail } = useApp();
  const [amount, setAmount] = useState("");
  const [got, setGot] = useState<Prepay | null>(null);
  const [busy, setBusy] = useState(false);
  const work = async () => {
    const n = Number(amount.replace(/,/g, ""));
    if (!(n > 0)) return;
    setBusy(true);
    try { setGot(await api<Prepay>("/money/net-worth/prepay", { method: "POST", body: { id: loan.id, amount: n } })); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Prepay: ${loan.name}`} onClose={onClose}>
      <div className="k-stack">
        <p className="k-small k-muted">Owed today {inr(loan.value)} at {loanRate(loan)}, EMI {inr(loan.facts.emi)}, {loan.facts.left} EMIs left.</p>
        <FormGrid onSubmit={(e) => { e.preventDefault(); void work(); }}>
          <Field label="Prepay" unit="₹" inputMode="decimal" placeholder="1,00,000" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <FormActions><button type="submit" className="btn" disabled={busy}>Work it out</button></FormActions>
        </FormGrid>
        {got && (got.closes
          ? <p className="k-small" role="status">Prepaying {inr(got.amount)} repays the loan. Interest no longer paid: <b>{inr(got.interest_saved)}</b>.</p>
          : (
            <div className="k-stack" role="status">
              {got.tenure && <p className="k-small"><b>Same EMI, shorter loan:</b> {got.tenure.months_saved} fewer EMIs ({got.tenure.months_left} left, the last on {day(got.tenure.ends)}); interest saved {inr(got.tenure.interest_saved)}.</p>}
              {got.lower_emi && <p className="k-small"><b>Same end date, smaller EMI:</b> {inr(got.lower_emi.emi)} a month ({inr(Math.abs(got.lower_emi.emi_change))} less); interest saved {inr(got.lower_emi.interest_saved)}.</p>}
              <p className="k-note">{got.note}</p>
            </div>
          ))}
      </div>
    </Modal>
  );
}

export function NetWorthPage() {
  const { fail, notify, me } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("cash");
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<{ id: string; kind: Kind; form: Record<string, string> } | null>(null);
  const [prepay, setPrepay] = useState<Row | null>(null);
  const [addStart, setAddStart] = useState(() => fresh("cash"));
  const [ask, setAsk] = useState<Ask | null>(null);
  const [adding, setAdding] = useState(false);
  const [step, setStep] = useState<"pick" | "form">("pick");
  const [fieldErrs, setFieldErrs] = useState<Record<string, string> | null>(null);
  const readSeq = useRef(0);                       // one more with every full reading, so a price update begun before it is dropped
  const load = useCallback(() => {
    setError(null);
    readSeq.current++;
    return api<View>("/money/net-worth").then(setView).catch((e) => { setError(e instanceof Error ? e.message : "Your net worth couldn't be read."); fail(e); });
  }, [fail]);
  useEffect(() => { load(); }, [load]);
  // the values at market prices again each minute while the market behind one of them trades (LIVE-1): only the totals and rows are
  // read, the history, the deposits' tax and the uploads are not, and an edit's answer that lands first is never overwritten
  useMarketRefresh(pricedMarkets(view?.assets), () => {
    const n = readSeq.current;
    api<Partial<View>>("/money/net-worth?live=true").then((x) => { if (n === readSeq.current) setView((cur) => (cur ? mergeLiveNetWorth(cur, x) : cur)); }).catch(() => undefined);
  }, !!view && !busy);

  const send = async (path: string, method: string, b?: object, done?: string) => {
    setBusy(true);
    setFieldErrs(null);
    try {
      const got = await api<View>(path, { method, body: b });
      readSeq.current++;
      setView(got);
      if (done) notify(done);
      return true;
    } catch (e) {
      const f = (e as ApiError).fields;
      if (f && Object.keys(f).length) setFieldErrs(f);      // said under the boxes they belong to
      else fail(e);
      return false;
    } finally { setBusy(false); }
  };
  const addOne = async (b: Record<string, string | number>) => {
    if (await send("/money/net-worth/items", "POST", b, `${FORM[kind].title} added.`)) {
      track("net worth entry added", { kind });
      setAddStart(fresh(kind));
      setAdding(false); setStep("pick");
    }
  };
  // straight to a kind's boxes (the quick-add chips), or to the picker of every kind
  const openAdd = (k?: Kind) => {
    if (k) { setKind(k); setAddStart(fresh(k)); setStep("form"); } else setStep("pick");
    setFieldErrs(null); setAdding(true);
  };
  const startEdit = (e: Entry) => {
    const k = e.kind;
    const form = blank(k);
    for (const f of FORM[k].fields) if (e[f.k] != null) form[f.k] = String(e[f.k]);
    setEdit({ id: e.id, kind: k, form });
  };
  const askRemove = (id: string, name: string, then?: () => void) => setAsk({
    title: `Remove ${name}?`, // R62-005: earlier days' snapshots keep the entry, so the dialog says so instead of promising the history changes
    body: "It is taken out of your net worth from today. Earlier days in the history chart keep it until you remove that day's snapshot below the chart. Your other entries stay.", label: "Remove this entry",
    run: async () => { if (await send(`/money/net-worth/items/${id}`, "DELETE", undefined, "Removed.")) then?.(); },
  });
  const download = async () => {
    try {
      const r = await api<Response>("/money/net-worth/export", { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-net-worth-${istToday()}.csv`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); }
  };
  // one snapshot out of the history (R7O-013: a test's holdings left a snapshot that only "Delete my net worth data"
  // could clear); the entries and the other days stay
  const askRemoveSnapshot = (d: string) => setAsk({
    title: `Remove the snapshot of ${dateOnly(d)}?`, body: "Only that day's net worth leaves the history chart. Your entries and the other days stay.",
    label: "Remove this snapshot",
    run: async () => { await api(`/money/net-worth/history/${encodeURIComponent(d)}`, { method: "DELETE" }); await load(); notify("Snapshot removed."); },
  });
  const removeAll = () => setAsk({
    title: "Delete my net worth data?", body: "Every entry, loan, policy and the history is removed from StratLab. My Holdings isn't touched.", label: "Delete my net worth data",
    run: async () => { await api("/money/net-worth", { method: "DELETE" }); await load(); notify("Your net worth data is deleted."); },
  });
  const confirm = async () => {
    if (!ask) return;
    setBusy(true);
    try { await ask.run(); } catch (e) { fail(e); } finally { setBusy(false); setAsk(null); }
  };

  const t = view?.totals;
  const empty = view && !view.assets.length && !view.liabilities.length && !view.insurance.policies.length;
  const hist = useMemo(() => view?.history ?? [], [view?.history]);
  const full = view?.limit != null && view.count >= view.limit;

  // the history's range: the app's one range control, only the stretches the snapshots cover (O4)
  const days = useMemo(() => hist.map((h) => h.d), [hist]);
  const rng = useRange("networth", days);
  // every snapshot is drawn; a partial one (something wasn't counted) is marked, so a dip it shows isn't read as a fall
  const whole = hist;
  const shown = whole.slice(rng.from);
  const marked = shown.flatMap((h, i) => (h.partial?.length ? [{ i, kind: "dot" as const, color: "var(--orange)" }] : []));
  const last = hist[hist.length - 1], move = t ? netWorthDelta(t.net, t.partial, hist, undefined, view?.valuation) : null;

  // VR1-143: when every asset is as of the same day it is said once, in the card's head, not under each of ten values
  const oneDay = !!view && view.assets.length > 1 && new Set(view.assets.map((r) => r.as_of)).size === 1;
  const assetCols: Column<Row>[] = [
    { key: "asset", header: "Asset, and how it's worked out", rowHeader: true, wrap: true, cell: (r) => (
      <>
        {/* VR6-015: "My Holdings: Indian stocks · Indian stocks": the kind is not said again when the name ends with it */}
        <b>{r.name}</b>{!r.name.endsWith(r.label) && <span className="k-note"> · {r.label}</span>}{r.basis === "as entered" && <span className="k-note"> · as entered</span>}
        <span className="k-sub-line">{r.rule}</span><Facts r={r} tax={view?.deposit_tax} />
      </>) },
    { key: "value", header: "Value", numeric: true, cell: (r) => <>{r.value == null ? "–" : inr(r.value)}{!oneDay && <span className="k-sub-line">as of {day(r.as_of)}</span>}</> },
    { key: "act", header: "", action: true, cell: (r) => (r.entry ? (
      <span className="k-row">
        <button type="button" className="btn quiet sm" onClick={() => startEdit(r.entry!)} aria-label={`Edit ${r.name}`}>Edit</button>
        <button type="button" className="btn quiet sm" onClick={() => askRemove(r.entry!.id, r.name)} aria-label={`Remove ${r.name}`}><Trash size={14} /></button>
      </span>
    ) : r.linked ? <Link className="btn quiet sm" to={r.linked}>Open</Link> : null) },
  ];
  const loanCols: Column<Row>[] = [
    // DG-011: a floating loan's rate after its resets, beside the sanctioned one
    { key: "loan", header: "Loan", rowHeader: true, cell: (r) => <><b>{r.name}</b><span className="k-sub-line">{loanRate(r)}{r.basis === "as entered" ? " · as entered" : ""}</span></> },
    { key: "owed", header: "Owed today", numeric: true, cell: (r) => inr(r.value) },
    { key: "emi", header: "EMI", numeric: true, cell: (r) => (r.facts.emi != null ? inr(r.facts.emi) : "–") },
    { key: "int", header: "Interest this FY", numeric: true, cell: (r) => (r.facts.interest_fy != null ? inr(r.facts.interest_fy) : "–") },
    // TABLE-SWEEP: the EMIs left under the end date, one column, so the row's three buttons stay on the card at 1280
    { key: "ends", header: "Ends", numeric: true, cell: (r) => <>{r.facts.ends ? day(r.facts.ends) : "–"}{r.facts.left != null && <span className="k-sub-line">{r.facts.left} EMI{r.facts.left === 1 ? "" : "s"} left</span>}</> },
    { key: "act", header: "", action: true, cell: (r) => (
      <span className="k-row">
        {r.facts.left ? <button type="button" className="btn quiet sm" onClick={() => setPrepay(r)} aria-label={`Prepay ${r.name}`}>Prepay</button> : null}
        <button type="button" className="btn quiet sm" onClick={() => startEdit(r.entry!)} aria-label={`Edit ${r.name}`}>Edit</button>
        <button type="button" className="btn quiet sm" onClick={() => askRemove(r.entry!.id, r.name)} aria-label={`Remove ${r.name}`}><Trash size={14} /></button>
      </span>) },
  ];
  const policyCols: Column<Policy>[] = [
    { key: "policy", header: "Policy", rowHeader: true, cell: (p) => <><b>{p.name}</b><span className="k-sub-line">{p.label} · {p.insurer}</span></> },
    { key: "sum", header: "Sum assured", numeric: true, cell: (p) => inr(p.sum_assured) },
    { key: "prem", header: "Premium", numeric: true, cell: (p) => <>{inr(p.premium)}<span className="k-sub-line">{p.frequency === "single" ? "once" : p.frequency}</span></> },
    // TABLE-SWEEP: the Next due column only when a policy has a due date (a column of dashes said nothing)
    ...(view?.insurance.policies.some((p) => p.next_due) ? [{ key: "due", header: "Next due", numeric: true, cell: (p: Policy) => (p.next_due ? <>{day(p.next_due)}<span className="k-sub-line">{p.due_in === 0 ? "due today" : `due in ${p.due_in} day${p.due_in === 1 ? "" : "s"}`}</span></> : "–") } as Column<Policy>] : []),
    { key: "nom", header: "Nominee", cell: (p) => p.nominee || <span className="k-muted">Not entered</span> },
    { key: "act", header: "", action: true, cell: (p) => (
      <span className="k-row">
        <button type="button" className="btn quiet sm" onClick={() => startEdit(p.entry)} aria-label={`Edit ${p.name}`}>Edit</button>
        <button type="button" className="btn quiet sm" onClick={() => askRemove(p.id, p.name)} aria-label={`Remove ${p.name}`}><Trash size={14} /></button>
      </span>) },
  ];

  // the history's snapshots, each removable: under the chart when there is one (DP2-006)
  const snapsList = (cls: string) => (
    <details className={cls} data-testid="nw-snapshots" open={empty || undefined}>
      {/* VR1-142: a plain "History: 3 snapshots", not "The history's snapshots (3): remove one"; each row's date and figure, its notes smaller under it, an icon to remove */}
      <summary className="k-small">History: {hist.length} snapshot{hist.length === 1 ? "" : "s"}</summary>
      <DataTable label="The history's snapshots" rows={[...hist].reverse()} rowKey={(h) => h.d} columns={[
        { key: "d", header: "Date", rowHeader: true, cell: (h) => <b>{dateOnly(h.d)}</b> },
        { key: "n", header: "Net worth", numeric: true, cell: (h) => inr(h.net) },
        { key: "w", header: "How it was taken", wrap: true, cell: (h) => <span className="k-note">{[h.why === "change" ? "taken when an entry changed" : h.why === "month" ? "monthly" : "", h.added ? `${signedInrCompact(h.added)} from entries added or changed` : "", h.partial?.length ? `partial (not counted: ${h.partial.join("; ")})` : ""].filter(Boolean).join(" · ")}</span> },
        { key: "x", header: "", action: true, cell: (h) => (
          <button type="button" className="btn quiet sm" onClick={() => askRemoveSnapshot(h.d)} aria-label={`Remove the snapshot of ${dateOnly(h.d)}`} title="Remove this snapshot"><Trash size={14} /></button>) },
      ]} />
    </details>
  );
  // "Prices as of" only over market prices: with none on the page the server dates it today, and "Prices as of 19 Oct" stood
  // before that day's open (R60-008)
  const priced = !!view?.assets.some((r) => r.basis === "market price" && r.value);
  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Portfolio" title="Net worth" asOf={priced ? view?.as_of : undefined} asOfLabel="Prices as of"
        lede="What you own minus what you owe: your stocks from My Holdings and mutual funds from your statement (both added on their own), plus the deposits, provident funds, gold, property and loans you add here."
        info="Each value shows how it's worked out and the date it's as of. Arithmetic on what you enter, not advice. Only you can see it, and you can delete it at any time." infoLabel="How this is worked out"
        // MO-2 (owner, 25 Oct): adding is the page's main action, so a full-size button at the top, not a small one in a card
        actions={view ? <button type="button" className="btn" onClick={() => openAdd()}><Plus size={16} />Add an entry</button> : undefined} />

      {!view && (error
        ? <ErrorState title="Your net worth couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>{error}</ErrorState>
        : <Card><Skeleton label="Adding up your net worth" /></Card>)}
      {view && t && (
        <>
          <Card label="Totals">
            <CardHead title="Where you stand" info={t.oldest_as_of ? `The oldest value you entered is as of ${day(t.oldest_as_of)}.` : undefined} />
            {/* with no loans the assets are the net worth: the same figure said again is left out (LIVE1C-056: ₹20,33,027 five times) */}
            {/* TABLE-SWEEP: a named first column and right-aligned figures; the Change column only when there is a change or a restated note to show */}
            <FactTable label="Where you stand" itemHead="Total" figureHead="Now" noteHead="Change" numeric rows={[
              { id: "net", k: "Net worth", v: <b>{inr(t.net)}</b>, n: move ? <><Delta value={move.change}>{signedInrCompact(move.change)}</Delta> {sinceNote(move, day, inrCompact)}</> : restatedNote(hist, view?.valuation, day) ?? undefined },
              ...(t.liabilities > 0 ? [{ id: "assets", k: "Assets", v: inr(t.assets) }, { id: "loans", k: "Loans", v: inr(t.liabilities) }] : []),
            ]} />
            {/* a source that couldn't be read or valued: named; snapshots of such a total are marked partial */}
            {/* DG-016: something with no price yet is a routine note; a source that couldn't be read is the warning */}
            {t.partial && t.partial.length > 0 && <Notice tone={t.partial_lasting ? "info" : "warn"} role="status" label="Partial total">Not in this total: {t.partial.join("; ")}. {t.partial_lasting ? "The history goes on meanwhile, with each snapshot marked partial." : "Only the monthly snapshot is kept meanwhile, marked partial."}</Notice>}
            {t.notes && t.notes.length > 0 && <Notes testId="nw-notes" items={t.notes} />}
            {/* what the plan includes, said where the numbers are: the menu has no lock on this page, it is free in the main */}
            {view.limit != null && <p className="k-note">{view.count} of {view.limit} free entries used. Basic keeps as many as you like, with the monthly history.</p>}
            {/* the history has a card once there is a chart to draw; until then, one line here says when it starts */}
            {!view.history_allowed
              ? <PlanNote>The net worth history is on the Basic plan{view.history_count ? ` (${view.history_count} snapshot${view.history_count === 1 ? "" : "s"} recorded so far)` : ""}.</PlanNote>
              : hist.length < 3 && !empty && <p className="k-note">A snapshot is taken on the 1st of each month and whenever you change an entry; the chart starts at the third{hist.length > 0 ? ` (${hist.length === 1 ? `the first is from ${day(hist[0].d)}` : `${hist.length} so far, the latest from ${day(hist[hist.length - 1].d)}`})` : ""}.</p>}
            {/* VR6-012: with no chart yet the snapshots list sits in this card under that line, not in a card of its own with one line in it (DP2-006's "empty-looking card" was still 97px of it) */}
            {view.history_allowed && hist.length > 0 && whole.length < 3 && snapsList("nw-snaps")}
          </Card>

          {/* MO-2 (owner, 25 Oct): one tap to the usual kinds, so adding a deposit, EPF, gold or a loan is never hunted for */}
          {!empty && !full && (
            <Card compact label="Add to your net worth">
              {/* VR1-141: the usual kinds as one strip beside the header's button, not a 140px card of its own with a repeated title */}
              <span className="k-eyebrow">Quick add</span>
              <div className="chip-row nw-quick" role="group" aria-label="Add to your net worth">
                {QUICK.map((k) => <button key={k} type="button" className="chip" onClick={() => openAdd(k)}><Plus size={14} />{FORM[k].title}</button>)}
                <button type="button" className="chip" onClick={() => openAdd()}>Something else…</button>
              </div>
            </Card>
          )}

          {empty && (
            <EmptyState title="Nothing added yet" action={{ label: "Add an entry", onClick: () => openAdd() }}>
              Add your savings, deposits, EPF or a loan. Stocks in <Link className="link" to="/holdings">My Holdings</Link> are added to the total on their own once you have some there.
            </EmptyState>
          )}
          {/* the history can hold a snapshot from entries since removed (R7M-012: ₹2,43,481.78 on 8 Oct beside "Nothing added yet"):
              it is said, and can be removed below, so it doesn't reappear in the chart when the next entry is added */}
          {empty && view.history_allowed && hist.length > 0 && (
            <Notice tone="warn" role="status" label="Kept history">
              The history still holds {hist.length === 1 ? "a snapshot" : `${hist.length} snapshots`} from earlier entries (latest {inr(hist[hist.length - 1].net)} on {day(hist[hist.length - 1].d)}), though nothing is entered now.
              {hist.length === 1 ? " It" : " They"} will show in the chart again once you add an entry; remove {hist.length === 1 ? "it" : "them"} below if {hist.length === 1 ? "it isn't" : "they aren't"} yours.
            </Notice>
          )}

          {/* a single class is a bar at 100% that says nothing the table does not (LIVE1C-056) */}
          {view.allocation.length > 1 && (
            <Card>
              <CardHead title="By asset class" />
              {/* TABLE-SWEEP: a table of the classes, their amount and their share, with the total under them (it was a list of bars) */}
              <ShareTable label="Assets by class" head="Asset class" footnote="Share of total assets, before loans."
                rows={view.allocation.map((a) => ({ key: a.class, name: a.label, value: inr(a.value), pct: a.pct }))}
                total={{ name: "All assets", value: inr(view.totals.assets), pct: 100 }} />
            </Card>
          )}

          {view.history_allowed && whole.length >= 3 && (
            <ChartFrame title="History" info="Net worth at each snapshot: the 1st of each month and the days you changed an entry." ranges={rng.options} range={rng.value} onRange={rng.pick} rangeFor={{ chart: "networth", times: days }}
              footer={<><p className="k-note">Last snapshot {day(last.d)}.{marked.length > 0 && " Marked points are partial: something wasn't counted that day (named in the snapshots below)."}</p>{snapsList("nw-snaps")}</>}
              table={{ label: "Net worth at each snapshot", rows: [...shown].reverse(), rowKey: (h) => h.d,
                columns: [{ key: "d", header: "Day", rowHeader: true, cell: (h) => dateOnly(h.d) }, { key: "net", header: "Net worth", numeric: true, cell: (h) => <>{inr(h.net)}{h.partial?.length ? <span className="k-sub-line">partial</span> : null}</> },
                  { key: "a", header: "Assets", numeric: true, cell: (h) => inr(h.assets) }, { key: "l", header: "Loans", numeric: true, cell: (h) => inr(h.liabilities) }] }}>
              <XYChart series={[{ values: shown.map((h) => h.net), color: "var(--series-1)", label: "Net worth", area: { color: "var(--series-1)", base: 0 } }]}
                times={shown.map((h) => h.d)} points={marked} format={(v) => inr(v)} axisFormat={(v) => axisInr(v)} ariaLabel="Net worth over time" height={220} testId="networth-chart" ranges={false} table={false} />
            </ChartFrame>
          )}

          {view.assets.length > 0 && (
            <Card>
              <CardHead title="Assets" actions={oneDay ? <span className="k-note">All as of {day(view.assets[0].as_of)}</span> : undefined} />
              <DataTable label="Assets" columns={assetCols} rows={view.assets} rowKey={(r) => r.id} stack />
              {view.gold_price && <p className="k-note">Gold at {inr(view.gold_price.per_g)} a gram (24 carat), from the front-month gold future on the commodity exchange, as of {day(view.gold_price.as_of)}.</p>}
            </Card>
          )}

          {view.liabilities.length > 0 && (
            <Card>
              <CardHead title="Loans" info={`Balances owed as of ${day(view.as_of)}, worked out from the amount, rate, tenure and start date you entered (reducing balance, monthly EMIs). Your lender's statement is the final word.`} />
              <DataTable label="Loans" columns={loanCols} rows={view.liabilities} rowKey={(r) => r.id} stack />
            </Card>
          )}

          {view.liabilities.length > 0 && <LoanCheck version={`${view.count}|${view.liabilities.map((l) => JSON.stringify(l.entry)).join("|")}`} />}

          {view.insurance.policies.length > 0 && (
            <Card>
              <CardHead title="Insurance policies" info="A due date that has passed moves on by the payment period. Policies aren't counted in net worth."
                actions={<span className="k-small">Premiums a year: <b>{inr(view.insurance.yearly_premium)}</b></span>} />
              <DataTable label="Insurance policies" columns={policyCols} rows={view.insurance.policies} rowKey={(p) => p.id} stack />
            </Card>
          )}


          <section className="k-stack">
            {/* TABLE-SWEEP: the qualifiers as numbered notes, not one long paragraph */}
            <Notes label="How the values are worked out" items={[
              <>Rates used unless you enter your own: EPF {view.rates.epf_note}; PPF {view.rates.ppf_note}; sovereign gold bonds {view.rates.sgb}% a year on the issue price.</>,
              "Deposits use the bank's usual method: whole periods compounded, simple interest on the days after.",
              "Values are before tax. Property and anything marked \"as entered\" is your own figure.",
              "Your entries are stored with your account only and never shared.",
            ]} />
            <div className="k-row">
              {!empty && <button type="button" className="btn quiet" onClick={download}><Download size={16} />Download CSV</button>}
              {!empty && <button type="button" className="btn danger" onClick={removeAll}><Trash size={16} />Delete my net worth data</button>}
            </div>
          </section>
        </>
      )}

      {/* adding: pick what it is, then its few boxes, in one pop-up (the page stays where it was) */}
      {adding && view && (
        <Modal title={step === "form" ? `Add: ${FORM[kind].title}` : "Add to your net worth"} onClose={() => { setAdding(false); setStep("pick"); }} wide>
          <div className="k-stack">
            {/* LIVE1B-073: at the limit the note below says it (and the page behind it says the count): not three times in one dialog */}
            {view.limit != null && !full && <span className="k-note">{view.count} of {view.limit} entries on your plan · <Link className="link" to="/plans">more with Basic</Link></span>}
            {/* the one lock wording (DP2-022): the plan and its count, then what Basic gives; the note adds the price */}
            {full ? <PlanNote plan="basic">Your {me?.plan_info.name ?? "Free"} plan keeps {view.limit} entries. Delete one to add another. Basic has no limit on entries, and adds the monthly history chart.</PlanNote>
              : step === "pick" ? <TilePicker label="What is it?" groups={TILES} value={kind} onChange={(k) => { setKind(k as Kind); setAddStart(fresh(k as Kind)); setStep("form"); setFieldErrs(null); }} />
              : <>
                <button type="button" className="btn quiet sm k-btn-end" onClick={() => setStep("pick")}>← Back</button>
                <EntryForm key={kind} kind={kind} start={addStart} busy={busy} saveLabel="Add" onSave={addOne} serverErrors={fieldErrs} onCancel={() => { setAdding(false); setStep("pick"); }} />
              </>}
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={`Edit: ${FORM[edit.kind].title}`} onClose={() => setEdit(null)} wide>
          <EntryForm kind={edit.kind} start={edit.form} busy={busy} saveLabel="Save" serverErrors={fieldErrs}
            onSave={async (b) => { if (await send(`/money/net-worth/items/${edit.id}`, "PUT", b, "Saved.")) setEdit(null); }} onCancel={() => setEdit(null)}
            onRemove={() => { const id = edit.id, name = String(edit.form.name || FORM[edit.kind].title); setEdit(null); askRemove(id, name); }} />
        </Modal>
      )}
      {prepay && <PrepayBox loan={prepay} onClose={() => setPrepay(null)} />}
      {ask && <ConfirmDialog title={ask.title} confirmLabel={ask.label} busy={busy} onConfirm={() => void confirm()} onClose={() => setAsk(null)}>{ask.body}</ConfirmDialog>}
    </div>
  );
}
