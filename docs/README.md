# Documentation

The documentation for the Stram Qualitative MCP, the read-only service that gives AI agents access to
Stram's News & Intelligence data. These pages follow the [Diátaxis](https://diataxis.fr/) framework:
each page has one purpose, so find what you need by asking what you are trying to do.

| If you want to... | Read | Type |
|---|---|---|
| Learn by doing, starting from nothing | [Getting started](tutorials/getting-started.md) | Tutorial |
| Accomplish a specific task | the [how-to guides](#how-to-guides) | How-to |
| Look up a fact, schema, setting or command | the [reference](#reference) | Reference |
| Understand why the service is built this way | the [explanations](#explanation) | Explanation |

## Tutorials

- [Getting started](tutorials/getting-started.md): run the service on your machine and make your first
  authenticated tool calls.

## How-to guides

- [Connect a client](how-to/connect-a-client.md)
- [Answer common questions with the tools](how-to/answer-common-questions.md)
- [Run the quality gates](how-to/run-the-quality-gates.md)
- [Add a tool](how-to/add-a-tool.md)
- [Move to a new `stram_data` release](how-to/upgrade-stram-data.md)
- [Deploy the service](how-to/deploy-the-service.md)
- [Check staging](how-to/check-staging.md)
- [Operate the service](how-to/operate-the-service.md): health, restarts, updates, rollback, audit and
  incidents.

## Reference

- [Tools](reference/tools.md): contracts, scopes and errors for all five tools.
- [Configuration](reference/configuration.md): every setting.
- [Deployment](reference/deployment.md): what the deployment scripts create.
- [Staging checklist](reference/staging-checklist.md): M6 conditions and their status.
- [Security exceptions](reference/security-exceptions.md): reviewed, time-bounded exceptions.

## Explanation

- [About the architecture](explanation/architecture.md): boundaries, request lifecycle, failure
  handling.
- [About the data](explanation/about-the-data.md): why results are untrusted, and what they can and
  cannot tell you.
- [About the FastMCP migration](explanation/about-the-fastmcp-migration.md): why the server framework
  changed.

## Project records

These are neither learning nor reference material.

- [Plans](../PLANS.md): milestones, evidence and open decisions.
- [Known gaps](GAPS.md): what is missing or unproven.
- [Engineering standards](../ENGINEERING.md): the rules every change follows.
- [Changelog](../CHANGELOG.md) and [agent guidance](../AGENTS.md).

## Where things are

| Path | Contents |
|---|---|
| `src/stram_qualitative_mcp/` | The service |
| `tool_registry.py`, `tool_models.py`, `tool_adapter.py` | What each tool is, its schema, and how it calls the Data Interface |
| `fastmcp_server.py`, `fastmcp_tools.py` | Assembly of the FastMCP server, and the tools built from the catalogue |
| `fastmcp_auth.py`, `access_policy.py`, `fastmcp_middleware.py` | Token checks, who may call what, and the middleware that enforces it |
| `policy.py`, `audit.py`, `worker.py` | Limits and dispatch, tamper-evident audit, the isolated process that reads data |
| `contracts/` | Frozen tool schemas and the Data Interface snapshot |
| `tests/` | Tests, with invented news data in `tests/fixtures/news/`; `tests/parity/` is the behavior suite |
| `tools/` | `dev_server.py`, `try_client.py`, `m6_check.py` and CI checks |
| `deploy/` | Server scripts |

## Writing documentation

Follow the documentation rules in [Engineering standards](../ENGINEERING.md#11-change-review-and-documentation-discipline).
Keep one purpose per page, link instead of repeating, and make every command copy-pasteable.
`tools/check_docs.py` fails if a page is missing from this index.

## The repositories

| Repository | Holds | How changes land |
|---|---|---|
| `stram_qualitative_mcp` (this one) | The MCP service | Direct to `main`, once all checks pass |
| `stram_data` (private) | Ingestion, the lake and the Data Interface | Pull request, reviewed by its owner |
| `stram_quant_mcp` | The Quant equivalent, which this follows | Not changed from here |
