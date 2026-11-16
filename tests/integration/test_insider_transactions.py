from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from stram_data.data_interface import DataInterface

from stram_qualitative_mcp.errors import ToolInputError, ToolUnavailableError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import InsiderTransactionsData
from tests.conftest import SYNTHETIC_LAKE

CLOCK = datetime(2026, 10, 30, tzinfo=UTC)
OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@pytest.fixture
def adapter() -> QualToolAdapter:
    return QualToolAdapter(
        DataInterface(SYNTHETIC_LAKE, news_parquet_root=SYNTHETIC_LAKE, clock=lambda: CLOCK)
    )


def _insiders(
    adapter: QualToolAdapter, **arguments: object
) -> tuple[InsiderTransactionsData, tuple[str, ...]]:
    envelope = adapter.execute(
        "qual_get_insider_transactions", {"tickers": ["AAPL"], **OCTOBER, **arguments}, "ins"
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, InsiderTransactionsData)
    return data, envelope.warnings  # type: ignore[attr-defined]


def test_buys_and_sales_are_kept_apart_from_grants_and_tax_withholding(
    adapter: QualToolAdapter,
) -> None:
    data, warnings = _insiders(adapter)

    # Newest filing date first; two filings on one day come in accession order.
    assert [(r.accession[-3:], r.code, r.category) for r in data.rows[:2]] == [
        ("105", "F", "tax_withholding"),
        ("106", "M", "option_exercise"),
    ]
    assert {r.category for r in data.rows} == {
        "open_market_sale",
        "open_market_purchase",
        "grant_or_award",
        "tax_withholding",
        "option_exercise",
    }
    assert warnings == () and not data.truncated and data.count == 6


def test_the_summary_splits_sale_value_by_the_filings_own_plan_box(
    adapter: QualToolAdapter,
) -> None:
    (apple,) = _insiders(adapter)[0].summary

    assert apple.covered is True
    assert (apple.open_market_purchases, apple.open_market_purchase_value) == (1, Decimal("58650"))
    assert (apple.open_market_sales, apple.open_market_sale_value) == (2, Decimal("300500"))
    assert apple.sale_value_under_plan == Decimal("200000")
    assert apple.sale_value_not_under_plan == Decimal("0")
    assert apple.sale_value_plan_unknown == Decimal("100500")  # no plan box is not "not a plan"
    assert (apple.distinct_buyers, apple.distinct_sellers) == (1, 2)


def test_every_row_links_to_its_sec_source_and_hides_the_internal_path(
    adapter: QualToolAdapter,
) -> None:
    data, _ = _insiders(adapter, categories=["open_market_sale"])

    assert [r.accession for r in data.rows] == ["0000000001-26-000102", "0000000001-26-000101"]
    assert data.rows[0].source_url == (
        "https://www.sec.gov/Archives/edgar/data/1/000000000126000102/doc4.xml"
    )
    assert "raw_path" not in data.rows[0].model_dump()


def test_footnote_text_is_left_out_unless_asked_for_but_always_counted(
    adapter: QualToolAdapter,
) -> None:
    plain, _ = _insiders(adapter, plan_10b5_1=True)
    asked, _ = _insiders(adapter, plan_10b5_1=True, include_footnotes=True)

    assert [(r.footnotes, r.footnote_count) for r in plain.rows] == [((), 1)]
    assert asked.rows[0].footnotes == ("Synthetic footnote: sold under a synthetic trading plan.",)


def test_a_truncated_answer_says_so_and_the_summary_still_covers_the_whole_range(
    adapter: QualToolAdapter,
) -> None:
    data, warnings = _insiders(adapter, limit=1)

    assert data.truncated and data.count == 1
    assert data.summary[0].open_market_sales == 2  # not cut by the row limit
    assert any("summary already covers the whole range" in w for w in warnings)


def test_a_company_that_is_not_tracked_says_zero_means_not_collected(
    adapter: QualToolAdapter,
) -> None:
    (zzzz,) = _insiders(adapter, tickers=["ZZZZ"])[0].summary

    assert zzzz.covered is False and zzzz.open_market_sales == 0


@pytest.mark.parametrize(
    "arguments",
    [
        {"tickers": ["AAPL", "AAPL"]},
        {"tickers": []},
        {"tickers": [f"T{i}" for i in range(11)]},
        {"categories": ["buy_everything"]},
        {"categories": ["gift", "gift"]},
        {"start_date": "2026-11-01"},  # after the end
        {"start_date": "2020-01-01"},  # beyond the five-year limit
        {"limit": 101},
        {"include_footnotes": "yes please"},
        {"sql": "select 1"},
    ],
)
def test_inputs_are_closed_and_bounded(
    adapter: QualToolAdapter, arguments: dict[str, object]
) -> None:
    with pytest.raises(ToolInputError):
        _insiders(adapter, **arguments)


def test_a_dataset_that_was_never_built_is_unavailable_not_empty(tmp_path: Path) -> None:
    (tmp_path / "parquet").mkdir()
    adapter = QualToolAdapter(
        DataInterface(tmp_path / "parquet", news_parquet_root=tmp_path, clock=lambda: CLOCK)
    )

    with pytest.raises(ToolUnavailableError):
        _insiders(adapter)
