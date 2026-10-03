import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { price } from "../lib/format";
import { researchApi, type Region } from "../lib/research";
import { CONDITIONS, EVENT_KINDS, MA_PERIODS, alertsApi, conditionKey, type AlertBody, type AlertsPage, type StockAlert } from "../lib/alerts";
import { Bell } from "./Icons";
import { Modal } from "./ui";

type Saved = AlertsPage & { alert: StockAlert; note: string | null };

/** Create or edit one alert. A stock passed in is fixed; `choices` offers a list (the watchlist) instead. */
export function AlertForm({ region: r0 = "IN", symbol: s0 = "", editing, choices, onSaved }: {
  region?: Region; symbol?: string; editing?: StockAlert; choices?: { region: Region; symbol: string }[]; onSaved: (r: Saved) => void;
}) {
  const { fail, notify } = useApp();
  const fixed = !editing && !!s0 && !choices;
  const [region, setRegion] = useState<Region>(editing?.region ?? r0);
  const [symbol, setSymbol] = useState(editing?.symbol ?? (s0 || choices?.[0]?.symbol || ""));
  const [cond, setCond] = useState(editing ? conditionKey(editing) : "price_above");
  const [value, setValue] = useState(editing?.value != null && editing.kind !== "stage" ? String(editing.value) : "");
  const [period, setPeriod] = useState(editing?.period && editing.kind === "ma" ? editing.period : 50);
  const [stage, setStage] = useState(editing?.kind === "stage" ? editing.value ?? 0 : 0);
  const [repeat, setRepeat] = useState(editing?.repeat ?? false);
  const [note, setNote] = useState(editing?.note ?? "");
  const [now, setNow] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
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
    const needsValue = c.kind === "price" || c.kind === "move" || c.kind === "rsi";
    if (!sym) { notify("Enter a ticker, like RELIANCE or AAPL."); return; }
    if (needsValue && (!value.trim() || !Number.isFinite(n) || n <= 0)) { notify(c.kind === "move" ? "Enter the day's move in percent." : "Enter the level."); return; }
    const body: AlertBody = {
      region, symbol: sym, kind: c.kind, op: c.op, repeat, note: note.trim() || null,
      value: needsValue ? n : c.kind === "stage" ? stage : null, period: c.kind === "ma" ? period : null,
    };
    setBusy(true);
    try {
      const r = editing ? await alertsApi.update(editing.id, body) : await alertsApi.create(body);
      notify(r.note ?? (editing ? "Alert saved." : `Alert set on ${sym}.`));
      onSaved(r);
    } catch (err) { fail(err); } finally { setBusy(false); }
  };

  return (
    <form className="stack alert-form" style={{ gap: 14 }} onSubmit={save}>
      {fixed ? (
        <p className="small"><b>{sym}</b> <span className="muted">· {region === "IN" ? "India" : "US"}{now != null ? ` · now ${price(now, ccy)}` : ""}</span></p>
      ) : (
        <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
          <label className="field" style={{ flex: "0 0 auto" }}>Market
            <select value={region} onChange={(e) => setRegion(e.target.value as Region)} disabled={!!choices}>
              <option value="IN">India</option><option value="US">United States</option>
            </select>
          </label>
          <label className="field" style={{ flex: "1 1 160px" }}>Stock
            {choices ? (
              <select value={`${region}:${symbol}`} onChange={(e) => { const [rg, s] = e.target.value.split(":"); setRegion(rg as Region); setSymbol(s); }}>
                {choices.map((x) => <option key={`${x.region}:${x.symbol}`} value={`${x.region}:${x.symbol}`}>{x.symbol}</option>)}
              </select>
            ) : <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder={region === "IN" ? "RELIANCE" : "AAPL"} maxLength={20} autoCapitalize="characters" />}
          </label>
        </div>
      )}
      {!fixed && now != null && <span className="hint">{sym} is at {price(now, ccy)} now.</span>}
      <label className="field">Alert me when
        <select aria-label="Alert me when" value={cond} onChange={(e) => setCond(e.target.value)}>
          {CONDITIONS.filter((x) => !x.india || region === "IN").map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
        </select>
      </label>
      {c.kind === "price" && <label className="field">Price level ({region === "IN" ? "₹" : "$"})
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder={now != null ? String(Math.round(now)) : "3000"} /></label>}
      {c.kind === "move" && <label className="field">Move in a day (%)
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="5" /></label>}
      {c.kind === "rsi" && <label className="field">RSI level (1 to 99)
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder={c.op === "above" ? "70" : "30"} /></label>}
      {c.kind === "ma" && <label className="field">Moving average
        <select aria-label="Moving average" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
          {MA_PERIODS.map((p) => <option key={p} value={p}>{p}-day average</option>)}
        </select></label>}
      {c.kind === "stage" && <label className="field">Which change
        <select aria-label="Which change" value={stage} onChange={(e) => setStage(Number(e.target.value))}>
          <option value={0}>Any change of stage</option>
          {[1, 2, 3, 4].map((s) => <option key={s} value={s}>Enters Stage {s}</option>)}
        </select></label>}
      <span className="hint">{EVENT_KINDS.includes(c.kind)
        ? "Checked once each evening against that day's exchange disclosures. The alert says who, which way, how many and when."
        : c.kind === "move" || c.kind === "high52" || c.kind === "low52"
        ? "Checked through the trading day with the live price."
        : "Fires when it crosses during market hours: the first check notes which side it's on, then it waits for a cross."}</span>
      <label className="field">Note for yourself (optional)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} placeholder="Why you set it" /></label>
      <label className="row small" style={{ gap: 8 }}>
        <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} />
        {EVENT_KINDS.includes(c.kind) ? "Repeat: keep it on after it fires (one message a day at most)" : "Repeat: keep it on after it fires (at most once a day)"}
      </label>
      <div className="row wrap" style={{ gap: 10 }}>
        <button className="btn" disabled={busy}>{busy ? "Saving…" : editing ? "Save alert" : "Set alert"}</button>
        <Link to="/account" className="btn quiet sm">Where alerts go</Link>
      </div>
    </form>
  );
}

/** "Set alert" for a company page, the deep dive or the watchlist: opens the form in a pop-up. */
export function AlertButton({ region, symbol, choices, label = "Set alert" }: {
  region: Region; symbol?: string; choices?: { region: Region; symbol: string }[]; label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn quiet sm" onClick={() => setOpen(true)} disabled={choices && !choices.length}><Bell size={17} />{label}</button>
      {open && (
        <Modal title={symbol ? `Alert on ${symbol}` : "Set an alert"} onClose={() => setOpen(false)}>
          <AlertForm region={region} symbol={symbol} choices={choices} onSaved={() => setOpen(false)} />
          <p className="hint" style={{ marginTop: 12 }}>See and change all your alerts on the <Link className="link" to="/alerts">Alerts page</Link>.</p>
        </Modal>
      )}
    </>
  );
}
