// EXPORT (4 Nov): one CSV builder for every table's download, and the theme's deck and CSV. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { columnOf, csvCell, csvName, plainNumber, shownValue, toCsv } from "../src/lib/csv.ts";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a cell: numbers stay numbers, text is quoted only when it must be, a formula is written as text", () => {
  assert.equal(csvCell(1234.5), "1234.5");
  assert.equal(csvCell(-0.75), "-0.75");
  assert.equal(csvCell(0.1 + 0.2), "0.3");                       // rounded to 12 significant digits
  assert.equal(csvCell(-0), "0");
  assert.equal(csvCell(NaN), "");
  assert.equal(csvCell(Infinity), "");
  assert.equal(csvCell(null), "");
  assert.equal(csvCell(undefined), "");
  assert.equal(csvCell(true), "yes");
  assert.equal(csvCell("Tata Steel"), "Tata Steel");
  assert.equal(csvCell("Larsen, Toubro"), '"Larsen, Toubro"');
  assert.equal(csvCell('The "big" one'), '"The ""big"" one"');
  assert.equal(csvCell("two\nlines"), '"two\nlines"');
  assert.equal(csvCell("=HYPERLINK(1)"), "'=HYPERLINK(1)");
  assert.equal(csvCell("+91 phone"), "'+91 phone");
  assert.equal(csvCell("@SUM(A1)"), "'@SUM(A1)");
  assert.equal(csvCell("−3.2 pts"), "'-3.2 pts");               // the real minus is written as "-", then guarded as text
  assert.equal(csvCell("=a,b"), `"'=a,b"`);
});

test("dates are ISO: a calendar day alone, a moment in UTC", () => {
  assert.equal(csvCell(new Date("2026-11-04")), "2026-11-04");
  assert.equal(csvCell(new Date("2026-11-04T09:15:30.250Z")), "2026-11-04T09:15:30Z");
  assert.equal(csvCell(new Date("not a date")), "");
});

test("the file: a byte-order mark, the header, CRLF rows", () => {
  const f = toCsv(["Company", "Market value (₹ crore)"], [["A, Ltd", 1500], ["B", null]]);
  assert.equal(f, '\uFEFFCompany,Market value (₹ crore)\r\n"A, Ltd",1500\r\nB,\r\n');
});

test("shown text read back: plain numbers become numbers, a dash is empty, money words stay text", () => {
  assert.equal(plainNumber("1,23,456.5"), 123456.5);
  assert.equal(plainNumber("1,234"), 1234);
  assert.equal(plainNumber("−3.2"), -3.2);
  assert.equal(plainNumber("+4.1"), 4.1);
  assert.equal(plainNumber("▲ 2.5"), 2.5);
  assert.equal(plainNumber("12a"), null);
  assert.equal(shownValue("–"), null);
  assert.equal(shownValue("  "), null);
  assert.equal(shownValue("42"), 42);
  assert.equal(shownValue("₹1.51 lakh cr"), "₹1.51 lakh cr");          // a unit word: kept as shown, never 1.51
  assert.equal(shownValue("12.4x"), "12.4x");
});

test("a column of percents or of rupees is a column of numbers with the unit in its name; a mixed one stays as shown", () => {
  assert.deepEqual(columnOf(["12.5%", "−3.0%", "–", "▲ 1.2%"]), { suffix: " (%)", values: [12.5, -3, null, 1.2] });
  assert.deepEqual(columnOf(["₹1,234", "₹56.50", ""]), { suffix: " (₹)", values: [1234, 56.5, null] });
  assert.deepEqual(columnOf(["$12.50", "−$3"]), { suffix: " ($)", values: [12.5, -3] });
  assert.deepEqual(columnOf(["₹925 cr", "₹1.51 lakh cr"]), { suffix: "", values: ["₹925 cr", "₹1.51 lakh cr"] });
  assert.deepEqual(columnOf(["12", "1,200", "–"]), { suffix: "", values: [12, 1200, null] });
  assert.deepEqual(columnOf(["–", "–"]), { suffix: "", values: [null, null] });
});

test("a file name: stratlab-, the words in lower case with hyphens, the day", () => {
  assert.equal(csvName("theme India defence IN companies", "2026-11-04"), "stratlab-theme-india-defence-in-companies-2026-11-04.csv");
  assert.equal(csvName("F&O: positioning / changes", "2026-11-04"), "stratlab-f-and-o-positioning-changes-2026-11-04.csv");
  assert.equal(csvName("Société Générale", ""), "stratlab-societe-generale.csv");
  assert.equal(csvName("!!!", "2026-11-04"), "stratlab-table-2026-11-04.csv");
});

test("every table download goes through the one builder and the one save (lib/share.ts download)", () => {
  const share = read("src/lib/share.ts");
  assert.match(share, /export function downloadCsv\(name: string, head: string\[\], rows: CsvValue\[\]\[\]\) \{\n  download\(new Blob\(\[toCsv\(head, rows\)\], \{ type: "text\/csv;charset=utf-8" \}\), name\);/);
  const table = read("src/components/kit/DataTable.tsx");
  assert.match(table, /downloadCsv\(csvName\(name, istToday\(\)\), t\.head, t\.rows\)/);
  assert.match(table, /data-csv=\{name\}/);
  // no page builds its own CSV text any more: each uses downloadCsv (or a server file saved through download)
  for (const f of ["src/pages/admin/InvoiceAdminPanel.tsx", "src/pages/admin/AuditPanel.tsx"]) {
    const s = read(f);
    assert.doesNotMatch(s, /lines\.join\("\\n"\)/, f);
    assert.match(s, /downloadCsv\(/, f);
  }
});

test("themes: Slides (PDF), Slides (PowerPoint) and the companies' CSV, the deck from the server's deck builder", () => {
  const d = read("src/components/ThemeDive.tsx");
  assert.match(d, /themeApi\.deck\(region, theme, format\)/);
  assert.match(d, /download\(await res\.blob\(\), `stratlab-theme-\$\{themeSlug\(theme\) \|\| "theme"\}-\$\{region\.toLowerCase\(\)\}\.\$\{format\}`\)/);
  assert.match(d, />\{making === "pdf" \? "Making the PDF…" : "Slides \(PDF\)"\}</);
  assert.match(d, />\{making === "pptx" \? "Making the deck…" : "Slides \(PowerPoint\)"\}</);
  assert.match(read("src/pages/ThemesPage.tsx"), /<ThemeDownloads r=\{r\} dive=\{dive\} region=\{region\} theme=\{q\} \/>/);
  assert.match(read("src/lib/theme.ts"), /deck: \(r: Region, theme: string, format: "pptx" \| "pdf"\) => api<Response>\(`\/research\/theme-dive\/deck\?/);
});
