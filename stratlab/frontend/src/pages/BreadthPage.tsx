import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import {
  RANGES, breadthApi, count, delta, savePick, savedPick, share, shortDay,
  type BreadthAlerts, type BreadthView, type Group, type GroupId, type History, type RangeId, type SectorTable, type Today,
} from "../lib/breadth";
import { ResearchNav, Panel } from "../components/Research";
import { LineChart, PairBars } from "../components/Charts";
import { AsOf, Info, Loading } from "../components/ui";

/* Market breadth: how many stocks in a group take part in the market's moves. Today's numbers for everyone; the
 * history as small charts (one measure each, never two scales on one chart) on Basic and up. Facts only. */

const A = "var(--bx-a)", B = "var(--bx-b)";
const fmt1 = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 1 });
const fmtPct = (v: number) => `${v.toFixed(1)}%`;
const fmtInt = (v: number) => Math.round(v).toLocaleString("en-IN");

export function BreadthPage() {
  const { fail } = useApp();
  const first = savedPick();
  const [group, setGroup] = useState<GroupId>(first.group);
  const [range, setRange] = useState<RangeId>(first.range);
  const [data, setData] = useState<BreadthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const n = ++seq.current;
    setLoading(true);
    savePick(group, range);
    breadthApi.get(group, range)
      .then((d) => { if (n === seq.current) { setData(d); setError(null); } })
      .catch((e) => {
        if (n !== seq.current) return;
        if ((e as { status?: number }).status === 404 && group !== "nifty500") { setGroup("nifty500"); return; }   // a group no longer offered
        setError((e as Error).message);
        fail(e);
      })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [group, range, fail]);

  const help = data?.help ?? {};
  const g = data?.group;
  return (
    <div className="stack breadth" style={{ gap: 24 }}>
      <ResearchNav region={g?.region ?? "IN"} />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Scans · {g?.region === "US" ? "United States" : "India"}</span>
        <h1 className="page-title">Market breadth</h1>
        <p className="page-sub">How many stocks in a group rose or fell, sit above their averages, or made new highs and lows, day by day,
          from daily closes. Every stock counts once: facts about what happened, not a forecast.</p>
      </div>

      <div className="row wrap bx-filters" style={{ gap: 10, alignItems: "center" }}>
        <span className="chip-select"><select aria-label="Group of stocks" value={group} onChange={(e) => setGroup(e.target.value as GroupId)}>
          {(["IN", "US"] as const).map((r) => (
            <optgroup key={r} label={r === "IN" ? "India" : "United States"}>
              {(data?.groups ?? []).filter((x) => x.region === r).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              {!data && r === "IN" && <option value={group}>Loading…</option>}
            </optgroup>
          ))}
        </select></span>
        {data && !data.locked && (
          <div className="seg" role="radiogroup" aria-label="Time range">
            {RANGES.map(([id, label]) => (
              <button key={id} role="radio" aria-checked={range === id} aria-pressed={range === id} onClick={() => setRange(id)}>{label}</button>
            ))}
          </div>
        )}
        {help.members && <span className="small muted row" style={{ gap: 0 }}>Who is counted<Info label="Which stocks are counted">{help.members}</Info></span>}
      </div>

      {!data && loading ? <Loading label="Counting the market" />
        : !data ? <p className="small muted">{error ?? "Market breadth couldn't be opened just now."}</p>
        : (
          <div className="stack" style={{ gap: 24, opacity: loading ? 0.55 : 1, transition: "opacity .15s" }} aria-busy={loading}>
            {!data.today ? (
              <div className="card stack" style={{ gap: 6 }} data-testid="breadth-empty">
                <b>No counts for {data.group.name} yet</b>
                <span className="small muted">Breadth is worked out after each market's close; the first run reads about two years of prices, so it takes a while. Check back after the next close.</span>
              </div>
            ) : (
              <>
                <Headline t={data.today} help={help} />
                <AsOf parts={[["Prices", data.as_of]]} />
                {data.locked ? (
                  <div className="banner" data-testid="breadth-locked">
                    <span>Today's numbers are on every plan. The history, charts and the sector table are on the {data.plan_needed} plan.</span>
                    <Link to="/plans" className="btn sm">See plans</Link>
                  </div>
                ) : data.history && <>
                  <AlertBox group={data.group} />
                  <Charts data={data} h={data.history} help={help} />
                </>}
              </>
            )}
          </div>
        )}
    </div>
  );
}

/* ---------- today's numbers ---------- */
function Tile({ label, info, value, sub, change }: { label: string; info?: string; value: ReactNode; sub?: ReactNode; change?: string }) {
  return (
    <div className="card bx-tile">
      <span className="small muted row" style={{ gap: 0 }}>{label}{info && <Info label={`About ${label.toLowerCase()}`}>{info}</Info>}</span>
      <b className="bx-value">{value}</b>
      {sub && <span className="tiny muted">{sub}</span>}
      {change && <span className="tiny muted">{change}</span>}
    </div>
  );
}

function Headline({ t, help }: { t: Today; help: Record<string, string> }) {
  const vs = t.prev_day ? ` vs ${shortDay(t.prev_day)}` : "";
  const pts = (k: "pct20" | "pct50" | "pct200" | "stage2") => (t[k].change == null ? undefined : `${delta(t[k].change, "pts", 1)}${vs}`);
  // two counts: the day before's pair, which reads more plainly than two signed changes
  const pair = (a: keyof Today, b: keyof Today) => {
    const x = t[a] as Today["adv"], y = t[b] as Today["adv"];
    if (!t.prev_day || (x.prev == null && y.prev == null)) return undefined;
    return x.change === 0 && y.change === 0 ? `Same as ${shortDay(t.prev_day)}` : `${shortDay(t.prev_day)}: ${count(x.prev)} / ${count(y.prev)}`;
  };
  return (
    <section className="bx-tiles" aria-label={`Breadth on ${shortDay(t.day)}`} data-testid="breadth-today">
      <Tile label="Rose / fell" info={help.ad} value={<>{count(t.adv.value)} <span className="muted">/</span> {count(t.dec.value)}</>}
        sub={`Ratio ${t.ad_ratio.value == null ? "–" : t.ad_ratio.value.toFixed(2)} · ${count(t.unch.value)} unchanged · ${count(t.stocks.value)} stocks`} change={pair("adv", "dec")} />
      <Tile label="Above 50-day average" info={help.ma} value={share(t.pct50.value)} sub={`20-day: ${share(t.pct20.value)}`} change={pts("pct50")} />
      <Tile label="Above 200-day average" info={help.ma} value={share(t.pct200.value)} change={pts("pct200")} />
      <Tile label="52-week highs / lows" info={help.highs_lows} value={<>{count(t.highs.value)} <span className="muted">/</span> {count(t.lows.value)}</>} change={pair("highs", "lows")} />
      <Tile label="Up 4% / down 4%" info={help.moves} value={<>{count(t.up4.value)} <span className="muted">/</span> {count(t.down4.value)}</>} change={pair("up4", "down4")} />
      <Tile label="In Stage 2" info={help.stage2} value={share(t.stage2.value)} change={pts("stage2")} />
      <Tile label="McClellan oscillator" info={help.mcclellan} value={t.mcclellan.value == null ? "–" : fmt1(t.mcclellan.value)}
        sub={t.summation.value == null ? undefined : `Summation ${fmt1(t.summation.value)}`}
        change={t.mcclellan.change == null ? undefined : `${delta(t.mcclellan.change, "", 1)}${vs}`} />
      <Tile label="TRIN" info={help.trin} value={t.trin.value == null ? "–" : t.trin.value.toFixed(2)}
        change={t.trin.change == null ? undefined : `${delta(t.trin.change, "", 2)}${vs}`} />
    </section>
  );
}

/* ---------- an alert on the share above the 50-day average ---------- */
function AlertBox({ group }: { group: Group }) {
  const { fail, notify } = useApp();
  const [alerts, setAlerts] = useState<BreadthAlerts | null>(null);
  const [level, setLevel] = useState("60");
  const [busy, setBusy] = useState(false);
  useEffect(() => { breadthApi.alerts().then(setAlerts).catch(() => setAlerts(null)); }, []);
  const n = Number(level);
  const ok = level.trim() !== "" && Number.isFinite(n) && n >= 1 && n <= 99;
  const add = async () => {
    setBusy(true);
    try {
      setAlerts(await breadthApi.addAlert(group.id, n));
      notify(`You'll get a message after the close when ${group.name}'s share above the 50-day average crosses ${n}%.`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    try { setAlerts(await breadthApi.deleteAlert(id)); } catch (e) { fail(e); }
  };
  const mine = alerts?.items ?? [];
  const name = (id: string) => (id === group.id ? group.name : id);
  return (
    <section className="card stack bx-alerts" style={{ gap: 10 }} aria-label="Breadth alerts">
      <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
        <label htmlFor="bx-level" className="small">Alert me when the share of {group.name} stocks above their 50-day average crosses</label>
        <span className="row" style={{ gap: 6 }}>
          <input id="bx-level" className="bx-level" inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} aria-invalid={!ok} />
          <span className="small">%</span>
        </span>
        <button className="btn sm" disabled={!ok || busy || (alerts ? mine.length >= alerts.limit : false)} onClick={add}>Add alert</button>
        <Info label="About breadth alerts">{"Checked once a day, after the counts for the close are in. You get one message each time the share moves from one side of your level to the other, by phone notification, Telegram or email, whichever you set up on the Account page. Up to 5."}</Info>
      </div>
      {mine.length > 0 && (
        <ul className="bx-alert-list">
          {mine.map((a) => (
            <li key={a.id} className="row" style={{ gap: 10 }}>
              <span className="small">{name(a.group)} crosses {a.level}%{a.side ? ` · now ${a.side}` : ""}{a.fired_at ? ` · last sent ${shortDay(a.fired_at.slice(0, 10))}` : ""}</span>
              <button className="btn quiet sm" aria-label={`Delete the alert at ${a.level}% on ${name(a.group)}`} onClick={() => remove(a.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
      {alerts && !alerts.channels.length && <p className="tiny muted">Set up a phone, Telegram or a confirmed email on the <Link className="link" to="/account">Account page</Link> for alerts to reach you.</p>}
    </section>
  );
}

/* ---------- the charts ---------- */
function Charts({ data, h, help }: { data: BreadthView; h: History; help: Record<string, string> }) {
  const labels = h.days.map(shortDay);
  const since = data.since ? shortDay(data.since) : null;
  const hasIndex = h.index.some((v) => v != null);
  const asOf = (s: ReactNode) => <p className="tiny muted">{s}</p>;
  const last = h.days.length ? shortDay(h.days[h.days.length - 1]) : "";
  return (
    <>
      <div className="rs-grid" data-testid="breadth-charts">
        <Panel title="Advance/decline line" info={help.ad_line}>
          <LineChart lines={[{ values: h.ad_line, color: A, label: "A/D line", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            format={fmtInt} ariaLabel={`Advance/decline line, ${labels[0]} to ${last}`} />
          {asOf(`Running total from ${since ?? "the first stored day"} · last ${last}`)}
        </Panel>
        <Panel title="Share above the 50- and 200-day averages" info={help.ma}>
          <LineChart lines={[{ values: h.pct50, color: A, label: "Above 50-day", width: 2 }, { values: h.pct200, color: B, label: "Above 200-day", width: 2 }]} legend
            labels={labels} times={h.days} sync="breadth" ranges={false} height={200} format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Share of stocks above their 50- and 200-day averages" />
          {asOf(`Last ${last}`)}
        </Panel>
        <Panel title={data.group.index_name} info={help.index}>
          {hasIndex ? <LineChart lines={[{ values: h.index, color: "var(--ink-2)", label: data.group.index_name, width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            format={(v) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 })} axisFormat={fmtInt} ariaLabel={`${data.group.index_name} closing level`} />
            : <p className="small muted">The index's prices weren't available for these days.</p>}
          {asOf(`Closing level · last ${last}`)}
        </Panel>
        <Panel title="New 52-week highs and lows" info={help.highs_lows}>
          <PairBars up={h.highs} down={h.lows} labels={labels} times={h.days} sync="breadth" ranges={false} upLabel="new highs" downLabel="new lows" upName="New highs" downName="New lows" upColor={A} downColor={B}
            format={fmtInt} ariaLabel="New 52-week highs (up) and lows (down) each day" />
          {asOf(`Highs drawn up, lows down · last ${last}`)}
        </Panel>
        <Panel title="McClellan oscillator" info={help.mcclellan}>
          <LineChart lines={[{ values: h.mcclellan, color: A, label: "Oscillator", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            baseline={0} format={fmt1} axisFormat={fmtInt} ariaLabel="McClellan oscillator" />
          {asOf(`Last ${last}`)}
        </Panel>
        <Panel title="McClellan summation index" info={help.summation}>
          <LineChart lines={[{ values: h.summation, color: A, label: "Summation", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            baseline={0} format={fmt1} axisFormat={fmtInt} ariaLabel="McClellan summation index" />
          {asOf(`Added up from ${since ?? "the first stored day"} · last ${last}`)}
        </Panel>
        <Panel title="Stocks up 4% and down 4%" info={help.moves}>
          <PairBars up={h.up4} down={h.down4} labels={labels} times={h.days} sync="breadth" ranges={false} upLabel="up 4%+" downLabel="down 4%+" upName="Up 4% or more" downName="Down 4% or more" upColor={A} downColor={B}
            format={fmtInt} ariaLabel="Stocks up 4% or more (up) and down 4% or more (down) each day" />
          {asOf(`Last ${last}`)}
        </Panel>
        <Panel title="Share in Stage 2" info={help.stage2}>
          <LineChart lines={[{ values: h.stage2, color: A, label: "In Stage 2", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Share of stocks in Stage 2" />
          {asOf(`Last ${last}`)}
        </Panel>
        <Panel title="Breadth thrust measure" info={help.thrust}>
          <LineChart lines={[{ values: h.thrust, color: A, label: "10-day average", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200}
            levels={[{ v: 40, color: "var(--dash)", label: "40%" }, { v: 61.5, color: "var(--dash)", label: "61.5%" }]}
            format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Breadth thrust measure, with lines at 40% and 61.5%" />
          <p className="small" data-testid="breadth-thrusts">
            {data.thrusts?.length ? `A thrust happened on ${data.thrusts.map((d) => shortDay(d)).join(", ")}.` : "No thrust in these days."}
            <span className="muted"> Dashed lines at 40% and 61.5%.</span>
          </p>
        </Panel>
        <Panel title="TRIN" info={help.trin}>
          <LineChart lines={[{ values: h.trin, color: A, label: "TRIN", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} height={200} refs={[{ v: 1, dash: true }]}
            format={(v) => v.toFixed(2)} ariaLabel="TRIN each day, with a line at 1" />
          {asOf(`Dashed line at 1 · last ${last}`)}
        </Panel>
        {data.sectors && data.sectors.rows.length > 0 && (
          <Panel title="Sectors: share above the 50-day average" info={help.sectors} span="full">
            <SectorHeat t={data.sectors} />
          </Panel>
        )}
        <Panel title="The last 20 trading days" span="full" info="The counts behind the charts, newest first.">
          <Recent h={h} />
        </Panel>
      </div>
    </>
  );
}

function SectorHeat({ t }: { t: SectorTable }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="table-wrap">
        <table className="nums bx-heat">
          <thead><tr><th>Sector</th><th>Stocks</th>{t.columns.map((c) => <th key={c.label} title={c.day}>{c.label}</th>)}</tr></thead>
          <tbody>
            {t.rows.map((r) => (
              <tr key={r.sector}>
                <td>{r.sector}</td>
                <td className="num">{r.stocks}</td>
                {r.values.map((v, i) => (
                  <td key={i} className="num bx-cell" title={`${r.sector}, ${t.columns[i].label.toLowerCase()} (${t.columns[i].day}): ${share(v)}`}
                    style={v == null ? undefined : { background: `color-mix(in srgb, var(--bx-a) ${Math.round(v * 0.45)}%, transparent)` }}>{share(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row small muted" style={{ gap: 8 }} aria-hidden="true">
        <span>0%</span><span className="bx-scale" /><span>100%</span>
        <span className="tiny">Darker: more of the sector's stocks above their 50-day average.</span>
      </div>
    </div>
  );
}

function Recent({ h }: { h: History }) {
  const n = h.days.length;
  const idx = Array.from({ length: Math.min(20, n) }, (_, k) => n - 1 - k);
  return (
    <div className="table-wrap">
      <table className="nums">
        <thead><tr><th>Day</th><th>Rose</th><th>Fell</th><th>Above 50-day</th><th>Above 200-day</th><th>Highs</th><th>Lows</th><th>Up 4%</th><th>Down 4%</th><th>McClellan</th><th>TRIN</th></tr></thead>
        <tbody>
          {idx.map((i) => (
            <tr key={h.days[i]}>
              <td>{shortDay(h.days[i])}</td>
              <td className="num">{count(h.adv[i])}</td><td className="num">{count(h.dec[i])}</td>
              <td className="num">{share(h.pct50[i])}</td><td className="num">{share(h.pct200[i])}</td>
              <td className="num">{count(h.highs[i])}</td><td className="num">{count(h.lows[i])}</td>
              <td className="num">{count(h.up4[i])}</td><td className="num">{count(h.down4[i])}</td>
              <td className="num">{fmt1(h.mcclellan[i])}</td><td className="num">{h.trin[i] == null ? "–" : h.trin[i]!.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
