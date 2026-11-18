from __future__ import annotations

from datetime import UTC, datetime

import pytest
from stram_data.data_interface import DataInterface

from stram_qualitative_mcp.errors import ToolInputError, ToolUnavailableError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import SectionsData
from tests.conftest import SYNTHETIC_LAKE
from tests.support.build_sections_fixture import ANNUAL, QUARTERLY

CLOCK = datetime(2026, 10, 30, tzinfo=UTC)


@pytest.fixture
def adapter() -> QualToolAdapter:
    return QualToolAdapter(
        DataInterface(SYNTHETIC_LAKE, news_parquet_root=SYNTHETIC_LAKE, clock=lambda: CLOCK)
    )


def _sections(
    adapter: QualToolAdapter, **arguments: object
) -> tuple[SectionsData, tuple[str, ...]]:
    envelope = adapter.execute(
        "qual_get_filing_sections", {"tickers": ["AAPL"], **arguments}, "sec"
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, SectionsData)
    return data, envelope.warnings  # type: ignore[attr-defined]


def test_rows_say_what_each_item_is_and_whether_to_trust_it(adapter: QualToolAdapter) -> None:
    data, warnings = _sections(adapter, forms=["10-K"])

    assert [row.item for row in data.rows] == ["1", "1A", "7", "8", "10", "7A"]
    flags = {row.item: row.quality_flags for row in data.rows}
    assert flags["8"] == ("numbers_in_financial_facts",)
    assert flags["10"] == ("incorporated_by_reference",)
    assert flags["7A"] == ("not_found",)
    assert all(row.untrusted_text is None and row.has_more is False for row in data.rows)
    assert data.not_collected == () and warnings == ()


def test_a_long_item_is_read_in_slices_until_has_more_is_false(adapter: QualToolAdapter) -> None:
    pieces: list[str] = []
    offset, warnings = 0, ()
    while True:
        data, warnings = _sections(
            adapter,
            accessions=[ANNUAL],
            items=["1A"],
            include_text=True,
            offset=offset,
            max_chars=4000,
        )
        (row,) = data.rows
        assert row.untrusted_text is not None and row.offset == offset
        pieces.append(row.untrusted_text)
        if not row.has_more:
            break
        assert any("larger offset" in warning for warning in warnings)
        offset += len(row.untrusted_text)

    assert len(pieces) > 1 and len("".join(pieces)) == row.char_count


def test_filings_can_be_asked_for_by_accession_alone(adapter: QualToolAdapter) -> None:
    data = adapter.execute("qual_get_filing_sections", {"accessions": [QUARTERLY]}, "acc").data  # type: ignore[attr-defined]

    assert {(row.part, row.item) for row in data.rows} == {("I", "2"), ("II", "1A")}


def test_a_ticker_that_was_never_collected_says_so(adapter: QualToolAdapter) -> None:
    data, warnings = _sections(adapter, tickers=["AAPL", "ZZZZ"])

    assert data.not_collected == ("ZZZZ",) and data.count > 0
    assert any("ZZZZ" in warning for warning in warnings)


def test_a_limit_that_cuts_the_list_is_a_warning(adapter: QualToolAdapter) -> None:
    data, warnings = _sections(adapter, limit=2)

    assert (data.count, data.truncated) == (2, True)
    assert any("truncated" in warning for warning in warnings)


@pytest.mark.parametrize(
    "arguments",
    [
        {"tickers": []},
        {"tickers": ["AAPL"], "start_date": "2026-01-01"},
        {"tickers": ["AAPL"], "items": ["risk"]},
        {"tickers": ["AAPL"], "accessions": ["123"]},
        {"tickers": ["AAPL"], "items": ["1A", "1A"]},
        {"tickers": ["AAPL"], "include_text": True, "limit": 11},
        {"tickers": ["AAPL"], "start_date": "2026-05-01", "end_date": "2026-01-01"},
        {"tickers": ["AAPL"], "max_chars": 9000},
        {"tickers": ["AAPL"], "unknown": 1},
    ],
)
def test_bad_requests_are_refused(adapter: QualToolAdapter, arguments: dict[str, object]) -> None:
    with pytest.raises(ToolInputError):
        adapter.execute("qual_get_filing_sections", arguments, "bad")


def test_a_lake_without_the_dataset_is_unavailable_not_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "parquet").mkdir()
    empty = QualToolAdapter(
        DataInterface(
            tmp_path / "parquet", news_parquet_root=tmp_path / "news", clock=lambda: CLOCK
        )
    )

    with pytest.raises(ToolUnavailableError):
        empty.execute("qual_get_filing_sections", {"tickers": ["AAPL"]}, "none")
