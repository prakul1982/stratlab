import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { asOf, fmtDate, marketTz, pct, price, safeHref } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { REGION_NAME, useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { Info } from "../components/ui";
import { FilingRow, SummaryLine, type FilingItem, type FilingSummary } from "../components/Filings";
import { QUADRANTS, QuadrantTag, RotationChart, useAnimate, type Quadrant, type RotationRow } from "../components/Rotation";
import {
  Badge, Card, CardHead, ChartFrame, CheckField, ChipBar, DataTable, DateField, Delta, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, PlanNote, Seg,
  Pager, Range, Select, Skeleton, Stat, StatRow,
} from "../components/kit";

/* ---------- Trend scan: Stage 2 + Supertrend, and the preset rule sets (Basic and up) ---------- */
interface ScanRow {
  id: string; symbol: string; name: string | null; currency: string | null; price: number; chg: number | null;
  stage: number | null; stage_days: number | null; st_up: boolean; st_days: number; signal: "fresh" | "st_s2" | "stage2" | null;
}
interface ScanOut { kind: "st_s2"; name: string; market: Region; rows: ScanRow[]; missing: string[]; problems: string[]; counts: Record<string, number> }
interface PresetRow { symbol: string; name: string | null; currency: string | null; price: number; chg: number | null; as_of: string; days_ago: number; day: string; detail: string }
interface PresetOut {
  kind: "preset"; scan: string; scan_name: string; name: string; market: Region; rows: PresetRow[]; matches: number; checked: number; as_of: string | null;
  updated_at?: string | null; stored: boolean; missing: string[]; problems: string[];
}
interface ScanInfo { id: string; name: string; text: string; rules: string[]; within: number }
interface SetInfo { id: string; name: string; count: number; stored?: boolean; as_of?: string | null }
interface ScanSets { sets: SetInfo[]; alerts: boolean; template: unknown; fresh_days: number; scans?: ScanInfo[]; rotation_sets?: { id: string; name: string }[] }

const STAGE_NAME: Record<number, string> = { 1: "Stage 1 · basing", 2: "Stage 2 · advancing", 3: "Stage 3 · topping", 4: "Stage 4 · declining" };
const SIGNAL: Record<string, ["ok" | "plain", string]> = {
  fresh: ["ok", "Fresh Stage 2 + Supertrend"], st_s2: ["ok", "In Stage 2 + Supertrend"], stage2: ["plain", "Stage 2, Supertrend down"],
};
const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;
const FIRST_SCAN: ScanInfo = { id: "st_s2", name: "Stage 2 + Supertrend", text: "", rules: [], within: 1 };
const sessions = (n: number) => (n === 0 ? "On the latest close" : `${n} session${n === 1 ? "" : "s"} before the latest close`);

export function ScanPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const { fail, notify, refreshNotebooks, me } = useApp();
  const nav = useNavigate();
  const [sets, setSets] = useState<ScanSets | null>(null);
  const [setId, setSetId] = useState(() => new URLSearchParams(window.location.search).get("set") || "watchlist");
  const scanId = params.get("scan") || "st_s2";
  const [out, setOut] = useState<ScanOut | PresetOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [only, setOnly] = useState(false);
  const pro = !!me?.plan_info?.features?.scans;
  const scans = sets?.scans?.length ? sets.scans : [FIRST_SCAN];
  const scan = scans.find((s) => s.id === scanId) ?? scans[0];

  useEffect(() => {
    setOut(null);
    api<ScanSets>(`/research/scan/sets?region=${region}`).then((s) => {
      setSets(s);
      const usable = (x: SetInfo) => (x.id !== "watchlist" && !x.stored) || !!x.count;
      setSetId((cur) => s.sets.some((x) => x.id === cur && usable(x)) ? cur : (s.sets.find(usable)?.id ?? "watchlist"));
    }).catch(fail);
  }, [region, fail]);

  const pickScan = (v: string) => {
    const p = new URLSearchParams(params); p.set("scan", v); setParams(p, { replace: true });
    setOut(null);
  };
  const runScan = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    try { setOut(await api<ScanOut | PresetOut>("/research/scan", { method: "POST", body: { region, set: setId, scan: scan.id } })); } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const toggleAlerts = async () => {
    if (!sets) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/scan/alerts", { method: "PUT", body: { on: !sets.alerts } });
      setSets({ ...sets, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message after each close when a watchlist stock gives a Stage 2 + Supertrend signal." : "Stage 2 + Supertrend alerts off.");
    } catch (e) { fail(e); }
  };
  const testIt = async () => {
    if (!out || out.kind !== "st_s2" || !sets) return;
    const members = out.rows.map((r) => ({ id: r.id, symbol: r.symbol }));
    if (members.length < 2) { notify("A group test needs at least two stocks."); return; }
    try {
      const nb = await api<{ id: string }>("/notebooks", { method: "POST", body: {
        name: `Stage 2 + Supertrend on ${out.name}`.slice(0, 80), question: "Does Stage 2 + Supertrend work on this group?",
        strategy: sets.template, group: { id: setId, name: out.name.slice(0, 60), market: region, members: members.slice(0, 50), maxOpen: 5 } } });
      await refreshNotebooks();
      nav(`/n/${nb.id}`);
    } catch (e) { fail(e); }
  };

  const cur = sets?.sets.find((s) => s.id === setId);
  const emptyWatch = !!cur && cur.id === "watchlist" && !cur.count;
  const notRead = !!cur && !!cur.stored && !cur.count;
  const st2 = out?.kind === "st_s2" ? out : null;
  const preset = out?.kind === "preset" ? out : null;
  const rows = (st2?.rows ?? []).filter((r) => !only || r.signal === "fresh" || r.signal === "st_s2");
  const link = (symbol: string) => `/research/${region}/${encodeURIComponent(symbol)}`;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/scan")} title="Trend scan"
        lede="Which stocks match a chart rule right now. Each match is a fact about the chart on a date, not advice."
        asOf={preset?.as_of} asOfTz={marketTz(region)} info="The rules: Stage 2 with the Supertrend up, a 52-week high breakout, a golden cross, an RSI bounce, a volume surge, a Bollinger squeeze breakout, a stock near its 52-week low, or a pullback in an uptrend." infoLabel="Which rules" />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      {!pro && <PlanNote>The trend scans and the Stage 2 + Supertrend alert are on the Basic plan.</PlanNote>}
      <Card>
        <CardHead title="Scan a group" />
        <FormGrid label="Scan a group" onSubmit={runScan}>
          <FieldGroup label="Scan" wide info={<>Each scan is a short list of chart rules, all of which must hold. Pick one to read its rules below.</>}>
            <ChipBar label="Scan rule sets" value={scan.id} onChange={pickScan} options={scans.map((s) => ({ value: s.id, label: s.name }))} />
          </FieldGroup>
          {scan.text && (
            <div className="k-field wide" data-testid="scan-rule">
              <p className="k-small">{scan.text}</p>
              {scan.rules.length > 0 && <p className="k-note">Rules: {scan.rules.join("; ")}. Counts as a match when it held on any of the last {scan.within} candle{scan.within === 1 ? "" : "s"}.</p>}
            </div>
          )}
          <Field label="Group to scan">
            {(id) => <Select id={id} value={setId} onChange={(v) => { setSetId(v); setOut(null); }}
              options={(sets?.sets ?? []).map((s) => ({ value: s.id, label: s.stored && !s.count ? `${s.name} (read after the close)` : `${s.name} (${s.count})`, disabled: (s.id === "watchlist" || !!s.stored) && !s.count }))} />}
          </Field>
          <FormActions>
            <button className="btn" disabled={busy || !pro || !cur?.count}>{busy ? "Scanning…" : "Scan"}</button>
            {sets && scan.id === "st_s2" && <CheckField checked={sets.alerts} disabled={!pro} onChange={toggleAlerts}
              label={<>Alert me after each close when a watchlist stock newly meets both (Stage 2 + Supertrend)
                <Info>{"Checked once a day after the market closes, for the stocks in your watchlist. Sent by phone notification, Telegram or email, whichever you set up in Settings."}</Info></>} />}
          </FormActions>
        </FormGrid>
      </Card>
      {emptyWatch && <Card compact><EmptyState title={`Your ${REGION_NAME[region]} watchlist is empty`} action={{ label: "Find a company", to: `/research?region=${region}` }}>Press Watch on company pages to add stocks, or scan a ready-made group.</EmptyState></Card>}
      {notRead && <Card compact><EmptyState title={`${cur?.name} hasn't been read yet`}>This group is worked out once a day after the market closes. Scan a smaller group meanwhile.</EmptyState></Card>}
      {!out && !busy && pro && !!cur?.count && <p className="k-small k-muted">Pick a scan and a group, then press Scan to see which stocks match.</p>}
      {busy && <Card><Skeleton label="Reading each stock's daily chart" lines={4} /></Card>}
      {preset && !busy && (
        <Card>
          <CardHead title={`${preset.scan_name}: ${preset.name}`} info={preset.stored
            ? `Worked out once a day after the close from each stock's daily candles${preset.updated_at ? `; last read ${asOf(preset.updated_at, { tz: marketTz(region) })}` : ""}.`
            : "Read now from each stock's daily candles."} />
          <StatRow>
            <Stat label="Match the rule" value={String(preset.matches)} note={preset.as_of ? `as of ${asOf(preset.as_of, { tz: marketTz(region) })}` : undefined} />
            <Stat label="Stocks checked" value={String(preset.checked)} note={preset.stored ? "read after the close" : "read just now"} />
          </StatRow>
          <DataTable label={`${preset.name}: ${preset.scan_name}`} rows={preset.rows} rowKey={(r) => r.symbol} sticky={preset.rows.length > 12} empty="No stock matches this rule right now."
            columns={[
              { key: "s", header: "Stock", rowHeader: true, wrap: true, cell: (r) => (
                <><Link className="link" to={link(r.symbol)}><b>{r.symbol}</b></Link>
                  {r.name && r.name !== r.symbol && <span className="k-sub-line">{r.name}</span>}
                  <Link className="link k-small" to={`${link(r.symbol)}/deep`}>Deep dive →</Link></>) },
              { key: "p", header: "Price", numeric: true, cell: (r) => (
                <>{price(r.price, r.currency ?? (region === "IN" ? "INR" : "USD"))}{r.chg != null && <span className="k-sub-line"><Delta value={r.chg} tone="neutral">{pct(r.chg, 2)}</Delta></span>}</>) },
              { key: "m", header: `Matches ${scan.name.toLowerCase()}`, wrap: true, cell: (r) => <>{asOf(r.day)}<span className="k-sub-line">{sessions(r.days_ago)}</span></> },
              { key: "d", header: "The numbers", wrap: true, cell: (r) => r.detail || "–" },
            ]} />
          {preset.matches > preset.rows.length && <p className="k-note">Showing the first {preset.rows.length} of {preset.matches.toLocaleString("en-IN")} matches, the most recent first.</p>}
          {(preset.missing.length > 0 || preset.problems.length > 0) && <p className="k-note">Skipped: {[...preset.missing, ...preset.problems].join(" · ")}</p>}
        </Card>
      )}
      {st2 && !busy && (
        <Card>
          <CardHead title={st2.name} actions={<>
            <CheckField label="Only Stage 2 + Supertrend" checked={only} onChange={setOnly} />
            <button className="btn quiet sm" onClick={testIt}>Backtest Stage 2 + Supertrend on this group</button></>} />
          <StatRow>
            <Stat label="Fresh Stage 2 + Supertrend" value={String(st2.counts.fresh)} note={`Supertrend turned up in the last ${sets?.fresh_days ?? 5} days`} />
            <Stat label="Already in Stage 2 + Supertrend" value={String(st2.counts.st_s2)} />
            <Stat label="In Stage 2 only" value={String(st2.counts.stage2)} />
          </StatRow>
          <DataTable label={`${st2.name}: stage and Supertrend`} rows={rows} rowKey={(r) => r.id} sticky={rows.length > 12} empty="Nothing matches right now."
            columns={[
              { key: "s", header: "Stock", rowHeader: true, wrap: true, cell: (r) => (
                <><Link className="link" to={link(r.symbol)}><b>{r.symbol}</b></Link>
                  {r.name && r.name !== r.symbol && <span className="k-sub-line">{r.name}</span>}
                  <Link className="link k-small" to={`${link(r.symbol)}/deep`}>Deep dive →</Link></>) },
              { key: "p", header: "Price", numeric: true, cell: (r) => (
                <>{price(r.price, r.currency ?? (region === "IN" ? "INR" : "USD"))}{r.chg != null && <span className="k-sub-line"><Delta value={r.chg} tone="neutral">{pct(r.chg, 2)}</Delta></span>}</>) },
              { key: "st", header: "Stage", cell: (r) => <>{r.stage ? STAGE_NAME[r.stage] : "–"}{r.stage_days ? <span className="k-sub-line">{days(r.stage_days)}</span> : null}</> },
              { key: "sp", header: "Supertrend", cell: (r) => <>{r.st_up ? "Up" : "Down"}<span className="k-sub-line">for {days(r.st_days)}</span></> },
              { key: "sg", header: "Signal", cell: (r) => (r.signal ? <Badge tone={SIGNAL[r.signal][0]} dot={false}>{SIGNAL[r.signal][1]}</Badge> : <span className="k-muted">–</span>) },
            ]} />
          {(st2.missing.length > 0 || st2.problems.length > 0) && <p className="k-note">Skipped: {[...st2.missing, ...st2.problems].join(" · ")}</p>}
        </Card>
      )}
      <p className="k-note inv-text">
        {scan.id === "st_s2"
          ? "Stage uses the 150-day average and its 20-day slope; Supertrend uses 10 days and 3× the average daily range (ATR). "
          : "A match says the rule held on the date shown, on daily candles. "}
        Past signals don't predict future returns, and nothing here is investment advice.
      </p>
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
  // the summary reads the chart: the same ones as are drawn, so its counts add up to "n of N on the chart"
  const names = (q: Quadrant) => all.filter((r) => r.quadrant === q).map((r) => r.name);
  const entered = all.filter((r) => r.quadrant === "leading" && r.moved && r.moved !== "leading").map((r) => r.name);
  const unit = interval === "weekly" ? "week" : "day";
  const few = (xs: string[], n = 5) => !xs.length ? "none" : xs.length <= n + 1 ? xs.join(", ") : `${xs.slice(0, n).join(", ")} and ${xs.length - n} more`;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/rotation")} title="Sector rotation" asOf={out?.as_of} asOfLabel="Closes up to" asOfTz={marketTz(region)}
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
          <Field label="Trail" info={`How many ${unit}s of each one's path to draw behind its dot.`} infoLabel="About the trail">
            {(id) => <Range id={id} min={1} max={12} value={tail} onChange={setTail} valueText={`${tail} ${unit}${tail === 1 ? "" : "s"}`} testId="rot-trail" />}
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
            <span className="k-small k-muted" data-testid="rot-count">{rows.length === all.length ? `All ${all.length}` : `${rows.length} of ${all.length}`} on the chart · {out.interval === "weekly" ? "weekly" : "daily"} closes{out.as_of ? ` to ${fmtDate(out.as_of)}` : ""}{step !== null ? ` · replaying ${unit} ${step} of ${out.tail}` : ""}</span>
            {rows.length > 0 && (
              <div className="rot-read">
                {([["leading", `stronger than ${drilled && out.parent ? out.parent.name : "the market"} and still gaining`], ["improving", "weaker, but picking up"],
                   ["weakening", "stronger, but losing pace"], ["lagging", "weaker and still slipping"]] as [Quadrant, string][]).map(([q, says]) => (
                  <div key={q}><QuadrantTag q={q} /><span className="k-muted k-small">{says}</span><span className="k-small" data-testid={`rot-${q}`}>{names(q).length ? `${names(q).length} of ${all.length} · ${few(names(q))}` : `none of ${all.length}`}</span></div>
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
          <p className="k-note">Heading is the way its dot moved over the trail: → stronger, ← weaker, ↑ gaining pace, ↓ losing pace, and the diagonals both at once. The counts above are for all {all.length}, not only the ones ticked.</p>
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
interface AllItem { id: string; symbol: string; company: string | null; at: string; category: string; label: string; severity: "red" | "amber" | "info"; subject: string; url: string | null }
interface FlagType { id: string; label: string; severity: "red" | "amber"; count: number }
interface AllOut {
  region: Region; scope: "all" | "mine"; items: AllItem[]; total: number; page: number; pages: number; size: number; from: string; to: string; flag: string;
  companies: number; types: FlagType[]; as_of: string | null; updated_at: string | null; covers: string; note: string; watchlist: number | null;
}

const RANGES = [{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }, { value: "365", label: "Last year" }];
const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysBack = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return isoDay(d); };

/** India watchlist: each company's last 3 months in one card, with the evening message switch. */
function WatchlistFilings({ pro }: { pro: boolean }) {
  const { fail, notify } = useApp();
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
      notify(r.alerts ? `You'll get a message each evening (${data.send_at} IST) when a stock you hold or watch files a red flag.` : "Filing alerts off.");
    } catch (e) { fail(e); }
  };

  return (
    <>
      {data && (
        <Card>
          <CheckField checked={data.alerts} onChange={toggleAlerts}
            label={<>Message me each evening when a stock I hold or watch files a red flag or something to look closer at
              <Info>{`Checked once a day at ${data.send_at} IST, for the Indian stocks in your holdings and your watchlist. Sent by phone notification, Telegram or email, whichever you set up in Settings.`}</Info></>} />
        </Card>
      )}
      {busy && <Card><Skeleton label="Reading each company's filings" lines={4} /></Card>}
      {error && <ErrorState title="The filings couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {data && !busy && (data.rows.length === 0 && data.problems.length === 0
        ? <Card><EmptyState title="No Indian stocks held or watched yet" action={{ label: "Find a company", to: "/research?region=IN" }}>Add your holdings, or open a company and press Watch: their filings show up here.</EmptyState></Card>
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
    </>
  );
}

/** The stored red-flag filings of every company (or the user's watchlist in the US), newest first, paged, with the type,
 * date and company filters. Everything in the address, so a filtered list can be shared. */
function AllFilings({ region, scope, pro }: { region: Region; scope: "all" | "mine"; pro: boolean }) {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<AllOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const flag = params.get("flag") ?? "";
  const range = params.get("range") ?? "90";
  const frmP = params.get("frm") ?? "";
  const toP = params.get("to") ?? "";
  const qP = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [text, setText] = useState(qP);

  const setParam = (changes: Record<string, string | null>, keepPage = false) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) p.set(k, v); else p.delete(k); }
    if (!keepPage && !("page" in changes)) p.delete("page");
    setParams(p, { replace: true });
  };
  useEffect(() => { if (!qP) setText(""); }, [qP]);          // the filters were reset (another market): so is the box
  useEffect(() => {
    const t = setTimeout(() => { if (text !== qP) setParam({ q: text.trim() || null }); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const custom = range === "custom";
  const frm = custom ? frmP : daysBack(Number(range) || 90);
  const to = custom ? toP : "";
  useEffect(() => {
    if (!pro) return;
    let live = true;
    setError(null);
    const qs = new URLSearchParams({ region, scope, flag, frm, to, q: qP, page: String(page), size: "25" });
    api<AllOut>(`/research/redflags?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [pro, region, scope, flag, frm, to, qP, page, tries]);

  if (!pro) return null;
  const noun = scope === "mine" ? "on your watchlist" : "across companies";
  return (
    <>
      <Card>
        <CardHead title={scope === "mine" ? "Your watchlist's red flags" : "Red flags across companies"}
          info={data ? <>{data.covers}. {data.as_of ? `Read through ${asOf(data.as_of, { tz: marketTz(region) })}. ` : ""}Filings are read once a day in the evening, so today's may not be in yet.</> : undefined} />
        <FieldGroup label="Type of flag" wide>
          <ChipBar label="Flag types" value={flag} onChange={(v) => setParam({ flag: v || null })}
            options={[{ value: "", label: "All types" }, ...(data?.types ?? []).map((t) => ({ value: t.id, label: `${t.label} · ${t.count}` }))]} />
        </FieldGroup>
        <FieldGroup label="Dates" wide>
          <ChipBar label="Date range" value={range} onChange={(v) => setParam({ range: v === "90" ? null : v, frm: null, to: null })}
            options={[...RANGES, { value: "custom", label: "Pick dates" }]} />
        </FieldGroup>
        <FormGrid label="Filter the filings" onSubmit={(e) => e.preventDefault()}>
          {custom && <DateField label="From" value={frmP} max={isoDay(new Date())} onChange={(d) => setParam({ frm: d || null })} />}
          {custom && <DateField label="To" value={toP} max={isoDay(new Date())} onChange={(d) => setParam({ to: d || null })} />}
          <Field label="Find a company" optional placeholder={region === "IN" ? "Like RELIANCE or Tata" : "Like AAPL or Apple"} value={text}
            onChange={(e) => setText(e.target.value)} autoComplete="off" />
        </FormGrid>
      </Card>
      {error && <ErrorState title="The red flags couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {!data && !error && <Card><Skeleton label="Opening the stored filings" lines={4} /></Card>}
      {data && (
        scope === "mine" && data.watchlist === 0 ? (
          <Card><EmptyState title={`Your ${REGION_NAME[region]} watchlist is empty`} action={{ label: "Find a company", to: `/research?region=${region}` }}>Open a company and press Watch: its red flags show up here.</EmptyState></Card>
        ) : (
          <Card>
            <CardHead title={`${data.total.toLocaleString("en-IN")} filing${data.total === 1 ? "" : "s"} ${noun}`}
              actions={<span className="k-small k-muted">{data.companies.toLocaleString("en-IN")} compan{data.companies === 1 ? "y" : "ies"} · {asOf(data.from)} to {asOf(data.to)}</span>} />
            <DataTable label="Red-flag filings, newest first" rows={data.items} rowKey={(r) => r.id} empty="Nothing matches these filters."
              columns={[
                { key: "d", header: "Filed", cell: (r) => asOf(r.at.slice(0, 10)) ?? "–" },
                { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (r) => (
                  <><Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}#filings`}><b>{r.symbol}</b></Link>
                    {r.company && r.company !== r.symbol && <span className="k-sub-line">{r.company}</span>}</>) },
                { key: "f", header: "Flag", wrap: true, cell: (r) => <Badge tone={r.severity === "red" ? "warn" : "plain"} dot={false}>{r.severity === "red" ? "⚑ " : ""}{r.label}</Badge> },
                { key: "s", header: "The filing", wrap: true, cell: (r) => (
                  <>{r.subject}{r.url && <span className="k-sub-line"><a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Open the filing ↗</a></span>}</>) },
              ]} />
            <Pager page={data.page} pages={data.pages} total={data.total} noun="filings" onPage={(n) => setParam({ page: n > 1 ? String(n) : null }, true)} />
          </Card>
        )
      )}
    </>
  );
}

export function FilingsPage() {
  const { me } = useApp();
  const pro = !!me?.plan_info?.features?.filings;
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "all" ? "all" : "mine";
  const pickView = (v: string) => { const p = new URLSearchParams(params); if (v === "all") p.set("view", "all"); else p.delete("view"); p.delete("page"); setParams(p, { replace: true }); };
  const pickRegion = (r: Region) => { setRegion(r); const p = new URLSearchParams(params); p.set("region", r); for (const k of ["flag", "page", "q", "frm", "to", "range"]) p.delete(k); setParams(p, { replace: true }); };

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/filings")} title="Filings and red flags"
        lede={region === "IN" ? "What companies told the exchange that is worth a closer read: fund raises, pledges, resignations, defaults." : "What S&P 500 companies told the SEC in a Form 8-K that is worth a closer read: bankruptcy, delisting, auditor and officer changes."}
        info={region === "IN"
          ? "Fund raises (QIP, preferential, rights, warrants), promoter pledges, auditor and director resignations, defaults, regulator action and rating downgrades. The last 3 months of the stocks you hold and watch, or the latest from every company."
          : "Bankruptcy, a delisting notice, a change of auditor, financial statements that can no longer be relied on, and director or officer changes. Your watchlist, or the latest from every S&P 500 company."} infoLabel="What counts" />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={pickRegion} />
        <Seg label="Which companies" value={view} onChange={pickView} options={[{ value: "mine", label: region === "IN" ? "Your stocks" : "Your watchlist" }, { value: "all", label: "All companies" }]} />
      </div>
      {!pro && <PlanNote>Red flags for your whole watchlist, with an evening alert, and the latest red flags across every company are on the Basic plan. Each company's own page shows its red flags on every plan.</PlanNote>}
      {view === "mine" && region === "IN" ? <WatchlistFilings pro={pro} /> : <AllFilings region={region} scope={view} pro={pro} />}
      <p className="k-note inv-text">
        {region === "IN"
          ? "From the companies' own filings with the exchange. Labels come from fixed keyword rules; a label is a reason to read the filing, not a verdict on the company, and nothing here is investment advice."
          : "From the Form 8-K items companies file with the SEC. The label names the item; it is a reason to read the filing, not a verdict on the company, and nothing here is investment advice."}
      </p>
    </div>
  );
}
