from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from stram_data.data_interface import DataInterface

import stram_qualitative_mcp.tool_adapter as tool_adapter
from stram_qualitative_mcp.errors import ToolInputError, ToolUnavailableError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import ShortInterestData
from tests.conftest import SYNTHETIC_LAKE
from tests.support.build_short_interest_fixture import HIDDEN_NAME

CLOCK = datetime(2026, 11, 18, tzinfo=UTC)
RANGE = {"start_date": "2026-09-01", "end_date": "2026-10-31"}


@pytest.fixture
def adapter() -> QualToolAdapter:
    return QualToolAdapter(
        DataInterface(SYNTHETIC_LAKE, news_parquet_root=SYNTHETIC_LAKE, clock=lambda: CLOCK)
    )


def _short_interest(
    adapter: QualToolAdapter, **arguments: object
) -> tuple[ShortInterestData, tuple[str, ...]]:
    envelope = adapter.execute(
        "qual_get_short_interest", {"tickers": ["AAPL"], **RANGE, **arguments}, "short"
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, ShortInterestData)
    return data, envelope.warnings  # type: ignore[attr-defined]


def test_rows_carry_the_figures_newest_settlement_first(adapter: QualToolAdapter) -> None:
    data, warnings = _short_interest(adapter)

    assert [row.settlement_date for row in data.rows] == [
        date(2026, 10, 30),
        date(2026, 10, 15),
        date(2026, 9, 30),
        date(2026, 9, 15),
    ]
    newest, split, _, oldest = data.rows
    assert newest.ticker == "AAPL"
    assert (newest.short_position, newest.previous_short_position) == (660_000, 600_000)
    assert (newest.change_percent, newest.average_daily_volume) == (10.0, 500_000)
    assert (newest.days_to_cover, newest.published_estimated) == (1.32, date(2026, 11, 7))
    assert newest.revision_flag and not newest.split_flag
    assert split.split_flag and not split.revision_flag
    assert oldest.previous_short_position is None and oldest.change_percent is None
    assert (data.count, data.limit, data.truncated) == (4, 50, False)
    assert "published_estimated" in data.note and warnings == ()


def test_a_row_holds_only_the_contract_fields(adapter: QualToolAdapter) -> None:
    data, _ = _short_interest(adapter)

    assert list(data.rows[0].model_dump()) == [
        "ticker",
        "settlement_date",
        "short_position",
        "previous_short_position",
        "change_percent",
        "average_daily_volume",
        "days_to_cover",
        "published_estimated",
        "issue_name",
        "split_flag",
        "revision_flag",
    ]


def test_several_tickers_are_answered_together(adapter: QualToolAdapter) -> None:
    data, warnings = _short_interest(adapter, tickers=["MSFT", "AAPL"])

    assert {row.ticker for row in data.rows} == {"AAPL", "MSFT"} and data.count == 6
    assert warnings == ()
    msft = next(
        row for row in data.rows if row.ticker == "MSFT" and row.average_daily_volume is None
    )
    assert msft.days_to_cover is None


def test_the_date_range_selects_settlement_dates(adapter: QualToolAdapter) -> None:
    data, _ = _short_interest(adapter, start_date="2026-09-30", end_date="2026-10-15")

    assert [row.settlement_date for row in data.rows] == [date(2026, 10, 15), date(2026, 9, 30)]


def test_without_dates_the_window_is_the_last_120_days(
    adapter: QualToolAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = {"tickers": ["AAPL"]}
    monkeypatch.setattr(tool_adapter, "_today", lambda: date(2027, 1, 12))  # 120 days: Sep 14
    data = adapter.execute("qual_get_short_interest", arguments, "d").data  # type: ignore[attr-defined]
    assert data.count == 4

    monkeypatch.setattr(tool_adapter, "_today", lambda: date(2027, 1, 13))  # window opens Sep 15
    data = adapter.execute("qual_get_short_interest", arguments, "d").data  # type: ignore[attr-defined]
    assert data.count == 4

    monkeypatch.setattr(tool_adapter, "_today", lambda: date(2027, 1, 14))  # Sep 15 is out
    data = adapter.execute("qual_get_short_interest", arguments, "d").data  # type: ignore[attr-defined]
    assert data.count == 3 and data.rows[-1].settlement_date == date(2026, 9, 30)


def test_only_a_start_date_runs_to_today_and_only_an_end_date_back_120_days(
    adapter: QualToolAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tool_adapter, "_today", lambda: date(2026, 11, 18))
    from_start = adapter.execute(
        "qual_get_short_interest", {"tickers": ["AAPL"], "start_date": "2026-10-15"}, "s"
    ).data  # type: ignore[attr-defined]
    to_end = adapter.execute(
        "qual_get_short_interest", {"tickers": ["AAPL"], "end_date": "2026-09-30"}, "e"
    ).data  # type: ignore[attr-defined]

    assert [row.settlement_date for row in from_start.rows] == [
        date(2026, 10, 30),
        date(2026, 10, 15),
    ]
    assert [row.settlement_date for row in to_end.rows] == [date(2026, 9, 30), date(2026, 9, 15)]


def test_a_limit_that_cuts_the_list_is_flagged_and_warned(adapter: QualToolAdapter) -> None:
    data, warnings = _short_interest(adapter, limit=2)

    assert (data.count, data.limit, data.truncated) == (2, 2, True)
    assert data.rows[0].settlement_date == date(2026, 10, 30)
    assert any("truncated" in warning for warning in warnings)


def test_a_ticker_with_no_figure_gets_a_warning(adapter: QualToolAdapter) -> None:
    data, warnings = _short_interest(adapter, tickers=["AAPL", "ZZZZ", "QQQQ"])

    assert data.count == 4
    assert warnings == (
        "no short interest figure for ZZZZ in this range",
        "no short interest figure for QQQQ in this range",
    )


def test_a_ticker_with_figures_only_outside_the_range_gets_the_warning(
    adapter: QualToolAdapter,
) -> None:
    data, warnings = _short_interest(adapter, tickers=["MSFT"], end_date="2026-09-20")

    assert data.rows == ()
    assert warnings == ("no short interest figure for MSFT in this range",)


def test_hidden_characters_in_the_issue_name_are_dropped(adapter: QualToolAdapter) -> None:
    data, _ = _short_interest(adapter, tickers=["BOLT"])

    (row,) = data.rows
    assert HIDDEN_NAME != "Bolt Synthetic Corp"  # the fixture really holds them
    assert row.issue_name == "Bolt Synthetic Corp"


@pytest.mark.parametrize(
    "arguments",
    [
        {"tickers": []},
        {"tickers": [f"T{i}" for i in range(26)]},
        {"tickers": ["AAPL", "AAPL"]},
        {"tickers": ["aapl"]},
        {"tickers": ["AAPL"], "limit": 501},
        {"tickers": ["AAPL"], "limit": 0},
        {"tickers": ["AAPL"], "start_date": "2026-10-31", "end_date": "2026-10-01"},
        {"tickers": ["AAPL"], "start_date": "2024-01-01", "end_date": "2026-10-31"},
        {"tickers": ["AAPL"], "start_date": "2024-01-01"},  # runs to today: over 800 days
        {"tickers": ["AAPL"], "start_date": "2027-01-01"},  # after today
        {"tickers": ["AAPL"], "unknown": 1},
    ],
)
def test_bad_requests_are_refused(
    adapter: QualToolAdapter, monkeypatch: pytest.MonkeyPatch, arguments: dict[str, object]
) -> None:
    monkeypatch.setattr(tool_adapter, "_today", lambda: date(2026, 11, 18))
    with pytest.raises(ToolInputError):
        adapter.execute("qual_get_short_interest", arguments, "bad")


def test_a_lake_without_the_dataset_is_unavailable_not_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "parquet").mkdir()
    empty = QualToolAdapter(
        DataInterface(
            tmp_path / "parquet", news_parquet_root=tmp_path / "news", clock=lambda: CLOCK
        )
    )

    with pytest.raises(ToolUnavailableError):
        empty.execute("qual_get_short_interest", {"tickers": ["AAPL"], **RANGE}, "none")
