# Changelog

## Unreleased

- M1: add `qual_search_news`, a synthetic news fixture lake and a `content_trust` envelope field.
  `STRAM_QUAL_MCP_PARQUET_ROOT` now points at the News Parquet root.
- M0: copied from `stram_quant_mcp` at `d191333` and renamed. Quant's ten tools are replaced by one
  placeholder, and the service pins `stram_data` 1.4.1. The worker memory limit defaults to 3 GB.
