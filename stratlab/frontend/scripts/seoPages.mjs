// At build time, writes each public page's own HTML next to index.html (dist/terms/index.html and so on), with that page's
// title, description, canonical address and robots tag already in it, and the home page's structured data (Organization,
// WebSite and the FAQ, from the same words the page draws). A crawler or a link preview that doesn't run scripts then sees
// the right page, not the home page's tags. Also writes dist/404.html, the page Vercel serves, with a 404 status, for an
// address nothing is at (vercel.json sends only the app's own addresses to index.html). The app still draws every page itself.
// unit/seo.test.mjs checks the output of these functions.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { absolute, HOME_DESCRIPTION, NOT_FOUND_DESCRIPTION, PAGES, SITE } from "../src/content/seo.ts";
import { FAQ, faqText } from "../src/content/faq.ts";

const attr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const text = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

/** The home page's structured data: who runs it, the site, and the questions the page answers (the page's own FAQ). */
export function homeJsonLd() {
  const graph = [
    { "@context": "https://schema.org", "@type": "Organization", name: "StratLab", url: `${SITE}/`, logo: `${SITE}/icon-512.png`, description: HOME_DESCRIPTION },
    { "@context": "https://schema.org", "@type": "WebSite", name: "StratLab", url: `${SITE}/`, description: HOME_DESCRIPTION },
    { "@context": "https://schema.org", "@type": "FAQPage",
      mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: faqText(f) } })) },
  ];
  // "<" is written as \u003c so no word of the questions can close the tag
  return `<script type="application/ld+json">${JSON.stringify(graph).replace(/</g, "\\u003c")}</script>`;
}

/** The template (index.html as built) with one page's own tags. */
export function pageHtml(template, { title, description, canonical, index, jsonld = "" }) {
  const swap = (re, to) => {
    if (!re.test(template)) throw new Error(`index.html has no ${re}`);
    template = template.replace(re, () => to);
  };
  swap(/<title>[^<]*<\/title>/, `<title>${text(title)}</title>`);
  swap(/<meta name="description" content="[^"]*">/, `<meta name="description" content="${attr(description)}">`);
  swap(/<meta name="robots" content="[^"]*">/, `<meta name="robots" content="${index ? "index, follow" : "noindex, follow"}">`);
  swap(/<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="${attr(canonical)}">`);
  swap(/<meta property="og:title" content="[^"]*">/, `<meta property="og:title" content="${attr(title)}">`);
  swap(/<meta property="og:description" content="[^"]*">/, `<meta property="og:description" content="${attr(description)}">`);
  swap(/<meta property="og:url" content="[^"]*">/, `<meta property="og:url" content="${attr(canonical)}">`);
  swap(/<meta name="twitter:title" content="[^"]*">/, `<meta name="twitter:title" content="${attr(title)}">`);
  swap(/<meta name="twitter:description" content="[^"]*">/, `<meta name="twitter:description" content="${attr(description)}">`);
  swap(/<!--jsonld-->/, jsonld);
  return template;
}

/** Every file to write, as [path under dist, html]. The home page replaces index.html itself. */
export function pageFiles(template) {
  const files = PAGES.map((p) => [p.path === "/" ? "index.html" : `${p.path.slice(1)}/index.html`,
    pageHtml(template, { title: p.title, description: p.description, canonical: absolute(p.canonical ?? p.path), index: p.index,
      jsonld: p.path === "/" ? homeJsonLd() : "" })]);
  files.push(["404.html", pageHtml(template, { title: "Page not found · StratLab", description: NOT_FOUND_DESCRIPTION, canonical: `${SITE}/`, index: false })]);
  return files;
}

export function seoPages() {
  let out = "dist";
  return {
    name: "stratlab-seo-pages",
    apply: "build",
    configResolved(c) { out = join(c.root, c.build.outDir); },
    closeBundle() {
      const template = readFileSync(join(out, "index.html"), "utf8");
      for (const [file, html] of pageFiles(template)) {
        mkdirSync(dirname(join(out, file)), { recursive: true });
        writeFileSync(join(out, file), html);
      }
    },
  };
}
