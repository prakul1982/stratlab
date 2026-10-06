import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf, safeHref } from "../../lib/format";
import { loadFoChanges, type FoEvent, type FoKind, type FoView } from "../../lib/foChanges";
import { Info } from "../../components/ui";
import { Earlier } from "../../components/Earlier";
import { Badge, Card, CardHead, CheckField, ChipBar, EmptyState, ErrorState, PageHeader, Skeleton } from "../../components/kit";
import { Search } from "../../components/Icons";
import "./trade.css";
import "./fo.css";

/* /trade/fo-changes: one dated list of the exchange's changes to its F&O contracts: stocks entering and leaving F&O
 * (with the last series they trade), lot-size revisions (old and new lot, and when they apply) and expiry-day and
 * session changes, from the exchange's contract file and circulars. Each line says the change in a sentence, with the
 * circulars it rests on under it. Free to view; an alert when a change touches your watchlist or paper sessions is on
 * Basic. Facts only. Built from the kit (components/kit). */

type Filter = "all" | FoKind;
const FILTERS: [Filter, string][] = [["all", "All"], ["exit", "Leaving"], ["entry", "Entering"], ["lot", "Lot sizes"], ["expiry", "Expiry and sessions"],
  ["circular", "Other circulars"]];
const TAG: Record<FoKind, string> = { exit: "Leaving F&O", entry: "Entering F&O", lot: "Lot size", expiry: "Expiry or session", circular: "Circular" };
const TONE: Record<FoKind, "warn" | "ok" | "plain"> = { exit: "warn", entry: "ok", lot: "plain", expiry: "plain", circular: "plain" };

const longDay = (iso: string) => asOf(iso.slice(0, 10)) ?? iso;

function symbolsOf(e: FoEvent): string[] {
  return e.symbol ? [e.symbol] : e.symbols ?? [];
}

function Row({ e, mine }: { e: FoEvent; mine: Set<string> }) {
  const syms = symbolsOf(e);
  const yours = syms.some((s) => mine.has(s));
  return (
    <li className="fo-row" data-kind={e.kind} data-symbol={e.symbol ?? ""}>
      <div className="k-row">
        <Badge tone={TONE[e.kind]} dot={false}>{TAG[e.kind]}</Badge>
        {syms.map((s) => e.segment === "index" ? <b key={s}>{s}</b>
          : <Link key={s} className="link" to={`/research/IN/${encodeURIComponent(s)}`}><b>{s}</b></Link>)}
        {yours && <Badge tone="ok" dot={false}>Your watchlist or sessions</Badge>}
      </div>
      <p className="k-small">{e.text}</p>
      {e.sources && e.sources.length > 0 && (
        <ul className="fo-sources" aria-label="Sources">
          {e.sources.map((s, i) => (
            <li key={`${s.no}${i}`} className="k-note">
              Source: {safeHref(s.url) ? <a className="link" href={safeHref(s.url)} target="_blank" rel="noopener noreferrer">{s.no ? `Circular ${s.no}: ` : ""}{s.subject}</a>
                : <>{s.no ? `Circular ${s.no}: ` : ""}{s.subject}</>}{s.date ? ` · ${longDay(s.date)}` : ""}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function Day({ day, rows, mine }: { day: string; rows: FoEvent[]; mine: Set<string> }) {
  return (
    <div className="k-stack k-tight fo-day">
      <h3 className="k-sub">{longDay(day)}</h3>
      <ul className="fo-list">{rows.map((e) => <Row key={e.id} e={e} mine={mine} />)}</ul>
    </div>
  );
}

export function FoChangesPage() {
  const { fail } = useApp();
  const [v, setV] = useState<FoView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [onlyMine, setOnlyMine] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    setError(null);
    loadFoChanges(true).then((x) => (x ? setV(x) : setError("The F&O contract changes couldn't be read. Try again in a minute.")));
  }, [again]);

  const mine = useMemo(() => new Set(v?.mine ?? []), [v]);
  const shown = useMemo(() => {
    if (!v) return [];
    const term = q.trim().toUpperCase();
    return v.events.filter((e) => (filter === "all" || e.kind === filter)
      && (!onlyMine || symbolsOf(e).some((s) => mine.has(s)))
      && (!term || symbolsOf(e).some((s) => s.includes(term)) || (e.subject ?? "").toUpperCase().includes(term)));
  }, [v, filter, onlyMine, q, mine]);
  // what is still ahead comes first, soonest first; what has passed is folded below it, newest first
  const groups = useMemo(() => {
    const out: [string, FoEvent[]][] = [];
    for (const e of shown) {
      const last = out[out.length - 1];
      if (last && last[0] === e.date) last[1].push(e);
      else out.push([e.date, [e]]);
    }
    const today = v?.today ?? "";
    return { ahead: out.filter(([d]) => d >= today).reverse(), past: out.filter(([d]) => d < today) };
  }, [shown, v]);
  const narrowed = filter !== "all" || onlyMine || !!q.trim();

  const setAlert = async (on: boolean) => {
    if (!v) return;
    try {
      const a = await api<FoView["alerts"]>("/trade/fo-changes/alerts", { method: "PUT", body: { on } });
      setV({ ...v, alerts: a });
    } catch (e) { fail(e); }
  };
  const a = v?.alerts;

  return (
    <div className="k-page fo-page">
      <PageHeader eyebrow="Trade · F&O desk" title="F&O changes" asOf={v?.as_of} asOfLabel="Checked"
        lede="Stocks entering and leaving F&O, lot-size revisions, and changes to expiry days and sessions, each with the exchange's circular it rests on. Facts, not advice."
        info={v ? <span data-testid="fo-asof">{v.sources.map((s) => `${s.label} ${s.as_of ? `as of ${longDay(s.as_of)}` : "not read yet"}${s.failed ? " (couldn't be refreshed since)" : ""}`).join(" · ")}. {v.note}</span> : undefined}
        infoLabel="Where this comes from" />
      {error ? <ErrorState title="The changes couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !v || !a ? <Card><Skeleton label="Reading the exchange's changes" /></Card>
        : (
          <>
            <Card label="Alert" compact>
              <CardHead level={3} title="Alert" />
              {a.allowed ? (
                <CheckField checked={a.on} onChange={setAlert}
                  label={<>Tell me when a change touches a stock on my watchlist or in a running paper session
                    <Info>Checked twice a trading day, before the open and in the evening. Each change is sent once, by phone notification, Telegram or email, whichever you set up on the Account page.</Info></>} />
              ) : (
                <p className="k-small">Alerts on these changes for your watchlist and paper sessions are on the {a.plan} plan. <Link className="link" to="/plans">See the {a.plan} plan</Link></p>
              )}
              {a.allowed && a.on && !a.channels.length && <span className="k-note">Nowhere to send it yet: add a phone, Telegram or a confirmed email on the <Link className="link" to="/account">Account</Link> page.</span>}
              {v.mine.length > 0 && <span className="k-note">Watching {v.mine.length} Indian symbol{v.mine.length === 1 ? "" : "s"} from your watchlist and paper sessions.</span>}
            </Card>

            <Card label="Every change">
              <CardHead title="Every change" />
              <div className="k-toolbar">
                <ChipBar label="Kind of change" value={filter} onChange={(f) => setFilter(f as Filter)} options={FILTERS.map(([value, label]) => ({ value, label }))} />
                <label className="k-search sf-search"><Search size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a symbol" aria-label="Find a symbol" /></label>
                {v.mine.length > 0 && <CheckField label="Only my watchlist and sessions" checked={onlyMine} onChange={setOnlyMine} />}
              </div>
              {!v.events.length ? (
                <EmptyState title="No changes read yet">The exchange's contract file and circulars are read twice a trading day; changes show here once they are.</EmptyState>
              ) : !groups.ahead.length && !groups.past.length ? (
                <p className="k-small k-muted">No changes match.</p>
              ) : (
                <div className="k-stack">
                  {groups.ahead.length > 0 && <span className="k-eyebrow">Coming up</span>}
                  {groups.ahead.map(([day, rows]) => <Day key={day} day={day} rows={rows} mine={mine} />)}
                  {/* a narrowed list is short, so its past changes show without a click */}
                  <Earlier key={narrowed ? "narrowed" : "all"} label="Earlier changes" count={groups.past.reduce((n, [, r]) => n + r.length, 0)} open={narrowed || !groups.ahead.length}>
                    {groups.past.map(([day, rows]) => <Day key={day} day={day} rows={rows} mine={mine} />)}
                  </Earlier>
                </div>
              )}
            </Card>
          </>
        )}
    </div>
  );
}
