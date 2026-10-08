import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { publicGet, type ApiError } from "../lib/http";
import { applySeo, seoFor } from "../lib/seo";
import { groupLabel, plainTerms } from "../lib/plainTerms";
import { pct, TF_NAME } from "../lib/format";
import { checksLine } from "../lib/tradeUi";
import { signIn } from "../lib/signin";
import { Search } from "../components/Icons";
import { PublicFrame } from "../components/PublicFrame";
import { Rules, shownStats, VERDICTS, type LibEntry } from "../components/LibraryBits";
import { STATUS_NAME, VerdictBadge } from "../components/ui";
import { Badge } from "../components/kit/Badge";
import { Card, CardHead } from "../components/kit/Card";
import { Select } from "../components/kit/Form";
import { PageHeader } from "../components/kit/PageHeader";
import { Stat, StatRow } from "../components/kit/Stat";
import { EmptyState, ErrorState, Skeleton } from "../components/kit/States";
import "./trade/trade.css";

/* StratLab's own library strategies, open to anyone and read only: the rules that were tested and the verdict each earned,
 * as the app's own backtest gave it. Copying one and re-testing it needs an account, so that button says it goes to Google.
 * Only entries StratLab published itself come from the server (/public/library), never a user's. */

const CHECK_NAME: Record<string, string> = { unseen: "Unseen years", nearby: "Nearby settings", shuffle: "Bad-luck drawdown", sample: "Enough trades" };
const MARKETS: [string, string][] = [["", "Every market"], ["IN", "India"], ["US", "United States"]];
const NOTE = "Tested by StratLab on past prices, for research and paper trading. A verdict describes the past, not what comes next, and nothing here is investment advice.";

const where = (e: LibEntry) => e.group ? groupLabel(e.group.name, e.group.members?.length) : e.instrument?.symbol ?? e.market;
const tone = (n: number | null) => (n == null || n === 0 ? undefined : n > 0 ? "up" as const : "down" as const);

const GoogleCopy = ({ label = "Continue with Google to copy and re-test" }: { label?: string }) => (
  <button type="button" className="btn" onClick={() => void signIn("/library")}>{label}</button>
);

/** /library, signed out: StratLab's own strategies with their verdicts. */
export function PublicLibrary() {
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [again, setAgain] = useState(0);
  const [q, setQ] = useState("");
  const [verdict, setVerdict] = useState("");
  const [market, setMarket] = useState("");
  useEffect(() => {
    let live = true;
    setFailed(false);
    publicGet<{ entries: LibEntry[] }>("/public/library").then((r) => { if (live) setRows(r.entries); }).catch(() => { if (live) { setRows([]); setFailed(true); } });
    return () => { live = false; };
  }, [again]);
  const shown = useMemo(() => (rows ?? []).filter((e) => (!verdict || e.verdict.verdict === verdict) && (!market || e.market === market)
    && (!q.trim() || `${e.name} ${e.description} ${where(e)}`.toLowerCase().includes(q.trim().toLowerCase()))), [rows, q, verdict, market]);
  return (
    <PublicFrame action={<GoogleCopy label="Continue with Google" />}>
      <PageHeader eyebrow="Strategy library" title="StratLab's own strategies"
        lede="Well-known rule sets that StratLab ran through its own backtest and four checks, each shown with the verdict it earned, the ones that failed as plainly as the ones that held up. Open one to read its rules." />
      <Card label="Find a strategy">
        <div className="k-toolbar">
          <label className="k-search"><Search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: RSI, breakout, NIFTY" aria-label="Search the library" /></label>
          <Select label="Market" value={market} onChange={setMarket} options={MARKETS.map(([value, label]) => ({ value, label }))} />
          <Select label="Verdict" value={verdict} onChange={setVerdict} options={VERDICTS.map(([value, label]) => ({ value, label }))} />
        </div>
      </Card>
      {rows === null ? <Card><Skeleton label="Opening the library" /></Card>
        : failed ? <ErrorState title="The library couldn't be opened" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Your connection or ours dropped for a moment.</ErrorState>
        : shown.length === 0 ? <EmptyState title={rows.length ? "Nothing matches that." : "There are no strategies to show yet."}>{rows.length ? "Clear the search or the filters to see them all." : "Check back soon."}</EmptyState>
        : (
          <>
            <span className="k-small k-muted">{shown.length} strateg{shown.length === 1 ? "y" : "ies"}</span>
            <div className="k-cards">
              {shown.map((e) => {
                const sh = shownStats(e);
                return (
                  <Card key={e.id} label={plainTerms(e.name)}>
                    <div className="k-stack k-tight">
                      <span className="k-eyebrow">{where(e)} · {TF_NAME[e.tf] ?? e.tf} candles{e.side !== "long" ? ` · ${e.side === "both" ? "long and short" : "short"}` : ""}</span>
                      <CardHead title={plainTerms(e.name)} level={2} />
                      <span className="k-note k-row"><Badge tone="ok" dot={false}>{e.badge ?? "StratLab"}</Badge><span>by {e.author}</span></span>
                    </div>
                    <div className="k-row"><VerdictBadge v={e.verdict.verdict} /><span className="k-note">{checksLine(e.verdict.passed, e.verdict.total)}</span>{!sh.ran && <Badge tone="plain" dot={false}>Not run</Badge>}</div>
                    {e.reason && <p className="k-note lib-reason">{e.reason}</p>}
                    <div className="k-mini-stats">
                      {([["After costs", sh.ret], ["Buy and hold", sh.buy_hold], ["Unseen years", sh.unseen]] as [string, number | null][])
                        .map(([k, n]) => <Stat key={k} label={k} value={n == null ? "–" : pct(n)} tone={tone(n)} />)}
                    </div>
                    <div className="k-row k-push"><Link className="btn sm" to={`/library/${encodeURIComponent(e.id)}`} aria-label={`Open the verdict and rules of ${plainTerms(e.name)}`}>Open the verdict and rules</Link></div>
                  </Card>
                );
              })}
            </div>
          </>
        )}
      <p className="k-note">{NOTE}</p>
    </PublicFrame>
  );
}

/** /library/<id>, signed out: one StratLab strategy with its verdict, its four checks, its figures and its rules. */
export function PublicLibraryEntry({ id }: { id: string }) {
  const [e, setE] = useState<LibEntry | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setE(null); setGone(null);
    publicGet<LibEntry>(`/public/library/${encodeURIComponent(id)}`)
      .then((r) => { if (live) setE(r); })
      .catch((x: ApiError) => { if (live) { setGone(x.status === 404 ? "That strategy isn't in StratLab's library." : x.message); document.title = "Strategy not found · StratLab"; } });
    return () => { live = false; };
  }, [id]);
  useEffect(() => {
    if (!e) return;
    const title = `${plainTerms(e.name)}: ${e.verdict.headline} · StratLab`;
    document.title = title;
    const desc = `${plainTerms(e.name)} on ${where(e)}: ${e.verdict.headline} ${e.reason ?? ""} Rules, results after costs and the four checks, as StratLab tested them on past prices.`.replace(/\s+/g, " ").trim();
    applySeo({ ...seoFor(`/library/${id}`, "public"), description: desc, canonical: seoFor(`/library/${id}`).canonical, index: true }, title);
  }, [e, id]);
  const sh = e ? shownStats(e) : null;
  return (
    <PublicFrame action={<GoogleCopy label="Continue with Google" />}>
      {!e && !gone && <Card><Skeleton label="Opening the strategy" /></Card>}
      {gone && <ErrorState title="This strategy isn't available" action={{ label: "See StratLab's strategies", to: "/library" }}>{gone}</ErrorState>}
      {e && sh && (
        <>
          <div className="k-stack">
            <span className="k-eyebrow">{plainTerms(e.name)} · {where(e)} · {TF_NAME[e.tf] ?? e.tf} candles</span>
            <h1 className={`verdict-head pub-head ${e.verdict.verdict}`}>{e.verdict.headline}</h1>
            <p className="k-lede">{e.verdict.summary}</p>
            {e.reason && <p className="k-small k-muted">{e.reason}</p>}
            <span className="k-note k-row"><Badge tone="ok" dot={false}>{e.badge ?? "StratLab"}</Badge><span>{e.range ? `Tested ${e.range.from} to ${e.range.to}` : "Tested on past prices"}</span></span>
          </div>
          <Card label="Results">
            <CardHead title="Results after costs" actions={<span className="k-note">{checksLine(e.verdict.passed, e.verdict.total)}</span>} />
            <StatRow label="Results">
              <Stat item label="Return after costs" value={sh.ret == null ? "–" : pct(sh.ret)} tone={tone(sh.ret)} />
              <Stat item label="Buy and hold" value={sh.buy_hold == null ? "–" : pct(sh.buy_hold)} tone={tone(sh.buy_hold)} />
              <Stat item label="Unseen years" value={sh.unseen == null ? "–" : pct(sh.unseen)} tone={tone(sh.unseen)} />
              <Stat item label="Worst fall" value={sh.mdd == null ? "–" : pct(sh.mdd)} tone={sh.mdd == null ? undefined : "down"} />
              <Stat item label="Trades" value={e.stats.trades == null ? "–" : String(e.stats.trades)} />
            </StatRow>
          </Card>
          {!!e.verdict.checks?.length && (
            <section className="pub-checks" aria-label="The four checks">
              {e.verdict.checks.map((c) => (
                <Card key={c.id} label={CHECK_NAME[c.id] ?? c.id}>
                  <CardHead level={3} title={CHECK_NAME[c.id] ?? c.id} actions={<Badge tone={c.status === "pass" ? "ok" : c.status === "fail" ? "warn" : "plain"}>{STATUS_NAME[c.status as keyof typeof STATUS_NAME] ?? c.status}</Badge>} />
                </Card>
              ))}
            </section>
          )}
          <Card label="The rules">
            <CardHead title="The rules that were tested" />
            <Rules s={e.strategy} />
            {e.description && <p className="k-small k-muted">{plainTerms(e.description)}</p>}
          </Card>
          <Card label="Copy and re-test">
            <CardHead title="Test it yourself" />
            <p className="k-small k-muted">Copy these rules into your own notebook and run them on your market and dates. Copying needs a free account; signing in only reads your name and email from Google.</p>
            <div className="k-row"><GoogleCopy /><Link className="btn quiet" to="/library">All StratLab strategies</Link></div>
          </Card>
          <p className="k-note">{NOTE}</p>
        </>
      )}
    </PublicFrame>
  );
}
