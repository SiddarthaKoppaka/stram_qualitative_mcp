# Stram Qualitative MCP: plan

Status on 2026-11-04: M0 to M5 and M7 are done. The service runs on FastMCP in private staging on the
tailnet, with Keycloak logins. M6 is in progress: its technical checks and a rollback drill pass, and
the firewall, boot persistence, alerts, release provenance and licensing remain.

This service gives agents read-only access to Stram's News & Intelligence data over MCP. It follows
[`stram_quant_mcp`](https://github.com/SiddarthaKoppaka/stram_quant_mcp) and keeps its security model.
It differs only where text behaves differently from numbers.

## 1. Vision and MVP

**Full vision.** An agent can research a company or theme across news, filings and social sources.
It can search by meaning, read sources with citations, follow how a story spread, track sentiment over
time, and line all of that up with Stram's quantitative data. Point-in-time reads make the same
research usable for backtests.

**MVP.** An agent can find what was reported about the 80 tracked companies, read the text we hold,
look up SEC filings, and see attention and tone over time. The MVP's first users are the two
stream owners and an agent working with them.

| Capability | MVP | After MVP |
|---|---|---|
| Company and keyword search | Yes | Ranking, phrases and entities |
| Read article and filing text | Yes | |
| SEC filings by form | Yes | |
| Daily volume and GDELT tone | Yes | |
| One result per story | Yes (exact title matches) | Reworded copies, using embeddings |
| Semantic search | | Phase 2: embeddings, TurboVec |
| Company-level sentiment | | Phase 2: FinBERT or JEV |
| Backtesting | Ingestion-time `as_of` only | Labelled publication-time mode |
| Social and investor-relations sources | | When collected |

Nothing in the MVP should block these later additions. Each one is a new tool or an additive field.

## 2. Architecture

```mermaid
flowchart LR
    C[MCP client] -->|HTTPS + bearer JWT| T[Streamable HTTP]
    T --> A[JWT authentication]
    A --> P[tenant, scope, rate and bounds]
    P --> J[(HMAC-chained audit)]
    P --> W[isolated query worker]
    W --> I[stram_data.data_interface]
    I --> D[DuckDB]
    D --> L[(read-only News lake)]
    W -. no token, socket APIs blocked .-> I
```

The service is a thin Tool Plane. It owns transport, identity, authorization, bounds, worker isolation,
audit and telemetry. It owns no SQL, ingestion, ranking or scoring. All data comes through the public
`stram_data.data_interface`, as ADR 002 requires.

**The worker has no network, so it cannot reach PostgreSQL.** Anything the MCP needs must therefore be
in Parquet or the text files, through the Data Interface. PostgreSQL would be a faster route to story
groups, but it would break both the isolation and ADR 002.

### Copied from `stram_quant_mcp`

We copy the code at commit `d191333` and rename it. A shared library can wait until both services are
deployed, because Quant's staging work is still changing `audit.py` and its deployment.

| Reused unchanged apart from naming | Rewritten |
|---|---|
| `auth`, `audit`, `policy`, `errors`, `telemetry`, `server`, `worker`, `entrypoint`, `settings`, `tools/`, `ENGINEERING.md`, security tests, CI gates | `tool_registry`, `tool_adapter`, `tool_models`, fixtures, `docs/TOOLS.md`, `contracts/` |

Naming: package `stram_qualitative_mcp`, tools `qual_*`, scopes `qual:*`, settings `STRAM_QUAL_MCP_*`.

### What differs from Quant

| Area | Quant | Qualitative | Why |
|---|---|---|---|
| Result rows | 100 default, 500 max | 20 default, 100 max | News rows use far more of a model's context |
| Worker memory | 1 GB | 4 GB address space, 2 GB for DuckDB | Calls failed at 3 GB in a long-running worker |
| Lake mount | `data-lake/parquet` | `data-lake/news/parquet` and `bodies` | Text lives beside Parquet; the raw archive is not exposed |
| Content trust | Numbers | Untrusted third-party text | See section 4 |
| Permissions | Discover, read, lineage, analytics | Discover, read, text, analytics | Full text gets its own scope |

## 3. Tools

All tools are read-only, idempotent and closed-world, with closed input and output schemas. Each has
one clear job. There is no generic query, URL-fetch or file tool. The envelope matches Quant's, with
`warnings` always present.

| Tool | Purpose | Scope | Deadline |
|---|---|---|---|
| `qual_describe_coverage` | Sources, date ranges, counts, freshness, tracked tickers, known gaps | `qual:discover` | 10 s |
| `qual_search_news` | Result cards by ticker, text, provider and date | `qual:read` | 10 s |
| `qual_get_filings` | SEC filings by ticker, form and date | `qual:read` | 10 s |
| `qual_get_article` | One article with bounded text and its versions | `qual:text` | 10 s |
| `qual_get_news_timeline` | Daily article and story counts, with average GDELT tone | `qual:analytics` | 15 s |

### `qual_search_news`

- Requires `start_date`, `end_date`, and at least one of `tickers`, `text` or `providers`.
- Filters: up to 10 `tickers`, `min_confidence` (default 0.6), `providers`, `text` (2 to 100 characters),
  `include_flagged` (default false), `collapse_stories` (default true), `as_of`.
- Date range: up to 1,830 days with `tickers`, up to 92 days without. Wider requests are rejected, never
  clamped. A full year without a ticker took 12 to 16 seconds and 4.7 GB on the live lake.
- Returns cards: `article_id`, `story_id`, `copies`, `provider`, `publisher`, `published_at`,
  `first_ingested_at`, `title`, `summary`, `url`, `tickers` with method and confidence, `text_available`,
  `version_count`, `quality_flags`. There is no cursor; `truncated=true` means narrow the request.

### `qual_get_filings`

- Requires `start_date`, `end_date` and 1 to 10 `tickers`. Optional `forms`, such as `8-K`, up to 10.
- Returns accession number, CIK, form, items, filed time, title, summary and URL.
- Filing metadata is stored in `metadata_json`, so the form and items are available from Parquet.

### `qual_get_article`

- Requires `article_id`. Optional `offset` (default 0) and `max_chars` (default 4,000, max 8,000), which
  covers the typical article: the sample median was 4,288 characters and the 90th percentile 8,551.
- Returns the card, `text_available`, the `untrusted_text` slice, `total_chars`, and `has_more`.
- When we hold no text it returns the metadata and `text_available=false`. This is a normal result.

### `qual_get_news_timeline`

- Requires 1 to 5 `tickers`, `start_date` and `end_date`, with a span up to 366 days.
- Returns per ticker and UTC day: articles and mean tone, with the number of articles behind that
  mean. M4 adds stories. Days without articles are absent rather than zero.
- Tone is GDELT's score for a whole article. It is labelled `gdelt_article_tone`, and is not sentiment
  about the company.

### `qual_describe_coverage`

- Takes no input.
- Returns, per provider: date range, record count and latest ingestion, plus tracked tickers, the text
  coverage figures, and fixed limitations.
- Lists missing 15-minute GDELT files in the last 30 days, so a gap is not mistaken for a quiet period.

## 4. Handling text

**All third-party strings are untrusted.** An article can contain instructions aimed at the model
reading it, and filtering cannot reliably catch that. So:

- Titles, summaries, publishers, URLs and article text are returned only as data fields, never in tool
  descriptions, errors or warnings.
- `text` sits in a field named for what it is, `untrusted_text`, and the envelope carries
  `content_trust: "untrusted_external"`.
- Control and zero-width characters are removed from `untrusted_text`. This reduces hidden text and does
  not make the text safe.
- Client guidance in `docs/reference/tools.md` tells consumers to treat it as data. The MCP cannot enforce that.
- `qual:text` is a separate scope, so a client can search without ever receiving article bodies.
- The service never fetches `url`. The body fetcher honours `robots.txt` and paywalls; a consumer would
  not.

**Text belongs to its publishers.** The MVP is internal. Check licensing before anyone else gets
`qual:text`. SEC filings are public records; news articles are not.

**This repository is public.** Test fixtures must be synthetic. Real article text, hosts, addresses and
credentials must never be committed.

## 5. Being honest about the data

These facts come from the live data on 2026-11-01. Tool output must not suggest otherwise.

| Fact | Rule |
|---|---|
| GDELT is 97% of records, with titles and no summaries | Show its title and source; do not imply it was read |
| Full text exists for about 66,000 articles, and Finnhub is still growing | `text_available` on every card |
| Parquet says `pending` for 5.19M items that will not be fetched | Report `text_available=false`; do not expose `pending` |
| 2.57M of 5.81M ticker links are below 0.6 confidence | Default `min_confidence` to 0.6 and show the match method |
| Confidence is a rule-based label | Never present it as a probability |
| Some spam passes the `content_farm` flag | State this in coverage; a filter is pipeline work |
| Exact-title grouping misses reworded copies | Call it `copies`; do not claim it counts independent reports |
| `as_of` uses ingestion, and history arrived from about Oct 30, 2026 | Warn when `as_of` precedes that date |
| `published_at` is the provider's time | Label it as such |
| 55 GDELT files are missing since Oct 31 | Report gaps in coverage |

## 6. Required `stram_data` work

M2's, M3's and M4's additions shipped in `stram_data` 1.5.0, 1.6.0 and 1.7.0. Every item left adds to the Data Interface and needs a new contract baseline. These go in `stram_data`
pull requests, and the Data Interface needs Sid's review.

| Item | Change | Needed by |
|---|---|---|

**SEC text.** All 3,936 SEC announcements say `fetched`, but none has a `body_path`. They hold a
500-character summary, and the full document is only in the raw archive, which this plan does not
expose. M2 returns the summary with `text_available=false`. Writing that text to `bodies/` is a later
pipeline job.

**Stories.** `article_stories` is only in PostgreSQL. M4 reproduces the `news_data.story_id` rule in
`NewsLake` and tests it against PostgreSQL on a sample, so nothing has to be rewritten in the lake.

## 7. Deployment

Quant MCP runs in private staging on the tailnet, with Keycloak, since 2026-11-02. Its rollback and
recovery checks are still pending.

**MVP (M5).** Runs on the data host on a loopback port, on the real lake. It uses the
integration-test identity setup and is reached through an SSH tunnel. This is a working demonstration,
not staging.

**Staging (M6).** Follows Quant's setup: the same Keycloak realm and tenant, with its own audience
and `qual:*` client scopes. The audience is the service's own URL, on its own tailnet HTTPS port
through Tailscale Serve, so it shares nothing with Quant's routes. `setup_host.sh` has a `staging`
mode, and `tools/m6_check.py` checks it from a laptop.

Both need an administrator on the data host, because the lake is readable only by its owner:

- A non-login service user, separate from Quant's.
- A read-only bind mount of the News `parquet` and `bodies` directories.
- An audit volume and key, separate from Quant's.
- Rootless Podman, as Quant uses.

`stram_data` is private and this repository is public, so hosted CI cannot install the dependency
without a credential. Follow Quant's approach: the pinned commit locally and a vendored wheel for the
image. Do not enable a self-hosted runner on a public repository.

## 8. Milestones

Implement one reviewed milestone at a time and record evidence here.

| # | Deliver | Done when |
|---|---|---|
| M0 | Copy and rename, with Quant's tools removed | Security tests and all gates pass with zero tools or one stub |
| M1 | `qual_search_news`, with synthetic fixtures | Passes end to end through the official MCP client on 1.4.1 |
| M2 | Text and filings (`stram_data` 1.5) | `qual_get_article` and `qual_get_filings` pass; injection and text-bound tests pass |
| M3 | Coverage and timeline | All five tools pass; schemas and hashes checked in |
| M4 | Story collapsing | Story IDs match PostgreSQL on a sample |
| M5 | Real lake on the data host, loopback only | Budgets in section 9 met on the live lake; pipelines unaffected |
| M6 | Staging with Keycloak | Quant's M6 acceptance checks pass for this service |
| M7 | FastMCP server, following the Quant MCP | The ported behavior suite passes; staging checks pass on the new image; rollback to the previous image works |

M6 remains.

**M7 evidence (2026-11-04).** The Quant MCP's FastMCP server and behavior suite were ported, with the
five tool contracts and schema hashes unchanged; 215 tests pass with 90% branch coverage, and CI is
green on `main` at `04f6677`. The hand-wired server is on the `old-mcp-archive` branch. Image
`m7` (`704e592d0d06`, FastMCP 4.1.6, `stram_data` 1.7.0) passed the worker probe and preflight on the
real lake, read-only. Deployed in staging at 02:14 UTC: `m6_check.py` passed all 25 checks from a
laptop, with each client listing only its own tools (4, 2 and 1) and denials returning `Access denied.`,
not retryable. `m6_evidence.sh` passed all 17 host checks; the audit journal carried on from 137 to 160
records under the same key, last hash
`206bb2a47af3f5b78910c025e625754cdecb4d4cce3e01c45da981b6a54be05c`. Five denied calls throttled the
discovery-only client, which then saw no tools and was refused coverage; 62 s later it worked again.

Rollback drill, 02:21 to 02:23 UTC: `setup_host.sh` with `IMAGE=...:m5` and the kept archive brought
back the hand-wired server, which answered ready, listed all five tools to the smoke client and refused
with its old message. Running it again with `m7` restored the FastMCP release, and `m6_check.py` passed
all 25 checks. The lake and journal were untouched throughout.

**M6 progress (2026-11-02).** The Quant owner created the `qual:*` scopes and three clients in the
staging realm: `stram-qual-smoke` (discover, read, analytics), `stram-qual-text` (discover, text) and
`stram-qual-discovery-only`. Their check confirmed the token claims, audience isolation, and that
`qual:text` is never in a default token. On the data host, a test container trusted the issuer's
certificate and matched its metadata and signing key (RS256). The service, run with staging settings
on the synthetic lake, published login details naming its own URL and the realm, and refused calls
without a valid token.

**M6 staging evidence (2026-11-03).** The service runs in `staging` mode, published on its own tailnet
HTTPS port through Tailscale Serve, with the Quant routes unchanged. From a laptop on the tailnet,
`m6_check.py` passed all 23 checks at 05:42 UTC: each client's token is for this service with exactly
its scopes; no token, a malformed token and a broken signature get 401; a wrong Host gets 421 and a
foreign Origin 403; all five tools are listed and authorized calls succeed; the smoke client cannot read
articles, the text client cannot search, and the discovery-only client can call only coverage.

An earlier run failed one check: every article read passed the 10 s deadline. It ran two lake-wide
scans over about 7,570 Parquet files, taking about 14 s; the memory and thread caps were not the cause.
Running compaction early brought the active set to 53 files and the article read under 1 s. The
repeated timeouts hit the worker's restart limit, and a plain `systemctl restart` then failed because
stopping the container stops the pod; [Operate the service](docs/how-to/operate-the-service.md) now restarts from the pod.

`m6_evidence.sh`, run on the host at 05:50 UTC, passed all 17 checks: the service user and the container
cannot write `parquet`, `bodies` or the container's root; the query worker shows `Seccomp: 2`, one filter
and `NoNewPrivs: 1`; a killed worker restarted and readiness returned in 3 s; the service stopped
cleanly; the journal verified, and a copy restored into a scratch volume matched it. External
checkpoint: 137 records, last sequence 137, last hash
`21a8e4ff4b1840be29bf948ef4b0d83225624503f7e4ce064b0edd15613d18d5`, key `af5fcd5462cd33a5`. Image
`65667b7857c9`. Eight simultaneous calls from the laptop gave seven results and one `overloaded`, and
readiness held. The deadline and the restart limit were exercised by the article timeouts above.

**Audit backups (2026-11-04).** Retention is 30 days, as for the Quant MCP. A daily root timer takes
an online backup, verifies the copy against the key and writes a checkpoint; the first run at 02:33 UTC
verified 186 records, last hash `6e1e4080c26862082c57fced2d0853e0cc7a586d1d81e032c6cdfde9732d7fd5`.
The latest backup, checkpoint and key are copied to the owner's laptop weekly.

Open, with owners needed: the host egress firewall, to plan with the Quant owner because the host is
shared; a reviewed image digest with provenance; boot persistence, which needs a reboot of the shared
host; alerts and dashboards; an off-host copy of the audit backup; and a licensing review before
anyone outside the team gets `qual:text`.

**M4 evidence (2026-11-02).** `qual_search_news` returns one row per story by default, on `stram_data`
1.7.0 (`e21f320`). Across 30 random days from 2021 to 2026, 35,107 of 35,110 story IDs match
`article_stories`, including 3,051 of 3,053 non-ASCII titles. In an earlier sample, the ASCII mismatches
came from different `published_at` values in the two stores. The worker limit rose after a soak test
found M5's timings hid a failure: DuckDB sized itself from the machine, so repeated calls returned
`unavailable` in a long-running worker at 3 GB, on 1.6.0 too. With 4 GB, 2 GB for DuckDB and 4 threads,
99 of 99 calls passed over seven minutes on the live lake with no restart, at low priority. Slowest
calls: ticker 1 month 2.8 s, ticker 1 year 5.7 s, 3 tickers 1 year 8.7 s, text 1 month 4.2 s, 92 days of
GDELT 9.2 s, timeline 3.8 s, coverage 2.2 s. The ticker and 3-ticker worst cases exceed section 9's
budgets of 2, 5 and 8 s, on a lake not yet compacted.

**Deployed M4 evidence (2026-11-02).** Through the official MCP client over HTTP on the deployed service,
70 of 72 calls passed over five and a half minutes, with no `unavailable` errors. The two failures were
a one-year ticker search and a three-ticker search hitting the 10 s deadline, with the slowest calls near
12.8 s. The cause is not known. Readiness held, and later rounds passed. Other worst cases: ticker
1 month 4.3 s, text 1 month 4.8 s, GDELT 92 days 8.9 s, timeline 4.7 s, filings 0.8 s, coverage 2.7 s.

**M5 evidence (2026-11-01).** The service runs on the data host on a loopback port, with a read-only view of
`parquet` and `bodies`. Through the official MCP client over HTTP on the live lake: coverage 2.7 s, ticker
1 month 1.9 s, ticker 1 year 4.1 s, 3 tickers 1 year 100 rows 5.1 s, text 1 month 2.9 s, filings 0.4 s, article
2.3 s, timeline 1.1 s. All are within section 9's budgets, and some are close. Requests without a valid
token get 401 and a wrong host gets 421. Pipelines stayed active. The demonstration signing key and
one-hour tokens are not staging.

**M3 evidence (2026-11-01).** On `stram_data` 1.6.0 (`947e49b`), all five tools pass through the official
MCP client on synthetic data. Through the isolated worker on the live lake, read-only: coverage 1.2 s,
AAPL October timeline 0.9 s, 5 tickers over a year 2.5 s. The AAPL October total matches search at
1,412 articles. Only 33 of them carry tone at confidence 0.6, because most GDELT links for AAPL sit
just under it, so `tone_articles` is returned with every mean.

**M2 evidence (2026-11-01).** On `stram_data` 1.5.0 (`ff8b151`), `qual_get_article` and
`qual_get_filings` pass through the official MCP client on synthetic data. Through the isolated worker
on the live lake, read-only: filings 0.2 s, article about 1.6 s. Paged text, missing text and SEC
summaries all behave as specified. Only `fetched` counts as text we hold.

**M0 evidence (2026-11-01).** Copied from `stram_quant_mcp` at `d191333`, pinned to `stram_data` 1.4.1
(`4e9fe24`). Tests ran on Linux, on the data host, from a throwaway copy using Python 3.13.

**M1 evidence (2026-11-01).** `qual_search_news` passes through the official MCP client against a
synthetic news lake. `collapse_stories` and `story_id` wait for M4, and `copies` with them.
Through the isolated worker at 3 GB on the live lake, read-only: ticker 1 month 1.1 s, ticker 1 year
2.6 s, 3 tickers 1 year 100 rows 3.9 s, text 1 month 2.4 s. All are within section 9's budgets.

## 9. Budgets

Measured on the live lake after compaction, on an 8-core host. M5 repeats these through the service.

| Query | Measured | Budget |
|---|---|---|
| Ticker, 1 month, 20 rows | 0.8 s | 2 s |
| Ticker, 1 year, 20 rows | 2.5 s | 5 s |
| 3 tickers, 1 year, 100 rows | 4.3 s | 8 s |
| Text, 1 month, 20 rows | 2.5 s | 5 s |

One query runs at a time, as in Quant. The worker's memory limit is 4 GB.

## 10. Risks

| Risk | Response |
|---|---|
| The file count grows and reads slow down again | Compaction is manual today; schedule it before M5 |
| Worker limits are hit on heavier filters | Requests are bounded by section 3; out-of-memory returns a safe error |
| Prompt injection through news text | Section 4 reduces it, but consumers must treat text as data |
| `get_news` is shared with the Quant-owned contract | Additive only, with Sid reviewing each change |
| Upstream security fixes land only in Quant | Compare `src/` against Quant at each milestone, until a shared library exists |
| Search is substring only | Good enough for the MVP; semantic search is the planned answer |
| Disk space on the data host | The MCP adds an audit file only; watch it during the Finnhub fetch |
