# Documentation

This is the documentation for the Stram Qualitative MCP, the read-only service that gives AI agents
access to Stram's News & Intelligence data.

## Read this first

| You want to | Read |
|---|---|
| Run it on your machine | [Onboarding](ONBOARDING.md) |
| Connect an agent, or call the tools from code | [How to consume](HOWTO_CONSUME.md) |
| Look up inputs, outputs, permissions and errors | [Tool reference](TOOLS.md) |
| Understand the design and its boundaries | [Architecture](ARCHITECTURE.md) |
| Install it on a server from nothing | [Deployment](../deploy/README.md) |
| Check, restart, update or recover it | [Operations](OPERATIONS.md) |
| Know what is missing or unproven | [Gaps](GAPS.md) |
| Review an accepted security risk | [Security exceptions](SECURITY_EXCEPTIONS.md) |

Changing the code? Read [Engineering standards](../ENGINEERING.md) and [AGENTS.md](../AGENTS.md) first.
Milestones and evidence are in [PLANS.md](../PLANS.md), and releases are in the
[changelog](../CHANGELOG.md).

## Where things are

| Path | Contents |
|---|---|
| `src/stram_qualitative_mcp/` | The service |
| `tool_registry.py`, `tool_models.py`, `tool_adapter.py` | What each tool is, its schema, and how it calls the Data Interface |
| `auth.py`, `policy.py`, `audit.py` | Login, permissions and limits, tamper-evident audit |
| `worker.py` | The isolated process that reads data |
| `contracts/` | Frozen tool schemas and the Data Interface snapshot |
| `tests/` | Tests, with invented news data in `tests/fixtures/news/` |
| `tools/` | `dev_server.py`, `try_client.py` and CI checks |
| `deploy/` | Server install scripts and notes |

## The repositories

| Repository | Holds | How changes land |
|---|---|---|
| `stram_qualitative_mcp` (this one) | The MCP service | Direct to `main`, once all checks pass |
| `stram_data` (private) | Ingestion, the lake and the Data Interface | Pull request, reviewed by its owner |
| `stram_quant_mcp` | The Quant equivalent, which this was copied from | Not changed from here |

A new tool usually needs both of the first two. The data feature goes into `stram_data`, then this
repository pins the new release and adds the tool.
