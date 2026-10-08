import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { price } from "../lib/format";
import { researchApi, type Region } from "../lib/research";
import { CONDITIONS, EVENT_KINDS, MA_PERIODS, alertsApi, conditionKey, type AlertBody, type AlertsPage, type StockAlert } from "../lib/alerts";
import { Bell } from "./Icons";
import { Modal } from "./ui";
import { CheckField, Field, FormActions, FormGrid, Notice, Select, StockPicker } from "./kit";
import { type ApiError } from "../lib/api";
import { numberProblem } from "../lib/validate";

type Saved = AlertsPage & { alert: StockAlert; note: string | null };

/** Create or edit one alert. A stock passed in is fixed; `choices` offers a list (the watchlist) instead. */
export function AlertForm({ region: r0 = "IN", symbol: s0 = "", editing, choices, onSaved, condition, nowhere, link = true }: {
  region?: Region; symbol?: string; editing?: StockAlert; choices?: { region: Region; symbol: string }[]; onSaved: (r: Saved) => void;
  condition?: string;
  /** Nothing is set up to send an alert yet (no phone, Telegram or confirmed email): said before it's set. */
  nowhere?: boolean;
  /** Offer "Where alerts go" (once: in the notice when nothing is set up, else beside the button). A page that already
   * has that link on it passes false. */
  link?: boolean;
}) {
  const { fail, notify } = useApp();
  const fixed = !editing && !!s0 && !choices;
  const [region, setRegion] = useState<Region>(editing?.region ?? r0);
  const [symbol, setSymbol] = useState(editing?.symbol ?? (s0 || choices?.[0]?.symbol || ""));
  const [picked, setPicked] = useState(editing?.symbol ?? (s0 || ""));        // what the stock box shows after a pick (typing alone leaves it be)
  const [cond, setCond] = useState(editing ? conditionKey(editing) : condition ?? "price_above");
  const [value, setValue] = useState(editing?.value != null && editing.kind !== "stage" ? String(editing.value) : "");
  const [period, setPeriod] = useState(editing?.period && editing.kind === "ma" ? editing.period : 50);
  const [stage, setStage] = useState(editing?.kind === "stage" ? editing.value ?? 0 : 0);
  const [repeat, setRepeat] = useState(editing?.repeat ?? false);
  const [note, setNote] = useState(editing?.note ?? "");
  const [now, setNow] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  // what's wrong, under the box it belongs to (not a toast that outlives the fix)
  const [errs, setErrs] = useState<{ symbol?: string; value?: string }>({});
  const c = CONDITIONS.find((x) => x.key === cond && (!x.india || region === "IN")) ?? CONDITIONS[0];
  const sym = symbol.trim().toUpperCase();
  const ccy = region === "IN" ? "INR" : "USD";

  // the price now, so the level can be set against it
  useEffect(() => {
    setNow(null);
    if (!/^[A-Z0-9&._-]{1,20}$/.test(sym)) return;
    let live = true;
    const t = window.setTimeout(() => researchApi.quotes(region, [sym]).then((q) => { if (live) setNow(q[sym]?.price ?? null); }).catch(() => undefined), 350);
    return () => { live = false; window.clearTimeout(t); };
  }, [region, sym]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = Number(value);
    const needsValue = c.kind === "price" || c.kind === "move" || c.kind === "rsi" || c.kind === "etfgap" || c.kind === "mtf";
    const bad = {
      symbol: sym ? undefined : "Type a name or ticker, then pick the company.",
      value: needsValue ? numberProblem(value, c.kind === "rsi" ? { min: 1, max: 99 } : { min: 0, above: true }) ?? undefined : undefined,
    };
    setErrs(bad);
    if (bad.symbol || bad.value) return;
    const body: AlertBody = {
      region, symbol: sym, kind: c.kind, op: c.op, repeat, note: note.trim() || null,
      value: needsValue ? n : c.kind === "stage" ? stage : null, period: c.kind === "ma" ? period : null,
    };
    setBusy(true);
    try {
      const r = editing ? await alertsApi.update(editing.id, body) : await alertsApi.create(body);
      notify(r.note ?? (editing ? "Alert saved." : `Alert set on ${sym}.`));
      onSaved(r);
    } catch (err) {
      const f = (err as ApiError).fields;
      if (f?.value || f?.symbol) setErrs({ value: f.value, symbol: f.symbol }); else fail(err);
    } finally { setBusy(false); }
  };

  const hint = c.kind === "etfgap"
    ? "Checked through the trading day: the live price against the fund's last published NAV. On the Basic plan."
    : c.kind === "mwpl"
    ? "Checked each evening against the exchange's combined open interest file: fires when the stock's MWPL use crosses 80%, up or down. From 95% the stock is in the F&O ban period. On the Basic plan."
    : c.kind === "mtf"
    ? "Checked each evening against the exchange's margin trading disclosure (published the next trading day): fires when the funded shares cross your level. On the Basic plan."
    : c.kind === "surveillance"
    ? "Checked twice each trading day against the exchange's surveillance lists (ASM, GSM, ESM, trade-to-trade, F&O ban, price bands). The alert says which list, which stage and the list's date."
    : c.kind === "bizupdate"
    ? "Checked each evening against the company's exchange filings. The alert gives the update's headline figure and its change on the year, as filed. On the Basic plan."
    : EVENT_KINDS.includes(c.kind)
    ? "Checked once each evening against that day's exchange disclosures. The alert says who, which way, how many and when."
    : c.kind === "move" || c.kind === "high52" || c.kind === "low52"
    ? "Checked through the trading day with the live price."
    : "Fires when it crosses during market hours: the first check notes which side it's on, then it waits for a cross.";

  const takeValue = (v: string) => { setValue(v); setErrs((x) => ({ ...x, value: undefined })); };

  return (
    <FormGrid onSubmit={save} label="Alert">
      {nowhere && !editing && (
        <div className="k-form-wide">
          <Notice role="status" action={link ? { label: "Where alerts go", to: "/settings#notifications" } : undefined}>
            Nothing is set up to send alerts yet, so this one will only show on the Alerts page when it fires.
          </Notice>
        </div>
      )}
      {fixed ? (
        <p className="k-small k-form-wide"><b>{sym}</b> <span className="k-muted">· {region === "IN" ? "India" : "US"}{now != null ? ` · now ${price(now, ccy)}` : ""}</span></p>
      ) : (
        <>
          <Field label="Market" wide>{(id) => <Select id={id} value={region} disabled={!!choices} onChange={(v) => setRegion(v as Region)} options={[{ value: "IN", label: "India" }, { value: "US", label: "United States" }]} />}</Field>
          {choices ? (
            <Field label="Stock" wide>
              {(id) => <Select id={id} value={`${region}:${symbol}`} onChange={(v) => { const [rg, s] = v.split(":"); setRegion(rg as Region); setSymbol(s); }}
                options={choices.map((x) => ({ value: `${x.region}:${x.symbol}`, label: x.symbol }))} />}
            </Field>
          ) : (
            <Field label="Stock" wide error={errs.symbol} hint={now != null ? `${sym} is at ${price(now, ccy)} now` : undefined}>
              {(id) => <StockPicker id={id} market={region} value={picked} placeholder={region === "IN" ? "Name or symbol, like RELIANCE" : "Name or ticker, like AAPL"}
                onText={(t) => { setSymbol(t); setErrs((x) => ({ ...x, symbol: undefined })); }} onPick={(s, r) => { setRegion(r); setSymbol(s); setPicked(s); setErrs((x) => ({ ...x, symbol: undefined })); }} />}
            </Field>
          )}
        </>
      )}
      <Field label="Alert me when" wide>
        {(id) => <Select id={id} value={cond} onChange={setCond} options={CONDITIONS.filter((x) => !x.india || region === "IN").map((x) => ({ value: x.key, label: x.label }))} />}
      </Field>
      {c.kind === "price" && <Field label="Price level" unit={region === "IN" ? "₹" : "$"} inputMode="decimal" value={value} onChange={(e) => takeValue(e.target.value)}
        placeholder={now != null ? String(Math.round(now)) : ""} error={errs.value} hint={now != null ? `Now ${price(now, ccy)}` : undefined} />}
      {c.kind === "move" && <Field label="Move in a day" unit="%" inputMode="decimal" value={value} onChange={(e) => takeValue(e.target.value)} placeholder="5" error={errs.value} />}
      {c.kind === "etfgap" && <Field label="Gap to its last NAV" unit="%" inputMode="decimal" value={value} onChange={(e) => takeValue(e.target.value)} placeholder="2" error={errs.value} />}
      {c.kind === "mtf" && <Field label="Level" unit="% of shares" inputMode="decimal" value={value} onChange={(e) => takeValue(e.target.value)} placeholder="1" info="As a percent of the shares issued." error={errs.value} />}
      {c.kind === "rsi" && <Field label="RSI level" inputMode="decimal" value={value} onChange={(e) => takeValue(e.target.value)} placeholder={c.op === "above" ? "70" : "30"} rule="1 to 99" error={errs.value} />}
      {c.kind === "ma" && <Field label="Moving average">{(id) => <Select id={id} value={period} onChange={(v) => setPeriod(Number(v))} options={MA_PERIODS.map((p) => ({ value: p, label: `${p}-day average` }))} />}</Field>}
      {c.kind === "stage" && <Field label="Which change">{(id) => <Select id={id} value={stage} onChange={(v) => setStage(Number(v))}
        options={[{ value: 0, label: "Any change of stage" }, ...[1, 2, 3, 4].map((s) => ({ value: s, label: `Enters Stage ${s}` }))]} />}</Field>}
      <p className="k-note k-form-wide">{hint}</p>
      <Field label="Note for yourself" optional wide value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} placeholder="Why you set it" />
      <div className="k-form-wide">
        <CheckField checked={repeat} onChange={setRepeat}
          label={EVENT_KINDS.includes(c.kind) ? "Repeat: keep it on after it fires (one message a day at most)" : "Repeat: keep it on after it fires (at most once a day)"} />
      </div>
      <FormActions>
        <button className="btn" disabled={busy}>{busy ? "Saving…" : editing ? "Save alert" : "Set alert"}</button>
        {link && !(nowhere && !editing) && <Link to="/settings#notifications" className="btn quiet sm">Where alerts go</Link>}
      </FormActions>
    </FormGrid>
  );
}

/** "Set alert" for a company page, the deep dive or the watchlist: opens the form in a pop-up. */
export function AlertButton({ region, symbol, choices, label = "Set alert", condition }: {
  region: Region; symbol?: string; choices?: { region: Region; symbol: string }[]; label?: string; condition?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn quiet sm" onClick={() => setOpen(true)} disabled={choices && !choices.length}><Bell size={17} />{label}</button>
      {open && <AlertDialog region={region} symbol={symbol} choices={choices} condition={condition} onClose={() => setOpen(false)} />}
    </>
  );
}

/** The alert form in a pop-up, for a page that opens it from its own menu (a company page's More). */
export function AlertDialog({ region, symbol, choices, condition, onClose }: {
  region: Region; symbol?: string; choices?: { region: Region; symbol: string }[]; condition?: string; onClose: () => void;
}) {
  return (
    <Modal title={symbol ? `Alert on ${symbol}` : "Set an alert"} onClose={onClose}>
      <div className="k-stack">
        <AlertForm region={region} symbol={symbol} choices={choices} condition={condition} onSaved={onClose} />
        <p className="k-note">See and change all your alerts on the <Link className="link" to="/alerts">Alerts page</Link>.</p>
      </div>
    </Modal>
  );
}
