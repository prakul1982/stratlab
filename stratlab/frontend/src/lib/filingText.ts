/** The filing's own words after its subject: a body that opens by printing the subject again ("Disclosure of creation of pledge by
 * promoter. Disclosure under Regulation 31 ...") keeps only what it adds (VR1-100). */
export function bodyAfter(subject: string, text: string): string {
  const norm = (x: string) => x.trim().replace(/\s+/g, " ");
  const sub = norm(subject).replace(/[.:;\s]+$/, ""), body = norm(text);
  if (!sub || !body.toLowerCase().startsWith(sub.toLowerCase())) return body;
  return body.slice(sub.length).replace(/^[.:;,\s-]+/, "");
}
