# StratLab in your AI assistant

[← Back to what StratLab does](FEATURES.md)

StratLab runs a remote [MCP](https://modelcontextprotocol.io) server, so Claude, ChatGPT and other AI assistants can
read your own StratLab data and, if you allow it, place **paper** orders in your own paper sessions. It's on the Pro
plan.

- **Read-only tools:** your watchlist, a holdings summary, one company's reported facts, the Stage 2 + Supertrend scan
  of your watchlist, your stock alerts, and your paper sessions with their P&L.
- **Paper tools (only on keys you allow):** open a position, or close the open one, in one of your own running
  single-instrument paper sessions, at the latest price with the session's slippage and charges. Simulated only.
- **No real orders.** Nothing the assistant can reach places, changes or cancels an order with a broker.
- **Facts only.** Tools return facts and arithmetic, never advice, ratings or targets.

## 1. Make a key

In StratLab, open **Account → AI assistant**, name the assistant (one key per assistant, so you can revoke one without
the others) and choose whether it may place paper orders. Copy the key (`slm_…`) straight away: StratLab keeps only a
fingerprint of it and can't show it again. **Revoke** stops a key at once.

The server address is shown on the same card: `https://<StratLab API>/mcp`.

## 2. Connect your assistant

**Claude Code**

```
claude mcp add --transport http stratlab https://<StratLab API>/mcp \
  --header "Authorization: Bearer slm_YOUR_KEY"
```

**Claude Desktop** (Settings → Developer → Edit Config; needs Node.js), then restart Claude:

```json
{
  "mcpServers": {
    "stratlab": {
      "command": "npx",
      "args": ["mcp-remote", "https://<StratLab API>/mcp", "--header", "Authorization:${STRATLAB_AUTH}"],
      "env": { "STRATLAB_AUTH": "Bearer slm_YOUR_KEY" }
    }
  }
}
```

**ChatGPT, through the OpenAI API** (Responses API, a remote MCP tool):

```
tools=[{
  "type": "mcp",
  "server_label": "stratlab",
  "server_url": "https://<StratLab API>/mcp",
  "headers": {"Authorization": "Bearer slm_YOUR_KEY"},
  "require_approval": "always"
}]
```

The Claude and ChatGPT apps' own connector screens sign in with OAuth, which StratLab doesn't offer yet; use one of
the ways above. Any client that can send a header to a Streamable HTTP MCP server works the same way.

## Limits and the log

Each key can make 30 tool calls a minute and 1,000 a day, with at most 20 paper orders and 6 scans an hour. A request
can be at most 64 KB, and long answers are shortened (they say so). Every tool call, with its arguments and result, is
listed under **What your assistants did** on the same card.

## For developers

The protocol is Streamable HTTP per the MCP specification revision 2026-07-28 (stateless: `server/discover`,
`tools/list`, `tools/call`, with `_meta` and the `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` headers checked
against the body). Clients on 2025-11-25 or 2025-06-18 use the `initialize` handshake and are served without a session.
Replies are single JSON objects; `GET` and `DELETE` on `/mcp` answer 405. The code is in
[`mcp_server.py`](../stratlab/backend/app/mcp_server.py) and [`mcp_keys.py`](../stratlab/backend/app/mcp_keys.py).
