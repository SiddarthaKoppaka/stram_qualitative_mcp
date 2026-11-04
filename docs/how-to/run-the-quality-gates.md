# How to run the quality gates

These are the checks CI runs on every push to `main`. Run them before you push. You need the
environment from [Getting started](../tutorials/getting-started.md).

```bash
uv run pytest --cov --cov-report=term-missing
uv run mypy
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
uv run python -m stram_qualitative_mcp.tools.export_schema --check
uv run python tools/check_docs.py
```

Each must pass:

| Gate | Passes when |
|---|---|
| `pytest` | Every test passes and branch coverage is at least 85% |
| `mypy` | Strict typing finds no issues |
| `ruff check` | No lint findings outside the legacy baseline in `pyproject.toml` |
| `ruff format --check` | Every file is already formatted |
| `lint-imports` | Modules import only from the layers beneath them |
| `export_schema --check` | The tool schemas match `contracts/tool_schemas.json` |
| `check_docs.py` | Links, anchors, commands and examples work, every page is in the index, and nothing looks like a secret |

CI also runs the dependency, secret and license checks, then builds the image and scans it. It needs
the `STRAM_DATA_READ_TOKEN` Actions secret to read `stram_data`.

## When a gate fails

- **`ruff format`**: run `uv run ruff format .` and commit the result.
- **A new lint finding** in code you wrote: fix it. Do not add it to the baseline, which may only
  shrink; see [Engineering standards](../../ENGINEERING.md#33-baseline-and-ratchet).
- **`lint-imports`**: move the import or the code so that it points down the layers in
  [Import boundaries](../../ENGINEERING.md#32-import-boundaries).
- **`export_schema --check`**: a tool contract changed. If the change is intended, follow
  [Add a tool](add-a-tool.md) step 5 and record why in the changelog.
- **Test data**: edit `tests/support/build_news_fixture.py` and rebuild it. Keep it invented, because
  this repository is public:

  ```bash
  uv run python tests/support/build_news_fixture.py
  ```
