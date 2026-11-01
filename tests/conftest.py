from __future__ import annotations

from pathlib import Path

import pytest
from stram_data.data_interface import DataInterface

from stram_qualitative_mcp.tool_adapter import QualToolAdapter

ROOT = Path(__file__).parent.parent
SYNTHETIC_LAKE = ROOT / "tests/fixtures/news/parquet"


@pytest.fixture
def data_interface() -> DataInterface:
    return DataInterface(SYNTHETIC_LAKE, news_parquet_root=SYNTHETIC_LAKE)


@pytest.fixture
def tool_adapter(data_interface: DataInterface) -> QualToolAdapter:
    return QualToolAdapter(data_interface)
