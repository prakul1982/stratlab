import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { signClass } from "../lib/format";
import {
  contracts, contractsShort, crore, dayName, istTime, PARTICIPANTS, RANGES, ratio, shortDay, signed, statusLine, strike,
  type CashPoint, type ChainFacts, type ChainPoint, type PartPoint, type PcrRow, type PRow, type Summary,
} from "../lib/positioning";
import { Legend, LineChart } from "../components/Charts";
import { StrikeChart } from "../components/StrikeChart";
import { TradeTabs } from "../components/PositioningCard";
import { Info, Loading } from "../components/ui";

/* /trade/positioning: who holds index futures and options (the exchange's participant-wise files), FII and DII cash
 * flows, each index's put-call ratio, and one index's option chain as facts: open interest and its change by strike,
 * max pain, the strikes with the most open interest and the at-the-money IV. Today's numbers on every plan; the
 * history and the IV percentile and rank on Basic. Nothing here reads the numbers as a signal. */

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

function Card({ title, info, right, children, id }: { title: ReactNode; info?: string; right?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="card stack pos-section" style={{ gap: 14 }} aria-labelledby={id ? `${id}-h` : undefined} id={id}>
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 id={id ? `${id}-h` : undefined} className="h3 row" style={{ gap: 0 }}>{title}{info && <Info>{info}</Info>}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

function Fig({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className="space-fig">
      <span className="tiny muted">{label}</span>
      <b className={`num ${tone ?? ""}`}>{value}</b>
      {sub && <span className="tiny muted">{sub}</span>}
    </div>
  );
}

const n = (r: PRow, k: string) => (r[k] as number | null | undefined) ?? null;

function Chg({ v }: { v: number | null }) {
  return v == null ? null : <span className={`tiny ${signClass(v)}`} style={{ display: "block" }}>{signed(v)}</span>;
}

/** The participants' index futures and options: long, short, net, each with its change from the day before. */
function ParticipantTable({ rows, kind }: { rows: PRow[]; kind: "oi" | "vol" }) {
  const cols: [string, string][] = kind === "oi"
    ? [["fut_idx_long", "Futures long"], ["fut_idx_short", "Futures short"], ["fut_idx_net", "Futures net"],
      ["opt_idx_call_long", "Calls long"], ["opt_idx_call_short", "Calls short"], ["opt_idx_put_long", "Puts long"], ["opt_idx_put_short", "Puts short"]]
    : [["fut_idx_long", "Futures bought"], ["fut_idx_short", "Futures sold"], ["opt_idx_call_long", "Calls bought"],
      ["opt_idx_call_short", "Calls sold"], ["opt_idx_put_long", "Puts bought"], ["opt_idx_put_short", "Puts sold"]];
  return (
    <div className="table-wrap">
      <table className="nums pos-table">
        <caption className="sr-only">{kind === "oi" ? "Index futures and options open interest by participant, in contracts" : "Index futures and options traded by participant, in contracts"}</caption>
        <thead><tr><th scope="col">Index F&amp;O</th>{cols.map(([k, l]) => <th key={k} scope="col">{l}</th>)}{kind === "oi" && <th scope="col">Futures long share</th>}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.id === "total" ? "total" : ""} data-participant={r.id}>
              <th scope="row">{r.label}</th>
              {cols.map(([k]) => (
                <td key={k}><span className={k.endsWith("_net") ? signClass(n(r, k)) : ""}>{k.endsWith("_net") ? signed(n(r, k)) : contracts(n(r, k))}</span><Chg v={n(r, `${k}_chg`)} /></td>
              ))}
              {kind === "oi" && <td>{r.fut_idx_long_pct == null ? "–" : `${r.fut_idx_long_pct}%`}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Participants({ s }: { s: Summary }) {
  const [kind, setKind] = useState<"oi" | "vol">("oi");
  const p = s.participants;
  const rows = kind === "oi" ? p.oi : p.vol ?? [];
  const fii = p.oi.find((r) => r.id === "fii");
  return (
    <Card id="pos-part" title="Participant-wise open interest" right={<Seg label="Open interest or volume" value={kind} onChange={setKind} options={[["oi", "Open interest"], ["vol", "Volume"]]} />}
      info="The exchange's daily count of index futures and options contracts each kind of participant held open (or traded that day), long and short. Clients are individuals and firms trading for themselves; DIIs are domestic institutions (mutual funds, insurers, banks); FIIs are foreign portfolio investors; Pro is brokers trading their own money. The small line under each number is the change from the trading day before.">
      <p className="small muted" data-testid="part-status">{statusLine(p, "participant files")}{p.prev ? ` Changes are from ${dayName(p.prev)}.` : ""}</p>
      {fii && kind === "oi" && (
        <div className="space-figs">
          <Fig label="FII index futures, net" value={signed(n(fii, "fut_idx_net"))} tone={signClass(n(fii, "fut_idx_net"))} sub={`${signed(n(fii, "fut_idx_net_chg"))} from the day before`} />
          <Fig label="FII futures long share" value={fii.fut_idx_long_pct == null ? "–" : `${fii.fut_idx_long_pct}%`} sub="Long of long + short" />
          <Fig label="FII index calls, net" value={signed(n(fii, "opt_idx_call_net"))} sub={`Puts, net ${signed(n(fii, "opt_idx_put_net"))}`} />
        </div>
      )}
      {rows.length ? <ParticipantTable rows={rows} kind={kind} /> : <p className="small muted">No {kind === "oi" ? "open interest" : "volume"} file stored yet.</p>}
      <p className="tiny muted">Contracts, as the exchange counts them. Stock futures and options are in the exchange's file too; the history keeps them.</p>
    </Card>
  );
}

function Cash({ s }: { s: Summary }) {
  const c = s.cash;
  return (
    <Card id="pos-cash" title="FII and DII cash market"
      info="The exchange's provisional numbers for the day: what foreign portfolio investors (FII/FPI) and domestic institutions (DII) bought and sold in the cash market, in ₹ crore. Final numbers can differ a little.">
      <p className="small muted" data-testid="cash-status">{statusLine(c, "cash numbers")}</p>
      {c.fii && c.dii ? (
        <div className="space-figs">
          <Fig label="FII/FPI net" value={crore(c.fii.net, true)} tone={signClass(c.fii.net)} sub={`Bought ${crore(c.fii.buy)} · sold ${crore(c.fii.sell)}`} />
          <Fig label="DII net" value={crore(c.dii.net, true)} tone={signClass(c.dii.net)} sub={`Bought ${crore(c.dii.buy)} · sold ${crore(c.dii.sell)}`} />
        </div>
      ) : <p className="small muted">Not published yet.</p>}
    </Card>
  );
}

function PcrTable() {
  const [rows, setRows] = useState<PcrRow[] | null | "error">(null);
  useEffect(() => { api<{ pcr: PcrRow[] }>("/trade/positioning/pcr").then((d) => setRows(d.pcr)).catch(() => setRows("error")); }, []);
  return (
    <Card id="pos-pcr" title="Put-call ratio by index"
      info="Total open interest in the nearest expiry's puts divided by its calls' (and the same for the day's volume), over the strikes read around the money. 'Near the money' counts only the 15 strikes either side, as StratLab's recordings do, so it matches the history.">
      {rows === null ? <Loading label="Reading each index's chain" />
        : rows === "error" ? <p className="small muted">The chains couldn't be read just now. Try again in a minute.</p>
        : (
      <>
      <div className="table-wrap">
        <table className="nums pos-table" data-testid="pcr-table">
          <caption className="sr-only">Put-call ratio for each index's nearest expiry</caption>
          <thead><tr><th scope="col">Index</th><th scope="col">Expiry</th><th scope="col">PCR (OI)</th><th scope="col">Near the money</th><th scope="col">PCR (volume)</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} data-pcr={r.name}>
                <th scope="row">{r.name}</th>
                {r.source ? (
                  <>
                    <td>{r.expiry ? shortDay(r.expiry) : "–"}</td><td>{ratio(r.pcr_oi)}</td><td>{ratio(r.pcr_near)}</td><td>{ratio(r.pcr_vol)}</td>
                  </>
                ) : <td colSpan={4} className="muted small" style={{ textAlign: "left" }}>No live chain and nothing recorded yet</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny muted">{rows.some((r) => r.source === "recorded") ? "Where the live chain is offline, the newest recording is shown. " : ""}Live chains are read at most once a minute.</p>
      </>
        )}
    </Card>
  );
}

function Chain({ names, full, plan }: { names: string[]; full: boolean; plan: string }) {
  const [name, setName] = useState(names[0] ?? "NIFTY");
  const [expiry, setExpiry] = useState("current");
  const [mode, setMode] = useState<"oi" | "chg">("oi");
  const [c, setC] = useState<ChainFacts | null | "error">(null);
  useEffect(() => {
    let live = true;
    setC(null);
    api<ChainFacts>(`/trade/positioning/chain?name=${name}&expiry=${expiry}`).then((d) => live && setC(d)).catch(() => live && setC("error"));
    return () => { live = false; };
  }, [name, expiry]);
  const hasChg = c && c !== "error" && c.rows.some((r) => r.call_chg != null || r.put_chg != null);
  return (
    <Card id="pos-chain" title="Option chain facts"
      info="From the index's option chain: open interest by strike and its change since the last recording of the trading day before; the max-pain strike (where the open options would be worth the least in total at expiry); the strikes with the most call and put open interest; and the at-the-money implied volatility, worked out from the at-the-money call and put with Black's formula, the forward from put-call parity and no interest rate.">
      <div className="row wrap" style={{ gap: 8 }}>
        <Seg label="Index" value={name} onChange={setName} options={names.map((x) => [x, x] as [string, string])} />
        <Seg label="Expiry" value={expiry} onChange={setExpiry} options={[["current", "Nearest expiry"], ["next", "Next"]]} />
      </div>
      {c === null ? <Loading label={`Reading ${name}'s chain`} />
        : c === "error" ? <p className="small muted">The chain couldn't be read just now. Try again in a minute.</p>
        : !c.source ? <p className="small muted" data-testid="chain-empty">No live chain for {name} right now, and none recorded yet.</p>
        : (
          <div className="stack" style={{ gap: 14 }} data-testid="chain-facts">
            <p className="small muted">
              Expiry {dayName(c.expiry)} · spot {strike(c.spot)} · {c.source === "live" ? "live chain" : "recorded chain"}, {istTime(c.as_of)}
            </p>
            <div className="space-figs">
              <Fig label="PCR (open interest)" value={ratio(c.pcr?.oi)} sub={`Near the money ${ratio(c.pcr_near)} · volume ${ratio(c.pcr?.vol)}`} />
              <Fig label="Max-pain strike" value={strike(c.max_pain)} />
              <Fig label="Most call open interest" value={strike(c.top?.call?.strike)} sub={c.top?.call ? `${contracts(c.top.call.oi)} contracts` : undefined} />
              <Fig label="Most put open interest" value={strike(c.top?.put?.strike)} sub={c.top?.put ? `${contracts(c.top.put.oi)} contracts` : undefined} />
              <Fig label="ATM implied volatility" value={c.atm_iv == null ? "–" : `${c.atm_iv.toFixed(1)}%`} sub={c.atm ? `At the ${strike(c.atm)} strike` : undefined} />
              <IvFig c={c} full={full} plan={plan} />
            </div>
            <div className="row wrap" style={{ gap: 10, justifyContent: "space-between" }}>
              <Seg label="Open interest or its change" value={mode} onChange={setMode} options={[["oi", "Open interest"], ["chg", "Change"]]} />
              <Legend items={[{ label: "Calls", color: "var(--pos-call)" }, { label: "Puts", color: "var(--pos-put)" }]} />
            </div>
            {mode === "chg" && !hasChg ? (
              <p className="small muted">No recording of this expiry from the trading day before, so there's no change to show yet.</p>
            ) : (
              <StrikeChart rows={c.rows} mode={mode} spot={c.spot} label={`${name} ${mode === "oi" ? "open interest" : "change in open interest"} by strike, calls and puts`} />
            )}
            {c.change_from && <p className="tiny muted">Change since the recording of {istTime(c.change_from)}.</p>}
            <details className="pos-details">
              <summary className="small">Show the strikes as a table</summary>
              <div className="table-wrap">
                <table className="nums pos-table">
                  <caption className="sr-only">{name} open interest, change and volume by strike</caption>
                  <thead><tr><th scope="col">Strike</th><th scope="col">Call OI</th><th scope="col">Change</th><th scope="col">Call volume</th><th scope="col">Put OI</th><th scope="col">Change</th><th scope="col">Put volume</th></tr></thead>
                  <tbody>
                    {[...c.rows].reverse().map((r) => (
                      <tr key={r.strike} className={r.strike === c.atm ? "atm" : ""}>
                        <th scope="row">{strike(r.strike)}</th><td>{contracts(r.call_oi)}</td><td>{signed(r.call_chg)}</td><td>{contracts(r.call_vol)}</td>
                        <td>{contracts(r.put_oi)}</td><td>{signed(r.put_chg)}</td><td>{contracts(r.put_vol)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <p className="tiny muted">The PCR, max pain and the top strikes count the {c.strikes_counted ?? c.rows.length} strikes read around the money; the chart shows the 41 nearest. {c.note}</p>
          </div>
        )}
    </Card>
  );
}

function IvFig({ c, full, plan }: { c: ChainFacts; full: boolean; plan: string }) {
  if (!full) return <Fig label="IV percentile and rank" value={<Link to="/plans" className="link small">{plan} plan</Link>} sub="Over StratLab's recorded days" />;
  const s = c.iv;
  if (!s || s.percentile == null)
    return <Fig label="IV percentile and rank" value="–" sub={s ? `${s.days} of ${s.need} recorded days needed so far` : undefined} />;
  return <Fig label="IV percentile · rank" value={`${s.percentile.toFixed(0)} · ${s.rank == null ? "–" : s.rank.toFixed(0)}`}
    sub={`Over ${s.days} recorded days (${s.low?.toFixed(1)}%–${s.high?.toFixed(1)}%)`} />;
}

/* ---------- history (Basic) ---------- */
const MEASURES: [string, string][] = [["fut_idx_net", "Index futures, net"], ["opt_idx_call_net", "Index calls, net"], ["opt_idx_put_net", "Index puts, net"], ["fut_stk_net", "Stock futures, net"]];

function useHistory<T>(kind: string, range: string, name = "NIFTY") {
  const [d, setD] = useState<T[] | null | "error">(null);
  useEffect(() => {
    let live = true;
    api<{ points: T[] }>(`/trade/positioning/history?kind=${kind}&range=${range}&name=${name}`)
      .then((r) => live && setD(r.points)).catch(() => live && setD("error"));
    return () => { live = false; };
  }, [kind, range, name]);
  return d;
}

function ChartBox({ title, children, empty }: { title: string; children: ReactNode; empty: boolean }) {
  return (
    <div className="stack pos-chart" style={{ gap: 8 }}>
      <h3 className="small" style={{ fontWeight: 600 }}>{title}</h3>
      {empty ? <p className="small muted">Not enough stored days to draw yet.</p> : children}
    </div>
  );
}

function History({ names }: { names: string[] }) {
  const [range, setRange] = useState("6m");
  const [who, setWho] = useState<PRow["id"]>("fii");
  const [measure, setMeasure] = useState("fut_idx_net");
  const [name, setName] = useState(names[0] ?? "NIFTY");
  const parts = useHistory<PartPoint>("participants", range);
  const cash = useHistory<CashPoint>("cash", range);
  const chain = useHistory<ChainPoint>("chain", range, name);
  const label = (p: { day: string }[]) => p.map((x) => dayName(x.day));
  const axis = (p: { day: string }[]) => p.map((x) => shortDay(x.day));
  const mlabel = MEASURES.find(([k]) => k === measure)?.[1] ?? "";
  return (
    <Card id="pos-history" title="History" info="The stored days: the exchange's files from its archives and each evening since, the cash numbers from the day StratLab started reading them, and the option-chain facts from StratLab's own recordings (the nearest expiry with at least a day to go, over the 15 strikes either side of the money).">
      <div className="row wrap" style={{ gap: 8 }}>
        <Seg label="Time range" value={range} onChange={setRange} options={RANGES as [string, string][]} />
      </div>
      {parts === null || cash === null ? <Loading label="Reading the history" />
        : parts === "error" || cash === "error" ? <p className="small muted">The history couldn't be read just now.</p>
        : (
          <div className="stack" style={{ gap: 22 }}>
            <div className="stack" style={{ gap: 8 }}>
              <div className="row wrap" style={{ gap: 8 }}>
                <Seg label="Participant" value={who} onChange={setWho} options={PARTICIPANTS} />
                <label className="field" style={{ minWidth: 180 }}>
                  <span className="sr-only">Measure</span>
                  <select value={measure} onChange={(e) => setMeasure(e.target.value)} aria-label="Measure">
                    {MEASURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </label>
              </div>
              <ChartBox title={`${PARTICIPANTS.find(([k]) => k === who)?.[1]}: ${mlabel.toLowerCase()} (contracts)`} empty={parts.length < 2}>
                <LineChart lines={[{ values: parts.map((p) => p[who as "fii"]?.[measure] ?? null), color: "var(--pos-call)", width: 2, label: mlabel }]}
                  labels={label(parts)} axisLabels={axis(parts)} format={contracts} axisFormat={contractsShort} baseline={0} height={220}
                  ariaLabel={`${who} ${mlabel} by day`} />
              </ChartBox>
            </div>
            <ChartBox title="Cash market, net (₹ crore)" empty={cash.length < 2}>
              <Legend items={[{ label: "FII/FPI", color: "var(--pos-call)" }, { label: "DII", color: "var(--pos-put)" }]} />
              <LineChart lines={[{ values: cash.map((p) => p.fii), color: "var(--pos-call)", width: 2, label: "FII/FPI" },
                { values: cash.map((p) => p.dii), color: "var(--pos-put)", width: 2, label: "DII" }]}
                labels={label(cash)} axisLabels={axis(cash)} format={(v) => crore(v, true)} axisFormat={(v) => contractsShort(v)} baseline={0} height={200}
                ariaLabel="FII and DII net cash market flows by day" />
            </ChartBox>
            <div className="stack" style={{ gap: 8 }}>
              <Seg label="Index for the chain history" value={name} onChange={setName} options={names.map((x) => [x, x] as [string, string])} />
              {chain === null ? <Loading label={`Reading ${name}'s recorded days`} />
                : chain === "error" ? <p className="small muted">The recorded days couldn't be read.</p>
                : (
                  <div className="grid2" style={{ gap: 18 }}>
                    <ChartBox title={`${name} PCR, near the money`} empty={chain.length < 2}>
                      <Legend items={[{ label: "Open interest", color: "var(--pos-call)" }, { label: "Volume", color: "var(--pos-put)" }]} />
                      <LineChart lines={[{ values: chain.map((p) => p.pcr_oi), color: "var(--pos-call)", width: 2, label: "Open interest" },
                        { values: chain.map((p) => p.pcr_vol), color: "var(--pos-put)", width: 2, label: "Volume" }]}
                        labels={label(chain)} axisLabels={axis(chain)} format={ratio} height={200} ariaLabel={`${name} put-call ratio by day`} />
                    </ChartBox>
                    <ChartBox title={`${name} ATM implied volatility (%)`} empty={chain.length < 2}>
                      <LineChart lines={[{ values: chain.map((p) => p.atm_iv), color: "var(--pos-call)", width: 2, label: "ATM IV" }]}
                        labels={label(chain)} axisLabels={axis(chain)} format={(v) => `${v.toFixed(1)}%`} height={200} ariaLabel={`${name} at-the-money IV by day`} />
                    </ChartBox>
                  </div>
                )}
            </div>
          </div>
        )}
    </Card>
  );
}

function Locked({ plan }: { plan: string }) {
  return (
    <section className="card stack" style={{ gap: 10 }} data-testid="pos-locked">
      <h2 className="h3">History and IV percentiles</h2>
      <p className="small muted">Charts of every participant's positions, the FII and DII cash flows, each index's PCR and ATM IV by day, and where today's IV sits among the recorded days, are on the {plan} plan. Today's numbers above are on every plan.</p>
      <Link to="/plans" className="btn sm" style={{ alignSelf: "flex-start" }}>See the {plan} plan</Link>
    </section>
  );
}

export function PositioningPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Summary>("/trade/positioning?pcr=false").then(setS).catch((e) => setError(e instanceof ApiError ? e.message : "The positioning numbers couldn't be read."));
  }, []);
  return (
    <div className="stack pos-page" style={{ gap: 20 }}>
      <TradeTabs />
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="page-title">Positioning</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>Who holds index futures and options, how foreign and domestic institutions bought and sold in the cash market, and what the index option chains show. The exchange's numbers as published, and arithmetic on option chains: facts, not advice.</p>
      </div>
      {error ? <div className="banner">{error}</div>
        : !s ? <Loading label="Reading the newest numbers" />
        : (
          <>
            <Participants s={s} />
            <div className="grid2" style={{ alignItems: "start" }}>
              <Cash s={s} />
              <PcrTable />
            </div>
            <Chain names={s.names} full={s.full} plan={s.plan_needed} />
            {s.full ? <History names={s.names} /> : <Locked plan={s.plan_needed} />}
            <p className="tiny muted">{s.note}</p>
          </>
        )}
    </div>
  );
}

export default PositioningPage;
