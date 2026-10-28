/* The words of the four policy pages (/terms, /privacy, /refunds, /contact): one source, read by the app (pages/LegalPage.tsx
 * draws them) and by the build (scripts/seoPages.mjs writes them into each page's own HTML, so they read without
 * JavaScript, even when the app's files fail to download). Plain data: no React.
 *
 * Inline marks inside a string: **bold**, `code`, [label](/path) for a page of the site, [label](mail:email|billing|privacy)
 * for a mailto link, {name} {email} {billing} {privacy} {address} {gstin} for the business's details, and {gstin?words}
 * or {address?words} for words that show only when that detail is set. */

export type Block = { h: string } | { p: string; small?: boolean } | { ul: (string | { when: "address" | "gstin"; text: string })[] };

export type Business = { name: string; email: string; billing: string; privacy: string; address: string; gstin: string };

/** The business's details when nothing has set them (the app reads config.js and the server's invoice settings over these). */
export const DEFAULT_BUSINESS: Business = { name: "StratLab", email: "support@stratlab.studio", billing: "billing@stratlab.studio",
  privacy: "privacy@stratlab.studio", address: "", gstin: "" };

/** The day each page's words last changed (the sitemap's dates, backend/app/site_pages.py, say the same). */
export const LEGAL_UPDATED: Record<string, string> = { "/terms": "16 October 2026", "/privacy": "28 October 2026", "/refunds": "25 October 2026", "/contact": "26 September 2026" };

export type Tok = { t: "text" | "b" | "code"; s: string } | { t: "link"; s: string; to: string } | { t: "mail"; s: string; to: string };

const fill = (s: string, biz: Business) =>
  s.replace(/\{(address|gstin)\?([^}]*)\}/g, (_, k: "address" | "gstin", w: string) => (biz[k] ? w : ""))
    .replace(/\{(name|email|billing|privacy|address|gstin)\}/g, (_, k: keyof Business) => biz[k]);

/** One string's inline marks as tokens, the business's details filled in. */
export function inline(text: string, biz: Business): Tok[] {
  const out: Tok[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/g;
  let at = 0, m: RegExpExecArray | null;
  const plain = (s: string) => { const f = fill(s, biz); if (f) out.push({ t: "text", s: f }); };
  while ((m = re.exec(text))) {
    plain(text.slice(at, m.index));
    if (m[1] != null) out.push({ t: "b", s: fill(m[1], biz) });
    else if (m[2] != null) out.push({ t: "code", s: m[2] });
    else if (m[4].startsWith("mail:")) out.push({ t: "mail", s: fill(m[3], biz), to: biz[m[4].slice(5) as keyof Business] });
    else out.push({ t: "link", s: fill(m[3], biz), to: m[4] });
    at = m.index + m[0].length;
  }
  plain(text.slice(at));
  return out;
}

export const LEGAL_BLOCKS: Record<string, Block[]> = {
  "/terms": [
    { p: "These terms cover your use of StratLab (the website and app at stratlab.studio), run by {name}. By signing in you agree to them." },
    { h: "What StratLab is" },
    { p: "StratLab is a research and education tool. You describe trading ideas, test them on past market data, and paper trade them with simulated money. **No real orders are ever placed.** Nothing on StratLab is investment advice or a recommendation to buy or sell anything, and {name} is not a SEBI-registered investment adviser or research analyst. Past results, including backtests and paper trading, don't predict future returns. Decisions you make with real money are yours." },
    { h: "Your account" },
    { ul: [
      "You sign in with a Google account and must be at least 18.",
      "Keep your account to yourself. One person, one account: making extra accounts to get around plan limits isn't allowed.",
      "You're responsible for what happens under your account.",
    ] },
    { h: "Plans and payment" },
    { ul: [
      "The Free plan costs nothing. Basic and Pro are subscriptions billed monthly or yearly at the prices on the Plans page when you subscribe: in Indian rupees for now, and in another currency only where the Plans page says so. When a price is shown in another currency but charged in rupees, your card provider converts it and may add its own fee. {gstin?Rupee prices include 18% GST.}",
      "Payments are processed by Razorpay. {name} never sees or stores your card or bank details.",
      "A subscription renews automatically at the end of each period until you cancel it. You can cancel any time from the Account page; see [Cancellation and refunds](/refunds).",
      "If we change a price, it applies from your next renewal after we've told you, and you can cancel before then.",
    ] },
    { h: "Fair use" },
    { p: "Don't misuse the service: no scraping or automated bulk requests, no attempts to break its security or reach other people's data, no reselling access, and nothing unlawful. Plan limits (backtests, AI builds, strategies paper traded at a time) apply per account. We may limit or suspend accounts that misuse the service." },
    { h: "What you publish" },
    { p: "Strategies you publish to the public library, and verdicts you share by link, can be seen by anyone with access. Only publish what you're happy to share. You keep ownership of your ideas and let us display what you publish. We may remove published content that's misleading, abusive or unlawful." },
    { h: "Market data and AI" },
    { p: "Prices come from brokers and public sources and can be delayed, incomplete or wrong. AI features can make mistakes: check any rules or research the AI writes before relying on them. The service is provided \"as is\", and features may change." },
    { h: "Liability" },
    { p: "To the extent the law allows, {name} isn't liable for trading losses or indirect losses arising from using StratLab, and our total liability to you is limited to what you paid us in the 12 months before the claim." },
    { h: "Ending" },
    { p: "You can stop using StratLab and cancel at any time. We may end the service or an account with notice, or without notice for misuse. These terms are governed by the laws of India, and courts in India have jurisdiction." },
    { h: "Changes" },
    { p: "If these terms change in an important way we'll say so in the app before the change applies. Questions: [{email}](mail:email)." },
  ],
  "/privacy": [
    { p: "This policy explains what {name} collects when you use StratLab, why, and your choices. It is written to meet India's Digital Personal Data Protection Act, 2023." },
    { h: "What we collect" },
    { ul: [
      "**Your Google account's email and ID**, to sign you in.",
      "**What you create:** notebooks, strategies, experiments, paper trading sessions, watchlists and settings.",
      "**Usage counts**, such as experiments and AI builds this month, to apply plan limits.",
      "**Alert contacts you choose to add:** an email address, each device's notification address if you turn on phone notifications, and a Telegram chat ID if Telegram is offered in Settings and you connect it.",
      "**Billing records:** your plan and Razorpay subscription ID. Card, UPI and bank details go to Razorpay only.",
      "**Usage analytics:** which pages you open and which features you use (such as running a backtest or saving a screen), and when a page breaks, the error's type and message with any addresses, IDs and long numbers removed; without your holdings, symbols you search or amounts. No screen recordings or typed text. Before you sign in, this is tied only to a random ID made in your browser, not to any account. Once you sign in, it is linked to your account's internal ID, never your email or name. Not collected at all if your browser sends Do Not Track or Global Privacy Control.",
      "**Technical logs:** request logs and error reports kept to run and fix the service. Error reports carry no email, IP address or request contents.",
    ] },
    { h: "How it's used" },
    { p: "Only to run StratLab: sign-in, running your tests and paper sessions, sending the alerts you asked for, billing, preventing abuse, and fixing problems. We don't sell your data. The ads and analytics described below load only if you allow them." },
    { h: "Ads and analytics, only if you allow them" },
    { p: "StratLab asks once, with an \"Allow\" and a \"No thanks\" button, before it loads any of the following. Say no and none of them is downloaded or sets anything. Basic and Pro have no ads." },
    { ul: [
      "**Google ads (AdSense):** public pages (the landing page, company pages, the strategy library and shared verdicts) and Free accounts may show ads. Google may set cookies and similar storage in your browser, and may read your IP address and device details, to choose, limit and measure ads and to prevent fraud.",
      "**Meta Pixel (Facebook and Instagram):** when it is switched on, it tells Meta which StratLab pages you opened and when you finished creating an account, so StratLab can measure its own advertising on Meta. It sends no email, holdings, notebooks or typed text, and its automatic button and page-detail tracking is off.",
      "**Microsoft Clarity:** when it is on, it records how pages are used (scrolls, taps and where people get stuck) as a replayable session with all text and form fields hidden. Microsoft may set cookies and process the recording.",
      "**Where none of them run:** no ad, pixel or recording is on Money, tax, holdings, net worth, Account, Settings, Admin, sign-in or payment pages, or in emails. A recording that was running stops when you open one of them.",
      "**Your browser can say no for you:** if it sends Do Not Track or Global Privacy Control, the Meta Pixel and Clarity do not load. StratLab gives none of these your email, holdings, notebooks or anything you type.",
      "**Asked about ads alone:** on a company page, the question is about Google ads only, and \"Allow\" there lets those ads load and nothing else. Meta's and Microsoft's are asked about separately and stay off until you allow them.",
      "**To change your answer,** use \"Change my choice\" on this page (taking a yes back reloads the page), or clear this site's data in your browser's settings. Google's own ad settings are at adssettings.google.com.",
    ] },
    { h: "Who processes it for us" },
    { ul: [
      "Supabase (database and sign-in), Railway (server) and Vercel (website) host the service.",
      "Google (AdSense) serves the ads on public pages and to Free accounts, Meta (the Meta Pixel) measures StratLab's own advertising, and Microsoft (Clarity) records how pages are used, each only if you allow it.",
      "Razorpay processes payments.",
      "AI providers receive the text you type into AI features, like an idea to turn into rules, but not your email. StratLab can send it to any of these eleven: Anthropic, Cerebras, Cloudflare Workers AI, Google Gemini, Groq, Hugging Face, Mistral, NVIDIA API catalog, OpenRouter, SambaNova and Z.ai. Which one answers a given request varies, and only those with a key set up on the server are used. Z.ai is a China-based service. Mistral and Google Gemini also read the public company filings that are scanned pictures. Some of these services are used on their free plans, whose terms let the provider keep what is sent and use it to improve or train their models (Google Gemini's free tier and Mistral's free plan say so): don't type anything into an AI feature that you wouldn't want a provider to keep.",
      "Our email provider delivers the alerts you turn on by email, and Telegram delivers them if it is offered in Settings and you connect it. Sentry receives error reports without personal details.",
      "PostHog (hosted in the US) receives the usage analytics described above.",
    ] },
    { p: "Some of these providers store data outside India, under their own security and privacy commitments." },
    { h: "Cookies and storage" },
    { p: "StratLab sets no cookies itself. It uses your browser's local storage, which stays on your device until you clear it, and session storage, which goes when you close the tab. Nothing StratLab stores is used for advertising. The ad and analytics scripts described above, if you allow them, can set their own cookies." },
    { ul: [
      "**Before you sign in**, on your first visit: a preference for light or dark mode and for the currency prices are shown in, a note that the page reloaded once if a file failed to load, and, when usage analytics are on, one entry from PostHog (its name starts with `ph_`) holding a random anonymous ID and session details. That PostHog entry is not made, and no analytics request is sent, if your browser sends Do Not Track or Global Privacy Control.",
      "**Your answer about ads and analytics:** `stratlab.ads`, \"yes\" or \"no\" with the date (and, for a yes about Google ads alone, a note saying so), kept in your browser for a year. It stays on your device.",
      "**While Google sign-in runs:** the page to come back to, and an invite code if you arrived by a friend's link.",
      "**After you sign in:** your sign-in session, which the sign-in service refreshes, and a few choices such as which menu is open and whether you have seen the tour.",
      "**To pay:** Razorpay's payment window can set its own cookies and storage on its own pages and windows.",
    ] },
    { p: "You can clear all of this from your browser's settings; you will be signed out and the choices above reset." },
    { h: "Keeping and deleting" },
    { p: "We keep your data while your account is open. You can delete notebooks and sessions yourself at any time. The Account page has \"Download all my data\" to get a copy of what we hold, \"Delete all my data\" to erase it, and \"Delete my account\" to erase it and delete your sign-in account too, at once and with no way back. Invoices and the payment records behind them are kept, as tax law requires; everything else goes. Or email [{privacy}](mail:privacy) to see what we hold or correct it; we'll act within 30 days." },
    { h: "Security" },
    { p: "Data is sent over HTTPS, access is limited to your own account, and secrets stay on the server. No system is perfectly secure; if a breach affects you, we'll tell you as the law requires." },
    { h: "Children" },
    { p: "StratLab is for adults (18+). We don't knowingly collect children's data." },
    { h: "Contact and grievances" },
    { p: "For privacy questions, requests or complaints, email [{privacy}](mail:privacy). If you're not satisfied, you can complain to the Data Protection Board of India." },
  ],
  "/refunds": [
    { h: "Cancelling" },
    { ul: [
      "Cancel any time from **Account → Plan and usage → Cancel subscription**. No questions, no calls.",
      "You keep your paid plan until the end of the period you've paid for, then move to the Free plan. You won't be charged again.",
      "Your notebooks and results stay; only paid features and limits change.",
    ] },
    { h: "Refunds" },
    { ul: [
      "Changed your mind? Ask within 7 days of any payment, monthly or yearly, and we refund it in full. The plan then ends and your account moves to the Free plan.",
      "After those 7 days, the period you've paid for isn't refunded; you can still cancel any time so it doesn't renew.",
      "Whenever it happens, we refund in full if you were charged twice, charged after cancelling, or charged but your plan didn't activate and we can't fix it.",
      "To ask for a refund, email [{billing}](mail:billing) from your account's email with the payment date. We reply within 2 working days. Approved refunds go back to the original payment method within 5–7 working days (your bank may take longer to show it).",
    ] },
    { h: "Delivery" },
    { p: "StratLab is an online service: nothing is shipped. A paid plan is active on your account as soon as the payment goes through, usually within a minute." },
  ],
  "/contact": [
    { p: "We're happy to help with your account, billing, refunds, privacy requests or anything else." },
    { ul: [
      "**Help and questions:** [{email}](mail:email). We reply within 2 working days.",
      "**Payments, invoices and refunds:** [{billing}](mail:billing)",
      "**Privacy and your data:** [{privacy}](mail:privacy)",
      "**Business:** {name}",
      { when: "address", text: "**Address:** {address}" },
      { when: "gstin", text: "**GSTIN:** {gstin}" },
    ] },
    { p: "For billing questions, write to [{billing}](mail:billing) with your account's email and the payment date so we can find it quickly.", small: true },
  ],
};
