# Stram Qualitative MCP: agent guidance

This repository is the independently deployed MCP Tool Plane for Stram qualitative data.

- Read [PLANS.md](PLANS.md) before changing architecture or scope and follow the normative
  [engineering standards](ENGINEERING.md) for every change.
- Treat `stram_data.data_interface` as the only data API. Do not import internal
  `stram_data` modules or duplicate SQL, ingestion, ranking, or availability logic.
- Changes to `stram_data` go through pull requests in that repository, never from here.
- Keep every exposed tool read-only, typed, bounded, authenticated, authorized, audited, and tested.
- Use a pinned `stram-data` release and a read-only lake mount. Never log tokens, secrets, raw tool
  payloads, filesystem paths, or unrestricted result data.
- Implement only one reviewed milestone at a time. Run its listed verification commands and record
  evidence and remaining risks in `PLANS.md`.
- Do not deploy, access credentials, or change production services without separate authorization.
- This repository is public. Fixtures must be synthetic; never commit article text, hosts,
  addresses or credentials.

Knowledge-transfer references are in `../stram_data/docs/README.md`, especially ADR 002 and
`docs/quant/DATA_INTERFACE.md`.

Start repository work from [README.md](README.md). Architecture, onboarding, tool contracts and
operations live under [docs/](docs/ARCHITECTURE.md); deployment prerequisites are in
[deploy/README.md](deploy/README.md). Do not copy those details into this file.
