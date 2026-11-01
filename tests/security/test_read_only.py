from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from stram_qualitative_mcp.worker import QueryWorker

ROOT = Path(__file__).parents[2]
LAKE = ROOT / "tests/fixtures/lake"


def inventory() -> dict[str, str]:
    return {
        str(path.relative_to(LAKE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(LAKE.rglob("*"))
        if path.is_file()
    }


@pytest.mark.asyncio
async def test_every_tool_layer_read_leaves_the_lake_unchanged() -> None:
    before = inventory()
    worker = QueryWorker(LAKE)
    await worker.start()
    await worker.call(
        "qual_describe_coverage",
        {},
        "read-only",
        10.0,
    )
    await worker.close()
    assert inventory() == before
