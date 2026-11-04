# About the FastMCP migration

This page explains why the server framework changed, what changed and what deliberately did not. It
records a decision; it is not a procedure.

**Status:** the FastMCP server is the only implementation. The hand-wired server it replaced is kept
on the `old-mcp-archive` branch, and its last image (`m5`) is the rollback target.

## Why change

This service was copied from the Quant MCP before that service moved to FastMCP. Both were built
directly on the lowest layer of the official MCP Python SDK, with a hand-written tool catalogue, JWT
verifier, transport and authorization. That gave full control, but every contributor had to learn all
of it before adding one tool.

The Quant MCP moved to [FastMCP](https://gofastmcp.com/) on 2026-11-03, with a behavior suite proving
the switch. FastMCP is built on the same SDK and provides tool registration, JWT verification, per-tool
checks and middleware. Following it keeps the two services on one stack, so a fix or a reviewer's
knowledge carries across, as agreed when this service reused the Quant work.

## What changed

| Concern | Before | After |
|---|---|---|
| Declaring a tool | Registry entry plus hand-wired dispatch | Each `ToolSpec` becomes a FastMCP tool automatically |
| Verifying the token | Custom `JWTTokenVerifier` | FastMCP's Keycloak provider with `StrictVerifier`, which adds the checks the stock one lacks |
| Per-tool access | Scope check at dispatch | A default-deny store consulted for every call and every listing, plus the dispatch check |
| `tools/list` | Every tool, to every caller | Only the tools the caller may call |
| Denials | `forbidden`, "The caller is not authorized to invoke this tool." | `access_denied`, "Access denied." |
| Errors | Fixed message | Fixed message plus a `retryable` flag; denials are never retryable |
| Repeated denials | Not limited | Five in 60 seconds throttles the caller |
| Request size | Checked by the SDK | A body limit before the framework reads anything |
| Audit backup | Export the volume while stopped | Also an online backup command, verified independently |

The code was ported from the Quant MCP's modules with names changed, and its behavior suite was
ported with it, mapped onto the five qualitative tools.

## What did not change

These exist because of this service's security and data promises, not because of the framework:

- the isolated query worker with its seccomp filter, deadlines and response budgets;
- the HMAC-chained audit journal, with one terminal record per call;
- the exact issuer, audience, tenant and expiry checks, and readiness waiting for the signing keys;
- Host and Origin allowlists, and the redaction rules for logs and telemetry;
- the five tool contracts: names, closed input and output schemas, scopes and schema hashes.

## Risks

- FastMCP releases often and has changed behavior between patch versions. One exact version is pinned,
  and an upgrade is an isolated change that runs the full contract and security suites.
- It adds transitive dependencies, which must pass the license and vulnerability gates.
- The throttle counts unknown tool names as denials, and does not cover transport-level 401s. A
  client that guesses tool names can throttle itself.

The rules new code follows are in [Engineering standards](../../ENGINEERING.md#34-framework-rules).
