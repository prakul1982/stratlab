// At build time, writes each public page's own HTML next to index.html (dist/terms/index.html and so on), with that page's
// title, description, canonical address and robots tag already in it, its own heading and opening words in the page's
// plain start-up block (R7V-008), and structured data: the home page's Organization, WebSite and FAQ, and the FAQ on /faq,
// from the same words the page draws. A crawler or a link preview that doesn't run scripts then sees the right page, not
// the home page's tags and words. Also writes dist/404.html, the page Vercel serves, with a 404 status, for an address
// nothing is at (vercel.json sends only the app's own addresses to index.html; a library strategy's address is its own
// file, so an unknown one is a 404 too). The app still draws every page itself.
// unit/seo.test.mjs checks the output of these functions.
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { absolute, BROWSE_COMPANIES, HOME_DESCRIPTION, INSTAGRAM, LIBRARY_SEEDS, libraryMeta, NOT_FOUND_DESCRIPTION, PAGES, SITE, withBrand } from "../src/content/seo.ts";
import { FAQ, faqText } from "../src/content/faq.ts";
import { AD_PAGE } from "../src/content/ad.ts";
import { DEFAULT_BUSINESS, inline, LEGAL_BLOCKS as POLICY_BLOCKS, LEGAL_UPDATED } from "../src/content/legal.ts";
import { ABOUT_BLOCKS } from "../src/content/about.ts";
import { CANCEL_NOTE, DATA_LINE, TRUST_LINE } from "../src/content/trust.ts";
/** Every page drawn from the policy text: the policies and /about (kept apart in the app so a policy page doesn't download it). */
const LEGAL_BLOCKS = { "/about": ABOUT_BLOCKS, ...POLICY_BLOCKS };
import { KEY, PLAN_IDS, PLAN_NAME, PRICE, WHO } from "../src/lib/plans.ts";

const attr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const text = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
/** JSON-LD; "<" is written as \u003c so no word of the questions can close the tag. */
const ld = (graph) => `<script type="application/ld+json">${JSON.stringify(graph).replace(/</g, "\\u003c")}</script>`;

/** The questions a page answers, as search engines read them (the same words the page draws). */
const faqPage = () => ({ "@context": "https://schema.org", "@type": "FAQPage",
  mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: faqText(f) } })) });

/** The home page's structured data: who runs it, the site, and the questions the page answers (the page's own FAQ). */
export function homeJsonLd() {
  return ld([
    { "@context": "https://schema.org", "@type": "Organization", name: "StratLab", url: `${SITE}/`, logo: `${SITE}/icon-512.png`, description: HOME_DESCRIPTION, sameAs: [INSTAGRAM] },
    { "@context": "https://schema.org", "@type": "WebSite", name: "StratLab", url: `${SITE}/`, description: HOME_DESCRIPTION },
    faqPage(),
  ]);
}

/** /faq's structured data: the questions it answers (R7V-008: only the home page carried them). */
export const faqJsonLd = () => ld([faqPage()]);

/** /plans' structured data: each plan with its prices in rupees (GST included), a month and a year, from the same numbers the page draws
 * (lib/plans.ts, which the server's tests keep equal to plans.py): so a crawler reads the plans without running the page (LIVE1A-066). */
export function plansJsonLd() {
  const offer = (plan, label, amount, billing) => ({ "@type": "Offer", name: label === "free" ? PLAN_NAME[plan] : `${PLAN_NAME[plan]}, ${label}`, price: String(amount), priceCurrency: "INR", url: `${SITE}/plans`,
    availability: "https://schema.org/InStock",
    priceSpecification: { "@type": "UnitPriceSpecification", price: String(amount), priceCurrency: "INR", valueAddedTaxIncluded: true, ...(billing ? { billingDuration: billing, unitCode: billing === "P1Y" ? "ANN" : "MON" } : {}) } });
  return ld([{ "@context": "https://schema.org", "@type": "ItemList", name: "StratLab plans", itemListElement: PLAN_IDS.map((id, i) => ({
    "@type": "ListItem", position: i + 1, item: { "@type": "Product", name: `StratLab ${PLAN_NAME[id]}`, description: WHO[id], brand: { "@type": "Brand", name: "StratLab" },
      offers: id === "free" ? [offer(id, "free", 0, null)] : [offer(id, "monthly", PRICE[id][0], "P1M"), offer(id, "yearly", PRICE[id][1], "P1Y")] } })) }]);
}

/** The plans as plain text under /plans' opening words: each plan, what it is for and its prices, for a crawler that runs no script. */
export const plansList = () => `\n<ul class="boot-links">\n${PLAN_IDS.map((id) => `<li><b>${text(PLAN_NAME[id])}</b>: ${text(WHO[id])}. ${id === "free" ? "₹0, no card needed." : `₹${PRICE[id][0].toLocaleString("en-IN")} a month or ₹${PRICE[id][1].toLocaleString("en-IN")} a year, GST included.`}</li>`).join("\n")}\n</ul>`;

/** The plain block's words for a page: its heading, its opening paragraphs and, on /faq, every question and answer. */
export function bootBody({ heading, summary, faq = false }) {
  const paras = summary.map((p) => `<p>${text(p)}</p>`).join("\n");
  const qa = faq ? "\n" + FAQ.map((f) => `<h2>${text(f.q)}</h2>\n${f.a.map((a) => `<p>${text(a)}</p>`).join("\n")}`).join("\n") : "";
  return `<h1>${text(heading)}</h1>\n${paras}${qa}`;
}

/** A policy page's whole text as HTML (content/legal.ts, the words the app draws too), so /terms, /privacy, /refunds and
 * /contact read without JavaScript, and still do when the app's files fail to download. */
export function legalBody(path, heading) {
  const tok = (t) => t.t === "b" ? `<b>${text(t.s)}</b>` : t.t === "code" ? `<code>${text(t.s)}</code>`
    : t.t === "mail" ? `<a href="mailto:${attr(t.to)}">${text(t.s)}</a>` : t.t === "link" ? `<a href="${attr(t.to)}">${text(t.s)}</a>` : text(t.s);
  const html = (s) => inline(s, DEFAULT_BUSINESS).map(tok).join("");
  const blocks = LEGAL_BLOCKS[path].map((b) => "h" in b ? `<h2>${text(b.h)}</h2>`
    : "p" in b ? `<p>${html(b.p)}</p>`
    : `<ul>\n${b.ul.filter((li) => typeof li === "string" || DEFAULT_BUSINESS[li.when]).map((li) => `<li>${html(typeof li === "string" ? li : li.text)}</li>`).join("\n")}\n</ul>`);
  return `<h1>${text(heading)}</h1>\n<p>Last updated ${text(LEGAL_UPDATED[path])}</p>\n${blocks.join("\n")}`;
}

/** The 404 page's way back: the home page, the company pages and the strategy library (plain links, no script needed). */
export const NOT_FOUND_LINKS = `\n<ul class="boot-links">\n<li><a href="/">Home</a></li>\n<li><a href="/stocks">Company pages</a></li>\n<li><a href="/library">Strategy library</a></li>\n</ul>`;

// ---------- the home page's start-up frame (LIVE13B-001) ----------
// While the landing's code downloads, a visitor whose browser runs scripts sees the landing's own header and hero, drawn from the HTML
// with the app's stylesheet (a render-blocking link in the head): the same classes, so the same column, wrap and place, the heading
// in Fraunces on the same three lines, the lede and the buttons in place. When the app draws, nothing moves (LIVE12B-001 showed the
// heading alone for 3.5 s, then re-wrapped it from two lines to three and moved it 39 px). The words are Login.tsx's hero, kept equal
// to it by unit/fix17.test.mjs; they live here, not in the app's code, so the landing's own download is unchanged. A crawler, or a
// browser with scripts off, reads the page's own paragraphs and links (the frame's lines are for scripts on only, index.html).
export const HERO_EYEBROW = "For traders and investors in India and the US";
export const HERO_LEDE = "Write it in plain words. StratLab tests it on years of real prices after every charge, then checks four ways whether the result could be luck. Company research, your holdings and your tax sit beside it.";
export const HERO_SMALL = "Free to start · No card · No coding";
export const HERO_PROOF = "See a verdict that held up, no sign-in";     // conv101 (P4): Login.tsx HeroProof's words
export const HERO_TRUST = `${TRUST_LINE} ${DATA_LINE}`;                  // conv101 (P6): Login.tsx's trust line (under the plans' cards in the frame)
const MARK_SVG = '<svg width="19" height="46" viewBox="254 174 156 382" aria-hidden="true" class="logo-mark"><defs><linearGradient id="boot-g" gradientUnits="userSpaceOnUse" x1="392" y1="228" x2="300" y2="365"><stop offset="0" stop-color="#16CC8F"/><stop offset=".55" stop-color="#0C8A5C"/><stop offset="1" stop-color="#063B28"/></linearGradient><linearGradient id="boot-r" gradientUnits="userSpaceOnUse" x1="285" y1="525" x2="345" y2="395"><stop offset="0" stop-color="#FF585E"/><stop offset=".5" stop-color="#E6333C"/><stop offset="1" stop-color="#930C17"/></linearGradient></defs><path fill="#FFFFFF" d="M266,308C268,322 300,338 330,352C370,372 400,392 404,418C408,432 394,448 390,460C390,440 360,416 320,396C285,378 262,362 257,343C254,330 258,316 266,308Z"/><rect x="381" y="177" width="10" height="56" rx="1.5" fill="#12C48A"/><path fill="url(#boot-g)" d="M345,252C310,268 266,290 266,308C268,322 300,338 330,352C370,372 400,392 404,418V234Q404,230 400,230H361Q357,230 357,234V348L345,342Z"/><rect x="277" y="455" width="11" height="98" rx="1.5" fill="#FF444B"/><path fill="url(#boot-r)" d="M257,343C262,362 285,378 320,396C362,416 391,436 390,460C390,480 350,510 316,530V405L306,399V453Q306,457 302,457H261Q257,457 257,453Z"/></svg>';
const GOOGLE_SVG = '<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>';
const MAIL_SVG = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/></svg>';

/** The template with the landing's own header in place of the plain one: the logo, the site's links (in the same `boot-nav` for a reader with
 * no script) and their phone menu, then `end` (the home page's Sign in button; none on the sign-in page itself). */
function landingHead(template, end) {
  const head = /<header class="boot-head">[\s\S]*?<nav class="boot-nav" aria-label="Site">([\s\S]*?)<\/nav><\/header>/;
  const m = head.exec(template);
  if (!m) throw new Error("index.html has no start-up header");
  const links = m[1];
  return template.replace(head, () => `<header class="lp-nav" data-boot-head><a href="/" class="brand" aria-label="StratLab home"><span class="logo logo-46">${MARK_SVG}<span class="logo-word"><b>Strat</b>Lab</span></span></a>`
    + `<nav class="boot-nav" aria-label="Site">${links}</nav><details class="lp-menu"><summary>Menu</summary><nav aria-label="Site (menu)">${links}</nav></details>`
    + `${end}</header>`);
}

/** The template with the home page's start-up frame: the landing's header (the site's links in the same `boot-nav` for a reader with
 * no script) and its hero copy over the page's own words, which stay in the HTML for crawlers and for scripts off. */
export function heroFrame(template, { heading, summary, after = "", fonts = [] }) {
  // the heading's italic face ("skill"), asked for at once beside the upright one index.html already asks for (publicFonts.mjs): the frame's
  // heading is the page's largest paint, drawn again when a face it waits for arrives (the landing waits for them anyway, entry.tsx)
  fonts = fonts.filter((f) => !template.includes(`/assets/${f}"`));
  if (fonts.length) template = template.replace("</head>", () => fonts.map((f) => `<link rel="preload" as="font" type="font/woff2" crossorigin href="/assets/${attr(f)}">\n`).join("") + "</head>");
  template = landingHead(template, `<a class="btn outline sm boot-js" href="/login">Sign in</a>`);
  const block = /<div class="boot[^"]*" data-boot>\n<h1>[^<]*<\/h1>\n<p>[^<]*<\/p>\n(<p class="boot-foot">[\s\S]*?<\/p>)\n<\/div>/;
  const b = block.exec(template);
  if (!b) throw new Error("index.html has no start-up block");
  const h1 = text(heading).replace(/\bskill\b/, "<em>skill</em>");
  const words = (summary ?? []).map((p) => `<p class="boot-text">${text(p)}</p>`).join("\n");
  const frame = `<div class="lp-hero ruled boot-hero" data-boot>\n<div class="lp-wrap lp-hero-grid"><div class="stack g22 lp-hero-copy">\n`
    + `<span class="eyebrow boot-js">${text(HERO_EYEBROW)}</span>\n<h1 class="serif lp-h1">${h1}</h1>\n<p class="serif lp-lede boot-js">${text(HERO_LEDE)}</p>\n`
    + `<div class="row wrap g12 boot-js"><a class="btn lp-cta" href="/login">${GOOGLE_SVG}Continue with Google</a><a class="btn outline email-way lp-cta-2" href="/login#email">${MAIL_SVG}Sign in with email</a>`
    + `<a class="btn quiet lp-cta-2" href="/library">${text(HERO_PROOF)}</a></div>\n<p class="small muted boot-js">${text(HERO_SMALL)}</p>\n`

    + `${words}${after.replace(/<ul class="boot-links">/, '<ul class="boot-links boot-text">')}\n${b[1].replace('class="boot-foot"', 'class="boot-foot boot-text"')}\n`
    + `</div><div class="boot-demo" aria-hidden="true"></div></div>\n</div>`;
  return template.replace(block, () => frame);
}

// ---------- the sign-in page's start-up frame (LIVE16B-001) ----------
// /login and /signup while the code downloads: the sign-in page itself (the landing's header, the heading, one line, Continue with Google
// and the email form, the small print), drawn from the HTML with the app's stylesheet and the classes pages/Login.tsx draws, so the real
// choices are on screen at once and nothing moves when the app draws over them. It said "StratLab signs in with your Google account" with no
// button for up to 3.25 s (live, 19 Nov), though email sign-in is on. A press or a typed address before the app is ready is kept by
// public/signin-early.js and done by the app once it draws (both buttons start disabled and that script enables them, so a press before it
// has run is never a plain form submit that reloads the page and loses the address); with email sign-in off in /config.js that script takes the email way out.
export const loginWords = (signup) => {
  const verb = signup ? "Sign up" : "Sign in";
  return { verb, lede: `${verb} with your Google account or your email address: no password to set up.`,
    small: "Google sign-in reads only your name and email address; email sign-in reads only your email address. By continuing you agree to the " };
};

export function loginFrame(template, { heading, summary, signup = false }) {
  template = landingHead(template, "");
  const block = /<div class="boot[^"]*" data-boot>\n<h1>[^<]*<\/h1>\n<p>[^<]*<\/p>\n(<p class="boot-foot">[\s\S]*?<\/p>)\n<\/div>/;
  const b = block.exec(template);
  if (!b) throw new Error("index.html has no start-up block");
  const w = loginWords(signup);
  const lede = text(w.lede).replace(" or your email address", '<span data-boot-or> or your email address</span>');
  const small = text(w.small).replace("; email sign-in reads only your email address", '<span data-boot-or>; email sign-in reads only your email address</span>');
  const words = (summary ?? []).map((p) => `<p class="boot-text">${text(p)}</p>`).join("\n");
  const frame = `<section id="top" class="lp-hero ruled boot-login" data-boot>\n<div class="lp-wrap lp-hero-grid lp-hero-solo lp-hero-login"><div class="stack g22 lp-hero-copy">\n`
    + `<span class="eyebrow">Is your trading idea <em>skill</em> or luck?</span>\n<h1 class="serif lp-h1 lp-own-h1">${text(heading)}</h1>\n<p class="serif lp-lede">${lede}</p>\n`
    + `<div class="row wrap g12"><button type="button" class="btn lp-cta" data-boot-google disabled>${GOOGLE_SVG}Continue with Google</button></div>\n`
    + `<div class="email-signin" data-boot-email><p class="email-signin-or" aria-hidden="true"><span>or</span></p><form class="email-signin-form" novalidate>`
    + `<label for="boot-email" class="email-signin-label">${w.verb} with email</label><div class="email-signin-row">`
    + `<input id="boot-email" class="k-input" autocomplete="email" inputmode="email" placeholder="you@example.com" aria-describedby="boot-email-help" type="email" name="email">`
    + `<button type="submit" class="btn outline" disabled>Email me a code</button></div><span id="boot-email-help" class="small muted">We email a one-time code and link. No password.</span></form></div>\n`
    + `<p class="small muted">${small}<a class="link" href="/terms">Terms</a> and <a class="link" href="/privacy">Privacy policy</a>.</p>\n`
    + `${words}\n${b[1].replace('class="boot-foot"', 'class="boot-foot boot-text"')}\n</div></div>\n</section>`;
  // LIVE17B-001: read from the head, first, at high priority, and run (defer) once the frame is parsed and before the app's own module: at
  // the end of the body, async, it came behind the app's chunks and the frame's buttons waited until 3.6 s
  const early = '<script src="/signin-early.js" defer fetchpriority="high"></script>';
  const head = '<script src="/config.js"></script>';
  if (!template.includes(head)) throw new Error("index.html has no config.js script");
  return template.replace(block, () => frame).replace(head, () => `${head}\n${early}`);
}

// ---------- the Plans page's start-up frame (LIVE18B-003) ----------
// A visitor's /plans while the code downloads: the Plans page itself as the app first draws it (pages/Login.tsx Pricing, `top`, while the
// prices are on their way), with the app's stylesheet and the same classes: the landing's header, the heading, the one-line lede's
// placeholder, the billing and currency switches' placeholders, and the three plan cards with their names, who each is for, the price's
// placeholder, the ways in and the five lines. Live it was a different, plain page for about 2 s (a 480 px column, the heading in Georgia,
// the site's links as a text list, prose, no buttons), then the real page replaced it. The words for a reader with no script (who can't
// sign in) are the page's own paragraphs and plans list, shown only then. The Google buttons wait, disabled, as the app's do until the
// prices come; the email way is a plain link to the sign-in page with the plan picked.
/** A loading plan card's Google button's words (pages/Login.tsx landingAction before the offer is read: unit/site81 keeps them equal). */
export const PLAN_FRAME_LABEL = { free: "Continue with Google", basic: "Continue with Google to get Basic", pro: "Continue with Google to get Pro" };   // (conv101, P7: the plan the button is for)

export function plansFrame(template, { heading, summary, after = "" }) {
  template = landingHead(template, `<a class="btn outline sm" href="/login">Sign in</a>`);
  const block = /<div class="boot[^"]*" data-boot>\n<h1>[^<]*<\/h1>\n<p>[^<]*<\/p>\n(<p class="boot-foot">[\s\S]*?<\/p>)\n<\/div>/;
  const b = block.exec(template);
  if (!b) throw new Error("index.html has no start-up block");
  const list = (p) => `<ul class="lp-plan-list">${KEY[p].map((f) => `<li><span aria-hidden="true">✓</span>${text(f)}</li>`).join("")}</ul>`;
  const card = (p) => {
    const label = PLAN_FRAME_LABEL[p];
    const email = p === "free" ? "/login#email" : `/login?plan=${p}#email`;
    return `<div class="lp-card lp-price${p === "pro" ? " lp-price-top" : ""}" data-plan="${p}"><div class="stack g2"><h2 class="h2">${text(PLAN_NAME[p])}</h2><span class="small muted">${text(WHO[p])}</span></div>`
      + `<div class="stack g2"><span class="lp-skel lp-skel-amount${p === "free" ? " lp-skel-amount-one" : ""}" role="img" aria-label="Loading the price"></span></div>`
      + `<div class="lp-plan-ways"><button type="button" class="btn${p === "pro" ? "" : " outline"}" disabled>${text(label)}</button>`
      + `<a class="btn outline email-way lp-plan-email" href="${attr(email)}">${MAIL_SVG}${text(label.replace("Continue with Google", "Sign in with email"))}</a>`
      + `<span class="small muted lp-plan-cancel">${text(p === "free" ? "No card needed" : CANCEL_NOTE)}</span></div>`
      // on a phone the five lines are one fold under the buttons, as the app's PhoneFold draws them; on a wider screen in view (index.html)
      + `<details class="lp-more lp-phone-fold"><summary>What ${text(PLAN_NAME[p])} includes</summary><div class="stack g24">${list(p)}</div></details>`
      + list(p).replace('class="lp-plan-list"', 'class="lp-plan-list boot-wide"') + `</div>`;
  };
  const words = (summary ?? []).map((p) => `<p class="boot-text">${text(p)}</p>`).join("\n");
  const frame = `<section id="pricing" class="lp-sec lp-sec-first boot-plans" data-boot aria-busy="true">\n<div class="lp-wrap stack g32">\n`
    + `<div class="lp-head"><h1 class="serif lp-h2">${text(heading)}</h1><span class="lp-skel lp-skel-p lp-skel-p-one" data-boot-js></span></div>\n`
    + `${words}${after.replace(/<ul class="boot-links">/, '<ul class="boot-links boot-text">')}\n`
    + `<div class="lp-period" data-boot-js><span class="lp-skel lp-skel-seg"></span><span class="lp-skel lp-skel-cur"></span></div>\n`
    + `<div class="lp-prices" data-boot-js>${PLAN_IDS.map(card).join("")}</div>\n`
    + `<div class="lp-faq lp-all-features" data-boot-js><details><summary>Every feature, plan by plan</summary><p class="small muted">Opening the lists…</p></details></div>\n`
    + `<p class="small muted lp-center" data-boot-js>${text(HERO_TRUST)}</p>\n`
    + `<p class="small muted" data-boot-js>Slide decks are on Basic and Pro. </p>\n<span class="lp-skel lp-skel-fine" data-boot-js></span>\n`
    + `${b[1].replace('class="boot-foot"', 'class="boot-foot boot-text"')}\n</div>\n</section>`;
  // with email sign-in off in /config.js, signin-early.js marks the page and the email ways go (index.html), as on /login
  const early = '<script src="/signin-early.js" defer fetchpriority="high"></script>';
  const head = '<script src="/config.js"></script>';
  if (!template.includes(head)) throw new Error("index.html has no config.js script");
  return template.replace(block, () => frame).replace(head, () => `${head}\n${early}`);
}

/** The template (index.html as built) with one page's own tags, and its own heading and words in the plain block. */
export function pageHtml(template, { title, description, canonical, index, jsonld = "", heading, summary, faq = false, body = "", after = "", readable = !!body, hero = false, login = null, plans = false, fonts = [] }) {
  const swap = (re, to) => {
    if (!re.test(template)) throw new Error(`index.html has no ${re}`);
    template = template.replace(re, () => to);
  };
  swap(/<title>[^<]*<\/title>/, `<title>${text(title)}</title>`);
  swap(/<meta name="description" content="[^"]*">/, `<meta name="description" content="${attr(description)}">`);
  swap(/<meta name="robots" content="[^"]*">/, `<meta name="robots" content="${index ? "index, follow" : "noindex, follow"}">`);
  // a page that isn't there (404.html) names no canonical address: the home page as its canonical said the 404 was the
  // home page (R8V-008); nor does any page kept out of search results (R10V-005: /about)
  swap(/<link rel="canonical" href="[^"]*">\n?/, canonical ? `<link rel="canonical" href="${attr(canonical)}">\n` : "");
  swap(/<meta property="og:title" content="[^"]*">/, `<meta property="og:title" content="${attr(title)}">`);
  swap(/<meta property="og:description" content="[^"]*">/, `<meta property="og:description" content="${attr(description)}">`);
  swap(/<meta property="og:url" content="[^"]*">\n?/, canonical ? `<meta property="og:url" content="${attr(canonical)}">\n` : "");
  swap(/<meta name="twitter:title" content="[^"]*">/, `<meta name="twitter:title" content="${attr(title)}">`);
  swap(/<meta name="twitter:description" content="[^"]*">/, `<meta name="twitter:description" content="${attr(description)}">`);
  swap(/<!--jsonld-->/, jsonld);
  if (heading && hero) return heroFrame(template, { heading, summary: summary?.length ? summary : [description], after, fonts });
  // LIVE17B-006: the sign-in page's own words are its lede; its description printed again under the small print (with scripts off) said the
  // same sentence twice. Only words of its own (a summary) are added.
  if (heading && login) return loginFrame(template, { heading, summary: summary?.length ? summary : [], signup: login === "signup" });
  if (heading && plans) return plansFrame(template, { heading, summary: summary?.length ? summary : [description], after });
  if (heading) {
    // the page's one heading and its words, where index.html has the home page's (the app replaces the block when it draws)
    const boot = /(<div class="boot[^"]*" data-boot>\n)<h1>[^<]*<\/h1>\n<p>[^<]*<\/p>/;
    if (!boot.test(template)) throw new Error(`index.html has no ${boot}`);
    // the landing's frame while the code downloads (LIVE13B-001, heroFrame) is the home page's alone: another page keeps the plain block
    template = template.replace(boot, (_, open) => open.replace(/ boot-hero\b/, "")
      .replace("data-boot>", readable ? "data-boot data-readable>" : "data-boot>")
      + (body || bootBody({ heading, summary: summary?.length ? summary : [description], faq }) + after));
  }
  return template;
}

/** The library's strategies as plain links, under its opening words, so a crawler that runs no script finds each one
 * (R45B-006: the served /library page named none of them). */
export const LIBRARY_LINKS = `\n<ul class="boot-links">\n${LIBRARY_SEEDS.map(([id, name]) => `<li><a href="/library/${id}">${text(name)}</a></li>`).join("\n")}\n</ul>`;

/** The home page's way to the company directories (SEO-1), as plain links under its opening words, for a crawler that runs no script. */
export const HOME_LINKS = `\n<ul class="boot-links">\n${BROWSE_COMPANIES.map(([to, name]) => `<li><a href="${attr(to)}">${text(name)}</a></li>`).join("\n")}\n</ul>`;

/** Every file to write, as [path under dist, html]. The home page replaces index.html itself. */
export function pageFiles(template, fonts = []) {
  // R15: the ad landing's page, from its own words (content/ad.ts), not the landing page's table
  const files = [...PAGES, AD_PAGE].map((p) => [p.path === "/" ? "index.html" : `${p.path.slice(1)}/index.html`,
    pageHtml(template, { title: p.title, description: p.description, canonical: p.index ? absolute(p.canonical ?? p.path) : null, index: p.index,
      jsonld: p.path === "/" ? homeJsonLd() : p.path === "/faq" ? faqJsonLd() : p.path === "/plans" ? plansJsonLd() : "", heading: p.heading, summary: p.summary,
      body: LEGAL_BLOCKS[p.path] ? legalBody(p.path, p.heading) : "",
      after: p.path === "/library" ? LIBRARY_LINKS : p.path === "/" ? HOME_LINKS : p.path === "/plans" || p.path === "/pricing" ? plansList() : "",
      faq: p.path === "/faq", hero: p.path === "/", login: p.path === "/login" ? "login" : p.path === "/signup" ? "signup" : null, plans: p.path === "/plans" || p.path === "/pricing", fonts })]);
  files.push(["404.html", pageHtml(template, { title: withBrand("Page not found"), description: NOT_FOUND_DESCRIPTION, canonical: null, index: false,
    heading: "Page not found", summary: [NOT_FOUND_DESCRIPTION], after: NOT_FOUND_LINKS, readable: true })]);
  return files;
}

/** StratLab's own library strategies, one file each (dist/library/<id>/index.html), with that strategy's own tags
 * (R6V-012: they carried the home page's title and canonical address), heading and rules (R7V-008). With `entries`
 * ({id: the public library's entry}), the title, description and opening words lead with the verdict's result, the
 * words the page itself shows once it has drawn ("117.1 points behind buy and hold after costs: …"), so a link preview
 * or a crawler that runs no script reads the same (R8V-008). Without an entry, the strategy's own words. */
export function libraryFiles(template, entries = {}) {
  return LIBRARY_SEEDS.map(([id, name]) => {
    const p = libraryMeta(id, name, entries[id]);
    return [`${p.path.slice(1)}/index.html`, pageHtml(template, { title: p.title, description: p.description, canonical: absolute(p.path), index: true,
      heading: p.heading, summary: p.summary })];
  });
}

/** The API's address for the build to read the public library from: STRATLAB_API_BASE, else where vercel.json sends
 * the company pages (the same server). */
export function apiBase(env = process.env, vercel = null) {
  if (env.STRATLAB_API_BASE) return env.STRATLAB_API_BASE.replace(/\/+$/, "");
  try {
    const v = vercel ?? JSON.parse(readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
    const r = (v.rewrites ?? []).find((x) => x.source === "/stocks/:path*");
    return r ? r.destination.replace(/\/stocks\/:path\*$/, "") : null;
  } catch {
    return null;
  }
}

/** StratLab's own library entries, {id: entry}, read once at build time (a few seconds at most) when the site's host
 * builds it (VERCEL is set there) or STRATLAB_SEO_ONLINE asks for it. {} otherwise (a local or test build stays the
 * same whatever the server holds), when the server can't be reached, or with STRATLAB_SEO_OFFLINE: the pages then carry
 * the strategy's own words, as before. */
export async function libraryEntries(env = process.env, get = globalThis.fetch) {
  const base = apiBase(env);
  if (!base || !(env.VERCEL || env.STRATLAB_SEO_ONLINE) || env.STRATLAB_SEO_OFFLINE || typeof get !== "function") return {};
  try {
    const r = await get(`${base}/public/library?limit=200`, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(8000) });
    if (!r.ok) return {};
    const body = await r.json();
    return Object.fromEntries((body.entries ?? []).filter((e) => e && typeof e.id === "string").map((e) => [e.id, e]));
  } catch {
    return {};
  }
}

/** A plain script as shipped: its whole-line comments left out (LIVE13B-001/004: boot.js, which every visitor downloads before anything else,
 * was a third comments, some 3 KB of the landing's 450 KB budget). The source in public/ keeps them; the code is unchanged. */
export const leanScript = (src) => src.replace(/^[ \t]*\/\*[\s\S]*?\*\/[ \t]*\n/gm, "").replace(/^[ \t]*\/\/.*\n/gm, "");

/** The built file of the landing heading's italic face: Fraunces 400 italic, Latin, as woff2. */
export const heroFonts = (names) => names.filter((n) => /^fraunces-latin-400-italic-[\w-]+\.woff2$/.test(n)).sort();

export function seoPages() {
  let out = "dist";
  return {
    name: "stratlab-seo-pages",
    apply: "build",
    configResolved(c) { out = join(c.root, c.build.outDir); },
    async closeBundle() {
      const template = readFileSync(join(out, "index.html"), "utf8");
      const entries = await libraryEntries();
      const fonts = heroFonts(readdirSync(join(out, "assets")));
      const boot = join(out, "boot.js");
      writeFileSync(boot, leanScript(readFileSync(boot, "utf8")));
      for (const [file, html] of [...pageFiles(template, fonts), ...libraryFiles(template, entries)]) {
        mkdirSync(dirname(join(out, file)), { recursive: true });
        writeFileSync(join(out, file), html);
      }
    },
  };
}
