import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { signClass } from "../lib/format";
import {
  contracts, contractsShort, crore, dayName, istTime, PARTICIPANTS, pct, RANGES, ratio, shortDay, sides, signed, spanLine, statusLine, strike,
  type CashPoint, type ChainFacts, type ChainPoint, type Coverage, type PartPoint, type PcrRow, type PRow, type Span, type Summary,
} from "../lib/positioning";
import { ChartEmpty, Legend, LineChart } from "../components/Charts";
import { StrikeChart } from "../components/StrikeChart";
import { Info, Loading } from "../components/ui";
import { useMoreColumns } from "../components/MoreColumns";
import { VixPanel } from "../components/VixPanel";

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

type Segment = "idx" | "stk";
const SEG_WORD: Record<Segment, string> = { idx: "index", stk: "stock" };

/** One source line under a section's title: where the numbers come from, and how much is stored. */
function Source({ children, testId }: { children: ReactNode; testId?: string }) {
  return <p className="tiny muted pos-source" data-testid={testId}>{children}</p>;
}

/** Long against short as a thin bar (the long side dark), with the two shares written out beside it. */
function Split({ long, short, words }: { long: number | null; short: number | null; words: [string, string] }) {
  if (long == null || short == null) return <>–</>;
  return (
    <span className="pos-split" title={sides(long, short, words)}>
      <span className="pos-split-bar" aria-hidden="true"><span style={{ width: `${long}%` }} /></span>
      <span>{pct(long)} / {pct(short)}</span>
    </span>
  );
}

/** The participants' futures and options (index or stock): long, short and net, each with its change from the day
 * before. Each side's share of the futures (worked out from long and short) is the extra column, so the table fits a
 * laptop; the FII figures above show it for FIIs either way. */
function ParticipantTable({ rows, kind, seg, split }: { rows: PRow[]; kind: "oi" | "vol"; seg: Segment; split: boolean }) {
  const [lo, sh]: [string, string] = kind === "oi" ? ["long", "short"] : ["bought", "sold"];
  const cols: [string, string][] = [
    [`fut_${seg}_long`, `Futures ${lo}`], [`fut_${seg}_short`, `Futures ${sh}`], [`fut_${seg}_net`, "Futures net"],
    [`opt_${seg}_call_long`, `Calls ${lo}`], [`opt_${seg}_call_short`, `Calls ${sh}`], [`opt_${seg}_put_long`, `Puts ${lo}`], [`opt_${seg}_put_short`, `Puts ${sh}`]];
  const what = `${SEG_WORD[seg]} futures and options ${kind === "oi" ? "open interest" : "traded"}`;
  return (
    <div className="table-wrap">
      <table className="nums pos-table" data-testid="part-table" data-segment={seg}>
        <caption className="sr-only">{`${what[0].toUpperCase()}${what.slice(1)} by participant, in contracts`}</caption>
        <thead>
          <tr>
            <th scope="col">{seg === "idx" ? "Index" : "Stock"} F&amp;O</th>
            {cols.slice(0, 3).map(([k, l]) => <th key={k} scope="col">{l}</th>)}
            {split && <th scope="col">Futures {lo} / {sh}</th>}
            {cols.slice(3).map(([k, l]) => <th key={k} scope="col">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cell = ([k]: [string, string]) => (
              <td key={k}><span className={k.endsWith("_net") ? signClass(n(r, k)) : ""}>{k.endsWith("_net") ? signed(n(r, k)) : contracts(n(r, k))}</span><Chg v={n(r, `${k}_chg`)} /></td>
            );
            return (
              <tr key={r.id} className={r.id === "total" ? "total" : ""} data-participant={r.id}>
                <th scope="row">{r.label}</th>
                {cols.slice(0, 3).map(cell)}
                {split && <td data-testid={`split-${r.id}`}><Split long={n(r, `fut_${seg}_long_pct`)} short={n(r, `fut_${seg}_short_pct`)} words={[lo, sh]} /></td>}
                {cols.slice(3).map(cell)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** "+1.2 pts from the day before" for a change in a share. */
const pts = (v: number) => `Long share ${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts from the day before`;

/** A tile with both sides written out, one to a line ("19.3% long", "80.7% short"), the bar under them. */
function SidesFig({ label, long, short, words, chg }: { label: string; long: number | null; short: number | null; words: [string, string]; chg: number | null }) {
  return (
    <div className="space-fig" data-testid="sides-fig">
      <span className="tiny muted">{label}</span>
      {/* the bar sits inside the number: a figure is three rows (label, number, note) shared with its neighbours */}
      {long == null || short == null ? <b className="num">–</b> : (
        <b className="num pos-sides"><span>{pct(long)} {words[0]}</span><span>{pct(short)} {words[1]}</span>
          <span className="pos-split-bar" aria-hidden="true"><span style={{ width: `${long}%` }} /></span></b>
      )}
      {chg != null && <span className="tiny muted">{pts(chg)}</span>}
    </div>
  );
}

function Participants({ s }: { s: Summary }) {
  const [kind, setKind] = useState<"oi" | "vol">("oi");
  const [seg, setSeg] = useState<Segment>("idx");
  const p = s.participants;
  const rows = kind === "oi" ? p.oi : p.vol ?? [];
  const fii = rows.find((r) => r.id === "fii");
  const cov = s.coverage?.participants;
  const words: [string, string] = kind === "oi" ? ["long", "short"] : ["bought", "sold"];
  const segWord = SEG_WORD[seg];
  const more = useMoreColumns("pos-part", 1);
  return (
    <Card id="pos-part" title="Participant-wise open interest"
      info="The exchange's daily count of futures and options contracts each kind of participant held open (or traded that day), long and short, for index and for stock contracts. Clients are individuals and firms trading for themselves; DIIs are domestic institutions (mutual funds, insurers, banks); FIIs are foreign portfolio investors; Pro is brokers trading their own money. Long / short is each side's share of the futures held. The small line under each number is the change from the trading day before.">
      <Source testId="part-source">
        From the exchange's end-of-day participant-wise file, published each trading evening.{" "}
        {cov ? <>Stored: {spanLine(cov)}{cov.backfill_done ? "." : `, still filling in the past ${Math.round(cov.backfill_target / 30.4)} months.`}</> : null}
        {s.full && cov && cov.days > 1 ? <> <a className="link" href="#pos-history">See the history</a>.</> : null}
      </Source>
      <div className="row wrap" style={{ gap: 8 }}>
        <Seg label="Index or stock contracts" value={seg} onChange={setSeg} options={[["idx", "Index F&O"], ["stk", "Stock F&O"]]} />
        <Seg label="Open interest or volume" value={kind} onChange={setKind} options={[["oi", "Open interest"], ["vol", "Volume"]]} />
        {rows.length > 0 && more.toggle}
      </div>
      <p className="small muted" data-testid="part-status">{statusLine(p, "participant files")}{p.prev ? ` Changes are from ${dayName(p.prev)}.` : ""}</p>
      {fii && (
        <div className="space-figs" data-testid="part-figs">
          <Fig label={`FII ${segWord} futures, net`} value={signed(n(fii, `fut_${seg}_net`))} tone={signClass(n(fii, `fut_${seg}_net`))}
            sub={`${signed(n(fii, `fut_${seg}_net_chg`))} from the day before`} />
          <SidesFig label={`FII ${segWord} futures, ${words.join(" · ")}`} long={n(fii, `fut_${seg}_long_pct`)} short={n(fii, `fut_${seg}_short_pct`)} words={words}
            chg={kind === "oi" ? n(fii, `fut_${seg}_long_pct_chg`) : null} />
          <Fig label={`FII ${segWord} calls, net`} value={signed(n(fii, `opt_${seg}_call_net`))}
            sub={`${sides(n(fii, `opt_${seg}_call_long_pct`), n(fii, `opt_${seg}_call_short_pct`), words)}`} />
          <Fig label={`FII ${segWord} puts, net`} value={signed(n(fii, `opt_${seg}_put_net`))}
            sub={`${sides(n(fii, `opt_${seg}_put_long_pct`), n(fii, `opt_${seg}_put_short_pct`), words)}`} />
        </div>
      )}
      {rows.length ? <ParticipantTable rows={rows} kind={kind} seg={seg} split={more.on} /> : <p className="small muted">No {kind === "oi" ? "open interest" : "volume"} file stored yet.</p>}
      <p className="tiny muted">Contracts, as the exchange counts them. {kind === "vol" ? "Volume is what each participant bought and sold that day; open interest is what they held at the close." : "Open interest is what each participant held at the close; Volume shows what they bought and sold that day."}</p>
    </Card>
  );
}

function Cash({ s }: { s: Summary }) {
  const c = s.cash;
  const cov = s.coverage?.cash;
  return (
    <Card id="pos-cash" title="FII and DII cash market"
      info="The exchange's provisional numbers for the day: what foreign portfolio investors (FII/FPI) and domestic institutions (DII) bought and sold in the cash market, in ₹ crore. Final numbers can differ a little.">
      <Source testId="cash-source">
        The exchange's provisional FII/DII figures, published each trading evening. The exchange shows only its latest day, so the history starts when StratLab began reading them{cov ? `: ${spanLine(cov)}` : ""}.
      </Source>
      <p className="small muted" data-testid="cash-status">{statusLine(c, "cash numbers")}</p>
      {c.fii && c.dii ? (
        <div className="space-figs">
          <Fig label="FII/FPI net" value={crore(c.fii.net, true)} tone={signClass(c.fii.net)} sub={`Bought ${crore(c.fii.buy)} · sold ${crore(c.fii.sell)}`} />
          <Fig label="DII net" value={crore(c.dii.net, true)} tone={signClass(c.dii.net)} sub={`Bought ${crore(c.dii.buy)} · sold ${crore(c.dii.sell)}`} />
        </div>
      ) : null}
    </Card>
  );
}

/** "Recorded since 6 Oct 2026 (12 days)" or "not recorded yet" for an index's own chain recordings. */
function recordedLine(name: string, r: Span | undefined): string {
  if (!r || !r.days) return `StratLab hasn't recorded a full day of ${name}'s chain yet; recordings are taken during market hours.`;
  return `StratLab has recorded ${name}'s chain since ${dayName(r.first)} (${r.days} trading day${r.days === 1 ? "" : "s"}).`;
}

function PcrTable({ coverage }: { coverage?: Coverage }) {
  const [rows, setRows] = useState<PcrRow[] | null | "error">(null);
  useEffect(() => { api<{ pcr: PcrRow[] }>("/trade/positioning/pcr").then((d) => setRows(d.pcr)).catch(() => setRows("error")); }, []);
  return (
    <Card id="pos-pcr" title="Put-call ratio by index"
      info="Total open interest in the nearest expiry's puts divided by its calls' (and the same for the day's volume), over the strikes read around the money. 'Near the money' counts only the 15 strikes either side, as StratLab's recordings do, so it matches the history.">
      <Source testId="pcr-source">From each index's live option chain, or StratLab's newest recording of it when the live chain is offline.</Source>
      {rows === null ? <Loading label="Reading each index's chain" />
        : rows === "error" ? <p className="small muted">The chains couldn't be read just now. Try again in a minute.</p>
        : (
      <>
      <div className="table-wrap">
        <table className="nums pos-table" data-testid="pcr-table">
          <caption className="sr-only">Put-call ratio for each index's nearest expiry</caption>
          <thead><tr><th scope="col">Index <span className="tiny muted">· expiry</span></th><th scope="col">PCR (OI)</th><th scope="col">Near the money</th><th scope="col">PCR (volume)</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} data-pcr={r.name}>
                <th scope="row">{r.name}{r.source && <span className="tiny muted pos-expiry" data-testid="pcr-expiry">{r.expiry ? shortDay(r.expiry) : "–"}</span>}</th>
                {r.source ? (
                  <>
                    <td>{ratio(r.pcr_oi)}</td><td>{ratio(r.pcr_near)}</td><td>{ratio(r.pcr_vol)}</td>
                  </>
                ) : <td colSpan={3} className="muted small" style={{ textAlign: "left", whiteSpace: "normal" }}>
                  {coverage?.chains[r.name]?.days ? `No live chain now; recorded since ${dayName(coverage.chains[r.name].first)}` : "No live chain now, and not recorded yet"}
                </td>}
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
        : !c.source ? (
          <div className="stack" style={{ gap: 6 }} data-testid="chain-empty">
            <p className="small muted">No live chain for {name} right now{c.recorded?.days ? ", and no recording from the last week." : ", and none recorded yet."}</p>
            <Source testId="chain-recorded">{recordedLine(name, c.recorded)}</Source>
          </div>
        )
        : (
          <div className="stack" style={{ gap: 14 }} data-testid="chain-facts">
            <div className="stack" style={{ gap: 2 }}>
              <p className="small muted">
                Expiry {dayName(c.expiry)} · spot {strike(c.spot)} · {c.source === "live" ? "live chain" : "recorded chain"}, {istTime(c.as_of)}
              </p>
              <Source testId="chain-recorded">{recordedLine(name, c.recorded)}</Source>
            </div>
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
const MEASURES: [string, string][] = [["fut_idx_net", "Index futures, net"], ["opt_idx_call_net", "Index calls, net"], ["opt_idx_put_net", "Index puts, net"],
  ["fut_stk_net", "Stock futures, net"], ["opt_stk_call_net", "Stock calls, net"], ["opt_stk_put_net", "Stock puts, net"]];
const SHARES: [string, string][] = [["fut_idx_long_pct", "Index futures"], ["fut_stk_long_pct", "Stock futures"]];

function useHistory<T>(kind: string, range: string, name = "NIFTY") {
  const [d, setD] = useState<{ points: T[]; recorded?: Span } | null | "error">(null);
  useEffect(() => {
    let live = true;
    api<{ points: T[]; recorded?: Span }>(`/trade/positioning/history?kind=${kind}&range=${range}&name=${name}`)
      .then((r) => live && setD(r)).catch(() => live && setD("error"));
    return () => { live = false; };
  }, [kind, range, name]);
  return d;
}

function ChartBox({ title, children, empty, emptyText, height = 200 }: { title: string; children: ReactNode; empty: boolean; emptyText?: string; height?: number }) {
  return (
    <div className="stack pos-chart" style={{ gap: 8 }}>
      <h3 className="small" style={{ fontWeight: 600 }}>{title}</h3>
      {empty ? <ChartEmpty height={height}>{emptyText ?? "Not enough stored days to draw yet."}</ChartEmpty> : children}
    </div>
  );
}

function History({ names, coverage }: { names: string[]; coverage?: Coverage }) {
  const [range, setRange] = useState("6m");
  const [who, setWho] = useState<PRow["id"]>("fii");
  const [measure, setMeasure] = useState("fut_idx_net");
  const [share, setShare] = useState("fut_idx_long_pct");
  const [name, setName] = useState(names[0] ?? "NIFTY");
  const partsH = useHistory<PartPoint>("participants", range);
  const cashH = useHistory<CashPoint>("cash", range);
  const chainH = useHistory<ChainPoint>("chain", range, name);
  const parts = partsH && partsH !== "error" ? partsH.points : partsH;
  const cash = cashH && cashH !== "error" ? cashH.points : cashH;
  const chain = chainH && chainH !== "error" ? chainH.points : chainH;
  const label = (p: { day: string }[]) => p.map((x) => dayName(x.day));
  const days = (p: { day: string }[]) => p.map((x) => x.day.slice(0, 10));
  const mlabel = MEASURES.find(([k]) => k === measure)?.[1] ?? "";
  const slabel = SHARES.find(([k]) => k === share)?.[1] ?? "";
  const whoName = PARTICIPANTS.find(([k]) => k === who)?.[1] ?? "";
  return (
    <Card id="pos-history" title="History" info="The stored days: the exchange's participant files from its archives and each evening since, the cash numbers from the day StratLab started reading them, and the option-chain facts from StratLab's own recordings (the nearest expiry with at least a day to go, over the 15 strikes either side of the money).">
      {coverage && (
        <Source testId="history-source">
          Participant files: {spanLine(coverage.participants)}. Cash numbers: {spanLine(coverage.cash)}. Option chains: StratLab's own recordings, one summary a day.
        </Source>
      )}
      <div className="row wrap" style={{ gap: 8 }}>
        <Seg label="Time range" value={range} onChange={setRange} options={RANGES as [string, string][]} />
        <Seg label="Participant" value={who} onChange={setWho} options={PARTICIPANTS} />
      </div>
      {parts === null || cash === null ? <Loading label="Reading the history" />
        : parts === "error" || cash === "error" ? <p className="small muted">The history couldn't be read just now.</p>
        : (
          <div className="stack" style={{ gap: 22 }}>
            <div className="grid2" style={{ gap: 18 }}>
              <div className="stack" style={{ gap: 8 }}>
                <label className="field" style={{ maxWidth: 240 }}>
                  <span className="sr-only">Measure</span>
                  <select value={measure} onChange={(e) => setMeasure(e.target.value)} aria-label="Measure">
                    {MEASURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </label>
                <ChartBox title={`${whoName}: ${mlabel.toLowerCase()} (contracts)`} empty={parts.length < 2} height={220}>
                  <LineChart lines={[{ values: parts.map((p) => p[who as "fii"]?.[measure] ?? null), color: "var(--pos-call)", width: 2, label: mlabel }]}
                    labels={label(parts)} times={days(parts)} sync="pos-history" ranges={false} format={contracts} axisFormat={contractsShort} baseline={0} height={220}
                    ariaLabel={`${whoName} ${mlabel} by day`} />
                </ChartBox>
              </div>
              <div className="stack" style={{ gap: 8 }}>
                <Seg label="Long share of" value={share} onChange={setShare} options={SHARES} />
                <ChartBox title={`${whoName}: ${slabel.toLowerCase()}, long share (% of long + short)`} empty={parts.length < 2} height={220}>
                  <LineChart lines={[{ values: parts.map((p) => p[who as "fii"]?.[share] ?? null), color: "var(--pos-call)", width: 2, label: "Long share" }]}
                    labels={label(parts)} times={days(parts)} sync="pos-history" ranges={false} format={(v) => `${v.toFixed(1)}% long · ${(100 - v).toFixed(1)}% short`}
                    axisFormat={(v) => `${v.toFixed(0)}%`} height={220} ariaLabel={`${whoName} ${slabel} long share by day`} />
                </ChartBox>
              </div>
            </div>
            <ChartBox title="Cash market, net (₹ crore)" empty={cash.length < 2}
              emptyText={`${cash.length ? "One day" : "No days"} stored so far: the exchange shows only its latest day, so this chart grows a day at a time from when StratLab started reading the numbers.`}>
              <LineChart lines={[{ values: cash.map((p) => p.fii), color: "var(--pos-call)", width: 2, label: "FII/FPI" },
                { values: cash.map((p) => p.dii), color: "var(--pos-put)", width: 2, label: "DII" }]}
                labels={label(cash)} times={days(cash)} sync="pos-history" ranges={false} legend format={(v) => crore(v, true)} axisFormat={(v) => contractsShort(v)} baseline={0} height={200}
                ariaLabel="FII and DII net cash market flows by day" />
            </ChartBox>
            <div className="stack" style={{ gap: 8 }}>
              <Seg label="Index for the chain history" value={name} onChange={setName} options={names.map((x) => [x, x] as [string, string])} />
              {chain === null || chainH === null ? <Loading label={`Reading ${name}'s recorded days`} />
                : chain === "error" || chainH === "error" ? <p className="small muted">The recorded days couldn't be read.</p>
                : (
                  <>
                    <Source testId="chain-history-source">{recordedLine(name, chainH.recorded)}</Source>
                    <div className="grid2" style={{ gap: 18 }}>
                      <ChartBox title={`${name} PCR, near the money`} empty={chain.length < 2} emptyText={`Not enough recorded days of ${name} to draw yet.`}>
                        <LineChart lines={[{ values: chain.map((p) => p.pcr_oi), color: "var(--pos-call)", width: 2, label: "Open interest" },
                          { values: chain.map((p) => p.pcr_vol), color: "var(--pos-put)", width: 2, label: "Volume" }]}
                          labels={label(chain)} times={days(chain)} sync="pos-history" ranges={false} legend format={ratio} height={200} ariaLabel={`${name} put-call ratio by day`} />
                      </ChartBox>
                      <ChartBox title={`${name} ATM implied volatility (%)`} empty={chain.length < 2} emptyText={`Not enough recorded days of ${name} to draw yet.`}>
                        <LineChart lines={[{ values: chain.map((p) => p.atm_iv), color: "var(--pos-call)", width: 2, label: "ATM IV" }]}
                          labels={label(chain)} times={days(chain)} sync="pos-history" ranges={false} format={(v) => `${v.toFixed(1)}%`} height={200} ariaLabel={`${name} at-the-money IV by day`} />
                      </ChartBox>
                    </div>
                  </>
                )}
            </div>
          </div>
        )}
    </Card>
  );
}

function Locked({ plan, coverage }: { plan: string; coverage?: Coverage }) {
  return (
    <section className="card stack" style={{ gap: 10 }} data-testid="pos-locked" id="pos-history">
      <h2 className="h3">History</h2>
      <p className="small muted">
        Charts of each participant's positions and long / short shares by day, the FII and DII cash flows, each index's PCR and ATM IV by day, and where today's IV sits among the recorded days, are on the {plan} plan.
        {coverage?.participants.days ? ` ${spanLine(coverage.participants)} of participant files are stored.` : ""} Today's numbers above are on every plan.
      </p>
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
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Trade · derivatives</span>
        <h1 className="page-title">Positioning</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>Who holds index and stock futures and options, FII and DII cash flows, India VIX, and what the index option chains show. The exchange's numbers as published: facts, not advice.</p>
      </div>
      {error ? <div className="banner">{error}</div>
        : !s ? <Loading label="Reading the newest numbers" />
        : (
          <>
            <Participants s={s} />
            <VixPanel />
            <div className="grid2" style={{ alignItems: "start" }}>
              <Cash s={s} />
              <PcrTable coverage={s.coverage} />
            </div>
            {s.full ? <History names={s.names} coverage={s.coverage} /> : <Locked plan={s.plan_needed} coverage={s.coverage} />}
            <Chain names={s.names} full={s.full} plan={s.plan_needed} />
            <p className="tiny muted">{s.note}</p>
          </>
        )}
    </div>
  );
}

export default PositioningPage;
