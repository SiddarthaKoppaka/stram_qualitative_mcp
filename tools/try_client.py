"""Call all five tools with the official MCP client and print a short summary.

    uv run python tools/try_client.py
    uv run python tools/try_client.py --endpoint URL --token-file PATH

The defaults match `tools/dev_server.py`. A failure exits non-zero, so it works as a smoke test.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).parents[1]
DATES = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


async def run(endpoint: str, token: str, ticker: str) -> None:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http,
        streamable_http_client(endpoint, http_client=http, terminate_on_close=False) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()

        async def call(tool: str, arguments: dict[str, object]) -> dict[str, Any]:
            result = await session.call_tool(tool, arguments)
            if result.is_error or result.structured_content is None:
                raise SystemExit(f"{tool} failed")
            data: dict[str, Any] = result.structured_content["data"]
            return data

        listed = await session.list_tools()
        print("tools:", ", ".join(sorted(tool.name for tool in listed.tools)))

        coverage = await call("qual_describe_coverage", {})
        sources = ", ".join(f"{row['provider']} {row['records']}" for row in coverage["providers"])
        print(f"coverage: {sources}; {len(coverage['tracked_tickers'])} tracked tickers")

        search = await call("qual_search_news", {**DATES, "tickers": [ticker]})
        print(f"search {ticker}: {search['count']} articles, truncated={search['truncated']}")

        filings = await call("qual_get_filings", {**DATES, "tickers": [ticker]})
        print(f"filings {ticker}: {filings['count']}")

        timeline = await call("qual_get_news_timeline", {**DATES, "tickers": [ticker]})
        print(f"timeline {ticker}: {timeline['count']} days")

        held = next((row for row in search["rows"] if row["text_available"]), None)
        if held is None:
            print("article: no result had stored text")
            return
        article = await call("qual_get_article", {"article_id": held["article_id"]})
        print(f"article: read {len(article['untrusted_text'])} of {article['total_chars']} chars")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--token-file", type=Path, default=ROOT / ".local/token")
    parser.add_argument("--ticker", default="AAPL")
    args = parser.parse_args()
    asyncio.run(run(args.endpoint, args.token_file.read_text().strip(), args.ticker))


if __name__ == "__main__":
    main()
