/** The address an AI assistant connects to: the StratLab server this page itself talks to (config.js's API_BASE), plus
 * /mcp. A relative API_BASE ("/api" or "") is read against this site's own address. The server's own idea of its
 * address is only the fallback: it said http://localhost:8000 wherever its PUBLIC_API_URL wasn't set. */
export function mcpEndpoint(apiBase: string | undefined, origin: string, fallback?: string): string {
  const base = (apiBase ?? "").trim();
  try {
    if (base || origin) {
      const url = new URL(base || "/", origin);
      if (url.protocol === "http:" || url.protocol === "https:") return `${url.origin}${url.pathname.replace(/\/+$/, "")}/mcp`;
    }
  } catch { /* not an address: use the server's */ }
  return fallback ?? "/mcp";
}
