# Tool reference

`src/stram_qualitative_mcp/tool_registry.py` defines the tools. Schemas and reviewed SHA-256 hashes
are in `contracts/tool_schemas.json`; MCP `tools/list` returns the same schemas and read-only
annotations.

The planned tools are in [PLANS.md](../PLANS.md). Only the placeholder below exists today.

## Common contract

All inputs are closed: unknown properties are rejected. Every tool is read-only, idempotent and
closed-world. Successful calls return structured content with this envelope:

```json
{
  "tool_version": "0.1.0",
  "stram_data_version": "1.4.1",
  "interface_version": "1",
  "policy_version": "availability-policy-hash",
  "request_id": "server-generated-id",
  "data": {},
  "warnings": []
}
```

Every call needs a valid JWT and the listed exact scope. Authorization is enforced before worker
dispatch. MCP errors contain a safe message and `isError=true`; they do not expose paths, SQL,
dependency details or stack traces.

## `qual_describe_coverage`

| Scope | Deadline | Input |
|---|---|---|
| `qual:discover` | 10 s | None |

A placeholder that proves the path from client to worker to Data Interface. It returns the
availability policies in `data.policies`. M3 replaces its output with per-source coverage.
