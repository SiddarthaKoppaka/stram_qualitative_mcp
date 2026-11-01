from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydantic import BaseModel

from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_registry import TOOL_SPECS, exported_definitions

ROOT = Path(__file__).parents[2]


def test_checked_in_tool_definitions_are_current_and_closed() -> None:
    checked_in = json.loads((ROOT / "contracts/tool_schemas.json").read_text())
    assert checked_in == exported_definitions()
    for tool in checked_in["tools"]:
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["annotations"] == {
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "readOnlyHint": True,
        }
        assert len(tool["schemaHash"]) == 64


def test_every_real_result_round_trips_through_its_output_contract(
    tool_adapter: QualToolAdapter,
) -> None:
    examples: dict[str, dict[str, object]] = {
        "qual_describe_coverage": {},
        "qual_search_news": {
            "tickers": ["AAPL"],
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
        },
        "qual_get_filings": {
            "tickers": ["AAPL"],
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
        },
        "qual_get_news_timeline": {
            "tickers": ["AAPL"],
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
        },
        "qual_get_article": {"article_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "held-text"))},
    }

    for spec in TOOL_SPECS:
        result = tool_adapter.execute(spec.name, examples[spec.name], spec.name)
        serialized = result.model_dump(mode="json")
        validated: BaseModel = spec.output_model.model_validate(serialized)
        assert validated.model_dump(mode="json") == serialized
