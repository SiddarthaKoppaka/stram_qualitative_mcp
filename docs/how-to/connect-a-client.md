# How to connect a client

This guide connects an agent or your own code to the service. Inputs and outputs are in the
[tool reference](../reference/tools.md).

## 1. Get the endpoint and a token

| Where | Endpoint | Token |
|---|---|---|
| Your machine | `http://127.0.0.1:8765/mcp` | `.local/token` from `tools/dev_server.py`; see [Getting started](../tutorials/getting-started.md) |
| Staging | `https://HOST:8443/mcp`, from a machine on the tailnet | A Keycloak `client_credentials` token, below |
| Demo mode on the server | `http://127.0.0.1:8801/mcp`, through `ssh -N -L 8801:127.0.0.1:8801 "$SERVER"` | `deploy/issue_demo_token.py` on the host, valid for an hour |

For staging, ask the realm for a token with your client's ID and secret. Keep the secret in a file,
never in a command line or chat:

```bash
curl -s "https://$HOST/realms/stram-staging/protocol/openid-connect/token" \
  -d grant_type=client_credentials -d client_id=stram-qual-smoke \
  --data-urlencode "client_secret@$HOME/.stram-qual/stram-qual-smoke.secret" \
  -d scope="qual:discover qual:read qual:analytics"
```

The reply's `access_token` lasts five minutes. Ask for `qual:text` explicitly if your client is allowed
it; no default token holds it.

## 2. Connect

The transport is MCP Streamable HTTP, and the token goes in `Authorization: Bearer <token>`.

**Claude Code:**

```bash
claude mcp add --transport http stram-qual http://127.0.0.1:8765/mcp \
  --header "Authorization: Bearer $TOKEN"
```

**Other MCP clients** need the URL and that header. Choose the HTTP or Streamable HTTP transport.

**Python,** with the official SDK:

```python
import asyncio
import os

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def search(endpoint: str) -> dict[str, object]:
    token = os.environ["STRAM_QUAL_MCP_TOKEN"]
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http,
        streamable_http_client(endpoint, http_client=http, terminate_on_close=False) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "qual_search_news",
            {"tickers": ["AAPL"], "start_date": "2026-10-01", "end_date": "2026-10-31"},
        )
        if result.is_error or result.structured_content is None:
            raise RuntimeError("search failed")
        return result.structured_content


print(asyncio.run(search("http://127.0.0.1:8765/mcp")))
```

[`tools/try_client.py`](../../tools/try_client.py) calls all five tools, and
[`tools/m6_check.py`](../../tools/m6_check.py) shows the staging login end to end.

## 3. Check what you can call

`tools/list` returns only the tools your token's scopes allow. If a tool you expect is missing, your
token lacks its scope; see [the tool reference](../reference/tools.md).

## 4. Handle errors

A failed call has `isError=true`, a fixed message and `_meta["io.stram/error"]` with its `code` and
`retryable`. Retry only when `retryable` is true, after a pause or with a narrower request. Never retry
`access_denied`: a caller denied five times in a minute is blocked for a while. See
[Errors](../reference/tools.md#errors).

To use the tools well, see [Answer common questions](answer-common-questions.md) and
[About the data](../explanation/about-the-data.md).
