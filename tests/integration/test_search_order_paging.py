"""qual_search_news order and paging: passed to the Data Interface (1.16), default unchanged."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from stram_data.data_interface import DataInterface, NewsQuery, NewsResult, NewsRow

from stram_qualitative_mcp.errors import ToolInputError
from stram_qualitative_mcp.tool_adapter import QualToolAdapter
from stram_qualitative_mcp.tool_models import (
    MAX_RESULT_ROWS,
    CleanNewsSearchData,
    NewsSearchData,
    NewsSearchInput,
)
from tests.conftest import SYNTHETIC_LAKE

OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}
STAMP = "2026-10-20T12:00:00+00:00"
CURSOR = f"published_asc|{STAMP}|{'0' * 36}|{STAMP}|{'1' * 36}"
MOMENT = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _search(adapter: QualToolAdapter, **arguments: object) -> NewsSearchData:
    envelope = adapter.execute("qual_search_news", {**OCTOBER, **arguments}, "search")
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, NewsSearchData)
    return data


def _pages(adapter: QualToolAdapter, **arguments: object) -> list[NewsSearchData]:
    pages: list[NewsSearchData] = []
    cursor = None
    while True:
        page = _search(adapter, limit=1, after=cursor, **arguments)
        pages.append(page)
        if page.next_cursor is None:
            return pages
        assert page.truncated and len(pages) < 50
        cursor = page.next_cursor


# --- against the synthetic lake, through the real Data Interface ---------------------------


def test_a_call_without_order_or_after_is_what_it_was(tool_adapter: QualToolAdapter) -> None:
    default = _search(tool_adapter, tickers=["AAPL"])
    assert default.next_cursor is None and not default.truncated
    assert default == _search(tool_adapter, tickers=["AAPL"], order="published_desc")
    published = [row.published_at for row in default.rows]
    assert published == sorted(published, reverse=True)


def test_published_asc_reverses_the_default_order(tool_adapter: QualToolAdapter) -> None:
    newest = [row.article_id for row in _search(tool_adapter, tickers=["AAPL"]).rows]
    oldest = [
        row.article_id
        for row in _search(tool_adapter, tickers=["AAPL"], order="published_asc").rows
    ]
    assert oldest == newest[::-1]


@pytest.mark.parametrize("order", ["published_desc", "published_asc"])
def test_pages_of_one_row_join_into_the_whole_result(
    tool_adapter: QualToolAdapter, order: str
) -> None:
    whole = [r.article_id for r in _search(tool_adapter, tickers=["AAPL"], order=order).rows]
    pages = _pages(tool_adapter, tickers=["AAPL"], order=order)
    assert [r.article_id for page in pages for r in page.rows] == whole
    assert len(pages) == len(whole) >= 3
    assert all(page.truncated for page in pages[:-1]) and not pages[-1].truncated


def test_copies_desc_lists_the_most_carried_story_first(tool_adapter: QualToolAdapter) -> None:
    rows = _search(tool_adapter, tickers=["AAPL", "INTC"], order="copies_desc").rows
    copies = [row.copies for row in rows]
    assert copies == sorted(copies, reverse=True) and copies[0] == 2


def test_as_of_holds_on_every_page(tool_adapter: QualToolAdapter) -> None:
    hidden = "Synthetic backfilled story"
    for page in _pages(tool_adapter, tickers=["AAPL"], as_of="2026-10-20"):
        assert hidden not in [row.title for row in page.rows]


def test_the_clean_view_carries_the_cursor(tool_adapter: QualToolAdapter) -> None:
    envelope = tool_adapter.execute(
        "qual_search_news",
        {**OCTOBER, "tickers": ["AAPL"], "limit": 1, "view": "clean"},
        "clean",
    )
    data = envelope.data  # type: ignore[attr-defined]
    assert isinstance(data, CleanNewsSearchData)
    assert data.truncated and data.next_cursor is not None
    assert _search(tool_adapter, tickers=["AAPL"], limit=1).next_cursor == data.next_cursor


# --- input checks --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {"order": "sideways"},
        {"order": "copies_desc", "collapse_stories": False},
        {"order": "published_desc", "after": CURSOR},  # a cursor of another order
        {"after": "not a cursor"},
        {"after": "published_desc|" + "9" * 300},
        {"limit": MAX_RESULT_ROWS + 1},
    ],
)
def test_bad_order_cursor_or_limit_is_refused(
    tool_adapter: QualToolAdapter, arguments: dict[str, object]
) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute(
            "qual_search_news", {**OCTOBER, "tickers": ["AAPL"], **arguments}, "bad"
        )


def test_a_cursor_the_interface_does_not_recognise_is_an_input_error(
    tool_adapter: QualToolAdapter,
) -> None:
    with pytest.raises(ToolInputError):
        tool_adapter.execute(
            "qual_search_news",
            {**OCTOBER, "tickers": ["AAPL"], "order": "published_asc", "after": CURSOR[:-4]},
            "forged",
        )


def test_the_row_cap_is_unchanged() -> None:
    assert MAX_RESULT_ROWS == 100
    schema = NewsSearchInput.model_json_schema()["properties"]
    assert schema["limit"]["maximum"] == 100
    assert schema["order"]["default"] == "published_desc" and schema["after"]["default"] is None


# --- against a stand-in for the Data Interface ---------------------------------------------


class RecordingData:
    """Remembers the NewsQuery it was given and answers with a truncated page."""

    def __init__(self) -> None:
        self.queries: list[NewsQuery] = []

    def describe_availability_policies(self) -> Any:
        return DataInterface(SYNTHETIC_LAKE).describe_availability_policies()

    def get_news(self, query: NewsQuery) -> NewsResult:
        self.queries.append(query)
        row = NewsRow.model_validate(
            {
                "article_id": "a" * 8 + "-aaaa-aaaa-aaaa-" + "a" * 12,
                "event_id": "b" * 8 + "-bbbb-bbbb-bbbb-" + "b" * 12,
                "event_type": "news.article",
                "provider": "finnhub",
                "publisher": None,
                "title": "Synthetic",
                "summary": None,
                "url": "https://example.test/x",
                "published_at": MOMENT,
                "first_ingested_at": MOMENT,
                "ingested_at": MOMENT,
                "version_count": 1,
                "tickers": (),
                "regions": (),
                "language": None,
                "cik": None,
                "accession_number": None,
                "body_status": "pending",
                "body_path": None,
                "quality_flags": (),
            }
        )
        return NewsResult(
            rows=(row,),
            count=1,
            limit=query.limit,
            truncated=True,
            as_of=query.as_of,
            all_versions=False,
            availability_note="note",
            next_cursor="published_asc|next",
        )


def test_order_and_cursor_reach_the_data_interface_and_its_cursor_comes_back() -> None:
    data = RecordingData()
    adapter = QualToolAdapter(data)  # type: ignore[arg-type]
    arguments: dict[str, Any] = {
        **OCTOBER,
        "tickers": ["AAPL"],
        "order": "published_asc",
        "after": CURSOR,
        "limit": 100,
    }
    envelope = adapter.execute("qual_search_news", arguments, "recorded")
    sent = data.queries[0]
    assert (sent.order, sent.after, sent.limit) == ("published_asc", CURSOR, 100)
    assert sent.collapse_stories is True
    assert envelope.data.next_cursor == "published_asc|next"  # type: ignore[attr-defined]


def test_without_them_the_defaults_are_sent() -> None:
    data = RecordingData()
    QualToolAdapter(data).execute(  # type: ignore[arg-type]
        "qual_search_news", {**OCTOBER, "tickers": ["AAPL"]}, "default"
    )
    sent = data.queries[0]
    assert (sent.order, sent.after) == ("published_desc", None)
