import { useState, type ReactNode } from "react";
import { Compass, Globe, Layers, Lens, Pencil, Pulse, Share, Sparkle, User } from "./Icons";
import { Modal } from "./ui";
import { LogoMark } from "./Logo";
import { TOUR_SEEN as SEEN } from "./Shell";

type Step = { icon: ReactNode; title: string; body: string; where: string };

const STEPS: Step[] = [
  { icon: <LogoMark size={52} />, title: "Welcome to StratLab",
    body: "For investors: understand a company from its own filings, its numbers and management's track record. For traders: describe an idea, test it on years of real prices after real costs, and learn if the edge is real or just luck. Here is everything, in about a minute.",
    where: "Each idea lives in its own notebook, listed in the sidebar (the ☰ menu on phones)." },
  { icon: <Compass size={34} />, title: "Ask or do anything",
    body: "One box that gets things done. \"Test: buy NIFTY when RSI drops below 30\" builds the rules and shows the verdict; \"paper trade an EMA cross on BTC\" starts paper trading; \"research HDFC Bank\", \"momentum ideas for banks\" or \"what is walk-forward?\" work too. Paste a strategy to import it.",
    where: "\"Ask or do anything\" at the top of the sidebar and on your notebooks page, the magnifier on phones, or Ctrl+K (⌘K on a Mac) anywhere." },
  { icon: <Sparkle size={34} />, title: "Describe ideas in plain English",
    body: "Type an idea the way you'd tell a friend: \"buy when RSI drops under 30, sell at 5% profit\". The builder turns it into exact rules and asks about anything it had to guess.",
    where: "New notebook, then \"Describe your idea\". To start over later, use \"Describe the idea again\" at the top of a notebook." },
  { icon: <Lens size={34} />, title: "Research a company first",
    body: "Look up any Indian or US company: price, valuation, growth, who owns it, news, and an AI read that ends with trading ideas you can test in one click. Themes, the market pulse and side-by-side comparisons are there too.",
    where: "Companies, in the Research group of the menu. Press Watch on a company to keep it on your watchlist." },
  { icon: <Pulse size={34} />, title: "Tools for investors",
    body: "Scan a group for Stage 2 stocks with the Supertrend up (ST S2), see which sectors lead or lag the market and click through to their stocks, read your watchlist companies' filings with red flags like a QIP, pledges or resignations, and open any Indian or US company's deep dive: business, the measures its industry is judged on, how it's valued, capex plans, a management report card and an investor checklist. The investor home puts your whole watchlist on one page.",
    where: "Scans in the menu (trend scan, screener, sector rotation and red flags, as tabs), and Watchlist, where \"At a glance\" puts every company on one page. Deep dive is on every Indian and US company page. Sector rotation and each company's red flags are on every plan; the rest are Basic tools." },
  { icon: <Globe size={34} />, title: "Test on any market",
    body: "The same rules run on Indian stocks, indices and F&O, US, UK, European and Japanese stocks, forex, crypto, or any market you have a CSV for. Prices, hours, currency and costs switch to match.",
    where: "Pick the market first on a new notebook, or press the \"Testing on\" button at the top of any notebook to change it." },
  { icon: <Pencil size={34} />, title: "Every rule is editable",
    body: "Highlighted words in the rules (marked ▾) are dropdowns. Tap one to change the indicator, its length, the condition or a number. Stop-loss, target and position size are right below.",
    where: "The Rules card in any notebook." },
  { icon: <Compass size={34} />, title: "Run experiments, get an honest verdict",
    body: "Each run is saved as an experiment. The verdict comes from four checks: does it work on years it never saw, with nearby settings, against shuffled luck, and with enough trades? From a verdict you can go further: a walk-forward test, or the same rules on similar stocks.",
    where: "Press \"Run experiment\" in a notebook, then open any result. Every number has an (i) button explaining it." },
  { icon: <Pulse size={34} />, title: "Paper trade what survives",
    body: "When an idea earns a real verdict, run it live on paper: real prices, fake money, same rules. With alerts on, you get a message when it would trade and a short report after the market closes.",
    where: "\"Paper trade\" at the top of a notebook or verdict page. Running sessions are under Paper trading in the sidebar." },
  { icon: <Layers size={34} />, title: "Groups, options and your own strategies",
    body: "Test one set of rules on a whole group of stocks with shared capital, paper trade option structures on live NSE, BSE, MCX and NSE currency (USDINR) prices (at a set time or when a notebook's rules signal), or import a strategy you already run and let StratLab set it up.",
    where: "\"Testing on\" on a notebook for groups; Options and Import a strategy in the sidebar." },
  { icon: <Share size={34} />, title: "Share, export and keep notes",
    body: "Send a verdict card from your phone or make a public link (your rules stay private), export the rules as a file, and jot lab notes so you remember why you changed something.",
    where: "\"Share verdict\" on a result, \"More → Export\" and Lab notes in a notebook." },
  { icon: <User size={34} />, title: "Make it yours",
    body: "Switch to night mode, see your plan and usage, and run the connection check if prices or the idea builder ever look stuck.",
    where: "Account and Night mode in the sidebar. You can reopen this tour any time from \"Tour\" at the bottom of the sidebar." },
];

export function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const step = STEPS[i];
  const last = i === STEPS.length - 1;
  const close = () => { try { localStorage.setItem(SEEN, "1"); } catch { /* private window */ } onClose(); };
  return (
    <Modal title="What you can do here" onClose={close}>
      <div className="tour" aria-live="polite">
        <div className="tour-icon">{step.icon}</div>
        <div className="stack" style={{ gap: 10 }}>
          <span className="eyebrow">{i + 1} of {STEPS.length}</span>
          <h3 className="serif" style={{ fontSize: 28, fontWeight: 400, lineHeight: 1.15 }}>{step.title}</h3>
          <p style={{ fontSize: 16.5 }}>{step.body}</p>
          <p className="tour-where"><b>Where:</b> {step.where}</p>
        </div>
      </div>
      <div className="tour-dots" role="tablist" aria-label="Tour steps">
        {STEPS.map((s, k) => (
          <button key={s.title} role="tab" tabIndex={-1} aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} onClick={() => setI(k)} />
        ))}
      </div>
      <div className="spread" style={{ marginTop: 18, flexWrap: "wrap", gap: 10 }}>
        <button className="link" onClick={close}>{last ? "Close" : "Skip the tour"}</button>
        <div className="row" style={{ gap: 8 }}>
          {i > 0 && <button className="btn quiet" onClick={() => setI(i - 1)}>Back</button>}
          {last ? <button className="btn" onClick={close}>Start testing</button>
            : <button className="btn" onClick={() => setI(i + 1)}>Next</button>}
        </div>
      </div>
    </Modal>
  );
}
