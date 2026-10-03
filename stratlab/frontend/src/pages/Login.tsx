import { useEffect, useState, type JSX } from "react";
import { supabase } from "../lib/api";
import { Google } from "../components/Icons";
import { LegalLinks } from "../components/LegalLinks";
import { Logo } from "../components/Logo";

/* The public landing page: what StratLab is, why it's different, and one way in (Google sign-in). */

type Status = "pass" | "warn" | "fail";
const STATUS: Record<Status, string> = { pass: "Passed", warn: "Warning", fail: "Failed" };

/** Three sample ideas for the hero demo: what you write, how it's read, what the verdict says. */
const DEMOS: {
  tab: string; idea: string; rule: [string, boolean][]; meta: string; verdict: string; tone: "blue" | "orange" | "ink"; why: string; checks: [string, Status][];
}[] = [
  {
    tab: "NIFTY 50", idea: "Buy NIFTY 50 when the 20-day average crosses above the 50-day, with a 2% stop loss",
    rule: [["Buy when", false], ["SMA 20", true], ["crosses above", true], ["SMA 50", true], ["· stop loss", false], ["2%", true]],
    meta: "Experiment v3 · NIFTY 50 · 38 trades", verdict: "Probably luck.", tone: "orange",
    why: "It made money on the years it was tuned on, then lost on years it had never seen.",
    checks: [["Unseen data", "fail"], ["Nearby settings", "fail"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "Bitcoin", idea: "Buy Bitcoin when RSI drops below 30, sell when it goes back above 55",
    rule: [["Buy when", false], ["RSI 14", true], ["falls below", true], ["30", true], ["· sell when above", false], ["55", true]],
    meta: "Experiment v5 · BTC/USD · 61 trades", verdict: "Likely a real edge.", tone: "blue",
    why: "It kept working on data it had never seen, and small changes to the settings didn't break it.",
    checks: [["Unseen data", "pass"], ["Nearby settings", "pass"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "NVIDIA", idea: "Short NVDA when it falls below its 20-day low, with a 5% trailing stop",
    rule: [["Sell short when", false], ["price", true], ["falls below", true], ["20-day low", true], ["· trail the stop", false], ["5%", true]],
    meta: "Experiment v1 · NVDA · 9 trades", verdict: "Not enough evidence.", tone: "ink",
    why: "Nine trades in five years is too few to tell skill from chance. Try a longer period or a looser rule.",
    checks: [["Unseen data", "warn"], ["Nearby settings", "pass"], ["Bad-luck drawdown", "pass"], ["Enough trades", "fail"]],
  },
];

const CHECKS: { title: string; body: string; art: JSX.Element }[] = [
  { title: "Unseen data", body: "We split the test in two, 70/30, and trade each part with fresh money. An idea that only made money in the earlier years probably fitted the past, not the market.", art: <ArtUnseen /> },
  { title: "Nearby settings", body: "We re-run your idea with up to 25 small variations of its indicator lengths. If only your exact settings make money, that's a lucky fit, not an edge.", art: <ArtNearby /> },
  { title: "Bad-luck drawdown", body: "We reshuffle the order of your trades 1,000 times to show how deep the losses could get with worse luck, so a bad run doesn't surprise you.", art: <ArtDrawdown /> },
  { title: "Enough trades", body: "A handful of wins proves nothing. Under 15 trades, luck dominates; 30 or more is a fair sample. We tell you which side you're on.", art: <ArtTrades /> },
];

const TOOLS: [string, string][] = [
  ["Ask or do anything", "One box for everything. \"Test: buy NIFTY when RSI drops below 30\" runs the test and shows the verdict; \"paper trade it on BTC\", \"research HDFC Bank\" or \"what is walk-forward?\" work too."],
  ["Plain-English rules", "Write the idea the way you'd say it. AI turns it into exact rules you can read. Tap any word to change it, add or remove a rule, or rewrite the whole thing in words."],
  ["Real trading costs", "STT, stamp duty, GST, exchange fees, SEC and FINRA fees, UK stamp duty, forex spread and slippage, per market."],
  ["Long, short or both", "Buy, short, or both ways in one strategy. Stops in %, points, ATR or swing lows; targets in % or R; trailing stops and time limits."],
  ["Built for intraday", "Entry windows, square-off time, trades per day, cooldowns and a daily loss cap, with intraday (MIS) costs."],
  ["20+ indicators", "Moving averages, RSI, MACD, Bollinger Bands, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian breakouts and volume."],
  ["Compare experiments", "Every run is saved and numbered. Put two side by side to see exactly what changed and whether it helped."],
  ["Paper trading", "When a verdict holds up, run it live on real prices with fake money: one stock, a whole group, or an option structure. One view shows everything at stake across your sessions, and a short report arrives after each market closes."],
  ["On your phone", "Install StratLab on your home screen like an app and get every paper trade and the daily report as a notification. No Telegram needed."],
  ["Strategy library", "Rules other traders published with the verdict they earned, luck included. Copy one into your own notebook and test it yourself."],
  ["Walk-forward test", "Re-tune the settings on the past, trade them on the next stretch the tuning never saw, slide forward, repeat. The strictest test there is."],
  ["Share the verdict", "Send a card with the chart and all four checks straight from your phone, or a public link anyone can open. Your rules stay private."],
];

const BEYOND: [string, string, string][] = [
  ["Options, live", "Straddles, strangles, iron flies, condors, spreads or any structure up to eight legs, paper traded on live NSE, BSE, MCX and NSE currency option prices. Every fill is the real bid or ask. Enter at a set time or whenever your own rules signal, say a 7 EMA cross buying the NIFTY call. Stops on the whole position or each leg, re-centring, and sizing by the broker's real margin.", "Chains recorded every 5 minutes for backtesting"],
  ["Whole groups", "Run one set of rules across NIFTY 50, the liquid F&O stocks, US mega caps, large coins or your own list, with one pot of capital and a limit on positions open at once. See which members carried it, then paper trade the whole group live, entering on the live price and skipping stocks whose spread is too wide.", "Built for scanners and momentum books"],
  ["Bring any strategy", "Drop in a config file, Pine Script, Python, MetaTrader, AmiBroker or plain words. StratLab works out what it is and sets it up in the right place: a notebook, a group, or the Options tab.", "Anything it can't carry over is listed"],
];

const INVESTORS: [string, string, string][] = [
  ["Stage 2 scan and sector rotation", "Which stocks are in Stage 2 with the Supertrend up, fresh signals first, and which sectors are Leading, Weakening, Lagging or Improving against the market, down to their biggest stocks. A daily alert when a new one lines up.", "Know where the money is moving"],
  ["Filings and red flags", "What your watchlist companies told the exchange: fund raises like a QIP or preferential issue, promoter pledges, auditor or director resignations, defaults, regulator action, rating downgrades. A 3-month summary, and an evening alert.", "Read the filing before the chart"],
  ["Company deep dive", "Ten years of sales, margins, capex and free cash flow, then the business model and every capex plan read from the company's own presentations and earnings calls, each linked to its source.", "In the company's own words"],
  ["Measured like its industry", "A hospital on revenue per occupied bed and occupancy, a bank on NIM and bad loans, a hotel on RevPAR, cement on EBITDA per tonne; valued on EV/EBITDA, price to book or P/E, whichever its industry uses.", "The right yardstick"],
  ["Management report card", "What management said it would deliver on past earnings calls (growth, margins, capex) checked against what the results later showed: met, missed or not due yet.", "Do they deliver?"],
  ["Checklist, home and deck", "Fixed, written-down checks on growth, quality, debt, cash, promoters, filings and trend, adjusted for the company's industry; every watchlist company on one investor home; and the whole deep dive as slides.", "All in one place"],
];

const MARKETS: [string, string, string][] = [
  ["₹", "India", "NSE and BSE stocks, indices and F&O"], ["₿", "Crypto", "BTC, ETH and hundreds of pairs"], ["$", "United States", "NYSE and NASDAQ stocks and ETFs"],
  ["£", "United Kingdom", "London Stock Exchange"], ["€", "Europe", "Xetra and Euronext"], ["¥", "Japan", "Tokyo Stock Exchange"],
  ["€$", "Forex", "Major and minor currency pairs"],
  ["₹Au", "Indian commodities", "MCX futures in rupees: gold, silver, crude, natural gas, base metals, in whole lots"],
  ["$Au", "Global commodities", "COMEX, NYMEX, ICE futures in dollars: gold, oil, grains, coffee, per unit"],
  ["+", "Your own data", "Upload any CSV of candles"],
];

const FAQ: [string, string][] = [
  ["Does StratLab place real trades?", "No. Everything is research and paper trading with fake money. No real orders are ever placed, and nothing here is investment advice."],
  ["Do I need to know how to code?", "No. You describe the idea in plain words. If something is missing, like when to sell, StratLab asks. You can also tap any rule to change it."],
  ["Where do the prices come from?", "Indian stocks, F&O and MCX commodities come from a live exchange feed. Crypto, US, UK, European, Japanese, forex and global commodity prices come from established market data sources; some can run a few minutes behind. Company research combines reported financials, recent news and Wikipedia."],
  ["Why not just look at the backtest return?", "Because almost any idea can be tuned to look great on past prices. The honesty checks ask whether it would have worked on data it never saw, with slightly different settings, and with worse luck. That's the difference between an edge and a coincidence."],
  ["Can I bring a strategy I already have?", "Yes. Import a StratLab export, a config file from your own bot, TradingView Pine Script, Python code (Backtrader, backtesting.py and similar), MetaTrader, AmiBroker, or just describe it. StratLab translates it into rules you can read, sets up a group if it trades a list of stocks, opens option structures in the Options tab, and lists anything it couldn't translate."],
  ["Can I test options strategies?", "You can paper trade them live today on NSE, BSE, MCX and NSE currency option prices, with fills at the real bid and ask. You can also let a notebook's rules decide when: long signals buy your structure and short signals its mirror. Backtesting options needs real historical prices for every strike, which nobody keeps for expired options, so StratLab is recording the NIFTY, BANKNIFTY and SENSEX chains every 5 minutes to build that history. We won't stand in a pricing model."],
  ["What does it cost?", "It's free to start: experiments every month, AI strategy builds, and 5 market days of paper trading. Basic (₹999 a month, or the same in your currency) adds group and options paper trading and a daily report; Pro (₹2,999) adds options on your own signals, faster group entries, alerts for every trade, every indicator and F&O, and the investor tools: the ST S2 scan, sector rotation, and filings and red flags."],
  ["Can I test commodities?", "Yes, as two separate markets. Indian commodities are MCX futures in rupees (gold, silver, crude oil, natural gas, copper, zinc, aluminium, lead, and their mini contracts), sized in whole lots with MCX costs, on years of daily history stitched across expiries. Global commodities are COMEX, NYMEX and ICE futures in dollars (gold, silver, oil, gas, copper, grains, coffee, sugar, cocoa, cotton), sized per ounce or barrel."],
  ["Is there an app?", "StratLab installs from the browser: on Android or a computer choose Install app, on an iPhone tap Share, then Add to Home Screen. It opens full screen with its own icon, and sends paper trades and the daily report as notifications."],
  ["Does it know market holidays?", "Yes. Exchange holidays in India, the US, UK, Europe and Japan are built in: the markets panel shows weekends and holidays, the daily report skips them, and they don't count toward the free trial."],
  ["Can I share a result?", "Yes. Share a verdict as an image from your phone, or make a public link. It shows the verdict, the chart and the checks, never your rules, and you can turn it off at any time."],
];

export function Login() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams(location.search + "&" + location.hash.replace(/^#/, ""));
    const d = p.get("error_description");
    if (!d) return;
    setError(/exchange external code/i.test(d)
      ? "Google sign-in couldn't finish: the Google Client ID or Secret saved in Supabase doesn't match your Google Cloud OAuth client."
      : `Sign-in failed: ${d}`);
    history.replaceState(null, "", location.pathname);
  }, []);

  const signIn = () => supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
  const cta = (label = "Start free") => (
    <button className="btn lp-cta" onClick={signIn}><Google />{label}</button>
  );

  return (
    <div className="lp">
      <header className="lp-nav">
        <a href="#top" className="brand" aria-label="StratLab home"><Logo size={46} /></a>
        <nav aria-label="Sections">
          <a href="#investors">For investors</a><a href="#how">For traders</a><a href="#checks">Honesty checks</a><a href="#beyond">Options &amp; groups</a><a href="#markets">Markets</a><a href="#faq">FAQ</a>
        </nav>
        <button className="btn outline sm" onClick={signIn}>Sign in</button>
      </header>

      <section id="top" className="lp-hero ruled">
        <div className="lp-wrap lp-hero-grid">
          <div className="stack" style={{ gap: 24 }}>
            <span className="eyebrow">For investors and traders · Before your money does</span>
            <h1 className="serif lp-h1">Know the company. <em>Test</em> the idea.</h1>
            <p className="serif lp-lede">Investing? Get the business in its own words, ten years of numbers, red flags, and whether management delivered what it promised. Trading? Write a strategy in plain words; we test it on years of real prices, after real costs, and tell you straight if the edge is real.</p>
            <div className="row wrap" style={{ gap: 12 }}>
              {cta()}
              <a className="btn quiet lp-cta-2" href="#investors">For investors</a>
              <a className="btn quiet lp-cta-2" href="#how">For traders</a>
            </div>
            {error && <p className="banner" role="alert">{error}</p>}
            <p className="small muted">Free to start · No code · Indian and US companies · 10 markets to test on · Paper trading only, no real orders</p>
          </div>
          <HeroDemo />
        </div>
      </section>

      <section className="lp-band">
        <div className="lp-wrap lp-facts">
          {[["10 yrs", "of numbers on every Indian and US company"], ["4", "honesty checks on every strategy test"], ["10", "markets to test on, plus your own data"], ["₹0", "to start, no card needed"]].map(([n, t]) => (
            <div key={t}><b className="serif">{n}</b><span>{t}</span></div>
          ))}
        </div>
      </section>

      <section id="research" className="lp-sec">
        <div className="lp-wrap lp-split">
          <div className="stack" style={{ gap: 14 }}>
            <span className="eyebrow">Research</span>
            <h2 className="serif lp-h2">Start with any company, Indian or US.</h2>
            <p className="lp-p">Look up any Indian or US company: price, key numbers, results against estimates, analyst ratings, insider trades and news. An AI read scores it, lays out the bull and bear case, and ends with three ideas you can test in one click.</p>
            <ul className="bullets lp-p" style={{ fontSize: 16 }}>
              <li><b>Themes:</b> map a sector: who's involved and where the margin sits.</li>
              <li><b>Market pulse:</b> index levels, headlines and today's mood.</li>
              <li><b>Compare</b> two companies, and keep a <b>watchlist</b>.</li>
            </ul>
          </div>
          <ResearchMock />
        </div>
      </section>

      <section id="investors" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head">
            <span className="eyebrow">For investors</span>
            <h2 className="serif lp-h2">Know the company before you own it.</h2>
            <p className="lp-p">For holding a stock for months or years, not minutes. Everything comes from the company's own filings and reported numbers, every quote is checked against its source, and nothing here tells you what to buy.</p>
          </div>
          <div className="lp-beyond">
            {INVESTORS.map(([t, b, tag]) => (
              <div key={t} className="card lp-beyond-card"><b>{t}</b><p className="small muted">{b}</p><span className="lp-fix">{tag}</span></div>
            ))}
          </div>
        </div>
      </section>


      <section className="lp-sec">
        <div className="lp-wrap lp-split">
          <div className="stack" style={{ gap: 14 }}>
            <span className="eyebrow">The problem</span>
            <h2 className="serif lp-h2">Most backtests are built to look good.</h2>
            <p className="lp-p">Tweak the numbers enough and any idea shows a beautiful curve on past prices. Then it meets the real market. Most tools stop at the curve. StratLab asks the questions a sceptical trader would.</p>
          </div>
          <div className="lp-problems">
            {[["Tuned to the past", "The settings were picked because they fit history, not because they'll hold up.", "Tested on years it was never judged on"],
              ["Costs ignored", "Brokerage, taxes and slippage quietly eat thin edges.", "Every fee and tax, per market"],
              ["One lucky chart", "It worked on the stock you picked, and nowhere else.", "Run on 10 similar instruments"]].map(([t, b, fix]) => (
              <div key={t} className="card lp-problem">
                <b>{t}</b><p className="small muted">{b}</p><span className="lp-fix">→ {fix}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head"><span className="eyebrow">How it works</span><h2 className="serif lp-h2">From a sentence to a verdict in a minute.</h2></div>
          <ol className="lp-steps">
            <li className="card"><span className="lp-num">1</span><b>Describe it</b><p className="small muted">"Buy Reliance when it's above its 200-day average and RSI crosses 50." Pick the market, or let StratLab find the stock in your sentence.</p></li>
            <li className="card"><span className="lp-num">2</span><b>Check the rules</b><p className="small muted">The idea becomes plain-English rules. Tap any highlighted word to change an indicator, a number or the stop loss, or rewrite it in words.</p></li>
            <li className="card"><span className="lp-num">3</span><b>Get an honest verdict</b><p className="small muted">Years of real prices, real costs and four honesty checks. Every number has an (i) that explains it.</p></li>
            <li className="card"><span className="lp-num">4</span><b>Improve, or paper trade</b><p className="small muted">Change one thing and run again, compare the two, and when it holds up, watch it live with fake money.</p></li>
          </ol>
        </div>
      </section>

      <section id="checks" className="lp-sec">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head">
            <span className="eyebrow">The honesty checks</span>
            <h2 className="serif lp-h2">Four questions every strategy has to answer.</h2>
            <p className="lp-p">Most apps show you the return. StratLab shows you whether you should believe it.</p>
          </div>
          <div className="lp-checks">
            {CHECKS.map((c) => (
              <div key={c.title} className="card lp-check">
                <div className="lp-art" aria-hidden="true">{c.art}</div>
                <b className="serif" style={{ fontSize: 21 }}>{c.title}</b>
                <p className="small muted">{c.body}</p>
              </div>
            ))}
          </div>
          <div className="card lp-travel">
            <div className="stack" style={{ gap: 8 }}>
              <span className="eyebrow">And one more</span>
              <b className="serif" style={{ fontSize: 24 }}>Does it work on similar stocks?</b>
              <p className="small muted" style={{ maxWidth: "52ch" }}>One tap runs your exact rules on about 10 well-known names from the same market and counts how many make money. Real patterns travel. Lucky charts don't.</p>
            </div>
            <div className="lp-dots" aria-label="7 of 10 similar instruments profitable">
              {Array.from({ length: 10 }, (_, i) => <span key={i} className={i < 7 ? "on" : ""} />)}
              <small className="mono">7 of 10 made money</small>
            </div>
          </div>
        </div>
      </section>

      <section id="beyond" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head">
            <span className="eyebrow">Beyond one chart</span>
            <h2 className="serif lp-h2">Options, whole groups, and the strategies you already run.</h2>
            <p className="lp-p">Real trading isn't one stock and one rule. StratLab handles the rest too.</p>
          </div>
          <div className="lp-beyond">
            {BEYOND.map(([t, b, tag]) => (
              <div key={t} className="card lp-beyond-card"><b>{t}</b><p className="small muted">{b}</p><span className="lp-fix">{tag}</span></div>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-sec">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head"><span className="eyebrow">The toolkit</span><h2 className="serif lp-h2">Everything a serious test needs.</h2></div>
          <div className="lp-tools">
            {TOOLS.map(([t, b]) => <div key={t} className="lp-tool"><b>{t}</b><p className="small muted">{b}</p></div>)}
          </div>
        </div>
      </section>

      <section id="markets" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <div className="lp-head">
            <span className="eyebrow">Markets</span>
            <h2 className="serif lp-h2">Test where you trade.</h2>
            <p className="lp-p">Each market uses its own trading hours, currency, and the fees and taxes you'd actually pay there.</p>
          </div>
          <div className="lp-markets">
            {MARKETS.map(([s, n, d]) => (
              <div key={n} className="card lp-market"><span className="lp-sym serif">{s}</span><div><b>{n}</b><p className="small muted">{d}</p></div></div>
            ))}
          </div>
        </div>
      </section>

      <section id="faq" className="lp-sec">
        <div className="lp-wrap lp-split">
          <div className="stack" style={{ gap: 14 }}>
            <span className="eyebrow">Questions</span>
            <h2 className="serif lp-h2">Good to know.</h2>
            <p className="lp-p">Free to start, with every market. Paid plans add more tests, more live sessions and the Pro tools.</p>
          </div>
          <div className="lp-faq">
            {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p className="muted">{a}</p></details>)}
          </div>
        </div>
      </section>

      <section className="lp-final ruled">
        <div className="lp-wrap stack" style={{ gap: 20, alignItems: "center", textAlign: "center" }}>
          <h2 className="serif lp-h2" style={{ maxWidth: "18ch" }}>Find out before your money does.</h2>
          <p className="lp-p">Test your first idea in a minute. Sign in with Google, no card needed.</p>
          {cta("Continue with Google")}
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-wrap spread" style={{ flexWrap: "wrap", gap: 16 }}>
          <Logo size={30} />
          <p className="small muted" style={{ maxWidth: "70ch" }}>Paper trading and research only. No real orders are placed. Past results don't predict future returns, and nothing on StratLab is investment advice. © {new Date().getFullYear()} StratLab.</p>
          <LegalLinks />
        </div>
      </footer>
    </div>
  );
}

/** Idea → rules → verdict, cycling through three examples until someone picks one. */
function HeroDemo() {
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(true);
  useEffect(() => {
    if (!auto || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((x) => (x + 1) % DEMOS.length), 6000);
    return () => clearInterval(t);
  }, [auto]);
  const d = DEMOS[i];
  return (
    <div className="lp-demo" aria-label="Example: an idea, its rules and its verdict">
      <div className="seg lp-demo-tabs" role="tablist">
        {DEMOS.map((x, k) => (
          <button key={x.tab} role="tab" aria-selected={k === i} aria-pressed={k === i} onClick={() => { setI(k); setAuto(false); }}>{x.tab}</button>
        ))}
      </div>
      <div key={i} className="lp-demo-body">
        <div className="card lp-demo-idea">
          <span className="eyebrow">You write</span>
          <p className="serif">"{d.idea}"</p>
        </div>
        <div className="card lp-demo-rule">
          <span className="eyebrow">StratLab reads</span>
          <p>{d.rule.map(([w, tok], k) => tok ? <span key={k} className="lp-tok">{w}</span> : <span key={k}> {w} </span>)}</p>
        </div>
        <div className="card lp-demo-verdict">
          <span className="eyebrow">{d.meta}</span>
          <span className="serif lp-verdict" style={{ color: d.tone === "ink" ? "var(--ink)" : `var(--${d.tone})` }}>{d.verdict}</span>
          <p className="serif" style={{ fontSize: 16, color: "var(--ink-2)" }}>{d.why}</p>
          <div className="stack small" style={{ gap: 7, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            {d.checks.map(([t, s]) => <div key={t} className="spread"><span>{t}</span><span className={`badge ${s}`}>{STATUS[s]}</span></div>)}
          </div>
          <span className="tiny muted">Sample result</span>
        </div>
      </div>
    </div>
  );
}

function ResearchMock() {
  const scores: [string, number, boolean][] = [["Moat", 92, true], ["Growth", 94, true], ["Value", 28, false], ["Momentum", 81, true]];
  return (
    <div className="card lp-rmock" aria-label="Example company research page">
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 2 }}><span className="eyebrow">NASDAQ · NVDA</span><b className="serif" style={{ fontSize: 26 }}>NVIDIA Corp</b></div>
        <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}><b className="serif" style={{ fontSize: 26 }}>$183.20</b><span className="badge next">▲ +1.33% today</span></div>
      </div>
      <div className="lp-rscore">
        <div className="stack" style={{ alignItems: "center", gap: 0 }}><b className="serif" style={{ fontSize: 44, color: "var(--blue)", lineHeight: 1 }}>77</b><span className="tiny muted mono">SCORE</span></div>
        <div className="stack" style={{ gap: 7, flex: 1 }}>
          {scores.map(([l, v, good]) => (
            <div key={l} className="score-row"><span className="small">{l}</span><div className="score-track"><div style={{ width: `${v}%`, background: good ? "var(--blue)" : "var(--orange)" }} /></div><span className="small mono">{v}</span></div>
          ))}
        </div>
      </div>
      <div className="lp-ridea">
        <b className="small">Ideas to test on NVDA</b>
        <p className="small">"Buy NVDA when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below, 7% stop loss"</p>
        <span className="btn blue sm" style={{ alignSelf: "flex-start", pointerEvents: "none" }}>Test this idea →</span>
      </div>
    </div>
  );
}

/* small illustrations for the four checks */
function ArtUnseen() {
  return (
    <svg viewBox="0 0 200 80">
      <rect x="140" y="4" width="56" height="72" rx="6" fill="var(--orange-soft)" />
      <text x="168" y="16" textAnchor="middle" fontSize="8" fill="var(--orange-ink)" fontFamily="var(--mono)">UNSEEN</text>
      <polyline points="6,66 26,58 46,60 66,46 86,44 106,32 126,26 140,24" fill="none" stroke="var(--blue)" strokeWidth="2.5" strokeLinejoin="round" />
      <polyline points="140,24 156,34 170,30 184,48 196,56" fill="none" stroke="var(--orange)" strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}
function ArtNearby() {
  const cells = [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 2, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0];
  return (
    <svg viewBox="0 0 200 80">
      {cells.map((c, k) => (
        <rect key={k} x={52 + (k % 5) * 20} y={2 + Math.floor(k / 5) * 15.5} width="17" height="13" rx="3"
          fill={c === 2 ? "var(--blue)" : c === 1 ? "var(--chip)" : "var(--orange-soft)"} stroke={c === 2 ? "var(--ink)" : "none"} />
      ))}
    </svg>
  );
}
function ArtDrawdown() {
  const paths = ["6,20 40,28 80,24 120,40 160,34 196,44", "6,20 40,34 80,40 120,36 160,52 196,48", "6,20 40,30 80,46 120,58 160,54 196,62", "6,20 40,26 80,30 120,28 160,40 196,36"];
  return (
    <svg viewBox="0 0 200 80">
      {paths.map((p, k) => <polyline key={k} points={p} fill="none" stroke={k === 2 ? "var(--orange)" : "var(--dash)"} strokeWidth={k === 2 ? 2.5 : 1.5} />)}
      <line x1="6" y1="72" x2="196" y2="72" stroke="var(--line-2)" strokeDasharray="3 3" />
    </svg>
  );
}
function ArtTrades() {
  return (
    <svg viewBox="0 0 200 80">
      {Array.from({ length: 30 }, (_, k) => (
        <circle key={k} cx={14 + (k % 10) * 19} cy={16 + Math.floor(k / 10) * 22} r="6.5" fill={k < 5 ? "var(--blue)" : "var(--chip)"} />
      ))}
    </svg>
  );
}
