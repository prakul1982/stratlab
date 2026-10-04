import { useEffect, useState, type JSX, type ReactNode } from "react";
import { NEXT_PAGE, supabase } from "../lib/api";
import { money, usePricing } from "../lib/currency";
import { FEATURES, LIMITS, PLAN_IDS, PLAN_NAME, PRICE, WHO, type PlanId } from "../lib/plans";
import { Google } from "../components/Icons";
import { LegalLinks } from "../components/LegalLinks";
import { Logo } from "../components/Logo";

/* The public landing page: what StratLab does, in four groups (research, portfolio and tax, strategy testing, alerts),
 * the plans, and one way in (Google sign-in). */

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

/* What StratLab does today, in the four groups the page is built around. Facts about the product only: nothing here
 * says what to buy or sell, rates a company or names a data source. */
const RESEARCH: [string, string][] = [
  ["Company pages", "Any Indian (NSE or BSE) or US company: price and chart, key numbers, results against estimates, who owns it, news, and an AI read in plain numbers that ends with ideas you can test."],
  ["Deep dive", "Ten years of sales, margins, capex and free cash flow, then the business model and plans read from the company's own presentations, calls or annual report, each quote checked against its source. As slides too, PowerPoint or PDF."],
  ["Report card and checklist", "What management said it would deliver on past calls, checked against the results that followed: met, missed or not due yet. Plus fixed, written-down checks with the number behind each."],
  ["Results calendar", "When Indian companies hold results board meetings and when US companies report, from a week back to four weeks ahead."],
  ["Corporate actions", "Dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date and record date, for your stocks or the whole market."],
  ["Deals and insider trades", "Promoters', directors' and key staff's own trades and pledges, substantial acquisitions, and the day's bulk and block deals, as filed with the exchange."],
  ["Surveillance lists", "Which Indian stocks are under ASM or GSM and at which stage, ESM, trade-to-trade, price-band changes and the F&O ban, with what each measure means."],
  ["Filings and red flags", "Fund raises, promoter pledges, auditor or director resignations, defaults, regulator action and rating downgrades, each linked to the filing."],
  ["Screens", "Filter companies by sector, size, growth, margins, debt, returns, yield, P/E, Stage, distance from the 52-week high and red-flag filings. Save a screen and get its new matches by email."],
  ["Stage 2 scan", "Which stocks in your watchlist or a ready-made group are in Stage 2 with the Supertrend up, fresh signals first, and a one-click backtest of the same rules."],
  ["Sector rotation", "Every sector against the market as Leading, Weakening, Lagging or Improving, with the trail it took, down to each sector's biggest stocks."],
  ["Watchlist, news and markets", "Your watchlist at a glance, the market pulse, themes and side-by-side comparisons, past newsletters on News, and which exchanges are open right now."],
];

const PORTFOLIO: [string, string, string][] = [
  ["My Holdings", "Import the holdings file from Zerodha, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities (CSV, Excel or the broker's own export), or any file with a stock and a quantity column. See value, gain or loss, sector mix, and each stock's trend, filings, results date and surveillance flags.", "Seen only by you, deleted in one step"],
  ["Dividends, bonuses and splits", "Dividends ahead and from the last 12 months on what you hold. A bonus or split since you saved your holdings is offered as a one-click Apply, with Undo, and nothing changes without you.", "Your holdings kept in step"],
  ["Tax report", "Capital gains on listed Indian shares from your broker's tradebooks and tax P&L files, or the ZIP of them: matched first in, first out, short and long term at the rates of the day, the yearly exemption, 2018 grandfathering, intraday shown apart, and set-off. Download it as CSV or PDF.", "An estimate to check with your CA"],
  ["Share cards and invites", "Share a company's facts as a card that previews on WhatsApp, X and LinkedIn. Invite a friend: once they've used StratLab on 3 days in their first 14, you both get a free month of Basic.", "Up to 12 free months"],
];

const TOOLS: [string, string][] = [
  ["Plain-English rules", "Write the idea the way you'd say it, or type it into Ask (Ctrl+K). AI turns it into exact rules you can read; tap any word to change it."],
  ["Real trading costs", "STT, stamp duty, GST, exchange fees, SEC and FINRA fees, UK stamp duty, forex spread and slippage, per market."],
  ["Long, short and intraday", "Buy, short or both. Stops in %, points, ATR or swing lows, trailing stops, entry windows, square-off and a daily loss cap."],
  ["20+ indicators", "Moving averages, RSI, MACD, Bollinger Bands, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian breakouts and volume."],
  ["Walk-forward test", "Re-tune on the past, trade the next stretch the tuning never saw, slide forward, repeat."],
  ["Whole groups", "One set of rules across NIFTY 50, the F&O stocks, US mega caps, large coins or your own list, with one pot of capital."],
  ["Options, live", "Straddles, condors, spreads or any structure up to eight legs, paper traded at the real bid and ask, at a set time or on your own rules' signal."],
  ["Bring any strategy", "A config file, Pine Script, Python, MetaTrader, AmiBroker or plain words, set up as a notebook, a group or an option structure."],
  ["Paper trading", "Run it live on real prices with fake money, see everything at stake across sessions, and get a short report after each close."],
  ["Compare experiments", "Every run is saved and numbered. Put two side by side to see what changed and whether it helped."],
  ["Strategy library", "Rules other people published with the verdict they earned, luck included. Copy one and test it yourself."],
  ["Share the verdict", "A card with the chart and all four checks, or a public link. Your rules stay private."],
];

const ALERTS: [string, string][] = [
  ["Stock alerts", "A price level, a big day's move, crossing a moving average, an RSI level, a Stage change or a new 52-week high or low; for Indian stocks, new insider trades, deals and surveillance changes too."],
  ["Results and corporate actions", "On results day and when the numbers are out, when a company you follow announces a dividend, bonus or split, and the evening before its ex-date."],
  ["Red flags and scans", "An evening alert when a watchlist company files a red flag, and a daily one when a stock newly lines up in the Stage 2 scan."],
  ["Paper trades", "Every paper trade as it happens, and a short report a few minutes after each market closes."],
  ["Newsletters", "The Market Brief for India or the US and My Stocks for the companies you follow, daily or weekly, plus a Saturday email of a saved screen's new matches."],
  ["Where they arrive", "As a notification on your phone (install StratLab from the browser), on Telegram, or by email to an address you confirmed. Every email has a one-click unsubscribe."],
];

const MARKETS: [string, string, string][] = [
  ["₹", "India", "NSE and BSE stocks, indices and F&O"], ["₿", "Crypto", "BTC, ETH and hundreds of pairs"], ["$", "United States", "NYSE and NASDAQ stocks and ETFs"],
  ["£", "United Kingdom", "London Stock Exchange"], ["€", "Europe", "Xetra and Euronext"], ["¥", "Japan", "Tokyo Stock Exchange"],
  ["€$", "Forex", "Major and minor currency pairs"], ["₹$", "Indian currency futures", "USDINR, EURINR, GBPINR, JPYINR and cross pairs"],
  ["₹Au", "Indian commodities", "MCX futures in rupees, in whole lots"], ["$Au", "Global commodities", "COMEX, NYMEX and ICE futures in dollars"],
  ["+", "Your own data", "Upload any CSV of candles"],
];

const fmt = (v: number | null) => (v == null ? "unlimited" : v.toLocaleString("en-IN"));
const L = LIMITS;

/** The questions people ask before signing up. Plan numbers come from lib/plans.ts, which a test keeps equal to plans.py. */
const FAQ: [string, string][] = [
  ["Does StratLab tell me what to buy?", "No. It shows facts: reported numbers, filings, prices and how a set of rules would have done in the past. It never says buy, sell or hold, gives no price targets or ratings, and nothing on StratLab is investment advice."],
  ["Does StratLab place real trades?", "No. Testing is on past prices and paper trading uses fake money. No real orders are ever placed."],
  ["Do I need to know how to code?", "No. You describe the idea in plain words. If something is missing, like when to sell, StratLab asks. You can also tap any rule to change it."],
  ["Where do the numbers come from?", "Indian prices come from a live exchange feed; other markets from established market data sources, some a few minutes behind. Company numbers come from reported results and the companies' own filings with the exchanges and the SEC. Every page with company numbers says how fresh they are."],
  ["Why not just look at the backtest return?", "Because almost any idea can be tuned to look great on past prices. The honesty checks ask whether it would have worked on data it never saw, with slightly different settings, and with worse luck. That's the difference between an edge and a coincidence."],
  ["Which holdings files can I import?", "The holdings export from Zerodha, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities is recognised by itself; any CSV or Excel file with a column for the stock and one for the quantity works too. Only you can see your holdings, and you can delete them in one step."],
  ["How does the tax report work?", "Upload your broker's tradebooks or tax P&L files, or the ZIP of them (up to 10 MB a file). StratLab matches buys and sales first in, first out, splits short from long term, applies the rate change of 23 July 2024, the yearly long-term exemption and 2018 grandfathering, and shows intraday trades apart. It's an estimate to check with a chartered accountant, not tax advice."],
  ["Can I test options strategies?", "You can paper trade them live on NSE, BSE, MCX and NSE currency option prices, with fills at the real bid and ask, at a set time or when a notebook's rules signal. Backtesting options needs real past prices for every strike, so StratLab records the NIFTY, BANKNIFTY and SENSEX chains every 5 minutes to build that history rather than guess with a pricing model."],
  ["What does it cost?", `Free to start: ${L.free.backtests_per_month} backtests and ${L.free.ai_builds_per_month} AI strategy builds a month, 5 market days of paper trading, ${L.free.deepdives_per_month} deep dives a month, ${L.free.stock_alerts} stock alerts, ${L.free.screens} saved screens, ${L.free.holdings} holdings and the tax report. Basic (₹${PRICE.basic[0].toLocaleString("en-IN")} a month including GST) adds every indicator, ${fmt(L.basic.backtests_per_month)} backtests, group and options paper trading, trade notifications, ${L.basic.deepdives_per_month} deep dives, the Stage 2 scan and daily newsletters. Pro (₹${PRICE.pro[0].toLocaleString("en-IN")}) adds ${fmt(L.pro.backtests_per_month)} backtests and deep dives, ${L.pro.live_limit} paper sessions at once, Indian F&O, options on your own signals and export.`],
  ["How do invite rewards work?", "Your invite link is in Account. When a friend who joined through it uses StratLab on 3 different days in their first 14, you both get a free month of Basic, up to 12 months for you. If you already pay, the month is kept and starts if your paid plan ever stops."],
  ["Can I read a company's facts without signing in?", "Yes. Every listed Indian and US company has a public facts page at stratlab.studio/stocks/in/SYMBOL or /stocks/us/SYMBOL, and a shared company card opens it too."],
  ["Is there an app?", "StratLab installs from the browser: on Android or a computer choose Install app, on an iPhone tap Share, then Add to Home Screen. It opens full screen with its own icon and sends alerts as notifications."],
  ["Does it know market holidays?", "Yes. Exchange holidays in India, the US, UK, Europe and Japan are built in: the markets panel shows weekends and holidays, the daily report skips them, and they don't count toward the free trial."],
];

/** Sign in with Google; `next` is the page to open once signed in. */
function signIn(next?: string) {
  // came from a public company page's link (test a strategy, the deep dive), or picked a plan: go there once signed in
  const to = next ?? (location.pathname !== "/" ? location.pathname + location.search : null);
  if (to) try { sessionStorage.setItem(NEXT_PAGE, to); } catch { /* storage off */ }
  return supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });
}

const SECTIONS: [string, string][] = [["research", "Research"], ["portfolio", "Portfolio and tax"], ["strategy", "Strategy testing"],
  ["alerts", "Alerts"], ["pricing", "Pricing"], ["faq", "FAQ"]];

/** A section's eyebrow, heading and one line under it. */
function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="lp-head">
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="serif lp-h2">{title}</h2>
      {children && <p className="lp-p">{children}</p>}
    </div>
  );
}

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

  const cta = (label = "Start free") => (
    <button className="btn lp-cta" onClick={() => signIn()}><Google />{label}</button>
  );

  return (
    <div className="lp">
      <header className="lp-nav">
        <a href="#top" className="brand" aria-label="StratLab home"><Logo size={46} /></a>
        <nav aria-label="Sections">
          {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>
        <button className="btn outline sm" onClick={() => signIn()}>Sign in</button>
      </header>

      <main>
      <section id="top" className="lp-hero ruled">
        <div className="lp-wrap lp-hero-grid">
          <div className="stack" style={{ gap: 24 }}>
            <span className="eyebrow">For investors and traders · Indian and US stocks</span>
            <h1 className="serif lp-h1">Know the company. <em>Test</em> the idea.</h1>
            <p className="serif lp-lede">Research any Indian or US company from its own filings, keep your holdings and capital gains in one place, hear when something changes, and test a trading idea on years of real prices before your money does.</p>
            <div className="row wrap" style={{ gap: 12 }}>
              {cta()}
              <a className="btn quiet lp-cta-2" href="#research">See what's inside</a>
            </div>
            {error && <p className="banner" role="alert">{error}</p>}
            <p className="small muted">Free to start · No card · No code · Facts, never tips · Paper trading only, no real orders</p>
          </div>
          <HeroDemo />
        </div>
      </section>

      <section className="lp-band" aria-label="StratLab in numbers">
        <div className="lp-wrap lp-facts">
          {[["10 yrs", "of numbers on Indian and US companies"], ["4", "honesty checks on every backtest"], ["10", "markets to test on, plus your own data"], ["₹0", "to start, no card needed"]].map(([n, t]) => (
            <div key={t}><b className="serif">{n}</b><span>{t}</span></div>
          ))}
        </div>
      </section>

      <section id="research" className="lp-sec">
        <div className="lp-wrap stack" style={{ gap: 40 }}>
          <div className="lp-split">
            <Head eyebrow="Research" title="Start with any company, Indian or US.">
              Everything comes from reported numbers, exchange filings and the company's own documents. Plain numbers, never scores, ratings or calls on the stock.
            </Head>
            <ResearchMock />
          </div>
          <div className="lp-tools">
            {RESEARCH.map(([t, b]) => <div key={t} className="lp-tool"><b>{t}</b><p className="small muted">{b}</p></div>)}
          </div>
        </div>
      </section>

      <section id="portfolio" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <Head eyebrow="Portfolio and tax" title="What you own, and what it means at tax time.">
            Bring the file your broker already gives you. StratLab reads it, keeps it private, and reports facts about your own positions.
          </Head>
          <div className="lp-grid2">
            {PORTFOLIO.map(([t, b, tag]) => (
              <div key={t} className="card lp-beyond-card"><b>{t}</b><p className="small muted">{b}</p><span className="lp-fix">{tag}</span></div>
            ))}
          </div>
        </div>
      </section>

      <section id="strategy" className="lp-sec">
        <div className="lp-wrap stack" style={{ gap: 40 }}>
          <Head eyebrow="Strategy testing" title="From a sentence to an honest verdict.">
            Most backtests are tuned until the curve looks good. StratLab tests the idea on years of real prices after real costs, then asks whether you should believe the result.
          </Head>
          <ol className="lp-steps">
            <li className="card"><span className="lp-num">1</span><b>Describe it</b><p className="small muted">"Buy Reliance when it's above its 200-day average and RSI crosses 50." Pick the market, or let StratLab find the stock in your sentence.</p></li>
            <li className="card"><span className="lp-num">2</span><b>Check the rules</b><p className="small muted">The idea becomes plain-English rules. Tap any highlighted word to change an indicator, a number or the stop loss.</p></li>
            <li className="card"><span className="lp-num">3</span><b>Get the verdict</b><p className="small muted">Years of real prices, real costs and four honesty checks. Every number has an (i) that explains it.</p></li>
            <li className="card"><span className="lp-num">4</span><b>Improve, or paper trade</b><p className="small muted">Change one thing and run again, compare the two, and when it holds up, run it live with fake money.</p></li>
          </ol>

          <div id="checks" className="stack lp-anchor" style={{ gap: 20 }}>
            <h3 className="serif lp-h3">Four questions every strategy has to answer.</h3>
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

          <div className="stack" style={{ gap: 20 }}>
            <h3 className="serif lp-h3">Everything a serious test needs.</h3>
            <div className="lp-tools">
              {TOOLS.map(([t, b]) => <div key={t} className="lp-tool"><b>{t}</b><p className="small muted">{b}</p></div>)}
            </div>
          </div>

          <div id="markets" className="stack lp-anchor" style={{ gap: 20 }}>
            <h3 className="serif lp-h3">Test where you trade.</h3>
            <p className="lp-p">Each market uses its own trading hours, currency, holidays, and the fees and taxes you'd actually pay there.</p>
            <div className="lp-markets">
              {MARKETS.map(([s, n, d]) => (
                <div key={n} className="card lp-market"><span className="lp-sym serif">{s}</span><div><b>{n}</b><p className="small muted">{d}</p></div></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="alerts" className="lp-sec lp-alt">
        <div className="lp-wrap stack" style={{ gap: 32 }}>
          <Head eyebrow="Alerts" title="Hear about it when it happens.">
            Pick what matters to you and where it should reach you. Alerts report what happened, never what to do about it.
          </Head>
          <div className="lp-tools lp-tools-3">
            {ALERTS.map(([t, b]) => <div key={t} className="lp-tool"><b>{t}</b><p className="small muted">{b}</p></div>)}
          </div>
        </div>
      </section>

      <Pricing />

      <section id="faq" className="lp-sec lp-alt">
        <div className="lp-wrap lp-split lp-split-top">
          <Head eyebrow="Questions" title="Good to know.">
            Anything not answered here, the Contact page at the bottom reaches a person.
          </Head>
          <div className="lp-faq">
            {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p className="muted">{a}</p></details>)}
          </div>
        </div>
      </section>

      <section className="lp-final ruled">
        <div className="lp-wrap stack" style={{ gap: 20, alignItems: "center", textAlign: "center" }}>
          <h2 className="serif lp-h2" style={{ maxWidth: "18ch" }}>Find out before your money does.</h2>
          <p className="lp-p">Sign in with Google, no card needed. A short first-steps list on your home page walks you through a backtest, a watchlist, a deep dive, paper trading and alerts.</p>
          {cta("Continue with Google")}
        </div>
      </section>
      </main>

      <footer className="lp-foot">
        <div className="lp-wrap spread" style={{ flexWrap: "wrap", gap: 16 }}>
          <Logo size={30} />
          <p className="small muted" style={{ maxWidth: "70ch" }}>Research and paper trading only. No real orders are placed. Past results don't predict future returns, and nothing on StratLab is investment advice. © {new Date().getFullYear()} StratLab.</p>
          <LegalLinks />
        </div>
      </footer>
    </div>
  );
}

/** The three plans, priced in the visitor's currency (rupees in India), with the same lines as the Plans page. */
function Pricing() {
  const { pricing, currency } = usePricing();
  const row = pricing?.currencies[currency];
  const price = (p: PlanId) => {
    if (!row || currency === "INR") return { shown: `₹${PRICE[p][0].toLocaleString("en-IN")}`, gst: p !== "free" };
    return { shown: money(row, p === "free" ? 0 : (row as unknown as Record<string, number>)[p], currency), gst: false };
  };
  return (
    <section id="pricing" className="lp-sec">
      <div className="lp-wrap stack" style={{ gap: 32 }}>
        <Head eyebrow="Pricing" title="Free to start. Pay when you need more.">
          Every market, company pages, deep dives, screens, My Holdings and the tax report are on the Free plan. Paid plans raise the limits and add the scans, alerts and live tools. Cancel any time.
        </Head>
        <div className="lp-prices">
          {PLAN_IDS.map((p) => {
            const pr = price(p);
            return (
              <div key={p} className={`card lp-price${p === "pro" ? " lp-price-top" : ""}`} data-plan={p}>
                <div className="stack" style={{ gap: 2 }}>
                  <h3 className="h2">{PLAN_NAME[p]}</h3>
                  <span className="small muted">{WHO[p]}</span>
                </div>
                <div className="stack" style={{ gap: 2 }}>
                  <div className="serif lp-amount">{pr.shown}<span className="small muted"> / month</span></div>
                  {pr.gst && <span className="tiny muted">incl. GST</span>}
                </div>
                <ul className="lp-plan-list">
                  {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="small muted lp-plan-sub">{f}</li>
                    : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
                </ul>
                <button className={`btn ${p === "pro" ? "" : "outline"}`} onClick={() => signIn(p === "free" ? undefined : "/plans")}>
                  {p === "free" ? "Start free" : `Start with ${PLAN_NAME[p]}`}
                </button>
              </div>
            );
          })}
        </div>
        <p className="small muted" style={{ maxWidth: "80ch" }}>Rupee prices include 18% GST, and every payment gets a GST invoice. Visitors outside India see prices in their own currency. Paid plans renew each month until you cancel, which you can do any time from Account.</p>
      </div>
    </section>
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
  // the company page's AI read: plain numbers from reported results and prices, never scores (sample figures)
  const facts: [string, string][] = [["Growth", "Sales, 3 years 68.2% a year · Net profit, 3 years 91.4% a year"],
    ["Price trend", "6.1% above the 200-day average · 1-year change +32.5% · Stage 2 (advancing)"],
    ["Debt and cash", "Debt to equity 0.11 · Cash from operations 94% of net profit"],
    ["Margins and returns", "Operating margin 33% → 62% over 5 years · ROE 91.9%"]];
  return (
    <div className="card lp-rmock" aria-label="Example company research page">
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 2 }}><span className="eyebrow">NASDAQ · NVDA</span><b className="serif" style={{ fontSize: 26 }}>NVIDIA Corp</b></div>
        <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}><b className="serif" style={{ fontSize: 26 }}>$183.20</b><span className="badge next">▲ +1.33% today</span></div>
      </div>
      <div className="lp-rfacts">
        {facts.map(([l, t]) => <div key={l} className="stack" style={{ gap: 1 }}><b className="small">{l}</b><span className="small muted">{t}</span></div>)}
        <span className="tiny muted">Sample figures. Facts from reported results and prices, not advice.</span>
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
