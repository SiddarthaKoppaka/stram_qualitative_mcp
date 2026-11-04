# Configuration

The service reads its settings once, at startup, from the environment. A missing required value or
an invalid one stops startup. The model is `AppSettings` in
[`settings.py`](../../src/stram_qualitative_mcp/settings.py).

## Required

| Variable | Meaning |
|---|---|
| `STRAM_QUAL_MCP_PARQUET_ROOT` | The News Parquet root; `bodies/` must sit beside it |
| `STRAM_QUAL_MCP_AUDIT_DB` | The audit journal's SQLite file |
| `STRAM_QUAL_MCP_AUDIT_KEY_FILE` | A file holding the audit HMAC key, at least 32 bytes |
| `STRAM_QUAL_MCP_ISSUER_URL` | The exact token issuer, such as the Keycloak realm URL |
| `STRAM_QUAL_MCP_RESOURCE_URL` | This service's URL, ending in `/mcp`; tokens must name it as their audience |
| `STRAM_QUAL_MCP_JWKS_URL` | Where the issuer publishes its signing keys |
| `STRAM_QUAL_MCP_TENANT_ID` | The only tenant whose tokens are accepted |
| `STRAM_QUAL_MCP_ALLOWED_HOSTS` | Comma-separated `Host` values, such as the resource URL's host and port |

## Optional

| Variable | Default | Meaning |
|---|---|---|
| `STRAM_QUAL_MCP_ALLOWED_ORIGINS` | None | Comma-separated browser origins; requests from any other `Origin` get 403 |
| `STRAM_QUAL_MCP_ALLOWED_ALGORITHMS` | `RS256` | The one signing algorithm accepted |
| `STRAM_QUAL_MCP_ALLOW_INSECURE_HTTP` | Off | `1` allows plain HTTP, only for loopback URLs, as in demo mode |
| `STRAM_QUAL_MCP_IMAGE_DIGEST` | `development` | Recorded in every audit record |
| `STRAM_QUAL_MCP_OTLP_ENDPOINT` | None | Where to send traces and metrics; HTTPS unless loopback in demo mode |
| `STRAM_QUAL_MCP_WORKER_MAX_RESTARTS` | 3 | Worker failures in a row before readiness stays false |
| `STRAM_QUAL_MCP_WORKER_RESTART_BACKOFF_SECONDS` | 0.25 | Pause before restarting the worker |
| `STRAM_QUAL_MCP_WORKER_SHUTDOWN_SECONDS` | 5 | How long shutdown waits for the worker |
| `STRAM_QUAL_MCP_DENIAL_LIMIT` | 5 | Denials that throttle a caller |
| `STRAM_QUAL_MCP_DENIAL_WINDOW_SECONDS` | 60 | The window those denials are counted in |
| `STRAM_QUAL_MCP_BIND_HOST` | `127.0.0.1` | `127.0.0.1`, or `0.0.0.0` inside a container |
| `STRAM_QUAL_MCP_BIND_PORT` | 8000 | The listening port |

## Fixed in code

| Setting | Value |
|---|---|
| Tenant claim | `tenant_id` |
| Queue | One query runs; two more may wait up to 2 s |
| Request body | 1 MiB |
| Response | 4 MiB |
| Worker memory | 4 GB, half of it for DuckDB, with 4 DuckDB threads |
| Rate limit | 30 calls a minute per caller |

## Deployment settings

`setup_host.sh` writes the service's settings from one of two sources. In demo mode it uses a local
issuer and signing key. In staging mode it reads a file shaped like
[staging.env.example](../../deploy/staging.env.example):

| Variable | Meaning |
|---|---|
| `STRAM_QUAL_PUBLIC_HOST` | The host's tailnet name |
| `STRAM_QUAL_PUBLIC_PORT` | The HTTPS port Tailscale Serve publishes, 8443 |
| `STRAM_QUAL_HOST_IPV4` | The host's Tailscale address, so the container reaches the issuer |
| `STRAM_QUAL_ISSUER_URL` | The Keycloak realm URL |
| `STRAM_QUAL_TENANT_ID` | The tenant, `local-stram` |

The script sets `IMAGE` to `localhost/stram-qualitative-mcp:m7` unless you pass another tag.
