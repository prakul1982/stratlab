import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { pct, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { REGION_NAME, useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { Info } from "../components/ui";
import { FilingRow, SummaryLine, type FilingItem, type FilingSummary } from "../components/Filings";
import { QUADRANTS, QuadrantTag, RotationChart, useAnimate, type Quadrant, type RotationRow } from "../components/Rotation";
import {
  Badge, Card, CardHead, ChartFrame, CheckField, DataTable, Delta, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, PlanNote, Seg,
  Select, Skeleton, Stat, StatRow,
} from "../components/kit";

/* ---------- Stage 2 + Supertrend scan (Basic and up) ---------- */
interface ScanRow {
  id: string; symbol: string; name: string | null; currency: string | null; price: number; chg: number | null;
  stage: number | null; stage_days: number | null; st_up: boolean; st_days: number; signal: "fresh" | "st_s2" | "stage2" | null;
}
interface ScanOut { name: string; market: Region; rows: ScanRow[]; missing: string[]; problems: string[]; counts: Record<string, number> }
interface ScanSets { sets: { id: string; name: string; count: number }[]; alerts: boolean; template: unknown; fresh_days: number; rotation_sets?: { id: string; name: string }[] }

const STAGE_NAME: Record<number, string> = { 1: "Stage 1 · basing", 2: "Stage 2 · advancing", 3: "Stage 3 · topping", 4: "Stage 4 · declining" };
const SIGNAL: Record<string, ["ok" | "plain", string]> = {
  fresh: ["ok", "Fresh ST S2"], st_s2: ["ok", "In ST S2"], stage2: ["plain", "Stage 2, Supertrend down"],
};
const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;

export function ScanPage() {
  const [region, setRegion] = useRegion();
  const { fail, notify, refreshNotebooks, me } = useApp();
  const nav = useNavigate();
  const [sets, setSets] = useState<ScanSets | null>(null);
  const [setId, setSetId] = useState(() => new URLSearchParams(window.location.search).get("set") || "watchlist");
  const [out, setOut] = useState<ScanOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [only, setOnly] = useState(false);
  const pro = !!me?.plan_info?.features?.scans;

  useEffect(() => {
    setOut(null);
    api<ScanSets>(`/research/scan/sets?region=${region}`).then((s) => {
      setSets(s);
      setSetId((cur) => s.sets.some((x) => x.id === cur && (x.id !== "watchlist" || x.count)) ? cur : (s.sets.find((x) => x.id !== "watchlist" || x.count)?.id ?? "watchlist"));
    }).catch(fail);
  }, [region, fail]);

  const runScan = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    try { setOut(await api<ScanOut>("/research/scan", { method: "POST", body: { region, set: setId } })); } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const toggleAlerts = async () => {
    if (!sets) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/scan/alerts", { method: "PUT", body: { on: !sets.alerts } });
      setSets({ ...sets, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message after each close when a watchlist stock gives an ST S2 signal." : "ST S2 alerts off.");
    } catch (e) { fail(e); }
  };
  const testIt = async () => {
    if (!out || !sets) return;
    const members = out.rows.map((r) => ({ id: r.id, symbol: r.symbol }));
    if (members.length < 2) { notify("A group test needs at least two stocks."); return; }
    try {
      const nb = await api<{ id: string }>("/notebooks", { method: "POST", body: {
        name: `ST S2 on ${out.name}`.slice(0, 80), question: "Does Stage 2 + Supertrend work on this group?",
        strategy: sets.template, group: { id: setId, name: out.name.slice(0, 60), market: region, members: members.slice(0, 50), maxOpen: 5 } } });
      await refreshNotebooks();
      nav(`/n/${nb.id}`);
    } catch (e) { fail(e); }
  };

  const rows = (out?.rows ?? []).filter((r) => !only || r.signal === "fresh" || r.signal === "st_s2");
  const cur = sets?.sets.find((s) => s.id === setId);
  const emptyWatch = !!cur && cur.id === "watchlist" && !cur.count;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/scan")} title="Stage 2 + Supertrend"
        lede="Which stocks are in Stage 2 (the price above a rising 150-day average) and have the Supertrend pointing up (a line that follows the price and flips when the trend turns). Both together are called ST S2 here. Facts from the charts, not advice." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      {!pro && <PlanNote>The Stage 2 + Supertrend scan and its alert are on the Basic plan.</PlanNote>}
      <Card>
        <CardHead title="Scan a group" />
        <FormGrid label="Scan a group" onSubmit={runScan}>
          <Field label="Group to scan">
            {(id) => <Select id={id} value={setId} onChange={(v) => { setSetId(v); setOut(null); }}
              options={(sets?.sets ?? []).map((s) => ({ value: s.id, label: `${s.name} (${s.count})`, disabled: s.id === "watchlist" && !s.count }))} />}
          </Field>
          <FormActions>
            <button className="btn" disabled={busy || !pro || !cur?.count}>{busy ? "Scanning…" : "Scan"}</button>
            {sets && <CheckField checked={sets.alerts} disabled={!pro} onChange={toggleAlerts}
              label={<>Alert me after each close when a watchlist stock newly meets both (ST S2)
                <Info>{"Checked once a day after the market closes, for the stocks in your watchlist. Sent by phone notification, Telegram or email, whichever you set up in Settings."}</Info></>} />}
          </FormActions>
        </FormGrid>
      </Card>
      {emptyWatch && <Card compact><EmptyState title={`Your ${REGION_NAME[region]} watchlist is empty`} action={{ label: "Find a company", to: `/research?region=${region}` }}>Press Watch on company pages to add stocks, or scan a ready-made group.</EmptyState></Card>}
      {!out && !busy && pro && !!cur?.count && <p className="k-small k-muted">Pick a group and press Scan to see each stock's stage and Supertrend direction.</p>}
      {busy && <Card><Skeleton label="Reading each stock's daily chart" lines={4} /></Card>}
      {out && !busy && (
        <Card>
          <CardHead title={out.name} actions={<>
            <CheckField label="Only ST S2" checked={only} onChange={setOnly} />
            <button className="btn quiet sm" onClick={testIt}>Backtest ST S2 on this group</button></>} />
          <StatRow>
            <Stat label="Fresh ST S2" value={String(out.counts.fresh)} note={`Supertrend turned up in the last ${sets?.fresh_days ?? 5} days`} />
            <Stat label="Already in ST S2" value={String(out.counts.st_s2)} />
            <Stat label="In Stage 2 only" value={String(out.counts.stage2)} />
          </StatRow>
          <DataTable label={`${out.name}: stage and Supertrend`} rows={rows} rowKey={(r) => r.id} sticky={rows.length > 12} empty="Nothing matches right now."
            columns={[
              { key: "s", header: "Stock", rowHeader: true, wrap: true, cell: (r) => (
                <><Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
                  {r.name && r.name !== r.symbol && <span className="k-sub-line">{r.name}</span>}
                  <Link className="link k-small" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}>Deep dive →</Link></>) },
              { key: "p", header: "Price", numeric: true, cell: (r) => (
                <>{price(r.price, r.currency ?? (region === "IN" ? "INR" : "USD"))}{r.chg != null && <span className="k-sub-line"><Delta value={r.chg} tone="neutral">{pct(r.chg, 2)}</Delta></span>}</>) },
              { key: "st", header: "Stage", cell: (r) => <>{r.stage ? STAGE_NAME[r.stage] : "–"}{r.stage_days ? <span className="k-sub-line">{days(r.stage_days)}</span> : null}</> },
              { key: "sp", header: "Supertrend", cell: (r) => <>{r.st_up ? "Up" : "Down"}<span className="k-sub-line">for {days(r.st_days)}</span></> },
              { key: "sg", header: "Signal", cell: (r) => (r.signal ? <Badge tone={SIGNAL[r.signal][0]} dot={false}>{SIGNAL[r.signal][1]}</Badge> : <span className="k-muted">–</span>) },
            ]} />
          {(out.missing.length > 0 || out.problems.length > 0) && <p className="k-note">Skipped: {[...out.missing, ...out.problems].join(" · ")}</p>}
        </Card>
      )}
      <p className="k-note inv-text">Stage uses the 150-day average and its 20-day slope; Supertrend uses 10 days and 3× the average daily range (ATR). Past signals don't predict future returns, and nothing here is investment advice.</p>
    </div>
  );
}

interface RotationOut {
  name: string; market: Region; benchmark: string; interval: "weekly" | "daily"; tail: number;
  rows: RotationRow[]; skipped: string[]; as_of: string | null; parent: { symbol: string; name: string } | null;
}

const ARROW = (deg: number | null) => deg == null ? "–" : ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"][Math.round(((deg + 360) % 360) / 45) % 8];

export function RotationPage() {
  const [region, setRegion] = useRegion();
  const { fail } = useApp();
  const [sets, setSets] = useState<ScanSets | null>(null);
  const [setId, setSetId] = useState("sectors");
  const [backTo, setBackTo] = useState<string | null>(null);        // the set a sector's stocks were opened from
  const [interval, setIv] = useState<"weekly" | "daily">("weekly");
  const [tail, setTail] = useState(4);
  const [askTail, setAskTail] = useState(4);
  const [picked, setPicked] = useState<Set<string> | null>(null);   // null = the default set (main sectors)
  const [focus, setFocus] = useState<string | null>(null);          // the slider settles before it asks the server
  const [out, setOut] = useState<RotationOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [tries, setTries] = useState(0);
  const [failed, setFailed] = useState<string | null>(null);
  const [step, animate] = useAnimate(out?.tail ?? tail);

  useEffect(() => {
    api<ScanSets>(`/research/scan/sets?region=${region}`).then(setSets).catch(fail);
  }, [region, fail]);

  useEffect(() => {
    const t = window.setTimeout(() => setAskTail(tail), 250);
    return () => window.clearTimeout(t);
  }, [tail]);

  useEffect(() => {
    let live = true;
    setBusy(true); setFailed(null);
    api<RotationOut>(`/research/rotation?region=${region}&set=${encodeURIComponent(setId)}&interval=${interval}&tail=${askTail}`)
      .then((r) => { if (live) setOut(r); }).catch((e) => { if (live) { setOut(null); setFailed((e as Error).message); } })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [region, setId, interval, askTail, tries]);

  useEffect(() => { setPicked(null); setFocus(null); }, [region, setId]);

  const groups = (sets?.sets ?? []).filter((s) => s.count >= 2);
  const indexSets = sets?.rotation_sets ?? [{ id: "sectors", name: region === "IN" ? "NSE sector indices" : "S&P 500 sectors" }];
  const isIndex = indexSets.some((x) => x.id === setId);
  const drilled = setId.startsWith("sector:");
  const openStocks = (r: RotationRow) => { setBackTo(setId); setSetId(`sector:${r.symbol}`); };
  const all = out?.rows ?? [];
  const isOn = (r: RotationRow) => (picked ? picked.has(r.id) : r.core !== false);
  const rows = all.filter(isOn);
  const toggle = (r: RotationRow) => {
    const next = new Set(all.filter(isOn).map((x) => x.id));
    if (next.has(r.id)) { next.delete(r.id); if (focus === r.id) setFocus(null); } else next.add(r.id);
    setPicked(next);
  };
  const names = (q: Quadrant) => all.filter((r) => r.quadrant === q).map((r) => r.name);
  const entered = all.filter((r) => r.quadrant === "leading" && r.moved && r.moved !== "leading").map((r) => r.name);
  const unit = interval === "weekly" ? "week" : "day";
  const few = (xs: string[], n = 5) => !xs.length ? "none" : xs.length <= n + 1 ? xs.join(", ") : `${xs.slice(0, n).join(", ")} and ${xs.length - n} more`;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/rotation")} title="Sector rotation" asOf={out?.as_of} asOfLabel="Closes up to"
        lede="Where each sector (or stock) stands against the market, and which way it's moving. Right of centre = stronger than the benchmark; above centre = gaining pace. Most move clockwise through the four corners." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={(r) => { setRegion(r); setSetId("sectors"); setBackTo(null); }} /></div>
      <Card>
        <FormGrid label="What to show">
          <Field label="What to compare">
            {(id) => (
              <select id={id} className="k-input" value={setId} onChange={(e) => { setSetId(e.target.value); setBackTo(null); }}>
                <optgroup label="Indices">{indexSets.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</optgroup>
                {groups.length > 0 && <optgroup label="Stocks">{groups.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.count})</option>)}</optgroup>}
                {drilled && <option value={setId}>{out?.name ?? "A sector's stocks"}</option>}
              </select>
            )}
          </Field>
          <FieldGroup label="Candle size">
            <Seg label="Candle size" value={interval} onChange={(v) => setIv(v as "weekly" | "daily")} options={[{ value: "weekly", label: "Weekly" }, { value: "daily", label: "Daily" }]} />
          </FieldGroup>
          <Field label="Trail">
            {(id) => (
              <div className="k-row">
                <input id={id} type="range" min={1} max={12} value={tail} onChange={(e) => setTail(+e.target.value)} aria-label="Trail length" />
                <span className="k-small">{tail} {unit}{tail === 1 ? "" : "s"}</span>
              </div>
            )}
          </Field>
          <FormActions>
            <button type="button" className="btn quiet sm" disabled={!out || busy || step !== null || (out?.tail ?? 1) < 2} onClick={animate}>{step !== null ? "Playing…" : "Animate"}</button>
            {drilled && <button type="button" className="btn quiet sm" onClick={() => { setSetId(backTo ?? "sectors"); setBackTo(null); }}>← Back to {indexSets.find((x) => x.id === (backTo ?? "sectors"))?.name ?? "sectors"}</button>}
          </FormActions>
        </FormGrid>
      </Card>
      {failed && <ErrorState title="The rotation couldn't be worked out" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{failed}</ErrorState>}
      {busy && !out && !failed && <Card><Skeleton label="Comparing each one with the market" lines={4} /></Card>}
      {out && (
        <ChartFrame title={`${out.name} vs ${out.benchmark}`}
          actions={<div className="rot-legend" aria-label="Legend">{QUADRANTS.map((q) => <span key={q.id} title={q.says}><QuadrantTag q={q.id} /></span>)}</div>}
          footer={all.length > 0 ? <p className="k-note">Each dot is where it is now; the faint line is where it came from. Hover or tap a dot, or a row below, to follow one.</p> : undefined}>
          <div className="k-stack">
            <span className="k-small k-muted">{rows.length} of {all.length} shown · {out.interval === "weekly" ? "weekly" : "daily"} closes{out.as_of ? ` to ${out.as_of}` : ""}{step !== null ? ` · replaying ${unit} ${step} of ${out.tail}` : ""}</span>
            {all.length > 0 && (
              <div className="rot-read">
                {([["leading", `stronger than ${drilled && out.parent ? out.parent.name : "the market"} and still gaining`], ["improving", "weaker, but picking up"],
                   ["weakening", "stronger, but losing pace"], ["lagging", "weaker and still slipping"]] as [Quadrant, string][]).map(([q, says]) => (
                  <div key={q}><QuadrantTag q={q} /><span className="k-muted k-small">{says}</span><span className="k-small">{few(names(q))}</span></div>
                ))}
                {entered.length > 0 && <p className="k-small">Moved into Leading over the last {out.tail} {unit}s: <b>{few(entered)}</b></p>}
              </div>
            )}
            {rows.length === 0 ? <EmptyState title={all.length ? "Nothing is ticked" : "Not enough price history to draw this yet"}>{all.length ? "Tick a few in the table below to draw them." : "It fills in as more closes are stored."}</EmptyState>
              : <RotationChart rows={rows} benchmark={out.benchmark} step={step} focus={focus} onFocus={setFocus} />}
          </div>
        </ChartFrame>
      )}
      {out && all.length > 0 && (
        <Card>
          <CardHead title={isIndex ? "The indices" : "The stocks"} actions={<>
            <button className="btn quiet sm" onClick={() => setPicked(new Set(all.map((r) => r.id)))}>Show all {all.length}</button>
            {all.some((r) => r.core === false) && <button className="btn quiet sm" onClick={() => setPicked(null)}>Main sectors only</button>}
            <button className="btn quiet sm" onClick={() => setPicked(new Set())}>Clear</button></>} />
          <DataTable label="Where each one stands" rows={all} rowKey={(r) => r.id} sticky={all.length > 14} rowAttrs={(r) => ({ className: focus === r.id ? "rot-row on" : "rot-row" })}
            columns={[
              { key: "on", header: <span className="sr-only">Show on chart</span>, cell: (r) => <input type="checkbox" checked={isOn(r)} onChange={() => toggle(r)} aria-label={`Show ${r.name} on the chart`} /> },
              { key: "n", header: isIndex ? "Index" : "Stock", rowHeader: true, wrap: true, cell: (r) => (isIndex
                ? <span className="k-row">{isOn(r) ? <button className="link" onClick={() => setFocus(focus === r.id ? null : r.id)}>{r.name}</button> : r.name}
                    {(r.stocks ?? 0) > 0 && <button className="btn quiet sm" onClick={() => openStocks(r)} title={`Its ${r.stocks} main stocks against the ${r.name} index`}>Stocks →</button>}</span>
                : <Link className="link" to={`/research/${region}/${encodeURIComponent(r.name)}`}>{r.name}</Link>) },
              { key: "q", header: "Now", cell: (r) => <QuadrantTag q={r.quadrant} /> },
              { key: "x", header: "Strength", numeric: true, cell: (r) => r.x.toFixed(2) },
              { key: "y", header: "Momentum", numeric: true, cell: (r) => r.y.toFixed(2) },
              { key: "h", header: "Heading", cell: (r) => <span aria-label={r.heading == null ? "no move" : `${Math.round(r.heading)} degrees`}>{ARROW(r.heading)}</span> },
              { key: "m", header: `${out.tail} ${unit}s ago`, cell: (r) => (r.moved ? (r.moved === r.quadrant ? <span className="k-small k-muted">same</span> : <QuadrantTag q={r.moved} />) : "–") },
            ]} />
          {out.skipped.length > 0 && <p className="k-note">Skipped (not enough history or not available): {out.skipped.join(" · ")}</p>}
        </Card>
      )}
      <p className="k-note inv-text">
        {drilled && out?.parent ? `Here each stock is measured against the ${out.parent.name} index itself, so Leading means it's beating its own sector. These are the sector's largest stocks, not its full official list. ` : ""}
        Strength: each one's price divided by {drilled && out?.parent ? `the ${out.parent.name} index` : region === "IN" ? "the Nifty 500" : "the S&P 500"}, compared with its own last 14 {unit}s (100 = its usual level). Momentum: the same for the change in that strength. StratLab's own calculation. Where something sits today doesn't predict where it goes next, and nothing here is investment advice.
      </p>
    </div>
  );
}

interface FilingsOverview {
  rows: { symbol: string; summary: FilingSummary; flags: FilingItem[] }[]; problems: string[]; days: number; alerts: boolean; send_at: string;
}

export function FilingsPage() {
  const { fail, notify, me } = useApp();
  const pro = !!me?.plan_info?.features?.filings;
  const [data, setData] = useState<FilingsOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    if (!pro) return;
    setBusy(true); setError(null);
    api<FilingsOverview>("/research/filings").then(setData).catch((e) => setError((e as Error).message)).finally(() => setBusy(false));
  }, [pro, tries]);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/filings/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? `You'll get a message each evening (${data.send_at} IST) when a watchlist stock files a red flag.` : "Filing alerts off.");
    } catch (e) { fail(e); }
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/filings")} title="Filings and red flags"
        lede="What your watchlist companies told the exchange in the last 3 months: fund raises (QIP, preferential, rights, warrants), promoter pledges, auditor and director resignations, defaults, regulator action and rating downgrades." />
      {!pro && <PlanNote>Red flags for your whole watchlist, with an evening alert, are on the Basic plan. Each company's own page shows its red flags on every plan.</PlanNote>}
      {data && (
        <Card>
          <CheckField checked={data.alerts} onChange={toggleAlerts}
            label={<>Message me each evening when a watchlist stock files a red flag or something to look closer at
              <Info>{`Checked once a day at ${data.send_at} IST, for the India stocks in your watchlist. Sent by phone notification, Telegram or email, whichever you set up in Settings.`}</Info></>} />
        </Card>
      )}
      {busy && <Card><Skeleton label="Reading each company's filings" lines={4} /></Card>}
      {error && <ErrorState title="The filings couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {data && !busy && (data.rows.length === 0 && data.problems.length === 0
        ? <Card><EmptyState title="Your watchlist has no India stocks yet" action={{ label: "Find a company", to: "/research?region=IN" }}>Open a company and press Watch: its filings show up here.</EmptyState></Card>
        : (
          <>
            {data.rows.map((r) => (
              <Card key={r.symbol}>
                <CardHead title={<Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`}>{r.symbol}</Link>}
                  actions={<Link className="btn quiet sm" to={`/research/IN/${encodeURIComponent(r.symbol)}/deep`}>Deep dive →</Link>} />
                <SummaryLine s={r.summary} />
                {r.flags.length > 0 ? <div className="inv-rows">{r.flags.map((i) => <FilingRow key={i.id} i={i} />)}</div>
                  : <span className="k-small k-muted">Nothing flagged in the last {data.days} days.</span>}
              </Card>
            ))}
            {data.problems.length > 0 && <p className="k-note">Couldn't read: {data.problems.join(" · ")}</p>}
          </>
        ))}
      <p className="k-note inv-text">From the companies' own filings with the exchange. Labels come from fixed keyword rules; a label is a reason to read the filing, not a verdict on the company, and nothing here is investment advice.</p>
    </div>
  );
}
