from __future__ import annotations

from datetime import UTC, datetime

from stram_data.data_interface import DataInterface

from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import COVERAGE_LIMITATIONS, CoverageData, TimelineData
from tests.conftest import SYNTHETIC_LAKE

OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


def _coverage(adapter: QualToolAdapter) -> CoverageData:
    data = adapter.execute("qual_describe_coverage", {}, "coverage").data  # type: ignore[attr-defined]
    assert isinstance(data, CoverageData)
    return data


def _timeline(adapter: QualToolAdapter, **arguments: object) -> TimelineData:
    envelope = adapter.execute(
        "qual_get_news_timeline", {**OCTOBER, "tickers": ["AAPL"], **arguments}, "timeline"
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, TimelineData)
    return data


def test_coverage_describes_sources_and_limits(tool_adapter: QualToolAdapter) -> None:
    data = _coverage(tool_adapter)
    assert {row.provider for row in data.providers} == {"finnhub", "gdelt", "sec"}
    assert "AAPL" in data.tracked_tickers
    assert data.limitations == COVERAGE_LIMITATIONS
    assert data.gdelt_window_days == 30


def test_coverage_counts_only_recorded_text(tool_adapter: QualToolAdapter) -> None:
    totals = {row.provider: row for row in _coverage(tool_adapter).providers}
    assert totals["sec"].articles_with_text == 0
    assert totals["finnhub"].articles_with_text >= 2


def test_coverage_works_when_no_gdelt_falls_in_the_window() -> None:
    data = DataInterface(
        SYNTHETIC_LAKE,
        news_parquet_root=SYNTHETIC_LAKE,
        clock=lambda: datetime(2036, 1, 1, tzinfo=UTC),
    )
    assert _coverage(QualToolAdapter(data)).missing_gdelt_slot_count == 0


def test_timeline_defaults_match_search(tool_adapter: QualToolAdapter) -> None:
    timeline = _timeline(tool_adapter)
    search = tool_adapter.execute("qual_search_news", {**OCTOBER, "tickers": ["AAPL"]}, "search")
    assert sum(row.articles for row in timeline.rows) == search.data.count  # type: ignore[attr-defined]


def test_timeline_labels_tone_and_shows_how_many_articles_back_it(
    tool_adapter: QualToolAdapter,
) -> None:
    rows = {row.day.day: row for row in _timeline(tool_adapter, min_confidence=0.0).rows}
    assert rows[19].gdelt_article_tone == 1.5
    assert rows[19].tone_articles == 1
    assert rows[20].gdelt_article_tone is None
    assert rows[20].tone_articles == 0
    assert "not sentiment" in _timeline(tool_adapter).tone_note


def test_timeline_counts_stories_beside_articles(tool_adapter: QualToolAdapter) -> None:
    rows = _timeline(tool_adapter, tickers=["INTC"]).rows
    assert [(row.articles, row.stories) for row in rows] == [(2, 1)]


def test_days_without_articles_are_absent(tool_adapter: QualToolAdapter) -> None:
    assert 2 not in {row.day.day for row in _timeline(tool_adapter).rows}
