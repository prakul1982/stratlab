import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { riskForCurrency } from "../lib/rules";
import type { GroupMember, Instrument, Market, Notebook } from "../lib/types";
import { parseCsv, saveUpload, type Candle } from "../lib/upload";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { SurvBadges } from "../components/Surveillance";
import { Card, CardHead, ChipBar, EmptyState, Field, FieldGroup, FormActions, FormGrid, Notice, PageHeader, Select, Skeleton, TilePicker } from "../components/kit";
import { HELP } from "../lib/help";
import { NotebookProblem, useNotebook } from "./NotebookPage";
import "./trade/trade.css";

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

type Preset = { id: string; name: string; market: string; symbols: string[]; count: number };

/** Test on a group of instruments: a ready-made list, or your own picks. */
function GroupPicker({ nb, market, onDone }: { nb: Notebook; market: Market; onDone: () => void }) {
  const { fail, notify, refreshNotebooks } = useApp();
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
    const t = window.setTimeout(() => document.getElementById("group-h")?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    return () => window.clearTimeout(t);
  }, [presets]);
  const preset = presets.find((p) => p.id === pick);
  const members: GroupMember[] = pick === "custom" ? custom : preset ? preset.symbols.map((symbol) => ({ symbol })) : [];
  const noun = market.id === "CRYPTO" ? "coins" : market.id === "FX" || market.id === "CDS" ? "pairs" : market.id === "MCX" || market.id === "CMDTY" ? "commodities" : "stocks";

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
          <div className="chip-row">
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
              <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : `Test on these ${members.length} ${noun}`}</button>
            </FormActions>
          </FormGrid>
          <p className="k-note">For a portfolio, size trades by <b>fixed capital per trade</b> in the rules' costs and position size, so each position gets its share.</p>
        </>
      )}
    </Card>
  );
}

export function MarketPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { markets, notify } = useApp();
  const { nb, patch, flush, problem, reload } = useNotebook(id);
  const [sel, setSel] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ bars: Candle[]; skipped: number; file: string } | null>(null);
  const [upName, setUpName] = useState("");
  const [upCur, setUpCur] = useState("USD");
  const [upStep, setUpStep] = useState(1);
  const loc = useLocation();

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
    patch({ instrument: i, instrumentId: i.id, strategy: { ...nb.strategy, risk: riskForCurrency(nb.strategy.risk, i.currency) } }, true);
    await flush();
    nav(`/n/${nb.id}`);
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
    await flush();
    nav(`/n/${nb.id}`);
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Where do you want to test it?" info={HELP.markets} infoLabel="About markets"
        lede={<><Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link> · The same rules run on any market. Prices, trading hours, currency and costs switch to match it.</>} />

      <Card label="Market">
        <CardHead title="Pick a market" />
        <TilePicker label="Market" value={sel} onChange={setSel}
          groups={[{ title: "Markets", tiles: markets.map((m) => ({ value: m.id, title: `${[...m.symbol].length === 1 && m.symbol !== "+" ? m.symbol + " " : ""}${m.name}`, sub: `${m.venues}${m.status !== "live" ? ` · ${STATUS[m.status]}` : ""}` })) }]} />
        {market && market.status !== "soon" && (
          <p className="k-note">{market.name}: {market.what} · {localHours(market)} · costs: {market.costs}</p>
        )}
      </Card>

      {market && market.status === "soon" && (
        <EmptyState title={`${market.name} is coming soon`}
          action={{ label: "Use your own data", onClick: () => setSel("CSV") }}>
          We're connecting a data source for {market.name}. Meanwhile, you can export candles from any charting site as a CSV and test on them with your own data.
        </EmptyState>
      )}
      {market && market.status === "offline" && (
        <Notice tone="warn">Market data for {market.name} is offline right now. It usually comes back after the daily data login; try again in a few minutes.</Notice>
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
          <p className="k-small k-muted">Any market, any timeframe. The first row should be headings: <span className="k-mono">date, open, high, low, close, volume</span>. Most charting sites and brokers can export this.</p>
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
