import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf } from "../../lib/format";
import { loadFoChanges, type FoEvent, type FoKind, type FoView } from "../../lib/foChanges";
import { Empty, Info, Loading } from "../../components/ui";

/* /trade/fo-changes: one dated list of the exchange's changes to its F&O contracts: stocks entering and leaving F&O
 * (with the last series they trade), lot-size revisions (old and new lot, and when they apply) and expiry-day and
 * session changes, from the exchange's contract file and circulars. Free to view; an alert when a change touches your
 * watchlist or paper sessions is on Basic. Facts only. */

type Filter = "all" | FoKind;
const FILTERS: [Filter, string][] = [["all", "All"], ["exit", "Leaving"], ["entry", "Entering"], ["lot", "Lot sizes"], ["expiry", "Expiry and sessions"],
  ["circular", "Other circulars"]];
const TAG: Record<FoKind, string> = { exit: "Leaving F&O", entry: "Entering F&O", lot: "Lot size", expiry: "Expiry or session", circular: "Circular" };

const longDay = (iso: string) => asOf(iso.slice(0, 10)) ?? iso;

function symbolsOf(e: FoEvent): string[] {
  return e.symbol ? [e.symbol] : e.symbols ?? [];
}

function Row({ e, mine }: { e: FoEvent; mine: Set<string> }) {
  const syms = symbolsOf(e);
  const yours = syms.some((s) => mine.has(s));
  return (
    <li className="fo-row" data-kind={e.kind} data-symbol={e.symbol ?? ""}>
      <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
        <span className={`fo-tag fo-${e.kind}`}>{TAG[e.kind]}</span>
        {syms.map((s) => e.segment === "index" ? <b key={s}>{s}</b>
          : <Link key={s} className="link" to={`/research/IN/${encodeURIComponent(s)}`}><b>{s}</b></Link>)}
        {yours && <span className="fo-yours">Your watchlist or sessions</span>}
      </div>
      <p className="small">{e.text}</p>
      <span className="tiny muted">
        {e.source === "circular" ? "Exchange circular" : "Exchange contract file"}{e.seen ? ` · first seen ${longDay(e.seen)}` : ""}
      </span>
    </li>
  );
}

function AlertCard({ v, onChange }: { v: FoView; onChange: (on: boolean) => void }) {
  const a = v.alerts;
  return (
    <section className="card stack" style={{ gap: 8 }} aria-labelledby="fo-alert-h">
      <h2 id="fo-alert-h" className="h3">Alert</h2>
      {a.allowed ? (
        <label className="row small fo-alert" style={{ gap: 10 }}>
          <input type="checkbox" checked={a.on} onChange={(e) => onChange(e.target.checked)} />
          Tell me when a change touches a stock on my watchlist or in a running paper session
          <Info>{"Checked twice a trading day, before the open and in the evening. Each change is sent once, by phone notification, Telegram or email, whichever you set up on the Account page."}</Info>
        </label>
      ) : (
        <p className="small">Alerts on these changes for your watchlist and paper sessions are on the {a.plan} plan. <Link className="link" to="/plans">See the {a.plan} plan</Link></p>
      )}
      {a.allowed && a.on && !a.channels.length && <p className="tiny muted">Nowhere to send it yet: add a phone, Telegram or a confirmed email on the <Link className="link" to="/account">Account</Link> page.</p>}
      {v.mine.length > 0 && <p className="tiny muted">Watching {v.mine.length} Indian symbol{v.mine.length === 1 ? "" : "s"} from your watchlist and paper sessions.</p>}
    </section>
  );
}

export function FoChangesPage() {
  const { fail } = useApp();
  const [v, setV] = useState<FoView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [onlyMine, setOnlyMine] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    loadFoChanges(true).then((x) => (x ? setV(x) : setError("The F&O contract changes couldn't be read. Try again in a minute.")));
  }, []);

  const mine = useMemo(() => new Set(v?.mine ?? []), [v]);
  const shown = useMemo(() => {
    if (!v) return [];
    const term = q.trim().toUpperCase();
    return v.events.filter((e) => (filter === "all" || e.kind === filter)
      && (!onlyMine || symbolsOf(e).some((s) => mine.has(s)))
      && (!term || symbolsOf(e).some((s) => s.includes(term)) || (e.subject ?? "").toUpperCase().includes(term)));
  }, [v, filter, onlyMine, q, mine]);
  const coming = useMemo(() => (v?.events ?? []).filter((e) => e.upcoming && e.source !== "circular" && e.kind !== "circular"), [v]);
  const groups = useMemo(() => {
    const out: [string, FoEvent[]][] = [];
    for (const e of shown) {
      const last = out[out.length - 1];
      if (last && last[0] === e.date) last[1].push(e);
      else out.push([e.date, [e]]);
    }
    return out;
  }, [shown]);

  const setAlert = async (on: boolean) => {
    if (!v) return;
    try {
      const a = await api<FoView["alerts"]>("/trade/fo-changes/alerts", { method: "PUT", body: { on } });
      setV({ ...v, alerts: a });
    } catch (e) { fail(e); }
  };

  return (
    <div className="stack fo-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="page-title">F&amp;O contract changes</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>Stocks entering and leaving F&amp;O with the last series they trade, lot-size revisions with the old and new lot, and changes to expiry days and sessions. From the exchange's contract file and circulars: facts, not advice.</p>
        {v && <p className="tiny muted as-of" data-testid="fo-asof">
          {v.sources.map((s) => `${s.label} ${s.as_of ? `as of ${longDay(s.as_of)}` : "not read yet"}${s.failed ? " (couldn't be refreshed since)" : ""}`).join(" · ")}
        </p>}
      </div>
      {error ? <div className="banner">{error}</div>
        : !v ? <Loading label="Reading the exchange's changes" />
        : (
          <>
            <div className="grid2" style={{ alignItems: "start" }}>
              <section className="card stack" style={{ gap: 10 }} aria-labelledby="fo-coming-h">
                <h2 id="fo-coming-h" className="h3">Coming up</h2>
                {coming.length ? (
                  <ul className="fo-list">
                    {coming.slice().reverse().slice(0, 8).map((e) => (
                      <li key={e.id} className="fo-row" data-kind={e.kind}>
                        <span className="tiny muted">{longDay(e.date)}</span>
                        <p className="small">{e.text}</p>
                      </li>
                    ))}
                  </ul>
                ) : <p className="small muted">No exits, entries or lot changes coming up in the exchange's contract file.</p>}
              </section>
              <AlertCard v={v} onChange={setAlert} />
            </div>

            <section className="stack" style={{ gap: 12 }} aria-labelledby="fo-all-h">
              <h2 id="fo-all-h" className="h3">Every change</h2>
              <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
                <div className="seg" role="group" aria-label="Kind of change">
                  {FILTERS.map(([f, l]) => <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>{l}</button>)}
                </div>
                <input className="input" style={{ maxWidth: 220 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a symbol" aria-label="Find a symbol" />
                {v.mine.length > 0 && <label className="row small" style={{ gap: 8 }}>
                  <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />Only my watchlist and sessions
                </label>}
              </div>
              {!v.events.length ? (
                <Empty title="No changes read yet">The exchange's contract file and circulars are read twice a trading day; changes show here once they are.</Empty>
              ) : !groups.length ? (
                <p className="small muted">No changes match.</p>
              ) : (
                <div className="stack" style={{ gap: 14 }}>
                  {groups.map(([day, rows]) => (
                    <div key={day} className="stack fo-day" style={{ gap: 6 }}>
                      <h3 className="eyebrow">{longDay(day)}{day >= v.today ? " · coming up" : ""}</h3>
                      <ul className="fo-list">{rows.map((e) => <Row key={e.id} e={e} mine={mine} />)}</ul>
                    </div>
                  ))}
                </div>
              )}
            </section>
            <p className="tiny muted">{v.note}</p>
          </>
        )}
    </div>
  );
}
