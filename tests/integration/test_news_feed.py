from __future__ import annotations

from datetime import UTC, datetime

import pytest
from stram_data.data_interface import DataInterface

from stram_qualitative_mcp.errors import ToolInputError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import NewsFeedData
from tests.conftest import SYNTHETIC_LAKE

# The synthetic AAPL items were ingested from 17 to 20 October and on 30 October.
CLOCK = datetime(2026, 10, 21, tzinfo=UTC)


@pytest.fixture
def adapter() -> QualToolAdapter:
    return QualToolAdapter(
        DataInterface(SYNTHETIC_LAKE, news_parquet_root=SYNTHETIC_LAKE, clock=lambda: CLOCK)
    )


def _feed(adapter: QualToolAdapter, **arguments: object) -> tuple[NewsFeedData, tuple[str, ...]]:
    envelope = adapter.execute(
        "qual_get_news_feed", {"tickers": ["AAPL"], "max_age_hours": 168, **arguments}, "feed"
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, NewsFeedData)
    return data, envelope.warnings  # type: ignore[attr-defined]


def test_feed_returns_new_versions_oldest_first_with_search_defaults(
    adapter: QualToolAdapter,
) -> None:
    data, warnings = _feed(adapter)
    # Flagged items and links below the default 0.6 confidence are left out, as in search.
    assert [row.title for row in data.rows] == [
        "Synthetic 8-K announcement",
        "Synthetic Apple supplier update",
    ]
    assert all(row.ingested_at <= data.settled_until for row in data.rows)
    assert data.rows[0].event_id and not data.truncated and warnings == ()


def test_the_cursor_continues_without_repeats(adapter: QualToolAdapter) -> None:
    first, warnings = _feed(adapter, limit=1)
    assert first.truncated and warnings == (
        "More news is waiting; call again at once with next_cursor.",
    )
    rest, _ = _feed(adapter, after=first.next_cursor)
    assert [row.title for row in rest.rows] == ["Synthetic Apple supplier update"]
    empty, _ = _feed(adapter, after=rest.next_cursor)
    assert empty.rows == () and empty.next_cursor == rest.next_cursor


def test_old_publications_are_not_news(adapter: QualToolAdapter) -> None:
    data, _ = _feed(adapter, max_age_hours=24)
    assert [row.title for row in data.rows] == ["Synthetic Apple supplier update"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"tickers": []},
        {"tickers": [f"T{i}" for i in range(51)]},
        {"tickers": ["aapl"]},
        {"after": "not a cursor"},
        {"after": "2026-10-20T00:00:00+00:00|; DROP"},
        {"limit": 101},
        {"max_age_hours": 169},
        {"unexpected": True},
    ],
)
def test_bad_requests_are_rejected(adapter: QualToolAdapter, arguments: dict[str, object]) -> None:
    with pytest.raises(ToolInputError):
        adapter.execute("qual_get_news_feed", {"tickers": ["AAPL"], **arguments}, "feed")
