import { useEffect, useId, useState } from "react";
import { publicGet, publicPost, type ApiError } from "../lib/http";
import { signIn } from "../lib/signin";
import { track } from "../lib/analytics";
import { Google } from "./IconsLite";
import { EmailWay } from "./EmailWay";
import { LIMITS } from "../lib/planCore";

/* Try one idea without signing in (conv101, P1): one of a few of the library's well-known rule sets on one of a few well-known stocks or
 * Bitcoin, run by the server's real backtest and verdict on five years of daily prices after costs (backend app/guest_try.py). Nothing is
 * saved; a few tries a day per visitor. The verdict is shown as the engine gives it, a loss as plainly as a gain, and the way to keep, change
 * or paper trade it is a free account. Loaded only when a visitor opens it (the landing page's own download stays under its budget). */

type Idea = { id: string; name: string; text: string };
type Inst = { id: string; market: string; symbol: string; name: string };
type Options = { ideas: Idea[]; instruments: Inst[]; per_day: number; days: number };
type Check = { id: string; status: "pass" | "warn" | "fail" | string };
type Result = {
  idea: Idea; instrument: Inst & { currency?: string | null }; range?: { from: string; to: string } | null; left: number; kept: boolean;
  verdict: { verdict: string; headline: string; summary?: string; passed: number; total: number; checks: Check[] };
  stats: { ret?: number | null; buy_hold?: number | null; mdd?: number | null; trades?: number | null; unseen?: number | null };
};

const CHECK_NAME: Record<string, string> = { unseen: "Unseen years", nearby: "Nearby settings", shuffle: "Bad-luck drawdown", sample: "Enough trades" };
const STATUS: Record<string, string> = { pass: "Passed", warn: "Warning", fail: "Failed" };
const MARKET: Record<string, string> = { IN: "India", US: "US", CRYPTO: "Crypto" };

/** A percentage with its sign and an arrow: ▲ green for a gain, ▼ red for a loss (the site's one rule for moves). */
function Pct({ v }: { v?: number | null }) {
  if (v == null || !Number.isFinite(v)) return <span className="muted">–</span>;
  const up = v >= 0;
  return <span className={`k-delta ${up ? "up" : "down"}`}>{up ? "▲" : "▼"} {up ? "+" : "−"}{Math.abs(v).toFixed(1)}%</span>;
}

const year = (iso?: string) => (iso ? new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }) : "");

export function GuestTry({ symbol: wanted, market: wantedMarket, where = "landing" }: { symbol?: string | null; market?: string | null; where?: string } = {}) {
  const [opts, setOpts] = useState<Options | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [idea, setIdea] = useState<string>("");
  const [inst, setInst] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [problem, setProblem] = useState<{ msg: string; limit: boolean } | null>(null);
  const base = useId();
  useEffect(() => {
    let live = true;
    publicGet<Options>("/public/try").then((o) => {
      if (!live) return;
      setOpts(o);
      setIdea(o.ideas[0]?.id ?? "");
      // a stock page's "test a strategy on X" link names the stock: picked here when it is one of these
      const pre = wanted ? o.instruments.find((i) => i.symbol.toUpperCase() === wanted.toUpperCase() && (!wantedMarket || i.market === wantedMarket.toUpperCase())) : null;
      setInst(pre?.id ?? o.instruments[0]?.id ?? "");
    }).catch((e: ApiError) => { if (live) setFailed(e?.message || "Couldn't load the ideas. Try again in a minute."); });
    return () => { live = false; };
  }, [wanted, wantedMarket]);

  const run = async () => {
    if (!idea || !inst || busy) return;
    setBusy(true); setProblem(null);
    const pick = opts?.instruments.find((i) => i.id === inst);
    track("guest try run", { kind: idea, region: pick?.market, source: where });
    try { setRes(await publicPost<Result>("/public/try", { idea, instrument: inst })); }
    catch (e) { const x = e as ApiError; setProblem({ msg: x?.message || "The test couldn't run. Try again in a minute.", limit: x?.status === 429 }); }
    finally { setBusy(false); }
  };
  const join = () => { track("guest try signup", { source: where }); void signIn("/new"); };

  if (failed) return <p className="small muted" role="status">{failed}</p>;
  if (!opts) return <div className="lp-card gt-card" aria-busy="true"><span className="lp-skel lp-skel-p" /><span className="lp-skel lp-skel-p" /></div>;
  const chosen = opts.ideas.find((i) => i.id === idea);
  return (
    <div className="lp-card gt-card stack g18" data-testid="guest-try">
      <fieldset className="gt-pick">
        <legend className="small"><b>1. Pick a rule set</b></legend>
        <div className="gt-chips" role="radiogroup" aria-label="Rule set">
          {opts.ideas.map((i) => (
            <button key={i.id} type="button" role="radio" aria-checked={idea === i.id} className={`gt-chip${idea === i.id ? " on" : ""}`}
              onClick={() => { setIdea(i.id); setRes(null); }}>{i.name}</button>
          ))}
        </div>
        {chosen && <p className="small muted gt-rule" id={`${base}-rule`}>{chosen.text}</p>}
      </fieldset>
      <fieldset className="gt-pick">
        <legend className="small"><b>2. Pick what to test it on</b></legend>
        <div className="gt-chips" role="radiogroup" aria-label="Stock or coin">
          {opts.instruments.map((i) => (
            <button key={i.id} type="button" role="radio" aria-checked={inst === i.id} className={`gt-chip${inst === i.id ? " on" : ""}`}
              title={`${i.name} (${MARKET[i.market] ?? i.market})`} onClick={() => { setInst(i.id); setRes(null); }}>{i.symbol}</button>
          ))}
        </div>
      </fieldset>
      <div className="row wrap g12">
        <button type="button" className="btn" onClick={() => void run()} disabled={busy} aria-describedby={`${base}-rule`}>
          {busy ? "Testing on five years of prices…" : "Run the test"}</button>
        <span className="small muted">Five years of daily prices, after every charge. Nothing is saved.</span>
      </div>
      {problem && (
        <div className="stack g8" role="alert">
          <p className="small">{problem.msg}</p>
          {problem.limit && <div className="row wrap g12"><button type="button" className="btn lp-cta" onClick={join}><Google />Sign up free with Google</button><EmailWay next="/new" /></div>}
        </div>
      )}
      {res && (
        <div className="gt-result stack g12" data-testid="guest-result" aria-live="polite">
          <div className="spread g8 wrap">
            <span className="eyebrow">{res.idea.name} · {res.instrument.name} ({res.instrument.symbol}){res.range ? ` · ${year(res.range.from)} to ${year(res.range.to)}` : ""}</span>
            <span className="lp-sample">Real test, not saved</span>
          </div>
          <b className="serif gt-headline">{res.verdict.headline}</b>
          {res.verdict.summary && <p className="small muted">{res.verdict.summary}</p>}
          <dl className="gt-stats">
            <div><dt className="small muted">After costs</dt><dd><Pct v={res.stats.ret} /></dd></div>
            <div><dt className="small muted">Buy and hold</dt><dd><Pct v={res.stats.buy_hold} /></dd></div>
            <div><dt className="small muted">On unseen years</dt><dd><Pct v={res.stats.unseen} /></dd></div>
            <div><dt className="small muted">Trades</dt><dd>{res.stats.trades ?? "–"}</dd></div>
          </dl>
          <div className="stack small lp-checklist">
            {res.verdict.checks.map((c) => <div key={c.id} className="spread"><span>{CHECK_NAME[c.id] ?? c.id}</span><span className={`badge ${c.status}`}>{STATUS[c.status] ?? c.status}</span></div>)}
          </div>
          <p className="small muted">Facts about the past, not advice: a result says nothing about what comes next.</p>
          <div className="gt-next stack g8">
            <b>Keep this test, change its rules, or write your own idea in plain words</b>
            <div className="row wrap g12">
              <button type="button" className="btn lp-cta" onClick={join}><Google />Sign up free with Google</button>
              <EmailWay next="/new" />
            </div>
            <span className="small muted">Free: {res.left > 0 ? `${res.left} more ${res.left === 1 ? "try" : "tries"} today without an account; ` : ""}an account gives {LIMITS.free.backtests_per_month} backtests a month, saved, no card.</span>
          </div>
        </div>
      )}
    </div>
  );
}
