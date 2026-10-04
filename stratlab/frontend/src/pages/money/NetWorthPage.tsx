import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf, money } from "../../lib/format";
import { AsOf, Empty, Loading, Modal } from "../../components/ui";
import { ChartEmpty, XYChart } from "../../components/Charts";
import { Download, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { moneyCompact } from "../../lib/chartFormat";

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
type View = {
  as_of: string; computed_at: string; totals: { assets: number; liabilities: number; net: number; oldest_as_of: string | null };
  allocation: { class: string; label: string; value: number; pct: number | null }[]; assets: Row[]; liabilities: Row[];
  insurance: { policies: Policy[]; yearly_premium: number; cover: Record<string, number>; next: string | null };
  gold_price: { per_g: number; as_of: string } | null; rates: { epf: number; epf_note: string; ppf: number; ppf_note: string; sgb: number };
  history: { d: string; net: number; assets: number; liabilities: number; why: string }[] | null; history_allowed: boolean; history_count: number;
  limit: number | null; count: number;
};
type Prepay = {
  outstanding: number; amount: number; closes: boolean; emi: number; months_left: number; interest_left?: number; interest_saved?: number; note: string;
  tenure: { months_left: number; months_saved: number; interest_saved: number; ends: string } | null;
  lower_emi: { emi: number; emi_change: number; interest_saved: number; months_left: number } | null;
};

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const day = (iso: string | null | undefined) => asOf(iso) ?? "–";

type Field = { k: string; label: string; type: "money" | "rate" | "date" | "int" | "num" | "text" | "select"; options?: [string, string][]; optional?: boolean; hint?: string };
const NAME: Field = { k: "name", label: "Name (optional)", type: "text", optional: true };
const AS_OF: Field = { k: "as_of", label: "Value as of", type: "date", optional: true };
/** What each kind of entry asks for. */
const FORM: Record<Kind, { title: string; fields: Field[]; note?: string }> = {
  epf: { title: "EPF", fields: [NAME, { k: "balance", label: "Balance (₹)", type: "money" }, { k: "as_of", label: "Balance as of", type: "date", optional: true },
    { k: "monthly", label: "Monthly contribution, yours and your employer's (₹)", type: "money", optional: true },
    { k: "rate", label: "Interest rate (% a year)", type: "rate", optional: true, hint: "8.25" }],
    note: "Interest is worked out monthly on the running balance and credited on 31 March, at the declared rate unless you enter another." },
  ppf: { title: "PPF", fields: [NAME, { k: "balance", label: "Balance (₹)", type: "money" }, { k: "as_of", label: "Balance as of", type: "date", optional: true },
    { k: "yearly", label: "Yearly deposit (₹)", type: "money", optional: true }, { k: "opened", label: "Account opened on", type: "date", optional: true },
    { k: "rate", label: "Interest rate (% a year)", type: "rate", optional: true, hint: "7.1" }],
    note: "Matures after 15 whole financial years from the end of the year it was opened in." },
  nps: { title: "NPS", fields: [NAME, { k: "tier1", label: "Tier I value (₹)", type: "money" }, { k: "tier2", label: "Tier II value (₹)", type: "money", optional: true }, AS_OF] },
  fd: { title: "Fixed deposit", fields: [NAME, { k: "principal", label: "Amount deposited (₹)", type: "money" }, { k: "rate", label: "Interest rate (% a year)", type: "rate" },
    { k: "compounding", label: "Interest compounds", type: "select", options: [["quarterly", "Every quarter"], ["monthly", "Every month"], ["half-yearly", "Every six months"], ["yearly", "Every year"], ["simple", "Simple interest"]] },
    { k: "start", label: "Start date", type: "date" }, { k: "maturity", label: "Maturity date", type: "date" }] },
  rd: { title: "Recurring deposit", fields: [NAME, { k: "monthly", label: "Monthly instalment (₹)", type: "money" }, { k: "rate", label: "Interest rate (% a year)", type: "rate" },
    { k: "start", label: "First instalment on", type: "date" }, { k: "maturity", label: "Maturity date", type: "date" }], note: "Each instalment compounds every quarter." },
  gold: { title: "Gold", fields: [NAME, { k: "grams", label: "Grams", type: "num", optional: true },
    { k: "purity", label: "Purity", type: "select", options: [["24", "24 carat"], ["22", "22 carat"], ["18", "18 carat"], ["14", "14 carat"]] },
    { k: "price_per_g", label: "Your own price a gram (₹, optional)", type: "money", optional: true },
    { k: "value", label: "Or its value (₹), used when there's no price", type: "money", optional: true }, AS_OF] },
  sgb: { title: "Sovereign gold bond", fields: [NAME, { k: "units", label: "Units (grams)", type: "num" }, { k: "issue_price", label: "Issue price a gram (₹)", type: "money", optional: true },
    { k: "start", label: "Issue date", type: "date", optional: true }, { k: "maturity", label: "Maturity date (8 years after issue if empty)", type: "date", optional: true }],
    note: "Interest of 2.5% a year on the issue price is paid every six months to your bank, so it isn't added to the value." },
  cash: { title: "Savings and cash", fields: [NAME, { k: "value", label: "Amount (₹)", type: "money" }, AS_OF] },
  property: { title: "Property", fields: [NAME, { k: "value", label: "Value (₹), your own estimate", type: "money" }, AS_OF] },
  crypto: { title: "Crypto", fields: [NAME, { k: "coin", label: "Coin (e.g. BTC)", type: "text", optional: true }, { k: "qty", label: "Quantity", type: "num", optional: true },
    { k: "value", label: "Or its value (₹), used when there's no price", type: "money", optional: true }, AS_OF] },
  other: { title: "Other asset", fields: [NAME, { k: "value", label: "Value (₹)", type: "money" }, AS_OF] },
  loan: { title: "Loan or card", fields: [NAME, { k: "loan_type", label: "Kind", type: "select", options: [["home", "Home loan"], ["car", "Car loan"], ["personal", "Personal loan"], ["education", "Education loan"], ["credit_card", "Credit card"], ["other", "Other loan"]] },
    { k: "lender", label: "Lender (optional)", type: "text", optional: true }, { k: "principal", label: "Amount borrowed, or owed on a card (₹)", type: "money" },
    { k: "rate", label: "Interest rate (% a year)", type: "rate" }, { k: "tenure_months", label: "Tenure in months (empty for a card)", type: "int", optional: true },
    { k: "start", label: "Loan start date", type: "date", optional: true }],
    note: "With a tenure, the EMI, the balance owed today and this year's interest are worked out on reducing balance, the first EMI a month after the start." },
  policy: { title: "Insurance policy", fields: [NAME, { k: "policy_type", label: "Kind", type: "select", options: [["term", "Term"], ["health", "Health"], ["life", "Life"], ["vehicle", "Vehicle"], ["other", "Other"]] },
    { k: "insurer", label: "Insurer", type: "text" }, { k: "sum_assured", label: "Sum assured (₹)", type: "money", optional: true }, { k: "premium", label: "Premium (₹)", type: "money" },
    { k: "frequency", label: "Paid", type: "select", options: [["yearly", "Every year"], ["half-yearly", "Every six months"], ["quarterly", "Every quarter"], ["monthly", "Every month"], ["single", "Once"]] },
    { k: "due", label: "Next premium due", type: "date", optional: true }, { k: "nominee", label: "Nominee (optional)", type: "text", optional: true }],
    note: "Policies are listed for their dates and premiums; they aren't counted in net worth." },
};
const KIND_ORDER: Kind[] = ["cash", "fd", "rd", "epf", "ppf", "nps", "gold", "sgb", "property", "crypto", "other", "loan", "policy"];

function blank(kind: Kind): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of FORM[kind].fields) out[f.k] = f.type === "select" ? f.options![0][0] : "";
  return out;
}

/** The form as the server takes it: numbers as numbers, empty fields left out. */
function body(kind: Kind, form: Record<string, string>) {
  const out: Record<string, string | number> = { kind };
  for (const f of FORM[kind].fields) {
    const v = (form[f.k] ?? "").trim();
    if (!v) continue;
    if (f.type === "money" || f.type === "rate" || f.type === "num" || f.type === "int" || (f.type === "select" && f.k === "purity")) {
      const n = Number(v.replace(/,/g, ""));
      if (!Number.isFinite(n)) throw new Error(`${f.label}: enter a number.`);
      out[f.k] = f.type === "int" || f.k === "purity" ? Math.round(n) : n;
    } else out[f.k] = v;
  }
  return out;
}

function EntryForm({ kind, start, busy, onSave, onCancel, saveLabel }: { kind: Kind; start: Record<string, string>; busy: boolean; saveLabel: string;
  onSave: (b: Record<string, string | number>) => void; onCancel?: () => void }) {
  const { notify } = useApp();
  const [form, setForm] = useState(start);
  useEffect(() => setForm(start), [start]);
  const spec = FORM[kind];
  const submit = () => {
    try { onSave(body(kind, form)); } catch (e) { notify((e as Error).message); }
  };
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="nw-form">
        {spec.fields.map((f) => (
          <label key={f.k} className="field">{f.label}
            {f.type === "select"
              ? <select value={form[f.k] ?? ""} onChange={(e) => setForm({ ...form, [f.k]: e.target.value })}>{f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              : <input value={form[f.k] ?? ""} type={f.type === "date" ? "date" : "text"} inputMode={f.type === "text" || f.type === "date" ? undefined : "decimal"}
                  placeholder={f.hint ?? (f.type === "money" ? "1,00,000" : f.type === "rate" ? "7" : "")} maxLength={f.type === "text" ? 60 : undefined}
                  onChange={(e) => setForm({ ...form, [f.k]: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />}
          </label>
        ))}
      </div>
      {spec.note && <p className="tiny muted" style={{ margin: 0 }}>{spec.note}</p>}
      <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
        <button className="btn" disabled={busy} onClick={submit}>{saveLabel}</button>
        {onCancel && <button className="btn quiet" onClick={onCancel}>Cancel</button>}
      </div>
    </div>
  );
}

/** One line of figures under an entry: maturity, interest, EMIs, as the server worked them out. */
function Facts({ r }: { r: Row }) {
  const f = r.facts || {};
  const bits: string[] = [];
  if (f.maturity) bits.push(`${f.matured ? "Matured" : "Matures"} ${day(f.maturity)}${f.maturity_value != null ? `: ${inr(f.maturity_value)}` : ""}`);
  if (f.interest_so_far != null && r.kind !== "loan") bits.push(`interest so far ${inr(f.interest_so_far)}`);
  if (f.year_end != null) bits.push(`${f.year_end_label}: ${inr(f.year_end)} projected`);
  if (f.paid_in != null) bits.push(`paid in ${inr(f.paid_in)}`);
  if (f.yearly_interest != null) bits.push(`interest ${inr(f.yearly_interest)} a year`);
  if (f.next_interest) bits.push(`next interest ${day(f.next_interest)}`);
  if (!bits.length) return null;
  return <div className="tiny muted">{bits.join(" · ")}</div>;
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
      <div className="stack" style={{ gap: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>Owed today {inr(loan.value)} at {loan.entry?.rate}% a year, EMI {inr(loan.facts.emi)}, {loan.facts.left} EMIs left.</p>
        <div className="row" style={{ gap: 10, alignItems: "end", flexWrap: "wrap" }}>
          <label className="field" style={{ flex: "1 1 180px" }}>Prepay (₹)<input value={amount} inputMode="decimal" placeholder="1,00,000" onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") work(); }} /></label>
          <button className="btn" disabled={busy} onClick={work}>Work it out</button>
        </div>
        {got && (got.closes
          ? <p className="small" role="status" style={{ margin: 0 }}>Prepaying {inr(got.amount)} repays the loan. Interest no longer paid: <b>{inr(got.interest_saved)}</b>.</p>
          : (
            <div className="stack" style={{ gap: 8 }} role="status">
              {got.tenure && <p className="small" style={{ margin: 0 }}><b>Same EMI, shorter loan:</b> {got.tenure.months_saved} fewer EMIs ({got.tenure.months_left} left, the last on {day(got.tenure.ends)}); interest saved {inr(got.tenure.interest_saved)}.</p>}
              {got.lower_emi && <p className="small" style={{ margin: 0 }}><b>Same end date, smaller EMI:</b> {inr(got.lower_emi.emi)} a month ({inr(Math.abs(got.lower_emi.emi_change))} less); interest saved {inr(got.lower_emi.interest_saved)}.</p>}
              <p className="tiny muted" style={{ margin: 0 }}>{got.note}</p>
            </div>
          ))}
      </div>
    </Modal>
  );
}

export function NetWorthPage() {
  const { fail, notify } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [kind, setKind] = useState<Kind>("cash");
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<{ id: string; kind: Kind; form: Record<string, string> } | null>(null);
  const [prepay, setPrepay] = useState<Row | null>(null);
  const [addStart, setAddStart] = useState(() => blank("cash"));
  const load = useCallback(() => api<View>("/money/net-worth").then(setView).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);

  const send = async (path: string, method: string, b?: object, done?: string) => {
    setBusy(true);
    try {
      setView(await api<View>(path, { method, body: b }));
      if (done) notify(done);
      return true;
    } catch (e) { fail(e); return false; } finally { setBusy(false); }
  };
  const addOne = async (b: Record<string, string | number>) => {
    if (await send("/money/net-worth/items", "POST", b, `${FORM[kind].title} added.`)) {
      track("net worth entry added", { kind });
      setAddStart(blank(kind));
    }
  };
  const startEdit = (e: Entry) => {
    const k = e.kind;
    const form = blank(k);
    for (const f of FORM[k].fields) if (e[f.k] != null) form[f.k] = String(e[f.k]);
    setEdit({ id: e.id, kind: k, form });
  };
  const download = async () => {
    try {
      const r = await api<Response>("/money/net-worth/export", { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-net-worth-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); }
  };
  const remove = () => {
    if (!confirm("Delete my net worth data? Every entry, loan, policy and the history is removed from StratLab. My Holdings isn't touched.")) return;
    api("/money/net-worth", { method: "DELETE" }).then(load).then(() => notify("Your net worth data is deleted.")).catch(fail);
  };

  const t = view?.totals;
  const empty = view && !view.assets.length && !view.liabilities.length && !view.insurance.policies.length;
  const hist = view?.history ?? [];
  const full = view?.limit != null && view.count >= view.limit;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Net worth</h1>
        <p className="page-sub">What you own minus what you owe: your stocks from My Holdings, plus deposits, provident funds, gold, property and loans you add here. Each value shows how it's worked out and the date it's as of. Arithmetic on what you enter, not advice. Only you can see it, and you can delete it at any time.</p>
      </div>

      {!view && <Loading label="Adding up your net worth" />}
      {view && t && (
        <>
          <div className="stat-row" aria-label="Totals">
            <div className="stat"><span className="tiny muted">Net worth</span><b className="num">{inr(t.net)}</b></div>
            <div className="stat"><span className="tiny muted">Assets</span><b className="num">{inr(t.assets)}</b></div>
            <div className="stat"><span className="tiny muted">Loans</span><b className="num">{inr(t.liabilities)}</b></div>
          </div>
          <AsOf parts={[["Worked out", view.computed_at], ["Oldest value entered", t.oldest_as_of]]} />

          {empty && (
            <Empty title="Nothing added yet">
              <p className="muted">Add your savings, deposits, EPF or a loan below. Stocks in <Link className="link" to="/holdings">My Holdings</Link> are counted on their own.</p>
            </Empty>
          )}

          {view.allocation.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <h2 className="h2">By asset class</h2>
              <div className="stack" style={{ gap: 10 }} role="list" aria-label="Assets by class">
                {view.allocation.map((a) => (
                  <div key={a.class} className="seg-row" role="listitem" title={`${a.label}: ${inr(a.value)} (${a.pct ?? 0}% of assets)`}>
                    <div className="spread small" style={{ gap: 10 }}><span>{a.label}</span><span className="num">{inr(a.value)} <span className="muted">· {a.pct == null ? "–" : `${a.pct.toFixed(1)}%`}</span></span></div>
                    <div className="seg-bar"><i style={{ width: `${Math.max(1, Math.min(100, a.pct ?? 0))}%` }} /></div>
                  </div>
                ))}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>Share of total assets, before loans.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">History</h2>
            {!view.history_allowed ? (
              <div className="banner"><span>The net worth history is on the Basic plan{view.history_count ? ` (${view.history_count} snapshot${view.history_count === 1 ? "" : "s"} recorded so far)` : ""}.</span><Link to="/plans" className="btn sm">See plans</Link></div>
            ) : hist.length < 2 ? (
              <ChartEmpty height={220}>A snapshot is taken on the 1st of each month and whenever you change an entry. The chart starts once there are two.</ChartEmpty>
            ) : (
              <>
                <XYChart series={[{ values: hist.map((h) => h.net), color: "var(--series-1)", label: "Net worth", area: { color: "var(--series-1)", base: Math.min(0, ...hist.map((h) => h.net)) } }]}
                  times={hist.map((h) => h.d)} format={(v) => inr(v)} axisFormat={(v) => moneyCompact(v, "INR")} ariaLabel="Net worth over time" height={220} testId="networth-chart" />
                <p className="tiny muted" style={{ margin: 0 }}>Net worth at each snapshot: the 1st of each month and the days you changed an entry. Last snapshot {day(hist[hist.length - 1].d)}.</p>
              </>
            )}
          </section>

          {view.assets.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <h2 className="h2">Assets</h2>
              <div className="table-wrap">
                <table aria-label="Assets">
                  <thead><tr><th style={{ textAlign: "left" }}>Asset, and how it's worked out</th><th>Value</th><th /></tr></thead>
                  <tbody>
                    {view.assets.map((r) => (
                      <tr key={r.id}>
                        <td style={{ textAlign: "left", whiteSpace: "normal", minWidth: 180 }}>
                          <b>{r.name}</b>{r.name !== r.label && <span className="tiny muted"> · {r.label}</span>}{r.basis === "as entered" && <span className="tiny muted"> · as entered</span>}
                          <div className="small muted">{r.rule}</div><Facts r={r} />
                        </td>
                        <td className="num">{r.value == null ? "–" : inr(r.value)}<div className="tiny muted">as of {day(r.as_of)}</div></td>
                        <td>{r.entry ? <button className="btn quiet sm" onClick={() => startEdit(r.entry!)} aria-label={`Edit ${r.name}`}>Edit</button>
                          : r.linked ? <Link className="btn quiet sm" to={r.linked}>Open</Link> : null}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {view.gold_price && <p className="tiny muted" style={{ margin: 0 }}>Gold at {inr(view.gold_price.per_g)} a gram (24 carat), from the front-month gold future on the commodity exchange, as of {day(view.gold_price.as_of)}.</p>}
            </section>
          )}

          {view.liabilities.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <h2 className="h2">Loans</h2>
              <div className="table-wrap">
                <table aria-label="Loans">
                  <thead><tr><th style={{ textAlign: "left" }}>Loan</th><th>Owed today</th><th>EMI</th><th>EMIs left</th><th>Interest this FY</th><th>Ends</th><th /></tr></thead>
                  <tbody>
                    {view.liabilities.map((r) => (
                      <tr key={r.id}>
                        <td style={{ textAlign: "left" }}><b>{r.name}</b><div className="tiny muted">{r.entry?.rate}% a year{r.basis === "as entered" ? " · as entered" : ""}</div></td>
                        <td className="num">{inr(r.value)}</td>
                        <td className="num">{r.facts.emi != null ? inr(r.facts.emi) : "–"}</td>
                        <td className="num">{r.facts.left ?? "–"}</td>
                        <td className="num">{r.facts.interest_fy != null ? inr(r.facts.interest_fy) : "–"}</td>
                        <td className="num small">{r.facts.ends ? day(r.facts.ends) : "–"}</td>
                        <td><div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                          {r.facts.left ? <button className="btn quiet sm" onClick={() => setPrepay(r)} aria-label={`Prepay ${r.name}`}>Prepay</button> : null}
                          <button className="btn quiet sm" onClick={() => startEdit(r.entry!)} aria-label={`Edit ${r.name}`}>Edit</button>
                        </div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>Balances owed as of {day(view.as_of)}, worked out from the amount, rate, tenure and start date you entered (reducing balance, monthly EMIs). Your lender's statement is the final word.</p>
            </section>
          )}

          {view.insurance.policies.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
                <h2 className="h2">Insurance policies</h2>
                <span className="small">Premiums a year: <b className="num">{inr(view.insurance.yearly_premium)}</b></span>
              </div>
              <div className="table-wrap">
                <table aria-label="Insurance policies">
                  <thead><tr><th style={{ textAlign: "left" }}>Policy</th><th>Sum assured</th><th>Premium</th><th>Next due</th><th style={{ textAlign: "left" }}>Nominee</th><th /></tr></thead>
                  <tbody>
                    {view.insurance.policies.map((p) => (
                      <tr key={p.id}>
                        <td style={{ textAlign: "left" }}><b>{p.name}</b><div className="tiny muted">{p.label} · {p.insurer}</div></td>
                        <td className="num">{inr(p.sum_assured)}</td>
                        <td className="num">{inr(p.premium)}<div className="tiny muted">{p.frequency === "single" ? "once" : p.frequency}</div></td>
                        <td className="num small">{p.next_due ? <>{day(p.next_due)}<div className="tiny muted">{p.due_in === 0 ? "due today" : `due in ${p.due_in} day${p.due_in === 1 ? "" : "s"}`}</div></> : "–"}</td>
                        <td style={{ textAlign: "left" }} className="small">{p.nominee || <span className="muted">Not entered</span>}</td>
                        <td><button className="btn quiet sm" onClick={() => startEdit(p.entry)} aria-label={`Edit ${p.name}`}>Edit</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>A due date that has passed moves on by the payment period. Policies aren't counted in net worth.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
              <h2 className="h2">Add an entry</h2>
              {view.limit != null && <span className="tiny muted">{view.count} of {view.limit} entries on your plan · <Link className="link" to="/plans">more with Basic</Link></span>}
            </div>
            <label className="field" style={{ maxWidth: 320 }}>What is it?
              <select value={kind} onChange={(e) => { const k = e.target.value as Kind; setKind(k); setAddStart(blank(k)); }}>
                {KIND_ORDER.map((k) => <option key={k} value={k}>{FORM[k].title}</option>)}
              </select>
            </label>
            {full
              ? <div className="banner"><span>Your plan keeps {view.limit} entries. Basic keeps as many as you like, with the history chart.</span><Link to="/plans" className="btn sm">See plans</Link></div>
              : <EntryForm key={kind} kind={kind} start={addStart} busy={busy} saveLabel="Add" onSave={addOne} />}
          </section>

          <section className="stack" style={{ gap: 8 }}>
            <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>
              Rates used unless you enter your own: EPF {view.rates.epf_note}; PPF {view.rates.ppf_note}; sovereign gold bonds {view.rates.sgb}% a year on the issue price.
              Deposits use the bank's usual method (whole periods compounded, simple interest on the days after). Values are before tax. Property and anything marked "as entered" is your own figure.
              Your entries are stored with your account only and never shared.
            </p>
            <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
              <button className="btn quiet" onClick={download}><Download size={16} />Download CSV</button>
              {!empty && <button className="btn danger" onClick={remove}><Trash size={16} />Delete my net worth data</button>}
            </div>
          </section>
        </>
      )}

      {edit && (
        <Modal title={`Edit: ${FORM[edit.kind].title}`} onClose={() => setEdit(null)} wide>
          <EntryForm kind={edit.kind} start={edit.form} busy={busy} saveLabel="Save"
            onSave={async (b) => { if (await send(`/money/net-worth/items/${edit.id}`, "PUT", b, "Saved.")) setEdit(null); }} onCancel={() => setEdit(null)} />
          <button className="btn danger" style={{ marginTop: 16 }} disabled={busy}
            onClick={async () => { if (await send(`/money/net-worth/items/${edit.id}`, "DELETE", undefined, "Removed.")) setEdit(null); }}><Trash size={16} />Remove this entry</button>
        </Modal>
      )}
      {prepay && <PrepayBox loan={prepay} onClose={() => setPrepay(null)} />}
    </div>
  );
}
