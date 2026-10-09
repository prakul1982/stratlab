// At build time, writes each public page's own HTML next to index.html (dist/terms/index.html and so on), with that page's
// title, description, canonical address and robots tag already in it, its own heading and opening words in the page's
// plain start-up block (R7V-008), and structured data: the home page's Organization, WebSite and FAQ, and the FAQ on /faq,
// from the same words the page draws. A crawler or a link preview that doesn't run scripts then sees the right page, not
// the home page's tags and words. Also writes dist/404.html, the page Vercel serves, with a 404 status, for an address
// nothing is at (vercel.json sends only the app's own addresses to index.html; a library strategy's address is its own
// file, so an unknown one is a 404 too). The app still draws every page itself.
// unit/seo.test.mjs checks the output of these functions.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { absolute, HOME_DESCRIPTION, LIBRARY_SEEDS, libraryMeta, NOT_FOUND_DESCRIPTION, PAGES, SITE } from "../src/content/seo.ts";
import { FAQ, faqText } from "../src/content/faq.ts";

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
    { "@context": "https://schema.org", "@type": "Organization", name: "StratLab", url: `${SITE}/`, logo: `${SITE}/icon-512.png`, description: HOME_DESCRIPTION },
    { "@context": "https://schema.org", "@type": "WebSite", name: "StratLab", url: `${SITE}/`, description: HOME_DESCRIPTION },
    faqPage(),
  ]);
}

/** /faq's structured data: the questions it answers (R7V-008: only the home page carried them). */
export const faqJsonLd = () => ld([faqPage()]);

/** The plain block's words for a page: its heading, its opening paragraphs and, on /faq, every question and answer. */
export function bootBody({ heading, summary, faq = false }) {
  const paras = summary.map((p) => `<p>${text(p)}</p>`).join("\n");
  const qa = faq ? "\n" + FAQ.map((f) => `<h2>${text(f.q)}</h2>\n${f.a.map((a) => `<p>${text(a)}</p>`).join("\n")}`).join("\n") : "";
  return `<h1>${text(heading)}</h1>\n${paras}${qa}`;
}

/** The template (index.html as built) with one page's own tags, and its own heading and words in the plain block. */
export function pageHtml(template, { title, description, canonical, index, jsonld = "", heading, summary, faq = false }) {
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
  if (heading) {
    // the page's one heading and its words, where index.html has the home page's (the app replaces the block when it draws)
    const boot = /(<div class="boot[^"]*" data-boot>\n)<h1>[^<]*<\/h1>\n<p>[^<]*<\/p>/;
    if (!boot.test(template)) throw new Error(`index.html has no ${boot}`);
    template = template.replace(boot, (_, open) => open + bootBody({ heading, summary: summary?.length ? summary : [description], faq }));
  }
  return template;
}

/** Every file to write, as [path under dist, html]. The home page replaces index.html itself. */
export function pageFiles(template) {
  const files = PAGES.map((p) => [p.path === "/" ? "index.html" : `${p.path.slice(1)}/index.html`,
    pageHtml(template, { title: p.title, description: p.description, canonical: p.index ? absolute(p.canonical ?? p.path) : null, index: p.index,
      jsonld: p.path === "/" ? homeJsonLd() : p.path === "/faq" ? faqJsonLd() : "", heading: p.heading, summary: p.summary,
      faq: p.path === "/faq" })]);
  files.push(["404.html", pageHtml(template, { title: "Page not found · StratLab", description: NOT_FOUND_DESCRIPTION, canonical: null, index: false,
    heading: "Page not found", summary: [NOT_FOUND_DESCRIPTION] })]);
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

export function seoPages() {
  let out = "dist";
  return {
    name: "stratlab-seo-pages",
    apply: "build",
    configResolved(c) { out = join(c.root, c.build.outDir); },
    async closeBundle() {
      const template = readFileSync(join(out, "index.html"), "utf8");
      const entries = await libraryEntries();
      for (const [file, html] of [...pageFiles(template), ...libraryFiles(template, entries)]) {
        mkdirSync(dirname(join(out, file)), { recursive: true });
        writeFileSync(join(out, file), html);
      }
    },
  };
}
