# How to add a tool

This guide adds one read-only tool. A tool only translates between MCP and the public
`stram_data.data_interface`; if the data it needs is not there yet, add it to `stram_data` first and
[upgrade](upgrade-stram-data.md).

1. **Models.** Add the tool's input and output models to `tool_models.py`. Inputs are closed
   (`extra="forbid"`) and every value has a bound.
2. **Catalogue.** Add a `ToolSpec` to `TOOL_SPECS` in `tool_registry.py`, with its description, models,
   one scope and a deadline. A new scope also needs a Keycloak client scope in the staging realm.
3. **Adapter.** Call the Data Interface from `tool_adapter.py`. Do not add SQL or news logic here.

   You do not write any FastMCP code: `fastmcp_tools.py` turns every spec into a tool, and access
   control, audit, error shaping and telemetry already apply to it.
4. **Tests.** Add success and rejection tests, including rejected inputs in
   `tests/security/test_resource_budgets.py`, and a call through the official client.
5. **Schemas.** Regenerate the reviewed schemas and their hashes, then check them in:

   ```bash
   uv run python -m stram_qualitative_mcp.tools.export_schema
   ```

6. **Documentation.** Add the tool to [the tool reference](../reference/tools.md), the table in
   `README.md`, and the changelog.

Run the [quality gates](run-the-quality-gates.md) before pushing.
