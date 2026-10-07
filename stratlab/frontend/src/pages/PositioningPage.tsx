import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import {
  contracts, contractsShort, crore, dayName, istTime, PARTICIPANTS, pct, RANGES, ratio, shortDay, sides, signed, spanLine, statusLine, strike,
  type CashPoint, type ChainFacts, type ChainPoint, type Coverage, type PartPoint, type PcrRow, type PRow, type Span, type Summary,
} from "../lib/positioning";
import { spanCheck, spanDays, SPAN_UNITS } from "../lib/intervals";
import { ChartEmpty, Legend, LineChart } from "../components/Charts";
import { StrikeChart } from "../components/StrikeChart";
import { useMoreColumns } from "../components/MoreColumns";
import { VixPanel } from "../components/VixPanel";
import { Card, CardHead, ChipBar, DataTable, Disclosure, EmptyState, ErrorState, Field, FieldGroup, PageHeader, Seg, Select, Skeleton, Stat, StatRow, type Column } from "../components/kit";
import { PosTabs } from "./trade/StockFuturesPage";
import "./trade/trade.css";
import "./trade/positioning.css";

/* /trade/positioning: who holds index futures and options (the exchange's participant-wise files), FII and DII cash
 * flows, each index's put-call ratio, and one index's option chain as facts: open interest and its change by strike,
 * max pain, the strikes with the most open interest and the at-the-money IV. Today's numbers on every plan; the
 * history and the IV percentile and rank on Basic. Nothing here reads the numbers as a signal. Built from the kit. */

/** A thin bar with the first share filled, as a picture (no inline width). */
export function PosBar({ long }: { long: number }) {
  return (
    <svg className="pos-bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">
      <rect className="bg" width="100" height="8" rx="4" /><rect className="fg" width={Math.max(0, Math.min(100, long))} height="8" rx="4" />
    </svg>
  );
}

const n = (r: PRow, k: string) => (r[k] as number | null | undefined) ?? null;

/** A change under a number, in plain words: no colour, since a rise in a position is neither good nor bad news. */
function Chg({ v }: { v: number | null }) {
  return v == null ? null : <span className="k-sub-line">{signed(v)}</span>;
}

type Segment = "idx" | "stk";
const SEG_WORD: Record<Segment, string> = { idx: "index", stk: "stock" };

/** One source line under a section's title: where the numbers come from, and how much is stored. */
function Source({ children, testId }: { children: ReactNode; testId?: string }) {
  return <p className="k-note pos-source" data-testid={testId}>{children}</p>;
}

/** Long against short as a thin bar (the long side dark), with the two shares written out beside it. */
function Split({ long, short, words }: { long: number | null; short: number | null; words: [string, string] }) {
  if (long == null || short == null) return <>–</>;
  return (
    <span className="pos-split" title={sides(long, short, words)}>
      <PosBar long={long} />
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
  const cell = ([k, l]: [string, string]): Column<PRow> => ({
    key: k, header: l, numeric: true,
    cell: (r) => <>{k.endsWith("_net") ? signed(n(r, k)) : contracts(n(r, k))}<Chg v={n(r, `${k}_chg`)} /></>,
  });
  const columns: Column<PRow>[] = [
    { key: "who", header: `${seg === "idx" ? "Index" : "Stock"} F&O`, rowHeader: true, cell: (r) => <b>{r.label}</b> },
    ...cols.slice(0, 3).map(cell),
    ...(split ? [{ key: "split", header: `Futures ${lo} / ${sh}`, numeric: true, cell: (r: PRow) => <span data-testid={`split-${r.id}`}><Split long={n(r, `fut_${seg}_long_pct`)} short={n(r, `fut_${seg}_short_pct`)} words={[lo, sh]} /></span> }] : []),
    ...cols.slice(3).map(cell),
  ];
  return (
    <div data-testid="part-table" data-segment={seg}>
      <DataTable label={`${what[0].toUpperCase()}${what.slice(1)} by participant, in contracts`} columns={columns} rows={rows} rowKey={(r) => r.id}
        rowAttrs={(r) => ({ "data-participant": r.id })} />
    </div>
  );
}

/** "+1.2 pts from the day before" for a change in a share. */
const pts = (v: number) => `Long share ${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts from the day before`;

/** A figure with both sides written out, one to a line ("19.3% long", "80.7% short"), the bar under them. */
function SidesFig({ label, long, short, words, chg }: { label: string; long: number | null; short: number | null; words: [string, string]; chg: number | null }) {
  return (
    <div className="k-stat" data-testid="sides-fig">
      <span className="k-stat-k">{label}</span>
      {long == null || short == null ? <span className="k-stat-v">–</span> : (
        <span className="k-stat-v pos-sides"><span>{pct(long)} {words[0]}</span><span>{pct(short)} {words[1]}</span>
          <PosBar long={long} /></span>
      )}
      {chg != null && <span className="k-stat-d">{pts(chg)}</span>}
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
    <Card id="pos-part" label="Participant-wise open interest">
      <CardHead title="Participant-wise open interest" infoLabel="About participant-wise open interest"
        info="The exchange's daily count of futures and options contracts each kind of participant held open (or traded that day), long and short, for index and for stock contracts. Clients are individuals and firms trading for themselves; DIIs are domestic institutions (mutual funds, insurers, banks); FIIs are foreign portfolio investors; Pro is brokers trading their own money. Long / short is each side's share of the futures held. The small line under each number is the change from the trading day before."
        actions={<>
          <Seg label="Index or stock contracts" value={seg} onChange={(v) => setSeg(v as Segment)} options={[{ value: "idx", label: "Index F&O" }, { value: "stk", label: "Stock F&O" }]} />
          <Seg label="Open interest or volume" value={kind} onChange={(v) => setKind(v as "oi" | "vol")} options={[{ value: "oi", label: "Open interest" }, { value: "vol", label: "Volume" }]} />
          {rows.length > 0 && more.toggle}
        </>} />
      <Source testId="part-source">
        From the exchange's end-of-day participant-wise file, published each trading evening.{" "}
        {cov ? <>Covers {spanLine(cov)}{cov.backfill_done ? "." : `, still filling in the past ${Math.round(cov.backfill_target / 30.4)} months.`}</> : null}
        {s.full && cov && cov.days > 1 ? <> <a className="link" href="#pos-history">See the history</a>.</> : null}
      </Source>
      <p className="k-small k-muted" data-testid="part-status">{statusLine(p, "participant files")}{p.prev ? ` Changes are from ${dayName(p.prev)}.` : ""}</p>
      {fii && (
        <div data-testid="part-figs">
          <StatRow label="FII figures">
            <Stat label={`FII ${segWord} futures, net`} value={signed(n(fii, `fut_${seg}_net`))} note={`${signed(n(fii, `fut_${seg}_net_chg`))} from the day before`} />
            <SidesFig label={`FII ${segWord} futures, ${words.join(" · ")}`} long={n(fii, `fut_${seg}_long_pct`)} short={n(fii, `fut_${seg}_short_pct`)} words={words}
              chg={kind === "oi" ? n(fii, `fut_${seg}_long_pct_chg`) : null} />
            <Stat label={`FII ${segWord} calls, net`} value={signed(n(fii, `opt_${seg}_call_net`))}
              note={`${sides(n(fii, `opt_${seg}_call_long_pct`), n(fii, `opt_${seg}_call_short_pct`), words)}`} />
            <Stat label={`FII ${segWord} puts, net`} value={signed(n(fii, `opt_${seg}_put_net`))}
              note={`${sides(n(fii, `opt_${seg}_put_long_pct`), n(fii, `opt_${seg}_put_short_pct`), words)}`} />
          </StatRow>
        </div>
      )}
      {rows.length ? <ParticipantTable rows={rows} kind={kind} seg={seg} split={more.on} /> : <EmptyState title={`No ${kind === "oi" ? "open interest" : "volume"} file stored yet`}>It appears here once the exchange's file for a trading day is read.</EmptyState>}
      <p className="k-note">Contracts, as the exchange counts them. {kind === "vol" ? "Volume is what each participant bought and sold that day; open interest is what they held at the close." : "Open interest is what each participant held at the close; Volume shows what they bought and sold that day."}</p>
    </Card>
  );
}

function Cash({ s }: { s: Summary }) {
  const c = s.cash;
  const cov = s.coverage?.cash;
  return (
    <Card id="pos-cash" label="FII and DII cash market">
      <CardHead title="FII and DII cash market" infoLabel="About the cash market figures"
        info="The exchange's provisional numbers for the day: what foreign portfolio investors (FII/FPI) and domestic institutions (DII) bought and sold in the cash market, in ₹ crore. Final numbers can differ a little." />
      <Source testId="cash-source">
        The exchange's provisional FII/DII figures, published each trading evening. The exchange shows only its latest day, so the history starts when StratLab began reading them{cov ? `: ${spanLine(cov)}` : ""}.
      </Source>
      <p className="k-small k-muted" data-testid="cash-status">{statusLine(c, "cash numbers")}</p>
      {c.fii && c.dii ? (
        <StatRow label="Cash market, net">
          <Stat label="FII/FPI net" value={crore(c.fii.net, true)} note={`Bought ${crore(c.fii.buy)} · sold ${crore(c.fii.sell)}`} />
          <Stat label="DII net" value={crore(c.dii.net, true)} note={`Bought ${crore(c.dii.buy)} · sold ${crore(c.dii.sell)}`} />
        </StatRow>
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
  const [again, setAgain] = useState(0);
  useEffect(() => { setRows(null); api<{ pcr: PcrRow[] }>("/trade/positioning/pcr").then((d) => setRows(d.pcr)).catch(() => setRows("error")); }, [again]);
  const cols: Column<PcrRow>[] = [
    { key: "name", header: <>Index <span className="k-note">· expiry</span></>, rowHeader: true, cell: (r) => <>{r.name}{r.source && <span className="k-sub-line" data-testid="pcr-expiry">{r.expiry ? `${shortDay(r.expiry)}${r.cycle ? ` · ${r.cycle}` : ""}` : "–"}</span>}</> },
    { key: "oi", header: "PCR (OI)", numeric: true, cell: (r) => ratio(r.pcr_oi) },
    { key: "near", header: "Near the money", numeric: true, cell: (r) => ratio(r.pcr_near) },
    { key: "vol", header: "PCR (volume)", numeric: true, cell: (r) => ratio(r.pcr_vol) },
  ];
  return (
    <Card id="pos-pcr" label="Put-call ratio by index">
      <CardHead title="Put-call ratio by index" infoLabel="About the put-call ratio"
        info="Total open interest in the nearest expiry's puts divided by its calls' (and the same for the day's volume), over the strikes read around the money. 'Near the money' counts only the 15 strikes either side, as StratLab's recordings do, so it matches the history." />
      <Source testId="pcr-source">From each index's live option chain, or StratLab's newest recording of it when the live chain is offline.</Source>
      {rows === null ? <Skeleton label="Reading each index's chain" />
        : rows === "error" ? <ErrorState title="The chains couldn't be read just now" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Try again in a minute.</ErrorState>
        : (
      <>
      <div data-testid="pcr-table">
        <DataTable label="Put-call ratio for each index's nearest expiry" columns={cols} rows={rows} rowKey={(r) => r.name} rowAttrs={(r) => ({ "data-pcr": r.name })}
          rowNote={(r) => (r.source ? undefined : coverage?.chains[r.name]?.days ? `No live chain now; recorded since ${dayName(coverage.chains[r.name].first)}` : "No live chain now, and not recorded yet")} />
      </div>
      <p className="k-note">{rows.some((r) => r.source === "recorded") ? "Where the live chain is offline, the newest recording is shown. " : ""}Live chains are read at most once a minute.</p>
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
  const [again, setAgain] = useState(0);
  useEffect(() => {
    let live = true;
    setC(null);
    api<ChainFacts>(`/trade/positioning/chain?name=${name}&expiry=${expiry}`).then((d) => live && setC(d)).catch(() => live && setC("error"));
    return () => { live = false; };
  }, [name, expiry, again]);
  const hasChg = c && c !== "error" && c.rows.some((r) => r.call_chg != null || r.put_chg != null);
  type CR = ChainFacts["rows"][number];
  const rowCols: Column<CR>[] = c && c !== "error" ? [
    { key: "k", header: "Strike", rowHeader: true, cell: (r) => strike(r.strike) },
    { key: "co", header: "Call OI", numeric: true, cell: (r) => contracts(r.call_oi) }, { key: "cc", header: "Change", numeric: true, cell: (r) => signed(r.call_chg) },
    { key: "cv", header: "Call volume", numeric: true, cell: (r) => contracts(r.call_vol) },
    { key: "po", header: "Put OI", numeric: true, cell: (r) => contracts(r.put_oi) }, { key: "pc", header: "Change", numeric: true, cell: (r) => signed(r.put_chg) },
    { key: "pv", header: "Put volume", numeric: true, cell: (r) => contracts(r.put_vol) },
  ] : [];
  return (
    <Card id="pos-chain" label="Option chain facts">
      <CardHead title="Option chain facts" infoLabel="About the option chain facts"
        info="From the index's option chain: open interest by strike and its change since the last recording of the trading day before; the max-pain strike (where the open options would be worth the least in total at expiry); the strikes with the most call and put open interest; and the at-the-money implied volatility, worked out from the at-the-money call and put with Black's formula, the forward from put-call parity and no interest rate."
        actions={<>
          <ChipBar label="Index" value={name} onChange={setName} options={names.map((x) => ({ value: x, label: x }))} />
          <Seg label="Expiry" value={expiry} onChange={setExpiry} options={[{ value: "current", label: "Nearest expiry" }, { value: "next", label: "Next" }]} />
        </>} />
      {c === null ? <Skeleton label={`Reading ${name}'s chain`} />
        : c === "error" ? <ErrorState title="The chain couldn't be read just now" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Try again in a minute.</ErrorState>
        : !c.source ? (
          <div className="k-stack k-tight" data-testid="chain-empty">
            <p className="k-small k-muted">No live chain for {name} right now{c.recorded?.days ? ", and no recording from the last week." : ", and none recorded yet."}</p>
            <Source testId="chain-recorded">{recordedLine(name, c.recorded)}</Source>
          </div>
        )
        : (
          <div className="k-stack" data-testid="chain-facts">
            <div className="k-stack k-tight">
              <p className="k-small k-muted">
                Expiry {dayName(c.expiry)} · spot {strike(c.spot)} · {c.source === "live" ? "live chain" : "recorded chain"}, {istTime(c.as_of)}
              </p>
              <Source testId="chain-recorded">{recordedLine(name, c.recorded)}</Source>
            </div>
            <StatRow label="Option chain figures">
              <Stat label="PCR (open interest)" value={ratio(c.pcr?.oi)} note={`Near the money ${ratio(c.pcr_near)} · volume ${ratio(c.pcr?.vol)}`} />
              <Stat label="Max-pain strike" value={strike(c.max_pain)} />
              <Stat label="Most call open interest" value={strike(c.top?.call?.strike)} note={c.top?.call ? `${contracts(c.top.call.oi)} contracts` : undefined} />
              <Stat label="Most put open interest" value={strike(c.top?.put?.strike)} note={c.top?.put ? `${contracts(c.top.put.oi)} contracts` : undefined} />
              <Stat label="ATM implied volatility" value={c.atm_iv == null ? "–" : `${c.atm_iv.toFixed(1)}%`} note={c.atm ? `At the ${strike(c.atm)} strike` : undefined} />
              <IvFig c={c} full={full} plan={plan} />
            </StatRow>
            <div className="k-spread">
              <Seg label="Open interest or its change" value={mode} onChange={(v) => setMode(v as "oi" | "chg")} options={[{ value: "oi", label: "Open interest" }, { value: "chg", label: "Change" }]} />
              <Legend items={[{ label: "Calls", color: "var(--pos-call)" }, { label: "Puts", color: "var(--pos-put)" }]} />
            </div>
            {mode === "chg" && !hasChg ? (
              <p className="k-small k-muted">No recording of this expiry from the trading day before, so there's no change to show yet.</p>
            ) : (
              <StrikeChart rows={c.rows} mode={mode} spot={c.spot} label={`${name} ${mode === "oi" ? "open interest" : "change in open interest"} by strike, calls and puts`} />
            )}
            {c.change_from && <p className="k-note">Change since the recording of {istTime(c.change_from)}.</p>}
            <Disclosure summary="Show the strikes as a table">
              <DataTable label={`${name} open interest, change and volume by strike`} columns={rowCols} rows={[...c.rows].reverse()} rowKey={(r) => String(r.strike)}
                rowAttrs={(r): Record<string, string> => (r.strike === c.atm ? { "data-atm": "1" } : {})} />
            </Disclosure>
            <p className="k-note">The PCR, max pain and the top strikes count the {c.strikes_counted ?? c.rows.length} strikes read around the money; the chart shows the 41 nearest. {c.note}</p>
          </div>
        )}
    </Card>
  );
}

function IvFig({ c, full, plan }: { c: ChainFacts; full: boolean; plan: string }) {
  if (!full) return <Stat label="IV percentile and rank" value={<Link to="/plans" className="link k-small">{plan} plan</Link>} note="Over StratLab's recorded days" />;
  const s = c.iv;
  if (!s || s.percentile == null)
    return <Stat label="IV percentile and rank" value="–" note={s ? `${s.days} of ${s.need} recorded days needed so far` : undefined} />;
  return <Stat label="IV percentile · rank" value={`${s.percentile.toFixed(0)} · ${s.rank == null ? "–" : s.rank.toFixed(0)}`}
    note={`Over ${s.days} recorded days (${s.low?.toFixed(1)}%–${s.high?.toFixed(1)}%)`} />;
}

/* ---------- history (Basic) ---------- */
const MEASURES: [string, string][] = [["fut_idx_net", "Index futures, net"], ["opt_idx_call_net", "Index calls, net"], ["opt_idx_put_net", "Index puts, net"],
  ["fut_stk_net", "Stock futures, net"], ["opt_stk_call_net", "Stock calls, net"], ["opt_stk_put_net", "Stock puts, net"]];
const SHARES: [string, string][] = [["fut_idx_long_pct", "Index futures"], ["fut_stk_long_pct", "Stock futures"]];
const API_RANGES = ["3m", "6m", "1y", "all"];

/** The stored history for a range. The server knows 3 months, 6 months, a year and all: a custom range reads all of it and
 * keeps the days inside the range here. */
function useHistory<T extends { day: string }>(kind: string, range: string, name = "NIFTY") {
  const [d, setD] = useState<{ points: T[]; recorded?: Span } | null | "error">(null);
  const custom = spanDays(range);
  const key = API_RANGES.includes(range) ? range : "all";
  useEffect(() => {
    let live = true;
    api<{ points: T[]; recorded?: Span }>(`/trade/positioning/history?kind=${kind}&range=${key}&name=${name}`)
      .then((r) => {
        if (!live) return;
        if (custom == null) { setD(r); return; }
        const from = new Date(Date.now() - custom * 86400_000).toISOString().slice(0, 10);
        setD({ ...r, points: r.points.filter((p) => p.day.slice(0, 10) >= from) });
      }).catch(() => live && setD("error"));
    return () => { live = false; };
  }, [kind, key, custom, name]);
  return d;
}

function ChartBox({ title, children, empty, emptyText, height = 200 }: { title: string; children: ReactNode; empty: boolean; emptyText?: string; height?: number }) {
  return (
    <div className="k-stack pos-chart">
      <h3 className="k-sub">{title}</h3>
      {empty ? <ChartEmpty height={height}>{emptyText ?? "Not enough days yet to draw."}</ChartEmpty> : children}
    </div>
  );
}

function History({ names, coverage }: { names: string[]; coverage?: Coverage }) {
  const { me } = useApp();
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
  const stored = coverage?.participants.days ?? 3650;
  return (
    <Card id="pos-history" label="History">
      <CardHead title="History" infoLabel="About the history"
        info="The days covered: the exchange's participant files from its archives and each evening since, the cash numbers from the day StratLab started reading them, and the option-chain facts from StratLab's own recordings (the nearest expiry with at least a day to go, over the 15 strikes either side of the money). A custom range can be any whole number of days, weeks, months or years up to the days stored."
        actions={<ChipBar label="Time range" value={range} onChange={setRange} options={RANGES.map(([value, label]) => ({ value, label }))}
          custom={{ storageKey: `stratlab.chips.positioning.${me?.id ?? "anon"}`, units: SPAN_UNITS, defaultUnit: "months", validate: spanCheck(Math.max(30, stored + 30), 5) }} />} />
      {coverage && (
        <Source testId="history-source">
          Participant files: {spanLine(coverage.participants)}. Cash numbers: {spanLine(coverage.cash)}. Option chains: StratLab's own recordings, one summary a day.
        </Source>
      )}
      <ChipBar label="Participant" value={who} onChange={(v) => setWho(v as PRow["id"])} options={PARTICIPANTS.map(([value, label]) => ({ value, label }))} />
      {parts === null || cash === null ? <Skeleton label="Reading the history" />
        : parts === "error" || cash === "error" ? <ErrorState title="The history couldn't be read just now">Try again in a minute.</ErrorState>
        : (
          <div className="k-stack">
            <div className="k-two">
              <div className="k-stack">
                <Field label="Measure">{(id) => <Select id={id} value={measure} onChange={setMeasure} options={MEASURES.map(([value, label]) => ({ value, label }))} />}</Field>
                <ChartBox title={`${whoName}: ${mlabel.toLowerCase()} (contracts)`} empty={parts.length < 2} height={220}>
                  <LineChart lines={[{ values: parts.map((p) => p[who as "fii"]?.[measure] ?? null), color: "var(--pos-call)", width: 2, label: mlabel }]}
                    labels={label(parts)} times={days(parts)} sync="pos-history" ranges={false} format={contracts} axisFormat={contractsShort} baseline={0} height={220}
                    ariaLabel={`${whoName} ${mlabel} by day`} />
                </ChartBox>
              </div>
              <div className="k-stack">
                <FieldGroup label="Long share of"><Seg label="Long share of" value={share} onChange={setShare} options={SHARES.map(([value, label]) => ({ value, label }))} /></FieldGroup>
                <ChartBox title={`${whoName}: ${slabel.toLowerCase()}, long share (% of long + short)`} empty={parts.length < 2} height={220}>
                  <LineChart lines={[{ values: parts.map((p) => p[who as "fii"]?.[share] ?? null), color: "var(--pos-call)", width: 2, label: "Long share" }]}
                    labels={label(parts)} times={days(parts)} sync="pos-history" ranges={false} format={(v) => `${v.toFixed(1)}% long · ${(100 - v).toFixed(1)}% short`}
                    axisFormat={(v) => `${v.toFixed(0)}%`} height={220} ariaLabel={`${whoName} ${slabel} long share by day`} />
                </ChartBox>
              </div>
            </div>
            <ChartBox title="Cash market, net (₹ cr)" empty={cash.length < 2}
              emptyText={`${cash.length ? "One day" : "No days"} so far: the exchange shows only its latest day, so this chart grows a day at a time from when StratLab started reading the numbers.`}>
              <LineChart lines={[{ values: cash.map((p) => p.fii), color: "var(--pos-call)", width: 2, label: "FII/FPI" },
                { values: cash.map((p) => p.dii), color: "var(--pos-put)", width: 2, label: "DII" }]}
                labels={label(cash)} times={days(cash)} sync="pos-history" ranges={false} legend format={(v) => crore(v, true)} axisFormat={(v) => contractsShort(v)} baseline={0} height={200}
                ariaLabel="FII and DII net cash market flows by day" />
            </ChartBox>
            <div className="k-stack">
              <ChipBar label="Index for the chain history" value={name} onChange={setName} options={names.map((x) => ({ value: x, label: x }))} />
              {chain === null || chainH === null ? <Skeleton label={`Reading ${name}'s recorded days`} />
                : chain === "error" || chainH === "error" ? <p className="k-small k-muted">The recorded days couldn't be read.</p>
                : (
                  <>
                    <Source testId="chain-history-source">{recordedLine(name, chainH.recorded)}</Source>
                    <div className="k-two">
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
    <Card id="pos-history" testId="pos-locked" label="History">
      <CardHead title="History" />
      <p className="k-small k-muted">
        Charts of each participant's positions and long / short shares by day, the FII and DII cash flows, each index's PCR and ATM IV by day, and where today's IV sits among the recorded days, are on the {plan} plan.
        {coverage?.participants.days ? ` ${spanLine(coverage.participants)} of participant files are kept.` : ""} Today's numbers above are on every plan.
      </p>
      <Link to="/plans" className="btn sm k-btn-end">See the {plan} plan</Link>
    </Card>
  );
}

export function PositioningPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  useEffect(() => {
    setError(null);
    api<Summary>("/trade/positioning?pcr=false").then(setS).catch((e) => setError(e instanceof ApiError ? e.message : "The positioning numbers couldn't be read."));
  }, [again]);
  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · F&O desk" title="Positioning"
        lede="Who holds index and stock futures and options, FII and DII cash flows, India VIX, and what the index option chains show. The exchange's numbers as published: facts, not advice."
        actions={<PosTabs />} />
      {error ? <ErrorState title="The positioning numbers couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !s ? <Card><Skeleton label="Reading the newest numbers" /></Card>
        : (
          <>
            <Participants s={s} />
            <VixPanel />
            <div className="k-two">
              <Cash s={s} />
              <PcrTable coverage={s.coverage} />
            </div>
            {s.full ? <History names={s.names} coverage={s.coverage} /> : <Locked plan={s.plan_needed} coverage={s.coverage} />}
            <Chain names={s.names} full={s.full} plan={s.plan_needed} />
            <p className="k-note">{s.note}</p>
          </>
        )}
    </div>
  );
}

export default PositioningPage;
