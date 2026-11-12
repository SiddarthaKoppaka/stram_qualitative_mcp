# Changelog

## Unreleased

- Move the image's Debian snapshot to 2026-11-12: the 2026-11-05 security index had expired, so the
  image no longer built.

- Add `qual_get_news_feed` (`qual:read`): news about 1 to 50 tickers that arrived after a cursor,
  oldest first, for callers that poll. Pin `stram_data` 1.9.0 at `9929740`, which adds the Data
  Interface's `get_news_feed`; the image still needs only `libpq5`, which it already installs.
  Existing tool contracts and schema hashes are unchanged.

- Bound the audit writes an unauthenticated caller can cause. HTTP denials before dispatch (bad token,
  Host or Origin) are recorded one by one for the first 20 in each 60 seconds; the rest are counted and
  written as one `transport_denials_sampled` record with the count in `row_count`. Each record is a
  synchronous hash-chained write, so a flood of bad tokens could stall the server and grow the journal.

- Add an optional `view` (`raw` default, `clean`) to `qual_search_news`, `qual_get_filings` and
  `qual_get_article`. The clean view is lossless: cards as one table holding every field, a count of
  kept ticker links under `min_confidence`, article furniture lines flagged by position without
  rewriting the text, and a plain `explanation` for empty results. Raw output is unchanged; these
  three tools' schema hashes change.

- M7: serve the tools with FastMCP 4.1.6, ported from the Quant MCP. **Client-visible changes:**
  denials are `access_denied` with the message "Access denied."; every error carries
  `_meta["io.stram/error"]` with `code` and `retryable`; `tools/list` shows only the tools a token's
  scopes allow; a caller denied five times in 60 seconds is throttled; request bodies over 1 MiB get
  413. The five tool contracts and schema hashes are unchanged. The hand-wired server is on the
  `old-mcp-archive` branch. Add an online audit `backup` command, the readability lint rules and
  import layers, the image tag `m7` with an `IMAGE` override for rollbacks, and an index check in
  `tools/check_docs.py`. The documentation is reorganized into tutorials, how-to guides, reference and
  explanation.
- M6 preparation: `setup_host.sh` takes a mode. `demo` keeps the loopback demonstration, and `staging`
  uses the shared Keycloak realm, its own audience and a tailnet HTTPS port, after checking from a
  container that the issuer is trusted. Add `deploy/staging.env.example` and `tools/m6_check.py`.
  The script's arguments change: `demo` now comes before the JWKS file.
- M4: `qual_search_news` returns one row per story by default, with `story_id` and `copies`, and the
  timeline gains `stories`. Pin `stram_data` 1.7.0. The worker limit rises to 4 GB, with half for
  DuckDB and 4 threads, which fixes `unavailable` on repeated calls in a long-running worker.
- Rewrite the documentation for first-time readers. Add `tools/dev_server.py`, `tools/try_client.py`
  and `deploy/build_image.sh`, and remove the unused Docker unit and runtime example.
- M3: replace the placeholder with real `qual_describe_coverage`, add `qual_get_news_timeline`, and pin
  `stram_data` 1.6.0.
- M2: add `qual_get_article` and `qual_get_filings`, and pin `stram_data` 1.5.0. Fixtures move to
  `tests/fixtures/news`, and the container mounts the News directory at `/news`, because text sits
  beside Parquet.
- M1: add `qual_search_news`, a synthetic news fixture lake and a `content_trust` envelope field.
  `STRAM_QUAL_MCP_PARQUET_ROOT` now points at the News Parquet root.
- M0: copied from `stram_quant_mcp` at `d191333` and renamed. Quant's ten tools are replaced by one
  placeholder, and the service pins `stram_data` 1.4.1. The worker memory limit defaults to 3 GB.
