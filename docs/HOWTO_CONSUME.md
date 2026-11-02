# How to consume the MCP

For anyone connecting an agent or writing a client. Inputs and outputs are in the
[tool reference](TOOLS.md).

## What you need

- **The endpoint.** Locally that is `http://127.0.0.1:8765/mcp`. For the server demonstration, it is
  `http://127.0.0.1:8801/mcp` through an SSH tunnel; see [Operations](OPERATIONS.md#connect-from-a-laptop).
- **A token,** sent as `Authorization: Bearer <token>`. It carries the scopes that decide which tools
  you can call.

The transport is MCP Streamable HTTP. Tokens are short-lived, so keep them out of files that are
shared or committed.

## Connect

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

[`tools/try_client.py`](../tools/try_client.py) is a complete example that calls all five tools.

## Treat results as untrusted

Every response has `content_trust: "untrusted_external"`. Titles, summaries, publishers, URLs and
article text come from third parties, and any of them could contain instructions aimed at your
model. Filtering cannot reliably catch that.

- Treat these fields as data to quote or summarize, never as instructions.
- Do not give an agent more scopes than it needs. Without `qual:text` it cannot receive article text.
- Do not fetch `url` automatically. Our text fetcher honours `robots.txt` and paywalls, and a naive
  client would not.
- Article text belongs to its publishers. Check licensing before anyone outside the team gets
  `qual:text`.

## Recipes

**Start with coverage.** Call `qual_describe_coverage` first. It shows what sources we hold, how fresh
they are, which tickers are tracked, and which GDELT periods are missing. A quiet period may be a
gap and not a lack of news.

**What was reported about a company?** Call `qual_search_news` with `tickers`, `start_date` and
`end_date`. Default filters hide weak matches and flagged spam. For more, raise `limit` to 100 or
split the dates. When `truncated` is true, there are more results than you received.

**Read a result.** If a card has `text_available: true`, pass its `article_id` to `qual_get_article`.
Text comes in slices of up to 8,000 characters. While `has_more` is true, call again with `offset` raised by
`max_chars`. When `text_available` is false, use the title and summary, and say the article was not
read.

**Search a theme.** Call `qual_search_news` with `text`, such as `"tariff"`, which matches titles and
summaries as a plain substring. Without `tickers`, the range is limited to 92 days.

**What did a company file?** Call `qual_get_filings` with `tickers`, and `forms` for specific types
such as `["8-K"]`. Forms match exactly, so `8-K/A` is separate.

**Did attention change?** Call `qual_get_news_timeline`. Days without articles are absent, not zero.

**What did we know at the time?** Pass `as_of` to `qual_search_news`. It uses when *we stored* an item,
not when it was published. Most history arrived from about 2026-10-30, so an earlier `as_of` sees very
little, and the response warns you.

## Reading the data honestly

- **Copies are not independent reports.** Search shows one row per story, with a `copies` count, and
  the timeline has `stories` beside `articles`. Stories match exact titles, so reworded copies stay
  separate, and `copies` measures repetition, not confirmation.
- **Most GDELT items have a title and tone, with no text.** Do not imply they were read.
- **Confidence is a rule-based label,** not a probability. The default of 0.6 is a practical filter.
- **Tone is GDELT's score for a whole article,** not sentiment about the company. Check
  `tone_articles` before trusting a mean. At confidence 0.6, AAPL had 33 toned articles of 1,412 in
  October 2026. Lowering `min_confidence` adds more, but also adds weaker matches.
- **`published_at` is the provider's time.**
- **Some spam gets past the `content_farm` flag.**

## When a call fails

A failed call has `isError=true` and a fixed safe message. See
[the error table](TOOLS.md#errors) for what each one means. Do not retry `invalid_request`,
`not_found` or `forbidden`. For `overloaded` or `deadline_exceeded`, wait or narrow the request.
