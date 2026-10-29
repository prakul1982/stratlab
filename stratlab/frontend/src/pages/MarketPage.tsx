import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { riskForCurrency } from "../lib/rules";
import type { GroupMember, Instrument, LiveRow, Market, Notebook } from "../lib/types";
import { LIMITS } from "../lib/plans";
import { parseCsv, saveUpload, type Candle } from "../lib/upload";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { SurvBadges } from "../components/Surveillance";
import { Card, CardHead, ChipBar, EmptyState, Field, FieldGroup, FormActions, FormGrid, Notice, PageHeader, Select, Skeleton, TilePicker } from "../components/kit";
import { HELP } from "../lib/help";
import { INDIA_FEED, offlineLine } from "../lib/dataBack";
import { NotebookProblem, useNotebook } from "./NotebookPage";
import "./trade/trade.css";
import { scrollBehavior } from "../lib/motion";

/* /n/:id/market: pick the market and instrument a notebook tests on, or a group, or your own CSV. Built from the kit
 * (components/kit). */

function localHours(m: Market): string {
  if (!m.hours) return "Your own session hours";
  if (!m.hours.open || !m.hours.close) return m.hours.days;
  // show the session in the viewer's own time zone
  const today = new Date();
  const toLocal = (hm: string) => {
    const [h, mi] = hm.split(":").map(Number);
    const guess = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate(), h, mi);
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: m.tz, year: "numeric", month: "numeric", day: "numeric",
      hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(new Date(guess));
    const get = (t: string) => +(parts.find((p) => p.type === t)?.value ?? 0);
    const shown = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
    const instant = guess - (shown - guess);   // the moment the market's clock reads h:mi
    return new Date(instant).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  };
  return `${toLocal(m.hours.open)}–${toLocal(m.hours.close)} your time, ${m.hours.days}`;
}

const STATUS: Record<Market["status"], string> = { live: "Live", offline: "Offline", soon: "Coming soon" };

type Preset = { id: string; name: string; market: string; symbols: string[]; count: number; as_of?: string };

/** Test on a group of instruments: a ready-made list, or your own picks. */
function GroupPicker({ nb, market, onDone }: { nb: Notebook; market: Market; onDone: () => void }) {
  const { fail, notify, refreshNotebooks, me } = useApp();
  const [presets, setPresets] = useState<Preset[]>([]);
  const current = nb.group && nb.group.market === market.id ? nb.group : null;
  const [pick, setPick] = useState<string | null>(current ? current.id : null);
  const [custom, setCustom] = useState<GroupMember[]>(current?.id === "custom" ? current.members : []);
  const [name, setName] = useState(current?.id === "custom" ? current.name : "My group");
  const [maxOpen, setMaxOpen] = useState(current?.maxOpen ?? 10);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Preset[]>(`/groups?market=${market.id}`).then(setPresets).catch(() => setPresets([])); }, [market.id]);
  useEffect(() => {
    if (location.hash !== "#group") return;
    const t = window.setTimeout(() => document.getElementById("group-h")?.scrollIntoView({ behavior: scrollBehavior(), block: "start" }), 300);
    return () => window.clearTimeout(t);
  }, [presets]);
  const preset = presets.find((p) => p.id === pick);
  const members: GroupMember[] = pick === "custom" ? custom : preset ? preset.symbols.map((symbol) => ({ symbol })) : [];
  const noun = market.id === "CRYPTO" ? "coins" : market.id === "FX" || market.id === "CDS" ? "pairs" : market.id === "MCX" || market.id === "CMDTY" ? "commodities" : "stocks";

  const overCap = me?.plan_info.group_size != null && members.length > me.plan_info.group_size;

  const save = async () => {
    if (members.length < 2) { notify(`Add at least two ${noun} to the group.`); return; }
    setBusy(true);
    try {
      await api(`/notebooks/${nb.id}`, { method: "PUT", body: { group: {
        id: pick === "custom" ? "custom" : pick, name: pick === "custom" ? (name.trim() || "My group") : preset!.name, market: market.id,
        maxOpen: Math.max(1, Math.min(maxOpen, members.length)), members } } });
      await refreshNotebooks();
      onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  return (
    <Card id="group-h" label="Test on a group">
      <CardHead title={`Or test on a group of ${noun}`} info={HELP.groupPick} infoLabel="About groups" />
      <p className="k-small k-muted">The same rules run on every {noun === "commodities" ? "commodity" : noun.slice(0, -1)} in the group at once, sharing one pot of capital, like a real intraday or momentum book.</p>
      <ChipBar label="Group" value={pick ?? ""} onChange={setPick} options={[...presets.map((p) => ({ value: p.id, label: `${p.name} (${p.count})` })), { value: "custom", label: "Build my own" }]} />
      {pick === "custom" && (
        <div className="k-stack">
          <FormGrid label="Group name">
            <Field label="Group name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
          </FormGrid>
          <InstrumentSearch market={market} compact onPick={(i) => {
            if (custom.length >= 50) { notify("A group can hold up to 50."); return; }
            if (!custom.some((m) => m.id === i.id)) setCustom([...custom, { id: i.id, symbol: i.symbol }]);
          }} />
        </div>
      )}
      {members.length > 0 && (
        <>
          {/* a ready-made list says how current it is: the index's members after its latest announced change (R51-004) */}
          {preset?.as_of && <p className="k-note" data-testid="group-as-of">The index's members as of {preset.as_of}, after its latest announced change.</p>}
          <div className="chip-row" role="group" aria-label={`The ${members.length} ${noun} in this group`} tabIndex={0}>
            {members.map((m) => (
              <span key={m.id ?? m.symbol} className="pill">{m.symbol}{market.id === "IN" && <> <SurvBadges region="IN" symbol={m.symbol} plain /></>}{pick === "custom" &&
                <button type="button" className="chip-x" aria-label={`Remove ${m.symbol}`} onClick={() => setCustom(custom.filter((x) => x !== m))}>×</button>}</span>
            ))}
          </div>
          <FormGrid label="Group limits" onSubmit={(e) => { e.preventDefault(); void save(); }}>
            <Field label="Positions open at once (max)" type="number" min={1} max={members.length} value={Math.min(maxOpen, members.length)} onChange={(e) => {
              const n = parseInt(e.target.value, 10); if (n >= 1 && n <= 50) setMaxOpen(n);
            }} />
            <FormActions>
              {/* a group over the plan's size can't be run, so the button is off and points at the note that says why (R76-001:
                  "Test on these 50 stocks" stayed pressable on Free under the "needs Pro" line) */}
              <button type="submit" className="btn" disabled={busy || overCap} aria-describedby={overCap ? "group-cap-note" : undefined}
                title={overCap ? `Your ${me!.plan_info.name} plan tests up to ${me!.plan_info.group_size} ${noun} in a group` : undefined}>
                {busy ? "Saving…" : `Test on these ${members.length} ${noun}`}</button>
            </FormActions>
          </FormGrid>
          {/* the plan's cap said here, before the press, with the plan that goes higher (R51-003: a 50-stock NIFTY group on
              Free said nothing until "Test on these 50 stocks" was refused) */}
          {overCap && (
            <p className="k-note" id="group-cap-note" data-testid="group-cap-note">Your {me!.plan_info.name} plan tests up to {me!.plan_info.group_size} {noun} in a group, so this one
              needs {members.length <= LIMITS.basic.group_size ? `Basic (up to ${LIMITS.basic.group_size})` : `Pro (up to ${LIMITS.pro.group_size})`}, or a smaller group of your own.
              {" "}<Link className="link" to="/plans">See plans</Link></p>)}
          <p className="k-note">For a portfolio, size trades by <b>fixed capital per trade</b> in the rules' costs and position size, so each position gets its share.</p>
        </>
      )}
    </Card>
  );
}

export function MarketPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { markets, notify, me } = useApp();
  const { nb, patch, flush, problem, reload } = useNotebook(id);
  const [sel, setSel] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ bars: Candle[]; skipped: number; file: string } | null>(null);
  const [upName, setUpName] = useState("");
  const [upCur, setUpCur] = useState("USD");
  const [upStep, setUpStep] = useState(1);
  const loc = useLocation();
  // a paper session already running this notebook's rules: it keeps trading what it started on whatever is picked here,
  // so that is said before a new pick (DP1-017: a running session stayed on the old instrument without a word)
  const [live, setLive] = useState<LiveRow | null>(null);
  useEffect(() => {
    if (!nb?.id) return;
    let on = true;
    const instId = nb.instrument && "id" in nb.instrument ? nb.instrument.id : null;
    api<LiveRow[]>("/live/sessions").then((rows) => {
      if (on) setLive(rows.find((r) => r.status === "running" && r.name === nb.name && (!instId || r.instrument?.id === instId)) ?? null);
    }).catch(() => undefined);
    return () => { on = false; };
  }, [nb?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!nb || sel) return;
    const asked = (loc.state as { market?: string } | null)?.market;
    const current = nb.instrument && "market" in nb.instrument ? nb.instrument.market : null;
    setSel(asked || current || markets.find((m) => m.status === "live" && m.id !== "CSV")?.id || "CRYPTO");
  }, [nb, markets, sel, loc.state]);

  if (!nb && problem) return <NotebookProblem problem={problem} retry={reload} />;
  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Where do you want to test it?" /><Card><Skeleton label="Opening markets" /></Card></div>;
  const market = markets.find((m) => m.id === sel);

  const choose = async (i: Instrument) => {
    patch({ instrument: i, instrumentId: i.id, strategy: { ...nb.strategy, risk: riskForCurrency(nb.strategy.risk, i.currency, { market: i.market, type: i.type, tf: nb.strategy.tf }) } }, true);
    if (await flush(true)) nav(`/n/${nb.id}`);      // a save that failed stays here, said, to be tried again
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    try {
      const parsed = parseCsv(await f.text());
      setUpload({ ...parsed, file: f.name });
      setUpName(f.name.replace(/\.(csv|txt)$/i, "").slice(0, 60));
    } catch (e) { notify((e as Error).message); }
  };

  const useUpload = async () => {
    if (!upload) return;
    const name = upName.trim() || "Uploaded data";
    saveUpload(nb.id, { name, currency: upCur, step: upStep, bars: upload.bars });
    patch({ instrument: { id: "CSV:upload", symbol: name, market: "CSV", currency: upCur }, instrumentId: `CSV:${name}` }, true);
    if (await flush(true)) nav(`/n/${nb.id}`);      // a save that failed stays here, said, to be tried again
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Where do you want to test it?" info={HELP.markets} infoLabel="About markets"
        lede={<><Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link> · The same rules run on any market. Prices, trading hours, currency and costs switch to match it.</>} />
      {live && (
        <div data-testid="market-live-note">
          <Notice tone="warn" role="note" action={{ label: "Open the session", to: `/paper/${live.id}` }}>
            A paper session is running these rules on {live.instrument?.symbol ?? "what this notebook tested on"}. A new pick here changes what the notebook tests, not the session: it keeps trading {live.instrument?.symbol ?? "the old one"} until you stop it. To paper trade the new pick, stop that session and start one from the notebook.
          </Notice>
        </div>
      )}

      <Card label="Market">
        <CardHead title="Pick a market" />
        <TilePicker label="Market" value={sel} onChange={setSel}
          groups={[{ title: "Markets", tiles: markets.map((m) => ({ value: m.id, title: `${[...m.symbol].length === 1 && m.symbol !== "+" ? m.symbol + " " : ""}${m.name}`, sub: `${m.venues}${m.status !== "live" ? ` · ${STATUS[m.status]}` : ""}` })) }]} />
        {market && market.status !== "soon" && (
          <p className="k-note">{market.name}: {market.what} · {localHours(market)} · Costs: {market.costs}</p>
        )}
      </Card>

      {market && market.status === "soon" && (
        <EmptyState title={`${market.name} is coming soon`}
          action={{ label: "Use your own data", onClick: () => setSel("CSV") }}>
          We're connecting a data source for {market.name}. Meanwhile, you can export candles from any charting site as a CSV and test on them with your own data.
        </EmptyState>
      )}
      {market && market.status === "offline" && (
        // India's data comes back with the daily data login, at the time the top banner gives, and no promise of a few minutes (DA-004)
        <Notice tone="warn">{INDIA_FEED.has(market.id) ? offlineLine(market.name, me?.data_note) : `Market data for ${market.name} is offline right now. Try again later.`}</Notice>
      )}

      {market && market.status === "live" && market.id !== "CSV" && (
        <Card label="Instrument">
          <CardHead title={`Search ${market.name}`} />
          <InstrumentSearch market={market} onPick={choose} autoFocus />
        </Card>
      )}
      {market && market.status === "live" && market.id !== "CSV" && <GroupPicker key={market.id} nb={nb} market={market} onDone={() => nav(`/n/${nb.id}`)} />}

      {market?.id === "CSV" && (
        <Card label="Upload candles">
          <CardHead title="Upload candles as a CSV" info={HELP.csv} infoLabel="What should the file look like?" />
          <p className="k-small k-muted">Any market, any timeframe. The first row should be headings: <span className="k-mono">date, open, high, low, close, volume</span>. Exports from charting sites, broker apps and Excel work as they are: commas or semicolons between the columns, dates as 2026-10-28 or 28-10-2026, and extra columns (an adjusted close, say) are ignored.</p>
          <label className="btn outline k-btn-end">
            Choose a CSV file
            <input type="file" accept=".csv,text/csv,.txt" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          {upload && (
            <>
              <p className="k-small">
                <b>{upload.bars.length.toLocaleString("en-IN")} candles</b> from {new Date(upload.bars[0].t).toLocaleDateString("en-GB")} to {new Date(upload.bars[upload.bars.length - 1].t).toLocaleDateString("en-GB")}
                {upload.skipped ? `, ${upload.skipped} rows skipped` : ""}.
              </p>
              <FormGrid label="About your data" onSubmit={(e) => { e.preventDefault(); void useUpload(); }}>
                <Field label="Name" maxLength={60} value={upName} onChange={(e) => setUpName(e.target.value)} />
                <Field label="Currency">{(fid) => <Select id={fid} value={upCur} onChange={setUpCur} options={["USD", "INR", "EUR", "GBP", "JPY", "USDT"].map((c) => ({ value: c, label: c }))} />}</Field>
                <FieldGroup label="Quantities" info={HELP.quantities}>
                  <Select label="Quantities" value={upStep} onChange={(v) => setUpStep(+v)} options={[{ value: 1, label: "Whole units (shares, lots)" }, { value: 0.0001, label: "Fractions (coins, forex)" }]} />
                </FieldGroup>
                <FormActions><button type="submit" className="btn">Test on this data</button></FormActions>
              </FormGrid>
              <p className="k-note">The file stays in this browser; only the candles are sent for each test.</p>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
