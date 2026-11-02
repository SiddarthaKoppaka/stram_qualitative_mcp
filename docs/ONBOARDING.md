# Onboarding

This takes you from nothing to a running service and all five tools answering, in about ten minutes.
It uses invented data and a throwaway login, so you need no server, secrets or real data.

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

Expected: `1.7.0`.

## 2. Start the service

```bash
uv run python tools/dev_server.py
```

Expected: it prints the endpoint and token path, then keeps running:

```text
MCP endpoint: http://127.0.0.1:8765/mcp
Token, valid for one hour: .../.local/token
```

This is the real server, with real login checks, audit and worker isolation. Only two things are
stand-ins. The data is the invented lake in `tests/fixtures/news/`, and instead of a login server the
script makes a temporary signing key, serves its public half on port 8766, and writes a one-hour
token. Everything it creates is in `.local/`, which Git ignores.

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

That confirms the whole path: client, login, permissions, worker, Data Interface and Parquet.

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

Then ask something like "What news do we have on AAPL in October 2026?" Remember that the data is
invented, and that the token lasts an hour. See [How to consume](HOWTO_CONSUME.md) for other clients.

## 5. Run the checks

These are the checks CI runs on every push to `main`:

```bash
uv run pytest --cov --cov-report=term-missing
uv run mypy
uv run ruff check .
uv run ruff format --check .
uv run python -m stram_qualitative_mcp.tools.export_schema --check
uv run python tools/check_docs.py
```

CI also runs the dependency, secret and license checks, then builds the image and tests it. It needs
the `STRAM_DATA_READ_TOKEN` Actions secret to read `stram_data`.

To change the test data, edit `tests/support/build_news_fixture.py` and rebuild it. Keep it invented,
because this repository is public:

```bash
uv run python tests/support/build_news_fixture.py
```

## Changing the code

**To add a tool:**

1. Add its input and output models to `tool_models.py`.
2. Add it to `TOOL_SPECS` in `tool_registry.py`, with one scope and a deadline.
3. Call the Data Interface from `tool_adapter.py`. Do not add SQL or news logic here.
4. Add tests, including rejected inputs in `tests/security/test_resource_budgets.py`.
5. Update the schema file and [the tool reference](TOOLS.md):

   ```bash
   uv run python -m stram_qualitative_mcp.tools.export_schema
   ```

**To move to a new `stram_data` release:** update the commit in `pyproject.toml`,
`.github/workflows/ci.yml` and `tools/prepare_container_dependency.sh`. Update the version in
`worker.py`, the `Dockerfile` and `tools/prepare_container_dependency.sh`. Then rename and refresh the
snapshot in `contracts/`, point `tests/contract/test_data_interface_release.py` at it, and run
`uv lock --upgrade-package stram-data`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv sync` fails on `stram_data` | No access to the private repository | Run the `git ls-remote` check above and ask for access. Never put a token in a URL or the lockfile |
| `Address already in use` | Another service has the port | `uv run python tools/dev_server.py --port 8775 --keys-port 8776`, then pass `--endpoint http://127.0.0.1:8775/mcp` to the client |
| Client gets 401 | The token expired, or the server restarted | Each start makes a new key. Restart if needed, then use the new `.local/token` |
| Client gets 421 | The URL's host differs from the allowed one | Use `127.0.0.1`, not `localhost` |
| Readiness stays `not_ready` | The worker or audit failed to start | Read the server's output. If the audit check failed, stop it and delete `.local/` |
| A tool returns `forbidden` | The token lacks that tool's scope | See [the tool reference](TOOLS.md). The local token has all four |
| Tests fail on Windows | Linux-only isolation tests | Use WSL |
| Connection refused | The server is not running | Start it, and wait for `{"status":"ready"}` |

## Next

- [How to consume](HOWTO_CONSUME.md) for using the tools well.
- [Architecture](ARCHITECTURE.md) for how a request is handled.
- [Deployment](../deploy/README.md) to run it on a server against real data.
