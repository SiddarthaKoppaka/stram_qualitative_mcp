# Getting started

In this tutorial you run the service on your own machine and make your first authenticated tool calls.
It takes about ten minutes. It uses invented data and a throwaway login, so you need no server, secrets
or real data.

## What you need

- **Linux, or WSL on Windows.** The worker's network isolation and memory limit only work on Linux.
- **Python 3.12, 3.13 or 3.14.**
- **[`uv`](https://docs.astral.sh/uv/)**, which installs everything else.
- **Git**, with read access to the private `stram_data` repository. Ask the repository owner if you
  do not have it.

Check your access before going further. This should print a commit, not an error:

```bash
git ls-remote https://github.com/SiddarthaKoppaka/stram_data.git HEAD
```

## 1. Install

```bash
git clone https://github.com/SiddarthaKoppaka/stram_qualitative_mcp.git
cd stram_qualitative_mcp
uv sync --frozen --dev
```

`--frozen` installs exactly what `uv.lock` pins, including the exact `stram_data` commit. Confirm it:

```bash
uv run python -c 'import stram_data; print(stram_data.__version__)'
```

Expected: `1.9.0`.

## 2. Start the service

```bash
uv run python tools/dev_server.py
```

Expected: it prints the endpoint and token path, then keeps running:

```text
MCP endpoint: http://127.0.0.1:8765/mcp
Token, valid for one hour: .../.local/token
```

This is the real FastMCP server, with real login checks, audit and worker isolation. Only two things
are stand-ins. The data is the invented lake in `tests/fixtures/news/`, and instead of a login server
the script makes a temporary signing key, serves its public half on port 8766, and writes a one-hour
token holding all four scopes. Everything it creates is in `.local/`, which Git ignores.

Leave it running. To get a new token, stop it with Ctrl+C and start it again.

## 3. Call the tools

In a second terminal, from the same folder:

```bash
curl -s http://127.0.0.1:8765/health/ready
uv run python tools/try_client.py
```

Expected:

```text
{"status":"ready"}
tools: qual_describe_coverage, qual_get_article, qual_get_filings, qual_get_news_timeline, qual_search_news
coverage: finnhub 7, gdelt 1, sec 2; 80 tracked tickers
search AAPL: 3 stories, truncated=False
filings AAPL: 1
timeline AAPL: 3 days
article: read 4000 of 9120 chars
```

You have now used the whole path: client, login, permissions, worker, Data Interface and Parquet.

Requests without a valid token are refused. This should print `401`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8765/mcp
```

## 4. Connect an agent

With the server still running, add it to Claude Code:

```bash
claude mcp add --transport http stram-qual http://127.0.0.1:8765/mcp \
  --header "Authorization: Bearer $(cat .local/token)"
```

Then ask something like "What news do we have on AAPL in October 2026?" The data is invented, and the
token lasts an hour.

## If a step fails

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv sync` fails on `stram_data` | No access to the private repository | Run the `git ls-remote` check above and ask for access. Never put a token in a URL or the lockfile |
| `Address already in use` | Another service has the port | `uv run python tools/dev_server.py --port 8775 --keys-port 8776`, then pass `--endpoint http://127.0.0.1:8775/mcp` to the client |
| Client gets 401 | The token expired, or the server restarted | Each start makes a new key. Restart if needed, then use the new `.local/token` |
| Client gets 421 | The URL's host differs from the allowed one | Use `127.0.0.1`, not `localhost` |
| Readiness stays `not_ready` | The worker or audit failed to start | Read the server's output. If the audit check failed, stop it and delete `.local/` |
| Tests fail on Windows | Linux-only isolation tests | Use WSL |
| Connection refused | The server is not running | Start it, and wait for `{"status":"ready"}` |

## Next

- [Connect a client](../how-to/connect-a-client.md) to use the tools from code or another agent.
- [About the architecture](../explanation/architecture.md) to see how a request is handled.
- [Run the quality gates](../how-to/run-the-quality-gates.md) before changing the code.
