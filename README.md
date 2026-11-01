# Stram Qualitative MCP

Stram Qualitative MCP lets AI agents read Stram's News & Intelligence data over the
[Model Context Protocol](https://modelcontextprotocol.io). An agent can search news about the tracked
companies, list SEC filings, read the article text we hold, and see attention and tone over time.

The service is read-only. It owns transport, login, permissions, limits, worker isolation, audit and
telemetry. All data comes through the public `stram_data.data_interface`. It holds no SQL, ingestion,
ranking or scoring. It follows [`stram_quant_mcp`](https://github.com/SiddarthaKoppaka/stram_quant_mcp)
and keeps that service's security model.

**Status:** all five tools work on the live data, as a private demonstration reached through an SSH
tunnel. It uses a test login, so it is not ready to share. See [what is not done yet](docs/GAPS.md).

## Tools

| Tool | What it does | Permission |
|---|---|---|
| `qual_describe_coverage` | Sources, date ranges, tracked tickers, known gaps | `qual:discover` |
| `qual_search_news` | Find articles by ticker, keyword, source and date | `qual:read` |
| `qual_get_filings` | List SEC filings by ticker, form and date | `qual:read` |
| `qual_get_article` | Read one article's text in pages | `qual:text` |
| `qual_get_news_timeline` | Daily article counts and GDELT tone per ticker | `qual:analytics` |

## Quick start

You need Linux or WSL, Python 3.12 or later, [`uv`](https://docs.astral.sh/uv/), and read access to the
private `stram_data` repository. No real data or login server is needed: this uses a small invented
news lake and a throwaway identity.

```bash
git clone https://github.com/SiddarthaKoppaka/stram_qualitative_mcp.git
cd stram_qualitative_mcp
uv sync --frozen --dev
uv run python tools/dev_server.py
```

Leave that running. In a second terminal:

```bash
uv run python tools/try_client.py
```

You should see all five tools listed, then a line of results from each. The
[onboarding guide](docs/ONBOARDING.md) explains each step and what to do if one fails.

## Documentation

Start with [docs/README.md](docs/README.md), which says what to read for each job.

| Need | Document |
|---|---|
| Run it for the first time | [Onboarding](docs/ONBOARDING.md) |
| Connect an agent and use the tools well | [How to consume](docs/HOWTO_CONSUME.md) |
| Look up a tool's inputs and outputs | [Tool reference](docs/TOOLS.md) |
| Understand how it works | [Architecture](docs/ARCHITECTURE.md) |
| Install it on a server | [Deployment](deploy/README.md) |
| Keep it running | [Operations](docs/OPERATIONS.md) |
| See what is missing | [Gaps](docs/GAPS.md) |
| See the plan and evidence | [Plans](PLANS.md) |
| Follow the engineering rules | [Engineering standards](ENGINEERING.md) |
