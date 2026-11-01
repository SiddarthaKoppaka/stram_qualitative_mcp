# Changelog

## Unreleased

- M3: replace the placeholder with real `qual_describe_coverage`, add `qual_get_news_timeline`, and pin
  `stram_data` 1.6.0.
- M2: add `qual_get_article` and `qual_get_filings`, and pin `stram_data` 1.5.0. Fixtures move to
  `tests/fixtures/news`, and the container mounts the News directory at `/news`, because text sits
  beside Parquet.
- M1: add `qual_search_news`, a synthetic news fixture lake and a `content_trust` envelope field.
  `STRAM_QUAL_MCP_PARQUET_ROOT` now points at the News Parquet root.
- M0: copied from `stram_quant_mcp` at `d191333` and renamed. Quant's ten tools are replaced by one
  placeholder, and the service pins `stram_data` 1.4.1. The worker memory limit defaults to 3 GB.
