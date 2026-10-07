import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, CFG } from "../lib/api";
import { Logo } from "../components/Logo";
import { LEGAL_PAGES } from "../components/LegalLinks";

/** Who runs the site, from config.js, so the policies name the real business without a code change. */
const BUSINESS = {
  name: CFG.BUSINESS_NAME || "StratLab",
  email: CFG.CONTACT_EMAIL || "info@stratlab.studio",
  privacy: CFG.PRIVACY_EMAIL || "privacy@stratlab.studio",
  address: CFG.BUSINESS_ADDRESS || "",
  updated: "26 September 2026",
};

const Mail = () => <a className="link" href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>;
const PrivacyMail = () => <a className="link" href={`mailto:${BUSINESS.privacy}`}>{BUSINESS.privacy}</a>;

function Terms() {
  return (
    <>
      <p>These terms cover your use of StratLab (the website and app at stratlab.studio), run by {BUSINESS.name}. By signing in you agree to them.</p>
      <h2 className="h3">What StratLab is</h2>
      <p>StratLab is a research and education tool. You describe trading ideas, test them on past market data, and paper trade them with simulated money. <b>No real orders are ever placed.</b> Nothing on StratLab is investment advice or a recommendation to buy or sell anything, and {BUSINESS.name} is not a SEBI-registered investment adviser or research analyst. Past results, including backtests and paper trading, don't predict future returns. Decisions you make with real money are yours.</p>
      <h2 className="h3">Your account</h2>
      <ul>
        <li>You sign in with a Google account and must be at least 18.</li>
        <li>Keep your account to yourself. One person, one account: making extra accounts to get around plan limits isn't allowed.</li>
        <li>You're responsible for what happens under your account.</li>
      </ul>
      <h2 className="h3">Plans and payment</h2>
      <ul>
        <li>The Free plan costs nothing. Basic and Pro are subscriptions billed monthly or yearly at the prices on the Plans page when you subscribe: in Indian rupees, or in your own currency where the Plans page says so. When a price is shown in another currency but charged in rupees, your card provider converts it and may add its own fee.</li>
        <li>Payments are processed by Razorpay. {BUSINESS.name} never sees or stores your card or bank details.</li>
        <li>A subscription renews automatically at the end of each period until you cancel it. You can cancel any time from the Account page; see <Link className="link" to="/refunds">Cancellation and refunds</Link>.</li>
        <li>If we change a price, it applies from your next renewal after we've told you, and you can cancel before then.</li>
      </ul>
      <h2 className="h3">Fair use</h2>
      <p>Don't misuse the service: no scraping or automated bulk requests, no attempts to break its security or reach other people's data, no reselling access, and nothing unlawful. Plan limits (experiments, AI builds, paper sessions) apply per account. We may limit or suspend accounts that misuse the service.</p>
      <h2 className="h3">What you publish</h2>
      <p>Strategies you publish to the public library, and verdicts you share by link, can be seen by anyone with access. Only publish what you're happy to share. You keep ownership of your ideas and let us display what you publish. We may remove published content that's misleading, abusive or unlawful.</p>
      <h2 className="h3">Market data and AI</h2>
      <p>Prices come from brokers and public sources and can be delayed, incomplete or wrong. AI features can make mistakes: check any rules or research the AI writes before relying on them. The service is provided "as is", and features may change.</p>
      <h2 className="h3">Liability</h2>
      <p>To the extent the law allows, {BUSINESS.name} isn't liable for trading losses or indirect losses arising from using StratLab, and our total liability to you is limited to what you paid us in the 12 months before the claim.</p>
      <h2 className="h3">Ending</h2>
      <p>You can stop using StratLab and cancel at any time. We may end the service or an account with notice, or without notice for misuse. These terms are governed by the laws of India, and courts in India have jurisdiction.</p>
      <h2 className="h3">Changes</h2>
      <p>If these terms change in an important way we'll say so in the app before the change applies. Questions: <Mail />.</p>
    </>
  );
}

function Privacy() {
  return (
    <>
      <p>This policy explains what {BUSINESS.name} collects when you use StratLab, why, and your choices. It is written to meet India's Digital Personal Data Protection Act, 2023.</p>
      <h2 className="h3">What we collect</h2>
      <ul>
        <li><b>Your Google account's email and ID</b>, to sign you in.</li>
        <li><b>What you create:</b> notebooks, strategies, experiments, paper trading sessions, watchlists and settings.</li>
        <li><b>Usage counts</b>, such as experiments and AI builds this month, to apply plan limits.</li>
        <li><b>Alert contacts you choose to add:</b> an email address, a Telegram chat ID, and each device's notification address if you turn on phone notifications.</li>
        <li><b>Billing records:</b> your plan and Razorpay subscription ID. Card, UPI and bank details go to Razorpay only.</li>
        <li><b>Usage analytics:</b> which pages you open and which features you use (such as running a backtest or saving a screen), linked to your account's internal ID, never your email or name, and without your holdings, symbols you search or amounts. No screen recordings or typed text. Skipped if your browser sends Do Not Track.</li>
        <li><b>Technical logs:</b> request logs and error reports kept to run and fix the service. Error reports carry no email, IP address or request contents.</li>
      </ul>
      <h2 className="h3">How it's used</h2>
      <p>Only to run StratLab: sign-in, running your tests and paper sessions, sending the alerts you asked for, billing, preventing abuse, and fixing problems. We don't sell your data, and there are no advertising trackers.</p>
      <h2 className="h3">Who processes it for us</h2>
      <ul>
        <li>Supabase (database and sign-in), Railway (server) and Vercel (website) host the service.</li>
        <li>Razorpay processes payments.</li>
        <li>AI providers (such as Groq, Google Gemini, Cerebras, Mistral, OpenRouter or Anthropic) receive the text you type into AI features, like an idea to turn into rules, but not your email.</li>
        <li>Telegram and our email provider deliver alerts you turn on. Sentry receives error reports without personal details.</li>
        <li>PostHog (hosted in the US) receives the usage analytics described above.</li>
      </ul>
      <p>Some of these providers store data outside India, under their own security and privacy commitments.</p>
      <h2 className="h3">Cookies and storage</h2>
      <p>Your browser keeps your sign-in session and a few preferences (like light or dark mode). Nothing is used for advertising.</p>
      <h2 className="h3">Keeping and deleting</h2>
      <p>We keep your data while your account is open. You can delete notebooks and sessions yourself at any time. To see what we hold, correct it, or delete your account and its data, email <PrivacyMail />; we'll act within 30 days. Billing records may be kept longer where tax law requires.</p>
      <h2 className="h3">Security</h2>
      <p>Data is sent over HTTPS, access is limited to your own account, and secrets stay on the server. No system is perfectly secure; if a breach affects you, we'll tell you as the law requires.</p>
      <h2 className="h3">Children</h2>
      <p>StratLab is for adults (18+). We don't knowingly collect children's data.</p>
      <h2 className="h3">Contact and grievances</h2>
      <p>For privacy questions, requests or complaints, email <PrivacyMail />. If you're not satisfied, you can complain to the Data Protection Board of India.</p>
    </>
  );
}

function Refunds() {
  return (
    <>
      <h2 className="h3">Cancelling</h2>
      <ul>
        <li>Cancel any time from <b>Account → Plan → Cancel subscription</b>. No questions, no calls.</li>
        <li>You keep your paid plan until the end of the period you've paid for, then move to the Free plan. You won't be charged again.</li>
        <li>Your notebooks and results stay; only paid features and limits change.</li>
      </ul>
      <h2 className="h3">Refunds</h2>
      <ul>
        <li>Because you can use a paid plan straight away and cancel any time before it renews, payments for a period that has started aren't refunded.</li>
        <li>We refund in full if you were charged twice, charged after cancelling, or charged but your plan didn't activate and we can't fix it.</li>
        <li>To ask for a refund, email <Mail /> from your account's email with the payment date. We reply within 2 working days. Approved refunds go back to the original payment method within 5–7 working days (your bank may take longer to show it).</li>
      </ul>
      <h2 className="h3">Delivery</h2>
      <p>StratLab is an online service: nothing is shipped. A paid plan is active on your account as soon as the payment goes through, usually within a minute.</p>
    </>
  );
}

function Contact() {
  return (
    <>
      <p>We're happy to help with your account, billing, refunds, privacy requests or anything else.</p>
      <ul>
        <li><b>Email:</b> <Mail />. We reply within 2 working days.</li>
        <li><b>Business:</b> {BUSINESS.name}</li>
        {BUSINESS.address && <li><b>Address:</b> {BUSINESS.address}</li>}
      </ul>
      <p className="small muted">For billing questions, include your account's email and the payment date so we can find it quickly.</p>
    </>
  );
}

const BODY: Record<string, () => ReactNode> = { "/terms": Terms, "/privacy": Privacy, "/refunds": Refunds, "/contact": Contact };

/** The public policy pages. They open without signing in, as payment providers and app stores require. */
export function LegalPage() {
  const { pathname } = useLocation();
  // the seller's details set in Admin → Invoices (legal name, address, business email), when the owner has set them
  const [, seen] = useState(0);
  useEffect(() => {
    let live = true;
    api<{ legal_name?: string; address?: string; email?: string }>("/public/business").then((b) => {
      if (!live || !b) return;
      if (b.legal_name) BUSINESS.name = b.legal_name;
      if (b.address && !CFG.BUSINESS_ADDRESS) BUSINESS.address = b.address;
      if (b.email) BUSINESS.email = b.email;
      seen((n) => n + 1);
    }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  const page = LEGAL_PAGES.find((p) => p.path === pathname) ?? LEGAL_PAGES[0];
  const Body = BODY[page.path];
  return (
    <div className="legal">
      <header className="legal-head">
        <Link to="/" aria-label="StratLab home"><Logo size={30} /></Link>
        <nav className="row wrap legal-links" aria-label="Policies">
          {LEGAL_PAGES.map((p) => <Link key={p.path} className={`small ${p.path === page.path ? "" : "muted"}`} to={p.path}
            aria-current={p.path === page.path ? "page" : undefined}>{p.title}</Link>)}
        </nav>
      </header>
      <article className="legal-body stack">
        <h1 className="page-title">{page.title}</h1>
        <p className="small muted">Last updated {BUSINESS.updated}</p>
        <Body />
      </article>
    </div>
  );
}
