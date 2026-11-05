/* Save a table as a CSV file (lib/csv.ts writes it), through the one save (lib/share.ts download) (EXPORT). In a file of its own so
 * the share helper, which the landing page loads, doesn't bring the CSV writer with it (R5V-020's budget). */
import { toCsv, type CsvValue } from "./csv";
import { download } from "./share";

export function downloadCsv(name: string, head: string[], rows: CsvValue[][]) {
  download(new Blob([toCsv(head, rows)], { type: "text/csv;charset=utf-8" }), name);
}
